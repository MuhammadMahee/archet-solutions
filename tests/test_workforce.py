"""Workforce boundaries: real SQLite, isolated account and sales services."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import time
from uuid import uuid4

import pytest

from api import index, workforce, workforce_ai as ai, sales
from api.workforce_store import Store
from test_portal import store, client, login, write


@pytest.fixture(autouse=True)
def local_workforce(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKFORCE_ENABLED', 'true')
    monkeypatch.setitem(index.app.config, 'WORKFORCE_DB_PATH', str(tmp_path / 'workforce.sqlite3'))
    monkeypatch.setattr(ai.Ollama, 'models', lambda self: ['qwen3:1.7b'])


@pytest.fixture
def queue(client):
    with index.app.app_context():
        return workforce.get_store()


def chat(client, members=None):
    response = write(client, 'workforce/conversations', {'title': 'Operations', 'member_ids': members or []})
    assert response.status_code == 201, response.json
    return response.json['id']


def send(client, cid, **changes):
    return write(client, f'workforce/conversations/{cid}/messages',
                 {'content': 'Summarize yesterday sales', 'request_id': str(uuid4()), **changes})


def report(start, end, filters=None):
    return {'start': start.isoformat(), 'end': end.isoformat(), 'updated_at': '2026-10-09T12:00:00+00:00',
            'rows': [{'dealer': 'Connect', 'market': 'DALLAS', 'store': '=UNTRUSTED()', 'total_boxes': 12, 'accessory': 240, 'incomplete': False}],
            'totals': {'total_boxes': 12, 'accessory': 240}, 'coverage': {'complete': 6, 'expected': 6, 'retained': 0}}


class Model:
    def __init__(self):
        self.calls = []
    def local_model(self, model):
        pass
    def chat(self, model, system, content, schema=None):
        self.calls.append((system, content))
        if schema:
            day = (sales.today() - timedelta(days=1)).isoformat()
            return json.dumps({'action': 'sales', 'message': 'I will delegate this sales report to Operations.',
                               'start': day, 'end': day, 'dealer': '', 'market': ''})
        return 'The saved report records 12 total boxes. Accessory sales are 240. Coverage is complete.'


@pytest.mark.parametrize('path', ['workforce/status', 'workforce/conversations', 'workforce/conversations/' + str(uuid4()), 'workforce/tasks/' + str(uuid4()) + '/report.csv'])
def test_auth_required(client, path):
    assert client.get('/api/internal/' + path).status_code == 401


def test_membership_is_required_even_for_other_admin(client, store, queue):
    login(client)
    cid = chat(client, [store.member['id']])
    task_id = send(client, cid).json['task_id']
    login(client, 'OtherAdmin')
    assert client.get('/api/internal/workforce/conversations').json['conversations'] == []
    assert client.get('/api/internal/workforce/conversations/' + cid).status_code == 404
    assert send(client, cid).status_code == 404
    assert client.get(f'/api/internal/workforce/tasks/{task_id}/audit').status_code == 404
    assert client.get(f'/api/internal/workforce/tasks/{task_id}/report.csv').status_code == 404
    login(client, 'Member')
    assert client.get('/api/internal/workforce/conversations/' + cid).status_code == 200
    assert send(client, cid, invoke_agents=False).status_code == 201
    assert write(client, f'workforce/tasks/{task_id}/cancel', {}).status_code == 403


def test_group_creation_and_model_settings_are_admin_only(client, store):
    login(client, 'Member')
    assert write(client, 'workforce/conversations', {'title': 'Shared', 'member_ids': [store.owner['id']]}).status_code == 403
    assert chat(client)
    assert write(client, 'workforce/settings', {'model': 'qwen3:1.7b'}, method='PATCH').status_code == 403


def test_csrf_and_rest_account_checks(client, store):
    login(client)
    assert client.post('/api/internal/workforce/conversations', json={'title': 'x'}).status_code == 403
    store.tables['portal_users'][0]['rest_mode'] = True
    assert client.get('/api/internal/workforce/conversations').status_code == 403


def test_message_idempotency_persistence_and_invalid_reuse(client, queue):
    login(client)
    cid = chat(client)
    request_id = str(uuid4())
    first = send(client, cid, request_id=request_id).json
    assert send(client, cid, request_id=request_id).json == first
    assert send(client, cid, request_id=request_id, content='Different').status_code == 409
    reopened = Store(queue.path)
    with reopened.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1


@pytest.mark.parametrize('changes', [{'content': ''}, {'content': 'x' * 4001}, {'content': ['bad']}, {'request_id': {}}, {'request_id': 'bad'}, {'invoke_agents': 'true'}])
def test_input_validation(client, changes):
    login(client)
    assert send(client, chat(client), **changes).status_code == 400


def test_cursors_and_new_messages_are_ordered(client):
    login(client)
    cid = chat(client)
    ids = [send(client, cid, invoke_agents=False).json['message_seq'] for _ in range(3)]
    data = client.get(f'/api/internal/workforce/conversations/{cid}?after={ids[0]}').json
    assert [m['seq'] for m in data['messages']] == ids[1:]
    data = client.get(f'/api/internal/workforce/conversations/{cid}?before={ids[-1]}').json
    assert [m['seq'] for m in data['messages']] == ids[:2]
    for query in ['after=-1', 'after=oops', 'after=1&before=2', 'after=999999999999999999999999999']:
        assert client.get(f'/api/internal/workforce/conversations/{cid}?{query}').status_code == 400


def test_queue_bounds_and_cancel_retry(client, queue):
    login(client)
    cid = chat(client)
    tasks = [send(client, cid).json['task_id'] for _ in range(5)]
    assert send(client, cid).status_code == 429
    assert write(client, f'workforce/tasks/{tasks[0]}/cancel', {}).status_code == 200
    assert write(client, f'workforce/tasks/{tasks[0]}/retry', {}).status_code == 200
    assert write(client, f'workforce/tasks/{tasks[0]}/retry', {}).status_code == 409
    assert write(client, f'workforce/tasks/{tasks[0]}/cancel', {}).status_code == 200
    assert queue.claim('worker')['id'] != tasks[0]


def test_atomic_claim_no_duplicate_execution(client, queue):
    login(client)
    cid = chat(client)
    send(client, cid)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(queue.claim, ['worker1', 'worker2']))
    assert sum(r is not None for r in results) == 1


def test_expired_lease_and_old_worker_cannot_publish_after_retry(client, queue):
    login(client)
    cid = chat(client)
    task_id = send(client, cid).json['task_id']
    old = queue.claim('old')
    with queue.connection(True) as conn:
        conn.execute('UPDATE tasks SET lease_until=?', (time.time() - 1,))
    assert queue.claim('new') is None
    assert write(client, f'workforce/tasks/{task_id}/retry', {}).status_code == 200
    new = queue.claim('new')
    assert not queue.progress(old, 'Done', ai.MANAGER, 'Old result', complete=True)
    assert queue.active(new)


def test_full_delegation_readonly_tool_and_attached_report(client, queue, monkeypatch):
    login(client)
    cid = chat(client)
    task_id = send(client, cid).json['task_id']
    calls = []
    def read(*args, **kwargs):
        calls.append(kwargs['filters'])
        return report(*args, **kwargs)
    monkeypatch.setattr(sales, 'report_data', read)
    model = Model()
    ai.execute(queue, queue.claim('worker'), model)
    state = client.get('/api/internal/workforce/conversations/' + cid).json
    assert state['tasks'][0]['status'] == 'completed'
    assert state['tasks'][0]['has_report']
    assert state['messages'][-1]['report_ready']
    assert not any(m['report_ready'] for m in state['messages'][:-1])
    assert [m['sender_id'] for m in state['messages'][1:]] == ['ai-manager', 'ai-operations', 'ai-manager']
    assert len(model.calls) == 3 and len(calls) == 1
    download = client.get(f'/api/internal/workforce/tasks/{task_id}/report.csv')
    assert download.status_code == 200 and b"'=UNTRUSTED()" in download.data
    assert 'attachment;' in download.headers['Content-Disposition']
    events = client.get(f'/api/internal/workforce/tasks/{task_id}/audit').json['events']
    assert {'agent.delegated', 'tool.started', 'tool.completed', 'agent.completed', 'task.completed'} <= {e['event'] for e in events}


@pytest.mark.parametrize('change', ['active', 'rest_mode', 'session_version', 'role'])
def test_account_revalidated_before_tool_execution(client, queue, store, monkeypatch, change):
    login(client)
    cid = chat(client)
    send(client, cid)
    class Revoke(Model):
        def chat(self, *args):
            result = super().chat(*args)
            store.tables['portal_users'][0][change] = {'active': False, 'rest_mode': True, 'session_version': 'revoked', 'role': 'denied'}[change]
            return result
    def forbidden(*args, **kwargs):
        pytest.fail('Revoked user must not access sales data')
    monkeypatch.setattr(sales, 'report_data', forbidden)
    ai.execute(queue, queue.claim('worker'), Revoke())
    with queue.connection() as conn:
        row = conn.execute('SELECT * FROM tasks').fetchone()
        assert row['status'] == 'failed' and 'access changed' in row['error']


def test_cancel_during_model_call_drops_output(client, queue, store):
    login(client)
    cid = chat(client)
    task_id = send(client, cid).json['task_id']
    class Cancel(Model):
        def chat(self, *args):
            queue.control(task_id, store.tables['portal_users'][0], 'cancel')
            return super().chat(*args)
    ai.execute(queue, queue.claim('worker'), Cancel())
    snapshot = client.get('/api/internal/workforce/conversations/' + cid).json
    assert snapshot['tasks'][0]['status'] == 'cancelled'
    assert len(snapshot['messages']) == 1


def test_upstream_failure_never_leaks_credentials(client, queue, monkeypatch):
    login(client)
    cid = chat(client)
    send(client, cid)
    def failed(*args, **kwargs):
        raise RuntimeError('postgresql://secret:password@database')
    monkeypatch.setattr(sales, 'report_data', failed)
    ai.execute(queue, queue.claim('worker'), Model())
    response = client.get('/api/internal/workforce/conversations/' + cid)
    assert response.json['tasks'][0]['status'] == 'failed'
    assert b'password@' not in response.data


def test_model_failure_marks_failed_without_completed_message(client, queue):
    login(client)
    cid = chat(client)
    send(client, cid)
    class Offline(Model):
        def chat(self, *args):
            raise ai.AIError('Ollama timed out.')
    ai.execute(queue, queue.claim('worker'), Offline())
    response = client.get('/api/internal/workforce/conversations/' + cid).json
    assert response['tasks'][0]['status'] == 'failed' and len(response['messages']) == 1


def test_invalid_plan_cannot_add_tools():
    with pytest.raises(ai.AIError):
        ai.parse_plan('{"action":"shell","command":"anything"}')
    data = json.loads(Model().chat('model', '', '', True))
    data['end'] = (sales.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ai.AIError):
        ai.parse_plan(json.dumps(data))


def test_manager_can_reply_without_inventing_tool_execution(client, queue):
    login(client)
    cid = chat(client)
    send(client, cid, content='Can you calculate payroll?')
    class Reply(Model):
        def chat(self, *args):
            return json.dumps(dict(action='reply', message='Payroll is not connected.', start='', end='', dealer='', market=''))
    ai.execute(queue, queue.claim('worker'), Reply())
    result = client.get('/api/internal/workforce/conversations/' + cid).json
    assert result['tasks'][0]['status'] == 'completed' and not result['tasks'][0]['has_report']
    assert len(result['messages']) == 2
    with queue.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE event='tool.started'").fetchone()[0] == 0


def test_manager_receives_current_group_identity_and_history_only(client, queue, store):
    login(client)
    private = chat(client)
    send(client, private, content='PRIVATE OTHER CHAT', invoke_agents=False)
    cid = chat(client, [store.member['id']])
    send(client, cid, content='Call the project Sunrise.', invoke_agents=False)
    login(client, 'Member')
    send(client, cid, content='I can help with Sunrise.', invoke_agents=False)
    login(client)
    send(client, cid, content='Who is here and what did we decide?')
    task = queue.claim('worker')
    send(client, cid, content='FUTURE MESSAGE', invoke_agents=False)
    model = Model()
    def reply(model_name, system, content, schema=None):
        model.calls.append((system, content))
        return json.dumps(dict(action='reply', message='You are Mahee. Member is also here.', start='', end='', dealer='', market=''))
    model.chat = reply
    ai.execute(queue, task, model)
    assert len(model.calls) == 1
    context = json.loads(model.calls[0][1])
    assert context['requester'] == {'name': 'Mahee', 'kind': 'human'}
    assert {p['name'] for p in context['conversation']['participants']} == {'Mahee', 'Member', ai.MANAGER[1], ai.OPERATIONS[1]}
    assert [m['name'] for m in context['conversation']['recent_messages']] == ['Mahee', 'Member']
    assert 'Sunrise' in model.calls[0][1]
    for excluded in ('PRIVATE OTHER CHAT', 'FUTURE MESSAGE', 'OtherAdmin', 'session_version', store.owner['id']):
        assert excluded not in model.calls[0][1]
    assert context['current_request'] == 'Who is here and what did we decide?'
    assert queue.snapshot(cid, store.owner['id'])['tasks'][0]['status'] == 'completed'
    with queue.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE event='tool.started'").fetchone()[0] == 0


def test_manager_history_is_bounded_ordered_and_membership_checked(client, queue, store):
    login(client)
    cid = chat(client)
    for number in range(28):
        send(client, cid, content=f'{number}: ' + 'x' * 3900, invoke_agents=False)
    send(client, cid, content='Summarize our plan')
    task = queue.claim('worker')
    context = queue.assignment_context(task)
    history = context['recent_messages']
    assert context['history_limited'] is True
    assert sum(len(m['content']) for m in history) <= 9000
    assert all(len(m['content']) <= 2500 for m in history)
    assert history[-1]['content'].startswith('27: ')
    assert [int(m['content'].split(':')[0]) for m in history] == sorted(int(m['content'].split(':')[0]) for m in history)
    with pytest.raises(ai.portal.PortalError):
        queue.assignment_context({**task, 'creator_id': store.admin['id']})


def test_removing_membership_prevents_context_from_reaching_model(client, queue, store):
    login(client)
    cid = chat(client)
    send(client, cid)
    task = queue.claim('worker')
    with queue.connection(True) as conn:
        conn.execute('DELETE FROM members WHERE conversation_id=? AND user_id=?', (cid, store.owner['id']))
    model = Model()
    ai.execute(queue, task, model)
    assert model.calls == []


def test_ollama_transport_timeout_and_cloud_rejection(monkeypatch):
    class Offline:
        def open(self, *args, **kwargs):
            raise TimeoutError('private network detail')
    monkeypatch.setattr(ai, 'build_opener', lambda *args: Offline())
    with pytest.raises(ai.AIError, match='timed out'):
        ai.Ollama().request('/api/chat', {})
    with pytest.raises(ai.AIError):
        ai.Ollama('file:///private')
    with pytest.raises(ai.AIError, match='local chat model'):
        ai.Ollama().local_model('qwen3:cloud')
    monkeypatch.setattr(ai.Ollama, 'request', lambda *args, **kwargs: {'remote_host': 'https://example.com', 'capabilities': ['completion']})
    with pytest.raises(ai.AIError, match='Cloud'):
        ai.Ollama().local_model('custom-alias')


def test_serverless_uses_postgres_without_local_storage(client, monkeypatch):
    login(client)
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('SUPABASE_DB_URL', 'postgresql://test-only')
    with index.app.app_context():
        assert isinstance(workforce.get_store(), workforce.PostgresStore)


def test_dismiss_failed_card_is_persistent_private_and_preserves_history(client, queue, store):
    login(client)
    cid = chat(client, [store.member['id']])
    task_id = send(client, cid).json['task_id']
    queue.fail(queue.claim('worker'), 'Sample failure')
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 200
    assert client.get('/api/internal/workforce/conversations/' + cid).json['tasks'] == []
    assert len(client.get('/api/internal/workforce/conversations/' + cid).json['messages']) == 1
    assert client.get(f'/api/internal/workforce/tasks/{task_id}/audit').status_code == 200
    login(client, 'Member')
    assert len(client.get('/api/internal/workforce/conversations/' + cid).json['tasks']) == 1
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 200
    login(client, 'OtherAdmin')
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 404
    login(client)
    assert client.get('/api/internal/workforce/conversations/' + cid).json['tasks'] == []
    assert write(client, f'workforce/tasks/{task_id}/retry', {}).status_code == 200
    queue.fail(queue.claim('worker'), 'New attempt failed')
    assert len(client.get('/api/internal/workforce/conversations/' + cid).json['tasks']) == 1


def test_active_assignment_cannot_be_dismissed(client, queue):
    login(client)
    cid = chat(client)
    task_id = send(client, cid).json['task_id']
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 409
    queue.claim('worker')
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 409
    assert write(client, f'workforce/tasks/{task_id}/cancel', {}).status_code == 200
    assert write(client, f'workforce/tasks/{task_id}/dismiss', {}).status_code == 200


class AddAgents(Model):
    def chat(self, model, system, content, schema=None):
        self.calls.append((system, content))
        return json.dumps(dict(action='add_agents', message='Adding specialists.', start='', end='', dealer='', market='', agent_ids=['ai-hr', 'ai-finance']))


def add_specialists(client, queue, cid):
    sent = send(client, cid, content='Add HR and Finance bots to this group.').json
    ai.execute(queue, queue.claim('worker', sent['task_id']), AddAgents())
    return sent


def test_manager_adds_real_persistent_bots_to_current_group_only(client, queue, store):
    login(client)
    cid, other = chat(client, [store.member['id']]), chat(client)
    sent = add_specialists(client, queue, cid)
    reopened = Store(queue.path)
    assert reopened.snapshot(cid, store.owner['id'])['agent_ids'] == ['ai-manager', 'ai-operations', 'ai-hr', 'ai-finance']
    assert reopened.snapshot(other, store.owner['id'])['agent_ids'] == ['ai-manager', 'ai-operations']
    state = client.get('/api/internal/workforce/conversations/' + cid).json
    assert state['tasks'][0]['status'] == 'completed'
    assert '@hr' in state['messages'][-1]['content'] and '@finance' in state['messages'][-1]['content']
    assert {p['handle'] for p in state['participants']} >= {'Mahee', 'Member', 'manager', 'hr', 'finance'}
    assert all('session_version' not in p for p in state['participants'])
    add_specialists(client, queue, cid)
    assert len(reopened.snapshot(cid, store.owner['id'])['agent_ids']) == 4
    with queue.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE event='agents.added'").fetchone()[0] == 2


def test_member_cannot_add_bots_to_someone_elses_group(client, queue, store):
    login(client)
    cid = chat(client, [store.member['id']])
    login(client, 'Member')
    add_specialists(client, queue, cid)
    state = queue.snapshot(cid, store.member['id'])
    assert state['agent_ids'] == ['ai-manager', 'ai-operations']
    assert 'group creator' in state['tasks'][0]['error']
    personal = chat(client)
    add_specialists(client, queue, personal)
    assert 'ai-hr' in queue.snapshot(personal, store.member['id'])['agent_ids']


def test_cancelled_addition_cannot_mutate_roster(client, queue, store):
    login(client)
    cid = chat(client)
    task_id = send(client, cid).json['task_id']
    task = queue.claim('worker')
    queue.control(task_id, store.owner, 'cancel')
    assert not queue.progress(task, 'Added', ai.MANAGER, complete=True, agents=['ai-hr'], user=store.owner)
    assert 'ai-hr' not in queue.snapshot(cid, store.owner['id'])['agent_ids']


@pytest.mark.parametrize('agents', [['ai-admin'], ['ai-manager'], ['ai-hr'] * 7, 'ai-hr'])
def test_model_cannot_add_arbitrary_agents_or_tools(agents):
    payload = dict(action='add_agents', message='Add', start='', end='', dealer='', market='', agent_ids=agents)
    with pytest.raises(ai.AIError):
        ai.parse_plan(json.dumps(payload))


def test_mentions_are_scoped_persisted_and_route_to_specialists(client, queue, store):
    login(client)
    cid = chat(client, [store.member['id']])
    add_specialists(client, queue, cid)
    sent = send(client, cid, content='@hr @finance Draft a hiring budget.', invoke_agents=False).json
    assert sent['task_id']
    task = queue.claim('worker', sent['task_id'])
    model = Model()
    ai.execute(queue, task, model)
    assert len(model.calls) == 2
    state = queue.snapshot(cid, store.owner['id'])
    assert {m['sender_id'] for m in state['messages'][-2:]} == {'ai-hr', 'ai-finance'}
    assert state['tasks'][0]['status'] == 'completed'
    assert any(m['mention_ids'] == ['ai-finance', 'ai-hr'] for m in state['messages'])
    model_payload = json.loads(model.calls[0][1])
    assert {p['handle'] for p in model_payload['mentioned']} == {'hr', 'finance'}
    other = chat(client)
    response = send(client, other, content='@hr Hello', invoke_agents=False).json
    assert not response['task_id']
    assert queue.snapshot(other, store.owner['id'])['messages'][-1]['mention_ids'] == []
    with pytest.raises(ai.portal.PortalError):
        queue.enqueue(other, store.owner, '@hr', str(uuid4()), 'model', True, ['ai-hr'])


def test_human_ping_does_not_run_ai_and_has_unread_marker(client, queue, store):
    login(client)
    cid = chat(client, [store.member['id']])
    sent = send(client, cid, content='@Member Please review this.', invoke_agents=True).json
    assert sent['task_id'] is None
    assert queue.list_chats(store.member['id'])[0]['mention_seq'] == sent['message_seq']
    assert queue.list_chats(store.owner['id'])[0]['mention_seq'] is None
    assert queue.snapshot(cid, store.member['id'])['messages'][0]['mention_ids'] == [store.member['id']]
    send(client, cid, content='someone@Member.com @MemberExtra @OtherAdmin `@Member` ```text\n@Member\n```', invoke_agents=False)
    assert queue.snapshot(cid, store.owner['id'])['messages'][-1]['mention_ids'] == []


def test_human_bot_handle_collision_is_unambiguous(client, queue, store):
    from api.workforce_agents import mentioned_people
    human = store.add_user('finance', 'member')
    people = ai.conversation_people([human['id']], ['ai-finance'])
    assert mentioned_people('@finance', people)[0]['id'] == 'ai-finance'
    assert mentioned_people('@user-finance', people)[0]['id'] == human['id']


def test_explicit_manager_mention_can_manage_already_mentioned_bots(client, queue, store):
    login(client)
    cid = chat(client)
    add_specialists(client, queue, cid)
    sent = send(client, cid, content='@manager Add @hr and Finance to this group.').json
    model = AddAgents()
    ai.execute(queue, queue.claim('worker', sent['task_id']), model)
    assert len(model.calls) == 1
    state = queue.snapshot(cid, store.owner['id'])
    assert state['tasks'][0]['status'] == 'completed'
    assert state['messages'][-1]['sender_id'] == 'ai-manager'

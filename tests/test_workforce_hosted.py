"""Hosted execution lifecycle and AI Gateway transport, without paid API calls."""
from io import BytesIO
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest

from api import index, workforce, workforce_ai as ai, workforce_hosted as hosted, sales
from api.workforce_postgres import Connection, PostgresStore
from api.workforce_store import Store
from test_portal import store, client, login, write
from test_workforce import Model, report


@pytest.fixture
def hosted_queue(client, monkeypatch, tmp_path):
    monkeypatch.setenv('WORKFORCE_AI_PROVIDER', 'vercel')
    monkeypatch.setenv('AI_GATEWAY_API_KEY', 'test-key-not-a-real-credential')
    monkeypatch.setenv('WORKFORCE_ENABLED', 'true')
    monkeypatch.delenv('WORKFORCE_MODELS', raising=False)
    monkeypatch.delenv('WORKFORCE_MODEL', raising=False)
    queue = Store(tmp_path / 'hosted.sqlite3')
    queue.lease_seconds = 330
    monkeypatch.setattr(workforce, 'get_store', lambda: queue)
    model = Model()
    model.models = lambda: [hosted.DEFAULT_MODEL]
    monkeypatch.setattr(workforce, 'ai_client', lambda: model)
    monkeypatch.setattr(sales, 'report_data', report)
    login(client)
    return queue, model


def create(client):
    return write(client, 'workforce/conversations', {'title': 'Hosted assignments'}).json['id']


def test_hosted_send_completes_without_worker_and_duplicate_is_free(client, hosted_queue):
    queue, model = hosted_queue
    cid = create(client)
    payload = {'content': 'Summarize yesterday sales', 'request_id': str(uuid4())}
    for _ in range(2):
        response = write(client, f'workforce/conversations/{cid}/messages', payload)
        assert response.status_code == 201
    state = client.get('/api/internal/workforce/conversations/' + cid).json
    assert state['tasks'][0]['status'] == 'completed'
    assert len(state['messages']) == 4 and len(model.calls) == 3
    csv = client.get('/api/internal/workforce/tasks/' + response.json['task_id'] + '/report.csv')
    assert csv.status_code == 200 and b'TOTAL' in csv.data
    info = client.get('/api/internal/workforce/status').json
    assert info['provider'] == 'vercel' and info['execution'] == 'request'
    assert info['model'] == hosted.DEFAULT_MODEL


def test_cancel_during_hosted_generation_discards_answer(client, hosted_queue):
    queue, model = hosted_queue
    def cancel(*args, **kwargs):
        with queue.connection() as conn:
            task = dict(conn.execute('SELECT * FROM tasks').fetchone())
        user = {'id': task['creator_id']}
        queue.control(task['id'], user, 'cancel')
        return json.dumps({'action': 'reply', 'message': 'Must not publish', 'start': '', 'end': '', 'dealer': '', 'market': ''})
    model.chat = cancel
    cid = create(client)
    write(client, f'workforce/conversations/{cid}/messages', {'content': 'Hello', 'request_id': str(uuid4())})
    state = client.get('/api/internal/workforce/conversations/' + cid).json
    assert state['tasks'][0]['status'] == 'cancelled' and len(state['messages']) == 1


def test_pending_recovery_owner_only_and_expired_lease(client, hosted_queue, store):
    queue, model = hosted_queue
    cid = create(client)
    user = store.tables['portal_users'][0]
    task = queue.enqueue(cid, user, 'Sales yesterday', str(uuid4()), hosted.DEFAULT_MODEL)['task_id']
    login(client, 'OtherAdmin')
    assert write(client, f'workforce/tasks/{task}/run', {}).status_code == 404
    login(client)
    old = queue.claim('old-invocation', task)
    with queue.connection(True) as conn:
        conn.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (task,))
    state = client.get('/api/internal/workforce/conversations/' + cid).json
    assert state['tasks'][0]['status'] == 'failed'
    assert write(client, f'workforce/tasks/{task}/retry', {}).status_code == 200
    assert not queue.progress(old, 'Stale', ai.MANAGER, 'Stale result', complete=True)
    assert client.get('/api/internal/workforce/conversations/' + cid).json['tasks'][0]['status'] == 'completed'
    pending = queue.enqueue(cid, user, 'Sales yesterday', str(uuid4()), hosted.DEFAULT_MODEL)['task_id']
    assert write(client, f'workforce/tasks/{pending}/run', {}).status_code == 200
    assert len(model.calls) == 6


def test_gateway_payload_is_bounded_and_has_schema(monkeypatch):
    monkeypatch.setenv('AI_GATEWAY_API_KEY', 'fake-key')
    calls = []
    def request(req, timeout):
        calls.append(req)
        assert timeout <= 45
        return BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': 'answer'}}]}).encode())
    monkeypatch.setattr(hosted, 'build_opener', lambda *_: SimpleNamespace(open=request))
    ai_client = hosted.VercelAI()
    assert ai_client.chat(hosted.DEFAULT_MODEL, 'system', 'user', ai.PLAN_SCHEMA) == 'answer'
    req = calls[0]
    assert req.full_url == 'https://ai-gateway.vercel.sh/v1/chat/completions'
    assert req.get_header('Authorization') == 'Bearer fake-key'
    data = json.loads(req.data)
    assert data['response_format']['json_schema']['schema'] == ai.PLAN_SCHEMA
    assert data['max_tokens'] == 1200 and data['stream'] is False
    assert 'fake-key' not in req.data.decode()


@pytest.mark.parametrize('code', [401, 403, 402, 429, 500])
def test_gateway_errors_never_expose_secrets(monkeypatch, code):
    monkeypatch.setenv('AI_GATEWAY_API_KEY', 'secret')
    def request(*args, **kwargs):
        raise HTTPError('https://example.com', code, 'SECRET UPSTREAM', {}, BytesIO(b'SECRET'))
    monkeypatch.setattr(hosted, 'build_opener', lambda *_: SimpleNamespace(open=request))
    with pytest.raises(ai.AIError) as error:
        hosted.VercelAI().chat(hosted.DEFAULT_MODEL, '', '')
    assert 'SECRET' not in str(error.value)


@pytest.mark.parametrize('reply', [b'not JSON', b'{}', b'{"choices":[]}',
    b'{"choices":[{"finish_reason":"length","message":{"content":"cut off"}}]}'])
def test_gateway_invalid_or_truncated_output(monkeypatch, reply):
    monkeypatch.setenv('AI_GATEWAY_API_KEY', 'secret')
    monkeypatch.setattr(hosted, 'build_opener', lambda *_: SimpleNamespace(open=lambda *a, **k: BytesIO(reply)))
    with pytest.raises(ai.AIError):
        hosted.VercelAI().chat(hosted.DEFAULT_MODEL, '', '')


def test_oidc_authentication_allowlist_and_missing_credentials(monkeypatch):
    monkeypatch.delenv('AI_GATEWAY_API_KEY', raising=False)
    monkeypatch.setenv('VERCEL_OIDC_TOKEN', 'oidc-test')
    client = hosted.VercelAI()
    assert client.key == 'oidc-test'
    with pytest.raises(ai.AIError):
        client.local_model('unconfigured/expensive-model')
    monkeypatch.delenv('VERCEL_OIDC_TOKEN')
    with pytest.raises(ai.AIError, match='Enable Vercel AI Gateway'):
        hosted.VercelAI().local_model(hosted.DEFAULT_MODEL)
    with pytest.raises(ai.AIError):
        hosted.NoRedirect().redirect_request()


def test_gateway_timeout_and_execution_budget(monkeypatch):
    monkeypatch.setenv('AI_GATEWAY_API_KEY', 'secret')
    def unavailable(*args, **kwargs):
        raise URLError('secret-url')
    monkeypatch.setattr(hosted, 'build_opener', lambda *_: SimpleNamespace(open=unavailable))
    client = hosted.VercelAI()
    with pytest.raises(ai.AIError, match='unavailable'):
        client.chat(hosted.DEFAULT_MODEL, '', '')
    client.deadline = 0
    with pytest.raises(ai.AIError, match='time limit'):
        client.chat(hosted.DEFAULT_MODEL, '', '')


def test_postgres_adapter_preserves_values_and_transaction(monkeypatch):
    from api import workforce_postgres as postgres
    calls = []
    class DB:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            calls.append(('transaction_end', args[0]))
        def execute(self, sql, values=()):
            calls.append((sql, values))
    def connect(url, **kwargs):
        assert kwargs['sslmode'] == 'require' and kwargs['prepare_threshold'] is None
        return DB()
    monkeypatch.setattr(postgres.psycopg, 'connect', connect)
    store = PostgresStore('postgresql://test')
    with pytest.raises(ValueError), store.connection(True) as conn:
        conn.execute('SELECT * FROM messages WHERE content=?', ("untrusted'?%s",))
        raise ValueError('rollback')
    assert ('SELECT * FROM messages WHERE content=%s', ("untrusted'?%s",)) in calls
    assert any('pg_advisory_xact_lock' in c[0] for c in calls)
    assert calls[-1] == ('transaction_end', ValueError)

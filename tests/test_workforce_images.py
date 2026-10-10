from io import BytesIO
import base64
import json
import random
from types import SimpleNamespace
from urllib.error import HTTPError
from uuid import uuid4

from PIL import Image
import pytest
from api import workforce_ai as ai, workforce_hosted as hosted, workforce_images as images
from api.portal import PortalError
from test_portal import store, client, login, write
from test_workforce import local_workforce, queue, chat, send, Model


def sample():
    output = BytesIO()
    Image.new('RGB', (100, 60), '#38aa99').save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode()


def test_upload_persists_privately_and_duplicate_does_not_copy(client, queue, store):
    login(client)
    cid = chat(client, [store.member['id']])
    request_id = str(uuid4())
    for _ in range(2):
        response = send(client, cid, content='', images=[{'data': sample()}], invoke_agents=False, request_id=request_id)
        assert response.status_code == 201
    state = queue.snapshot(cid, store.owner['id'])
    assert len(state['messages']) == 1
    picture = state['messages'][0]['images'][0]
    assert 'data' not in picture
    path = '/api/internal/workforce/images/' + picture['id']
    response = client.get(path)
    assert response.status_code == 200 and response.mimetype == 'image/png'
    assert 'no-store' in response.headers['Cache-Control']
    assert Image.open(BytesIO(response.data)).size == (100, 60)
    login(client, 'Member')
    assert client.get(path).status_code == 200
    login(client, 'OtherAdmin')
    assert client.get(path).status_code == 404
    store.tables['portal_users'][2]['rest_mode'] = True
    assert client.get(path).status_code == 403


@pytest.mark.parametrize('payload', [[{'data': 'broken!'}], [{'data': base64.b64encode(b'<svg onload="alert(1)"/>').decode()}], [{}], 'bad', [{'data': 'a' * 1400001}], [{'data': sample()}] * 3])
def test_invalid_images_do_not_save_messages(client, queue, store, payload):
    login(client)
    cid = chat(client)
    assert send(client, cid, images=payload).status_code == 400
    assert queue.snapshot(cid, store.owner['id'])['messages'] == []


def test_image_upload_accepts_realistic_size_and_rolls_back_when_storage_full(client, queue, store):
    login(client)
    cid = chat(client)
    output = BytesIO()
    Image.frombytes('RGB', (300, 300), random.Random(1).randbytes(270000)).save(output, format='PNG')
    assert len(output.getvalue()) > 32000
    picture = {'data': base64.b64encode(output.getvalue()).decode()}
    assert send(client, cid, images=[picture], invoke_agents=False).status_code == 201
    with queue.connection(True) as conn:
        conn.execute('UPDATE message_images SET size=?', (100 * 1024 * 1024,))
    assert send(client, cid, images=[picture], invoke_agents=False).status_code == 413
    assert len(queue.snapshot(cid, store.owner['id'])['messages']) == 1


def test_cancel_during_capture_does_not_publish_image(client, queue, store, monkeypatch):
    login(client)
    cid = chat(client)
    task_id = send(client, cid, content='Screenshot https://example.com').json['task_id']
    def capture(*args):
        queue.control(task_id, store.owner, 'cancel')
        return images.text_image('Example', 'Synthetic website')
    monkeypatch.setattr(ai, 'website_image', capture)
    class Plan(Model):
        def chat(self, *args, **kwargs):
            return json.dumps(dict(action='website_screenshot', message='Capture the page.', url='https://example.com', agent_ids=[], start='', end='', dealer='', market=''))
    ai.execute(queue, queue.claim('worker', task_id), Plan())
    state = queue.snapshot(cid, store.owner['id'])
    assert state['tasks'][0]['status'] == 'cancelled'
    assert len(state['messages']) == 1
    with queue.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM message_images').fetchone()[0] == 0


def test_vision_reads_upload_and_remembers_for_followups(client, queue, store):
    login(client)
    cid = chat(client)
    send(client, cid, content='', images=[{'data': sample()}], invoke_agents=False)
    sent = send(client, cid, content='What is in that screenshot?').json
    class Vision(Model):
        def describe_images(self, pictures):
            assert len(pictures) == 1 and pictures[0]['mime'] == 'image/png'
            return 'A green rectangle.'
        def chat(self, model, system, content, schema=None):
            self.calls.append((system, content))
            return json.dumps(dict(action='reply', message='A green rectangle.', start='', end='', dealer='', market=''))
    model = Vision()
    ai.execute(queue, queue.claim('worker', sent['task_id']), model)
    assert json.loads(model.calls[0][1])['uploaded_image_notes'] == 'A green rectangle.'
    following = send(client, cid, content='What color was it?').json
    task = queue.claim('worker', following['task_id'])
    assert queue.task_images(task) == []
    ai.execute(queue, task, model)
    assert json.loads(model.calls[-1][1])['conversation']['earlier_image_notes'][0]['analysis'] == 'A green rectangle.'


@pytest.mark.parametrize('action', ['summary_image', 'website_screenshot'])
def test_bot_image_is_attached_only_after_tool_success(client, queue, store, monkeypatch, action):
    login(client)
    cid = chat(client)
    sent = send(client, cid, content='Send a screenshot of https://example.com').json
    monkeypatch.setattr(ai, 'website_image', lambda *args: images.text_image('Example', 'Synthetic website capture'))
    class Plan(Model):
        def chat(self, *args, **kwargs):
            return json.dumps(dict(action=action, message='A sample summary.', url='https://example.com' if action == 'website_screenshot' else '', agent_ids=[], start='', end='', dealer='', market=''))
    ai.execute(queue, queue.claim('worker', sent['task_id']), Plan())
    state = queue.snapshot(cid, store.owner['id'])
    assert state['tasks'][0]['status'] == 'completed'
    assert state['messages'][-1]['images'][0]['mime'] == 'image/png'


@pytest.mark.parametrize('url,prompt', [
    ('https://example.com/secret', 'Capture https://example.com'),
    ('http://example.com', 'Capture http://example.com'),
    ('https://127.0.0.1', 'Capture https://127.0.0.1'),
    ('https://example.com?token=secret', 'Capture https://example.com?token=secret'),
    ('https://user:password@example.com', 'Capture https://user:password@example.com'),
    ('https://internal.archetsolutions.com', 'Capture https://internal.archetsolutions.com'),
])
def test_website_url_must_be_explicit_public_and_credential_free(url, prompt, monkeypatch):
    monkeypatch.setattr(images.socket, 'getaddrinfo', lambda *a, **k: [(None,None,None,None,('127.0.0.1' if '127.' in a[0] else '93.184.216.34',443))])
    with pytest.raises(PortalError):
        images.public_url(url, prompt)


def test_website_capture_only_uses_fixed_service_and_its_cdn(monkeypatch):
    monkeypatch.setattr(images.socket, 'getaddrinfo', lambda *a, **k: [(None,None,None,None,('93.184.216.34',443))])
    calls = []
    def request(req, **kwargs):
        calls.append(req)
        if len(calls) == 1:
            return BytesIO(json.dumps({'status':'success','data':{'screenshot':{'url':'https://iad.microlink.io/example.png'}}}).encode())
        return BytesIO(base64.b64decode(sample()))
    monkeypatch.setattr(images, 'build_opener', lambda *_: SimpleNamespace(open=request))
    output = images.website_image('https://example.com', 'Capture `https://example.com`.')
    assert output['mime'] == 'image/png'
    assert calls[0].full_url.startswith('https://api.microlink.io/?')
    assert calls[1].full_url == 'https://iad.microlink.io/example.png'
    assert all(req.get_header('Authorization') is None and req.get_header('Cookie') is None for req in calls)


def test_vision_uses_groq_image_model_and_keeps_key_out_of_payload(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'PRIVATE-KEY')
    def request(req, **kwargs):
        body = json.loads(req.data)
        assert body['model'] == hosted.GROQ_VISION_MODEL
        assert body['max_completion_tokens'] == 800
        assert 'max_tokens' not in body
        assert body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        assert 'PRIVATE-KEY' not in req.data.decode()
        return BytesIO(b'{"choices":[{"finish_reason":"stop","message":{"content":"Green rectangle"}}]}')
    monkeypatch.setattr(hosted, 'build_opener', lambda *_: SimpleNamespace(open=request))
    assert hosted.GroqAI().describe_images([{'mime':'image/png','data':sample()}]) == 'Green rectangle'


def test_oversized_groq_request_does_not_recommend_waiting():
    error = HTTPError('https://api.groq.com', 429, 'limit', {}, BytesIO(b'{"error":{"message":"Request too large for model","code":"rate_limit_exceeded"}}'))
    with pytest.raises(ai.AIError, match='per-request allowance'):
        hosted.GroqAI().http_error(error)

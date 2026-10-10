"""AI Workforce endpoints reuse portal cookies, CSRF checks and account rules."""
import csv
import base64
from io import StringIO
import os
from pathlib import Path
import sqlite3
from threading import Lock
from uuid import uuid4

from flask import current_app, g, jsonify, request, Response

from api import portal, sales
from api.portal import PortalError, require_user, body, text_field, valid_id
from api.workforce_ai import AIError, Ollama, execute, conversation_people
from api.workforce_agents import AGENTS, mentioned_people
from api.workforce_store import Store
from api.workforce_hosted import VercelAI, GroqAI, hosted, default_model, provider, model_setting, groq_model
from api.workforce_postgres import PostgresStore
from api.workforce_images import upload_images

ROOT = Path(__file__).resolve().parents[1]
_stores = {}
_lock = Lock()


def get_store():
    if os.getenv('WORKFORCE_ENABLED', 'true').lower() != 'true':
        raise PortalError('AI Workforce is disabled.', 503)
    if os.getenv('VERCEL') or hosted():
        return PostgresStore()
    path = current_app.config.get('WORKFORCE_DB_PATH') or os.getenv('WORKFORCE_DB_PATH') or str(ROOT / '.data' / 'workforce.sqlite3')
    path = str(Path(path).resolve())
    with _lock:
        if path not in _stores:
            _stores[path] = Store(path)
        return _stores[path]


def ai_client():
    if provider() == 'groq':
        return GroqAI()
    return VercelAI() if hosted() else Ollama()


def selected_model(store):
    model = store.model(default_model(), model_setting())
    return groq_model(model) if provider() == 'groq' else model


def run_assignment(store, task_id, user):
    if not hosted():
        return
    with store.connection() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            raise PortalError('Assignment not found.', 404)
        store.member(conn, row['conversation_id'], user['id'])
        if row['creator_id'] != user['id']:
            raise PortalError('Only the requesting employee can start this assignment.', 403)
    task = store.claim('vercel-' + str(uuid4()), task_id)
    if task:
        execute(store, task, ai_client())


def register_workforce(app):
    @app.errorhandler(sqlite3.Error)
    def workforce_storage_error(exc):
        app.logger.warning('Local workforce storage unavailable (%s)', type(exc).__name__)
        return jsonify(message='Workforce storage is unavailable. Check the AI server disk and database permissions.'), 503

    @app.errorhandler(AIError)
    def workforce_ai_error(exc):
        return jsonify(message=str(exc)), 503

    @app.get('/api/internal/workforce/status')
    @require_user()
    def workforce_status():
        store = get_store()
        error = None
        client = ai_client()
        model = selected_model(store)
        try:
            models = client.models()
            if hosted():
                client.local_model(model)
        except AIError as exc:
            models, error = [], str(exc)
        return jsonify(employees=list(AGENTS.values()), models=models, ollama_online=error is None,
                       model=model, provider=provider(),
                       execution='request' if hosted() else 'worker',
                       ai_configured=error is None,
                       worker_online=store.worker_online(), error=error,
                       demo=bool(app.config.get('WORKFORCE_DEMO', False)),
                       integrations=[{'name': 'Saved sales reports', 'connected': bool(os.getenv('SUPABASE_DB_URL')) or bool(app.config.get('WORKFORCE_DEMO'))},
                                     {'name': 'Commissions, targets, HR and document knowledge', 'connected': False}])

    @app.patch('/api/internal/workforce/settings')
    @require_user(admin=True)
    def workforce_settings():
        store = get_store()
        model = text_field(body(), 'model', 150)
        client = ai_client()
        if model not in client.models():
            raise PortalError('Select one of the available models.')
        client.local_model(model)
        store.set_model(model, g.portal_user['id'], model_setting())
        return jsonify(model=model)

    @app.get('/api/internal/workforce/conversations')
    @require_user()
    def workforce_chats():
        store = get_store()
        return jsonify(conversations=store.list_chats(g.portal_user['id']), worker_online=store.worker_online())

    @app.post('/api/internal/workforce/conversations')
    @require_user()
    def workforce_create_chat():
        store = get_store()
        payload = body()
        title = text_field(payload, 'title', 80)
        members = payload.get('member_ids', [])
        if not isinstance(members, list) or len(members) > 20 or any(not isinstance(uid, str) for uid in members):
            raise PortalError('Choose up to 20 team members.')
        members = list({valid_id(uid) for uid in members} - {g.portal_user['id']})
        if members and g.portal_user['role'] != 'admin':
            raise PortalError('An administrator must create shared groups.', 403)
        for uid in members:
            users = portal.db('portal_users', id='eq.' + uid, limit=1)
            if not users or not users[0]['active'] or users[0].get('rest_mode'):
                raise PortalError('A selected employee is unavailable.')
        portal.rate_limit('workforce-create', g.portal_user['id'], 20, 3600)
        chat = store.create_chat(title, g.portal_user['id'], members)
        return jsonify(id=chat), 201

    @app.get('/api/internal/workforce/conversations/<chat>')
    @require_user()
    def workforce_chat(chat):
        try:
            after, before = int(request.args.get('after', '0')), int(request.args.get('before', '0'))
        except ValueError:
            raise PortalError('Invalid message cursor.') from None
        if min(after, before) < 0 or max(after, before) >= 9223372036854775807 or (after and before):
            raise PortalError('Invalid message cursor.')
        store = get_store()
        if hosted():
            store.expire()
        state = store.snapshot(valid_id(chat), g.portal_user['id'], after, before)
        state['participants'] = conversation_people(state['member_ids'], state['agent_ids'])
        state['can_add_agents'] = g.portal_user['role'] == 'admin' or state['conversation']['creator_id'] == g.portal_user['id']
        return jsonify(state)

    @app.post('/api/internal/workforce/conversations/<chat>/messages')
    @require_user()
    def workforce_send(chat):
        store = get_store()
        payload = body()
        images = upload_images(payload.get('images', []))
        content = text_field(payload, 'content', 4000, required=not images) or 'Please review the attached screenshot.'
        request_id = valid_id(text_field(payload, 'request_id', 36))
        invoke = payload.get('invoke_agents', True)
        if type(invoke) is not bool:
            raise PortalError('Invalid AI assignment preference.')
        _, members, agents = store.roster(valid_id(chat), g.portal_user['id'])
        mentioned = mentioned_people(content, conversation_people(members, agents))
        # A direct human ping is a chat message; mentioning a bot explicitly
        # invokes that bot even if automatic Manager replies are unchecked.
        if mentioned:
            invoke = any(p['kind'] == 'ai' for p in mentioned)
        portal.rate_limit('workforce-message', g.portal_user['id'], 60, 60)
        result = store.enqueue(valid_id(chat), g.portal_user, content, request_id,
                               selected_model(store), invoke, [p['id'] for p in mentioned], images)
        if result['task_id']:
            run_assignment(store, result['task_id'], g.portal_user)
        return jsonify(result), 201

    @app.get('/api/internal/workforce/images/<image_id>')
    @require_user()
    def workforce_image(image_id):
        image = get_store().image(valid_id(image_id), g.portal_user['id'])
        return Response(base64.b64decode(image['data']), mimetype=image['mime'], headers={
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': 'inline; filename="chat-image.' + ('png' if image['mime'] == 'image/png' else 'jpg') + '"'})

    @app.post('/api/internal/workforce/tasks/<task_id>/<action>')
    @require_user()
    def workforce_task_action(task_id, action):
        if action not in ('cancel', 'retry', 'run', 'dismiss') or (action == 'run' and not hosted()):
            raise PortalError('Not found.', 404)
        body()
        store = get_store()
        task_id = valid_id(task_id)
        if action == 'dismiss':
            store.dismiss(task_id, g.portal_user['id'])
        elif action != 'run':
            store.control(task_id, g.portal_user, action)
        if action in ('retry', 'run'):
            run_assignment(store, task_id, g.portal_user)
        return jsonify(status='success')

    @app.get('/api/internal/workforce/tasks/<task_id>/snapshot')
    @require_user()
    def workforce_snapshot(task_id):
        result = get_store().result(valid_id(task_id), g.portal_user['id'])
        # Render the saved report using the same canvas as Sales Update's Copy Snapshot.
        # Older reports predate stored color fills; derive them from their saved rows.
        return jsonify({**result, 'metric_fills': result.get('metric_fills') or sales.metric_fills(result['rows'])})

    @app.get('/api/internal/workforce/tasks/<task_id>/report.csv')
    @require_user()
    def workforce_report(task_id):
        result = get_store().result(valid_id(task_id), g.portal_user['id'])
        out = StringIO(newline='')
        writer = csv.writer(out)
        columns = ['dealer', 'market', 'store', 'new_activation', 'upgrade', 'reactivation', 'bts', 'hsi', 'accessory', 'total_boxes', 'qpay', 'apo', 'qpay_conv', 'stale', 'incomplete']
        def safe(value):
            if value is None:
                return ''
            text = str(value)
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text
        writer.writerow(['Source', result['source']])
        writer.writerow(['From', result['start'], 'To', result['end']])
        writer.writerow(['Updated', result['updated_at'] or 'Not available'])
        writer.writerow(['Completed source-days', result['coverage']['complete'], 'Expected', result['coverage']['expected'], 'Retained', result['coverage']['retained']])
        writer.writerow(['Dealer filter', safe(result['filters']['dealer'] or 'All'), 'Market filter', safe(result['filters']['market'] or 'All')])
        writer.writerow(columns)
        for row in [*result['rows'], {'store': 'TOTAL', **result['totals']}]:
            writer.writerow([safe(row.get(key)) for key in columns])
        return Response('\ufeff' + out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="archet-sales-{task_id}.csv"'})

    @app.get('/api/internal/workforce/tasks/<task_id>/audit')
    @require_user()
    def workforce_audit(task_id):
        store = get_store()
        with store.connection() as conn:
            task = conn.execute('SELECT * FROM tasks WHERE id=?', (valid_id(task_id),)).fetchone()
            if not task:
                raise PortalError('Task not found.', 404)
            store.member(conn, task['conversation_id'], g.portal_user['id'])
            rows = [dict(r) for r in conn.execute('SELECT event,details,created_at FROM audit WHERE task_id=? ORDER BY seq', (task_id,))]
        return jsonify(events=rows)

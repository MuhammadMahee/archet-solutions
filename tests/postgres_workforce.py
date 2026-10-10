"""Exercise real PostgreSQL SQL in isolated PGlite/WASM, never production.

Requires Chromium from requirements-dev and internet for the pinned public
PGlite module. Does not test the Supabase network connection or TLS transport.
"""
from contextlib import contextmanager
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from api.workforce_store import Store
from api.portal import PortalError

ROOT = Path(__file__).resolve().parents[1]


class Rows:
    def __init__(self, result):
        self.rows = result['rows']
        self.rowcount = result.get('affectedRows', 0)
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows
    def __iter__(self):
        return iter(self.rows)


class SQL:
    def __init__(self, page):
        self.page = page
    def execute(self, sql, params=()):
        parts = sql.split('?')
        statement = parts[0] + ''.join('$' + str(i) + part for i, part in enumerate(parts[1:], 1))
        # Preserve PostgreSQL int64 values across the browser's JSON/Number boundary.
        values = [str(v) if isinstance(v, int) and abs(v) > 2**53 - 1 else v for v in params]
        return Rows(self.page.evaluate('async ([sql,params]) => await db.query(sql,params)', [statement, values]))
    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)


class PgStore(Store):
    def __init__(self, page):
        self.sql = SQL(page)
    @contextmanager
    def connection(self, write=False):
        self.sql.execute('BEGIN')
        self.sql.execute('SET LOCAL search_path TO archet_workforce, pg_catalog')
        try:
            yield self.sql
            self.sql.execute('COMMIT')
        except BaseException:
            self.sql.execute('ROLLBACK')
            raise


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.evaluate('''async () => {
            const {PGlite} = await import('https://cdn.jsdelivr.net/npm/@electric-sql/pglite@0.5.8/dist/index.js');
            window.db = new PGlite(); await db.waitReady;
            await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;');
        }''')
        page.evaluate('sql => db.exec(sql)', (ROOT / 'supabase/migrations/012_ai_workforce.sql').read_text())
        page.evaluate('sql => db.exec(sql)', (ROOT / 'supabase/migrations/013_workforce_agents_mentions.sql').read_text())
        page.evaluate('sql => db.exec(sql)', (ROOT / 'supabase/migrations/014_workforce_images.sql').read_text())
        store = PgStore(page)
        user = {'id': str(uuid4()), 'display_name': 'Sample employee', 'session_version': str(uuid4())}
        other = str(uuid4())
        cid = store.create_chat('Sample PostgreSQL chat', user['id'], [other])
        assert len(store.list_chats(user['id'])) == 1
        assert store.list_chats(str(uuid4())) == []
        request_id = str(uuid4())
        task = store.enqueue(cid, user, 'Sample sales question', request_id, 'sample/model')
        assert store.enqueue(cid, user, 'Sample sales question', request_id, 'sample/model') == task
        try:
            store.enqueue(cid, user, 'Different message', request_id, 'sample/model')
        except PortalError as exc:
            assert exc.status == 409
        else:
            raise AssertionError('Expected duplicate-content rejection')
        store.heartbeat('worker')
        assert store.worker_online()
        claimed = store.claim('worker', task['task_id'])
        assert store.claim('other-worker', task['task_id']) is None
        assert store.active(claimed)
        context = store.assignment_context(claimed)
        assert context['title'] == 'Sample PostgreSQL chat' and context['recent_messages'] == []
        assert set(context['member_ids']) == {user['id'], other}
        result = {'rows': [{'store': 'Sample'}], 'totals': {'total_boxes': 12, 'accessory': 240},
                  'coverage': {'complete': 1, 'expected': 1, 'retained': 0}, 'start': '2026-10-08', 'end': '2026-10-08'}
        assert store.progress(claimed, 'Done', ('ai-manager', 'AI Manager'), 'Sample summary', complete=True, result=result)
        state = store.snapshot(cid, other)
        assert state['messages'][-1]['report_summary']['total_boxes'] == 12
        assert store.result(task['task_id'], other) == result
        assert len(store.snapshot(cid, other, after=state['messages'][0]['seq'])['messages']) == 1
        assert len(store.snapshot(cid, other, before=state['messages'][-1]['seq'])['messages']) == 1
        store.set_model('sample/updated', user['id'])
        assert store.model('fallback') == 'sample/updated'
        second = store.enqueue(cid, user, 'Cancel this', str(uuid4()), 'sample/model')['task_id']
        store.control(second, user, 'cancel')
        store.control(second, user, 'retry')
        running = store.claim('worker', second)
        assert store.latest_report(running) == result
        context = store.assignment_context(running)
        assert [m['content'] for m in context['recent_messages']] == ['Sample sales question', 'Sample summary']
        with store.connection(True) as conn:
            conn.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (second,))
        store.expire()
        assert not store.progress(running, 'Stale', complete=True)
        store.control(second, user, 'retry')
        running = store.claim('worker', second)
        store.fail(running, 'Sample failure')
        assert store.snapshot(cid, other)['tasks'][0]['status'] == 'failed'
        store.dismiss(second, user['id'])
        assert all(t['id'] != second for t in store.snapshot(cid, user['id'])['tasks'])
        assert store.snapshot(cid, other)['tasks'][0]['id'] == second
        user['role'] = 'admin'
        add = store.enqueue(cid, user, 'Add HR', str(uuid4()), 'sample/model')['task_id']
        add_task = store.claim('worker', add)
        assert store.progress(add_task, 'Added', ('ai-manager', 'AI Manager'), complete=True, agents=['ai-hr'], user=user)
        assert 'ai-hr' in store.snapshot(cid, other)['agent_ids']
        ping = store.enqueue(cid, user, '@hr @teammate Hello', str(uuid4()), 'sample/model', False, ['ai-hr', other])
        assert set(store.snapshot(cid, other)['messages'][-1]['mention_ids']) == {'ai-hr', other}
        assert store.list_chats(other)[0]['mention_seq'] == ping['message_seq']
        from api.workforce_images import text_image
        picture = text_image('Test', 'Isolated PostgreSQL image')
        image_task = store.enqueue(cid, user, 'Review image', str(uuid4()), 'sample/model', images=[picture])
        claimed_image = store.claim('worker', image_task['task_id'])
        uploaded = store.task_images(claimed_image)
        assert len(uploaded) == 1
        assert store.image(uploaded[0]['id'], other)['data'] == picture['data']
        store.remember_images(claimed_image, 'Test image', uploaded)
        assert store.task_images(claimed_image)[0]['analysis'] == 'Test image'
        assert store.progress(claimed_image, 'Done', ('ai-manager', 'AI Manager'), 'Image response', complete=True, images=[picture])
        assert len(store.snapshot(cid, other)['messages'][-1]['images']) == 1
        denied = page.evaluate('''async () => {
            await db.exec('SET ROLE anon');
            try { await db.query('SELECT * FROM archet_workforce.messages'); return false; }
            catch (e) { return e.code === '42501'; }
            finally { await db.exec('RESET ROLE'); }
        }''')
        assert denied
        print('PASS: PostgreSQL migration, private schema permissions, chat, idempotency, claim, progress, report, pagination, settings, cancellation, retry and expired leases. Isolated WASM database only.')
        browser.close()


if __name__ == '__main__':
    main()

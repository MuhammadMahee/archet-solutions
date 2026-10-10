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
        with store.connection(True) as conn:
            conn.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (second,))
        store.expire()
        assert not store.progress(running, 'Stale', complete=True)
        store.control(second, user, 'retry')
        running = store.claim('worker', second)
        store.fail(running, 'Sample failure')
        assert store.snapshot(cid, other)['tasks'][0]['status'] == 'failed'
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

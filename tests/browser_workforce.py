"""Browser + worker + SQLite test. --live-ollama uses real inference with labeled sample data."""
import argparse
import os
from contextlib import ExitStack
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, sales, workforce, workforce_ai as ai
from api.workforce_store import Store
from test_portal import FakeStore
from test_workforce import Model, report


def demo_report(start, end, filters=None):
    data = report(start, end, filters)
    data['rows'][0]['store'] = 'DEMO Dallas Sample Store'
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-ollama', action='store_true')
    parser.add_argument('--hosted', action='store_true', help='Test Vercel request execution with an isolated store and model double.')
    parser.add_argument('--groq', action='store_true', help='Test the Groq provider UI using isolated sample data.')
    args = parser.parse_args()
    args.hosted = args.hosted or args.groq
    if args.hosted and args.live_ollama:
        parser.error('Choose hosted simulation or live Ollama, not both.')
    artifacts = ROOT / 'test-results' / 'workforce'
    artifacts.mkdir(parents=True, exist_ok=True)
    fake = FakeStore()
    stop = Event()
    failures = []
    with TemporaryDirectory(prefix='archet-workforce-test-') as temporary, ExitStack() as stack:
        queue = Store(Path(temporary) / 'demo.sqlite3')
        stack.enter_context(patch.dict(index.app.config, WORKFORCE_DB_PATH=queue.path, WORKFORCE_DEMO=True))
        stack.enter_context(patch.object(portal, 'db', fake.db))
        stack.enter_context(patch.object(portal, 'auth', fake.auth))
        stack.enter_context(patch.object(index, 'db', fake.db))
        stack.enter_context(patch.object(sales, 'report_data', demo_report))
        if args.hosted:
            stack.enter_context(patch.dict(os.environ, WORKFORCE_AI_PROVIDER='groq' if args.groq else 'vercel'))
            stack.enter_context(patch.object(workforce, 'get_store', lambda: queue))
            class HostedModel(Model):
                def models(self):
                    return ['openai/gpt-oss-120b' if args.groq else 'google/gemini-2.5-flash-lite']
            stack.enter_context(patch.object(workforce, 'ai_client', HostedModel))
        if not args.live_ollama:
            stack.enter_context(patch.object(ai.Ollama, 'models', lambda self: ['qwen3:1.7b']))
        def worker():
            while not stop.is_set():
                try:
                    queue.heartbeat('browser-worker')
                    task = queue.claim('browser-worker')
                    if task:
                        ai.execute(queue, task, None if args.live_ollama else Model())
                except Exception as exc:
                    failures.append(type(exc).__name__)
                    return
                stop.wait(.15)
        # Real inference can last longer than a lease; keep a separate heartbeat just like the CLI worker.
        def heartbeat():
            while not stop.wait(5):
                queue.heartbeat('browser-worker')
        worker_thread = Thread(target=worker, daemon=True)
        heartbeat_thread = Thread(target=heartbeat, daemon=True)
        server = make_server('127.0.0.1', 0, index.app, threaded=True)
        server_thread = Thread(target=server.serve_forever, daemon=True)
        origin = f'http://127.0.0.1:{server.server_port}'
        server_thread.start()
        if not args.hosted:
            worker_thread.start(); heartbeat_thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page(); errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(origin + '/ai-workforce')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#page-workforce')).to_be_visible()
                expect(page.locator('#wf-demo')).to_be_visible()
                if args.hosted:
                    expect(page.locator('#wf-worker')).to_have_text('AI runs on Vercel')
                    page.locator('#wf-settings').click()
                    expect(page.locator('#wf-connection')).to_contain_text('Groq: Configured' if args.groq else 'Vercel AI Gateway: Configured')
                    expect(page.locator('#wf-worker-help')).to_contain_text('Groq Free plan' if args.groq else 'hosted model')
                    page.locator('#wf-settings-dialog .close').click()
                page.screenshot(path=str(artifacts / 'empty-desktop.png'), full_page=True)
                page.locator('#wf-start').click()
                page.locator('#wf-new-title').fill('Daily Operations · Demo')
                expect(page.locator('#wf-people option')).to_have_count(2)
                page.locator('#wf-people').select_option(fake.member['id'])
                page.locator('#wf-new-form button[type=submit]').click()
                expect(page.locator('#wf-title')).to_have_text('Daily Operations · Demo')
                page.locator('#wf-input').fill('Summarize yesterday\'s saved sales for all stores.')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(4, timeout=600000 if args.live_ollama else 15000)
                expect(page.locator('.wf-task[data-status="completed"]')).to_have_count(0)
                expect(page.locator('.wf-message.operations')).to_have_count(1)
                expect(page.locator('#wf-messages')).to_contain_text('12')
                expect(page.locator('.wf-source')).to_contain_text('$240.00')
                if args.live_ollama:
                    actual = page.locator('#wf-messages').inner_text().lower()
                    assert 'no saved records matched' not in actual, actual
                    assert '240 accessories' not in actual, actual
                with page.expect_download() as download:
                    page.get_by_role('link', name='Download source report').click()
                downloaded = download.value
                target = artifacts / 'sample-sales.csv'
                downloaded.save_as(target)
                assert 'DEMO Dallas Sample Store' in target.read_text(encoding='utf-8-sig')
                page.screenshot(path=str(artifacts / ('live-desktop.png' if args.live_ollama else 'chat-desktop.png')), full_page=True)
                # History persists through a page reload and still has exactly one job.
                page.reload()
                expect(page.locator('#wf-chats .wf-chat')).to_have_count(1)
                page.locator('#wf-chats .wf-chat').click()
                expect(page.locator('.wf-message')).to_have_count(4)
                page.locator('#wf-invoke').uncheck()
                page.locator('#wf-input').fill('<img src=x onerror="alert(1)"> **safe text**')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(5)
                assert page.locator('#wf-messages img').count() == 0
                page.locator('#wf-message-search').fill('safe text')
                expect(page.locator('.wf-message')).to_have_count(1)
                page.locator('#wf-message-search').fill('')
                page.set_viewport_size({'width': 390, 'height': 844})
                expect(page.locator('#wf-back')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(artifacts / 'chat-mobile.png'), full_page=True)
                page.locator('#wf-back').click()
                expect(page.locator('#wf-chats')).to_be_visible()
                page.locator('#wf-chats .wf-chat').click()
                expect(page.locator('#wf-input')).to_be_visible()
                # A second actual browser session can read this shared group with its own account.
                member_context = browser.new_context()
                member = member_context.new_page(); member.goto(origin + '/ai-workforce')
                member.locator('#login-username').fill('Member'); member.locator('#login-password').fill('TestPass123')
                member.locator('#login-form button[type=submit]').click()
                expect(member.locator('#wf-chats .wf-chat')).to_have_count(1)
                member.locator('#wf-chats .wf-chat').click()
                expect(member.locator('.wf-message')).to_have_count(5)
                if args.hosted:
                    user = fake.tables['portal_users'][0]
                    cid = queue.list_chats(user['id'])[0]['id']
                    queue.enqueue(cid, user, 'Sample failed assignment', str(uuid4()), 'sample/model')
                    queue.fail(queue.claim('sample-failure'), 'Sample gateway setup error')
                    expect(page.get_by_role('button', name='Dismiss failed assignment')).to_be_visible()
                    page.screenshot(path=str(artifacts / 'failed-card-mobile.png'), full_page=True)
                    page.get_by_role('button', name='Dismiss failed assignment').click()
                    expect(page.locator('.wf-task[data-status="failed"]')).to_have_count(0)
                    page.reload()
                    page.locator('#wf-chats .wf-chat').click()
                    expect(page.locator('.wf-message')).to_have_count(6)
                    expect(page.locator('.wf-task[data-status="failed"]')).to_have_count(0)
                    expect(member.locator('.wf-task[data-status="failed"]')).to_have_count(1)
                fake.tables['portal_users'][0]['rest_mode'] = True
                expect(page.locator('#account-rest')).to_be_visible(timeout=10000)
                assert page.locator('#wf-messages').inner_text() == ''
                assert page.locator('#wf-chats').inner_text() == ''
                assert not errors, errors
                assert not failures, failures
                member_context.close(); context.close(); browser.close()
                with queue.connection() as conn:
                    assert conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == (2 if args.hosted else 1)
                    assert conn.execute("SELECT COUNT(*) FROM audit WHERE event='tool.completed'").fetchone()[0] == 1
                print('PASS: login, group membership, manager delegation, sales tool, persisted result, CSV, reload, safe rendering, mobile, second user, rest-mode privacy.' + (' REAL LOCAL OLLAMA; SAMPLE SALES ONLY.' if args.live_ollama else ' Deterministic model double.'), flush=True)
        finally:
            stop.set(); server.shutdown(); server.server_close()
            if not args.hosted:
                worker_thread.join(timeout=200); heartbeat_thread.join(timeout=10)
            server_thread.join(timeout=10)


if __name__ == '__main__':
    main()

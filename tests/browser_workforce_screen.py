"""Full-screen Workforce navigation, independent scrolling and shared appearance."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from uuid import uuid4
import logging
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, workforce
from api.workforce_store import Store
from test_portal import FakeStore


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    artifacts = ROOT/'test-results/workforce-screen'
    artifacts.mkdir(parents=True, exist_ok=True)
    fake = FakeStore()
    with TemporaryDirectory() as tmp, ExitStack() as stack:
        queue = Store(Path(tmp)/'screen.sqlite3')
        for module in (portal, index):
            stack.enter_context(patch.object(module, 'db', fake.db))
        stack.enter_context(patch.object(portal, 'auth', fake.auth))
        stack.enter_context(patch.object(workforce, 'get_store', lambda: queue))
        class Client:
            def models(self): return ['sample']
            def local_model(self, *args): pass
        stack.enter_context(patch.object(workforce, 'ai_client', Client))
        for title in ['Store managers', 'Sales updates', 'Daily operations']:
            cid = queue.create_chat(title, fake.owner['id'], [fake.member['id']])
            for user, content in [(fake.member, 'Morning team! The opening checklist is ready for review.'),
                                  (fake.owner, 'Thanks. Please share any updates here so everyone has the same context.'),
                                  (fake.member, 'Will do. Everything is on track for today.')]:
                queue.enqueue(cid, user, content, str(uuid4()), 'sample', invoke=False)
        server = make_server('127.0.0.1', 0, index.app, threaded=True)
        Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width':1440,'height':900})
                page = context.new_page(); errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin+'/internal#settings')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#page-settings')).to_be_visible()
                page.locator('nav [data-page=workforce]').click()
                expect(page).to_have_url(origin+'/ai-workforce#workforce')
                expect(page.locator('.wf-chat')).to_have_count(3)

                def fullscreen():
                    expect(page.locator('#workspace-sidebar')).to_be_hidden()
                    expect(page.locator('.topbar')).to_be_hidden()
                    assert page.evaluate('''() => {
                        const shell=document.querySelector('#page-workforce').getBoundingClientRect();
                        const layout=document.querySelector('.wf-layout').getBoundingClientRect();
                        return shell.x===0 && shell.y===0 && shell.width===innerWidth &&
                            Math.abs(shell.height-innerHeight)<1 && Math.abs(layout.bottom-innerHeight)<1 &&
                            document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight;
                    }''')

                fullscreen()
                page.screenshot(path=str(artifacts/'welcome.png'),full_page=True)
                page.locator('.wf-chat').first.click()
                expect(page.locator('.wf-message')).to_have_count(3)
                expect(page.locator('.wf-chat.selected')).to_have_count(1)
                for mode, surface in [('light','rgb(255, 255, 255)'),('dark','rgb(17, 27, 33)')]:
                    if mode=='dark': page.locator('.wf-rail [data-theme-toggle]').click()
                    expect(page.locator('html')).to_have_attribute('data-theme', mode)
                    expect(page.locator('.wf-inbox')).to_have_css('background-color', surface)
                    expect(page.locator('#wf-input')).to_have_css('background-color', surface)
                    expect(page.locator('.wf-chat.selected')).to_have_css('background-color', 'rgb(42, 57, 66)' if mode=='dark' else 'rgb(233, 237, 239)')
                    fullscreen()
                    page.screenshot(path=str(artifacts/f'chat-{mode}.png'),full_page=True)
                page.locator('#wf-search').fill('Sales updates')
                expect(page.locator('.wf-chat')).to_have_count(1)
                page.locator('#wf-search').fill('')
                page.locator('#wf-memory').click()
                expect(page.locator('#wf-memory-panel')).to_be_visible()
                page.locator('#wf-memory-panel .close').click()
                page.reload()
                expect(page.locator('.wf-chat')).to_have_count(3)
                expect(page.locator('html')).to_have_attribute('data-theme','dark')
                page.locator('.wf-chat').first.click()
                expect(page.locator('.wf-message')).to_have_count(3)
                # Long history scrolls inside the log; the composer stays visible.
                page.evaluate('''() => {const messages=document.querySelector('#wf-messages');
                    for(let i=0;i<30;i++)messages.append(messages.querySelector('article').cloneNode(true));}''')
                assert page.locator('#wf-log').evaluate('(el)=>el.scrollHeight>el.clientHeight')
                fullscreen()
                for size in [{'width':390,'height':844},{'width':360,'height':500},{'width':844,'height':390}]:
                    page.set_viewport_size(size);fullscreen()
                    assert page.locator('#wf-composer').evaluate('(el)=>el.getBoundingClientRect().bottom<=innerHeight+1')
                    assert page.locator('#wf-log').evaluate('(el)=>el.clientHeight>40')
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('.wf-rail')).to_be_hidden()
                page.locator('#wf-back').click()
                expect(page.locator('.wf-inbox')).to_be_visible()
                expect(page.locator('.wf-conversation')).to_be_hidden()
                expect(page.locator('.wf-rail')).to_be_visible()
                page.locator('.wf-rail [data-theme-toggle]').click()
                expect(page.locator('html')).to_have_attribute('data-theme','light')
                page.screenshot(path=str(artifacts/'inbox-mobile.png'),full_page=True)
                page.locator('.wf-chat').first.click()
                fullscreen()
                page.screenshot(path=str(artifacts/'chat-mobile.png'),full_page=True)
                page.locator('#wf-back').click()
                page.get_by_role('link', name='Back to portal').click()
                expect(page.locator('#page-sales')).to_be_visible()
                expect(page.locator('body')).not_to_have_class(__import__('re').compile('.*workforce-mode.*'))
                # Returning to Workforce keeps the session and full-screen layout.
                page.set_viewport_size({'width':1440,'height':900})
                if not page.locator('nav [data-page=workforce]').is_visible(): page.locator('#sidebar-toggle').click()
                page.locator('nav [data-page=workforce]').click()
                expect(page.locator('.wf-chat')).to_have_count(3)
                fullscreen()
                page.locator('#wf-signout').click()
                expect(page.locator('#login')).to_be_visible()
                assert not errors, errors
                browser.close()
                print('PASS: dedicated route, full viewport, both themes, persistence, search, memory, scrolling, mobile back, portal return, sign out.')
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__': main()

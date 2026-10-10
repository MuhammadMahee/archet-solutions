"""Browser verification of real memory controls and cross-chat recall with a model double."""
from pathlib import Path
import sys,json,logging,os
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import ExitStack
from threading import Thread
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from api import index,portal,workforce
from api.workforce_store import Store
from test_portal import FakeStore


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    fake=FakeStore();artifacts=Path('test-results/workforce');artifacts.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory() as tmp,ExitStack() as stack:
        queue=Store(Path(tmp)/'memory.sqlite3')
        for module in (portal,index):stack.enter_context(patch.object(module,'db',fake.db))
        stack.enter_context(patch.object(portal,'auth',fake.auth));stack.enter_context(patch.object(workforce,'get_store',lambda:queue))
        stack.enter_context(patch.dict(os.environ,WORKFORCE_AI_PROVIDER='groq'))
        class Client:
            def models(self):return ['openai/gpt-oss-120b']
            def local_model(self,*args):pass
            def chat(self,model,system,content,schema=None):
                context=json.loads(content);remember=context['current_request'].startswith('Remember')
                notes=context['memory']['notes']
                return json.dumps(dict(action='remember' if remember else 'reply',message='You prefer concise Dallas updates.' if notes else 'No saved preferences.',start='',end='',dealer='',market='',agent_ids=[],url='',memories=[dict(topic='Reporting preference',evidence='I prefer concise Dallas updates.')] if remember else []))
        stack.enter_context(patch.object(workforce,'ai_client',Client))
        server=make_server('127.0.0.1',0,index.app,threaded=True);Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/ai-workforce');page.locator('#login-username').fill('Mahee');page.locator('#login-password').fill('TestPass123');page.locator('#login-form button[type=submit]').click()
                page.locator('#wf-start').click();page.locator('#wf-new-title').fill('First group');page.locator('#wf-new-form button[type=submit]').click()
                page.locator('#wf-input').fill('Remember: I prefer concise Dallas updates.');page.locator('#wf-input').press('Enter');expect(page.locator('#wf-messages')).to_contain_text("I've saved 1 memory note")
                page.locator('#wf-new').click();page.locator('#wf-new-title').fill('Fresh group');page.locator('#wf-new-form button[type=submit]').click();expect(page.locator('#wf-title')).to_have_text('Fresh group')
                page.locator('#wf-input').fill('How do I like updates?');page.locator('#wf-input').press('Enter');expect(page.locator('#wf-messages')).to_contain_text('You prefer concise Dallas updates.')
                page.locator('#wf-memory').click();expect(page.locator('.wf-memory-note')).to_have_count(1);expect(page.locator('.wf-memory-note')).to_contain_text('Personal')
                page.locator('[data-edit-memory]').click();page.locator('#wf-control-dialog [name=content]').fill('Send a concise update every morning.');page.locator('#wf-control-dialog [name=scope]').select_option('company');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('.wf-memory-note')).to_contain_text('Shared with all employees')
                page.locator('#wf-memory-auto').uncheck();expect(page.locator('#wf-memory-auto')).not_to_be_checked()
                page.locator('#wf-memory-panel').screenshot(path=str(artifacts/'memory-desktop.png'))
                page.locator('#wf-memory-panel .close').click();page.reload();page.locator('#wf-memory').click();expect(page.locator('#wf-memory-auto')).not_to_be_checked();expect(page.locator('.wf-memory-note')).to_contain_text('every morning')
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(artifacts/'memory-mobile.png'));assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('[data-forget-memory]').click();page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('.wf-memory-note')).to_have_count(0)
                page.locator('#wf-memory-panel .close').click();page.locator('.wf-chat').filter(has_text='Fresh group').click();page.locator('#wf-input').fill('What do you remember?');page.locator('#wf-input').press('Enter');expect(page.locator('#wf-messages')).to_contain_text('No saved preferences.')
                assert not errors,errors
                browser.close();print('PASS: remember in chat, new-group recall, memory review/edit/company sharing, opt-out persistence, forget, mobile.')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':main()

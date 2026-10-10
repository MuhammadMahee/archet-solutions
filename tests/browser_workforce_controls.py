"""Real browser controls with isolated users and SQLite; no external AI."""
from pathlib import Path
import sys, logging
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import ExitStack
from threading import Thread
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, workforce
from api.workforce_store import Store
from test_portal import FakeStore


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    fake=FakeStore(); artifacts=Path('test-results/workforce');artifacts.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory() as tmp,ExitStack() as stack:
        queue=Store(Path(tmp)/'chat.sqlite3')
        for module in (portal,index): stack.enter_context(patch.object(module,'db',fake.db))
        stack.enter_context(patch.object(portal,'auth',fake.auth))
        stack.enter_context(patch.object(workforce,'get_store',lambda:queue))
        class Client:
            def models(self):return ['sample']
            def local_model(self,*a):pass
        stack.enter_context(patch.object(workforce,'ai_client',Client))
        server=make_server('127.0.0.1',0,index.app,threaded=True);Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write']);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/ai-workforce')
                page.locator('#login-username').fill('Mahee');page.locator('#login-password').fill('TestPass123');page.locator('#login-form button[type=submit]').click()
                page.locator('#wf-start').click();page.locator('#wf-new-title').fill('Team controls');expect(page.locator('#wf-people option')).to_have_count(2);page.locator('#wf-people').select_option(fake.member['id']);page.locator('#wf-new-form button[type=submit]').click();expect(page.locator('#wf-title')).to_have_text('Team controls')
                page.locator('#wf-invoke').uncheck();page.locator('#wf-input').fill('Hello team https://example.com');page.locator('#wf-input').press('Enter');expect(page.locator('.wf-message')).to_have_count(1)
                def message_menu(label):
                    page.locator('[data-message-options]').first.click();page.get_by_role('menuitem',name=label,exact=True).click()
                def chat_menu(label):
                    page.locator('#wf-chat-menu').click();page.get_by_role('menuitem',name=label,exact=True).click()
                message_menu('Reply');expect(page.locator('.wf-reply-bar')).to_be_visible();page.locator('#wf-input').fill('Reply with context');page.locator('#wf-input').press('Enter');expect(page.locator('.wf-message')).to_have_count(2);expect(page.locator('.wf-quoted')).to_contain_text('Hello team')
                message_menu('React');page.get_by_role('menuitem',name='👍',exact=True).click();expect(page.locator('.wf-message-meta').first).to_contain_text('👍 1')
                message_menu('Star');expect(page.locator('.wf-message-meta').first).to_contain_text('★')
                message_menu('Pin');expect(page.locator('.wf-message-meta').first).to_contain_text('📌')
                chat_menu('Starred messages');expect(page.locator('#wf-control-dialog')).to_contain_text('Hello team');page.locator('#wf-control-dialog .close').click()
                chat_menu('Search');page.locator('#wf-control-dialog textarea').fill('Hello team');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('#wf-control-dialog h2')).to_have_text('Search results');expect(page.locator('#wf-control-dialog')).to_contain_text('Hello team');page.locator('#wf-control-dialog .close').click()
                chat_menu('Group info');expect(page.locator('#wf-group-info')).to_be_visible();page.locator('#wf-group-info').get_by_role('button',name='Edit group name',exact=True).click();page.locator('#wf-control-dialog textarea').fill('Updated group');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('#wf-title')).to_have_text('Updated group')
                page.locator('#wf-group-info').get_by_role('button',name='Add member',exact=True).click();page.locator('#wf-control-dialog select').select_option(fake.admin['id']);page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('#wf-member-list')).to_contain_text('OtherAdmin')
                page.locator('#wf-group-info').get_by_role('button',name='Invite to group via link',exact=True).click();expect(page.get_by_label('Group invite link')).to_have_value(__import__('re').compile(r'.*#invite=.+'));page.locator('#wf-copy-invite').click();expect(page.locator('#wf-copy-invite')).to_have_text('Copied');page.locator('#wf-revoke-invite').click()
                page.locator('#wf-group-info').screenshot(path=str(artifacts/'group-info-controls.png'));page.locator('#wf-group-info .close').click()
                chat_menu('Chat theme');page.locator('#wf-control-dialog select').select_option('forest');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('#wf-active')).to_have_attribute('data-theme','forest')
                chat_menu('Add to Favorites');page.locator('.wf-inbox-filters select').select_option('favorites');expect(page.locator('.wf-chat')).to_have_count(1)
                chat_menu('Archive chat');expect(page.locator('.wf-chat')).to_have_count(0);page.locator('.wf-inbox-filters select').select_option('archived');expect(page.locator('.wf-chat')).to_have_count(1)
                chat_menu('Unarchive chat');page.locator('.wf-inbox-filters select').select_option('all');expect(page.locator('.wf-chat')).to_have_count(1)
                page.reload();page.locator('.wf-chat').click();expect(page.locator('.wf-message-meta').first).to_contain_text('★');expect(page.locator('#wf-active')).to_have_attribute('data-theme','forest')
                page.locator('#wf-chat-menu').click();page.screenshot(path=str(artifacts/'chat-options.png'),full_page=True);page.keyboard.press('Escape')
                message_menu('Delete for me');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('.wf-message')).to_have_count(1);expect(page.locator('.wf-quoted')).to_contain_text('Original message unavailable')
                chat_menu('Clear chat');page.locator('#wf-control-dialog button[type=submit]').click();expect(page.locator('.wf-message')).to_have_count(0)
                cid=queue.list_chats(fake.owner['id'])[0]['id'];assert len(queue.snapshot(cid,fake.member['id'])['messages'])==2
                page.set_viewport_size({'width':390,'height':844});chat_menu('Group info');expect(page.locator('#wf-group-info')).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');page.screenshot(path=str(artifacts/'group-info-mobile.png'),full_page=True)
                assert not errors,errors
                browser.close();print('PASS: menus, reply, reactions, stars, pins, full search, group edits, member add, invite/revoke, themes, favorites/archive, persistence, delete-for-me, clear, mobile.')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':main()

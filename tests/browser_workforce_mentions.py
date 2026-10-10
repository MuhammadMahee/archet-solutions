"""Real browser group bots and mentions; isolated accounts, storage and model."""
from contextlib import ExitStack
import json
import base64
from io import BytesIO
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, workforce, workforce_hosted
from api.workforce_store import Store
from test_portal import FakeStore


class AgentModel:
    def models(self):
        return [workforce_hosted.GROQ_MODEL]
    def local_model(self, model):
        pass
    def describe_images(self, images):
        assert images[0]['mime'] == 'image/png'
        return 'The screenshot shows a green rectangle.'
    def chat(self, model, system, content, schema=None):
        if schema:
            context = json.loads(content)
            if 'image summary' in context['current_request']:
                assert 'green rectangle' in context['uploaded_image_notes']
                return json.dumps(dict(action='summary_image', message='A green rectangle.', agent_ids=[], url='', start='', end='', dealer='', market=''))
            return json.dumps(dict(action='add_agents', message='Add HR.', agent_ids=['ai-hr'],
                                   start='', end='', dealer='', market=''))
        assert 'HR Agent' in system
        return 'Here is an onboarding checklist: introduce the team and agree on first-week goals.'


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    fake = FakeStore()
    artifacts = ROOT / 'test-results/workforce'
    artifacts.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary, ExitStack() as stack:
        queue = Store(Path(temporary) / 'chat.sqlite3')
        stack.enter_context(patch.object(portal, 'db', fake.db))
        stack.enter_context(patch.object(portal, 'auth', fake.auth))
        stack.enter_context(patch.object(index, 'db', fake.db))
        stack.enter_context(patch.object(workforce, 'get_store', lambda: queue))
        stack.enter_context(patch.object(workforce, 'ai_client', AgentModel))
        stack.enter_context(patch.dict(os.environ, WORKFORCE_AI_PROVIDER='groq'))
        server = make_server('127.0.0.1', 0, index.app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(origin + '/ai-workforce')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                page.locator('#wf-start').click()
                page.locator('#wf-new-title').fill('People and planning')
                expect(page.locator('#wf-people option')).to_have_count(2)
                page.locator('#wf-people').select_option(fake.member['id'])
                page.locator('#wf-new-form button[type=submit]').click()
                expect(page.locator('#wf-title')).to_have_text('People and planning')
                page.locator('#wf-directory').click()
                page.locator('[data-add-agent="ai-hr"]').click()
                expect(page.locator('#wf-input')).to_have_value('@manager Add HR Agent to this group.')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(2)
                expect(page.locator('#wf-members')).to_contain_text('@hr')
                page.locator('#wf-input').fill('@h')
                expect(page.get_by_role('option', name='HR Agent @hr')).to_be_visible()
                page.locator('#wf-input').press('Enter')
                expect(page.locator('#wf-input')).to_have_value('@hr ')
                expect(page.locator('.wf-message')).to_have_count(2)
                page.locator('#wf-input').fill('@hr Draft an onboarding checklist.')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(4)
                expect(page.locator('.wf-message').last.locator('.wf-sender')).to_contain_text('HR Agent')
                expect(page.locator('.wf-mention').last).to_have_text('@hr')
                page.reload()
                page.locator('#wf-chats .wf-chat').click()
                expect(page.locator('#wf-members')).to_contain_text('@hr')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.get_by_role('button', name='Mention a teammate', exact=True).click()
                expect(page.locator('#wf-mention-menu')).to_be_visible()
                assert page.get_by_role('option', name='OtherAdmin').count() == 0
                page.screenshot(path=str(artifacts / 'mentions-mobile.png'), full_page=True)
                page.get_by_role('option', name='Member @Member').click()
                expect(page.locator('#wf-input')).to_have_value('@Member ')
                page.locator('#wf-input').fill('@Member Please review <img src=x onerror=alert(1)>')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(5)
                assert page.locator('#wf-messages img').count() == 0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                member_context = browser.new_context()
                member = member_context.new_page()
                member.goto(origin + '/ai-workforce')
                member.locator('#login-username').fill('Member')
                member.locator('#login-password').fill('TestPass123')
                member.locator('#login-form button[type=submit]').click()
                expect(member.locator('.wf-ping')).to_be_visible()
                member.locator('#wf-chats .wf-chat').click()
                expect(member.locator('.wf-message.mentioned')).to_have_count(1)
                expect(member.locator('.wf-message.mentioned .wf-mention')).to_have_text('@Member')
                expect(member.locator('.wf-ping')).to_have_count(0)
                member.locator('#wf-directory').click()
                expect(member.locator('[data-add-agent]')).to_have_count(0)
                image = BytesIO()
                Image.new('RGB', (500, 300), '#309977').save(image, format='PNG')
                page.locator('#wf-invoke').uncheck()
                page.locator('#wf-image-input').set_input_files({'name':'screenshot.png','mimeType':'image/png','buffer':image.getvalue()})
                expect(page.locator('#wf-image-preview img')).to_have_count(1)
                page.get_by_role('button', name='Remove screenshot 1').click()
                expect(page.locator('#wf-image-preview')).to_be_hidden()
                page.locator('#wf-input').evaluate('''(input, data) => {
                    const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
                    const transfer = new DataTransfer();
                    transfer.items.add(new File([bytes], 'pasted.png', {type:'image/png'}));
                    input.dispatchEvent(new ClipboardEvent('paste', {clipboardData:transfer, bubbles:true, cancelable:true}));
                }''', base64.b64encode(image.getvalue()).decode())
                expect(page.locator('#wf-image-preview img')).to_have_count(1)
                page.locator('#wf-send').click()
                expect(page.locator('.wf-message')).to_have_count(6)
                expect(page.locator('.wf-chat-image')).to_have_count(1)
                page.locator('.wf-chat-image').click()
                expect(page.locator('#wf-full-image')).to_be_visible()
                page.wait_for_function("document.getElementById('wf-full-image').naturalWidth === 500")
                page.locator('#wf-image-dialog .close').click()
                page.locator('#wf-invoke').check()
                page.locator('#wf-input').fill('Send an image summary of that screenshot.')
                page.locator('#wf-input').press('Enter')
                expect(page.locator('.wf-message')).to_have_count(8)
                expect(page.locator('.wf-chat-image')).to_have_count(2)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(artifacts / 'images-mobile.png'), full_page=True)
                assert not errors, errors
                member_context.close()
                context.close()
                browser.close()
            print('PASS: group bots, mentions, permissions, mobile, screenshot upload/paste/removal, private image viewer, vision context and bot image reply.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()

"""Browser coverage for mandatory password changes on portal and sheet entry."""
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_portal import FakeStore
from api import index, portal


def main():
    fake = FakeStore()
    for user in fake.tables['portal_users']:
        user['must_change_password'] = True
    server = make_server('127.0.0.1', 0, index.app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal, 'db', fake.db), patch.object(portal, 'auth', fake.auth), patch.object(portal, 'password_write', fake.password_write):
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width': 390, 'height': 844})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(origin + '/internal#users')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#required-password')).to_be_visible()
                expect(page.locator('#workspace')).to_be_hidden()
                page.goto(origin + '/spreadsheet')
                expect(page.locator('#required-password')).to_be_visible()
                page.locator('#required-current').fill('TestPass123')
                page.locator('#required-new').fill('TestPass123')
                page.locator('#required-confirm').fill('TestPass123')
                page.locator('#required-password-form button[type=submit]').click()
                expect(page.locator('#required-password-error')).to_contain_text('different')
                page.locator('#required-new').fill('ChangedPass456')
                page.locator('#required-confirm').fill('ChangedPass456')
                page.locator('#required-password-form button[type=submit]').click()
                expect(page.locator('#login')).to_be_visible()
                expect(page.locator('#login-error')).to_contain_text('Password updated')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('ChangedPass456')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#workspace')).to_be_visible()
                expect(page.locator('#required-password')).to_be_hidden()
                assert not errors, errors
                context.close()
                # Direct sheet login and rest accounts must also reach the reset screen.
                member = next(u for u in fake.tables['portal_users'] if u['username'] == 'Member')
                member['rest_mode'] = True
                context = browser.new_context()
                page = context.new_page()
                page.goto(origin + '/spreadsheet')
                page.locator('#sheet-username').fill('Member')
                page.locator('#sheet-password').fill('TestPass123')
                page.locator('#sheet-login-form button[type=submit]').click()
                expect(page.locator('#required-password')).to_be_visible()
                page.locator('#required-password-logout').click()
                expect(page.locator('#login')).to_be_visible()
                browser.close()
                print('Mandatory reset browser checks passed.')
        finally:
            server.shutdown()


if __name__ == '__main__':
    main()

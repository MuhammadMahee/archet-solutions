"""Rest mode across two live browser sessions, reloads and API access."""
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, sales
from test_portal import FakeStore
from browser_sales import fixture_report


def main():
    fake=FakeStore();server=make_server('127.0.0.1',0,index.app,threaded=True)
    origin=f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal,'db',fake.db),patch.object(portal,'auth',fake.auth),patch.object(sales,'report_data',fixture_report):
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();admin=browser.new_page();member=browser.new_page(viewport={'width':1440,'height':900})
                errors=[]
                for page,user,hash in ((admin,'Mahee','users'),(member,'Member','sales')):
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(origin+'/internal#'+hash)
                    page.locator('#login-username').fill(user);page.locator('#login-password').fill('TestPass123');page.locator('#login-form button[type=submit]').click()
                button=admin.locator('[data-rest-user="'+fake.member['id']+'"]')
                expect(button).to_have_text('Take a Rest')
                expect(admin.locator('[data-rest-user="'+fake.owner['id']+'"]')).to_be_disabled()
                other=browser.new_page();other.goto(origin+'/internal#users')
                other.locator('#login-username').fill('OtherAdmin');other.locator('#login-password').fill('TestPass123');other.locator('#login-form button[type=submit]').click()
                expect(other.locator('#user-list [data-user]').first).to_be_visible()
                expect(other.locator('[data-rest-user]')).to_have_count(0)
                for rest in (True,False):
                    status=other.evaluate('''async ({uid,rest}) => (await fetch('/api/internal/users/'+uid+'/rest',{method:'PATCH',headers:{'Content-Type':'application/json','X-Archet-Request':'1'},body:JSON.stringify({rest_mode:rest})})).status''',{'uid':fake.member['id'],'rest':rest})
                    assert status==403
                other.close()
                expect(member.locator('#sales-count')).to_have_text('72 STORES')
                button.click();expect(button).to_have_text('Back to Work')
                expect(member.locator('#account-rest')).to_be_visible(timeout=10000)
                expect(member.locator('#rest-message')).to_have_text("Now it's time to have Tui wich Lund Member")
                expect(member.locator('#rest-hint')).to_have_text('Reload to fix')
                expect(member.locator('#rest-emoji')).to_have_text('\U0001f595\U0001f3fb')
                expect(member.locator('#workspace')).to_be_hidden()
                assert member.locator('#sales-table tbody tr').count()==0
                assert member.evaluate("fetch('/api/internal/quota').then(r=>r.status)")==403
                member.screenshot(path=str(ROOT/'test-results/rest-desktop.png'))
                member.reload();expect(member.locator('#rest-message')).to_have_text('Chal Bey Dalley')
                expect(member.locator('#rest-hint')).to_have_text('Reload to fix')
                expect(member.locator('#rest-emoji')).to_have_text('\U0001f346')
                for picture in (1,2,3,3):
                    member.reload()
                    expect(member.locator('#rest-image')).to_be_visible()
                    expect(member.locator('#rest-image')).to_have_attribute('src',f'/assets/rest-image-{picture}.png')
                    expect(member.locator('#rest-hint')).to_have_text('Ask Mahee to fix it' if picture==3 else 'Reload to fix')
                    expect(member.locator('#rest-image')).to_have_js_property('complete',True)
                    assert member.locator('#rest-image').evaluate('(image) => image.naturalWidth') > 0
                    expect(member.locator('#rest-emoji')).to_be_hidden()
                    expect(member.locator('#rest-message')).to_be_hidden()
                    expect(member.locator('#workspace')).to_be_hidden()
                with member.expect_response('**/api/internal/me'):
                    member.evaluate("window.dispatchEvent(new Event('focus'))")
                expect(member.locator('#rest-image')).to_have_attribute('src','/assets/rest-image-3.png')
                member.evaluate("location.hash='users';showPage('users')")
                expect(member.locator('#workspace')).to_be_hidden()
                member.set_viewport_size({'width':390,'height':844})
                member.screenshot(path=str(ROOT/'test-results/rest-mobile.png'))
                assert member.evaluate('document.documentElement.scrollWidth<=innerWidth')
                button.click();expect(button).to_have_text('Take a Rest')
                expect(member.locator('#workspace')).to_be_visible(timeout=10000)
                expect(member.locator('#account-rest')).to_be_hidden()
                # A new rest episode shows the initial message even in a reloaded document.
                button.click();expect(member.locator('#rest-emoji')).to_have_text('\U0001f595\U0001f3fb',timeout=10000)
                expect(member.locator('#rest-image')).to_be_hidden()
                expect(member.locator('#rest-hint')).to_have_text('Reload to fix')
                member.locator('#rest-logout').click();expect(member.locator('#login')).to_be_visible()
                member.locator('#login-username').fill('Member');member.locator('#login-password').fill('TestPass123');member.locator('#login-form button[type=submit]').click()
                expect(member.locator('#rest-message')).to_have_text("Now it's time to have Tui wich Lund Member")
                assert not errors,errors
                browser.close()
            print('Rest toggle, existing/new sessions, protected API, reload, restoration and mobile checks passed.')
        finally: server.shutdown()


if __name__=='__main__':main()

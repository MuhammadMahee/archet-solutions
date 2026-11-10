"""Real composer, inbox, approval, and report flow using temporary PostgreSQL tables."""
import base64
import json
import logging
import os
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from pytest import MonkeyPatch
from api import index,portal
from test_portal import FakeStore
from test_cases import case_db,picture


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    os.environ['CASE_TEST_DB']='1'
    fake=FakeStore()
    fake.db('portal_users','PATCH',{'page_access':[]},id='eq.'+fake.member['id'])
    monkeypatch=MonkeyPatch();database=case_db.__wrapped__(monkeypatch,fake);next(database)
    artifacts=ROOT/'test-results';artifacts.mkdir(exist_ok=True)
    server=make_server('127.0.0.1',0,index.app,threaded=True)
    origin=f'http://127.0.0.1:{server.server_port}'
    row={'dealer':'MAGIC','original_dealer':'MAGIC','row_number':2,'store_id':'WB-abcdef0123456789abcdef01',
         'market':'DALLAS','store':'EXAMPLE STORE','carrier':'VAPE SHOP','dm':'Example Manager','state':'TX',
         'dealer_code':'-','door_code':'-','sap_id':'-','address':'-','zip_code':'-','matched':False}
    def tree(route):
        route.fulfill(status=200,content_type='application/json',body=json.dumps({'rows':[row],
            'active':{'filename':'Calling Tree - Nov-26.xlsx','activated_at':'2026-11-09T12:00:00Z'}}))
    with patch.object(portal,'db',fake.db),patch.object(portal,'auth',fake.auth):
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                context=browser.new_context(viewport={'width':1440,'height':1000})
                context.route('**/api/internal/calling-tree',tree)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                def login(page,name,route):
                    page.goto(origin+'/internal#'+route)
                    page.locator('#login-username').fill(name);page.locator('#login-password').fill('TestPass123')
                    page.locator('#login-form button[type=submit]').click()
                    expect(page.locator('#page-'+route)).to_be_visible()
                login(page,'Member','cases')
                expect(page.locator('.nav [data-page="callingtree"]')).to_be_visible()
                expect(page.locator('.nav [data-page="case-report"]')).to_be_hidden()
                page.locator('#page-cases [data-case-compose]').click()
                expect(page.locator('#case-compose-dialog')).to_be_visible()
                page.locator('#case-to').select_option(fake.owner['id'])
                page.locator('#case-cc').select_option(fake.admin['id'])
                page.locator('#case-type').select_option('Custom')
                expect(page.locator('#case-custom')).to_be_visible()
                page.locator('#case-custom').fill('Receipt mismatch')
                page.locator('#case-ntid').fill('example-001')
                page.locator('#case-employee').fill('Example Employee')
                page.locator('#case-subject').fill('Invoice needs a review')
                page.locator('#case-body').fill('Please review the attached picture. <script>unsafe()</script>')
                image=picture()
                page.locator('#case-pictures').set_input_files({'name':image['filename'],'mimeType':'image/png','buffer':base64.b64decode(image['content'])})
                page.screenshot(path=str(artifacts/'cases-compose-desktop.png'),full_page=True)
                page.locator('#case-send').click()
                expect(page.locator('#case-compose-dialog')).not_to_be_visible(timeout=20000)
                expect(page.locator('#case-history')).to_contain_text('Invoice needs a review')
                expect(page.locator('#case-history')).to_contain_text('Pending')
                assert page.locator('#case-history [data-case-review]').count()==0
                page.locator('.nav [data-page="callingtree"]').click()
                expect(page.locator('#tree-table tbody tr')).to_have_count(1)
                assert page.locator('#tree-table thead th').all_text_contents()==['S. No','Carrier','Dealer','DM','Store ID','State','Dealer Code','Door Code','SAP ID','Market','Store Name','Address','ZIP Code']
                expect(page.locator('#tree-table')).not_to_contain_text('WB-')
                expect(page.locator('#tree-table')).not_to_contain_text('RT-POS')
                expect(page.locator('#tree-upload')).to_be_hidden()
                page.screenshot(path=str(artifacts/'calling-tree-columns.png'),full_page=True)
                owner_context=browser.new_context(viewport={'width':1440,'height':1000})
                owner=owner_context.new_page();owner.on('pageerror',lambda e:errors.append(str(e)))
                login(owner,'Mahee','inbox')
                expect(owner.locator('#case-unread')).to_have_text('1')
                expect(owner.locator('#case-inbox')).to_contain_text('Invoice needs a review')
                owner.locator('#case-inbox [data-case-open]').click()
                expect(owner.locator('#case-detail-content')).to_contain_text('<script>unsafe()</script>')
                expect(owner.locator('#case-detail-content img')).to_have_count(1)
                owner.wait_for_function("() => document.querySelector('#case-detail-content img')?.naturalWidth > 0")
                expect(owner.locator('#case-unread')).to_be_hidden()
                owner.screenshot(path=str(artifacts/'cases-detail-desktop.png'),full_page=True)
                owner.locator('[data-close="case-detail-dialog"]').click()
                owner.locator('#case-inbox [data-status="approved"]').click()
                expect(owner.locator('#case-inbox .case-status')).to_have_text('Approved')
                owner.locator('.nav [data-page="case-report"]').click()
                expect(owner.locator('#case-ranking')).to_contain_text('Member')
                expect(owner.locator('#case-report-table')).to_contain_text('EXAMPLE-001')
                assert owner.locator('#case-report-table th').all_text_contents()==['Date','User','Employee NTID','Employee Name','Case Type']
                owner.screenshot(path=str(artifacts/'cases-admin-report.png'),full_page=True)
                cc_context=browser.new_context();cc=cc_context.new_page();login(cc,'OtherAdmin','inbox')
                expect(cc.locator('#case-inbox')).to_contain_text('Invoice needs a review')
                expect(cc.locator('#case-unread')).to_have_text('1')
                page.locator('.nav [data-page="cases"]').click()
                expect(page.locator('#case-history .case-status')).to_have_text('Approved')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(artifacts/'cases-mobile.png'),full_page=True)
                page.locator('#page-cases [data-case-compose]').click()
                expect(page.locator('#case-compose-dialog')).to_be_visible()
                page.screenshot(path=str(artifacts/'cases-compose-mobile.png'),full_page=True)
                assert page.locator('#case-compose-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
                page.locator('[data-close="case-compose-dialog"]').click()
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('#logout').click()
                expect(page.locator('#login')).to_be_visible()
                assert page.locator('#case-history').inner_text()==''
                assert not errors,errors
                browser.close()
                print('Browser checks passed: restricted member, 13 Excel columns, hidden internal IDs, custom case, picture, To/CC Inbox, approval, report, mobile, logout cleanup.')
        finally:
            server.shutdown()
            try:next(database)
            except StopIteration:pass
            monkeypatch.undo()


if __name__=='__main__':main()

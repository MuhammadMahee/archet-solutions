"""Calling Tree UI flow, including a real workbook file input and member visibility."""
from pathlib import Path
import sys,json,base64
from datetime import datetime,timezone
from threading import Thread
from unittest.mock import patch
from io import BytesIO
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from openpyxl import Workbook
from api import index,portal,sales,calling_tree
from test_portal import FakeStore
from browser_sales import fixture_report


def main():
    fake=FakeStore();book=Workbook();sheet=book.active
    sheet.append(['Dealer','Store ID','Market','Store Name','DM'])
    sheet.append(['Connect','S1','Reno','FIRST STORE','Manager'])
    sheet.append(['SPDI-CA','S2','Cali','SECOND STORE','Manager'])
    stream=BytesIO();book.save(stream);payload=stream.getvalue()
    _,rows=calling_tree.parse_workbook(payload)
    rows=calling_tree.describe_rows(rows,{(r['dealer'],r['store_id']):[] for r in rows})
    state={'rows':[],'active':None}
    def route_handler(route):
        req=route.request
        if req.url.endswith('/preview'):
            assert base64.b64decode(req.post_data_json['content'])==payload
            result={'preview_id':'test-preview','filename':'calling-tree.xlsx','worksheet':'Sheet',
                    'rows':rows,'counts':{'Connect':1,'California':1},'unmatched':0}
        elif req.url.endswith('/activate'):
            assert req.post_data_json['preview_id']=='test-preview'
            state.update(rows=rows,active={'filename':'calling-tree.xlsx','activated_at':'2026-09-26T12:00:00Z'})
            result={'message':'Calling Tree updated. Sales Update now uses these stores.'}
        else:result=state
        route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
    server=make_server('127.0.0.1',0,index.app,threaded=True);origin=f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal,'db',fake.db),patch.object(portal,'auth',fake.auth),patch.object(sales,'report_data',fixture_report):
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1440,'height':1000})
                ctx.route('**/api/internal/calling-tree**',route_handler)
                ctx.route('**/api/internal/cases/unread',lambda route:route.fulfill(json={'count':0}))
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.clock.install(time=datetime(2026,11,10,18,29,tzinfo=timezone.utc))
                page.goto(origin+'/internal#callingtree')
                page.locator('#login-username').fill('Mahee');page.locator('#login-password').fill('TestPass123');page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#page-callingtree')).to_be_visible();expect(page.locator('#tree-upload')).to_be_visible()
                page.locator('#tree-file').set_input_files({'name':'calling-tree.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':payload})
                page.locator('#tree-preview-button').click();expect(page.locator('#tree-preview')).to_be_visible()
                expect(page.locator('#tree-table tbody tr')).to_have_count(2)
                expect(page.locator('#tree-table thead th').nth(10)).to_have_text('Market Live Time')
                expect(page.locator('.tree-market-time').first).to_contain_text('PST')
                assert not state['active']
                page.locator('#tree-activate').click();expect(page.locator('#tree-message')).to_contain_text('Calling Tree updated')
                expect(page.locator('#tree-preview')).to_be_hidden();assert state['active']
                # Exercise every active time zone and the unavailable fallback, independently of the viewer's zone.
                clock_rows=[dict(rows[0],market=market,state=st,store_id=str(i)) for i,(market,st) in enumerate([
                    ('RENO','NV'),('UTAH','CA'),('CHICAGO','IL'),('METRO - CLA','OH'),('UNKNOWN','')])]
                state['rows']=calling_tree.describe_rows(clock_rows,{})
                page.evaluate('window.callingTree.load()')
                page.clock.pause_at(datetime(2026,11,10,18,30,tzinfo=timezone.utc))
                clock_cells=page.locator('.tree-market-time')
                expect(clock_cells).to_have_text(['10:30:00 AM PST','11:30:00 AM MST','12:30:00 PM CST','01:30:00 PM EST','Time zone unavailable'])
                page.clock.run_for(1000)
                expect(clock_cells.first).to_have_text('10:30:01 AM PST')
                page.clock.set_system_time(datetime(2026,7,10,18,30,tzinfo=timezone.utc))
                page.clock.run_for(1000)
                expect(clock_cells).to_have_text(['11:30:01 AM PDT','12:30:01 PM MDT','01:30:01 PM CDT','02:30:01 PM EDT','Time zone unavailable'])
                state['rows']=rows
                page.evaluate('window.callingTree.load()')
                page.locator('#tree-search').fill('FIRST');expect(page.locator('#tree-table tbody tr')).to_have_count(1)
                page.locator('#tree-search').fill('');page.locator('#tree-dealer').select_option('California');expect(page.locator('#tree-table tbody tr')).to_have_count(1)
                page.screenshot(path=str(ROOT/'test-results/calling-tree-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(ROOT/'test-results/calling-tree-mobile.png'),full_page=True)
                page.locator('#sidebar-toggle').click()
                page.locator('#logout').click();expect(page.locator('#login')).to_be_visible()
                assert page.locator('#tree-table tbody tr').count()==0
                page.locator('#login-username').fill('Member');page.locator('#login-password').fill('TestPass123');page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#page-callingtree')).to_be_visible();expect(page.locator('#tree-upload')).to_be_hidden()
                expect(page.locator('#tree-table tbody tr')).to_have_count(2)
                assert not errors,errors
                browser.close();print('Calling Tree browser checks passed: live seconds, four time zones, daylight saving, unknown market, upload, preview, activate, filters, mobile, member read-only, logout cleanup.')
        finally:server.shutdown()


if __name__=='__main__':main()

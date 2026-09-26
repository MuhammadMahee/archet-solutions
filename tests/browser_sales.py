"""Browser checks for dealer filters, dates, colors, PNG snapshot and XLSX export."""
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch
from datetime import date
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flask import request
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, sales
from test_portal import FakeStore


def fixture_report(start, end):
    rows=[]
    for dealer in sales.COLORS:
        for n in range(1,13):
            rows.append(sales.ratios({'dealer':dealer,'market':f'{dealer.upper()} {1 if n<7 else 2}',
                'store':f'{dealer.upper()} STORE {n:02}', 'store_id':str(n),'stale':False,
                'new_activation':n%4,'upgrade':n%2,'reactivation':0,'bts':0,'hsi':0,
                'accessory':Decimal(str(n*12.5)),'total_boxes':n%4+n%2,'qpay':n}))
    dealer=request.args.get('dealer','');market=request.args.get('market','');sid=request.args.get('store','')
    if dealer: rows=[r for r in rows if r['dealer']==dealer]
    markets=sorted({r['market'] for r in rows})
    if market: rows=[r for r in rows if r['market']==market]
    stores=[{'id':r['dealer']+':'+r['store_id'],'name':r['store']} for r in rows]
    if sid: rows=[r for r in rows if r['dealer']+':'+r['store_id']==sid]
    return {'rows':rows,'totals':sales.ratios({k:sum(r[k] for r in rows) for k in sales.METRICS}),
            'dealers':[{'name':d,'color':c} for d,c in sales.COLORS.items()],
            'markets':markets,'stores':stores,'start':start.isoformat(),'end':end.isoformat(),
            'today':sales.today().isoformat(),'updated_at':'2026-09-26T17:41:00+00:00',
            'coverage':{'complete':6,'expected':6,'retained':0,'errors':[]}}


def main():
    fake=FakeStore();server=make_server('127.0.0.1',0,index.app,threaded=True)
    origin=f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal,'db',fake.db),patch.object(portal,'auth',fake.auth),patch.object(sales,'report_data',fixture_report):
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                ctx=browser.new_context(viewport={'width':1536,'height':1000},permissions=['clipboard-read','clipboard-write'])
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(origin+'/internal')
                page.locator('#login-username').fill('Mahee');page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#sales-count')).to_have_text('60 STORES')
                expect(page.locator('#sales-table th').first).to_have_text('Dealer')
                backgrounds=[]
                for dealer in sales.COLORS:
                    page.locator('#sales-dealer').select_option(dealer)
                    expect(page.locator('#sales-count')).to_have_text('12 STORES')
                    expect(page.locator('#sales-table tbody tr').first).to_contain_text(dealer.upper()+' STORE')
                    page.wait_for_timeout(300)
                    backgrounds.append(page.evaluate('getComputedStyle(document.body).backgroundColor'))
                assert len(set(backgrounds))==5
                page.locator('#sales-dealer').select_option('California')
                expect(page.locator('#sales-table tbody tr').first).to_contain_text('CALIFORNIA STORE')
                page.screenshot(path=str(ROOT/'test-results/sales-desktop.png'),full_page=True)
                page.locator('#sales-market').select_option('CALIFORNIA 1')
                expect(page.locator('#sales-count')).to_have_text('6 STORES')
                page.locator('#sales-store').select_option('California:1')
                expect(page.locator('#sales-count')).to_have_text('1 STORES')
                with page.expect_download() as download:
                    page.locator('#sales-excel').click()
                download.value.save_as(str(ROOT/'test-results/sales-filtered.xlsx'))
                labels=page.evaluate('''() => {const labels=[];const orig=CanvasRenderingContext2D.prototype.fillText;
                    CanvasRenderingContext2D.prototype.fillText=function(text,...rest){labels.push(text);return orig.call(this,text,...rest)};
                    salesDashboard.snapshot();CanvasRenderingContext2D.prototype.fillText=orig;return labels;}''')
                assert 'DEALER' not in labels and 'MARKET' in labels
                page.locator('#sales-copy').click()
                expect(page.locator('#sales-message')).to_contain_text('Snapshot copied')
                assert page.evaluate("async()=> (await navigator.clipboard.read())[0].types.includes('image/png')")
                page.locator('#sales-period').select_option('month')
                expect(page.locator('#sales-range-badge')).to_contain_text('1,')
                page.locator('#sales-dealer').select_option('ARM')
                expect(page.locator('#sales-count')).to_have_text('12 STORES')
                assert page.locator('#sales-market').input_value()==''
                assert page.locator('#sales-store').input_value()==''
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'test-results/sales-mobile.png'),full_page=True)
                page.locator('#logout').click();expect(page.locator('#login')).to_be_visible()
                assert page.locator('#sales-table tbody tr').count()==0
                assert not errors,errors
                browser.close()
                print('Sales browser checks passed: filters, 5 persistent themes, dates, XLSX, PNG clipboard without Dealer, mobile layout, logout cleanup.')
        finally:server.shutdown()


if __name__=='__main__':main()

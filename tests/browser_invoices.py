"""Real browser invoice editing, privacy, A4 PDF and responsive smoke test."""
from pathlib import Path
import re
import sys
from threading import Thread
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, invoices, sales
from test_portal import FakeStore
from test_invoices import InvoiceStore
from browser_sales import fixture_report


def main():
    fake, ledger = FakeStore(), InvoiceStore()
    artifacts = ROOT / 'test-results'
    artifacts.mkdir(exist_ok=True)
    server = make_server('127.0.0.1', 0, index.app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal,'db',fake.db), patch.object(portal,'auth',fake.auth), patch.object(invoices,'db',ledger.db), patch.object(sales,'report_data',fixture_report):
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width':1440,'height':1050})
                page = context.new_page(); errors = []
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/internal/calling-tree',lambda route:route.fulfill(json={'rows':[{'dealer':'Connect','market':'Dallas'},{'dealer':'ARBF','market':'Houston'}]}))
                page.goto(origin + '/internal#invoices')
                page.locator('#login-username').fill('Mahee'); page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#invoice-fields')).to_be_enabled()
                page.locator('#invoice-month').fill('2026-09')
                expect(page.locator('#invoice-period')).to_contain_text('September 2026')
                expect(page.locator('#invoices-nav')).to_be_visible()
                for dealer,market,amount,advance,remark in [('Connect','Dallas','12500.25','4000.10','September operations. Balance due next month.'),('ARBF','Houston','8750','2500','Advance received on September 12.'),('California','Los Angeles','3200','4000','Credit toward next month.')]:
                    page.locator('#invoice-add').click()
                    tr = page.locator('#invoice-rows tr').last
                    for field,value in [('dealer',dealer),('market',market),('amount',amount),('advance',advance),('remark',remark)]:
                        tr.locator(f'[data-field={field}]').fill(value)
                expect(page.locator('#invoice-total')).to_have_text('$24,450.25')
                expect(page.locator('#invoice-advance')).to_have_text('$10,500.10')
                expect(page.locator('#invoice-balance')).to_have_text('$13,950.15')
                page.locator('#invoice-save').click(); expect(page.locator('#invoice-state')).to_have_text('All changes saved')
                assert len(ledger.records['2026-09']['rows']) == 3
                page.reload(); expect(page.locator('#invoice-rows tr')).to_have_count(3)
                page.evaluate('document.fonts.ready')
                expect(page.locator('.inv-hero-brand img')).to_be_visible()
                assert page.locator('.inv-hero-brand img').evaluate('(img) => img.complete && img.naturalWidth > 0')
                assert page.evaluate("document.fonts.check('600 16px \"Archet Display\"') && document.fonts.check('400 12px \"Archet Inter\"')")
                page.screenshot(path=str(artifacts/'invoices-desktop.png'),full_page=True)
                # Print button must save before opening the browser dialog.
                page.evaluate("window.print = () => { window.printed = true; window.dispatchEvent(new Event('beforeprint')); }")
                page.locator('#invoice-print-button').click()
                page.wait_for_function('window.printed === true')
                expect(page.locator('#invoice-print')).to_contain_text('October 2026')
                expect(page.locator('#invoice-print footer')).to_contain_text('Archet Solutions Private Limited')
                assert page.locator('#invoice-print img').evaluate('(img) => img.complete && img.naturalWidth > 0')
                page.emulate_media(media='print')
                expect(page.locator('#workspace')).to_be_hidden()
                expect(page.locator('#invoice-print')).to_be_visible()
                page.screenshot(path=str(artifacts/'invoices-print.png'),full_page=True)
                pdf = page.pdf(path=str(artifacts/'invoices-a4.pdf'),prefer_css_page_size=True,print_background=True)
                boxes = re.findall(rb'/MediaBox\s*\[([\d.\s]+)\]',pdf)
                assert boxes
                for box in boxes:
                    x,y,width,height = map(float,box.split())
                    assert abs(width-595.28)<1 and abs(height-841.89)<1, box
                assert len(re.findall(rb'/Type /Page\b',pdf)) == 1
                page.emulate_media(media='screen')
                page.evaluate("window.dispatchEvent(new Event('afterprint'))")
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(artifacts/'invoices-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                # Unsafe notes remain literal text in both editor and printed output.
                page.locator('#invoice-rows tr').first.locator('[data-field=remark]').fill('<img src=x onerror=alert(1)>')
                page.locator('#invoice-save').click(); expect(page.locator('#invoice-state')).to_have_text('All changes saved')
                page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                assert page.locator('#invoice-print img').count() == 1
                assert page.locator('#invoice-print img').get_attribute('src') == '/archet-logo.png'
                page.evaluate("window.dispatchEvent(new Event('afterprint'))")
                # Pending changes survive navigation and cancellation of a month switch.
                page.locator('#invoice-rows tr').first.locator('[data-field=amount]').fill('13000')
                page.once('dialog',lambda dialog:dialog.dismiss())
                page.locator('#invoice-month').fill('2026-10')
                expect(page.locator('#invoice-month')).to_have_value('2026-09')
                page.evaluate("showPage('settings')"); page.evaluate("showPage('invoices')")
                expect(page.locator('#invoice-rows tr').first.locator('[data-field=amount]')).to_have_value('13000')
                page.locator('#invoice-save').click(); expect(page.locator('#invoice-state')).to_have_text('All changes saved')
                # A conflicting tab cannot overwrite an invoice; a failed save cannot print.
                ledger.records['2026-09']['revision'] = '00000000-0000-0000-0000-000000000001'
                page.evaluate('window.printed = false')
                page.locator('#invoice-print-button').click()
                expect(page.locator('#invoice-message')).to_contain_text('another tab')
                assert page.evaluate('window.printed') is False
                page.locator('#invoice-reload').click(); expect(page.locator('#invoice-state')).to_have_text('All changes saved')
                # Longer ledgers repeat table headings across multiple A4 pages.
                saved_rows = ledger.records['2026-09']['rows']
                ledger.records['2026-09']['rows'] = [{**saved_rows[0],'market':f'Market {i+1:02}','remark':'Monthly service and advance payment. '*8} for i in range(40)]
                page.locator('#invoice-reload').click(); expect(page.locator('#invoice-rows tr')).to_have_count(40)
                page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                page.emulate_media(media='print')
                expect(page.locator('#workspace')).to_be_hidden()
                expect(page.locator('#invoice-print')).to_be_visible()
                pdf = page.pdf(path=str(artifacts/'invoices-multipage-a4.pdf'),prefer_css_page_size=True,print_background=True)
                assert len(re.findall(rb'/Type /Page\b',pdf)) > 1
                page.emulate_media(media='screen')
                ledger.records['2026-09']['rows'] = saved_rows
                page.set_viewport_size({'width':1440,'height':1050})
                page.locator('#logout').click(); expect(page.locator('#login')).to_be_visible()
                assert page.locator('#invoice-rows tr').count() == 0
                assert page.locator('#invoice-print').inner_text() == ''
                for username in ['OtherAdmin','Member']:
                    page.locator('#login-username').fill(username); page.locator('#login-password').fill('TestPass123')
                    page.locator('#login-form button[type=submit]').click()
                    expect(page.locator('#workspace')).to_be_visible()
                    expect(page.locator('#invoices-nav')).to_be_hidden()
                    page.evaluate("showPage('invoices')")
                    expect(page.locator('#page-invoices')).to_be_hidden()
                    status = page.evaluate("async () => (await fetch('/api/internal/invoices/2026-09')).status")
                    assert status == 403
                    page.locator('#logout').click(); expect(page.locator('#login')).to_be_visible()
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
    print('Invoice browser checks passed. Desktop, mobile and A4 artifacts saved to test-results.')


if __name__ == '__main__':
    main()

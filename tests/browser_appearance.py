"""Dealer colors and persisted appearance across report pages and mobile."""
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, sales, quota
from test_portal import FakeStore
from browser_sales import fixture_report
from browser_quota import fixture_report as quota_report


def main():
    fake = FakeStore()
    server = make_server('127.0.0.1', 0, index.app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal, 'db', fake.db), patch.object(portal, 'auth', fake.auth), \
         patch.object(sales, 'report_data', fixture_report), patch.object(quota, 'report_data', quota_report):
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport={'width':1440,'height':1000})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.route('**/api/internal/calling-tree', lambda r: r.fulfill(json={
                    'rows':[dict(dealer=d, store_id=d, store=d+' STORE', market='CHICAGO', matched=True)
                            for d in sales.COLORS],
                    'active':{'filename':'Fixture.xlsx','activated_at':'2026-11-01T12:00:00Z'}}))
                page.goto(origin+'/internal')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#sales-count')).to_have_text('60 STORES')
                palette = lambda: page.evaluate("""() => ['body','.sidebar','.sales-hero'].map(s=>{
                    const css=getComputedStyle(document.querySelector(s));return css.backgroundColor+css.backgroundImage;
                })""")
                for mode in ('light','dark'):
                    if mode == 'dark': page.locator('.topbar [data-theme-toggle]').click()
                    expect(page.locator('html')).to_have_attribute('data-theme', mode)
                    colors=[]
                    for dealer in sales.COLORS:
                        page.locator('#sales-dealer').select_option(dealer)
                        expect(page.locator('#sales-count')).to_have_text('12 STORES')
                        expect(page.locator('html')).to_have_attribute('data-dealer', dealer)
                        colors.append(palette())
                    assert all(len({c[i] for c in colors}) == 5 for i in range(3)), colors
                    page.screenshot(path=str(ROOT/f'test-results/appearance-{mode}.png'), full_page=True)
                page.reload()
                expect(page.locator('#sales-count')).to_have_text('60 STORES')
                expect(page.locator('html')).to_have_attribute('data-theme','dark')
                expect(page.locator('#page-sales .sales-filters')).to_have_css('background-color','rgb(20, 34, 53)')
                page.locator('#sales-dealer-trigger').click()
                expect(page.locator('#sales-dealer-menu')).to_have_css('background-color','rgb(20, 34, 53)')
                page.get_by_role('combobox',name='Search dealer').press('Escape')
                for name, select in [('quota','quota-dealer'),('callingtree','tree-dealer')]:
                    page.locator(f'nav [data-page={name}]').click()
                    expect(page.locator('#'+select+' option[value=California]')).to_be_attached()
                    page.locator('#'+select).select_option('California')
                    expect(page.locator('html')).to_have_attribute('data-dealer','California')
                    expect(page.locator('.sidebar')).to_have_css('background-color','rgb(73, 28, 44)')
                page.locator('nav [data-page=settings]').click()
                expect(page.locator('#page-settings')).to_be_visible()
                expect(page.locator('#page-settings .card')).to_have_css('background-color','rgb(20, 34, 53)')
                page.set_viewport_size({'width':390,'height':844})
                toggle = page.locator('.topbar [data-theme-toggle]')
                expect(toggle).to_be_visible()
                toggle.click()
                expect(page.locator('html')).to_have_attribute('data-theme','light')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                toggle.click()
                page.screenshot(path=str(ROOT/'test-results/appearance-mobile.png'),full_page=True)
                assert not errors, errors
                browser.close()
                print('Appearance passed: five visible dealer palettes in both modes, persistence, dropdowns, report navigation, settings, mobile.')
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__': main()

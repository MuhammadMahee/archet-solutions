"""Browser checks against isolated source and review fixtures; no production writes."""
import base64
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flask import request
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from api import index, portal, store_hours as sh
from test_portal import FakeStore
from test_store_hours import sample_rows


def main():
    fake = FakeStore()
    saved = {}
    def fixture(start, end):
        rows = sample_rows()
        rows += sh.build_rows([dict(dealer='AMQ', store_id='N1329B', market='CHICAGO', store='GLENVIEW')],
                              [], [], [], start, end)
        # Include a fully reviewed row to verify all screenshot colors.
        rows[0].update(closing_time='20:00:00', camera_out='19:58:00', closing_status='Early')
        for row in rows:
            row.update(saved.get((row['dealer'], row['store_id'], row['date']), {}))
        dealer, market = request.args.get('dealer'), request.args.get('market')
        if dealer: rows = [r for r in rows if r['dealer'] == dealer]
        markets = sorted({r['market'] for r in rows})
        if market: rows = [r for r in rows if r['market'] == market]
        stores = [dict(id=r['dealer']+':'+r['store_id'], name=r['store']) for r in rows]
        if request.args.get('store'): rows = [r for r in rows if r['dealer']+':'+r['store_id'] == request.args['store']]
        return dict(rows=rows, start=start.isoformat(), end=end.isoformat(), today='2026-10-20', earliest='2026-10-01',
                    dealers=list(sh.COLORS), markets=markets, stores=stores, updated_at=None, coverage={'complete': 2, 'expected': 2, 'errors': []})
    def save(payload, user_id):
        row = deepcopy(payload)
        row.update(sh.evaluate(row))
        row['revision'] += 1
        saved[(row['dealer'], row['store_id'], row['date'])] = row
        return row['revision']
    server = make_server('127.0.0.1', 0, index.app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    with patch.object(portal, 'db', fake.db), patch.object(portal, 'auth', fake.auth), patch.object(sh, 'report_data', fixture), patch.object(sh, 'save_review', save), patch.object(sh, 'today', lambda: date(2026, 10, 20)), patch.object(sh, 'run_sync', lambda *args: dict(status='complete', remaining=0, pending=0, workers=[])):
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                ctx = browser.new_context(viewport={'width': 1600, 'height': 1050}, permissions=['clipboard-read', 'clipboard-write'])
                page = ctx.new_page()
                page.clock.install(time=datetime(2026, 10, 20, 17, tzinfo=timezone.utc))
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(origin+'/internal#storehours')
                page.locator('#login-username').fill('Mahee')
                page.locator('#login-password').fill('TestPass123')
                page.locator('#login-form button[type=submit]').click()
                expect(page.locator('#sh-total')).to_have_text('4')
                expect(page.locator('#sh-copy')).to_be_hidden()
                expect(page.locator('#sh-pending')).to_have_text('3')
                page.locator('#sh-dealer').select_option('Connect')
                expect(page.locator('#sh-total')).to_have_text('2')
                row = page.locator('#sh-table tbody tr').nth(1)
                row.locator('[data-column=camera_in] input').fill('10:07:00')
                expect(row.locator('[data-column=opening_status]')).to_have_text('Schedule required')
                row.locator('[data-column=opening_time] input').fill('10:00:00')
                expect(row.locator('[data-column=chargeback]')).to_have_text('-$10')
                row.locator('button').click()
                expect(page.locator('#sh-message')).to_contain_text('Camera review saved')
                expect(page.locator('#sh-chargebacks')).to_have_text('−$20')
                page.screenshot(path=str(ROOT/'test-results/store-hours-form.png'), full_page=True)
                page.locator('#sh-switch').click()
                expect(page.locator('#page-storehoursreport')).to_be_visible()
                expect(page.locator('#sh-copy')).to_be_visible()
                assert page.locator('#sh-table input').count() == 0
                page.locator('#sh-copy').click()
                expect(page.locator('#sh-message')).to_contain_text('Snapshot copied')
                assert page.evaluate("async () => (await navigator.clipboard.read())[0].types.includes('image/png')")
                with page.expect_download() as download:
                    page.locator('#sh-excel').click()
                download.value.save_as(str(ROOT/'test-results/store-hours.xlsx'))
                image = page.evaluate('() => storeHoursDashboard.snapshot().toDataURL().split(",")[1]')
                (ROOT/'test-results/store-hours-snapshot.png').write_bytes(base64.b64decode(image))
                page.screenshot(path=str(ROOT/'test-results/store-hours-report.png'), full_page=True)
                page.locator('#sh-date').click()
                expect(page.locator('#sh-date-dialog')).to_be_visible()
                page.screenshot(path=str(ROOT/'test-results/store-hours-dates.png'), full_page=True)
                page.locator('#sh-custom-trigger').click()
                page.get_by_role('button', name='Oct 1, 2026', exact=True).click()
                page.get_by_role('button', name='Oct 20, 2026', exact=True).click()
                page.screenshot(path=str(ROOT/'test-results/store-hours-calendar.png'), full_page=True)
                page.locator('#sh-date-apply').click()
                expect(page.locator('#sh-date')).to_contain_text('Oct 1, 2026')
                expect(page.locator('#sh-total')).to_have_text('2')
                page.locator('#sh-sync').click()
                expect(page.locator('#sh-message')).to_contain_text('including the last extracted date')
                page.locator('#sh-dealer').select_option('AMQ')
                expect(page.locator('#sh-total')).to_have_text('20')
                saturday = page.locator('#sh-table tbody tr').filter(has_text='Oct 17, 2026')
                sunday = page.locator('#sh-table tbody tr').filter(has_text='Oct 18, 2026')
                expect(saturday.locator('[data-column=closing_time]')).to_have_text('6:00:00 PM')
                expect(sunday.locator('[data-column=opening_time]')).to_have_text('12:00:00 PM')
                expect(sunday.locator('[data-column=opening_status]')).to_have_text('Pending camera review')
                page.locator('#sh-switch').click()
                expect(page.locator('#sh-note')).to_contain_text('Monday–Friday, Saturday, or Sunday')
                sunday = page.locator('#sh-table tbody tr').filter(has_text='Oct 18, 2026')
                expect(sunday.locator('[data-column=opening_time] input')).to_have_value('12:00:00')
                expect(sunday.locator('[data-column=closing_time] input')).to_have_attribute('title', 'Sunday workbook hours: 6:00:00 PM. Clear and save to restore this time.')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path=str(ROOT/'test-results/store-hours-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('#sh-date').click()
                expect(page.locator('#sh-date-dialog')).to_be_visible()
                page.keyboard.press('Escape')
                assert not errors, errors
                print('Browser checks passed: editing, pending/charges, report navigation, filters, calendar, clipboard PNG, XLSX, sync, mobile layout.')
                browser.close()
        finally:
            server.shutdown()


if __name__ == '__main__':
    main()

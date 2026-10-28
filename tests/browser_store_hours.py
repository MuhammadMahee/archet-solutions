"""Browser checks against isolated source and review fixtures; no production writes."""
import base64
import json
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
from api import store_hours_sheet as sheet
from test_portal import FakeStore
from test_store_hours import sample_rows
from test_store_hours_directory import workbook
from api.store_hours_directory import parse_schedule_workbook, map_schedule_rows
from api.portal import PortalError


def main(grid_check=None, spreadsheet=False):
    fake = FakeStore()
    saved = {}
    versions = []
    manual = []
    uploaded = []
    preview_rows = []
    sheet_config = {'columns':[], 'revision':0}
    def column_change(payload,user_id):
        if payload['action']=='add':
            sheet_config['columns'].append(dict(id='custom_'+str(len(sheet_config['columns'])+1),name=payload['name'],format=payload.get('format','text')))
        else:
            column=next(c for c in sheet_config['columns'] if c['id']==payload['id'])
            if payload['action']=='delete': column['deleted']=True
            else: column['name']=payload['name']
        sheet_config['revision']+=1
        versions.append(dict(id=str(len(versions)+1),transaction_id='1',recorded_at='2026-10-23T12:00:00+00:00',kind='sheet',operation='UPDATE',dealer='*',store_id='__sheet__',store='Shared spreadsheet',market='',report_date=None,employee='',actor_name='Mahee',before_data={'columns':[]},after_data=deepcopy(sheet_config)))
        return deepcopy(sheet_config)
    directory = [dict(dealer=r['dealer'],store_id=r['store_id'],market=r['market'],store=r['store']) for r in sample_rows()]
    directory = list({(s['dealer'],s['store_id']):s for s in directory}.values())
    directory += [dict(dealer='AMQ',store_id='N1329B',market='CHICAGO',store='GLENVIEW'),
                  dict(dealer='The Fix',store_id='WB-PRIME',market='CHICAGO',store='PRIME',source_id=None),
                  dict(dealer='Smoke Magic',store_id='WB-MAGIC',market='DALLAS',store='MAGIC 1',source_id=None)]
    def row_key(row): return row['dealer'],row['store_id'],row.get('source_date',row['date']),row.get('employee_key','')
    initial_revisions={row_key(row):row['revision'] for row in sample_rows()}
    def fixture(start, end):
        rows = sample_rows()
        rows += sh.build_rows(directory[3:], [], [], [], start, end, manual)
        # Include a fully reviewed row to verify all screenshot colors.
        rows[0].update(closing_time='20:00:00', camera_out='19:58:00', closing_status='Early')
        for row in rows:
            row.update(saved.get(row_key(row), {}))
        dealer, market = request.args.get('dealer'), request.args.get('market')
        if dealer: rows = [r for r in rows if r['dealer'] == dealer]
        markets = sorted({r['market'] for r in rows})
        if market: rows = [r for r in rows if r['market'] == market]
        stores = list({r['dealer']+':'+r['store_id']:dict(id=r['dealer']+':'+r['store_id'],name=r['store']) for r in rows}.values())
        if request.args.get('store'): rows = [r for r in rows if r['dealer']+':'+r['store_id'] == request.args['store']]
        return dict(rows=[r for r in rows if not r.get('removed')], removed_rows=[r for r in rows if r.get('removed')], start=start.isoformat(), end=end.isoformat(), today='2026-10-20', earliest='2026-10-01',
                    dealers=sorted({s['dealer'] for s in directory}), directory=directory, manual_store_count=2, markets=markets, stores=stores, updated_at=None, coverage={'complete': 2, 'expected': 2, 'errors': []})
    def save(payload, user_id, include_row=False):
        if payload['revision']!=saved.get(row_key(payload),{}).get('revision',initial_revisions.get(row_key(payload),0)):
            raise PortalError('Someone updated this review.',409)
        row = deepcopy(payload)
        row.update(sh.evaluate(row))
        row.update(row.get('cell_overrides', {}))
        row['revision'] += 1
        versions.append(dict(id=str(len(versions)+1),transaction_id='1',recorded_at='2026-10-23T12:00:00+00:00',kind='review',operation='UPDATE',dealer=row['dealer'],store_id=row['store_id'],store='STORE ONE',market='HOUSTON',report_date=row['date'],employee='Closing Employee',actor_name='Mahee (@Mahee)',before_data=saved.get(row_key(row),dict(camera_in=None,camera_out=None,opening_time=None,closing_time=None,revision=0)),after_data=deepcopy(row)))
        saved[row_key(row)] = row
        return {'revision':row['revision'],'row':deepcopy(row)} if include_row else row['revision']
    def add_employee(payload,user_id):
        key=sh.employee_key(payload['employee'])
        if any(m['dealer']==payload['dealer'] and m['store_id']==payload['store_id'] and m['report_date'].isoformat()==payload['date'] and m['employee_key']==key for m in manual):
            raise PortalError('This employee already has a row for this store and date.',409)
        manual.append(dict(dealer=payload['dealer'],store_id=payload['store_id'],report_date=date.fromisoformat(payload['date']),employee_key=key,employee=payload['employee']))
        return key
    def change_rows(payload,user_id):
        available=fixture(date(2026,10,20),date(2026,10,20))
        for entry in payload['rows']:
            row=next(r for r in available['rows']+available['removed_rows'] if row_key(r)==row_key(entry))
            if row['revision']!=entry['revision']:raise PortalError('Row changed',409)
            row={**row,'removed':payload['action']=='remove'}
            save(row,user_id)
        return len(payload['rows'])
    def preview(payload,user_id):
        preview_rows[:] = map_schedule_rows(parse_schedule_workbook(base64.b64decode(payload['content'])),directory)
        return dict(preview_id='test-preview',rows=preview_rows,added=1,updated=0,corrected=sum(bool(r.get('corrected_connect_opening')) for r in preview_rows))
    def apply_upload(payload,user_id):
        directory.extend(preview_rows)
        return len(preview_rows)
    def history(start,end):
        before=int(request.args.get('before') or len(versions)+1)
        rows=[v for v in reversed(versions) if int(v['id'])<before]
        return dict(versions=rows[:2],next_cursor=rows[1]['id'] if len(rows)>2 else None,tracking_started='2026-10-23T00:00:00+00:00')
    server = make_server('127.0.0.1', 0, index.app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    from contextlib import nullcontext
    with patch.object(portal, 'db', fake.db), patch.object(portal, 'auth', fake.auth), patch.object(sh, 'report_data', fixture), patch.object(sh, 'save_review', save), patch.object(sh, 'today', lambda: date(2026, 10, 20)), patch.object(sh, 'run_sync', lambda *args: dict(status='complete', remaining=0, pending=0, workers=[])), patch.object(sh,'add_manual_employee',add_employee), patch.object(sh,'set_rows_removed',change_rows), patch.object(sh,'preview_schedule_upload',preview), patch.object(sh,'apply_schedule_upload',apply_upload), patch.object(sh,'version_history',history), patch.object(sheet,'live_revision',lambda:str(len(versions))), patch.object(sheet,'settings',lambda *args:deepcopy(sheet_config)), patch.object(sheet,'change_column',column_change), patch.object(sh,'connect',lambda:nullcontext(None)):
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                ctx = browser.new_context(viewport={'width': 1600, 'height': 1050}, permissions=['clipboard-read', 'clipboard-write'])
                page = ctx.new_page()
                page.clock.set_fixed_time(datetime(2026, 10, 20, 17, tzinfo=timezone.utc))
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(origin+('/spreadsheet' if spreadsheet else '/internal#storehours'))
                page.locator('#sheet-username' if spreadsheet else '#login-username').fill('Mahee')
                page.locator('#sheet-password' if spreadsheet else '#login-password').fill('TestPass123')
                page.locator('#sheet-login-form button[type=submit]' if spreadsheet else '#login-form button[type=submit]').click()
                if spreadsheet: expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
                else: expect(page.locator('#sh-total')).to_have_text('7')
                if grid_check:
                    grid_check(page)
                    assert not errors, errors
                    browser.close()
                    return
                expect(page.locator('#sh-copy')).to_be_hidden()
                expect(page.locator('#sh-pending')).to_have_text('6')
                page.locator('#sh-dealer-trigger').click()
                assert page.evaluate("() => Math.abs(document.querySelector('#sh-dealer-trigger').getBoundingClientRect().left-document.querySelector('.sh-picker-menu:not([hidden])').getBoundingClientRect().left)<2")
                page.screenshot(path=str(ROOT/'test-results/store-hours-dropdown.png'))
                page.get_by_role('combobox',name='Search dealer').fill('connect')
                page.get_by_role('combobox',name='Search dealer').press('Enter')
                expect(page.locator('#sh-total')).to_have_text('3')
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
                expect(page.locator('#sh-total')).to_have_text('3')
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
                page.locator('#sh-dealer').select_option('The Fix')
                expect(page.locator('#sh-total')).to_have_text('20')
                page.locator('#sh-add').click()
                expect(page.locator('#sh-employee-dialog')).to_be_visible()
                page.locator('#sh-employee-store-trigger').click()
                page.get_by_role('combobox',name='Search store',exact=True).fill('PRIME')
                page.get_by_role('combobox',name='Search store',exact=True).press('Enter')
                page.locator('#sh-employee-name').fill('Manual Employee')
                page.locator('#sh-employee-date').fill('2026-10-20')
                page.locator('#sh-employee-submit').click()
                expect(page.locator('#sh-message')).to_contain_text('Employee added')
                expect(page.locator('#sh-total')).to_have_text('1')
                expect(page.locator('#sh-table tbody')).to_contain_text('Manual Employee')
                expect(page.locator('#sh-table tbody')).to_contain_text('No Clock In')
                page.locator('#sh-add').click()
                page.locator('#sh-employee-name').fill('Manual Employee')
                page.locator('#sh-employee-submit').click()
                expect(page.locator('#sh-employee-error')).to_contain_text('already has a row')
                page.locator('#sh-employee-cancel').click()
                page.locator('#sh-manage').click()
                page.locator('#sh-file').set_input_files(dict(name='new-stores.xlsx',mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer=workbook(company='NEW WIRELESS',store='FUTURE STORE')))
                expect(page.locator('#sh-upload-count')).to_contain_text('1 new store')
                expect(page.locator('#sh-upload-table')).to_contain_text('FUTURE STORE')
                page.screenshot(path=str(ROOT/'test-results/store-hours-upload.png'),full_page=True)
                page.locator('#sh-upload-apply').click()
                expect(page.locator('#sh-message')).to_contain_text('Workbook applied')
                page.locator('#sh-upload-close').click()
                page.locator('#sh-dealer-trigger').click()
                page.get_by_role('combobox',name='Search dealer').fill('New Wireless')
                page.get_by_role('combobox',name='Search dealer').press('Enter')
                expect(page.locator('#sh-table tbody')).to_contain_text('FUTURE STORE')
                expect(page.locator('#sh-table [data-column=opening_time] input')).to_have_value('10:00:00')
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

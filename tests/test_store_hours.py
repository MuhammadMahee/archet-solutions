from contextlib import nullcontext
import csv
from datetime import date, datetime, time
from io import BytesIO, StringIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from api import store_hours as sh
from api.sales import ReportError
from test_portal import store, client, login, write


DAY = date(2026, 10, 20)


def report_csv(rows):
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(['marketid', 'custno', 'company', 'username', 'name', 'lastname', 'clockintime', 'clockouttime'])
    writer.writerows(rows)
    return out.getvalue().encode()


def test_real_csv_layout_both_datetime_formats_and_duplicate_updates():
    rows = sh.read_report(report_csv([
        ['HOUSTON', '1', 'STORE', 'user', 'First', 'Last', '10/20/2026  9:02:00 AM', ''],
        ['HOUSTON', '1', 'STORE', 'user', 'First', 'Last', '10/20/2026 09:02:00', '10/20/2026 20:00:00'],
    ]))
    assert len(rows) == 1
    assert rows[0]['report_date'] == DAY
    assert rows[0]['employee'] == 'First Last'
    assert rows[0]['clock_out'] == datetime(2026, 10, 20, 20)


@pytest.mark.parametrize('data,code', [
    (b'<html>login</html>', 'invalid_report_or_expired_cookies'),
    (b'company,clockintime\n', 'report_columns_changed'),
    (report_csv([['HOUSTON', '1', 'STORE', 'u', 'A', 'B', '', '']]), 'missing_clockin_date'),
    (report_csv([['HOUSTON', '1', 'STORE', 'u', 'A', 'B', 'garbage', '']]), 'invalid_punch_date'),
])
def test_failed_exports_cannot_replace_saved_rows(data, code):
    with pytest.raises(ReportError, match=code):
        sh.read_report(data)


def test_valid_empty_export():
    assert sh.read_report(report_csv([])) == []


@pytest.mark.parametrize('market,camera,charge', [
    ('HOUSTON', '10:04:59', 0), ('HOUSTON', '10:05:00', -10),
    ('RENO', '10:04:59', 0), ('RENO', '10:05:00', -10),
    ('DALLAS', '10:09:59', 0), ('DALLAS', '10:10:00', -10),
    ('OTHER', '10:30:00', 0),
])
def test_chargeback_boundaries(market, camera, charge):
    result = sh.evaluate(dict(dealer='Connect', market=market, opening_time='10:00:00', camera_in=camera))
    assert result['chargeback'] == charge


def test_other_dealers_never_charged_and_no_camera_never_uses_rt():
    row = dict(dealer='ARM', market='HOUSTON', opening_time='10:00:00', camera_in='10:30:00')
    assert sh.evaluate(row)['chargeback'] == 0
    row.update(camera_in=None, rt_clockin='2026-10-20T10:45:00')
    assert sh.evaluate(row)['opening_status'] == 'Pending camera review'
    assert sh.evaluate(row)['chargeback'] is None
    row.update(camera_in='10:10:00', opening_time=None)
    assert sh.evaluate(row)['opening_status'] == 'Schedule required'
    assert sh.evaluate(row)['chargeback'] is None


@pytest.mark.parametrize('camera,status', [('10:00:59', 'On Time'), ('10:01:00', 'Late'), ('09:59:00', 'On Time')])
def test_late_marking(camera, status):
    assert sh.evaluate(dict(dealer='Connect', market='RENO', opening_time='10:00:00', camera_in=camera))['opening_status'] == status


@pytest.mark.parametrize('camera,status', [('19:59:01', 'On Time'), ('19:59:00', 'Early'), ('20:01:00', 'On Time')])
def test_early_marking(camera, status):
    assert sh.evaluate(dict(dealer='Connect', market='RENO', closing_time='20:00:00', camera_out=camera))['closing_status'] == status


def test_overnight_schedule():
    row = dict(dealer='Connect', market='RENO', opening_time='18:00:00', closing_time='02:00:00', camera_out='01:59:00')
    assert sh.evaluate(row)['closing_status'] == 'Early'
    row['camera_out'] = '02:00:00'
    assert sh.evaluate(row)['closing_status'] == 'On Time'


def sample_rows():
    roster = [dict(dealer='Connect', market='HOUSTON', store='STORE ONE', store_id='1'),
              dict(dealer='Connect', market='HOUSTON', store='NO PUNCHES', store_id='2'),
              dict(dealer='ARM', market='DALLAS', store='OTHER DEALER', store_id='1')]
    punches = sh.read_report(report_csv([
        ['HOUSTON', '1', 'STORE ONE', 'u1', 'Opening', 'Employee', '10/20/2026 10:02:00', '10/20/2026 14:00:00'],
        ['HOUSTON', '1', 'STORE ONE', 'u2', 'Closing', 'Employee', '10/20/2026 14:00:00', '10/20/2026 20:00:00'],
    ]))
    for row in punches:
        row['source_id'] = 'connect'
    review = dict(dealer='Connect', store_id='1', report_date=DAY, camera_in=time(10, 5), opening_time=time(10), revision=1)
    return sh.build_rows(roster, punches, [review], [], DAY, DAY)


def test_roster_includes_missing_stores_keeps_dealers_separate_and_multiple_shifts():
    rows = sample_rows()
    assert len(rows) == 4
    assert rows[0]['employee'] == 'Opening Employee'
    assert rows[0]['rt_clockout'] == '2026-10-20T14:00:00'
    assert rows[0]['chargeback'] == -10
    assert rows[1]['employee'] == 'Closing Employee'
    assert rows[1]['rt_clockout'] == '2026-10-20T20:00:00'
    assert rows[1]['opening_status'] == 'Pending camera review'
    for row in rows[2:]:
        assert row['employee'] == '-'
        assert row['rt_clockin'] is row['rt_clockout'] is None
        assert sh.display_value('rt_clockin', row['rt_clockin']) == 'No Clock In'
        assert sh.display_value('rt_clockout', row['rt_clockout']) == 'No Clock Out'


def test_last_extracted_day_is_inclusive_even_across_month_boundary():
    assert sh.sync_start(date(2026, 9, 30), DAY, DAY) == date(2026, 9, 30)
    assert sh.sync_start(None, DAY, DAY) == DAY
    assert sh.sync_start(None, None, DAY) == date(2026, 10, 1)


def test_fetch_payload_and_older_open_shift_carryovers(monkeypatch):
    from urllib.parse import parse_qs
    def read(opener, req, limit, **kwargs):
        assert req.full_url == sh.REPORT_URL
        payload = parse_qs(req.data.decode(), keep_blank_values=True)
        assert payload['frmStart'] == ['10/19/2026'] and payload['frmEnd'] == ['10/20/2026']
        assert payload['btnExcel'] == ['click'] and payload['frmStore'] == ['']
        return report_csv([['HOUSTON', '1', 'STORE', 'u', 'A', 'B', '10/18/2026 10:00:00', ''],
                           ['HOUSTON', '1', 'STORE', 'u', 'A', 'B', '10/20/2026 10:00:00', '']])
    monkeypatch.setattr(sh, 'read_source', read)
    rows = sh.fetch_report(None, date(2026, 10, 19), DAY)
    assert len(rows) == 1 and rows[0]['report_date'] == DAY


def test_excel_columns_missing_values_colors_and_formula_safety():
    rows = sample_rows()
    rows[0]['employee'] = '=HYPERLINK("bad")'
    book = load_workbook(sh.excel_report(dict(rows=rows, start=DAY.isoformat(), end=DAY.isoformat(), updated_at=None, coverage={'complete': 0, 'expected': 2})))
    sheet = book.active
    assert [c.value for c in sheet[2]] == [heading for _, heading in sh.COLUMNS]
    assert sheet['D3'].data_type == 's'
    assert sheet['N3'].value == -10
    assert sheet['I3'].fill.fgColor.rgb.endswith('FFC7CE')
    assert sheet['H5'].value == 'No Clock In' and sheet['L5'].value == 'No Clock Out'
    assert sheet['N5'].value == 'Pending'


def test_endpoints_auth_and_sync_admin_only(client, monkeypatch):
    for path in ('store-hours', 'store-hours/export'):
        assert client.get('/api/internal/'+path).status_code == 401
    login(client, 'Member')
    assert write(client, 'store-hours/refresh', {}).status_code == 403
    monkeypatch.setattr(sh, 'report_data', lambda *args: {'rows': []})
    assert client.get('/api/internal/store-hours').status_code == 200
    monkeypatch.setattr(sh, 'save_review', lambda p, user_id: 2)
    assert write(client, 'store-hours/review', {}).json['revision'] == 2


@pytest.mark.parametrize('changes', [dict(date='bad'), dict(date='2999-01-01'), dict(camera_in='25:00'), dict(revision=-1), dict(camera_in='10:00+03:00')])
def test_invalid_review_input_rejected_before_database(changes):
    from api.portal import PortalError
    with pytest.raises(PortalError):
        sh.save_review({**dict(dealer='Connect', store_id='1', date=DAY.isoformat(), revision=0), **changes}, 'user')


def test_save_refresh_does_not_touch_camera_reviews():
    statements = []
    class DB:
        def transaction(self): return nullcontext()
        def execute(self, sql, params): statements.append((sql, params))
        def cursor(self): return nullcontext(self)
        def executemany(self, sql, params): statements.append((sql, params))
    sh.save_punches(DB(), 'connect', DAY, DAY, [])
    assert 'delete from public.store_time_punches' in statements[0][0]
    assert all('store_hours_reviews' not in sql for sql, _ in statements)
    assert statements[1][1] == [(0, 'connect', DAY)]

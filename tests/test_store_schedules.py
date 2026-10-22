from datetime import date, time
from contextlib import nullcontext
from types import SimpleNamespace
import json
from pathlib import Path

from openpyxl import load_workbook
import pytest

from api import store_hours as sh
from api.store_schedules import schedule_catalog, scheduled_hours


def store(dealer='Connect', sid='NTG-DAL46', market='DALLAS'):
    return dict(dealer=dealer, store_id=sid, market=market, store='TEST STORE')


def test_all_workbook_rows_retained_and_only_verified_stores_mapped():
    source = json.loads((Path(__file__).resolve().parents[1]/'api/store_schedules.json').read_text())
    assert len(source['stores']) == 38
    assert len(schedule_catalog()) == 27
    assert sum(not s['portal_store_id'] for s in source['stores']) == 11
    assert not scheduled_hours(store('ARBF', 'C-70851157'), date(2026, 10, 22)).get('opening_time')
    assert not scheduled_hours(store('California', 'SPSCA1011'), date(2026, 10, 22)).get('opening_time')


@pytest.mark.parametrize('day,opening,closing,period', [
    (date(2026, 10, 23), time(10), time(20), 'Monday–Friday'),
    (date(2026, 10, 24), time(10), time(20), 'Saturday'),
    (date(2026, 10, 25), time(11), time(19), 'Sunday'),
    (date(2026, 10, 26), time(10), time(20), 'Monday–Friday'),
])
def test_connect_corrected_opening_and_date_selection(day, opening, closing, period):
    assert scheduled_hours(store(), day) == dict(opening_time=opening, closing_time=closing, period=period)


def test_all_connect_monday_saturday_corrections():
    connect = [entry for (dealer, _), entry in schedule_catalog().items() if dealer == 'Connect']
    assert len(connect) == 18
    assert all(entry[period]['opening_time'] == time(10) for entry in connect for period in ('weekday', 'saturday'))


def test_saturday_difference_and_aliases():
    glenview = store('AMQ', 'N1329B', 'CHICAGO')
    assert scheduled_hours(glenview, date(2026, 10, 23))['closing_time'] == time(19)
    assert scheduled_hours(glenview, date(2026, 10, 24))['closing_time'] == time(18)
    assert scheduled_hours(glenview, date(2026, 10, 25))['opening_time'] == time(12)
    assert scheduled_hours(store('ARM', '317-002', 'CHICAGO'), date(2026, 10, 23))['closing_time'] == time(19)
    assert 'opening_time' not in scheduled_hours(store('ARM', 'N1329B'), date(2026, 10, 23))


def test_store_exceptions_and_market_sundays():
    sunday = date(2026, 10, 25)
    assert scheduled_hours(store('Connect', 'NTG-HOU035', 'HOUSTON'), date(2026, 10, 23))['closing_time'] == time(19)
    assert scheduled_hours(store('Connect', 'NTG-HOU035', 'HOUSTON'), sunday)['closing_time'] == time(18)
    assert scheduled_hours(store('Connect', 'NTG-REN01', 'RENO'), sunday)['opening_time'] == time(12)
    assert scheduled_hours(store('SRH', 'TXD2121A'), date(2026, 10, 23))['opening_time'] == time(9)
    assert scheduled_hours(store('SRH', 'TXD2121A'), sunday)['closing_time'] == time(17)


def test_rows_resolve_each_day_and_keep_camera_review_pending():
    rows = sh.build_rows([store()], [], [], [], date(2026, 10, 23), date(2026, 10, 26))
    assert [r['opening_time'] for r in rows] == ['10:00:00', '10:00:00', '11:00:00', '10:00:00']
    assert all(r['opening_status'] == 'Pending camera review' and r['chargeback'] is None for r in rows)
    assert all(r['employee'] == '-' and r['rt_clockin'] is None for r in rows)


def test_camera_review_uses_sunday_schedule_and_explicit_override_wins():
    day = date(2026, 10, 18)
    review = dict(dealer='Connect', store_id='NTG-DAL46', report_date=day, camera_in=time(11, 10),
                  camera_out=time(18, 59), opening_time=None, closing_time=None, revision=1)
    row = sh.build_rows([store()], [], [review], [], day, day)[0]
    assert row['opening_status'] == 'Late' and row['chargeback'] == -10
    assert row['closing_status'] == 'Early'
    review['opening_time'] = time(11, 10)
    row = sh.build_rows([store()], [], [review], [], day, day)[0]
    assert row['opening_status'] == 'On Time' and row['chargeback'] == 0
    assert row['scheduled_opening_time'] == '11:00:00'


def test_excel_receives_resolved_weekend_hours():
    day = date(2026, 10, 18)
    rows = sh.build_rows([store()], [], [], [], day, day)
    book = load_workbook(sh.excel_report(dict(rows=rows, start=day.isoformat(), end=day.isoformat(),
        updated_at=None, coverage={'complete': 0, 'expected': 1})))
    assert book.active['F3'].value == '11:00:00 AM'
    assert book.active['J3'].value == '7:00:00 PM'


@pytest.mark.parametrize('opening,closing,expected', [
    ('11:00', '19:00', (None, None)),
    ('11:30', '18:00', (time(11, 30), time(18))),
    ('', '', (None, None)),
])
def test_camera_saves_store_only_explicit_schedule_overrides(monkeypatch, opening, closing, expected):
    calls = []
    class DB:
        def transaction(self): return nullcontext()
        def execute(self, sql, params):
            calls.append(params)
            return SimpleNamespace(fetchone=lambda: {'revision': 1})
    monkeypatch.setattr(sh, 'connect', lambda: nullcontext(DB()))
    monkeypatch.setattr(sh, 'roster_with_schedules', lambda conn: [store()])
    monkeypatch.setattr(sh, 'store_day_rows', lambda *args: [{'employee_key': '', 'revision': 0}])
    sh.save_review(dict(dealer='Connect', store_id='NTG-DAL46', date='2026-10-18', revision=0,
                        opening_time=opening, closing_time=closing, camera_in='11:10', camera_out='18:59'), 'user')
    assert calls[-1][4:6] == expected
    assert calls[-1][6:8] == (time(11, 10), time(18, 59))

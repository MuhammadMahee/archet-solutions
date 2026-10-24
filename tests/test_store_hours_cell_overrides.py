from contextlib import nullcontext
from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from api import index, store_hours as sh
from api.portal import PortalError


DAY = date(2026, 10, 20)


@pytest.mark.parametrize('value', [
    [], {'dealer': 'Changed'}, {'date': '2026-02-30'}, {'date': '2099-01-01'},
    {'date': None}, {'rt_clockin': '25:00'}, {'rt_clockout': '10:00+01:00'},
    {'chargeback': 'NaN'}, {'chargeback': 1000001}, {'chargeback': '1.001'},
    {'employee': 'x' * 161}, {'market': 'bad\nvalue'}, {'store_status': None},
])
def test_invalid_corrections_rejected(value):
    with pytest.raises(PortalError):
        sh.validate_cell_overrides(value)


def test_corrections_preserve_source_identity_and_survive_changed_imports():
    store = dict(dealer='Connect', store_id='1', store='Original Store', market='HOUSTON')
    punch = dict(source_id='connect', store_id='1', store='Original Store', report_date=DAY,
                 employee='Original Employee', clock_in=datetime(2026, 10, 20, 10, 5), clock_out=None)
    overrides = sh.validate_cell_overrides(dict(date='2026-10-19', market='RENO', store='Corrected Store',
        employee='Corrected Employee', store_status='Reviewed', rt_clockin='09:59',
        opening_status='Excused', rt_clockout='20:01', closing_status='Verified', chargeback='-25.50'))
    review = dict(dealer='Connect', store_id='1', report_date=DAY,
                  employee_key=sh.employee_key('Original Employee'), revision=1,
                  opening_time=time(10), camera_in=time(10, 5), cell_overrides=overrides)
    row = sh.build_rows([store], [punch], [review], [], DAY, DAY)[0]
    assert all(row[k] == v for k, v in overrides.items())
    assert row['source_date'] == DAY.isoformat()
    assert row['employee_key'] == sh.employee_key('Original Employee')
    assert row['source_values']['employee'] == 'Original Employee'
    assert row['source_values']['chargeback'] == -10
    punch['clock_in'] = datetime(2026, 10, 20, 11)
    assert sh.build_rows([store], [punch], [review], [], DAY, DAY)[0]['rt_clockin'] == '09:59:00'
    review['cell_overrides'] = {}
    restored = sh.build_rows([store], [punch], [review], [], DAY, DAY)[0]
    assert restored['date'] == DAY.isoformat()
    assert restored['employee'] == 'Original Employee'
    assert restored['rt_clockin'] == '2026-10-20T11:00:00'
    assert restored['chargeback'] == -10 and restored['opening_status'] == 'Late'


def test_blank_corrections_are_distinct_from_source_defaults():
    store = dict(dealer='Connect', store_id='1', store='Store', market='HOUSTON')
    review = dict(dealer='Connect', store_id='1', report_date=DAY, revision=1,
                  camera_in=time(10, 5), opening_time=time(10),
                  cell_overrides=sh.validate_cell_overrides({'employee':'', 'chargeback':None, 'store_status':''}))
    row = sh.build_rows([store], [], [review], [], DAY, DAY)[0]
    assert row['employee'] == row['store_status'] == ''
    assert row['chargeback'] is None
    assert row['source_values']['chargeback'] == -10


@pytest.mark.parametrize('value,expected', [(-25.5,'-$25.50'), (0,'$0'), (12,'$12'), (None,'Pending')])
def test_corrected_chargeback_display(value, expected):
    assert sh.display_value('chargeback', value) == expected


def test_date_correction_moves_filtered_row_without_extra_empty_placeholder(monkeypatch):
    target = date(2026, 10, 19)
    roster = [dict(dealer='Connect',store_id='1',store='Original',market='HOUSTON',source_id='connect')]
    reviews = [dict(dealer='Connect',store_id='1',report_date=DAY,employee_key='person:example',revision=1,
                    cell_overrides={'date':target.isoformat(),'market':'RENO','employee':'Corrected'})]
    punches = []

    class DB:
        def execute(self, sql, args=None):
            data = (reviews if 'from public.store_hours_employee_reviews' in sql else
                    punches if 'from public.store_time_punches' in sql else [])
            return SimpleNamespace(fetchall=lambda:data,fetchone=lambda:{'day':DAY})

    monkeypatch.setattr(sh,'connect',lambda:nullcontext(DB()))
    monkeypatch.setattr(sh,'roster_with_schedules',lambda conn:roster)
    with index.app.test_request_context('/api/internal/store-hours?market=RENO'):
        rows=sh.report_data(target,target)['rows']
        assert len(rows)==1 and rows[0]['employee']=='Corrected'
        assert rows[0]['source_date']==DAY.isoformat()
        assert sh.report_data(DAY,DAY)['rows']==[]
    with index.app.test_request_context('/api/internal/store-hours'):
        assert len(sh.report_data(target,target)['rows'])==1
        # A source punch with no employee name is real data, not an empty placeholder.
        punches.append(dict(source_id='connect',store_id='1',store='Original',report_date=target,
                            employee='-',clock_in=datetime(2026,10,19,10),clock_out=None))
        rows=sh.report_data(target,target)['rows']
        assert len(rows)==2 and any(r['rt_clockin'] for r in rows)
    roster.append(dict(dealer='Connect',store_id='2',store='Other store',market='DALLAS',source_id='connect'))
    with index.app.test_request_context('/api/internal/store-hours?store=Connect:1'):
        result=sh.report_data(target,target)
        assert len(result['stores'])==2
        assert result['markets']==['DALLAS','HOUSTON','RENO']

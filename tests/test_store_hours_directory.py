from datetime import date, datetime, time
from io import BytesIO
from contextlib import nullcontext

from openpyxl import Workbook
import pytest

from api import store_hours as sh
from api import store_hours_directory as directory
from api.portal import PortalError
from test_portal import store, client, login, write


DAY = date(2026, 10, 20)


def workbook(company='CONNECT WIRELESS', store='NEW STORE', opening=time(10), edit=None):
    b = Workbook()
    first = b.active
    first.title = 'MON TO SAT'
    first.append(['Store Opening', None, None, None, 'MONDAY - FRIDAY', None, 'SATURDAY'])
    first.append(['Carrier','Company Name','Market','Store','Opening Time','Closing Time','Opening Time','Closing Time'])
    first.append(['METRO BY T-MOBILE',company,'DALLAS',store,opening,time(20),opening,time(19)])
    sun = b.create_sheet('SUN')
    sun.append(['Store Opening',None,None,None,'SUNDAY'])
    sun.append(['Carrier','Company Name','Market','Store','Opening Time','Closing Time'])
    sun.append(['METRO BY T-MOBILE',company,'DALLAS',store,time(11),time(18)])
    if edit:
        edit(b)
    out = BytesIO()
    b.save(out)
    return out.getvalue()


def test_workbook_weekday_saturday_sunday_and_confirmed_correction():
    rows = directory.parse_schedule_workbook(workbook(opening=time(22)))
    assert rows[0]['corrected_connect_opening'] is True
    assert rows[0]['schedules']['weekday']['opening_time'] == '10:00:00'
    assert rows[0]['schedules']['saturday']['closing_time'] == '19:00:00'
    assert rows[0]['schedules']['sunday']['opening_time'] == '11:00:00'


@pytest.mark.parametrize('edit', [
    lambda b: b.remove(b['SUN']),
    lambda b: setattr(b['SUN']['D3'], 'value', 'OTHER STORE'),
    lambda b: setattr(b['SUN']['E3'], 'value', '=NOW()'),
    lambda b: setattr(b['SUN']['E3'], 'value', '25:00'),
    lambda b: b['SUN'].append(['METRO BY T-MOBILE','CONNECT WIRELESS','DALLAS','NEW STORE',time(11),time(18)]),
])
def test_bad_workbook_never_reaches_database(edit):
    with pytest.raises(PortalError):
        directory.parse_schedule_workbook(workbook(edit=edit))


def test_new_dealer_store_and_reupload_keep_stable_id():
    parsed = directory.parse_schedule_workbook(workbook(company='FUTURE DEALER'))
    first = directory.map_schedule_rows(parsed, [])[0]
    assert first['dealer'] == 'Future Dealer' and first['source_id'] is None
    assert first['action'] == 'Add'
    second = directory.map_schedule_rows(parsed, [first])[0]
    assert second['store_id'] == first['store_id'] and second['action'] == 'Update'


def test_seed_aliases_match_portal_ids_and_total_stores_stay_manual():
    parsed = directory.parse_schedule_workbook(workbook(company='ARM WIRELESS',store='GLENVIEW'))
    parsed[0]['market'] = 'CHICAGO'
    roster = [dict(dealer='AMQ', store_id='N1329B', market='CHICAGO', store='AMQ TRADING LLC', source_id='arm1')]
    mapped = directory.map_schedule_rows(parsed, roster)[0]
    assert mapped['store_id'] == 'N1329B' and mapped['source_id'] == 'arm1'
    total = directory.parse_schedule_workbook(workbook(company='ARBF',store='EULESS'))
    assert directory.map_schedule_rows(total, roster)[0]['source_id'] is None


def punch(name, hour, out):
    return dict(source_id='connect', store_id='1', store='STORE', market='HOUSTON', report_date=DAY,
                employee=name, clock_in=datetime(2026,10,20,hour), clock_out=datetime(2026,10,20,out))


def test_unique_employee_rows_multiple_shifts_and_manual_merge():
    roster = [dict(dealer='Connect', store_id='1', store='STORE', market='HOUSTON')]
    punches = [punch('Jane Doe',10,12),punch('  JANE   DOE ',13,20),punch('John Smith',11,19)]
    manual = [dict(dealer='Connect',store_id='1',report_date=DAY,employee='Jane Doe',employee_key=sh.employee_key('Jane Doe')),
              dict(dealer='Connect',store_id='1',report_date=DAY,employee='Alex New',employee_key=sh.employee_key('Alex New'))]
    rows = sh.build_rows(roster,punches,[],[],DAY,DAY,manual)
    assert len(rows) == 3
    jane = next(r for r in rows if r['employee_key'] == sh.employee_key('Jane Doe'))
    assert jane['rt_clockin'].endswith('10:00:00') and jane['rt_clockout'].endswith('20:00:00')
    assert jane['manual']
    alex = next(r for r in rows if r['employee']=='Alex New')
    assert alex['rt_clockin'] is alex['rt_clockout'] is None


def test_employee_reviews_and_chargebacks_are_independent():
    roster = [dict(dealer='Connect',store_id='1',store='STORE',market='HOUSTON')]
    reviews = [dict(dealer='Connect',store_id='1',report_date=DAY,employee_key=sh.employee_key(name),
                    opening_time=time(10),camera_in=camera,revision=revision)
               for name,camera,revision in [('Jane Doe',time(10,5),1),('John Smith',time(10,7),2)]]
    rows = sh.build_rows(roster,[punch('Jane Doe',10,20),punch('John Smith',11,19)],reviews,[],DAY,DAY)
    assert [r['revision'] for r in rows] == [1,2]
    assert [r['chargeback'] for r in rows] == [-10,-10]


def test_manual_only_dealer_has_placeholder_and_no_source_error():
    roster=[dict(dealer='The Fix',store_id='WB-1',store='PRIME',market='CHICAGO',source_id=None)]
    row=sh.build_rows(roster,[],[],[],DAY,DAY)[0]
    assert row['source_status']=='manual_only' and row['employee']=='-'


def test_reappearing_manual_duplicate_rejected(monkeypatch):
    class DB:
        def transaction(self): return nullcontext()
        def execute(self,*args): pass
    monkeypatch.setattr(sh,'connect',lambda:nullcontext(DB()))
    monkeypatch.setattr(sh,'roster_with_schedules',lambda conn:[dict(dealer='The Fix',store_id='WB-1')])
    monkeypatch.setattr(sh,'store_day_rows',lambda *args,**kwargs:[{'employee_key':sh.employee_key('Jane Doe')}])
    with pytest.raises(PortalError,match='already has a row'):
        sh.add_manual_employee(dict(dealer='The Fix',store_id='WB-1',date=DAY.isoformat(),employee=' JANE   DOE '),'user')


def test_manual_and_upload_access(client,monkeypatch):
    assert write(client,'store-hours/employees',{}).status_code==401
    login(client,'Member')
    for path in ('store-hours/schedules/preview','store-hours/schedules/apply'):
        assert write(client,path,{}).status_code==400
    monkeypatch.setattr(sh,'add_manual_employee',lambda *args:'person:jane')
    assert write(client,'store-hours/employees',{}).json['employee_key']=='person:jane'

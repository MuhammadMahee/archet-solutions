from datetime import date, datetime, time
from io import BytesIO
from contextlib import nullcontext
from types import SimpleNamespace

from openpyxl import Workbook, load_workbook
import pytest

from api import store_hours as sh
from api import index
from api import store_hours_directory as directory
from api.portal import PortalError
from test_portal import store, client, login, write


DAY = date(2026, 10, 20)


def schedule_row(dealer, sid, name):
    return dict(dealer=dealer,store_id=sid,store=name,market='OLD MARKET',company=dealer,source_id=None,
                schedules={period:{'opening_time':'10:00:00','closing_time':'20:00:00'}
                           for period in ('weekday','saturday','sunday')})


def test_roster_uses_only_calling_tree_with_renamed_store_schedules(monkeypatch):
    tree=[dict(dealer='MAGIC',store_id='WB-a',store='MAGIC1',market='DALLAS'),
          dict(dealer='California',store_id='WB-b',store='THE FIX',market='UTAH'),
          dict(dealer='California',store_id='WB-c',store='THE FIX',market='UTAH')]
    old=[schedule_row('Smoke Magic','WB-a','MAGIC 1'),schedule_row('The Fix','WB-b','HARRISVILLE'),
         schedule_row('The Fix','WB-c','LAYTON'),schedule_row('Other','WB-extra','EXCLUDED')]
    monkeypatch.setattr(directory,'active_roster',lambda conn:tree)
    conn=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:old))
    rows=directory.roster_with_schedules(conn)
    assert {(r['dealer'],r['store_id']) for r in rows}=={(r['dealer'],r['store_id']) for r in tree}
    assert len(rows)==3  # Same-name Calling Tree stores remain separate locations.
    assert next(r for r in rows if r['store_id']=='WB-a')['store']=='MAGIC1'
    assert {r['market'] for r in rows}=={'DALLAS','UTAH'}
    assert all(directory.hours_for_store(r,DAY)['opening_time']==time(10) for r in rows)
    assert all(r['source_id'] is None for r in rows)
    tree.clear()
    assert directory.roster_with_schedules(conn)==[]


def test_schedule_matching_prefers_exact_dealer_and_rejects_ambiguous_ids(monkeypatch):
    tree=[dict(dealer='MAGIC',store_id=sid,store=sid,market='DALLAS') for sid in ('WB-a','WB-b','ordinary')]
    exact=schedule_row('MAGIC','WB-a','CURRENT');exact['schedules']['weekday']['opening_time']='09:00:00'
    old=[exact,schedule_row('Old','WB-a','OLD'),schedule_row('Old','WB-b','FIRST'),
         schedule_row('Other','WB-b','SECOND'),schedule_row('Other','ordinary','OTHER DEALER')]
    monkeypatch.setattr(directory,'active_roster',lambda conn:tree)
    conn=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:old))
    rows={r['store_id']:r for r in directory.roster_with_schedules(conn)}
    assert directory.hours_for_store(rows['WB-a'],DAY)['opening_time']==time(9)
    assert 'schedules' not in rows['WB-b'] and 'schedules' not in rows['ordinary']


@pytest.mark.parametrize('path',['store-hours','compliance'])
def test_both_reports_filters_and_exports_exclude_legacy_store_duplicates(monkeypatch,path):
    tree=[dict(dealer='MAGIC',store_id='WB-a',store='MAGIC1',market='DALLAS'),
          dict(dealer='California',store_id='WB-b',store='THE FIX - HARRISVILLE',market='UTAH')]
    old=[schedule_row('Smoke Magic','WB-a','MAGIC 1'),schedule_row('The Fix','WB-b','HARRISVILLE'),
         schedule_row('Other','WB-extra','EXCLUDED')]
    manual=[dict(dealer='MAGIC',store_id='WB-a',report_date=DAY,employee=name,employee_key=sh.employee_key(name))
            for name in ('Alice','Bob')]
    manual.append(dict(dealer='Smoke Magic',store_id='WB-a',report_date=DAY,employee='Old row',employee_key='person:old'))
    reviews=[dict(dealer='MAGIC',store_id='WB-a',report_date=DAY,employee_key='person:alice',revision=3,camera_in=time(10))]
    class DB:
        def execute(self,sql,args=None):
            rows=old if 'public.store_hours_directory' in sql else manual if '_manual_employees' in sql else reviews if '_employee_reviews' in sql else []
            return SimpleNamespace(fetchall=lambda:rows,fetchone=lambda:{'day':DAY})
    monkeypatch.setattr(directory,'active_roster',lambda conn:tree)
    monkeypatch.setattr(sh,'connect',lambda:nullcontext(DB()))
    with index.app.test_request_context('/api/internal/'+path+'/sheet/export'):
        data=sh.report_data(DAY,DAY)
        assert {(r['dealer'],r['store_id']) for r in data['rows']}=={('MAGIC','WB-a'),('California','WB-b')}
        assert len(data['rows'])==3  # Keep legitimate employee rows.
        assert next(r for r in data['rows'] if r['employee']=='Alice')['revision']==3
        assert len(data['directory'])==len(data['stores'])==2
        assert {d['id'] for d in data['dealers']}=={'MAGIC','California'}
        assert data['markets']==['DALLAS','UTAH']
        book=load_workbook(sh.excel_report(data))
        values={cell.value for row in book.active for cell in row if isinstance(cell.value,str)}
        assert 'MAGIC1' in values and 'THE FIX - HARRISVILLE' in values
        assert not {'MAGIC 1','HARRISVILLE','EXCLUDED','Smoke Magic','The Fix'}&values


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
    assert directory.map_schedule_rows(parsed, roster) == []
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

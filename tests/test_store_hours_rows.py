from contextlib import nullcontext
from datetime import date, datetime
from copy import deepcopy
import pytest
from api import store_hours as sh
from api.portal import PortalError
from test_portal import client, store, login, write

DAY=date(2026,10,20)
STORE=dict(dealer='Connect',store_id='1',store='STORE',market='HOUSTON',
           schedules={'weekday':{'opening_time':'10:00:00','closing_time':'20:00:00'}})


def punch(name):
    return dict(source_id='connect',store_id='1',store='STORE',employee=name,report_date=DAY,
                clock_in=datetime(2026,10,20,10),clock_out=None)


def test_removed_rows_survive_sync_without_hiding_new_employees():
    review=dict(dealer='Connect',store_id='1',report_date=DAY,employee_key=sh.employee_key('Jane'),removed=True,revision=3)
    assert sh.build_rows([STORE],[punch('Jane')],[review],[],DAY,DAY)==[]
    rows=sh.build_rows([STORE],[punch('Jane'),punch('John')],[review],[],DAY,DAY)
    assert [r['employee'] for r in rows]==['John']
    removed=sh.build_rows([STORE],[punch('Jane')],[review],[],DAY,DAY,include_removed=True)[0]
    assert removed['removed'] and removed['revision']==3 and removed['rt_clockin']
    # A removed blank placeholder must not transfer its removal to the first imported employee.
    review['employee_key']=''
    assert sh.build_rows([STORE],[],[review],[],DAY,DAY)==[]
    assert sh.build_rows([STORE],[punch('Jane')],[review],[],DAY,DAY)[0]['employee']=='Jane'


def setup_db(monkeypatch):
    rows=sh.build_rows([STORE],[punch('Jane'),punch('John')],[],[],DAY,DAY)
    rows[0].update(cell_overrides={'employee':'Corrected Jane'},custom_cells={'custom_1':'Keep'},
                   cell_formats={'employee':{'font_family':'Calibri'}})
    calls=[]
    class DB:
        def transaction(self):return nullcontext()
        def execute(self,sql,args):calls.append((sql,args))
    monkeypatch.setattr(sh,'connect',lambda:nullcontext(DB()))
    monkeypatch.setattr(sh,'roster_with_schedules',lambda conn:[STORE])
    monkeypatch.setattr(sh,'store_day_rows',lambda conn,store,day,include_removed=False:deepcopy(rows))
    return rows,calls


def identities(rows):
    return [{k:r[k] for k in ('dealer','store_id','source_date','employee_key','revision')} for r in rows]


def test_removal_batch_preserves_values_and_restoration_uses_revision(monkeypatch):
    rows,calls=setup_db(monkeypatch)
    assert sh.set_rows_removed({'action':'remove','rows':identities(rows)},'user')==2
    inserts=[args for sql,args in calls if sql.startswith('insert')]
    assert len(inserts)==2
    assert inserts[0][4:6]==(None,None)  # Do not pin workbook defaults as overrides.
    assert inserts[0][9]==1 and inserts[0][-1] is True
    assert inserts[0][10].obj=={'employee':'Corrected Jane'}
    assert inserts[0][11].obj=={'custom_1':'Keep'}
    assert inserts[0][12].obj=={'employee':{'font_family':'Calibri'}}
    rows[0].update(removed=True,revision=1)
    assert sh.set_rows_removed({'action':'restore','rows':identities(rows[:1])},'user')==1
    assert calls[-1][1][-1] is False and calls[-1][1][9]==2


@pytest.mark.parametrize('failure',['stale','already_removed','missing','duplicate'])
def test_removal_validates_entire_batch_before_writing(monkeypatch,failure):
    rows,calls=setup_db(monkeypatch);entries=identities(rows)
    if failure=='stale':entries[1]['revision']=99
    if failure=='already_removed':rows[1]['removed']=True
    if failure=='missing':entries[1]['employee_key']='missing'
    if failure=='duplicate':entries.append(entries[0])
    with pytest.raises(PortalError):sh.set_rows_removed({'action':'remove','rows':entries},'user')
    assert not any(sql.startswith('insert') for sql,args in calls)


@pytest.mark.parametrize('payload',[{}, {'action':'delete','rows':[{}]}, {'action':'remove','rows':[]},
    {'action':'remove','rows':[{}]*101}, {'action':'restore','rows':['bad']}])
def test_bad_row_requests_rejected(payload):
    with pytest.raises(PortalError):sh.set_rows_removed(payload,'user')


def test_row_route_requires_session_and_same_origin(client,monkeypatch):
    assert write(client,'store-hours/rows',{}).status_code==401
    login(client,'Member')
    assert client.post('/api/internal/store-hours/rows',json={}).status_code==403
    monkeypatch.setattr(sh,'set_rows_removed',lambda payload,user:2)
    assert write(client,'store-hours/rows',{}).json['count']==2

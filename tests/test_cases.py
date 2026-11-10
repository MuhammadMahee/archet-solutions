"""Case validation plus opt-in SQL tests using session-local temporary tables only."""
import base64
from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image
import psycopg
from psycopg.rows import dict_row
import pytest

from api import cases, index
from api.portal import PortalError
from test_portal import client, store, login, write


def payload(to=None, cc=None, **changes):
    return dict(request_id=str(uuid4()), violation_date=cases.today().isoformat(),
                dealer='Connect', store_id='C1',
                employee_ntid='ntid-100', employee_name='Example Employee',
                case_type='Payment Fraud', subject='Review invoice', body='Evidence for review.',
                to=to or [str(uuid4())], cc=cc or [], attachments=[], **changes)


def picture():
    image=Image.new('RGB',(20,20),'red');data=BytesIO();image.save(data,format='PNG')
    return {'filename':'evidence.png','content':base64.b64encode(data.getvalue()).decode()}


@pytest.mark.parametrize('field,value',[
    ('violation_date','bad'),('violation_date',(cases.today()+timedelta(days=1)).isoformat()),
    ('case_type','Unknown'),('to',[]),('to',['not-a-user']),('employee_name',''),
    ('employee_ntid',''),('subject',''),('body',''),('request_id','bad'),
    ('attachments',[{'filename':'x.svg','content':base64.b64encode(b'<svg/>').decode()}]),
    ('attachments',[picture()]*6),
])
def test_bad_draft_rejected(field,value):
    data=payload();data[field]=value
    with pytest.raises(PortalError):cases.validate_draft(data)


def test_custom_type_recipients_and_picture_validation():
    data=payload();data.update(case_type='Custom',custom_type='Unusual invoice',attachments=[picture()])
    result=cases.validate_draft(data)
    assert result['case_type']=='Unusual invoice' and result['employee_ntid']=='NTID-100'
    assert result['attachments'][0]['content_type']=='image/png'
    data['cc']=data['to']
    with pytest.raises(PortalError,match='only once'):cases.validate_draft(data)
    data['cc']=[];data['custom_type']=''
    with pytest.raises(PortalError):cases.validate_draft(data)


def test_picture_orientation_is_preserved_and_metadata_removed():
    source=Image.new('RGB',(10,20),'blue');exif=Image.Exif();exif[274]=6
    data=BytesIO();source.save(data,format='JPEG',exif=exif)
    saved=cases.validate_images([{'filename':'photo.jpg','content':base64.b64encode(data.getvalue()).decode()}])[0]
    with Image.open(BytesIO(saved['data'])) as result:
        assert result.size==(20,10)
        assert not result.getexif()


def test_unauthenticated_and_member_admin_routes(client):
    assert client.get('/api/internal/cases').status_code==401
    assert client.get('/api/internal/cases/recipients').status_code==401
    login(client,'Member')
    assert client.get('/api/internal/cases/report').status_code==403
    assert client.get('/api/internal/cases?folder=all').status_code==403
    assert write(client,'cases/'+str(uuid4())+'/review',{'status':'approved','revision':1},'PATCH').status_code==403
    assert client.post('/api/internal/cases',json=payload()).status_code==403


@pytest.fixture
def case_db(monkeypatch,store):
    if os.getenv('CASE_TEST_DB')!='1':pytest.skip('Set CASE_TEST_DB=1 to run isolated temporary-table SQL integration tests.')
    store.add_user('Outsider','member')
    # Temporary tables are private to this connection and disappear when closed.
    # The adapter redirects every cases query; no public table is mutated.
    conn=psycopg.connect(os.environ['SUPABASE_DB_URL'],autocommit=True,row_factory=dict_row,connect_timeout=15)
    conn.execute('create temp table portal_users(id uuid primary key,username text,display_name text,active boolean)')
    for user in store.tables['portal_users']:
        conn.execute('insert into pg_temp.portal_users values(%s,%s,%s,%s)',(user['id'],user['username'],user['display_name'],user['active']))
    migration=(Path(__file__).parents[1]/'supabase/migrations/030_violation_cases.sql').read_text()
    ddl=migration.split('alter table public.violation_cases enable row level security;')[0]
    ddl=ddl.replace('create table public.','create temp table pg_temp.').replace('public.','pg_temp.')
    conn.execute(ddl,prepare=False)
    editing=(Path(__file__).parents[1]/'supabase/migrations/031_case_editing.sql').read_text()
    ddl=editing.split('alter table public.case_edits enable row level security;')[0]
    conn.execute(ddl.replace('create table public.','create temp table pg_temp.').replace('public.','pg_temp.'),prepare=False)
    locations=(Path(__file__).parents[1]/'supabase/migrations/032_case_locations.sql').read_text()
    conn.execute(locations.replace('public.','pg_temp.'),prepare=False)
    conn.execute('create temp table calling_tree_versions(id integer primary key,status text,filename text,worksheet text,activated_at timestamptz)')
    conn.execute("insert into pg_temp.calling_tree_versions values(1,'active','Test.xlsx','Stores',now())")
    conn.execute('create temp table calling_tree_stores(version_id integer,dealer text,store_id text,store text,market text,row_number integer)')
    conn.execute("""insert into pg_temp.calling_tree_stores values
        (1,'Connect','C1','EXAMPLE STORE','DALLAS',1),
        (1,'Connect','C2','SECOND STORE','DALLAS',2),
        (1,'ARBF','A1','EULESS','TOTAL',3)""")

    class Cursor:
        def __enter__(self):self.raw=conn.cursor();return self
        def __exit__(self,*args):self.raw.close()
        def executemany(self,sql,params):return self.raw.executemany(sql.replace('public.','pg_temp.'),params)

    class DB:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):return conn.execute(sql.replace('public.','pg_temp.'),params)
        def transaction(self):return conn.transaction()
        def cursor(self):return Cursor()

    db=DB();monkeypatch.setattr(cases,'connect',lambda:db)
    try:yield db
    finally:conn.close()


def signed_in(name):
    result=index.app.test_client();assert login(result,name).status_code==200;return result


def test_calling_tree_locations_are_validated_saved_and_editable_by_admin_only(client,store,case_db):
    login(client,'Member')
    options=client.get('/api/internal/cases/recipients').json['stores']
    assert {(s['dealer'],s['store_id']) for s in options}=={('Connect','C1'),('Connect','C2'),('ARBF','A1')}
    for location in ({},{'dealer':'Connect'},{'dealer':'ARBF','store_id':'C1'},{'dealer':'Unknown','store_id':'C1'}):
        draft=payload([store.owner['id']]);draft.pop('dealer');draft.pop('store_id');draft.update(location)
        assert write(client,'cases',draft).status_code==400
    draft=payload([store.owner['id']]);draft['store_name']='Forged name'
    cid=write(client,'cases',draft).json['id']
    saved=client.get('/api/internal/cases/'+cid).json['case']
    assert (saved['dealer'],saved['store_id'],saved['store_name'])==('Connect','C1','EXAMPLE STORE')
    assert client.get('/api/internal/cases').json['cases'][0]['store_name']=='EXAMPLE STORE'
    assert write(client,'cases/'+cid,{'revision':1,'dealer':'ARBF','store_id':'A1'},'PATCH').status_code==403
    owner=signed_in('Mahee')
    assert write(owner,'cases/'+cid+'/review',{'revision':1,'status':'approved'},'PATCH').status_code==200
    assert write(owner,'cases/'+cid,{'revision':2,'dealer':'ARBF','store_id':'C1'},'PATCH').status_code==400
    assert write(owner,'cases/'+cid,{'revision':2,'dealer':'ARBF','store_id':'A1'},'PATCH').status_code==200
    edited=owner.get('/api/internal/cases/'+cid).json
    assert edited['case']['store_name']=='EULESS' and edited['case']['status']=='pending'
    assert edited['edits'][0]['changed_fields']==['dealer','store_id','store_name']
    # Retired selections and legacy cases can still receive recipient/content edits.
    case_db.execute("delete from public.calling_tree_stores where store_id='A1'")
    assert write(owner,'cases/'+cid,{'revision':3,'subject':'Updated'},'PATCH').status_code==200
    case_db.execute("update public.violation_cases set dealer='',store_id='',store_name='' where id=%s",(cid,))
    assert write(client,'cases/'+cid,{'revision':4,'cc':[store.admin['id']]},'PATCH').status_code==200


def test_case_page_grants_are_independent_and_enforced(client,store,case_db):
    login(client)
    cid=write(client,'cases',payload([store.member['id']])).json['id']
    store.db('portal_users','PATCH',{'page_access':['inbox']},id='eq.'+store.member['id'])
    member=signed_in('Member')
    assert member.get('/api/internal/cases?folder=inbox').status_code==200
    assert member.get('/api/internal/cases/'+cid).status_code==200
    assert member.get('/api/internal/cases/unread').status_code==200
    assert member.get('/api/internal/cases').status_code==403
    assert write(member,'cases',payload([store.owner['id']])).status_code==403
    store.db('portal_users','PATCH',{'page_access':['cases']},id='eq.'+store.member['id'])
    member=signed_in('Member')
    assert member.get('/api/internal/cases').status_code==200
    assert member.get('/api/internal/cases?folder=inbox').status_code==403
    assert member.get('/api/internal/cases/unread').status_code==403
    store.db('portal_users','PATCH',{'page_access':['case-report']},id='eq.'+store.admin['id'])
    admin=signed_in('OtherAdmin');day=cases.today().isoformat()
    assert admin.get('/api/internal/cases/report?start='+day+'&end='+day).status_code==200
    assert admin.get('/api/internal/cases/'+cid).status_code==200
    assert admin.get('/api/internal/cases').status_code==403
    store.db('portal_users','PATCH',{'page_access':['cases','inbox']},id='eq.'+store.admin['id'])
    admin=signed_in('OtherAdmin')
    assert admin.get('/api/internal/cases/report?start='+day+'&end='+day).status_code==403


def test_store_rename_and_page_access_migration_preserves_records(store,case_db):
    # Every table is session-local; exercise the complete production data migration.
    case_db.execute("alter table public.portal_users add column role text default 'member', add column page_access text[]")
    case_db.execute("alter table public.portal_users add constraint portal_page_access_valid check(page_access is null or cardinality(page_access)<=9)")
    case_db.execute("update public.portal_users set page_access=array['sales'] where id=%s",(store.member['id'],))
    case_db.execute("update public.portal_users set role='admin',page_access=array[]::text[] where id=%s",(store.admin['id'],))
    case_db.execute("update public.calling_tree_stores set store='EULESS' where store_id='A1'")
    case_db.execute('create temp table public.store_hours_directory(store_id text,store text,updated_at timestamptz)')
    case_db.execute("insert into public.store_hours_directory values('A1','EULESS',now())")
    for table in ('store_time_punches','sales_performance'):
        case_db.execute(f'create temp table public.{table}(store text)')
        case_db.execute(f"insert into public.{table} values('EULESS')")
    for table in ('store_hours_employee_reviews','compliance_employee_reviews'):
        case_db.execute(f'create temp table public.{table}(cell_overrides jsonb,revision integer)')
        case_db.execute(f'''insert into public.{table} values('{{"store":"EULESS","employee":"Original"}}',4)''')
    migration=(Path(__file__).parents[1]/'supabase/migrations/033_store_name_and_case_page_access.sql').read_text()
    case_db.execute(migration)
    assert case_db.execute('select store_id,store from public.store_hours_directory').fetchone()=={'store_id':'A1','store':'109 MARTHA ST SUITE 227'}
    for table in ('store_time_punches','sales_performance'):
        assert case_db.execute(f'select store from public.{table}').fetchone()['store']=='109 MARTHA ST SUITE 227'
    for table in ('store_hours_employee_reviews','compliance_employee_reviews'):
        row=case_db.execute(f'select * from public.{table}').fetchone()
        assert row['cell_overrides']=={'store':'109 MARTHA ST SUITE 227','employee':'Original'} and row['revision']==5
    rows={str(r['id']):r for r in case_db.execute('select id,page_access from public.portal_users').fetchall()}
    assert set(rows[store.member['id']]['page_access'])=={'sales','cases','inbox'}
    assert set(rows[store.admin['id']]['page_access'])=={'cases','inbox','case-report'}
    assert rows[store.owner['id']]['page_access'] is None
    cid=case_db.execute('''insert into public.violation_cases(submitted_by,sender_name,request_id,
        violation_date,employee_ntid,employee_name,case_type,subject,body,dealer,store_id,store_name)
        values(%s,'Member',%s,%s,'N1','Example','Theft','Example','Details','ARBF','A1','109 MARTHA ST SUITE 227') returning id''',
        (store.member['id'],str(uuid4()),cases.today())).fetchone()['id']
    restore=(Path(__file__).parents[1]/'supabase/migrations/034_restore_euless_store_name.sql').read_text()
    case_db.execute(restore)
    assert case_db.execute('select store_id,store from public.store_hours_directory').fetchall()==[{'store_id':'A1','store':'EULESS'}]
    assert case_db.execute("select store_id,store from public.calling_tree_stores where store_id='A1'").fetchall()==[{'store_id':'A1','store':'EULESS'}]
    for table in ('store_time_punches','sales_performance'):
        assert case_db.execute(f'select store from public.{table}').fetchall()==[{'store':'EULESS'}]
    for table in ('store_hours_employee_reviews','compliance_employee_reviews'):
        assert case_db.execute(f'select * from public.{table}').fetchall()==[{'cell_overrides':{'store':'EULESS','employee':'Original'},'revision':6}]
    assert case_db.execute('select store_id,store_name,revision from public.violation_cases where id=%s',(cid,)).fetchone()=={'store_id':'A1','store_name':'EULESS','revision':2}


def test_send_inbox_privacy_attachments_and_retry(client,store,case_db):
    login(client,'Member')
    draft=payload([store.owner['id']],[store.admin['id']]);draft['attachments']=[picture()]
    sent=write(client,'cases',draft);assert sent.status_code==201,sent.json
    cid=sent.json['id']
    assert write(client,'cases',draft).json['id']==cid
    assert len(client.get('/api/internal/cases').json['cases'])==1
    owner=signed_in('Mahee');cc=signed_in('OtherAdmin');outsider=signed_in('Outsider')
    assert owner.get('/api/internal/cases/unread').json['count']==1
    assert cc.get('/api/internal/cases/unread').json['count']==1
    assert len(owner.get('/api/internal/cases?folder=inbox').json['cases'])==1
    assert outsider.get('/api/internal/cases?folder=inbox').json['cases']==[]
    assert outsider.get('/api/internal/cases/'+cid).status_code==404
    detail=owner.get('/api/internal/cases/'+cid).json
    assert len(detail['recipients'])==2 and detail['case']['employee_ntid']=='NTID-100'
    aid=detail['attachments'][0]['id'];url='/api/internal/cases/'+cid+'/attachments/'+aid
    assert owner.get(url).mimetype=='image/png'
    assert outsider.get(url).status_code==404
    assert client.get(url).status_code==200
    assert owner.get('/api/internal/cases/unread').json['count']==1 # GET is read-only
    assert write(owner,'cases/'+cid+'/read',{}).status_code==200
    assert owner.get('/api/internal/cases/unread').json['count']==0
    assert cc.get('/api/internal/cases/unread').json['count']==1


def test_atomic_delivery_review_conflicts_and_report(client,store,case_db):
    login(client,'Member')
    draft=payload([store.owner['id']],cc=[str(uuid4())])
    assert write(client,'cases',draft).status_code==400
    assert case_db.execute('select count(*) as n from public.violation_cases').fetchone()['n']==0
    draft['cc']=[]
    cid=write(client,'cases',draft).json['id']
    second=payload([store.owner['id']]);second['violation_date']=(cases.today()-timedelta(days=7)).isoformat()
    assert write(client,'cases',second).status_code==201
    owner=signed_in('Mahee')
    assert write(owner,'cases/'+cid+'/review',{'status':'approved','revision':1},'PATCH').status_code==200
    assert write(owner,'cases/'+cid+'/review',{'status':'not_approved','revision':1},'PATCH').status_code==409
    assert write(owner,'cases/'+cid+'/review',{'status':'not_approved','revision':2},'PATCH').status_code==200
    detail=owner.get('/api/internal/cases/'+cid).json
    assert detail['case']['status']=='not_approved' and len(detail['reviews'])==2
    today=cases.today().isoformat()
    report=owner.get('/api/internal/cases/report?start='+today+'&end='+today)
    assert report.status_code==200,report.json
    data=report.json
    assert data['total']==1 and len(data['rows'])==1
    assert data['rows'][0]['user']=='Member'
    assert data['ranking'][0]['submitted']==1 and data['ranking'][0]['not_approved']==1
    for _ in range(2):
        assert write(owner,'cases',payload([store.member['id']])).status_code==201
    ranked=owner.get('/api/internal/cases/report?start='+today+'&end='+today).json
    assert ranked['total']==3
    assert [(r['user_name'],r['submitted']) for r in ranked['ranking']]==[('Mahee',2),('Member',1)]
    assert owner.get('/api/internal/cases/report?start=2026-11-10&end=2026-11-01').status_code==400


def test_disabled_recipient_pagination_and_restricted_pages(client,store,case_db):
    store.db('portal_users','PATCH',{'page_access':['cases','inbox']},id='eq.'+store.member['id'])
    login(client,'Member')
    pages=client.get('/api/internal/me').json['user']['page_access']
    assert {'callingtree','cases','inbox'}<=set(pages)
    assert 'case-report' not in pages
    assert client.get('/api/internal/cases/recipients').status_code==200
    case_db.execute('update public.portal_users set active=false where id=%s',(store.admin['id'],))
    assert write(client,'cases',payload([store.admin['id']])).status_code==400
    assert client.get('/api/internal/cases?offset=-1').status_code==400
    assert client.get('/api/internal/cases?status=invalid').status_code==400
    # Fixed ordering and page boundaries use real PostgreSQL queries.
    for n in range(51):
        case_db.execute('''insert into public.violation_cases(submitted_by,sender_name,request_id,
            violation_date,employee_ntid,employee_name,case_type,subject,body)
            values(%s,'Member',%s,%s,'N1','Example','Theft',%s,'Details')''',
            (store.member['id'],str(uuid4()),cases.today(),'Case '+str(n)))
    first=client.get('/api/internal/cases').json;second=client.get('/api/internal/cases?offset=50').json
    assert len(first['cases'])==50 and first['has_more']
    assert len(second['cases'])==1 and not second['has_more']
    assert first['cases'][0]['id']!=second['cases'][0]['id']


def test_sender_edits_only_recipients_and_recipient_access_is_revoked(client,store,case_db):
    login(client,'Member')
    outsider=next(u for u in store.tables['portal_users'] if u['username']=='Outsider')
    cid=write(client,'cases',payload([outsider['id']],[store.admin['id']])).json['id']
    other=signed_in('Outsider');owner=signed_in('Mahee')
    assert other.get('/api/internal/cases/'+cid).json['case']['can_edit'] is False
    assert write(other,'cases/'+cid,{'revision':1,'to':[store.owner['id']]},'PATCH').status_code==403
    assert write(other,'cases/'+cid,{'revision':1},'DELETE').status_code==403
    for key,value in [('sender_id',store.owner['id']),('submitted_by',store.owner['id']),('subject','Changed'),
                      ('dealer','ARBF'),('store_id','A1'),('store_name','Forged'),
                      ('body','Changed'),('employee_name','Changed'),('case_type','Theft'),('attachments',[]),
                      ('remove_attachments',[]),('status','approved')]:
        assert write(client,'cases/'+cid,{'revision':1,key:value},'PATCH').status_code==403
    assert write(owner,'cases/'+cid+'/review',{'revision':1,'status':'approved'},'PATCH').status_code==200
    response=write(client,'cases/'+cid,{'revision':2,'to':[store.owner['id']],'cc':[store.admin['id']]},'PATCH')
    assert response.status_code==200,response.json
    updated=client.get('/api/internal/cases/'+cid).json
    assert updated['case']['status']=='approved' and updated['case']['revision']==3
    assert updated['edits'][0]['changed_fields']==['to']
    assert other.get('/api/internal/cases/'+cid).status_code==404
    assert other.get('/api/internal/cases?folder=inbox').json['cases']==[]
    assert other.get('/api/internal/cases/unread').json['count']==0
    assert owner.get('/api/internal/cases/unread').json['count']==1
    assert write(client,'cases/'+cid,{'revision':2,'to':[store.owner['id']]},'PATCH').status_code==409
    assert write(client,'cases/'+cid,{'revision':3,'to':[]},'PATCH').status_code==400
    assert write(client,'cases/'+cid,{'revision':3,'cc':[store.owner['id']]},'PATCH').status_code==400
    assert client.get('/api/internal/cases/'+cid).json['case']['revision']==3


def test_admin_changes_sender_details_pictures_and_report_attribution(client,store,case_db):
    login(client,'Member')
    outsider=next(u for u in store.tables['portal_users'] if u['username']=='Outsider')
    draft=payload([store.member['id']],[store.owner['id']]);draft['attachments']=[picture()]
    cid=write(client,'cases',draft).json['id'];owner=signed_in('Mahee')
    aid=client.get('/api/internal/cases/'+cid).json['attachments'][0]['id']
    assert write(owner,'cases/'+cid+'/review',{'status':'approved','revision':1},'PATCH').status_code==200
    changed=write(owner,'cases/'+cid,{'revision':2,'sender_id':outsider['id'],
        'subject':'Corrected subject','case_type':'Custom','custom_type':'Invoice error',
        'employee_ntid':'updated-ntid','body':'Corrected details','remove_attachments':[aid]},'PATCH')
    assert changed.status_code==200,changed.json
    result=owner.get('/api/internal/cases/'+cid).json
    assert result['case']['sender_id']==outsider['id'] and result['case']['sender_name']=='Outsider'
    assert result['case']['submitted_by']==store.member['id'] # original creator remains immutable
    assert result['case']['status']=='pending' and result['case']['reviewed_by'] is None
    assert result['case']['case_type']=='Invoice error' and result['case']['employee_ntid']=='UPDATED-NTID'
    assert result['attachments']==[] and 'sender' in result['edits'][0]['changed_fields']
    assert owner.get('/api/internal/cases/'+cid+'/attachments/'+aid).status_code==404
    assert client.get('/api/internal/cases').json['cases']==[]
    assert client.get('/api/internal/cases/'+cid).json['case']['can_edit'] is False # still a recipient
    assert write(client,'cases/'+cid,{'revision':3,'to':[store.owner['id']]},'PATCH').status_code==403
    assert write(client,'cases/'+cid,{'revision':3},'DELETE').status_code==403
    sender=signed_in('Outsider')
    assert sender.get('/api/internal/cases').json['cases'][0]['can_edit'] is True
    assert write(sender,'cases/'+cid,{'revision':3,'cc':[store.admin['id']]},'PATCH').status_code==200
    assert write(client,'cases',draft).json['id']==cid # retry cannot duplicate a reassigned case
    today=cases.today().isoformat()
    report=owner.get('/api/internal/cases/report?start='+today+'&end='+today).json
    assert report['ranking'][0]['user_name']=='Outsider' and report['rows'][0]['user']=='Outsider'
    invalid=write(owner,'cases/'+cid,{'revision':4,'sender_id':str(uuid4())},'PATCH')
    assert invalid.status_code==400
    assert write(owner,'cases/'+cid,{'revision':4,'remove_attachments':[str(uuid4())]},'PATCH').status_code==400
    assert owner.get('/api/internal/cases/'+cid).json['case']['revision']==4
    audit=case_db.execute('select before_state,after_state from public.case_edits where case_id=%s order by id',(cid,)).fetchall()
    assert audit[0]['before_state']['sender_id']==store.member['id'] and audit[0]['after_state']['sender_id']==outsider['id']


def test_sender_and_admin_delete_hide_case_inbox_pictures_and_reports(client,store,case_db):
    login(client,'Member');owner=signed_in('Mahee')
    draft=payload([store.owner['id']]);draft['attachments']=[picture()]
    cid=write(client,'cases',draft).json['id']
    aid=client.get('/api/internal/cases/'+cid).json['attachments'][0]['id']
    assert write(client,'cases/'+cid,{'revision':2},'DELETE').status_code==409
    assert client.delete('/api/internal/cases/'+cid,json={'revision':1}).status_code==403
    response=write(client,'cases/'+cid,{'revision':1},'DELETE')
    assert response.status_code==200,response.json
    assert client.get('/api/internal/cases').json['cases']==[]
    assert owner.get('/api/internal/cases?folder=all').json['cases']==[]
    assert owner.get('/api/internal/cases?folder=inbox').json['cases']==[]
    assert owner.get('/api/internal/cases/unread').json['count']==0
    assert client.get('/api/internal/cases/'+cid).status_code==404
    assert owner.get('/api/internal/cases/'+cid+'/attachments/'+aid).status_code==404
    assert write(owner,'cases/'+cid+'/review',{'revision':2,'status':'approved'},'PATCH').status_code==404
    assert write(owner,'cases/'+cid,{'revision':2,'subject':'Resurrect'},'PATCH').status_code==404
    assert write(client,'cases',draft).status_code==409
    today=cases.today().isoformat()
    assert owner.get('/api/internal/cases/report?start='+today+'&end='+today).json['total']==0
    record=case_db.execute('select deleted_at,deleted_by from public.violation_cases where id=%s',(cid,)).fetchone()
    assert record['deleted_at'] and str(record['deleted_by'])==store.member['id']
    cid2=write(client,'cases',payload([store.admin['id']])).json['id']
    assert write(owner,'cases/'+cid2,{'revision':1},'DELETE').status_code==200

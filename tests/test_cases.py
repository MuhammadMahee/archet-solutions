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
    store.db('portal_users','PATCH',{'page_access':[]},id='eq.'+store.member['id'])
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

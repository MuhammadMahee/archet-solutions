"""Page grants cover navigation APIs, exports, mutations and account administration."""
import pytest
from api import index, portal
from test_portal import client, store, login, write


def restrict(store,user,pages):
    store.db('portal_users','PATCH',{'page_access':pages},id='eq.'+user['id'])


@pytest.mark.parametrize('path',[
    'sales','sales/export','quota','quota/excel','quota/template','calling-tree',
    'store-hours','store-hours/export','store-hours/history','store-hours/sheet',
    'store-hours/sheet/export','store-hours/sheet/updates','workforce/status',
    'workforce/conversations','invoices','users','quotes',
])
def test_restricted_read_routes_fail_before_loading_data(client,store,path):
    restrict(store,store.member,[]);login(client,'Member')
    assert client.get('/api/internal/'+path).status_code==403
    assert client.get('/api/internal/me').json['user']['page_access']==['settings']


@pytest.mark.parametrize('path,method',[
    ('sales/refresh','POST'),('quota/upload','POST'),('calling-tree/preview','POST'),
    ('store-hours/review','POST'),('store-hours/employees','POST'),('store-hours/rows','POST'),
    ('store-hours/schedules/apply','POST'),('store-hours/sheet/columns','POST'),
    ('store-hours/sheet/presence','POST'),('workforce/conversations','POST'),
    ('users','POST'),
])
def test_restricted_admin_cannot_bypass_with_write_api(client,store,path,method):
    restrict(store,store.admin,[]);login(client,'OtherAdmin')
    assert write(client,path,{},method).status_code==403


def test_grants_persist_and_changes_revoke_sessions(client,store):
    login(client)
    created=write(client,'users',{'username':'Scoped','display_name':'Scoped User','role':'member',
        'password':'TestPass123','page_access':['quotes','spreadsheet']})
    assert created.status_code==201
    uid=created.json['user']['id']
    other=index.app.test_client();assert login(other,'Scoped').status_code==200
    assert other.get('/api/internal/quotes').status_code==200
    assert other.get('/api/internal/sales').status_code==403
    assert write(client,'users/'+uid,{'page_access':['overview']},'PATCH').status_code==200
    assert other.get('/api/internal/me').status_code==401
    login(other,'Scoped')
    assert other.get('/api/internal/me').json['user']['page_access']==['overview','settings']
    assert other.get('/api/internal/quotes').status_code==200
    assert write(other,'quotes/'+store.member['id'],{'status':'new'},'PATCH').status_code==403


@pytest.mark.parametrize('pages',[None,'all',['bogus'],['settings'],['quotes','quotes'],[{}],['invoices']])
def test_invalid_page_grants_rejected(client,store,pages):
    login(client)
    assert write(client,'users/'+store.member['id'],{'page_access':pages},'PATCH').status_code==400


def test_owner_always_retains_access_and_members_cannot_get_accounts(client,store):
    restrict(store,store.owner,[]);login(client)
    assert client.get('/api/internal/users').status_code==200
    assert 'users' in client.get('/api/internal/me').json['user']['page_access']
    assert write(client,'users/'+store.member['id'],{'page_access':['users']},'PATCH').status_code==400
    assert write(client,'users/'+store.owner['id'],{'page_access':[]},'PATCH').status_code==403


def test_restricted_admin_cannot_grant_more_access_or_reset_broader_account(client,store):
    restrict(store,store.admin,['users','quotes']);login(client,'OtherAdmin')
    assert write(client,'users',{'username':'NewUser','display_name':'New','role':'admin',
        'password':'TestPass123','page_access':['users','sales']}).status_code==403
    assert write(client,'users/'+store.member['id'],{'password':'AnotherPass123'},'PATCH').status_code==403
    restrict(store,store.member,['quotes'])
    assert write(client,'users/'+store.member['id'],{'page_access':[]},'PATCH').status_code==200


def test_legacy_access_and_new_account_empty_access(client,store):
    login(client)
    assert set(portal.PAGE_OPTIONS)<=set(client.get('/api/internal/me').json['user']['page_access'])
    created=write(client,'users',{'username':'NoPages','display_name':'No pages','password':'TestPass123','page_access':[]})
    assert created.status_code==201 and created.json['user']['page_access']==['settings']

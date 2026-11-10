"""Page grants cover navigation APIs, exports, mutations and account administration."""
import pytest
from contextlib import nullcontext
from api import index, portal
from test_portal import client, store, login, write


def restrict(store,user,pages):
    store.db('portal_users','PATCH',{'page_access':pages},id='eq.'+user['id'])


@pytest.mark.parametrize('username',['Member','OtherAdmin'])
def test_calling_tree_is_available_even_without_assigned_pages(client,store,monkeypatch,username):
    from api import calling_tree
    target=store.member if username=='Member' else store.admin
    restrict(store,target,[]);login(client,username)
    monkeypatch.setattr(index,'sales_connect',lambda:nullcontext(None))
    monkeypatch.setattr(calling_tree,'active_roster',lambda conn:[])
    monkeypatch.setattr(calling_tree,'source_catalog',lambda conn:{})
    assert client.get('/api/internal/calling-tree').status_code==200
    if username=='Member':assert write(client,'calling-tree/preview',{}).status_code==403


@pytest.mark.parametrize('path',[
    'sales','sales/export','quota','quota/excel','quota/template',
    'store-hours','store-hours/export','store-hours/history','store-hours/sheet',
    'store-hours/sheet/export','store-hours/sheet/updates','workforce/status',
    'workforce/conversations','invoices','users','quotes','cases','cases?folder=inbox','cases/recipients','cases/unread','cases/report',
])
def test_restricted_read_routes_fail_before_loading_data(client,store,path):
    restrict(store,store.member,[]);login(client,'Member')
    assert client.get('/api/internal/'+path).status_code==403
    assert client.get('/api/internal/me').json['user']['page_access']==['callingtree','settings']


@pytest.mark.parametrize('path,method',[
    ('sales/refresh','POST'),('quota/upload','POST'),
    ('store-hours/review','POST'),('store-hours/employees','POST'),('store-hours/rows','POST'),
    ('store-hours/schedules/apply','POST'),('store-hours/sheet/columns','POST'),
    ('store-hours/sheet/presence','POST'),('workforce/conversations','POST'),
    ('users','POST'),('cases','POST'),('cases/00000000-0000-0000-0000-000000000001','PATCH'),('cases/00000000-0000-0000-0000-000000000001','DELETE'),
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
    assert other.get('/api/internal/me').json['user']['page_access']==['callingtree','overview','settings']
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
    assert created.status_code==201 and created.json['user']['page_access']==['callingtree','settings']


def test_new_pages_are_assignable_and_report_is_admin_only(client,store):
    login(client)
    catalog=client.get('/api/internal/users').json['page_options']
    assert {'cases','inbox','case-report'}<=set(catalog)
    assert write(client,'users/'+store.member['id'],{'page_access':['cases','inbox']},'PATCH').status_code==200
    assert write(client,'users/'+store.member['id'],{'page_access':['case-report']},'PATCH').status_code==400
    assert write(client,'users/'+store.admin['id'],{'page_access':['case-report']},'PATCH').status_code==200

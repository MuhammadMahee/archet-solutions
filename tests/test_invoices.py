"""Invoice permissions, exact arithmetic, persistence and concurrent updates."""
from copy import deepcopy
from uuid import uuid4

import pytest

from api import invoices
from api.supabase_store import StoreError
from test_portal import store, client, login, write  # Shared authenticated portal fixtures.


class InvoiceStore:
    def __init__(self):
        self.records = {}
        self.calls = 0

    def db(self, table, method='GET', data=None, **params):
        self.calls += 1
        if table == 'rpc/list_saved_invoices':
            records = [r for r in self.records.values()
                       if data['p_query'].lower() in r['name'].lower()
                       and (not data['p_month'] or r['month'] == data['p_month'])]
            records.sort(key=lambda r:(r['updated_at'],r['id']),reverse=True)
            return [{key:r[key] for key in ('id','name','month','updated_at')}
                    for r in records[data['p_offset']:data['p_offset']+21]]
        assert table == 'invoice_months'
        matched = [(key,r) for key,r in self.records.items()
                   if all(str(r.get(field,'')) == value[3:] for field,value in params.items() if field != 'limit')]
        if method == 'POST':
            if any(r['id'] == data['id'] or (data.get('legacy_month') and r.get('legacy_month') == data['legacy_month']) for r in self.records.values()):
                raise StoreError(409, '23505')
            self.records[data.get('legacy_month') or data['id']] = deepcopy(data)
            return [deepcopy(data)]
        elif method == 'PATCH':
            if not matched:
                return []
            key, existing = matched[0]
            self.records[key].update(deepcopy(data))
            return [deepcopy(self.records[key])]
        return [deepcopy(r) for _,r in matched][:int(params.get('limit',1000))]


@pytest.fixture
def ledger(monkeypatch):
    fake = InvoiceStore()
    monkeypatch.setattr(invoices, 'db', fake.db)
    return fake


def row(**changes):
    return {'dealer':'Connect', 'market':'Dallas', 'store_count':1, 'amount_cents':10010,
            'advance_cents':3010, 'remark':'Pay balance next month', **changes}


def save(client, rows=None, revision=None, month='2026-09'):
    return write(client, 'invoices/' + month, {'rows': [row()] if rows is None else rows, 'revision': revision}, 'PUT')


@pytest.mark.parametrize('username', [None, 'Member', 'OtherAdmin'])
def test_only_mahee_can_read_or_write(client, ledger, username):
    if username:
        login(client, username)
    expected = 403 if username else 401
    assert client.get('/api/internal/invoices/2026-09').status_code == expected
    assert save(client).status_code == expected
    assert ledger.calls == 0


def test_name_and_owner_both_required(client, store, ledger):
    store.owner['is_owner'] = False
    # FakeStore returns copies; update the persisted account explicitly.
    store.db('portal_users', 'PATCH', {'is_owner':False}, id='eq.' + store.owner['id'])
    login(client)
    assert save(client).status_code == 403
    store.db('portal_users', 'PATCH', {'is_owner':True}, id='eq.' + store.admin['id'])
    login(client, 'OtherAdmin')
    assert save(client).status_code == 403
    assert ledger.calls == 0


def test_save_reload_update_and_separate_months(client, ledger):
    login(client)
    empty = client.get('/api/internal/invoices/2026-09').json['invoice']
    assert empty['rows'] == [] and empty['revision'] is None
    result = save(client)
    assert result.status_code == 200
    invoice = result.json['invoice']
    assert invoice['totals'] == {'amount_cents':10010,'advance_cents':3010,'balance_cents':7000}
    assert invoice['balance_month'] == '2026-10'
    assert client.get('/api/internal/invoices/2026-09').json['invoice'] == invoice
    edited = save(client, [row(amount_cents=12010)], invoice['revision']).json['invoice']
    assert edited['totals']['balance_cents'] == 9000
    assert edited['revision'] != invoice['revision']
    december = save(client, month='2026-12').json['invoice']
    assert december['balance_month'] == '2027-01'
    assert len(ledger.records) == 2
    cleared = save(client, [], edited['revision'])
    assert cleared.json['invoice']['totals']['balance_cents'] == 0


def test_stale_revision_and_duplicate_create_do_not_overwrite(client, ledger):
    login(client)
    first = save(client).json['invoice']
    latest = save(client, [row(amount_cents=12000)], first['revision']).json['invoice']
    assert save(client, [row(amount_cents=1)], first['revision']).status_code == 409
    assert save(client).status_code == 409
    assert ledger.records['2026-09']['revision'] == latest['revision']


@pytest.mark.parametrize('value', [-1, 1.1, True, '100', None, 100000000000])
@pytest.mark.parametrize('field', ['amount_cents', 'advance_cents'])
def test_invalid_amounts_rejected(client, ledger, field, value):
    login(client)
    assert save(client, [row(**{field:value})]).status_code == 400
    assert not ledger.records


@pytest.mark.parametrize('rows', [None, {}, ['oops'], [row(market=' ')], [row(dealer='')],
    [row(remark='a'*501)], [row(), row(market=' DALLAS ')], [row()]*101])
def test_invalid_rows_rejected(client, ledger, rows):
    login(client)
    assert write(client,'invoices/2026-09',{'rows':rows},'PUT').status_code == 400


@pytest.mark.parametrize('month', ['2026-13', '2026-1', '1999-12', 'bad', '2026-00'])
def test_invalid_months(client, ledger, month):
    login(client)
    assert client.get('/api/internal/invoices/' + month).status_code == 400
    assert save(client, month=month).status_code == 400


def test_credit_balance_and_server_computation(client, ledger):
    login(client)
    result = save(client, [row(amount_cents=10,advance_cents=30,balance_cents=999), row(dealer='ARBF')])
    invoice = result.json['invoice']
    assert invoice['rows'][0]['balance_cents'] == -20
    assert 'balance_cents' not in ledger.records['2026-09']['rows'][0]


def test_host_csrf_revoked_and_rest_sessions(client, store, ledger):
    login(client)
    assert client.put('/api/internal/invoices/2026-09', json={'rows':[]}).status_code == 403
    assert client.get('/api/internal/invoices/2026-09', base_url='https://archetsolutions.com').status_code == 404
    store.db('portal_users','PATCH',{'rest_mode':True},id='eq.' + store.owner['id'])
    assert save(client).json['code'] == 'account_rest'
    store.db('portal_users','PATCH',{'active':False},id='eq.' + store.owner['id'])
    assert save(client).status_code == 401
    assert ledger.calls == 0


def test_upstream_failure_is_not_reported_as_save_success(client, ledger, monkeypatch):
    login(client)
    def unavailable(*args, **kwargs):
        raise StoreError()
    monkeypatch.setattr(invoices, 'db', unavailable)
    assert save(client).status_code == 503


@pytest.mark.parametrize('revision', [123, [], {}, True, 'bad'])
def test_invalid_revision_returns_validation_error(client, ledger, revision):
    login(client)
    assert save(client, revision=revision).status_code == 400


def test_store_count_multiplies_rate_before_deducting_advance(client, ledger):
    login(client)
    result = save(client, [row(store_count=5, amount_cents=250005, advance_cents=400010,
                               subtotal_cents=1, balance_cents=1),
                           row(market='Austin', store_count=2, amount_cents=160000, advance_cents=400000)])
    assert result.status_code == 200
    invoice = result.json['invoice']
    assert invoice['rows'][0]['subtotal_cents'] == 1250025
    assert invoice['rows'][0]['balance_cents'] == 850015
    assert invoice['rows'][1]['balance_cents'] == -80000
    assert invoice['totals'] == {'amount_cents':1570025, 'advance_cents':800010, 'balance_cents':770015}
    assert client.get('/api/internal/invoices/2026-09').json['invoice'] == invoice
    assert ledger.records['2026-09']['rows'][0]['store_count'] == 5
    assert 'subtotal_cents' not in ledger.records['2026-09']['rows'][0]


@pytest.mark.parametrize('count', [0, -1, 1.5, True, '5', None, 10001])
def test_invalid_store_counts(client, ledger, count):
    login(client)
    assert save(client, [row(store_count=count)]).status_code == 400
    assert not ledger.records


def test_subtotal_limit_keeps_cent_arithmetic_exact(client, ledger):
    login(client)
    assert save(client, [row(store_count=10000, amount_cents=99999999999)]).status_code == 400
    assert save(client, [row(store_count=10000, amount_cents=1)]).json['invoice']['rows'][0]['subtotal_cents'] == 10000


def test_legacy_invoice_defaults_to_one_store_without_changing_totals(client, ledger):
    login(client)
    save(client)
    del ledger.records['2026-09']['rows'][0]['store_count']
    invoice = client.get('/api/internal/invoices/2026-09').json['invoice']
    assert invoice['rows'][0]['store_count'] == 1
    assert invoice['rows'][0]['balance_cents'] == 7000
    assert save(client, invoice['rows'], invoice['revision']).status_code == 200
    assert ledger.records['2026-09']['rows'][0]['store_count'] == 1


def save_named(client, name='Connect September', uid=None, revision=None, month='2026-09'):
    return write(client, 'invoices/' + (uid or str(uuid4())),
                 {'name':name,'month':month,'rows':[row(store_count=3)],'revision':revision}, 'PUT')


def test_multiple_named_invoices_same_month_and_rename(client, ledger):
    login(client)
    first = save_named(client).json['invoice']
    second = save_named(client, 'ARBF September').json['invoice']
    assert first['id'] != second['id'] and len(ledger.records) == 2
    updated = save_named(client, 'Connect revised', first['id'], first['revision'], '2026-10').json['invoice']
    assert len(ledger.records) == 2
    assert updated['name'] == 'Connect revised' and updated['month'] == '2026-10'
    assert client.get('/api/internal/invoices/' + first['id']).json['invoice'] == updated
    assert client.get('/api/internal/invoices/' + second['id']).json['invoice'] == second
    assert save_named(client, uid=first['id'],revision=first['revision']).status_code == 409
    assert save_named(client, uid=first['id']).status_code == 409


def test_search_by_name_month_and_paginate(client, ledger):
    login(client)
    for i in range(22):
        save_named(client, f'Connect {i:02}')
    save_named(client, 'ARBF October',month='2026-10')
    page1 = client.get('/api/internal/invoices?q=connect').json
    page2 = client.get('/api/internal/invoices?q=CONNECT&offset=20').json
    assert len(page1['invoices']) == 20 and page1['has_more']
    assert len(page2['invoices']) == 2 and not page2['has_more']
    assert not {i['id'] for i in page1['invoices']} & {i['id'] for i in page2['invoices']}
    assert all('rows' not in i for i in page1['invoices'])
    assert client.get('/api/internal/invoices?q=Connect&month=2026-10').json['invoices'] == []
    assert len(client.get('/api/internal/invoices?month=2026-10').json['invoices']) == 1


def test_old_monthly_invoices_visible_and_editable_in_library(client, ledger):
    login(client)
    original = save(client).json['invoice']
    listed = client.get('/api/internal/invoices').json['invoices']
    assert listed[0]['id'] == original['id']
    updated = save_named(client,'Old invoice renamed',original['id'],original['revision']).json['invoice']
    assert len(ledger.records) == 1 and updated['id'] == original['id']
    assert client.get('/api/internal/invoices/2026-09').json['invoice']['name'] == 'Old invoice renamed'


@pytest.mark.parametrize('name', ['', '   ', 'x'*121, None, 123])
def test_invalid_names(client, ledger, name):
    login(client)
    assert save_named(client,name).status_code == 400
    assert not ledger.records


@pytest.mark.parametrize('username', [None,'Member','OtherAdmin'])
def test_library_and_named_invoice_access_is_mahee_only(client, ledger, username):
    if username:
        login(client,username)
    status = 403 if username else 401
    assert client.get('/api/internal/invoices').status_code == status
    assert client.get('/api/internal/invoices/' + str(uuid4())).status_code == status
    assert save_named(client).status_code == status
    assert ledger.calls == 0


def test_library_validation_and_missing_invoice(client, ledger):
    login(client)
    for query in ('offset=-1','offset=abc','month=2026-13','q=' + 'x'*121):
        assert client.get('/api/internal/invoices?' + query).status_code == 400
    assert client.get('/api/internal/invoices/' + str(uuid4())).status_code == 404
    assert save_named(client,month=None).status_code == 400


@pytest.mark.parametrize('month,days,rate,expected', [
    ('2026-09',15,30000,15000), ('2026-09',30,30000,30000),
    ('2026-10',15,31000,15000), ('2026-10',31,31000,31000),
    ('2026-02',14,28000,14000), ('2026-02',28,28000,28000),
    ('2028-02',14,29000,14000), ('2028-02',29,29000,29000),
    ('2026-09',0,30000,0), ('2026-09',15,1,1),
    ('2026-10',1,100,3), ('2026-10',16,1,1),
])
def test_prorated_potential_pay_uses_actual_calendar_month(client, ledger, month, days, rate, expected):
    login(client)
    result = save(client,[row(days_worked=days,amount_cents=rate,advance_cents=0)],month=month)
    assert result.status_code == 200
    invoice = result.json['invoice']
    assert invoice['rows'][0]['potential_pay_cents'] == expected
    assert invoice['totals']['amount_cents'] == expected
    assert invoice['rows'][0]['days_worked'] == days


def test_invoice_advance_deducted_once_and_summary_remark_persists(client, ledger):
    login(client)
    uid = str(uuid4())
    data = {'name':'Partial month','month':'2026-09','rows':[
        row(store_count=5,amount_cents=250005,days_worked=15,advance_cents=0),
        row(market='Austin',amount_cents=10000,days_worked=30,advance_cents=0)],
        'advance_cents':20000,'remark':'Advance received by bank transfer.'}
    result = write(client,'invoices/' + uid,data,'PUT')
    assert result.status_code == 200
    invoice = result.json['invoice']
    assert invoice['totals'] == {'amount_cents':635013,'advance_cents':20000,'balance_cents':615013}
    assert invoice['remark'] == data['remark']
    assert client.get('/api/internal/invoices/' + uid).json['invoice'] == invoice
    data.update(revision=invoice['revision'],advance_cents=700000)
    assert write(client,'invoices/' + uid,data,'PUT').json['invoice']['totals']['balance_cents'] == -64987


@pytest.mark.parametrize('days', [-1,31,1.5,True,'15',None])
def test_invalid_days_worked(client, ledger, days):
    login(client)
    assert save(client,[row(days_worked=days)]).status_code == 400
    assert not ledger.records


def test_days_exceeding_february_rejected_and_each_line_rounded_once(client, ledger):
    login(client)
    assert save(client,[row(days_worked=29)],month='2026-02').status_code == 400
    assert save(client,[row(days_worked=30)],month='2028-02').status_code == 400
    result = save(client,[row(amount_cents=1,days_worked=15,advance_cents=0),
                          row(market='Austin',amount_cents=1,days_worked=15,advance_cents=0)])
    assert result.json['invoice']['totals']['amount_cents'] == 2


@pytest.mark.parametrize('advance', [-1,True,None,'500',1.1,10000000000000])
def test_invalid_invoice_advance(client, ledger, advance):
    login(client)
    assert write(client,'invoices/' + str(uuid4()),{'name':'Bad advance','month':'2026-09',
        'rows':[row()], 'advance_cents':advance},'PUT').status_code == 400


def test_old_invoice_defaults_full_month_and_combines_advances(client, ledger):
    login(client)
    invoice = save(client,[row(advance_cents=1000),row(market='Austin',advance_cents=2000)]).json['invoice']
    old = ledger.records['2026-09']
    old.pop('advance_cents'); old.pop('remark')
    for item in old['rows']:
        item.pop('days_worked')
    result = client.get('/api/internal/invoices/2026-09').json['invoice']
    assert result['totals'] == invoice['totals']
    assert result['advance_cents'] == 3000 and result['remark'] == ''
    assert all(r['days_worked'] == 30 for r in result['rows'])
    # The new editor moves the advance to the footer without deducting it twice.
    for item in result['rows']:
        item.pop('advance_cents')
    result['name'] = 'Migrated invoice'
    saved = write(client,'invoices/' + result['id'],result,'PUT').json['invoice']
    assert saved['totals'] == invoice['totals']

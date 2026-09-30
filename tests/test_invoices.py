"""Invoice permissions, exact arithmetic, persistence and concurrent updates."""
from copy import deepcopy

import pytest

from api import invoices
from api.supabase_store import StoreError
from test_portal import store, client, login, write  # Shared authenticated portal fixtures.


class InvoiceStore:
    def __init__(self):
        self.records = {}
        self.calls = 0

    def db(self, table, method='GET', data=None, **params):
        assert table == 'invoice_months'
        self.calls += 1
        month = data['month'] if data else params['month'][3:]
        existing = self.records.get(month)
        if method == 'POST':
            if existing:
                raise StoreError(409, '23505')
            self.records[month] = deepcopy(data)
        elif method == 'PATCH':
            if not existing or params['revision'] != 'eq.' + existing['revision']:
                return []
            self.records[month] = deepcopy(data)
        result = self.records.get(month)
        return [deepcopy(result)] if result else []


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

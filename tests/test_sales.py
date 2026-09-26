from datetime import date
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from contextlib import nullcontext

import pytest
from openpyxl import load_workbook

from api import index, sales
from test_portal import store, client, login, write


def row(source='arm1', day=date(2026, 9, 1), sid='S1', **changes):
    return {'source_id': source, 'report_date': day, 'store_id': sid,
            'market': 'MARKET', 'store': 'STORE', 'stale': False,
            **{k: 0 for k in sales.METRICS}, **changes}


def test_arm_overlap_is_not_double_counted_and_dealers_stay_separate():
    rows = [row(new_activation=2, total_boxes=2, accessory=Decimal('50'), qpay=4),
            row('arm2', new_activation=99, total_boxes=99),
            row('connect', new_activation=3, total_boxes=3),
            row(day=date(2026, 9, 2), total_boxes=1, accessory=Decimal('10'), qpay=2)]
    result = sales.aggregate(rows)
    arm = next(r for r in result if r['dealer'] == 'ARM')
    assert arm['total_boxes'] == 3
    assert arm['apo'] == Decimal('20.00')
    assert arm['qpay_conv'] == Decimal('50.00')
    assert len(result) == 2


def test_fresh_arm_copy_wins_over_retained_copy():
    result = sales.aggregate([row(stale=True, total_boxes=5), row('arm2', total_boxes=3)])
    assert result[0]['total_boxes'] == 3
    assert result[0]['stale'] is False


def test_zero_denominators_and_half_up_rounding():
    assert sales.ratios({'accessory': Decimal('1.005'), 'total_boxes': 1, 'qpay': 0})['apo'] == Decimal('1.01')
    assert sales.ratios({'accessory': 0, 'total_boxes': 0, 'qpay': 0})['qpay_conv'] == 0


@pytest.mark.parametrize('value', ['NaN', 'Infinity', 'wrong'])
def test_bad_numeric_values_reject_whole_report(value):
    with pytest.raises(sales.ReportError):
        sales.number(value)


def test_new_account_sessions_discard_shared_fw_cookie(monkeypatch):
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return b'<input name="frmStart"><input name="frmEnd">'
    class Opener:
        def open(self, *args, **kwargs): return Response()
    def opener(*handlers):
        captured.extend(list(handlers[1].cookiejar))
        return Opener()
    monkeypatch.setattr(sales, 'build_opener', opener)
    sales.open_source({'FW_SessionID':'SHARED', 'sec85952EAF_id':'user', 'sec85952EAF_pd':'secret'})
    assert {c.name for c in captured} == {'sec85952EAF_id', 'sec85952EAF_pd'}
    assert all(c.secure and c.domain == 'myrtpos.com' for c in captured)


def test_redirect_cannot_send_cookie_to_unrelated_host():
    with pytest.raises(sales.ReportError):
        sales.SameHostRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com/')


@pytest.mark.parametrize('path', ['sales', 'sales/export'])
def test_reports_require_login(client, path):
    assert client.get('/api/internal/' + path).status_code == 401


def test_member_can_read_but_only_admin_can_refresh(client, monkeypatch):
    monkeypatch.setattr(sales, 'report_data', lambda *args: {'rows': []})
    monkeypatch.setattr(sales, 'run_batch', lambda: {'status': 'complete'})
    login(client, 'Member')
    assert client.get('/api/internal/sales').status_code == 200
    assert write(client, 'sales/refresh', {}).status_code == 403
    login(client)
    assert write(client, 'sales/refresh', {}).status_code == 200
    assert client.post('/api/internal/sales/refresh', json={}).status_code == 403


def test_scheduler_fails_closed_and_blocks_preview(client, monkeypatch):
    monkeypatch.setattr(sales, 'run_batch', lambda: {'status': 'complete'})
    monkeypatch.delenv('CRON_SECRET', raising=False)
    assert client.post('/api/jobs/sales').status_code == 401
    monkeypatch.setenv('CRON_SECRET', 'test-secret')
    assert client.post('/api/jobs/sales', headers={'Authorization':'Bearer wrong'}).status_code == 401
    h = {'Authorization': 'Bearer test-secret'}
    assert client.post('/api/jobs/sales', headers=h).status_code == 200
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    assert client.post('/api/jobs/sales', headers=h).status_code == 403


@pytest.mark.parametrize('query', ['start=invalid', 'start=2026-01-01&end=2026-05-01', 'start=2099-01-01', 'start=2026-09-20&end=2026-09-01'])
def test_invalid_ranges_are_rejected_before_database(client, query):
    login(client)
    assert client.get('/api/internal/sales?' + query).status_code == 400


def test_six_workers_actually_start_together(monkeypatch):
    barrier = Barrier(6, timeout=5)
    calls = []
    class Result:
        def __init__(self, value): self.value = value
        def fetchone(self): return self.value
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, *args):
            if 'try_advisory' in sql: return Result({'locked':True})
            return Result({'remaining':0,'due':0,'failed':0})
    def worker(source, cookies, current):
        calls.append(source)
        barrier.wait()
        return {'source':source,'completed':1,'failed':0}
    monkeypatch.setattr(sales, 'connect', Conn)
    monkeypatch.setattr(sales, 'seed_jobs', lambda *args: None)
    monkeypatch.setattr(sales, 'source_worker', worker)
    assert sales.run_batch()['status'] == 'complete'
    assert set(calls) == set(sales.SOURCES)


def test_busy_lock_does_not_start_downloads(monkeypatch):
    class Result:
        def fetchone(self): return {'locked':False}
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): return Result()
    monkeypatch.setattr(sales, 'connect', Conn)
    monkeypatch.setattr(sales, 'source_worker', lambda *args: pytest.fail('must not download'))
    assert sales.run_batch()['status'] == 'busy'


def test_xlsx_keeps_dealer_and_blocks_formula_injection():
    rows = sales.aggregate([row(store='=HYPERLINK("https://example.com")', total_boxes=2, accessory=Decimal('40'),qpay=4)])
    data = {'rows':rows,'totals':rows[0], 'start':'2026-09-01','end':'2026-09-01',
            'coverage':{'complete':6,'expected':6,'retained':0},'updated_at':None}
    book = load_workbook(sales.workbook_bytes(data))
    sheet = book.active
    assert sheet.cell(1,1).value == 'Dealer'
    assert sheet.cell(2,1).value == 'ARM'
    assert sheet.cell(2,3).data_type == 's'
    assert sheet.cell(2,10).value == 20
    assert sheet.cell(2,13).value == 50


def test_parser_accepts_unassigned_market_and_rejects_duplicate_store(monkeypatch):
    headers=['custno','company','marketid','newact','upgsor','reactact','totact','totaccessory','totpaymentqty','iot','hint']
    values=['S1','Store','',2,1,0,3,60,6,2,1]
    class Sheet:
        nrows=2
        def row_values(self, i):return headers
        def cell_value(self, r, c):return values[c]
    class Book:
        def sheet_by_index(self, i):return Sheet()
    monkeypatch.setattr(sales.xlrd,'open_workbook',lambda **kw:Book())
    result=sales.read_xls(b'dummy')
    assert result[0]['market']=='UNASSIGNED'
    assert result[0]['bts']==1
    Sheet.nrows=3
    with pytest.raises(sales.ReportError,match='duplicate_store'):
        sales.read_xls(b'dummy')

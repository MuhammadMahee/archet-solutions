"""Retirement must affect portal results, exports, and sync without deleting history."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO

from openpyxl import load_workbook
from api import calling_tree, index, quota, sales, store_hours_directory
from test_sales import row
from test_portal import store, client, login, write


DAY = date(2026, 10, 1)


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return deepcopy(self.rows)


class ReadDB:
    def __init__(self):
        self.roster = [dict(dealer=d, store_id='S1', market='CHICAGO', store=d + ' STORE',
                            filename='roster.xlsx', version_id='v1', worksheet='Stores',
                            activated_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
                       for d in ('AMQ', 'ARM')]
        self.raw = [row(source='arm1', day=DAY, total_boxes=100), row(source='arm2', day=DAY, total_boxes=2)]
        self.imports = [dict(source_id=s, report_date=DAY, status='complete' if s != 'arm1' else 'error',
                             loaded_at=datetime(2026, 10, 1, tzinfo=timezone.utc), retained_count=0)
                        for s in sales.SOURCES]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def transaction(self): return nullcontext()
    def execute(self, sql, args=None):
        if 'SET TRANSACTION' in sql: return Result([])
        if 'quota_uploads' in sql:
            return Result([dict(dealer=d, goal_month=DAY, filename=d+'.xlsx', row_count=1,
                                uploaded_at=datetime(2026,10,1,tzinfo=timezone.utc)) for d in ('AMQ','ARM')])
        if 'quota_goals' in sql:
            return Result([{**s, **{k:10 for k in quota.GOALS}} for s in self.roster])
        if 'calling_tree_stores' in sql: return Result(self.roster)
        if 'store_hours_directory' in sql:
            return Result([{**s, 'source_id':'arm1' if s['dealer']=='AMQ' else 'arm2',
                            'schedules':{}, 'company':s['dealer']} for s in self.roster])
        if 'select distinct source_id,store_id' in sql: return Result(self.raw)
        if 'sales_performance p' in sql: return Result(self.raw)
        if 'sales_imports' in sql: return Result(self.imports)
        raise AssertionError(sql)


def test_roster_and_schedule_directory_exclude_amq_without_deleting_history():
    db = ReadDB()
    before = deepcopy(db.roster)
    assert [s['dealer'] for s in calling_tree.active_roster(db)] == ['ARM']
    assert [s['dealer'] for s in store_hours_directory.roster_with_schedules(db)] == ['ARM']
    assert db.roster == before


def test_sales_totals_coverage_filters_and_export_exclude_amq(monkeypatch):
    db = ReadDB()
    monkeypatch.setattr(sales, 'connect', lambda: db)
    with index.app.test_request_context('/api/internal/sales'):
        report = sales.report_data(DAY, DAY)
    assert [r['dealer'] for r in report['rows']] == ['ARM']
    assert report['totals']['total_boxes'] == 2
    assert report['coverage']['complete'] == report['coverage']['expected'] == 5
    assert report['coverage']['errors'] == []
    assert 'AMQ' not in [d['name'] for d in report['dealers']]
    assert report['stores'] == [{'id':'ARM:S1', 'name':'ARM STORE'}]
    sheet = load_workbook(BytesIO(sales.workbook_bytes(report).getvalue())).active
    assert sheet.cell(2, 1).value == 'ARM'
    assert all(cell.value != 'AMQ' for cells in sheet for cell in cells)
    assert len(db.raw) == 2


def test_quota_upload_history_goals_and_totals_exclude_amq(monkeypatch):
    monkeypatch.setattr(sales, 'connect', ReadDB)
    monkeypatch.setattr(sales, 'today', lambda: DAY)
    with index.app.test_request_context('/api/internal/quota?month=2026-10'):
        report = quota.report_data()
    assert report['count'] == 1
    assert report['dealers'] == list(sales.COLORS)
    assert [u['dealer'] for u in report['uploads']] == ['ARM']
    assert all(r['dealer'] == 'ARM' for t in report['tables'] for r in t['rows'])


def test_retired_filters_rejected_and_assets_served(client, monkeypatch):
    monkeypatch.setattr(sales, 'connect', ReadDB)
    login(client)
    for endpoint in ('sales?dealer=AMQ', 'sales/export?dealer=AMQ', 'quota?dealer=AMQ', 'quota/template?dealer=AMQ'):
        assert client.get('/api/internal/' + endpoint).status_code == 400
    assert write(client, 'quota/upload', {'dealer':'AMQ'}).status_code == 400
    for asset in ('portal-design.css','sheet-design.css'):
        assert client.get('/assets/' + asset).status_code == 200


def test_only_active_sources_get_new_sync_jobs():
    inserted = []
    class DB:
        def transaction(self): return nullcontext()
        def cursor(self): return nullcontext(self)
        def executemany(self, sql, rows): inserted.extend(rows)
        def execute(self, *args): pass
    sales.seed_jobs(DB(), DAY)
    assert {r[0] for r in inserted} == {'connect','california','srh','arm2','arbf'}
    assert sales.SOURCES['arm1'] == 'AMQ'  # Archived source records still resolve.

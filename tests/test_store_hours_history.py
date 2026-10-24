from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from api import index, store_hours as sh
from api.portal import PortalError
from test_portal import client, store, login, write


def test_history_requires_login_and_has_no_mutation_endpoint(client, monkeypatch):
    assert client.get('/api/internal/store-hours/history').status_code == 401
    login(client, 'Member')
    monkeypatch.setattr(sh, 'version_history', lambda *args: {'versions': [], 'next_cursor': None})
    assert client.get('/api/internal/store-hours/history').status_code == 200
    for method in ('POST', 'PATCH', 'PUT', 'DELETE'):
        assert write(client, 'store-hours/history', {}, method=method).status_code == 405
    login(client)
    assert write(client, 'store-hours/history', {}, method='DELETE').status_code == 405


@pytest.mark.parametrize('query', ['before=-1', 'before=no', 'before=0', 'before=9223372036854775808', 'store=invalid'])
def test_history_rejects_bad_cursor_or_store(query):
    with index.app.test_request_context('/api/internal/store-hours/history?'+query):
        with pytest.raises(PortalError):
            sh.version_history(date(2026, 10, 20), date(2026, 10, 20))


def test_history_paginates_without_joining_mutable_source_rows(monkeypatch):
    calls = []
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    records = [dict(id=n, transaction_id=8, recorded_at=now, report_date=None, kind='schedule',
                    actor_name='Original employee', before_data=None, after_data={'company': 'Connect'}) for n in range(100, 49, -1)]

    class DB:
        def execute(self, sql, args=None):
            calls.append((sql, args))
            return SimpleNamespace(fetchall=lambda: records, fetchone=lambda: {'started': now})

    monkeypatch.setattr(sh, 'connect', lambda: nullcontext(DB()))
    with index.app.test_request_context('/api/internal/store-hours/history?dealer=Connect&store=Connect:1&market=HOUSTON&before=101&search=Jane'):
        result = sh.version_history(date(2026, 10, 20), date(2026, 10, 21))
    assert len(result['versions']) == 50 and result['next_cursor'] == '51'
    assert result['versions'][0]['id'] == '100'
    assert result['versions'][0]['recorded_at'] == now.isoformat()
    sql, args = calls[0]
    assert 'report_date is null' in sql and 'id<%s' in sql and 'limit 51' in sql
    assert 'join' not in sql.lower()
    assert args[-1] == 101 and 'Jane' in args

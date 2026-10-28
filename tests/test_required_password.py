"""Required password changes cannot be bypassed through roles or direct APIs."""
import pytest
from contextlib import contextmanager
from api import index, portal
from api.supabase_store import StoreError
from test_portal import store, client, login, write


def force(store, user):
    store.db('portal_users', 'PATCH', {'must_change_password': True}, id='eq.' + user['id'])


@pytest.mark.parametrize('username', ['Mahee', 'OtherAdmin', 'Member'])
def test_every_role_must_reset_before_data_access(client, store, username):
    user = next(u for u in store.tables['portal_users'] if u['username'] == username)
    force(store, user)
    assert login(client, username).json['user']['must_change_password'] is True
    assert client.get('/api/internal/me').json['user']['must_change_password'] is True
    for path in ['users', 'quotes', 'store-hours', 'sales']:
        response = client.get('/api/internal/' + path)
        assert response.status_code == 403, path
        assert response.json['code'] == 'password_change_required'
    assert write(client, 'store-hours/review', {}).json['code'] == 'password_change_required'
    assert write(client, 'logout', {}).status_code == 200


@pytest.mark.parametrize('current,new', [('wrong', 'ChangedPass456'), ('TestPass123', 'TestPass123'), ('TestPass123', 'short')])
def test_failed_reset_keeps_gate(client, store, current, new):
    force(store, store.member)
    login(client, 'Member')
    response = write(client, 'password', {'current_password': current, 'new_password': new})
    assert response.status_code in (400, 403)
    assert client.get('/api/internal/me').json['user']['must_change_password'] is True


@pytest.mark.parametrize('rest', [False, True])
def test_success_clears_gate_revokes_sessions_and_preserves_rest(client, store, rest):
    force(store, store.member)
    store.db('portal_users', 'PATCH', {'rest_mode': rest}, id='eq.' + store.member['id'])
    second = index.app.test_client()
    login(client, 'Member'); login(second, 'Member')
    response = write(client, 'password', {'current_password': 'TestPass123', 'new_password': 'ChangedPass456'})
    assert response.status_code == 200
    assert client.get('/api/internal/me').status_code == 401
    assert second.get('/api/internal/me').status_code == 401
    assert login(client, 'Member').status_code == 401
    response = login(client, 'Member', password='ChangedPass456')
    assert response.status_code == 200
    assert response.json['user']['must_change_password'] is False
    assert response.json['user']['rest_mode'] is rest
    assert store.password_values[store.member['id']] == 'ChangedPass456'
    if rest:
        assert client.get('/api/internal/quotes').json['code'] == 'account_rest'


def test_vault_failure_does_not_clear_requirement(client, store, monkeypatch):
    force(store, store.member)
    login(client, 'Member')
    @contextmanager
    def fail(uid):
        yield lambda password: None
        raise StoreError()
    monkeypatch.setattr(portal, 'password_write', fail)
    assert write(client, 'password', {'current_password': 'TestPass123', 'new_password': 'ChangedPass456'}).status_code == 503
    assert login(client, 'Member', password='ChangedPass456').json['user']['must_change_password'] is True


def test_inflight_normal_change_cannot_clear_new_requirement(client, store, monkeypatch):
    login(client, 'Member')
    @contextmanager
    def concurrent_reset(uid):
        force(store, store.member)
        yield lambda password: None
    monkeypatch.setattr(portal, 'password_write', concurrent_reset)
    assert write(client, 'password', {'current_password': 'TestPass123', 'new_password': 'ChangedPass456'}).status_code == 200
    assert login(client, 'Member', password='ChangedPass456').json['user']['must_change_password'] is True


def test_disabled_account_stays_disabled(client, store):
    force(store, store.member)
    store.db('portal_users', 'PATCH', {'active': False}, id='eq.' + store.member['id'])
    assert login(client, 'Member').status_code == 401

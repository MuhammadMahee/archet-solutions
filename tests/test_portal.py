"""Security and persistence behavior, with Supabase isolated at its boundary."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api import index, portal
from api.supabase_store import StoreError


class FakeStore:
    def __init__(self):
        self.tables = {name: [] for name in ("portal_users", "portal_sessions", "quote_requests")}
        self.auth_users = {}
        self.rate_allowed = True
        self.unavailable = False
        self.owner = self.add_user("Mahee", "admin", owner=True)
        self.member = self.add_user("Member", "member")
        self.admin = self.add_user("OtherAdmin", "admin")

    def add_user(self, username, role, owner=False):
        uid = str(uuid4())
        self.auth_users[portal.login_email(username)] = {"id": uid, "password": "TestPass123"}
        return self.db("portal_users", "POST", {"id": uid, "username": username,
            "display_name": username, "role": role, "is_owner": owner})[0]

    def db(self, table, method="GET", data=None, **params):
        if self.unavailable:
            raise StoreError()
        if table == "rpc/portal_check_rate":
            return self.rate_allowed
        rows = self.tables[table]
        if method == "POST":
            row = {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **deepcopy(data)}
            if table == "portal_users":
                row = {"active": True, "is_owner": False, "role": "member", "session_version": str(uuid4()), **row}
                row["username_key"] = row["username"].lower()
            if table == "quote_requests":
                row = {"status": "new", "notes": "", "notification_status": "pending", **row}
            rows.append(row)
            return [deepcopy(row)]
        def matches(row):
            for key, value in params.items():
                if key in ("select", "order", "limit", "offset"):
                    continue
                operator, expected = value.split(".", 1)
                actual = str(row.get(key, ""))
                if operator == "eq" and actual != expected:
                    return False
                if operator == "gt" and actual <= expected:
                    return False
            return True
        matched = [row for row in rows if matches(row)]
        if method == "PATCH":
            for row in matched:
                row.update(deepcopy(data))
        if method == "DELETE":
            self.tables[table] = [row for row in rows if not matches(row)]
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", len(matched)))
        result = deepcopy(matched[offset:offset + limit])
        if "select" in params:
            result = [{key: row[key] for key in params["select"].split(",")} for row in result]
        return result

    def auth(self, path, method="POST", data=None, **params):
        if self.unavailable:
            raise StoreError()
        if path == "token":
            user = self.auth_users.get(data["email"])
            if not user or data["password"] != user["password"]:
                raise StoreError(400, "invalid_credentials")
            return {"user": {"id": user["id"]}, "access_token": "should-never-reach-browser"}
        if path == "admin/users":
            if data["email"] in self.auth_users:
                raise StoreError(422, "email_exists")
            user = {"id": str(uuid4()), "password": data["password"]}
            self.auth_users[data["email"]] = user
            return deepcopy(user)
        uid = path.split("/")[-1]
        email = next(email for email, user in self.auth_users.items() if user["id"] == uid)
        if method == "DELETE":
            del self.auth_users[email]
            return None
        self.auth_users[email].update(data)
        return deepcopy(self.auth_users[email])


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    fake = FakeStore()
    monkeypatch.setattr(portal, "db", fake.db)
    monkeypatch.setattr(portal, "auth", fake.auth)
    monkeypatch.setattr(index, "db", fake.db)
    monkeypatch.setattr(index, "send_lead_notification", lambda record: None)
    monkeypatch.setattr(index, "send_confirmation_email", lambda *args: None)
    index.app.config["TESTING"] = True
    return fake


@pytest.fixture
def client(store):
    return index.app.test_client()


def write(client, path, data, method="POST", base_url="http://localhost"):
    return client.open("/api/internal/" + path, method=method, json=data, base_url=base_url,
        headers={"Origin": base_url, "X-Archet-Request": "1"})


def login(client, username="Mahee", **extra):
    return write(client, "login", {"username": username, "password": "TestPass123", **extra})


def test_host_routing_and_private_robots(client):
    assert b"Operations Intelligence" in client.get("/").data
    assert b"Internal Workspace" in client.get("/", base_url="https://internal.archetsolutions.com").data
    assert b"Internal Workspace" in client.get("/internal").data
    assert client.get("/internal", base_url="https://archetsolutions.com").location == "https://internal.archetsolutions.com"
    assert client.get("/api/internal/me", base_url="https://archetsolutions.com").status_code == 404
    response = client.get("/robots.txt", base_url="https://internal.archetsolutions.com")
    assert b"Disallow: /" in response.data
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.parametrize("path", ["me", "users", "quotes"])
def test_anonymous_cannot_read_private_data(client, path):
    assert client.get("/api/internal/" + path).status_code == 401


def test_login_cookie_and_case_insensitive_username(client, store):
    response = login(client, "mAhEe", remember=True)
    assert response.status_code == 200
    assert response.json["user"]["is_owner"]
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Max-Age=2592000" in cookie
    assert "access_token" not in response.get_data(as_text=True)
    assert client.get("/api/internal/me").status_code == 200
    session = store.tables["portal_sessions"][0]
    assert len(session["token_hash"]) == 64
    assert session["token_hash"] not in cookie


def test_production_cookie_is_secure_and_host_only(client):
    response = write(client, "login", {"username": "Mahee", "password": "TestPass123"},
        base_url="https://internal.archetsolutions.com")
    cookie = response.headers["Set-Cookie"]
    assert "__Host-archet_session=" in cookie and "Secure" in cookie and "Domain=" not in cookie
    assert "Max-Age" not in cookie


def test_bad_password_and_disabled_user(client, store):
    assert write(client, "login", {"username": "Mahee", "password": "wrong"}).status_code == 401
    store.db("portal_users", "PATCH", {"active": False}, id="eq." + store.member["id"])
    assert login(client, "Member").status_code == 401


def test_csrf_and_missing_origin_blocked(client):
    payload = {"username": "Mahee", "password": "TestPass123"}
    assert client.post("/api/internal/login", json=payload).status_code == 403
    response = client.post("/api/internal/login", json=payload,
        headers={"Origin": "https://evil.example", "X-Archet-Request": "1"})
    assert response.status_code == 403


def test_rate_limits_and_service_failure_fail_closed(client, store):
    store.rate_allowed = False
    response = login(client)
    assert response.status_code == 429 and "Retry-After" in response.headers
    store.unavailable = True
    assert login(client).status_code == 503
    assert not store.tables["portal_sessions"]


def test_expired_session_and_logout(client, store):
    login(client)
    store.tables["portal_sessions"][0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert client.get("/api/internal/me").status_code == 401
    login(client)
    assert write(client, "logout", {}).status_code == 200
    assert client.get("/api/internal/me").status_code == 401
    assert not store.tables["portal_sessions"]


def test_members_cannot_manage_accounts(client, store):
    login(client, "Member")
    assert client.get("/api/internal/users").status_code == 403
    assert write(client, "users", {}).status_code == 403
    assert write(client, "users/" + store.owner["id"], {"active": False}, "PATCH").status_code == 403


def test_admin_create_and_owner_protection(client, store):
    login(client)
    response = write(client, "users", {"username": "New_Team", "display_name": "New teammate", "password": "NewPass123", "role": "member"})
    assert response.status_code == 201
    assert "password" not in response.json["user"]
    assert write(client, "users", {"username": "new_team", "display_name": "Duplicate", "password": "NewPass123"}).status_code == 409
    assert write(client, "users/" + store.owner["id"], {"active": False}, "PATCH").status_code == 403
    assert write(client, "users/" + store.owner["id"], {"password": "changed123"}, "PATCH").status_code == 403
    assert write(client, "users/not-a-uuid", {"active": False}, "PATCH").status_code == 400


@pytest.mark.parametrize("change", [{"active": False}, {"role": "admin"}, {"password": "ChangedPass123"}])
def test_account_changes_revoke_existing_sessions(client, store, change):
    member_client = index.app.test_client()
    login(member_client, "Member")
    login(client)
    assert write(client, "users/" + store.member["id"], change, "PATCH").status_code == 200
    assert member_client.get("/api/internal/me").status_code == 401
    if "password" in change:
        assert login(member_client, "Member").status_code == 401
        assert write(member_client, "login", {"username": "Member", "password": change["password"]}).status_code == 200


def test_own_password_change_revokes_all_sessions(client, store):
    other = index.app.test_client()
    login(client)
    login(other)
    assert write(client, "password", {"current_password": "wrong", "new_password": "ChangedPass123"}).status_code == 403
    assert write(client, "password", {"current_password": "TestPass123", "new_password": "ChangedPass123"}).status_code == 200
    assert client.get("/api/internal/me").status_code == 401
    assert other.get("/api/internal/me").status_code == 401


QUOTE = {"full_name": "Test Person", "company": "Test Co", "email": "test@example.com", "brand": "Retail"}


def test_quote_survives_email_failure_and_is_editable(client, store, monkeypatch):
    def fail(record):
        raise RuntimeError("SMTP unavailable")
    monkeypatch.setattr(index, "send_lead_notification", fail)
    response = client.post("/api/quote", json=QUOTE)
    assert response.status_code == 200
    row = store.tables["quote_requests"][0]
    assert row["notification_status"] == "failed"
    login(client, "Member")
    assert client.get("/api/internal/quotes").json["quotes"][0]["company"] == "Test Co"
    response = write(client, "quotes/" + row["id"], {"status": "contacted", "notes": "Called today"}, "PATCH")
    assert response.status_code == 200
    assert row["notes"] == "Called today" and row["updated_by"] == store.member["id"]


def test_no_success_when_quote_storage_fails(client, store):
    store.unavailable = True
    assert client.post("/api/quote", json=QUOTE).status_code == 503
    assert not store.tables["quote_requests"]


@pytest.mark.parametrize("payload", [[1], {**QUOTE, "full_name": 42}, {**QUOTE, "email": "bad\r\nBcc:other@test.com"}, {**QUOTE, "message": "x" * 10001}])
def test_quote_validation(client, payload):
    assert client.post("/api/quote", json=payload).status_code == 400


def test_page_boundaries(client, store):
    for i in range(51):
        store.db("quote_requests", "POST", {**QUOTE, "company": str(i)})
    login(client)
    first = client.get("/api/internal/quotes").json
    second = client.get("/api/internal/quotes?offset=50").json
    assert len(first["quotes"]) == 50 and first["has_more"]
    assert len(second["quotes"]) == 1 and not second["has_more"]

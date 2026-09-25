import io
import json
from urllib.error import HTTPError

import pytest

from api import supabase_store as store


@pytest.mark.parametrize("key", ["sb_secret_test", "legacy.jwt.key"])
def test_server_key_headers_and_encoded_filters(monkeypatch, key):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", key)
    captured = []
    def fetch(request, timeout):
        captured.append(request)
        return io.BytesIO(b'[]')
    monkeypatch.setattr(store, "urlopen", fetch)
    assert store.db("portal_users", username_key="eq.member_name") == []
    request = captured[0]
    assert request.get_header("Apikey") == key
    assert request.get_header("Authorization") == (None if key.startswith("sb_secret_") else "Bearer " + key)
    assert "username_key=eq.member_name" in request.full_url


def test_transport_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    def fetch(request, timeout):
        raise HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(json.dumps({"code": "invalid_credentials", "message": "sensitive detail"}).encode()))
    monkeypatch.setattr(store, "urlopen", fetch)
    with pytest.raises(store.StoreError) as exc:
        store.auth("token", data={"password": "secret"})
    assert exc.value.code == "invalid_credentials"
    assert "sensitive" not in str(exc.value) and "secret" not in str(exc.value)

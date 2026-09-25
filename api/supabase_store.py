"""Server-only Supabase REST/Auth client. No credentials reach the browser."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class StoreError(Exception):
    def __init__(self, status=503, code="unavailable"):
        self.status = status
        self.code = code
        super().__init__("Supabase request failed")


def call(path, method="GET", data=None, params=None):
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url.startswith("https://") or not key:
        raise StoreError(code="not_configured")
    headers = {"apikey": key, "Content-Type": "application/json"}
    # Legacy service-role JWTs need Authorization. Modern secret keys use apikey.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + key
    if path.startswith("rest/"):
        headers["Prefer"] = "return=representation"
    target = url + "/" + path
    if params:
        target += "?" + urlencode(params)
    req = Request(target, data=None if data is None else json.dumps(data).encode(),
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as exc:
        try:
            error = json.loads(exc.read())
        except (ValueError, OSError):
            error = {}
        raise StoreError(exc.code, error.get("code") or error.get("error_code", "upstream_error")) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise StoreError() from None


def db(table, method="GET", data=None, **params):
    return call("rest/v1/" + table, method, data, params)


def auth(path, method="POST", data=None, **params):
    return call("auth/v1/" + path, method, data, params)


def login_email(username):
    # These are internal identifiers, never email recipients.
    return username.lower() + "@users.internal.archetsolutions.com"

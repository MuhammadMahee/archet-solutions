"""Username login backed by Supabase Auth and revocable server-side sessions."""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import UUID, uuid4

from flask import g, jsonify, request

try:
    from api.supabase_store import StoreError, auth, db, login_email
except ModuleNotFoundError:
    from supabase_store import StoreError, auth, db, login_email

INTERNAL_HOST = os.getenv("INTERNAL_HOST", "internal.archetsolutions.com")
USERNAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")
PUBLIC_USER_FIELDS = "id,username,display_name,role,active,is_owner,created_at,rest_mode,rest_version,page_access,must_change_password"

PAGE_OPTIONS = {'sales':'Sales Update','spreadsheet':'Opening / Closing Spreadsheet',
    'quota':'Quota Update','callingtree':'Calling Tree','workforce':'AI Workforce',
    'overview':'Overview','quotes':'Quote inbox','users':'Accounts'}


def allowed_pages(user):
    if user.get('is_owner'):
        return list(PAGE_OPTIONS)+['invoices','settings']
    selected=user.get('page_access')
    pages=[key for key in PAGE_OPTIONS if selected is None or key in selected]
    return [key for key in pages if key!='users' or user['role']=='admin']+['settings']


def page_access_field(payload, role):
    selected=payload.get('page_access')
    if not isinstance(selected,list) or len(selected)>len(PAGE_OPTIONS) or any(not isinstance(key,str) or key not in PAGE_OPTIONS for key in selected) or len(set(selected))!=len(selected):
        raise PortalError('Choose valid page access.')
    if role!='admin' and 'users' in selected:
        raise PortalError('Accounts access requires the Admin role.')
    if set(selected)-set(allowed_pages(g.portal_user)):
        raise PortalError('You can only grant pages available to your own account.',403)
    return [key for key in PAGE_OPTIONS if key in selected]


def check_page_access(user):
    path=request.path.removeprefix('/api/internal/').split('/')[0]
    page={'store-hours':'spreadsheet','sales':'sales','quota':'quota','calling-tree':'callingtree',
          'workforce':'workforce','invoices':'invoices','users':'users','quotes':'quotes'}.get(path)
    permitted=allowed_pages(user)
    # Overview reads the same inquiry summary; follow-up edits still need Quote inbox.
    if page=='quotes' and request.method=='GET' and 'overview' in permitted:
        return
    if page and page not in permitted:
        raise PortalError('You do not have access to this page. Contact your administrator.',403)


def password_write(uid):
    from api.password_vault import password_write as write
    return write(uid)


def reveal_password(uid,actor):
    from api.password_vault import reveal
    return reveal(uid,actor)


def can_view_passwords(user):
    return user.get('role')=='admin' and user.get('username','').casefold() in {'mahee','mughees','sharjeel'}


def local_request():
    return not os.getenv("VERCEL") and request.host.split(":")[0] in ("localhost", "127.0.0.1")


def portal_host():
    host = request.host.split(":")[0].lower()
    return host == INTERNAL_HOST or local_request() or (
        os.getenv("VERCEL_ENV") == "preview" and host.endswith(".vercel.app"))


def cookie_name():
    return "archet_session" if local_request() else "__Host-archet_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def client_address():
    # Vercel overwrites this header; never trust arbitrary X-Forwarded-For.
    if os.getenv("VERCEL"):
        return request.headers.get("X-Vercel-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(scope, identity, limit=10, seconds=900):
    allowed = db("rpc/portal_check_rate", "POST", {
        "p_key": scope + ":" + digest(identity), "p_limit": limit, "p_seconds": seconds,
    })
    if not allowed:
        raise PortalError("Too many attempts. Please try again later.", 429)


class PortalError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise PortalError("A JSON object is required.")
    return payload


def text_field(payload, name, maximum=100, required=True):
    value = payload.get(name, "")
    if not isinstance(value, str) or len(value) > maximum:
        raise PortalError("Invalid " + name.replace("_", " ") + ".")
    value = value.strip()
    if required and not value:
        raise PortalError(name.replace("_", " ").capitalize() + " is required.")
    return value


def password_field(payload, name="password"):
    value = payload.get(name)
    if not isinstance(value, str) or not 8 <= len(value) <= 128:
        raise PortalError("Passwords must contain 8 to 128 characters.")
    return value


def valid_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError):
        raise PortalError("Invalid record ID.") from None


def user_view(user):
    return {**{key: user[key] for key in PUBLIC_USER_FIELDS.split(",") if key!="page_access"}, "page_access":allowed_pages(user)}


def require_user(admin=False, allow_rest=False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = request.cookies.get(cookie_name(), "")
            if not token or len(token) > 128:
                raise PortalError("Please sign in.", 401)
            sessions = db("portal_sessions", token_hash="eq." + digest(token),
                          expires_at="gt." + datetime.now(timezone.utc).isoformat(), limit=1)
            if not sessions:
                raise PortalError("Your session has expired. Please sign in.", 401)
            session = sessions[0]
            users = db("portal_users", id="eq." + session["user_id"], limit=1)
            if not users or not users[0]["active"] or users[0]["session_version"] != session["session_version"]:
                raise PortalError("Please sign in again.", 401)
            g.portal_user = users[0]
            g.session_hash = digest(token)
            password_required = g.portal_user.get('must_change_password', False)
            password_route = request.path == '/api/internal/password'
            if password_required and request.path not in ('/api/internal/me', '/api/internal/password'):
                return jsonify(status='error', code='password_change_required',
                               message='Change your password before continuing.', user=user_view(g.portal_user)), 403
            if g.portal_user.get('rest_mode') and not allow_rest and not (password_required and password_route):
                return jsonify(status='error', code='account_rest', message='Your account is on rest.',
                               user=user_view(g.portal_user)), 403
            if admin and g.portal_user["role"] != "admin":
                raise PortalError("Administrator access is required.", 403)
            check_page_access(g.portal_user)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def register_portal(app):
    @app.errorhandler(PortalError)
    def portal_error(exc):
        response = jsonify(status="error", message=exc.message)
        if exc.status == 429:
            response.headers["Retry-After"] = "900"
        return response, exc.status

    @app.errorhandler(StoreError)
    def store_error(exc):
        app.logger.warning("Supabase unavailable (status=%s, code=%s)", exc.status, exc.code)
        return jsonify(status="error", message="The data service is unavailable. Please contact your administrator."), 503

    @app.before_request
    def guard_portal():
        limit=3*1024*1024 if request.path in ('/api/internal/calling-tree/preview','/api/internal/quota/upload','/api/internal/store-hours/schedules/preview') else 32*1024
        if request.path.startswith('/api/internal/invoices/'):
            limit = 512 * 1024
        if request.path in ('/api/internal/store-hours/review','/api/internal/store-hours/sheet/presence'):
            limit = 512 * 1024
        if request.method in ('POST', 'PATCH') and re.fullmatch(r'/api/internal/workforce/conversations/[0-9a-f-]{36}/(messages|profile)', request.path):
            limit = 3 * 1024 * 1024
        if request.content_length and request.content_length>limit:
            raise PortalError('The upload or request is too large.',413)
        if not request.path.startswith("/api/internal/"):
            return
        if not portal_host():
            raise PortalError("Not found", 404)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            scheme = "http" if local_request() and not request.is_secure else "https"
            if request.headers.get("Origin") != scheme + "://" + request.host:
                raise PortalError("This request must come from the internal portal.", 403)
            if request.headers.get("X-Archet-Request") != "1" or not request.is_json:
                raise PortalError("Invalid portal request.", 403)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith(("/api/internal/", "/internal", "/spreadsheet", "/ai-workforce")) or request.host.split(":")[0] == INTERNAL_HOST:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.post("/api/internal/login")
    def login():
        payload = body()
        username = text_field(payload, "username", 32)
        password = payload.get("password")
        if not USERNAME.fullmatch(username) or not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise PortalError("Incorrect username or password.", 401)
        remember = payload.get("remember", False)
        if not isinstance(remember, bool):
            raise PortalError("Invalid remember preference.")
        rate_limit("login-ip", client_address(), 30)
        rate_limit("login-user", username.lower(), 10)
        # Read the session version before verifying the password so concurrent
        # administrative changes invalidate any login already in progress.
        users = db("portal_users", username_key="eq." + username.lower(), limit=1)
        try:
            result = auth("token", data={"email": login_email(username), "password": password}, grant_type="password")
        except StoreError as exc:
            if exc.status in (400, 401, 422):
                raise PortalError("Incorrect username or password.", 401) from None
            if exc.status == 429:
                raise PortalError("Too many attempts. Please try again later.", 429) from None
            raise
        if not users or not users[0]["active"] or result["user"]["id"] != users[0]["id"]:
            raise PortalError("Incorrect username or password.", 401)
        user = users[0]
        token = secrets.token_urlsafe(32)
        lifetime = timedelta(days=30) if remember else timedelta(hours=12)
        db("portal_sessions", "POST", {"token_hash": digest(token), "user_id": user["id"],
            "session_version": user["session_version"],
            "expires_at": (datetime.now(timezone.utc) + lifetime).isoformat()})
        old = request.cookies.get(cookie_name())
        if old:
            db("portal_sessions", "DELETE", token_hash="eq." + digest(old))
        response = jsonify(user=user_view(user))
        response.set_cookie(cookie_name(), token, max_age=int(lifetime.total_seconds()) if remember else None,
                            secure=not local_request(), httponly=True, samesite="Strict", path="/")
        return response

    @app.get("/api/internal/me")
    @require_user(allow_rest=True)
    def me():
        return jsonify(user=user_view(g.portal_user))

    @app.post("/api/internal/logout")
    def logout():
        token = request.cookies.get(cookie_name())
        if token:
            db("portal_sessions", "DELETE", token_hash="eq." + digest(token))
        response = jsonify(status="success")
        response.delete_cookie(cookie_name(), path="/", secure=not local_request(), httponly=True, samesite="Strict")
        return response

    @app.get("/api/internal/users")
    @require_user(admin=True)
    def users_list():
        return jsonify(users=[user_view(user) for user in db("portal_users", select=PUBLIC_USER_FIELDS, order="created_at.asc", limit=1000)],
                       page_options=PAGE_OPTIONS,assignable_pages=allowed_pages(g.portal_user),can_view_passwords=can_view_passwords(g.portal_user))

    @app.post("/api/internal/users")
    @require_user(admin=True)
    def users_create():
        payload = body()
        username = text_field(payload, "username", 32)
        if not USERNAME.fullmatch(username):
            raise PortalError("Use 3–32 letters, numbers or underscores for the username.")
        if username.lower() == "mahee":
            raise PortalError("This username belongs to the permanent owner.", 409)
        display_name = text_field(payload, "display_name")
        password = password_field(payload)
        role = payload.get("role", "member")
        if role not in ("admin", "member"):
            raise PortalError("Invalid role.")
        selected=payload.get("page_access",[key for key in PAGE_OPTIONS if key in allowed_pages(g.portal_user) and (key!="users" or role=="admin")])
        page_access=page_access_field({"page_access":selected},role)
        if db("portal_users", username_key="eq." + username.lower(), limit=1):
            raise PortalError("That username already exists.", 409)
        try:
            result = auth("admin/users", data={"email": login_email(username), "password": password, "email_confirm": True})
        except StoreError as exc:
            if exc.status in (400, 422):
                raise PortalError("Unable to create this account. The username may exist or the password may not meet the project policy.") from None
            raise
        uid = result["id"]
        try:
            with password_write(uid) as remember:
                user = db("portal_users", "POST", {"id": uid, "username": username, "display_name": display_name, "role": role, "page_access":page_access})[0]
                remember(password)
        except StoreError:
            try:
                auth("admin/users/" + uid, "DELETE")
            except StoreError:
                app.logger.error("An Auth account needs administrator cleanup after profile creation failed")
            raise
        return jsonify(user=user_view(user)), 201

    @app.patch("/api/internal/users/<uid>")
    @require_user(admin=True)
    def users_update(uid):
        uid = valid_id(uid)
        payload = body()
        users = db("portal_users", id="eq." + uid, limit=1)
        if not users:
            raise PortalError("Account not found.", 404)
        target = users[0]
        if target["is_owner"]:
            raise PortalError("The permanent owner cannot be changed here. Use Change password for your own password.", 403)
        if uid == g.portal_user["id"]:
            raise PortalError("Ask another administrator to change your account.", 403)
        if set(allowed_pages(target))-set(allowed_pages(g.portal_user)):
            raise PortalError("Ask an administrator with all of this account's pages to manage it.",403)
        if target['username'].casefold() in {'mahee','mughees','sharjeel'} and not can_view_passwords(g.portal_user):
            raise PortalError('Only Mahee, Sharjeel and Mughees can manage password-viewer accounts.',403)
        changes = {}
        if "role" in payload:
            if payload["role"] not in ("admin", "member"):
                raise PortalError("Invalid role.")
            changes["role"] = payload["role"]
        if "active" in payload:
            if not isinstance(payload["active"], bool):
                raise PortalError("Invalid account status.")
            changes["active"] = payload["active"]
        if "page_access" in payload:
            changes["page_access"]=page_access_field(payload,changes.get("role",target["role"]))
        password = password_field(payload) if "password" in payload else None
        if not changes and password is None:
            raise PortalError("No account changes supplied.")
        # A fresh version makes concurrent updates invalidate old sessions.
        changes["session_version"] = str(uuid4())
        db("portal_users", "PATCH", changes, id="eq." + uid)
        if password is not None:
            with password_write(uid) as remember:
                try:
                    auth("admin/users/" + uid, "PUT", {"password": password})
                except StoreError as exc:
                    if exc.status in (400, 422):
                        raise PortalError("The password does not meet the project policy. Existing sessions were revoked.") from None
                    raise
                # Revoke logins which started while the Auth update was in flight.
                db("portal_users", "PATCH", {"session_version": str(uuid4())}, id="eq." + uid)
                remember(password)
        return jsonify(status="success")

    @app.post('/api/internal/users/<uid>/password/reveal')
    @require_user(admin=True)
    def users_password_reveal(uid):
        if not can_view_passwords(g.portal_user):
            raise PortalError('Only Mahee, Sharjeel and Mughees can view account passwords.',403)
        uid=valid_id(uid)
        if uid==g.portal_user['id']:
            raise PortalError('Use Settings to change your own password.',400)
        if not db('portal_users',id='eq.'+uid,limit=1):
            raise PortalError('Account not found.',404)
        rate_limit('password-view',g.portal_user['id'],60)
        password=reveal_password(uid,g.portal_user['id'])
        return jsonify(password=password,available=password is not None)

    @app.patch('/api/internal/users/<uid>/rest')
    @require_user(admin=True)
    def users_rest(uid):
        if not g.portal_user['is_owner'] or g.portal_user['username'] != 'Mahee':
            raise PortalError('Only Mahee can change account rest status.', 403)
        uid = valid_id(uid)
        rest = body().get('rest_mode')
        if not isinstance(rest, bool):
            raise PortalError('Choose a valid rest status.')
        users = db('portal_users', id='eq.' + uid, limit=1)
        if not users:
            raise PortalError('Account not found.', 404)
        if users[0]['is_owner'] or uid == g.portal_user['id']:
            raise PortalError('The permanent owner and your own account cannot be put on rest here.', 403)
        # Keep login sessions usable for the rest screen and automatic restoration.
        changed = db('portal_users', 'PATCH', {'rest_mode': rest, 'rest_version': str(uuid4())}, id='eq.' + uid)
        return jsonify(user=user_view(changed[0]))

    @app.post("/api/internal/password")
    @require_user()
    def change_password():
        payload = body()
        current = payload.get("current_password")
        if not isinstance(current, str) or not 1 <= len(current) <= 128:
            raise PortalError("Current password is required.")
        password = password_field(payload, "new_password")
        if g.portal_user.get('must_change_password') and password == current:
            raise PortalError('Choose a new password different from your current password.')
        rate_limit("password", g.portal_user["id"], 10)
        with password_write(g.portal_user['id']) as remember:
            try:
                auth("token", data={"email": login_email(g.portal_user["username"]), "password": current}, grant_type="password")
            except StoreError as exc:
                if exc.status in (400, 401, 422):
                    raise PortalError("Current password is incorrect.", 403) from None
                raise
            try:
                auth("admin/users/" + g.portal_user["id"], "PUT", {"password": password})
            except StoreError as exc:
                if exc.status in (400, 422):
                    raise PortalError("The new password does not meet the project policy.") from None
                raise
            db("portal_users", "PATCH", {"session_version": str(uuid4())}, id="eq." + g.portal_user["id"])
            remember(password)
        # Only clear a requirement observed by this request, after the password
        # and vault transaction succeed. A reset imposed during a normal change
        # must remain in effect.
        if g.portal_user.get('must_change_password'):
            db('portal_users', 'PATCH', {'must_change_password': False,
                'session_version': str(uuid4())}, id='eq.' + g.portal_user['id'])
        response = jsonify(status="success", message="Password updated. Please sign in again.")
        response.delete_cookie(cookie_name(), path="/", secure=not local_request(), httponly=True, samesite="Strict")
        return response

    @app.get("/api/internal/quotes")
    @require_user()
    def quotes_list():
        try:
            offset = max(0, int(request.args.get("offset", "0")))
        except ValueError:
            raise PortalError("Invalid page.") from None
        rows = db("quote_requests", order="received_at.desc,id.desc", limit=51, offset=offset)
        return jsonify(quotes=rows[:50], has_more=len(rows) > 50)

    @app.patch("/api/internal/quotes/<qid>")
    @require_user()
    def quotes_update(qid):
        qid = valid_id(qid)
        payload = body()
        status = payload.get("status")
        if status not in ("new", "contacted", "closed"):
            raise PortalError("Invalid quote status.")
        notes = text_field(payload, "notes", 10000, required=False)
        rows = db("quote_requests", "PATCH", {"status": status, "notes": notes,
            "updated_by": g.portal_user["id"], "updated_at": datetime.now(timezone.utc).isoformat()}, id="eq." + qid)
        if not rows:
            raise PortalError("Quote not found.", 404)
        return jsonify(quote=rows[0])

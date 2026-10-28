"""Encrypted, explicitly revealed copies of newly assigned portal passwords."""
import base64
from contextlib import contextmanager
import json
import os
import psycopg

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from api.sales import connect
from api.supabase_store import StoreError

def cipher():
    # Independent purpose-specific key from high-entropy server configuration.
    secret=os.getenv('PORTAL_PASSWORD_KEY') or os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    if not secret or len(secret)<32:
        raise StoreError(code='password_storage_not_configured')
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'archet-portal-v1',info=b'password-display-vault').derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(uid,password):
    return cipher().encrypt(json.dumps({'user_id':str(uid),'password':password}).encode()).decode()


def decrypt(uid,token):
    try:
        value=json.loads(cipher().decrypt(token.encode()))
        if value['user_id']!=str(uid) or not isinstance(value['password'],str):return None
        return value['password']
    except (InvalidToken,ValueError,KeyError,TypeError):
        return None


@contextmanager
def vault_connection():
    try:
        with connect() as conn:
            yield conn
    except psycopg.Error:
        raise StoreError(code='password_storage_unavailable') from None


@contextmanager
def password_write(uid):
    # Serialize create/reset/self-change across workers. Supabase Auth updates are
    # external to this transaction; the Auth fingerprint prevents stale reveals
    # if a later database write fails or a password is reset outside the portal.
    cipher()
    with vault_connection() as conn:
        with conn.transaction():
            conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,839271))",(str(uid),))
            def save(password):
                conn.execute("""insert into public.portal_password_vault(user_id,ciphertext,auth_fingerprint)
                    select id,%s,encode(sha256(convert_to(encrypted_password,'UTF8')),'hex')
                    from auth.users where id=%s
                    on conflict(user_id) do update set ciphertext=excluded.ciphertext,
                    auth_fingerprint=excluded.auth_fingerprint,updated_at=now()""",(encrypt(uid,password),uid))
            yield save


def reveal(uid,actor):
    with vault_connection() as conn:
        with conn.transaction():
            conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,839271))",(str(uid),))
            row=conn.execute("""select v.ciphertext from public.portal_password_vault v join auth.users u on u.id=v.user_id
                where v.user_id=%s and v.auth_fingerprint=encode(sha256(convert_to(u.encrypted_password,'UTF8')),'hex')""",(uid,)).fetchone()
            password=decrypt(uid,row['ciphertext']) if row else None
            conn.execute('insert into public.portal_password_views(actor_id,target_id,available) values(%s,%s,%s)',(actor,uid,password is not None))
            return password

"""Create the permanent owner once; never reset an existing owner's password."""
import getpass
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api.supabase_store import StoreError, auth, db, login_email


def main():
    if not os.getenv("SUPABASE_URL") or not (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SECRET_KEY in your local .env first.")
    existing = db("portal_users", username_key="eq.mahee", limit=1)
    if existing:
        if not existing[0]["is_owner"]:
            raise SystemExit("Mahee already exists as a non-owner. Resolve this in Supabase before continuing.")
        print("The permanent Mahee owner already exists. No credentials were changed.")
        return
    password = os.getenv("ARCHET_OWNER_PASSWORD") or getpass.getpass("Initial password for Mahee: ")
    if not 8 <= len(password) <= 128:
        raise SystemExit("The password must contain 8 to 128 characters.")
    result = auth("admin/users", data={"email": login_email("Mahee"), "password": password, "email_confirm": True})
    uid = result["id"]
    try:
        db("portal_users", "POST", {"id": uid, "username": "Mahee", "display_name": "Mahee",
            "role": "admin", "active": True, "is_owner": True})
    except StoreError:
        try:
            auth("admin/users/" + uid, "DELETE")
        except StoreError:
            print("Remove the orphaned Mahee Auth user in Supabase before retrying.", file=sys.stderr)
        raise
    print("Permanent owner Mahee created. Sign in at https://internal.archetsolutions.com.")
    print("Remove ARCHET_OWNER_PASSWORD from your local .env after verifying login.")


if __name__ == "__main__":
    try:
        main()
    except StoreError as exc:
        raise SystemExit(f"Supabase setup failed (status {exc.status}, code {exc.code}). Check keys, run the migration, and retry.") from None

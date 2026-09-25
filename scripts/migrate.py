"""Run pending SQL migrations during production builds, never on web requests."""
import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv
import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
LOCK_ID = 714092663589021  # Stable across deployments of this application.
NAME_PATTERN = re.compile(r"^(\d{3,})_[a-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    name: str
    sql: str
    checksum: str
    number: int


def read_migrations(directory=MIGRATIONS):
    migrations = []
    for path in directory.glob("*.sql"):
        match = NAME_PATTERN.fullmatch(path.name)
        if not match:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        sql = path.read_text(encoding="utf-8-sig")
        # The runner owns the transaction, including its history record.
        if re.search(r"^\s*(?:begin|commit|rollback|start\s+transaction)\s*;", sql, re.I | re.M):
            raise MigrationError(f"Remove transaction commands from {path.name}; the runner supplies them.")
        if not sql.strip():
            raise MigrationError(f"Empty migration: {path.name}")
        migrations.append(Migration(path.name, sql, hashlib.sha256(sql.encode()).hexdigest(), int(match[1])))
    migrations.sort(key=lambda migration: migration.number)
    if not migrations:
        raise MigrationError("No migration files found; check the build's project root.")
    if len({migration.number for migration in migrations}) != len(migrations):
        raise MigrationError("Migration numbers must be unique.")
    return migrations


def apply_migrations(connection, migrations, baseline=None):
    names = {migration.name for migration in migrations}
    if baseline and baseline not in names:
        raise MigrationError("The baseline filename must match a local migration.")
    # DDL, history and locking use the same transaction. Concurrent builds wait
    # before inspecting history, then skip work the earlier build committed.
    with connection.transaction():
        connection.execute("SET LOCAL lock_timeout = '60s'")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        connection.execute("CREATE SCHEMA IF NOT EXISTS archet_private")
        connection.execute("REVOKE ALL ON SCHEMA archet_private FROM PUBLIC, anon, authenticated, service_role")
        connection.execute("""CREATE TABLE IF NOT EXISTS archet_private.schema_migrations (
            name text PRIMARY KEY,
            checksum text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )""")
        connection.execute("REVOKE ALL ON archet_private.schema_migrations FROM PUBLIC, anon, authenticated, service_role")
        applied = dict(connection.execute("SELECT name, checksum FROM archet_private.schema_migrations").fetchall())
        if set(applied) - names:
            raise MigrationError("The database contains migrations missing from this checkout. Restore the missing files.")
        for migration in migrations:
            if migration.name in applied and applied[migration.name] != migration.checksum:
                raise MigrationError(f"Previously applied migration changed: {migration.name}. Restore it and add a new file.")
        count = 0
        for migration in migrations:
            if migration.name in applied:
                print(f"[migrate] Already applied: {migration.name}", flush=True)
                continue
            if baseline:
                if migration.name != baseline:
                    continue
                print(f"[migrate] Recording manually applied migration: {migration.name}", flush=True)
            else:
                print(f"[migrate] Applying: {migration.name}", flush=True)
                connection.execute(migration.sql, prepare=False)
            connection.execute(
                "INSERT INTO archet_private.schema_migrations (name, checksum) VALUES (%s, %s)",
                (migration.name, migration.checksum),
            )
            count += 1
        if count:
            connection.execute("NOTIFY pgrst, 'reload schema'")
    print(f"[migrate] Success. {count} migration(s) {'recorded' if baseline else 'applied'}.", flush=True)
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", metavar="FILENAME",
        help="Record SQL already applied manually, without executing it. Verify the existing schema first.")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    environment = os.getenv("VERCEL_ENV", "")
    if environment and environment != "production" and os.getenv("MIGRATE_PREVIEW", "").lower() != "true":
        print("[migrate] Skipped non-production deployment. Use a separate preview DB and MIGRATE_PREVIEW=true to enable.")
        return 0
    if os.getenv("VERCEL") and not environment:
        print("[migrate] VERCEL_ENV is missing; cannot determine the deployment target.", file=sys.stderr)
        return 1
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
        print("[migrate] SUPABASE_DB_URL is required. Add the Supabase session-pooler database URI in Vercel's Production environment variables.", file=sys.stderr)
        return 1
    try:
        info = conninfo_to_dict(url)
        if info.get("port") == "6543":
            raise MigrationError("Use the Session pooler (port 5432) or a direct database connection, not transaction pooling.")
        migrations = read_migrations()
        with psycopg.connect(url, autocommit=True, sslmode="require", connect_timeout=15) as connection:
            apply_migrations(connection, migrations, baseline=args.baseline)
        return 0
    except MigrationError as exc:
        print(f"[migrate] {exc}", file=sys.stderr)
    except psycopg.Error as exc:
        code = exc.sqlstate or "connection_error"
        hint = " Check SUPABASE_DB_URL and database connectivity."
        if code == "42P07":
            hint = " Existing tables found. If you already ran 001 manually, follow the baseline instructions in SETUP.md."
        print(f"[migrate] Database migration failed ({code}). Changes from this run were rolled back.{hint}", file=sys.stderr)
    except OSError:
        print("[migrate] Could not read migration files. Check the project root and file permissions.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

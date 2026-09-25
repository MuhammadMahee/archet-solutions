from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tomllib

import psycopg
import pytest

from scripts import migrate


class Database:
    """Transactional boundary double; never connects to a real database."""
    def __init__(self):
        self.history = {}
        self.executed = []
        self.calls = []
        self.fail_sql = None
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaction(self):
        history, executed = deepcopy(self.history), self.executed[:]
        try:
            yield
        except Exception:
            self.history, self.executed = history, executed
            self.rollbacks += 1
            raise
        else:
            self.commits += 1

    def execute(self, sql, params=None, **kwargs):
        self.calls.append(sql)
        if sql.startswith("SELECT name, checksum"):
            return SimpleNamespace(fetchall=lambda: list(self.history.items()))
        if sql.startswith("INSERT INTO archet_private.schema_migrations"):
            self.history[params[0]] = params[1]
        if kwargs.get("prepare") is False:
            if sql == self.fail_sql:
                raise psycopg.ProgrammingError("simulated SQL failure")
            self.executed.append(sql)


def files(tmp_path):
    (tmp_path / "001_first.sql").write_text("CREATE TABLE first_table(id integer);\n", encoding="utf-8")
    (tmp_path / "002_second.sql").write_text("CREATE TABLE second_table(id integer);\n", encoding="utf-8")
    return migrate.read_migrations(tmp_path)


def test_first_build_applies_once_and_redeploy_skips(tmp_path):
    migrations = files(tmp_path)
    db = Database()
    assert migrate.apply_migrations(db, migrations) == 2
    assert db.executed == [migration.sql for migration in migrations]
    assert len(db.history) == 2
    assert migrate.apply_migrations(db, migrations) == 0
    assert len(db.executed) == 2
    assert db.calls.index("SELECT pg_advisory_xact_lock(%s)") < db.calls.index("SELECT name, checksum FROM archet_private.schema_migrations")


def test_failure_rolls_back_sql_and_history_together(tmp_path):
    migrations = files(tmp_path)
    db = Database()
    db.fail_sql = migrations[1].sql
    with pytest.raises(psycopg.Error):
        migrate.apply_migrations(db, migrations)
    assert not db.history and not db.executed
    assert db.rollbacks == 1 and db.commits == 0
    db.fail_sql = None
    assert migrate.apply_migrations(db, migrations) == 2


def test_modified_applied_migration_fails_before_new_sql(tmp_path):
    migrations = files(tmp_path)
    db = Database()
    migrate.apply_migrations(db, migrations[:1])
    (tmp_path / "001_first.sql").write_text("SELECT 'changed';", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="Previously applied migration changed"):
        migrate.apply_migrations(db, migrate.read_migrations(tmp_path))
    assert len(db.executed) == 1


def test_missing_migration_fails(tmp_path):
    migrations = files(tmp_path)
    db = Database()
    migrate.apply_migrations(db, migrations)
    with pytest.raises(migrate.MigrationError, match="missing from this checkout"):
        migrate.apply_migrations(db, migrations[:1])


def test_explicit_baseline_only_records_selected_file(tmp_path):
    migrations = files(tmp_path)
    db = Database()
    assert migrate.apply_migrations(db, migrations, baseline="001_first.sql") == 1
    assert not db.executed and list(db.history) == ["001_first.sql"]
    assert migrate.apply_migrations(db, migrations) == 1
    assert db.executed == [migrations[1].sql]
    with pytest.raises(migrate.MigrationError, match="must match"):
        migrate.apply_migrations(db, migrations, baseline="unknown.sql")


@pytest.mark.parametrize("sql", ["BEGIN;\nSELECT 1;\nCOMMIT;", "SELECT 1;\nROLLBACK;"])
def test_migration_cannot_override_transaction(tmp_path, sql):
    (tmp_path / "001_test.sql").write_text(sql, encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="transaction commands"):
        migrate.read_migrations(tmp_path)


def test_line_endings_do_not_change_checksums(tmp_path):
    path = tmp_path / "001_test.sql"
    path.write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    first = migrate.read_migrations(tmp_path)[0].checksum
    path.write_bytes(b"SELECT 1;\nSELECT 2;\n")
    assert migrate.read_migrations(tmp_path)[0].checksum == first


def test_duplicate_numbers_rejected(tmp_path):
    files(tmp_path)
    (tmp_path / "001_duplicate.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="unique"):
        migrate.read_migrations(tmp_path)


@pytest.fixture
def build_env(monkeypatch):
    monkeypatch.setattr(migrate, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("MIGRATE_PREVIEW", raising=False)
    return monkeypatch


def test_production_missing_connection_fails_build(build_env, capsys):
    assert migrate.main([]) == 1
    assert "SUPABASE_DB_URL is required" in capsys.readouterr().err


def test_preview_skips_without_connecting(build_env):
    build_env.setenv("VERCEL_ENV", "preview")
    def never_connect(*args, **kwargs):
        pytest.fail("Preview tried connecting to a database")
    build_env.setattr(migrate.psycopg, "connect", never_connect)
    assert migrate.main([]) == 0


def test_opted_in_preview_requires_database(build_env):
    build_env.setenv("VERCEL_ENV", "preview")
    build_env.setenv("MIGRATE_PREVIEW", "true")
    assert migrate.main([]) == 1


def test_connection_failures_hide_credentials(build_env, capsys):
    build_env.setenv("SUPABASE_DB_URL", "postgresql://postgres:private-password@localhost:5432/postgres")
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("bad connection private-password")
    build_env.setattr(migrate.psycopg, "connect", fail)
    assert migrate.main([]) == 1
    output = capsys.readouterr()
    assert "private-password" not in output.err
    assert "migration failed" in output.err


def test_transaction_pooler_rejected(build_env, capsys):
    build_env.setenv("SUPABASE_DB_URL", "postgresql://postgres:private-password@localhost:6543/postgres")
    assert migrate.main([]) == 1
    assert "Session pooler" in capsys.readouterr().err


def test_vercel_build_wiring_and_existing_sql():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "vercel.json").read_text())
    manifest = tomllib.loads((root / "pyproject.toml").read_text())
    assert config["framework"] == "flask" and "builds" not in config
    assert config["buildCommand"] == "python scripts/migrate.py"
    assert manifest["tool"]["vercel"]["entrypoint"] == "api.index:app"
    assert set(manifest["project"]["dependencies"]) == set((root / "requirements.txt").read_text().splitlines())
    migrations = migrate.read_migrations()
    assert migrations[0].name == "001_internal_portal.sql"

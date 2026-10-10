"""Workforce storage on the existing Supabase PostgreSQL connection."""
from contextlib import contextmanager
import os

import psycopg
from psycopg.rows import dict_row

from api.portal import PortalError
from api.workforce_store import Store


class Connection:
    """Adapt the store's static, parameterized SQL to psycopg placeholders."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        return self.connection.execute(sql.replace('?', '%s'), parameters)

    def executemany(self, sql, parameters):
        with self.connection.cursor() as cursor:
            cursor.executemany(sql.replace('?', '%s'), parameters)


class PostgresStore(Store):
    # Longer than vercel.json maxDuration. A terminated invocation becomes
    # retryable on the next visit without replaying its model/tool calls.
    lease_seconds = 330

    def __init__(self, url=None):
        self.url = url or os.getenv('SUPABASE_DB_URL', '')
        if not self.url:
            raise PortalError('Configure SUPABASE_DB_URL for AI Workforce storage.', 503)

    @contextmanager
    def connection(self, write=False):
        try:
            with psycopg.connect(self.url, sslmode='require', connect_timeout=10,
                                 row_factory=dict_row, prepare_threshold=None) as conn:
                conn.execute("SET LOCAL search_path TO archet_workforce, pg_catalog")
                conn.execute("SET LOCAL statement_timeout = '15s'")
                conn.execute("SET LOCAL lock_timeout = '10s'")
                if write:
                    # Match SQLite's short BEGIN IMMEDIATE transactions across all
                    # Vercel instances. Never hold this lock during a model/tool call.
                    conn.execute('SELECT pg_advisory_xact_lock(714092663589022)')
                yield Connection(conn)
        except psycopg.errors.UndefinedTable:
            raise PortalError('AI Workforce storage is not installed. Deploy migration 012 to this database.', 503) from None
        except psycopg.Error:
            raise PortalError('AI Workforce storage is unavailable. Check the Supabase database connection.', 503) from None

    def worker_online(self):
        # Assignments execute inside the request; there is no external worker.
        return True

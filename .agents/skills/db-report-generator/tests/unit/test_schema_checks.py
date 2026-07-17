import psycopg2
import pytest

from scripts.collectors import schema_checks
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_missing_primary_key_fires(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.events (id int, payload text);"
    with _fixtures_sql.make_schema(conn, "sc1", ddl) as schema:
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "missing_primary_key"]
        assert len(rows) == 1
        assert rows[0]["table"] == "events"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_oversized_uuid_v4_pk_fires_on_large_table(pg_dsn, monkeypatch):
    monkeypatch.setattr(schema_checks, "_LARGE_TABLE_ROW_THRESHOLD", 2)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.big (id uuid PRIMARY KEY DEFAULT gen_random_uuid());"
    with _fixtures_sql.make_schema(conn, "sc2", ddl) as schema:
        with conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'ANALYZE "{schema}".big')
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "oversized_uuid_pk"]
        assert len(rows) == 1
        assert rows[0]["column"] == "id"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_uuid_v7_pk_does_not_fire(pg_dsn, monkeypatch):
    monkeypatch.setattr(schema_checks, "_LARGE_TABLE_ROW_THRESHOLD", 2)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.big (id uuid PRIMARY KEY);"
    with _fixtures_sql.make_schema(conn, "sc3", ddl) as schema:
        with conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{schema}".big VALUES '
                        "('11111111-1111-7111-8111-111111111111'), "
                        "('22222222-2222-7222-8222-222222222222'), "
                        "('33333333-3333-7333-8333-333333333333')")
            cur.execute(f'ANALYZE "{schema}".big')
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "oversized_uuid_pk"]
        assert rows == []
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_timestamp_without_timezone_fires(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.logs (id serial PRIMARY KEY, created_at timestamp);"
    with _fixtures_sql.make_schema(conn, "sc4", ddl) as schema:
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "timestamp_without_timezone"]
        assert len(rows) == 1
        assert rows[0]["column"] == "created_at"
    conn.close()

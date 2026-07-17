import psycopg2
import pytest

from scripts.collectors.rls_policies import collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_ok_empty_when_no_policies(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_flags_unwrapped_auth_uid(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes USING (owner = auth.uid());
    """
    with _fixtures_sql.make_schema(conn, "rls1", ddl):
        diag = collect(conn, {})
        assert diag["status"] == "ok"
        issues = {(r["issue"], r["function"]) for r in diag["metrics"]}
        assert ("unwrapped_reeval_call", "auth.uid") in issues
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_does_not_flag_wrapped_auth_uid(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes USING (owner = (select auth.uid()));
    """
    with _fixtures_sql.make_schema(conn, "rls2", ddl):
        diag = collect(conn, {})
        issues = {r["issue"] for r in diag["metrics"] if r["issue"] == "unwrapped_reeval_call"}
        assert issues == set()
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_flags_missing_supporting_index(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, org_id int);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_org_only ON {s}.notes USING (org_id = 5);
    """
    with _fixtures_sql.make_schema(conn, "rls3", ddl):
        diag = collect(conn, {})
        rows = [r for r in diag["metrics"] if r["issue"] == "missing_supporting_index"]
        assert len(rows) == 1
        assert rows[0]["column"] == "org_id"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_does_not_flag_auth_uid_nested_in_case_inside_subselect(pg_dsn):
    """Regression: _UnwrappedCallFinder must recognize a FuncCall as
    "wrapped" even when it's several AST levels below the SubLink -- here
    SubLink -> SelectStmt -> targetList -> ResTarget -> CaseExpr ->
    CaseWhen -> FuncCall -- not just a FuncCall as the SubLink's direct
    (or near-direct) child, as in test_collect_does_not_flag_wrapped_auth_uid
    above."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes
        USING (owner = (select case when true then auth.uid() else null end));
    """
    with _fixtures_sql.make_schema(conn, "rls6", ddl):
        diag = collect(conn, {})
        issues = {r["issue"] for r in diag["metrics"] if r["issue"] == "unwrapped_reeval_call"}
        assert issues == set()
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_flags_unwrapped_auth_uid_even_when_search_path_hides_schema(pg_dsn):
    """Regression for a live-verified bug: pg_get_expr() (which
    pg_policies.qual/with_check text comes from) schema-qualifies a
    function name only when it is NOT already visible unqualified via the
    CURRENT session's search_path. Confirmed against real Postgres 16: if
    the reporting connection's own search_path happens to include `auth`,
    `owner = auth.uid()` comes back from pg_policies as `owner = uid()`
    (schema prefix silently dropped), which would defeat a naive
    `auth.<fn>` text/name match. collect() must force a stable rendering
    regardless of the connection's own search_path."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes USING (owner = auth.uid());
    """
    with _fixtures_sql.make_schema(conn, "rls7", ddl):
        with conn.cursor() as cur:
            cur.execute("SET search_path = auth, public")
        diag = collect(conn, {})
        assert diag["status"] == "ok"
        issues = {(r["issue"], r["function"]) for r in diag["metrics"]}
        assert ("unwrapped_reeval_call", "auth.uid") in issues
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()

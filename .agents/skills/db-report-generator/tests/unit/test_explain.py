import psycopg2
import pytest

from scripts import explain
from scripts.collectors import base
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def _query_stats_diag(rows):
    return base.diagnostic("query", "ok", rows)


def test_run_returns_skipped_when_mode_off():
    diag = explain.run(None, {}, _query_stats_diag([]), mode="off", top_n=5, analyze_top_n=0,
                        statement_timeout_ms=3000, lock_timeout_ms=500)
    assert diag["status"] == "skipped"


def test_run_returns_skipped_when_query_stats_unavailable():
    diag = explain.run(None, {}, None, mode="plan", top_n=5, analyze_top_n=0,
                        statement_timeout_ms=3000, lock_timeout_ms=500)
    assert diag["status"] == "skipped"


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_ok_with_empty_query_stats_rows(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag([]),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_plan_mode_captures_plan_for_literal_query(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl1", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl1".t WHERE id = 1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        assert diag["status"] == "ok"
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["plan"] is not None
        assert row["explain_unavailable"] is None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_parameterized_query_pre_pg16_is_explicitly_unavailable(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl2", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl2".t WHERE id = $1'}]
        diag = explain.run(conn, {"server_version_num": 150000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["plan"] is None
        assert row["explain_unavailable"] == "parameterized_pre_pg16"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_parameterized_query_pg16_uses_generic_plan(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl3", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl3".t WHERE id = $1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["explain_unavailable"] is None
        assert row["plan"] is not None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_analyze_mode_runs_analyze_for_safe_select_within_analyze_top_n(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl4", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl4".t WHERE id = 1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=1,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "analyze"
        assert row["analyze_skipped_reason"] is None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_analyze_mode_skips_analyze_for_for_update(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl5", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl5".t WHERE id = 1 FOR UPDATE'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=1,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["analyze_skipped_reason"] == "locking_clause"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_restores_default_timeouts_after_explain(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl6", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl6".t WHERE id = 1'}]
        explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                    mode="plan", top_n=5, analyze_top_n=0,
                    statement_timeout_ms=111, lock_timeout_ms=22)
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "15s"
            cur.execute("SHOW lock_timeout")
            assert cur.fetchone()[0] == "3s"
    conn.close()


# ---------------------------------------------------------------------------
# Task 4 verification-item regression tests (beyond the brief's prescribed
# suite above): traced/probed independently rather than trusting the brief's
# code by inspection alone.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_parameterized_query_never_gets_analyze_mode_even_when_eligible(pg_dsn):
    """Verification item 1: the GENERIC_PLAN branch (has_parameters=True,
    PG16+) must never set mode="analyze", even when the row is within
    analyze_top_n and mode="analyze" -- it is the one branch that does NOT
    call sql_classify.is_analyze_safe(), and its safety instead rests on
    EXPLAIN GENERIC_PLAN being inherently non-executing (mirrored by never
    passing ANALYZE in its SQL text). This exercises that branch under the
    exact conditions (analyze mode, index 0 < analyze_top_n) that would
    trigger ANALYZE for a non-parameterized query, to confirm it still
    doesn't."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl7", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl7".t WHERE id = $1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=5,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["plan"] is not None
        assert row["analyze_skipped_reason"] is None
    conn.close()


def _make_fdw_fixture(cur):
    """Two plain tables (s.a, s.b) plus a loopback-FDW foreign table
    (fdw_ns.remote_tbl) that never needs to actually connect anywhere --
    CREATE SERVER/USER MAPPING/FOREIGN TABLE only write catalog metadata,
    no connectivity is required or exercised since the test only checks
    pg_foreign_table, never queries through the foreign table."""
    cur.execute("CREATE SCHEMA s")
    cur.execute("CREATE TABLE s.a (id int)")
    cur.execute("CREATE TABLE s.b (id int)")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
    cur.execute("CREATE SERVER dummy_srv FOREIGN DATA WRAPPER postgres_fdw "
                "OPTIONS (host 'localhost', dbname 'postgres')")
    cur.execute("CREATE USER MAPPING FOR CURRENT_USER SERVER dummy_srv")
    cur.execute("CREATE SCHEMA fdw_ns")
    cur.execute("CREATE FOREIGN TABLE fdw_ns.remote_tbl (id int) "
                "SERVER dummy_srv OPTIONS (table_name 'irrelevant')")


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_references_foreign_table_false_for_multi_relation_join_without_foreign_table(pg_dsn):
    """Verification item 2: a 2-table join with NEITHER table foreign must
    exercise the (now array-based) multi-relation SQL without error and
    correctly return False."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            _make_fdw_fixture(cur)
        from scripts.lib import sql_classify
        stmt = sql_classify.parse_statement("SELECT * FROM s.a JOIN s.b ON s.a.id = s.b.id")
        assert explain._references_foreign_table(conn, stmt) is False
    finally:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS s CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS fdw_ns CASCADE")
            cur.execute("DROP SERVER IF EXISTS dummy_srv CASCADE")
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_references_foreign_table_true_for_multi_relation_join_including_foreign_table(pg_dsn):
    """Verification item 2: a 2-table join where ONE table (schema-qualified)
    is foreign must be detected -- proves the multi-relation tuple/array
    adaptation actually matches, not just avoids erroring."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            _make_fdw_fixture(cur)
        from scripts.lib import sql_classify
        stmt = sql_classify.parse_statement(
            "SELECT * FROM s.a JOIN fdw_ns.remote_tbl r ON s.a.id = r.id"
        )
        assert explain._references_foreign_table(conn, stmt) is True
    finally:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS s CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS fdw_ns CASCADE")
            cur.execute("DROP SERVER IF EXISTS dummy_srv CASCADE")
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_references_foreign_table_true_for_unqualified_name_via_search_path(pg_dsn):
    """Verification item 2 / safety-gap regression: an UNQUALIFIED reference
    to a foreign table that resolves via a non-public search_path must
    still be detected.

    Confirmed by hand against the brief's original implementation (a
    (schema, relname) IN %s catalog join that fell back to a hardcoded
    "public" schema for unqualified names): with search_path set to
    fdw_ns and an unqualified `SELECT * FROM remote_tbl`, the original
    code queried pg_namespace/pg_class for ('public', 'remote_tbl') --
    which doesn't exist -- and returned False, i.e. it would have let
    ANALYZE run against a query that genuinely touches a foreign table.
    The fix resolves each reference via to_regclass() on THIS connection
    (the same one about to run the EXPLAIN), which follows the real,
    live search_path exactly as the planner itself would."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            _make_fdw_fixture(cur)
            cur.execute("SET search_path TO fdw_ns, public")
        from scripts.lib import sql_classify
        stmt = sql_classify.parse_statement("SELECT * FROM remote_tbl")
        assert explain._references_foreign_table(conn, stmt) is True
    finally:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO public")
            cur.execute("DROP SCHEMA IF EXISTS s CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS fdw_ns CASCADE")
            cur.execute("DROP SERVER IF EXISTS dummy_srv CASCADE")
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_analyze_mode_skips_analyze_for_foreign_table_via_search_path(pg_dsn):
    """End-to-end version of the same regression, through explain.run()
    itself (the function Task 8 actually calls), not just the internal
    helper: mode="analyze", row within analyze_top_n, statement is
    otherwise is_analyze_safe()==True (plain SELECT, no locking clause,
    no writes) but references a foreign table only by unqualified name
    under a non-public search_path. Must be downgraded to plan mode."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            _make_fdw_fixture(cur)
            cur.execute("SET search_path TO fdw_ns, public")
        rows = [{"queryid": "1", "query": "SELECT * FROM remote_tbl"}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=1,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["analyze_skipped_reason"] == "foreign_table"
    finally:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO public")
            cur.execute("DROP SCHEMA IF EXISTS s CASCADE")
            cur.execute("DROP SCHEMA IF EXISTS fdw_ns CASCADE")
            cur.execute("DROP SERVER IF EXISTS dummy_srv CASCADE")
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_restores_default_timeouts_even_when_row_processing_raises(pg_dsn, monkeypatch):
    """Verification item 3: force an exception to escape the per-row
    processing (bypassing _explain_row's own internal try/except, which
    would otherwise swallow ordinary EXPLAIN failures) so the try/finally
    around _restore_default_timeouts in run() is actually exercised, not
    just read as presumably correct."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True

    def _boom(*args, **kwargs):
        raise RuntimeError("forced failure for finally-block test")

    monkeypatch.setattr(explain, "_explain_row", _boom)
    try:
        rows = [{"queryid": "1", "query": "SELECT 1"}]
        with pytest.raises(RuntimeError, match="forced failure"):
            explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                        mode="plan", top_n=5, analyze_top_n=0,
                        statement_timeout_ms=111, lock_timeout_ms=22)
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "15s"
            cur.execute("SHOW lock_timeout")
            assert cur.fetchone()[0] == "3s"
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_metrics_row_has_exact_documented_shape(pg_dsn):
    """Verification item 5: locks down the exact per-row key set the brief
    documents as Task 8's contract, the same way test_query_stats.py locks
    down query_stats's row shape."""
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl8", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl8".t WHERE id = 1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert set(row) == {"queryid", "mode", "plan", "explain_unavailable",
                             "analyze_skipped_reason", "role", "search_path", "database"}
    conn.close()

import psycopg2
import pytest

from scripts import index_advisor
from scripts.collectors import base
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def _query_stats_diag(rows):
    return base.diagnostic("query", "ok", rows)


def test_run_returns_skipped_when_query_stats_unavailable():
    diag = index_advisor.run(None, None, top_n=5)
    assert diag["status"] == "skipped"


def test_run_ok_empty_when_no_rows():
    diag = index_advisor.run(None, _query_stats_diag([]), top_n=5)
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_suggests_index_for_uncovered_equality_predicate(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text)"
    with _fixtures_sql.make_schema(conn, "advtest", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "advtest".orders WHERE org_id = 5'}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["status"] == "ok"
        assert len(diag["metrics"]) == 1
        suggestion = diag["metrics"][0]
        assert suggestion["schema"] == "advtest"
        assert suggestion["table"] == "orders"
        assert suggestion["suggested_columns"] == ["org_id"]
        assert "CREATE INDEX" in suggestion["suggested_ddl"]
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_skips_when_index_already_exists(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text);
    CREATE INDEX ON {s}.orders (org_id);
    """
    with _fixtures_sql.make_schema(conn, "advtest2", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "advtest2".orders WHERE org_id = 5'}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["metrics"] == []
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_skips_multi_table_queries(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int);
    CREATE TABLE {s}.orgs (id serial PRIMARY KEY, name text);
    """
    with _fixtures_sql.make_schema(conn, "advtest3", ddl):
        rows = [{"queryid": "1",
                  "query": 'SELECT * FROM "advtest3".orders o JOIN "advtest3".orgs g ON o.org_id = g.id WHERE g.name = \'x\''}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["metrics"] == []
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_suggests_index_for_alias_qualified_predicate(pg_dsn):
    # `o.status = 'x'` parses to a ColumnRef with fields ("o", "status") --
    # path[-1] must drop the table alias and yield the bare column name
    # "status", not "o" or the qualified pair, and must not crash trying to
    # treat "o" as a real column.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text)"
    with _fixtures_sql.make_schema(conn, "advtest4", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "advtest4".orders o WHERE o.status = \'x\''}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["status"] == "ok"
        assert len(diag["metrics"]) == 1
        suggestion = diag["metrics"][0]
        assert suggestion["schema"] == "advtest4"
        assert suggestion["table"] == "orders"
        assert suggestion["suggested_columns"] == ["status"]
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_dedups_identical_suggestions_across_queries(pg_dsn):
    # Two distinct slow queries (different queryid) that both boil down to
    # the same (schema, table, columns) suggestion must produce exactly one
    # metrics row, not one per queryid.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text)"
    with _fixtures_sql.make_schema(conn, "advtest5", ddl):
        rows = [
            {"queryid": "1", "query": 'SELECT * FROM "advtest5".orders WHERE org_id = 5'},
            {"queryid": "2", "query": 'SELECT * FROM "advtest5".orders WHERE org_id = 99'},
        ]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert len(diag["metrics"]) == 1
        assert diag["metrics"][0]["queryid"] == "1"
    conn.close()

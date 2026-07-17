import psycopg2
import pytest

from scripts.collectors.stale_stats import collect, modified_pct
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_modified_pct_edges():
    assert modified_pct(0, 5) is None
    assert modified_pct(100, 50) == 50.0
    assert modified_pct(100, 0) == 0.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_unanalyzed_table(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "stale_test", "CREATE TABLE {s}.t (id int primary key)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "stale_test".t (id) VALUES (1), (2), (3)')
            diag = collect(conn, {})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    assert diag["scope"] == "table"
    row = next(m for m in diag["metrics"] if m["table"] == "t")
    assert row["n_mod_since_analyze"] >= 3
    assert row["last_analyze"] is None
    assert row["last_autoanalyze"] is None

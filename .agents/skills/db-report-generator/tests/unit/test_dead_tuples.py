import psycopg2
import pytest

from scripts.collectors.dead_tuples import collect, dead_pct
from tests.pgcontainer import docker_available


def test_dead_pct_formula_edges():
    assert dead_pct(0, 5) == 100.0        # all dead, no live -> 100 (was 0 in v3)
    assert dead_pct(100, 0) == 0.0
    assert dead_pct(50, 50) == 50.0
    assert dead_pct(0, 0) == 0.0          # no rows -> 0, no ZeroDivision


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_runs_and_rows_are_wellformed(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    for m in diag["metrics"]:
        assert m["n_dead"] > 0
        assert 0.0 <= m["dead_pct"] <= 100.0
        assert set(m) == {"schema", "table", "n_live", "n_dead", "dead_pct"}

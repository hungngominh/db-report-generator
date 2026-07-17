import psycopg2
import pytest

from scripts.collectors.database_stats import cache_hit_ratio, collect
from tests.pgcontainer import docker_available


def test_cache_hit_ratio_edges():
    assert cache_hit_ratio(0, 0) is None
    assert cache_hit_ratio(100, 0) == 1.0
    assert cache_hit_ratio(0, 100) == 0.0
    assert cache_hit_ratio(90, 10) == 0.9


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_returns_one_row_for_current_database(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "database"
    assert len(diag["metrics"]) == 1
    row = diag["metrics"][0]
    assert set(row) == {
        "numbackends", "xact_commit", "xact_rollback", "blks_read", "blks_hit",
        "cache_hit_ratio", "tup_returned", "tup_fetched", "tup_inserted", "tup_updated",
        "tup_deleted", "conflicts", "temp_files", "temp_bytes", "deadlocks", "stats_reset",
    }
    assert row["numbackends"] >= 1

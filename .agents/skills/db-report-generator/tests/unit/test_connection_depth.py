import psycopg2
import pytest

from scripts.collectors.connection_depth import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_scoped_and_cluster_counts(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"configured_pool_size": 20})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    row = diag["metrics"][0]
    assert row["db_connections"] >= 1
    assert row["cluster_connections"] >= row["db_connections"]
    assert row["cluster_max_connections"] > 0
    assert row["configured_pool_size"] == 20


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_pool_size_defaults_to_none(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["metrics"][0]["configured_pool_size"] is None

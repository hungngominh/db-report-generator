import psycopg2
import pytest

from scripts.collectors.replication import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_is_ok_and_empty_with_no_replication_configured(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "cluster"
    assert diag["metrics"] == []

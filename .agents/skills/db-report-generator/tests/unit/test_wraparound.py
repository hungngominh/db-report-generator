import psycopg2
import pytest

from scripts.collectors.wraparound import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_returns_database_and_table_rows(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "database"
    levels = {m["level"] for m in diag["metrics"]}
    assert "database" in levels
    for m in diag["metrics"]:
        assert m["xid_age"] >= 0
        assert m["autovacuum_freeze_max_age"] > 0
        assert m["vacuum_failsafe_age"] is not None


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_failsafe_fields_are_none_before_pg14(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 130000})
    finally:
        conn.close()
    assert all(m["vacuum_failsafe_age"] is None for m in diag["metrics"])
    assert all(m["vacuum_multixact_failsafe_age"] is None for m in diag["metrics"])

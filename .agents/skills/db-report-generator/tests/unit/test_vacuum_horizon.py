import psycopg2
import pytest

from scripts.collectors.vacuum_horizon import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_own_backend_xmin(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    backend_rows = [m for m in diag["metrics"] if m["level"] == "backend"]
    assert len(backend_rows) >= 1
    assert all(m["xmin_age"] is not None for m in backend_rows)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_prepared_xacts_empty_by_default(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert [m for m in diag["metrics"] if m["level"] == "prepared_xact"] == []

import psycopg2
import pytest

from scripts.collectors.stat_io import collect
from tests.pgcontainer import docker_available


def test_collect_skips_before_pg16():
    diag = collect(None, {"server_version_num": 150006})
    assert diag["status"] == "skipped"
    assert "16" in diag["reason"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_nulls_timing_columns_when_track_io_timing_is_off(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        # postgres:16 fixture image default is track_io_timing = off
        diag = collect(conn, {"server_version_num": 160000, "track_io_timing": False})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert len(diag["metrics"]) > 0
    for row in diag["metrics"]:
        assert row["read_time_ms"] is None
        assert row["write_time_ms"] is None
        assert row["extend_time_ms"] is None
        assert row["fsync_time_ms"] is None
        assert row["reads"] is not None  # non-timing counters still reported

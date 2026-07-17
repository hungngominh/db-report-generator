import psycopg2
import pytest

from scripts.collectors.checkpoint_activity import (
    _use_checkpointer, checkpoints_req_ratio, collect,
)
from tests.pgcontainer import docker_available


def test_use_checkpointer_version_gate():
    assert _use_checkpointer(170000) is True
    assert _use_checkpointer(160005) is False
    assert _use_checkpointer(140000) is False


def test_checkpoints_req_ratio_edges():
    assert checkpoints_req_ratio(0, 0) is None
    assert checkpoints_req_ratio(10, 0) == 0.0
    assert checkpoints_req_ratio(0, 10) == 1.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_uses_bgwriter_on_pg16(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "cluster"
    row = diag["metrics"][0]
    assert row["source_view"] == "pg_stat_bgwriter"
    assert row["checkpoints_timed"] >= 0
    assert row["buffers_written"] >= 0

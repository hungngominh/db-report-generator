import psycopg2
import pytest

from scripts.collectors import wait_events
from scripts.collectors.wait_events import _aggregate, collect
from tests.pgcontainer import docker_available


def test_aggregate_combines_counts_across_samples():
    samples = [
        [("Lock", "relation"), ("IO", "DataFileRead")],
        [("Lock", "relation")],
        [(None, None)],
    ]
    # collect() normalizes None -> "CPU" in SQL; _aggregate takes rows as-is.
    counts = _aggregate(samples)
    assert counts[("Lock", "relation")] == 2
    assert counts[("IO", "DataFileRead")] == 1
    assert counts[(None, None)] == 1


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_is_insufficient_activity_when_idle(pg_dsn, monkeypatch):
    monkeypatch.setattr(wait_events, "SAMPLES", 2)
    monkeypatch.setattr(wait_events, "INTERVAL_SECONDS", 0.1)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["quality"]["insufficient_activity"] is True
    assert diag["metrics"] == []

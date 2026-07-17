import psycopg2
import pytest

from scripts.sampler import sample_pg_stat_statements_window, snapshot_pg_stat_statements
from tests.pgcontainer import docker_available

SCHEMA = "public"


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_snapshot_shape(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        snap = snapshot_pg_stat_statements(conn, SCHEMA)
    finally:
        conn.close()
    assert set(snap) == {"stats_reset", "postmaster_start", "rows"}
    assert isinstance(snap["rows"], dict)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_window_reflects_only_activity_during_the_window(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            cur.execute("SELECT pg_stat_statements_reset()")
            for _ in range(3):
                cur.execute("SELECT 918273645 /* sampler_marker */")  # before the window

        def run_during_window(_seconds):
            with conn.cursor() as cur:
                for _ in range(4):
                    cur.execute("SELECT 918273645 /* sampler_marker */")

        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=run_during_window)
    finally:
        conn.close()
    assert result["reset_detected"] is False
    match = [d for d in result["deltas"] if "918273645" in d["query"]]
    assert len(match) == 1
    assert match[0]["window_calls"] == 4


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_reset_mid_window_is_detected_and_invalidates_the_window(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

        def reset_during_window(_seconds):
            with conn.cursor() as cur:
                cur.execute("SELECT pg_stat_statements_reset()")

        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=reset_during_window)
    finally:
        conn.close()
    assert result["reset_detected"] is True
    assert result["deltas"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_sample_records_window_seconds_and_both_timestamps(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=lambda _s: None)
    finally:
        conn.close()
    assert result["window_seconds"] == 0
    assert result["sample1_at"] and result["sample2_at"]
    assert result["sample1_at"] <= result["sample2_at"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_each_snapshot_leaves_no_open_transaction(pg_dsn):
    # Roadmap gate "cung-txn -> phat hien" (same-transaction -> detected):
    # lib.db.connect() uses autocommit=True, so every snapshot statement is
    # its own transaction by construction. Prove it directly here rather
    # than only by code inspection: psycopg2 reports TRANSACTION_STATUS_IDLE
    # immediately after each snapshot call, so nothing carries a snapshot
    # across the two samples the way a shared open transaction would.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        snapshot_pg_stat_statements(conn, SCHEMA)
        assert conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
        snapshot_pg_stat_statements(conn, SCHEMA)
        assert conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_qualifies_with_extension_schema_not_search_path(pg_dsn):
    # Same proof as index_bloat's schema-qualification test (P0b): a bogus
    # schema must make the call fail rather than silently falling back to
    # search_path.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        with pytest.raises(psycopg2.Error):
            snapshot_pg_stat_statements(conn, "no_such_schema")
    finally:
        conn.close()

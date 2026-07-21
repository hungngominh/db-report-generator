from datetime import date

from monitor import retention
from monitor.config import MonitorConfig
from storage import db as storage_db


def _cfg(storage_dsn="postgresql://x"):
    return MonitorConfig(
        target_host="h", target_port=5432, target_db="d", target_user="u",
        target_password="p", target_name="t", storage_dsn=storage_dsn,
    )


def test_maybe_run_retention_skips_when_already_run_today():
    def fail_connect(dsn):
        raise AssertionError("connect_fn should not be called when already run today")

    today = date(2026, 7, 21)
    result = retention.maybe_run_retention(
        _cfg(), today, today_fn=lambda: today, connect_fn=fail_connect)

    assert result == today


def test_maybe_run_retention_deletes_old_samples(storage_dsn_url):
    cfg = _cfg(storage_dsn_url)
    conn = storage_db.connect(storage_dsn_url)
    storage_db.init_schema(conn)
    target_id = storage_db.ensure_target(conn, "t")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO samples (target_id, collector, tier, collected_at, payload) "
            "VALUES (%s, 'connection_depth', 'light', now() - interval '40 days', '{}'::jsonb)",
            (target_id,),
        )
    conn.close()

    today = date(2026, 7, 21)
    result = retention.maybe_run_retention(cfg, None, today_fn=lambda: today)

    assert result == today

    verify_conn = storage_db.connect(storage_dsn_url)
    with verify_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM samples WHERE target_id = %s", (target_id,))
        count = cur.fetchone()[0]
    verify_conn.close()
    assert count == 0

"""Daily retention cleanup, gated by date so it runs at most once per day
regardless of how often the caller (the heavy-tier loop) checks."""
from datetime import date

from storage import db as storage_db


def maybe_run_retention(cfg, last_run_date, *, today_fn=date.today,
                         connect_fn=storage_db.connect,
                         delete_fn=storage_db.delete_old_samples):
    today = today_fn()
    if last_run_date == today:
        return last_run_date
    conn = connect_fn(cfg.storage_dsn)
    try:
        delete_fn(conn, cfg.retention_days)
    finally:
        conn.close()
    return today

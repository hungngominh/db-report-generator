"""P2.5 — WAL volume (cumulative since reset) + HOT update ratio per table."""
from scripts.collectors import base

_WAL_SQL = """
SELECT wal_records, wal_fpi, wal_bytes, wal_buffers_full, stats_reset
FROM pg_stat_wal
"""

_HOT_SQL = """
SELECT schemaname, relname, n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC
LIMIT 20
"""


def hot_update_ratio(n_tup_upd, n_tup_hot_upd):
    return round(n_tup_hot_upd / n_tup_upd, 4) if n_tup_upd > 0 else None


def collect(conn, caps):
    metrics = []
    if caps.get("server_version_num", 0) >= 140000:
        with conn.cursor() as cur:
            cur.execute(_WAL_SQL)
            row = cur.fetchone()
        if row is not None:
            wal_records, wal_fpi, wal_bytes, wal_buffers_full, stats_reset = row
            metrics.append({
                "level": "wal", "wal_records": wal_records, "wal_fpi": wal_fpi,
                "wal_bytes": int(wal_bytes) if wal_bytes is not None else None,
                "wal_buffers_full": wal_buffers_full,
                "stats_reset": stats_reset.isoformat() if stats_reset else None,
            })

    with conn.cursor() as cur:
        cur.execute(_HOT_SQL)
        hot_rows = cur.fetchall()
    metrics += [
        {"level": "table", "schema": r[0], "table": r[1], "n_tup_upd": r[2], "n_tup_hot_upd": r[3],
         "hot_update_ratio": hot_update_ratio(r[2], r[3])}
        for r in hot_rows
    ]
    return base.diagnostic("database", "ok", metrics)

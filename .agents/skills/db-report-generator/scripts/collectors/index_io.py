"""P2.6 — index-level cache/IO (cumulative since reset)."""
from scripts.collectors import base

_SQL = """
SELECT sio.schemaname, sio.relname, sio.indexrelname, sio.idx_blks_read, sio.idx_blks_hit,
       COALESCE(sui.idx_scan, 0)
FROM pg_statio_user_indexes sio
JOIN pg_stat_user_indexes sui USING (indexrelid)
ORDER BY sio.idx_blks_read DESC
LIMIT 30
"""


def cache_hit_ratio(idx_blks_hit, idx_blks_read):
    total = idx_blks_hit + idx_blks_read
    return round(idx_blks_hit / total, 4) if total > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "index": r[2], "idx_blks_read": r[3], "idx_blks_hit": r[4],
         "cache_hit_ratio": cache_hit_ratio(r[4], r[3]), "idx_scan": r[5]}
        for r in rows
    ]
    return base.diagnostic("index", "ok", metrics)

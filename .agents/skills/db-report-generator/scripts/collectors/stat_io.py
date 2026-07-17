"""P2.12 — pg_stat_io (PG16+), gated by track_io_timing (B5: unknown, never 0)."""
from scripts.collectors import base

_SQL = """
SELECT backend_type, object, context, reads, writes, hits,
       read_time, write_time, extend_time, fsync_time
FROM pg_stat_io
"""


def collect(conn, caps):
    if caps.get("server_version_num", 0) < 160000:
        return base.skipped("cluster", "pg_stat_io requires PostgreSQL 16+")

    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()

    track_io_timing = bool(caps.get("track_io_timing"))
    metrics = []
    for (backend_type, obj, context, reads, writes, hits,
         read_time, write_time, extend_time, fsync_time) in rows:
        metrics.append({
            "backend_type": backend_type, "object": obj, "context": context,
            "reads": reads, "writes": writes, "hits": hits,
            "read_time_ms": read_time if track_io_timing else None,
            "write_time_ms": write_time if track_io_timing else None,
            "extend_time_ms": extend_time if track_io_timing else None,
            "fsync_time_ms": fsync_time if track_io_timing else None,
        })
    return base.diagnostic("cluster", "ok", metrics)

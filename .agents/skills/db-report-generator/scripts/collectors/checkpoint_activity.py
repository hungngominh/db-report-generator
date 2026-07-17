"""P2.4 — checkpoint/bgwriter activity, version-guarded (pg_stat_checkpointer is PG17+)."""
from scripts.collectors import base

_CHECKPOINTER_SQL = """
SELECT num_timed, num_requested, write_time, sync_time, buffers_written, stats_reset
FROM pg_stat_checkpointer
"""

_BGWRITER_SQL = """
SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
       buffers_checkpoint, stats_reset
FROM pg_stat_bgwriter
"""


def _use_checkpointer(server_version_num):
    return server_version_num >= 170000


def checkpoints_req_ratio(checkpoints_timed, checkpoints_req):
    total = checkpoints_timed + checkpoints_req
    return round(checkpoints_req / total, 4) if total > 0 else None


def collect(conn, caps):
    use_checkpointer = _use_checkpointer(caps.get("server_version_num", 0))
    sql = _CHECKPOINTER_SQL if use_checkpointer else _BGWRITER_SQL
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    if row is None:
        return base.skipped("cluster", "no row returned from checkpoint/bgwriter stats view")

    checkpoints_timed, checkpoints_req, write_time_ms, sync_time_ms, buffers_written, stats_reset = row
    metrics = [{
        "source_view": "pg_stat_checkpointer" if use_checkpointer else "pg_stat_bgwriter",
        "checkpoints_timed": checkpoints_timed,
        "checkpoints_req": checkpoints_req,
        "checkpoints_req_ratio": checkpoints_req_ratio(checkpoints_timed, checkpoints_req),
        "write_time_ms": write_time_ms,
        "sync_time_ms": sync_time_ms,
        "buffers_written": buffers_written,
        "stats_reset": stats_reset.isoformat() if stats_reset else None,
    }]
    return base.diagnostic("cluster", "ok", metrics)

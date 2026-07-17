"""P2.10 — session blocking graph via pg_blocking_pids(). Empty is healthy."""
from scripts.collectors import base

_SQL = """
SELECT blocked.pid, blocked.usename, blocking.pid, blocking.usename,
       blocked.query, blocking.query,
       EXTRACT(EPOCH FROM (now() - blocked.query_start))::float8
FROM pg_stat_activity blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS bp(pid) ON true
JOIN pg_stat_activity blocking ON blocking.pid = bp.pid
WHERE blocked.datname = current_database()
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"blocked_pid": r[0], "blocked_user": r[1], "blocking_pid": r[2], "blocking_user": r[3],
         "blocked_query": r[4], "blocking_query": r[5], "blocked_duration_seconds": r[6]}
        for r in rows
    ]
    return base.diagnostic("database", "ok", metrics)

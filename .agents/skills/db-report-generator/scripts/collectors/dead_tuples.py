"""P0.4 — dead-tuple ratio with the correct denominator (n_live + n_dead)."""
from scripts.collectors import base

_SQL = """
SELECT schemaname, relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE n_dead_tup > 0
ORDER BY n_dead_tup DESC
"""


def dead_pct(n_live, n_dead):
    total = n_live + n_dead
    if total <= 0:
        return 0.0
    return round(n_dead / total * 100, 2)


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "n_live": int(r[2]), "n_dead": int(r[3]),
         "dead_pct": dead_pct(int(r[2]), int(r[3]))}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)

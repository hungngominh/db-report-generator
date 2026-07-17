"""P2.7 — stale table statistics: modified rows vs. analyze cadence."""
from scripts.collectors import base

_SQL = """
SELECT schemaname, relname, n_live_tup, n_mod_since_analyze, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_mod_since_analyze DESC
LIMIT 30
"""


def modified_pct(n_live_tup, n_mod_since_analyze):
    return round(n_mod_since_analyze / n_live_tup * 100, 2) if n_live_tup > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = []
    for schema, table, n_live, n_mod, last_analyze, last_autoanalyze in rows:
        candidates = [t for t in (last_analyze, last_autoanalyze) if t is not None]
        last_analyzed_at = max(candidates) if candidates else None
        metrics.append({
            "schema": schema, "table": table, "n_live_tup": n_live, "n_mod_since_analyze": n_mod,
            "modified_pct": modified_pct(n_live, n_mod),
            "last_analyze": last_analyze.isoformat() if last_analyze else None,
            "last_autoanalyze": last_autoanalyze.isoformat() if last_autoanalyze else None,
            "last_analyzed_at": last_analyzed_at.isoformat() if last_analyzed_at else None,
        })
    return base.diagnostic("table", "ok", metrics)

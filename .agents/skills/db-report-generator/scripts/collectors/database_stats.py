"""P2.2 — pg_stat_database: cumulative-since-reset counters + cache hit ratio."""
from scripts.collectors import base

_SQL = """
SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       conflicts, temp_files, temp_bytes, deadlocks, stats_reset
FROM pg_stat_database
WHERE datname = current_database()
"""


def cache_hit_ratio(blks_hit, blks_read):
    total = blks_hit + blks_read
    return round(blks_hit / total, 4) if total > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        row = cur.fetchone()
    if row is None:
        return base.skipped("database", "no pg_stat_database row for current_database()")
    (numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
     tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
     conflicts, temp_files, temp_bytes, deadlocks, stats_reset) = row
    metrics = [{
        "numbackends": numbackends, "xact_commit": xact_commit, "xact_rollback": xact_rollback,
        "blks_read": blks_read, "blks_hit": blks_hit,
        "cache_hit_ratio": cache_hit_ratio(blks_hit, blks_read),
        "tup_returned": tup_returned, "tup_fetched": tup_fetched, "tup_inserted": tup_inserted,
        "tup_updated": tup_updated, "tup_deleted": tup_deleted, "conflicts": conflicts,
        "temp_files": temp_files, "temp_bytes": temp_bytes, "deadlocks": deadlocks,
        "stats_reset": stats_reset.isoformat() if stats_reset else None,
    }]
    return base.diagnostic("database", "ok", metrics)

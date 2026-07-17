"""P2.8 — connection depth, explicitly scoped: db-scoped counts never compared to
cluster-wide max_connections without both being clearly labeled (the v3 bug)."""
from scripts.collectors import base

_SQL = """
SELECT
    count(*) FILTER (WHERE datname = current_database()) AS db_connections,
    count(*) AS cluster_connections,
    count(*) FILTER (WHERE datname = current_database() AND state = 'idle in transaction')
        AS idle_in_transaction,
    max(EXTRACT(EPOCH FROM (now() - xact_start)))
        FILTER (WHERE datname = current_database() AND xact_start IS NOT NULL) AS longest_txn_seconds
FROM pg_stat_activity
"""

_MAX_CONNECTIONS_SQL = "SELECT current_setting('max_connections')::int"


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        db_connections, cluster_connections, idle_in_transaction, longest_txn_seconds = cur.fetchone()
        cur.execute(_MAX_CONNECTIONS_SQL)
        cluster_max_connections = cur.fetchone()[0]

    metrics = [{
        "db_connections": db_connections,
        "cluster_connections": cluster_connections,
        "cluster_max_connections": cluster_max_connections,
        "idle_in_transaction": idle_in_transaction,
        "longest_txn_seconds": longest_txn_seconds,
        "configured_pool_size": caps.get("configured_pool_size"),
    }]
    return base.diagnostic("database", "ok", metrics)

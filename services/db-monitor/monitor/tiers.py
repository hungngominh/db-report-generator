"""Static assignment of existing db-report-generator collectors to sampling
tiers. fk_missing_index, rls_policies, and schema_checks are DDL/structure
checks, not time-series metrics -- deliberately excluded from Core (DDL
drift detection is a deferred sub-project, see the design spec)."""

LIGHT_COLLECTOR_NAMES = [
    "connection_depth", "database_stats", "wait_events", "checkpoint_activity",
    "wal_hot", "replication", "blocking", "vacuum_horizon", "wraparound",
    "index_io", "stat_io", "dead_tuples", "stale_stats", "query_stats",
]

HEAVY_COLLECTOR_NAMES = [
    "index_bloat", "duplicate_index", "table_index_size",
]


def build_registry(names):
    from scripts.collectors import COLLECTORS
    return {name: COLLECTORS[name] for name in names}

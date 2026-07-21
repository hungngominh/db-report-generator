from monitor import tiers


def test_light_and_heavy_collector_lists_are_exact():
    assert tiers.LIGHT_COLLECTOR_NAMES == [
        "connection_depth", "database_stats", "wait_events", "checkpoint_activity",
        "wal_hot", "replication", "blocking", "vacuum_horizon", "wraparound",
        "index_io", "stat_io", "dead_tuples", "stale_stats", "query_stats",
    ]
    assert tiers.HEAVY_COLLECTOR_NAMES == [
        "index_bloat", "duplicate_index", "table_index_size",
    ]


def test_no_overlap_between_tiers():
    assert set(tiers.LIGHT_COLLECTOR_NAMES) & set(tiers.HEAVY_COLLECTOR_NAMES) == set()


def test_build_registry_returns_real_collector_callables():
    from scripts.collectors import COLLECTORS

    registry = tiers.build_registry(tiers.LIGHT_COLLECTOR_NAMES)

    assert set(registry.keys()) == set(tiers.LIGHT_COLLECTOR_NAMES)
    for name in tiers.LIGHT_COLLECTOR_NAMES:
        assert registry[name] is COLLECTORS[name]

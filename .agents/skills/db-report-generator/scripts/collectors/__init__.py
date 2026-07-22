"""Collector registry + isolated runner."""
from scripts.collectors import base

# Each collector module appends itself here (name -> collect callable).
COLLECTORS = {}

from scripts.collectors import fk_missing_index

COLLECTORS["fk_missing_index"] = fk_missing_index.collect

from scripts.collectors import duplicate_index

COLLECTORS["duplicate_index"] = duplicate_index.collect

from scripts.collectors import index_bloat

COLLECTORS["index_bloat"] = index_bloat.collect

from scripts.collectors import dead_tuples

COLLECTORS["dead_tuples"] = dead_tuples.collect

from scripts.collectors import table_index_size

COLLECTORS["table_index_size"] = table_index_size.collect

from scripts.collectors import query_stats

COLLECTORS["query_stats"] = query_stats.collect

from scripts.collectors import wraparound

COLLECTORS["wraparound"] = wraparound.collect

from scripts.collectors import database_stats

COLLECTORS["database_stats"] = database_stats.collect

from scripts.collectors import wait_events

COLLECTORS["wait_events"] = wait_events.collect

from scripts.collectors import checkpoint_activity

COLLECTORS["checkpoint_activity"] = checkpoint_activity.collect

from scripts.collectors import wal_hot

COLLECTORS["wal_hot"] = wal_hot.collect

from scripts.collectors import index_io

COLLECTORS["index_io"] = index_io.collect

from scripts.collectors import stale_stats

COLLECTORS["stale_stats"] = stale_stats.collect

from scripts.collectors import connection_depth

COLLECTORS["connection_depth"] = connection_depth.collect

from scripts.collectors import replication

COLLECTORS["replication"] = replication.collect

from scripts.collectors import blocking

COLLECTORS["blocking"] = blocking.collect

from scripts.collectors import vacuum_horizon

COLLECTORS["vacuum_horizon"] = vacuum_horizon.collect

from scripts.collectors import stat_io

COLLECTORS["stat_io"] = stat_io.collect

from scripts.collectors import rls_policies

COLLECTORS["rls_policies"] = rls_policies.collect

from scripts.collectors import schema_checks

COLLECTORS["schema_checks"] = schema_checks.collect

from scripts.collectors import seq_scan

COLLECTORS["seq_scan"] = seq_scan.collect


def run_collectors(conn, caps, registry=None, *, sampling=None):
    """Run every collector with per-collector isolation.

    A collector that raises is recorded as an ``error`` diagnostic (reason =
    the exception class name — never the message, to avoid leaking identifiers)
    and does not abort the others. ``sampling`` (the per-target windowed
    pg_stat_statements deltas, or None) is merged into a *copy* of ``caps``
    so the caller's own ``caps``/``target["capabilities"]`` dict is never
    mutated and never carries the raw sampling payload.
    """
    reg = registry if registry is not None else COLLECTORS
    merged_caps = {**caps, "sampling": sampling}
    out = {}
    for name, fn in reg.items():
        try:
            out[name] = fn(conn, merged_caps)
        except Exception as exc:  # noqa: BLE001 - isolate per-collector failure
            out[name] = base.diagnostic(
                "table", "error", [], reason=type(exc).__name__)
    return out

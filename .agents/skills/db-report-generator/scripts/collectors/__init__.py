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

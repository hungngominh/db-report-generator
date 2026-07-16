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


def run_collectors(conn, caps, registry=None):
    """Run every collector with per-collector isolation.

    A collector that raises is recorded as an ``error`` diagnostic (reason =
    the exception class name — never the message, to avoid leaking identifiers)
    and does not abort the others.
    """
    reg = registry if registry is not None else COLLECTORS
    out = {}
    for name, fn in reg.items():
        try:
            out[name] = fn(conn, caps)
        except Exception as exc:  # noqa: BLE001 - isolate per-collector failure
            out[name] = base.diagnostic(
                "table", "error", [], reason=type(exc).__name__)
    return out

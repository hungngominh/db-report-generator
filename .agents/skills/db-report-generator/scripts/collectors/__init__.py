"""Collector registry + isolated runner."""
from scripts.collectors import base

# Each collector module appends itself here (name -> collect callable).
COLLECTORS = {}


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

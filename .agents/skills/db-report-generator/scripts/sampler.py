"""Delta sampling of pg_stat_statements (spec §6 P1.1 + §0.A2 + §0.B2).

Two cumulative snapshots, `window_seconds` apart, reduce to per-queryid
window deltas. Windowed formulas only (Δtotal/Δcalls, ...) — never a naive
mean2-mean1 or stddev2-stddev1 subtraction (forbidden by spec §0.A2).
"""
import time
from datetime import datetime, timezone

import psycopg2.sql as sql

_ZERO_ROW = {
    "query": "", "calls": 0, "total_exec_time": 0.0, "rows": 0,
    "mean_exec_time": 0.0, "stddev_exec_time": 0.0,
    "shared_blks_read": 0, "temp_blks_read": 0, "temp_blks_written": 0,
}

_SNAPSHOT_SQL = """
SELECT queryid::text, query, calls, total_exec_time, rows, mean_exec_time,
       stddev_exec_time, shared_blks_read, temp_blks_read, temp_blks_written
FROM {pgss}
"""
_INFO_SQL = "SELECT stats_reset FROM {info}"


def combined_stddev(n1: int, mean1: float, stddev1: float,
                     n2: int, mean2: float, stddev2: float) -> float:
    """Population stddev of the (n2-n1) delta subset, from two cumulative
    (count, mean, population-stddev) snapshots. Exact via the sum-of-squares
    identity SS = n*(stddev**2 + mean**2); never stddev2-stddev1.
    """
    dn = n2 - n1
    if dn <= 0:
        return 0.0
    ss1 = n1 * (stddev1 ** 2 + mean1 ** 2)
    ss2 = n2 * (stddev2 ** 2 + mean2 ** 2)
    delta_sum = n2 * mean2 - n1 * mean1
    delta_mean = delta_sum / dn
    variance = max((ss2 - ss1) / dn - delta_mean ** 2, 0.0)
    return variance ** 0.5


def reset_between(snap1: dict, snap2: dict) -> bool:
    """True if pg_stat_statements was reset or the server restarted between
    the two snapshots (spec §0.A2) — invalidates the whole sampling window.
    """
    return (snap1["stats_reset"] != snap2["stats_reset"]
            or snap1["postmaster_start"] != snap2["postmaster_start"])


def compute_deltas(snap1: dict, snap2: dict) -> dict:
    """Turn two pg_stat_statements snapshots into windowed deltas.

    A global reset/restart invalidates the whole window (empty deltas,
    reset_detected=True — spec §0.A2). Per-queryid eviction — calls
    decreased between the two samples (spec §0.B2) — drops only that
    entry, not the whole window. A queryid absent from snapshot 1 is a
    legitimately new query: its full calls count occurred inside the
    window, not an eviction case.
    """
    if reset_between(snap1, snap2):
        return {"reset_detected": True, "deltas": []}

    deltas = []
    for queryid, row2 in snap2["rows"].items():
        row1 = snap1["rows"].get(queryid, _ZERO_ROW)
        if row2["calls"] < row1["calls"]:
            continue  # per-entry eviction+recreation (B2) — drop this entry only
        window_calls = row2["calls"] - row1["calls"]
        if window_calls == 0:
            continue
        window_total = row2["total_exec_time"] - row1["total_exec_time"]
        window_rows = row2["rows"] - row1["rows"]
        stddev = combined_stddev(
            row1["calls"], row1["mean_exec_time"], row1["stddev_exec_time"],
            row2["calls"], row2["mean_exec_time"], row2["stddev_exec_time"],
        )
        deltas.append({
            "queryid": queryid,
            "query": row2["query"],
            "window_calls": window_calls,
            "window_total_exec_time_ms": window_total,
            "window_mean_exec_time_ms": window_total / window_calls,
            "window_stddev_exec_time_ms": stddev,
            "window_rows_per_call": window_rows / window_calls,
            "window_shared_blks_read": row2["shared_blks_read"] - row1["shared_blks_read"],
            "window_temp_blks_read": row2["temp_blks_read"] - row1["temp_blks_read"],
            "window_temp_blks_written": row2["temp_blks_written"] - row1["temp_blks_written"],
        })
    deltas.sort(key=lambda d: (-d["window_total_exec_time_ms"], d["queryid"]))
    return {"reset_detected": False, "deltas": deltas}


def snapshot_pg_stat_statements(conn, schema: str) -> dict:
    """Placeholder — implemented in Task 3."""
    raise NotImplementedError


def sample_pg_stat_statements_window(conn, schema: str, window_seconds: int,
                                      *, sleep_fn=time.sleep) -> dict:
    """Placeholder — implemented in Task 3."""
    raise NotImplementedError

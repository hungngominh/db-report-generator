"""P1.2 — pg_stat_statements 3-axis windowed query stats (spec §6 P1.2).

Pure transformer: reads the per-target deltas the sampler (P1.1) already
computed out of ``caps["sampling"]`` and reduces them to schema-valid
metrics. Default top-sort is total_exec_time descending (already the
sampler's own sort order — this collector does not re-sort), replacing the
old v3 default of sorting by mean.
"""
from scripts.collectors import base

MINIMUM_ACTIVITY_CALLS = 5  # below this total window calls, deltas are too thin to judge


def collect(conn, caps):
    ext = (caps.get("extensions") or {}).get("pg_stat_statements")
    if not ext:
        return base.skipped(
            "query", "query_stats requires the pg_stat_statements extension (not installed)")
    sampling = caps.get("sampling")
    if sampling is None:
        return base.skipped(
            "query", "no sampling window was collected for this target")

    quality = dict(base.STRUCTURAL_QUALITY)
    if sampling["reset_detected"]:
        quality["sampling_valid"] = False
        quality["reset_detected"] = True
        return base.diagnostic("query", "ok", [], quality=quality)

    deltas = sampling["deltas"]
    total_window_calls = sum(d["window_calls"] for d in deltas)
    if total_window_calls < MINIMUM_ACTIVITY_CALLS:
        quality["insufficient_activity"] = True

    metrics = [
        {
            "queryid": d["queryid"],
            "query": d["query"],
            "window_calls": d["window_calls"],
            "window_total_exec_time_ms": d["window_total_exec_time_ms"],
            "window_mean_exec_time_ms": d["window_mean_exec_time_ms"],
            "window_stddev_exec_time_ms": d["window_stddev_exec_time_ms"],
            "window_rows_per_call": d["window_rows_per_call"],
            "window_shared_blks_read": d["window_shared_blks_read"],
            "window_temp_blks_read": d["window_temp_blks_read"],
            "window_temp_blks_written": d["window_temp_blks_written"],
        }
        for d in deltas
    ]
    return base.diagnostic("query", "ok", metrics, quality=quality)

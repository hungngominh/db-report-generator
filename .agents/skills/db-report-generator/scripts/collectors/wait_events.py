"""P2.3 — multi-sample wait-event distribution over a short window."""
import time
from collections import Counter

from scripts.collectors import base

SAMPLES = 5
INTERVAL_SECONDS = 1.0
# This fixed ~SAMPLES*INTERVAL_SECONDS per-target sleep is not counted by
# analyzer._check_latency_budget's B4 warning (that only sums sampling.window_seconds).

_SQL = """
SELECT wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database() AND pid != pg_backend_pid() AND state = 'active'
"""


def _sample_once(conn):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        return cur.fetchall()


def _aggregate(samples):
    counts = Counter()
    for rows in samples:
        for wait_event_type, wait_event in rows:
            counts[(wait_event_type, wait_event)] += 1
    return counts


def collect(conn, caps, *, samples=None, interval_seconds=None, sleep_fn=time.sleep):
    samples = samples if samples is not None else SAMPLES
    interval_seconds = interval_seconds if interval_seconds is not None else INTERVAL_SECONDS

    all_samples = []
    for i in range(samples):
        all_samples.append(_sample_once(conn))
        if i < samples - 1:
            sleep_fn(interval_seconds)

    counts = _aggregate(all_samples)
    total_observations = sum(counts.values())
    quality = dict(base.STRUCTURAL_QUALITY)
    if total_observations == 0:
        quality["insufficient_activity"] = True
        return base.diagnostic("database", "ok", [], quality=quality)

    metrics = [
        {"wait_event_type": t if t is not None else "CPU", "wait_event": e,
         "sample_count": c, "total_samples": samples}
        for (t, e), c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return base.diagnostic("database", "ok", metrics, quality=quality)

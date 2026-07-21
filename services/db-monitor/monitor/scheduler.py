"""Sequential per-tier sampling loop. Each tier runs its own
`while: run(); sleep()` loop on its own thread -- structurally single-flight,
so no explicit overlap guard is needed. Failures back off exponentially
(base 2s, cap 300s) rather than hammering an unreachable target DB."""
import logging
import threading
import time

from monitor import cycle

logger = logging.getLogger("db-monitor")


def _backoff_seconds(attempt, base=2, cap=300):
    return min(base * (2 ** attempt), cap)


def run_tier_loop(cfg, tier, collector_names, target_id, interval_seconds,
                   *, sampling_window_seconds=None, after_cycle_fn=None,
                   stop_event=None, sleep_fn=time.sleep, run_cycle_fn=cycle.run_cycle):
    stop = stop_event or threading.Event()
    attempt = 0
    while not stop.is_set():
        cycle_start = time.monotonic()
        try:
            run_cycle_fn(cfg, tier, collector_names, target_id,
                         sampling_window_seconds=sampling_window_seconds)
            if after_cycle_fn is not None:
                after_cycle_fn()
            attempt = 0
        except Exception:  # noqa: BLE001 - keep the daemon alive across cycle failures
            logger.exception("%s cycle failed", tier)
            sleep_fn(_backoff_seconds(attempt))
            attempt += 1
            continue
        elapsed = time.monotonic() - cycle_start
        remaining = max(0.0, interval_seconds - elapsed)
        sleep_fn(remaining)

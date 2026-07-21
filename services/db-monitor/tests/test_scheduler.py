import threading

from monitor import scheduler


def test_run_tier_loop_stops_after_stop_event_set():
    calls = []
    stop_event = threading.Event()

    def fake_run_cycle(cfg, tier, names, target_id, sampling_window_seconds=None):
        calls.append(tier)
        if len(calls) >= 3:
            stop_event.set()

    sleeps = []
    scheduler.run_tier_loop(
        cfg=object(), tier="light", collector_names=[], target_id=1,
        interval_seconds=60, stop_event=stop_event,
        sleep_fn=sleeps.append, run_cycle_fn=fake_run_cycle,
    )

    assert calls == ["light", "light", "light"]
    assert len(sleeps) == 3


def test_run_tier_loop_backs_off_on_failure():
    stop_event = threading.Event()
    attempts = []

    def failing_run_cycle(cfg, tier, names, target_id, sampling_window_seconds=None):
        attempts.append(1)
        if len(attempts) >= 3:
            stop_event.set()
        raise RuntimeError("boom")

    sleeps = []
    scheduler.run_tier_loop(
        cfg=object(), tier="light", collector_names=[], target_id=1,
        interval_seconds=60, stop_event=stop_event,
        sleep_fn=sleeps.append, run_cycle_fn=failing_run_cycle,
    )

    assert sleeps == [2, 4, 8]


def test_run_tier_loop_calls_after_cycle_fn_on_success():
    stop_event = threading.Event()
    after_calls = []

    def fake_run_cycle(cfg, tier, names, target_id, sampling_window_seconds=None):
        pass

    def after_cycle():
        after_calls.append(1)
        stop_event.set()

    scheduler.run_tier_loop(
        cfg=object(), tier="heavy", collector_names=[], target_id=1,
        interval_seconds=1800, stop_event=stop_event,
        sleep_fn=lambda s: None, run_cycle_fn=fake_run_cycle,
        after_cycle_fn=after_cycle,
    )

    assert after_calls == [1]

import statistics

import pytest

from scripts.sampler import combined_stddev, compute_deltas, reset_between


def test_combined_stddev_matches_population_stddev_of_delta_subset():
    before = [10.0, 12.0, 11.0, 9.0, 13.0]
    during = [50.0, 55.0, 45.0, 60.0, 40.0, 52.0]
    combined = before + during
    n1, mean1, stddev1 = len(before), statistics.fmean(before), statistics.pstdev(before)
    n2, mean2, stddev2 = len(combined), statistics.fmean(combined), statistics.pstdev(combined)
    result = combined_stddev(n1, mean1, stddev1, n2, mean2, stddev2)
    expected = statistics.pstdev(during)
    assert result == pytest.approx(expected, abs=1e-9)


def test_combined_stddev_zero_delta_calls_returns_zero():
    assert combined_stddev(10, 5.0, 1.0, 10, 5.0, 1.0) == 0.0


def test_combined_stddev_never_equals_naive_subtraction():
    # Regression guard for spec §0.A2: stddev2-stddev1 is forbidden and is
    # not even a valid stddev (can go negative) — the combined formula must
    # produce the true population stddev of the delta subset instead.
    before = [100.0] * 5           # stddev1 == 0
    during = [1.0, 200.0, 5.0, 300.0]
    combined = before + during
    n1, mean1, stddev1 = 5, 100.0, 0.0
    n2, mean2, stddev2 = 9, statistics.fmean(combined), statistics.pstdev(combined)
    result = combined_stddev(n1, mean1, stddev1, n2, mean2, stddev2)
    expected = statistics.pstdev(during)
    assert result == pytest.approx(expected, abs=1e-6)
    assert result != pytest.approx(stddev2 - stddev1)


def _snap(stats_reset, postmaster_start, rows):
    return {"stats_reset": stats_reset, "postmaster_start": postmaster_start, "rows": rows}


def test_reset_between_true_when_stats_reset_changes():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:05:00Z", "2026-01-01T00:00:00Z", {})
    assert reset_between(s1, s2) is True


def test_reset_between_true_when_postmaster_restarts():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z", {})
    assert reset_between(s1, s2) is True


def test_reset_between_false_when_unchanged():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    assert reset_between(s1, s2) is False


_ROW = {"query": "select 1", "calls": 10, "total_exec_time": 100.0, "rows": 10,
        "mean_exec_time": 10.0, "stddev_exec_time": 0.0,
        "shared_blks_read": 5, "temp_blks_read": 0, "temp_blks_written": 0}


def test_compute_deltas_uses_delta_formulas_not_mean_subtraction():
    row1 = {**_ROW, "calls": 10, "total_exec_time": 100.0, "rows": 10, "mean_exec_time": 10.0}
    row2 = {**_ROW, "calls": 14, "total_exec_time": 180.0, "rows": 18, "mean_exec_time": 12.857}
    s1 = _snap("t0", "p0", {"q1": row1})
    s2 = _snap("t0", "p0", {"q1": row2})
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is False
    [d] = result["deltas"]
    assert d["window_calls"] == 4
    assert d["window_total_exec_time_ms"] == pytest.approx(80.0)
    assert d["window_mean_exec_time_ms"] == pytest.approx(20.0)   # 80/4, not 12.857-10.0
    assert d["window_rows_per_call"] == pytest.approx(2.0)        # (18-10)/4
    assert d["window_shared_blks_read"] == 0


def test_compute_deltas_global_reset_yields_empty_and_flag():
    s1 = _snap("t0", "p0", {"q1": _ROW})
    s2 = _snap("t1", "p0", {"q1": _ROW})   # stats_reset changed
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is True
    assert result["deltas"] == []


def test_compute_deltas_drops_only_the_evicted_entry_not_the_whole_window():
    stable = {**_ROW, "calls": 20, "total_exec_time": 200.0, "rows": 20}
    evicted1 = {**_ROW, "calls": 50, "total_exec_time": 5000.0, "rows": 50}
    evicted2 = {**_ROW, "calls": 3, "total_exec_time": 30.0, "rows": 3}   # calls DECREASED -> evicted+recreated
    s1 = _snap("t0", "p0", {"q_stable": stable, "q_evicted": evicted1})
    s2 = _snap("t0", "p0", {"q_stable": {**stable, "calls": 25, "total_exec_time": 250.0, "rows": 25},
                             "q_evicted": evicted2})
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is False
    ids = {d["queryid"] for d in result["deltas"]}
    assert ids == {"q_stable"}   # q_evicted's decreasing-calls entry was dropped, not the whole window


def test_compute_deltas_new_queryid_counts_its_full_window_calls():
    s1 = _snap("t0", "p0", {})
    s2 = _snap("t0", "p0", {"q_new": {**_ROW, "calls": 3, "total_exec_time": 30.0, "rows": 3}})
    result = compute_deltas(s1, s2)
    [d] = result["deltas"]
    assert d["queryid"] == "q_new"
    assert d["window_calls"] == 3


def test_compute_deltas_sorted_by_total_exec_time_desc_then_queryid():
    row_a = {**_ROW, "calls": 100, "total_exec_time": 50.0, "rows": 100}    # low total, high calls
    row_b = {**_ROW, "calls": 2, "total_exec_time": 500.0, "rows": 2}       # high total, low calls
    s1 = _snap("t0", "p0", {})
    s2 = _snap("t0", "p0", {"a": row_a, "b": row_b})
    result = compute_deltas(s1, s2)
    assert [d["queryid"] for d in result["deltas"]] == ["b", "a"]   # total_exec_time desc, not calls

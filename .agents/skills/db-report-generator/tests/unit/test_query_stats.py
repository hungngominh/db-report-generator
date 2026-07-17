from scripts.collectors.query_stats import collect


def test_skips_when_extension_absent():
    diag = collect(conn=None, caps={"extensions": {}})
    assert diag["status"] == "skipped"
    assert "pg_stat_statements" in diag["reason"]
    assert diag["metrics"] == []


def test_skips_when_no_sampling_was_performed():
    caps = {"extensions": {"pg_stat_statements": {"present": True, "schema": "public"}}}
    diag = collect(conn=None, caps=caps)
    assert diag["status"] == "skipped"
    assert diag["metrics"] == []


def test_reset_detected_marks_quality_invalid_and_empties_metrics():
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": True, "deltas": [], "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["status"] == "ok"
    assert diag["quality"]["sampling_valid"] is False
    assert diag["quality"]["reset_detected"] is True
    assert diag["metrics"] == []


def test_zero_workload_marks_insufficient_activity():
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": False, "deltas": [], "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["quality"]["sampling_valid"] is True
    assert diag["quality"]["insufficient_activity"] is True
    assert diag["metrics"] == []


def _delta(queryid, calls, total_ms):
    return {"queryid": queryid, "query": f"select {queryid}", "window_calls": calls,
            "window_total_exec_time_ms": total_ms, "window_mean_exec_time_ms": total_ms / calls,
            "window_stddev_exec_time_ms": 0.5, "window_rows_per_call": 1.0,
            "window_shared_blks_read": 0, "window_temp_blks_read": 0, "window_temp_blks_written": 0}


def test_active_window_reports_metrics_sorted_by_total_time_not_calls():
    deltas = [
        _delta("1", calls=3, total_ms=300.0),    # low calls, high total time
        _delta("2", calls=50, total_ms=50.0),    # high calls, low total time
    ]
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": False, "deltas": deltas, "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["quality"]["insufficient_activity"] is False
    assert [m["queryid"] for m in diag["metrics"]] == ["1", "2"]
    m = diag["metrics"][0]
    assert set(m) == {"queryid", "query", "window_calls", "window_total_exec_time_ms",
                       "window_mean_exec_time_ms", "window_stddev_exec_time_ms",
                       "window_rows_per_call", "window_shared_blks_read",
                       "window_temp_blks_read", "window_temp_blks_written"}

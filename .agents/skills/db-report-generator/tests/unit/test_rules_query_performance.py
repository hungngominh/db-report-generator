from scripts import rules


def _quality(sampling_valid=True, insufficient_activity=False):
    return {"sampling_valid": sampling_valid, "reset_detected": not sampling_valid,
            "insufficient_activity": insufficient_activity, "truncated": False}


def _rules_by_block():
    catalog = rules.load_catalog()
    by_block = {}
    for axis_rules in catalog.values():
        for rule in axis_rules:
            by_block.setdefault(rule["block"], []).append(rule)
    return by_block


def _query_row(queryid="1", mean_ms=1500.0):
    return {"queryid": queryid, "query": "select 1", "window_calls": 10,
            "window_total_exec_time_ms": mean_ms * 10, "window_mean_exec_time_ms": mean_ms,
            "window_stddev_exec_time_ms": 1.0, "window_rows_per_call": 1.0,
            "window_shared_blks_read": 0, "window_temp_blks_read": 0, "window_temp_blks_written": 0}


def test_slow_query_red_above_1000ms_mean_when_ungated():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "red"
    assert findings[0]["confidence"] == "estimated"
    assert findings[0]["finding_id"] == "query_perf.slow_query_mean_exec_time:1"


def test_slow_query_healthy_fires_nothing():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_query_row(mean_ms=5.0)]}
    assert rules.evaluate_diagnostic("query_stats", diag, _rules_by_block()) == []


def test_b3_sampling_invalid_forces_unknown_heuristic():
    diag = {"status": "ok", "quality": _quality(sampling_valid=False),
            "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "unknown"
    assert findings[0]["confidence"] == "heuristic"


def test_a2_insufficient_activity_forces_unknown_heuristic():
    diag = {"status": "ok", "quality": _quality(insufficient_activity=True),
            "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "unknown"
    assert findings[0]["confidence"] == "heuristic"


def test_gating_does_not_manufacture_findings_for_healthy_values():
    # A2/B3 gate a diagnostic whose value is otherwise green -> still zero findings.
    diag = {"status": "ok", "quality": _quality(sampling_valid=False),
            "metrics": [_query_row(mean_ms=5.0)]}
    assert rules.evaluate_diagnostic("query_stats", diag, _rules_by_block()) == []


def test_index_cache_hit_ratio_yellow_below_90_percent():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "index": "t_idx",
                         "idx_blks_read": 10, "idx_blks_hit": 85, "cache_hit_ratio": 0.85, "idx_scan": 100}]}
    findings = rules.evaluate_diagnostic("index_io", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == "query_perf.index_cache_hit_ratio:public:t:t_idx"

from scripts import rules


def _quality(sampling_valid=True, insufficient_activity=False):
    return {"sampling_valid": sampling_valid, "reset_detected": False,
            "insufficient_activity": insufficient_activity, "truncated": False}


def test_load_catalog_covers_all_five_axes():
    catalog = rules.load_catalog()
    assert set(catalog) == set(rules.AXES)
    assert rules.AXES == ("db-health", "query-performance", "maintenance",
                          "connections", "security-rls")


def test_quality_gated_true_when_sampling_invalid():
    assert rules._quality_gated(_quality(sampling_valid=False)) is True


def test_quality_gated_true_when_insufficient_activity():
    assert rules._quality_gated(_quality(insufficient_activity=True)) is True


def test_quality_gated_false_when_healthy():
    assert rules._quality_gated(_quality()) is False


def test_compare_higher_is_worse():
    thresholds = {"red": 20, "yellow": 5}
    assert rules._compare(25, thresholds, "higher_is_worse") == "red"
    assert rules._compare(10, thresholds, "higher_is_worse") == "yellow"
    assert rules._compare(1, thresholds, "higher_is_worse") == "green"


def test_compare_lower_is_worse():
    thresholds = {"red": 0.80, "yellow": 0.90}
    assert rules._compare(0.5, thresholds, "lower_is_worse") == "red"
    assert rules._compare(0.85, thresholds, "lower_is_worse") == "yellow"
    assert rules._compare(0.99, thresholds, "lower_is_worse") == "green"


_RULE = {
    "finding_id": "test.metric", "title": "Test metric cao", "severity": "warning",
    "kind": "threshold", "block": "some_block", "metric_key": "value",
    "direction": "higher_is_worse", "thresholds": {"red": 20, "yellow": 5},
    "row_identity_fields": ["schema", "table"], "confidence": "measured",
}


def test_eval_threshold_skips_green_rows():
    findings = rules._eval_threshold(_RULE, [{"schema": "public", "table": "t", "value": 1}], gated=False)
    assert findings == []


def test_eval_threshold_skips_rows_missing_the_metric():
    findings = rules._eval_threshold(_RULE, [{"schema": "public", "table": "t"}], gated=False)
    assert findings == []


def test_eval_threshold_fires_with_row_identity_suffix():
    findings = rules._eval_threshold(
        _RULE, [{"schema": "public", "table": "t", "value": 25}], gated=False)
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_id"] == "test.metric:public:t"
    assert f["severity"] == "warning"
    assert f["assessment"] == "red"
    assert f["confidence"] == "measured"
    assert f["evidence_ids"] == ["value=25"]
    assert f["remediation_ids"] == []


def test_eval_threshold_gated_forces_unknown_heuristic_but_keeps_evidence():
    findings = rules._eval_threshold(
        _RULE, [{"schema": "public", "table": "t", "value": 25}], gated=True)
    f = findings[0]
    assert f["assessment"] == "unknown"
    assert f["confidence"] == "heuristic"
    assert f["evidence_ids"] == ["value=25"]  # gating never touches evidence


_RATIO_RULE = {
    "finding_id": "test.ratio", "title": "Test ratio cao", "severity": "critical",
    "kind": "ratio_threshold", "block": "some_block",
    "numerator_key": "num", "denominator_key": "den",
    "direction": "higher_is_worse", "thresholds": {"red": 1.0, "yellow": 0.8},
    "row_identity_fields": [], "confidence": "measured",
}


def test_eval_ratio_threshold_computes_ratio_and_fires():
    findings = rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": 100}], gated=False)
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["evidence_ids"] == ["num=90", "den=100"]


def test_eval_ratio_threshold_skips_zero_or_none_denominator():
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": 0}], gated=False) == []
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": None}], gated=False) == []


def test_eval_ratio_threshold_skips_none_numerator():
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": None, "den": 100}], gated=False) == []


def test_evaluate_diagnostic_returns_empty_for_unregistered_block():
    diag = {"status": "ok", "quality": _quality(), "metrics": [{"value": 99}]}
    assert rules.evaluate_diagnostic("no_such_block", diag, {}) == []


def test_evaluate_diagnostic_returns_empty_for_skipped_status():
    diag = {"status": "skipped", "quality": _quality(), "metrics": []}
    rules_by_block = {"some_block": [_RULE]}
    assert rules.evaluate_diagnostic("some_block", diag, rules_by_block) == []


def test_evaluate_diagnostic_dispatches_by_kind():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "value": 25}]}
    rules_by_block = {"some_block": [_RULE]}
    findings = rules.evaluate_diagnostic("some_block", diag, rules_by_block)
    assert len(findings) == 1
    assert findings[0]["finding_id"] == "test.metric:public:t"


def test_evaluate_target_writes_findings_into_each_diagnostic(monkeypatch):
    monkeypatch.setattr(rules, "load_catalog", lambda: {"db-health": [_RULE]})
    target = {"diagnostics": {
        "some_block": {"status": "ok", "quality": _quality(),
                        "metrics": [{"schema": "public", "table": "t", "value": 25}]},
        "other_block": {"status": "ok", "quality": _quality(), "metrics": []},
    }}
    rules.evaluate_target(target)
    assert len(target["diagnostics"]["some_block"]["findings"]) == 1
    assert target["diagnostics"]["other_block"]["findings"] == []

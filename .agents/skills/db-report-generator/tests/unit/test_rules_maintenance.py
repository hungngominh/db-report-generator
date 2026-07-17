from scripts import rules


def _quality():
    return {"sampling_valid": True, "reset_detected": False,
            "insufficient_activity": False, "truncated": False}


def _rules_by_block():
    catalog = rules.load_catalog()
    by_block = {}
    for axis_rules in catalog.values():
        for rule in axis_rules:
            by_block.setdefault(rule["block"], []).append(rule)
    return by_block


def test_dead_tuples_red_above_20_percent():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "n_live": 80, "n_dead": 20, "dead_pct": 20.0}]}
    findings = rules.evaluate_diagnostic("dead_tuples", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["finding_id"] == "maintenance.dead_tuples_pct:public:t"
    assert findings[0]["assessment"] == "red"


def test_stale_stats_yellow_above_20_percent_modified():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "n_live_tup": 100,
                         "n_mod_since_analyze": 25, "modified_pct": 25.0,
                         "last_analyze": None, "last_autoanalyze": None, "last_analyzed_at": None}]}
    findings = rules.evaluate_diagnostic("stale_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"


def test_index_bloat_notice_severity_and_estimated_confidence():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "table_len": 1000,
                         "dead_tuple_percent": 35.0, "approx_free_percent": 10.0}]}
    findings = rules.evaluate_diagnostic("index_bloat", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["severity"] == "notice"
    assert findings[0]["confidence"] == "estimated"
    assert findings[0]["assessment"] == "red"


def test_duplicate_index_fires_one_per_row_regardless_of_kind():
    metrics = [
        {"kind": "exact_duplicate", "schema": "public", "table": "t", "keep": "t_pkey",
         "members": ["t_pkey", "t_dup_idx"], "drop_candidates": ["t_dup_idx"]},
        {"kind": "potentially_redundant", "schema": "public", "table": "t2",
         "redundant": "t2_a_idx", "covered_by": "t2_a_b_idx"},
    ]
    diag = {"status": "ok", "quality": _quality(), "metrics": metrics}
    findings = rules.evaluate_diagnostic("duplicate_index", diag, _rules_by_block())
    assert len(findings) == 2
    assert all(f["assessment"] == "yellow" for f in findings)
    ids = {f["finding_id"] for f in findings}
    assert "maintenance.duplicate_index:exact_duplicate:public:t:t_pkey" in ids
    assert "maintenance.duplicate_index:potentially_redundant:public:t2:t2_a_idx" in ids


def test_fk_missing_index_fires_red():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "orders", "constraint": "orders_user_id_fkey",
                         "columns": ["user_id"], "suggested_ddl": "CREATE INDEX ..."}]}
    findings = rules.evaluate_diagnostic("fk_missing_index", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "red"
    assert findings[0]["finding_id"] == "maintenance.fk_missing_index:public:orders:orders_user_id_fkey"


def test_schema_hygiene_issue_fires_yellow_for_missing_pk():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "events", "issue": "missing_primary_key",
                         "column": None, "row_estimate": 10.0}]}
    findings = rules.evaluate_diagnostic("schema_checks", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == "maintenance.schema_hygiene_issue:public:events:missing_primary_key"

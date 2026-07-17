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


def test_cache_hit_ratio_red_below_80_percent():
    diag = {"status": "ok", "quality": _quality(), "metrics": [{"cache_hit_ratio": 0.75}]}
    findings = rules.evaluate_diagnostic("database_stats", diag, _rules_by_block())
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_id"] == "db_health.cache_hit_ratio"
    assert f["assessment"] == "red"
    assert f["confidence"] == "measured"


def test_cache_hit_ratio_healthy_fires_nothing():
    diag = {"status": "ok", "quality": _quality(), "metrics": [{"cache_hit_ratio": 0.99}]}
    assert rules.evaluate_diagnostic("database_stats", diag, _rules_by_block()) == []


def test_wraparound_xid_age_yellow_at_80_percent_of_freeze_max_age():
    row = {"level": "table", "schema": "public", "table": "big", "xid_age": 160_000_000,
           "mxid_age": 0, "autovacuum_freeze_max_age": 200_000_000,
           "autovacuum_multixact_freeze_max_age": 400_000_000,
           "vacuum_failsafe_age": None, "vacuum_multixact_failsafe_age": None}
    diag = {"status": "ok", "quality": _quality(), "metrics": [row]}
    findings = rules.evaluate_diagnostic("wraparound", diag, _rules_by_block())
    xid_findings = [f for f in findings if f["finding_id"].startswith("db_health.wraparound_xid_age")]
    assert len(xid_findings) == 1
    assert xid_findings[0]["assessment"] == "yellow"
    assert xid_findings[0]["finding_id"] == "db_health.wraparound_xid_age:table:public:big"


def test_wraparound_mxid_age_red_at_full_freeze_max_age():
    row = {"level": "database", "datname": "prod", "xid_age": 0, "mxid_age": 500_000_000,
           "autovacuum_freeze_max_age": 200_000_000,
           "autovacuum_multixact_freeze_max_age": 400_000_000,
           "vacuum_failsafe_age": None, "vacuum_multixact_failsafe_age": None}
    diag = {"status": "ok", "quality": _quality(), "metrics": [row]}
    findings = rules.evaluate_diagnostic("wraparound", diag, _rules_by_block())
    mxid_findings = [f for f in findings if f["finding_id"].startswith("db_health.wraparound_mxid_age")]
    assert len(mxid_findings) == 1
    assert mxid_findings[0]["assessment"] == "red"
    assert mxid_findings[0]["severity"] == "critical"

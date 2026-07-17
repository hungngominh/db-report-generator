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


def _conn_row(**overrides):
    row = {"db_connections": 5, "cluster_connections": 10, "cluster_max_connections": 100,
           "idle_in_transaction": 0, "longest_txn_seconds": None, "configured_pool_size": None}
    row.update(overrides)
    return row


def test_cluster_pressure_red_above_90_percent():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [_conn_row(cluster_connections=95, cluster_max_connections=100)]}
    findings = rules.evaluate_diagnostic("connection_depth", diag, _rules_by_block())
    ids = {f["finding_id"] for f in findings}
    assert "connections.cluster_pressure" in ids


def test_pool_pressure_skips_when_pool_size_not_configured():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [_conn_row(db_connections=95, configured_pool_size=None)]}
    findings = rules.evaluate_diagnostic("connection_depth", diag, _rules_by_block())
    ids = {f["finding_id"] for f in findings}
    assert "connections.pool_pressure" not in ids


def test_pool_pressure_fires_when_pool_size_configured():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [_conn_row(db_connections=95, configured_pool_size=100)]}
    findings = rules.evaluate_diagnostic("connection_depth", diag, _rules_by_block())
    ids = {f["finding_id"] for f in findings}
    assert "connections.pool_pressure" in ids


def test_idle_in_transaction_skips_when_no_long_transaction():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_conn_row(longest_txn_seconds=None)]}
    findings = rules.evaluate_diagnostic("connection_depth", diag, _rules_by_block())
    ids = {f["finding_id"] for f in findings}
    assert "connections.idle_in_transaction" not in ids


def test_idle_in_transaction_red_above_600_seconds():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_conn_row(longest_txn_seconds=650.0)]}
    findings = rules.evaluate_diagnostic("connection_depth", diag, _rules_by_block())
    matches = [f for f in findings if f["finding_id"] == "connections.idle_in_transaction"]
    assert len(matches) == 1
    assert matches[0]["assessment"] == "red"


def test_blocking_red_above_30_seconds_with_pid_identity():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"blocked_pid": 100, "blocked_user": "u", "blocking_pid": 200,
                         "blocking_user": "u2", "blocked_query": "select 1", "blocking_query": "select 2",
                         "blocked_duration_seconds": 45.0}]}
    findings = rules.evaluate_diagnostic("blocking", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "red"
    assert findings[0]["severity"] == "critical"
    assert findings[0]["finding_id"] == "connections.blocking:100:200"


def test_blocking_empty_metrics_is_healthy():
    diag = {"status": "ok", "quality": _quality(), "metrics": []}
    assert rules.evaluate_diagnostic("blocking", diag, _rules_by_block()) == []

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


def test_rls_policy_issue_fires_yellow():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "notes", "policy": "notes_owner_only",
                         "clause": "qual", "issue": "unwrapped_reeval_call",
                         "function": "auth.uid", "column": None}]}
    findings = rules.evaluate_diagnostic("rls_policies", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == \
        "security_rls.rls_policy_issue:public:notes:notes_owner_only:qual:unwrapped_reeval_call:auth.uid"

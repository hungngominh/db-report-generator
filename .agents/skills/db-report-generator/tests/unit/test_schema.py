import pytest

from scripts.lib.schema import load_schema, validate_report, validation_errors

MINIMAL = {
    "schema_version": "4.0",
    "tool_version": "4.0.0",
    "run": {"run_id": "r1", "started_at": "2026-07-16T00:00:00Z", "completed_at": None},
    "redaction_mode": "none",
    "targets": [],
}


def test_schema_loads():
    schema = load_schema()
    assert schema["$schema"].endswith("2020-12/schema")


def test_minimal_valid():
    validate_report(MINIMAL)  # не raise
    assert validation_errors(MINIMAL) == []


def test_bad_schema_version_rejected():
    bad = {**MINIMAL, "schema_version": "3.0"}
    assert validation_errors(bad)


def test_bad_assessment_enum_rejected():
    bad = {
        **MINIMAL,
        "targets": [
            {
                "target_id": "t1",
                "database": "db",
                "collection_status": "ok",
                "capabilities": {},
                "diagnostics": {
                    "overview": {
                        "collector_version": "1.0",
                        "scope": "database",
                        "status": "ok",
                        "quality": {
                            "sampling_valid": True,
                            "reset_detected": False,
                            "insufficient_activity": False,
                            "truncated": False,
                        },
                        "metrics": [],
                        "findings": [
                            {
                                "finding_id": "x",
                                "severity": "warning",
                                "assessment": "blue",  # invalid
                                "confidence": "measured",
                                "evidence_ids": [],
                                "remediation_ids": [],
                            }
                        ],
                    }
                },
            }
        ],
    }
    assert validation_errors(bad)


_BASE_TARGET = {
    "target_id": "t1", "database": "db", "collection_status": "ok",
    "capabilities": {}, "diagnostics": {},
}


def test_target_sampling_null_is_valid():
    ok = {**MINIMAL, "targets": [{**_BASE_TARGET, "sampling": None}]}
    assert validation_errors(ok) == []


def test_target_sampling_object_is_valid():
    ok = {**MINIMAL, "targets": [{**_BASE_TARGET, "sampling": {
        "window_seconds": 30, "sample1_at": "2026-07-17T00:00:00Z",
        "sample2_at": "2026-07-17T00:00:30Z", "reset_detected": False,
    }}]}
    assert validation_errors(ok) == []


def test_target_sampling_missing_is_still_valid():
    # sampling is optional (not in target.required) — targets that skip
    # sampling entirely (no pg_stat_statements) must stay schema-valid.
    ok = {**MINIMAL, "targets": [_BASE_TARGET]}
    assert validation_errors(ok) == []


def test_target_sampling_extra_field_rejected():
    bad = {**MINIMAL, "targets": [{**_BASE_TARGET, "sampling": {
        "window_seconds": 30, "sample1_at": "t1", "sample2_at": "t2",
        "reset_detected": False, "extra": 1,
    }}]}
    assert validation_errors(bad)


def test_target_sampling_missing_required_subfield_rejected():
    bad = {**MINIMAL, "targets": [{**_BASE_TARGET, "sampling": {
        "window_seconds": 30, "sample1_at": "t1", "reset_detected": False,
    }}]}
    assert validation_errors(bad)

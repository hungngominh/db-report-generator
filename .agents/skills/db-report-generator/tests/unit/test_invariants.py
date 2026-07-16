import copy

from scripts.lib.invariants import (
    check_confidence_invalidation,
    enforce_confidence_invalidation,
)


def _violating():
    return {
        "targets": [
            {
                "target_id": "t",
                "diagnostics": {
                    "d": {
                        "quality": {"sampling_valid": False, "reset_detected": True,
                                    "insufficient_activity": False, "truncated": False},
                        "findings": [
                            {"finding_id": "f", "severity": "warning",
                             "assessment": "red", "confidence": "measured",
                             "evidence_ids": [], "remediation_ids": []}
                        ],
                    }
                },
            }
        ]
    }


def test_detects_violation():
    assert check_confidence_invalidation(_violating())


def test_enforce_normalizes():
    fixed = enforce_confidence_invalidation(_violating())
    f = fixed["targets"][0]["diagnostics"]["d"]["findings"][0]
    assert f["assessment"] == "unknown"
    assert f["confidence"] == "heuristic"
    assert check_confidence_invalidation(fixed) == []


def test_sample_report_clean_after_enforce(sample_report):
    fixed = enforce_confidence_invalidation(sample_report)
    assert check_confidence_invalidation(fixed) == []


def test_enforce_does_not_touch_valid_sampling():
    data = copy.deepcopy(_violating())
    data["targets"][0]["diagnostics"]["d"]["quality"]["sampling_valid"] = True
    fixed = enforce_confidence_invalidation(data)
    f = fixed["targets"][0]["diagnostics"]["d"]["findings"][0]
    assert f["assessment"] == "red" and f["confidence"] == "measured"

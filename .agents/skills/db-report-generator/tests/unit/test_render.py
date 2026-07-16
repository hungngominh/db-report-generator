import json
import os
from pathlib import Path

from scripts.render import build_summary, render_db_status, render_findings

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _check(name: str, actual: str):
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
    assert path.read_text(encoding="utf-8") == actual, f"golden drift: {name}"


def test_db_status_golden(sample_report):
    _check("DB_STATUS_REPORT.md", render_db_status(sample_report))


def test_findings_golden(sample_report):
    _check("FINDINGS.md", render_findings(sample_report))


def test_summary_golden(sample_report):
    actual = json.dumps(build_summary(sample_report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _check("report_summary.json", actual)


def test_render_is_deterministic(sample_report):
    assert render_db_status(sample_report) == render_db_status(sample_report)


def test_invalid_sampling_shows_unknown(sample_report):
    # wraparound có sampling_valid=false → phải là ⚪ unknown, không xanh
    out = render_db_status(sample_report)
    assert "⚪" in out
    assert "xid.wraparound-age" in out


def test_render_downgrades_violating_finding_b3():
    # Guards render-layer wiring of B3: a finding under sampling_valid=false with
    # a raw non-unknown assessment MUST be downgraded to ⚪ unknown by the render
    # enforce step. Fails if enforce_confidence_invalidation() is removed from
    # render_db_status / render_findings.
    data = {
        "schema_version": "4.0",
        "tool_version": "4.0.0",
        "run": {"run_id": "r", "started_at": "x", "completed_at": None},
        "redaction_mode": "none",
        "targets": [
            {
                "target_id": "t", "database": "db", "collection_status": "ok", "error": None,
                "capabilities": {},
                "diagnostics": {
                    "d": {
                        "collector_version": "1.0", "scope": "database", "status": "ok",
                        "reason": None,
                        "quality": {"sampling_valid": False, "reset_detected": True,
                                    "insufficient_activity": False, "truncated": False},
                        "metrics": [],
                        "findings": [
                            {"finding_id": "x.raw", "severity": "warning",
                             "assessment": "red", "confidence": "measured",
                             "evidence_ids": [], "remediation_ids": []}
                        ],
                    }
                },
            }
        ],
    }
    status = render_db_status(data)
    assert "🔴 red" not in status
    assert "⚪ unknown" in status
    assert render_findings(data).count("🔴 red") == 0

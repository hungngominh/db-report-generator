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

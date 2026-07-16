"""Deterministic renderer: report_data.json -> Markdown + summary (no timestamps)."""
import json
from pathlib import Path

from scripts.lib.invariants import enforce_confidence_invalidation
from scripts.lib.sortkeys import iter_findings, sort_targets, sorted_block_names

ASSESSMENT_ICONS = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
    "unknown": "⚪",
    "not_applicable": "➖",
}


def _icon(assessment: str) -> str:
    return ASSESSMENT_ICONS.get(assessment, "⚪")


def render_db_status(data: dict) -> str:
    data = enforce_confidence_invalidation(data)
    lines = ["# Báo cáo tình trạng Database", ""]
    for target in sort_targets(data["targets"]):
        lines.append(f"## Target: {target['database']} (`{target['target_id']}`) — thu thập: {target['collection_status']}")
        lines.append("")
        if target["collection_status"] == "error":
            lines.append(f"> 🔴 Lỗi thu thập: {target.get('error') or 'không rõ'}")
            lines.append("")
            continue
        for block in sorted_block_names(target["diagnostics"]):
            diag = target["diagnostics"][block]
            suffix = f" · {diag['reason']}" if diag.get("reason") else ""
            lines.append(f"### {block} — {diag['status']}{suffix}")
            if not diag["quality"]["sampling_valid"]:
                lines.append("")
                lines.append("> ⚪ Sampling không hợp lệ — các đánh giá bị hạ về `unknown`.")
            if diag["findings"]:
                lines.append("")
                lines.append("| Finding | Mức | Đánh giá | Tin cậy |")
                lines.append("|---|---|---|---|")
                for f in diag["findings"]:
                    lines.append(f"| `{f['finding_id']}` | {f['severity']} | {_icon(f['assessment'])} {f['assessment']} | {f['confidence']} |")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_findings(data: dict) -> str:
    data = enforce_confidence_invalidation(data)
    lines = ["# Findings (tổng hợp)", "",
             "| Target | Khối | Finding | Mức | Đánh giá | Tin cậy |",
             "|---|---|---|---|---|---|"]
    for f in iter_findings(data):
        lines.append(f"| `{f['target_id']}` | {f['block']} | `{f['finding_id']}` | {f['severity']} | {_icon(f['assessment'])} {f['assessment']} | {f['confidence']} |")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_summary(data: dict) -> dict:
    data = enforce_confidence_invalidation(data)
    by_assessment: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    targets: dict[str, dict] = {}
    for target in data["targets"]:
        count = sum(len(d["findings"]) for d in target["diagnostics"].values())
        targets[target["target_id"]] = {"collection_status": target["collection_status"], "findings": count}
    for f in iter_findings(data):
        by_assessment[f["assessment"]] = by_assessment.get(f["assessment"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    return {
        "total_findings": sum(by_severity.values()),
        "by_assessment": by_assessment,
        "by_severity": by_severity,
        "targets": targets,
    }


def render_all(data: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "DB_STATUS_REPORT.md").write_text(render_db_status(data), encoding="utf-8", newline="\n")
    (out_dir / "FINDINGS.md").write_text(render_findings(data), encoding="utf-8", newline="\n")
    (out_dir / "report_summary.json").write_text(
        json.dumps(build_summary(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )

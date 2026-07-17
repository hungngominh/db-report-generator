"""P3 — rule engine: diagnostics(metrics) -> findings, with spec §0.B3/A2
quality gating.

Rules are data (references/rules/<axis>.json), not code. evaluate_target()
walks a target's diagnostics once, dispatching each diagnostic's registered
rules through one of the generic evaluators registered in _EVALUATORS.

Axis is a code-level grouping key only — the frozen finding schema
(additionalProperties: false) has no `axis` field, so which references/rules/
file a rule lives in is the only record of its axis membership.
"""
import functools
import json
from pathlib import Path

_RULES_DIR = Path(__file__).resolve().parents[1] / "references" / "rules"

AXES = ("db-health", "query-performance", "maintenance", "connections", "security-rls")


@functools.lru_cache(maxsize=1)
def load_catalog() -> dict:
    catalog = {}
    for axis in AXES:
        path = _RULES_DIR / f"{axis}.json"
        with open(path, encoding="utf-8") as f:
            catalog[axis] = json.load(f)
    return catalog


def _row_identity(row: dict, fields: list) -> str:
    parts = [str(row[f]) for f in fields if row.get(f) is not None]
    return ":".join(parts)


def _quality_gated(quality: dict) -> bool:
    return (not quality.get("sampling_valid", True)) or bool(quality.get("insufficient_activity", False))


def _compare(value, thresholds: dict, direction: str) -> str:
    if direction == "higher_is_worse":
        if value >= thresholds["red"]:
            return "red"
        if value >= thresholds["yellow"]:
            return "yellow"
        return "green"
    if value <= thresholds["red"]:
        return "red"
    if value <= thresholds["yellow"]:
        return "yellow"
    return "green"


def _make_finding(rule, *, assessment, confidence, row_id, evidence, gated) -> dict:
    finding_id = rule["finding_id"] if not row_id else f'{rule["finding_id"]}:{row_id}'
    return {
        "finding_id": finding_id,
        "severity": rule["severity"],
        "assessment": "unknown" if gated else assessment,
        "confidence": "heuristic" if gated else confidence,
        "title": rule["title"],
        "evidence_ids": evidence,
        "remediation_ids": [],
    }


def _eval_threshold(rule, metrics, gated) -> list:
    findings = []
    for row in metrics:
        value = row.get(rule["metric_key"])
        if value is None:
            continue
        assessment = _compare(value, rule["thresholds"], rule["direction"])
        if assessment == "green":
            continue
        row_id = _row_identity(row, rule.get("row_identity_fields", []))
        evidence = [f'{rule["metric_key"]}={value}']
        findings.append(_make_finding(
            rule, assessment=assessment, confidence=rule["confidence"],
            row_id=row_id, evidence=evidence, gated=gated))
    return findings


def _eval_ratio_threshold(rule, metrics, gated) -> list:
    findings = []
    for row in metrics:
        numerator = row.get(rule["numerator_key"])
        denominator = row.get(rule["denominator_key"])
        if numerator is None or not denominator:
            continue
        value = numerator / denominator
        assessment = _compare(value, rule["thresholds"], rule["direction"])
        if assessment == "green":
            continue
        row_id = _row_identity(row, rule.get("row_identity_fields", []))
        evidence = [f'{rule["numerator_key"]}={numerator}', f'{rule["denominator_key"]}={denominator}']
        findings.append(_make_finding(
            rule, assessment=assessment, confidence=rule["confidence"],
            row_id=row_id, evidence=evidence, gated=gated))
    return findings


_EVALUATORS = {
    "threshold": _eval_threshold,
    "ratio_threshold": _eval_ratio_threshold,
}


def evaluate_diagnostic(block: str, diagnostic: dict, rules_by_block: dict) -> list:
    applicable = rules_by_block.get(block)
    if not applicable or diagnostic.get("status") not in ("ok", "partial"):
        return []
    gated = _quality_gated(diagnostic.get("quality", {}))
    findings = []
    for rule in applicable:
        evaluator = _EVALUATORS[rule["kind"]]
        findings.extend(evaluator(rule, diagnostic.get("metrics", []), gated))
    return findings


def evaluate_target(target: dict) -> None:
    catalog = load_catalog()
    rules_by_block = {}
    for axis_rules in catalog.values():
        for rule in axis_rules:
            rules_by_block.setdefault(rule["block"], []).append(rule)
    for block, diag in target.get("diagnostics", {}).items():
        diag["findings"] = evaluate_diagnostic(block, diag, rules_by_block)

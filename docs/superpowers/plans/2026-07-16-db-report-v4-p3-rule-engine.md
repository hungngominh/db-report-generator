# P3 — Rule Engine + Unknown/Confidence Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the P0–P2 collectors' metrics-only output into real findings by adding a small, fully data-driven rule engine (`scripts/rules.py` + `references/rules/<axis>.json`), wire it into `analyzer.py`, and remove the legacy combined 0–100 score from `SKILL.md`/`references/template-combined-report.md` in favor of the spec's per-axis ranking model.

**Architecture:** Every P0–P2 collector already returns `findings: []` (see `scripts/collectors/base.py::diagnostic`) — the comment there has said "rule engine (metrics -> findings) is Phase 3" since P0b. The finding schema itself (`references/report-data.schema.json#/$defs/finding`) and the B3 confidence-invalidation invariant (`scripts/lib/invariants.py`) were both built in Phase −1 and are already unit-tested; `render.py` already calls `enforce_confidence_invalidation()` unconditionally. **None of those three files need to change.** P3's actual scope is narrow: a new `scripts/rules.py` module reads a JSON rule catalog (5 files, one per spec §8 axis), evaluates each diagnostic's `metrics` list against the rules registered for that diagnostic's block name, and writes the result into `diagnostic["findings"]`. Three generic evaluator kinds (`threshold`, `ratio_threshold`, `presence`) cover all 14 rules — axis content is pure data, never per-rule Python code. `analyzer.py` calls `rules.evaluate_target(target)` once per target, right after `collectors.run_collectors(...)`, and — as a defensive regression guard — asserts `invariants.check_confidence_invalidation(report)` is empty before returning, so a future rule-engine bug that violates B3 fails loudly in `analyze()` rather than silently failing schema validation (the schema has no way to express the B3 relationship, since it is a cross-field invariant, not a structural constraint).

**Tech Stack:** Python 3, pure in-memory rule evaluation (no new DB queries — the engine only reads `target["diagnostics"][block]["metrics"]`, already collected), pytest (all rule-engine tests are Docker-independent — they operate on plain dicts, not live Postgres).

## Global Constraints

- **§0.B3 (confidence invalidation, exact spec text):** *"Bất kỳ finding phái sinh từ diagnostic có `quality.sampling_valid=false` → bắt buộc `confidence ≤ heuristic` và `assessment = unknown`. Renderer/agent không được nâng cấp. Ràng buộc này validate trong schema/CI."* Any finding derived from a diagnostic whose `quality.sampling_valid` is `false` MUST have `confidence` forced to `heuristic` and `assessment` forced to `unknown`; nothing downstream may upgrade it. `scripts/rules.py` enforces this itself, at creation time, for every finding it emits — it does not rely solely on `render.py`'s `enforce_confidence_invalidation()` safety net.
- **A2 (insufficient activity):** when a diagnostic's underlying sample is too thin to judge (e.g. `query_stats`'s `quality.insufficient_activity=true`, set when `total_window_calls < MINIMUM_ACTIVITY_CALLS`), the same downgrade applies. This plan treats B3 and A2 as one unified "quality gate" — `rules._quality_gated(quality)` returns true if *either* flag says the data can't be trusted, and the engine applies the identical unknown/heuristic downgrade for both.
- **Gating never manufactures findings, only downgrades existing ones:** a quality-gated diagnostic with an otherwise-healthy (green) value produces **no finding at all** — exactly as an ungated healthy value would. Gating changes the `assessment`/`confidence` of a finding that *would already fire* on the raw value; it never turns a green row into a new "couldn't judge" finding. (An earlier draft of this plan considered emitting an unknown finding for every row of a gated diagnostic; that was rejected because it would flood the report with noise for `insufficient_activity` diagnostics that have many healthy rows — inconsistent with this project's established "no green noise" rendering philosophy, e.g. `render.py` never renders a row for a healthy assessment.)
- **§8 (per-axis model, exact spec constraint):** remove the combined 0–100 score entirely (double-counting + false precision). Replace with a per-axis ranking: `db-health`, `query-performance`, `maintenance`, `connections`, `security/RLS` — each axis shows 🟢/🟡/🔴 + issue list + a confidence level (`measured`/`estimated`/`heuristic`). No more "green" labels derived from cumulative counters without a delta window or an explicit "estimated" label. **Acceptance: no `/100` numbers anywhere in template/output; every verdict carries a confidence level.** This plan's axis order (`AXES` tuple) matches this spec listing verbatim: `db-health, query-performance, maintenance, connections, security-rls`.
- **No `axis` field on the finding schema.** `references/report-data.schema.json#/$defs/finding` is frozen (`additionalProperties: false`, Phase −1 lock point) and has no `axis` property. Axis membership is a **code-level lookup only** — which `references/rules/<axis>.json` file a rule lives in, not a field on the emitted finding. Do not add an `axis` field to any finding dict, and do not propose a schema change in this phase.
- **`security-rls` has no backing collector in P3.** RLS detection is P4.3's job (a future phase). `references/rules/security-rls.json` is a permanent, deliberate empty-list placeholder (`[]`) for this phase — Task 1 creates it and Task 8 asserts (by name, not just "some test somewhere") that its emptiness is intentional, not a forgotten TODO.
- **Metrics-only collectors from P0–P2 do not change.** No collector's Python code is touched by this plan. The only production code touched outside `scripts/rules.py` and its JSON catalog is `scripts/analyzer.py` (Task 7) and two documentation/template files (Task 9).
- **Read-only, no new DB queries.** The rule engine operates entirely on already-collected `target["diagnostics"][block]["metrics"]` — it opens no cursor, calls no SQL.
- **No git push without explicit user permission.** A real IP address remains in git history; local commits/merges only, exactly as done for P0a, P0b, P1, and P2.
- **Never start work directly on `master`.** This phase's branch is `feature/db-report-v4-p3`, branched from current `master` (P2's merge commit `e718d6f`).

### Architecture decision: why axis membership is a code-level lookup, not a schema field

The finding schema was frozen in Phase −1 with `additionalProperties: false` specifically so that every later phase builds *within* the existing contract rather than re-opening it. Adding an `axis` field would mean touching the one file every phase has explicitly avoided touching. Since `references/rules/<axis>.json` is already split one-file-per-axis, "which axis does this finding belong to" is fully recoverable from which catalog file defined the rule that produced it — a renderer (P3 doesn't build one; that's a later phase) can reconstruct the axis→findings grouping by re-walking `rules.load_catalog()` and matching `finding_id` prefixes (every `finding_id` in this plan is namespaced `axis_shortname.rule_name`, e.g. `db_health.cache_hit_ratio`, `maintenance.fk_missing_index`, `connections.blocking`, `query_perf.slow_query_mean_exec_time`) or by block name. This plan does not build that grouping helper — it's out of scope until a renderer needs it — but the naming convention is established now so it's free later.

### Architecture decision: `security-rls.json` is an intentional empty placeholder

Spec §8 lists `security/RLS` as one of the five axes a rendered report must show, but no P0–P2 collector inspects Row Level Security policies (that's P4.3, per the roadmap). Rather than skip the axis silently (which would make `AXES` inconsistent with the spec's 5-axis listing, and would look like an oversight to a future reader), `references/rules/security-rls.json` exists now as `[]`, and `load_catalog()["security-rls"] == []` is asserted by name in Task 8's coverage test with a comment explaining *why* it's empty. When P4.3 lands RLS detection, that task only needs to add rule entries to this already-existing file — no engine change.

### Architecture decision: gating is downgrade-only, never finding-manufacturing

Every one of the three evaluators (`_eval_threshold`, `_eval_ratio_threshold`, `_eval_presence`) computes what the finding *would* look like under normal (non-gated) rules first, and only then — if `gated` is true — overwrites `assessment`/`confidence` on that already-decided finding via `_make_finding`. A `_eval_threshold`/`_eval_ratio_threshold` row whose computed assessment is `"green"` is skipped (`continue`) before gating is ever consulted, regardless of `gated`'s value. This keeps the "no green noise" behavior identical whether or not the diagnostic is quality-gated, and keeps the gate's effect exactly scoped to what §0.B3/A2 actually require: never let an already-flagged finding claim more certainty than the data supports.

## Interfaces (shared across tasks)

- `scripts.rules.load_catalog() -> dict[str, list[dict]]` — `@functools.lru_cache(maxsize=1)`, keyed by axis name (`rules.AXES`), reads `references/rules/<axis>.json`. Task 1 creates this plus all 5 (initially near-empty) catalog files.
- `scripts.rules.AXES: tuple[str, ...]` = `("db-health", "query-performance", "maintenance", "connections", "security-rls")` — spec §8 order, verbatim.
- `scripts.rules._quality_gated(quality: dict) -> bool` — Task 1. `True` iff `quality.get("sampling_valid", True) is False or quality.get("insufficient_activity", False) is True`.
- `scripts.rules._compare(value: float, thresholds: dict, direction: str) -> str` — Task 1. Returns `"red"`/`"yellow"`/`"green"`. `direction` is `"higher_is_worse"` or `"lower_is_worse"`.
- `scripts.rules._make_finding(rule: dict, *, assessment: str, confidence: str, row_id: str, evidence: list[str], gated: bool) -> dict` — Task 1. Builds one schema-valid finding dict. `finding_id` is `rule["finding_id"]` alone when `row_id` is empty, else `f'{rule["finding_id"]}:{row_id}'`. `remediation_ids` is always `[]` in this phase (P6 populates it later). When `gated` is `True`, `assessment` is forced to `"unknown"` and `confidence` to `"heuristic"` regardless of the passed-in values — `evidence_ids` is never touched by gating (matches `invariants.enforce_confidence_invalidation()`'s own behavior of only touching `assessment`/`confidence`).
- `scripts.rules._eval_threshold(rule: dict, metrics: list[dict], gated: bool) -> list[dict]`, `scripts.rules._eval_ratio_threshold(rule, metrics, gated) -> list[dict]` — Task 1. `scripts.rules._eval_presence(rule, metrics, gated) -> list[dict]` — Task 2. All three are registered in `scripts.rules._EVALUATORS: dict[str, callable]` keyed by each rule's `"kind"` field.
- `scripts.rules.evaluate_diagnostic(block: str, diagnostic: dict, rules_by_block: dict) -> list[dict]` — Task 1. Returns `[]` if no rules are registered for `block`, or if `diagnostic["status"] not in ("ok", "partial")` (a `skipped`/`error` diagnostic has no metrics worth judging). Otherwise computes `gated` once from `diagnostic["quality"]` and dispatches every applicable rule through `_EVALUATORS[rule["kind"]]`.
- `scripts.rules.evaluate_target(target: dict) -> None` — Task 1. Mutates `target["diagnostics"][block]["findings"]` in place for every block. Builds the `block -> [rules]` index from `load_catalog()` internally (flattening all 5 axes) so callers never need to know about axes.
- **Rule catalog entry shape** (every `.json` file in `references/rules/` is a JSON array of these dicts):
  - Common to all kinds: `finding_id` (str), `title` (str, Vietnamese — matches `render.py`'s existing Vietnamese-only output convention), `severity` (`info|notice|warning|critical`), `kind` (`threshold|ratio_threshold|presence`), `block` (str — must be a real key in `scripts.collectors.COLLECTORS`), `confidence` (`measured|estimated|heuristic` — the *non-gated* confidence; ignored when gated), `row_identity_fields` (list[str] — used to build a stable per-row `finding_id` suffix when a block's `metrics` has more than one row).
  - `threshold` additionally: `metric_key` (str), `direction` (`higher_is_worse|lower_is_worse`), `thresholds` (`{"red": number, "yellow": number}`).
  - `ratio_threshold` additionally: `numerator_key` (str), `denominator_key` (str), `direction`, `thresholds` — same shape as `threshold`, but the compared value is `row[numerator_key] / row[denominator_key]`, and the row is skipped if the denominator is `None` or `0`, or the numerator is `None`.
  - `presence` additionally: `assessment` (`green|yellow|red` — fixed per rule; a presence rule fires once per row, always at this assessment when not gated).
- Task 7 (`analyzer.py`) depends on Tasks 1–6 being complete (`rules.evaluate_target` must exist and the catalog must be populated) and on the existing `scripts.lib.invariants.check_confidence_invalidation(data: dict) -> list[str]` (already implemented, Phase −1, unchanged).

## File Structure

```
.agents/skills/db-report-generator/
  scripts/
    rules.py                               # CREATE (Tasks 1-2)
    analyzer.py                            # MODIFY (Task 7)
  references/
    rules/
      db-health.json                       # CREATE (Task 1 empty placeholder, Task 3 populates)
      query-performance.json               # CREATE (Task 1 empty placeholder, Task 5 populates)
      maintenance.json                     # CREATE (Task 1 empty placeholder, Task 4 populates)
      connections.json                     # CREATE (Task 1 empty placeholder, Task 6 populates)
      security-rls.json                    # CREATE (Task 1, stays `[]` — see Architecture decision)
    template-combined-report.md            # MODIFY (Task 9)
  SKILL.md                                 # MODIFY (Task 9)
  tests/unit/
    test_rules.py                          # CREATE (Tasks 1, 2, 8)
    test_rules_db_health.py                # CREATE (Task 3)
    test_rules_maintenance.py              # CREATE (Task 4)
    test_rules_query_performance.py        # CREATE (Task 5)
    test_rules_connections.py              # CREATE (Task 6)
    test_analyzer.py                       # MODIFY (Task 7)
    test_skill_docs.py                     # CREATE (Task 9)
```

No changes to `references/report-data.schema.json`, `scripts/lib/invariants.py`, `scripts/lib/sortkeys.py`, or `scripts/render.py` are required by this plan — all four were already built generically in Phase −1 and verified against this plan's design (see Architecture section above).

---

### Task 1: `scripts/rules.py` core — catalog loader, quality gate, threshold/ratio_threshold evaluators

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/rules.py`
- Create: `.agents/skills/db-report-generator/references/rules/db-health.json` (empty placeholder `[]`)
- Create: `.agents/skills/db-report-generator/references/rules/query-performance.json` (empty placeholder `[]`)
- Create: `.agents/skills/db-report-generator/references/rules/maintenance.json` (empty placeholder `[]`)
- Create: `.agents/skills/db-report-generator/references/rules/connections.json` (empty placeholder `[]`)
- Create: `.agents/skills/db-report-generator/references/rules/security-rls.json` (permanent `[]`)
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules.py`

**Interfaces:**
- Produces: `load_catalog()`, `AXES`, `_row_identity`, `_quality_gated`, `_compare`, `_make_finding`, `_eval_threshold`, `_eval_ratio_threshold`, `_EVALUATORS` (with only `"threshold"`/`"ratio_threshold"` registered — Task 2 adds `"presence"`), `evaluate_diagnostic`, `evaluate_target` — exact signatures in the Interfaces section above.
- Consumes: nothing from earlier tasks (this is the first task).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rules.py`:

```python
from scripts import rules


def _quality(sampling_valid=True, insufficient_activity=False):
    return {"sampling_valid": sampling_valid, "reset_detected": False,
            "insufficient_activity": insufficient_activity, "truncated": False}


def test_load_catalog_covers_all_five_axes():
    catalog = rules.load_catalog()
    assert set(catalog) == set(rules.AXES)
    assert rules.AXES == ("db-health", "query-performance", "maintenance",
                          "connections", "security-rls")


def test_quality_gated_true_when_sampling_invalid():
    assert rules._quality_gated(_quality(sampling_valid=False)) is True


def test_quality_gated_true_when_insufficient_activity():
    assert rules._quality_gated(_quality(insufficient_activity=True)) is True


def test_quality_gated_false_when_healthy():
    assert rules._quality_gated(_quality()) is False


def test_compare_higher_is_worse():
    thresholds = {"red": 20, "yellow": 5}
    assert rules._compare(25, thresholds, "higher_is_worse") == "red"
    assert rules._compare(10, thresholds, "higher_is_worse") == "yellow"
    assert rules._compare(1, thresholds, "higher_is_worse") == "green"


def test_compare_lower_is_worse():
    thresholds = {"red": 0.80, "yellow": 0.90}
    assert rules._compare(0.5, thresholds, "lower_is_worse") == "red"
    assert rules._compare(0.85, thresholds, "lower_is_worse") == "yellow"
    assert rules._compare(0.99, thresholds, "lower_is_worse") == "green"


_RULE = {
    "finding_id": "test.metric", "title": "Test metric cao", "severity": "warning",
    "kind": "threshold", "block": "some_block", "metric_key": "value",
    "direction": "higher_is_worse", "thresholds": {"red": 20, "yellow": 5},
    "row_identity_fields": ["schema", "table"], "confidence": "measured",
}


def test_eval_threshold_skips_green_rows():
    findings = rules._eval_threshold(_RULE, [{"schema": "public", "table": "t", "value": 1}], gated=False)
    assert findings == []


def test_eval_threshold_skips_rows_missing_the_metric():
    findings = rules._eval_threshold(_RULE, [{"schema": "public", "table": "t"}], gated=False)
    assert findings == []


def test_eval_threshold_fires_with_row_identity_suffix():
    findings = rules._eval_threshold(
        _RULE, [{"schema": "public", "table": "t", "value": 25}], gated=False)
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_id"] == "test.metric:public:t"
    assert f["severity"] == "warning"
    assert f["assessment"] == "red"
    assert f["confidence"] == "measured"
    assert f["evidence_ids"] == ["value=25"]
    assert f["remediation_ids"] == []


def test_eval_threshold_gated_forces_unknown_heuristic_but_keeps_evidence():
    findings = rules._eval_threshold(
        _RULE, [{"schema": "public", "table": "t", "value": 25}], gated=True)
    f = findings[0]
    assert f["assessment"] == "unknown"
    assert f["confidence"] == "heuristic"
    assert f["evidence_ids"] == ["value=25"]  # gating never touches evidence


_RATIO_RULE = {
    "finding_id": "test.ratio", "title": "Test ratio cao", "severity": "critical",
    "kind": "ratio_threshold", "block": "some_block",
    "numerator_key": "num", "denominator_key": "den",
    "direction": "higher_is_worse", "thresholds": {"red": 1.0, "yellow": 0.8},
    "row_identity_fields": [], "confidence": "measured",
}


def test_eval_ratio_threshold_computes_ratio_and_fires():
    findings = rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": 100}], gated=False)
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["evidence_ids"] == ["num=90", "den=100"]


def test_eval_ratio_threshold_skips_zero_or_none_denominator():
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": 0}], gated=False) == []
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": 90, "den": None}], gated=False) == []


def test_eval_ratio_threshold_skips_none_numerator():
    assert rules._eval_ratio_threshold(_RATIO_RULE, [{"num": None, "den": 100}], gated=False) == []


def test_evaluate_diagnostic_returns_empty_for_unregistered_block():
    diag = {"status": "ok", "quality": _quality(), "metrics": [{"value": 99}]}
    assert rules.evaluate_diagnostic("no_such_block", diag, {}) == []


def test_evaluate_diagnostic_returns_empty_for_skipped_status():
    diag = {"status": "skipped", "quality": _quality(), "metrics": []}
    rules_by_block = {"some_block": [_RULE]}
    assert rules.evaluate_diagnostic("some_block", diag, rules_by_block) == []


def test_evaluate_diagnostic_dispatches_by_kind():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "value": 25}]}
    rules_by_block = {"some_block": [_RULE]}
    findings = rules.evaluate_diagnostic("some_block", diag, rules_by_block)
    assert len(findings) == 1
    assert findings[0]["finding_id"] == "test.metric:public:t"


def test_evaluate_target_writes_findings_into_each_diagnostic(monkeypatch):
    monkeypatch.setattr(rules, "load_catalog", lambda: {"db-health": [_RULE]})
    target = {"diagnostics": {
        "some_block": {"status": "ok", "quality": _quality(),
                        "metrics": [{"schema": "public", "table": "t", "value": 25}]},
        "other_block": {"status": "ok", "quality": _quality(), "metrics": []},
    }}
    rules.evaluate_target(target)
    assert len(target["diagnostics"]["some_block"]["findings"]) == 1
    assert target["diagnostics"]["other_block"]["findings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.rules'` (or `ImportError`).

- [ ] **Step 3: Create the empty rule catalog placeholders**

`references/rules/db-health.json`, `references/rules/query-performance.json`, `references/rules/maintenance.json`, `references/rules/connections.json` — each file contains exactly:

```json
[]
```

`references/rules/security-rls.json` — same content, but this one is a **permanent** placeholder (no later task in this plan populates it; see the Architecture decision above):

```json
[]
```

- [ ] **Step 4: Implement `scripts/rules.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules.py -v`
Expected: PASS (17 tests)

- [ ] **Step 6: Commit**

```bash
git add scripts/rules.py references/rules/db-health.json references/rules/query-performance.json \
        references/rules/maintenance.json references/rules/connections.json \
        references/rules/security-rls.json tests/unit/test_rules.py
git commit -m "feat(p3): rule engine core — catalog loader, quality gate, threshold/ratio_threshold evaluators (P3 foundation)"
```

---

### Task 2: `presence` evaluator

**Files:**
- Modify: `.agents/skills/db-report-generator/scripts/rules.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules.py`

**Interfaces:**
- Consumes: `_make_finding`, `_row_identity` from Task 1 (unchanged signatures).
- Produces: `_eval_presence(rule: dict, metrics: list[dict], gated: bool) -> list[dict]`, registered in `_EVALUATORS["presence"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_rules.py`:

```python
_PRESENCE_RULE = {
    "finding_id": "test.presence", "title": "Test presence issue", "severity": "notice",
    "kind": "presence", "block": "some_block", "assessment": "yellow",
    "row_identity_fields": ["schema", "table"], "confidence": "measured",
}


def test_eval_presence_fires_once_per_row():
    metrics = [{"schema": "public", "table": "a"}, {"schema": "public", "table": "b"}]
    findings = rules._eval_presence(_PRESENCE_RULE, metrics, gated=False)
    assert len(findings) == 2
    assert {f["finding_id"] for f in findings} == {"test.presence:public:a", "test.presence:public:b"}
    assert all(f["assessment"] == "yellow" for f in findings)
    assert all(f["evidence_ids"] == [] for f in findings)


def test_eval_presence_empty_metrics_fires_nothing():
    assert rules._eval_presence(_PRESENCE_RULE, [], gated=False) == []


def test_eval_presence_gated_forces_unknown_heuristic():
    findings = rules._eval_presence(_PRESENCE_RULE, [{"schema": "public", "table": "a"}], gated=True)
    assert findings[0]["assessment"] == "unknown"
    assert findings[0]["confidence"] == "heuristic"


def test_presence_kind_dispatches_through_evaluate_diagnostic():
    diag = {"status": "ok", "quality": _quality(), "metrics": [{"schema": "public", "table": "a"}]}
    findings = rules.evaluate_diagnostic("some_block", diag, {"some_block": [_PRESENCE_RULE]})
    assert len(findings) == 1
    assert findings[0]["finding_id"] == "test.presence:public:a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rules.py -k presence -v`
Expected: FAIL with `KeyError: 'presence'` (from `_EVALUATORS[rule["kind"]]`)

- [ ] **Step 3: Implement `_eval_presence` and register it**

In `scripts/rules.py`, add the function right after `_eval_ratio_threshold` and add it to `_EVALUATORS`:

```python
def _eval_presence(rule, metrics, gated) -> list:
    findings = []
    for row in metrics:
        row_id = _row_identity(row, rule.get("row_identity_fields", []))
        findings.append(_make_finding(
            rule, assessment=rule["assessment"], confidence=rule["confidence"],
            row_id=row_id, evidence=[], gated=gated))
    return findings


_EVALUATORS = {
    "threshold": _eval_threshold,
    "ratio_threshold": _eval_ratio_threshold,
    "presence": _eval_presence,
}
```

(Replace the existing two-entry `_EVALUATORS` dict from Task 1 with this three-entry version — do not leave two definitions in the file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/rules.py tests/unit/test_rules.py
git commit -m "feat(p3): add presence evaluator to rule engine (P3 foundation)"
```

---

### Task 3: `db-health` axis rules (cache hit ratio, XID/MultiXact wraparound)

**Files:**
- Modify: `.agents/skills/db-report-generator/references/rules/db-health.json`
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules_db_health.py`

**Interfaces:**
- Consumes: `rules.load_catalog()`, `rules.evaluate_diagnostic(block, diagnostic, rules_by_block)` from Task 1 — unchanged.
- Produces: 3 populated rules consumable by any later task's `evaluate_target` call. No new Python functions.

Field names verified against real collector source: `scripts/collectors/database_stats.py` (`cache_hit_ratio`, scope=`database`) and `scripts/collectors/wraparound.py` (`level`, `datname` for level=`database` rows, `schema`+`table` for level=`table` rows, `xid_age`, `mxid_age`, and threshold GUCs `autovacuum_freeze_max_age`/`autovacuum_multixact_freeze_max_age` spread onto every row).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rules_db_health.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rules_db_health.py -v`
Expected: FAIL — all assert on `len(findings) == 1`/similar but the catalog is empty (`[]`), so every assertion sees `0` findings.

- [ ] **Step 3: Populate `references/rules/db-health.json`**

```json
[
  {
    "finding_id": "db_health.cache_hit_ratio",
    "title": "Tỷ lệ cache hit thấp",
    "severity": "warning",
    "kind": "threshold",
    "block": "database_stats",
    "metric_key": "cache_hit_ratio",
    "direction": "lower_is_worse",
    "thresholds": {"red": 0.80, "yellow": 0.90},
    "row_identity_fields": [],
    "confidence": "measured"
  },
  {
    "finding_id": "db_health.wraparound_xid_age",
    "title": "XID age tiến gần ngưỡng autovacuum_freeze_max_age",
    "severity": "critical",
    "kind": "ratio_threshold",
    "block": "wraparound",
    "numerator_key": "xid_age",
    "denominator_key": "autovacuum_freeze_max_age",
    "direction": "higher_is_worse",
    "thresholds": {"red": 1.0, "yellow": 0.8},
    "row_identity_fields": ["level", "datname", "schema", "table"],
    "confidence": "measured"
  },
  {
    "finding_id": "db_health.wraparound_mxid_age",
    "title": "MultiXact age tiến gần ngưỡng autovacuum_multixact_freeze_max_age",
    "severity": "critical",
    "kind": "ratio_threshold",
    "block": "wraparound",
    "numerator_key": "mxid_age",
    "denominator_key": "autovacuum_multixact_freeze_max_age",
    "direction": "higher_is_worse",
    "thresholds": {"red": 1.0, "yellow": 0.8},
    "row_identity_fields": ["level", "datname", "schema", "table"],
    "confidence": "measured"
  }
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules_db_health.py -v`
Expected: PASS (4 tests). Also re-run `pytest tests/unit/test_rules.py -v` to confirm Tasks 1–2's tests are unaffected (they use `monkeypatch`/inline `rules_by_block` dicts, never `load_catalog()`'s real content directly except `test_load_catalog_covers_all_five_axes`, which only checks axis names).

- [ ] **Step 5: Commit**

```bash
git add references/rules/db-health.json tests/unit/test_rules_db_health.py
git commit -m "feat(p3): db-health axis rules — cache hit ratio, XID/MultiXact wraparound (P3.db-health)"
```

---

### Task 4: `maintenance` axis rules (dead tuples, stale stats, index bloat, duplicate index, FK missing index)

**Files:**
- Modify: `.agents/skills/db-report-generator/references/rules/maintenance.json`
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules_maintenance.py`

**Interfaces:**
- Consumes: `rules.evaluate_diagnostic`, `_eval_presence` (Task 2) — this is the first axis to exercise the `presence` kind.
- Produces: 5 populated rules.

Field names verified against: `scripts/collectors/dead_tuples.py` (`schema`, `table`, `dead_pct`, scope=`table`), `scripts/collectors/stale_stats.py` (`schema`, `table`, `modified_pct`, scope=`table`), `scripts/collectors/index_bloat.py` (`schema`, `table`, `dead_tuple_percent`, scope=`table`), `scripts/collectors/duplicate_index.py` (`kind` ∈ `{exact_duplicate, potentially_redundant}`, `schema`, `table`, `keep`/`redundant` present depending on `kind`, scope=`index`), `scripts/collectors/fk_missing_index.py` (`schema`, `table`, `constraint`, scope=`table`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rules_maintenance.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rules_maintenance.py -v`
Expected: FAIL — 0 findings for every case (catalog is `[]`).

- [ ] **Step 3: Populate `references/rules/maintenance.json`**

Note the `duplicate_index` row identity: `_row_identity` only includes fields present *and non-None* in the row, in the exact `row_identity_fields` order given — so `exact_duplicate` rows (which have `keep` but not `redundant`) produce `kind:schema:table:keep`, and `potentially_redundant` rows (which have `redundant` but not `keep`) produce `kind:schema:table:redundant`, matching the test above.

```json
[
  {
    "finding_id": "maintenance.dead_tuples_pct",
    "title": "Tỷ lệ dead tuple cao",
    "severity": "warning",
    "kind": "threshold",
    "block": "dead_tuples",
    "metric_key": "dead_pct",
    "direction": "higher_is_worse",
    "thresholds": {"red": 20, "yellow": 5},
    "row_identity_fields": ["schema", "table"],
    "confidence": "measured"
  },
  {
    "finding_id": "maintenance.stale_stats_pct",
    "title": "Thống kê bảng đã cũ (cần ANALYZE)",
    "severity": "notice",
    "kind": "threshold",
    "block": "stale_stats",
    "metric_key": "modified_pct",
    "direction": "higher_is_worse",
    "thresholds": {"red": 50, "yellow": 20},
    "row_identity_fields": ["schema", "table"],
    "confidence": "measured"
  },
  {
    "finding_id": "maintenance.index_bloat_pct",
    "title": "Index/table có dấu hiệu bloat",
    "severity": "notice",
    "kind": "threshold",
    "block": "index_bloat",
    "metric_key": "dead_tuple_percent",
    "direction": "higher_is_worse",
    "thresholds": {"red": 30, "yellow": 10},
    "row_identity_fields": ["schema", "table"],
    "confidence": "estimated"
  },
  {
    "finding_id": "maintenance.duplicate_index",
    "title": "Index trùng lặp hoặc dư thừa",
    "severity": "notice",
    "kind": "presence",
    "block": "duplicate_index",
    "assessment": "yellow",
    "row_identity_fields": ["kind", "schema", "table", "keep", "redundant"],
    "confidence": "measured"
  },
  {
    "finding_id": "maintenance.fk_missing_index",
    "title": "Khóa ngoại thiếu index hỗ trợ",
    "severity": "warning",
    "kind": "presence",
    "block": "fk_missing_index",
    "assessment": "red",
    "row_identity_fields": ["schema", "table", "constraint"],
    "confidence": "measured"
  }
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules_maintenance.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add references/rules/maintenance.json tests/unit/test_rules_maintenance.py
git commit -m "feat(p3): maintenance axis rules — dead tuples, stale stats, bloat, duplicate/missing indexes (P3.maintenance)"
```

---

### Task 5: `query-performance` axis rules + B3/A2 gating behavior tests

**Files:**
- Modify: `.agents/skills/db-report-generator/references/rules/query-performance.json`
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules_query_performance.py`

**Interfaces:**
- Consumes: `rules.evaluate_diagnostic`, `rules._quality_gated` (Task 1) — this task's tests are the designated coverage for spec §0.B3/A2 because `query_stats` is the only diagnostic in the whole system whose `quality.sampling_valid` can genuinely be `False` (`scripts/collectors/query_stats.py` sets it on `reset_detected`) or `quality.insufficient_activity` can be `True` (`total_window_calls < MINIMUM_ACTIVITY_CALLS = 5`).
- Produces: 2 populated rules.

Field names verified against `scripts/collectors/query_stats.py` (`queryid`, `window_mean_exec_time_ms`, scope=`query`) and `scripts/collectors/index_io.py` (`schema`, `table`, `index`, `cache_hit_ratio`, scope=`index`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rules_query_performance.py`:

```python
from scripts import rules


def _quality(sampling_valid=True, insufficient_activity=False):
    return {"sampling_valid": sampling_valid, "reset_detected": not sampling_valid,
            "insufficient_activity": insufficient_activity, "truncated": False}


def _rules_by_block():
    catalog = rules.load_catalog()
    by_block = {}
    for axis_rules in catalog.values():
        for rule in axis_rules:
            by_block.setdefault(rule["block"], []).append(rule)
    return by_block


def _query_row(queryid="1", mean_ms=1500.0):
    return {"queryid": queryid, "query": "select 1", "window_calls": 10,
            "window_total_exec_time_ms": mean_ms * 10, "window_mean_exec_time_ms": mean_ms,
            "window_stddev_exec_time_ms": 1.0, "window_rows_per_call": 1.0,
            "window_shared_blks_read": 0, "window_temp_blks_read": 0, "window_temp_blks_written": 0}


def test_slow_query_red_above_1000ms_mean_when_ungated():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "red"
    assert findings[0]["confidence"] == "estimated"
    assert findings[0]["finding_id"] == "query_perf.slow_query_mean_exec_time:1"


def test_slow_query_healthy_fires_nothing():
    diag = {"status": "ok", "quality": _quality(), "metrics": [_query_row(mean_ms=5.0)]}
    assert rules.evaluate_diagnostic("query_stats", diag, _rules_by_block()) == []


def test_b3_sampling_invalid_forces_unknown_heuristic():
    diag = {"status": "ok", "quality": _quality(sampling_valid=False),
            "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "unknown"
    assert findings[0]["confidence"] == "heuristic"


def test_a2_insufficient_activity_forces_unknown_heuristic():
    diag = {"status": "ok", "quality": _quality(insufficient_activity=True),
            "metrics": [_query_row(mean_ms=1500.0)]}
    findings = rules.evaluate_diagnostic("query_stats", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "unknown"
    assert findings[0]["confidence"] == "heuristic"


def test_gating_does_not_manufacture_findings_for_healthy_values():
    # A2/B3 gate a diagnostic whose value is otherwise green -> still zero findings.
    diag = {"status": "ok", "quality": _quality(sampling_valid=False),
            "metrics": [_query_row(mean_ms=5.0)]}
    assert rules.evaluate_diagnostic("query_stats", diag, _rules_by_block()) == []


def test_index_cache_hit_ratio_yellow_below_90_percent():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "t", "index": "t_idx",
                         "idx_blks_read": 10, "idx_blks_hit": 85, "cache_hit_ratio": 0.85, "idx_scan": 100}]}
    findings = rules.evaluate_diagnostic("index_io", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == "query_perf.index_cache_hit_ratio:public:t:t_idx"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rules_query_performance.py -v`
Expected: FAIL — 0 findings for every firing case (catalog is `[]`).

- [ ] **Step 3: Populate `references/rules/query-performance.json`**

```json
[
  {
    "finding_id": "query_perf.slow_query_mean_exec_time",
    "title": "Truy vấn có thời gian thực thi trung bình cao",
    "severity": "warning",
    "kind": "threshold",
    "block": "query_stats",
    "metric_key": "window_mean_exec_time_ms",
    "direction": "higher_is_worse",
    "thresholds": {"red": 1000, "yellow": 100},
    "row_identity_fields": ["queryid"],
    "confidence": "estimated"
  },
  {
    "finding_id": "query_perf.index_cache_hit_ratio",
    "title": "Tỷ lệ cache hit của index thấp",
    "severity": "notice",
    "kind": "threshold",
    "block": "index_io",
    "metric_key": "cache_hit_ratio",
    "direction": "lower_is_worse",
    "thresholds": {"red": 0.80, "yellow": 0.90},
    "row_identity_fields": ["schema", "table", "index"],
    "confidence": "measured"
  }
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules_query_performance.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add references/rules/query-performance.json tests/unit/test_rules_query_performance.py
git commit -m "feat(p3): query-performance axis rules + B3/A2 quality-gating coverage (P3.query-performance)"
```

---

### Task 6: `connections` axis rules (cluster/pool pressure, idle-in-transaction, blocking)

**Files:**
- Modify: `.agents/skills/db-report-generator/references/rules/connections.json`
- Test: `.agents/skills/db-report-generator/tests/unit/test_rules_connections.py`

**Interfaces:**
- Consumes: `rules.evaluate_diagnostic` (Task 1), `_eval_ratio_threshold`'s zero/None-denominator skip (Task 1) — `pool_pressure` deliberately relies on this to no-op when `configured_pool_size` is unset.
- Produces: 4 populated rules.

Field names verified against `scripts/collectors/connection_depth.py` (single-row metrics: `db_connections`, `cluster_connections`, `cluster_max_connections`, `idle_in_transaction`, `longest_txn_seconds`, `configured_pool_size`, scope=`database`) and `scripts/collectors/blocking.py` (`blocked_pid`, `blocking_pid`, `blocked_duration_seconds`, scope=`database`). Note `connection_depth.py`'s own docstring: "explicitly scoped: db-scoped counts never compared to cluster-wide max_connections without both being clearly labeled (the v3 bug)" — `cluster_pressure` and `pool_pressure` are deliberately two separate rules for this reason (cluster-scoped fields never mixed with db-scoped fields in one ratio).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rules_connections.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rules_connections.py -v`
Expected: FAIL — every firing assertion sees 0 findings (catalog is `[]`); the two "skip"/"empty" tests pass vacuously already, but run the whole file to confirm the firing tests fail first.

- [ ] **Step 3: Populate `references/rules/connections.json`**

```json
[
  {
    "finding_id": "connections.cluster_pressure",
    "title": "Áp lực kết nối toàn cluster cao",
    "severity": "warning",
    "kind": "ratio_threshold",
    "block": "connection_depth",
    "numerator_key": "cluster_connections",
    "denominator_key": "cluster_max_connections",
    "direction": "higher_is_worse",
    "thresholds": {"red": 0.90, "yellow": 0.60},
    "row_identity_fields": [],
    "confidence": "measured"
  },
  {
    "finding_id": "connections.pool_pressure",
    "title": "Áp lực connection pool của ứng dụng cao",
    "severity": "warning",
    "kind": "ratio_threshold",
    "block": "connection_depth",
    "numerator_key": "db_connections",
    "denominator_key": "configured_pool_size",
    "direction": "higher_is_worse",
    "thresholds": {"red": 0.90, "yellow": 0.60},
    "row_identity_fields": [],
    "confidence": "measured"
  },
  {
    "finding_id": "connections.idle_in_transaction",
    "title": "Có giao dịch idle-in-transaction kéo dài",
    "severity": "warning",
    "kind": "threshold",
    "block": "connection_depth",
    "metric_key": "longest_txn_seconds",
    "direction": "higher_is_worse",
    "thresholds": {"red": 600, "yellow": 60},
    "row_identity_fields": [],
    "confidence": "measured"
  },
  {
    "finding_id": "connections.blocking",
    "title": "Có phiên bị block kéo dài",
    "severity": "critical",
    "kind": "threshold",
    "block": "blocking",
    "metric_key": "blocked_duration_seconds",
    "direction": "higher_is_worse",
    "thresholds": {"red": 30, "yellow": 5},
    "row_identity_fields": ["blocked_pid", "blocking_pid"],
    "confidence": "measured"
  }
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules_connections.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add references/rules/connections.json tests/unit/test_rules_connections.py
git commit -m "feat(p3): connections axis rules — cluster/pool pressure, idle-in-transaction, blocking (P3.connections)"
```

---

### Task 7: wire `rules.evaluate_target` into `analyzer.py` + defensive B3 assertion

**Files:**
- Modify: `.agents/skills/db-report-generator/scripts/analyzer.py`
- Modify: `.agents/skills/db-report-generator/tests/unit/test_analyzer.py`

**Interfaces:**
- Consumes: `rules.evaluate_target(target: dict) -> None` (Tasks 1–6, now fully populated), `scripts.lib.invariants.check_confidence_invalidation(data: dict) -> list[str]` (Phase −1, unchanged).
- Produces: `target["diagnostics"][block]["findings"]` is now populated by every real target `analyzer.analyze()` returns; `analyze()` raises `RuntimeError` if the B3 invariant is ever violated (a rule-engine bug, not a normal runtime condition).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_analyzer.py`:

```python
def test_analyze_target_wires_rule_engine_into_diagnostics(monkeypatch):
    from scripts import analyzer

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(analyzer.db, "connect", lambda cfg: FakeConn())
    monkeypatch.setattr(analyzer.capabilities, "probe", lambda conn: {"extensions": {}})
    fake_diagnostics = {
        "database_stats": {
            "collector_version": "1", "scope": "database", "status": "ok", "reason": None,
            "quality": {"sampling_valid": True, "reset_detected": False,
                        "insufficient_activity": False, "truncated": False},
            "metrics": [{"cache_hit_ratio": 0.5}], "findings": [],
        },
    }
    monkeypatch.setattr(analyzer.collectors, "run_collectors", lambda conn, caps, sampling=None: fake_diagnostics)
    cfg = DbConfig(host="h", port=1, database="d", user="u", password="p", project_name="p")

    target = analyzer._analyze_target(cfg)

    findings = target["diagnostics"]["database_stats"]["findings"]
    assert len(findings) == 1
    assert findings[0]["finding_id"] == "db_health.cache_hit_ratio"
    assert findings[0]["assessment"] == "red"


def test_analyze_raises_on_b3_violation(monkeypatch):
    from scripts import analyzer

    def fake_analyze_target(cfg):
        return {
            "target_id": cfg.project_name, "database": cfg.database,
            "collection_status": "ok", "error": None, "capabilities": {}, "sampling": None,
            "diagnostics": {
                "query_stats": {
                    "collector_version": "1", "scope": "query", "status": "ok", "reason": None,
                    "quality": {"sampling_valid": False, "reset_detected": True,
                                "insufficient_activity": False, "truncated": False},
                    "metrics": [],
                    # deliberately violates B3: assessment/confidence not downgraded
                    "findings": [{"finding_id": "bug", "severity": "warning", "assessment": "red",
                                  "confidence": "measured", "title": "t",
                                  "evidence_ids": [], "remediation_ids": []}],
                },
            },
        }

    monkeypatch.setattr(analyzer, "_analyze_target", fake_analyze_target)
    cfg = DbConfig(host="h", port=1, database="d", user="u", password="p", project_name="p")

    with pytest.raises(RuntimeError, match="B3"):
        analyzer.analyze([cfg])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_analyzer.py -k "wires_rule_engine or b3_violation" -v`
Expected: FAIL — `test_analyze_target_wires_rule_engine_into_diagnostics` fails on `len(findings) == 1` (still `0`, since `rules.evaluate_target` isn't called yet); `test_analyze_raises_on_b3_violation` fails because `schema.validate_report` raises `jsonschema.exceptions.ValidationError`, not `RuntimeError` matching `"B3"` (the guard doesn't exist yet, so the malformed finding reaches schema validation and fails there instead, for an unrelated reason — a `findings` list is schema-valid shape-wise here, so validation may actually pass; either way this assertion fails without the new guard raising the specific `RuntimeError`).

- [ ] **Step 3: Modify `scripts/analyzer.py`**

Change the imports at the top:

```python
from scripts import capabilities, collectors, rules, sampler
from scripts.lib import db, invariants, schema
```

In `_analyze_target`, insert the rule-engine call right after `run_collectors` and before computing `collection_status`:

```python
            target["diagnostics"] = collectors.run_collectors(
                conn, target["capabilities"], sampling=sampling_result)
            rules.evaluate_target(target)
            target["collection_status"] = _collection_status(target["diagnostics"])
```

In `analyze()`, insert the defensive B3 assertion right before `schema.validate_report(report)`:

```python
    violations = invariants.check_confidence_invalidation(report)
    if violations:
        raise RuntimeError(f"B3 confidence-invalidation violated: {violations}")
    schema.validate_report(report)
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_analyzer.py -v`
Expected: PASS (all tests in the file, including the two new ones and every pre-existing Docker-gated test — the Docker-gated ones still skip cleanly without Docker, unaffected by this change).

- [ ] **Step 5: Commit**

```bash
git add scripts/analyzer.py tests/unit/test_analyzer.py
git commit -m "feat(p3): wire rule engine into analyzer.py + defensive B3 RuntimeError guard (P3 wiring)"
```

---

### Task 8: axis-matrix coverage tests (every block covered, security-rls placeholder verified, AXES order matches spec)

**Files:**
- Modify: `.agents/skills/db-report-generator/tests/unit/test_rules.py`

**Interfaces:**
- Consumes: `rules.load_catalog()`, `rules.AXES`, `scripts.collectors.COLLECTORS` (unchanged registry from P0–P2).
- Produces: no new production code — this task only adds tests that assert the catalog, as a whole, is internally consistent and matches the spec's axis listing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_rules.py`:

```python
from scripts.collectors import COLLECTORS


def test_every_rule_block_is_a_real_collector():
    catalog = rules.load_catalog()
    known_blocks = set(COLLECTORS)
    for axis, axis_rules in catalog.items():
        for rule in axis_rules:
            assert rule["block"] in known_blocks, f"{axis}/{rule['finding_id']} references unknown block {rule['block']!r}"


def test_security_rls_is_an_intentional_empty_placeholder():
    # No P0-P2 collector inspects Row Level Security policies (that's P4.3).
    # This axis is deliberately empty in P3, not a forgotten TODO.
    catalog = rules.load_catalog()
    assert catalog["security-rls"] == []


def test_axes_match_spec_section_8_order():
    assert rules.AXES == ("db-health", "query-performance", "maintenance",
                          "connections", "security-rls")


def test_every_rule_has_a_unique_finding_id_within_its_axis():
    catalog = rules.load_catalog()
    for axis, axis_rules in catalog.items():
        ids = [r["finding_id"] for r in axis_rules]
        assert len(ids) == len(set(ids)), f"duplicate finding_id within axis {axis!r}"


def test_every_rule_kind_is_registered():
    catalog = rules.load_catalog()
    for axis_rules in catalog.values():
        for rule in axis_rules:
            assert rule["kind"] in rules._EVALUATORS
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `pytest tests/unit/test_rules.py -k "block_is_a_real_collector or intentional_empty or axes_match or unique_finding_id or kind_is_registered" -v`
Expected: These should already PASS if Tasks 1–6 were implemented correctly (this task adds a safety net, not new behavior) — if any fails, it means a real defect slipped through an earlier task (e.g. a typo'd block name); fix the offending `references/rules/<axis>.json` entry directly, re-run, then proceed.

- [ ] **Step 3: (only if Step 2 found a failure) fix the offending catalog file, re-run**

Not expected in the normal path — included for completeness per this project's TDD convention. If Step 2 passes cleanly, skip to Step 4.

- [ ] **Step 4: Run the full test suite to confirm nothing regressed**

Run: `pytest tests/unit -v`
Expected: PASS (all unit tests; Docker-gated tests skip cleanly without Docker, as in every prior phase)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_rules.py
git commit -m "test(p3): axis-matrix coverage — every rule block real, security-rls placeholder verified, AXES order matches spec §8"
```

---

### Task 9: remove legacy 0–100 score from `SKILL.md` and `references/template-combined-report.md`

**Files:**
- Modify: `.agents/skills/db-report-generator/SKILL.md`
- Modify: `.agents/skills/db-report-generator/references/template-combined-report.md`
- Test: `.agents/skills/db-report-generator/tests/unit/test_skill_docs.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — this is a documentation-only task, verified by regex, not by any Python API.
- Produces: no more `/100` numbers or `_score}}` placeholders anywhere in these two files (spec §8 acceptance criterion).

This task deliberately does **not** rewrite the surrounding v3-era workflow narrative in `SKILL.md` (Bước 5.6/5.7/9 describe the old agent-driven approach and the deferred `compare.py` feature per the project's existing scope decision) — only the specific 0–100 score artifacts. A full `SKILL.md` v4 rewrite is P7's job.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_skill_docs.py`:

```python
import re


_FORBIDDEN = [re.compile(r"/100\b"), re.compile(r"\{\{\w*_score\}\}")]


def test_skill_md_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in SKILL.md"


def test_combined_report_template_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "references" / "template-combined-report.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in template-combined-report.md"


def test_combined_report_template_has_axis_matrix_placeholders(skill_dir):
    text = (skill_dir / "references" / "template-combined-report.md").read_text(encoding="utf-8")
    for axis_key in ("db_health", "query_performance", "maintenance", "connections", "security_rls"):
        assert f"{{{{{axis_key}_icon}}}}" in text, f"missing {axis_key}_icon placeholder"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_skill_docs.py -v`
Expected: FAIL — `SKILL.md` still contains its "Hệ thống chấm điểm" `/100` scoring table and the Bước 9 example's `Score` column (e.g. `🟡 78/100`); `template-combined-report.md` still contains `{{db_score}}/100` etc. and has no `{{db_health_icon}}`-style placeholders yet.

- [ ] **Step 3: Replace the scoring table in `references/template-combined-report.md`**

`references/template-combined-report.md` currently reads (verbatim, lines 8-22):

````markdown
## BẢNG ĐIỀU KHIỂN TỔNG QUAN

| Hạng Mục | Điểm | Trạng Thái |
|----------|------|------------|
| **Sức Khỏe Database** | {{db_score}}/100 | {{db_status_icon}} |
| **Chất Lượng Code (Lớp DB)** | {{code_score}}/100 | {{code_status_icon}} |
| **Bảo Mật** | {{security_score}}/100 | {{security_status_icon}} |
| **Hiệu Suất** | {{perf_score}}/100 | {{perf_status_icon}} |
| **TỔNG** | **{{total_score}}/100** | **{{total_status_icon}}** |

### Quy Ước Điểm
- 🟢 90-100: Xuất sắc
- 🟡 70-89: Tốt, có điểm cần cải thiện
- 🟠 50-69: Cần chú ý
- 🔴 0-49: Nghiêm trọng, cần xử lý ngay
````

Using the `Edit` tool, replace that exact block (from `## BẢNG ĐIỀU KHIỂN TỔNG QUAN` through the last `- 🔴 0-49: Nghiêm trọng, cần xử lý ngay` line) with:

```markdown
## MA TRẬN TRỤC (AXIS MATRIX)

| Trục | Trạng thái | Độ tin cậy | Ghi chú |
|------|-----------|-----------|---------|
| DB Health | {{db_health_icon}} | {{db_health_confidence}} | {{db_health_note}} |
| Query Performance | {{query_performance_icon}} | {{query_performance_confidence}} | {{query_performance_note}} |
| Maintenance | {{maintenance_icon}} | {{maintenance_confidence}} | {{maintenance_note}} |
| Connections | {{connections_icon}} | {{connections_confidence}} | {{connections_note}} |
| Security/RLS | {{security_rls_icon}} | {{security_rls_confidence}} | {{security_rls_note}} |

**Quy Ước Ký Hiệu:**
- 🟢 green — không phát hiện vấn đề ở ngưỡng đã đo
- 🟡 yellow — cảnh báo sớm, cần theo dõi
- 🔴 red — vấn đề nghiêm trọng, cần xử lý
- ⚪ unknown — dữ liệu không đủ tin cậy để đánh giá (không được nâng cấp lên green/yellow/red — spec §0.B3)
- ➖ not_applicable — trục không áp dụng cho hệ thống này

**Độ tin cậy:** `measured` (đo trực tiếp) > `estimated` (suy ra từ mẫu) > `heuristic` (suy đoán, độ tin cậy thấp nhất — luôn đi kèm `unknown` theo §0.B3).
```

- [ ] **Step 4: Replace the scoring artifacts in `SKILL.md`**

`SKILL.md` is currently a v3-era, agent-generates-scripts workflow document top to bottom (a full v4 rewrite is P7's job — out of scope here). Only the three `/100`-scoring artifacts below are touched in this task; the surrounding Bước 5/8 narrative is left untouched.

**4a.** `SKILL.md` currently reads (verbatim, lines 620-627, inside "### Bước 6: Tạo Báo Cáo Tổng Hợp"):

````markdown
**Hệ thống chấm điểm:**

| Hạng mục | Tiêu chí | Điểm |
|----------|---------|------|
| DB Health | Cache >95%: +30, Connections <60%: +20, No blocking: +20, Dead tuples <5%: +15, Size hợp lý: +15 | /100 |
| Code Quality | No SQL injection: +30, No N+1: +25, Parameterized queries: +20, Proper connection mgmt: +15, Migration up-to-date: +10 | /100 |
| Security | No hardcoded creds: +40, No SQL injection: +30, Proper auth: +30 | /100 |
| Performance | Index coverage: +30, No slow queries >1s: +25, Cache hit >90%: +25, No SELECT *: +20 | /100 |
````

Using the `Edit` tool, replace that exact block with:

```markdown
### Mô hình đánh giá theo trục (Axis Model)

Từ P3 trở đi, hệ thống KHÔNG dùng điểm số tổng hợp 0-100 (double-counting, false precision). Mỗi trục trong 5 trục sau được đánh giá độc lập bằng 🟢/🟡/🔴/⚪/➖ kèm độ tin cậy (`measured`/`estimated`/`heuristic`):

| Trục | Nguồn rule | Diagnostic blocks liên quan |
|------|-----------|------------------------------|
| DB Health | `references/rules/db-health.json` | `database_stats`, `wraparound` |
| Query Performance | `references/rules/query-performance.json` | `query_stats`, `index_io` |
| Maintenance | `references/rules/maintenance.json` | `dead_tuples`, `stale_stats`, `index_bloat`, `duplicate_index`, `fk_missing_index` |
| Connections | `references/rules/connections.json` | `connection_depth`, `blocking` |
| Security/RLS | `references/rules/security-rls.json` (rỗng — chưa có collector, xem P4.3) | — |

Việc ánh xạ block → trục là tra cứu ở code (`scripts/rules.py`), không phải field trong schema — schema finding không có field `axis`.
```

**4b.** `SKILL.md` currently reads (verbatim, line 637, inside "### Bước 7: So Sánh Với Báo Cáo Trước"):

```markdown
   - So sánh Code Score (nếu có)
```

Using the `Edit` tool, replace that exact line with:

```markdown
   - So sánh số lượng finding theo severity giữa các lần chạy (không còn khái niệm "Code Score" tổng hợp)
```

**4c.** `SKILL.md` currently reads (verbatim, lines 776-779, inside the "### Bước 9: Tổng Hợp Tất Cả Dự Án" example block):

````markdown
| # | Dự Án    | DB Status | Code Status | Score | P0 | P1 | P2 | Solutions |
|---|----------|-----------|-------------|-------|----|----|----|-----------|
| 1 | Project_A| 🟢 95%   | 🟡 78/100   | 85    | 0  | 2  | 5  | 7         |
| 2 | Project_B| 🟡 82%   | 🔴 45/100   | 62    | 3  | 5  | 8  | 16        |
````

Using the `Edit` tool, replace that exact block (still inside the surrounding ` ``` ` example fence — do not touch the fence markers themselves) with:

````markdown
| # | Dự Án    | Trục Xấu Nhất  | P0 | P1 | P2 | Solutions |
|---|----------|----------------|----|----|----|-----------|
| 1 | Project_A| 🟡 maintenance | 0  | 2  | 5  | 7         |
| 2 | Project_B| 🔴 db-health   | 3  | 5  | 8  | 16        |
````

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_skill_docs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full test suite one more time**

Run: `pytest tests/unit -v`
Expected: PASS (all unit tests, Docker-gated ones skip cleanly)

- [ ] **Step 7: Commit**

```bash
git add SKILL.md references/template-combined-report.md tests/unit/test_skill_docs.py
git commit -m "docs(p3): remove legacy 0-100 combined score, replace with per-axis matrix (spec §8 acceptance)"
```

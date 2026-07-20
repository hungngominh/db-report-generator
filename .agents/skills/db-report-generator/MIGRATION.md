# Migration Guide — db-report-generator v3 → v4

`db-report-generator` moved from an "agent hand-writes SQL and fills a Handlebars template" model (v3) to a deterministic Python pipeline (v4): `scripts/analyzer.py` connects and collects, `scripts/rules.py` evaluates findings against `references/rules/*.json`, `scripts/render.py` writes `DB_STATUS_REPORT.md`/`FINDINGS.md`/`report_summary.json`. This document is for anyone who has an existing v3-era workspace, notes, or automation built around this skill.

## What triggers this migration

You're affected if you have any of the following from before this upgrade:
- A copy of `references/template-db-report.md` you were filling in by hand or via your own script
- Notes or scripts that reference a `Code Quality /100` or any other `.../100` composite score
- Automation that parses `**Rollback:**` sections out of `PERFORMANCE_SOLUTIONS.md`
- A workspace still pointing at `.claude/skills/db-report-generator/` (that path never existed as a real Python runtime in this repo — see `README.md`'s Buoc 1/4 for the corrected layout)

## Report generation: what changed

| | v3 | v4 |
|---|---|---|
| DB status report | Agent hand-runs 12 raw-SQL sections, fills `references/template-db-report.md` | `scripts/run_report.py` (run via `python -m scripts.run_report <.env> <out_dir>`) generates `DB_STATUS_REPORT.md` + `FINDINGS.md` + `report_summary.json` deterministically |
| Source of truth | The rendered Markdown itself | `report_data.json` (schema: `references/report-data.schema.json`) — Markdown is a rendering of it |
| Code/Combined/Solutions reports | Agent-authored from templates | Unchanged — still agent-authored, templates now live in `assets/templates/` (moved from `references/`) |
| Scoring | Composite `0-100` score | 5-axis model (`db-health`, `query-performance`, `maintenance`, `connections`, `security-rls`), each 🟢/🟡/🔴/⚪/➖ + confidence tier (`measured`/`estimated`/`heuristic`) — no single number |
| Remediation SQL | Ad hoc `**Rollback:**` heading | `recovery_or_rollback` field, gated by a 5-tier `remediation_class` taxonomy (`references/remediation-policy.md`) — `dangerous`-tier fixes are excluded from any "run now" script block and require manual review |
| Slow query diagnosis | `pg_stat_statements` text only | Same, plus `EXPLAIN` plans attached automatically (plan-only by default; `ANALYZE` requires explicit opt-in + allowlist — see `ExplainMode` below) |
| Index suggestions | Manual reading of `queries-index.sql` output | `scripts/index_advisor.py` suggests column-level indexes (composite/partial/covering) from parsed slow-query predicates, checking for existing indexes first |
| RLS | Not covered | `scripts/collectors/rls_policies.py` detects unwrapped `auth.uid()`/`current_setting()` re-evaluated per row, and RLS policy columns lacking a supporting index |
| Schema hygiene | Not covered | Missing primary key, oversized UUID PK, `timestamp` without time zone |

## Config: new optional `.env` fields (v4)

All are optional — omitting them falls back to the defaults below, so an unmodified v3-era `.env` file still works:

```json
{
  "SamplingWindowSeconds": 30,
  "ExplainMode": "plan",
  "ExplainTopN": 5,
  "ExplainAnalyzeTopN": 0,
  "ExplainStatementTimeoutMs": 3000,
  "ExplainLockTimeoutMs": 500
}
```

`ExplainMode` is `off` (don't run EXPLAIN), `plan` (default — EXPLAIN without ANALYZE, never executes the query), or `analyze` (explicit opt-in; still gated by an allowlist and a real PostgreSQL-grammar parser classification, not a regex, before any query is allowed to run with ANALYZE).

## File layout changes

- `references/template-db-report.md` — **removed**. `scripts/render.py` supersedes it; there is nothing to migrate to, since its output is now generated, not filled in.
- `references/template-code-report.md`, `references/template-combined-report.md`, `references/template-solutions-report.md` — **moved** to `assets/templates/`. If you had local overrides of these files, move them to the same path under `assets/templates/`.
- `queries-overview.sql`, `queries-performance.sql`, `queries-index.sql` (`references/`) — kept as historical human-readable reference material only; the agent's Bước 3 no longer runs these files.

## If you have automation scraping the old reports

Anything parsing `DB_STATUS_REPORT.md`'s old 11-section Handlebars layout, a `.../100` score, or a `**Rollback:**` heading needs updating: read `report_data.json` directly instead (stable schema, `jsonschema`-validated on every run) rather than parsing Markdown.

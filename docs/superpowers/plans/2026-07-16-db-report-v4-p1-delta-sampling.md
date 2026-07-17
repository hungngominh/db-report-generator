# Phase 1 — Delta Sampling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the analyzer a correct two-sample "delta" measurement of `pg_stat_statements` — the windowed averages/stddev/IO counters a query produced *during* the observation window, never lifetime cumulative numbers, never a naive `mean2-mean1` subtraction — and wire it through as a new `query_stats` collector (P1.2), with the runtime model that keeps multi-target sampling from growing linearly (B4).

**Architecture:** A new `scripts/sampler.py` takes two point-in-time snapshots of `pg_stat_statements` (+ its reset marker + server start time) `window_seconds` apart and reduces them to per-`queryid` deltas using an exact combined-variance formula (never `stddev2-stddev1`). `analyzer.py` calls the sampler **once per target** (not once per collector — this is what makes B4's bounded-runtime model possible) and passes the result into `collectors.run_collectors(..., sampling=...)`, which merges it into every collector's `caps["sampling"]` without changing the existing 5 collectors' `collect(conn, caps)` signature. A new `scripts/collectors/query_stats.py` collector (P1.2) is a pure transformer: it reads the precomputed deltas out of `caps["sampling"]` and emits schema-valid `metrics[]`, sorted by `total_exec_time` descending (the new default top-sort per spec §6 P1.2, replacing `mean`). `analyzer.analyze()` also gains bounded `ThreadPoolExecutor` concurrency across targets (each target already owns an independent connection) plus a latency-budget warning, satisfying B4's "runtime must not grow linearly in N×30s" requirement.

**Tech Stack:** Python ≥3.10, psycopg2 (`psycopg2.sql.Identifier` for schema-qualification, same pattern P0b established for `pgstattuple`), pytest (+ Docker `postgres:16` fixture — this phase adds `shared_preload_libraries=pg_stat_statements` to the container so the extension actually tracks stats, not just installs), `jsonschema` (via existing `scripts.lib.schema`), stdlib `concurrent.futures`/`statistics`/`warnings`.

## Global Constraints

- **Read-only / no side effects:** the sampler issues only `SELECT`s against `pg_stat_statements`/`pg_stat_statements_info`/`pg_postmaster_start_time()`. Never DDL/DML, never calls `pg_stat_statements_reset()` or `pg_stat_clear_snapshot()` in production code — `lib.db.connect()` already runs `autocommit=True`, so every individual statement is already its own transaction, which structurally satisfies spec §0.A2's "two samples in separate transactions" requirement without needing an explicit snapshot-clear call.
- **Forbidden formulas (spec §0.A2, non-negotiable):** `window_mean_exec_time = Δtotal_exec_time/Δcalls` and `window_rows_per_call = Δrows/Δcalls` — **never** `mean2-mean1`. `window_stddev_exec_time` must **never** be `stddev2-stddev1`; it must be recovered from the two cumulative (count, mean, population-stddev) snapshots via the combined-variance / sum-of-squares identity (`SS = n*(stddev²+mean²)`), implemented once in `sampler.combined_stddev` and reused everywhere a windowed stddev is needed.
- **Reset/restart detection (spec §0.A2):** if `pg_stat_statements_info.stats_reset` changed OR `pg_postmaster_start_time()` changed between the two samples, the **whole window** is invalid: `quality.sampling_valid=false`, `reset_detected=true`, `metrics=[]`, and the collector must never emit green/yellow/red for that target's query_stats block this run.
- **Per-queryid eviction (spec §0.B2):** `pg_stat_statements_info.dealloc` is a **global** counter and must not be used to invalidate individual entries. Per `queryid`: if `calls` decreased between the two samples, drop **only that entry's** delta (not a global reset). A `queryid` present in sample 2 but absent from sample 1 is a legitimately new query (its whole `calls` count occurred inside the window) — not an eviction case.
- **Minimum activity (spec §6 P1.1):** below `minimum_activity` total window calls, `quality.insufficient_activity=true` (the query_stats collector still emits `status="ok"` with empty/thin `metrics`; the confidence-invalidation invariant already implemented in `lib/invariants.py` downgrades any finding derived from it — findings themselves are out of scope this phase, metrics-only, same as P0b).
- **Schema-qualification:** every reference to `pg_stat_statements`/`pg_stat_statements_info` is built with `psycopg2.sql.Identifier(schema, name)` using the schema recorded by `capabilities.probe()`, never bare/search_path-relative names — same pattern P0b's `index_bloat.py` established for `pgstattuple_approx`, required because managed PG (Supabase) can install extensions outside `public`/off `search_path`.
- **Metrics-only this phase:** `query_stats.collect()` returns `findings: []`. Thresholds/severity/assessment are Phase 3.
- **Schema-valid:** every `diagnostic` still validates against `$defs/diagnostic` (unchanged this phase). The one schema change this phase is additive: a new optional, nullable `target.sampling` object (`window_seconds`, `sample1_at`, `sample2_at`, `reset_detected`) — `additionalProperties: false` on it, like every other object in this schema.
- **Isolation:** a query_stats collection failure must not kill the target or the run — same `run_collectors` per-collector isolation from P0b, unchanged.
- **Determinism:** `compute_deltas` sorts its output by `(-window_total_exec_time_ms, queryid)` — stable, no timestamps/random in metric bodies. `query_stats.collect()` does not re-sort; it trusts the sampler's order.
- **Concurrency (spec §0.B4):** multi-target sampling must use a bounded-parallel model (`ThreadPoolExecutor`, one connection per target — safe, connections are already independent) so wall-clock time does not grow linearly with `N targets × window_seconds`. `analyzer.analyze()` records each target's actual `window_seconds` in `target["sampling"]` and warns (via `warnings.warn`, `RuntimeWarning`) when total elapsed time is suspiciously close to the fully-serial sum for N>1 targets.
- **Reports in Vietnamese** downstream; keep English for table/column/SQL identifiers and Python code.

## Interfaces (shared across tasks)

- `scripts.capabilities.probe(conn) -> dict` (exists, P0a) — `caps["extensions"]["pg_stat_statements"] -> {"present": True, "schema": "..."}` when installed.
- `scripts.collectors.base.diagnostic(...)` / `base.skipped(...)` / `base.STRUCTURAL_QUALITY` (exist, P0b).
- Sampler contract (**Produced by Task 2 (math) + Task 3 (live capture), consumed by Task 6 (analyzer) and Task 5 (query_stats collector)**):
  - `scripts.sampler.combined_stddev(n1: int, mean1: float, stddev1: float, n2: int, mean2: float, stddev2: float) -> float` — population stddev of just the `(n2-n1)` delta subset. Returns `0.0` when `n2 <= n1`.
  - `scripts.sampler.reset_between(snap1: dict, snap2: dict) -> bool` — `True` if `stats_reset` or `postmaster_start` differ.
  - `scripts.sampler.compute_deltas(snap1: dict, snap2: dict) -> dict` — `{"reset_detected": bool, "deltas": list[dict]}`. Each delta dict: `queryid` (str), `query` (str), `window_calls` (int), `window_total_exec_time_ms` (float), `window_mean_exec_time_ms` (float), `window_stddev_exec_time_ms` (float), `window_rows_per_call` (float), `window_shared_blks_read` (int), `window_temp_blks_read` (int), `window_temp_blks_written` (int). Sorted `(-window_total_exec_time_ms, queryid)`.
  - `scripts.sampler.snapshot_pg_stat_statements(conn, schema: str) -> dict` — `{"stats_reset": <ts>, "postmaster_start": <ts>, "rows": dict[queryid(str), row-dict]}`.
  - `scripts.sampler.sample_pg_stat_statements_window(conn, schema: str, window_seconds: int, *, sleep_fn=time.sleep) -> dict` — `{"window_seconds": int, "sample1_at": str, "sample2_at": str, "reset_detected": bool, "deltas": list[dict]}`. `sleep_fn` is injectable (tests run activity mid-window instead of literally sleeping).
- `scripts.collectors.run_collectors(conn, caps, registry=None, *, sampling=None) -> dict[str, dict]` (**Modified by Task 4**) — merges `sampling` into a **copy** of `caps` as `caps["sampling"]` before calling each collector (never mutates the caller's `caps` dict — `target["capabilities"]` must never carry the raw sampling payload).
- `scripts.collectors.query_stats.collect(conn, caps) -> dict` (**Produced by Task 5**) — reads `caps["sampling"]`, emits a diagnostic with `scope="query"`.
- `scripts.lib.envparse.DbConfig.sampling_window_seconds: int = 30` (**Modified by Task 6**), parsed from optional `.env` key `SamplingWindowSeconds`.
- `scripts.analyzer._analyze_target(cfg) -> dict` (**Modified by Task 6**) — target dict gains a `"sampling"` key: `None`, or `{"window_seconds", "sample1_at", "sample2_at", "reset_detected"}` (the raw `deltas` list never lands here — only in the `query_stats` diagnostic's `metrics[]`).
- `scripts.analyzer.analyze(configs, *, redaction_mode="redact") -> dict` (**Modified by Task 7**) — same signature, now runs targets through a bounded `ThreadPoolExecutor` when `len(configs) > 1`.

---

## File Structure

```
scripts/
  sampler.py                       # NEW — P1.1: pure math (Task 2) + live snapshot/window capture (Task 3)
  collectors/
    __init__.py                    # MODIFY — sampling kwarg passthrough (Task 4); register query_stats (Task 5)
    query_stats.py                 # NEW — P1.2 collector (Task 5)
  lib/
    envparse.py                    # MODIFY — SamplingWindowSeconds -> DbConfig.sampling_window_seconds (Task 6)
  analyzer.py                      # MODIFY — sampler wiring + target.sampling (Task 6); bounded concurrency + latency warning (Task 7)
references/
  report-data.schema.json          # MODIFY — target.sampling nullable object (Task 1)
tests/
  pgcontainer.py                   # MODIFY — preload pg_stat_statements so CREATE EXTENSION actually tracks stats (Task 3)
  unit/
    test_schema.py                 # MODIFY — sampling field validity (Task 1)
    test_sampler_math.py           # NEW — combined_stddev / reset_between / compute_deltas (Task 2)
    test_sampler_live.py           # NEW — snapshot/window against Docker PG (Task 3)
    test_collectors_framework.py   # MODIFY — sampling passthrough (Task 4)
    test_query_stats.py            # NEW — P1.2 collector (Task 5)
    test_envparse.py               # MODIFY — SamplingWindowSeconds parsing (Task 6)
    test_analyzer.py               # MODIFY — sampling wiring (Task 6); concurrency + latency warning (Task 7)
```

---

### Task 1: Schema extension — `target.sampling`

**Files:**
- Modify: `SKILL_DIR/references/report-data.schema.json`
- Modify: `SKILL_DIR/tests/unit/test_schema.py`

**Interfaces:**
- Consumes: `scripts.lib.schema.validation_errors` (exists, P−1).
- Produces: schema `$defs/target` gains an optional, nullable `sampling` property — `{window_seconds: int>=0, sample1_at: string, sample2_at: string, reset_detected: bool}`, consumed by Task 6's `analyzer.py` change.

- [ ] **Step 1: Write the failing test**

Add to `SKILL_DIR/tests/unit/test_schema.py` (append after the existing tests, keep the existing `MINIMAL` constant):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_schema.py -q`
Expected: FAIL — `test_target_sampling_object_is_valid` and `test_target_sampling_missing_is_still_valid` fail because `additionalProperties: false` on `$defs/target` currently rejects the unknown `sampling` key.

- [ ] **Step 3: Add `sampling` to the schema**

In `SKILL_DIR/references/report-data.schema.json`, inside `$defs.target.properties` (after `"diagnostics"`), add:

```json
        "sampling": {
          "type": ["object", "null"],
          "additionalProperties": false,
          "required": ["window_seconds", "sample1_at", "sample2_at", "reset_detected"],
          "properties": {
            "window_seconds": {"type": "integer", "minimum": 0},
            "sample1_at": {"type": "string"},
            "sample2_at": {"type": "string"},
            "reset_detected": {"type": "boolean"}
          }
        }
```

Do **not** add `"sampling"` to `$defs.target.required` — it stays optional so targets that never sample (no `pg_stat_statements`) remain valid with the key entirely absent or set to `null`.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_schema.py -q`
Expected: PASS (all tests in the file, including the new ones).

- [ ] **Step 5: Run the full existing suite to confirm no regression**

Run: `python -m pytest tests/unit -q -k "not live and not docker"` (or the project's normal `pytest` invocation) to confirm the schema change didn't break `test_fixture.py`/`test_render.py`/`test_analyzer.py`'s schema-valid assertions.
Expected: PASS, same pass count as before this task plus the 5 new schema tests.

- [ ] **Step 6: Commit**

```bash
git add references/report-data.schema.json tests/unit/test_schema.py
git commit -m "feat(p1): add optional target.sampling schema field (P1.1)"
```

---

### Task 2: `sampler.py` — pure math

**Files:**
- Create: `SKILL_DIR/scripts/sampler.py`
- Create: `SKILL_DIR/tests/unit/test_sampler_math.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB).
- Produces: `sampler.combined_stddev(...)`, `sampler.reset_between(snap1, snap2)`, `sampler.compute_deltas(snap1, snap2)`, `sampler._ZERO_ROW` (internal default row for a queryid new to the window) — consumed by Task 3 (live capture calls `compute_deltas`) and indirectly by Task 5/6.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_sampler_math.py`:

```python
import statistics

import pytest

from scripts.sampler import combined_stddev, compute_deltas, reset_between


def test_combined_stddev_matches_population_stddev_of_delta_subset():
    before = [10.0, 12.0, 11.0, 9.0, 13.0]
    during = [50.0, 55.0, 45.0, 60.0, 40.0, 52.0]
    combined = before + during
    n1, mean1, stddev1 = len(before), statistics.fmean(before), statistics.pstdev(before)
    n2, mean2, stddev2 = len(combined), statistics.fmean(combined), statistics.pstdev(combined)
    result = combined_stddev(n1, mean1, stddev1, n2, mean2, stddev2)
    expected = statistics.pstdev(during)
    assert result == pytest.approx(expected, abs=1e-9)


def test_combined_stddev_zero_delta_calls_returns_zero():
    assert combined_stddev(10, 5.0, 1.0, 10, 5.0, 1.0) == 0.0


def test_combined_stddev_never_equals_naive_subtraction():
    # Regression guard for spec §0.A2: stddev2-stddev1 is forbidden and is
    # not even a valid stddev (can go negative) — the combined formula must
    # produce the true population stddev of the delta subset instead.
    before = [100.0] * 5           # stddev1 == 0
    during = [1.0, 200.0, 5.0, 300.0]
    combined = before + during
    n1, mean1, stddev1 = 5, 100.0, 0.0
    n2, mean2, stddev2 = 9, statistics.fmean(combined), statistics.pstdev(combined)
    result = combined_stddev(n1, mean1, stddev1, n2, mean2, stddev2)
    expected = statistics.pstdev(during)
    assert result == pytest.approx(expected, abs=1e-6)
    assert result != pytest.approx(stddev2 - stddev1)


def _snap(stats_reset, postmaster_start, rows):
    return {"stats_reset": stats_reset, "postmaster_start": postmaster_start, "rows": rows}


def test_reset_between_true_when_stats_reset_changes():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:05:00Z", "2026-01-01T00:00:00Z", {})
    assert reset_between(s1, s2) is True


def test_reset_between_true_when_postmaster_restarts():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z", {})
    assert reset_between(s1, s2) is True


def test_reset_between_false_when_unchanged():
    s1 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    s2 = _snap("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {})
    assert reset_between(s1, s2) is False


_ROW = {"query": "select 1", "calls": 10, "total_exec_time": 100.0, "rows": 10,
        "mean_exec_time": 10.0, "stddev_exec_time": 0.0,
        "shared_blks_read": 5, "temp_blks_read": 0, "temp_blks_written": 0}


def test_compute_deltas_uses_delta_formulas_not_mean_subtraction():
    row1 = {**_ROW, "calls": 10, "total_exec_time": 100.0, "rows": 10, "mean_exec_time": 10.0}
    row2 = {**_ROW, "calls": 14, "total_exec_time": 180.0, "rows": 18, "mean_exec_time": 12.857}
    s1 = _snap("t0", "p0", {"q1": row1})
    s2 = _snap("t0", "p0", {"q1": row2})
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is False
    [d] = result["deltas"]
    assert d["window_calls"] == 4
    assert d["window_total_exec_time_ms"] == pytest.approx(80.0)
    assert d["window_mean_exec_time_ms"] == pytest.approx(20.0)   # 80/4, not 12.857-10.0
    assert d["window_rows_per_call"] == pytest.approx(2.0)        # (18-10)/4
    assert d["window_shared_blks_read"] == 0


def test_compute_deltas_global_reset_yields_empty_and_flag():
    s1 = _snap("t0", "p0", {"q1": _ROW})
    s2 = _snap("t1", "p0", {"q1": _ROW})   # stats_reset changed
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is True
    assert result["deltas"] == []


def test_compute_deltas_drops_only_the_evicted_entry_not_the_whole_window():
    stable = {**_ROW, "calls": 20, "total_exec_time": 200.0, "rows": 20}
    evicted1 = {**_ROW, "calls": 50, "total_exec_time": 5000.0, "rows": 50}
    evicted2 = {**_ROW, "calls": 3, "total_exec_time": 30.0, "rows": 3}   # calls DECREASED -> evicted+recreated
    s1 = _snap("t0", "p0", {"q_stable": stable, "q_evicted": evicted1})
    s2 = _snap("t0", "p0", {"q_stable": {**stable, "calls": 25, "total_exec_time": 250.0, "rows": 25},
                             "q_evicted": evicted2})
    result = compute_deltas(s1, s2)
    assert result["reset_detected"] is False
    ids = {d["queryid"] for d in result["deltas"]}
    assert ids == {"q_stable"}   # q_evicted's decreasing-calls entry was dropped, not the whole window


def test_compute_deltas_new_queryid_counts_its_full_window_calls():
    s1 = _snap("t0", "p0", {})
    s2 = _snap("t0", "p0", {"q_new": {**_ROW, "calls": 3, "total_exec_time": 30.0, "rows": 3}})
    result = compute_deltas(s1, s2)
    [d] = result["deltas"]
    assert d["queryid"] == "q_new"
    assert d["window_calls"] == 3


def test_compute_deltas_sorted_by_total_exec_time_desc_then_queryid():
    row_a = {**_ROW, "calls": 100, "total_exec_time": 50.0, "rows": 100}    # low total, high calls
    row_b = {**_ROW, "calls": 2, "total_exec_time": 500.0, "rows": 2}       # high total, low calls
    s1 = _snap("t0", "p0", {})
    s2 = _snap("t0", "p0", {"a": row_a, "b": row_b})
    result = compute_deltas(s1, s2)
    assert [d["queryid"] for d in result["deltas"]] == ["b", "a"]   # total_exec_time desc, not calls
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_sampler_math.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'scripts.sampler'`).

- [ ] **Step 3: Write the minimal implementation**

Create `SKILL_DIR/scripts/sampler.py`:

```python
"""Delta sampling of pg_stat_statements (spec §6 P1.1 + §0.A2 + §0.B2).

Two cumulative snapshots, `window_seconds` apart, reduce to per-queryid
window deltas. Windowed formulas only (Δtotal/Δcalls, ...) — never a naive
mean2-mean1 or stddev2-stddev1 subtraction (forbidden by spec §0.A2).
"""
import time
from datetime import datetime, timezone

import psycopg2.sql as sql

_ZERO_ROW = {
    "query": "", "calls": 0, "total_exec_time": 0.0, "rows": 0,
    "mean_exec_time": 0.0, "stddev_exec_time": 0.0,
    "shared_blks_read": 0, "temp_blks_read": 0, "temp_blks_written": 0,
}

_SNAPSHOT_SQL = """
SELECT queryid::text, query, calls, total_exec_time, rows, mean_exec_time,
       stddev_exec_time, shared_blks_read, temp_blks_read, temp_blks_written
FROM {pgss}
"""
_INFO_SQL = "SELECT stats_reset FROM {info}"


def combined_stddev(n1: int, mean1: float, stddev1: float,
                     n2: int, mean2: float, stddev2: float) -> float:
    """Population stddev of the (n2-n1) delta subset, from two cumulative
    (count, mean, population-stddev) snapshots. Exact via the sum-of-squares
    identity SS = n*(stddev**2 + mean**2); never stddev2-stddev1.
    """
    dn = n2 - n1
    if dn <= 0:
        return 0.0
    ss1 = n1 * (stddev1 ** 2 + mean1 ** 2)
    ss2 = n2 * (stddev2 ** 2 + mean2 ** 2)
    delta_sum = n2 * mean2 - n1 * mean1
    delta_mean = delta_sum / dn
    variance = max((ss2 - ss1) / dn - delta_mean ** 2, 0.0)
    return variance ** 0.5


def reset_between(snap1: dict, snap2: dict) -> bool:
    """True if pg_stat_statements was reset or the server restarted between
    the two snapshots (spec §0.A2) — invalidates the whole sampling window.
    """
    return (snap1["stats_reset"] != snap2["stats_reset"]
            or snap1["postmaster_start"] != snap2["postmaster_start"])


def compute_deltas(snap1: dict, snap2: dict) -> dict:
    """Turn two pg_stat_statements snapshots into windowed deltas.

    A global reset/restart invalidates the whole window (empty deltas,
    reset_detected=True — spec §0.A2). Per-queryid eviction — calls
    decreased between the two samples (spec §0.B2) — drops only that
    entry, not the whole window. A queryid absent from snapshot 1 is a
    legitimately new query: its full calls count occurred inside the
    window, not an eviction case.
    """
    if reset_between(snap1, snap2):
        return {"reset_detected": True, "deltas": []}

    deltas = []
    for queryid, row2 in snap2["rows"].items():
        row1 = snap1["rows"].get(queryid, _ZERO_ROW)
        if row2["calls"] < row1["calls"]:
            continue  # per-entry eviction+recreation (B2) — drop this entry only
        window_calls = row2["calls"] - row1["calls"]
        if window_calls == 0:
            continue
        window_total = row2["total_exec_time"] - row1["total_exec_time"]
        window_rows = row2["rows"] - row1["rows"]
        stddev = combined_stddev(
            row1["calls"], row1["mean_exec_time"], row1["stddev_exec_time"],
            row2["calls"], row2["mean_exec_time"], row2["stddev_exec_time"],
        )
        deltas.append({
            "queryid": queryid,
            "query": row2["query"],
            "window_calls": window_calls,
            "window_total_exec_time_ms": window_total,
            "window_mean_exec_time_ms": window_total / window_calls,
            "window_stddev_exec_time_ms": stddev,
            "window_rows_per_call": window_rows / window_calls,
            "window_shared_blks_read": row2["shared_blks_read"] - row1["shared_blks_read"],
            "window_temp_blks_read": row2["temp_blks_read"] - row1["temp_blks_read"],
            "window_temp_blks_written": row2["temp_blks_written"] - row1["temp_blks_written"],
        })
    deltas.sort(key=lambda d: (-d["window_total_exec_time_ms"], d["queryid"]))
    return {"reset_detected": False, "deltas": deltas}


def snapshot_pg_stat_statements(conn, schema: str) -> dict:
    """Placeholder — implemented in Task 3."""
    raise NotImplementedError


def sample_pg_stat_statements_window(conn, schema: str, window_seconds: int,
                                      *, sleep_fn=time.sleep) -> dict:
    """Placeholder — implemented in Task 3."""
    raise NotImplementedError
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_sampler_math.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/sampler.py tests/unit/test_sampler_math.py
git commit -m "feat(p1): sampler pure math — combined stddev, reset detection, per-queryid deltas (P1.1, A2, B2)"
```

---

### Task 3: `sampler.py` — live snapshot + window capture

**Files:**
- Modify: `SKILL_DIR/scripts/sampler.py`
- Modify: `SKILL_DIR/tests/pgcontainer.py`
- Create: `SKILL_DIR/tests/unit/test_sampler_live.py`

**Interfaces:**
- Consumes: `sampler.compute_deltas` (Task 2), `psycopg2.sql.Identifier` (schema-qualification pattern from P0b's `index_bloat.py`).
- Produces: `sampler.snapshot_pg_stat_statements(conn, schema) -> dict`, `sampler.sample_pg_stat_statements_window(conn, schema, window_seconds, *, sleep_fn=time.sleep) -> dict` — consumed by Task 6's `analyzer.py`.

- [ ] **Step 1: Enable `pg_stat_statements` tracking in the test container**

`pg_stat_statements` needs `shared_preload_libraries` set **before** the server starts — unlike `pgstattuple` (function-only), `CREATE EXTENSION` alone installs the SQL objects but the module's stat-tracking hooks stay inactive without this. Modify `SKILL_DIR/tests/pgcontainer.py`'s `__enter__`:

```python
    def __enter__(self):
        self.port = _free_port()
        self.name = f"dbrep-test-{self.port}"
        try:
            subprocess.run(
                ["docker", "run", "-d", "--rm", "--name", self.name,
                 "-e", "POSTGRES_PASSWORD=postgres",
                 "-p", f"{self.port}:5432", self.image,
                 "-c", "shared_preload_libraries=pg_stat_statements"],
                check=True, capture_output=True,
            )
            self._wait_ready()
        except Exception:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
            raise
        return self
```

(Only the `docker run` argument list changes — appends `-c shared_preload_libraries=pg_stat_statements` after the image name, which the official `postgres` image passes through as server options. Backward compatible: preloading the module has no effect on any other test's behavior.)

- [ ] **Step 2: Write the failing test**

Create `SKILL_DIR/tests/unit/test_sampler_live.py`:

```python
import psycopg2
import pytest

from scripts.sampler import sample_pg_stat_statements_window, snapshot_pg_stat_statements
from tests.pgcontainer import docker_available

SCHEMA = "public"


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_snapshot_shape(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        snap = snapshot_pg_stat_statements(conn, SCHEMA)
    finally:
        conn.close()
    assert set(snap) == {"stats_reset", "postmaster_start", "rows"}
    assert isinstance(snap["rows"], dict)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_window_reflects_only_activity_during_the_window(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            cur.execute("SELECT pg_stat_statements_reset()")
            for _ in range(3):
                cur.execute("SELECT 918273645 /* sampler_marker */")  # before the window

        def run_during_window(_seconds):
            with conn.cursor() as cur:
                for _ in range(4):
                    cur.execute("SELECT 918273645 /* sampler_marker */")

        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=run_during_window)
    finally:
        conn.close()
    assert result["reset_detected"] is False
    match = [d for d in result["deltas"] if "918273645" in d["query"]]
    assert len(match) == 1
    assert match[0]["window_calls"] == 4


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_reset_mid_window_is_detected_and_invalidates_the_window(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

        def reset_during_window(_seconds):
            with conn.cursor() as cur:
                cur.execute("SELECT pg_stat_statements_reset()")

        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=reset_during_window)
    finally:
        conn.close()
    assert result["reset_detected"] is True
    assert result["deltas"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_sample_records_window_seconds_and_both_timestamps(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        result = sample_pg_stat_statements_window(
            conn, SCHEMA, window_seconds=0, sleep_fn=lambda _s: None)
    finally:
        conn.close()
    assert result["window_seconds"] == 0
    assert result["sample1_at"] and result["sample2_at"]
    assert result["sample1_at"] <= result["sample2_at"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_each_snapshot_leaves_no_open_transaction(pg_dsn):
    # Roadmap gate "cung-txn -> phat hien" (same-transaction -> detected):
    # lib.db.connect() uses autocommit=True, so every snapshot statement is
    # its own transaction by construction. Prove it directly here rather
    # than only by code inspection: psycopg2 reports TRANSACTION_STATUS_IDLE
    # immediately after each snapshot call, so nothing carries a snapshot
    # across the two samples the way a shared open transaction would.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        snapshot_pg_stat_statements(conn, SCHEMA)
        assert conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
        snapshot_pg_stat_statements(conn, SCHEMA)
        assert conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_qualifies_with_extension_schema_not_search_path(pg_dsn):
    # Same proof as index_bloat's schema-qualification test (P0b): a bogus
    # schema must make the call fail rather than silently falling back to
    # search_path.
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        with pytest.raises(psycopg2.Error):
            snapshot_pg_stat_statements(conn, "no_such_schema")
    finally:
        conn.close()
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/unit/test_sampler_live.py -q`
Expected: FAIL — `NotImplementedError` from the Task 2 placeholders (skips cleanly with "docker not available" if Docker isn't installed; if it fails instead of skipping, Docker is available and the failure must be `NotImplementedError`).

- [ ] **Step 4: Implement the live functions**

In `SKILL_DIR/scripts/sampler.py`, replace the two placeholder functions at the bottom of the file:

```python
def snapshot_pg_stat_statements(conn, schema: str) -> dict:
    """One point-in-time snapshot of pg_stat_statements + its reset marker +
    the server start time (spec §0.A2 restart detection). Each call is its
    own read-only autocommit statement — i.e. its own transaction, since
    lib.db.connect() already runs autocommit=True — which satisfies the
    "separate transactions" requirement of the two-sample protocol without
    needing an explicit pg_stat_clear_snapshot() call.
    """
    pgss = sql.Identifier(schema, "pg_stat_statements")
    info = sql.Identifier(schema, "pg_stat_statements_info")
    with conn.cursor() as cur:
        cur.execute(sql.SQL(_SNAPSHOT_SQL).format(pgss=pgss))
        rows = {}
        for (queryid, query, calls, total_exec_time, row_count, mean_exec_time,
             stddev_exec_time, shared_blks_read, temp_blks_read,
             temp_blks_written) in cur.fetchall():
            rows[queryid] = {
                "query": query, "calls": calls, "total_exec_time": total_exec_time,
                "rows": row_count, "mean_exec_time": mean_exec_time,
                "stddev_exec_time": stddev_exec_time,
                "shared_blks_read": shared_blks_read,
                "temp_blks_read": temp_blks_read,
                "temp_blks_written": temp_blks_written,
            }
        cur.execute(sql.SQL(_INFO_SQL).format(info=info))
        stats_reset = cur.fetchone()[0]
        cur.execute("SELECT pg_postmaster_start_time()")
        postmaster_start = cur.fetchone()[0]
    return {"stats_reset": stats_reset, "postmaster_start": postmaster_start, "rows": rows}


def sample_pg_stat_statements_window(conn, schema: str, window_seconds: int,
                                      *, sleep_fn=time.sleep) -> dict:
    """Take two snapshots `window_seconds` apart and reduce them to windowed
    deltas (spec §6 P1.1). `sleep_fn` is injectable so tests can run activity
    mid-window instead of literally sleeping.
    """
    sample1_at = datetime.now(timezone.utc).isoformat()
    snap1 = snapshot_pg_stat_statements(conn, schema)
    sleep_fn(window_seconds)
    sample2_at = datetime.now(timezone.utc).isoformat()
    snap2 = snapshot_pg_stat_statements(conn, schema)
    result = compute_deltas(snap1, snap2)
    return {
        "window_seconds": window_seconds,
        "sample1_at": sample1_at,
        "sample2_at": sample2_at,
        "reset_detected": result["reset_detected"],
        "deltas": result["deltas"],
    }
```

Remove the two `raise NotImplementedError` placeholder bodies — this step replaces them entirely.

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_sampler_live.py tests/unit/test_sampler_math.py -q`
Expected: PASS (6 live tests + 11 math tests), or all 6 live tests SKIPPED if Docker isn't available in this environment.

- [ ] **Step 6: Commit**

```bash
git add scripts/sampler.py tests/pgcontainer.py tests/unit/test_sampler_live.py
git commit -m "feat(p1): sampler live snapshot/window capture, schema-qualified (P1.1)"
```

---

### Task 4: `run_collectors` sampling passthrough

**Files:**
- Modify: `SKILL_DIR/scripts/collectors/__init__.py`
- Modify: `SKILL_DIR/tests/unit/test_collectors_framework.py`

**Interfaces:**
- Consumes: existing `run_collectors(conn, caps, registry=None)` (P0b).
- Produces: `run_collectors(conn, caps, registry=None, *, sampling=None)` — merges `sampling` into a **copy** of `caps` as `caps["sampling"]` before calling each collector — consumed by Task 5's `query_stats.collect()` and Task 6's `analyzer.py`.

- [ ] **Step 1: Write the failing test**

Append to `SKILL_DIR/tests/unit/test_collectors_framework.py`:

```python
def test_run_collectors_merges_sampling_into_caps_for_every_collector():
    seen = {}

    def spy(conn, caps):
        seen["sampling"] = caps.get("sampling")
        return base.diagnostic("query", "ok", [])

    run_collectors(conn=None, caps={"server_version_num": 1}, registry={"spy": spy},
                    sampling={"window_seconds": 30, "deltas": []})
    assert seen["sampling"] == {"window_seconds": 30, "deltas": []}


def test_run_collectors_sampling_defaults_to_none():
    seen = {}

    def spy(conn, caps):
        seen["sampling"] = caps.get("sampling")
        return base.diagnostic("query", "ok", [])

    run_collectors(conn=None, caps={}, registry={"spy": spy})
    assert seen["sampling"] is None


def test_run_collectors_does_not_mutate_the_caller_caps_dict():
    # target["capabilities"] must never carry the raw sampling payload —
    # only caps passed into each collector should see it.
    caller_caps = {"server_version_num": 1}
    run_collectors(conn=None, caps=caller_caps, registry={},
                    sampling={"window_seconds": 30, "deltas": []})
    assert "sampling" not in caller_caps
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_collectors_framework.py -q`
Expected: FAIL — `TypeError: run_collectors() got an unexpected keyword argument 'sampling'`.

- [ ] **Step 3: Implement the passthrough**

In `SKILL_DIR/scripts/collectors/__init__.py`, replace `run_collectors`:

```python
def run_collectors(conn, caps, registry=None, *, sampling=None):
    """Run every collector with per-collector isolation.

    A collector that raises is recorded as an ``error`` diagnostic (reason =
    the exception class name — never the message, to avoid leaking identifiers)
    and does not abort the others. ``sampling`` (the per-target windowed
    pg_stat_statements deltas, or None) is merged into a *copy* of ``caps``
    so the caller's own ``caps``/``target["capabilities"]`` dict is never
    mutated and never carries the raw sampling payload.
    """
    reg = registry if registry is not None else COLLECTORS
    merged_caps = {**caps, "sampling": sampling}
    out = {}
    for name, fn in reg.items():
        try:
            out[name] = fn(conn, merged_caps)
        except Exception as exc:  # noqa: BLE001 - isolate per-collector failure
            out[name] = base.diagnostic(
                "table", "error", [], reason=type(exc).__name__)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_collectors_framework.py -q`
Expected: PASS (all tests in the file, including the 3 new ones).

- [ ] **Step 5: Run the full existing collector test suite to confirm no regression**

Run: `python -m pytest tests/unit/test_fk_missing_index.py tests/unit/test_duplicate_index.py tests/unit/test_index_bloat.py tests/unit/test_dead_tuples.py tests/unit/test_table_index_size.py -q`
Expected: PASS — the 5 existing P0b collectors ignore the new `caps["sampling"]` key, unaffected.

- [ ] **Step 6: Commit**

```bash
git add scripts/collectors/__init__.py tests/unit/test_collectors_framework.py
git commit -m "feat(p1): run_collectors sampling passthrough, non-mutating (P1.1 wiring)"
```

---

### Task 5: `query_stats.py` collector (P1.2)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/query_stats.py`
- Modify: `SKILL_DIR/scripts/collectors/__init__.py`
- Create: `SKILL_DIR/tests/unit/test_query_stats.py`

**Interfaces:**
- Consumes: `caps["extensions"]["pg_stat_statements"]` (capabilities.py, P0a), `caps["sampling"]` (Task 4's `run_collectors`) — shape `{"reset_detected": bool, "deltas": [...]}` as produced by `sampler.compute_deltas` (Task 2/3).
- Produces: `query_stats.collect(conn, caps) -> dict`, `query_stats.MINIMUM_ACTIVITY_CALLS: int` — registered into `collectors.COLLECTORS["query_stats"]`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_query_stats.py`:

```python
from scripts.collectors.query_stats import collect


def test_skips_when_extension_absent():
    diag = collect(conn=None, caps={"extensions": {}})
    assert diag["status"] == "skipped"
    assert "pg_stat_statements" in diag["reason"]
    assert diag["metrics"] == []


def test_skips_when_no_sampling_was_performed():
    caps = {"extensions": {"pg_stat_statements": {"present": True, "schema": "public"}}}
    diag = collect(conn=None, caps=caps)
    assert diag["status"] == "skipped"
    assert diag["metrics"] == []


def test_reset_detected_marks_quality_invalid_and_empties_metrics():
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": True, "deltas": [], "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["status"] == "ok"
    assert diag["quality"]["sampling_valid"] is False
    assert diag["quality"]["reset_detected"] is True
    assert diag["metrics"] == []


def test_zero_workload_marks_insufficient_activity():
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": False, "deltas": [], "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["quality"]["sampling_valid"] is True
    assert diag["quality"]["insufficient_activity"] is True
    assert diag["metrics"] == []


def _delta(queryid, calls, total_ms):
    return {"queryid": queryid, "query": f"select {queryid}", "window_calls": calls,
            "window_total_exec_time_ms": total_ms, "window_mean_exec_time_ms": total_ms / calls,
            "window_stddev_exec_time_ms": 0.5, "window_rows_per_call": 1.0,
            "window_shared_blks_read": 0, "window_temp_blks_read": 0, "window_temp_blks_written": 0}


def test_active_window_reports_metrics_sorted_by_total_time_not_calls():
    deltas = [
        _delta("1", calls=3, total_ms=300.0),    # low calls, high total time
        _delta("2", calls=50, total_ms=50.0),    # high calls, low total time
    ]
    caps = {
        "extensions": {"pg_stat_statements": {"present": True, "schema": "public"}},
        "sampling": {"reset_detected": False, "deltas": deltas, "window_seconds": 30,
                     "sample1_at": "t1", "sample2_at": "t2"},
    }
    diag = collect(conn=None, caps=caps)
    assert diag["quality"]["insufficient_activity"] is False
    assert [m["queryid"] for m in diag["metrics"]] == ["1", "2"]
    m = diag["metrics"][0]
    assert set(m) == {"queryid", "query", "window_calls", "window_total_exec_time_ms",
                       "window_mean_exec_time_ms", "window_stddev_exec_time_ms",
                       "window_rows_per_call", "window_shared_blks_read",
                       "window_temp_blks_read", "window_temp_blks_written"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_query_stats.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'scripts.collectors.query_stats'`).

- [ ] **Step 3: Write the minimal implementation**

Create `SKILL_DIR/scripts/collectors/query_stats.py`:

```python
"""P1.2 — pg_stat_statements 3-axis windowed query stats (spec §6 P1.2).

Pure transformer: reads the per-target deltas the sampler (P1.1) already
computed out of ``caps["sampling"]`` and reduces them to schema-valid
metrics. Default top-sort is total_exec_time descending (already the
sampler's own sort order — this collector does not re-sort), replacing the
old v3 default of sorting by mean.
"""
from scripts.collectors import base

MINIMUM_ACTIVITY_CALLS = 5  # below this total window calls, deltas are too thin to judge


def collect(conn, caps):
    ext = (caps.get("extensions") or {}).get("pg_stat_statements")
    if not ext:
        return base.skipped(
            "query", "query_stats requires the pg_stat_statements extension (not installed)")
    sampling = caps.get("sampling")
    if sampling is None:
        return base.skipped(
            "query", "no sampling window was collected for this target")

    quality = dict(base.STRUCTURAL_QUALITY)
    if sampling["reset_detected"]:
        quality["sampling_valid"] = False
        quality["reset_detected"] = True
        return base.diagnostic("query", "ok", [], quality=quality)

    deltas = sampling["deltas"]
    total_window_calls = sum(d["window_calls"] for d in deltas)
    if total_window_calls < MINIMUM_ACTIVITY_CALLS:
        quality["insufficient_activity"] = True

    metrics = [
        {
            "queryid": d["queryid"],
            "query": d["query"],
            "window_calls": d["window_calls"],
            "window_total_exec_time_ms": d["window_total_exec_time_ms"],
            "window_mean_exec_time_ms": d["window_mean_exec_time_ms"],
            "window_stddev_exec_time_ms": d["window_stddev_exec_time_ms"],
            "window_rows_per_call": d["window_rows_per_call"],
            "window_shared_blks_read": d["window_shared_blks_read"],
            "window_temp_blks_read": d["window_temp_blks_read"],
            "window_temp_blks_written": d["window_temp_blks_written"],
        }
        for d in deltas
    ]
    return base.diagnostic("query", "ok", metrics, quality=quality)
```

Register it in `SKILL_DIR/scripts/collectors/__init__.py` (append after the existing 5 registrations):

```python
from scripts.collectors import query_stats

COLLECTORS["query_stats"] = query_stats.collect
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_query_stats.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the framework tests to confirm registration didn't break isolation**

Run: `python -m pytest tests/unit/test_collectors_framework.py tests/unit/test_analyzer.py -q`
Expected: PASS (the new registry entry runs through the same `run_collectors` isolation path; existing analyzer tests are schema-valid regardless of the extra diagnostic block since `diagnostics` is `additionalProperties: {"$ref": "#/$defs/diagnostic"}`, an open map).

- [ ] **Step 6: Commit**

```bash
git add scripts/collectors/query_stats.py scripts/collectors/__init__.py tests/unit/test_query_stats.py
git commit -m "feat(p1): query_stats collector — 3-axis windowed pg_stat_statements (P1.2)"
```

---

### Task 6: `envparse.py` + `analyzer.py` sampler integration

**Files:**
- Modify: `SKILL_DIR/scripts/lib/envparse.py`
- Modify: `SKILL_DIR/scripts/analyzer.py`
- Modify: `SKILL_DIR/tests/unit/test_envparse.py`
- Modify: `SKILL_DIR/tests/unit/test_analyzer.py`

**Interfaces:**
- Consumes: `sampler.sample_pg_stat_statements_window` (Task 3), `collectors.run_collectors(..., sampling=...)` (Task 4).
- Produces: `DbConfig.sampling_window_seconds: int = 30`; `_analyze_target(cfg)` sets `target["sampling"]` to `None` or `{"window_seconds", "sample1_at", "sample2_at", "reset_detected"}` and calls `run_collectors(conn, caps, sampling=<full sampler result>)` — consumed by Task 7's concurrency change (which reads `target["sampling"]["window_seconds"]` for the latency budget).

- [ ] **Step 1: Write the failing test — envparse**

Append to `SKILL_DIR/tests/unit/test_envparse.py`:

```python
def test_sampling_window_seconds_defaults_to_30():
    assert parse_env(json.dumps(SAMPLE)).sampling_window_seconds == 30


def test_sampling_window_seconds_reads_custom_value():
    data = {**SAMPLE, "SamplingWindowSeconds": 45}
    assert parse_env(json.dumps(data)).sampling_window_seconds == 45
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_envparse.py -q`
Expected: FAIL — `AttributeError: 'DbConfig' object has no attribute 'sampling_window_seconds'`.

- [ ] **Step 3: Add the field to `DbConfig`/`parse_env`**

In `SKILL_DIR/scripts/lib/envparse.py`:

```python
@dataclass
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    project_name: str = ""
    code_path: str = ""
    sampling_window_seconds: int = 30
    raw: dict = field(default_factory=dict)
```

And in `parse_env`, add the new kwarg to the returned `DbConfig(...)` call (after `code_path=...`):

```python
        code_path=str(data.get("CodePath", "")),
        sampling_window_seconds=int(data.get("SamplingWindowSeconds", 30)),
        raw=data,
```

- [ ] **Step 4: Run to verify envparse tests pass**

Run: `python -m pytest tests/unit/test_envparse.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing test — analyzer wiring**

In `SKILL_DIR/tests/unit/test_analyzer.py`, add two imports at the top of the file (after the existing `import pytest`):

```python
import dataclasses

import psycopg2
```

Then append to the file:

```python
def test_analyze_target_sampling_is_none_when_pg_stat_statements_absent(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn)])
    target = report["targets"][0]
    assert target["sampling"] is None


def test_analyze_populates_sampling_metadata_when_pg_stat_statements_present(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    finally:
        conn.close()
    cfg = dataclasses.replace(_good(pg_dsn), sampling_window_seconds=0)
    report = analyze([cfg])
    target = report["targets"][0]
    assert target["sampling"] is not None
    assert target["sampling"]["window_seconds"] == 0
    assert target["sampling"]["reset_detected"] is False
    assert target["diagnostics"]["query_stats"]["status"] == "ok"
```

- [ ] **Step 6: Run to verify it fails**

Run: `python -m pytest tests/unit/test_analyzer.py -q`
Expected: FAIL — `KeyError: 'sampling'` (the target dict doesn't have that key yet).

- [ ] **Step 7: Wire the sampler into `_analyze_target`**

In `SKILL_DIR/scripts/analyzer.py`, add the import (with the existing `from scripts import capabilities, collectors` line):

```python
from scripts import capabilities, collectors, sampler
```

Replace `_analyze_target`:

```python
def _analyze_target(cfg: DbConfig) -> dict:
    target = {
        "target_id": cfg.project_name or cfg.database,
        "database": cfg.database,
        "collection_status": "ok",
        "error": None,
        "capabilities": {},
        "diagnostics": {},
        "sampling": None,
    }
    try:
        conn = db.connect(cfg)
        try:
            target["capabilities"] = capabilities.probe(conn)
            pgss = target["capabilities"].get("extensions", {}).get("pg_stat_statements")
            sampling_result = None
            if pgss:
                sampling_result = sampler.sample_pg_stat_statements_window(
                    conn, pgss["schema"], cfg.sampling_window_seconds)
                target["sampling"] = {
                    "window_seconds": sampling_result["window_seconds"],
                    "sample1_at": sampling_result["sample1_at"],
                    "sample2_at": sampling_result["sample2_at"],
                    "reset_detected": sampling_result["reset_detected"],
                }
            target["diagnostics"] = collectors.run_collectors(
                conn, target["capabilities"], sampling=sampling_result)
            target["collection_status"] = _collection_status(target["diagnostics"])
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - isolate per-target failure
        target["collection_status"] = "error"
        target["error"] = _scrub(str(exc), cfg)
    return target
```

Note: `target["sampling"]` (the schema-tracked summary) never includes the raw `deltas` list — only `collectors.run_collectors`'s `sampling` kwarg (the full `sampling_result`, including `deltas`) carries that, and it only reaches `query_stats.collect()` via `caps["sampling"]`, never the persisted `target["sampling"]` field.

- [ ] **Step 8: Run to verify it passes**

Run: `python -m pytest tests/unit/test_analyzer.py -q`
Expected: PASS (all tests in the file, including the 2 new ones).

- [ ] **Step 9: Run the full suite to confirm no regression**

Run: `python -m pytest tests/unit -q`
Expected: PASS, all tests green (or Docker-dependent ones cleanly skipped).

- [ ] **Step 10: Commit**

```bash
git add scripts/lib/envparse.py scripts/analyzer.py tests/unit/test_envparse.py tests/unit/test_analyzer.py
git commit -m "feat(p1): wire sampler into analyzer — target.sampling + SamplingWindowSeconds config (P1.1)"
```

---

### Task 7: Bounded multi-target concurrency + latency-budget warning (B4)

**Files:**
- Modify: `SKILL_DIR/scripts/analyzer.py`
- Modify: `SKILL_DIR/tests/unit/test_analyzer.py`

**Interfaces:**
- Consumes: `target["sampling"]["window_seconds"]` (Task 6).
- Produces: `analyzer._check_latency_budget(targets: list, elapsed_seconds: float) -> None` (emits `RuntimeWarning` when the budget looks blown); `analyzer.analyze()` now runs targets through a bounded `ThreadPoolExecutor` when `len(configs) > 1`.

- [ ] **Step 1: Write the failing test — latency budget (pure, no DB)**

In `SKILL_DIR/tests/unit/test_analyzer.py`, add one import at the top of the file (after `import pytest`):

```python
import warnings
```

Then append to the file:

```python
from scripts.analyzer import _check_latency_budget


def _sampled_target(window_seconds):
    return {"sampling": {"window_seconds": window_seconds}}


def test_latency_budget_warns_when_elapsed_close_to_serial_sum():
    targets = [_sampled_target(30), _sampled_target(30), _sampled_target(30)]  # sum = 90s
    with pytest.warns(RuntimeWarning, match="not bounded"):
        _check_latency_budget(targets, elapsed_seconds=85.0)


def test_latency_budget_silent_when_elapsed_reflects_bounded_parallelism():
    targets = [_sampled_target(30), _sampled_target(30), _sampled_target(30)]  # sum = 90s
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget(targets, elapsed_seconds=32.0)  # ran in ~1 window, not 3 -> no raise


def test_latency_budget_silent_for_a_single_target():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget([_sampled_target(30)], elapsed_seconds=30.0)


def test_latency_budget_silent_when_no_sampling_was_performed():
    targets = [{"sampling": None}, {"sampling": None}]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget(targets, elapsed_seconds=100.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_analyzer.py -q -k latency_budget`
Expected: FAIL (`ImportError: cannot import name '_check_latency_budget'`).

- [ ] **Step 3: Write the failing test — bounded concurrency (pure, monkeypatched, no DB)**

Append to `SKILL_DIR/tests/unit/test_analyzer.py`:

```python
def test_analyze_runs_multiple_targets_concurrently(monkeypatch):
    import time as time_module

    from scripts import analyzer

    def fake_analyze_target(cfg):
        time_module.sleep(0.2)
        return {"target_id": cfg.project_name, "database": cfg.database,
                "collection_status": "ok", "error": None, "capabilities": {},
                "diagnostics": {}, "sampling": None}

    monkeypatch.setattr(analyzer, "_analyze_target", fake_analyze_target)
    configs = [DbConfig(host="h", port=1, database=f"d{i}", user="u", password="p",
                        project_name=f"p{i}") for i in range(4)]
    t0 = time_module.monotonic()
    report = analyzer.analyze(configs)
    elapsed = time_module.monotonic() - t0
    assert len(report["targets"]) == 4
    assert {t["target_id"] for t in report["targets"]} == {"p0", "p1", "p2", "p3"}
    # 4 targets x 0.2s would be 0.8s fully serial; bounded-parallel keeps it near 0.2s.
    assert elapsed < 0.6
```

- [ ] **Step 4: Run to verify it fails**

Run: `python -m pytest tests/unit/test_analyzer.py -q -k concurrently`
Expected: FAIL — either an `AssertionError` on `elapsed < 0.6` (current code runs the list comprehension serially, ~0.8s) or a validation error from `schema.validate_report` (fake targets omit `"sampling"`, which is fine since Task 1 made it optional — this should not fail on schema; if it does, double check Task 1 was applied).

- [ ] **Step 5: Implement bounded concurrency + the latency check**

In `SKILL_DIR/scripts/analyzer.py`, add imports (with the existing `import re` / `import uuid` block):

```python
import concurrent.futures
import time
import warnings
```

Add the two new module-level pieces (after `TOOL_VERSION = "4.0.0"`):

```python
_MAX_WORKERS = 8
_LATENCY_WARNING_RATIO = 0.8  # elapsed > 80% of the fully-serial sum -> parallelism isn't bounding runtime


def _check_latency_budget(targets: list, elapsed_seconds: float) -> None:
    """Spec §0.B4: warn if multi-target sampling isn't actually bounded —
    i.e. total elapsed time is suspiciously close to what a fully serial
    N x window_seconds run would take.
    """
    total_window = sum((t.get("sampling") or {}).get("window_seconds", 0) for t in targets)
    if len(targets) > 1 and total_window > 0 and elapsed_seconds > total_window * _LATENCY_WARNING_RATIO:
        warnings.warn(
            f"multi-target sampling took {elapsed_seconds:.1f}s for {len(targets)} targets "
            f"(sum of window_seconds={total_window}s) — runtime is not bounded, check concurrency",
            RuntimeWarning,
        )
```

Replace `analyze`:

```python
def analyze(configs, *, redaction_mode: str = "redact") -> dict:
    started = _now()
    t0 = time.monotonic()
    if len(configs) <= 1:
        targets = [_analyze_target(cfg) for cfg in configs]
    else:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(_MAX_WORKERS, len(configs))) as pool:
            targets = list(pool.map(_analyze_target, configs))
    _check_latency_budget(targets, time.monotonic() - t0)
    report = {
        "schema_version": "4.0",
        "tool_version": TOOL_VERSION,
        "run": {"run_id": str(uuid.uuid4()), "started_at": started, "completed_at": _now()},
        "redaction_mode": redaction_mode,
        "targets": targets,
    }
    schema.validate_report(report)
    return report
```

(`pool.map` preserves input order, so `targets` stays in the same order as `configs`, matching the previous sequential behavior — each target already uses its own independent `psycopg2` connection via `db.connect(cfg)` inside `_analyze_target`, so running them on separate threads is safe.)

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/unit/test_analyzer.py -q`
Expected: PASS (all tests in the file, including all new ones from Tasks 6 and 7).

- [ ] **Step 7: Run the full suite to confirm no regression**

Run: `python -m pytest tests/unit -q`
Expected: PASS, all tests green (Docker-dependent tests skip cleanly if Docker isn't available).

- [ ] **Step 8: Commit**

```bash
git add scripts/analyzer.py tests/unit/test_analyzer.py
git commit -m "feat(p1): bounded multi-target concurrency + latency-budget warning (B4)"
```

---

## Post-plan verification

After Task 7, run the complete suite once more and confirm the final tally includes every new test file:

```bash
python -m pytest tests/unit -q
```

Expected: all green (Docker-gated tests skip cleanly without Docker, run and pass with it). This closes P1's roadmap gate: reset-between-samples → invalidated; same-transaction sampling structurally guaranteed by the read-only autocommit connection; per-queryid eviction invalidates only that entry; zero-workload → `insufficient_activity`; formulas tested against the forbidden-subtraction regression guards; multi-target runtime proven bounded.

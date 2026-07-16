# Phase 0b — Blocker-fix Collectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the five broken v3 diagnostic queries (P0.1–P0.5) into correct, versioned, schema-valid Python **collectors** that populate `report_data.json`'s per-target `diagnostics{}`.

**Architecture:** A `scripts/collectors/` package. Each collector is a module exposing `collect(conn, caps) -> dict` returning one schema-valid `diagnostic` object (see `$defs/diagnostic` in `references/report-data.schema.json`). A registry (`COLLECTORS`) + `run_collectors(conn, caps)` runs them with per-collector isolation. `analyzer.py` calls `run_collectors` to fill each target's `diagnostics`. Collectors are **read-only** and **metrics-only**: they emit corrected `metrics[]`; `findings[]` stays `[]` (the rule engine that turns metrics→findings is Phase 3).

**Tech Stack:** Python ≥3.10, psycopg2, pytest (+ Docker `postgres:16` fixture, skips without Docker), jsonschema (via existing `scripts.lib.schema`).

## Global Constraints

- **Read-only / no side effects:** collectors issue only `SELECT`/catalog reads. Never DDL/DML. (The connection is already server-enforced read-only.)
- **Metrics-only this phase:** every collector returns `findings: []`. Thresholds/severity/assessment are Phase 3. The blocker theme here is *correct collection*, not judgement.
- **Schema-valid:** every `diagnostic` validates against `$defs/diagnostic`: required `collector_version` (str), `scope` (cluster|database|table|index|query), `status` (ok|partial|skipped|error), `quality` (the 4 booleans), `metrics` (array), `findings` (array). Optional `reason` (str|null).
- **Version/capability adaptation:** a collector that needs a newer PG or a missing extension returns `status="skipped"` with a human `reason`, never an error, never a fake-empty "ok". `skipped` ≠ green.
- **Isolation:** one collector raising must not kill the target or the run; `run_collectors` records that collector as `status="error"` and continues. If any collector errored, the target's `collection_status` becomes `"partial"`.
- **Determinism:** stable `ORDER BY` in SQL and stable sort in Python; no timestamps/random in metric bodies.
- **Reports in Vietnamese** downstream; keep English for table/column/SQL identifiers.

## Interfaces (shared across tasks)

- `scripts.capabilities.probe(conn) -> dict` (exists) — `caps` with keys `server_version_num` (int), `extensions` (dict name→{present,schema}), etc.
- Collector contract (**Produced by Task 1, consumed by Tasks 2–6**):
  - `scripts.collectors.base.STRUCTURAL_QUALITY: dict` — `{"sampling_valid": True, "reset_detected": False, "insufficient_activity": False, "truncated": False}`.
  - `scripts.collectors.base.diagnostic(scope, status, metrics, *, reason=None, quality=STRUCTURAL_QUALITY, collector_version="1") -> dict`.
  - `scripts.collectors.base.skipped(scope, reason, *, collector_version="1") -> dict` — status skipped, metrics [].
  - `scripts.collectors.run_collectors(conn, caps, registry=None) -> dict[str, dict]` — name→diagnostic, per-collector isolated.
  - `scripts.collectors.COLLECTORS: dict[str, callable]` — the live registry (each task appends one entry).
- Each collector module: `collect(conn, caps) -> dict` (a diagnostic).

---

## File Structure

```
scripts/collectors/
  __init__.py            # COLLECTORS registry + run_collectors()
  base.py                # diagnostic()/skipped() builders + STRUCTURAL_QUALITY
  fk_missing_index.py    # P0.2
  duplicate_index.py     # P0.3
  index_bloat.py         # P0.1 (pgstattuple-preferred; skip if absent)
  dead_tuples.py         # P0.4
  table_index_size.py    # P0.5
scripts/analyzer.py      # MODIFY: call run_collectors, derive partial status
tests/unit/
  _fixtures_sql.py       # helper: make a uniquely-named schema, drop on exit
  test_collectors_framework.py
  test_fk_missing_index.py
  test_duplicate_index.py
  test_index_bloat.py
  test_dead_tuples.py
  test_table_index_size.py
```

---

### Task 1: Collector framework + analyzer integration

**Files:**
- Create: `SKILL_DIR/scripts/collectors/__init__.py`
- Create: `SKILL_DIR/scripts/collectors/base.py`
- Modify: `SKILL_DIR/scripts/analyzer.py`
- Create: `SKILL_DIR/tests/unit/test_collectors_framework.py`

**Interfaces:**
- Consumes: `scripts.lib.schema.validate_report` (P−1), the frozen `$defs/diagnostic`.
- Produces: `base.STRUCTURAL_QUALITY`, `base.diagnostic(...)`, `base.skipped(...)`, `collectors.run_collectors(conn, caps, registry=None)`, `collectors.COLLECTORS` (empty this task), and analyzer wiring that puts diagnostics on each target and sets `collection_status="partial"` when a collector errored.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_collectors_framework.py`:
```python
from scripts.collectors import base, run_collectors
from scripts.analyzer import _collection_status
from scripts.lib.schema import validate_report


def _wrap(diag):
    # Minimal schema-valid report carrying one diagnostic, to prove diag shape.
    return {
        "schema_version": "4.0", "tool_version": "4.0.0",
        "run": {"run_id": "x", "started_at": "t", "completed_at": "t"},
        "redaction_mode": "redact",
        "targets": [{
            "target_id": "t", "database": "d", "collection_status": "ok",
            "error": None, "capabilities": {}, "diagnostics": {"demo": diag},
        }],
    }


def test_diagnostic_and_skipped_are_schema_valid():
    ok = base.diagnostic("table", "ok", [{"a": 1}])
    validate_report(_wrap(ok))            # must not raise
    sk = base.skipped("table", "needs pgstattuple")
    assert sk["status"] == "skipped" and sk["metrics"] == [] and sk["reason"]
    validate_report(_wrap(sk))


def test_run_collectors_isolates_a_raising_collector():
    def good(conn, caps):
        return base.diagnostic("index", "ok", [{"n": 1}])

    def boom(conn, caps):
        raise RuntimeError("kaboom")

    out = run_collectors(conn=None, caps={}, registry={"good": good, "bad": boom})
    assert out["good"]["status"] == "ok"
    assert out["bad"]["status"] == "error"
    assert "RuntimeError" in (out["bad"]["reason"] or "")


def test_collection_status_is_partial_when_any_diagnostic_errored():
    ok = {"status": "ok"}
    err = {"status": "error"}
    assert _collection_status({"a": ok}) == "ok"
    assert _collection_status({"a": ok, "b": err}) == "partial"
    assert _collection_status({}) == "ok"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_collectors_framework.py -q`
Expected: FAIL (`ModuleNotFoundError: scripts.collectors`).

- [ ] **Step 3: Write `base.py`**

Create `SKILL_DIR/scripts/collectors/base.py`:
```python
"""Shared builders for schema-valid diagnostic objects (metrics-only in P0b)."""

# Structural collectors read the catalog directly — no delta sampling window —
# so the sampling quality flags are trivially "valid". The B3 invalidation
# invariant only downgrades when sampling_valid is False.
STRUCTURAL_QUALITY = {
    "sampling_valid": True,
    "reset_detected": False,
    "insufficient_activity": False,
    "truncated": False,
}


def diagnostic(scope, status, metrics, *, reason=None,
               quality=None, collector_version="1"):
    return {
        "collector_version": collector_version,
        "scope": scope,
        "status": status,
        "reason": reason,
        "quality": dict(quality or STRUCTURAL_QUALITY),
        "metrics": list(metrics),
        "findings": [],  # rule engine (metrics -> findings) is Phase 3
    }


def skipped(scope, reason, *, collector_version="1"):
    return diagnostic(scope, "skipped", [], reason=reason,
                      collector_version=collector_version)
```

- [ ] **Step 4: Write `__init__.py`**

Create `SKILL_DIR/scripts/collectors/__init__.py`:
```python
"""Collector registry + isolated runner."""
from scripts.collectors import base

# Each collector module appends itself here (name -> collect callable).
COLLECTORS = {}


def run_collectors(conn, caps, registry=None):
    """Run every collector with per-collector isolation.

    A collector that raises is recorded as an ``error`` diagnostic (reason =
    the exception class name — never the message, to avoid leaking identifiers)
    and does not abort the others.
    """
    reg = registry if registry is not None else COLLECTORS
    out = {}
    for name, fn in reg.items():
        try:
            out[name] = fn(conn, caps)
        except Exception as exc:  # noqa: BLE001 - isolate per-collector failure
            out[name] = base.diagnostic(
                "table", "error", [], reason=type(exc).__name__)
    return out
```

- [ ] **Step 5: Wire into `analyzer.py`**

In `SKILL_DIR/scripts/analyzer.py`, add the import and helper, and populate diagnostics in `_analyze_target`.

Add to the imports block:
```python
from scripts import capabilities, collectors
```
(Replace the existing `from scripts import capabilities` line.)

Add this helper near `_scrub`:
```python
def _collection_status(diagnostics: dict) -> str:
    if any(d.get("status") == "error" for d in diagnostics.values()):
        return "partial"
    return "ok"
```

In `_analyze_target`, replace the success block so diagnostics are filled and status derived. The `try` body becomes:
```python
    try:
        conn = db.connect(cfg)
        try:
            target["capabilities"] = capabilities.probe(conn)
            target["diagnostics"] = collectors.run_collectors(conn, target["capabilities"])
            target["collection_status"] = _collection_status(target["diagnostics"])
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - isolate per-target failure
        target["collection_status"] = "error"
        target["error"] = _scrub(str(exc), cfg)
```
(With `COLLECTORS` empty this task, `diagnostics` stays `{}` and status stays `ok` — existing analyzer tests keep passing.)

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/unit/test_collectors_framework.py tests/unit/test_analyzer.py -q`
Expected: PASS (framework tests green; analyzer tests unchanged — still `diagnostics == {}`).

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, no regressions, warnings-as-errors clean.

- [ ] **Step 8: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors .agents/skills/db-report-generator/scripts/analyzer.py .agents/skills/db-report-generator/tests/unit/test_collectors_framework.py
git commit -m "feat(p0b): collector framework + analyzer diagnostics wiring" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Shared test fixture helper

**Files:**
- Create: `SKILL_DIR/tests/unit/_fixtures_sql.py`

**Interfaces:**
- Produces: `make_schema(conn, name, ddl)` context manager — creates a uniquely-named schema, runs `ddl`, yields, `DROP SCHEMA name CASCADE` on exit. Used by Tasks 3–7 collector tests. Requires a read-write connection (tests connect via `psycopg2.connect(**pg_dsn)`, not `db.connect`).

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_fixtures_sql.py`:
```python
import psycopg2
import pytest

from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_make_schema_creates_and_drops(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, "t_fixture_demo", 'CREATE TABLE {s}.a (id int);'):
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM information_schema.tables "
                            "WHERE table_schema='t_fixture_demo' AND table_name='a'")
                assert cur.fetchone() is not None
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name='t_fixture_demo'")
            assert cur.fetchone() is None  # dropped
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_fixtures_sql.py -q`
Expected: FAIL (`ModuleNotFoundError: tests._fixtures_sql`).

- [ ] **Step 3: Write the helper**

Create `SKILL_DIR/tests/unit/_fixtures_sql.py`:
```python
"""Test helper: build a throwaway, uniquely-named schema for collector tests."""
from contextlib import contextmanager


@contextmanager
def make_schema(conn, name, ddl):
    """Create schema ``name``, run ``ddl`` (``{s}`` -> schema name), drop on exit.

    ``conn`` must be a read-write autocommit psycopg2 connection.
    """
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{name}"')
        cur.execute(ddl.format(s=f'"{name}"'))
    try:
        yield name
    finally:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_fixtures_sql.py -q`
Expected: PASS with Docker; skip without.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/tests/unit/_fixtures_sql.py .agents/skills/db-report-generator/tests/unit/test_fixtures_sql.py
git commit -m "test(p0b): schema fixture helper for collector tests" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: FK-missing-index collector (P0.2)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/fk_missing_index.py`
- Create: `SKILL_DIR/tests/unit/test_fk_missing_index.py`

**Interfaces:**
- Consumes: `base`, a live connection. Produces: `collect(conn, caps) -> diagnostic` (scope `table`). Registers as `COLLECTORS["fk_missing_index"]`.
- Each metric row: `{"schema", "table", "constraint", "columns": [str], "suggested_ddl": str}`.

**Detection rule (verified on PG16):** a FK constraint is *missing an index* iff no non-partial, non-expression index on the referencing table has the FK's `conkey` columns as the **leading key-column prefix** (`indkey[1:len(conkey)]`, within `indnkeyatts` key columns). This correctly flags reversed-order and partial-only coverage, and does NOT flag leading-prefix or `INCLUDE`-key coverage.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_fk_missing_index.py`:
```python
import psycopg2
import pytest

from scripts.collectors.fk_missing_index import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}."Parent" (id int PRIMARY KEY);
CREATE TABLE {s}."OrderVehicle" (id int PRIMARY KEY,
    "ParentId" int REFERENCES {s}."Parent"(id));                 -- missing -> flag
CREATE TABLE {s}.covered (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.covered (parent_id, id);                     -- leading prefix -> ok
CREATE TABLE {s}.pa (a int, b int, PRIMARY KEY (a,b));
CREATE TABLE {s}.reversed (a int, b int,
    FOREIGN KEY (a,b) REFERENCES {s}.pa(a,b));
CREATE INDEX ON {s}.reversed (b, a);                             -- reversed -> flag
CREATE TABLE {s}.partial_fk (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.partial_fk (parent_id) WHERE parent_id IS NOT NULL;  -- partial -> flag
CREATE TABLE {s}.include_ok (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.include_ok (parent_id) INCLUDE (id);         -- key prefix -> ok
"""


def _collect_schema(pg_dsn, schema):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, schema, DDL):
            diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    rows = [m for m in diag["metrics"] if m["schema"] == schema]
    return diag, {m["table"] for m in rows}, {m["table"]: m for m in rows}


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_flags_only_the_uncovered_fks(pg_dsn):
    diag, tables, by_table = _collect_schema(pg_dsn, "t_fk_missing")
    assert diag["status"] == "ok"
    assert tables == {"OrderVehicle", "reversed", "partial_fk"}
    assert "covered" not in tables and "include_ok" not in tables


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_suggested_ddl_quotes_pascalcase(pg_dsn):
    _, _, by_table = _collect_schema(pg_dsn, "t_fk_ddl")
    ddl = by_table["OrderVehicle"]["suggested_ddl"]
    assert '"OrderVehicle"' in ddl and '"ParentId"' in ddl
    assert by_table["OrderVehicle"]["columns"] == ["ParentId"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_fk_missing_index.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the collector**

Create `SKILL_DIR/scripts/collectors/fk_missing_index.py`:
```python
"""P0.2 — foreign keys lacking a supporting leading-prefix index."""
from scripts.collectors import base

_SQL = """
SELECT ns.nspname AS schema,
       rel.relname AS tbl,
       con.conname AS constraint_name,
       (SELECT array_agg(a.attname ORDER BY x.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS x(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = x.attnum
       ) AS cols,
       format('CREATE INDEX ON %I.%I (%s);', ns.nspname, rel.relname,
          (SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY x.ord)
             FROM unnest(con.conkey) WITH ORDINALITY AS x(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = x.attnum)
       ) AS suggested_ddl
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE con.contype = 'f'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = con.conrelid
      AND i.indpred IS NULL
      AND i.indexprs IS NULL
      AND i.indnkeyatts >= array_length(con.conkey, 1)
      AND (string_to_array(i.indkey::text, ' ')::int[])[1:array_length(con.conkey, 1)]
          = con.conkey::int[]
  )
ORDER BY schema, tbl, constraint_name
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "constraint": r[2],
         "columns": list(r[3]), "suggested_ddl": r[4]}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `SKILL_DIR/scripts/collectors/__init__.py`, add below the `COLLECTORS = {}` line:
```python
from scripts.collectors import fk_missing_index

COLLECTORS["fk_missing_index"] = fk_missing_index.collect
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_fk_missing_index.py -q`
Expected: PASS with Docker (2 tests). Skip without Docker.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. (The analyzer's Docker tests now see a populated `diagnostics["fk_missing_index"]`; they assert only on the good/bad targets and stay green because the report is still schema-valid.)

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors/fk_missing_index.py .agents/skills/db-report-generator/scripts/collectors/__init__.py .agents/skills/db-report-generator/tests/unit/test_fk_missing_index.py
git commit -m "feat(p0b): FK-missing-index collector w/ prefix match (P0.2)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Duplicate-index collector (P0.3)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/duplicate_index.py`
- Create: `SKILL_DIR/tests/unit/test_duplicate_index.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> diagnostic` (scope `index`). Registers as `COLLECTORS["duplicate_index"]`.
- Metric rows, two kinds:
  - `{"kind": "exact_duplicate", "schema", "table", "keep": str, "drop_candidates": [str], "members": [str]}`
  - `{"kind": "potentially_redundant", "schema", "table", "redundant": str, "covered_by": str}`

**Algorithm:** fetch index descriptors, group in Python.
- **exact_duplicate:** identical signature `(table_oid, amname, indnkeyatts, indkey, indclass, indcollation, indoption, has_expr+pred_text, indnullsnotdistinct)`. `indnullsnotdistinct` only exists on PG15+ — select it only when `server_version_num >= 150000`, else `False`. `keep` = deterministic pick: sort members by `(is_primary desc, is_unique desc, is_exclusion desc, index_name asc)`, keep the first. `drop_candidates` = the rest **excluding** any PK/UNIQUE/exclusion index (never propose dropping a constraint-backing index).
- **potentially_redundant:** for two plain (non-partial, non-expression, non-unique, non-primary) btree indexes on the same table where index A's key columns are a strict **leading prefix** of index B's key columns (same opclass on the shared prefix) → A is redundant, covered by B.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_duplicate_index.py`:
```python
import psycopg2
import pytest

from scripts.collectors.duplicate_index import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.dup (id int PRIMARY KEY, x int, y int, z int);
CREATE INDEX dup_x_1 ON {s}.dup (x);
CREATE INDEX dup_x_2 ON {s}.dup (x);              -- exact duplicate of dup_x_1 (both plain)
CREATE UNIQUE INDEX dup_z_uniq ON {s}.dup (z);    -- unique on z
CREATE INDEX dup_z_plain ON {s}.dup (z);          -- same signature as dup_z_uniq: only the plain one is droppable
CREATE INDEX dup_xy ON {s}.dup (x, y);            -- dup_x_1 (x) is a leading prefix of this
"""


def _run(pg_dsn, schema, version=160000):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, schema, DDL):
            diag = collect(conn, {"server_version_num": version})
    finally:
        conn.close()
    rows = [m for m in diag["metrics"] if m["schema"] == schema]
    return diag, rows


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_exact_duplicate_detected_and_constraints_never_dropped(pg_dsn):
    diag, rows = _run(pg_dsn, "t_dup_exact")
    assert diag["status"] == "ok"
    exact = [r for r in rows if r["kind"] == "exact_duplicate"]
    by_members = {frozenset(r["members"]): r for r in exact}
    # plain x-pair: exactly one drop candidate; keep is deterministic (sorted by name)
    xpair = by_members[frozenset({"dup_x_1", "dup_x_2"})]
    assert len(xpair["drop_candidates"]) == 1
    assert xpair["keep"] == "dup_x_1"
    # unique + plain on z share a signature: the UNIQUE is kept, only the plain
    # is droppable (a constraint-backing index is NEVER a drop candidate).
    zpair = by_members[frozenset({"dup_z_uniq", "dup_z_plain"})]
    assert zpair["keep"] == "dup_z_uniq"
    assert zpair["drop_candidates"] == ["dup_z_plain"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_prefix_redundancy_detected(pg_dsn):
    diag, rows = _run(pg_dsn, "t_dup_prefix")
    red = [r for r in rows if r["kind"] == "potentially_redundant"]
    # dup_x_1 (x) is a leading prefix of dup_xy (x, y)
    assert any(r["redundant"] == "dup_x_1" and r["covered_by"] == "dup_xy" for r in red)
    # a UNIQUE index is never called redundant
    assert all(r["redundant"] != "dup_z_uniq" for r in red)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_duplicate_index.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the collector**

Create `SKILL_DIR/scripts/collectors/duplicate_index.py`:
```python
"""P0.3 — exact-duplicate and prefix-redundant indexes (constraint-safe)."""
from collections import defaultdict

from scripts.collectors import base

# indnullsnotdistinct exists only on PG15+; select conditionally.
_SQL = """
SELECT rel.oid AS table_oid, ns.nspname AS schema, rel.relname AS tbl,
       ic.relname AS index_name, am.amname,
       i.indnkeyatts, i.indkey::text, i.indclass::text, i.indcollation::text,
       i.indoption::text,
       (i.indexprs IS NOT NULL) AS has_expr,
       COALESCE(i.indpred::text, '') AS pred,
       {nnd} AS nnd,
       i.indisprimary, i.indisunique, i.indisexclusion
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class rel ON rel.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
JOIN pg_am am ON am.oid = ic.relam
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
  AND i.indisvalid
ORDER BY schema, tbl, index_name
"""


def _rows(conn, caps):
    nnd = "i.indnullsnotdistinct" if caps.get("server_version_num", 0) >= 150000 else "false"
    with conn.cursor() as cur:
        cur.execute(_SQL.format(nnd=nnd))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _signature(r):
    return (r["table_oid"], r["amname"], r["indnkeyatts"], r["indkey"],
            r["indclass"], r["indcollation"], r["indoption"], r["has_expr"],
            r["pred"], r["nnd"])


def _key_cols(r):
    # leading key columns only (indkey may carry INCLUDE cols beyond indnkeyatts)
    return tuple(r["indkey"].split()[: r["indnkeyatts"]])


def collect(conn, caps):
    rows = _rows(conn, caps)
    metrics = []

    # --- exact duplicates: group by full signature ---
    groups = defaultdict(list)
    for r in rows:
        groups[_signature(r)].append(r)
    for members in groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (
            not r["indisprimary"], not r["indisunique"],
            not r["indisexclusion"], r["index_name"]))
        keep = ordered[0]
        drop_candidates = [m["index_name"] for m in ordered[1:]
                           if not (m["indisprimary"] or m["indisunique"]
                                   or m["indisexclusion"])]
        metrics.append({
            "kind": "exact_duplicate",
            "schema": keep["schema"], "table": keep["tbl"],
            "keep": keep["index_name"],
            "members": sorted(m["index_name"] for m in members),
            "drop_candidates": sorted(drop_candidates),
        })

    # --- prefix redundancy: plain btree, A's key cols strict prefix of B's ---
    plain = [r for r in rows
             if r["amname"] == "btree" and not r["has_expr"] and not r["pred"]
             and not r["indisprimary"] and not r["indisunique"]
             and not r["indisexclusion"]]
    by_table = defaultdict(list)
    for r in plain:
        by_table[r["table_oid"]].append(r)
    for group in by_table.values():
        for a in group:
            ka = _key_cols(a)
            for b in group:
                if a["index_name"] == b["index_name"]:
                    continue
                kb = _key_cols(b)
                if len(ka) < len(kb) and kb[: len(ka)] == ka:
                    metrics.append({
                        "kind": "potentially_redundant",
                        "schema": a["schema"], "table": a["tbl"],
                        "redundant": a["index_name"], "covered_by": b["index_name"],
                    })
                    break

    metrics.sort(key=lambda m: (m["kind"], m["schema"], m["table"],
                                m.get("keep") or m.get("redundant") or ""))
    return base.diagnostic("index", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `SKILL_DIR/scripts/collectors/__init__.py`, add:
```python
from scripts.collectors import duplicate_index

COLLECTORS["duplicate_index"] = duplicate_index.collect
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_duplicate_index.py -q`
Expected: PASS with Docker (2 tests). Skip without.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors/duplicate_index.py .agents/skills/db-report-generator/scripts/collectors/__init__.py .agents/skills/db-report-generator/tests/unit/test_duplicate_index.py
git commit -m "feat(p0b): duplicate/redundant index collector, constraint-safe (P0.3)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Index-bloat collector (P0.1)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/index_bloat.py`
- Create: `SKILL_DIR/tests/unit/test_index_bloat.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> diagnostic` (scope `table`). Registers as `COLLECTORS["index_bloat"]`.
- **Design decision (see plan-review note):** the v3 estimator referenced `relhasoids` (removed PG12+, would error on PG14–18) and is notoriously inaccurate. This collector **prefers `pgstattuple`**: when the extension is present it reports real per-table bloat via `pgstattuple_approx`; when absent it returns `status="skipped"` with an actionable reason (no fragile page-estimate, no `relhasoids`). This satisfies P0.1's acceptance ("runs without error on PG14–18") honestly.
- Metric row: `{"schema", "table", "table_len", "dead_tuple_percent": float, "approx_free_percent": float}`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_index_bloat.py`:
```python
import psycopg2
import pytest

from scripts.collectors.index_bloat import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.t (id int PRIMARY KEY, pad text);
INSERT INTO {s}.t SELECT g, repeat('x', 200) FROM generate_series(1, 5000) g;
DELETE FROM {s}.t WHERE id % 2 = 0;
"""


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_skips_cleanly_when_pgstattuple_absent(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"extensions": {}})       # extension not present
    finally:
        conn.close()
    assert diag["status"] == "skipped"
    assert "pgstattuple" in (diag["reason"] or "")
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_reports_dead_percent_when_pgstattuple_present(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")
        with make_schema(conn, "t_bloat", DDL):
            caps = {"extensions": {"pgstattuple": {"present": True, "schema": "public"}}}
            diag = collect(conn, caps)
    finally:
        conn.close()
    assert diag["status"] == "ok"
    row = [m for m in diag["metrics"] if m["schema"] == "t_bloat" and m["table"] == "t"]
    assert row and row[0]["dead_tuple_percent"] > 20  # ~half deleted -> substantial
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_index_bloat.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the collector**

Create `SKILL_DIR/scripts/collectors/index_bloat.py`:
```python
"""P0.1 — table/index bloat via pgstattuple (skip cleanly if extension absent)."""
from scripts.collectors import base

# User tables only; run pgstattuple_approx per table. LATERAL keeps it one query.
_SQL = """
SELECT ns.nspname AS schema, rel.relname AS tbl,
       st.table_len, st.dead_tuple_percent, st.approx_free_percent
FROM pg_class rel
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
CROSS JOIN LATERAL pgstattuple_approx(rel.oid) AS st
WHERE rel.relkind = 'r'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY st.dead_tuple_percent DESC
"""


def collect(conn, caps):
    if "pgstattuple" not in (caps.get("extensions") or {}):
        return base.skipped(
            "table",
            "index_bloat requires the pgstattuple extension (not installed)")
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "table_len": int(r[2]),
         "dead_tuple_percent": round(float(r[3]), 2),
         "approx_free_percent": round(float(r[4]), 2)}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `SKILL_DIR/scripts/collectors/__init__.py`, add:
```python
from scripts.collectors import index_bloat

COLLECTORS["index_bloat"] = index_bloat.collect
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_index_bloat.py -q`
Expected: PASS with Docker (2 tests). Skip without.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. (Note: the analyzer's live target has no `pgstattuple`, so `diagnostics["index_bloat"].status == "skipped"` — which does NOT make the target `partial`, only `error` does. Analyzer tests stay green.)

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors/index_bloat.py .agents/skills/db-report-generator/scripts/collectors/__init__.py .agents/skills/db-report-generator/tests/unit/test_index_bloat.py
git commit -m "feat(p0b): index-bloat collector via pgstattuple, no relhasoids (P0.1)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Dead-tuples collector (P0.4)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/dead_tuples.py`
- Create: `SKILL_DIR/tests/unit/test_dead_tuples.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> diagnostic` (scope `table`). Registers as `COLLECTORS["dead_tuples"]`.
- **Fix:** denominator is `n_live_tup + n_dead_tup` (not `n_live_tup`); a table with `n_live=0, n_dead>0` yields `dead_pct=100.0` (not 0). Column named `dead_pct`.
- Metric row: `{"schema", "table", "n_live", "n_dead", "dead_pct": float}`. Only rows with `n_dead > 0` (nothing dead is nothing to report).

**Note on testing the 100%-dead edge:** live stats (`n_live_tup`/`n_dead_tup`) update asynchronously via the stats collector, so a test that DELETEs rows cannot deterministically observe `n_live=0` immediately. The load-bearing correctness (the denominator + the `live=0,dead>0 → 100` branch) is proven by a **direct unit test of the pure formula function** `dead_pct(n_live, n_dead)`, plus a Docker test that the SQL runs and returns well-formed rows.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_dead_tuples.py`:
```python
import psycopg2
import pytest

from scripts.collectors.dead_tuples import collect, dead_pct
from tests.pgcontainer import docker_available


def test_dead_pct_formula_edges():
    assert dead_pct(0, 5) == 100.0        # all dead, no live -> 100 (was 0 in v3)
    assert dead_pct(100, 0) == 0.0
    assert dead_pct(50, 50) == 50.0
    assert dead_pct(0, 0) == 0.0          # no rows -> 0, no ZeroDivision


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_runs_and_rows_are_wellformed(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    for m in diag["metrics"]:
        assert m["n_dead"] > 0
        assert 0.0 <= m["dead_pct"] <= 100.0
        assert set(m) == {"schema", "table", "n_live", "n_dead", "dead_pct"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_dead_tuples.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the collector**

Create `SKILL_DIR/scripts/collectors/dead_tuples.py`:
```python
"""P0.4 — dead-tuple ratio with the correct denominator (n_live + n_dead)."""
from scripts.collectors import base

_SQL = """
SELECT schemaname, relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE n_dead_tup > 0
ORDER BY n_dead_tup DESC
"""


def dead_pct(n_live, n_dead):
    total = n_live + n_dead
    if total <= 0:
        return 0.0
    return round(n_dead / total * 100, 2)


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "n_live": int(r[2]), "n_dead": int(r[3]),
         "dead_pct": dead_pct(int(r[2]), int(r[3]))}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `SKILL_DIR/scripts/collectors/__init__.py`, add:
```python
from scripts.collectors import dead_tuples

COLLECTORS["dead_tuples"] = dead_tuples.collect
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_dead_tuples.py -q`
Expected: PASS (formula test always runs; Docker test with Docker).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors/dead_tuples.py .agents/skills/db-report-generator/scripts/collectors/__init__.py .agents/skills/db-report-generator/tests/unit/test_dead_tuples.py
git commit -m "feat(p0b): dead-tuple collector w/ correct denominator (P0.4)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Table index-size collector (P0.5)

**Files:**
- Create: `SKILL_DIR/scripts/collectors/table_index_size.py`
- Create: `SKILL_DIR/tests/unit/test_table_index_size.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> diagnostic` (scope `table`). Registers as `COLLECTORS["table_index_size"]`.
- **Fix:** report the true index size with `pg_indexes_size(relid)` labeled `index_bytes`, instead of `pg_total_relation_size - pg_relation_size` (which mislabels TOAST+meta as "index"). Also expose `toast_bytes` separately so the old blob is still visible but correctly named.
- Metric row: `{"schema", "table", "total_bytes", "heap_bytes", "index_bytes", "toast_bytes", "row_estimate"}`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_table_index_size.py`:
```python
import psycopg2
import pytest

from scripts.collectors.table_index_size import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.t (id int PRIMARY KEY, a int, b int);
CREATE INDEX ON {s}.t (a);
CREATE INDEX ON {s}.t (b);
INSERT INTO {s}.t SELECT g, g, g FROM generate_series(1, 2000) g;
"""


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_index_bytes_equals_pg_indexes_size(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, "t_idxsize", DDL):
            diag = collect(conn, {})
            with conn.cursor() as cur:
                cur.execute("SELECT pg_indexes_size('\"t_idxsize\".t'::regclass)")
                expected = cur.fetchone()[0]
    finally:
        conn.close()
    row = [m for m in diag["metrics"] if m["schema"] == "t_idxsize" and m["table"] == "t"][0]
    assert row["index_bytes"] == expected
    assert set(row) == {"schema", "table", "total_bytes", "heap_bytes",
                        "index_bytes", "toast_bytes", "row_estimate"}
    # heap + index + toast never exceeds the reported total
    assert row["heap_bytes"] + row["index_bytes"] + row["toast_bytes"] <= row["total_bytes"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_table_index_size.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the collector**

Create `SKILL_DIR/scripts/collectors/table_index_size.py`:
```python
"""P0.5 — table size breakdown with a correctly-labeled index size."""
from scripts.collectors import base

_SQL = """
SELECT ns.nspname AS schema, rel.relname AS tbl,
       pg_total_relation_size(rel.oid) AS total_bytes,
       pg_relation_size(rel.oid) AS heap_bytes,
       pg_indexes_size(rel.oid) AS index_bytes,
       COALESCE(pg_total_relation_size(rel.reltoastrelid), 0) AS toast_bytes,
       rel.reltuples::bigint AS row_estimate
FROM pg_class rel
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE rel.relkind = 'r'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "total_bytes": int(r[2]),
         "heap_bytes": int(r[3]), "index_bytes": int(r[4]),
         "toast_bytes": int(r[5]), "row_estimate": int(r[6])}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `SKILL_DIR/scripts/collectors/__init__.py`, add:
```python
from scripts.collectors import table_index_size

COLLECTORS["table_index_size"] = table_index_size.collect
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/unit/test_table_index_size.py -q`
Expected: PASS with Docker. Skip without.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/scripts/collectors/table_index_size.py .agents/skills/db-report-generator/scripts/collectors/__init__.py .agents/skills/db-report-generator/tests/unit/test_table_index_size.py
git commit -m "feat(p0b): table index-size collector, correct label (P0.5)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Acceptance Gate (Phase 0b)

- [ ] `python -m pytest -q` green (collector Docker tests pass with Docker, skip cleanly without).
- [ ] `analyze([...])` output stays schema-valid with `diagnostics` populated by all five collectors; a target with a failing collector reports `collection_status="partial"`, others `"ok"`.
- [ ] FK collector flags reversed-order / partial-only coverage and does NOT flag leading-prefix / INCLUDE-key coverage; suggested DDL quotes PascalCase identifiers.
- [ ] Duplicate collector never lists a PK/UNIQUE/exclusion index as a drop candidate; keep is deterministic; prefix redundancy detected.
- [ ] No `relhasoids` anywhere; bloat collector runs on PG14–18 (skips cleanly without pgstattuple).
- [ ] `dead_pct` uses `n_live+n_dead`; 100%-dead → 100.0.
- [ ] `index_bytes` equals `pg_indexes_size(relid)`.

## Decisions for plan review (flag to human before executing)

1. **Metrics-only, findings deferred to P3.** Collectors emit corrected `metrics[]`; severity/assessment/`findings[]` come from the Phase 3 rule engine. This keeps the phase boundary clean and avoids duplicating rule logic. (If you want P0.4's "🔴 for 100% dead" visible now, that is a *render/rule* concern and belongs to P3; the corrected `dead_pct` metric is what P0b guarantees.)
2. **P0.1 prefers `pgstattuple`, skips otherwise** — rather than porting the fragile `relhasoids`-based page estimator as a fallback. Honest `skipped` > misleading estimate, and it removes `relhasoids` entirely. This is a mild deviation from the spec's "keep the estimate as a guarded fallback"; confirm you accept it.
3. **Collector error `reason` = exception class name only** (not the message) to avoid leaking identifiers/paths into `report_data.json`.

## Self-Review notes

- **Spec coverage:** P0.1 (Task 5), P0.2 (Task 3), P0.3 (Task 4), P0.4 (Task 6), P0.5 (Task 7). P0.6/P0.7 → P6/P7; P0.8 done in P0a.
- **SQL verified** against live PG16 (fixtures with reversed/partial/INCLUDE FK cases, exact dup + PK/UNIQUE, dead_pct edges, pg_indexes_size) before this plan was written.
- **Version guards:** `duplicate_index` selects `indnullsnotdistinct` only on PG15+; `index_bloat` gates on the `pgstattuple` capability. Other collectors use catalog columns present on PG14–18.
- **Type consistency:** every collector returns `base.diagnostic(...)`; `run_collectors` and `_collection_status` consume `status`; analyzer fills `target["diagnostics"]`.
```

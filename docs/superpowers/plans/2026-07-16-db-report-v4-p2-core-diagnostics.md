# P2 — Core Diagnostics + Scope/Quality Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 12 new read-only collectors (P2.1–P2.12) covering wraparound risk, database-level activity counters, wait events, checkpoint/bgwriter health, WAL+HOT, index IO, stale stats, connection depth, replication, blocking, vacuum horizon, and `pg_stat_io` — plus extend `capabilities.py` with the two B5 probes (`track_io_timing`, `pg_stat_statements.track`) those collectors need.

**Architecture:** Every P2 collector follows the exact P0b/P1 pattern already established: a pure module under `scripts/collectors/`, registered in `scripts/collectors/__init__.py`'s `COLLECTORS` dict, called by `run_collectors(conn, caps, sampling=...)` with per-collector exception isolation already in place. All 12 collectors are **structural** (point-in-time reads against core catalog/stats views — no extension required, no new sampling window). This is a deliberate architecture decision (see Global Constraints) that keeps P2 additive-only: **no changes to `references/report-data.schema.json`** (the `scope` enum already covers `cluster|database|table|index|query`, and `capabilities`/`metrics` are open objects/arrays) and **no changes to `sampler.py` or the P1 sampling window**.

**Tech Stack:** Python 3, psycopg2 (read-only, server-enforced via `lib/db.py`), pytest with Docker-gated live-DB tests (`postgres:16` fixture, skip cleanly without Docker).

## Global Constraints

- **A4 (version matrix):** target officially PG14–18 (PG13 best-effort). Any collector reading a view/column that differs by version MUST branch on `caps["server_version_num"]` and degrade gracefully — never let an unsupported-version query raise past collector isolation. Two concrete version gates in this phase: `pg_stat_checkpointer` is PG17+ only (PG14–16 use `pg_stat_bgwriter`); `pg_stat_io` is PG16+ only (skip on PG14–15). `vacuum_failsafe_age`/`vacuum_multixact_failsafe_age` GUCs are PG14+ only.
- **A5 (schema contract):** every collector returns a `base.diagnostic(...)`/`base.skipped(...)` shaped dict — `collector_version`, `scope` (one of `cluster|database|table|index|query`), `status` (`ok|partial|skipped|error`), `quality`, `metrics`, `findings` (always `[]` this phase — the rule engine is Phase 3). `skipped` must never be read as "green" — that's a Phase 3 rendering concern, not this phase's.
- **B5 (`track_io_timing` capability):** `pg_stat_io`'s timing columns (`read_time`, `write_time`, `extend_time`, `fsync_time`) MUST be reported as `null`, **never `0`**, whenever `caps["track_io_timing"]` is `False` — even though PostgreSQL itself returns `0` (not `NULL`) for those columns when timing is disabled. This is the exact bug B5 exists to prevent: `0` reads as "no I/O wait", `null` correctly reads as "unknown, timing is off".
- **Metrics-only phase (carried from P0b/P1):** every collector's `findings` stays `[]`. Do not invent severities, assessments, or thresholds in Python collector code — that's Phase 3's rule engine. Do not add "assessment thresholds" logic anywhere in this phase.
- **Read-only, no new transaction/timeout management:** `db.connect(cfg)` already sets `readonly=True`, `autocommit=True`, `statement_timeout=15000ms`, `lock_timeout=3000ms` server-side (`scripts/lib/db.py`). Collectors never open transactions, set their own timeouts, or write.
- **Per-collector isolation is already in place** (`collectors/__init__.py::run_collectors`) — a new collector that raises becomes an `error` diagnostic and does not take down the others. No task in this plan touches that isolation mechanism.
- **No secret/PII leakage:** none of these collectors touch connection strings, passwords, or hosts. `blocking.py` (P2.10) does surface live query text (`blocked_query`/`blocking_query`) — this matches the already-established, already-deferred precedent of `query_stats.py` (P1.2) storing raw query text unredacted (`redaction_mode` wiring is a tracked pre-existing gap, out of scope for P2 — do not attempt to fix it here).
- **No git push without explicit user permission.** A real IP address remains in git history; local commits/merges only, exactly as done for P0a, P0b, and P1.
- **Never start work directly on `master`.** This phase's branch is `feature/db-report-v4-p2`, branched from current `master` (`f844056`).

### Architecture decision: why P2 collectors are structural, not delta-sampled

The spec's P2.2 line reads "`pg_stat_database`: deadlocks, temp_files/temp_bytes, xact_rollback/xact_commit, tup_*, conflicts, blks hit/read (as delta)". Building a second delta-sampling window (alongside P1's `pg_stat_statements` window) to properly "delta" `pg_stat_database`/`pg_stat_wal` would either (a) double per-target wall-clock latency (a second N-second sleep per target, working against §0.B4's latency-budget concern), or (b) require re-architecting `sampler.py` into a multi-channel capture shared with the existing window — a nontrivial change to already-reviewed, already-merged P1 code, for counters whose cumulative-since-reset form is already how virtually every PostgreSQL monitoring tool (pgAdmin, Datadog, etc.) presents them. v4's own scope decision (recorded in project memory) already defers cross-run trend/delta comparison to a **post-v4** `compare.py` tool — v4 itself stays snapshot-per-run. Consistent with that decision, P2.2/P2.5/P2.6 report **cumulative-since-`stats_reset`** counters plus the `stats_reset` timestamp itself (so Phase 3's rule engine, or a future `compare.py`, can contextualize magnitude against reset age). This is a conscious, documented tradeoff, the same way P0b documented its `pgstattuple` bloat tradeoff.

## Interfaces (shared across tasks)

- `scripts.collectors.base.diagnostic(scope, status, metrics, *, reason=None, quality=None, collector_version="1") -> dict` and `base.skipped(scope, reason, *, collector_version="1") -> dict` — unchanged, already exist.
- `scripts.capabilities.probe(conn) -> dict` — Task 1 adds two new keys: `track_io_timing: bool` and `pg_stat_statements_track: str | None`. Every later task's collector receives these via the `caps` dict already passed into `collect(conn, caps)` by `run_collectors`.
- Every new collector module exposes `collect(conn, caps) -> dict` (the shape `run_collectors` calls) plus any pure helper functions named in that task (e.g. `cache_hit_ratio`, `modified_pct`) for direct unit testing without a DB connection.
- Task 9 (`connection_depth.py`) additionally relies on a new key `caps["configured_pool_size"]` that Task 9 itself adds to `scripts/analyzer.py`'s `_analyze_target` (set right after `capabilities.probe(conn)` is called, from `cfg.raw.get("PoolSize")`) — no other task needs to know about this key.
- Task 13 (`stat_io.py`) depends on Task 1's `caps["track_io_timing"]` key — Task 13 must run after Task 1.

## File Structure

```
.agents/skills/db-report-generator/
  scripts/
    capabilities.py                        # MODIFY (Task 1)
    analyzer.py                            # MODIFY (Task 9 — configured_pool_size wiring)
    collectors/
      __init__.py                          # MODIFY (every task appends one registration)
      wraparound.py                        # CREATE (Task 2  — P2.1)
      database_stats.py                    # CREATE (Task 3  — P2.2)
      wait_events.py                       # CREATE (Task 4  — P2.3)
      checkpoint_activity.py               # CREATE (Task 5  — P2.4)
      wal_hot.py                           # CREATE (Task 6  — P2.5)
      index_io.py                          # CREATE (Task 7  — P2.6)
      stale_stats.py                       # CREATE (Task 8  — P2.7)
      connection_depth.py                  # CREATE (Task 9  — P2.8)
      replication.py                       # CREATE (Task 10 — P2.9)
      blocking.py                          # CREATE (Task 11 — P2.10)
      vacuum_horizon.py                    # CREATE (Task 12 — P2.11)
      stat_io.py                           # CREATE (Task 13 — P2.12)
  tests/unit/
    test_capabilities.py                   # MODIFY (Task 1)
    test_analyzer.py                       # MODIFY (Task 9)
    test_wraparound.py                     # CREATE (Task 2)
    test_database_stats.py                 # CREATE (Task 3)
    test_wait_events.py                    # CREATE (Task 4)
    test_checkpoint_activity.py            # CREATE (Task 5)
    test_wal_hot.py                        # CREATE (Task 6)
    test_index_io.py                       # CREATE (Task 7)
    test_stale_stats.py                    # CREATE (Task 8)
    test_connection_depth.py               # CREATE (Task 9)
    test_replication.py                    # CREATE (Task 10)
    test_blocking.py                       # CREATE (Task 11)
    test_vacuum_horizon.py                 # CREATE (Task 12)
    test_stat_io.py                        # CREATE (Task 13)
```

No changes to `references/report-data.schema.json` are required by this plan — verified against the current schema's `$defs.diagnostic.scope` enum (`cluster|database|table|index|query`, already covers every scope used below) and `$defs.target.capabilities` (`{"type": "object"}`, fully open).

---

### Task 1: `capabilities.py` — B5 probes (`track_io_timing`, `pg_stat_statements.track`)

**Files:**
- Modify: `.agents/skills/db-report-generator/scripts/capabilities.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_capabilities.py`

**Interfaces:**
- Produces: `probe(conn)` return dict gains `"track_io_timing": bool` and `"pg_stat_statements_track": str | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_capabilities.py`:

```python
@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_includes_io_timing_capabilities(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    assert caps["track_io_timing"] is False  # postgres:16 fixture image default
    assert caps["pg_stat_statements_track"] == "top"  # default once the library is preloaded
```

Also update the existing key-set assertion in `test_probe_shape_and_values` to include the two new keys:

```python
    assert set(["server_version_num", "is_superuser", "has_pg_read_all_stats",
                "has_pg_monitor", "vendor", "managed", "extensions", "ram_bytes",
                "track_io_timing", "pg_stat_statements_track"]) <= set(caps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_capabilities.py -v`
Expected: FAIL — `KeyError: 'track_io_timing'`

- [ ] **Step 3: Write minimal implementation**

Replace the body of `probe()` in `scripts/capabilities.py`:

```python
def probe(conn) -> dict:
    with conn.cursor() as cur:
        server_version_num = int(_scalar(cur, "SELECT current_setting('server_version_num')::int"))
        is_superuser = bool(_scalar(cur, "SELECT current_setting('is_superuser') = 'on'"))
        has_read_all = bool(_scalar(
            cur, "SELECT pg_catalog.pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')"))
        has_monitor = bool(_scalar(
            cur, "SELECT pg_catalog.pg_has_role(current_user, 'pg_monitor', 'USAGE')"))
        track_io_timing = bool(_scalar(cur, "SELECT current_setting('track_io_timing') = 'on'"))
        pg_stat_statements_track = _scalar(
            cur, "SELECT current_setting('pg_stat_statements.track', true)")
        cur.execute(
            "SELECT extname, extnamespace::regnamespace::text FROM pg_extension ORDER BY extname")
        extensions = {name: {"present": True, "schema": schema} for name, schema in cur.fetchall()}
        cur.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(_CLOUD_ROLES),))
        roles = {r[0] for r in cur.fetchall()}

    vendor = _vendor(roles)
    return {
        "server_version_num": server_version_num,
        "is_superuser": is_superuser,
        "has_pg_read_all_stats": has_read_all,
        "has_pg_monitor": has_monitor,
        "track_io_timing": track_io_timing,
        "pg_stat_statements_track": pg_stat_statements_track,
        "vendor": vendor,
        "managed": vendor in ("supabase", "rds", "aurora"),
        "extensions": extensions,
        "ram_bytes": None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_capabilities.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add scripts/capabilities.py tests/unit/test_capabilities.py
git commit -m "feat(p2): capabilities probes for track_io_timing + pg_stat_statements.track (B5)"
```

---

### Task 2: P2.1 — XID/MultiXact wraparound (`wraparound.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/wraparound.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_wraparound.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["wraparound"]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_wraparound.py`:

```python
import psycopg2
import pytest

from scripts.collectors.wraparound import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_returns_database_and_table_rows(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "database"
    levels = {m["level"] for m in diag["metrics"]}
    assert "database" in levels
    for m in diag["metrics"]:
        assert m["xid_age"] >= 0
        assert m["autovacuum_freeze_max_age"] > 0
        assert m["vacuum_failsafe_age"] is not None


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_failsafe_fields_are_none_before_pg14(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 130000})
    finally:
        conn.close()
    assert all(m["vacuum_failsafe_age"] is None for m in diag["metrics"])
    assert all(m["vacuum_multixact_failsafe_age"] is None for m in diag["metrics"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_wraparound.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.wraparound'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/wraparound.py`:

```python
"""P2.1 — XID/MultiXact wraparound relative to autovacuum_freeze_max_age/failsafe_age."""
from scripts.collectors import base

_GUC_SQL = """
SELECT current_setting('autovacuum_freeze_max_age')::bigint,
       current_setting('autovacuum_multixact_freeze_max_age')::bigint
"""

_FAILSAFE_SQL = """
SELECT current_setting('vacuum_failsafe_age')::bigint,
       current_setting('vacuum_multixact_failsafe_age')::bigint
"""

_DATABASE_SQL = """
SELECT datname, age(datfrozenxid) AS xid_age, age(datminmxid) AS mxid_age
FROM pg_database
WHERE datallowconn
ORDER BY age(datfrozenxid) DESC
"""

_TABLE_SQL = """
SELECT n.nspname, c.relname, age(c.relfrozenxid) AS xid_age, age(c.relminmxid) AS mxid_age
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 20
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_GUC_SQL)
        freeze_max_age, multixact_freeze_max_age = cur.fetchone()

        failsafe_age = multixact_failsafe_age = None
        if caps.get("server_version_num", 0) >= 140000:
            cur.execute(_FAILSAFE_SQL)
            failsafe_age, multixact_failsafe_age = cur.fetchone()

        cur.execute(_DATABASE_SQL)
        db_rows = cur.fetchall()
        cur.execute(_TABLE_SQL)
        table_rows = cur.fetchall()

    thresholds = {
        "autovacuum_freeze_max_age": freeze_max_age,
        "autovacuum_multixact_freeze_max_age": multixact_freeze_max_age,
        "vacuum_failsafe_age": failsafe_age,
        "vacuum_multixact_failsafe_age": multixact_failsafe_age,
    }
    metrics = [
        {"level": "database", "datname": row[0], "xid_age": row[1], "mxid_age": row[2], **thresholds}
        for row in db_rows
    ] + [
        {"level": "table", "schema": row[0], "table": row[1], "xid_age": row[2], "mxid_age": row[3],
         **thresholds}
        for row in table_rows
    ]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py` (immediately before the `def run_collectors` line):

```python
from scripts.collectors import wraparound

COLLECTORS["wraparound"] = wraparound.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_wraparound.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/wraparound.py scripts/collectors/__init__.py tests/unit/test_wraparound.py
git commit -m "feat(p2): XID/MultiXact wraparound collector (P2.1)"
```

---

### Task 3: P2.2 — `pg_stat_database` (`database_stats.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/database_stats.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_database_stats.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["database_stats"]`; pure helper `cache_hit_ratio(blks_hit, blks_read) -> float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_database_stats.py`:

```python
import psycopg2
import pytest

from scripts.collectors.database_stats import cache_hit_ratio, collect
from tests.pgcontainer import docker_available


def test_cache_hit_ratio_edges():
    assert cache_hit_ratio(0, 0) is None
    assert cache_hit_ratio(100, 0) == 1.0
    assert cache_hit_ratio(0, 100) == 0.0
    assert cache_hit_ratio(90, 10) == 0.9


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_returns_one_row_for_current_database(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "database"
    assert len(diag["metrics"]) == 1
    row = diag["metrics"][0]
    assert set(row) == {
        "numbackends", "xact_commit", "xact_rollback", "blks_read", "blks_hit",
        "cache_hit_ratio", "tup_returned", "tup_fetched", "tup_inserted", "tup_updated",
        "tup_deleted", "conflicts", "temp_files", "temp_bytes", "deadlocks", "stats_reset",
    }
    assert row["numbackends"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_database_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.database_stats'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/database_stats.py`:

```python
"""P2.2 — pg_stat_database: cumulative-since-reset counters + cache hit ratio."""
from scripts.collectors import base

_SQL = """
SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       conflicts, temp_files, temp_bytes, deadlocks, stats_reset
FROM pg_stat_database
WHERE datname = current_database()
"""


def cache_hit_ratio(blks_hit, blks_read):
    total = blks_hit + blks_read
    return round(blks_hit / total, 4) if total > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        row = cur.fetchone()
    if row is None:
        return base.skipped("database", "no pg_stat_database row for current_database()")
    (numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
     tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
     conflicts, temp_files, temp_bytes, deadlocks, stats_reset) = row
    metrics = [{
        "numbackends": numbackends, "xact_commit": xact_commit, "xact_rollback": xact_rollback,
        "blks_read": blks_read, "blks_hit": blks_hit,
        "cache_hit_ratio": cache_hit_ratio(blks_hit, blks_read),
        "tup_returned": tup_returned, "tup_fetched": tup_fetched, "tup_inserted": tup_inserted,
        "tup_updated": tup_updated, "tup_deleted": tup_deleted, "conflicts": conflicts,
        "temp_files": temp_files, "temp_bytes": temp_bytes, "deadlocks": deadlocks,
        "stats_reset": stats_reset.isoformat() if stats_reset else None,
    }]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import database_stats

COLLECTORS["database_stats"] = database_stats.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_database_stats.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/database_stats.py scripts/collectors/__init__.py tests/unit/test_database_stats.py
git commit -m "feat(p2): pg_stat_database collector (P2.2)"
```

---

### Task 4: P2.3 — Wait events (`wait_events.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/wait_events.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_wait_events.py`

**Interfaces:**
- Produces: `collect(conn, caps, *, samples=None, interval_seconds=None, sleep_fn=time.sleep) -> dict` registered as `COLLECTORS["wait_events"]`; module constants `SAMPLES = 5`, `INTERVAL_SECONDS = 1.0`; pure helper `_aggregate(samples: list[list[tuple]]) -> collections.Counter`.
- Note: `run_collectors` calls `fn(conn, merged_caps)` with exactly two positional args, so the keyword-only params always take their defaults in production; tests override the module-level `SAMPLES`/`INTERVAL_SECONDS` constants via `monkeypatch` to keep the live test fast. **The function must read `SAMPLES`/`INTERVAL_SECONDS` from the module namespace at call time (not bind them as literal default values)** so monkeypatching those constants actually takes effect.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_wait_events.py`:

```python
import psycopg2
import pytest

from scripts.collectors import wait_events
from scripts.collectors.wait_events import _aggregate, collect
from tests.pgcontainer import docker_available


def test_aggregate_combines_counts_across_samples():
    samples = [
        [("Lock", "relation"), ("IO", "DataFileRead")],
        [("Lock", "relation")],
        [(None, None)],
    ]
    # collect() normalizes None -> "CPU" in SQL; _aggregate takes rows as-is.
    counts = _aggregate(samples)
    assert counts[("Lock", "relation")] == 2
    assert counts[("IO", "DataFileRead")] == 1
    assert counts[(None, None)] == 1


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_is_insufficient_activity_when_idle(pg_dsn, monkeypatch):
    monkeypatch.setattr(wait_events, "SAMPLES", 2)
    monkeypatch.setattr(wait_events, "INTERVAL_SECONDS", 0.1)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["quality"]["insufficient_activity"] is True
    assert diag["metrics"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_wait_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.wait_events'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/wait_events.py`:

```python
"""P2.3 — multi-sample wait-event distribution over a short window."""
import time
from collections import Counter

from scripts.collectors import base

SAMPLES = 5
INTERVAL_SECONDS = 1.0

_SQL = """
SELECT wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database() AND pid != pg_backend_pid() AND state = 'active'
"""


def _sample_once(conn):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        return cur.fetchall()


def _aggregate(samples):
    counts = Counter()
    for rows in samples:
        for wait_event_type, wait_event in rows:
            counts[(wait_event_type, wait_event)] += 1
    return counts


def collect(conn, caps, *, samples=None, interval_seconds=None, sleep_fn=time.sleep):
    samples = samples if samples is not None else SAMPLES
    interval_seconds = interval_seconds if interval_seconds is not None else INTERVAL_SECONDS

    all_samples = []
    for i in range(samples):
        all_samples.append(_sample_once(conn))
        if i < samples - 1:
            sleep_fn(interval_seconds)

    counts = _aggregate(all_samples)
    total_observations = sum(counts.values())
    quality = dict(base.STRUCTURAL_QUALITY)
    if total_observations == 0:
        quality["insufficient_activity"] = True
        return base.diagnostic("database", "ok", [], quality=quality)

    metrics = [
        {"wait_event_type": t if t is not None else "CPU", "wait_event": e,
         "sample_count": c, "total_samples": samples}
        for (t, e), c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return base.diagnostic("database", "ok", metrics, quality=quality)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import wait_events

COLLECTORS["wait_events"] = wait_events.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_wait_events.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/wait_events.py scripts/collectors/__init__.py tests/unit/test_wait_events.py
git commit -m "feat(p2): wait-event distribution collector (P2.3)"
```

---

### Task 5: P2.4 — Checkpoint/bgwriter (`checkpoint_activity.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/checkpoint_activity.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_checkpoint_activity.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["checkpoint_activity"]`; pure helpers `_use_checkpointer(server_version_num) -> bool`, `checkpoints_req_ratio(checkpoints_timed, checkpoints_req) -> float | None`.
- The live Docker fixture is `postgres:16`, which takes the `pg_stat_bgwriter` branch (`pg_stat_checkpointer` is PG17+ and does not exist on this fixture) — the PG17+ branch is exercised by the version-gate unit test only, not the live test; full coverage of that branch depends on the project's PG17 CI matrix (§0.A4).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_checkpoint_activity.py`:

```python
import psycopg2
import pytest

from scripts.collectors.checkpoint_activity import (
    _use_checkpointer, checkpoints_req_ratio, collect,
)
from tests.pgcontainer import docker_available


def test_use_checkpointer_version_gate():
    assert _use_checkpointer(170000) is True
    assert _use_checkpointer(160005) is False
    assert _use_checkpointer(140000) is False


def test_checkpoints_req_ratio_edges():
    assert checkpoints_req_ratio(0, 0) is None
    assert checkpoints_req_ratio(10, 0) == 0.0
    assert checkpoints_req_ratio(0, 10) == 1.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_uses_bgwriter_on_pg16(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "cluster"
    row = diag["metrics"][0]
    assert row["source_view"] == "pg_stat_bgwriter"
    assert row["checkpoints_timed"] >= 0
    assert row["buffers_written"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_checkpoint_activity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.checkpoint_activity'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/checkpoint_activity.py`:

```python
"""P2.4 — checkpoint/bgwriter activity, version-guarded (pg_stat_checkpointer is PG17+)."""
from scripts.collectors import base

_CHECKPOINTER_SQL = """
SELECT num_timed, num_requested, write_time, sync_time, buffers_written, stats_reset
FROM pg_stat_checkpointer
"""

_BGWRITER_SQL = """
SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
       buffers_checkpoint, stats_reset
FROM pg_stat_bgwriter
"""


def _use_checkpointer(server_version_num):
    return server_version_num >= 170000


def checkpoints_req_ratio(checkpoints_timed, checkpoints_req):
    total = checkpoints_timed + checkpoints_req
    return round(checkpoints_req / total, 4) if total > 0 else None


def collect(conn, caps):
    use_checkpointer = _use_checkpointer(caps.get("server_version_num", 0))
    sql = _CHECKPOINTER_SQL if use_checkpointer else _BGWRITER_SQL
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    if row is None:
        return base.skipped("cluster", "no row returned from checkpoint/bgwriter stats view")

    checkpoints_timed, checkpoints_req, write_time_ms, sync_time_ms, buffers_written, stats_reset = row
    metrics = [{
        "source_view": "pg_stat_checkpointer" if use_checkpointer else "pg_stat_bgwriter",
        "checkpoints_timed": checkpoints_timed,
        "checkpoints_req": checkpoints_req,
        "checkpoints_req_ratio": checkpoints_req_ratio(checkpoints_timed, checkpoints_req),
        "write_time_ms": write_time_ms,
        "sync_time_ms": sync_time_ms,
        "buffers_written": buffers_written,
        "stats_reset": stats_reset.isoformat() if stats_reset else None,
    }]
    return base.diagnostic("cluster", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import checkpoint_activity

COLLECTORS["checkpoint_activity"] = checkpoint_activity.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_checkpoint_activity.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/checkpoint_activity.py scripts/collectors/__init__.py tests/unit/test_checkpoint_activity.py
git commit -m "feat(p2): checkpoint/bgwriter collector, PG17+ version-guarded (P2.4)"
```

---

### Task 6: P2.5 — WAL + HOT (`wal_hot.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/wal_hot.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_wal_hot.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["wal_hot"]`; pure helper `hot_update_ratio(n_tup_upd, n_tup_hot_upd) -> float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_wal_hot.py`:

```python
import psycopg2
import pytest

from scripts.collectors.wal_hot import collect, hot_update_ratio
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_hot_update_ratio_edges():
    assert hot_update_ratio(0, 0) is None
    assert hot_update_ratio(10, 10) == 1.0
    assert hot_update_ratio(10, 0) == 0.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_wal_row_and_hot_table_row(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "walhot_test",
                "CREATE TABLE {s}.t (id int primary key, v int)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "walhot_test".t (id, v) VALUES (1, 1)')
                cur.execute('UPDATE "walhot_test".t SET v = 2 WHERE id = 1')
            diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    levels = {m["level"] for m in diag["metrics"]}
    assert "wal" in levels
    table_rows = [m for m in diag["metrics"] if m["level"] == "table" and m["table"] == "t"]
    assert len(table_rows) == 1
    assert table_rows[0]["n_tup_upd"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_wal_hot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.wal_hot'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/wal_hot.py`:

```python
"""P2.5 — WAL volume (cumulative since reset) + HOT update ratio per table."""
from scripts.collectors import base

_WAL_SQL = """
SELECT wal_records, wal_fpi, wal_bytes, wal_buffers_full, stats_reset
FROM pg_stat_wal
"""

_HOT_SQL = """
SELECT schemaname, relname, n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC
LIMIT 20
"""


def hot_update_ratio(n_tup_upd, n_tup_hot_upd):
    return round(n_tup_hot_upd / n_tup_upd, 4) if n_tup_upd > 0 else None


def collect(conn, caps):
    metrics = []
    if caps.get("server_version_num", 0) >= 140000:
        with conn.cursor() as cur:
            cur.execute(_WAL_SQL)
            row = cur.fetchone()
        if row is not None:
            wal_records, wal_fpi, wal_bytes, wal_buffers_full, stats_reset = row
            metrics.append({
                "level": "wal", "wal_records": wal_records, "wal_fpi": wal_fpi,
                "wal_bytes": wal_bytes, "wal_buffers_full": wal_buffers_full,
                "stats_reset": stats_reset.isoformat() if stats_reset else None,
            })

    with conn.cursor() as cur:
        cur.execute(_HOT_SQL)
        hot_rows = cur.fetchall()
    metrics += [
        {"level": "table", "schema": r[0], "table": r[1], "n_tup_upd": r[2], "n_tup_hot_upd": r[3],
         "hot_update_ratio": hot_update_ratio(r[2], r[3])}
        for r in hot_rows
    ]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import wal_hot

COLLECTORS["wal_hot"] = wal_hot.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_wal_hot.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/wal_hot.py scripts/collectors/__init__.py tests/unit/test_wal_hot.py
git commit -m "feat(p2): WAL volume + HOT update ratio collector (P2.5)"
```

---

### Task 7: P2.6 — Index-level cache/IO (`index_io.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/index_io.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_index_io.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["index_io"]`; pure helper `cache_hit_ratio(idx_blks_hit, idx_blks_read) -> float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_index_io.py`:

```python
import psycopg2
import pytest

from scripts.collectors.index_io import cache_hit_ratio, collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_cache_hit_ratio_edges():
    assert cache_hit_ratio(0, 0) is None
    assert cache_hit_ratio(5, 0) == 1.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_created_index(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "idxio_test",
                "CREATE TABLE {s}.t (id int primary key, v int); "
                "CREATE INDEX t_v_idx ON {s}.t (v)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "idxio_test".t (id, v) VALUES (1, 1)')
                cur.execute('SELECT * FROM "idxio_test".t WHERE v = 1')
            diag = collect(conn, {})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    assert diag["scope"] == "index"
    names = {m["index"] for m in diag["metrics"]}
    assert "t_v_idx" in names
    row = next(m for m in diag["metrics"] if m["index"] == "t_v_idx")
    assert set(row) == {"schema", "table", "index", "idx_blks_read", "idx_blks_hit",
                         "cache_hit_ratio", "idx_scan"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_index_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.index_io'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/index_io.py`:

```python
"""P2.6 — index-level cache/IO (cumulative since reset)."""
from scripts.collectors import base

_SQL = """
SELECT sio.schemaname, sio.relname, sio.indexrelname, sio.idx_blks_read, sio.idx_blks_hit,
       COALESCE(sui.idx_scan, 0)
FROM pg_statio_user_indexes sio
JOIN pg_stat_user_indexes sui USING (indexrelid)
ORDER BY sio.idx_blks_read DESC
LIMIT 30
"""


def cache_hit_ratio(idx_blks_hit, idx_blks_read):
    total = idx_blks_hit + idx_blks_read
    return round(idx_blks_hit / total, 4) if total > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "index": r[2], "idx_blks_read": r[3], "idx_blks_hit": r[4],
         "cache_hit_ratio": cache_hit_ratio(r[4], r[3]), "idx_scan": r[5]}
        for r in rows
    ]
    return base.diagnostic("index", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import index_io

COLLECTORS["index_io"] = index_io.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_index_io.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/index_io.py scripts/collectors/__init__.py tests/unit/test_index_io.py
git commit -m "feat(p2): index-level cache/IO collector (P2.6)"
```

---

### Task 8: P2.7 — Stale stats (`stale_stats.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/stale_stats.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_stale_stats.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["stale_stats"]`; pure helper `modified_pct(n_live_tup, n_mod_since_analyze) -> float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_stale_stats.py`:

```python
import psycopg2
import pytest

from scripts.collectors.stale_stats import collect, modified_pct
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_modified_pct_edges():
    assert modified_pct(0, 5) is None
    assert modified_pct(100, 50) == 50.0
    assert modified_pct(100, 0) == 0.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_unanalyzed_table(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "stale_test", "CREATE TABLE {s}.t (id int primary key)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "stale_test".t (id) VALUES (1), (2), (3)')
            diag = collect(conn, {})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    assert diag["scope"] == "table"
    row = next(m for m in diag["metrics"] if m["table"] == "t")
    assert row["n_mod_since_analyze"] >= 3
    assert row["last_analyze"] is None
    assert row["last_autoanalyze"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_stale_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.stale_stats'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/stale_stats.py`:

```python
"""P2.7 — stale table statistics: modified rows vs. analyze cadence."""
from scripts.collectors import base

_SQL = """
SELECT schemaname, relname, n_live_tup, n_mod_since_analyze, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_mod_since_analyze DESC
LIMIT 30
"""


def modified_pct(n_live_tup, n_mod_since_analyze):
    return round(n_mod_since_analyze / n_live_tup * 100, 2) if n_live_tup > 0 else None


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = []
    for schema, table, n_live, n_mod, last_analyze, last_autoanalyze in rows:
        candidates = [t for t in (last_analyze, last_autoanalyze) if t is not None]
        last_analyzed_at = max(candidates) if candidates else None
        metrics.append({
            "schema": schema, "table": table, "n_live_tup": n_live, "n_mod_since_analyze": n_mod,
            "modified_pct": modified_pct(n_live, n_mod),
            "last_analyze": last_analyze.isoformat() if last_analyze else None,
            "last_autoanalyze": last_autoanalyze.isoformat() if last_autoanalyze else None,
            "last_analyzed_at": last_analyzed_at.isoformat() if last_analyzed_at else None,
        })
    return base.diagnostic("table", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import stale_stats

COLLECTORS["stale_stats"] = stale_stats.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_stale_stats.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/stale_stats.py scripts/collectors/__init__.py tests/unit/test_stale_stats.py
git commit -m "feat(p2): stale statistics collector (P2.7)"
```

---

### Task 9: P2.8 — Connection depth (`connection_depth.py` + `analyzer.py` wiring)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/connection_depth.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Modify: `.agents/skills/db-report-generator/scripts/analyzer.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_connection_depth.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_analyzer.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["connection_depth"]`.
- Produces: `scripts/analyzer.py::_analyze_target` sets `target["capabilities"]["configured_pool_size"] = cfg.raw.get("PoolSize")` immediately after `capabilities.probe(conn)`, so `caps["configured_pool_size"]` is available to `connection_depth.collect` via the same `target["capabilities"]` dict `run_collectors` already receives.
- This fixes the v3 bug of comparing a per-database connection count against the cluster-wide `max_connections` ceiling without saying so: this collector reports `db_connections` (this database only) and `cluster_connections`/`cluster_max_connections` (explicitly named as cluster-wide) as separate, clearly-labeled fields — never conflated.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_connection_depth.py`:

```python
import psycopg2
import pytest

from scripts.collectors.connection_depth import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_scoped_and_cluster_counts(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"configured_pool_size": 20})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    row = diag["metrics"][0]
    assert row["db_connections"] >= 1
    assert row["cluster_connections"] >= row["db_connections"]
    assert row["cluster_max_connections"] > 0
    assert row["configured_pool_size"] == 20


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_pool_size_defaults_to_none(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["metrics"][0]["configured_pool_size"] is None
```

Append to `tests/unit/test_analyzer.py`:

```python
def test_analyze_wires_configured_pool_size_from_raw_env(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    cfg = dataclasses.replace(_good(pg_dsn))
    cfg.raw["PoolSize"] = 15
    report = analyze([cfg])
    assert report["targets"][0]["capabilities"]["configured_pool_size"] == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_connection_depth.py tests/unit/test_analyzer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.collectors.connection_depth'` (and, once that's created, `KeyError: 'configured_pool_size'` in the analyzer test until Step 3's `analyzer.py` edit lands)

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/connection_depth.py`:

```python
"""P2.8 — connection depth, explicitly scoped: db-scoped counts never compared to
cluster-wide max_connections without both being clearly labeled (the v3 bug)."""
from scripts.collectors import base

_SQL = """
SELECT
    count(*) FILTER (WHERE datname = current_database()) AS db_connections,
    count(*) AS cluster_connections,
    count(*) FILTER (WHERE datname = current_database() AND state = 'idle in transaction')
        AS idle_in_transaction,
    max(EXTRACT(EPOCH FROM (now() - xact_start)))
        FILTER (WHERE datname = current_database() AND xact_start IS NOT NULL) AS longest_txn_seconds
FROM pg_stat_activity
"""

_MAX_CONNECTIONS_SQL = "SELECT current_setting('max_connections')::int"


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        db_connections, cluster_connections, idle_in_transaction, longest_txn_seconds = cur.fetchone()
        cur.execute(_MAX_CONNECTIONS_SQL)
        cluster_max_connections = cur.fetchone()[0]

    metrics = [{
        "db_connections": db_connections,
        "cluster_connections": cluster_connections,
        "cluster_max_connections": cluster_max_connections,
        "idle_in_transaction": idle_in_transaction,
        "longest_txn_seconds": longest_txn_seconds,
        "configured_pool_size": caps.get("configured_pool_size"),
    }]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import connection_depth

COLLECTORS["connection_depth"] = connection_depth.collect
```

In `scripts/analyzer.py`, modify `_analyze_target` — change:

```python
            target["capabilities"] = capabilities.probe(conn)
            pgss = target["capabilities"].get("extensions", {}).get("pg_stat_statements")
```

to:

```python
            target["capabilities"] = capabilities.probe(conn)
            target["capabilities"]["configured_pool_size"] = cfg.raw.get("PoolSize")
            pgss = target["capabilities"].get("extensions", {}).get("pg_stat_statements")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_connection_depth.py tests/unit/test_analyzer.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/connection_depth.py scripts/collectors/__init__.py scripts/analyzer.py tests/unit/test_connection_depth.py tests/unit/test_analyzer.py
git commit -m "feat(p2): connection depth collector, explicit db-vs-cluster scoping (P2.8)"
```

---

### Task 10: P2.9 — Replication slots (`replication.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/replication.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_replication.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["replication"]`. Empty `pg_replication_slots`/`pg_stat_replication` is a legitimate healthy state (`status="ok"`, `metrics=[]`) — not `skipped`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_replication.py`:

```python
import psycopg2
import pytest

from scripts.collectors.replication import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_is_ok_and_empty_with_no_replication_configured(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["scope"] == "cluster"
    assert diag["metrics"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_replication.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.replication'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/replication.py`:

```python
"""P2.9 — replication slots + standby lag. Empty results are a legitimate healthy state."""
from scripts.collectors import base

_SLOTS_SQL = """
SELECT slot_name, slot_type, active, wal_status,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint AS retained_wal_bytes
FROM pg_replication_slots
"""

_STANDBY_SQL = """
SELECT application_name, state,
       pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint AS replay_lag_bytes
FROM pg_stat_replication
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SLOTS_SQL)
        slot_rows = cur.fetchall()
        cur.execute(_STANDBY_SQL)
        standby_rows = cur.fetchall()

    metrics = [
        {"level": "slot", "slot_name": r[0], "slot_type": r[1], "active": r[2],
         "wal_status": r[3], "retained_wal_bytes": r[4]}
        for r in slot_rows
    ] + [
        {"level": "standby", "application_name": r[0], "state": r[1], "replay_lag_bytes": r[2]}
        for r in standby_rows
    ]
    return base.diagnostic("cluster", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import replication

COLLECTORS["replication"] = replication.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_replication.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/replication.py scripts/collectors/__init__.py tests/unit/test_replication.py
git commit -m "feat(p2): replication slots + standby lag collector (P2.9)"
```

---

### Task 11: P2.10 — Blocking graph (`blocking.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/blocking.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_blocking.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["blocking"]`. Empty result is a legitimate healthy state (`status="ok"`, `metrics=[]`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_blocking.py`:

```python
import threading
import time

import psycopg2
import pytest

from scripts.collectors.blocking import collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_finds_no_blocking_by_default(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_finds_a_real_blocking_pair(pg_dsn):
    conn_a = psycopg2.connect(**pg_dsn)
    conn_a.autocommit = True
    conn_b = psycopg2.connect(**pg_dsn)
    conn_watch = psycopg2.connect(**pg_dsn)
    conn_watch.autocommit = True

    with _fixtures_sql.make_schema(conn_a, "blk_test", "CREATE TABLE {s}.t (id int primary key)"):
        with conn_a.cursor() as cur:
            cur.execute('INSERT INTO "blk_test".t (id) VALUES (1)')
            cur.execute('BEGIN')
            cur.execute('SELECT * FROM "blk_test".t WHERE id = 1 FOR UPDATE')

        blocked_started = threading.Event()

        def _blocked_update():
            with conn_b.cursor() as cur:
                blocked_started.set()
                cur.execute('UPDATE "blk_test".t SET id = 1 WHERE id = 1')

        t = threading.Thread(target=_blocked_update)
        t.start()
        blocked_started.wait(timeout=5)
        time.sleep(0.5)

        try:
            diag = collect(conn_watch, {})
        finally:
            with conn_a.cursor() as cur:
                cur.execute('COMMIT')
            t.join(timeout=5)
            conn_b.close()

    conn_a.close()
    conn_watch.close()

    assert diag["status"] == "ok"
    assert len(diag["metrics"]) == 1
    row = diag["metrics"][0]
    assert "SELECT" in row["blocking_query"]
    assert "UPDATE" in row["blocked_query"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_blocking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.blocking'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/blocking.py`:

```python
"""P2.10 — session blocking graph via pg_blocking_pids(). Empty is healthy."""
from scripts.collectors import base

_SQL = """
SELECT blocked.pid, blocked.usename, blocking.pid, blocking.usename,
       blocked.query, blocking.query,
       EXTRACT(EPOCH FROM (now() - blocked.query_start))
FROM pg_stat_activity blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS bp(pid) ON true
JOIN pg_stat_activity blocking ON blocking.pid = bp.pid
WHERE blocked.datname = current_database()
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"blocked_pid": r[0], "blocked_user": r[1], "blocking_pid": r[2], "blocking_user": r[3],
         "blocked_query": r[4], "blocking_query": r[5], "blocked_duration_seconds": r[6]}
        for r in rows
    ]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import blocking

COLLECTORS["blocking"] = blocking.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_blocking.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/blocking.py scripts/collectors/__init__.py tests/unit/test_blocking.py
git commit -m "feat(p2): session blocking graph collector (P2.10)"
```

---

### Task 12: P2.11 — Vacuum horizon (`vacuum_horizon.py`)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/vacuum_horizon.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_vacuum_horizon.py`

**Interfaces:**
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["vacuum_horizon"]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_vacuum_horizon.py`:

```python
import psycopg2
import pytest

from scripts.collectors.vacuum_horizon import collect
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_own_backend_xmin(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    backend_rows = [m for m in diag["metrics"] if m["level"] == "backend"]
    assert len(backend_rows) >= 1
    assert all(m["xmin_age"] is not None for m in backend_rows)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_prepared_xacts_empty_by_default(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert [m for m in diag["metrics"] if m["level"] == "prepared_xact"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_vacuum_horizon.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.vacuum_horizon'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/vacuum_horizon.py`:

```python
"""P2.11 — what's pinning the vacuum horizon: long-running backends + prepared transactions."""
from scripts.collectors import base

_BACKEND_SQL = """
SELECT pid, usename, state, age(backend_xmin),
       EXTRACT(EPOCH FROM (now() - xact_start))
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL AND datname = current_database()
ORDER BY age(backend_xmin) DESC
LIMIT 20
"""

_PREPARED_SQL = """
SELECT gid, owner, age(transaction)
FROM pg_prepared_xacts
WHERE database = current_database()
ORDER BY age(transaction) DESC
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_BACKEND_SQL)
        backend_rows = cur.fetchall()
        cur.execute(_PREPARED_SQL)
        prepared_rows = cur.fetchall()

    metrics = [
        {"level": "backend", "pid": r[0], "usename": r[1], "state": r[2],
         "xmin_age": r[3], "xact_age_seconds": r[4]}
        for r in backend_rows
    ] + [
        {"level": "prepared_xact", "gid": r[0], "owner": r[1], "xid_age": r[2]}
        for r in prepared_rows
    ]
    return base.diagnostic("database", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import vacuum_horizon

COLLECTORS["vacuum_horizon"] = vacuum_horizon.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_vacuum_horizon.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/vacuum_horizon.py scripts/collectors/__init__.py tests/unit/test_vacuum_horizon.py
git commit -m "feat(p2): vacuum horizon collector — backend_xmin + prepared xacts (P2.11)"
```

---

### Task 13: P2.12 — `pg_stat_io` (`stat_io.py`), capability-gated (B5)

**Files:**
- Create: `.agents/skills/db-report-generator/scripts/collectors/stat_io.py`
- Modify: `.agents/skills/db-report-generator/scripts/collectors/__init__.py`
- Test: `.agents/skills/db-report-generator/tests/unit/test_stat_io.py`

**Interfaces:**
- Consumes: `caps["track_io_timing"]` (from Task 1's `capabilities.py` extension) and `caps["server_version_num"]`.
- Produces: `collect(conn, caps) -> dict` registered as `COLLECTORS["stat_io"]`.
- **B5 invariant under test:** when `track_io_timing` is `False`, the four timing fields (`read_time_ms`, `write_time_ms`, `extend_time_ms`, `fsync_time_ms`) must be `None` in every metric row, even though PostgreSQL itself returns `0` (not `NULL`) for those columns when timing is disabled — this collector must NOT pass the raw `0` through.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_stat_io.py`:

```python
import psycopg2
import pytest

from scripts.collectors.stat_io import collect
from tests.pgcontainer import docker_available


def test_collect_skips_before_pg16():
    diag = collect(None, {"server_version_num": 150006})
    assert diag["status"] == "skipped"
    assert "16" in diag["reason"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_nulls_timing_columns_when_track_io_timing_is_off(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        # postgres:16 fixture image default is track_io_timing = off
        diag = collect(conn, {"server_version_num": 160000, "track_io_timing": False})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert len(diag["metrics"]) > 0
    for row in diag["metrics"]:
        assert row["read_time_ms"] is None
        assert row["write_time_ms"] is None
        assert row["extend_time_ms"] is None
        assert row["fsync_time_ms"] is None
        assert row["reads"] is not None  # non-timing counters still reported
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_stat_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.stat_io'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/collectors/stat_io.py`:

```python
"""P2.12 — pg_stat_io (PG16+), gated by track_io_timing (B5: unknown, never 0)."""
from scripts.collectors import base

_SQL = """
SELECT backend_type, object, context, reads, writes, hits,
       read_time, write_time, extend_time, fsync_time
FROM pg_stat_io
"""


def collect(conn, caps):
    if caps.get("server_version_num", 0) < 160000:
        return base.skipped("cluster", "pg_stat_io requires PostgreSQL 16+")

    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()

    track_io_timing = bool(caps.get("track_io_timing"))
    metrics = []
    for (backend_type, obj, context, reads, writes, hits,
         read_time, write_time, extend_time, fsync_time) in rows:
        metrics.append({
            "backend_type": backend_type, "object": obj, "context": context,
            "reads": reads, "writes": writes, "hits": hits,
            "read_time_ms": read_time if track_io_timing else None,
            "write_time_ms": write_time if track_io_timing else None,
            "extend_time_ms": extend_time if track_io_timing else None,
            "fsync_time_ms": fsync_time if track_io_timing else None,
        })
    return base.diagnostic("cluster", "ok", metrics)
```

Append to `scripts/collectors/__init__.py`:

```python
from scripts.collectors import stat_io

COLLECTORS["stat_io"] = stat_io.collect
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_stat_io.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/collectors/stat_io.py scripts/collectors/__init__.py tests/unit/test_stat_io.py
git commit -m "feat(p2): pg_stat_io collector, track_io_timing-gated per B5 (P2.12)"
```

---

## Post-implementation: full suite + final review

After Task 13, run the complete suite once (`pytest -q` from the skill root) to confirm all P0/P1/P2 tests remain green together, then proceed to the final whole-branch review per `superpowers:subagent-driven-development` (dispatch on the most capable available model), covering the full `feature/db-report-v4-p2` diff against `master`.

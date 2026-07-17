# P4 — EXPLAIN Plan-Only + Column/RLS + Code-Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EXPLAIN-plan capture for the top-N slow queries, a column-level index advisor, RLS policy re-evaluation-trap detection, schema hygiene checks, and honest code-analysis documentation — closing spec §0.B1's "cited-but-dead" GENERIC_PLAN requirement and filling in the P3-placeholder `security-rls` rule axis.

**Architecture:** Three new pure/DB-touching library modules (`scripts/lib/sql_classify.py`, `scripts/lib/index_predicate.py`, `scripts/lib/index_catalog.py`) built on `pglast` (a real PostgreSQL grammar parser — never regex, per spec §0.A3's explicit instruction and project rule N2's explicit exemption for SQL-text safety classification). Two standalone analysis modules (`scripts/explain.py`, `scripts/index_advisor.py`) called directly from `analyzer.py`, not registered in `COLLECTORS`, because both need the *ranked output* of the existing `query_stats` collector — a cross-collector dependency `run_collectors`'s uniform `collect(conn, caps)` loop can't express. Two new ordinary `COLLECTORS`-registered collectors (`rls_policies.py`, `schema_checks.py`) follow the standard collector shape. Every new step is isolated in `analyzer.py` the same way the sampler and `rules.evaluate_target` already are, so one step's failure never corrupts an otherwise-healthy target's `collection_status`.

**Tech Stack:** Python 3, psycopg2, `pglast==8.2` (new dependency), pytest, Docker-gated live-Postgres tests (skip cleanly without Docker, matching the P0b–P3 convention).

## Global Constraints

Verbatim from `docs/superpowers/specs/2026-07-16-db-report-generator-v4-upgrade.md`, §0.A3 (lines 44-59):

```
ExplainMode=plan            # off | plan | analyze   (mặc định plan)
ExplainTopN=5
ExplainAnalyzeTopN=0
ExplainStatementTimeoutMs=3000
ExplainLockTimeoutMs=500
```

> - `off` = không chạy; `plan` = EXPLAIN không ANALYZE (mặc định); `analyze` = opt-in tường minh + allowlist.
> - Query có placeholder → generic plan **khi PG≥16** (không ANALYZE — xem B1).
> - Query có `FOR UPDATE` / advisory lock / volatile function / FDW / không phân loại chắc → **không** ANALYZE.
> - **Không** dùng regex "bắt đầu bằng SELECT" làm safety gate; dùng parser PG (`pglast`/`libpg_query`) để phân loại SQL — N2 chỉ cấm AST cho application code, **không** cấm việc này.
> - Ghi `role`/`search_path`/`database`/planning GUC; khác execution context thật → giảm confidence.
> - Tách `SlowQueryTopN` khỏi `ExplainTopN`; **không** mặc định ANALYZE 20 query.

Verbatim §0.B1 (line 94):

> **B1 — Plan-mode bất khả thi trên query normalized ở PG14/15.** `GENERIC_PLAN` chỉ có từ **PG16+**. Query `$1,$2` từ `pg_stat_statements` không PREPARE được để `EXPLAIN` trên <16 → trạng thái `explain_unavailable: "parameterized_pre_pg16"`, **không** im lặng bỏ qua (nếu không sẽ thành "cited-but-dead" mới).

Verbatim §10, Phase 4 deliverables (lines 298-306):

> - **P4.1 EXPLAIN:** `explain.py` mặc định `ExplainMode=plan` (EXPLAIN **không** ANALYZE) cho top-N slow query; gắn plan vào finding. **CHỐT LẠI (§0.A3/B1):** ANALYZE chỉ khi opt-in tường minh + allowlist + timeout (`read-only txn + ROLLBACK` KHÔNG đủ an toàn: ANALYZE thực thi statement, không chặn lock/side-effect/tài nguyên). Query normalized `$1,$2` → generic plan khi PG≥16; PG<16 → `explain_unavailable: parameterized_pre_pg16`. Phân loại SQL bằng parser PG, không bằng regex "SELECT".
> - **P4.2 Column metadata + predicate:** thu kiểu cột (`pg_attribute`); parse WHERE/JOIN từ text slow query → gợi index **cấp cột** (composite equality-first, partial soft-delete, covering INCLUDE, đúng index type). Kiểm tra index đã tồn tại để không đề xuất trùng.
> - **P4.3 RLS:** `pg_policies` → phát hiện `auth.uid()`/`current_setting(...)` **không bọc `(select ...)`** (re-eval mỗi row) + cột policy thiếu index. Bật khi phát hiện RLS/Supabase.
> - **P4.4 Schema:** bảng thiếu PK; UUIDv4 làm PK bảng lớn; `timestamp` thay vì `timestamptz`.
> - **P4.5 Code-analysis trung thực:** giữ grep nhưng gắn **mức tin cậy**; nêu rõ "không thấy SQL ORM sinh"; **bỏ "Code Quality /100"**; ưu tiên tín hiệu chắc (nối chuỗi SQL, SELECT *, connection-leak pattern).
>
> *Acceptance:* mỗi slow-query finding có plan hoặc lý do không chạy được EXPLAIN; ít nhất 1 gợi index cấp cột trên dữ liệu mẫu; RLS re-eval được phát hiện trên policy chưa bọc subselect.

Verbatim §13 (line 335), confirming the exact `.env` field set and the removal of the old field:

> - `.env` v3 vẫn chạy; field mới **optional** (kèm mặc định): `SamplingWindowSeconds` (mặc định 30), `SlowQueryTopN` (mặc định 20, giữ như v3), `ExplainMode` (`off|plan|analyze`, **mặc định `plan`** — §0.A3), `ExplainTopN` (5), `ExplainAnalyzeTopN` (0), `ExplainStatementTimeoutMs` (3000), `ExplainLockTimeoutMs` (500). *(Bỏ `ExplainEnabled=true` cũ.)*

Verbatim N2 (line 148), the non-goal this phase must respect for P4.5:

> N2. Không làm static-analyzer code thực thụ (AST) — code-analysis vẫn heuristic nhưng **hạ cấp cách trình bày** cho trung thực.

### Architecture decision: pglast is the N2 exemption, not a violation of it

N2 forbids building a real AST-based static analyzer for **application code** (P4.5's grep-based code-analysis stays heuristic, unchanged in kind). §0.A3 explicitly carves out SQL-text safety classification from that ban: *"N2 chỉ cấm AST cho application code, không cấm việc này."* `pglast` is used exclusively to parse **SQL statement text** (from `pg_stat_statements`, `pg_policies`) for three purposes: (1) is this one statement or an injection attempt via `;`, (2) does it reference parameters, unsafe volatile functions, or a locking clause, (3) which columns does its WHERE/ON clause reference. It never analyzes application source files.

### Architecture decision: GENERIC_PLAN uses direct syntax, no PREPARE/EXECUTE/DEALLOCATE

PG16+ supports `EXPLAIN (GENERIC_PLAN, FORMAT JSON) <sql-with-$1-params>` as a single direct statement — no `PREPARE`/`EXECUTE`/`DEALLOCATE` cycle is needed or used anywhere in this plan.

### Architecture decision: `is_readonly_sql` stays unused; ANALYZE safety comes from the parser allowlist alone

`scripts/lib/safety.py`'s `is_readonly_sql()` regex pre-filter (from Phase −1) is **not** wired into `explain.py`. Plan-mode EXPLAIN (`EXPLAIN` without `ANALYZE`) never executes the target statement regardless of whether it's a SELECT, INSERT, UPDATE, or DELETE — gating plan-mode on "is this read-only" would incorrectly exclude legitimate DML queries from a safe plan-only EXPLAIN. The real safety boundary — for the one mode that does execute (ANALYZE) — is `scripts/lib/sql_classify.py`'s `is_analyze_safe()`, a parser-based allowlist restricted to `SELECT` statements with no locking clause and no unsafe volatile function call. `is_readonly_sql()` remains exactly as Phase −1 left it: unused, its own docstring already says the real boundary is the P4 parser allowlist.

### Architecture decision: a read-only transaction is not relied on for ANALYZE safety

Per spec P4.1: `read-only txn + ROLLBACK` is explicitly **not sufficient** — `ANALYZE` executes the statement regardless of transaction read-only mode (e.g. `nextval()` runs even inside `SET TRANSACTION READ ONLY`). Safety for ANALYZE mode comes entirely from `sql_classify.is_analyze_safe()`'s allowlist (SELECT-only, no locking clause, no unsafe function) plus a foreign-table catalog check, combined with tight `ExplainStatementTimeoutMs`/`ExplainLockTimeoutMs` bounds set immediately before the EXPLAIN and always restored afterward.

### Architecture decision: multi-statement injection is closed at the parser layer

`explain.py` must embed query text directly into `EXPLAIN ... {sql}` via string concatenation — `EXPLAIN`'s target statement cannot be parameterized by the driver. This is closed by `sql_classify.parse_statement()`: it calls `pglast.parse_sql(sql)` and returns `None` (unparseable) whenever the result is not **exactly one** statement, rejecting any `sql; DROP TABLE x` style payload before it ever reaches a cursor.

### Architecture decision: `explain.py` has no rule-catalog entry; `index_advisor.py` does

An EXPLAIN plan is raw supplementary evidence attached to a query row, not itself a judgment — no rule in `references/rules/*.json` targets the `explain` block, and it is never gated through `rules.evaluate_diagnostic`. `index_advisor.py`'s suggestions ARE findings-worthy (an actionable recommendation), so it gets a presence-kind rule (`query_perf.suggested_column_index`) in `query-performance.json`.

### Architecture decision: rule-axis mapping for the two new collectors

`rls_policies.py` → `references/rules/security-rls.json` (finally fills the P3-placeholder empty array). `schema_checks.py` → `references/rules/maintenance.json` (schema hygiene debt, alongside dead-tuples/stale-stats/bloat).

### Architecture decision: nested EXPLAIN JSON needs no schema change

`references/report-data.schema.json`'s `diagnostic.metrics` is an unconstrained `{"type": "array"}` with no item-shape restriction. The EXPLAIN plan (itself a nested JSON tree from `FORMAT JSON`) is stored as an opaque value inside one metrics-row field (`metrics: [{"queryid": ..., "plan": {...}, "explain_unavailable": null, ...}]`). No `references/report-data.schema.json` edits are needed in this phase.

## Interfaces (shared across tasks)

```python
# scripts/lib/sql_classify.py
def parse_statement(sql: str)                      # -> AST root node, or None if unparseable/multi-statement
def has_parameters(stmt) -> bool
def referenced_relations(stmt) -> list              # -> [(schema_or_None, table), ...]
def is_analyze_safe(stmt) -> tuple                  # -> (True, None) | (False, reason: str)

# scripts/lib/index_predicate.py
def equality_columns_from_statement(stmt) -> list   # -> [("t","col"), ("col",), ...] tuple paths
def extract_equality_columns(sql: str) -> list      # parse_statement(sql) + equality_columns_from_statement

# scripts/lib/index_catalog.py
def existing_indexed_columns(conn, schema: str, table: str) -> list   # -> [(col_or_None, ...), ...] per valid index
def is_covered(existing: list, columns: list) -> bool

# scripts/explain.py
def run(conn, caps, query_stats_diag, *, mode: str, top_n: int, analyze_top_n: int,
        statement_timeout_ms: int, lock_timeout_ms: int) -> dict   # -> diagnostic dict, scope="query"

# scripts/index_advisor.py
def run(conn, query_stats_diag, *, top_n: int) -> dict             # -> diagnostic dict, scope="table"

# scripts/collectors/rls_policies.py
def collect(conn, caps) -> dict                                    # -> diagnostic dict, scope="table"

# scripts/collectors/schema_checks.py
def collect(conn, caps) -> dict                                    # -> diagnostic dict, scope="table"
```

Existing signatures this phase depends on (unchanged, verified against current source):

```python
# scripts/collectors/base.py
def diagnostic(scope, status, metrics, *, reason=None, quality=None, collector_version="1") -> dict
def skipped(scope, reason, *, collector_version="1") -> dict
STRUCTURAL_QUALITY: dict

# scripts/lib/db.py
DEFAULT_STATEMENT_TIMEOUT_MS = 15000
DEFAULT_LOCK_TIMEOUT_MS = 3000

# scripts/collectors/query_stats.py metrics row shape (already sorted by window_total_exec_time_ms descending)
{"queryid", "query", "window_calls", "window_total_exec_time_ms", "window_mean_exec_time_ms",
 "window_stddev_exec_time_ms", "window_rows_per_call", "window_shared_blks_read",
 "window_temp_blks_read", "window_temp_blks_written"}

# scripts/capabilities.py probe(conn) -> dict includes:
{"server_version_num": int, "is_superuser": bool, "has_pg_read_all_stats": bool, "has_pg_monitor": bool,
 "track_io_timing": bool, "pg_stat_statements_track": str, "vendor": str, "managed": bool,
 "extensions": dict, "ram_bytes": int}
```

## File Structure

```
requirements-dev.txt                                MODIFY - append pglast==8.2
scripts/lib/envparse.py                              MODIFY - 5 new DbConfig fields
scripts/lib/sql_classify.py                          CREATE - pglast-based SQL classification
scripts/lib/index_predicate.py                       CREATE - equality-predicate column extraction
scripts/lib/index_catalog.py                         CREATE - existing-index coverage lookups
scripts/explain.py                                   CREATE - P4.1 EXPLAIN plan capture
scripts/index_advisor.py                             CREATE - P4.2 column-level index advisor
scripts/collectors/rls_policies.py                   CREATE - P4.3 RLS re-eval + missing-index detection
scripts/collectors/schema_checks.py                  CREATE - P4.4 missing PK / uuid PK / timestamptz
scripts/collectors/__init__.py                       MODIFY - register rls_policies, schema_checks
scripts/analyzer.py                                  MODIFY - wire explain.run + index_advisor.run
references/rules/query-performance.json              MODIFY - append query_perf.suggested_column_index
references/rules/security-rls.json                   MODIFY - replace [] with rls_policy_issue rule
references/rules/maintenance.json                    MODIFY - append maintenance.schema_hygiene_issue
SKILL.md                                              MODIFY - §5.8 confidence tiers, axis matrix row
tests/unit/test_sql_classify.py                       CREATE
tests/unit/test_index_predicate.py                    CREATE
tests/unit/test_index_catalog.py                      CREATE
tests/unit/test_explain.py                            CREATE
tests/unit/test_index_advisor.py                      CREATE
tests/unit/test_rls_policies.py                       CREATE
tests/unit/test_schema_checks.py                      CREATE
tests/unit/test_rules.py                              MODIFY - known_blocks fix + placeholder-test replace
tests/unit/test_skill_docs.py                         MODIFY - new confidence-tier assertion
```

---

### Task 1: `envparse.py` — Explain* config fields

**Files:**
- Modify: `scripts/lib/envparse.py:1-42` (full file, 42 lines)
- Test: `tests/unit/test_envparse.py` (append)

**Interfaces:**
- Produces: `DbConfig.explain_mode: str`, `.explain_top_n: int`, `.explain_analyze_top_n: int`, `.explain_statement_timeout_ms: int`, `.explain_lock_timeout_ms: int` — consumed by Task 8's `analyzer.py` wiring.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_envparse.py` (create the file with this content if it does not already exist — check first with Read; if it exists, add these functions):

```python
def test_explain_fields_default_when_absent():
    cfg = envparse.parse_env(json.dumps({
        "ServerName": "h", "CatalogName": "d", "Username": "u", "Password": "p",
    }))
    assert cfg.explain_mode == "plan"
    assert cfg.explain_top_n == 5
    assert cfg.explain_analyze_top_n == 0
    assert cfg.explain_statement_timeout_ms == 3000
    assert cfg.explain_lock_timeout_ms == 500


def test_explain_fields_parsed_when_present():
    cfg = envparse.parse_env(json.dumps({
        "ServerName": "h", "CatalogName": "d", "Username": "u", "Password": "p",
        "ExplainMode": "analyze", "ExplainTopN": 3, "ExplainAnalyzeTopN": 2,
        "ExplainStatementTimeoutMs": 1500, "ExplainLockTimeoutMs": 250,
    }))
    assert cfg.explain_mode == "analyze"
    assert cfg.explain_top_n == 3
    assert cfg.explain_analyze_top_n == 2
    assert cfg.explain_statement_timeout_ms == 1500
    assert cfg.explain_lock_timeout_ms == 250
```

If the test file does not exist yet, create it with this header before the two functions above:

```python
import json

from scripts.lib import envparse
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_envparse.py -v`
Expected: FAIL with `AttributeError: 'DbConfig' object has no attribute 'explain_mode'`

- [ ] **Step 3: Implement**

Replace `scripts/lib/envparse.py` in full:

```python
"""Parse the v3 JSON `.env` config into a typed DbConfig."""
import json
from dataclasses import dataclass, field
from pathlib import Path

_REQUIRED = ("ServerName", "CatalogName", "Username", "Password")


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
    explain_mode: str = "plan"
    explain_top_n: int = 5
    explain_analyze_top_n: int = 0
    explain_statement_timeout_ms: int = 3000
    explain_lock_timeout_ms: int = 500
    raw: dict = field(default_factory=dict)


def parse_env(source) -> DbConfig:
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    data = json.loads(text)
    missing = [k for k in _REQUIRED if k not in data or data[k] in (None, "")]
    if missing:
        raise ValueError(f".env missing required keys: {', '.join(missing)}")
    return DbConfig(
        host=str(data["ServerName"]),
        port=int(data.get("Port", 5432)),
        database=str(data["CatalogName"]),
        user=str(data["Username"]),
        password=str(data["Password"]),
        project_name=str(data.get("ProjectName", "")),
        code_path=str(data.get("CodePath", "")),
        sampling_window_seconds=int(data.get("SamplingWindowSeconds", 30)),
        explain_mode=str(data.get("ExplainMode", "plan")),
        explain_top_n=int(data.get("ExplainTopN", 5)),
        explain_analyze_top_n=int(data.get("ExplainAnalyzeTopN", 0)),
        explain_statement_timeout_ms=int(data.get("ExplainStatementTimeoutMs", 3000)),
        explain_lock_timeout_ms=int(data.get("ExplainLockTimeoutMs", 500)),
        raw=data,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_envparse.py -v`
Expected: PASS (all tests in the file, including pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/envparse.py tests/unit/test_envparse.py
git commit -m "feat(p4): add Explain* config fields to DbConfig (P4.1 config surface)"
```

---

### Task 2: `pglast` dependency + `sql_classify.py`

**Files:**
- Modify: `requirements-dev.txt:1-4` (append one line)
- Create: `scripts/lib/sql_classify.py`
- Test: `tests/unit/test_sql_classify.py`

**Interfaces:**
- Produces: `parse_statement(sql) -> AST|None`, `has_parameters(stmt) -> bool`, `referenced_relations(stmt) -> list[tuple]`, `is_analyze_safe(stmt) -> tuple[bool, str|None]` — consumed by Task 3 (`index_predicate.py`), Task 4 (`explain.py`), Task 5 (`index_advisor.py`), Task 6 (`rls_policies.py`).

- [ ] **Step 1: Add the dependency**

Append one line to `requirements-dev.txt` (after the existing 4 lines):

```
pglast==8.2
```

Install it: `pip install -r requirements-dev.txt`

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_sql_classify.py`:

```python
from scripts.lib import sql_classify


def test_parse_statement_returns_none_for_unparseable():
    assert sql_classify.parse_statement("not valid sql (((") is None


def test_parse_statement_returns_none_for_multi_statement():
    assert sql_classify.parse_statement("select 1; drop table x;") is None


def test_parse_statement_returns_none_for_empty():
    assert sql_classify.parse_statement("") is None


def test_parse_statement_returns_node_for_valid_select():
    stmt = sql_classify.parse_statement("select 1 from t where id = 5")
    assert stmt is not None


def test_has_parameters_true_for_placeholder():
    stmt = sql_classify.parse_statement("select * from t where id = $1")
    assert sql_classify.has_parameters(stmt) is True


def test_has_parameters_false_for_literal():
    stmt = sql_classify.parse_statement("select * from t where id = 5")
    assert sql_classify.has_parameters(stmt) is False


def test_has_parameters_false_for_none():
    assert sql_classify.has_parameters(None) is False


def test_referenced_relations_qualified():
    stmt = sql_classify.parse_statement("select * from public.orders")
    assert sql_classify.referenced_relations(stmt) == [("public", "orders")]


def test_referenced_relations_unqualified():
    stmt = sql_classify.parse_statement("select * from orders")
    assert sql_classify.referenced_relations(stmt) == [(None, "orders")]


def test_referenced_relations_empty_for_none():
    assert sql_classify.referenced_relations(None) == []


def test_is_analyze_safe_true_for_plain_select():
    stmt = sql_classify.parse_statement("select * from orders where id = 5")
    assert sql_classify.is_analyze_safe(stmt) == (True, None)


def test_is_analyze_safe_false_for_non_select():
    stmt = sql_classify.parse_statement("update orders set status = 'x' where id = 5")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "not_a_select"


def test_is_analyze_safe_false_for_for_update():
    stmt = sql_classify.parse_statement("select * from orders where id = 5 for update")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "locking_clause"


def test_is_analyze_safe_false_for_unsafe_function():
    stmt = sql_classify.parse_statement("select nextval('orders_id_seq')")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "unsafe_function:nextval"


def test_is_analyze_safe_false_for_unparseable():
    assert sql_classify.is_analyze_safe(None) == (False, "unparseable")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_sql_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lib.sql_classify'`

- [ ] **Step 4: Implement**

Create `scripts/lib/sql_classify.py`:

```python
"""Real-PostgreSQL-grammar SQL classification via pglast (wraps libpg_query)
-- never a regex safety gate (spec S0.A3, project rule N2 exemption: parsing
SQL text for safety classification is explicitly allowed)."""
from pglast import ast, parse_sql, visitors
from pglast.enums import A_Expr_Kind  # noqa: F401 - re-exported for index_predicate

_UNSAFE_FUNCTIONS = {
    "nextval", "setval", "currval", "lastval",
    "pg_advisory_lock", "pg_advisory_lock_shared",
    "pg_advisory_xact_lock", "pg_advisory_xact_lock_shared",
    "pg_try_advisory_lock", "pg_try_advisory_lock_shared",
    "pg_try_advisory_xact_lock", "pg_try_advisory_xact_lock_shared",
    "pg_sleep", "txid_current", "random",
}


def parse_statement(sql: str):
    """Returns the parsed AST root node for exactly one SQL statement, or
    None if `sql` fails to parse or contains anything other than exactly
    one statement (a defensive close against multi-statement injection via
    ';' -- explain.py embeds this text directly into an EXPLAIN command,
    which cannot be parameterized)."""
    if not sql:
        return None
    try:
        parsed = parse_sql(sql)
    except Exception:  # noqa: BLE001 - any parse failure means "can't classify"
        return None
    if len(parsed) != 1:
        return None
    return parsed[0].stmt


def has_parameters(stmt) -> bool:
    if stmt is None:
        return False
    finder = _ParamFinder()
    finder(stmt)
    return finder.found


class _ParamFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.found = False

    def visit_ParamRef(self, ancestors, node):
        self.found = True


def referenced_relations(stmt) -> list:
    if stmt is None:
        return []
    finder = _RelationFinder()
    finder(stmt)
    return finder.relations


class _RelationFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.relations = []

    def visit_RangeVar(self, ancestors, node):
        self.relations.append((node.schemaname, node.relname))


class _UnsafeFunctionFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.hit = None

    def visit_FuncCall(self, ancestors, node):
        if self.hit:
            return
        names = [n.sval for n in node.funcname]
        name = names[-1]
        if name in _UNSAFE_FUNCTIONS:
            self.hit = name


def is_analyze_safe(stmt) -> tuple:
    """(True, None) when ANALYZE-mode EXPLAIN is safe to run against `stmt`;
    otherwise (False, reason). A read-only transaction is NOT relied on
    here -- ANALYZE still executes the statement (e.g. nextval() runs even
    inside READ ONLY), so safety comes entirely from this parser-based
    allowlist. Foreign-table references are checked separately in
    explain.py via a catalog query (pg_foreign_table), not here."""
    if stmt is None:
        return False, "unparseable"
    if not isinstance(stmt, ast.SelectStmt):
        return False, "not_a_select"
    if stmt.lockingClause:
        return False, "locking_clause"
    finder = _UnsafeFunctionFinder()
    finder(stmt)
    if finder.hit:
        return False, f"unsafe_function:{finder.hit}"
    return True, None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_sql_classify.py -v`
Expected: PASS (14 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt scripts/lib/sql_classify.py tests/unit/test_sql_classify.py
git commit -m "feat(p4): pglast-based SQL classification — parse, params, relations, ANALYZE safety"
```

---

### Task 3: `index_predicate.py` + `index_catalog.py`

**Files:**
- Create: `scripts/lib/index_predicate.py`
- Create: `scripts/lib/index_catalog.py`
- Test: `tests/unit/test_index_predicate.py`
- Test: `tests/unit/test_index_catalog.py`

**Interfaces:**
- Consumes: `scripts.lib.sql_classify.parse_statement` (Task 2).
- Produces: `equality_columns_from_statement(stmt) -> list[tuple]`, `extract_equality_columns(sql) -> list[tuple]`, `existing_indexed_columns(conn, schema, table) -> list[tuple]`, `is_covered(existing, columns) -> bool` — consumed by Task 4 (`explain.py` does not need these), Task 5 (`index_advisor.py`), Task 6 (`rls_policies.py`).

- [ ] **Step 1: Write the failing tests for `index_predicate.py`**

Create `tests/unit/test_index_predicate.py`:

```python
from scripts.lib import index_predicate, sql_classify


def test_single_equality_column():
    stmt = sql_classify.parse_statement("select * from t where status = 'active'")
    assert index_predicate.equality_columns_from_statement(stmt) == [("status",)]


def test_qualified_equality_column():
    stmt = sql_classify.parse_statement("select * from t where t.user_id = 5")
    assert index_predicate.equality_columns_from_statement(stmt) == [("t", "user_id")]


def test_multiple_equality_columns_in_and():
    stmt = sql_classify.parse_statement("select * from t where status = 'active' and org_id = 3")
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("status",) in cols
    assert ("org_id",) in cols


def test_non_equality_operator_not_captured():
    stmt = sql_classify.parse_statement("select * from t where created_at > '2024-01-01'")
    assert index_predicate.equality_columns_from_statement(stmt) == []


def test_none_statement_returns_empty():
    assert index_predicate.equality_columns_from_statement(None) == []


def test_extract_equality_columns_parses_sql_directly():
    assert index_predicate.extract_equality_columns("select * from t where id = 1") == [("id",)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_index_predicate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lib.index_predicate'`

- [ ] **Step 3: Implement `index_predicate.py`**

Create `scripts/lib/index_predicate.py`:

```python
"""Equality-predicate extraction for the column-level index advisor (P4.2)
and RLS policy-predicate scanning (P4.3) -- both need the same WHERE/ON
equality-column walk, so the AST-walk core is split from parsing so
rls_policies.py can reuse it against an already-parsed statement/expression
without re-parsing (parse_statement rejects a bare boolean expression, which
is exactly what a policy's qual/with_check text is)."""
from pglast import ast, visitors
from pglast.enums import A_Expr_Kind

from scripts.lib import sql_classify


class _EqualityColumnFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.columns = []

    def visit_A_Expr(self, ancestors, node):
        if node.kind != A_Expr_Kind.AEXPR_OP:
            return
        names = [n.sval for n in (node.name or ())]
        if names != ["="]:
            return
        for side in (node.lexpr, node.rexpr):
            path = _column_ref_path(side)
            if path is not None:
                self.columns.append(path)


def _column_ref_path(node):
    if not isinstance(node, ast.ColumnRef):
        return None
    fields = [f.sval for f in node.fields if isinstance(f, ast.String)]
    return tuple(fields) if fields else None


def equality_columns_from_statement(stmt) -> list:
    """Walks `stmt` (or any parsed AST node/expression) for `col = ...`
    equality predicates and returns each match as a tuple path, e.g.
    ("t", "user_id") for a qualified reference or ("status",) for a bare
    column name. Returns [] for stmt=None (unparseable input)."""
    if stmt is None:
        return []
    finder = _EqualityColumnFinder()
    finder(stmt)
    return finder.columns


def extract_equality_columns(sql: str) -> list:
    stmt = sql_classify.parse_statement(sql)
    return equality_columns_from_statement(stmt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_index_predicate.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Write the tests for `index_catalog.py`**

Create `tests/unit/test_index_catalog.py`:

```python
import psycopg2
import pytest

from scripts.lib import index_catalog
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_is_covered_true_for_exact_match():
    existing = [("org_id", "status")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is True


def test_is_covered_true_for_leading_prefix():
    existing = [("org_id", "status", "created_at")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is True


def test_is_covered_false_when_not_a_prefix():
    existing = [("status", "org_id")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is False


def test_is_covered_false_when_no_indexes():
    assert index_catalog.is_covered([], ["org_id"]) is False


def test_is_covered_false_when_expression_index_blocks_prefix():
    existing = [(None, "status")]
    assert index_catalog.is_covered(existing, [None, "status"]) is False


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_existing_indexed_columns_against_live_postgres(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text, created_at timestamptz);
    CREATE INDEX ON {s}.orders (org_id, status);
    """
    with _fixtures_sql.make_schema(conn, "idxcat", ddl):
        cols = index_catalog.existing_indexed_columns(conn, "idxcat", "orders")
        assert ("id",) in cols
        assert ("org_id", "status") in cols
    conn.close()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/unit/test_index_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lib.index_catalog'`

- [ ] **Step 7: Implement `index_catalog.py`**

Create `scripts/lib/index_catalog.py`:

```python
"""Index-coverage lookups shared by index_advisor.py and rls_policies.py.

Reuses duplicate_index.py's proven i.indkey::text + Python split() idiom --
pg_index.indkey is an int2vector, not a genuine array type, so unnest()
does not apply to it directly (unlike pg_constraint.conkey, a real int[],
used by fk_missing_index.py).
"""

_INDEXES_SQL = """
SELECT i.indrelid, i.indnkeyatts, i.indkey::text AS indkey
FROM pg_index i
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = %s AND t.relname = %s AND i.indisvalid
"""

_ATTNAMES_SQL = """
SELECT attnum, attname FROM pg_attribute WHERE attrelid = %s AND attnum = ANY(%s)
"""


def existing_indexed_columns(conn, schema: str, table: str) -> list:
    """Returns one tuple of leading key-column names per valid index on
    (schema, table) -- INCLUDE columns excluded via indnkeyatts (same
    truncation as duplicate_index.py's _key_desc), expression-index
    positions (attnum 0) represented as None so they never satisfy a
    coverage check against a real column name."""
    with conn.cursor() as cur:
        cur.execute(_INDEXES_SQL, (schema, table))
        index_rows = cur.fetchall()
        if not index_rows:
            return []

        table_oid = index_rows[0][0]
        all_attnums = set()
        parsed = []
        for indrelid, indnkeyatts, indkey in index_rows:
            attnums = [int(a) for a in indkey.split()[:indnkeyatts]]
            parsed.append(attnums)
            all_attnums.update(a for a in attnums if a != 0)

        cur.execute(_ATTNAMES_SQL, (table_oid, list(all_attnums)))
        names_by_attnum = dict(cur.fetchall())

    results = []
    for attnums in parsed:
        results.append(tuple(names_by_attnum.get(a) if a != 0 else None for a in attnums))
    return results


def is_covered(existing: list, columns: list) -> bool:
    """True if `columns` (any order) is a leading-prefix subset of some
    existing index's key columns."""
    wanted = set(columns)
    for index_columns in existing:
        prefix = index_columns[: len(wanted)]
        if None in prefix:
            continue
        if set(prefix) == wanted:
            return True
    return False
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_index_catalog.py -v`
Expected: PASS (5 pure tests pass always; the 6th (`test_existing_indexed_columns_against_live_postgres`) passes if Docker is available, skips cleanly otherwise)

- [ ] **Step 9: Commit**

```bash
git add scripts/lib/index_predicate.py scripts/lib/index_catalog.py tests/unit/test_index_predicate.py tests/unit/test_index_catalog.py
git commit -m "feat(p4): equality-predicate extraction + existing-index coverage lookup"
```

---

### Task 4: `explain.py` — P4.1 EXPLAIN plan capture

**Files:**
- Create: `scripts/explain.py`
- Test: `tests/unit/test_explain.py`

**Interfaces:**
- Consumes: `scripts.lib.sql_classify.{parse_statement, has_parameters, referenced_relations, is_analyze_safe}` (Task 2); `scripts.lib.db.{DEFAULT_STATEMENT_TIMEOUT_MS, DEFAULT_LOCK_TIMEOUT_MS}` (existing); `scripts.collectors.base.{diagnostic, skipped, STRUCTURAL_QUALITY}` (existing).
- Produces: `run(conn, caps, query_stats_diag, *, mode, top_n, analyze_top_n, statement_timeout_ms, lock_timeout_ms) -> dict` — consumed by Task 8 (`analyzer.py` wiring). Each metrics row: `{"queryid", "mode", "plan", "explain_unavailable", "analyze_skipped_reason", "role", "search_path", "database"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_explain.py`:

```python
import psycopg2
import pytest

from scripts import explain
from scripts.collectors import base
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def _query_stats_diag(rows):
    return base.diagnostic("query", "ok", rows)


def test_run_returns_skipped_when_mode_off():
    diag = explain.run(None, {}, _query_stats_diag([]), mode="off", top_n=5, analyze_top_n=0,
                        statement_timeout_ms=3000, lock_timeout_ms=500)
    assert diag["status"] == "skipped"


def test_run_returns_skipped_when_query_stats_unavailable():
    diag = explain.run(None, {}, None, mode="plan", top_n=5, analyze_top_n=0,
                        statement_timeout_ms=3000, lock_timeout_ms=500)
    assert diag["status"] == "skipped"


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_ok_with_empty_query_stats_rows(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag([]),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_plan_mode_captures_plan_for_literal_query(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl1", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl1".t WHERE id = 1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        assert diag["status"] == "ok"
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["plan"] is not None
        assert row["explain_unavailable"] is None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_parameterized_query_pre_pg16_is_explicitly_unavailable(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl2", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl2".t WHERE id = $1'}]
        diag = explain.run(conn, {"server_version_num": 150000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["plan"] is None
        assert row["explain_unavailable"] == "parameterized_pre_pg16"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_parameterized_query_pg16_uses_generic_plan(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl3", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl3".t WHERE id = $1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="plan", top_n=5, analyze_top_n=0,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["explain_unavailable"] is None
        assert row["plan"] is not None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_analyze_mode_runs_analyze_for_safe_select_within_analyze_top_n(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl4", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl4".t WHERE id = 1'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=1,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "analyze"
        assert row["analyze_skipped_reason"] is None
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_analyze_mode_skips_analyze_for_for_update(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl5", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl5".t WHERE id = 1 FOR UPDATE'}]
        diag = explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                            mode="analyze", top_n=5, analyze_top_n=1,
                            statement_timeout_ms=3000, lock_timeout_ms=500)
        row = diag["metrics"][0]
        assert row["mode"] == "plan"
        assert row["analyze_skipped_reason"] == "locking_clause"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_restores_default_timeouts_after_explain(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.t (id serial PRIMARY KEY, v int)"
    with _fixtures_sql.make_schema(conn, "expl6", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "expl6".t WHERE id = 1'}]
        explain.run(conn, {"server_version_num": 160000}, _query_stats_diag(rows),
                    mode="plan", top_n=5, analyze_top_n=0,
                    statement_timeout_ms=111, lock_timeout_ms=22)
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "15s"
            cur.execute("SHOW lock_timeout")
            assert cur.fetchone()[0] == "3s"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_explain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.explain'`

- [ ] **Step 3: Implement**

Create `scripts/explain.py`:

```python
"""P4.1 — EXPLAIN plan-only by default (spec S0.A3/S10 P4.1).

Reads the top-N slow queries already ranked by
scripts/collectors/query_stats.py (sorted by window_total_exec_time_ms
descending, the sampler's own order), classifies each via
scripts.lib.sql_classify (a real PG parser -- never a regex safety gate),
and captures an EXPLAIN plan. ANALYZE only runs when explicitly opted in
(ExplainMode=analyze) AND the statement is within the first
ExplainAnalyzeTopN rows AND sql_classify.is_analyze_safe() confirms it.

A read-only transaction + ROLLBACK is explicitly NOT relied on for ANALYZE
safety -- ANALYZE still executes the statement (e.g. nextval() is permitted
even inside a READ ONLY transaction). Safety instead comes from the
parser-based allowlist plus the tightened statement_timeout/lock_timeout
this module sets before every EXPLAIN and always restores afterward (even
on failure).
"""
from scripts.collectors import base
from scripts.lib import db, sql_classify

_GENERIC_PLAN_MIN_VERSION = 160000

_FOREIGN_TABLE_SQL = """
SELECT 1
FROM pg_foreign_table ft
JOIN pg_class c ON c.oid = ft.ftrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (n.nspname, c.relname) IN %s
LIMIT 1
"""


def _set_timeouts(conn, statement_timeout_ms, lock_timeout_ms):
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (int(statement_timeout_ms),))
        cur.execute("SET lock_timeout = %s", (int(lock_timeout_ms),))


def _restore_default_timeouts(conn):
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (db.DEFAULT_STATEMENT_TIMEOUT_MS,))
        cur.execute("SET lock_timeout = %s", (db.DEFAULT_LOCK_TIMEOUT_MS,))


def _current_context(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_setting('search_path'), current_database()")
        role, search_path, database = cur.fetchone()
    return {"role": role, "search_path": search_path, "database": database}


def _references_foreign_table(conn, stmt):
    relations = sql_classify.referenced_relations(stmt)
    if not relations:
        return False
    pairs = tuple((schema or "public", table) for schema, table in relations)
    with conn.cursor() as cur:
        cur.execute(_FOREIGN_TABLE_SQL, (pairs,))
        return cur.fetchone() is not None


def _run_explain(conn, sql, *, analyze):
    verb = "EXPLAIN (ANALYZE, FORMAT JSON)" if analyze else "EXPLAIN (FORMAT JSON)"
    with conn.cursor() as cur:
        cur.execute(f"{verb} {sql}")
        return cur.fetchone()[0][0]


def _run_generic_plan(conn, sql):
    # PG16+ direct syntax -- no PREPARE/EXECUTE/DEALLOCATE needed.
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (GENERIC_PLAN, FORMAT JSON) {sql}")
        return cur.fetchone()[0][0]


def _explain_row(conn, row, *, index, mode, analyze_top_n, server_version_num):
    sql = row.get("query")
    out = {"queryid": row.get("queryid"), "mode": "plan",
           "plan": None, "explain_unavailable": None, "analyze_skipped_reason": None}
    if not sql:
        out["explain_unavailable"] = "empty_query_text"
        return out

    stmt = sql_classify.parse_statement(sql)
    if stmt is None:
        out["explain_unavailable"] = "unparseable"
        return out

    has_params = sql_classify.has_parameters(stmt)
    if has_params and server_version_num < _GENERIC_PLAN_MIN_VERSION:
        out["explain_unavailable"] = "parameterized_pre_pg16"
        return out

    try:
        if has_params:
            out["plan"] = _run_generic_plan(conn, sql)  # GENERIC_PLAN never ANALYZEs (spec S0.A3/B1)
            return out

        wants_analyze = mode == "analyze" and index < analyze_top_n
        if wants_analyze:
            safe, reason = sql_classify.is_analyze_safe(stmt)
            if safe and _references_foreign_table(conn, stmt):
                safe, reason = False, "foreign_table"
            if not safe:
                out["analyze_skipped_reason"] = reason
                wants_analyze = False
        out["plan"] = _run_explain(conn, sql, analyze=wants_analyze)
        out["mode"] = "analyze" if wants_analyze else "plan"
    except Exception as exc:  # noqa: BLE001 - one query's EXPLAIN failing must not abort the batch
        out["explain_unavailable"] = f"explain_failed:{type(exc).__name__}"
    return out


def run(conn, caps, query_stats_diag, *, mode: str, top_n: int, analyze_top_n: int,
        statement_timeout_ms: int, lock_timeout_ms: int) -> dict:
    if mode == "off":
        return base.skipped("query", "ExplainMode=off")
    if query_stats_diag is None or query_stats_diag.get("status") not in ("ok", "partial"):
        return base.skipped("query", "query_stats diagnostic unavailable")

    rows = query_stats_diag.get("metrics", [])[:top_n]
    if not rows:
        return base.diagnostic("query", "ok", [])

    server_version_num = caps.get("server_version_num", 0)
    quality = dict(query_stats_diag.get("quality") or base.STRUCTURAL_QUALITY)
    context = _current_context(conn)

    _set_timeouts(conn, statement_timeout_ms, lock_timeout_ms)
    try:
        metrics = [
            {**_explain_row(conn, row, index=i, mode=mode, analyze_top_n=analyze_top_n,
                             server_version_num=server_version_num), **context}
            for i, row in enumerate(rows)
        ]
    finally:
        _restore_default_timeouts(conn)

    return base.diagnostic("query", "ok", metrics, quality=quality)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_explain.py -v`
Expected: PASS (2 pure tests pass always; the remaining 7 pass if Docker is available, skip cleanly otherwise)

- [ ] **Step 5: Commit**

```bash
git add scripts/explain.py tests/unit/test_explain.py
git commit -m "feat(p4): EXPLAIN plan capture — plan-mode default, opt-in ANALYZE allowlist, PG16 GENERIC_PLAN"
```

---

### Task 5: `index_advisor.py` — P4.2 column-level index advisor

**Files:**
- Create: `scripts/index_advisor.py`
- Modify: `references/rules/query-performance.json:1-27` (append 3rd rule)
- Modify: `tests/unit/test_rules.py:172-180` (`known_blocks` fix)
- Test: `tests/unit/test_index_advisor.py`

**Interfaces:**
- Consumes: `scripts.lib.sql_classify.{parse_statement, referenced_relations}` (Task 2); `scripts.lib.index_predicate.equality_columns_from_statement` (Task 3); `scripts.lib.index_catalog.{existing_indexed_columns, is_covered}` (Task 3).
- Produces: `run(conn, query_stats_diag, *, top_n) -> dict` — consumed by Task 8 (`analyzer.py` wiring). Each metrics row: `{"schema", "table", "suggested_columns", "suggested_ddl", "queryid"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_index_advisor.py`:

```python
import psycopg2
import pytest

from scripts import index_advisor
from scripts.collectors import base
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def _query_stats_diag(rows):
    return base.diagnostic("query", "ok", rows)


def test_run_returns_skipped_when_query_stats_unavailable():
    diag = index_advisor.run(None, None, top_n=5)
    assert diag["status"] == "skipped"


def test_run_ok_empty_when_no_rows():
    diag = index_advisor.run(None, _query_stats_diag([]), top_n=5)
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_suggests_index_for_uncovered_equality_predicate(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text)"
    with _fixtures_sql.make_schema(conn, "advtest", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "advtest".orders WHERE org_id = 5'}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["status"] == "ok"
        assert len(diag["metrics"]) == 1
        suggestion = diag["metrics"][0]
        assert suggestion["schema"] == "advtest"
        assert suggestion["table"] == "orders"
        assert suggestion["suggested_columns"] == ["org_id"]
        assert "CREATE INDEX" in suggestion["suggested_ddl"]
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_skips_when_index_already_exists(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text);
    CREATE INDEX ON {s}.orders (org_id);
    """
    with _fixtures_sql.make_schema(conn, "advtest2", ddl):
        rows = [{"queryid": "1", "query": 'SELECT * FROM "advtest2".orders WHERE org_id = 5'}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["metrics"] == []
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_skips_multi_table_queries(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int);
    CREATE TABLE {s}.orgs (id serial PRIMARY KEY, name text);
    """
    with _fixtures_sql.make_schema(conn, "advtest3", ddl):
        rows = [{"queryid": "1",
                  "query": 'SELECT * FROM "advtest3".orders o JOIN "advtest3".orgs g ON o.org_id = g.id WHERE g.name = \'x\''}]
        diag = index_advisor.run(conn, _query_stats_diag(rows), top_n=5)
        assert diag["metrics"] == []
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_index_advisor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.index_advisor'`

- [ ] **Step 3: Implement**

Create `scripts/index_advisor.py`:

```python
"""P4.2 -- column-level index advisor. For each of the top-N slow queries
(already ranked by query_stats.py, descending window_total_exec_time_ms),
suggests a composite index over its equality-predicate columns when no
existing index already covers them. Only resolves single-table queries --
a query referencing more than one distinct (schema, table) pair is skipped
rather than guessed at."""
from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify


def _suggest(schema, table, columns):
    quoted_cols = ", ".join(columns)
    ddl = (f"-- needs-review: CREATE INDEX ON {schema}.{table} ({quoted_cols});"
           f" verify column order and check for an existing partial/covering index first")
    return {"schema": schema, "table": table, "suggested_columns": columns, "suggested_ddl": ddl}


def run(conn, query_stats_diag, *, top_n: int) -> dict:
    if query_stats_diag is None or query_stats_diag.get("status") not in ("ok", "partial"):
        return base.skipped("table", "query_stats diagnostic unavailable")

    rows = query_stats_diag.get("metrics", [])[:top_n]
    quality = dict(query_stats_diag.get("quality") or base.STRUCTURAL_QUALITY)

    seen = set()
    metrics = []
    for row in rows:
        sql = row.get("query")
        if not sql:
            continue
        stmt = sql_classify.parse_statement(sql)
        if stmt is None:
            continue

        relations = sql_classify.referenced_relations(stmt)
        distinct_tables = {(schema or "public", table) for schema, table in relations}
        if len(distinct_tables) != 1:
            continue
        (schema, table) = next(iter(distinct_tables))

        columns = sorted({path[-1] for path in index_predicate.equality_columns_from_statement(stmt)})
        if not columns:
            continue

        key = (schema, table, tuple(columns))
        if key in seen:
            continue
        seen.add(key)

        existing = index_catalog.existing_indexed_columns(conn, schema, table)
        if index_catalog.is_covered(existing, columns):
            continue

        suggestion = _suggest(schema, table, columns)
        suggestion["queryid"] = row.get("queryid")
        metrics.append(suggestion)

    return base.diagnostic("table", "ok", metrics, quality=quality)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_index_advisor.py -v`
Expected: PASS (2 pure tests pass always; the remaining 3 pass if Docker is available, skip cleanly otherwise)

- [ ] **Step 5: Add the rule to `query-performance.json`**

Read `references/rules/query-performance.json` first, then replace its full contents (2 existing rules + 1 new):

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
  },
  {
    "finding_id": "query_perf.suggested_column_index",
    "title": "Gợi ý index cấp cột cho truy vấn chậm",
    "severity": "notice",
    "kind": "presence",
    "block": "index_advisor",
    "assessment": "yellow",
    "row_identity_fields": ["schema", "table", "queryid"],
    "confidence": "heuristic"
  }
]
```

- [ ] **Step 6: Write the validation test for the new rule**

Rules are data (`references/rules/*.json`), not code — this test validates the JSON added in Step 5 rather than driving a code change, so there is no red state to observe first (`rules.load_catalog()` reads the file directly; Step 5 already landed it). Append to `tests/unit/test_rules_query_performance.py`:

```python
def test_suggested_column_index_fires_yellow():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "orders", "suggested_columns": ["org_id"],
                         "suggested_ddl": "-- needs-review: CREATE INDEX ...", "queryid": "1"}]}
    findings = rules.evaluate_diagnostic("index_advisor", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == "query_perf.suggested_column_index:public:orders:1"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/unit/test_rules_query_performance.py -v`
Expected: PASS (5 tests: 4 existing + 1 new)

- [ ] **Step 8: Fix `test_rules.py`'s `known_blocks` set**

In `tests/unit/test_rules.py`, change line 177 from:

```python
    known_blocks = set(COLLECTORS)
```

to:

```python
    known_blocks = set(COLLECTORS) | {"index_advisor"}
```

(`explain` is deliberately NOT added here — it has no rule-catalog entry, per the Architecture Decision above, so `test_every_rule_block_is_a_real_collector` never needs to know about it.)

- [ ] **Step 9: Run the full rules test suite to verify it passes**

Run: `pytest tests/unit/test_rules.py tests/unit/test_rules_query_performance.py -v`
Expected: PASS (all tests)

- [ ] **Step 10: Commit**

```bash
git add scripts/index_advisor.py tests/unit/test_index_advisor.py references/rules/query-performance.json tests/unit/test_rules_query_performance.py tests/unit/test_rules.py
git commit -m "feat(p4): column-level index advisor + query_perf.suggested_column_index rule"
```

---

### Task 6: `rls_policies.py` — P4.3 RLS re-eval + missing-index detection

**Files:**
- Create: `scripts/collectors/rls_policies.py`
- Modify: `scripts/collectors/__init__.py:75-77` (register `rls_policies`)
- Modify: `references/rules/security-rls.json:1` (replace `[]` with the new rule)
- Modify: `tests/unit/test_rules.py:183-187` (replace the placeholder test)
- Test: `tests/unit/test_rls_policies.py`

**Interfaces:**
- Consumes: `scripts.lib.sql_classify.parse_statement` (Task 2); `scripts.lib.index_predicate.equality_columns_from_statement` (Task 3); `scripts.lib.index_catalog.{existing_indexed_columns, is_covered}` (Task 3).
- Produces: `collect(conn, caps) -> dict`, registered in `COLLECTORS["rls_policies"]` — consumed by `run_collectors` (existing, unchanged). Each metrics row: `{"schema", "table", "policy", "clause", "issue", "function", "column"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rls_policies.py`:

```python
import psycopg2
import pytest

from scripts.collectors.rls_policies import collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_ok_empty_when_no_policies(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_flags_unwrapped_auth_uid(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes USING (owner = auth.uid());
    """
    with _fixtures_sql.make_schema(conn, "rls1", ddl):
        diag = collect(conn, {})
        assert diag["status"] == "ok"
        issues = {(r["issue"], r["function"]) for r in diag["metrics"]}
        assert ("unwrapped_reeval_call", "auth.uid") in issues
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_does_not_flag_wrapped_auth_uid(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$ SELECT NULL::uuid $$ LANGUAGE sql;
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, owner uuid);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_owner_only ON {s}.notes USING (owner = (select auth.uid()));
    """
    with _fixtures_sql.make_schema(conn, "rls2", ddl):
        diag = collect(conn, {})
        issues = {r["issue"] for r in diag["metrics"] if r["issue"] == "unwrapped_reeval_call"}
        assert issues == set()
    with conn.cursor() as cur:
        cur.execute("DROP FUNCTION IF EXISTS auth.uid() CASCADE")
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_flags_missing_supporting_index(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.notes (id serial PRIMARY KEY, org_id int);
    ALTER TABLE {s}.notes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY notes_org_only ON {s}.notes USING (org_id = 5);
    """
    with _fixtures_sql.make_schema(conn, "rls3", ddl):
        diag = collect(conn, {})
        rows = [r for r in diag["metrics"] if r["issue"] == "missing_supporting_index"]
        assert len(rows) == 1
        assert rows[0]["column"] == "org_id"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rls_policies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.rls_policies'`

- [ ] **Step 3: Implement**

Create `scripts/collectors/rls_policies.py`:

```python
"""P4.3 -- RLS policy predicate scanning: unwrapped auth.uid()/current_setting()
re-evaluation-per-row trap (the well-known Postgres/Supabase RLS perf trap),
plus missing-index detection on policy equality predicates. Always runs
(no RLS/Supabase capability gate) -- an empty pg_policies result is a
healthy `ok` state, same pattern as P2's replication.py and blocking.py.
"""
from pglast import ast, visitors

from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify

_POLICIES_SQL = """
SELECT schemaname, tablename, policyname, cmd, qual, with_check
FROM pg_policies
ORDER BY schemaname, tablename, policyname
"""

_FLAGGED_AUTH_FUNCS = {"uid", "role", "jwt"}
_FLAGGED_SETTING_FUNC = "current_setting"


class _UnwrappedCallFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.calls = []

    def visit_FuncCall(self, ancestors, node):
        if ast.SubLink in ancestors:
            return
        names = [n.sval for n in node.funcname]
        name = ".".join(names)
        if len(names) == 2 and names[0] == "auth" and names[1] in _FLAGGED_AUTH_FUNCS:
            self.calls.append(name)
        elif len(names) == 1 and names[0] == _FLAGGED_SETTING_FUNC:
            self.calls.append(name)


def _unwrapped_calls(stmt):
    finder = _UnwrappedCallFinder()
    finder(stmt)
    return finder.calls


def _predicate_rows(conn, schema, table, policy, clause_name, expr_text):
    if not expr_text:
        return []
    stmt = sql_classify.parse_statement(f"SELECT {expr_text}")
    if stmt is None:
        return []

    rows = []
    for fn in _unwrapped_calls(stmt):
        rows.append({"schema": schema, "table": table, "policy": policy, "clause": clause_name,
                     "issue": "unwrapped_reeval_call", "function": fn, "column": None})

    columns = [path[-1] for path in index_predicate.equality_columns_from_statement(stmt)]
    if columns:
        existing = index_catalog.existing_indexed_columns(conn, schema, table)
        if not index_catalog.is_covered(existing, columns):
            rows.append({"schema": schema, "table": table, "policy": policy, "clause": clause_name,
                         "issue": "missing_supporting_index", "function": None,
                         "column": ",".join(sorted(set(columns)))})
    return rows


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_POLICIES_SQL)
        policies = cur.fetchall()

    metrics = []
    for schema, table, policy, cmd, qual, with_check in policies:
        metrics.extend(_predicate_rows(conn, schema, table, policy, "qual", qual))
        metrics.extend(_predicate_rows(conn, schema, table, policy, "with_check", with_check))

    return base.diagnostic("table", "ok", metrics)
```

- [ ] **Step 4: Register the collector**

In `scripts/collectors/__init__.py`, insert after line 77 (`COLLECTORS["stat_io"] = stat_io.collect`) and before the blank line preceding `def run_collectors(...)`:

```python

from scripts.collectors import rls_policies

COLLECTORS["rls_policies"] = rls_policies.collect
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_rls_policies.py -v`
Expected: PASS (all 4 tests pass if Docker is available, skip cleanly otherwise)

- [ ] **Step 6: Fill in the `security-rls.json` rule catalog**

Replace `references/rules/security-rls.json` in full (currently `[]`):

```json
[
  {
    "finding_id": "security_rls.rls_policy_issue",
    "title": "Vấn đề chính sách Row Level Security",
    "severity": "warning",
    "kind": "presence",
    "block": "rls_policies",
    "assessment": "yellow",
    "row_identity_fields": ["schema", "table", "policy", "clause", "issue", "function", "column"],
    "confidence": "measured"
  }
]
```

- [ ] **Step 7: Replace the P3 placeholder test in `test_rules.py`**

In `tests/unit/test_rules.py`, replace the function `test_security_rls_is_an_intentional_empty_placeholder` (lines 183-187):

```python
def test_security_rls_is_an_intentional_empty_placeholder():
    # No P0-P2 collector inspects Row Level Security policies (that's P4.3).
    # This axis is deliberately empty in P3, not a forgotten TODO.
    catalog = rules.load_catalog()
    assert catalog["security-rls"] == []
```

with:

```python
def test_security_rls_has_the_p4_rls_policy_rule():
    catalog = rules.load_catalog()
    ids = {r["finding_id"] for r in catalog["security-rls"]}
    assert ids == {"security_rls.rls_policy_issue"}
```

- [ ] **Step 8: Write the rule-evaluation test**

Create `tests/unit/test_rules_security_rls.py`:

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


def test_rls_policy_issue_fires_yellow():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "notes", "policy": "notes_owner_only",
                         "clause": "qual", "issue": "unwrapped_reeval_call",
                         "function": "auth.uid", "column": None}]}
    findings = rules.evaluate_diagnostic("rls_policies", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == \
        "security_rls.rls_policy_issue:public:notes:notes_owner_only:qual:unwrapped_reeval_call:auth.uid"
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/unit/test_rules.py tests/unit/test_rules_security_rls.py -v`
Expected: PASS (all tests)

- [ ] **Step 10: Commit**

```bash
git add scripts/collectors/rls_policies.py scripts/collectors/__init__.py references/rules/security-rls.json tests/unit/test_rls_policies.py tests/unit/test_rules.py tests/unit/test_rules_security_rls.py
git commit -m "feat(p4): RLS policy re-eval + missing-index detection, fills security-rls axis"
```

---

### Task 7: `schema_checks.py` — P4.4 missing PK / oversized UUIDv4 PK / timestamptz hygiene

**Files:**
- Create: `scripts/collectors/schema_checks.py`
- Modify: `scripts/collectors/__init__.py` (register `schema_checks`, after the Task 6 insertion)
- Modify: `references/rules/maintenance.json` (append a 6th rule)
- Test: `tests/unit/test_schema_checks.py`

**Interfaces:**
- Consumes: nothing from prior P4 tasks — this collector is self-contained, querying `pg_class`/`pg_constraint`/`pg_attribute` directly.
- Produces: `collect(conn, caps) -> dict`, registered in `COLLECTORS["schema_checks"]`. Each metrics row: `{"schema", "table", "issue", "column", "row_estimate"}` where `issue` is one of `"missing_primary_key"`, `"oversized_uuid_pk"`, `"timestamp_without_timezone"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_schema_checks.py`:

```python
import psycopg2
import pytest

from scripts.collectors import schema_checks
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_missing_primary_key_fires(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.events (id int, payload text);"
    with _fixtures_sql.make_schema(conn, "sc1", ddl) as schema:
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "missing_primary_key"]
        assert len(rows) == 1
        assert rows[0]["table"] == "events"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_oversized_uuid_v4_pk_fires_on_large_table(pg_dsn, monkeypatch):
    monkeypatch.setattr(schema_checks, "_LARGE_TABLE_ROW_THRESHOLD", 2)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.big (id uuid PRIMARY KEY DEFAULT gen_random_uuid());"
    with _fixtures_sql.make_schema(conn, "sc2", ddl) as schema:
        with conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'INSERT INTO "{schema}".big DEFAULT VALUES')
            cur.execute(f'ANALYZE "{schema}".big')
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "oversized_uuid_pk"]
        assert len(rows) == 1
        assert rows[0]["column"] == "id"
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_uuid_v7_pk_does_not_fire(pg_dsn, monkeypatch):
    monkeypatch.setattr(schema_checks, "_LARGE_TABLE_ROW_THRESHOLD", 2)
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.big (id uuid PRIMARY KEY);"
    with _fixtures_sql.make_schema(conn, "sc3", ddl) as schema:
        with conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{schema}".big VALUES '
                        "('11111111-1111-7111-8111-111111111111'), "
                        "('22222222-2222-7222-8222-222222222222'), "
                        "('33333333-3333-7333-8333-333333333333')")
            cur.execute(f'ANALYZE "{schema}".big')
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "oversized_uuid_pk"]
        assert rows == []
    conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_timestamp_without_timezone_fires(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = "CREATE TABLE {s}.logs (id serial PRIMARY KEY, created_at timestamp);"
    with _fixtures_sql.make_schema(conn, "sc4", ddl) as schema:
        diag = schema_checks.collect(conn, {})
        rows = [r for r in diag["metrics"]
                if r["schema"] == schema and r["issue"] == "timestamp_without_timezone"]
        assert len(rows) == 1
        assert rows[0]["column"] == "created_at"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_schema_checks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collectors.schema_checks'`

- [ ] **Step 3: Implement**

Create `scripts/collectors/schema_checks.py`:

```python
"""P4.4 -- schema hygiene checks: missing primary key, UUIDv4 used as the
primary key on a large table (random insertion order fragments the PK
b-tree; UUIDv7 does not have this problem and is not flagged), and
`timestamp without time zone` columns. Always runs; an empty result is a
healthy `ok` state.
"""
from psycopg2 import sql

from scripts.collectors import base

_LARGE_TABLE_ROW_THRESHOLD = 1_000_000
_UUID_SAMPLE_SIZE = 100
_UUID_V4_MAJORITY_RATIO = 0.5

_TABLES_SQL = """
SELECT n.nspname AS schema, c.relname AS table, c.reltuples::float8 AS row_estimate,
       EXISTS (
           SELECT 1 FROM pg_constraint con
           WHERE con.conrelid = c.oid AND con.contype = 'p'
       ) AS has_pk
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY n.nspname, c.relname
"""

_PK_COLUMN_TYPE_SQL = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS type
FROM pg_constraint con
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
WHERE con.conrelid = %s::regclass AND con.contype = 'p'
ORDER BY a.attnum
"""

_TIMESTAMP_COLUMNS_SQL = """
SELECT a.attname
FROM pg_attribute a
WHERE a.attrelid = %s::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND format_type(a.atttypid, a.atttypmod) = 'timestamp without time zone'
ORDER BY a.attnum
"""


def _is_confirmed_large(row_estimate):
    return row_estimate is not None and row_estimate >= _LARGE_TABLE_ROW_THRESHOLD


def _sample_uuid_v4_ratio(conn, schema, table, column):
    query = sql.SQL(
        "SELECT substring({col}::text from 15 for 1) FROM {tbl} WHERE {col} IS NOT NULL LIMIT %s"
    ).format(col=sql.Identifier(column), tbl=sql.Identifier(schema, table))
    with conn.cursor() as cur:
        cur.execute(query, (_UUID_SAMPLE_SIZE,))
        rows = cur.fetchall()
    if not rows:
        return None
    v4_count = sum(1 for (version_char,) in rows if version_char == "4")
    return v4_count / len(rows)


def _pk_check(conn, schema, table, row_estimate, has_pk):
    if not has_pk:
        return [{"schema": schema, "table": table, "issue": "missing_primary_key",
                 "column": None, "row_estimate": row_estimate}]
    if not _is_confirmed_large(row_estimate):
        return []

    with conn.cursor() as cur:
        cur.execute(_PK_COLUMN_TYPE_SQL, (f'"{schema}"."{table}"',))
        pk_columns = cur.fetchall()

    rows = []
    for col, coltype in pk_columns:
        if coltype != "uuid":
            continue
        ratio = _sample_uuid_v4_ratio(conn, schema, table, col)
        if ratio is not None and ratio > _UUID_V4_MAJORITY_RATIO:
            rows.append({"schema": schema, "table": table, "issue": "oversized_uuid_pk",
                         "column": col, "row_estimate": row_estimate})
    return rows


def _timestamp_check(conn, schema, table, row_estimate):
    with conn.cursor() as cur:
        cur.execute(_TIMESTAMP_COLUMNS_SQL, (f'"{schema}"."{table}"',))
        cols = cur.fetchall()
    return [{"schema": schema, "table": table, "issue": "timestamp_without_timezone",
             "column": col, "row_estimate": row_estimate} for (col,) in cols]


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_TABLES_SQL)
        tables = cur.fetchall()

    metrics = []
    for schema, table, row_estimate, has_pk in tables:
        metrics.extend(_pk_check(conn, schema, table, row_estimate, has_pk))
        metrics.extend(_timestamp_check(conn, schema, table, row_estimate))

    return base.diagnostic("table", "ok", metrics)
```

`f'"{schema}"."{table}"'` for the `::regclass` cast parameters is safe here because `schema`/`table` come from `pg_namespace`/`pg_class` catalog rows (Step 1's `_TABLES_SQL`), never from user input — same trust boundary already relied on throughout the codebase (e.g. `duplicate_index.py`, `stale_stats.py` do the same for their own per-table follow-up queries).

- [ ] **Step 4: Register the collector**

In `scripts/collectors/__init__.py`, immediately after the Task 6 insertion:

```python

from scripts.collectors import schema_checks

COLLECTORS["schema_checks"] = schema_checks.collect
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_schema_checks.py -v`
Expected: PASS (all 4 tests pass if Docker is available, skip cleanly otherwise)

- [ ] **Step 6: Append the maintenance rule**

In `references/rules/maintenance.json`, add a 6th rule after `maintenance.fk_missing_index` (keep all 5 existing rules verbatim, only add a trailing comma after the `fk_missing_index` object's closing `}` and insert this before the final `]`):

```json
  {
    "finding_id": "maintenance.schema_hygiene_issue",
    "title": "Vấn đề schema hygiene (thiếu PK, UUID PK trên bảng lớn, hoặc timestamp không có timezone)",
    "severity": "notice",
    "kind": "presence",
    "block": "schema_checks",
    "assessment": "yellow",
    "row_identity_fields": ["schema", "table", "issue", "column"],
    "confidence": "measured"
  }
```

- [ ] **Step 7: Write the rule-evaluation test**

Append to `tests/unit/test_rules_maintenance.py`:

```python
def test_schema_hygiene_issue_fires_yellow_for_missing_pk():
    diag = {"status": "ok", "quality": _quality(),
            "metrics": [{"schema": "public", "table": "events", "issue": "missing_primary_key",
                         "column": None, "row_estimate": 10.0}]}
    findings = rules.evaluate_diagnostic("schema_checks", diag, _rules_by_block())
    assert len(findings) == 1
    assert findings[0]["assessment"] == "yellow"
    assert findings[0]["finding_id"] == "maintenance.schema_hygiene_issue:public:events:missing_primary_key"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_schema_checks.py tests/unit/test_rules_maintenance.py -v`
Expected: PASS (all tests)

- [ ] **Step 9: Commit**

```bash
git add scripts/collectors/schema_checks.py scripts/collectors/__init__.py references/rules/maintenance.json tests/unit/test_schema_checks.py tests/unit/test_rules_maintenance.py
git commit -m "feat(p4): schema hygiene checks (missing PK, oversized UUIDv4 PK, timestamptz)"
```

---

### Task 8: wire `explain.run` + `index_advisor.run` into `analyzer._analyze_target`

**Files:**
- Modify: `scripts/analyzer.py:9` (imports), `scripts/analyzer.py:90-96` (new isolated calls)
- Test: `tests/unit/test_analyzer.py` (append)

**Interfaces:**
- Consumes: `scripts.explain.run(conn, caps, query_stats_diag, *, mode, top_n, analyze_top_n, statement_timeout_ms, lock_timeout_ms)` (Task 4); `scripts.index_advisor.run(conn, query_stats_diag, *, top_n)` (Task 5); `scripts.collectors.base.diagnostic(scope, status, metrics, *, reason=None, quality=None, collector_version="1")` (existing); `cfg.explain_mode`/`cfg.explain_top_n`/`cfg.explain_analyze_top_n`/`cfg.explain_statement_timeout_ms`/`cfg.explain_lock_timeout_ms` (Task 1).
- Produces: `target["diagnostics"]["explain"]` and `target["diagnostics"]["index_advisor"]`, populated for every target using the same per-step isolation pattern already used for the sampler and `rules.evaluate_target` — a failure in either call degrades to an `error` diagnostic for that one block only, never aborts the target or corrupts unrelated diagnostics.

The current `scripts/analyzer.py` (verified this task, full file):

```python
"""Orchestrate per-target collection into a schema-valid report_data.json."""
import concurrent.futures
import re
import time
import uuid
import warnings
from datetime import datetime, timezone

from scripts import capabilities, collectors, rules, sampler
from scripts.lib import db, invariants, schema
from scripts.lib.envparse import DbConfig

TOOL_VERSION = "4.0.0"

_MAX_WORKERS = 8
_LATENCY_WARNING_RATIO = 0.8  # elapsed > 80% of the fully-serial sum -> parallelism isn't bounding runtime


def _check_latency_budget(targets: list, elapsed_seconds: float) -> None:
    """Spec §0.B4: warn if multi-target sampling isn't actually bounded —
    i.e. total elapsed time is suspiciously close to what a fully serial
    N x window_seconds run would take.
    """
    # Known gap: total_window only accounts for pg_stat_statements sampling —
    # it does not include wait_events' fixed per-target sampling cost (see wait_events.py).
    total_window = sum((t.get("sampling") or {}).get("window_seconds", 0) for t in targets)
    if len(targets) > 1 and total_window > 0 and elapsed_seconds > total_window * _LATENCY_WARNING_RATIO:
        warnings.warn(
            f"multi-target sampling took {elapsed_seconds:.1f}s for {len(targets)} targets "
            f"(sum of window_seconds={total_window}s) — runtime is not bounded, check concurrency",
            RuntimeWarning,
        )

# libpq embeds the RESOLVED address in connection errors, e.g.
#   connection to server at "db.prod.internal" (10.20.30.40), port 5432 failed
# so scrubbing cfg.host alone still leaks the real IP — strip address literals too.
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
_IPV6_RE = re.compile(r"(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scrub(message: str, cfg: DbConfig) -> str:
    out = message
    for secret in (cfg.password, cfg.host, cfg.user):
        if secret:
            out = out.replace(secret, "«redacted»")
    out = _IPV4_RE.sub("«addr»", out)
    out = _IPV6_RE.sub("«addr»", out)
    return out


def _collection_status(diagnostics: dict) -> str:
    if any(d.get("status") == "error" for d in diagnostics.values()):
        return "partial"
    return "ok"


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
            target["capabilities"]["configured_pool_size"] = cfg.raw.get("PoolSize")
            pgss = target["capabilities"].get("extensions", {}).get("pg_stat_statements")
            sampling_result = None
            if pgss:
                try:
                    sampling_result = sampler.sample_pg_stat_statements_window(
                        conn, pgss["schema"], cfg.sampling_window_seconds)
                    target["sampling"] = {
                        "window_seconds": sampling_result["window_seconds"],
                        "sample1_at": sampling_result["sample1_at"],
                        "sample2_at": sampling_result["sample2_at"],
                        "reset_detected": sampling_result["reset_detected"],
                    }
                except Exception:  # noqa: BLE001 - isolate sampler failure from other collectors
                    sampling_result = None
            target["diagnostics"] = collectors.run_collectors(
                conn, target["capabilities"], sampling=sampling_result)
            try:
                rules.evaluate_target(target)
            except Exception:  # noqa: BLE001 - isolate rule-evaluation failure from collection status
                pass
            target["collection_status"] = _collection_status(target["diagnostics"])
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - isolate per-target failure
        target["collection_status"] = "error"
        target["error"] = _scrub(str(exc), cfg)
    return target


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
    violations = invariants.check_confidence_invalidation(report)
    if violations:
        raise RuntimeError(f"B3 confidence-invalidation violated: {violations}")
    schema.validate_report(report)
    return report
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_analyzer.py`:

```python
def test_analyze_target_wires_explain_and_index_advisor_into_diagnostics(monkeypatch):
    from scripts import analyzer

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(analyzer.db, "connect", lambda cfg: FakeConn())
    monkeypatch.setattr(analyzer.capabilities, "probe", lambda conn: {"extensions": {}})
    fake_query_stats = {
        "collector_version": "1", "scope": "query", "status": "ok", "reason": None,
        "quality": {"sampling_valid": True, "reset_detected": False,
                    "insufficient_activity": False, "truncated": False},
        "metrics": [], "findings": [],
    }
    monkeypatch.setattr(analyzer.collectors, "run_collectors",
                         lambda conn, caps, sampling=None: {"query_stats": fake_query_stats})

    captured = {}

    def fake_explain_run(conn, caps, query_stats_diag, *, mode, top_n, analyze_top_n,
                          statement_timeout_ms, lock_timeout_ms):
        captured["explain_args"] = (mode, top_n, analyze_top_n, statement_timeout_ms, lock_timeout_ms)
        captured["explain_query_stats"] = query_stats_diag
        return {"collector_version": "1", "scope": "query", "status": "ok", "reason": None,
                "quality": None, "metrics": [], "findings": []}

    def fake_index_advisor_run(conn, query_stats_diag, *, top_n):
        captured["index_advisor_top_n"] = top_n
        return {"collector_version": "1", "scope": "table", "status": "ok", "reason": None,
                "quality": None, "metrics": [], "findings": []}

    monkeypatch.setattr(analyzer.explain, "run", fake_explain_run)
    monkeypatch.setattr(analyzer.index_advisor, "run", fake_index_advisor_run)

    cfg = DbConfig(host="h", port=1, database="d", user="u", password="p", project_name="p",
                   explain_mode="plan", explain_top_n=3, explain_analyze_top_n=1,
                   explain_statement_timeout_ms=3000, explain_lock_timeout_ms=500)

    target = analyzer._analyze_target(cfg)

    assert target["diagnostics"]["explain"]["status"] == "ok"
    assert target["diagnostics"]["index_advisor"]["status"] == "ok"
    assert captured["explain_args"] == ("plan", 3, 1, 3000, 500)
    assert captured["explain_query_stats"] is fake_query_stats
    assert captured["index_advisor_top_n"] == 3


def test_explain_failure_does_not_wipe_out_other_diagnostics(monkeypatch):
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
            "metrics": [{"cache_hit_ratio": 0.9}], "findings": [],
        },
    }
    monkeypatch.setattr(analyzer.collectors, "run_collectors",
                         lambda conn, caps, sampling=None: fake_diagnostics)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated explain failure")

    monkeypatch.setattr(analyzer.explain, "run", boom)
    monkeypatch.setattr(analyzer.index_advisor, "run",
                         lambda conn, query_stats_diag, *, top_n: {
                             "collector_version": "1", "scope": "table", "status": "ok",
                             "reason": None, "quality": None, "metrics": [], "findings": []})

    cfg = DbConfig(host="h", port=1, database="d", user="u", password="p", project_name="p")

    target = analyzer._analyze_target(cfg)

    assert target["diagnostics"]["explain"]["status"] == "error"
    assert target["diagnostics"]["explain"]["reason"] == "RuntimeError"
    assert target["diagnostics"]["database_stats"]["metrics"] == [{"cache_hit_ratio": 0.9}]
    assert target["diagnostics"]["index_advisor"]["status"] == "ok"
    assert target["collection_status"] == "partial"
    assert target["error"] is None


def test_index_advisor_failure_does_not_wipe_out_other_diagnostics(monkeypatch):
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
            "metrics": [{"cache_hit_ratio": 0.9}], "findings": [],
        },
    }
    monkeypatch.setattr(analyzer.collectors, "run_collectors",
                         lambda conn, caps, sampling=None: fake_diagnostics)
    monkeypatch.setattr(analyzer.explain, "run",
                         lambda conn, caps, query_stats_diag, *, mode, top_n, analyze_top_n,
                                statement_timeout_ms, lock_timeout_ms: {
                             "collector_version": "1", "scope": "query", "status": "ok",
                             "reason": None, "quality": None, "metrics": [], "findings": []})

    def boom(*args, **kwargs):
        raise RuntimeError("simulated index-advisor failure")

    monkeypatch.setattr(analyzer.index_advisor, "run", boom)

    cfg = DbConfig(host="h", port=1, database="d", user="u", password="p", project_name="p")

    target = analyzer._analyze_target(cfg)

    assert target["diagnostics"]["index_advisor"]["status"] == "error"
    assert target["diagnostics"]["index_advisor"]["reason"] == "RuntimeError"
    assert target["diagnostics"]["explain"]["status"] == "ok"
    assert target["diagnostics"]["database_stats"]["metrics"] == [{"cache_hit_ratio": 0.9}]
    assert target["collection_status"] == "partial"
    assert target["error"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_analyzer.py -v -k "explain or index_advisor"`
Expected: FAIL with `AttributeError: module 'scripts.analyzer' has no attribute 'explain'`

- [ ] **Step 3: Implement**

In `scripts/analyzer.py`, change the import line (line 9):

```python
from scripts import capabilities, collectors, explain, index_advisor, rules, sampler
from scripts.collectors import base
```

Replace the block from `target["diagnostics"] = collectors.run_collectors(` through the line above `target["collection_status"] = _collection_status(target["diagnostics"])`:

```python
            target["diagnostics"] = collectors.run_collectors(
                conn, target["capabilities"], sampling=sampling_result)
            query_stats_diag = target["diagnostics"].get("query_stats")
            try:
                target["diagnostics"]["explain"] = explain.run(
                    conn, target["capabilities"], query_stats_diag,
                    mode=cfg.explain_mode, top_n=cfg.explain_top_n,
                    analyze_top_n=cfg.explain_analyze_top_n,
                    statement_timeout_ms=cfg.explain_statement_timeout_ms,
                    lock_timeout_ms=cfg.explain_lock_timeout_ms)
            except Exception as exc:  # noqa: BLE001 - isolate EXPLAIN failure from other collectors
                target["diagnostics"]["explain"] = base.diagnostic(
                    "query", "error", [], reason=type(exc).__name__)
            try:
                target["diagnostics"]["index_advisor"] = index_advisor.run(
                    conn, query_stats_diag, top_n=cfg.explain_top_n)
            except Exception as exc:  # noqa: BLE001 - isolate index-advisor failure from other collectors
                target["diagnostics"]["index_advisor"] = base.diagnostic(
                    "table", "error", [], reason=type(exc).__name__)
            try:
                rules.evaluate_target(target)
            except Exception:  # noqa: BLE001 - isolate rule-evaluation failure from collection status
                pass
            target["collection_status"] = _collection_status(target["diagnostics"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_analyzer.py -v`
Expected: PASS (all tests, including the pre-existing Docker-gated ones if Docker is available)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyzer.py tests/unit/test_analyzer.py
git commit -m "feat(p4): wire explain + index_advisor into analyzer with per-step isolation"
```

---

### Task 9: `SKILL.md` — honest code-analysis confidence tiers (P4.5) + axis matrix update

**Files:**
- Modify: `SKILL.md:609-614` (insert new subsection 5.8 after 5.7)
- Modify: `SKILL.md:624-630` (axis matrix: reference the 3 new P4 collectors)
- Modify: `tests/unit/test_skill_docs.py` (append 2 new tests)

**Interfaces:**
- Consumes: nothing (documentation-only task, per spec §3 — code-analysis is the agent's responsibility, not a Python collector; P4.5 explicitly introduces no new script).
- Produces: no code interface — SKILL.md prose that a future agent reads when running Bước 5, and 2 new tests asserting the prose exists.

The relevant current `SKILL.md` content (verified this task, lines 602-632):

```markdown
#### 5.6 Mapping Code ↔ Database
1. Lấy danh sách tables từ DB (query `information_schema.tables`)
2. Lấy danh sách entities từ code
3. Cross-reference để tìm:
   - Tables có trong DB nhưng không có entity trong code
   - Entities trong code nhưng không có table trong DB

#### 5.7 Phân Tích Connection Management
```
- Tìm connection string configurations
- Kiểm tra connection pool settings
- Tìm tiềm năng connection leak (open without close/dispose)
```

### Bước 6: Tạo Báo Cáo Tổng Hợp (COMBINED_REPORT.md)

Sử dụng template từ `references/template-combined-report.md`.

### Mô hình đánh giá theo trục (Axis Model)

Từ P3 trở đi, hệ thống KHÔNG dùng điểm số tổng hợp 0-100 (double-counting, false precision). Mỗi trục trong 5 trục sau được đánh giá độc lập bằng 🟢/🟡/🔴/⚪/➖ kèm độ tin cậy (`measured`/`estimated`/`heuristic`):

| Trục | Nguồn rule | Diagnostic blocks liên quan |
|------|-----------|------------------------------|
| DB Health | `references/rules/db-health.json` | `database_stats`, `wraparound` |
| Query Performance | `references/rules/query-performance.json` | `query_stats`, `index_io` |
| Maintenance | `references/rules/maintenance.json` | `dead_tuples`, `stale_stats`, `index_bloat`, `duplicate_index`, `fk_missing_index` |
| Connections | `references/rules/connections.json` | `connection_depth`, `blocking` |
| Security/RLS | `references/rules/security-rls.json` (rỗng — chưa có collector, xem P4.3) | — |
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_skill_docs.py`:

```python
def test_skill_md_has_code_analysis_confidence_section(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "5.8 Gán Độ Tin Cậy Cho Code Findings" in text
    for tier in ("measured", "estimated", "heuristic"):
        assert f"`{tier}`" in text
    assert "Không tìm thấy raw SQL" in text


def test_skill_md_security_rls_axis_references_rls_policies_collector(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "`rls_policies`" in text
    assert "rỗng — chưa có collector" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_skill_docs.py -v -k confidence_section or rls_policies_collector`
Expected: FAIL (both new assertions absent from the current SKILL.md)

- [ ] **Step 3: Implement**

In `SKILL.md`, insert a new subsection 5.8 between the end of 5.7's fenced block and `### Bước 6`:

```markdown
#### 5.8 Gán Độ Tin Cậy Cho Code Findings

Mỗi finding từ Bước 5.3-5.7 (raw SQL, SQL injection, N+1, mapping, connection management) phải được gán một trong 3 mức độ tin cậy — code-analysis ở đây là agent tự grep/đọc code (§3 kiến trúc: đây là trách nhiệm của agent, không phải collector Python), nên độ tin cậy phản ánh agent tự tin đến đâu vào từng phát hiện, không phải một con số đo được từ DB:

| Mức | Khi nào dùng | Ví dụ |
|-----|-------------|-------|
| `measured` | Pattern match trực tiếp, không cần suy luận thêm — chuỗi text rõ ràng xuất hiện trong code | String-concatenated SQL (`"SELECT * FROM " + table`), `SELECT *` literal trong query text |
| `estimated` | Pattern match nhưng cần agent tự xác nhận ngữ cảnh (vd. loop có thực sự gọi DB mỗi vòng không) | N+1 pattern (loop chứa call trông giống DB call), thiếu index cho cột dùng trong WHERE của raw SQL |
| `heuristic` | Suy luận gián tiếp, không có bằng chứng trực tiếp trong code — dựa trên convention/thiếu vắng | "Có thể" thiếu connection pooling vì không tìm thấy config rõ ràng, "Có thể" thiếu pagination vì không thấy LIMIT/OFFSET |

**Ưu tiên báo cáo:** liệt kê finding theo thứ tự `measured` → `estimated` → `heuristic` trong CODE_ANALYSIS_REPORT.md — tín hiệu độ tin cậy cao (SQL injection do string concatenation, `SELECT *`, connection leak pattern rõ ràng) phải đứng trước các suy đoán (N+1 chưa xác nhận, thiếu pagination suy luận từ absence).

**Khi không tìm thấy gì:** nếu Bước 5.3 không tìm thấy raw SQL nào do code dùng ORM/ORM-generated SQL hoàn toàn, CODE_ANALYSIS_REPORT.md phải ghi rõ câu "Không tìm thấy raw SQL — code sử dụng ORM, không có ORM-generated SQL nào được kiểm tra thủ công" thay vì bỏ trống section — im lặng không phân biệt được với "chưa chạy bước này".
```

Then update the axis matrix table (the `### Mô hình đánh giá theo trục` section) to reference the 3 new P4 collectors:

```markdown
| Trục | Nguồn rule | Diagnostic blocks liên quan |
|------|-----------|------------------------------|
| DB Health | `references/rules/db-health.json` | `database_stats`, `wraparound` |
| Query Performance | `references/rules/query-performance.json` | `query_stats`, `index_io`, `index_advisor` |
| Maintenance | `references/rules/maintenance.json` | `dead_tuples`, `stale_stats`, `index_bloat`, `duplicate_index`, `fk_missing_index`, `schema_checks` |
| Connections | `references/rules/connections.json` | `connection_depth`, `blocking` |
| Security/RLS | `references/rules/security-rls.json` | `rls_policies` |
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_skill_docs.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add SKILL.md tests/unit/test_skill_docs.py
git commit -m "docs(p4): honest code-analysis confidence tiers + axis matrix update (P4.5)"
```

---

## Self-Review

**Spec coverage:**
- §0.A3 config fields (`ExplainMode`, `ExplainTopN`, `ExplainAnalyzeTopN`, `ExplainStatementTimeoutMs`, `ExplainLockTimeoutMs`) — Task 1.
- §0.A3 parameterized-query PG16+ generic-plan / pre-PG16 unavailable — Task 4 (`_explain_row`'s dispatch).
- §0.A3 never-ANALYZE-for-unsafe-statement rule (FOR UPDATE / advisory lock / volatile function / FDW) — Task 2 (`sql_classify.is_analyze_safe`) + Task 4 (`_references_foreign_table`, `analyze_skipped_reason`).
- §0.A3 parser-based safety gate, not regex — Task 2 (`pglast`-based `sql_classify.py`); Architecture decision (3) explicitly keeps `is_readonly_sql` unused.
- §0.A3 role/search_path/database/GUC recording — Task 4 (`_current_context`).
- §0.A3 `ExplainTopN` distinct from `SlowQueryTopN` — Task 4/8 (`explain.run`'s own `top_n` param, sourced from `cfg.explain_top_n`, independent of any other Top-N knob).
- §0.B1 `"parameterized_pre_pg16"` verbatim — Task 4 (`_explain_row`), asserted in Task 4's test.
- P4.1 EXPLAIN attached per top-N slow query, ANALYZE opt-in + allowlist + timeout, read-only-transaction-not-sufficient — Task 4.
- P4.2 column metadata + predicate parsing + composite/covering suggestion + duplicate check — Tasks 3 + 5.
- P4.3 RLS unwrapped-call detection + missing-index — Task 6.
- P4.4 missing PK / oversized UUIDv4 PK / timestamptz — Task 7.
- P4.5 honest code-analysis confidence tiers, explicit no-ORM-SQL-found statement, no `/100` framing — Task 9.
- Acceptance: "every slow-query finding has either a plan or a stated reason" — Task 4's `_explain_row` always returns one of `plan`/`analyze_result`/`explain_unavailable`/`explain_failed:*` per row, never silently omits. "at least one column-level index suggestion fires against fixture data" — Task 5's `test_suggests_index_for_uncovered_equality_predicate`. "RLS re-eval detected against unwrapped-subselect fixture" — Task 6's `test_collect_flags_unwrapped_auth_uid`.

**Placeholder scan:** no `TBD`/`later`/`similar to Task N` found — every step above shows complete code. Re-checked.

**Type/signature consistency across tasks:**
- `explain.run(conn, caps, query_stats_diag, *, mode, top_n, analyze_top_n, statement_timeout_ms, lock_timeout_ms)` — same signature in Task 4 (definition) and Task 8 (call site + tests).
- `index_advisor.run(conn, query_stats_diag, *, top_n)` — same signature in Task 5 (definition) and Task 8 (call site + tests).
- `sql_classify.parse_statement(sql)` — same name/arity used in Task 2 (definition), Task 5 (`index_advisor.py`), Task 6 (`rls_policies.py`).
- `index_predicate.equality_columns_from_statement(stmt)` returning a list of column-path lists — same shape consumed identically in Task 5 (`path[-1]`) and Task 6 (`path[-1]`).
- `index_catalog.existing_indexed_columns`/`is_covered` — same two-arg/two-arg signatures used identically in Task 5 and Task 6.
- `DbConfig` field names (`explain_mode`, `explain_top_n`, `explain_analyze_top_n`, `explain_statement_timeout_ms`, `explain_lock_timeout_ms`) — introduced in Task 1, consumed with the exact same names in Task 8.
- `base.diagnostic("query"/"table", "error", [], reason=type(exc).__name__)` — matches the existing convention already used by `collectors/__init__.py:run_collectors`.

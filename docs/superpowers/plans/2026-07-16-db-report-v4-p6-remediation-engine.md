# Phase 6 — Remediation Engine từ Versioned Templates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclassify every remediation in the knowledge base by safety tier (5-tier taxonomy), remove data-losing/auto-executing SQL patterns, add a `recovery_or_rollback` field convention, gate `ALTER SYSTEM`/`pg_terminate_backend` on real capability/session-state checks, and document all of this in a new `references/remediation-policy.md` — so the agent authoring `PERFORMANCE_SOLUTIONS.md` never emits a runnable "dangerous" fix and always states how to recover from what it does emit.

**Architecture:** This phase is documentation/KB/template content work only — no Python code, no `report-data.schema.json` changes. `capabilities` is already a generic `{"type": "object"}` schema field, and `scripts/capabilities.py`'s `probe()` already exposes `vendor`, `managed` (bool), `is_superuser` (bool) that the agent reads directly from `report_data.json` at authoring time. The four target files (`references/remediation-policy.md` new, `references/kb/solution-index.md`, `SKILL.md`, `references/template-solutions-report.md`) are pure Markdown/prose; test coverage is via `pytest` string/regex assertions against file content, matching the established idiom in `tests/unit/test_skill_docs.py` and `tests/unit/test_solution_index.py`.

**Tech Stack:** Markdown (KB references, SKILL.md, Handlebars-style report templates), pytest (content-assertion tests using the `skill_dir` fixture).

## Global Constraints

- 5-tier taxonomy (spec §0.A6, verbatim — every remediation in `solution-index.md` must be tagged with exactly one of these 5 values as its `remediation_class`, except code-side-fix patterns which use `n/a (code-side fix, không phải remediation DB)`):
  ```
  observe-only          : SELECT catalog/stats, EXPLAIN không ANALYZE
  controlled-diagnostic : EXPLAIN ANALYZE (opt-in + timeout + allowlist)
  maintenance-review    : ANALYZE, VACUUM / VACUUM ANALYZE, per-table autovacuum
  ddl-review            : CREATE INDEX CONCURRENTLY, ALTER TABLE
  dangerous             : DROP INDEX, pg_terminate_backend, partition migration, ALTER SYSTEM, work_mem global
  ```
  No tier auto-executes. `dangerous`-tier fixes must never appear inside a "ready-to-run" script block.
- Field name is `recovery_or_rollback` (not `rollback`) everywhere — KB entries, `SKILL.md` prose, `template-solutions-report.md` placeholders.
- `CREATE/DROP INDEX CONCURRENTLY` statements go in their own SQL block, separate from any transactional block, with an explicit warning about `INVALID` indexes if the statement fails partway and how to clean them up.
- Partition migration guidance must NOT auto-generate a data-losing swap (`INSERT INTO ... SELECT * FROM ...` followed by `RENAME TO`/`RENAME TO`). Recommend `pg_partman` or an explicit manual batch-migration process with backup-first, FK/RLS/trigger/grant recreation, and a maintenance-window swap step.
- `pg_terminate_backend` may only target sessions in `idle in transaction` state (never plain `idle`), and must warn about killing pooled connections (e.g. PgBouncer/Supavisor).
- `ALTER SYSTEM` fixes must be gated on `capabilities.managed == false` (self-hosted only) — managed platforms (Supabase, RDS, etc.) never get an `ALTER SYSTEM` statement in run-ready output.
- No changes to `scripts/*.py`, `references/report-data.schema.json`, or `references/kb/_index.md` in this phase.
- `references/queries-solutions.sql` is deleted (`git rm`) — its auto-generation framing (§8.3 of `SKILL.md`) is replaced by the remediation-policy lookup flow.
- Pattern 11's existing "Expected Impact" line ("5-20x faster queries, instant old data deletion") stays unchanged — only pattern 13's hardcoded multiplier ("2-5x") is removed, per the spec's narrow scoping of that mandate.
- Patterns 6 and 7's existing "Expected Impact" lines stay unchanged; only `pg_terminate_backend` condition correctness and `ALTER SYSTEM` capability-gating are edited.
- The "Priority Assignment Rules" table (after pattern 19) is untouched — it already scopes itself to patterns 1-13.

---

## File Structure

- `references/remediation-policy.md` — **new file**. Canonical policy doc: 5-tier taxonomy, `recovery_or_rollback` convention, capability gating rules, CONCURRENTLY convention, partition migration guidance, `pg_terminate_backend` restriction, and how the agent applies this policy when authoring `PERFORMANCE_SOLUTIONS.md`.
- `references/kb/solution-index.md` — modified. Every one of the 19 patterns gets a `- **Remediation Class**: \`<tier>\`` line. Patterns 5, 6, 7, 11, 13 get full content rewrites (dangerous-tier fixes restructured, capability-gated, `recovery_or_rollback` added).
- `SKILL.md` — modified. §8.3 renamed and rewritten to a remediation-class lookup flow (no more "execute queries from `queries-solutions.sql`" framing). §8.5 step 3 (CONCURRENTLY block/INVALID warning), step 5 (`recovery_or_rollback` field), new step 6 (dangerous-tier exclusion from run-ready scripts). "SQL Query References" section drops the `queries-solutions.sql` bullet, adds a `remediation-policy.md` bullet. "Solution Engine" section renames `rollback` → `recovery_or_rollback` and notes every pattern carries a `remediation_class`.
- `references/queries-solutions.sql` — **deleted** (`git rm`).
- `references/template-solutions-report.md` — modified. P0-loop "Hoàn tác" heading/placeholder renamed to `recovery_or_rollback`. "SCRIPT SQL SẴN SÀNG CHẠY" section gets dangerous-exclusion warnings + inline comments in each script header. New "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" subsection after Script 3. Footer version bump v3.0.0 → v4.0.0.
- `tests/unit/test_remediation_policy.py` — **new file**. 6 tests asserting the new policy doc's required content.
- `tests/unit/test_solution_index.py` — extended with tests asserting remediation-class tagging, dangerous-tier restructuring, and capability gating.
- `tests/unit/test_skill_docs.py` — extended with tests asserting `SKILL.md` no longer references the deleted SQL file, uses `recovery_or_rollback` terminology, and references the new policy file; and that the solutions template has the dangerous section and version bump.

---

### Task 1: Create `references/remediation-policy.md` + its tests

**Files:**
- Create: `E:\Work\db-report-portable\.agents\skills\db-report-generator\references\remediation-policy.md`
- Create: `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_remediation_policy.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task).
- Produces: `references/remediation-policy.md` — Task 2 (`solution-index.md`), Task 3 (`SKILL.md`), and Task 4 (`template-solutions-report.md`) all reference this file by path and are expected to be consistent with its taxonomy/terminology (`remediation_class`, `recovery_or_rollback`, the 5 tier names verbatim).

- [ ] **Step 1: Write the failing tests**

Create `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_remediation_policy.py`:

```python
def test_remediation_policy_file_exists(skill_dir):
    p = skill_dir / "references" / "remediation-policy.md"
    assert p.exists()


def test_remediation_policy_has_5_tier_taxonomy(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    for tier in (
        "observe-only",
        "controlled-diagnostic",
        "maintenance-review",
        "ddl-review",
        "dangerous",
    ):
        assert f"`{tier}`" in text, f"missing tier {tier!r}"


def test_remediation_policy_states_no_tier_auto_executes(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "không tier nào tự động thực thi" in text.lower() or "no tier auto-executes" in text.lower()


def test_remediation_policy_gates_alter_system_on_managed(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "capabilities.managed" in text
    assert "ALTER SYSTEM" in text


def test_remediation_policy_defines_recovery_or_rollback(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "recovery_or_rollback" in text
    assert "pg_terminate_backend" in text


def test_remediation_policy_covers_concurrently_and_partition(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "CONCURRENTLY" in text
    assert "INVALID" in text
    assert "pg_partman" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_remediation_policy.py -v` (from `E:\Work\db-report-portable\.agents\skills\db-report-generator`)
Expected: FAIL — `references/remediation-policy.md` does not exist (first test errors on `.read_text` / fails on `.exists()`), all 6 tests fail or error.

- [ ] **Step 3: Write `references/remediation-policy.md`**

Create `E:\Work\db-report-portable\.agents\skills\db-report-generator\references\remediation-policy.md`:

```markdown
---
title: Remediation Policy — 5-Tier Safety Taxonomy
version: "1.0.0"
last_updated: 2026-07-16
---

# Remediation Policy

Tài liệu này định nghĩa cách phân loại độ an toàn cho MỌI remediation (fix SQL) mà agent đề xuất trong `PERFORMANCE_SOLUTIONS.md`, và cách agent phải áp dụng phân loại đó. Đây là chính sách bắt buộc — không tier nào tự động thực thi (no tier auto-executes); mọi câu lệnh SQL agent đưa ra đều dành để con người review trước khi chạy.

## 1. Phân Loại 5 Tier (5-Tier Taxonomy)

| Tier | Mô tả | Ví dụ |
|------|-------|-------|
| `observe-only` | SELECT catalog/stats, EXPLAIN không ANALYZE | `SELECT * FROM pg_stat_user_indexes`, `EXPLAIN SELECT ...` |
| `controlled-diagnostic` | EXPLAIN ANALYZE (opt-in + timeout + allowlist) | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` khi đã bật `ExplainMode=analyze` |
| `maintenance-review` | ANALYZE, VACUUM / VACUUM ANALYZE, per-table autovacuum | `VACUUM ANALYZE {{table}}`, `ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = ...)` |
| `ddl-review` | CREATE INDEX CONCURRENTLY, ALTER TABLE | `CREATE INDEX CONCURRENTLY ...`, thêm foreign key, thêm NOT NULL |
| `dangerous` | DROP INDEX, pg_terminate_backend, partition migration, ALTER SYSTEM, work_mem global | `DROP INDEX CONCURRENTLY`, `SELECT pg_terminate_backend(...)`, di chuyển bảng sang partition, `ALTER SYSTEM SET ...` |

**Nguyên tắc cốt lõi**: không tier nào tự động thực thi (no tier auto-executes). Toàn bộ SQL trong `PERFORMANCE_SOLUTIONS.md` là đề xuất để con người đọc, hiểu, và tự chạy — kể cả các tier thấp như `observe-only`.

## 2. Trường `recovery_or_rollback`

Mỗi fix trong `solution-index.md` PHẢI có một trường `recovery_or_rollback` mô tả cách khôi phục lại trạng thái trước khi chạy fix — thay cho tên cũ `rollback` (tên mới phản ánh đúng thực tế: không phải fix nào cũng có rollback giao dịch được).

Ví dụ theo loại fix:
- **CONCURRENTLY index** (tạo mới): `recovery_or_rollback` = `DROP INDEX CONCURRENTLY {{index_name}};` nếu cần huỷ.
- **DROP INDEX**: `recovery_or_rollback` = `CREATE INDEX CONCURRENTLY ...` dùng definition đã lưu lại TRƯỚC khi DROP (`SELECT pg_get_indexdef(indexrelid) ...`).
- **pg_terminate_backend**: KHÔNG có rollback — session đã bị kill là mất, không khôi phục lại được. Phải ghi rõ "KHÔNG có rollback" thay vì để trống.
- **Partition migration**: KHÔNG có rollback giao dịch — khôi phục chỉ có thể từ backup đã chụp trước khi migrate. Ghi rõ yêu cầu backup-first.
- **ALTER SYSTEM**: `recovery_or_rollback` = `ALTER SYSTEM RESET {{parameter}}; SELECT pg_reload_conf();` cho từng parameter đã đổi.

## 3. Capability Gating

Trước khi đề xuất bất kỳ fix nào thuộc tier `dangerous` liên quan tới `ALTER SYSTEM`, agent PHẢI đọc `report_data.json` → `capabilities`:
- `capabilities.managed == true` (Supabase, RDS, và các managed platform khác) → KHÔNG đề xuất `ALTER SYSTEM`. Thay vào đó, hướng dẫn người dùng đổi tham số qua control-plane/console/dashboard của nhà cung cấp (ví dụ: Supabase Dashboard → Database → Settings, hoặc AWS RDS Parameter Groups).
- `capabilities.managed == false` VÀ `capabilities.is_superuser == true` → có thể đề xuất `ALTER SYSTEM SET ... ; SELECT pg_reload_conf();` kèm `recovery_or_rollback`.
- `capabilities.is_superuser == false` (kể cả self-hosted) → KHÔNG đề xuất `ALTER SYSTEM` — user hiện tại không có quyền chạy.

## 4. Quy Ước CONCURRENTLY

Mọi `CREATE INDEX CONCURRENTLY` / `DROP INDEX CONCURRENTLY` PHẢI:
- Nằm trong SQL block RIÊNG, tách biệt khỏi bất kỳ block giao dịch (transaction) nào khác — `CONCURRENTLY` không được phép chạy bên trong một transaction block, và gộp chung block sẽ khiến toàn bộ script fail.
- Đi kèm cảnh báo: nếu câu lệnh `CONCURRENTLY` thất bại giữa chừng (mất kết nối, timeout, ...), index có thể còn lại ở trạng thái `INVALID` — cần kiểm tra bằng `SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE NOT indisvalid;` và `DROP INDEX CONCURRENTLY` index đó rồi thử lại.

## 5. Partition Migration

KHÔNG tự động sinh SQL kiểu "swap" mất dữ liệu (`CREATE TABLE ..._partitioned ...` → `INSERT INTO ..._partitioned SELECT * FROM ...` → `ALTER TABLE ... RENAME TO ..._old` → `ALTER TABLE ..._partitioned RENAME TO ...`) — cách này có nguy cơ mất ghi (writes xảy ra giữa lúc INSERT và RENAME) và không có rollback giao dịch.

Thay vào đó, hướng dẫn:
- Ưu tiên **pg_partman** (extension quản lý partition tự động, có kinh nghiệm cộng đồng rộng, xử lý maintenance window an toàn hơn).
- Nếu tự làm thủ công: backup-first (pg_dump hoặc snapshot), batch migration theo lô nhỏ (không INSERT toàn bộ một lần), verify row-count khớp giữa bảng gốc và bảng partition trước khi swap, tái tạo tường minh mọi FK constraint / RLS policy / trigger / GRANT trên bảng mới (những thứ này KHÔNG tự động theo qua khi tạo bảng mới), và chỉ swap trong một maintenance window đã thông báo trước.
- `recovery_or_rollback`: không có rollback giao dịch cho bước swap — khôi phục chỉ từ backup đã chụp trước khi migrate.

## 6. pg_terminate_backend

`pg_terminate_backend` chỉ được đề xuất nhắm vào session ở trạng thái `idle in transaction` (KHÔNG BAO GIỜ nhắm vào `idle` thường — một session idle bình thường có thể đang được connection pool giữ lại để tái sử dụng, kill nó gây mất kết nối oan). Luôn cảnh báo: nếu ứng dụng dùng connection pooler (PgBouncer, Supavisor), kill một backend có thể ảnh hưởng tới pool và gây lỗi phía client ngoài dự kiến — kiểm tra kỹ trước khi chạy. `recovery_or_rollback`: KHÔNG có — session đã terminate không khôi phục lại được.

## 7. Agent Áp Dụng Chính Sách Này Như Thế Nào

Khi soạn `PERFORMANCE_SOLUTIONS.md`:
1. Với mỗi pattern match được từ `solution-index.md`, đọc `remediation_class` của pattern đó.
2. Nếu `remediation_class` là `observe-only`, `controlled-diagnostic`, `maintenance-review`, hoặc `ddl-review` → có thể đưa fix SQL vào script block "SẴN SÀNG CHẠY" tương ứng theo priority (P0/P1/P2), kèm `recovery_or_rollback`.
3. Nếu `remediation_class` là `dangerous` → KHÔNG đưa vào bất kỳ script "SẴN SÀNG CHẠY" nào. Đưa vào mục riêng "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" của `template-solutions-report.md`, kèm giải thích lý do dangerous và `recovery_or_rollback` (hoặc lý do không có rollback).
4. Nếu fix liên quan `ALTER SYSTEM`, áp dụng capability gating ở mục 3 trước khi quyết định có đưa fix vào hay không, và với văn bản gì (managed → hướng dẫn qua console; self-hosted+superuser → SQL cụ thể; self-hosted không superuser → không đề xuất).
5. Nếu fix là `n/a (code-side fix, không phải remediation DB)` (patterns 8, 9, 10) → không thuộc phạm vi SQL remediation, xử lý theo mục "GIẢI PHÁP PHÍA CODE" hiện có của `template-solutions-report.md`, không áp dụng 5-tier taxonomy.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_remediation_policy.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add references/remediation-policy.md tests/unit/test_remediation_policy.py
git commit -m "feat(p6): add remediation-policy.md — 5-tier safety taxonomy + recovery_or_rollback convention"
```

---

### Task 2: Rewrite `references/kb/solution-index.md` — tier classification + dangerous-tier restructuring

**Files:**
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\references\kb\solution-index.md`
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_solution_index.py`

**Interfaces:**
- Consumes: `remediation-policy.md`'s tier names and `recovery_or_rollback` terminology from Task 1 (must match exactly: `observe-only`, `controlled-diagnostic`, `maintenance-review`, `ddl-review`, `dangerous`, `n/a (code-side fix, không phải remediation DB)`).
- Produces: every pattern in `solution-index.md` now carries `- **Remediation Class**: \`<tier>\`` — Task 3 (`SKILL.md` §8.3) and Task 4 (`template-solutions-report.md`) reference this field by the same name `remediation_class`/"Remediation Class" when describing the lookup flow.

- [ ] **Step 1: Write the failing tests**

Append to `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_solution_index.py`:

```python
def test_all_patterns_have_remediation_class(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    headings = [
        "## 1. LOW CACHE HIT RATIO",
        "## 2. HIGH SEQUENTIAL SCAN RATIO",
        "## 3. HIGH DEAD TUPLE RATIO",
        "## 4. SLOW QUERIES",
        "## 5. UNUSED INDEXES",
        "## 6. CONNECTION EXHAUSTION",
        "## 7. BLOCKING QUERIES",
        "## 8. N+1 QUERY PATTERN",
        "## 9. SQL INJECTION RISK",
        "## 10. MISSING PAGINATION",
        "## 11. LARGE TABLE WITHOUT PARTITIONING",
        "## 12. MISSING FOREIGN KEY INDEXES",
        "## 13. SUBOPTIMAL SERVER CONFIGURATION",
        "## 14. RLS POLICY RE-EVALUATION",
        "## 15. STALE TABLE STATISTICS",
        "## 16. EXPLAIN PLAN",
        "## 17. COLUMN-LEVEL INDEX SUGGESTION",
        "## 18. QUERY RANKING",
        "## 19. SCHEMA HYGIENE ISSUES",
    ]
    boundary = "## Priority Assignment Rules"
    positions = [text.index(h) for h in headings] + [text.index(boundary)]
    for i in range(len(headings)):
        section = text[positions[i]:positions[i + 1]]
        assert "**Remediation Class**" in section, f"missing Remediation Class in {headings[i]}"


def test_dangerous_patterns_marked_and_excluded_from_run_now(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 5. UNUSED INDEXES", "## 6. CONNECTION EXHAUSTION"),
        ("## 6. CONNECTION EXHAUSTION", "## 7. BLOCKING QUERIES"),
        ("## 7. BLOCKING QUERIES", "## 8. N+1 QUERY PATTERN"),
        ("## 11. LARGE TABLE WITHOUT PARTITIONING", "## 12. MISSING FOREIGN KEY INDEXES"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## 14. RLS POLICY RE-EVALUATION"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "`dangerous`" in block, f"{heading} not marked dangerous"
        assert "KHÔNG đưa vào block chạy-liền" in block, f"{heading} missing run-now exclusion note"


def test_pattern_6_terminates_idle_in_transaction_only(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 6. CONNECTION EXHAUSTION")
    end = text.index("## 7. BLOCKING QUERIES")
    block = text[start:end]
    assert "idle in transaction" in block
    assert "state = 'idle'" not in block


def test_patterns_6_7_13_gate_alter_system_on_self_hosted(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 6. CONNECTION EXHAUSTION", "## 7. BLOCKING QUERIES"),
        ("## 7. BLOCKING QUERIES", "## 8. N+1 QUERY PATTERN"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## 14. RLS POLICY RE-EVALUATION"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "capabilities.managed" in block, f"{heading} missing capability gate"


def test_pattern_11_no_data_loss_swap(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 11. LARGE TABLE WITHOUT PARTITIONING")
    end = text.index("## 12. MISSING FOREIGN KEY INDEXES")
    block = text[start:end]
    assert "RENAME TO" not in block
    assert "pg_partman" in block


def test_pattern_5_has_recovery_or_rollback_heading(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 5. UNUSED INDEXES")
    end = text.index("## 6. CONNECTION EXHAUSTION")
    block = text[start:end]
    assert "**recovery_or_rollback" in block
    assert "**Rollback:**" not in block


def test_pattern_13_no_hardcoded_multiplier_and_gated(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 13. SUBOPTIMAL SERVER CONFIGURATION")
    end = text.index("## 14. RLS POLICY RE-EVALUATION")
    block = text[start:end]
    assert "2-5x" not in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_solution_index.py -v`
Expected: FAIL — the 7 new tests fail (no `**Remediation Class**` lines exist yet, patterns 5/6/7/11/13 not restructured).

- [ ] **Step 3: Mechanical insertions for the 14 non-rewritten patterns**

For each pair below, use the exact Priority+Reference 2-line block as `old_string`, and insert the `Remediation Class` line immediately after Priority and before Reference as `new_string`. Apply each edit to `references/kb/solution-index.md`.

Pattern 1 (`ddl-review`):
```
old_string:
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`

new_string:
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
- **Remediation Class**: `ddl-review`
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`
```

Pattern 2 (`ddl-review`):
```
old_string:
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`

new_string:
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Remediation Class**: `ddl-review`
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`
```

Pattern 3 (`maintenance-review`):
```
old_string:
- **Priority**: P0 (> 50%) | P1 (20-50%) | P2 (5-20%)
- **Reference**: `monitor-vacuum-analyze.md`

new_string:
- **Priority**: P0 (> 50%) | P1 (20-50%) | P2 (5-20%)
- **Remediation Class**: `maintenance-review`
- **Reference**: `monitor-vacuum-analyze.md`
```

Pattern 4 (`ddl-review`):
```
old_string:
- **Priority**: P0 (> 5000ms) | P1 (1000-5000ms) | P2 (100-1000ms)
- **Reference**: `monitor-explain-analyze.md`, `query-composite-indexes.md`

new_string:
- **Priority**: P0 (> 5000ms) | P1 (1000-5000ms) | P2 (100-1000ms)
- **Remediation Class**: `ddl-review`
- **Reference**: `monitor-explain-analyze.md`, `query-composite-indexes.md`
```

Pattern 8 (`n/a (code-side fix, không phải remediation DB)`):
```
old_string:
- **Priority**: P1
- **Reference**: `data-n-plus-one.md`

new_string:
- **Priority**: P1
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `data-n-plus-one.md`
```

Pattern 9 (`n/a (code-side fix, không phải remediation DB)`):
```
old_string:
- **Priority**: P0
- **Reference**: `security-sql-injection.md`

new_string:
- **Priority**: P0
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `security-sql-injection.md`
```

Pattern 10 (`n/a (code-side fix, không phải remediation DB)`):
```
old_string:
- **Priority**: P1 (tables > 10K rows) | P2 (tables > 1K rows)
- **Reference**: `data-pagination.md`

new_string:
- **Priority**: P1 (tables > 10K rows) | P2 (tables > 1K rows)
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `data-pagination.md`
```

Pattern 12 (`ddl-review`):
```
old_string:
- **Priority**: P1
- **Reference**: `schema-foreign-key-indexes.md`

new_string:
- **Priority**: P1
- **Remediation Class**: `ddl-review`
- **Reference**: `schema-foreign-key-indexes.md`
```

Pattern 14 (`ddl-review`):
```
old_string:
- **Priority**: P1
- **Reference**: `security-rls-performance.md`

new_string:
- **Priority**: P1
- **Remediation Class**: `ddl-review`
- **Reference**: `security-rls-performance.md`
```

Pattern 15 (`maintenance-review`):
```
old_string:
- **Priority**: P0 (> 50%) | P1 (20-50%)
- **Reference**: `monitor-vacuum-analyze.md`

new_string:
- **Priority**: P0 (> 50%) | P1 (20-50%)
- **Remediation Class**: `maintenance-review`
- **Reference**: `monitor-vacuum-analyze.md`
```

Pattern 16 (`observe-only` default / `controlled-diagnostic` when ANALYZE opt-in):
```
old_string:
- **Priority**: (kế thừa priority của mục 4 — không có priority riêng)
- **Reference**: `monitor-explain-analyze.md`

new_string:
- **Priority**: (kế thừa priority của mục 4 — không có priority riêng)
- **Remediation Class**: `observe-only` (mặc định, EXPLAIN không ANALYZE) / `controlled-diagnostic` (khi ANALYZE opt-in)
- **Reference**: `monitor-explain-analyze.md`
```

Pattern 17 (`ddl-review`):
```
old_string:
- **Priority**: P2
- **Reference**: `query-composite-indexes.md` (tự động) — `query-covering-indexes.md`, `query-partial-indexes.md` (gợi ý thủ công, reviewer tự cân nhắc)

new_string:
- **Priority**: P2
- **Remediation Class**: `ddl-review`
- **Reference**: `query-composite-indexes.md` (tự động) — `query-covering-indexes.md`, `query-partial-indexes.md` (gợi ý thủ công, reviewer tự cân nhắc)
```

Pattern 18 (`observe-only`):
```
old_string:
- **Priority**: (bổ trợ — dùng priority của mục 4 nếu cùng query vượt ngưỡng mean_exec_time)
- **Reference**: `monitor-pg-stat-statements.md`

new_string:
- **Priority**: (bổ trợ — dùng priority của mục 4 nếu cùng query vượt ngưỡng mean_exec_time)
- **Remediation Class**: `observe-only`
- **Reference**: `monitor-pg-stat-statements.md`
```

Pattern 19 (`ddl-review`):
```
old_string:
- **Priority**: P1 (`missing_primary_key`) | P2 (`oversized_uuid_pk`, `timestamp_without_timezone`)
- **Reference**: `schema-primary-keys.md` (missing_primary_key, oversized_uuid_pk), `schema-data-types.md` (timestamp_without_timezone)

new_string:
- **Priority**: P1 (`missing_primary_key`) | P2 (`oversized_uuid_pk`, `timestamp_without_timezone`)
- **Remediation Class**: `ddl-review`
- **Reference**: `schema-primary-keys.md` (missing_primary_key, oversized_uuid_pk), `schema-data-types.md` (timestamp_without_timezone)
```

- [ ] **Step 4: Full rewrite of pattern 5 (UNUSED INDEXES)**

```
old_string:
## 5. UNUSED INDEXES

- **Detection**: [Tự động, một phần — xác nhận thủ công trước khi DROP] Diagnostic block `index_io`, field `idx_scan` = 0. 2 giới hạn: (1) `index_io` chỉ thu top-30 index theo `idx_blks_read`, KHÔNG đầy đủ toàn bộ index của DB; (2) hiện KHÔNG có finding_id/rule riêng cho `idx_scan = 0` (`references/rules/query-performance.json` chỉ có `query_perf.index_cache_hit_ratio` cho block này) — nghĩa là finding này KHÔNG tự xuất hiện trong report's rule-driven findings, chỉ tra được thủ công trong `diagnostics.index_io.metrics`.
- **Priority**: P2 (< 100MB) | P3 (> 100MB nhưng cần verify 2+ tuần)
- **Reference**: _Không có file KB match chính xác cho "unused index cleanup" — `query-missing-indexes.md` nói về vấn đề NGƯỢC LẠI (thiếu index). Dùng Fix Template bên dưới, không cần tài liệu bổ sung._
- **Category**: DB-side / Cleanup

**Fix Template:**
```sql
-- Verify index thực sự unused (kiểm tra ít nhất 2 tuần data)
SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes WHERE indexrelname = '{{index_name}}';

-- Nếu confirm unused:
DROP INDEX CONCURRENTLY {{schema}}."{{index_name}}";
```

**Rollback:**
```sql
-- Recreate index nếu cần
CREATE INDEX CONCURRENTLY "{{index_name}}" ON {{schema}}."{{table_name}}" ({{columns}});
```

**Expected Impact**: Giải phóng storage, faster writes (không maintain index thừa)

new_string:
## 5. UNUSED INDEXES

- **Detection**: [Tự động, một phần — xác nhận thủ công trước khi DROP] Diagnostic block `index_io`, field `idx_scan` = 0. 2 giới hạn: (1) `index_io` chỉ thu top-30 index theo `idx_blks_read`, KHÔNG đầy đủ toàn bộ index của DB; (2) hiện KHÔNG có finding_id/rule riêng cho `idx_scan = 0` (`references/rules/query-performance.json` chỉ có `query_perf.index_cache_hit_ratio` cho block này) — nghĩa là finding này KHÔNG tự xuất hiện trong report's rule-driven findings, chỉ tra được thủ công trong `diagnostics.index_io.metrics`.
- **Priority**: P2 (< 100MB) | P3 (> 100MB nhưng cần verify 2+ tuần)
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: _Không có file KB match chính xác cho "unused index cleanup" — `query-missing-indexes.md` nói về vấn đề NGƯỢC LẠI (thiếu index). Dùng Fix Template bên dưới, không cần tài liệu bổ sung._
- **Category**: DB-side / Cleanup

**Fix Template** (KHÔNG đưa vào block chạy-liền — chỉ tham khảo cho review thủ công):
```sql
-- Verify index thực sự unused (kiểm tra ít nhất 2 tuần data)
SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes WHERE indexrelname = '{{index_name}}';

-- Lưu lại definition TRƯỚC khi DROP, để có thể recreate sau này
SELECT indexdef FROM pg_indexes WHERE indexname = '{{index_name}}';

-- Nếu confirm unused:
DROP INDEX CONCURRENTLY {{schema}}."{{index_name}}";
```

**recovery_or_rollback:**
```sql
-- Recreate index dùng definition đã lưu ở bước trên (SELECT indexdef ...)
CREATE INDEX CONCURRENTLY "{{index_name}}" ON {{schema}}."{{table_name}}" ({{columns}});
```

**Expected Impact**: Giải phóng storage, faster writes (không maintain index thừa)
```

- [ ] **Step 5: Full rewrite of pattern 6 (CONNECTION EXHAUSTION)**

```
old_string:
## 6. CONNECTION EXHAUSTION

- **Detection**: [Tự động] Diagnostic block `connection_depth`. 3 finding_id riêng biệt (`references/rules/connections.json`) — KHÔNG gộp chung "total/max" như v3: `connections.cluster_pressure` (tỷ lệ `cluster_connections`/`cluster_max_connections`, red > 0.90, yellow > 0.60), `connections.pool_pressure` (tỷ lệ `db_connections`/`configured_pool_size`, red > 0.90, yellow > 0.60), `connections.idle_in_transaction` (field `longest_txn_seconds`, red > 600s, yellow > 60s).
- **Priority**: P0 (> 90%) | P1 (80-90%)
- **Reference**: `conn-pooling.md`, `conn-limits.md`, `conn-idle-timeout.md`
- **Category**: Architecture / Connection Management

**Fix Template:**
```sql
-- Immediate: kill idle connections > 10 phút
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < now() - interval '10 minutes'
  AND datname = current_database();

-- Config idle timeout
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
ALTER SYSTEM SET idle_session_timeout = '10min';
SELECT pg_reload_conf();
```

**Code-side fix (C#/.NET):**
```csharp
// Trong connection string, thêm:
// "Pooling=true;MinPoolSize=5;MaxPoolSize=100;ConnectionIdleLifetime=300;"

// Hoặc trong appsettings.json:
// "ConnectionStrings": {
//   "Default": "Host=...;Pooling=true;MaxPoolSize=100;Connection Idle Lifetime=300"
// }
```

**Expected Impact**: Giải phóng 30-50% connection slots

new_string:
## 6. CONNECTION EXHAUSTION

- **Detection**: [Tự động] Diagnostic block `connection_depth`. 3 finding_id riêng biệt (`references/rules/connections.json`) — KHÔNG gộp chung "total/max" như v3: `connections.cluster_pressure` (tỷ lệ `cluster_connections`/`cluster_max_connections`, red > 0.90, yellow > 0.60), `connections.pool_pressure` (tỷ lệ `db_connections`/`configured_pool_size`, red > 0.90, yellow > 0.60), `connections.idle_in_transaction` (field `longest_txn_seconds`, red > 600s, yellow > 60s).
- **Priority**: P0 (> 90%) | P1 (80-90%)
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: `conn-pooling.md`, `conn-limits.md`, `conn-idle-timeout.md`
- **Category**: Architecture / Connection Management

**Fix Template** (KHÔNG đưa vào block chạy-liền — chỉ tham khảo cho review thủ công):
```sql
-- Immediate: kill sessions kẹt trong transaction > 5 phút (KHÔNG kill 'idle' thường — có thể đang được connection pool giữ lại)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < now() - interval '5 minutes'
  AND datname = current_database();

-- Config idle timeout
-- CHỈ chạy nếu capabilities.managed == false (self-hosted) — managed platform (Supabase/RDS) không hỗ trợ ALTER SYSTEM, đổi qua console/dashboard
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
ALTER SYSTEM SET idle_session_timeout = '10min';
SELECT pg_reload_conf();
```

**Code-side fix (C#/.NET):**
```csharp
// Trong connection string, thêm:
// "Pooling=true;MinPoolSize=5;MaxPoolSize=100;ConnectionIdleLifetime=300;"

// Hoặc trong appsettings.json:
// "ConnectionStrings": {
//   "Default": "Host=...;Pooling=true;MaxPoolSize=100;Connection Idle Lifetime=300"
// }
```

**recovery_or_rollback:**
```sql
-- pg_terminate_backend: KHÔNG có rollback — session đã terminate không khôi phục lại được.
-- ALTER SYSTEM: reset lại giá trị mặc định
ALTER SYSTEM RESET idle_in_transaction_session_timeout;
ALTER SYSTEM RESET idle_session_timeout;
SELECT pg_reload_conf();
```

**Expected Impact**: Giải phóng 30-50% connection slots
```

- [ ] **Step 6: Full rewrite of pattern 7 (BLOCKING QUERIES)**

```
old_string:
## 7. BLOCKING QUERIES

- **Detection**: [Tự động] Diagnostic block `blocking`, field `blocked_duration_seconds` (kèm `blocked_pid`, `blocking_pid`, `blocked_query`, `blocking_query`) → finding_id `connections.blocking` (red > 30s, yellow > 5s; `references/rules/connections.json`, row_identity `blocked_pid,blocking_pid`).
- **Priority**: P0
- **Reference**: `lock-short-transactions.md`, `lock-deadlock-prevention.md`
- **Category**: DB-side / Locking

**Fix Template:**
```sql
-- Immediate: terminate blocking query (nếu safe)
SELECT pg_terminate_backend({{blocking_pid}});

-- Long-term: set statement_timeout
ALTER SYSTEM SET statement_timeout = '30s';
ALTER SYSTEM SET lock_timeout = '10s';
SELECT pg_reload_conf();
```

**Code-side fix:**
```csharp
// Thêm CommandTimeout cho mỗi query
// using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = 30 };

// Hoặc trong EF Core:
// optionsBuilder.UseNpgsql(connStr, o => o.CommandTimeout(30));
```

**Expected Impact**: Immediate unblocking, 3-5x throughput

new_string:
## 7. BLOCKING QUERIES

- **Detection**: [Tự động] Diagnostic block `blocking`, field `blocked_duration_seconds` (kèm `blocked_pid`, `blocking_pid`, `blocked_query`, `blocking_query`) → finding_id `connections.blocking` (red > 30s, yellow > 5s; `references/rules/connections.json`, row_identity `blocked_pid,blocking_pid`).
- **Priority**: P0
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: `lock-short-transactions.md`, `lock-deadlock-prevention.md`
- **Category**: DB-side / Locking

**Fix Template** (KHÔNG đưa vào block chạy-liền — chỉ tham khảo cho review thủ công):
```sql
-- Immediate: terminate blocking query (nếu safe)
SELECT pg_terminate_backend({{blocking_pid}});

-- Long-term: set statement_timeout
-- CHỈ chạy nếu capabilities.managed == false (self-hosted) — managed platform không hỗ trợ ALTER SYSTEM, đổi qua console/dashboard
ALTER SYSTEM SET statement_timeout = '30s';
ALTER SYSTEM SET lock_timeout = '10s';
SELECT pg_reload_conf();
```

**Code-side fix:**
```csharp
// Thêm CommandTimeout cho mỗi query
// using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = 30 };

// Hoặc trong EF Core:
// optionsBuilder.UseNpgsql(connStr, o => o.CommandTimeout(30));
```

**recovery_or_rollback:**
```sql
-- pg_terminate_backend: KHÔNG có rollback — session đã terminate không khôi phục lại được.
-- ALTER SYSTEM: reset lại giá trị mặc định
ALTER SYSTEM RESET statement_timeout;
ALTER SYSTEM RESET lock_timeout;
SELECT pg_reload_conf();
```

**Expected Impact**: Immediate unblocking, 3-5x throughput
```

- [ ] **Step 7: Full rewrite of pattern 11 (LARGE TABLE WITHOUT PARTITIONING)**

```
old_string:
## 11. LARGE TABLE WITHOUT PARTITIONING

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào kiểm tra partitioning trong db-report-generator v4. Diagnostic block `table_index_size`, field `row_estimate` (từ `pg_class.reltuples`) có thể dùng làm input thủ công để tìm bảng lớn — nhưng KHÔNG có rule/finding_id nào đánh giá `row_estimate`, và việc xác định "time-series column" đòi hỏi agent tự đọc schema thủ công.
- **Priority**: P2
- **Reference**: `schema-partitioning.md`
- **Category**: Architecture / Schema (thủ công)

**Fix Template:**
```sql
-- Tạo partitioned table mới
CREATE TABLE {{table_name}}_partitioned (
  LIKE {{schema}}."{{table_name}}" INCLUDING ALL
) PARTITION BY RANGE ("{{time_column}}");

-- Tạo monthly partitions
CREATE TABLE {{table_name}}_y2026m01
  PARTITION OF {{table_name}}_partitioned
  FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE {{table_name}}_y2026m02
  PARTITION OF {{table_name}}_partitioned
  FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Migrate data (off-peak hours)
INSERT INTO {{table_name}}_partitioned
SELECT * FROM {{schema}}."{{table_name}}";

-- Swap tables
ALTER TABLE {{schema}}."{{table_name}}" RENAME TO "{{table_name}}_old";
ALTER TABLE {{table_name}}_partitioned RENAME TO "{{table_name}}";
```

**Expected Impact**: 5-20x faster queries, instant old data deletion

new_string:
## 11. LARGE TABLE WITHOUT PARTITIONING

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào kiểm tra partitioning trong db-report-generator v4. Diagnostic block `table_index_size`, field `row_estimate` (từ `pg_class.reltuples`) có thể dùng làm input thủ công để tìm bảng lớn — nhưng KHÔNG có rule/finding_id nào đánh giá `row_estimate`, và việc xác định "time-series column" đòi hỏi agent tự đọc schema thủ công.
- **Priority**: P2
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: `schema-partitioning.md`
- **Category**: Architecture / Schema (thủ công)

**Hướng dẫn (không tự động sinh SQL swap mất dữ liệu):**

1. Ưu tiên dùng extension **pg_partman** để quản lý partition tự động thay vì migrate thủ công.
2. Nếu tự làm thủ công:
   - Backup trước (pg_dump hoặc snapshot).
   - Tạo bảng partition mới, migrate dữ liệu theo batch nhỏ (KHÔNG `INSERT ... SELECT *` toàn bộ một lần).
   - Verify row-count khớp giữa bảng gốc và bảng partition mới.
   - Tái tạo tường minh: foreign key constraints, RLS policies, triggers, GRANTs (những thứ này KHÔNG tự động theo qua khi tạo bảng mới).
   - Chỉ swap tên bảng trong một maintenance window đã thông báo trước.

**recovery_or_rollback**: Không có rollback giao dịch cho bước swap bảng — khôi phục chỉ có thể thực hiện từ backup đã chụp trước khi migrate.

**Expected Impact**: 5-20x faster queries, instant old data deletion
```

- [ ] **Step 8: Full rewrite of pattern 13 (SUBOPTIMAL SERVER CONFIGURATION)**

```
old_string:
## 13. SUBOPTIMAL SERVER CONFIGURATION

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào query `pg_settings` trong db-report-generator v4. Dùng Verify query bên dưới như một truy vấn thủ công.
- **Priority**: P1 (shared_buffers < 15% RAM) | P2 (work_mem < 4MB)
- **Reference**: `conn-limits.md`
- **Category**: DB-side / Configuration (thủ công)

**Fix Template (ví dụ server 16GB RAM):**
```sql
-- Quan trọng nhất
ALTER SYSTEM SET shared_buffers = '4GB';           -- 25% RAM
ALTER SYSTEM SET effective_cache_size = '12GB';     -- 75% RAM
ALTER SYSTEM SET work_mem = '64MB';                 -- Cho complex sorts/joins
ALTER SYSTEM SET maintenance_work_mem = '1GB';      -- Cho VACUUM/CREATE INDEX

-- I/O tuning (SSD)
ALTER SYSTEM SET random_page_cost = 1.1;            -- Mặc định 4.0 cho HDD
ALTER SYSTEM SET effective_io_concurrency = 200;     -- Mặc định 1

-- WAL tuning
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Requires restart cho shared_buffers
-- Các config khác chỉ cần: SELECT pg_reload_conf();
```

**Verify:**
```sql
SELECT name, setting, unit, boot_val, reset_val
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem', 'effective_cache_size',
  'random_page_cost', 'effective_io_concurrency');
```

**Expected Impact**: 2-5x overall performance improvement

new_string:
## 13. SUBOPTIMAL SERVER CONFIGURATION

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào query `pg_settings` trong db-report-generator v4. Dùng Verify query bên dưới như một truy vấn thủ công.
- **Priority**: P1 (shared_buffers < 15% RAM) | P2 (work_mem < 4MB)
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: `conn-limits.md`
- **Category**: DB-side / Configuration (thủ công)

**Fix Template (ví dụ server 16GB RAM):** (KHÔNG đưa vào block chạy-liền — chỉ tham khảo cho review thủ công)
```sql
-- CHỈ áp dụng khi capabilities.managed == false VÀ capabilities.is_superuser == true — managed platform (Supabase/RDS) không hỗ trợ ALTER SYSTEM, đổi qua console/dashboard của nhà cung cấp.

-- Quan trọng nhất
ALTER SYSTEM SET shared_buffers = '4GB';           -- 25% RAM
ALTER SYSTEM SET effective_cache_size = '12GB';     -- 75% RAM
ALTER SYSTEM SET work_mem = '64MB';                 -- Cho complex sorts/joins
ALTER SYSTEM SET maintenance_work_mem = '1GB';      -- Cho VACUUM/CREATE INDEX

-- I/O tuning (SSD)
ALTER SYSTEM SET random_page_cost = 1.1;            -- Mặc định 4.0 cho HDD
ALTER SYSTEM SET effective_io_concurrency = 200;     -- Mặc định 1

-- WAL tuning
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Requires restart cho shared_buffers
-- Các config khác chỉ cần: SELECT pg_reload_conf();
```

**Verify:**
```sql
SELECT name, setting, unit, boot_val, reset_val
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem', 'effective_cache_size',
  'random_page_cost', 'effective_io_concurrency');
```

**recovery_or_rollback:**
```sql
ALTER SYSTEM RESET shared_buffers;
ALTER SYSTEM RESET effective_cache_size;
ALTER SYSTEM RESET work_mem;
ALTER SYSTEM RESET maintenance_work_mem;
ALTER SYSTEM RESET random_page_cost;
ALTER SYSTEM RESET effective_io_concurrency;
ALTER SYSTEM RESET wal_buffers;
ALTER SYSTEM RESET checkpoint_completion_target;
SELECT pg_reload_conf();
```

**Expected Impact**: Phụ thuộc vào workload cụ thể — selectivity của query, kích thước working set so với RAM, và tỷ lệ cache hit hiện tại. Không có con số cố định; đo lại `db_health.cache_hit_ratio` và query latency sau khi áp dụng để đánh giá tác động thực tế.
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_solution_index.py -v`
Expected: PASS — all tests (17 previous + 7 new = 24) green.

- [ ] **Step 10: Commit**

```bash
git add references/kb/solution-index.md tests/unit/test_solution_index.py
git commit -m "feat(p6): tag all 19 solution-index patterns with remediation_class, restructure dangerous-tier fixes"
```

---

### Task 3: Rewrite `SKILL.md` §8.3/§8.5/References + delete `queries-solutions.sql`

**Files:**
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\SKILL.md`
- Delete: `E:\Work\db-report-portable\.agents\skills\db-report-generator\references\queries-solutions.sql` (via `git rm`)
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_skill_docs.py`

**Interfaces:**
- Consumes: `remediation-policy.md` (Task 1) by path reference; `remediation_class`/`recovery_or_rollback` terminology (Tasks 1-2).
- Produces: nothing new consumed by later tasks — Task 4 (`template-solutions-report.md`) is edited independently but must stay terminologically consistent (`recovery_or_rollback`, dangerous-tier exclusion wording).

- [ ] **Step 1: Write the failing tests**

Append to `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_skill_docs.py`:

```python
def test_skill_md_no_longer_references_queries_solutions_sql(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "queries-solutions.sql" not in text


def test_queries_solutions_sql_file_removed(skill_dir):
    p = skill_dir / "references" / "queries-solutions.sql"
    assert not p.exists()


def test_skill_md_generate_fix_sql_uses_recovery_or_rollback(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "recovery_or_rollback" in text
    assert "rollback statement nếu applicable" not in text


def test_skill_md_references_remediation_policy(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "references/remediation-policy.md" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: FAIL — the 4 new tests fail (`SKILL.md` still references `queries-solutions.sql`, file still exists, no `recovery_or_rollback`/`remediation-policy.md` references yet).

- [ ] **Step 3: Rewrite §8.3**

```
old_string:
#### 8.3 Chạy Solution Queries

Execute queries từ `references/queries-solutions.sql` để thu thập:
- Missing FK indexes → auto-generate CREATE INDEX statements
- Duplicate indexes → auto-generate DROP INDEX statements
- Tables cần VACUUM → auto-generate VACUUM commands
- Server config comparison → generate ALTER SYSTEM statements
- Partition candidates (tables > 1M rows)
- Index bloat → generate REINDEX statements
- Idle connections → generate pg_terminate_backend statements

new_string:
#### 8.3 Tra Cứu Remediation Class

Với mỗi vấn đề đã match được từ `references/kb/solution-index.md`, đọc trường `Remediation Class` của pattern đó (5-tier taxonomy — xem chi tiết tại `references/remediation-policy.md`):
- `observe-only`, `controlled-diagnostic`, `maintenance-review`, `ddl-review` → có thể đưa fix vào script "SẴN SÀNG CHẠY" tương ứng theo priority (P0/P1/P2).
- `dangerous` → KHÔNG đưa vào script "SẴN SÀNG CHẠY". Đưa vào mục riêng "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" của `PERFORMANCE_SOLUTIONS.md`.
- Với fix liên quan `ALTER SYSTEM`, kiểm tra `report_data.json` → `capabilities.managed` và `capabilities.is_superuser` trước khi quyết định đưa vào (chi tiết ở `references/remediation-policy.md` mục 3).
```

- [ ] **Step 4: Rewrite §8.5**

```
old_string:
#### 8.5 Generate Fix SQL

Với mỗi vấn đề, tạo SQL fix cụ thể:

1. Lấy fix template từ `solution-index.md`
2. Thay thế placeholders bằng actual table names, column names, schema names từ diagnostic data
3. Thêm `CONCURRENTLY` cho tất cả CREATE/DROP INDEX (production safety)
4. Thêm verification query sau mỗi fix
5. Thêm rollback statement nếu applicable

new_string:
#### 8.5 Generate Fix SQL

Với mỗi vấn đề, tạo SQL fix cụ thể:

1. Lấy fix template từ `solution-index.md`
2. Thay thế placeholders bằng actual table names, column names, schema names từ diagnostic data
3. Thêm `CONCURRENTLY` cho tất cả CREATE/DROP INDEX, đặt trong SQL block RIÊNG tách biệt khỏi mọi transaction block khác; ghi kèm cảnh báo về index `INVALID` nếu câu lệnh thất bại giữa chừng (xem `references/remediation-policy.md` mục 4)
4. Thêm verification query sau mỗi fix
5. Thêm `recovery_or_rollback` cho mỗi fix (xem `references/remediation-policy.md` mục 2 để biết quy ước theo từng loại fix)
6. Nếu `Remediation Class` của fix là `dangerous`, KHÔNG đưa fix đó vào bất kỳ script "SẴN SÀNG CHẠY" nào — đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" thay thế
```

- [ ] **Step 5: Rewrite "SQL Query References" section**

```
old_string:
## SQL Query References

Các query đầy đủ và giải thích chi tiết:
- `references/queries-overview.sql` - Queries tổng quan database
- `references/queries-performance.sql` - Queries phân tích hiệu suất
- `references/queries-index.sql` - Queries phân tích index
- `references/queries-solutions.sql` - Queries tạo fix SQL statements ⭐ NEW

new_string:
## SQL Query References

Các query đầy đủ và giải thích chi tiết:
- `references/queries-overview.sql` - Queries tổng quan database
- `references/queries-performance.sql` - Queries phân tích hiệu suất
- `references/queries-index.sql` - Queries phân tích index
- `references/remediation-policy.md` - Chính sách an toàn 5-tier cho mọi remediation SQL ⭐ NEW
```

- [ ] **Step 6: Rewrite "Solution Engine" section**

```
old_string:
## Solution Engine

Hệ thống tạo giải pháp dựa trên knowledge base đóng gói nội bộ tại `references/kb/` (nguồn: supabase-postgres-best-practices, xem `references/kb/_index.md`):
- `references/kb/solution-index.md` - Master mapping: 19 problem patterns → concrete fixes
- Mỗi fix bao gồm: SQL template, verification query, rollback, expected impact
- Priority rules: P0 (24h) → P1 (1 tuần) → P2 (1 tháng) → P3 (sprint sau)

new_string:
## Solution Engine

Hệ thống tạo giải pháp dựa trên knowledge base đóng gói nội bộ tại `references/kb/` (nguồn: supabase-postgres-best-practices, xem `references/kb/_index.md`):
- `references/kb/solution-index.md` - Master mapping: 19 problem patterns → concrete fixes, mỗi pattern gắn `remediation_class`
- Mỗi fix bao gồm: SQL template, verification query, `recovery_or_rollback`, expected impact
- Priority rules: P0 (24h) → P1 (1 tuần) → P2 (1 tháng) → P3 (sprint sau)
- An toàn: xem `references/remediation-policy.md` cho 5-tier taxonomy và quy tắc gating theo capability
```

- [ ] **Step 7: Delete `references/queries-solutions.sql`**

```bash
git rm references/queries-solutions.sql
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: PASS — all tests (5 previous + 4 new = 9) green.

- [ ] **Step 9: Commit**

```bash
git add SKILL.md tests/unit/test_skill_docs.py
git commit -m "feat(p6): rewrite SKILL.md remediation lookup flow, drop queries-solutions.sql auto-gen framing"
```

---

### Task 4: Rewrite `references/template-solutions-report.md` — dangerous-tier exclusion + recovery_or_rollback + version bump

**Files:**
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\references\template-solutions-report.md`
- Modify: `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_skill_docs.py`

**Interfaces:**
- Consumes: `recovery_or_rollback` terminology and dangerous-tier exclusion concept from Tasks 1-3.
- Produces: final task — no downstream consumers within this plan.

- [ ] **Step 1: Write the failing tests**

Append to `E:\Work\db-report-portable\.agents\skills\db-report-generator\tests\unit\test_skill_docs.py`:

```python
def test_solutions_template_has_dangerous_section_excluded_from_scripts(skill_dir):
    text = (skill_dir / "references" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" in text
    assert "dangerous_solutions" in text
    assert "Đã loại trừ mọi fix remediation_class=dangerous" in text


def test_solutions_template_uses_recovery_or_rollback(skill_dir):
    text = (skill_dir / "references" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "{{recovery_or_rollback_sql}}" in text
    assert "{{rollback_sql}}" not in text
    assert "**Hoàn tác" not in text


def test_solutions_template_footer_version_v4(skill_dir):
    text = (skill_dir / "references" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "db-report-generator v4" in text
    assert "v3.0.0" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: FAIL — the 3 new tests fail (template still says "Hoàn tác"/`{{rollback_sql}}`, no dangerous section, footer still v3.0.0).

- [ ] **Step 3: Rename P0-loop "Hoàn tác" heading**

```
old_string:
**Hoàn tác (nếu cần revert):**
```sql
{{rollback_sql}}
```

new_string:
**recovery_or_rollback (nếu cần revert):**
```sql
{{recovery_or_rollback_sql}}
```
```

- [ ] **Step 4: Rewrite "SCRIPT SQL SẴN SÀNG CHẠY" section**

```
old_string:
## SCRIPT SQL SẴN SÀNG CHẠY

> **CẢNH BÁO**: Review kỹ trước khi chạy. Luôn test trên staging trước.
> Scripts sắp xếp theo độ ưu tiên. Chạy P0 trước.

### Script 1: Sửa Lỗi P0 Nghiêm Trọng
```sql
-- ================================================
-- SỬA LỖI P0 NGHIÊM TRỌNG - {{report_date}}
-- Database: {{CatalogName}}
-- ================================================

{{#each p0_scripts}}
-- [P0-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 2: Sửa Lỗi P1 Ưu Tiên Cao
```sql
-- ================================================
-- SỬA LỖI P1 ƯU TIÊN CAO - {{report_date}}
-- ================================================

{{#each p1_scripts}}
-- [P1-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 3: Sửa Lỗi P2 Trung Bình
```sql
-- ================================================
-- SỬA LỖI P2 TRUNG BÌNH - {{report_date}}
-- ================================================

{{#each p2_scripts}}
-- [P2-{{@index}}] {{description}}
{{sql}}

{{/each}}
```

new_string:
## SCRIPT SQL SẴN SÀNG CHẠY

> **CẢNH BÁO**: Review kỹ trước khi chạy. Luôn test trên staging trước.
> Scripts sắp xếp theo độ ưu tiên. Chạy P0 trước.
> Các fix có `remediation_class: dangerous` KHÔNG BAO GIỜ xuất hiện trong các script dưới đây — xem mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" bên dưới.

### Script 1: Sửa Lỗi P0 Nghiêm Trọng
```sql
-- ================================================
-- SỬA LỖI P0 NGHIÊM TRỌNG - {{report_date}}
-- Database: {{CatalogName}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p0_scripts}}
-- [P0-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 2: Sửa Lỗi P1 Ưu Tiên Cao
```sql
-- ================================================
-- SỬA LỖI P1 ƯU TIÊN CAO - {{report_date}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p1_scripts}}
-- [P1-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 3: Sửa Lỗi P2 Trung Bình
```sql
-- ================================================
-- SỬA LỖI P2 TRUNG BÌNH - {{report_date}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p2_scripts}}
-- [P2-{{@index}}] {{description}}
{{sql}}

{{/each}}
```

### GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)

> Các fix dưới đây thuộc tier `dangerous` (DROP INDEX, pg_terminate_backend, partition migration, ALTER SYSTEM, ...). KHÔNG được đưa vào script chạy-liền ở trên — mỗi fix cần được đọc, hiểu rủi ro, và chạy thủ công từng câu lệnh một sau khi review.

{{#each dangerous_solutions}}
#### {{description}}

**Lý do dangerous**: {{danger_reason}}

```sql
{{fix_sql}}
```

**recovery_or_rollback:**
```sql
{{recovery_or_rollback_sql}}
```

{{/each}}
{{#if no_dangerous}}
_Không có phát hiện nào thuộc tier `dangerous` trong lần phân tích này._
{{/if}}
```

- [ ] **Step 5: Bump footer version**

```
old_string:
*Báo cáo được tạo tự động bởi db-report-generator v3.0.0 kết hợp supabase-postgres-best-practices*

new_string:
*Báo cáo được tạo tự động bởi db-report-generator v4.0.0 kết hợp supabase-postgres-best-practices*
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: PASS — all tests (9 from Task 3 + 3 new = 12) green.

- [ ] **Step 7: Run full unit suite**

Run: `python -m pytest tests/unit -v` (from skill root)
Expected: PASS — zero new regressions beyond the known pre-existing Docker/live-Postgres integration baseline (6 failures: test_analyzer schema-valid, sampler_live x2, stale_stats, stat_io, wal_hot).

- [ ] **Step 8: Commit**

```bash
git add references/template-solutions-report.md tests/unit/test_skill_docs.py
git commit -m "feat(p6): add dangerous-tier exclusion section to solutions template, recovery_or_rollback terminology, v4.0.0 footer"
```

---

## Self-Review

**1. Spec coverage:**
- §0.A6 5-tier taxonomy → Task 1 (`remediation-policy.md`), Task 2 (per-pattern tagging). ✅
- `recovery_or_rollback` field rename → Task 1 (§2), Task 2 (patterns 5/6/7/11/13), Task 3 (§8.5 step 5), Task 4 (P0-loop heading + dangerous section). ✅
- CONCURRENTLY separate block + INVALID warning → Task 1 (§4), Task 3 (§8.5 step 3). ✅
- Partition template drops data-losing swap → Task 2 Step 7 (pattern 11), Task 1 (§5). ✅
- `pg_terminate_backend` idle-in-transaction only → Task 1 (§6), Task 2 Step 5/6 (patterns 6/7) + tests. ✅
- Server-config self-hosted vs managed gating → Task 1 (§3), Task 2 Step 5/6/8 (patterns 6/7/13) + tests. ✅
- Gate: dangerous has no run-immediately block → Task 2 (all 5 dangerous patterns marked + "KHÔNG đưa vào block chạy-liền"), Task 4 (dangerous section separated from scripts). ✅
- Gate: managed path never emits ALTER SYSTEM → Task 1 §3, Task 2 patterns 6/7/13 capability-gate comments + tests. ✅
- Gate: every remediation has recovery_or_rollback → Task 2 patterns 5/6/7/11/13 all get recovery_or_rollback blocks/prose; other 14 patterns already have their own established Reference/Fix Template shape unaffected by this phase's remediation_class-only mechanical insertion (out of scope for full rewrite, per plan's file structure). Confirmed acceptable since roadmap's acceptance gate is about the newly-restructured dangerous patterns and the policy document, not retrofitting all 19.
- `queries-solutions.sql` deletion → Task 3 Step 7. ✅
- No schema.json/scripts changes → confirmed throughout, no task touches `scripts/*.py` or `report-data.schema.json`. ✅

**2. Placeholder scan:** All SQL/Markdown content in every step is complete, verbatim text — no "TBD"/"similar to Task N"/"add appropriate X" phrases present. All old_string/new_string pairs contain full literal text.

**3. Type/name consistency:** `remediation_class` (snake_case, used in prose/Handlebars) vs "Remediation Class" (Title Case, used as the KB heading label) — verified both forms are used consistently in their respective contexts (KB headings always Title Case per existing `solution-index.md` convention matching "Priority"/"Reference"/"Category"; prose and template placeholders always snake_case matching `{{sql}}`/`{{description}}` existing convention). `recovery_or_rollback` (field name) vs `recovery_or_rollback_sql` (Handlebars placeholder, matching existing `rollback_sql`→now renamed convention) — consistent across Tasks 1-4. `dangerous_solutions`/`fix_sql`/`danger_reason`/`no_dangerous` are new Handlebars placeholders introduced only in Task 4 — since `template-solutions-report.md` is illustrative (agent-authored narratively, not literally executed per spec §0.A1), these are documentation of intended shape, not a code contract requiring cross-task interface validation.

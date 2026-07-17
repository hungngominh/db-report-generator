# Phase 5 — Nối KB Thật (KB Mapping by Rule IDs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `references/kb/solution-index.md` so every problem pattern's `Detection` field cites a real, verified db-report-generator v4 signal (diagnostic block + field + finding_id, or an honest "no collector"/"code-analysis" label) instead of stale v3 pseudo-SQL conditions, fix the two known-wrong `Reference` citations, and add coverage for signals P1-P4 introduced with no KB mapping at all.

**Architecture:** Documentation-only phase — no new Python. `solution-index.md` is read by the agent at SKILL.md Bước 8 (Generate Performance Solutions); nothing in `scripts/` parses it programmatically (verified: `grep -rln "solution-index" --include="*.py"` returns nothing). Every existing pattern's four-line header block (`Detection`/`Priority`/`Reference`/`Category`) gets rewritten to name the exact diagnostic block, field, and finding_id it maps to (verified against the live `references/rules/*.json` files and collector source in this same research pass — not re-derived from memory). Six new pattern entries (14-19) are appended for signals that P1-P4 introduced but that `solution-index.md` never mapped: RLS re-eval (P4.3), stale stats (P2.7), EXPLAIN-attached plan (P4.1), column-level index suggestion (P4.2), query ranking by total time (P1.2), and schema hygiene issues (P4.4 — missing PK / oversized UUIDv4 PK / timestamp without timezone, discovered this session to have zero existing KB coverage). One new KB body file (`security-sql-injection.md`) replaces a dangling citation to a nonexistent "Security best practices" file.

**Tech Stack:** Markdown (KB files), pytest (`tests/unit/test_solution_index.py`, `tests/unit/test_skill_docs.py`) using the existing `skill_dir` fixture from `conftest.py`.

## Global Constraints

- Every `**Reference**:` field in `solution-index.md` must point to a file that exists under `references/kb/` (§0.C — the KB is self-contained; no external filesystem paths). A `Reference:` line inside a KB body file's closing citation (e.g. a Supabase/OWASP URL) is a knowledge-source citation, not a filesystem path, and is exempt from this rule.
- No `Reference:` field may cite a filename that does not exist on disk, and no field may cite a file whose topic is the wrong direction for the pattern (e.g. citing a "missing index" file for a "drop unused index" pattern) — per spec §11, both of these are explicitly called out as bugs to fix (pattern 9's dangling "Security best practices" citation, pattern 5's wrong-direction `query-missing-indexes.md` citation).
- Acceptance gate (§11): at least 8 of the 13 original (v3-era) patterns must be connected to a real, verifiable tool signal (an actual diagnostic block/field, or the established code-analysis + confidence-tier methodology from SKILL.md §5.8). Patterns with genuinely no collector backing must be marked as manual/operator-only ("gợi ý thủ công") rather than presented as automated. This plan connects 10/13 (1, 3, 4, 5, 6, 7, 8, 9, 10, 12) and marks 3/13 as manual (2, 11, 13) — the gate is enforced by an executable test (`test_at_least_8_of_13_legacy_patterns_have_connected_detection`), not just prose.
- Every diagnostic block name, field name, and finding_id cited anywhere in this plan was verified against the live source in this research session (`references/rules/*.json`, `scripts/collectors/*.py`) — not reconstructed from memory. Do not substitute a "similar-sounding" name during implementation; use the exact names given in each task's Steps.
- Do not modify the trailing `## Priority Assignment Rules` table's existing 23 rows — it is a legacy quick-reference matrix for patterns 1-13 only and is explicitly out of scope for this phase (only a one-line prose note is added above it, in Task 3, clarifying its scope).
- Do not modify `scripts/` in this phase — P5 is documentation-only per spec §11 framing ("Nối KB thật" = connect existing KB docs to existing signals, introduce no new collector).
- Do not touch SKILL.md Bước 8.2's per-bullet detection-criteria list (lines ~750-770) beyond the single pattern-count fix in Task 3 — rewriting that list's stale v3-style bullets (`cache_hit_pct < 90%`, etc.) is out of scope for this phase; `solution-index.md` is the authoritative mapping the agent actually reads at Bước 8.1, and fixing Bước 8.2 in full is a larger, separate cleanup not requested by spec §11.

---

### Task 1: New KB file for SQL injection + register it in `_index.md`

**Files:**
- Create: `references/kb/security-sql-injection.md`
- Modify: `references/kb/_index.md`
- Test: `tests/unit/test_solution_index.py` (new file)

**Interfaces:**
- Consumes: nothing from prior phases — pure documentation.
- Produces: a KB body file at `references/kb/security-sql-injection.md` that Task 2 will cite from `solution-index.md` pattern 9's `Reference` field (replacing the dangling "Security best practices" citation).

The current `references/kb/_index.md` (verified this session, full file, 80 lines) has this exact structure relevant to this task:

```
## Danh sách file (31)

**Query Performance** (`query-`)
- `query-composite-indexes.md`
...
**Security & RLS** (`security-`)
- `security-privileges.md`
- `security-rls-basics.md`
- `security-rls-performance.md`

**Schema Design** (`schema-`)
...
---

*30 topic file + 1 solution engine = 31 file. Đồng bộ từ `supabase-postgres-best-practices/references/` ngày 2026-07-16.*
```

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_solution_index.py`:

```python
def test_security_sql_injection_kb_file_exists(skill_dir):
    p = skill_dir / "references" / "kb" / "security-sql-injection.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "parameterized" in text.lower() or "tham số hóa" in text.lower()
    assert "%s" in text  # psycopg2-style parameter placeholder example


def test_kb_index_lists_security_sql_injection(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "- `security-sql-injection.md`" in text


def test_kb_index_file_count_updated(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "## Danh sách file (32)" in text
    assert "## Danh sách file (31)" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_solution_index.py -v`
Expected: FAIL — `security-sql-injection.md` does not exist; `_index.md` still says "(31)" and lacks the new bullet.

- [ ] **Step 3: Create the KB file**

Create `references/kb/security-sql-injection.md`:

```markdown
---
title: Prevent SQL Injection with Parameterized Queries
impact: CRITICAL
impactDescription: Eliminates the #1 database attack vector; prevents data breach, data loss, or full database compromise
tags: security, sql-injection, parameterized-queries, orm
---

## Prevent SQL Injection with Parameterized Queries

String-concatenated or interpolated SQL lets an attacker inject arbitrary SQL through user input. Always bind user input as query parameters — never build SQL text by concatenating or interpolating values.

**Incorrect (string concatenation — injectable):**

```sql
-- C# / .NET
var sql = "SELECT * FROM users WHERE email = '" + email + "'";
var cmd = new SqlCommand(sql, connection);

-- Python
cur.execute("SELECT * FROM users WHERE email = '" + email + "'")
cur.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

**Correct (parameterized query):**

```sql
-- C# / .NET
var sql = "SELECT * FROM users WHERE email = @email";
var cmd = new SqlCommand(sql, connection);
cmd.Parameters.AddWithValue("@email", email);

-- Python (psycopg2)
cur.execute("SELECT * FROM users WHERE email = %s", (email,))

-- Python (psycopg2, named params)
cur.execute("SELECT * FROM users WHERE email = %(email)s", {"email": email})
```

ORM query builders (Entity Framework, Dapper with parameters, SQLAlchemy, Django ORM) parameterize automatically — the risk is specifically raw/dynamic SQL built with string concatenation or f-strings/string interpolation.

Reference: [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
```

- [ ] **Step 4: Register the file in `_index.md`**

In `references/kb/_index.md`, apply these 3 edits:

Edit A — file count heading:

```
- old: ## Danh sách file (31)
- new: ## Danh sách file (32)
```

Edit B — Security & RLS file list:

```
- old:
**Security & RLS** (`security-`)
- `security-privileges.md`
- `security-rls-basics.md`
- `security-rls-performance.md`

- new:
**Security & RLS** (`security-`)
- `security-privileges.md`
- `security-rls-basics.md`
- `security-rls-performance.md`
- `security-sql-injection.md`
```

Edit C — footer count line:

```
- old: *30 topic file + 1 solution engine = 31 file. Đồng bộ từ `supabase-postgres-best-practices/references/` ngày 2026-07-16.*
- new: *31 topic file + 1 solution engine = 32 file. 30 file gốc đồng bộ từ `supabase-postgres-best-practices/references/` ngày 2026-07-16; `security-sql-injection.md` thêm mới trong Phase 5 (2026-07-17) để khớp code-analysis finding "SQL Injection Risk" (pattern 9, xem `solution-index.md`).*
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_solution_index.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 6: Commit**

```bash
git add references/kb/security-sql-injection.md references/kb/_index.md tests/unit/test_solution_index.py
git commit -m "docs(p5): add security-sql-injection.md KB file, register in _index.md"
```

---

### Task 2: Standardize `Detection`/`Reference` fields for patterns 1-13 in `solution-index.md`

**Files:**
- Modify: `references/kb/solution-index.md`
- Test: `tests/unit/test_solution_index.py` (append)

**Interfaces:**
- Consumes: `security-sql-injection.md` from Task 1 (cited in pattern 9's rewritten `Reference` field).
- Produces: every pattern 1-13 `Detection` line now names a real diagnostic block/field/finding_id (or is honestly marked manual/code-analysis) for Task 3 and any future reader to rely on. No new interface for later tasks beyond the file's own content — Task 3 appends new patterns after this file's structure is finalized, so run this task's edits first.

The current `references/kb/solution-index.md` (verified this session, full file read, 492 lines) has the exact structure shown in each edit's `old` block below — every edit's `old` string is copied verbatim from the live file, confirmed unique within it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_solution_index.py`:

```python
def test_solution_index_version_bumped(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    assert 'version: "2.0.0"' in text


def test_solution_index_has_detection_legend(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    assert "Chú giải Detection" in text
    for label in ("[Tự động]", "[Tự động, một phần]", "[Code-analysis]", "[Gợi ý thủ công"):
        assert label in text


def test_pattern_5_no_longer_cites_missing_indexes_reference(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 5. UNUSED INDEXES")
    end = text.index("## 6. CONNECTION EXHAUSTION")
    block = text[start:end]
    assert "query-missing-indexes.md" not in block


def test_pattern_9_cites_real_sql_injection_kb_file(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 9. SQL INJECTION RISK")
    end = text.index("## 10. MISSING PAGINATION")
    block = text[start:end]
    assert "`security-sql-injection.md`" in block
    assert "Security best practices" not in block


def test_manual_only_patterns_marked_explicitly(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 2. HIGH SEQUENTIAL SCAN RATIO", "## 3. HIGH DEAD TUPLE RATIO"),
        ("## 11. LARGE TABLE WITHOUT PARTITIONING", "## 12. MISSING FOREIGN KEY INDEXES"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## Priority Assignment Rules"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "Gợi ý thủ công" in block
        assert "không có collector" in block.lower()


def test_automated_patterns_cite_real_diagnostic_blocks(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    checks = {
        "## 1. LOW CACHE HIT RATIO": ("database_stats", "db_health.cache_hit_ratio"),
        "## 3. HIGH DEAD TUPLE RATIO": ("dead_tuples", "maintenance.dead_tuples_pct"),
        "## 4. SLOW QUERIES": ("query_stats", "query_perf.slow_query_mean_exec_time"),
        "## 6. CONNECTION EXHAUSTION": ("connection_depth", "connections.cluster_pressure"),
        "## 7. BLOCKING QUERIES": ("blocking", "connections.blocking"),
        "## 12. MISSING FOREIGN KEY INDEXES": ("fk_missing_index", "maintenance.fk_missing_index"),
    }
    for heading, (block_name, finding_id) in checks.items():
        idx = text.index(heading)
        section = text[idx:idx + 1200]
        assert f"`{block_name}`" in section, heading
        assert finding_id in section, heading


def test_code_analysis_patterns_reference_confidence_tiers(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading in ("## 8. N+1 QUERY PATTERN", "## 9. SQL INJECTION RISK", "## 10. MISSING PAGINATION"):
        idx = text.index(heading)
        section = text[idx:idx + 600]
        assert "SKILL.md" in section
        assert "Code-analysis" in section


def test_no_reference_field_points_outside_kb(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("- **Reference**"):
            assert "../" not in line
            assert "supabase-postgres-best-practices" not in line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_solution_index.py -v -k "version_bumped or detection_legend or pattern_5 or pattern_9 or manual_only or automated_patterns or code_analysis or reference_field"`
Expected: FAIL — none of these strings/labels exist in the current file yet.

- [ ] **Step 3: Rewrite frontmatter + intro, add the Detection legend**

In `references/kb/solution-index.md`:

```
- old:
---
title: Solution Index - Problem-to-Fix Mapping
description: Maps detected DB/code problems to concrete solutions. Used by db-report-generator v3.0+ as the solution engine.
version: "1.0.0"
---

# Solution Index

Mỗi entry mapping: **Problem Pattern → Concrete Fix + Priority + Impact**

Khi db-report-generator phát hiện vấn đề, nó tra cứu file này để tạo PERFORMANCE_SOLUTIONS.md với SQL/code fix sẵn sàng chạy.

---

- new:
---
title: Solution Index - Problem-to-Fix Mapping
description: Maps detected DB/code problems (19 patterns, signal-verified P5) to concrete solutions. Used by db-report-generator v4.0+ as the solution engine.
version: "2.0.0"
---

# Solution Index

Mỗi entry mapping: **Problem Pattern → Concrete Fix + Priority + Impact**

Khi db-report-generator phát hiện vấn đề, nó tra cứu file này để tạo PERFORMANCE_SOLUTIONS.md với SQL/code fix sẵn sàng chạy.

> **Chú giải Detection** (P5 — nối KB thật với tín hiệu tool thật): `[Tự động]` = tool tự thu thập signal và đánh giá qua rule engine (`scripts/rules.py`) → có `finding_id` xuất hiện trong report findings. `[Tự động, một phần]` = signal có thật trong diagnostics nhưng chưa có rule/finding_id riêng, hoặc bị giới hạn phạm vi thu thập — cần agent tra thủ công trong `report_data.json`. `[Code-analysis]` = agent tự grep/đọc code theo SKILL.md §5.8, có gán độ tin cậy (`measured`/`estimated`/`heuristic`), KHÔNG phải collector Python. `[Gợi ý thủ công — không có collector]` = KHÔNG có signal tự động nào — chỉ là gợi ý cho operator tự kiểm tra, KHÔNG xuất hiện trong report.

---
```

- [ ] **Step 4: Rewrite pattern 1's header block**

```
- old:
## 1. LOW CACHE HIT RATIO (Table-Level)

- **Detection**: `cache_hit_pct < 90` từ `pg_statio_user_tables`
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`
- **Category**: DB-side / Index

- new:
## 1. LOW CACHE HIT RATIO (Database-Level)

- **Detection**: [Tự động] Diagnostic block `database_stats`, field `cache_hit_ratio` (0.0–1.0, KHÔNG phải `_pct`) → finding_id `db_health.cache_hit_ratio` (red < 0.80, yellow < 0.90; `references/rules/db-health.json`). LƯU Ý: đây là cache hit ratio cấp DATABASE, không phải cấp table — không có collector nào query `pg_statio_user_tables`. Cho cache hit cấp INDEX, xem block `index_io` / finding_id `query_perf.index_cache_hit_ratio`.
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`
- **Category**: DB-side / Index
```

- [ ] **Step 5: Rewrite pattern 2's header block**

```
- old:
## 2. HIGH SEQUENTIAL SCAN RATIO

- **Detection**: `seq_scan_pct > 50` AND `n_live_tup > 10000`
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`
- **Category**: DB-side / Index

- new:
## 2. HIGH SEQUENTIAL SCAN RATIO

- **Detection**: [Gợi ý thủ công — không có collector] Không có block/collector nào trong db-report-generator v4 thu thập `seq_scan`/`idx_scan` cấp table (`pg_stat_user_tables`). Đây KHÔNG phải một automated finding — dùng Fix Template bên dưới như một truy vấn thủ công khi nghi ngờ table bị seq scan nhiều (vd. khi thấy `Seq Scan` trong EXPLAIN plan của mục 4/16).
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`
- **Category**: DB-side / Index (thủ công)
```

- [ ] **Step 6: Rewrite pattern 3's header block**

```
- old:
## 3. HIGH DEAD TUPLE RATIO

- **Detection**: `dead_pct > 5` từ `pg_stat_user_tables`
- **Priority**: P0 (> 50%) | P1 (20-50%) | P2 (5-20%)
- **Reference**: `monitor-vacuum-analyze.md`
- **Category**: DB-side / Maintenance

- new:
## 3. HIGH DEAD TUPLE RATIO

- **Detection**: [Tự động] Diagnostic block `dead_tuples`, field `dead_pct` → finding_id `maintenance.dead_tuples_pct` (red > 20%, yellow > 5%; `references/rules/maintenance.json`, row_identity `schema,table`). Block trả `n_live`/`n_dead` (KHÔNG phải `n_live_tup`/`n_dead_tup` như tên cột gốc `pg_stat_user_tables`).
- **Priority**: P0 (> 50%) | P1 (20-50%) | P2 (5-20%)
- **Reference**: `monitor-vacuum-analyze.md`
- **Category**: DB-side / Maintenance
```

- [ ] **Step 7: Rewrite pattern 4's header block**

```
- old:
## 4. SLOW QUERIES (High Mean Execution Time)

- **Detection**: `mean_exec_time > 100` từ `pg_stat_statements`
- **Priority**: P0 (> 5000ms) | P1 (1000-5000ms) | P2 (100-1000ms)
- **Reference**: `monitor-explain-analyze.md`, `query-composite-indexes.md`
- **Category**: DB-side / Query + Index

- new:
## 4. SLOW QUERIES (High Mean Execution Time)

- **Detection**: [Tự động] Diagnostic block `query_stats`, field `window_mean_exec_time_ms` (mean trong sampling window, KHÔNG phải `mean_exec_time` tích lũy) → finding_id `query_perf.slow_query_mean_exec_time` (red > 1000ms, yellow > 100ms; `references/rules/query-performance.json`, row_identity `queryid`). EXPLAIN plan tự động gắn kèm top-N query chậm nhất — xem mục 16. Xếp hạng bổ sung theo tổng thời gian × số lần gọi — xem mục 18.
- **Priority**: P0 (> 5000ms) | P1 (1000-5000ms) | P2 (100-1000ms)
- **Reference**: `monitor-explain-analyze.md`, `query-composite-indexes.md`
- **Category**: DB-side / Query + Index
```

- [ ] **Step 8: Rewrite pattern 5's header block**

```
- old:
## 5. UNUSED INDEXES

- **Detection**: `idx_scan = 0` AND NOT `_pkey`
- **Priority**: P2 (< 100MB) | P3 (> 100MB nhưng cần verify 2+ tuần)
- **Reference**: `query-missing-indexes.md`
- **Category**: DB-side / Cleanup

- new:
## 5. UNUSED INDEXES

- **Detection**: [Tự động, một phần — xác nhận thủ công trước khi DROP] Diagnostic block `index_io`, field `idx_scan` = 0. 2 giới hạn: (1) `index_io` chỉ thu top-30 index theo `idx_blks_read`, KHÔNG đầy đủ toàn bộ index của DB; (2) hiện KHÔNG có finding_id/rule riêng cho `idx_scan = 0` (`references/rules/query-performance.json` chỉ có `query_perf.index_cache_hit_ratio` cho block này) — nghĩa là finding này KHÔNG tự xuất hiện trong report's rule-driven findings, chỉ tra được thủ công trong `diagnostics.index_io.metrics`.
- **Priority**: P2 (< 100MB) | P3 (> 100MB nhưng cần verify 2+ tuần)
- **Reference**: _Không có file KB match chính xác cho "unused index cleanup" — `query-missing-indexes.md` nói về vấn đề NGƯỢC LẠI (thiếu index). Dùng Fix Template bên dưới, không cần tài liệu bổ sung._
- **Category**: DB-side / Cleanup
```

- [ ] **Step 9: Rewrite pattern 6's header block**

```
- old:
## 6. CONNECTION EXHAUSTION

- **Detection**: `total_connections > 0.8 * max_connections`
- **Priority**: P0 (> 90%) | P1 (80-90%)
- **Reference**: `conn-pooling.md`, `conn-limits.md`, `conn-idle-timeout.md`
- **Category**: Architecture / Connection Management

- new:
## 6. CONNECTION EXHAUSTION

- **Detection**: [Tự động] Diagnostic block `connection_depth`. 3 finding_id riêng biệt (`references/rules/connections.json`) — KHÔNG gộp chung "total/max" như v3: `connections.cluster_pressure` (tỷ lệ `cluster_connections`/`cluster_max_connections`, red > 0.90, yellow > 0.60), `connections.pool_pressure` (tỷ lệ `db_connections`/`configured_pool_size`, red > 0.90, yellow > 0.60), `connections.idle_in_transaction` (field `longest_txn_seconds`, red > 600s, yellow > 60s).
- **Priority**: P0 (> 90%) | P1 (80-90%)
- **Reference**: `conn-pooling.md`, `conn-limits.md`, `conn-idle-timeout.md`
- **Category**: Architecture / Connection Management
```

- [ ] **Step 10: Rewrite pattern 7's header block**

```
- old:
## 7. BLOCKING QUERIES

- **Detection**: Rows returned từ blocking queries check
- **Priority**: P0
- **Reference**: `lock-short-transactions.md`, `lock-deadlock-prevention.md`
- **Category**: DB-side / Locking

- new:
## 7. BLOCKING QUERIES

- **Detection**: [Tự động] Diagnostic block `blocking`, field `blocked_duration_seconds` (kèm `blocked_pid`, `blocking_pid`, `blocked_query`, `blocking_query`) → finding_id `connections.blocking` (red > 30s, yellow > 5s; `references/rules/connections.json`, row_identity `blocked_pid,blocking_pid`).
- **Priority**: P0
- **Reference**: `lock-short-transactions.md`, `lock-deadlock-prevention.md`
- **Category**: DB-side / Locking
```

- [ ] **Step 11: Rewrite pattern 8's header block**

```
- old:
## 8. N+1 QUERY PATTERN

- **Detection**: Loop chứa DB call bên trong (code analysis)
- **Priority**: P1
- **Reference**: `data-n-plus-one.md`
- **Category**: Code-side / Query Pattern

- new:
## 8. N+1 QUERY PATTERN

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep loop chứa DB call bên trong (không phải collector Python) — confidence tier mặc định `estimated` (cần agent tự xác nhận loop có thực sự gọi DB mỗi vòng), theo bảng độ tin cậy §5.8.
- **Priority**: P1
- **Reference**: `data-n-plus-one.md`
- **Category**: Code-side / Query Pattern
```

- [ ] **Step 12: Rewrite pattern 9's header block**

```
- old:
## 9. SQL INJECTION RISK

- **Detection**: String concatenation trong SQL context
- **Priority**: P0
- **Reference**: Security best practices
- **Category**: Code-side / Security

- new:
## 9. SQL INJECTION RISK

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep string-concatenated/interpolated SQL context — confidence tier `measured` khi chuỗi text nối SQL xuất hiện rõ ràng (vd. `"SELECT * FROM " + table`), theo bảng độ tin cậy §5.8.
- **Priority**: P0
- **Reference**: `security-sql-injection.md`
- **Category**: Code-side / Security
```

- [ ] **Step 13: Rewrite pattern 10's header block**

```
- old:
## 10. MISSING PAGINATION

- **Detection**: Query trả về tất cả rows không có LIMIT
- **Priority**: P1 (tables > 10K rows) | P2 (tables > 1K rows)
- **Reference**: `data-pagination.md`
- **Category**: Code-side / Query Pattern

- new:
## 10. MISSING PAGINATION

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep query trả về tất cả rows không có LIMIT/OFFSET/cursor — confidence tier `heuristic` (suy luận từ việc KHÔNG thấy LIMIT, không phải bằng chứng trực tiếp), theo bảng độ tin cậy §5.8.
- **Priority**: P1 (tables > 10K rows) | P2 (tables > 1K rows)
- **Reference**: `data-pagination.md`
- **Category**: Code-side / Query Pattern
```

- [ ] **Step 14: Rewrite pattern 11's header block**

```
- old:
## 11. LARGE TABLE WITHOUT PARTITIONING

- **Detection**: `n_live_tup > 10,000,000` với time-series column
- **Priority**: P2
- **Reference**: `schema-partitioning.md`
- **Category**: Architecture / Schema

- new:
## 11. LARGE TABLE WITHOUT PARTITIONING

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào kiểm tra partitioning trong db-report-generator v4. Diagnostic block `table_index_size`, field `row_estimate` (từ `pg_class.reltuples`) có thể dùng làm input thủ công để tìm bảng lớn — nhưng KHÔNG có rule/finding_id nào đánh giá `row_estimate`, và việc xác định "time-series column" đòi hỏi agent tự đọc schema thủ công.
- **Priority**: P2
- **Reference**: `schema-partitioning.md`
- **Category**: Architecture / Schema (thủ công)
```

- [ ] **Step 15: Rewrite pattern 12's header block**

```
- old:
## 12. MISSING FOREIGN KEY INDEXES

- **Detection**: FK constraint exists nhưng không có index trên FK column
- **Priority**: P1
- **Reference**: `schema-foreign-key-indexes.md`
- **Category**: DB-side / Index

- new:
## 12. MISSING FOREIGN KEY INDEXES

- **Detection**: [Tự động] Diagnostic block `fk_missing_index`, fields `schema`, `table`, `constraint`, `columns`, `suggested_ddl` → finding_id `maintenance.fk_missing_index` (presence rule, assessment cố định `red`; `references/rules/maintenance.json`, row_identity `schema,table,constraint`).
- **Priority**: P1
- **Reference**: `schema-foreign-key-indexes.md`
- **Category**: DB-side / Index
```

- [ ] **Step 16: Rewrite pattern 13's header block**

```
- old:
## 13. SUBOPTIMAL SERVER CONFIGURATION

- **Detection**: Config khác biệt lớn so với recommendations
- **Priority**: P1 (shared_buffers < 15% RAM) | P2 (work_mem < 4MB)
- **Reference**: `conn-limits.md`
- **Category**: DB-side / Configuration

- new:
## 13. SUBOPTIMAL SERVER CONFIGURATION

- **Detection**: [Gợi ý thủ công — không có collector] Không có block nào query `pg_settings` trong db-report-generator v4. Dùng Verify query bên dưới như một truy vấn thủ công.
- **Priority**: P1 (shared_buffers < 15% RAM) | P2 (work_mem < 4MB)
- **Reference**: `conn-limits.md`
- **Category**: DB-side / Configuration (thủ công)
```

- [ ] **Step 17: Run tests to verify they pass**

Run: `pytest tests/unit/test_solution_index.py -v`
Expected: PASS (all tests including Task 1's)

- [ ] **Step 18: Commit**

```bash
git add references/kb/solution-index.md tests/unit/test_solution_index.py
git commit -m "docs(p5): connect patterns 1-13 Detection fields to real v4 signals, fix wrong citations"
```

---

### Task 3: Add patterns 14-19 for previously-unmapped P1-P4 signals + update pattern-count text

**Files:**
- Modify: `references/kb/solution-index.md`
- Modify: `references/kb/_index.md`
- Modify: `SKILL.md:887`
- Test: `tests/unit/test_solution_index.py` (append), `tests/unit/test_skill_docs.py` (append)

**Interfaces:**
- Consumes: Task 2's finalized patterns 1-13 (new patterns are appended after pattern 13, before `## Priority Assignment Rules`, so Task 2 must land first — its edits and this task's insertion point don't overlap, but appending before Task 2's rewrite would leave a `## Priority Assignment Rules` old_string ambiguous mid-edit).
- Produces: final pattern count (19) referenced in both `references/kb/_index.md` and `SKILL.md` — no further task depends on this.

Verified this session directly against `references/rules/*.json` and collector source (not reconstructed from memory):
- `security-rls.json`: `{"finding_id": "security_rls.rls_policy_issue", "kind": "presence", "block": "rls_policies", "assessment": "yellow", "row_identity_fields": ["schema","table","policy","clause","issue","function","column"]}`. `scripts/collectors/rls_policies.py` metrics rows use `issue` ∈ `{"unwrapped_reeval_call", "missing_supporting_index"}` (per Task 6 brief `.superpowers/sdd/task-*-brief.md` — `unwrapped_reeval_call` sets `function`/clears `column`, `missing_supporting_index` sets `column`/clears `function`).
- `maintenance.json`: `{"finding_id": "maintenance.stale_stats_pct", "kind": "threshold", "block": "stale_stats", "metric_key": "modified_pct", "thresholds": {"red": 50, "yellow": 20}, "row_identity_fields": ["schema","table"]}`.
- No rule targets block `explain` or `index_advisor`'s presence directly except `query_perf.suggested_column_index` (below) — `explain`'s per-row `plan`/`explain_unavailable` fields are read directly by the agent as supporting evidence, not a standalone finding.
- `query-performance.json`: `{"finding_id": "query_perf.suggested_column_index", "kind": "presence", "block": "index_advisor", "assessment": "yellow", "row_identity_fields": ["schema","table","queryid"]}`. `scripts/index_advisor.py` (Task 5) generates COMPOSITE equality-column suggestions only — it does not generate partial or covering (INCLUDE) suggestions.
- `query_stats` block (P1.2, `scripts/collectors/query_stats.py`) metrics carry `window_total_exec_time_ms` and `window_calls`, pre-sorted descending by the sampler — no separate finding_id targets this field (only `window_mean_exec_time_ms` has one, `query_perf.slow_query_mean_exec_time`).
- `maintenance.json`: `{"finding_id": "maintenance.schema_hygiene_issue", "kind": "presence", "block": "schema_checks", "assessment": "yellow", "row_identity_fields": ["schema","table","issue","column"]}`. `scripts/collectors/schema_checks.py` (Task 7) metrics rows use `issue` ∈ `{"missing_primary_key", "oversized_uuid_pk", "timestamp_without_timezone"}`, with `_LARGE_TABLE_ROW_THRESHOLD = 1_000_000` gating `oversized_uuid_pk`. This finding has ZERO existing coverage anywhere in `solution-index.md` — discovered this session; `references/kb/schema-primary-keys.md` (verbatim: "Avoid random UUIDs (v4) as primary keys on large tables (causes index fragmentation)") and `references/kb/schema-data-types.md` (verbatim: `created_at timestamptz, -- Always store timezone-aware timestamps`) already cover both non-PK-absence issues accurately — no new KB file needed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_solution_index.py`:

```python
def test_new_patterns_14_to_19_present(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for n, title_fragment in [
        (14, "RLS POLICY RE-EVALUATION"),
        (15, "STALE TABLE STATISTICS"),
        (16, "EXPLAIN PLAN"),
        (17, "COLUMN-LEVEL INDEX SUGGESTION"),
        (18, "QUERY RANKING"),
        (19, "SCHEMA HYGIENE ISSUES"),
    ]:
        assert f"## {n}. {title_fragment}" in text


def test_pattern_14_rls_cites_real_finding_id(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 14. RLS POLICY RE-EVALUATION")
    section = text[idx:idx + 1200]
    assert "`rls_policies`" in section
    assert "security_rls.rls_policy_issue" in section
    assert "unwrapped_reeval_call" in section
    assert "missing_supporting_index" in section
    assert "`security-rls-performance.md`" in section


def test_pattern_17_notes_composite_only_limitation(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 17. COLUMN-LEVEL INDEX SUGGESTION")
    section = text[idx:idx + 1500]
    assert "index_advisor" in section
    assert "query_perf.suggested_column_index" in section
    assert "không tự sinh" in section.lower()


def test_pattern_19_schema_hygiene_cites_real_finding_id(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 19. SCHEMA HYGIENE ISSUES")
    section = text[idx:idx + 1200]
    assert "`schema_checks`" in section
    assert "maintenance.schema_hygiene_issue" in section
    assert "missing_primary_key" in section
    assert "oversized_uuid_pk" in section
    assert "timestamp_without_timezone" in section
    assert "`schema-primary-keys.md`" in section
    assert "`schema-data-types.md`" in section


def test_kb_index_pattern_count_updated(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "19 problem pattern" in text
    assert "13 problem pattern" not in text


def test_at_least_8_of_13_legacy_patterns_have_connected_detection(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    positions = sorted(text.index(f"## {n}.") for n in range(1, 14))
    positions.append(text.index("## 14."))
    connected = 0
    for i in range(13):
        section = text[positions[i]:positions[i + 1]]
        if "Gợi ý thủ công" not in section:
            connected += 1
    assert connected >= 8
```

Append to `tests/unit/test_skill_docs.py`:

```python
def test_skill_md_solution_engine_pattern_count_matches_solution_index(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "19 problem patterns" in text
    assert "13 problem patterns" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_solution_index.py tests/unit/test_skill_docs.py -v -k "pattern_14_to or pattern_19 or pattern_17 or kb_index_pattern_count or legacy_patterns_have_connected or solution_engine_pattern_count"`
Expected: FAIL — patterns 14-19 don't exist yet; count strings not yet updated.

- [ ] **Step 3: Insert patterns 14-19 before the Priority Assignment Rules table**

In `references/kb/solution-index.md`:

```
- old:
---

## Priority Assignment Rules

- new:
---

## 14. RLS POLICY RE-EVALUATION PERFORMANCE TRAP

- **Detection**: [Tự động] Diagnostic block `rls_policies` → finding_id `security_rls.rls_policy_issue` (presence rule, assessment cố định `yellow`; `references/rules/security-rls.json`, row_identity `schema,table,policy,clause,issue,function,column`). Field `issue` nhận đúng 2 giá trị: `unwrapped_reeval_call` (gọi `auth.uid()`/`auth.role()`/`auth.jwt()`/`current_setting()` KHÔNG bọc trong scalar subselect — field `function` được set, `column` = null) hoặc `missing_supporting_index` (cột dùng trong equality predicate của policy không có index hỗ trợ — field `column` được set, `function` = null).
- **Priority**: P1
- **Reference**: `security-rls-performance.md`
- **Category**: Security / RLS

**Fix Template:**
```sql
-- issue = unwrapped_reeval_call: bọc function trong SELECT để chỉ evaluate 1 lần
-- ❌ TRƯỚC
create policy {{policy_name}} on {{schema}}."{{table_name}}"
  using ({{function}}() = {{column}});

-- ✅ SAU
create policy {{policy_name}} on {{schema}}."{{table_name}}"
  using ((select {{function}}()) = {{column}});

-- issue = missing_supporting_index: thêm index cho cột dùng trong policy predicate
CREATE INDEX CONCURRENTLY idx_{{table_name}}_{{column}}
ON {{schema}}."{{table_name}}" ({{column}});
```

**Expected Impact**: 100x+ nhanh hơn trên bảng lớn (function chỉ evaluate 1 lần thay vì mỗi row)

---

## 15. STALE TABLE STATISTICS (ANALYZE Lag)

- **Detection**: [Tự động] Diagnostic block `stale_stats`, field `modified_pct` → finding_id `maintenance.stale_stats_pct` (red > 50%, yellow > 20%; `references/rules/maintenance.json`, row_identity `schema,table`). Block còn trả `n_live_tup`, `n_mod_since_analyze`, `last_analyze`, `last_autoanalyze`.
- **Priority**: P0 (> 50%) | P1 (20-50%)
- **Reference**: `monitor-vacuum-analyze.md`
- **Category**: DB-side / Maintenance

**Fix Template:**
```sql
-- Immediate fix
ANALYZE {{schema}}."{{table_name}}";

-- Long-term: tune autovacuum_analyze_scale_factor cho table hay ghi nhiều
ALTER TABLE {{schema}}."{{table_name}}" SET (autovacuum_analyze_scale_factor = 0.02);
```

**Expected Impact**: Query planner có thống kê chính xác → chọn plan tốt hơn (tránh Seq Scan sai do ước lượng row sai)

---

## 16. EXPLAIN PLAN ĐÍNH KÈM CHO SLOW QUERY

- **Detection**: [Tự động, bổ trợ — không có finding_id riêng] Diagnostic block `explain` (gắn tự động vào top-N query chậm nhất từ mục 4, `ExplainTopN` query). Mỗi row: `{queryid, mode ("plan"|"analyze"), plan (JSON plan hoặc null), explain_unavailable (lý do hoặc null, vd. "parameterized_pre_pg16"), analyze_skipped_reason, role, search_path, database}`. KHÔNG có rule/finding_id nào target block này trong `references/rules/*.json` — đây là bằng chứng bổ trợ đọc kèm finding của mục 4, không phải finding độc lập.
- **Priority**: (kế thừa priority của mục 4 — không có priority riêng)
- **Reference**: `monitor-explain-analyze.md`
- **Category**: Query Performance (bổ trợ cho mục 4)

**Fix Template:**
```
Đọc field `plan` (JSON) của query trong finding mục 4 — tìm node `Seq Scan` trên bảng lớn,
`Nested Loop` chi phí cao, hoặc `Sort` tràn ra disk. Nếu `explain_unavailable` khác null
(vd. "parameterized_pre_pg16"), không có plan — chỉ dùng window_mean_exec_time_ms của mục 4.
Áp Fix Template tương ứng ở mục 4 dựa trên node plan tìm được.
```

**Expected Impact**: Xác nhận chính xác root cause trước khi tạo index (tránh tạo index sai)

---

## 17. COLUMN-LEVEL INDEX SUGGESTION (Composite / Partial / Covering)

- **Detection**: [Tự động, một phần] Diagnostic block `index_advisor` → finding_id `query_perf.suggested_column_index` (presence rule, assessment cố định `yellow`; `references/rules/query-performance.json`, row_identity `schema,table,queryid`). Row: `{schema, table, suggested_columns, suggested_ddl, queryid}`. CHÚ Ý QUAN TRỌNG: hiện chỉ sinh gợi ý index COMPOSITE trên equality-predicate columns — KHÔNG tự sinh gợi ý PARTIAL hay COVERING (INCLUDE); reviewer phải tự cân nhắc 2 sub-loại đó thủ công.
- **Priority**: P2
- **Reference**: `query-composite-indexes.md` (tự động) — `query-covering-indexes.md`, `query-partial-indexes.md` (gợi ý thủ công, reviewer tự cân nhắc)
- **Category**: Query Performance

**Fix Template:**
```sql
-- suggested_ddl từ diagnostics.index_advisor.metrics đã sẵn sàng chạy sau khi review:
{{suggested_ddl}}

-- Trước khi chạy: kiểm tra thủ công xem có nên dùng partial index (WHERE cho soft-delete)
-- hoặc covering index (INCLUDE thêm cột SELECT) thay vì composite đơn thuần.
```

**Expected Impact**: 10-100x nhanh hơn cho query có equality predicate chưa được index

---

## 18. QUERY RANKING THEO TỔNG THỜI GIAN THỰC THI (Total Time × Calls)

- **Detection**: [Tự động, bổ trợ — không có finding_id riêng] Diagnostic block `query_stats`, fields `window_total_exec_time_ms`, `window_calls` (sampler đã pre-sort giảm dần theo `window_total_exec_time_ms`, collector không sort lại). KHÔNG có finding_id riêng cho field này (chỉ `window_mean_exec_time_ms` có rule — xem mục 4) — dùng như bảng xếp hạng bổ trợ để ưu tiên tối ưu query nào ảnh hưởng tổng tải nhiều nhất, kể cả khi mean_exec_time không vượt ngưỡng.
- **Priority**: (bổ trợ — dùng priority của mục 4 nếu cùng query vượt ngưỡng mean_exec_time)
- **Reference**: `monitor-pg-stat-statements.md`
- **Category**: Query Performance (bổ trợ cho mục 4)

**Fix Template:**
```
Sắp xếp diagnostics.query_stats.metrics theo window_total_exec_time_ms giảm dần (đã sort sẵn) —
ưu tiên tối ưu N query đầu tiên trước, dùng cùng Fix Template với mục 4.
```

**Expected Impact**: Ưu tiên đúng thứ tự tối ưu theo tổng tải thực tế, không chỉ theo mean latency

---

## 19. SCHEMA HYGIENE ISSUES (Missing PK / Oversized UUIDv4 PK / Timestamp Without Timezone)

- **Detection**: [Tự động] Diagnostic block `schema_checks` → finding_id `maintenance.schema_hygiene_issue` (presence rule, assessment cố định `yellow`; `references/rules/maintenance.json`, row_identity `schema,table,issue,column`). Field `issue` nhận đúng 3 giá trị: `missing_primary_key` (table không có PK — `column` = null), `oversized_uuid_pk` (PK là UUIDv4 VÀ table có `row_estimate` vượt `_LARGE_TABLE_ROW_THRESHOLD`, mặc định 1,000,000 rows), `timestamp_without_timezone` (cột kiểu `timestamp without time zone`).
- **Priority**: P1 (`missing_primary_key`) | P2 (`oversized_uuid_pk`, `timestamp_without_timezone`)
- **Reference**: `schema-primary-keys.md` (missing_primary_key, oversized_uuid_pk), `schema-data-types.md` (timestamp_without_timezone)
- **Category**: DB-side / Schema

**Fix Template:**
```sql
-- issue = missing_primary_key
ALTER TABLE {{schema}}."{{table_name}}" ADD PRIMARY KEY ({{suggested_column}});
-- Nếu chưa có cột phù hợp: thêm cột id trước
ALTER TABLE {{schema}}."{{table_name}}" ADD COLUMN id bigint generated always as identity;
ALTER TABLE {{schema}}."{{table_name}}" ADD PRIMARY KEY (id);

-- issue = oversized_uuid_pk: không đổi PK ngay trên bảng lớn (risky) — bảng mới nên
-- dùng UUIDv7 (time-ordered) thay vì UUIDv4 ngay từ đầu, xem schema-primary-keys.md

-- issue = timestamp_without_timezone
ALTER TABLE {{schema}}."{{table_name}}" ALTER COLUMN {{column}} TYPE timestamptz
  USING {{column}} AT TIME ZONE 'UTC';
```

**Expected Impact**: `missing_primary_key` → cho phép logical replication/CDC (yêu cầu PK hoặc REPLICA IDENTITY), tránh duplicate rows khi retry insert. `oversized_uuid_pk` → tránh index fragmentation trên bảng lớn (insert ngẫu nhiên vào b-tree). `timestamp_without_timezone` → tránh bug do ambiguous timezone khi app server và DB server ở múi giờ khác nhau.

---

*Bảng dưới đây là ma trận ưu tiên rút gọn kế thừa từ v3, chỉ áp dụng cho pattern 1-13. Pattern 14-19 (bổ sung P5) dùng Priority ghi trực tiếp trong từng mục, không nằm trong bảng này.*

## Priority Assignment Rules
```

- [ ] **Step 4: Update the pattern count in `_index.md`**

In `references/kb/_index.md`:

```
- old: **Solution Engine:** `solution-index.md` — master mapping 13 problem pattern → fix cụ thể
- new: **Solution Engine:** `solution-index.md` — master mapping 19 problem pattern → fix cụ thể
```

- [ ] **Step 5: Update the pattern count in `SKILL.md`**

In `SKILL.md` (verified this session, line 887):

```
- old: - `references/kb/solution-index.md` - Master mapping: 13 problem patterns → concrete fixes
- new: - `references/kb/solution-index.md` - Master mapping: 19 problem patterns → concrete fixes
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_solution_index.py tests/unit/test_skill_docs.py -v`
Expected: PASS (all tests, this file and the whole existing skill_docs suite)

- [ ] **Step 7: Run the full existing unit suite to confirm no regression**

Run: `pytest tests/unit -q`
Expected: same baseline as before this phase (6 pre-existing unrelated failures in `test_analyzer.py`, `test_sampler_live.py`, `test_stale_stats.py`, `test_stat_io.py`, `test_wal_hot.py` — verified this session as the pre-existing baseline, unrelated to this phase's docs-only changes); all `test_solution_index.py` and `test_skill_docs.py` tests pass.

- [ ] **Step 8: Commit**

```bash
git add references/kb/solution-index.md references/kb/_index.md SKILL.md tests/unit/test_solution_index.py tests/unit/test_skill_docs.py
git commit -m "docs(p5): add patterns 14-19 for previously-unmapped P1-P4 signals, update pattern counts"
```

---

## Self-Review

**Spec coverage:**
- §11 mapping table pattern → detection → fix → reference — Tasks 2 + 3 rewrite every `Detection`/`Reference` field to cite a verified diagnostic block/field/finding_id or an honest manual/code-analysis label.
- §11 priority-unlock list: total_exec_time/calls ranking (P1.2) — Task 3 pattern 18. Column-level missing index (P4.2) — Task 3 pattern 17. EXPLAIN (P4.1) — Task 3 pattern 16. RLS (P4.3) — Task 3 pattern 14. Stale-stats (P2.7) — Task 3 pattern 15. Composite/partial/covering (P4.2) — folded into pattern 17 (composite is automated, partial/covering explicitly marked manual within the same pattern, not fabricated as automated). FK-index correctness (P0.2) — Task 2 pattern 12 (already had a KB reference, now also cites the real finding_id).
- §11 "must fix wrong citations" — pattern 5 (`query-missing-indexes.md` cited the opposite problem) fixed in Task 2 Step 8 by removing the wrong-direction citation and stating explicitly why no KB file fits. Pattern 9 ("Security best practices", not a real filename) fixed in Task 1 (new file) + Task 2 Step 12 (citation updated).
- §11 "mark non-auto-detectable topics as gợi ý thủ công" — Task 2 Steps 5, 14, 16 (patterns 2, 11, 13), each with an explicit `[Gợi ý thủ công — không có collector]` label and a stated reason (grep-confirmed absence of the relevant collector/query in `scripts/`).
- §11 acceptance "≥8/13 patterns connected to a real tool signal" — enforced by `test_at_least_8_of_13_legacy_patterns_have_connected_detection` (Task 3), which counts 10/13 (patterns 1, 3, 4, 5, 6, 7, 8, 9, 10, 12) as connected.
- §11 "no citations to missing files" — `test_no_reference_field_points_outside_kb` (Task 2) plus every `Reference` field naming only files created in this plan or already present in `references/kb/` (verified via `_index.md`'s own file listing before writing any citation).
- §0.C "all references point into references/kb/" — every `Reference` field in the rewritten patterns names a bare filename (no path prefix), matching the existing convention throughout the file; the one exception (pattern 5's now-empty reference, explicitly explained) still names no external path.
- Discovered-in-session gap (schema_checks/P4.4, zero prior KB coverage) — Task 3 pattern 19, using two already-existing, content-verified KB files rather than inventing a new one.

**Placeholder scan:** no `TBD`/`later`/`similar to Task N` found — every step shows the complete verbatim `old`/`new` text to apply, or complete new file content. Re-checked.

**Type/signature consistency across tasks:**
- `security-sql-injection.md` filename and citation string (`security-sql-injection.md`) match exactly between Task 1 (creation) and Task 2 Step 12 (citation in pattern 9).
- Finding IDs, block names, and field names used in Task 3's patterns 14/15/17/18/19 were verified directly against `references/rules/*.json` and collector source in this same session (quoted verbatim in the task's preamble), not copied from an earlier, potentially stale research summary.
- Pattern count progression is consistent: 13 (start) → unchanged through Task 1/2 (only new-file/citation work) → 19 after Task 3's 6 new patterns (14-19), reflected identically in `solution-index.md`'s own patterns, `_index.md`'s "master mapping N problem pattern" line, and `SKILL.md`'s "Master mapping: N problem patterns" line.
- `test_solution_index.py` is created once (Task 1) and only appended to thereafter (Tasks 2, 3) — no task overwrites another task's tests.

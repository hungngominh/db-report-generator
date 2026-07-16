# db-report-generator v4.0 — Roadmap (plan-of-plans)

> **For agentic workers:** Đây là **roadmap**, KHÔNG phải plan thực thi. Mỗi phase bên dưới sẽ có một **plan chi tiết riêng** (viết bằng `superpowers:writing-plans`, TDD step-by-step) trước khi execute. Execute bằng `superpowers:subagent-driven-development` hoặc `superpowers:executing-plans`, mỗi lần **một phase**, review giữa các phase.

**Nguồn:** [Spec v4](../specs/2026-07-16-db-report-generator-v4-upgrade.md) — mọi quyết định khóa ở **§0** của spec là bất biến; roadmap này chỉ sắp xếp thứ tự thực thi, không override spec.

**Goal:** Biến `db-report-generator` từ skill SKILL.md-driven (agent tự sinh script lúc chạy) thành một **Python package deterministic, testable, an toàn** — thu thập số liệu bằng Python, diễn giải bằng agent, qua hợp đồng JSON multi-target có schema.

**Architecture:** `analyzer.py` (capabilities → collectors → sampler → explain) xuất `report_data.json` (validate schema) → `render.py` sinh báo cáo **deterministic** (golden-testable) → agent viết phần **narrative** → `assemble.py` ghép báo cáo tổng. Python sở hữu mọi con số/finding; agent chỉ diễn giải.

**Tech stack (chốt cho roadmap, xác nhận lại ở phase liên quan):**
- **Python** ≥ 3.10 (floor xác nhận ở P−1; README cũ ghi 3.8+ → nâng lên).
- **Test:** `pytest`. JSON Schema: thư viện `jsonschema` (Draft 2020-12).
- **DB driver:** *quyết định mở* — `psycopg2-binary` (khớp setup.bat hiện tại, dễ cài Windows) vs `psycopg` (v3). **Lock ở P0** (phase live-DB đầu tiên). P−1 gần như không đụng driver.
- **SQL parser (safety gate EXPLAIN):** `pglast`/`libpg_query` — thêm ở P4.
- **PostgreSQL matrix:** 14, 15, 16, 17, 18 (13 best-effort) — §0.A4.
- **CI reality:** workspace **không phải git repo** (spec §17). ⇒ P−1 giao **local test runner** (`pytest`) + `docker-compose` khởi PG14–18 cục bộ + **template GitHub Actions** để dùng khi init git. Không giả định CI cloud tồn tại.

---

## Global Constraints (áp cho MỌI phase — copy verbatim từ spec §0)

- **Determinism:** `analyzer.py` KHÔNG nhúng timestamp/random vào nhánh *dữ liệu chẩn đoán*; `generated_at`/`sample*_at` nằm ở nhánh metadata riêng, bị loại khi so golden. `render.py` byte-ổn định trên cùng input. (§0.A1)
- **Safety invariant:** analyzer/collector **KHÔNG BAO GIỜ** phát lệnh DDL/DML lên DB. EXPLAIN mặc định plan-only; ANALYZE chỉ opt-in + allowlist + timeout. (§0.A3, A6, N4)
- **No dangerous auto-execute:** không lớp remediation nào tự chạy; class chỉ quyết định trình bày/approval. (§0.A6)
- **Confidence invalidation:** finding từ diagnostic có `quality.sampling_valid=false` ⇒ `confidence ≤ heuristic` **và** `assessment = unknown`; renderer/agent không được nâng cấp. (§0.B3)
- **Multi-target isolation:** 1 database chết/timeout ⇒ ghi lỗi vào target đó, **tiếp tục** target khác; không làm chết cả run. (§0.A5, P7.3)
- **Redaction:** không ghi password/DSN đầy đủ/host thật vào log/output; query text có mode redact/hash; `report_data.json` ghi `redaction_mode`. (bổ sung bảo mật review)
- **Version adaptation:** PG14–18 chính thức; `server_version > known` ⇒ conservative mode, không chạy collector chưa biết schema. (§0.A4)
- **KB nội bộ:** mọi tham chiếu KB trỏ `references/kb/` (đã self-contained §0.C); không path ngoài.
- **Enum cố định:** collector `status = ok|partial|skipped|error`; `assessment = green|yellow|red|unknown|not_applicable`; `confidence = measured|estimated|heuristic`. `skipped`/thiếu activity **không bao giờ** = green. (§0.A5)
- **Ngôn ngữ báo cáo:** tiếng Việt (giữ tiếng Anh cho tên bảng/cột/SQL/tên file). (SKILL.md hiện tại)
- **Tương thích `.env`:** `.env` v3 vẫn chạy; field mới **optional** kèm mặc định. Tên 4 file báo cáo gốc (`DB_STATUS_REPORT.md`, `CODE_ANALYSIS_REPORT.md`, `PERFORMANCE_SOLUTIONS.md`, `COMBINED_REPORT.md`) **giữ nguyên** để so-sánh-ngày cũ chạy được; artifact mới (`report_data.json`, `report_summary.json`, `FINDINGS.md`, `INTERPRETATION.md`) thêm vào. (§13, §0.A1)

---

## Target file structure (đích cuối v4; migrate dần qua các phase)

```
.agents/skills/db-report-generator/
├── SKILL.md                      # control plane: input → analyzer → validate → render → KB → diễn giải (KHÔNG thực thi remediation)
├── CLAUDE.md
├── scripts/
│   ├── analyzer.py               # orchestrator (entrypoint)
│   ├── capabilities.py           # dò version/vendor/quyền/extension/track_io_timing
│   ├── sampler.py                # 2 mẫu delta, reset semantics
│   ├── explain.py                # EXPLAIN plan-only + safety gate (pglast)
│   ├── render.py                 # report_data.json → DB_STATUS_REPORT.md / FINDINGS.md / report_summary.json
│   ├── assemble.py               # ghép COMBINED_REPORT.md
│   ├── rules.py                  # rule engine: metrics → findings (deterministic)
│   ├── lib/                      # schema-validate, deterministic sort, redaction, .env parse
│   └── collectors/               # 1 module / nhóm chẩn đoán (versioned)
├── references/
│   ├── report-data.schema.json   # JSON Schema 2020-12 (multi-target)
│   ├── collector-contracts.md
│   ├── remediation-policy.md
│   ├── rules/                    # ngưỡng + finding definitions (versioned)
│   ├── kb/                       # ✅ đã có (31 file, self-contained)
│   └── *.sql                     # queries versioned (giữ, refactor dần)
├── assets/
│   └── templates/                # template-*.md chuyển vào đây
└── tests/
    ├── fixtures/                 # report_data.json mẫu (positive + negative)
    ├── golden/                   # snapshot render
    ├── unit/                     # test collector SQL trên Docker PG14-18
    └── run.py / conftest.py      # runner + fixtures
```

Hiện có: `SKILL.md`, `CLAUDE.md`, `references/{queries-*.sql, template-*.md, sample.env, kb/}`. Chưa có: `scripts/`, `tests/`, `assets/`, `references/{rules/, *.schema.json, *-contracts.md, *-policy.md}`.

---

## Bản đồ phase → deliverable → phụ thuộc

Thứ tự thực thi tuyến tính: **P−1 → P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7** (khớp §0 thứ tự đề xuất). Mỗi phase ship được độc lập; dừng sau bất kỳ phase nào skill vẫn hoạt động.

### P−1 — Contract freeze & safety harness  *(nền tảng)*
- **Plan file:** `2026-07-16-db-report-v4-p-minus-1-contract-harness.md`
- **Deliverables:**
  - `references/report-data.schema.json` — JSON Schema 2020-12, multi-target `targets[]`, enum status/assessment/confidence, `quality{}`, `findings[]` (§0.A5).
  - `tests/fixtures/report_data.sample.json` — fixture v4-shaped hand-authored: có target `ok`, target `error`, block `skipped`, block `sampling_valid=false`→unknown, finding measured/heuristic.
  - `scripts/render.py` — đọc `report_data.json` → `DB_STATUS_REPORT.md` + `FINDINGS.md` + `report_summary.json`, **deterministic** (sort ổn định, loại nhánh time).
  - `scripts/lib/` — `schema.py` (validate), `sortkeys.py` (deterministic sort), `redact.py` (redaction + `redaction_mode`), `envparse.py` (đọc `.env` v3 JSON).
  - `tests/` — pytest: (1) fixture validate schema, (2) schema **reject** malformed, (3) render golden byte-stable, (4) redaction che password/host, (5) deterministic sort, (6) safety-invariant scaffold (analyzer không sinh DDL/DML — assert bằng static/allowlist), (7) confidence-invalidation (B3).
  - Test runner + `docker-compose.pg.yml` (PG14–18) + `.github/workflows/tests.yml` (template).
  - Golden baseline snapshot đầu tiên.
- **Depends:** — (không).
- **Spec:** §0.A1, A5, A7, B3; §3.1; P7.1.
- **Gate:** `pytest` xanh; render byte-ổn định; schema loại malformed; redaction pass; fixture hợp lệ; không đụng live DB (thuần Python).

### P0 — Blocker + bảo mật + de-danger  *(phase live-DB đầu tiên → LOCK DB driver)*
- **Plan file:** `...-p0-blockers-security.md`
- **Deliverables:**
  - `scripts/capabilities.py` (**§4** — chạy đầu tiên, mọi collector đọc trước khi hành động): `server_version_num`, `is_superuser`, membership `pg_read_all_stats`/`pg_monitor`, vendor heuristic (Supabase/RDS/Aurora/self-hosted/unknown), extension + schema, RAM nếu có; fallback bảo thủ khi unknown. Lock **DB driver** (`psycopg2` vs `psycopg`) tại đây.
  - Port/fix SQL blocker thành collector versioned: bỏ `relhasoids` (P0.1); FK-index đúng theo **prefix** (`(b,a)` covered, INCLUDE/partial/expression loại — review); dup-index **full signature** (amname/indnkeyatts/indkey/indclass/indcollation/indoption/indexprs/indpred/indnullsnotdistinct/reloptions — review) + tách `exact_duplicate` vs `potentially_redundant`; `dead_pct` mẫu số đúng (P0.4); nhãn `index_size` (P0.5); gỡ khung "chạy liền" nguy hiểm (P0.6); README/setup honest (P0.7); bảo mật `.env` + `.gitignore` + placeholder + `redaction_mode` (P0.8 + review security).
- **Depends:** P−1 (schema, test harness, redaction).
- **Spec:** §4 (capability probing), §5 (P0.1–P0.8), §0.A6 (partial), bảo mật review, FK/dup review.
- **Gate:** user readonly (không superuser) → `capabilities.is_superuser=false`, khối superuser-only `skipped` có lý do, run hoàn tất không lỗi (§4 acceptance); mỗi query fixed chạy không lỗi PG14–18 (unit test Docker); negative fixtures (FK reversed/INCLUDE/partial; dup PK/UNIQUE không drop); sample.env không IP thật; không còn block chạy-liền cho `dangerous`.

### P1 — Delta sampling đúng semantics
- **Plan file:** `...-p1-delta-sampling.md`
- **Deliverables:** `scripts/sampler.py` — 2 mẫu **transaction riêng** / `pg_stat_clear_snapshot()`; theo dõi `stats_reset` + restart + counter giảm; eviction **per-queryid** (B2); công thức window (`Δtotal/Δcalls`…, cấm trừ mean/stddev — A2); `quality{}` flags; `minimum_activity`→unknown. Config `SamplingWindowSeconds`. Mô hình latency multi-target (B4).
- **Depends:** P−1 (schema quality), P0 (capabilities, driver).
- **Spec:** §6 (P1.1, P1.2), §0.A2, B2, B4.
- **Gate:** fixtures 2 chiều: reset giữa 2 mẫu → `invalidated`; cùng-txn → phát hiện; dealloc → invalidate entry; zero-workload → unknown; test công thức.

### P2 — Core diagnostics + scope/quality metadata
- **Plan file:** `...-p2-core-diagnostics.md`
- **Deliverables:** collectors P2.1–P2.9 (XID/MultiXact wraparound **tương đối** `autovacuum_freeze_max_age`/`failsafe_age` — review; pg_stat_database; wait events; checkpoint/bgwriter; WAL+HOT; index-IO; stale-stats; connection sâu; replication slots) + **P2.10 blocking graph** (`pg_blocking_pids`), **P2.11 vacuum horizon** (`backend_xmin`, prepared xact), **P2.12 `pg_stat_io`** theo capability (review). Mở rộng `capabilities.py` (từ P0) thêm probe `track_io_timing` + `pg_stat_statements.track` (B5).
- **Depends:** P−1, P0, P1.
- **Spec:** §7, review 3 collector, wraparound-relative, B5.
- **Gate:** mỗi section có `scope`+`quality`; `skipped` duyên dáng khi thiếu view/quyền/version; positive+negative fixtures.

### P3 — Rule engine + unknown/confidence model
- **Plan file:** `...-p3-rule-engine.md`
- **Deliverables:** `references/rules/*` (finding_id, severity, assessment, confidence, threshold, evidence) + `scripts/rules.py` (metrics→findings deterministic); **bỏ score 0–100**; assessment gồm `unknown`/`not_applicable`; áp **B3 invariant**; ma trận theo trục (db-health/query/maintenance/connections/security-RLS).
- **Depends:** P2 (metrics), P−1 (schema).
- **Spec:** §8, §0.A5, B3.
- **Gate:** không còn 0–100; mỗi phán quyết có confidence; `sampling_valid=false`→unknown; test ma trận trục.

### P4 — EXPLAIN plan-only + column/RLS + code-analysis
- **Plan file:** `...-p4-explain-column-rls.md`
- **Deliverables:** `scripts/explain.py` — `ExplainMode=plan` mặc định; generic plan PG16+; safety gate bằng **parser** (pglast) không regex; allowlist + `statement_timeout`/`lock_timeout`; PG<16 parameterized → `explain_unavailable` (B1). P4.2 gợi index cấp cột (composite/partial/covering, check đã tồn tại). P4.3 RLS `auth.uid()` không bọc `(select …)`. P4.4 schema (PK thiếu, uuidv4 PK lớn, timestamptz). P4.5 code-analysis honest (bỏ /100).
- **Depends:** P2, P3.
- **Spec:** §10, §0.A3, B1.
- **Gate:** mỗi slow-query có plan hoặc lý do; ANALYZE không bao giờ mặc định; RLS re-eval fixtures; parser gate test.

### P5 — KB mapping bằng rule IDs
- **Plan file:** `...-p5-kb-mapping.md`
- **Deliverables:** bảng ánh xạ trong `references/kb/solution-index.md`/`rules`: pattern → detection (tín hiệu tool THỰC SỰ thu) → fix cấp cột → `reference` = file trong `references/kb/` (§0.C, không path ngoài). Mở khóa ≥8/13 pattern. Sửa cite sai. Đánh dấu topic không auto-detect là "gợi ý thủ công".
- **Depends:** P3 (rule IDs), P4 (column/RLS/EXPLAIN detections).
- **Spec:** §11, §0.C.
- **Gate:** ≥8/13 pattern nối tín hiệu thật; không cite file thiếu; reference trỏ `references/kb/`.

### P6 — Remediation engine từ versioned templates
- **Plan file:** `...-p6-remediation-engine.md`
- **Deliverables:** `references/remediation-policy.md` + SQL template versioned; **taxonomy 5 lớp** (observe-only/controlled-diagnostic/maintenance-review/ddl-review/dangerous — §0.A6); `recovery_or_rollback`; CONCURRENTLY block riêng + cảnh báo INVALID; partition bỏ template mất-dữ-liệu → `pg_partman`/quy trình; `pg_terminate_backend` chỉ idle-in-txn; server-config self-hosted vs managed (không `ALTER SYSTEM` cho managed).
- **Depends:** P3 (findings), P5 (KB), P0/P2 (capabilities).
- **Spec:** §9, §0.A6.
- **Gate:** dangerous không có block chạy-liền; managed không `ALTER SYSTEM`; mỗi remediation có `recovery_or_rollback`.

### P7 — Migration, docs, packaging, release hardening
- **Plan file:** `...-p7-packaging-release.md`
- **Deliverables:** `MIGRATION.md` v3→v4; README/setup khớp hybrid + honest; bump `4.0.0`; template → `assets/templates/`; **batch isolation** P7.3 (1 DB die → tiếp DB khác); ship list gồm `references/kb/`; golden + local matrix cuối; `<details>`+`sanitize()` giữ.
- **Depends:** tất cả.
- **Spec:** §12, §0.A4/A7/C, §13.
- **Gate:** local matrix PG14–18 xanh; 1 DB die không hỏng run; golden bắt render drift; packaging ship đúng file.

---

## Phụ thuộc (rút gọn)

```
P-1 ──► P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5 ──► P6 ──► P7
 (contract)          (metrics)     (findings)  (detections)(KB)  (remediation)(release)
```

Tuyến tính là chủ đích (test-first + mỗi phase ship được). Một số việc có thể chồng lấn khi execute (vd P2 collectors song song nhau), nhưng **ranh giới plan** giữ theo phase để review từng cổng.

## Quyết định còn mở (lock đúng phase)

| Quyết định | Lock ở | Mặc định đề xuất |
|---|---|---|
| DB driver `psycopg2` vs `psycopg`(v3) | P0 | `psycopg2-binary` (khớp setup.bat, portable Windows) |
| Python floor | P−1 | ≥ 3.10 |
| Docker sẵn có cho local PG matrix? | P−1 | Có fallback: test thuần-Python (schema/render/redaction) luôn chạy; unit-collector cần Docker → skip nếu vắng |
| Chuyển `template-*.md` → `assets/templates/` ngay hay ở P7 | P7 | Ở P7 (tránh vỡ path v3 giữa chừng) |

## Cách thực thi từng phase (nhắc lại)

1. `superpowers:writing-plans` → viết plan chi tiết cho phase (TDD, code đầy đủ mỗi step).
2. Review plan.
3. `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` → execute.
4. Verify gate của phase → sang phase kế.

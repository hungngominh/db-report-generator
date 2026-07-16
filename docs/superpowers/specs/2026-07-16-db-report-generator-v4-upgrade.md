# Spec: Nâng cấp `db-report-generator` lên v4.0

- **Ngày:** 2026-07-16
- **Tác giả:** Brainstorm cùng Claude (Superpowers)
- **Trạng thái:** Review spec xong — đã fold 7 điểm khóa + 5 bổ sung (xem **§0**); chờ duyệt lại → chuyển writing-plans
- **Skill mục tiêu:** `.agents/skills/db-report-generator` (v3.0.0 → v4.0.0)
- **Quyết định định hình:** (1) Phạm vi = v4.0 toàn diện; (2) Runtime = **Hybrid** (thu thập deterministic + diễn giải agent); (3) Môi trường = **cả self-hosted lẫn managed, auto-detect capability**.

---

## 0. Quyết định khóa sau review spec (BẮT BUỘC — override phần thân bên dưới)

> Các quyết định dưới đây được chốt trong vòng review spec (16/07/2026) và **thay thế** mọi mô tả mâu thuẫn ở phần thân. Khi phần thân (§3, §9, §13, §14…) khác với §0, **§0 thắng**. Đây là điều kiện để chuyển sang `writing-plans`.

### A. Bảy điểm khóa

**A1 — Canonical renderer: tách render deterministic khỏi narrative agent.** *(override §3, §3.1, P7.1)*

Luồng đúng:

```
analyzer.py → report_data.json
  → render.py    → DB_STATUS_REPORT.md / FINDINGS.md / report_summary.json   (deterministic, golden-testable)
  → agent        → INTERPRETATION.md / PERFORMANCE_SOLUTIONS.md              (narrative — chỉ diễn giải finding đã có)
  → assemble.py  → COMBINED_REPORT.md
```

- Python/rule engine **sở hữu**: `finding_id`, `severity`, `confidence`, `evidence`, `remediation_class`, `sql_template_id`, `kb_reference_id`.
- Agent **không** được tạo thêm số liệu / severity / SQL / finding mới; chỉ diễn giải finding đã tồn tại.
- `analyzer.py` ghi **toàn bộ** metadata thời gian (`generated_at`, `sample*_at`) ngay khi collector xong; agent **không** sửa JSON. Golden compare vẫn loại nhánh metadata thời gian.
- *Acceptance:* golden test so trên output của `render.py` (không phải văn xuôi agent); cùng `report_data.json` → render byte-ổn định.

**A2 — Sampler reset semantics.** *(override P1.1)*

- Hai mẫu phải ở **transaction riêng** hoặc gọi `pg_stat_clear_snapshot()` trước mẫu 2 (PG mặc định `stats_fetch_consistency=cache` → hai lần đọc cùng txn trả giá trị y hệt).
- Lưu & so `stats_reset`; phát hiện server restart, counter giảm, eviction `pg_stat_statements`, cửa sổ thiếu activity.
- Nếu `stats_reset` đổi / restart / delta âm → `quality.sampling_valid=false`, `reset_detected=true`; **không** sinh green/yellow/red.
- Nếu calls/blocks/tx dưới `minimum_activity` → `assessment="unknown"`, `reason="insufficient_activity"`.
- Công thức **bắt buộc**:
  - `window_mean_exec_time = Δtotal_exec_time / Δcalls`
  - `window_rows_per_call  = Δrows / Δcalls`
  - **Cấm** `mean₂ − mean₁`. `stddev` **không** lấy bằng `stddev₂ − stddev₁` — hoặc tính lại từ count/mean/variance (công thức gộp variance), hoặc ghi rõ `lifetime_stddev`.

**A3 — EXPLAIN mode (plan mặc định).** *(override P4.1, config §13; làm rõ N2)*

```
ExplainMode=plan            # off | plan | analyze   (mặc định plan)
ExplainTopN=5
ExplainAnalyzeTopN=0
ExplainStatementTimeoutMs=3000
ExplainLockTimeoutMs=500
```

- `off` = không chạy; `plan` = EXPLAIN không ANALYZE (mặc định); `analyze` = opt-in tường minh + allowlist.
- Query có placeholder → generic plan **khi PG≥16** (không ANALYZE — xem B1).
- Query có `FOR UPDATE` / advisory lock / volatile function / FDW / không phân loại chắc → **không** ANALYZE.
- **Không** dùng regex "bắt đầu bằng SELECT" làm safety gate; dùng parser PG (`pglast`/`libpg_query`) để phân loại SQL — N2 chỉ cấm AST cho application code, **không** cấm việc này.
- Ghi `role`/`search_path`/`database`/planning GUC; khác execution context thật → giảm confidence.
- Tách `SlowQueryTopN` khỏi `ExplainTopN`; **không** mặc định ANALYZE 20 query.

**A4 — Version matrix 14–18.** *(override P0.1, P7.2, §13)*

- CI bắt buộc: PG **14, 15, 16, 17, 18**. Legacy best-effort: PG13 (không phải support tier chính thức; PG13 EOL 11/2025).
- `server_version > known_version` → **conservative mode**, không chạy collector chưa biết schema.

**A5 — JSON Schema multi-target.** *(override §3.1)*

- Contract mới: `schema_version`, `tool_version`, `run{run_id, started_at, completed_at}`, và **`targets[]`** (mỗi target = 1 database, có `collection_status`, `capabilities`, `diagnostics`).
- Mỗi diagnostic: `collector_version`, `scope`, `status`, `quality{sampling_valid, reset_detected, insufficient_activity, truncated}`, `metrics[]`, `findings[]`.
- Mỗi finding: `finding_id`, `severity`, `assessment`, `confidence`, `evidence_ids[]`, `remediation_ids[]`.
- Enum riêng: collector `status = ok|partial|skipped|error`; `assessment = green|yellow|red|unknown|not_applicable`; `confidence = measured|estimated|heuristic`.
- `skipped` / thiếu activity **tuyệt đối không** quy thành green.
- File `references/report-data.schema.json`; **mọi run validate schema trước khi agent đọc**.

**A6 — Risk taxonomy 5 lớp + `recovery_or_rollback`.** *(override §9; hòa giải với N4)*

```
observe-only          : SELECT catalog/stats, EXPLAIN không ANALYZE
controlled-diagnostic : EXPLAIN ANALYZE (opt-in + timeout + allowlist)
maintenance-review    : ANALYZE, VACUUM / VACUUM ANALYZE, per-table autovacuum
ddl-review            : CREATE INDEX CONCURRENTLY, ALTER TABLE
dangerous             : DROP INDEX, pg_terminate_backend, partition migration, ALTER SYSTEM, work_mem global
```

- **Không lớp nào tự thực thi** (khớp N4); class chỉ quyết định trình bày / cảnh báo / approval — **không** quyết định execution. ANALYZE / VACUUM / EXPLAIN ANALYZE **không** còn là `auto-safe`.
- Đổi field `rollback` → `recovery_or_rollback`: `pg_terminate_backend` không rollback; `DROP INDEX` chỉ recovery bằng tạo lại; partition migration có recovery plan chứ không transactional rollback.

**A7 — Test-first: thêm Phase −1.** *(override §14, P7.1–P7.2)*

`Phase −1 — Contract freeze & safety harness`: fixture v3 hiện tại; JSON Schema v4; test runner; CI PG14–18; deterministic sort; safety invariant (analyzer **không** phát DDL/DML); secret-redaction tests; renderer golden baseline. Sau đó **mỗi phase thêm test cùng implementation**; Phase 7 chỉ release hardening + packaging.

### B. Năm bổ sung (đóng các lỗ "cited-but-dead" mới)

**B1 — Plan-mode bất khả thi trên query normalized ở PG14/15.** `GENERIC_PLAN` chỉ có từ **PG16+**. Query `$1,$2` từ `pg_stat_statements` không PREPARE được để `EXPLAIN` trên <16 → trạng thái `explain_unavailable: "parameterized_pre_pg16"`, **không** im lặng bỏ qua (nếu không sẽ thành "cited-but-dead" mới).

**B2 — Detection eviction theo per-queryid, không chỉ `dealloc`.** `dealloc` (trong `pg_stat_statements_info`) là counter **toàn cục**, không cho biết entry nào bị evict. Track theo `queryid`: nếu `calls` của một queryid **giảm** hoặc queryid **biến mất** giữa hai mẫu → invalidate delta của entry đó. Đồng thời theo dõi `stats_reset` toàn cục trong `pg_stat_statements_info`.

**B3 — Confidence invalidation invariant (ràng buộc schema, không phải khuyến nghị).** Bất kỳ finding phái sinh từ diagnostic có `quality.sampling_valid=false` → **bắt buộc** `confidence ≤ heuristic` và `assessment = unknown`. Renderer/agent **không** được nâng cấp. Ràng buộc này validate trong schema/CI.

**B4 — Sampling latency cho multi-target.** Cửa sổ 30s × N target: chốt mô hình chạy (song song có bound, hoặc cửa sổ chia sẻ) để runtime không nở tuyến tính; ghi `window_seconds` thực tế mỗi target và cảnh báo nếu tổng thời gian vượt ngưỡng.

**B5 — `track_io_timing` / `pg_stat_statements.track` là capability.** `pg_stat_io` timing & blk-timing phụ thuộc `track_io_timing`; khi tắt → metric `unknown`, **không** phải `0`. `capabilities.py` probe `track_io_timing` và `pg_stat_statements.track`, gắn vào nhánh `capabilities` của JSON.

### C. Self-contained: KB đóng gói nội bộ *(quyết định + đã thực hiện 16/07/2026)*

- `db-report-generator` **không** còn phụ thuộc skill ngoài `supabase-postgres-best-practices`. Toàn bộ **31 file KB** (30 topic + `solution-index.md`) đã copy vào **`references/kb/`** + `references/kb/_index.md` (navigation + provenance Supabase).
- Path cứng `../supabase-postgres-best-practices/references/solution-index.md` trong SKILL.md → `references/kb/solution-index.md`. Attribution "supabase-postgres-best-practices" trong template/footer **giữ nguyên** (nguồn tri thức, không phải path).
- `setup.bat`/`README` bỏ bước ship skill KB riêng — KB đi kèm trong `.agents/skills/db-report-generator/` (xcopy `/s` cuốn theo `references/kb/`).
- **Hệ quả cho v4:** Phase 5 ("nối KB thật") đọc từ `references/kb/` (không path ngoài); cấu trúc skill đề xuất giữ thư mục `references/kb/`; **P7.4** packaging ship `references/kb/`; golden/unit test không được giả định skill KB ngoài tồn tại. `supabase-postgres-best-practices` có thể **xóa an toàn** sau khi verify không còn tham chiếu `../supabase-postgres-best-practices` trong `db-report-generator`.

---

## 1. Bối cảnh & động cơ

Hai vòng đánh giá đối kháng (mỗi phát hiện được fact-check độc lập theo ngữ nghĩa PostgreSQL) kết luận skill hiện tại **chưa đủ tin cậy** để đánh giá hiệu năng DB:

**Vòng 1 — review chất lượng (37 confirmed / 12 overstated / 1 wrong):**
- Blocker: runtime Python trong README **không tồn tại**; `setup.bat` báo "hoàn tất" giả; query index-bloat **lỗi cứng trên PG12+** (`relhasoids`); template partition **mất dữ liệu**.
- Sai lầm phương pháp gốc: đọc **counter tích lũy như snapshot tức thời** → false-green/false-red; điểm 0–100 double-count + giả chính xác.
- Query sai: FK-index (`ANY(indkey)`), duplicate-index bất định + có thể drop UNIQUE/PK, `dead_pct` sai mẫu số + trả 0% khi bảng chết hoàn toàn, cache-hit chỉ tính heap, slow-query xếp theo `mean_exec_time`.
- Remediation nguy hiểm dưới khung "chạy luôn"; giả định self-hosted superuser → vỡ trên managed.
- Thiếu chẩn đoán trọng yếu: XID wraparound, `pg_stat_database`, wait events, EXPLAIN, index-level cache, stale stats.

**Vòng 2 — coverage vs `supabase-postgres-best-practices` (30 file):**
- 14/30 được cite; detectability = **0 yes / 15 partial / 15 no**. Tool không biến được **bất kỳ** file KB nào thành finding chính xác.
- Engine chỉ đọc **1 file** (`solution-index.md`); 30 body là "bibliography trang trí" (~30% operational).
- RLS performance (HIGH, sát thủ hiệu năng Supabase) = 0% phủ; `pg_stat_statements` chỉ rank theo `mean` (mù `total_exec_time` + `calls`).
- Dead wiring: EXPLAIN/composite/covering được cite nhưng engine không thể kích hoạt.

**Mục tiêu v4.0:** biến skill thành **công cụ đánh giá hiệu năng đáng tin, an toàn, testable**, thực sự tận dụng KB, thích ứng cả self-hosted lẫn managed.

---

## 2. Goals / Non-goals

**Goals**
- G1. Sửa mọi blocker khiến skill không chạy hoặc nguy hiểm.
- G2. Chẩn đoán **đúng phương pháp** (delta theo cửa sổ thời gian, không đọc tích lũy như snapshot).
- G3. Phủ các chiều hiệu năng trọng yếu còn thiếu.
- G4. Chẩn đoán **cấp cột** có kiểm chứng bằng EXPLAIN, phát hiện RLS.
- G5. **Nối KB thật**: mỗi pattern có detection cụ thể → fix cấp cột → tham chiếu KB.
- G6. Solution engine **an toàn, có gate, phân biệt self-hosted/managed**.
- G7. **Testable**: golden output + unit test collector trên nhiều phiên bản PG.
- G8. Đóng gói/README khớp thực tế; bảo mật cấu hình.

**Non-goals**
- N1. Không xây dashboard web mới (index.html/viewer.html) — nếu README nhắc thì gỡ nhắc hoặc đánh dấu optional; không thuộc phạm vi v4.
- N2. Không làm static-analyzer code thực thụ (AST) — code-analysis vẫn heuristic nhưng **hạ cấp cách trình bày** cho trung thực.
- N3. Không đổi định dạng `.env` gây phá vỡ tương thích v3 (chỉ thêm field optional).
- N4. Không tự động **thực thi** bất kỳ fix ghi/DDL nào lên DB — skill chỉ chẩn đoán và đề xuất.

---

## 3. Kiến trúc & luồng dữ liệu (Hybrid)

Tách **thu thập (deterministic, Python)** khỏi **diễn giải (agent)** qua hợp đồng JSON.

> **CHỐT LẠI (§0.A1):** agent **không** viết các báo cáo Markdown chính. `render.py` sinh `DB_STATUS_REPORT.md` / `FINDINGS.md` / `report_summary.json` deterministic (golden-testable); agent chỉ viết `INTERPRETATION.md` / `PERFORMANCE_SOLUTIONS.md`; `assemble.py` ghép `COMBINED_REPORT.md`. Sơ đồ dưới đây phản ánh phân vai cũ (agent viết toàn bộ .md) — đọc theo §0.A1.

```
analyzer.py  (Python, versioned, testable)
  ├─ capabilities.py       # dò quyền/vendor/extension/version/RAM
  ├─ collectors/*.sql|.py  # mỗi nhóm chẩn đoán = 1 module có version
  ├─ sampler.py            # 2 mẫu cách N giây -> DELTA cho counter
  ├─ explain.py            # EXPLAIN plan-only mặc định (§0.A3); ANALYZE opt-in + allowlist
  └─ writer.py             # xuất report_data.json (schema cố định)
             │
             ▼  report_data.json  (structured, deterministic)
             │
Claude (agent, theo SKILL.md)
  ├─ đọc report_data.json + solution-index.md + KB refs (khi cần)
  ├─ code-analysis (grep, gán mức tin cậy)
  ├─ viết DB_STATUS / CODE_ANALYSIS / PERFORMANCE_SOLUTIONS / COMBINED (.md, tiếng Việt)
  └─ sinh khuyến nghị có gate (không "chạy luôn" cho nhóm nguy hiểm)
```

**Ranh giới trách nhiệm (bất biến):**
- **Python** chịu trách nhiệm mọi **con số & phát hiện SQL** → test được bằng golden JSON.
- **Agent** chịu trách nhiệm **văn xuôi, nhận định, code-analysis, sinh giải pháp** → linh hoạt.
- SQL sống trong file có version (không sinh lại mỗi run) — vá finding "SQL regenerated inline each run".

### 3.1 Hợp đồng `report_data.json` (bản phác)

> **CHỐT LẠI (§0.A5):** bản phác dưới đây chỉ mô hình hóa **một** database và thiếu typed schema / finding-id / quality. Contract chính thức là **multi-target `targets[]`** + `references/report-data.schema.json` (§0.A5); mọi run validate schema **trước khi** agent đọc. `generated_at`/`sample*_at` do `analyzer.py` ghi (§0.A1), không phải agent.
```jsonc
{
  "schema_version": "4.0",
  "generated_at": "<iso, do agent đóng dấu sau khi chạy>",
  "project": { "name": "...", "server": "...", "port": 5432, "database": "..." },
  "capabilities": {
    "server_version_num": 150004,
    "is_superuser": false,
    "has_pg_read_all_stats": true,
    "vendor": "supabase|rds|aurora|self-hosted|unknown",
    "managed": true,
    "extensions": { "pg_stat_statements": {"present": true, "schema": "extensions"}, "pgstattuple": {"present": false} },
    "ram_bytes": null
  },
  "sampling": { "window_seconds": 30, "sample1_at": "...", "sample2_at": "..." },
  "diagnostics": {
    "<block_name>": { "status": "ok|skipped|error", "reason": "...", "rows": [ ... ] }
  }
}
```
- Mọi khối có `status` để báo cáo phản ánh trung thực phần chạy được / bị bỏ do thiếu quyền / lỗi.
- `schema_version` cho phép golden test & migration về sau.
- **Lưu ý determinism:** `analyzer.py` KHÔNG nhúng timestamp/random vào phần *dữ liệu chẩn đoán* dùng để so golden; các trường thời gian (`generated_at`, `sample*_at`) nằm ở nhánh metadata riêng và bị loại khi so sánh golden.

---

## 4. Capability probing & thích ứng môi trường (P0)

Chạy **đầu tiên**; mọi collector/solution đọc `capabilities` trước khi hành động.

- Thu thập: `server_version_num`, `is_superuser`, membership `pg_read_all_stats`/`pg_monitor`, vendor heuristic (Supabase: schema `extensions` + role `supabase_admin`/`authenticator`; RDS/Aurora: `rds_superuser`, setting `rds.*`), extension khả dụng + schema, RAM nếu lấy được.
- **Thích ứng giải pháp:**
  - self-hosted + superuser → `ALTER SYSTEM SET ...; SELECT pg_reload_conf();` (kèm cảnh báo restart cho `shared_buffers`).
  - managed → "chỉnh trong parameter group / dashboard nhà cung cấp"; **không** sinh `ALTER SYSTEM`.
  - pooler: managed Supabase → nêu Supavisor (6543) + caveat prepared statements.
- **Thích ứng chẩn đoán:** khối cần quyền không có → `status: skipped`, `reason: "cần pg_read_all_stats"`; không làm vỡ run.

**Acceptance:** chạy với user readonly (không superuser) → report_data.json có `capabilities.is_superuser=false`, các khối superuser-only `skipped` với lý do, run hoàn tất không lỗi.

---

## 5. Phase 0 — Blocker + bảo mật

| # | Sửa | Chi tiết | Acceptance |
|---|-----|----------|-----------|
| P0.1 | Bỏ `relhasoids` | Query bloat trong `queries-index.sql`: gỡ 2 tham chiếu `relhasoids` (không dùng trong phép tính); ưu tiên `pgstattuple` khi có; guard `server_version_num`. | Query chạy không lỗi trên PG 14–18 (PG13 best-effort — §0.A4). |
| P0.2 | FK-index đúng | So `conkey` (mảng có thứ tự) với **tiền tố dẫn đầu** của `indkey`; 1 `CREATE INDEX` composite/1 FK; **quote** tên cột; tên index từ relname trần (join `pg_class`/`pg_namespace`, không dấu `.`). Sửa cả `queries-solutions.sql #1` lẫn `solution-index.md #12`. | Index (other_col, fk_col) KHÔNG được coi là đủ; DDL sinh ra chạy được với tên PascalCase. |
| P0.3 | Duplicate-index | `array_agg(... ORDER BY ...)`; loại index PK/UNIQUE/exclusion khỏi ứng viên DROP; chọn "keep" xác định. | Không đề xuất drop index backing PK/UNIQUE. |
| P0.4 | `dead_pct` | Mẫu số `n_live+n_dead`; ca `n_live=0 & n_dead>0` → 100% (không phải 0%); đổi nhãn cột cho đúng nghĩa. | Bảng 100% chết hiển thị 🔴, không phải 🟢. |
| P0.5 | Nhãn `index_size` | Dùng `pg_indexes_size(relid)` cho đúng "index"; hoặc đổi nhãn thành "index+TOAST+meta" nếu giữ công thức cũ. | Nhãn khớp giá trị. |
| P0.6 | Gate remediation | Bỏ khung "copy-paste chạy luôn"; phân loại fix (§9). | Không còn block script chạy-liền cho nhóm `dangerous`. |
| P0.7 | Runtime/README | Viết lại README khớp gói thật (hybrid); `setup.bat` **fail rõ ràng** khi nguồn thiếu; gỡ/nêu-optional các file web không tồn tại. | `setup.bat` không báo "hoàn tất" khi copy 0 file. |
| P0.8 | Bảo mật | Bỏ IP public thật khỏi `sample.env`/`.env.sample` (placeholder); thêm `.gitignore` chặn `.env`; ghi cảnh báo creds plaintext + khuyến nghị readonly. | Không còn IP/định danh thật trong mẫu. |

---

## 6. Phase 1 — Phương pháp đo

- **P1.1 Delta sampling:** `sampler.py` lấy 2 mẫu các counter (`pg_statio_user_tables`, `pg_stat_user_tables`, `pg_stat_statements`, `pg_stat_database`) cách `window_seconds` (mặc định 30, cấu hình qua `.env` optional `SamplingWindowSeconds`). Báo cáo tỉ lệ **trong cửa sổ**. Ghi rõ `sampling_window` trong mọi báo cáo.
  - *Acceptance:* cache-hit/seq-scan/slow-query phản ánh hoạt động trong cửa sổ; report_data.json có 2 mốc mẫu.
- **P1.2 `pg_stat_statements` 3 trục:** thu và cho phép xếp theo `total_exec_time`, `calls`, `mean_exec_time`; thêm `shared_blks_read`, `temp_blks_read/written`, `stddev_exec_time`, `rows/calls`. Báo cáo hiển thị top theo `total_exec_time` là mặc định (đổi từ `mean`).
  - *Acceptance:* query tần suất cao / tổng-thời-gian cao xuất hiện ở top; không chỉ outlier hiếm.

---

## 7. Phase 2 — Chẩn đoán còn thiếu

Thêm collectors (mỗi cái là 1 module + section báo cáo + ngưỡng đánh giá):
- **P2.1 XID/MultiXact wraparound:** `age(datfrozenxid)` theo DB & top bảng; ngưỡng cảnh báo (vd >1.5B 🟡, >1.8B 🔴). *Ưu tiên cao nhất — rủi ro sập DB.*
- **P2.2 `pg_stat_database`:** deadlocks, temp_files/temp_bytes, `xact_rollback/xact_commit`, `tup_*`, conflicts, blks hit/read (delta).
- **P2.3 Wait events:** lấy mẫu `pg_stat_activity.wait_event_type/wait_event` (nhiều mẫu trong cửa sổ) → phân bố lớp nút cổ chai.
- **P2.4 Checkpoint/bgwriter:** `pg_stat_checkpointer` (PG17+) / `pg_stat_bgwriter` (guard version); `checkpoints_timed` vs `_req`.
- **P2.5 WAL + HOT:** WAL volume (delta), `n_tup_hot_upd/n_tup_upd` ratio.
- **P2.6 Index-level cache/IO:** `pg_statio_user_indexes` (idx_blks_hit/read).
- **P2.7 Stale stats:** dùng `last_analyze`/`last_autoanalyze` (đã thu) + `n_mod_since_analyze` vs `n_live_tup` → cảnh báo planner-stats cũ.
- **P2.8 Connection sâu:** idle-in-transaction count + longest xact age; sửa lỗi so `total_connections`(per-db) với `max_connections`(cluster) — nêu rõ phạm vi, thêm so với pool size `.env` nếu có.
- **P2.9 Replication slots:** `pg_replication_slots` (lag, retained WAL) ngoài `pg_stat_replication`.

*Acceptance mỗi mục:* section xuất hiện trong DB_STATUS_REPORT với ngưỡng đánh giá; `skipped` duyên dáng khi thiếu view/quyền/version.

---

## 8. Phase 3 — Mô hình đánh giá (thay điểm 0–100)

- **Bỏ** score 0–100 gộp (double-count + giả chính xác).
- **Thay bằng** bảng phân hạng theo **trục**: `db-health`, `query-performance`, `maintenance`, `connections`, `security/RLS`. Mỗi trục: 🟢/🟡/🔴 + danh sách vấn đề + **mức tin cậy** (`measured` / `estimated` / `heuristic`).
- Loại bỏ nhãn "green" dựa trên counter tích lũy; đánh giá dựa trên delta (P1) hoặc đánh dấu `estimated` nếu không có cửa sổ.
- COMBINED_REPORT hiển thị ma trận trục thay vì 1 con số.

*Acceptance:* không còn số 0–100 nào trong template/output; mỗi phán quyết kèm mức tin cậy.

---

## 9. Phase 6 — Solution engine v2 (an toàn) *(triển khai sau P4/P5 nhưng đặc tả ở đây cho liền mạch)*

- **Phân loại fix (CHỐT LẠI §0.A6 — thay taxonomy 3 lớp cũ bằng 5 lớp):**
  - `observe-only`: SELECT catalog/stats, EXPLAIN không ANALYZE.
  - `controlled-diagnostic`: EXPLAIN ANALYZE (opt-in + timeout + allowlist).
  - `maintenance-review`: ANALYZE, VACUUM / VACUUM ANALYZE, per-table autovacuum.
  - `ddl-review`: `CREATE INDEX CONCURRENTLY`, `ALTER TABLE`.
  - `dangerous`: `DROP INDEX`, `pg_terminate_backend`, partition migration, `ALTER SYSTEM`, `work_mem` global.
  - **Không lớp nào tự thực thi** (khớp N4); class chỉ quyết định trình bày/cảnh báo/approval. ANALYZE/VACUUM/EXPLAIN ANALYZE **không** còn là `auto-safe`. Field `rollback` → `recovery_or_rollback`.
- **Mặc định KHÔNG** xuất block "chạy liền" cho `dangerous`; hiển thị dưới dạng đề xuất + điều kiện + cảnh báo + verify/rollback.
- **`CONCURRENTLY`:** mỗi lệnh 1 block riêng, ghi rõ "không chạy trong transaction", cảnh báo INVALID index khi fail + cách dọn.
- **Partition:** bỏ template `INSERT...SELECT + RENAME` mất-dữ-liệu; thay bằng hướng dẫn `pg_partman` hoặc quy trình có nêu downtime + FK/RLS/trigger/grant không tự theo + yêu cầu backup.
- **`pg_terminate_backend`:** bỏ auto-sinh cho idle thường; chỉ đề xuất cho idle-in-transaction lâu, kèm cảnh báo giết session pool.
- **Server config:** chỉ sinh `ALTER SYSTEM` khi self-hosted + có RAM thật; managed → hướng dashboard; bỏ số "impact 100–1000x" cứng → mô tả phụ thuộc selectivity/kích thước/cache.
- Giữ **verify + rollback** cho mọi fix (điểm mạnh v3).

*Acceptance:* PERFORMANCE_SOLUTIONS phân nhóm rõ; nhóm dangerous không có block chạy-liền; managed không xuất `ALTER SYSTEM`.

---

## 10. Phase 4 — Chẩn đoán sâu & code-analysis

- **P4.1 EXPLAIN:** `explain.py` mặc định `ExplainMode=plan` (EXPLAIN **không** ANALYZE) cho top-N slow query; gắn plan vào finding. **CHỐT LẠI (§0.A3/B1):** ANALYZE chỉ khi opt-in tường minh + allowlist + timeout (`read-only txn + ROLLBACK` KHÔNG đủ an toàn: ANALYZE thực thi statement, không chặn lock/side-effect/tài nguyên). Query normalized `$1,$2` → generic plan khi PG≥16; PG<16 → `explain_unavailable: parameterized_pre_pg16`. Phân loại SQL bằng parser PG, không bằng regex "SELECT".
- **P4.2 Column metadata + predicate:** thu kiểu cột (`pg_attribute`); parse WHERE/JOIN từ text slow query → gợi index **cấp cột** (composite equality-first, partial soft-delete, covering INCLUDE, đúng index type). Kiểm tra index đã tồn tại để không đề xuất trùng.
- **P4.3 RLS:** `pg_policies` → phát hiện `auth.uid()`/`current_setting(...)` **không bọc `(select ...)`** (re-eval mỗi row) + cột policy thiếu index. Bật khi phát hiện RLS/Supabase.
- **P4.4 Schema:** bảng thiếu PK; UUIDv4 làm PK bảng lớn; `timestamp` thay vì `timestamptz`.
- **P4.5 Code-analysis trung thực:** giữ grep nhưng gắn **mức tin cậy**; nêu rõ "không thấy SQL ORM sinh"; **bỏ "Code Quality /100"**; ưu tiên tín hiệu chắc (nối chuỗi SQL, SELECT *, connection-leak pattern).

*Acceptance:* mỗi slow-query finding có plan hoặc lý do không chạy được EXPLAIN; ít nhất 1 gợi index cấp cột trên dữ liệu mẫu; RLS re-eval được phát hiện trên policy chưa bọc subselect.

---

## 11. Phase 5 — Nối KB thật

- Xây **bảng ánh xạ** trong `solution-index.md`: mỗi pattern → `detection` (query/tín hiệu cụ thể tool THỰC SỰ thu) → `fix` (cấp cột) → `reference` (file KB, đọc body khi cần giải thích).
- **Mở khóa** (ưu tiên): total_exec_time/calls ranking (P1.2), column-level missing index (P4.2), EXPLAIN (P4.1), RLS (P4.3), stale-stats (P2.7), composite/partial/covering (P4.2), FK-index đúng (P0.2).
- **Sửa cite sai:** pattern 5 (unused→DROP) không cite `query-missing-indexes.md`; pattern 9 (SQLi) không trỏ file không tồn tại (dùng nội dung inline hoặc tạo file security phù hợp). *(KB navigation đã có tại `references/kb/_index.md` và path SKILL.md đã rewire nội bộ — xem §0.C; mọi `reference` trong bảng ánh xạ trỏ vào `references/kb/`, không path ngoài.)*
- Đánh dấu rõ topic **không tự phát hiện được** (advisory, skip-locked, upsert, batch-insert...) là "gợi ý thủ công", không giả vờ auto.

*Acceptance:* ≥ 8/13 pattern có detection nối với tín hiệu tool thật (tăng từ ~0 chính xác); không còn cite trỏ file thiếu.

---

## 12. Phase 7 — Tests, error handling, đóng gói

- **P7.1 Golden tests:** snapshot `report_data.json` mẫu (loại nhánh metadata thời gian) → so render báo cáo ổn định. Fixture cho: có/không `pg_stat_statements`, superuser/không, managed/self-hosted, bảng dead 100%.
- **P7.2 Unit test collector:** chạy từng SQL trên container Postgres **14, 15, 16, 17, 18** (CI matrix; PG13 best-effort — §0.A4) đảm bảo không lỗi cú pháp/cột (bắt lỗi kiểu `relhasoids`).
- **P7.3 Error handling:** `statement_timeout` phía client + timeout mỗi DB; **batch isolation** (1 DB treo/không kết nối được → ghi lỗi vào report của DB đó, tiếp tục DB khác); không để 1 DB làm chết cả run.
- **P7.4 Đóng gói:** README + `setup.bat` khớp kiến trúc hybrid; liệt kê đúng file ship; `MIGRATION.md` v3→v4; bump version 3.0.0→4.0.0, cập nhật ngày.
- **P7.5 Templates:** thêm section (wraparound, waits, pg_stat_database, RLS, EXPLAIN), cột "độ tin cậy", `sampling_window`; **giữ** quy tắc `<details>` + `sanitize()` (điểm mạnh v3).

*Acceptance:* CI xanh trên 5 phiên bản PG; 1 DB die không làm hỏng run; golden test phát hiện thay đổi render ngoài ý muốn.

---

## 13. Tương thích & migration

- `.env` v3 vẫn chạy; field mới **optional** (kèm mặc định): `SamplingWindowSeconds` (mặc định 30), `SlowQueryTopN` (mặc định 20, giữ như v3), `ExplainMode` (`off|plan|analyze`, **mặc định `plan`** — §0.A3), `ExplainTopN` (5), `ExplainAnalyzeTopN` (0), `ExplainStatementTimeoutMs` (3000), `ExplainLockTimeoutMs` (500). *(Bỏ `ExplainEnabled=true` cũ.)*
- Cấu trúc output theo ngày giữ nguyên; thêm section mới trong template hiện có (không đổi tên file để so-sánh-ngày cũ vẫn hoạt động).
- Bước "so sánh ngày trước" (v3) giữ; xử lý trường hợp schema báo cáo đổi giữa v3↔v4 (chỉ so các chỉ số cùng tồn tại).

---

## 14. Thứ tự triển khai (phases độc lập, ship được từng phần)

`P-1` contract freeze + test harness + canonical renderer (§0.A7) → `P0` blocker+bảo mật+gỡ output "chạy liền" nguy hiểm → `P1` delta sampling đúng semantics (§0.A2) → `P2` core diagnostics + scope/quality metadata → `P3` rule engine + unknown/confidence → `P4` EXPLAIN plan-only + column/RLS (ANALYZE opt-in, §0.A3) → `P5` KB mapping bằng rule IDs → `P6` remediation từ versioned templates → `P7` migration+docs+packaging+release hardening.

Mỗi phase có acceptance riêng; có thể dừng sau bất kỳ phase nào mà skill vẫn hoạt động (không để trạng thái nửa vời).

---

## 15. Rủi ro & giả định

- **Determinism vs môi trường thật:** golden test cần fixture JSON, không phụ thuộc DB thật; test collector cần container PG (giả định có Docker trong CI hoặc chạy tay).
- **EXPLAIN ANALYZE thực thi query:** **CHỐT LẠI (§0.A3)** — mặc định `ExplainMode=plan` (không ANALYZE); ANALYZE chỉ opt-in + allowlist + timeout. `read-only txn + ROLLBACK` **không** đủ an toàn (ANALYZE vẫn thực thi statement, không chặn lock/side-effect/tài nguyên); giới hạn top-N nhỏ + `statement_timeout`/`lock_timeout` khi bật ANALYZE.
- **Vendor heuristic** có thể sai với nhà cung cấp lạ → mặc định fallback an toàn (coi như không-superuser, không sinh `ALTER SYSTEM`).
- **Parse predicate từ text query** là heuristic → gợi index cấp cột gắn nhãn `needs-review`, không auto.

---

## 16. Truy vết spec ↔ phát hiện đánh giá

| Phát hiện (nguồn) | Xử lý ở |
|---|---|
| Runtime thiếu / setup giả (V1) | P0.7 |
| `relhasoids` PG12+ (V1) | P0.1 |
| Partition mất dữ liệu (V1) | §9 |
| Counter tích lũy đọc như snapshot (V1) | P1.1 |
| FK-index / dup-index / dead_pct / cache-hit / index_size (V1) | P0.2–P0.5, P1.2 |
| Điểm 0–100 double-count (V1) | Phase 3 |
| Remediation nguy hiểm + managed (V1) | §4, §9 |
| XID / pg_stat_database / waits / checkpoint / index-IO / stale-stats (V1) | Phase 2 |
| KB chỉ đọc 1 file, 0 detect chính xác (V2) | Phase 5, P4.2 |
| `pg_stat_statements` chỉ mean (V2) | P1.2 |
| RLS 0% phủ (V2) | P4.3 |
| EXPLAIN cited-but-dead (V2) | P4.1 |
| Cite sai file / `_sections.md` thiếu (V2) | Phase 5 |
| Không test / SQL sinh lại mỗi run (V1/V2) | §3, P7.1–P7.2 |
| 1 DB die làm chết run (V1) | P7.3 |

---

## 17. Ghi chú vận hành

- Workspace **không phải git repo** → spec này được ghi file nhưng **không commit được**; nếu sau này khởi tạo git, commit lại.
- Bước tiếp theo sau khi duyệt spec: **writing-plans** để tạo implementation plan chi tiết (theo Superpowers).

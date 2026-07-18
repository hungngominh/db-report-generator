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

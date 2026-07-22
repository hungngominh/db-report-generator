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

## 1. LOW CACHE HIT RATIO (Database-Level)

- **Detection**: [Tự động] Diagnostic block `database_stats`, field `cache_hit_ratio` (0.0–1.0, KHÔNG phải `_pct`) → finding_id `db_health.cache_hit_ratio` (red < 0.80, yellow < 0.90; `references/rules/db-health.json`). LƯU Ý: đây là cache hit ratio cấp DATABASE, không phải cấp table — không có collector nào query `pg_statio_user_tables`. Cho cache hit cấp INDEX, xem mục **1b** bên dưới.
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
- **Remediation Class**: `ddl-review`
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`
- **Category**: DB-side / Index

**Fix Template:**
```sql
-- Bước 1: Tìm queries đang hit table này
SELECT LEFT(query, 300), calls, mean_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%{{table_name}}%'
ORDER BY total_exec_time DESC LIMIT 10;

-- Bước 2: Xem execution plan của query chậm nhất
EXPLAIN (ANALYZE, BUFFERS) {{slow_query}};

-- Bước 3: Tạo index dựa trên WHERE/JOIN columns
CREATE INDEX CONCURRENTLY idx_{{table_name}}_{{columns}}
ON {{schema}}."{{table_name}}" ({{columns}})
{{#if has_soft_delete}}WHERE "IsDeleted" = false{{/if}};
```

**Verify:**
```sql
SELECT relname, heap_blks_hit::float / NULLIF(heap_blks_hit + heap_blks_read, 0) * 100 AS cache_pct
FROM pg_statio_user_tables WHERE relname = '{{table_name}}';
```

**Expected Impact**: 100-1000x faster queries trên indexed columns

---

## 1b. LOW CACHE HIT RATIO (Index-Level)

- **Detection**: [Tự động] Diagnostic block `index_io` (`scripts/collectors/index_io.py`), field `cache_hit_ratio` (0.0–1.0) → finding_id `query_perf.index_cache_hit_ratio` (red < 0.80, yellow < 0.90; `references/rules/query-performance.json`). Đây là cache hit ratio cấp INDEX (khác mục 1, cấp DATABASE).
- **Priority**: P1 (< 80%) | P2 (80-90%)
- **Remediation Class**: `observe-only` — mẫu (`idx_blks_hit` + `idx_blks_read`) của một index riêng lẻ thường nhỏ nên tỷ lệ dễ nhiễu; chỉ dùng để theo dõi xu hướng qua nhiều lần lấy mẫu, KHÔNG tự động suy ra hành động DDL cụ thể.
- **Reference**: `query-missing-indexes.md`, `query-covering-indexes.md`
- **Category**: DB-side / Index

⚠️ **Lỗi thường gặp**: `idx_scan` KHÔNG tồn tại trong `pg_statio_user_indexes` (view đó chỉ có `idx_blks_hit`/`idx_blks_read`). `idx_scan` nằm trong `pg_stat_user_indexes`. Muốn lấy cả hai trong 1 câu truy vấn, PHẢI JOIN hai view qua `indexrelid` — xem Verify bên dưới (khớp đúng cú pháp SQL mà collector `index_io.py` đang dùng).

**Fix Template** (chưa thể sinh SQL DDL tự động — cần xác định query cụ thể trước):
```sql
-- Bước 1: Tìm các query đang dùng bảng chứa index này (thay {{table_name}} bằng tên bảng thực tế)
SELECT LEFT(query, 300), calls, mean_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%{{table_name}}%'
ORDER BY total_exec_time DESC LIMIT 10;
```

**Verify:**
```sql
SELECT sio.schemaname, sio.relname AS table_name, sio.indexrelname AS index_name,
       COALESCE(sui.idx_scan, 0) AS idx_scan, sio.idx_blks_hit, sio.idx_blks_read,
       ROUND(sio.idx_blks_hit::numeric / NULLIF(sio.idx_blks_hit + sio.idx_blks_read, 0), 4) AS
         cache_hit_ratio
FROM pg_statio_user_indexes sio
JOIN pg_stat_user_indexes sui USING (indexrelid)
WHERE sio.indexrelname IN ({{index_name_list}});
```

**Expected Impact**: Không áp dụng trực tiếp — mục đích là theo dõi xu hướng qua nhiều lần lấy mẫu (khuyến nghị 3-7 ngày) trước khi quyết định hành động (tăng cache / bỏ index nếu chỉ là mức độ nhỏ).

---

## 2. HIGH SEQUENTIAL SCAN RATIO

- **Detection**: [Tự động] Diagnostic block `seq_scan`, field `seq_scan_pct` (`seq_scan / (seq_scan + idx_scan) * 100`) → finding_id `maintenance.seq_scan_pct` (red > 80%, yellow > 50%; `references/rules/maintenance.json`, row_identity `schema,table`). LƯU Ý: collector chỉ xét bảng có `n_live_tup > 10,000` (khớp floor thấp nhất P1 bên dưới) — bảng nhỏ hơn bị loại ngay từ SQL vì Postgres ưu tiên seq scan trên bảng nhỏ một cách hợp lý, không phải vấn đề. Rule hiện dùng một ngưỡng % duy nhất (không tách riêng mốc >100K dòng cho P0), theo đúng cách các rule tỷ lệ % khác trong `maintenance.json` (`dead_tuples_pct`, `stale_stats_pct`, `index_bloat_pct`) đã làm. Mỗi row còn có field `related_queries` (rỗng nếu sampling window không bắt được query nào chạm bảng này) — danh sách nguyên văn các query trong sampling window có tham chiếu tới bảng đó, kèm `window_calls`/`window_total_exec_time_ms`, thay thế bước dò `pg_stat_statements` thủ công bên dưới khi có sẵn.
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Remediation Class**: `ddl-review`
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`
- **Category**: DB-side / Index

**Fix Template:**
```sql
-- Nếu diagnostic có related_queries: đọc nguyên văn query đó (hiển thị qua
-- <details> theo SKILL.md) để xác định eq_columns/range_columns thật, thay
-- vì đoán. Chỉ khi related_queries rỗng mới cần dò thủ công:
SELECT LEFT(query, 300), calls FROM pg_stat_statements
WHERE query ILIKE '%{{table_name}}%' ORDER BY calls DESC LIMIT 5;

-- Tạo composite index (equality columns trước, range columns sau)
CREATE INDEX CONCURRENTLY idx_{{table_name}}_{{columns}}
ON {{schema}}."{{table_name}}" ({{eq_columns}}, {{range_columns}});
```

**Verify:**
```sql
SELECT relname, seq_scan, idx_scan,
  round(seq_scan::numeric / NULLIF(seq_scan + idx_scan, 0) * 100, 2) AS seq_pct
FROM pg_stat_user_tables WHERE relname = '{{table_name}}';
```

**Expected Impact**: 100-1000x faster, loại bỏ full table scans

---

## 3. HIGH DEAD TUPLE RATIO

- **Detection**: [Tự động] Diagnostic block `dead_tuples`, field `dead_pct` → finding_id `maintenance.dead_tuples_pct` (red > 20%, yellow > 5%; `references/rules/maintenance.json`, row_identity `schema,table`). Block trả `n_live`/`n_dead` (KHÔNG phải `n_live_tup`/`n_dead_tup` như tên cột gốc `pg_stat_user_tables`).
- **Priority**: P0 (> 50%) | P1 (20-50%) | P2 (5-20%)
- **Remediation Class**: `maintenance-review`
- **Reference**: `monitor-vacuum-analyze.md`
- **Category**: DB-side / Maintenance

**Fix Template:**
```sql
-- Immediate fix
VACUUM ANALYZE {{schema}}."{{table_name}}";

-- Long-term: tune autovacuum riêng cho table này
ALTER TABLE {{schema}}."{{table_name}}" SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_analyze_scale_factor = 0.02,
  autovacuum_vacuum_cost_delay = 10
);
```

**Verify:**
```sql
SELECT relname, n_dead_tup, n_live_tup,
  round(n_dead_tup::numeric / NULLIF(n_live_tup, 0) * 100, 2) AS dead_pct,
  last_autovacuum
FROM pg_stat_user_tables WHERE relname = '{{table_name}}';
```

**recovery_or_rollback:**
```sql
ALTER TABLE {{schema}}."{{table_name}}" RESET (
  autovacuum_vacuum_scale_factor,
  autovacuum_analyze_scale_factor,
  autovacuum_vacuum_cost_delay
);
```

**Expected Impact**: 2-10x better query plans, giải phóng disk space

---

## 4. SLOW QUERIES (High Mean Execution Time)

- **Detection**: [Tự động] Diagnostic block `query_stats`, field `window_mean_exec_time_ms` (mean trong sampling window, KHÔNG phải `mean_exec_time` tích lũy) → finding_id `query_perf.slow_query_mean_exec_time` (red > 1000ms, yellow > 100ms; `references/rules/query-performance.json`, row_identity `queryid`). EXPLAIN plan tự động gắn kèm top-N query chậm nhất — xem mục 16. Xếp hạng bổ sung theo tổng thời gian × số lần gọi — xem mục 18.
- **Priority**: P0 (> 5000ms) | P1 (1000-5000ms) | P2 (100-1000ms)
- **Remediation Class**: `ddl-review`
- **Reference**: `monitor-explain-analyze.md`, `query-composite-indexes.md`
- **Category**: DB-side / Query + Index

**Fix Template:**
```sql
-- Bước 1: Lấy full query
SELECT query FROM pg_stat_statements WHERE queryid = {{queryid}};

-- Bước 2: Phân tích execution plan
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {{query}};

-- Bước 3: Dựa trên plan, xử lý theo pattern:

-- Pattern A: Seq Scan → Tạo index
CREATE INDEX CONCURRENTLY idx_{{table}}_{{filter_columns}}
ON {{schema}}."{{table}}" ({{filter_columns}});

-- Pattern B: Nested Loop trên bảng lớn → Tạo index cho JOIN column
CREATE INDEX CONCURRENTLY idx_{{table}}_{{join_column}}
ON {{schema}}."{{table}}" ({{join_column}});

-- Pattern C: Sort lớn → Tạo index bao gồm ORDER BY columns
CREATE INDEX CONCURRENTLY idx_{{table}}_{{sort_columns}}
ON {{schema}}."{{table}}" ({{filter_columns}}, {{sort_columns}});
```

**Verify:**
```sql
SELECT queryid, mean_exec_time, calls
FROM pg_stat_statements WHERE queryid = {{queryid}};
-- So sánh mean_exec_time trước và sau
```

**Expected Impact**: 10-100x faster per query

---

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

---

## 6. CONNECTION EXHAUSTION

- **Detection**: [Tự động] Diagnostic block `connection_depth`. 3 finding_id riêng biệt (`references/rules/connections.json`) — KHÔNG gộp chung "total/max" như v3: `connections.cluster_pressure` (tỷ lệ `cluster_connections`/`cluster_max_connections`, red > 0.90, yellow > 0.60), `connections.pool_pressure` (tỷ lệ `db_connections`/`configured_pool_size`, red > 0.90, yellow > 0.60), `connections.idle_in_transaction` (field `longest_txn_seconds`, red > 600s, yellow > 60s).
- **Priority**: P0 (> 90%) | P1 (80-90%)
- **Remediation Class**: `dangerous` — KHÔNG đưa vào block chạy-liền, chỉ đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)".
- **Reference**: `conn-pooling.md`, `conn-limits.md`, `conn-idle-timeout.md`
- **Category**: Architecture / Connection Management

**Fix Template** (KHÔNG đưa vào block chạy-liền — chỉ tham khảo cho review thủ công):
```sql
-- Immediate: kill sessions kẹt trong transaction > 5 phút (KHÔNG kill 'idle' thường — có thể đang được PgBouncer/Supavisor pool giữ lại)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < now() - interval '5 minutes'
  AND datname = current_database();

-- Config idle timeout
-- CHỈ chạy nếu capabilities.managed == false VÀ capabilities.is_superuser == true — managed platform (Supabase/RDS) không hỗ trợ ALTER SYSTEM, đổi qua console/dashboard
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

---

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
-- CHỈ chạy nếu capabilities.managed == false VÀ capabilities.is_superuser == true — managed platform không hỗ trợ ALTER SYSTEM, đổi qua console/dashboard
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

---

## 8. N+1 QUERY PATTERN

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep loop chứa DB call bên trong (không phải collector Python) — confidence tier mặc định `estimated` (cần agent tự xác nhận loop có thực sự gọi DB mỗi vòng), theo bảng độ tin cậy §5.8.
- **Priority**: P1
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `data-n-plus-one.md`
- **Category**: Code-side / Query Pattern

**Fix Template (C#/.NET Entity Framework):**
```csharp
// ❌ TRƯỚC (N+1): 1 query + N queries
foreach (var user in users)
{
    var orders = db.Orders.Where(o => o.UserId == user.Id).ToList();
}

// ✅ SAU - Option A: Eager Loading
var usersWithOrders = db.Users
    .Include(u => u.Orders)
    .Where(u => u.IsActive)
    .ToList();

// ✅ SAU - Option B: Batch Query
var userIds = users.Select(u => u.Id).ToList();
var allOrders = db.Orders
    .Where(o => userIds.Contains(o.UserId))
    .GroupBy(o => o.UserId)
    .ToDictionary(g => g.Key, g => g.ToList());
```

**Fix Template (Dapper):**
```csharp
// ❌ TRƯỚC
foreach (var id in userIds)
    conn.Query("SELECT * FROM Orders WHERE UserId = @Id", new { Id = id });

// ✅ SAU
var allOrders = conn.Query(
    "SELECT * FROM Orders WHERE UserId = ANY(@Ids)",
    new { Ids = userIds.ToArray() });
```

**Expected Impact**: 10-100x fewer database round trips

---

## 9. SQL INJECTION RISK

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep string-concatenated/interpolated SQL context — confidence tier `measured` khi chuỗi text nối SQL xuất hiện rõ ràng (vd. `"SELECT * FROM " + table`), theo bảng độ tin cậy §5.8.
- **Priority**: P0
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `security-sql-injection.md`
- **Category**: Code-side / Security

**Fix Template (C#/.NET):**
```csharp
// ❌ TRƯỚC (vulnerable):
db.Database.ExecuteSqlRaw($"SELECT * FROM Users WHERE Name = '{input}'");
// hoặc
var sql = "SELECT * FROM Users WHERE Name = '" + input + "'";

// ✅ SAU (parameterized):
db.Database.ExecuteSqlRaw("SELECT * FROM Users WHERE Name = {0}", input);
// hoặc
db.Users.FromSqlInterpolated($"SELECT * FROM Users WHERE Name = {input}");
// hoặc Dapper:
conn.Query("SELECT * FROM Users WHERE Name = @Name", new { Name = input });
```

**Expected Impact**: Loại bỏ SQL injection attack vector

---

## 10. MISSING PAGINATION

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep query trả về tất cả rows không có LIMIT/OFFSET/cursor — confidence tier `heuristic` (suy luận từ việc KHÔNG thấy LIMIT, không phải bằng chứng trực tiếp), theo bảng độ tin cậy §5.8.
- **Priority**: P1 (tables > 10K rows) | P2 (tables > 1K rows)
- **Remediation Class**: `n/a (code-side fix, không phải remediation DB)`
- **Reference**: `data-pagination.md`
- **Category**: Code-side / Query Pattern

**Fix Template (SQL):**
```sql
-- ❌ TRƯỚC: Offset pagination (chậm ở page lớn)
SELECT * FROM {{table}} ORDER BY id OFFSET 10000 LIMIT 20;

-- ✅ SAU: Cursor-based pagination (O(1) mọi depth)
SELECT * FROM {{table}} WHERE id > {{last_id}} ORDER BY id LIMIT 20;
```

**Fix Template (C#/.NET):**
```csharp
// ❌ TRƯỚC
var all = db.Orders.ToList();

// ✅ SAU
var page = db.Orders
    .Where(o => o.Id > lastId)
    .OrderBy(o => o.Id)
    .Take(pageSize)
    .ToList();
```

**Expected Impact**: Consistent O(1) performance ở mọi page depth

---

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

---

## 12. MISSING FOREIGN KEY INDEXES

- **Detection**: [Tự động] Diagnostic block `fk_missing_index`, fields `schema`, `table`, `constraint`, `columns`, `suggested_ddl` → finding_id `maintenance.fk_missing_index` (presence rule, assessment cố định `red`; `references/rules/maintenance.json`, row_identity `schema,table,constraint`).
- **Priority**: P1
- **Remediation Class**: `ddl-review`
- **Reference**: `schema-foreign-key-indexes.md`
- **Category**: DB-side / Index

**Fix Template:**
```sql
-- Auto-detect missing FK indexes
SELECT
  c.conrelid::regclass AS table_name,
  a.attname AS fk_column,
  'CREATE INDEX CONCURRENTLY idx_' || c.conrelid::regclass || '_' || a.attname
    || ' ON ' || c.conrelid::regclass || ' (' || a.attname || ');' AS fix_sql
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.conrelid AND a.attnum = ANY(i.indkey)
  );

-- Execute generated CREATE INDEX statements
{{generated_fix_sql}}
```

**Expected Impact**: 10-100x faster JOINs và CASCADE operations

---

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

---

## 14. RLS POLICY RE-EVALUATION PERFORMANCE TRAP

- **Detection**: [Tự động] Diagnostic block `rls_policies` → finding_id `security_rls.rls_policy_issue` (presence rule, assessment cố định `yellow`; `references/rules/security-rls.json`, row_identity `schema,table,policy,clause,issue,function,column`). Field `issue` nhận đúng 2 giá trị: `unwrapped_reeval_call` (gọi `auth.uid()`/`auth.role()`/`auth.jwt()`/`current_setting()` KHÔNG bọc trong scalar subselect — field `function` được set, `column` = null) hoặc `missing_supporting_index` (cột dùng trong equality predicate của policy không có index hỗ trợ — field `column` được set, `function` = null).
- **Priority**: P1
- **Remediation Class**: `ddl-review`
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
- **Remediation Class**: `maintenance-review`
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

- **Detection**: [Tự động, một phần — không có finding_id riêng] Diagnostic block `explain` (gắn tự động vào top-N query chậm nhất từ mục 4, `ExplainTopN` query). Mỗi row: `{queryid, mode ("plan"|"analyze"), plan (JSON plan hoặc null), explain_unavailable (lý do hoặc null, vd. "parameterized_pre_pg16"), analyze_skipped_reason, role, search_path, database}`. KHÔNG có rule/finding_id nào target block này trong `references/rules/*.json` — đây là bằng chứng bổ trợ đọc kèm finding của mục 4, không phải finding độc lập.
- **Priority**: (kế thừa priority của mục 4 — không có priority riêng)
- **Remediation Class**: `observe-only` (mặc định, EXPLAIN không ANALYZE) / `controlled-diagnostic` (khi ANALYZE opt-in)
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
- **Remediation Class**: `ddl-review`
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

- **Detection**: [Tự động, một phần — không có finding_id riêng] Diagnostic block `query_stats`, fields `window_total_exec_time_ms`, `window_calls` (sampler đã pre-sort giảm dần theo `window_total_exec_time_ms`, collector không sort lại). KHÔNG có finding_id riêng cho field này (chỉ `window_mean_exec_time_ms` có rule — xem mục 4) — dùng như bảng xếp hạng bổ trợ để ưu tiên tối ưu query nào ảnh hưởng tổng tải nhiều nhất, kể cả khi mean_exec_time không vượt ngưỡng.
- **Priority**: (bổ trợ — dùng priority của mục 4 nếu cùng query vượt ngưỡng mean_exec_time)
- **Remediation Class**: `observe-only`
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
- **Remediation Class**: `ddl-review`
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

| Condition | Priority |
|-----------|----------|
| SQL injection detected | **P0** |
| Cache hit < 50% trên active table | **P0** |
| Blocking queries active | **P0** |
| Connection usage > 90% | **P0** |
| Dead tuples > 50% | **P0** |
| Cache hit 50-80% | **P1** |
| Slow query avg > 1000ms | **P1** |
| N+1 pattern in code | **P1** |
| Missing FK index | **P1** |
| Connection usage 60-90% | **P1** |
| Dead tuples 20-50% | **P1** |
| shared_buffers < 15% RAM | **P1** |
| Cache hit 80-90% | **P2** |
| Unused indexes | **P2** |
| Slow query avg 100-1000ms | **P2** |
| Missing pagination (>10K rows) | **P2** |
| SELECT * pattern | **P2** |
| Dead tuples 5-20% | **P2** |
| Table >10M rows, no partition | **P2** |
| Server config suboptimal | **P2** |
| Index bloat | **P3** |
| Duplicate indexes | **P3** |
| Covering index opportunities | **P3** |

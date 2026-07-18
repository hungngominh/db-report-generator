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

- **Detection**: [Tự động] Diagnostic block `database_stats`, field `cache_hit_ratio` (0.0–1.0, KHÔNG phải `_pct`) → finding_id `db_health.cache_hit_ratio` (red < 0.80, yellow < 0.90; `references/rules/db-health.json`). LƯU Ý: đây là cache hit ratio cấp DATABASE, không phải cấp table — không có collector nào query `pg_statio_user_tables`. Cho cache hit cấp INDEX, xem block `index_io` / finding_id `query_perf.index_cache_hit_ratio`.
- **Priority**: P0 (< 50%) | P1 (50-80%) | P2 (80-90%)
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

## 2. HIGH SEQUENTIAL SCAN RATIO

- **Detection**: [Gợi ý thủ công — không có collector] Không có block/collector nào trong db-report-generator v4 thu thập `seq_scan`/`idx_scan` cấp table (`pg_stat_user_tables`). Đây KHÔNG phải một automated finding — dùng Fix Template bên dưới như một truy vấn thủ công khi nghi ngờ table bị seq scan nhiều (vd. khi thấy `Seq Scan` trong EXPLAIN plan của mục 4/16).
- **Priority**: P0 (> 80% seq, > 100K rows) | P1 (> 50% seq, > 10K rows)
- **Reference**: `query-missing-indexes.md`, `query-composite-indexes.md`
- **Category**: DB-side / Index (thủ công)

**Fix Template:**
```sql
-- Tìm columns đang bị filter (từ pg_stat_statements)
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

**Rollback:**
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

---

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

---

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

---

## 8. N+1 QUERY PATTERN

- **Detection**: [Code-analysis — xem SKILL.md §5.8] Agent tự grep loop chứa DB call bên trong (không phải collector Python) — confidence tier mặc định `estimated` (cần agent tự xác nhận loop có thực sự gọi DB mỗi vòng), theo bảng độ tin cậy §5.8.
- **Priority**: P1
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

---

## 12. MISSING FOREIGN KEY INDEXES

- **Detection**: [Tự động] Diagnostic block `fk_missing_index`, fields `schema`, `table`, `constraint`, `columns`, `suggested_ddl` → finding_id `maintenance.fk_missing_index` (presence rule, assessment cố định `red`; `references/rules/maintenance.json`, row_identity `schema,table,constraint`).
- **Priority**: P1
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

---

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

-- ============================================
-- SOLUTION GENERATION QUERIES
-- Queries tạo fix SQL statements tự động
-- Dùng cho PERFORMANCE_SOLUTIONS.md
-- ============================================

-- 1. Missing Foreign Key Indexes (auto-generate CREATE INDEX)
SELECT
  c.conrelid::regclass AS table_name,
  c.conname AS constraint_name,
  a.attname AS fk_column,
  cf.relname AS referenced_table,
  'CREATE INDEX CONCURRENTLY idx_'
    || replace(c.conrelid::regclass::text, '"', '')
    || '_' || a.attname
    || ' ON ' || c.conrelid::regclass || ' (' || a.attname || ');' AS fix_sql
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
JOIN pg_class cf ON cf.oid = c.confrelid
WHERE c.contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.conrelid AND a.attnum = ANY(i.indkey)
  )
ORDER BY c.conrelid::regclass::text;

-- 2. Seq-scan tables cross-referenced with actual queries (for targeted index creation)
-- LƯU Ý: Query này JOIN pg_stat_statements, phải detect schema trước
-- Dùng kết quả từ queries-performance.sql bước 2a để lấy ext_schema
-- Thay {{ext_schema}} bằng schema thực tế (ví dụ: extensions, public)
-- Nếu pg_stat_statements không có, chạy version không có JOIN (bên dưới)

-- Version CÓ pg_stat_statements:
SELECT
  t.schemaname,
  t.relname AS table_name,
  t.seq_scan,
  t.idx_scan,
  t.n_live_tup,
  round(t.seq_scan::numeric / NULLIF(t.seq_scan + t.idx_scan, 0) * 100, 2) AS seq_pct,
  regexp_replace(LEFT(s.query, 300), E'[\\n\\r\\t]+', ' ', 'g') AS query_sample,
  s.calls AS query_calls,
  round(s.mean_exec_time::numeric, 2) AS avg_ms
FROM pg_stat_user_tables t
LEFT JOIN {{ext_schema}}.pg_stat_statements s
  ON s.query ILIKE '%' || t.relname || '%'
  AND s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
WHERE t.seq_scan > 100
  AND t.n_live_tup > 10000
  AND t.seq_scan > COALESCE(t.idx_scan, 0)
ORDER BY t.seq_tup_read DESC
LIMIT 30;

-- Version KHÔNG CÓ pg_stat_statements (fallback):
-- SELECT
--   t.schemaname,
--   t.relname AS table_name,
--   t.seq_scan,
--   t.idx_scan,
--   t.n_live_tup,
--   round(t.seq_scan::numeric / NULLIF(t.seq_scan + t.idx_scan, 0) * 100, 2) AS seq_pct,
--   NULL AS query_sample,
--   NULL AS query_calls,
--   NULL AS avg_ms
-- FROM pg_stat_user_tables t
-- WHERE t.seq_scan > 100
--   AND t.n_live_tup > 10000
--   AND t.seq_scan > COALESCE(t.idx_scan, 0)
-- ORDER BY t.seq_tup_read DESC
-- LIMIT 30;

-- 3. Duplicate Indexes (auto-generate DROP INDEX)
SELECT
  pg_size_pretty(sum(pg_relation_size(idx))::bigint) AS total_wasted_size,
  (array_agg(idx))[1] AS keep_index,
  (array_agg(idx))[2] AS drop_index,
  'DROP INDEX CONCURRENTLY ' || (array_agg(idx))[2] || ';' AS fix_sql
FROM (
  SELECT indexrelid::regclass AS idx,
    (indrelid::text || E'\n' || indclass::text || E'\n' ||
     indkey::text || E'\n' || COALESCE(indexprs::text, '') ||
     E'\n' || COALESCE(indpred::text, '')) AS key
  FROM pg_index
) sub
GROUP BY key HAVING count(*) > 1
ORDER BY sum(pg_relation_size(idx)) DESC;

-- 4. Tables needing VACUUM (auto-generate VACUUM + autovacuum tuning)
SELECT
  schemaname, relname,
  n_dead_tup,
  n_live_tup,
  CASE WHEN n_live_tup > 0
    THEN round(n_dead_tup::numeric / n_live_tup * 100, 2)
    ELSE 0
  END AS dead_pct,
  last_autovacuum,
  -- Immediate fix
  'VACUUM ANALYZE ' || schemaname || '."' || relname || '";' AS immediate_fix,
  -- Long-term fix
  'ALTER TABLE ' || schemaname || '."' || relname || '" SET ('
    || 'autovacuum_vacuum_scale_factor = 0.05, '
    || 'autovacuum_analyze_scale_factor = 0.02);' AS long_term_fix
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC
LIMIT 20;

-- 5. Server config vs recommendations
SELECT
  name, setting, unit,
  CASE
    WHEN name = 'shared_buffers' THEN '25% of server RAM'
    WHEN name = 'effective_cache_size' THEN '75% of server RAM'
    WHEN name = 'work_mem' THEN '50-256MB depending on concurrent queries'
    WHEN name = 'maintenance_work_mem' THEN '512MB-2GB'
    WHEN name = 'max_connections' THEN 'Use connection pooler, keep 100-200'
    WHEN name = 'random_page_cost' THEN '1.1 for SSD, 4.0 for HDD'
    WHEN name = 'effective_io_concurrency' THEN '200 for SSD, 2 for HDD'
    WHEN name = 'checkpoint_completion_target' THEN '0.9'
    WHEN name = 'wal_buffers' THEN '64MB'
    ELSE 'Review based on workload'
  END AS recommendation,
  CASE
    WHEN name = 'shared_buffers' THEN
      'ALTER SYSTEM SET shared_buffers = ''CALCULATED''; -- Requires restart'
    WHEN name = 'effective_cache_size' THEN
      'ALTER SYSTEM SET effective_cache_size = ''CALCULATED''; SELECT pg_reload_conf();'
    WHEN name = 'work_mem' THEN
      'ALTER SYSTEM SET work_mem = ''64MB''; SELECT pg_reload_conf();'
    WHEN name = 'maintenance_work_mem' THEN
      'ALTER SYSTEM SET maintenance_work_mem = ''1GB''; SELECT pg_reload_conf();'
    WHEN name = 'random_page_cost' THEN
      'ALTER SYSTEM SET random_page_cost = 1.1; SELECT pg_reload_conf();'
    WHEN name = 'effective_io_concurrency' THEN
      'ALTER SYSTEM SET effective_io_concurrency = 200; SELECT pg_reload_conf();'
    ELSE NULL
  END AS fix_sql
FROM pg_settings
WHERE name IN (
  'shared_buffers', 'work_mem', 'maintenance_work_mem',
  'effective_cache_size', 'max_connections',
  'random_page_cost', 'effective_io_concurrency',
  'checkpoint_completion_target', 'wal_buffers'
);

-- 6. Partition candidates (tables > 1M rows)
SELECT
  schemaname, relname,
  n_live_tup,
  pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
  pg_size_pretty(pg_relation_size(relid)) AS data_size
FROM pg_stat_user_tables
WHERE n_live_tup > 1000000
ORDER BY n_live_tup DESC;

-- 7. Index bloat candidates (> 100MB, for REINDEX)
SELECT
  schemaname || '."' || relname || '"' AS table_name,
  indexrelname AS index_name,
  pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
  idx_scan,
  'REINDEX INDEX CONCURRENTLY ' || schemaname || '."' || indexrelname || '";' AS fix_sql
FROM pg_stat_user_indexes
WHERE pg_relation_size(indexrelid) > 100 * 1024 * 1024  -- > 100MB
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 10;

-- 8. Idle connections to terminate
SELECT
  pid, usename, state, state_change,
  now() - state_change AS idle_duration,
  'SELECT pg_terminate_backend(' || pid || ');' AS fix_sql
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < now() - interval '10 minutes'
  AND datname = current_database()
ORDER BY state_change
LIMIT 20;

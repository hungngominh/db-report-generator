-- ============================================
-- PERFORMANCE ANALYSIS QUERIES
-- ============================================

-- 1. Cache hit ratio per table (Top 20 worst)
SELECT
  schemaname, relname,
  heap_blks_read as disk_reads,
  heap_blks_hit as cache_hits,
  CASE WHEN heap_blks_hit + heap_blks_read > 0
    THEN round(heap_blks_hit::numeric / (heap_blks_hit + heap_blks_read) * 100, 2)
    ELSE 0
  END as cache_hit_pct
FROM pg_statio_user_tables
WHERE heap_blks_hit + heap_blks_read > 0
ORDER BY heap_blks_read DESC
LIMIT 20;

-- ============================================
-- 2. pg_stat_statements: DETECT SCHEMA TRƯỚC
-- ============================================
-- Bước 2a: Kiểm tra extension có tồn tại và tìm schema
-- LUÔN chạy query này TRƯỚC khi query pg_stat_statements
SELECT
  e.extname,
  n.nspname AS ext_schema,
  e.extversion
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'pg_stat_statements';
-- Nếu trả về 0 dòng → extension chưa cài, bỏ qua slow queries
-- Nếu trả về 1 dòng → lấy ext_schema để dùng ở bước 2b

-- Bước 2b: Detect PostgreSQL version (ảnh hưởng tên cột)
SELECT current_setting('server_version_num')::int AS version_num;
-- >= 130000: dùng total_exec_time, mean_exec_time, max_exec_time
-- <  130000: dùng total_time, mean_time, max_time

-- Bước 2c: Top 20 slowest queries (thay {{ext_schema}} bằng giá trị từ 2a)
-- IMPORTANT: regexp_replace strips newlines/tabs to prevent markdown table breakage
-- PostgreSQL >= 13:
SELECT
  queryid,
  regexp_replace(LEFT(query, 200), E'[\\n\\r\\t]+', ' ', 'g') as query_preview,
  calls,
  round(total_exec_time::numeric, 2) as total_time_ms,
  round(mean_exec_time::numeric, 2) as avg_time_ms,
  round(max_exec_time::numeric, 2) as max_time_ms,
  rows
FROM {{ext_schema}}.pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY mean_exec_time DESC
LIMIT 20;

-- PostgreSQL < 13 (thay tên cột):
-- SELECT
--   queryid,
--   regexp_replace(LEFT(query, 200), E'[\\n\\r\\t]+', ' ', 'g') as query_preview,
--   calls,
--   round(total_time::numeric, 2) as total_time_ms,
--   round(mean_time::numeric, 2) as avg_time_ms,
--   round(max_time::numeric, 2) as max_time_ms,
--   rows
-- FROM {{ext_schema}}.pg_stat_statements
-- WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
-- ORDER BY mean_time DESC
-- LIMIT 20;

-- 3. Table sizes (Top 20)
SELECT
  schemaname,
  relname as table_name,
  pg_size_pretty(pg_total_relation_size(relid)) as total_size,
  pg_size_pretty(pg_relation_size(relid)) as data_size,
  pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size,
  n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;

-- 4. Blocking queries
SELECT
  blocked_locks.pid AS blocked_pid,
  blocked_activity.usename AS blocked_user,
  LEFT(blocked_activity.query, 150) AS blocked_query,
  blocking_locks.pid AS blocking_pid,
  blocking_activity.usename AS blocking_user,
  LEFT(blocking_activity.query, 150) AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
  AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
  AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
  AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
  AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
  AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
  AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
  AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
  AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
  AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
  AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

-- 5. Long running queries (> 5 minutes)
SELECT
  pid, usename, state, query_start,
  now() - query_start AS duration,
  LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE state != 'idle'
  AND query_start < now() - interval '5 minutes'
  AND datname = current_database()
ORDER BY duration DESC;

-- 6. Dead tuples (need VACUUM)
SELECT
  schemaname, relname,
  n_live_tup, n_dead_tup,
  CASE WHEN n_live_tup > 0
    THEN round(n_dead_tup::numeric / n_live_tup * 100, 2)
    ELSE 0
  END as dead_pct,
  last_vacuum, last_autovacuum,
  last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC
LIMIT 20;

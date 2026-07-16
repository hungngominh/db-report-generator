-- ============================================
-- DATABASE OVERVIEW QUERIES
-- ============================================

-- 1. Database size
SELECT
  pg_database.datname,
  pg_size_pretty(pg_database_size(pg_database.datname)) as size
FROM pg_database
WHERE datname = current_database();

-- 2. Server uptime
SELECT now() - pg_postmaster_start_time() AS uptime;

-- 3. Active connections
SELECT count(*) as active_connections
FROM pg_stat_activity
WHERE datname = current_database() AND state = 'active';

-- 4. Total connections
SELECT count(*) as total_connections
FROM pg_stat_activity
WHERE datname = current_database();

-- 5. Overall cache hit ratio
SELECT
  sum(heap_blks_read) as heap_read,
  sum(heap_blks_hit) as heap_hit,
  CASE WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
    THEN round(sum(heap_blks_hit)::numeric / (sum(heap_blks_hit) + sum(heap_blks_read)) * 100, 2)
    ELSE 0
  END as cache_hit_ratio
FROM pg_statio_user_tables;

-- 6. PostgreSQL version
SELECT version();

-- 7. Current settings summary
SELECT name, setting, unit, short_desc
FROM pg_settings
WHERE name IN (
  'shared_buffers', 'work_mem', 'maintenance_work_mem',
  'effective_cache_size', 'max_connections',
  'checkpoint_completion_target', 'wal_buffers',
  'random_page_cost', 'effective_io_concurrency'
);

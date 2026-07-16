-- ============================================
-- INDEX ANALYSIS QUERIES
-- ============================================

-- 1. Missing indexes (tables with high seq scan ratio)
SELECT
  schemaname, relname,
  seq_scan, seq_tup_read,
  idx_scan, idx_tup_fetch,
  n_live_tup,
  CASE WHEN seq_scan + idx_scan > 0
    THEN round(seq_scan::numeric / (seq_scan + idx_scan) * 100, 2)
    ELSE 0
  END as seq_scan_pct
FROM pg_stat_user_tables
WHERE seq_scan > 100
  AND n_live_tup > 10000
  AND (idx_scan IS NULL OR idx_scan < seq_scan)
ORDER BY seq_tup_read DESC
LIMIT 20;

-- 2. Index usage statistics (least used)
SELECT
  schemaname, relname as table_name,
  indexrelname as index_name,
  idx_scan as times_used,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;

-- 3. Unused indexes (candidates for removal)
SELECT
  schemaname, relname as table_name,
  indexrelname as index_name,
  idx_scan as times_used,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelname NOT LIKE '%_pkey'
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;

-- 4. Duplicate indexes
SELECT
  pg_size_pretty(sum(pg_relation_size(idx))::bigint) AS size,
  (array_agg(idx))[1] AS idx1,
  (array_agg(idx))[2] AS idx2,
  (array_agg(idx))[3] AS idx3,
  (array_agg(idx))[4] AS idx4
FROM (
  SELECT
    indexrelid::regclass AS idx,
    (indrelid::text || E'\n' || indclass::text || E'\n' ||
     indkey::text || E'\n' || coalesce(indexprs::text, '') ||
     E'\n' || coalesce(indpred::text, '')) AS key
  FROM pg_index
) sub
GROUP BY key
HAVING count(*) > 1
ORDER BY sum(pg_relation_size(idx)) DESC;

-- 5. Index bloat estimation
SELECT
  current_database() AS db,
  schemaname, tablename, reltuples::bigint AS tups,
  relpages::bigint AS pages,
  otta,
  ROUND(CASE WHEN otta = 0 OR sml.relpages = 0 THEN 0.0
    ELSE sml.relpages / otta::numeric END, 1) AS tbloat,
  CASE WHEN relpages < otta THEN 0
    ELSE relpages::bigint - otta END AS wastedpages,
  CASE WHEN relpages < otta THEN 0
    ELSE (relpages - otta)::bigint * 8192 END AS wastedbytes,
  CASE WHEN relpages < otta THEN '0 bytes'::text
    ELSE pg_size_pretty((relpages - otta)::bigint * 8192) END AS wastedsize,
  iname, ituples::bigint AS itups, ipages::bigint AS ipages,
  iotta,
  ROUND(CASE WHEN iotta = 0 OR ipages = 0 THEN 0.0
    ELSE ipages / iotta::numeric END, 1) AS ibloat,
  CASE WHEN ipages < iotta THEN 0
    ELSE ipages::bigint - iotta END AS iwastedpages,
  CASE WHEN ipages < iotta THEN 0
    ELSE (ipages - iotta)::bigint * 8192 END AS iwastedbytes,
  CASE WHEN ipages < iotta THEN '0 bytes'::text
    ELSE pg_size_pretty((ipages - iotta)::bigint * 8192) END AS iwastedsize
FROM (
  SELECT
    nn.nspname AS schemaname,
    cc.relname AS tablename,
    COALESCE(cc.reltuples, 0) AS reltuples,
    COALESCE(cc.relpages, 0) AS relpages,
    COALESCE(bs * CEIL((datahdr + ma -
      (CASE WHEN datahdr%ma = 0 THEN ma ELSE datahdr%ma END)) / ma +
      nullhdr2 + 4) / (bs - 20::float), 0) AS otta,
    COALESCE(c2.relname, '?') AS iname,
    COALESCE(c2.reltuples, 0) AS ituples,
    COALESCE(c2.relpages, 0) AS ipages,
    COALESCE(CEIL(reltuples / FLOOR((bs - pageopqdata - pagehdr) /
      (4 + nulldatahdrwidth)::float)), 0) AS iotta
  FROM (
    SELECT
      ma, bs, foo.nspname, foo.relname, foo.reltuples, foo.relpages,
      foo.oid, foo.heession, foo.fillfactor,
      (datawidth + (hdr + ma - (CASE WHEN hdr%ma = 0 THEN ma ELSE hdr%ma END)))::numeric AS datahdr,
      (maxfracsum * (nullhdr + ma - (CASE WHEN nullhdr%ma = 0 THEN ma ELSE nullhdr%ma END))) AS nullhdr2
    FROM (
      SELECT
        ns.nspname, tbl.relname, tbl.reltuples, tbl.relpages, tbl.oid,
        current_setting('block_size')::numeric AS bs, 27 AS hdr, 4 AS ma,
        tbl.relhasoids AS heession,
        COALESCE((
          SELECT (regexp_matches(reloptions::text, E'fillfactor=(\\d+)'))[1]::int
          FROM pg_class WHERE oid = tbl.oid AND reloptions IS NOT NULL), 100) AS fillfactor,
        SUM((1 - coalesce(s.null_frac, 0)) * coalesce(s.avg_width, 1024)) AS datawidth,
        MAX(coalesce(s.null_frac, 0)) AS maxfracsum,
        27 + (
          CASE WHEN MAX(coalesce(s.null_frac, 0)) > 0 THEN (7 + count(s.attname)) / 8 ELSE 0::int END
        ) AS nullhdr
      FROM pg_attribute AS a
      JOIN pg_class AS tbl ON a.attrelid = tbl.oid
      JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
      LEFT JOIN pg_stats AS s ON s.schemaname = ns.nspname
        AND s.tablename = tbl.relname AND s.attname = a.attname AND s.inherited = false
      WHERE a.attnum > 0 AND NOT a.attisdropped AND tbl.relkind = 'r'
        AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
      GROUP BY ns.nspname, tbl.relname, tbl.reltuples, tbl.relpages, tbl.oid, tbl.relhasoids
    ) AS foo
  ) AS rs
  JOIN pg_class cc ON cc.relname = rs.relname
  JOIN pg_namespace nn ON cc.relnamespace = nn.oid AND nn.nspname = rs.nspname
  LEFT JOIN pg_index i ON indrelid = cc.oid
  LEFT JOIN pg_class c2 ON c2.oid = i.indexrelid,
  LATERAL (SELECT 8 AS pageopqdata, 24 AS pagehdr,
    CASE WHEN MAX(coalesce(s.null_frac, 0)) > 0 THEN 2 ELSE 0 END AS nulldatahdrwidth
    FROM pg_stats s WHERE s.schemaname = nn.nspname AND s.tablename = cc.relname) AS const
) AS sml
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY wastedbytes DESC
LIMIT 10;

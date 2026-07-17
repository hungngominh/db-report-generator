"""P0.5 — table size breakdown with a correctly-labeled index size."""
from scripts.collectors import base

_SQL = """
SELECT ns.nspname AS schema, rel.relname AS tbl,
       pg_total_relation_size(rel.oid) AS total_bytes,
       pg_relation_size(rel.oid) AS heap_bytes,
       pg_indexes_size(rel.oid) AS index_bytes,
       COALESCE(pg_total_relation_size(rel.reltoastrelid), 0) AS toast_bytes,
       rel.reltuples::bigint AS row_estimate
FROM pg_class rel
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE rel.relkind = 'r'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "total_bytes": int(r[2]),
         "heap_bytes": int(r[3]), "index_bytes": int(r[4]),
         "toast_bytes": int(r[5]), "row_estimate": int(r[6])}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)

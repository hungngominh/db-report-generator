"""P0.2 — foreign keys lacking a supporting leading-prefix index."""
from scripts.collectors import base

_SQL = """
SELECT ns.nspname AS schema,
       rel.relname AS tbl,
       con.conname AS constraint_name,
       (SELECT array_agg(a.attname ORDER BY x.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS x(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = x.attnum
       ) AS cols,
       format('CREATE INDEX ON %I.%I (%s);', ns.nspname, rel.relname,
          (SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY x.ord)
             FROM unnest(con.conkey) WITH ORDINALITY AS x(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = x.attnum)
       ) AS suggested_ddl
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE con.contype = 'f'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = con.conrelid
      AND i.indisvalid
      AND i.indpred IS NULL
      AND i.indexprs IS NULL
      AND i.indnkeyatts >= array_length(con.conkey, 1)
      AND (string_to_array(i.indkey::text, ' ')::int[])[1:array_length(con.conkey, 1)]
          = con.conkey::int[]
  )
ORDER BY schema, tbl, constraint_name
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "constraint": r[2],
         "columns": list(r[3]), "suggested_ddl": r[4]}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)

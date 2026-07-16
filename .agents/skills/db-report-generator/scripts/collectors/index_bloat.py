"""P0.1 — table/index bloat via pgstattuple (skip cleanly if extension absent)."""
from scripts.collectors import base

# User tables only; run pgstattuple_approx per table. LATERAL keeps it one query.
_SQL = """
SELECT ns.nspname AS schema, rel.relname AS tbl,
       st.table_len, st.dead_tuple_percent, st.approx_free_percent
FROM pg_class rel
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
CROSS JOIN LATERAL pgstattuple_approx(rel.oid) AS st
WHERE rel.relkind = 'r'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY st.dead_tuple_percent DESC
"""


def collect(conn, caps):
    if "pgstattuple" not in (caps.get("extensions") or {}):
        return base.skipped(
            "table",
            "index_bloat requires the pgstattuple extension (not installed)")
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()
    metrics = [
        {"schema": r[0], "table": r[1], "table_len": int(r[2]),
         "dead_tuple_percent": round(float(r[3]), 2),
         "approx_free_percent": round(float(r[4]), 2)}
        for r in rows
    ]
    return base.diagnostic("table", "ok", metrics)

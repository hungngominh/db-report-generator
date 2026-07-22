"""Sequential-scan ratio on tables large enough for it to matter.

n_live_tup > 10000 is the same floor pattern 2's own KB text uses as its
lowest tier (P1: >50% seq, >10K rows) -- below that, Postgres legitimately
prefers a seq scan over an index scan, so smaller tables are excluded at
the source rather than surfaced as noise.
"""
from scripts.collectors import base
from scripts.lib import index_catalog, sql_classify

_SQL = """
SELECT schemaname, relname, seq_scan, idx_scan, n_live_tup
FROM pg_stat_user_tables
WHERE n_live_tup > 10000 AND (seq_scan + idx_scan) > 0
ORDER BY seq_scan DESC
"""


def seq_scan_pct(seq_scan, idx_scan):
    total = seq_scan + idx_scan
    if total <= 0:
        return None
    return round(seq_scan / total * 100, 2)


def _group_by_table(conn, rows, *, count_key):
    """Groups pg_stat_statements rows -- sampling-window deltas OR cumulative
    snapshot rows -- by every (schema, table) they reference, so a flagged
    table's evidence can show the real WHERE-clause queries touching it. A
    JOIN row is attached under every table it resolves to (this cross-
    reference has no need to reject multi-table queries the way
    index_advisor.py does, since it isn't guessing a column suggestion).
    Each table's matches are sorted by row[count_key] descending --
    window_calls for deltas, calls for cumulative rows."""
    by_table = {}
    for row in rows:
        stmt = sql_classify.parse_statement(row.get("query"))
        if stmt is None:
            continue
        relations = sql_classify.referenced_relations(stmt)
        if not relations:
            continue
        for table_key in set(index_catalog.resolve_relations(conn, relations)):
            by_table.setdefault(table_key, []).append(row)
    for matches in by_table.values():
        matches.sort(key=lambda r: r.get(count_key) or 0, reverse=True)
    return by_table


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SQL)
        rows = cur.fetchall()

    related_by_table = {}
    if rows:
        sampling = caps.get("sampling")
        if sampling and not sampling.get("reset_detected"):
            related_by_table = _group_by_table(
                conn, sampling.get("deltas") or [], count_key="window_calls")

    metrics = []
    for r in rows:
        schema, table = r[0], r[1]
        related = related_by_table.get((schema, table), [])
        metrics.append({
            "schema": schema, "table": table, "seq_scan": int(r[2]), "idx_scan": int(r[3]),
            "n_live_tup": int(r[4]), "seq_scan_pct": seq_scan_pct(int(r[2]), int(r[3])),
            "related_queries": [
                {"queryid": d.get("queryid"), "query": d.get("query"),
                 "window_calls": d.get("window_calls"),
                 "window_total_exec_time_ms": d.get("window_total_exec_time_ms")}
                for d in related
            ],
        })
    return base.diagnostic("table", "ok", metrics)

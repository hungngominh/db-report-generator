"""P4.2 -- column-level index advisor. For each of the top-N slow queries
(already ranked by query_stats.py, descending window_total_exec_time_ms),
suggests a composite index over its equality-predicate columns when no
existing index already covers them. Only resolves single-table queries --
a query referencing more than one distinct (schema, table) pair is skipped
rather than guessed at."""
from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify


def _suggest(schema, table, columns):
    quoted_cols = ", ".join(columns)
    ddl = (f"-- needs-review: CREATE INDEX ON {schema}.{table} ({quoted_cols});"
           f" verify column order and check for an existing partial/covering index first")
    return {"schema": schema, "table": table, "suggested_columns": columns, "suggested_ddl": ddl}


def run(conn, query_stats_diag, *, top_n: int) -> dict:
    if query_stats_diag is None or query_stats_diag.get("status") not in ("ok", "partial"):
        return base.skipped("table", "query_stats diagnostic unavailable")

    rows = query_stats_diag.get("metrics", [])[:top_n]
    quality = dict(query_stats_diag.get("quality") or base.STRUCTURAL_QUALITY)

    seen = set()
    metrics = []
    for row in rows:
        sql = row.get("query")
        if not sql:
            continue
        stmt = sql_classify.parse_statement(sql)
        if stmt is None:
            continue

        relations = sql_classify.referenced_relations(stmt)
        distinct_tables = {(schema or "public", table) for schema, table in relations}
        if len(distinct_tables) != 1:
            continue
        (schema, table) = next(iter(distinct_tables))

        columns = sorted({path[-1] for path in index_predicate.equality_columns_from_statement(stmt)})
        if not columns:
            continue

        key = (schema, table, tuple(columns))
        if key in seen:
            continue
        seen.add(key)

        existing = index_catalog.existing_indexed_columns(conn, schema, table)
        if index_catalog.is_covered(existing, columns):
            continue

        suggestion = _suggest(schema, table, columns)
        suggestion["queryid"] = row.get("queryid")
        metrics.append(suggestion)

    return base.diagnostic("table", "ok", metrics, quality=quality)

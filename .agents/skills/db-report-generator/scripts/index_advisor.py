"""P4.2 -- column-level index advisor. For each of the top-N slow queries
(already ranked by query_stats.py, descending window_total_exec_time_ms),
suggests a composite index over its equality-predicate columns when no
existing index already covers them. Only resolves single-table queries --
a query referencing more than one distinct (schema, table) pair is skipped
rather than guessed at. Each referenced relation is resolved to its
canonical (schema, table) via index_catalog.resolve_relations() (backed by
to_regclass() against the live connection) so unqualified names follow the
connection's actual search_path instead of being guessed at."""
from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify


def _suggest(schema, table, columns):
    quoted_cols = ", ".join(columns)
    ddl = (f"-- needs-review: CREATE INDEX ON {schema}.{table} ({quoted_cols});"
           f" verify column order and check for an existing partial/covering index first")
    return {"schema": schema, "table": table, "suggested_columns": columns, "suggested_ddl": ddl}


def _resolve_single_table(conn, relations):
    """Resolves every (schema, table) reference in `relations` via
    index_catalog.resolve_relations(), and returns that pair iff EVERY
    reference resolved to a real relation AND they all collapse to exactly
    one distinct table (a self-join like `orders o1 JOIN orders o2` is
    fine; a genuine multi-table query is not). Returns None otherwise --
    callers must skip the row rather than guess a schema. See
    index_catalog.resolve_relations's docstring and
    test_index_advisor.py's search_path regression tests for why an
    unqualified name is never guessed at (e.g. hardcoded to "public")."""
    if not relations:
        return None
    resolved = index_catalog.resolve_relations(conn, relations)
    if len(resolved) != len(relations):
        return None  # at least one reference didn't resolve to a real relation
    distinct_tables = set(resolved)
    if len(distinct_tables) != 1:
        return None
    return next(iter(distinct_tables))


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
        resolved = _resolve_single_table(conn, relations)
        if resolved is None:
            continue
        (schema, table) = resolved

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

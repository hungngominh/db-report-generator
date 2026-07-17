"""P4.2 -- column-level index advisor. For each of the top-N slow queries
(already ranked by query_stats.py, descending window_total_exec_time_ms),
suggests a composite index over its equality-predicate columns when no
existing index already covers them. Only resolves single-table queries --
a query referencing more than one distinct (schema, table) pair is skipped
rather than guessed at. Each referenced relation is resolved to its
canonical (schema, table) via to_regclass() against the live connection
(see _RESOLVE_RELATIONS_SQL below) so unqualified names follow the
connection's actual search_path instead of being guessed at."""
from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify

# Resolves each referenced relation the same way the planner itself would --
# via to_regclass() against THIS connection's live search_path -- rather
# than guessing a schema for unqualified names. An earlier version of this
# module built the (schema, table) key directly from
# sql_classify.referenced_relations(), falling back to a hardcoded "public"
# schema whenever a RangeVar had no explicit schemaname. That silently
# misattributes the table whenever the connection's search_path resolves an
# unqualified name to some other schema (e.g. a multi-tenant
# search_path = tenant1, public): it would suggest CREATE INDEX ON
# public.orders (...) for a table that may not even exist in public, while
# missing that the real table (tenant1.orders) already has a covering
# index. A reference that doesn't resolve to any real relation at all
# (typo, dropped table, ...) is dropped from the result set entirely --
# "can't confidently resolve this query" is treated as a skip, never a
# guess. See explain.py's _FOREIGN_TABLE_SQL for the same fix applied to
# the foreign-table safety check, and test_index_advisor.py's search_path
# regression test for a live reproduction of the bug this closes.
_RESOLVE_RELATIONS_SQL = """
SELECT ref.ident, n.nspname, c.relname
FROM unnest(%s::text[]) AS ref(ident)
JOIN pg_class c ON c.oid = to_regclass(ref.ident)::oid
JOIN pg_namespace n ON n.oid = c.relnamespace
"""


def _suggest(schema, table, columns):
    quoted_cols = ", ".join(columns)
    ddl = (f"-- needs-review: CREATE INDEX ON {schema}.{table} ({quoted_cols});"
           f" verify column order and check for an existing partial/covering index first")
    return {"schema": schema, "table": table, "suggested_columns": columns, "suggested_ddl": ddl}


def _resolve_single_table(conn, relations):
    """Resolves every (schema, table) reference in `relations` to its
    canonical (nspname, relname) via to_regclass() on `conn`, and returns
    that pair iff EVERY reference resolved to a real relation AND they all
    collapse to exactly one distinct table (a self-join like
    `orders o1 JOIN orders o2` is fine; a genuine multi-table query is
    not). Returns None otherwise -- callers must skip the row rather than
    guess a schema."""
    if not relations:
        return None
    idents = [index_catalog.qualified_ident(conn, schema, table) for schema, table in relations]
    with conn.cursor() as cur:
        cur.execute(_RESOLVE_RELATIONS_SQL, (idents,))
        resolved_rows = cur.fetchall()
    if len(resolved_rows) != len(idents):
        return None  # at least one reference didn't resolve to a real relation
    distinct_tables = {(nspname, relname) for _, nspname, relname in resolved_rows}
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

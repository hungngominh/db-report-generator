"""P4.1 -- EXPLAIN plan-only by default (spec S0.A3/S10 P4.1).

Reads the top-N slow queries already ranked by
scripts/collectors/query_stats.py (sorted by window_total_exec_time_ms
descending, the sampler's own order), classifies each via
scripts.lib.sql_classify (a real PG parser -- never a regex safety gate),
and captures an EXPLAIN plan. ANALYZE only runs when explicitly opted in
(ExplainMode=analyze) AND the statement is within the first
ExplainAnalyzeTopN rows AND sql_classify.is_analyze_safe() confirms it.

A read-only transaction + ROLLBACK is explicitly NOT relied on for ANALYZE
safety -- ANALYZE still executes the statement (e.g. nextval() is permitted
even inside a READ ONLY transaction). Safety instead comes from the
parser-based allowlist plus the tightened statement_timeout/lock_timeout
this module sets before every EXPLAIN and always restores afterward (even
on failure).
"""
from psycopg2.extensions import quote_ident

from scripts.collectors import base
from scripts.lib import db, sql_classify

_GENERIC_PLAN_MIN_VERSION = 160000

# Resolves each referenced relation the same way the EXPLAIN itself will --
# via to_regclass() against THIS connection's live search_path -- rather
# than guessing a schema for unqualified names. An earlier version of this
# check joined (schema, relname) tuples against pg_namespace/pg_class with
# an unqualified name hardcoded to "public"; that is wrong whenever the
# connection's search_path resolves an unqualified name to some other
# schema, which would silently let ANALYZE run against a foreign table
# (see test_explain.py's search_path regression test for a live
# reproduction of the bypass this closes).
_FOREIGN_TABLE_SQL = """
SELECT 1
FROM unnest(%s::text[]) AS ref(ident)
JOIN pg_foreign_table ft ON ft.ftrelid = to_regclass(ref.ident)::oid
LIMIT 1
"""


def _set_timeouts(conn, statement_timeout_ms, lock_timeout_ms):
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (int(statement_timeout_ms),))
        cur.execute("SET lock_timeout = %s", (int(lock_timeout_ms),))


def _restore_default_timeouts(conn):
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (db.DEFAULT_STATEMENT_TIMEOUT_MS,))
        cur.execute("SET lock_timeout = %s", (db.DEFAULT_LOCK_TIMEOUT_MS,))


def _current_context(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_setting('search_path'), current_database()")
        role, search_path, database = cur.fetchone()
    return {"role": role, "search_path": search_path, "database": database}


def _qualified_ident(conn, schema, table):
    ident = quote_ident(table, conn)
    if schema:
        ident = f"{quote_ident(schema, conn)}.{ident}"
    return ident


def _references_foreign_table(conn, stmt):
    relations = sql_classify.referenced_relations(stmt)
    if not relations:
        return False
    idents = [_qualified_ident(conn, schema, table) for schema, table in relations]
    with conn.cursor() as cur:
        cur.execute(_FOREIGN_TABLE_SQL, (idents,))
        return cur.fetchone() is not None


def _run_explain(conn, sql, *, analyze):
    verb = "EXPLAIN (ANALYZE, FORMAT JSON)" if analyze else "EXPLAIN (FORMAT JSON)"
    with conn.cursor() as cur:
        cur.execute(f"{verb} {sql}")
        return cur.fetchone()[0][0]


def _run_generic_plan(conn, sql):
    # PG16+ direct syntax -- no PREPARE/EXECUTE/DEALLOCATE needed.
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (GENERIC_PLAN, FORMAT JSON) {sql}")
        return cur.fetchone()[0][0]


def _explain_row(conn, row, *, index, mode, analyze_top_n, server_version_num):
    sql = row.get("query")
    out = {"queryid": row.get("queryid"), "mode": "plan",
           "plan": None, "explain_unavailable": None, "analyze_skipped_reason": None}
    if not sql:
        out["explain_unavailable"] = "empty_query_text"
        return out

    stmt = sql_classify.parse_statement(sql)
    if stmt is None:
        out["explain_unavailable"] = "unparseable"
        return out

    has_params = sql_classify.has_parameters(stmt)
    if has_params and server_version_num < _GENERIC_PLAN_MIN_VERSION:
        out["explain_unavailable"] = "parameterized_pre_pg16"
        return out

    try:
        if has_params:
            out["plan"] = _run_generic_plan(conn, sql)  # GENERIC_PLAN never ANALYZEs (spec S0.A3/B1)
            return out

        wants_analyze = mode == "analyze" and index < analyze_top_n
        if wants_analyze:
            safe, reason = sql_classify.is_analyze_safe(stmt)
            if safe and _references_foreign_table(conn, stmt):
                safe, reason = False, "foreign_table"
            if not safe:
                out["analyze_skipped_reason"] = reason
                wants_analyze = False
        out["plan"] = _run_explain(conn, sql, analyze=wants_analyze)
        out["mode"] = "analyze" if wants_analyze else "plan"
    except Exception as exc:  # noqa: BLE001 - one query's EXPLAIN failing must not abort the batch
        out["explain_unavailable"] = f"explain_failed:{type(exc).__name__}"
    return out


def run(conn, caps, query_stats_diag, *, mode: str, top_n: int, analyze_top_n: int,
        statement_timeout_ms: int, lock_timeout_ms: int) -> dict:
    if mode == "off":
        return base.skipped("query", "ExplainMode=off")
    if query_stats_diag is None or query_stats_diag.get("status") not in ("ok", "partial"):
        return base.skipped("query", "query_stats diagnostic unavailable")

    rows = query_stats_diag.get("metrics", [])[:top_n]
    if not rows:
        return base.diagnostic("query", "ok", [])

    server_version_num = caps.get("server_version_num", 0)
    quality = dict(query_stats_diag.get("quality") or base.STRUCTURAL_QUALITY)
    context = _current_context(conn)

    _set_timeouts(conn, statement_timeout_ms, lock_timeout_ms)
    try:
        metrics = [
            {**_explain_row(conn, row, index=i, mode=mode, analyze_top_n=analyze_top_n,
                             server_version_num=server_version_num), **context}
            for i, row in enumerate(rows)
        ]
    finally:
        _restore_default_timeouts(conn)

    return base.diagnostic("query", "ok", metrics, quality=quality)

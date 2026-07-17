"""P4.3 -- RLS policy predicate scanning: unwrapped auth.uid()/current_setting()
re-evaluation-per-row trap (the well-known Postgres/Supabase RLS perf trap),
plus missing-index detection on policy equality predicates. Always runs
(no RLS/Supabase capability gate) -- an empty pg_policies result is a
healthy `ok` state, same pattern as P2's replication.py and blocking.py.
"""
from pglast import ast, visitors

from scripts.collectors import base
from scripts.lib import index_catalog, index_predicate, sql_classify

_POLICIES_SQL = """
SELECT schemaname, tablename, policyname, cmd, qual, with_check
FROM pg_policies
ORDER BY schemaname, tablename, policyname
"""

_FLAGGED_AUTH_FUNCS = {"uid", "role", "jwt"}
_FLAGGED_SETTING_FUNC = "current_setting"


class _UnwrappedCallFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.calls = []

    def visit_FuncCall(self, ancestors, node):
        if ast.SubLink in ancestors:
            return
        names = [n.sval for n in node.funcname or ()]
        name = ".".join(names)
        if len(names) == 2 and names[0] == "auth" and names[1] in _FLAGGED_AUTH_FUNCS:
            self.calls.append(name)
        elif len(names) == 1 and names[0] == _FLAGGED_SETTING_FUNC:
            self.calls.append(name)


def _unwrapped_calls(stmt):
    finder = _UnwrappedCallFinder()
    finder(stmt)
    return finder.calls


def _fetch_policies(conn):
    """Runs _POLICIES_SQL with the connection's search_path forced to
    pg_catalog for the query's duration, then restores it -- otherwise the
    unwrapped-call detection below can be silently defeated.

    pg_policies.qual/with_check are built from pg_get_expr(), which
    schema-qualifies a function name in its output only when that function
    is NOT already resolvable unqualified via the CURRENT session's
    search_path (generate_function_name()/FunctionIsVisible() in
    ruleutils.c -- this is session-search-path-dependent deparsing, a
    distinct mechanism from the RangeVar/to_regclass search-path bug fixed
    in index_advisor.py and explain.py, but the same underlying hazard:
    trusting catalog-derived TEXT as if it were schema-stable). Verified
    live against Postgres 16: with search_path = 'auth, public', a policy
    created as `USING (owner = auth.uid())` comes back from pg_policies as
    `qual = '(owner = uid())'` -- the schema prefix silently dropped --
    which would defeat _UnwrappedCallFinder's `auth.<fn>` two-part name
    match entirely. Forcing search_path to pg_catalog (always implicitly
    searched, itself never needs qualification) guarantees every
    non-builtin function reference comes back fully schema-qualified,
    independent of whatever search_path the connecting role has
    configured. See test_rls_policies.py's
    test_collect_flags_unwrapped_auth_uid_even_when_search_path_hides_schema
    for a live reproduction.

    Restoring splices current_setting()'s echoed text directly into `SET
    search_path TO <text>` rather than binding it as a %s parameter --
    verified live that binding it as a string parameter is wrong: search_path
    is a GUC_LIST_INPUT variable, and the comma-list is only split when the
    value appears as a bare identifier list in the SQL text itself. A
    single quoted-string parameter is instead stored as ONE literal schema
    name (confirmed live: it left search_path set to a single bogus schema
    literally named "auth, public"). The spliced text is never
    attacker-controlled -- it is the server's own canonical GUC state
    reflected back via current_setting(), which is guaranteed to already
    be valid `SET ... TO` syntax (including the special "$user" token and
    quoted names containing commas/spaces)."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('search_path')")
        original_search_path = cur.fetchone()[0]
        cur.execute("SET search_path = pg_catalog")
        try:
            cur.execute(_POLICIES_SQL)
            return cur.fetchall()
        finally:
            cur.execute("SET search_path TO " + original_search_path)


def _predicate_rows(conn, schema, table, policy, clause_name, expr_text):
    if not expr_text:
        return []
    stmt = sql_classify.parse_statement(f"SELECT {expr_text}")
    if stmt is None:
        return []

    rows = []
    for fn in _unwrapped_calls(stmt):
        rows.append({"schema": schema, "table": table, "policy": policy, "clause": clause_name,
                     "issue": "unwrapped_reeval_call", "function": fn, "column": None})

    columns = [path[-1] for path in index_predicate.equality_columns_from_statement(stmt)]
    if columns:
        existing = index_catalog.existing_indexed_columns(conn, schema, table)
        if not index_catalog.is_covered(existing, columns):
            rows.append({"schema": schema, "table": table, "policy": policy, "clause": clause_name,
                         "issue": "missing_supporting_index", "function": None,
                         "column": ",".join(sorted(set(columns)))})
    return rows


def collect(conn, caps):
    policies = _fetch_policies(conn)

    metrics = []
    for schema, table, policy, _cmd, qual, with_check in policies:
        metrics.extend(_predicate_rows(conn, schema, table, policy, "qual", qual))
        metrics.extend(_predicate_rows(conn, schema, table, policy, "with_check", with_check))

    return base.diagnostic("table", "ok", metrics)

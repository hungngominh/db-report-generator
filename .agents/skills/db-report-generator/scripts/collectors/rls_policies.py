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

    Restoring uses `SELECT set_config('search_path', %s, false)` with
    original_search_path bound as an ordinary %s parameter -- confirmed
    live (see test_rls_policies.py) that this is NOT the same hazard as
    binding a %s parameter into `SET search_path TO %s` (the statement
    grammar): that form treats the bound value as a single quoted string
    literal for the value slot and does NOT split it on commas, so a
    readback of "auth, public" round-trips into one bogus schema literally
    named "auth, public" (confirmed live: `SHOW search_path` afterward
    reads `"auth, public"`, and unqualified names stop resolving).
    set_config() is a regular function call taking a text argument, and
    Postgres re-parses that argument through the normal GUC_LIST_INPUT
    list-splitting logic for search_path regardless of how the text
    argument was supplied -- confirmed live that
    `set_config('search_path', 'auth, public', false)` bound as a %s
    parameter leaves `SHOW search_path` reading `auth, public` (two
    schemas) and both schemas resolve unqualified names correctly via
    to_regclass(). set_config() was also confirmed live to tolerate an
    empty string (`set_config('search_path', '', false)`) without raising,
    leaving the connection usable afterward -- unlike the old splice
    approach, which would have built the syntactically invalid `SET
    search_path TO ` and raised inside this `finally` block, permanently
    wedging the connection's search_path at `pg_catalog` for every
    collector that runs afterward on the same shared connection. Using
    set_config() as a bound parameter is therefore both injection-safe
    (no string splicing at all) and correct for the empty/multi-schema
    cases the old splice could not handle. See
    test_rls_policies.py::test_collect_leaves_connection_usable_after_empty_search_path
    for a live reproduction."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('search_path')")
        original_search_path = cur.fetchone()[0]
        cur.execute("SET search_path = pg_catalog")
        try:
            cur.execute(_POLICIES_SQL)
            return cur.fetchall()
        finally:
            cur.execute("SELECT set_config('search_path', %s, false)", (original_search_path,))


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

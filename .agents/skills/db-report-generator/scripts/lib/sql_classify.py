"""Real-PostgreSQL-grammar SQL classification via pglast (wraps libpg_query)
-- never a regex safety gate (spec S0.A3, project rule N2 exemption: parsing
SQL text for safety classification is explicitly allowed)."""
from pglast import ast, parse_sql, visitors
from pglast.enums import A_Expr_Kind  # noqa: F401 - re-exported for index_predicate

_UNSAFE_FUNCTIONS = {
    "nextval", "setval", "currval", "lastval",
    "pg_advisory_lock", "pg_advisory_lock_shared",
    "pg_advisory_xact_lock", "pg_advisory_xact_lock_shared",
    "pg_try_advisory_lock", "pg_try_advisory_lock_shared",
    "pg_try_advisory_xact_lock", "pg_try_advisory_xact_lock_shared",
    "pg_sleep", "txid_current", "random",
}


def parse_statement(sql: str):
    """Returns the parsed AST root node for exactly one SQL statement, or
    None if `sql` fails to parse or contains anything other than exactly
    one statement (a defensive close against multi-statement injection via
    ';' -- explain.py embeds this text directly into an EXPLAIN command,
    which cannot be parameterized)."""
    if not sql:
        return None
    try:
        parsed = parse_sql(sql)
    except Exception:  # noqa: BLE001 - any parse failure means "can't classify"
        return None
    if len(parsed) != 1:
        return None
    return parsed[0].stmt


def has_parameters(stmt) -> bool:
    if stmt is None:
        return False
    finder = _ParamFinder()
    finder(stmt)
    return finder.found


class _ParamFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.found = False

    def visit_ParamRef(self, ancestors, node):
        self.found = True


def referenced_relations(stmt) -> list:
    if stmt is None:
        return []
    finder = _RelationFinder()
    finder(stmt)
    return finder.relations


class _RelationFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.relations = []

    def visit_RangeVar(self, ancestors, node):
        self.relations.append((node.schemaname, node.relname))


class _UnsafeFunctionFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.hit = None

    def visit_FuncCall(self, ancestors, node):
        if self.hit:
            return
        names = [n.sval for n in node.funcname]
        name = names[-1]
        if name in _UNSAFE_FUNCTIONS:
            self.hit = name


def is_analyze_safe(stmt) -> tuple:
    """(True, None) when ANALYZE-mode EXPLAIN is safe to run against `stmt`;
    otherwise (False, reason). A read-only transaction is NOT relied on
    here -- ANALYZE still executes the statement (e.g. nextval() runs even
    inside READ ONLY), so safety comes entirely from this parser-based
    allowlist. Foreign-table references are checked separately in
    explain.py via a catalog query (pg_foreign_table), not here."""
    if stmt is None:
        return False, "unparseable"
    if not isinstance(stmt, ast.SelectStmt):
        return False, "not_a_select"
    if stmt.lockingClause:
        return False, "locking_clause"
    finder = _UnsafeFunctionFinder()
    finder(stmt)
    if finder.hit:
        return False, f"unsafe_function:{finder.hit}"
    return True, None

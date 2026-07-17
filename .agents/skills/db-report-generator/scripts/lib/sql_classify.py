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
    "pg_advisory_unlock", "pg_advisory_unlock_shared", "pg_advisory_unlock_all",
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
        names = [n.sval for n in node.funcname or ()]
        if not names:
            return
        name = names[-1]
        if name in _UNSAFE_FUNCTIONS:
            self.hit = name


class _WriteStmtFinder(visitors.Visitor):
    """Finds a DML write statement anywhere in the tree -- including nested
    inside a writable CTE's ctequery (e.g. `WITH d AS (DELETE ...) SELECT
    ...`), which parses as a top-level SelectStmt and would otherwise evade
    an isinstance check on the outer statement alone."""

    def __init__(self):
        super().__init__()
        self.hit = None

    def visit_DeleteStmt(self, ancestors, node):
        if self.hit is None:
            self.hit = "DeleteStmt"

    def visit_UpdateStmt(self, ancestors, node):
        if self.hit is None:
            self.hit = "UpdateStmt"

    def visit_InsertStmt(self, ancestors, node):
        if self.hit is None:
            self.hit = "InsertStmt"

    def visit_MergeStmt(self, ancestors, node):
        if self.hit is None:
            self.hit = "MergeStmt"


class _LockingClauseFinder(visitors.Visitor):
    """Finds a non-empty lockingClause on ANY SelectStmt in the tree, not
    just the top-level statement -- PostgreSQL allows a locking clause
    (e.g. FOR UPDATE) on a non-recursive CTE's own SelectStmt, which is
    nested under withClause.ctes[...].ctequery rather than the outer
    statement."""

    def __init__(self):
        super().__init__()
        self.hit = False

    def visit_SelectStmt(self, ancestors, node):
        if node.lockingClause:
            self.hit = True


def is_analyze_safe(stmt) -> tuple:
    """(True, None) when ANALYZE-mode EXPLAIN is safe to run against `stmt`;
    otherwise (False, reason). A read-only transaction is NOT relied on
    here -- ANALYZE still executes the statement (e.g. nextval() runs even
    inside READ ONLY), so safety comes entirely from this parser-based
    allowlist. Foreign-table references are checked separately in
    explain.py via a catalog query (pg_foreign_table), not here.

    Both the write-statement and locking-clause checks walk the ENTIRE
    tree (not just the top-level node) because PostgreSQL supports
    writable CTEs (`WITH d AS (DELETE FROM t ...) SELECT ...`), which
    parse as a top-level SelectStmt with the DeleteStmt/UpdateStmt/
    InsertStmt/MergeStmt nested inside withClause.ctes[...].ctequery, and
    likewise supports a locking clause on a non-recursive CTE's own
    SelectStmt.

    The legacy `SELECT ... INTO new_table FROM ...` syntax also parses as
    a plain SelectStmt (distinct from CREATE TABLE AS, which parses as a
    separate CreateTableAsStmt node already caught by not_a_select) but
    populates stmt.intoClause and, under ANALYZE, actually creates and
    populates the target table -- a real side effect -- so it must be
    rejected explicitly here rather than falling through as a read."""
    if stmt is None:
        return False, "unparseable"
    if not isinstance(stmt, ast.SelectStmt):
        return False, "not_a_select"
    if stmt.intoClause:
        return False, "select_into"
    write_finder = _WriteStmtFinder()
    write_finder(stmt)
    if write_finder.hit:
        return False, f"write_statement:{write_finder.hit}"
    locking_finder = _LockingClauseFinder()
    locking_finder(stmt)
    if locking_finder.hit:
        return False, "locking_clause"
    finder = _UnsafeFunctionFinder()
    finder(stmt)
    if finder.hit:
        return False, f"unsafe_function:{finder.hit}"
    return True, None

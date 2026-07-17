"""Equality-predicate extraction for the column-level index advisor (P4.2)
and RLS policy-predicate scanning (P4.3) -- both need the same WHERE/ON
equality-column walk, so the AST-walk core is split from parsing so
rls_policies.py can reuse it against an already-parsed statement/expression
without re-parsing (parse_statement rejects a bare boolean expression, which
is exactly what a policy's qual/with_check text is)."""
from pglast import ast, visitors
from pglast.enums import A_Expr_Kind

from scripts.lib import sql_classify


class _EqualityColumnFinder(visitors.Visitor):
    def __init__(self):
        super().__init__()
        self.columns = []

    def visit_A_Expr(self, ancestors, node):
        if node.kind != A_Expr_Kind.AEXPR_OP:
            return
        names = [n.sval for n in (node.name or ())]
        if names != ["="]:
            return
        for side in (node.lexpr, node.rexpr):
            path = _column_ref_path(side)
            if path is not None:
                self.columns.append(path)


def _column_ref_path(node):
    if not isinstance(node, ast.ColumnRef):
        return None
    fields = [f.sval for f in node.fields if isinstance(f, ast.String)]
    return tuple(fields) if fields else None


def equality_columns_from_statement(stmt) -> list:
    """Walks `stmt` (or any parsed AST node/expression) for `col = ...`
    equality predicates and returns each match as a tuple path, e.g.
    ("t", "user_id") for a qualified reference or ("status",) for a bare
    column name. Returns [] for stmt=None (unparseable input).

    This is a tree-wide walk, not a top-level-only check: visit_A_Expr is
    invoked by pglast.visitors.Visitor's dispatch for every A_Expr node
    anywhere in the tree, so equality predicates nested inside a FROM
    subquery, a CTE, an OR branch, or a JOIN ... ON clause are all found
    the same way a top-level WHERE clause is."""
    if stmt is None:
        return []
    finder = _EqualityColumnFinder()
    finder(stmt)
    return finder.columns


def extract_equality_columns(sql: str) -> list:
    stmt = sql_classify.parse_statement(sql)
    return equality_columns_from_statement(stmt)

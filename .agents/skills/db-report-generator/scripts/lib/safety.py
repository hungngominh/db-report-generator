"""Read-only SQL gate (conservative; upgraded to a real parser in P4).

Returns True ONLY for a single, pure-read statement. Errs toward False: a
legitimate read misclassified just won't be EXPLAINed; it is never True for
anything that could modify data/schema/session state or execute a statement
(incl. EXPLAIN ANALYZE, writable CTEs, and multi-statement strings).
"""
import re

READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "TABLE", "VALUES")

_LEADING_NOISE = re.compile(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s)+", re.DOTALL)
# Data/schema/state-modifying verbs. Scanned ONLY for WITH/EXPLAIN statements,
# where a writable CTE or an explained DML can hide. A plain SELECT/SHOW/TABLE/
# VALUES cannot embed these, so it is not scanned (avoids false-negatives on
# string literals / identifiers like a column named "update").
_MODIFY = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"COPY|CALL|DO|VACUUM|ANALYZE|REINDEX|CLUSTER|REFRESH|LOCK|COMMENT|"
    r"NOTIFY|IMPORT|SECURITY)\b",
    re.IGNORECASE,
)


def _strip(sql: str) -> str:
    return _LEADING_NOISE.sub("", sql).strip()


def is_readonly_sql(sql: str) -> bool:
    s = _strip(sql)
    if not s:
        return False
    # Reject multiple statements ("SELECT 1; DROP TABLE x"); allow one trailing ';'.
    if ";" in s.rstrip().rstrip(";"):
        return False
    head = s.split(None, 1)[0].upper()
    if head not in READONLY_PREFIXES:
        return False
    # WITH may carry a writable CTE; EXPLAIN may explain a DML or use ANALYZE
    # (which EXECUTES the statement). Scan those for modifying verbs.
    if head in ("WITH", "EXPLAIN") and _MODIFY.search(s):
        return False
    return True

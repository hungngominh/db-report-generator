"""Best-effort read-only SQL pre-filter (NOT a security boundary).

Returns True only for a single statement that *looks* purely read-only by
prefix + keyword inspection. This is an ADVISORY filter, not a guarantee: a
keyword blocklist cannot catch every side effect (arbitrary volatile or
administrative function calls in a SELECT list cannot be enumerated). The real
safety boundary is a read-only transaction / read-only role enforced by the
database (wired in P0+) plus the parser-based allowlist (P4). Callers MUST
combine this with those — never treat True as proof of safety. Errs toward
False (over-rejection is safe).
"""
import re

READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "TABLE", "VALUES")

_LEADING_NOISE = re.compile(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s)+", re.DOTALL)
# Modifying / executing verbs, plus INTO (SELECT..INTO = CREATE TABLE AS) and a
# non-exhaustive set of known side-effecting functions. Scanned across the WHOLE
# statement for EVERY accepted head. Not complete — see the module docstring.
_MODIFY = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"COPY|CALL|DO|VACUUM|ANALYZE|REINDEX|CLUSTER|REFRESH|LOCK|COMMENT|NOTIFY|"
    r"IMPORT|SECURITY|INTO|"
    r"set_config|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|"
    r"lo_export|lo_import|pg_read_file|pg_write_file|nextval|setval)\b",
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
    # Scan for modify/execute markers across EVERY accepted head (a plain SELECT
    # can still create a table via INTO or execute a side-effecting function).
    if _MODIFY.search(s):
        return False
    return True

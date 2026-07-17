"""Index-coverage lookups shared by index_advisor.py and rls_policies.py.

Reuses duplicate_index.py's proven i.indkey::text + Python split() idiom --
pg_index.indkey is an int2vector, not a genuine array type, so unnest()
does not apply to it directly (unlike pg_constraint.conkey, a real int[],
used by fk_missing_index.py).
"""
from psycopg2.extensions import quote_ident

_INDEXES_SQL = """
SELECT i.indrelid, i.indnkeyatts, i.indkey::text AS indkey
FROM pg_index i
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = %s AND t.relname = %s AND i.indisvalid
"""

_ATTNAMES_SQL = """
SELECT attnum, attname FROM pg_attribute WHERE attrelid = %s AND attnum = ANY(%s)
"""


def existing_indexed_columns(conn, schema: str, table: str) -> list:
    """Returns one tuple of leading key-column names per valid index on
    (schema, table) -- INCLUDE columns excluded via indnkeyatts (same
    truncation as duplicate_index.py's _key_desc), expression-index
    positions (attnum 0) represented as None so they never satisfy a
    coverage check against a real column name."""
    with conn.cursor() as cur:
        cur.execute(_INDEXES_SQL, (schema, table))
        index_rows = cur.fetchall()
        if not index_rows:
            return []

        table_oid = index_rows[0][0]
        all_attnums = set()
        parsed = []
        for indrelid, indnkeyatts, indkey in index_rows:
            attnums = [int(a) for a in indkey.split()[:indnkeyatts]]
            parsed.append(attnums)
            all_attnums.update(a for a in attnums if a != 0)

        cur.execute(_ATTNAMES_SQL, (table_oid, list(all_attnums)))
        names_by_attnum = dict(cur.fetchall())

    results = []
    for attnums in parsed:
        results.append(tuple(names_by_attnum.get(a) if a != 0 else None for a in attnums))
    return results


def qualified_ident(conn, schema, table):
    """Builds a properly-quoted, optionally schema-qualified identifier for
    (schema, table) via quote_ident() on `conn` -- shared by explain.py and
    index_advisor.py, which both need to feed catalog-derived table names
    back into SQL text safely."""
    ident = quote_ident(table, conn)
    if schema:
        ident = f"{quote_ident(schema, conn)}.{ident}"
    return ident


def is_covered(existing: list, columns: list) -> bool:
    """True if `columns` (any order) is a leading-prefix subset of some
    existing index's key columns."""
    wanted = set(columns)
    for index_columns in existing:
        prefix = index_columns[: len(wanted)]
        if None in prefix:
            continue
        if set(prefix) == wanted:
            return True
    return False

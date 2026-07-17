"""P4.4 -- schema hygiene checks: missing primary key, UUIDv4 used as the
primary key on a large table (random insertion order fragments the PK
b-tree; UUIDv7 does not have this problem and is not flagged), and
`timestamp without time zone` columns. Always runs; an empty result is a
healthy `ok` state, same pattern as P2's replication.py/blocking.py and
this phase's rls_policies.py.
"""
from psycopg2 import sql

from scripts.collectors import base

_LARGE_TABLE_ROW_THRESHOLD = 1_000_000
_UUID_SAMPLE_SIZE = 100
_UUID_V4_MAJORITY_RATIO = 0.5

_TABLES_SQL = """
SELECT n.nspname AS schema, c.relname AS table, c.reltuples::float8 AS row_estimate,
       EXISTS (
           SELECT 1 FROM pg_constraint con
           WHERE con.conrelid = c.oid AND con.contype = 'p'
       ) AS has_pk,
       c.oid AS table_oid
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY n.nspname, c.relname
"""

# Joined by table OID -- captured straight off this same pg_class row in
# _TABLES_SQL -- rather than by casting a hand-quoted, schema-qualified
# string to ::regclass. schema/table are catalog-derived (pg_namespace/
# pg_class), never user input, but a naive f'"{schema}"."{table}"' does not
# double an embedded double-quote the way real identifier quoting does, so
# a table legally (if unusually) named e.g. `ta"ble` would build a
# malformed regclass literal and either error out or resolve to the wrong
# relation. This module's own _sample_uuid_v4_ratio() below already avoids
# that by building its FROM-clause identifier via psycopg2.sql.Identifier;
# index_advisor.py's _qualified_ident() uses quote_ident() for the same
# reason. Binding the OID directly -- the same pattern
# scripts/lib/index_catalog.py already uses for its own per-table
# follow-up queries -- sidesteps identifier quoting entirely rather than
# introducing a second, inconsistent quoting mechanism in this file.
_PK_COLUMN_TYPE_SQL = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS type
FROM pg_constraint con
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
WHERE con.conrelid = %s AND con.contype = 'p'
ORDER BY a.attnum
"""

_TIMESTAMP_COLUMNS_SQL = """
SELECT a.attname
FROM pg_attribute a
WHERE a.attrelid = %s
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND format_type(a.atttypid, a.atttypmod) = 'timestamp without time zone'
ORDER BY a.attnum
"""


def _is_confirmed_large(row_estimate):
    return row_estimate is not None and row_estimate >= _LARGE_TABLE_ROW_THRESHOLD


def _sample_uuid_v4_ratio(conn, schema, table, column):
    # RFC 4122's canonical text form is 8-4-4-4-12 hex digits
    # ("xxxxxxxx-xxxx-Vxxx-Nxxx-xxxxxxxxxxxx"): 8 hex + '-' (pos 9) + 4 hex
    # (pos 10-13) + '-' (pos 14) puts the version nibble V at 1-indexed
    # position 15. Confirmed against this module's own test fixtures: the
    # v4 sample's 15th character is '4', the v7 sample's is '7'.
    query = sql.SQL(
        "SELECT substring({col}::text from 15 for 1) FROM {tbl} WHERE {col} IS NOT NULL LIMIT %s"
    ).format(col=sql.Identifier(column), tbl=sql.Identifier(schema, table))
    with conn.cursor() as cur:
        cur.execute(query, (_UUID_SAMPLE_SIZE,))
        rows = cur.fetchall()
    if not rows:
        return None
    v4_count = sum(1 for (version_char,) in rows if version_char == "4")
    return v4_count / len(rows)


def _pk_check(conn, schema, table, row_estimate, has_pk, table_oid):
    if not has_pk:
        return [{"schema": schema, "table": table, "issue": "missing_primary_key",
                 "column": None, "row_estimate": row_estimate}]
    if not _is_confirmed_large(row_estimate):
        return []

    with conn.cursor() as cur:
        cur.execute(_PK_COLUMN_TYPE_SQL, (table_oid,))
        pk_columns = cur.fetchall()

    rows = []
    for col, coltype in pk_columns:
        if coltype != "uuid":
            continue
        ratio = _sample_uuid_v4_ratio(conn, schema, table, col)
        if ratio is not None and ratio > _UUID_V4_MAJORITY_RATIO:
            rows.append({"schema": schema, "table": table, "issue": "oversized_uuid_pk",
                         "column": col, "row_estimate": row_estimate})
    return rows


def _timestamp_check(conn, schema, table, row_estimate, table_oid):
    with conn.cursor() as cur:
        cur.execute(_TIMESTAMP_COLUMNS_SQL, (table_oid,))
        cols = cur.fetchall()
    return [{"schema": schema, "table": table, "issue": "timestamp_without_timezone",
             "column": col, "row_estimate": row_estimate} for (col,) in cols]


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_TABLES_SQL)
        tables = cur.fetchall()

    metrics = []
    for schema, table, row_estimate, has_pk, table_oid in tables:
        metrics.extend(_pk_check(conn, schema, table, row_estimate, has_pk, table_oid))
        metrics.extend(_timestamp_check(conn, schema, table, row_estimate, table_oid))

    return base.diagnostic("table", "ok", metrics)

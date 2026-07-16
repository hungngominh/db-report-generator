"""Test helper: build a throwaway, uniquely-named schema for collector tests."""
from contextlib import contextmanager


@contextmanager
def make_schema(conn, name, ddl):
    """Create schema ``name``, run ``ddl`` (``{s}`` -> schema name), drop on exit.

    ``conn`` must be a read-write autocommit psycopg2 connection.
    """
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{name}"')
        cur.execute(ddl.format(s=f'"{name}"'))
    try:
        yield name
    finally:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')

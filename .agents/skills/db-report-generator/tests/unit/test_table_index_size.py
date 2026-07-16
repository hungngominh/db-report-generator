import psycopg2
import pytest

from scripts.collectors.table_index_size import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.t (id int PRIMARY KEY, a int, b int);
CREATE INDEX ON {s}.t (a);
CREATE INDEX ON {s}.t (b);
INSERT INTO {s}.t SELECT g, g, g FROM generate_series(1, 2000) g;
"""


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_index_bytes_equals_pg_indexes_size(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, "t_idxsize", DDL):
            diag = collect(conn, {})
            with conn.cursor() as cur:
                cur.execute("SELECT pg_indexes_size('\"t_idxsize\".t'::regclass)")
                expected = cur.fetchone()[0]
    finally:
        conn.close()
    row = [m for m in diag["metrics"] if m["schema"] == "t_idxsize" and m["table"] == "t"][0]
    assert row["index_bytes"] == expected
    assert set(row) == {"schema", "table", "total_bytes", "heap_bytes",
                        "index_bytes", "toast_bytes", "row_estimate"}
    # heap + index + toast never exceeds the reported total
    assert row["heap_bytes"] + row["index_bytes"] + row["toast_bytes"] <= row["total_bytes"]

import psycopg2
import pytest

from scripts.collectors.index_bloat import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.t (id int PRIMARY KEY, pad text);
INSERT INTO {s}.t SELECT g, repeat('x', 200) FROM generate_series(1, 5000) g;
DELETE FROM {s}.t WHERE id % 2 = 0;
"""


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_skips_cleanly_when_pgstattuple_absent(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {"extensions": {}})       # extension not present
    finally:
        conn.close()
    assert diag["status"] == "skipped"
    assert "pgstattuple" in (diag["reason"] or "")
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_reports_dead_percent_when_pgstattuple_present(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")
        with make_schema(conn, "t_bloat", DDL):
            caps = {"extensions": {"pgstattuple": {"present": True, "schema": "public"}}}
            diag = collect(conn, caps)
    finally:
        conn.close()
    assert diag["status"] == "ok"
    row = [m for m in diag["metrics"] if m["schema"] == "t_bloat" and m["table"] == "t"]
    assert row and row[0]["dead_tuple_percent"] > 20  # ~half deleted -> substantial

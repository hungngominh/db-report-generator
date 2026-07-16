import psycopg2
import pytest

from scripts.collectors.fk_missing_index import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}."Parent" (id int PRIMARY KEY);
CREATE TABLE {s}."OrderVehicle" (id int PRIMARY KEY,
    "ParentId" int REFERENCES {s}."Parent"(id));                 -- missing -> flag
CREATE TABLE {s}.covered (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.covered (parent_id, id);                     -- leading prefix -> ok
CREATE TABLE {s}.pa (a int, b int, PRIMARY KEY (a,b));
CREATE TABLE {s}.reversed (a int, b int,
    FOREIGN KEY (a,b) REFERENCES {s}.pa(a,b));
CREATE INDEX ON {s}.reversed (b, a);                             -- reversed -> flag
CREATE TABLE {s}.partial_fk (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.partial_fk (parent_id) WHERE parent_id IS NOT NULL;  -- partial -> flag
CREATE TABLE {s}.include_ok (id int PRIMARY KEY,
    parent_id int REFERENCES {s}."Parent"(id));
CREATE INDEX ON {s}.include_ok (parent_id) INCLUDE (id);         -- key prefix -> ok
"""


def _collect_schema(pg_dsn, schema):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, schema, DDL):
            diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()
    rows = [m for m in diag["metrics"] if m["schema"] == schema]
    return diag, {m["table"] for m in rows}, {m["table"]: m for m in rows}


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_flags_only_the_uncovered_fks(pg_dsn):
    diag, tables, by_table = _collect_schema(pg_dsn, "t_fk_missing")
    assert diag["status"] == "ok"
    assert tables == {"OrderVehicle", "reversed", "partial_fk"}
    assert "covered" not in tables and "include_ok" not in tables


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_suggested_ddl_quotes_pascalcase(pg_dsn):
    _, _, by_table = _collect_schema(pg_dsn, "t_fk_ddl")
    ddl = by_table["OrderVehicle"]["suggested_ddl"]
    assert '"OrderVehicle"' in ddl and '"ParentId"' in ddl
    assert by_table["OrderVehicle"]["columns"] == ["ParentId"]

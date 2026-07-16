import psycopg2
import pytest

from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_make_schema_creates_and_drops(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, "t_fixture_demo", 'CREATE TABLE {s}.a (id int);'):
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM information_schema.tables "
                            "WHERE table_schema='t_fixture_demo' AND table_name='a'")
                assert cur.fetchone() is not None
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name='t_fixture_demo'")
            assert cur.fetchone() is None  # dropped
    finally:
        conn.close()

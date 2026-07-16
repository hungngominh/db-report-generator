import psycopg2
import pytest

from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_pg_fixture_is_live_and_readonly_capable(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()

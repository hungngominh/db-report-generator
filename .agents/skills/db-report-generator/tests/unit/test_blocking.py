import threading
import time

import psycopg2
import pytest

from scripts.collectors.blocking import collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_finds_no_blocking_by_default(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    assert diag["metrics"] == []


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_finds_a_real_blocking_pair(pg_dsn):
    conn_a = psycopg2.connect(**pg_dsn)
    conn_a.autocommit = True
    conn_b = psycopg2.connect(**pg_dsn)
    conn_watch = psycopg2.connect(**pg_dsn)
    conn_watch.autocommit = True

    with _fixtures_sql.make_schema(conn_a, "blk_test", "CREATE TABLE {s}.t (id int primary key)"):
        with conn_a.cursor() as cur:
            cur.execute('INSERT INTO "blk_test".t (id) VALUES (1)')
            cur.execute('BEGIN')
            cur.execute('SELECT * FROM "blk_test".t WHERE id = 1 FOR UPDATE')

        blocked_started = threading.Event()

        def _blocked_update():
            with conn_b.cursor() as cur:
                blocked_started.set()
                cur.execute('UPDATE "blk_test".t SET id = 1 WHERE id = 1')

        t = threading.Thread(target=_blocked_update)
        t.start()
        blocked_started.wait(timeout=5)
        time.sleep(0.5)

        try:
            diag = collect(conn_watch, {})
        finally:
            with conn_a.cursor() as cur:
                cur.execute('COMMIT')
            t.join(timeout=5)
            conn_b.close()

    conn_a.close()
    conn_watch.close()

    assert diag["status"] == "ok"
    assert len(diag["metrics"]) == 1
    row = diag["metrics"][0]
    assert "SELECT" in row["blocking_query"]
    assert "UPDATE" in row["blocked_query"]

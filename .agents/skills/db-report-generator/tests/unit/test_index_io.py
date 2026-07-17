import psycopg2
import pytest

from scripts.collectors.index_io import cache_hit_ratio, collect
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_cache_hit_ratio_edges():
    assert cache_hit_ratio(0, 0) is None
    assert cache_hit_ratio(5, 0) == 1.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_created_index(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "idxio_test",
                "CREATE TABLE {s}.t (id int primary key, v int); "
                "CREATE INDEX t_v_idx ON {s}.t (v)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "idxio_test".t (id, v) VALUES (1, 1)')
                cur.execute('SELECT * FROM "idxio_test".t WHERE v = 1')
            diag = collect(conn, {})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    assert diag["scope"] == "index"
    names = {m["index"] for m in diag["metrics"]}
    assert "t_v_idx" in names
    row = next(m for m in diag["metrics"] if m["index"] == "t_v_idx")
    assert set(row) == {"schema", "table", "index", "idx_blks_read", "idx_blks_hit",
                         "cache_hit_ratio", "idx_scan"}

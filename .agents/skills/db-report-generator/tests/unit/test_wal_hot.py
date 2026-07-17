import psycopg2
import pytest

from scripts.collectors.wal_hot import collect, hot_update_ratio
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_hot_update_ratio_edges():
    assert hot_update_ratio(0, 0) is None
    assert hot_update_ratio(10, 10) == 1.0
    assert hot_update_ratio(10, 0) == 0.0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_reports_wal_row_and_hot_table_row(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with _fixtures_sql.make_schema(
                conn, "walhot_test",
                "CREATE TABLE {s}.t (id int primary key, v int)"):
            with conn.cursor() as cur:
                cur.execute('INSERT INTO "walhot_test".t (id, v) VALUES (1, 1)')
                cur.execute('UPDATE "walhot_test".t SET v = 2 WHERE id = 1')
            diag = collect(conn, {"server_version_num": 160000})
    finally:
        conn.close()

    assert diag["status"] == "ok"
    levels = {m["level"] for m in diag["metrics"]}
    assert "wal" in levels
    table_rows = [m for m in diag["metrics"] if m["level"] == "table" and m["table"] == "t"]
    assert len(table_rows) == 1
    assert table_rows[0]["n_tup_upd"] >= 1

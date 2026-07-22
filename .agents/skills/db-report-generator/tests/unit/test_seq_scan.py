import psycopg2
import pytest

from scripts.collectors import seq_scan
from scripts.collectors.seq_scan import collect, seq_scan_pct
from scripts.lib import index_catalog, sql_classify
from tests.pgcontainer import docker_available


def _delta(queryid, query, window_calls=1, window_total_exec_time_ms=1.0):
    return {"queryid": queryid, "query": query, "window_calls": window_calls,
            "window_total_exec_time_ms": window_total_exec_time_ms}


def test_seq_scan_pct_formula_edges():
    assert seq_scan_pct(80, 20) == 80.0
    assert seq_scan_pct(0, 100) == 0.0
    assert seq_scan_pct(100, 0) == 100.0
    assert seq_scan_pct(0, 0) is None  # no scans at all -> unknown, not 0


def test_related_queries_by_table_empty_deltas_returns_empty_dict():
    assert seq_scan._group_by_table(None, [], count_key="window_calls") == {}


def test_related_queries_by_table_groups_single_table_query(monkeypatch):
    delta = _delta("1", "SELECT * FROM orders WHERE org_id = 5", window_calls=10)
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations", lambda stmt: [(None, "orders")])
    monkeypatch.setattr(index_catalog, "resolve_relations", lambda conn, relations: [("public", "orders")])

    by_table = seq_scan._group_by_table(None, [delta], count_key="window_calls")

    assert by_table == {("public", "orders"): [delta]}


def test_related_queries_by_table_join_query_attached_to_both_tables(monkeypatch):
    delta = _delta("1", "SELECT * FROM orders o JOIN orgs g ON o.org_id = g.id WHERE g.name = 'x'")
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations",
                         lambda stmt: [(None, "orders"), (None, "orgs")])
    monkeypatch.setattr(index_catalog, "resolve_relations",
                         lambda conn, relations: [("public", "orders"), ("public", "orgs")])

    by_table = seq_scan._group_by_table(None, [delta], count_key="window_calls")

    assert by_table == {("public", "orders"): [delta], ("public", "orgs"): [delta]}


def test_related_queries_by_table_drops_unparseable_query(monkeypatch):
    delta = _delta("1", "not valid sql (((")
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: None)

    by_table = seq_scan._group_by_table(None, [delta], count_key="window_calls")

    assert by_table == {}


def test_related_queries_by_table_drops_unresolvable_relation(monkeypatch):
    delta = _delta("1", "SELECT * FROM some_cte_alias")
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations", lambda stmt: [(None, "some_cte_alias")])
    monkeypatch.setattr(index_catalog, "resolve_relations", lambda conn, relations: [])

    by_table = seq_scan._group_by_table(None, [delta], count_key="window_calls")

    assert by_table == {}


def test_related_queries_by_table_no_relations_referenced_is_dropped(monkeypatch):
    delta = _delta("1", "SELECT 1")
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations", lambda stmt: [])

    by_table = seq_scan._group_by_table(None, [delta], count_key="window_calls")

    assert by_table == {}


def test_related_queries_by_table_sorted_by_window_calls_descending(monkeypatch):
    low = _delta("1", "SELECT * FROM orders WHERE org_id = 1", window_calls=2)
    high = _delta("2", "SELECT * FROM orders WHERE org_id = 2", window_calls=50)
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations", lambda stmt: [(None, "orders")])
    monkeypatch.setattr(index_catalog, "resolve_relations", lambda conn, relations: [("public", "orders")])

    by_table = seq_scan._group_by_table(None, [low, high], count_key="window_calls")

    assert by_table[("public", "orders")] == [high, low]


def test_group_by_table_sorts_by_calls_desc_for_cumulative(monkeypatch):
    low = {"queryid": "1", "query": "SELECT * FROM orders WHERE org_id = 1",
           "calls": 2, "total_exec_time_ms": 1.0}
    high = {"queryid": "2", "query": "SELECT * FROM orders WHERE org_id = 2",
            "calls": 90, "total_exec_time_ms": 5.0}
    monkeypatch.setattr(sql_classify, "parse_statement", lambda sql: sql)
    monkeypatch.setattr(sql_classify, "referenced_relations", lambda stmt: [(None, "orders")])
    monkeypatch.setattr(index_catalog, "resolve_relations",
                        lambda conn, relations: [("public", "orders")])

    by_table = seq_scan._group_by_table(None, [low, high], count_key="calls")

    assert by_table[("public", "orders")] == [high, low]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_collect_runs_and_rows_are_wellformed(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        diag = collect(conn, {})
    finally:
        conn.close()
    assert diag["status"] == "ok"
    for m in diag["metrics"]:
        assert m["n_live_tup"] > 10000
        assert m["seq_scan"] + m["idx_scan"] > 0
        assert 0.0 <= m["seq_scan_pct"] <= 100.0
        assert m["related_queries"] == []
        assert set(m) == {"schema", "table", "seq_scan", "idx_scan", "n_live_tup",
                           "seq_scan_pct", "related_queries"}

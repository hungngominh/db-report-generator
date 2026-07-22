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
        for q in m["related_queries"]:
            assert q["source"] in ("window", "cumulative")
            if q["source"] == "window":
                assert "window_calls" in q and "window_total_exec_time_ms" in q
            else:
                assert "calls" in q and "total_exec_time_ms" in q
        assert set(m) == {"schema", "table", "seq_scan", "idx_scan", "n_live_tup",
                           "seq_scan_pct", "related_queries"}


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, *a):
        pass
    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
    def cursor(self):
        return _FakeCursor(self._rows)


def _win(queryid="1", query="q", window_calls=3, window_total_exec_time_ms=2.0):
    return {"queryid": queryid, "query": query, "window_calls": window_calls,
            "window_total_exec_time_ms": window_total_exec_time_ms}


def _cum(queryid="9", query="c", calls=50, total_exec_time_ms=8.0):
    return {"queryid": queryid, "query": query, "calls": calls,
            "total_exec_time_ms": total_exec_time_ms}


def test_related_for_table_prefers_window_and_tags_source():
    key = ("public", "orders")
    out = seq_scan._related_for_table(key, {key: [_win()]}, {key: [_cum()]})
    assert len(out) == 1
    assert out[0]["source"] == "window"
    assert out[0]["window_calls"] == 3
    assert "calls" not in out[0]


def test_related_for_table_falls_back_to_cumulative_when_window_empty():
    key = ("public", "orders")
    out = seq_scan._related_for_table(key, {}, {key: [_cum(calls=99, total_exec_time_ms=9.0)]})
    assert len(out) == 1
    assert out[0]["source"] == "cumulative"
    assert out[0]["calls"] == 99
    assert out[0]["total_exec_time_ms"] == 9.0
    assert "window_calls" not in out[0]


def test_related_for_table_empty_when_neither():
    assert seq_scan._related_for_table(("public", "x"), {}, {}) == []


def test_related_for_table_caps_cumulative_at_five():
    key = ("public", "orders")
    items = [_cum(queryid=str(i), calls=100 - i) for i in range(8)]  # pre-sorted desc
    out = seq_scan._related_for_table(key, {}, {key: items})
    assert len(out) == 5
    assert [o["queryid"] for o in out] == ["0", "1", "2", "3", "4"]


def test_collect_reset_detected_skips_window_but_uses_cumulative(monkeypatch):
    seq_rows = [("dbo", "orders", 5000, 10, 20000)]
    seen = {}

    def fake_group(conn, rows, *, count_key):
        seen[count_key] = rows
        if count_key == "calls" and rows:
            return {("dbo", "orders"): rows}
        return {}

    monkeypatch.setattr(seq_scan, "_group_by_table", fake_group)
    caps = {"sampling": {"reset_detected": True,
                         "deltas": [_win()],
                         "cumulative": [_cum()]}}
    diag = seq_scan.collect(_FakeConn(seq_rows), caps)

    assert "window_calls" not in seen          # window path gated off on reset
    assert "calls" in seen                       # cumulative path still ran
    m = diag["metrics"][0]
    assert m["related_queries"][0]["source"] == "cumulative"
    assert set(m) == {"schema", "table", "seq_scan", "idx_scan", "n_live_tup",
                      "seq_scan_pct", "related_queries"}


def test_collect_no_sampling_yields_empty_related():
    diag = seq_scan.collect(_FakeConn([("dbo", "orders", 5000, 10, 20000)]), {})
    assert diag["metrics"][0]["related_queries"] == []

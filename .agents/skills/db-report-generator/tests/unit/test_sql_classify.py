from scripts.lib import sql_classify


def test_parse_statement_returns_none_for_unparseable():
    assert sql_classify.parse_statement("not valid sql (((") is None


def test_parse_statement_returns_none_for_multi_statement():
    assert sql_classify.parse_statement("select 1; drop table x;") is None


def test_parse_statement_returns_none_for_empty():
    assert sql_classify.parse_statement("") is None


def test_parse_statement_returns_node_for_valid_select():
    stmt = sql_classify.parse_statement("select 1 from t where id = 5")
    assert stmt is not None


def test_has_parameters_true_for_placeholder():
    stmt = sql_classify.parse_statement("select * from t where id = $1")
    assert sql_classify.has_parameters(stmt) is True


def test_has_parameters_false_for_literal():
    stmt = sql_classify.parse_statement("select * from t where id = 5")
    assert sql_classify.has_parameters(stmt) is False


def test_has_parameters_false_for_none():
    assert sql_classify.has_parameters(None) is False


def test_referenced_relations_qualified():
    stmt = sql_classify.parse_statement("select * from public.orders")
    assert sql_classify.referenced_relations(stmt) == [("public", "orders")]


def test_referenced_relations_unqualified():
    stmt = sql_classify.parse_statement("select * from orders")
    assert sql_classify.referenced_relations(stmt) == [(None, "orders")]


def test_referenced_relations_empty_for_none():
    assert sql_classify.referenced_relations(None) == []


def test_is_analyze_safe_true_for_plain_select():
    stmt = sql_classify.parse_statement("select * from orders where id = 5")
    assert sql_classify.is_analyze_safe(stmt) == (True, None)


def test_is_analyze_safe_false_for_non_select():
    stmt = sql_classify.parse_statement("update orders set status = 'x' where id = 5")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "not_a_select"


def test_is_analyze_safe_false_for_for_update():
    stmt = sql_classify.parse_statement("select * from orders where id = 5 for update")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "locking_clause"


def test_is_analyze_safe_false_for_unsafe_function():
    stmt = sql_classify.parse_statement("select nextval('orders_id_seq')")
    safe, reason = sql_classify.is_analyze_safe(stmt)
    assert safe is False
    assert reason == "unsafe_function:nextval"


def test_is_analyze_safe_false_for_unparseable():
    assert sql_classify.is_analyze_safe(None) == (False, "unparseable")

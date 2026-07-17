from scripts.lib import index_predicate, sql_classify


def test_single_equality_column():
    stmt = sql_classify.parse_statement("select * from t where status = 'active'")
    assert index_predicate.equality_columns_from_statement(stmt) == [("status",)]


def test_qualified_equality_column():
    stmt = sql_classify.parse_statement("select * from t where t.user_id = 5")
    assert index_predicate.equality_columns_from_statement(stmt) == [("t", "user_id")]


def test_multiple_equality_columns_in_and():
    stmt = sql_classify.parse_statement("select * from t where status = 'active' and org_id = 3")
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("status",) in cols
    assert ("org_id",) in cols


def test_non_equality_operator_not_captured():
    stmt = sql_classify.parse_statement("select * from t where created_at > '2024-01-01'")
    assert index_predicate.equality_columns_from_statement(stmt) == []


def test_none_statement_returns_empty():
    assert index_predicate.equality_columns_from_statement(None) == []


def test_extract_equality_columns_parses_sql_directly():
    assert index_predicate.extract_equality_columns("select * from t where id = 1") == [("id",)]


def test_equality_column_inside_from_subquery():
    stmt = sql_classify.parse_statement(
        "select * from (select * from t where org_id = 3) sub"
    )
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("org_id",) in cols


def test_equality_column_inside_or_branch():
    stmt = sql_classify.parse_statement(
        "select * from t where status = 'active' or org_id = 3"
    )
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("status",) in cols
    assert ("org_id",) in cols


def test_equality_column_inside_join_on_clause():
    stmt = sql_classify.parse_statement(
        "select * from t join u on t.org_id = u.org_id where 1 = 1"
    )
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("t", "org_id") in cols
    assert ("u", "org_id") in cols


def test_equality_column_inside_cte():
    stmt = sql_classify.parse_statement(
        "with c as (select * from t where org_id = 3) select * from c"
    )
    cols = index_predicate.equality_columns_from_statement(stmt)
    assert ("org_id",) in cols

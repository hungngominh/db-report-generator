import pytest

from scripts.lib.safety import is_readonly_sql


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "  select * from pg_stat_activity",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "EXPLAIN SELECT * FROM t",
    "EXPLAIN (VERBOSE) SELECT 1",
    "SHOW work_mem",
    "SELECT 1;",
])
def test_readonly_allowed(sql):
    assert is_readonly_sql(sql) is True


@pytest.mark.parametrize("sql", [
    "DROP INDEX foo",
    "delete from t",
    "UPDATE t SET a=1",
    "INSERT INTO t VALUES (1)",
    "TRUNCATE t",
    "ALTER SYSTEM SET work_mem='1GB'",
    "CREATE INDEX ON t (a)",
    "EXPLAIN ANALYZE SELECT * FROM t",
    "EXPLAIN (ANALYZE, BUFFERS) SELECT 1",
    "VACUUM ANALYZE t",
    "SET statement_timeout = '3s'",          # session state change → not read-only
    "SELECT 1; DROP TABLE x",                # multi-statement
    "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",  # writable CTE
    "SELECT * INTO new_table FROM old_table",              # CREATE TABLE AS
    "WITH x AS (SELECT 1) SELECT * INTO t2 FROM x",        # writable via INTO
    "SELECT set_config('work_mem','1GB',false)",           # session state change
    "WITH x AS (SELECT set_config('work_mem','1GB',false)) SELECT * FROM x",
    "SELECT pg_terminate_backend(12345)",                  # execute admin action
    "SELECT lo_export(12345, '/tmp/x')",                   # filesystem write
    "SELECT * FROM t FOR UPDATE",                          # row lock side effect
    "",
])
def test_write_or_unsafe_blocked(sql):
    assert is_readonly_sql(sql) is False

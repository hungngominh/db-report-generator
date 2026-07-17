import psycopg2
import pytest

from scripts.collectors.duplicate_index import collect
from tests._fixtures_sql import make_schema
from tests.pgcontainer import docker_available

DDL = """
CREATE TABLE {s}.dup (id int PRIMARY KEY, x int, y int, z int);
CREATE INDEX dup_x_1 ON {s}.dup (x);
CREATE INDEX dup_x_2 ON {s}.dup (x);              -- exact duplicate of dup_x_1 (both plain)
CREATE UNIQUE INDEX dup_z_uniq ON {s}.dup (z);    -- unique on z
CREATE INDEX dup_z_plain ON {s}.dup (z);          -- same signature as dup_z_uniq: only the plain one is droppable
CREATE INDEX dup_xy ON {s}.dup (x, y);            -- dup_x_1 (x) is a leading prefix of this
"""


def _run(pg_dsn, schema, version=160000):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, schema, DDL):
            diag = collect(conn, {"server_version_num": version})
    finally:
        conn.close()
    rows = [m for m in diag["metrics"] if m["schema"] == schema]
    return diag, rows


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_exact_duplicate_detected_and_constraints_never_dropped(pg_dsn):
    diag, rows = _run(pg_dsn, "t_dup_exact")
    assert diag["status"] == "ok"
    exact = [r for r in rows if r["kind"] == "exact_duplicate"]
    by_members = {frozenset(r["members"]): r for r in exact}
    # plain x-pair: exactly one drop candidate; keep is deterministic (sorted by name)
    xpair = by_members[frozenset({"dup_x_1", "dup_x_2"})]
    assert len(xpair["drop_candidates"]) == 1
    assert xpair["keep"] == "dup_x_1"
    # unique + plain on z share a signature: the UNIQUE is kept, only the plain
    # is droppable (a constraint-backing index is NEVER a drop candidate).
    zpair = by_members[frozenset({"dup_z_uniq", "dup_z_plain"})]
    assert zpair["keep"] == "dup_z_uniq"
    assert zpair["drop_candidates"] == ["dup_z_plain"]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_prefix_redundancy_detected(pg_dsn):
    diag, rows = _run(pg_dsn, "t_dup_prefix")
    red = [r for r in rows if r["kind"] == "potentially_redundant"]
    # dup_x_1 (x) is a leading prefix of dup_xy (x, y)
    assert any(r["redundant"] == "dup_x_1" and r["covered_by"] == "dup_xy" for r in red)
    # a UNIQUE index is never called redundant
    assert all(r["redundant"] != "dup_z_uniq" for r in red)


EXPR_DDL = """
CREATE TABLE {s}.t (id int PRIMARY KEY, name text, other int);
CREATE INDEX idx_lower ON {s}.t (lower(name));
CREATE INDEX idx_upper ON {s}.t (upper(name));
CREATE INDEX idx_pat ON {s}.t (name text_pattern_ops);
CREATE INDEX idx_name_other ON {s}.t (name, other);
"""


def _run_ddl(pg_dsn, schema, ddl, version=160000):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with make_schema(conn, schema, ddl):
            diag = collect(conn, {"server_version_num": version})
    finally:
        conn.close()
    return [m for m in diag["metrics"] if m["schema"] == schema]


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_different_expression_indexes_are_not_exact_duplicates(pg_dsn):
    rows = _run_ddl(pg_dsn, "t_dup_expr", EXPR_DDL)
    exact = [r for r in rows if r["kind"] == "exact_duplicate"]
    for r in exact:
        assert not {"idx_lower", "idx_upper"} <= set(r["members"])


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_prefix_redundancy_respects_opclass(pg_dsn):
    rows = _run_ddl(pg_dsn, "t_dup_opclass", EXPR_DDL)
    red = [r for r in rows if r["kind"] == "potentially_redundant"]
    assert all(r["redundant"] != "idx_pat" for r in red)

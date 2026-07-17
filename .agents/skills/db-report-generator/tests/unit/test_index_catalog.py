import psycopg2
import pytest

from scripts.lib import index_catalog
from tests import _fixtures_sql
from tests.pgcontainer import docker_available


def test_is_covered_true_for_exact_match():
    existing = [("org_id", "status")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is True


def test_is_covered_true_for_leading_prefix():
    existing = [("org_id", "status", "created_at")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is True


def test_is_covered_true_regardless_of_column_order():
    # is_covered's docstring says `columns` may be given in "any order", and
    # for an all-equality predicate set that is also true of the existing
    # index's own leading-column order: real PostgreSQL matches multicolumn
    # btree index columns by identity, not by the textual order equality
    # clauses were written/discovered in (see "Multicolumn Indexes" in the
    # PostgreSQL docs -- "the clauses can appear in any order"). An index on
    # (status, org_id) is therefore just as usable for an equality lookup on
    # {org_id, status} as one on (org_id, status) would be, so this must be
    # True, not a "not a prefix" miss.
    existing = [("status", "org_id")]
    assert index_catalog.is_covered(existing, ["org_id", "status"]) is True


def test_is_covered_false_when_wanted_columns_are_not_the_leading_columns():
    # Genuine "not a prefix" case: the leading 2 columns of the index are
    # (status, org_id) -- neither of which is the same *set* as the wanted
    # {org_id, created_at}, so no combination of leading columns covers it.
    existing = [("status", "org_id", "created_at")]
    assert index_catalog.is_covered(existing, ["org_id", "created_at"]) is False


def test_is_covered_false_when_no_indexes():
    assert index_catalog.is_covered([], ["org_id"]) is False


def test_is_covered_false_when_expression_index_blocks_prefix():
    existing = [(None, "status")]
    assert index_catalog.is_covered(existing, [None, "status"]) is False


def test_is_covered_vacuously_true_for_empty_columns_when_indexes_exist():
    # Empty `columns` means "the empty set of columns" -- the empty set is
    # a subset of every leading prefix, so this is vacuously True as long
    # as at least one index exists on the table (matches is_covered's own
    # stated definition: "columns is a leading-prefix subset of some
    # existing index's key columns").
    existing = [("org_id", "status")]
    assert index_catalog.is_covered(existing, []) is True


def test_is_covered_false_for_empty_columns_and_no_indexes():
    assert index_catalog.is_covered([], []) is False


def test_is_covered_true_for_duplicate_columns_in_wanted():
    existing = [("org_id", "status")]
    assert index_catalog.is_covered(existing, ["org_id", "org_id", "status"]) is True


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_existing_indexed_columns_against_live_postgres(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    ddl = """
    CREATE TABLE {s}.orders (id serial PRIMARY KEY, org_id int, status text, created_at timestamptz);
    CREATE INDEX ON {s}.orders (org_id, status);
    """
    with _fixtures_sql.make_schema(conn, "idxcat", ddl):
        cols = index_catalog.existing_indexed_columns(conn, "idxcat", "orders")
        assert ("id",) in cols
        assert ("org_id", "status") in cols
    conn.close()

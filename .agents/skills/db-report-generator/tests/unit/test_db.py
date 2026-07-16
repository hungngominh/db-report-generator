import psycopg2
import pytest

from scripts.lib.db import connect, logging_dsn
from scripts.lib.envparse import DbConfig
from tests.pgcontainer import docker_available


def _cfg_from_dsn_kwargs(kw) -> DbConfig:
    return DbConfig(host=kw["host"], port=kw["port"], database=kw["dbname"],
                    user=kw["user"], password=kw["password"], project_name="t")


def test_logging_dsn_is_redacted():
    cfg = DbConfig(host="db.internal.example", port=5432, database="prod",
                   user="app", password="s3cr3t", project_name="p")
    out = logging_dsn(cfg)
    assert "s3cr3t" not in out
    assert "db.internal.example" not in out


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_connect_runs_select(pg_dsn):
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 42")
            assert cur.fetchone()[0] == 42
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_connection_is_read_only(pg_dsn):
    # The server must REJECT writes — this is the real safety boundary.
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn))
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TABLE should_not_exist (x int)")
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_statement_timeout_is_set(pg_dsn):
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn), statement_timeout_ms=1234)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "1234ms"
    finally:
        conn.close()

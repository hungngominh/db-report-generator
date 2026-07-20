import psycopg2
import pytest

from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_pg_fixture_is_live_and_readonly_capable(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()


import subprocess

from tests.pgcontainer import PostgresContainer


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_container_cleaned_up_when_ready_fails(monkeypatch):
    # If _wait_ready raises inside __enter__, the container must still be removed
    # (no leak) — __exit__ won't run because __enter__ never returned.
    def boom(self, timeout=60.0):
        raise RuntimeError("simulated not-ready")

    monkeypatch.setattr(PostgresContainer, "_wait_ready", boom)
    pg = PostgresContainer()
    with pytest.raises(RuntimeError):
        pg.__enter__()
    out = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name={pg.name}"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"leaked container {pg.name}"


def test_default_image_is_pg16_without_env_var(monkeypatch):
    monkeypatch.delenv("DBREPORT_TEST_PG_IMAGE", raising=False)
    assert PostgresContainer().image == "postgres:16"


def test_image_honors_env_var_override(monkeypatch):
    monkeypatch.setenv("DBREPORT_TEST_PG_IMAGE", "postgres:14")
    assert PostgresContainer().image == "postgres:14"


def test_explicit_image_arg_overrides_env_var(monkeypatch):
    monkeypatch.setenv("DBREPORT_TEST_PG_IMAGE", "postgres:14")
    assert PostgresContainer(image="postgres:18").image == "postgres:18"

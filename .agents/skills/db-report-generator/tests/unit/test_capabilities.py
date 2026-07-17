import psycopg2
import pytest

from scripts.capabilities import probe
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_shape_and_values(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    assert caps["server_version_num"] >= 140000
    assert caps["is_superuser"] is True          # 'postgres' superuser in the container
    assert caps["vendor"] == "self-hosted"       # plain container, no cloud roles
    assert caps["managed"] is False
    assert "plpgsql" in caps["extensions"]        # default extension
    assert set(["server_version_num", "is_superuser", "has_pg_read_all_stats",
                "has_pg_monitor", "vendor", "managed", "extensions", "ram_bytes",
                "track_io_timing", "pg_stat_statements_track"]) <= set(caps)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_is_json_serializable(pg_dsn):
    import json
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    json.dumps(caps)  # must not raise


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_includes_io_timing_capabilities(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    assert caps["track_io_timing"] is False  # postgres:16 fixture image default
    assert caps["pg_stat_statements_track"] == "top"  # default once the library is preloaded

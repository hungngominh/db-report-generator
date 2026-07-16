import pytest

from scripts.analyzer import _scrub, analyze
from scripts.lib.envparse import DbConfig
from scripts.lib.schema import validation_errors
from tests.pgcontainer import docker_available


def _good(pg_dsn) -> DbConfig:
    return DbConfig(host=pg_dsn["host"], port=pg_dsn["port"], database=pg_dsn["dbname"],
                    user=pg_dsn["user"], password=pg_dsn["password"], project_name="good")


def _bad() -> DbConfig:
    return DbConfig(host="127.0.0.1", port=1, database="nope",
                    user="nobody", password="s3cr3t-nope", project_name="bad")


def test_analyze_output_is_schema_valid_and_isolates_failures(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn), _bad()])
    assert validation_errors(report) == []
    by_id = {t["target_id"]: t for t in report["targets"]}
    assert by_id["good"]["collection_status"] == "ok"
    assert by_id["good"]["capabilities"]["server_version_num"] >= 140000
    # Registered collectors run for a healthy target; none of them error out.
    # (Was `== {}` back when no collectors were registered in Phase 0a.)
    assert all(d["status"] == "ok" for d in by_id["good"]["diagnostics"].values())
    # one dead target does not kill the run
    assert by_id["bad"]["collection_status"] == "error"
    assert by_id["bad"]["error"]


def test_error_message_is_scrubbed_of_password(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_bad()])
    err = report["targets"][0]["error"]
    assert "s3cr3t-nope" not in err


def test_scrub_redacts_password_host_and_user_when_present():
    cfg = DbConfig(host="db.internal.example", port=5432, database="prod",
                   user="appuser", password="s3cr3t-nope", project_name="p")
    msg = ('connection to server at "db.internal.example" failed: '
           'password authentication failed for user "appuser" (password=s3cr3t-nope)')
    out = _scrub(msg, cfg)
    assert "s3cr3t-nope" not in out
    assert "db.internal.example" not in out
    assert "appuser" not in out
    assert "«redacted»" in out


def test_metadata_present_but_no_time_in_diagnostics(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn)])
    assert report["schema_version"] == "4.0"
    assert report["run"]["run_id"]
    # capabilities/diagnostics carry no timestamp keys
    caps = report["targets"][0]["capabilities"]
    assert not any("_at" in k or k in ("timestamp", "now") for k in caps)


def test_scrub_strips_resolved_ip_literal_not_just_configured_host():
    # libpq echoes the resolved IP even when ServerName is a hostname.
    cfg = DbConfig(host="db.prod.internal", port=5432, database="prod",
                   user="appuser", password="pw", project_name="p")
    msg = ('connection to server at "db.prod.internal" (10.20.30.40), '
           'port 5432 failed: Connection refused')
    out = _scrub(msg, cfg)
    assert "db.prod.internal" not in out
    assert "10.20.30.40" not in out          # the resolved IP must be gone
    assert "Connection refused" in out        # useful reason preserved


def test_scrub_strips_ipv6_literal():
    cfg = DbConfig(host="localhost", port=5432, database="prod",
                   user="u", password="pw", project_name="p")
    out = _scrub('server at "localhost" (::1), port 1 failed', cfg)
    assert "::1" not in out

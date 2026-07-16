import pytest

from scripts.analyzer import analyze
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
    assert by_id["good"]["diagnostics"] == {}
    # one dead target does not kill the run
    assert by_id["bad"]["collection_status"] == "error"
    assert by_id["bad"]["error"]


def test_error_message_is_scrubbed_of_password(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_bad()])
    err = report["targets"][0]["error"]
    assert "s3cr3t-nope" not in err


def test_metadata_present_but_no_time_in_diagnostics(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn)])
    assert report["schema_version"] == "4.0"
    assert report["run"]["run_id"]
    # capabilities/diagnostics carry no timestamp keys
    caps = report["targets"][0]["capabilities"]
    assert not any("_at" in k or k in ("timestamp", "now") for k in caps)

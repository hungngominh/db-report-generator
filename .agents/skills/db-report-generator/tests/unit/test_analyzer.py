import pytest

import warnings

import dataclasses

import psycopg2

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
    # a healthy target: no collector errored (skipped is legitimate, e.g. a
    # collector whose required extension isn't installed)
    assert all(d["status"] != "error" for d in by_id["good"]["diagnostics"].values())
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


def test_analyze_target_sampling_is_none_when_pg_stat_statements_absent(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn)])
    target = report["targets"][0]
    assert target["sampling"] is None


def test_analyze_populates_sampling_metadata_when_pg_stat_statements_present(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    finally:
        conn.close()
    cfg = dataclasses.replace(_good(pg_dsn), sampling_window_seconds=0)
    report = analyze([cfg])
    target = report["targets"][0]
    assert target["sampling"] is not None
    assert target["sampling"]["window_seconds"] == 0
    assert target["sampling"]["reset_detected"] is False
    assert target["diagnostics"]["query_stats"]["status"] == "ok"


from scripts.analyzer import _check_latency_budget


def _sampled_target(window_seconds):
    return {"sampling": {"window_seconds": window_seconds}}


def test_latency_budget_warns_when_elapsed_close_to_serial_sum():
    targets = [_sampled_target(30), _sampled_target(30), _sampled_target(30)]  # sum = 90s
    with pytest.warns(RuntimeWarning, match="not bounded"):
        _check_latency_budget(targets, elapsed_seconds=85.0)


def test_latency_budget_silent_when_elapsed_reflects_bounded_parallelism():
    targets = [_sampled_target(30), _sampled_target(30), _sampled_target(30)]  # sum = 90s
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget(targets, elapsed_seconds=32.0)  # ran in ~1 window, not 3 -> no raise


def test_latency_budget_silent_for_a_single_target():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget([_sampled_target(30)], elapsed_seconds=30.0)


def test_latency_budget_silent_when_no_sampling_was_performed():
    targets = [{"sampling": None}, {"sampling": None}]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_latency_budget(targets, elapsed_seconds=100.0)


def test_sampler_failure_does_not_wipe_out_other_collectors(pg_dsn, monkeypatch):
    if not docker_available():
        pytest.skip("docker not available")
    conn = psycopg2.connect(**pg_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    finally:
        conn.close()

    from scripts import sampler

    def boom(*args, **kwargs):
        raise RuntimeError("simulated sampler failure")

    monkeypatch.setattr(sampler, "sample_pg_stat_statements_window", boom)

    report = analyze([_good(pg_dsn)])
    target = report["targets"][0]
    assert target["sampling"] is None
    assert target["error"] is None
    assert target["collection_status"] in ("ok", "partial")
    assert target["diagnostics"]
    assert all(d.get("status") != "error" for d in target["diagnostics"].values()
               if d.get("status") is not None)


def test_analyze_runs_multiple_targets_concurrently(monkeypatch):
    import time as time_module

    from scripts import analyzer

    def fake_analyze_target(cfg):
        time_module.sleep(0.2)
        return {"target_id": cfg.project_name, "database": cfg.database,
                "collection_status": "ok", "error": None, "capabilities": {},
                "diagnostics": {}, "sampling": None}

    monkeypatch.setattr(analyzer, "_analyze_target", fake_analyze_target)
    configs = [DbConfig(host="h", port=1, database=f"d{i}", user="u", password="p",
                        project_name=f"p{i}") for i in range(4)]
    t0 = time_module.monotonic()
    report = analyzer.analyze(configs)
    elapsed = time_module.monotonic() - t0
    assert len(report["targets"]) == 4
    assert {t["target_id"] for t in report["targets"]} == {"p0", "p1", "p2", "p3"}
    # 4 targets x 0.2s would be 0.8s fully serial; bounded-parallel keeps it near 0.2s.
    assert elapsed < 0.6


def test_analyze_wires_configured_pool_size_from_raw_env(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    cfg = dataclasses.replace(_good(pg_dsn))
    cfg.raw["PoolSize"] = 15
    report = analyze([cfg])
    assert report["targets"][0]["capabilities"]["configured_pool_size"] == 15

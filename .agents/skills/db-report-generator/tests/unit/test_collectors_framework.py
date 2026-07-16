from scripts.collectors import base, run_collectors
from scripts.analyzer import _collection_status
from scripts.lib.schema import validate_report


def _wrap(diag):
    # Minimal schema-valid report carrying one diagnostic, to prove diag shape.
    return {
        "schema_version": "4.0", "tool_version": "4.0.0",
        "run": {"run_id": "x", "started_at": "t", "completed_at": "t"},
        "redaction_mode": "redact",
        "targets": [{
            "target_id": "t", "database": "d", "collection_status": "ok",
            "error": None, "capabilities": {}, "diagnostics": {"demo": diag},
        }],
    }


def test_diagnostic_and_skipped_are_schema_valid():
    ok = base.diagnostic("table", "ok", [{"a": 1}])
    validate_report(_wrap(ok))            # must not raise
    sk = base.skipped("table", "needs pgstattuple")
    assert sk["status"] == "skipped" and sk["metrics"] == [] and sk["reason"]
    validate_report(_wrap(sk))


def test_run_collectors_isolates_a_raising_collector():
    def good(conn, caps):
        return base.diagnostic("index", "ok", [{"n": 1}])

    def boom(conn, caps):
        raise RuntimeError("kaboom")

    out = run_collectors(conn=None, caps={}, registry={"good": good, "bad": boom})
    assert out["good"]["status"] == "ok"
    assert out["bad"]["status"] == "error"
    assert "RuntimeError" in (out["bad"]["reason"] or "")


def test_collection_status_is_partial_when_any_diagnostic_errored():
    ok = {"status": "ok"}
    err = {"status": "error"}
    assert _collection_status({"a": ok}) == "ok"
    assert _collection_status({"a": ok, "b": err}) == "partial"
    assert _collection_status({}) == "ok"

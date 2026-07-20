import json

from scripts import run_report

ENV_JSON = json.dumps({
    "ServerName": "localhost", "Port": 5432, "CatalogName": "app_prod",
    "Username": "postgres", "Password": "secret",
})

FAKE_REPORT = {
    "schema_version": "4.0", "tool_version": "4.0.0",
    "run": {"run_id": "r", "started_at": "t0", "completed_at": "t1"},
    "redaction_mode": "redact",
    "targets": [
        {
            "target_id": "app_prod", "database": "app_prod", "collection_status": "ok", "error": None,
            "capabilities": {}, "diagnostics": {},
        }
    ],
}


def test_run_writes_report_data_json_and_rendered_files(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(ENV_JSON, encoding="utf-8")
    out_dir = tmp_path / "2026-07-20"

    captured = {}

    def fake_analyze(configs, **kwargs):
        captured["configs"] = configs
        return FAKE_REPORT

    monkeypatch.setattr(run_report.analyzer, "analyze", fake_analyze)

    result = run_report.run(env_path, out_dir)

    assert result == FAKE_REPORT
    assert captured["configs"][0].database == "app_prod"
    data = json.loads((out_dir / "report_data.json").read_text(encoding="utf-8"))
    assert data == FAKE_REPORT
    assert (out_dir / "DB_STATUS_REPORT.md").exists()
    assert (out_dir / "FINDINGS.md").exists()
    assert (out_dir / "report_summary.json").exists()


def test_main_rejects_missing_env_file(tmp_path, capsys):
    missing = tmp_path / "nope.env"
    out_dir = tmp_path / "out"
    rc = run_report.main(["run_report", str(missing), str(out_dir)])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_main_rejects_wrong_arg_count(capsys):
    rc = run_report.main(["run_report", "only-one-arg"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_main_reports_invalid_env_as_error(tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text(json.dumps({"ServerName": "localhost"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = run_report.main(["run_report", str(env_path), str(out_dir)])
    assert rc == 1
    assert "invalid .env" in capsys.readouterr().err

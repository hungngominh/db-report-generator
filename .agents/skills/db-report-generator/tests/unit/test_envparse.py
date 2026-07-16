import json

import pytest

from scripts.lib.envparse import DbConfig, parse_env

SAMPLE = {
    "ServerName": "db.example",
    "CatalogName": "MyDatabase",
    "Username": "readonly_user",
    "Password": "secret",
    "Port": 5432,
    "ProjectName": "My App",
    "CodePath": "D:/Projects/MyApp",
}


def test_parse_from_json_string():
    cfg = parse_env(json.dumps(SAMPLE))
    assert isinstance(cfg, DbConfig)
    assert cfg.host == "db.example"
    assert cfg.port == 5432
    assert cfg.database == "MyDatabase"
    assert cfg.user == "readonly_user"
    assert cfg.password == "secret"
    assert cfg.project_name == "My App"


def test_parse_from_path(tmp_path):
    p = tmp_path / ".env"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    cfg = parse_env(p)
    assert cfg.database == "MyDatabase"


def test_port_defaults_to_5432_when_absent():
    data = {k: v for k, v in SAMPLE.items() if k != "Port"}
    assert parse_env(json.dumps(data)).port == 5432


def test_missing_required_key_raises():
    data = {k: v for k, v in SAMPLE.items() if k != "ServerName"}
    with pytest.raises(ValueError):
        parse_env(json.dumps(data))

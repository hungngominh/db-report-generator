import pytest

from monitor.config import MonitorConfig, load_config


def test_load_config_raises_on_missing_required_vars():
    with pytest.raises(ValueError, match="missing required env vars"):
        load_config(env={})


def test_load_config_applies_defaults():
    env = {
        "TARGET_DB_HOST": "db.internal", "TARGET_DB_NAME": "app",
        "TARGET_DB_USER": "monitor", "TARGET_DB_PASSWORD": "secret",
        "TARGET_NAME": "acme-prod", "STORAGE_DB_DSN": "postgresql://storage/db",
    }
    cfg = load_config(env=env)

    assert cfg == MonitorConfig(
        target_host="db.internal", target_port=5432, target_db="app",
        target_user="monitor", target_password="secret", target_name="acme-prod",
        storage_dsn="postgresql://storage/db",
        light_interval_seconds=60, heavy_interval_seconds=1800, retention_days=30,
    )


def test_load_config_reads_overrides():
    env = {
        "TARGET_DB_HOST": "db.internal", "TARGET_DB_PORT": "6432",
        "TARGET_DB_NAME": "app", "TARGET_DB_USER": "monitor",
        "TARGET_DB_PASSWORD": "secret", "TARGET_NAME": "acme-prod",
        "STORAGE_DB_DSN": "postgresql://storage/db",
        "LIGHT_INTERVAL_SECONDS": "30", "HEAVY_INTERVAL_SECONDS": "900",
        "RETENTION_DAYS": "7",
    }
    cfg = load_config(env=env)

    assert cfg.target_port == 6432
    assert cfg.light_interval_seconds == 30
    assert cfg.heavy_interval_seconds == 900
    assert cfg.retention_days == 7

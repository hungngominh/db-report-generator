"""Docker-style KEY=VALUE env var config for the db-monitor daemon."""
import os
from dataclasses import dataclass


@dataclass
class MonitorConfig:
    target_host: str
    target_port: int
    target_db: str
    target_user: str
    target_password: str
    target_name: str
    storage_dsn: str
    light_interval_seconds: int = 60
    heavy_interval_seconds: int = 1800
    retention_days: int = 30


_REQUIRED = (
    "TARGET_DB_HOST", "TARGET_DB_NAME", "TARGET_DB_USER",
    "TARGET_DB_PASSWORD", "TARGET_NAME", "STORAGE_DB_DSN",
)


def load_config(env=None) -> MonitorConfig:
    e = env if env is not None else os.environ
    missing = [k for k in _REQUIRED if not e.get(k)]
    if missing:
        raise ValueError(f"missing required env vars: {', '.join(missing)}")
    return MonitorConfig(
        target_host=e["TARGET_DB_HOST"],
        target_port=int(e.get("TARGET_DB_PORT", 5432)),
        target_db=e["TARGET_DB_NAME"],
        target_user=e["TARGET_DB_USER"],
        target_password=e["TARGET_DB_PASSWORD"],
        target_name=e["TARGET_NAME"],
        storage_dsn=e["STORAGE_DB_DSN"],
        light_interval_seconds=int(e.get("LIGHT_INTERVAL_SECONDS", 60)),
        heavy_interval_seconds=int(e.get("HEAVY_INTERVAL_SECONDS", 1800)),
        retention_days=int(e.get("RETENTION_DAYS", 30)),
    )

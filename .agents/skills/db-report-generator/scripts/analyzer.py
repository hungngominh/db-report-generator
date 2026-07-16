"""Orchestrate per-target collection into a schema-valid report_data.json."""
import uuid
from datetime import datetime, timezone

from scripts import capabilities
from scripts.lib import db, schema
from scripts.lib.envparse import DbConfig

TOOL_VERSION = "4.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scrub(message: str, cfg: DbConfig) -> str:
    out = message
    for secret in (cfg.password, cfg.host, cfg.user):
        if secret:
            out = out.replace(secret, "«redacted»")
    return out


def _analyze_target(cfg: DbConfig) -> dict:
    target = {
        "target_id": cfg.project_name or cfg.database,
        "database": cfg.database,
        "collection_status": "ok",
        "error": None,
        "capabilities": {},
        "diagnostics": {},  # collectors land here in Phase 0b
    }
    try:
        conn = db.connect(cfg)
        try:
            target["capabilities"] = capabilities.probe(conn)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - isolate per-target failure
        target["collection_status"] = "error"
        target["error"] = _scrub(str(exc), cfg)
    return target


def analyze(configs, *, redaction_mode: str = "redact") -> dict:
    started = _now()
    targets = [_analyze_target(cfg) for cfg in configs]
    report = {
        "schema_version": "4.0",
        "tool_version": TOOL_VERSION,
        "run": {"run_id": str(uuid.uuid4()), "started_at": started, "completed_at": _now()},
        "redaction_mode": redaction_mode,
        "targets": targets,
    }
    schema.validate_report(report)
    return report

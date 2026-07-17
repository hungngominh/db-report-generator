"""Orchestrate per-target collection into a schema-valid report_data.json."""
import re
import uuid
from datetime import datetime, timezone

from scripts import capabilities, collectors
from scripts.lib import db, schema
from scripts.lib.envparse import DbConfig

TOOL_VERSION = "4.0.0"

# libpq embeds the RESOLVED address in connection errors, e.g.
#   connection to server at "db.prod.internal" (10.20.30.40), port 5432 failed
# so scrubbing cfg.host alone still leaks the real IP — strip address literals too.
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
_IPV6_RE = re.compile(r"(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scrub(message: str, cfg: DbConfig) -> str:
    out = message
    for secret in (cfg.password, cfg.host, cfg.user):
        if secret:
            out = out.replace(secret, "«redacted»")
    out = _IPV4_RE.sub("«addr»", out)
    out = _IPV6_RE.sub("«addr»", out)
    return out


def _collection_status(diagnostics: dict) -> str:
    if any(d.get("status") == "error" for d in diagnostics.values()):
        return "partial"
    return "ok"


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
            target["diagnostics"] = collectors.run_collectors(conn, target["capabilities"])
            target["collection_status"] = _collection_status(target["diagnostics"])
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

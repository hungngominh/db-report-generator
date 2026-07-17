"""Orchestrate per-target collection into a schema-valid report_data.json."""
import concurrent.futures
import re
import time
import uuid
import warnings
from datetime import datetime, timezone

from scripts import capabilities, collectors, sampler
from scripts.lib import db, schema
from scripts.lib.envparse import DbConfig

TOOL_VERSION = "4.0.0"

_MAX_WORKERS = 8
_LATENCY_WARNING_RATIO = 0.8  # elapsed > 80% of the fully-serial sum -> parallelism isn't bounding runtime


def _check_latency_budget(targets: list, elapsed_seconds: float) -> None:
    """Spec §0.B4: warn if multi-target sampling isn't actually bounded —
    i.e. total elapsed time is suspiciously close to what a fully serial
    N x window_seconds run would take.
    """
    total_window = sum((t.get("sampling") or {}).get("window_seconds", 0) for t in targets)
    if len(targets) > 1 and total_window > 0 and elapsed_seconds > total_window * _LATENCY_WARNING_RATIO:
        warnings.warn(
            f"multi-target sampling took {elapsed_seconds:.1f}s for {len(targets)} targets "
            f"(sum of window_seconds={total_window}s) — runtime is not bounded, check concurrency",
            RuntimeWarning,
        )

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
        "diagnostics": {},
        "sampling": None,
    }
    try:
        conn = db.connect(cfg)
        try:
            target["capabilities"] = capabilities.probe(conn)
            pgss = target["capabilities"].get("extensions", {}).get("pg_stat_statements")
            sampling_result = None
            if pgss:
                sampling_result = sampler.sample_pg_stat_statements_window(
                    conn, pgss["schema"], cfg.sampling_window_seconds)
                target["sampling"] = {
                    "window_seconds": sampling_result["window_seconds"],
                    "sample1_at": sampling_result["sample1_at"],
                    "sample2_at": sampling_result["sample2_at"],
                    "reset_detected": sampling_result["reset_detected"],
                }
            target["diagnostics"] = collectors.run_collectors(
                conn, target["capabilities"], sampling=sampling_result)
            target["collection_status"] = _collection_status(target["diagnostics"])
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - isolate per-target failure
        target["collection_status"] = "error"
        target["error"] = _scrub(str(exc), cfg)
    return target


def analyze(configs, *, redaction_mode: str = "redact") -> dict:
    started = _now()
    t0 = time.monotonic()
    if len(configs) <= 1:
        targets = [_analyze_target(cfg) for cfg in configs]
    else:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(_MAX_WORKERS, len(configs))) as pool:
            targets = list(pool.map(_analyze_target, configs))
    _check_latency_budget(targets, time.monotonic() - t0)
    report = {
        "schema_version": "4.0",
        "tool_version": TOOL_VERSION,
        "run": {"run_id": str(uuid.uuid4()), "started_at": started, "completed_at": _now()},
        "redaction_mode": redaction_mode,
        "targets": targets,
    }
    schema.validate_report(report)
    return report

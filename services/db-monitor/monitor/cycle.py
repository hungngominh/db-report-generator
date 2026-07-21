"""One sampling cycle: connect to the target, probe capabilities, run one
tier's collectors, batch-write the results to the storage DB."""
from datetime import datetime, timezone

from scripts import capabilities, sampler
from scripts.collectors import run_collectors
from scripts.lib import db as target_db
from scripts.lib.envparse import DbConfig

from monitor import tiers
from storage import db as storage_db

_APP_NAME = "db-monitor"


def _to_db_config(cfg) -> DbConfig:
    return DbConfig(
        host=cfg.target_host, port=cfg.target_port, database=cfg.target_db,
        user=cfg.target_user, password=cfg.target_password,
    )


def run_cycle(cfg, tier, collector_names, target_id, *, sampling_window_seconds=None) -> dict:
    """Run one cycle for `tier`, writing results to the storage DB.

    Opens and closes its own target-DB connection and its own storage-DB
    connection -- psycopg2 connections aren't safe to share across threads,
    and the light/heavy tiers run on independent timers/threads.
    """
    conn = target_db.connect(_to_db_config(cfg))
    try:
        with conn.cursor() as cur:
            cur.execute("SET application_name = %s", (_APP_NAME,))
        caps = capabilities.probe(conn)
        sampling_result = None
        if sampling_window_seconds is not None:
            pgss = caps.get("extensions", {}).get("pg_stat_statements")
            if pgss:
                try:
                    sampling_result = sampler.sample_pg_stat_statements_window(
                        conn, pgss["schema"], sampling_window_seconds)
                except Exception:  # noqa: BLE001 - isolate sampler failure from collectors
                    sampling_result = None
        registry = tiers.build_registry(collector_names)
        diagnostics = run_collectors(conn, caps, registry, sampling=sampling_result)
    finally:
        conn.close()

    collected_at = datetime.now(timezone.utc)
    storage_conn = storage_db.connect(cfg.storage_dsn)
    try:
        storage_db.insert_samples(storage_conn, target_id, tier, collected_at, diagnostics)
    finally:
        storage_conn.close()
    return diagnostics

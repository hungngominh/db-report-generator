"""Entrypoint: seed the target row, start light/heavy tier loops on daemon threads."""
import logging
import threading

from monitor import config as config_mod
from monitor import retention, scheduler, tiers
from storage import db as storage_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("db-monitor")


def _heavy_after_cycle(cfg, retention_state):
    retention_state["last_retention_date"] = retention.maybe_run_retention(
        cfg, retention_state["last_retention_date"])


def main():
    cfg = config_mod.load_config()

    conn = storage_db.connect(cfg.storage_dsn)
    try:
        storage_db.init_schema(conn)
        target_id = storage_db.ensure_target(conn, cfg.target_name)
    finally:
        conn.close()

    logger.info("db-monitor starting for target=%s", cfg.target_name)

    light_thread = threading.Thread(
        target=scheduler.run_tier_loop,
        args=(cfg, "light", tiers.LIGHT_COLLECTOR_NAMES, target_id, cfg.light_interval_seconds),
        kwargs={"sampling_window_seconds": 30},
        daemon=True, name="light-tier",
    )

    retention_state = {"last_retention_date": None}
    heavy_thread = threading.Thread(
        target=scheduler.run_tier_loop,
        args=(cfg, "heavy", tiers.HEAVY_COLLECTOR_NAMES, target_id, cfg.heavy_interval_seconds),
        kwargs={"after_cycle_fn": lambda: _heavy_after_cycle(cfg, retention_state)},
        daemon=True, name="heavy-tier",
    )

    light_thread.start()
    heavy_thread.start()
    light_thread.join()
    heavy_thread.join()


if __name__ == "__main__":
    main()

from monitor import cycle
from monitor.config import MonitorConfig
from storage import db as storage_db


def _build_cfg(target_dsn_kwargs, storage_dsn_url):
    return MonitorConfig(
        target_host=target_dsn_kwargs["host"],
        target_port=target_dsn_kwargs["port"],
        target_db=target_dsn_kwargs["dbname"],
        target_user=target_dsn_kwargs["user"],
        target_password=target_dsn_kwargs["password"],
        target_name="test-target",
        storage_dsn=storage_dsn_url,
    )


def test_run_cycle_writes_samples_for_requested_collectors(target_dsn_kwargs, storage_dsn_url):
    cfg = _build_cfg(target_dsn_kwargs, storage_dsn_url)

    storage_conn = storage_db.connect(cfg.storage_dsn)
    storage_db.init_schema(storage_conn)
    target_id = storage_db.ensure_target(storage_conn, cfg.target_name)
    storage_conn.close()

    diagnostics = cycle.run_cycle(cfg, "light", ["connection_depth"], target_id)

    assert "connection_depth" in diagnostics
    assert diagnostics["connection_depth"]["status"] == "ok"

    verify_conn = storage_db.connect(cfg.storage_dsn)
    with verify_conn.cursor() as cur:
        cur.execute(
            "SELECT collector, tier FROM samples WHERE target_id = %s", (target_id,))
        rows = cur.fetchall()
    verify_conn.close()

    assert rows == [("connection_depth", "light")]

from datetime import date

from monitor import config as config_mod
from monitor import main as main_mod
from monitor import scheduler, tiers


class _FakeThread:
    instances = []

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.name = name
        self.started = False
        self.joined = False
        _FakeThread.instances.append(self)

    def start(self):
        self.started = True

    def join(self):
        self.joined = True


class _FakeStorageConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_main_wires_light_and_heavy_tier_threads(monkeypatch):
    _FakeThread.instances = []
    monkeypatch.setattr(main_mod.threading, "Thread", _FakeThread)

    cfg = config_mod.MonitorConfig(
        target_host="h", target_port=5432, target_db="d", target_user="u",
        target_password="p", target_name="acme", storage_dsn="postgresql://x",
        light_interval_seconds=60, heavy_interval_seconds=1800, retention_days=30,
    )
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg)

    fake_conn = _FakeStorageConn()
    monkeypatch.setattr(main_mod.storage_db, "connect", lambda dsn: fake_conn)
    monkeypatch.setattr(main_mod.storage_db, "init_schema", lambda conn: None)
    monkeypatch.setattr(main_mod.storage_db, "ensure_target", lambda conn, name: 42)

    main_mod.main()

    assert fake_conn.closed
    assert len(_FakeThread.instances) == 2

    light, heavy = _FakeThread.instances
    assert light.name == "light-tier"
    assert light.target is scheduler.run_tier_loop
    assert light.args == (cfg, "light", tiers.LIGHT_COLLECTOR_NAMES, 42, cfg.light_interval_seconds)
    assert light.kwargs == {"sampling_window_seconds": 30}
    assert light.daemon is True
    assert light.started and light.joined

    assert heavy.name == "heavy-tier"
    assert heavy.target is scheduler.run_tier_loop
    assert heavy.args == (cfg, "heavy", tiers.HEAVY_COLLECTOR_NAMES, 42, cfg.heavy_interval_seconds)
    assert callable(heavy.kwargs["after_cycle_fn"])
    assert heavy.daemon is True
    assert heavy.started and heavy.joined


def test_heavy_after_cycle_threads_retention_state(monkeypatch):
    _FakeThread.instances = []
    monkeypatch.setattr(main_mod.threading, "Thread", _FakeThread)

    cfg = config_mod.MonitorConfig(
        target_host="h", target_port=5432, target_db="d", target_user="u",
        target_password="p", target_name="acme", storage_dsn="postgresql://x",
        light_interval_seconds=60, heavy_interval_seconds=1800, retention_days=30,
    )
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg)

    fake_conn = _FakeStorageConn()
    monkeypatch.setattr(main_mod.storage_db, "connect", lambda dsn: fake_conn)
    monkeypatch.setattr(main_mod.storage_db, "init_schema", lambda conn: None)
    monkeypatch.setattr(main_mod.storage_db, "ensure_target", lambda conn, name: 42)

    calls = []
    fake_dates = [date(2026, 1, 1), date(2026, 1, 2)]

    def fake_maybe_run_retention(cfg_arg, last_run_date):
        calls.append(last_run_date)
        return fake_dates[len(calls) - 1]

    monkeypatch.setattr(main_mod.retention, "maybe_run_retention", fake_maybe_run_retention)

    main_mod.main()

    heavy = _FakeThread.instances[1]
    after_cycle_fn = heavy.kwargs["after_cycle_fn"]

    after_cycle_fn()
    after_cycle_fn()

    assert calls == [None, date(2026, 1, 1)]

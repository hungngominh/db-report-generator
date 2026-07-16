# Phase 0a: Connection, Capabilities & Analyzer Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stand up the live-DB pipeline — parse `.env`, connect to PostgreSQL **read-only**, probe capabilities, and have `analyzer.py` emit a schema-valid multi-target `report_data.json` (with empty diagnostics for now) — tested against a Dockerized Postgres. Phase 0b fills in the blocker-fix collectors.

**Architecture:** `envparse.py` reads the v3 JSON `.env` → `DbConfig`. `db.py` opens a **read-only** psycopg2 connection (server-enforced `default_transaction_read_only` — the real safety boundary that `safety.py` is advisory to) with statement/lock timeouts. `capabilities.py` probes version/superuser/roles/extensions/vendor. `analyzer.py` orchestrates per-target connect→probe→assemble, isolates per-target failures, validates against the frozen schema, and returns the report dict.

**Tech Stack:** Python ≥3.10, `psycopg2-binary` (DB driver — locked here per roadmap), `pytest`. Live-DB tests use a throwaway Docker `postgres:16` container, and **skip** when Docker is unavailable.

**Nguồn:** [Spec §4 (capability probing), §5 P0.8, §3.1](../specs/2026-07-16-db-report-generator-v4-upgrade.md) · [Roadmap P0](2026-07-16-db-report-generator-v4-roadmap.md). Builds on Phase −1 (schema, redact, safety — already on `master`).

## Global Constraints

- **Read-only boundary:** every connection is opened read-only (`set_session(readonly=True)`), so the SERVER rejects any write/DDL. This is the real safety boundary; `is_readonly_sql` (P−1) stays an advisory pre-filter. (§0.A3/A6/N4)
- **Determinism:** `analyzer.py` puts wall-clock/uuid only in the `run` metadata branch (`run_id`, `started_at`, `completed_at`); it must NOT put timestamps/random into `capabilities` or `diagnostics`. (§0.A1)
- **Redaction:** never log/emit a full DSN or password; connection-error strings are scrubbed of host+password before they reach `target.error`; the report carries `redaction_mode`. Reuse `scripts/lib/redact.py`. (bảo mật review)
- **Multi-target isolation:** one target failing to connect/probe → `collection_status="error"` with a scrubbed reason; the run continues with other targets. (§0.A5, P7.3)
- **Schema-valid always:** `analyzer.analyze(...)` validates its output against `references/report-data.schema.json` before returning. Empty `diagnostics: {}` is valid. (§0.A5)
- **Enum/vendor values:** `collection_status ∈ {ok, partial, error}`; `vendor ∈ {supabase, rds, aurora, self-hosted, unknown}`; unknown/unreachable env → conservative (`is_superuser=false` assumed only when actually probed false; never fabricate capability). (§4, §0.A4)
- **Location & run convention:** all code under `.agents/skills/db-report-generator/` (SKILL_DIR). pip/pytest from SKILL_DIR; git from repo root. Commit footer:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

## File structure (this phase)

```
.agents/skills/db-report-generator/
├── requirements-dev.txt              # + psycopg2-binary   (Task 0)
├── conftest.py                       # + pg_dsn / pg_conn fixtures (Task 0)
├── tests/
│   ├── pgcontainer.py                # Docker Postgres lifecycle helper (Task 0)
│   └── unit/
│       ├── test_pgcontainer.py       # Task 0
│       ├── test_envparse.py          # Task 1
│       ├── test_db.py                # Task 2 (live-DB)
│       ├── test_capabilities.py      # Task 3 (live-DB)
│       └── test_analyzer.py          # Task 4 (live-DB + error path)
├── scripts/
│   ├── analyzer.py                   # Task 4
│   ├── capabilities.py               # Task 3
│   └── lib/
│       ├── envparse.py               # Task 1
│       └── db.py                     # Task 2
└── references/sample.env             # placeholder fix (Task 5)
```

---

### Task 0: psycopg2 dep + Docker Postgres test harness

**Files:**
- Modify: `SKILL_DIR/requirements-dev.txt`
- Create: `SKILL_DIR/tests/pgcontainer.py`
- Modify: `SKILL_DIR/conftest.py`
- Test: `SKILL_DIR/tests/unit/test_pgcontainer.py`

**Interfaces:**
- Produces: `tests/pgcontainer.py` with `docker_available() -> bool`, `PostgresContainer` (context manager) exposing `.dsn_kwargs` (dict for `psycopg2.connect`) and `.dsn_url` (str). `conftest.py` gains session fixtures `pg_dsn` (dict of connect kwargs, skips if no Docker) and `pg_conn` (a live psycopg2 connection to it). Tasks 2–4 consume these.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_pgcontainer.py`:
```python
import psycopg2
import pytest

from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_pg_fixture_is_live_and_readonly_capable(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run (from SKILL_DIR): `python -m pytest tests/unit/test_pgcontainer.py -q`
Expected: FAIL (`ModuleNotFoundError: tests.pgcontainer`).

- [ ] **Step 3: Add dependency**

Append to `SKILL_DIR/requirements-dev.txt`:
```
psycopg2-binary>=2.9
```
Run: `pip install -r requirements-dev.txt`

- [ ] **Step 4: Write the container helper**

Create `SKILL_DIR/tests/pgcontainer.py`:
```python
"""Throwaway Docker Postgres for live-DB tests. Skips cleanly without Docker."""
import shutil
import socket
import subprocess
import time

import psycopg2


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class PostgresContainer:
    def __init__(self, image: str = "postgres:16"):
        self.image = image
        self.name = None
        self.port = None

    @property
    def dsn_kwargs(self) -> dict:
        return {
            "host": "127.0.0.1", "port": self.port, "dbname": "postgres",
            "user": "postgres", "password": "postgres", "connect_timeout": 10,
        }

    @property
    def dsn_url(self) -> str:
        return f"postgresql://postgres:postgres@127.0.0.1:{self.port}/postgres"

    def __enter__(self):
        self.port = _free_port()
        self.name = f"dbrep-test-{self.port}"
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", self.name,
             "-e", "POSTGRES_PASSWORD=postgres",
             "-p", f"{self.port}:5432", self.image],
            check=True, capture_output=True,
        )
        self._wait_ready()
        return self

    def _wait_ready(self, timeout: float = 60.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                conn = psycopg2.connect(**self.dsn_kwargs)
                conn.close()
                return
            except Exception as e:  # noqa: BLE001 - retry until ready
                last = e
                time.sleep(0.5)
        raise RuntimeError(f"postgres container not ready in {timeout}s: {last}")

    def __exit__(self, *exc):
        if self.name:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
```

- [ ] **Step 5: Add fixtures to conftest.py**

Append to `SKILL_DIR/conftest.py`:
```python
@pytest.fixture(scope="session")
def _pg_container():
    from tests.pgcontainer import PostgresContainer, docker_available

    if not docker_available():
        pytest.skip("docker not available")
    with PostgresContainer() as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_dsn(_pg_container) -> dict:
    return _pg_container.dsn_kwargs


@pytest.fixture(scope="session")
def pg_dsn_url(_pg_container) -> str:
    return _pg_container.dsn_url
```

- [ ] **Step 6: Run to verify it passes (or skips without Docker)**

Run: `python -m pytest tests/unit/test_pgcontainer.py -q`
Expected: PASS (1 passed) with Docker; SKIP (1 skipped) without. First run may take ~30–60s to pull `postgres:16`.

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/db-report-generator/{requirements-dev.txt,conftest.py,tests/pgcontainer.py,tests/unit/test_pgcontainer.py}
git commit -m "test(p0a): docker postgres fixture for live-DB tests" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 1: `.env` parser

**Files:**
- Create: `SKILL_DIR/scripts/lib/envparse.py`
- Test: `SKILL_DIR/tests/unit/test_envparse.py`

**Interfaces:**
- Produces: `DbConfig` dataclass (`host, port, database, user, password, project_name, code_path, raw`) and `parse_env(source) -> DbConfig` (accepts a JSON string or a `pathlib.Path`). Field mapping: `ServerName→host`, `Port→port`, `CatalogName→database`, `Username→user`, `Password→password`, `ProjectName→project_name`, `CodePath→code_path`. Missing required key → `ValueError`. Consumed by `db.py` and `analyzer.py`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_envparse.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_envparse.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

Create `SKILL_DIR/scripts/lib/envparse.py`:
```python
"""Parse the v3 JSON `.env` config into a typed DbConfig."""
import json
from dataclasses import dataclass, field
from pathlib import Path

_REQUIRED = ("ServerName", "CatalogName", "Username", "Password")


@dataclass
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    project_name: str = ""
    code_path: str = ""
    raw: dict = field(default_factory=dict)


def parse_env(source) -> DbConfig:
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    data = json.loads(text)
    missing = [k for k in _REQUIRED if k not in data or data[k] in (None, "")]
    if missing:
        raise ValueError(f".env missing required keys: {', '.join(missing)}")
    return DbConfig(
        host=str(data["ServerName"]),
        port=int(data.get("Port", 5432)),
        database=str(data["CatalogName"]),
        user=str(data["Username"]),
        password=str(data["Password"]),
        project_name=str(data.get("ProjectName", "")),
        code_path=str(data.get("CodePath", "")),
        raw=data,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_envparse.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/envparse.py,tests/unit/test_envparse.py}
git commit -m "feat(p0a): .env JSON parser -> DbConfig" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Read-only connection helper

**Files:**
- Create: `SKILL_DIR/scripts/lib/db.py`
- Test: `SKILL_DIR/tests/unit/test_db.py`

**Interfaces:**
- Consumes: `DbConfig` (Task 1), `scripts.lib.redact.redact_dsn` (P−1), `pg_dsn` fixture (Task 0).
- Produces: `connect(cfg, *, statement_timeout_ms=15000, lock_timeout_ms=3000) -> psycopg2.connection` (read-only session, timeouts set); `logging_dsn(cfg) -> str` (redacted). `analyzer.py` consumes `connect`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_db.py`:
```python
import psycopg2
import pytest

from scripts.lib.db import connect, logging_dsn
from scripts.lib.envparse import DbConfig
from tests.pgcontainer import docker_available


def _cfg_from_dsn_kwargs(kw) -> DbConfig:
    return DbConfig(host=kw["host"], port=kw["port"], database=kw["dbname"],
                    user=kw["user"], password=kw["password"], project_name="t")


def test_logging_dsn_is_redacted():
    cfg = DbConfig(host="db.internal.example", port=5432, database="prod",
                   user="app", password="s3cr3t", project_name="p")
    out = logging_dsn(cfg)
    assert "s3cr3t" not in out
    assert "db.internal.example" not in out


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_connect_runs_select(pg_dsn):
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 42")
            assert cur.fetchone()[0] == 42
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_connection_is_read_only(pg_dsn):
    # The server must REJECT writes — this is the real safety boundary.
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn))
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TABLE should_not_exist (x int)")
    finally:
        conn.close()


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_statement_timeout_is_set(pg_dsn):
    conn = connect(_cfg_from_dsn_kwargs(pg_dsn), statement_timeout_ms=1234)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "1234ms"
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_db.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

Create `SKILL_DIR/scripts/lib/db.py`:
```python
"""Read-only PostgreSQL connection helper (server-enforced read-only)."""
import psycopg2

from scripts.lib.envparse import DbConfig
from scripts.lib.redact import redact_dsn

DEFAULT_STATEMENT_TIMEOUT_MS = 15000
DEFAULT_LOCK_TIMEOUT_MS = 3000
_APP_NAME = "db-report-generator"


def connect(cfg: DbConfig, *, statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
            lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS):
    conn = psycopg2.connect(
        host=cfg.host, port=cfg.port, dbname=cfg.database,
        user=cfg.user, password=cfg.password,
        connect_timeout=10, application_name=_APP_NAME,
    )
    # Server-enforced read-only + autocommit: every statement runs in a
    # read-only transaction, so writes/DDL are rejected by the server.
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (int(statement_timeout_ms),))
        cur.execute("SET lock_timeout = %s", (int(lock_timeout_ms),))
    return conn


def logging_dsn(cfg: DbConfig) -> str:
    """A redacted DSN safe for logs (no password, no host)."""
    return redact_dsn(f"postgresql://{cfg.user}:x@{cfg.host}:{cfg.port}/{cfg.database}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_db.py -q`
Expected: PASS (4 passed) with Docker; the redaction test always runs, the 3 live tests skip without Docker.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/db.py,tests/unit/test_db.py}
git commit -m "feat(p0a): read-only psycopg2 connection helper + timeouts" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Capability probing

**Files:**
- Create: `SKILL_DIR/scripts/capabilities.py`
- Test: `SKILL_DIR/tests/unit/test_capabilities.py`

**Interfaces:**
- Consumes: a live read-only connection (`db.connect`), `pg_conn`/`pg_dsn` fixtures.
- Produces: `probe(conn) -> dict` with keys `server_version_num` (int), `is_superuser` (bool), `has_pg_read_all_stats` (bool), `has_pg_monitor` (bool), `vendor` (str enum), `managed` (bool), `extensions` (dict name→{present,schema}), `ram_bytes` (int|None). Consumed by `analyzer.py`; refined in later phases.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_capabilities.py`:
```python
import psycopg2
import pytest

from scripts.capabilities import probe
from tests.pgcontainer import docker_available


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_shape_and_values(pg_dsn):
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    assert caps["server_version_num"] >= 140000
    assert caps["is_superuser"] is True          # 'postgres' superuser in the container
    assert caps["vendor"] == "self-hosted"       # plain container, no cloud roles
    assert caps["managed"] is False
    assert "plpgsql" in caps["extensions"]        # default extension
    assert set(["server_version_num", "is_superuser", "has_pg_read_all_stats",
                "has_pg_monitor", "vendor", "managed", "extensions", "ram_bytes"]) <= set(caps)


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_probe_is_json_serializable(pg_dsn):
    import json
    conn = psycopg2.connect(**pg_dsn)
    try:
        caps = probe(conn)
    finally:
        conn.close()
    json.dumps(caps)  # must not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_capabilities.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

Create `SKILL_DIR/scripts/capabilities.py`:
```python
"""Probe DB version / privileges / vendor / extensions before collectors run (spec §4)."""

_CLOUD_ROLES = ("supabase_admin", "authenticator", "rds_superuser", "rdsadmin")


def _scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def _vendor(roles: set) -> str:
    if {"supabase_admin", "authenticator"} & roles:
        return "supabase"
    if {"rds_superuser", "rdsadmin"} & roles:
        return "rds"  # aurora shares rds roles; refined in a later phase
    return "self-hosted"


def probe(conn) -> dict:
    with conn.cursor() as cur:
        server_version_num = int(_scalar(cur, "SELECT current_setting('server_version_num')::int"))
        is_superuser = bool(_scalar(cur, "SELECT current_setting('is_superuser') = 'on'"))
        has_read_all = bool(_scalar(
            cur, "SELECT pg_catalog.pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')"))
        has_monitor = bool(_scalar(
            cur, "SELECT pg_catalog.pg_has_role(current_user, 'pg_monitor', 'USAGE')"))
        cur.execute(
            "SELECT extname, extnamespace::regnamespace::text FROM pg_extension ORDER BY extname")
        extensions = {name: {"present": True, "schema": schema} for name, schema in cur.fetchall()}
        cur.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(_CLOUD_ROLES),))
        roles = {r[0] for r in cur.fetchall()}

    vendor = _vendor(roles)
    return {
        "server_version_num": server_version_num,
        "is_superuser": is_superuser,
        "has_pg_read_all_stats": has_read_all,
        "has_pg_monitor": has_monitor,
        "vendor": vendor,
        "managed": vendor in ("supabase", "rds", "aurora"),
        "extensions": extensions,
        "ram_bytes": None,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_capabilities.py -q`
Expected: PASS (2 passed) with Docker; skip without.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/capabilities.py,tests/unit/test_capabilities.py}
git commit -m "feat(p0a): capability probing (version/superuser/roles/vendor/extensions)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Analyzer orchestrator (multi-target, schema-valid)

**Files:**
- Create: `SKILL_DIR/scripts/analyzer.py`
- Test: `SKILL_DIR/tests/unit/test_analyzer.py`

**Interfaces:**
- Consumes: `DbConfig` list, `db.connect`, `capabilities.probe`, `scripts.lib.schema.validate_report`, `scripts.lib.redact`.
- Produces: `analyze(configs, *, redaction_mode="redact") -> dict` — a schema-valid `report_data.json` with one target per config, each `collection_status` ok/error, `capabilities` filled on success, `diagnostics = {}` (collectors arrive in P0b). Per-target exceptions are caught, scrubbed, and recorded as `error` without aborting the run. Also `TOOL_VERSION`.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_analyzer.py`:
```python
import pytest

from scripts.analyzer import analyze
from scripts.lib.envparse import DbConfig
from scripts.lib.schema import validation_errors
from tests.pgcontainer import docker_available


def _good(pg_dsn) -> DbConfig:
    return DbConfig(host=pg_dsn["host"], port=pg_dsn["port"], database=pg_dsn["dbname"],
                    user=pg_dsn["user"], password=pg_dsn["password"], project_name="good")


def _bad() -> DbConfig:
    return DbConfig(host="127.0.0.1", port=1, database="nope",
                    user="nobody", password="s3cr3t-nope", project_name="bad")


def test_analyze_output_is_schema_valid_and_isolates_failures(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn), _bad()])
    assert validation_errors(report) == []
    by_id = {t["target_id"]: t for t in report["targets"]}
    assert by_id["good"]["collection_status"] == "ok"
    assert by_id["good"]["capabilities"]["server_version_num"] >= 140000
    assert by_id["good"]["diagnostics"] == {}
    # one dead target does not kill the run
    assert by_id["bad"]["collection_status"] == "error"
    assert by_id["bad"]["error"]


def test_error_message_is_scrubbed_of_password(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_bad()])
    err = report["targets"][0]["error"]
    assert "s3cr3t-nope" not in err


def test_metadata_present_but_no_time_in_diagnostics(pg_dsn):
    if not docker_available():
        pytest.skip("docker not available")
    report = analyze([_good(pg_dsn)])
    assert report["schema_version"] == "4.0"
    assert report["run"]["run_id"]
    # capabilities/diagnostics carry no timestamp keys
    caps = report["targets"][0]["capabilities"]
    assert not any("_at" in k or k in ("timestamp", "now") for k in caps)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_analyzer.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

Create `SKILL_DIR/scripts/analyzer.py`:
```python
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
    for secret in (cfg.password, cfg.host):
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_analyzer.py -q`
Expected: PASS (3 passed) with Docker; skip without.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/analyzer.py,tests/unit/test_analyzer.py}
git commit -m "feat(p0a): analyzer skeleton — multi-target, isolated, schema-valid" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Sanitize `sample.env` (P0.8 security)

**Files:**
- Modify: `SKILL_DIR/references/sample.env`
- Test: `SKILL_DIR/tests/unit/test_sample_env.py`

**Interfaces:**
- Produces: a `sample.env` with a placeholder host (no real IP) that still `parse_env`s cleanly.

- [ ] **Step 1: Write the failing test**

Create `SKILL_DIR/tests/unit/test_sample_env.py`:
```python
import re
from pathlib import Path

from scripts.lib.envparse import parse_env

SAMPLE = Path(__file__).resolve().parents[2] / "references" / "sample.env"


def test_sample_env_has_no_real_ip_or_secret():
    text = SAMPLE.read_text(encoding="utf-8")
    # no bare IPv4 literal
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), "sample.env must not contain a real IP"
    assert "your_password_here" in text or "changeme" in text


def test_sample_env_still_parses():
    cfg = parse_env(SAMPLE)
    assert cfg.host and cfg.database and cfg.user
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_sample_env.py -q`
Expected: FAIL (the current file still contains a real IPv4 literal as `ServerName`).

- [ ] **Step 3: Replace the file with a placeholder version**

Overwrite `SKILL_DIR/references/sample.env`:
```json
{
  "ServerName": "your-db-host.example",
  "CatalogName": "MyDatabase",
  "Username": "readonly_user",
  "Password": "your_password_here",
  "Port": 5432,
  "MaxPoolSize": 500,
  "CodePath": "D:/Projects/MyApp",
  "ProjectName": "My Application",
  "CodeLanguage": "csharp",
  "Framework": "dotnet"
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_sample_env.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{references/sample.env,tests/unit/test_sample_env.py}
git commit -m "fix(p0a): remove real IP from sample.env (P0.8), add guard test" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Acceptance Gate (Phase 0a)

- [ ] `python -m pytest -q` green (live-DB tests pass with Docker, skip cleanly without).
- [ ] Connection is server-enforced read-only (a `CREATE TABLE` raises `ReadOnlySqlTransaction`).
- [ ] `capabilities.probe` returns the documented shape and is JSON-serializable.
- [ ] `analyze([good, bad])` returns a schema-valid multi-target report; the bad target is `error`, the good one `ok` with capabilities; error text carries no password.
- [ ] `sample.env` has no real IP and still parses.

## Self-Review notes (đã kiểm)

- **Spec coverage P0a:** §4 capability probing ✓ (Task 3); §3.1 multi-target report + schema-valid ✓ (Task 4); §0.A5 isolation ✓; P0.8 sample.env ✓ (Task 5); read-only boundary (§0.A3/A6) ✓ (Task 2). Driver locked = psycopg2 (roadmap).
- **Type consistency:** `analyzer` uses `db.connect`, `capabilities.probe`, `schema.validate_report`, `DbConfig` fields exactly as defined in Tasks 1–3.
- **Out of scope (later):** blocker-fix collectors (P0b); RAM detection, richer vendor/aurora split, `.env` v4 optional fields (`SamplingWindowSeconds`, `ExplainMode`) — P1/P4; README/setup honesty (P0.7) → P7; remediation-gate framing (P0.6) → naturally satisfied (no remediation output yet), revisited in P6.

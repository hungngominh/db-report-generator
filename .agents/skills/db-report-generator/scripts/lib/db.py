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

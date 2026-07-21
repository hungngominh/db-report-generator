"""Storage-DB helpers: schema init, target seeding, batch sample insert, retention delete."""
import json
from pathlib import Path

import psycopg2

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(dsn):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def init_schema(conn):
    with conn.cursor() as cur:
        cur.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))


def ensure_target(conn, name) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO targets (name) VALUES (%s) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
            "RETURNING id",
            (name,),
        )
        return cur.fetchone()[0]


def insert_samples(conn, target_id, tier, collected_at, diagnostics: dict) -> None:
    rows = [
        (target_id, collector, tier, collected_at, json.dumps(payload))
        for collector, payload in diagnostics.items()
    ]
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO samples (target_id, collector, tier, collected_at, payload) "
            "VALUES (%s, %s, %s, %s, %s::jsonb)",
            rows,
        )


def delete_old_samples(conn, retention_days) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM samples WHERE collected_at < now() - make_interval(days => %s)",
            (retention_days,),
        )
        return cur.rowcount

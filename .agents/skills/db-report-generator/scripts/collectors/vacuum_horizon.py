"""P2.11 — what's pinning the vacuum horizon: long-running backends + prepared transactions."""
from scripts.collectors import base

_BACKEND_SQL = """
SELECT pid, usename, state, age(backend_xmin),
       EXTRACT(EPOCH FROM (now() - xact_start))
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL AND datname = current_database()
ORDER BY age(backend_xmin) DESC
LIMIT 20
"""

_PREPARED_SQL = """
SELECT gid, owner, age(transaction)
FROM pg_prepared_xacts
WHERE database = current_database()
ORDER BY age(transaction) DESC
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_BACKEND_SQL)
        backend_rows = cur.fetchall()
        cur.execute(_PREPARED_SQL)
        prepared_rows = cur.fetchall()

    metrics = [
        {"level": "backend", "pid": r[0], "usename": r[1], "state": r[2],
         "xmin_age": r[3], "xact_age_seconds": r[4]}
        for r in backend_rows
    ] + [
        {"level": "prepared_xact", "gid": r[0], "owner": r[1], "xid_age": r[2]}
        for r in prepared_rows
    ]
    return base.diagnostic("database", "ok", metrics)

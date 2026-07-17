"""P2.9 — replication slots + standby lag. Empty results are a legitimate healthy state."""
from scripts.collectors import base

_SLOTS_SQL = """
SELECT slot_name, slot_type, active, wal_status,
       CASE WHEN pg_is_in_recovery() THEN NULL
            ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
       END::bigint AS retained_wal_bytes
FROM pg_replication_slots
"""

_STANDBY_SQL = """
SELECT application_name, state,
       pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint AS replay_lag_bytes
FROM pg_stat_replication
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_SLOTS_SQL)
        slot_rows = cur.fetchall()
        cur.execute(_STANDBY_SQL)
        standby_rows = cur.fetchall()

    metrics = [
        {"level": "slot", "slot_name": r[0], "slot_type": r[1], "active": r[2],
         "wal_status": r[3], "retained_wal_bytes": r[4]}
        for r in slot_rows
    ] + [
        {"level": "standby", "application_name": r[0], "state": r[1], "replay_lag_bytes": r[2]}
        for r in standby_rows
    ]
    return base.diagnostic("cluster", "ok", metrics)

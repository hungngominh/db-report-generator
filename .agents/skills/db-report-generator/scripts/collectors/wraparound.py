"""P2.1 — XID/MultiXact wraparound relative to autovacuum_freeze_max_age/failsafe_age."""
from scripts.collectors import base

_GUC_SQL = """
SELECT current_setting('autovacuum_freeze_max_age')::bigint,
       current_setting('autovacuum_multixact_freeze_max_age')::bigint
"""

_FAILSAFE_SQL = """
SELECT current_setting('vacuum_failsafe_age')::bigint,
       current_setting('vacuum_multixact_failsafe_age')::bigint
"""

_DATABASE_SQL = """
SELECT datname, age(datfrozenxid) AS xid_age, age(datminmxid) AS mxid_age
FROM pg_database
WHERE datallowconn
ORDER BY age(datfrozenxid) DESC
"""

_TABLE_SQL = """
SELECT n.nspname, c.relname, age(c.relfrozenxid) AS xid_age, age(c.relminmxid) AS mxid_age
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 20
"""


def collect(conn, caps):
    with conn.cursor() as cur:
        cur.execute(_GUC_SQL)
        freeze_max_age, multixact_freeze_max_age = cur.fetchone()

        failsafe_age = multixact_failsafe_age = None
        if caps.get("server_version_num", 0) >= 140000:
            cur.execute(_FAILSAFE_SQL)
            failsafe_age, multixact_failsafe_age = cur.fetchone()

        cur.execute(_DATABASE_SQL)
        db_rows = cur.fetchall()
        cur.execute(_TABLE_SQL)
        table_rows = cur.fetchall()

    thresholds = {
        "autovacuum_freeze_max_age": freeze_max_age,
        "autovacuum_multixact_freeze_max_age": multixact_freeze_max_age,
        "vacuum_failsafe_age": failsafe_age,
        "vacuum_multixact_failsafe_age": multixact_failsafe_age,
    }
    metrics = [
        {"level": "database", "datname": row[0], "xid_age": row[1], "mxid_age": row[2], **thresholds}
        for row in db_rows
    ] + [
        {"level": "table", "schema": row[0], "table": row[1], "xid_age": row[2], "mxid_age": row[3],
         **thresholds}
        for row in table_rows
    ]
    return base.diagnostic("database", "ok", metrics)

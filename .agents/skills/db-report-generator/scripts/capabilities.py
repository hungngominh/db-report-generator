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
        track_io_timing = bool(_scalar(cur, "SELECT current_setting('track_io_timing') = 'on'"))
        pg_stat_statements_track = _scalar(
            cur, "SELECT current_setting('pg_stat_statements.track', true)")
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
        "track_io_timing": track_io_timing,
        "pg_stat_statements_track": pg_stat_statements_track,
        "vendor": vendor,
        "managed": vendor in ("supabase", "rds", "aurora"),
        "extensions": extensions,
        "ram_bytes": None,
    }

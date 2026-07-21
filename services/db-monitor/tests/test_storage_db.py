from storage import db as storage_db


def test_init_schema_and_ensure_target_is_idempotent(storage_dsn_url):
    conn = storage_db.connect(storage_dsn_url)
    storage_db.init_schema(conn)

    id1 = storage_db.ensure_target(conn, "acme-prod")
    id2 = storage_db.ensure_target(conn, "acme-prod")

    assert id1 == id2

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM targets WHERE name = 'acme-prod'")
        assert cur.fetchone()[0] == 1
    conn.close()


def test_insert_samples_writes_one_row_per_collector(storage_dsn_url):
    conn = storage_db.connect(storage_dsn_url)
    storage_db.init_schema(conn)
    target_id = storage_db.ensure_target(conn, "acme-prod")

    from datetime import datetime, timezone
    collected_at = datetime.now(timezone.utc)
    diagnostics = {
        "connection_depth": {"status": "ok", "metrics": [{"db_connections": 3}]},
        "database_stats": {"status": "ok", "metrics": [{"size_bytes": 1024}]},
    }
    storage_db.insert_samples(conn, target_id, "light", collected_at, diagnostics)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT collector, tier, payload FROM samples WHERE target_id = %s ORDER BY collector",
            (target_id,),
        )
        rows = cur.fetchall()
    conn.close()

    assert [r[0] for r in rows] == ["connection_depth", "database_stats"]
    assert all(r[1] == "light" for r in rows)
    assert rows[0][2] == {"status": "ok", "metrics": [{"db_connections": 3}]}


def test_delete_old_samples_removes_rows_past_retention(storage_dsn_url):
    conn = storage_db.connect(storage_dsn_url)
    storage_db.init_schema(conn)
    target_id = storage_db.ensure_target(conn, "acme-prod")

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO samples (target_id, collector, tier, collected_at, payload) "
            "VALUES (%s, 'connection_depth', 'light', now() - interval '40 days', '{}'::jsonb)",
            (target_id,),
        )
        cur.execute(
            "INSERT INTO samples (target_id, collector, tier, collected_at, payload) "
            "VALUES (%s, 'connection_depth', 'light', now(), '{}'::jsonb)",
            (target_id,),
        )

    deleted = storage_db.delete_old_samples(conn, 30)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM samples WHERE target_id = %s", (target_id,))
        remaining = cur.fetchone()[0]
    conn.close()

    assert deleted == 1
    assert remaining == 1

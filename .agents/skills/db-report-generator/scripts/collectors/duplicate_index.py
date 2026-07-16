"""P0.3 — exact-duplicate and prefix-redundant indexes (constraint-safe)."""
from collections import defaultdict

from scripts.collectors import base

# indnullsnotdistinct exists only on PG15+; select conditionally.
_SQL = """
SELECT rel.oid AS table_oid, ns.nspname AS schema, rel.relname AS tbl,
       ic.relname AS index_name, am.amname,
       i.indnkeyatts, i.indkey::text, i.indclass::text, i.indcollation::text,
       i.indoption::text,
       COALESCE(pg_get_expr(i.indexprs, i.indrelid), '') AS exprs,
       COALESCE(i.indpred::text, '') AS pred,
       {nnd} AS nnd,
       i.indisprimary, i.indisunique, i.indisexclusion
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class rel ON rel.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
JOIN pg_am am ON am.oid = ic.relam
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
  AND i.indisvalid
ORDER BY schema, tbl, index_name
"""


def _rows(conn, caps):
    nnd = "i.indnullsnotdistinct" if caps.get("server_version_num", 0) >= 150000 else "false"
    with conn.cursor() as cur:
        cur.execute(_SQL.format(nnd=nnd))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _signature(r):
    return (r["table_oid"], r["amname"], r["indnkeyatts"], r["indkey"],
            r["indclass"], r["indcollation"], r["indoption"], r["exprs"],
            r["pred"], r["nnd"])


def _key_desc(r):
    # per key column: (attnum, opclass, collation, option) — excludes INCLUDE cols
    n = r["indnkeyatts"]
    keys = r["indkey"].split()[:n]
    classes = r["indclass"].split()[:n]
    colls = r["indcollation"].split()[:n]
    opts = r["indoption"].split()[:n]
    return tuple(zip(keys, classes, colls, opts))


def collect(conn, caps):
    rows = _rows(conn, caps)
    metrics = []

    # --- exact duplicates: group by full signature ---
    groups = defaultdict(list)
    for r in rows:
        groups[_signature(r)].append(r)
    for members in groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (
            not r["indisprimary"], not r["indisunique"],
            not r["indisexclusion"], r["index_name"]))
        keep = ordered[0]
        drop_candidates = [m["index_name"] for m in ordered[1:]
                           if not (m["indisprimary"] or m["indisunique"]
                                   or m["indisexclusion"])]
        metrics.append({
            "kind": "exact_duplicate",
            "schema": keep["schema"], "table": keep["tbl"],
            "keep": keep["index_name"],
            "members": sorted(m["index_name"] for m in members),
            "drop_candidates": sorted(drop_candidates),
        })

    # --- prefix redundancy: plain btree, A's key cols strict prefix of B's ---
    plain = [r for r in rows
             if r["amname"] == "btree" and not r["exprs"] and not r["pred"]
             and not r["indisprimary"] and not r["indisunique"]
             and not r["indisexclusion"]]
    by_table = defaultdict(list)
    for r in plain:
        by_table[r["table_oid"]].append(r)
    for group in by_table.values():
        for a in group:
            ka = _key_desc(a)
            for b in group:
                if a["index_name"] == b["index_name"]:
                    continue
                kb = _key_desc(b)
                if len(ka) < len(kb) and kb[: len(ka)] == ka:
                    metrics.append({
                        "kind": "potentially_redundant",
                        "schema": a["schema"], "table": a["tbl"],
                        "redundant": a["index_name"], "covered_by": b["index_name"],
                    })
                    break

    metrics.sort(key=lambda m: (m["kind"], m["schema"], m["table"],
                                m.get("keep") or m.get("redundant") or ""))
    return base.diagnostic("index", "ok", metrics)

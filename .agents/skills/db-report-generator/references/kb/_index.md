# Knowledge Base — PostgreSQL best practices (bundled)

> **Nguồn / Provenance:** Toàn bộ nội dung thư mục này được sao chép từ skill `supabase-postgres-best-practices`
> (Postgres performance & best practices from Supabase) để `db-report-generator` **self-contained** — không còn
> phụ thuộc skill ngoài. Attribution cho Supabase được giữ nguyên trong các footer báo cáo.
>
> Đây là **dữ liệu tham chiếu**, không phải một skill. Solution engine đọc `solution-index.md`; các file body
> được đọc *on-demand* khi cần giải thích hoặc nối detection (v4 — Phase 5 "nối KB thật").

## Mục lục theo nhóm

| Ưu tiên | Nhóm | Impact | Prefix |
|--------:|------|--------|--------|
| 1 | Query Performance | CRITICAL | `query-` |
| 2 | Connection Management | CRITICAL | `conn-` |
| 3 | Security & RLS | CRITICAL | `security-` |
| 4 | Schema Design | HIGH | `schema-` |
| 5 | Concurrency & Locking | MEDIUM-HIGH | `lock-` |
| 6 | Data Access Patterns | MEDIUM | `data-` |
| 7 | Monitoring & Diagnostics | LOW-MEDIUM | `monitor-` |
| 8 | Advanced Features | LOW | `advanced-` |

**Solution Engine:** `solution-index.md` — master mapping 13 problem pattern → fix cụ thể
(SQL template, reference file, priority P0–P3, expected impact).

## Danh sách file (31)

**Query Performance** (`query-`)
- `query-composite-indexes.md`
- `query-covering-indexes.md`
- `query-index-types.md`
- `query-missing-indexes.md`
- `query-partial-indexes.md`

**Connection Management** (`conn-`)
- `conn-idle-timeout.md`
- `conn-limits.md`
- `conn-pooling.md`
- `conn-prepared-statements.md`

**Security & RLS** (`security-`)
- `security-privileges.md`
- `security-rls-basics.md`
- `security-rls-performance.md`

**Schema Design** (`schema-`)
- `schema-data-types.md`
- `schema-foreign-key-indexes.md`
- `schema-lowercase-identifiers.md`
- `schema-partitioning.md`
- `schema-primary-keys.md`

**Concurrency & Locking** (`lock-`)
- `lock-advisory.md`
- `lock-deadlock-prevention.md`
- `lock-short-transactions.md`
- `lock-skip-locked.md`

**Data Access Patterns** (`data-`)
- `data-batch-inserts.md`
- `data-n-plus-one.md`
- `data-pagination.md`
- `data-upsert.md`

**Monitoring & Diagnostics** (`monitor-`)
- `monitor-explain-analyze.md`
- `monitor-pg-stat-statements.md`
- `monitor-vacuum-analyze.md`

**Advanced Features** (`advanced-`)
- `advanced-full-text-search.md`
- `advanced-jsonb-indexing.md`

**Solution Engine**
- `solution-index.md`

---

*30 topic file + 1 solution engine = 31 file. Đồng bộ từ `supabase-postgres-best-practices/references/` ngày 2026-07-16.*

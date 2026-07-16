---
name: db-report-generator
description: Tự động quét tất cả thư mục database trong workspace, kết nối PostgreSQL qua .env, tạo báo cáo tình trạng DB + Code + GIẢI PHÁP PERFORMANCE cụ thể và lưu vào thư mục theo ngày (yyyy-MM-dd). Chẩn đoán vấn đề VÀ kê đơn giải pháp từ code đến DB.
metadata:
  author: NGOMI
  version: "3.0.0"
  date: February 2026
---

# Database & Code Report Generator + Solution Engine

Skill tự động tạo báo cáo tình trạng database PostgreSQL, phân tích code, VÀ đưa ra giải pháp performance cụ thể (ready-to-execute SQL + code fixes) cho tất cả dự án được cấu hình trong workspace.

**v3.0 - Tích hợp Solution Engine (KB đóng gói nội bộ tại `references/kb/`, nguồn: `supabase-postgres-best-practices`)**: Mỗi vấn đề phát hiện được đi kèm giải pháp cụ thể với priority, SQL fix, code fix, và expected impact. Skill **self-contained** — không phụ thuộc skill KB ngoài.

## Ngôn Ngữ Báo Cáo

**BẮT BUỘC: Tất cả báo cáo output PHẢI viết hoàn toàn bằng TIẾNG VIỆT.**

- Tiêu đề sections: tiếng Việt (ví dụ: "Tổng Quan", "Truy Vấn Chậm", "Kích Thước Bảng")
- Nhận xét, đánh giá, khuyến nghị: tiếng Việt
- Tên cột trong bảng: tiếng Việt (ví dụ: "Tên Bảng", "Kích Thước", "Số Dòng", "Thời Gian TB")
- Giữ nguyên tiếng Anh CHỈ cho: tên bảng DB, tên cột DB, tên index, SQL code, code snippets, tên file
- Ký hiệu đánh giá: dùng icon + tiếng Việt (🟢 Tốt, 🟡 Cần cải thiện, 🔴 Nghiêm trọng)

## Khi Nào Sử Dụng

- Khi cần tạo báo cáo tình trạng database hàng ngày
- Khi cần kiểm tra hiệu suất, slow queries, missing indexes
- Khi cần phân tích code liên quan đến database (SQL injection, N+1, missing indexes)
- Khi cần audit database + code định kỳ
- Khi người dùng yêu cầu "tạo báo cáo", "check DB status", "kiểm tra database", "audit code"

## Cấu Trúc Thư Mục

```
workspace/
├── PROJECT_A/
│   ├── .env                              # Connection + Code config (JSON)
│   ├── 2026-02-04/
│   │   ├── DB_STATUS_REPORT.md           # Chẩn đoán Database
│   │   ├── CODE_ANALYSIS_REPORT.md       # Phân tích Code
│   │   ├── PERFORMANCE_SOLUTIONS.md      # ⭐ Giải pháp cụ thể (SQL + Code fixes)
│   │   └── COMBINED_REPORT.md            # Dashboard tổng hợp
│   ├── 2026-02-05/
│   │   ├── DB_STATUS_REPORT.md
│   │   ├── CODE_ANALYSIS_REPORT.md
│   │   ├── PERFORMANCE_SOLUTIONS.md
│   │   └── COMBINED_REPORT.md
│   └── ...
├── PROJECT_B/
│   ├── .env
│   ├── 2026-02-04/
│   │   ├── DB_STATUS_REPORT.md
│   │   ├── CODE_ANALYSIS_REPORT.md
│   │   ├── PERFORMANCE_SOLUTIONS.md
│   │   └── COMBINED_REPORT.md
│   └── ...
```

## Định Dạng File .env

File `.env` trong mỗi thư mục dự án chứa JSON với cấu trúc:

```json
{
  "ServerName": "host_or_ip",
  "CatalogName": "database_name",
  "Username": "user",
  "Password": "password",
  "Port": 5432,
  "MaxPoolSize": 500,
  "CodePath": "D:/Projects/MyApp",
  "ProjectName": "My Application",
  "CodeLanguage": "csharp",
  "Framework": "dotnet"
}
```

### Giải Thích Các Trường

| Trường | Bắt buộc | Mặc định | Mô tả |
|--------|----------|----------|-------|
| `ServerName` | ✅ | - | Host hoặc IP của PostgreSQL server |
| `CatalogName` | ✅ | - | Tên database |
| `Username` | ✅ | - | Username kết nối DB |
| `Password` | ✅ | - | Password kết nối DB |
| `Port` | ❌ | `5432` | Port PostgreSQL |
| `MaxPoolSize` | ❌ | `100` | Kích thước connection pool tối đa |
| `CodePath` | ❌ | `null` | Đường dẫn tuyệt đối tới thư mục code dự án. Nếu không có, bỏ qua phần Code Report |
| `ProjectName` | ❌ | Tên thư mục | Tên hiển thị của dự án |
| `CodeLanguage` | ❌ | auto-detect | Ngôn ngữ chính: `csharp`, `java`, `python`, `typescript`, `go`, `php` |
| `Framework` | ❌ | auto-detect | Framework: `dotnet`, `spring`, `django`, `nestjs`, `gin`, `laravel` |

## Quy Trình Thực Hiện

### Bước 1: Quét Workspace Tìm Database Directories

1. Liệt kê tất cả thư mục con trực tiếp trong workspace root
2. Lọc chỉ những thư mục có chứa file `.env`
3. Đọc và parse JSON từ mỗi file `.env`
4. Hiển thị danh sách database tìm được cho user xác nhận

### Bước 2: Tạo Thư Mục Ngày

1. Lấy ngày hiện tại theo định dạng `yyyy-MM-dd`
2. Tạo thư mục con `yyyy-MM-dd` trong mỗi thư mục database
3. Nếu thư mục đã tồn tại, hỏi user có muốn ghi đè báo cáo cũ không

### Bước 3: Kết Nối Và Thu Thập Dữ Liệu

Với mỗi database, sử dụng Python script với `psycopg2` để chạy các query sau:

#### 3.1 Tổng Quan Database
```sql
-- Database size
SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) as size
FROM pg_database WHERE datname = current_database();

-- Uptime
SELECT now() - pg_postmaster_start_time() AS uptime;

-- Active connections
SELECT count(*) as active_connections FROM pg_stat_activity
WHERE datname = current_database() AND state = 'active';

-- Total connections
SELECT count(*) as total_connections FROM pg_stat_activity
WHERE datname = current_database();
```

#### 3.2 Cache Hit Ratio (Tổng Thể)
```sql
SELECT
  sum(heap_blks_read) as heap_read,
  sum(heap_blks_hit) as heap_hit,
  CASE WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
    THEN round(sum(heap_blks_hit)::numeric / (sum(heap_blks_hit) + sum(heap_blks_read)) * 100, 2)
    ELSE 0
  END as cache_hit_ratio
FROM pg_statio_user_tables;
```

#### 3.3 Cache Hit Ratio Theo Bảng (Top 20)
```sql
SELECT
  schemaname, relname,
  heap_blks_read as disk_reads,
  heap_blks_hit as cache_hits,
  CASE WHEN heap_blks_hit + heap_blks_read > 0
    THEN round(heap_blks_hit::numeric / (heap_blks_hit + heap_blks_read) * 100, 2)
    ELSE 0
  END as cache_hit_pct
FROM pg_statio_user_tables
WHERE heap_blks_hit + heap_blks_read > 0
ORDER BY heap_blks_read DESC
LIMIT 20;
```

#### 3.4 Top 20 Slow Queries (cần pg_stat_statements)

**QUAN TRỌNG - Detect Schema Trước Khi Query:**

Extension `pg_stat_statements` có thể nằm ở schema khác (`extensions`, `public`, `pg_catalog`, ...) mà `search_path` của user kết nối không bao gồm. Phải detect trước:

**Bước 3.4a: Kiểm tra extension đã cài và tìm schema:**
```sql
SELECT
  e.extname,
  n.nspname AS ext_schema,
  e.extversion
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'pg_stat_statements';
```

Kết quả sẽ trả về `ext_schema` (ví dụ: `extensions`, `public`, `pg_catalog`).

**Bước 3.4b: Nếu extension TỒN TẠI, thêm schema vào search_path TRƯỚC KHI query:**
```sql
-- Giả sử ext_schema = 'extensions' (thay bằng giá trị thực từ 3.4a)
SET search_path TO extensions, public, dbo;
```

Hoặc dùng schema-qualified name trực tiếp:
```sql
-- Thay {{ext_schema}} bằng giá trị từ bước 3.4a
SELECT
  queryid,
  regexp_replace(LEFT(query, 200), E'[\\n\\r\\t]+', ' ', 'g') as query_preview,
  calls,
  round(total_exec_time::numeric, 2) as total_time_ms,
  round(mean_exec_time::numeric, 2) as avg_time_ms,
  round(max_exec_time::numeric, 2) as max_time_ms,
  rows
FROM {{ext_schema}}.pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY mean_exec_time DESC
LIMIT 20;
```

**Bước 3.4c: Xử lý PostgreSQL version khác nhau:**

| PostgreSQL Version | Cột thời gian | Cách xử lý |
|-------------------|---------------|-------------|
| >= 13 | `total_exec_time`, `mean_exec_time`, `max_exec_time` | Dùng trực tiếp |
| < 13 | `total_time`, `mean_time`, `max_time` | Thay tên cột |

Detect version:
```sql
SELECT current_setting('server_version_num')::int AS version_num;
-- >= 130000 = PostgreSQL 13+
```

**Bước 3.4d: Nếu extension KHÔNG TỒN TẠI (query 3.4a trả về 0 dòng):**
- Ghi trong báo cáo: "Extension pg_stat_statements chưa được cài đặt"
- Bỏ qua phần slow queries
- Thêm vào khuyến nghị: cài extension

**Tóm tắt logic trong Python:**
```python
# 1. Detect extension schema
cursor.execute("""
    SELECT n.nspname AS ext_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'pg_stat_statements'
""")
row = cursor.fetchone()

if row:
    ext_schema = row[0]
    # 2. Detect PG version
    cursor.execute("SELECT current_setting('server_version_num')::int")
    pg_version = cursor.fetchone()[0]

    if pg_version >= 130000:
        time_col = "total_exec_time"
        mean_col = "mean_exec_time"
        max_col = "max_exec_time"
    else:
        time_col = "total_time"
        mean_col = "mean_time"
        max_col = "max_time"

    # 3. Query with schema-qualified name
    query = f"""
        SELECT queryid,
          regexp_replace(LEFT(query, 200), E'[\\n\\r\\t]+', ' ', 'g') as query_preview,
          calls,
          round({time_col}::numeric, 2) as total_time_ms,
          round({mean_col}::numeric, 2) as avg_time_ms,
          round({max_col}::numeric, 2) as max_time_ms,
          rows
        FROM {ext_schema}.pg_stat_statements
        WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
        ORDER BY {mean_col} DESC
        LIMIT 20
    """
    cursor.execute(query)
    slow_queries = cursor.fetchall()
else:
    slow_queries = None  # Extension chưa cài
```

### ⛔ BẮT BUỘC - Sanitize + Format Tương Tác

#### A. Hàm `sanitize()` bắt buộc

Script Python **BẮT BUỘC** phải có hàm này ở đầu file và dùng cho MỌI cell trong markdown table:

```python
import re

def sanitize(value):
    """BẮT BUỘC dùng cho mọi cell trong markdown table."""
    if value is None:
        return ""
    s = str(value)
    s = s.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    s = s.replace('|', '\\|')
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()
```

#### B. Query text dùng `<details>` — KHÔNG nhét vào table cell

**KHÔNG BAO GIỜ đặt query text vào cell trong markdown table.** Query text chứa newlines, tab, ký tự đặc biệt — luôn phá vỡ bảng dù đã sanitize.

**Cách đúng:** Bảng chỉ chứa SỐ LIỆU. Query text nằm trong `<details>` bên dưới bảng.

```markdown
<!-- Bảng chỉ có số liệu, KHÔNG có query text -->
| # | Mã Truy Vấn | Số Lần Gọi | TB (ms) | Cao Nhất (ms) | Tổng (ms) | Số Dòng |
|---|-------------|------------|---------|--------------|-----------|---------|
| 1 | 4005459... | 4 | 9640.76 | 10161.15 | 38563.05 | 14,475,817 |
| 2 | -441070... | 4 | 2386.51 | 2702.12 | 9546.02 | 1,917,912 |

<!-- Query text trong details expandable — bấm để mở -->
<details>
<summary>🔍 #1 — TB: 9640.76ms — 4 lần gọi — 14,475,817 dòng</summary>

\`\`\`sql
SELECT r."Id", r."ID_GUID", r."IsDeleted"...
\`\`\`

</details>

<details>
<summary>🔍 #2 — TB: 2386.51ms — 4 lần gọi — 1,917,912 dòng</summary>

\`\`\`sql
SELECT s."Id", s."FromDate", s."IsBusy"...
\`\`\`

</details>
```

**Python code mẫu:**
```python
def extract_table_name(query_text):
    """Trích tên bảng chính từ query text.
    Tìm FROM/INTO/UPDATE/JOIN + tên bảng."""
    if not query_text:
        return "N/A"
    import re
    # Tìm pattern: FROM/JOIN/UPDATE/INTO + schema."TableName" hoặc schema.tablename
    patterns = [
        r'(?:FROM|JOIN|UPDATE|INTO)\s+(?:(?:(\w+)\.)?"?(\w+)"?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, query_text, re.IGNORECASE)
        if match:
            schema = match.group(1) or ''
            table = match.group(2) or ''
            if table.lower() not in ('select', 'where', 'set', 'values', 'pg_stat_statements'):
                return f'{schema}.{table}' if schema else table
    return "N/A"

# 1. Ghi bảng số liệu (không có query text, không có tên table)
lines = []
lines.append("| # | Mã Truy Vấn | Số Lần Gọi | TB (ms) | Cao Nhất (ms) | Tổng (ms) | Số Dòng |")
lines.append("|---|-------------|------------|---------|--------------|-----------|---------|")
for idx, row in enumerate(slow_queries, 1):
    lines.append(f"| {idx} | {sanitize(row['queryid'])} | {sanitize(row['calls'])} | {sanitize(row['avg_time_ms'])} | {sanitize(row['max_time_ms'])} | {sanitize(row['total_time_ms'])} | {sanitize(row['rows'])} |")

lines.append("")

# 2. Ghi details expandable với tên table trong summary
for idx, row in enumerate(slow_queries, 1):
    query_text = row['query_preview'] or ''
    table_name = extract_table_name(query_text)
    lines.append(f'<details>')
    lines.append(f'<summary>🔍 #{idx} — <code>{table_name}</code> — TB: {row["avg_time_ms"]}ms — {row["calls"]} lần gọi — {row["rows"]} dòng</summary>')
    lines.append(f'')
    lines.append(f'```sql')
    lines.append(query_text)  # Giữ nguyên format gốc trong code block
    lines.append(f'```')
    lines.append(f'')
    lines.append(f'| Chỉ Số | Giá Trị |')
    lines.append(f'|--------|---------|')
    lines.append(f'| **Mã truy vấn** | `{row["queryid"]}` |')
    lines.append(f'| **Bảng chính** | `{table_name}` |')
    lines.append(f'| **Thời gian TB** | {row["avg_time_ms"]} ms |')
    lines.append(f'| **Thời gian cao nhất** | {row["max_time_ms"]} ms |')
    lines.append(f'| **Tổng thời gian** | {row["total_time_ms"]} ms |')
    lines.append(f'| **Số lần gọi** | {row["calls"]} |')
    lines.append(f'| **Số dòng** | {row["rows"]} |')
    lines.append(f'')
    lines.append(f'</details>')
    lines.append(f'')
```

**Áp dụng `<details>` cho TẤT CẢ phần có query text:**
- Slow queries → `<details>` với SQL block
- Blocking queries → `<details>` với cả 2 query (bị chặn + đang chặn) + gợi ý `pg_cancel_backend()`
- Long running queries → `<details>` với query + gợi ý xử lý

**Áp dụng `sanitize()` cho mọi cell KHÁC trong table:**
- Table names, index names, schema names
- Số liệu, phần trăm, dung lượng
- Bất kỳ giá trị nào từ database đưa vào markdown table

**Lưu ý:** Nếu `pg_stat_statements` chưa được cài (query 3.4a trả về 0 dòng), ghi nhận trong báo cáo và bỏ qua phần này.

#### 3.5 Table Sizes (Top 20)
```sql
SELECT
  schemaname,
  relname as table_name,
  pg_size_pretty(pg_total_relation_size(relid)) as total_size,
  pg_size_pretty(pg_relation_size(relid)) as data_size,
  pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size,
  n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

#### 3.6 Missing Indexes (Bảng Có Nhiều Seq Scan)
```sql
SELECT
  schemaname, relname,
  seq_scan, seq_tup_read,
  idx_scan, idx_tup_fetch,
  n_live_tup,
  CASE WHEN seq_scan + idx_scan > 0
    THEN round(seq_scan::numeric / (seq_scan + idx_scan) * 100, 2)
    ELSE 0
  END as seq_scan_pct
FROM pg_stat_user_tables
WHERE seq_scan > 100
  AND n_live_tup > 10000
  AND (idx_scan IS NULL OR idx_scan < seq_scan)
ORDER BY seq_tup_read DESC
LIMIT 20;
```

#### 3.7 Index Usage Statistics
```sql
SELECT
  schemaname, relname as table_name,
  indexrelname as index_name,
  idx_scan as times_used,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;
```

#### 3.8 Unused Indexes (Lãng Phí Dung Lượng)
```sql
SELECT
  schemaname, relname as table_name,
  indexrelname as index_name,
  idx_scan as times_used,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelname NOT LIKE '%_pkey'
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;
```

#### 3.9 Blocking Queries
```sql
SELECT
  blocked_locks.pid AS blocked_pid,
  blocked_activity.usename AS blocked_user,
  LEFT(blocked_activity.query, 150) AS blocked_query,
  blocking_locks.pid AS blocking_pid,
  blocking_activity.usename AS blocking_user,
  LEFT(blocking_activity.query, 150) AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
  AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
  AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
  AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
  AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
  AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
  AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
  AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
  AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
  AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
  AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

#### 3.10 Long Running Queries (> 5 phút)
```sql
SELECT
  pid,
  usename,
  state,
  query_start,
  now() - query_start AS duration,
  LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE state != 'idle'
  AND query_start < now() - interval '5 minutes'
  AND datname = current_database()
ORDER BY duration DESC;
```

#### 3.11 Dead Tuples (Cần VACUUM)
```sql
SELECT
  schemaname, relname,
  n_live_tup,
  n_dead_tup,
  CASE WHEN n_live_tup > 0
    THEN round(n_dead_tup::numeric / n_live_tup * 100, 2)
    ELSE 0
  END as dead_pct,
  last_vacuum,
  last_autovacuum,
  last_analyze,
  last_autoanalyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC
LIMIT 20;
```

#### 3.12 Replication Status (nếu có)
```sql
SELECT
  client_addr,
  state,
  sent_lsn,
  write_lsn,
  flush_lsn,
  replay_lsn,
  pg_wal_lsn_diff(sent_lsn, replay_lsn) AS replication_lag_bytes
FROM pg_stat_replication;
```

### Bước 4: Tạo Báo Cáo Database (DB_STATUS_REPORT.md)

Sử dụng template từ `references/template-db-report.md` để tạo file `DB_STATUS_REPORT.md` trong thư mục ngày.

**Quy ước đánh giá tự động:**
- Cache Hit: 🟢 >95% | 🟡 80-95% | 🔴 <80%
- Dead Tuples: 🟢 <5% | 🟡 5-20% | 🔴 >20%
- Seq Scan %: 🟢 <30% | 🟡 30-50% | 🔴 >50%
- Connection Usage: 🟢 <60% max | 🟡 60-80% | 🔴 >80%

### Bước 5: Phân Tích Code (CODE_ANALYSIS_REPORT.md)

**Chỉ thực hiện khi `CodePath` được cấu hình trong .env.**

Sử dụng template từ `references/template-code-report.md`.

#### 5.1 Quét Cấu Trúc Dự Án
1. Đọc cấu trúc thư mục từ `CodePath`
2. Xác định ngôn ngữ và framework (tự động hoặc từ .env)
3. Đếm files, lines of code

#### 5.2 Tìm Models/Entities
Tùy theo ngôn ngữ:

**C# (.NET):**
```
- Tìm files trong thư mục Models/, Entities/, Domain/
- Grep pattern: `class\s+\w+\s*:\s*(Entity|BaseEntity|DbContext)`
- Grep pattern: `\[Table\(".*"\)\]`
- Tìm DbContext và DbSet<> declarations
```

**Java (Spring):**
```
- Grep pattern: `@Entity`, `@Table`
- Tìm files trong thư mục entity/, model/, domain/
```

**Python (Django):**
```
- Grep pattern: `class\s+\w+\(models\.Model\)`
- Tìm files models.py
```

**TypeScript (NestJS/TypeORM):**
```
- Grep pattern: `@Entity\(\)`, `@Column\(\)`
- Tìm files *.entity.ts
```

#### 5.3 Tìm Raw SQL Queries
```
Grep patterns (tất cả ngôn ngữ):
- "SELECT\s+.*\s+FROM\s+"
- "INSERT\s+INTO\s+"
- "UPDATE\s+\w+\s+SET"
- "DELETE\s+FROM\s+"
- "CREATE\s+(TABLE|INDEX)"
- "ALTER\s+TABLE"
- "DROP\s+(TABLE|INDEX)"
- ExecuteSqlRaw, FromSqlRaw (C#)
- @Query, nativeQuery (Java)
- raw(), execute() (Python)
- query(), createQueryBuilder (TypeScript)
```

#### 5.4 Phát Hiện SQL Injection
```
Grep patterns:
- String concatenation trong query: $"...{variable}...", f"...{var}...", "..." + var + "..."
- String.Format trong SQL context
- Không dùng parameterized queries
```

#### 5.5 Phát Hiện N+1 Query Patterns
```
- Loop chứa DB call bên trong
- Lazy loading trong loop
- Include/Eager loading thiếu
```

#### 5.6 Mapping Code ↔ Database
1. Lấy danh sách tables từ DB (query `information_schema.tables`)
2. Lấy danh sách entities từ code
3. Cross-reference để tìm:
   - Tables có trong DB nhưng không có entity trong code
   - Entities trong code nhưng không có table trong DB

#### 5.7 Phân Tích Connection Management
```
- Tìm connection string configurations
- Kiểm tra connection pool settings
- Tìm tiềm năng connection leak (open without close/dispose)
```

### Bước 6: Tạo Báo Cáo Tổng Hợp (COMBINED_REPORT.md)

Sử dụng template từ `references/template-combined-report.md`.

**Hệ thống chấm điểm:**

| Hạng mục | Tiêu chí | Điểm |
|----------|---------|------|
| DB Health | Cache >95%: +30, Connections <60%: +20, No blocking: +20, Dead tuples <5%: +15, Size hợp lý: +15 | /100 |
| Code Quality | No SQL injection: +30, No N+1: +25, Parameterized queries: +20, Proper connection mgmt: +15, Migration up-to-date: +10 | /100 |
| Security | No hardcoded creds: +40, No SQL injection: +30, Proper auth: +30 | /100 |
| Performance | Index coverage: +30, No slow queries >1s: +25, Cache hit >90%: +25, No SELECT *: +20 | /100 |

### Bước 7: So Sánh Với Báo Cáo Trước

1. Tìm thư mục ngày gần nhất trước ngày hiện tại
2. Nếu tồn tại báo cáo cũ, thêm section **SO SÁNH** vào đầu mỗi báo cáo:
   - So sánh Cache Hit Ratio
   - So sánh Avg Query Time
   - So sánh Database Size
   - So sánh số Blocking Queries
   - So sánh Code Score (nếu có)
   - Ghi nhận xu hướng: ⬆️ cải thiện | ⬇️ xấu đi | ➡️ không đổi

### Bước 8: Generate Performance Solutions (PERFORMANCE_SOLUTIONS.md)

Bước này biến kết quả chẩn đoán thành giải pháp cụ thể sử dụng solution engine (KB đóng gói nội bộ tại `references/kb/`; nguồn: supabase-postgres-best-practices).

#### 8.1 Load Solution Index

Đọc solution mapping từ (KB đóng gói nội bộ):
`references/kb/solution-index.md`

File này mapping mỗi problem pattern tới:
- Concrete SQL fix template
- Best practice reference file
- Priority level (P0-P3)
- Expected impact

#### 8.2 Thu Thập Tất Cả Vấn Đề Phát Hiện

Tổng hợp issues từ Bước 3-5:

**Từ DB diagnostics (Bước 3):**
- Tables có `cache_hit_pct < 90%`
- Tables có `seq_scan_pct > 50%` và `n_live_tup > 10,000`
- Tables có `dead_pct > 5%`
- Slow queries (`mean_exec_time > 100ms`)
- Unused indexes (`idx_scan = 0`)
- Connection usage > 60% of max
- Blocking queries
- Long-running queries (> 5 min)
- Server config parameters khác biệt so với recommendations

**Từ Code analysis (Bước 5):**
- SQL injection risks
- N+1 query patterns
- Missing pagination trên large tables
- SELECT * patterns
- Connection management issues

#### 8.3 Chạy Solution Queries

Execute queries từ `references/queries-solutions.sql` để thu thập:
- Missing FK indexes → auto-generate CREATE INDEX statements
- Duplicate indexes → auto-generate DROP INDEX statements
- Tables cần VACUUM → auto-generate VACUUM commands
- Server config comparison → generate ALTER SYSTEM statements
- Partition candidates (tables > 1M rows)
- Index bloat → generate REINDEX statements
- Idle connections → generate pg_terminate_backend statements

#### 8.4 Assign Priority

Gán priority theo bảng rules sau:

| Condition | Priority |
|-----------|----------|
| SQL injection detected | **P0** |
| Cache hit < 50% trên active table | **P0** |
| Blocking queries active | **P0** |
| Connection usage > 90% | **P0** |
| Dead tuples > 50% | **P0** |
| Cache hit 50-80% | **P1** |
| Slow query avg > 1000ms | **P1** |
| N+1 pattern in code | **P1** |
| Missing FK index | **P1** |
| Connection usage 60-90% | **P1** |
| Dead tuples 20-50% | **P1** |
| shared_buffers < 15% RAM | **P1** |
| Cache hit 80-90% | **P2** |
| Unused indexes | **P2** |
| Slow query avg 100-1000ms | **P2** |
| Missing pagination (>10K rows) | **P2** |
| SELECT * pattern | **P2** |
| Dead tuples 5-20% | **P2** |
| Table >10M rows, no partition | **P2** |
| Server config suboptimal | **P2** |
| Index bloat | **P3** |
| Duplicate indexes | **P3** |
| Covering index opportunities | **P3** |

#### 8.5 Generate Fix SQL

Với mỗi vấn đề, tạo SQL fix cụ thể:

1. Lấy fix template từ `solution-index.md`
2. Thay thế placeholders bằng actual table names, column names, schema names từ diagnostic data
3. Thêm `CONCURRENTLY` cho tất cả CREATE/DROP INDEX (production safety)
4. Thêm verification query sau mỗi fix
5. Thêm rollback statement nếu applicable

#### 8.6 Generate Code-Side Solutions

Cho các vấn đề code (N+1, SQL injection, missing pagination):

1. Hiển thị code snippet có vấn đề (file path + line number)
2. Hiển thị corrected code pattern từ best practices
3. Adapt fix theo ngôn ngữ/framework của dự án (từ .env `CodeLanguage`/`Framework`)

Ví dụ output:
```
❌ TRƯỚC (N+1):
foreach (var user in users) { db.Orders.Where(o => o.UserId == user.Id); }

✅ SAU:
var usersWithOrders = db.Users.Include(u => u.Orders).ToList();
```

#### 8.7 Generate Architecture Recommendations

Cho các vấn đề hệ thống, đưa ra recommendations:

- **Caching strategy**: Khi nhiều tables có low cache hit → recommend Redis/Memcached
- **Read replicas**: Khi connection usage cao AND nhiều read queries
- **Materialized views**: Khi slow queries aggregate large datasets lặp lại
- **Connection pooling**: Khi connection count cao, không có pooler
- **Partitioning**: Khi tables > 10M rows với time-based access patterns

#### 8.8 Write PERFORMANCE_SOLUTIONS.md

Sử dụng template `references/template-solutions-report.md` để tạo report bao gồm:
- Executive summary (đếm theo priority)
- Solutions grouped by priority (P0 → P3)
- Ready-to-execute SQL scripts section (copy-paste chạy luôn)
- Code-side solutions (before/after examples)
- Architecture recommendations
- Solution tracking checklist

### Bước 9: Tổng Hợp Tất Cả Dự Án

Sau khi tạo xong báo cáo cho tất cả dự án, hiển thị tóm tắt:

```
═══════════════════════════════════════════════
       KẾT QUẢ TẠO BÁO CÁO - yyyy-MM-dd
═══════════════════════════════════════════════

Tổng số dự án: N

| # | Dự Án    | DB Status | Code Status | Score | P0 | P1 | P2 | Solutions |
|---|----------|-----------|-------------|-------|----|----|----|-----------|
| 1 | Project_A| 🟢 95%   | 🟡 78/100   | 85    | 0  | 2  | 5  | 7         |
| 2 | Project_B| 🟡 82%   | 🔴 45/100   | 62    | 3  | 5  | 8  | 16        |

Báo cáo đã được lưu tại:
📁 PROJECT_A/yyyy-MM-dd/
   ├── DB_STATUS_REPORT.md
   ├── CODE_ANALYSIS_REPORT.md
   ├── PERFORMANCE_SOLUTIONS.md    ⭐ 7 solutions (0 P0, 2 P1, 5 P2)
   └── COMBINED_REPORT.md
📁 PROJECT_B/yyyy-MM-dd/
   ├── DB_STATUS_REPORT.md
   ├── CODE_ANALYSIS_REPORT.md
   ├── PERFORMANCE_SOLUTIONS.md    ⭐ 16 solutions (3 P0, 5 P1, 8 P2)
   └── COMBINED_REPORT.md
```

## Xử Lý Lỗi

- Nếu không kết nối được DB: ghi log lỗi, tạo báo cáo rỗng với thông tin lỗi, tiếp tục dự án tiếp theo
- Nếu `pg_stat_statements` chưa cài: bỏ qua phần slow queries, ghi nhận trong báo cáo
- Nếu không có quyền đọc một số view: ghi nhận phần nào bị thiếu
- Nếu `CodePath` không tồn tại hoặc rỗng: bỏ qua Code Report, chỉ tạo DB Report
- Nếu `CodePath` không có trong .env: chỉ tạo DB Report
- Nếu thư mục ngày đã tồn tại: hỏi user có muốn ghi đè không
- Nếu solution-index.md không tìm thấy: tạo solutions dựa trên general best practices

## Thư Mục Làm Việc

**BẮT BUỘC: Tất cả script Python, file tạm, file trung gian PHẢI được tạo trong thư mục workspace hiện tại (cùng cấp với các thư mục dự án). KHÔNG ĐƯỢC dùng thư mục tạm hệ thống (C:\Users\...\Temp, /tmp, scratchpad, v.v.).**

Cụ thể:
- Script Python kết nối DB: tạo tại `{workspace}/.scripts/generate_db_report.py`
- File kết quả trung gian: tạo tại `{workspace}/.scripts/`
- Thư mục `.scripts/` sẽ được tạo tự động nếu chưa có
- Sau khi chạy xong, có thể giữ lại script để user debug hoặc chạy lại

Ví dụ với workspace `e:\Skills`:
```
e:\Skills/
├── .scripts/
│   └── generate_db_report.py    ← Script chạy tại đây
├── SIGO/
│   ├── .env
│   └── 2026-02-04/
├── CoShare/
│   ├── .env
│   └── 2026-02-04/
```

**Lý do:** Giữ mọi thứ trong workspace giúp:
1. Dễ debug khi có lỗi
2. Không phụ thuộc vào ổ đĩa hệ thống
3. User có thể xem và chỉnh sửa script
4. Chạy lại script thủ công bất cứ lúc nào

## Yêu Cầu Hệ Thống

- Python 3.x với `psycopg2` (hoặc `psycopg2-binary`)
- Quyền `SELECT` trên các system views (`pg_stat_*`, `pg_statio_*`)
- Quyền `EXECUTE` trên `pg_database_size()`, `pg_relation_size()`
- Nếu cần slow queries: extension `pg_stat_statements` phải được cài

## Report Templates

Sử dụng các template chuẩn trong thư mục `references/`:
- `references/template-db-report.md` - Template báo cáo Database
- `references/template-code-report.md` - Template báo cáo Code
- `references/template-solutions-report.md` - Template giải pháp Performance ⭐ NEW
- `references/template-combined-report.md` - Template báo cáo tổng hợp

## SQL Query References

Các query đầy đủ và giải thích chi tiết:
- `references/queries-overview.sql` - Queries tổng quan database
- `references/queries-performance.sql` - Queries phân tích hiệu suất
- `references/queries-index.sql` - Queries phân tích index
- `references/queries-solutions.sql` - Queries tạo fix SQL statements ⭐ NEW

## Solution Engine

Hệ thống tạo giải pháp dựa trên knowledge base đóng gói nội bộ tại `references/kb/` (nguồn: supabase-postgres-best-practices, xem `references/kb/_index.md`):
- `references/kb/solution-index.md` - Master mapping: 13 problem patterns → concrete fixes
- Mỗi fix bao gồm: SQL template, verification query, rollback, expected impact
- Priority rules: P0 (24h) → P1 (1 tuần) → P2 (1 tháng) → P3 (sprint sau)

---
name: db-report-generator
description: Tự động quét tất cả thư mục database trong workspace, kết nối PostgreSQL qua .env, tạo báo cáo tình trạng DB + Code + GIẢI PHÁP PERFORMANCE cụ thể và lưu vào thư mục theo ngày (yyyy-MM-dd). Chẩn đoán vấn đề VÀ kê đơn giải pháp từ code đến DB.
metadata:
  author: NGOMI
  version: "4.0.0"
  date: July 2026
---

# Database & Code Report Generator + Solution Engine

Skill tự động tạo báo cáo tình trạng database PostgreSQL, phân tích code, VÀ đưa ra giải pháp performance cụ thể (ready-to-execute SQL + code fixes) cho tất cả dự án được cấu hình trong workspace.

**v4.0 - Kiến trúc Python tất định** (`scripts/analyzer.py` → collectors → `scripts/rules.py` → `scripts/render.py`) sinh `DB_STATUS_REPORT.md`/`FINDINGS.md` không cần agent tự viết SQL, cộng Solution Engine (KB đóng gói nội bộ tại `references/kb/`, nguồn: `supabase-postgres-best-practices`) đi kèm mỗi finding với priority, SQL fix, code fix, và expected impact. Skill **self-contained** — không phụ thuộc skill KB ngoài.

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
  "CodePath": "D:/Projects/MyApp",
  "ProjectName": "My Application",
  "CodeLanguage": "csharp",
  "Framework": "dotnet",
  "SamplingWindowSeconds": 30,
  "ExplainMode": "plan",
  "ExplainTopN": 5,
  "ExplainAnalyzeTopN": 0,
  "ExplainStatementTimeoutMs": 3000,
  "ExplainLockTimeoutMs": 500
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
| `CodePath` | ❌ | `null` | Đường dẫn tuyệt đối tới thư mục code dự án. Nếu không có, bỏ qua phần Code Report |
| `ProjectName` | ❌ | Tên thư mục | Tên hiển thị của dự án |
| `CodeLanguage` | ❌ | auto-detect | Ngôn ngữ chính: `csharp`, `java`, `python`, `typescript`, `go`, `php` |
| `Framework` | ❌ | auto-detect | Framework: `dotnet`, `spring`, `django`, `nestjs`, `gin`, `laravel` |
| `SamplingWindowSeconds` | ❌ | `30` | Độ dài (giây) của cửa sổ live sampling dùng để đo delta pg_stat_statements giữa 2 lần snapshot |
| `ExplainMode` | ❌ | `"plan"` | Chế độ EXPLAIN cho top slow queries: `off` (tắt hẳn), `plan` (chỉ lập kế hoạch, không chạy query), `analyze` (**THỰC SỰ CHẠY query** trên DB live, không chỉ lập kế hoạch). Chế độ `analyze` chỉ được coi là an toàn khi CẢ BA cơ chế sau cùng có hiệu lực: (a) phân loại câu lệnh bằng parser thật `sql_classify.is_analyze_safe()` (không bao giờ dùng regex), (b) allowlist tường minh — chỉ `ExplainAnalyzeTopN` câu truy vấn chậm đầu tiên được phép, (c) `ExplainStatementTimeoutMs`/`ExplainLockTimeoutMs` siết chặt. Transaction READ ONLY KHÔNG được xem là cơ chế an toàn — ANALYZE vẫn thực thi các side-effect như `nextval()` ngay cả trong transaction READ ONLY |
| `ExplainTopN` | ❌ | `5` | Số lượng slow queries (theo thứ hạng `query_stats`) sẽ được EXPLAIN (chế độ `plan` hoặc `analyze`) |
| `ExplainAnalyzeTopN` | ❌ | `0` | Trong số `ExplainTopN` câu, chỉ `ExplainAnalyzeTopN` câu đầu tiên được phép chạy EXPLAIN ANALYZE thật (chỉ áp dụng khi `ExplainMode=analyze`); phần còn lại vẫn chỉ EXPLAIN plan |
| `ExplainStatementTimeoutMs` | ❌ | `3000` | `statement_timeout` (ms) áp cho mỗi lệnh EXPLAIN/EXPLAIN ANALYZE, khôi phục lại giá trị mặc định ngay sau đó |
| `ExplainLockTimeoutMs` | ❌ | `500` | `lock_timeout` (ms) áp cho mỗi lệnh EXPLAIN/EXPLAIN ANALYZE, khôi phục lại giá trị mặc định ngay sau đó |

**Ghi chú:** EXPLAIN plan (và gợi ý từ index advisor) được đính kèm vào diagnostic block `explain` và `index_advisor` trong `report_data.json` — JSON plan nằm lồng bên trong các dòng `metrics` của từng block, KHÔNG có file "explain report" riêng ở cấp cao nhất.

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

### Bước 3: Thu Thập Dữ Liệu (Python Pipeline)

**KHÔNG tự viết SQL hay script kết nối DB thủ công.** Toàn bộ việc kết nối, thu thập, và đánh giá đã được đóng gói tất định trong `scripts/` (analyzer → collectors → rules → render) — xem `scripts/analyzer.py::_analyze_target` để biết danh sách đầy đủ diagnostic block nếu cần tra cứu. Với mỗi database:

1. Chạy:
   ```bash
   set PYTHONIOENCODING=utf-8
   cd {workspace}\.agents\skills\db-report-generator
   python -m scripts.run_report "{path-to-project}\.env" "{path-to-project}\{yyyy-MM-dd}"
   ```
2. Lệnh trên (`scripts/run_report.py`) tự thực hiện toàn bộ — agent không cần viết code cho bước này:
   - Kết nối read-only + timeout (`scripts/lib/db.py`), thăm dò capability (`scripts/capabilities.py`: vendor, managed, superuser, server_version_num)
   - Chạy tất cả collector đã đăng ký trong `scripts/collectors/__init__.py::COLLECTORS` (cache hit, table/index size, dead tuples, missing FK index, duplicate/bloated index, slow queries qua `pg_stat_statements` với tự-detect schema/version, blocking, replication, wraparound, wait events, `pg_stat_database`, RLS policy, schema hygiene) cộng `scripts/explain.py` (EXPLAIN plan top-N slow query, an toàn theo `ExplainMode`) và `scripts/index_advisor.py` (gợi ý index cấp cột)
   - Đánh giá mọi finding theo `references/rules/*.json` (`scripts/rules.py`) — 5 trục: `db-health`, `query-performance`, `maintenance`, `connections`, `security-rls`
   - Ghi `report_data.json` (nguồn sự thật duy nhất, schema `references/report-data.schema.json`), `DB_STATUS_REPORT.md`, `FINDINGS.md`, `report_summary.json` vào thư mục ngày
3. Nếu database này lỗi (không kết nối được, timeout, thiếu quyền...), `analyzer.py` đã tự cô lập lỗi đó vào riêng database này (`target.collection_status = "error"` + `target.error`) — **không** làm hỏng báo cáo của database khác trong cùng lần chạy, và **không** làm dừng vòng lặp qua các dự án còn lại (Bước 9). Đọc trường `error` trong `report_data.json` nếu cần biết lý do.
4. `report_data.json` là nguồn duy nhất cho Bước 5–8 sau đây — **không** tự tính lại cache hit ratio, dead tuple %, seq scan % v.v. bằng tay; đọc thẳng từ `diagnostics.<block>.findings[].assessment` / `.metrics`.

### Bước 4: Báo Cáo Database Đã Được Tạo Tự Động

`DB_STATUS_REPORT.md` và `FINDINGS.md` đã được `scripts/render.py` tạo xong ở Bước 3 — **đừng** tạo lại bằng tay hay dùng template Handlebars nào cho phần DB. Đọc 2 file này để lấy issue list cho Bước 6 (Combined Report) và Bước 8 (Solutions).

**Quy ước đánh giá** (áp dụng tự động bởi `scripts/rules.py`, không cần tính tay):
- 🟢 green / 🟡 yellow / 🔴 red / ⚪ unknown (dữ liệu không đủ tin cậy để đánh giá, §0.B3 — không được tự nâng cấp lên green/yellow/red) / ➖ not_applicable
- Ngưỡng chi tiết từng finding: xem `references/rules/*.json` (không hardcode ngưỡng trong báo cáo)

### Quy Ước Định Dạng Chung — Bắt Buộc Cho Báo Cáo Agent Tự Viết (Bước 5, 6, 8)

`DB_STATUS_REPORT.md`/`FINDINGS.md` ở Bước 3–4 do Python sinh ra, không cần convention này. Nhưng `CODE_ANALYSIS_REPORT.md` (Bước 5), `COMBINED_REPORT.md` (Bước 6), và `PERFORMANCE_SOLUTIONS.md` (Bước 8) vẫn do agent tự viết Markdown — áp dụng đúng 2 quy tắc sau cho các file đó:

#### A. Hàm `sanitize()` bắt buộc

Nếu agent dùng Python để build các file này, **BẮT BUỘC** có hàm này ở đầu file và dùng cho MỌI cell trong markdown table:

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

#### B. Query/code text dùng `<details>` — KHÔNG nhét vào table cell

**KHÔNG BAO GIỜ đặt query text hoặc code snippet vào cell trong markdown table.** Text nhiều dòng luôn phá vỡ bảng dù đã sanitize.

**Cách đúng:** Bảng chỉ chứa SỐ LIỆU. Query/code text nằm trong `<details>` bên dưới bảng:

```markdown
<!-- Bảng chỉ có số liệu, KHÔNG có query text -->
| # | Mã Truy Vấn | Số Lần Gọi | TB (ms) |
|---|-------------|------------|---------|
| 1 | 4005459... | 4 | 9640.76 |

<!-- Query text trong details expandable — bấm để mở -->
<details>
<summary>🔍 #1 — TB: 9640.76ms — 4 lần gọi</summary>

\`\`\`sql
SELECT ...
\`\`\`

</details>
```

**Áp dụng cho:** slow-query excerpt trong `PERFORMANCE_SOLUTIONS.md`, raw-SQL excerpt trong `CODE_ANALYSIS_REPORT.md`, và bất kỳ đoạn code/SQL nhiều dòng nào khác được trích dẫn trong 3 file này.

### Bước 5: Phân Tích Code (CODE_ANALYSIS_REPORT.md)

**Chỉ thực hiện khi `CodePath` được cấu hình trong .env.**

Sử dụng template từ `assets/templates/template-code-report.md`.

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

#### 5.8 Gán Độ Tin Cậy Cho Code Findings

Mỗi finding từ Bước 5.3-5.7 (raw SQL, SQL injection, N+1, mapping, connection management) phải được gán một trong 3 mức độ tin cậy — code-analysis ở đây là agent tự grep/đọc code (§3 kiến trúc: đây là trách nhiệm của agent, không phải collector Python), nên độ tin cậy phản ánh agent tự tin đến đâu vào từng phát hiện, không phải một con số đo được từ DB:

| Mức | Khi nào dùng | Ví dụ |
|-----|-------------|-------|
| `measured` | Pattern match trực tiếp, không cần suy luận thêm — chuỗi text rõ ràng xuất hiện trong code | String-concatenated SQL (`"SELECT * FROM " + table`), `SELECT *` literal trong query text |
| `estimated` | Pattern match nhưng cần agent tự xác nhận ngữ cảnh (vd. loop có thực sự gọi DB mỗi vòng không) | N+1 pattern (loop chứa call trông giống DB call), thiếu index cho cột dùng trong WHERE của raw SQL |
| `heuristic` | Suy luận gián tiếp, không có bằng chứng trực tiếp trong code — dựa trên convention/thiếu vắng | "Có thể" thiếu connection pooling vì không tìm thấy config rõ ràng, "Có thể" thiếu pagination vì không thấy LIMIT/OFFSET |

**Ưu tiên báo cáo:** liệt kê finding theo thứ tự `measured` → `estimated` → `heuristic` trong CODE_ANALYSIS_REPORT.md — tín hiệu độ tin cậy cao (SQL injection do string concatenation, `SELECT *`, connection leak pattern rõ ràng) phải đứng trước các suy đoán (N+1 chưa xác nhận, thiếu pagination suy luận từ absence).

**Khi không tìm thấy gì:** nếu Bước 5.3 không tìm thấy raw SQL nào do code dùng ORM/ORM-generated SQL hoàn toàn, CODE_ANALYSIS_REPORT.md phải ghi rõ câu "Không tìm thấy raw SQL — code sử dụng ORM, không có ORM-generated SQL nào được kiểm tra thủ công" thay vì bỏ trống section — im lặng không phân biệt được với "chưa chạy bước này".

### Bước 6: Tạo Báo Cáo Tổng Hợp (COMBINED_REPORT.md)

Sử dụng template từ `assets/templates/template-combined-report.md`.

### Mô hình đánh giá theo trục (Axis Model)

Từ P3 trở đi, hệ thống KHÔNG dùng điểm số tổng hợp 0-100 (double-counting, false precision). Mỗi trục trong 5 trục sau được đánh giá độc lập bằng 🟢/🟡/🔴/⚪/➖ kèm độ tin cậy (`measured`/`estimated`/`heuristic`):

| Trục | Nguồn rule | Diagnostic blocks liên quan |
|------|-----------|------------------------------|
| DB Health | `references/rules/db-health.json` | `database_stats`, `wraparound` |
| Query Performance | `references/rules/query-performance.json` | `query_stats`, `index_io`, `index_advisor` |
| Maintenance | `references/rules/maintenance.json` | `dead_tuples`, `stale_stats`, `index_bloat`, `duplicate_index`, `fk_missing_index`, `schema_checks` |
| Connections | `references/rules/connections.json` | `connection_depth`, `blocking` |
| Security/RLS | `references/rules/security-rls.json` | `rls_policies` |

Việc ánh xạ block → trục là tra cứu ở code (`scripts/rules.py`), không phải field trong schema — schema finding không có field `axis`.

### Bước 7: So Sánh Với Báo Cáo Trước

1. Tìm thư mục ngày gần nhất trước ngày hiện tại
2. Nếu tồn tại báo cáo cũ, thêm section **SO SÁNH** vào đầu mỗi báo cáo:
   - So sánh Cache Hit Ratio
   - So sánh Avg Query Time
   - So sánh Database Size
   - So sánh số Blocking Queries
   - So sánh số lượng finding theo severity giữa các lần chạy (không còn khái niệm "Code Score" tổng hợp)
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
- Tables có `seq_scan_pct > 50%` và `n_live_tup > 10,000` (nếu diagnostic có `related_queries` không rỗng, dùng chính query đó thay vì tự đoán cột filter)
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

#### 8.3 Tra Cứu Remediation Class

Với mỗi vấn đề đã match được từ `references/kb/solution-index.md`, đọc trường `Remediation Class` của pattern đó (5-tier taxonomy — xem chi tiết tại `references/remediation-policy.md`):
- `observe-only`, `controlled-diagnostic`, `maintenance-review`, `ddl-review` → có thể đưa fix vào script "SẴN SÀNG CHẠY" tương ứng theo priority (P0/P1/P2).
- `dangerous` → KHÔNG đưa vào script "SẴN SÀNG CHẠY". Đưa vào mục riêng "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" của `PERFORMANCE_SOLUTIONS.md`.
- Với fix liên quan `ALTER SYSTEM`, kiểm tra `report_data.json` → `capabilities.managed` và `capabilities.is_superuser` trước khi quyết định đưa vào (chi tiết ở `references/remediation-policy.md` mục 3).

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
3. Thêm `CONCURRENTLY` cho tất cả CREATE/DROP INDEX, đặt trong SQL block RIÊNG tách biệt khỏi mọi transaction block khác; ghi kèm cảnh báo về index `INVALID` nếu câu lệnh thất bại giữa chừng (xem `references/remediation-policy.md` mục 4)
4. Thêm verification query sau mỗi fix
5. Thêm `recovery_or_rollback` cho mỗi fix (xem `references/remediation-policy.md` mục 2 để biết quy ước theo từng loại fix)
6. Nếu `Remediation Class` của fix là `dangerous`, KHÔNG đưa fix đó vào bất kỳ script "SẴN SÀNG CHẠY" nào — đưa vào mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" thay thế

⛔ **Dedupe trước khi sinh DDL cho `fk_missing_index`** — nhiều constraint FK khác tên nhưng cùng `(schema, table, columns)` là chuyện có thật trên schema đã migrate nhiều lần (đặc biệt tên dạng `FK__<table>__<hash>` tự sinh bởi SQL Server). Mỗi finding trong `report_data.json` là 1 constraint, KHÔNG phải 1 index cần tạo — **group theo `(schema, table, columns)` trước khi viết `CREATE INDEX CONCURRENTLY`, chỉ giữ 1 câu lệnh cho mỗi nhóm.** Nếu một nhóm có >1 constraint, ghi rõ trong phần "Phát hiện phụ" của solution đó (bảng: cột — số constraint trùng — số index thực cần) và gợi ý xem lại việc `DROP CONSTRAINT` các bản dư (không đưa vào script tự động vì cần xác nhận thủ công không có dependency nào phụ thuộc tên constraint cụ thể). Đếm tổng "constraint" và tổng "index cần tạo" là hai con số khác nhau — nêu cả hai trong tóm tắt tổng quan, KHÔNG chỉ nêu số constraint.

⛔ **Render `related_queries` của `seq_scan` bằng `<details>`, không phải bằng cách đoán cột filter** — mỗi row trong diagnostic `seq_scan` có thể có field `related_queries` (danh sách query thật đã bắt được trong sampling window, full text + `window_calls` + `window_total_exec_time_ms`). Khi field này không rỗng, PHẢI hiển thị nguyên văn từng query trong khối `<details>` riêng cho bảng đó (theo đúng convention Phần B ở trên: bảng chỉ có số liệu, query text nằm trong `<details>`, `<summary>` dạng `🔍 <code>{schema}.{table}</code> — {window_calls} lần gọi trong window`), KHÔNG tự suy diễn cột filter qua tên bảng hay qua fix template mẫu. Khi `related_queries` rỗng (sampling window không bắt được query nào chạm bảng này), ghi rõ điều đó trong phần solution thay vì im lặng bỏ qua — gợi ý chạy lại report vào giờ cao điểm nghiệp vụ.

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

Sử dụng template `assets/templates/template-solutions-report.md` để tạo report bao gồm:
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

| # | Dự Án    | Trục Xấu Nhất  | P0 | P1 | P2 | Solutions |
|---|----------|----------------|----|----|----|-----------|
| 1 | Project_A| 🟡 maintenance | 0  | 2  | 5  | 7         |
| 2 | Project_B| 🔴 db-health   | 3  | 5  | 8  | 16        |

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

- Không kết nối được DB / thiếu quyền đọc view / `pg_stat_statements` chưa cài: **đã được `scripts/analyzer.py` tự xử lý** — mỗi target lỗi được cô lập vào `collection_status`/`error`/`status: "skipped"` riêng của nó (xem Bước 3, mục 3)
- Nếu `CodePath` không tồn tại hoặc rỗng, hoặc không có trong `.env`: bỏ qua Code Report, chỉ tạo DB Report
- Nếu thư mục ngày đã tồn tại: hỏi user có muốn ghi đè không
- Nếu solution-index.md không tìm thấy: tạo solutions dựa trên general best practices

## Thư Mục Làm Việc

**BẮT BUỘC: Mọi file trung gian, script tạm mà agent tự tạo (cho Bước 5, 6, 8) PHẢI được tạo trong thư mục workspace hiện tại (cùng cấp với các thư mục dự án). KHÔNG ĐƯỢC dùng thư mục tạm hệ thống (C:\Users\...\Temp, /tmp, scratchpad, v.v.).**

Cụ thể:
- Bước 3 (thu thập dữ liệu DB) đã dùng script đóng gói sẵn `scripts/run_report.py` trong thư mục skill — **không** tạo script kết nối DB mới cho bước này.
- Nếu agent cần script tạm cho Bước 5/6/8 (vd. phân tích code, tổng hợp report): tạo tại `{workspace}/.scripts/`
- Thư mục `.scripts/` sẽ được tạo tự động nếu chưa có
- Sau khi chạy xong, có thể giữ lại script để user debug hoặc chạy lại

Ví dụ với workspace `e:\Skills`:
```
e:\Skills/
├── .scripts/
│   └── (script tạm nếu Bước 5/6/8 cần)
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
- `pglast` (parser SQL thật theo grammar PostgreSQL, dùng để phân loại an toàn câu lệnh trước khi EXPLAIN ANALYZE và quét policy RLS — không dựa vào regex)
- Quyền `SELECT` trên các system views (`pg_stat_*`, `pg_statio_*`)
- Quyền `EXECUTE` trên `pg_database_size()`, `pg_relation_size()`
- Nếu cần slow queries: extension `pg_stat_statements` phải được cài

## Report Templates

`DB_STATUS_REPORT.md`/`FINDINGS.md` được sinh tự động bởi `scripts/render.py` (Bước 3-4) — không dùng template Handlebars. 3 báo cáo còn lại vẫn do agent tự viết, dùng template chuẩn trong `assets/templates/`:
- `assets/templates/template-code-report.md` - Template báo cáo Code (Bước 5)
- `assets/templates/template-solutions-report.md` - Template giải pháp Performance (Bước 8)
- `assets/templates/template-combined-report.md` - Template báo cáo tổng hợp (Bước 6)

## SQL Query References

Các file `.sql` dưới đây là tài liệu tham khảo lịch sử (nội dung tương đương các query trong `scripts/collectors/*.py`) — Bước 3 KHÔNG còn chạy các file này trực tiếp:
- `references/queries-overview.sql` - Queries tổng quan database
- `references/queries-performance.sql` - Queries phân tích hiệu suất
- `references/queries-index.sql` - Queries phân tích index
- `references/remediation-policy.md` - Chính sách an toàn 5-tier cho mọi remediation SQL (vẫn dùng ở Bước 8)

## Solution Engine

Hệ thống tạo giải pháp dựa trên knowledge base đóng gói nội bộ tại `references/kb/` (nguồn: supabase-postgres-best-practices, xem `references/kb/_index.md`):
- `references/kb/solution-index.md` - Master mapping: 19 problem patterns → concrete fixes, mỗi pattern gắn `remediation_class`
- Mỗi fix bao gồm: SQL template, verification query, `recovery_or_rollback`, expected impact
- Priority rules: P0 (24h) → P1 (1 tuần) → P2 (1 tháng) → P3 (sprint sau)
- An toàn: xem `references/remediation-policy.md` cho 5-tier taxonomy và quy tắc gating theo capability

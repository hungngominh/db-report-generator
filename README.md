# DB Report Generator - Portable Package

## Yêu cầu hệ thống

- **Python 3.11+** (có pip)
- **PostgreSQL** (database cần phân tích)
- **Docker** (tùy chọn — chỉ cần nếu bạn muốn chạy bộ test tích hợp của skill)
- **Windows 10/11** (đã test) hoặc Linux/macOS

## Cấu trúc thư mục

```
db-report-portable/
├── README.md                        # File này
├── setup.bat                        # Script cài đặt tự động (Windows)
├── .agents/skills/db-report-generator/   # Skill: pipeline Python + hướng dẫn cho agent
│   ├── SKILL.md                     # Đặc tả skill đầy đủ (Bước 1-9)
│   ├── CLAUDE.md                    # Quy ước định dạng / sanitize() cho agent
│   ├── MIGRATION.md                 # Hướng dẫn nâng cấp v3 -> v4
│   ├── requirements.txt             # Dependency runtime (psycopg2-binary, pglast, jsonschema)
│   ├── requirements-dev.txt         # requirements.txt + pytest/pyyaml (để chạy bộ test)
│   ├── scripts/
│   │   ├── run_report.py            # CLI: .env -> report_data.json + DB_STATUS_REPORT.md + FINDINGS.md
│   │   ├── analyzer.py              # Kết nối + thu thập + đánh giá (thư viện, không có __main__)
│   │   ├── render.py                # report_data.json -> Markdown (tất định, không template)
│   │   ├── collectors/              # Mỗi collector 1 file (cache hit, dead tuples, RLS, v.v.)
│   │   └── lib/                     # db.py, envparse.py, schema.py, safety.py, v.v.
│   ├── references/                  # rules/*.json, kb/ (Solution Engine KB), SQL tham khảo
│   └── assets/templates/            # Template cho 3 báo cáo vấn đề agent tự viết (Code/Combined/Solutions)
└── sample-project/
    └── .env.sample                  # Mẫu file cấu hình
```

## Hướng dẫn cài đặt

### Bước 1: Giải nén vào workspace

Giải nén (hoặc copy) toàn bộ thư mục này vào nơi bạn muốn làm workspace. Ví dụ:

```
E:\Skills\          <-- workspace root
├── .agents\skills\db-report-generator\   <-- đã bao gồm KB tại references\kb\
└── YourProject\    <-- thư mục dự án của bạn
    └── .env        <-- file cấu hình DB
```

### Bước 2: Cài Python packages

```bash
cd .agents/skills/db-report-generator
pip install -r requirements.txt
```

### Bước 3: Tạo file .env cho dự án

Copy `sample-project/.env.sample` vào thư mục dự án và đổi tên thành `.env`:

```bash
cp sample-project/.env.sample YourProject/.env
```

Sửa các thông tin — ý nghĩa từng field:

**Bắt buộc:**
- `ServerName`: IP hoặc hostname của PostgreSQL server
- `CatalogName`: Tên database
- `Username` / `Password`: Tài khoản database (nên dùng tài khoản chỉ đọc — readonly)

**Tùy chọn — kết nối:**
- `Port`: Port PostgreSQL (mặc định `5432` nếu bỏ trống)

**Tùy chọn — phân tích code (dùng bởi agent ở Bước 5, chỉ khi chạy qua Claude Code CLI):**
- `CodePath`: Đường dẫn tới source code dự án, để agent grep/phân tích code (bỏ trống thì bỏ qua bước phân tích code)
- `ProjectName`: Tên dự án, hiển thị trong báo cáo
- `CodeLanguage` / `Framework`: Ngôn ngữ/framework của source code — ví dụ `csharp`/`dotnet`, `python`/`django`. Tùy chọn, agent sẽ tự auto-detect nếu bỏ trống

**Tùy chọn — sampling & EXPLAIN (mặc định đã an toàn, hầu hết không cần chỉnh):**
- `SamplingWindowSeconds` (mặc định `30`): Thời gian lấy mẫu (snapshot đầu/cuối) để tính các số liệu theo cửa sổ thời gian, ví dụ tốc độ query, tốc độ phát sinh dead tuple
- `ExplainMode` (mặc định `plan`): Chế độ chạy `EXPLAIN` cho các query chậm nhất — `off` (không chạy), `plan` (chỉ lấy execution plan, không thực thi query), `analyze` (chạy `EXPLAIN ANALYZE`, có thực thi query thật — chỉ nên bật khi đã hiểu rõ rủi ro, có allowlist và timeout)
- `ExplainTopN` (mặc định `5`): Số lượng query chậm nhất sẽ được chạy `EXPLAIN` để lấy plan
- `ExplainAnalyzeTopN` (mặc định `0`): Số lượng query trong top slow-query được phép chạy `EXPLAIN ANALYZE` — chỉ có hiệu lực khi `ExplainMode` là `analyze`; mặc định `0` nghĩa là không chạy ANALYZE trên query nào
- `ExplainStatementTimeoutMs` (mặc định `3000`): Timeout (ms) cho statement khi chạy `EXPLAIN`, tránh treo trên query nặng
- `ExplainLockTimeoutMs` (mặc định `500`): Timeout (ms) chờ lock khi chạy `EXPLAIN`, tránh block các query khác trên server

Xem thêm `.agents/skills/db-report-generator/MIGRATION.md` để biết chi tiết logic an toàn của `EXPLAIN`.

### Bước 4: Chạy thử

**Cách 1 - Qua Python trực tiếp (chỉ tạo DB_STATUS_REPORT.md/FINDINGS.md):**
```bash
set PYTHONIOENCODING=utf-8
cd .agents/skills/db-report-generator
python -m scripts.run_report E:\Skills\YourProject\.env E:\Skills\YourProject\yyyy-MM-dd
```

**Cách 2 - Qua Claude Code CLI (tạo cả CODE_ANALYSIS_REPORT.md/COMBINED_REPORT.md/PERFORMANCE_SOLUTIONS.md theo SKILL.md):**
```bash
/db-report-generator
```

## Kết quả sau khi chạy

Báo cáo được tạo trong thư mục dự án theo ngày:

```
YourProject/
├── .env
└── yyyy-MM-dd/
    ├── report_data.json             # Nguồn sự thật duy nhất (schema-valid)
    ├── DB_STATUS_REPORT.md          # Sinh tự động bởi scripts/render.py
    ├── FINDINGS.md                  # Sinh tự động bởi scripts/render.py
    ├── report_summary.json          # Sinh tự động bởi scripts/render.py
    ├── CODE_ANALYSIS_REPORT.md      # Agent tự viết (nếu có CodePath), qua Claude Code
    ├── COMBINED_REPORT.md           # Agent tự viết, qua Claude Code
    └── PERFORMANCE_SOLUTIONS.md     # Agent tự viết, qua Claude Code
```

## Lưu ý

- **PYTHONIOENCODING=utf-8**: Bắt buộc trên Windows để hiển thị tiếng Việt đúng
- **readonly_user**: Nên tạo tài khoản chỉ đọc (SELECT) để an toàn
- **pg_stat_statements**: Extension này nên được cài trên PostgreSQL server để có thông tin slow queries — nếu chưa có, `query_workload` sẽ báo `status: "skipped"` trong `report_data.json` thay vì lỗi
- **Firewall**: Đảm bảo máy chạy skill kết nối được tới PostgreSQL server (port 5432)
- **Nâng cấp từ bản v3 cũ hơn?** Xem `.agents/skills/db-report-generator/MIGRATION.md`

# DB Report Generator - Portable Package

## Yeu cau he thong

- **Python 3.8+** (co pip)
- **Claude Code CLI** (de chay skill qua `/db-report-generator`)
- **PostgreSQL** (database can phan tich)
- **Windows 10/11** (da test) hoac Linux/macOS

## Cau truc thu muc

```
db-report-portable/
├── README.md                 # File nay
├── setup.bat                 # Script cai dat tu dong (Windows)
├── .claude/skills/db-report-generator/   # Python runtime
│   ├── analyzer.py           # Core analyzer (ket noi DB + phan tich)
│   ├── run_skill.py          # Entry point - auto-scan workspace
│   ├── SKILL.md              # Dac ta skill day du
│   ├── skill_instructions.md # Huong dan cho Claude
│   ├── CLAUDE.md             # Quy tac cho agent
│   └── references/           # SQL templates + report templates
├── .agents/skills/
│   └── db-report-generator/  # Huong dan + templates cho agent (self-contained)
│       ├── SKILL.md
│       ├── CLAUDE.md
│       └── references/       # SQL queries + report templates
│           └── kb/           # Knowledge base: 31 bai PostgreSQL (nguon: supabase-postgres-best-practices)
├── .scripts/                 # Script ho tro
│   ├── generate_db_report.py # Script tao bao cao
│   ├── daily_report_automation.py  # Tu dong hang ngay
│   ├── run_daily_report.bat  # Bat file chay hang ngay
│   └── setup_task_scheduler.ps1    # Cai dat Task Scheduler
└── sample-project/
    └── .env.sample           # Mau file cau hinh
```

## Huong dan cai dat

### Buoc 1: Giai nen vao workspace

Giai nen (hoac copy) toan bo thu muc nay vao noi ban muon lam workspace. Vi du:

```
E:\Skills\          <-- workspace root
├── .claude\skills\db-report-generator\
├── .agents\skills\db-report-generator\   <-- da bao gom KB tai references\kb\
├── .scripts\
└── YourProject\    <-- thu muc du an cua ban
    └── .env        <-- file cau hinh DB
```

### Buoc 2: Cai Python packages

```bash
pip install psycopg2-binary requests
```

### Buoc 3: Tao file .env cho du an

Copy `sample-project/.env.sample` vao thu muc du an va doi ten thanh `.env`:

```bash
cp sample-project/.env.sample YourProject/.env
```

Sua cac thong tin:
- `ServerName`: IP hoac hostname cua PostgreSQL server
- `CatalogName`: Ten database
- `Username` / `Password`: Tai khoan database (nen dung readonly)
- `Port`: Port PostgreSQL (mac dinh 5432)
- `CodePath`: Duong dan toi source code du an (de phan tich code)
- `ProjectName`: Ten du an
- `CodeLanguage`: Ngon ngu code (csharp, python, java, typescript...)
- `Framework`: Framework (dotnet, django, spring, nextjs...)
- `IISBaseURL`: URL web server xem bao cao (tuy chon)
- `GoogleChatWebhook`: Webhook URL gui thong bao (tuy chon)

### Buoc 4: Chay thu

**Cach 1 - Qua Python truc tiep:**
```bash
set PYTHONIOENCODING=utf-8
cd .claude/skills/db-report-generator
python analyzer.py E:\Skills\YourProject\.env
```

**Cach 2 - Auto-scan workspace:**
```bash
set PYTHONIOENCODING=utf-8
cd .claude/skills/db-report-generator
python run_skill.py
```

**Cach 3 - Qua Claude Code CLI:**
```bash
/db-report-generator
```

### Buoc 5 (Tuy chon): Cai dat chay tu dong hang ngay

Chay PowerShell voi quyen Admin:
```powershell
powershell -ExecutionPolicy Bypass -File .scripts/setup_task_scheduler.ps1
```

## Ket qua sau khi chay

Bao cao duoc tao trong thu muc du an theo ngay:

```
YourProject/
├── .env
├── 2026-02-12/
│   ├── DB_STATUS_REPORT.md          # Bao cao tinh trang database
│   ├── CODE_ANALYSIS_REPORT.md      # Phan tich code
│   ├── COMBINED_REPORT.md           # Bao cao tong hop
│   ├── PERFORMANCE_SOLUTIONS.md     # Giai phap cu the
│   └── web.config                   # Cho IIS (neu co)
├── reports.json                     # Danh sach ngay co bao cao
├── index.html                       # Dashboard web (neu co IISBaseURL)
└── viewer.html                      # Xem bao cao web (neu co IISBaseURL)
```

## Luu y

- **PYTHONIOENCODING=utf-8**: Bat buoc tren Windows de hien thi tieng Viet dung
- **readonly_user**: Nen tao tai khoan chi doc (SELECT) de an toan
- **pg_stat_statements**: Extension nay nen duoc cai tren PostgreSQL server de co thong tin slow queries
- **Firewall**: Dam bao may chay skill ket noi duoc toi PostgreSQL server (port 5432)

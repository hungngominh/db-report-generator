# DB Report Generator - Portable Package

## Yeu cau he thong

- **Python 3.11+** (co pip)
- **PostgreSQL** (database can phan tich)
- **Docker** (tuy chon — chi can neu ban muon chay bo test tich hop cua skill)
- **Windows 10/11** (da test) hoac Linux/macOS

## Cau truc thu muc

```
db-report-portable/
├── README.md                        # File nay
├── setup.bat                        # Script cai dat tu dong (Windows)
├── .agents/skills/db-report-generator/   # Skill: pipeline Python + huong dan cho agent
│   ├── SKILL.md                     # Dac ta skill day du (Buoc 1-9)
│   ├── CLAUDE.md                    # Quy uoc dinh dang / sanitize() cho agent
│   ├── MIGRATION.md                 # Huong dan nang cap v3 -> v4
│   ├── requirements.txt             # Dependency runtime (psycopg2-binary, pglast, jsonschema)
│   ├── requirements-dev.txt         # requirements.txt + pytest/pyyaml (de chay bo test)
│   ├── scripts/
│   │   ├── run_report.py            # CLI: .env -> report_data.json + DB_STATUS_REPORT.md + FINDINGS.md
│   │   ├── analyzer.py              # Ket noi + thu thap + danh gia (thu vien, khong co __main__)
│   │   ├── render.py                # report_data.json -> Markdown (tat dinh, khong template)
│   │   ├── collectors/              # Moi collector 1 file (cache hit, dead tuples, RLS, v.v.)
│   │   └── lib/                     # db.py, envparse.py, schema.py, safety.py, v.v.
│   ├── references/                  # rules/*.json, kb/ (Solution Engine KB), SQL tham khao
│   └── assets/templates/            # Template cho 3 bao cao van de agent tu viet (Code/Combined/Solutions)
└── sample-project/
    └── .env.sample                  # Mau file cau hinh
```

## Huong dan cai dat

### Buoc 1: Giai nen vao workspace

Giai nen (hoac copy) toan bo thu muc nay vao noi ban muon lam workspace. Vi du:

```
E:\Skills\          <-- workspace root
├── .agents\skills\db-report-generator\   <-- da bao gom KB tai references\kb\
└── YourProject\    <-- thu muc du an cua ban
    └── .env        <-- file cau hinh DB
```

### Buoc 2: Cai Python packages

```bash
cd .agents/skills/db-report-generator
pip install -r requirements.txt
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
- `CodePath`: Duong dan toi source code du an (de phan tich code, tuy chon)
- `ProjectName`: Ten du an
- `SamplingWindowSeconds` / `ExplainMode` / `ExplainTopN` / `ExplainAnalyzeTopN` / `ExplainStatementTimeoutMs` / `ExplainLockTimeoutMs`: tuy chon, xem `.agents/skills/db-report-generator/MIGRATION.md` de biet gia tri mac dinh va y nghia

### Buoc 4: Chay thu

**Cach 1 - Qua Python truc tiep (chi tao DB_STATUS_REPORT.md/FINDINGS.md):**
```bash
set PYTHONIOENCODING=utf-8
cd .agents/skills/db-report-generator
python -m scripts.run_report E:\Skills\YourProject\.env E:\Skills\YourProject\2026-07-20
```

**Cach 2 - Qua Claude Code CLI (tao ca CODE_ANALYSIS_REPORT.md/COMBINED_REPORT.md/PERFORMANCE_SOLUTIONS.md theo SKILL.md):**
```bash
/db-report-generator
```

## Ket qua sau khi chay

Bao cao duoc tao trong thu muc du an theo ngay:

```
YourProject/
├── .env
└── 2026-07-20/
    ├── report_data.json             # Nguon su that duy nhat (schema-valid)
    ├── DB_STATUS_REPORT.md          # Sinh tu dong boi scripts/render.py
    ├── FINDINGS.md                  # Sinh tu dong boi scripts/render.py
    ├── report_summary.json          # Sinh tu dong boi scripts/render.py
    ├── CODE_ANALYSIS_REPORT.md      # Agent tu viet (neu co CodePath), qua Claude Code
    ├── COMBINED_REPORT.md           # Agent tu viet, qua Claude Code
    └── PERFORMANCE_SOLUTIONS.md     # Agent tu viet, qua Claude Code
```

## Luu y

- **PYTHONIOENCODING=utf-8**: Bat buoc tren Windows de hien thi tieng Viet dung
- **readonly_user**: Nen tao tai khoan chi doc (SELECT) de an toan
- **pg_stat_statements**: Extension nay nen duoc cai tren PostgreSQL server de co thong tin slow queries — neu chua co, `query_workload` se bao `status: "skipped"` trong `report_data.json` thay vi loi
- **Firewall**: Dam bao may chay skill ket noi duoc toi PostgreSQL server (port 5432)
- **Nang cap tu ban v3 cu hon?** Xem `.agents/skills/db-report-generator/MIGRATION.md`

# Phase 7 (P7) — Packaging & Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Skill root (state this explicitly in every implementer dispatch):** `E:\Work\db-report-portable\.agents\skills\db-report-generator\`. P5's Task 1 implementer wrote files at the repo root by mistake because this path wasn't spelled out — do not repeat that.

**Goal:** Close out the db-report-generator v4 upgrade by making the tested Python pipeline (`scripts/analyzer.py` → `scripts/render.py`) the thing `SKILL.md` actually invokes (instead of hand-run raw SQL + legacy Handlebars templates), adding a real CLI entrypoint, closing the golden-test/PG-version-matrix coverage gaps the spec calls for, retiring dead template/doc content, and making the repo's README/setup.bat/CI describe the layout that actually exists on disk.

**Architecture:** No new subsystems. This phase is glue and packaging: (1) a thin `scripts/run_report.py` CLI wrapping the existing `parse_env` → `analyzer.analyze` → `render.render_all` call chain that nothing currently drives from a command line; (2) `SKILL.md` rewritten so Bước 3/4 call that CLI instead of describing 12 sub-sections of raw SQL; (3) template inventory pruned to what `render.py` doesn't already supersede, moved to `assets/templates/`; (4) golden-test and Docker-Postgres-matrix coverage extended to the scenarios the spec names; (5) root `README.md`/`setup.bat`/CI brought in line with the real `.agents/skills/db-report-generator/` tree (there is no `.claude/skills/`, no `.scripts/`, no `run_skill.py` anywhere in this repo).

**Tech Stack:** Python 3.11+ (stdlib `json`/`pathlib`/`sys` only for the new CLI — no new runtime dependency), pytest (existing test tooling), Docker (existing `tests/pgcontainer.py` mechanism), GitHub Actions.

## Global Constraints

- Skill root is `E:\Work\db-report-portable\.agents\skills\db-report-generator\` — all `scripts/`, `references/`, `tests/`, `SKILL.md`, `CLAUDE.md` paths below are relative to it unless stated as repo-root (`E:\Work\db-report-portable\`).
- All P7 work commits directly to `master` — no feature branch (established P0–P6 precedent, confirmed again for P7).
- **Never push to any remote without explicit user permission** — a real IP address (`REDACTED-DB-HOST`) is still present in this repo's git history; this is a standing constraint, not a P7-specific one.
- No placeholders anywhere (code, docs, tests) — every value in this plan is the literal value to write.
- TDD: for every task, write/update the test first, confirm it fails against the current file, then make the change, then confirm the test passes.
- The `sanitize()` function and the `<details>`/`<summary>` query-text convention (`SKILL.md` old lines 274–393) must be **relocated, not deleted** — it still governs `CODE_ANALYSIS_REPORT.md`, `COMBINED_REPORT.md`, `PERFORMANCE_SOLUTIONS.md`, which remain agent-authored Markdown.
- Do not touch the 5-axis model (`db-health`/`query-performance`/`maintenance`/`connections`/`security-rls`), the 5-tier remediation taxonomy, or `references/rules/*.json` — those are P3/P6 territory and already correct.
- `references/report-data.schema.json` needs **no changes** in this phase — its `diagnostic.metrics` field is `{"type": "array"}` with no item-shape constraint, so no new collector or fixture needs a schema edit.
- Every new/changed Python file must pass `python -m pytest -q` from the skill root with **zero new failures** beyond the 6 known pre-existing Docker/live-Postgres integration failures documented in the P5/P6 progress ledger (`test_analyzer` schema-valid Decimal-serialization case, `sampler_live` x2, `stale_stats`, `stat_io`, `wal_hot`).

---

## File Structure

New files:
- `scripts/run_report.py` — CLI entrypoint (`run()` + `main()`)
- `tests/unit/test_run_report.py`
- `assets/templates/template-code-report.md` (moved from `references/`)
- `assets/templates/template-combined-report.md` (moved from `references/`)
- `assets/templates/template-solutions-report.md` (moved from `references/`)
- `tests/fixtures/report_data.no_pgss.sample.json`
- `tests/fixtures/report_data.selfhosted_superuser.sample.json`
- `tests/fixtures/report_data.dead_tuples_100pct.sample.json`
- `tests/golden/DB_STATUS_REPORT.no_pgss.md`
- `tests/golden/DB_STATUS_REPORT.selfhosted_superuser.md`
- `tests/golden/DB_STATUS_REPORT.dead_tuples_100pct.md`
- `tests/unit/test_pgcontainer.py`
- `MIGRATION.md` (skill root)
- `requirements.txt` (skill root, runtime-only)
- `E:\Work\db-report-portable\.github\workflows\tests.yml` (moved from skill dir)

Deleted files:
- `references/template-db-report.md`
- `.agents/skills/db-report-generator/.github/workflows/tests.yml` (moved, not left behind)

Modified files:
- `SKILL.md`
- `scripts/render.py`
- `tests/unit/test_render.py`
- `tests/fixtures/report_data.sample.json`
- `tests/golden/DB_STATUS_REPORT.md`
- `tests/unit/test_skill_docs.py`
- `tests/pgcontainer.py`
- `requirements-dev.txt`
- `E:\Work\db-report-portable\README.md`
- `E:\Work\db-report-portable\setup.bat`
- `E:\Work\db-report-portable\sample-project\.env.sample`

---

### Task 1: `scripts/run_report.py` CLI entrypoint

**Files:**
- Create: `scripts/run_report.py`
- Test: `tests/unit/test_run_report.py`

**Interfaces:**
- Consumes: `scripts.lib.envparse.parse_env(source) -> DbConfig` (raises `ValueError` on missing/invalid keys), `scripts.analyzer.analyze(configs: list, *, redaction_mode="redact") -> dict`, `scripts.render.render_all(data: dict, out_dir: Path) -> None`.
- Produces: `run_report.run(env_path: Path, out_dir: Path) -> dict` and `run_report.main(argv: list[str]) -> int`, used nowhere else in this phase except documentation (`SKILL.md` Task 2, `README.md` Task 7 both tell the user to invoke it as `python -m scripts.run_report <env> <out_dir>`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_run_report.py`:

```python
import json

from scripts import run_report

ENV_JSON = json.dumps({
    "ServerName": "localhost", "Port": 5432, "CatalogName": "app_prod",
    "Username": "postgres", "Password": "secret",
})

FAKE_REPORT = {
    "schema_version": "4.0", "tool_version": "4.0.0",
    "run": {"run_id": "r", "started_at": "t0", "completed_at": "t1"},
    "redaction_mode": "redact",
    "targets": [
        {
            "target_id": "app_prod", "database": "app_prod", "collection_status": "ok", "error": None,
            "capabilities": {}, "diagnostics": {},
        }
    ],
}


def test_run_writes_report_data_json_and_rendered_files(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(ENV_JSON, encoding="utf-8")
    out_dir = tmp_path / "2026-07-20"

    captured = {}

    def fake_analyze(configs, **kwargs):
        captured["configs"] = configs
        return FAKE_REPORT

    monkeypatch.setattr(run_report.analyzer, "analyze", fake_analyze)

    result = run_report.run(env_path, out_dir)

    assert result == FAKE_REPORT
    assert captured["configs"][0].database == "app_prod"
    data = json.loads((out_dir / "report_data.json").read_text(encoding="utf-8"))
    assert data == FAKE_REPORT
    assert (out_dir / "DB_STATUS_REPORT.md").exists()
    assert (out_dir / "FINDINGS.md").exists()
    assert (out_dir / "report_summary.json").exists()


def test_main_rejects_missing_env_file(tmp_path, capsys):
    missing = tmp_path / "nope.env"
    out_dir = tmp_path / "out"
    rc = run_report.main(["run_report", str(missing), str(out_dir)])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_main_rejects_wrong_arg_count(capsys):
    rc = run_report.main(["run_report", "only-one-arg"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_main_reports_invalid_env_as_error(tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text(json.dumps({"ServerName": "localhost"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = run_report.main(["run_report", str(env_path), str(out_dir)])
    assert rc == 1
    assert "invalid .env" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_run_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_report'` (or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/run_report.py`:

```python
"""CLI entrypoint: .env -> report_data.json + rendered reports."""
import json
import sys
from pathlib import Path

from scripts import analyzer, render
from scripts.lib.envparse import parse_env

USAGE = "usage: python -m scripts.run_report <path-to-.env> <output-dir>"


def run(env_path: Path, out_dir: Path) -> dict:
    cfg = parse_env(Path(env_path))
    report = analyzer.analyze([cfg])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_data.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    render.render_all(report, out_dir)
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    env_path, out_dir = Path(argv[1]), Path(argv[2])
    if not env_path.exists():
        print(f"error: .env file not found: {env_path}", file=sys.stderr)
        return 2
    try:
        run(env_path, out_dir)
    except ValueError as exc:
        print(f"error: invalid .env: {exc}", file=sys.stderr)
        return 1
    print(f"OK: report written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_run_report.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_report.py tests/unit/test_run_report.py
git commit -m "feat(p7): add scripts/run_report.py CLI entrypoint (P7 Task 1)"
```

---

### Task 2: Rewire `SKILL.md` Bước 3+4 to invoke the Python pipeline

**Files:**
- Modify: `SKILL.md` (old lines 118–538: Bước 3 "Kết Nối Và Thu Thập Dữ Liệu" sub-sections 3.1–3.12 + Bước 4 "Tạo Báo Cáo Database"; old lines ~818–826: "Xử Lý Lỗi")
- Test: `tests/unit/test_skill_docs.py`

**Interfaces:**
- Consumes: `scripts/run_report.py`'s CLI contract from Task 1 (`python -m scripts.run_report <env> <out_dir>`).
- Produces: nothing consumed by later tasks — this is a documentation-only change. Task 3 depends on the fact that this task's new text no longer references `references/template-db-report.md` (confirmed below: the only old reference to that file, at old line 531, sits inside the span this task replaces).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_skill_docs.py`:

```python
def test_skill_md_step3_invokes_python_pipeline_not_raw_sql(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "python -m scripts.run_report" in text
    assert "#### 3.4 Top 20 Slow Queries" not in text
    assert "FROM pg_stat_user_tables" not in text


def test_skill_md_keeps_sanitize_and_details_convention(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "def sanitize(value):" in text
    assert "KHÔNG BAO GIỜ đặt query text" in text


def test_skill_md_error_handling_delegates_to_analyzer(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    idx = text.index("## Xử Lý Lỗi")
    section = text[idx:idx + 800]
    assert "analyzer.py" in section
    assert "ghi log lỗi, tạo báo cáo rỗng với thông tin lỗi" not in section
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_skill_docs.py -k "step3_invokes or sanitize_and_details or error_handling_delegates" -v`
Expected: all 3 FAIL against the current `SKILL.md`.

- [ ] **Step 3: Replace SKILL.md's Bước 3 + Bước 4**

Find the span starting at the line `### Bước 3: Kết Nối Và Thu Thập Dữ Liệu` and ending immediately before the line `### Bước 5: Phân Tích Code (CODE_ANALYSIS_REPORT.md)` (this is the entire old Bước 3 with its 12 sub-sections 3.1–3.12, including the sanitize/`<details>` convention block, plus old Bước 4). Replace that entire span with:

```markdown
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
```

- [ ] **Step 4: Update "Xử Lý Lỗi"**

Find:
```markdown
## Xử Lý Lỗi

- Nếu không kết nối được DB: ghi log lỗi, tạo báo cáo rỗng với thông tin lỗi, tiếp tục dự án tiếp theo
- Nếu `pg_stat_statements` chưa cài: bỏ qua phần slow queries, ghi nhận trong báo cáo
- Nếu không có quyền đọc một số view: ghi nhận phần nào bị thiếu
- Nếu `CodePath` không tồn tại hoặc rỗng: bỏ qua Code Report, chỉ tạo DB Report
- Nếu `CodePath` không có trong .env: chỉ tạo DB Report
- Nếu thư mục ngày đã tồn tại: hỏi user có muốn ghi đè không
- Nếu solution-index.md không tìm thấy: tạo solutions dựa trên general best practices
```

Replace with:
```markdown
## Xử Lý Lỗi

- Không kết nối được DB / thiếu quyền đọc view / `pg_stat_statements` chưa cài: **đã được `scripts/analyzer.py` tự xử lý** — mỗi target lỗi được cô lập vào `collection_status`/`error`/`status: "skipped"` riêng của nó (xem Bước 3, mục 3)
- Nếu `CodePath` không tồn tại hoặc rỗng, hoặc không có trong `.env`: bỏ qua Code Report, chỉ tạo DB Report
- Nếu thư mục ngày đã tồn tại: hỏi user có muốn ghi đè không
- Nếu solution-index.md không tìm thấy: tạo solutions dựa trên general best practices
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: all pass, including the 3 new tests and all pre-existing ones (no path/text collisions — verified none of the pre-existing tests in this file assert on Bước 3/Bước 4/"Xử Lý Lỗi" content).

- [ ] **Step 6: Commit**

```bash
git add SKILL.md tests/unit/test_skill_docs.py
git commit -m "feat(p7): rewire SKILL.md Bước 3-4 to invoke scripts.run_report instead of raw SQL (P7 Task 2)"
```

---

### Task 3: Retire `template-db-report.md`, move remaining templates to `assets/templates/`, version-bump sweep

**Files:**
- Delete: `references/template-db-report.md`
- Move: `references/template-code-report.md` → `assets/templates/template-code-report.md`
- Move: `references/template-combined-report.md` → `assets/templates/template-combined-report.md`
- Move: `references/template-solutions-report.md` → `assets/templates/template-solutions-report.md`
- Modify: `SKILL.md` (frontmatter version, intro line, 3 body path references, "Report Templates"/"SQL Query References" sections)
- Modify: `tests/unit/test_skill_docs.py` (path fixes for moved templates)

**Interfaces:**
- Consumes: nothing from Task 2 except the fact that Task 2 already removed the only reference to `references/template-db-report.md` in the old Bước 4 (old line 531) — confirmed via `grep -n "template-db-report" SKILL.md` returning only that one now-deleted occurrence plus the "Report Templates" list entry this task also removes.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_skill_docs.py`:

```python
def test_templates_moved_to_assets_dir(skill_dir):
    for name in ("template-code-report.md", "template-combined-report.md", "template-solutions-report.md"):
        assert (skill_dir / "assets" / "templates" / name).exists(), f"{name} not found under assets/templates/"
        assert not (skill_dir / "references" / name).exists(), f"{name} still present under references/"


def test_template_db_report_removed(skill_dir):
    assert not (skill_dir / "references" / "template-db-report.md").exists()


def test_skill_md_version_bumped_to_4(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert 'version: "4.0.0"' in text
    assert 'version: "3.0.0"' not in text


def test_skill_md_report_templates_section_points_to_assets(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    idx = text.index("## Report Templates")
    section = text[idx:idx + 600]
    assert "assets/templates/template-code-report.md" in section
    assert "assets/templates/template-combined-report.md" in section
    assert "assets/templates/template-solutions-report.md" in section
    assert "references/template-db-report.md" not in section
```

Then fix the 6 existing path references in `tests/unit/test_skill_docs.py` (the pre-existing tests `test_combined_report_template_has_no_legacy_0_100_score`, `test_combined_report_template_has_axis_matrix_placeholders`, `test_solutions_template_has_dangerous_section_excluded_from_scripts`, `test_solutions_template_uses_recovery_or_rollback`, `test_solutions_template_footer_version_v4` — replace every `skill_dir / "references" / "template-combined-report.md"` with `skill_dir / "assets" / "templates" / "template-combined-report.md"`, and every `skill_dir / "references" / "template-solutions-report.md"` with `skill_dir / "assets" / "templates" / "template-solutions-report.md"`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: the 4 new tests FAIL (files not yet moved, version not yet bumped); the 5 path-updated pre-existing tests FAIL with `FileNotFoundError` (files still at their old `references/` path).

- [ ] **Step 3: Move the template files**

```bash
mkdir -p assets/templates
git mv references/template-code-report.md assets/templates/template-code-report.md
git mv references/template-combined-report.md assets/templates/template-combined-report.md
git mv references/template-solutions-report.md assets/templates/template-solutions-report.md
git rm references/template-db-report.md
```

- [ ] **Step 4: Update SKILL.md frontmatter + intro**

Find:
```yaml
metadata:
  author: NGOMI
  version: "3.0.0"
  date: February 2026
```
Replace with:
```yaml
metadata:
  author: NGOMI
  version: "4.0.0"
  date: July 2026
```

Find:
```markdown
**v3.0 - Tích hợp Solution Engine (KB đóng gói nội bộ tại `references/kb/`, nguồn: `supabase-postgres-best-practices`)**: Mỗi vấn đề phát hiện được đi kèm giải pháp cụ thể với priority, SQL fix, code fix, và expected impact. Skill **self-contained** — không phụ thuộc skill KB ngoài.
```
Replace with:
```markdown
**v4.0 - Kiến trúc Python tất định** (`scripts/analyzer.py` → collectors → `scripts/rules.py` → `scripts/render.py`) sinh `DB_STATUS_REPORT.md`/`FINDINGS.md` không cần agent tự viết SQL, cộng Solution Engine (KB đóng gói nội bộ tại `references/kb/`, nguồn: `supabase-postgres-best-practices`) đi kèm mỗi finding với priority, SQL fix, code fix, và expected impact. Skill **self-contained** — không phụ thuộc skill KB ngoài.
```

- [ ] **Step 5: Update the 3 in-body template path references**

Find (Bước 5): `Sử dụng template từ \`references/template-code-report.md\`.`
Replace: `Sử dụng template từ \`assets/templates/template-code-report.md\`.`

Find (Bước 6): `Sử dụng template từ \`references/template-combined-report.md\`.`
Replace: `Sử dụng template từ \`assets/templates/template-combined-report.md\`.`

Find (Bước 8.8): `Sử dụng template \`references/template-solutions-report.md\` để tạo report bao gồm:`
Replace: `Sử dụng template \`assets/templates/template-solutions-report.md\` để tạo report bao gồm:`

- [ ] **Step 6: Rewrite "Report Templates" and "SQL Query References" sections**

Find:
```markdown
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
- `references/remediation-policy.md` - Chính sách an toàn 5-tier cho mọi remediation SQL ⭐ NEW
```

Replace with:
```markdown
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_docs.py -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add -A -- assets references SKILL.md tests/unit/test_skill_docs.py
git commit -m "feat(p7): retire template-db-report.md, move remaining templates to assets/templates/, bump SKILL.md to v4.0.0 (P7 Task 3)"
```

---

### Task 4: Golden fixture variants + `sampling` window display

**Files:**
- Modify: `scripts/render.py` (`render_db_status`)
- Modify: `tests/fixtures/report_data.sample.json` (add `sampling` to `t-main`)
- Modify: `tests/golden/DB_STATUS_REPORT.md` (regenerate via `UPDATE_GOLDEN=1`)
- Modify: `tests/unit/test_render.py` (new tests)
- Create: `tests/fixtures/report_data.no_pgss.sample.json`
- Create: `tests/fixtures/report_data.selfhosted_superuser.sample.json`
- Create: `tests/fixtures/report_data.dead_tuples_100pct.sample.json`
- Create: `tests/golden/DB_STATUS_REPORT.no_pgss.md` (generated via `UPDATE_GOLDEN=1`)
- Create: `tests/golden/DB_STATUS_REPORT.selfhosted_superuser.md` (generated via `UPDATE_GOLDEN=1`)
- Create: `tests/golden/DB_STATUS_REPORT.dead_tuples_100pct.md` (generated via `UPDATE_GOLDEN=1`)

**Interfaces:**
- Consumes: `scripts.lib.schema.validate_report(data: dict) -> None` (raises on invalid), `scripts.render.render_db_status`/`render_findings`/`build_summary` (unchanged signatures).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_render.py`:

```python
def test_sampling_window_is_displayed(sample_report):
    out = render_db_status(sample_report)
    assert "Cửa sổ lấy mẫu: 30s" in out
    assert "2026-07-16T00:00:00Z → 2026-07-16T00:00:30Z" in out


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_no_pgss_scenario_golden():
    fixture = _load_fixture("report_data.no_pgss.sample.json")
    _check("DB_STATUS_REPORT.no_pgss.md", render_db_status(fixture))


def test_selfhosted_superuser_scenario_is_schema_valid_and_deterministic():
    from scripts.lib import schema

    fixture = _load_fixture("report_data.selfhosted_superuser.sample.json")
    schema.validate_report(fixture)
    out1 = render_db_status(fixture)
    out2 = render_db_status(fixture)
    assert out1 == out2
    _check("DB_STATUS_REPORT.selfhosted_superuser.md", out1)


def test_dead_tuples_100pct_scenario_shows_red():
    fixture = _load_fixture("report_data.dead_tuples_100pct.sample.json")
    out = render_db_status(fixture)
    assert "🔴 red" in out
    assert "maintenance.dead_tuples_pct" in out
    _check("DB_STATUS_REPORT.dead_tuples_100pct.md", out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_render.py -v`
Expected: `test_sampling_window_is_displayed` FAILS (no sampling line rendered yet); the 3 new scenario tests FAIL with `FileNotFoundError` (fixtures don't exist yet) and the pre-existing `test_db_status_golden` still PASSES (unaffected until Step 3).

- [ ] **Step 3: Add `sampling` to the base fixture**

In `tests/fixtures/report_data.sample.json`, in the `t-main` target object, add a `"sampling"` key immediately after `"capabilities"`:

```json
      "capabilities": {"server_version_num": 160004, "is_superuser": false, "vendor": "supabase", "managed": true},
      "sampling": {"window_seconds": 30, "sample1_at": "2026-07-16T00:00:00Z", "sample2_at": "2026-07-16T00:00:30Z", "reset_detected": false},
```

- [ ] **Step 4: Render the sampling window in `render_db_status`**

In `scripts/render.py`, find:
```python
        if target["collection_status"] == "error":
            lines.append(f"> 🔴 Lỗi thu thập: {target.get('error') or 'không rõ'}")
            lines.append("")
            continue
        for block in sorted_block_names(target["diagnostics"]):
```
Replace with:
```python
        if target["collection_status"] == "error":
            lines.append(f"> 🔴 Lỗi thu thập: {target.get('error') or 'không rõ'}")
            lines.append("")
            continue
        sampling = target.get("sampling")
        if sampling:
            reset_note = " · ⚪ phát hiện reset pg_stat_statements giữa 2 mẫu" if sampling["reset_detected"] else ""
            lines.append(
                f"> Cửa sổ lấy mẫu: {sampling['window_seconds']}s "
                f"({sampling['sample1_at']} → {sampling['sample2_at']}){reset_note}"
            )
            lines.append("")
        for block in sorted_block_names(target["diagnostics"]):
```

- [ ] **Step 5: Create the 3 new fixtures**

Create `tests/fixtures/report_data.no_pgss.sample.json`:
```json
{
  "schema_version": "4.0",
  "tool_version": "4.0.0",
  "run": {"run_id": "run-fixture-no-pgss", "started_at": "2026-07-16T00:00:00Z", "completed_at": "2026-07-16T00:00:05Z"},
  "redaction_mode": "redact",
  "targets": [
    {
      "target_id": "t-no-pgss",
      "database": "legacy_db",
      "collection_status": "ok",
      "error": null,
      "capabilities": {"server_version_num": 150003, "is_superuser": false, "vendor": "self-hosted", "managed": false},
      "diagnostics": {
        "overview": {
          "collector_version": "1.0",
          "scope": "database",
          "status": "ok",
          "reason": null,
          "quality": {"sampling_valid": true, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": [
            {"finding_id": "db.reachable", "severity": "info", "assessment": "green", "confidence": "measured", "title": "Kết nối và thu thập thành công", "evidence_ids": [], "remediation_ids": []}
          ]
        },
        "query_workload": {
          "collector_version": "1.0",
          "scope": "database",
          "status": "skipped",
          "reason": "pg_stat_statements chưa được cài",
          "quality": {"sampling_valid": false, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": []
        }
      }
    }
  ]
}
```

Create `tests/fixtures/report_data.selfhosted_superuser.sample.json`:
```json
{
  "schema_version": "4.0",
  "tool_version": "4.0.0",
  "run": {"run_id": "run-fixture-selfhosted-su", "started_at": "2026-07-16T00:00:00Z", "completed_at": "2026-07-16T00:00:05Z"},
  "redaction_mode": "redact",
  "targets": [
    {
      "target_id": "t-selfhosted-su",
      "database": "onprem_erp",
      "collection_status": "ok",
      "error": null,
      "capabilities": {"server_version_num": 140011, "is_superuser": true, "vendor": "self-hosted", "managed": false},
      "diagnostics": {
        "overview": {
          "collector_version": "1.0",
          "scope": "database",
          "status": "ok",
          "reason": null,
          "quality": {"sampling_valid": true, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": [
            {"finding_id": "db.reachable", "severity": "info", "assessment": "green", "confidence": "measured", "title": "Kết nối và thu thập thành công", "evidence_ids": [], "remediation_ids": []}
          ]
        }
      }
    }
  ]
}
```

Create `tests/fixtures/report_data.dead_tuples_100pct.sample.json`:
```json
{
  "schema_version": "4.0",
  "tool_version": "4.0.0",
  "run": {"run_id": "run-fixture-dead-tuples-100", "started_at": "2026-07-16T00:00:00Z", "completed_at": "2026-07-16T00:00:05Z"},
  "redaction_mode": "redact",
  "targets": [
    {
      "target_id": "t-dead-tuples",
      "database": "batch_db",
      "collection_status": "ok",
      "error": null,
      "capabilities": {"server_version_num": 160004, "is_superuser": false, "vendor": "supabase", "managed": true},
      "diagnostics": {
        "dead_tuples": {
          "collector_version": "1.0",
          "scope": "table",
          "status": "ok",
          "reason": null,
          "quality": {"sampling_valid": true, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [
            {"schema": "public", "table": "events_log", "dead_pct": 100.0, "n_dead_tup": 500000, "n_live_tup": 0}
          ],
          "findings": [
            {"finding_id": "maintenance.dead_tuples_pct", "severity": "warning", "assessment": "red", "confidence": "measured", "title": "Tỷ lệ dead tuple cao", "evidence_ids": [], "remediation_ids": []}
          ]
        }
      }
    }
  ]
}
```

- [ ] **Step 6: Regenerate golden files**

Run:
```bash
UPDATE_GOLDEN=1 python -m pytest tests/unit/test_render.py -v
```
This writes `tests/golden/DB_STATUS_REPORT.md` (updated for the new sampling line) and the 3 new golden files. Then re-run without the env var to confirm stability:
```bash
python -m pytest tests/unit/test_render.py -v
```
Expected: all pass, output identical to the just-written golden files (no drift).

- [ ] **Step 7: Commit**

```bash
git add scripts/render.py tests/fixtures tests/golden tests/unit/test_render.py
git commit -m "feat(p7): render target.sampling window + add 3 golden-test scenario variants (P7 Task 4)"
```

---

### Task 5: Fix the PG14-18 test matrix mechanism

**Files:**
- Modify: `tests/pgcontainer.py`
- Modify: `.agents/skills/db-report-generator/.github/workflows/tests.yml` (still at its current in-skill-dir location; Task 7 moves it to repo root)
- Create: `tests/unit/test_pgcontainer.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PostgresContainer()`'s default `image` now reads `DBREPORT_TEST_PG_IMAGE` env var (default `"postgres:16"`, unchanged from today when the var is unset) — Task 7's CI activation step relies on this env var being read.

**Context — why this is the real gap:** `.github/workflows/tests.yml`'s `pg: [14, 15, 16, 17, 18]` matrix currently spins up a GitHub Actions `services: postgres:` container per job, but nothing in `conftest.py`/`tests/pgcontainer.py` ever connects to it — `PostgresContainer.__init__` hardcodes `image: str = "postgres:16"` and launches its **own**, separate `docker run` container regardless of which matrix leg is running. So today, all 5 CI matrix legs would (if the workflow were active) exercise the same PG16 container the tests always launch — the matrix runs 5x for no additional coverage. There's also a second, unrelated bug: GitHub Actions' `services:` shorthand cannot pass `-c shared_preload_libraries=pg_stat_statements` the way `PostgresContainer.__enter__`'s own `docker run` already does — so the `services:` container the workflow currently starts couldn't run the `pg_stat_statements`-dependent tests anyway. The fix below drops the redundant/broken `services:` block and drives the *existing, working* `PostgresContainer` docker-run path (which already preloads `pg_stat_statements` correctly) from the matrix variable instead.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pgcontainer.py`:

```python
from tests.pgcontainer import PostgresContainer


def test_default_image_is_pg16_without_env_var(monkeypatch):
    monkeypatch.delenv("DBREPORT_TEST_PG_IMAGE", raising=False)
    assert PostgresContainer().image == "postgres:16"


def test_image_honors_env_var_override(monkeypatch):
    monkeypatch.setenv("DBREPORT_TEST_PG_IMAGE", "postgres:14")
    assert PostgresContainer().image == "postgres:14"


def test_explicit_image_arg_overrides_env_var(monkeypatch):
    monkeypatch.setenv("DBREPORT_TEST_PG_IMAGE", "postgres:14")
    assert PostgresContainer(image="postgres:18").image == "postgres:18"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_pgcontainer.py -v`
Expected: `test_image_honors_env_var_override` FAILS (`AssertionError: 'postgres:16' != 'postgres:14'`) — the env var is not read yet.

- [ ] **Step 3: Read the env var in `PostgresContainer.__init__`**

In `tests/pgcontainer.py`, find:
```python
"""Throwaway Docker Postgres for live-DB tests. Skips cleanly without Docker."""
import shutil
import socket
import subprocess
import time

import psycopg2
```
Replace with:
```python
"""Throwaway Docker Postgres for live-DB tests. Skips cleanly without Docker."""
import os
import shutil
import socket
import subprocess
import time

import psycopg2
```

Find:
```python
class PostgresContainer:
    def __init__(self, image: str = "postgres:16"):
        self.image = image
```
Replace with:
```python
class PostgresContainer:
    def __init__(self, image: str | None = None):
        self.image = image or os.environ.get("DBREPORT_TEST_PG_IMAGE", "postgres:16")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_pgcontainer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Fix the CI workflow's matrix mechanism**

In `.agents/skills/db-report-generator/.github/workflows/tests.yml`, find:
```yaml
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        pg: [14, 15, 16, 17, 18]
    services:
      postgres:
        image: postgres:${{ matrix.pg }}
        env: {POSTGRES_PASSWORD: postgres}
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    defaults:
      run:
        working-directory: .agents/skills/db-report-generator
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest -q
```
Replace with:
```yaml
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        pg: [14, 15, 16, 17, 18]
    defaults:
      run:
        working-directory: .agents/skills/db-report-generator
    env:
      DBREPORT_TEST_PG_IMAGE: postgres:${{ matrix.pg }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest -q
```

(No `services:` block — `tests/pgcontainer.py`'s own `docker run`, already invoked by the session-scoped `_pg_container` fixture in `conftest.py`, now launches the matrix-selected version with `pg_stat_statements` correctly preloaded via its existing `-c shared_preload_libraries=pg_stat_statements` flag. GitHub-hosted `ubuntu-latest` runners have Docker available, so `docker_available()` returns `True` there.)

- [ ] **Step 6: Run the full unit suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: same pass/fail counts as before this task (3 new passes from Step 4/`test_pgcontainer.py`; no change to the 6 known pre-existing Docker/live-Postgres failures, since those require Docker to actually be running locally to execute at all — if Docker isn't running in this environment, they still `pytest.skip`, unaffected by this change).

- [ ] **Step 7: Commit**

```bash
git add tests/pgcontainer.py tests/unit/test_pgcontainer.py .agents/skills/db-report-generator/.github/workflows/tests.yml
git commit -m "fix(p7): drive PG14-18 CI matrix through PostgresContainer's own docker run instead of a broken/redundant services: block (P7 Task 5)"
```

---

### Task 6: `MIGRATION.md` (v3 → v4)

**Files:**
- Create: `MIGRATION.md` (skill root)
- Test: `tests/unit/test_skill_docs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks (Task 7's README links to this file by relative path `.agents/skills/db-report-generator/MIGRATION.md`).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_skill_docs.py`:

```python
def test_migration_md_exists_and_covers_v3_to_v4(skill_dir):
    p = skill_dir / "MIGRATION.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for marker in (
        "0-100", "assets/templates", "template-db-report.md",
        "recovery_or_rollback", "EXPLAIN", "RLS",
        "scripts/run_report.py", "report_data.json",
    ):
        assert marker in text, f"MIGRATION.md missing coverage of: {marker}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_skill_docs.py -k migration -v`
Expected: FAIL — `MIGRATION.md` does not exist.

- [ ] **Step 3: Write `MIGRATION.md`**

Create `MIGRATION.md`:

```markdown
# Migration Guide — db-report-generator v3 → v4

`db-report-generator` moved from an "agent hand-writes SQL and fills a Handlebars template" model (v3) to a deterministic Python pipeline (v4): `scripts/analyzer.py` connects and collects, `scripts/rules.py` evaluates findings against `references/rules/*.json`, `scripts/render.py` writes `DB_STATUS_REPORT.md`/`FINDINGS.md`/`report_summary.json`. This document is for anyone who has an existing v3-era workspace, notes, or automation built around this skill.

## What triggers this migration

You're affected if you have any of the following from before this upgrade:
- A copy of `references/template-db-report.md` you were filling in by hand or via your own script
- Notes or scripts that reference a `Code Quality /100` or any other `.../100` composite score
- Automation that parses `**Rollback:**` sections out of `PERFORMANCE_SOLUTIONS.md`
- A workspace still pointing at `.claude/skills/db-report-generator/` (that path never existed as a real Python runtime in this repo — see `README.md`'s Buoc 1/4 for the corrected layout)

## Report generation: what changed

| | v3 | v4 |
|---|---|---|
| DB status report | Agent hand-runs 12 raw-SQL sections, fills `references/template-db-report.md` | `python -m scripts.run_report <.env> <out_dir>` generates `DB_STATUS_REPORT.md` + `FINDINGS.md` + `report_summary.json` deterministically |
| Source of truth | The rendered Markdown itself | `report_data.json` (schema: `references/report-data.schema.json`) — Markdown is a rendering of it |
| Code/Combined/Solutions reports | Agent-authored from templates | Unchanged — still agent-authored, templates now live in `assets/templates/` (moved from `references/`) |
| Scoring | Composite `0-100` score | 5-axis model (`db-health`, `query-performance`, `maintenance`, `connections`, `security-rls`), each 🟢/🟡/🔴/⚪/➖ + confidence tier (`measured`/`estimated`/`heuristic`) — no single number |
| Remediation SQL | Ad hoc `**Rollback:**` heading | `recovery_or_rollback` field, gated by a 5-tier `remediation_class` taxonomy (`references/remediation-policy.md`) — `dangerous`-tier fixes are excluded from any "run now" script block and require manual review |
| Slow query diagnosis | `pg_stat_statements` text only | Same, plus `EXPLAIN` plans attached automatically (plan-only by default; `ANALYZE` requires explicit opt-in + allowlist — see `ExplainMode` below) |
| Index suggestions | Manual reading of `queries-index.sql` output | `scripts/index_advisor.py` suggests column-level indexes (composite/partial/covering) from parsed slow-query predicates, checking for existing indexes first |
| RLS | Not covered | `scripts/collectors/rls_policies.py` detects unwrapped `auth.uid()`/`current_setting()` re-evaluated per row, and RLS policy columns lacking a supporting index |
| Schema hygiene | Not covered | Missing primary key, oversized UUID PK, `timestamp` without time zone |

## Config: new optional `.env` fields (v4)

All are optional — omitting them falls back to the defaults below, so an unmodified v3-era `.env` file still works:

```json
{
  "SamplingWindowSeconds": 30,
  "ExplainMode": "plan",
  "ExplainTopN": 5,
  "ExplainAnalyzeTopN": 0,
  "ExplainStatementTimeoutMs": 3000,
  "ExplainLockTimeoutMs": 500
}
```

`ExplainMode` is `off` (don't run EXPLAIN), `plan` (default — EXPLAIN without ANALYZE, never executes the query), or `analyze` (explicit opt-in; still gated by an allowlist and a real PostgreSQL-grammar parser classification, not a regex, before any query is allowed to run with ANALYZE).

## File layout changes

- `references/template-db-report.md` — **removed**. `scripts/render.py` supersedes it; there is nothing to migrate to, since its output is now generated, not filled in.
- `references/template-code-report.md`, `references/template-combined-report.md`, `references/template-solutions-report.md` — **moved** to `assets/templates/`. If you had local overrides of these files, move them to the same path under `assets/templates/`.
- `queries-overview.sql`, `queries-performance.sql`, `queries-index.sql` (`references/`) — kept as historical human-readable reference material only; the agent's Bước 3 no longer runs these files.

## If you have automation scraping the old reports

Anything parsing `DB_STATUS_REPORT.md`'s old 11-section Handlebars layout, a `.../100` score, or a `**Rollback:**` heading needs updating: read `report_data.json` directly instead (stable schema, `jsonschema`-validated on every run) rather than parsing Markdown.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_skill_docs.py -k migration -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add MIGRATION.md tests/unit/test_skill_docs.py
git commit -m "docs(p7): add MIGRATION.md covering v3->v4 report/config/template changes (P7 Task 6)"
```

---

### Task 7: README.md + setup.bat rewrite, runtime `requirements.txt`, CI activation

**Files:**
- Modify (full rewrite): `E:\Work\db-report-portable\README.md`
- Modify: `E:\Work\db-report-portable\setup.bat`
- Create: `requirements.txt` (skill root, runtime-only)
- Modify: `requirements-dev.txt` (skill root, reference the new runtime file instead of duplicating it)
- Modify: `E:\Work\db-report-portable\sample-project\.env.sample` (document the 6 new optional v4 fields)
- Move: `.agents/skills/db-report-generator/.github/workflows/tests.yml` → `E:\Work\db-report-portable\.github\workflows\tests.yml`

**Interfaces:**
- Consumes: Task 1's `scripts/run_report.py` CLI contract, Task 5's fixed CI matrix mechanism, Task 6's `MIGRATION.md`.
- Produces: nothing (final task).

**Context — verified real repo layout (do not describe anything not confirmed to exist):** `.claude/` exists at repo root but contains only `scheduled_tasks.lock` — no `.claude/skills/` directory, no `run_skill.py`, no `skill_instructions.md` anywhere in this repo. `.scripts/` does not exist. `.agents/skills/db-report-generator/` is real and contains `SKILL.md`, `CLAUDE.md`, `MIGRATION.md` (Task 6), `scripts/`, `references/`, `assets/templates/` (Task 3), `tests/`, `requirements-dev.txt`, `docker-compose.pg.yml`, `pytest.ini`. `sample-project/.env.sample` exists at repo root. The `requests` package (referenced by the old README/setup.bat `pip install psycopg2-binary requests` line) is not imported anywhere in `scripts/` — it belonged to a Google-Chat-webhook automation feature that isn't part of this skill.

- [ ] **Step 1: Write the failing tests**

Create a new test file `tests/unit/test_root_docs.py` **at the skill root** (`skill_dir` fixture only resolves paths under the skill directory, so these tests reach up via `skill_dir.parent.parent.parent` — 3 levels up from `.agents/skills/db-report-generator/` to the repo root):

```python
def test_readme_describes_real_agents_skills_layout(skill_dir):
    repo_root = skill_dir.parent.parent.parent
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    assert ".claude/skills" not in text
    assert "run_skill.py" not in text
    assert ".agents/skills/db-report-generator" in text
    assert "python -m scripts.run_report" in text


def test_setup_bat_does_not_reference_claude_skills(skill_dir):
    repo_root = skill_dir.parent.parent.parent
    text = (repo_root / "setup.bat").read_text(encoding="utf-8")
    assert ".claude\\skills" not in text
    assert ".scripts" not in text
    assert "requirements.txt" in text


def test_runtime_requirements_txt_has_no_dev_only_deps(skill_dir):
    text = (skill_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "psycopg2-binary" in text
    assert "pglast" in text
    assert "jsonschema" in text
    assert "pytest" not in text
    assert "pyyaml" not in text.lower()


def test_requirements_dev_includes_runtime_requirements(skill_dir):
    text = (skill_dir / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in text
    assert "pytest" in text


def test_env_sample_documents_new_v4_fields():
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    data = json.loads((repo_root / "sample-project" / ".env.sample").read_text(encoding="utf-8"))
    for key in ("SamplingWindowSeconds", "ExplainMode", "ExplainTopN"):
        assert key in data


def test_ci_workflow_active_at_repo_root(skill_dir):
    repo_root = skill_dir.parent.parent.parent
    p = repo_root / ".github" / "workflows" / "tests.yml"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "TEMPLATE" not in text
    assert not (skill_dir / ".github").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_root_docs.py -v`
Expected: all 6 FAIL against the current repo state.

- [ ] **Step 3: Create the runtime `requirements.txt` and slim `requirements-dev.txt`**

Create `requirements.txt`:
```
jsonschema>=4.18
psycopg2-binary>=2.9
pglast==8.2
```

Replace the full contents of `requirements-dev.txt` (currently `jsonschema>=4.18\npytest>=7.4\npyyaml>=6.0\npsycopg2-binary>=2.9\npglast==8.2\n`) with:
```
-r requirements.txt
pytest>=7.4
pyyaml>=6.0
```

- [ ] **Step 4: Document the new v4 `.env` fields in the sample**

In `sample-project/.env.sample`, find:
```json
{
  "ServerName": "your-db-server-ip",
  "CatalogName": "your_database_name",
  "Username": "readonly_user",
  "Password": "your_password",
  "Port": 5432,
  "MaxPoolSize": 500,
  "CodePath": "D:/Work/YourProject",
  "ProjectName": "YourProject",
  "CodeLanguage": "csharp",
  "Framework": "dotnet",
  "IISBaseURL": "http://your-server:port",
  "GoogleChatWebhook": "https://chat.googleapis.com/v1/spaces/YOUR_SPACE/messages?key=YOUR_KEY&token=YOUR_TOKEN"
}
```
Replace with:
```json
{
  "ServerName": "your-db-server-ip",
  "CatalogName": "your_database_name",
  "Username": "readonly_user",
  "Password": "your_password",
  "Port": 5432,
  "CodePath": "D:/Work/YourProject",
  "ProjectName": "YourProject",
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
(`MaxPoolSize`, `IISBaseURL`, `GoogleChatWebhook` removed — none are read by `scripts/lib/envparse.py::parse_env`, confirmed by its `_REQUIRED`/`DbConfig` field list; they belonged to the unrelated dashboard/webhook automation described in the old README, which this skill's Python pipeline does not implement.)

- [ ] **Step 5: Rewrite `README.md`**

Replace the entire contents of `E:\Work\db-report-portable\README.md` with:

```markdown
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
│   └── assets/templates/            # Template cho 3 bao cao van do agent tu viet (Code/Combined/Solutions)
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
```

- [ ] **Step 6: Fix `setup.bat`**

Find:
```batchfile
:: Install dependencies
echo.
echo Dang cai dat Python packages...
pip install psycopg2-binary requests >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong the cai dat packages. Thu chay: pip install psycopg2-binary requests
    pause
    exit /b 1
)
echo [OK] psycopg2-binary va requests da cai dat
```
Replace with:
```batchfile
:: Install dependencies
echo.
echo Dang cai dat Python packages...
pip install -r "%~dp0.agents\skills\db-report-generator\requirements.txt" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong the cai dat packages. Thu chay: pip install -r .agents\skills\db-report-generator\requirements.txt
    pause
    exit /b 1
)
echo [OK] psycopg2-binary, pglast, jsonschema da cai dat
```

Find:
```batchfile
:: Create directories
if not exist "%WORKSPACE%\.claude\skills\db-report-generator\references" mkdir "%WORKSPACE%\.claude\skills\db-report-generator\references"
if not exist "%WORKSPACE%\.agents\skills\db-report-generator\references" mkdir "%WORKSPACE%\.agents\skills\db-report-generator\references"
if not exist "%WORKSPACE%\.scripts" mkdir "%WORKSPACE%\.scripts"

:: Copy claude skills
xcopy /s /y /q "%~dp0.claude\skills\db-report-generator\*" "%WORKSPACE%\.claude\skills\db-report-generator\" >nul
echo [OK] Claude skill files

:: Copy agent skills
xcopy /s /y /q "%~dp0.agents\skills\db-report-generator\*" "%WORKSPACE%\.agents\skills\db-report-generator\" >nul
echo [OK] Agent skill instructions (bao gom KB tai references\kb\)

:: Copy scripts
xcopy /s /y /q "%~dp0.scripts\*" "%WORKSPACE%\.scripts\" >nul
echo [OK] Helper scripts
```
Replace with:
```batchfile
:: Create directories
if not exist "%WORKSPACE%\.agents\skills\db-report-generator\references" mkdir "%WORKSPACE%\.agents\skills\db-report-generator\references"

:: Copy agent skill (SKILL.md, CLAUDE.md, MIGRATION.md, scripts/, references/, assets/templates/)
xcopy /s /y /q "%~dp0.agents\skills\db-report-generator\*" "%WORKSPACE%\.agents\skills\db-report-generator\" >nul
echo [OK] Agent skill (scripts + references + assets/templates, bao gom KB tai references\kb\)
```

Find:
```batchfile
echo Buoc tiep theo:
echo   1. Tao file .env trong thu muc du an
echo      (Xem mau tai: %~dp0sample-project\.env.sample)
echo.
echo   2. Chay bao cao:
echo      cd %WORKSPACE%\.claude\skills\db-report-generator
echo      set PYTHONIOENCODING=utf-8
echo      python analyzer.py [duong-dan-toi-.env]
echo.
echo   3. Hoac dung Claude Code:
echo      /db-report-generator
echo.
```
Replace with:
```batchfile
echo Buoc tiep theo:
echo   1. Tao file .env trong thu muc du an
echo      (Xem mau tai: %~dp0sample-project\.env.sample)
echo.
echo   2. Chay bao cao:
echo      cd %WORKSPACE%\.agents\skills\db-report-generator
echo      set PYTHONIOENCODING=utf-8
echo      python -m scripts.run_report [duong-dan-toi-.env] [thu-muc-ket-qua]
echo.
echo   3. Hoac dung Claude Code (tao ca Code/Combined/Solutions report):
echo      /db-report-generator
echo.
```

- [ ] **Step 7: Activate CI — move the workflow to repo root**

```bash
mkdir -p ../../../../.github/workflows
git mv .agents/skills/db-report-generator/.github/workflows/tests.yml ../../../../.github/workflows/tests.yml
```
(paths above are relative to the skill root `.agents/skills/db-report-generator/`; run from the repo root instead if that's simpler: `git mv .agents/skills/db-report-generator/.github/workflows/tests.yml .github/workflows/tests.yml`)

Then, in the moved `E:\Work\db-report-portable\.github\workflows\tests.yml`, remove the now-inapplicable template header. Find:
```yaml
# TEMPLATE — GitHub Actions only runs workflows at repo-root .github/workflows/.
# Copy this file there to activate CI (spec §17).
name: tests
```
Replace with:
```yaml
name: tests
```

- [ ] **Step 8: Run tests to verify they pass**

Run (from the skill root): `python -m pytest tests/unit/test_root_docs.py -v`
Expected: all 6 passed.

Then run the full suite to confirm no regressions: `python -m pytest -q`
Expected: same known-failure count as the P6 baseline (6 pre-existing Docker/live-Postgres failures), zero new failures.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt requirements-dev.txt tests/unit/test_root_docs.py
git -C ../../../../ add README.md setup.bat sample-project/.env.sample .github/workflows/tests.yml
git -C ../../../../ status
git commit -m "docs(p7): rewrite README/setup.bat for the real .agents/skills/ layout, add runtime requirements.txt, activate CI at repo root (P7 Task 7)"
```
(Run the commit from the repo root `E:\Work\db-report-portable\` so both the skill-relative and repo-root paths are captured in one commit — adjust the `git add`/`-C` invocations to whichever shell you're in; the important part is a single commit covering both the skill-dir and repo-root changes together, since they're one logical change.)

---

## Roadmap gate cross-check (P7.3 batch isolation)

The roadmap's P7 gate list includes "1 DB die không hỏng run" (batch isolation, §0.A5/P7.3). This is **already implemented and already tested** — `scripts/analyzer.py::_analyze_target` isolates each target's exceptions into that target's own `collection_status`/`error`, and `tests/unit/test_analyzer.py::test_analyze_output_is_schema_valid_and_isolates_failures` (plus `test_analyze_runs_multiple_targets_concurrently`, from the B4 concurrency work) already cover it. No new task is needed for this gate item — it is called out here so the final whole-branch review doesn't flag it as an unaddressed roadmap requirement.

## Post-plan: pre-flight scan note

Before dispatching Task 1, the controller should re-scan this plan once for internal conflicts per `subagent-driven-development`'s pre-flight step. One thing to flag explicitly if not already resolved: Task 7 Step 9's commit spans two directories (skill dir + repo root) in one `git commit` — if the executing agent's tooling can't easily do a single cross-directory commit, splitting it into two sequential commits (skill-dir first, repo-root second) is an acceptable, low-risk deviation from this step's literal text; note it in the task's completion report rather than treating it as a spec deviation requiring escalation.

## After all tasks: final review and close-out

1. Dispatch the final whole-branch review (most capable model — opus) per `subagent-driven-development`, using `scripts/review-package` against the merge-base (this phase has no separate branch — merge-base is the P6 final commit `9db7c6d`) through the last P7 commit.
2. Update `.superpowers/sdd/progress.md` with a `# P7 Progress Ledger` section following the same style as P5/P6 (one line per task with commit range + review verdict, plus a final whole-branch-review entry).
3. Update memory files `db-report-v4-progress.md` and `MEMORY.md` to record P7 complete — this is the last roadmapped phase (P-1 → P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7); the v4 upgrade project is feature-complete once P7 closes.
4. Use `superpowers:finishing-a-development-branch` — expected outcome, per P0-P6 precedent, is "already on `master`, nothing to merge"; any push still requires explicit user permission (real IP address still present in git history, per the standing security constraint).

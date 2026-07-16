# Phase −1: Contract Freeze & Safety Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đóng băng hợp đồng dữ liệu v4 (JSON Schema multi-target) và dựng bộ test harness deterministic — nền tảng mà mọi phase sau (P0→P7) test dựa vào; hoàn toàn thuần Python, không đụng live DB.

**Architecture:** Một JSON Schema (Draft 2020-12) định nghĩa `report_data.json`. Các module thuần hàm trong `scripts/lib/` (validate, sort, redact, invariants, safety) + `scripts/render.py` (report_data.json → báo cáo Markdown deterministic). Test bằng `pytest`, golden snapshot cho render.

**Tech Stack:** Python ≥3.10, `pytest`, `jsonschema` (Draft 2020-12), `pyyaml` (chỉ để test parse config YAML). DB driver: KHÔNG dùng ở phase này.

**Nguồn:** [Spec §0.A1/A5/A7/B3, §3.1, P7.1](../specs/2026-07-16-db-report-generator-v4-upgrade.md) · [Roadmap](2026-07-16-db-report-generator-v4-roadmap.md) (phase P−1).

## Global Constraints

- **Determinism:** render byte-ổn định trên cùng input; KHÔNG nhúng timestamp/random vào body báo cáo (bỏ qua `run.*` khi render). (§0.A1)
- **Enum cố định:** collector `status = ok|partial|skipped|error`; `assessment = green|yellow|red|unknown|not_applicable`; `confidence = measured|estimated|heuristic`; `severity = info|notice|warning|critical`. `skipped`/thiếu activity không bao giờ = green. (§0.A5)
- **Confidence invalidation (B3):** diagnostic có `quality.sampling_valid=false` ⇒ mọi finding của nó `confidence=heuristic` **và** `assessment=unknown`. (§0.B3)
- **Safety invariant:** cung cấp gate `is_readonly_sql()` để P0+ dùng; phase này chỉ dựng + test gate, chưa có collector. (§0.A3/A6/N4)
- **Redaction:** không để password/DSN/host lọt ra output; `report_data.json` mang `redaction_mode`. (bảo mật review)
- **Ngôn ngữ báo cáo:** tiếng Việt (giữ tiếng Anh cho tên bảng/cột/SQL/finding_id/tên file).
- **Vị trí code:** tất cả nằm trong `.agents/skills/db-report-generator/` (skill self-contained, portable). pytest chạy từ thư mục skill này.

**Quy ước chạy lệnh (quan trọng — cwd khác nhau):**
- **SKILL_DIR** = `.agents/skills/db-report-generator` (nơi có `conftest.py`/`pytest.ini`).
- Lệnh **pip/pytest** chạy **từ SKILL_DIR**: `cd .agents/skills/db-report-generator && python -m pytest -q`.
- Lệnh **git** (`init`/`add`/`commit`) chạy **từ repo root** (`e:\Work\db-report-portable`) với path repo-root-relative như ghi trong mỗi step.
- Biến môi trường inline (`UPDATE_GOLDEN=1 python …`) là cú pháp **bash** (dùng Bash tool). PowerShell tương đương: `$env:UPDATE_GOLDEN=1; python …; Remove-Item Env:UPDATE_GOLDEN`.
- Mọi commit dùng footer:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

## File structure (tạo trong phase này)

```
.agents/skills/db-report-generator/
├── conftest.py                         # sys.path + fixtures cho pytest
├── requirements-dev.txt
├── pytest.ini
├── references/
│   └── report-data.schema.json         # Task 1
├── scripts/
│   ├── __init__.py
│   ├── render.py                       # Task 7
│   └── lib/
│       ├── __init__.py
│       ├── schema.py                   # Task 1
│       ├── sortkeys.py                 # Task 3
│       ├── redact.py                   # Task 4
│       ├── invariants.py               # Task 5
│       └── safety.py                   # Task 6
├── tests/
│   ├── fixtures/report_data.sample.json  # Task 2
│   ├── golden/                          # Task 7 (generated)
│   ├── unit/
│   │   ├── test_smoke.py               # Task 0
│   │   ├── test_schema.py              # Task 1
│   │   ├── test_fixture.py             # Task 2
│   │   ├── test_sortkeys.py            # Task 3
│   │   ├── test_redact.py              # Task 4
│   │   ├── test_invariants.py          # Task 5
│   │   ├── test_safety.py              # Task 6
│   │   ├── test_render.py              # Task 7
│   │   └── test_harness_config.py      # Task 8
│   └── README.md                        # Task 8
├── docker-compose.pg.yml                # Task 8
└── .github/workflows/tests.yml          # Task 8 (template)
```

Repo root cũng nhận `.gitignore` (Task 0).

---

### Task 0: Scaffolding + pytest harness

**Files:**
- Create: `.gitignore` (repo root)
- Create: `SKILL_DIR/requirements-dev.txt`
- Create: `SKILL_DIR/pytest.ini`
- Create: `SKILL_DIR/conftest.py`
- Create: `SKILL_DIR/scripts/__init__.py`, `SKILL_DIR/scripts/lib/__init__.py`
- Test: `SKILL_DIR/tests/unit/test_smoke.py`

**Interfaces:**
- Produces: `conftest.py` đặt `SKILL_DIR` lên `sys.path` và cung cấp fixture `sample_report` (đọc `tests/fixtures/report_data.sample.json`) + fixture `skill_dir` (Path). Mọi task sau import `from scripts.lib.X import ...` và dùng các fixture này.

- [ ] **Step 1: Xác nhận git + tạo .gitattributes**

Git đã được khởi tạo ở pre-flight (repo đang ở branch `feature/db-report-v4`; `.gitignore` đã commit trong baseline). Chỉ cần thêm `.gitattributes` để **ép LF** — bảo đảm golden byte-ổn định cross-platform (Windows/CI Linux).

Create `.gitattributes` (repo root):
```gitattributes
* text=auto eol=lf
```

Verify (từ repo root):
```bash
git rev-parse --abbrev-ref HEAD   # kỳ vọng: feature/db-report-v4
```

- [ ] **Step 2: requirements-dev.txt + pytest.ini**

Create `SKILL_DIR/requirements-dev.txt`:
```
jsonschema>=4.18
pytest>=7.4
pyyaml>=6.0
```

Create `SKILL_DIR/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: conftest.py + package markers**

Create `SKILL_DIR/scripts/__init__.py` (empty) and `SKILL_DIR/scripts/lib/__init__.py` (empty).

Create `SKILL_DIR/conftest.py`:
```python
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))


@pytest.fixture
def skill_dir() -> Path:
    return SKILL_DIR


@pytest.fixture
def sample_report() -> dict:
    p = SKILL_DIR / "tests" / "fixtures" / "report_data.sample.json"
    return json.loads(p.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Smoke test**

Create `SKILL_DIR/tests/unit/test_smoke.py`:
```python
def test_pytest_runs():
    assert True
```

- [ ] **Step 5: Cài deps + chạy**

Run (từ SKILL_DIR):
```bash
pip install -r requirements-dev.txt
python -m pytest tests/unit/test_smoke.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add .gitattributes .agents/skills/db-report-generator/{requirements-dev.txt,pytest.ini,conftest.py,scripts,tests}
git commit -m "chore(p-1): pytest harness + scaffolding" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 1: JSON Schema v4 + validator

**Files:**
- Create: `SKILL_DIR/references/report-data.schema.json`
- Create: `SKILL_DIR/scripts/lib/schema.py`
- Test: `SKILL_DIR/tests/unit/test_schema.py`

**Interfaces:**
- Produces: `schema.py` với `load_schema() -> dict`, `validate_report(data: dict) -> None` (raise `jsonschema.exceptions.ValidationError` nếu sai), `validation_errors(data: dict) -> list[str]` (list message, rỗng nếu hợp lệ). Mọi task sau validate bằng các hàm này.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_schema.py`:
```python
import pytest

from scripts.lib.schema import load_schema, validate_report, validation_errors

MINIMAL = {
    "schema_version": "4.0",
    "tool_version": "4.0.0",
    "run": {"run_id": "r1", "started_at": "2026-07-16T00:00:00Z", "completed_at": None},
    "redaction_mode": "none",
    "targets": [],
}


def test_schema_loads():
    schema = load_schema()
    assert schema["$schema"].endswith("2020-12/schema")


def test_minimal_valid():
    validate_report(MINIMAL)  # không raise
    assert validation_errors(MINIMAL) == []


def test_bad_schema_version_rejected():
    bad = {**MINIMAL, "schema_version": "3.0"}
    assert validation_errors(bad)


def test_bad_assessment_enum_rejected():
    bad = {
        **MINIMAL,
        "targets": [
            {
                "target_id": "t1",
                "database": "db",
                "collection_status": "ok",
                "capabilities": {},
                "diagnostics": {
                    "overview": {
                        "collector_version": "1.0",
                        "scope": "database",
                        "status": "ok",
                        "quality": {
                            "sampling_valid": True,
                            "reset_detected": False,
                            "insufficient_activity": False,
                            "truncated": False,
                        },
                        "metrics": [],
                        "findings": [
                            {
                                "finding_id": "x",
                                "severity": "warning",
                                "assessment": "blue",  # invalid
                                "confidence": "measured",
                                "evidence_ids": [],
                                "remediation_ids": [],
                            }
                        ],
                    }
                },
            }
        ],
    }
    assert validation_errors(bad)
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_schema.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.lib.schema`).

- [ ] **Step 3: Viết schema JSON**

Create `SKILL_DIR/references/report-data.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://db-report-generator/schemas/report-data-4.0.json",
  "title": "db-report-generator report_data v4",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "tool_version", "run", "redaction_mode", "targets"],
  "properties": {
    "schema_version": {"const": "4.0"},
    "tool_version": {"type": "string", "minLength": 1},
    "run": {
      "type": "object",
      "additionalProperties": false,
      "required": ["run_id", "started_at", "completed_at"],
      "properties": {
        "run_id": {"type": "string", "minLength": 1},
        "started_at": {"type": "string"},
        "completed_at": {"type": ["string", "null"]}
      }
    },
    "redaction_mode": {"enum": ["none", "hash", "redact"]},
    "targets": {"type": "array", "items": {"$ref": "#/$defs/target"}}
  },
  "$defs": {
    "target": {
      "type": "object",
      "additionalProperties": false,
      "required": ["target_id", "database", "collection_status", "capabilities", "diagnostics"],
      "properties": {
        "target_id": {"type": "string", "minLength": 1},
        "database": {"type": "string"},
        "collection_status": {"enum": ["ok", "partial", "error"]},
        "error": {"type": ["string", "null"]},
        "capabilities": {"type": "object"},
        "diagnostics": {
          "type": "object",
          "additionalProperties": {"$ref": "#/$defs/diagnostic"}
        }
      }
    },
    "diagnostic": {
      "type": "object",
      "additionalProperties": false,
      "required": ["collector_version", "scope", "status", "quality", "metrics", "findings"],
      "properties": {
        "collector_version": {"type": "string"},
        "scope": {"enum": ["cluster", "database", "table", "index", "query"]},
        "status": {"enum": ["ok", "partial", "skipped", "error"]},
        "reason": {"type": ["string", "null"]},
        "quality": {"$ref": "#/$defs/quality"},
        "metrics": {"type": "array"},
        "findings": {"type": "array", "items": {"$ref": "#/$defs/finding"}}
      }
    },
    "quality": {
      "type": "object",
      "additionalProperties": false,
      "required": ["sampling_valid", "reset_detected", "insufficient_activity", "truncated"],
      "properties": {
        "sampling_valid": {"type": "boolean"},
        "reset_detected": {"type": "boolean"},
        "insufficient_activity": {"type": "boolean"},
        "truncated": {"type": "boolean"}
      }
    },
    "finding": {
      "type": "object",
      "additionalProperties": false,
      "required": ["finding_id", "severity", "assessment", "confidence", "evidence_ids", "remediation_ids"],
      "properties": {
        "finding_id": {"type": "string", "minLength": 1},
        "severity": {"enum": ["info", "notice", "warning", "critical"]},
        "assessment": {"enum": ["green", "yellow", "red", "unknown", "not_applicable"]},
        "confidence": {"enum": ["measured", "estimated", "heuristic"]},
        "title": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "remediation_ids": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

- [ ] **Step 4: Viết validator**

Create `SKILL_DIR/scripts/lib/schema.py`:
```python
"""Validate report_data.json against the frozen v4 JSON Schema."""
import functools
import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "references" / "report-data.schema.json"


@functools.lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema())


def validate_report(data: dict) -> None:
    """Raise jsonschema.exceptions.ValidationError on the first violation."""
    _validator().validate(data)


def validation_errors(data: dict) -> list[str]:
    """Return all validation messages (empty list == valid)."""
    return [e.message for e in sorted(_validator().iter_errors(data), key=str)]
```

- [ ] **Step 5: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_schema.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/db-report-generator/{references/report-data.schema.json,scripts/lib/schema.py,tests/unit/test_schema.py}
git commit -m "feat(p-1): freeze report_data v4 JSON Schema + validator" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Golden fixture (multi-target, edge cases)

**Files:**
- Create: `SKILL_DIR/tests/fixtures/report_data.sample.json`
- Test: `SKILL_DIR/tests/unit/test_fixture.py`

**Interfaces:**
- Produces: fixture `report_data.sample.json` — dùng bởi Task 5/7 và fixture `sample_report`. Cấu trúc: 2 target (`t-main` ok, `t-analytics` error/timeout); target ok có 3 diagnostic: `overview` (ok, finding green measured), `query_workload` (ok, finding yellow measured), `wraparound` (ok nhưng `sampling_valid=false` → finding unknown heuristic), và `wait_events` (skipped, thiếu quyền).

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_fixture.py`:
```python
from scripts.lib.schema import validation_errors


def test_fixture_valid_against_schema(sample_report):
    assert validation_errors(sample_report) == []


def test_fixture_is_multi_target(sample_report):
    ids = {t["target_id"] for t in sample_report["targets"]}
    assert {"t-main", "t-analytics"} <= ids


def test_fixture_has_error_target(sample_report):
    err = [t for t in sample_report["targets"] if t["collection_status"] == "error"]
    assert err and err[0]["diagnostics"] == {}


def test_fixture_has_skipped_and_invalid_sampling(sample_report):
    main = next(t for t in sample_report["targets"] if t["target_id"] == "t-main")
    diags = main["diagnostics"]
    assert diags["wait_events"]["status"] == "skipped"
    assert diags["wraparound"]["quality"]["sampling_valid"] is False
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_fixture.py -v`
Expected: FAIL (`FileNotFoundError` cho fixture).

- [ ] **Step 3: Viết fixture**

Create `SKILL_DIR/tests/fixtures/report_data.sample.json`:
```json
{
  "schema_version": "4.0",
  "tool_version": "4.0.0",
  "run": {"run_id": "run-fixture-0001", "started_at": "2026-07-16T00:00:00Z", "completed_at": "2026-07-16T00:00:31Z"},
  "redaction_mode": "redact",
  "targets": [
    {
      "target_id": "t-main",
      "database": "app_prod",
      "collection_status": "ok",
      "error": null,
      "capabilities": {"server_version_num": 160004, "is_superuser": false, "vendor": "supabase", "managed": true},
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
          "status": "ok",
          "reason": null,
          "quality": {"sampling_valid": true, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": [
            {"finding_id": "query.high-total-time", "severity": "warning", "assessment": "yellow", "confidence": "measured", "title": "Một query chiếm phần lớn tổng thời gian thực thi", "evidence_ids": ["ev.q.1"], "remediation_ids": ["rem.index.1"]}
          ]
        },
        "wraparound": {
          "collector_version": "1.0",
          "scope": "database",
          "status": "ok",
          "reason": "stats vừa reset giữa 2 mẫu",
          "quality": {"sampling_valid": false, "reset_detected": true, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": [
            {"finding_id": "xid.wraparound-age", "severity": "notice", "assessment": "unknown", "confidence": "heuristic", "title": "Không đủ dữ liệu tin cậy để đánh giá tuổi XID", "evidence_ids": [], "remediation_ids": []}
          ]
        },
        "wait_events": {
          "collector_version": "1.0",
          "scope": "cluster",
          "status": "skipped",
          "reason": "cần pg_read_all_stats",
          "quality": {"sampling_valid": false, "reset_detected": false, "insufficient_activity": false, "truncated": false},
          "metrics": [],
          "findings": []
        }
      }
    },
    {
      "target_id": "t-analytics",
      "database": "analytics",
      "collection_status": "error",
      "error": "statement_timeout: không kết nối được trong 5s",
      "capabilities": {},
      "diagnostics": {}
    }
  ]
}
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_fixture.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/tests/{fixtures/report_data.sample.json,unit/test_fixture.py}
git commit -m "test(p-1): golden fixture with multi-target + edge cases" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Deterministic sort keys

**Files:**
- Create: `SKILL_DIR/scripts/lib/sortkeys.py`
- Test: `SKILL_DIR/tests/unit/test_sortkeys.py`

**Interfaces:**
- Produces: `SEVERITY_RANK: dict[str,int]`; `severity_rank(sev: str) -> int`; `sort_targets(targets: list[dict]) -> list[dict]` (theo `target_id`); `sorted_block_names(diagnostics: dict) -> list[str]`; `iter_findings(data: dict) -> list[dict]` — trả finding "phẳng" đã bổ sung `target_id`, `block`, sắp theo `(-severity_rank, target_id, block, finding_id)`. Render (Task 7) tiêu thụ các hàm này.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_sortkeys.py`:
```python
from scripts.lib.sortkeys import (
    iter_findings,
    severity_rank,
    sort_targets,
    sorted_block_names,
)


def test_severity_rank_order():
    assert severity_rank("critical") > severity_rank("warning") > severity_rank("notice") > severity_rank("info")


def test_severity_rank_unknown_is_lowest():
    assert severity_rank("bogus") == -1


def test_sort_targets_by_id():
    ts = [{"target_id": "b"}, {"target_id": "a"}]
    assert [t["target_id"] for t in sort_targets(ts)] == ["a", "b"]


def test_sorted_block_names(sample_report):
    main = next(t for t in sample_report["targets"] if t["target_id"] == "t-main")
    names = sorted_block_names(main["diagnostics"])
    assert names == ["overview", "query_workload", "wait_events", "wraparound"]


def test_iter_findings_sorted_severity_first(sample_report):
    findings = iter_findings(sample_report)
    ranks = [severity_rank(f["severity"]) for f in findings]
    assert ranks == sorted(ranks, reverse=True)
    first = findings[0]
    assert set(["target_id", "block", "finding_id"]) <= set(first)
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_sortkeys.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết implementation**

Create `SKILL_DIR/scripts/lib/sortkeys.py`:
```python
"""Deterministic ordering helpers for rendering report_data."""

SEVERITY_RANK = {"info": 0, "notice": 1, "warning": 2, "critical": 3}


def severity_rank(sev: str) -> int:
    return SEVERITY_RANK.get(sev, -1)


def sort_targets(targets: list[dict]) -> list[dict]:
    return sorted(targets, key=lambda t: t["target_id"])


def sorted_block_names(diagnostics: dict) -> list[str]:
    return sorted(diagnostics.keys())


def iter_findings(data: dict) -> list[dict]:
    rows: list[dict] = []
    for target in data["targets"]:
        tid = target["target_id"]
        for block in sorted_block_names(target["diagnostics"]):
            for finding in target["diagnostics"][block]["findings"]:
                rows.append({**finding, "target_id": tid, "block": block})
    rows.sort(key=lambda f: (-severity_rank(f["severity"]), f["target_id"], f["block"], f["finding_id"]))
    return rows
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_sortkeys.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/sortkeys.py,tests/unit/test_sortkeys.py}
git commit -m "feat(p-1): deterministic sort keys for rendering" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Redaction

**Files:**
- Create: `SKILL_DIR/scripts/lib/redact.py`
- Test: `SKILL_DIR/tests/unit/test_redact.py`

**Interfaces:**
- Produces: `redact_dsn(dsn: str) -> str` (che password trong DSN kiểu `postgresql://user:pass@host/db`); `redact_value(text: str, mode: str) -> str` (mode `none|hash|redact`); `contains_secret(text: str, secrets: list[str]) -> bool` (tiện cho test output). P0+ dùng cho log/output.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_redact.py`:
```python
from scripts.lib.redact import contains_secret, redact_dsn, redact_value


def test_redact_dsn_hides_password():
    out = redact_dsn("postgresql://app:s3cr3t@10.0.0.5:5432/prod")
    assert "s3cr3t" not in out
    assert "app" in out and "prod" in out


def test_redact_dsn_hides_host_when_redacted():
    out = redact_dsn("postgresql://app:s3cr3t@db.internal.example:5432/prod")
    assert "db.internal.example" not in out


def test_redact_value_modes():
    assert redact_value("abc", "none") == "abc"
    assert redact_value("abc", "redact") == "«redacted»"
    hashed = redact_value("abc", "hash")
    assert hashed != "abc" and hashed.startswith("sha256:")


def test_contains_secret():
    assert contains_secret("dsn=...s3cr3t...", ["s3cr3t"])
    assert not contains_secret("clean text", ["s3cr3t"])
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_redact.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết implementation**

Create `SKILL_DIR/scripts/lib/redact.py`:
```python
"""Redaction helpers — never let secrets reach logs/output."""
import hashlib
import re

_DSN_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z][\w+.\-]*)://(?P<authority>[^/?#]*)(?P<tail>[/?#].*)?$",
    re.DOTALL,
)


def redact_dsn(dsn: str) -> str:
    """Hide password, ALL host(s), query AND fragment secrets in a DSN.

    Whitelist path: preserve the db-name only when it is a single clean token
    (``/[\\w.-]+``); over-redact anything else (host material leaked into the
    path, extra segments, ports). Over-redact the whole locator if an '@' lands
    in the tail. Fails safe: unparseable input becomes a placeholder.
    (Hardened over 3 review rounds — closes multi-host/IPv6, query/fragment,
    and host-in-path leak classes.)
    """
    m = _DSN_RE.match(dsn.strip())
    if not m:
        return "«redacted-dsn»"
    scheme = m.group("scheme")
    authority = m.group("authority")
    tail = m.group("tail") or ""

    if "@" in tail:
        return f"{scheme}://«redacted»"

    if "@" in authority:
        userinfo, _hostinfo = authority.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        cred = f"{user}:«redacted»" if ":" in userinfo else user
        redacted_authority = f"{cred}@«host»"
    else:
        redacted_authority = "«host»"

    path = re.split(r"[?#]", tail, maxsplit=1)[0]
    if path in ("", "/"):
        redacted_tail = path
    elif re.fullmatch(r"/[\w.\-]+", path):
        redacted_tail = path if path == tail else path + "?«redacted»"
    else:
        redacted_tail = "/«redacted»"

    return f"{scheme}://{redacted_authority}{redacted_tail}"


def redact_value(text: str, mode: str) -> str:
    if mode == "none":
        return text
    if mode == "hash":
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return "«redacted»"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(s and s in text for s in secrets)
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_redact.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/redact.py,tests/unit/test_redact.py}
git commit -m "feat(p-1): redaction helpers (dsn/value/secret-scan)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Confidence-invalidation invariant (B3)

**Files:**
- Create: `SKILL_DIR/scripts/lib/invariants.py`
- Test: `SKILL_DIR/tests/unit/test_invariants.py`

**Interfaces:**
- Produces: `check_confidence_invalidation(data: dict) -> list[str]` (list vi phạm, rỗng nếu OK); `enforce_confidence_invalidation(data: dict) -> dict` (trả bản deep-copy đã chuẩn hoá: mọi finding trong diagnostic `sampling_valid=false` bị đặt `confidence="heuristic"`, `assessment="unknown"`). render/rule-engine gọi enforce trước khi trình bày.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_invariants.py`:
```python
import copy

from scripts.lib.invariants import (
    check_confidence_invalidation,
    enforce_confidence_invalidation,
)


def _violating():
    return {
        "targets": [
            {
                "target_id": "t",
                "diagnostics": {
                    "d": {
                        "quality": {"sampling_valid": False, "reset_detected": True,
                                    "insufficient_activity": False, "truncated": False},
                        "findings": [
                            {"finding_id": "f", "severity": "warning",
                             "assessment": "red", "confidence": "measured",
                             "evidence_ids": [], "remediation_ids": []}
                        ],
                    }
                },
            }
        ]
    }


def test_detects_violation():
    assert check_confidence_invalidation(_violating())


def test_enforce_normalizes():
    fixed = enforce_confidence_invalidation(_violating())
    f = fixed["targets"][0]["diagnostics"]["d"]["findings"][0]
    assert f["assessment"] == "unknown"
    assert f["confidence"] == "heuristic"
    assert check_confidence_invalidation(fixed) == []


def test_sample_report_clean_after_enforce(sample_report):
    fixed = enforce_confidence_invalidation(sample_report)
    assert check_confidence_invalidation(fixed) == []


def test_enforce_does_not_touch_valid_sampling():
    data = copy.deepcopy(_violating())
    data["targets"][0]["diagnostics"]["d"]["quality"]["sampling_valid"] = True
    fixed = enforce_confidence_invalidation(data)
    f = fixed["targets"][0]["diagnostics"]["d"]["findings"][0]
    assert f["assessment"] == "red" and f["confidence"] == "measured"
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_invariants.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết implementation**

Create `SKILL_DIR/scripts/lib/invariants.py`:
```python
"""Cross-cutting contract invariants (spec §0.B3)."""
import copy


def _iter_diagnostics(data: dict):
    for target in data.get("targets", []):
        for block, diag in target.get("diagnostics", {}).items():
            yield target.get("target_id"), block, diag


def check_confidence_invalidation(data: dict) -> list[str]:
    violations: list[str] = []
    for tid, block, diag in _iter_diagnostics(data):
        if diag.get("quality", {}).get("sampling_valid", True):
            continue
        for f in diag.get("findings", []):
            if f.get("assessment") != "unknown" or f.get("confidence") != "heuristic":
                violations.append(f"{tid}/{block}/{f.get('finding_id')}")
    return violations


def enforce_confidence_invalidation(data: dict) -> dict:
    out = copy.deepcopy(data)
    for _tid, _block, diag in _iter_diagnostics(out):
        if diag.get("quality", {}).get("sampling_valid", True):
            continue
        for f in diag.get("findings", []):
            f["assessment"] = "unknown"
            f["confidence"] = "heuristic"
    return out
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_invariants.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/invariants.py,tests/unit/test_invariants.py}
git commit -m "feat(p-1): enforce confidence-invalidation invariant (B3)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Read-only SQL safety gate

**Files:**
- Create: `SKILL_DIR/scripts/lib/safety.py`
- Test: `SKILL_DIR/tests/unit/test_safety.py`

**Interfaces:**
- Produces: `READONLY_PREFIXES: tuple[str, ...]`; `is_readonly_sql(sql: str) -> bool` (True nếu statement bắt đầu bằng SELECT/WITH…SELECT/EXPLAIN-không-ANALYZE/SHOW/SET/TABLE; False cho DDL/DML/EXPLAIN ANALYZE). **Ghi chú:** đây là gate prefix tạm; P4 nâng cấp bằng parser `pglast`. P0+ import gate này.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_safety.py`:
```python
import pytest

from scripts.lib.safety import is_readonly_sql


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "  select * from pg_stat_activity",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "EXPLAIN SELECT * FROM t",
    "SHOW work_mem",
    "SET statement_timeout = '3s'",
])
def test_readonly_allowed(sql):
    assert is_readonly_sql(sql) is True


@pytest.mark.parametrize("sql", [
    "DROP INDEX foo",
    "delete from t",
    "UPDATE t SET a=1",
    "INSERT INTO t VALUES (1)",
    "TRUNCATE t",
    "ALTER SYSTEM SET work_mem='1GB'",
    "CREATE INDEX ON t (a)",
    "EXPLAIN ANALYZE SELECT * FROM t",
    "EXPLAIN (ANALYZE, BUFFERS) SELECT 1",
    "VACUUM ANALYZE t",
    "",
])
def test_write_or_analyze_blocked(sql):
    assert is_readonly_sql(sql) is False
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_safety.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết implementation**

Create `SKILL_DIR/scripts/lib/safety.py`:
```python
"""Read-only SQL gate (prefix-based; upgraded to a real parser in P4)."""
import re

READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "SET", "TABLE", "VALUES")

_LEADING_COMMENT = re.compile(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s)+", re.DOTALL)
_ANALYZE_IN_EXPLAIN = re.compile(r"\bANALYZE\b", re.IGNORECASE)


def _strip(sql: str) -> str:
    return _LEADING_COMMENT.sub("", sql).strip()


def is_readonly_sql(sql: str) -> bool:
    s = _strip(sql)
    if not s:
        return False
    head = s.split(None, 1)[0].upper()
    if head not in READONLY_PREFIXES:
        return False
    if head == "EXPLAIN":
        # EXPLAIN is read-only ONLY without ANALYZE (ANALYZE executes the statement).
        prefix = s[: s.upper().find("SELECT")] if "SELECT" in s.upper() else s
        if _ANALYZE_IN_EXPLAIN.search(prefix):
            return False
    return True
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_safety.py -v`
Expected: PASS (17 passed).

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/lib/safety.py,tests/unit/test_safety.py}
git commit -m "feat(p-1): read-only SQL safety gate (prefix, pre-parser)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Deterministic renderer + golden snapshot

**Files:**
- Create: `SKILL_DIR/scripts/render.py`
- Create (generated): `SKILL_DIR/tests/golden/DB_STATUS_REPORT.md`, `SKILL_DIR/tests/golden/FINDINGS.md`, `SKILL_DIR/tests/golden/report_summary.json`
- Test: `SKILL_DIR/tests/unit/test_render.py`

**Interfaces:**
- Consumes: `scripts.lib.sortkeys` (`sort_targets`, `sorted_block_names`, `iter_findings`, `severity_rank`), `scripts.lib.invariants.enforce_confidence_invalidation`.
- Produces: `ASSESSMENT_ICONS: dict`; `render_db_status(data: dict) -> str`; `render_findings(data: dict) -> str`; `build_summary(data: dict) -> dict`; `render_all(data: dict, out_dir: Path) -> None` (ghi 3 file). Golden test so output với `tests/golden/`.

- [ ] **Step 1: Viết test (golden-aware) thất bại**

Create `SKILL_DIR/tests/unit/test_render.py`:
```python
import json
import os
from pathlib import Path

from scripts.render import build_summary, render_db_status, render_findings

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _check(name: str, actual: str):
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
    assert path.read_text(encoding="utf-8") == actual, f"golden drift: {name}"


def test_db_status_golden(sample_report):
    _check("DB_STATUS_REPORT.md", render_db_status(sample_report))


def test_findings_golden(sample_report):
    _check("FINDINGS.md", render_findings(sample_report))


def test_summary_golden(sample_report):
    actual = json.dumps(build_summary(sample_report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _check("report_summary.json", actual)


def test_render_is_deterministic(sample_report):
    assert render_db_status(sample_report) == render_db_status(sample_report)


def test_invalid_sampling_shows_unknown(sample_report):
    # wraparound có sampling_valid=false → phải là ⚪ unknown, không xanh
    out = render_db_status(sample_report)
    assert "⚪" in out
    assert "xid.wraparound-age" in out
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_render.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.render`).

- [ ] **Step 3: Viết renderer**

Create `SKILL_DIR/scripts/render.py`:
```python
"""Deterministic renderer: report_data.json -> Markdown + summary (no timestamps)."""
import json
from pathlib import Path

from scripts.lib.invariants import enforce_confidence_invalidation
from scripts.lib.sortkeys import iter_findings, sort_targets, sorted_block_names

ASSESSMENT_ICONS = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
    "unknown": "⚪",
    "not_applicable": "➖",
}


def _icon(assessment: str) -> str:
    return ASSESSMENT_ICONS.get(assessment, "⚪")


def render_db_status(data: dict) -> str:
    data = enforce_confidence_invalidation(data)
    lines = ["# Báo cáo tình trạng Database", ""]
    for target in sort_targets(data["targets"]):
        lines.append(f"## Target: {target['database']} (`{target['target_id']}`) — thu thập: {target['collection_status']}")
        lines.append("")
        if target["collection_status"] == "error":
            lines.append(f"> 🔴 Lỗi thu thập: {target.get('error') or 'không rõ'}")
            lines.append("")
            continue
        for block in sorted_block_names(target["diagnostics"]):
            diag = target["diagnostics"][block]
            suffix = f" · {diag['reason']}" if diag.get("reason") else ""
            lines.append(f"### {block} — {diag['status']}{suffix}")
            if not diag["quality"]["sampling_valid"]:
                lines.append("")
                lines.append("> ⚪ Sampling không hợp lệ — các đánh giá bị hạ về `unknown`.")
            if diag["findings"]:
                lines.append("")
                lines.append("| Finding | Mức | Đánh giá | Tin cậy |")
                lines.append("|---|---|---|---|")
                for f in diag["findings"]:
                    lines.append(f"| `{f['finding_id']}` | {f['severity']} | {_icon(f['assessment'])} {f['assessment']} | {f['confidence']} |")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_findings(data: dict) -> str:
    data = enforce_confidence_invalidation(data)
    lines = ["# Findings (tổng hợp)", "",
             "| Target | Khối | Finding | Mức | Đánh giá | Tin cậy |",
             "|---|---|---|---|---|---|"]
    for f in iter_findings(data):
        lines.append(f"| `{f['target_id']}` | {f['block']} | `{f['finding_id']}` | {f['severity']} | {_icon(f['assessment'])} {f['assessment']} | {f['confidence']} |")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_summary(data: dict) -> dict:
    data = enforce_confidence_invalidation(data)
    by_assessment: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    targets: dict[str, dict] = {}
    for target in data["targets"]:
        count = sum(len(d["findings"]) for d in target["diagnostics"].values())
        targets[target["target_id"]] = {"collection_status": target["collection_status"], "findings": count}
    for f in iter_findings(data):
        by_assessment[f["assessment"]] = by_assessment.get(f["assessment"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    return {
        "total_findings": sum(by_severity.values()),
        "by_assessment": by_assessment,
        "by_severity": by_severity,
        "targets": targets,
    }


def render_all(data: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "DB_STATUS_REPORT.md").write_text(render_db_status(data), encoding="utf-8", newline="\n")
    (out_dir / "FINDINGS.md").write_text(render_findings(data), encoding="utf-8", newline="\n")
    (out_dir / "report_summary.json").write_text(
        json.dumps(build_summary(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
```

- [ ] **Step 4: Sinh golden baseline + verify ổn định**

Run (sinh baseline lần đầu, rồi chạy lại để xác nhận stable):
```bash
UPDATE_GOLDEN=1 python -m pytest tests/unit/test_render.py -q
python -m pytest tests/unit/test_render.py -v
```
Expected: lần 2 PASS (5 passed). **Review** 3 file trong `tests/golden/` bằng mắt: `⚪ unknown` xuất hiện cho `xid.wraparound-age`; target `t-analytics` hiển thị 🔴 lỗi; không có timestamp nào trong 3 file.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/db-report-generator/{scripts/render.py,tests/unit/test_render.py,tests/golden}
git commit -m "feat(p-1): deterministic renderer + golden snapshot" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Test-matrix config + docs (local runner + CI template)

**Files:**
- Create: `SKILL_DIR/docker-compose.pg.yml`
- Create: `SKILL_DIR/.github/workflows/tests.yml`
- Create: `SKILL_DIR/tests/README.md`
- Test: `SKILL_DIR/tests/unit/test_harness_config.py`

**Interfaces:**
- Produces: docker-compose khởi PG 14–18 cục bộ (dùng ở P0+ cho unit-collector); workflow template GitHub Actions (dùng khi init git remote). Test chỉ xác nhận YAML parse được và liệt kê đủ 5 phiên bản.

- [ ] **Step 1: Viết test thất bại**

Create `SKILL_DIR/tests/unit/test_harness_config.py`:
```python
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_lists_pg_14_to_18():
    compose = yaml.safe_load((ROOT / "docker-compose.pg.yml").read_text(encoding="utf-8"))
    images = " ".join(str(s.get("image", "")) for s in compose["services"].values())
    for v in ("14", "15", "16", "17", "18"):
        assert f"postgres:{v}" in images


def test_ci_workflow_parses_and_has_matrix():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    assert "jobs" in wf
    pg = wf["jobs"]["test"]["strategy"]["matrix"]["pg"]
    assert sorted(str(x) for x in pg) == ["14", "15", "16", "17", "18"]
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `python -m pytest tests/unit/test_harness_config.py -v`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Viết config**

Create `SKILL_DIR/docker-compose.pg.yml`:
```yaml
# Local PostgreSQL matrix for unit-collector tests (P0+). Not used in P-1 tests.
services:
  pg14:
    image: postgres:14
    environment: {POSTGRES_PASSWORD: postgres}
    ports: ["55432:5432"]
  pg15:
    image: postgres:15
    environment: {POSTGRES_PASSWORD: postgres}
    ports: ["55433:5432"]
  pg16:
    image: postgres:16
    environment: {POSTGRES_PASSWORD: postgres}
    ports: ["55434:5432"]
  pg17:
    image: postgres:17
    environment: {POSTGRES_PASSWORD: postgres}
    ports: ["55435:5432"]
  pg18:
    image: postgres:18
    environment: {POSTGRES_PASSWORD: postgres}
    ports: ["55436:5432"]
```

Create `SKILL_DIR/.github/workflows/tests.yml`:
```yaml
name: tests
on: [push, pull_request]
jobs:
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

Create `SKILL_DIR/tests/README.md`:
```markdown
# Tests

## Chạy nhanh (thuần Python, không cần DB)
```bash
cd .agents/skills/db-report-generator
pip install -r requirements-dev.txt
python -m pytest -q
```

## Cập nhật golden khi render đổi có chủ đích
```bash
UPDATE_GOLDEN=1 python -m pytest tests/unit/test_render.py -q
```

## Unit-collector matrix (P0+ , cần Docker)
```bash
docker compose -f docker-compose.pg.yml up -d
# ... chạy test collector trỏ tới cổng 55432..55436 ...
docker compose -f docker-compose.pg.yml down
```

CI cloud: `.github/workflows/tests.yml` (template, dùng khi repo có remote).
```

- [ ] **Step 4: Chạy để xác nhận pass**

Run: `python -m pytest tests/unit/test_harness_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Chạy toàn bộ suite**

Run: `python -m pytest -q`
Expected: PASS (tất cả test P−1 xanh).

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/db-report-generator/{docker-compose.pg.yml,.github,tests/README.md,tests/unit/test_harness_config.py}
git commit -m "chore(p-1): local PG matrix + CI template + test docs" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Acceptance Gate (Phase −1)

- [ ] `python -m pytest -q` xanh toàn bộ (thuần Python, không cần DB/Docker).
- [ ] `references/report-data.schema.json` loại được doc malformed (sai enum/thiếu field).
- [ ] Fixture multi-target hợp lệ; có target `error`, block `skipped`, block `sampling_valid=false`.
- [ ] Render byte-ổn định (golden); `sampling_valid=false` → ⚪ `unknown`, không xanh.
- [ ] Redaction che password/host; `is_readonly_sql` chặn DDL/DML/EXPLAIN ANALYZE.
- [ ] Không file nào trong `tests/golden/` chứa timestamp/random.

## Self-Review notes (đã kiểm)

- **Spec coverage P−1:** schema (A5) ✓, fixture ✓, render deterministic (A1) ✓, golden (P7.1) ✓, redaction ✓, safety gate scaffold (A3) ✓, B3 invariant ✓, CI/local matrix (A4/§17) ✓.
- **Type consistency:** `render.py` gọi đúng tên hàm export từ `sortkeys.py` (`sort_targets`, `sorted_block_names`, `iter_findings`) và `invariants.py` (`enforce_confidence_invalidation`). Enum khớp schema.
- **Ngoài phạm vi P−1 (làm ở phase sau):** `envparse.py` (P0, khi cần đọc `.env`), collectors/live-DB, rule engine, EXPLAIN parser `pglast` (P4).

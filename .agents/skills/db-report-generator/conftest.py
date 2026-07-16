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

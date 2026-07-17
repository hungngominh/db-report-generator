import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))


@pytest.fixture
def skill_dir() -> Path:
    return SKILL_DIR

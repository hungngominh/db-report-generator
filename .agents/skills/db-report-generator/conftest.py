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


@pytest.fixture(scope="session")
def _pg_container():
    from tests.pgcontainer import PostgresContainer, docker_available

    if not docker_available():
        pytest.skip("docker not available")
    with PostgresContainer() as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_dsn(_pg_container) -> dict:
    return _pg_container.dsn_kwargs


@pytest.fixture(scope="session")
def pg_dsn_url(_pg_container) -> str:
    return _pg_container.dsn_url

import sys
from pathlib import Path

import pytest

DB_MONITOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = DB_MONITOR_DIR.parent.parent
SKILL_DIR = REPO_ROOT / ".agents" / "skills" / "db-report-generator"

for _path in (DB_MONITOR_DIR, SKILL_DIR):
    _p = str(_path)
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session")
def _target_pg():
    from tests.pgcontainer import PostgresContainer, docker_available

    if not docker_available():
        pytest.skip("docker not available")
    with PostgresContainer() as pg:
        yield pg


@pytest.fixture(scope="session")
def _storage_pg():
    from tests.pgcontainer import PostgresContainer, docker_available

    if not docker_available():
        pytest.skip("docker not available")
    with PostgresContainer() as pg:
        yield pg


@pytest.fixture
def target_dsn_kwargs(_target_pg) -> dict:
    return _target_pg.dsn_kwargs


@pytest.fixture
def storage_dsn_url(_storage_pg) -> str:
    return _storage_pg.dsn_url

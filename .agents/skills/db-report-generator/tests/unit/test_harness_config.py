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

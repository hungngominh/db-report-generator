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

    repo_root = Path(__file__).resolve().parents[5]
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

def test_remediation_policy_file_exists(skill_dir):
    p = skill_dir / "references" / "remediation-policy.md"
    assert p.exists()


def test_remediation_policy_has_5_tier_taxonomy(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    for tier in (
        "observe-only",
        "controlled-diagnostic",
        "maintenance-review",
        "ddl-review",
        "dangerous",
    ):
        assert f"`{tier}`" in text, f"missing tier {tier!r}"


def test_remediation_policy_states_no_tier_auto_executes(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "không tier nào tự động thực thi" in text.lower() or "no tier auto-executes" in text.lower()


def test_remediation_policy_gates_alter_system_on_managed(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "capabilities.managed" in text
    assert "ALTER SYSTEM" in text


def test_remediation_policy_defines_recovery_or_rollback(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "recovery_or_rollback" in text
    assert "pg_terminate_backend" in text


def test_remediation_policy_covers_concurrently_and_partition(skill_dir):
    text = (skill_dir / "references" / "remediation-policy.md").read_text(encoding="utf-8")
    assert "CONCURRENTLY" in text
    assert "INVALID" in text
    assert "pg_partman" in text

import re


_FORBIDDEN = [re.compile(r"/100\b"), re.compile(r"\{\{\w*_score\}\}")]


def test_skill_md_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in SKILL.md"


def test_combined_report_template_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "assets" / "templates" / "template-combined-report.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in template-combined-report.md"


def test_combined_report_template_has_axis_matrix_placeholders(skill_dir):
    text = (skill_dir / "assets" / "templates" / "template-combined-report.md").read_text(encoding="utf-8")
    for axis_key in ("db_health", "query_performance", "maintenance", "connections", "security_rls"):
        assert f"{{{{{axis_key}_icon}}}}" in text, f"missing {axis_key}_icon placeholder"


def test_skill_md_has_code_analysis_confidence_section(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "5.8 Gán Độ Tin Cậy Cho Code Findings" in text
    for tier in ("measured", "estimated", "heuristic"):
        assert f"`{tier}`" in text
    assert "Không tìm thấy raw SQL" in text


def test_skill_md_security_rls_axis_references_rls_policies_collector(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "`rls_policies`" in text
    assert "rỗng — chưa có collector" not in text


def test_skill_md_solution_engine_pattern_count_matches_solution_index(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "19 problem patterns" in text
    assert "13 problem patterns" not in text


def test_skill_md_no_longer_references_queries_solutions_sql(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "queries-solutions.sql" not in text


def test_queries_solutions_sql_file_removed(skill_dir):
    p = skill_dir / "references" / "queries-solutions.sql"
    assert not p.exists()


def test_skill_md_generate_fix_sql_uses_recovery_or_rollback(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "recovery_or_rollback" in text
    assert "rollback statement nếu applicable" not in text


def test_skill_md_references_remediation_policy(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "references/remediation-policy.md" in text


def test_solutions_template_has_dangerous_section_excluded_from_scripts(skill_dir):
    text = (skill_dir / "assets" / "templates" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" in text
    assert "dangerous_solutions" in text
    assert "Đã loại trừ mọi fix remediation_class=dangerous" in text


def test_solutions_template_uses_recovery_or_rollback(skill_dir):
    text = (skill_dir / "assets" / "templates" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "{{recovery_or_rollback_sql}}" in text
    assert "{{rollback_sql}}" not in text
    assert "**Hoàn tác" not in text


def test_solutions_template_footer_version_v4(skill_dir):
    text = (skill_dir / "assets" / "templates" / "template-solutions-report.md").read_text(encoding="utf-8")
    assert "db-report-generator v4" in text
    assert "v3.0.0" not in text


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

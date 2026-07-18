import re


_FORBIDDEN = [re.compile(r"/100\b"), re.compile(r"\{\{\w*_score\}\}")]


def test_skill_md_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in SKILL.md"


def test_combined_report_template_has_no_legacy_0_100_score(skill_dir):
    text = (skill_dir / "references" / "template-combined-report.md").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN:
        assert not pattern.search(text), f"found forbidden pattern {pattern.pattern!r} in template-combined-report.md"


def test_combined_report_template_has_axis_matrix_placeholders(skill_dir):
    text = (skill_dir / "references" / "template-combined-report.md").read_text(encoding="utf-8")
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

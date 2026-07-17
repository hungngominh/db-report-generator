def test_security_sql_injection_kb_file_exists(skill_dir):
    p = skill_dir / "references" / "kb" / "security-sql-injection.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "parameterized" in text.lower() or "tham số hóa" in text.lower()
    assert "%s" in text  # psycopg2-style parameter placeholder example


def test_kb_index_lists_security_sql_injection(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "- `security-sql-injection.md`" in text


def test_kb_index_file_count_updated(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "## Danh sách file (32)" in text
    assert "## Danh sách file (31)" not in text

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


def test_solution_index_version_bumped(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    assert 'version: "2.0.0"' in text


def test_solution_index_has_detection_legend(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    assert "Chú giải Detection" in text
    for label in ("[Tự động]", "[Tự động, một phần]", "[Code-analysis]", "[Gợi ý thủ công"):
        assert label in text


def test_pattern_5_no_longer_cites_missing_indexes_reference(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 5. UNUSED INDEXES")
    end = text.index("## 6. CONNECTION EXHAUSTION")
    block = text[start:end]
    assert "- **Reference**: `query-missing-indexes.md`" not in block


def test_pattern_9_cites_real_sql_injection_kb_file(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 9. SQL INJECTION RISK")
    end = text.index("## 10. MISSING PAGINATION")
    block = text[start:end]
    assert "`security-sql-injection.md`" in block
    assert "Security best practices" not in block


def test_manual_only_patterns_marked_explicitly(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 2. HIGH SEQUENTIAL SCAN RATIO", "## 3. HIGH DEAD TUPLE RATIO"),
        ("## 11. LARGE TABLE WITHOUT PARTITIONING", "## 12. MISSING FOREIGN KEY INDEXES"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## Priority Assignment Rules"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "Gợi ý thủ công" in block
        assert "không có collector" in block.lower()


def test_automated_patterns_cite_real_diagnostic_blocks(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    checks = {
        "## 1. LOW CACHE HIT RATIO": ("database_stats", "db_health.cache_hit_ratio"),
        "## 3. HIGH DEAD TUPLE RATIO": ("dead_tuples", "maintenance.dead_tuples_pct"),
        "## 4. SLOW QUERIES": ("query_stats", "query_perf.slow_query_mean_exec_time"),
        "## 6. CONNECTION EXHAUSTION": ("connection_depth", "connections.cluster_pressure"),
        "## 7. BLOCKING QUERIES": ("blocking", "connections.blocking"),
        "## 12. MISSING FOREIGN KEY INDEXES": ("fk_missing_index", "maintenance.fk_missing_index"),
    }
    for heading, (block_name, finding_id) in checks.items():
        idx = text.index(heading)
        section = text[idx:idx + 1200]
        assert f"`{block_name}`" in section, heading
        assert finding_id in section, heading


def test_code_analysis_patterns_reference_confidence_tiers(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading in ("## 8. N+1 QUERY PATTERN", "## 9. SQL INJECTION RISK", "## 10. MISSING PAGINATION"):
        idx = text.index(heading)
        section = text[idx:idx + 600]
        assert "SKILL.md" in section
        assert "Code-analysis" in section


def test_no_reference_field_points_outside_kb(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("- **Reference**"):
            assert "../" not in line
            assert "supabase-postgres-best-practices" not in line

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


def test_new_patterns_14_to_19_present(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for n, title_fragment in [
        (14, "RLS POLICY RE-EVALUATION"),
        (15, "STALE TABLE STATISTICS"),
        (16, "EXPLAIN PLAN"),
        (17, "COLUMN-LEVEL INDEX SUGGESTION"),
        (18, "QUERY RANKING"),
        (19, "SCHEMA HYGIENE ISSUES"),
    ]:
        assert f"## {n}. {title_fragment}" in text


def test_pattern_14_rls_cites_real_finding_id(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 14. RLS POLICY RE-EVALUATION")
    section = text[idx:idx + 1200]
    assert "`rls_policies`" in section
    assert "security_rls.rls_policy_issue" in section
    assert "unwrapped_reeval_call" in section
    assert "missing_supporting_index" in section
    assert "`security-rls-performance.md`" in section


def test_pattern_17_notes_composite_only_limitation(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 17. COLUMN-LEVEL INDEX SUGGESTION")
    section = text[idx:idx + 1500]
    assert "index_advisor" in section
    assert "query_perf.suggested_column_index" in section
    assert "không tự sinh" in section.lower()


def test_pattern_19_schema_hygiene_cites_real_finding_id(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 19. SCHEMA HYGIENE ISSUES")
    section = text[idx:idx + 1200]
    assert "`schema_checks`" in section
    assert "maintenance.schema_hygiene_issue" in section
    assert "missing_primary_key" in section
    assert "oversized_uuid_pk" in section
    assert "timestamp_without_timezone" in section
    assert "`schema-primary-keys.md`" in section
    assert "`schema-data-types.md`" in section


def test_pattern_1b_index_cache_hit_cites_real_finding_id(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    idx = text.index("## 1b. LOW CACHE HIT RATIO")
    end = text.index("## 2. HIGH SEQUENTIAL SCAN RATIO")
    section = text[idx:end]
    assert "`index_io`" in section
    assert "query_perf.index_cache_hit_ratio" in section
    assert "observe-only" in section
    assert "pg_statio_user_indexes" in section
    assert "pg_stat_user_indexes" in section


def test_kb_index_pattern_count_updated(skill_dir):
    text = (skill_dir / "references" / "kb" / "_index.md").read_text(encoding="utf-8")
    assert "19 problem pattern" in text
    assert "13 problem pattern" not in text


def test_at_least_8_of_13_legacy_patterns_have_connected_detection(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    positions = sorted(text.index(f"## {n}.") for n in range(1, 14))
    positions.append(text.index("## 14."))
    connected = 0
    for i in range(13):
        section = text[positions[i]:positions[i + 1]]
        if "Gợi ý thủ công" not in section:
            connected += 1
    assert connected >= 8


def test_all_patterns_have_remediation_class(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    headings = [
        "## 1. LOW CACHE HIT RATIO",
        "## 2. HIGH SEQUENTIAL SCAN RATIO",
        "## 3. HIGH DEAD TUPLE RATIO",
        "## 4. SLOW QUERIES",
        "## 5. UNUSED INDEXES",
        "## 6. CONNECTION EXHAUSTION",
        "## 7. BLOCKING QUERIES",
        "## 8. N+1 QUERY PATTERN",
        "## 9. SQL INJECTION RISK",
        "## 10. MISSING PAGINATION",
        "## 11. LARGE TABLE WITHOUT PARTITIONING",
        "## 12. MISSING FOREIGN KEY INDEXES",
        "## 13. SUBOPTIMAL SERVER CONFIGURATION",
        "## 14. RLS POLICY RE-EVALUATION",
        "## 15. STALE TABLE STATISTICS",
        "## 16. EXPLAIN PLAN",
        "## 17. COLUMN-LEVEL INDEX SUGGESTION",
        "## 18. QUERY RANKING",
        "## 19. SCHEMA HYGIENE ISSUES",
    ]
    boundary = "## Priority Assignment Rules"
    positions = [text.index(h) for h in headings] + [text.index(boundary)]
    for i in range(len(headings)):
        section = text[positions[i]:positions[i + 1]]
        assert "**Remediation Class**" in section, f"missing Remediation Class in {headings[i]}"


def test_dangerous_patterns_marked_and_excluded_from_run_now(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 5. UNUSED INDEXES", "## 6. CONNECTION EXHAUSTION"),
        ("## 6. CONNECTION EXHAUSTION", "## 7. BLOCKING QUERIES"),
        ("## 7. BLOCKING QUERIES", "## 8. N+1 QUERY PATTERN"),
        ("## 11. LARGE TABLE WITHOUT PARTITIONING", "## 12. MISSING FOREIGN KEY INDEXES"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## 14. RLS POLICY RE-EVALUATION"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "`dangerous`" in block, f"{heading} not marked dangerous"
        assert "KHÔNG đưa vào block chạy-liền" in block, f"{heading} missing run-now exclusion note"


def test_pattern_6_terminates_idle_in_transaction_only(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 6. CONNECTION EXHAUSTION")
    end = text.index("## 7. BLOCKING QUERIES")
    block = text[start:end]
    assert "idle in transaction" in block
    assert "state = 'idle'" not in block
    assert "PgBouncer" in block and "Supavisor" in block, "pattern 6 missing named pool-kill warning"


def test_patterns_6_7_13_gate_alter_system_on_self_hosted(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    for heading, next_heading in [
        ("## 6. CONNECTION EXHAUSTION", "## 7. BLOCKING QUERIES"),
        ("## 7. BLOCKING QUERIES", "## 8. N+1 QUERY PATTERN"),
        ("## 13. SUBOPTIMAL SERVER CONFIGURATION", "## 14. RLS POLICY RE-EVALUATION"),
    ]:
        start = text.index(heading)
        end = text.index(next_heading)
        block = text[start:end]
        assert "capabilities.managed" in block, f"{heading} missing capability gate"
        assert "capabilities.is_superuser" in block, f"{heading} missing is_superuser gate"


def test_pattern_11_no_data_loss_swap(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 11. LARGE TABLE WITHOUT PARTITIONING")
    end = text.index("## 12. MISSING FOREIGN KEY INDEXES")
    block = text[start:end]
    assert "RENAME TO" not in block
    assert "pg_partman" in block


def test_pattern_5_has_recovery_or_rollback_heading(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 5. UNUSED INDEXES")
    end = text.index("## 6. CONNECTION EXHAUSTION")
    block = text[start:end]
    assert "**recovery_or_rollback" in block
    assert "**Rollback:**" not in block


def test_pattern_13_no_hardcoded_multiplier_and_gated(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    start = text.index("## 13. SUBOPTIMAL SERVER CONFIGURATION")
    end = text.index("## 14. RLS POLICY RE-EVALUATION")
    block = text[start:end]
    assert "2-5x" not in block


def test_no_leftover_rollback_heading_anywhere_in_file(skill_dir):
    text = (skill_dir / "references" / "kb" / "solution-index.md").read_text(encoding="utf-8")
    assert "**Rollback:**" not in text
    assert "{{rollback_sql}}" not in text

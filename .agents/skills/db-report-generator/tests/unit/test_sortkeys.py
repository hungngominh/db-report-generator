from scripts.lib.sortkeys import (
    iter_findings,
    severity_rank,
    sort_targets,
    sorted_block_names,
)


def test_severity_rank_order():
    assert severity_rank("critical") > severity_rank("warning") > severity_rank("notice") > severity_rank("info")


def test_severity_rank_unknown_is_lowest():
    assert severity_rank("bogus") == -1


def test_sort_targets_by_id():
    ts = [{"target_id": "b"}, {"target_id": "a"}]
    assert [t["target_id"] for t in sort_targets(ts)] == ["a", "b"]


def test_sorted_block_names(sample_report):
    main = next(t for t in sample_report["targets"] if t["target_id"] == "t-main")
    names = sorted_block_names(main["diagnostics"])
    assert names == ["overview", "query_workload", "wait_events", "wraparound"]


def test_iter_findings_sorted_severity_first(sample_report):
    findings = iter_findings(sample_report)
    ranks = [severity_rank(f["severity"]) for f in findings]
    assert ranks == sorted(ranks, reverse=True)
    first = findings[0]
    assert set(["target_id", "block", "finding_id"]) <= set(first)

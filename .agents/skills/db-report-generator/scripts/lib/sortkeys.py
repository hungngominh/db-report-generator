"""Deterministic ordering helpers for rendering report_data."""

SEVERITY_RANK = {"info": 0, "notice": 1, "warning": 2, "critical": 3}


def severity_rank(sev: str) -> int:
    return SEVERITY_RANK.get(sev, -1)


def sort_targets(targets: list[dict]) -> list[dict]:
    return sorted(targets, key=lambda t: t["target_id"])


def sorted_block_names(diagnostics: dict) -> list[str]:
    return sorted(diagnostics.keys())


def iter_findings(data: dict) -> list[dict]:
    rows: list[dict] = []
    for target in data["targets"]:
        tid = target["target_id"]
        for block in sorted_block_names(target["diagnostics"]):
            for finding in target["diagnostics"][block]["findings"]:
                rows.append({**finding, "target_id": tid, "block": block})
    rows.sort(key=lambda f: (-severity_rank(f["severity"]), f["target_id"], f["block"], f["finding_id"]))
    return rows

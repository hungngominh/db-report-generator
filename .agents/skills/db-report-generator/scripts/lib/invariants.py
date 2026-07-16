"""Cross-cutting contract invariants (spec §0.B3)."""
import copy


def _iter_diagnostics(data: dict):
    for target in data.get("targets", []):
        for block, diag in target.get("diagnostics", {}).items():
            yield target.get("target_id"), block, diag


def check_confidence_invalidation(data: dict) -> list[str]:
    violations: list[str] = []
    for tid, block, diag in _iter_diagnostics(data):
        if diag.get("quality", {}).get("sampling_valid", True):
            continue
        for f in diag.get("findings", []):
            if f.get("assessment") != "unknown" or f.get("confidence") != "heuristic":
                violations.append(f"{tid}/{block}/{f.get('finding_id')}")
    return violations


def enforce_confidence_invalidation(data: dict) -> dict:
    out = copy.deepcopy(data)
    for _tid, _block, diag in _iter_diagnostics(out):
        if diag.get("quality", {}).get("sampling_valid", True):
            continue
        for f in diag.get("findings", []):
            f["assessment"] = "unknown"
            f["confidence"] = "heuristic"
    return out

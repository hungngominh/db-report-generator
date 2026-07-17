"""Shared builders for schema-valid diagnostic objects (metrics-only in P0b)."""

# Structural collectors read the catalog directly — no delta sampling window —
# so the sampling quality flags are trivially "valid". The B3 invalidation
# invariant only downgrades when sampling_valid is False.
STRUCTURAL_QUALITY = {
    "sampling_valid": True,
    "reset_detected": False,
    "insufficient_activity": False,
    "truncated": False,
}


def diagnostic(scope, status, metrics, *, reason=None,
               quality=None, collector_version="1"):
    return {
        "collector_version": collector_version,
        "scope": scope,
        "status": status,
        "reason": reason,
        "quality": dict(quality or STRUCTURAL_QUALITY),
        "metrics": list(metrics),
        "findings": [],  # rule engine (metrics -> findings) is Phase 3
    }


def skipped(scope, reason, *, collector_version="1"):
    return diagnostic(scope, "skipped", [], reason=reason,
                      collector_version=collector_version)

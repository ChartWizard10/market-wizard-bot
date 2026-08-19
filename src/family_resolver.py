"""Cross-family evidence resolver for Chart Wizard.

CFR-1 arbitrates simultaneous detections from the four locked bullish setup
families without turning confluence into a score multiplier or letting a failed
*sibling* family automatically cancel a valid primary setup.

Doctrine boundary
-----------------
- Sequence and sovereign market evidence outrank a pattern label.
- Multiple labels can describe the same auction from different angles.
- Confluence is context, not automatic capital permission.
- A family-local failure (for example a gap boundary failure) does not by itself
  invalidate an otherwise coherent SMA-cradle or VCP setup.
- A shared/common failure must remain visible for the common prefilter/tiering
  gates; this resolver never suppresses it.
- The resolver never assigns SNIPE_IT / STARTER / NEAR_ENTRY, never routes
  Discord, and never authorizes capital.

The module is intentionally pure and side-effect free.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VERSION = "CFR-1"

BREAK_RETEST_CONTINUATION = "BREAK_RETEST_CONTINUATION"
VCP_BREAK_RETEST = "VCP_BREAK_RETEST"
SMA_CRADLE_CONTINUATION = "SMA_CRADLE_CONTINUATION"
GAP_FILL_REVERSAL = "GAP_FILL_REVERSAL"
NONE = "NONE"

FAMILY_ORDER = (
    BREAK_RETEST_CONTINUATION,
    VCP_BREAK_RETEST,
    SMA_CRADLE_CONTINUATION,
    GAP_FILL_REVERSAL,
)

REL_NONE = "NONE"
REL_SINGLE = "SINGLE"
REL_CONFLUENT = "CONFLUENT"
REL_COMPATIBLE = "COMPATIBLE"
REL_AMBIGUOUS = "AMBIGUOUS"
REL_CONTRADICTORY = "CONTRADICTORY"
REL_ALL_FAILED = "ALL_FAILED"

CONFLICT_NONE = "NONE"
CONFLICT_LOCAL = "LOCAL"
CONFLICT_SHARED = "SHARED"

_SHARED_FAILURE_CODES = {
    "OVERHEAD_BLOCKED",
    "RETEST_FAILED",
    "DATA_EMPTY",
    "DATA_ERROR",
    "INSUFFICIENT_BARS",
    "STALE_DATA",
    "HOSTILE_VALUE_ALIGNMENT",
}


def _bool(obj: dict, key: str) -> bool:
    return bool(obj.get(key)) if isinstance(obj, dict) else False


def _score(obj: dict) -> int:
    try:
        return max(0, min(100, int(obj.get("family_score") or 0)))
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _codes(obj: dict) -> set[str]:
    out: set[str] = set()
    for key in ("blockers", "soft_caps"):
        values = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(values, (list, tuple, set)):
            for value in values:
                if isinstance(value, str) and value:
                    out.add(value.upper())
    return out


def _is_failed(obj: dict) -> bool:
    """True when this family's own lifecycle has failed."""
    if not isinstance(obj, dict) or not obj.get("detected"):
        return False
    state = str(obj.get("state") or "").upper()
    retest = str(obj.get("retest_state") or "").upper()
    codes = _codes(obj)
    return bool(
        "FAILED" in state
        or retest == "FAILED"
        or "ACCEPTED_BELOW_VALUE_POCKET" in codes
        or "ACCEPTED_BELOW_GAP_BOUNDARY" in codes
        or "RETEST_FAILED" in codes
    )


def _failure_scope(obj: dict) -> str:
    if not _is_failed(obj):
        return CONFLICT_NONE
    if _codes(obj) & _SHARED_FAILURE_CODES:
        return CONFLICT_SHARED
    return CONFLICT_LOCAL


def _path_quality(obj: dict) -> int:
    path = str(obj.get("path_status") or "UNKNOWN").upper()
    if path in {"CLEAN", "CLEAN_TO_PIVOT"}:
        return 2
    if "BLOCKED" in path:
        return 0
    return 1


def _geometry_quality(obj: dict) -> int:
    inv = _num(obj.get("invalidation_level"))
    target = _num(obj.get("target_1"))
    rr = _num(obj.get("rr_to_t1"))
    points = int(inv is not None) + int(target is not None)
    if rr is not None and rr >= 3.0:
        points += 1
    return points


def _priority_key(obj: dict) -> tuple:
    family_id = str(obj.get("family_id") or NONE)
    try:
        family_priority = -FAMILY_ORDER.index(family_id)
    except ValueError:
        family_priority = -999

    return (
        int(_bool(obj, "entry_structure_valid")),
        int(_bool(obj, "admission_ready")),
        int(_bool(obj, "watch_ready")),
        _path_quality(obj),
        _geometry_quality(obj),
        _score(obj),
        family_priority,
    )


def _family_snapshot(obj: dict) -> dict:
    return {
        "family_id": str(obj.get("family_id") or NONE),
        "state": str(obj.get("state") or "UNKNOWN"),
        "family_score": _score(obj),
        "watch_ready": _bool(obj, "watch_ready"),
        "admission_ready": _bool(obj, "admission_ready"),
        "entry_structure_valid": _bool(obj, "entry_structure_valid"),
        "failed": _is_failed(obj),
        "failure_scope": _failure_scope(obj),
        "path_status": str(obj.get("path_status") or "UNKNOWN"),
        "invalidation_level": obj.get("invalidation_level"),
        "target_1": obj.get("target_1"),
        "rr_to_t1": obj.get("rr_to_t1"),
    }


def resolve_families(families: dict[str, dict] | None) -> dict:
    """Resolve simultaneous setup-family evidence into one primary context.

    The resolver chooses a primary family but does not mutate any family object
    and does not create a trading tier. Failed siblings remain observable.
    """
    source = families if isinstance(families, dict) else {}

    detected: list[dict] = []
    for family_id in FAMILY_ORDER:
        obj = source.get(family_id)
        if isinstance(obj, dict) and obj.get("detected"):
            detected.append(obj)

    if not detected:
        return {
            "version": VERSION,
            "relationship": REL_NONE,
            "conflict_scope": CONFLICT_NONE,
            "resolved_primary_family": NONE,
            "secondary_families": [],
            "detected_count": 0,
            "viable_count": 0,
            "failed_families": [],
            "shared_failure_codes": [],
            "admission_ready": False,
            "entry_structure_valid": False,
            "confluence_count": 0,
            "score_stacking_allowed": False,
            "capital_authority": False,
            "reason_codes": ["NO_DETECTED_FAMILY"],
            "family_snapshots": [],
        }

    failed = [obj for obj in detected if _is_failed(obj)]
    viable = [obj for obj in detected if not _is_failed(obj)]

    shared_failure_codes = sorted(
        {
            code
            for obj in failed
            for code in _codes(obj)
            if code in _SHARED_FAILURE_CODES
        }
    )

    candidates = viable if viable else detected
    primary_obj = max(candidates, key=_priority_key)
    primary = str(primary_obj.get("family_id") or NONE)
    secondary = [
        str(obj.get("family_id") or NONE)
        for obj in detected
        if str(obj.get("family_id") or NONE) != primary
    ]

    ready_viable = [obj for obj in viable if _bool(obj, "admission_ready")]
    entry_valid_viable = [obj for obj in viable if _bool(obj, "entry_structure_valid")]
    watch_viable = [obj for obj in viable if _bool(obj, "watch_ready")]

    conflict_scope = CONFLICT_NONE
    if failed:
        conflict_scope = (
            CONFLICT_SHARED
            if any(_failure_scope(obj) == CONFLICT_SHARED for obj in failed)
            else CONFLICT_LOCAL
        )

    reason_codes: list[str] = []
    if not viable:
        relationship = REL_ALL_FAILED
        reason_codes.append("ALL_DETECTED_FAMILIES_FAILED")
    elif failed:
        relationship = REL_CONTRADICTORY
        reason_codes.append(
            "SHARED_FAILURE_PRESENT"
            if conflict_scope == CONFLICT_SHARED
            else "FAMILY_LOCAL_FAILURE_PRESENT"
        )
        if conflict_scope == CONFLICT_LOCAL and ready_viable:
            reason_codes.append("VALID_PRIMARY_PRESERVED_DESPITE_LOCAL_SIBLING_FAILURE")
    elif len(ready_viable) >= 2:
        relationship = REL_CONFLUENT
        reason_codes.append("MULTIPLE_ADMISSION_READY_FAMILIES")
        if len(entry_valid_viable) >= 2:
            reason_codes.append("MULTIPLE_ENTRY_STRUCTURES_VALID")
    elif len(ready_viable) == 1 and len(watch_viable) >= 2:
        relationship = REL_COMPATIBLE
        reason_codes.append("ONE_PRIMARY_READY_WITH_SUPPORTING_FAMILY_CONTEXT")
    elif len(viable) >= 2:
        relationship = REL_AMBIGUOUS
        reason_codes.append("MULTIPLE_FAMILIES_DETECTED_WITHOUT_CLEAR_SHARED_READINESS")
    else:
        relationship = REL_SINGLE
        reason_codes.append("SINGLE_VIABLE_FAMILY")

    if shared_failure_codes:
        reason_codes.append("COMMON_GATE_FAILURE_REMAINS_SOVEREIGN")

    return {
        "version": VERSION,
        "relationship": relationship,
        "conflict_scope": conflict_scope,
        "resolved_primary_family": primary,
        "secondary_families": secondary,
        "detected_count": len(detected),
        "viable_count": len(viable),
        "failed_families": [str(obj.get("family_id") or NONE) for obj in failed],
        "shared_failure_codes": shared_failure_codes,
        "admission_ready": bool(viable and _bool(primary_obj, "admission_ready")),
        "entry_structure_valid": bool(viable and _bool(primary_obj, "entry_structure_valid")),
        "confluence_count": len(ready_viable),
        "score_stacking_allowed": False,
        "capital_authority": False,
        "reason_codes": reason_codes,
        "family_snapshots": [_family_snapshot(obj) for obj in detected],
    }


def reconcile_compiled_evidence(evidence: dict | None) -> dict:
    """Return a deep-copied SFC object with CFR-1 primary resolution applied.

    The raw SFC compiler primary is retained under ``compiler_primary_*`` for
    provenance. Reconciliation is idempotent: calling it again does not erase
    the original compiler selection. Per-family objects are never mutated.
    """
    source = evidence if isinstance(evidence, dict) else {}
    out = deepcopy(source)
    families = out.get("families")
    families = families if isinstance(families, dict) else {}

    compiler_primary = str(
        source.get("compiler_primary_family")
        or source.get("primary_family")
        or NONE
    )
    compiler_primary_obj = families.get(compiler_primary)
    compiler_primary_obj = (
        compiler_primary_obj if isinstance(compiler_primary_obj, dict) else {}
    )
    out["compiler_primary_family"] = compiler_primary
    out["compiler_primary_state"] = str(
        source.get("compiler_primary_state")
        or source.get("primary_state")
        or compiler_primary_obj.get("state")
        or "NONE"
    )
    out["compiler_primary_family_score"] = int(
        source.get("compiler_primary_family_score")
        or source.get("primary_family_score")
        or compiler_primary_obj.get("family_score")
        or 0
    )

    resolution = resolve_families(families)
    out["family_resolution"] = resolution
    out["resolver_version"] = VERSION

    primary = resolution["resolved_primary_family"]
    primary_obj = families.get(primary) if primary != NONE else None
    primary_obj = primary_obj if isinstance(primary_obj, dict) else None

    out["primary_family"] = primary
    out["detected_families"] = [
        family_id
        for family_id in FAMILY_ORDER
        if isinstance(families.get(family_id), dict)
        and families[family_id].get("detected")
    ]
    out["watch_ready"] = any(
        bool(obj.get("watch_ready"))
        for obj in families.values()
        if isinstance(obj, dict)
        and obj.get("detected")
        and not _is_failed(obj)
    )
    out["admission_ready"] = bool(
        primary_obj and not _is_failed(primary_obj) and primary_obj.get("admission_ready")
    )
    out["entry_structure_valid"] = bool(
        primary_obj and not _is_failed(primary_obj) and primary_obj.get("entry_structure_valid")
    )
    out["primary_state"] = primary_obj.get("state") if primary_obj else "NONE"
    out["primary_family_score"] = _score(primary_obj) if primary_obj else 0
    out["primary_invalidation_level"] = primary_obj.get("invalidation_level") if primary_obj else None
    out["primary_target_1"] = primary_obj.get("target_1") if primary_obj else None
    out["primary_rr_to_t1"] = primary_obj.get("rr_to_t1") if primary_obj else None

    return out

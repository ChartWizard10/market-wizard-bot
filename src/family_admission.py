"""Setup-family admission arbitration for Chart Wizard.

SFC-2A defines how normalized setup-family evidence may influence deep-analysis
admission/ranking without granting a trading tier, capital permission, Discord
routing, or bypassing common fatal gates.

CFR-2 production wiring adds one deliberate normalization side effect:
``enriched['setup_family_evidence']`` is replaced with CFR's deep-copied,
resolved evidence before arbitration. This guarantees that candidate admission
and the later GPT-5.6 prompt see the same primary family and relationship state.
The underlying per-family evidence objects are preserved byte-semantically in
the reconciled copy, and compiler-primary provenance is retained separately.

Doctrine boundary:
- family evidence may repair a generic prefilter blind spot;
- family evidence may not rescue bad data, hostile value, failed retest,
  blocked overhead, or excessive extension;
- family-specific invalidation / target / R:R may satisfy generic prefilter
  geometry for model admission only;
- cross-family confluence never adds scores and never grants a tier;
- a local failed sibling does not automatically cancel a distinct valid primary;
- shared/common failures remain owned by the existing active veto/tiering stack;
- final tiering, ladder, seal, invalidation, path and capital law remain
  downstream and sovereign.
"""

from __future__ import annotations

from typing import Any

from src import family_resolver

VERSION = "SFC-2A"
RESOLUTION_BRIDGE_VERSION = "CFR-2"

NONE = "NONE"
LOCKED_FAMILIES = {
    "BREAK_RETEST_CONTINUATION",
    "VCP_BREAK_RETEST",
    "SMA_CRADLE_CONTINUATION",
    "GAP_FILL_REVERSAL",
}

NEVER_RESCUE_VETOES = {
    "data_empty",
    "data_error",
    "insufficient_bars",
    "stale_data",
    "overhead_blocked",
    "price_too_extended",
    "retest_failed",
    "hostile_value_alignment",
}

CONDITIONAL_FAMILY_VETOES = {
    "no_clear_structure",
    "mid_range_no_edge",
    "no_clear_invalidation_estimate",
    "no_target_path",
    "rr_below_threshold_estimate",
}


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _resolved_evidence(enriched: dict) -> dict:
    """Normalize setup-family evidence once and attach it to the enriched row.

    Reconciliation itself is pure/deep-copy. The assignment is intentional so
    the same resolved object is consumed by prefilter admission and, later in
    the scheduler, by GPT-5.6 prompt construction.
    """
    evidence = enriched.get("setup_family_evidence")
    if not isinstance(evidence, dict):
        return {}

    resolved = family_resolver.reconcile_compiled_evidence(evidence)
    enriched["setup_family_evidence"] = resolved
    return resolved


def _evidence_bool(evidence: dict, primary_obj: dict, key: str) -> bool:
    """Trust reconciled top-level False; fall back only when key is absent."""
    if key in evidence:
        return bool(evidence.get(key))
    return bool(primary_obj.get(key))


def _evidence_int(evidence: dict, primary_obj: dict, key: str, fallback: str) -> int:
    if key in evidence:
        try:
            return int(evidence.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(primary_obj.get(fallback) or 0)
    except (TypeError, ValueError):
        return 0


def _family_snapshot(enriched: dict) -> dict:
    evidence = _resolved_evidence(enriched)
    if not evidence:
        return {}

    primary = str(evidence.get("primary_family") or NONE)
    if primary not in LOCKED_FAMILIES:
        return {}

    families = evidence.get("families")
    families = families if isinstance(families, dict) else {}
    primary_obj = families.get(primary)
    primary_obj = primary_obj if isinstance(primary_obj, dict) else {}
    resolution = evidence.get("family_resolution")
    resolution = resolution if isinstance(resolution, dict) else {}

    return {
        "primary_family": primary,
        "compiler_primary_family": str(evidence.get("compiler_primary_family") or NONE),
        "primary_state": str(
            evidence.get("primary_state")
            if "primary_state" in evidence
            else primary_obj.get("state") or "UNKNOWN"
        ),
        "family_score": _evidence_int(
            evidence, primary_obj, "primary_family_score", "family_score"
        ),
        "watch_ready": _evidence_bool(evidence, primary_obj, "watch_ready"),
        "admission_ready": _evidence_bool(evidence, primary_obj, "admission_ready"),
        "entry_structure_valid": _evidence_bool(
            evidence, primary_obj, "entry_structure_valid"
        ),
        "invalidation_level": (
            evidence.get("primary_invalidation_level")
            if "primary_invalidation_level" in evidence
            else primary_obj.get("invalidation_level")
        ),
        "target_1": (
            evidence.get("primary_target_1")
            if "primary_target_1" in evidence
            else primary_obj.get("target_1")
        ),
        "rr_to_t1": (
            evidence.get("primary_rr_to_t1")
            if "primary_rr_to_t1" in evidence
            else primary_obj.get("rr_to_t1")
        ),
        "path_status": str(primary_obj.get("path_status") or "UNKNOWN"),
        "blockers": list(primary_obj.get("blockers") or []),
        "soft_caps": list(primary_obj.get("soft_caps") or []),
        "relationship": str(resolution.get("relationship") or "NONE"),
        "conflict_scope": str(resolution.get("conflict_scope") or "NONE"),
        "secondary_families": list(resolution.get("secondary_families") or []),
        "failed_families": list(resolution.get("failed_families") or []),
        "shared_failure_codes": list(resolution.get("shared_failure_codes") or []),
        "confluence_count": int(resolution.get("confluence_count") or 0),
        "score_stacking_allowed": bool(resolution.get("score_stacking_allowed", False)),
        "capital_authority": bool(resolution.get("capital_authority", False)),
        "resolver_reason_codes": list(resolution.get("reason_codes") or []),
    }


def build_family_admission_decision(
    enriched: dict,
    prefilter_score: int | float,
    veto_flags: list[str] | tuple[str, ...] | None,
    config: dict,
) -> dict:
    """Return governed model-admission arbitration for one ticker.

    The result intentionally contains no final tier, capital action or routing
    fields. Family confluence can change which family is inspected and ranked;
    it cannot convert evidence into capital permission.
    """
    enriched = enriched if isinstance(enriched, dict) else {}
    vetoes = list(veto_flags or [])
    score = max(0, min(100, int(prefilter_score or 0)))

    cfg = config.get("prefilter", {}).get("family_admission", {})
    cfg = cfg if isinstance(cfg, dict) else {}
    enabled = bool(cfg.get("enabled", True))
    min_family_score = int(cfg.get("min_family_score", 65))
    max_rank_score = int(cfg.get("max_family_rank_score", 95))
    min_rr = float(config.get("tiers", {}).get("snipe_it", {}).get("min_rr", 3.0))

    if not enabled:
        return {
            "version": VERSION,
            "resolution_bridge_version": RESOLUTION_BRIDGE_VERSION,
            "active": False,
            "primary_family": NONE,
            "primary_state": "NONE",
            "family_score": 0,
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "admitted_by_family": False,
            "rescued_vetoes": [],
            "remaining_vetoes": vetoes,
            "admission_rank_score": score,
            "reason": "FAMILY_ADMISSION_DISABLED",
        }

    family = _family_snapshot(enriched)
    if not family:
        return {
            "version": VERSION,
            "resolution_bridge_version": RESOLUTION_BRIDGE_VERSION,
            "active": False,
            "primary_family": NONE,
            "primary_state": "NONE",
            "family_score": 0,
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "admitted_by_family": False,
            "rescued_vetoes": [],
            "remaining_vetoes": vetoes,
            "admission_rank_score": score,
            "reason": "NO_ACTIVE_FAMILY_ADMISSION_EVIDENCE",
        }

    # CFR must never become authority accidentally.
    if family["score_stacking_allowed"] or family["capital_authority"]:
        return {
            "version": VERSION,
            "resolution_bridge_version": RESOLUTION_BRIDGE_VERSION,
            "active": False,
            "primary_family": family["primary_family"],
            "primary_state": family["primary_state"],
            "family_score": int(family["family_score"]),
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "admitted_by_family": False,
            "rescued_vetoes": [],
            "remaining_vetoes": vetoes,
            "admission_rank_score": score,
            "reason": "CFR_AUTHORITY_CONTRACT_VIOLATION",
        }

    family_score = max(0, min(100, int(family["family_score"])))
    family_lane_ready = bool(
        family["admission_ready"] and family_score >= min_family_score
    )

    rescued: list[str] = []
    remaining: list[str] = []

    family_inv = _num(family.get("invalidation_level"))
    family_target = _num(family.get("target_1"))
    family_rr = _num(family.get("rr_to_t1"))

    for veto in vetoes:
        if veto in NEVER_RESCUE_VETOES:
            remaining.append(veto)
            continue

        if not family_lane_ready or veto not in CONDITIONAL_FAMILY_VETOES:
            remaining.append(veto)
            continue

        if veto in {"no_clear_structure", "mid_range_no_edge"}:
            rescued.append(veto)
            continue

        if veto == "no_clear_invalidation_estimate":
            if family_inv is not None:
                rescued.append(veto)
            else:
                remaining.append(veto)
            continue

        if veto == "no_target_path":
            if family_target is not None:
                rescued.append(veto)
            else:
                remaining.append(veto)
            continue

        if veto == "rr_below_threshold_estimate":
            if family_rr is not None and family_rr >= min_rr:
                rescued.append(veto)
            else:
                remaining.append(veto)
            continue

        remaining.append(veto)

    admitted_by_family = bool(family_lane_ready and not remaining)

    # Rank influence remains single-family and bounded. CONFLUENT never adds a
    # second family score or bonus. Entry proof keeps the existing +3 maximum.
    admission_rank_score = score
    if family_lane_ready:
        family_rank = family_score + (3 if family["entry_structure_valid"] else 0)
        admission_rank_score = max(score, min(max_rank_score, family_rank))

    if admitted_by_family:
        reason = "FAMILY_ADMISSION_READY"
    elif family["watch_ready"] and not family["admission_ready"]:
        reason = "FAMILY_WATCH_READY_NOT_ADMISSION_READY"
    elif family_score < min_family_score:
        reason = "FAMILY_SCORE_BELOW_ADMISSION_FLOOR"
    elif remaining:
        reason = "COMMON_GATE_BLOCKER_REMAINS"
    else:
        reason = "FAMILY_NOT_ADMISSION_READY"

    return {
        "version": VERSION,
        "resolution_bridge_version": RESOLUTION_BRIDGE_VERSION,
        "active": True,
        "primary_family": family["primary_family"],
        "compiler_primary_family": family["compiler_primary_family"],
        "primary_state": family["primary_state"],
        "family_score": family_score,
        "watch_ready": family["watch_ready"],
        "admission_ready": family["admission_ready"],
        "entry_structure_valid": family["entry_structure_valid"],
        "family_invalidation_level": family.get("invalidation_level"),
        "family_target_1": family.get("target_1"),
        "family_rr_to_t1": family.get("rr_to_t1"),
        "family_path_status": family.get("path_status"),
        "family_blockers": family.get("blockers", []),
        "family_soft_caps": family.get("soft_caps", []),
        "family_relationship": family["relationship"],
        "family_conflict_scope": family["conflict_scope"],
        "secondary_families": family["secondary_families"],
        "failed_families": family["failed_families"],
        "shared_failure_codes": family["shared_failure_codes"],
        "confluence_count": family["confluence_count"],
        "resolver_reason_codes": family["resolver_reason_codes"],
        "admitted_by_family": admitted_by_family,
        "rescued_vetoes": rescued,
        "remaining_vetoes": remaining,
        "admission_rank_score": admission_rank_score,
        "reason": reason,
    }

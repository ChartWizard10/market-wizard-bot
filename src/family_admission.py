"""Setup-family admission arbitration for Chart Wizard.

Phase SFC-2A defines how normalized SFC-1 family evidence may influence
*deep-analysis admission and ranking* without ever granting a trading tier,
capital permission, Discord routing, or bypassing common fatal gates.

Doctrine boundary:
- family evidence may repair a generic prefilter blind spot;
- family evidence may not rescue bad data, hostile value, failed retest,
  blocked overhead, or excessive extension;
- family-specific invalidation / target / R:R may satisfy generic prefilter
  geometry for model admission only;
- final tiering, ladder, seal, invalidation, path and capital law remain
  downstream and sovereign.

This module is pure and side-effect free. SFC-2B wires it into prefilter.
"""

from __future__ import annotations

from typing import Any

VERSION = "SFC-2A"

NONE = "NONE"
LOCKED_FAMILIES = {
    "BREAK_RETEST_CONTINUATION",
    "VCP_BREAK_RETEST",
    "SMA_CRADLE_CONTINUATION",
    "GAP_FILL_REVERSAL",
}

# These are never rescued by a family label. They represent truth/quality
# failures that remain common across every setup family.
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

# These generic-prefilter vetoes can be superseded for *model admission only*
# when the family compiler supplies equivalent, explicit evidence.
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


def _family_snapshot(enriched: dict) -> dict:
    evidence = enriched.get("setup_family_evidence")
    if not isinstance(evidence, dict):
        return {}

    primary = str(evidence.get("primary_family") or NONE)
    if primary not in LOCKED_FAMILIES:
        return {}

    families = evidence.get("families")
    families = families if isinstance(families, dict) else {}
    primary_obj = families.get(primary)
    primary_obj = primary_obj if isinstance(primary_obj, dict) else {}

    return {
        "primary_family": primary,
        "primary_state": str(
            evidence.get("primary_state")
            or primary_obj.get("state")
            or "UNKNOWN"
        ),
        "family_score": int(
            evidence.get("primary_family_score")
            or primary_obj.get("family_score")
            or 0
        ),
        "watch_ready": bool(
            evidence.get("watch_ready")
            or primary_obj.get("watch_ready")
        ),
        "admission_ready": bool(
            evidence.get("admission_ready")
            or primary_obj.get("admission_ready")
        ),
        "entry_structure_valid": bool(
            evidence.get("entry_structure_valid")
            or primary_obj.get("entry_structure_valid")
        ),
        "invalidation_level": (
            evidence.get("primary_invalidation_level")
            if evidence.get("primary_invalidation_level") is not None
            else primary_obj.get("invalidation_level")
        ),
        "target_1": (
            evidence.get("primary_target_1")
            if evidence.get("primary_target_1") is not None
            else primary_obj.get("target_1")
        ),
        "rr_to_t1": (
            evidence.get("primary_rr_to_t1")
            if evidence.get("primary_rr_to_t1") is not None
            else primary_obj.get("rr_to_t1")
        ),
        "path_status": str(primary_obj.get("path_status") or "UNKNOWN"),
        "blockers": list(primary_obj.get("blockers") or []),
        "soft_caps": list(primary_obj.get("soft_caps") or []),
    }


def build_family_admission_decision(
    enriched: dict,
    prefilter_score: int | float,
    veto_flags: list[str] | tuple[str, ...] | None,
    config: dict,
) -> dict:
    """Return SFC-2A model-admission arbitration for one ticker.

    The result intentionally contains no final tier, capital action or routing
    fields. It can only say whether the setup-family lane is eligible to be
    considered by the model-admission stage.
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

    family = _family_snapshot(enriched)
    if not enabled or not family:
        return {
            "version": VERSION,
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

    # Rank influence is admission-only. A strong family object can repair a
    # legacy prefilter score blind spot, but it cannot exceed the configured cap
    # and it never changes the original prefilter score.
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
        "active": True,
        "primary_family": family["primary_family"],
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
        "admitted_by_family": admitted_by_family,
        "rescued_vetoes": rescued,
        "remaining_vetoes": remaining,
        "admission_rank_score": admission_rank_score,
        "reason": reason,
    }

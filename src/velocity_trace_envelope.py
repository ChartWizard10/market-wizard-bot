"""VELOCITY-1C — scan-trace observation bridge.

This module converts existing scan-time prefilter/judgment evidence into the
immutable VELOCITY-1B observation envelope without introducing future data.
It is the contract immediately before live scan-telemetry wiring.

Why a bridge is necessary
-------------------------
The scanner has three research populations that must remain distinguishable:

1. ``analyzed`` — selected for GPT-5.6 and completed deterministic judgment;
2. ``model_failed`` / historical ``claude_failed`` — selected for deep analysis
   but no valid model result was produced;
3. ``ranked_not_analyzed`` near-cut observations — eligible candidates just
   outside the current 30-candidate model cap, especially ranks 31-60.

The third population is essential for the later CAP-40 counterfactual. It must
not be mislabeled WAIT merely because GPT-5.6 was never called.

VELOCITY-1C therefore adds explicit selection/analysis provenance around the
VELOCITY-1B envelope. No tier/capital/routing authority is created. No future
bar or outcome field is accepted or produced.

This module is PURE: no file writes, no network calls, no telemetry mutation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from src.velocity_observation import build_observation_envelope

VERSION = "VELOCITY-1C"

TRACE_ANALYZED = "analyzed"
TRACE_MODEL_FAILED = "model_failed"
TRACE_CLAUDE_FAILED = "claude_failed"  # historical compatibility name
TRACE_RANKED_NOT_ANALYZED = "ranked_not_analyzed"

CAPTURE_TRACE_KINDS = {
    TRACE_ANALYZED,
    TRACE_MODEL_FAILED,
    TRACE_CLAUDE_FAILED,
    TRACE_RANKED_NOT_ANALYZED,
}

_FORBIDDEN_FUTURE_KEYS = {
    "future_bars",
    "future_daily_bars",
    "forward_outcome",
    "outcome_label",
    "target_hit_session",
    "stop_hit_session",
    "mfe_pct",
    "mae_pct",
    "max_favorable_excursion_pct",
    "max_adverse_excursion_pct",
}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _scan_id_to_observed_at(scan_id: str) -> str | None:
    """Recover the UTC scan start encoded by production scan IDs.

    Production full-scan IDs are ``scan_YYYYMMDD_HHMMSS_<nonce>`` and are
    generated from UTC. The helper never fabricates a date for manual IDs that
    do not carry one.
    """
    value = str(scan_id or "").strip()
    parts = value.split("_")
    if len(parts) < 4 or parts[0] != "scan":
        return None
    stamp = f"{parts[1]}_{parts[2]}"
    try:
        dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _fallback_observed_at(judgment: dict) -> str | None:
    """Use model/final-signal timestamp only when the scan ID cannot supply time."""
    if not isinstance(judgment, dict):
        return None
    final_signal = judgment.get("final_signal")
    final_signal = final_signal if isinstance(final_signal, dict) else {}
    candidate = final_signal.get("timestamp_et") or judgment.get("timestamp_et")
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    text = candidate.strip()
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text


def should_capture_trace_observation(trace_kind: str, *, near_cut: bool = False) -> bool:
    """True only for populations required by validation/CAP-40 research."""
    kind = str(trace_kind or "").strip().lower()
    if kind in {TRACE_ANALYZED, TRACE_MODEL_FAILED, TRACE_CLAUDE_FAILED}:
        return True
    if kind == TRACE_RANKED_NOT_ANALYZED:
        return bool(near_cut)
    return False


def _family_evidence_from_prefilter(prefilter_row: dict) -> dict:
    """Reconstruct compact *scan-time* family context already in prefilter output.

    No pattern is redetected here. The function only projects fields already
    computed by SFC/CFR admission and key-feature ledgers.
    """
    row = prefilter_row if isinstance(prefilter_row, dict) else {}
    kf = row.get("key_features")
    kf = kf if isinstance(kf, dict) else {}
    fa = row.get("family_admission")
    fa = fa if isinstance(fa, dict) else {}

    primary = str(
        fa.get("primary_family")
        or kf.get("setup_family_primary")
        or "NONE"
    )
    if primary == "NONE":
        return {
            "version": "SFC/CFR_SCAN_PROJECTION",
            "primary_family": "NONE",
            "detected_families": [],
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "primary_state": "NONE",
            "primary_family_score": 0,
            "families": {},
        }

    state = str(
        fa.get("primary_state")
        or kf.get("setup_family_state")
        or "UNKNOWN"
    )
    try:
        score = int(
            fa.get("family_score")
            if fa.get("family_score") is not None
            else kf.get("setup_family_score") or 0
        )
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    watch_ready = bool(
        fa.get("watch_ready")
        if "watch_ready" in fa
        else kf.get("setup_family_watch_ready")
    )
    admission_ready = bool(
        fa.get("admission_ready")
        if "admission_ready" in fa
        else kf.get("setup_family_admission_ready")
    )
    entry_valid = bool(
        fa.get("entry_structure_valid")
        if "entry_structure_valid" in fa
        else kf.get("setup_family_entry_structure_valid")
    )

    invalidation = _float(
        fa.get("family_invalidation_level")
        if fa.get("family_invalidation_level") is not None
        else kf.get("setup_family_invalidation")
    )
    target = _float(
        fa.get("family_target_1")
        if fa.get("family_target_1") is not None
        else kf.get("setup_family_target_1")
    )
    rr = _float(
        fa.get("family_rr_to_t1")
        if fa.get("family_rr_to_t1") is not None
        else kf.get("setup_family_rr_to_t1")
    )

    relationship = str(fa.get("family_relationship") or "NONE")
    conflict_scope = str(fa.get("family_conflict_scope") or "NONE")
    secondary = list(fa.get("secondary_families") or [])
    failed = list(fa.get("failed_families") or [])
    shared = list(fa.get("shared_failure_codes") or [])
    resolver_reasons = list(fa.get("resolver_reason_codes") or [])

    primary_obj = {
        "family_id": primary,
        "detected": True,
        "state": state,
        "family_score": score,
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_valid,
        "invalidation_level": invalidation,
        "target_1": target,
        "rr_to_t1": rr,
        "path_status": str(fa.get("family_path_status") or "UNKNOWN"),
        "blockers": list(fa.get("family_blockers") or []),
        "soft_caps": list(fa.get("family_soft_caps") or []),
        "metrics": {},
    }

    return {
        "version": "SFC/CFR_SCAN_PROJECTION",
        "primary_family": primary,
        "compiler_primary_family": str(fa.get("compiler_primary_family") or primary),
        "detected_families": [primary] + [x for x in secondary if x != primary],
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_valid,
        "primary_state": state,
        "primary_family_score": score,
        "primary_invalidation_level": invalidation,
        "primary_target_1": target,
        "primary_rr_to_t1": rr,
        "family_resolution": {
            "version": "CFR_SCAN_PROJECTION",
            "relationship": relationship,
            "conflict_scope": conflict_scope,
            "resolved_primary_family": primary,
            "secondary_families": secondary,
            "failed_families": failed,
            "shared_failure_codes": shared,
            "confluence_count": int(fa.get("confluence_count") or 0),
            "score_stacking_allowed": False,
            "capital_authority": False,
            "reason_codes": resolver_reasons,
        },
        "families": {primary: primary_obj},
    }


def _features_from_prefilter(prefilter_row: dict) -> dict:
    row = prefilter_row if isinstance(prefilter_row, dict) else {}
    kf = row.get("key_features")
    kf = kf if isinstance(kf, dict) else {}
    family = _family_evidence_from_prefilter(row)

    target = _float(family.get("primary_target_1"))
    targets = []
    if target is not None:
        targets = [{"label": "FAMILY_T1", "level": target, "reason": "scan-time family target"}]

    return {
        "current_price": _float(kf.get("current_price")),
        "atr": _float(kf.get("atr")),
        "invalidation_level": _float(
            family.get("primary_invalidation_level")
        ),
        "targets": targets,
        "estimated_rr": _float(kf.get("estimated_rr")),
        "overhead_status": kf.get("overhead_status"),
        "sma_value_alignment": kf.get("sma_value_alignment"),
        "structure_event": kf.get("structure_event"),
        "retest_status": kf.get("retest_status"),
        "volume_behavior": kf.get("volume_behavior"),
        "setup_family_evidence": family,
    }


def _judgment_projection(judgment: dict | None) -> dict:
    out = deepcopy(judgment) if isinstance(judgment, dict) else {}
    if "four_hour_operational" not in out and isinstance(out.get("four_hour_real"), dict):
        out["four_hour_operational"] = deepcopy(out["four_hour_real"])
    return out


def _normalize_unanalyzed_envelope(
    envelope: dict,
    *,
    observation_stage: str,
    deep_analysis_selected: bool,
) -> dict:
    """Remove the false implication that an unanalysed candidate was judged WAIT."""
    out = deepcopy(envelope)
    stage = str(observation_stage or "UNANALYZED").strip().upper()
    out["stage"] = stage

    final_state = out.get("final_state")
    if isinstance(final_state, dict):
        final_state["observed_tier"] = None
        final_state["capital_action"] = None
        final_state["safe_for_alert"] = False
        final_state["capital_authorized"] = False

    feasibility = out.get("velocity_feasibility")
    if isinstance(feasibility, dict):
        feasibility["stage"] = stage
        feasibility["capital_authorized"] = False
        feasibility["research_only"] = True
        feasibility["capital_authority"] = False

    out["selection_context"] = {
        "trace_kind": observation_stage,
        "deep_analysis_selected": bool(deep_analysis_selected),
        "analysis_performed": False,
        "final_tier_observed": False,
        "capital_authorized": False,
    }
    return out


def _contains_forbidden_future_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_FUTURE_KEYS:
                return True
            if _contains_forbidden_future_key(nested):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_future_key(x) for x in value)
    return False


def build_trace_observation(
    *,
    scan_id: str,
    trace_kind: str,
    ticker: str,
    prefilter_row: dict | None,
    judgment: dict | None = None,
    near_cut: bool = False,
) -> dict | None:
    """Build one immutable scan-time research observation for a telemetry trace.

    Returns ``None`` for trace populations not needed by the current validation
    plan. The result contains no future outcome and has no capital authority.
    """
    kind = str(trace_kind or "").strip().lower()
    if not should_capture_trace_observation(kind, near_cut=near_cut):
        return None

    row = prefilter_row if isinstance(prefilter_row, dict) else {}
    projected_judgment = _judgment_projection(judgment)
    features = _features_from_prefilter(row)

    observed_at = _scan_id_to_observed_at(scan_id) or _fallback_observed_at(projected_judgment)
    if observed_at is None:
        return None

    analysis_performed = kind == TRACE_ANALYZED
    deep_analysis_selected = kind in {
        TRACE_ANALYZED,
        TRACE_MODEL_FAILED,
        TRACE_CLAUDE_FAILED,
    }

    envelope = build_observation_envelope(
        scan_id=str(scan_id),
        ticker=str(ticker),
        observed_at=observed_at,
        prefilter=row,
        judgment=projected_judgment if analysis_performed else None,
        features=features,
    )
    if envelope is None:
        return None

    if analysis_performed:
        out = deepcopy(envelope)
        final_state = out.get("final_state")
        capital_authorized = bool(
            isinstance(final_state, dict) and final_state.get("capital_authorized")
        )
        out["selection_context"] = {
            "trace_kind": kind,
            "deep_analysis_selected": True,
            "analysis_performed": True,
            "final_tier_observed": True,
            "capital_authorized": capital_authorized,
        }
    else:
        out = _normalize_unanalyzed_envelope(
            envelope,
            observation_stage=kind,
            deep_analysis_selected=deep_analysis_selected,
        )

    out["bridge_version"] = VERSION
    out["research_only"] = True
    out["capital_authority"] = False

    if _contains_forbidden_future_key(out):
        # Fail closed. Scan-time telemetry must never persist future labels here.
        return None

    return out

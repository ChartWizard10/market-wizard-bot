"""Algorithmic prefilter scorer and GPT-5.6 candidate admission layer.

Scans the full ticker universe using structure-first features, scores the legacy
0-100 prefilter, applies common vetoes, arbitrates deterministic setup-family
evidence, ranks candidates, and caps the deep-analysis list.

This is NOT the final trade grader. It does NOT call the model and it does NOT
assign trading tiers. SFC-2B may admit a candidate for GPT-5.6 inspection when
a normalized setup family repairs a generic prefilter blind spot, but final
tiering, ladder, seal, risk and capital authority remain downstream.

Historical ``claude_*`` result keys are retained as compatibility aliases while
provider-neutral nomenclature is migrated separately. Production provider truth
is OpenAI GPT-5.6.

No rsi, macd, bollinger_bands, or stochastic. Ever.
"""

import logging

from src import family_admission

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Veto flag constants
# ---------------------------------------------------------------------------

VETO_DATA_EMPTY = "data_empty"
VETO_DATA_ERROR = "data_error"
VETO_INSUFFICIENT_BARS = "insufficient_bars"
VETO_STALE_DATA = "stale_data"
VETO_NO_CLEAR_STRUCTURE = "no_clear_structure"
VETO_NO_INVALIDATION = "no_clear_invalidation_estimate"
VETO_NO_TARGET_PATH = "no_target_path"
VETO_OVERHEAD_BLOCKED = "overhead_blocked"
VETO_PRICE_TOO_EXTENDED = "price_too_extended"
VETO_RETEST_FAILED = "retest_failed"
VETO_MID_RANGE_NO_EDGE = "mid_range_no_edge"
VETO_HOSTILE_ALIGNMENT = "hostile_value_alignment"
VETO_RR_BELOW_THRESHOLD = "rr_below_threshold_estimate"

# Legacy generic hard-block set. SFC-2A family arbitration owns the narrow,
# explicit distinction between never-rescuable common failures and conditional
# generic admission blind spots. Original veto flags are always preserved.
_HARD_BLOCK_VETOES = {
    VETO_DATA_EMPTY,
    VETO_DATA_ERROR,
    VETO_INSUFFICIENT_BARS,
    VETO_STALE_DATA,
    VETO_NO_CLEAR_STRUCTURE,
    VETO_NO_INVALIDATION,
    VETO_NO_TARGET_PATH,
    VETO_OVERHEAD_BLOCKED,
    VETO_PRICE_TOO_EXTENDED,
    VETO_RETEST_FAILED,
    VETO_MID_RANGE_NO_EDGE,
    VETO_HOSTILE_ALIGNMENT,
    VETO_RR_BELOW_THRESHOLD,
}


# ---------------------------------------------------------------------------
# Per-category scoring helpers
# ---------------------------------------------------------------------------

def _score_trend_alignment(enriched: dict, weight: int) -> int:
    alignment = enriched.get("sma_value_alignment", "unavailable")
    if alignment == "supportive":
        return weight
    if alignment == "mixed":
        return round(weight * 0.55)
    return 0


def _score_structure_event(enriched: dict, weight: int) -> int:
    event = enriched.get("structure_event", "none")
    wick_only = enriched.get("wick_only_break", False)

    if event == "MSS":
        return weight
    if event in ("BOS", "failed_breakdown_reclaim", "accepted_break"):
        return round(weight * 0.90)
    if event == "reclaim":
        return round(weight * 0.75)
    if event == "CHOCH":
        return round(weight * 0.40)
    if wick_only:
        return round(weight * 0.15)
    return 0


def _score_zone_quality(enriched: dict, weight: int) -> int:
    fvg = enriched.get("fvg")
    ob = enriched.get("ob")
    score = 0

    if fvg and ob:
        score = weight
    elif fvg or ob:
        score = round(weight * 0.67)

    in_zone = (fvg and fvg.get("price_in_fvg")) or (ob and ob.get("price_at_ob"))
    if in_zone and score > 0:
        score = min(weight, score + round(weight * 0.20))
    return score


def _score_retest(enriched: dict, weight: int) -> int:
    status = enriched.get("retest_status", "missing")
    if status == "confirmed":
        return weight
    if status == "partial":
        return round(weight * 0.60)
    if status == "missing":
        return round(weight * 0.20)
    return 0


def _score_target_rr(enriched: dict, weight: int) -> int:
    overhead = enriched.get("overhead_status", "unknown")
    rr = enriched.get("estimated_rr")
    targets = enriched.get("targets", [])

    if overhead == "blocked" or not targets:
        return 0

    rr_strong = rr is not None and rr >= 3.0
    rr_weak = rr is not None and rr < 3.0

    if overhead == "clear":
        if rr_strong:
            return weight
        if rr_weak:
            return round(weight * 0.65)
        return round(weight * 0.50)

    if overhead == "moderate":
        if rr_strong:
            return round(weight * 0.67)
        if rr_weak:
            return round(weight * 0.40)
        return round(weight * 0.30)

    if rr_strong:
        return round(weight * 0.53)
    if rr_weak:
        return round(weight * 0.25)
    return round(weight * 0.20)


def _score_volume(enriched: dict, weight: int) -> int:
    behavior = enriched.get("volume_behavior", "unknown")
    if behavior == "expansion":
        return weight
    if behavior == "dryup":
        return round(weight * 0.80)
    if behavior == "neutral":
        return round(weight * 0.50)
    return round(weight * 0.20)


def _score_data_quality(enriched: dict, weight: int) -> int:
    status = enriched.get("data_status", "ERROR")
    if status == "OK":
        return weight
    if status == "STALE":
        return round(weight * 0.40)
    if status == "INSUFFICIENT":
        return round(weight * 0.20)
    return 0


# ---------------------------------------------------------------------------
# Scoring entry point
# ---------------------------------------------------------------------------

def algo_score(enriched: dict, config: dict) -> tuple[int, dict]:
    """Score a single enriched ticker 0-100. Returns (total, breakdown)."""
    weights = config.get("prefilter", {}).get("scoring_weights", {})

    w_trend = weights.get("trend_value_alignment", 15)
    w_struct = weights.get("structure_event", 20)
    w_zone = weights.get("fvg_ob_demand_zone_quality", 15)
    w_retest = weights.get("retest_proximity_status", 20)
    w_rr = weights.get("target_path_rr_estimate", 15)
    w_vol = weights.get("volume_participation", 10)
    w_data = weights.get("data_quality_recency", 5)

    s_trend = _score_trend_alignment(enriched, w_trend)
    s_struct = _score_structure_event(enriched, w_struct)
    s_zone = _score_zone_quality(enriched, w_zone)
    s_retest = _score_retest(enriched, w_retest)
    s_rr = _score_target_rr(enriched, w_rr)
    s_vol = _score_volume(enriched, w_vol)
    s_data = _score_data_quality(enriched, w_data)

    total = max(0, min(100, s_trend + s_struct + s_zone + s_retest + s_rr + s_vol + s_data))
    breakdown = {
        "trend_value_alignment": s_trend,
        "structure_event": s_struct,
        "fvg_ob_demand_zone_quality": s_zone,
        "retest_proximity_status": s_retest,
        "target_path_rr_estimate": s_rr,
        "volume_participation": s_vol,
        "data_quality_recency": s_data,
    }
    return total, breakdown


# ---------------------------------------------------------------------------
# Hard veto evaluation
# ---------------------------------------------------------------------------

def apply_hard_vetoes(enriched: dict, config: dict) -> list[str]:
    """Return active generic prefilter veto flags for this ticker.

    SFC-2B preserves this legacy veto ledger exactly. Family arbitration may
    explicitly supersede a narrow subset for model admission, but it never
    deletes the original evidence.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    max_extension = thresholds.get("max_price_extension_from_sma20_pct", 8)
    min_rr = config.get("tiers", {}).get("snipe_it", {}).get("min_rr", 3.0)

    vetoes: list[str] = []
    status = enriched.get("data_status", "ERROR")

    if status == "EMPTY":
        return [VETO_DATA_EMPTY]
    if status == "ERROR":
        return [VETO_DATA_ERROR]
    if status == "INSUFFICIENT":
        return [VETO_INSUFFICIENT_BARS]
    if status == "STALE":
        return [VETO_STALE_DATA]

    has_structure = enriched.get("structure_event", "none") != "none"
    has_fvg = bool(enriched.get("fvg"))
    has_ob = bool(enriched.get("ob"))
    has_zone = has_fvg or has_ob

    if not has_structure and not has_zone:
        vetoes.append(VETO_NO_CLEAR_STRUCTURE)
    if enriched.get("invalidation_level") is None:
        vetoes.append(VETO_NO_INVALIDATION)
    if not enriched.get("targets"):
        vetoes.append(VETO_NO_TARGET_PATH)
    if enriched.get("overhead_status") == "blocked":
        vetoes.append(VETO_OVERHEAD_BLOCKED)

    ext = enriched.get("price_extension_from_sma20_pct")
    if ext is not None and ext > max_extension:
        vetoes.append(VETO_PRICE_TOO_EXTENDED)

    if enriched.get("retest_status") == "failed":
        vetoes.append(VETO_RETEST_FAILED)
    if enriched.get("sma_value_alignment") == "hostile":
        vetoes.append(VETO_HOSTILE_ALIGNMENT)

    rr = enriched.get("estimated_rr")
    if rr is not None and rr < min_rr:
        vetoes.append(VETO_RR_BELOW_THRESHOLD)

    if (
        not has_structure
        and not has_zone
        and enriched.get("retest_status") in ("missing", "failed")
        and VETO_MID_RANGE_NO_EDGE not in vetoes
    ):
        vetoes.append(VETO_MID_RANGE_NO_EDGE)

    return vetoes


# ---------------------------------------------------------------------------
# Family snapshot helpers
# ---------------------------------------------------------------------------

def _family_key_features(enriched: dict) -> dict:
    evidence = enriched.get("setup_family_evidence")
    if not isinstance(evidence, dict):
        return {
            "setup_family_primary": "NONE",
            "setup_family_state": "NONE",
            "setup_family_score": 0,
            "setup_family_watch_ready": False,
            "setup_family_admission_ready": False,
            "setup_family_entry_structure_valid": False,
            "setup_family_invalidation": None,
            "setup_family_target_1": None,
            "setup_family_rr_to_t1": None,
        }

    return {
        "setup_family_primary": evidence.get("primary_family", "NONE"),
        "setup_family_state": evidence.get("primary_state", "NONE"),
        "setup_family_score": int(evidence.get("primary_family_score") or 0),
        "setup_family_watch_ready": bool(evidence.get("watch_ready")),
        "setup_family_admission_ready": bool(evidence.get("admission_ready")),
        "setup_family_entry_structure_valid": bool(evidence.get("entry_structure_valid")),
        "setup_family_invalidation": evidence.get("primary_invalidation_level"),
        "setup_family_target_1": evidence.get("primary_target_1"),
        "setup_family_rr_to_t1": evidence.get("primary_rr_to_t1"),
    }


# ---------------------------------------------------------------------------
# Single-ticker prefilter result
# ---------------------------------------------------------------------------

def _build_key_features(enriched: dict) -> dict:
    """Assemble key features forwarded to deterministic tiering/audit layers."""
    cp = enriched.get("current_price") or enriched.get("latest_close") or enriched.get("close")
    co = enriched.get("current_open")
    ch = enriched.get("current_high")
    cl = enriched.get("current_low")
    pc = enriched.get("previous_close")

    change_pct: float | None = None
    if cp is not None and pc is not None and pc != 0:
        try:
            change_pct = round((float(cp) - float(pc)) / float(pc) * 100, 3)
        except (TypeError, ValueError):
            pass

    bar_dir = "unknown"
    if cp is not None and co is not None:
        try:
            fcp, fco = float(cp), float(co)
            if fcp > fco:
                bar_dir = "green"
            elif fcp < fco:
                bar_dir = "red"
            else:
                bar_dir = "flat"
        except (TypeError, ValueError):
            pass

    close_loc: float | None = None
    if cp is not None and ch is not None and cl is not None:
        try:
            fcp, fch, fcl = float(cp), float(ch), float(cl)
            rng = fch - fcl
            if rng > 0:
                close_loc = round((fcp - fcl) / rng, 3)
        except (TypeError, ValueError):
            pass

    features = {
        "sma_value_alignment": enriched.get("sma_value_alignment"),
        "structure_event": enriched.get("structure_event"),
        "zone_quality": _zone_label(enriched),
        "retest_status": enriched.get("retest_status"),
        "overhead_status": enriched.get("overhead_status"),
        "estimated_rr": enriched.get("estimated_rr"),
        "volume_behavior": enriched.get("volume_behavior"),
        "price_extension_pct": enriched.get("price_extension_from_sma20_pct"),
        "current_price": cp,
        "current_open": co,
        "current_high": ch,
        "current_low": cl,
        "previous_close": pc,
        "current_change_pct": change_pct,
        "current_bar_direction": bar_dir,
        "current_close_location_pct": close_loc,
    }
    features.update(_family_key_features(enriched))
    return features


def score_ticker(enriched: dict, config: dict) -> dict:
    """Score, veto and arbitrate model admission for one enriched ticker."""
    ticker = enriched.get("ticker", "UNKNOWN")
    data_status = enriched.get("data_status", "ERROR")

    vetoes = apply_hard_vetoes(enriched, config)
    has_legacy_hard_block = bool(set(vetoes) & _HARD_BLOCK_VETOES)

    if data_status == "OK":
        score, breakdown = algo_score(enriched, config)
    else:
        score = 0
        breakdown = {k: 0 for k in [
            "trend_value_alignment", "structure_event", "fvg_ob_demand_zone_quality",
            "retest_proximity_status", "target_path_rr_estimate",
            "volume_participation", "data_quality_recency",
        ]}

    min_score = config.get("prefilter", {}).get("prefilter_min_score", 55)
    score_below_floor = score < min_score and data_status == "OK"
    legacy_eligible = not has_legacy_hard_block and not score_below_floor

    family_decision = family_admission.build_family_admission_decision(
        enriched,
        score,
        vetoes,
        config,
    )
    family_eligible = bool(family_decision.get("admitted_by_family"))
    eligible = bool(legacy_eligible or family_eligible)

    family_rank = int(family_decision.get("admission_rank_score") or score)
    admission_rank_score = max(score, family_rank) if eligible else score

    if legacy_eligible and family_eligible:
        admission_source = "legacy+family"
    elif family_eligible:
        admission_source = "family"
    elif legacy_eligible:
        admission_source = "legacy"
    else:
        admission_source = "none"

    rejection_reason: str | None = None
    if not eligible:
        if has_legacy_hard_block:
            rejection_reason = "hard_veto: " + ", ".join(vetoes)
        elif score_below_floor:
            rejection_reason = f"score_below_floor: {score} < {min_score}"
        else:
            rejection_reason = "not_admitted"

    return {
        "ticker": ticker,
        "data_status": data_status,
        "prefilter_score": score,
        "score_breakdown": breakdown,
        # Original generic evidence is retained even when family arbitration
        # explicitly supersedes a generic veto for model admission.
        "veto_flags": vetoes,
        "effective_admission_vetoes": list(family_decision.get("remaining_vetoes") or []),
        "legacy_prefilter_eligible": legacy_eligible,
        "family_admission": family_decision,
        "admission_source": admission_source,
        "admission_rank_score": admission_rank_score,
        "eligible_for_model": eligible,
        # Historical compatibility alias. Do not remove until the provider-
        # neutral scheduler/telemetry migration is separately reviewed.
        "eligible_for_claude": eligible,
        "rejection_reason": rejection_reason,
        "ranking_reason": _ranking_summary(enriched, score, vetoes, family_decision),
        "key_features": _build_key_features(enriched),
    }


def _zone_label(enriched: dict) -> str:
    fvg = enriched.get("fvg")
    ob = enriched.get("ob")
    if fvg and ob:
        return "FVG+OB"
    if fvg:
        return "FVG"
    if ob:
        return "OB"
    return "none"


def _ranking_summary(
    enriched: dict,
    score: int,
    vetoes: list,
    family_decision: dict | None = None,
) -> str:
    fd = family_decision if isinstance(family_decision, dict) else {}
    family = fd.get("primary_family")
    family_part = ""
    if family and family != "NONE":
        family_part = (
            f" family={family}:{fd.get('primary_state', 'UNKNOWN')}"
            f" fscore={fd.get('family_score', 0)}"
        )

    if vetoes:
        rescued = fd.get("rescued_vetoes") or []
        rescued_part = f" rescued=[{', '.join(rescued)}]" if rescued else ""
        return f"score={score} vetoed=[{', '.join(vetoes[:3])}]{rescued_part}{family_part}"

    event = enriched.get("structure_event", "none")
    retest = enriched.get("retest_status", "missing")
    rr = enriched.get("estimated_rr")
    rr_str = f"RR={rr:.1f}" if rr else "RR=?"
    return f"score={score} event={event} retest={retest} {rr_str}{family_part}"


# ---------------------------------------------------------------------------
# Board-level prefilter
# ---------------------------------------------------------------------------

def prefilter(enriched_list: list, config: dict) -> dict:
    """Score, arbitrate, rank and cap the full ticker board.

    ``model_candidates`` is the canonical SFC-2B name. ``claude_candidates``
    is an exact compatibility alias until historical scheduler/telemetry names
    are migrated separately.
    """
    max_candidates = config.get("prefilter", {}).get("max_claude_candidates_per_scan", 30)
    min_score = config.get("prefilter", {}).get("prefilter_min_score", 55)

    all_results: list[dict] = []
    rejected_data = 0
    rejected_veto = 0
    above_floor = 0
    family_admitted = 0

    for enriched in enriched_list:
        result = score_ticker(enriched, config)
        all_results.append(result)

        status = result["data_status"]
        if status != "OK":
            rejected_data += 1
            continue

        if result["prefilter_score"] >= min_score:
            above_floor += 1

        if result.get("admission_source") in ("family", "legacy+family"):
            family_admitted += 1

        if not result["eligible_for_model"]:
            rejected_veto += 1

    eligible = [r for r in all_results if r["eligible_for_model"]]
    ranked = sorted(
        eligible,
        key=lambda r: (
            int(r.get("admission_rank_score") or 0),
            int(r.get("prefilter_score") or 0),
            str(r.get("ticker") or ""),
        ),
        reverse=True,
    )
    candidates = ranked[:max_candidates]

    top_10 = [
        {
            "ticker": r["ticker"],
            "score": r["prefilter_score"],
            "admission_rank_score": r.get("admission_rank_score", r["prefilter_score"]),
            "admission_source": r.get("admission_source", "legacy"),
        }
        for r in ranked[:10]
    ]

    board_summary = {
        "total_tickers_input": len(enriched_list),
        "total_evaluated": len(all_results),
        "total_rejected_by_data_quality": rejected_data,
        "total_rejected_by_veto": rejected_veto,
        "total_above_prefilter_min_score": above_floor,
        "total_family_admitted": family_admitted,
        "total_model_candidates": len(candidates),
        # Historical compatibility field.
        "total_claude_candidates": len(candidates),
        "top_10_tickers_by_score": top_10,
    }

    log.info(
        "Prefilter complete: %d input -> %d eligible -> %d GPT-5.6 candidates (family_admitted=%d)",
        len(enriched_list),
        len(eligible),
        len(candidates),
        family_admitted,
    )

    return {
        "all_results": all_results,
        "ranked_results": ranked,
        "model_candidates": candidates,
        # Historical compatibility alias.
        "claude_candidates": candidates,
        "board_summary": board_summary,
    }

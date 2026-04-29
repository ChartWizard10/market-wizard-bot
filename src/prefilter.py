"""Algorithmic prefilter scorer.

Scans the full ticker universe using Phase 2 features, scores 0–100,
applies pre-Claude hard vetoes, ranks candidates, and caps the list.

This is NOT the final trade grader. It does NOT call Claude. It does NOT
assign tiers. Its only job is to decide which tickers are worth Claude's time.

No rsi, macd, bollinger_bands, or stochastic. Ever.
"""

import logging
from typing import Any

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

# Vetoes that unconditionally block Claude eligibility
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
    # hostile or unavailable
    return 0


def _score_structure_event(enriched: dict, weight: int) -> int:
    event = enriched.get("structure_event", "none")
    wick_only = enriched.get("wick_only_break", False)

    if event == "MSS":
        return weight                        # sweep + structure shift = highest
    if event in ("BOS", "failed_breakdown_reclaim", "accepted_break"):
        return round(weight * 0.90)
    if event == "reclaim":
        return round(weight * 0.75)
    if event == "CHOCH":
        return round(weight * 0.40)          # modest only — not a bullish full signal
    if wick_only:
        return round(weight * 0.15)          # flagged noise, not rewarded
    return 0                                 # none


def _score_zone_quality(enriched: dict, weight: int) -> int:
    fvg = enriched.get("fvg")
    ob = enriched.get("ob")
    score = 0

    if fvg and ob:
        score = weight                       # both present — strongest confluence
    elif fvg or ob:
        score = round(weight * 0.67)         # one present — decent

    # Bonus: price is actively inside the zone
    in_zone = (fvg and fvg.get("price_in_fvg")) or (ob and ob.get("price_at_ob"))
    if in_zone and score > 0:
        bonus = round(weight * 0.20)
        score = min(weight, score + bonus)

    return score


def _score_retest(enriched: dict, weight: int) -> int:
    status = enriched.get("retest_status", "missing")
    if status == "confirmed":
        return weight
    if status == "partial":
        return round(weight * 0.60)
    if status == "missing":
        return round(weight * 0.20)
    return 0                                 # failed


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
        return round(weight * 0.50)          # no RR computable but path is clear

    if overhead == "moderate":
        if rr_strong:
            return round(weight * 0.67)
        if rr_weak:
            return round(weight * 0.40)
        return round(weight * 0.30)

    # unknown overhead
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
        return round(weight * 0.80)          # dry-up on retest is constructive
    if behavior == "neutral":
        return round(weight * 0.50)
    return round(weight * 0.20)              # unknown


def _score_data_quality(enriched: dict, weight: int) -> int:
    status = enriched.get("data_status", "ERROR")
    if status == "OK":
        return weight
    if status == "STALE":
        return round(weight * 0.40)
    if status == "INSUFFICIENT":
        return round(weight * 0.20)
    return 0                                 # EMPTY / ERROR


# ---------------------------------------------------------------------------
# Scoring entry point
# ---------------------------------------------------------------------------

def algo_score(enriched: dict, config: dict) -> tuple[int, dict]:
    """Score a single enriched ticker 0–100. Returns (total, breakdown)."""
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

    total = s_trend + s_struct + s_zone + s_retest + s_rr + s_vol + s_data
    total = max(0, min(100, total))

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
    """Return list of active veto flags for this ticker.

    A veto does not silently drop the ticker — it is recorded so
    summary stats can explain why it was rejected.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    max_extension = thresholds.get("max_price_extension_from_sma20_pct", 8)
    min_rr = config.get("tiers", {}).get("snipe_it", {}).get("min_rr", 3.0)

    vetoes: list[str] = []
    status = enriched.get("data_status", "ERROR")

    # --- Data quality vetoes ---
    if status == "EMPTY":
        vetoes.append(VETO_DATA_EMPTY)
        return vetoes                        # no features to check further
    if status == "ERROR":
        vetoes.append(VETO_DATA_ERROR)
        return vetoes
    if status == "INSUFFICIENT":
        vetoes.append(VETO_INSUFFICIENT_BARS)
        return vetoes
    if status == "STALE":
        vetoes.append(VETO_STALE_DATA)
        return vetoes

    # --- Structure vetoes ---
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

    # --- Overhead ---
    if enriched.get("overhead_status") == "blocked":
        vetoes.append(VETO_OVERHEAD_BLOCKED)

    # --- Price extension ---
    ext = enriched.get("price_extension_from_sma20_pct")
    if ext is not None and ext > max_extension:
        vetoes.append(VETO_PRICE_TOO_EXTENDED)

    # --- Retest ---
    if enriched.get("retest_status") == "failed":
        vetoes.append(VETO_RETEST_FAILED)

    # --- Value alignment ---
    if enriched.get("sma_value_alignment") == "hostile":
        vetoes.append(VETO_HOSTILE_ALIGNMENT)

    # --- R:R ---
    rr = enriched.get("estimated_rr")
    if rr is not None and rr < min_rr:
        vetoes.append(VETO_RR_BELOW_THRESHOLD)

    # --- Mid-range / no edge ---
    # Trigger when: no structure, no zone, score would be near zero
    if (
        not has_structure
        and not has_zone
        and enriched.get("retest_status") in ("missing", "failed")
    ):
        if VETO_MID_RANGE_NO_EDGE not in vetoes:
            vetoes.append(VETO_MID_RANGE_NO_EDGE)

    return vetoes


# ---------------------------------------------------------------------------
# Single-ticker prefilter result
# ---------------------------------------------------------------------------

def _build_key_features(enriched: dict) -> dict:
    """Assemble key_features dict forwarded to tiering. Includes current OHLC acceptance data."""
    cp = (
        enriched.get("current_price")
        or enriched.get("latest_close")
        or enriched.get("close")
    )
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

    return {
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


def score_ticker(enriched: dict, config: dict) -> dict:
    """Score and veto a single ticker. Returns full prefilter result dict.

    enriched must include data_status and (if OK) all feature fields from
    indicators.enrich(). Rejected tickers preserve veto_flags and
    rejection_reason for summary stats.
    """
    ticker = enriched.get("ticker", "UNKNOWN")
    data_status = enriched.get("data_status", "ERROR")

    vetoes = apply_hard_vetoes(enriched, config)
    has_hard_block = bool(set(vetoes) & _HARD_BLOCK_VETOES)

    # Always compute score even for vetoed tickers (for transparency)
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
    eligible = not has_hard_block and not score_below_floor

    rejection_reason: str | None = None
    if has_hard_block:
        rejection_reason = "hard_veto: " + ", ".join(vetoes)
    elif score_below_floor:
        rejection_reason = f"score_below_floor: {score} < {min_score}"

    return {
        "ticker": ticker,
        "data_status": data_status,
        "prefilter_score": score,
        "score_breakdown": breakdown,
        "veto_flags": vetoes,
        "eligible_for_claude": eligible,
        "rejection_reason": rejection_reason,
        "ranking_reason": _ranking_summary(enriched, score, vetoes),
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


def _ranking_summary(enriched: dict, score: int, vetoes: list) -> str:
    if vetoes:
        return f"score={score} vetoed=[{', '.join(vetoes[:3])}]"
    event = enriched.get("structure_event", "none")
    retest = enriched.get("retest_status", "missing")
    rr = enriched.get("estimated_rr")
    rr_str = f"RR={rr:.1f}" if rr else "RR=?"
    return f"score={score} event={event} retest={retest} {rr_str}"


# ---------------------------------------------------------------------------
# Board-level prefilter
# ---------------------------------------------------------------------------

def prefilter(enriched_list: list, config: dict) -> dict:
    """Score, veto, rank, and cap the full ticker board.

    Args:
        enriched_list: list of dicts, each with data_status and (if OK)
                       all feature fields from indicators.enrich().
        config:        loaded doctrine_config.yaml dict.

    Returns:
        all_results:                 every ticker result (eligible + rejected)
        ranked_results:              eligible tickers sorted by score desc
        claude_candidates:           top N eligible by score, capped per config
        board_summary:               aggregate stats
    """
    max_candidates = config.get("prefilter", {}).get("max_claude_candidates_per_scan", 30)
    min_score = config.get("prefilter", {}).get("prefilter_min_score", 55)

    all_results: list[dict] = []
    rejected_data: int = 0
    rejected_veto: int = 0
    above_floor: int = 0

    for enriched in enriched_list:
        result = score_ticker(enriched, config)
        all_results.append(result)

        status = result["data_status"]
        if status != "OK":
            rejected_data += 1
        elif result["veto_flags"] and set(result["veto_flags"]) & _HARD_BLOCK_VETOES:
            rejected_veto += 1
        elif result["prefilter_score"] >= min_score:
            above_floor += 1
        else:
            rejected_veto += 1              # score below floor counts as rejected

    eligible = [r for r in all_results if r["eligible_for_claude"]]
    ranked = sorted(eligible, key=lambda r: r["prefilter_score"], reverse=True)
    candidates = ranked[:max_candidates]

    top_10 = [
        {"ticker": r["ticker"], "score": r["prefilter_score"]}
        for r in ranked[:10]
    ]

    board_summary = {
        "total_tickers_input": len(enriched_list),
        "total_evaluated": len(all_results),
        "total_rejected_by_data_quality": rejected_data,
        "total_rejected_by_veto": rejected_veto,
        "total_above_prefilter_min_score": above_floor,
        "total_claude_candidates": len(candidates),
        "top_10_tickers_by_score": top_10,
    }

    log.info(
        "Prefilter complete: %d input → %d eligible → %d claude_candidates",
        len(enriched_list), len(eligible), len(candidates),
    )

    return {
        "all_results": all_results,
        "ranked_results": ranked,
        "claude_candidates": candidates,
        "board_summary": board_summary,
    }

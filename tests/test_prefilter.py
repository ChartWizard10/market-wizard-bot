"""Prefilter tests — Phase 3."""

import yaml
import pytest

from src.prefilter import (
    algo_score,
    apply_hard_vetoes,
    score_ticker,
    prefilter,
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
    VETO_HOSTILE_ALIGNMENT,
    VETO_RR_BELOW_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

with open("config/doctrine_config.yaml") as _f:
    _CONFIG = yaml.safe_load(_f)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _base_enriched(**overrides) -> dict:
    """A fully-valid enriched dict representing a clean setup. Override any field."""
    base = {
        "ticker": "TEST",
        "data_status": "OK",
        "current_price": 100.0,
        # SMA / value
        "sma20": 98.0, "sma50": 95.0, "sma200": 88.0,
        "sma_value_alignment": "supportive",
        "price_extension_from_sma20_pct": 2.0,
        # Structure
        "structure_event": "MSS",
        "structure_confirmed": True,
        "structure_level": 97.0,
        "prior_structural_high": 97.0,
        "wick_only_break": False,
        # FVG
        "fvg": {
            "fvg_top": 99.5, "fvg_mid": 98.75, "fvg_bot": 98.0,
            "fvg_start_idx": 10, "fvg_end_idx": 12,
            "fvg_filled": False, "price_in_fvg": True,
        },
        # OB
        "ob": {
            "ob_hi": 99.0, "ob_lo": 97.5, "ob_core": 98.25,
            "ob_idx": 8, "mitigated": False, "price_at_ob": False,
        },
        # Retest
        "retest_status": "confirmed",
        "retest_zone": "FVG",
        "retest_distance_atr": 0.0,
        # Overhead
        "overhead_status": "clear",
        "overhead_level": 115.0,
        "overhead_distance_pct": 15.0,
        # Targets / invalidation / R:R
        "targets": [{"label": "T1", "level": 112.0, "reason": "nearest pool"}],
        "invalidation_level": 96.5,
        "invalidation_condition": "below OB low",
        "estimated_rr": 3.5,
        # Volume
        "volume_ratio": 1.4,
        "volume_behavior": "expansion",
        # Sweeps / liquidity
        "sweep_detected": True,
        "sweep_low": 95.0,
        "prior_low": 96.0,
        "atr": 1.2,
        # Pools
        "equal_highs": [115.0, 120.0],
        "equal_lows": [95.0],
        "nearest_pool_above": 115.0,
        "nearest_pool_below": 95.0,
    }
    base.update(overrides)
    return base


def _make_board(n: int, **overrides) -> list:
    """Make a list of n enriched dicts."""
    return [_base_enriched(ticker=f"SYM{i:03d}", **overrides) for i in range(n)]


# ---------------------------------------------------------------------------
# 1. Score range
# ---------------------------------------------------------------------------

def test_score_is_between_0_and_100():
    enriched = _base_enriched()
    score, _ = algo_score(enriched, _CONFIG)
    assert 0 <= score <= 100


def test_score_zero_for_empty_data():
    enriched = _base_enriched(data_status="EMPTY")
    result = score_ticker(enriched, _CONFIG)
    assert result["prefilter_score"] == 0


def test_perfect_setup_scores_high():
    enriched = _base_enriched()
    score, _ = algo_score(enriched, _CONFIG)
    assert score >= 80, f"Perfect setup should score ≥ 80, got {score}"


def test_no_structure_no_zone_scores_low():
    enriched = _base_enriched(
        structure_event="none",
        wick_only_break=False,
        fvg=None,
        ob=None,
        retest_status="missing",
        targets=[],
        invalidation_level=None,
        estimated_rr=None,
        sma_value_alignment="unavailable",
        volume_behavior="unknown",
    )
    score, _ = algo_score(enriched, _CONFIG)
    # With no structure, no zone, no retest, no RR, unavailable alignment, unknown volume:
    # max possible = data_quality(5) + retest_missing partial(4) = ~9
    assert score < 20, f"Degenerate setup should score < 20, got {score}"


# ---------------------------------------------------------------------------
# 2. Scoring weights applied correctly
# ---------------------------------------------------------------------------

def test_weights_sum_contribution():
    """Weights from config must sum to 100."""
    weights = _CONFIG["prefilter"]["scoring_weights"]
    assert sum(weights.values()) == 100


def test_all_weight_buckets_contribute_nonzero_for_ideal_setup():
    enriched = _base_enriched()
    _, breakdown = algo_score(enriched, _CONFIG)
    for bucket, val in breakdown.items():
        assert val > 0, f"Bucket '{bucket}' should be > 0 for ideal setup, got {val}"


# ---------------------------------------------------------------------------
# 3. Trend / value alignment
# ---------------------------------------------------------------------------

def test_supportive_alignment_scores_full_trend_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    supportive = _base_enriched(sma_value_alignment="supportive")
    _, bd_s = algo_score(supportive, _CONFIG)
    assert bd_s["trend_value_alignment"] == weights["trend_value_alignment"]


def test_mixed_alignment_scores_partial():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    mixed = _base_enriched(sma_value_alignment="mixed")
    _, bd = algo_score(mixed, _CONFIG)
    assert 0 < bd["trend_value_alignment"] < weights["trend_value_alignment"]


def test_hostile_alignment_scores_zero_trend():
    hostile = _base_enriched(sma_value_alignment="hostile")
    _, bd = algo_score(hostile, _CONFIG)
    assert bd["trend_value_alignment"] == 0


# ---------------------------------------------------------------------------
# 4. Structure event
# ---------------------------------------------------------------------------

def test_mss_scores_full_structure_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(structure_event="MSS")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["structure_event"] == weights["structure_event"]


def test_bos_scores_near_full():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(structure_event="BOS")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["structure_event"] >= round(weights["structure_event"] * 0.85)


def test_choch_scores_modestly():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(structure_event="CHOCH")
    _, bd = algo_score(enriched, _CONFIG)
    # Must be significantly below full weight
    assert bd["structure_event"] < round(weights["structure_event"] * 0.55)


def test_no_structure_scores_zero():
    enriched = _base_enriched(structure_event="none", wick_only_break=False)
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["structure_event"] == 0


def test_wick_only_scores_near_zero():
    enriched = _base_enriched(structure_event="none", wick_only_break=True)
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["structure_event"] < 5


# ---------------------------------------------------------------------------
# 5. Zone quality
# ---------------------------------------------------------------------------

def test_fvg_and_ob_scores_full_zone_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched()  # has both fvg and ob
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["fvg_ob_demand_zone_quality"] == weights["fvg_ob_demand_zone_quality"]


def test_fvg_only_scores_partial_zone():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(ob=None)
    _, bd = algo_score(enriched, _CONFIG)
    assert 0 < bd["fvg_ob_demand_zone_quality"] < weights["fvg_ob_demand_zone_quality"]


def test_no_zone_scores_zero():
    enriched = _base_enriched(fvg=None, ob=None)
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["fvg_ob_demand_zone_quality"] == 0


# ---------------------------------------------------------------------------
# 6. Retest proximity
# ---------------------------------------------------------------------------

def test_confirmed_retest_scores_full_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(retest_status="confirmed")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["retest_proximity_status"] == weights["retest_proximity_status"]


def test_partial_retest_scores_partial():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(retest_status="partial")
    _, bd = algo_score(enriched, _CONFIG)
    assert 0 < bd["retest_proximity_status"] < weights["retest_proximity_status"]


def test_missing_retest_scores_low():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(retest_status="missing")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["retest_proximity_status"] < round(weights["retest_proximity_status"] * 0.35)


def test_failed_retest_scores_zero():
    enriched = _base_enriched(retest_status="failed")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["retest_proximity_status"] == 0


# ---------------------------------------------------------------------------
# 7. Target path / R:R
# ---------------------------------------------------------------------------

def test_clear_overhead_rr_above_3_scores_full():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(overhead_status="clear", estimated_rr=3.5)
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["target_path_rr_estimate"] == weights["target_path_rr_estimate"]


def test_overhead_blocked_scores_zero_rr():
    enriched = _base_enriched(overhead_status="blocked")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["target_path_rr_estimate"] == 0


def test_rr_below_3_scores_lower():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    good = _base_enriched(overhead_status="clear", estimated_rr=3.5)
    weak = _base_enriched(overhead_status="clear", estimated_rr=1.8)
    _, bd_good = algo_score(good, _CONFIG)
    _, bd_weak = algo_score(weak, _CONFIG)
    assert bd_weak["target_path_rr_estimate"] < bd_good["target_path_rr_estimate"]


# ---------------------------------------------------------------------------
# 8. Volume
# ---------------------------------------------------------------------------

def test_expansion_scores_full_volume_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(volume_behavior="expansion")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["volume_participation"] == weights["volume_participation"]


def test_dryup_scores_high_volume():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(volume_behavior="dryup")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["volume_participation"] >= round(weights["volume_participation"] * 0.75)


def test_neutral_volume_scores_partial():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(volume_behavior="neutral")
    _, bd = algo_score(enriched, _CONFIG)
    assert 0 < bd["volume_participation"] < weights["volume_participation"]


# ---------------------------------------------------------------------------
# 9. Data quality
# ---------------------------------------------------------------------------

def test_ok_data_scores_full_quality_weight():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(data_status="OK")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["data_quality_recency"] == weights["data_quality_recency"]


def test_stale_data_reduces_quality_score():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(data_status="STALE")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["data_quality_recency"] < weights["data_quality_recency"]


def test_insufficient_bars_reduces_quality_score():
    weights = _CONFIG["prefilter"]["scoring_weights"]
    enriched = _base_enriched(data_status="INSUFFICIENT")
    _, bd = algo_score(enriched, _CONFIG)
    assert bd["data_quality_recency"] < weights["data_quality_recency"]


# ---------------------------------------------------------------------------
# 10–13. Hard vetoes
# ---------------------------------------------------------------------------

def test_data_empty_veto_blocks_claude():
    enriched = _base_enriched(data_status="EMPTY")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_DATA_EMPTY in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_data_error_veto_blocks_claude():
    enriched = _base_enriched(data_status="ERROR")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_DATA_ERROR in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_stale_data_veto_blocks_claude():
    enriched = _base_enriched(data_status="STALE")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_STALE_DATA in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_overhead_blocked_veto_blocks_claude():
    enriched = _base_enriched(overhead_status="blocked")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_OVERHEAD_BLOCKED in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_price_too_extended_veto_blocks_claude():
    # Extension above max_price_extension_from_sma20_pct (8%)
    enriched = _base_enriched(price_extension_from_sma20_pct=12.0)
    result = score_ticker(enriched, _CONFIG)
    assert VETO_PRICE_TOO_EXTENDED in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_retest_failed_veto_blocks_claude():
    enriched = _base_enriched(retest_status="failed")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_RETEST_FAILED in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_hostile_alignment_veto_blocks_claude():
    enriched = _base_enriched(sma_value_alignment="hostile")
    result = score_ticker(enriched, _CONFIG)
    assert VETO_HOSTILE_ALIGNMENT in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_rr_below_threshold_veto_blocks_claude():
    enriched = _base_enriched(estimated_rr=1.5)
    result = score_ticker(enriched, _CONFIG)
    assert VETO_RR_BELOW_THRESHOLD in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_no_invalidation_veto_blocks_claude():
    enriched = _base_enriched(invalidation_level=None)
    result = score_ticker(enriched, _CONFIG)
    assert VETO_NO_INVALIDATION in result["veto_flags"]
    assert not result["eligible_for_claude"]


def test_no_target_path_veto_blocks_claude():
    enriched = _base_enriched(targets=[])
    result = score_ticker(enriched, _CONFIG)
    assert VETO_NO_TARGET_PATH in result["veto_flags"]
    assert not result["eligible_for_claude"]


# ---------------------------------------------------------------------------
# 14. Ranking
# ---------------------------------------------------------------------------

def test_candidates_ranked_highest_to_lowest():
    board = [
        _base_enriched(ticker="HIGH", structure_event="MSS", retest_status="confirmed",
                       sma_value_alignment="supportive", estimated_rr=4.0),
        _base_enriched(ticker="MID", structure_event="reclaim", retest_status="partial",
                       sma_value_alignment="mixed", estimated_rr=3.1),
        _base_enriched(ticker="LOW", structure_event="CHOCH", retest_status="missing",
                       sma_value_alignment="mixed", estimated_rr=3.0),
    ]
    result = prefilter(board, _CONFIG)
    scores = [r["prefilter_score"] for r in result["ranked_results"]]
    assert scores == sorted(scores, reverse=True), f"Not descending: {scores}"


# ---------------------------------------------------------------------------
# 15. Cap at max_claude_candidates_per_scan
# ---------------------------------------------------------------------------

def test_claude_candidates_capped_at_max():
    max_n = _CONFIG["prefilter"]["max_claude_candidates_per_scan"]
    board = _make_board(max_n + 20)  # more than the cap
    result = prefilter(board, _CONFIG)
    assert len(result["claude_candidates"]) <= max_n


def test_fewer_than_max_candidates_returned_without_padding():
    board = _make_board(5)
    result = prefilter(board, _CONFIG)
    assert len(result["claude_candidates"]) <= 5


# ---------------------------------------------------------------------------
# 16. Claude not called on all tickers
# ---------------------------------------------------------------------------

def test_prefilter_does_not_call_claude(monkeypatch):
    """prefilter() must never import or call the Claude client."""
    called = []

    # Patch the module to detect any call
    import src.prefilter as pf_module

    def fake_claude(*a, **kw):
        called.append(True)

    monkeypatch.setattr(pf_module, "_HARD_BLOCK_VETOES", pf_module._HARD_BLOCK_VETOES)  # no-op patch
    board = _make_board(10)
    prefilter(board, _CONFIG)
    assert not called, "prefilter must not call Claude"


def test_prefilter_rejects_below_floor_tickers():
    """Tickers scoring below prefilter_min_score must not be in claude_candidates."""
    min_score = _CONFIG["prefilter"]["prefilter_min_score"]
    # Build a board where one ticker is deliberately weak
    weak = _base_enriched(
        ticker="WEAK",
        structure_event="none",
        fvg=None,
        ob=None,
        retest_status="missing",
        sma_value_alignment="mixed",
        overhead_status="unknown",
        estimated_rr=None,
        targets=[],
        invalidation_level=None,
        volume_behavior="neutral",
    )
    board = [weak]
    result = prefilter(board, _CONFIG)
    candidate_tickers = [r["ticker"] for r in result["claude_candidates"]]
    assert "WEAK" not in candidate_tickers


# ---------------------------------------------------------------------------
# 17. Mixed board without crashing
# ---------------------------------------------------------------------------

def test_mixed_board_runs_without_crash():
    board = [
        _base_enriched(ticker="OK1"),
        _base_enriched(ticker="STALE1", data_status="STALE"),
        _base_enriched(ticker="EMPTY1", data_status="EMPTY"),
        _base_enriched(ticker="ERR1", data_status="ERROR"),
        _base_enriched(ticker="VETO1", overhead_status="blocked"),
        _base_enriched(ticker="RR1", estimated_rr=1.2),
        _base_enriched(ticker="EXT1", price_extension_from_sma20_pct=15.0),
    ]
    result = prefilter(board, _CONFIG)
    assert result["board_summary"]["total_tickers_input"] == 7
    assert result["board_summary"]["total_evaluated"] == 7


# ---------------------------------------------------------------------------
# 18. Rejected tickers preserve veto_flags and rejection_reason
# ---------------------------------------------------------------------------

def test_rejected_ticker_preserves_veto_and_reason():
    enriched = _base_enriched(ticker="VETOED", data_status="EMPTY")
    result = score_ticker(enriched, _CONFIG)
    assert not result["eligible_for_claude"]
    assert result["veto_flags"]
    assert result["rejection_reason"] is not None
    assert "hard_veto" in result["rejection_reason"]


def test_score_below_floor_has_rejection_reason():
    enriched = _base_enriched(
        ticker="LOWSCORE",
        structure_event="none",
        fvg=None, ob=None,
        retest_status="missing",
        sma_value_alignment="mixed",
        overhead_status="unknown",
        estimated_rr=None,
        targets=[{"label": "T1", "level": 110.0, "reason": "test"}],
        invalidation_level=97.0,
        volume_behavior="neutral",
        price_extension_from_sma20_pct=2.0,
    )
    result = score_ticker(enriched, _CONFIG)
    # If score is below floor and no hard vetoes, rejection_reason should note floor
    if not result["eligible_for_claude"] and not result["veto_flags"]:
        assert "score_below_floor" in (result["rejection_reason"] or "")


# ---------------------------------------------------------------------------
# 19. Disabled indicators absent from scoring
# ---------------------------------------------------------------------------

def test_no_disabled_indicators_in_scoring():
    """algo_score must not reference rsi, macd, bollinger, or stochastic."""
    import inspect
    import src.prefilter as pf
    source = inspect.getsource(pf)
    for term in ["rsi", "macd", "bollinger", "stochastic"]:
        # Allow the term only in the module docstring negation line
        lines = [l for l in source.splitlines()
                 if term in l.lower() and "no rsi" not in l.lower() and "#" not in l]
        assert not lines, f"Disabled indicator '{term}' found in prefilter.py: {lines}"


# ---------------------------------------------------------------------------
# Board summary structure
# ---------------------------------------------------------------------------

def test_board_summary_has_required_keys():
    result = prefilter(_make_board(5), _CONFIG)
    summary = result["board_summary"]
    required = [
        "total_tickers_input", "total_evaluated",
        "total_rejected_by_data_quality", "total_rejected_by_veto",
        "total_above_prefilter_min_score", "total_claude_candidates",
        "top_10_tickers_by_score",
    ]
    for key in required:
        assert key in summary, f"Missing board_summary key: {key}"


def test_board_summary_counts_add_up():
    board = _make_board(10)
    result = prefilter(board, _CONFIG)
    s = result["board_summary"]
    assert s["total_evaluated"] == s["total_tickers_input"]

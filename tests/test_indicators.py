"""Indicator and disabled-indicator tests — Phase 2."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.indicators import (
    compute_smas,
    sma_value_alignment,
    compute_atr,
    compute_swings,
    detect_sweep,
    detect_structure_event,
    detect_fvg,
    detect_ob,
    assess_retest,
    assess_overhead,
    estimate_targets,
    estimate_invalidation,
    estimate_rr,
    assess_volume,
    detect_vcp,
    classify_entry_family,
    assess_retest_quality,
    assess_consumption_risk,
    assess_level_authority,
    assess_zone_freshness,
    classify_break_retest_state,
    classify_market_structure_state,
    compute_weekly_sma_alignment,
    compute_weekly_trend_state,
    compute_weekly_alignment_context,
    compute_weekly_evidence,
    compute_4h_sma_alignment,
    compute_4h_reclaim_status,
    compute_4h_structure_note,
    compute_4h_data_status,
    classify_4h_market_state,
    compute_four_hour_evidence,
    enrich,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "prefilter": {
        "thresholds": {
            "swing_lookback_bars": 60,
            "recent_trigger_window_bars": 10,
            "fvg_lookback_bars": 30,
            "ob_lookback_bars": 30,
            "overhead_block_distance_pct": 3,
            "volume_expansion_ratio": 1.2,
            "volume_dryup_ratio": 0.8,
        }
    }
}


_ANCHOR = date(2025, 1, 2)  # known weekday anchor — avoids weekend boundary issues


def _make_trending_df(n: int = 300, trend: float = 0.3) -> pd.DataFrame:
    """Uptrending OHLCV with enough bars for SMA200."""
    np.random.seed(7)
    idx = pd.bdate_range(end=_ANCHOR, periods=n)
    actual = len(idx)
    closes = 100 + np.cumsum(np.random.randn(actual) * 0.5 + trend)
    df = pd.DataFrame({
        "open": closes - 0.2,
        "high": closes + 0.8,
        "low": closes - 0.8,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, actual).astype(float),
    }, index=idx)
    return df


def _make_df(n: int = 150) -> pd.DataFrame:
    """Flat-ish OHLCV for general use."""
    np.random.seed(42)
    idx = pd.bdate_range(end=_ANCHOR, periods=n)
    actual = len(idx)
    closes = 50 + np.cumsum(np.random.randn(actual) * 0.3)
    df = pd.DataFrame({
        "open": closes - 0.1,
        "high": closes + 0.5,
        "low": closes - 0.5,
        "close": closes,
        "volume": np.random.randint(500_000, 3_000_000, actual).astype(float),
    }, index=idx)
    return df


# ---------------------------------------------------------------------------
# Disabled indicator check
# ---------------------------------------------------------------------------

def test_no_rsi_in_indicators_output():
    df = _make_df(200)
    result = enrich("TEST", df, BASE_CONFIG)
    forbidden = {"rsi", "macd", "bollinger_bands", "stochastic",
                 "bollinger_upper", "bollinger_lower", "bollinger_mid"}
    found = forbidden & set(result.keys())
    assert not found, f"Disabled indicator keys found in enrich() output: {found}"


def test_no_disabled_in_prefilter_score():
    # Placeholder — will be enforced in Phase 3.
    # Verified here that enrich() output (which feeds prefilter) has no disabled keys.
    df = _make_df(200)
    result = enrich("TEST", df, BASE_CONFIG)
    for key in result:
        assert "rsi" not in key.lower()
        assert "macd" not in key.lower()
        assert "bollinger" not in key.lower()
        assert "stochastic" not in key.lower()


def test_no_disabled_in_prompt_payload():
    """build_prompt() must not include rsi, macd, bollinger, or stochastic in output."""
    from src.claude_client import build_prompt
    df = _make_df(200)
    enriched = enrich("TEST", df, BASE_CONFIG)
    enriched["latest_close"] = enriched["current_price"]
    prompt = build_prompt(enriched)
    prompt_lower = prompt.lower()
    for indicator in ("rsi", "macd", "bollinger", "stochastic"):
        assert indicator not in prompt_lower, (
            f"Disabled indicator '{indicator}' found in build_prompt() output"
        )


def test_no_disabled_in_discord_embed():
    """format_alert() embed text must not include rsi, macd, bollinger, or stochastic."""
    from src.discord_alerts import format_alert
    df = _make_df(200)
    enriched = enrich("TEST", df, BASE_CONFIG)
    enriched["latest_close"] = enriched["current_price"]
    enriched["data_status"] = "OK"

    # Build a minimal tiering_result using the enriched dict fields
    signal = {
        "ticker": "TEST", "tier": "SNIPE_IT", "score": 88,
        "setup_family": "continuation",
        "structure_event": enriched.get("structure_event", "MSS"),
        "trend_state": "fresh_expansion",
        "sma_value_alignment": enriched.get("sma_value_alignment", "supportive"),
        "zone_type": "FVG", "trigger_level": enriched["current_price"],
        "retest_status": enriched.get("retest_status", "confirmed"),
        "hold_status": "confirmed",
        "invalidation_condition": enriched.get("invalidation_condition", "below zone"),
        "invalidation_level": enriched.get("invalidation_level", 140.0),
        "targets": enriched.get("targets") or [{"label": "T1", "level": 160.0, "reason": "pool"}],
        "risk_reward": enriched.get("estimated_rr", 3.0),
        "overhead_status": enriched.get("overhead_status", "clear"),
        "forced_participation": "none", "missing_conditions": [],
        "upgrade_trigger": "none", "next_action": "Enter on retest",
        "discord_channel": "#snipe-signals", "capital_action": "full_quality_allowed",
        "reason": "MSS with confirmed retest.",
    }
    tr = {
        "final_tier": "SNIPE_IT", "score": 88, "safe_for_alert": True,
        "final_discord_channel": "#snipe-signals",
        "final_signal": signal,
    }
    text = format_alert(tr)
    text_lower = text.lower()
    for indicator in ("rsi", "macd", "bollinger", "stochastic"):
        assert indicator not in text_lower, (
            f"Disabled indicator '{indicator}' found in format_alert() output"
        )


# ---------------------------------------------------------------------------
# SMA / Value alignment
# ---------------------------------------------------------------------------

def test_sma_computed_from_full_history():
    """SMA200 requires 200 bars — must be available from 18mo data (≥250 trading days)."""
    df = _make_trending_df(300)
    smas = compute_smas(df)
    assert smas["sma20"] is not None, "SMA20 should compute with 300 bars"
    assert smas["sma50"] is not None, "SMA50 should compute with 300 bars"
    assert smas["sma200"] is not None, "SMA200 should compute with 300 bars"


def test_sma200_unavailable_with_insufficient_bars():
    df = _make_df(150)  # fewer than 200 bars
    smas = compute_smas(df)
    assert smas["sma200"] is None, "SMA200 should be None with only 150 bars"


def test_value_alignment_supportive():
    df = _make_trending_df(300, trend=0.5)
    smas = compute_smas(df)
    cur = float(df["close"].iloc[-1])
    # Force alignment: cur > s20 > s50 > s200
    alignment = sma_value_alignment(cur, smas)
    # In a strong uptrend, alignment should be supportive or mixed
    assert alignment in ("supportive", "mixed")


def test_value_alignment_hostile():
    # Build a downtrending series where cur < sma20 < sma50
    idx = pd.bdate_range(end=_ANCHOR, periods=200)
    n = len(idx)
    closes = 200 - np.arange(n) * 0.4
    df = pd.DataFrame({
        "open": closes + 0.1, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes,
        "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    smas = compute_smas(df)
    cur = float(df["close"].iloc[-1])
    alignment = sma_value_alignment(cur, smas)
    assert alignment == "hostile", f"Expected hostile, got {alignment}"


def test_value_alignment_unavailable_without_sma():
    smas = {"sma20": None, "sma50": None, "sma200": None}
    assert sma_value_alignment(100.0, smas) == "unavailable"


# ---------------------------------------------------------------------------
# Sweep detection
# ---------------------------------------------------------------------------

def _make_fixed_df(n: int) -> tuple:
    """Return (idx, n_actual) using a fixed anchor to avoid weekend boundary issues."""
    idx = pd.bdate_range(end=_ANCHOR, periods=n)
    return idx, len(idx)


def test_sweep_excludes_recent_window_from_prior_low():
    """Prior low must be computed from bars BEFORE the recent window."""
    idx, n = _make_fixed_df(120)
    closes = np.ones(n) * 100.0
    lows = np.ones(n) * 98.0
    # Set a clear prior low in the lookback zone (not in recent window)
    lows[n - 40] = 90.0   # clear prior low, outside recent window
    # Set recent low just below that prior low
    lows[n - 5] = 89.0    # inside recent window — should trigger sweep
    df = pd.DataFrame({
        "open": closes, "high": closes + 1, "low": lows,
        "close": closes, "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    result = detect_sweep(df, BASE_CONFIG)
    assert result["sweep_detected"] is True
    assert result["prior_low"] is not None


def test_sweep_not_triggered_without_low_break():
    df = _make_df(150)
    # Ensure all lows are approximately the same — no sweep
    df = df.copy()
    df["low"] = 49.0
    df["close"] = 50.0
    df["open"] = 50.0
    df["high"] = 51.0
    result = detect_sweep(df, BASE_CONFIG)
    assert result["sweep_detected"] is False


# ---------------------------------------------------------------------------
# BOS / MSS — body close required
# ---------------------------------------------------------------------------

def test_mss_requires_body_close_not_wick():
    """A wick above prior high must not be classified as a confirmed structure event."""
    idx, n = _make_fixed_df(120)
    base = 100.0
    closes = np.ones(n) * base
    highs = np.ones(n) * (base + 1)
    lows = np.ones(n) * (base - 1)
    opens = np.ones(n) * base

    highs[n - 50] = 115.0
    highs[n - 3] = 116.0
    closes[n - 3] = 100.0  # body does NOT close above prior high

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.ones(n) * 1_000_000,
    }, index=idx)

    no_sweep = {"sweep_detected": False, "sweep_low": None, "prior_low": 99.0}
    result = detect_structure_event(df, no_sweep, BASE_CONFIG)

    assert result["structure_event"] == "none", (
        f"Expected 'none' for wick-only break, got '{result['structure_event']}'"
    )
    assert result["wick_only_break"] is True


def test_bos_triggers_on_body_close():
    """Body close above prior structural high must produce BOS."""
    idx, n = _make_fixed_df(120)
    closes = np.ones(n) * 100.0
    highs = np.ones(n) * 101.0
    lows = np.ones(n) * 99.0
    opens = np.ones(n) * 100.0

    closes[n - 50] = 110.0
    highs[n - 50] = 111.0

    closes[n - 5] = 112.0
    closes[n - 4] = 113.0
    closes[n - 3] = 111.5
    highs[n - 5:] = 114.0

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.ones(n) * 1_000_000,
    }, index=idx)

    no_sweep = {"sweep_detected": False, "sweep_low": None, "prior_low": 99.0}
    result = detect_structure_event(df, no_sweep, BASE_CONFIG)
    assert result["structure_event"] in ("BOS", "reclaim"), (
        f"Expected BOS or reclaim, got '{result['structure_event']}'"
    )


# ---------------------------------------------------------------------------
# FVG detection
# ---------------------------------------------------------------------------

def test_fvg_returns_top_mid_bottom():
    """Bullish FVG must return top > mid > bot."""
    idx, n = _make_fixed_df(100)
    closes = np.ones(n) * 100.0
    opens = closes.copy()
    highs = closes + 1.0
    lows = closes - 1.0
    vols = np.ones(n) * 1_000_000.0

    i = n - 15
    highs[i] = 102.0
    lows[i + 2] = 105.0
    closes[i + 1] = 107.0
    lows[i + 3:] = 103.0

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    }, index=idx)

    result = detect_fvg(df, BASE_CONFIG)
    assert result is not None, "FVG should be detected"
    assert result["fvg_top"] > result["fvg_mid"] > result["fvg_bot"], (
        f"FVG levels out of order: top={result['fvg_top']} mid={result['fvg_mid']} bot={result['fvg_bot']}"
    )


def test_fvg_filled_excluded():
    """FVG that price has returned into must be excluded."""
    idx, n = _make_fixed_df(100)
    closes = np.ones(n) * 100.0
    highs = closes + 1.0
    lows = closes - 1.0
    opens = closes.copy()
    vols = np.ones(n) * 1_000_000.0

    i = n - 25
    highs[i] = 102.0
    lows[i + 2] = 105.0
    lows[i + 5] = 101.0  # fills the FVG

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    }, index=idx)

    result = detect_fvg(df, BASE_CONFIG)
    if result is not None:
        assert result["fvg_start_idx"] != i, "Filled FVG must not be returned"


# ---------------------------------------------------------------------------
# OB / demand zone
# ---------------------------------------------------------------------------

def test_ob_returns_clear_levels():
    """OB detection must return hi, lo, and core levels."""
    idx, n = _make_fixed_df(100)
    opens = np.ones(n) * 100.0
    closes = np.ones(n) * 100.5
    highs = np.ones(n) * 101.0
    lows = np.ones(n) * 99.5
    vols = np.ones(n) * 1_000_000.0

    i = n - 20
    opens[i] = 102.0
    closes[i] = 100.0
    opens[i + 1] = 100.5
    closes[i + 1] = 104.0
    highs[i + 1] = 104.5
    closes[i + 2:] = 103.0

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    }, index=idx)

    result = detect_ob(df, BASE_CONFIG)
    assert result is not None, "OB should be detected"
    assert result["ob_hi"] > result["ob_lo"], "OB hi must be above OB lo"
    assert result["ob_core"] is not None


def test_ob_mitigated_excluded():
    """OB where price closed back below ob_lo must be excluded."""
    idx, n = _make_fixed_df(100)
    opens = np.ones(n) * 100.0
    closes = np.ones(n) * 100.5
    highs = np.ones(n) * 101.0
    lows = np.ones(n) * 99.5
    vols = np.ones(n) * 1_000_000.0

    i = n - 30
    opens[i] = 102.0
    closes[i] = 100.0
    opens[i + 1] = 100.5
    closes[i + 1] = 104.0
    highs[i + 1] = 104.5
    closes[i + 5] = 99.0
    lows[i + 5] = 98.5

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    }, index=idx)

    result = detect_ob(df, BASE_CONFIG)
    if result is not None:
        assert result["ob_idx"] != i, "Mitigated OB must not be returned"


# ---------------------------------------------------------------------------
# Overhead path
# ---------------------------------------------------------------------------

def test_overhead_blocked_detected():
    pools = {"nearest_pool_above": 102.0, "equal_highs": [102.0], "equal_lows": []}
    result = assess_overhead(100.0, pools, 1.0, BASE_CONFIG)
    # 2% distance, block threshold is 3% → blocked
    assert result["overhead_status"] == "blocked"


def test_overhead_clear_detected():
    pools = {"nearest_pool_above": 115.0, "equal_highs": [115.0], "equal_lows": []}
    result = assess_overhead(100.0, pools, 1.0, BASE_CONFIG)
    # 15% distance → clear
    assert result["overhead_status"] == "clear"


def test_overhead_unknown_when_no_pool_above():
    pools = {"nearest_pool_above": None, "equal_highs": [], "equal_lows": []}
    result = assess_overhead(100.0, pools, 1.0, BASE_CONFIG)
    assert result["overhead_status"] == "unknown"


# ---------------------------------------------------------------------------
# R:R
# ---------------------------------------------------------------------------

def test_rr_below_3_is_detectable():
    targets = [{"label": "T1", "level": 101.0, "reason": "test"}]
    inv = {"invalidation_level": 99.5, "invalidation_condition": "below swing low"}
    # cur=100, T1=101, stop=99.5 → reward=1, risk=0.5 → RR=2.0
    rr = estimate_rr(100.0, targets, inv)
    assert rr is not None
    assert rr < 3.0, f"Expected RR < 3.0, got {rr}"


def test_rr_above_3_is_detectable():
    targets = [{"label": "T1", "level": 110.0, "reason": "test"}]
    inv = {"invalidation_level": 97.0, "invalidation_condition": "below OB low"}
    # cur=100, T1=110, stop=97 → reward=10, risk=3 → RR=3.33
    rr = estimate_rr(100.0, targets, inv)
    assert rr is not None
    assert rr >= 3.0, f"Expected RR >= 3.0, got {rr}"


def test_rr_none_when_no_targets():
    inv = {"invalidation_level": 97.0, "invalidation_condition": "below OB"}
    rr = estimate_rr(100.0, [], inv)
    assert rr is None


def test_rr_none_when_no_invalidation():
    targets = [{"label": "T1", "level": 110.0, "reason": "test"}]
    inv = {"invalidation_level": None, "invalidation_condition": "none"}
    rr = estimate_rr(100.0, targets, inv)
    assert rr is None


# ---------------------------------------------------------------------------
# Volume behavior
# ---------------------------------------------------------------------------

def test_volume_expansion_detected():
    idx, n = _make_fixed_df(50)
    closes = np.ones(n) * 100.0
    vols = np.ones(n) * 1_000_000.0
    vols[-1] = 2_500_000.0
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": vols,
    }, index=idx)
    result = assess_volume(df, BASE_CONFIG)
    assert result["volume_behavior"] == "expansion"
    assert result["volume_ratio"] >= 1.2


def test_volume_dryup_detected():
    idx, n = _make_fixed_df(50)
    closes = np.ones(n) * 100.0
    vols = np.ones(n) * 1_000_000.0
    vols[-1] = 500_000.0
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": vols,
    }, index=idx)
    result = assess_volume(df, BASE_CONFIG)
    assert result["volume_behavior"] == "dryup"
    assert result["volume_ratio"] <= 0.8


# ---------------------------------------------------------------------------
# enrich() integration
# ---------------------------------------------------------------------------

def test_enrich_returns_required_keys():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    required = [
        "ticker", "current_price", "sma20", "sma50", "sma200",
        "sma_value_alignment", "structure_event", "structure_confirmed",
        "sweep_detected", "fvg", "ob", "retest_status", "overhead_status",
        "targets", "invalidation_level", "invalidation_condition",
        "estimated_rr", "volume_ratio", "volume_behavior", "atr",
    ]
    for key in required:
        assert key in result, f"Missing key in enrich() output: {key}"


def test_enrich_no_disabled_indicators():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    for key in result:
        assert "rsi" not in key.lower()
        assert "macd" not in key.lower()
        assert "bollinger" not in key.lower()
        assert "stochastic" not in key.lower()


# ---------------------------------------------------------------------------
# Phase 1B — VCP (Volatility Contraction Pattern) detection
# ---------------------------------------------------------------------------
# Evidence-capture engine. Tests verify deterministic classification of:
#   CONFIRMED / FORMING / ABSENT / INVALID / UNKNOWN
# plus correct measurement of advance, contractions, volume dry-up, pivot,
# MA alignment, and failure flag. None of these fields drive any tier gate,
# scoring, calibration, routing, capital, or alert decision in the scanner —
# but detection accuracy still matters because future backtesting depends
# on these labels being trustworthy.


_VCP_FIELDS = (
    "vcp_status",
    "vcp_prior_advance_pct",
    "vcp_contractions_count",
    "vcp_range_contraction",
    "vcp_contraction_sequence",
    "vcp_volume_dryup",
    "vcp_volume_ratio",
    "vcp_ma_alignment",
    "vcp_pivot_level",
    "vcp_failure_flag",
)


def _build_vcp_df(closes, volumes=None) -> pd.DataFrame:
    """Build OHLCV DataFrame from a closes array. high/low offset by 0.5%."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range(end=_ANCHOR, periods=n)
    actual = len(idx)
    closes = closes[-actual:]
    if volumes is None:
        volumes = np.full(actual, 1_000_000.0)
    else:
        volumes = np.asarray(volumes, dtype=float)[-actual:]
    return pd.DataFrame({
        "open":   closes * 0.997,
        "high":   closes * 1.005,
        "low":    closes * 0.995,
        "close":  closes,
        "volume": volumes,
    }, index=idx)


def _construct_vcp_closes(
    advance_low: float = 50.0,
    pivot: float = 100.0,
    contractions: list[float] | None = None,
    advance_bars: int = 60,
    consol_segment_bars: int = 8,
    pre_advance_bars: int = 70,
) -> np.ndarray:
    """Construct a synthetic price path: pre-advance → advance → contractions.

    contractions: list of pullback depths (%) e.g. [12, 7, 4] for tightening.
    """
    contractions = contractions or []
    pre = np.full(pre_advance_bars, advance_low)
    advance = np.linspace(advance_low, pivot, advance_bars)
    segments = [pre, advance]
    last_high = pivot
    for depth_pct in contractions:
        low = last_high * (1 - depth_pct / 100)
        # half-segment down to low, half back up to a slightly lower high
        down = np.linspace(last_high, low, consol_segment_bars)
        next_high = last_high * 0.998   # marginal lower high to test tightening
        up = np.linspace(low, next_high, consol_segment_bars)
        segments.extend([down, up])
        last_high = next_high
    return np.concatenate(segments)


def test_vcp_unknown_when_insufficient_bars():
    # 30 bars is below _VCP_MIN_BARS (60)
    df = _make_df(30)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    assert result["vcp_status"] == "UNKNOWN"
    assert result["vcp_prior_advance_pct"] is None
    assert result["vcp_contractions_count"] == 0


def test_vcp_unknown_when_few_swings():
    # Constant prices → no swing detection → UNKNOWN
    closes = np.full(120, 50.0)
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    assert result["vcp_status"] in ("UNKNOWN", "ABSENT")


def test_vcp_confirmed_three_tightening_contractions():
    # 100% prior advance, 3 tightening pullbacks (12 → 7 → 4), volume dry-up
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[12.0, 7.0, 4.0],
    )
    n = len(closes)
    # Advance-phase volume high, recent volume low (dry-up)
    vols = np.full(n, 2_000_000.0)
    vols[-10:] = 500_000.0
    df = _build_vcp_df(closes, vols)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)

    assert result["vcp_status"] == "CONFIRMED", (
        f"Expected CONFIRMED, got {result['vcp_status']}; result={result}"
    )
    assert result["vcp_prior_advance_pct"] is not None
    assert result["vcp_prior_advance_pct"] >= 25.0
    assert 2 <= result["vcp_contractions_count"] <= 4
    assert result["vcp_range_contraction"] is True
    assert result["vcp_volume_dryup"] is True
    assert result["vcp_failure_flag"] is False
    assert result["vcp_pivot_level"] is not None
    # Contraction sequence should be tightening
    seq = result["vcp_contraction_sequence"]
    assert len(seq) >= 2
    assert all(seq[i] < seq[i - 1] for i in range(1, len(seq)))


def test_vcp_absent_when_no_prior_advance():
    # Sideways from start — no meaningful advance
    closes = np.full(150, 100.0)
    # Add small noise so swings are detected
    closes = closes + np.sin(np.linspace(0, 20, 150)) * 0.5
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    assert result["vcp_status"] in ("ABSENT", "UNKNOWN")
    assert not result["vcp_range_contraction"]


def test_vcp_invalid_when_breakdown_after_contractions():
    # Same construction as confirmed VCP, then a hard drop at the end
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[12.0, 7.0, 4.0],
    )
    # Append a sharp breakdown — 10% drop in the last 5 bars
    breakdown = np.linspace(closes[-1], closes[-1] * 0.85, 6)[1:]
    closes = np.concatenate([closes, breakdown])
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    # If contractions are detected, breakdown must register as INVALID.
    if result["vcp_contractions_count"] >= 1:
        assert result["vcp_failure_flag"] is True or result["vcp_status"] == "INVALID", (
            f"Expected failure flag or INVALID after breakdown; result={result}"
        )


def test_vcp_volume_dryup_detection():
    # Same advance, with vs. without dry-up
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[12.0, 7.0, 4.0],
    )
    n = len(closes)
    # Variant A: volume is elevated in recent window — NOT dry-up
    vols_no_dryup = np.full(n, 1_000_000.0)
    vols_no_dryup[-10:] = 1_200_000.0
    df_a = _build_vcp_df(closes, vols_no_dryup)
    smas_a = compute_smas(df_a)
    swings_a = compute_swings(df_a, 60)
    result_a = detect_vcp(df_a, swings_a, smas_a, BASE_CONFIG)
    assert result_a["vcp_volume_dryup"] is False

    # Variant B: volume contracts heavily in recent window — IS dry-up
    vols_dryup = np.full(n, 2_000_000.0)
    vols_dryup[-10:] = 400_000.0
    df_b = _build_vcp_df(closes, vols_dryup)
    smas_b = compute_smas(df_b)
    swings_b = compute_swings(df_b, 60)
    result_b = detect_vcp(df_b, swings_b, smas_b, BASE_CONFIG)
    assert result_b["vcp_volume_dryup"] is True
    assert result_b["vcp_volume_ratio"] is not None
    assert result_b["vcp_volume_ratio"] < 0.85


def test_vcp_contraction_sequence_recorded():
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[15.0, 9.0, 5.0],
    )
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    assert isinstance(result["vcp_contraction_sequence"], list)
    if result["vcp_contractions_count"] >= 1:
        assert all(isinstance(x, (int, float)) for x in result["vcp_contraction_sequence"])


def test_vcp_pivot_identification_matches_consolidation_top():
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[12.0, 7.0, 4.0],
    )
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    if result["vcp_pivot_level"] is not None:
        # Pivot should be near the constructed top of 100 (within consolidation noise)
        assert 95.0 <= result["vcp_pivot_level"] <= 105.0


def test_vcp_fields_present_in_enrich_output():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    for key in _VCP_FIELDS:
        assert key in result, f"VCP field missing from enrich() output: {key}"


def test_vcp_ma_alignment_uppercase_labels():
    closes = _construct_vcp_closes(
        advance_low=50.0, pivot=100.0,
        contractions=[12.0, 7.0, 4.0],
    )
    df = _build_vcp_df(closes)
    swings = compute_swings(df, 60)
    smas = compute_smas(df)
    result = detect_vcp(df, swings, smas, BASE_CONFIG)
    assert result["vcp_ma_alignment"] in {"SUPPORTIVE", "MIXED", "HOSTILE", "UNKNOWN"}


# ===========================================================================
# Phase 1C-P1 — Break & Retest doctrine organs (evidence-only)
# ===========================================================================

_BRT_FIELDS = (
    "entry_family",
    "retest_quality",
    "consumption_risk",
    "level_authority",
    "zone_freshness",
    "break_retest_state",
    "one_hour_momentum_repair",
)


def _zone_touch_df(n, z_lo, z_hi, touch_bars, last_close=None):
    """Build OHLCV df where bars sit above [z_lo, z_hi] except touch_bars (indices),
    which dip into the zone band. last_close overrides the final bar's close.
    """
    idx = pd.bdate_range(end=_ANCHOR, periods=n)
    n = len(idx)
    highs, lows, closes = [], [], []
    for i in range(n):
        if i in touch_bars:
            highs.append(z_hi + 1.0)
            lows.append(z_lo + 0.2)
            closes.append(z_hi + 0.5)
        else:
            highs.append(z_hi + 6.0)
            lows.append(z_hi + 4.0)
            closes.append(z_hi + 5.0)
    if last_close is not None:
        closes[-1] = last_close
        highs[-1] = max(highs[-1], last_close)
        lows[-1] = min(lows[-1], last_close)
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes,
         "volume": [1_000_000.0] * n},
        index=idx,
    )


# ---- entry_family ----

def test_entry_family_mss_reclaim_when_sweep_and_mss():
    fam = classify_entry_family("MSS", True, {"fvg_bot": 1}, {"ob_lo": 1},
                                "UNKNOWN", "supportive", "confirmed")
    assert fam == "mss_reclaim", "sweep + MSS must classify as mss_reclaim before zone families"


def test_entry_family_failed_break_conversion_on_reclaim():
    fam = classify_entry_family("reclaim", False, None, None,
                                "UNKNOWN", "mixed", "confirmed")
    assert fam == "failed_break_conversion"


def test_entry_family_zone_core_when_fvg_and_ob():
    fam = classify_entry_family("BOS", False, {"fvg_bot": 1}, {"ob_lo": 1},
                                "UNKNOWN", "mixed", "confirmed")
    assert fam == "zone_core"


def test_entry_family_fvg_entry_when_only_fvg():
    fam = classify_entry_family("BOS", False, {"fvg_bot": 1}, None,
                                "UNKNOWN", "mixed", "confirmed")
    assert fam == "fvg_entry"


def test_entry_family_ob_entry_when_only_ob():
    fam = classify_entry_family("BOS", False, None, {"ob_lo": 1},
                                "UNKNOWN", "mixed", "confirmed")
    assert fam == "ob_entry"


def test_entry_family_vcp_base_when_vcp_and_no_zone():
    # VCP is one family inside the doctrine — only used when no structural zone.
    fam = classify_entry_family("none", False, None, None,
                                "CONFIRMED", "mixed", "missing")
    assert fam == "vcp_base"


def test_entry_family_vcp_does_not_override_zone():
    # A confirmed VCP with a present FVG zone is still a zone family, not vcp_base.
    fam = classify_entry_family("BOS", False, {"fvg_bot": 1}, None,
                                "CONFIRMED", "mixed", "confirmed")
    assert fam == "fvg_entry", "VCP must never displace a structural zone family"


def test_entry_family_dynamic_value_when_sma_retest_only():
    fam = classify_entry_family("BOS", False, None, None,
                                "UNKNOWN", "supportive", "partial")
    assert fam == "dynamic_value"


def test_entry_family_unclassified_when_no_signals():
    fam = classify_entry_family("none", False, None, None,
                                "UNKNOWN", "hostile", "missing")
    assert fam == "unclassified"


# ---- retest_quality ----

def test_retest_quality_not_retesting_when_status_missing():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars=set())
    assert assess_retest_quality(df, "missing", "OB", None, {"ob_lo": 100.0, "ob_hi": 102.0}) == "not_retesting"


def test_retest_quality_not_retesting_when_no_zone():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars=set())
    assert assess_retest_quality(df, "confirmed", None, None, None) == "not_retesting"


def test_retest_quality_clean_bounce_when_wick_then_close_above():
    # Final bar wicks into the zone but closes above it; little prior lingering.
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={11}, last_close=None)
    # Force the last bar: low dips into zone, close back above zone top.
    df.iloc[-1, df.columns.get_loc("low")] = 101.0
    df.iloc[-1, df.columns.get_loc("close")] = 103.0
    df.iloc[-1, df.columns.get_loc("high")] = 103.5
    q = assess_retest_quality(df, "confirmed", "OB", None, {"ob_lo": 100.0, "ob_hi": 102.0})
    assert q == "clean_bounce", f"expected clean_bounce, got {q}"


def test_retest_quality_body_in_zone_when_close_inside():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={11}, last_close=101.0)
    q = assess_retest_quality(df, "confirmed", "OB", None, {"ob_lo": 100.0, "ob_hi": 102.0})
    assert q == "body_in_zone", f"expected body_in_zone, got {q}"


def test_retest_quality_overlap_when_many_bars_in_zone():
    # Several recent bars overlap the zone; final close above → drift/overlap.
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={7, 8, 9, 10}, last_close=107.0)
    q = assess_retest_quality(df, "confirmed", "OB", None, {"ob_lo": 100.0, "ob_hi": 102.0})
    assert q == "overlap", f"expected overlap, got {q}"


# ---- consumption_risk ----

def test_consumption_risk_unknown_when_no_zone():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars=set())
    assert assess_consumption_risk(df, None, None, None) == "unknown"


def test_consumption_risk_low_when_zero_or_one_touch():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={9})
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    assert assess_consumption_risk(df, None, ob, "OB") == "low"


def test_consumption_risk_moderate_when_two_touches():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={8, 10})
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    assert assess_consumption_risk(df, None, ob, "OB") == "moderate"


def test_consumption_risk_high_when_three_touches_no_expansion():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={7, 9, 11}, last_close=101.0)
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    assert assess_consumption_risk(df, None, ob, "OB") == "high"


def test_consumption_risk_moderate_when_three_touches_but_expanded():
    # 3+ touches but price expanded well above the zone → not high.
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars={5, 6, 7}, last_close=120.0)
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    assert assess_consumption_risk(df, None, ob, "OB") == "moderate"


# ---- level_authority ----

def test_level_authority_strong_when_three_nearby_swings():
    swings = {"swing_highs": [(10, 100.0), (20, 100.5), (30, 99.8)], "swing_lows": [(15, 90.0)]}
    assert assess_level_authority(100.0, None, None, swings, None) == "strong"


def test_level_authority_moderate_when_two_nearby_swings():
    swings = {"swing_highs": [(10, 100.0), (20, 100.4)], "swing_lows": [(15, 80.0)]}
    assert assess_level_authority(100.0, None, None, swings, None) == "moderate"


def test_level_authority_weak_when_one_nearby_swing():
    swings = {"swing_highs": [(10, 100.0)], "swing_lows": [(15, 80.0)]}
    assert assess_level_authority(100.0, None, None, swings, None) == "weak"


def test_level_authority_unknown_when_no_reference_level():
    swings = {"swing_highs": [(10, 100.0)], "swing_lows": []}
    assert assess_level_authority(None, None, None, swings, None) == "unknown"


def test_level_authority_uses_zone_core_when_no_structure_level():
    swings = {"swing_highs": [(10, 101.0), (20, 100.9), (30, 101.1)], "swing_lows": []}
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    # zone core = 101.0; three swings within 1% → strong
    assert assess_level_authority(None, None, ob, swings, "OB") == "strong"


# ---- zone_freshness ----

def test_zone_freshness_unknown_when_no_zone():
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars=set())
    assert assess_zone_freshness(df, None, None, None) == "unknown"


def test_zone_freshness_fresh_when_young_and_untouched():
    # Zone formed 4 bars ago, no touches → fresh.
    df = _zone_touch_df(12, 100.0, 102.0, touch_bars=set())
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 8}
    assert assess_zone_freshness(df, None, ob, "OB") == "fresh"


def test_zone_freshness_consumed_when_three_touches():
    df = _zone_touch_df(20, 100.0, 102.0, touch_bars={10, 12, 14})
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 3}
    assert assess_zone_freshness(df, None, ob, "OB") == "consumed"


def test_zone_freshness_tested_when_aged_with_some_interaction():
    # Old zone (formed at idx 2 of 30 bars), one touch → tested (not fresh, not consumed).
    df = _zone_touch_df(30, 100.0, 102.0, touch_bars={20})
    ob = {"ob_lo": 100.0, "ob_hi": 102.0, "ob_idx": 2}
    assert assess_zone_freshness(df, None, ob, "OB") == "tested"


# ---- break_retest_state ----

def test_break_retest_state_awaiting_break_when_no_structure():
    assert classify_break_retest_state("none", "missing") == "awaiting_break"


def test_break_retest_state_break_confirmed_when_bos_no_retest():
    assert classify_break_retest_state("BOS", "missing") == "break_confirmed"


def test_break_retest_state_retesting_when_partial():
    assert classify_break_retest_state("BOS", "partial") == "retesting"


def test_break_retest_state_retesting_when_confirmed_no_hold():
    # Scanner view (no hold_status supplied): confirmed retest = retesting.
    assert classify_break_retest_state("BOS", "confirmed") == "retesting"


def test_break_retest_state_failed_when_retest_failed():
    assert classify_break_retest_state("BOS", "failed") == "failed"


def test_break_retest_state_hold_states_future_wired():
    # When hold + acceptance are supplied, the downstream sequence states light up.
    assert classify_break_retest_state("BOS", "confirmed", "confirmed", "accepted") == "active_entry"
    assert classify_break_retest_state("BOS", "confirmed", "confirmed", "damaging") == "trigger_pending"
    assert classify_break_retest_state("BOS", "confirmed", "confirmed", None) == "hold_confirmed"


def test_break_retest_state_unknown_on_garbage():
    assert classify_break_retest_state("weird_state", "weird") == "unknown"


# ---- enrich() integration ----

def test_brt_fields_present_in_enrich_output():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    for key in _BRT_FIELDS:
        assert key in result, f"BRT field missing from enrich() output: {key}"


def test_brt_one_hour_momentum_repair_is_deferred():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    assert result["one_hour_momentum_repair"] == "deferred_requires_1h", (
        "one_hour_momentum_repair must remain deferred — no daily-bar proxy allowed"
    )


def test_brt_enrich_labels_within_valid_domains():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG)
    assert r["entry_family"] in {
        "zone_core", "fvg_entry", "ob_entry", "mss_reclaim",
        "failed_break_conversion", "vcp_base", "dynamic_value", "unclassified",
    }
    assert r["retest_quality"] in {"clean_bounce", "body_in_zone", "overlap", "unclear", "not_retesting"}
    assert r["consumption_risk"] in {"low", "moderate", "high", "unknown"}
    assert r["level_authority"] in {"strong", "moderate", "weak", "unknown"}
    assert r["zone_freshness"] in {"fresh", "tested", "consumed", "unknown"}
    assert r["break_retest_state"] in {
        "awaiting_break", "break_confirmed", "retesting", "hold_confirmed",
        "trigger_pending", "active_entry", "failed", "unknown",
    }


def test_no_disabled_indicators_in_brt_functions():
    # Source-level guard: the new Phase 1C functions must not reference any
    # forbidden retail indicator. Word-boundary match so doctrine labels that
    # legitimately embed a substring (e.g. "failed_break_conve[rsi]on") do not
    # trip a false positive.
    import inspect
    import re
    for fn in (
        classify_entry_family, assess_retest_quality, assess_consumption_risk,
        assess_level_authority, assess_zone_freshness, classify_break_retest_state,
    ):
        src = inspect.getsource(fn).lower()
        for bad in ("rsi", "macd", "bollinger", "stochastic"):
            assert not re.search(rf"\b{bad}\b", src), (
                f"forbidden indicator {bad!r} found in {fn.__name__}"
            )


# ===========================================================================
# Phase 1D — Market Structure State (evidence-only)
# ===========================================================================

_MKTSTATE_VALID = frozenset({
    "EXPANSION", "ORDERLY_CONTINUATION", "COMPRESSION",
    "REPAIR", "TRANSITION", "FAILURE", "UNKNOWN",
})

# Shorthand to avoid 5-arg repetition in tests
def _mss(se, sw, rs, sva, oh):
    return classify_market_structure_state(se, sw, rs, sva, oh)


# ---- EXPANSION ----

def test_mktstate_expansion_on_mss_sweep_supportive():
    assert _mss("MSS", True, "confirmed", "supportive", "clear") == "EXPANSION"


def test_mktstate_expansion_on_mss_no_sweep_supportive():
    # MSS alone with supportive alignment is sufficient for EXPANSION
    assert _mss("MSS", False, "partial", "supportive", "unknown") == "EXPANSION"


def test_mktstate_expansion_on_bos_with_sweep_supportive():
    assert _mss("BOS", True, "partial", "supportive", "clear") == "EXPANSION"


# ---- ORDERLY_CONTINUATION ----

def test_mktstate_orderly_continuation_bos_no_sweep():
    assert _mss("BOS", False, "partial", "supportive", "clear") == "ORDERLY_CONTINUATION"


def test_mktstate_orderly_continuation_bos_missing_retest():
    assert _mss("BOS", False, "missing", "supportive", "clear") == "ORDERLY_CONTINUATION"


# ---- COMPRESSION ----

def test_mktstate_compression_no_structure_mixed_alignment():
    assert _mss("none", False, "missing", "mixed", "unknown") == "COMPRESSION"


def test_mktstate_compression_no_structure_unavailable_alignment():
    assert _mss("none", False, None, "unavailable", None) == "COMPRESSION"


def test_mktstate_compression_all_none_inputs():
    assert _mss(None, False, None, None, None) == "COMPRESSION"


# ---- REPAIR ----

def test_mktstate_repair_on_reclaim():
    assert _mss("reclaim", False, "partial", "supportive", "clear") == "REPAIR"


def test_mktstate_repair_sweep_without_mss():
    # Sweep detected but structure_event is none = repair in progress
    assert _mss("none", True, "partial", "supportive", "clear") == "REPAIR"


def test_mktstate_repair_sweep_with_bos_mixed_alignment():
    # BOS + sweep but mixed alignment → TRANSITION (not REPAIR)
    # because TRANSITION check runs first for known structure events
    result = _mss("BOS", True, "partial", "mixed", "clear")
    assert result == "TRANSITION"


def test_mktstate_repair_reclaim_with_supportive_alignment():
    assert _mss("reclaim", False, "not_retesting", "supportive", "unknown") == "REPAIR"


# ---- TRANSITION ----

def test_mktstate_transition_mss_with_mixed_alignment():
    assert _mss("MSS", False, "confirmed", "mixed", "clear") == "TRANSITION"


def test_mktstate_transition_bos_with_blocked_overhead():
    assert _mss("BOS", False, "partial", "supportive", "blocked") == "TRANSITION"


def test_mktstate_transition_mss_with_moderate_overhead():
    assert _mss("MSS", True, "confirmed", "supportive", "moderate") == "TRANSITION"


def test_mktstate_transition_bos_unavailable_alignment():
    assert _mss("BOS", False, "partial", "unavailable", "clear") == "TRANSITION"


# ---- FAILURE ----

def test_mktstate_failure_on_failed_retest():
    assert _mss("BOS", False, "failed", "mixed", "blocked") == "FAILURE"


def test_mktstate_failure_hostile_no_structure():
    assert _mss("none", False, "missing", "hostile", "clear") == "FAILURE"


def test_mktstate_failure_hostile_empty_structure():
    assert _mss(None, False, None, "hostile", None) == "FAILURE"


def test_mktstate_failure_overrides_structure():
    # Even strong structure event cannot prevent FAILURE when retest failed
    assert _mss("MSS", True, "failed", "supportive", "clear") == "FAILURE"


# ---- UNKNOWN ----

def test_mktstate_unknown_on_garbage_inputs():
    assert _mss("GARBAGE_EVENT", False, None, "strong_bull", None) == "UNKNOWN"


def test_mktstate_unknown_returns_string():
    result = _mss("GARBAGE", True, "garbage", "garbage", "garbage")
    assert isinstance(result, str)
    # Must be a valid state label
    assert result in _MKTSTATE_VALID


# ---- enrich() integration ----

def test_mktstate_present_in_enrich_output():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    assert "market_structure_state" in result, (
        "market_structure_state missing from enrich() output"
    )


def test_mktstate_enrich_label_within_valid_domain():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    assert result["market_structure_state"] in _MKTSTATE_VALID, (
        f"market_structure_state {result['market_structure_state']!r} not in valid domain"
    )


# ---- source guard ----

def test_no_disabled_indicators_in_mktstate_function():
    import inspect
    import re
    src = inspect.getsource(classify_market_structure_state).lower()
    for bad in ("rsi", "macd", "bollinger", "stochastic"):
        assert not re.search(rf"\b{bad}\b", src), (
            f"forbidden indicator {bad!r} found in classify_market_structure_state"
        )


# ===========================================================================
# Phase 14A — Weekly Sovereignty Evidence Layer (evidence-only)
# ===========================================================================

_WEEKLY_FIELDS = (
    "weekly_sma_alignment",
    "weekly_trend_state",
    "weekly_alignment_context",
)

_WK_ANCHOR = pd.Timestamp("2025-01-03")  # a Friday


def _wk_df(closes, highs=None, lows=None) -> pd.DataFrame:
    """Build a weekly OHLCV DataFrame (W-FRI index) directly from a close series."""
    n = len(closes)
    idx = pd.bdate_range(end=_WK_ANCHOR, periods=n, freq="W-FRI")
    c = np.array(closes, dtype=float)
    h = (c + 1.0) if highs is None else np.array(highs, dtype=float)
    l = (c - 1.0) if lows is None else np.array(lows, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": h, "low": l, "close": c, "volume": [1_000_000.0] * n},
        index=idx,
    )


def _wk_rising(n=60):
    return _wk_df(list(50 + np.arange(n) * 0.8))


def _wk_falling(n=60):
    return _wk_df(list(120 - np.arange(n) * 0.8))


def _wk_mixed():
    # Long rise then a sharp recent drop: close falls below SMA50 while SMA50
    # slope is still rising → neither supportive nor hostile → mixed.
    return _wk_df(list(50 + np.arange(56) * 0.9) + [95, 88, 80, 72])


def _wk_basing():
    # 60 weeks oscillating tightly around 100; last close just below range mid.
    return _wk_df([100 + (1.5 if i % 2 == 0 else -1.5) for i in range(59)] + [99.0])


def _wk_distributing():
    top = list(50 + np.arange(44) * 1.0)
    plat_close = [94, 95, 94, 93.5, 94.5, 94, 93.5, 94, 94.5, 94, 93.5, 94, 94.5, 94, 93.8, 94.2]
    plat_high = [95.5, 96, 95, 94.5, 95, 94.8, 94, 94.5, 95, 94.5, 94, 94.5, 95, 94.5, 94.3, 94.7]
    return _wk_df(top + plat_close, highs=[x + 1 for x in top] + plat_high)


# ---- weekly_sma_alignment (tests 1–4) ----

def test_weekly_sma_alignment_supportive_on_clean_uptrend():
    assert compute_weekly_sma_alignment(_wk_rising()) == "supportive"


def test_weekly_sma_alignment_mixed_on_incomplete_alignment():
    assert compute_weekly_sma_alignment(_wk_mixed()) == "mixed"


def test_weekly_sma_alignment_hostile_on_weekly_breakdown():
    assert compute_weekly_sma_alignment(_wk_falling()) == "hostile"


def test_weekly_sma_alignment_unavailable_on_insufficient_bars():
    assert compute_weekly_sma_alignment(_wk_df(list(50 + np.arange(20) * 0.8))) == "unavailable"


# ---- weekly_trend_state (tests 5–9) ----

def test_weekly_trend_state_advancing():
    assert compute_weekly_trend_state(_wk_rising()) == "advancing"


def test_weekly_trend_state_basing():
    assert compute_weekly_trend_state(_wk_basing()) == "basing"


def test_weekly_trend_state_distributing():
    assert compute_weekly_trend_state(_wk_distributing()) == "distributing"


def test_weekly_trend_state_declining():
    assert compute_weekly_trend_state(_wk_falling()) == "declining"


def test_weekly_trend_state_unknown_on_insufficient_data():
    assert compute_weekly_trend_state(_wk_df(list(50 + np.arange(15) * 0.8))) == "unknown"


# ---- weekly_alignment_context (tests 10–14) ----

def test_weekly_alignment_context_full():
    assert compute_weekly_alignment_context(
        "supportive", "advancing", "supportive", "EXPANSION"
    ) == "full_alignment"


def test_weekly_alignment_context_partial():
    assert compute_weekly_alignment_context(
        "mixed", "basing", "supportive", "EXPANSION"
    ) == "partial_alignment"


def test_weekly_alignment_context_repair():
    assert compute_weekly_alignment_context(
        "mixed", "basing", "mixed", "REPAIR"
    ) == "repair_alignment"


def test_weekly_alignment_context_countertrend():
    assert compute_weekly_alignment_context(
        "hostile", "declining", "supportive", "EXPANSION"
    ) == "countertrend_context"


def test_weekly_alignment_context_unknown_when_unavailable():
    assert compute_weekly_alignment_context(
        "unavailable", "unknown", "supportive", "EXPANSION"
    ) == "unknown"


# ---- enrich() integration (test 15) ----

def test_enrich_returns_all_weekly_fields():
    df = _make_trending_df(300)
    result = enrich("TEST", df, BASE_CONFIG)
    for key in _WEEKLY_FIELDS:
        assert key in result, f"weekly field missing from enrich() output: {key}"


def test_enrich_weekly_fields_within_valid_domains():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG)
    assert r["weekly_sma_alignment"] in {"supportive", "mixed", "hostile", "unavailable"}
    assert r["weekly_trend_state"] in {"advancing", "basing", "distributing", "declining", "unknown"}
    assert r["weekly_alignment_context"] in {
        "full_alignment", "partial_alignment", "repair_alignment",
        "countertrend_context", "unknown",
    }


# ---- safe defaults & failure handling ----

def test_weekly_evidence_safe_defaults_on_short_df():
    df = _make_df(120)  # ~24 weeks → insufficient for weekly SMA50
    ev = compute_weekly_evidence(df, "mixed", "COMPRESSION")
    assert ev["weekly_sma_alignment"] == "unavailable"
    assert ev["weekly_trend_state"] == "unknown"
    assert ev["weekly_alignment_context"] == "unknown"


def test_weekly_evidence_safe_defaults_on_garbage_input():
    # Non-DatetimeIndex / empty inputs must not raise.
    assert compute_weekly_evidence(None, "supportive", "EXPANSION") == {
        "weekly_sma_alignment": "unavailable",
        "weekly_trend_state": "unknown",
        "weekly_alignment_context": "unknown",
    }
    empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    ev = compute_weekly_evidence(empty, "supportive", "EXPANSION")
    assert ev["weekly_sma_alignment"] == "unavailable"


# ---- forbidden-indicator source guard (test 31) ----

def test_no_disabled_indicators_in_weekly_functions():
    import inspect
    import re
    for fn in (
        compute_weekly_sma_alignment, compute_weekly_trend_state,
        compute_weekly_alignment_context, compute_weekly_evidence,
    ):
        src = inspect.getsource(fn).lower()
        for bad in ("rsi", "macd", "bollinger", "stochastic"):
            assert not re.search(rf"\b{bad}\b", src), (
                f"forbidden indicator {bad!r} found in {fn.__name__}"
            )


# ---- coexistence with prior evidence layers (test 32, indicators side) ----

def test_weekly_coexists_with_vcp_brt_mktstate_in_enrich():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG)
    # Prior-phase evidence fields still present alongside weekly fields.
    for key in ("vcp_status", "entry_family", "break_retest_state",
                "market_structure_state", "weekly_sma_alignment",
                "weekly_trend_state", "weekly_alignment_context"):
        assert key in r, f"expected evidence field missing after Phase 14A: {key}"


# ===========================================================================
# Phase 14C — Real 4H Operational State Evidence Engine (evidence-only)
# ===========================================================================

_4H_END = pd.Timestamp("2026-06-05 16:00")
_4H_FIELDS = (
    "four_hour_market_state",
    "four_hour_sma_alignment",
    "four_hour_reclaim_status",
    "four_hour_structure_note",
    "four_hour_data_status",
)


def _df4h(closes, highs=None, lows=None, opens=None, end=_4H_END):
    """Build a real 4H OHLCV DataFrame (DatetimeIndex at 4H freq)."""
    n = len(closes)
    idx = pd.date_range(end=pd.Timestamp(end), periods=n, freq="4h")
    c = np.array(closes, dtype=float)
    h = (c + 0.5) if highs is None else np.array(highs, dtype=float)
    l = (c - 0.5) if lows is None else np.array(lows, dtype=float)
    o = c if opens is None else np.array(opens, dtype=float)
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": [1_000_000.0] * n},
        index=idx,
    )


def _4h_pad(closes, highs, lows, fill=12):
    """Prepend flat filler bars so the shaped last-12 bars drive the structure read."""
    fc = [closes[0]] * fill
    fh = [highs[0]] * fill
    fl = [lows[0]] * fill
    return _df4h(fc + list(closes), highs=fh + list(highs), lows=fl + list(lows))


def _4h_uptrend(n=60):
    return _df4h(list(50 + np.arange(n) * 0.5))


def _4h_downtrend(n=60):
    return _df4h(list(120 - np.arange(n) * 0.5))


# ---- four_hour_sma_alignment (supportive | mixed | hostile | unavailable) ----

def test_4h_sma_alignment_supportive():
    assert compute_4h_sma_alignment(_4h_uptrend()) == "supportive"


def test_4h_sma_alignment_hostile():
    assert compute_4h_sma_alignment(_4h_downtrend()) == "hostile"


def test_4h_sma_alignment_mixed():
    # Downtrend (sma20 < sma50) then a pop above sma20 → neither full-stack nor hostile.
    base = list(120 - np.arange(50) * 0.4)
    m = _df4h(base + [base[-1] + 3, base[-1] + 5])
    assert compute_4h_sma_alignment(m) == "mixed"


def test_4h_sma_alignment_unavailable_on_short_data():
    assert compute_4h_sma_alignment(_df4h(list(range(10)))) == "unavailable"


# ---- four_hour_reclaim_status ----

def test_4h_reclaim_reclaimed():
    assert compute_4h_reclaim_status(_4h_uptrend()) == "reclaimed"


def test_4h_reclaim_below_value():
    assert compute_4h_reclaim_status(_4h_downtrend()) == "below_value"


def test_4h_reclaim_testing():
    base = list(120 - np.arange(50) * 0.4)
    m = _df4h(base + [base[-1] + 3, base[-1] + 5])
    assert compute_4h_reclaim_status(m) == "testing"


def test_4h_reclaim_failed_reclaim():
    base = list(120 - np.arange(40) * 0.5)
    closes = base + [101, 103, 102]
    opens = list(closes)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    highs[-2] = closes[-2] + 8          # a recent bar pokes above SMA20
    opens[-1] = closes[-1] + 4          # last bar closes bearish, back below
    d = _df4h(closes, highs=highs, lows=lows, opens=opens)
    assert compute_4h_reclaim_status(d) == "failed_reclaim"


def test_4h_reclaim_unavailable_on_short_data():
    assert compute_4h_reclaim_status(_df4h(list(range(8)))) == "unavailable"


# ---- four_hour_structure_note ----

def test_4h_structure_higher_high_sequence():
    d = _df4h([80] * 12 + [90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 112])
    assert compute_4h_structure_note(d) == "higher_high_sequence"


def test_4h_structure_higher_low_repair():
    hl_c = [91, 92, 93, 92, 94, 93, 95, 94, 96, 95, 97, 96]
    hl_h = [97] * 12
    hl_l = [88, 89, 89, 90, 90, 91, 92, 92, 93, 93, 94, 94]
    assert compute_4h_structure_note(_4h_pad(hl_c, hl_h, hl_l)) == "higher_low_repair"


def test_4h_structure_lower_high_pressure():
    lh_h = [110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100, 99]
    lh_l = [95] * 12
    lh_c = [103, 102, 101, 100, 99, 98, 99, 100, 99, 100, 99, 100]
    assert compute_4h_structure_note(_4h_pad(lh_c, lh_h, lh_l)) == "lower_high_pressure"


def test_4h_structure_range_compression():
    wide_c = [100] * 6
    wide_h = [105, 104, 105, 104, 105, 104]
    wide_l = [95, 96, 95, 96, 95, 96]
    tight_c = [100] * 6
    tight_h = [101, 100.8, 101, 100.8, 101, 100.8]
    tight_l = [99, 99.2, 99, 99.2, 99, 99.2]
    d = _4h_pad(wide_c + tight_c, wide_h + tight_h, wide_l + tight_l)
    assert compute_4h_structure_note(d) == "range_compression"


def test_4h_structure_breakdown_pressure():
    bd_h = [110, 108, 106, 104, 102, 100, 98, 96, 94, 92, 90, 88]
    bd_l = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82, 80, 78]
    bd_c = [101, 99, 97, 95, 93, 91, 89, 87, 85, 83, 81, 79]
    assert compute_4h_structure_note(_4h_pad(bd_c, bd_h, bd_l)) == "breakdown_pressure"


def test_4h_structure_failed_breakdown_reclaim():
    fb_l = [100, 100, 100, 100, 100, 100, 99, 98, 95, 97, 99, 100]
    fb_h = [105, 105, 105, 105, 105, 105, 104, 103, 100, 104, 106, 107]
    fb_c = [104, 104, 104, 104, 104, 104, 102, 100, 96, 103, 105, 106]
    assert compute_4h_structure_note(_4h_pad(fb_c, fb_h, fb_l)) == "failed_breakdown_reclaim"


def test_4h_structure_unknown():
    d = _df4h([100] * 24, highs=[101] * 24, lows=[99] * 24)
    assert compute_4h_structure_note(d) == "unknown"


def test_4h_structure_unavailable_on_short_data():
    assert compute_4h_structure_note(_df4h(list(range(10)))) == "unavailable"


# ---- four_hour_data_status (current | degraded | stale | unavailable) ----

def test_4h_data_status_current():
    d = _4h_uptrend(30)
    assert compute_4h_data_status(d, None, pd.Timestamp("2026-06-05 18:00")) == "current"


def test_4h_data_status_degraded():
    d = _4h_uptrend(30)
    assert compute_4h_data_status(d, None, pd.Timestamp("2026-06-06 12:00")) == "degraded"


def test_4h_data_status_stale():
    d = _4h_uptrend(30)
    assert compute_4h_data_status(d, None, pd.Timestamp("2026-06-10 16:00")) == "stale"


def test_4h_data_status_unavailable():
    assert compute_4h_data_status(None) == "unavailable"
    empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    assert compute_4h_data_status(empty) == "unavailable"


# ---- classify_4h_market_state (all 8 states, deterministic synthesis) ----

def test_4h_market_state_expansion():
    assert classify_4h_market_state(
        None, "supportive", "reclaimed", "higher_high_sequence"
    ) == "EXPANSION"


def test_4h_market_state_orderly_continuation():
    assert classify_4h_market_state(
        None, "supportive", "reclaimed", "higher_low_repair"
    ) == "ORDERLY_CONTINUATION"


def test_4h_market_state_compression():
    assert classify_4h_market_state(
        None, "mixed", "below_value", "range_compression"
    ) == "COMPRESSION"


def test_4h_market_state_repair():
    assert classify_4h_market_state(
        None, "mixed", "below_value", "failed_breakdown_reclaim"
    ) == "REPAIR"
    assert classify_4h_market_state(
        None, "mixed", "testing", "unknown"
    ) == "REPAIR"


def test_4h_market_state_transition():
    assert classify_4h_market_state(
        None, "hostile", "below_value", "lower_high_pressure"
    ) == "TRANSITION"
    assert classify_4h_market_state(
        None, "mixed", "unknown", "unknown"
    ) == "TRANSITION"


def test_4h_market_state_failure():
    assert classify_4h_market_state(
        None, "hostile", "below_value", "breakdown_pressure"
    ) == "FAILURE"


def test_4h_market_state_unknown():
    assert classify_4h_market_state(
        None, "supportive", "unknown", "unknown"
    ) == "UNKNOWN"


def test_4h_market_state_unavailable():
    assert classify_4h_market_state(
        None, "unavailable", "unavailable", "unavailable"
    ) == "UNAVAILABLE"


# ---- compute_four_hour_evidence orchestrator & safe defaults ----

def test_4h_evidence_full_on_real_uptrend():
    ev = compute_four_hour_evidence(
        _4h_uptrend(60), None, pd.Timestamp("2026-06-05 18:00")
    )
    assert ev["four_hour_market_state"] == "EXPANSION"
    assert ev["four_hour_sma_alignment"] == "supportive"
    assert ev["four_hour_reclaim_status"] == "reclaimed"
    assert ev["four_hour_structure_note"] == "higher_high_sequence"
    assert ev["four_hour_data_status"] == "current"


def test_4h_evidence_unavailable_on_none():
    assert compute_four_hour_evidence(None) == {
        "four_hour_market_state": "UNAVAILABLE",
        "four_hour_sma_alignment": "unavailable",
        "four_hour_reclaim_status": "unavailable",
        "four_hour_structure_note": "unavailable",
        "four_hour_data_status": "unavailable",
    }


def test_4h_evidence_unavailable_on_short_data():
    ev = compute_four_hour_evidence(_4h_uptrend(10))
    assert ev["four_hour_market_state"] == "UNAVAILABLE"
    assert ev["four_hour_sma_alignment"] == "unavailable"
    assert ev["four_hour_data_status"] == "unavailable"


def test_4h_evidence_safe_on_empty_df():
    empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    assert compute_four_hour_evidence(empty) == _EMPTY_4H_EXPECTED


def test_4h_evidence_safe_on_nan_data():
    closes = list(50 + np.arange(30) * 0.5)
    closes[-1] = np.nan
    closes[-5] = np.nan
    d = _df4h(closes)
    ev = compute_four_hour_evidence(d, None, pd.Timestamp("2026-06-05 18:00"))
    # Must not raise; every field stays within its valid domain.
    assert ev["four_hour_market_state"] in {
        "EXPANSION", "ORDERLY_CONTINUATION", "COMPRESSION", "REPAIR",
        "TRANSITION", "FAILURE", "UNKNOWN", "UNAVAILABLE",
    }
    assert ev["four_hour_sma_alignment"] in {"supportive", "mixed", "hostile", "unavailable"}


def test_4h_evidence_safe_on_non_datetime_index():
    d = _4h_uptrend(60).reset_index(drop=True)  # RangeIndex, not DatetimeIndex
    assert compute_four_hour_evidence(d) == _EMPTY_4H_EXPECTED


_EMPTY_4H_EXPECTED = {
    "four_hour_market_state": "UNAVAILABLE",
    "four_hour_sma_alignment": "unavailable",
    "four_hour_reclaim_status": "unavailable",
    "four_hour_structure_note": "unavailable",
    "four_hour_data_status": "unavailable",
}


# ---- enrich() integration ----

def test_enrich_4h_unavailable_when_no_4h_df():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG)  # no four_hour_df → honest UNAVAILABLE
    assert r["four_hour_market_state"] == "UNAVAILABLE"
    assert r["four_hour_sma_alignment"] == "unavailable"
    assert r["four_hour_reclaim_status"] == "unavailable"
    assert r["four_hour_structure_note"] == "unavailable"
    assert r["four_hour_data_status"] == "unavailable"


def test_enrich_4h_real_values_when_4h_df_supplied():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG, four_hour_df=_4h_uptrend(60))
    assert r["four_hour_market_state"] == "EXPANSION"
    assert r["four_hour_sma_alignment"] == "supportive"
    for key in _4H_FIELDS:
        assert key in r


def test_enrich_4h_does_not_fake_from_daily():
    # The daily df is a clean uptrend; without a real 4H df, 4H must stay
    # UNAVAILABLE — proving 4H is never manufactured from daily bars.
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG)
    assert r["four_hour_market_state"] == "UNAVAILABLE"
    # Daily proxy (market_structure_state) remains independently populated.
    assert r["market_structure_state"] != "UNAVAILABLE"


# ---- forbidden-indicator source guard ----

def test_no_disabled_indicators_in_4h_functions():
    import inspect
    import re
    for fn in (
        compute_4h_sma_alignment, compute_4h_reclaim_status,
        compute_4h_structure_note, compute_4h_data_status,
        classify_4h_market_state, compute_four_hour_evidence,
    ):
        src = inspect.getsource(fn).lower()
        for bad in ("rsi", "macd", "bollinger", "stochastic"):
            assert not re.search(rf"\b{bad}\b", src), (
                f"forbidden indicator {bad!r} found in {fn.__name__}"
            )


# ---- coexistence with all prior evidence layers ----

def test_4h_coexists_with_all_prior_evidence_in_enrich():
    df = _make_trending_df(300)
    r = enrich("TEST", df, BASE_CONFIG, four_hour_df=_4h_uptrend(60))
    for key in ("vcp_status", "entry_family", "break_retest_state",
                "market_structure_state", "weekly_sma_alignment",
                "weekly_trend_state", "weekly_alignment_context",
                "four_hour_market_state", "four_hour_data_status"):
        assert key in r, f"expected evidence field missing after Phase 14C: {key}"

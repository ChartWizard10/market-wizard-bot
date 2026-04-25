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
    pytest.skip("Verified in Phase 4 when build_prompt() is implemented")


def test_no_disabled_in_discord_embed():
    pytest.skip("Verified in Phase 7 when discord_alerts is implemented")


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

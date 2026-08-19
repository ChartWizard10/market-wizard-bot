"""Phase SFC-1 deterministic setup-family compiler tests."""

from copy import deepcopy

import numpy as np
import pandas as pd

from src.setup_family_compiler import (
    BREAK_RETEST_CONTINUATION,
    GAP_FILL_REVERSAL,
    NONE,
    SMA_CRADLE_CONTINUATION,
    VCP_BREAK_RETEST,
    compile_setup_families,
)


def _frame(closes, volumes=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if volumes is None:
        volumes = np.full(n, 1_000_000.0)
    volumes = np.asarray(volumes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    highs = np.maximum(opens, closes) + 0.8
    lows = np.minimum(opens, closes) - 0.8
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _base(**overrides):
    out = {
        "structure_event": "none",
        "retest_status": "missing",
        "overhead_status": "clear",
        "invalidation_level": None,
        "targets": [],
    }
    out.update(overrides)
    return out


def test_break_retest_continuation_uses_existing_structure_truth():
    df = _frame(np.linspace(100, 135, 70))
    base = _base(
        structure_event="reclaim",
        retest_status="confirmed",
        invalidation_level=131.0,
        targets=[{"level": 145.0}],
    )
    result = compile_setup_families(df, 135.0, base)
    br = result["families"][BREAK_RETEST_CONTINUATION]

    assert br["detected"] is True
    assert br["state"] == "RETEST_HELD"
    assert br["entry_structure_valid"] is True
    assert br["admission_ready"] is True
    assert br["invalidation_level"] == 131.0
    assert br["target_1"] == 145.0


def _vcp_frame():
    first = np.linspace(90.0, 126.0, 50)
    # Broad -> medium -> tight compression near the high.
    tail = np.array(
        [
            126.0, 131.0, 125.0, 130.0, 126.5,
            129.8, 127.2, 129.7, 127.8, 129.6,
            128.2, 129.8, 128.6, 129.9, 128.9,
            129.6, 129.1, 129.8, 129.3, 129.9,
        ]
    )
    closes = np.r_[first, tail]
    volumes = np.r_[np.full(50, 1_500_000.0), np.full(15, 1_050_000.0), np.full(5, 550_000.0)]
    df = _frame(closes, volumes)
    # Give the broad early contractions more range while the final five stay tight.
    df.loc[50:54, "high"] += 2.0
    df.loc[50:54, "low"] -= 2.0
    df.loc[55:59, "high"] += 1.0
    df.loc[55:59, "low"] -= 1.0
    df.loc[65:69, "high"] = np.maximum(df.loc[65:69, "open"], df.loc[65:69, "close"]) + 0.25
    df.loc[65:69, "low"] = np.minimum(df.loc[65:69, "open"], df.loc[65:69, "close"]) - 0.25
    return df


def test_vcp_detects_sponsored_contraction_without_classic_fvg_ob_structure():
    df = _vcp_frame()
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    vcp = result["families"][VCP_BREAK_RETEST]

    assert vcp["detected"] is True
    assert vcp["watch_ready"] is True
    assert vcp["admission_ready"] is True
    assert vcp["state"] in {"FINAL_CONTRACTION", "BREAKOUT_ACCEPTED", "BREAKOUT_RETEST_HELD"}
    assert vcp["metrics"]["range_contracting"] or vcp["metrics"]["pullbacks_contracting"]
    assert vcp["metrics"]["volume_contracting"] is True
    assert vcp["target_1"] is not None


def test_random_sideways_chop_is_not_promoted_to_vcp():
    x = np.arange(80)
    closes = 100 + np.sin(x * 1.7) * 5.0
    df = _frame(closes, np.full(80, 1_000_000.0))
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    vcp = result["families"][VCP_BREAK_RETEST]

    assert vcp["admission_ready"] is False
    assert vcp["entry_structure_valid"] is False


def _cradle_frame(close_above=True):
    closes = np.linspace(90.0, 140.0, 75)
    # Controlled repair lets the rising 20-day average catch price.
    closes[-6:] = [139.0, 137.8, 136.8, 136.0, 136.6, 137.2 if close_above else 125.0]
    volumes = np.r_[np.full(69, 1_200_000.0), np.full(6, 700_000.0)]
    df = _frame(closes, volumes)
    sma20 = df.close.rolling(20).mean()
    # Defensive penultimate candle pierces value and recovers above it.
    i = len(df) - 2
    ma = float(sma20.iloc[i])
    df.loc[i, "open"] = ma + 0.35
    df.loc[i, "low"] = ma - 1.25
    df.loc[i, "close"] = ma + 0.55
    df.loc[i, "high"] = ma + 0.9
    if close_above:
        latest_ma = float(df.close.rolling(20).mean().iloc[-1])
        df.loc[len(df) - 1, "open"] = latest_ma + 0.2
        df.loc[len(df) - 1, "low"] = latest_ma - 0.15
        df.loc[len(df) - 1, "close"] = latest_ma + 0.6
        df.loc[len(df) - 1, "high"] = latest_ma + 0.9
    return df


def test_sma_cradle_recognizes_rising_value_defense_not_blind_ma_touch():
    df = _cradle_frame(close_above=True)
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    cradle = result["families"][SMA_CRADLE_CONTINUATION]

    assert cradle["detected"] is True
    assert cradle["location_valid"] is True
    assert cradle["metrics"]["touched_value"] is True
    assert cradle["metrics"]["defensive_lower_wick"] is True
    assert cradle["metrics"]["reclaim"] is True
    assert cradle["admission_ready"] is True


def test_sma_touch_without_reclaim_never_becomes_entry_structure_valid():
    df = _cradle_frame(close_above=False)
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    cradle = result["families"][SMA_CRADLE_CONTINUATION]

    assert cradle["entry_structure_valid"] is False
    assert cradle["state"] != "CRADLE_RETEST_HELD"


def _gap_fill_frame(accepted_below=False):
    closes = np.linspace(95.0, 108.0, 60)
    df = _frame(closes)
    gap_i = 45
    prev_close = float(df.close.iloc[gap_i - 1])
    gap_high = prev_close + 4.0
    df.loc[gap_i, "open"] = gap_high
    df.loc[gap_i, "low"] = gap_high - 0.4
    df.loc[gap_i, "high"] = gap_high + 2.0
    df.loc[gap_i, "close"] = gap_high + 1.2

    # Keep the auction above the gap until the recent fill test.
    for i in range(gap_i + 1, len(df) - 5):
        value = gap_high + 1.0 + (i - gap_i) * 0.12
        df.loc[i, ["open", "close"]] = [value - 0.15, value]
        df.loc[i, "high"] = value + 0.5
        df.loc[i, "low"] = value - 0.5

    if accepted_below:
        vals = [gap_high + 0.5, gap_high - 1.0, prev_close - 0.6, prev_close - 0.8, prev_close - 0.9]
    else:
        vals = [gap_high + 0.7, gap_high - 0.4, prev_close - 0.45, prev_close + 0.7, prev_close + 0.9]
    for j, value in enumerate(vals, start=len(df) - 5):
        df.loc[j, "open"] = value - 0.2
        df.loc[j, "close"] = value
        df.loc[j, "high"] = value + 0.5
        df.loc[j, "low"] = value - 0.55
    return df


def test_gap_fill_reversal_requires_failed_acceptance_and_reclaim():
    df = _gap_fill_frame(accepted_below=False)
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    gap = result["families"][GAP_FILL_REVERSAL]

    assert gap["detected"] is True
    assert gap["metrics"]["gap_fill_pct"] >= 50.0
    assert gap["metrics"]["body_reclaim"] is True
    assert gap["entry_structure_valid"] is True
    assert gap["admission_ready"] is True


def test_gap_fill_acceptance_below_boundary_blocks_bullish_family():
    df = _gap_fill_frame(accepted_below=True)
    result = compile_setup_families(df, float(df.close.iloc[-1]), _base())
    gap = result["families"][GAP_FILL_REVERSAL]

    assert gap["metrics"]["accepted_below_gap"] is True
    assert gap["admission_ready"] is False
    assert gap["entry_structure_valid"] is False
    assert "ACCEPTED_BELOW_GAP_BOUNDARY" in gap["blockers"]


def test_compiler_never_mutates_existing_canonical_features():
    df = _vcp_frame()
    base = _base(
        structure_event="reclaim",
        retest_status="partial",
        invalidation_level=120.0,
        targets=[{"level": 140.0}],
    )
    before = deepcopy(base)
    compile_setup_families(df, float(df.close.iloc[-1]), base)
    assert base == before


def test_bad_or_missing_history_degrades_to_none_without_fabrication():
    result = compile_setup_families(None, 100.0, _base())
    assert result["primary_family"] == NONE
    assert result["admission_ready"] is False
    assert result["entry_structure_valid"] is False
    assert all(not x["detected"] for x in result["families"].values())

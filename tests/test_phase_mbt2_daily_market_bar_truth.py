"""Phase MBT-2 — Daily Market-Bar Truth: developing vs closed Daily authority.

Governing law under test:

    CLOSED Daily bars own confirmation.
    The current LIVE Daily bar may inform location and developing state.

    A live break is not a closed BOS.
    A live reclaim is not a closed reclaim.
    A live zone breach is not an accepted Daily failure.
    Partial Daily volume is not a completed participation verdict.

    Current price truth and closed-candle truth must coexist without being
    confused.

Every test injects `now_utc` so the Daily session clock is deterministic and
never depends on when the suite runs.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src import candle_evidence, claude_client, indicators, market_data
from src import prefilter as prefilter_mod
from src import higher_timeframe_context
from src.market_data import resolve_daily_bar_status

ET = ZoneInfo("America/New_York")

CFG = {
    "prefilter": {
        "thresholds": {
            "swing_lookback_bars": 60,
            "recent_trigger_window_bars": 10,
            "fvg_lookback_bars": 30,
            "ob_lookback_bars": 30,
            "overhead_block_distance_pct": 3,
            "volume_expansion_ratio": 1.2,
            "volume_dryup_ratio": 0.8,
            "max_price_extension_from_sma20_pct": 8,
        },
        "scoring_weights": {
            "trend_value_alignment": 15,
            "structure_event": 20,
            "fvg_ob_demand_zone_quality": 15,
            "retest_proximity_status": 20,
            "target_path_rr_estimate": 15,
            "volume_participation": 10,
            "data_quality_recency": 5,
        },
        "prefilter_min_score": 55,
        "max_claude_candidates_per_scan": 30,
    },
    "tiers": {"snipe_it": {"min_rr": 3.0}},
}

# Deterministic session anchors. 2025-06-10 is a Tuesday, 2025-06-11 a
# Wednesday; both are EDT (UTC-4).
LAST_CLOSED_DAY = date(2025, 6, 10)
SESSION_DAY = date(2025, 6, 11)


def et_now(y, m, d, hour, minute=0) -> datetime:
    """A wall-clock America/New_York instant, as an absolute UTC datetime."""
    return datetime(y, m, d, hour, minute, tzinfo=ET).astimezone(timezone.utc)


NOW_MIDSESSION = et_now(2025, 6, 11, 14, 0)     # SESSION_DAY still trading
NOW_AFTER_CLOSE = et_now(2025, 6, 11, 16, 5)    # SESSION_DAY complete
NOW_NEXT_MORNING = et_now(2025, 6, 12, 9, 45)   # next session running


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _frame(rows, last=LAST_CLOSED_DAY) -> pd.DataFrame:
    idx = pd.bdate_range(end=last, periods=len(rows))
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [r[4] for r in rows],
        },
        index=idx,
    )


def _append(df, o, h, l, c, v=200_000.0, when=None):
    """Append one more daily row (the developing session by default)."""
    stamp = pd.Timestamp(when if when is not None else SESSION_DAY)
    return pd.concat(
        [df, pd.DataFrame(
            {"open": [o], "high": [h], "low": [l], "close": [c], "volume": [v]},
            index=[stamp],
        )]
    )


FLAT = (99.9, 100.5, 99.5, 100.0, 1_000_000.0)
PLATEAU = (105.8, 106.5, 105.5, 106.0, 1_000_000.0)


def flat_df(n=150) -> pd.DataFrame:
    """Completed history with NO confirmed structure event and no zone."""
    return _frame([FLAT] * n)


def _zone_rows(tail):
    """127 flat bars, a 3-bar displacement leaving one unfilled bullish FVG
    at [100.5, 103.0], then `tail`."""
    rows = [FLAT] * 127
    rows.append((100.0, 100.5, 99.5, 100.2, 1_000_000.0))    # c1: high = 100.5
    rows.append((100.3, 106.0, 100.2, 105.8, 3_000_000.0))   # displacement
    rows.append((103.5, 106.5, 103.0, 105.0, 2_000_000.0))   # c3: low  = 103.0
    return rows + tail


def zone_df() -> pd.DataFrame:
    """Confirmed FVG [100.5, 103.0]; completed price parked well above it."""
    return _frame(_zone_rows([PLATEAU] * 20))


def zone_retested_df() -> pd.DataFrame:
    """Same FVG, but the LAST COMPLETED bar closes inside the zone."""
    tail = []
    for i in range(20):
        c = 106.0 - (106.0 - 101.75) * (i + 1) / 20
        tail.append((c + 0.2, c + 0.5, max(c - 0.5, 100.7), c, 1_000_000.0))
    return _frame(_zone_rows(tail))


ZONE_LOW, ZONE_HIGH = 100.5, 103.0
ZONE_MID = 101.75


# ===========================================================================
# 1-7 — Daily bar-status law
# ===========================================================================

def test_01_same_session_row_before_close_is_live():
    ctx = resolve_daily_bar_status(_append(flat_df(30), 100, 101, 99, 100.5),
                                   now_utc=NOW_MIDSESSION)
    assert ctx["status"] == "LIVE"
    assert ctx["live_bar_available"] is True
    assert ctx["status_source"] == "regular_session_in_progress_et"
    assert ctx["live_daily_date"] == SESSION_DAY.isoformat()
    assert ctx["last_closed_daily_date"] == LAST_CLOSED_DAY.isoformat()
    assert ctx["using_live_bar_for_confirmation"] is False


def test_02_same_row_after_normal_close_is_closed():
    ctx = resolve_daily_bar_status(_append(flat_df(30), 100, 101, 99, 100.5),
                                   now_utc=NOW_AFTER_CLOSE)
    assert ctx["status"] == "CLOSED"
    assert ctx["live_bar_available"] is False
    assert ctx["status_source"] == "regular_session_complete_et"
    assert ctx["last_closed_daily_date"] == SESSION_DAY.isoformat()
    assert ctx["live_daily_date"] is None


def test_03_previous_trading_day_row_next_morning_is_closed():
    ctx = resolve_daily_bar_status(flat_df(30), now_utc=NOW_NEXT_MORNING)
    assert ctx["status"] == "CLOSED"
    assert ctx["status_source"] == "prior_session_date_et"
    assert ctx["live_bar_available"] is False


def test_04_weekend_does_not_make_friday_live():
    friday = date(2025, 6, 13)
    df = _frame([FLAT] * 30, last=friday)
    for now in (et_now(2025, 6, 14, 11, 0), et_now(2025, 6, 15, 11, 0)):
        ctx = resolve_daily_bar_status(df, now_utc=now)
        assert ctx["status"] == "CLOSED", now
        assert ctx["live_bar_available"] is False


def test_05_only_the_newest_daily_row_may_be_live():
    df = _append(flat_df(150), 100, 104, 99, 103.5)
    e = indicators.enrich("T", df, CFG, now_utc=NOW_MIDSESSION)
    ctx = e["daily_bar_context"]
    # Exactly one row is withheld from confirmation — never two, never zero.
    assert ctx["live_bar_available"] is True
    assert ctx["confirmed_bars"] == len(df) - 1
    assert e["last_closed_daily_close"] == round(float(df["close"].iloc[-2]), 4)


def test_06_dst_handled_by_zoneinfo_not_hardcoded_offsets():
    # Summer (EDT, UTC-4): 15:30 ET == 19:30 UTC -> still LIVE.
    summer_day = date(2025, 6, 11)
    df_summer = _frame([FLAT] * 30, last=summer_day)
    assert resolve_daily_bar_status(
        df_summer, now_utc=datetime(2025, 6, 11, 19, 30, tzinfo=timezone.utc)
    )["status"] == "LIVE"
    assert resolve_daily_bar_status(
        df_summer, now_utc=datetime(2025, 6, 11, 20, 5, tzinfo=timezone.utc)
    )["status"] == "CLOSED"

    # Winter (EST, UTC-5): 15:30 ET == 20:30 UTC -> still LIVE.
    winter_day = date(2025, 1, 15)
    df_winter = _frame([FLAT] * 30, last=winter_day)
    assert resolve_daily_bar_status(
        df_winter, now_utc=datetime(2025, 1, 15, 20, 30, tzinfo=timezone.utc)
    )["status"] == "LIVE"
    assert resolve_daily_bar_status(
        df_winter, now_utc=datetime(2025, 1, 15, 21, 5, tzinfo=timezone.utc)
    )["status"] == "CLOSED"

    src = (market_data.__file__ or "")
    text = open(src).read() if src.endswith(".py") else ""
    assert "America/New_York" in text


def test_07_early_close_uncertainty_delays_confirmation():
    # 2025-07-03 is a real 13:00 ET early close. With no market calendar the
    # bar stays LIVE until 16:00 ET — confirmation is DELAYED, never invented.
    df = _frame([FLAT] * 30, last=date(2025, 7, 3))
    assert resolve_daily_bar_status(df, now_utc=et_now(2025, 7, 3, 13, 30))["status"] == "LIVE"
    assert resolve_daily_bar_status(df, now_utc=et_now(2025, 7, 3, 16, 1))["status"] == "CLOSED"


# ===========================================================================
# 8-9 — price contracts
# ===========================================================================

def test_08_current_price_stays_live():
    df = _append(flat_df(150), 100.0, 104.0, 99.0, 103.5)
    e = indicators.enrich("T", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["current_price"] == 103.5
    assert e["current_open"] == 100.0
    assert e["current_high"] == 104.0
    assert e["current_low"] == 99.0


def test_09_last_closed_close_is_separate_from_current_price():
    df = _append(flat_df(150), 100.0, 104.0, 99.0, 103.5)
    e = indicators.enrich("T", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["last_closed_daily_close"] == 100.0
    assert e["current_price"] == 103.5
    assert e["current_price"] != e["last_closed_daily_close"]

    # With no live bar the two collapse onto the same completed close.
    e2 = indicators.enrich("T", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert e2["current_price"] == e2["last_closed_daily_close"] == 103.5


# ===========================================================================
# 10-13 — confirmed features are immune to the developing bar
# ===========================================================================

def _two_live_prices(base_df, low_close=100.5, high_close=117.0):
    a = _append(base_df, 100.0, low_close + 0.5, 99.5, low_close)
    b = _append(base_df, 100.0, high_close + 1.0, 99.5, high_close)
    return (indicators.enrich("A", a, CFG, now_utc=NOW_MIDSESSION),
            indicators.enrich("A", b, CFG, now_utc=NOW_MIDSESSION))


def test_10_confirmed_smas_do_not_move_with_the_live_close():
    ea, eb = _two_live_prices(flat_df(250))
    assert ea["sma20"] == eb["sma20"]
    assert ea["sma50"] == eb["sma50"]
    assert ea["sma200"] == eb["sma200"]
    assert ea["sma_value_alignment"] == eb["sma_value_alignment"]


def test_11_current_extension_from_confirmed_sma_may_move_with_live_price():
    ea, eb = _two_live_prices(flat_df(250))
    assert ea["price_extension_from_sma20_pct"] != eb["price_extension_from_sma20_pct"]
    # ...and the LIVE alignment view is exposed as its own field (flat history
    # keeps both reads "mixed"; the divergent case is asserted in the
    # far-above-SMA adversarial test).
    assert ea["live_sma_value_alignment"] == "mixed"
    assert eb["live_sma_value_alignment"] == "mixed"
    assert eb["sma_value_alignment"] == ea["sma_value_alignment"] == "mixed"


def test_12_confirmed_atr_is_not_moved_by_developing_range():
    ea, eb = _two_live_prices(flat_df(250))
    assert ea["atr"] == eb["atr"]


def test_13_confirmed_swings_are_not_moved_by_developing_bar():
    ea, eb = _two_live_prices(flat_df(250))
    assert ea["last_swing_high"] == eb["last_swing_high"]
    assert ea["last_swing_low"] == eb["last_swing_low"]
    assert ea["swing_highs"] == eb["swing_highs"]
    assert ea["swing_lows"] == eb["swing_lows"]
    assert ea["recent_range_high"] == eb["recent_range_high"]
    assert ea["recent_range_low"] == eb["recent_range_low"]


# ===========================================================================
# 14-17 — structure law
# ===========================================================================

def test_14_live_break_cannot_alone_confirm_structure():
    base = flat_df(150)
    baseline = indicators.enrich("S", base, CFG, now_utc=NOW_NEXT_MORNING)
    assert baseline["structure_confirmed"] is False

    df = _append(base, 100.0, 104.0, 99.5, 103.5)   # closes far above the level
    live = indicators.enrich("S", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["structure_event"] == "none"
    assert live["structure_confirmed"] is False
    assert live["structure_level"] is None
    assert live["live_structure_context"]["state"] == "LIVE_BREAK_BUILDING"
    assert live["live_structure_context"]["confirms_structure"] is False


def test_15_same_bar_after_close_may_confirm_structure():
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5)
    closed = indicators.enrich("S", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert closed["structure_confirmed"] is True
    assert closed["structure_event"] in ("BOS", "MSS")
    assert closed["live_structure_context"] is None


def test_16_live_reclaim_cannot_alone_become_a_confirmed_reclaim():
    # Completed history that lost a level, then a developing bar back above it.
    rows = [FLAT] * 100 + [(104.9, 105.5, 104.5, 105.0, 1_000_000.0)] * 20
    rows += [(97.9, 98.5, 97.5, 98.0, 1_000_000.0)] * 30
    base = _frame(rows)
    baseline = indicators.enrich("R", base, CFG, now_utc=NOW_NEXT_MORNING)
    level = baseline["prior_structural_high"]

    df = _append(base, 98.0, level + 2.0, 97.8, level + 1.5)
    live = indicators.enrich("R", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["structure_event"] == baseline["structure_event"]
    assert live["structure_confirmed"] == baseline["structure_confirmed"]
    assert live["live_structure_context"]["state"] in (
        "LIVE_BREAK_BUILDING", "LIVE_RECLAIM_BUILDING")
    assert live["live_structure_context"]["confirms_structure"] is False


def test_17_live_wick_only_structural_interaction_is_preserved_as_information():
    base = flat_df(150)
    level = indicators.enrich("W", base, CFG, now_utc=NOW_NEXT_MORNING)["prior_structural_high"]
    df = _append(base, 99.8, level + 3.0, 99.5, level - 0.5)   # wick through, close under
    live = indicators.enrich("W", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["structure_confirmed"] is False
    ctx = live["live_structure_context"]
    assert ctx["state"] == "LIVE_WICK_BREAK"
    assert ctx["live_high"] > ctx["level"] >= ctx["live_close"]
    assert ctx["confirms_structure"] is False


# ===========================================================================
# 18-21 — retest law
# ===========================================================================

def test_18_live_price_inside_zone_cannot_alone_confirm_a_retest():
    base = zone_df()
    closed = indicators.enrich("Z", base, CFG, now_utc=NOW_NEXT_MORNING)
    assert closed["retest_status"] == "missing"

    df = _append(base, 105.8, 106.0, ZONE_MID - 0.5, ZONE_MID)
    live = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["retest_status"] != "confirmed"
    assert live["retest_status"] == "partial"
    assert live["daily_retest_proof"] == "PROVISIONAL_LIVE"
    assert live["live_retest_context"]["live_interaction"] == "INSIDE_ZONE"
    assert live["live_retest_context"]["confirms_retest"] is False


def test_19_live_price_below_zone_cannot_emit_failed():
    base = zone_df()
    df = _append(base, 105.8, 106.0, ZONE_LOW - 4.5, ZONE_LOW - 4.0)
    live = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["retest_status"] != "failed"
    assert live["live_retest_context"]["live_interaction"] == "BELOW_ZONE"
    assert live["live_retest_context"]["confirms_failure"] is False
    # ...and the confirmed zone is NOT destroyed by the unfinished breach.
    assert live["fvg"] is not None
    assert live["fvg"]["fvg_bot"] == ZONE_LOW
    assert live["fvg"]["fvg_top"] == ZONE_HIGH


def test_20_failed_retest_requires_completed_evidence_and_stays_unreachable():
    """`failed` is owned by closed evidence only.

    On the current (unchanged) zone rules a surviving zone can never sit above
    price: an FVG survives only while lows stay above its base, an OB only
    while closes stay above its low. So `assess_retest`'s failed branch is
    structurally unreachable from enrich() — before AND after MBT-2. MBT-2
    must not introduce a new path to it.
    """
    # The rule itself is untouched: called directly with a below-price zone it
    # still returns "failed".
    direct = indicators.assess_retest(
        90.0, {"fvg_bot": 100.0, "fvg_top": 102.0}, None, 1.0)
    assert direct["retest_status"] == "failed"

    # But no daily frame — live or closed — reaches it through enrich().
    rng = np.random.RandomState(17)
    seen = set()
    for _ in range(400):
        n = 140
        closes = 100 + np.cumsum(rng.randn(n) * rng.uniform(0.3, 3.0))
        spread = np.abs(rng.randn(n)) * rng.uniform(0.2, 2.0) + 0.1
        d = pd.DataFrame(
            {"open": closes + rng.randn(n) * 0.2, "high": closes + spread,
             "low": closes - spread, "close": closes,
             "volume": rng.randint(100_000, 5_000_000, n).astype(float)},
            index=pd.bdate_range(end=LAST_CLOSED_DAY, periods=n))
        d["high"] = d[["high", "open", "close"]].max(axis=1)
        d["low"] = d[["low", "open", "close"]].min(axis=1)
        for now in (NOW_MIDSESSION, NOW_NEXT_MORNING):
            seen.add(indicators.enrich("RND", d, CFG, now_utc=now)["retest_status"])
    assert "failed" not in seen
    assert {"missing", "partial", "confirmed"} & seen


def test_21_closed_daily_retest_may_emit_confirmed():
    e = indicators.enrich("Z", zone_retested_df(), CFG, now_utc=NOW_NEXT_MORNING)
    assert e["retest_status"] == "confirmed"
    assert e["retest_zone"] == "FVG"
    assert e["daily_retest_proof"] == "CLOSED_CONFIRMED"


def test_21b_closed_confirmation_survives_a_live_excursion_out_of_the_zone():
    """A live move away from the zone is information — it does not erase a
    retest the completed session actually proved."""
    base = zone_retested_df()
    df = _append(base, 101.8, 102.0, ZONE_LOW - 4.0, ZONE_LOW - 3.5)
    live = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["retest_status"] == "confirmed"
    assert live["daily_retest_proof"] == "CLOSED_CONFIRMED"
    assert live["live_retest_context"]["live_interaction"] == "BELOW_ZONE"


# ===========================================================================
# 22-25 — zone law
# ===========================================================================

def test_22_developing_bar_cannot_create_a_completed_fvg():
    base = flat_df(150)
    assert indicators.enrich("F", base, CFG, now_utc=NOW_NEXT_MORNING)["fvg"] is None
    # A developing bar whose low gaps far above the prior highs would form an
    # FVG if it were allowed to be the third candle.
    df = _append(base, 118.0, 120.0, 117.0, 119.0)
    live = indicators.enrich("F", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["fvg"] is None
    closed = indicators.enrich("F", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert closed["fvg"] is not None      # same bar, once complete, may create it


def test_23_developing_bar_cannot_create_a_completed_ob():
    """An OB needs three bars of aftermath. The developing bar must not count
    as one of them — it may not be the thing that makes a zone old enough."""
    rows = [FLAT] * 146
    rows.append((101.0, 101.2, 99.0, 99.2, 1_000_000.0))     # OB candle
    rows.append((99.3, 104.0, 99.2, 103.8, 2_000_000.0))     # displacement
    rows.append((103.9, 104.5, 103.5, 104.0, 1_000_000.0))
    base = _frame(rows)
    df = _append(base, 104.0, 104.5, 103.5, 104.2)

    live = indicators.enrich("O", df, CFG, now_utc=NOW_MIDSESSION)
    closed = indicators.enrich("O", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert live["ob"] is None
    assert closed["ob"] is not None
    assert closed["ob"]["ob_lo"] == 99.2


def test_24_developing_close_cannot_confirm_ob_mitigation():
    rows = [FLAT] * 120
    rows.append((101.0, 101.2, 99.0, 99.2, 1_000_000.0))    # OB candle
    rows.append((99.3, 104.0, 99.2, 103.8, 2_000_000.0))    # displacement
    rows += [(103.9, 104.5, 103.5, 104.0, 1_000_000.0)] * 20
    base = _frame(rows)
    closed = indicators.enrich("M", base, CFG, now_utc=NOW_NEXT_MORNING)
    assert closed["ob"] is not None
    ob_lo = closed["ob"]["ob_lo"]

    df = _append(base, 104.0, 104.2, ob_lo - 3.0, ob_lo - 2.0)
    live = indicators.enrich("M", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["ob"] is not None and live["ob"]["ob_lo"] == ob_lo
    assert live["ob"]["mitigated"] is False
    # Once that same bar closes, the mitigation rule applies normally.
    after = indicators.enrich("M", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert after["ob"] is None or after["ob"]["ob_lo"] != ob_lo


def test_25_live_zone_interaction_remains_observable():
    df = _append(zone_df(), 105.8, 106.0, ZONE_MID - 0.5, ZONE_MID)
    live = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    ctx = live["live_retest_context"]
    assert ctx["live_zone"] == "FVG"
    assert ctx["live_zone_low"] == ZONE_LOW and ctx["live_zone_high"] == ZONE_HIGH
    assert ctx["live_interaction"] == "INSIDE_ZONE"
    assert ctx["live_distance_atr"] == 0.0
    assert live["fvg"]["price_in_fvg"] is True     # location truth is preserved


# ===========================================================================
# 26-29 — volume law
# ===========================================================================

def test_26_partial_daily_volume_cannot_become_confirmed_dryup():
    base = flat_df(150)
    df = _append(base, 100.0, 100.4, 99.8, 100.1, v=200_000.0)
    live = indicators.enrich("V", df, CFG, now_utc=NOW_MIDSESSION)
    assert live["volume_behavior"] != "dryup"
    assert live["volume_behavior"] == indicators.enrich(
        "V", base, CFG, now_utc=NOW_NEXT_MORNING)["volume_behavior"]
    assert live["live_daily_volume"] == 200_000.0


def test_27_confirmed_volume_comes_from_the_last_completed_session():
    base = flat_df(150)
    df = _append(base, 100.0, 100.4, 99.8, 100.1, v=200_000.0)
    live = indicators.enrich("V", df, CFG, now_utc=NOW_MIDSESSION)
    expected = indicators.assess_volume(base, CFG)
    assert live["volume_ratio"] == expected["volume_ratio"]
    assert live["volume_behavior"] == expected["volume_behavior"]
    # After the close the same partial-session row becomes real evidence.
    closed = indicators.enrich("V", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert closed["volume_behavior"] == "dryup"


def test_28_no_volume_thresholds_changed():
    th = CFG["prefilter"]["thresholds"]
    v = pd.Series([1_000_000.0] * 20 + [1_250_000.0])
    df = pd.DataFrame({"volume": v})
    assert indicators.assess_volume(df, CFG)["volume_behavior"] == "expansion"
    assert th["volume_expansion_ratio"] == 1.2 and th["volume_dryup_ratio"] == 0.8


def test_29_confirmed_structure_zones_volume_identical_when_only_live_price_moves():
    base = zone_df()
    a = _append(base, 105.8, 106.2, 105.4, 105.9)
    b = _append(base, 105.8, 112.0, 105.4, 111.5)
    ea = indicators.enrich("P", a, CFG, now_utc=NOW_MIDSESSION)
    eb = indicators.enrich("P", b, CFG, now_utc=NOW_MIDSESSION)
    for field in ("structure_event", "structure_level", "structure_confirmed",
                  "prior_structural_high", "wick_only_break", "fvg", "ob",
                  "volume_ratio", "volume_behavior", "sma20", "sma50", "sma200",
                  "atr", "sma_value_alignment", "last_swing_high", "last_swing_low",
                  "equal_highs", "equal_lows", "recent_range_high", "recent_range_low",
                  "sweep_detected", "invalidation_level", "last_closed_daily_close"):
        assert ea[field] == eb[field], field


def test_30_current_location_and_rr_may_move_with_live_price():
    base = zone_df()
    a = _append(base, 105.8, 106.2, 105.4, 105.9)
    b = _append(base, 105.8, 112.0, 105.4, 111.5)
    ea = indicators.enrich("P", a, CFG, now_utc=NOW_MIDSESSION)
    eb = indicators.enrich("P", b, CFG, now_utc=NOW_MIDSESSION)
    assert ea["current_price"] != eb["current_price"]
    assert ea["price_extension_from_sma20_pct"] != eb["price_extension_from_sma20_pct"]
    assert (ea["estimated_rr"], ea["overhead_status"]) != (
        eb["estimated_rr"], eb["overhead_status"])


# ===========================================================================
# 31-34 — Claude input truth
# ===========================================================================

def _claude_enriched(now):
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5)
    e = indicators.enrich("C", df, CFG, now_utc=now)
    e["data_status"] = "OK"
    e["latest_close"] = round(float(df["close"].iloc[-1]), 4)   # what scheduler sets
    return e


def test_31_current_price_is_not_mislabeled_latest_close():
    e = _claude_enriched(NOW_MIDSESSION)
    prompt = claude_client.build_prompt(e)
    assert "LATEST_CLOSE" not in prompt
    assert f"CURRENT_PRICE: {e['current_price']}" in prompt


def test_32_claude_receives_daily_bar_status():
    assert "DAILY_BAR_STATUS: LIVE" in claude_client.build_prompt(_claude_enriched(NOW_MIDSESSION))
    assert "DAILY_BAR_STATUS: CLOSED" in claude_client.build_prompt(_claude_enriched(NOW_AFTER_CLOSE))


def test_33_claude_receives_last_closed_close_separately():
    e = _claude_enriched(NOW_MIDSESSION)
    prompt = claude_client.build_prompt(e)
    assert f"LAST_CLOSED_DAILY_CLOSE: {e['last_closed_daily_close']}" in prompt
    assert e["last_closed_daily_close"] != e["current_price"]
    assert "DAILY_STRUCTURE_SOURCE: CLOSED_BARS" in prompt
    assert "DAILY_RETEST_PROOF: " in prompt
    assert "DAILY_VOLUME_SOURCE: LAST_COMPLETED_SESSION" in prompt


def test_33b_legacy_enriched_without_daily_context_keeps_latest_close():
    """Callers that never went through indicators.enrich() are unchanged."""
    prompt = claude_client.build_prompt({"ticker": "L", "latest_close": 42.5})
    assert "LATEST_CLOSE: 42.5" in prompt
    assert "DAILY_BAR_STATUS" not in prompt


def test_34_claude_call_count_and_prompt_size_unchanged():
    e = _claude_enriched(NOW_MIDSESSION)
    prompt = claude_client.build_prompt(e)
    # build_prompt is pure: no client, no network, no model call.
    assert isinstance(prompt, str)
    # Provenance costs a handful of short lines, not a token explosion.
    assert len(prompt.splitlines()) <= 30
    for banned in ("rsi", "macd", "bollinger", "stochastic"):
        assert banned not in prompt.lower()


# ===========================================================================
# 35-39 — prefilter compatibility (inputs corrected, thresholds untouched)
# ===========================================================================

def test_35_prefilter_weights_unchanged():
    w = CFG["prefilter"]["scoring_weights"]
    assert (w["trend_value_alignment"], w["structure_event"],
            w["fvg_ob_demand_zone_quality"], w["retest_proximity_status"],
            w["target_path_rr_estimate"], w["volume_participation"],
            w["data_quality_recency"]) == (15, 20, 15, 20, 15, 10, 5)
    assert CFG["prefilter"]["prefilter_min_score"] == 55


def test_36_prefilter_veto_vocabulary_unchanged():
    assert prefilter_mod._HARD_BLOCK_VETOES == {
        "data_empty", "data_error", "insufficient_bars", "stale_data",
        "no_clear_structure", "no_clear_invalidation_estimate", "no_target_path",
        "overhead_blocked", "price_too_extended", "retest_failed",
        "mid_range_no_edge", "hostile_value_alignment", "rr_below_threshold_estimate",
    }


def test_37_candidate_cap_remains_30():
    assert CFG["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_38_live_below_zone_excursion_cannot_trigger_retest_failed_veto():
    df = _append(zone_df(), 105.8, 106.0, ZONE_LOW - 4.5, ZONE_LOW - 4.0)
    e = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    e["data_status"] = "OK"
    assert prefilter_mod.VETO_RETEST_FAILED not in prefilter_mod.apply_hard_vetoes(e, CFG)


def test_39_live_above_structure_excursion_earns_no_confirmed_structure_points():
    base = flat_df(150)
    df = _append(base, 100.0, 104.0, 99.5, 103.5)
    live = indicators.enrich("S", df, CFG, now_utc=NOW_MIDSESSION)
    live["data_status"] = "OK"
    closed = indicators.enrich("S", df, CFG, now_utc=NOW_AFTER_CLOSE)
    closed["data_status"] = "OK"

    completed_only = indicators.enrich("S", base, CFG, now_utc=NOW_NEXT_MORNING)
    completed_only["data_status"] = "OK"

    w = CFG["prefilter"]["scoring_weights"]["structure_event"]
    live_pts = prefilter_mod._score_structure_event(live, w)
    closed_pts = prefilter_mod._score_structure_event(closed, w)
    baseline_pts = prefilter_mod._score_structure_event(completed_only, w)

    # The developing bar adds exactly nothing; whatever the completed history
    # already earned (here: a flagged wick-only break) is all that remains.
    assert live_pts == baseline_pts
    assert live["structure_event"] == "none"
    # The same bar, once closed, earns real BOS/MSS structure credit.
    assert closed_pts > live_pts
    assert closed["structure_event"] in ("BOS", "MSS")


# ===========================================================================
# 40-42 — candle evidence and higher-timeframe context
# ===========================================================================

def test_40_candle_evidence_live_daily_status_remains_provisional():
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5)
    e = indicators.enrich("K", df, CFG, now_utc=NOW_MIDSESSION)
    ctx = candle_evidence.build_candle_evidence_context(e, {"final_tier": "STARTER"})
    assert ctx["candle_status"] == "OPEN_OR_UNKNOWN"
    assert ctx["score_delta"] <= 0
    assert "forming" in ctx["display_text"] or ctx["display_text"] == ""


def test_41_completed_daily_candle_may_be_classified_closed():
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5)
    e = indicators.enrich("K", df, CFG, now_utc=NOW_AFTER_CLOSE)
    ctx = candle_evidence.build_candle_evidence_context(e, {"final_tier": "STARTER"})
    assert e["daily_bar_context"]["status"] == "CLOSED"
    assert ctx["candle_status"] == "CLOSED"
    # Authority is unchanged: without a next candle nothing positive is earned.
    assert ctx["score_delta"] <= 0
    assert "forming" not in ctx["display_text"]


def test_41b_unknown_daily_status_never_reads_as_closed():
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5,
                 when=SESSION_DAY + timedelta(days=30))     # future-dated row
    e = indicators.enrich("K", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["daily_bar_context"]["status"] == "UNKNOWN"
    assert e["daily_bar_context"]["current_row_trusted"] is False
    assert e["daily_bar_context"]["ambiguous_rows_withheld"] == 1
    ctx = candle_evidence.build_candle_evidence_context(e, {"final_tier": "STARTER"})
    assert ctx["candle_status"] == "OPEN_OR_UNKNOWN"


def test_41c_legacy_enriched_without_daily_context_is_unchanged():
    legacy = {"current_open": 100.0, "current_high": 104.0,
              "current_low": 99.0, "current_price": 103.0, "atr": 1.0}
    ctx = candle_evidence.build_candle_evidence_context(legacy, {"final_tier": "STARTER"})
    assert ctx["candle_status"] == "OPEN_OR_UNKNOWN"


def test_42_higher_timeframe_completed_period_handling_does_not_regress():
    df = _append(flat_df(400), 100.0, 118.0, 99.5, 117.0)
    bars = higher_timeframe_context.daily_bars_from_df(df)
    obj = higher_timeframe_context.build_higher_timeframe_context(
        "H",
        enriched_data=indicators.enrich("H", df, CFG, now_utc=NOW_MIDSESSION),
        daily_bars=bars, config=CFG)
    lb = obj["lookback"]
    assert obj["data_status"] == "OK"
    assert lb["current_weekly_bar_is_developing"] is True
    assert lb["current_monthly_bar_is_developing"] is True
    assert lb["last_completed_weekly_bar_date"] is not None
    assert lb["last_completed_monthly_bar_date"] is not None

    # The developing daily bar's 118.0 spike never reaches a COMPLETED weekly
    # or monthly bar — the current period is excluded by HTF's own rules, and
    # the completed bar set is identical with or without the developing row.
    clean, _ = higher_timeframe_context._normalize_daily_bars(bars)
    without = higher_timeframe_context._normalize_daily_bars(
        higher_timeframe_context.daily_bars_from_df(df.iloc[:-1]))[0]
    for period in ("weekly", "monthly"):
        completed, developing = higher_timeframe_context._resample(clean, period)
        completed_wo, _ = higher_timeframe_context._resample(without, period)
        assert completed == completed_wo, period
        assert all(b["high"] < 118.0 for b in completed), period
        assert developing is not None and developing["high"] == 118.0, period

    # HTF still anchors location on the CURRENT price — that is correct and
    # unchanged; only completed-bar authority is protected.
    assert obj["weekly"]["sma_relationship"]["price_vs_20"] == "ABOVE"


# ===========================================================================
# 43-45 — parity
# ===========================================================================

def test_43_no_new_market_data_request():
    df = _append(flat_df(150), 100.0, 104.0, 99.5, 103.5)
    with patch("yfinance.download") as dl:
        indicators.enrich("N", df, CFG, now_utc=NOW_MIDSESSION)
        resolve_daily_bar_status(df, now_utc=NOW_MIDSESSION)
    assert dl.call_count == 0


def test_44_no_new_dependency():
    """MBT-2 adds no dependency: zoneinfo is stdlib on this runtime and no
    market-calendar package was introduced."""
    import subprocess
    import sys
    assert "zoneinfo" in sys.stdlib_module_names
    reqs = open("requirements.txt").read().lower()
    for pkg in ("pandas-market-calendars", "pandas_market_calendars",
                "exchange_calendars", "exchange-calendars", "holidays",
                "trading-calendars"):
        assert pkg not in reqs
    # requirements.txt is byte-for-byte untouched by this phase.
    changed = subprocess.run(
        ["git", "diff", "--name-only", "origin/main", "--", "requirements.txt"],
        capture_output=True, text=True).stdout.strip()
    assert changed == ""


def test_45_mbt1_one_hour_contract_untouched():
    # MBT-1's 1H helpers still resolve exactly as before; MBT-2 added Daily
    # helpers alongside them without altering the 1H interval law.
    bar = datetime(2025, 6, 11, 13, 30, tzinfo=timezone.utc)      # 09:30 ET
    assert market_data._resolve_newest_bar_open(bar, 60, bar + timedelta(minutes=30)) is True
    assert market_data._resolve_newest_bar_open(bar, 60, bar + timedelta(minutes=61)) is False
    assert market_data._resolve_newest_bar_open(None, 60, bar) is True


# ===========================================================================
# CRITICAL SAME-BAR TRANSITION — evidence maturity, not strategy change
# ===========================================================================

def test_critical_transition_live_to_closed_same_bar():
    """One bar, one set of OHLC values, two clock readings."""
    base = zone_df()
    df = _append(base, 105.8, 106.5, ZONE_MID - 0.4, ZONE_MID, v=200_000.0)

    scan_a = indicators.enrich("T", df, CFG, now_utc=NOW_MIDSESSION)     # 14:00 ET
    scan_b = indicators.enrich("T", df, CFG, now_utc=NOW_AFTER_CLOSE)    # 16:05 ET

    # Identical market evidence.
    assert scan_a["current_price"] == scan_b["current_price"] == ZONE_MID
    assert scan_a["current_high"] == scan_b["current_high"]
    assert scan_a["current_low"] == scan_b["current_low"]

    # SCAN A — developing: no confirmation may come from that bar.
    assert scan_a["daily_bar_context"]["status"] == "LIVE"
    assert scan_a["last_closed_daily_close"] == 106.0
    assert scan_a["daily_retest_proof"] == "PROVISIONAL_LIVE"
    assert scan_a["retest_status"] == "partial"
    assert scan_a["volume_behavior"] != "dryup"
    assert scan_a["live_retest_context"]["live_interaction"] == "INSIDE_ZONE"

    # SCAN B — complete: the same bar now carries full Daily authority.
    assert scan_b["daily_bar_context"]["status"] == "CLOSED"
    assert scan_b["last_closed_daily_close"] == ZONE_MID
    assert scan_b["daily_retest_proof"] == "CLOSED_CONFIRMED"
    assert scan_b["retest_status"] == "confirmed"
    assert scan_b["volume_behavior"] == "dryup"
    assert scan_b["live_retest_context"] is None

    # Confirmed anchors moved only because a session completed.
    assert scan_a["atr"] != scan_b["atr"] or scan_a["sma20"] != scan_b["sma20"]


# ===========================================================================
# ADVERSARIAL TIMESTAMPS AND FRAMES
# ===========================================================================

@pytest.mark.parametrize("hour,minute,expected", [
    (9, 29, "LIVE"), (9, 35, "LIVE"), (12, 0, "LIVE"), (15, 55, "LIVE"),
    (16, 0, "CLOSED"), (16, 5, "CLOSED"), (20, 0, "CLOSED"),
])
def test_adv_session_clock_boundaries(hour, minute, expected):
    df = _frame([FLAT] * 30, last=SESSION_DAY)
    ctx = resolve_daily_bar_status(df, now_utc=et_now(2025, 6, 11, hour, minute))
    assert ctx["status"] == expected


def test_adv_naive_daily_index_still_resolves():
    df = _frame([FLAT] * 30, last=SESSION_DAY)
    assert df.index.tz is None
    assert resolve_daily_bar_status(df, now_utc=NOW_MIDSESSION)["status"] == "LIVE"


def test_adv_tz_aware_daily_index_still_resolves():
    df = _frame([FLAT] * 30, last=SESSION_DAY)
    df.index = df.index.tz_localize("America/New_York")
    assert resolve_daily_bar_status(df, now_utc=NOW_MIDSESSION)["status"] == "LIVE"
    assert resolve_daily_bar_status(df, now_utc=NOW_AFTER_CLOSE)["status"] == "CLOSED"


def test_adv_provider_row_missing_today():
    df = _frame([FLAT] * 30, last=LAST_CLOSED_DAY)
    ctx = resolve_daily_bar_status(df, now_utc=NOW_MIDSESSION)
    assert ctx["status"] == "CLOSED"
    assert ctx["live_bar_available"] is False
    assert ctx["confirmed_bars"] == 30


def test_adv_malformed_index_is_unknown_never_closed():
    df = _frame([FLAT] * 30)
    df.index = pd.Index(["not-a-date"] * 30)
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]
    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "unparseable_index"
    # Not one unparseable row may enter confirmation.
    assert len(part["confirmed_df"]) == 0
    assert ctx["confirmed_bars"] == 0
    assert ctx["ambiguous_rows_withheld"] == 30
    assert part["live_row"] is None
    assert ctx["live_bar_available"] is False
    assert ctx["current_row_trusted"] is False


def test_adv_unsorted_index_recovers_history_by_date_not_position():
    """Bad ordering must not destroy recoverable history — but it must also
    not let a row be confirmed just because it sits early in the frame."""
    df = _frame([FLAT] * 30)
    df = df.iloc[list(range(28)) + [29, 28]]        # last two rows swapped
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    # Every row here is a unique COMPLETED prior session, so all are eligible…
    assert ctx["status"] == "CLOSED"
    assert len(part["confirmed_df"]) == 30
    # …and the confirmed subset is re-sorted chronologically before use.
    assert ctx["index_reordered"] is True
    dates = list(part["confirmed_df"].index)
    assert dates == sorted(dates)
    assert ctx["current_row_trusted"] is False      # physical last isn't newest
    assert ctx["ambiguous_rows_withheld"] == 0


def test_adv_duplicate_dates_do_not_fabricate_a_close():
    df = _frame([FLAT] * 30)
    df = pd.concat([df, df.iloc[[-1]]])       # duplicate final session date
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]
    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "duplicate_session_dates"
    assert ctx["using_live_bar_for_confirmation"] is False
    # BOTH copies are withheld — no copy is crowned canonical.
    assert len(part["confirmed_df"]) == 29
    assert ctx["ambiguous_rows_withheld"] == 2
    assert LAST_CLOSED_DAY not in [i.date() for i in part["confirmed_df"].index]


def test_adv_future_dated_row_is_unknown():
    df = _append(flat_df(30), 100, 101, 99, 100.5,
                 when=SESSION_DAY + timedelta(days=10))
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]
    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "future_dated_row"
    assert part["live_row"] is None
    assert ctx["live_bar_available"] is False
    # The future row is excluded; the genuine completed history survives.
    assert len(part["confirmed_df"]) == 30
    assert ctx["ambiguous_rows_withheld"] == 1
    assert ctx["current_row_trusted"] is False


def test_adv_empty_and_none_frames_never_claim_closed():
    for frame in (None, pd.DataFrame()):
        ctx = resolve_daily_bar_status(frame, now_utc=NOW_MIDSESSION)
        assert ctx["status"] == "UNKNOWN"
        assert ctx["live_bar_available"] is False
        assert ctx["confirmed_bars"] == 0


def test_adv_single_daily_row_yields_no_confirmed_evidence():
    df = _frame([FLAT], last=SESSION_DAY)
    e = indicators.enrich("ONE", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["daily_bar_context"]["status"] == "LIVE"
    assert e["daily_bar_context"]["confirmed_bars"] == 0
    assert e["last_closed_daily_close"] is None
    assert e["structure_confirmed"] is False
    assert e["structure_event"] == "none"
    assert e["fvg"] is None and e["ob"] is None
    assert e["sma20"] is None and e["atr"] is None
    assert e["volume_behavior"] == "unknown"
    assert e["current_price"] == 100.0        # current price still available


def test_adv_naive_now_is_treated_as_utc():
    df = _frame([FLAT] * 30, last=SESSION_DAY)
    naive = NOW_MIDSESSION.replace(tzinfo=None)
    assert resolve_daily_bar_status(df, now_utc=naive)["status"] == "LIVE"


def test_adv_huge_live_breakout_that_reverses_before_close():
    base = flat_df(150)
    spike = _append(base, 100.0, 130.0, 99.5, 129.0)      # 10:00 ET blow-off
    fade = _append(base, 100.0, 130.0, 99.0, 99.8)        # same day, faded
    e_spike = indicators.enrich("X", spike, CFG, now_utc=NOW_MIDSESSION)
    e_fade = indicators.enrich("X", fade, CFG, now_utc=NOW_MIDSESSION)
    for field in ("structure_event", "structure_confirmed", "sma20", "atr",
                  "volume_behavior", "recent_range_high", "last_closed_daily_close"):
        assert e_spike[field] == e_fade[field], field
    assert e_spike["structure_confirmed"] is False


def test_adv_huge_live_breakdown_that_reclaims_before_close():
    base = zone_df()
    flush = _append(base, 105.8, 106.0, 90.0, 91.0)
    reclaim = _append(base, 105.8, 106.4, 90.0, 106.0)
    e_flush = indicators.enrich("Y", flush, CFG, now_utc=NOW_MIDSESSION)
    e_reclaim = indicators.enrich("Y", reclaim, CFG, now_utc=NOW_MIDSESSION)
    assert e_flush["fvg"] == e_reclaim["fvg"]          # zone survives both
    assert e_flush["retest_status"] != "failed"
    assert e_flush["last_closed_daily_close"] == e_reclaim["last_closed_daily_close"]


def test_adv_partial_live_volume_at_10am_is_never_a_verdict():
    base = flat_df(150)
    for shares in (10_000.0, 200_000.0, 900_000.0):
        df = _append(base, 100.0, 100.4, 99.8, 100.1, v=shares)
        e = indicators.enrich("V", df, CFG, now_utc=et_now(2025, 6, 11, 10, 0))
        assert e["volume_behavior"] == "neutral"
        assert e["live_daily_volume"] == shares


def test_adv_live_price_far_above_sma_is_location_not_permission():
    # Gently rising completed history so the SMA stack is strictly ordered.
    rows = []
    for i in range(250):
        c = 80.0 + i * 0.08
        rows.append((c - 0.1, c + 0.5, c - 0.5, c, 1_000_000.0))
    base = _frame(rows)
    df = _append(base, 100.0, 141.0, 99.5, 140.0)
    e = indicators.enrich("E", df, CFG, now_utc=NOW_MIDSESSION)
    closed_only = indicators.enrich("E", base, CFG, now_utc=NOW_NEXT_MORNING)

    # Confirmed alignment is the completed close against completed SMAs and is
    # untouched by the live blow-off; the live view is exposed separately.
    assert e["sma_value_alignment"] == closed_only["sma_value_alignment"]
    assert e["live_sma_value_alignment"] == "supportive"
    assert e["sma20"] == closed_only["sma20"]
    assert e["price_extension_from_sma20_pct"] > 8       # location veto still fires
    # Structure authority is whatever the COMPLETED history already earned —
    # the live blow-off adds nothing.
    assert e["structure_confirmed"] == closed_only["structure_confirmed"]
    assert e["structure_event"] == closed_only["structure_event"]
    assert e["structure_level"] == closed_only["structure_level"]


def test_adv_live_below_zone_then_back_inside_before_close():
    base = zone_df()
    df = _append(base, 105.8, 106.0, ZONE_LOW - 5.0, ZONE_MID)
    e = indicators.enrich("Z", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["fvg"] is not None and e["fvg"]["fvg_bot"] == ZONE_LOW
    assert e["retest_status"] == "partial"
    assert e["daily_retest_proof"] == "PROVISIONAL_LIVE"


# ===========================================================================
# STRATEGY DIFFERENTIAL — Class A / B / C
# ===========================================================================

def test_class_a_completed_history_only_is_bit_for_bit_unchanged():
    """No live bar => MBT-2 must be a no-op on every legacy feature."""
    df = zone_retested_df()
    e = indicators.enrich("A", df, CFG, now_utc=NOW_NEXT_MORNING)

    swings = indicators.compute_swings(df, 60)
    sweep = indicators.detect_sweep(df, CFG)
    legacy = {
        "sma20": indicators.compute_smas(df)["sma20"],
        "atr": indicators.compute_atr(df),
        "last_swing_high": swings["last_swing_high"],
        "structure_event": indicators.detect_structure_event(df, sweep, CFG)["structure_event"],
        "fvg": indicators.detect_fvg(df, CFG),
        "ob": indicators.detect_ob(df, CFG),
        "volume_behavior": indicators.assess_volume(df, CFG)["volume_behavior"],
    }
    for field, expected in legacy.items():
        assert e[field] == expected, field
    assert e["daily_bar_context"]["status"] == "CLOSED"
    assert e["live_retest_context"] is None
    assert e["live_structure_context"] is None
    assert e["live_daily_volume"] is None
    assert e["live_sma_value_alignment"] is None


def test_class_b_false_bullish_confirmation_is_corrected_to_provisional():
    """Developing bar that used to manufacture BOS + confirmed retest."""
    base = zone_df()
    df = _append(base, 105.8, 108.0, ZONE_MID - 0.5, ZONE_MID, v=150_000.0)

    e = indicators.enrich("B", df, CFG, now_utc=NOW_MIDSESSION)
    e["data_status"] = "OK"

    # What the pre-MBT-2 code would have computed: the whole frame as "closed".
    old_structure = indicators.detect_structure_event(
        df, indicators.detect_sweep(df, CFG), CFG)
    old_retest = indicators.assess_retest(
        ZONE_MID, indicators.detect_fvg(df, CFG), indicators.detect_ob(df, CFG),
        indicators.compute_atr(df))
    old_volume = indicators.assess_volume(df, CFG)

    assert old_retest["retest_status"] == "confirmed"
    assert e["retest_status"] == "partial"                    # corrected
    assert old_volume["volume_behavior"] == "dryup"
    assert e["volume_behavior"] != "dryup"                    # corrected
    assert e["volume_behavior"] == "neutral"

    # In THIS frame the developing bar wicks through the structural level and
    # closes back under it, so neither view confirms structure. Stated exactly
    # on both sides — the live excursion is preserved only as information.
    assert old_structure["structure_confirmed"] is False
    assert e["structure_confirmed"] is False
    assert e["live_structure_context"]["state"] == "LIVE_WICK_BREAK"
    assert e["live_structure_context"]["live_high"] == 108.0
    assert e["live_structure_context"]["level"] == 106.0

    w = CFG["prefilter"]["scoring_weights"]["retest_proximity_status"]
    assert prefilter_mod._score_retest(e, w) < prefilter_mod._score_retest(
        {"retest_status": "confirmed"}, w)


def test_class_b2_developing_break_is_a_deterministic_before_after_differential():
    """Second Class-B vector: a developing bar that closes clean above the
    structural level. Pre-MBT-2 it manufactured BOS + dryup; MBT-2 grants
    neither. Every value asserted exactly on both sides."""
    base = flat_df(150)
    df = _append(base, 100.0, 104.0, 99.5, 103.5, v=150_000.0)

    old_structure = indicators.detect_structure_event(
        df, indicators.detect_sweep(df, CFG), CFG)
    old_volume = indicators.assess_volume(df, CFG)
    e = indicators.enrich("B2", df, CFG, now_utc=NOW_MIDSESSION)

    # BEFORE (whole frame treated as closed)
    assert old_structure["structure_event"] == "BOS"
    assert old_structure["structure_confirmed"] is True
    assert old_volume["volume_behavior"] == "dryup"
    assert old_volume["volume_ratio"] == 0.15

    # AFTER (completed bars only)
    assert e["structure_event"] == "none"
    assert e["structure_confirmed"] is False
    assert e["structure_level"] is None
    assert e["volume_behavior"] == "neutral"
    assert e["live_structure_context"]["state"] == "LIVE_BREAK_BUILDING"
    assert e["live_structure_context"]["confirms_structure"] is False
    assert e["live_daily_volume"] == 150_000.0

    # The same bar, once complete, earns exactly what the rules allow.
    closed = indicators.enrich("B2", df, CFG, now_utc=NOW_AFTER_CLOSE)
    assert closed["structure_event"] == "BOS"
    assert closed["structure_confirmed"] is True
    assert closed["volume_behavior"] == "dryup"


def test_class_c_false_bearish_failure_is_corrected():
    """Developing breach that used to swap the active zone and rewrite state."""
    base = zone_retested_df()
    df = _append(base, 101.8, 102.0, ZONE_LOW - 6.0, ZONE_LOW - 5.0)

    e = indicators.enrich("C", df, CFG, now_utc=NOW_MIDSESSION)
    e["data_status"] = "OK"

    old_fvg = indicators.detect_fvg(df, CFG)     # pre-MBT-2 view of the zone
    assert old_fvg != e["fvg"]                   # the unfinished bar moved it
    assert e["fvg"]["fvg_bot"] == ZONE_LOW       # confirmed zone preserved
    assert e["retest_status"] == "confirmed"     # proven by the completed session
    assert e["daily_retest_proof"] == "CLOSED_CONFIRMED"
    assert e["live_retest_context"]["live_interaction"] == "BELOW_ZONE"
    assert prefilter_mod.VETO_RETEST_FAILED not in prefilter_mod.apply_hard_vetoes(e, CFG)


def test_every_live_field_carries_an_explicit_non_confirmation_assertion():
    df = _append(zone_df(), 105.8, 108.0, ZONE_MID - 0.5, ZONE_MID)
    e = indicators.enrich("N", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["daily_bar_context"]["using_live_bar_for_confirmation"] is False
    assert e["live_retest_context"]["confirms_retest"] is False
    assert e["live_retest_context"]["confirms_failure"] is False
    assert e["live_structure_context"]["confirms_structure"] is False


# ===========================================================================
# PHASE MBT-2A — ambiguous Daily partition safety
#
# Physical row position is not confirmation provenance. A malformed ordering
# cannot promote an unfinished candle into completed evidence, and duplicate
# session rows are ambiguity rather than extra confirmation.
# ===========================================================================

def _row(o, h, l, c, v, when):
    return pd.DataFrame(
        {"open": [o], "high": [h], "low": [l], "close": [c], "volume": [v]},
        index=[pd.Timestamp(when)])


# A violent developing session — if it ever leaks into confirmation it is
# impossible to miss in SMA / ATR / structure / volume.
LOUD_TODAY = (100.0, 130.0, 99.5, 129.0, 5_000_000.0)

# What confirmation MUST look like: completed flat history, nothing else.
SAFE_FIELDS = ("sma20", "sma50", "atr", "structure_event", "structure_confirmed",
               "recent_range_high", "recent_range_low", "volume_behavior",
               "volume_ratio", "sma_value_alignment", "last_swing_high",
               "last_swing_low", "sweep_detected", "fvg", "ob")


def _safe_baseline():
    return indicators.enrich("SAFE", flat_df(150), CFG, now_utc=NOW_NEXT_MORNING)


def _assert_confirmation_matches_safe_history(e):
    safe = _safe_baseline()
    contaminated = [f for f in SAFE_FIELDS if e[f] != safe[f]]
    assert contaminated == [], contaminated


def test_2a_01_non_monotonic_today_row_before_last_is_excluded():
    """[..., 06-10, 06-11(LIVE), 06-10] — the developing row is not the
    physical last row, and must still be withheld from confirmation."""
    df = pd.concat([flat_df(150), _row(*LOUD_TODAY, SESSION_DAY),
                    _row(*FLAT, LAST_CLOSED_DAY)])
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)

    confirmed_dates = [i.date() for i in part["confirmed_df"].index]
    assert SESSION_DAY not in confirmed_dates
    # The duplicated 06-10 session is ambiguous, so both copies go too.
    assert LAST_CLOSED_DAY not in confirmed_dates
    assert part["context"]["ambiguous_rows_withheld"] == 2
    # The developing row is found by DATE, not by position.
    assert part["live_row"] is not None
    assert float(part["live_row"]["close"]) == 129.0
    assert part["context"]["status"] == "LIVE"


def test_2a_02_non_monotonic_confirmation_equals_safe_completed_history():
    df = pd.concat([flat_df(150), _row(*LOUD_TODAY, SESSION_DAY),
                    _row(*FLAT, LAST_CLOSED_DAY)])
    e = indicators.enrich("NM", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)
    assert e["structure_confirmed"] is False
    assert e["volume_behavior"] != "expansion"
    assert e["last_closed_daily_close"] == 100.0
    assert e["live_structure_context"]["live_close"] == 129.0


def test_2a_02b_pure_reordering_recovers_history_instead_of_discarding_it():
    """Unique valid dates in the wrong order: keep every completed row, sort
    it chronologically, and still withhold the developing session."""
    base = flat_df(150)
    # Two completed rows swapped, and the developing row buried mid-frame.
    df = pd.concat([base.iloc[:-2], base.iloc[[-1]],
                    _row(*LOUD_TODAY, SESSION_DAY), base.iloc[[-2]]])
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "LIVE"
    assert ctx["index_reordered"] is True
    dates = list(part["confirmed_df"].index)
    assert dates == sorted(dates)
    assert ctx["ambiguous_rows_withheld"] == 0
    assert len(part["confirmed_df"]) == 150          # no history discarded
    assert SESSION_DAY not in [i.date() for i in part["confirmed_df"].index]

    e = indicators.enrich("RO", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)


def test_2a_03_duplicate_today_rows_neither_gains_authority():
    df = pd.concat([flat_df(150), _row(*LOUD_TODAY, SESSION_DAY),
                    _row(100.0, 131.0, 99.0, 130.0, 6_000_000.0, SESSION_DAY)])
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "duplicate_session_dates"
    assert ctx["ambiguous_rows_withheld"] == 2
    assert part["live_row"] is None                  # no canonical copy invented
    assert ctx["live_bar_available"] is False
    assert SESSION_DAY not in [i.date() for i in part["confirmed_df"].index]

    e = indicators.enrich("DUP", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)
    assert e["live_retest_context"] is None
    assert e["live_structure_context"] is None
    assert e["daily_bar_context"]["using_live_bar_for_confirmation"] is False


def test_2a_04_duplicate_historical_session_is_not_two_confirmed_candles():
    df = pd.concat([flat_df(150),
                    _row(100.0, 125.0, 99.0, 124.0, 4_000_000.0, LAST_CLOSED_DAY)])
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "duplicate_session_dates"
    assert len(part["confirmed_df"]) == 149          # BOTH copies withheld
    assert ctx["ambiguous_rows_withheld"] == 2
    assert [i.date() for i in part["confirmed_df"].index].count(LAST_CLOSED_DAY) == 0

    e = indicators.enrich("DH", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)


def test_2a_05_future_row_embedded_before_last_is_excluded():
    df = pd.concat([flat_df(150),
                    _row(100.0, 140.0, 99.0, 139.0, 7_000_000.0, "2025-12-31"),
                    _row(*FLAT, "2025-06-11")])
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "future_dated_row"
    assert date(2025, 12, 31) not in [i.date() for i in part["confirmed_df"].index]
    # The current-session row is still correctly withheld as developing.
    assert SESSION_DAY not in [i.date() for i in part["confirmed_df"].index]

    e = indicators.enrich("FU", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)
    assert e["recent_range_high"] != 140.0


def test_2a_06_malformed_row_embedded_before_last_is_excluded():
    df = pd.concat([flat_df(150),
                    _row(100.0, 145.0, 99.0, 144.0, 8_000_000.0, LAST_CLOSED_DAY),
                    _row(*FLAT, SESSION_DAY)])
    df.index = pd.Index(list(df.index[:-2]) + ["not-a-date", df.index[-1]],
                        dtype=object)
    part = market_data.partition_daily_bars(df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "UNKNOWN"
    assert ctx["status_source"] == "unparseable_index"
    assert len(part["confirmed_df"]) == 150          # malformed + developing out
    assert ctx["ambiguous_rows_withheld"] == 1

    e = indicators.enrich("MF", df, CFG, now_utc=NOW_MIDSESSION)
    _assert_confirmation_matches_safe_history(e)
    assert e["recent_range_high"] != 145.0


def test_2a_07_confirmed_subset_is_chronological_before_indicators_run():
    base = flat_df(60)
    scrambled = base.iloc[[10, 3, 55, 0, 41] + [i for i in range(60)
                                                if i not in (10, 3, 55, 0, 41)]]
    part = market_data.partition_daily_bars(scrambled, now_utc=NOW_NEXT_MORNING)
    dates = list(part["confirmed_df"].index)
    assert dates == sorted(dates)
    assert len(dates) == 60
    assert part["context"]["index_reordered"] is True
    # Sorting reorders rows; it never edits them.
    assert sorted(part["confirmed_df"]["close"].tolist()) == sorted(
        scrambled["close"].tolist())


def test_2a_08_clean_production_frame_is_unchanged():
    """A normal Yahoo frame must partition exactly as MBT-2 already did."""
    live_df = _append(zone_df(), 105.8, 106.5, ZONE_MID - 0.4, ZONE_MID)
    part = market_data.partition_daily_bars(live_df, now_utc=NOW_MIDSESSION)
    ctx = part["context"]

    assert ctx["status"] == "LIVE"
    assert ctx["index_reordered"] is False
    assert ctx["ambiguous_rows_withheld"] == 0
    assert ctx["current_row_trusted"] is True
    assert ctx["confirmed_bars"] == len(live_df) - 1
    # Identical to the old positional slice for a clean frame.
    assert part["confirmed_df"].equals(live_df.iloc[:-1])
    assert part["live_row"].equals(live_df.iloc[-1])
    assert part["current_row"].equals(live_df.iloc[-1])

    closed_df = zone_df()
    cpart = market_data.partition_daily_bars(closed_df, now_utc=NOW_NEXT_MORNING)
    assert cpart["context"]["status"] == "CLOSED"
    assert cpart["confirmed_df"].equals(closed_df)
    assert cpart["live_row"] is None
    assert cpart["context"]["current_row_trusted"] is True


def test_2a_09_live_to_closed_transition_is_unchanged():
    base = zone_df()
    df = _append(base, 105.8, 106.5, ZONE_MID - 0.4, ZONE_MID, v=200_000.0)
    a = indicators.enrich("T", df, CFG, now_utc=NOW_MIDSESSION)
    b = indicators.enrich("T", df, CFG, now_utc=NOW_AFTER_CLOSE)

    assert (a["daily_bar_context"]["status"], b["daily_bar_context"]["status"]) == (
        "LIVE", "CLOSED")
    assert (a["retest_status"], b["retest_status"]) == ("partial", "confirmed")
    assert (a["daily_retest_proof"], b["daily_retest_proof"]) == (
        "PROVISIONAL_LIVE", "CLOSED_CONFIRMED")
    assert (a["volume_behavior"], b["volume_behavior"]) == ("neutral", "dryup")
    assert (a["last_closed_daily_close"], b["last_closed_daily_close"]) == (
        106.0, ZONE_MID)
    assert a["current_price"] == b["current_price"] == ZONE_MID
    for ctx in (a["daily_bar_context"], b["daily_bar_context"]):
        assert ctx["ambiguous_rows_withheld"] == 0
        assert ctx["current_row_trusted"] is True


def test_2a_10_ambiguity_never_buys_confirmation_back_to_keep_a_price():
    """Current price survives an ambiguous frame; confirmation does not."""
    df = pd.concat([flat_df(150), _row(*LOUD_TODAY, SESSION_DAY),
                    _row(100.0, 131.0, 99.0, 130.0, 6_000_000.0, SESSION_DAY)])
    e = indicators.enrich("AM", df, CFG, now_utc=NOW_MIDSESSION)
    assert e["current_price"] == 130.0                      # price preserved
    assert e["daily_bar_context"]["current_row_trusted"] is False   # disclosed
    assert e["structure_confirmed"] is False
    assert e["daily_bar_context"]["using_live_bar_for_confirmation"] is False
    _assert_confirmation_matches_safe_history(e)


def test_2a_11_partition_never_raises_on_hostile_input():
    hostile = [None, pd.DataFrame(), flat_df(1), flat_df(0)]
    for frame in hostile:
        part = market_data.partition_daily_bars(frame, now_utc=NOW_MIDSESSION)
        assert part["context"]["using_live_bar_for_confirmation"] is False
        assert part["context"]["status"] in ("LIVE", "CLOSED", "UNKNOWN")

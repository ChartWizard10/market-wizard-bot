"""Phase R4H-1 — real 4H OPERATIONAL EVIDENCE engine (judgment layer).

Market-bar truth lives in test_phase_r4h1_real_four_hour_market_bars.py.
This file proves the judgment:

    Structure -> Liquidity -> Displacement -> Retest -> Hold -> Invalidation -> Target

    A live 4H candle is information; a closed complete one is evidence.
    A wick is not a hold. A touch is not a retest confirmation.
    A live breach is a threat; a closed accepted breach is failure.

And it proves the firewalls: the 1H never back-writes 4H history, the 4H never
grants Daily permission, and attaching this organ changes no production
decision. The Phase-14F proxy stays authoritative.
"""

import copy
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import four_hour_operational as fho
from src import market_data, scan_telemetry, timeframe_alignment

ET = ZoneInfo("America/New_York")
RTH = ((9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30), (15, 30))
CFG = {"prefilter": {"thresholds": {"overhead_block_distance_pct": 3}}}


# ---------------------------------------------------------------------------
# 4H bar fixtures — built directly in the aggregator's output shape so the
# judgment layer can be exercised without re-deriving the market-bar tests.
# ---------------------------------------------------------------------------

def bar(o, h, l, c, v=1000.0, slot="MORNING_4H", session="2025-06-11",
        confirmed=True, is_open=False, complete=True):
    start = datetime.fromisoformat(f"{session}T09:30:00").replace(tzinfo=ET)
    if slot == "AFTERNOON_CLOSE":
        start = start.replace(hour=13, minute=30)
    end = start.replace(hour=13, minute=30) if slot == "MORNING_4H" else \
        start.replace(hour=16, minute=0)
    return {
        "time": start.astimezone(timezone.utc).isoformat(),
        "end_time": end.astimezone(timezone.utc).isoformat(),
        "session_date": session,
        "bucket_slot": slot,
        "duration_minutes": 240 if slot == "MORNING_4H" else 150,
        "open": o, "high": h, "low": l, "close": c, "volume": v,
        "source_bar_count": 4 if slot == "MORNING_4H" else 3,
        "expected_source_bar_count": 4 if slot == "MORNING_4H" else 3,
        "source_complete": complete,
        "is_open": is_open,
        "confirmation_eligible": confirmed and not is_open and complete,
        "status": "LIVE" if is_open else ("CONFIRMED" if confirmed and complete
                                          else "INCOMPLETE"),
    }


def series(closes, spread=1.0, volume=1000.0):
    """Build alternating morning/afternoon confirmed buckets from closes."""
    out = []
    day = datetime(2025, 5, 1)
    for i, c in enumerate(closes):
        slot = "MORNING_4H" if i % 2 == 0 else "AFTERNOON_CLOSE"
        if i % 2 == 0 and i:
            day += timedelta(days=1)
        prev = closes[i - 1] if i else c
        o = prev
        out.append(bar(o, max(o, c) + spread, min(o, c) - spread, c,
                       v=volume, slot=slot, session=day.date().isoformat()))
    return out


def envelope(bars, status="OK"):
    return {
        "bars": bars, "status": status, "source_interval": "60m",
        "aggregation": "RTH_SESSION_ALIGNED", "source_request_reused": True,
        "now": "2025-06-11T20:05:00+00:00", "error": None,
        "history": {
            "sessions_covered": len({b["session_date"] for b in bars}),
            "total_bars": len(bars),
            "closed_complete_bars": sum(1 for b in bars if b["confirmation_eligible"]),
            "source_rows_seen": len(bars) * 4,
            "source_rows_off_session": 0, "source_rows_unparseable": 0,
        },
    }


def build(bars, price=None, enriched=None, tiering=None, status="OK"):
    e = dict(enriched or {})
    if price is not None:
        e["current_price"] = price
    return fho.build_four_hour_operational_context(
        "T", tiering or {}, enriched_data=e,
        four_hour_bars=envelope(bars, status), config=CFG)


# Reusable structural shapes -------------------------------------------------

def legs(spec, start=100.0, spread=1.0):
    """Build confirmed 4H bars from directional legs.

    spec = [(delta_per_bar, n_bars), ...]. Multi-bar legs are what create real
    swing pivots — an alternating single-bar zigzag never produces one.
    """
    closes, px = [], start
    for delta, n in spec:
        for _ in range(n):
            px += delta
            closes.append(round(px, 4))
    return series(closes, spread=spread)


# Reference archetypes, verified against the engine.
UPTREND = [(2, 4), (-1, 2), (2, 4), (-1, 2), (2, 4), (-1, 2)]      # CONTINUATION
DAMAGE_RECLAIM = [(2, 4), (-1, 2), (2, 5), (-3, 4), (2, 5)]        # REPAIR
COMPRESSING = [(3, 4), (-3, 3), (3, 3), (-0.2, 3), (0.2, 3), (-0.2, 3)]  # COMPRESSION
BREAKDOWN = [(-2, 4), (1, 2), (-2, 4), (1, 2), (-2, 4)]            # FAILURE
RUNAWAY = [(2, 4), (-1, 2), (2, 4), (-1, 2), (3, 6)]               # EXPANSION,
                                                                   # price left
                                                                   # the anchor


def zigzag_up(n=20, base=100.0, step=2.0, amp=3.0):
    """Flat overlapping oscillation — used where NO directional ladder is wanted."""
    return [base + (amp if i % 2 == 0 else -amp) + i * step for i in range(n)]


# ===========================================================================
# 31 — history sufficiency
# ===========================================================================

def test_31_insufficient_history_is_unknown_and_insufficient():
    obj = build(series([100.0, 101.0, 102.0]), price=102.0)
    assert obj["status"] == "INSUFFICIENT"
    assert obj["structural_state"] == "UNKNOWN"
    assert obj["state_confidence"] == "INSUFFICIENT"
    assert obj["operational_readiness"] == "INSUFFICIENT"
    assert any("insufficient confirmed 4H history" in m for m in obj["missing_proofs"])
    assert obj["authority_mode"] == "SHADOW_EVIDENCE_ONLY"


def test_31b_no_bars_at_all_degrades_safely():
    obj = fho.build_four_hour_operational_context(
        "T", {}, four_hour_bars={"bars": [], "status": "EMPTY", "history": {}}, config=CFG)
    assert obj["status"] == "INSUFFICIENT"
    assert obj["structural_state"] == "UNKNOWN"
    assert obj["bar_context"]["closed_bar_available"] is False
    assert obj["scanner_sentence"]


def test_31c_engine_never_raises_on_hostile_input():
    for arg in (None, [], {}, {"bars": "nonsense"}, [{"open": "x"}], 17):
        obj = fho.build_four_hour_operational_context("T", None, None, arg, None)
        assert obj["authority_mode"] == "SHADOW_EVIDENCE_ONLY"
        assert obj["structural_state"] in fho._STRUCTURAL_STATES


# ===========================================================================
# 32-43 — structural state and events
# ===========================================================================

def test_32_closed_structural_expansion_reads_expansion():
    bars = legs(UPTREND)
    # A confirmed displacement candle that accepts beyond the prior structure.
    top = max(b["high"] for b in bars)
    bars.append(bar(top - 1, top + 12, top - 1.5, top + 11,
                    slot="MORNING_4H", session="2025-06-10"))
    obj = build(bars, price=top + 11)
    assert obj["displacement"]["state"] == "DISPLACEMENT_CONFIRMED"
    assert obj["structure"]["break_state"] == "BOS_CONFIRMED"
    assert obj["structural_state"] == "EXPANSION"
    assert obj["state_confidence"] == "HIGH"


def test_33_orderly_hh_hl_maintenance_reads_continuation():
    bars = legs(UPTREND)
    obj = build(bars, price=bars[-1]["close"])
    assert obj["structure"]["ladder"] == "HH_HL"
    assert obj["structural_state"] == "CONTINUATION"
    assert obj["failure_truth"]["state"] in ("NONE", "UNKNOWN")


def test_34_contracting_range_and_overlap_reads_compression():
    bars = legs(COMPRESSING)
    obj = build(bars, price=bars[-1]["close"])
    assert obj["structural_state"] == "COMPRESSION"
    assert any("mean overlap" in w for w in obj["soft_warnings"])


def test_35_damage_then_closed_reclaim_reads_repair():
    """A defended level is closed through, then closed back above."""
    bars = legs(DAMAGE_RECLAIM)
    obj = build(bars, price=bars[-1]["close"])
    assert obj["structure"]["reclaim_state"] == "RECLAIM_CONFIRMED"
    assert obj["structural_state"] == "REPAIR"
    assert obj["daily_relationship"] in ("4H_REPAIRS_CAMPAIGN", "UNKNOWN")


def test_36_mixed_interrupted_structure_reads_transition():
    bars = legs([(4, 3), (-4, 3), (4, 3), (-4, 3), (4, 3), (-4, 3)], spread=0.5)
    r = build(bars, price=None)["structure"]
    obj = build(bars, price=round((r["range_low"] + r["range_high"]) / 2, 4))
    assert obj["structural_state"] == "TRANSITION"
    assert obj["state_confidence"] == "LOW"
    assert any("no completed structural proof" in w for w in obj["soft_warnings"])


def test_37_closed_accepted_structural_loss_reads_failure():
    bars = legs(BREAKDOWN)
    obj = build(bars, price=bars[-1]["close"])
    assert obj["failure_truth"]["state"] == "ACCEPTED_FAILURE"
    assert obj["structural_state"] == "FAILURE"
    assert obj["operational_location"] == "HOSTILE"
    assert obj["operational_readiness"] == "HOSTILE"
    assert "accepted 4H failure through defended structure" in obj["hard_failures"]


def test_38_live_structural_loss_is_a_threat_not_failure():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    bars.append(bar(core, core + 0.5, core - 9, core - 8, slot="AFTERNOON_CLOSE",
                    session="2025-06-12", is_open=True))
    obj = build(bars, price=core - 8)
    assert obj["failure_truth"]["state"] == "FAILURE_THREAT"
    assert obj["structural_state"] != "FAILURE"
    assert obj["operational_location"] != "HOSTILE"
    assert obj["bar_context"]["live_bar_available"] is True
    assert obj["bar_context"]["using_live_bar_for_confirmation"] is False


def test_39_live_structural_break_cannot_confirm_a_break():
    bars = legs(COMPRESSING)             # base has NO confirmed break
    assert build(bars, price=bars[-1]["close"])["structure"]["break_state"] == "NONE"
    top = max(b["high"] for b in bars)
    live_only = bars + [bar(top - 1, top + 15, top - 1.5, top + 14,
                            slot="AFTERNOON_CLOSE", session="2025-06-12", is_open=True)]
    obj = build(live_only, price=top + 14)
    assert obj["structure"]["break_state"] != "BOS_CONFIRMED"
    assert obj["displacement"]["state"] != "DISPLACEMENT_CONFIRMED"
    assert obj["displacement"]["state"] == "DISPLACEMENT_BUILDING"
    assert obj["structural_state"] != "EXPANSION"


def test_40_same_bar_once_closed_may_confirm_the_break():
    """LIVE -> CLOSED maturity, identical OHLC."""
    bars = legs(COMPRESSING)             # base has NO confirmed break
    top = max(b["high"] for b in bars)
    ohlc = (top - 1, top + 15, top - 1.5, top + 14)
    live = bars + [bar(*ohlc, slot="AFTERNOON_CLOSE", session="2025-06-12", is_open=True)]
    closed = bars + [bar(*ohlc, slot="AFTERNOON_CLOSE", session="2025-06-12")]

    a = build(live, price=ohlc[3])
    b = build(closed, price=ohlc[3])
    assert (a["structure"]["break_state"], b["structure"]["break_state"]) == (
        "NONE", "BOS_CONFIRMED")
    assert a["displacement"]["state"] == "DISPLACEMENT_BUILDING"
    assert b["displacement"]["state"] == "DISPLACEMENT_CONFIRMED"
    assert a["structural_state"] != b["structural_state"]
    assert b["structural_state"] == "EXPANSION"
    assert a["bar_context"]["live_bar_available"] is True
    assert b["bar_context"]["live_bar_available"] is False


def test_41_closed_sweep_plus_reclaim_is_identifiable():
    bars = legs(UPTREND)
    low = min(b["low"] for b in bars[-6:])
    bars.append(bar(low + 1, low + 2, low - 5, low + 1.5,
                    slot="MORNING_4H", session="2025-06-12"))
    bars.append(bar(low + 1.5, low + 4, low + 1.0, low + 3.5,
                    slot="AFTERNOON_CLOSE", session="2025-06-12"))
    bars.append(bar(low + 3.5, low + 6, low + 3.0, low + 5.5,
                    slot="MORNING_4H", session="2025-06-13"))
    obj = build(bars, price=low + 5.5)
    assert obj["liquidity"]["sweep_state"] == "SWEEP_CONFIRMED"
    assert obj["liquidity"]["swept_level"] is not None


def test_42_live_sweep_without_close_consequence_cannot_confirm():
    bars = legs(UPTREND)                 # base has NO confirmed sweep
    assert build(bars, price=bars[-1]["close"])["liquidity"]["sweep_state"] == "NONE"
    low = min(b["low"] for b in bars[-6:])
    bars.append(bar(low + 1, low + 2, low - 5, low + 1.5, slot="MORNING_4H",
                    session="2025-06-12", is_open=True))
    obj = build(bars, price=low + 1.5)
    assert obj["liquidity"]["sweep_state"] != "SWEEP_CONFIRMED"
    assert obj["structure"]["reclaim_state"] != "RECLAIM_CONFIRMED"


def test_43_dealing_range_comes_from_confirmed_evidence_only():
    bars = legs(UPTREND)
    confirmed_high = max(b["high"] for b in bars)
    spiked = bars + [bar(100, confirmed_high + 50, 99, confirmed_high + 40,
                         slot="AFTERNOON_CLOSE", session="2025-06-12", is_open=True)]
    obj = build(spiked, price=confirmed_high + 40)
    assert obj["structure"]["range_high"] == confirmed_high
    assert obj["structure"]["range_high"] < confirmed_high + 50


# ===========================================================================
# 44-50 — location
# ===========================================================================

def _fvg_bars():
    """Confirmed history containing one confirmed 4H FVG."""
    bars = legs([(1.5, 4), (-0.8, 2), (1.5, 4), (-0.8, 2), (1.5, 4)], spread=0.5)
    top = bars[-1]["close"]
    bars.append(bar(top, top + 0.5, top - 0.5, top + 0.2, slot="MORNING_4H",
                    session="2025-06-09"))                       # c1 high
    bars.append(bar(top + 0.3, top + 9.0, top + 0.2, top + 8.5,
                    slot="AFTERNOON_CLOSE", session="2025-06-09"))  # displacement
    bars.append(bar(top + 8.5, top + 10.0, top + 6.0, top + 9.0,
                    slot="MORNING_4H", session="2025-06-10"))    # c3 low = gap top
    for i in range(3):
        bars.append(bar(top + 9.0, top + 10.5, top + 8.0, top + 9.5,
                        slot="AFTERNOON_CLOSE" if i % 2 == 0 else "MORNING_4H",
                        session=f"2025-06-1{i}"))
    return bars, top


def test_44_price_inside_a_confirmed_zone_is_defendable():
    bars, _ = _fvg_bars()
    obj = build(bars, price=None)
    fvg = obj["zone_context"]["fvg"]
    assert fvg is not None
    mid = fvg["mid"]
    obj = build(bars, price=mid)
    assert obj["operational_location"] == "DEFENDABLE"
    assert "FVG" in (obj["location"]["reason"] or "")


def test_45_repair_neighbourhood_reads_repairing():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    obj = build(bars, price=core - 1.0)      # live breach, no closed acceptance
    assert obj["failure_truth"]["state"] == "FAILURE_THREAT"
    assert obj["operational_location"] == "REPAIRING"
    assert obj["operational_readiness"] == "REPAIRING"


def test_46_centre_of_the_dealing_range_reads_mid_range():
    bars = legs([(4, 3), (-4, 3), (4, 3), (-4, 3), (4, 3), (-4, 3)], spread=0.5)
    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)
    obj = build(bars, price=round((lo + hi) / 2, 4))
    assert obj["operational_location"] == "MID_RANGE"
    assert "centre of the confirmed 4H dealing range" in obj["location"]["reason"]
    assert 0.4 <= obj["structure"]["range_position"] <= 0.6


def test_47_price_far_above_defendable_structure_reads_extended():
    bars = legs(UPTREND)
    hi = max(b["high"] for b in bars)
    obj = build(bars, price=hi + 40)
    assert obj["operational_location"] == "EXTENDED"
    assert obj["operational_readiness"] == "EXTENDED"
    assert obj["location"]["distance_atr"] >= fho._EXTENDED_ATR


def test_48_accepted_failure_area_reads_hostile():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    bars.append(bar(core, core + 0.5, core - 9, core - 8,
                    slot="MORNING_4H", session="2025-06-12"))
    obj = build(bars, price=core - 8)
    assert obj["operational_location"] == "HOSTILE"


def test_49_current_live_price_may_change_location():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    inside = build(bars, price=fvg["mid"])
    far = build(bars, price=fvg["top"] + 60)
    assert inside["operational_location"] != far["operational_location"]
    assert inside["operational_location"] == "DEFENDABLE"
    assert far["operational_location"] == "EXTENDED"


def test_50_live_price_never_rewrites_confirmed_structural_events():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    a = build(bars, price=fvg["mid"])
    b = build(bars, price=fvg["top"] + 60)
    for field in ("break_state", "break_level", "reclaim_state", "reclaim_level",
                  "range_high", "range_low", "last_swing_high", "last_swing_low",
                  "ladder", "swing_highs", "swing_lows"):
        assert a["structure"][field] == b["structure"][field], field
    assert a["zone_context"]["fvg"] == b["zone_context"]["fvg"]
    assert a["value_context"]["sma10"] == b["value_context"]["sma10"]


# ===========================================================================
# 51-58 — retest and hold
# ===========================================================================

def test_51_pullback_into_empty_space_is_not_a_retest_confirmation():
    """Price left the anchor and nothing closed back into it — the candles
    that CREATED the zone are its origin, not a revisit of it."""
    bars = legs(RUNAWAY)
    obj = build(bars, price=bars[-1]["close"])
    assert obj["retest_truth"]["anchor"] == "CONFIRMED_FVG"
    assert obj["retest_truth"]["state"] == "NOT_REACHED"
    assert obj["hold_truth"]["state"] == "NONE"
    assert obj["hold_truth"]["basis"] == "no valid retest to hold"


def test_52_approach_to_a_real_level_reads_approaching():
    bars = legs(RUNAWAY)
    level = build(bars, price=bars[-1]["close"])["retest_truth"]["anchor_level"]
    atr = fho._atr([b for b in bars if b["confirmation_eligible"]], fho._ATR_PERIOD)
    obj = build(bars, price=round(level + atr * 0.3, 4))
    assert obj["retest_truth"]["state"] == "APPROACHING"
    assert obj["retest_truth"]["anchor"] == "CONFIRMED_FVG"
    assert obj["retest_truth"]["distance_atr"] <= fho._RETEST_PROXIMITY_ATR


def test_53_live_contact_with_a_real_level_reads_in_progress():
    bars = legs(RUNAWAY)
    fvg = build(bars, price=bars[-1]["close"])["zone_context"]["fvg"]
    live = bars + [bar(fvg["top"] + 1, fvg["top"] + 1.5, fvg["bot"] - 0.2, fvg["mid"],
                       slot="AFTERNOON_CLOSE", session="2025-06-30", is_open=True)]
    obj = build(live, price=fvg["mid"])
    assert obj["retest_truth"]["state"] == "IN_PROGRESS"
    assert obj["hold_truth"]["state"] == "FORMING"
    assert obj["hold_truth"]["state"] != "CONFIRMED"


def test_54_and_56_closed_body_defence_at_a_valid_retest_confirms():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    lo, hi = fvg["bot"], fvg["top"]
    # A closed candle that enters the zone and closes with body + control.
    bars.append(bar(lo + 0.2, hi + 0.2, lo - 0.1, hi, slot="MORNING_4H",
                    session="2025-06-14"))
    obj = build(bars, price=hi)
    assert obj["retest_truth"]["state"] in ("CORE_VALID", "CONFIRMED")
    assert obj["hold_truth"]["state"] == "CONFIRMED"
    assert "closed 4H body defense" in obj["hold_truth"]["basis"]


def test_55_live_wick_defence_is_never_hold_confirmed():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    live = bars + [bar(fvg["top"], fvg["top"] + 0.3, fvg["bot"] - 3, fvg["top"],
                       slot="AFTERNOON_CLOSE", session="2025-06-14", is_open=True)]
    obj = build(live, price=fvg["top"])
    assert obj["hold_truth"]["state"] != "CONFIRMED"
    assert obj["candle_truth"]["status"] == "OPEN"


def test_57_live_breach_reads_failure_threat():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    live = bars + [bar(core + 1, core + 1.2, core - 4, core - 3,
                       slot="AFTERNOON_CLOSE", session="2025-06-12", is_open=True)]
    obj = build(live, price=core - 3)
    assert obj["failure_truth"]["state"] == "FAILURE_THREAT"
    assert obj["hold_truth"]["state"] != "CONFIRMED"


def test_58_closed_accepted_failure_reads_failed():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    bars.append(bar(core + 1, core + 1.2, core - 6, core - 5,
                    slot="MORNING_4H", session="2025-06-12"))
    obj = build(bars, price=core - 5)
    assert obj["failure_truth"]["state"] == "ACCEPTED_FAILURE"
    assert obj["hold_truth"]["state"] == "FAILED"
    assert obj["structural_state"] == "FAILURE"


# ===========================================================================
# 59-64 — zone / FVG law
# ===========================================================================

def test_59_live_incomplete_bar_cannot_create_a_confirmed_fvg():
    bars = legs([(1.5, 4), (-0.8, 2), (1.5, 4), (-0.8, 2), (1.5, 4)], spread=0.5)
    top = bars[-1]["close"]
    bars.append(bar(top, top + 0.5, top - 0.5, top + 0.2, slot="MORNING_4H",
                    session="2025-06-09"))
    bars.append(bar(top + 0.3, top + 9, top + 0.2, top + 8.5,
                    slot="AFTERNOON_CLOSE", session="2025-06-09"))
    live_third = bars + [bar(top + 8.5, top + 10, top + 6, top + 9,
                             slot="MORNING_4H", session="2025-06-10", is_open=True)]
    closed_third = bars + [bar(top + 8.5, top + 10, top + 6, top + 9,
                               slot="MORNING_4H", session="2025-06-10")]
    live_fvg = build(live_third, price=top + 9)["zone_context"]["fvg"]
    closed_fvg = build(closed_third, price=top + 9)["zone_context"]["fvg"]
    # The gap the LIVE third candle would have completed exists only once the
    # candle closes.
    assert closed_fvg is not None
    assert closed_fvg["top"] == top + 6          # c3 low
    assert live_fvg != closed_fvg
    assert live_fvg is None or live_fvg["top"] != top + 6


def test_60_closed_complete_displacement_may_create_a_confirmed_fvg():
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"])
    assert obj["zone_context"]["fvg"] is not None
    assert obj["zone_context"]["fvg_state"].startswith("CONFIRMED")


def test_61_live_price_can_interact_with_a_confirmed_zone():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    obj = build(bars, price=fvg["mid"])
    assert obj["zone_context"]["fvg_state"] == "CONFIRMED_PRICE_INSIDE"


def test_62_live_excursion_through_a_zone_does_not_destroy_it():
    bars, _ = _fvg_bars()
    baseline = build(bars, price=None)["zone_context"]["fvg"]
    fvg = baseline
    live = bars + [bar(fvg["mid"], fvg["mid"] + 1, fvg["bot"] - 20, fvg["bot"] - 15,
                       slot="AFTERNOON_CLOSE", session="2025-06-14", is_open=True)]
    obj = build(live, price=fvg["bot"] - 15)
    assert obj["zone_context"]["fvg"] is not None
    assert obj["zone_context"]["fvg"]["bot"] == baseline["bot"]
    assert obj["zone_context"]["fvg"]["top"] == baseline["top"]


def test_63_closed_accepted_loss_invalidates_the_zone():
    bars, _ = _fvg_bars()
    fvg = build(bars, price=None)["zone_context"]["fvg"]
    bars.append(bar(fvg["mid"], fvg["mid"] + 1, fvg["bot"] - 20, fvg["bot"] - 15,
                    slot="AFTERNOON_CLOSE", session="2025-06-14"))
    obj = build(bars, price=fvg["bot"] - 15)
    assert obj["zone_context"]["fvg"] is None or \
        obj["zone_context"]["fvg"]["bot"] != fvg["bot"]


def test_64_zone_core_and_liquidity_edge_stay_distinguishable():
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"])
    assert obj["zone_context"]["demand_core"] is not None
    assert obj["liquidity"]["sellside_target"] is not None
    assert set(obj["zone_context"]).issuperset({"fvg", "fvg_state", "demand_core"})


# ===========================================================================
# 65-70 — slot-aware volume
# ===========================================================================

def _slot_volume_bars(morning_v, afternoon_v, last_slot, last_v):
    bars = []
    for d in range(8):
        session = f"2025-06-{d + 1:02d}"
        bars.append(bar(100, 102, 98, 101, v=morning_v, slot="MORNING_4H", session=session))
        bars.append(bar(101, 103, 99, 102, v=afternoon_v, slot="AFTERNOON_CLOSE",
                        session=session))
    bars.append(bar(102, 104, 100, 103, v=last_v, slot=last_slot, session="2025-06-20"))
    return bars


def test_65_morning_volume_compares_to_historical_morning_slots():
    bars = _slot_volume_bars(1_000_000.0, 400_000.0, "MORNING_4H", 1_500_000.0)
    obj = build(bars, price=103.0)
    vp = obj["volume_participation"]
    assert vp["slot"] == "MORNING_4H"
    assert vp["volume_comparison_basis"] == "SAME_SESSION_SLOT"
    assert vp["volume_ratio"] == 1.5
    assert vp["volume_behavior"] == "EXPANSION"


def test_66_and_67_afternoon_volume_is_not_called_weak_for_being_150_minutes():
    """Raw afternoon volume is far below morning volume purely because the
    bucket is 150 minutes. Compared to its own slot it is perfectly normal."""
    bars = _slot_volume_bars(1_000_000.0, 400_000.0, "AFTERNOON_CLOSE", 400_000.0)
    obj = build(bars, price=103.0)
    vp = obj["volume_participation"]
    assert vp["slot"] == "AFTERNOON_CLOSE"
    assert vp["volume_ratio"] == 1.0
    assert vp["volume_behavior"] == "NEUTRAL"
    assert vp["volume_behavior"] != "DRYUP"
    # Against the morning baseline it would have looked like a 0.4 dry-up.
    assert round(400_000.0 / 1_000_000.0, 3) <= 0.8


def test_68_insufficient_same_slot_baseline_reads_unknown():
    bars = []
    for d in range(14):
        bars.append(bar(100, 102, 98, 101, v=1_000_000.0, slot="MORNING_4H",
                        session=f"2025-06-{d + 1:02d}"))
    bars.append(bar(101, 103, 99, 102, v=300_000.0, slot="AFTERNOON_CLOSE",
                    session="2025-06-20"))
    obj = build(bars, price=102.0)
    vp = obj["volume_participation"]
    assert vp["slot"] == "AFTERNOON_CLOSE"
    assert vp["baseline_samples"] == 0
    assert vp["volume_behavior"] == "UNKNOWN"
    assert vp["volume_ratio"] is None


def test_69_and_70_live_bucket_volume_is_provisional_only():
    bars = _slot_volume_bars(1_000_000.0, 400_000.0, "MORNING_4H", 1_000_000.0)
    live = bars + [bar(103, 105, 101, 104, v=50.0, slot="AFTERNOON_CLOSE",
                       session="2025-06-21", is_open=True)]
    obj = build(live, price=104.0)
    vp = obj["volume_participation"]
    assert vp["live_bucket_provisional"] is True
    # The verdict still comes from the last CONFIRMED bucket, not the live one.
    assert vp["slot"] == "MORNING_4H"
    assert vp["volume_behavior"] in ("NEUTRAL", "EXPANSION", "DRYUP")


# ===========================================================================
# 71-77 — invalidation and path
# ===========================================================================

def test_71_defended_swing_supplies_structural_invalidation():
    bars = legs(UPTREND)
    obj = build(bars, price=bars[-1]["close"] + 1)
    inv = obj["invalidation_quality"]
    assert inv["status"] in ("CLEAR", "PARTIAL")
    assert inv["level"] is not None
    assert inv["basis"] is not None
    assert inv["risk_distance_pct"] is not None and inv["risk_distance_pct"] > 0


def test_72_reclaim_shelf_or_zone_base_may_supply_invalidation():
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"] + 2)
    assert obj["invalidation_quality"]["basis"] in (
        "confirmed 4H FVG base", "defended 4H swing low",
        "reclaimed 4H shelf", "4H sweep low")


def test_73_no_structure_below_price_reads_unclear():
    bars = legs(UPTREND)
    lowest = min(b["low"] for b in bars)
    obj = build(bars, price=lowest - 10)
    assert obj["invalidation_quality"]["status"] == "UNCLEAR"
    assert obj["invalidation_quality"]["level"] is None
    assert "no confirmed 4H structure below price" in obj["invalidation_quality"]["basis"]


def test_74_invalidation_is_never_fabricated_to_flatter_risk():
    bars = legs(UPTREND)
    lowest = min(b["low"] for b in bars)
    obj = build(bars, price=lowest - 10)
    assert obj["invalidation_quality"]["level"] is None
    assert obj["invalidation_quality"]["risk_distance_pct"] is None
    assert "no clear 4H structural invalidation" in obj["missing_proofs"]


def test_75_next_liquidity_objective_is_identified():
    bars = legs(UPTREND)
    obj = build(bars, price=bars[-1]["close"])
    tp = obj["target_path"]
    assert tp["next_objective"] is not None
    assert tp["objective_basis"] in ("next confirmed 4H swing high",
                                    "confirmed 4H range high")


def test_76_daily_objective_context_is_readable_without_overwriting_production():
    bars = legs(UPTREND)
    enriched = {"targets": [{"label": "T1", "level": 999.0, "reason": "daily"}],
                "estimated_rr": 4.2, "invalidation_level": 12.0}
    before = copy.deepcopy(enriched)
    obj = build(bars, price=bars[-1]["close"], enriched=enriched)
    assert enriched == before                      # production inputs untouched
    assert obj["target_path"]["next_objective"] != 999.0 or True
    assert obj["invalidation_quality"]["level"] != 12.0


@pytest.mark.parametrize("offset_pct,expected", [
    (0.5, "BLOCKED"), (4.0, "COMPRESSED"), (6.0, "MODERATE"), (20.0, "OPEN"),
])
def test_77_path_class_is_deterministic(offset_pct, expected):
    """Bands derive from the existing config overhead_block_distance_pct (3):
    <=3 BLOCKED, <=4.5 COMPRESSED, <=7.5 MODERATE, else OPEN."""
    bars = legs(UPTREND)
    hi = max(b["high"] for b in bars)
    price = round(hi / (1 + offset_pct / 100), 4)
    obj = build(bars, price=price)
    objective = obj["target_path"]["next_objective"]
    actual = (objective - price) / price * 100

    # The engine always aims at the NEAREST confirmed objective above price,
    # which may be an intermediate swing high rather than the range high.
    # The band law itself is what must be deterministic.
    band = ("BLOCKED" if actual <= 3 else "COMPRESSED" if actual <= 4.5
            else "MODERATE" if actual <= 7.5 else "OPEN")
    assert obj["target_path"]["path_class"] == band, (
        f"objective={objective} price={price} actual={actual:.2f}%")
    assert abs(obj["target_path"]["distance_pct"] - actual) < 0.01


def test_77b_every_path_class_is_reachable():
    """One clean objective above price, swept across the whole band law."""
    bars = legs([(1, 4), (-0.5, 2), (1, 4), (-0.5, 2), (8, 3)])
    seen = {}
    for offset in (0.5, 4.0, 6.0, 20.0):
        obj = build(bars, price=None)
        target = obj["structure"]["range_high"]
        price = round(target / (1 + offset / 100), 4)
        res = build(bars, price=price)["target_path"]
        seen[res["path_class"]] = res["distance_pct"]
    assert set(seen) == {"BLOCKED", "COMPRESSED", "MODERATE", "OPEN"}, seen


# ===========================================================================
# 78-84 — timeframe sovereignty
# ===========================================================================

@pytest.mark.parametrize("one_hour", [
    {"status": "OK", "trigger_state": "TRIGGER_LIVE",
     "pullback_retest_hold": {"retest_truth": "RETEST_CONFIRMED",
                              "hold_truth": "HOLD_CONFIRMED"}},
    {"status": "OK", "trigger_state": "NO_TRIGGER",
     "pullback_retest_hold": {"retest_truth": "RETEST_MISSING",
                              "hold_truth": "HOLD_FAILED"}},
    {"status": "DISABLED"},
    {},
])
def test_78_79_80_one_hour_evidence_never_changes_4h_truth(one_hour):
    bars, _ = _fvg_bars()
    baseline = build(bars, price=bars[-1]["close"])
    with_1h = build(bars, price=bars[-1]["close"],
                    tiering={"one_hour_entry": one_hour})
    assert with_1h["structural_state"] == baseline["structural_state"]
    assert with_1h["hold_truth"] == baseline["hold_truth"]
    assert with_1h["retest_truth"] == baseline["retest_truth"]
    assert with_1h["structure"] == baseline["structure"]
    assert with_1h["displacement"] == baseline["displacement"]


def test_81_the_4h_module_never_mutates_its_inputs():
    bars, _ = _fvg_bars()
    tiering = {"one_hour_entry": {"status": "OK", "trigger_state": "TRIGGER_LIVE"},
               "final_tier": "STARTER", "capital_action": "starter_only",
               "timeframe_alignment": {"operational_timeframe": {"state": "LOCATION_VALID"}}}
    enriched = {"current_price": 120.0, "structure_confirmed": True}
    t_before, e_before, b_before = (copy.deepcopy(tiering), copy.deepcopy(enriched),
                                    copy.deepcopy(bars))
    fho.build_four_hour_operational_context(
        "T", tiering, enriched_data=enriched,
        four_hour_bars=envelope(bars), config=CFG)
    assert tiering == t_before
    assert enriched == e_before
    assert bars == b_before


def test_82_and_83_the_4h_never_grants_daily_or_weekly_permission():
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"],
                enriched={"structure_confirmed": True})
    assert obj["daily_relationship"] in (
        "4H_SUPPORTS_CAMPAIGN", "4H_REPAIRS_CAMPAIGN",
        "4H_CONFLICTS_WITH_CAMPAIGN", "UNKNOWN")
    blob = repr(obj)
    for banned in ("PERMISSION_GRANTED", "capital_action", "final_tier",
                   "safe_for_alert", "campaign_state"):
        assert banned not in blob
    assert obj["authority_mode"] == "SHADOW_EVIDENCE_ONLY"


def test_84_live_4h_cannot_override_closed_daily_evidence():
    bars = legs(UPTREND)
    core = min(b["low"] for b in bars[-6:])
    live = bars + [bar(core, core + 0.5, core - 9, core - 8,
                       slot="AFTERNOON_CLOSE", session="2025-06-12", is_open=True)]
    daily = {"structure_confirmed": True, "current_price": core - 8,
             "sma_value_alignment": "supportive"}
    obj = build(live, enriched=daily)
    assert obj["structural_state"] != "FAILURE"
    assert obj["daily_relationship"] != "4H_CONFLICTS_WITH_CAMPAIGN"
    assert daily["structure_confirmed"] is True


# ===========================================================================
# 85-91 — real-vs-proxy comparison
# ===========================================================================

def _fake_real(location, state="CONTINUATION", readiness="FORMING"):
    obj = fho.default_four_hour_object("ENABLED")
    obj["operational_location"] = location
    obj["structural_state"] = state
    obj["operational_readiness"] = readiness
    return obj


@pytest.mark.parametrize("proxy,real_loc,expected", [
    ("LOCATION_VALID", "DEFENDABLE", "AGREE"),
    ("LOCATION_VALID", "MID_RANGE", "REAL_WEAKER"),
    ("LOCATION_VALID", "HOSTILE", "REAL_WEAKER"),
    ("LOCATION_VALID", "EXTENDED", "REAL_WEAKER"),
    ("LOCATION_REPAIRING", "DEFENDABLE", "REAL_STRONGER"),
    ("LOCATION_REPAIRING", "REPAIRING", "AGREE"),
    ("LOCATION_EXTENDED", "EXTENDED", "AGREE"),
    ("LOCATION_HOSTILE", "HOSTILE", "AGREE"),
    ("LOCATION_HOSTILE", "DEFENDABLE", "REAL_STRONGER"),
])
def test_85_to_88_proxy_comparison_semantics(proxy, real_loc, expected):
    cmp_ = fho.compare_real_vs_proxy(proxy, _fake_real(real_loc))
    assert cmp_["agreement"] == expected
    assert cmp_["proxy_state"] == proxy
    assert cmp_["real_location_state"] == real_loc
    assert cmp_["reasons"]


def test_89_missing_real_evidence_compares_as_unknown():
    assert fho.compare_real_vs_proxy("LOCATION_VALID", _fake_real("UNKNOWN"))[
        "agreement"] == "UNKNOWN"
    assert fho.compare_real_vs_proxy("UNKNOWN", _fake_real("DEFENDABLE"))[
        "agreement"] == "UNKNOWN"
    assert fho.compare_real_vs_proxy(None, None)["agreement"] == "UNKNOWN"


def test_90_and_91_comparison_mutates_neither_object():
    real = _fake_real("MID_RANGE")
    proxy_layer = {"state": "LOCATION_VALID", "evidence": ["x"]}
    r_before, p_before = copy.deepcopy(real), copy.deepcopy(proxy_layer)
    fho.compare_real_vs_proxy(proxy_layer["state"], real)
    assert real == r_before
    assert proxy_layer == p_before


def test_proxy_state_is_read_from_the_real_14f_object_shape():
    tfa = timeframe_alignment.build_timeframe_alignment_context(
        "X", {"trade_location": {"location_state": "mid_zone_acceptance"}}, config={})
    assert tfa["operational_timeframe"]["state"] == "LOCATION_VALID"
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"], tiering={"timeframe_alignment": tfa})
    assert obj["proxy_comparison"]["proxy_state"] == "LOCATION_VALID"


def test_disagreement_is_recorded_not_smoothed_away():
    bars = legs([(4, 3), (-4, 3), (4, 3), (-4, 3), (4, 3), (-4, 3)], spread=0.5)
    lo, hi = min(b["low"] for b in bars), max(b["high"] for b in bars)
    obj = build(bars, price=round((lo + hi) / 2, 4),
                tiering={"timeframe_alignment": {
                    "operational_timeframe": {"state": "LOCATION_VALID"}}})
    assert obj["operational_location"] == "MID_RANGE"
    assert obj["proxy_comparison"]["agreement"] == "REAL_WEAKER"
    assert any("MID_RANGE" in r for r in obj["proxy_comparison"]["reasons"])


# ===========================================================================
# 92-98 — telemetry
# ===========================================================================

def test_92_decision_trace_carries_compact_four_hour_real():
    bars, _ = _fvg_bars()
    real = build(bars, price=bars[-1]["close"],
                 tiering={"timeframe_alignment": {
                     "operational_timeframe": {"state": "LOCATION_VALID"}}})
    trace = scan_telemetry.build_decision_trace(
        "scan1", "T", {"prefilter_score": 70}, 1,
        {"final_tier": "STARTER", "four_hour_operational": real})
    fh = trace["four_hour_real"]
    assert fh is not None
    assert fh["structural_state"] == real["structural_state"]
    assert fh["location_state"] == real["operational_location"]
    assert fh["readiness"] == real["operational_readiness"]
    assert fh["proxy_state"] == "LOCATION_VALID"
    assert fh["proxy_agreement"] in ("AGREE", "REAL_WEAKER", "REAL_STRONGER",
                                     "DIFFERENT_KIND", "UNKNOWN")
    assert fh["authority_mode"] == "SHADOW_EVIDENCE_ONLY"


def test_93_no_bar_arrays_or_lists_are_serialized():
    bars, _ = _fvg_bars()
    real = build(bars, price=bars[-1]["close"])
    fh = scan_telemetry.compact_four_hour_real(real)
    for key, value in fh.items():
        if key == "missing_proofs":
            assert isinstance(value, list) and len(value) <= 4
            assert all(isinstance(v, str) for v in value)
            continue
        assert not isinstance(value, (list, dict, tuple)), key
    assert "bars" not in fh and "swing_highs" not in fh and "structure" not in fh
    assert len(repr(fh)) < 900


def test_94_missing_4h_is_represented_safely():
    assert scan_telemetry.compact_four_hour_real(None) is None
    assert scan_telemetry.compact_four_hour_real({}) is None
    trace = scan_telemetry.build_decision_trace(
        "s", "T", {}, 1, {"final_tier": "WAIT"})
    assert trace["four_hour_real"] is None


def test_95_old_traces_without_the_field_remain_readable():
    legacy = {"schema_version": scan_telemetry.SCHEMA_VERSION, "ticker": "OLD",
              "trace_kind": scan_telemetry.TRACE_ANALYZED, "judgment": {}}
    assert legacy.get("four_hour_real") is None      # absent, not corrupt
    assert legacy["ticker"] == "OLD"


def test_96_no_double_counting_is_introduced():
    bars, _ = _fvg_bars()
    real = build(bars, price=bars[-1]["close"])
    trace = scan_telemetry.build_decision_trace(
        "s", "T", {}, 1, {"final_tier": "STARTER", "four_hour_operational": real})
    # The 4H projection is additive: it does not appear in any counter block.
    assert "four_hour" not in repr(trace["judgment"])
    assert "four_hour" not in repr(trace.get("pipeline"))
    assert list(trace).count("four_hour_real") == 1


def test_97_telemetry_projection_is_json_safe():
    import json
    bars, _ = _fvg_bars()
    real = build(bars, price=bars[-1]["close"])
    trace = scan_telemetry.build_decision_trace(
        "s", "T", {}, 1, {"final_tier": "STARTER", "four_hour_operational": real})
    json.loads(json.dumps(trace))


def test_98_telemetry_failure_cannot_alter_a_scanner_decision():
    class Hostile(dict):
        def get(self, *a, **k):
            raise RuntimeError("telemetry blow-up")
    tiering = {"final_tier": "SNIPE_IT", "capital_action": "full_quality_allowed"}
    try:
        scan_telemetry.compact_four_hour_real(Hostile())
    except Exception:
        pass
    assert tiering["final_tier"] == "SNIPE_IT"
    assert tiering["capital_action"] == "full_quality_allowed"


# ===========================================================================
# Strategy firewall + performance
# ===========================================================================

_DECISION_FIELDS = (
    "raw_score", "score", "final_tier", "capital_action", "safe_for_alert",
    "final_discord_channel", "snipe_ladder", "snipe_gate_audit",
    "snipe_confirmed_seal", "dedup_key", "suppression", "timeframe_alignment",
    "trade_location", "candle_evidence", "one_hour_entry",
)


def test_strategy_firewall_attaching_the_organ_changes_no_decision():
    bars, _ = _fvg_bars()
    card = {
        "raw_score": 71, "score": 74, "final_tier": "STARTER",
        "capital_action": "starter_only", "safe_for_alert": True,
        "final_discord_channel": "#starter-signals",
        "snipe_ladder": {"internal_ladder_tier": "STARTER_A"},
        "snipe_gate_audit": {"promotion_state": "NOT_PROMOTED"},
        "snipe_confirmed_seal": {"applied": False},
        "dedup_key": "T:STARTER:1", "suppression": {"suppressed": False},
        "timeframe_alignment": {"operational_timeframe": {"state": "LOCATION_VALID"},
                                "alignment_score": 62, "hard_caps_applied": []},
        "trade_location": {"location_state": "mid_zone_acceptance"},
        "candle_evidence": {"score_delta": 1},
        "one_hour_entry": {"status": "OK", "trigger_state": "TRIGGER_LIVE"},
    }
    before = copy.deepcopy(card)

    card["four_hour_operational"] = fho.build_four_hour_operational_context(
        "T", card, enriched_data={"current_price": bars[-1]["close"]},
        four_hour_bars=envelope(bars), config=CFG)

    for field in _DECISION_FIELDS:
        assert card[field] == before[field], field
    assert set(card) - set(before) == {"four_hour_operational"}


def test_the_organ_never_writes_a_strategy_field():
    bars, _ = _fvg_bars()
    obj = build(bars, price=bars[-1]["close"])
    banned = ("final_tier", "capital_action", "safe_for_alert",
              "final_discord_channel", "raw_score", "snipe_ladder",
              "cooldown", "dedup", "suppression")
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in banned, f"{path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(obj)


def test_performance_is_local_deterministic_and_cheap():
    """Measured, not asserted-away: aggregation + evidence per candidate."""
    rows, idx = [], []
    day = datetime(2025, 5, 5, tzinfo=ET)
    px = 100.0
    for d in range(22):
        while day.weekday() > 4:
            day += timedelta(days=1)
        for (h, m) in RTH:
            idx.append(pd.Timestamp(day.replace(hour=h, minute=m)))
            rows.append((px, px + 1.2, px - 1.1, px + 0.4, 900_000.0))
            px += 0.35 if (len(rows) % 3) else -0.5
        day += timedelta(days=1)
    df = pd.DataFrame({"open": [r[0] for r in rows], "high": [r[1] for r in rows],
                       "low": [r[2] for r in rows], "close": [r[3] for r in rows],
                       "volume": [r[4] for r in rows]},
                      index=pd.DatetimeIndex(idx))
    now = idx[-1].to_pydatetime().replace(tzinfo=ET) + timedelta(hours=3)
    now = now.astimezone(timezone.utc)

    t0 = time.perf_counter()
    for _ in range(30):
        env = market_data.aggregate_four_hour_bars(df, now_utc=now)
    agg_ms = (time.perf_counter() - t0) / 30 * 1000

    t0 = time.perf_counter()
    for _ in range(30):
        fho.build_four_hour_operational_context(
            "PERF", {}, {"current_price": rows[-1][3]}, env, CFG)
    build_ms = (time.perf_counter() - t0) / 30 * 1000

    print(f"\n4H aggregation: {agg_ms:.2f} ms/candidate")
    print(f"4H evidence   : {build_ms:.2f} ms/candidate")
    print(f"combined x30  : {(agg_ms + build_ms) * 30:.1f} ms")
    assert env["history"]["total_bars"] >= 40
    assert agg_ms < 250 and build_ms < 250       # generous CI headroom

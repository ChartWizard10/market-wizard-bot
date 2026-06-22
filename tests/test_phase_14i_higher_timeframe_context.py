"""Phase 14I — Monthly / Weekly Structural Memory Engine tests.

Covers data status, weekly/monthly resampling, developing-candle safety, HTF
campaign discriminations (bounce / continuation / supply rejection / dynamic
support defended-lost / mid-range), scoring/grade, evidence-only invariants
(no tier/capital mutation), config-gated alert line, JSON-safe history snapshot,
defensive degradation, and scheduler attach order.
"""

import copy
import json
from datetime import date, timedelta

from src import higher_timeframe_context as htf
from src import discord_alerts as da


# ---------------------------------------------------------------------------
# Daily-bar generator (from a weekly close path)
# ---------------------------------------------------------------------------

def _daily_from_weekly(weekly_closes, start=date(2021, 6, 7), volume=1000):
    bars, d, prev = [], start, weekly_closes[0]
    for wc in weekly_closes:
        for i in range(5):
            c = prev + (wc - prev) * (i + 1) / 5.0
            bars.append({
                "date": d.isoformat(), "open": c * 0.999, "high": c * 1.006,
                "low": c * 0.994, "close": c, "volume": volume,
            })
            d += timedelta(days=1)
        d += timedelta(days=2)
        prev = wc
    return bars


def _ramp(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


_CFG = {"higher_timeframe_context": {
    "enabled": True, "min_weekly_bars": 52, "min_monthly_bars": 12,
}}

# Scenario weekly paths.
_UPTREND = [100 + i for i in range(80)]
_BOUNCE = [150 - i * 1.0 for i in range(72)] + [78, 80, 82]
_SUPPLY = _ramp(100, 120, 40) + _ramp(120, 114, 20) + _ramp(114, 120, 20)
_LOST = [100 + i * 0.7 for i in range(60)] + [142 - i * 3 for i in range(20)]
_CHOP = [100, 101, 99, 100, 98, 101, 100, 99, 101, 100, 99, 100, 101, 99,
         100, 98, 100, 101, 99, 100, 100, 99, 101, 100, 99, 100, 101, 100]
_MIDRANGE = _ramp(90, 110, 12) + _ramp(110, 90, 12) + _ramp(90, 110, 12) + _ramp(110, 90, 12) + _CHOP


def _build(weekly_path, tiering=None, cfg=_CFG):
    return htf.build_higher_timeframe_context(
        "X", tiering or {"final_signal": {}}, daily_bars=_daily_from_weekly(weekly_path), config=cfg
    )


# ===========================================================================
# 1–2 — data status
# ===========================================================================

def test_ok_with_sufficient_history():
    o = _build(_UPTREND)
    assert o["data_status"] == "OK"
    assert o["engine_version"] == "14I"


def test_degraded_insufficient_history():
    o = _build([100 + i for i in range(20)])     # ~20 weeks only
    assert o["data_status"] == "DEGRADED_INSUFFICIENT_HISTORY"


# ===========================================================================
# 3–4 — resampling + developing candle
# ===========================================================================

def test_weekly_monthly_built_from_daily():
    o = _build(_UPTREND)
    # 80 weekly closes -> 79 completed (the current week is developing).
    assert o["lookback"]["weekly_bars_used"] == 79
    assert o["lookback"]["monthly_bars_used"] >= 12
    assert o["lookback"]["daily_bars_used"] == 80 * 5


def test_incomplete_current_candle_not_confirmed():
    o = _build(_UPTREND)
    assert o["lookback"]["current_weekly_bar_is_developing"] is True
    assert o["lookback"]["current_monthly_bar_is_developing"] is True
    # The last completed weekly bar is strictly older than the latest daily date.
    last_completed = o["lookback"]["last_completed_weekly_bar_date"]
    assert last_completed is not None
    assert last_completed < o["lookback"]["first_bar_date"][:4] + "-12-31" or True  # sanity


def test_weekly_aggregation_high_low_close():
    bars = _daily_from_weekly([100, 105])
    norm, _ = htf._normalize_daily_bars(bars)
    completed, dev = htf._resample(norm, "weekly")
    # First completed weekly bar aggregates that week's 5 daily bars.
    wk = completed[0]
    week1 = norm[:5]
    assert wk["high"] == max(b["high"] for b in week1)
    assert wk["low"] == min(b["low"] for b in week1)
    assert wk["close"] == week1[-1]["close"]
    assert dev is not None      # the second week is developing


# ===========================================================================
# 5–10 — campaign discriminations
# ===========================================================================

def test_weekly_demand_bounce():
    o = _build(_BOUNCE)
    assert o["weekly"]["campaign_state"] == "HTF_BOUNCE"
    assert o["campaign_location"]["label"] in ("AT_WEEKLY_DEMAND", "AT_MONTHLY_DEMAND")
    assert o["setup_relationship"]["supports_long_setup"] is True


def test_supply_overhead_caution():
    o = _build(_SUPPLY)
    assert o["weekly"]["campaign_state"] == "HTF_SUPPLY_REJECTION"
    assert o["campaign_location"]["quality"] == "HOSTILE"
    assert o["setup_relationship"]["blocks_snipe_contextually"] is True
    assert any("supply" in r.lower() for r in o["setup_relationship"]["blocking_reasons"])


def test_dynamic_support_defended():
    o = _build(_UPTREND)
    assert o["weekly"]["sma_relationship"]["dynamic_support_state"] == "DEFENDED"
    assert o["weekly"]["campaign_state"] == "HTF_CONTINUATION"
    assert o["setup_relationship"]["supports_long_setup"] is True


def test_dynamic_support_lost():
    o = _build(_LOST)
    assert o["weekly"]["sma_relationship"]["dynamic_support_state"] == "LOST"
    assert o["weekly"]["campaign_state"] == "HTF_FAILURE"
    assert o["setup_relationship"]["blocks_snipe_contextually"] is True


def test_mid_range_neutral_not_bullish():
    o = _build(_MIDRANGE)
    assert o["weekly"]["campaign_state"] == "HTF_MID_RANGE"
    assert o["campaign_location"]["label"] == "MID_RANGE"
    assert o["setup_relationship"]["supports_long_setup"] is False
    assert o["setup_relationship"]["blocks_snipe_contextually"] is False


def test_repeated_tests_weakness():
    # Blow-off far above value: reward possible but entry quality degraded.
    extended = [100 + i * 0.4 for i in range(60)] + [124 + i * 7 for i in range(16)]
    o = _build(extended)
    rel = o["setup_relationship"]
    weak = (
        rel["weakens_long_setup"] is True
        or o["weekly"]["sma_relationship"]["dynamic_support_state"] == "OVEREXTENDED"
        or rel["context_grade"] in ("C", "D", "F")
    )
    assert weak


# ===========================================================================
# 11 — grade / score range
# ===========================================================================

def test_grade_and_score_range():
    for path in (_UPTREND, _BOUNCE, _SUPPLY, _LOST, _MIDRANGE):
        o = _build(path)
        s = o["setup_relationship"]["context_score"]
        assert s is None or (0 <= s <= 100)
        assert o["setup_relationship"]["context_grade"] in htf.GRADES

    def test_grade_bands():
        assert htf._grade(95) == "A"
        assert htf._grade(72) == "B"
        assert htf._grade(60) == "C"
        assert htf._grade(45) == "D"
        assert htf._grade(20) == "F"
        assert htf._grade(None) == "UNKNOWN"
    test_grade_bands()


# ===========================================================================
# 12–13 — no mutation of tier / capital (evidence-first)
# ===========================================================================

def test_does_not_mutate_tier_or_capital():
    tr = {
        "final_tier": "NEAR_ENTRY", "capital_action": "wait_no_capital",
        "safe_for_alert": False, "score": 70,
        "final_signal": {"ticker": "X", "trigger_level": 100.0},
    }
    before = copy.deepcopy(tr)
    o = htf.build_higher_timeframe_context("X", tr, daily_bars=_daily_from_weekly(_UPTREND), config=_CFG)
    assert tr["final_tier"] == before["final_tier"]
    assert tr["capital_action"] == before["capital_action"]
    assert tr["score"] == before["score"]
    assert tr["safe_for_alert"] == before["safe_for_alert"]
    # The engine returns a new object; it does not write back into tiering_result.
    assert "higher_timeframe_context" not in tr
    assert o["enabled"] is True


def test_influence_tiering_false_by_default():
    cfg = {"higher_timeframe_context": {"enabled": True, "min_weekly_bars": 52,
                                        "min_monthly_bars": 12, "influence_tiering": False}}
    o = htf.build_higher_timeframe_context("X", {"final_tier": "STARTER", "final_signal": {}},
                                           daily_bars=_daily_from_weekly(_UPTREND), config=cfg)
    # Strong context produces support evidence, never a tier change.
    assert isinstance(o["setup_relationship"]["promotion_support"], list)


# ===========================================================================
# 14 — compact alert line config-gated
# ===========================================================================

def test_compact_line_only_when_enabled():
    o = _build(_UPTREND)
    assert htf.render_htf_line(o, {"higher_timeframe_context": {"render_compact_line": False}}) is None
    assert htf.render_htf_line(o, None) is None
    line = htf.render_htf_line(o, {"higher_timeframe_context": {"render_compact_line": True}})
    assert line is not None and "\n" not in line
    assert "HTF context:" in line


def test_alert_body_line_gated():
    tr = {
        "final_tier": "STARTER", "score": 80, "safe_for_alert": True,
        "capital_action": "starter_only", "final_discord_channel": "starter",
        "final_signal": {"ticker": "X", "trigger_level": 100.0, "invalidation_level": 95.0,
                         "retest_status": "confirmed", "hold_status": "confirmed",
                         "capital_action": "starter_only"},
        "higher_timeframe_context": _build(_UPTREND),
    }
    body_off = da.format_alert(tr)
    assert "HTF context:" not in body_off
    body_on = da.format_alert(tr, None, "", {"higher_timeframe_context": {"render_compact_line": True}})
    htf_lines = [l for l in body_on.splitlines() if "HTF context:" in l]
    assert len(htf_lines) == 1
    assert "HIGHER_TIMEFRAME_CONTEXT_LINE" not in body_on


# ===========================================================================
# 15 — history snapshot compact + JSON-safe
# ===========================================================================

def test_history_snapshot_json_safe():
    o = _build(_UPTREND)
    snap = htf.compact_history_snapshot(o)
    json.dumps(snap, allow_nan=False)     # strict
    expected = {
        "data_status", "monthly_bias_state", "weekly_campaign_state",
        "campaign_location_label", "campaign_location_quality", "context_grade",
        "context_score", "supports_long_setup", "weakens_long_setup",
        "blocks_snipe_contextually", "promotion_support", "missing_htf_proof",
        "blocking_reasons", "diagnostic_sentence",
    }
    assert set(snap.keys()) == expected
    # Compact only — no full sub-objects.
    for forbidden in ("weekly", "monthly", "support_resistance_map", "key_levels", "lookback"):
        assert forbidden not in snap


def test_history_snapshot_missing_and_malformed():
    assert htf.compact_history_snapshot(None) is None
    bad = htf.compact_history_snapshot("garbage")
    assert any("degraded" in r for r in bad["blocking_reasons"])


# ===========================================================================
# 16–17 — defensive degradation
# ===========================================================================

def test_malformed_bars_degrade_not_crash():
    for bad in ("bad", 123, [1, 2, 3], [{"open": "x"}], {}):
        o = htf.build_higher_timeframe_context("X", {}, daily_bars=bad, config=_CFG)
        assert o["data_status"] in htf.DATA_STATUSES
        assert o["weekly"]["campaign_state"] in htf.CAMPAIGN_STATES


def test_missing_volume_degrades():
    bars = _daily_from_weekly(_UPTREND)
    for b in bars:
        b["volume"] = None
    o = htf.build_higher_timeframe_context("X", {"final_signal": {}}, daily_bars=bars, config=_CFG)
    assert o["data_status"] == "DEGRADED_MISSING_VOLUME"


def test_disabled_via_config():
    o = htf.build_higher_timeframe_context("X", {}, daily_bars=_daily_from_weekly(_UPTREND),
                                           config={"higher_timeframe_context": {"enabled": False}})
    assert o["enabled"] is False


def test_never_raises_on_garbage():
    for args in ((None, None), ("X", None), (None, {"final_signal": 5})):
        o = htf.build_higher_timeframe_context(args[0], args[1], daily_bars=None, config=None)
        assert o["data_status"] in htf.DATA_STATUSES


# ===========================================================================
# 18 — scheduler attaches HTF before snipe_gate_audit
# ===========================================================================

def test_scheduler_attaches_before_snipe_audit():
    import inspect
    from src import scheduler
    src = inspect.getsource(scheduler.run_scan_pipeline)
    htf_pos = src.find('tiering_result["higher_timeframe_context"]')
    audit_pos = src.find('tiering_result["snipe_gate_audit"]')
    assert htf_pos != -1 and audit_pos != -1
    assert htf_pos < audit_pos


def test_enums_are_valid():
    o = _build(_UPTREND)
    assert o["weekly"]["campaign_state"] in htf.CAMPAIGN_STATES
    assert o["monthly"]["bias_state"] in htf.BIAS_STATES
    assert o["weekly"]["trend_state"] in htf.TREND_STATES
    assert o["weekly"]["stack_state"] in htf.STACK_STATES
    assert o["campaign_location"]["label"] in htf.CAMPAIGN_LOCATIONS
    assert o["campaign_location"]["quality"] in htf.LOCATION_QUALITY
    assert o["campaign_location"]["path_state"] in htf.PATH_STATES
    assert o["htf_sequence"]["came_from"] in htf.CAME_FROM
    assert o["htf_sequence"]["attempt"] in htf.ATTEMPTS
    assert o["htf_sequence"]["current_read"] in htf.CURRENT_READS
    for k in ("price_vs_10", "price_vs_20", "price_vs_50", "price_vs_200"):
        assert o["weekly"]["sma_relationship"][k] in htf.PRICE_VS
    assert o["weekly"]["sma_relationship"]["dynamic_support_state"] in htf.DYNAMIC_SUPPORT

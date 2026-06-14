"""Phase 14C.3 — Candle Evidence Quality Engine tests.

A candle is a completed auction receipt: bodies = accepted value, wicks =
rejected value, close = control, next candle = verdict. The engine must read
candle quality truthfully without choking valid A+ setups, and may only
RECOMMEND a bounded score_delta — never mutate raw score, tier, capital,
routing, suppression, or dedup.
"""

import copy

from src import candle_evidence as ce
from src import score_calibration as sc
from src.discord_alerts import format_alert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enr(open_, high, low, close, atr=None, volume_ratio=None, fvg=None, ob=None):
    e = {
        "current_open": open_,
        "current_high": high,
        "current_low": low,
        "current_price": close,
    }
    if atr is not None:
        e["atr"] = atr
    if volume_ratio is not None:
        e["volume_ratio"] = volume_ratio
    if fvg is not None:
        e["fvg"] = fvg
    if ob is not None:
        e["ob"] = ob
    return e


def _loc(zone_low=19.0, zone_high=21.0, zone_type="FVG", state="mid_zone_acceptance",
         scan_price=20.5, zone_mid=20.0, confirmation_level=21.0):
    return {
        "zone_type": zone_type,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_mid": zone_mid,
        "scan_price": scan_price,
        "location_state": state,
        "confirmation_level": confirmation_level,
        "display_text": f"{state} — next proof above {zone_high:.2f}.",
    }


def _tr(final_tier="SNIPE_IT", score=88, trade_location=None, candle=None,
        reason="Structure confirmed.", next_action="Enter on confirmation.",
        retest_status="confirmed", hold_status="confirmed", structure_event="MSS",
        risk_realism_state="healthy", overhead_status="clear",
        invalidation_level=18.5, **sig_extra):
    sig = {
        "ticker": "HPE", "score": score, "scan_price": 20.5, "zone_type": "FVG",
        "setup_family": "continuation", "structure_event": structure_event,
        "trend_state": "expansion", "risk_realism_state": risk_realism_state,
        "overhead_status": overhead_status, "retest_status": retest_status,
        "hold_status": hold_status, "risk_reward": 4.5,
        "sma_value_alignment": "supportive", "missing_conditions": [],
        "invalidation_level": invalidation_level,
        "invalidation_condition": "daily close below zone",
        "reason": reason, "next_action": next_action,
        "targets": [{"label": "T1", "level": 25.0, "reason": "pool"}],
    }
    sig.update(sig_extra)
    tr = {
        "final_tier": final_tier, "score": score, "safe_for_alert": final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT": "#snipe", "STARTER": "#starter",
            "NEAR_ENTRY": "#near", "WAIT": "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT": "full_quality_allowed", "STARTER": "starter_only",
            "NEAR_ENTRY": "wait_no_capital", "WAIT": "no_trade",
        }.get(final_tier, "no_trade"),
        "trajectory": {"label": "NEW_SIGNAL", "text": ""},
        "final_signal": sig,
    }
    if trade_location is not None:
        tr["trade_location"] = trade_location
    if candle is not None:
        tr["candle_evidence"] = candle
    return tr


# ===========================================================================
# 1. Metric math
# ===========================================================================

class TestMetricMath:
    def test_body_pct(self):
        ctx = ce.build_candle_evidence_context(_enr(10, 18, 8, 16))
        assert abs(ctx["body_pct"] - 0.6) < 1e-6

    def test_upper_lower_wick_pct(self):
        ctx = ce.build_candle_evidence_context(_enr(10, 18, 8, 16))
        assert abs(ctx["upper_wick_pct"] - 0.2) < 1e-6
        assert abs(ctx["lower_wick_pct"] - 0.2) < 1e-6

    def test_close_position_pct(self):
        ctx = ce.build_candle_evidence_context(_enr(10, 18, 8, 16))
        assert abs(ctx["close_position_pct"] - 0.8) < 1e-6

    def test_zero_range_does_not_raise(self):
        ctx = ce.build_candle_evidence_context(_enr(10, 10, 10, 10))
        assert ctx["status"] == "insufficient_data"
        assert ctx["candle_veto"] in ("NO_CLOSE_CONFIRMATION", "UNKNOWN")

    def test_range_atr_ratio(self):
        ctx = ce.build_candle_evidence_context(_enr(10, 20, 10, 19, atr=5.0))
        # range 10 / atr 5 = 2.0
        assert abs(ctx["range_atr_ratio"] - 2.0) < 1e-6

    def test_volume_ratio_from_bar(self):
        bars = [{"open": 10, "high": 20, "low": 8, "close": 18,
                 "volume": 150, "avg_volume": 100}]
        ctx = ce.build_candle_evidence_context({}, {}, bars=bars)
        assert abs(ctx["volume_ratio"] - 1.5) < 1e-6


# ===========================================================================
# 2. Candle family classification
# ===========================================================================

class TestCandleFamily:
    def test_dominant_bullish_body_displacement(self):
        ctx = ce.build_candle_evidence_context(_enr(20.0, 25.0, 19.8, 24.8, atr=2.0))
        assert ctx["candle_family"] == "DISPLACEMENT"
        assert ctx["close_quality"] == "STRONG_BULLISH_CLOSE"

    def test_dominant_bearish_body_displacement(self):
        ctx = ce.build_candle_evidence_context(_enr(25.0, 25.2, 20.0, 20.2, atr=2.0))
        assert ctx["candle_family"] == "DISPLACEMENT"
        assert ctx["close_quality"] == "STRONG_BEARISH_CLOSE"

    def test_doji_small_body_indecision(self):
        ctx = ce.build_candle_evidence_context(_enr(20.0, 20.6, 19.4, 20.05))
        assert ctx["candle_family"] == "DOJI_INDECISION"

    def test_high_volume_small_body_absorption(self):
        ctx = ce.build_candle_evidence_context(
            _enr(20.0, 20.5, 19.7, 20.1, atr=5.0, volume_ratio=1.6)
        )
        assert ctx["candle_family"] == "ABSORPTION"

    def test_lower_wick_at_fvg_rejection(self):
        # Dominant lower wick, small body, decent close → REJECTION.
        loc = _loc()
        tr = {"final_tier": "SNIPE_IT", "trade_location": loc, "final_signal": {}}
        ctx = ce.build_candle_evidence_context(_enr(20.5, 20.8, 19.1, 20.7), tr)
        assert ctx["candle_family"] == "REJECTION"

    def test_lower_wick_at_fvg_retest_hold(self):
        # Strong body, high close, holds zone, no dominant wick → RETEST_HOLD.
        loc = _loc()
        tr = {"final_tier": "SNIPE_IT", "trade_location": loc, "final_signal": {}}
        ctx = ce.build_candle_evidence_context(_enr(20.0, 20.8, 19.5, 20.7, atr=2.0), tr)
        assert ctx["candle_family"] == "RETEST_HOLD"

    def test_inside_candle_compression(self):
        bars = [{"open": 10, "high": 20, "low": 5, "close": 15},
                {"open": 12, "high": 18, "low": 8, "close": 14}]
        ctx = ce.build_candle_evidence_context({}, {}, bars=bars)
        assert ctx["candle_family"] == "INSIDE_COMPRESSION"

    def test_outside_candle_volatility(self):
        # Event engulfs prior range and closes mid → OUTSIDE_VOLATILITY/UNRESOLVED.
        bars = [{"open": 12, "high": 16, "low": 11, "close": 14},
                {"open": 13, "high": 18, "low": 9, "close": 13.5}]
        ctx = ce.build_candle_evidence_context({}, {}, bars=bars)
        assert ctx["candle_family"] in ("OUTSIDE_VOLATILITY", "UNRESOLVED")


# ===========================================================================
# 3. Next-candle verdict
# ===========================================================================

class TestNextCandleVerdict:
    def _retest_pair(self, next_close):
        # Event = bullish hold candle at zone; next candle close varies. The next
        # candle is given a real body (open well off the close) so it is never
        # mistaken for an indecision bar.
        event = {"open": 20.0, "high": 20.8, "low": 19.5, "close": 20.7, "atr": 2.0}
        nxt = {
            "open": 20.45,
            "high": max(next_close, 20.7) + 0.1,
            "low": min(next_close, 20.3) - 0.1,
            "close": next_close,
        }
        tr = {"final_tier": "SNIPE_IT",
              "trade_location": _loc(), "final_signal": {}}
        return ce.build_candle_evidence_context({}, tr, bars=[event, nxt], event_index=0)

    def test_hold_verdict(self):
        ctx = self._retest_pair(20.75)   # holds above failure, not beyond proof
        assert ctx["next_candle_verdict"] == "HOLD"

    def test_fail_verdict(self):
        ctx = self._retest_pair(18.9)    # closes below failure (zone_low 19.0)
        assert ctx["next_candle_verdict"] == "FAIL"

    def test_continuation_verdict(self):
        ctx = self._retest_pair(22.5)    # closes beyond proof level
        assert ctx["next_candle_verdict"] == "CONTINUATION"

    def test_pending_when_event_is_last_bar(self):
        bars = [{"open": 20.0, "high": 20.8, "low": 19.5, "close": 20.7}]
        ctx = ce.build_candle_evidence_context({}, {}, bars=bars)
        assert ctx["next_candle_verdict"] == "PENDING"

    def test_not_available_from_enriched_only(self):
        ctx = ce.build_candle_evidence_context(_enr(20.0, 25.0, 19.8, 24.8, atr=2.0))
        assert ctx["next_candle_verdict"] == "NOT_AVAILABLE"


# ===========================================================================
# 4. Tier safety
# ===========================================================================

class TestTierSafety:
    def test_snipe_doji_at_trigger_caution_and_negative_delta(self):
        loc = _loc()
        tr = _tr("SNIPE_IT", trade_location=loc)
        ctx = ce.build_candle_evidence_context(_enr(20.0, 20.6, 19.4, 20.05), tr)
        assert ctx["candle_family"] == "DOJI_INDECISION"
        assert ctx["candle_veto"] == "DOJI_AT_TRIGGER"
        assert ctx["score_delta"] < 0

    def test_starter_unresolved_no_elite_wording(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.5, 19.7, 20.1, atr=5.0, volume_ratio=1.6),
            _tr("STARTER", trade_location=loc),
        )
        tr = _tr("STARTER", trade_location=loc, candle=candle)
        body = format_alert(tr)
        assert "institutional-grade" not in body.lower()
        assert "Elite candidate" not in body

    def test_near_entry_watch_language_only(self):
        loc = _loc(state="lower_zone_defense")
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.6, 19.4, 20.05), _tr("NEAR_ENTRY", trade_location=loc)
        )
        tr = _tr("NEAR_ENTRY", trade_location=loc, candle=candle)
        body = format_alert(tr)
        assert "capital authorized" not in body.lower()
        assert "confirmed hold" not in body.lower()

    def test_snipe_hostile_upper_wick_veto(self):
        # Bullish setup but a dominant upper wick with a real (non-doji) body and
        # a weak bearish close = supply rejection (hostile), kept below zone_high
        # so it is a wick conflict, not a failed break.
        loc = _loc()
        tr = _tr("SNIPE_IT", trade_location=loc)
        ctx = ce.build_candle_evidence_context(_enr(20.0, 20.9, 19.4, 19.5, atr=2.0), tr)
        assert ctx["candle_veto"] == "HOSTILE_WICK"
        assert ctx["score_delta"] < 0


# ===========================================================================
# 5. Score calibration invariants
# ===========================================================================

class TestCalibrationInvariants:
    def _run(self, final_tier="SNIPE_IT", score=88, candle_enr=None, loc=None):
        loc = loc or _loc()
        tr = _tr(final_tier, score=score, trade_location=loc)
        enr = candle_enr or _enr(20.0, 20.6, 19.4, 20.05)  # doji default
        tr["candle_evidence"] = ce.build_candle_evidence_context(enr, tr)
        before = copy.deepcopy(tr)
        cal = sc.calibrate_score(tr)
        return before, tr, cal

    def test_raw_score_unchanged(self):
        before, after, cal = self._run(score=88)
        assert after["score"] == before["score"] == 88
        assert after["final_signal"]["score"] == 88
        assert cal["raw_score"] == 88

    def test_final_tier_unchanged(self):
        before, after, _ = self._run()
        assert after["final_tier"] == before["final_tier"]

    def test_capital_action_unchanged(self):
        before, after, _ = self._run()
        assert after["capital_action"] == before["capital_action"]

    def test_discord_channel_unchanged(self):
        before, after, _ = self._run()
        assert after["final_discord_channel"] == before["final_discord_channel"]

    def test_safe_for_alert_unchanged(self):
        before, after, _ = self._run()
        assert after["safe_for_alert"] == before["safe_for_alert"]

    def test_candle_veto_caps_below_elite(self):
        # High raw + doji veto on SNIPE_IT must not reach elite (>=90); unresolved
        # SNIPE_IT cap holds it at or below 88.
        _, _, cal = self._run(score=93)
        assert cal["calibrated_score"] <= 88

    def test_retest_hold_confirmed_not_candle_capped(self):
        # RETEST_HOLD + CONTINUATION verdict is exempt from candle caps.
        loc = _loc()
        tr = _tr("SNIPE_IT", score=92, trade_location=loc)
        event = {"open": 20.0, "high": 20.8, "low": 19.5, "close": 20.7, "atr": 2.0}
        nxt = {"open": 20.7, "high": 22.7, "low": 20.5, "close": 22.5}
        tr["candle_evidence"] = ce.build_candle_evidence_context(
            {}, tr, bars=[event, nxt], event_index=0
        )
        assert tr["candle_evidence"]["candle_family"] == "RETEST_HOLD"
        assert tr["candle_evidence"]["next_candle_verdict"] == "CONTINUATION"
        cal = sc.calibrate_score(tr)
        assert cal["calibrated_score"] >= 90

    def test_absent_candle_is_inert(self):
        tr_no = _tr("SNIPE_IT", score=85, trade_location=_loc())
        tr_unknown = _tr("SNIPE_IT", score=85, trade_location=_loc(),
                         candle=ce.build_candle_evidence_context({}, {}))
        a = sc.calibrate_score(tr_no)
        b = sc.calibrate_score(tr_unknown)
        assert a["calibrated_score"] == b["calibrated_score"]


# ===========================================================================
# 6. Discord display
# ===========================================================================

class TestDiscordDisplay:
    def test_candle_read_line_appears(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 25.0, 19.8, 24.8, atr=2.0), _tr("SNIPE_IT", trade_location=loc)
        )
        tr = _tr("SNIPE_IT", trade_location=loc, candle=candle)
        body = format_alert(tr)
        assert "Candle read:" in body

    def test_candle_caution_line_when_veto(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.6, 19.4, 20.05), _tr("SNIPE_IT", trade_location=loc)
        )
        tr = _tr("SNIPE_IT", trade_location=loc, candle=candle)
        body = format_alert(tr)
        assert "Candle caution:" in body
        assert "doji at trigger" in body.lower()

    def test_no_boolean_leak_with_candle(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.6, 19.4, 20.05), _tr("SNIPE_IT", trade_location=loc)
        )
        tr = _tr("SNIPE_IT", trade_location=loc, candle=candle,
                 reason="price_in_zone=True; structure confirmed.")
        body = format_alert(tr)
        assert "=True" not in body and "=False" not in body

    def test_starter_incomplete_candle_no_elite(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.6, 19.4, 20.05), _tr("STARTER", trade_location=loc)
        )
        tr = _tr("STARTER", trade_location=loc, candle=candle)
        body = format_alert(tr)
        assert "institutional-grade" not in body.lower()
        assert "High-quality STARTER" in body

    def test_no_all_conditions_satisfied_when_veto(self):
        loc = _loc()
        candle = ce.build_candle_evidence_context(
            _enr(20.0, 20.6, 19.4, 20.05), _tr("SNIPE_IT", trade_location=loc)
        )
        tr = _tr("SNIPE_IT", trade_location=loc, candle=candle,
                 reason="Structure confirmed; all conditions satisfied.")
        body = format_alert(tr)
        assert "all conditions satisfied" not in body.lower()

    def test_clean_retest_hold_no_caution(self):
        loc = _loc()
        event = {"open": 20.0, "high": 20.8, "low": 19.5, "close": 20.7, "atr": 2.0}
        nxt = {"open": 20.7, "high": 21.5, "low": 20.5, "close": 21.3}
        tr = _tr("SNIPE_IT", trade_location=loc)
        tr["candle_evidence"] = ce.build_candle_evidence_context(
            {}, tr, bars=[event, nxt], event_index=0
        )
        body = format_alert(tr)
        assert "Candle read:" in body
        assert "Candle caution:" not in body


# ===========================================================================
# 7. Production safety
# ===========================================================================

class TestProductionSafety:
    def test_missing_ohlcv_returns_unknown(self):
        ctx = ce.build_candle_evidence_context({}, {})
        assert ctx["status"] in ("insufficient_data", "unknown")
        assert ctx["candle_family"] in ("UNKNOWN",)
        assert ctx["score_delta"] == 0

    def test_malformed_data_does_not_raise(self):
        ctx = ce.build_candle_evidence_context(
            {"current_open": "x", "current_high": None, "current_low": [], "current_price": {}},
            {"final_signal": "not a dict"},
        )
        assert isinstance(ctx, dict)
        assert ctx["score_delta"] == 0

    def test_bars_with_none_entries_handled(self):
        bars = [None, {"open": 10, "high": 20, "low": 8, "close": 18}, "junk"]
        ctx = ce.build_candle_evidence_context({}, {}, bars=bars)
        assert isinstance(ctx, dict)
        assert ctx["status"] == "ok"

    def test_none_inputs_safe(self):
        ctx = ce.build_candle_evidence_context(None, None)
        assert isinstance(ctx, dict)
        assert ctx["candle_family"] == "UNKNOWN"

    def test_calibration_without_candle_key(self):
        # tiering_result that never had candle_evidence attached still calibrates.
        tr = _tr("SNIPE_IT", score=85, trade_location=_loc())
        assert "candle_evidence" not in tr
        cal = sc.calibrate_score(tr)
        assert cal["raw_score"] == 85
        assert isinstance(cal["calibrated_score"], int)

    def test_score_delta_bounded(self):
        # Even an extreme contradiction never exceeds the [-4, +3] envelope.
        loc = _loc()
        tr = _tr("SNIPE_IT", trade_location=loc)
        ctx = ce.build_candle_evidence_context(_enr(20.0, 20.6, 19.4, 20.05), tr)
        assert -4 <= ctx["score_delta"] <= 3

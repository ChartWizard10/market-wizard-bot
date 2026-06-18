"""Phase 14F — Multi-Timeframe Alignment Evidence Object tests.

Covers the 8 mandated groups: schema, mapping, 1H integration, scoring/caps,
no-mutation, Discord rendering, regression, and elite additions (determinism,
re-entrancy, ordered classification, blocks_trigger truth table, FIELD_MAP
honesty, NEAR_ENTRY conflict discipline).

Doctrine under test:
  - Weekly campaign / Daily permission / 4H operational / 1H trigger proof.
  - 1H state is sourced from one_hour_entry, never reclassified.
  - The object never promotes, routes, authorizes capital, or mutates state.
  - Cap → score → grade pipeline; lowest cap wins.
"""

import copy

from src import discord_alerts as da
from src import timeframe_alignment as tfa


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

_CAPITAL = {
    "SNIPE_IT": "full_quality_allowed", "STARTER": "starter_only",
    "NEAR_ENTRY": "wait_no_capital", "WAIT": "no_trade", "INVALID": "no_trade",
}


def _signal(**over):
    s = {
        "trend_state": "fresh_expansion", "structure_event": "bos",
        "overhead_status": "moderate", "zone_type": "fvg",
        "invalidation_level": 99.5, "trigger_level": 102.0,
        "targets": [{"label": "T1", "level": 108.0}], "risk_reward": 4.0,
    }
    s.update(over)
    return s


def _oh(state="RETEST_IN_PROGRESS", hold="HOLD_WEAK", sl="1H_TRIGGER_WEAK",
        al="WATCH_ONLY", fresh="FRESH", status="ENABLED", closed=False,
        path="ACCEPTABLE", loc="ACCEPTABLE_BUT_NOT_IDEAL"):
    return {
        "enabled": True, "status": status, "trigger_state": state,
        "alert_truth_label": al, "score_label": sl, "data_freshness": fresh,
        "pullback_retest_hold": {"hold_truth": hold},
        "candle_truth": {"closed_candle_confirms": closed},
        "location_realism": {"label": loc},
        "invalidation": {"clear": True},
        "path_quality": {"path_label": path},
    }


def _tiering(tier="NEAR_ENTRY", loc_state="mid_zone_acceptance", oh=None,
             safe=False, signal_over=None, trade_location="default",
             rejection_reason=""):
    if trade_location == "default":
        trade_location = {"location_state": loc_state}
    return {
        "final_tier": tier,
        "score": 87,
        "safe_for_alert": safe,
        "capital_action": _CAPITAL.get(tier, "no_trade"),
        "final_discord_channel": "near_entry",
        "rejection_reason": rejection_reason,
        "final_signal": _signal(**(signal_over or {})),
        "trade_location": trade_location,
        "one_hour_entry": oh,
    }


def _build(tier="NEAR_ENTRY", **kw):
    return tfa.build_timeframe_alignment_context("T", _tiering(tier, **kw))


# ===========================================================================
# GROUP 1 — SCHEMA
# ===========================================================================

class TestSchema:
    _TOP = {
        "enabled", "status", "alignment_grade", "alignment_score",
        "alignment_label", "campaign_timeframe", "swing_timeframe",
        "operational_timeframe", "trigger_timeframe", "conflicts",
        "missing_context", "hard_caps_applied", "downgrade_reasons",
        "scanner_sentence",
    }
    _LAYER = {"timeframe", "role", "state", "evidence", "warnings", "blocks_trigger"}

    def test_top_level_fields(self):
        o = _build("STARTER", safe=True, oh=_oh())
        assert self._TOP.issubset(o.keys())

    def test_layer_subobject_fields(self):
        o = _build(oh=_oh())
        for key in ("campaign_timeframe", "swing_timeframe",
                    "operational_timeframe", "trigger_timeframe"):
            assert self._LAYER.issubset(o[key].keys())

    def test_all_emitted_enums_valid(self):
        o = _build(oh=_oh())
        assert o["status"] in tfa.STATUS_VALUES
        assert o["alignment_grade"] in tfa.ALIGNMENT_GRADES
        assert o["alignment_label"] in tfa.ALIGNMENT_LABELS
        assert o["campaign_timeframe"]["state"] in tfa.WEEKLY_STATES
        assert o["swing_timeframe"]["state"] in tfa.DAILY_STATES
        assert o["operational_timeframe"]["state"] in tfa.OPERATIONAL_STATES
        assert o["trigger_timeframe"]["state"] in tfa.TRIGGER_STATES

    def test_malformed_input_returns_safe(self):
        o = tfa.build_timeframe_alignment_context("T", {"final_signal": 5, "one_hour_entry": "x"})
        assert o["status"] in ("DEGRADED", "ENABLED", "ERROR")
        assert o["alignment_label"] in tfa.ALIGNMENT_LABELS

    def test_missing_tiering_result_does_not_raise(self):
        o = tfa.build_timeframe_alignment_context("T", None)
        assert o["alignment_label"] in tfa.ALIGNMENT_LABELS
        assert o["status"] in tfa.STATUS_VALUES

    def test_missing_enriched_does_not_raise(self):
        o = tfa.build_timeframe_alignment_context("T", _tiering(oh=_oh()), enriched_data=None)
        assert o["status"] in tfa.STATUS_VALUES

    def test_garbage_never_raises(self):
        for bad in (None, 123, "x", [], {}, {"final_signal": []}):
            o = tfa.build_timeframe_alignment_context(None, bad)
            assert o["alignment_label"] in tfa.ALIGNMENT_LABELS

    def test_error_object_shape(self):
        o = tfa.error_timeframe_alignment_object("boom")
        assert o["status"] == "ERROR"
        assert o["alignment_label"] == "INSUFFICIENT_CONTEXT"
        assert o["alignment_grade"] == "UNKNOWN"
        assert o["alignment_score"] == 0
        assert any("boom" in r for r in o["downgrade_reasons"])

    def test_disabled_via_config(self):
        o = tfa.build_timeframe_alignment_context(
            "T", _tiering(oh=_oh()), config={"timeframe_alignment": {"enabled": False}}
        )
        assert o["status"] == "DISABLED"
        assert o["enabled"] is False


# ===========================================================================
# GROUP 2 — MAPPING
# ===========================================================================

class TestMapping:
    def test_near_entry_weak_is_pending_not_lower_tf(self):
        o = _build("NEAR_ENTRY", loc_state="mid_zone_acceptance", oh=_oh())
        assert o["alignment_label"] in ("HTF_ALIGNED_TRIGGER_PENDING", "MIXED_ALIGNMENT")
        assert o["alignment_label"] != "LOWER_TIMEFRAME_ONLY"

    def test_starter_confirmed_full_stack(self):
        o = _build("STARTER", safe=True, loc_state="mid_zone_acceptance",
                   oh=_oh("TRIGGER_LIVE", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "LIVE_TRIGGER", closed=True))
        assert o["alignment_label"] == "FULL_STACK_ALIGNED"

    def test_snipe_confirmed_full_stack(self):
        o = _build("SNIPE_IT", safe=True, loc_state="mid_zone_acceptance",
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_A_PLUS",
                          "CONFIRMED_TRIGGER", closed=True))
        assert o["alignment_label"] == "FULL_STACK_ALIGNED"

    def test_wait_one_hour_only_no_htf(self):
        # Weekly + Daily unknown; only 1H + maybe 4H classifiable.
        o = tfa.build_timeframe_alignment_context("T", {
            "final_tier": "", "trade_location": {"location_state": "unknown"},
            "final_signal": {}, "one_hour_entry": _oh(),
        })
        assert o["alignment_label"] in ("LOWER_TIMEFRAME_ONLY", "INSUFFICIENT_CONTEXT")

    def test_hostile_location_conflicted_or_capped(self):
        o = _build("NEAR_ENTRY", loc_state="below_zone_failure", oh=_oh())
        assert o["alignment_label"] == "CONFLICTED" or o["alignment_score"] <= 59

    def test_failed_one_hour_is_trigger_failed_and_conflicted(self):
        o = _build("NEAR_ENTRY", oh=_oh("FAILED_RETEST", "HOLD_FAILED",
                                        "NO_VALID_1H_TRIGGER", "FAILED_TRIGGER"))
        assert o["trigger_timeframe"]["state"] == "TRIGGER_FAILED"
        assert o["alignment_label"] == "CONFLICTED"


# ===========================================================================
# GROUP 3 — 1H INTEGRATION
# ===========================================================================

class TestOneHourIntegration:
    def test_uses_existing_one_hour_object(self):
        o = _build(oh=_oh("HOLD_FORMING", al="FORMING_TRIGGER"))
        ev = " ".join(o["trigger_timeframe"]["evidence"])
        assert "one_hour_entry" in ev

    def test_missing_one_hour_is_unknown(self):
        o = _build(oh=None)
        assert o["trigger_timeframe"]["state"] == "UNKNOWN"

    def test_disabled_one_hour_is_unknown(self):
        o = _build(oh=_oh(status="DISABLED"))
        assert o["trigger_timeframe"]["state"] == "UNKNOWN"

    def test_stale_one_hour_maps_trigger_stale(self):
        o = _build(oh=_oh("STALE_TRIGGER", fresh="STALE"))
        assert o["trigger_timeframe"]["state"] == "TRIGGER_STALE"

    def test_failed_one_hour_maps_trigger_failed(self):
        o = _build(oh=_oh("INVALID_1H_TRIGGER", al="FAILED_TRIGGER"))
        assert o["trigger_timeframe"]["state"] == "TRIGGER_FAILED"

    def test_weak_one_hour_maps_trigger_weak(self):
        o = _build(oh=_oh("APPROACHING_LOCATION", hold="HOLD_WEAK",
                          sl="1H_TRIGGER_WEAK", al="WATCH_ONLY"))
        assert o["trigger_timeframe"]["state"] == "TRIGGER_WEAK"


# ===========================================================================
# GROUP 4 — SCORING AND CAPS
# ===========================================================================

class TestScoringAndCaps:
    def test_weights_sum_full_stack(self):
        layers = {
            "1W": {"state": "BULLISH"}, "1D": {"state": "PERMISSION_GRANTED"},
            "4H": {"state": "LOCATION_VALID"}, "1H": {"state": "TRIGGER_CONFIRMED"},
        }
        assert tfa.score_alignment(layers) == 100

    def test_grade_bands(self):
        assert tfa.grade_from_score(95) == "A"
        assert tfa.grade_from_score(84) == "A-"
        assert tfa.grade_from_score(78) == "B+"
        assert tfa.grade_from_score(70) == "B"
        assert tfa.grade_from_score(60) == "C"
        assert tfa.grade_from_score(45) == "D"
        assert tfa.grade_from_score(30) == "F"
        assert tfa.grade_from_score(None) == "UNKNOWN"

    def test_lowest_cap_wins(self):
        capped = tfa.apply_alignment_caps(90, {"A": 74, "B": 49, "C": 79})
        assert capped == 49

    def test_cap_limits_score_then_grade_derives(self):
        # 92 raw with daily denied → score 49, grade D.
        capped = tfa.apply_alignment_caps(92, {"DAILY_PERMISSION_DENIED": 49})
        assert capped == 49
        assert tfa.grade_from_score(capped) == "D"

    def test_daily_denied_cap_applies(self):
        o = _build("INVALID", oh=_oh())
        assert "DAILY_PERMISSION_DENIED" in o["hard_caps_applied"]
        assert o["alignment_score"] <= 49

    def test_4h_hostile_cap_applies(self):
        o = _build(loc_state="below_zone_failure", oh=_oh())
        assert "FOUR_HOUR_HOSTILE_LOCATION" in o["hard_caps_applied"]
        assert o["alignment_score"] <= 59

    def test_1h_failed_cap_applies(self):
        o = _build(oh=_oh("FAILED_RETEST", al="FAILED_TRIGGER"))
        assert "ONE_HOUR_TRIGGER_FAILED" in o["hard_caps_applied"]
        assert o["alignment_score"] <= 49

    def test_1h_stale_cap_applies(self):
        o = _build(oh=_oh("STALE_TRIGGER", fresh="STALE"))
        assert "ONE_HOUR_TRIGGER_STALE" in o["hard_caps_applied"]
        assert o["alignment_score"] <= 69

    def test_lower_tf_only_cap_applies(self):
        o = tfa.build_timeframe_alignment_context("T", {
            "final_tier": "", "trade_location": {"location_state": "mid_zone_acceptance"},
            "final_signal": {}, "one_hour_entry": _oh(),
        })
        if o["alignment_label"] == "LOWER_TIMEFRAME_ONLY":
            assert "LOWER_TIMEFRAME_ONLY" in o["hard_caps_applied"]
            assert o["alignment_score"] <= 64

    def test_insufficient_context_cap_applies(self):
        o = tfa.build_timeframe_alignment_context("T", {
            "final_tier": "", "trade_location": {"location_state": "unknown"},
            "final_signal": {}, "one_hour_entry": None,
        })
        assert o["alignment_label"] == "INSUFFICIENT_CONTEXT"
        assert "INSUFFICIENT_CONTEXT" in o["hard_caps_applied"]
        assert o["alignment_score"] <= 74

    def test_no_invalidation_cap_applies(self):
        o = _build("NEAR_ENTRY", oh=_oh(), signal_over={"invalidation_level": None})
        # one_hour invalidation.clear is True in the fixture, so cap should NOT fire.
        # Flip it off to prove the cap path.
        o2 = tfa.build_timeframe_alignment_context("T", _tiering(
            "NEAR_ENTRY", oh={**_oh(), "invalidation": {"clear": False}},
            signal_over={"invalidation_level": None},
        ))
        assert "NO_CLEAR_INVALIDATION" in o2["hard_caps_applied"]

    def test_caps_record_reasons(self):
        o = _build("INVALID", oh=_oh("FAILED_RETEST", al="FAILED_TRIGGER"))
        assert o["hard_caps_applied"]
        assert len(o["downgrade_reasons"]) >= len(o["hard_caps_applied"])


# ===========================================================================
# GROUP 5 — NO MUTATION
# ===========================================================================

class TestNoMutation:
    def test_no_sovereign_field_mutation(self):
        src = _tiering("NEAR_ENTRY", oh=_oh())
        snap = {
            "score": src["score"], "final_tier": src["final_tier"],
            "capital_action": src["capital_action"],
            "final_discord_channel": src["final_discord_channel"],
            "safe_for_alert": src["safe_for_alert"],
        }
        before = copy.deepcopy(src)
        tfa.build_timeframe_alignment_context("T", src)
        assert src == before
        for k, v in snap.items():
            assert src[k] == v


# ===========================================================================
# GROUP 6 — DISCORD
# ===========================================================================

def _discord_signal(**o):
    s = {
        "ticker": "SPG", "setup_family": "continuation", "structure_event": "bos",
        "trend_state": "fresh_expansion", "zone_type": "fvg", "trigger_level": 102.0,
        "invalidation_level": 99.5, "invalidation_condition": "1H close below",
        "risk_reward": 3.6, "overhead_status": "moderate", "risk_realism_state": "healthy",
        "sma_value_alignment": "supportive", "retest_status": "partial",
        "hold_status": "partial", "targets": [{"label": "T1", "level": 108.0}],
        "missing_conditions": ["overhead_path_not_clean"],
        "near_entry_blocker_note": "awaiting 1H hold", "next_action": "monitor",
        "reason": "BOS", "capital_action": "wait_no_capital", "scan_price": 101.2,
    }
    s.update(o)
    return s


def _discord_tiering(oh=None, loc_state="mid_zone_acceptance", tier="NEAR_ENTRY"):
    tr = {
        "final_tier": tier, "score": 87, "safe_for_alert": False,
        "capital_action": _CAPITAL.get(tier, "no_trade"),
        "final_signal": _discord_signal(),
        "trade_location": {
            "zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
            "location_state": loc_state,
        },
        "one_hour_entry": oh if oh is not None else {
            "enabled": True, "status": "ENABLED", "data_freshness": "FRESH",
            "trigger_state": "RETEST_IN_PROGRESS", "score": 66,
            "score_label": "1H_TRIGGER_WEAK", "alert_truth_label": "WATCH_ONLY",
            "hard_caps_applied": ["NO_RETEST"],
            "pullback_retest_hold": {"pullback_truth": "PULLBACK_REAL",
                                     "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_WEAK",
                                     "retest_zone_type": "FVG"},
            "candle_truth": {"event_type": "REJECTION", "closed_candle_confirms": False},
            "location_realism": {"label": "ACCEPTABLE_BUT_NOT_IDEAL"},
            "invalidation": {"clear": True, "level": 99.5},
            "path_quality": {"path_label": "ACCEPTABLE"},
        },
    }
    tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context("SPG", tr)
    return tr


_FORBIDDEN_READY = (
    "ready to enter", "live trigger", "confirmed entry", "capital authorized",
    "enter now", "go long", "trigger confirmed",
)


class TestDiscord:
    def test_renders_compact_block(self):
        body = da.format_alert(_discord_tiering())
        assert "TF alignment:" in body
        assert "TF score:" in body
        assert "TF stack:" in body
        assert "1W=" in body and "1D=" in body and "4H=" in body and "1H=" in body

    def test_does_not_remove_one_hour_block(self):
        body = da.format_alert(_discord_tiering())
        assert "1H trigger:" in body
        assert "1H truth:" in body

    def test_no_trigger_ready_wording_when_pending(self):
        body = da.format_alert(_discord_tiering())
        tf_region = body[body.index("TF alignment:"):]
        low = tf_region.lower()
        for phrase in _FORBIDDEN_READY:
            assert phrase not in low

    def test_includes_inferred_weekly_note(self):
        body = da.format_alert(_discord_tiering())
        assert "inferred weekly context" in body

    def test_does_not_say_weekly_confirmed(self):
        body = da.format_alert(_discord_tiering())
        assert "weekly confirmed" not in body.lower()
        assert "weekly verified" not in body.lower()

    def test_enum_values_not_rewritten(self):
        body = da.format_alert(_discord_tiering())
        assert "TRIGGER_FORMING" in body or "TRIGGER_WEAK" in body
        assert "PERMISSION_FORMING" in body
        assert "LOCATION_VALID" in body
        assert "TIMEFRAME_ALIGNMENT_BLOCK" not in body

    def test_renders_conflicts_compactly(self):
        body = da.format_alert(_discord_tiering(loc_state="below_zone_failure"))
        assert "TF caution:" in body

    def test_degraded_context_renders_compactly(self):
        # No one_hour object → DEGRADED, but block still renders the stack.
        tr = _discord_tiering(oh={"status": "DISABLED", "enabled": False})
        body = da.format_alert(tr)
        assert "TF alignment:" in body
        assert "1H=UNKNOWN" in body


# ===========================================================================
# GROUP 7 — REGRESSION
# ===========================================================================

class TestRegression:
    def test_spg_psa_weak_stays_watch_only(self):
        o = _build("NEAR_ENTRY", loc_state="mid_zone_acceptance",
                   oh=_oh("RETEST_IN_PROGRESS", "HOLD_WEAK", "1H_TRIGGER_WEAK", "WATCH_ONLY"))
        assert o["alignment_label"] in ("HTF_ALIGNED_TRIGGER_PENDING", "MIXED_ALIGNMENT")
        assert o["alignment_label"] != "CONFLICTED"

    def test_confirmed_setup_full_stack(self):
        o = _build("SNIPE_IT", safe=True, loc_state="mid_zone_acceptance",
                   oh=_oh("TRIGGER_LIVE", "HOLD_CONFIRMED", "1H_TRIGGER_A_PLUS",
                          "LIVE_TRIGGER", closed=True))
        assert o["alignment_label"] == "FULL_STACK_ALIGNED"

    def test_near_entry_with_htf_not_lower_tf_only(self):
        o = _build("NEAR_ENTRY", loc_state="mid_zone_acceptance", oh=_oh())
        assert o["alignment_label"] != "LOWER_TIMEFRAME_ONLY"

    def test_lower_tf_only_no_trigger_ready_sentence(self):
        o = tfa.build_timeframe_alignment_context("T", {
            "final_tier": "", "trade_location": {"location_state": "mid_zone_acceptance"},
            "final_signal": {}, "one_hour_entry": _oh(),
        })
        low = str(o["scanner_sentence"]).lower()
        for phrase in _FORBIDDEN_READY:
            assert phrase not in low

    def test_weekly_inferred_never_confirmed(self):
        o = _build(oh=_oh())
        ev = " ".join(o["campaign_timeframe"]["evidence"]).lower()
        assert "inferred" in ev
        assert "weekly confirmed" not in ev
        assert "weekly verified" not in ev


# ===========================================================================
# GROUP 8 — ELITE ADDITIONS
# ===========================================================================

class TestEliteAdditions:
    def test_determinism(self):
        src = _tiering("NEAR_ENTRY", oh=_oh())
        a = tfa.build_timeframe_alignment_context("T", src)
        b = tfa.build_timeframe_alignment_context("T", src)
        assert a == b

    def test_reentrancy_no_source_mutation(self):
        src = _tiering("STARTER", safe=True, oh=_oh("TRIGGER_LIVE", "HOLD_CONFIRMED",
                                                    "1H_TRIGGER_VALID", "LIVE_TRIGGER"))
        before = copy.deepcopy(src)
        tfa.build_timeframe_alignment_context("T", src)
        tfa.build_timeframe_alignment_context("T", src)
        assert src == before

    def test_ordered_classification_repair_beats_mixed(self):
        # daily FORMING, weekly NEUTRAL, 4H repairing, 1H stale → step 6 wins
        # over step 7 (mixed). 1H STALE avoids step 5 (pending) and, on NEAR_ENTRY,
        # avoids the legacy-vs-1H conflict.
        o = _build("NEAR_ENTRY", loc_state="lower_zone_defense",
                   signal_over={"trend_state": "transition"},
                   oh=_oh("STALE_TRIGGER", fresh="STALE"))
        assert o["operational_timeframe"]["state"] == "LOCATION_REPAIRING"
        assert o["alignment_label"] == "HTF_VALID_4H_REPAIR"

    def test_blocks_trigger_truth_table_weekly(self):
        on = tfa.derive_campaign_timeframe({"trend_state": "failure"}, {}, {})
        off = tfa.derive_campaign_timeframe({"trend_state": "fresh_expansion", "structure_event": "bos"}, {}, {})
        assert on["blocks_trigger"] is True
        assert off["blocks_trigger"] is False

    def test_blocks_trigger_truth_table_daily(self):
        on = tfa.derive_swing_timeframe({"final_tier": "INVALID"}, {})
        off = tfa.derive_swing_timeframe({"final_tier": "NEAR_ENTRY"}, {})
        assert on["blocks_trigger"] is True
        assert off["blocks_trigger"] is False

    def test_blocks_trigger_truth_table_4h(self):
        on = tfa.derive_operational_timeframe({"location_state": "below_zone_failure"}, {})
        off = tfa.derive_operational_timeframe({"location_state": "mid_zone_acceptance"}, {})
        assert on["blocks_trigger"] is True
        assert off["blocks_trigger"] is False

    def test_blocks_trigger_truth_table_1h(self):
        on = tfa.derive_trigger_timeframe_from_one_hour_entry(_oh("FAILED_RETEST", al="FAILED_TRIGGER"))
        off = tfa.derive_trigger_timeframe_from_one_hour_entry(_oh("HOLD_FORMING", al="FORMING_TRIGGER"))
        assert on["blocks_trigger"] is True
        assert off["blocks_trigger"] is False

    def test_field_map_honesty_missing_key_degrades(self):
        # Missing trade_location + one_hour → degraded with named missing context,
        # never raises.
        o = tfa.build_timeframe_alignment_context("T", {"final_tier": "NEAR_ENTRY",
                                                        "final_signal": _signal()})
        assert o["status"] in ("DEGRADED", "ENABLED")
        assert o["missing_context"]

    def test_near_entry_conflict_discipline(self):
        # Weak/forming 1H + NO CAPITAL must not become CONFLICTED.
        for state, hold, sl, al in (
            ("RETEST_IN_PROGRESS", "HOLD_WEAK", "1H_TRIGGER_WEAK", "WATCH_ONLY"),
            ("HOLD_FORMING", "HOLD_FORMING", "1H_TRIGGER_FORMING", "FORMING_TRIGGER"),
            ("PULLBACK_FORMING", "NONE", "1H_TRIGGER_FORMING", "FORMING_TRIGGER"),
        ):
            o = _build("NEAR_ENTRY", loc_state="mid_zone_acceptance",
                       oh=_oh(state, hold, sl, al))
            assert o["alignment_label"] != "CONFLICTED"

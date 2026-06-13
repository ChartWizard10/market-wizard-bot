"""Phase 14C.2 — Alert Truth Contract / Capital Language Cleanup tests.

The Discord alert is an execution contract. It must not leak internal booleans,
overstate STARTER as elite, frame a repeated SNIPE_IT as a fresh opportunity,
conflate risk invalidation with deep zone failure, call a wider stop a "trail
stop", or imply add/full aggression before the next proof level is reclaimed.

All cleanup is display-only — tier, capital_action, routing, suppression, and
the raw score are never touched.
"""

import copy

from src.discord_alerts import (
    format_alert,
    _sanitize_boolean_debug_fragments,
    _sanitize_trail_stop_language,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loc(
    location_state="mid_zone_acceptance",
    zone_type="FVG",
    zone_low=44.575,
    zone_mid=49.0225,
    zone_high=53.47,
    scan_price=45.51,
    confirmation_level=49.0225,
    display_text="mid-zone acceptance — next proof above 53.47.",
) -> dict:
    return {
        "zone_type": zone_type,
        "zone_low": zone_low,
        "zone_mid": zone_mid,
        "zone_high": zone_high,
        "scan_price": scan_price,
        "position_in_zone_pct": 30.0,
        "location_state": location_state,
        "confirmation_level": confirmation_level,
        "invalidation_distance_pct": 3.3,
        "location_pressure": "normal",
        "display_text": display_text,
        "flags": [],
    }


def _tr(
    final_tier="SNIPE_IT",
    score=88,
    reason="Structure confirmed; dip toward 49.02 expected.",
    next_action="Enter on confirmation.",
    invalidation_level=44.0,
    trajectory_label="NEW_SIGNAL",
    trade_location=None,
    retest_status="confirmed",
    hold_status="confirmed",
    structure_event="MSS",
    risk_realism_state="healthy",
    overhead_status="clear",
    sma_value_alignment="supportive",
    risk_reward=4.5,
    **signal_extra,
) -> dict:
    sig = {
        "ticker": "HPE",
        "score": score,
        "scan_price": 45.51,
        "zone_type": "FVG",
        "setup_family": "continuation",
        "structure_event": structure_event,
        "trend_state": "expansion",
        "risk_realism_state": risk_realism_state,
        "overhead_status": overhead_status,
        "retest_status": retest_status,
        "hold_status": hold_status,
        "risk_reward": risk_reward,
        "sma_value_alignment": sma_value_alignment,
        "missing_conditions": [],
        "invalidation_level": invalidation_level,
        "invalidation_condition": "daily body close below zone",
        "reason": reason,
        "next_action": next_action,
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
    }
    sig.update(signal_extra)
    tr = {
        "final_tier": final_tier,
        "score": score,
        "safe_for_alert": final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT": "#snipe-signals",
            "STARTER": "#starter-signals",
            "NEAR_ENTRY": "#near-entry-watch",
            "WAIT": "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT": "full_quality_allowed",
            "STARTER": "starter_only",
            "NEAR_ENTRY": "wait_no_capital",
            "WAIT": "no_trade",
        }.get(final_tier, "no_trade"),
        "trajectory": {"label": trajectory_label, "text": ""},
        "final_signal": sig,
    }
    if trade_location is not None:
        tr["trade_location"] = trade_location
    return tr


# ---------------------------------------------------------------------------
# 1. Boolean / debug-fragment leak sanitizer
# ---------------------------------------------------------------------------

class TestBooleanLeakSanitizer:
    def test_humanized_zone_true_leak_rewritten(self):
        out = _sanitize_boolean_debug_fragments("Price has not returned to the zone=True")
        assert "=True" not in out and "=true" not in out
        assert "=False" not in out
        assert "returned to the active zone" in out.lower()

    def test_raw_zone_booleans_rewritten(self):
        out = _sanitize_boolean_debug_fragments(
            "price_at_ob=True and price_at_fvg=False right now"
        )
        assert "=True" not in out and "=False" not in out
        assert "True" not in out and "False" not in out

    def test_generic_field_bool_stripped(self):
        out = _sanitize_boolean_debug_fragments("setup_valid=True; momentum strong")
        assert "=True" not in out
        assert "momentum strong" in out

    def test_empty_input_safe(self):
        assert _sanitize_boolean_debug_fragments("") == ""

    def test_no_leak_in_full_alert_body(self):
        tr = _tr(reason="price_in_zone=True, structure confirmed.")
        body = format_alert(tr, {"reason": "new_signal"}, "scan_1")
        assert "=True" not in body
        assert "=False" not in body

    def test_alignment_spacing_preserved(self):
        # Full-body pass must not collapse the column-alignment whitespace.
        tr = _tr()
        body = format_alert(tr, {"reason": "new_signal"}, "scan_1")
        assert "  Trigger:" in body
        assert "EXECUTION" in body


# ---------------------------------------------------------------------------
# 2. STARTER quality heat control
# ---------------------------------------------------------------------------

class TestStarterQualityHeat:
    def test_starter_says_high_quality_starter(self):
        tr = _tr(final_tier="STARTER")
        body = format_alert(tr)
        assert "High-quality STARTER" in body

    def test_starter_states_full_size_not_granted(self):
        tr = _tr(final_tier="STARTER")
        body = format_alert(tr)
        assert "full-size confirmation not granted" in body

    def test_starter_not_elite_institutional(self):
        tr = _tr(final_tier="STARTER")
        body = format_alert(tr)
        assert "Elite candidate" not in body
        assert "all five quality dimensions institutional-grade" not in body
        assert "institutional-grade" not in body.lower()

    def test_starter_high_quality_label_survives_language_guard(self):
        # The guard cools generic "high-quality" prose but exempts the tier label.
        tr = _tr(final_tier="STARTER", reason="high-quality breakout in progress.")
        body = format_alert(tr)
        assert "High-quality STARTER" in body
        # Generic prestige "high-quality" elsewhere is still cooled.
        assert "high-quality breakout" not in body.lower()


# ---------------------------------------------------------------------------
# 3. Repeated SNIPE_IT signal language realism
# ---------------------------------------------------------------------------

class TestRepeatedSignalLanguage:
    def test_repeated_snipe_thesis_language(self):
        tr = _tr(final_tier="SNIPE_IT", trajectory_label="REPEATED_NO_CHANGE")
        body = format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        assert "thesis remains valid" in body
        assert "Repeated:" in body

    def test_repeated_snipe_not_framed_as_fresh(self):
        tr = _tr(final_tier="SNIPE_IT", trajectory_label="REPEATED_NO_CHANGE")
        body = format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        assert "fresh new opportunity" not in body.lower()
        # scan-time verification reminder present
        assert "verify current price before action" in body.lower()

    def test_cooldown_expired_triggers_repeated_even_if_new_signal(self):
        tr = _tr(final_tier="SNIPE_IT", trajectory_label="NEW_SIGNAL")
        body = format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        assert "Repeated:" in body

    def test_fresh_signal_has_no_repeated_line(self):
        tr = _tr(final_tier="SNIPE_IT", trajectory_label="NEW_SIGNAL")
        body = format_alert(tr, {"reason": "new_signal"}, "scan_1")
        assert "Repeated:" not in body

    def test_repeated_starter_generic_language(self):
        tr = _tr(final_tier="STARTER", trajectory_label="REPEATED_NO_CHANGE")
        body = format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        assert "no new aggression unless next proof confirms" in body


# ---------------------------------------------------------------------------
# 4. Invalidation-level separation
# ---------------------------------------------------------------------------

class TestInvalidationSeparation:
    def test_deep_zone_failure_named_separately(self):
        loc = _loc(location_state="lower_zone_defense", zone_low=19.10)
        tr = _tr(invalidation_level=21.94, trade_location=loc)
        body = format_alert(tr)
        assert "Deep FVG failure: 19.10" in body
        # Risk invalidation line still names its own level.
        assert "Invalidation:" in body
        assert "21.94" in body

    def test_levels_not_conflated_on_one_line(self):
        loc = _loc(location_state="lower_zone_defense", zone_low=19.10)
        tr = _tr(invalidation_level=21.94, trade_location=loc)
        body = format_alert(tr)
        inval_lines = [ln for ln in body.splitlines() if "Invalidation:" in ln]
        assert inval_lines and "19.10" not in inval_lines[0]

    def test_no_deep_line_when_zone_equals_invalidation(self):
        loc = _loc(location_state="mid_zone_acceptance", zone_low=21.94)
        tr = _tr(invalidation_level=21.94, trade_location=loc)
        body = format_alert(tr)
        assert "Deep FVG failure" not in body

    def test_no_deep_line_when_zone_above_invalidation(self):
        # Deep-failure level must be BELOW the risk stop to be a deep failure.
        loc = _loc(location_state="mid_zone_acceptance", zone_low=44.575)
        tr = _tr(invalidation_level=44.0, trade_location=loc)
        body = format_alert(tr)
        assert "Deep FVG failure" not in body


# ---------------------------------------------------------------------------
# 5. Trail-stop wording safety
# ---------------------------------------------------------------------------

class TestTrailStopSafety:
    def test_trail_stop_below_invalidation_relabelled(self):
        out = _sanitize_trail_stop_language("Trail stop below 19.10 protects size.", 21.94)
        assert "trail stop" not in out.lower()
        assert "deep failure reference" in out

    def test_trail_stop_above_invalidation_preserved(self):
        # A stop that tightens risk (above the invalidation) keeps trail wording.
        out = _sanitize_trail_stop_language("Trail stop to 25.00 once TP1 hits.", 21.94)
        assert "trail stop" in out.lower()
        assert "deep failure reference" not in out

    def test_trail_stop_in_full_alert_body(self):
        tr = _tr(reason="Trail stop below 19.10 caps risk.", invalidation_level=21.94)
        body = format_alert(tr)
        assert "deep failure reference" in body
        # The EXIT STRATEGY "Trail:" management line is a different construct.
        assert "Trail stop below 19.10" not in body

    def test_no_level_trail_stop_unchanged(self):
        # No numeric level → cannot assert it widens risk → leave wording intact.
        out = _sanitize_trail_stop_language("Use a trail stop after TP1.", 21.94)
        assert "trail stop" in out.lower()


# ---------------------------------------------------------------------------
# 6. Location-proof consistency
# ---------------------------------------------------------------------------

class TestLocationProofConsistency:
    def test_mid_zone_proof_note_present(self):
        loc = _loc(
            location_state="mid_zone_acceptance",
            confirmation_level=53.47,
            scan_price=49.50,
            display_text="mid-zone acceptance — next proof above 53.47.",
        )
        tr = _tr(final_tier="SNIPE_IT", trade_location=loc)
        body = format_alert(tr)
        assert "acceptance above 53.47" in body
        assert "next proof above" in body.lower()

    def test_mid_zone_does_not_imply_add_before_proof(self):
        loc = _loc(
            location_state="mid_zone_acceptance",
            confirmation_level=53.47,
            scan_price=49.50,
        )
        tr = _tr(final_tier="SNIPE_IT", trade_location=loc)
        body = format_alert(tr)
        assert "waits for" in body.lower()
        assert "add now" not in body.lower()
        assert "full size now" not in body.lower()

    def test_starter_mid_zone_add_waits(self):
        loc = _loc(
            location_state="mid_zone_acceptance",
            confirmation_level=53.47,
            scan_price=49.50,
        )
        tr = _tr(final_tier="STARTER", trade_location=loc)
        body = format_alert(tr)
        assert "add waits for acceptance above 53.47" in body

    def test_proof_note_absent_when_confirmation_below_price(self):
        loc = _loc(
            location_state="mid_zone_acceptance",
            confirmation_level=48.0,
            scan_price=49.50,
        )
        tr = _tr(final_tier="SNIPE_IT", trade_location=loc)
        body = format_alert(tr)
        assert "Proof:" not in body


# ---------------------------------------------------------------------------
# 7. No tier / capital / routing / suppression / raw-score mutation
# ---------------------------------------------------------------------------

class TestNoMutation:
    def _run_all_paths(self, tr):
        before = copy.deepcopy(tr)
        format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        return before, tr

    def test_decision_fields_unchanged(self):
        loc = _loc(location_state="lower_zone_defense", zone_low=19.10)
        tr = _tr(final_tier="STARTER", invalidation_level=21.94,
                 trade_location=loc, trajectory_label="REPEATED_NO_CHANGE",
                 reason="price_in_zone=True; Trail stop below 19.10.")
        before, after = self._run_all_paths(tr)
        for key in ("final_tier", "capital_action", "final_discord_channel",
                    "safe_for_alert", "score"):
            assert before[key] == after[key]

    def test_raw_signal_score_unchanged(self):
        tr = _tr(final_tier="SNIPE_IT", score=88)
        before = tr["final_signal"]["score"]
        format_alert(tr, {"reason": "cooldown_expired"}, "scan_1")
        assert tr["final_signal"]["score"] == before

    def test_trade_location_not_mutated(self):
        loc = _loc(location_state="mid_zone_acceptance", confirmation_level=53.47,
                   scan_price=49.50)
        tr = _tr(final_tier="SNIPE_IT", trade_location=loc)
        before = copy.deepcopy(loc)
        format_alert(tr)
        assert tr["trade_location"] == before

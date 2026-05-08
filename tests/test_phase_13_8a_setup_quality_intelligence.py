"""Phase 13.8A — Setup Quality Intelligence / A+ Discrimination Layer tests.

Covers:
  _evaluate_setup_quality()  — quality label assignment across all signal states
  format_alert() integration — "Quality read:" line present in ACTION section,
                               correct phrase per quality label, no tier/capital
                               side-effects, regression guard for prior content
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _evaluate_setup_quality,
    _QUALITY_LABEL_PHRASES,
    format_alert,
)

# ---------------------------------------------------------------------------
# Signal factories
# ---------------------------------------------------------------------------


def _base_signal(**overrides) -> dict:
    """Minimal final_signal dict with all fields needed by _evaluate_setup_quality()."""
    base = {
        "ticker": "TEST",
        "tier": "SNIPE_IT",
        "score": 88,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "zone_type": "OB",
        "trigger_level": 200.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below OB",
        "invalidation_level": 195.00,
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "sma_value_alignment": "supportive",
        "forced_participation": "none",
        "next_action": "Enter at trigger.",
        "capital_action": "full_quality_allowed",
        "reason": "Clean BOS with retest and hold.",
        "missing_conditions": [],
        "upgrade_trigger": "",
        "targets": [{"label": "T1", "level": 210.00, "reason": "prior high"}],
        "discord_channel": "#snipe-signals",
        "risk_realism_state": "healthy",
        "risk_realism_note": "Risk window is healthy.",
        "risk_distance": 5.00,
        "risk_distance_pct": 2.50,
        "current_price_to_invalidation": 8.00,
        "current_price_to_invalidation_pct": 4.00,
        "scan_price": 198.00,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "Signal based on scan-time price; verify live chart before entry.",
    }
    base.update(overrides)
    return base


def _tiering_result(final_tier: str, **signal_overrides) -> dict:
    """Build a minimal tiering_result dict for format_alert()."""
    sig = _base_signal(**signal_overrides)
    sig["tier"] = final_tier
    # Force capital_action and discord_channel to match tier
    cap_map = {
        "SNIPE_IT": "full_quality_allowed",
        "STARTER": "starter_only",
        "NEAR_ENTRY": "wait_no_capital",
        "WAIT": "no_trade",
    }
    chan_map = {
        "SNIPE_IT": "#snipe-signals",
        "STARTER": "#starter-signals",
        "NEAR_ENTRY": "#near-entry-watch",
        "WAIT": "none",
    }
    sig["capital_action"] = cap_map.get(final_tier, "no_trade")
    sig["discord_channel"] = chan_map.get(final_tier, "none")
    return {
        "final_tier": final_tier,
        "score": sig["score"],
        "ticker": sig["ticker"],
        "final_signal": sig,
    }


def _ne_tiering_result(**signal_overrides) -> dict:
    """NEAR_ENTRY tiering_result with NEAR_ENTRY-appropriate defaults."""
    defaults = {
        "retest_status": "partial",
        "hold_status": "missing",
        "risk_reward": None,
        "risk_realism_state": "unknown",
        "missing_conditions": ["retest_confirmed", "hold_confirmed"],
        "upgrade_trigger": "Confirmed retest and hold of FVG.",
        "next_action": "Watch for retest confirmation.",
        "reason": "Structure repair in progress; no zone acceptance yet.",
        "near_entry_blocker_note": (
            "Blocker: retest is not fully confirmed; "
            "wait for full zone interaction and hold."
        ),
        "score": 62,
    }
    defaults.update(signal_overrides)
    return _tiering_result("NEAR_ENTRY", **defaults)


# ===========================================================================
# _evaluate_setup_quality — unit tests
# ===========================================================================


class TestEvaluateSetupQuality:
    """Direct unit tests for _evaluate_setup_quality()."""

    # ---- A_PLUS_CANDIDATE ----

    def test_a_plus_all_clean(self):
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    def test_a_plus_tight_risk_is_still_a_plus(self):
        """Tight risk does not prevent A+; only fragile/invalid/unknown does."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="tight",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    def test_a_plus_moderate_overhead_not_blocking(self):
        """Moderate overhead without a blocker note keyword is not a blocker → A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="moderate",
            sma_value_alignment="supportive",
            near_entry_blocker_note="",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    def test_a_plus_sma_unavailable_treated_as_ok(self):
        """SMA unavailable is not 'hostile' — does not prevent A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="unavailable",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    def test_a_plus_sma_mixed_treated_as_ok(self):
        """Mixed SMA is not 'hostile' — does not prevent A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="mixed",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    # ---- CLEAN_STARTER ----

    def test_clean_starter_fragile_risk(self):
        """Fragile risk prevents A+; retest + hold confirmed → CLEAN_STARTER."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="fragile",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "CLEAN_STARTER"

    def test_clean_starter_invalid_risk(self):
        """Invalid risk prevents A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="invalid",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "CLEAN_STARTER"

    def test_clean_starter_unknown_risk(self):
        """Unknown risk prevents A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="unknown",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "CLEAN_STARTER"

    def test_clean_starter_overhead_blocked(self):
        """Blocked overhead prevents A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="blocked",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "CLEAN_STARTER"

    def test_clean_starter_overhead_blocker_active(self):
        """Moderate overhead with blocker note referencing 'overhead' prevents A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="moderate",
            sma_value_alignment="supportive",
            near_entry_blocker_note="Overhead resistance is blocking the path.",
        )
        assert _evaluate_setup_quality(sig, "STARTER") == "CLEAN_STARTER"

    def test_clean_starter_sma_hostile(self):
        """Hostile SMA alignment prevents A+."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="hostile",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "CLEAN_STARTER"

    def test_clean_starter_multiple_imperfections(self):
        """Multiple imperfections still → CLEAN_STARTER when both confirmed."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="fragile",
            overhead_status="blocked",
            sma_value_alignment="hostile",
        )
        assert _evaluate_setup_quality(sig, "STARTER") == "CLEAN_STARTER"

    # ---- WATCH_ONLY_VALID ----

    def test_watch_only_partial_retest(self):
        """Partial retest = partial progress → WATCH_ONLY_VALID."""
        sig = _base_signal(
            retest_status="partial",
            hold_status="missing",
            structure_event="MSS",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "WATCH_ONLY_VALID"

    def test_watch_only_partial_hold(self):
        """Partial hold = partial progress → WATCH_ONLY_VALID."""
        sig = _base_signal(
            retest_status="missing",
            hold_status="partial",
            structure_event="FVG",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "WATCH_ONLY_VALID"

    def test_watch_only_retest_confirmed_hold_missing(self):
        """Retest confirmed but hold missing: 'has_partial' is True → WATCH_ONLY_VALID."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="missing",
            structure_event="BOS",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "WATCH_ONLY_VALID"

    def test_watch_only_both_partial(self):
        """Both partial → WATCH_ONLY_VALID."""
        sig = _base_signal(
            retest_status="partial",
            hold_status="partial",
            structure_event="OB",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "WATCH_ONLY_VALID"

    def test_watch_only_with_fvg_structure(self):
        """FVG structure event qualifies as structure_present."""
        sig = _base_signal(
            retest_status="partial",
            hold_status="missing",
            structure_event="FVG",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "WATCH_ONLY_VALID"

    # ---- STRUCTURALLY_VALID_BUT_IMPERFECT ----

    def test_structurally_valid_both_missing_with_structure(self):
        """Both retest and hold missing, structure present → STRUCTURALLY_VALID_BUT_IMPERFECT."""
        sig = _base_signal(
            retest_status="missing",
            hold_status="missing",
            structure_event="BOS",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "STRUCTURALLY_VALID_BUT_IMPERFECT"

    def test_structurally_valid_failed_retest_with_structure(self):
        """Failed retest, no partial progress, structure present → STRUCTURALLY_VALID_BUT_IMPERFECT."""
        sig = _base_signal(
            retest_status="failed",
            hold_status="missing",
            structure_event="MSS",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "STRUCTURALLY_VALID_BUT_IMPERFECT"

    # ---- LOW_PRIORITY_VALID ----

    def test_low_priority_no_structure(self):
        """No structure event → LOW_PRIORITY_VALID."""
        sig = _base_signal(
            retest_status="missing",
            hold_status="missing",
            structure_event="none",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "LOW_PRIORITY_VALID"

    def test_low_priority_structure_event_none_string(self):
        """structure_event='none' (string) triggers LOW_PRIORITY_VALID."""
        sig = _base_signal(
            retest_status="failed",
            hold_status="failed",
            structure_event="none",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "LOW_PRIORITY_VALID"

    # ---- Tier does not alter label assignment ----

    def test_tier_does_not_override_a_plus(self):
        """final_tier=STARTER with all quality gates clean → A_PLUS."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "STARTER") == "A_PLUS_CANDIDATE"

    def test_near_entry_with_all_confirmed_is_a_plus(self):
        """If a NEAR_ENTRY signal somehow has all quality gates clean → A_PLUS."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "NEAR_ENTRY") == "A_PLUS_CANDIDATE"


# ===========================================================================
# format_alert() integration
# ===========================================================================


class TestFormatAlertQualityReadPresence:
    """Quality read line appears in the ACTION section for every alertable tier."""

    def test_quality_read_in_snipe_it(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert "Quality read:" in result

    def test_quality_read_in_starter(self):
        result = format_alert(_tiering_result("STARTER"))
        assert "Quality read:" in result

    def test_quality_read_in_near_entry(self):
        result = format_alert(_ne_tiering_result())
        assert "Quality read:" in result

    def test_quality_read_in_action_section(self):
        """Quality read line must appear after 'ACTION' header and before 'FRESHNESS'."""
        result = format_alert(_tiering_result("SNIPE_IT"))
        action_pos  = result.find("\nACTION\n")
        quality_pos = result.find("Quality read:")
        fresh_pos   = result.find("\nFRESHNESS\n")
        assert action_pos != -1, "ACTION section missing"
        assert quality_pos != -1, "Quality read missing"
        assert fresh_pos  != -1, "FRESHNESS section missing"
        assert action_pos < quality_pos < fresh_pos

    def test_quality_read_not_in_execution_block(self):
        """Quality read must not appear before the EXECUTION block separator ends."""
        result = format_alert(_tiering_result("SNIPE_IT"))
        execution_pos = result.find("\nEXECUTION\n")
        quality_pos   = result.find("Quality read:")
        assert execution_pos < quality_pos  # quality comes after EXECUTION

    def test_only_one_quality_read_line(self):
        """Exactly one 'Quality read:' line per alert."""
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert result.count("Quality read:") == 1


class TestFormatAlertQualityPhrases:
    """Correct quality phrase emitted for each label scenario."""

    def test_a_plus_phrase_for_clean_snipe_it(self):
        result = format_alert(_tiering_result(
            "SNIPE_IT",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        ))
        assert _QUALITY_LABEL_PHRASES["A_PLUS_CANDIDATE"] in result

    def test_clean_starter_phrase_for_fragile_risk(self):
        result = format_alert(_tiering_result(
            "STARTER",
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="fragile",
            overhead_status="clear",
            sma_value_alignment="supportive",
        ))
        assert _QUALITY_LABEL_PHRASES["CLEAN_STARTER"] in result

    def test_clean_starter_phrase_for_hostile_sma(self):
        result = format_alert(_tiering_result(
            "STARTER",
            retest_status="confirmed",
            hold_status="confirmed",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="hostile",
        ))
        assert _QUALITY_LABEL_PHRASES["CLEAN_STARTER"] in result

    def test_watch_only_phrase_for_near_entry(self):
        result = format_alert(_ne_tiering_result(
            retest_status="partial",
            hold_status="missing",
            structure_event="BOS",
        ))
        assert _QUALITY_LABEL_PHRASES["WATCH_ONLY_VALID"] in result

    def test_structurally_valid_phrase_for_both_missing(self):
        result = format_alert(_ne_tiering_result(
            retest_status="missing",
            hold_status="missing",
            structure_event="MSS",
            # Backfill partial progress would normally happen in tiering.py;
            # for this direct test we use has_partial=False explicitly.
        ))
        # STRUCTURALLY_VALID_BUT_IMPERFECT requires both missing AND structure present
        # with no partial progress.
        assert _QUALITY_LABEL_PHRASES["STRUCTURALLY_VALID_BUT_IMPERFECT"] in result


class TestFormatAlertQualityNoSideEffects:
    """Quality read must not alter tier, capital, or any other alert content."""

    def test_tier_unchanged_snipe_it(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert "🔴 SNIPE IT" in result

    def test_tier_unchanged_starter(self):
        result = format_alert(_tiering_result("STARTER"))
        assert "🟡 STARTER" in result

    def test_tier_unchanged_near_entry(self):
        result = format_alert(_ne_tiering_result())
        assert "🟢 NEAR ENTRY" in result

    def test_capital_label_unchanged_snipe_it(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert "SNIPE_IT conditions met." in result
        assert "FULL QUALITY" in result

    def test_capital_label_unchanged_starter(self):
        result = format_alert(_tiering_result("STARTER"))
        assert "STARTER conditions met." in result
        assert "STARTER SIZE ONLY" in result

    def test_no_capital_yet_unchanged_near_entry(self):
        result = format_alert(_ne_tiering_result())
        assert "NO CAPITAL YET" in result

    def test_next_action_preserved(self):
        result = format_alert(_tiering_result("SNIPE_IT", next_action="Enter at trigger."))
        assert "Next: Enter at trigger." in result

    def test_reason_preserved(self):
        result = format_alert(_tiering_result(
            "SNIPE_IT",
            reason="Clean BOS with retest and hold.",
        ))
        assert "Why:  Clean BOS with retest and hold." in result

    def test_quality_phrase_not_doubled(self):
        """Quality phrase must not be duplicated anywhere in the body."""
        result = format_alert(_tiering_result(
            "SNIPE_IT",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        ))
        phrase = _QUALITY_LABEL_PHRASES["A_PLUS_CANDIDATE"]
        assert result.count(phrase) == 1

    def test_quality_phrase_survives_contract_guard(self):
        """A+ phrase must not be stripped by the contract guard or sovereignty guard."""
        result = format_alert(_tiering_result(
            "SNIPE_IT",
            risk_realism_state="healthy",
            overhead_status="clear",
            sma_value_alignment="supportive",
        ))
        assert "A+ candidate" in result

    def test_watch_only_phrase_survives_ne_firewall(self):
        """Watch-only valid phrase must not be caught by the NEAR_ENTRY firewall."""
        result = format_alert(_ne_tiering_result(
            retest_status="partial",
            hold_status="missing",
            structure_event="BOS",
        ))
        assert "Watch-only valid" in result


class TestFormatAlertQualityRegressionGuards:
    """Ensure prior alert sections are unchanged by the Phase 13.8A addition."""

    def _render_snipe(self, **overrides) -> str:
        return format_alert(_tiering_result("SNIPE_IT", **overrides))

    def _render_starter(self, **overrides) -> str:
        return format_alert(_tiering_result("STARTER", **overrides))

    def _render_ne(self, **overrides) -> str:
        return format_alert(_ne_tiering_result(**overrides))

    def test_snipe_execution_block_present(self):
        result = self._render_snipe()
        assert "EXECUTION" in result
        assert "Trigger:" in result
        assert "Retest:" in result
        assert "Hold:" in result
        assert "Invalidation:" in result

    def test_snipe_targets_block_present(self):
        result = self._render_snipe()
        assert "TARGETS" in result

    def test_snipe_freshness_block_present(self):
        result = self._render_snipe()
        assert "FRESHNESS" in result
        assert "Scan Price:" in result

    def test_ne_no_capital_section_present(self):
        result = self._render_ne()
        assert "NO CAPITAL YET" in result
        assert "Blocker:" in result
        assert "Missing conditions:" in result
        assert "Upgrade trigger:" in result

    def test_meta_section_present(self):
        result = self._render_snipe()
        assert "META" in result

    def test_starter_execution_block_unchanged(self):
        result = self._render_starter()
        assert "EXECUTION" in result
        assert "STARTER conditions met." in result

    def test_quality_line_between_sizing_and_next(self):
        """Quality read line is sandwiched between sizing and Next in ACTION."""
        result = self._render_snipe()
        sizing_pos  = result.find("FULL QUALITY")
        quality_pos = result.find("Quality read:")
        next_pos    = result.find("  Next:")
        assert sizing_pos  != -1
        assert quality_pos != -1
        assert next_pos    != -1
        assert sizing_pos < quality_pos < next_pos

    def test_all_quality_labels_have_phrases(self):
        """Every internal label constant has a corresponding human phrase."""
        labels = [
            "A_PLUS_CANDIDATE",
            "CLEAN_STARTER",
            "WATCH_ONLY_VALID",
            "STRUCTURALLY_VALID_BUT_IMPERFECT",
            "LOW_PRIORITY_VALID",
        ]
        for label in labels:
            assert label in _QUALITY_LABEL_PHRASES, f"Missing phrase for {label}"
            phrase = _QUALITY_LABEL_PHRASES[label]
            assert isinstance(phrase, str) and len(phrase) > 10, (
                f"Phrase for {label} is too short: {phrase!r}"
            )

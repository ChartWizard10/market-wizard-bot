"""Phase 13.7I — Narrative sovereignty layer tests.

Covers:
  _apply_narrative_sovereignty_guard()  — direct unit tests for all rule groups
  format_alert() integration            — end-to-end with live-style fixtures
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _apply_narrative_sovereignty_guard,
    _FRAGILE_RISK_CAUTION,
    format_alert,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ne_signal(ticker: str = "TEST", **overrides) -> dict:
    base: dict = {
        "final_tier": "NEAR_ENTRY",
        "score": 62,
        "ticker": ticker,
        "final_signal": {
            "ticker": ticker,
            "tier": "NEAR_ENTRY",
            "score": 62,
            "setup_family": "reclaim",
            "structure_event": "MSS",
            "trend_state": "repair",
            "zone_type": "FVG",
            "trigger_level": 150.00,
            "retest_status": "partial",
            "hold_status": "missing",
            "invalidation_condition": "below FVG base",
            "invalidation_level": 147.50,
            "risk_reward": None,
            "overhead_status": "clear",
            "forced_participation": "none",
            "next_action": "Watch for retest confirmation.",
            "capital_action": "wait_no_capital",
            "reason": "Structure repair in progress; no zone acceptance yet.",
            "missing_conditions": ["retest_confirmed", "hold_confirmed"],
            "upgrade_trigger": "Confirmed retest and hold of FVG.",
            "targets": [{"label": "T1", "level": 158.00, "reason": "prior swing high"}],
            "discord_channel": "#near-entry-watch",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
            if k in base["final_signal"]:
                base["final_signal"][k] = v
        else:
            base["final_signal"][k] = v
    return base


def _snipe_signal(**overrides) -> dict:
    base: dict = {
        "final_tier": "SNIPE_IT",
        "score": 88,
        "ticker": "XYZ",
        "final_signal": {
            "ticker": "XYZ",
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
            "forced_participation": "none",
            "next_action": "Enter at trigger.",
            "capital_action": "full_quality_allowed",
            "reason": "Clean BOS with retest and hold.",
            "missing_conditions": [],
            "upgrade_trigger": "",
            "targets": [{"label": "T1", "level": 210.00, "reason": "prior high"}],
            "discord_channel": "#snipe-signals",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
            if k in base["final_signal"]:
                base["final_signal"][k] = v
        else:
            base["final_signal"][k] = v
    return base


def _starter_signal(**overrides) -> dict:
    base: dict = {
        "final_tier": "STARTER",
        "score": 78,
        "ticker": "ABC",
        "final_signal": {
            "ticker": "ABC",
            "tier": "STARTER",
            "score": 78,
            "setup_family": "reclaim",
            "structure_event": "MSS",
            "trend_state": "repair",
            "zone_type": "FVG",
            "trigger_level": 100.00,
            "retest_status": "confirmed",
            "hold_status": "confirmed",
            "invalidation_condition": "below FVG base",
            "invalidation_level": 97.00,
            "risk_reward": 3.1,
            "overhead_status": "clear",
            "forced_participation": "none",
            "next_action": "Enter reduced size at trigger.",
            "capital_action": "starter_only",
            "reason": "Zone accepted with retest confirmed.",
            "missing_conditions": [],
            "upgrade_trigger": "",
            "targets": [{"label": "T1", "level": 108.00, "reason": "swing high"}],
            "discord_channel": "#starter-signals",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
            if k in base["final_signal"]:
                base["final_signal"][k] = v
        else:
            base["final_signal"][k] = v
    return base


# ---------------------------------------------------------------------------
# Unit tests — _apply_narrative_sovereignty_guard() directly
# ---------------------------------------------------------------------------

class TestSovereigntyGuardUnit:
    """Direct unit tests: pass a pre-constructed body into the guard and assert output."""

    # --- Test 1: NEAR_ENTRY cannot imply entry ---
    def test_ne_enter_on_confirmation_removed(self):
        body = "NO CAPITAL — WATCH ONLY\nenter on confirmation once FVG holds."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "enter on" not in result.lower()
        assert "no capital" in result.lower() or "watch" in result.lower()

    def test_ne_enter_long_removed(self):
        body = "enter long at trigger level."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "enter long" not in result.lower()

    def test_ne_entry_valid_removed(self):
        body = "entry valid once zone confirmed."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "entry valid" not in result.lower()
        assert "watch" in result.lower()

    def test_ne_capital_authorized_removed(self):
        body = "capital authorized after retest confirms."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "capital authorized" not in result.lower()

    def test_ne_deploy_capital_removed(self):
        body = "deploy capital once zone holds."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "deploy capital" not in result.lower()

    # --- Test 2: NEAR_ENTRY cannot imply starter sizing ---
    def test_ne_starter_sizing_removed(self):
        body = "starter sizing only until upgrade confirms."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "starter sizing" not in result.lower()
        assert "watch" in result.lower() or "no capital" in result.lower()

    def test_ne_adding_size_removed(self):
        body = "adding size is not appropriate before zone holds."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "adding size" not in result.lower()

    def test_ne_starter_size_removed(self):
        body = "starter size acceptable once trigger is reached."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "starter size" not in result.lower()

    # --- Test 3: Retest partial — no defended-zone language ---
    def test_retest_partial_defended_zone_removed(self):
        body = "successful retest of demand zone; demand defended at key level."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "successful retest" not in result.lower()
        assert "demand defended" not in result.lower()
        assert "retest" in result.lower()  # replacement should mention retest

    def test_retest_partial_acceptance_confirmed_removed(self):
        body = "acceptance confirmed at zone base."
        signal = {"retest_status": "partial", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        # retest not confirmed → acceptance_confirmed caught
        assert "acceptance confirmed" not in result.lower()

    def test_retest_confirmed_defended_zone_preserved(self):
        """When retest IS confirmed, defended-zone language must not be removed."""
        body = "successful retest of demand zone; buyers defended."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert "successful retest" in result.lower()

    # --- Test 4: Hold partial — no accepted/continuation language ---
    def test_hold_partial_hold_confirmed_removed(self):
        body = "hold confirmed at zone; continuation confirmed."
        signal = {"retest_status": "partial", "hold_status": "partial",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "hold confirmed" not in result.lower()
        assert "continuation confirmed" not in result.lower()

    def test_hold_confirmed_language_preserved(self):
        """When hold IS confirmed, hold-confirmed language must survive."""
        body = "hold confirmed; continuation confirmed at zone."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert "hold confirmed" in result.lower()

    # --- Test 5: Overhead blocker active cannot say not blocked ---
    def test_overhead_blocker_active_not_blocking_removed(self):
        body = "Overhead: moderate — not blocking"
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "moderate", "risk_realism_state": "",
                  "near_entry_blocker_note": "Overhead resistance limiting path."}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "not blocking" not in result.lower()
        assert "blocker" in result.lower()

    def test_overhead_blocker_active_clear_path_removed(self):
        body = "clear path to target exists above."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "moderate", "risk_realism_state": "",
                  "near_entry_blocker_note": "Overhead resistance ceiling nearby."}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "clear path" not in result.lower()

    def test_overhead_blocked_not_blocking_removed(self):
        body = "overhead is not blocking at this level."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "blocked", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "not blocking" not in result.lower()

    # --- Test 6: SNIPE_IT with moderate overhead (no blocker) keeps not-blocking label ---
    def test_snipe_it_moderate_not_blocking_preserved(self):
        body = "Overhead: moderate — not blocking"
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "moderate", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        # No blocker → blocker rules don't fire → "not blocking" survives
        assert "not blocking" in result.lower()

    def test_ne_moderate_no_blocker_not_blocking_preserved(self):
        """NEAR_ENTRY with moderate overhead but NO overhead-specific blocker note."""
        body = "Overhead: moderate — not blocking"
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "moderate", "risk_realism_state": "",
                  "near_entry_blocker_note": "Retest not yet confirmed."}  # no overhead kw
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "not blocking" in result.lower()

    # --- Test 7: Fragile risk adds caution ---
    def test_fragile_risk_clean_asymmetry_replaced(self):
        body = "clean asymmetry with 4:1 R:R ratio."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "fragile",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "clean asymmetry" not in result.lower()
        assert "compressed" in result.lower()

    def test_fragile_risk_caution_injected(self):
        """When fragile and no prior caution markers, caution is injected."""
        body = "  Risk state:     fragile\nSome other text."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "fragile",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert any(
            m in result.lower()
            for m in ("compressed", "execution sensitiv", "risk is fragile")
        )

    def test_fragile_risk_caution_not_duplicated(self):
        """If caution markers already present, caution is not injected a second time."""
        body = (
            "  Risk state:     fragile\n"
            f"  Risk note:      {_FRAGILE_RISK_CAUTION}"
        )
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "fragile",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert result.count(_FRAGILE_RISK_CAUTION) == 1

    def test_healthy_risk_no_caution(self):
        body = "clean asymmetry at 4:1 setup."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "healthy",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert _FRAGILE_RISK_CAUTION not in result

    # --- Test 8: STARTER cannot say full quality ---
    def test_starter_full_quality_removed(self):
        body = "FULL QUALITY — capital authorized after live-chart verification."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("STARTER", signal, body)
        assert "full quality" not in result.lower()
        assert "starter" in result.lower() or "reduced" in result.lower()

    def test_starter_maximum_conviction_removed(self):
        body = "maximum conviction setup confirmed."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("STARTER", signal, body)
        assert "maximum conviction" not in result.lower()

    def test_starter_pristine_setup_removed(self):
        body = "pristine setup with all conditions aligned."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("STARTER", signal, body)
        assert "pristine setup" not in result.lower()

    # --- Test 9: SNIPE_IT cannot contain no-capital contradiction ---
    def test_snipe_it_no_capital_removed(self):
        body = "NO CAPITAL — WATCH ONLY"
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert "no capital" not in result.lower()
        assert "watch only" not in result.lower()

    def test_snipe_it_watch_only_removed(self):
        body = "watch-only; no capital until upgrade."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert "watch" not in result.lower() or "monitoring" in result.lower()

    def test_snipe_it_blocker_active_removed(self):
        body = "blocker active; confirm path before capital."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        assert "blocker active" not in result.lower()

    # --- Test 10: Bare snake_case keys still removed ---
    def test_residual_snake_case_removed(self):
        body = "retest_confirmed and hold_confirmed still pending."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "retest_confirmed" not in result
        assert "hold_confirmed" not in result

    def test_residual_diagnostic_label_removed(self):
        body = "retest_status is partial confirmation pending."
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        result = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        assert "retest_status" not in result

    # --- Test 11: Idempotence ---
    def test_idempotent_near_entry(self):
        body = (
            "enter on confirmation; successful retest; clean asymmetry; "
            "adding size not yet allowed; retest_status is partial."
        )
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "moderate", "risk_realism_state": "fragile",
                  "near_entry_blocker_note": "Overhead resistance blocking."}
        once = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, body)
        twice = _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, once)
        assert once == twice

    def test_idempotent_snipe_it(self):
        body = "Clean BOS with retest and hold; successful retest of demand."
        signal = {"retest_status": "confirmed", "hold_status": "confirmed",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        once = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, body)
        twice = _apply_narrative_sovereignty_guard("SNIPE_IT", signal, once)
        assert once == twice

    def test_empty_body_unchanged(self):
        signal = {"retest_status": "partial", "hold_status": "missing",
                  "overhead_status": "clear", "risk_realism_state": "",
                  "near_entry_blocker_note": ""}
        assert _apply_narrative_sovereignty_guard("NEAR_ENTRY", signal, "") == ""


# ---------------------------------------------------------------------------
# Test 12: Live-style regression — full multi-condition scenario
# ---------------------------------------------------------------------------

class TestLiveStyleRegression:
    """Full multi-condition scenario with format_alert() end-to-end."""

    def test_full_near_entry_regression(self):
        """NEAR_ENTRY with partial retest/hold, moderate overhead (blocker), fragile risk.

        Output must:
        - Not contain entry/sizing language
        - Not contain 'not blocked' / 'not blocking'
        - Not contain 'successful retest'
        - Contain NO CAPITAL YET
        - Not contain 'clean asymmetry'
        """
        signal = _ne_signal(
            ticker="REGR",
            retest_status="partial",
            hold_status="partial",
            overhead_status="moderate",
            risk_realism_state="fragile",
            near_entry_blocker_note="Overhead resistance ceiling limiting upside path.",
            reason=(
                "enter on confirmation before adding size; "
                "overhead is moderate but not blocked; "
                "successful retest of demand zone; "
                "clean asymmetry at 4:1."
            ),
            next_action="Trade management: trail stop below zone once entry confirmed.",
        )
        text = format_alert(signal)

        assert "enter on" not in text.lower()
        assert "adding size" not in text.lower()
        assert "not blocking" not in text.lower()
        assert "not blocked" not in text.lower()
        assert "successful retest" not in text.lower()
        assert "clean asymmetry" not in text.lower()
        assert "trail stop" not in text.lower()
        assert "NO CAPITAL YET" in text

    def test_full_near_entry_fragile_risk_caution_present(self):
        """Fragile risk state must appear in output."""
        signal = _ne_signal(
            ticker="FRAGR",
            retest_status="partial",
            hold_status="partial",
            overhead_status="moderate",
            risk_realism_state="fragile",
            near_entry_blocker_note="Overhead supply limiting path.",
            reason="clean asymmetry with strong R:R.",
        )
        text = format_alert(signal)
        assert "fragile" in text.lower() or "compressed" in text.lower() or "execution sensitiv" in text.lower()

    def test_retest_sovereignty_in_ne(self):
        """Defended-zone language must not survive in NEAR_ENTRY with partial retest."""
        signal = _ne_signal(
            retest_status="partial",
            reason="demand defended at FVG base; structure fully confirmed.",
        )
        text = format_alert(signal)
        assert "demand defended" not in text.lower()
        assert "structure fully confirmed" not in text.lower()

    def test_hold_sovereignty_in_ne(self):
        """Hold-confirmed language must not survive in NEAR_ENTRY with missing hold."""
        signal = _ne_signal(
            hold_status="missing",
            reason="hold confirmed at zone; continuation confirmed below swing.",
        )
        text = format_alert(signal)
        assert "hold confirmed" not in text.lower()
        assert "continuation confirmed" not in text.lower()


# ---------------------------------------------------------------------------
# format_alert() integration — tier-level regression guards
# ---------------------------------------------------------------------------


class TestFormatAlertSovereigntyIntegration:
    """Verify sovereignty through the full format_alert() pipeline."""

    def test_ne_no_entry_in_output(self):
        text = format_alert(_ne_signal(next_action="enter on confirmation at trigger."))
        assert "enter on" not in text.lower()
        assert "NO CAPITAL YET" in text

    def test_ne_no_capital_header_always_present(self):
        text = format_alert(_ne_signal(
            reason="Zone is forming; starter size once confirmed.",
            next_action="Position management after zone holds.",
        ))
        assert "NO CAPITAL YET" in text
        assert "starter size" not in text.lower()
        assert "position management" not in text.lower()

    def test_starter_full_quality_not_in_output(self):
        text = format_alert(_starter_signal(reason="FULL QUALITY setup confirmed; all SNIPE_IT conditions met."))
        assert "full quality" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_snipe_it_no_capital_not_in_output(self):
        text = format_alert(_snipe_signal(reason="NO CAPITAL — WATCH ONLY until retest."))
        assert "no capital" not in text.lower()
        assert "watch only" not in text.lower()

    def test_snipe_it_clean_content_preserved(self):
        """SNIPE_IT with clean reason must not be mangled."""
        text = format_alert(_snipe_signal())
        assert "Enter at trigger." in text
        assert "Clean BOS with retest and hold." in text

    def test_ne_clean_content_preserved(self):
        """NEAR_ENTRY with clean watch-only reason must not be mangled."""
        text = format_alert(_ne_signal(
            reason="Structure repair in progress; no zone acceptance yet.",
            next_action="Watch for retest confirmation.",
        ))
        assert "Structure repair in progress" in text
        assert "Watch for retest confirmation." in text

    def test_starter_legitimate_language_preserved(self):
        text = format_alert(_starter_signal())
        assert "Enter reduced size at trigger." in text
        assert "Zone accepted with retest confirmed." in text

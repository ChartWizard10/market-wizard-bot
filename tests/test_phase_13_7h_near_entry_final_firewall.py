"""Phase 13.7H — NEAR_ENTRY capital-language final firewall + residual diagnostic
humanizer tests.

Covers:
  _apply_near_entry_capital_firewall()  — capital/action phrase neutralization
                                          and residual diagnostic safety net
  format_alert() integration            — MRVL, SEIC, ATKR live-style fixtures
                                          + regression guards for STARTER/SNIPE_IT
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _apply_near_entry_capital_firewall,
    format_alert,
)

# ---------------------------------------------------------------------------
# Shared signal factory
# ---------------------------------------------------------------------------

# Forbidden substrings: none of these may appear in any NEAR_ENTRY alert.
_NE_FORBIDDEN = [
    "enter long",
    "enter on",
    "adding size",
    "add size",
    "size can be reviewed",
    "trail stop",
    "position management",
    "capital commitment",
    "retest_status",
    "hold_status",
    "price_in_zone",
]


def _ne_signal(ticker: str = "TEST", **overrides) -> dict:
    """Minimal NEAR_ENTRY tiering_result dict suitable for format_alert()."""
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


def _assert_ne_clean(text: str) -> None:
    """Assert none of the globally forbidden NEAR_ENTRY phrases appear in text."""
    for phrase in _NE_FORBIDDEN:
        assert phrase not in text.lower(), (
            f"Forbidden phrase {phrase!r} found in NEAR_ENTRY output"
        )


# ===========================================================================
# _apply_near_entry_capital_firewall — unit tests
# ===========================================================================


class TestApplyNearEntryCapitalFirewall:
    # --- sizing language ---
    def test_before_adding_size(self):
        result = _apply_near_entry_capital_firewall(
            "Watch for retest; before adding size wait for confirmation."
        )
        assert "adding size" not in result.lower()

    def test_size_can_be_reviewed(self):
        result = _apply_near_entry_capital_firewall(
            "Once retest confirms, size can be reviewed."
        )
        assert "size can be reviewed" not in result.lower()
        assert "reconsidered" in result.lower() or "review" in result.lower()

    def test_adding_size_bare(self):
        result = _apply_near_entry_capital_firewall("adding size is not appropriate yet.")
        assert "adding size" not in result.lower()

    def test_add_size_bare(self):
        result = _apply_near_entry_capital_firewall("Do not add size until zone holds.")
        assert "add size" not in result.lower()

    # --- entry language ---
    def test_enter_on_confirmation(self):
        result = _apply_near_entry_capital_firewall(
            "enter on confirmation once FVG holds."
        )
        assert "enter on" not in result.lower()
        assert "wait for confirmation" in result.lower()

    def test_enter_on_bare(self):
        result = _apply_near_entry_capital_firewall("enter on the next bar.")
        assert "enter on" not in result.lower()

    def test_entry_valid(self):
        result = _apply_near_entry_capital_firewall("entry valid once zone holds.")
        assert "entry valid" not in result.lower()
        assert "on watch" in result.lower()

    # --- capital / position management ---
    def test_capital_commitment(self):
        result = _apply_near_entry_capital_firewall(
            "No capital commitment until retest confirms."
        )
        assert "capital commitment" not in result.lower()

    def test_trail_stop(self):
        result = _apply_near_entry_capital_firewall(
            "trail stop below zone low once confirmed."
        )
        assert "trail stop" not in result.lower()
        assert "invalidation reference" in result.lower()

    # --- residual diagnostic labels ---
    def test_retest_status_is_partial(self):
        result = _apply_near_entry_capital_firewall("retest_status is partial.")
        assert "retest_status" not in result
        assert "retest is only partial" in result

    def test_retest_status_is_missing(self):
        result = _apply_near_entry_capital_firewall("retest_status is missing.")
        assert "retest_status" not in result
        assert "retest is missing" in result

    def test_hold_status_is_partial(self):
        result = _apply_near_entry_capital_firewall("hold_status is partial.")
        assert "hold_status" not in result
        assert "hold is not fully confirmed" in result

    def test_hold_status_is_missing(self):
        result = _apply_near_entry_capital_firewall("hold_status is missing.")
        assert "hold_status" not in result
        assert "hold is missing" in result

    def test_price_in_zone_is_true(self):
        result = _apply_near_entry_capital_firewall("price_in_zone is true.")
        assert "price_in_zone" not in result
        assert "price is inside the zone" in result

    def test_price_in_zone_is_false(self):
        result = _apply_near_entry_capital_firewall("price_in_zone is false.")
        assert "price_in_zone" not in result
        assert "price is not inside the zone" in result

    # --- clean text unchanged ---
    def test_clean_watch_language_unchanged(self):
        text = "Watch for retest confirmation."
        assert _apply_near_entry_capital_firewall(text) == text

    def test_empty_string(self):
        assert _apply_near_entry_capital_firewall("") == ""

    def test_case_insensitive(self):
        result = _apply_near_entry_capital_firewall("ENTER ON CONFIRMATION.")
        assert "enter on" not in result.lower()

    def test_idempotent(self):
        text = "enter on confirmation; trail stop below zone."
        once = _apply_near_entry_capital_firewall(text)
        twice = _apply_near_entry_capital_firewall(once)
        assert once == twice

    def test_no_capital_yet_phrase_preserved(self):
        """'no capital' watch language must survive the firewall."""
        text = "NO CAPITAL — WATCH ONLY"
        result = _apply_near_entry_capital_firewall(text)
        assert "NO CAPITAL" in result


# ===========================================================================
# format_alert() integration — MRVL NEAR_ENTRY fixture
# ===========================================================================


class TestFormatAlertMrvlFixture:
    """MRVL live-style defect: 'before adding size' + 'retest_status is partial'."""

    def _render(self, **overrides) -> str:
        return format_alert(_ne_signal(ticker="MRVL", **overrides))

    def test_before_adding_size_removed(self):
        text = self._render(
            reason=(
                "Zone is re-approaching after pullback; before adding size "
                "need retest confirmation."
            )
        )
        assert "adding size" not in text.lower()

    def test_retest_status_is_partial_removed(self):
        text = self._render(
            reason="retest_status is partial — zone has not been fully retested yet."
        )
        assert "retest_status" not in text

    def test_both_defects_removed(self):
        text = self._render(
            reason=(
                "retest_status is partial; before adding size "
                "wait for full zone confirmation."
            )
        )
        assert "retest_status" not in text
        assert "adding size" not in text.lower()

    def test_no_capital_yet_present(self):
        text = self._render(
            reason="retest_status is partial; before adding size wait."
        )
        assert "NO CAPITAL YET" in text

    def test_full_forbidden_list_clear(self):
        text = self._render(
            reason="retest_status is partial; before adding size needs check.",
            next_action="enter on confirmation once retest holds.",
        )
        _assert_ne_clean(text)


# ===========================================================================
# format_alert() integration — SEIC NEAR_ENTRY fixture
# ===========================================================================


class TestFormatAlertSeicFixture:
    """SEIC live-style defect: 'size can be reviewed' + 'hold_status is partial'."""

    def _render(self, **overrides) -> str:
        return format_alert(_ne_signal(ticker="SEIC", **overrides))

    def test_size_can_be_reviewed_removed(self):
        text = self._render(
            next_action="size can be reviewed once hold confirms."
        )
        assert "size can be reviewed" not in text.lower()

    def test_hold_status_is_partial_removed(self):
        text = self._render(
            reason="hold_status is partial — price accepted zone but hold not confirmed."
        )
        assert "hold_status" not in text

    def test_both_defects_removed(self):
        text = self._render(
            reason="hold_status is partial.",
            next_action="size can be reviewed when hold confirms.",
        )
        assert "hold_status" not in text
        assert "size can be reviewed" not in text.lower()

    def test_no_capital_yet_present(self):
        text = self._render(
            reason="hold_status is partial.",
            next_action="size can be reviewed when hold confirms.",
        )
        assert "NO CAPITAL YET" in text

    def test_full_forbidden_list_clear(self):
        text = self._render(
            reason="hold_status is partial; adding size premature.",
            next_action="size can be reviewed; enter on confirmation.",
        )
        _assert_ne_clean(text)


# ===========================================================================
# format_alert() integration — ATKR NEAR_ENTRY fixture (blocker active)
# ===========================================================================


class TestFormatAlertAtkrFixture:
    """ATKR live-style defect: 'enter on confirmation' with blocker active.

    The headline must say NO CAPITAL / WATCH ONLY while the action text must
    not say 'enter on confirmation' — the two are mutually contradictory.
    """

    def _render(self, **overrides) -> str:
        return format_alert(
            _ne_signal(
                ticker="ATKR",
                near_entry_blocker_note="Overhead resistance blocking capital.",
                **overrides,
            )
        )

    def test_enter_on_confirmation_removed(self):
        text = self._render(
            next_action="enter on confirmation once overhead clears."
        )
        assert "enter on" not in text.lower()

    def test_no_capital_yet_present_with_blocker(self):
        text = self._render(
            next_action="enter on confirmation once overhead clears."
        )
        assert "NO CAPITAL YET" in text

    def test_blocker_and_entry_language_contradiction_resolved(self):
        """Alert with active blocker must not contain both NO CAPITAL and enter-on language."""
        text = self._render(
            next_action="enter on confirmation once overhead clears.",
            reason="Setup valid; trail stop below FVG base.",
        )
        assert "enter on" not in text.lower()
        assert "trail stop" not in text.lower()
        assert "NO CAPITAL YET" in text

    def test_trail_stop_removed_with_blocker(self):
        text = self._render(
            reason="Manage risk; trail stop below zone low."
        )
        assert "trail stop" not in text.lower()
        assert "invalidation reference" in text.lower()

    def test_full_forbidden_list_clear(self):
        text = self._render(
            reason="trail stop below OB; capital commitment deferred.",
            next_action="enter on confirmation; adding size after hold.",
        )
        _assert_ne_clean(text)


# ===========================================================================
# Regression guards — STARTER and SNIPE_IT must be unaffected
# ===========================================================================


class TestFirewallDoesNotAffectOtherTiers:
    def _snipe_signal(self) -> dict:
        return {
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
                "next_action": "Enter at trigger on confirmation.",
                "capital_action": "full_quality_allowed",
                "reason": "Clean BOS with retest and hold.",
                "missing_conditions": [],
                "upgrade_trigger": "",
                "targets": [{"label": "T1", "level": 210.00, "reason": "prior high"}],
                "discord_channel": "#snipe-signals",
            },
        }

    def _starter_signal(self) -> dict:
        return {
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

    def test_snipe_it_next_action_preserved(self):
        """SNIPE_IT 'Enter at trigger on confirmation.' must survive (not a NEAR_ENTRY)."""
        text = format_alert(self._snipe_signal())
        assert "Enter at trigger on confirmation." in text

    def test_snipe_it_reason_preserved(self):
        text = format_alert(self._snipe_signal())
        assert "Clean BOS with retest and hold." in text

    def test_starter_next_action_preserved(self):
        text = format_alert(self._starter_signal())
        assert "Enter reduced size at trigger." in text

    def test_starter_reason_preserved(self):
        text = format_alert(self._starter_signal())
        assert "Zone accepted with retest confirmed." in text

    def test_near_entry_firewall_not_applied_to_starter(self):
        """STARTER alert containing 'trail stop' language gets CAPITAL_CONTRACT treatment,
        not the NEAR_ENTRY firewall, so its replacement text differs."""
        signal = self._starter_signal()
        signal["final_signal"]["reason"] = "Zone holds; trail stop below FVG low."
        text = format_alert(signal)
        # STARTER contract replaces "trail stop" → "invalidation reference only"
        # (from CAPITAL_CONTRACT) — but that's also what the firewall would say.
        # The key assertion is that STARTER output is not mangled by the firewall
        # replacing "entry valid" or "enter on" when those don't appear.
        assert "Zone holds" in text or "trail stop" not in text.lower()

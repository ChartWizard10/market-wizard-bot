"""Phase 13.7G — Bare gate-key humanizer + NEAR_ENTRY classification-language seal tests.

Covers:
  _humanize_bare_gate_keys()                  — snake_case gate-key replacement
  _parse_missing_conditions()                 — string/list normalization to token list
  _format_missing_conditions()                — sentence-case, semicolon-joined, trailing period
  _seal_near_entry_classification_language()  — tier-mechanics phrase neutralization
  format_alert() integration                  — LSTR NEAR_ENTRY fixture + regression guards
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _format_missing_conditions,
    _humanize_bare_gate_keys,
    _parse_missing_conditions,
    _seal_near_entry_classification_language,
    format_alert,
)

# ---------------------------------------------------------------------------
# Shared signal factory
# ---------------------------------------------------------------------------


def _ne_signal(**overrides) -> dict:
    """Minimal NEAR_ENTRY tiering_result dict suitable for format_alert()."""
    base: dict = {
        "final_tier": "NEAR_ENTRY",
        "score": 62,
        "ticker": "LSTR",
        "final_signal": {
            "ticker": "LSTR",
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


# ===========================================================================
# _humanize_bare_gate_keys — unit tests
# ===========================================================================


class TestHumanizeBareGateKeys:
    def test_retest_confirmed(self):
        assert _humanize_bare_gate_keys("retest_confirmed") == "Retest not confirmed"

    def test_hold_confirmed(self):
        assert _humanize_bare_gate_keys("hold_confirmed") == "Hold not confirmed"

    def test_price_in_zone(self):
        assert _humanize_bare_gate_keys("price_in_zone") == "Price has not returned to the zone"

    def test_trigger_confirmed(self):
        assert _humanize_bare_gate_keys("trigger_confirmed") == "Trigger acceptance not confirmed"

    def test_overhead_clear(self):
        assert _humanize_bare_gate_keys("overhead_clear") == "Overhead path not clean"

    def test_missing_retest(self):
        assert _humanize_bare_gate_keys("missing_retest") == "Retest not confirmed"

    def test_missing_hold(self):
        assert _humanize_bare_gate_keys("missing_hold") == "Hold not confirmed"

    def test_comma_separated_list(self):
        """Comma-separated gate keys in prose text are each replaced."""
        result = _humanize_bare_gate_keys("retest_confirmed, hold_confirmed")
        assert "retest_confirmed" not in result
        assert "hold_confirmed" not in result
        assert "Retest not confirmed" in result
        assert "Hold not confirmed" in result

    def test_inline_sentence(self):
        """Gate key embedded in a sentence is replaced without disturbing surrounding text."""
        text = "The blocker is retest_confirmed and volume."
        result = _humanize_bare_gate_keys(text)
        assert "retest_confirmed" not in result
        assert "Retest not confirmed" in result
        assert "volume" in result

    def test_no_match_unchanged(self):
        text = "Watch for retest confirmation."
        assert _humanize_bare_gate_keys(text) == text

    def test_empty_string(self):
        assert _humanize_bare_gate_keys("") == ""

    def test_case_insensitive(self):
        result = _humanize_bare_gate_keys("RETEST_CONFIRMED")
        assert "RETEST_CONFIRMED" not in result.upper() or "Retest not confirmed" in result

    def test_idempotent(self):
        text = "retest_confirmed, hold_confirmed"
        once = _humanize_bare_gate_keys(text)
        twice = _humanize_bare_gate_keys(once)
        assert once == twice

    def test_longest_key_wins_over_partial(self):
        """missing_retest must match before any shorter partial key would."""
        result = _humanize_bare_gate_keys("missing_retest")
        assert "missing_retest" not in result
        assert "Retest not confirmed" in result

    def test_asymmetry_valid(self):
        result = _humanize_bare_gate_keys("asymmetry_valid")
        assert "asymmetry_valid" not in result
        assert "R:R" in result or "asymmetry" in result.lower()

    def test_invalidation_clarity(self):
        result = _humanize_bare_gate_keys("invalidation_clarity")
        assert "invalidation_clarity" not in result
        assert "Invalidation" in result


# ===========================================================================
# _parse_missing_conditions — unit tests
# ===========================================================================


class TestParseMissingConditions:
    def test_list_of_strings(self):
        result = _parse_missing_conditions(["retest_confirmed", "hold_confirmed"])
        assert result == ["retest_confirmed", "hold_confirmed"]

    def test_comma_separated_string(self):
        result = _parse_missing_conditions("retest_confirmed, hold_confirmed")
        assert result == ["retest_confirmed", "hold_confirmed"]

    def test_semicolon_separated_string(self):
        result = _parse_missing_conditions("retest_confirmed; hold_confirmed")
        assert result == ["retest_confirmed", "hold_confirmed"]

    def test_single_string(self):
        result = _parse_missing_conditions("retest_confirmed")
        assert result == ["retest_confirmed"]

    def test_list_with_comma_item(self):
        """List item that itself is comma-separated is split further."""
        result = _parse_missing_conditions(["retest_confirmed, hold_confirmed"])
        assert result == ["retest_confirmed", "hold_confirmed"]

    def test_empty_list(self):
        assert _parse_missing_conditions([]) == []

    def test_none(self):
        assert _parse_missing_conditions(None) == []

    def test_empty_string(self):
        assert _parse_missing_conditions("") == []

    def test_strips_whitespace(self):
        result = _parse_missing_conditions("  retest_confirmed ,  hold_confirmed  ")
        assert result == ["retest_confirmed", "hold_confirmed"]


# ===========================================================================
# _format_missing_conditions — unit tests
# ===========================================================================


class TestFormatMissingConditions:
    def test_two_items(self):
        result = _format_missing_conditions(["Retest not confirmed", "Hold not confirmed"])
        assert result == "Retest not confirmed; hold not confirmed."

    def test_single_item(self):
        result = _format_missing_conditions(["Retest not confirmed"])
        assert result == "Retest not confirmed."

    def test_first_item_kept_as_is(self):
        """First item is not lowercased."""
        result = _format_missing_conditions(["Retest not confirmed", "Hold not confirmed"])
        assert result.startswith("Retest")

    def test_subsequent_items_lowercased(self):
        result = _format_missing_conditions(["Retest not confirmed", "Hold not confirmed"])
        assert "; hold not confirmed." in result

    def test_trailing_period_added(self):
        result = _format_missing_conditions(["Retest not confirmed"])
        assert result.endswith(".")

    def test_no_double_period(self):
        result = _format_missing_conditions(["Retest not confirmed."])
        assert not result.endswith("..")

    def test_empty_list_returns_dash(self):
        assert _format_missing_conditions([]) == "—"

    def test_three_items(self):
        result = _format_missing_conditions([
            "Retest not confirmed",
            "Hold not confirmed",
            "Overhead path not clean",
        ])
        assert result.count(";") == 2
        assert result.endswith(".")


# ===========================================================================
# _seal_near_entry_classification_language — unit tests
# ===========================================================================


class TestSealNearEntryClassificationLanguage:
    def test_preventing_starter_classification(self):
        text = "preventing STARTER classification"
        result = _seal_near_entry_classification_language(text)
        assert "STARTER" not in result
        assert "preventing capital authorization" in result

    def test_preventing_snipe_it_classification(self):
        text = "preventing SNIPE_IT classification"
        result = _seal_near_entry_classification_language(text)
        assert "SNIPE_IT" not in result
        assert "preventing capital authorization" in result

    def test_preventing_starter_or_snipe_it_classification(self):
        text = "preventing STARTER or SNIPE_IT classification"
        result = _seal_near_entry_classification_language(text)
        assert "STARTER" not in result
        assert "SNIPE_IT" not in result
        assert "preventing capital authorization" in result

    def test_starter_classification_no_preventing(self):
        """Without 'preventing' prefix, replacement is 'capital authorization'."""
        text = "STARTER classification is required"
        result = _seal_near_entry_classification_language(text)
        assert "STARTER" not in result
        assert "capital authorization" in result
        assert "preventing" not in result

    def test_tier_upgrade(self):
        text = "tier upgrade conditions met"
        result = _seal_near_entry_classification_language(text)
        assert "tier upgrade" not in result.lower()
        assert "capital authorization" in result

    def test_classification_upgrade(self):
        text = "classification upgrade pending"
        result = _seal_near_entry_classification_language(text)
        assert "classification upgrade" not in result.lower()
        assert "capital authorization" in result

    def test_no_match_unchanged(self):
        text = "Watch for retest confirmation."
        assert _seal_near_entry_classification_language(text) == text

    def test_empty_string(self):
        assert _seal_near_entry_classification_language("") == ""

    def test_case_insensitive(self):
        text = "preventing starter classification"
        result = _seal_near_entry_classification_language(text)
        assert "starter" not in result.lower()
        assert "preventing capital authorization" in result

    def test_idempotent(self):
        text = "preventing SNIPE_IT classification"
        once = _seal_near_entry_classification_language(text)
        twice = _seal_near_entry_classification_language(once)
        assert once == twice

    def test_does_not_introduce_tier_names(self):
        """Replacement must not contain SNIPE_IT or STARTER."""
        text = "preventing STARTER or SNIPE_IT classification"
        result = _seal_near_entry_classification_language(text)
        assert "STARTER" not in result
        assert "SNIPE_IT" not in result


# ===========================================================================
# format_alert() integration — LSTR NEAR_ENTRY fixture
# ===========================================================================


class TestFormatAlertLstrFixture:
    """LSTR NEAR_ENTRY fixture — validates the two live defects from Phase 13.7G spec."""

    def _render(self, **overrides) -> str:
        return format_alert(_ne_signal(**overrides))

    def test_bare_gate_keys_not_in_missing_conditions(self):
        """Raw snake_case gate keys must not appear in the rendered Missing conditions line."""
        text = self._render(missing_conditions=["retest_confirmed", "hold_confirmed"])
        assert "retest_confirmed" not in text
        assert "hold_confirmed" not in text

    def test_missing_conditions_humanized(self):
        """Gate keys rendered as human text in Missing conditions line."""
        text = self._render(missing_conditions=["retest_confirmed", "hold_confirmed"])
        assert "Retest not confirmed" in text
        assert "hold not confirmed" in text

    def test_missing_conditions_format(self):
        """Missing conditions: semicolon-separated, first capitalized, trailing period."""
        text = self._render(missing_conditions=["retest_confirmed", "hold_confirmed"])
        assert "Missing conditions: Retest not confirmed; hold not confirmed." in text

    def test_classification_language_not_in_reason(self):
        """'preventing STARTER or SNIPE_IT classification' in reason must be neutralized."""
        text = self._render(
            reason="preventing STARTER or SNIPE_IT classification from being assigned."
        )
        assert "STARTER" not in text
        assert "SNIPE_IT" not in text
        assert "preventing capital authorization" in text

    def test_classification_language_not_in_next_action(self):
        """'preventing STARTER or SNIPE_IT classification' in next_action must be neutralized."""
        text = self._render(
            next_action="These gaps are preventing STARTER or SNIPE_IT classification."
        )
        assert "STARTER" not in text or "SNIPE_IT" not in text
        assert "preventing capital authorization" in text

    def test_no_capital_yet_always_present(self):
        """NEAR_ENTRY must always display 'NO CAPITAL YET'."""
        text = self._render(
            missing_conditions=["retest_confirmed", "hold_confirmed"],
            reason="preventing SNIPE_IT classification.",
        )
        assert "NO CAPITAL YET" in text

    def test_gate_key_in_blocker_note_humanized(self):
        """Gate keys in blocker note are replaced with human text."""
        text = self._render(near_entry_blocker_note="retest_confirmed is blocking entry.")
        assert "retest_confirmed" not in text
        assert "Retest not confirmed" in text

    def test_gate_key_in_upgrade_trigger_humanized(self):
        """Gate keys in upgrade_trigger are replaced with human text."""
        text = self._render(upgrade_trigger="Resolve retest_confirmed and hold_confirmed.")
        assert "retest_confirmed" not in text
        assert "hold_confirmed" not in text

    def test_missing_conditions_comma_string_parsed(self):
        """missing_conditions as a comma-separated string is parsed and humanized."""
        text = self._render(missing_conditions="retest_confirmed, hold_confirmed")
        assert "retest_confirmed" not in text
        assert "Retest not confirmed" in text

    def test_snipe_it_alert_not_affected(self):
        """SNIPE_IT alert must NOT have classification language stripped."""
        signal = {
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
        text = format_alert(signal)
        assert "Enter at trigger." in text
        assert "Clean BOS with retest and hold." in text

    def test_starter_alert_not_affected(self):
        """STARTER alert — gate-key humanization applies but classification seal does not."""
        signal = {
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
        text = format_alert(signal)
        assert "Enter reduced size at trigger." in text
        assert "Zone accepted with retest confirmed." in text

    def test_no_raw_gate_keys_in_full_output(self):
        """No known bare gate key should appear in the full alert output."""
        text = self._render(
            missing_conditions=["retest_confirmed", "hold_confirmed"],
            reason="Blockers are retest_confirmed and hold_confirmed.",
            next_action="Resolve retest_confirmed to upgrade.",
        )
        for key in ("retest_confirmed", "hold_confirmed", "price_in_zone", "missing_retest"):
            assert key not in text, f"Expected gate key {key!r} to be absent from output"

    def test_format_missing_conditions_semicolon_separator(self):
        """Multiple missing conditions are semicolon-separated in output."""
        text = self._render(missing_conditions=["retest_confirmed", "hold_confirmed"])
        assert "Missing conditions: Retest not confirmed; hold not confirmed." in text

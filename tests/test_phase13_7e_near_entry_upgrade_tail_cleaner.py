"""Phase 13.7E — NEAR_ENTRY upgrade-language seal + dangling tail cleaner tests.

Covers:
  _neutralize_near_entry_upgrade_language()  — field-level upgrade sentence removal
  _clean_near_entry_dangling_tails()          — "no capital" artifact tail removal
  _finalize_near_entry_body_text()            — safety-net full-text pass
  format_alert() integration                 — end-to-end NEAR_ENTRY alert output
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _clean_near_entry_dangling_tails,
    _finalize_near_entry_body_text,
    _neutralize_near_entry_upgrade_language,
    format_alert,
)

# ---------------------------------------------------------------------------
# Shared signal factory
# ---------------------------------------------------------------------------

_REPLACEMENT = "If confirmed, conviction improves for the next alert cycle."


def _ne_signal(**overrides) -> dict:
    """Minimal NEAR_ENTRY tiering_result dict suitable for format_alert()."""
    base: dict = {
        "final_tier": "NEAR_ENTRY",
        "score": 62,
        "ticker": "TEST",
        "final_signal": {
            "ticker": "TEST",
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
            "missing_conditions": ["missing_retest", "missing_hold"],
            "upgrade_trigger": "Confirmed retest and hold of FVG.",
            "targets": [{"label": "T1", "level": 158.00, "reason": "prior swing high"}],
            "discord_channel": "#near-entry-watch",
        },
    }
    # Apply field-level overrides inside final_signal
    for k, v in overrides.items():
        if k in base:
            base[k] = v
        else:
            base["final_signal"][k] = v
    return base


# ===========================================================================
# _neutralize_near_entry_upgrade_language — unit tests
# ===========================================================================


class TestNeutralizeNearEntryUpgradeLanguage:
    def test_upgrade_to_snipe_it(self):
        text = "That would allow upgrade to SNIPE_IT consideration."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "SNIPE_IT" not in result
        assert result == _REPLACEMENT

    def test_upgrade_to_starter(self):
        text = "If confirmed, evaluate upgrade to STARTER."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "STARTER" not in result
        assert _REPLACEMENT in result

    def test_upgrading_to_starter_or_snipe_it(self):
        text = "upgrading to STARTER or SNIPE_IT depending on volume and bar quality"
        result = _neutralize_near_entry_upgrade_language(text)
        assert "SNIPE_IT" not in result
        assert "STARTER" not in result
        assert _REPLACEMENT in result

    def test_upgrade_consideration_phrase(self):
        text = "SNIPE_IT consideration once zone holds."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "SNIPE_IT" not in result

    def test_case_insensitive_snipe_it(self):
        text = "upgrade to snipe_it consideration pending."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "snipe_it" not in result.lower()
        assert _REPLACEMENT in result

    def test_case_insensitive_starter(self):
        text = "upgrading to starter if volume confirms."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "starter" not in result.lower()
        assert _REPLACEMENT in result

    def test_no_upgrade_language_unchanged(self):
        text = "Watch for retest of FVG base before committing capital."
        result = _neutralize_near_entry_upgrade_language(text)
        assert result == text

    def test_empty_string(self):
        assert _neutralize_near_entry_upgrade_language("") == ""

    def test_neutral_dash_unchanged(self):
        assert _neutralize_near_entry_upgrade_language("—") == "—"

    def test_duplicate_replacement_collapsed(self):
        """Two upgrade sentences in same field → single replacement sentence."""
        text = (
            "Upgrade to SNIPE_IT once retest confirms. "
            "Upgrading to STARTER or SNIPE_IT after volume."
        )
        result = _neutralize_near_entry_upgrade_language(text)
        assert result.count(_REPLACEMENT) == 1

    def test_preserves_preceding_clean_sentence(self):
        """Non-upgrade sentence before upgrade sentence is not consumed."""
        text = "Volume confirmed expansion. Upgrade to SNIPE_IT if hold follows."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "Volume confirmed expansion" in result
        assert "SNIPE_IT" not in result

    def test_result_does_not_contain_capital_authorized(self):
        """Replacement text must not introduce capital-authorized language."""
        text = "Upgrade to SNIPE_IT once zone holds."
        result = _neutralize_near_entry_upgrade_language(text)
        assert "capital authorized" not in result.lower()
        assert "capital allowed" not in result.lower()

    def test_idempotent(self):
        """Running twice produces same result as running once."""
        text = "That would allow upgrade to SNIPE_IT consideration."
        once = _neutralize_near_entry_upgrade_language(text)
        twice = _neutralize_near_entry_upgrade_language(once)
        assert once == twice


# ===========================================================================
# _clean_near_entry_dangling_tails — unit tests
# ===========================================================================


class TestCleanNearEntryDanglingTails:
    def test_dot_number_dot(self):
        """'no capital.01.' artifact → 'no capital.'"""
        assert _clean_near_entry_dangling_tails("Watch-only; no capital.01.") == "Watch-only; no capital."

    def test_dot_space_only_dot(self):
        """'no capital. only.' artifact → 'no capital.'"""
        assert _clean_near_entry_dangling_tails("Watch-only; no capital. only.") == "Watch-only; no capital."

    def test_space_only_dot(self):
        """'no capital only.' artifact → 'no capital.'"""
        assert _clean_near_entry_dangling_tails("Watch-only; no capital only.") == "Watch-only; no capital."

    def test_space_only_no_trailing_dot(self):
        """'no capital only' (no trailing period) → 'no capital.'"""
        assert _clean_near_entry_dangling_tails("no capital only") == "no capital."

    def test_clean_no_capital_unchanged(self):
        """'no capital.' already clean → unchanged."""
        assert _clean_near_entry_dangling_tails("Watch-only; no capital.") == "Watch-only; no capital."

    def test_no_capital_mid_sentence(self):
        """Tail cleaned even when 'no capital' appears mid-sentence."""
        text = "Alert: no capital.01. More text."
        result = _clean_near_entry_dangling_tails(text)
        assert ".01." not in result
        assert "no capital." in result

    def test_empty_string(self):
        assert _clean_near_entry_dangling_tails("") == ""

    def test_case_insensitive(self):
        result = _clean_near_entry_dangling_tails("NO CAPITAL only.")
        assert "only" not in result.lower()

    def test_idempotent(self):
        text = "Watch-only; no capital.01."
        once = _clean_near_entry_dangling_tails(text)
        twice = _clean_near_entry_dangling_tails(once)
        assert once == twice


# ===========================================================================
# _finalize_near_entry_body_text — unit tests
# ===========================================================================


class TestFinalizeNearEntryBodyText:
    def test_upgrade_sentence_removed(self):
        text = "  Why:  Upgrade to SNIPE_IT if hold confirms."
        result = _finalize_near_entry_body_text(text)
        assert "SNIPE_IT" not in result
        assert _REPLACEMENT in result

    def test_tail_artifact_cleaned(self):
        text = "Watch-only; no capital.01."
        result = _finalize_near_entry_body_text(text)
        assert ".01." not in result
        assert "no capital." in result

    def test_combined_upgrade_and_tail(self):
        text = "Upgrade to STARTER consideration. no capital. only."
        result = _finalize_near_entry_body_text(text)
        assert "STARTER" not in result
        assert ". only." not in result

    def test_clean_text_unchanged(self):
        text = "Watch for retest. No capital yet."
        result = _finalize_near_entry_body_text(text)
        assert result == text

    def test_structural_label_prefix_preserved(self):
        """Structural label prefixes ('  Why:  ') must survive the pass."""
        text = "  Why:  Setup is forming but needs confirmation."
        result = _finalize_near_entry_body_text(text)
        assert "  Why:  " in result

    def test_idempotent(self):
        text = "Upgrade to SNIPE_IT once confirmed. no capital only."
        once = _finalize_near_entry_body_text(text)
        twice = _finalize_near_entry_body_text(once)
        assert once == twice


# ===========================================================================
# format_alert() integration — NEAR_ENTRY upgrade language in reason/next_action
# ===========================================================================


class TestFormatAlertNearEntryUpgradeLanguage:
    def _render(self, **overrides) -> str:
        return format_alert(_ne_signal(**overrides))

    def test_upgrade_to_snipe_it_in_reason_removed(self):
        text = self._render(
            reason="That would allow upgrade to SNIPE_IT consideration once zone holds."
        )
        assert "SNIPE_IT" not in text
        assert _REPLACEMENT in text

    def test_upgrade_to_starter_in_next_action_removed(self):
        text = self._render(
            next_action="If confirmed, evaluate upgrade to STARTER."
        )
        assert "STARTER" not in text
        assert _REPLACEMENT in text

    def test_upgrading_to_starter_or_snipe_it_in_next_action_removed(self):
        text = self._render(
            next_action="upgrading to STARTER or SNIPE_IT depending on volume and bar quality"
        )
        assert "SNIPE_IT" not in text
        assert "STARTER" not in text

    def test_clean_reason_unchanged(self):
        clean = "Structure repair in progress; no zone acceptance yet."
        text = self._render(reason=clean)
        assert clean in text

    def test_clean_next_action_unchanged(self):
        clean = "Watch for retest confirmation."
        text = self._render(next_action=clean)
        assert clean in text

    def test_no_capital_yet_always_present(self):
        """NEAR_ENTRY must always display 'NO CAPITAL YET'."""
        text = self._render(
            reason="Upgrade to SNIPE_IT consideration.",
            next_action="upgrading to STARTER if volume confirms.",
        )
        assert "NO CAPITAL YET" in text

    def test_upgrade_language_not_in_final_output(self):
        """Neither 'upgrade to SNIPE_IT' nor 'upgrade to STARTER' should appear."""
        text = self._render(
            reason="Upgrade to SNIPE_IT consideration.",
            next_action="Upgrading to STARTER or SNIPE_IT if confirmed.",
        )
        assert "upgrade to SNIPE_IT" not in text.lower()
        assert "upgrade to STARTER" not in text.lower()
        assert "upgrading to" not in text.lower()

    def test_replacement_does_not_introduce_capital_authorized(self):
        text = self._render(reason="Upgrade to SNIPE_IT consideration.")
        assert "capital authorized" not in text.lower()
        assert "capital allowed" not in text.lower()

    def test_tail_artifact_not_in_output(self):
        """Dangling tail artifacts from guard replacements must not appear."""
        text = self._render()
        assert ".01." not in text
        assert ". only." not in text

    def test_snipe_it_alert_not_affected(self):
        """SNIPE_IT alert must NOT have upgrade language stripped (not NEAR_ENTRY)."""
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
        # SNIPE_IT alert should render without upgrade-language stripping touching it
        assert "Enter at trigger." in text
        assert "Clean BOS with retest and hold." in text

    def test_wait_alert_not_affected(self):
        """WAIT alert must not have upgrade language stripping applied."""
        signal = {
            "final_tier": "WAIT",
            "score": 40,
            "ticker": "ABC",
            "final_signal": {
                "ticker": "ABC",
                "tier": "WAIT",
                "score": 40,
                "setup_family": "none",
                "structure_event": "none",
                "trend_state": "basing",
                "zone_type": "none",
                "trigger_level": None,
                "retest_status": "missing",
                "hold_status": "missing",
                "invalidation_condition": "—",
                "invalidation_level": None,
                "risk_reward": None,
                "overhead_status": "unknown",
                "forced_participation": "none",
                "next_action": "No action.",
                "capital_action": "no_trade",
                "reason": "No setup present.",
                "missing_conditions": [],
                "upgrade_trigger": "",
                "targets": [],
                "discord_channel": "none",
            },
        }
        text = format_alert(signal)
        assert "No action." in text

    def test_field_level_neutralization_before_render(self):
        """Upgrade language in reason must be neutralized before rendering,
        so the structural 'Why:' label is preserved in output."""
        text = self._render(reason="Upgrade to SNIPE_IT if zone holds.")
        assert "  Why:  " in text
        assert "SNIPE_IT" not in text

    def test_field_level_neutralization_next_action_label_preserved(self):
        """Upgrade language in next_action must be neutralized before rendering,
        so the structural 'Next:' label is preserved in output."""
        text = self._render(next_action="upgrading to STARTER once confirmed.")
        assert "  Next: " in text
        assert "STARTER" not in text

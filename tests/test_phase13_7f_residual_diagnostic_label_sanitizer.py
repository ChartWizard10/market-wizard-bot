"""Phase 13.7F — Residual diagnostic label sanitizer tests.

Covers:
  _sanitize_diagnostic_labels()  — unit tests for all known field/value pairs
  format_alert() integration     — AMKR live fixture, STARTER regression,
                                   SNIPE_IT regression
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _sanitize_diagnostic_labels,
    format_alert,
)

# ---------------------------------------------------------------------------
# Shared signal factories
# ---------------------------------------------------------------------------


def _ne_signal(**overrides) -> dict:
    """Minimal NEAR_ENTRY tiering_result dict."""
    base: dict = {
        "final_tier": "NEAR_ENTRY",
        "score": 63,
        "ticker": "TEST",
        "final_signal": {
            "ticker": "TEST",
            "tier": "NEAR_ENTRY",
            "score": 63,
            "setup_family": "reclaim",
            "structure_event": "MSS",
            "trend_state": "repair",
            "zone_type": "FVG",
            "trigger_level": 72.13,
            "retest_status": "partial",
            "hold_status": "partial",
            "invalidation_condition": "below FVG base",
            "invalidation_level": 71.67,
            "risk_reward": None,
            "overhead_status": "clear",
            "forced_participation": "none",
            "next_action": "Watch for zone retest and hold confirmation.",
            "capital_action": "wait_no_capital",
            "reason": "Structure repair in progress.",
            "missing_conditions": ["missing_retest", "missing_hold"],
            "upgrade_trigger": "Confirmed retest and hold of FVG.",
            "targets": [{"label": "T1", "level": 76.50, "reason": "prior swing high"}],
            "discord_channel": "#near-entry-watch",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
            # Keep final_signal in sync for keys shared at both levels (e.g. ticker, score).
            if k in base["final_signal"]:
                base["final_signal"][k] = v
        else:
            base["final_signal"][k] = v
    return base


def _starter_signal(**overrides) -> dict:
    """Minimal STARTER tiering_result dict."""
    base: dict = {
        "final_tier": "STARTER",
        "score": 77,
        "ticker": "TEST",
        "final_signal": {
            "ticker": "TEST",
            "tier": "STARTER",
            "score": 77,
            "setup_family": "continuation",
            "structure_event": "BOS",
            "trend_state": "fresh_expansion",
            "zone_type": "OB",
            "trigger_level": 150.00,
            "retest_status": "confirmed",
            "hold_status": "partial",
            "invalidation_condition": "below OB",
            "invalidation_level": 147.00,
            "risk_reward": 3.2,
            "overhead_status": "moderate",
            "forced_participation": "none",
            "next_action": "Enter at trigger with starter size.",
            "capital_action": "starter_only",
            "reason": "BOS confirmed; hold partial — starter only.",
            "missing_conditions": [],
            "upgrade_trigger": "",
            "targets": [{"label": "T1", "level": 158.00, "reason": "prior high"}],
            "discord_channel": "#starter-signals",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
        else:
            base["final_signal"][k] = v
    return base


def _snipe_signal(**overrides) -> dict:
    """Minimal SNIPE_IT tiering_result dict."""
    base: dict = {
        "final_tier": "SNIPE_IT",
        "score": 88,
        "ticker": "TEST",
        "final_signal": {
            "ticker": "TEST",
            "tier": "SNIPE_IT",
            "score": 88,
            "setup_family": "continuation",
            "structure_event": "BOS",
            "trend_state": "fresh_expansion",
            "zone_type": "FVG",
            "trigger_level": 200.00,
            "retest_status": "confirmed",
            "hold_status": "confirmed",
            "invalidation_condition": "below FVG base",
            "invalidation_level": 195.00,
            "risk_reward": 4.0,
            "overhead_status": "clear",
            "forced_participation": "none",
            "next_action": "Enter at trigger after live-chart confirmation.",
            "capital_action": "full_quality_allowed",
            "reason": "Clean BOS with confirmed retest and hold; overhead clear.",
            "missing_conditions": [],
            "upgrade_trigger": "",
            "targets": [{"label": "T1", "level": 210.00, "reason": "prior swing high"}],
            "discord_channel": "#snipe-signals",
        },
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = v
        else:
            base["final_signal"][k] = v
    return base


# ===========================================================================
# _sanitize_diagnostic_labels — unit tests
# ===========================================================================


class TestSanitizeDiagnosticLabels:
    # --- retest_status ---

    def test_retest_status_is_partial(self):
        result = _sanitize_diagnostic_labels("retest_status is partial")
        assert result == "retest is only partially confirmed"

    def test_retest_status_is_confirmed(self):
        result = _sanitize_diagnostic_labels("retest_status is confirmed")
        assert result == "retest is confirmed"

    def test_retest_status_is_missing(self):
        result = _sanitize_diagnostic_labels("retest_status is missing")
        assert result == "retest has not yet been confirmed"

    def test_retest_status_is_failed(self):
        result = _sanitize_diagnostic_labels("retest_status is failed")
        assert result == "retest failed"

    def test_retest_status_colon_partial(self):
        result = _sanitize_diagnostic_labels("retest_status: partial")
        assert result == "retest is only partially confirmed"

    # --- hold_status ---

    def test_hold_status_is_partial(self):
        result = _sanitize_diagnostic_labels("hold_status is partial")
        assert result == "hold is only partially confirmed"

    def test_hold_status_is_confirmed(self):
        result = _sanitize_diagnostic_labels("hold_status is confirmed")
        assert result == "hold is confirmed"

    def test_hold_status_is_missing(self):
        result = _sanitize_diagnostic_labels("hold_status is missing")
        assert result == "hold has not yet been confirmed"

    def test_hold_status_is_failed(self):
        result = _sanitize_diagnostic_labels("hold_status is failed")
        assert result == "hold failed"

    def test_hold_status_colon_partial(self):
        result = _sanitize_diagnostic_labels("hold_status: partial")
        assert result == "hold is only partially confirmed"

    # --- price_in_zone ---

    def test_price_in_zone_true(self):
        result = _sanitize_diagnostic_labels("price_in_zone is True")
        assert result == "price is inside the zone"

    def test_price_in_zone_false(self):
        result = _sanitize_diagnostic_labels("price_in_zone is False")
        assert result == "price is not yet inside the zone"

    def test_price_in_zone_colon_true(self):
        result = _sanitize_diagnostic_labels("price_in_zone: True")
        assert result == "price is inside the zone"

    # --- trigger_status ---

    def test_trigger_status_below(self):
        result = _sanitize_diagnostic_labels("trigger_status is below_trigger")
        assert result == "price remains below trigger"

    def test_trigger_status_above(self):
        result = _sanitize_diagnostic_labels("trigger_status is above_trigger")
        assert result == "price is above trigger"

    def test_trigger_status_at(self):
        result = _sanitize_diagnostic_labels("trigger_status is at_trigger")
        assert result == "price is at trigger"

    def test_trigger_status_colon_below(self):
        result = _sanitize_diagnostic_labels("trigger_status: below_trigger")
        assert result == "price remains below trigger"

    # --- overhead_status ---

    def test_overhead_status_is_moderate(self):
        result = _sanitize_diagnostic_labels("overhead_status is moderate")
        assert result == "overhead is moderate"

    def test_overhead_status_is_blocked(self):
        result = _sanitize_diagnostic_labels("overhead_status is blocked")
        assert result == "overhead is blocked"

    def test_overhead_status_is_clear(self):
        result = _sanitize_diagnostic_labels("overhead_status is clear")
        assert result == "overhead is clear"

    # --- invalidation_level ---

    def test_invalidation_level_colon_not_applicable_space(self):
        """'invalidation_level: not applicable' (space form) → human string."""
        result = _sanitize_diagnostic_labels("invalidation_level: not applicable")
        assert "retest_status" not in result
        assert "invalidation_level" not in result
        assert "executable invalidation" in result

    def test_invalidation_level_is_not_applicable_underscore(self):
        """'invalidation_level is not_applicable' (underscore form) → human string."""
        result = _sanitize_diagnostic_labels("invalidation_level is not_applicable")
        assert "invalidation_level" not in result
        assert "executable invalidation" in result

    # --- risk_state ---

    def test_risk_state_is_tight(self):
        result = _sanitize_diagnostic_labels("risk_state is tight")
        assert result == "risk window is tight relative to zone"

    def test_risk_state_is_healthy(self):
        result = _sanitize_diagnostic_labels("risk_state is healthy")
        assert result == "risk window is healthy"

    def test_risk_state_is_wide(self):
        result = _sanitize_diagnostic_labels("risk_state is wide")
        assert result == "risk window is wide"

    def test_risk_state_colon_tight(self):
        result = _sanitize_diagnostic_labels("risk_state: tight")
        assert result == "risk window is tight relative to zone"

    # --- General properties ---

    def test_case_insensitive_is_form(self):
        result = _sanitize_diagnostic_labels("RETEST_STATUS IS PARTIAL")
        assert "RETEST_STATUS" not in result
        assert "partially confirmed" in result.lower()

    def test_case_insensitive_colon_form(self):
        result = _sanitize_diagnostic_labels("HOLD_STATUS: CONFIRMED")
        assert "HOLD_STATUS" not in result
        assert "hold is confirmed" in result.lower()

    def test_inline_in_prose_amkr_case(self):
        """The live AMKR defect: label embedded inside a longer sentence."""
        text = (
            "Specific imperfection: retest_status is partial — price has approached "
            "the FVG but has not yet produced a confirmed body-close hold reaction "
            "inside the zone."
        )
        result = _sanitize_diagnostic_labels(text)
        assert "retest_status" not in result
        assert "retest is only partially confirmed" in result
        # Surrounding prose is preserved
        assert "price has approached the FVG" in result

    def test_multiple_labels_in_same_text(self):
        text = "retest_status is partial — hold_status is missing."
        result = _sanitize_diagnostic_labels(text)
        assert "retest_status" not in result
        assert "hold_status" not in result
        assert "retest is only partially confirmed" in result
        assert "hold has not yet been confirmed" in result

    def test_fallback_for_unknown_value(self):
        """Unknown value → human field name + human value (underscores stripped)."""
        result = _sanitize_diagnostic_labels("retest_status is pending_review")
        assert "retest_status" not in result
        assert "retest" in result
        assert "pending review" in result  # underscore stripped in fallback

    def test_clean_text_unchanged(self):
        text = "Watch for zone retest and hold confirmation."
        assert _sanitize_diagnostic_labels(text) == text

    def test_empty_string(self):
        assert _sanitize_diagnostic_labels("") == ""

    def test_none_like_dash_unchanged(self):
        assert _sanitize_diagnostic_labels("—") == "—"

    def test_idempotent(self):
        """Running twice produces same result as running once."""
        text = "retest_status is partial — hold_status is missing."
        once = _sanitize_diagnostic_labels(text)
        twice = _sanitize_diagnostic_labels(once)
        assert once == twice

    def test_no_field_labels_in_output(self):
        """None of the diagnostic field names should survive."""
        text = (
            "retest_status is partial; hold_status is missing; "
            "price_in_zone is False; trigger_status is below_trigger; "
            "overhead_status is moderate; risk_state is tight."
        )
        result = _sanitize_diagnostic_labels(text)
        for label in (
            "retest_status", "hold_status", "price_in_zone",
            "trigger_status", "overhead_status", "risk_state",
        ):
            assert label not in result, f"Label '{label}' survived sanitization"


# ===========================================================================
# format_alert() integration — AMKR live fixture
# ===========================================================================


class TestFormatAlertAmkrFixture:
    """Spec-mandated assertions for the AMKR near-entry live defect."""

    _AMKR_REASON = (
        "Specific imperfection: retest_status is partial — price has approached "
        "the FVG but has not yet produced a confirmed body-close hold reaction "
        "inside the zone."
    )

    def _render(self, **overrides) -> str:
        return format_alert(
            _ne_signal(
                ticker="AMKR",
                trigger_level=72.13,
                retest_status="partial",
                hold_status="partial",
                invalidation_level=71.67,
                reason=self._AMKR_REASON,
                **overrides,
            )
        )

    def test_output_contains_no_capital_watch_only(self):
        """Spec: output contains 'NO CAPITAL — WATCH ONLY'."""
        assert "NO CAPITAL — WATCH ONLY" in self._render()

    def test_output_does_not_contain_retest_status(self):
        """Spec: 'retest_status' is absent from rendered output."""
        assert "retest_status" not in self._render()

    def test_output_does_not_contain_hold_status(self):
        """Spec: 'hold_status' is absent from rendered output."""
        assert "hold_status" not in self._render()

    def test_output_does_not_contain_price_in_zone(self):
        """Spec: 'price_in_zone' is absent from rendered output."""
        assert "price_in_zone" not in self._render()

    def test_output_does_not_contain_trigger_status(self):
        """Spec: 'trigger_status' is absent from rendered output."""
        assert "trigger_status" not in self._render()

    def test_output_does_not_contain_overhead_status(self):
        """Spec: 'overhead_status' is absent from rendered output."""
        assert "overhead_status" not in self._render()

    def test_output_does_not_contain_invalidation_level_as_label(self):
        """Spec: 'invalidation_level' (raw label) is absent from rendered output."""
        text = self._render()
        # The word 'invalidation' may appear in 'Invalidation:' structural label —
        # that is expected.  The raw field name with underscore must not appear.
        assert "invalidation_level" not in text

    def test_human_meaning_retest_partial_present(self):
        """Spec: output still contains human meaning of 'retest is partial'."""
        text = self._render()
        # "retest is only partially confirmed" is the translated form
        assert "retest is only partially confirmed" in text

    def test_retest_context_prose_preserved(self):
        """Surrounding prose about price approaching FVG should survive."""
        text = self._render()
        assert "price has approached the FVG" in text

    def test_no_capital_context_present(self):
        """Spec: output explains no capital until retest and hold are confirmed."""
        text = self._render()
        # NEAR_ENTRY section header + ACTION sizing
        assert "NO CAPITAL" in text

    def test_why_label_preserved(self):
        """Structural 'Why:' label must not be consumed by the sanitizer."""
        assert "  Why:  " in self._render()

    def test_amkr_ticker_present(self):
        assert "AMKR" in self._render()

    def test_hold_status_in_reason_also_sanitized(self):
        """If hold_status also appears in reason, both are sanitized."""
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                reason=(
                    "retest_status is partial — zone approached but not held. "
                    "hold_status is missing — no body-close confirmation yet."
                ),
            )
        )
        assert "retest_status" not in text
        assert "hold_status" not in text
        assert "retest is only partially confirmed" in text
        assert "hold has not yet been confirmed" in text

    def test_risk_state_tight_in_next_action_sanitized(self):
        """risk_state is tight in next_action field is sanitized."""
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                next_action="risk_state is tight — manage size carefully.",
            )
        )
        assert "risk_state" not in text
        assert "risk window is tight" in text

    def test_price_in_zone_in_reason_sanitized(self):
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                reason="price_in_zone is False — price has not yet returned to FVG.",
            )
        )
        assert "price_in_zone" not in text
        assert "price is not yet inside the zone" in text

    def test_trigger_status_below_in_reason_sanitized(self):
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                reason="trigger_status is below_trigger; awaiting reclaim.",
            )
        )
        assert "trigger_status" not in text
        assert "price remains below trigger" in text

    def test_overhead_status_moderate_in_reason_sanitized(self):
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                reason="overhead_status is moderate — not blocking capital.",
            )
        )
        assert "overhead_status" not in text
        assert "overhead is moderate" in text

    def test_invalidation_level_colon_in_reason_sanitized(self):
        text = format_alert(
            _ne_signal(
                ticker="AMKR",
                reason="invalidation_level: not applicable — zone not yet confirmed.",
            )
        )
        assert "invalidation_level" not in text
        assert "executable invalidation" in text


# ===========================================================================
# format_alert() regression — STARTER (sanitizer must not damage valid text)
# ===========================================================================


class TestFormatAlertRegressionStarter:
    """STARTER tier: sanitizer must not damage valid trade language."""

    def _render(self, **overrides) -> str:
        return format_alert(_starter_signal(**overrides))

    def test_starter_conditions_met_present(self):
        assert "STARTER conditions met." in self._render()

    def test_starter_sizing_present(self):
        assert "STARTER SIZE ONLY" in self._render()

    def test_clean_reason_unchanged(self):
        """Clean reason without diagnostic labels is preserved exactly."""
        clean = "BOS confirmed; hold partial — starter only."
        assert clean in self._render()

    def test_clean_next_action_unchanged(self):
        clean = "Enter at trigger with starter size."
        assert clean in self._render()

    def test_ticker_present(self):
        assert "TEST" in self._render()

    def test_no_diagnostic_label_in_output(self):
        """No raw field labels must appear in a clean STARTER alert."""
        text = self._render()
        for label in (
            "retest_status", "hold_status", "price_in_zone",
            "trigger_status", "overhead_status", "risk_state",
        ):
            assert label not in text

    def test_starter_with_diagnostic_in_reason_sanitized(self):
        """Even for STARTER, diagnostic labels in reason are sanitized."""
        text = format_alert(
            _starter_signal(
                reason="retest_status is confirmed — clean retest; hold_status is partial.",
            )
        )
        assert "retest_status" not in text
        assert "hold_status" not in text
        assert "retest is confirmed" in text
        assert "hold is only partially confirmed" in text
        # STARTER tier wording must not be damaged
        assert "STARTER" in text

    def test_structural_execution_labels_unchanged(self):
        """Rendered 'Retest:' and 'Hold:' structural labels must not be consumed."""
        text = self._render()
        assert "  Retest:" in text
        assert "  Hold:" in text


# ===========================================================================
# format_alert() regression — SNIPE_IT (sanitizer must not damage valid text)
# ===========================================================================


class TestFormatAlertRegressionSnipeIt:
    """SNIPE_IT tier: sanitizer must not damage valid trade language."""

    def _render(self, **overrides) -> str:
        return format_alert(_snipe_signal(**overrides))

    def test_snipe_it_conditions_met_present(self):
        assert "SNIPE_IT conditions met." in self._render()

    def test_full_quality_present(self):
        assert "FULL QUALITY" in self._render()

    def test_clean_reason_unchanged(self):
        clean = "Clean BOS with confirmed retest and hold; overhead clear."
        assert clean in self._render()

    def test_clean_next_action_unchanged(self):
        clean = "Enter at trigger after live-chart confirmation."
        assert clean in self._render()

    def test_ticker_present(self):
        assert "TEST" in self._render()

    def test_no_diagnostic_label_in_output(self):
        text = self._render()
        for label in (
            "retest_status", "hold_status", "price_in_zone",
            "trigger_status", "overhead_status", "risk_state",
        ):
            assert label not in text

    def test_snipe_it_with_diagnostic_in_reason_sanitized(self):
        """Even for SNIPE_IT, diagnostic labels in reason are sanitized."""
        text = format_alert(
            _snipe_signal(
                reason=(
                    "retest_status is confirmed; overhead_status is clear. "
                    "Full quality setup."
                ),
            )
        )
        assert "retest_status" not in text
        assert "overhead_status" not in text
        assert "retest is confirmed" in text
        assert "overhead is clear" in text
        assert "SNIPE_IT" in text

    def test_structural_execution_labels_unchanged(self):
        """Rendered 'Retest:' and 'Hold:' structural labels must not be consumed."""
        text = self._render()
        assert "  Retest:" in text
        assert "  Hold:" in text

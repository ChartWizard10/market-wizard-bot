"""Phase 13.7D — Human-Facing Blocker / Upgrade Text Renderer tests.

Covers the humanization layer introduced in discord_alerts.py:

  _humanize_missing_condition()   — translates internal engine labels to
                                     human-readable text for the "Missing
                                     conditions:" line
  _humanize_upgrade_trigger()     — strips raw field labels; replaces
                                     tier-name references in NEAR_ENTRY upgrade
                                     trigger text with neutral watchlist language
  _humanize_blocker_note()        — strips raw diagnostic key_name: prefixes
                                     from blocker note text

Regression targets:

  LSTR-style bug — alert contained raw diagnostic labels such as:
    "retest_status: price has not returned to the FVG zone (179.24–179.26)
     since the BOS event, hold_status: no hold confirmation possible without retest"
  These must be stripped / translated at render time so Discord output reads
  as human trading-desk language.

  Tier-name leak — NEAR_ENTRY upgrade trigger text that says "upgrade to STARTER"
  or "upgrade to SNIPE_IT" must be replaced with neutral watchlist guidance.
"""

import pytest
from src.discord_alerts import (
    _CONDITION_LABEL_MAP,
    _humanize_blocker_note,
    _humanize_missing_condition,
    _humanize_upgrade_trigger,
    format_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tr(tier: str, **signal_overrides) -> dict:
    """Build a minimal tiering_result for format_alert()."""
    capital_map = {
        "SNIPE_IT":   "full_quality_allowed",
        "STARTER":    "starter_only",
        "NEAR_ENTRY": "wait_no_capital",
        "WAIT":       "no_trade",
    }
    channel_map = {
        "SNIPE_IT":   "#snipe-signals",
        "STARTER":    "#starter-signals",
        "NEAR_ENTRY": "#near-entry-watch",
        "WAIT":       "none",
    }
    signal = {
        "ticker": "TEST",
        "tier": tier,
        "score": 75,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "partial",
        "hold_status": "partial",
        "invalidation_condition": "Below FVG base",
        "invalidation_level": 95.00,
        "targets": [{"label": "T1", "level": 115.00, "reason": "Prior swing high"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": ["retest_not_confirmed"],
        "upgrade_trigger": "Full zone retest with hold confirmation.",
        "next_action": "Watch for zone acceptance.",
        "discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "reason": "Zone valid — awaiting retest.",
        "sanitized_reason": "Zone valid — awaiting retest.",
        "sanitized_next_action": None,
        "scan_price": 99.50,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "",
        "price_distance_to_trigger_pct": 0.5,
        "price_distance_to_invalidation_pct": 4.5,
        "risk_distance": 5.00,
        "risk_distance_pct": 5.0,
        "current_price_to_invalidation": 4.50,
        "current_price_to_invalidation_pct": 4.5,
        "risk_realism_state": "healthy",
        "risk_realism_note": None,
        "near_entry_blocker_note": (
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        ),
    }
    signal.update(signal_overrides)
    return {
        "ok": True,
        "final_tier": tier,
        "score": signal["score"],
        "safe_for_alert": True,
        "final_discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "final_signal": signal,
    }


# ---------------------------------------------------------------------------
# _humanize_missing_condition unit tests
# ---------------------------------------------------------------------------

class TestHumanizeMissingCondition:

    def test_missing_retest_exact_label(self):
        assert _humanize_missing_condition("missing_retest") == "Retest not yet confirmed"

    def test_missing_hold_exact_label(self):
        assert _humanize_missing_condition("missing_hold") == "Hold not yet confirmed"

    def test_current_acceptance_needed(self):
        result = _humanize_missing_condition("current_acceptance_needed")
        assert "zone acceptance" in result.lower() or "acceptance" in result.lower()

    def test_retest_not_confirmed(self):
        assert _humanize_missing_condition("retest_not_confirmed") == "Retest not yet confirmed"

    def test_hold_not_confirmed(self):
        assert _humanize_missing_condition("hold_not_confirmed") == "Hold not yet confirmed"

    def test_retest_partial(self):
        result = _humanize_missing_condition("retest_partial")
        assert "retest" in result.lower()
        assert "partial" in result.lower() or "awaiting" in result.lower()

    def test_hold_partial(self):
        result = _humanize_missing_condition("hold_partial")
        assert "hold" in result.lower()

    def test_overhead_path_not_clean(self):
        result = _humanize_missing_condition("overhead_path_not_clean")
        assert "overhead" in result.lower()

    def test_overhead_blocked(self):
        result = _humanize_missing_condition("overhead_blocked")
        assert "overhead" in result.lower()

    def test_dash_format_extracts_description(self):
        """'label — description' form: description extracted and capitalized."""
        cond = "trigger_acceptance — price is below trigger and has not confirmed acceptance above trigger"
        result = _humanize_missing_condition(cond)
        assert "trigger_acceptance" not in result.lower()
        assert "price is below trigger" in result.lower()
        # First letter should be uppercase
        assert result[0].isupper()

    def test_dash_format_with_map_match(self):
        """If the label part matches the map, use the map translation."""
        cond = "missing_retest — zone has not been tested"
        result = _humanize_missing_condition(cond)
        assert result == "Retest not yet confirmed"

    def test_raw_retest_status_prefix_stripped(self):
        """'retest_status: ...' prefix stripped; remaining text returned."""
        cond = "retest_status: price has not returned to the FVG zone"
        result = _humanize_missing_condition(cond)
        assert "retest_status:" not in result.lower()
        assert "price has not returned" in result.lower()

    def test_raw_hold_status_prefix_stripped(self):
        cond = "hold_status: no hold confirmation possible without retest"
        result = _humanize_missing_condition(cond)
        assert "hold_status:" not in result.lower()
        assert "no hold confirmation" in result.lower()

    def test_raw_price_in_zone_prefix_stripped(self):
        cond = "price_in_zone: price has not entered the demand zone"
        result = _humanize_missing_condition(cond)
        assert "price_in_zone:" not in result.lower()
        assert "price has not entered" in result.lower()

    def test_raw_trigger_status_prefix_stripped(self):
        cond = "trigger_status: trigger level not yet reached"
        result = _humanize_missing_condition(cond)
        assert "trigger_status:" not in result.lower()

    def test_raw_overhead_status_prefix_stripped(self):
        cond = "overhead_status: resistance cluster immediately above"
        result = _humanize_missing_condition(cond)
        assert "overhead_status:" not in result.lower()

    def test_unknown_label_returned_unchanged(self):
        """Unknown labels that don't match any pattern are returned as-is."""
        cond = "some_custom_condition"
        result = _humanize_missing_condition(cond)
        assert result == cond

    def test_empty_string(self):
        assert _humanize_missing_condition("") == ""

    def test_capitalization_applied(self):
        """Description from dash-format should have first letter capitalized."""
        cond = "trigger_acceptance — price is below the zone"
        result = _humanize_missing_condition(cond)
        assert result[0].isupper()


# ---------------------------------------------------------------------------
# _humanize_upgrade_trigger unit tests
# ---------------------------------------------------------------------------

class TestHumanizeUpgradeTrigger:

    def test_upgrade_to_starter_replaced_in_near_entry(self):
        text = "Confirmation upgrade to STARTER when retest holds."
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert "starter" not in result.lower()
        assert "starter" not in result.lower()

    def test_upgrade_to_snipe_it_replaced_in_near_entry(self):
        text = "Upgrade to SNIPE_IT once hold confirms."
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert "snipe_it" not in result.lower()

    def test_upgrading_to_starter_replaced(self):
        text = "Setup upgrading to STARTER after zone hold."
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert "starter" not in result.lower()

    def test_tier_refs_not_replaced_in_starter(self):
        """Tier name references in STARTER upgrade text are left unchanged."""
        text = "Confirmed hold may upgrade to SNIPE_IT on next cycle."
        result = _humanize_upgrade_trigger(text, "STARTER")
        # For STARTER, no tier replacement performed
        assert "snipe_it" in result.lower()

    def test_tier_refs_not_replaced_in_snipe_it(self):
        """Tier name references in SNIPE_IT upgrade text are left unchanged."""
        text = "Full conditions met; no upgrade to STARTER needed."
        result = _humanize_upgrade_trigger(text, "SNIPE_IT")
        assert "starter" in result.lower()

    def test_raw_field_label_stripped_in_near_entry(self):
        text = "retest_status: confirmed — upgrade to STARTER"
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert "retest_status:" not in result.lower()
        assert "starter" not in result.lower()

    def test_raw_field_label_stripped_in_starter(self):
        text = "hold_status: partial — wait for confirmation"
        result = _humanize_upgrade_trigger(text, "STARTER")
        assert "hold_status:" not in result.lower()
        assert "wait for confirmation" in result.lower()

    def test_clean_text_unchanged(self):
        """Clean trigger text passes through without modification."""
        text = "Full zone retest confirmed with body-close hold."
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert result == text

    def test_dash_sentinel_unchanged(self):
        assert _humanize_upgrade_trigger("—", "NEAR_ENTRY") == "—"

    def test_none_sentinel_unchanged(self):
        assert _humanize_upgrade_trigger("none", "NEAR_ENTRY") == "none"

    def test_replacement_text_is_neutral(self):
        """Replacement text does not contain tier names."""
        text = "upgrade to STARTER or upgrade to SNIPE_IT"
        result = _humanize_upgrade_trigger(text, "NEAR_ENTRY")
        assert "starter" not in result.lower()
        assert "snipe_it" not in result.lower()


# ---------------------------------------------------------------------------
# _humanize_blocker_note unit tests
# ---------------------------------------------------------------------------

class TestHumanizeBlockerNote:

    def test_retest_status_prefix_stripped(self):
        note = "retest_status: price has not returned to zone since BOS"
        result = _humanize_blocker_note(note)
        assert "retest_status:" not in result.lower()
        assert "price has not returned" in result.lower()

    def test_hold_status_prefix_stripped(self):
        note = "hold_status: no hold confirmation possible"
        result = _humanize_blocker_note(note)
        assert "hold_status:" not in result.lower()

    def test_clean_note_unchanged(self):
        note = "price is below trigger; wait for reclaim and hold above trigger"
        result = _humanize_blocker_note(note)
        assert result == note

    def test_empty_returns_empty(self):
        assert _humanize_blocker_note("") == ""

    def test_none_like_empty(self):
        assert _humanize_blocker_note(None) == None or _humanize_blocker_note("") == ""


# ---------------------------------------------------------------------------
# LSTR-style integration test — full format_alert() pipeline
# ---------------------------------------------------------------------------

class TestLSTRStyleIntegration:

    def test_lstr_raw_retest_hold_labels_not_in_output(self):
        """LSTR-style: raw 'retest_status:' and 'hold_status:' must not appear in alert."""
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=[
                "retest_status: price has not returned to the FVG zone (179.24–179.26)"
                " since the BOS event",
                "hold_status: no hold confirmation possible without retest",
            ],
            upgrade_trigger="Full zone retest with body-close hold.",
        )
        text = format_alert(tr)
        assert "retest_status:" not in text.lower()
        assert "hold_status:" not in text.lower()

    def test_lstr_description_text_preserved(self):
        """Content after the raw prefix is preserved in human-readable form."""
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=[
                "retest_status: price has not returned to the FVG zone (179.24) since BOS",
            ],
            upgrade_trigger="Full zone retest with body-close hold.",
        )
        text = format_alert(tr)
        assert "price has not returned" in text.lower()

    def test_lstr_combined_label_sentence_humanized(self):
        """Combined 'key: val, key: val' pattern stripped cleanly."""
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=[
                "retest_status: price has not returned to zone, hold_status: no hold possible",
            ],
            upgrade_trigger="Full zone retest with body-close hold.",
        )
        text = format_alert(tr)
        assert "retest_status:" not in text.lower()
        assert "hold_status:" not in text.lower()

    def test_lstr_full_alert_capital_contract_intact(self):
        """Capital language is unaffected by missing-condition humanization."""
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=["retest_status: not yet confirmed"],
            upgrade_trigger="Full zone retest with hold.",
        )
        text = format_alert(tr)
        assert "NO CAPITAL" in text or "WATCH ONLY" in text
        assert "FULL QUALITY" not in text

    def test_lstr_blocker_note_raw_labels_stripped(self):
        """Raw diagnostic labels in blocker note are stripped before rendering."""
        tr = _tr(
            "NEAR_ENTRY",
            near_entry_blocker_note=(
                "Blocker: retest_status: price has not returned to zone; "
                "hold_status: no hold possible without retest."
            ),
            missing_conditions=["missing_retest"],
        )
        text = format_alert(tr)
        assert "retest_status:" not in text.lower()
        assert "hold_status:" not in text.lower()


# ---------------------------------------------------------------------------
# Raw field label cannot appear in final alert — broad gate tests
# ---------------------------------------------------------------------------

class TestNoRawFieldLabelsInOutput:

    _RAW_LABELS = [
        "retest_status:",
        "hold_status:",
        "price_in_zone:",
        "trigger_status:",
        "overhead_status:",
    ]

    def _assert_no_raw_labels(self, text: str) -> None:
        for label in self._RAW_LABELS:
            assert label not in text.lower(), (
                f"Raw field label {label!r} leaked into alert output"
            )

    def test_near_entry_no_raw_labels_in_missing_conditions(self):
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=[
                "retest_status: not yet confirmed",
                "hold_status: awaiting hold",
                "price_in_zone: price outside zone",
            ],
        )
        self._assert_no_raw_labels(format_alert(tr))

    def test_near_entry_no_raw_labels_in_upgrade_trigger(self):
        tr = _tr(
            "NEAR_ENTRY",
            upgrade_trigger="retest_status: confirmed — upgrade to STARTER",
        )
        self._assert_no_raw_labels(format_alert(tr))

    def test_near_entry_no_raw_labels_in_blocker_note(self):
        tr = _tr(
            "NEAR_ENTRY",
            near_entry_blocker_note=(
                "Blocker: overhead_status: moderate — path not clear"
            ),
        )
        self._assert_no_raw_labels(format_alert(tr))

    def test_starter_no_raw_labels_in_output(self):
        tr = _tr(
            "STARTER",
            retest_status="confirmed",
            hold_status="confirmed",
            missing_conditions=[],
            near_entry_blocker_note=None,
            reason="BOS confirmed with hold. retest_status: confirmed, hold_status: confirmed.",
            sanitized_reason="BOS confirmed with hold. Conditions confirmed.",
        )
        self._assert_no_raw_labels(format_alert(tr))

    def test_snipe_it_no_raw_labels_in_output(self):
        tr = _tr(
            "SNIPE_IT",
            retest_status="confirmed",
            hold_status="confirmed",
            overhead_status="clear",
            missing_conditions=[],
            near_entry_blocker_note=None,
            reason="All conditions met. Path clear.",
            sanitized_reason="All conditions met. Path clear.",
        )
        self._assert_no_raw_labels(format_alert(tr))


# ---------------------------------------------------------------------------
# NEAR_ENTRY upgrade trigger must not mention STARTER or SNIPE_IT
# ---------------------------------------------------------------------------

class TestNearEntryUpgradeTierNameExclusion:

    def test_upgrade_to_starter_not_in_near_entry_alert(self):
        tr = _tr(
            "NEAR_ENTRY",
            upgrade_trigger=(
                "Upgrade to STARTER when retest and hold both confirm."
            ),
        )
        text = format_alert(tr)
        # Tier name should not appear in upgrade trigger line
        # (contract guard may still mention STARTER SIZE ONLY in sizing, but
        #  the upgrade trigger line must not say "upgrade to STARTER")
        lines = [l for l in text.split("\n") if "upgrade trigger" in l.lower()]
        assert len(lines) == 1
        assert "starter" not in lines[0].lower()

    def test_upgrade_to_snipe_it_not_in_near_entry_alert(self):
        tr = _tr(
            "NEAR_ENTRY",
            upgrade_trigger="Upgrade to SNIPE_IT once overhead clears.",
        )
        text = format_alert(tr)
        lines = [l for l in text.split("\n") if "upgrade trigger" in l.lower()]
        assert len(lines) == 1
        assert "snipe_it" not in lines[0].lower()

    def test_neutral_upgrade_text_unchanged(self):
        """Already-neutral upgrade text is left unchanged."""
        tr = _tr(
            "NEAR_ENTRY",
            upgrade_trigger="Full zone retest confirmed with body-close hold.",
        )
        text = format_alert(tr)
        lines = [l for l in text.split("\n") if "upgrade trigger" in l.lower()]
        assert len(lines) == 1
        assert "full zone retest" in lines[0].lower()

    def test_starter_alert_can_reference_snipe_it_in_trigger(self):
        """STARTER upgrade trigger is allowed to mention SNIPE_IT."""
        tr = _tr(
            "STARTER",
            retest_status="confirmed",
            hold_status="confirmed",
            missing_conditions=[],
            near_entry_blocker_note=None,
            upgrade_trigger="Full overhead clear may confirm SNIPE_IT entry.",
            reason="Starter candidate.",
            sanitized_reason="Starter candidate.",
        )
        text = format_alert(tr)
        # For STARTER tier, tier name references in upgrade text are not replaced
        # (NEAR_ENTRY-only restriction). The test simply confirms STARTER renders.
        assert "STARTER SIZE ONLY" in text


# ---------------------------------------------------------------------------
# Humanization does not alter capital contract
# ---------------------------------------------------------------------------

class TestCapitalContractUnchangedByHumanization:

    def test_near_entry_capital_contract_intact(self):
        tr = _tr("NEAR_ENTRY")
        text = format_alert(tr)
        assert "NO CAPITAL" in text or "WATCH ONLY" in text
        assert "FULL QUALITY" not in text
        assert "STARTER SIZE ONLY" not in text

    def test_starter_capital_contract_intact(self):
        tr = _tr(
            "STARTER",
            retest_status="confirmed",
            hold_status="confirmed",
            missing_conditions=[],
            near_entry_blocker_note=None,
            reason="Clean setup.",
            sanitized_reason="Clean setup.",
        )
        text = format_alert(tr)
        assert "STARTER SIZE ONLY" in text
        assert "NO CAPITAL — WATCH ONLY" not in text
        assert "FULL QUALITY" not in text

    def test_snipe_it_capital_contract_intact(self):
        tr = _tr(
            "SNIPE_IT",
            retest_status="confirmed",
            hold_status="confirmed",
            overhead_status="clear",
            missing_conditions=[],
            near_entry_blocker_note=None,
            reason="All conditions met.",
            sanitized_reason="All conditions met.",
        )
        text = format_alert(tr)
        assert "SNIPE_IT conditions met." in text
        assert "FULL QUALITY" in text
        assert "NO CAPITAL" not in text


# ---------------------------------------------------------------------------
# _CONDITION_LABEL_MAP structure sanity
# ---------------------------------------------------------------------------

class TestConditionLabelMapSanity:

    def test_all_values_are_non_empty_strings(self):
        for key, val in _CONDITION_LABEL_MAP.items():
            assert isinstance(val, str) and val.strip(), (
                f"_CONDITION_LABEL_MAP[{key!r}] is empty or not a string"
            )

    def test_all_values_start_with_uppercase(self):
        for key, val in _CONDITION_LABEL_MAP.items():
            assert val[0].isupper(), (
                f"_CONDITION_LABEL_MAP[{key!r}] = {val!r} does not start with uppercase"
            )

    def test_core_labels_present(self):
        assert "missing_retest" in _CONDITION_LABEL_MAP
        assert "missing_hold" in _CONDITION_LABEL_MAP
        assert "current_acceptance_needed" in _CONDITION_LABEL_MAP

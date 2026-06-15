"""Phase 14C.3B — Alert Truth Harmonization tests.

Five surgical defect fixes so a Discord alert never contradicts its own tier,
blocker, location, or candle evidence:

  1. NEAR_ENTRY blank blocker intelligence synthesized from available context.
  2. Generic completion language neutralized when candle confirmation is pending.
  3. Repeated-signal capital posture is explicit and tier-accurate.
  4. Duplicate scan-time freshness notes collapsed to one.
  5. Proof line harmonized with candle confirmation requirement.

All fixes are display-only.  No tier / score / capital / routing / suppression
/ dedup mutation.
"""

import copy

from src.discord_alerts import (
    format_alert,
    _is_blank_alert_field,
    _has_candle_confirmation_gap,
    _derive_missing_conditions,
    _derive_upgrade_trigger,
    _neutralize_completion_language_for_candle_gap,
    _derive_capital_posture_line,
    _dedupe_freshness_notes,
)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _loc(
    location_state="mid_zone_acceptance",
    zone_type="FVG",
    zone_low=44.0,
    zone_high=53.0,
    zone_mid=48.5,
    scan_price=45.5,
    confirmation_level=49.0,
    display_text="mid-zone acceptance — next proof above 53.00.",
) -> dict:
    return {
        "zone_type":         zone_type,
        "zone_low":          zone_low,
        "zone_high":         zone_high,
        "zone_mid":          zone_mid,
        "scan_price":        scan_price,
        "location_state":    location_state,
        "confirmation_level": confirmation_level,
        "display_text":      display_text,
        "flags":             [],
    }


def _candle(
    family="DOJI_INDECISION",
    veto="DOJI_AT_TRIGGER",
    verdict="NOT_AVAILABLE",
    status="OPEN_OR_UNKNOWN",
    display_text="indecision — doji/small body at decision area; "
                 "next candle verdict required.",
    score_delta=-2,
) -> dict:
    return {
        "status":              "ok",
        "candle_status":       status,
        "candle_family":       family,
        "candle_veto":         veto,
        "next_candle_verdict": verdict,
        "score_delta":         score_delta,
        "display_text":        display_text,
        "warnings":            [],
    }


def _tr(
    final_tier="SNIPE_IT",
    score=88,
    reason="Structure confirmed.",
    next_action="Enter on confirmation.",
    invalidation_level=44.0,
    trajectory_label="NEW_SIGNAL",
    trade_location=None,
    candle_evidence=None,
    retest_status="confirmed",
    hold_status="confirmed",
    structure_event="MSS",
    risk_realism_state="healthy",
    overhead_status="clear",
    sma_value_alignment="supportive",
    risk_reward=4.5,
    missing_conditions=None,
    upgrade_trigger="—",
    **signal_extra,
) -> dict:
    sig = {
        "ticker":               "HPE",
        "score":                score,
        "scan_price":           45.5,
        "zone_type":            "FVG",
        "setup_family":         "continuation",
        "structure_event":      structure_event,
        "trend_state":          "expansion",
        "risk_realism_state":   risk_realism_state,
        "overhead_status":      overhead_status,
        "retest_status":        retest_status,
        "hold_status":          hold_status,
        "risk_reward":          risk_reward,
        "sma_value_alignment":  sma_value_alignment,
        "missing_conditions":   missing_conditions or [],
        "invalidation_level":   invalidation_level,
        "invalidation_condition": "daily body close below zone",
        "reason":               reason,
        "next_action":          next_action,
        "upgrade_trigger":      upgrade_trigger,
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
    }
    sig.update(signal_extra)
    tr = {
        "final_tier":           final_tier,
        "score":                score,
        "safe_for_alert":       final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT":   "#snipe",
            "STARTER":    "#starter",
            "NEAR_ENTRY": "#near",
            "WAIT":       "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT":   "full_quality_allowed",
            "STARTER":    "starter_only",
            "NEAR_ENTRY": "wait_no_capital",
            "WAIT":       "no_trade",
        }.get(final_tier, "no_trade"),
        "trajectory": {"label": trajectory_label, "text": ""},
        "final_signal": sig,
    }
    if trade_location is not None:
        tr["trade_location"] = trade_location
    if candle_evidence is not None:
        tr["candle_evidence"] = candle_evidence
    return tr


# ===========================================================================
# Unit tests for the new pure helper functions
# ===========================================================================

class TestIsBlankAlertField:
    def test_none_is_blank(self):
        assert _is_blank_alert_field(None)

    def test_dash_is_blank(self):
        assert _is_blank_alert_field("—")
        assert _is_blank_alert_field("-")

    def test_none_string_is_blank(self):
        assert _is_blank_alert_field("none")
        assert _is_blank_alert_field("None")

    def test_empty_string_is_blank(self):
        assert _is_blank_alert_field("")
        assert _is_blank_alert_field("   ")

    def test_real_value_not_blank(self):
        assert not _is_blank_alert_field("Body close above 49.00")
        assert not _is_blank_alert_field("0")


class TestHasCandleConfirmationGap:
    def test_empty_dict_no_gap(self):
        assert not _has_candle_confirmation_gap({})

    def test_unknown_context_no_gap(self):
        ctx = {"status": "unknown", "candle_veto": "UNKNOWN",
               "next_candle_verdict": "UNKNOWN", "candle_family": None}
        assert not _has_candle_confirmation_gap(ctx)

    def test_veto_active_is_gap(self):
        assert _has_candle_confirmation_gap({"candle_veto": "DOJI_AT_TRIGGER"})
        assert _has_candle_confirmation_gap({"candle_veto": "HOSTILE_WICK"})

    def test_open_candle_is_gap(self):
        assert _has_candle_confirmation_gap({"candle_status": "OPEN_OR_UNKNOWN"})

    def test_pending_verdict_is_gap(self):
        assert _has_candle_confirmation_gap({"next_candle_verdict": "PENDING"})
        assert _has_candle_confirmation_gap({"next_candle_verdict": "NOT_AVAILABLE"})

    def test_doji_family_is_gap(self):
        assert _has_candle_confirmation_gap({"candle_family": "DOJI_INDECISION"})
        assert _has_candle_confirmation_gap({"candle_family": "ABSORPTION"})
        assert _has_candle_confirmation_gap({"candle_family": "UNRESOLVED"})

    def test_clean_retest_hold_no_gap(self):
        ctx = {
            "candle_veto": "NONE",
            "next_candle_verdict": "HOLD",
            "candle_family": "RETEST_HOLD",
            "candle_status": "CLOSED",
        }
        assert not _has_candle_confirmation_gap(ctx)


class TestDeriveMissingConditions:
    def test_blocker_note_is_primary(self):
        result = _derive_missing_conditions({}, {}, {}, "Overhead supply above 51.00.")
        assert result == "Overhead supply above 51.00."

    def test_retest_not_confirmed_synthesized(self):
        result = _derive_missing_conditions(
            {"retest_status": "partial", "hold_status": "confirmed"},
            {}, {}, ""
        )
        assert "retest" in result.lower()
        assert result != "—"

    def test_hold_not_confirmed_synthesized(self):
        result = _derive_missing_conditions(
            {"retest_status": "confirmed", "hold_status": "missing"},
            {}, {}, ""
        )
        assert "hold" in result.lower()
        assert result != "—"

    def test_lower_zone_defense_synthesized(self):
        result = _derive_missing_conditions(
            {"retest_status": "confirmed", "hold_status": "confirmed"},
            {},
            {"location_state": "lower_zone_defense"},
            ""
        )
        assert "lower zone" in result.lower()
        assert result != "—"

    def test_candle_veto_appended(self):
        result = _derive_missing_conditions(
            {"retest_status": "confirmed", "hold_status": "confirmed"},
            {"candle_veto": "DOJI_AT_TRIGGER"},
            {},
            ""
        )
        assert "doji" in result.lower()
        assert result != "—"

    def test_all_confirmed_no_context_returns_dash(self):
        result = _derive_missing_conditions(
            {"retest_status": "confirmed", "hold_status": "confirmed"},
            {}, {}, ""
        )
        assert result == "—"


class TestDeriveUpgradeTrigger:
    def test_confirmation_level_preferred(self):
        result = _derive_upgrade_trigger({}, {"confirmation_level": 49.0}, {})
        assert "49.00" in result
        assert "hold confirmation" in result.lower()

    def test_zone_low_fallback(self):
        result = _derive_upgrade_trigger({}, {"zone_low": 44.0}, {})
        assert "44.00" in result
        assert "hold confirmation" in result.lower()

    def test_candle_veto_fallback(self):
        result = _derive_upgrade_trigger(
            {}, {}, {"candle_veto": "DOJI_AT_TRIGGER"}
        )
        assert "next candle" in result.lower()
        assert "invalidation" in result.lower()

    def test_no_context_returns_dash(self):
        result = _derive_upgrade_trigger({}, {}, {})
        assert result == "—"

    def test_does_not_invent_prices(self):
        # No tl_ctx → should not return a numeric price
        result = _derive_upgrade_trigger({}, {}, {"candle_veto": "HOSTILE_WICK"})
        import re
        assert not re.search(r"\b\d+\.\d+\b", result)


class TestNeutralizeCompletionLanguage:
    def test_snipe_it_gap_replaces_all_conditions(self):
        text = "All SNIPE_IT conditions satisfied."
        out = _neutralize_completion_language_for_candle_gap(text, "SNIPE_IT", True)
        assert "All SNIPE_IT conditions satisfied" not in out
        assert "candle confirmation remains pending" in out

    def test_starter_gap_replaces_all_conditions(self):
        text = "All conditions satisfied; ready to enter."
        out = _neutralize_completion_language_for_candle_gap(text, "STARTER", True)
        assert "all conditions satisfied" not in out.lower()
        assert "full-size confirmation remains pending" in out

    def test_near_entry_gap_replaces_conditions(self):
        text = "All conditions met."
        out = _neutralize_completion_language_for_candle_gap(text, "NEAR_ENTRY", True)
        assert "all conditions met" not in out.lower()
        assert "execution confirmation remains incomplete" in out

    def test_no_gap_does_not_replace(self):
        text = "All SNIPE_IT conditions satisfied."
        out = _neutralize_completion_language_for_candle_gap(text, "SNIPE_IT", False)
        assert "All SNIPE_IT conditions satisfied" in out

    def test_preserves_capital_contract_headline(self):
        # "SNIPE_IT conditions met." lacks 'all' — must NOT be replaced.
        text = "  SNIPE_IT conditions met.\n  FULL QUALITY"
        out = _neutralize_completion_language_for_candle_gap(text, "SNIPE_IT", True)
        assert "SNIPE_IT conditions met." in out


class TestDeriveCapitalPostureLine:
    def test_snipe_candle_gap_hold_only(self):
        ce = _candle()
        result = _derive_capital_posture_line("SNIPE_IT", ce, {})
        assert "hold existing only" in result
        assert "no fresh add" in result

    def test_snipe_proof_above_hold_only(self):
        tl = {"confirmation_level": 49.0, "scan_price": 45.5}
        result = _derive_capital_posture_line("SNIPE_IT", {}, tl)
        assert "hold existing only" in result

    def test_snipe_clean_candle_proof_satisfied_conditional_add(self):
        ce = {
            "candle_veto": "NONE", "next_candle_verdict": "HOLD",
            "candle_family": "RETEST_HOLD", "candle_status": "CLOSED",
        }
        tl = {"confirmation_level": 45.0, "scan_price": 45.5}  # proof below scan
        result = _derive_capital_posture_line("SNIPE_IT", ce, tl)
        assert "add only after" in result
        assert "trigger/location" in result

    def test_near_entry_no_capital(self):
        result = _derive_capital_posture_line("NEAR_ENTRY", {}, {})
        assert "no capital" in result
        assert "watch only" in result

    def test_starter_starter_only(self):
        result = _derive_capital_posture_line("STARTER", {}, {})
        assert "starter only" in result
        assert "next proof" in result


class TestDedupeFreshnessNotes:
    def test_repeated_no_existing_note_returns_unified(self):
        notes = _dedupe_freshness_notes("", True, False)
        assert len(notes) == 1
        assert "scan-time" in notes[0].lower() or "scan time" in notes[0].lower()

    def test_repeated_scan_time_note_collapses_to_one(self):
        existing = "Signal based on scan-time price; verify live chart before entry."
        notes = _dedupe_freshness_notes(existing, True, False)
        assert len(notes) == 1

    def test_repeated_non_scan_note_keeps_both(self):
        existing = "Gap fill risk present."
        notes = _dedupe_freshness_notes(existing, True, False)
        assert len(notes) == 2
        assert notes[0] == existing

    def test_non_repeated_scan_time_note_collapses(self):
        existing = "Signal based on scan-time price; verify live chart before entry."
        notes = _dedupe_freshness_notes(existing, False, False)
        assert len(notes) == 1

    def test_non_repeated_no_note_returns_empty(self):
        notes = _dedupe_freshness_notes("", False, False)
        assert notes == []

    def test_candle_aware_uses_candle_language(self):
        notes = _dedupe_freshness_notes("", True, True)
        assert len(notes) == 1
        assert "candle state" in notes[0].lower()


# ===========================================================================
# Group 1 — Empty blocker intelligence cleanup (format_alert integration)
# ===========================================================================

class TestEmptyBlockerIntelligence:
    def test_near_entry_no_dash_missing_conditions(self):
        """NEAR_ENTRY with partial retest must never render 'Missing conditions: —'."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="confirmed",
            missing_conditions=[],
            upgrade_trigger="—",
            trade_location=_loc(),
            near_entry_blocker_note="",
        )
        body = format_alert(tr)
        assert "Missing conditions: —" not in body

    def test_near_entry_no_none_upgrade_trigger(self):
        """NEAR_ENTRY with location proof level must not render 'Upgrade trigger: none'."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="confirmed",
            missing_conditions=[],
            upgrade_trigger="none",
            trade_location=_loc(confirmation_level=49.0),
            near_entry_blocker_note="",
        )
        body = format_alert(tr)
        assert "Upgrade trigger:    none" not in body
        assert "Upgrade trigger:    —" not in body

    def test_near_entry_upgrade_trigger_uses_confirmation_level(self):
        """Synthesized upgrade trigger must include the confirmation level price."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="missing",
            missing_conditions=[],
            upgrade_trigger="—",
            trade_location=_loc(confirmation_level=49.0),
            near_entry_blocker_note="",
        )
        body = format_alert(tr)
        assert "49.00" in body

    def test_near_entry_blocker_note_is_primary_missing_condition(self):
        """If blocker note is present, it becomes the missing condition."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="confirmed",
            hold_status="confirmed",
            missing_conditions=[],
            upgrade_trigger="—",
            trade_location=_loc(),
            near_entry_blocker_note="Overhead resistance at 53.00 blocking capital.",
        )
        body = format_alert(tr)
        assert "Missing conditions: —" not in body

    def test_near_entry_hold_incomplete_synthesized(self):
        """Incomplete hold → missing conditions contains hold context."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="confirmed",
            hold_status="missing",
            missing_conditions=[],
            upgrade_trigger="—",
            trade_location=_loc(),
            near_entry_blocker_note="",
        )
        body = format_alert(tr)
        assert "hold" in body.lower()
        assert "Missing conditions: —" not in body


# ===========================================================================
# Group 2 — Candle caution completion neutralization
# ===========================================================================

class TestCandleCautionCompletionNeutralization:
    def test_snipe_unresolved_candle_no_all_conditions_satisfied(self):
        """SNIPE_IT + doji candle: 'All SNIPE_IT conditions satisfied.' must be gone."""
        ce = _candle(family="DOJI_INDECISION", veto="DOJI_AT_TRIGGER",
                     verdict="NOT_AVAILABLE")
        tr = _tr(
            "SNIPE_IT",
            reason="All SNIPE_IT conditions satisfied. Structure confirmed.",
            candle_evidence=ce,
            trade_location=_loc(),
        )
        body = format_alert(tr)
        assert "All SNIPE_IT conditions satisfied" not in body

    def test_snipe_unresolved_candle_renders_pending_language(self):
        """SNIPE_IT + doji candle: must render 'candle confirmation remains pending'."""
        ce = _candle(family="DOJI_INDECISION", veto="DOJI_AT_TRIGGER",
                     verdict="NOT_AVAILABLE")
        tr = _tr(
            "SNIPE_IT",
            reason="All SNIPE_IT conditions satisfied.",
            candle_evidence=ce,
            trade_location=_loc(),
        )
        body = format_alert(tr)
        assert "candle confirmation remains pending" in body

    def test_starter_candle_caution_no_fullsize_implication(self):
        """STARTER + absorption candle: no language implying full-size authorization."""
        ce = _candle(family="ABSORPTION", veto="HIGH_VOLUME_NO_PROGRESS",
                     verdict="NOT_AVAILABLE")
        tr = _tr(
            "STARTER",
            reason="All starter conditions met. All conditions satisfied.",
            candle_evidence=ce,
            trade_location=_loc(),
        )
        body = format_alert(tr)
        # Should not say "all conditions satisfied" while candle is cautionary.
        assert "all conditions satisfied" not in body.lower()

    def test_near_entry_candle_caution_watch_only_language(self):
        """NEAR_ENTRY + candle gap: must remain watch-only language."""
        ce = _candle(family="DOJI_INDECISION", veto="DOJI_AT_TRIGGER",
                     verdict="NOT_AVAILABLE")
        tr = _tr(
            "NEAR_ENTRY",
            reason="Structure exists; candle resolution needed.",
            missing_conditions=["retest_confirmed"],
            upgrade_trigger="—",
            candle_evidence=ce,
            trade_location=_loc(),
        )
        body = format_alert(tr)
        assert "capital authorized" not in body.lower()
        assert "full quality" not in body.lower()

    def test_no_gap_candle_does_not_neutralize(self):
        """When candle is confirmed RETEST_HOLD, completion language must survive."""
        ce = {
            "status": "ok",
            "candle_family": "RETEST_HOLD",
            "candle_veto": "NONE",
            "next_candle_verdict": "HOLD",
            "candle_status": "CLOSED",
            "display_text": "retest hold — zone defended.",
            "score_delta": 2,
            "warnings": [],
        }
        tr = _tr(
            "SNIPE_IT",
            reason="All SNIPE_IT conditions satisfied.",
            candle_evidence=ce,
            trade_location=_loc(),
        )
        body = format_alert(tr)
        # With no candle gap, the phrase may survive (or be handled by other guards).
        # The key invariant: no incorrect "candle confirmation remains pending".
        assert "candle confirmation remains pending" not in body


# ===========================================================================
# Group 3 — Repeated signal capital posture
# ===========================================================================

class TestRepeatedSignalCapitalPosture:
    def _repeated_tr(self, final_tier, candle_ev=None, tl=None):
        return _tr(
            final_tier,
            trajectory_label="REPEATED_NO_CHANGE",
            trade_location=tl or _loc(),
            candle_evidence=candle_ev,
        )

    def test_repeated_snipe_candle_pending_hold_existing_only(self):
        """Repeated SNIPE_IT + unresolved candle → hold existing, no fresh add."""
        ce = _candle(family="DOJI_INDECISION", veto="DOJI_AT_TRIGGER",
                     verdict="NOT_AVAILABLE")
        body = format_alert(self._repeated_tr("SNIPE_IT", candle_ev=ce))
        assert "hold existing only" in body.lower()
        assert "no fresh add" in body.lower()

    def test_repeated_snipe_proof_above_price_hold_existing_only(self):
        """Repeated SNIPE_IT + proof level still above scan price → hold existing."""
        # confirmation_level=49.0 > scan_price=45.5 → proof_above=True
        tl = _loc(confirmation_level=49.0, scan_price=45.5)
        body = format_alert(self._repeated_tr("SNIPE_IT", tl=tl))
        assert "hold existing only" in body.lower()

    def test_repeated_snipe_clean_candle_conditional_add(self):
        """Repeated SNIPE_IT + confirmed candle + proof satisfied → conditional add."""
        ce = {
            "status": "ok",
            "candle_family": "RETEST_HOLD",
            "candle_veto": "NONE",
            "next_candle_verdict": "HOLD",
            "candle_status": "CLOSED",
            "display_text": "retest hold confirmed.",
            "score_delta": 2,
            "warnings": [],
        }
        # confirmation_level=44.5 < scan_price=45.5 → proof satisfied
        tl = _loc(confirmation_level=44.5, scan_price=45.5)
        body = format_alert(self._repeated_tr("SNIPE_IT", candle_ev=ce, tl=tl))
        assert "add only after" in body.lower()

    def test_repeated_near_entry_no_capital_posture(self):
        """Repeated NEAR_ENTRY → capital posture says 'no capital; watch only'."""
        body = format_alert(self._repeated_tr("NEAR_ENTRY"))
        assert "no capital" in body.lower()
        assert "watch only" in body.lower()

    def test_repeated_starter_starter_only_posture(self):
        """Repeated STARTER → capital posture says 'starter only'."""
        body = format_alert(self._repeated_tr("STARTER"))
        assert "starter only" in body.lower()


# ===========================================================================
# Group 4 — Freshness note dedupe
# ===========================================================================

class TestFreshnessNoteDedupe:
    def test_repeated_signal_only_one_note(self):
        """Repeated alert with existing scan-time note renders exactly one Note: line."""
        tr = _tr(
            "SNIPE_IT",
            trajectory_label="REPEATED_NO_CHANGE",
            trade_location=_loc(),
            freshness_note="Signal based on scan-time price; verify live chart before entry.",
        )
        body = format_alert(tr)
        note_lines = [ln for ln in body.splitlines() if ln.strip().startswith("Note:")]
        assert len(note_lines) == 1, f"Expected 1 Note: line, got {len(note_lines)}"

    def test_no_duplicate_scan_time_notes(self):
        """Two scan-time notes with the same meaning must be collapsed."""
        tr = _tr(
            "SNIPE_IT",
            trajectory_label="REPEATED_NO_CHANGE",
            trade_location=_loc(),
            freshness_note="Signal based on scan-time price; verify live chart before entry.",
        )
        body = format_alert(tr)
        # Count occurrences of the scan-time keyword phrase
        count = body.lower().count("scan-time")
        assert count <= 1, f"'scan-time' appears {count} times — duplicate note present"

    def test_non_repeated_alert_keeps_original_note(self):
        """Non-repeated alert with a scan-time note keeps one note unchanged."""
        tr = _tr(
            "SNIPE_IT",
            trajectory_label="NEW_SIGNAL",
            trade_location=_loc(),
            freshness_note="Signal based on scan-time price; verify live chart before entry.",
        )
        body = format_alert(tr)
        note_lines = [ln for ln in body.splitlines() if ln.strip().startswith("Note:")]
        assert len(note_lines) == 1

    def test_non_scan_time_note_not_deduped(self):
        """A gap-fill risk note (not scan-time) is kept alongside any repeated note."""
        tr = _tr(
            "SNIPE_IT",
            trajectory_label="REPEATED_NO_CHANGE",
            trade_location=_loc(),
            freshness_note="Gap fill risk between 47.00 and 48.00.",
        )
        body = format_alert(tr)
        note_lines = [ln for ln in body.splitlines() if ln.strip().startswith("Note:")]
        # Gap note + unified scan-time note = 2 notes
        assert len(note_lines) == 2

    def test_no_note_field_repeated_adds_one(self):
        """Repeated alert with no freshness_note still gets one scan-time note."""
        tr = _tr(
            "SNIPE_IT",
            trajectory_label="REPEATED_NO_CHANGE",
            trade_location=_loc(),
        )
        body = format_alert(tr)
        note_lines = [ln for ln in body.splitlines() if ln.strip().startswith("Note:")]
        assert len(note_lines) == 1


# ===========================================================================
# Group 5 — Proof/candle harmonization
# ===========================================================================

class TestProofCandleHarmonization:
    def test_proof_above_price_candle_pending_includes_candle_requirement(self):
        """Proof line must include 'candle confirmation' when candle gap is active."""
        ce = _candle(family="DOJI_INDECISION", veto="DOJI_AT_TRIGGER",
                     verdict="NOT_AVAILABLE")
        # confirmation_level=49.0 > scan_price=45.5 → proof_above=True
        tr = _tr(
            "SNIPE_IT",
            candle_evidence=ce,
            trade_location=_loc(
                location_state="mid_zone_acceptance",
                confirmation_level=49.0,
                scan_price=45.5,
            ),
        )
        body = format_alert(tr)
        assert "candle confirmation" in body.lower()

    def test_proof_above_price_no_candle_gap_no_candle_suffix(self):
        """Without a candle gap, proof line must NOT add 'candle confirmation'."""
        ce = {
            "status": "ok",
            "candle_family": "RETEST_HOLD",
            "candle_veto": "NONE",
            "next_candle_verdict": "HOLD",
            "candle_status": "CLOSED",
            "display_text": "retest hold confirmed.",
            "score_delta": 2,
            "warnings": [],
        }
        tr = _tr(
            "SNIPE_IT",
            candle_evidence=ce,
            trade_location=_loc(
                location_state="mid_zone_acceptance",
                confirmation_level=49.0,
                scan_price=45.5,
            ),
        )
        body = format_alert(tr)
        # "candle confirmation" should NOT appear as a proof-line suffix
        # (it may appear in other lines, so just check the Proof: line)
        proof_lines = [ln for ln in body.splitlines() if "Proof:" in ln]
        for pl in proof_lines:
            assert "candle confirmation" not in pl.lower()

    def test_near_entry_proof_says_incomplete_not_aggression(self):
        """NEAR_ENTRY + mid_zone_acceptance + proof above price: proof note uses
        'execution proof remains incomplete', not 'fresh/add aggression'."""
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=["retest_confirmed"],
            upgrade_trigger="—",
            trade_location=_loc(
                location_state="mid_zone_acceptance",
                confirmation_level=49.0,
                scan_price=45.5,
            ),
        )
        body = format_alert(tr)
        assert "execution proof remains incomplete" in body
        assert "aggression" not in body.lower()


# ===========================================================================
# Group 6 — Invariants
# ===========================================================================

class TestInvariants:
    def _base_tr(self, final_tier="SNIPE_IT", **kw):
        return _tr(final_tier, trade_location=_loc(), **kw)

    def test_format_alert_does_not_mutate_final_tier(self):
        tr = self._base_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["final_tier"] == before["final_tier"]

    def test_format_alert_does_not_mutate_score(self):
        tr = self._base_tr(score=88)
        before_score = tr["score"]
        format_alert(tr)
        assert tr["score"] == before_score

    def test_format_alert_does_not_mutate_capital_action(self):
        tr = self._base_tr("STARTER")
        before = tr["capital_action"]
        format_alert(tr)
        assert tr["capital_action"] == before

    def test_format_alert_does_not_mutate_channel(self):
        tr = self._base_tr()
        before = tr["final_discord_channel"]
        format_alert(tr)
        assert tr["final_discord_channel"] == before

    def test_format_alert_does_not_mutate_safe_for_alert(self):
        tr = self._base_tr()
        before = tr["safe_for_alert"]
        format_alert(tr)
        assert tr["safe_for_alert"] == before

    def test_no_exception_on_missing_candle_evidence(self):
        tr = self._base_tr()
        assert "candle_evidence" not in tr
        body = format_alert(tr)
        assert isinstance(body, str)
        assert len(body) > 0

    def test_no_exception_on_malformed_candle_evidence(self):
        tr = self._base_tr(candle_evidence={"candle_veto": None, "status": "error"})
        body = format_alert(tr)
        assert isinstance(body, str)

    def test_no_exception_on_missing_trade_location(self):
        tr = _tr("SNIPE_IT")
        assert "trade_location" not in tr
        body = format_alert(tr)
        assert isinstance(body, str)

    def test_no_exception_on_near_entry_no_blocker(self):
        tr = _tr(
            "NEAR_ENTRY",
            missing_conditions=[],
            upgrade_trigger="—",
        )
        body = format_alert(tr)
        assert isinstance(body, str)
        assert "NO CAPITAL" in body

    def test_final_signal_score_unchanged(self):
        tr = self._base_tr(score=91)
        format_alert(tr)
        assert tr["final_signal"]["score"] == 91

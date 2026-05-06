"""Phase 13.7C — Final Alert Body Contract Hardener tests.

Covers two live post-deploy bugs and the normalization layer introduced in 13.7C:

  KOS bug  — STARTER alert: Why text contains "All SNIPE_IT conditions are satisfied."
             (the "are satisfied" variant was absent from Phase 13.7B STARTER forbidden list)
  LSTR bug — NEAR_ENTRY alert: contains "No no no capital..." — repeated replacement artifact
             triggered when "capital authorized" appeared inside a phrase already negated
             (e.g. "no capital authorized" → guard replaces "capital authorized" with
             "no capital", producing "no no capital"; if tiering.py also ran a sanitizer
             pass, it could stack to "no no no capital")

New functions tested:
  _normalize_repeated_capital_language()  — collapses "no no capital ..." runs
  _normalize_duplicate_punctuation()      — collapses ".." / "..." runs
  _apply_final_body_contract_guard()      — chains guard → normalizers

New forbidden phrases tested (STARTER):
  "all snipe_it conditions are satisfied"   (KOS bug phrase, 37 chars)
  "snipe_it conditions are satisfied"       (33 chars)
  "all snipe_it conditions cleared"         (31 chars)
  "all snipe_it conditions passed"          (30 chars)
  "all six snipe_it conditions"             (27 chars)
  "full-size allowed"                       (17 chars)
  "full size allowed"                       (17 chars)
  "enter long"                              (10 chars)

New forbidden phrases tested (NEAR_ENTRY):
  "capital is authorized"                   (21 chars — precedes "capital authorized")
"""

import pytest
from src.discord_alerts import (
    CAPITAL_CONTRACT,
    _apply_contract_guard,
    _apply_final_body_contract_guard,
    _normalize_duplicate_punctuation,
    _normalize_repeated_capital_language,
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
        "score": 80,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Below FVG base",
        "invalidation_level": 95.00,
        "targets": [{"label": "T1", "level": 115.00, "reason": "Prior swing high"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Watch for acceptance.",
        "discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "reason": "Clean structure.",
        "sanitized_reason": None,
        "sanitized_next_action": None,
        "scan_price": 100.00,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 5.0,
        "risk_distance": 5.00,
        "risk_distance_pct": 5.0,
        "current_price_to_invalidation": 5.00,
        "current_price_to_invalidation_pct": 5.0,
        "risk_realism_state": "healthy",
        "risk_realism_note": None,
        "near_entry_blocker_note": None,
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
# KOS bug: "All SNIPE_IT conditions are satisfied." in STARTER alert
# ---------------------------------------------------------------------------

class TestKOSBugStarterAresatisfied:
    """KOS-style STARTER alerts where Claude used the 'are satisfied' variant."""

    def test_kos_are_satisfied_stripped_from_starter(self):
        """'All SNIPE_IT conditions are satisfied.' must not appear in STARTER alert."""
        tr = _tr(
            "STARTER",
            reason=(
                "BOS confirmed with OB retest and hold. "
                "All SNIPE_IT conditions are satisfied. Full quality execution."
            ),
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "all snipe_it conditions are satisfied" not in text.lower()
        assert "All SNIPE_IT conditions are satisfied" not in text
        assert "STARTER SIZE ONLY" in text

    def test_kos_snipe_it_conditions_are_satisfied_lowercase(self):
        """Lowercase variant also stripped."""
        tr = _tr(
            "STARTER",
            reason="snipe_it conditions are satisfied — full-quality entry.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "snipe_it conditions are satisfied" not in text.lower()
        assert "FULL QUALITY" not in text

    def test_kos_replacement_is_starter_safe_language(self):
        """Replacement must not authorize full-size capital."""
        tr = _tr(
            "STARTER",
            reason="All SNIPE_IT conditions are satisfied. Proceed full size.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        # SNIPE_IT affirmation replaced — "are satisfied" variant must be gone
        assert "all snipe_it conditions are satisfied" not in text.lower()
        # Must carry STARTER capital language
        assert "STARTER SIZE ONLY" in text
        assert "FULL QUALITY" not in text
        assert "NO CAPITAL" not in text

    def test_kos_all_snipe_it_conditions_cleared(self):
        """'all snipe_it conditions cleared' variant stripped."""
        tr = _tr(
            "STARTER",
            reason="All SNIPE_IT conditions cleared — entering full quality.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "all snipe_it conditions cleared" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_kos_all_snipe_it_conditions_passed(self):
        """'all snipe_it conditions passed' variant stripped."""
        tr = _tr(
            "STARTER",
            reason="All SNIPE_IT conditions passed.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "all snipe_it conditions passed" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_kos_all_six_snipe_it_conditions(self):
        """'all six snipe_it conditions' phrase stripped."""
        tr = _tr(
            "STARTER",
            reason="All six SNIPE_IT conditions are in place for full capital.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "all six snipe_it conditions" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_kos_full_size_allowed_stripped(self):
        """'full-size allowed' stripped from STARTER."""
        tr = _tr(
            "STARTER",
            reason="Retest confirmed and hold confirmed. Full-size allowed.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "full-size allowed" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_kos_full_size_allowed_no_hyphen(self):
        """'full size allowed' (no hyphen) stripped from STARTER."""
        tr = _tr(
            "STARTER",
            reason="Full size allowed given strong structure.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "full size allowed" not in text.lower()
        assert "STARTER SIZE ONLY" in text

    def test_kos_enter_long_stripped_from_starter(self):
        """'enter long' stripped from STARTER alert."""
        tr = _tr(
            "STARTER",
            reason="Structure confirmed. Enter long at trigger.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert "enter long" not in text.lower()


# ---------------------------------------------------------------------------
# LSTR bug: "No no no capital..." repeated-replacement artifact
# ---------------------------------------------------------------------------

class TestLSTRBugRepeatedCapitalArtifact:
    """LSTR-style NEAR_ENTRY alerts producing 'no no no capital' artifacts."""

    def test_lstr_no_no_capital_normalized(self):
        """'no no capital' artifact collapsed to clean watch-only language."""
        # Simulate: "no capital authorized" → guard replaces "capital authorized"
        # with "no capital" → text becomes "no no capital"
        raw = "Watch setup: no no capital until confirmation."
        result = _normalize_repeated_capital_language(raw)
        assert "no no capital" not in result.lower()
        assert "no capital" in result.lower() or "watch-only" in result.lower()

    def test_lstr_triple_no_capital_normalized(self):
        """'no no no capital' (triple) artifact also collapsed."""
        raw = "No no no capital authorized here."
        result = _normalize_repeated_capital_language(raw)
        assert "no no no capital" not in result.lower()

    def test_lstr_capital_is_authorized_in_near_entry(self):
        """'capital is authorized' (21 char variant) replaced in NEAR_ENTRY."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="partial",
            overhead_status="clear",
            reason="Capital is authorized once retest confirms.",
            sanitized_reason=None,
            near_entry_blocker_note="Blocker: retest not confirmed.",
            missing_conditions=["retest_partial"],
            upgrade_trigger="Confirmed close inside zone.",
        )
        text = format_alert(tr)
        assert "capital is authorized" not in text.lower()
        assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    def test_lstr_no_capital_authorized_does_not_stack(self):
        """'no capital authorized' in NEAR_ENTRY must not produce 'no no capital'."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="partial",
            overhead_status="clear",
            reason="No capital authorized until retest confirms fully.",
            sanitized_reason=None,
            near_entry_blocker_note="Blocker: retest not confirmed.",
            missing_conditions=["retest_partial"],
            upgrade_trigger="Confirmed close inside zone.",
        )
        text = format_alert(tr)
        # Must not have stacked no-capital
        assert "no no capital" not in text.lower()
        assert "no no no capital" not in text.lower()
        # Must still carry no-capital language
        assert "NO CAPITAL" in text or "no capital" in text.lower() or "Watch-only" in text

    def test_lstr_full_pipeline_no_double_no_capital(self):
        """Full format_alert() output for NEAR_ENTRY must never have 'no no capital'."""
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="missing",
            hold_status="missing",
            overhead_status="moderate",
            reason=(
                "Setup approaching zone. No capital authorized until retest and hold "
                "are both confirmed. Capital is authorized at that point."
            ),
            sanitized_reason=None,
            near_entry_blocker_note=(
                "Blocker: retest missing; hold missing. Wait for zone interaction."
            ),
            missing_conditions=["retest_missing", "hold_missing"],
            upgrade_trigger="Confirmed close inside zone with body acceptance.",
        )
        text = format_alert(tr)
        assert "no no capital" not in text.lower()
        assert "no no no capital" not in text.lower()
        assert "NO CAPITAL" in text or "WATCH ONLY" in text


# ---------------------------------------------------------------------------
# Normalization unit tests
# ---------------------------------------------------------------------------

class TestNormalizationFunctions:

    def test_normalize_repeated_capital_no_capital_double(self):
        assert "no no capital" not in _normalize_repeated_capital_language(
            "No no capital here."
        ).lower()

    def test_normalize_repeated_capital_triple(self):
        result = _normalize_repeated_capital_language("no no no capital authorized")
        assert "no no no" not in result.lower()

    def test_normalize_repeated_capital_single_unchanged(self):
        """Single 'no capital' must not be altered."""
        result = _normalize_repeated_capital_language("Watch-only; no capital.")
        assert "no capital" in result.lower()

    def test_normalize_repeated_capital_case_insensitive(self):
        result = _normalize_repeated_capital_language("NO NO CAPITAL UNTIL CONFIRMED.")
        assert "no no capital" not in result.lower()

    def test_normalize_duplicate_period_double(self):
        result = _normalize_duplicate_punctuation("Confirmed.. Watch only.")
        assert ".." not in result

    def test_normalize_duplicate_period_triple(self):
        result = _normalize_duplicate_punctuation("Wait... no capital.")
        assert "..." not in result

    def test_normalize_duplicate_period_single_unchanged(self):
        """Single period must not be removed."""
        result = _normalize_duplicate_punctuation("Watch-only; no capital.")
        assert result.endswith(".")

    def test_normalize_duplicate_period_four_dots(self):
        result = _normalize_duplicate_punctuation("Forming....")
        assert "...." not in result
        assert "." in result


# ---------------------------------------------------------------------------
# _apply_final_body_contract_guard unit tests
# ---------------------------------------------------------------------------

class TestApplyFinalBodyContractGuard:

    def test_guard_then_normalize_order(self):
        """Guard runs first (may produce artifact), normalizer cleans it."""
        # Craft a string where "capital authorized" appears after "no " —
        # contract guard replaces "capital authorized" → "no capital",
        # producing "no no capital"; normalizer must then clean it.
        body = "Watch: no capital authorized until zone confirms."
        result = _apply_final_body_contract_guard("NEAR_ENTRY", body)
        assert "no no capital" not in result.lower()

    def test_guard_removes_starter_affirmation_in_near_entry(self):
        body = "STARTER conditions met. NO CAPITAL — WATCH ONLY."
        result = _apply_final_body_contract_guard("NEAR_ENTRY", body)
        assert "starter conditions met" not in result.lower()

    def test_guard_removes_snipe_it_affirmation_in_starter(self):
        body = "All SNIPE_IT conditions are satisfied. STARTER SIZE ONLY."
        result = _apply_final_body_contract_guard("STARTER", body)
        assert "all snipe_it conditions are satisfied" not in result.lower()

    def test_punctuation_cleaned_after_guard(self):
        """Double period produced by guard replacement is cleaned."""
        # "snipe_it conditions met." → "STARTER conditions met."
        # If reason ends with "snipe_it conditions met.." the replacement
        # might double the period; normalizer must collapse it.
        body = "STARTER SIZE ONLY. snipe_it conditions met.."
        result = _apply_final_body_contract_guard("STARTER", body)
        assert ".." not in result

    def test_idempotent_on_clean_starter_text(self):
        """Running guard twice on already-clean STARTER text is safe."""
        body = "STARTER conditions met.\nSTARTER SIZE ONLY — reduced-size capital only."
        first = _apply_final_body_contract_guard("STARTER", body)
        second = _apply_final_body_contract_guard("STARTER", first)
        assert first == second

    def test_idempotent_on_clean_near_entry_text(self):
        """Running guard twice on already-clean NEAR_ENTRY text is safe."""
        body = (
            "Near-entry watch — no capital until blocker resolves.\n"
            "NO CAPITAL — WATCH ONLY\n"
            "Watch-only; no capital."
        )
        first = _apply_final_body_contract_guard("NEAR_ENTRY", body)
        second = _apply_final_body_contract_guard("NEAR_ENTRY", first)
        assert first == second

    def test_idempotent_on_clean_snipe_it_text(self):
        """Running guard twice on already-clean SNIPE_IT text is safe."""
        body = (
            "SNIPE_IT conditions met.\n"
            "FULL QUALITY — capital authorized after live-chart verification."
        )
        first = _apply_final_body_contract_guard("SNIPE_IT", body)
        second = _apply_final_body_contract_guard("SNIPE_IT", first)
        assert first == second


# ---------------------------------------------------------------------------
# CAPITAL_CONTRACT structure sanity — Phase 13.7C additions
# ---------------------------------------------------------------------------

class TestCapitalContractStructure13_7C:

    def test_starter_has_are_satisfied_variant(self):
        """STARTER forbidden must include the KOS bug phrase."""
        phrases = [p for p, _ in CAPITAL_CONTRACT["STARTER"]["forbidden"]]
        assert "all snipe_it conditions are satisfied" in phrases

    def test_starter_are_satisfied_before_satisfied(self):
        """'are satisfied' (37) must appear before 'satisfied' (33) in list."""
        phrases = [p for p, _ in CAPITAL_CONTRACT["STARTER"]["forbidden"]]
        idx_are = phrases.index("all snipe_it conditions are satisfied")
        idx_plain = phrases.index("all snipe_it conditions satisfied")
        assert idx_are < idx_plain, (
            "'all snipe_it conditions are satisfied' must precede "
            "'all snipe_it conditions satisfied' to prevent partial shadowing"
        )

    def test_starter_snipe_are_satisfied_variant_present(self):
        """'snipe_it conditions are satisfied' (non-'all' form) also present."""
        phrases = [p for p, _ in CAPITAL_CONTRACT["STARTER"]["forbidden"]]
        assert "snipe_it conditions are satisfied" in phrases

    def test_starter_has_enter_long(self):
        phrases = [p for p, _ in CAPITAL_CONTRACT["STARTER"]["forbidden"]]
        assert "enter long" in phrases

    def test_starter_has_full_size_allowed_variants(self):
        phrases = [p for p, _ in CAPITAL_CONTRACT["STARTER"]["forbidden"]]
        assert "full-size allowed" in phrases
        assert "full size allowed" in phrases

    def test_near_entry_has_capital_is_authorized(self):
        """NEAR_ENTRY forbidden must include 'capital is authorized' (21-char form)."""
        phrases = [p for p, _ in CAPITAL_CONTRACT["NEAR_ENTRY"]["forbidden"]]
        assert "capital is authorized" in phrases

    def test_near_entry_capital_is_authorized_before_capital_authorized(self):
        """'capital is authorized' (21) must precede 'capital authorized' (18)."""
        phrases = [p for p, _ in CAPITAL_CONTRACT["NEAR_ENTRY"]["forbidden"]]
        idx_long = phrases.index("capital is authorized")
        idx_short = phrases.index("capital authorized")
        assert idx_long < idx_short, (
            "'capital is authorized' must precede 'capital authorized' "
            "to prevent the shorter form from shadow-matching first"
        )

    def test_near_entry_no_replacement_contains_capital_authorized(self):
        """No NEAR_ENTRY replacement string may contain 'capital authorized'.

        If any replacement contained 'capital authorized', the guard could
        re-match its own output in a subsequent pass, producing infinite
        or cascading replacements.
        """
        for match, replacement in CAPITAL_CONTRACT["NEAR_ENTRY"]["forbidden"]:
            assert "capital authorized" not in replacement.lower(), (
                f"Replacement for {match!r} contains 'capital authorized', "
                "which would trigger re-matching on a second guard pass."
            )

    def test_starter_forbidden_longest_first_for_snipe_it_variants(self):
        """All SNIPE_IT-variant phrases in STARTER must be ordered longest-first."""
        snipe_phrases = [
            (p, r) for p, r in CAPITAL_CONTRACT["STARTER"]["forbidden"]
            if "snipe_it" in p
        ]
        lengths = [len(p) for p, _ in snipe_phrases]
        for i in range(len(lengths) - 1):
            # Allow ties but not reversal
            assert lengths[i] >= lengths[i + 1], (
                f"STARTER SNIPE_IT forbidden phrases not longest-first: "
                f"{snipe_phrases[i][0]!r} ({lengths[i]}) before "
                f"{snipe_phrases[i+1][0]!r} ({lengths[i+1]})"
            )


# ---------------------------------------------------------------------------
# Full format_alert() regression — existing tiers unaffected
# ---------------------------------------------------------------------------

class TestExistingTierContractUnaffected:

    def test_snipe_it_contract_intact(self):
        tr = _tr("SNIPE_IT", reason="Clean structure with confirmed retest and hold.")
        text = format_alert(tr)
        assert "SNIPE_IT conditions met." in text
        assert "FULL QUALITY" in text
        assert "NO CAPITAL" not in text

    def test_starter_contract_intact(self):
        tr = _tr("STARTER", reason="Retest partial but OB demand holds.")
        text = format_alert(tr)
        assert "STARTER conditions met." in text
        assert "STARTER SIZE ONLY" in text
        assert "NO CAPITAL — WATCH ONLY" not in text
        assert "FULL QUALITY" not in text

    def test_near_entry_contract_intact(self):
        tr = _tr(
            "NEAR_ENTRY",
            retest_status="partial",
            hold_status="partial",
            reason="Retest partial; zone not yet confirmed.",
            near_entry_blocker_note="Blocker: retest not confirmed.",
            missing_conditions=["retest_partial"],
            upgrade_trigger="Confirmed body close inside zone.",
        )
        text = format_alert(tr)
        assert "NO CAPITAL" in text or "WATCH ONLY" in text
        assert "FULL QUALITY" not in text
        assert "SNIPE_IT conditions met" not in text

    def test_full_size_confirmation_not_granted_preserved_in_starter(self):
        """'full-size confirmation not granted' is valid STARTER denial language."""
        tr = _tr(
            "STARTER",
            reason=(
                "BOS confirmed with OB retest and hold. Overhead moderate — "
                "full-size confirmation not granted. Starter size only."
            ),
            sanitized_reason=None,
        )
        text = format_alert(tr)
        # "full-size confirmation not granted" must survive (not be stripped)
        assert "full-size confirmation not granted" in text
        assert "STARTER SIZE ONLY" in text

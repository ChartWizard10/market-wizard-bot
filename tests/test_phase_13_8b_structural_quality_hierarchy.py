"""Phase 13.8B — Structural Quality Hierarchy tests.

Covers:
  _evaluate_quality_dimensions() — per-dimension grading for all 5 dimensions
  _evaluate_setup_quality()      — A_PLUS_ELITE label and 5-dimension label logic
  _build_quality_phrase()        — dynamic phrase generation for top 3 labels
  format_alert() integration     — elite/candidate/starter phrases in ACTION section
  No-side-effect guards          — tier, capital, routing unchanged by quality label
  Discrimination gap fix         — institutional-grade vs marginal-pass produce different output
"""

from __future__ import annotations

import pytest

from src.discord_alerts import (
    _evaluate_quality_dimensions,
    _evaluate_setup_quality,
    _build_quality_phrase,
    _QUALITY_LABEL_PHRASES,
    format_alert,
)


# ---------------------------------------------------------------------------
# Signal factories
# ---------------------------------------------------------------------------


def _base_signal(**overrides) -> dict:
    """All-premium baseline: BOS+continuation, fresh_expansion, OB, clear, healthy, rr=4.5."""
    base = {
        "ticker": "TEST",
        "tier": "SNIPE_IT",
        "score": 92,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "zone_type": "OB",
        "trigger_level": 200.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below OB",
        "invalidation_level": 195.00,
        "risk_reward": 4.5,
        "overhead_status": "clear",
        "sma_value_alignment": "supportive",
        "forced_participation": "none",
        "next_action": "Enter at trigger.",
        "capital_action": "full_quality_allowed",
        "reason": "Elite BOS with confirmed hold and institutional zone.",
        "missing_conditions": [],
        "upgrade_trigger": "",
        "targets": [{"label": "T1", "level": 220.00, "reason": "prior high"}],
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
        "near_entry_blocker_note": None,
    }
    base.update(overrides)
    return base


def _tiering_result(final_tier: str, **signal_overrides) -> dict:
    sig = _base_signal(**signal_overrides)
    sig["tier"] = final_tier
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
    # Phase 15C: mirror tiering's quality label contract — premium language is
    # explicitly allowed only on clean SNIPE_IT.
    sig.setdefault("quality_label_allowed", final_tier == "SNIPE_IT")
    return {
        "final_tier": final_tier,
        "score": sig["score"],
        "ticker": sig["ticker"],
        "final_signal": sig,
    }


def _ne_tiering_result(**signal_overrides) -> dict:
    defaults = {
        "retest_status": "partial",
        "hold_status": "missing",
        "risk_reward": None,
        "risk_realism_state": "unknown",
        "missing_conditions": ["retest_confirmed", "hold_confirmed"],
        "upgrade_trigger": "Confirmed retest and hold of FVG.",
        "next_action": "Watch for retest confirmation.",
        "reason": "Structure repair in progress.",
        "near_entry_blocker_note": (
            "Blocker: retest is not fully confirmed; wait for zone interaction."
        ),
        "score": 62,
    }
    defaults.update(signal_overrides)
    return _tiering_result("NEAR_ENTRY", **defaults)


# ===========================================================================
# _evaluate_quality_dimensions — per-dimension unit tests
# ===========================================================================


class TestDimension1StructuralFreshness:
    """trend_state grading."""

    def test_fresh_expansion_is_premium(self):
        sig = _base_signal(trend_state="fresh_expansion")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        # Dim 1 is first grade; all other dims premium in base signal (rr=4.5)
        assert n_prem == 5

    def test_basing_is_premium(self):
        sig = _base_signal(trend_state="basing")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5  # still all-premium (rr=4.5 base)

    def test_mature_continuation_is_standard(self):
        sig = _base_signal(trend_state="mature_continuation")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4   # one non-premium
        assert n_disc == 0

    def test_transition_is_standard(self):
        sig = _base_signal(trend_state="transition")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_repair_is_discount(self):
        sig = _base_signal(trend_state="repair")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_failure_is_discount(self):
        sig = _base_signal(trend_state="failure")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_unknown_trend_state_is_discount(self):
        sig = _base_signal(trend_state="")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1


class TestDimension2SequenceQuality:
    """structure_event + setup_family pair grading."""

    def test_bos_continuation_is_premium(self):
        sig = _base_signal(structure_event="BOS", setup_family="continuation")
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_bos_accepted_break_is_premium(self):
        sig = _base_signal(structure_event="BOS", setup_family="accepted_break")
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_bos_compression_to_expansion_is_premium(self):
        sig = _base_signal(
            structure_event="BOS", setup_family="compression_to_expansion"
        )
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_bos_squeeze_family_is_standard(self):
        """BOS with non-premium family → standard (not premium, not discount)."""
        sig = _base_signal(structure_event="BOS", setup_family="squeeze")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_mss_continuation_is_standard(self):
        sig = _base_signal(structure_event="MSS", setup_family="continuation")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_choch_is_discount(self):
        sig = _base_signal(structure_event="CHOCH", setup_family="reversal")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_reversal_family_is_discount(self):
        sig = _base_signal(structure_event="MSS", setup_family="reversal")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_exhaustion_trap_family_is_discount(self):
        sig = _base_signal(structure_event="MSS", setup_family="exhaustion_trap")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_none_structure_event_is_discount(self):
        sig = _base_signal(structure_event="none", setup_family="continuation")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1


class TestDimension3ZonePrecision:
    """zone_type grading."""

    def test_ob_is_premium(self):
        sig = _base_signal(zone_type="OB")
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_fvg_is_premium(self):
        sig = _base_signal(zone_type="FVG")
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_demand_is_standard(self):
        sig = _base_signal(zone_type="demand")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_flip_zone_is_standard(self):
        sig = _base_signal(zone_type="flip_zone")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_support_cluster_is_discount(self):
        sig = _base_signal(zone_type="support_cluster")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_zone_none_is_discount(self):
        sig = _base_signal(zone_type="none")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1


class TestDimension4PathOpenness:
    """overhead_status (+ blocker check) grading."""

    def test_clear_is_premium(self):
        sig = _base_signal(overhead_status="clear", near_entry_blocker_note=None)
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_moderate_no_blocker_is_standard(self):
        sig = _base_signal(overhead_status="moderate", near_entry_blocker_note="")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_moderate_with_overhead_blocker_is_discount(self):
        sig = _base_signal(
            overhead_status="moderate",
            near_entry_blocker_note="Overhead resistance is blocking the path.",
        )
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_blocked_is_discount(self):
        sig = _base_signal(overhead_status="blocked")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_unknown_overhead_is_discount(self):
        sig = _base_signal(overhead_status="unknown")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1


class TestDimension5RiskProfile:
    """risk_realism_state + risk_reward grading."""

    def test_healthy_rr_gte_4_is_premium(self):
        sig = _base_signal(risk_realism_state="healthy", risk_reward=4.0)
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_healthy_rr_above_4_is_premium(self):
        sig = _base_signal(risk_realism_state="healthy", risk_reward=5.2)
        n_prem, _n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5

    def test_healthy_rr_lt_4_is_standard(self):
        sig = _base_signal(risk_realism_state="healthy", risk_reward=3.5)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_healthy_rr_none_is_standard(self):
        sig = _base_signal(risk_realism_state="healthy", risk_reward=None)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_tight_rr_gte_35_is_standard(self):
        sig = _base_signal(risk_realism_state="tight", risk_reward=3.5)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 4
        assert n_disc == 0

    def test_tight_rr_lt_35_is_discount(self):
        sig = _base_signal(risk_realism_state="tight", risk_reward=3.0)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_fragile_is_discount(self):
        sig = _base_signal(risk_realism_state="fragile", risk_reward=4.0)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1

    def test_unknown_risk_state_is_discount(self):
        sig = _base_signal(risk_realism_state="unknown", risk_reward=4.0)
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc >= 1


class TestSmaAlignmentSupplement:
    """SMA hostility increments n_discount without consuming a dimension slot."""

    def test_hostile_sma_adds_one_discount(self):
        """All 5 dimensions premium + hostile SMA → n_premium=5 but n_discount=1."""
        sig = _base_signal(sma_value_alignment="hostile")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5
        assert n_disc == 1

    def test_supportive_sma_no_effect(self):
        sig = _base_signal(sma_value_alignment="supportive")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_prem == 5
        assert n_disc == 0

    def test_mixed_sma_no_extra_discount(self):
        sig = _base_signal(sma_value_alignment="mixed")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc == 0

    def test_unavailable_sma_no_extra_discount(self):
        sig = _base_signal(sma_value_alignment="unavailable")
        n_prem, n_disc = _evaluate_quality_dimensions(sig)
        assert n_disc == 0


# ===========================================================================
# _evaluate_setup_quality — A_PLUS_ELITE label tests
# ===========================================================================


class TestAPlusEliteLabel:
    """A_PLUS_ELITE requires all 5 premium, 0 discounts, both confirmed."""

    def test_elite_with_all_five_premium(self):
        """rr=4.5 base gives Dim5=premium → all five premium → A_PLUS_ELITE."""
        sig = _base_signal(
            retest_status="confirmed",
            hold_status="confirmed",
            sma_value_alignment="supportive",
        )
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_ELITE"

    def test_elite_with_fvg_zone(self):
        sig = _base_signal(zone_type="FVG", sma_value_alignment="supportive")
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_ELITE"

    def test_elite_blocked_by_standard_dim(self):
        """One standard dimension (n_premium=4) → A_PLUS_CANDIDATE, not ELITE."""
        sig = _base_signal(trend_state="mature_continuation")
        assert _evaluate_setup_quality(sig, "SNIPE_IT") == "A_PLUS_CANDIDATE"

    def test_elite_blocked_by_any_discount(self):
        """One discount dimension → n_discount=1 → A_PLUS_CANDIDATE or lower."""
        sig = _base_signal(risk_realism_state="fragile")
        label = _evaluate_setup_quality(sig, "SNIPE_IT")
        assert label != "A_PLUS_ELITE"

    def test_elite_blocked_by_sma_hostile(self):
        """Hostile SMA adds supplemental discount → n_discount=1 → not ELITE."""
        sig = _base_signal(sma_value_alignment="hostile")
        label = _evaluate_setup_quality(sig, "SNIPE_IT")
        assert label != "A_PLUS_ELITE"

    def test_elite_requires_both_confirmed(self):
        """All 5 premium but retest missing → neither confirmed → not ELITE."""
        sig = _base_signal(retest_status="missing")
        label = _evaluate_setup_quality(sig, "SNIPE_IT")
        assert label != "A_PLUS_ELITE"

    def test_elite_requires_hold_confirmed(self):
        sig = _base_signal(hold_status="partial")
        label = _evaluate_setup_quality(sig, "SNIPE_IT")
        assert label != "A_PLUS_ELITE"

    def test_elite_label_in_label_phrases_dict(self):
        assert "A_PLUS_ELITE" in _QUALITY_LABEL_PHRASES

    def test_elite_phrase_prefix_is_high_quality_executable(self):
        # Phase 15C: prestige label retired.
        assert _QUALITY_LABEL_PHRASES["A_PLUS_ELITE"] == "High-quality executable"


# ===========================================================================
# _build_quality_phrase — dynamic phrase generation tests
# ===========================================================================


class TestBuildQualityPhrase:
    """Dynamic phrase output for top-three labels."""

    def _elite_signal(self) -> dict:
        # quality_label_allowed=True mirrors tiering's clean-SNIPE_IT contract.
        return _base_signal(sma_value_alignment="supportive", quality_label_allowed=True)

    def _candidate_signal(self) -> dict:
        # 4 premium (healthy+rr=3.5 → standard), 0 discounts
        return _base_signal(risk_reward=3.5, quality_label_allowed=True)

    def _starter_signal(self) -> dict:
        # both confirmed but 1 discount (fragile risk)
        return _base_signal(risk_realism_state="fragile", quality_label_allowed=True)

    def test_elite_phrase_starts_with_high_quality(self):
        # Phase 15C: "Elite candidate" retired.
        phrase = _build_quality_phrase("A_PLUS_ELITE", self._elite_signal())
        assert phrase.startswith("High-quality executable")

    def test_elite_phrase_uses_audit_safe_count(self):
        # Phase 15C: "all five … institutional-grade" retired; only the
        # audit-safe X/5 form may render.
        phrase = _build_quality_phrase("A_PLUS_ELITE", self._elite_signal())
        assert "premium dimensions: 5/5" in phrase
        assert "all five" not in phrase.lower()
        assert "institutional" not in phrase.lower()

    def test_candidate_phrase_starts_with_complete_sequence(self):
        phrase = _build_quality_phrase("A_PLUS_CANDIDATE", self._candidate_signal())
        assert phrase.startswith("Complete sequence")

    def test_candidate_phrase_includes_dimension_count(self):
        """Phrase should contain the actual premium count."""
        phrase = _build_quality_phrase("A_PLUS_CANDIDATE", self._candidate_signal())
        # 4 of 5 dimensions premium for this signal — audit-safe X/5 form
        assert "premium dimensions: 4/5" in phrase

    def test_candidate_phrase_contains_confirmed(self):
        phrase = _build_quality_phrase("A_PLUS_CANDIDATE", self._candidate_signal())
        assert "confirmed" in phrase

    def test_starter_phrase_starts_with_confirmed_sequence(self):
        phrase = _build_quality_phrase("CLEAN_STARTER", self._starter_signal())
        assert phrase.startswith("Confirmed sequence")

    def test_starter_phrase_includes_premium_count(self):
        phrase = _build_quality_phrase("CLEAN_STARTER", self._starter_signal())
        # fragile risk = 1 discount → 4 premium dims — audit-safe X/5 form
        assert "premium dimensions: 4/5" in phrase

    def test_starter_phrase_contains_retest_and_hold(self):
        phrase = _build_quality_phrase("CLEAN_STARTER", self._starter_signal())
        assert "retest" in phrase.lower()
        assert "hold" in phrase.lower()

    def test_watch_only_phrase_is_static(self):
        """WATCH_ONLY_VALID phrase is the unchanged static string."""
        phrase = _build_quality_phrase("WATCH_ONLY_VALID", _base_signal())
        assert phrase == _QUALITY_LABEL_PHRASES["WATCH_ONLY_VALID"]

    def test_structurally_valid_phrase_is_static(self):
        phrase = _build_quality_phrase("STRUCTURALLY_VALID_BUT_IMPERFECT", _base_signal())
        assert phrase == _QUALITY_LABEL_PHRASES["STRUCTURALLY_VALID_BUT_IMPERFECT"]

    def test_low_priority_phrase_is_static(self):
        phrase = _build_quality_phrase("LOW_PRIORITY_VALID", _base_signal())
        assert phrase == _QUALITY_LABEL_PHRASES["LOW_PRIORITY_VALID"]

    def test_unknown_label_falls_back_gracefully(self):
        phrase = _build_quality_phrase("NONEXISTENT_LABEL", _base_signal())
        assert isinstance(phrase, str)
        assert len(phrase) > 0


# ===========================================================================
# format_alert() integration — elite/candidate phrases in ACTION section
# ===========================================================================


class TestFormatAlertPhase13_8BIntegration:
    """Elite label and dynamic phrases appear correctly in formatted alerts."""

    def test_high_quality_phrase_in_snipe_it_alert(self):
        """All-premium signal produces the Phase 15C high-quality phrase."""
        result = format_alert(_tiering_result("SNIPE_IT"))  # rr=4.5 base → elite label
        assert "High-quality executable" in result
        assert "Elite candidate" not in result

    def test_starter_alert_renders_tactical_phrase_not_elite(self):
        # Phase 15C: STARTER may never carry the premium label.
        result = format_alert(_tiering_result("STARTER"))
        assert "High-quality STARTER" in result
        assert "Elite candidate" not in result
        assert "High-quality executable" not in result

    def test_candidate_phrase_when_one_dim_standard(self):
        """One standard dimension drops to the complete-sequence phrase."""
        result = format_alert(_tiering_result("SNIPE_IT", trend_state="mature_continuation"))
        assert "Complete sequence" in result
        assert "Elite candidate" not in result
        assert "A+ candidate" not in result

    def test_candidate_phrase_contains_dimension_count(self):
        result = format_alert(_tiering_result("SNIPE_IT", trend_state="mature_continuation"))
        # mature_continuation → standard → 4 premium — audit-safe X/5 form
        assert "premium dimensions: 4/5" in result

    def test_starter_phrase_when_one_discount(self):
        result = format_alert(
            _tiering_result("SNIPE_IT", risk_realism_state="fragile")
        )
        assert "Confirmed sequence" in result

    def test_starter_phrase_not_elite(self):
        result = format_alert(
            _tiering_result("SNIPE_IT", risk_realism_state="fragile")
        )
        assert "Elite candidate" not in result
        assert "A+ candidate" not in result

    def test_elite_phrase_in_action_section(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        action_pos = result.find("\nACTION\n")
        elite_pos  = result.find("High-quality executable")
        fresh_pos  = result.find("\nFRESHNESS\n")
        assert action_pos != -1
        assert elite_pos  != -1
        assert fresh_pos  != -1
        assert action_pos < elite_pos < fresh_pos

    def test_only_one_quality_read_line_with_elite(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert result.count("Quality read:") == 1

    def test_elite_phrase_not_duplicated(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert result.count("High-quality executable") == 1


# ===========================================================================
# No-side-effect guards — elite label must not change tier or capital
# ===========================================================================


class TestAPlusEliteNoSideEffects:
    """Elite label is informational only: tier, capital, channel unchanged."""

    def test_elite_does_not_change_snipe_tier(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert "🔴 SNIPE IT" in result

    def test_elite_does_not_change_starter_tier(self):
        result = format_alert(_tiering_result("STARTER"))
        assert "🟡 STARTER" in result

    def test_elite_does_not_change_capital_action_snipe(self):
        result = format_alert(_tiering_result("SNIPE_IT"))
        assert "Execution-valid" in result        # Phase 15C sizing language
        assert "SNIPE_IT conditions met." in result

    def test_elite_does_not_change_capital_action_starter(self):
        result = format_alert(_tiering_result("STARTER"))
        assert "STARTER SIZE ONLY" in result

    def test_candidate_does_not_change_capital_action(self):
        result = format_alert(
            _tiering_result("SNIPE_IT", trend_state="mature_continuation")
        )
        assert "Execution-valid" in result        # Phase 15C sizing language

    def test_elite_label_does_not_affect_tiering_result_dict(self):
        """The tiering_result dict is not mutated by quality evaluation."""
        tr = _tiering_result("SNIPE_IT")
        _ = format_alert(tr)
        assert tr["final_tier"] == "SNIPE_IT"
        assert tr["final_signal"]["capital_action"] == "full_quality_allowed"


# ===========================================================================
# Discrimination gap regression — Phase 13.8B core correctness check
# ===========================================================================


class TestDiscriminationGapFixed:
    """The two setups that were previously identical now produce different labels.

    Setup A: BOS + fresh_expansion + OB + clear + healthy + rr=4.5 → A_PLUS_ELITE
    Setup B: MSS + mature_continuation + support_cluster + moderate + tight + rr=3.1 → CLEAN_STARTER
    """

    def _setup_a(self) -> dict:
        return _base_signal(
            structure_event="BOS",
            setup_family="continuation",
            trend_state="fresh_expansion",
            zone_type="OB",
            overhead_status="clear",
            sma_value_alignment="supportive",
            risk_realism_state="healthy",
            risk_reward=4.5,
            retest_status="confirmed",
            hold_status="confirmed",
        )

    def _setup_b(self) -> dict:
        return _base_signal(
            structure_event="MSS",
            setup_family="continuation",
            trend_state="mature_continuation",
            zone_type="support_cluster",
            overhead_status="moderate",
            sma_value_alignment="mixed",
            risk_realism_state="tight",
            risk_reward=3.1,
            retest_status="confirmed",
            hold_status="confirmed",
            near_entry_blocker_note="",
        )

    def test_setup_a_is_elite(self):
        assert _evaluate_setup_quality(self._setup_a(), "SNIPE_IT") == "A_PLUS_ELITE"

    def test_setup_b_is_clean_starter(self):
        assert _evaluate_setup_quality(self._setup_b(), "SNIPE_IT") == "CLEAN_STARTER"

    def test_setup_a_and_b_are_different(self):
        label_a = _evaluate_setup_quality(self._setup_a(), "SNIPE_IT")
        label_b = _evaluate_setup_quality(self._setup_b(), "SNIPE_IT")
        assert label_a != label_b

    def test_setup_a_phrase_says_high_quality(self):
        # Phase 15C: premium phrase requires the explicit contract flag.
        sig = self._setup_a()
        sig["quality_label_allowed"] = True
        phrase = _build_quality_phrase("A_PLUS_ELITE", sig)
        assert "High-quality executable" in phrase
        assert "Elite" not in phrase

    def test_setup_b_phrase_says_confirmed_sequence(self):
        phrase = _build_quality_phrase("CLEAN_STARTER", self._setup_b())
        assert "Confirmed sequence" in phrase

    def test_format_alert_setup_a_shows_high_quality(self):
        tr = _tiering_result("SNIPE_IT")
        tr["final_signal"].update(self._setup_a())
        result = format_alert(tr)
        assert "High-quality executable" in result
        assert "Elite candidate" not in result

    def test_format_alert_setup_b_shows_confirmed_sequence(self):
        tr = _tiering_result("SNIPE_IT")
        tr["final_signal"].update(self._setup_b())
        result = format_alert(tr)
        assert "Confirmed sequence" in result
        assert "Elite candidate" not in result
        assert "High-quality executable" not in result

    def test_setup_b_dimensions_have_discounts(self):
        """Setup B has at least two discount dimensions."""
        n_prem, n_disc = _evaluate_quality_dimensions(self._setup_b())
        assert n_disc >= 2

    def test_setup_a_has_five_premium_zero_discount(self):
        n_prem, n_disc = _evaluate_quality_dimensions(self._setup_a())
        assert n_prem == 5
        assert n_disc == 0

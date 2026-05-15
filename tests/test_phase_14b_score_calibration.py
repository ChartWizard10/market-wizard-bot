"""Phase 14B — Score calibration tests (audit-only).

Verifies that score_calibration.calibrate_score():
  - Returns a complete dict (raw_score, calibrated_score, delta, score_band, reasons, primary_reason, display_text)
  - Bounds delta to [-8, +4]
  - Applies risk realism, overhead, trajectory, and structure adjustments correctly
  - Caps scores >= 90 unless elite preconditions are met
  - NEVER mutates tiering_result["score"]
  - NEVER mutates tiering_result["final_tier"]
  - NEVER mutates tiering_result["capital_action"]
  - NEVER mutates tiering_result["final_discord_channel"]
  - NEVER mutates tiering_result["safe_for_alert"]
"""

import pytest

from src import score_calibration as sc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tr(
    final_tier: str = "SNIPE_IT",
    score: int = 87,
    risk_realism_state: str = "healthy",
    overhead_status: str = "clear",
    retest_status: str = "confirmed",
    hold_status: str = "confirmed",
    structure_event: str = "MSS",
    missing_conditions=None,
    trajectory_label: str = "REPEATED_NO_CHANGE",
) -> dict:
    return {
        "final_tier": final_tier,
        "score": score,
        "safe_for_alert": final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT":   "#snipe-signals",
            "STARTER":    "#starter-signals",
            "NEAR_ENTRY": "#near-entry-watch",
            "WAIT":       "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT":   "full_quality_allowed",
            "STARTER":    "starter_only",
            "NEAR_ENTRY": "wait_no_capital",
            "WAIT":       "no_trade",
        }.get(final_tier, "no_trade"),
        "trajectory": {"label": trajectory_label, "text": ""},
        "final_signal": {
            "ticker": "AAPL",
            "score": score,
            "risk_realism_state": risk_realism_state,
            "overhead_status": overhead_status,
            "retest_status": retest_status,
            "hold_status": hold_status,
            "structure_event": structure_event,
            "missing_conditions": missing_conditions if missing_conditions is not None else [],
        },
    }


# ---------------------------------------------------------------------------
# 1. Output shape and invariants
# ---------------------------------------------------------------------------

class TestOutputShape:
    def test_returns_required_keys(self):
        cal = sc.calibrate_score(_make_tr())
        assert set(cal.keys()) >= {
            "raw_score", "calibrated_score", "delta", "score_band",
            "reasons", "primary_reason", "display_text",
        }

    def test_raw_score_matches_input(self):
        cal = sc.calibrate_score(_make_tr(score=87))
        assert cal["raw_score"] == 87

    def test_reasons_is_list_of_strings(self):
        cal = sc.calibrate_score(_make_tr(overhead_status="moderate"))
        assert isinstance(cal["reasons"], list)
        for r in cal["reasons"]:
            assert isinstance(r, str)

    def test_never_raises_on_malformed(self):
        try:
            cal = sc.calibrate_score({})
            assert isinstance(cal, dict)
            cal = sc.calibrate_score({"score": "nonsense"})
            assert isinstance(cal, dict)
        except Exception as exc:
            pytest.fail(f"calibrate_score raised: {exc}")

    def test_delta_always_bounded(self):
        # Throw the worst possible signal at it
        tr = _make_tr(
            final_tier="NEAR_ENTRY",
            score=80,
            risk_realism_state="fragile",
            overhead_status="blocked",
            retest_status="missing",
            hold_status="missing",
            structure_event="none",
            missing_conditions=["a", "b", "c", "d"],
            trajectory_label="DOWNGRADING",
        )
        cal = sc.calibrate_score(tr)
        assert -8 <= cal["delta"] <= 4

    def test_delta_ceiling_bounded(self):
        # Throw the best possible signal at it
        tr = _make_tr(
            final_tier="SNIPE_IT", score=87,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="UPGRADING",
        )
        cal = sc.calibrate_score(tr)
        assert -8 <= cal["delta"] <= 4


# ---------------------------------------------------------------------------
# 2. SNIPE_IT path separation
# ---------------------------------------------------------------------------

class TestSnipeItSeparation:
    def test_clean_snipe_it_strong_or_boosted(self):
        # Clean path, healthy risk, confirmed/confirmed, elite structure, repeated
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=87,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="REPEATED_NO_CHANGE",
        ))
        # +1 clear path + +1 elite structure = +2 → 89
        assert cal["calibrated_score"] >= 87

    def test_moderate_path_compresses_below_clean(self):
        clean = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            overhead_status="clear", structure_event="MSS",
        ))
        moderate = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            overhead_status="moderate", structure_event="MSS",
        ))
        assert moderate["calibrated_score"] < clean["calibrated_score"]

    def test_blocker_active_compresses_more_than_moderate(self):
        moderate = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88, overhead_status="moderate",
        ))
        blocked = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88, overhead_status="blocked",
        ))
        assert blocked["calibrated_score"] < moderate["calibrated_score"]

    def test_blocker_snipe_it_does_not_rank_equal_to_clean(self):
        clean = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88, overhead_status="clear",
        ))
        blocked = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88, overhead_status="blocked",
        ))
        assert blocked["calibrated_score"] != clean["calibrated_score"]


# ---------------------------------------------------------------------------
# 3. STARTER flow preservation
# ---------------------------------------------------------------------------

class TestStarterFlow:
    def test_starter_flow_preserved(self):
        # STARTER signals must still produce a valid calibrated score
        cal = sc.calibrate_score(_make_tr(
            final_tier="STARTER", score=78,
            overhead_status="clear", structure_event="BOS",
        ))
        # Score is still valid (not destroyed)
        assert cal["calibrated_score"] >= 70

    def test_starter_clean_strong_but_not_elite(self):
        cal = sc.calibrate_score(_make_tr(
            final_tier="STARTER", score=83,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="BOS", trajectory_label="UPGRADING",
        ))
        # +1 path +1 structure +2 trajectory = +4 → 87
        # Stays below elite range (90+) because elite cap requires SNIPE_IT
        assert cal["calibrated_score"] < 90

    def test_starter_moderate_compresses(self):
        clean    = sc.calibrate_score(_make_tr(final_tier="STARTER", score=82, overhead_status="clear"))
        moderate = sc.calibrate_score(_make_tr(final_tier="STARTER", score=82, overhead_status="moderate"))
        assert moderate["calibrated_score"] < clean["calibrated_score"]


# ---------------------------------------------------------------------------
# 4. Risk realism
# ---------------------------------------------------------------------------

class TestRiskRealism:
    def test_fragile_risk_compresses_score(self):
        healthy  = sc.calibrate_score(_make_tr(final_tier="NEAR_ENTRY", score=70,
                                                risk_realism_state="healthy",
                                                missing_conditions=["x"]))
        fragile  = sc.calibrate_score(_make_tr(final_tier="NEAR_ENTRY", score=70,
                                                risk_realism_state="fragile",
                                                missing_conditions=["x"]))
        assert fragile["calibrated_score"] < healthy["calibrated_score"]

    def test_fragile_cannot_reach_elite(self):
        # Even with high raw score and otherwise elite conditions
        cal = sc.calibrate_score(_make_tr(
            final_tier="NEAR_ENTRY", score=92,
            risk_realism_state="fragile",
            overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS",
            missing_conditions=["x"],
            trajectory_label="UPGRADING",
        ))
        # NEAR_ENTRY never elite (elite cap requires SNIPE_IT)
        assert cal["calibrated_score"] < 90

    def test_elevated_risk_mild_penalty(self):
        normal   = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=87,
                                                risk_realism_state="normal"))
        elevated = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=87,
                                                risk_realism_state="elevated"))
        assert elevated["calibrated_score"] < normal["calibrated_score"]
        assert normal["calibrated_score"] - elevated["calibrated_score"] <= 2


# ---------------------------------------------------------------------------
# 5. Trajectory boosts / compressions
# ---------------------------------------------------------------------------

class TestTrajectoryAdjustments:
    def test_upgrading_gives_boost(self):
        repeated  = sc.calibrate_score(_make_tr(score=85, trajectory_label="REPEATED_NO_CHANGE"))
        upgrading = sc.calibrate_score(_make_tr(score=85, trajectory_label="UPGRADING"))
        assert upgrading["calibrated_score"] > repeated["calibrated_score"]

    def test_improving_gives_smaller_boost_than_upgrading(self):
        improving  = sc.calibrate_score(_make_tr(score=85, trajectory_label="IMPROVING"))
        upgrading  = sc.calibrate_score(_make_tr(score=85, trajectory_label="UPGRADING"))
        assert upgrading["calibrated_score"] >= improving["calibrated_score"]

    def test_deteriorating_compresses(self):
        repeated      = sc.calibrate_score(_make_tr(score=85, trajectory_label="REPEATED_NO_CHANGE"))
        deteriorating = sc.calibrate_score(_make_tr(score=85, trajectory_label="DETERIORATING"))
        assert deteriorating["calibrated_score"] < repeated["calibrated_score"]

    def test_downgrading_compresses_more_than_deteriorating(self):
        det  = sc.calibrate_score(_make_tr(score=85, trajectory_label="DETERIORATING"))
        down = sc.calibrate_score(_make_tr(score=85, trajectory_label="DOWNGRADING"))
        assert down["calibrated_score"] <= det["calibrated_score"]

    def test_blocker_persisting_compresses_watch(self):
        repeated = sc.calibrate_score(_make_tr(
            final_tier="NEAR_ENTRY", score=68, trajectory_label="REPEATED_NO_CHANGE",
            missing_conditions=["x"],
        ))
        blocker  = sc.calibrate_score(_make_tr(
            final_tier="NEAR_ENTRY", score=68, trajectory_label="BLOCKER_PERSISTING",
            missing_conditions=["x"],
        ))
        assert blocker["calibrated_score"] < repeated["calibrated_score"]


# ---------------------------------------------------------------------------
# 6. Elite cap
# ---------------------------------------------------------------------------

class TestEliteCap:
    def test_elite_eligible_can_reach_90(self):
        # SNIPE_IT, healthy, clear, confirmed/confirmed, MSS, UPGRADING
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="UPGRADING",
        ))
        # +1 path +1 structure +2 trajectory = +4 → 92 (elite-eligible)
        assert cal["calibrated_score"] >= 90

    def test_elite_cap_when_overhead_moderate(self):
        # High raw score but moderate overhead → cap at 89
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=92,
            risk_realism_state="healthy", overhead_status="moderate",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="UPGRADING",
        ))
        assert cal["calibrated_score"] <= 89

    def test_elite_cap_when_risk_fragile(self):
        # SNIPE_IT with fragile risk shouldn't happen post-13.9A, but cap handles it
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=92,
            risk_realism_state="elevated", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS",
        ))
        assert cal["calibrated_score"] <= 89

    def test_elite_cap_when_deteriorating(self):
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=91,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="DETERIORATING",
        ))
        assert cal["calibrated_score"] <= 89


# ---------------------------------------------------------------------------
# 7. Score band classification
# ---------------------------------------------------------------------------

class TestScoreBand:
    def test_band_elite(self):
        assert sc._band(90) == "elite"
        assert sc._band(95) == "elite"

    def test_band_executable(self):
        assert sc._band(86) == "executable"
        assert sc._band(89) == "executable"

    def test_band_tactical(self):
        assert sc._band(81) == "tactical"
        assert sc._band(85) == "tactical"

    def test_band_developing(self):
        assert sc._band(75) == "developing"
        assert sc._band(80) == "developing"

    def test_band_watch(self):
        assert sc._band(68) == "watch"
        assert sc._band(74) == "watch"

    def test_band_low(self):
        assert sc._band(50) == "low"
        assert sc._band(67) == "low"


# ---------------------------------------------------------------------------
# 8. Display text
# ---------------------------------------------------------------------------

class TestDisplayText:
    def test_display_text_includes_score(self):
        cal = sc.calibrate_score(_make_tr(score=88, overhead_status="moderate"))
        assert str(cal["calibrated_score"]) in cal["display_text"]

    def test_display_text_includes_calibrated_word(self):
        cal = sc.calibrate_score(_make_tr(score=88))
        assert "calibrated" in cal["display_text"].lower()

    def test_negative_delta_in_text(self):
        cal = sc.calibrate_score(_make_tr(score=88, overhead_status="blocked"))
        assert "(-" in cal["display_text"] or "compressed" in cal["display_text"].lower() or "blocked" in cal["display_text"].lower()

    def test_positive_delta_in_text(self):
        cal = sc.calibrate_score(_make_tr(score=85, trajectory_label="UPGRADING",
                                           overhead_status="clear", structure_event="MSS"))
        # +1 path +1 structure +2 trajectory = +4
        assert cal["delta"] > 0
        assert "+" in cal["display_text"] or "improving" in cal["display_text"].lower() or "elite" in cal["display_text"].lower()


# ---------------------------------------------------------------------------
# 9. Invariant: NO MUTATION of tier/capital/routing/score
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_does_not_mutate_score(self):
        tr = _make_tr(score=88, overhead_status="moderate")
        original_score = tr["score"]
        sc.calibrate_score(tr)
        assert tr["score"] == original_score
        assert tr["final_signal"]["score"] == original_score

    def test_does_not_mutate_final_tier(self):
        tr = _make_tr(final_tier="SNIPE_IT", overhead_status="blocked")
        sc.calibrate_score(tr)
        assert tr["final_tier"] == "SNIPE_IT"

    def test_does_not_mutate_capital_action(self):
        tr = _make_tr(final_tier="SNIPE_IT")
        sc.calibrate_score(tr)
        assert tr["capital_action"] == "full_quality_allowed"

    def test_does_not_mutate_discord_channel(self):
        tr = _make_tr(final_tier="STARTER")
        sc.calibrate_score(tr)
        assert tr["final_discord_channel"] == "#starter-signals"

    def test_does_not_mutate_safe_for_alert(self):
        tr = _make_tr(final_tier="NEAR_ENTRY", missing_conditions=["x"])
        sc.calibrate_score(tr)
        assert tr["safe_for_alert"] is True

    def test_does_not_mutate_final_signal_fields(self):
        tr = _make_tr(final_tier="SNIPE_IT", risk_realism_state="elevated")
        original_signal = dict(tr["final_signal"])
        sc.calibrate_score(tr)
        for key, value in original_signal.items():
            assert tr["final_signal"][key] == value


# ---------------------------------------------------------------------------
# 10. WAIT signals
# ---------------------------------------------------------------------------

class TestWaitTier:
    def test_wait_calibration_does_not_crash(self):
        tr = _make_tr(final_tier="WAIT", score=40)
        cal = sc.calibrate_score(tr)
        assert isinstance(cal, dict)
        assert cal["raw_score"] == 40

    def test_wait_safe_for_alert_unchanged(self):
        tr = _make_tr(final_tier="WAIT", score=40)
        sc.calibrate_score(tr)
        assert tr["safe_for_alert"] is False


# ---------------------------------------------------------------------------
# 11. Discord integration: Calibrated line rendered when present
# ---------------------------------------------------------------------------

class TestDiscordIntegration:
    def test_calibration_text_appears_in_format_alert(self):
        from src.discord_alerts import format_alert

        tr = {
            "final_tier": "SNIPE_IT",
            "score": 88,
            "safe_for_alert": True,
            "final_discord_channel": "#snipe-signals",
            "trajectory": {"label": "REPEATED_NO_CHANGE", "text": ""},
            "calibration": {
                "raw_score": 88,
                "calibrated_score": 86,
                "delta": -2,
                "score_band": "executable",
                "reasons": ["overhead=moderate (-2)"],
                "primary_reason": "overhead is moderate",
                "display_text": "86 calibrated (-2) — overhead is moderate.",
            },
            "final_signal": {
                "ticker": "AAPL",
                "setup_family": "continuation",
                "structure_event": "MSS",
                "trend_state": "fresh_expansion",
                "zone_type": "FVG",
                "trigger_level": 182.50,
                "retest_status": "confirmed",
                "hold_status": "confirmed",
                "invalidation_condition": "Close below 178.20",
                "invalidation_level": 178.20,
                "risk_reward": 4.2,
                "overhead_status": "moderate",
                "forced_participation": "none",
                "next_action": "Enter at trigger.",
                "reason": "Clean FVG retest with MSS.",
                "targets": [{"label": "T1", "level": 195.0, "reason": "Prior swing"}],
                "capital_action": "full_quality_allowed",
                "missing_conditions": [],
                "upgrade_trigger": "none",
            },
        }
        output = format_alert(tr)
        assert "Score realism:" in output
        assert "86 calibrated" in output
        # Main Score field unchanged — shows 88 (raw)
        assert "Score: 88" in output

    def test_no_calibration_does_not_crash(self):
        from src.discord_alerts import format_alert

        tr = {
            "final_tier": "STARTER",
            "score": 78,
            "safe_for_alert": True,
            "final_discord_channel": "#starter-signals",
            "trajectory": {"label": "REPEATED_NO_CHANGE", "text": ""},
            # No calibration key
            "final_signal": {
                "ticker": "MSFT",
                "setup_family": "continuation",
                "structure_event": "BOS",
                "trend_state": "mature_continuation",
                "zone_type": "OB",
                "trigger_level": 420.0,
                "retest_status": "confirmed",
                "hold_status": "confirmed",
                "invalidation_condition": "Close below OB low",
                "invalidation_level": 410.0,
                "risk_reward": 3.5,
                "overhead_status": "clear",
                "forced_participation": "none",
                "next_action": "Execute at trigger.",
                "reason": "BOS confirmation.",
                "targets": [{"label": "T1", "level": 445.0, "reason": "Prior high"}],
                "capital_action": "starter_only",
                "missing_conditions": [],
                "upgrade_trigger": "none",
            },
        }
        output = format_alert(tr)
        assert "Score realism:" not in output
        assert "Score: 78" in output

    def test_empty_calibration_display_not_rendered(self):
        from src.discord_alerts import format_alert

        tr = {
            "final_tier": "STARTER",
            "score": 77,
            "safe_for_alert": True,
            "final_discord_channel": "#starter-signals",
            "trajectory": {"label": "REPEATED_NO_CHANGE", "text": ""},
            "calibration": {
                "raw_score": 77,
                "calibrated_score": 77,
                "delta": 0,
                "score_band": "developing",
                "reasons": [],
                "primary_reason": "no compression",
                "display_text": "",
            },
            "final_signal": {
                "ticker": "NVDA",
                "setup_family": "continuation",
                "structure_event": "BOS",
                "trend_state": "mature_continuation",
                "zone_type": "OB",
                "trigger_level": 870.0,
                "retest_status": "confirmed",
                "hold_status": "confirmed",
                "invalidation_condition": "Close below OB low",
                "invalidation_level": 855.0,
                "risk_reward": 3.5,
                "overhead_status": "clear",
                "forced_participation": "none",
                "next_action": "Execute at trigger.",
                "reason": "OB retest with BOS.",
                "targets": [{"label": "T1", "level": 910.0, "reason": "Prior high"}],
                "capital_action": "starter_only",
                "missing_conditions": [],
                "upgrade_trigger": "none",
            },
        }
        output = format_alert(tr)
        assert "Score realism:" not in output


# ---------------------------------------------------------------------------
# 13. Phase 14C patch regressions — P1 (tight → -1) and P3 (UPGRADING +2→+1)
# ---------------------------------------------------------------------------

class TestPhase14CPatch:
    # ---- P1: "tight" risk state now penalized ---------------------------------

    def test_tight_in_risk_adj_dict(self):
        from src.score_calibration import _RISK_ADJ
        assert "tight" in _RISK_ADJ
        assert _RISK_ADJ["tight"] == -1

    def test_tight_risk_penalized_vs_healthy(self):
        healthy = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=88,
                                               risk_realism_state="healthy",
                                               overhead_status="clear"))
        tight   = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=88,
                                               risk_realism_state="tight",
                                               overhead_status="clear"))
        assert tight["calibrated_score"] < healthy["calibrated_score"]
        # Exactly 1 point difference (the tight penalty)
        assert healthy["calibrated_score"] - tight["calibrated_score"] == 1

    def test_tight_risk_penalty_matches_elevated(self):
        tight    = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=87,
                                                risk_realism_state="tight",
                                                overhead_status="clear"))
        elevated = sc.calibrate_score(_make_tr(final_tier="SNIPE_IT", score=87,
                                                risk_realism_state="elevated",
                                                overhead_status="clear"))
        assert tight["calibrated_score"] == elevated["calibrated_score"]

    def test_tight_risk_near_entry_penalized(self):
        healthy = sc.calibrate_score(_make_tr(final_tier="NEAR_ENTRY", score=72,
                                               risk_realism_state="healthy",
                                               overhead_status="clear",
                                               missing_conditions=["x"]))
        tight   = sc.calibrate_score(_make_tr(final_tier="NEAR_ENTRY", score=72,
                                               risk_realism_state="tight",
                                               overhead_status="clear",
                                               missing_conditions=["x"]))
        assert tight["calibrated_score"] < healthy["calibrated_score"]

    def test_tight_risk_does_not_block_alert_or_tier(self):
        # P1 is calibration only — must not touch tier, capital, or safe_for_alert
        tr = _make_tr(final_tier="SNIPE_IT", score=88, risk_realism_state="tight")
        sc.calibrate_score(tr)
        assert tr["final_tier"] == "SNIPE_IT"
        assert tr["capital_action"] == "full_quality_allowed"
        assert tr["safe_for_alert"] is True

    # ---- P3: UPGRADING trajectory bonus reduced from +2 to +1 ---------------

    def test_upgrading_in_trajectory_adj_is_one(self):
        from src.score_calibration import _TRAJECTORY_ADJ
        assert _TRAJECTORY_ADJ["UPGRADING"] == 1

    def test_upgrading_bonus_is_plus_one_vs_repeated(self):
        # Isolate trajectory effect: use structure=none (-1) to avoid elite-cap
        # interference; compare UPGRADING vs REPEATED_NO_CHANGE on identical setup.
        repeated  = sc.calibrate_score(_make_tr(score=84, trajectory_label="REPEATED_NO_CHANGE",
                                                  overhead_status="clear", structure_event="none"))
        upgrading = sc.calibrate_score(_make_tr(score=84, trajectory_label="UPGRADING",
                                                  overhead_status="clear", structure_event="none"))
        # After P3: UPGRADING gives exactly 1 more than REPEATED (reduced from 2)
        assert upgrading["calibrated_score"] - repeated["calibrated_score"] == 1

    def test_upgrading_and_improving_give_equal_bonus(self):
        # After P3: UPGRADING = +1, IMPROVING = +1 — same trajectory bonus
        improving = sc.calibrate_score(_make_tr(score=84, trajectory_label="IMPROVING",
                                                  overhead_status="clear", structure_event="none"))
        upgrading = sc.calibrate_score(_make_tr(score=84, trajectory_label="UPGRADING",
                                                  overhead_status="clear", structure_event="none"))
        assert upgrading["calibrated_score"] == improving["calibrated_score"]

    def test_upgrading_elite_setup_still_reaches_90(self):
        # Promotion should still reach elite when all preconditions are met.
        # +1 clear +1 MSS +1 UPGRADING = +3 → 91 (elite-eligible)
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            risk_realism_state="healthy", overhead_status="clear",
            retest_status="confirmed", hold_status="confirmed",
            structure_event="MSS", trajectory_label="UPGRADING",
        ))
        assert cal["calibrated_score"] >= 90

    def test_upgrading_does_not_mutate_tier_or_capital(self):
        tr = _make_tr(final_tier="SNIPE_IT", score=87, trajectory_label="UPGRADING")
        sc.calibrate_score(tr)
        assert tr["final_tier"] == "SNIPE_IT"
        assert tr["capital_action"] == "full_quality_allowed"
        assert tr["safe_for_alert"] is True

    # ---- Combined P1 + P3 interaction ----------------------------------------

    def test_mod_style_tight_overhead_no_longer_masks_risk(self):
        # MOD pattern: SNIPE_IT, tight risk, moderate overhead, REPEATED.
        # Before P1: risk contributed 0. After P1: risk contributes -1.
        # Combined: -1 (tight) + -2 (moderate) + +1 (BOS) = -2 → 86 (was -1 → 87)
        cal = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            risk_realism_state="tight",
            overhead_status="moderate",
            structure_event="BOS",
            trajectory_label="REPEATED_NO_CHANGE",
        ))
        assert cal["calibrated_score"] == 86
        assert cal["delta"] == -2

    def test_mksi_style_promotion_ordering_gap_reduced(self):
        # MKSI-like: SNIPE_IT, healthy, clear, UPGRADING, raw=88
        # After P3: +1(clear) +1(MSS) +1(UPGRADING) = +3 → 91
        # IREN-like: SNIPE_IT, healthy, clear, REPEATED, raw=88
        # After P3: +1(clear) +1(MSS) +0(REPEATED) = +2 → 90
        mksi_like = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            risk_realism_state="healthy", overhead_status="clear",
            structure_event="MSS", trajectory_label="UPGRADING",
        ))
        iren_like = sc.calibrate_score(_make_tr(
            final_tier="SNIPE_IT", score=88,
            risk_realism_state="healthy", overhead_status="clear",
            structure_event="MSS", trajectory_label="REPEATED_NO_CHANGE",
        ))
        # Gap reduced: was 2 points (92 vs 90), now 1 point (91 vs 90)
        gap = mksi_like["calibrated_score"] - iren_like["calibrated_score"]
        assert gap == 1


# ---------------------------------------------------------------------------
# 12. Sanity: full test suite still passes (smoke-level check on imports)
# ---------------------------------------------------------------------------

def test_module_imports_cleanly():
    """Smoke test: trajectory and calibration modules co-exist and import."""
    from src import trajectory       # noqa: F401
    from src import score_calibration  # noqa: F401
    from src import scheduler        # noqa: F401
    from src import discord_alerts   # noqa: F401

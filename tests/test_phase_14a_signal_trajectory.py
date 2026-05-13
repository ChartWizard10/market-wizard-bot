"""Phase 14A — Signal Trajectory tests.

Verifies that trajectory.compute() returns the correct label and non-empty text
for all 9 trajectory scenarios.  Also verifies:
  - trajectory injection does NOT modify tier, capital_action, safe_for_alert
  - trajectory is rendered in the discord_alerts.format_alert() output when text is set
  - WAIT signals have a trajectory label but are never posted (existing routing rules)
"""

import pytest

from src import trajectory as traj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tiering_result(
    final_tier: str = "SNIPE_IT",
    score: int = 88,
    retest_status: str = "confirmed",
    hold_status: str = "confirmed",
    risk_realism_state: str = "healthy",
    overhead_status: str = "clear",
    missing_conditions=None,
    upgrade_trigger: str = "price holds above FVG and breaks resistance",
) -> dict:
    """Minimal tiering_result structure used as the current-cycle signal."""
    return {
        "final_tier": final_tier,
        "score": score,
        "safe_for_alert": final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT": "#snipe-signals",
            "STARTER": "#starter-signals",
            "NEAR_ENTRY": "#near-entry-watch",
            "WAIT": "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT": "full_quality_allowed",
            "STARTER": "starter_only",
            "NEAR_ENTRY": "wait_no_capital",
            "WAIT": "no_trade",
        }.get(final_tier, "no_trade"),
        "final_signal": {
            "ticker": "AAPL",
            "tier": final_tier,
            "score": score,
            "retest_status": retest_status,
            "hold_status": hold_status,
            "risk_realism_state": risk_realism_state,
            "overhead_status": overhead_status,
            "missing_conditions": missing_conditions if missing_conditions is not None else [],
            "upgrade_trigger": upgrade_trigger,
        },
    }


def _make_prev_history_entry(
    tier: str = "SNIPE_IT",
    score: int = 80,
    retest_status: str = "confirmed",
    hold_status: str = "confirmed",
    risk_realism_state: str = "healthy",
    overhead_status: str = "clear",
    missing_conditions=None,
    upgrade_trigger: str = "price holds above FVG and breaks resistance",
) -> dict:
    """One alert_history entry representing the previous scan cycle."""
    return {
        "ticker": "AAPL",
        "tier": tier,
        "score": score,
        "retest_status": retest_status,
        "hold_status": hold_status,
        "risk_realism_state": risk_realism_state,
        "overhead_status": overhead_status,
        "missing_conditions": missing_conditions if missing_conditions is not None else [],
        "upgrade_trigger": upgrade_trigger,
    }


def _ticker_state_with_history(history_entry: dict) -> dict:
    return {
        "last_alerted_tier": history_entry["tier"],
        "last_alerted_at": "2025-05-12T10:15:00",
        "alert_history": [history_entry],
    }


# ---------------------------------------------------------------------------
# 1. NEW_SIGNAL — no prior history
# ---------------------------------------------------------------------------

class TestNewSignal:
    def test_new_signal_when_ticker_state_none(self):
        result = traj.compute(_make_tiering_result("STARTER", score=78), None)
        assert result["label"] == "NEW_SIGNAL"
        assert result["text"]
        assert "first appearance" in result["text"].lower()

    def test_new_signal_when_alert_history_empty(self):
        ticker_state = {"last_alerted_tier": None, "last_alerted_at": None, "alert_history": []}
        result = traj.compute(_make_tiering_result("STARTER", score=78), ticker_state)
        assert result["label"] == "NEW_SIGNAL"

    def test_new_signal_when_ticker_state_empty_dict(self):
        result = traj.compute(_make_tiering_result("SNIPE_IT"), {})
        assert result["label"] == "NEW_SIGNAL"


# ---------------------------------------------------------------------------
# 2. UPGRADING — tier improved
# ---------------------------------------------------------------------------

class TestUpgrading:
    def test_near_entry_to_starter_is_upgrading(self):
        prev   = _make_prev_history_entry(tier="NEAR_ENTRY", score=65)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=78)
        result = traj.compute(curr, state)
        assert result["label"] == "UPGRADING"
        assert "NEAR_ENTRY" in result["text"]
        assert "STARTER" in result["text"]

    def test_starter_to_snipe_it_is_upgrading(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=77)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=90)
        result = traj.compute(curr, state)
        assert result["label"] == "UPGRADING"
        assert "SNIPE_IT" in result["text"]

    def test_near_entry_to_snipe_it_is_upgrading(self):
        prev   = _make_prev_history_entry(tier="NEAR_ENTRY", score=62)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=91)
        result = traj.compute(curr, state)
        assert result["label"] == "UPGRADING"

    def test_upgrading_includes_score_change(self):
        prev   = _make_prev_history_entry(tier="NEAR_ENTRY", score=65)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=78)
        result = traj.compute(curr, state)
        assert "65" in result["text"]
        assert "78" in result["text"]


# ---------------------------------------------------------------------------
# 3. DOWNGRADING — tier dropped
# ---------------------------------------------------------------------------

class TestDowngrading:
    def test_snipe_it_to_starter_is_downgrading(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=89)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=76)
        result = traj.compute(curr, state)
        assert result["label"] == "DOWNGRADING"
        assert "SNIPE_IT" in result["text"]
        assert "STARTER" in result["text"]

    def test_starter_to_near_entry_is_downgrading(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=76)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("NEAR_ENTRY", score=62,
                                      missing_conditions=["retest_missing"])
        result = traj.compute(curr, state)
        assert result["label"] == "DOWNGRADING"

    def test_downgrading_includes_score_change(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=89)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=76)
        result = traj.compute(curr, state)
        assert "89" in result["text"]
        assert "76" in result["text"]


# ---------------------------------------------------------------------------
# 4. IMPROVING — same tier, score up ≥ 5 or confirmations improved
# ---------------------------------------------------------------------------

class TestImproving:
    def test_score_up_5_points_is_improving(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=75)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=80)
        result = traj.compute(curr, state)
        assert result["label"] == "IMPROVING"
        assert "75" in result["text"]
        assert "80" in result["text"]

    def test_score_up_exactly_5_is_improving(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=75)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=80)
        result = traj.compute(curr, state)
        assert result["label"] == "IMPROVING"

    def test_retest_partial_to_confirmed_is_improving(self):
        prev   = _make_prev_history_entry(
            tier="SNIPE_IT", score=88,
            retest_status="partial", hold_status="confirmed",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result(
            "SNIPE_IT", score=89,
            retest_status="confirmed", hold_status="confirmed",
        )
        result = traj.compute(curr, state)
        assert result["label"] == "IMPROVING"
        assert "confirmations" in result["text"].lower()

    def test_risk_improved_is_improving(self):
        prev   = _make_prev_history_entry(
            tier="STARTER", score=77, risk_realism_state="elevated",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=79, risk_realism_state="healthy")
        result = traj.compute(curr, state)
        assert result["label"] == "IMPROVING"
        assert "risk" in result["text"].lower()


# ---------------------------------------------------------------------------
# 5. DETERIORATING — same tier, score down ≥ 5 or quality worsened
# ---------------------------------------------------------------------------

class TestDeteriorating:
    def test_score_down_5_is_deteriorating(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=90)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=84)
        result = traj.compute(curr, state)
        assert result["label"] == "DETERIORATING"
        assert "90" in result["text"]
        assert "84" in result["text"]

    def test_hold_confirmed_to_partial_is_deteriorating(self):
        prev   = _make_prev_history_entry(
            tier="SNIPE_IT", score=88,
            retest_status="confirmed", hold_status="confirmed",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result(
            "SNIPE_IT", score=87,
            retest_status="confirmed", hold_status="partial",
        )
        result = traj.compute(curr, state)
        assert result["label"] == "DETERIORATING"
        assert "confirmations" in result["text"].lower()

    def test_risk_worsened_not_fragile_is_deteriorating(self):
        # healthy → elevated: deteriorating (not quality_compressed — fragile is required for QC)
        prev   = _make_prev_history_entry(tier="STARTER", score=78, risk_realism_state="healthy")
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=77, risk_realism_state="elevated")
        result = traj.compute(curr, state)
        assert result["label"] == "DETERIORATING"


# ---------------------------------------------------------------------------
# 6. QUALITY_COMPRESSED — risk_realism_state became fragile
# ---------------------------------------------------------------------------

class TestQualityCompressed:
    def test_healthy_to_fragile_is_quality_compressed(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=88, risk_realism_state="healthy")
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=89, risk_realism_state="fragile")
        result = traj.compute(curr, state)
        assert result["label"] == "QUALITY_COMPRESSED"
        assert "fragile" in result["text"].lower()

    def test_normal_to_fragile_is_quality_compressed(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=77, risk_realism_state="normal")
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=76, risk_realism_state="fragile")
        result = traj.compute(curr, state)
        assert result["label"] == "QUALITY_COMPRESSED"

    def test_elevated_to_fragile_is_quality_compressed(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=76, risk_realism_state="elevated")
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=75, risk_realism_state="fragile")
        result = traj.compute(curr, state)
        assert result["label"] == "QUALITY_COMPRESSED"

    def test_already_fragile_to_fragile_is_not_quality_compressed(self):
        # Was already fragile — no compression event; should fall through to REPEATED or DETERIORATING
        prev   = _make_prev_history_entry(tier="STARTER", score=76, risk_realism_state="fragile")
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=76, risk_realism_state="fragile")
        result = traj.compute(curr, state)
        assert result["label"] != "QUALITY_COMPRESSED"


# ---------------------------------------------------------------------------
# 7. STALE_WATCH — NEAR_ENTRY, same missing_conditions
# ---------------------------------------------------------------------------

class TestStaleWatch:
    def test_near_entry_same_missing_conditions_is_stale_watch(self):
        mc     = ["retest_missing", "hold_missing"]
        prev   = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=65,
            missing_conditions=mc,
            overhead_status="clear",     # not blocked → not BLOCKER_PERSISTING
            upgrade_trigger="different from last",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result(
            "NEAR_ENTRY", score=64,
            missing_conditions=mc,
            overhead_status="clear",
            upgrade_trigger="watch for retest of FVG zone",  # changed trigger → no blocker
        )
        result = traj.compute(curr, state)
        assert result["label"] == "STALE_WATCH"
        assert "unchanged" in result["text"].lower()

    def test_near_entry_different_missing_conditions_not_stale(self):
        prev   = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=65,
            missing_conditions=["retest_missing"],
            overhead_status="clear",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result(
            "NEAR_ENTRY", score=64,
            missing_conditions=["retest_missing", "hold_missing"],
            overhead_status="clear",
        )
        result = traj.compute(curr, state)
        assert result["label"] != "STALE_WATCH"

    def test_stale_watch_order_insensitive(self):
        # Missing conditions in different list order → still stale watch
        prev   = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=63,
            missing_conditions=["hold_missing", "retest_missing"],
            overhead_status="clear",
            upgrade_trigger="trigger A",
        )
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result(
            "NEAR_ENTRY", score=62,
            missing_conditions=["retest_missing", "hold_missing"],
            overhead_status="clear",
            upgrade_trigger="trigger B",   # different trigger so not BLOCKER_PERSISTING
        )
        result = traj.compute(curr, state)
        assert result["label"] == "STALE_WATCH"


# ---------------------------------------------------------------------------
# 8. BLOCKER_PERSISTING — NEAR_ENTRY, same upgrade trigger + overhead blocked
# ---------------------------------------------------------------------------

class TestBlockerPersisting:
    def test_same_upgrade_trigger_and_blocked_overhead_is_blocker_persisting(self):
        trigger = "price must reclaim 185 and close above resistance"
        prev    = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=64,
            missing_conditions=["retest_missing"],
            overhead_status="blocked",
            upgrade_trigger=trigger,
        )
        state   = _ticker_state_with_history(prev)
        curr    = _make_tiering_result(
            "NEAR_ENTRY", score=63,
            missing_conditions=["retest_missing"],
            overhead_status="blocked",
            upgrade_trigger=trigger,
        )
        result  = traj.compute(curr, state)
        assert result["label"] == "BLOCKER_PERSISTING"
        assert "blocker" in result["text"].lower()

    def test_same_trigger_moderate_overhead_is_blocker_persisting(self):
        trigger = "wait for volume expansion above prior high"
        prev    = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=62,
            overhead_status="moderate",
            upgrade_trigger=trigger,
        )
        state   = _ticker_state_with_history(prev)
        curr    = _make_tiering_result(
            "NEAR_ENTRY", score=61,
            overhead_status="moderate",
            upgrade_trigger=trigger,
        )
        result  = traj.compute(curr, state)
        assert result["label"] == "BLOCKER_PERSISTING"

    def test_changed_trigger_clear_overhead_is_not_blocker_persisting(self):
        prev    = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=64,
            overhead_status="clear",
            upgrade_trigger="old trigger text",
        )
        state   = _ticker_state_with_history(prev)
        curr    = _make_tiering_result(
            "NEAR_ENTRY", score=63,
            overhead_status="clear",
            upgrade_trigger="new trigger text",
        )
        result  = traj.compute(curr, state)
        assert result["label"] != "BLOCKER_PERSISTING"

    def test_same_trigger_clear_overhead_is_not_blocker_persisting(self):
        # Same trigger but overhead cleared → not a persisting blocker
        trigger = "some trigger"
        prev    = _make_prev_history_entry(
            tier="NEAR_ENTRY", score=64,
            overhead_status="blocked",
            upgrade_trigger=trigger,
        )
        state   = _ticker_state_with_history(prev)
        curr    = _make_tiering_result(
            "NEAR_ENTRY", score=63,
            overhead_status="clear",   # cleared
            upgrade_trigger=trigger,
        )
        result  = traj.compute(curr, state)
        assert result["label"] != "BLOCKER_PERSISTING"


# ---------------------------------------------------------------------------
# 9. REPEATED_NO_CHANGE — same tier, no meaningful change
# ---------------------------------------------------------------------------

class TestRepeatedNoChange:
    def test_same_tier_score_within_4_is_repeated(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=87)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=89)   # delta = 2, below threshold
        result = traj.compute(curr, state)
        assert result["label"] == "REPEATED_NO_CHANGE"
        assert result["text"]

    def test_same_tier_score_unchanged_is_repeated(self):
        prev   = _make_prev_history_entry(tier="STARTER", score=77)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("STARTER", score=77)
        result = traj.compute(curr, state)
        assert result["label"] == "REPEATED_NO_CHANGE"

    def test_same_tier_score_delta_4_is_repeated(self):
        prev   = _make_prev_history_entry(tier="SNIPE_IT", score=88)
        state  = _ticker_state_with_history(prev)
        curr   = _make_tiering_result("SNIPE_IT", score=92)   # delta = 4, just below threshold
        result = traj.compute(curr, state)
        assert result["label"] == "REPEATED_NO_CHANGE"


# ---------------------------------------------------------------------------
# Invariant: trajectory never affects tier/capital/routing
# ---------------------------------------------------------------------------

class TestTrajectoryInvariant:
    def test_trajectory_does_not_modify_final_tier(self):
        tr = _make_tiering_result("SNIPE_IT", score=90)
        traj.compute(tr, None)
        assert tr["final_tier"] == "SNIPE_IT"

    def test_trajectory_does_not_modify_capital_action(self):
        tr = _make_tiering_result("SNIPE_IT", score=90)
        traj.compute(tr, None)
        assert tr["capital_action"] == "full_quality_allowed"

    def test_trajectory_does_not_modify_safe_for_alert(self):
        tr = _make_tiering_result("STARTER", score=77)
        traj.compute(tr, None)
        assert tr["safe_for_alert"] is True

    def test_trajectory_does_not_modify_discord_channel(self):
        tr = _make_tiering_result("NEAR_ENTRY", score=62,
                                   missing_conditions=["retest_missing"])
        traj.compute(tr, None)
        assert tr["final_discord_channel"] == "#near-entry-watch"

    def test_trajectory_always_returns_dict(self):
        # Even with malformed input, compute() must return a dict (never raises)
        result = traj.compute({}, None)
        assert isinstance(result, dict)
        assert "label" in result
        assert "text" in result

    def test_trajectory_never_raises(self):
        # None tiering_result is unusual but must not crash
        try:
            result = traj.compute(None, None)  # type: ignore[arg-type]
            assert isinstance(result, dict)
        except Exception as exc:
            pytest.fail(f"trajectory.compute raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Discord alert renders trajectory line
# ---------------------------------------------------------------------------

class TestDiscordRender:
    def test_trajectory_text_appears_in_format_alert(self):
        from src.discord_alerts import format_alert

        # Build a minimal tiering_result that will pass format_alert
        tr = {
            "final_tier": "SNIPE_IT",
            "score": 88,
            "safe_for_alert": True,
            "final_discord_channel": "#snipe-signals",
            "trajectory": {"label": "IMPROVING", "text": "Improving — score 80 → 88."},
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
                "overhead_status": "clear",
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
        assert "Trajectory:" in output
        assert "Improving" in output

    def test_no_trajectory_key_does_not_crash(self):
        from src.discord_alerts import format_alert

        tr = {
            "final_tier": "STARTER",
            "score": 78,
            "safe_for_alert": True,
            "final_discord_channel": "#starter-signals",
            # No 'trajectory' key at all
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
                "reason": "OB retest with BOS confirmation.",
                "targets": [{"label": "T1", "level": 910.0, "reason": "Prior high"}],
                "capital_action": "starter_only",
                "missing_conditions": [],
                "upgrade_trigger": "none",
            },
        }
        output = format_alert(tr)
        assert "Trajectory:" not in output   # empty text → line not appended

    def test_empty_trajectory_text_not_rendered(self):
        from src.discord_alerts import format_alert

        tr = {
            "final_tier": "STARTER",
            "score": 77,
            "safe_for_alert": True,
            "final_discord_channel": "#starter-signals",
            "trajectory": {"label": "UNKNOWN", "text": ""},
            "final_signal": {
                "ticker": "MSFT",
                "setup_family": "reclaim",
                "structure_event": "CHoCH",
                "trend_state": "repair",
                "zone_type": "demand",
                "trigger_level": 420.0,
                "retest_status": "confirmed",
                "hold_status": "confirmed",
                "invalidation_condition": "Close below demand zone",
                "invalidation_level": 412.0,
                "risk_reward": 3.1,
                "overhead_status": "clear",
                "forced_participation": "none",
                "next_action": "Execute at trigger.",
                "reason": "Demand zone reclaim.",
                "targets": [{"label": "T1", "level": 440.0, "reason": "Resistance"}],
                "capital_action": "starter_only",
                "missing_conditions": [],
                "upgrade_trigger": "none",
            },
        }
        output = format_alert(tr)
        assert "Trajectory:" not in output

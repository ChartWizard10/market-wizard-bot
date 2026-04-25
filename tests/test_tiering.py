"""Tiering validation tests — Phase 5."""

import pathlib

import pytest

from src.tiering import validate, CHANNEL_MAP, CAPITAL_MAP, TIERS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "tiers": {
        "snipe_it":   {"min_score": 85, "min_rr": 3.0},
        "starter":    {"min_score": 75, "min_rr": 3.0},
        "near_entry": {"min_score": 60},
        "wait":       {"posts_to_discord": False},
    }
}


def _snipe_signal(**overrides) -> dict:
    """Build a Claude signal that passes all SNIPE_IT gates."""
    base = {
        "ticker": "AAPL",
        "timestamp_et": "2025-01-15T10:30:00-05:00",
        "tier": "SNIPE_IT",
        "score": 90,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 182.50,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Daily close below FVG base at 178.20",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "Full quality — zone held cleanly",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at zone retest confirmation",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with confirmed FVG retest and hold.",
    }
    base.update(overrides)
    return base


def _starter_signal(**overrides) -> dict:
    """Build a Claude signal that passes STARTER gates but not SNIPE_IT score floor."""
    base = _snipe_signal(
        tier="STARTER",
        score=78,
        discord_channel="#starter-signals",
        capital_action="starter_only",
        reason="Partial zone interaction — reduced size warranted.",
    )
    base.update(overrides)
    return base


def _near_entry_signal(**overrides) -> dict:
    """Build a Claude signal that passes NEAR_ENTRY gates."""
    base = _snipe_signal(
        tier="NEAR_ENTRY",
        score=65,
        retest_status="missing",
        hold_status="missing",
        invalidation_level=None,
        risk_reward=None,
        discord_channel="#near-entry-watch",
        capital_action="wait_no_capital",
        missing_conditions=["retest_status", "hold_status"],
        upgrade_trigger="Confirmed retest of FVG base at 179.00 with hold.",
        reason="MSS confirmed, zone present, awaiting retest.",
    )
    base.update(overrides)
    return base


def _wait_signal(**overrides) -> dict:
    base = _snipe_signal(
        tier="WAIT",
        score=40,
        structure_event="none",
        retest_status="missing",
        hold_status="missing",
        discord_channel="none",
        capital_action="no_trade",
        missing_conditions=[],
        upgrade_trigger="none",
        reason="No clear structure or zone.",
    )
    base.update(overrides)
    return base


def _pf(vetoes: list | None = None) -> dict:
    """Build a minimal prefilter result dict."""
    return {"veto_flags": vetoes or []}


# ---------------------------------------------------------------------------
# 1. SNIPE_IT valid case passes and routes to #snipe-signals
# ---------------------------------------------------------------------------

def test_snipe_it_valid_passes():
    result = validate(_snipe_signal(), _pf(), _BASE_CONFIG)
    assert result["ok"] is True
    assert result["final_tier"] == "SNIPE_IT"
    assert result["final_discord_channel"] == "#snipe-signals"
    assert result["safe_for_alert"] is True
    assert result["capital_action"] == "full_quality_allowed"
    assert not result["downgrades"]


# ---------------------------------------------------------------------------
# 2. STARTER valid case passes and routes to #starter-signals
# ---------------------------------------------------------------------------

def test_starter_valid_passes():
    result = validate(_starter_signal(), _pf(), _BASE_CONFIG)
    assert result["ok"] is True
    assert result["final_tier"] == "STARTER"
    assert result["final_discord_channel"] == "#starter-signals"
    assert result["safe_for_alert"] is True
    assert result["capital_action"] == "starter_only"


# ---------------------------------------------------------------------------
# 3. NEAR_ENTRY valid case passes and routes to #near-entry-watch
# ---------------------------------------------------------------------------

def test_near_entry_valid_passes():
    result = validate(_near_entry_signal(), _pf(), _BASE_CONFIG)
    assert result["ok"] is True
    assert result["final_tier"] == "NEAR_ENTRY"
    assert result["final_discord_channel"] == "#near-entry-watch"
    assert result["safe_for_alert"] is True
    assert result["capital_action"] == "wait_no_capital"


# ---------------------------------------------------------------------------
# 4. WAIT routes to none and safe_for_alert false
# ---------------------------------------------------------------------------

def test_wait_routes_to_none():
    result = validate(_wait_signal(), _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["final_discord_channel"] == "none"
    assert result["safe_for_alert"] is False
    assert result["capital_action"] == "no_trade"


# ---------------------------------------------------------------------------
# 5. Claude discord_channel mismatch corrected deterministically
# ---------------------------------------------------------------------------

def test_discord_channel_mismatch_corrected():
    # Claude says SNIPE_IT but puts wrong channel
    signal = _snipe_signal(discord_channel="#near-entry-watch")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "SNIPE_IT"
    assert result["final_discord_channel"] == "#snipe-signals"
    assert result["final_signal"]["discord_channel"] == "#snipe-signals"


# ---------------------------------------------------------------------------
# 6. Claude capital_action mismatch corrected deterministically
# ---------------------------------------------------------------------------

def test_capital_action_mismatch_corrected():
    signal = _snipe_signal(capital_action="wait_no_capital")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "SNIPE_IT"
    assert result["capital_action"] == "full_quality_allowed"
    assert result["final_signal"]["capital_action"] == "full_quality_allowed"


# ---------------------------------------------------------------------------
# 7. SNIPE_IT downgraded if retest missing
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_retest_missing():
    signal = _snipe_signal(
        retest_status="missing",
        hold_status="missing",
        missing_conditions=["retest_status", "hold_status"],
        upgrade_trigger="Retest of FVG at 179 with hold",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"
    assert result["downgrades"]


# ---------------------------------------------------------------------------
# 8. SNIPE_IT downgraded if hold missing
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_hold_missing():
    signal = _snipe_signal(
        hold_status="missing",
        missing_conditions=["hold_status"],
        upgrade_trigger="Close above OB top at 183.00 confirming hold",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 9. SNIPE_IT downgraded if invalidation_condition empty
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_invalidation_condition_empty():
    signal = _snipe_signal(
        invalidation_condition="",
        missing_conditions=["invalidation_condition"],
        upgrade_trigger="Define clear invalidation level",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 10. SNIPE_IT downgraded if invalidation_level null
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_invalidation_level_null():
    signal = _snipe_signal(
        invalidation_level=None,
        missing_conditions=["invalidation_level"],
        upgrade_trigger="Identify specific invalidation price",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 11. SNIPE_IT downgraded if targets empty
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_targets_empty():
    signal = _snipe_signal(
        targets=[],
        missing_conditions=["targets"],
        upgrade_trigger="Define T1 and T2 targets",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 12. SNIPE_IT downgraded if risk_reward below 3.0
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_rr_below_threshold():
    signal = _snipe_signal(
        risk_reward=2.1,
        missing_conditions=["risk_reward below 3.0"],
        upgrade_trigger="Target at 196.00 to achieve R:R >= 3.0",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 13. SNIPE_IT downgraded if overhead blocked
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_overhead_blocked():
    signal = _snipe_signal(
        overhead_status="blocked",
        missing_conditions=["overhead_status"],
        upgrade_trigger="Break and close above resistance at 185.00",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 14. SNIPE_IT downgraded if structure_event none — forces WAIT (not just not-SNIPE)
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_structure_event_none():
    # structure_event=none in signal → all tiers blocked → WAIT
    signal = _snipe_signal(
        structure_event="none",
        missing_conditions=["structure_event"],
        upgrade_trigger="BOS above 184.00 swing high",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "structure_event=none must force WAIT, not just downgrade from SNIPE_IT"
    )
    assert result["original_claude_tier"] == "SNIPE_IT"
    assert result["safe_for_alert"] is False


# ---------------------------------------------------------------------------
# 15. SNIPE_IT downgraded if sma_value_alignment hostile
# ---------------------------------------------------------------------------

def test_snipe_it_downgraded_hostile_alignment():
    # hostile alignment → entry gate fails for SNIPE_IT and STARTER
    # NEAR_ENTRY doesn't check alignment → lands NEAR_ENTRY if near_gates pass
    signal = _snipe_signal(
        sma_value_alignment="hostile",
        missing_conditions=["sma_value_alignment"],
        upgrade_trigger="Price reclaim above SMA50 at 175.00",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")
    assert result["original_claude_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 14b. no_clear_structure veto blocks NEAR_ENTRY (all-alert-blocking)
# ---------------------------------------------------------------------------

def test_no_clear_structure_veto_blocks_near_entry():
    # NEAR_ENTRY signal with valid gates — but prefilter has no_clear_structure
    signal = _near_entry_signal()
    result = validate(signal, _pf(["no_clear_structure"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert "no_clear_structure" in result["applied_vetoes"]


def test_no_clear_structure_veto_blocks_snipe_and_starter():
    for base_tier, signal_fn in (("SNIPE_IT", _snipe_signal), ("STARTER", _starter_signal)):
        result = validate(signal_fn(), _pf(["no_clear_structure"]), _BASE_CONFIG)
        assert result["final_tier"] == "WAIT", f"{base_tier} should be WAIT with no_clear_structure veto"
        assert result["safe_for_alert"] is False


def test_structure_event_none_in_signal_blocks_near_entry():
    # Even without a prefilter veto, Claude signal with structure_event=none → WAIT
    signal = _near_entry_signal(structure_event="none")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False


def test_no_clear_structure_high_score_cannot_override():
    signal = _snipe_signal(score=99)
    result = validate(signal, _pf(["no_clear_structure"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["score"] == 99         # score preserved, tier still WAIT
    assert result["safe_for_alert"] is False


def test_claude_tier_cannot_override_no_clear_structure_veto():
    # Claude says NEAR_ENTRY (lowest trade tier) — still blocked by no_clear_structure
    signal = _near_entry_signal()
    result = validate(signal, _pf(["no_clear_structure"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "NEAR_ENTRY"
    assert result["downgrades"]


def test_claude_tier_cannot_override_no_clear_structure_in_signal():
    # Claude says NEAR_ENTRY but structure_event=none → WAIT (signal-level check)
    signal = _near_entry_signal(structure_event="none")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "NEAR_ENTRY"
    assert result["safe_for_alert"] is False


# ---------------------------------------------------------------------------
# 16. STARTER cannot survive missing retest
# ---------------------------------------------------------------------------

def test_starter_cannot_survive_missing_retest():
    signal = _starter_signal(
        retest_status="missing",
        missing_conditions=["retest_status"],
        upgrade_trigger="Retest of OB base at 180.00",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")
    assert result["original_claude_tier"] == "STARTER"
    assert result["downgrades"]


# ---------------------------------------------------------------------------
# 17. STARTER cannot survive missing hold
# ---------------------------------------------------------------------------

def test_starter_cannot_survive_missing_hold():
    signal = _starter_signal(
        hold_status="missing",
        missing_conditions=["hold_status"],
        upgrade_trigger="Hold above OB core on next bar",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")
    assert result["original_claude_tier"] == "STARTER"


# ---------------------------------------------------------------------------
# 18. STARTER cannot be assigned to a forming/no-trigger setup
# ---------------------------------------------------------------------------

def test_starter_not_assigned_to_forming_setup():
    # Forming: no retest, no hold, setup hasn't triggered yet
    signal = _starter_signal(
        retest_status="missing",
        hold_status="missing",
        # No valid NEAR_ENTRY conditions either — forces WAIT
        missing_conditions=[],
        upgrade_trigger="none",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "STARTER"


# ---------------------------------------------------------------------------
# 19. NEAR_ENTRY requires missing_conditions
# ---------------------------------------------------------------------------

def test_near_entry_requires_missing_conditions():
    signal = _near_entry_signal(missing_conditions=[])
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "NEAR_ENTRY"
    assert result["downgrades"]


def test_near_entry_requires_missing_conditions_not_string():
    signal = _near_entry_signal(missing_conditions="retest_status")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"


# ---------------------------------------------------------------------------
# 20. NEAR_ENTRY requires upgrade_trigger
# ---------------------------------------------------------------------------

def test_near_entry_requires_upgrade_trigger():
    signal = _near_entry_signal(upgrade_trigger="")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "NEAR_ENTRY"


def test_near_entry_upgrade_trigger_none_string_rejected():
    signal = _near_entry_signal(upgrade_trigger="none")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"


# ---------------------------------------------------------------------------
# 21. NEAR_ENTRY allows no capital only
# ---------------------------------------------------------------------------

def test_near_entry_capital_is_wait_no_capital():
    result = validate(_near_entry_signal(), _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    assert result["capital_action"] == "wait_no_capital"
    assert result["final_signal"]["capital_action"] == "wait_no_capital"
    assert result["safe_for_alert"] is True       # can post to #near-entry-watch
    assert result["final_discord_channel"] == "#near-entry-watch"


# ---------------------------------------------------------------------------
# 22. WAIT never posts to Discord
# ---------------------------------------------------------------------------

def test_wait_never_posts_to_discord():
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"):
        signal = _snipe_signal(
            tier=tier,
            structure_event="none",
            retest_status="missing",
            hold_status="missing",
            invalidation_level=None,
            discord_channel="none",
            capital_action="no_trade",
            missing_conditions=[],
            upgrade_trigger="none",
            score=30,
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        if result["final_tier"] == "WAIT":
            assert result["final_discord_channel"] == "none"
            assert result["safe_for_alert"] is False


def test_wait_signal_safe_for_alert_false():
    result = validate(_wait_signal(), _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert result["final_discord_channel"] == "none"


# ---------------------------------------------------------------------------
# 23. Hard veto data_empty blocks all alert tiers
# ---------------------------------------------------------------------------

def test_hard_veto_data_empty_blocks_alert():
    # Even a SNIPE_IT signal with data_empty veto must be WAIT
    signal = _snipe_signal()
    result = validate(signal, _pf(["data_empty"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert "data_empty" in result["applied_vetoes"]
    assert result["downgrades"]


# ---------------------------------------------------------------------------
# 24. Hard veto stale_data blocks all alert tiers
# ---------------------------------------------------------------------------

def test_hard_veto_stale_data_blocks_alert():
    signal = _snipe_signal()
    result = validate(signal, _pf(["stale_data"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert "stale_data" in result["applied_vetoes"]


# ---------------------------------------------------------------------------
# 25. Hard veto overhead_blocked blocks SNIPE_IT and STARTER
# ---------------------------------------------------------------------------

def test_hard_veto_overhead_blocked_blocks_entry_tiers():
    # overhead_blocked in prefilter vetoes blocks SNIPE_IT and STARTER
    # NEAR_ENTRY is not blocked by it — signal lands at NEAR_ENTRY if gates pass
    signal = _snipe_signal(
        missing_conditions=["overhead_status"],
        upgrade_trigger="Break above resistance at 186.00",
    )
    result = validate(signal, _pf(["overhead_blocked"]), _BASE_CONFIG)
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")
    assert "overhead_blocked" in result["applied_vetoes"]


# ---------------------------------------------------------------------------
# 26. Hard veto rr_below_threshold_estimate blocks SNIPE_IT and STARTER
# ---------------------------------------------------------------------------

def test_hard_veto_rr_below_threshold_blocks_entry_tiers():
    signal = _snipe_signal(
        missing_conditions=["rr_below_threshold"],
        upgrade_trigger="Target extends to 197.00 for R:R >= 3.0",
    )
    result = validate(signal, _pf(["rr_below_threshold_estimate"]), _BASE_CONFIG)
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")
    assert "rr_below_threshold_estimate" in result["applied_vetoes"]


# ---------------------------------------------------------------------------
# 27. High score cannot override hard veto
# ---------------------------------------------------------------------------

def test_high_score_cannot_override_hard_veto():
    # Score of 99, all conditions met — but stale_data blocks everything
    signal = _snipe_signal(score=99)
    result = validate(signal, _pf(["stale_data"]), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert result["score"] == 99                  # score is preserved, but tier is WAIT


# ---------------------------------------------------------------------------
# 28. tiering.py does not upgrade Claude tier upward
# ---------------------------------------------------------------------------

def test_tiering_does_not_upgrade_claude_tier():
    # Claude says NEAR_ENTRY but all SNIPE_IT conditions are met
    # tiering.py must NOT upgrade to SNIPE_IT or STARTER
    signal = _near_entry_signal(
        score=95,
        retest_status="confirmed",
        hold_status="confirmed",
        invalidation_level=178.20,
        risk_reward=3.8,
        overhead_status="clear",
        structure_event="MSS",
        sma_value_alignment="supportive",
        # NEAR_ENTRY gates must still pass
        missing_conditions=["one minor condition"],
        upgrade_trigger="Very specific trigger event at 183.00",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    assert result["original_claude_tier"] == "NEAR_ENTRY"
    assert not result["downgrades"]


def test_tiering_does_not_upgrade_wait():
    signal = _wait_signal()
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["original_claude_tier"] == "WAIT"
    assert not result["downgrades"]


# ---------------------------------------------------------------------------
# 29. Malformed / partial analysis rejected or WAIT safely
# ---------------------------------------------------------------------------

def test_none_signal_rejected_safely():
    result = validate(None, _pf(), _BASE_CONFIG)
    assert result["ok"] is False
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert result["final_signal"] is None


def test_empty_dict_signal_becomes_wait():
    result = validate({}, _pf(), _BASE_CONFIG)
    assert result["ok"] is True
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False


def test_signal_with_unknown_tier_becomes_wait():
    signal = _snipe_signal(tier="ABSOLUTE_BANGER")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False


# ---------------------------------------------------------------------------
# 30. Result contains applied_vetoes and downgrades
# ---------------------------------------------------------------------------

def test_result_contains_applied_vetoes_and_downgrades():
    # Clean signal: applied_vetoes and downgrades present and are lists
    result = validate(_snipe_signal(), _pf(), _BASE_CONFIG)
    assert "applied_vetoes" in result
    assert "downgrades" in result
    assert isinstance(result["applied_vetoes"], list)
    assert isinstance(result["downgrades"], list)


def test_downgrade_recorded_in_downgrades_list():
    # Force a downgrade and confirm it's recorded
    signal = _snipe_signal(
        retest_status="missing",
        hold_status="missing",
        missing_conditions=["retest_status", "hold_status"],
        upgrade_trigger="Retest of FVG at 179 with hold",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT"
    assert len(result["downgrades"]) >= 1
    assert "SNIPE_IT" in result["downgrades"][0]


def test_veto_flag_appears_in_applied_vetoes():
    result = validate(_snipe_signal(), _pf(["data_empty", "stale_data"]), _BASE_CONFIG)
    assert "data_empty" in result["applied_vetoes"]
    assert "stale_data" in result["applied_vetoes"]


# ---------------------------------------------------------------------------
# 31. No disabled indicators used in tiering logic
# ---------------------------------------------------------------------------

def test_no_disabled_indicators_in_tiering_source():
    source = pathlib.Path("src/tiering.py").read_text()
    source_lower = source.lower()
    for indicator in ("rsi", "macd", "bollinger_bands", "stochastic"):
        assert indicator not in source_lower, (
            f"Disabled indicator '{indicator}' found in src/tiering.py"
        )


# ---------------------------------------------------------------------------
# Extra: final_signal tier and routing always match final_tier
# ---------------------------------------------------------------------------

def test_final_signal_tier_matches_final_tier():
    for signal_fn in (_snipe_signal, _starter_signal, _near_entry_signal, _wait_signal):
        result = validate(signal_fn(), _pf(), _BASE_CONFIG)
        if result["final_signal"] is not None:
            assert result["final_signal"]["tier"] == result["final_tier"]
            assert result["final_signal"]["discord_channel"] == result["final_discord_channel"]
            assert result["final_signal"]["capital_action"] == result["capital_action"]


# ---------------------------------------------------------------------------
# Extra: channel and capital maps cover all tiers
# ---------------------------------------------------------------------------

def test_channel_map_covers_all_tiers():
    for tier in TIERS:
        assert tier in CHANNEL_MAP
    assert CHANNEL_MAP["WAIT"] == "none"


def test_capital_map_covers_all_tiers():
    for tier in TIERS:
        assert tier in CAPITAL_MAP
    assert CAPITAL_MAP["WAIT"] == "no_trade"

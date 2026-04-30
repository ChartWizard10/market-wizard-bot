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


# ---------------------------------------------------------------------------
# Phase 10A-G: Semantic price sanity, strict gates, damage cap, preservation
# ---------------------------------------------------------------------------

def _pf_with_price(price: float | None, vetoes: list | None = None) -> dict:
    """Prefilter result carrying a current_price for sanity gate tests."""
    return {
        "veto_flags": vetoes or [],
        "key_features": {"current_price": price},
    }


# 1. Invalidation at or above trigger → impossible bullish geometry → downgrade
def test_bullish_signal_rejects_invalidation_above_trigger():
    # invalidation_level >= trigger_level is impossible for a bullish entry
    signal = _snipe_signal(trigger_level=182.50, invalidation_level=185.00)
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT", (
        "SNIPE_IT must be blocked when invalidation_level >= trigger_level"
    )
    assert result["downgrades"], "downgrade must be recorded"


# 2. First target below trigger → target path impossible → downgrade
def test_bullish_signal_rejects_target_below_trigger():
    signal = _snipe_signal(
        trigger_level=182.50,
        invalidation_level=178.00,
        targets=[{"label": "T1", "level": 180.00, "reason": "Below entry — invalid"}],
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT", (
        "SNIPE_IT must be blocked when first target is at or below trigger_level"
    )


# 3. Non-positive risk_reward → invalid geometry → downgrade
def test_bullish_signal_rejects_nonpositive_risk_reward():
    signal = _snipe_signal(risk_reward=-1.0)
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] != "SNIPE_IT", (
        "SNIPE_IT must be blocked when risk_reward is negative"
    )


# 4. current_price below invalidation_level → position stopped out → WAIT
def test_current_price_below_invalidation_forces_wait_when_current_price_available():
    signal = _snipe_signal(trigger_level=182.50, invalidation_level=178.00)
    # Price has already traded below the stop level
    pf = _pf_with_price(175.00)
    result = validate(signal, pf, _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "current_price below invalidation_level must force WAIT regardless of Claude tier"
    )
    assert result["safe_for_alert"] is False


# 5. SNIPE_IT requires confirmed retest AND confirmed hold
def test_snipe_requires_confirmed_retest_and_hold():
    for bad_retest, bad_hold in [
        ("missing", "confirmed"),
        ("confirmed", "missing"),
        ("partial", "confirmed"),
        ("confirmed", "failed"),
    ]:
        signal = _snipe_signal(retest_status=bad_retest, hold_status=bad_hold)
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] != "SNIPE_IT", (
            f"SNIPE_IT must be blocked: retest={bad_retest} hold={bad_hold}"
        )
        assert result["original_claude_tier"] == "SNIPE_IT"


# 6. STARTER requires confirmed retest AND confirmed hold
def test_starter_requires_confirmed_retest_and_hold():
    for bad_retest, bad_hold in [
        ("missing", "confirmed"),
        ("confirmed", "missing"),
    ]:
        signal = _starter_signal(retest_status=bad_retest, hold_status=bad_hold)
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] not in ("SNIPE_IT", "STARTER"), (
            f"STARTER must be blocked: retest={bad_retest} hold={bad_hold}"
        )
        assert result["original_claude_tier"] == "STARTER"


# 7. NEAR_ENTRY allows missing retest/hold when geometry is valid
def test_near_entry_allows_missing_retest_only_when_geometry_valid():
    # Standard NEAR_ENTRY: missing retest, missing hold, invalidation_level=None → valid
    signal = _near_entry_signal()
    # trigger_level=182.50 (inherited), invalidation_level=None → geometry check skipped
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY", (
        "NEAR_ENTRY must be preserved when geometry is valid (invalidation_level=None skips check)"
    )
    assert result["safe_for_alert"] is True


# 8. NEAR_ENTRY with impossible geometry (both levels present, invalidation above trigger) → WAIT
def test_near_entry_impossible_geometry_forces_wait():
    signal = _near_entry_signal(
        trigger_level=182.50,
        invalidation_level=185.00,  # above trigger — impossible
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "NEAR_ENTRY with invalidation_level >= trigger_level must force WAIT"
    )
    assert result["safe_for_alert"] is False


# 9. JBHT-style valid STARTER is preserved by new sanity gates
def test_jbht_style_valid_starter_preserved():
    # Realistic STARTER: BOS, continuation, overhead moderate, confirmed retest/hold
    # trigger below current (already near entry), invalidation below trigger, target above
    signal = _starter_signal(
        ticker="JBHT",
        structure_event="BOS",
        setup_family="continuation",
        trend_state="mature_continuation",
        trigger_level=190.00,
        invalidation_level=185.50,   # below trigger ✓
        targets=[{"label": "T1", "level": 205.00, "reason": "Prior swing high cluster"}],
        risk_reward=3.2,             # >= 3.0 ✓
        overhead_status="moderate",  # not blocked ✓
        retest_status="confirmed",   # ✓
        hold_status="confirmed",     # ✓
        sma_value_alignment="supportive",
        score=78,
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "STARTER", (
        "JBHT-style STARTER with valid geometry must be preserved — not downgraded"
    )
    assert result["safe_for_alert"] is True
    assert result["final_discord_channel"] == "#starter-signals"
    assert result["capital_action"] == "starter_only"
    assert not result["downgrades"]


# 10. IRDM-style SNIPE_IT downgraded when current_price is below invalidation
def test_irdm_style_snipe_downgraded_or_wait_when_current_damage_fields_available():
    # Claude says SNIPE_IT, but current price has already traded through the stop zone
    signal = _snipe_signal(
        ticker="IRDM",
        trigger_level=10.50,
        invalidation_level=9.80,
        targets=[{"label": "T1", "level": 13.00, "reason": "Resistance cluster"}],
        risk_reward=3.5,
        retest_status="confirmed",
        hold_status="confirmed",
    )
    # Current price is 9.50 — already below invalidation_level of 9.80
    pf = _pf_with_price(9.50)
    result = validate(signal, pf, _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "IRDM-style SNIPE_IT must be capped to WAIT when current_price < invalidation_level"
    )
    assert result["safe_for_alert"] is False
    # Phase 10.1: acceptance pre-check fires first (invalidated), not semantic sanity
    assert "invalidated" in (result["rejection_reason"] or "")


# 11. WAIT never posts to Discord (explicit named test)
def test_wait_never_posts():
    for signal_fn in (_snipe_signal, _starter_signal, _near_entry_signal, _wait_signal):
        signal = signal_fn()
        result = validate(signal, _pf(), _BASE_CONFIG)
        if result["final_tier"] == "WAIT":
            assert result["final_discord_channel"] == "none", (
                f"WAIT must never post: got channel={result['final_discord_channel']!r}"
            )
            assert result["safe_for_alert"] is False
            assert result["capital_action"] == "no_trade"


# 12. discord_channel is always recomputed from final_tier (not trusted from Claude)
def test_discord_channel_recomputed_from_final_tier():
    # Claude says SNIPE_IT but puts a mismatched channel — tiering must correct it
    signal = _snipe_signal(discord_channel="#near-entry-watch")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "SNIPE_IT"
    assert result["final_discord_channel"] == "#snipe-signals"
    assert result["final_signal"]["discord_channel"] == "#snipe-signals"

    # STARTER with wrong channel
    signal = _starter_signal(discord_channel="#snipe-signals")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "STARTER"
    assert result["final_discord_channel"] == "#starter-signals"
    assert result["final_signal"]["discord_channel"] == "#starter-signals"


# 13. capital_action is always recomputed from final_tier (not trusted from Claude)
def test_capital_action_recomputed_from_final_tier():
    # Claude says SNIPE_IT but wrong capital_action
    signal = _snipe_signal(capital_action="wait_no_capital")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["capital_action"] == "full_quality_allowed"
    assert result["final_signal"]["capital_action"] == "full_quality_allowed"

    # NEAR_ENTRY that gets forced to WAIT — capital_action must be no_trade
    signal = _near_entry_signal(missing_conditions=[], upgrade_trigger="none")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["capital_action"] == "no_trade"
    assert result["final_signal"]["capital_action"] == "no_trade"


# 14. rejection_reason contains "semantic_price_sanity_failed" when geometry is rejected
def test_reason_includes_semantic_sanity_failure_on_geometry_reject():
    # Impossible geometry: invalidation above trigger
    signal = _snipe_signal(trigger_level=182.50, invalidation_level=185.00)
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["rejection_reason"] is not None
    assert "semantic_price_sanity_failed" in result["rejection_reason"], (
        f"rejection_reason must contain 'semantic_price_sanity_failed', got: {result['rejection_reason']!r}"
    )


# ===========================================================================
# Phase 10.1 — Current Acceptance Zone Defense Gate
# ===========================================================================

def _pf_with_key_features(key_features: dict, vetoes: list | None = None) -> dict:
    """Build a prefilter result with explicit key_features for acceptance tests."""
    return {
        "veto_flags": vetoes or [],
        "key_features": key_features,
    }


# 10.1-1: invalidated acceptance forces WAIT for SNIPE_IT
def test_acceptance_invalidated_forces_wait_snipe_it():
    # Price has traded through the stop — SNIPE_IT must become WAIT
    signal = _snipe_signal(trigger_level=50.00, invalidation_level=46.00)
    kf = {"current_price": 45.50}  # below invalidation_level=46.00
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        f"SNIPE_IT with price below stop must be WAIT, got {result['final_tier']!r}"
    )
    assert result["safe_for_alert"] is False
    assert "invalidated" in (result["rejection_reason"] or "")


# 10.1-2: invalidated acceptance forces WAIT for STARTER
def test_acceptance_invalidated_forces_wait_starter():
    signal = _starter_signal(trigger_level=50.00, invalidation_level=46.00)
    kf = {"current_price": 45.90}  # at/below stop
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["safe_for_alert"] is False
    assert "invalidated" in (result["rejection_reason"] or "")


# 10.1-3: invalidated acceptance forces WAIT for NEAR_ENTRY
def test_acceptance_invalidated_forces_wait_near_entry():
    # NEAR_ENTRY with a concrete invalidation level set — price trades through it
    signal = _near_entry_signal(
        trigger_level=50.00,
        invalidation_level=46.00,
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest of zone",
    )
    kf = {"current_price": 45.00}  # below stop
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "NEAR_ENTRY with price below stop must be WAIT"
    )
    assert "invalidated" in (result["rejection_reason"] or "")


# 10.1-4: damaging acceptance caps SNIPE_IT to NEAR_ENTRY (valid geometry)
def test_acceptance_damaging_caps_snipe_it_to_near_entry():
    # Price is below trigger but above stop → zone is being tested, not confirmed
    signal = _snipe_signal(trigger_level=50.00, invalidation_level=46.00)
    kf = {"current_price": 48.50}  # below trigger=50.00, above stop=46.00
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY", (
        f"SNIPE_IT with price below trigger must be capped to NEAR_ENTRY, got {result['final_tier']!r}"
    )
    assert result["safe_for_alert"] is True
    assert "damaging" in " ".join(result["downgrades"])


# 10.1-5: damaging acceptance caps STARTER to NEAR_ENTRY (valid geometry)
def test_acceptance_damaging_caps_starter_to_near_entry():
    signal = _starter_signal(trigger_level=50.00, invalidation_level=46.00)
    kf = {"current_price": 48.00}  # below trigger
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    assert "damaging" in " ".join(result["downgrades"])


# 10.1-6: damaging acceptance with impossible geometry forces WAIT (not NEAR_ENTRY)
def test_acceptance_damaging_with_impossible_geometry_forces_wait():
    # Price below trigger (damaging) AND target is below trigger (impossible geometry)
    signal = _snipe_signal(
        trigger_level=100.00,
        invalidation_level=95.00,
        targets=[{"label": "T1", "level": 90.00, "reason": "Below entry — impossible"}],
        risk_reward=3.5,
    )
    kf = {"current_price": 98.00, "current_bar_direction": "red", "current_close_location_pct": 0.20}
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "damaging acceptance + impossible geometry must produce WAIT, not NEAR_ENTRY"
    )
    assert "damaging" in (result["rejection_reason"] or "")


# 10.1-7: unproven acceptance blocks SNIPE_IT but STARTER survives cascade
def test_acceptance_unproven_blocks_snipe_but_not_starter():
    # trigger_level=None → _classify_current_acceptance returns 'unproven'
    # This adds a failure to _snipe_gate_failures only, not _starter_gate_failures.
    # score=90 passes STARTER min=75, so cascade lands at STARTER.
    signal = _snipe_signal(score=90, trigger_level=None)
    kf = {"current_price": 182.00, "current_bar_direction": "unknown"}
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "STARTER", (
        f"unproven acceptance must cascade SNIPE_IT → STARTER, got {result['final_tier']!r}"
    )
    assert any("unproven" in d for d in result["downgrades"])


# 10.1-8: accepted acceptance allows SNIPE_IT through
def test_acceptance_accepted_allows_snipe_it():
    # Price above trigger, green candle — zone is being actively defended
    signal = _snipe_signal(trigger_level=50.00, invalidation_level=46.00)
    kf = {
        "current_price": 52.00,  # above trigger
        "current_bar_direction": "green",
        "current_close_location_pct": 0.80,
    }
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "SNIPE_IT", (
        f"accepted acceptance must not downgrade SNIPE_IT, got {result['final_tier']!r}"
    )


# 10.1-9: unknown acceptance (no current data) does not force any downgrade
def test_acceptance_unknown_no_forced_downgrade():
    # _pf() has no key_features → current_price is None → acceptance='unknown'
    signal = _snipe_signal()
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "SNIPE_IT", (
        "Missing current price data must not downgrade a valid SNIPE_IT"
    )


# 10.1-10: FORM-style — active selling into zone caps SNIPE_IT to NEAR_ENTRY
def test_form_style_selling_into_zone_capped_to_near_entry():
    # FORM: strong red candle, close in bottom quarter, price below trigger
    signal = _snipe_signal(
        ticker="FORM",
        trigger_level=30.00,
        invalidation_level=27.00,
        targets=[{"label": "T1", "level": 38.00, "reason": "Prior swing high"}],
        risk_reward=3.5,
    )
    kf = {
        "current_price": 28.50,        # below trigger=30.00
        "current_bar_direction": "red",
        "current_close_location_pct": 0.18,  # closing near lows = strong rejection
    }
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY", (
        "FORM-style active zone selling must cap SNIPE_IT to NEAR_ENTRY"
    )
    assert result["capital_action"] == "wait_no_capital"


# 10.1-11: VFC-style — price already through stop forces WAIT
def test_vfc_style_price_through_stop_forced_wait():
    signal = _snipe_signal(
        ticker="VFC",
        trigger_level=20.00,
        invalidation_level=17.50,
        targets=[{"label": "T1", "level": 26.00, "reason": "Resistance level"}],
        risk_reward=3.5,
    )
    kf = {"current_price": 17.20}  # below invalidation_level=17.50
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "VFC-style: price through stop must force WAIT"
    )
    assert result["safe_for_alert"] is False
    assert result["capital_action"] == "no_trade"


# 10.1-12: CAVA-style — damaging + impossible geometry → WAIT (not NEAR_ENTRY)
def test_cava_style_damaging_impossible_geometry_forces_wait():
    # CAVA: price below trigger (damaging) AND first target is below trigger (impossible)
    signal = _snipe_signal(
        ticker="CAVA",
        trigger_level=120.00,
        invalidation_level=114.00,
        targets=[{"label": "T1", "level": 110.00, "reason": "Wrong direction target"}],
        risk_reward=3.5,
    )
    kf = {
        "current_price": 117.00,       # below trigger=120.00 → damaging
        "current_bar_direction": "red",
        "current_close_location_pct": 0.15,
    }
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT", (
        "CAVA-style damaging acceptance + impossible geometry must produce WAIT, not NEAR_ENTRY"
    )
    assert result["safe_for_alert"] is False


# 10.1-13: CAVA live failure mode — valid geometry, confirmed retest/hold, but damaging
#           current acceptance caps STARTER (the exact live scenario that slipped through)
def test_cava_style_valid_geometry_but_damaging_current_acceptance_caps_starter():
    # All geometry is valid: target above trigger, invalidation below trigger, positive R:R.
    # All confirmations are in place: retest confirmed, hold confirmed.
    # The sole failure: current price is falling into the zone — red candle, close near lows,
    # price has not reclaimed or defended the trigger level.
    # STARTER must NOT remain STARTER when the zone is being actively sold into.
    signal = _starter_signal(
        ticker="CAVA",
        trigger_level=90.00,
        invalidation_level=85.00,
        targets=[{"label": "T1", "level": 105.00, "reason": "Prior swing high"}],
        risk_reward=3.75,
        retest_status="confirmed",
        hold_status="confirmed",
        score=78,
    )
    kf = {
        "current_price": 87.50,          # above invalidation=85.00 but below trigger=90.00
        "current_bar_direction": "red",
        "current_close_location_pct": 0.22,  # closing in lower quarter — active selling
    }
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)

    assert result["final_tier"] != "STARTER", (
        "CAVA live failure: valid-geometry STARTER with damaging acceptance must not remain STARTER"
    )
    # damaging acceptance (price below trigger, red candle) → caps to NEAR_ENTRY
    assert result["final_tier"] == "NEAR_ENTRY", (
        f"STARTER with damaging current acceptance must be capped to NEAR_ENTRY, got {result['final_tier']!r}"
    )
    assert result["capital_action"] == "wait_no_capital"
    assert result["safe_for_alert"] is True
    assert any("damaging" in d for d in result["downgrades"]), (
        f"Downgrade reason must mention 'damaging', got: {result['downgrades']}"
    )


# ===========================================================================
# Phase 12A — Alert Integrity / Sanitized Reason
# ===========================================================================

from src.tiering import _sanitize_reason_for_tier


# 12A-1: sanitized_reason present in final_signal
def test_12a_sanitized_reason_present_in_final_signal():
    result = validate(_snipe_signal(), _pf(), _BASE_CONFIG)
    assert "sanitized_reason" in result["final_signal"]


# 12A-2: SNIPE_IT reason is preserved unchanged (no restrictions on SNIPE)
def test_12a_snipe_it_reason_preserved():
    signal = _snipe_signal(reason="All SNIPE_IT conditions met — execute full quality.")
    result = validate(signal, _pf(), _BASE_CONFIG)
    fs = result["final_signal"]
    assert result["final_tier"] == "SNIPE_IT"
    assert "All SNIPE_IT conditions met" in (fs["sanitized_reason"] or "")


# 12A-3: STARTER final_tier removes SNIPE_IT-claiming language
def test_12a_starter_sanitized_removes_snipe_language():
    dirty = "All SNIPE_IT conditions met — execute at full quality."
    clean = _sanitize_reason_for_tier(dirty, "STARTER")
    assert "All SNIPE_IT conditions met" not in clean
    assert "Starter-quality" in clean or "SNIPE confirmation not granted" in clean


# 12A-4: NEAR_ENTRY sanitized removes capital-approved language
def test_12a_near_entry_sanitized_removes_capital_language():
    dirty = "Zone valid. Reducing conviction to STARTER tier only — retest not confirmed."
    clean = _sanitize_reason_for_tier(dirty, "NEAR_ENTRY")
    assert "STARTER tier only" not in clean
    assert "watch-only" in clean.lower() or "confirmation pending" in clean.lower()


# 12A-5: WAIT sanitized removes entry-approved language
def test_12a_wait_sanitized_removes_entry_language():
    dirty = "Full quality allowed — capital authorized to enter."
    clean = _sanitize_reason_for_tier(dirty, "WAIT")
    assert "capital authorized" not in clean.lower() or "no capital authorized" in clean.lower()
    assert "full quality allowed" not in clean.lower() or "no capital authorized" in clean.lower()


# 12A-6: STARTER validate call produces sanitized_reason in final_signal
def test_12a_starter_validate_sanitized_reason_in_signal():
    signal = _starter_signal(reason="All SNIPE_IT conditions met — reduced size only.")
    result = validate(signal, _pf(), _BASE_CONFIG)
    fs = result["final_signal"]
    sanitized = fs.get("sanitized_reason") or ""
    assert "All SNIPE_IT conditions met" not in sanitized


# 12A-7: sanitize_reason_for_tier is a pure function (empty reason returns empty string)
def test_12a_sanitize_empty_reason_returns_empty():
    assert _sanitize_reason_for_tier("", "STARTER") == ""
    assert _sanitize_reason_for_tier(None, "NEAR_ENTRY") == ""


# 12A-8: Regression — replacement string that contains its banned phrase must
# not cause the sanitizer to re-scan inserted replacement text. Previously the
# while/find loop produced an infinite loop because "No capital authorized."
# contains "capital authorized" and was matched again on every iteration.
def test_12a_sanitizer_replacement_that_contains_banned_phrase_does_not_loop():
    # Direct unit-level call — must terminate.
    dirty = "Capital authorized — proceed to entry."
    clean = _sanitize_reason_for_tier(dirty, "WAIT")
    assert isinstance(clean, str)
    # The misleading entry permission must be neutered. The sanitizer's intent
    # is to ensure any reader sees "no capital authorized" wording, not raw
    # "capital authorized" as a positive permission.
    assert "no capital authorized" in clean.lower()

    # Through validate() — must terminate, must keep WAIT, must populate sanitized_reason.
    signal = _wait_signal(reason="Capital authorized — proceed to entry.")
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    fs = result["final_signal"]
    sanitized = fs.get("sanitized_reason") or ""
    assert "no capital authorized" in sanitized.lower()


# 12A-9: NEAR_ENTRY equivalent — same self-containing replacement bug class.
# NEAR_ENTRY has ("capital authorized", "no capital authorized") which is
# structurally identical to the WAIT case.
def test_12a_near_entry_capital_authorized_replacement_does_not_loop():
    dirty = "Setup forming. Capital authorized once retest confirms."
    clean = _sanitize_reason_for_tier(dirty, "NEAR_ENTRY")
    assert isinstance(clean, str)
    assert "no capital authorized" in clean.lower()


# ===========================================================================
# Phase 12B: Conservative NEAR_ENTRY missing_conditions backfill
# ===========================================================================

# 12B-1: No backfill when both retest and hold are missing — no observable
# progress, so missing_conditions stays empty and the existing veto runs the
# signal down to WAIT.
def test_12b_no_backfill_when_retest_and_hold_both_missing():
    signal = _near_entry_signal(
        missing_conditions=[],
        retest_status="missing",
        hold_status="missing",
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["capital_action"] == "no_trade"
    fs = result["final_signal"]
    # Backfill must not invent items
    assert fs.get("missing_conditions") in ([], None) or fs.get("missing_conditions") == []


# 12B-2: Backfill runs when retest is partial — at least one sign of progress.
def test_12b_backfills_missing_conditions_when_retest_partial():
    signal = _near_entry_signal(
        missing_conditions=[],
        retest_status="partial",
        hold_status="missing",
        invalidation_level=178.20,
        trigger_level=182.50,
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    assert result["capital_action"] == "wait_no_capital"
    fs = result["final_signal"]
    backfilled = fs.get("missing_conditions") or []
    assert isinstance(backfilled, list)
    assert backfilled  # non-empty
    # Hold is still missing, so "missing_hold" is the deterministic item
    assert "missing_hold" in backfilled


# 12B-3: Backfill runs when hold is partial — at least one sign of progress.
def test_12b_backfills_missing_conditions_when_hold_partial():
    signal = _near_entry_signal(
        missing_conditions=[],
        retest_status="missing",
        hold_status="partial",
        invalidation_level=178.20,
        trigger_level=182.50,
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    assert result["capital_action"] == "wait_no_capital"
    fs = result["final_signal"]
    backfilled = fs.get("missing_conditions") or []
    assert isinstance(backfilled, list)
    assert backfilled
    assert "missing_retest" in backfilled


# 12B-4: Backfill must NOT override Phase 10 semantic geometry failure.
# Invalidation >= trigger is impossible bullish geometry — hard veto always wins.
def test_12b_backfill_does_not_override_semantic_geometry_failure():
    signal = _near_entry_signal(
        missing_conditions=[],
        retest_status="partial",
        hold_status="missing",
        trigger_level=180.00,
        invalidation_level=182.00,  # Above trigger — impossible bullish geometry
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "WAIT"
    assert result["capital_action"] == "no_trade"
    # The downgrade reason must mention the Phase 10 semantic sanity failure
    downgrade_text = " ".join(result.get("downgrades", []))
    assert "semantic_price_sanity_failed" in downgrade_text


# 12B-5: Backfill must NOT override Phase 10.1 current_acceptance damage cap.
# Price below trigger ("damaging") downgrades SNIPE/STARTER → NEAR_ENTRY but
# also stops NEAR_ENTRY from being escalated. For a NEAR_ENTRY claude_tier
# under damaging acceptance with valid geometry, NEAR_ENTRY remains, never gets
# converted into a capital-authorized state by Phase 12B's backfill.
def test_12b_backfill_does_not_override_current_acceptance_failure():
    signal = _near_entry_signal(
        missing_conditions=[],
        retest_status="partial",
        hold_status="missing",
        trigger_level=182.50,
        invalidation_level=178.20,
    )
    # current_price below trigger → damaging acceptance
    pf = {"veto_flags": [], "key_features": {"current_price": 180.00}}
    result = validate(signal, pf, _BASE_CONFIG)
    # Capital must remain wait_no_capital regardless of backfill — NEAR_ENTRY
    # tier never grants capital.
    assert result["capital_action"] == "wait_no_capital"
    # Tier itself stays NEAR_ENTRY (or downgrades to WAIT) but never escalates.
    assert result["final_tier"] in ("NEAR_ENTRY", "WAIT")


# 12B-6: SNIPE_IT and STARTER gates must be unchanged. The backfill only
# applies to claude_tier=NEAR_ENTRY signals, so a valid SNIPE_IT and STARTER
# fixture should produce the same result as before Phase 12B.
def test_12b_snipe_and_starter_gates_unchanged():
    snipe_result = validate(_snipe_signal(), _pf(), _BASE_CONFIG)
    assert snipe_result["final_tier"] == "SNIPE_IT"
    assert snipe_result["final_discord_channel"] == "#snipe-signals"
    assert snipe_result["capital_action"] == "full_quality_allowed"

    starter_result = validate(_starter_signal(), _pf(), _BASE_CONFIG)
    assert starter_result["final_tier"] == "STARTER"
    assert starter_result["final_discord_channel"] == "#starter-signals"
    assert starter_result["capital_action"] == "starter_only"

    # Even if we hand SNIPE_IT/STARTER an empty missing_conditions, Phase 12B
    # backfill must not run for those tiers — their gates are independent.
    snipe_empty_mc = validate(
        _snipe_signal(missing_conditions=[]), _pf(), _BASE_CONFIG
    )
    assert snipe_empty_mc["final_tier"] == "SNIPE_IT"
    starter_empty_mc = validate(
        _starter_signal(missing_conditions=[]), _pf(), _BASE_CONFIG
    )
    assert starter_empty_mc["final_tier"] == "STARTER"


# ===========================================================================
# Phase 12C: Risk Realism informational fields
# ===========================================================================

from src.tiering import _classify_risk_realism


# 12C-1: Tiny risk distance → fragile state. Final tier preserved.
def test_12c_valid_geometry_tiny_stop_gets_fragile_risk_state():
    # trigger=100.00, invalidation=99.70 → risk_distance=0.30, pct=0.30%
    signal = _snipe_signal(
        trigger_level=100.00,
        invalidation_level=99.70,
        targets=[{"label": "T1", "level": 105.00, "reason": "Prior swing high"}],
        risk_reward=3.5,
    )
    kf = {"current_price": 101.50}
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    fs = result["final_signal"]
    assert fs["risk_realism_state"] == "fragile"
    assert "fragile" in fs["risk_realism_note"].lower()
    # Phase 12C must NOT introduce semantic_price_sanity_failed for valid geometry
    downgrade_text = " ".join(result.get("downgrades", []))
    assert "semantic_price_sanity_failed" not in downgrade_text
    # Final tier must not be downgraded by Phase 12C alone
    assert result["final_tier"] == "SNIPE_IT"


# 12C-2: Risk distance between 0.35% and 0.75% → tight state.
def test_12c_valid_geometry_tight_stop_gets_tight_risk_state():
    # trigger=100.00, invalidation=99.50 → pct=0.50%
    signal = _snipe_signal(
        trigger_level=100.00,
        invalidation_level=99.50,
        targets=[{"label": "T1", "level": 105.00, "reason": "Prior swing high"}],
        risk_reward=3.5,
    )
    kf = {"current_price": 102.00}
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    fs = result["final_signal"]
    assert fs["risk_realism_state"] == "tight"
    assert "tight" in fs["risk_realism_note"].lower()
    assert result["final_tier"] == "SNIPE_IT"


# 12C-3: Healthy risk window — risk_distance_pct >= 0.75% AND
# current_price_to_invalidation_pct >= 1.0%.
def test_12c_healthy_risk_window_gets_healthy_state():
    # trigger=100.00, invalidation=98.00 → risk_distance_pct=2.0%
    # current_price=102.00, cp - invalidation = 4.0, pct = 4.0/102 * 100 = 3.92%
    signal = _snipe_signal(
        trigger_level=100.00,
        invalidation_level=98.00,
        targets=[{"label": "T1", "level": 110.00, "reason": "Prior swing high"}],
        risk_reward=5.0,
    )
    kf = {"current_price": 102.00}
    result = validate(signal, _pf_with_key_features(kf), _BASE_CONFIG)
    fs = result["final_signal"]
    assert fs["risk_realism_state"] == "healthy"
    assert "healthy" in fs["risk_realism_note"].lower()
    assert fs["risk_distance"] == 2.0
    assert fs["risk_distance_pct"] == 2.0


# 12C-4: Missing trigger or invalidation → unknown, no crash, no downgrade.
def test_12c_missing_fields_gets_unknown_without_downgrade():
    # NEAR_ENTRY signal with no invalidation_level — should be "unknown"
    signal = _near_entry_signal(invalidation_level=None)
    result = validate(signal, _pf(), _BASE_CONFIG)
    fs = result["final_signal"]
    assert fs["risk_realism_state"] == "unknown"
    assert fs["risk_distance"] is None
    assert fs["risk_distance_pct"] is None
    # No new hard downgrade caused by risk realism
    downgrade_text = " ".join(result.get("downgrades", []))
    assert "risk_realism" not in downgrade_text.lower()
    assert "fragile" not in downgrade_text.lower()


# 12C-5: Impossible geometry still produces canonical semantic_price_sanity_failed.
# Phase 12C must NOT replace or compete with that rejection reason. risk_realism
# may still mark the state as "invalid" informationally.
def test_12c_impossible_geometry_still_uses_semantic_price_sanity_failed():
    # invalidation=105.00 >= trigger=100.00 → impossible bullish geometry
    signal = _snipe_signal(
        trigger_level=100.00,
        invalidation_level=105.00,
        targets=[{"label": "T1", "level": 110.00, "reason": "Prior swing high"}],
        risk_reward=3.5,
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    # Canonical rejection reason still mentions semantic_price_sanity_failed
    downgrade_text = " ".join(result.get("downgrades", []))
    assert "semantic_price_sanity_failed" in downgrade_text, (
        f"Phase 10 semantic gate must own impossible-geometry rejection. "
        f"Got downgrades: {result.get('downgrades')!r}"
    )
    # Final tier WAIT
    assert result["final_tier"] == "WAIT"
    # Phase 12C marks informationally — but does not own the rejection
    fs = result["final_signal"]
    assert fs["risk_realism_state"] == "invalid"


# 12C-6: JBHT-style valid STARTER must remain STARTER. risk_realism is
# informational and does not change tier or capital action.
def test_12c_risk_realism_does_not_change_jbht_style_starter():
    # JBHT: trigger=190.00, invalidation=185.50 → risk_distance_pct ≈ 2.37% → healthy
    signal = _starter_signal(
        ticker="JBHT",
        structure_event="BOS",
        setup_family="continuation",
        trend_state="mature_continuation",
        trigger_level=190.00,
        invalidation_level=185.50,
        targets=[{"label": "T1", "level": 205.00, "reason": "Prior swing high cluster"}],
        risk_reward=3.2,
        overhead_status="moderate",
        retest_status="confirmed",
        hold_status="confirmed",
        sma_value_alignment="supportive",
        score=78,
    )
    result = validate(signal, _pf(), _BASE_CONFIG)
    assert result["final_tier"] == "STARTER"
    assert result["capital_action"] == "starter_only"
    fs = result["final_signal"]
    assert fs["risk_realism_state"] in ("healthy", "tight")


# 12C-7: Phase 10/10.1 regression — FORM/VFC/CAVA/JBHT scenarios still pass.
# This test re-runs the canonical Phase 10/10.1 fixtures alongside Phase 12C
# to prove that adding the risk_realism informational fields did not regress
# any existing semantic gate or current-acceptance behavior.
def test_12c_phase_10_1_form_vfc_cava_tests_still_pass():
    # FORM-style: SNIPE with selling-into-zone (damaging) + valid geometry → NEAR_ENTRY cap
    form_signal = _snipe_signal(
        ticker="FORM",
        trigger_level=50.00,
        invalidation_level=46.00,
        targets=[{"label": "T1", "level": 60.00, "reason": "Prior swing high"}],
        risk_reward=3.0,
        retest_status="confirmed",
        hold_status="confirmed",
    )
    form_kf = {
        "current_price": 47.50,
        "current_bar_direction": "red",
        "current_close_location_pct": 0.18,
    }
    form_result = validate(form_signal, _pf_with_key_features(form_kf), _BASE_CONFIG)
    assert form_result["final_tier"] == "NEAR_ENTRY", (
        "FORM-style damaging acceptance with valid geometry must cap to NEAR_ENTRY"
    )

    # VFC-style: price already through stop → WAIT
    vfc_signal = _snipe_signal(
        ticker="VFC",
        trigger_level=15.00,
        invalidation_level=14.20,
        targets=[{"label": "T1", "level": 18.00, "reason": "Prior swing high"}],
        risk_reward=3.5,
    )
    vfc_kf = {"current_price": 13.80}
    vfc_result = validate(vfc_signal, _pf_with_key_features(vfc_kf), _BASE_CONFIG)
    assert vfc_result["final_tier"] == "WAIT", (
        "VFC-style price-through-stop must force WAIT"
    )

    # CAVA valid-geometry damaging → STARTER capped to NEAR_ENTRY
    cava_signal = _starter_signal(
        ticker="CAVA",
        trigger_level=90.00,
        invalidation_level=85.00,
        targets=[{"label": "T1", "level": 105.00, "reason": "Prior swing high"}],
        risk_reward=3.75,
        retest_status="confirmed",
        hold_status="confirmed",
        score=78,
    )
    cava_kf = {
        "current_price": 87.50,
        "current_bar_direction": "red",
        "current_close_location_pct": 0.22,
    }
    cava_result = validate(cava_signal, _pf_with_key_features(cava_kf), _BASE_CONFIG)
    assert cava_result["final_tier"] == "NEAR_ENTRY", (
        "CAVA valid-geometry damaging acceptance must cap STARTER to NEAR_ENTRY"
    )

    # JBHT valid STARTER preserved
    jbht_signal = _starter_signal(
        ticker="JBHT",
        structure_event="BOS",
        trigger_level=190.00,
        invalidation_level=185.50,
        targets=[{"label": "T1", "level": 205.00, "reason": "Prior swing high"}],
        risk_reward=3.2,
        overhead_status="moderate",
        retest_status="confirmed",
        hold_status="confirmed",
        sma_value_alignment="supportive",
        score=78,
    )
    jbht_result = validate(jbht_signal, _pf(), _BASE_CONFIG)
    assert jbht_result["final_tier"] == "STARTER", (
        "JBHT-style valid STARTER must remain STARTER under Phase 12C"
    )


# 12C-8: Direct unit test for _classify_risk_realism (no validate() coupling).
def test_12c_classify_risk_realism_direct_units():
    # Healthy
    state, note, fields = _classify_risk_realism(100.0, 98.0, 102.0)
    assert state == "healthy"
    assert fields["risk_distance"] == 2.0
    assert fields["risk_distance_pct"] == 2.0

    # Tight
    state, _, _ = _classify_risk_realism(100.0, 99.50, 101.50)
    assert state == "tight"

    # Fragile
    state, _, _ = _classify_risk_realism(100.0, 99.80, 101.0)
    assert state == "fragile"

    # Invalid (impossible geometry — Phase 10 owns rejection, Phase 12C labels)
    state, note, _ = _classify_risk_realism(100.0, 105.0, 101.0)
    assert state == "invalid"
    assert "semantic gate owns rejection" in note.lower()

    # Unknown — missing trigger
    state, _, fields = _classify_risk_realism(None, 98.0, 102.0)
    assert state == "unknown"
    assert fields["risk_distance"] is None

    # Unknown — missing invalidation
    state, _, _ = _classify_risk_realism(100.0, None, 102.0)
    assert state == "unknown"

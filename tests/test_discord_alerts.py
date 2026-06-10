"""Discord alert routing and format tests — Phase 7."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.discord_alerts import (
    resolve_channel_id,
    format_alert,
    chunk_message,
    send_alert,
    _sanitize,
    _sendable,
    _clean_blocker_label,
    _classify_entry_grade,
    _ENTRY_GRADE_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tiering_result(tier="SNIPE_IT", score=88, safe=True, **signal_overrides) -> dict:
    signal = {
        "ticker": "AAPL",
        "tier": tier,
        "score": score,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 182.50,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Daily close below FVG base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "risk_reward": 3.1,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at zone retest",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with FVG retest confirmed.",
        # Phase 12A: sanitized_reason (None = falls back to reason)
        "sanitized_reason": None,
        # Phase 11 freshness fields (mirroring what tiering.validate() now adds)
        "scan_price": 182.50,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "Signal based on scan-time price; verify live chart before entry.",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 2.41,
        # Phase 12C risk realism informational fields (defaults match a healthy SNIPE_IT)
        "risk_distance": 4.30,
        "risk_distance_pct": 2.356,
        "current_price_to_invalidation": 4.30,
        "current_price_to_invalidation_pct": 2.356,
        "risk_realism_state": "healthy",
        "risk_realism_note": "Risk window is healthy.",
    }
    signal.update(signal_overrides)
    return {
        "ok": True,
        "final_tier": tier,
        "score": score,
        "safe_for_alert": safe,
        "final_discord_channel": "#snipe-signals" if tier == "SNIPE_IT" else "none",
        "capital_action": signal["capital_action"],
        "final_signal": signal,
    }


def _dedup_yes(reason="new_signal") -> dict:
    return {"should_alert": True, "reason": reason, "dedup_key": "AAPL|SNIPE_IT|182.50|178.20"}


def _dedup_no(reason="duplicate_suppressed") -> dict:
    return {"should_alert": False, "reason": reason, "dedup_key": "AAPL|SNIPE_IT|182.50|178.20"}


def _mock_bot(channel_id: int) -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    return bot


def _config(snipe=1001, starter=1002, near_entry=1003) -> dict:
    return {
        "discord": {
            "snipe_channel_id": snipe,
            "starter_channel_id": starter,
            "near_entry_channel_id": near_entry,
            "scan_log_channel_id": None,
        }
    }


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. SNIPE_IT routes to snipe channel
# ---------------------------------------------------------------------------

def test_snipe_it_routes_to_snipe_channel():
    tr = _tiering_result(tier="SNIPE_IT")
    bot = _mock_bot(1001)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is True
    assert result["channel_id"] == 1001
    bot.get_channel.assert_called_once_with(1001)


# ---------------------------------------------------------------------------
# 2. STARTER routes to starter channel
# ---------------------------------------------------------------------------

def test_starter_routes_to_starter_channel():
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        discord_channel="#starter-signals",
    )
    tr["final_discord_channel"] = "#starter-signals"
    bot = _mock_bot(1002)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is True
    assert result["channel_id"] == 1002


# ---------------------------------------------------------------------------
# 3. NEAR_ENTRY routes to near-entry channel
# ---------------------------------------------------------------------------

def test_near_entry_routes_to_near_entry_channel():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        safe=True,
        capital_action="wait_no_capital",
        discord_channel="#near-entry-watch",
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest",
    )
    tr["final_discord_channel"] = "#near-entry-watch"
    bot = _mock_bot(1003)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is True
    assert result["channel_id"] == 1003


# ---------------------------------------------------------------------------
# 4. WAIT does not post
# ---------------------------------------------------------------------------

def test_wait_does_not_post():
    tr = _tiering_result(tier="WAIT", safe=False)
    tr["safe_for_alert"] = False
    bot = MagicMock()
    bot.get_channel = MagicMock()
    cfg = _config()
    result = _run(send_alert(tr, None, bot, cfg))
    assert result["sent"] is False
    bot.get_channel.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Null channel ID: no crash, logs ROUTING_FAILURE
# ---------------------------------------------------------------------------

def test_null_channel_id_no_crash():
    tr = _tiering_result(tier="SNIPE_IT")
    bot = MagicMock()
    bot.get_channel = MagicMock()
    cfg = {"discord": {"snipe_channel_id": None, "starter_channel_id": None, "near_entry_channel_id": None}}
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is False
    assert result["skipped_reason"] == "channel_not_configured"
    bot.get_channel.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Alert fields come from validated signal dict only
# ---------------------------------------------------------------------------

def test_alert_fields_from_json_only():
    tr = _tiering_result(tier="SNIPE_IT", score=90)
    text = format_alert(tr)
    assert "AAPL" in text
    assert "90" in text
    assert "MSS" in text
    assert "continuation" in text
    assert "182.50" in text
    assert "178.20" in text
    assert "T1" in text
    assert "195.00" in text


# ---------------------------------------------------------------------------
# 7. Dedup suppressed → no post
# ---------------------------------------------------------------------------

def test_dedup_suppressed_does_not_post():
    tr = _tiering_result(tier="SNIPE_IT")
    bot = _mock_bot(1001)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_no(), bot, cfg))
    assert result["sent"] is False
    assert result["skipped_reason"] == "duplicate_suppressed"
    bot.get_channel.assert_not_called()


# ---------------------------------------------------------------------------
# 8. None dedup_decision allows send (manual path)
# ---------------------------------------------------------------------------

def test_none_dedup_allows_send():
    tr = _tiering_result(tier="SNIPE_IT")
    bot = _mock_bot(1001)
    cfg = _config()
    result = _run(send_alert(tr, None, bot, cfg))
    assert result["sent"] is True


# ---------------------------------------------------------------------------
# 9. safe_for_alert=False blocks even with good tier
# ---------------------------------------------------------------------------

def test_unsafe_for_alert_blocks_send():
    tr = _tiering_result(tier="SNIPE_IT", safe=False)
    tr["safe_for_alert"] = False
    bot = _mock_bot(1001)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is False
    assert result["skipped_reason"] == "unsafe_for_alert"


# ---------------------------------------------------------------------------
# 10. Discord send exception: returns ok=False, no crash
# ---------------------------------------------------------------------------

def test_discord_send_exception_returns_error_no_crash():
    tr = _tiering_result(tier="SNIPE_IT")
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=Exception("Connection reset"))
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["ok"] is False
    assert result["sent"] is False
    assert result["error_type"] == "discord_send_error"
    assert "Connection reset" in result["error_message"]


# ---------------------------------------------------------------------------
# 11. chunk_message returns single chunk for short text
# ---------------------------------------------------------------------------

def test_chunk_message_single_chunk_for_short_text():
    text = "Hello world"
    chunks = chunk_message(text, max_len=2000)
    assert chunks == ["Hello world"]


# ---------------------------------------------------------------------------
# 12. chunk_message splits correctly at line boundary
# ---------------------------------------------------------------------------

def test_chunk_message_splits_on_line_boundary():
    # 3 lines each 800 chars → total 2400+ chars, must split at 2000 limit
    line = "A" * 800
    text = f"{line}\n{line}\n{line}"
    chunks = chunk_message(text, max_len=2000)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 2000


# ---------------------------------------------------------------------------
# 13. chunk_message hard-splits a single line exceeding max_len
# ---------------------------------------------------------------------------

def test_chunk_message_hard_splits_overlong_line():
    line = "X" * 3000
    chunks = chunk_message(line, max_len=2000)
    assert len(chunks) == 2
    assert all(len(c) <= 2000 for c in chunks)


# ---------------------------------------------------------------------------
# 14. _sanitize neutralizes @everyone
# ---------------------------------------------------------------------------

def test_sanitize_neutralizes_at_everyone():
    result = _sanitize("@everyone check this out")
    assert "@everyone" not in result
    assert "everyone" in result  # text preserved, just broken


# ---------------------------------------------------------------------------
# 15. _sanitize neutralizes @here
# ---------------------------------------------------------------------------

def test_sanitize_neutralizes_at_here():
    result = _sanitize("@here please look")
    assert "@here" not in result
    assert "here" in result


# ---------------------------------------------------------------------------
# 16. _sanitize strips role/user mentions
# ---------------------------------------------------------------------------

def test_sanitize_strips_role_user_mentions():
    result = _sanitize("Hey <@123456789> and <@&987654321>")
    assert "<@" not in result
    assert "[mention]" in result


# ---------------------------------------------------------------------------
# 17. format_alert includes NEAR_ENTRY-specific fields
# ---------------------------------------------------------------------------

def test_format_alert_near_entry_includes_missing_conditions_and_upgrade_trigger():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status", "hold_status"],
        upgrade_trigger="Confirmed retest of FVG at 179.00",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    text = format_alert(tr)
    assert "NO CAPITAL" in text
    assert "retest_status" in text
    assert "hold_status" in text
    assert "Confirmed retest of FVG at 179.00" in text


# ---------------------------------------------------------------------------
# 18. format_alert does NOT include NEAR_ENTRY block for SNIPE_IT
# ---------------------------------------------------------------------------

def test_format_alert_snipe_it_no_near_entry_block():
    tr = _tiering_result(tier="SNIPE_IT")
    text = format_alert(tr)
    assert "NO CAPITAL" not in text
    assert "Missing conditions" not in text


# ---------------------------------------------------------------------------
# 19. format_alert includes forced participation when non-none
# ---------------------------------------------------------------------------

def test_format_alert_includes_forced_participation():
    tr = _tiering_result(tier="SNIPE_IT", forced_participation="Earnings in 2 days")
    text = format_alert(tr)
    assert "FORCED PARTICIPATION" in text
    assert "Earnings in 2 days" in text


# ---------------------------------------------------------------------------
# 20. format_alert omits forced participation when 'none'
# ---------------------------------------------------------------------------

def test_format_alert_omits_forced_participation_when_none():
    tr = _tiering_result(tier="SNIPE_IT", forced_participation="none")
    text = format_alert(tr)
    assert "FORCED PARTICIPATION" not in text


# ---------------------------------------------------------------------------
# 21. resolve_channel_id reads env var first
# ---------------------------------------------------------------------------

def test_resolve_channel_id_reads_env_var_first():
    cfg = _config(snipe=1001)
    with patch.dict(os.environ, {"DISCORD_SNIPE_CHANNEL_ID": "9999"}):
        result = resolve_channel_id("SNIPE_IT", cfg)
    assert result == 9999


# ---------------------------------------------------------------------------
# 22. resolve_channel_id falls back to config when env var absent
# ---------------------------------------------------------------------------

def test_resolve_channel_id_falls_back_to_config():
    cfg = _config(snipe=1001)
    env_without_snipe = {k: v for k, v in os.environ.items() if k != "DISCORD_SNIPE_CHANNEL_ID"}
    with patch.dict(os.environ, env_without_snipe, clear=True):
        result = resolve_channel_id("SNIPE_IT", cfg)
    assert result == 1001


# ---------------------------------------------------------------------------
# 23. resolve_channel_id returns None for unknown tier
# ---------------------------------------------------------------------------

def test_resolve_channel_id_returns_none_for_wait():
    cfg = _config()
    result = resolve_channel_id("WAIT", cfg)
    assert result is None


# ---------------------------------------------------------------------------
# 24. send_alert posts multiple chunks when message is long
# ---------------------------------------------------------------------------

def test_send_alert_posts_multiple_chunks_for_long_message():
    tr = _tiering_result(
        tier="SNIPE_IT",
        reason="A" * 1500,
        next_action="B" * 600,
    )
    channel = MagicMock()
    channel.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    cfg = _config()
    result = _run(send_alert(tr, _dedup_yes(), bot, cfg))
    assert result["sent"] is True
    assert result["message_count"] >= 2
    assert channel.send.call_count == result["message_count"]


# ===========================================================================
# Phase 11 — Alert Freshness + Drift Layer
# ===========================================================================

import pytest


# 11-1: FRESHNESS block includes scan_price when available
def test_alert_includes_scan_price_when_current_price_available():
    tr = _tiering_result(tier="SNIPE_IT", scan_price=182.50)
    text = format_alert(tr)
    assert "FRESHNESS" in text
    assert "Scan Price:" in text
    assert "182.50" in text


# 11-2: drift_status=snapshot_only when no live recheck price (current architecture)
def test_alert_freshness_snapshot_only_when_no_live_recheck_price():
    tr = _tiering_result(tier="SNIPE_IT", drift_status="snapshot_only", drift_pct=0.0)
    text = format_alert(tr)
    assert "snapshot_only" in text
    assert "verify live chart" in text.lower() or "scan-time" in text.lower()


# 11-3: future — drift_status=invalidated if live price available
@pytest.mark.skip(
    reason="TODO: Requires live post-scan recheck price. "
    "Currently snapshot_only only. Implement when !recheck TICKER is built."
)
def test_drift_status_invalidated_when_current_price_below_invalidation_if_live_price_available():
    pass


# 11-4: future — drift_status=degraded if live price moves below trigger
@pytest.mark.skip(
    reason="TODO: Requires live post-scan recheck price. "
    "Currently snapshot_only only. Implement when !recheck TICKER is built."
)
def test_drift_status_degraded_when_current_price_moves_below_trigger_if_live_price_available():
    pass


# 11-5: future — drift_status=extended if live price near T1
@pytest.mark.skip(
    reason="TODO: Requires live post-scan recheck price. "
    "Currently snapshot_only only. Implement when !recheck TICKER is built."
)
def test_drift_status_extended_when_price_near_target_if_live_price_available():
    pass


# 11-6: STARTER alert must not say "All SNIPE_IT conditions met." in the ACTION block
def test_starter_alert_does_not_say_all_snipe_conditions_met():
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        # Claude's reason deliberately does NOT say SNIPE_IT (well-behaved case)
        reason="Partial zone interaction — reduced size warranted.",
    )
    tr["final_tier"] = "STARTER"
    tr["capital_action"] = "starter_only"
    text = format_alert(tr)
    # Deterministic tier label must say STARTER (Phase 13.7B contract headline)
    assert "STARTER conditions met." in text
    # SNIPE_IT label must NOT appear in this STARTER alert
    assert "All SNIPE_IT conditions met." not in text


# 11-7: SNIPE_IT alert correctly shows "SNIPE_IT conditions met." (Phase 13.7B contract)
def test_snipe_alert_says_all_snipe_conditions_met():
    tr = _tiering_result(tier="SNIPE_IT", reason="Clean zone defense, full quality.")
    text = format_alert(tr)
    assert "SNIPE_IT conditions met." in text
    assert "STARTER conditions met." not in text


# 11-8: NEAR_ENTRY alert uses NEAR_ENTRY action language
def test_near_entry_alert_uses_near_entry_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    # Phase 13.6A: label updated — no longer says "wait for missing confirmations"
    # (inaccurate when retest/hold confirmed but overhead/acceptance blocks capital)
    assert "Near-entry watch — no capital until blocker resolves." in text


# 11-9: WAIT never posts — but if format_alert called directly it shows WAIT language
def test_wait_alert_uses_wait_language_or_does_not_post():
    tr = _tiering_result(tier="WAIT", safe=False)
    tr["final_tier"] = "WAIT"
    tr["safe_for_alert"] = False
    # WAIT never posts via send_alert (tested elsewhere)
    # If format_alert called directly, tier action label must be WAIT
    text = format_alert(tr)
    assert "WAIT — no actionable setup." in text
    # send_alert blocks WAIT
    bot = MagicMock()
    bot.get_channel = MagicMock()
    cfg = _config()
    result = _run(send_alert(tr, None, bot, cfg))
    assert result["sent"] is False


# 11-10: final_tier controls ACTION label regardless of what Claude wrote in reason
def test_final_tier_controls_alert_language_not_claude_reason():
    # Claude wrote SNIPE_IT language in reason, but final_tier is STARTER
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        reason="All SNIPE_IT conditions met — execute at full quality.",
    )
    tr["final_tier"] = "STARTER"
    tr["capital_action"] = "starter_only"
    text = format_alert(tr)
    # Deterministic label must be STARTER (from final_tier — Phase 13.7B contract)
    assert "STARTER conditions met." in text
    # The badge must say STARTER too
    assert "🟡 STARTER" in text


# 11-11: Phase 10 semantic price sanity gates still pass (regression)
def test_phase10_semantic_price_sanity_still_passes():
    from src.tiering import validate
    signal = {
        "ticker": "JBHT",
        "tier": "STARTER",
        "score": 78,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "OB",
        "trigger_level": 182.50,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Below OB base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at retest",
        "discord_channel": "#starter-signals",
        "capital_action": "starter_only",
        "reason": "BOS confirmed with OB retest and hold.",
    }
    config = {
        "tiers": {
            "snipe_it": {"min_score": 85, "min_rr": 3.0},
            "starter":  {"min_score": 75, "min_rr": 3.0},
            "near_entry": {"min_score": 60},
        }
    }
    result = validate(signal, {"veto_flags": []}, config)
    assert result["final_tier"] == "STARTER"
    assert result["safe_for_alert"] is True


# 11-12: JBHT-style valid STARTER still preserved with freshness fields present
def test_jbht_style_starter_still_preserved():
    from src.tiering import validate
    signal = {
        "ticker": "JBHT",
        "tier": "STARTER",
        "score": 78,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "OB",
        "trigger_level": 182.50,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Below OB base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at retest",
        "discord_channel": "#starter-signals",
        "capital_action": "starter_only",
        "reason": "BOS confirmed with OB retest and hold.",
    }
    config = {
        "tiers": {
            "snipe_it": {"min_score": 85, "min_rr": 3.0},
            "starter":  {"min_score": 75, "min_rr": 3.0},
            "near_entry": {"min_score": 60},
        }
    }
    pf = {
        "veto_flags": [],
        "key_features": {"current_price": 182.50},
    }
    result = validate(signal, pf, config)
    assert result["final_tier"] == "STARTER"
    # Phase 11 freshness fields must be present in final_signal
    fs = result["final_signal"]
    assert fs.get("scan_price") == 182.50
    assert fs.get("drift_status") == "snapshot_only"
    assert fs.get("drift_pct") == 0.0
    assert "scan-time" in fs.get("freshness_note", "")
    assert fs.get("price_distance_to_trigger_pct") == 0.0


# 11-13: CRNT-style alert shows snapshot_only with operator verification note
def test_crnt_style_snapshot_only_warns_operator_to_verify_live_chart():
    tr = _tiering_result(
        tier="STARTER",
        ticker="CRNT",
        capital_action="starter_only",
        scan_price=2.50,
        drift_status="snapshot_only",
        freshness_note="Signal based on scan-time price; verify live chart before entry.",
    )
    tr["final_tier"] = "STARTER"
    tr["capital_action"] = "starter_only"
    text = format_alert(tr)
    assert "FRESHNESS" in text
    assert "2.50" in text
    assert "snapshot_only" in text
    assert "verify live chart before entry" in text.lower()


# 11-14: discord_channel still recomputed from final_tier (not Claude's field)
def test_discord_channel_still_recomputed_from_final_tier():
    from src.tiering import validate
    signal = {
        "ticker": "AAPL",
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
        "invalidation_condition": "Below FVG base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at retest",
        "discord_channel": "#near-entry-watch",   # Claude mismatch — must be corrected
        "capital_action": "full_quality_allowed",
        "reason": "Full quality setup.",
    }
    config = {
        "tiers": {
            "snipe_it": {"min_score": 85, "min_rr": 3.0},
            "starter":  {"min_score": 75, "min_rr": 3.0},
            "near_entry": {"min_score": 60},
        }
    }
    result = validate(signal, {"veto_flags": []}, config)
    assert result["final_tier"] == "SNIPE_IT"
    assert result["final_discord_channel"] == "#snipe-signals"
    assert result["final_signal"]["discord_channel"] == "#snipe-signals"


# 11-15: capital_action still recomputed from final_tier (not Claude's field)
def test_capital_action_still_recomputed_from_final_tier():
    from src.tiering import validate
    signal = {
        "ticker": "AAPL",
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
        "invalidation_condition": "Below FVG base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at retest",
        "discord_channel": "#snipe-signals",
        "capital_action": "wait_no_capital",   # Claude mismatch — must be corrected
        "reason": "Full quality setup.",
    }
    config = {
        "tiers": {
            "snipe_it": {"min_score": 85, "min_rr": 3.0},
            "starter":  {"min_score": 75, "min_rr": 3.0},
            "near_entry": {"min_score": 60},
        }
    }
    result = validate(signal, {"veto_flags": []}, config)
    assert result["final_tier"] == "SNIPE_IT"
    assert result["capital_action"] == "full_quality_allowed"
    assert result["final_signal"]["capital_action"] == "full_quality_allowed"


# ===========================================================================
# Phase 12A — Alert Integrity / Sanitized Reason (Discord rendering)
# ===========================================================================

# 12A-D1: Alert uses sanitized_reason when present, not raw reason
def test_12a_alert_uses_sanitized_reason_over_raw():
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        reason="All SNIPE_IT conditions met — execute full quality.",
        sanitized_reason="Starter-quality candidate; full SNIPE confirmation not granted.",
    )
    tr["final_tier"] = "STARTER"
    text = format_alert(tr)
    # sanitized_reason must appear in Why line
    assert "Starter-quality candidate" in text
    # raw SNIPE phrase must NOT appear in Why line
    assert "All SNIPE_IT conditions met" not in text


# 12A-D2: Alert falls back to raw reason when sanitized_reason is None
def test_12a_alert_falls_back_to_raw_reason_when_sanitized_none():
    tr = _tiering_result(
        tier="SNIPE_IT",
        reason="Clean MSS with FVG retest confirmed.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "Clean MSS with FVG retest confirmed." in text


# 12A-D3: NEAR_ENTRY alert does not display capital-positive language from raw reason
def test_12a_near_entry_alert_no_capital_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        reason="Reducing conviction to STARTER tier only.",
        sanitized_reason="Watch-only; confirmation pending.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "STARTER tier only" not in text
    assert "watch-only" in text.lower() or "confirmation pending" in text.lower()


# 12A-D4: SNIPE_IT alert DOES display SNIPE language (no restriction for SNIPE_IT)
def test_12a_snipe_alert_preserves_snipe_language():
    tr = _tiering_result(
        tier="SNIPE_IT",
        reason="All SNIPE_IT conditions met. Zone defended cleanly.",
        sanitized_reason="All SNIPE_IT conditions met. Zone defended cleanly.",
    )
    text = format_alert(tr)
    assert "All SNIPE_IT conditions met" in text


# ===========================================================================
# Phase 12D — Discord Risk Display
# ===========================================================================

# 12D-1: Risk window distance and percentage are both displayed
def test_12d_alert_displays_risk_distance_when_available():
    tr = _tiering_result(
        tier="SNIPE_IT",
        risk_distance=4.30,
        risk_distance_pct=2.356,
    )
    text = format_alert(tr)
    assert "RISK REALISM" in text
    assert "Risk window" in text
    # Numeric values rendered (2 decimals)
    assert "4.30" in text
    assert "2.36%" in text


# 12D-2: Distance to invalidation and percentage are both displayed
def test_12d_alert_displays_distance_to_invalidation_when_available():
    tr = _tiering_result(
        tier="SNIPE_IT",
        current_price_to_invalidation=4.30,
        current_price_to_invalidation_pct=2.356,
    )
    text = format_alert(tr)
    assert "Price" in text and "inval" in text
    assert "4.30" in text
    assert "2.36%" in text


# 12D-3: Risk state and note are displayed in the alert
def test_12d_alert_displays_risk_realism_state_and_note():
    tr = _tiering_result(
        tier="SNIPE_IT",
        risk_realism_state="tight",
        risk_realism_note="Risk window is tight; verify live chart before entry.",
    )
    text = format_alert(tr)
    assert "Risk state" in text
    assert "tight" in text
    assert "Risk note" in text
    assert "Risk window is tight" in text


# 12D-4: When numeric risk fields are None, alert formats cleanly without "None"
def test_12d_alert_hides_missing_risk_numeric_fields_cleanly():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest of FVG at 179.00",
        risk_distance=None,
        risk_distance_pct=None,
        current_price_to_invalidation=None,
        current_price_to_invalidation_pct=None,
        risk_realism_state="unknown",
        risk_realism_note="Risk realism unknown; missing trigger, invalidation, or current price.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    text = format_alert(tr)
    # Alert formats without crash and without rendering "None" strings for numerics
    assert "Risk window:    None" not in text
    assert "Price → inval:  None" not in text
    assert "$None" not in text
    # State and note still display because they are populated
    assert "unknown" in text
    assert "Risk realism unknown" in text


# 12D-5: Sanitized reason is still preferred over raw reason in the alert
def test_12d_alert_still_uses_sanitized_reason():
    tr = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="All SNIPE_IT conditions met — execute at full quality.",
        sanitized_reason="Starter-quality candidate; full SNIPE confirmation not granted.",
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    # Sanitized text wins
    assert "Starter-quality candidate" in text
    # Raw misleading prose must not appear in the Why line
    # (the deterministic "All STARTER conditions met." action label is still allowed,
    #  but the raw claim "All SNIPE_IT conditions met" must not appear)
    assert "All SNIPE_IT conditions met" not in text


# 12D-6: FRESHNESS block is still present after Phase 12D additions
def test_12d_freshness_block_still_present():
    tr = _tiering_result(tier="SNIPE_IT", scan_price=182.50)
    text = format_alert(tr)
    assert "FRESHNESS" in text
    assert "Scan Price:" in text
    assert "snapshot_only" in text


# 12D-7: STARTER alert language must not say "All SNIPE_IT conditions met"
def test_12d_starter_alert_language_still_not_snipe():
    tr = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="Starter-quality candidate; reduced size.",
        sanitized_reason=None,
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    # Deterministic STARTER action label is used; the SNIPE label must not appear
    assert "All SNIPE_IT conditions met" not in text
    assert "STARTER conditions met" in text  # Phase 13.7B contract headline


# ===========================================================================
# Phase 12.1 — NEAR_ENTRY Language Integrity (Discord rendering)
# ===========================================================================

# 12.1-D1: NEAR_ENTRY alert does not render the FORCED PARTICIPATION block,
# even when forced_participation field is a non-empty, non-"none" string.
def test_12_1_near_entry_removes_forced_participation_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        forced_participation="Full quality — zone held cleanly",
        reason="MSS confirmed, zone present, awaiting retest.",
        sanitized_reason="MSS confirmed, zone present, awaiting retest.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    # FORCED PARTICIPATION block must be suppressed for NEAR_ENTRY
    assert "FORCED PARTICIPATION" not in text


# 12.1-D2: NEAR_ENTRY alert always shows NO CAPITAL — WATCH ONLY label
def test_12_1_near_entry_keeps_no_capital_action():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest of FVG at 179.00",
        reason="Zone valid — awaiting retest.",
        sanitized_reason="Zone valid — awaiting retest.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "NO CAPITAL" in text
    assert "WATCH ONLY" in text


# 12.1-D3: STARTER alert still renders FORCED PARTICIPATION when set
def test_12_1_starter_forced_participation_still_renders():
    tr = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        forced_participation="Reduced-size entry — zone quality partial",
        reason="Partial zone interaction.",
        sanitized_reason="Partial zone interaction.",
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    assert "FORCED PARTICIPATION" in text
    assert "Reduced-size entry" in text


# 12.1-D4: SNIPE_IT alert still renders FORCED PARTICIPATION when set
def test_12_1_snipe_forced_participation_still_renders():
    tr = _tiering_result(
        tier="SNIPE_IT",
        forced_participation="Full quality — zone held cleanly",
        reason="Clean MSS with FVG retest confirmed.",
        sanitized_reason="Clean MSS with FVG retest confirmed.",
    )
    text = format_alert(tr)
    assert "FORCED PARTICIPATION" in text
    assert "Full quality" in text


# ===========================================================================
# Phase 12.2 — Final-Tier Language Sovereignty (Discord rendering)
# ===========================================================================

# 12.2-D1: NEAR_ENTRY alert Why line does not render SNIPE_IT language
def test_12_2_near_entry_alert_does_not_render_snipe_language():
    # sanitized_reason carries already-cleaned text (as tiering.validate() produces).
    # Phase 13.6B: old "Watchlist only until retest and hold confirm." is now also a
    # banned phrase — use the current replacement text "Watch-only; no capital."
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        reason="All SNIPE_IT conditions satisfied.",
        sanitized_reason="Watch-only; no capital.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "snipe_it" not in text.lower()
    assert "all snipe_it conditions" not in text.lower()
    assert "watch-only" in text.lower() or "no capital" in text.lower()


# 12.2-D2: NEAR_ENTRY alert Why line does not render "entry valid"
def test_12_2_near_entry_alert_does_not_render_entry_valid():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        reason="Zone defended — entry valid while zone holds.",
        sanitized_reason="Zone defended — Watchlist only until retest and hold confirm. while zone holds.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "entry valid" not in text.lower()


# 12.2-D3: NEAR_ENTRY alert always shows NO CAPITAL — WATCH ONLY
def test_12_2_near_entry_alert_keeps_no_capital_watch_only():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Confirmed retest of FVG",
        reason="Zone valid — awaiting retest.",
        sanitized_reason="Zone valid — awaiting retest.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "NO CAPITAL" in text
    assert "WATCH ONLY" in text


# 12.2-D4: STARTER alert Why line uses STARTER not SNIPE language
def test_12_2_starter_alert_uses_starter_not_snipe_language():
    tr = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="All SNIPE_IT conditions satisfied.",
        sanitized_reason="All STARTER conditions met.",
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    # Why line should show STARTER replacement, not SNIPE
    assert "snipe_it" not in text.lower()
    assert "all starter conditions met" in text.lower()


# 12.2-D5: SNIPE_IT alert preserves SNIPE language
def test_12_2_snipe_alert_preserves_snipe_language():
    tr = _tiering_result(
        tier="SNIPE_IT",
        reason="All SNIPE_IT conditions satisfied. Zone defended cleanly.",
        sanitized_reason="All SNIPE_IT conditions satisfied. Zone defended cleanly.",
    )
    text = format_alert(tr)
    assert "all snipe_it conditions satisfied" in text.lower()


# 12.2-D6: Phase 12.1 tests still pass after Phase 12.2 additions
def test_12_2_existing_12_1_tests_still_pass():
    # 12.1-D1: FORCED PARTICIPATION suppressed for NEAR_ENTRY
    tr_ne = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        forced_participation="Full quality — zone held cleanly",
        reason="MSS confirmed, zone present, awaiting retest.",
        sanitized_reason="MSS confirmed, zone present, awaiting retest.",
    )
    tr_ne["final_tier"] = "NEAR_ENTRY"
    tr_ne["capital_action"] = "wait_no_capital"
    tr_ne["final_discord_channel"] = "#near-entry-watch"
    text_ne = format_alert(tr_ne)
    assert "FORCED PARTICIPATION" not in text_ne

    # 12.1-D3: STARTER still renders FORCED PARTICIPATION
    tr_st = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        forced_participation="Reduced-size entry — zone quality partial",
        reason="Partial zone interaction.",
        sanitized_reason="Partial zone interaction.",
    )
    tr_st["final_tier"] = "STARTER"
    tr_st["final_discord_channel"] = "#starter-signals"
    text_st = format_alert(tr_st)
    assert "FORCED PARTICIPATION" in text_st


# ===========================================================================
# Phase 12.3 — NEAR_ENTRY Blocker Explanation Integrity + STARTER Wording
# ===========================================================================

# 12.3-D1: NEAR_ENTRY alert renders Blocker line
def test_12_3_near_entry_alert_renders_blocker_note():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Full zone retest with hold confirmation.",
        reason="Zone valid — awaiting retest.",
        sanitized_reason="Zone valid — awaiting retest.",
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        ),
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "Blocker:" in text
    assert "retest is not fully confirmed" in text


# 12.3-D2: NEAR_ENTRY alert does not render "Missing conditions: —"
def test_12_3_near_entry_alert_missing_conditions_not_blank():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["trigger_acceptance — price is below trigger"],
        upgrade_trigger="Price reclaims and holds above trigger with body-close confirmation.",
        reason="Zone valid.",
        sanitized_reason="Zone valid.",
        near_entry_blocker_note=(
            "Blocker: price is below trigger; wait for reclaim and hold above trigger."
        ),
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "Missing conditions: —" not in text
    # Phase 13.7D: raw "trigger_acceptance" label is now humanized — verify the
    # description part ("price is below trigger") is present instead.
    assert "trigger_acceptance" not in text.lower()
    assert "price is below trigger" in text.lower()


# 12.3-D3: NEAR_ENTRY alert does not render "Upgrade trigger:    none"
def test_12_3_near_entry_alert_upgrade_trigger_not_none():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_missing"],
        upgrade_trigger="Full zone retest confirmed with body-close hold.",
        reason="Zone valid.",
        sanitized_reason="Zone valid.",
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        ),
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "Upgrade trigger:    none" not in text
    assert "Full zone retest" in text


# 12.3-D4: NEAR_ENTRY alert does not render "enter on confirmed close" language
def test_12_3_near_entry_alert_no_enter_on_confirmed_close_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Full retest confirmation required.",
        reason="Zone valid — enter on confirmed close above trigger.",
        sanitized_reason="Zone valid — watch for confirmed close above trigger.",
        near_entry_blocker_note="Blocker: retest is not fully confirmed.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "enter on confirmed close" not in text.lower()


# 12.3-D5: NEAR_ENTRY alert does not render "stop below" language
def test_12_3_near_entry_alert_no_stop_below_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Full retest confirmation required.",
        reason="Zone valid — stop below 178.00.",
        sanitized_reason="Zone valid — invalidation reference below 178.00.",
        near_entry_blocker_note="Blocker: retest is not fully confirmed.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "stop below" not in text.lower()


# 12.3-D6: STARTER alert does not contain "full SNIPE confirmation not granted"
def test_12_3_starter_alert_replaces_snipe_denial_language():
    tr = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="Setup satisfies all SNIPE_IT criteria.",
        sanitized_reason="Starter-quality candidate; full-size confirmation not granted.",
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    assert "full snipe confirmation not granted" not in text.lower()
    assert "full-size confirmation not granted" in text.lower()


# 12.3-D7: STARTER and SNIPE_IT alerts do not render near_entry_blocker_note
def test_12_3_starter_and_snipe_alerts_do_not_render_near_entry_blocker():
    tr_st = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="Starter quality setup.",
        sanitized_reason="Starter quality setup.",
    )
    tr_st["final_tier"] = "STARTER"
    tr_st["final_discord_channel"] = "#starter-signals"
    text_st = format_alert(tr_st)
    assert "Blocker:" not in text_st

    tr_sn = _tiering_result(
        tier="SNIPE_IT",
        reason="Clean MSS with FVG retest confirmed.",
        sanitized_reason="Clean MSS with FVG retest confirmed.",
    )
    text_sn = format_alert(tr_sn)
    assert "Blocker:" not in text_sn


# 12.3-D8: Phase 12.2 language regressions still pass
def test_12_3_phase_12_2_language_tests_still_pass():
    from src.tiering import _sanitize_reason_for_tier

    # 12.2 regression: NEAR_ENTRY removes SNIPE language
    dirty = "All SNIPE_IT conditions satisfied."
    clean = _sanitize_reason_for_tier(dirty, "NEAR_ENTRY")
    assert "snipe_it" not in clean.lower()
    assert "watch-only" in clean.lower() or "no capital" in clean.lower()

    # Render in alert — NEAR_ENTRY with pre-cleaned sanitized_reason.
    # Phase 13.6B: old "Watchlist only until retest and hold confirm." is now a
    # banned phrase in the guard; use the current replacement text instead.
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Close above trigger with hold.",
        reason="All SNIPE_IT conditions satisfied.",
        sanitized_reason="Watch-only; no capital.",
        near_entry_blocker_note="Blocker: retest is not fully confirmed.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "all snipe_it conditions" not in text.lower()
    assert "watch-only" in text.lower() or "no capital" in text.lower()

    # 12.2 regression: STARTER alert uses STARTER not SNIPE language
    tr2 = _tiering_result(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="All SNIPE_IT conditions satisfied.",
        sanitized_reason="All STARTER conditions met.",
    )
    tr2["final_tier"] = "STARTER"
    tr2["final_discord_channel"] = "#starter-signals"
    text2 = format_alert(tr2)
    assert "all snipe_it conditions" not in text2.lower()
    assert "all starter conditions met" in text2.lower()


# ===========================================================================
# Phase 12.3A — Clean Near-Entry Blocker Rendering
# ===========================================================================

_C_SIGNAL = {
    "ticker": "C",
    "timestamp_et": "2025-01-15T10:30:00-05:00",
    "tier": "NEAR_ENTRY",
    "score": 87,
    "setup_family": "continuation",
    "structure_event": "MSS",
    "trend_state": "fresh_expansion",
    "sma_value_alignment": "supportive",
    "zone_type": "FVG",
    "trigger_level": 128.44,
    "retest_status": "confirmed",
    "hold_status": "confirmed",
    "invalidation_condition": "Daily close below FVG base",
    "invalidation_level": None,
    "targets": [{"label": "T1", "level": 140.0, "reason": "Prior swing"}],
    "risk_reward": 4.60,
    "overhead_status": "moderate",
    "forced_participation": "none",
    "missing_conditions": [],
    "upgrade_trigger": "none",
    "next_action": "Watch for reclaim above trigger.",
    "discord_channel": "#near-entry-watch",
    "capital_action": "wait_no_capital",
    "reason": "Zone valid — awaiting trigger acceptance.",
}
_C_PF = {"veto_flags": [], "key_features": {"current_price": 128.35}}
_C_CONFIG = {
    "tiers": {
        "snipe_it": {"min_score": 85, "min_rr": 3.0},
        "starter": {"min_score": 75, "min_rr": 3.0},
        "near_entry": {"min_score": 60},
    }
}


# 12.3A-7: Rendered alert does not show double Blocker: prefix
def test_12_3a_alert_no_double_blocker_prefix():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=87,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["trigger_acceptance — price is below trigger"],
        upgrade_trigger="Price reclaims and holds above trigger with body-close confirmation.",
        reason="Zone valid.",
        sanitized_reason="Zone valid.",
        near_entry_blocker_note=(
            "Blocker: price is below trigger; wait for reclaim and hold above trigger."
        ),
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    # Blocker label appears exactly once; note text is present without double prefix
    assert "Blocker:" in text
    assert "price is below trigger" in text
    assert "Blocker: Blocker:" not in text


# 12.3A-8: _clean_blocker_label strips one or more leading "Blocker:" prefixes
def test_12_3a_clean_blocker_label_strips_prefix():
    assert _clean_blocker_label("Blocker: price is below trigger.") == "price is below trigger."
    assert _clean_blocker_label("Blocker:price is below trigger.") == "price is below trigger."
    assert _clean_blocker_label("Blocker: Blocker: X") == "X"
    assert _clean_blocker_label("blocker: Blocker: X") == "X"
    assert _clean_blocker_label("no prefix here") == "no prefix here"
    assert _clean_blocker_label("") == ""
    assert _clean_blocker_label(None) == ""


# 12.3A-9: C-style alert does not render "Missing conditions: —"
def test_12_3a_alert_missing_conditions_not_dash_for_below_trigger():
    from src.tiering import validate as tiering_validate

    result = tiering_validate(dict(_C_SIGNAL), _C_PF, _C_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    text = format_alert(result)
    assert "Missing conditions: —" not in text
    # Phase 13.7D: raw "trigger_acceptance" label is now humanized — verify the
    # description part ("price is below trigger" or "price is below") is present.
    assert "trigger_acceptance" not in text.lower()
    assert "price is below" in text.lower() or "below trigger" in text.lower()


# 12.3A-10: C-style alert does not render "Upgrade trigger:    none"
def test_12_3a_alert_upgrade_trigger_not_none_for_below_trigger():
    from src.tiering import validate as tiering_validate

    result = tiering_validate(dict(_C_SIGNAL), _C_PF, _C_CONFIG)
    assert result["final_tier"] == "NEAR_ENTRY"
    text = format_alert(result)
    assert "Upgrade trigger:    none" not in text
    assert "reclaims" in text.lower() or "trigger" in text.lower()


# 12.3A-11: NEAR_ENTRY alert does not render "manage position" language
def test_12_3a_alert_no_manage_position_language():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_status"],
        upgrade_trigger="Full zone retest with hold confirmation.",
        reason="Zone held — manage position if price attempts trigger.",
        sanitized_reason="Zone held — No position management until capital is authorized.",
        next_action="Watch zone — manage position if price attempts breakout.",
        sanitized_next_action=(
            "Watch zone — No position management until capital is authorized."
        ),
        near_entry_blocker_note="Blocker: retest is not fully confirmed.",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    # Phase 12.3A: "manage position" is removed upstream by tiering sanitizer
    assert "manage position" not in text.lower()
    # Phase 13.7B: "no position management until capital is authorized" is now itself a
    # forbidden NEAR_ENTRY phrase — the contract guard replaces it with the watch fallback.
    assert "no position management" not in text.lower()
    assert "capital is authorized" not in text.lower()
    # Replacement must be watch-safe language
    assert "watch-only" in text.lower() or "blocker resolution" in text.lower()


# 12.3A-12: PVH STARTER preserved; Phase 12.3 and 12.2 language regressions pass
def test_12_3a_pvh_starter_language_preserved():
    from src.tiering import _sanitize_reason_for_tier

    # PVH STARTER: STARTER SIZE ONLY, full-size confirmation not granted, no Blocker:
    tr_pvh = _tiering_result(
        tier="STARTER",
        score=82,
        capital_action="starter_only",
        reason="Setup satisfies all SNIPE_IT criteria.",
        sanitized_reason="Starter-quality candidate; full-size confirmation not granted.",
    )
    tr_pvh["final_tier"] = "STARTER"
    tr_pvh["final_discord_channel"] = "#starter-signals"
    text_pvh = format_alert(tr_pvh)
    assert "STARTER SIZE ONLY" in text_pvh
    assert "full-size confirmation not granted" in text_pvh.lower()
    assert "Blocker:" not in text_pvh

    # Phase 12.3 regression: NEAR_ENTRY blocker note present but not double-prefixed
    tr_ne = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["retest_not_confirmed"],
        upgrade_trigger="Full zone retest with hold.",
        reason="Zone valid.",
        sanitized_reason="Zone valid.",
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        ),
    )
    tr_ne["final_tier"] = "NEAR_ENTRY"
    tr_ne["final_discord_channel"] = "#near-entry-watch"
    text_ne = format_alert(tr_ne)
    assert "Blocker:" in text_ne
    assert "Blocker: Blocker:" not in text_ne

    # Phase 12.2 regression: NEAR_ENTRY removes SNIPE language from reason
    clean = _sanitize_reason_for_tier("All SNIPE_IT conditions satisfied.", "NEAR_ENTRY")
    assert "snipe_it" not in clean.lower()


# ---------------------------------------------------------------------------
# Exit strategy tests
# ---------------------------------------------------------------------------

def test_snipe_it_exit_strategy_renders_tp1_tp2_tp3():
    """SNIPE_IT alert with T1/T2/T3 targets renders TP1, TP2, TP3 and hard stop."""
    tr = _tiering_result(
        tier="SNIPE_IT",
        score=88,
        targets=[
            {"label": "T1", "level": 195.00, "reason": "Prior swing high"},
            {"label": "T2", "level": 204.50, "reason": "Range extension"},
            {"label": "T3", "level": 215.00, "reason": "HTF target"},
        ],
        invalidation_level=178.20,
        invalidation_condition="Daily close below FVG base",
    )
    text = format_alert(tr)
    assert "EXIT STRATEGY" in text
    assert "TP1: 195.00" in text
    assert "TP2: 204.50" in text
    assert "TP3: 215.00" in text
    assert "178.20" in text
    assert "Hard stop:" in text
    assert "Trail:" in text


def test_missing_tp2_tp3_shows_dash_not_invented():
    """When only T1 is present, TP2 and TP3 show '—' and no values are invented."""
    tr = _tiering_result(
        tier="SNIPE_IT",
        score=88,
        targets=[{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        invalidation_level=178.20,
    )
    text = format_alert(tr)
    assert "EXIT STRATEGY" in text
    assert "TP1: 195.00" in text
    # TP2 and TP3 must show dash, not an invented number
    assert "TP2: —" in text
    assert "TP3: —" in text


def test_starter_exit_strategy_uses_reduced_size_language():
    """STARTER alert shows starter-appropriate exit language (no full-size references)."""
    tr = _tiering_result(
        tier="STARTER",
        score=80,
        targets=[
            {"label": "T1", "level": 195.00, "reason": "Prior swing high"},
            {"label": "T2", "level": 204.50, "reason": "Range extension"},
        ],
        invalidation_level=178.20,
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    assert "EXIT STRATEGY" in text
    assert "TP1: 195.00" in text
    assert "TP2: 204.50" in text
    assert "starter size" in text.lower()
    assert "Hard stop:" in text
    # Must not claim full capital authorization
    assert "capital authorized" not in text.lower()


def test_near_entry_exit_strategy_conditional_no_capital():
    """NEAR_ENTRY alert shows conditional exit plan with no capital language."""
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        missing_conditions=["missing_retest"],
        upgrade_trigger="Full zone retest with hold.",
        targets=[{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        invalidation_level=178.20,
        invalidation_condition="Below zone low",
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "EXIT STRATEGY" in text
    assert "conditional" in text.lower()
    assert "no capital" in text.lower()
    assert "TP1 reference" in text
    assert "Hard stop reference" in text
    # Must not use full-capital language
    assert "capital authorized" not in text.lower()


# ---------------------------------------------------------------------------
# Phase 14A: Entry Grade Engine tests
# ---------------------------------------------------------------------------

def _grade_signal(**overrides) -> dict:
    """Minimal signal dict for _classify_entry_grade unit tests."""
    base = {
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "entry_acceptance": "accepted",
        "risk_realism_state": "healthy",
        "overhead_status": "clear",
        "risk_reward": 3.5,
        "price_distance_to_trigger_pct": 0.3,
    }
    base.update(overrides)
    return base


# ---- Grade law: F cap (non-negotiable) ----

def test_entry_grade_f_no_confirmed_retest():
    """retest_status != confirmed → F regardless of other conditions."""
    grade = _classify_entry_grade(_grade_signal(retest_status="partial"), "SNIPE_IT")
    assert grade == _ENTRY_GRADE_LABELS["F_GRADE"]
    assert "F" in grade


def test_entry_grade_f_no_confirmed_hold():
    """hold_status != confirmed → F regardless of other conditions."""
    grade = _classify_entry_grade(_grade_signal(hold_status="missing"), "SNIPE_IT")
    assert grade == _ENTRY_GRADE_LABELS["F_GRADE"]
    assert "F" in grade


def test_entry_grade_f_both_unconfirmed():
    """Both retest and hold missing → F."""
    grade = _classify_entry_grade(
        _grade_signal(retest_status="missing", hold_status="missing"), "STARTER"
    )
    assert "F" in grade


# ---- Grade law: C cap ----

def test_entry_grade_c_price_below_trigger():
    """entry_acceptance=damaging (price below trigger) → C."""
    grade = _classify_entry_grade(
        _grade_signal(entry_acceptance="damaging"), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["C_GRADE"]
    assert "C" in grade


def test_entry_grade_c_price_invalidated():
    """entry_acceptance=invalidated (price at/below stop) → C."""
    grade = _classify_entry_grade(
        _grade_signal(entry_acceptance="invalidated"), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["C_GRADE"]
    assert "C" in grade


def test_entry_grade_f_takes_priority_over_c():
    """F cap fires before C — missing retest + damaging acceptance → F."""
    grade = _classify_entry_grade(
        _grade_signal(retest_status="failed", entry_acceptance="damaging"), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["F_GRADE"]


# ---- Grade law: B hard ceilings ----

def test_entry_grade_b_unproven_acceptance():
    """entry_acceptance=unproven → B_UNPROVEN ceiling."""
    grade = _classify_entry_grade(
        _grade_signal(entry_acceptance="unproven"), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["B_UNPROVEN"]
    assert "B" in grade


def test_entry_grade_b_fragile_risk_window():
    """risk_realism_state=fragile → B_FRAGILE ceiling even with high rr."""
    grade = _classify_entry_grade(
        _grade_signal(risk_realism_state="fragile", risk_reward=5.0), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["B_FRAGILE"]
    assert "B" in grade


def test_entry_grade_b_overhead_blocked():
    """overhead_status=blocked → B_OVERHEAD ceiling."""
    grade = _classify_entry_grade(
        _grade_signal(overhead_status="blocked"), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["B_OVERHEAD"]
    assert "B" in grade


def test_entry_grade_b_chasing_extension():
    """price_distance_to_trigger_pct > 2.0 → B_CHASING ceiling."""
    grade = _classify_entry_grade(
        _grade_signal(price_distance_to_trigger_pct=3.5, risk_reward=4.5), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["B_CHASING"]
    assert "B" in grade


def test_entry_grade_b_chasing_boundary_exactly_2pct():
    """price_distance_to_trigger_pct == 2.0 does NOT trigger B_CHASING (> 2.0 required)."""
    grade = _classify_entry_grade(
        _grade_signal(price_distance_to_trigger_pct=2.0, risk_reward=4.5), "SNIPE_IT"
    )
    assert grade != _ENTRY_GRADE_LABELS["B_CHASING"]


# ---- Grade law: A and A+ ----

def test_entry_grade_a_confirmed_healthy_rr3():
    """All confirmed, healthy risk, rr=3.2, moderate overhead → A."""
    grade = _classify_entry_grade(
        _grade_signal(
            risk_reward=3.2,
            overhead_status="moderate",
            price_distance_to_trigger_pct=1.0,
        ),
        "SNIPE_IT",
    )
    assert grade == _ENTRY_GRADE_LABELS["A_GRADE"]
    assert "A" in grade
    assert "A+" not in grade


def test_entry_grade_a_plus_sniper_conditions():
    """All A+ conditions met → A+."""
    grade = _classify_entry_grade(
        _grade_signal(
            risk_reward=4.5,
            overhead_status="clear",
            risk_realism_state="healthy",
            price_distance_to_trigger_pct=0.2,
        ),
        "SNIPE_IT",
    )
    assert grade == _ENTRY_GRADE_LABELS["A_PLUS"]
    assert "A+" in grade


def test_entry_grade_a_plus_blocked_by_rr_below_4():
    """rr=3.9 (< 4.0) blocks A+; falls to A when other A conditions are met."""
    grade = _classify_entry_grade(
        _grade_signal(
            risk_reward=3.9,
            overhead_status="clear",
            price_distance_to_trigger_pct=0.2,
        ),
        "SNIPE_IT",
    )
    assert grade == _ENTRY_GRADE_LABELS["A_GRADE"]


def test_entry_grade_b_default_when_rr_below_3():
    """rr < 3.0 → B default (no A or A+ possible)."""
    grade = _classify_entry_grade(
        _grade_signal(risk_reward=2.5), "SNIPE_IT"
    )
    assert grade == _ENTRY_GRADE_LABELS["B_DEFAULT"]
    assert "B" in grade


# ---- NEAR_ENTRY tier cap ----

def test_entry_grade_near_entry_caps_at_b_not_a():
    """NEAR_ENTRY tier gate caps grade at B_WATCH even when conditions are perfect."""
    grade = _classify_entry_grade(
        _grade_signal(risk_reward=4.5, price_distance_to_trigger_pct=0.1),
        "NEAR_ENTRY",
    )
    assert grade == _ENTRY_GRADE_LABELS["B_WATCH"]
    assert "B" in grade
    assert "A" not in grade


def test_entry_grade_near_entry_f_fires_before_b_watch():
    """NEAR_ENTRY with missing retest → F fires before B_WATCH cap."""
    grade = _classify_entry_grade(
        _grade_signal(retest_status="missing"),
        "NEAR_ENTRY",
    )
    assert grade == _ENTRY_GRADE_LABELS["F_GRADE"]


# ---- WAIT tier ----

def test_entry_grade_wait_returns_empty_string():
    """WAIT tier → empty string (entry grade must not be rendered)."""
    assert _classify_entry_grade(_grade_signal(), "WAIT") == ""


# ---- Integration: format_alert renders entry grade ----

def test_entry_grade_renders_in_action_section():
    """format_alert() includes 'Entry grade:' in the ACTION section."""
    tr = _tiering_result(
        tier="SNIPE_IT",
        score=90,
        entry_acceptance="accepted",
        risk_realism_state="healthy",
        risk_reward=3.5,
        overhead_status="clear",
        price_distance_to_trigger_pct=0.3,
    )
    text = format_alert(tr)
    assert "Entry grade:" in text
    action_idx    = text.index("ACTION")
    entry_idx     = text.index("Entry grade:")
    freshness_idx = text.index("FRESHNESS")
    assert entry_idx > action_idx, "Entry grade must appear after ACTION header"
    assert entry_idx < freshness_idx, "Entry grade must appear before FRESHNESS"


def test_entry_grade_not_rendered_for_wait():
    """WAIT tier alerts must not contain 'Entry grade:'."""
    tr = _tiering_result(tier="WAIT", score=0, safe=False)
    tr["final_tier"] = "WAIT"
    tr["safe_for_alert"] = False
    tr["final_signal"]["tier"] = "WAIT"
    tr["final_signal"]["capital_action"] = "no_trade"
    text = format_alert(tr)
    assert "Entry grade:" not in text


# ---- Guard pass tests ----

def test_entry_grade_phrase_passes_contract_guard_snipe_it():
    """A+ entry grade phrase survives SNIPE_IT contract and sovereignty guards."""
    tr = _tiering_result(
        tier="SNIPE_IT",
        score=92,
        entry_acceptance="accepted",
        risk_realism_state="healthy",
        risk_reward=4.5,
        overhead_status="clear",
        price_distance_to_trigger_pct=0.2,
    )
    text = format_alert(tr)
    assert "Entry grade:" in text
    entry_line = next(l for l in text.split("\n") if "Entry grade:" in l)
    assert "A+" in entry_line, f"A+ grade corrupted by guard: {entry_line!r}"


def test_entry_grade_phrase_passes_contract_guard_starter():
    """A entry grade phrase survives STARTER contract and sovereignty guards."""
    tr = _tiering_result(
        tier="STARTER",
        score=80,
        entry_acceptance="accepted",
        risk_realism_state="healthy",
        risk_reward=3.2,
        overhead_status="moderate",
        price_distance_to_trigger_pct=0.8,
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    tr["final_signal"]["tier"] = "STARTER"
    tr["final_signal"]["capital_action"] = "starter_only"
    text = format_alert(tr)
    assert "Entry grade:" in text
    entry_line = next(l for l in text.split("\n") if "Entry grade:" in l)
    assert "A" in entry_line, f"A grade corrupted by guard: {entry_line!r}"
    assert "A+" not in entry_line


def test_entry_grade_phrase_passes_contract_guard_near_entry():
    """F entry grade phrase survives NEAR_ENTRY contract and sovereignty guards."""
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        score=65,
        safe=True,
        capital_action="wait_no_capital",
        retest_status="missing",
        hold_status="missing",
        missing_conditions=["missing_retest", "missing_hold"],
        upgrade_trigger="Full zone retest with hold.",
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed; "
            "wait for full zone interaction and hold."
        ),
    )
    tr["final_tier"] = "NEAR_ENTRY"
    tr["final_discord_channel"] = "#near-entry-watch"
    tr["final_signal"]["tier"] = "NEAR_ENTRY"
    tr["final_signal"]["capital_action"] = "wait_no_capital"
    text = format_alert(tr)
    assert "Entry grade:" in text
    entry_line = next(l for l in text.split("\n") if "Entry grade:" in l)
    assert "F" in entry_line, f"F grade corrupted by guard: {entry_line!r}"
    assert "full quality" not in text.lower()


# ===========================================================================
# Phase 1C-P1 — Break & Retest doctrine organs must NOT change alert format
# ===========================================================================

_BRT_PAYLOAD = {
    "entry_family":             "failed_break_conversion",
    "retest_quality":           "overlap",
    "consumption_risk":         "high",
    "level_authority":          "weak",
    "zone_freshness":           "consumed",
    "break_retest_state":       "trigger_pending",
    "one_hour_momentum_repair": "deferred_requires_1h",
}


def test_format_alert_does_not_render_brt_field_names():
    # The doctrine organs are evidence-only; their field names must never appear
    # as rendered labels in the alert body.
    tr = _tiering_result(**_BRT_PAYLOAD)
    text = format_alert(tr).lower()
    for field in _BRT_PAYLOAD:
        assert field not in text, (
            f"BRT field name {field!r} leaked into rendered alert"
        )


def test_format_alert_does_not_render_brt_values():
    # Distinctive BRT label values must not appear in the rendered alert body.
    tr = _tiering_result(**_BRT_PAYLOAD)
    text = format_alert(tr).lower()
    for value in ("failed_break_conversion", "consumed", "trigger_pending",
                  "deferred_requires_1h", "zone_freshness", "consumption_risk"):
        assert value not in text, f"BRT value {value!r} leaked into rendered alert"


def test_format_alert_identical_with_and_without_brt_fields():
    # Rendering must be byte-identical whether or not BRT evidence is attached.
    tr_without = _tiering_result()
    tr_with = _tiering_result(**_BRT_PAYLOAD)
    assert format_alert(tr_with) == format_alert(tr_without), (
        "BRT evidence changed the rendered alert body"
    )


def test_format_alert_brt_does_not_break_wait_suppression():
    # A WAIT-equivalent unsafe result carrying BRT evidence still produces no
    # actionable render path change (format_alert is only called for sendable
    # tiers, but the body must not surface BRT data even if invoked).
    tr = _tiering_result(tier="NEAR_ENTRY", **_BRT_PAYLOAD)
    tr["final_tier"] = "NEAR_ENTRY"
    tr["final_discord_channel"] = "#near-entry-watch"
    tr["final_signal"]["tier"] = "NEAR_ENTRY"
    tr["final_signal"]["capital_action"] = "wait_no_capital"
    text = format_alert(tr).lower()
    assert "break_retest_state" not in text
    assert "consumption_risk" not in text


# ===========================================================================
# Phase 1D — Market Structure State storage was evidence-only.
# Phase 1E SUPERSEDES the Phase 1D "display-neutral" contract: the scanner
# state is now rendered in the alert body as a human-facing truth layer.
# The raw snake_case field name must still never appear (label is "Market
# State:"), but the state VALUE is now intentionally surfaced.
# ===========================================================================

_MKTSTATE_PAYLOAD = {
    "market_structure_state": "FAILURE",
}


def test_format_alert_does_not_render_mktstate_field_name():
    # The raw snake_case field name must never appear as a rendered label.
    tr = _tiering_result(**_MKTSTATE_PAYLOAD)
    text = format_alert(tr).lower()
    assert "market_structure_state" not in text, (
        "raw market_structure_state field name leaked into rendered alert"
    )


# ===========================================================================
# Phase 1E — Human-facing State Truth Layer (display-only)
# ===========================================================================

def test_1e_renders_market_state_when_present():
    # 1: Market State appears in the alert when market_structure_state is set.
    tr = _tiering_result(market_structure_state="REPAIR")
    text = format_alert(tr)
    assert "Market State: REPAIR" in text, (
        f"Market State not rendered; alert body:\n{text}"
    )


def test_1e_does_not_render_market_state_when_absent():
    # 2: When the field is missing, the trend/zone line is the legacy format and
    # no Market State label appears.
    tr = _tiering_result()  # no market_structure_state key
    tr["final_signal"].pop("market_structure_state", None)
    text = format_alert(tr)
    assert "Market State" not in text, "Market State rendered when field absent"
    assert "Trend: fresh_expansion  |  Zone: FVG" in text, (
        "Legacy trend/zone line changed when market_structure_state absent"
    )


def test_1e_does_not_render_market_state_when_none():
    # 2b: None value is treated as absent (falsy) → legacy output.
    tr = _tiering_result(market_structure_state=None)
    text = format_alert(tr)
    assert "Market State" not in text
    assert "Trend: fresh_expansion  |  Zone: FVG" in text


def test_1e_display_does_not_change_final_tier():
    # 3: format_alert is display-only — it must not mutate final_tier.
    tr = _tiering_result(tier="SNIPE_IT", market_structure_state="FAILURE")
    before = tr["final_tier"]
    _ = format_alert(tr)
    assert tr["final_tier"] == before == "SNIPE_IT"


def test_1e_display_does_not_change_capital_action():
    # 4: format_alert must not mutate capital_action.
    tr = _tiering_result(market_structure_state="COMPRESSION")
    before = tr["capital_action"]
    _ = format_alert(tr)
    assert tr["capital_action"] == before


def test_1e_display_does_not_change_final_discord_channel():
    # 5: format_alert must not mutate final_discord_channel.
    tr = _tiering_result(market_structure_state="TRANSITION")
    before = tr["final_discord_channel"]
    _ = format_alert(tr)
    assert tr["final_discord_channel"] == before == "#snipe-signals"


def test_1e_wait_still_never_posts():
    # 6: A WAIT result carrying any market_structure_state remains unsendable.
    # _sendable() is the gate; Market State display must not flip it.
    for state in ("EXPANSION", "REPAIR", "FAILURE", "UNKNOWN"):
        tr = _tiering_result(tier="WAIT", safe=False, market_structure_state=state)
        tr["final_tier"] = "WAIT"
        tr["final_discord_channel"] = "none"
        sendable, reason = _sendable(tr, None)
        assert sendable is False, (
            f"WAIT became sendable with market_structure_state={state!r}"
        )
        assert reason == "wait_no_alert"


def test_1e_roku_style_fresh_expansion_corrected_by_repair():
    # 7: ROKU-style — Claude says fresh_expansion, scanner says REPAIR.
    # Both must render side by side; tier is unchanged (still SNIPE_IT).
    tr = _tiering_result(
        tier="SNIPE_IT",
        trend_state="fresh_expansion",
        market_structure_state="REPAIR",
    )
    text = format_alert(tr)
    assert "Trend: fresh_expansion" in text, "Claude trend_state must remain visible"
    assert "Market State: REPAIR" in text, "Scanner truth layer must be visible"
    # The corrected line shows both, in order, on the same row.
    assert "Trend: fresh_expansion  |  Market State: REPAIR  |  Zone: FVG" in text
    # Display did not change the decision.
    assert tr["final_tier"] == "SNIPE_IT"


def test_1e_no_brt_or_vcp_fields_render():
    # 8: Promoting market_structure_state must not surface any BRT/VCP organ.
    tr = _tiering_result(
        market_structure_state="EXPANSION",
        entry_family="failed_break_conversion",
        consumption_risk="high",
        break_retest_state="trigger_pending",
        zone_freshness="consumed",
        vcp_status="CONFIRMED",
        vcp_contraction_sequence="3-2-1",
    )
    text = format_alert(tr).lower()
    for leaked in ("entry_family", "consumption_risk", "break_retest_state",
                   "zone_freshness", "failed_break_conversion", "trigger_pending",
                   "vcp_status", "vcp_contraction_sequence", "3-2-1"):
        assert leaked not in text, f"unapproved field {leaked!r} leaked into alert"
    # Market State itself is the only newly-surfaced organ (text is lowercased).
    assert "market state: expansion" in text


# ===========================================================================
# Phase 14A — Weekly Sovereignty context (display-only)
# ===========================================================================

_WEEKLY_DISPLAY_PAYLOAD = {
    "weekly_sma_alignment":     "supportive",
    "weekly_trend_state":       "advancing",
    "weekly_alignment_context": "partial_alignment",
}


def test_14a_renders_weekly_context_when_present():
    # 28: weekly context line appears when weekly fields are present.
    tr = _tiering_result(**_WEEKLY_DISPLAY_PAYLOAD)
    text = format_alert(tr)
    assert "Weekly: advancing / supportive  |  Alignment: partial_alignment" in text, (
        f"weekly context not rendered; alert body:\n{text}"
    )


def test_14a_omits_weekly_context_when_absent():
    # 29: when weekly fields are missing, no weekly line appears and the daily
    # trend/zone line is unchanged.
    tr = _tiering_result()
    for f in ("weekly_sma_alignment", "weekly_trend_state", "weekly_alignment_context"):
        tr["final_signal"].pop(f, None)
    text = format_alert(tr)
    assert "Weekly:" not in text, "weekly line rendered when all weekly fields absent"
    assert "Alignment:" not in text


def test_14a_omits_weekly_context_when_none():
    # 29b: explicit None values are treated as absent.
    tr = _tiering_result(
        weekly_sma_alignment=None, weekly_trend_state=None, weekly_alignment_context=None
    )
    text = format_alert(tr)
    assert "Weekly:" not in text


def test_14a_does_not_render_snake_case_field_names():
    # 30: raw snake_case field names must never appear as rendered labels.
    tr = _tiering_result(**_WEEKLY_DISPLAY_PAYLOAD)
    text = format_alert(tr).lower()
    for field in ("weekly_sma_alignment", "weekly_trend_state", "weekly_alignment_context"):
        assert field not in text, f"raw field name {field!r} leaked into rendered alert"


def test_14a_weekly_display_does_not_change_decision_fields():
    # display-only: format_alert must not mutate tier/capital/channel.
    tr = _tiering_result(**_WEEKLY_DISPLAY_PAYLOAD)
    before = (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"])
    _ = format_alert(tr)
    assert (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"]) == before


def test_14a_daily_layer_preserved_with_weekly_present():
    # Daily Trend / Market State / Zone line must remain intact alongside weekly.
    tr = _tiering_result(market_structure_state="REPAIR", **_WEEKLY_DISPLAY_PAYLOAD)
    text = format_alert(tr)
    assert "Trend: fresh_expansion  |  Market State: REPAIR  |  Zone: FVG" in text
    assert "Weekly: advancing / supportive  |  Alignment: partial_alignment" in text


def test_14a_partial_weekly_payload_renders_with_safe_fillers():
    # If only the context is present, the line still renders with safe fillers.
    tr = _tiering_result(weekly_alignment_context="countertrend_context")
    tr["final_signal"].pop("weekly_sma_alignment", None)
    tr["final_signal"].pop("weekly_trend_state", None)
    text = format_alert(tr)
    assert "Weekly: unknown / unavailable  |  Alignment: countertrend_context" in text


# ===========================================================================
# Phase 14C — Real 4H Operational State context (display-only)
# ===========================================================================

_4H_DISPLAY_PAYLOAD = {
    "four_hour_market_state":   "TRANSITION",
    "four_hour_sma_alignment":  "mixed",
    "four_hour_reclaim_status": "below_value",
    "four_hour_structure_note": "lower_high_pressure",
    "four_hour_data_status":    "current",
}

_4H_FIELDS = (
    "four_hour_market_state", "four_hour_sma_alignment",
    "four_hour_reclaim_status", "four_hour_structure_note",
    "four_hour_data_status",
)

# No-authority language that must never appear on the 4H line.
_4H_FORBIDDEN_WORDS = ("blocked", "approved", "downgraded", "vetoed")


def test_14c_renders_4h_context_when_present():
    tr = _tiering_result(**_4H_DISPLAY_PAYLOAD)
    text = format_alert(tr)
    assert (
        "4H: TRANSITION  |  SMA: mixed  |  Reclaim: below_value  |  Data: current"
        in text
    ), f"4H context not rendered; alert body:\n{text}"


def test_14c_renders_unavailable_4h_line():
    tr = _tiering_result(
        four_hour_market_state="UNAVAILABLE",
        four_hour_sma_alignment="unavailable",
        four_hour_reclaim_status="unavailable",
        four_hour_structure_note="unavailable",
        four_hour_data_status="unavailable",
    )
    text = format_alert(tr)
    assert (
        "4H: UNAVAILABLE  |  SMA: unavailable  |  Reclaim: unavailable  |  Data: unavailable"
        in text
    )


def test_14c_omits_4h_context_when_absent():
    tr = _tiering_result()
    for f in _4H_FIELDS:
        tr["final_signal"].pop(f, None)
    text = format_alert(tr)
    assert "4H:" not in text, "4H line rendered when all 4H fields absent"


def test_14c_omits_4h_context_when_none():
    tr = _tiering_result(**{f: None for f in _4H_FIELDS})
    text = format_alert(tr)
    assert "4H:" not in text


def test_14c_does_not_render_snake_case_field_names():
    tr = _tiering_result(**_4H_DISPLAY_PAYLOAD)
    text = format_alert(tr).lower()
    for field in _4H_FIELDS:
        assert field not in text, f"raw field name {field!r} leaked into rendered alert"


def test_14c_no_authority_language_on_4h_line():
    tr = _tiering_result(
        four_hour_market_state="FAILURE",
        four_hour_sma_alignment="hostile",
        four_hour_reclaim_status="failed_reclaim",
        four_hour_structure_note="breakdown_pressure",
        four_hour_data_status="current",
    )
    text = format_alert(tr)
    # Isolate the 4H line and assert no authority verbs appear on it.
    line = next((ln for ln in text.splitlines() if ln.strip().startswith("4H:")), "")
    assert line, "4H line missing"
    low = line.lower()
    for word in _4H_FORBIDDEN_WORDS:
        assert word not in low, f"authority word {word!r} appeared on 4H line: {line!r}"


def test_14c_4h_display_does_not_change_decision_fields():
    tr = _tiering_result(**_4H_DISPLAY_PAYLOAD)
    before = (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"])
    _ = format_alert(tr)
    assert (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"]) == before


def test_14c_daily_weekly_layers_preserved_with_4h_present():
    tr = _tiering_result(
        market_structure_state="REPAIR",
        **_WEEKLY_DISPLAY_PAYLOAD, **_4H_DISPLAY_PAYLOAD,
    )
    text = format_alert(tr)
    assert "Trend: fresh_expansion  |  Market State: REPAIR  |  Zone: FVG" in text
    assert "Weekly: advancing / supportive  |  Alignment: partial_alignment" in text
    assert "4H: TRANSITION  |  SMA: mixed  |  Reclaim: below_value  |  Data: current" in text


def test_14c_adverse_4h_does_not_make_wait_sendable():
    # WAIT must remain non-sendable regardless of any 4H evidence.
    tr = _tiering_result(tier="WAIT", safe=False, **_4H_DISPLAY_PAYLOAD)
    tr["final_discord_channel"] = "none"
    sendable, _reason = _sendable(tr, None)
    assert sendable is False


def test_14c_does_not_leak_internal_4h_or_prior_fields():
    tr = _tiering_result(**_4H_DISPLAY_PAYLOAD)
    text = format_alert(tr).lower()
    # 4H is the only newly-surfaced layer; structure_note is captured for
    # backtesting but is NOT a rendered label.
    assert "four_hour_structure_note" not in text
    assert "lower_high_pressure" not in text  # structure_note value not displayed
    assert "4h: transition" in text


# ===========================================================================
# Phase 14E — Real 1H Entry Trigger context (display-only)
# ===========================================================================

_1H_DISPLAY_PAYLOAD = {
    "one_hour_trigger_family":    "break_retest_hold",
    "one_hour_state":             "expansion",
    "one_hour_retest_quality":    "clean",
    "one_hour_acceptance_state":  "accepted",
    "one_hour_consequence_state": "confirmed",
    "one_hour_no_chase_status":   "ideal",
    "one_hour_data_status":       "available",
}

_1H_FIELDS = (
    "one_hour_trigger_family", "one_hour_state", "one_hour_retest_quality",
    "one_hour_acceptance_state", "one_hour_consequence_state",
    "one_hour_no_chase_status", "one_hour_data_status",
)

# No-authority language that must never appear on the 1H line.
_1H_FORBIDDEN_WORDS = ("blocked", "approved", "downgraded", "vetoed", "authorized")


def test_14e_renders_1h_context_when_present():
    tr = _tiering_result(**_1H_DISPLAY_PAYLOAD)
    text = format_alert(tr)
    assert (
        "1H: break_retest_hold  |  Retest: clean  |  Acceptance: accepted  |  "
        "Consequence: confirmed  |  No-Chase: ideal  |  Data: available"
        in text
    ), f"1H context not rendered; alert body:\n{text}"


def test_14e_renders_unknown_1h_line():
    tr = _tiering_result(
        one_hour_trigger_family="unknown",
        one_hour_state="unknown",
        one_hour_retest_quality="unknown",
        one_hour_acceptance_state="unknown",
        one_hour_consequence_state="unknown",
        one_hour_no_chase_status="unknown",
        one_hour_data_status="unavailable",
    )
    text = format_alert(tr)
    assert (
        "1H: unknown  |  Retest: unknown  |  Acceptance: unknown  |  "
        "Consequence: unknown  |  No-Chase: unknown  |  Data: unavailable"
        in text
    )


def test_14e_omits_1h_context_when_absent():
    tr = _tiering_result()
    for f in _1H_FIELDS:
        tr["final_signal"].pop(f, None)
    text = format_alert(tr)
    assert "1H:" not in text, "1H line rendered when all 1H fields absent"


def test_14e_omits_1h_context_when_none():
    tr = _tiering_result(**{f: None for f in _1H_FIELDS})
    text = format_alert(tr)
    assert "1H:" not in text


def test_14e_does_not_render_snake_case_field_names():
    tr = _tiering_result(**_1H_DISPLAY_PAYLOAD)
    text = format_alert(tr).lower()
    for field in _1H_FIELDS:
        assert field not in text, f"raw field name {field!r} leaked into rendered alert"


def test_14e_no_authority_language_on_1h_line():
    tr = _tiering_result(
        one_hour_trigger_family="none",
        one_hour_state="failure",
        one_hour_retest_quality="failed",
        one_hour_acceptance_state="rejected",
        one_hour_consequence_state="rejected",
        one_hour_no_chase_status="overextended",
        one_hour_data_status="available",
    )
    text = format_alert(tr)
    line = next((ln for ln in text.splitlines() if ln.strip().startswith("1H:")), "")
    assert line, "1H line missing"
    low = line.lower()
    for word in _1H_FORBIDDEN_WORDS:
        assert word not in low, f"authority word {word!r} appeared on 1H line: {line!r}"


def test_14e_1h_display_does_not_change_decision_fields():
    tr = _tiering_result(**_1H_DISPLAY_PAYLOAD)
    before = (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"])
    _ = format_alert(tr)
    assert (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"]) == before


def test_14e_higher_timeframe_layers_preserved_with_1h_present():
    tr = _tiering_result(
        market_structure_state="REPAIR",
        four_hour_market_state="TRANSITION",
        four_hour_sma_alignment="mixed",
        four_hour_reclaim_status="below_value",
        four_hour_structure_note="lower_high_pressure",
        four_hour_data_status="current",
        **_1H_DISPLAY_PAYLOAD,
    )
    text = format_alert(tr)
    assert "4H: TRANSITION  |  SMA: mixed  |  Reclaim: below_value  |  Data: current" in text
    assert "1H: break_retest_hold  |  Retest: clean" in text


def test_14e_adverse_1h_does_not_make_wait_sendable():
    tr = _tiering_result(tier="WAIT", safe=False, **_1H_DISPLAY_PAYLOAD)
    tr["final_discord_channel"] = "none"
    sendable, _reason = _sendable(tr, None)
    assert sendable is False


# ===========================================================================
# Phase 14F — Active Auction Conflict notice (displays a tiering decision)
# ===========================================================================

_14F_STARTER_NOTE = (
    "Full-size capital withheld. Higher-timeframe trend remains "
    "constructive, but the 4H/1H auction has not yet proven "
    "continuation acceptance."
)
_14F_NEAR_ENTRY_NOTE = (
    "Capital withheld. Higher-timeframe trend remains constructive, "
    "but the active 4H/1H auction is contradicting continuation; "
    "wait for acceptance proof."
)


def _14f_starter_capped_result(**extra) -> dict:
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        active_auction_conflict=True,
        active_auction_conflict_points=4,
        active_auction_conflict_reasons=["four_hour_reclaim_status=failed_reclaim (+2)"],
        active_auction_conflict_note=_14F_STARTER_NOTE,
        **extra,
    )
    tr["capital_action"] = "starter_only"
    tr["final_discord_channel"] = "#starter-signals"
    return tr


def test_14f_renders_conflict_block_when_capped_to_starter():
    text = format_alert(_14f_starter_capped_result())
    assert "ACTIVE AUCTION CONFLICT" in text
    assert "Full-size capital withheld." in text
    assert "has not yet proven" in text


def test_14f_capped_starter_does_not_say_full_quality():
    text = format_alert(_14f_starter_capped_result())
    # The sizing line must be the STARTER contract, not the SNIPE one.
    assert "STARTER SIZE ONLY" in text
    assert "FULL QUALITY" not in text
    assert "capital authorized after live-chart verification" not in text


def test_14f_renders_conflict_block_when_capped_to_near_entry():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        capital_action="wait_no_capital",
        active_auction_conflict=True,
        active_auction_conflict_points=6,
        active_auction_conflict_reasons=["one_hour_acceptance_state=pending (+1)"],
        active_auction_conflict_note=_14F_NEAR_ENTRY_NOTE,
    )
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "ACTIVE AUCTION CONFLICT" in text
    assert "Capital withheld." in text


def test_14f_omits_conflict_block_when_not_triggered():
    tr = _tiering_result(
        active_auction_conflict=False,
        active_auction_conflict_points=0,
        active_auction_conflict_reasons=[],
        active_auction_conflict_note=None,
    )
    text = format_alert(tr)
    assert "ACTIVE AUCTION CONFLICT" not in text


def test_14f_omits_conflict_block_when_fields_absent():
    tr = _tiering_result()
    text = format_alert(tr)
    assert "ACTIVE AUCTION CONFLICT" not in text


def test_14f_conflict_block_does_not_alter_evidence_lines():
    tr = _14f_starter_capped_result(
        four_hour_market_state="TRANSITION",
        four_hour_sma_alignment="mixed",
        four_hour_reclaim_status="below_value",
        four_hour_structure_note="lower_high_pressure",
        four_hour_data_status="current",
        one_hour_trigger_family="none",
        one_hour_state="repair",
        one_hour_retest_quality="weak",
        one_hour_acceptance_state="pending",
        one_hour_consequence_state="neutral",
        one_hour_no_chase_status="acceptable",
        one_hour_data_status="available",
    )
    text = format_alert(tr)
    assert "4H: TRANSITION  |  SMA: mixed  |  Reclaim: below_value  |  Data: current" in text
    assert (
        "1H: none  |  Retest: weak  |  Acceptance: pending  |  "
        "Consequence: neutral  |  No-Chase: acceptable  |  Data: available"
        in text
    )
    # The 4H/1H evidence lines themselves stay authority-free.
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("4H:") or s.startswith("1H:"):
            low = s.lower()
            for word in _1H_FORBIDDEN_WORDS:
                assert word not in low, f"authority word {word!r} on evidence line: {ln!r}"


def test_14f_conflict_does_not_make_wait_sendable():
    tr = _tiering_result(
        tier="WAIT", safe=False,
        active_auction_conflict=True,
        active_auction_conflict_note=_14F_NEAR_ENTRY_NOTE,
    )
    tr["final_discord_channel"] = "none"
    sendable, _reason = _sendable(tr, None)
    assert sendable is False


def test_14f_conflict_block_display_does_not_change_decision_fields():
    tr = _14f_starter_capped_result()
    before = (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"])
    _ = format_alert(tr)
    assert (tr["final_tier"], tr["capital_action"], tr["final_discord_channel"]) == before


# ===========================================================================
# Phase 14F.1 — NEAR_ENTRY language firewall (watch-only authority in text)
# ===========================================================================

# Phrases that must never appear in a rendered NEAR_ENTRY alert body.
_14F1_FORBIDDEN_NE = (
    "enter at", "enter near", "enter on", "entry at", "buy at", "take at",
    "take the trade", "current price with stop", "capital authorized",
    "full quality", "full-size", "starter size", "starter conditions met",
    "snipe_it conditions met",
)


def _assert_no_forbidden_ne_language(text: str):
    low = text.lower()
    for phrase in _14F1_FORBIDDEN_NE:
        assert phrase not in low, f"forbidden NEAR_ENTRY phrase {phrase!r} in body:\n{text}"


def test_14f1_natural_near_entry_execution_language_sanitized():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        capital_action="wait_no_capital",
        next_action="Enter at current price with stop below 178.20",
        reason="Buy at the retest and take the trade full-size; starter size also fine.",
        upgrade_trigger="Entry at 182.50 once reclaimed",
    )
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    _assert_no_forbidden_ne_language(text)
    assert "no capital" in text.lower() or "watch" in text.lower()


def test_14f1_governor_capped_near_entry_renders_watch_only():
    from src.tiering import validate
    signal = {
        "ticker": "ARM", "tier": "SNIPE_IT", "score": 88,
        "setup_family": "continuation", "structure_event": "BOS",
        "trend_state": "fresh_expansion", "sma_value_alignment": "supportive",
        "zone_type": "OB", "trigger_level": 182.50,
        "retest_status": "confirmed", "hold_status": "confirmed",
        "invalidation_condition": "Daily close below OB base",
        "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "risk_reward": 3.5, "overhead_status": "clear",
        "forced_participation": "none", "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at current price with stop below 178.20",
        "discord_channel": "#snipe-signals", "capital_action": "full_quality_allowed",
        "reason": "Clean BOS with confirmed OB retest and hold.",
    }
    kf = {
        "four_hour_market_state": "TRANSITION", "four_hour_sma_alignment": "mixed",
        "four_hour_reclaim_status": "below_value",
        "four_hour_structure_note": "lower_high_pressure",
        "four_hour_data_status": "current",
        "one_hour_trigger_family": "none", "one_hour_state": "repair",
        "one_hour_retest_quality": "weak", "one_hour_acceptance_state": "pending",
        "one_hour_consequence_state": "neutral", "one_hour_no_chase_status": "acceptable",
        "one_hour_data_status": "available",
    }
    cfg = {"tiers": {"snipe_it": {"min_score": 85, "min_rr": 3.0},
                     "starter": {"min_score": 75, "min_rr": 3.0},
                     "near_entry": {"min_score": 60}}}
    res = validate(signal, {"veto_flags": [], "key_features": kf}, cfg)
    assert res["final_tier"] == "NEAR_ENTRY"
    text = format_alert(res)
    _assert_no_forbidden_ne_language(text)
    assert "ACTIVE AUCTION CONFLICT" in text
    assert "Monitor for reclaim, acceptance, and hold" in text


def test_14f1_starter_still_says_starter_size_only():
    tr = _tiering_result(tier="STARTER", capital_action="starter_only")
    tr["capital_action"] = "starter_only"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)
    assert "STARTER SIZE ONLY" in text


def test_14f1_snipe_it_still_says_full_quality_capital_authorized():
    text = format_alert(_tiering_result())
    assert "FULL QUALITY — capital authorized after live-chart verification." in text


def test_14f1_wait_still_never_sendable():
    tr = _tiering_result(
        tier="WAIT", safe=False,
        next_action="Enter at current price with stop below 178.20",
    )
    tr["final_discord_channel"] = "none"
    sendable, _reason = _sendable(tr, None)
    assert sendable is False


def test_14f1_firewall_does_not_mutate_structural_fields_or_dedup_key():
    from src.state_store import make_dedup_key
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        capital_action="wait_no_capital",
        next_action="Enter at current price with stop below 178.20",
    )
    sig = tr["final_signal"]
    key_before = make_dedup_key("AAPL", tr["final_tier"],
                                sig["trigger_level"], sig["invalidation_level"])
    structural_before = (sig["trigger_level"], sig["invalidation_level"],
                         list(sig["targets"]), sig["score"], sig["tier"])
    _ = format_alert(tr)
    key_after = make_dedup_key("AAPL", tr["final_tier"],
                               sig["trigger_level"], sig["invalidation_level"])
    structural_after = (sig["trigger_level"], sig["invalidation_level"],
                        list(sig["targets"]), sig["score"], sig["tier"])
    assert key_before == key_after
    assert structural_before == structural_after
    # The raw stored text fields are not rewritten by rendering.
    assert sig["next_action"] == "Enter at current price with stop below 178.20"


def test_14f1_decision_path_does_not_read_sanitized_text():
    import inspect
    from src import tiering
    for fn_name in ("_determine_final_tier", "_entry_gate_failures",
                    "_snipe_gate_failures", "_starter_gate_failures",
                    "_near_entry_gate_failures",
                    "_detect_active_auction_conflict",
                    "_apply_active_auction_conflict_governor"):
        src = inspect.getsource(getattr(tiering, fn_name))
        assert "sanitized" not in src, (
            f"decision-path function {fn_name} reads sanitized display text"
        )


# ===========================================================================
# Phase 15A — Daily Authority Governor display block
# ===========================================================================

_15A_NE_NOTE = (
    "Capital withheld. Lower-timeframe structure may be improving, "
    "but the daily chart has not granted swing permission yet. "
    "Required proof: weekly_trend_state=declining (+5)"
)
_15A_STARTER_NOTE = (
    "Starter only. Daily context is constructive enough to monitor, "
    "but one or more authority layers are incomplete. "
    "Missing proof: weekly_trend_state=distributing (+3)"
)


def _15a_ne_capped_result(**extra) -> dict:
    """SNIPE_IT capped to NEAR_ENTRY by the Daily Authority Governor."""
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        capital_action="wait_no_capital",
        daily_authority_conflict=True,
        daily_authority_points=5,
        daily_authority_reasons=["weekly_trend_state=declining (+5)"],
        daily_authority_note=_15A_NE_NOTE,
        daily_permission_cap="SNIPE_IT→NEAR_ENTRY",
        active_auction_conflict=False,
        active_auction_conflict_points=0,
        active_auction_conflict_reasons=[],
        active_auction_conflict_note=None,
        **extra,
    )
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    return tr


def _15a_starter_capped_result(**extra) -> dict:
    """SNIPE_IT capped to STARTER by the Daily Authority Governor."""
    tr = _tiering_result(
        tier="STARTER",
        capital_action="starter_only",
        daily_authority_conflict=True,
        daily_authority_points=3,
        daily_authority_reasons=["weekly_trend_state=distributing (+3)"],
        daily_authority_note=_15A_STARTER_NOTE,
        daily_permission_cap="SNIPE_IT→STARTER",
        active_auction_conflict=False,
        active_auction_conflict_points=0,
        active_auction_conflict_reasons=[],
        active_auction_conflict_note=None,
        **extra,
    )
    tr["capital_action"] = "starter_only"
    tr["final_discord_channel"] = "#starter-signals"
    return tr


# 15A-D1: NEAR_ENTRY cap shows "DAILY AUTHORITY CONFLICT" header
def test_15a_near_entry_cap_shows_authority_conflict_header():
    text = format_alert(_15a_ne_capped_result())
    assert "DAILY AUTHORITY CONFLICT" in text
    assert "Capital withheld." in text
    assert "daily chart has not granted swing permission" in text


# 15A-D2: STARTER cap shows "DAILY AUTHORITY CAP" header
def test_15a_starter_cap_shows_authority_cap_header():
    text = format_alert(_15a_starter_capped_result())
    assert "DAILY AUTHORITY CAP" in text
    assert "Starter only." in text
    assert "one or more authority layers are incomplete" in text


# 15A-D3: no conflict → neither block appears
def test_15a_no_conflict_no_block_shown():
    tr = _tiering_result(
        daily_authority_conflict=False,
        daily_authority_points=0,
        daily_authority_reasons=[],
        daily_authority_note=None,
        daily_permission_cap=None,
    )
    text = format_alert(tr)
    assert "DAILY AUTHORITY" not in text


# 15A-D4: no daily_authority_conflict field → block absent (field-absent safety)
def test_15a_absent_fields_no_block():
    tr = _tiering_result()  # no daily_authority_* fields at all
    text = format_alert(tr)
    assert "DAILY AUTHORITY" not in text


# 15A-D5: note content rendered in the block
def test_15a_note_content_rendered():
    text = format_alert(_15a_ne_capped_result())
    assert "Required proof:" in text
    assert "weekly_trend_state=declining" in text


# 15A-D6: NEAR_ENTRY capped by DAG still has NE capital firewall applied
def test_15a_ne_capped_by_dag_still_has_ne_capital_firewall():
    tr = _15a_ne_capped_result(next_action="Enter at current price with stop below 178.20")
    text = format_alert(tr)
    _assert_no_forbidden_ne_language(text)


# 15A-D7: when both 14F and 15A fire, both blocks appear
def test_15a_both_governors_show_both_blocks():
    tr = _tiering_result(
        tier="NEAR_ENTRY",
        capital_action="wait_no_capital",
        active_auction_conflict=True,
        active_auction_conflict_points=6,
        active_auction_conflict_reasons=["one_hour_acceptance_state=pending (+1)"],
        active_auction_conflict_note=_14F_NEAR_ENTRY_NOTE,
        daily_authority_conflict=True,
        daily_authority_points=5,
        daily_authority_reasons=["weekly_trend_state=declining (+5)"],
        daily_authority_note=_15A_NE_NOTE,
        daily_permission_cap="STARTER→NEAR_ENTRY",
    )
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    text = format_alert(tr)
    assert "ACTIVE AUCTION CONFLICT" in text
    assert "DAILY AUTHORITY CONFLICT" in text

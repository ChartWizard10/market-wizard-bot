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
        # Phase 11 freshness fields (mirroring what tiering.validate() now adds)
        "scan_price": 182.50,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "Signal based on scan-time price; verify live chart before entry.",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 2.41,
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
    # Deterministic tier label must say STARTER
    assert "All STARTER conditions met." in text
    # SNIPE_IT label must NOT appear in this STARTER alert
    assert "All SNIPE_IT conditions met." not in text


# 11-7: SNIPE_IT alert correctly shows "All SNIPE_IT conditions met."
def test_snipe_alert_says_all_snipe_conditions_met():
    tr = _tiering_result(tier="SNIPE_IT", reason="Clean zone defense, full quality.")
    text = format_alert(tr)
    assert "All SNIPE_IT conditions met." in text
    assert "All STARTER conditions met." not in text


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
    assert "NEAR_ENTRY conditions met; wait for missing confirmations." in text


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
    # Deterministic label must be STARTER (from final_tier)
    assert "All STARTER conditions met." in text
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

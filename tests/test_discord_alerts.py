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

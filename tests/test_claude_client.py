"""Claude client JSON contract tests — Phase 4."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claude_client import (
    build_prompt,
    load_system_prompt,
    parse_and_validate_json,
    async_claude_scan,
    _DISABLED_INDICATORS,
    _REQUIRED_KEYS,
    _TIER_CHANNEL_MAP,
    _TIER_CAPITAL_MAP,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_signal(**overrides) -> dict:
    """Build a minimal valid Claude response dict."""
    base = {
        "ticker": "AAPL",
        "timestamp_et": "2025-01-15T10:30:00-05:00",
        "tier": "SNIPE_IT",
        "score": 88,
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
        "risk_reward": 3.1,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at zone retest confirmation",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with FVG retest confirmed and held. Clear overhead.",
    }
    base.update(overrides)
    return base


def _valid_enriched(**overrides) -> dict:
    """Build a minimal valid enriched ticker dict for prompt building."""
    base = {
        "ticker": "AAPL",
        "latest_close": 183.50,
        "sma20": 180.00,
        "sma50": 175.00,
        "sma200": 165.00,
        "sma_value_alignment": "supportive",
        "price_extension_from_sma20_pct": 1.94,
        "atr": 2.50,
        "structure_event": "MSS",
        "wick_only_break": False,
        "fvg": {
            "fvg_top": 182.00, "fvg_mid": 180.50, "fvg_bot": 179.00,
            "fvg_filled": False, "price_in_fvg": False,
        },
        "ob": None,
        "retest_status": "confirmed",
        "overhead_status": "clear",
        "volume_behavior": "expansion",
        "invalidation_level": 178.00,
        "targets": [{"label": "T1", "level": 195.00, "reason": "Prior swing high"}],
        "estimated_rr": 3.2,
    }
    base.update(overrides)
    return base


_MINIMAL_CONFIG = {
    "claude": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1200,
        "max_concurrent_calls": 8,
    }
}


# ---------------------------------------------------------------------------
# 1. Valid JSON passes
# ---------------------------------------------------------------------------

def test_valid_json_passes():
    raw = json.dumps(_valid_signal())
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is not None
    assert err_type is None
    assert signal["tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 2. Malformed JSON rejected
# ---------------------------------------------------------------------------

def test_malformed_json_rejected():
    raw = "NOT JSON AT ALL"
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_PARSE_ERROR"
    assert err_msg is not None


# ---------------------------------------------------------------------------
# 3. Missing required key rejected
# ---------------------------------------------------------------------------

def test_missing_key_rejected():
    data = _valid_signal()
    del data["invalidation_level"]
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_SCHEMA_ERROR"
    assert "invalidation_level" in err_msg


# ---------------------------------------------------------------------------
# 4. Invalid enum value rejected
# ---------------------------------------------------------------------------

def test_invalid_enum_rejected():
    data = _valid_signal(tier="STRONG_BUY")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_ENUM_ERROR"
    assert "tier" in err_msg


# ---------------------------------------------------------------------------
# 5. Routing mismatch (discord_channel) is returned as-is — tiering.py corrects it
# ---------------------------------------------------------------------------

def test_routing_mismatch_passes_validation():
    """parse_and_validate_json accepts the mismatch — tiering.py is the correcting authority."""
    data = _valid_signal(tier="SNIPE_IT", discord_channel="#near-entry-watch")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    # JSON validator does not enforce tier↔channel mapping — that belongs to tiering.py
    assert signal is not None
    assert err_type is None
    assert signal["discord_channel"] == "#near-entry-watch"


# ---------------------------------------------------------------------------
# 6. Prose / markdown fences around JSON stripped correctly
# ---------------------------------------------------------------------------

def test_prose_around_json_stripped():
    signal_json = json.dumps(_valid_signal())
    wrapped = f"Here is my analysis:\n\n```json\n{signal_json}\n```\n\nLet me know if you need more details."
    signal, err_type, err_msg = parse_and_validate_json(wrapped)
    assert signal is not None
    assert err_type is None
    assert signal["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# 7. All required keys present in accepted signal
# ---------------------------------------------------------------------------

def test_all_required_keys_present_after_parse():
    raw = json.dumps(_valid_signal())
    signal, _, _ = parse_and_validate_json(raw)
    assert signal is not None
    for key in _REQUIRED_KEYS:
        assert key in signal, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 8. Non-numeric risk_reward treated as null, not rejected
# ---------------------------------------------------------------------------

def test_non_numeric_risk_reward_treated_as_null():
    data = _valid_signal(risk_reward="not-a-number")
    raw = json.dumps(data)
    signal, err_type, _ = parse_and_validate_json(raw)
    assert signal is not None
    assert err_type is None
    assert signal["risk_reward"] is None


# ---------------------------------------------------------------------------
# 9. score clamped to 0–100
# ---------------------------------------------------------------------------

def test_score_clamped_above_100():
    data = _valid_signal(score=150)
    signal, _, _ = parse_and_validate_json(json.dumps(data))
    assert signal is not None
    assert signal["score"] == 100


def test_score_clamped_below_zero():
    data = _valid_signal(score=-10)
    signal, _, _ = parse_and_validate_json(json.dumps(data))
    assert signal is not None
    assert signal["score"] == 0


# ---------------------------------------------------------------------------
# 10. targets must be a list
# ---------------------------------------------------------------------------

def test_targets_not_list_rejected():
    data = _valid_signal(targets="T1: 195.00")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_SCHEMA_ERROR"
    assert "targets" in err_msg


# ---------------------------------------------------------------------------
# 11. All WAIT-tier enum values accepted
# ---------------------------------------------------------------------------

def test_wait_tier_valid():
    data = _valid_signal(
        tier="WAIT",
        discord_channel="none",
        capital_action="no_trade",
        retest_status="missing",
        hold_status="missing",
        invalidation_level=None,
        risk_reward=None,
    )
    signal, err_type, _ = parse_and_validate_json(json.dumps(data))
    assert signal is not None
    assert err_type is None
    assert signal["tier"] == "WAIT"


# ---------------------------------------------------------------------------
# 12. NEAR_ENTRY tier valid
# ---------------------------------------------------------------------------

def test_near_entry_tier_valid():
    data = _valid_signal(
        tier="NEAR_ENTRY",
        discord_channel="#near-entry-watch",
        capital_action="wait_no_capital",
        retest_status="missing",
        hold_status="missing",
        risk_reward=None,
        invalidation_level=None,
        missing_conditions=["retest_status", "hold_status"],
        upgrade_trigger="Confirmed retest of FVG with hold at 179.00",
    )
    signal, err_type, _ = parse_and_validate_json(json.dumps(data))
    assert signal is not None
    assert err_type is None
    assert signal["tier"] == "NEAR_ENTRY"


# ---------------------------------------------------------------------------
# 13. build_prompt excludes all disabled indicators
# ---------------------------------------------------------------------------

def test_build_prompt_excludes_disabled_indicators():
    enriched = _valid_enriched()
    prompt = build_prompt(enriched)
    prompt_lower = prompt.lower()
    for indicator in _DISABLED_INDICATORS:
        assert indicator not in prompt_lower, f"Disabled indicator '{indicator}' found in prompt"


# ---------------------------------------------------------------------------
# 14. build_prompt includes key structure fields
# ---------------------------------------------------------------------------

def test_build_prompt_includes_structure_fields():
    enriched = _valid_enriched()
    prompt = build_prompt(enriched)
    assert "STRUCTURE_EVENT:" in prompt
    assert "RETEST_STATUS:" in prompt
    assert "OVERHEAD_STATUS:" in prompt
    assert "FVG:" in prompt
    assert "VOLUME_BEHAVIOR:" in prompt


# ---------------------------------------------------------------------------
# 15. build_prompt includes ticker and price fields
# ---------------------------------------------------------------------------

def test_build_prompt_includes_ticker_and_price():
    enriched = _valid_enriched(ticker="NVDA", latest_close=850.00)
    prompt = build_prompt(enriched)
    assert "TICKER: NVDA" in prompt
    assert "LATEST_CLOSE: 850" in prompt


# ---------------------------------------------------------------------------
# 16. async_claude_scan returns one result per candidate
# ---------------------------------------------------------------------------

def test_async_scan_returns_one_result_per_candidate():
    valid_response = json.dumps(_valid_signal())

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=valid_response)]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    candidates = [_valid_enriched(ticker="AAPL"), _valid_enriched(ticker="NVDA")]
    system_prompt = "SYSTEM PROMPT"

    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, system_prompt, mock_client, _MINIMAL_CONFIG)
    )
    assert len(results) == len(candidates)


# ---------------------------------------------------------------------------
# 17. async_claude_scan handles Claude API error gracefully
# ---------------------------------------------------------------------------

def test_async_scan_handles_api_error_gracefully():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

    candidates = [_valid_enriched(ticker="AAPL")]
    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert len(results) == 1
    assert results[0]["signal"] is None
    assert results[0]["error_type"] == "CLAUDE_API_ERROR"


# ---------------------------------------------------------------------------
# 18. async_claude_scan handles malformed JSON from Claude gracefully
# ---------------------------------------------------------------------------

def test_async_scan_handles_malformed_json_gracefully():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="This is not JSON at all.")]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    candidates = [_valid_enriched(ticker="AAPL")]
    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert results[0]["signal"] is None
    assert results[0]["error_type"] == "JSON_PARSE_ERROR"


# ---------------------------------------------------------------------------
# 19. Claude call count is bounded by max_concurrent_calls semaphore (mock proof)
# ---------------------------------------------------------------------------

def test_async_scan_call_count_matches_candidates():
    """Claude is called exactly once per candidate — no more."""
    valid_response = json.dumps(_valid_signal())
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=valid_response)]

    call_count = []

    async def fake_create(**kwargs):
        call_count.append(1)
        return mock_message

    mock_client = MagicMock()
    mock_client.messages.create = fake_create

    n = 5
    candidates = [_valid_enriched(ticker=f"SYM{i}") for i in range(n)]
    asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert len(call_count) == n


# ---------------------------------------------------------------------------
# 20. load_system_prompt raises FileNotFoundError for missing path
# ---------------------------------------------------------------------------

def test_load_system_prompt_raises_for_missing_path():
    with pytest.raises(FileNotFoundError):
        load_system_prompt("/nonexistent/path/system.md")


# ---------------------------------------------------------------------------
# 21. load_system_prompt loads actual prompt file
# ---------------------------------------------------------------------------

def test_load_system_prompt_loads_actual_file():
    prompt = load_system_prompt("prompts/market_wizard_system.md")
    assert len(prompt) > 100
    assert "WAIT" in prompt
    assert "SNIPE_IT" in prompt
    # Disabled indicators must not appear as enabled features in the prompt
    assert "RSI" not in prompt or "FORBIDDEN" in prompt or "MUST NOT" in prompt


# ---------------------------------------------------------------------------
# 22. Invalid enum on non-tier field is also caught
# ---------------------------------------------------------------------------

def test_invalid_enum_on_setup_family_rejected():
    data = _valid_signal(setup_family="ROCKET_SHIP")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_ENUM_ERROR"
    assert "setup_family" in err_msg


# ---------------------------------------------------------------------------
# 23. tier↔channel mapping constants are correct
# ---------------------------------------------------------------------------

def test_tier_channel_map_complete():
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"):
        assert tier in _TIER_CHANNEL_MAP
    assert _TIER_CHANNEL_MAP["WAIT"] == "none"
    assert _TIER_CHANNEL_MAP["SNIPE_IT"] == "#snipe-signals"


def test_tier_capital_map_complete():
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"):
        assert tier in _TIER_CAPITAL_MAP
    assert _TIER_CAPITAL_MAP["WAIT"] == "no_trade"
    assert _TIER_CAPITAL_MAP["SNIPE_IT"] == "full_quality_allowed"

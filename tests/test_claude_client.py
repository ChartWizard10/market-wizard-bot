"""Claude client JSON contract tests — Phase 4."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

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
    _RateGovernor,
    _is_rate_limit_error,
    _estimate_tokens,
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
        # Zero pacing so existing tests complete instantly
        "claude_concurrency": 1,
        "claude_min_seconds_between_calls": 0.0,
        "claude_max_input_tokens_per_minute_budget": 999999,
    }
}

# Config used for rate-limit specific tests — production-like values
_RATE_CFG = {
    "claude": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1200,
        "claude_concurrency": 1,
        "claude_min_seconds_between_calls": 4.0,
        "claude_max_input_tokens_per_minute_budget": 25000,
    }
}


# ---------------------------------------------------------------------------
# 1. Pure valid JSON passes
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
    assert err_type == "non_json_wrapper"


def test_syntactically_broken_json_rejected():
    raw = '{"ticker": "AAPL", "tier": SNIPE_IT}'  # unquoted value
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_PARSE_ERROR"


# ---------------------------------------------------------------------------
# 3. Markdown-fenced JSON rejected (strict contract: JSON only)
# ---------------------------------------------------------------------------

def test_markdown_fenced_json_rejected():
    signal_json = json.dumps(_valid_signal())
    fenced = f"```json\n{signal_json}\n```"
    signal, err_type, err_msg = parse_and_validate_json(fenced)
    assert signal is None
    assert err_type == "markdown_wrapper"
    assert err_msg is not None


def test_plain_code_fence_rejected():
    signal_json = json.dumps(_valid_signal())
    fenced = f"```\n{signal_json}\n```"
    signal, err_type, err_msg = parse_and_validate_json(fenced)
    assert signal is None
    assert err_type == "markdown_wrapper"


# ---------------------------------------------------------------------------
# 4. Prose wrapper around JSON rejected
# ---------------------------------------------------------------------------

def test_prose_before_json_rejected():
    signal_json = json.dumps(_valid_signal())
    wrapped = f"Here is my analysis:\n\n{signal_json}"
    signal, err_type, err_msg = parse_and_validate_json(wrapped)
    assert signal is None
    assert err_type == "non_json_wrapper"


def test_prose_after_json_rejected():
    signal_json = json.dumps(_valid_signal())
    wrapped = f"{signal_json}\n\nLet me know if you need more details."
    signal, err_type, err_msg = parse_and_validate_json(wrapped)
    assert signal is None
    assert err_type == "non_json_wrapper"


def test_prose_before_and_after_json_rejected():
    signal_json = json.dumps(_valid_signal())
    wrapped = f"Analysis:\n\n{signal_json}\n\nPlease review."
    signal, err_type, err_msg = parse_and_validate_json(wrapped)
    assert signal is None
    assert err_type in ("non_json_wrapper", "markdown_wrapper")


# ---------------------------------------------------------------------------
# 5. Missing required key rejected
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
# 6. Invalid enum value rejected
# ---------------------------------------------------------------------------

def test_invalid_enum_on_tier_rejected():
    data = _valid_signal(tier="STRONG_BUY")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_ENUM_ERROR"
    assert "tier" in err_msg


def test_invalid_enum_on_setup_family_rejected():
    data = _valid_signal(setup_family="ROCKET_SHIP")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_ENUM_ERROR"
    assert "setup_family" in err_msg


# ---------------------------------------------------------------------------
# 7. Routing mismatch passes validation — tiering.py corrects it
# ---------------------------------------------------------------------------

def test_routing_mismatch_passes_json_validation():
    """parse_and_validate_json does not enforce tier↔channel mapping — tiering.py owns that."""
    data = _valid_signal(tier="SNIPE_IT", discord_channel="#near-entry-watch")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is not None
    assert err_type is None
    assert signal["discord_channel"] == "#near-entry-watch"


# ---------------------------------------------------------------------------
# 8. All required keys present in accepted signal
# ---------------------------------------------------------------------------

def test_all_required_keys_present_after_parse():
    raw = json.dumps(_valid_signal())
    signal, _, _ = parse_and_validate_json(raw)
    assert signal is not None
    for key in _REQUIRED_KEYS:
        assert key in signal, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 9. Non-numeric risk_reward treated as null, not rejected
# ---------------------------------------------------------------------------

def test_non_numeric_risk_reward_treated_as_null():
    data = _valid_signal(risk_reward="not-a-number")
    raw = json.dumps(data)
    signal, err_type, _ = parse_and_validate_json(raw)
    assert signal is not None
    assert err_type is None
    assert signal["risk_reward"] is None


# ---------------------------------------------------------------------------
# 10. score clamped to 0–100
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
# 11. targets must be a list — rejects safely if not
# ---------------------------------------------------------------------------

def test_targets_not_list_rejected():
    data = _valid_signal(targets="T1: 195.00")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_SCHEMA_ERROR"
    assert "targets" in err_msg


# ---------------------------------------------------------------------------
# 12. missing_conditions must be a list — rejects safely if not
# ---------------------------------------------------------------------------

def test_missing_conditions_not_list_rejected():
    data = _valid_signal(missing_conditions="retest_status")
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_SCHEMA_ERROR"
    assert "missing_conditions" in err_msg


def test_missing_conditions_null_rejected():
    data = _valid_signal(missing_conditions=None)
    raw = json.dumps(data)
    signal, err_type, err_msg = parse_and_validate_json(raw)
    assert signal is None
    assert err_type == "JSON_SCHEMA_ERROR"
    assert "missing_conditions" in err_msg


# ---------------------------------------------------------------------------
# 13. WAIT and NEAR_ENTRY tiers accepted by JSON validator
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
# 14. build_prompt excludes all disabled indicators
# ---------------------------------------------------------------------------

def test_build_prompt_excludes_disabled_indicators():
    enriched = _valid_enriched()
    prompt = build_prompt(enriched)
    prompt_lower = prompt.lower()
    for indicator in _DISABLED_INDICATORS:
        assert indicator not in prompt_lower, f"Disabled indicator '{indicator}' found in prompt"


# ---------------------------------------------------------------------------
# 15. build_prompt includes key structure fields
# ---------------------------------------------------------------------------

def test_build_prompt_includes_structure_fields():
    enriched = _valid_enriched()
    prompt = build_prompt(enriched)
    assert "STRUCTURE_EVENT:" in prompt
    assert "RETEST_STATUS:" in prompt
    assert "OVERHEAD_STATUS:" in prompt
    assert "FVG:" in prompt
    assert "VOLUME_BEHAVIOR:" in prompt


def test_build_prompt_includes_ticker_and_price():
    enriched = _valid_enriched(ticker="NVDA", latest_close=850.00)
    prompt = build_prompt(enriched)
    assert "TICKER: NVDA" in prompt
    assert "LATEST_CLOSE: 850" in prompt


# ---------------------------------------------------------------------------
# 16. async_claude_scan returns one result per candidate (mocked — no live calls)
# ---------------------------------------------------------------------------

def test_async_scan_returns_one_result_per_candidate():
    valid_response = json.dumps(_valid_signal())
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=valid_response)]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    candidates = [_valid_enriched(ticker="AAPL"), _valid_enriched(ticker="NVDA")]
    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "SYSTEM", mock_client, _MINIMAL_CONFIG)
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
    assert results[0]["error_type"] in ("JSON_PARSE_ERROR", "non_json_wrapper")


# ---------------------------------------------------------------------------
# 19. Claude is called exactly once per candidate — mock proof, no live calls
# ---------------------------------------------------------------------------

def test_async_scan_call_count_matches_candidates():
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
    assert "SNIPE_IT" in prompt
    assert "WAIT" in prompt
    assert "JSON" in prompt


# ---------------------------------------------------------------------------
# 22. Tier ↔ channel/capital mapping constants are complete and correct
# ---------------------------------------------------------------------------

def test_tier_channel_map_complete():
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"):
        assert tier in _TIER_CHANNEL_MAP
    assert _TIER_CHANNEL_MAP["WAIT"] == "none"
    assert _TIER_CHANNEL_MAP["SNIPE_IT"] == "#snipe-signals"
    assert _TIER_CHANNEL_MAP["STARTER"] == "#starter-signals"
    assert _TIER_CHANNEL_MAP["NEAR_ENTRY"] == "#near-entry-watch"


def test_tier_capital_map_complete():
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"):
        assert tier in _TIER_CAPITAL_MAP
    assert _TIER_CAPITAL_MAP["WAIT"] == "no_trade"
    assert _TIER_CAPITAL_MAP["SNIPE_IT"] == "full_quality_allowed"
    assert _TIER_CAPITAL_MAP["STARTER"] == "starter_only"
    assert _TIER_CAPITAL_MAP["NEAR_ENTRY"] == "wait_no_capital"


# ---------------------------------------------------------------------------
# 23. _estimate_tokens: conservative chars/4 estimate
# ---------------------------------------------------------------------------

def test_estimate_tokens_chars_over_4():
    assert _estimate_tokens("x" * 400) == 100
    assert _estimate_tokens("x" * 1) == 1      # min=1
    assert _estimate_tokens("") == 1            # empty → min=1


# ---------------------------------------------------------------------------
# 24. _is_rate_limit_error: detects 429 by string
# ---------------------------------------------------------------------------

def test_is_rate_limit_error_detects_429():
    assert _is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert _is_rate_limit_error(Exception("rate limit exceeded")) is True
    assert _is_rate_limit_error(Exception("too many requests")) is True


def test_is_rate_limit_error_passes_through_other_errors():
    assert _is_rate_limit_error(Exception("network timeout")) is False
    assert _is_rate_limit_error(Exception("500 Internal Server Error")) is False


# ---------------------------------------------------------------------------
# 25. 429 exception → error_type == "claude_rate_limited", not CLAUDE_API_ERROR
# ---------------------------------------------------------------------------

def test_429_classified_as_claude_rate_limited():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=Exception("429 Too Many Requests: rate limit exceeded")
    )
    candidates = [_valid_enriched(ticker="AAPL")]
    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert results[0]["error_type"] == "claude_rate_limited"
    assert results[0]["signal"] is None


def test_non_rate_limit_error_stays_claude_api_error():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=Exception("500 Internal Server Error")
    )
    candidates = [_valid_enriched(ticker="AAPL")]
    results = asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert results[0]["error_type"] == "CLAUDE_API_ERROR"


# ---------------------------------------------------------------------------
# 26. _RateGovernor: enforces minimum inter-call gap
# ---------------------------------------------------------------------------

def test_governor_enforces_min_gap():
    fake_time = [0.0]
    sleep_log = []

    async def fake_sleep(secs: float):
        sleep_log.append(secs)
        fake_time[0] += secs

    governor = _RateGovernor(
        min_gap_secs=4.0,
        max_tpm=999999,
        _clock=lambda: fake_time[0],
        _sleep=fake_sleep,
    )

    async def run():
        await governor.acquire(100)          # first call — no sleep
        fake_time[0] = 2.0                   # only 2s elapsed
        await governor.acquire(100)          # should sleep 2s to reach 4s gap

    asyncio.get_event_loop().run_until_complete(run())
    assert len(sleep_log) == 1
    assert abs(sleep_log[0] - 2.0) < 0.01


# ---------------------------------------------------------------------------
# 27. _RateGovernor: enforces token budget (sleeps until window resets)
# ---------------------------------------------------------------------------

def test_governor_enforces_token_budget():
    fake_time = [0.0]
    sleep_log = []

    async def fake_sleep(secs: float):
        sleep_log.append(secs)
        fake_time[0] += secs

    governor = _RateGovernor(
        min_gap_secs=0.0,
        max_tpm=1000,
        _clock=lambda: fake_time[0],
        _sleep=fake_sleep,
    )

    async def run():
        await governor.acquire(600)         # uses 600/1000 tokens
        fake_time[0] = 5.0                  # 5s into 60s window
        await governor.acquire(500)         # 600+500=1100 > 1000 → sleep ~55s
        assert governor.tokens_in_window == 500  # window reset, only new tokens

    asyncio.get_event_loop().run_until_complete(run())
    assert len(sleep_log) == 1
    assert abs(sleep_log[0] - 55.0) < 1.0   # slept ~55s to reset window


# ---------------------------------------------------------------------------
# 28. async_claude_scan: concurrency never exceeds claude_concurrency config
# ---------------------------------------------------------------------------

def test_async_scan_respects_concurrency_limit():
    """Concurrent live API calls never exceed claude_concurrency=1."""
    concurrent = [0]
    peak = [0]

    valid_response = json.dumps(_valid_signal())
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=valid_response)]

    async def fake_create(**kwargs):
        concurrent[0] += 1
        peak[0] = max(peak[0], concurrent[0])
        await asyncio.sleep(0)              # yield to allow others to start
        concurrent[0] -= 1
        return mock_message

    mock_client = MagicMock()
    mock_client.messages.create = fake_create

    candidates = [_valid_enriched(ticker=f"SYM{i}") for i in range(4)]
    asyncio.get_event_loop().run_until_complete(
        async_claude_scan(candidates, "PROMPT", mock_client, _MINIMAL_CONFIG)
    )
    assert peak[0] <= 1

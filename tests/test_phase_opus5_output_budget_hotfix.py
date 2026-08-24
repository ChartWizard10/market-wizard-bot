"""Opus 5 adaptive-thinking output-budget regressions.

Claude Opus 5 reasoning and visible text share the Messages API max_tokens
ceiling. A response that stops at max_tokens is incomplete evidence and must be
classified before the strict JSON parser sees the truncated text.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.claude_client import claude_call


CFG = {
    "claude": {
        "model": "claude-opus-5",
        "max_tokens": 8192,
    }
}


def _signal(**overrides):
    signal = {
        "ticker": "BAESY",
        "timestamp_et": "2026-08-24T15:48:00-04:00",
        "tier": "WAIT",
        "score": 70,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "repair",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 1.0,
        "retest_status": "partial",
        "hold_status": "partial",
        "invalidation_condition": "below level",
        "invalidation_level": 0.9,
        "targets": [{"label": "T1", "level": 1.3, "reason": "test"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": ["hold"],
        "upgrade_trigger": "closed hold",
        "next_action": "wait",
        "discord_channel": "none",
        "capital_action": "no_trade",
        "reason": "forming",
    }
    signal.update(overrides)
    return signal


def _enriched():
    return {
        "ticker": "BAESY",
        "latest_close": 1.0,
        "structure_event": "BOS",
        "retest_status": "partial",
        "overhead_status": "clear",
        "volume_behavior": "neutral",
        "targets": [],
    }


def _run(content, *, stop_reason="end_turn", config=None):
    response = SimpleNamespace(content=content, stop_reason=stop_reason)
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    result = asyncio.run(
        claude_call(
            _enriched(),
            "SYSTEM",
            client,
            asyncio.Semaphore(1),
            config or CFG,
        )
    )
    return result, client


def test_configured_8192_budget_is_sent_to_anthropic():
    result, client = _run(
        [SimpleNamespace(type="text", text=json.dumps(_signal()))]
    )
    assert result["error_type"] is None
    kwargs = client.messages.create.await_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["max_tokens"] == 8192


def test_missing_config_budget_defaults_to_8192():
    result, client = _run(
        [SimpleNamespace(type="text", text=json.dumps(_signal()))],
        config={"claude": {"model": "claude-opus-5"}},
    )
    assert result["error_type"] is None
    assert client.messages.create.await_args.kwargs["max_tokens"] == 8192


def test_max_tokens_stop_reason_is_truncation_not_json_parse_error():
    result, client = _run(
        [SimpleNamespace(type="text", text='{"ticker":"BAESY","reason":"unterminated')],
        stop_reason="max_tokens",
    )
    assert result["signal"] is None
    assert result["error_type"] == "CLAUDE_OUTPUT_TRUNCATED"
    assert "stop_reason=max_tokens" in result["error_message"]
    assert client.messages.create.await_count == 1


def test_context_window_stop_reason_is_truncation():
    result, _ = _run(
        [SimpleNamespace(type="text", text='{"ticker":"BAESY"')],
        stop_reason="model_context_window_exceeded",
    )
    assert result["signal"] is None
    assert result["error_type"] == "CLAUDE_OUTPUT_TRUNCATED"


def test_end_turn_malformed_json_remains_json_parse_error():
    result, _ = _run(
        [SimpleNamespace(type="text", text='{"ticker":"BAESY","reason":"unterminated')],
        stop_reason="end_turn",
    )
    assert result["signal"] is None
    assert result["error_type"] == "JSON_PARSE_ERROR"


def test_truncated_snipe_prefix_can_never_become_trading_evidence():
    result, _ = _run(
        [SimpleNamespace(type="text", text='{"ticker":"BAESY","tier":"SNIPE_IT"')],
        stop_reason="max_tokens",
    )
    assert result["signal"] is None
    assert result["error_type"] == "CLAUDE_OUTPUT_TRUNCATED"


def test_legacy_magicmock_without_real_stop_reason_still_parses():
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(_signal()))]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    result = asyncio.run(
        claude_call(
            _enriched(),
            "SYSTEM",
            client,
            asyncio.Semaphore(1),
            CFG,
        )
    )

    assert result["error_type"] is None
    assert result["signal"]["ticker"] == "BAESY"

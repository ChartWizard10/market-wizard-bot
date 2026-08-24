"""Opus 5 content-block compatibility at the Anthropic boundary.

Thinking is internal model work, not scanner output or trading evidence.
Only visible text blocks may feed the strict JSON contract.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.claude_client import claude_call


def _signal(**overrides):
    base = {
        "ticker": "BAESY",
        "timestamp_et": "2026-08-24T15:08:00-04:00",
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
    base.update(overrides)
    return base


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


CFG = {
    "claude": {
        "model": "claude-opus-5",
        "max_tokens": 1200,
        "claude_concurrency": 1,
        "claude_min_seconds_between_calls": 0.0,
        "claude_max_input_tokens_per_minute_budget": 999999,
    }
}


def _thinking(text=None):
    obj = SimpleNamespace(type="thinking", thinking="internal", signature="sig")
    if text is not None:
        obj.text = text
    return obj


def _redacted():
    return SimpleNamespace(type="redacted_thinking", data="opaque")


def _text(value):
    return SimpleNamespace(type="text", text=value)


def _run(content):
    response = SimpleNamespace(content=content)
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return asyncio.run(
        claude_call(
            _enriched(),
            "SYSTEM",
            client,
            asyncio.Semaphore(1),
            CFG,
        )
    )


def test_text_only_response_parses():
    out = _run([_text(json.dumps(_signal()))])
    assert out["error_type"] is None
    assert out["signal"]["tier"] == "WAIT"


def test_opus_thinking_then_text_parses():
    out = _run([_thinking(), _text(json.dumps(_signal()))])
    assert out["error_type"] is None
    assert out["signal"]["ticker"] == "BAESY"


def test_redacted_thinking_then_text_parses():
    out = _run([_redacted(), _text(json.dumps(_signal()))])
    assert out["error_type"] is None
    assert out["signal"]["tier"] == "WAIT"


def test_multiple_thinking_blocks_then_text_parse():
    out = _run([_thinking(), _thinking(), _text(json.dumps(_signal()))])
    assert out["error_type"] is None


def test_multiple_text_blocks_are_joined_in_order():
    raw = json.dumps(_signal(), separators=(",", ":"))
    split = len(raw) // 2
    out = _run([_thinking(), _text(raw[:split]), _text(raw[split:])])
    assert out["error_type"] is None
    assert out["signal"]["ticker"] == "BAESY"


def test_thinking_only_is_shape_error_not_api_error():
    out = _run([_thinking()])
    assert out["signal"] is None
    assert out["error_type"] == "CLAUDE_RESPONSE_NO_TEXT"


def test_empty_content_is_shape_error_not_api_error():
    out = _run([])
    assert out["signal"] is None
    assert out["error_type"] == "CLAUDE_RESPONSE_NO_TEXT"


def test_thinking_cannot_become_trading_evidence():
    fake_snipe = json.dumps(_signal(tier="SNIPE_IT"))
    real_wait = json.dumps(_signal(tier="WAIT"))
    out = _run([_thinking(text=fake_snipe), _text(real_wait)])
    assert out["error_type"] is None
    assert out["signal"]["tier"] == "WAIT"


def test_thinking_json_without_text_is_never_parsed():
    out = _run([_thinking(text=json.dumps(_signal(tier="SNIPE_IT")))])
    assert out["signal"] is None
    assert out["error_type"] == "CLAUDE_RESPONSE_NO_TEXT"


def test_markdown_text_keeps_strict_rejection():
    raw = "```json\n" + json.dumps(_signal()) + "\n```"
    out = _run([_thinking(), _text(raw)])
    assert out["signal"] is None
    assert out["error_type"] == "markdown_wrapper"


def test_malformed_text_keeps_json_error():
    out = _run([_thinking(), _text("{bad")])
    assert out["signal"] is None
    assert out["error_type"] == "JSON_PARSE_ERROR"


def test_api_exception_remains_claude_api_error():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=Exception("500 Internal Server Error"))
    out = asyncio.run(
        claude_call(_enriched(), "SYSTEM", client, asyncio.Semaphore(1), CFG)
    )
    assert out["signal"] is None
    assert out["error_type"] == "CLAUDE_API_ERROR"


def test_rate_limit_remains_rate_limited():
    client = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=Exception("429 Too Many Requests: rate limit exceeded")
    )
    out = asyncio.run(
        claude_call(_enriched(), "SYSTEM", client, asyncio.Semaphore(1), CFG)
    )
    assert out["signal"] is None
    assert out["error_type"] == "claude_rate_limited"

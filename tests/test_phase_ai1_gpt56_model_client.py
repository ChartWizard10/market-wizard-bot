"""AI-1 — OpenAI GPT-5.6 production model-client contract.

All API calls are mocked. These tests prove provider/model routing, Structured
Outputs, failure semantics, deterministic result order, and no doctrine drift.
"""

import asyncio
import inspect
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import model_client


def _signal(ticker="AAPL"):
    return {
        "ticker": ticker,
        "timestamp_et": "2026-08-19T10:30:00-04:00",
        "tier": "WAIT",
        "score": 55,
        "setup_family": "none",
        "structure_event": "none",
        "trend_state": "basing",
        "sma_value_alignment": "mixed",
        "zone_type": "none",
        "trigger_level": None,
        "retest_status": "missing",
        "hold_status": "missing",
        "invalidation_condition": "none",
        "invalidation_level": None,
        "targets": [{"label": "T1", "level": None, "reason": "not computable"}],
        "risk_reward": None,
        "overhead_status": "unknown",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "wait",
        "discord_channel": "none",
        "capital_action": "no_trade",
        "reason": "No actionable setup.",
    }


def _enriched(ticker="AAPL"):
    return {
        "ticker": ticker,
        "current_price": 100.0,
        "latest_close": 100.0,
        "sma_value_alignment": "mixed",
        "structure_event": "none",
        "retest_status": "missing",
        "overhead_status": "unknown",
        "volume_behavior": "neutral",
        "targets": [],
    }


def _config():
    return {
        "model": {
            "provider": "openai",
            "name": "gpt-5.6",
            "max_output_tokens": 1200,
            "reasoning_effort": "medium",
            "concurrency": 1,
            "min_seconds_between_calls": 0.0,
            "max_input_tokens_per_minute_budget": 999999,
        }
    }


def _client(signal=None):
    client = MagicMock()
    response = MagicMock()
    response.output_text = json.dumps(signal or _signal())
    client.responses.create = AsyncMock(return_value=response)
    return client


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


def test_default_model_is_gpt_5_6():
    model, source = model_client.resolve_model({})
    assert model == "gpt-5.6"
    assert source == "DEFAULT"


def test_environment_model_override_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-terra")
    model, source = model_client.resolve_model(_config())
    assert model == "gpt-5.6-terra"
    assert source == "ENVIRONMENT"


def test_config_model_used_when_env_absent():
    model, source = model_client.resolve_model(_config())
    assert model == "gpt-5.6"
    assert source == "CONFIG"


def test_model_call_uses_responses_api_and_strict_schema():
    client = _client()
    result = asyncio.run(model_client.model_call(
        _enriched(), "SYSTEM", client, asyncio.Semaphore(1), _config()
    ))
    assert result["signal"]["tier"] == "WAIT"
    kwargs = client.responses.create.await_args.kwargs
    assert kwargs["model"] == "gpt-5.6"
    assert kwargs["instructions"] == "SYSTEM"
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert kwargs["max_output_tokens"] == 1200
    fmt = kwargs["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "market_wizard_signal"
    assert fmt["schema"]["additionalProperties"] is False
    assert set(fmt["schema"]["required"]) == model_client._REQUIRED_KEYS


def test_model_call_rate_limit_is_not_a_market_rejection():
    client = _client()
    client.responses.create = AsyncMock(side_effect=RuntimeError("429 rate limit"))
    result = asyncio.run(model_client.model_call(
        _enriched(), "SYSTEM", client, asyncio.Semaphore(1), _config()
    ))
    assert result["signal"] is None
    assert result["error_type"] == "model_rate_limited"


def test_model_call_api_error_is_generic_provider_failure():
    client = _client()
    client.responses.create = AsyncMock(side_effect=RuntimeError("network timeout"))
    result = asyncio.run(model_client.model_call(
        _enriched(), "SYSTEM", client, asyncio.Semaphore(1), _config()
    ))
    assert result["signal"] is None
    assert result["error_type"] == "MODEL_API_ERROR"


def test_batch_preserves_candidate_order_and_one_call_per_candidate():
    client = MagicMock()

    async def create(**kwargs):
        ticker = kwargs["input"].splitlines()[0].split(":", 1)[1].strip()
        response = MagicMock()
        response.output_text = json.dumps(_signal(ticker=ticker))
        return response

    client.responses.create = AsyncMock(side_effect=create)
    candidates = [_enriched("AAA"), _enriched("BBB"), _enriched("CCC")]
    results = asyncio.run(model_client.async_model_scan(
        candidates, "SYSTEM", client, _config()
    ))
    assert [r["ticker"] for r in results] == ["AAA", "BBB", "CCC"]
    assert client.responses.create.await_count == 3


def test_production_model_client_contains_no_anthropic_api_call():
    src = inspect.getsource(model_client)
    assert "AsyncAnthropic" not in src
    assert ".messages.create(" not in src
    assert "responses.create" in src


def test_signal_schema_matches_hardened_parser_required_keys():
    assert set(model_client.SIGNAL_JSON_SCHEMA["properties"]) == model_client._REQUIRED_KEYS
    assert set(model_client.SIGNAL_JSON_SCHEMA["required"]) == model_client._REQUIRED_KEYS

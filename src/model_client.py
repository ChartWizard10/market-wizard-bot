"""OpenAI GPT-5.6 deep-analysis boundary for Chart Wizard.

This module is the production model client. GPT-5.6 is an analyst/classifier;
deterministic tiering remains sovereign over capital, routing and hard gates.

The signal prompt/parser contract is intentionally reused from the hardened
legacy client during AI-1 so provider migration cannot silently rewrite trading
doctrine. A later provider-neutral cleanup may relocate those pure helpers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from src.claude_client import (
    _RateGovernor,
    _estimate_tokens,
    _ENUM_FIELDS,
    _REQUIRED_KEYS,
    build_prompt,
    load_system_prompt,
    parse_and_validate_json,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.6"
MODEL_SOURCE_ENVIRONMENT = "ENVIRONMENT"
MODEL_SOURCE_CONFIG = "CONFIG"
MODEL_SOURCE_DEFAULT = "DEFAULT"


def resolve_model(config: dict) -> tuple[str, str]:
    """Resolve runtime model: OPENAI_MODEL -> config.model.name -> gpt-5.6."""
    env_model = str(os.getenv("OPENAI_MODEL") or "").strip()
    if env_model:
        return env_model, MODEL_SOURCE_ENVIRONMENT

    model_cfg = config.get("model", {}) if isinstance(config, dict) else {}
    if isinstance(model_cfg, dict):
        config_model = str(model_cfg.get("name") or "").strip()
        if config_model:
            return config_model, MODEL_SOURCE_CONFIG

    return DEFAULT_MODEL, MODEL_SOURCE_DEFAULT


def _is_rate_limit_error(exc: Exception) -> bool:
    """True for OpenAI 429/rate-limit failures without requiring live API access."""
    try:
        import openai
        if isinstance(exc, openai.RateLimitError):
            return True
    except (ImportError, AttributeError, TypeError):
        pass
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
        or "too many requests" in msg
    )


def _signal_schema() -> dict:
    """Strict JSON Schema matching the scanner's existing signal contract."""
    def enum_schema(field: str) -> dict:
        return {"type": "string", "enum": sorted(_ENUM_FIELDS[field])}

    properties = {
        "ticker": {"type": "string"},
        "timestamp_et": {"type": "string"},
        "tier": enum_schema("tier"),
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "setup_family": enum_schema("setup_family"),
        "structure_event": enum_schema("structure_event"),
        "trend_state": enum_schema("trend_state"),
        "sma_value_alignment": enum_schema("sma_value_alignment"),
        "zone_type": enum_schema("zone_type"),
        "trigger_level": {"type": ["number", "null"]},
        "retest_status": enum_schema("retest_status"),
        "hold_status": enum_schema("hold_status"),
        "invalidation_condition": {"type": "string"},
        "invalidation_level": {"type": ["number", "null"]},
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "level": {"type": ["number", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["label", "level", "reason"],
                "additionalProperties": False,
            },
        },
        "risk_reward": {"type": ["number", "null"]},
        "overhead_status": enum_schema("overhead_status"),
        "forced_participation": {"type": "string"},
        "missing_conditions": {"type": "array", "items": {"type": "string"}},
        "upgrade_trigger": {"type": "string"},
        "next_action": {"type": "string"},
        "discord_channel": enum_schema("discord_channel"),
        "capital_action": enum_schema("capital_action"),
        "reason": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(_REQUIRED_KEYS),
        "additionalProperties": False,
    }


SIGNAL_JSON_SCHEMA = _signal_schema()


async def model_call(
    enriched: dict,
    system_prompt: str,
    client: Any,
    semaphore: asyncio.Semaphore,
    config: dict,
) -> dict:
    """Send one enriched ticker to OpenAI GPT-5.6 and validate the signal."""
    ticker = enriched.get("ticker", "UNKNOWN")
    model_cfg = config.get("model", {}) if isinstance(config, dict) else {}
    model_cfg = model_cfg if isinstance(model_cfg, dict) else {}
    model, _source = resolve_model(config)
    max_output_tokens = int(model_cfg.get("max_output_tokens", 1200))
    reasoning_effort = str(model_cfg.get("reasoning_effort", "medium") or "medium").strip()
    prompt_text = build_prompt(enriched)

    kwargs = {
        "model": model,
        "instructions": system_prompt,
        "input": prompt_text,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "market_wizard_signal",
                "schema": SIGNAL_JSON_SCHEMA,
                "strict": True,
            }
        },
    }
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    async with semaphore:
        try:
            response = await client.responses.create(**kwargs)
            response_text = str(getattr(response, "output_text", "") or "")
            if not response_text.strip():
                raise RuntimeError("OpenAI response contained no output_text")
        except Exception as exc:
            if _is_rate_limit_error(exc):
                log.warning("MODEL_RATE_LIMITED: %s: %s", ticker, exc)
                return {
                    "ticker": ticker,
                    "signal": None,
                    "error_type": "model_rate_limited",
                    "error_message": str(exc),
                }
            log.warning("MODEL_API_ERROR: %s: %s", ticker, exc)
            return {
                "ticker": ticker,
                "signal": None,
                "error_type": "MODEL_API_ERROR",
                "error_message": str(exc),
            }

    signal, error_type, error_message = parse_and_validate_json(response_text)
    if signal is None:
        log.warning("%s: %s: %s", error_type, ticker, error_message)
        return {
            "ticker": ticker,
            "signal": None,
            "error_type": error_type,
            "error_message": error_message,
        }

    return {
        "ticker": ticker,
        "signal": signal,
        "error_type": None,
        "error_message": None,
    }


async def async_model_scan(
    candidates: list,
    system_prompt: str,
    client: Any,
    config: dict,
    _governor: _RateGovernor | None = None,
) -> list:
    """Analyze candidates in deterministic input order with conservative pacing."""
    model_cfg = config.get("model", {}) if isinstance(config, dict) else {}
    model_cfg = model_cfg if isinstance(model_cfg, dict) else {}

    max_concurrent = int(model_cfg.get("concurrency", 1))
    min_gap = float(model_cfg.get("min_seconds_between_calls", 1.0))
    tpm_budget = int(model_cfg.get("max_input_tokens_per_minute_budget", 250000))

    semaphore = asyncio.Semaphore(max_concurrent)
    governor = _governor if _governor is not None else _RateGovernor(
        min_gap_secs=min_gap,
        max_tpm=tpm_budget,
    )

    selected_model, model_source = resolve_model(config)
    log.info("MODEL_SELECTED: model=%s source=%s", selected_model, model_source)

    results = []
    for enriched in candidates:
        prompt_text = build_prompt(enriched)
        estimated_tokens = _estimate_tokens(system_prompt + prompt_text)
        sleep_secs = await governor.acquire(estimated_tokens)
        if sleep_secs > 0.0:
            log.info(
                "model_rate_governor_sleep: %.1fs token_budget_used=%d/%d",
                sleep_secs,
                governor.tokens_in_window,
                tpm_budget,
            )
        results.append(
            await model_call(enriched, system_prompt, client, semaphore, config)
        )

    return results

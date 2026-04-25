"""Async Claude API wrapper. Sends structured prompts, validates strict JSON responses."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "ticker", "timestamp_et", "tier", "score", "setup_family", "structure_event",
    "trend_state", "sma_value_alignment", "zone_type", "trigger_level",
    "retest_status", "hold_status", "invalidation_condition", "invalidation_level",
    "targets", "risk_reward", "overhead_status", "forced_participation",
    "missing_conditions", "upgrade_trigger", "next_action", "discord_channel",
    "capital_action", "reason",
}

_ENUM_FIELDS: dict[str, set] = {
    "tier":               {"SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"},
    "setup_family":       {"continuation", "reclaim", "compression_to_expansion",
                           "reversal", "squeeze", "exhaustion_trap", "none"},
    "structure_event":    {"BOS", "MSS", "CHOCH", "reclaim", "accepted_break",
                           "failed_breakdown_reclaim", "none"},
    "trend_state":        {"fresh_expansion", "mature_continuation", "repair",
                           "transition", "failure", "basing"},
    "sma_value_alignment": {"supportive", "mixed", "hostile", "unavailable"},
    "zone_type":          {"FVG", "OB", "demand", "flip_zone", "support_cluster", "none"},
    "retest_status":      {"confirmed", "partial", "missing", "failed"},
    "hold_status":        {"confirmed", "partial", "missing", "failed"},
    "overhead_status":    {"clear", "moderate", "blocked", "unknown"},
    "discord_channel":    {"#snipe-signals", "#starter-signals", "#near-entry-watch", "none"},
    "capital_action":     {"full_quality_allowed", "starter_only", "wait_no_capital", "no_trade"},
}

# Disabled indicators must never appear in prompt payloads
_DISABLED_INDICATORS = {"rsi", "macd", "bollinger_bands", "stochastic"}

_TIER_CHANNEL_MAP = {
    "SNIPE_IT":   "#snipe-signals",
    "STARTER":    "#starter-signals",
    "NEAR_ENTRY": "#near-entry-watch",
    "WAIT":       "none",
}

_TIER_CAPITAL_MAP = {
    "SNIPE_IT":   "full_quality_allowed",
    "STARTER":    "starter_only",
    "NEAR_ENTRY": "wait_no_capital",
    "WAIT":       "no_trade",
}


# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------

def load_system_prompt(path: str = "prompts/market_wizard_system.md") -> str:
    """Load the system prompt from the specified path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"System prompt not found: {path}")
    return p.read_text()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(enriched: dict, prefilter_result: dict | None = None) -> str:
    """Build structured context string for Claude. No disabled indicators included."""
    ticker = enriched.get("ticker", "UNKNOWN")
    lines = [f"TICKER: {ticker}"]

    # Price context
    close = enriched.get("latest_close") or enriched.get("close")
    if close is not None:
        lines.append(f"LATEST_CLOSE: {close}")

    # SMA levels — no disabled indicators
    sma20 = enriched.get("sma20")
    sma50 = enriched.get("sma50")
    sma200 = enriched.get("sma200")
    if sma20 is not None:
        lines.append(f"SMA20: {sma20}")
    if sma50 is not None:
        lines.append(f"SMA50: {sma50}")
    if sma200 is not None:
        lines.append(f"SMA200: {sma200}")

    alignment = enriched.get("sma_value_alignment")
    if alignment:
        lines.append(f"SMA_VALUE_ALIGNMENT: {alignment}")

    ext = enriched.get("price_extension_from_sma20_pct")
    if ext is not None:
        lines.append(f"PRICE_EXTENSION_FROM_SMA20_PCT: {ext:.2f}")

    # ATR
    atr = enriched.get("atr")
    if atr is not None:
        lines.append(f"ATR: {atr:.4f}")

    # Structure
    event = enriched.get("structure_event", "none")
    lines.append(f"STRUCTURE_EVENT: {event}")

    wick_only = enriched.get("wick_only_break", False)
    if wick_only:
        lines.append("WICK_ONLY_BREAK: true")

    # Zone
    fvg = enriched.get("fvg")
    if fvg:
        lines.append(
            f"FVG: top={fvg.get('fvg_top')}, mid={fvg.get('fvg_mid')}, "
            f"bot={fvg.get('fvg_bot')}, filled={fvg.get('fvg_filled')}, "
            f"price_in_zone={fvg.get('price_in_fvg')}"
        )
    else:
        lines.append("FVG: none")

    ob = enriched.get("ob")
    if ob:
        lines.append(
            f"OB: hi={ob.get('ob_hi')}, lo={ob.get('ob_lo')}, "
            f"mitigated={ob.get('mitigated')}, price_at_ob={ob.get('price_at_ob')}"
        )
    else:
        lines.append("OB: none")

    # Retest and overhead
    retest = enriched.get("retest_status", "missing")
    lines.append(f"RETEST_STATUS: {retest}")

    overhead = enriched.get("overhead_status", "unknown")
    lines.append(f"OVERHEAD_STATUS: {overhead}")

    # Volume
    vol_behavior = enriched.get("volume_behavior", "unknown")
    lines.append(f"VOLUME_BEHAVIOR: {vol_behavior}")

    # Invalidation and targets
    invalidation = enriched.get("invalidation_level")
    if invalidation is not None:
        lines.append(f"ESTIMATED_INVALIDATION_LEVEL: {invalidation:.4f}")

    targets = enriched.get("targets", [])
    if targets:
        for t in targets:
            lines.append(f"TARGET: label={t.get('label')}, level={t.get('level')}, reason={t.get('reason')}")
    else:
        lines.append("TARGETS: none")

    rr = enriched.get("estimated_rr")
    if rr is not None:
        lines.append(f"ESTIMATED_RR: {rr:.2f}")

    # Prefilter context
    if prefilter_result:
        score = prefilter_result.get("prefilter_score")
        if score is not None:
            lines.append(f"PREFILTER_SCORE: {score}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON parsing and validation
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the first JSON object from a response."""
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    # Find the first { ... } block
    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return text[start:].strip()


def parse_and_validate_json(
    response_text: str,
) -> tuple[dict | None, str | None, str | None]:
    """Parse and validate a Claude JSON response.

    Returns:
        (signal_dict, error_type, error_message)
        On success: (signal_dict, None, None)
        On failure: (None, error_type, error_message)

    error_type values: JSON_PARSE_ERROR, JSON_SCHEMA_ERROR, JSON_ENUM_ERROR
    """
    raw = _extract_json(response_text)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, "JSON_PARSE_ERROR", str(exc)

    if not isinstance(data, dict):
        return None, "JSON_PARSE_ERROR", "top-level value is not an object"

    # Required key check
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        return None, "JSON_SCHEMA_ERROR", f"missing keys: {sorted(missing)}"

    # Enum validation
    for field, allowed in _ENUM_FIELDS.items():
        val = data.get(field)
        if val not in allowed:
            return None, "JSON_ENUM_ERROR", f"{field}={val!r} not in {sorted(allowed)}"

    # risk_reward: must be number or null
    rr = data.get("risk_reward")
    if rr is not None and not isinstance(rr, (int, float)):
        log.warning("risk_reward is non-numeric (%r) — treating as null", rr)
        data["risk_reward"] = None

    # targets: must be a list
    if not isinstance(data.get("targets"), list):
        return None, "JSON_SCHEMA_ERROR", "targets must be a list"

    # score: clamp to int 0–100
    score = data.get("score")
    if not isinstance(score, (int, float)):
        data["score"] = 0
    else:
        data["score"] = max(0, min(100, int(score)))

    return data, None, None


# ---------------------------------------------------------------------------
# Single Claude call
# ---------------------------------------------------------------------------

async def claude_call(
    enriched: dict,
    system_prompt: str,
    client: Any,
    semaphore: asyncio.Semaphore,
    config: dict,
) -> dict:
    """Send one enriched ticker to Claude. Returns result dict with signal or error info."""
    ticker = enriched.get("ticker", "UNKNOWN")
    claude_cfg = config.get("claude", {})
    model = claude_cfg.get("model", "claude-sonnet-4-6")
    max_tokens = claude_cfg.get("max_tokens", 1200)

    prompt_text = build_prompt(enriched)

    async with semaphore:
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt_text}],
            )
            response_text = response.content[0].text
        except Exception as exc:
            log.warning("CLAUDE_API_ERROR: %s: %s", ticker, exc)
            return {
                "ticker": ticker,
                "signal": None,
                "error_type": "CLAUDE_API_ERROR",
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


# ---------------------------------------------------------------------------
# Batch async scan
# ---------------------------------------------------------------------------

async def async_claude_scan(
    candidates: list,
    system_prompt: str,
    client: Any,
    config: dict,
) -> list:
    """Run Claude analysis on all candidates with concurrency limit.

    Args:
        candidates: list of enriched dicts (already prefiltered)
        system_prompt: loaded system prompt string
        client: anthropic AsyncAnthropic client
        config: doctrine_config dict

    Returns:
        list of result dicts, one per candidate, in input order
    """
    max_concurrent = config.get("claude", {}).get("max_concurrent_calls", 8)
    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = [
        claude_call(enriched, system_prompt, client, semaphore, config)
        for enriched in candidates
    ]

    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)

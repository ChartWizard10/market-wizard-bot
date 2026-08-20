"""Production Anthropic model boundary — prompt, call, parser, pacing.

Production deep analysis is Anthropic Claude. ``main.py`` instantiates
``anthropic.AsyncAnthropic`` and passes it straight through the scheduler to
``claude_call``, which calls ``client.messages.create(...)`` natively. There is
no provider adapter and no cross-provider fallback: if Anthropic is
unavailable the scanner fails closed.

The model is an ANALYST. It never owns market data, proof truth, tier legality,
risk law, capital law or routing — those belong to the deterministic scanner
organs downstream.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anthropic model routing (Phase MR-1, restored to production by AI-2R).
#
#     1. ANTHROPIC_MODEL environment variable (non-empty, trimmed)
#     2. config["claude"]["model"]
#     3. DEFAULT_CLAUDE_MODEL
#
# The default is Opus 5 so production stays on the intended model even if the
# Railway override is temporarily absent. An emergency model rollback stays
# WITHIN Anthropic (e.g. ANTHROPIC_MODEL=claude-sonnet-4-6) — it changes the
# model, never the provider.
#
# Deliberately no model whitelist and no catalog lookup: the messages.create
# request is the runtime authority on whether an ID exists. An explicitly
# selected model is never silently replaced after an API rejection.
# ---------------------------------------------------------------------------

DEFAULT_CLAUDE_MODEL = "claude-opus-5"

MODEL_SOURCE_ENVIRONMENT = "ENVIRONMENT"
MODEL_SOURCE_CONFIG = "CONFIG"
MODEL_SOURCE_DEFAULT = "DEFAULT"


def resolve_claude_model(config: dict) -> tuple[str, str]:
    """Return (model, source) for this runtime.

    An empty or whitespace-only value at any level means "not supplied" and
    falls through — an empty model string is never sent to Anthropic.
    """
    env_model = str(os.getenv("ANTHROPIC_MODEL") or "").strip()
    if env_model:
        return env_model, MODEL_SOURCE_ENVIRONMENT

    claude_cfg = config.get("claude", {}) if isinstance(config, dict) else {}
    config_model = str(claude_cfg.get("model") or "").strip()
    if config_model:
        return config_model, MODEL_SOURCE_CONFIG

    return DEFAULT_CLAUDE_MODEL, MODEL_SOURCE_DEFAULT


# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Conservative token estimate: chars // 4."""
    return max(1, len(text) // 4)


def _is_rate_limit_error(exc: Exception) -> bool:
    """True for Anthropic 429 / rate-limit errors."""
    try:
        import anthropic
        if isinstance(exc, anthropic.RateLimitError):
            return True
    except (ImportError, AttributeError):
        pass
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "rate_limit" in msg or "too many requests" in msg


class _RateGovernor:
    """Paces model calls to stay within TPM budget and minimum inter-call gap.

    Both _clock and _sleep are injectable for unit-test control.
    """

    def __init__(
        self,
        min_gap_secs: float,
        max_tpm: int,
        _clock=None,
        _sleep=None,
    ):
        self._min_gap = float(min_gap_secs)
        self._max_tpm = int(max_tpm)
        self._clock = _clock or time.monotonic
        self._sleep = _sleep or asyncio.sleep
        self._last_call_at: float | None = None
        self._window_start: float | None = None
        self._tokens_in_window: int = 0

    @property
    def tokens_in_window(self) -> int:
        return self._tokens_in_window

    async def acquire(self, estimated_tokens: int) -> float:
        """Wait if necessary; return total seconds slept."""
        now = self._clock()
        total_sleep = 0.0

        if self._window_start is None or now - self._window_start >= 60.0:
            self._window_start = now
            self._tokens_in_window = 0

        if self._last_call_at is not None:
            elapsed = now - self._last_call_at
            if elapsed < self._min_gap:
                gap_sleep = self._min_gap - elapsed
                await self._sleep(gap_sleep)
                total_sleep += gap_sleep
                now = self._clock()

        if self._tokens_in_window + estimated_tokens > self._max_tpm:
            window_age = now - self._window_start
            remaining = max(0.0, 60.0 - window_age)
            if remaining > 0.0:
                await self._sleep(remaining)
                total_sleep += remaining
                now = self._clock()
            self._window_start = now
            self._tokens_in_window = 0

        self._tokens_in_window += estimated_tokens
        self._last_call_at = self._clock()
        return total_sleep


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


def _append_setup_family_context(lines: list[str], enriched: dict) -> None:
    """Append compact normalized SFC evidence to the Claude input payload.

    Family evidence is deterministic context, not capital authority. The model
    sees lifecycle/state/location/geometry so it can reason about VCP, SMA
    cradle, gap-fill and break/retest candidates that the generic FVG/OB view
    alone cannot express.
    """
    evidence = enriched.get("setup_family_evidence")
    if not isinstance(evidence, dict):
        return

    primary = str(evidence.get("primary_family") or "NONE")
    if primary == "NONE":
        return

    families = evidence.get("families")
    families = families if isinstance(families, dict) else {}
    primary_obj = families.get(primary)
    primary_obj = primary_obj if isinstance(primary_obj, dict) else {}

    lines.append(f"SETUP_FAMILY_PRIMARY: {primary}")
    lines.append(
        f"SETUP_FAMILY_STATE: {evidence.get('primary_state') or primary_obj.get('state') or 'UNKNOWN'}"
    )
    lines.append(
        f"SETUP_FAMILY_SCORE: {int(evidence.get('primary_family_score') or primary_obj.get('family_score') or 0)}"
    )
    lines.append(f"SETUP_FAMILY_WATCH_READY: {bool(evidence.get('watch_ready') or primary_obj.get('watch_ready'))}")
    lines.append(f"SETUP_FAMILY_ADMISSION_READY: {bool(evidence.get('admission_ready') or primary_obj.get('admission_ready'))}")
    lines.append(
        "SETUP_FAMILY_ENTRY_STRUCTURE_VALID: "
        f"{bool(evidence.get('entry_structure_valid') or primary_obj.get('entry_structure_valid'))}"
    )

    invalidation = (
        evidence.get("primary_invalidation_level")
        if evidence.get("primary_invalidation_level") is not None
        else primary_obj.get("invalidation_level")
    )
    target = (
        evidence.get("primary_target_1")
        if evidence.get("primary_target_1") is not None
        else primary_obj.get("target_1")
    )
    rr = (
        evidence.get("primary_rr_to_t1")
        if evidence.get("primary_rr_to_t1") is not None
        else primary_obj.get("rr_to_t1")
    )
    if invalidation is not None:
        lines.append(f"SETUP_FAMILY_INVALIDATION: {invalidation}")
    if target is not None:
        lines.append(f"SETUP_FAMILY_TARGET_1: {target}")
    if rr is not None:
        lines.append(f"SETUP_FAMILY_RR_TO_T1: {rr}")

    lines.append(f"SETUP_FAMILY_PATH_STATUS: {primary_obj.get('path_status', 'UNKNOWN')}")

    blockers = primary_obj.get("blockers") or []
    soft_caps = primary_obj.get("soft_caps") or []
    if blockers:
        lines.append("SETUP_FAMILY_BLOCKERS: " + ", ".join(str(x) for x in blockers))
    if soft_caps:
        lines.append("SETUP_FAMILY_SOFT_CAPS: " + ", ".join(str(x) for x in soft_caps))

    metrics = primary_obj.get("metrics")
    if isinstance(metrics, dict) and metrics:
        lines.append(
            "SETUP_FAMILY_METRICS: "
            + json.dumps(metrics, sort_keys=True, separators=(",", ":"), default=str)
        )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(enriched: dict, prefilter_result: dict | None = None) -> str:
    """Build structured context for the production Claude analyst boundary."""
    ticker = enriched.get("ticker", "UNKNOWN")
    lines = [f"TICKER: {ticker}"]

    daily_ctx = enriched.get("daily_bar_context")
    daily_ctx = daily_ctx if isinstance(daily_ctx, dict) else {}
    daily_status = str(daily_ctx.get("status") or "").upper().strip()

    if daily_status:
        lines.append(f"DAILY_BAR_STATUS: {daily_status}")
        current_price = enriched.get("current_price")
        if current_price is not None:
            lines.append(f"CURRENT_PRICE: {current_price}")
        last_closed = enriched.get("last_closed_daily_close")
        if last_closed is not None:
            lines.append(f"LAST_CLOSED_DAILY_CLOSE: {last_closed}")
    else:
        close = enriched.get("latest_close") or enriched.get("close")
        if close is not None:
            lines.append(f"LATEST_CLOSE: {close}")

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

    atr = enriched.get("atr")
    if atr is not None:
        lines.append(f"ATR: {atr:.4f}")

    event = enriched.get("structure_event", "none")
    lines.append(f"STRUCTURE_EVENT: {event}")

    wick_only = enriched.get("wick_only_break", False)
    if wick_only:
        lines.append("WICK_ONLY_BREAK: true")

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

    retest = enriched.get("retest_status", "missing")
    lines.append(f"RETEST_STATUS: {retest}")

    overhead = enriched.get("overhead_status", "unknown")
    lines.append(f"OVERHEAD_STATUS: {overhead}")

    vol_behavior = enriched.get("volume_behavior", "unknown")
    lines.append(f"VOLUME_BEHAVIOR: {vol_behavior}")

    if daily_status:
        lines.append("DAILY_STRUCTURE_SOURCE: CLOSED_BARS")
        lines.append(
            f"DAILY_RETEST_PROOF: {enriched.get('daily_retest_proof', 'CLOSED_CONFIRMED')}"
        )
        lines.append("DAILY_VOLUME_SOURCE: LAST_COMPLETED_SESSION")

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

    # SFC-2B deterministic family lifecycle context for Claude.
    _append_setup_family_context(lines, enriched)

    if prefilter_result:
        score = prefilter_result.get("prefilter_score")
        if score is not None:
            lines.append(f"PREFILTER_SCORE: {score}")
        admission_score = prefilter_result.get("admission_rank_score")
        if admission_score is not None:
            lines.append(f"ADMISSION_RANK_SCORE: {admission_score}")
        admission_source = prefilter_result.get("admission_source")
        if admission_source:
            lines.append(f"ADMISSION_SOURCE: {admission_source}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON parsing and validation
# ---------------------------------------------------------------------------

def parse_and_validate_json(
    response_text: str,
) -> tuple[dict | None, str | None, str | None]:
    """Parse and validate a strict model JSON response.

    The model must return pure JSON only — no markdown fences, no prose wrapper.
    Any non-JSON wrapping is rejected rather than silently stripped.
    """
    stripped = response_text.strip()

    if "```" in stripped:
        return None, "markdown_wrapper", "response contains markdown code fences — JSON only"
    if not stripped.startswith("{"):
        return None, "non_json_wrapper", "response does not begin with '{' — JSON only"

    try:
        decoder = json.JSONDecoder()
        data, end_idx = decoder.raw_decode(stripped)
        trailing = stripped[end_idx:].strip()
        if trailing:
            return None, "non_json_wrapper", "response contains prose after JSON object"
    except (json.JSONDecodeError, ValueError) as exc:
        return None, "JSON_PARSE_ERROR", str(exc)

    if not isinstance(data, dict):
        return None, "JSON_PARSE_ERROR", "top-level value is not an object"

    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        return None, "JSON_SCHEMA_ERROR", f"missing keys: {sorted(missing)}"

    for field, allowed in _ENUM_FIELDS.items():
        val = data.get(field)
        if val not in allowed:
            return None, "JSON_ENUM_ERROR", f"{field}={val!r} not in {sorted(allowed)}"

    rr = data.get("risk_reward")
    if rr is not None and not isinstance(rr, (int, float)):
        log.warning("risk_reward is non-numeric (%r) — treating as null", rr)
        data["risk_reward"] = None

    if not isinstance(data.get("targets"), list):
        return None, "JSON_SCHEMA_ERROR", "targets must be a list"
    if not isinstance(data.get("missing_conditions"), list):
        return None, "JSON_SCHEMA_ERROR", "missing_conditions must be a list"

    score = data.get("score")
    if not isinstance(score, (int, float)):
        data["score"] = 0
    else:
        data["score"] = max(0, min(100, int(score)))

    return data, None, None


# ---------------------------------------------------------------------------
# Historical single Claude call compatibility path
# ---------------------------------------------------------------------------

async def claude_call(
    enriched: dict,
    system_prompt: str,
    client: Any,
    semaphore: asyncio.Semaphore,
    config: dict,
) -> dict:
    """Send one enriched ticker to Claude. Returns a result dict with the
    parsed signal or structured error info. Never raises."""
    ticker = enriched.get("ticker", "UNKNOWN")
    claude_cfg = config.get("claude", {})
    model, _model_source = resolve_claude_model(config)
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
            if _is_rate_limit_error(exc):
                log.warning("CLAUDE_RATE_LIMITED: %s: %s", ticker, exc)
                return {
                    "ticker": ticker,
                    "signal": None,
                    "error_type": "claude_rate_limited",
                    "error_message": str(exc),
                }
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
# Historical batch compatibility path
# ---------------------------------------------------------------------------

async def async_claude_scan(
    candidates: list,
    system_prompt: str,
    client: Any,
    config: dict,
    _governor: "_RateGovernor | None" = None,
) -> list:
    """Run historical scheduler-compatible analysis in deterministic order."""
    claude_cfg = config.get("claude", {})
    max_concurrent = int(
        claude_cfg.get("claude_concurrency", claude_cfg.get("max_concurrent_calls", 1))
    )
    min_gap = float(claude_cfg.get("claude_min_seconds_between_calls", 4.0))
    tpm_budget = int(claude_cfg.get("claude_max_input_tokens_per_minute_budget", 25000))

    semaphore = asyncio.Semaphore(max_concurrent)
    governor = _governor if _governor is not None else _RateGovernor(
        min_gap_secs=min_gap,
        max_tpm=tpm_budget,
    )

    selected_model, model_source = resolve_claude_model(config)
    log.info("CLAUDE_MODEL_SELECTED: model=%s source=%s", selected_model, model_source)

    results = []
    for enriched in candidates:
        prompt_text = build_prompt(enriched)
        estimated_tokens = _estimate_tokens(system_prompt + prompt_text)
        sleep_secs = await governor.acquire(estimated_tokens)
        if sleep_secs > 0.0:
            log.info(
                "rate_governor_sleep: %.1fs token_budget_used=%d/%d",
                sleep_secs, governor.tokens_in_window, tpm_budget,
            )
        result = await claude_call(enriched, system_prompt, client, semaphore, config)
        results.append(result)

    return results

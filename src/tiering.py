"""Deterministic tier validation. Final authority over all tier decisions.

Claude's output is the starting classifier only. This module applies hard vetoes,
downgrade logic, and routing corrections that Claude cannot override.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

TIERS = ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT")

CHANNEL_MAP = {
    "SNIPE_IT":   "#snipe-signals",
    "STARTER":    "#starter-signals",
    "NEAR_ENTRY": "#near-entry-watch",
    "WAIT":       "none",
}

CAPITAL_MAP = {
    "SNIPE_IT":   "full_quality_allowed",
    "STARTER":    "starter_only",
    "NEAR_ENTRY": "wait_no_capital",
    "WAIT":       "no_trade",
}

# ---------------------------------------------------------------------------
# Veto sets (strings match prefilter.py VETO_* constants)
# ---------------------------------------------------------------------------

# Block SNIPE_IT and STARTER entry; NEAR_ENTRY may still alert for these
_ENTRY_BLOCKING_VETOES = {
    "data_empty",
    "data_error",
    "insufficient_bars",
    "stale_data",
    "no_clear_structure",
    "no_clear_invalidation_estimate",
    "no_target_path",
    "overhead_blocked",
    "price_too_extended",
    "retest_failed",
    "mid_range_no_edge",
    "hostile_value_alignment",
    "rr_below_threshold_estimate",
}

# Block ALL alert tiers — force WAIT regardless of score or Claude output.
# no_clear_structure is here because NEAR_ENTRY requires structural proximity;
# with no structure at all there is no valid watch alert.
_ALL_ALERT_BLOCKING_VETOES = {
    "data_empty",
    "data_error",
    "insufficient_bars",
    "stale_data",
    "no_clear_structure",
    "retest_failed",
    "mid_range_no_edge",
}


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

def _entry_gate_failures(
    signal: dict,
    prefilter_vetoes: list,
    min_rr: float,
    current_price: float | None = None,
) -> list[str]:
    """Return failure reasons for the entry gates shared by SNIPE_IT and STARTER."""
    failures: list[str] = []

    retest = signal.get("retest_status", "missing")
    if retest != "confirmed":
        failures.append(f"retest_status={retest!r} (need confirmed)")

    hold = signal.get("hold_status", "missing")
    if hold != "confirmed":
        failures.append(f"hold_status={hold!r} (need confirmed)")

    ic = signal.get("invalidation_condition", "")
    if not ic or str(ic).lower() == "none":
        failures.append("invalidation_condition empty")

    if signal.get("invalidation_level") is None:
        failures.append("invalidation_level null")

    targets = signal.get("targets", [])
    if not isinstance(targets, list) or not targets:
        failures.append("targets empty")

    rr = signal.get("risk_reward")
    if rr is not None and rr < min_rr:
        failures.append(f"risk_reward={rr:.2f} < min_rr={min_rr}")

    if signal.get("overhead_status") == "blocked":
        failures.append("overhead_status=blocked")

    if signal.get("structure_event", "none") == "none":
        failures.append("structure_event=none")

    if signal.get("sma_value_alignment") == "hostile":
        failures.append("sma_value_alignment=hostile")

    active_block = set(prefilter_vetoes) & _ENTRY_BLOCKING_VETOES
    if active_block:
        failures.append(f"prefilter_hard_veto: {sorted(active_block)}")

    # Semantic price sanity — geometry relationship checks
    failures.extend(_semantic_price_sanity_failures(signal, current_price))

    return failures


def _snipe_gate_failures(
    signal: dict,
    prefilter_vetoes: list,
    score: int,
    config: dict,
    current_price: float | None = None,
) -> list[str]:
    tier_cfg = config.get("tiers", {}).get("snipe_it", {})
    min_score = tier_cfg.get("min_score", 85)
    min_rr = tier_cfg.get("min_rr", 3.0)

    failures = _entry_gate_failures(signal, prefilter_vetoes, min_rr, current_price)

    if score < min_score:
        failures.append(f"score={score} < snipe_min_score={min_score}")

    return failures


def _starter_gate_failures(
    signal: dict,
    prefilter_vetoes: list,
    score: int,
    config: dict,
    current_price: float | None = None,
) -> list[str]:
    tier_cfg = config.get("tiers", {}).get("starter", {})
    min_score = tier_cfg.get("min_score", 75)
    min_rr = tier_cfg.get("min_rr", 3.0)

    failures = _entry_gate_failures(signal, prefilter_vetoes, min_rr, current_price)

    if score < min_score:
        failures.append(f"score={score} < starter_min_score={min_score}")

    return failures


def _near_entry_gate_failures(
    signal: dict,
    score: int,
    config: dict,
    current_price: float | None = None,
) -> list[str]:
    min_score = config.get("tiers", {}).get("near_entry", {}).get("min_score", 60)
    failures: list[str] = []

    if score < min_score:
        failures.append(f"score={score} < near_entry_min_score={min_score}")

    missing = signal.get("missing_conditions")
    if not isinstance(missing, list) or not missing:
        failures.append("missing_conditions empty or not a list")

    trigger = signal.get("upgrade_trigger", "")
    if not trigger or str(trigger).lower() == "none":
        failures.append("upgrade_trigger empty or 'none'")

    # Impossible geometry blocks NEAR_ENTRY too — if both levels are present and
    # contradict each other, there is no valid watch setup to alert on.
    # Checks are skipped when levels are None (common for NEAR_ENTRY).
    failures.extend(_semantic_price_sanity_failures(signal, current_price))

    return failures


def _first_all_alert_blocker(prefilter_vetoes: list) -> str | None:
    """Return the first veto that blocks ALL alert tiers, or None."""
    for v in prefilter_vetoes:
        if v in _ALL_ALERT_BLOCKING_VETOES:
            return v
    return None


# ---------------------------------------------------------------------------
# Semantic price sanity
# ---------------------------------------------------------------------------

def _semantic_price_sanity_failures(
    signal: dict,
    current_price: float | None = None,
) -> list[str]:
    """Check bullish geometry invariants. Returns failure reasons.

    All checks assume bullish/long setups. Checks are skipped when required
    levels are absent so NEAR_ENTRY signals with incomplete data are not
    falsely blocked.
    """
    failures: list[str] = []

    trigger = signal.get("trigger_level")
    invalidation = signal.get("invalidation_level")
    targets = signal.get("targets", [])
    rr = signal.get("risk_reward")

    # Invalidation must be strictly below trigger (stop below entry for bullish)
    if trigger is not None and invalidation is not None:
        try:
            if float(invalidation) >= float(trigger):
                failures.append(
                    f"semantic_price_sanity_failed: invalidation_level={invalidation} "
                    f">= trigger_level={trigger} (impossible bullish geometry)"
                )
        except (TypeError, ValueError):
            pass

    # First actionable target must be above trigger
    if trigger is not None and isinstance(targets, list) and targets:
        first_target = targets[0]
        if isinstance(first_target, dict):
            t_level = first_target.get("level")
            if t_level is not None:
                try:
                    if float(t_level) <= float(trigger):
                        failures.append(
                            f"semantic_price_sanity_failed: first_target_level={t_level} "
                            f"<= trigger_level={trigger} (target not above entry)"
                        )
                except (TypeError, ValueError):
                    pass

    # risk_reward must be positive if present
    if rr is not None:
        try:
            if float(rr) <= 0:
                failures.append(
                    f"semantic_price_sanity_failed: risk_reward={rr} is not positive"
                )
        except (TypeError, ValueError):
            pass

    # Current price already below invalidation → position already stopped out
    if current_price is not None and invalidation is not None:
        try:
            if float(current_price) < float(invalidation):
                failures.append(
                    f"semantic_price_sanity_failed: current_price={current_price} "
                    f"< invalidation_level={invalidation} (price below stop level)"
                )
        except (TypeError, ValueError):
            pass

    return failures


# ---------------------------------------------------------------------------
# Downgrade cascade
# ---------------------------------------------------------------------------

def _determine_final_tier(
    claude_tier: str,
    signal: dict,
    prefilter_vetoes: list,
    score: int,
    config: dict,
    current_price: float | None = None,
) -> tuple[str, list[str], list[str]]:
    """Return (final_tier, downgrades, notes).

    Only downgrades are allowed — this function never upgrades claude_tier.
    """
    downgrades: list[str] = []
    notes: list[str] = []

    if claude_tier not in TIERS:
        notes.append(f"unknown tier {claude_tier!r} — forced to WAIT")
        return "WAIT", downgrades, notes

    # WAIT input: preserve — never upgrade
    if claude_tier == "WAIT":
        return "WAIT", downgrades, notes

    # All-alert-blocking veto forces WAIT regardless of tier or score
    blocker = _first_all_alert_blocker(prefilter_vetoes)
    if blocker:
        downgrades.append(f"{claude_tier}→WAIT: all-alert veto={blocker}")
        return "WAIT", downgrades, notes

    # Signal-level structure check: no structure in Claude output → WAIT.
    # Mirrors the no_clear_structure prefilter veto: NEAR_ENTRY requires
    # structural proximity and is not valid when structure itself is absent.
    if signal.get("structure_event", "none") == "none":
        downgrades.append(f"{claude_tier}→WAIT: structure_event=none (no clear structure)")
        return "WAIT", downgrades, notes

    # ---- SNIPE_IT path ----
    if claude_tier == "SNIPE_IT":
        snipe_failures = _snipe_gate_failures(signal, prefilter_vetoes, score, config, current_price)
        if not snipe_failures:
            return "SNIPE_IT", downgrades, notes

        starter_failures = _starter_gate_failures(signal, prefilter_vetoes, score, config, current_price)
        if not starter_failures:
            downgrades.append(f"SNIPE_IT→STARTER: {'; '.join(snipe_failures)}")
            return "STARTER", downgrades, notes

        near_failures = _near_entry_gate_failures(signal, score, config, current_price)
        if not near_failures:
            downgrades.append(f"SNIPE_IT→NEAR_ENTRY: {'; '.join(snipe_failures)}")
            return "NEAR_ENTRY", downgrades, notes

        downgrades.append(f"SNIPE_IT→WAIT: {'; '.join(snipe_failures)}")
        return "WAIT", downgrades, notes

    # ---- STARTER path ----
    if claude_tier == "STARTER":
        starter_failures = _starter_gate_failures(signal, prefilter_vetoes, score, config, current_price)
        if not starter_failures:
            return "STARTER", downgrades, notes

        near_failures = _near_entry_gate_failures(signal, score, config, current_price)
        if not near_failures:
            downgrades.append(f"STARTER→NEAR_ENTRY: {'; '.join(starter_failures)}")
            return "NEAR_ENTRY", downgrades, notes

        downgrades.append(f"STARTER→WAIT: {'; '.join(starter_failures)}")
        return "WAIT", downgrades, notes

    # ---- NEAR_ENTRY path ----
    if claude_tier == "NEAR_ENTRY":
        near_failures = _near_entry_gate_failures(signal, score, config, current_price)
        if not near_failures:
            return "NEAR_ENTRY", downgrades, notes

        downgrades.append(f"NEAR_ENTRY→WAIT: {'; '.join(near_failures)}")
        return "WAIT", downgrades, notes

    # Fallback (should not reach here given TIERS guard above)
    return "WAIT", downgrades, notes


# ---------------------------------------------------------------------------
# Signal-level veto derivation
# ---------------------------------------------------------------------------

def _signal_derived_vetoes(signal: dict) -> list[str]:
    """Derive veto labels from Claude signal fields for transparency in applied_vetoes."""
    derived: list[str] = []
    if signal.get("overhead_status") == "blocked":
        derived.append("overhead_blocked")
    if signal.get("sma_value_alignment") == "hostile":
        derived.append("hostile_value_alignment")
    if signal.get("retest_status") == "failed":
        derived.append("retest_failed")
    if signal.get("structure_event", "none") == "none":
        derived.append("no_clear_structure")
    if signal.get("invalidation_level") is None:
        derived.append("no_clear_invalidation_estimate")
    targets = signal.get("targets", [])
    if not isinstance(targets, list) or not targets:
        derived.append("no_target_path")
    return derived


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate(
    raw_signal: dict | None,
    prefilter_result: dict | None,
    config: dict,
) -> dict:
    """Apply all hard vetoes and tier gates. Return final validated result.

    Claude's tier is the starting classifier. This function is the sole final
    authority — Claude cannot override its output.

    Args:
        raw_signal:       Parsed Claude JSON dict (from parse_and_validate_json).
                          May be None if Claude call failed.
        prefilter_result: Prefilter result dict containing at least 'veto_flags'.
        config:           Loaded doctrine_config.yaml dict.

    Returns:
        Dict with keys: ok, final_tier, original_claude_tier, score,
        final_discord_channel, capital_action, applied_vetoes, downgrades,
        rejection_reason, validation_notes, safe_for_alert, final_signal.
    """
    # Handle None or invalid signal
    if raw_signal is None or not isinstance(raw_signal, dict):
        return {
            "ok": False,
            "final_tier": "WAIT",
            "original_claude_tier": None,
            "score": 0,
            "final_discord_channel": "none",
            "capital_action": "no_trade",
            "applied_vetoes": [],
            "downgrades": [],
            "rejection_reason": "raw_signal is None or not a dict",
            "validation_notes": ["signal rejected before tiering — malformed or missing"],
            "safe_for_alert": False,
            "final_signal": None,
        }

    claude_tier = raw_signal.get("tier", "WAIT")
    if claude_tier not in TIERS:
        claude_tier = "WAIT"

    score = raw_signal.get("score", 0)
    if not isinstance(score, (int, float)):
        score = 0
    score = int(score)

    prefilter_vetoes: list = (prefilter_result or {}).get("veto_flags", [])

    # Extract current_price from prefilter key_features if available.
    # Used by _semantic_price_sanity_failures to detect already-stopped-out positions.
    current_price: float | None = None
    cp_raw = (prefilter_result or {}).get("key_features", {}).get("current_price")
    if cp_raw is not None:
        try:
            current_price = float(cp_raw)
        except (TypeError, ValueError):
            pass

    final_tier, downgrades, notes = _determine_final_tier(
        claude_tier, raw_signal, prefilter_vetoes, score, config, current_price
    )

    # applied_vetoes: prefilter vetoes + signal-derived vetoes (deduplicated)
    applied_vetoes = list(prefilter_vetoes)
    for v in _signal_derived_vetoes(raw_signal):
        if v not in applied_vetoes:
            applied_vetoes.append(v)

    # Build corrected final_signal with deterministic routing applied
    final_signal = dict(raw_signal)
    final_signal["tier"] = final_tier
    final_signal["discord_channel"] = CHANNEL_MAP[final_tier]
    final_signal["capital_action"] = CAPITAL_MAP[final_tier]

    safe_for_alert = final_tier != "WAIT"

    rejection_reason: str | None = None
    if final_tier == "WAIT":
        if downgrades:
            rejection_reason = downgrades[-1]
        elif claude_tier == "WAIT":
            rejection_reason = "tier=WAIT: no actionable setup"
        else:
            rejection_reason = f"{claude_tier}→WAIT: gates failed"

    log.info(
        "Tiering: ticker=%s claude=%s → final=%s safe=%s vetoes=%s",
        raw_signal.get("ticker", "?"),
        claude_tier,
        final_tier,
        safe_for_alert,
        applied_vetoes or "none",
    )

    return {
        "ok": True,
        "final_tier": final_tier,
        "original_claude_tier": claude_tier,
        "score": score,
        "final_discord_channel": CHANNEL_MAP[final_tier],
        "capital_action": CAPITAL_MAP[final_tier],
        "applied_vetoes": applied_vetoes,
        "downgrades": downgrades,
        "rejection_reason": rejection_reason,
        "validation_notes": notes,
        "safe_for_alert": safe_for_alert,
        "final_signal": final_signal,
    }

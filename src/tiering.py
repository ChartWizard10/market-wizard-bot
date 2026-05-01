"""Deterministic tier validation. Final authority over all tier decisions.

Claude's output is the starting classifier only. This module applies hard vetoes,
downgrade logic, and routing corrections that Claude cannot override.
"""

import logging
import re
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
# Phase 12A: Alert integrity — tier-contradicting phrase replacement
# ---------------------------------------------------------------------------
# Phrases that must not appear in the displayed reason for a given final tier.
# Listed longest-first within each tier to prevent partial-match shadowing.
# Format: (banned_phrase_lowercase_match, replacement_text)
_TIER_BANNED_PHRASES: dict[str, list[tuple[str, str]]] = {
    # All lists are ordered longest-first so that compound phrases are matched
    # before their sub-phrases. This prevents partial-match shadowing where a
    # shorter pattern would consume part of a longer phrase first.
    "NEAR_ENTRY": [
        # 40 chars — Phase 12A
        ("reducing conviction to starter tier only", "Watch-only; confirmation pending."),
        # 38 chars — Phase 12.3: must precede "all snipe_it conditions satisfied" (33)
        ("enter on confirmed close above trigger", "watch for confirmed close above trigger"),
        # 33 chars — Phase 12.2: must precede "snipe_it conditions satisfied" (29)
        ("all snipe_it conditions satisfied", "Watchlist only until retest and hold confirm."),
        # 31 chars — Phase 12.2: must precede "snipe_it criteria" (17)
        ("satisfies all snipe_it criteria",   "Watchlist only until retest and hold confirm."),
        # 29 chars — Phase 12.2
        ("snipe_it conditions satisfied",      "Watchlist only until retest and hold confirm."),
        # 28 chars — Phase 12.1
        ("starter allocation warranted",       "Watchlist only until retest and hold confirm."),
        # 28 chars — Phase 12.2: must precede "snipe criteria" (14)
        ("satisfies all snipe criteria",       "Watchlist only until retest and hold confirm."),
        # 27 chars — Phase 12A: must precede "snipe_it conditions met" (23)
        ("all snipe_it conditions met",        "Watch-only; confirmation pending."),
        # 26 chars — Phase 12A
        ("all starter conditions met",         "Watch-only; confirmation pending."),
        # 23 chars — Phase 12.1
        ("starter entry warranted",            "Watchlist only until retest and hold confirm."),
        # 23 chars — Phase 12A
        ("snipe_it conditions met",            "Watch-only; confirmation pending."),
        # 22 chars — Phase 12.2
        ("full-quality candidate",             "watch-only candidate"),
        # 20 chars — Phase 12.1
        ("snipe conditions met",               "Watch-only; confirmation pending."),
        # 20 chars — Phase 12.1
        ("forced participation",               "Watchlist only until retest and hold confirm."),
        # 20 chars — Phase 12A: must precede "full quality" (12)
        ("full quality allowed",               "no capital authorized"),
        # 20 chars — Phase 12.1
        ("allocation warranted",               "Watchlist only until retest and hold confirm."),
        # 18 chars — Phase 12.1
        ("reduced-size entry",                 "Watchlist only until retest and hold confirm."),
        # 18 chars — Phase 12A
        ("capital authorized",                 "no capital authorized"),
        # 17 chars — Phase 12.1
        ("capital justified",                  "Watchlist only until retest and hold confirm."),
        # 17 chars — Phase 12.2
        ("snipe_it criteria",                  "Watchlist only until retest and hold confirm."),
        # 17 chars — Phase 12A
        ("starter tier only",                  "watch-only"),
        # 17 chars — Phase 12.1
        ("starter warranted",                  "Watchlist only until retest and hold confirm."),
        # 15 chars — Phase 12.1
        ("entry warranted",                    "Watchlist only until retest and hold confirm."),
        # 15 chars — Phase 12.3A: position-management language inappropriate for watchlist tier
        ("manage position",                    "No position management until capital is authorized."),
        # 14 chars — Phase 12.2
        ("snipe criteria",                     "Watchlist only until retest and hold confirm."),
        # 12 chars — Phase 12.1
        ("reduced size",                       "Watchlist only until retest and hold confirm."),
        # 12 chars — Phase 12A: must follow "full quality allowed" above
        ("full quality",                       "no capital authorized"),
        # 11 chars — Phase 12.2
        ("entry valid",                        "Watchlist only until retest and hold confirm."),
        # 10 chars — Phase 12.3A: must precede "stop below" — "trail stop below" contains
        # "stop below" as a sub-span; processing "trail stop" first prevents "stop below"
        # from consuming the overlapping portion and blocking the trail-stop replacement.
        # Updated Phase 12.3A: includes no-position-management reference.
        ("trail stop",                         "use invalidation reference only; no position management until capital is authorized."),
        # 10 chars — Phase 12.3: must follow "trail stop" above
        ("stop below",                         "invalidation reference below"),
    ],
    "STARTER": [
        # 35 chars — Phase 12.3: must precede "all snipe_it conditions satisfied" (33)
        # and "snipe confirmation not granted" (30)
        ("full snipe confirmation not granted", "full-size confirmation not granted"),
        # 33 chars — Phase 12.2: must precede "snipe_it conditions satisfied" (29)
        ("all snipe_it conditions satisfied",  "All STARTER conditions met."),
        # 31 chars — Phase 12.2: must precede "snipe_it criteria" (17)
        # Phase 12.3: replacement no longer says "SNIPE" to prevent self-referential
        # "SNIPE" wording in STARTER alerts.
        ("satisfies all snipe_it criteria",    "Starter-quality candidate; full-size confirmation not granted."),
        # 30 chars — Phase 12.3: must precede "snipe_it conditions satisfied" (29)
        ("snipe confirmation not granted",     "full-size confirmation not granted"),
        # 29 chars — Phase 12.2
        ("snipe_it conditions satisfied",      "All STARTER conditions met."),
        # 28 chars — Phase 12.2: must precede "snipe criteria" (14)
        ("satisfies all snipe criteria",       "Starter-quality candidate; full-size confirmation not granted."),
        # 27 chars — Phase 12A: must precede "snipe_it conditions met" (23)
        ("all snipe_it conditions met",        "Starter-quality candidate; full-size confirmation not granted."),
        # 23 chars — Phase 12A
        ("snipe_it conditions met",            "Starter-quality candidate; full-size confirmation not granted."),
        # 17 chars — Phase 12.2: must precede "snipe criteria" (14)
        ("snipe_it criteria",                  "starter criteria"),
        # 14 chars — Phase 12.2
        ("snipe criteria",                     "starter criteria"),
    ],
    "WAIT": [
        # Replacement-text hygiene for multi-pass safety:
        # Only ("capital authorized" → "No capital authorized.") is allowed to
        # produce "No capital authorized." because it is the SOLE phrase whose
        # output contains "capital authorized" as a substring, and the
        # non-overlapping scanner protects it within a single pass.
        # All other entries use "No valid setup." or "no actionable setup" so
        # that no earlier replacement inserts text matched by a later pass.
        #
        # 33 chars — Phase 12.2: must precede "snipe_it conditions satisfied" (29)
        ("all snipe_it conditions satisfied",  "No valid setup."),
        # 31 chars — Phase 12.2: must precede "snipe_it criteria" (17)
        ("satisfies all snipe_it criteria",    "No valid setup."),
        # 29 chars — Phase 12.2
        ("snipe_it conditions satisfied",      "No valid setup."),
        # 28 chars — Phase 12.2: must precede "snipe criteria" (14)
        ("satisfies all snipe criteria",       "No valid setup."),
        # 27 chars — Phase 12.2: must precede "snipe_it conditions met" (23)
        ("all snipe_it conditions met",        "No valid setup."),
        # 23 chars — Phase 12.2
        ("snipe_it conditions met",            "No valid setup."),
        # 20 chars — Phase 12A: must precede "full quality" (12); safe replacement
        ("full quality allowed",               "no valid setup"),
        # 18 chars — Phase 12A: ONLY entry allowed to produce "No capital authorized."
        ("capital authorized",                 "No capital authorized."),
        # 17 chars — Phase 12.2: must precede "snipe criteria" (14)
        ("snipe_it criteria",                  "no actionable setup"),
        # 14 chars — Phase 12.2
        ("snipe criteria",                     "no actionable setup"),
        # 12 chars — Phase 12A: must follow "full quality allowed" above
        ("full quality",                       "no actionable setup"),
        # 11 chars — Phase 12.2
        ("entry valid",                        "No valid setup."),
        # 11 chars — Phase 12A
        ("execute now",                        "No valid setup."),
        # 9 chars — Phase 12A
        ("enter now",                          "No valid setup."),
    ],
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
    key_features: dict | None = None,
) -> list[str]:
    tier_cfg = config.get("tiers", {}).get("snipe_it", {})
    min_score = tier_cfg.get("min_score", 85)
    min_rr = tier_cfg.get("min_rr", 3.0)

    failures = _entry_gate_failures(signal, prefilter_vetoes, min_rr, current_price)

    if score < min_score:
        failures.append(f"score={score} < snipe_min_score={min_score}")

    # Unproven acceptance blocks SNIPE_IT — cascade will try STARTER next.
    # STARTER does not run this check, so unproven alone cannot suppress STARTER.
    acceptance = _classify_current_acceptance(signal, key_features or {})
    if acceptance == "unproven":
        failures.append("current_acceptance=unproven (zone defense unconfirmed for SNIPE_IT)")

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
# Current acceptance classification
# ---------------------------------------------------------------------------

def _classify_current_acceptance(signal: dict, key_features: dict) -> str:
    """Classify live price action relative to the signal's zone.

    Returns: accepted | unproven | damaging | invalidated | unknown

    'unknown' means no current price data — callers must NOT downgrade on unknown.
    'unproven' means data exists but zone defense is inconclusive — blocks SNIPE_IT only.
    """
    current_price = key_features.get("current_price")
    if current_price is None:
        return "unknown"

    try:
        cp = float(current_price)
    except (TypeError, ValueError):
        return "unknown"

    trigger = signal.get("trigger_level")
    invalidation = signal.get("invalidation_level")
    bar_dir = key_features.get("current_bar_direction", "unknown")
    close_loc = key_features.get("current_close_location_pct")

    # Invalidated: price at or below the stop level
    if invalidation is not None:
        try:
            if cp <= float(invalidation):
                return "invalidated"
        except (TypeError, ValueError):
            pass

    # Without a trigger level we cannot assess entry acceptance
    if trigger is None:
        # Strong rejection candle is still damaging even without a trigger reference
        if bar_dir == "red" and close_loc is not None:
            try:
                if float(close_loc) < 0.25:
                    return "damaging"
            except (TypeError, ValueError):
                pass
        return "unproven"

    try:
        trig = float(trigger)
    except (TypeError, ValueError):
        return "unproven"

    # Price has not reached the entry trigger
    if cp < trig:
        return "damaging"

    # Price at/above trigger — check for strong rejection candle
    if bar_dir == "red" and close_loc is not None:
        try:
            if float(close_loc) < 0.25:
                return "damaging"
        except (TypeError, ValueError):
            pass

    # Price at/above trigger with no rejection signal
    return "accepted"


# ---------------------------------------------------------------------------
# Phase 12A/12.2: Sanitize reason text for final tier
# ---------------------------------------------------------------------------

# Phase 12.2: Post-replacement cleanup for NEAR_ENTRY.
# Replacing "entry valid" with "Watchlist only until retest and hold confirm."
# inside a phrase like "entry valid only until X" leaves a dangling
# "only until X" tail.  This regex removes it.
_WATCHLIST_TAIL_RE = re.compile(
    r"(retest and hold confirm\.)\s+only until\b[^.]*\.?",
    re.IGNORECASE,
)


def _near_entry_blocker_backfill(signal: dict, current_price: float | None) -> None:
    """Phase 12.3: pre-gate backfill for NEAR_ENTRY signals.

    Populates upgrade_trigger and missing_conditions from blocker priority so
    the NEAR_ENTRY gate can pass when Claude left these fields blank or 'none'.
    Modifies signal in place. Called only when claude_tier == 'NEAR_ENTRY'.

    Priority A (price below trigger) overrides missing_conditions with
    trigger-specific context. Priorities B–F only backfill upgrade_trigger
    when it is blank/none — missing_conditions is left as-is.
    """
    trigger = signal.get("trigger_level")
    retest = signal.get("retest_status", "missing")
    hold = signal.get("hold_status", "missing")
    rr = signal.get("risk_reward")
    overhead = signal.get("overhead_status", "unknown")

    existing_trigger = str(signal.get("upgrade_trigger") or "")
    trigger_is_blank = not existing_trigger or existing_trigger.lower() == "none"

    # Priority A: price has not accepted above trigger — most specific blocker
    if current_price is not None and trigger is not None:
        try:
            if float(current_price) < float(trigger):
                signal["missing_conditions"] = [
                    "trigger_acceptance — price is below trigger and has not confirmed"
                    " acceptance above trigger"
                ]
                if trigger_is_blank:
                    signal["upgrade_trigger"] = (
                        "Price reclaims and holds above trigger with body-close confirmation."
                    )
                return
        except (TypeError, ValueError):
            pass

    # Priorities B–F: only backfill upgrade_trigger when blank AND at least one of
    # retest/hold shows partial progress (mirrors Phase 12B has_partial_progress guard).
    # When both are 'missing', no progress exists and the gate should reject — do not
    # rescue a signal that has neither retest nor hold progress.
    if not trigger_is_blank:
        return

    has_partial_progress = (
        retest in ("partial", "confirmed") or hold in ("partial", "confirmed")
    )
    if not has_partial_progress:
        return

    if retest != "confirmed":
        signal["upgrade_trigger"] = "Full zone retest confirmed with body-close hold."
    elif hold != "confirmed":
        signal["upgrade_trigger"] = "Body-close acceptance inside or above the zone."
    elif rr is None or (isinstance(rr, (int, float)) and float(rr) < 3.0):
        signal["upgrade_trigger"] = "Wait for improved entry geometry (R:R ≥ 3.0)."
    elif overhead in ("moderate", "blocked", "unknown"):
        signal["upgrade_trigger"] = "Reclaim through overhead resistance with acceptance."
    else:
        signal["upgrade_trigger"] = "Trigger acceptance with retest and hold confirmation."


def _build_near_entry_blocker_note(signal: dict, current_price: float | None) -> str:
    """Phase 12.3: build a human-readable blocker explanation for NEAR_ENTRY alerts.

    Returns a 'Blocker: ...' string. Called only when final_tier == 'NEAR_ENTRY'.
    Applies the same priority as _near_entry_blocker_backfill so the rendered
    blocker always matches the pre-gate backfill decision.
    """
    trigger = signal.get("trigger_level")
    retest = signal.get("retest_status", "missing")
    hold = signal.get("hold_status", "missing")
    rr = signal.get("risk_reward")
    overhead = signal.get("overhead_status", "unknown")

    # A: price below trigger
    if current_price is not None and trigger is not None:
        try:
            if float(current_price) < float(trigger):
                return (
                    "Blocker: price is below trigger; wait for reclaim and hold above trigger."
                )
        except (TypeError, ValueError):
            pass

    # B: retest not confirmed
    if retest != "confirmed":
        return (
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        )

    # C: hold not confirmed
    if hold != "confirmed":
        return (
            "Blocker: hold is not fully confirmed; wait for body-close acceptance"
            " inside/above the zone."
        )

    # D: R:R not sufficient
    if rr is None or (isinstance(rr, (int, float)) and float(rr) < 3.0):
        return (
            "Blocker: R:R is not sufficient for capital; wait for improved entry geometry."
        )

    # E: overhead not clean
    if overhead in ("moderate", "blocked", "unknown"):
        return (
            "Blocker: overhead path is not clean enough for capital;"
            " wait for reclaim through resistance."
        )

    # F: fallback
    return (
        "Blocker: watchlist only until trigger acceptance, retest, and hold confirm."
    )


def _replace_phrase_non_overlapping(text: str, banned_lower: str, replacement: str) -> str:
    """Replace every non-overlapping case-insensitive occurrence of `banned_lower`
    in `text` with `replacement`. The cursor advances over the matched span in the
    source text only — never into the inserted replacement — so a replacement that
    contains the banned substring cannot trigger another match.
    """
    if not banned_lower:
        return text
    lower_text = text.lower()
    n = len(lower_text)
    parts: list[str] = []
    cursor = 0
    while cursor < n:
        idx = lower_text.find(banned_lower, cursor)
        if idx == -1:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:idx])
        parts.append(replacement)
        cursor = idx + len(banned_lower)
    else:
        # cursor reached n exactly — nothing trailing
        pass
    return "".join(parts)


def _sanitize_reason_for_tier(reason: str | None, final_tier: str) -> str:
    """Remove phrases from Claude's reason that contradict final_tier.

    Uses case-insensitive substring replacement from _TIER_BANNED_PHRASES.
    Does not attempt NLP — only replaces explicit tier-contradiction strings.
    Preserves all chart structure and analysis reasoning.
    Returns the original reason unchanged for SNIPE_IT (no restrictions).

    Replacement is performed as a single non-overlapping pass per phrase, so a
    replacement that itself contains the banned substring will not loop.
    """
    if not reason:
        return ""
    banned_list = _TIER_BANNED_PHRASES.get(final_tier, [])
    if not banned_list:
        return str(reason)
    result = str(reason)
    for banned_lower, replacement in banned_list:
        result = _replace_phrase_non_overlapping(result, banned_lower, replacement)
    # Phase 12.2: NEAR_ENTRY cleanup — strip dangling "only until..." tail that
    # appears when a banned phrase (e.g. "entry valid") was embedded in a
    # construction like "entry valid only until X", leaving
    # "Watchlist only until retest and hold confirm. only until X".
    if final_tier == "NEAR_ENTRY":
        result = _WATCHLIST_TAIL_RE.sub(r"\1", result)
    return result


# ---------------------------------------------------------------------------
# Phase 12B: Conservative NEAR_ENTRY missing_conditions backfill
# ---------------------------------------------------------------------------
# Doctrine: NEAR_ENTRY alerts must be explicit about what is missing, but the
# bot must not invent progress. If both retest and hold are "missing", there is
# no observable progress and the empty-list veto is allowed to downgrade the
# signal to WAIT (existing behavior preserved). Backfill runs only when at
# least one of retest_status / hold_status is "partial" or "confirmed".
#
# This backfill never overrides hard vetoes — semantic_price_sanity_failures,
# current_acceptance_invalidated/damaging, prefilter blockers, and structure
# absence still fire downstream in _determine_final_tier and can downgrade
# NEAR_ENTRY → WAIT regardless of the missing_conditions list contents.
#
# This backfill is NEVER applied to SNIPE_IT or STARTER claude_tier. Those
# tier gates remain exactly as before.

def _backfill_missing_conditions(signal: dict) -> list[str]:
    """Return a deterministic missing_conditions list, or [] if no progress.

    Returns [] when both retest_status and hold_status are 'missing' so the
    caller's empty-list veto can downgrade the signal to WAIT.
    """
    retest = signal.get("retest_status", "missing")
    hold = signal.get("hold_status", "missing")

    has_partial_progress = (
        retest in ("partial", "confirmed") or hold in ("partial", "confirmed")
    )
    if not has_partial_progress:
        return []

    out: list[str] = []
    if retest == "missing":
        out.append("missing_retest")
    if hold == "missing":
        out.append("missing_hold")
    if not out:
        out.append("current_acceptance_needed")
    return out


# ---------------------------------------------------------------------------
# Phase 12C: Risk Realism informational fields
# ---------------------------------------------------------------------------
# Operator-clarity layer. NOT a hard-filter layer.
#
# Phase 10 _semantic_price_sanity_failures remains canonical for impossible
# geometry (invalidation >= trigger, first target <= trigger, risk_reward <= 0,
# current_price below invalidation). Phase 12C must NOT own those rejections,
# and must NOT add a competing rejection reason. Phase 12C only labels what the
# risk window looks like for operator awareness.
#
# State precedence (most conservative wins):
#   invalid > fragile > tight > healthy > unknown
#
# Phase 12C does not modify final_tier, capital_action, discord_channel,
# downgrades, or rejection_reason. It populates informational fields only.

def _classify_risk_realism(
    trigger: float | None,
    invalidation: float | None,
    current_price: float | None,
) -> tuple[str, str, dict]:
    """Classify whether the risk window is realistic. Informational only.

    Returns (state, note, computed_fields_dict). The dict has four keys:
        risk_distance, risk_distance_pct,
        current_price_to_invalidation, current_price_to_invalidation_pct.
    Any of those may be None when the inputs are missing or non-numeric.
    """
    fields: dict = {
        "risk_distance": None,
        "risk_distance_pct": None,
        "current_price_to_invalidation": None,
        "current_price_to_invalidation_pct": None,
    }

    risk_distance: float | None = None
    risk_distance_pct: float | None = None
    if trigger is not None and invalidation is not None:
        try:
            t = float(trigger)
            i = float(invalidation)
            risk_distance = t - i
            fields["risk_distance"] = round(risk_distance, 4)
            if t != 0:
                risk_distance_pct = risk_distance / abs(t) * 100
                fields["risk_distance_pct"] = round(risk_distance_pct, 3)
        except (TypeError, ValueError):
            pass

    cp_to_inval: float | None = None
    cp_to_inval_pct: float | None = None
    if current_price is not None and invalidation is not None:
        try:
            cp = float(current_price)
            i = float(invalidation)
            cp_to_inval = cp - i
            fields["current_price_to_invalidation"] = round(cp_to_inval, 4)
            if cp != 0:
                cp_to_inval_pct = cp_to_inval / abs(cp) * 100
                fields["current_price_to_invalidation_pct"] = round(cp_to_inval_pct, 3)
        except (TypeError, ValueError):
            pass

    # Cannot classify without risk_distance_pct
    if risk_distance_pct is None:
        return (
            "unknown",
            "Risk realism unknown; missing trigger, invalidation, or current price.",
            fields,
        )

    # Impossible geometry — Phase 10 owns rejection. Mark informationally only.
    if risk_distance is not None and risk_distance <= 0:
        return (
            "invalid",
            "Risk geometry invalid; semantic gate owns rejection.",
            fields,
        )

    # Classify by risk_distance_pct (most conservative wins)
    if risk_distance_pct < 0.35:
        state = "fragile"
    elif risk_distance_pct < 0.75:
        state = "tight"
    else:
        state = "healthy"

    # current_price_to_invalidation_pct < 1.0 → escalate at least to tight.
    # If price has already traded below invalidation, Phase 10 owns rejection,
    # but for operator clarity we still mark this as fragile.
    if cp_to_inval_pct is not None:
        if cp_to_inval_pct < 0:
            state = "fragile"
        elif cp_to_inval_pct < 1.0:
            if state == "healthy":
                state = "tight"

    if state == "fragile":
        note = "Risk window is fragile; invalidation is very close."
    elif state == "tight":
        note = "Risk window is tight; verify live chart before entry."
    else:
        note = "Risk window is healthy."

    return (state, note, fields)


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
    key_features: dict | None = None,
) -> tuple[str, list[str], list[str]]:
    """Return (final_tier, downgrades, notes).

    Only downgrades are allowed — this function never upgrades claude_tier.
    """
    downgrades: list[str] = []
    notes: list[str] = []
    kf = key_features or {}

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

    # Acceptance pre-check: live price action vs the claimed zone
    acceptance = _classify_current_acceptance(signal, kf)

    if acceptance == "invalidated":
        # Price is at or below the stop level — position already stopped out
        downgrades.append(
            f"{claude_tier}→WAIT: current_acceptance=invalidated (price at/below stop)"
        )
        return "WAIT", downgrades, notes

    if acceptance == "damaging" and claude_tier in ("SNIPE_IT", "STARTER"):
        # Price below trigger or strong rejection candle — cap to NEAR_ENTRY
        # Only valid if geometry is self-consistent (otherwise WAIT is safer)
        geo_failures = _semantic_price_sanity_failures(signal, current_price)
        if geo_failures:
            downgrades.append(
                f"{claude_tier}→WAIT: current_acceptance=damaging with impossible geometry"
            )
            return "WAIT", downgrades, notes
        downgrades.append(f"{claude_tier}→NEAR_ENTRY: current_acceptance=damaging")
        return "NEAR_ENTRY", downgrades, notes

    # ---- SNIPE_IT path ----
    if claude_tier == "SNIPE_IT":
        snipe_failures = _snipe_gate_failures(signal, prefilter_vetoes, score, config, current_price, kf)
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

    # Extract key_features for acceptance and semantic sanity checks.
    key_features: dict = (prefilter_result or {}).get("key_features", {})
    current_price: float | None = None
    cp_raw = key_features.get("current_price")
    if cp_raw is not None:
        try:
            current_price = float(cp_raw)
        except (TypeError, ValueError):
            pass

    # Phase 12B: conservative backfill of missing_conditions for NEAR_ENTRY when
    # at least one sign of partial progress exists. Does not run for SNIPE_IT
    # or STARTER. Hard vetoes downstream still fire — backfill never grants entry.
    working_signal = dict(raw_signal)
    if claude_tier == "NEAR_ENTRY":
        existing_mc = working_signal.get("missing_conditions")
        if not isinstance(existing_mc, list) or not existing_mc:
            backfilled = _backfill_missing_conditions(working_signal)
            if backfilled:
                working_signal["missing_conditions"] = backfilled

    # Phase 12.3: pre-gate backfill for NEAR_ENTRY.
    # Populates upgrade_trigger (and for price-below-trigger, missing_conditions)
    # so the NEAR_ENTRY gate passes when Claude left those fields blank or 'none'.
    # Does not change tier-gate logic — only ensures required fields are present.
    if claude_tier == "NEAR_ENTRY":
        _near_entry_blocker_backfill(working_signal, current_price)

    final_tier, downgrades, notes = _determine_final_tier(
        claude_tier, working_signal, prefilter_vetoes, score, config, current_price, key_features
    )

    # applied_vetoes: prefilter vetoes + signal-derived vetoes (deduplicated)
    applied_vetoes = list(prefilter_vetoes)
    for v in _signal_derived_vetoes(working_signal):
        if v not in applied_vetoes:
            applied_vetoes.append(v)

    # Build corrected final_signal with deterministic routing applied.
    # Use working_signal so 12B-backfilled missing_conditions are visible.
    final_signal = dict(working_signal)
    final_signal["tier"] = final_tier
    final_signal["discord_channel"] = CHANNEL_MAP[final_tier]
    final_signal["capital_action"] = CAPITAL_MAP[final_tier]

    # Phase 12A: sanitize Claude prose so alerts cannot display tier-contradicting language
    final_signal["sanitized_reason"] = _sanitize_reason_for_tier(
        final_signal.get("reason"), final_tier
    )

    # Phase 12.3A: sanitize next_action to strip position-management language for NEAR_ENTRY
    final_signal["sanitized_next_action"] = _sanitize_reason_for_tier(
        final_signal.get("next_action"), final_tier
    )

    # Phase 12.3: NEAR_ENTRY blocker explanation — always explains why capital is not authorized.
    # Only added when final_tier is NEAR_ENTRY; absent for SNIPE_IT, STARTER, and WAIT.
    if final_tier == "NEAR_ENTRY":
        final_signal["near_entry_blocker_note"] = _build_near_entry_blocker_note(
            final_signal, current_price
        )

    # Phase 11: Freshness/drift fields — snapshot_only architecture.
    # scan_price is the last close at scan time (from prefilter key_features).
    # No live re-fetch occurs between scan and alert send.
    # TODO: !recheck TICKER command can refresh these fields post-alert.
    final_signal["scan_price"] = current_price
    if current_price is not None:
        try:
            trig = final_signal.get("trigger_level")
            if trig is not None:
                final_signal["price_distance_to_trigger_pct"] = round(
                    (float(current_price) - float(trig)) / abs(float(trig)) * 100, 3
                )
            else:
                final_signal["price_distance_to_trigger_pct"] = None
        except (TypeError, ValueError, ZeroDivisionError):
            final_signal["price_distance_to_trigger_pct"] = None
        try:
            inval = final_signal.get("invalidation_level")
            if inval is not None:
                final_signal["price_distance_to_invalidation_pct"] = round(
                    (float(current_price) - float(inval)) / abs(float(inval)) * 100, 3
                )
            else:
                final_signal["price_distance_to_invalidation_pct"] = None
        except (TypeError, ValueError, ZeroDivisionError):
            final_signal["price_distance_to_invalidation_pct"] = None
    else:
        final_signal["price_distance_to_trigger_pct"] = None
        final_signal["price_distance_to_invalidation_pct"] = None
    final_signal["drift_status"] = "snapshot_only"
    final_signal["drift_pct"] = 0.0
    final_signal["freshness_note"] = (
        "Signal based on scan-time price; verify live chart before entry."
    )

    # Phase 12C: Risk Realism informational fields. Operator-clarity only.
    # Does NOT change final_tier, capital_action, discord_channel, or downgrades.
    # Phase 10 _semantic_price_sanity_failures retains canonical authority over
    # impossible-geometry rejection.
    _rr_trigger = final_signal.get("trigger_level")
    _rr_invalidation = final_signal.get("invalidation_level")
    _rr_state, _rr_note, _rr_fields = _classify_risk_realism(
        _rr_trigger, _rr_invalidation, current_price
    )
    final_signal["risk_distance"] = _rr_fields["risk_distance"]
    final_signal["risk_distance_pct"] = _rr_fields["risk_distance_pct"]
    final_signal["current_price_to_invalidation"] = _rr_fields["current_price_to_invalidation"]
    final_signal["current_price_to_invalidation_pct"] = _rr_fields["current_price_to_invalidation_pct"]
    final_signal["risk_realism_state"] = _rr_state
    final_signal["risk_realism_note"] = _rr_note

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

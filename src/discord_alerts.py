"""Discord alert formatting and routing for validated final signals.

Reads only from tiering_result['final_signal'] and tiering_result top-level fields.
Routes by final_tier exclusively — never trusts Claude's discord_channel field.
WAIT never posts. Null channel IDs are safe (log + skip, no raise).
Does not call Claude, yfinance, tiering, or state_store.
"""

import logging
import math
import os
import re

from src import higher_timeframe_context as _htf_context
from src import snipe_gate_audit as _snipe_audit
from src import timeframe_alignment as _tf_alignment

log = logging.getLogger(__name__)

_DISCORD_MAX_CHARS = 2000

# Sentinel marking where the structured 1H evidence block is spliced in after the
# narrative guards run. Deliberately keyword-free so no guard rewrites it.
_ONE_HOUR_SENTINEL = "⁣ONE_HOUR_EVIDENCE_BLOCK⁣"

# Sentinel for the Phase 14F multi-timeframe alignment block — same splice-after-
# guards protection so its structured enum values are never rewritten.
_TF_ALIGNMENT_SENTINEL = "⁣TIMEFRAME_ALIGNMENT_BLOCK⁣"

# Sentinel for the optional Phase 14H SNIPE-audit compact line (config-gated,
# default off). Same splice-after-guards protection for its label enum.
_SNIPE_AUDIT_SENTINEL = "⁣SNIPE_GATE_AUDIT_LINE⁣"

# Sentinel for the optional Phase 14I HTF-context compact line (config-gated,
# default off).
_HTF_CONTEXT_SENTINEL = "⁣HIGHER_TIMEFRAME_CONTEXT_LINE⁣"

_TIER_ENV_VAR = {
    "SNIPE_IT":   "DISCORD_SNIPE_CHANNEL_ID",
    "STARTER":    "DISCORD_STARTER_CHANNEL_ID",
    "NEAR_ENTRY": "DISCORD_NEAR_ENTRY_CHANNEL_ID",
}

_TIER_CONFIG_KEY = {
    "SNIPE_IT":   "snipe_channel_id",
    "STARTER":    "starter_channel_id",
    "NEAR_ENTRY": "near_entry_channel_id",
}

_TIER_BADGE = {
    "SNIPE_IT":   "🔴 SNIPE IT",
    "STARTER":    "🟡 STARTER",
    "NEAR_ENTRY": "🟢 NEAR ENTRY",
    "WAIT":       "⚪ WAIT",
}

_CAPITAL_LABEL = {
    "full_quality_allowed": "FULL QUALITY",
    "starter_only":         "STARTER SIZE ONLY",
    "wait_no_capital":      "NO CAPITAL — WATCH ONLY",
    "no_trade":             "NO TRADE",
}

# ---------------------------------------------------------------------------
# Phase 13.7B: Alert Decision Contract — single source of truth for
# ACTION section text, capital policy, and tier-forbidden phrases.
#
# The contract:
#   headline    — required first line of the ACTION section
#   sizing      — required capital/sizing line of the ACTION section
#   capital_state — string identifier (informational)
#   forbidden   — list of (lowercase_match, safe_replacement) tuples,
#                 ordered longest-match-first to prevent partial-shadow.
#
# Replacement-text hygiene rule (applies to ALL tiers):
#   No replacement string in NEAR_ENTRY's forbidden list may contain
#   "capital authorized" as a substring. The "capital authorized" entry
#   replaces with "no capital" (without "authorized"), so no earlier
#   replacement can produce a string the "capital authorized" rule would
#   then re-match in a subsequent iteration.
# ---------------------------------------------------------------------------
CAPITAL_CONTRACT: dict[str, dict] = {
    "SNIPE_IT": {
        "headline": "SNIPE_IT conditions met.",
        "sizing": "FULL QUALITY — capital authorized after live-chart verification.",
        "capital_state": "capital_authorized",
        # Forbidden in SNIPE_IT alert text — longest first within each group.
        "forbidden": [
            ("no position management until capital is authorized",
             "Continue monitoring live hold and expansion."),
            ("no capital until blocker resolves",
             "Continue monitoring live hold and expansion."),
            ("no capital — watch only",
             "Continue monitoring live hold and expansion."),
            ("starter size only",
             "Continue monitoring live hold and expansion."),
            ("near-entry watch",
             "Continue monitoring live hold and expansion."),
            ("blocker resolves",
             "Continue monitoring live hold and expansion."),
            ("no capital yet",
             "Continue monitoring live hold and expansion."),
            ("watch-only",
             "Continue monitoring live hold and expansion."),
            ("no capital",
             "Continue monitoring live hold and expansion."),
            ("watch only",
             "Continue monitoring live hold and expansion."),
        ],
    },
    "STARTER": {
        "headline": "STARTER conditions met.",
        "sizing": "STARTER SIZE ONLY — reduced-size capital only.",
        "capital_state": "starter_only",
        # Forbidden in STARTER alert text — longest first.
        "forbidden": [
            # 50
            ("no position management until capital is authorized",
             "Maintain starter-only sizing until upgrade conditions are met."),
            # 37 — KOS bug (Phase 13.7C): "are satisfied" variant missing from 13.7B.
            ("all snipe_it conditions are satisfied",
             "STARTER conditions met; full-size authorization not granted."),
            # 33
            ("all snipe_it conditions satisfied",   "STARTER conditions met."),
            # 33 — "are satisfied" variant for the non-"all" form
            ("snipe_it conditions are satisfied",
             "STARTER conditions met; full-size authorization not granted."),
            # 31
            ("all snipe_it conditions are met",     "STARTER conditions met."),
            # 31
            ("all snipe_it conditions cleared",
             "STARTER conditions met; full-size authorization not granted."),
            # 30
            ("all snipe_it conditions passed",
             "STARTER conditions met; full-size authorization not granted."),
            # 29
            ("snipe_it conditions satisfied",       "STARTER conditions met."),
            # 28
            ("all snipe_it conditions met.",        "STARTER conditions met."),
            # 27
            ("all snipe_it conditions met",         "STARTER conditions met."),
            # 27 — "all six snipe_it …" phrase seen in live output
            ("all six snipe_it conditions",
             "STARTER conditions met; full-size authorization not granted."),
            # 27
            ("snipe_it conditions are met",         "STARTER conditions met."),
            # 23
            ("no capital — watch only",             "STARTER SIZE ONLY"),
            # 23
            ("snipe_it conditions met",             "STARTER conditions met."),
            # 16
            ("near-entry watch",
             "Maintain starter-only sizing until upgrade conditions are met."),
            # 17
            ("full-size allowed",                   "STARTER SIZE ONLY"),
            # 17
            ("full size allowed",                   "STARTER SIZE ONLY"),
            # 18
            ("capital authorized",                  "reduced-size capital allocated"),
            # 12
            ("full quality",                        "STARTER SIZE ONLY"),
            # "full-size" / "full size" intentionally excluded — "full-size confirmation
            # not granted" is legitimate STARTER denial language; the bare substring
            # would produce false positives. "full quality" catches the real risk.
            # 10
            ("enter long",                          "Monitor entry conditions."),
            # 10
            ("no capital",                          "STARTER SIZE ONLY"),
            # 10
            ("watch only",                          "STARTER SIZE ONLY"),
        ],
    },
    "NEAR_ENTRY": {
        "headline": "Near-entry watch — no capital until blocker resolves.",
        "sizing": "NO CAPITAL — WATCH ONLY",
        "capital_state": "no_capital",
        # Forbidden in NEAR_ENTRY alert text — longest first.
        # All Phase 13.6A/13.6B entries preserved; Phase 13.7B adds new entries.
        "forbidden": [
            # 50: specific compound phrase — must precede "position management"
            ("no position management until capital is authorized",
             "Watch-only; wait for blocker resolution."),
            # 44
            ("watchlist only until retest and hold confirm", "Watch-only; no capital."),
            # 39
            ("degrading this from snipe_it to starter",     "Watch-only; no capital."),
            # 35
            ("downgraded from snipe_it to starter",         "Watch-only; no capital."),
            # 33
            ("all snipe_it conditions satisfied", "Watch-only; no capital."),
            # 31
            ("all snipe_it conditions are met",   "Watch-only; no capital."),
            # 29
            ("snipe_it conditions satisfied",     "Watch-only; no capital."),
            ("snipe_it downgrade to starter",     "Watch-only; no capital."),
            # 28
            ("all snipe_it conditions met.",      "Watch-only; no capital."),
            # 27
            ("all snipe_it conditions met",       "Watch-only; no capital."),
            ("all starter conditions met.",       "Watch-only; no capital."),
            ("snipe_it conditions are met",       "Watch-only; no capital."),
            # 26
            ("all starter conditions met",        "Watch-only; no capital."),
            # 24
            ("from snipe_it to starter",          "Watch-only; no capital."),
            # 23
            ("snipe_it conditions met",           "Watch-only; no capital."),
            # 22
            ("starter conditions met",            "Watch-only; no capital."),
            # 21
            ("downgraded to starter",             "Watch-only; no capital."),
            ("making this a starter",             "Watch-only; no capital."),
            # 20
            ("watchlist only until",              "Watch-only; no capital."),
            ("downgrade to starter",              "Watch-only; no capital."),
            # 19
            ("position management",               "Watch-only; wait for blocker resolution."),
            ("snipe_it to starter",               "Watch-only; no capital."),
            # 21 — must precede shorter "capital authorized" (18 chars)
            ("capital is authorized",             "no capital"),
            # 18
            ("capital authorized",                "no capital"),
            # 17
            ("starter size only",                 "NO CAPITAL — WATCH ONLY"),
            # 15
            ("add to position",                   "Watch-only; wait for blocker resolution."),
            # 14
            ("starter sizing",                    "no capital"),
            # 12
            ("full quality",                      "no capital"),
            # 10
            ("enter long",                        "Watch-only; wait for blocker resolution."),
            ("trail stop",                        "invalidation reference only"),
            # 5 — short; catches "scale in", "scale out", "scale up", "scale your entry"
            ("scale",                             "Watch-only; wait for blocker resolution."),
        ],
    },
}

# Derived action labels — keep for internal use; ACTION section now built from
# CAPITAL_CONTRACT directly so these are reference-only.
_TIER_ACTION_LABEL = {t: c["headline"] for t, c in CAPITAL_CONTRACT.items()}
_TIER_ACTION_LABEL["WAIT"] = "WAIT — no actionable setup."

_MENTION_RE = re.compile(r"@(everyone|here)", re.IGNORECASE)
_ROLE_USER_MENTION_RE = re.compile(r"<@[!&]?\d+>")


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------

def resolve_channel_id(tier: str, config: dict) -> int | None:
    """Resolve channel ID: env var first, then config. Returns None if unconfigured."""
    env_var = _TIER_ENV_VAR.get(tier)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            try:
                return int(val)
            except ValueError:
                log.warning("Invalid int in env var %s=%r", env_var, val)

    config_key = _TIER_CONFIG_KEY.get(tier)
    if config_key:
        val = (config.get("discord") or {}).get(config_key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                log.warning("Invalid channel ID in config discord.%s=%r", config_key, val)

    return None


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

def _sanitize(text: str | None) -> str:
    """Neutralize @everyone/@here and role/user mentions."""
    if not text:
        return ""
    # Insert zero-width space after @ to break mention
    text = _MENTION_RE.sub(lambda m: "@​" + m.group(1), text)
    text = _ROLE_USER_MENTION_RE.sub("[mention]", text)
    return text


# ---------------------------------------------------------------------------
# Phase 13.7B: Contract guard — replaces Phase 13.6A _consistency_guard()
# ---------------------------------------------------------------------------

def _apply_contract_guard(text: str, final_tier: str) -> str:
    """Final-pass safety net using CAPITAL_CONTRACT forbidden-phrase lists.

    Replaces tier-contradicting phrases that survived upstream sanitization.
    Logs a warning for every hit — each hit indicates a gap in tiering.py's
    _sanitize_reason_for_tier that should be patched upstream.

    Runs sequentially on the fully assembled alert text; longest-first ordering
    in CAPITAL_CONTRACT.forbidden prevents partial-match shadowing.
    """
    contract = CAPITAL_CONTRACT.get(final_tier)
    if not contract:
        return text
    result = text
    for match_lower, replacement in contract["forbidden"]:
        if match_lower in result.lower():
            log.warning(
                "CONTRACT_GUARD: tier=%s — found forbidden phrase %r; replacing.",
                final_tier, match_lower,
            )
            result = re.sub(re.escape(match_lower), replacement, result, flags=re.IGNORECASE)
    return result


# ---------------------------------------------------------------------------
# Phase 13.7C: Normalization helpers — applied after contract guard pass.
# ---------------------------------------------------------------------------

_REPEATED_NO_CAPITAL_RE = re.compile(
    r"\b(?:no\s+){2,}capital(?:[^\n.]*)?",
    re.IGNORECASE,
)
_DOUBLE_PERIOD_RE = re.compile(r"\.{2,}")


def _normalize_repeated_capital_language(text: str) -> str:
    """Collapse 'no no capital' / 'no no no capital …' guard artifacts."""
    return _REPEATED_NO_CAPITAL_RE.sub("Watch-only; no capital.", text)


def _normalize_duplicate_punctuation(text: str) -> str:
    """Collapse '..' / '...' runs produced by sequential replacements."""
    return _DOUBLE_PERIOD_RE.sub(".", text)


def _apply_final_body_contract_guard(final_tier: str, body: str) -> str:
    """Chain: contract guard → repeated-capital normalizer → punctuation normalizer.

    Order matters: the contract guard may produce 'no no capital' when
    'capital authorized' appears inside an already-negated phrase (LSTR bug).
    Normalization runs after to clean those artifacts.
    Phase 13.7E: NEAR_ENTRY adds a final hardening pass to catch any upgrade-
    language that slipped through field-level neutralization.
    Phase 13.7F: diagnostic label sanitizer runs last for all tiers, catching
    any field-label phrase that slipped through the field-level pre-pass.
    Phase 13.7H: NEAR_ENTRY capital-language firewall neutralizes capital/
    action phrases and residual diagnostics.
    Phase 13.7I: narrative sovereignty guard runs after this function, as
    a separate signal-aware final pass in format_alert().
    """
    result = _apply_contract_guard(body, final_tier)
    result = _normalize_repeated_capital_language(result)
    result = _normalize_duplicate_punctuation(result)
    if final_tier == "NEAR_ENTRY":
        result = _finalize_near_entry_body_text(result)
    result = _sanitize_diagnostic_labels(result)
    result = _humanize_bare_gate_keys(result)
    # Phase 14C.2: STARTER prestige-language guard — must run before the boolean
    # firewall so any introduced phrase is also sanitized.
    if final_tier == "STARTER":
        result = _apply_starter_quality_guard(result)
    # Phase 14C.2: final-body boolean/debug firewall — last line of defence
    # against any "field=True/False" fragment surfacing in any section.
    result = _sanitize_boolean_debug_fragments(result)
    if final_tier == "NEAR_ENTRY":
        result = _apply_near_entry_capital_firewall(result)
    return result


# ---------------------------------------------------------------------------
# Phase 14C.1: directional language correction. "Dip toward" is only honest
# when the level is BELOW the current price; for a level above price the prose
# must use reclaim/push language. Applied in format_alert when the trade
# location context proves the confirmation level sits above scan price.
# ---------------------------------------------------------------------------

_DIP_TOWARD_RE = re.compile(r"\bdips?\s+toward(?:s)?\b", re.IGNORECASE)


# Phase 14C.3: candle evidence display helpers (display-only — never reads or
# writes any decision field). The veto humanizer mirrors candle_evidence's own
# map so discord_alerts stays self-contained (no cross-module import).
# ---------------------------------------------------------------------------

_CANDLE_VETO_TEXT = {
    "OPEN_ONLY":               "candle still open; close not confirmed.",
    "NO_CLOSE_CONFIRMATION":   "close confirmation missing.",
    "NO_NEXT_CANDLE_VERDICT":  "next-candle verdict pending.",
    "DOJI_AT_TRIGGER":         "doji at trigger; confirmation incomplete.",
    "HOSTILE_WICK":            "hostile wick against the setup direction.",
    "FAILED_RETEST":           "failed retest; no fresh aggression.",
    "HIGH_VOLUME_NO_PROGRESS": "high-volume effort produced limited progress.",
    "EXTENDED_FROM_VALUE":     "extended from value; chase risk.",
    "MID_RANGE_NO_LEVEL":      "mid-range; no level interaction.",
}

# When candle evidence is vetoed, "all conditions satisfied/met" cannot stand —
# the candle has not confirmed the claim. Display-only neutralization.
_CANDLE_ALL_CONDITIONS_RE = re.compile(
    r"\ball\s+conditions\s+(?:are\s+)?(?:satisfied|met)\b", re.IGNORECASE
)


def _humanize_candle_veto(veto: str) -> str:
    return _CANDLE_VETO_TEXT.get(str(veto or "").strip().upper(), "")


def _render_one_hour_lines(one_hour) -> list:
    """Compact 1H entry-trigger evidence block (Phase 14E.1). Display-only.

    Returns [] when the object is missing/disabled so alerts are never flooded.
    WATCH_ONLY / NO_ALERT never carry entry-ready language — the sentence is
    state-derived. Stale/degraded bar context renders an explicit caution.
    """
    if not isinstance(one_hour, dict):
        return []
    status = str(one_hour.get("status", "DISABLED"))
    if status == "DISABLED":
        return []

    state = str(one_hour.get("trigger_state", "NO_1H_EVIDENCE"))
    sentence = str(one_hour.get("scanner_sentence") or "").strip()
    score = one_hour.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    score_label = str(one_hour.get("score_label", "NO_VALID_1H_TRIGGER"))
    caps = one_hour.get("hard_caps_applied") or []
    caps_text = ", ".join(str(c) for c in caps) if caps else "none"
    truth = one_hour.get("pullback_retest_hold") or {}
    candle = one_hour.get("candle_truth") or {}
    location = one_hour.get("location_realism") or {}
    freshness = str(one_hour.get("data_freshness", "STALE"))

    out = [
        f"  1H trigger: {state} — {sentence}",
        f"  1H score:   {score_label} {score}/100; caps: {caps_text}",
        (
            "  1H truth:   "
            f"retest={truth.get('retest_truth', 'NONE')}, "
            f"hold={truth.get('hold_truth', 'NONE')}, "
            f"candle={candle.get('event_type', 'NONE')}, "
            f"location={location.get('label', 'MIDRANGE_NO_EDGE')}"
        ),
    ]
    if freshness in ("STALE", "DEGRADED"):
        out.append(
            "  1H caution: stale/degraded bar context; "
            "trigger-ready wording blocked."
        )
    return out


def _neutralize_all_conditions(text: str) -> str:
    """Cool 'all conditions satisfied/met' to honest developing language. Used
    only when an active candle veto contradicts a completed-claim phrasing."""
    if not text:
        return text
    return _CANDLE_ALL_CONDITIONS_RE.sub("conditions still developing", text)


# ---------------------------------------------------------------------------
# Phase 14C.3B: Alert truth harmonization helpers.
#
# Five surgical defect fixes so an alert never contradicts its own tier,
# blocker, location, or candle evidence:
#   1. Synthesize missing-condition / upgrade-trigger when blank (NEAR_ENTRY).
#   2. Neutralize generic completion language when a candle gap exists.
#   3. Derive honest capital posture for repeated / cooldown-expired signals.
#   4. Deduplicate scan-time freshness notes.
#   5. Harmonize the proof line when candle confirmation is still required.
#
# Display-only.  Never mutates score, tier, capital_action, routing,
# suppression, dedup, or any structured decision field.
# ---------------------------------------------------------------------------

# Inline veto-humanizer (display-only; mirrors candle_evidence.humanize_candle_veto).
# Period-less version used in missing-condition synthesis (appended into sentences).
_CANDLE_VETO_HUMAN: dict[str, str] = {
    "OPEN_ONLY":               "candle still open; close not confirmed",
    "NO_CLOSE_CONFIRMATION":   "close confirmation missing",
    "NO_NEXT_CANDLE_VERDICT":  "next-candle verdict pending",
    "DOJI_AT_TRIGGER":         "doji at trigger; confirmation incomplete",
    "HOSTILE_WICK":            "hostile wick against the setup direction",
    "FAILED_RETEST":           "failed retest; no fresh aggression",
    "HIGH_VOLUME_NO_PROGRESS": "high-volume effort produced limited progress",
    "EXTENDED_FROM_VALUE":     "extended from value; chase risk",
    "MID_RANGE_NO_LEVEL":      "mid-range; no level interaction",
}

_SCAN_TIME_KEYWORDS = (
    "scan-time", "scan time", "verify live", "verify current price",
)

# Matches Claude-generated prose claiming all conditions are met (with or
# without a tier name). Does NOT match the CAPITAL_CONTRACT action headline
# "SNIPE_IT conditions met." because that headline lacks the "all" prefix.
_COMPLETION_LANG_RE = re.compile(
    r"\ball\s+(?:(?:SNIPE_IT|STARTER|the)\s+)?conditions\s+"
    r"(?:are\s+)?(?:satisfied|met|cleared|passed)\b",
    re.IGNORECASE,
)
_COMPLETION_REPLACEMENT: dict[str, str] = {
    "SNIPE_IT": (
        "Structural SNIPE_IT conditions satisfied; "
        "candle confirmation remains pending"
    ),
    "STARTER": (
        "Starter structure is valid; "
        "full-size confirmation remains pending"
    ),
    "NEAR_ENTRY": "Structure exists; execution confirmation remains incomplete",
}


def _is_blank_alert_field(value) -> bool:
    """True when a field is empty, a dash placeholder, or 'none'."""
    if value is None:
        return True
    return str(value).strip().lower() in ("", "—", "-", "none", "n/a", "na")


def _has_candle_confirmation_gap(candle: dict) -> bool:
    """True when candle evidence is incomplete, unresolved, forming, or failed.

    Returns False when candle is absent or is the safe unknown context
    (status='unknown').  Display-only — no decision side-effects.
    """
    if not candle:
        return False
    # Safe unknown context: status='unknown' and no real family populated.
    if candle.get("status") == "unknown" and not candle.get("candle_family"):
        return False
    veto    = str(candle.get("candle_veto",        "NONE")).strip().upper()
    verdict = str(candle.get("next_candle_verdict", "")).strip().upper()
    family  = str(candle.get("candle_family",       "UNKNOWN")).strip().upper()
    status  = str(candle.get("candle_status",       "")).strip().upper()
    if veto not in ("NONE", "UNKNOWN", ""):
        return True
    if verdict in ("PENDING", "NOT_AVAILABLE", "INDECISION", "FAIL"):
        return True
    if family in (
        "DOJI_INDECISION", "ABSORPTION", "UNRESOLVED",
        "OUTSIDE_VOLATILITY", "FAILED_BREAK",
    ):
        return True
    if status == "OPEN_OR_UNKNOWN":
        return True
    return False


def _derive_missing_conditions(
    signal: dict,
    candle: dict,
    tl_ctx: dict,
    blocker_note: str,
) -> str:
    """Synthesize a truthful missing-condition sentence when the field is blank.

    Priority: blocker note (primary) → retest → hold → lower-zone defense
    → candle caution.  Never invents prices.  Display-only.
    """
    bn = str(blocker_note or "").strip()
    if bn:
        return bn

    parts: list[str] = []
    sig    = signal or {}
    retest = str(sig.get("retest_status", "")).lower()
    hold   = str(sig.get("hold_status",   "")).lower()

    if retest not in ("confirmed",):
        parts.append(
            "Clean retest is incomplete; "
            "wait for full zone interaction and hold"
        )
    if hold not in ("confirmed",):
        parts.append(
            "Hold confirmation remains incomplete; "
            "wait for body-close acceptance inside/above the active zone"
        )

    if tl_ctx:
        state = str(tl_ctx.get("location_state") or "").lower()
        if state == "lower_zone_defense":
            parts.append(
                "Price is still defending the lower zone; "
                "confirmation above the stated proof level is required"
            )

    if candle:
        veto = str(candle.get("candle_veto", "NONE")).strip().upper()
        veto_text = _CANDLE_VETO_HUMAN.get(veto, "")
        if veto_text:
            parts.append(veto_text)

    return ". ".join(parts) + "." if parts else "—"


def _derive_upgrade_trigger(
    signal: dict,
    tl_ctx: dict,
    candle: dict,
) -> str:
    """Synthesize an upgrade trigger using the Phase 14C.3C source-priority law.

    Uses _select_upgrade_trigger_level to enforce correct level-source hierarchy.
    Never returns a target/T1/T2/liquidity level as the execution proof trigger.
    Display-only.
    """
    level, source, _ = _select_upgrade_trigger_level(signal, tl_ctx)

    if level is not None:
        if source == "zone_low":
            return (
                f"Retest the active zone and close back above "
                f"{level:.2f} with hold confirmation."
            )
        return f"Body close / acceptance above {level:.2f} with hold confirmation."

    if candle:
        veto = str(candle.get("candle_veto", "NONE")).strip().upper()
        if veto not in ("NONE", "UNKNOWN", ""):
            return "Next candle confirms direction without violating invalidation."

    return "Retest the active zone and confirm hold with a body close before any capital."


def _neutralize_completion_language_for_candle_gap(
    text: str,
    tier: str,
    has_gap: bool,
) -> str:
    """Replace generic completion language with tier-specific honest text when
    candle evidence is incomplete.  Preserves the CAPITAL_CONTRACT structured
    ACTION headline ('SNIPE_IT conditions met.') which never carries 'all'.
    Display-only — no score/tier/capital mutation.
    """
    if not has_gap or not text:
        return text
    replacement = _COMPLETION_REPLACEMENT.get(tier, "conditions still developing")
    return _COMPLETION_LANG_RE.sub(replacement, text)


def _derive_capital_posture_line(
    final_tier: str,
    candle: dict,
    tl_ctx: dict,
) -> str:
    """Return the capital-posture sentence for a repeated / cooldown-expired signal.

    Display-only — never mutates tier, capital_action, or routing.
    """
    has_gap = _has_candle_confirmation_gap(candle or {})

    proof_above = False
    if tl_ctx:
        conf = tl_ctx.get("confirmation_level")
        scan = tl_ctx.get("scan_price")
        try:
            proof_above = (
                conf is not None and scan is not None
                and float(conf) > float(scan)
            )
        except (TypeError, ValueError):
            pass

    if final_tier == "SNIPE_IT":
        if has_gap or proof_above:
            return (
                "Capital posture: hold existing only; "
                "no fresh add until candle/location proof confirms."
            )
        return (
            "Capital posture: add only after live price still holds "
            "trigger/location and invalidation remains valid."
        )
    if final_tier == "NEAR_ENTRY":
        return "Capital posture: no capital; watch only until blocker resolves."
    if final_tier == "STARTER":
        return (
            "Capital posture: starter only; "
            "no add until next proof confirms."
        )
    return ""


def _dedupe_freshness_notes(
    freshness_note: str,
    is_repeated: bool,
    has_candle_evidence: bool,
) -> list[str]:
    """Return a deduped list of freshness note strings for the FRESHNESS block.

    When the existing note already carries scan-time language and the alert is
    also repeated, collapse to one unified note instead of printing two notes
    that say the same thing.
    """
    note = str(freshness_note or "").strip()
    note_is_scan_time = any(kw in note.lower() for kw in _SCAN_TIME_KEYWORDS)

    if is_repeated or note_is_scan_time:
        unified = (
            "Signal is scan-time only; verify current price and candle "
            "state before action."
            if has_candle_evidence
            else "Signal is scan-time only; verify current price before action."
        )
        if note_is_scan_time:
            return [unified]
        notes: list[str] = []
        if note:
            notes.append(note)
        notes.append(unified)
        return notes

    return [note] if note else []


# ---------------------------------------------------------------------------
# Phase 14C.3C: Upgrade-trigger level source guard.
#
# Prevents trade_location.confirmation_level (which trade_location.py can
# set to T1 / the first target when price is below the zone) from ever
# appearing as the "Upgrade trigger:" execution proof level.
#
# Source-priority law (highest → lowest):
#   1. confirmation_level   — only when NOT a target value
#   2. proof_level          — from signal (if present)
#   3. trigger_level        — always trusted; shown on the EXECUTION line
#   4. zone_high            — FVG / OB top (long-setup proof)
#   5. zone_low             — last resort (retest-and-hold phrasing)
#   Never: any value that appears in signal.targets[], t1, t2, take_profit.
#
# Display-only.  Never mutates score, tier, capital, routing, or any
# structured decision field.
# ---------------------------------------------------------------------------

# Labels that identify take-profit / exit / liquidity / target levels.
_TARGET_LEVEL_LABELS: set[str] = set({
    "t1", "t2", "t3", "tp", "tp1", "tp2", "tp3",
    "target", "ltp",
    "liquidity", "liquidity_pool", "nearest_liquidity_pool",
    "measured_move", "extension_target", "extension",
    "take_profit", "profit_target",
})


def _is_target_like_label(label_str: str) -> bool:
    """True when label identifies a take-profit / liquidity / target level."""
    return str(label_str or "").strip().lower() in _TARGET_LEVEL_LABELS


def _valid_execution_proof_level(value) -> "float | None":
    """Return float if value is numeric, finite, and positive; else None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0:
        return None
    return f


def _collect_target_levels(signal: dict) -> set:
    """Return all numeric level values listed in signal.targets[].

    Every entry in targets[] is a profit / liquidity / exit target.
    None of them should be selected as the upgrade-trigger proof level.
    Direct t1/t2/take_profit fields are also included.
    """
    result: set[float] = set()
    targets = (signal or {}).get("targets") or []
    if isinstance(targets, list):
        for t in targets:
            if isinstance(t, dict):
                lv = _valid_execution_proof_level(t.get("level"))
                if lv is not None:
                    result.add(lv)
    for field in ("t1", "t2", "tp1", "tp2", "take_profit"):
        v = _valid_execution_proof_level((signal or {}).get(field))
        if v is not None:
            result.add(v)
    return set(result)


def _select_upgrade_trigger_level(
    signal: dict,
    tl_ctx: dict,
) -> "tuple[float | None, str, str]":
    """Priority-ordered selection of a valid execution-proof level for display.

    Returns (level, source_name, reason).
    Returns (None, '', reason) when no valid proof level exists.
    Never selects a value that appears in the signal's targets list.
    """
    banned = _collect_target_levels(signal)
    sig = signal or {}
    tl  = tl_ctx or {}

    # 1. confirmation_level — trade_location's computed proof level.
    #    Rejected when trade_location fell back to _first_target() (T1 contamination).
    conf = _valid_execution_proof_level(tl.get("confirmation_level"))
    if conf is not None and conf not in banned:
        return (conf, "confirmation_level", "trade-location confirmation level")

    # 2. proof_level from signal (explicit field, rarely populated but trusted)
    proof = _valid_execution_proof_level(sig.get("proof_level"))
    if proof is not None and proof not in banned:
        return (proof, "proof_level", "signal proof level")

    # 3. trigger_level — the execution anchor shown on the EXECUTION line.
    #    Always an entry-proof level, never a take-profit.
    trigger = _valid_execution_proof_level(sig.get("trigger_level"))
    if trigger is not None:
        return (trigger, "trigger_level", "execution trigger level")

    # 4. zone_high — FVG top / OB top (long-setup proof)
    zone_high = _valid_execution_proof_level(tl.get("zone_high"))
    if zone_high is not None and zone_high not in banned:
        return (zone_high, "zone_high", "zone top — execution proof level")

    # 5. zone_low — last resort; rendered with retest-and-hold phrasing
    zone_low = _valid_execution_proof_level(tl.get("zone_low"))
    if zone_low is not None and zone_low not in banned:
        return (zone_low, "zone_low", "zone low — retest-and-hold proof")

    return (None, "", "no valid execution proof level found")


# ---------------------------------------------------------------------------
# Phase 13.7E: NEAR_ENTRY-only upgrade-language seal + dangling tail cleaner.
# ---------------------------------------------------------------------------

# Matches prose fragments that reference upgrading to SNIPE_IT or STARTER inside
# a NEAR_ENTRY alert.  Applied to individual prose fields (reason, next_action)
# before rendering, so structural label prefixes ("  Why:  ", "  Next: ") are not
# consumed.
_NE_UPGRADE_SENTENCE_RE = re.compile(
    # "upgrade/upgrades/upgraded/upgrading to SNIPE_IT/STARTER [or SNIPE_IT/STARTER]
    # [consideration]" and "SNIPE_IT/STARTER consideration".
    # Note: "upgrading" = upgrad+ing (no 'e'), so it cannot be written as
    # "upgrade" + suffix — the two branches handle both root spellings.
    r"[^.\n]*"
    r"\b(?:"
    r"(?:upgrade[sd]?|upgrading)\s+(?:conviction\s+)?to\s+"
    r"(?:SNIPE_IT|STARTER)(?:\s+or\s+(?:SNIPE_IT|STARTER))?"
    r"(?:\s+consideration)?"
    r"|(?:SNIPE_IT|STARTER)\s+consideration"
    r")\b"
    r"[^.\n]*\.?",
    re.IGNORECASE,
)
_NE_UPGRADE_REPLACEMENT = "If confirmed, conviction improves for the next alert cycle."

# Matches "no capital" followed by artifact tails produced by sequential guard
# replacements, e.g. "no capital.01." or "no capital. only." or "no capital only."
_NE_CAPITAL_TAIL_RE = re.compile(
    r"(no\s+capital)"
    r"(?:"
    r"\.\s+only\.?"
    r"|\.\d+\.?"
    r"|\s+only\.?"
    r")",
    re.IGNORECASE,
)


def _neutralize_near_entry_upgrade_language(text: str) -> str:
    """Replace upgrade-tier sentences in a NEAR_ENTRY prose field.

    Applied to individual fields before rendering so structural label prefixes
    are not consumed.  Collapses duplicate replacement sentences produced when
    a field contains more than one upgrade-language fragment.
    """
    cleaned = _NE_UPGRADE_SENTENCE_RE.sub(_NE_UPGRADE_REPLACEMENT, text)
    # Collapse repeated replacement sentence produced by multiple sub() matches.
    replacement_escaped = re.escape(_NE_UPGRADE_REPLACEMENT)
    cleaned = re.sub(
        rf"(?:{replacement_escaped}\s*){{2,}}",
        _NE_UPGRADE_REPLACEMENT,
        cleaned,
    )
    return cleaned.strip()


def _clean_near_entry_dangling_tails(text: str) -> str:
    """Remove artifact tails attached to 'no capital' left by guard replacements."""
    return _NE_CAPITAL_TAIL_RE.sub(r"\1.", text)


def _finalize_near_entry_body_text(text: str) -> str:
    """Safety-net pass for NEAR_ENTRY fully-rendered text.

    Catches any upgrade-language that slipped through field-level neutralization
    (e.g. in blocker notes or missing-condition strings), then cleans dangling
    tails, then seals any tier-mechanics classification language.
    Called inside _apply_final_body_contract_guard for NEAR_ENTRY only.
    """
    result = _NE_UPGRADE_SENTENCE_RE.sub(_NE_UPGRADE_REPLACEMENT, text)
    result = _clean_near_entry_dangling_tails(result)
    result = _seal_near_entry_classification_language(result)
    return result


def _clean_blocker_label(note: str | None) -> str:
    """Strip one or more leading 'Blocker:' prefixes from a blocker note string.

    _build_near_entry_blocker_note returns 'Blocker: X'; the renderer adds its
    own 'Blocker:' label prefix. Without this helper the rendered line would be
    'Blocker:            Blocker: X'. Stripping here keeps it clean.
    """
    if not note:
        return ""
    return re.sub(r"^(Blocker:\s*)+", "", note, flags=re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
# Phase 13.7D: Human-facing text renderer for missing conditions,
# upgrade triggers, and blocker notes.
# ---------------------------------------------------------------------------

# Exact-match translation map: internal engine label → human-readable string.
# Used for labels produced by _backfill_missing_conditions and
# _near_entry_blocker_backfill.
_CONDITION_LABEL_MAP: dict[str, str] = {
    "missing_retest":            "Retest not yet confirmed",
    "missing_hold":              "Hold not yet confirmed",
    "current_acceptance_needed": "Awaiting zone acceptance confirmation",
    "retest_not_confirmed":      "Retest not yet confirmed",
    "hold_not_confirmed":        "Hold not yet confirmed",
    "retest_partial":            "Retest partially confirmed — awaiting full confirmation",
    "hold_partial":              "Hold partially confirmed — awaiting full confirmation",
    "overhead_path_not_clean":   "Overhead path not clean enough for capital",
    "overhead_blocked":          "Overhead resistance blocking capital",
}

# Strips raw diagnostic "key_name: " prefixes produced when Claude embeds
# field names in free-text fields (e.g. "retest_status: price has not returned…").
_RAW_FIELD_LABEL_RE = re.compile(
    r"\b(retest_status|hold_status|price_in_zone|trigger_status|overhead_status)\s*:\s*",
    re.IGNORECASE,
)

# Matches "upgrade to TIER / upgrading to TIER" patterns.
_UPGRADE_TIER_RE = re.compile(
    r"\b(?:upgrade(?:s|d|ing)?\s+to|upgrading\s+to)\s+(SNIPE_IT|STARTER|NEAR_ENTRY)\b",
    re.IGNORECASE,
)

# Human replacement for tier-name references inside NEAR_ENTRY upgrade trigger.
_UPGRADE_TIER_HUMAN: dict[str, str] = {
    "snipe_it":   "confirms the setup for review on the next alert cycle",
    "starter":    "improves conviction for the next alert cycle",
    "near_entry": "improves conviction for the next alert cycle",
}


def _humanize_missing_condition(cond: str) -> str:
    """Translate a single missing-condition label to human-readable text.

    Handles three forms in priority order:
      1. Exact internal label → translation map ("missing_retest" → "Retest not yet confirmed")
      2. "label — description" format → use description part (capitalized), or map if label matches
      3. Raw diagnostic prefix ("retest_status: …") → strip prefix, capitalize remainder
      4. Unknown label → return as-is (preserves existing behavior)
    """
    s = str(cond).strip()
    if not s:
        return s

    lower = s.lower()

    # 1. Exact match
    if lower in _CONDITION_LABEL_MAP:
        return _CONDITION_LABEL_MAP[lower]

    # 2. "label — description" em-dash format
    if " — " in s:
        label_part, _, desc_part = s.partition(" — ")
        map_val = _CONDITION_LABEL_MAP.get(label_part.strip().lower())
        if map_val:
            return map_val
        desc_part = desc_part.strip()
        if desc_part:
            return desc_part[0].upper() + desc_part[1:]

    # 3. Strip raw field-label prefix
    cleaned = _RAW_FIELD_LABEL_RE.sub("", s).strip()
    if cleaned != s:
        return cleaned[0].upper() + cleaned[1:] if cleaned else cleaned

    # 4. Fallback — return unchanged
    return s


def _humanize_upgrade_trigger(text: str, final_tier: str) -> str:
    """Strip raw field labels and, for NEAR_ENTRY, replace tier-name references.

    For NEAR_ENTRY: "upgrade to STARTER" → neutral watchlist guidance so
    subscribers see trader-facing language, not tier mechanics.
    For other tiers: only strips raw diagnostic prefixes.
    """
    if not text or text in ("—", "none", "None"):
        return text

    result = _RAW_FIELD_LABEL_RE.sub("", text).strip()

    if final_tier == "NEAR_ENTRY":
        def _replace_tier(m: re.Match) -> str:
            return _UPGRADE_TIER_HUMAN.get(
                m.group(1).lower(),
                "improves conviction for the next alert cycle",
            )
        result = _UPGRADE_TIER_RE.sub(_replace_tier, result)

    return result


def _humanize_blocker_note(text: str) -> str:
    """Strip raw diagnostic key_name: prefixes from a blocker note string."""
    if not text:
        return text
    return _RAW_FIELD_LABEL_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Phase 13.7F: Residual diagnostic label sanitizer — all tiers.
#
# Converts raw internal field-label phrases leaking into Claude prose fields
# into human-readable equivalents.  Two connector forms are handled:
#   "field_name is value"  (the AMKR live defect — "retest_status is partial")
#   "field_name: value"    (colon form, now with full translation)
# Applied field-level (reason, next_action, all tiers) and as a final-body
# safety-net inside _apply_final_body_contract_guard().
# ---------------------------------------------------------------------------

# (field_lower, value_lower) → human-readable phrase.
_DIAG_IS_MAP: dict[tuple[str, str], str] = {
    # retest_status
    ("retest_status",    "partial"):          "retest is only partially confirmed",
    ("retest_status",    "confirmed"):        "retest is confirmed",
    ("retest_status",    "missing"):          "retest has not yet been confirmed",
    ("retest_status",    "failed"):           "retest failed",
    # hold_status
    ("hold_status",      "partial"):          "hold is only partially confirmed",
    ("hold_status",      "confirmed"):        "hold is confirmed",
    ("hold_status",      "missing"):          "hold has not yet been confirmed",
    ("hold_status",      "failed"):           "hold failed",
    # price_in_zone
    ("price_in_zone",    "true"):             "price is inside the zone",
    ("price_in_zone",    "false"):            "price is not yet inside the zone",
    # trigger_status
    ("trigger_status",   "below_trigger"):    "price remains below trigger",
    ("trigger_status",   "above_trigger"):    "price is above trigger",
    ("trigger_status",   "at_trigger"):       "price is at trigger",
    # overhead_status
    ("overhead_status",  "moderate"):         "overhead is moderate",
    ("overhead_status",  "blocked"):          "overhead is blocked",
    ("overhead_status",  "clear"):            "overhead is clear",
    # invalidation_level special values (underscore and space forms)
    ("invalidation_level", "not_applicable"): "executable invalidation pending live zone confirmation",
    ("invalidation_level", "not applicable"): "executable invalidation pending live zone confirmation",
    # risk_state
    ("risk_state",       "tight"):            "risk window is tight relative to zone",
    ("risk_state",       "healthy"):          "risk window is healthy",
    ("risk_state",       "wide"):             "risk window is wide",
}

# Fallback human field name for values not in the map.
_FIELD_HUMAN_NAME: dict[str, str] = {
    "retest_status":      "retest",
    "hold_status":        "hold",
    "price_in_zone":      "price-in-zone",
    "trigger_status":     "trigger status",
    "overhead_status":    "overhead",
    "invalidation_level": "invalidation",
    "risk_state":         "risk state",
}

# "field_name is value" — value is a single word (including underscore words like
# "below_trigger").  Single-word only to prevent matching conjunctions like "and"
# when two field phrases appear in the same sentence.
_DIAG_LABEL_IS_RE = re.compile(
    r"\b(retest_status|hold_status|price_in_zone|trigger_status|"
    r"overhead_status|invalidation_level|risk_state)"
    r"\s+is\s+([\w]+)\b",
    re.IGNORECASE,
)

# "field_name: value" — colon form; single-word value capture.
_DIAG_LABEL_COLON_RE = re.compile(
    r"\b(retest_status|hold_status|price_in_zone|trigger_status|"
    r"overhead_status|invalidation_level|risk_state)"
    r"\s*:\s*([\w]+)\b",
    re.IGNORECASE,
)

# "invalidation_level: not applicable" — colon + two-word value; handled before
# the general colon pass to guarantee the two-word key is matched intact.
_INVAL_NOT_APPLICABLE_RE = re.compile(
    r"\binvalidation_level\s*:\s*not\s+applicable\b",
    re.IGNORECASE,
)

# "invalidation_level is not applicable" — "is" connector + two-word value;
# handled before the general "is" pass for the same reason.
_INVAL_IS_NOT_APPLICABLE_RE = re.compile(
    r"\binvalidation_level\s+is\s+not\s+applicable\b",
    re.IGNORECASE,
)


def _replace_diag_phrase(field_raw: str, value_raw: str) -> str:
    """Translate a (field, value) pair to human-readable text."""
    field_lower = field_raw.lower()
    value_lower = value_raw.lower().strip()
    key = (field_lower, value_lower)
    if key in _DIAG_IS_MAP:
        return _DIAG_IS_MAP[key]
    # Fallback: use human field name with value (underscores stripped).
    human_field = _FIELD_HUMAN_NAME.get(field_lower, field_lower.replace("_", " "))
    human_value = value_lower.replace("_", " ")
    return f"{human_field} is {human_value}"


def _sanitize_diagnostic_labels(text: str) -> str:
    """Replace raw internal field-label phrases with human-readable equivalents.

    Handles three forms in order:
    1. "invalidation_level: not applicable" — two-word colon value (special-cased
       to guarantee the lookup key is matched before the general colon pass).
    2. "field_name is value"  — e.g. "retest_status is partial" (AMKR live defect).
    3. "field_name: value"    — colon form with full translation.

    Applied field-level to reason/next_action for all tiers, and as a final-body
    safety-net inside _apply_final_body_contract_guard().
    """
    if not text:
        return text

    # 0. Engine/validator summary phrases — replaced before field-label pass.
    # "All conditions satisfied / met" is Claude's validator shorthand; it leaks
    # into reason/next_action when the model summarises its internal gate check.
    # Replace with neutral language that doesn't claim trade-readiness.
    result = re.sub(
        r"\ball conditions (?:satisfied|met)\b",
        "setup conditions developing",
        text,
        flags=re.IGNORECASE,
    )

    # 1. Two-word forms handled first (before single-word pass captures partial match).
    result = _INVAL_NOT_APPLICABLE_RE.sub(
        "executable invalidation pending live zone confirmation", result
    )
    result = _INVAL_IS_NOT_APPLICABLE_RE.sub(
        "executable invalidation pending live zone confirmation", result
    )

    # 2. "field_name is value" (single word)
    result = _DIAG_LABEL_IS_RE.sub(
        lambda m: _replace_diag_phrase(m.group(1), m.group(2)), result
    )

    # 3. "field_name: value"
    result = _DIAG_LABEL_COLON_RE.sub(
        lambda m: _replace_diag_phrase(m.group(1), m.group(2)), result
    )

    return result


# ---------------------------------------------------------------------------
# Phase 13.7G: Bare gate-key humanizer + NEAR_ENTRY classification-language seal.
#
# Converts bare snake_case gate keys (e.g. "retest_confirmed", "hold_confirmed")
# that appear in missing_conditions lists, blocker notes, or prose fields into
# human-readable text.  Also neutralizes tier-mechanics classification language
# in NEAR_ENTRY narrative fields.
# ---------------------------------------------------------------------------

# Maps bare snake_case gate keys → human text (missing/not-met context).
# Used by _humanize_bare_gate_keys(); entries matched as whole words.
_GATE_KEY_MAP: dict[str, str] = {
    "retest_confirmed":          "Retest not confirmed",
    "hold_confirmed":            "Hold not confirmed",
    "price_in_zone":             "Price has not returned to the zone",
    "trigger_confirmed":         "Trigger acceptance not confirmed",
    "overhead_clear":            "Overhead path not clean",
    "risk_realism_valid":        "Risk window not valid",
    "asymmetry_valid":           "R:R / asymmetry not valid",
    "invalidation_clarity":      "Invalidation not clear",
    "volume_confirmed":          "Volume confirmation missing",
    "sma_alignment_supportive":  "SMA alignment not supportive",
    "acceptance_confirmed":      "Acceptance not confirmed",
    "break_confirmed":           "Break confirmation missing",
    # missing_ prefix variants
    "missing_retest":            "Retest not confirmed",
    "missing_hold":              "Hold not confirmed",
    "missing_price_in_zone":     "Price has not returned to the zone",
    "missing_trigger":           "Trigger acceptance not confirmed",
    "missing_overhead_clear":    "Overhead path not clean",
    "missing_risk_realism":      "Risk window not valid",
}

# Build whole-word regex from the map — longest keys first to prevent partial
# shadowing (e.g. "missing_retest" before bare "retest_confirmed").
_GATE_KEYS_PATTERN = "|".join(
    re.escape(k) for k in sorted(_GATE_KEY_MAP.keys(), key=len, reverse=True)
)
_GATE_KEY_WORD_RE = re.compile(
    rf"\b({_GATE_KEYS_PATTERN})\b",
    re.IGNORECASE,
)


def _humanize_bare_gate_keys(text: str) -> str:
    """Replace bare snake_case gate keys with human-readable equivalents.

    Handles comma/semicolon-separated lists as well as inline sentence use.
    Applied field-level to reason, next_action, upgrade_trigger, and blocker_note,
    and as a final-body safety-net inside _apply_final_body_contract_guard().
    """
    if not text:
        return text

    def _replace(m: re.Match) -> str:
        return _GATE_KEY_MAP.get(m.group(1).lower(), m.group(1))

    return _GATE_KEY_WORD_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# Phase 14C.2: boolean / debug-fragment sanitizer.
#
# Internal scanner booleans (price_in_zone=True, price_at_ob=True,
# price_at_fvg=True) and any residual "field=True/False" fragment must never
# reach Discord — the alert is an execution contract, not a debug dump. The
# bare-gate-key humanizer can also expand a key and leave a dangling "=True"
# tail (e.g. "...returned to the zone=True"); this pass repairs both the raw and
# the half-humanized forms.
# ---------------------------------------------------------------------------

_BOOL_ZONE_PHRASE = (
    r"(?:price\s+has\s+(?:not\s+)?returned\s+to\s+the\s+(?:active\s+)?zone"
    r"|price[_ ](?:in|at)[_ ][a-z_]+"
    r"|in[_ ]zone|at[_ ](?:ob|fvg))"
)
_BOOL_ZONE_TRUE_RE  = re.compile(_BOOL_ZONE_PHRASE + r"\s*=\s*true\b",  re.IGNORECASE)
_BOOL_ZONE_FALSE_RE = re.compile(_BOOL_ZONE_PHRASE + r"\s*=\s*false\b", re.IGNORECASE)
_BOOL_GENERIC_RE    = re.compile(r"\s*\b[\w.\-/]+\s*=\s*(?:true|false)\b", re.IGNORECASE)
_BOOL_SPACE_BEFORE_PUNCT_RE = re.compile(r" ([.,;])")


def _sanitize_boolean_debug_fragments(text: str) -> str:
    """Strip/rewrite internal boolean/debug fragments so no '=True'/'=False'
    leaks into the alert body. Zone-presence booleans become human zone prose;
    any other field=bool fragment is removed. Safe to run on the full body —
    it never collapses intentional column-alignment whitespace.
    """
    if not text:
        return text
    result = _BOOL_ZONE_TRUE_RE.sub(
        "Price has returned to the active zone and is attempting to hold", text
    )
    result = _BOOL_ZONE_FALSE_RE.sub(
        "Price has not yet returned to the active zone", result
    )
    result = _BOOL_GENERIC_RE.sub("", result)
    result = _BOOL_SPACE_BEFORE_PUNCT_RE.sub(r"\1", result)
    return result


# ---------------------------------------------------------------------------
# Phase 14C.2: trail-stop language safety.
#
# "Trail stop" is profit-protection language and is honest only when the stop
# tightens risk (moves toward entry/profit). A "trail stop" placed BELOW the
# current invalidation widens risk and is really a deep-failure reference — it
# must be relabelled so the alert never disguises added risk as protection.
# ---------------------------------------------------------------------------

_TRAIL_STOP_LEVEL_RE = re.compile(
    r"\btrail(?:ing)?\s+stop\b"
    r"(?:\s+(?:below|under|at|near|to)\s*\$?(\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)
_TRAIL_STOP_WORD_RE = re.compile(r"\btrail(?:ing)?\s+stop\b", re.IGNORECASE)


def _sanitize_trail_stop_language(text: str, inval_level) -> str:
    """Relabel a 'trail stop' that sits below the invalidation as a deep-failure
    reference. Trail wording survives only when it tightens risk.
    """
    if not text:
        return text
    try:
        inval = float(inval_level) if inval_level is not None else None
    except (TypeError, ValueError):
        inval = None
    if inval is None:
        return text

    def _repl(m: re.Match) -> str:
        whole   = m.group(0)
        lvl_str = m.group(1)
        if lvl_str is None:
            return whole
        try:
            lvl = float(lvl_str)
        except ValueError:
            return whole
        if lvl < inval:
            return _TRAIL_STOP_WORD_RE.sub("deep failure reference", whole)
        return whole

    return _TRAIL_STOP_LEVEL_RE.sub(_repl, text)


# ---------------------------------------------------------------------------
# Phase 14C.2: STARTER quality language guard.
#
# STARTER alerts must not carry prestige/elite language that implies full-size
# authorization. The "High-quality STARTER" tier label is sanctioned and
# exempt; generic "high-quality" prose claims are cooled to "strong tactical".
# Display-only — does not affect tier, capital_action, or routing.
# ---------------------------------------------------------------------------

_QLG_STARTER: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\ball\s+conditions\s+(?:are\s+)?(?:satisfied|met)\b", re.IGNORECASE),
     "starter conditions met"),
    (re.compile(r"\ball\s+(?:5|five)\b", re.IGNORECASE), "several"),
    # Phase 14C.2: the sanctioned "High-quality STARTER" tier label is exempt
    # (it already names the tier and states the capital limit); cool every other
    # bare "high-quality" prestige claim.
    (re.compile(r"\bhigh[-\s]quality\b(?!\s+starter)", re.IGNORECASE), "strong tactical"),
    # Affirmative full-size grants only — denial language ("full-size
    # authorization not granted", "full-size capital withheld") must survive.
    (re.compile(r"\bfull[-\s]siz(?:e|ed)\s+(?:allowed|authorized|authorization\s+granted"
                r"|position|entry)\b", re.IGNORECASE), "starter size only"),
]


def _apply_starter_quality_guard(body: str) -> str:
    """Cool prestige/elite language in STARTER alert bodies (display-only).

    The 'High-quality STARTER' tier label is sanctioned and survives unchanged.
    """
    for pat, repl in _QLG_STARTER:
        body = pat.sub(repl, body)
    return body


def _parse_missing_conditions(raw) -> list[str]:
    """Normalize missing_conditions from a string or list to individual tokens.

    Handles:
    - list of strings: ["retest_confirmed", "hold_confirmed"]
    - comma-separated string: "retest_confirmed, hold_confirmed"
    - semicolon-separated string: "retest_confirmed; hold_confirmed"
    - each list item may itself be comma/semicolon-separated
    """
    if not raw:
        return []
    tokens: list[str] = []
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        for tok in re.split(r"[,;]\s*", str(item).strip()):
            tok = tok.strip()
            if tok:
                tokens.append(tok)
    return tokens


def _format_missing_conditions(items: list[str]) -> str:
    """Format humanized missing-condition items as a single readable string.

    Sentence case (first item kept as-is, subsequent items lower-cased),
    semicolon-separated, trailing period.  Returns "—" for an empty list.
    """
    if not items:
        return "—"
    parts = [items[0]]
    parts += [
        (item[0].lower() + item[1:]) if len(item) > 1 else item.lower()
        for item in items[1:]
    ]
    result = "; ".join(parts)
    if result and not result.endswith("."):
        result += "."
    return result


# Matches NEAR_ENTRY-inappropriate tier-mechanics classification phrases.
# "preventing X classification" → "preventing capital authorization"
# "X classification" / "tier upgrade" / "classification upgrade" → "capital authorization"
_NE_CLASSIFICATION_RE = re.compile(
    r"\b(?:"
    r"preventing\s+(?:STARTER|SNIPE_IT)(?:\s+or\s+(?:STARTER|SNIPE_IT))?\s+classification"
    r"|(?:STARTER|SNIPE_IT)(?:\s+or\s+(?:STARTER|SNIPE_IT))?\s+classification"
    r"|(?:tier|classification)\s+upgrade"
    r")\b",
    re.IGNORECASE,
)


def _ne_classify_replace(m: re.Match) -> str:
    if "preventing" in m.group(0).lower():
        return "preventing capital authorization"
    return "capital authorization"


def _seal_near_entry_classification_language(text: str) -> str:
    """Neutralize tier-mechanics classification language in NEAR_ENTRY prose.

    Replaces 'preventing X classification', 'X classification', 'tier upgrade',
    and 'classification upgrade' with trading-desk equivalents.
    Applied to NEAR_ENTRY fields only — STARTER/SNIPE_IT tier identities preserved.
    """
    if not text:
        return text
    return _NE_CLASSIFICATION_RE.sub(_ne_classify_replace, text)


# ---------------------------------------------------------------------------
# Phase 13.7H: NEAR_ENTRY capital-language final firewall + residual diagnostic
# safety net.
#
# Neutralizes capital/action phrases that survived all prior passes (CAPITAL_CONTRACT
# forbidden list, 13.7E upgrade seal, 13.7F diagnostic sanitizer, 13.7G gate-key
# humanizer).  Also provides a last-resort catch for raw diagnostic field phrases.
# Applied as a NEAR_ENTRY-only final pass at the end of _apply_final_body_contract_guard().
# ---------------------------------------------------------------------------

# (pattern, replacement) — longest / most-specific phrases first within each group
# to prevent partial-match shadowing.
_NE_CAPITAL_ACTION_FIREWALL: list[tuple[str, str]] = [
    # Sizing language
    (r"\bbefore\s+adding\s+size\b",
     "before the next alert review"),
    (r"\bsize\s+can\s+be\s+reviewed\b",
     "setup can be reconsidered on the next alert review"),
    (r"\badding\s+size\b",
     "reconsidering on the next alert review"),
    (r"\badd\s+size\b",
     "reconsider on the next alert review"),
    # Entry language
    (r"\benter\s+on\s+confirmation\b",
     "wait for confirmation; no capital until blocker resolves"),
    (r"\benter\s+on\b",
     "wait for confirmation"),
    (r"\bentry\s+valid\b",
     "setup remains on watch"),
    # Capital / position management
    (r"\bcapital\s+commitment\b",
     "watch commitment"),
    (r"\btrail\s+stop\b",
     "use invalidation reference only"),
    # Residual diagnostic field-label phrases — safety net for 13.7F body-pass misses.
    # Single-word "is" form only (two-word "not applicable" is handled by 13.7F).
    (r"\bretest_status\s+is\s+partial\b",   "retest is only partial"),
    (r"\bretest_status\s+is\s+missing\b",   "retest is missing"),
    (r"\bhold_status\s+is\s+partial\b",     "hold is not fully confirmed"),
    (r"\bhold_status\s+is\s+missing\b",     "hold is missing"),
    (r"\bprice_in_zone\s+is\s+true\b",      "price is inside the zone"),
    (r"\bprice_in_zone\s+is\s+false\b",     "price is not inside the zone"),
]

# Pre-compiled patterns for runtime efficiency.
_NE_CAPITAL_ACTION_FIREWALL_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _NE_CAPITAL_ACTION_FIREWALL
]


def _apply_near_entry_capital_firewall(text: str) -> str:
    """Final NEAR_ENTRY-only pass: neutralize capital/action language and
    catch residual diagnostic field phrases that survived all prior passes.

    Must run after _sanitize_diagnostic_labels() and _humanize_bare_gate_keys()
    so it operates on already-cleaned text.  NEAR_ENTRY only.
    """
    if not text:
        return text
    result = text
    for pattern_re, replacement in _NE_CAPITAL_ACTION_FIREWALL_COMPILED:
        result = pattern_re.sub(replacement, result)
    return result


# ---------------------------------------------------------------------------
# Phase 13.7I: Narrative sovereignty layer.
#
# Structured state is sovereign.  Narrative is downstream.
# The rendered alert must never overrule, soften, or contradict final_tier,
# retest_status, hold_status, overhead_status, risk_realism_state, or capital
# authorization.  This pass runs after all prior body sanitizers so it can
# inspect final_signal fields and eliminate any surviving contradiction.
#
# Rule groups:
#   1. Tier sovereignty  — NEAR_ENTRY / STARTER / SNIPE_IT forbidden phrases
#   2. Retest sovereignty — forbidden when retest_status != "confirmed"
#   3. Hold sovereignty   — forbidden when hold_status != "confirmed"
#   4. Overhead sovereignty — blocker active or status == "blocked"
#   5. Risk sovereignty   — fragile risk must be acknowledged, not masked
#   6. Final contradiction cleanup — normalization run after all replacements
# ---------------------------------------------------------------------------


def _compile_sovereignty_rules(
    rules: list[tuple[str, str]],
) -> list[tuple[re.Pattern, str]]:
    return [(re.compile(pattern, re.IGNORECASE), replacement) for pattern, replacement in rules]


def _apply_sovereignty_rules(
    text: str,
    compiled: list[tuple[re.Pattern, str]],
) -> str:
    result = text
    for pat, repl in compiled:
        result = pat.sub(repl, result)
    return result


# Rule Group 1a — NEAR_ENTRY: no capital / watch-only sovereignty.
# Defense-in-depth over CAPITAL_CONTRACT + 13.7H; adds phrases not yet covered.
# NOTE: use [ \t]+ (not \s+) throughout to prevent cross-line matching when
# these patterns are applied to the fully-rendered multiline alert body.
_SOVEREIGN_NE_RULES: list[tuple[str, str]] = [
    # Entry / action verbs (longest / most-specific first)
    (r"\bdeploy[ \t]+capital\b",                 "Watch-only; no capital."),
    (r"\bactionable[ \t]+now\b",                 "Watch-only; no capital."),
    (r"\bsequence[ \t]+complete\b",
     "If confirmed, conviction improves for the next alert cycle."),
    (r"\bdefended[ \t]+structure[ \t]+confirmed\b", "Structure repair in progress."),
    (r"\benter[ \t]+long\b",                     "Watch-only; wait for blocker resolution."),
    (r"\benter[ \t]+on[ \t]+confirmation\b",
     "wait for confirmation; no capital until blocker resolves"),
    (r"\benter[ \t]+on\b",                       "wait for confirmation"),
    (r"\bentry[ \t]+valid\b",                    "setup remains on watch"),
    # Sizing language
    (r"\bstarter[ \t]+sizing\b",                 "Watch-only; no capital."),
    (r"\bstarter[ \t]+size\b",                   "Watch-only; no capital."),
    (r"\badd[ \t]+to[ \t]+position\b",           "Watch-only; wait for blocker resolution."),
    (r"\bsize[ \t]+can[ \t]+be[ \t]+reviewed\b",
     "setup can be reconsidered on the next alert review"),
    (r"\badding[ \t]+size\b",                    "reconsidering on the next alert review"),
    (r"\badd[ \t]+size\b",                       "reconsider on the next alert review"),
    (r"\bscale\b",                               "Watch-only; wait for blocker resolution."),
    # Trade management
    (r"\btrail[ \t]+stop\b",                     "use invalidation reference only"),
    (r"\bposition[ \t]+management\b",            "Watch-only; wait for blocker resolution."),
    (r"\bno[ \t]+trade[ \t]+management\b",
     "No trade management needed until entry is authorized."),
    # Capital language
    (r"\bcapital[ \t]+authorized\b",             "no capital"),
    (r"\bfull[ \t]+quality\b",                   "no capital"),
    (r"\ball[ \t]+snipe_it[ \t]+conditions\b",   "Watch-only; no capital."),
    (r"\ball[ \t]+starter[ \t]+conditions\b",    "Watch-only; no capital."),
    (r"\bcapital[ \t]+commitment\b",             "watch commitment"),
]

# Rule Group 1b — STARTER: reduced-size sovereignty.
# NOTE: "full-size confirmation not granted" is valid STARTER denial language
# (see CAPITAL_CONTRACT comment) — the bare "full[\s-]size" is intentionally
# excluded to prevent false positives.  Only "full quality" and explicit
# SNIPE_IT-conditions phrases are forbidden.
_SOVEREIGN_STARTER_RULES: list[tuple[str, str]] = [
    (r"\bmaximum[ \t]+conviction\b",
     "STARTER SIZE ONLY — reduced-size capital only."),
    (r"\bpristine[ \t]+setup\b",
     "STARTER conditions met; full-size authorization not granted."),
    (r"\ball[ \t]+snipe_it[ \t]+conditions[ \t]+(?:met|satisfied|are[ \t]+(?:met|satisfied)|cleared|passed)\b",
     "STARTER conditions met; full-size authorization not granted."),
    (r"\bfull[ \t]+quality\b",
     "STARTER SIZE ONLY — reduced-size capital only."),
]

# Rule Group 1c — SNIPE_IT: no contradiction with capital authorization.
# Defense-in-depth over CAPITAL_CONTRACT["SNIPE_IT"].
_SOVEREIGN_SNIPE_RULES: list[tuple[str, str]] = [
    (r"\bno[ \t]+capital[ \t]*[—\-–][ \t]*watch[ \t]+only\b",
     "Continue monitoring live hold and expansion."),
    (r"\bno[ \t]+capital\b",
     "Continue monitoring live hold and expansion."),
    (r"\bwatch[\t\-]only\b",
     "Continue monitoring live hold and expansion."),
    (r"\bblocker[ \t]+active\b",
     "Continue monitoring live hold and expansion."),
    (r"\bmissing[ \t]+confirmation\b",
     "Continue monitoring live hold and expansion."),
    (r"\bpartial[ \t]+retest\b",
     "Continue monitoring live hold and expansion."),
    (r"\bpartial[ \t]+hold\b",
     "Continue monitoring live hold and expansion."),
]

# Rule Group 2 — Retest sovereignty (applied when retest_status != "confirmed").
# Uses [ \t]+ to prevent matching across alert section newlines.
_SOVEREIGN_RETEST_RULES: list[tuple[str, str]] = [
    (r"\bsuccessful[ \t]+retest\b",          "Retest not confirmed."),
    (r"\bretest[ \t]+defended\b",            "Retest not confirmed."),
    (r"\bdefended[ \t]+zone\b",              "Zone defense not confirmed."),
    (r"\bdemand[ \t]+defended\b",            "Zone defense not confirmed."),
    (r"\bfull[ \t]+zone[ \t]+confirmation\b", "Retest remains incomplete."),
    (r"\bconfirmed[ \t]+defense\b",          "Retest not confirmed."),
    (r"\bacceptance[ \t]+confirmed\b",       "Retest remains incomplete."),
    (r"\bstructure[ \t]+fully[ \t]+confirmed\b", "Retest remains incomplete."),
]

# Rule Group 3 — Hold sovereignty (applied when hold_status != "confirmed").
# Uses [ \t]+ to prevent matching across alert section newlines.
_SOVEREIGN_HOLD_RULES: list[tuple[str, str]] = [
    (r"\bhold[ \t]+confirmed\b",             "Hold not confirmed."),
    (r"\bconfirmed[ \t]+hold\b",             "Hold not confirmed."),
    (r"\bdefended[ \t]+hold\b",              "Hold not confirmed."),
    (r"\bcontinuation[ \t]+confirmed\b",     "Hold remains incomplete."),
    (r"\bacceptance[ \t]+confirmed\b",       "Hold remains incomplete."),
    (r"\bbuyers[ \t]+confirmed[ \t]+defense\b", "Hold not confirmed."),
]

# Rule Group 4a — Overhead blocker active (moderate + blocker note references overhead).
_SOVEREIGN_OH_BLOCKER_RULES: list[tuple[str, str]] = [
    (r"\boverhead[ \t]+(?:is[ \t]+)?(?:moderate[ \t]*[—\-–][ \t]*)?not[ \t]+block(?:ing|ed)\b",
     "Overhead remains a blocker."),
    (r"\bnot[ \t]+block(?:ing|ed)\b",        "Overhead remains a blocker."),
    (r"\bclear[ \t]+path\b",                 "Path requires reclaim through nearby resistance."),
    (r"\bclean[ \t]+path\b",                 "Path requires reclaim through nearby resistance."),
    (r"\bpath[ \t]+clear\b",                 "Path requires reclaim through nearby resistance."),
    (r"\boverhead[ \t]+clear\b",             "Overhead remains a blocker."),
]

# Rule Group 4b — Overhead blocked.
_SOVEREIGN_OH_BLOCKED_RULES: list[tuple[str, str]] = [
    (r"\bclear[ \t]+path\b",                 "Path is blocked by overhead resistance."),
    (r"\bclean[ \t]+path\b",                 "Path is blocked by overhead resistance."),
    (r"\bpath[ \t]+clear\b",                 "Path is blocked by overhead resistance."),
    (r"\boverhead[ \t]+clear\b",             "Overhead is blocked."),
    (r"\bnot[ \t]+block(?:ing|ed)\b",        "Overhead is blocked."),
]

# Rule Group 5 — Fragile risk: prohibited high-confidence language.
_SOVEREIGN_FRAGILE_RULES: list[tuple[str, str]] = [
    (r"\bclean[ \t]+asymmetry\b",            "compressed-invalidation asymmetry"),
    (r"\bpristine[ \t]+[Rr]:?[Rr]\b",        "tight R:R (compressed invalidation)"),
    (r"\bstrong[ \t]+asymmetry\b",           "R:R asymmetry (compressed invalidation)"),
    (r"\bfull[\t\-]quality[ \t]+risk\b",     "execution-sensitive risk"),
]

# Fragile caution note injected into RISK REALISM block when state == "fragile".
_FRAGILE_RISK_CAUTION = (
    "Risk is fragile; invalidation is compressed and execution is sensitive."
)

# Pre-compile all rule groups at import time.
_SOVEREIGN_NE_COMPILED      = _compile_sovereignty_rules(_SOVEREIGN_NE_RULES)
_SOVEREIGN_STARTER_COMPILED = _compile_sovereignty_rules(_SOVEREIGN_STARTER_RULES)
_SOVEREIGN_SNIPE_COMPILED   = _compile_sovereignty_rules(_SOVEREIGN_SNIPE_RULES)
_SOVEREIGN_RETEST_COMPILED  = _compile_sovereignty_rules(_SOVEREIGN_RETEST_RULES)
_SOVEREIGN_HOLD_COMPILED    = _compile_sovereignty_rules(_SOVEREIGN_HOLD_RULES)
_SOVEREIGN_OH_BLOCKER_COMPILED = _compile_sovereignty_rules(_SOVEREIGN_OH_BLOCKER_RULES)
_SOVEREIGN_OH_BLOCKED_COMPILED = _compile_sovereignty_rules(_SOVEREIGN_OH_BLOCKED_RULES)
_SOVEREIGN_FRAGILE_COMPILED = _compile_sovereignty_rules(_SOVEREIGN_FRAGILE_RULES)

_OVERHEAD_BLOCK_KEYWORDS = ("overhead", "path", "resist", "supply", "ceiling")


def _overhead_blocker_active(overhead_status: str, near_entry_blocker_note: str) -> bool:
    """True when overhead_status is moderate and the blocker note references overhead."""
    if overhead_status.lower().strip() != "moderate":
        return False
    note_lower = (near_entry_blocker_note or "").lower()
    return any(kw in note_lower for kw in _OVERHEAD_BLOCK_KEYWORDS)


def _apply_narrative_sovereignty_guard(
    final_tier: str,
    signal: dict,
    body: str,
) -> str:
    """Deterministic narrative governance — structured state is sovereign.

    Runs as the absolute final pass in format_alert() after all sanitization
    and hardening passes.  Inspects structured signal fields and removes any
    narrative contradiction with the validated state.

    Rule groups:
      1. Tier sovereignty  — NEAR_ENTRY / STARTER / SNIPE_IT
      2. Retest sovereignty — when retest_status != confirmed
      3. Hold sovereignty   — when hold_status != confirmed
      4. Overhead sovereignty — when overhead blocker active or blocked
      5. Risk sovereignty   — when risk_realism_state == fragile
      6. Final cleanup       — normalization after all replacements
    """
    if not body:
        return body

    result = body

    retest_status      = str(signal.get("retest_status", "")).lower().strip()
    hold_status        = str(signal.get("hold_status", "")).lower().strip()
    overhead_status    = str(signal.get("overhead_status", "")).lower().strip()
    risk_realism_state = str(signal.get("risk_realism_state") or "").lower().strip()
    near_entry_blocker = str(signal.get("near_entry_blocker_note") or "")

    # ---- Rule Group 1: Tier sovereignty ----
    if final_tier == "NEAR_ENTRY":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_NE_COMPILED)
    elif final_tier == "STARTER":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_STARTER_COMPILED)
    elif final_tier == "SNIPE_IT":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_SNIPE_COMPILED)

    # ---- Rule Group 2: Retest sovereignty ----
    if retest_status != "confirmed":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_RETEST_COMPILED)

    # ---- Rule Group 3: Hold sovereignty ----
    if hold_status != "confirmed":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_HOLD_COMPILED)

    # ---- Rule Group 4: Overhead sovereignty ----
    if _overhead_blocker_active(overhead_status, near_entry_blocker):
        result = _apply_sovereignty_rules(result, _SOVEREIGN_OH_BLOCKER_COMPILED)
    elif overhead_status == "blocked":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_OH_BLOCKED_COMPILED)

    # ---- Rule Group 5: Risk sovereignty ----
    if risk_realism_state == "fragile":
        result = _apply_sovereignty_rules(result, _SOVEREIGN_FRAGILE_COMPILED)
        # Inject caution note into RISK REALISM section if not already present.
        caution_markers = ("compressed", "execution sensitiv", "is fragile")
        if not any(m in result.lower() for m in caution_markers):
            fragile_line = "  Risk state:     fragile"
            if fragile_line in result:
                result = result.replace(
                    fragile_line,
                    fragile_line + f"\n  Risk note:      {_FRAGILE_RISK_CAUTION}",
                    1,
                )

    # ---- Rule Group 6: Final contradiction cleanup ----
    result = _normalize_repeated_capital_language(result)
    result = _normalize_duplicate_punctuation(result)
    result = _sanitize_diagnostic_labels(result)
    result = _humanize_bare_gate_keys(result)
    if final_tier == "NEAR_ENTRY":
        result = _clean_near_entry_dangling_tails(result)

    return result


# ---------------------------------------------------------------------------
# Phase 14E.1A: 1H alert-truth alignment.
#
# The legacy structured fields (retest_status / hold_status from the daily/4H
# tiering pass) can read "confirmed" while the dedicated 1H entry-trigger
# evidence engine — measuring actual 1H bars — proves the trigger is NOT yet
# confirmed (RETEST_IN_PROGRESS / HOLD_WEAK / 1H_TRIGGER_WEAK / WATCH_ONLY).
# When they conflict the 1H object is sovereign for trigger-PROOF wording: the
# legacy proof language is cooled to honest watch-only language.
#
# This NEVER touches capital posture, routing, tier, suppression, dedup, or the
# structured trigger/invalidation/target fields. It only neutralizes overstated
# retest/hold/quality PROOF wording. The 1H block itself is spliced in after this
# pass (via the keyword-free sentinel) and is therefore never altered here.
# ---------------------------------------------------------------------------

# Trigger states that mean the 1H has NOT proven a closed, confirmed hold.
_ONE_HOUR_INCOMPLETE_STATES = {
    "NO_1H_EVIDENCE", "APPROACHING_LOCATION", "PULLBACK_FORMING",
    "RETEST_IN_PROGRESS", "HOLD_FORMING", "FAILED_RETEST",
    "INVALID_1H_TRIGGER", "STALE_TRIGGER",
}
_ONE_HOUR_INCOMPLETE_HOLDS = {"HOLD_WEAK", "HOLD_FORMING", "HOLD_FAILED", "NONE"}
_ONE_HOUR_INCOMPLETE_SCORES = {"1H_TRIGGER_WEAK", "NO_VALID_1H_TRIGGER"}
_ONE_HOUR_INCOMPLETE_ALERTS = {
    "NO_ALERT", "WATCH_ONLY", "FORMING_TRIGGER", "FAILED_TRIGGER",
}

# Confirmed-path states/labels — proof wording stays allowed (no overcooling).
_ONE_HOUR_CONFIRMED_STATES = {"HOLD_CONFIRMED", "TRIGGER_LIVE"}
_ONE_HOUR_CONFIRMED_ALERTS = {"CONFIRMED_TRIGGER", "LIVE_TRIGGER"}

_OH_RETEST_VALUE_RE = re.compile(
    r"^([ \t]*Retest:[ \t]+)confirmed\b", re.IGNORECASE | re.MULTILINE
)
_OH_HOLD_VALUE_RE = re.compile(
    r"^([ \t]*Hold:[ \t]+)confirmed\b", re.IGNORECASE | re.MULTILINE
)
_OH_QUALITY_LINE_RE = re.compile(
    r"^([ \t]*Quality read:[ \t]*).*$", re.MULTILINE
)
_OH_CONFIRMED_SEQUENCE_RE = re.compile(
    r"\bconfirmed[ \t]+sequence[ \t]+and[ \t]+hold\b", re.IGNORECASE
)
_OH_APLUS_SETUP_RE = re.compile(r"\bA\+[ \t]+setup\b", re.IGNORECASE)
_OH_NEAR_READY_RE = re.compile(r"\bnear[\t\- ]ready\b", re.IGNORECASE)

_OH_WATCH_ONLY_QUALITY = (
    "Watch-only valid — structure exists, but 1H trigger proof remains incomplete."
)
_OH_PROOF_LINE = (
    "  1H proof: 1H evidence has not confirmed a closed hold."
)


def _one_hour_proof_incomplete(one_hour) -> bool:
    """True when the 1H evidence object proves the trigger is NOT yet confirmed.

    Returns False when the object is missing/disabled (legacy wording preserved)
    or when the 1H genuinely confirms (HOLD_CONFIRMED/TRIGGER_LIVE with a
    confirmed/live alert label) — so confirmed wording is never overcooled.
    """
    if not isinstance(one_hour, dict):
        return False
    status = str(one_hour.get("status", "DISABLED")).upper()
    if status == "DISABLED":
        return False

    state = str(one_hour.get("trigger_state", "")).upper()
    hold = str((one_hour.get("pullback_retest_hold") or {}).get("hold_truth", "")).upper()
    score_label = str(one_hour.get("score_label", "")).upper()
    alert_label = str(one_hour.get("alert_truth_label", "")).upper()

    # Genuine confirmation — never cool.
    if (
        state in _ONE_HOUR_CONFIRMED_STATES
        and hold == "HOLD_CONFIRMED"
        and alert_label in _ONE_HOUR_CONFIRMED_ALERTS
    ):
        return False

    return (
        state in _ONE_HOUR_INCOMPLETE_STATES
        or hold in _ONE_HOUR_INCOMPLETE_HOLDS
        or score_label in _ONE_HOUR_INCOMPLETE_SCORES
        or alert_label in _ONE_HOUR_INCOMPLETE_ALERTS
    )


def _apply_one_hour_truth_alignment_guard(body: str, one_hour) -> str:
    """Cool legacy retest/hold/quality PROOF wording when the 1H object — the
    sovereign trigger-proof source — has not confirmed a closed hold.

    Display-only. Never touches capital, routing, tier, suppression, dedup, or
    the structured trigger/invalidation/target fields. Runs before the 1H block
    is spliced in, so the structured evidence block is never altered.
    """
    if not body or not _one_hour_proof_incomplete(one_hour):
        return body

    result = body
    # EXECUTION retest/hold values: an overstated "confirmed" is cooled to the
    # honest 1H read. Partial / missing values are already honest — left as-is.
    result = _OH_RETEST_VALUE_RE.sub(r"\1in progress", result)
    result = _OH_HOLD_VALUE_RE.sub(r"\1weak", result)

    # Quality read line: replace the whole value so A+/elite/near-ready/
    # "confirmed sequence and hold" prestige language cannot overstate 1H proof.
    result = _OH_QUALITY_LINE_RE.sub(r"\g<1>" + _OH_WATCH_ONLY_QUALITY, result)

    # Defense-in-depth: neutralize the same proof phrases anywhere else in prose.
    result = _OH_CONFIRMED_SEQUENCE_RE.sub(
        "structure present; 1H hold not yet confirmed", result
    )
    result = _OH_APLUS_SETUP_RE.sub("Watch-only valid setup", result)
    result = _OH_NEAR_READY_RE.sub("watch-only", result)

    # Add an explicit one-line 1H proof note in the ACTION section (right after
    # the cooled Quality read line) so the incomplete-proof reason is visible.
    if "1H proof: 1H evidence has not confirmed" not in result:
        result = _OH_QUALITY_LINE_RE.sub(
            lambda m: m.group(0) + "\n" + _OH_PROOF_LINE, result, count=1
        )

    return result


# ---------------------------------------------------------------------------
# Phase 14G: Alert posture compression — STARTER / NEAR_ENTRY language truth.
#
# Text-only. Compresses contradictory / duplicated posture wording so the alert
# reads decisively. Never mutates tier, capital, routing, suppression, dedup,
# or any structured field. Runs after the narrative + 1H-truth guards and before
# the structured 1H / TF blocks are spliced in, so those blocks are untouched.
#
# STARTER law:  a STARTER is reduced-size capital, not watch-only. When 1H proof
#   is still pending the cooled "Watch-only valid …" quality read contradicts the
#   STARTER posture; it is replaced with decisive reduced-size language while
#   add / full-size remains blocked on 1H closed-hold proof.
# NEAR_ENTRY law: keep NO CAPITAL / watch-only, but never duplicate the blocker
#   into the missing-conditions line ("Missing conditions: Blocker: …").
# ---------------------------------------------------------------------------

_STARTER_PENDING_QUALITY = (
    "Starter valid — reduced-size only; add/full-size waits for 1H closed-hold proof."
)

_QUALITY_READ_LINE_RE = re.compile(
    r"^([ \t]*Quality read:[ \t]*).*$", re.MULTILINE
)
_ONE_HOUR_PROOF_LINE_RE = re.compile(
    r"^[ \t]*1H proof: 1H evidence has not confirmed a closed hold\.[ \t]*\n",
    re.MULTILINE,
)
_NE_MISSING_CONDITIONS_LINE_RE = re.compile(
    r"^Missing conditions:[ \t]*(.*)$", re.MULTILINE
)
_NE_BLOCKER_LINE_RE = re.compile(r"^Blocker:[ \t]*(.*)$", re.MULTILINE)
_LEADING_BLOCKER_PREFIX_RE = re.compile(r"^Blocker:[ \t]*", re.IGNORECASE)


def _apply_starter_posture_compression(
    body: str, final_tier: str, capital_action: str
) -> str:
    """Replace contradictory watch-only quality wording in a STARTER alert with
    decisive reduced-size posture. Add / full-size stays blocked on 1H proof.

    Gated on the presence of the cooled "Watch-only valid" leak, which only
    surfaces in a STARTER body when 1H trigger proof is pending. STARTER policy
    permits reduced-size capital, so watch-only / no-capital wording must never
    leak in. "no add" / "no full-size" wording is intentionally preserved.
    """
    if str(final_tier).upper() != "STARTER" or str(capital_action).lower() != "starter_only":
        return body
    if "watch-only valid" not in body.lower():
        return body

    result = body
    # Decisive STARTER quality read.
    result = _QUALITY_READ_LINE_RE.sub(r"\g<1>" + _STARTER_PENDING_QUALITY, result)
    # The new quality read already states the add/full-size proof requirement —
    # drop the now-redundant cooled 1H-proof narrative line (compression).
    result = _ONE_HOUR_PROOF_LINE_RE.sub("", result)
    # Defense-in-depth: no residual watch-only phrasing may remain in a STARTER.
    result = re.sub(r"Watch-only valid", "Starter valid", result)
    result = re.sub(r"\bwatch-only\b", "reduced-size starter", result, flags=re.IGNORECASE)
    return result


# ---------------------------------------------------------------------------
# Phase 14Q: STARTER truth-headline guard.
#
# A static "STARTER conditions met." ACTION headline overstates a STARTER whose
# 1H trigger proof is still forming (RETEST_IN_PROGRESS / HOLD_WEAK / WATCH_ONLY
# / candle unresolved). When the 1H object proves the trigger is NOT confirmed,
# the headline is rewritten to a thesis-only truth: the structure/thesis remains
# valid but fresh entry proof is incomplete, so no fresh aggression is implied.
#
# Display-only. Never touches tier, capital, routing, suppression, dedup, or the
# structured fields. Gated on _one_hour_proof_incomplete, so a STARTER whose base
# sequence genuinely confirms keeps the standard headline.
# ---------------------------------------------------------------------------

_STARTER_THESIS_HEADLINE = (
    "STARTER thesis valid — structure holds, but fresh 1H trigger proof is "
    "incomplete; no fresh aggression until closed 1H hold."
)
_STARTER_CONDITIONS_MET_LINE_RE = re.compile(
    r"^([ \t]*)STARTER conditions met\.[ \t]*$", re.MULTILINE
)
_STARTER_ENTRY_VALID_NOW_RE = re.compile(
    r"\bentry valid (?:now|near current[\w \t]*)\b", re.IGNORECASE
)


def _apply_starter_truth_headline_guard(body: str, final_tier: str, one_hour) -> str:
    """Cool an overstated STARTER headline when the 1H trigger proof is forming.

    Replaces 'STARTER conditions met.' with thesis-only truth wording and
    neutralizes any 'entry valid now / near current' fresh-entry implication.
    Runs after posture compression so the corrected headline survives to output.
    """
    if str(final_tier).upper() != "STARTER":
        return body
    if not _one_hour_proof_incomplete(one_hour):
        return body
    result = _STARTER_CONDITIONS_MET_LINE_RE.sub(r"\1" + _STARTER_THESIS_HEADLINE, body)
    # Inline occurrences too (e.g. a contract-guard-rewritten "Why:" line) — the
    # phrase may not claim completion anywhere while the 1H trigger is forming.
    result = re.sub(r"STARTER conditions met\b\.?",
                    "STARTER thesis valid — trigger proof incomplete.",
                    result, flags=re.IGNORECASE)
    result = _STARTER_ENTRY_VALID_NOW_RE.sub("setup on watch (reduced-size thesis only)", result)
    return result


def _apply_confirmed_base_starter_headline_guard(body: str, final_tier: str, tiering_result) -> str:
    """Phase 14Q — a STARTER sealed down from SNIPE_IT with a CONFIRMED base
    sequence (entry-zone retest/hold proven; only full-size/SNIPE proof missing)
    must say so, naming the exact SNIPE-only blocker, instead of the generic
    'STARTER conditions met.'.

    Gated on the seal marker (applied + sealed_tier STARTER), which only exists
    when the Phase 14M/14Q seal acted — legacy STARTER alerts are untouched.
    Display-only; never touches tier, capital, routing, or structured fields.
    """
    if str(final_tier).upper() != "STARTER" or not isinstance(tiering_result, dict):
        return body
    seal = tiering_result.get("snipe_confirmed_seal")
    if not isinstance(seal, dict) or seal.get("applied") is not True:
        return body
    if str(seal.get("sealed_tier") or "").upper() != "STARTER":
        return body
    recon = tiering_result.get("snipe_promotion_reconciliation")
    recon = recon if isinstance(recon, dict) else {}
    if not recon.get("base_sequence_confirmed"):
        return body
    codes = [
        b.get("code") for b in (recon.get("snipe_only_blockers") or [])
        if isinstance(b, dict) and b.get("code")
    ]
    blocked_by = " / ".join(codes) if codes else "full-size confirmation proof"
    headline = (
        f"Confirmed-base STARTER — base retest/hold valid; "
        f"full-size/SNIPE blocked by {blocked_by}."
    )
    return _STARTER_CONDITIONS_MET_LINE_RE.sub(r"\1" + headline, body)


def _apply_near_entry_missing_proof_compression(body: str, final_tier: str) -> str:
    """Compress duplicated blocker / missing-condition wording in a NEAR_ENTRY
    alert. Only the duplicate pattern is touched — a clean "Missing conditions:"
    line (a humanized list distinct from the blocker) is left intact.

    Transforms:
      "Missing conditions: Blocker: <X>"  ->  "Missing proof: <X>"
    and, when the missing-proof content duplicates the Blocker line, collapses it
    to "Missing proof: closed hold confirmation." Never removes the blocker,
    upgrade trigger, invalidation, or NO CAPITAL lines.
    """
    if str(final_tier).upper() != "NEAR_ENTRY":
        return body

    bm = _NE_BLOCKER_LINE_RE.search(body)
    blocker_text = bm.group(1).strip() if bm else ""

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", str(s).strip().rstrip(". ").lower())

    def _line_repl(m: re.Match) -> str:
        content = m.group(1).strip()
        deduped = _LEADING_BLOCKER_PREFIX_RE.sub("", content).strip()
        is_blocker_prefixed = bool(_LEADING_BLOCKER_PREFIX_RE.match(content))
        is_dup = bool(blocker_text) and _norm(deduped) == _norm(blocker_text)
        if not (is_blocker_prefixed or is_dup):
            return m.group(0)            # clean line — leave untouched
        if is_dup:
            deduped = "closed hold confirmation."
        return "Missing proof: " + deduped

    return _NE_MISSING_CONDITIONS_LINE_RE.sub(_line_repl, body)


# ---------------------------------------------------------------------------
# Phase 13.8B: Structural Quality Hierarchy — five-dimension quality layer.
#
# Replaces the Phase 13.8A binary-gate model with five three-state dimensions
# drawn exclusively from existing signal fields.  Each dimension grades as
# premium / standard / discount.  Dimension counts drive label assignment.
#
# Adds A_PLUS_ELITE (all five dimensions institutional-grade) to discriminate
# genuine elite setups from technically-valid-but-marginal A+ passes.
#
# Labels are purely presentational.  They do NOT affect tier, capital_action,
# discord_channel, suppression logic, or any hard-veto gate.  Display only.
# ---------------------------------------------------------------------------

# Short canonical prefixes for the top three labels — used as the dict values
# so existing `_QUALITY_LABEL_PHRASES["X"] in result` assertions remain valid
# while _build_quality_phrase() generates fuller dynamic text.
# Lower three labels keep their full static phrases (unchanged from 13.8A).
_QUALITY_LABEL_PHRASES: dict[str, str] = {
    "A_PLUS_ELITE":   "Elite candidate",
    "A_PLUS_CANDIDATE": "A+ candidate",
    "CLEAN_STARTER":  "Clean starter",
    "WATCH_ONLY_VALID": (
        "Watch-only valid — structure exists, but retest and hold are incomplete."
    ),
    "STRUCTURALLY_VALID_BUT_IMPERFECT": (
        "Structurally valid — conditions incomplete; wait for further development."
    ),
    "LOW_PRIORITY_VALID": (
        "Low-priority valid — setup exists but lacks multiple confirmation layers."
    ),
}


def _evaluate_quality_dimensions(signal: dict) -> tuple[int, int]:
    """Score the five structural quality dimensions.  Returns (n_premium, n_discount).

    Dimensions:
      1. Structural freshness  — trend_state
      2. Sequence quality      — structure_event + setup_family pair
      3. Zone precision        — zone_type
      4. Path openness         — overhead_status (+ active blocker check)
      5. Risk profile          — risk_realism_state + risk_reward

    SMA hostility is applied as a supplemental discount point after dimension
    scoring, preserving Phase 13.8A's A+/hostile-SMA boundary.

    Informational only — never touches tier, capital_action, or routing.
    """
    trend_state        = str(signal.get("trend_state", "") or "").lower().strip()
    structure_event    = str(signal.get("structure_event", "none") or "none").lower().strip()
    setup_family       = str(signal.get("setup_family", "none") or "none").lower().strip()
    zone_type          = str(signal.get("zone_type", "none") or "none").lower().strip()
    overhead_status    = str(signal.get("overhead_status", "unknown") or "unknown").lower().strip()
    near_entry_blocker = str(signal.get("near_entry_blocker_note") or "")
    risk_realism_state = str(signal.get("risk_realism_state") or "unknown").lower().strip()
    sma_alignment      = str(signal.get("sma_value_alignment", "unavailable") or "unavailable").lower().strip()

    rr: float | None = None
    try:
        raw_rr = signal.get("risk_reward")
        if raw_rr is not None:
            rr = float(raw_rr)
    except (TypeError, ValueError):
        pass

    grades: list[str] = []

    # ---- Dimension 1: Structural freshness ----
    if trend_state in ("fresh_expansion", "basing"):
        grades.append("premium")
    elif trend_state in ("mature_continuation", "transition"):
        grades.append("standard")
    else:                                               # repair, failure, unknown, empty
        grades.append("discount")

    # ---- Dimension 2: Sequence quality ----
    _premium_seq_families = ("continuation", "accepted_break", "compression_to_expansion")
    _discount_seq_families = ("reversal", "exhaustion_trap")
    if structure_event == "bos" and setup_family in _premium_seq_families:
        grades.append("premium")
    elif structure_event == "bos":
        grades.append("standard")
    elif structure_event == "choch" or setup_family in _discount_seq_families:
        grades.append("discount")
    elif structure_event == "none" or setup_family == "none":
        grades.append("discount")
    elif structure_event in ("mss", "reclaim", "accepted_break", "failed_breakdown_reclaim"):
        grades.append("standard")
    elif setup_family in ("reclaim", "failed_breakdown_reclaim"):
        grades.append("standard")
    else:
        grades.append("standard")

    # ---- Dimension 3: Zone precision ----
    if zone_type in ("ob", "fvg"):
        grades.append("premium")
    elif zone_type in ("demand", "flip_zone"):
        grades.append("standard")
    else:                                               # support_cluster, none, unknown
        grades.append("discount")

    # ---- Dimension 4: Path openness ----
    overhead_blocker_active = _overhead_blocker_active(overhead_status, near_entry_blocker)
    if overhead_status == "clear" and not overhead_blocker_active:
        grades.append("premium")
    elif overhead_status == "moderate" and not overhead_blocker_active:
        grades.append("standard")
    else:                                               # blocked, unknown, or blocker active
        grades.append("discount")

    # ---- Dimension 5: Risk profile ----
    if risk_realism_state == "healthy" and rr is not None and rr >= 4.0:
        grades.append("premium")
    elif risk_realism_state == "healthy" or (
        risk_realism_state == "tight" and rr is not None and rr >= 3.5
    ):
        grades.append("standard")
    else:                                               # fragile, invalid, unknown, tight<3.5
        grades.append("discount")

    n_premium  = grades.count("premium")
    n_discount = grades.count("discount")

    # SMA hostility: applied as a supplemental discount (not a dimension slot).
    if sma_alignment == "hostile":
        n_discount += 1

    return n_premium, n_discount


def _build_quality_phrase(label: str, signal: dict, final_tier: str = "") -> str:
    """Build the human-readable quality phrase for the ACTION section.

    Top three labels get dynamic phrases that name dimension counts.
    Lower three labels return their full static phrases (unchanged from 13.8A).

    Phase 13.8C: When final_tier == NEAR_ENTRY and both retest+hold are confirmed,
    the phrase names the remaining blocker from missing_conditions so the quality
    read does not contradict the "NO CAPITAL" directive without explanation.

    Informational only — no side effects on tier, capital, or routing.
    """
    n_premium, _n_discount = _evaluate_quality_dimensions(signal)

    # Phase 13.8C Fix 3: NEAR_ENTRY + both_confirmed — quality phrase must name the
    # remaining blocker, not claim the setup is fully ready (which contradicts NE tier).
    if final_tier == "NEAR_ENTRY" and label in ("A_PLUS_ELITE", "A_PLUS_CANDIDATE", "CLEAN_STARTER"):
        missing = signal.get("missing_conditions") or []
        if missing:
            blocker = "; ".join(_humanize_missing_condition(str(m)) for m in missing[:2])
            if label == "A_PLUS_ELITE":
                return f"Elite setup — confirmed sequence and hold; pending: {blocker}."
            if label == "A_PLUS_CANDIDATE":
                return (
                    f"A+ setup — {n_premium} of 5 dimensions premium, "
                    f"confirmed sequence and hold; pending: {blocker}."
                )
            # CLEAN_STARTER
            premium_note = (
                "quality factors mixed" if n_premium == 0
                else f"{n_premium} of 5 quality factors premium"
            )
            return f"Near-ready — confirmed sequence and hold, {premium_note}; pending: {blocker}."
        else:
            # No missing_conditions listed — generic near-ready phrasing
            if label == "A_PLUS_ELITE":
                return "Elite setup — confirmed sequence and hold; near-ready pending blocker resolution."
            if label == "A_PLUS_CANDIDATE":
                return (
                    f"A+ setup — {n_premium} of 5 dimensions premium, "
                    "confirmed sequence and hold; near-ready pending blocker resolution."
                )
            premium_note = (
                "quality factors mixed" if n_premium == 0
                else f"{n_premium} of 5 quality factors premium"
            )
            return f"Near-ready — confirmed sequence and hold, {premium_note}; pending blocker resolution."

    if final_tier == "STARTER" and label in ("A_PLUS_ELITE", "A_PLUS_CANDIDATE", "CLEAN_STARTER"):
        # Phase 14C.2: STARTER quality heat control. A STARTER is never an elite
        # full-size grant; the label names the tier and states the capital limit
        # plainly so prestige language can never outrun the tier contract.
        return (
            "High-quality STARTER — structure and hold confirmed; "
            "full-size confirmation not granted."
        )

    if label == "A_PLUS_ELITE":
        return "Elite candidate — all five quality dimensions institutional-grade."
    if label == "A_PLUS_CANDIDATE":
        return (
            f"A+ candidate — {n_premium} of 5 dimensions premium, "
            "confirmed sequence and hold."
        )
    if label == "CLEAN_STARTER":
        # Phase 13.8C Fix 2: "0 of 5 quality factors premium" reads poorly —
        # replace with "quality factors mixed" when no dimensions are premium.
        if n_premium == 0:
            return "Clean starter — retest and hold confirmed; quality factors mixed."
        return (
            f"Clean starter — retest and hold confirmed, "
            f"{n_premium} of 5 quality factors premium."
        )
    return _QUALITY_LABEL_PHRASES.get(label, label)


def _evaluate_setup_quality(signal: dict, final_tier: str) -> str:
    """Evaluate setup quality and return a compact internal quality label.

    Phase 13.8B — five-dimension structural hierarchy:

      A_PLUS_ELITE                 — both confirmed; all 5 dimensions premium, 0 discounts
      A_PLUS_CANDIDATE             — both confirmed; ≥ 3 premium dimensions, 0 discounts
      CLEAN_STARTER                — both confirmed; any dimension profile
      WATCH_ONLY_VALID             — structure present, at least partial retest/hold progress
      STRUCTURALLY_VALID_BUT_IMPERFECT — structure present, no partial progress
      LOW_PRIORITY_VALID           — catch-all (no structure or no alertable progress)

    Informational only.  Never changes tier, capital_action, discord_channel,
    suppression logic, or any hard-veto gate.
    """
    retest_status  = str(signal.get("retest_status", "missing")).lower().strip()
    hold_status    = str(signal.get("hold_status",   "missing")).lower().strip()
    structure_event = str(signal.get("structure_event", "none")).lower().strip()

    both_confirmed    = retest_status == "confirmed" and hold_status == "confirmed"
    structure_present = structure_event != "none"
    has_partial_progress = (
        retest_status in ("partial", "confirmed")
        or hold_status in ("partial", "confirmed")
    )

    if both_confirmed:
        n_premium, n_discount = _evaluate_quality_dimensions(signal)
        # A_PLUS_ELITE: all five dimensions premium, zero discounts (including SMA)
        if n_premium == 5 and n_discount == 0:
            return "A_PLUS_ELITE"
        # A_PLUS_CANDIDATE: at least three premium, strictly zero discounts
        if n_premium >= 3 and n_discount == 0:
            return "A_PLUS_CANDIDATE"
        # CLEAN_STARTER: both gates confirmed; one or more dimension imperfections
        return "CLEAN_STARTER"

    # ---- Below here: at least one of retest/hold is NOT confirmed ----

    if structure_present and has_partial_progress:
        return "WATCH_ONLY_VALID"

    if structure_present:
        return "STRUCTURALLY_VALID_BUT_IMPERFECT"

    return "LOW_PRIORITY_VALID"


# ---------------------------------------------------------------------------
# Phase 13.7B: Context-aware overhead label
# ---------------------------------------------------------------------------

def _render_overhead_label(
    overhead_status: str,
    final_tier: str,
    near_entry_blocker_note: str | None = None,
) -> str:
    """Return a display-ready overhead label (without the 'Overhead:' prefix).

    Rules:
    - clear   → "clear"
    - blocked → "blocked"
    - moderate + SNIPE_IT/STARTER → "moderate — not blocking"
      (passing these tiers means overhead was not a veto)
    - moderate + NEAR_ENTRY + overhead keyword in blocker note
              → "moderate — blocker active"
    - moderate + NEAR_ENTRY, no overhead keyword → "moderate — not blocking"
    - unknown/other → pass through raw value
    """
    s = (overhead_status or "").lower().strip()
    if s == "clear":
        return "clear"
    if s == "blocked":
        return "blocked"
    if s == "moderate":
        if final_tier in ("SNIPE_IT", "STARTER"):
            return "moderate — not blocking"
        if final_tier == "NEAR_ENTRY":
            note_lower = (near_entry_blocker_note or "").lower()
            overhead_keywords = ("overhead", "path", "resist", "supply", "ceiling")
            if any(kw in note_lower for kw in overhead_keywords):
                return "moderate — blocker active"
            return "moderate — not blocking"
        return "moderate — not blocking"
    # Pass through unknown/other values (e.g. "unknown", "—")
    return overhead_status if overhead_status else "—"


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _fmt_level(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_targets(targets) -> str:
    if not isinstance(targets, list) or not targets:
        return "  —"
    lines = []
    for t in targets:
        if isinstance(t, dict):
            label = t.get("label", "")
            level = _fmt_level(t.get("level"))
            reason = _sanitize(str(t.get("reason", "")))
            lines.append(f"  {label}: {level}  ({reason})")
        else:
            lines.append(f"  {_sanitize(str(t))}")
    return "\n".join(lines)


def format_alert(
    tiering_result: dict,
    dedup_decision: dict | None = None,
    scan_id: str = "",
    config: dict | None = None,
) -> str:
    """Build plain-text alert message from validated tiering_result fields only.

    Phase 14H: an optional compact SNIPE-audit line is rendered only when
    config["snipe_gate_audit"]["render_compact_line"] is true. Default off — no
    line is added when config is None (every existing caller is unaffected).
    """
    final_tier   = tiering_result.get("final_tier", "WAIT")
    score        = tiering_result.get("score", 0)
    signal       = tiering_result.get("final_signal") or {}

    ticker           = _sanitize(str(signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")))
    setup_family     = _sanitize(str(signal.get("setup_family", "—")))
    structure_event  = _sanitize(str(signal.get("structure_event", "—")))
    trend_state      = _sanitize(str(signal.get("trend_state", "—")))
    zone_type        = _sanitize(str(signal.get("zone_type", "—")))

    trigger_level      = signal.get("trigger_level")
    retest_status      = _sanitize(str(signal.get("retest_status", "—")))
    hold_status        = _sanitize(str(signal.get("hold_status", "—")))
    inval_condition    = _sanitize(str(signal.get("invalidation_condition", "—")))
    inval_level        = signal.get("invalidation_level")
    risk_reward        = signal.get("risk_reward")
    overhead_status    = str(signal.get("overhead_status", "—"))
    forced_part        = _sanitize(str(signal.get("forced_participation", "none")))
    next_action        = _sanitize(str(signal.get("sanitized_next_action") or signal.get("next_action", "—")))
    capital_action     = signal.get("capital_action", "no_trade")
    # Phase 12A: use sanitized_reason if present; fall back to raw reason
    reason             = _sanitize(str(signal.get("sanitized_reason") or signal.get("reason", "—")))
    missing_conditions = signal.get("missing_conditions") or []
    # Phase 13.7D: humanize upgrade trigger before sanitization
    _upgrade_trigger_raw = str(signal.get("upgrade_trigger", "—"))
    _upgrade_trigger_hum = _humanize_upgrade_trigger(_upgrade_trigger_raw, final_tier)
    _upgrade_trigger_hum = _humanize_bare_gate_keys(_upgrade_trigger_hum)
    if final_tier == "NEAR_ENTRY":
        _upgrade_trigger_hum = _seal_near_entry_classification_language(_upgrade_trigger_hum)
    upgrade_trigger    = _sanitize(_upgrade_trigger_hum)

    # Phase 13.7F: strip residual internal diagnostic labels from prose fields
    # (all tiers).  Runs before the 13.7E/13.7G passes so all operate on
    # already-cleaned inputs.
    reason      = _sanitize_diagnostic_labels(reason)
    next_action = _sanitize_diagnostic_labels(next_action)

    # Phase 13.7G: humanize bare gate keys in prose fields (all tiers).
    reason      = _humanize_bare_gate_keys(reason)
    next_action = _humanize_bare_gate_keys(next_action)

    # Phase 14C.2: boolean/debug-fragment firewall (all tiers). Runs after the
    # gate-key humanizer so it also repairs the "...zone=True" half-humanized
    # leak. Display-only — no decision field is read or written.
    reason      = _sanitize_boolean_debug_fragments(reason)
    next_action = _sanitize_boolean_debug_fragments(next_action)

    # Phase 14C.2: trail-stop safety (all tiers). A trail stop below the
    # invalidation widens risk and is relabelled a deep-failure reference.
    reason      = _sanitize_trail_stop_language(reason, signal.get("invalidation_level"))
    next_action = _sanitize_trail_stop_language(next_action, signal.get("invalidation_level"))

    # Phase 13.7E: field-level upgrade-language neutralization for NEAR_ENTRY.
    # Applied before rendering so structural label prefixes are not consumed by
    # the sentence-level regex.
    if final_tier == "NEAR_ENTRY":
        reason      = _neutralize_near_entry_upgrade_language(reason)
        next_action = _neutralize_near_entry_upgrade_language(next_action)
        # Phase 13.7G: seal tier-mechanics classification language (NEAR_ENTRY only).
        reason      = _seal_near_entry_classification_language(reason)
        next_action = _seal_near_entry_classification_language(next_action)
        # Phase 13.8C Fix 4: when retest AND hold are both already confirmed, entry-intent
        # language in next_action ("enter on retest", "enter on confirmation") is
        # factually wrong and the sovereignty guard would corrupt it into
        # "wait for confirmation retest" — a visible contradiction.
        # Pre-substitute to watch language before the body-level guard fires.
        _retest_s   = str(signal.get("retest_status", "")).lower().strip()
        _hold_s     = str(signal.get("hold_status",   "")).lower().strip()
        if _retest_s == "confirmed" and _hold_s == "confirmed":
            next_action = re.sub(
                r"\benter\s+on\s+retest(?:\s+of\s+(?:the\s+)?zone)?\b",
                "monitor for blocker resolution",
                next_action,
                flags=re.IGNORECASE,
            )
            next_action = re.sub(
                r"\benter\s+on\s+confirmation\b",
                "monitor for blocker resolution",
                next_action,
                flags=re.IGNORECASE,
            )
            next_action = re.sub(
                r"\benter\s+on\b",
                "monitor for blocker resolution",
                next_action,
                flags=re.IGNORECASE,
            )
    targets            = signal.get("targets", [])

    # Phase 11: freshness fields (snapshot_only in current architecture)
    scan_price      = signal.get("scan_price")
    drift_status    = _sanitize(str(signal.get("drift_status", "unknown")))
    drift_pct_raw   = signal.get("drift_pct", 0.0)
    freshness_note  = _sanitize(str(signal.get("freshness_note", "")))

    # Phase 12C/D: risk realism informational fields. Display only — not gating.
    risk_distance        = signal.get("risk_distance")
    risk_distance_pct    = signal.get("risk_distance_pct")
    cp_to_inval          = signal.get("current_price_to_invalidation")
    cp_to_inval_pct      = signal.get("current_price_to_invalidation_pct")
    risk_realism_state   = signal.get("risk_realism_state")
    risk_realism_note_raw = signal.get("risk_realism_note")
    risk_realism_note    = _sanitize(str(risk_realism_note_raw)) if risk_realism_note_raw else ""

    badge = _TIER_BADGE.get(final_tier, final_tier)
    rr_str = f"{float(risk_reward):.2f}" if risk_reward is not None else "—"

    # Phase 13.7B: ACTION section driven by CAPITAL_CONTRACT, not raw Claude fields.
    # capital_label kept for WAIT fallback only.
    contract = CAPITAL_CONTRACT.get(final_tier)
    if contract:
        action_headline = contract["headline"]
        sizing_line     = contract["sizing"]
    else:
        action_headline = _TIER_ACTION_LABEL.get(final_tier, f"Tier: {final_tier}")
        sizing_line     = _CAPITAL_LABEL.get(capital_action, capital_action)

    # Phase 13.7B: context-aware overhead label
    raw_blocker_str = str(signal.get("near_entry_blocker_note") or "")
    overhead_label = _render_overhead_label(overhead_status, final_tier, raw_blocker_str)

    # Phase 14C.2: zone boundaries needed for the deep-failure EXECUTION line
    # (extracted early so the line can be appended immediately after Overhead).
    _tl_ctx_pre   = tiering_result.get("trade_location") or {}
    _tl_zone_low  = _tl_ctx_pre.get("zone_low")
    _tl_zone_type = str(_tl_ctx_pre.get("zone_type") or "").upper()

    # Phase 14C.3B: extract candle evidence early — needed for NEAR_ENTRY
    # synthesis (Defect 1), proof-line harmonization (Defect 5), capital
    # posture (Defect 3), and completion-language neutralization (Defect 2).
    _candle         = tiering_result.get("candle_evidence") or {}
    _candle_display = str(_candle.get("display_text", "")).strip()
    _candle_family  = str(_candle.get("candle_family", "UNKNOWN"))
    _candle_veto    = str(_candle.get("candle_veto", "NONE")).strip().upper()
    _has_candle_gap = _has_candle_confirmation_gap(_candle)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{badge} | {ticker} | Score: {score}",
        f"Setup: {setup_family}  |  Structure: {structure_event}",
        f"Trend: {trend_state}  |  Zone: {zone_type}",
        "──────────────────────────────",
        "EXECUTION",
        f"  Trigger:      {_fmt_level(trigger_level)}",
        f"  Retest:       {retest_status}",
        f"  Hold:         {hold_status}",
        f"  Invalidation: {inval_condition} @ {_fmt_level(inval_level)}",
        f"  R:R:          {rr_str}",
        f"  Overhead:     {overhead_label}",
    ]

    # Phase 14C.2: invalidation clarity. When the structural zone floor sits
    # below the risk invalidation, name the deep zone-failure level on its own
    # line so the risk stop and the deep-failure level are never conflated.
    try:
        _inval_f = float(inval_level) if inval_level is not None else None
        _zlow_f  = float(_tl_zone_low) if _tl_zone_low is not None else None
    except (TypeError, ValueError):
        _inval_f = _zlow_f = None
    if (
        _inval_f is not None and _zlow_f is not None
        and round(_zlow_f, 2) < round(_inval_f, 2)
    ):
        _zlabel = _tl_zone_type if _tl_zone_type in ("FVG", "OB") else "zone"
        lines.append(f"  Deep {_zlabel} failure: {_fmt_level(_zlow_f)}  (below risk invalidation)")

    # Phase 12D: RISK REALISM block — only emit lines for non-None values so
    # alerts never display "None". State and note are always displayed when
    # populated by tiering (Phase 12C fills them deterministically).
    risk_lines: list[str] = []
    if risk_distance is not None and risk_distance_pct is not None:
        risk_lines.append(
            f"  Risk window:    ${float(risk_distance):.2f} / {float(risk_distance_pct):.2f}%"
        )
    elif risk_distance is not None:
        risk_lines.append(f"  Risk window:    ${float(risk_distance):.2f}")
    elif risk_distance_pct is not None:
        risk_lines.append(f"  Risk window:    {float(risk_distance_pct):.2f}%")

    if cp_to_inval is not None and cp_to_inval_pct is not None:
        risk_lines.append(
            f"  Price → inval:  ${float(cp_to_inval):.2f} / {float(cp_to_inval_pct):.2f}%"
        )
    elif cp_to_inval is not None:
        risk_lines.append(f"  Price → inval:  ${float(cp_to_inval):.2f}")
    elif cp_to_inval_pct is not None:
        risk_lines.append(f"  Price → inval:  {float(cp_to_inval_pct):.2f}%")

    if risk_realism_state:
        risk_lines.append(f"  Risk state:     {risk_realism_state}")
    if risk_realism_note:
        risk_lines.append(f"  Risk note:      {risk_realism_note}")

    if risk_lines:
        lines += [
            "──────────────────────────────",
            "RISK REALISM",
        ] + risk_lines

    lines += [
        "──────────────────────────────",
        "TARGETS",
        _fmt_targets(targets),
    ]

    # Phase 12.1: NEAR_ENTRY never displays forced participation — no capital context
    if final_tier != "NEAR_ENTRY" and forced_part and forced_part.lower() not in ("none", "—", ""):
        lines += ["──────────────────────────────", f"FORCED PARTICIPATION: {forced_part}"]

    if final_tier == "NEAR_ENTRY":
        # Phase 13.7G: parse, humanize (gate keys + condition map), format.
        _mc_tokens = _parse_missing_conditions(missing_conditions)
        _mc_human = [
            _humanize_bare_gate_keys(_sanitize(_humanize_missing_condition(tok)))
            for tok in _mc_tokens
        ]
        missing_str = _format_missing_conditions(_mc_human) if _mc_human else "—"
        # Phase 14C.3B Defect 1: never render blank missing-condition when
        # useful context exists (blocker, retest, hold, zone defense, candle).
        if _is_blank_alert_field(missing_str):
            missing_str = _derive_missing_conditions(
                signal, _candle, _tl_ctx_pre, raw_blocker_str
            )
        # Phase 12.3: render blocker note above missing conditions.
        # Phase 12.3A: strip leading "Blocker:" prefix before adding our label
        # so _build_near_entry_blocker_note's prefix does not double up.
        # Phase 13.7D/13.7G: strip raw field-label prefixes; humanize gate keys;
        # seal tier-mechanics classification language.
        _blocker_cleaned = _humanize_blocker_note(_clean_blocker_label(raw_blocker_str))
        _blocker_cleaned = _humanize_bare_gate_keys(_blocker_cleaned)
        _blocker_cleaned = _seal_near_entry_classification_language(_blocker_cleaned)
        blocker_note = _sanitize(_blocker_cleaned)
        # Phase 14C.3B Defect 1: synthesize upgrade trigger when blank/none.
        _upgrade_trigger_ne = upgrade_trigger
        if _is_blank_alert_field(_upgrade_trigger_ne):
            _upgrade_trigger_ne = _derive_upgrade_trigger(
                signal, _tl_ctx_pre, _candle
            )
        lines += [
            "──────────────────────────────",
            "⚠️  NO CAPITAL YET",
        ]
        if blocker_note:
            lines.append(f"Blocker:            {blocker_note}")
        lines += [
            f"Missing conditions: {missing_str}",
            f"Upgrade trigger:    {_upgrade_trigger_ne}",
        ]

    # Phase 13.8B/13.8C: setup quality diagnostic (informational; no tier/capital effect)
    quality_label  = _evaluate_setup_quality(signal, final_tier)
    quality_phrase = _build_quality_phrase(quality_label, signal, final_tier)

    # Phase 14A: trajectory line (informational — never affects tier/capital/routing)
    _trajectory      = tiering_result.get("trajectory") or {}
    _trajectory_text = str(_trajectory.get("text", "")).strip()

    # Phase 14B: score calibration line (audit-only — never mutates main Score field)
    _calibration         = tiering_result.get("calibration") or {}
    _calibration_display = str(_calibration.get("display_text", "")).strip()

    # Phase 14C.1/14C.2: trade-location context (display-only — never affects
    # tier, capital, routing, suppression, or dedup). _tl_zone_low and
    # _tl_zone_type are already set above for the deep-failure EXECUTION line.
    _tl_ctx     = tiering_result.get("trade_location") or {}
    _tl_state   = str(_tl_ctx.get("location_state") or "unknown")
    _tl_display = str(_tl_ctx.get("display_text", "")).strip()
    _tl_conf    = _tl_ctx.get("confirmation_level")
    _tl_scan    = _tl_ctx.get("scan_price")

    try:
        _tl_conf_above = (
            _tl_conf is not None and _tl_scan is not None
            and float(_tl_conf) > float(_tl_scan)
        )
    except (TypeError, ValueError):
        _tl_conf_above = False

    # Directional language correction: a confirmation level above scan price is
    # something to reclaim, not "dip toward". Display-only prose fix.
    if _tl_conf_above:
        next_action = _DIP_TOWARD_RE.sub("push toward", next_action)
        reason      = _DIP_TOWARD_RE.sub("push toward", reason)

    # Phase 14C.2: repeated-signal realism. A repeated thesis or a cooldown-
    # expired re-alert must not read as a fresh new opportunity. Display-only.
    _traj_label   = str(_trajectory.get("label", "")).strip().upper()
    _dedup_reason = str((dedup_decision or {}).get("reason", "")).strip().lower()
    _is_repeated  = (
        _traj_label == "REPEATED_NO_CHANGE"
        or "cooldown_expired" in _dedup_reason
        or "repeat" in _dedup_reason
    )

    # Phase 14C.1: location-aware confirmation string.
    try:
        _tl_conf_str = f"{float(_tl_conf):.2f}" if _tl_conf is not None else "zone mid"
    except (TypeError, ValueError):
        _tl_conf_str = "zone mid"

    # Quality read acknowledgment: executable-tier quality language may not
    # ignore active lower-zone defense.
    if _tl_state == "lower_zone_defense" and final_tier in ("SNIPE_IT", "STARTER"):
        quality_phrase = (
            f"{quality_phrase} Zone defense active — "
            f"confirmation above {_tl_conf_str} still required."
        )

    # Phase 14C.2: location-proof consistency. In mid-zone acceptance with the
    # next-proof level still above price, executable quality language may not
    # imply add/full aggression before that level is reclaimed.
    _proof_note = ""
    if _tl_state == "mid_zone_acceptance" and _tl_conf_above:
        # Phase 14C.3B Defect 5: harmonize proof line with candle confirmation
        # requirement when next-candle verdict is still pending.
        _candle_sfx = " and candle confirmation" if _has_candle_gap else ""
        if final_tier == "SNIPE_IT":
            _proof_note = (
                f"Structure valid; fresh/add aggression waits for "
                f"acceptance above {_tl_conf_str}{_candle_sfx}."
            )
        elif final_tier == "STARTER":
            _proof_note = (
                f"Starter valid while holding zone; add waits for "
                f"acceptance above {_tl_conf_str}{_candle_sfx}."
            )
        elif final_tier == "NEAR_ENTRY":
            _proof_note = (
                "Structure valid, but execution proof remains incomplete."
            )

    lines += [
        "──────────────────────────────",
        "ACTION",
        f"  {action_headline}",
        f"  {sizing_line}",
        f"  Quality read: {quality_phrase}",
    ]
    # Phase 14C.2 / 14C.3B Defect 3: repeated-signal realism. Keeps tier
    # intact and declares explicit capital posture (hold / conditional-add /
    # no-capital / starter-only) so the repeated alert is never mistaken for
    # a fresh entry opportunity.
    if _is_repeated and final_tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        if final_tier == "SNIPE_IT":
            _repeated_note = "SNIPE_IT thesis remains valid after cooldown."
        else:
            _repeated_note = (
                "Repeated signal — thesis remains valid; "
                "no new aggression unless next proof confirms."
            )
        lines.append(f"  Repeated: {_repeated_note}")
        _posture = _derive_capital_posture_line(final_tier, _candle, _tl_ctx)
        if _posture:
            lines.append(f"  {_posture}")
    if _proof_note:
        lines.append(f"  Proof: {_proof_note}")
    lines += [
        f"  Next: {next_action}",
        f"  Why:  {reason}",
    ]
    if _trajectory_text:
        lines.append(f"  Trajectory:   {_trajectory_text}")
    if _calibration_display:
        lines.append(f"  Score realism: {_calibration_display}")
    if _tl_display and _tl_state != "unknown":
        lines.append(f"  Location: {_tl_display}")

    # Phase 14C.3: candle evidence read + caution (display-only — never affects
    # tier, capital, routing, suppression, dedup, or raw score).
    _candle         = tiering_result.get("candle_evidence") or {}
    _candle_display = str(_candle.get("display_text", "")).strip()
    _candle_family  = str(_candle.get("candle_family", "UNKNOWN"))
    _candle_veto    = str(_candle.get("candle_veto", "NONE")).strip().upper()
    if _candle_display and _candle_family not in ("UNKNOWN", ""):
        lines.append(f"  Candle read: {_candle_display}")
    if _candle_veto not in ("NONE", "UNKNOWN", ""):
        _veto_text = _humanize_candle_veto(_candle_veto)
        if _veto_text:
            lines.append(f"  Candle caution: {_veto_text}")

    # Phase 14E.1: compact 1H entry-trigger evidence block (display-only — never
    # affects tier, capital, routing, suppression, dedup, or raw score). The block
    # is structured, sovereign evidence and must NOT pass through the Claude-prose
    # narrative neutralizers (which would, e.g., rewrite the literal HOLD_CONFIRMED
    # enum). It is spliced in via a sentinel AFTER all guards have run.
    _one_hour_block_lines = _render_one_hour_lines(tiering_result.get("one_hour_entry"))
    if _one_hour_block_lines:
        lines.append(_ONE_HOUR_SENTINEL)

    # Phase 14F: compact multi-timeframe alignment block (display/audit only —
    # never affects tier, capital, routing, suppression, dedup, or raw score).
    # Placed beside the 1H block; spliced via a keyword-free sentinel after all
    # narrative guards so its structured enum values are never rewritten. Does
    # not replace or remove the 1H block.
    _tf_block_lines = _tf_alignment.render_timeframe_alignment_lines(
        tiering_result.get("timeframe_alignment")
    )
    if _tf_block_lines:
        lines.append(_TF_ALIGNMENT_SENTINEL)

    # Phase 14H: optional compact SNIPE-audit line (config-gated, default off).
    # One line only — no gate table, no bloat. Spliced via a keyword-free
    # sentinel after the narrative guards so its label enum is never rewritten.
    _snipe_audit_line = _snipe_audit.render_snipe_audit_line(
        tiering_result.get("snipe_gate_audit"), config
    )
    if _snipe_audit_line:
        lines.append(_SNIPE_AUDIT_SENTINEL)

    # Phase 14I: optional compact HTF-context line (config-gated, default off).
    _htf_context_line = _htf_context.render_htf_line(
        tiering_result.get("higher_timeframe_context"), config
    )
    if _htf_context_line:
        lines.append(_HTF_CONTEXT_SENTINEL)

    # FRESHNESS block — always present; snapshot_only when no live recheck price
    lines += [
        "──────────────────────────────",
        "FRESHNESS",
        f"  Scan Price: {_fmt_level(scan_price)}",
    ]
    if drift_status not in ("snapshot_only", "unknown") and drift_pct_raw != 0.0:
        try:
            dp = float(drift_pct_raw)
            sign = "+" if dp > 0 else ""
            lines.append(f"  Drift:      {sign}{dp:.2f}%")
        except (TypeError, ValueError):
            pass
    lines.append(f"  Status:     {drift_status}")
    # Phase 14C.3B Defect 4: deduplicate freshness notes — never render two
    # notes that say the same scan-time thing.
    _has_live_candle = bool(
        _candle_display and _candle_family not in ("UNKNOWN", "")
    )
    for _fn in _dedupe_freshness_notes(freshness_note, _is_repeated, _has_live_candle):
        lines.append(f"  Note:       {_fn}")

    lines += [
        "──────────────────────────────",
        "META",
    ]

    if dedup_decision:
        dedup_reason = dedup_decision.get("reason", "—")
        dedup_key    = dedup_decision.get("dedup_key", "—")
        lines.append(f"  Dedup: {dedup_reason}  |  Key: {dedup_key}")

    if scan_id:
        lines.append(f"  Scan ID: {scan_id}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Phase 13.7C: final body contract guard — contract guard then normalization.
    # Removes tier-contradicting phrases and cleans up any replacement artifacts.
    # Phase 13.7I: narrative sovereignty guard — structured state is sovereign;
    # runs after all prior passes with access to the full validated signal dict.
    rendered = "\n".join(lines)
    rendered = _apply_final_body_contract_guard(final_tier, rendered)
    # Phase 14C.3B Defect 2: when candle evidence is incomplete / unresolved,
    # generic completion language must not imply capital-ready status. Replace
    # tier-specific completion phrases with honest pending language.
    # _has_candle_gap is a superset of the 14C.3 veto-only gate; it also covers
    # PENDING verdict, bad family, and OPEN_OR_UNKNOWN status.
    if _has_candle_gap:
        rendered = _neutralize_completion_language_for_candle_gap(
            rendered, final_tier, _has_candle_gap
        )
    rendered = _apply_narrative_sovereignty_guard(final_tier, signal, rendered)
    # Phase 14E.1A: 1H alert-truth alignment. When the dedicated 1H evidence
    # object proves the trigger is not yet confirmed, cool any overstated legacy
    # retest/hold/quality proof wording. Runs after every narrative guard and
    # before the 1H block splice, so the structured 1H block is never altered and
    # capital/routing/tier/structured fields are left intact.
    rendered = _apply_one_hour_truth_alignment_guard(
        rendered, tiering_result.get("one_hour_entry")
    )
    # Phase 14G: posture compression (text-only). STARTER must read as reduced-
    # size, never watch-only; NEAR_ENTRY must not duplicate its blocker into the
    # missing-conditions line. Runs after the truth guard and before the splices
    # so the structured 1H / TF blocks are never touched.
    rendered = _apply_starter_posture_compression(rendered, final_tier, capital_action)
    # Phase 14Q: STARTER truth-headline — a forming-1H STARTER may not say
    # "STARTER conditions met." / "entry valid now". Runs after posture
    # compression so the corrected thesis-only headline survives to output.
    rendered = _apply_starter_truth_headline_guard(
        rendered, final_tier, tiering_result.get("one_hour_entry")
    )
    # Phase 14Q: a STARTER sealed down from SNIPE_IT with a confirmed base must
    # name the exact SNIPE-only blocker instead of the generic headline.
    rendered = _apply_confirmed_base_starter_headline_guard(
        rendered, final_tier, tiering_result
    )
    rendered = _apply_near_entry_missing_proof_compression(rendered, final_tier)
    # Splice the structured 1H block in after every narrative guard has run.
    if _one_hour_block_lines:
        rendered = rendered.replace(
            _ONE_HOUR_SENTINEL, "\n".join(_one_hour_block_lines)
        )
    # Splice the structured multi-timeframe alignment block in last (same
    # protection: enum values are never rewritten by the narrative guards).
    if _tf_block_lines:
        rendered = rendered.replace(
            _TF_ALIGNMENT_SENTINEL, "\n".join(_tf_block_lines)
        )
    if _snipe_audit_line:
        rendered = rendered.replace(_SNIPE_AUDIT_SENTINEL, _snipe_audit_line)
    if _htf_context_line:
        rendered = rendered.replace(_HTF_CONTEXT_SENTINEL, _htf_context_line)
    return rendered


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_message(text: str, max_len: int = _DISCORD_MAX_CHARS) -> list[str]:
    """Split text into chunks ≤ max_len chars, breaking on line boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in text.split("\n"):
        # Hard-split a single line that exceeds max_len
        while len(line) > max_len:
            chunks.append(line[:max_len])
            line = line[max_len:]

        line_with_newline = len(line) + 1  # +1 for the \n
        if current_len + line_with_newline > max_len and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0

        current_lines.append(line)
        current_len += line_with_newline

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


# ---------------------------------------------------------------------------
# Send-guard helpers
# ---------------------------------------------------------------------------

def _sendable(tiering_result: dict, dedup_decision: dict | None) -> tuple[bool, str]:
    """Return (sendable, skip_reason). All hard blocks checked here."""
    final_tier = tiering_result.get("final_tier", "WAIT")
    safe       = tiering_result.get("safe_for_alert", False)

    if final_tier == "WAIT":
        return False, "wait_no_alert"
    if not safe:
        return False, "unsafe_for_alert"
    if final_tier not in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        return False, f"unknown_tier:{final_tier}"

    if dedup_decision is not None and not dedup_decision.get("should_alert", True):
        return False, dedup_decision.get("reason", "dedup_suppressed")

    return True, ""


def _not_sendable(skip_reason: str, final_tier: str) -> dict:
    return {
        "ok": True,
        "sent": False,
        "channel_id": None,
        "final_tier": final_tier,
        "message_count": 0,
        "error_type": None,
        "error_message": None,
        "skipped_reason": skip_reason,
    }


def _missing_channel(final_tier: str, ticker: str) -> dict:
    log.warning("ROUTING_FAILURE: %s %s — channel not configured", final_tier, ticker)
    return {
        "ok": True,
        "sent": False,
        "channel_id": None,
        "final_tier": final_tier,
        "message_count": 0,
        "error_type": "routing_failure",
        "error_message": f"channel not configured for tier {final_tier}",
        "skipped_reason": "channel_not_configured",
    }


def _send_error(channel_id: int, final_tier: str, exc: Exception) -> dict:
    log.error("DISCORD_SEND_FAILED: %s channel=%s: %s", final_tier, channel_id, exc)
    return {
        "ok": False,
        "sent": False,
        "channel_id": channel_id,
        "final_tier": final_tier,
        "message_count": 0,
        "error_type": "discord_send_error",
        "error_message": str(exc),
        "skipped_reason": None,
    }


def _send_ok(channel_id: int, final_tier: str, message_count: int) -> dict:
    return {
        "ok": True,
        "sent": True,
        "channel_id": channel_id,
        "final_tier": final_tier,
        "message_count": message_count,
        "error_type": None,
        "error_message": None,
        "skipped_reason": None,
    }


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def send_alert(
    tiering_result: dict,
    dedup_decision: dict | None,
    bot,
    config: dict,
    scan_id: str = "",
) -> dict:
    """Format and send a validated signal alert to the appropriate Discord channel.

    Returns a structured result dict; never raises.
    WAIT is never posted. Null channel IDs are safe.
    """
    final_tier = tiering_result.get("final_tier", "WAIT")
    signal     = tiering_result.get("final_signal") or {}
    ticker     = str(signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN"))

    ok, skip_reason = _sendable(tiering_result, dedup_decision)
    if not ok:
        return _not_sendable(skip_reason, final_tier)

    channel_id = resolve_channel_id(final_tier, config)
    if channel_id is None:
        return _missing_channel(final_tier, ticker)

    channel = bot.get_channel(channel_id)
    if channel is None:
        log.warning("ROUTING_FAILURE: %s %s — bot.get_channel(%s) returned None", final_tier, ticker, channel_id)
        return _missing_channel(final_tier, ticker)

    text   = format_alert(tiering_result, dedup_decision, scan_id, config)
    chunks = chunk_message(text)

    try:
        for chunk in chunks:
            await channel.send(chunk)
        log.info("Alert sent: %s %s → channel %s (%d chunk(s))", final_tier, ticker, channel_id, len(chunks))
        return _send_ok(channel_id, final_tier, len(chunks))
    except Exception as exc:
        return _send_error(channel_id, final_tier, exc)

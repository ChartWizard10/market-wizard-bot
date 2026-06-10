"""Discord alert formatting and routing for validated final signals.

Reads only from tiering_result['final_signal'] and tiering_result top-level fields.
Routes by final_tier exclusively — never trusts Claude's discord_channel field.
WAIT never posts. Null channel IDs are safe (log + skip, no raise).
Does not call Claude, yfinance, tiering, or state_store.
"""

import logging
import os
import re

log = logging.getLogger(__name__)

_DISCORD_MAX_CHARS = 2000

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
    if final_tier == "NEAR_ENTRY":
        result = _apply_near_entry_capital_firewall(result)
    return result


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
    # Phase 14F.1: NEAR_ENTRY language firewall — execution commands and
    # capital-tier language can never imply action in a watch-only alert.
    # Execution-command patterns consume to end of line: an entry instruction
    # is an action clause, and watch-only language must fully replace it
    # rather than leave a truncated half-command behind.
    (r"\benter\s+(?:at|near)\b[^\n]*",
     "Monitor for reclaim, acceptance, and hold. No capital until blocker resolves."),
    (r"\bentry\s+(?:at|near)\b[^\n]*",
     "watch level only; no capital until blocker resolves."),
    (r"\bbuy\s+at\b[^\n]*",
     "Monitor for reclaim, acceptance, and hold. No capital until blocker resolves."),
    (r"\btake\s+the\s+trade\b",
     "continue watching"),
    (r"\btake\s+at\b[^\n]*",
     "Monitor for reclaim, acceptance, and hold. No capital until blocker resolves."),
    (r"\bcurrent\s+price\s+with\s+stop\b[^\n]*",
     "Watch only. Capital remains withheld until the trigger is reclaimed and accepted."),
    (r"\bfull[-\s]+sized?\b",
     "no-capital"),
    (r"\bstarter\s+siz(?:e[ds]?|ing)\b",
     "no capital"),
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
# Entry Grade Engine — display-only entry quality classifier.
# Answers: "Is this exact location worth capital right now?"
# ---------------------------------------------------------------------------

_ENTRY_GRADE_LABELS: dict[str, str] = {
    "A_PLUS":     "A+ — sniper-grade location; precision criteria met.",
    "A_GRADE":    "A — executable; confirmation criteria met.",
    "B_DEFAULT":  "B — confirmed; entry precision imperfect.",
    "B_UNPROVEN": "B — zone defense unconfirmed.",
    "B_FRAGILE":  "B — risk window compressed.",
    "B_OVERHEAD": "B — overhead path not clean.",
    "B_CHASING":  "B — price extended above trigger.",
    "B_WATCH":    "B — watch tier; conditions require further confirmation.",
    "C_GRADE":    "C — price location adverse.",
    "F_GRADE":    "F — retest or hold not confirmed.",
}


def _classify_entry_grade(signal: dict, final_tier: str) -> str:
    """Classify entry quality. Display-only — never affects tier, capital, or routing.

    Grade law (first match wins):
      F  — retest or hold not confirmed
      C  — acceptance damaging or invalidated
      B  — ceiling: unproven, fragile risk, blocked overhead, or chasing > +2.0%
      A+ — accepted, healthy risk, rr≥4.0, clear overhead, drift ≤+0.5%
      A  — accepted, healthy/tight risk, rr≥3.0, clear/moderate overhead
      B  — default for confirmed but imperfect
    """
    if final_tier == "WAIT":
        return ""

    retest     = str(signal.get("retest_status",   "missing") or "missing").lower().strip()
    hold       = str(signal.get("hold_status",     "missing") or "missing").lower().strip()
    acceptance = str(signal.get("entry_acceptance","unknown") or "unknown").lower().strip()
    risk_state = str(signal.get("risk_realism_state","unknown") or "unknown").lower().strip()
    overhead   = str(signal.get("overhead_status", "unknown") or "unknown").lower().strip()

    rr: float | None = None
    try:
        raw_rr = signal.get("risk_reward")
        if raw_rr is not None:
            rr = float(raw_rr)
    except (TypeError, ValueError):
        pass

    drift_pct: float | None = None
    try:
        raw_drift = signal.get("price_distance_to_trigger_pct")
        if raw_drift is not None:
            drift_pct = float(raw_drift)
    except (TypeError, ValueError):
        pass

    if retest != "confirmed" or hold != "confirmed":
        return _ENTRY_GRADE_LABELS["F_GRADE"]

    if acceptance in ("damaging", "invalidated"):
        return _ENTRY_GRADE_LABELS["C_GRADE"]

    if acceptance == "unproven":
        return _ENTRY_GRADE_LABELS["B_UNPROVEN"]
    if risk_state == "fragile":
        return _ENTRY_GRADE_LABELS["B_FRAGILE"]
    if overhead == "blocked":
        return _ENTRY_GRADE_LABELS["B_OVERHEAD"]
    if drift_pct is not None and drift_pct > 2.0:
        return _ENTRY_GRADE_LABELS["B_CHASING"]

    # NEAR_ENTRY tier gate is active; capital not authorized regardless of conditions.
    if final_tier == "NEAR_ENTRY":
        return _ENTRY_GRADE_LABELS["B_WATCH"]

    if (
        acceptance == "accepted"
        and risk_state == "healthy"
        and rr is not None and rr >= 4.0
        and overhead == "clear"
        and drift_pct is not None and drift_pct <= 0.5
    ):
        return _ENTRY_GRADE_LABELS["A_PLUS"]

    if (
        acceptance == "accepted"
        and risk_state in ("healthy", "tight")
        and overhead in ("clear", "moderate")
        and rr is not None and rr >= 3.0
    ):
        return _ENTRY_GRADE_LABELS["A_GRADE"]

    return _ENTRY_GRADE_LABELS["B_DEFAULT"]


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


def _build_exit_strategy_lines(
    targets: list,
    inval_level,
    inval_condition: str,
    final_tier: str,
) -> list[str]:
    """Build EXIT STRATEGY section lines from existing computed fields only.

    Maps T1→TP1, T2→TP2, T3→TP3 from the existing targets list.
    Never invents target levels — absent TPs show "—".
    Language is selected to pass all contract and sovereignty guards cleanly.
    """
    tp: dict[int, object] = {}
    for t in (targets or []):
        if not isinstance(t, dict):
            continue
        lbl = str(t.get("label", "")).strip().upper()
        if lbl == "T1" and 1 not in tp:
            tp[1] = t.get("level")
        elif lbl == "T2" and 2 not in tp:
            tp[2] = t.get("level")
        elif lbl == "T3" and 3 not in tp:
            tp[3] = t.get("level")

    tp1 = _fmt_level(tp.get(1))
    tp2 = _fmt_level(tp.get(2)) if 2 in tp else "—"
    tp3 = _fmt_level(tp.get(3)) if 3 in tp else "—"

    inval_str = _fmt_level(inval_level)
    _ic = (inval_condition or "").strip()
    inval_desc = f" ({_ic})" if _ic and _ic not in ("—", "none", "None") else ""

    lines: list[str] = [
        "──────────────────────────────",
        "EXIT STRATEGY",
    ]

    if final_tier == "SNIPE_IT":
        lines += [
            f"  TP1: {tp1}  — first trim, reduce risk.",
            f"  TP2: {tp2}  — main profit-take / begin trail.",
            f"  TP3: {tp3}  — runner extension only.",
            f"  Hard stop: {inval_str}{inval_desc}",
            "  Trail: active only after TP1 confirmed and structure holds.",
        ]
    elif final_tier == "STARTER":
        lines += [
            f"  TP1: {tp1}  — partial exit, starter size.",
            f"  TP2: {tp2}  — exit remainder; no additions until upgrade confirmed.",
            f"  TP3: {tp3}  — runner only if upgraded.",
            f"  Hard stop: {inval_str}{inval_desc}",
            "  Manage at starter size only.",
        ]
    elif final_tier == "NEAR_ENTRY":
        lines += [
            "  Exit plan: conditional — no capital until blocker resolves.",
            f"  TP1 reference: {tp1}  (if entry triggered).",
            f"  Hard stop reference: {inval_str}{inval_desc}",
        ]

    return lines


def format_alert(
    tiering_result: dict,
    dedup_decision: dict | None = None,
    scan_id: str = "",
) -> str:
    """Build plain-text alert message from validated tiering_result fields only."""
    final_tier   = tiering_result.get("final_tier", "WAIT")
    score        = tiering_result.get("score", 0)
    signal       = tiering_result.get("final_signal") or {}

    ticker           = _sanitize(str(signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")))
    setup_family     = _sanitize(str(signal.get("setup_family", "—")))
    structure_event  = _sanitize(str(signal.get("structure_event", "—")))
    trend_state      = _sanitize(str(signal.get("trend_state", "—")))
    zone_type        = _sanitize(str(signal.get("zone_type", "—")))

    # Phase 1E — Human-facing state truth layer. Display-only: scanner-computed
    # market_structure_state is shown beside Claude's trend_state so humans can
    # see the evidence layer. Never read by any gate, score, routing, or capital
    # decision; rendered only when present (absent → output unchanged).
    _mkt_state_raw = signal.get("market_structure_state")
    market_structure_state = (
        _sanitize(str(_mkt_state_raw)) if _mkt_state_raw else ""
    )

    # Phase 14A — Weekly Sovereignty context (display-only). Scanner-computed
    # weekly evidence shown beside the daily layer; never read by any gate,
    # score, routing, or capital decision. Rendered only when present.
    _wk_sma_raw   = signal.get("weekly_sma_alignment")
    _wk_trend_raw = signal.get("weekly_trend_state")
    _wk_ctx_raw   = signal.get("weekly_alignment_context")
    weekly_sma_alignment     = _sanitize(str(_wk_sma_raw)) if _wk_sma_raw else ""
    weekly_trend_state       = _sanitize(str(_wk_trend_raw)) if _wk_trend_raw else ""
    weekly_alignment_context = _sanitize(str(_wk_ctx_raw)) if _wk_ctx_raw else ""

    # Phase 14C — Real 4H Operational State context (display-only). Scanner-
    # computed 4H evidence shown beneath the weekly/daily layers; never read by
    # any gate, score, routing, or capital decision. Rendered only when present.
    # No authority language ("blocked"/"approved"/"downgraded"/"vetoed").
    _4h_state_raw   = signal.get("four_hour_market_state")
    _4h_sma_raw     = signal.get("four_hour_sma_alignment")
    _4h_reclaim_raw = signal.get("four_hour_reclaim_status")
    _4h_data_raw    = signal.get("four_hour_data_status")
    four_hour_market_state   = _sanitize(str(_4h_state_raw)) if _4h_state_raw else ""
    four_hour_sma_alignment  = _sanitize(str(_4h_sma_raw)) if _4h_sma_raw else ""
    four_hour_reclaim_status = _sanitize(str(_4h_reclaim_raw)) if _4h_reclaim_raw else ""
    four_hour_data_status    = _sanitize(str(_4h_data_raw)) if _4h_data_raw else ""

    # Phase 14E — Real 1H Entry Trigger context (display-only). Scanner-computed
    # 1H trigger evidence shown beneath the 4H/weekly/daily layers; never read by
    # any gate, score, routing, or capital decision. Informational only — implies
    # no authority, no approval, and no capital authorisation. Rendered only when
    # present. No authority language ("blocked"/"approved"/"downgraded"/"vetoed").
    _1h_trigger_raw    = signal.get("one_hour_trigger_family")
    _1h_retest_raw     = signal.get("one_hour_retest_quality")
    _1h_accept_raw     = signal.get("one_hour_acceptance_state")
    _1h_conseq_raw     = signal.get("one_hour_consequence_state")
    _1h_nochase_raw    = signal.get("one_hour_no_chase_status")
    _1h_data_raw       = signal.get("one_hour_data_status")
    one_hour_trigger_family    = _sanitize(str(_1h_trigger_raw)) if _1h_trigger_raw else ""
    one_hour_retest_quality    = _sanitize(str(_1h_retest_raw)) if _1h_retest_raw else ""
    one_hour_acceptance_state  = _sanitize(str(_1h_accept_raw)) if _1h_accept_raw else ""
    one_hour_consequence_state = _sanitize(str(_1h_conseq_raw)) if _1h_conseq_raw else ""
    one_hour_no_chase_status   = _sanitize(str(_1h_nochase_raw)) if _1h_nochase_raw else ""
    one_hour_data_status       = _sanitize(str(_1h_data_raw)) if _1h_data_raw else ""

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

    # Phase 1E: insert Market State between Trend and Zone only when present.
    if market_structure_state:
        trend_zone_line = (
            f"Trend: {trend_state}  |  Market State: {market_structure_state}"
            f"  |  Zone: {zone_type}"
        )
    else:
        trend_zone_line = f"Trend: {trend_state}  |  Zone: {zone_type}"

    # Phase 14A: weekly context line, shown beneath the daily line only when any
    # weekly evidence is present. Daily layer above is never altered.
    _weekly_line = None
    if weekly_trend_state or weekly_sma_alignment or weekly_alignment_context:
        _wk_trend = weekly_trend_state or "unknown"
        _wk_sma   = weekly_sma_alignment or "unavailable"
        _wk_ctx   = weekly_alignment_context or "unknown"
        _weekly_line = (
            f"Weekly: {_wk_trend} / {_wk_sma}  |  Alignment: {_wk_ctx}"
        )

    # Phase 14C: 4H operational-condition line, shown beneath the weekly/daily
    # lines only when any 4H evidence is present. Context only — daily/weekly
    # layers above are never altered. No authority language.
    _four_hour_line = None
    if (four_hour_market_state or four_hour_sma_alignment
            or four_hour_reclaim_status or four_hour_data_status):
        _4h_state   = four_hour_market_state or "UNAVAILABLE"
        _4h_sma     = four_hour_sma_alignment or "unavailable"
        _4h_reclaim = four_hour_reclaim_status or "unavailable"
        _4h_data    = four_hour_data_status or "unavailable"
        _four_hour_line = (
            f"4H: {_4h_state}  |  SMA: {_4h_sma}  |  "
            f"Reclaim: {_4h_reclaim}  |  Data: {_4h_data}"
        )

    # Phase 14E: 1H trigger-evidence line, shown beneath the 4H/weekly/daily
    # lines only when any 1H evidence is present. Informational context only —
    # the higher-timeframe layers above are never altered, and this line never
    # implies authority or approval. No authority language.
    _one_hour_line = None
    if (one_hour_trigger_family or one_hour_retest_quality
            or one_hour_acceptance_state or one_hour_consequence_state
            or one_hour_no_chase_status or one_hour_data_status):
        _1h_trigger = one_hour_trigger_family or "unknown"
        _1h_retest  = one_hour_retest_quality or "unknown"
        _1h_accept  = one_hour_acceptance_state or "unknown"
        _1h_conseq  = one_hour_consequence_state or "unknown"
        _1h_nochase = one_hour_no_chase_status or "unknown"
        _1h_data    = one_hour_data_status or "unavailable"
        _one_hour_line = (
            f"1H: {_1h_trigger}  |  Retest: {_1h_retest}  |  "
            f"Acceptance: {_1h_accept}  |  Consequence: {_1h_conseq}  |  "
            f"No-Chase: {_1h_nochase}  |  Data: {_1h_data}"
        )

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{badge} | {ticker} | Score: {score}",
        f"Setup: {setup_family}  |  Structure: {structure_event}",
        trend_zone_line,
    ]
    if _weekly_line:
        lines.append(_weekly_line)
    if _four_hour_line:
        lines.append(_four_hour_line)
    if _one_hour_line:
        lines.append(_one_hour_line)
    lines += [
        "──────────────────────────────",
        "EXECUTION",
        f"  Trigger:      {_fmt_level(trigger_level)}",
        f"  Retest:       {retest_status}",
        f"  Hold:         {hold_status}",
        f"  Invalidation: {inval_condition} @ {_fmt_level(inval_level)}",
        f"  R:R:          {rr_str}",
        f"  Overhead:     {overhead_label}",
    ]

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

    lines += _build_exit_strategy_lines(targets, inval_level, inval_condition, final_tier)

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
        # Phase 12.3: render blocker note above missing conditions.
        # Phase 12.3A: strip leading "Blocker:" prefix before adding our label
        # so _build_near_entry_blocker_note's prefix does not double up.
        # Phase 13.7D/13.7G: strip raw field-label prefixes; humanize gate keys;
        # seal tier-mechanics classification language.
        _blocker_cleaned = _humanize_blocker_note(_clean_blocker_label(raw_blocker_str))
        _blocker_cleaned = _humanize_bare_gate_keys(_blocker_cleaned)
        _blocker_cleaned = _seal_near_entry_classification_language(_blocker_cleaned)
        blocker_note = _sanitize(_blocker_cleaned)
        lines += [
            "──────────────────────────────",
            "⚠️  NO CAPITAL YET",
        ]
        if blocker_note:
            lines.append(f"Blocker:            {blocker_note}")
        lines += [
            f"Missing conditions: {missing_str}",
            f"Upgrade trigger:    {upgrade_trigger}",
        ]

    # Phase 13.8B/13.8C: setup quality diagnostic (informational; no tier/capital effect)
    quality_label  = _evaluate_setup_quality(signal, final_tier)
    quality_phrase = _build_quality_phrase(quality_label, signal, final_tier)

    # Entry grade — display-only; never affects tier, capital, or routing
    entry_grade_phrase = _classify_entry_grade(signal, final_tier)

    # Phase 14A: trajectory line (informational — never affects tier/capital/routing)
    _trajectory      = tiering_result.get("trajectory") or {}
    _trajectory_text = str(_trajectory.get("text", "")).strip()

    # Phase 14B: score calibration line (audit-only — never mutates main Score field)
    _calibration         = tiering_result.get("calibration") or {}
    _calibration_display = str(_calibration.get("display_text", "")).strip()

    lines += [
        "──────────────────────────────",
        "ACTION",
        f"  {action_headline}",
        f"  {sizing_line}",
        f"  Quality read: {quality_phrase}",
    ]
    if entry_grade_phrase:
        lines.append(f"  Entry grade: {entry_grade_phrase}")
    lines += [
        f"  Next: {next_action}",
        f"  Why:  {reason}",
    ]
    if _trajectory_text:
        lines.append(f"  Trajectory:   {_trajectory_text}")
    if _calibration_display:
        lines.append(f"  Score realism: {_calibration_display}")

    # Phase 14F: Active Auction Conflict notice — rendered only when the
    # governor in tiering.py already capped the tier. This block displays a
    # decision that was made upstream; it makes no decision here and the
    # 4H/1H evidence lines above remain authority-free.
    if signal.get("active_auction_conflict"):
        _aac_note_raw = signal.get("active_auction_conflict_note")
        _aac_note = _sanitize(str(_aac_note_raw)) if _aac_note_raw else (
            "Full-size capital withheld. The active 4H/1H auction has not "
            "yet proven continuation acceptance."
        )
        lines += [
            "──────────────────────────────",
            "⚠️  ACTIVE AUCTION CONFLICT",
            f"  {_aac_note}",
        ]

    # Phase 15A: Daily Authority Governor notice — rendered only when the
    # governor in tiering.py already capped the tier. Display-only; the
    # decision was made upstream and is not re-made here.
    if signal.get("daily_authority_conflict"):
        _dag_note_raw = signal.get("daily_authority_note")
        _dag_cap = signal.get("daily_permission_cap") or ""
        if "NEAR_ENTRY" in _dag_cap:
            _dag_header = "⚠️  DAILY AUTHORITY CONFLICT"
            _dag_default = (
                "Capital withheld. Lower-timeframe structure may be improving, "
                "but the daily chart has not granted swing permission yet."
            )
        else:
            _dag_header = "⚠️  DAILY AUTHORITY CAP"
            _dag_default = (
                "Starter only. Daily context is constructive enough to monitor, "
                "but one or more authority layers are incomplete."
            )
        _dag_note = _sanitize(str(_dag_note_raw)) if _dag_note_raw else _dag_default
        lines += [
            "──────────────────────────────",
            _dag_header,
            f"  {_dag_note}",
        ]

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
    if freshness_note:
        lines.append(f"  Note:       {freshness_note}")

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
    return _apply_narrative_sovereignty_guard(final_tier, signal, rendered)


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

    text   = format_alert(tiering_result, dedup_decision, scan_id)
    chunks = chunk_message(text)

    try:
        for chunk in chunks:
            await channel.send(chunk)
        log.info("Alert sent: %s %s → channel %s (%d chunk(s))", final_tier, ticker, channel_id, len(chunks))
        return _send_ok(channel_id, final_tier, len(chunks))
    except Exception as exc:
        return _send_error(channel_id, final_tier, exc)

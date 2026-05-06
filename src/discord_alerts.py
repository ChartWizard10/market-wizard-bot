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
            ("no position management until capital is authorized",
             "Maintain starter-only sizing until upgrade conditions are met."),
            ("all snipe_it conditions satisfied",   "STARTER conditions met."),
            ("all snipe_it conditions are met",     "STARTER conditions met."),
            ("all snipe_it conditions met.",        "STARTER conditions met."),
            ("snipe_it conditions satisfied",       "STARTER conditions met."),
            ("snipe_it conditions are met",         "STARTER conditions met."),
            ("all snipe_it conditions met",         "STARTER conditions met."),
            ("no capital — watch only",             "STARTER SIZE ONLY"),
            ("snipe_it conditions met",             "STARTER conditions met."),
            ("near-entry watch",
             "Maintain starter-only sizing until upgrade conditions are met."),
            ("capital authorized",                  "reduced-size capital allocated"),
            ("full quality",                        "STARTER SIZE ONLY"),
            # "full-size" / "full size" intentionally excluded — "full-size confirmation
            # not granted" is legitimate STARTER denial language; the bare substring
            # would produce false positives. "full quality" catches the real risk.
            ("no capital",                          "STARTER SIZE ONLY"),
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
            # 21
            ("downgraded to starter",             "Watch-only; no capital."),
            ("making this a starter",             "Watch-only; no capital."),
            # 20
            ("watchlist only until",              "Watch-only; no capital."),
            ("downgrade to starter",              "Watch-only; no capital."),
            # 19
            ("position management",               "Watch-only; wait for blocker resolution."),
            ("snipe_it to starter",               "Watch-only; no capital."),
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
    upgrade_trigger    = _sanitize(str(signal.get("upgrade_trigger", "—")))
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
        missing_str = ", ".join(_sanitize(str(c)) for c in missing_conditions) if missing_conditions else "—"
        # Phase 12.3: render blocker note above missing conditions.
        # Phase 12.3A: strip leading "Blocker:" prefix before adding our label
        # so _build_near_entry_blocker_note's prefix does not double up.
        blocker_note = _sanitize(_clean_blocker_label(raw_blocker_str))
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

    lines += [
        "──────────────────────────────",
        "ACTION",
        f"  {action_headline}",
        f"  {sizing_line}",
        f"  Next: {next_action}",
        f"  Why:  {reason}",
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

    # Phase 13.7B: contract guard — deterministic final pass.
    # Removes any tier-contradicting phrases that survived all upstream sanitization.
    rendered = "\n".join(lines)
    return _apply_contract_guard(rendered, final_tier)


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

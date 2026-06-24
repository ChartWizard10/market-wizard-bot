"""Phase 14J — read-only operator audit-access bridge for alert_history.

A pure, dependency-free evidence-retrieval organ. Given a scan_id or ticker, it
reads the production state file (the SAME path src/state_store.py resolves) and
returns compact, human-readable audit evidence for the matching alert_history
row(s): tier/capital/score, the persisted 1H proxy fields, the Phase 14H.1
snipe_gate_audit snapshot, and the Phase 14I higher_timeframe_context snapshot,
plus a one-line promotion-path interpretation.

Hard guarantees (this module is an audit bridge, not trading logic):
  - READ-ONLY. It never writes, moves, or resets the state file. (Note: it does
    NOT call state_store.load(), which backs up + resets corrupt files.)
  - It never mutates tiering, capital, scoring, routing, suppression, dedup,
    SNIPE gates, compression, higher_timeframe_context, or snipe_gate_audit.
  - It never executes shell, never accepts arbitrary file paths (the path comes
    only from config via state_store), never dumps the whole state file, and
    never emits secrets/tokens (it whitelists compact fields only).
  - Pure stdlib; no Discord/network imports — fully unit-testable.

FIELD_MAP honesty (verified against src/state_store.record_alert):
  - Rows live under state["tickers"][TICKER]["alert_history"] (per-ticker lists,
    NOT a global flat list).
  - A row uses keys `tier` (not final_tier), `alerted_at` (not timestamp),
    `final_discord_channel` (not signal_channel).
  - Persisted evidence snapshots: `snipe_gate_audit` (Phase 14H.1 compact),
    `higher_timeframe_context` (Phase 14I compact), `one_hour_entry` and
    `timeframe_alignment` (Phase 14O compact). The legacy `retest_status`/
    `hold_status` proxies (sourced from final_signal, not one_hour_entry)
    are preserved unchanged alongside the new evidence.
  - Historical rows persisted before Phase 14O lack `one_hour_entry`/
    `timeframe_alignment` entirely; those rows are reported as "not persisted
    on this historical row" rather than invented.
"""

import json
import re
from pathlib import Path

from src import state_store

# ---------------------------------------------------------------------------
# Config / defaults
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ROWS = 3
_DISCORD_MAX_CHARS = 1900           # conservative (< Discord's 2000 hard cap)
_SCAN_ID_RE = re.compile(r"^scan_[0-9]{8}_[0-9]{6}_[0-9a-zA-Z]+$")

# Conclusion labels (closed set — spec-defined).
CONCLUSIONS = {
    "CORRECTLY_BLOCKED", "POSSIBLE_UNDER_PROMOTION", "CORRECT_STARTER",
    "CORRECT_NEAR_ENTRY", "NEEDS_MANUAL_REVIEW",
    # Phase 14K additions:
    "SNIPE_CONFIRMED", "INCONSISTENT_AUDIT_STATE",
    # Phase 14M addition — a LEGACY/historical persisted SNIPE_IT row (no Phase
    # 14M.1 snipe_confirmed_seal marker) whose own evidence still carries
    # active blockers is a false SNIPE confirmation, never a clean one. A
    # post-14M sealed row never reaches this label (see sealed_applied above);
    # it resolves to CORRECT_NEAR_ENTRY/CORRECT_STARTER instead.
    "INCONSISTENT_SNIPE_CONFIRMED",
}

_CONFIRMED_TOKENS = {"confirmed", "hold_confirmed", "retest_confirmed", "true", "yes", "pass"}


# ---------------------------------------------------------------------------
# Read-only state access (never mutates / never resets corrupt files)
# ---------------------------------------------------------------------------

def _audit_cfg(config: dict) -> dict:
    cfg = (config or {}).get("audit_access")
    return cfg if isinstance(cfg, dict) else {}


def load_state_readonly(config: dict) -> dict:
    """Strictly read-only load of the alert_history state file.

    Returns {"ok": True, "state": <dict>} or {"ok": False, "error": <code>,
    "message": <friendly>}. Never raises, never writes/moves/resets anything
    (unlike state_store.load, which backs up + resets corrupt files).
    """
    path = state_store._state_path(config or {})       # reuse existing resolution
    try:
        if not Path(path).exists():
            return {
                "ok": False, "error": "state_file_not_found",
                "message": f"No alert_history state file found at `{path}`.",
            }
        raw = Path(path).read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "ok": False, "error": "state_file_unreadable",
            "message": f"Could not read state file: {type(exc).__name__}.",
        }
    try:
        data = json.loads(raw)
    except Exception:
        return {
            "ok": False, "error": "state_file_malformed",
            "message": "State file is malformed JSON — cannot audit (read-only; not modifying it).",
        }
    if not isinstance(data, dict) or not isinstance(data.get("tickers"), dict):
        return {
            "ok": False, "error": "state_file_malformed",
            "message": "State file structure is unexpected (missing 'tickers') — cannot audit.",
        }
    return {"ok": True, "state": data}


# ---------------------------------------------------------------------------
# Query parsing + row lookup
# ---------------------------------------------------------------------------

def parse_query(arg: str):
    """Classify a query token as a scan_id or a ticker.

    Returns ("scan_id", value) | ("ticker", VALUE) | ("invalid", None).
    """
    if not isinstance(arg, str):
        return ("invalid", None)
    token = arg.strip()
    if not token:
        return ("invalid", None)
    if _SCAN_ID_RE.match(token) or token.lower().startswith("scan_"):
        return ("scan_id", token)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", token):
        return ("ticker", token.upper())
    return ("invalid", None)


def _iter_rows(state: dict):
    tickers = (state or {}).get("tickers") or {}
    if not isinstance(tickers, dict):
        return
    for tkr_state in tickers.values():
        if not isinstance(tkr_state, dict):
            continue
        history = tkr_state.get("alert_history")
        if isinstance(history, list):
            for row in history:
                if isinstance(row, dict):
                    yield row


def find_by_scan_id(state: dict, scan_id: str) -> list:
    """All rows whose scan_id matches exactly (newest last in storage order)."""
    return [r for r in _iter_rows(state) if r.get("scan_id") == scan_id]


def find_by_ticker(state: dict, ticker: str, max_rows: int = _DEFAULT_MAX_ROWS) -> list:
    """Latest <=max_rows rows for a ticker (most recent first)."""
    tickers = (state or {}).get("tickers") or {}
    tkr_state = tickers.get(ticker) if isinstance(tickers, dict) else None
    if not isinstance(tkr_state, dict):
        return []
    history = tkr_state.get("alert_history")
    if not isinstance(history, list):
        return []
    rows = [r for r in history if isinstance(r, dict)]
    # Storage order is append (oldest->newest); newest first for display.
    rows = sorted(rows, key=lambda r: str(r.get("alerted_at") or ""), reverse=True)
    n = max(1, int(max_rows or _DEFAULT_MAX_ROWS))
    return rows[:n]


# ---------------------------------------------------------------------------
# Permission gate (conservative — disabled unless explicitly configured)
# ---------------------------------------------------------------------------

def is_authorized(config: dict, user_id=None, channel_id=None) -> dict:
    """Conservative read-only access gate.

    Returns {"allowed": bool, "reason": str}.
      - audit_access missing or enabled=false  -> denied (feature off).
      - enabled but no user/channel IDs configured -> denied by default.
      - enabled with IDs -> allowed when user_id in allowed_user_ids OR
        channel_id in allowed_channel_ids.
    """
    cfg = _audit_cfg(config)
    if not cfg or cfg.get("enabled", False) is not True:
        return {"allowed": False, "reason": "audit_access disabled (config.audit_access.enabled is not true)"}

    allowed_users = {str(x) for x in (cfg.get("allowed_user_ids") or []) if x is not None}
    allowed_channels = {str(x) for x in (cfg.get("allowed_channel_ids") or []) if x is not None}

    if not allowed_users and not allowed_channels:
        return {
            "allowed": False,
            "reason": "audit_access enabled but no allowed_user_ids/allowed_channel_ids configured (denied by default)",
        }

    if user_id is not None and str(user_id) in allowed_users:
        return {"allowed": True, "reason": "authorized operator user"}
    if channel_id is not None and str(channel_id) in allowed_channels:
        return {"allowed": True, "reason": "authorized operator channel"}

    return {"allowed": False, "reason": "caller user/channel not in audit_access allow-list"}


# ---------------------------------------------------------------------------
# Interpretation (promotion-path conclusion)
# ---------------------------------------------------------------------------

def _is_confirmed(value) -> bool:
    return isinstance(value, str) and value.strip().lower() in _CONFIRMED_TOKENS


def _nonempty_list(value) -> list:
    return [x for x in value if x not in (None, "", [])] if isinstance(value, list) else []


def interpret(row: dict) -> dict:
    """Promotion-path interpretation of a persisted row.

    Returns {"label": <CONCLUSIONS>, "notes": [str, ...]}.

    Phase 14K: this is the defense-in-depth consistency seal for HISTORICAL
    rows. A row persisted by an older (pre-14K) snipe_gate_audit build could
    claim promotion_state == PROMOTION_READY while blocked_gate_names /
    missing_proofs / an HTF contextual block are simultaneously non-empty
    (the live HAE scan_20260622_164918_4fc48e contradiction). Such a row is
    never rewritten — it is labeled INCONSISTENT_AUDIT_STATE rather than
    POSSIBLE_UNDER_PROMOTION, so the contradiction is surfaced, not hidden,
    and is never mistaken for a genuine under-promotion case.
    """
    tier = row.get("tier")
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else {}
    seal = row.get("snipe_confirmed_seal") if isinstance(row.get("snipe_confirmed_seal"), dict) else {}
    sealed_applied = seal.get("applied") is True

    promotion_state = sga.get("promotion_state")
    blocked = _nonempty_list(sga.get("blocked_gate_names")) or _nonempty_list(sga.get("blocked_gates"))
    missing = _nonempty_list(sga.get("missing_proofs"))
    score_blocked = _nonempty_list(sga.get("score_blocked_by"))
    htf_blocks = htf.get("blocks_snipe_contextually") is True
    has_real_blockers = bool(blocked or missing or score_blocked) or htf_blocks

    retest_ok = _is_confirmed(row.get("retest_status"))
    hold_ok = _is_confirmed(row.get("hold_status"))
    one_h_incomplete = not (retest_ok and hold_ok)

    notes: list = []

    # Contextual mentions (do not change the label, but surface the evidence).
    if htf_blocks:
        notes.append("HTF contextual block: weekly/monthly supply/structure blocks SNIPE.")
    if _mentions_candle(blocked) or _mentions_candle(missing):
        notes.append("candle proof blocker: 1H closed-hold / candle truth unresolved.")
    elif one_h_incomplete:
        notes.append(
            f"1H trigger proof incomplete (retest={row.get('retest_status')!r}, hold={row.get('hold_status')!r})."
        )

    # Primary label.
    if sealed_applied and tier in ("NEAR_ENTRY", "STARTER"):
        # Phase 14M.1: a row the Phase 14M seal already downgraded out of
        # SNIPE_IT carries its own seal marker. It is never re-read as
        # ALREADY_SNIPE, INCONSISTENT_SNIPE_CONFIRMED, or an under-promotion
        # candidate — it is the corrected tier truth, sealed down on purpose.
        label = "CORRECT_NEAR_ENTRY" if tier == "NEAR_ENTRY" else "CORRECT_STARTER"
        notes.insert(
            0,
            f"SNIPE confirmation was blocked; final tier was sealed down to {tier} "
            "(Phase 14M seal) — candidate had SNIPE-shaped structure, not a clean SNIPE.",
        )
    elif tier == "SNIPE_IT":
        # Phase 14M: a SNIPE_IT row is only a CLEAN confirmation when no active
        # blocker, missing proof, blocked score, or HTF contextual block
        # remains. Otherwise it is a false SNIPE confirmation (the live FORM
        # contradiction) — surfaced, never read as clean.
        if has_real_blockers:
            label = "INCONSISTENT_SNIPE_CONFIRMED"
            notes.insert(
                0,
                "tier is SNIPE_IT but active SNIPE blockers/missing proofs remain; "
                "not a clean SNIPE confirmation.",
            )
        else:
            label = "SNIPE_CONFIRMED"
    elif promotion_state == "PROMOTION_READY" and not has_real_blockers:
        label = "POSSIBLE_UNDER_PROMOTION"
        notes.insert(0, "snipe_gate_audit.promotion_state == PROMOTION_READY but tier is not SNIPE_IT.")
    elif promotion_state == "PROMOTION_READY":
        # Contradiction: "ready" claimed while an active blocker remains.
        # Treat as blocked, not as under-promotion evidence.
        label = "INCONSISTENT_AUDIT_STATE"
        notes.insert(0, "Promotion state says ready, but active blockers remain; treating as blocked, not under-promotion.")
    elif tier == "STARTER":
        label = "CORRECT_STARTER"
    elif tier == "NEAR_ENTRY":
        label = "CORRECT_NEAR_ENTRY"
    elif tier == "WAIT" and has_real_blockers:
        label = "CORRECTLY_BLOCKED"
    else:
        label = "NEEDS_MANUAL_REVIEW"

    return {"label": label, "notes": notes}


def _mentions_candle(items) -> bool:
    for it in items or []:
        s = (it if isinstance(it, str) else json.dumps(it, default=str)).lower()
        if "candle" in s or "wick" in s or "closed_hold" in s or "closed hold" in s:
            return True
    return False


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_NOT_PERSISTED = "n/a (not persisted in alert_history)"
_NOT_PERSISTED_ROW = "n/a (not persisted on this historical row)"
_TFA_NOT_PERSISTED_ROW = "Phase 14F timeframe_alignment object is not persisted on this historical row."


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        if not value:
            return "—"
        return ", ".join(_fmt_item(x) for x in value)
    return str(value)


def _fmt_item(x) -> str:
    if isinstance(x, dict):
        # Prefer a human gate/name/reason; never dump raw object reprs.
        for key in ("gate", "name", "reason", "label", "trigger"):
            v = x.get(key)
            if isinstance(v, str) and v:
                return v
        return json.dumps(x, default=str)
    return str(x)


def _score_label_suffix(sga: dict) -> str:
    """Phase 14K score-consistency suffix.

    Older (pre-14K) persisted rows lack raw_snipe_score/score_blocked_by —
    in that case this is silent (no claim is made either way). When present,
    a blocked-by gate must never let the score read as a clean, unexplained
    perfect number.
    """
    raw = sga.get("raw_snipe_score")
    blocked_by = _nonempty_list(sga.get("score_blocked_by"))
    if raw is None or not blocked_by:
        return ""
    return f" (raw {raw} pre-block — score blocked by {', '.join(blocked_by)})"


def _format_one_hour_entry_lines(row: dict) -> list:
    oh = row.get("one_hour_entry") if isinstance(row.get("one_hour_entry"), dict) else None
    if oh is None:
        return [
            "__1H ENTRY__ (proxy fields only — full one_hour_entry object is not persisted)",
            f"Status: {_NOT_PERSISTED_ROW}",
            f"Score: {_NOT_PERSISTED_ROW}",
            f"Retest: {_fmt(row.get('retest_status'))}",
            f"Hold: {_fmt(row.get('hold_status'))}",
            f"Candle: {_NOT_PERSISTED_ROW}",
            f"Location: {_NOT_PERSISTED_ROW}",
        ]
    loc = oh.get("location_realism") if isinstance(oh.get("location_realism"), dict) else {}
    candle = oh.get("candle_truth") if isinstance(oh.get("candle_truth"), dict) else {}
    prh = oh.get("pullback_retest_hold") if isinstance(oh.get("pullback_retest_hold"), dict) else {}
    inval = oh.get("invalidation") if isinstance(oh.get("invalidation"), dict) else {}
    path = oh.get("path_quality") if isinstance(oh.get("path_quality"), dict) else {}
    return [
        "__1H ENTRY__",
        f"Status: {_fmt(oh.get('status'))}",
        f"Data freshness: {_fmt(oh.get('data_freshness'))}",
        f"Trigger state: {_fmt(oh.get('trigger_state'))}",
        f"Score: {_fmt(oh.get('score'))} ({_fmt(oh.get('score_label'))})",
        f"Retest: {_fmt(row.get('retest_status'))}",
        f"Hold: {_fmt(row.get('hold_status'))}",
        f"Retest truth: {_fmt(prh.get('retest_truth'))}",
        f"Hold truth: {_fmt(prh.get('hold_truth'))}",
        f"Location: {_fmt(loc.get('label'))}",
        f"Candle: {_fmt(candle.get('event_type'))} (closed confirms: {_fmt(candle.get('closed_candle_confirms'))})",
        f"Invalidation clear: {_fmt(inval.get('clear'))}",
        f"Path label: {_fmt(path.get('path_label'))}",
        f"Hard caps applied: {_fmt(oh.get('hard_caps_applied'))}",
        f"Downgrade reasons: {_fmt(oh.get('downgrade_reasons'))}",
        f"Alert truth label: {_fmt(oh.get('alert_truth_label'))}",
        f"Diagnostic: {_fmt(oh.get('scanner_sentence'))}",
    ]


def _format_timeframe_alignment_lines(row: dict) -> list:
    tfa = row.get("timeframe_alignment") if isinstance(row.get("timeframe_alignment"), dict) else None
    if tfa is None:
        return [
            "__TIMEFRAME ALIGNMENT__",
            f"  ({_TFA_NOT_PERSISTED_ROW})",
        ]
    campaign = tfa.get("campaign_timeframe") if isinstance(tfa.get("campaign_timeframe"), dict) else {}
    swing = tfa.get("swing_timeframe") if isinstance(tfa.get("swing_timeframe"), dict) else {}
    operational = tfa.get("operational_timeframe") if isinstance(tfa.get("operational_timeframe"), dict) else {}
    trigger = tfa.get("trigger_timeframe") if isinstance(tfa.get("trigger_timeframe"), dict) else {}
    return [
        "__TIMEFRAME ALIGNMENT__",
        f"Status: {_fmt(tfa.get('status'))}",
        f"Alignment grade / score: {_fmt(tfa.get('alignment_grade'))} / {_fmt(tfa.get('alignment_score'))}",
        f"Alignment label: {_fmt(tfa.get('alignment_label'))}",
        f"Campaign (1W) state: {_fmt(campaign.get('state'))}",
        f"Swing (1D) permission: {_fmt(swing.get('state'))}",
        f"Operational (4H) location: {_fmt(operational.get('state'))}",
        f"Trigger (1H) proof: {_fmt(trigger.get('state'))}",
        f"Conflicts: {_fmt(tfa.get('conflicts'))}",
        f"Missing context: {_fmt(tfa.get('missing_context'))}",
        f"Diagnostic: {_fmt(tfa.get('scanner_sentence'))}",
    ]


def format_row(row: dict) -> str:
    """Render one alert_history row as compact, sectioned audit text."""
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else {}
    verdict = interpret(row)

    grade_score = f"{_fmt(htf.get('context_grade'))} / {_fmt(htf.get('context_score'))}" if htf else "—"

    lines = [
        f"**AUDIT ROW — {_fmt(row.get('ticker'))} `{_fmt(row.get('scan_id'))}`**",
        f"Ticker: {_fmt(row.get('ticker'))}",
        f"Scan ID: {_fmt(row.get('scan_id'))}",
        f"Timestamp: {_fmt(row.get('alerted_at'))}",
        f"Final tier: {_fmt(row.get('tier'))}",
        f"Capital action: {_fmt(row.get('capital_action'))}",
        f"Score: {_fmt(row.get('score'))}",
        f"Signal channel: {_fmt(row.get('final_discord_channel'))}",
        "",
        *_format_one_hour_entry_lines(row),
        "",
        *_format_timeframe_alignment_lines(row),
        "",
        "__SNIPE GATE AUDIT__",
        f"Audit label: {_fmt(sga.get('audit_label'))}",
        f"Promotion state: {_fmt(sga.get('promotion_state'))}",
        f"SNIPE score: {_fmt(sga.get('snipe_score'))}{_score_label_suffix(sga)}",
        f"SNIPE grade: {_fmt(sga.get('snipe_grade'))}",
        f"Eligible for SNIPE review: {_fmt(sga.get('eligible_for_snipe_review'))}",
        f"Blocked gates: {_fmt(sga.get('blocked_gate_names'))}",
        f"Missing proofs: {_fmt(sga.get('missing_proofs'))}",
        f"Promotion triggers: {_fmt(sga.get('promotion_triggers'))}",
        f"Blocking reasons: {_fmt(sga.get('blocking_reasons'))}",
        f"Diagnostic: {_fmt(sga.get('diagnostic_sentence'))}",
        "",
        "__HIGHER TIMEFRAME CONTEXT__",
        f"Data status: {_fmt(htf.get('data_status'))}",
        f"Monthly bias: {_fmt(htf.get('monthly_bias_state'))}",
        f"Weekly campaign: {_fmt(htf.get('weekly_campaign_state'))}",
        f"Campaign location: {_fmt(htf.get('campaign_location_label'))}",
        f"Location quality: {_fmt(htf.get('campaign_location_quality'))}",
        f"Context grade / score: {grade_score}",
        f"Supports long: {_fmt(htf.get('supports_long_setup'))}",
        f"Weakens long: {_fmt(htf.get('weakens_long_setup'))}",
        f"Blocks SNIPE contextually: {_fmt(htf.get('blocks_snipe_contextually'))}",
        f"Promotion support: {_fmt(htf.get('promotion_support'))}",
        f"Missing HTF proof: {_fmt(htf.get('missing_htf_proof'))}",
        f"Blocking reasons: {_fmt(htf.get('blocking_reasons'))}",
        f"Diagnostic: {_fmt(htf.get('diagnostic_sentence'))}",
        "",
        "__CONCLUSION__",
        f"{verdict['label']}" + (f" — {' '.join(verdict['notes'])}" if verdict["notes"] else ""),
    ]
    return "\n".join(lines)


def compact_json(row: dict) -> dict:
    """Sanitized compact JSON view (whitelist only — never raw state/secrets)."""
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else None
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else None
    oh = row.get("one_hour_entry") if isinstance(row.get("one_hour_entry"), dict) else None
    tfa = row.get("timeframe_alignment") if isinstance(row.get("timeframe_alignment"), dict) else None
    verdict = interpret(row)
    return {
        "ticker": row.get("ticker"),
        "scan_id": row.get("scan_id"),
        "alerted_at": row.get("alerted_at"),
        "tier": row.get("tier"),
        "capital_action": row.get("capital_action"),
        "score": row.get("score"),
        "final_discord_channel": row.get("final_discord_channel"),
        "retest_status": row.get("retest_status"),
        "hold_status": row.get("hold_status"),
        "snipe_gate_audit": sga,
        "higher_timeframe_context": htf,
        "one_hour_entry": oh,
        "timeframe_alignment": tfa,
        "conclusion": verdict["label"],
        "conclusion_notes": verdict["notes"],
    }


def _chunk(text: str, max_len: int = _DISCORD_MAX_CHARS) -> list:
    """Local line-aware chunker (keeps this module Discord-import-free)."""
    if len(text) <= max_len:
        return [text]
    chunks, cur, cur_len = [], [], 0
    for line in text.split("\n"):
        while len(line) > max_len:
            chunks.append(line[:max_len])
            line = line[max_len:]
        add = len(line) + 1
        if cur_len + add > max_len and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def run_audit(config: dict, args, user_id=None, channel_id=None) -> dict:
    """Resolve and render an audit request. READ-ONLY.

    args: the raw argument string after `!audit` (e.g. "HAE", "scan_... json").

    Returns:
      {"ok": bool, "messages": list[str], "error": str|None,
       "match_count": int, "json": <obj|None>}
    messages is always a Discord-length-safe list (possibly one element).
    """
    # Permission first — never reveal data to an unauthorized caller.
    auth = is_authorized(config, user_id=user_id, channel_id=channel_id)
    if not auth["allowed"]:
        return _err("unauthorized", f"Audit access denied: {auth['reason']}.")

    tokens = (args or "").split()
    if not tokens:
        return _err("usage", "Usage: `!audit <scan_id|TICKER> [json]`  e.g. `!audit HAE` or `!audit scan_20260622_164918_4fc48e`")

    json_mode = False
    if tokens and tokens[-1].lower() == "json":
        json_mode = True
        tokens = tokens[:-1]
    if not tokens:
        return _err("usage", "Usage: `!audit <scan_id|TICKER> [json]`")

    kind, value = parse_query(tokens[0])
    if kind == "invalid":
        return _err("bad_query", f"Could not parse `{tokens[0]}` as a scan_id or ticker.")

    loaded = load_state_readonly(config)
    if not loaded["ok"]:
        return _err(loaded["error"], loaded["message"])
    state = loaded["state"]

    max_rows = int(_audit_cfg(config).get("max_rows", _DEFAULT_MAX_ROWS) or _DEFAULT_MAX_ROWS)

    if kind == "scan_id":
        rows = find_by_scan_id(state, value)
        if not rows:
            return _err("not_found", f"No alert_history row found with scan_id `{value}`.")
    else:
        rows = find_by_ticker(state, value, max_rows=max_rows)
        if not rows:
            return _err("not_found", f"No alert_history rows found for ticker `{value}`.")
        if len(rows) > max_rows:
            return _err(
                "too_many",
                f"{len(rows)} rows for `{value}` — narrow with a scan_id, or showing the latest {max_rows}.",
            )

    if json_mode:
        payload = [compact_json(r) for r in rows]
        text = "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"
        return {"ok": True, "error": None, "match_count": len(rows),
                "json": payload, "messages": _chunk(text)}

    body = ("\n\n" + ("—" * 8) + "\n\n").join(format_row(r) for r in rows)
    header = f"**Audit: {kind} `{value}` — {len(rows)} row(s)**\n\n"
    return {"ok": True, "error": None, "match_count": len(rows),
            "json": None, "messages": _chunk(header + body)}


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "match_count": 0, "json": None, "messages": [message]}


# ===========================================================================
# Phase 14L — AuditReady under-promotion radar
# ===========================================================================
#
# !auditready scans recent alert_history rows for TRUE possible under-promotion:
# a setup the SNIPE gate audit calls PROMOTION_READY (eligible, no blockers, no
# missing proofs, no HTF contextual block) that the scanner nonetheless did not
# promote to SNIPE_IT. It is a radar over the existing Phase 14J/14K evidence —
# it reuses the same read-only state loader, the same permission gate, and the
# same interpret() conclusion. It changes no tiering/scoring/routing/capital
# logic and never mutates state. If it is noisy, it failed: a row is only a
# candidate when interpret() == POSSIBLE_UNDER_PROMOTION AND no active blocker
# is found by any structured or hard-text signal.

_AUDITREADY_DEFAULT_SCAN_ROWS = 100
_AUDITREADY_MIN_SCAN_ROWS = 10
_AUDITREADY_MAX_SCAN_ROWS = 300
_AUDITREADY_MAX_CANDIDATES = 10

# capital_action values that mean full SNIPE-size capital was already granted —
# such a row is not "under-promoted" by definition.
_FULL_SNIPE_CAPITAL = {"full_snipe", "full_quality_allowed", "full", "snipe"}

# Non-tradeable / non-candidate tiers.
#
# WATCHLIST is intentionally NOT in this set. A WATCHLIST row whose
# snipe_gate_audit is genuinely PROMOTION_READY with zero active blockers is
# itself an audit contradiction (clean readiness sitting on the lowest tier)
# and must be surfaced like any other under-promotion candidate, not hidden
# behind a tier assumption. It passes through the identical strict gate below
# as STARTER/NEAR_ENTRY — no loosened blockers, no special-cased interpret().
_NON_CANDIDATE_TIERS = {"SNIPE_IT", "PASS", "WAIT", ""}

# Benign, explicitly-non-blocking diagnostic text the 14K seal appends to a
# genuinely clean PROMOTION_READY row. These must NOT count as active blockers.
_BENIGN_REASON_MARKERS = (
    "appear complete but final_tier is not snipe_it",
    "downgraded from promotion_ready to promotion_pending",
)

# Full blocker vocabulary — applied ONLY to blocking_reasons AFTER benign
# markers are filtered out (so the clean integrity note never trips it).
_TEXT_BLOCKER_TERMS = (
    "blocked", "blocker", "missing", "waits for", "pending", "not confirmed",
    "not clean", "unresolved", "hostile wick", "candle veto", "failed retest",
    "no fresh aggression", "hold weak", "hold partial", "trigger forming",
    "no valid 1h", "proof incomplete", "full-size confirmation not granted",
)

# Hard blocker vocabulary — safe to scan the generic diagnostic_sentence with,
# because (unlike "waits for"/"missing"/"pending") none of these terms appear in
# the benign STARTER/NEAR_ENTRY boilerplate that a clean candidate still carries
# (e.g. "starter valid, but SNIPE promotion waits for 1H closed-hold proof").
_HARD_BLOCKER_TERMS = (
    "hostile wick", "candle veto", "failed retest", "no fresh aggression",
    "hold weak", "hold partial", "trigger forming", "no valid 1h",
    "proof incomplete", "not confirmed", "not clean", "unresolved",
    "blocked by", "full-size confirmation not granted",
)

_GRADE_RANK = {
    "A+": 0, "A": 1, "A-": 2, "B+": 3, "B": 4, "B-": 5,
    "C+": 6, "C": 7, "C-": 8, "D": 9, "F": 10, "UNKNOWN": 11,
}


def _row_ts(row: dict) -> str:
    """Sortable timestamp string (ISO timestamps sort lexicographically)."""
    if not isinstance(row, dict):
        return ""
    return str(row.get("timestamp") or row.get("alerted_at") or row.get("scan_time") or "")


def _row_ticker(row: dict, parent: str = None) -> str:
    if isinstance(row, dict) and row.get("ticker"):
        return str(row.get("ticker"))
    return str(parent or "?")


def _row_final_tier(row: dict) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("final_tier") or row.get("tier") or "").upper().strip()


def _num(value) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if f == f else 0.0     # NaN -> 0


def _has_term(text, terms) -> bool:
    if not isinstance(text, str):
        return False
    low = text.lower()
    return any(t in low for t in terms)


def _nonbenign_reasons(value) -> list:
    """blocking_reasons strings with the 14K benign seal/integrity notes removed."""
    out = []
    if not isinstance(value, list):
        return out
    for item in value:
        s = item if isinstance(item, str) else (
            _fmt_item(item) if isinstance(item, dict) else None
        )
        if not isinstance(s, str) or not s:
            continue
        low = s.lower()
        if any(marker in low for marker in _BENIGN_REASON_MARKERS):
            continue
        out.append(s)
    return out


def collect_recent_rows(state: dict, limit: int = _AUDITREADY_DEFAULT_SCAN_ROWS) -> list:
    """Flatten alert_history rows across all tickers, newest first, capped at
    `limit`. Read-only: a row missing its own `ticker` key is shallow-copied with
    the parent ticker filled in (the source state dict is never mutated)."""
    rows = []
    tickers = (state or {}).get("tickers") or {}
    if not isinstance(tickers, dict):
        return []
    for tkey, tstate in tickers.items():
        if not isinstance(tstate, dict):
            continue
        history = tstate.get("alert_history")
        if not isinstance(history, list):
            continue
        for row in history:
            if not isinstance(row, dict):
                continue
            if not row.get("ticker"):
                row = {**row, "ticker": tkey}     # shallow copy; no source mutation
            rows.append(row)
    rows.sort(key=_row_ts, reverse=True)
    n = max(1, int(limit or _AUDITREADY_DEFAULT_SCAN_ROWS))
    return rows[:n]


def active_blockers(row: dict) -> list:
    """Return human-readable active-blocker reasons for a row; empty == clean.

    Reads BOTH structured fields (authoritative) and hard text signals. Treats
    the 14K benign integrity/seal notes as non-blocking, and never scans
    promotion_triggers (a trigger like "avoid body close below invalidation" is
    guidance, not a blocker). Errs strict: any signal of an unresolved blocker
    disqualifies the row.
    """
    reasons = []
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else {}

    if _nonempty_list(sga.get("blocked_gate_names")):
        reasons.append(f"blocked gates: {', '.join(_fmt_item(x) for x in sga['blocked_gate_names'])}")
    if _nonempty_list(sga.get("blocked_gates")):
        reasons.append("blocked_gates present")
    if _nonempty_list(sga.get("missing_proofs")):
        reasons.append(f"missing proofs: {', '.join(_fmt_item(x) for x in sga['missing_proofs'])}")
    if _nonempty_list(sga.get("score_blocked_by")):
        reasons.append(f"score blocked by: {', '.join(_fmt_item(x) for x in sga['score_blocked_by'])}")
    if htf.get("blocks_snipe_contextually") is True:
        reasons.append("HTF contextual block (weekly/monthly supply/structure)")

    for r in _nonbenign_reasons(sga.get("blocking_reasons")):
        if _has_term(r, _TEXT_BLOCKER_TERMS):
            reasons.append(f"blocking reason: {r}")

    diag = sga.get("diagnostic_sentence")
    if _has_term(diag, _HARD_BLOCKER_TERMS):
        reasons.append(f"diagnostic blocker: {diag}")

    return reasons


def is_auditready_candidate(row: dict):
    """Return (is_candidate: bool, reasons: list[str]).

    For a non-candidate, reasons explains WHY it failed (diagnostic). For a
    candidate, reasons holds the explicit "why flagged" justification.
    """
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else None
    seal = row.get("snipe_confirmed_seal") if isinstance(row.get("snipe_confirmed_seal"), dict) else None
    final_tier = _row_final_tier(row)
    capital = str(row.get("capital_action") or "").lower().strip()

    fails = []
    if isinstance(seal, dict) and seal.get("applied") is True:
        # Phase 14M.1: a row the Phase 14M seal sealed down out of SNIPE_IT is
        # never a "possible under-promotion" — it was already corrected, on
        # purpose, for a documented reason.
        fails.append("snipe_confirmed_seal.applied is true (Phase 14M sealed-down row)")
    if final_tier in _NON_CANDIDATE_TIERS:
        fails.append(f"tier {final_tier or 'unknown'} is not an under-promotion candidate")
    if capital in _FULL_SNIPE_CAPITAL:
        fails.append(f"capital_action {capital} is already full size")
    if not sga:
        fails.append("no snipe_gate_audit snapshot")
    else:
        if sga.get("eligible_for_snipe_review") is not True:
            fails.append("not eligible_for_snipe_review")
        if sga.get("promotion_state") != "PROMOTION_READY":
            fails.append(f"promotion_state {sga.get('promotion_state')} != PROMOTION_READY")

    fails.extend(active_blockers(row))

    if interpret(row)["label"] != "POSSIBLE_UNDER_PROMOTION":
        fails.append("audit interpretation is not POSSIBLE_UNDER_PROMOTION")

    if fails:
        return False, fails

    why = [
        "promotion_state is PROMOTION_READY, no blocked gates, no missing "
        f"proofs, no active blockers, but final_tier is {final_tier}.",
    ]
    return True, why


def _candidate_priority(row: dict) -> str:
    """Audit-severity label only — never implies capital/trading permission."""
    tier = _row_final_tier(row)
    if tier == "WATCHLIST":
        return "REVIEW PRIORITY"
    if tier == "NEAR_ENTRY":
        return "HIGH REVIEW PRIORITY"
    return "PRIORITY"


def _candidate_eff_score(row: dict) -> float:
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    eff = sga.get("effective_snipe_score")
    if eff is None:
        eff = sga.get("snipe_score")
    return _num(eff)


def _candidate_grade_rank(row: dict) -> int:
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    return _GRADE_RANK.get(str(sga.get("snipe_grade") or "UNKNOWN").upper(), _GRADE_RANK["UNKNOWN"])


def _rank_candidates(candidates: list) -> list:
    """candidates: list[(row, why)]. Rank: higher effective score, then better
    grade, then newer timestamp. Python's stable sort lets us layer these."""
    ranked = sorted(candidates, key=lambda rw: _row_ts(rw[0]), reverse=True)        # newest first
    ranked.sort(key=lambda rw: (-_candidate_eff_score(rw[0]), _candidate_grade_rank(rw[0])))
    return ranked


def _empty_counts() -> dict:
    return {
        "SNIPE_CONFIRMED": 0, "CORRECT_STARTER": 0, "CORRECT_NEAR_ENTRY": 0,
        "INCONSISTENT_AUDIT_STATE": 0, "INCONSISTENT_SNIPE_CONFIRMED": 0,
        "POSSIBLE_UNDER_PROMOTION": 0,
        "CORRECTLY_BLOCKED": 0, "NEEDS_MANUAL_REVIEW": 0,
    }


def _empty_promo_counts() -> dict:
    return {
        "PROMOTION_READY": 0, "PROMOTION_PENDING": 0, "PROMOTION_BLOCKED": 0,
        "ALREADY_SNIPE": 0, "NOT_ELIGIBLE": 0, "UNKNOWN": 0,
    }


def _auditready_candidate_json(row: dict, why: list) -> dict:
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else {}
    return {
        "ticker": _row_ticker(row),
        "scan_id": row.get("scan_id"),
        "timestamp": _row_ts(row) or None,
        "final_tier": _row_final_tier(row),
        "capital_action": row.get("capital_action"),
        "score": row.get("score"),
        "snipe_score": sga.get("snipe_score"),
        "raw_snipe_score": sga.get("raw_snipe_score"),
        "effective_snipe_score": sga.get("effective_snipe_score"),
        "score_blocked_by": sga.get("score_blocked_by"),
        "display_score_label": sga.get("display_score_label"),
        "snipe_grade": sga.get("snipe_grade"),
        "promotion_state": sga.get("promotion_state"),
        "audit_label": sga.get("audit_label"),
        "blocks_snipe_contextually": htf.get("blocks_snipe_contextually"),
        "conclusion": "POSSIBLE_UNDER_PROMOTION",
        "priority": _candidate_priority(row),
        "why_flagged": why,
    }


def _fmt_score_line(row: dict) -> str:
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    raw = sga.get("raw_snipe_score")
    eff = sga.get("effective_snipe_score")
    if eff is not None and raw is not None and eff != raw:
        return f"{_fmt(eff)} (raw {_fmt(raw)})"
    if eff is not None:
        return _fmt(eff)
    return _fmt(sga.get("snipe_score"))


def _render_candidate(idx: int, row: dict, why: list) -> str:
    sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
    htf = row.get("higher_timeframe_context") if isinstance(row.get("higher_timeframe_context"), dict) else {}
    tier = _row_final_tier(row)
    priority = _candidate_priority(row)
    htf_ctx = (
        f"{_fmt(htf.get('weekly_campaign_state'))} / {_fmt(htf.get('campaign_location_label'))} "
        f"({_fmt(htf.get('campaign_location_quality'))})" if htf else "—"
    )
    if tier == "WATCHLIST":
        note_label = "Review note"
        review = (
            "WATCHLIST with clean PROMOTION_READY is an audit contradiction, not "
            "capital permission. Review the scan_id with !audit before any "
            "doctrine conclusion."
        )
    elif tier == "NEAR_ENTRY":
        note_label = "Upgrade / review note"
        review = (
            "NEAR_ENTRY with a fully ready SNIPE audit and zero blockers — review "
            "for promotion urgently."
        )
    else:
        note_label = "Upgrade / review note"
        review = "STARTER with a fully ready SNIPE audit and zero blockers — review for promotion."
    return "\n".join([
        f"**Candidate #{idx} — {_row_ticker(row)}**  [{priority}]",
        f"Scan ID: {_fmt(row.get('scan_id'))}",
        f"Timestamp: {_fmt(_row_ts(row) or None)}",
        f"Final tier: {_fmt(tier)}",
        f"Capital action: {_fmt(row.get('capital_action'))}",
        f"Score: {_fmt(row.get('score'))}",
        f"SNIPE score: {_fmt_score_line(row)}",
        f"SNIPE grade: {_fmt(sga.get('snipe_grade'))}",
        f"Promotion state: {_fmt(sga.get('promotion_state'))}",
        f"Audit label: {_fmt(sga.get('audit_label'))}",
        f"HTF context: {htf_ctx}",
        "Conclusion: POSSIBLE_UNDER_PROMOTION",
        f"Why flagged: {' '.join(why)}",
        f"{note_label}: {review}",
        f"Command: !audit {_fmt(row.get('scan_id'))}",
    ])


def _render_auditready_candidates(meta: dict, counts: dict, candidates: list) -> str:
    head = [
        "**AUDITREADY — POSSIBLE UNDER-PROMOTION CANDIDATES**",
        f"Rows scanned: {meta['rows_scanned']}",
        f"Candidates found: {meta['candidates_found']}",
        f"Newest timestamp inspected: {_fmt(meta['newest'])}",
        f"Oldest timestamp inspected: {_fmt(meta['oldest'])}",
        "",
    ]
    blocks = [_render_candidate(i + 1, row, why) for i, (row, why) in enumerate(candidates)]
    return "\n".join(head) + "\n\n".join(blocks)


def _render_auditready_clear(meta: dict, counts: dict, promo_counts: dict) -> str:
    return "\n".join([
        "**AUDITREADY — CLEAR**",
        f"Rows scanned: {meta['rows_scanned']}",
        f"Newest row: {_fmt(meta['newest'])}",
        f"Oldest row: {_fmt(meta['oldest'])}",
        f"SNIPE_CONFIRMED: {counts['SNIPE_CONFIRMED']}",
        f"CORRECT_STARTER: {counts['CORRECT_STARTER']}",
        f"CORRECT_NEAR_ENTRY: {counts['CORRECT_NEAR_ENTRY']}",
        f"INCONSISTENT_AUDIT_STATE: {counts['INCONSISTENT_AUDIT_STATE']}",
        f"PROMOTION_PENDING: {promo_counts['PROMOTION_PENDING']}",
        f"PROMOTION_BLOCKED: {promo_counts['PROMOTION_BLOCKED']}",
        "POSSIBLE_UNDER_PROMOTION: 0",
        "",
        "Interpretation:",
        "No true under-promotion candidates found. Scanner is not currently "
        "showing evidence of SNIPE suppression in the inspected window.",
        "",
        "Next:",
        "Continue monitoring. Use `!audit <scan_id|TICKER>` on any individual "
        "alert you want to inspect.",
    ])


def build_auditready_report(config: dict, limit: int = _AUDITREADY_DEFAULT_SCAN_ROWS,
                            json_mode: bool = False) -> dict:
    """Scan recent rows and render the radar result. READ-ONLY."""
    loaded = load_state_readonly(config)
    if not loaded["ok"]:
        if loaded["error"] == "state_file_not_found":
            msg = (
                "AUDITREADY unavailable — alert_history state file not found.\n"
                "This command must run inside the live production bot container "
                "with access to `.state/alert_history.json`."
            )
        elif loaded["error"] == "state_file_malformed":
            msg = (
                "AUDITREADY unavailable — alert_history state file could not be "
                "parsed.\nNo state was modified."
            )
        else:
            msg = f"AUDITREADY unavailable — {loaded['message']}"
        return _err(loaded["error"], msg)

    state = loaded["state"]
    cfg = _audit_cfg(config)
    max_candidates = int(cfg.get("auditready_max_candidates", _AUDITREADY_MAX_CANDIDATES)
                         or _AUDITREADY_MAX_CANDIDATES)

    rows = collect_recent_rows(state, limit)
    counts = _empty_counts()
    promo_counts = _empty_promo_counts()
    found = []
    for row in rows:
        label = interpret(row)["label"]
        counts[label] = counts.get(label, 0) + 1
        sga = row.get("snipe_gate_audit") if isinstance(row.get("snipe_gate_audit"), dict) else {}
        promo = sga.get("promotion_state")
        if promo:
            promo_counts[promo] = promo_counts.get(promo, 0) + 1
        ok, why = is_auditready_candidate(row)
        if ok:
            found.append((row, why))

    found = _rank_candidates(found)[:max_candidates]
    meta = {
        "rows_scanned": len(rows),
        "newest": (_row_ts(rows[0]) or None) if rows else None,
        "oldest": (_row_ts(rows[-1]) or None) if rows else None,
        "candidates_found": len(found),
    }

    if json_mode:
        payload = [_auditready_candidate_json(row, why) for (row, why) in found]
        text = "```json\n" + json.dumps(
            {"meta": meta, "counts": counts, "candidates": payload},
            indent=2, default=str,
        ) + "\n```"
        return {"ok": True, "error": None, "match_count": len(found),
                "json": payload, "messages": _chunk(text)}

    if not found:
        text = _render_auditready_clear(meta, counts, promo_counts)
    else:
        text = _render_auditready_candidates(meta, counts, found)
    return {"ok": True, "error": None, "match_count": len(found),
            "json": None, "messages": _chunk(text)}


def run_auditready(config: dict, args=None, user_id=None, channel_id=None) -> dict:
    """Top-level !auditready handler. READ-ONLY.

    args: raw string after `!auditready`, or a token list. Recognizes an optional
    numeric row-limit (clamped to 10..300) and an optional `json` flag.
    """
    auth = is_authorized(config, user_id=user_id, channel_id=channel_id)
    if not auth["allowed"]:
        return _err("unauthorized", f"Audit access denied: {auth['reason']}.")

    if isinstance(args, str):
        tokens = args.split()
    elif isinstance(args, (list, tuple)):
        tokens = [str(t) for t in args]
    else:
        tokens = []

    json_mode = False
    limit = None
    for tok in tokens:
        t = str(tok).strip().lower()
        if not t:
            continue
        if t == "json":
            json_mode = True
        elif t.isdigit():
            limit = int(t)
        else:
            return _err(
                "usage",
                "Usage: `!auditready [rows 10-300] [json]`  e.g. `!auditready`, "
                "`!auditready 50`, `!auditready json`",
            )

    cfg = _audit_cfg(config)
    default_rows = int(cfg.get("auditready_default_scan_rows", _AUDITREADY_DEFAULT_SCAN_ROWS)
                       or _AUDITREADY_DEFAULT_SCAN_ROWS)
    max_rows = int(cfg.get("auditready_max_scan_rows", _AUDITREADY_MAX_SCAN_ROWS)
                   or _AUDITREADY_MAX_SCAN_ROWS)
    if limit is None:
        limit = default_rows
    limit = max(_AUDITREADY_MIN_SCAN_ROWS, min(limit, max_rows))

    return build_auditready_report(config, limit=limit, json_mode=json_mode)

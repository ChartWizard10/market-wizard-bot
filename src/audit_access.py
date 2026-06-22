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
  - The FULL one_hour_entry and timeframe_alignment objects are NOT persisted in
    alert_history. Only `retest_status`/`hold_status` survive as 1H proxies; the
    14F timeframe_alignment object is not persisted at all. Those sub-fields are
    reported as "not persisted in alert_history" rather than invented.
  - Persisted evidence snapshots: `snipe_gate_audit` (Phase 14H.1 compact) and
    `higher_timeframe_context` (Phase 14I compact).
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

    promotion_state = sga.get("promotion_state")
    blocked = _nonempty_list(sga.get("blocked_gate_names")) or _nonempty_list(sga.get("blocked_gates"))
    missing = _nonempty_list(sga.get("missing_proofs"))
    htf_blocks = htf.get("blocks_snipe_contextually") is True
    has_real_blockers = bool(blocked or missing) or htf_blocks

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
    if tier == "SNIPE_IT":
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
        "__1H ENTRY__ (proxy fields only — full one_hour_entry object is not persisted)",
        f"Status: {_NOT_PERSISTED}",
        f"Score: {_NOT_PERSISTED}",
        f"Retest: {_fmt(row.get('retest_status'))}",
        f"Hold: {_fmt(row.get('hold_status'))}",
        f"Candle: {_NOT_PERSISTED}",
        f"Location: {_NOT_PERSISTED}",
        "",
        "__TIMEFRAME ALIGNMENT__",
        "  (Phase 14F timeframe_alignment object is not persisted in alert_history — live tiering_result only)",
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

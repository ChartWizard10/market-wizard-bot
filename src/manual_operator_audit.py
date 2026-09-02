"""Phase 14X — full manual !analyze operator audit renderer.

A pure, read-only PRESENTATION layer over the completed result of
``scheduler.run_analyze()``. The production judgment engine (Claude analysis,
deterministic tiering, trajectory, trade location, candle truth, 1H entry,
timeframe alignment, real 4H, higher-timeframe context, SNIPE gate audit,
ladder arbitration, the downgrade-only seal, audit reconciliation, score
calibration) already runs exactly once inside ``scheduler.run_analyze`` —
see Phase 14W (``tests/test_phase_14w_manual_analyze_parity.py``), which
proves autoscan and manual !analyze share one named judgment organ.

This module NEVER re-runs, re-derives, or second-guesses that judgment. It is
an OBSERVER: given the already-completed ``result`` dict (as returned by
``run_analyze``), it renders the full operator audit the doctrine spec
requires. It never fetches market/1H/4H data, never calls Claude/Anthropic,
never runs indicators/prefilter/tiering/ladder/seal, never writes state,
never sends a Discord alert, and never mutates its input.

Hard guarantees (mirrors src/audit_access.py's documented contract):
  - The renderer is pure/read-only. It uses stdlib (json, re),
    src.display_formatting.format_usd_price (itself pure/stdlib), and exactly
    ONE narrowly-scoped exception: the canonical, pure
    higher_timeframe_context.compact_history_snapshot(htf) serializer (Phase
    14X.2), used solely to normalize the live nested HTF evidence object into
    the same flat shape as its persisted snapshot — never a hand-rolled
    parallel mapping that could drift from production's own serialization.
    That single call performs no market/network/clock access, computes no
    judgment, and mutates nothing; it only reshapes fields the HTF engine has
    already computed. This module still never invokes an HTF (or any other)
    EVIDENCE BUILDER, never runs indicators/prefilter/tiering/ladder/seal,
    never writes state, never sends a Discord alert, and never mutates its
    input. No other scanner/tiering/market-data/Discord/network imports.
  - Every accessor is a defensive `.get()` read; nothing here can raise on a
    partial/missing sub-object, and nothing here writes back into `result`.
  - A missing/unavailable datum renders as "—" or an explicit "UNAVAILABLE"
    label — never a fabricated $0.00, 0%, False, or "failed".
  - MISSING proof (not yet attempted) is always kept distinct from BROKEN /
    FAILED proof (attempted and did not hold) — see `_proof_state_of`.
"""

import json
import re

from src.display_formatting import format_usd_price

# ---------------------------------------------------------------------------
# Local, self-contained text hygiene (mirrors src/audit_access.py's convention
# of not importing src.discord_alerts's private helpers — this module stays
# independently testable and dependency-free of the alert-formatting layer).
# ---------------------------------------------------------------------------

_MENTION_RE = re.compile(r"@(everyone|here)", re.IGNORECASE)
_ROLE_USER_MENTION_RE = re.compile(r"<@[!&]?\d+>")

_UNAVAILABLE = "UNAVAILABLE"
_DASH = "—"

_DISCORD_MAX_CHARS = 1900  # conservative, matches audit_access._DISCORD_MAX_CHARS


def _sanitize(text) -> str:
    """Neutralize @everyone/@here and role/user mentions. Never raises."""
    if not text:
        return ""
    s = str(text)
    s = _MENTION_RE.sub(lambda m: "@​" + m.group(1), s)
    s = _ROLE_USER_MENTION_RE.sub("[mention]", s)
    return s


def _fmt(v, placeholder: str = _DASH) -> str:
    """Generic scalar formatter. None/blank -> placeholder; never invents 0/False."""
    if v is None:
        return placeholder
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        s = v.strip()
        return s if s else placeholder
    if isinstance(v, list):
        return ", ".join(_fmt_item(x) for x in v) if v else placeholder
    return str(v)


def _fmt_item(x) -> str:
    if isinstance(x, dict):
        for key in ("gate", "name", "reason", "label", "trigger"):
            v = x.get(key)
            if isinstance(v, str) and v:
                return v
        return json.dumps(x, default=str)
    return str(x)


def _fmt_price(v) -> str:
    """Dollar-formatted price, or '—' — never a fabricated $0.00."""
    if v is None:
        return _DASH
    try:
        return format_usd_price(float(v))
    except (TypeError, ValueError):
        return _DASH


def _is_finite(f: float) -> bool:
    return f == f and f not in (float("inf"), float("-inf"))  # noqa: PLR0124 (NaN self-compare)


def _fmt_pct(v) -> str:
    if v is None:
        return _DASH
    try:
        f = float(v)
        if not _is_finite(f):
            return _DASH
        return f"{f:.2f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_ratio(v) -> str:
    if v is None:
        return _DASH
    try:
        f = float(v)
        if not _is_finite(f):
            return _DASH
        return f"{f:.2f}:1"
    except (TypeError, ValueError):
        return _DASH


def _safe_dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _safe_list(v) -> list:
    return v if isinstance(v, list) else []


def _nonempty(v) -> list:
    return [x for x in _safe_list(v) if x not in (None, "", [])]


_LIQUIDITY_KEYWORDS = ("liquidity", "pool", "sweep")


def _mentions_liquidity(text) -> bool:
    if not isinstance(text, str):
        return False
    low = text.lower()
    return any(kw in low for kw in _LIQUIDITY_KEYWORDS)


# ---------------------------------------------------------------------------
# Capital / tier display labels (mirrors src/discord_alerts._CAPITAL_LABEL —
# duplicated locally, display-only, so this renderer stays import-independent
# of the alert-formatting module per the audit_access.py self-contained
# convention documented above).
# ---------------------------------------------------------------------------

_CAPITAL_LABEL = {
    "full_quality_allowed": "FULL-SIZE AUTHORIZED",
    "starter_only":         "STARTER SIZE ONLY",
    "wait_no_capital":      "NO CAPITAL — WATCH ONLY",
    "no_trade":             "NO TRADE",
}

_CAPITAL_READINESS = {
    "SNIPE_IT":   "FULL",
    "STARTER":    "STARTER",
    "NEAR_ENTRY": "NONE",
    "WAIT":       "NONE",
}

_TIER_BADGE = {
    "SNIPE_IT":   "🔴 SNIPE IT",
    "STARTER":    "🟡 STARTER",
    "NEAR_ENTRY": "🟢 NEAR ENTRY",
    "WAIT":       "⚪ WAIT",
}

_TIER_ORDER = ["WAIT", "NEAR_ENTRY", "STARTER", "SNIPE_IT"]

# retest/hold-status style proof-state enums -> a MISSING vs BROKEN/FAILED
# vs CONFIRMED vs FORMING classification. This distinction is a locked law —
# absence of proof is never displayed as failure.
_PROOF_MISSING_TOKENS = {"missing", "none", "", "unknown", "n/a"}
_PROOF_PARTIAL_TOKENS = {"partial", "forming"}
_PROOF_FAILED_TOKENS = {"failed", "broken"}
_PROOF_CONFIRMED_TOKENS = {"confirmed", "true", "yes", "hold_confirmed", "retest_confirmed"}


def _proof_state_of(value) -> str:
    """Classify a raw proof-status token into CONFIRMED/FORMING/MISSING/BROKEN.

    Reads the value's own enum literally — never infers failure from absence.
    """
    s = str(value or "").strip().lower()
    if s in _PROOF_CONFIRMED_TOKENS:
        return "CONFIRMED"
    if s in _PROOF_FAILED_TOKENS:
        return "BROKEN"
    if s in _PROOF_PARTIAL_TOKENS:
        return "FORMING"
    return "MISSING"


_PROOF_ICON = {
    "CONFIRMED": "✅",
    "FORMING":   "🟡",
    "BROKEN":    "❌",
    "MISSING":   _DASH,
    "UNAVAILABLE": _DASH,
    # Phase 14X.1: a defined risk/target contract is not the same claim as a
    # proof event having occurred — see DEFINED vs CONFIRMED law below. Uses
    # its own icon so it can never be visually mistaken for ✅ CONFIRMED.
    "DEFINED": "📋",
}


def _icon(state: str) -> str:
    return _PROOF_ICON.get(state, _DASH)


# ---------------------------------------------------------------------------
# Authoritative retest/hold display (mirrors the MA-1A precedence law already
# governing discord_alerts.format_alert: the dedicated 1H entry engine's own
# truth states are trusted over the stale signal-level retest/hold fields
# when 1H evidence is usable; verbatim read, nothing recomputed here).
# ---------------------------------------------------------------------------

_RETEST_TRUTH_STATE = {
    "RETEST_CORE_VALID": "CONFIRMED",
    "RETEST_REAL":       "CONFIRMED",
    "RETEST_EDGE_ONLY":  "FORMING",
    "RETEST_MISSED":     "MISSING",
}
_HOLD_TRUTH_STATE = {
    "HOLD_CONFIRMED": "CONFIRMED",
    "HOLD_FORMING":   "FORMING",
    "HOLD_WEAK":      "FORMING",
    "HOLD_FAILED":    "BROKEN",
}


def _one_hour_usable(one_hour: dict) -> bool:
    if not one_hour:
        return False
    if str(one_hour.get("status", "DISABLED")).upper() in ("DISABLED", "ERROR"):
        return False
    if str(one_hour.get("data_freshness", "")).upper() == "STALE":
        return False
    return True


def _authoritative_proof_detail(one_hour: dict, truth_key: str, table: dict, fallback_value):
    """Prefer the 1H engine's own truth state; fall back to signal-level enum.

    Returns (state, raw_label, source) — raw_label is the actual enum token
    backing the state (e.g. "RETEST_REAL" or the signal-level "partial"),
    and source is "1H" only when genuinely 1H-sourced, else "SIGNAL" — so a
    display line can never claim "LOCAL 1H" evidence when it actually fell
    back to the model's own signal-level field.
    """
    if _one_hour_usable(one_hour):
        prh = _safe_dict(one_hour.get("pullback_retest_hold"))
        truth = str(prh.get(truth_key, "") or "").upper().strip()
        if truth in table:
            return table[truth], truth, "1H"
    return _proof_state_of(fallback_value), _fmt(fallback_value), "SIGNAL"


def _authoritative_proof_state(one_hour: dict, truth_key: str, table: dict, fallback_value) -> str:
    """Prefer the 1H engine's own truth state; fall back to signal-level enum."""
    return _authoritative_proof_detail(one_hour, truth_key, table, fallback_value)[0]


def _daily_permission(ev: dict) -> str:
    """YES/CONDITIONAL/NO/UNAVAILABLE swing-permission label — the single
    shared derivation used by the DAILY timeframe section, the DOCTRINE
    SEQUENCE swing-qualification annotation, and AUTHORITY RECONCILIATION,
    so the three can never disagree with each other."""
    tfa = ev["timeframe_alignment"]
    if not tfa or str(tfa.get("status") or "").upper() != "ENABLED":
        return _UNAVAILABLE
    swing = _safe_dict(tfa.get("swing_timeframe"))
    swing_state = str(swing.get("state") or "PERMISSION_UNKNOWN")
    return _SWING_PERMISSION_MAP.get(swing_state, _UNAVAILABLE)


def _acceptance_state_from_location(location_state, structure_event) -> str:
    """Classify trade_location.location_state into a proof state.

    "below_zone_failure" (src/trade_location.py._classify) is a genuine BROKEN
    state — price failed below the zone — and must never render as FORMING,
    which would misrepresent a failed setup as still-developing. Every other
    non-"unknown" location_state indicates the price is at least present in/at
    the zone (FORMING), and "mid_zone_acceptance" or a Claude-classified
    structural reclaim indicates acceptance is CONFIRMED.
    """
    ls = str(location_state or "").lower()
    if ls == "below_zone_failure":
        return "BROKEN"
    if "acceptance" in ls or str(structure_event) == "reclaim":
        return "CONFIRMED"
    if ls and ls != "unknown":
        return "FORMING"
    return "MISSING"


# 4H structural break evidence (src/four_hour_operational.py) — the correct,
# already-computed source for the EXECUTION PROOF "Break" step. Deliberately
# NOT sourced from final_signal.structure_event: that field is the Daily/
# swing-level thesis (rendered separately as the DOCTRINE SEQUENCE "Structure"
# row), and reusing it here would let higher-timeframe evidence masquerade as
# independent 1H/4H execution-level break confirmation.
_FOUR_HOUR_BREAK_STATE_MAP = {
    "BOS_CONFIRMED": "CONFIRMED",
    "WICK_ONLY": "FORMING",
    "NONE": "MISSING",
}


def _four_hour_break_state(four_hour: dict) -> str:
    if not four_hour or not four_hour.get("enabled"):
        return "UNAVAILABLE"
    structure = _safe_dict(four_hour.get("structure"))
    raw = str(structure.get("break_state") or "UNKNOWN").upper()
    return _FOUR_HOUR_BREAK_STATE_MAP.get(raw, "UNAVAILABLE")


# ---------------------------------------------------------------------------
# Section builders — each reads only already-completed evidence.
# ---------------------------------------------------------------------------

def _extract(result: dict) -> dict:
    """Pull the stable sub-objects out of a completed run_analyze() result.

    Never mutates `result`; every value below is a reference read, not a copy
    of anything that would need copy-on-write protection (this module never
    writes to any of them).
    """
    tiering_result = _safe_dict(result.get("tiering_result"))
    signal = _safe_dict(tiering_result.get("final_signal"))
    return {
        "tiering_result": tiering_result,
        "signal": signal,
        "trajectory": _safe_dict(tiering_result.get("trajectory")),
        "trade_location": _safe_dict(tiering_result.get("trade_location")),
        "candle_evidence": _safe_dict(tiering_result.get("candle_evidence")),
        "one_hour_entry": _safe_dict(tiering_result.get("one_hour_entry")),
        "timeframe_alignment": _safe_dict(tiering_result.get("timeframe_alignment")),
        "four_hour_operational": _safe_dict(tiering_result.get("four_hour_operational")),
        "higher_timeframe_context": _safe_dict(tiering_result.get("higher_timeframe_context")),
        "snipe_gate_audit": _safe_dict(tiering_result.get("snipe_gate_audit")),
        "snipe_ladder": _safe_dict(tiering_result.get("snipe_ladder")),
        "snipe_confirmed_seal": _safe_dict(tiering_result.get("snipe_confirmed_seal")),
        "calibration": _safe_dict(tiering_result.get("calibration")),
        "enriched": _safe_dict(result.get("enriched")),
    }


def _verdict_capital_section(result: dict, ev: dict) -> dict:
    """VERDICT/CAPITAL evidence.

    Phase 14X.1 scan-clock law: the operator scan time comes ONLY from the
    runtime-captured result["scan_timestamp_et"] (set once in
    scheduler.run_analyze — never by the model). final_signal.timestamp_et
    is Claude's own field; it stays in the schema for model-contract
    compatibility but carries zero scan-clock authority and is rendered
    separately, explicitly labelled non-authoritative.

    Entry quality/readiness uses the SAME authoritative 1H precedence as
    DOCTRINE SEQUENCE / EXECUTION PROOF (_authoritative_proof_detail) rather
    than the stale signal-level retest_status/hold_status directly, so the
    top summary can never contradict the dedicated sections below it.
    """
    tiering_result = ev["tiering_result"]
    signal = ev["signal"]
    one_hour = ev["one_hour_entry"]
    daily_ctx = _safe_dict(ev["enriched"].get("daily_bar_context"))
    final_tier = str(result.get("final_tier") or tiering_result.get("final_tier") or "WAIT").upper()
    capital_action = tiering_result.get("capital_action")
    calibration = ev["calibration"]

    setup_quality = (
        f"family={_fmt(signal.get('setup_family'))} / "
        f"structure={_fmt(signal.get('structure_event'))} / "
        f"trend={_fmt(signal.get('trend_state'))}"
    )
    candle_family = ev["candle_evidence"].get("candle_family")
    retest_state, retest_raw, _retest_src = _authoritative_proof_detail(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state, hold_raw, _hold_src = _authoritative_proof_detail(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )
    entry_quality = (
        f"retest={retest_state} ({retest_raw}) / "
        f"hold={hold_state} ({hold_raw}) / "
        f"candle={_fmt(candle_family)}"
    )

    daily_status = daily_ctx.get("status")
    return {
        "ticker": _fmt(signal.get("ticker") or result.get("ticker")),
        "final_tier": final_tier,
        "badge": _TIER_BADGE.get(final_tier, final_tier),
        "capital_label": _CAPITAL_LABEL.get(capital_action, _fmt(capital_action)),
        "scan_price": _fmt_price(signal.get("scan_price")),
        "scan_executed": _fmt(result.get("scan_timestamp_et")),
        "model_timestamp": _fmt(signal.get("timestamp_et")),
        "daily_evidence_status": _fmt(daily_status) if daily_status else _UNAVAILABLE,
        "daily_last_closed_date": _fmt(daily_ctx.get("last_closed_daily_date")),
        "daily_live_date": _fmt(daily_ctx.get("live_daily_date")),
        "raw_score": _fmt(tiering_result.get("score")),
        "calibrated_score": _fmt(calibration.get("calibrated_score")) if calibration else _DASH,
        "setup_quality": setup_quality,
        "entry_quality": entry_quality,
    }


# ---------------------------------------------------------------------------
# Centralized structure_event display mapping (Phase 14X.1 pre-merge hardening).
#
# The naive "contains the substring 'failed'" heuristic previously classified
# failed_breakdown_reclaim as BROKEN/FAILED. That is wrong: the model schema
# (prompts/market_wizard_system.md) defines it as "Price broke below support,
# but immediately reversed and closed back above. Trap-style bullish event" —
# and every real strategy module that scores/gates structure_event treats it
# as a fully confirmed positive structural event, same tier as BOS/accepted_
# break (src/prefilter.py._score_structure_event: BOS/failed_breakdown_
# reclaim/accepted_break all score 90% of weight; MSS scores 100%; reclaim
# scores 75%). CHOCH is real but consistently weaker/earlier across the
# codebase (prefilter.py scores it only 40%; src/setup_family_compiler.py's
# valid_events and src/snipe_gate_audit.py's confirmed-structure group both
# EXCLUDE it) — an early change-of-character, not sovereign confirmation.
# This mapping is DISPLAY ONLY: it changes no score, gate, or tier.
# ---------------------------------------------------------------------------

_STRUCTURE_EVENT_STATE = {
    "bos": "CONFIRMED",
    "mss": "CONFIRMED",
    "reclaim": "CONFIRMED",
    "accepted_break": "CONFIRMED",
    "failed_breakdown_reclaim": "CONFIRMED",
    "choch": "FORMING",
    "none": "MISSING",
}


def _structure_event_state(structure_event) -> str:
    key = str(structure_event or "none").strip().lower()
    return _STRUCTURE_EVENT_STATE.get(key, "MISSING")


def _setup_section(ev: dict) -> dict:
    signal = ev["signal"]
    retest_state = _proof_state_of(signal.get("retest_status"))
    hold_state = _proof_state_of(signal.get("hold_status"))
    structure_state = _structure_event_state(signal.get("structure_event"))

    if structure_state == "MISSING":
        stage = _UNAVAILABLE
    elif retest_state == "BROKEN" or hold_state == "BROKEN":
        # A genuinely failed local proof leg is FAILED regardless of how the
        # structural event is named — never inferred from the event's name.
        stage = "FAILED"
    elif structure_state == "CONFIRMED" and retest_state == "CONFIRMED" and hold_state == "CONFIRMED":
        stage = "CONFIRMED"
    else:
        stage = "FORMING"

    return {
        "family": _fmt(signal.get("setup_family")),
        "state": _fmt(signal.get("trend_state")),
        # Production scope is bullish swing-entry only (README mission
        # statement) — this is a fixed doctrine fact, not a per-ticker
        # judgment, so it is never inferred from signal fields.
        "direction": "Long (bullish swing — production scanner scope)",
        "stage": stage,
    }


def _htf_thesis_authorization(ev: dict, structure_state: str) -> str:
    """AUTHORIZED / CONDITIONAL / NOT AUTHORIZED / UNAVAILABLE.

    Answers exactly one question: is the HIGHER-TIMEFRAME swing thesis
    authorized (Weekly/Daily context + Daily/swing Structure)? This is a
    single, named boolean-turned-enum precisely so it cannot be conflated
    with two other, different questions this renderer also answers
    elsewhere: whether the LOCAL execution sequence (4H+1H: Break ->
    Acceptance -> Retest -> Hold) is complete, and whether CAPITAL is ready
    (owned exclusively by final_tier/capital_action). Local 1H retest/hold
    proof — however clean — never substitutes for this; a clean local
    sequence can coexist with NOT AUTHORIZED/CONDITIONAL here.
    """
    daily_permission = _daily_permission(ev)
    if daily_permission == _UNAVAILABLE:
        return _UNAVAILABLE
    if daily_permission == "NO":
        return "NOT AUTHORIZED"
    if daily_permission == "YES" and structure_state == "CONFIRMED":
        return "AUTHORIZED"
    if daily_permission in ("YES", "CONDITIONAL"):
        return "CONDITIONAL"
    return "NOT AUTHORIZED"


def _doctrine_sequence_section(ev: dict) -> list:
    """SWING DOCTRINE SEQUENCE: Structure -> Liquidity -> Displacement ->
    Acceptance/Reclaim -> Retest -> Hold -> Invalidation -> Target.

    Liquidity/Displacement/Acceptance have no dedicated schema field; each is
    rendered as DERIVED_DISPLAY from the fields that do exist (structure_event,
    location_state, zone_type), explicitly labelled, never invented.

    Retest/Hold carry an additional annotation naming exactly one question:
    is the HTF (Weekly/Daily) swing thesis AUTHORIZED? A CONFIRMED local
    (1H) retest/hold is real evidence, but it does not by itself mean the
    higher-timeframe thesis is authorized — that requires the upstream
    Structure gate AND Daily swing permission to also hold. Local proof can
    improve while HTF-thesis authorization remains withheld; see
    _htf_thesis_authorization. This is deliberately a single, named
    question — never conflated with local-execution-sequence completeness
    (EXECUTION PROOF) or capital readiness (owned only by final_tier).

    Invalidation/Target render DEFINED, never CONFIRMED — a defined risk
    contract (a level + condition exist) is not the same claim as that level
    having been triggered/hit, which this renderer has no explicit event-
    level evidence to assert either way.
    """
    signal = ev["signal"]
    trade_location = ev["trade_location"]
    one_hour = ev["one_hour_entry"]

    structure_event = signal.get("structure_event")
    structure_state = _structure_event_state(structure_event)

    displacement_state = (
        "CONFIRMED" if str(structure_event or "").upper() in ("BOS", "MSS", "ACCEPTED_BREAK")
        else "MISSING"
    )

    location_state = trade_location.get("location_state")
    acceptance_state = _acceptance_state_from_location(location_state, signal.get("structure_event"))

    retest_state, retest_raw, retest_src = _authoritative_proof_detail(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state, hold_raw, hold_src = _authoritative_proof_detail(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )
    htf_thesis = _htf_thesis_authorization(ev, structure_state)
    qualification_note = (
        None if htf_thesis == "AUTHORIZED"
        else f"HTF THESIS AUTHORIZATION: {htf_thesis} — local proof alone does not authorize it"
    )

    inval_level = signal.get("invalidation_level")
    invalidation_state = "DEFINED" if inval_level is not None else "MISSING"

    targets = _safe_list(signal.get("targets"))
    target_state = "DEFINED" if targets else "MISSING"

    rows = [
        ("Structure", structure_state, _fmt(signal.get("structure_event")), None, None),
        ("Liquidity", "UNAVAILABLE",
         "not modeled as a discrete field in the current schema", None, None),
        ("Displacement", displacement_state,
         f"derived from structure_event={_fmt(signal.get('structure_event'))}", None, None),
        ("Acceptance/Reclaim", acceptance_state, _fmt(trade_location.get("location_state")), None, None),
        ("Retest", retest_state, f"LOCAL {retest_src}: {retest_raw}", None, qualification_note),
        ("Hold", hold_state, f"LOCAL {hold_src}: {hold_raw}", None, qualification_note),
        ("Invalidation", invalidation_state,
         _fmt(signal.get("invalidation_condition")), _fmt_price(inval_level), None),
        ("Target", target_state,
         f"{len(targets)} target(s)" if targets else _DASH,
         _fmt_price(targets[0].get("level")) if targets and isinstance(targets[0], dict) else None, None),
    ]
    return [
        {
            "step": step, "state": state, "icon": _icon(state), "evidence": evidence,
            "level": level, "qualification_note": note,
        }
        for step, state, evidence, level, note in rows
    ]


def _local_execution_states(ev: dict) -> dict:
    """The single source of truth for the Break -> Acceptance -> Retest ->
    Hold local (4H/1H) execution chain — computed once, consumed by both
    EXECUTION PROOF and AUTHORITY RECONCILIATION so the two sections can
    never disagree about local proof or sequence completeness.
    """
    signal = ev["signal"]
    trade_location = ev["trade_location"]
    one_hour = ev["one_hour_entry"]
    four_hour = ev["four_hour_operational"]

    # Sourced from 4H structural evidence, never from the Daily/swing-level
    # final_signal.structure_event (that field already drives the DOCTRINE
    # SEQUENCE "Structure" row) — see _four_hour_break_state's docstring.
    break_state = _four_hour_break_state(four_hour)
    break_raw = _fmt(_safe_dict(four_hour.get("structure")).get("break_state")) if four_hour else _DASH

    location_state = trade_location.get("location_state")
    acceptance_state = _acceptance_state_from_location(location_state, signal.get("structure_event"))

    retest_state, retest_raw, _retest_src = _authoritative_proof_detail(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state, hold_raw, _hold_src = _authoritative_proof_detail(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )
    return {
        "break": break_state, "break_raw": break_raw,
        "acceptance": acceptance_state,
        "retest": retest_state, "retest_raw": retest_raw,
        "hold": hold_state, "hold_raw": hold_raw,
    }


def _local_execution_sequence(states: dict) -> str:
    """COMPLETE / INCOMPLETE / FAILED / UNAVAILABLE for the full local chain.
    A single BROKEN leg fails the whole sequence regardless of position."""
    ordered = [states["break"], states["acceptance"], states["retest"], states["hold"]]
    if any(s == "BROKEN" for s in ordered):
        return "FAILED"
    if all(s == "CONFIRMED" for s in ordered):
        return "COMPLETE"
    if all(s in ("MISSING", "UNAVAILABLE") for s in ordered):
        return _UNAVAILABLE
    return "INCOMPLETE"


def _local_proof_narrative(states: dict) -> str:
    """BROKEN / CONFIRMED / IMPROVING / NONE — a conservative, precedence-
    ordered narrative over the SAME four legs used by
    _local_execution_sequence. This is the fix for the defect where an
    optimistic OR could let e.g. RETEST_REAL (CONFIRMED) hide a HOLD_FAILED
    (BROKEN) behind "IMPROVING" — a later failed critical leg must never be
    hidden by an earlier successful one. BROKEN always outranks everything
    else; only when nothing is BROKEN can partial/complete progress be
    reported as IMPROVING/CONFIRMED.
    """
    ordered = [states["break"], states["acceptance"], states["retest"], states["hold"]]
    if any(s == "BROKEN" for s in ordered):
        return "BROKEN"
    if all(s == "CONFIRMED" for s in ordered):
        return "CONFIRMED"
    if any(s in ("CONFIRMED", "FORMING") for s in ordered):
        return "IMPROVING"
    return "NONE"


def _execution_proof_section(ev: dict) -> dict:
    states = _local_execution_states(ev)
    sequence = _local_execution_sequence(states)
    final_tier = str(ev["tiering_result"].get("final_tier") or "WAIT").upper()

    return {
        "break": {"state": states["break"], "icon": _icon(states["break"]), "raw": states["break_raw"]},
        "acceptance": {"state": states["acceptance"], "icon": _icon(states["acceptance"])},
        "retest": {"state": states["retest"], "icon": _icon(states["retest"]), "raw": states["retest_raw"]},
        "hold": {"state": states["hold"], "icon": _icon(states["hold"]), "raw": states["hold_raw"]},
        "sequence": sequence,
        "capital_readiness": _CAPITAL_READINESS.get(final_tier, "NONE"),
        # Phase 14X.1: this section is LOCAL (4H/1H) execution evidence only.
        # It never authorizes capital on its own — capital comes from the
        # already-computed final_tier/capital_action, shown elsewhere and
        # unchanged by this renderer. Static, always-true clarifying label.
        "authority": "LOCAL ONLY — not capital-authorizing on its own",
    }


_WEEKLY_REQUIRED_FIELDS = (
    "monthly_bias_state", "weekly_campaign_state",
    "campaign_location_label", "context_grade",
)

# src/higher_timeframe_context.py's own real vocabulary: BIAS_STATES,
# CAMPAIGN_STATES-equivalents, LOCATION_QUALITY, and GRADES all include the
# literal placeholder "UNKNOWN" as a legitimate degraded/insufficient-data
# value — a non-empty Python string, so a bare truthiness check on these
# fields wrongly counts "UNKNOWN" as present/complete evidence. This treats
# it (and other real non-informative tokens the engine emits) as NOT
# satisfying completeness.
_HTF_NONINFORMATIVE_TOKENS = {
    "", "unknown", "unavailable", "not_available", "n/a", "none", "null", "error",
}


def _htf_field_is_meaningful(value) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower()
    if not s or s in _HTF_NONINFORMATIVE_TOKENS:
        return False
    if s.startswith("degraded"):
        return False
    return True


def _normalize_htf_view(htf) -> dict:
    """Adapter over the two real higher_timeframe_context shapes.

    Phase 14X.2 finding: tiering_result["higher_timeframe_context"] on a
    completed live run_analyze() result is the FULL NESTED object exactly as
    build_higher_timeframe_context() returns it — monthly_bias_state,
    weekly_campaign_state, campaign_location_label, campaign_location_
    quality, context_grade, supports_long_setup, weakens_long_setup, and
    blocks_snipe_contextually live at htf["monthly"]["bias_state"],
    htf["weekly"]["campaign_state"], htf["campaign_location"]["label"/
    "quality"], and htf["setup_relationship"][...] respectively — NEVER as
    top-level flat keys. The historical alert_history persistence path
    instead stores the ALREADY-FLATTENED shape (produced by
    higher_timeframe_context.compact_history_snapshot, the same function
    src/audit_access.py's persisted-row rendering implicitly depends on).
    Reading the nested object as if it were flat silently starved this
    renderer's Weekly section of every field except data_status/
    diagnostic_sentence (both happen to be top-level in either shape).

    This function detects which shape it received and always normalizes to
    the flat view using that SAME canonical, already-existing, pure
    serialization function — never a hand-rolled parallel mapping that could
    drift from it. Never mutates `htf`. When both a nested sub-object and a
    stray top-level flat key are present (e.g. a hand-built fixture), the
    nested object always wins — it is the authoritative live source; a flat
    key only exists at all on an already-compacted snapshot.
    """
    if not isinstance(htf, dict):
        return {}
    is_nested = any(isinstance(htf.get(k), dict) for k in ("monthly", "weekly", "setup_relationship", "campaign_location"))
    if is_nested:
        from src import higher_timeframe_context as _htf_engine  # local import (pure, stdlib-only serializer)
        compact = _htf_engine.compact_history_snapshot(htf)
        if isinstance(compact, dict):
            return compact
    # Already-flat/compact shape (persisted snapshot or a test fixture built
    # directly in that shape) — used as-is; a field genuinely absent here
    # simply renders as unavailable downstream, never fabricated.
    return htf


def _weekly_section(ev: dict) -> dict:
    """WEEKLY — CAMPAIGN CONTEXT.

    Phase 14X.1 law: UNKNOWN is not bullish, UNKNOWN is not bearish, and
    UNKNOWN is not complete evidence. A posture value is only ever computed
    from `supports_long_setup`/`weakens_long_setup`, but if the underlying
    campaign evidence is materially incomplete — any of _WEEKLY_REQUIRED_
    FIELDS missing OR literally "UNKNOWN"/degraded (src/higher_timeframe_
    context.py's own real vocabulary), even though data_status == "OK" —
    the posture must be explicitly qualified, and positive sponsorship can
    never be PROVEN from missing/degraded evidence.
    """
    htf = _normalize_htf_view(ev["higher_timeframe_context"])
    if not htf or str(htf.get("data_status") or "").upper() != "OK":
        return {"available": False, "campaign_evidence": "INCOMPLETE"}
    supports = htf.get("supports_long_setup") is True
    weakens = htf.get("weakens_long_setup") is True
    if weakens:
        posture = "hostile"
    elif supports:
        posture = "supportive"
    else:
        posture = "mixed"

    missing_fields = [f for f in _WEEKLY_REQUIRED_FIELDS if not _htf_field_is_meaningful(htf.get(f))]
    campaign_evidence = "COMPLETE" if not missing_fields else "INCOMPLETE"
    positive_sponsorship = "PROVEN" if (campaign_evidence == "COMPLETE" and supports and not weakens) else "NOT PROVEN"

    return {
        "available": True,
        "monthly_bias": _fmt(htf.get("monthly_bias_state")),
        "weekly_campaign": _fmt(htf.get("weekly_campaign_state")),
        "location": _fmt(htf.get("campaign_location_label")),
        "location_quality": _fmt(htf.get("campaign_location_quality")),
        "posture": posture,
        "campaign_evidence": campaign_evidence,
        "positive_sponsorship": positive_sponsorship,
        "blocks_snipe": htf.get("blocks_snipe_contextually") is True,
        "diagnostic": _sanitize(htf.get("diagnostic_sentence")),
    }


_SWING_PERMISSION_MAP = {
    "PERMISSION_GRANTED": "YES",
    "PERMISSION_REPAIRING": "CONDITIONAL",
    "PERMISSION_FORMING": "CONDITIONAL",
    "PERMISSION_DENIED": "NO",
    "PERMISSION_UNKNOWN": _UNAVAILABLE,
}


def _daily_section(ev: dict) -> dict:
    tfa = ev["timeframe_alignment"]
    if not tfa or str(tfa.get("status") or "").upper() != "ENABLED":
        return {"available": False}
    swing = _safe_dict(tfa.get("swing_timeframe"))
    swing_state = str(swing.get("state") or "PERMISSION_UNKNOWN")
    enriched = ev["enriched"]
    return {
        "available": True,
        "trend_state": _fmt(ev["signal"].get("trend_state")),
        "sma10": _fmt_price(enriched.get("sma10")),
        "sma20": _fmt_price(enriched.get("sma20")),
        "sma50": _fmt_price(enriched.get("sma50")),
        "sma200": _fmt_price(enriched.get("sma200")),
        "sma_alignment": _fmt(ev["signal"].get("sma_value_alignment")),
        "swing_state": swing_state,
        "permission": _daily_permission(ev),
    }


def _four_hour_section(ev: dict) -> dict:
    fh = ev["four_hour_operational"]
    if not fh or not fh.get("enabled"):
        return {"available": False}
    structure = _safe_dict(fh.get("structure"))
    retest_truth = _safe_dict(fh.get("retest_truth"))
    return {
        "available": True,
        "structural_state": _fmt(fh.get("structural_state")),
        "operational_location": _fmt(fh.get("operational_location")),
        "operational_readiness": _fmt(fh.get("operational_readiness")),
        "state_confidence": _fmt(fh.get("state_confidence")),
        "break_state": _fmt(structure.get("break_state")),
        "retest_state": _fmt(retest_truth.get("state")),
        "verdict": _fmt(fh.get("operational_location")),
    }


_ONE_HOUR_READY_MAP = {
    "TRIGGER_LIVE": "READY",
    "TRIGGER_READY": "READY",
    "TRIGGER_FAILED": "FAILED",
}


def _one_hour_section(ev: dict) -> dict:
    oh = ev["one_hour_entry"]
    if not oh or str(oh.get("status") or "DISABLED").upper() in ("DISABLED", "ERROR"):
        return {"available": False}
    trigger_state = str(oh.get("trigger_state") or "NO_1H_EVIDENCE")
    if "FAIL" in trigger_state.upper():
        readiness = "FAILED"
    else:
        readiness = _ONE_HOUR_READY_MAP.get(trigger_state, "FORMING")
    prh = _safe_dict(oh.get("pullback_retest_hold"))
    return {
        "available": True,
        "trigger_state": _fmt(trigger_state),
        "break_level": _fmt_price(ev["signal"].get("trigger_level")),
        "retest": _fmt(prh.get("retest_truth")),
        "hold": _fmt(prh.get("hold_truth")),
        "last_closed_state": _fmt(oh.get("data_freshness")),
        "live_state": "information only — no confirmation authority until close",
        "readiness": readiness,
        "score": _fmt(oh.get("score")),
        "score_label": _fmt(oh.get("score_label")),
        "diagnostic": _sanitize(oh.get("scanner_sentence")),
    }


def _timeframe_sovereignty_section(ev: dict) -> dict:
    return {
        "weekly": _weekly_section(ev),
        "daily": _daily_section(ev),
        "four_hour": _four_hour_section(ev),
        "one_hour": _one_hour_section(ev),
    }


def _trade_location_section(ev: dict) -> dict:
    signal = ev["signal"]
    trade_location = ev["trade_location"]
    enriched = ev["enriched"]

    inval_level = signal.get("invalidation_level")
    scan_price = signal.get("scan_price") or trade_location.get("scan_price")
    trigger = signal.get("trigger_level")
    targets = _safe_list(signal.get("targets"))
    t1 = targets[0].get("level") if targets and isinstance(targets[0], dict) else None

    def _pct_distance(a, b):
        try:
            a_f, b_f = float(a), float(b)
            if b_f == 0:
                return None
            return (a_f - b_f) / abs(b_f) * 100.0
        except (TypeError, ValueError):
            return None

    zone_type = trade_location.get("zone_type")
    zone_low = trade_location.get("zone_low")
    zone_high = trade_location.get("zone_high")
    zone_mid = trade_location.get("zone_mid")

    return {
        "current_price": _fmt_price(scan_price),
        "trigger": _fmt_price(trigger),
        "zone_type": _fmt(zone_type),
        "zone_low": _fmt_price(zone_low),
        "zone_high": _fmt_price(zone_high),
        "zone_mid": _fmt_price(zone_mid),
        "sma10": _fmt_price(enriched.get("sma10")),
        "sma20": _fmt_price(enriched.get("sma20")),
        "sma50": _fmt_price(enriched.get("sma50")),
        "sma200": _fmt_price(enriched.get("sma200")),
        "invalidation": _fmt_price(inval_level),
        # Phase 14X.1: a target LEVEL existing is not a target HIT/CONFIRMED
        # event — labelled DEFINED elsewhere (DOCTRINE SEQUENCE). The `reason`
        # text is Claude's own prose (final_signal.targets[].reason is part
        # of the model's structured output, not a deterministic computation),
        # so it is explicitly tagged [MODEL]; when it invokes liquidity
        # language the renderer states plainly that no discrete liquidity
        # schema exists to validate the claim (see DOCTRINE SEQUENCE's
        # "Liquidity: UNAVAILABLE" row — same honest gap, not re-solved here).
        "targets": [
            {
                "label": t.get("label"),
                "level": _fmt_price(t.get("level")),
                "reason": _sanitize(t.get("reason")),
                "reason_provenance": "MODEL",
                "liquidity_validation": (
                    _UNAVAILABLE
                    if _mentions_liquidity(t.get("reason"))
                    else None
                ),
            }
            for t in targets if isinstance(t, dict)
        ],
        "dist_to_trigger_pct": _fmt_pct(_pct_distance(scan_price, trigger)),
        "dist_to_invalidation_pct": _fmt_pct(_pct_distance(scan_price, inval_level)),
        "dist_to_t1_pct": _fmt_pct(_pct_distance(t1, scan_price)),
    }


def _candle_truth_section(ev: dict) -> dict:
    """CANDLE TRUTH evidence.

    tiering_result["candle_evidence"] is built upstream by calling
    candle_evidence.build_candle_evidence_context(enriched, tiering_result)
    with no bars/timeframe args — it falls back to the CURRENT DAILY bar
    (candle_evidence's own event-from-enriched path reads enriched's
    current_* fields, which is the Daily indicator dict), and its own
    `timeframe` field is therefore None in production today. This section
    must never claim that object is 1H evidence; the timeframe label is
    always echoed verbatim from the source, never asserted.

    Genuinely 1H-scoped candle evidence — one_hour_entry.candle_truth — is
    rendered as a separate, explicitly labelled subsection when usable.
    """
    candle = ev["candle_evidence"]
    one_hour = ev["one_hour_entry"]

    generic_available = bool(candle) and str(candle.get("status") or "unknown") != "unknown"
    tf_raw = candle.get("timeframe") if generic_available else None
    tf_label = _fmt(tf_raw) if tf_raw else "not specified by evidence"

    one_hour_candle: dict = {}
    if _one_hour_usable(one_hour):
        oh_candle = _safe_dict(one_hour.get("candle_truth"))
        event_type = str(oh_candle.get("event_type") or "NONE").upper()
        if event_type not in ("", "NONE"):
            one_hour_candle = {
                "event_type": _fmt(oh_candle.get("event_type")),
                "closed_candle_confirms": _fmt(oh_candle.get("closed_candle_confirms")),
                "body_acceptance": _fmt(oh_candle.get("body_acceptance")),
                "wick_rejection": _fmt(oh_candle.get("wick_rejection")),
                "follow_through_present": _fmt(oh_candle.get("follow_through_present")),
                "volume_support": _fmt(oh_candle.get("volume_support")),
            }

    return {
        "available": generic_available or bool(one_hour_candle),
        "generic_available": generic_available,
        "timeframe_label": tf_label,
        "body_pct": _fmt_pct(candle.get("body_pct")) if generic_available else _DASH,
        "upper_wick_pct": _fmt_pct(candle.get("upper_wick_pct")) if generic_available else _DASH,
        "lower_wick_pct": _fmt_pct(candle.get("lower_wick_pct")) if generic_available else _DASH,
        "close_position_pct": _fmt_pct(candle.get("close_position_pct")) if generic_available else _DASH,
        "candle_family": _fmt(candle.get("candle_family")) if generic_available else _DASH,
        "close_quality": _fmt(candle.get("close_quality")) if generic_available else _DASH,
        "wick_read": _fmt(candle.get("wick_read")) if generic_available else _DASH,
        "level_reaction": _fmt(candle.get("level_reaction")) if generic_available else _DASH,
        "next_candle_verdict": _fmt(candle.get("next_candle_verdict")) if generic_available else _DASH,
        "candle_veto": _fmt(candle.get("candle_veto")) if generic_available else _DASH,
        "display_text": _sanitize(candle.get("display_text")) if generic_available else "",
        "one_hour_candle": one_hour_candle,
        "live_state": "information only — no confirmation authority until close",
    }


_RR_RECONCILE_TOLERANCE = 0.05  # 5% relative tolerance — documented, strict


def _reconcile_rr(entry_price, invalidation, target, source_rr, tolerance: float = _RR_RECONCILE_TOLERANCE):
    """Deterministically reconcile (entry_price, invalidation, target) against
    source_rr; return the computed ratio only when it matches within
    `tolerance`, else None. Never raises.

    This is the SOLE mechanism by which any R:R may be labelled reconciled/
    executable — mere existence of a price is never sufficient. Two
    independent callers use this with two different bases:
      - scan_price as entry_price -> "Reference R:R (scan-price)"
      - trigger_level as entry_price -> "Executable-entry R:R"
    A reconciliation against one basis says nothing about the other; each
    call is independent.
    """
    try:
        entry_f = float(entry_price)
        inv_f = float(invalidation)
        target_f = float(target)
        src_f = float(source_rr)
    except (TypeError, ValueError):
        return None
    if not all(_is_finite(x) for x in (entry_f, inv_f, target_f, src_f)):
        return None
    risk = entry_f - inv_f          # bullish mandate: risk is entry minus invalidation, below entry
    reward = target_f - entry_f     # reward is target minus entry, above entry
    if risk <= 0 or reward <= 0 or src_f == 0:
        return None
    computed = reward / risk
    if not _is_finite(computed):
        return None
    if abs(computed - src_f) / abs(src_f) <= tolerance:
        return computed
    return None


def _risk_runway_section(ev: dict) -> dict:
    """RISK / RUNWAY.

    Phase 14X.1 provenance laws:
      - Trigger existence alone does NOT prove the source risk_reward was
        computed from (trigger -> invalidation -> T1) geometry — a source
        R:R could have been calculated from scan price, another reference,
        or unreconstructable model reasoning. EXECUTABLE-ENTRY R:R is
        therefore labelled reconciled ONLY when (trigger, invalidation, T1)
        deterministically matches source_rr within tolerance (_reconcile_rr)
        — otherwise it is UNAVAILABLE with an explicit "not reconciled"
        basis, even when a trigger exists.
      - "Reference R:R (scan-price)" is an INDEPENDENT reconciliation check
        against (scan_price, invalidation, T1) — it may reconcile while the
        trigger-basis does not, and vice versa; the two never imply each
        other.
      - Reported overhead is the MODEL's own final_signal.overhead_status —
        never presented as independently verified. When the deterministic
        structural overhead computation (indicators.py's assess_overhead,
        already computed into enriched["overhead_status"/"overhead_level"/
        "overhead_distance_pct"]) is available, it is shown as its own,
        separately-labelled structural reconciliation; when it is not
        available, that is stated explicitly rather than silently upgrading
        the model's "clear" into a proven clean path.
    """
    signal = ev["signal"]
    one_hour = ev["one_hour_entry"]
    enriched = ev["enriched"]
    targets = _safe_list(signal.get("targets"))
    t1 = targets[0] if targets and isinstance(targets[0], dict) else {}
    t2 = targets[1] if len(targets) > 1 and isinstance(targets[1], dict) else {}
    path_quality = _safe_dict(one_hour.get("path_quality")) if one_hour else {}

    def _reward_pct(target_level, trigger):
        try:
            t_f, trig_f = float(target_level), float(trigger)
            if trig_f == 0:
                return None
            return (t_f - trig_f) / abs(trig_f) * 100.0
        except (TypeError, ValueError):
            return None

    trigger = signal.get("trigger_level")
    scan_price = signal.get("scan_price")
    invalidation = signal.get("invalidation_level")
    source_rr = signal.get("risk_reward")
    t1_level = t1.get("level") if t1 else None

    # Executable-entry basis: reconciled against the real trigger, never
    # merely because a trigger happens to exist.
    executable_reconciled = (
        _reconcile_rr(trigger, invalidation, t1_level, source_rr)
        if (trigger is not None and t1_level is not None and source_rr is not None) else None
    )
    if trigger is None:
        executable_entry_rr = _UNAVAILABLE
        executable_entry_rr_basis = "UNAVAILABLE / no executable trigger"
    elif executable_reconciled is not None:
        executable_entry_rr = _fmt_ratio(executable_reconciled)
        executable_entry_rr_basis = "DERIVED_DISPLAY / reconciled to source value"
    else:
        executable_entry_rr = _UNAVAILABLE
        executable_entry_rr_basis = "NOT RECONCILED"

    # Reference basis: an INDEPENDENT reconciliation against scan price —
    # never implied by, or implying, the executable-entry basis above.
    reference_reconciled = (
        _reconcile_rr(scan_price, invalidation, t1_level, source_rr)
        if (t1_level is not None and source_rr is not None) else None
    )
    reference_rr = _fmt_ratio(reference_reconciled) if reference_reconciled is not None else _DASH
    reference_rr_basis = (
        "DERIVED_DISPLAY / reconciled to source value" if reference_reconciled is not None
        else "UNAVAILABLE / not reconstructable within tolerance"
    )

    # Deterministic structural overhead (indicators.assess_overhead) — real,
    # already-computed evidence independent of the model. Reported alongside,
    # never merged into, the model's own overhead_status.
    struct_overhead_status = enriched.get("overhead_status")
    struct_overhead_available = struct_overhead_status is not None
    struct_overhead_level = enriched.get("overhead_level")
    struct_overhead_distance_pct = enriched.get("overhead_distance_pct")

    return {
        "executable_trigger": _fmt_price(trigger) if trigger is not None else _UNAVAILABLE,
        "reference_price": _fmt_price(scan_price),
        "invalidation": _fmt_price(signal.get("invalidation_level")),
        "risk_distance": _fmt_price(signal.get("risk_distance")),
        "risk_distance_pct": _fmt_pct(signal.get("risk_distance_pct")),
        "t1": _fmt_price(t1.get("level")),
        "t2": _fmt_price(t2.get("level")),
        "reward_t1_pct": _fmt_pct(_reward_pct(t1.get("level"), trigger)) if t1 else _DASH,
        "reward_t2_pct": _fmt_pct(_reward_pct(t2.get("level"), trigger)) if t2 else _DASH,
        "source_rr": _fmt_ratio(source_rr),
        "executable_entry_rr": executable_entry_rr,
        "executable_entry_rr_basis": executable_entry_rr_basis,
        "reference_rr": reference_rr,
        "reference_rr_basis": reference_rr_basis,
        "reported_overhead": _fmt(signal.get("overhead_status")),
        "reported_overhead_source": "MODEL / final_signal",
        "structural_overhead_status": _fmt(struct_overhead_status) if struct_overhead_available else _UNAVAILABLE,
        "structural_overhead_level": _fmt_price(struct_overhead_level) if struct_overhead_available else _DASH,
        "structural_overhead_distance_pct": _fmt_pct(struct_overhead_distance_pct) if struct_overhead_available else _DASH,
        "path_clarity_label": (
            _fmt(path_quality.get("path_label"))
            if path_quality and str(path_quality.get("path_label") or "UNKNOWN").upper() != "UNKNOWN"
            else "NOT INDEPENDENTLY VERIFIED"
        ),
        "failure_condition": _sanitize(signal.get("invalidation_condition")),
    }


def _tier_judgment_section(ev: dict, result: dict) -> dict:
    """TIER JUDGMENT.

    Phase 14X.2 fix: this section previously classified retest/hold
    proof independently via _proof_state_of(signal.get(...)) — the stale
    signal-level fields — never checking whether usable 1H evidence had
    already superseded them. That let the SAME operator case file say
    "retest CONFIRMED" in VERDICT/DOCTRINE/EXECUTION PROOF while TIER
    JUDGMENT simultaneously listed "retest_status=partial" as a current
    missing proof — two interpretations of one fact. This now uses the
    identical _authoritative_proof_detail precedence as every other
    section (one_hour_entry wins when usable, else the signal-level
    field), so all sections can never again disagree.

    A completed snipe_gate_audit.missing_proofs entry that merely names
    "retest"/"hold" is also superseded once the CURRENT authoritative
    state for that leg reads CONFIRMED — the raw evidence is not deleted
    anywhere upstream (snipe_gate_audit itself is untouched), only this
    display no longer repeats a claim its own authoritative source has
    already resolved.
    """
    tiering_result = ev["tiering_result"]
    signal = ev["signal"]
    sga = ev["snipe_gate_audit"]
    ladder = ev["snipe_ladder"]
    seal = ev["snipe_confirmed_seal"]
    one_hour = ev["one_hour_entry"]

    final_tier = str(result.get("final_tier") or tiering_result.get("final_tier") or "WAIT").upper()
    capital_action = tiering_result.get("capital_action")

    missing_proofs = _nonempty(sga.get("missing_proofs"))
    blocked_gates = _nonempty(sga.get("blocked_gate_names")) or _nonempty(sga.get("blocked_gates"))
    applied_vetoes = _nonempty(tiering_result.get("applied_vetoes"))

    retest_state, retest_raw, retest_src = _authoritative_proof_detail(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state, hold_raw, hold_src = _authoritative_proof_detail(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )

    # MISSING vs BROKEN law: "failed"/BROKEN is broken; anything else
    # incomplete (missing/partial/forming) is missing, never invented as
    # failed. Signal-sourced fallback keeps the exact legacy label format
    # ("retest_status=failed") for backward-compatible provenance; a 1H-
    # sourced read is labelled as such so the operator can see which
    # authority produced it.
    broken: list = []
    missing: list = []
    if retest_state == "BROKEN":
        broken.append(f"retest_status={retest_raw}" if retest_src == "SIGNAL" else f"1H retest={retest_raw}")
    elif retest_state != "CONFIRMED":
        missing.append(f"retest_status={retest_raw}" if retest_src == "SIGNAL" else f"1H retest={retest_state} ({retest_raw})")
    if hold_state == "BROKEN":
        broken.append(f"hold_status={hold_raw}" if hold_src == "SIGNAL" else f"1H hold={hold_raw}")
    elif hold_state != "CONFIRMED":
        missing.append(f"hold_status={hold_raw}" if hold_src == "SIGNAL" else f"1H hold={hold_state} ({hold_raw})")

    retest_confirmed = retest_state == "CONFIRMED"
    hold_confirmed = hold_state == "CONFIRMED"
    for m in missing_proofs:
        item_text = _fmt_item(m)
        low = item_text.lower()
        if retest_confirmed and "retest" in low:
            continue  # superseded by current authoritative retest confirmation
        if hold_confirmed and "hold" in low:
            continue  # superseded by current authoritative hold confirmation
        missing.append(item_text)
    for v in applied_vetoes:
        broken.append(_fmt_item(v))

    why_this_tier = _sanitize(
        ladder.get("why_this_ladder_tier")
        or sga.get("diagnostic_sentence")
        or signal.get("reason")
        or ""
    ) or _DASH
    why_not_higher = _sanitize(ladder.get("why_not_higher") or "") or _DASH
    why_not_lower = _sanitize(ladder.get("why_not_lower") or "") or _DASH

    next_idx = _TIER_ORDER.index(final_tier) + 1 if final_tier in _TIER_ORDER else None
    why_not_starter = _DASH
    why_not_snipe = _DASH
    if final_tier in ("WAIT", "NEAR_ENTRY"):
        why_not_starter = why_not_higher
    if final_tier in ("WAIT", "NEAR_ENTRY", "STARTER"):
        why_not_snipe = _sanitize(
            (ladder.get("why_not_higher") if final_tier == "STARTER" else "")
            or sga.get("diagnostic_sentence") or ""
        ) or _DASH

    primary_blocker = _fmt_item(blocked_gates[0]) if blocked_gates else (
        _fmt_item(missing_proofs[0]) if missing_proofs else _DASH
    )

    promotion_requirement = _DASH
    proofs = ladder.get("next_promotion_proof")
    if isinstance(proofs, list) and proofs:
        promotion_requirement = _sanitize(str(proofs[0]))

    failure_condition = _sanitize(ladder.get("failure_condition") or "") or _DASH

    seal_note = ""
    if seal.get("applied"):
        seal_note = (
            f"SNIPE confirmation was sealed down: "
            f"{_fmt(seal.get('original_tier'))} -> {_fmt(seal.get('corrected_tier'))}."
        )

    return {
        "final_tier": final_tier,
        "why_this_tier": why_this_tier,
        "why_not_higher": why_not_higher,
        "why_not_starter": why_not_starter,
        "why_not_snipe_it": why_not_snipe,
        "why_not_lower": why_not_lower,
        "primary_blocker": primary_blocker,
        "missing_proof": missing or [_DASH],
        "broken_proof": broken or [_DASH],
        "promotion_requirement": promotion_requirement,
        "failure_condition": failure_condition,
        "capital_permission": _CAPITAL_LABEL.get(capital_action, _fmt(capital_action)),
        "seal_note": seal_note,
    }


def _authority_reconciliation_section(ev: dict) -> dict:
    """AUTHORITY RECONCILIATION.

    Answers THREE DISTINCT, never-collapsed questions from already-computed
    evidence only — never a new tiering judgment:

      A. HTF THESIS AUTHORIZATION (Weekly/Daily context + Daily/swing
         Structure) — AUTHORIZED / CONDITIONAL / NOT AUTHORIZED / UNAVAILABLE.
         Owned by _htf_thesis_authorization.
      B. LOCAL EXECUTION SEQUENCE (4H Break -> Acceptance -> 1H Retest ->
         Hold) — COMPLETE / INCOMPLETE / FAILED / UNAVAILABLE. Identical
         value to EXECUTION PROOF's "sequence" field (both derive from
         _local_execution_states/_local_execution_sequence), so the two
         sections can never disagree.
      C. CAPITAL READINESS — FULL / STARTER / NONE. Owned exclusively by
         final_tier via _CAPITAL_READINESS, identical to EXECUTION PROOF's
         capital_readiness field.

    Daily YES + Structure CONFIRMED + 4H WICK_ONLY is a real, valid case
    where (A) reads AUTHORIZED while (B) reads INCOMPLETE/FAILED — HTF
    thesis authorization is not proof the local execution sequence, let
    alone capital, is ready. Local proof itself is reported separately
    (local_proof) using the conservative BROKEN-outranks-IMPROVING
    precedence in _local_proof_narrative — a clean retest never hides a
    failed hold behind an optimistic "IMPROVING" read.
    """
    signal = ev["signal"]
    tiering_result = ev["tiering_result"]

    structure_state = _structure_event_state(signal.get("structure_event"))
    daily_permission = _daily_permission(ev)
    htf_thesis = _htf_thesis_authorization(ev, structure_state)

    states = _local_execution_states(ev)
    local_execution_sequence = _local_execution_sequence(states)
    local_proof = _local_proof_narrative(states)

    blockers = []
    if daily_permission != "YES":
        blockers.append(f"Daily permission {daily_permission}")
    if states["break"] != "CONFIRMED":
        blockers.append(f"4H break {states['break']}")
    if structure_state != "CONFIRMED":
        blockers.append(f"Daily/swing structure {structure_state}")

    final_tier = str(tiering_result.get("final_tier") or "WAIT").upper()
    return {
        "local_proof": local_proof,
        "htf_thesis_authorization": htf_thesis,
        "local_execution_sequence": local_execution_sequence,
        "blockers": blockers or [_DASH],
        "capital": _CAPITAL_READINESS.get(final_tier, "NONE"),
    }


# ---------------------------------------------------------------------------
# AUDIT INTEGRITY — Phase 14X.1 final integrity-conflict guard.
#
# Production already runs a downgrade-only consistency seal
# (src/snipe_confirmed_seal.py, applied upstream in the shared post-tiering
# judgment organ BEFORE this renderer ever sees the result) whose law is:
# SNIPE_IT/full capital/SNIPE routing may not survive an active confirmation
# blocker (failed hold, failed retest, incomplete 1H trigger, blocked gate,
# missing proof, HTF contextual block). In the normal path a completed
# result reaching this renderer should therefore already be internally
# coherent.
#
# This section is a DEFENSIVE, READ-ONLY check on the completed result this
# renderer actually received — it is not a second tiering engine, it never
# re-runs the seal's or the gate audit's logic, and it never mutates
# final_tier/capital_action. It only detects when the DISPLAYED evidence
# (already computed and rendered elsewhere in this same audit — local
# execution sequence, local proof, HTF thesis authorization, and the raw
# snipe_gate_audit/snipe_confirmed_seal fields) contradicts the DISPLAYED
# final-tier/capital claim, and says so plainly. Source truth (final_tier,
# capital_action) is never rewritten — only its trust status is reported.
# ---------------------------------------------------------------------------

# Mirrors src/snipe_confirmed_seal.py's own vocabulary (read, never imported/
# called — this module stays a pure, dependency-free renderer). A promotion
# state or audit label in these sets is something production's OWN seal/gate
# audit already treats as "not a clean confirmation."
_BLOCKING_PROMOTION_STATES = {"PROMOTION_BLOCKED", "PROMOTION_PENDING", "NOT_ELIGIBLE"}
_BLOCKING_AUDIT_LABELS = {
    "DISQUALIFIED", "STARTER_ONLY_VALID", "WATCH_ONLY_BLOCKED",
    "INSUFFICIENT_CONTEXT", "SNIPE_CONFIRMATION_BLOCKED",
}


def _audit_integrity_section(ev: dict, result: dict, tier_judgment: dict) -> dict:
    tiering_result = ev["tiering_result"]
    sga = ev["snipe_gate_audit"]
    seal = ev["snipe_confirmed_seal"]

    final_tier = str(result.get("final_tier") or tiering_result.get("final_tier") or "WAIT").upper()
    capital = _CAPITAL_READINESS.get(final_tier, "NONE")

    structure_state = _structure_event_state(ev["signal"].get("structure_event"))
    htf_thesis = _htf_thesis_authorization(ev, structure_state)
    states = _local_execution_states(ev)
    local_execution_sequence = _local_execution_sequence(states)
    local_proof = _local_proof_narrative(states)

    conflicts: list = []
    incomplete: list = []

    # Phase 14X.2 — cross-section proof-contradiction insurance check.
    # TIER JUDGMENT is now built from the identical authoritative retest/hold
    # precedence (_authoritative_proof_detail) as EXECUTION PROOF/DOCTRINE
    # SEQUENCE, so this should never fire in practice — it exists as a
    # regression guard comparing NORMALIZED evidence objects (never rendered
    # prose) in case the two ever drift apart again.
    tj_stale_texts = [
        m for m in (tier_judgment.get("missing_proof") or []) + (tier_judgment.get("broken_proof") or [])
        if m and m != _DASH
    ]
    if states["retest"] == "CONFIRMED" and any("retest" in t.lower() for t in tj_stale_texts):
        conflicts.append(
            "Authoritative retest is CONFIRMED but Tier Judgment lists a retest proof gap"
        )
    if states["hold"] == "CONFIRMED" and any("hold" in t.lower() for t in tj_stale_texts):
        conflicts.append(
            "Authoritative hold is CONFIRMED but Tier Judgment lists a hold proof gap"
        )
    if states["retest"] == "BROKEN" and not any("retest" in b.lower() for b in (tier_judgment.get("broken_proof") or []) if b != _DASH):
        conflicts.append(
            "Authoritative retest is BROKEN but Tier Judgment does not list it as broken"
        )
    if states["hold"] == "BROKEN" and not any("hold" in b.lower() for b in (tier_judgment.get("broken_proof") or []) if b != _DASH):
        conflicts.append(
            "Authoritative hold is BROKEN but Tier Judgment does not list it as broken"
        )

    # Clear conflict #1 — false SNIPE execution: SNIPE_IT claimed without a
    # complete local execution sequence. UNAVAILABLE (no evidence to judge)
    # is treated as an evidence gap, not a proven conflict — see the
    # "incomplete is not conflict" law.
    if final_tier == "SNIPE_IT":
        if local_execution_sequence in ("FAILED", "INCOMPLETE"):
            conflicts.append(
                f"SNIPE_IT claimed but local execution sequence is {local_execution_sequence}"
            )
        elif local_execution_sequence == _UNAVAILABLE:
            incomplete.append("local execution sequence evidence is UNAVAILABLE")

    # Clear conflict #2 — a failed critical local proof leg cannot coexist
    # with a capital-granting tier claim (STARTER or SNIPE_IT).
    if local_proof == "BROKEN" and final_tier in ("STARTER", "SNIPE_IT"):
        conflicts.append(
            f"{final_tier} claimed but local proof is BROKEN (a critical execution leg failed)"
        )

    # Clear conflict #3 — SNIPE_IT requires the HTF thesis to be actually
    # AUTHORIZED, not merely CONDITIONAL/NOT AUTHORIZED (matches real
    # production doctrine: CHOCH/early structure and non-granted Daily
    # permission are never sufficient for SNIPE-tier confirmation — see
    # src/prefilter.py._score_structure_event, setup_family_compiler.py's
    # valid_events, and snipe_gate_audit.py's BREAK_CONFIRMED gate, none of
    # which admit CHOCH as a confirmed break).
    if final_tier == "SNIPE_IT":
        if htf_thesis == _UNAVAILABLE:
            incomplete.append("HTF thesis authorization evidence is UNAVAILABLE")
        elif htf_thesis != "AUTHORIZED":
            conflicts.append(f"SNIPE_IT claimed but HTF thesis authorization is {htf_thesis}")

    # Clear conflict #4 — the completed result's OWN seal/gate-audit objects
    # already declare a contradiction. Read verbatim; never recomputed.
    if seal.get("applied") is True:
        corrected = str(seal.get("corrected_tier") or seal.get("sealed_tier") or "").upper().strip()
        if corrected and corrected != final_tier:
            conflicts.append(
                f"snipe_confirmed_seal.applied=True corrected_tier={corrected} "
                f"but final_tier is still {final_tier}"
            )
    if final_tier == "SNIPE_IT":
        promo = str(sga.get("promotion_state") or "").upper().strip()
        if promo in _BLOCKING_PROMOTION_STATES:
            conflicts.append(f"SNIPE_IT claimed but snipe_gate_audit.promotion_state is {promo}")
        blocked = _nonempty(sga.get("blocked_gate_names")) or _nonempty(sga.get("blocked_gates"))
        if blocked:
            conflicts.append(
                "SNIPE_IT claimed but blocked gates remain: "
                + ", ".join(_fmt_item(x) for x in blocked)
            )
        audit_label = str(sga.get("audit_label") or "").upper().strip()
        if audit_label in _BLOCKING_AUDIT_LABELS:
            conflicts.append(f"SNIPE_IT claimed but snipe_gate_audit.audit_label is {audit_label}")

    # De-duplicate while preserving order.
    seen, unique_conflicts = set(), []
    for c in conflicts:
        if c not in seen:
            seen.add(c)
            unique_conflicts.append(c)

    if unique_conflicts:
        status = "CONFLICT"
        trust = "DO NOT TREAT CAPITAL CLAIM AS VERIFIED UNTIL PIPELINE CONFLICT IS RECONCILED"
    elif incomplete:
        status = "INCOMPLETE"
        trust = "VERIFIED"
    else:
        status = "CONSISTENT"
        trust = "VERIFIED"

    return {
        "status": status,
        "source_final_tier": final_tier,
        "source_capital": capital,
        "conflicts": unique_conflicts or [_DASH],
        "incomplete_reasons": incomplete or [_DASH],
        "trust": trust,
    }


def _delivery_section(result: dict, ev: dict) -> dict:
    tiering_result = ev["tiering_result"]
    safe_for_alert = result.get("safe_for_alert")
    if safe_for_alert is None:
        safe_for_alert = tiering_result.get("safe_for_alert")
    alert_sent = result.get("alert_sent", False)
    return {
        "alert_eligible": "YES" if safe_for_alert else "NO",
        "alert_sent": "YES" if alert_sent else "NO",
        "dedup_reason": _fmt(result.get("dedup_reason")),
        "scan_id": _fmt(result.get("scan_id")),
    }


# ---------------------------------------------------------------------------
# Top-level build / render
# ---------------------------------------------------------------------------

def build_operator_audit(result: dict, config: dict | None = None) -> dict:
    """Build the full structured operator audit from a completed run_analyze()
    result. Pure function — reads only; never mutates `result`.
    """
    result = result if isinstance(result, dict) else {}
    ev = _extract(result)
    tier_judgment = _tier_judgment_section(ev, result)
    return {
        "status": result.get("status"),
        "verdict_capital": _verdict_capital_section(result, ev),
        "setup": _setup_section(ev),
        "doctrine_sequence": _doctrine_sequence_section(ev),
        "execution_proof": _execution_proof_section(ev),
        "timeframe_sovereignty": _timeframe_sovereignty_section(ev),
        "trade_location": _trade_location_section(ev),
        "candle_truth": _candle_truth_section(ev),
        "risk_runway": _risk_runway_section(ev),
        "authority_reconciliation": _authority_reconciliation_section(ev),
        "audit_integrity": _audit_integrity_section(ev, result, tier_judgment),
        "tier_judgment": tier_judgment,
        "delivery": _delivery_section(result, ev),
    }


def _render_doctrine_sequence(rows: list) -> list:
    lines = ["SWING DOCTRINE SEQUENCE", "─" * 30]
    for row in rows:
        level = f"  @ {row['level']}" if row.get("level") else ""
        lines.append(f"{row['icon']} {row['step']:<20} {row['state']:<12} {row['evidence']}{level}")
        if row.get("qualification_note"):
            lines.append(f"{'':<24}  {row['qualification_note']}")
    return lines


def _render_weekly(w: dict) -> list:
    if not w.get("available"):
        return [
            "WEEKLY — CAMPAIGN CONTEXT",
            f"  {_UNAVAILABLE}",
            f"  Campaign evidence: {w.get('campaign_evidence', 'INCOMPLETE')}",
        ]
    lines = [
        "WEEKLY — CAMPAIGN CONTEXT",
        f"  Monthly bias:     {w['monthly_bias']}",
        f"  Weekly campaign:  {w['weekly_campaign']}",
        f"  Location:         {w['location']} ({w['location_quality']})",
        f"  Posture:          {w['posture']}",
        f"  Campaign evidence:    {w['campaign_evidence']}",
        f"  Positive sponsorship: {w['positive_sponsorship']}",
        f"  Blocks SNIPE:     {'yes' if w['blocks_snipe'] else 'no'}",
    ]
    return lines


def _render_daily(d: dict) -> list:
    if not d.get("available"):
        return ["DAILY — SWING PERMISSION", f"  {_UNAVAILABLE}"]
    return [
        "DAILY — SWING PERMISSION",
        f"  Trend state:      {d['trend_state']}",
        f"  10 SMA:           {d['sma10']}",
        f"  20 SMA:           {d['sma20']}",
        f"  50 SMA:           {d['sma50']}",
        f"  200 SMA:          {d['sma200']}",
        f"  SMA alignment:    {d['sma_alignment']}",
        f"  Permission:       {d['permission']}  ({d['swing_state']})",
    ]


def _render_four_hour(f: dict) -> list:
    if not f.get("available"):
        return ["4H — OPERATIONAL LOCATION", f"  {_UNAVAILABLE}"]
    return [
        "4H — OPERATIONAL LOCATION",
        f"  Structural state: {f['structural_state']}",
        f"  Location:         {f['operational_location']}",
        f"  Readiness:        {f['operational_readiness']}",
        f"  Confidence:       {f['state_confidence']}",
        f"  Break state:      {f['break_state']}",
        f"  Retest state:     {f['retest_state']}",
        f"  Verdict:          {f['verdict']}",
    ]


def _render_one_hour(o: dict) -> list:
    if not o.get("available"):
        return ["1H — ENTRY PROOF", f"  {_UNAVAILABLE}"]
    return [
        "1H — ENTRY PROOF",
        f"  Trigger state:    {o['trigger_state']}",
        f"  Break level:      {o['break_level']}",
        f"  Retest:           {o['retest']}",
        f"  Hold:             {o['hold']}",
        f"  Last closed 1H:   {o['last_closed_state']}",
        f"  Current live 1H:  {o['live_state']}",
        f"  Readiness:        {o['readiness']}",
        f"  Score:            {o['score']} ({o['score_label']})",
        f"  Diagnostic:       {o['diagnostic']}",
    ]


def _render_authority_reconciliation(ar: dict) -> list:
    return [
        "─" * 32,
        "AUTHORITY RECONCILIATION",
        "─" * 32,
        f"  Local proof:               {ar['local_proof']}",
        f"  HTF thesis authorization:  {ar['htf_thesis_authorization']}",
        f"  Local execution sequence:  {ar['local_execution_sequence']}",
        f"  Capital readiness:         {ar['capital']}",
        "  Primary higher-authority blockers:",
        *[f"    • {b}" for b in ar["blockers"]],
        "  Interpretation: these are three separate questions. HTF thesis "
        "authorization does not mean the local execution sequence is "
        "complete; a complete local sequence does not by itself change "
        "capital readiness, which comes only from the final tier.",
    ]


def render_operator_audit(result: dict, config: dict | None = None) -> str:
    """Render the full MANUAL TICKER AUDIT text. Pure function — never
    mutates `result`, never performs I/O of any kind."""
    audit = build_operator_audit(result, config)
    vc = audit["verdict_capital"]
    setup = audit["setup"]
    exe = audit["execution_proof"]
    ts = audit["timeframe_sovereignty"]
    tl = audit["trade_location"]
    candle = audit["candle_truth"]
    risk = audit["risk_runway"]
    ar = audit["authority_reconciliation"]
    ai = audit["audit_integrity"]
    tj = audit["tier_judgment"]
    delivery = audit["delivery"]

    lines = [
        "━" * 32,
        f"🧙🏿‍♂️ MANUAL TICKER AUDIT — {vc['ticker']}",
        "━" * 32,
        "",
        f"VERDICT: {vc['badge']}",
        f"CAPITAL: {vc['capital_label']}",
        "",
        f"Scan price:                {vc['scan_price']}",
        f"Scan executed:             {vc['scan_executed']}",
        f"Model timestamp:           {vc['model_timestamp']}  (not used as scan authority)",
        f"Daily evidence status:     {vc['daily_evidence_status']}",
        f"Last closed daily date:    {vc['daily_last_closed_date']}",
        f"Live daily date:           {vc['daily_live_date']}",
        f"Raw score:                 {vc['raw_score']}",
        f"Final/calibrated score:    {vc['calibrated_score']}",
        f"Setup quality:             {vc['setup_quality']}",
        f"Entry quality/readiness:   {vc['entry_quality']}",
        "",
        "SETUP",
        f"  Family:    {setup['family']}",
        f"  State:     {setup['state']}",
        f"  Direction: {setup['direction']}",
        f"  Stage:     {setup['stage']}",
        "",
        "─" * 32,
    ]
    lines += _render_doctrine_sequence(audit["doctrine_sequence"])
    lines += [
        "",
        "─" * 32,
        "LOCAL EXECUTION PROOF",
        "─" * 32,
        f"  {exe['break']['icon']} 4H Break:   {exe['break']['state']} — {exe['break']['raw']}",
        f"  {exe['acceptance']['icon']} Acceptance: {exe['acceptance']['state']}",
        f"  {exe['retest']['icon']} 1H Retest:  {exe['retest']['state']} — {exe['retest']['raw']}",
        f"  {exe['hold']['icon']} 1H Hold:    {exe['hold']['state']} — {exe['hold']['raw']}",
        "",
        f"  Local sequence:    {exe['sequence']}",
        f"  Capital readiness: {exe['capital_readiness']}",
        f"  Authority:         {exe['authority']}",
        "",
        "─" * 32,
        "TIMEFRAME SOVEREIGNTY",
        "─" * 32,
    ]
    lines += _render_weekly(ts["weekly"])
    lines.append("")
    lines += _render_daily(ts["daily"])
    lines.append("")
    lines += _render_four_hour(ts["four_hour"])
    lines.append("")
    lines += _render_one_hour(ts["one_hour"])
    lines += [
        "",
        "(Locked law: Weekly = campaign context, Daily = swing permission, "
        "4H = operational location, 1H = trigger proof.)",
        "",
    ]
    lines += _render_authority_reconciliation(ar)
    lines += [
        "",
        "─" * 32,
        "AUDIT INTEGRITY",
        "─" * 32,
        f"  Status:                    {ai['status']}",
        f"  Source final tier:         {ai['source_final_tier']}",
        f"  Source capital readiness:  {ai['source_capital']}",
        "  Evidence conflicts:",
        *[f"    • {c}" for c in ai["conflicts"]],
        "  Evidence gaps (incomplete, not proven conflict):",
        *[f"    • {r}" for r in ai["incomplete_reasons"]],
        f"  Operator trust:            {ai['trust']}",
        "",
        "─" * 32,
        "TRADE LOCATION / KEY NUMBERS",
        "─" * 32,
        f"  Current price:       {tl['current_price']}",
        f"  Trigger:             {tl['trigger']}",
        f"  Zone ({tl['zone_type']}):  {tl['zone_low']}–{tl['zone_high']}",
        f"  Zone midpoint:       {tl['zone_mid']}",
        f"  10 SMA:              {tl['sma10']}",
        f"  20 SMA:              {tl['sma20']}",
        f"  50 SMA:              {tl['sma50']}",
        f"  200 SMA:             {tl['sma200']}",
        f"  Invalidation (DEFINED): {tl['invalidation']}",
        "  Targets (DEFINED — not hit/confirmed events):",
    ]
    if tl["targets"]:
        for t in tl["targets"]:
            lines.append(f"    {t['label']}: {t['level']}  ({t['reason']})  [reason: {t['reason_provenance']}]")
            if t.get("liquidity_validation"):
                lines.append(f"      Liquidity validation: {t['liquidity_validation']}")
    else:
        lines.append(f"    {_DASH}")
    lines += [
        f"  Distance to trigger:      {tl['dist_to_trigger_pct']}",
        f"  Distance to invalidation: {tl['dist_to_invalidation_pct']}",
        f"  Distance to T1:           {tl['dist_to_t1_pct']}",
        "",
        "─" * 32,
        "CANDLE TRUTH",
        "─" * 32,
    ]
    if candle.get("available"):
        if candle["generic_available"]:
            lines += [
                f"  LAST CLOSED CANDLE (timeframe: {candle['timeframe_label']})",
                f"    Body %:            {candle['body_pct']}",
                f"    Upper wick %:      {candle['upper_wick_pct']}",
                f"    Lower wick %:      {candle['lower_wick_pct']}",
                f"    Close position %:  {candle['close_position_pct']}",
                f"    Candle family:     {candle['candle_family']}",
                f"    Close quality:     {candle['close_quality']}",
                f"    Wick read:         {candle['wick_read']}",
                f"    Level reaction:    {candle['level_reaction']}",
            ]
        if candle["one_hour_candle"]:
            oh = candle["one_hour_candle"]
            if candle["generic_available"]:
                lines.append("")
            lines += [
                "  1H CANDLE TRUTH",
                f"    Event type:             {oh['event_type']}",
                f"    Closed candle confirms: {oh['closed_candle_confirms']}",
                f"    Body acceptance:        {oh['body_acceptance']}",
                f"    Wick rejection:         {oh['wick_rejection']}",
                f"    Follow-through:         {oh['follow_through_present']}",
                f"    Volume support:         {oh['volume_support']}",
            ]
        lines += [
            "",
            "  CURRENT LIVE 1H",
            f"    State: {candle['live_state']}",
            "",
            "  NEXT-CANDLE / FOLLOW-THROUGH OBLIGATION",
            f"    {candle['next_candle_verdict']} — {candle['display_text'] or _DASH}",
        ]
    else:
        lines.append(f"  {_UNAVAILABLE}")
    lines += [
        "",
        "(Locked law: body = accepted value, wick = exploration/rejection, "
        "close = control snapshot, next candle = verdict, live candle = "
        "information, not confirmation.)",
        "",
        "─" * 32,
        "RISK / RUNWAY",
        "─" * 32,
        f"  Executable trigger:        {risk['executable_trigger']}",
        f"  Reference price:           {risk['reference_price']}",
        f"  Invalidation (DEFINED):    {risk['invalidation']}",
        f"  Risk distance:             {risk['risk_distance']} ({risk['risk_distance_pct']})",
        f"  Target 1 (DEFINED):        {risk['t1']}",
        f"  Target 2 (DEFINED):        {risk['t2']}",
        f"  Reward to T1:              {risk['reward_t1_pct']}",
        f"  Reward to T2:              {risk['reward_t2_pct']}",
        f"  Source-provided R:R:       {risk['source_rr']}",
        f"  Executable-entry R:R:      {risk['executable_entry_rr']}",
        f"    Basis:                   {risk['executable_entry_rr_basis']}",
        f"  Reference R:R (scan-price): {risk['reference_rr']}",
        f"    Basis:                   {risk['reference_rr_basis']}",
        f"  Reported overhead:         {risk['reported_overhead']}",
        f"    Source:                  {risk['reported_overhead_source']}",
        f"  Structural overhead (deterministic): {risk['structural_overhead_status']}",
        f"    Level / distance:        {risk['structural_overhead_level']} / {risk['structural_overhead_distance_pct']}",
        f"  Path quality:              {risk['path_clarity_label']}",
        f"  Failure condition:         {risk['failure_condition']}",
        "",
        "─" * 32,
        "TIER JUDGMENT",
        "─" * 32,
        f"  FINAL TIER:              {tj['final_tier']}",
        f"  WHY THIS TIER:           {tj['why_this_tier']}",
        f"  WHY NOT THE NEXT TIER:   {tj['why_not_higher']}",
        f"  WHY NOT STARTER:         {tj['why_not_starter']}",
        f"  WHY NOT SNIPE_IT:        {tj['why_not_snipe_it']}",
        f"  PRIMARY BLOCKING GATE:   {tj['primary_blocker']}",
        "  MISSING PROOF:",
    ]
    for m in tj["missing_proof"]:
        lines.append(f"    • {m}")
    lines.append("  BROKEN / FAILED PROOF:")
    for b in tj["broken_proof"]:
        lines.append(f"    • {b}")
    lines += [
        f"  PROMOTION REQUIREMENT:   {tj['promotion_requirement']}",
        f"  DEMOTION / FAILURE COND: {tj['failure_condition']}",
        f"  CAPITAL PERMISSION:      {tj['capital_permission']}",
    ]
    if tj["seal_note"]:
        lines.append(f"  {tj['seal_note']}")
    lines += [
        "",
        "─" * 32,
        "DELIVERY / AUDIT",
        "─" * 32,
        f"  Alert eligible:   {delivery['alert_eligible']}",
        f"  Alert sent:       {delivery['alert_sent']}",
        f"  Dedup evaluation: {delivery['dedup_reason']}",
        f"  Scan ID:          {delivery['scan_id']}",
    ]
    return "\n".join(_sanitize(l) for l in lines)


def render_operator_audit_compact(result: dict, config: dict | None = None) -> str:
    """Legacy-equivalent short summary (kept for `!analyze TICKER compact`)."""
    result = result if isinstance(result, dict) else {}
    ticker = _fmt(result.get("ticker"))
    final_tier = _fmt(result.get("final_tier", "WAIT"))
    alert_sent = result.get("alert_sent", False)
    dedup_reason = _fmt(result.get("dedup_reason"))
    scan_id = _fmt(result.get("scan_id"))
    return (
        f"**{_sanitize(ticker)}** — {final_tier}\n"
        f"Alert sent: {alert_sent}  |  Dedup: {_sanitize(dedup_reason)}\n"
        f"Scan ID: {_sanitize(scan_id)}"
    )


def render_operator_audit_json(result: dict, config: dict | None = None) -> str:
    """Sanitized machine-readable audit JSON (whitelist-only via build_operator_audit)."""
    audit = build_operator_audit(result, config)
    return json.dumps(audit, indent=2, default=str)


def chunk_operator_audit(text: str, max_len: int = _DISCORD_MAX_CHARS) -> list:
    """Line-aware chunker, section boundaries preferred. Self-contained (no
    import of discord_alerts.chunk_message) so this module has zero Discord
    dependency.

    Lossless by construction: operates on text.splitlines(keepends=True) so
    every original character (including each line's own newline) is placed
    into exactly one chunk and chunks are joined with "".join(...) — never
    "\\n".join(...), which would silently drop the separator newline at
    whichever line a mid-stream flush happens to land on. "".join(chunks)
    always reconstructs the original text exactly.
    """
    if len(text) <= max_len:
        return [text]
    lines = text.splitlines(keepends=True)
    chunks: list = []
    cur: list = []
    cur_len = 0
    for line in lines:
        stripped = line.rstrip("\n")
        is_boundary = stripped.startswith("─" * 4) or stripped.startswith("━" * 4)
        if is_boundary and cur and cur_len + len(line) > max_len * 0.6:
            chunks.append("".join(cur))
            cur, cur_len = [], 0
        while len(line) > max_len:
            chunks.append(line[:max_len])
            line = line[max_len:]
        if cur_len + len(line) > max_len and cur:
            chunks.append("".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line)
    if cur:
        chunks.append("".join(cur))
    return chunks

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
  - Pure stdlib only (json, re) plus src.display_formatting.format_usd_price
    (itself pure/stdlib — see that module's docstring). No scanner/tiering/
    market-data/Discord/network imports.
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


def _fmt_pct(v) -> str:
    if v is None:
        return _DASH
    try:
        return f"{float(v):.2f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_ratio(v) -> str:
    if v is None:
        return _DASH
    try:
        return f"{float(v):.2f}:1"
    except (TypeError, ValueError):
        return _DASH


def _safe_dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _safe_list(v) -> list:
    return v if isinstance(v, list) else []


def _nonempty(v) -> list:
    return [x for x in _safe_list(v) if x not in (None, "", [])]


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


def _authoritative_proof_state(one_hour: dict, truth_key: str, table: dict, fallback_value) -> str:
    """Prefer the 1H engine's own truth state; fall back to signal-level enum."""
    if _one_hour_usable(one_hour):
        prh = _safe_dict(one_hour.get("pullback_retest_hold"))
        truth = str(prh.get(truth_key, "") or "").upper().strip()
        if truth in table:
            return table[truth]
    return _proof_state_of(fallback_value)


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
    tiering_result = ev["tiering_result"]
    signal = ev["signal"]
    final_tier = str(result.get("final_tier") or tiering_result.get("final_tier") or "WAIT").upper()
    capital_action = tiering_result.get("capital_action")
    calibration = ev["calibration"]

    setup_quality = (
        f"family={_fmt(signal.get('setup_family'))} / "
        f"structure={_fmt(signal.get('structure_event'))} / "
        f"trend={_fmt(signal.get('trend_state'))}"
    )
    candle_family = ev["candle_evidence"].get("candle_family")
    entry_quality = (
        f"retest={_fmt(signal.get('retest_status'))} / "
        f"hold={_fmt(signal.get('hold_status'))} / "
        f"candle={_fmt(candle_family)}"
    )

    return {
        "ticker": _fmt(signal.get("ticker") or result.get("ticker")),
        "final_tier": final_tier,
        "badge": _TIER_BADGE.get(final_tier, final_tier),
        "capital_label": _CAPITAL_LABEL.get(capital_action, _fmt(capital_action)),
        "scan_price": _fmt_price(signal.get("scan_price")),
        "scan_time": _fmt(signal.get("timestamp_et")),
        "raw_score": _fmt(tiering_result.get("score")),
        "calibrated_score": _fmt(calibration.get("calibrated_score")) if calibration else _DASH,
        "setup_quality": setup_quality,
        "entry_quality": entry_quality,
    }


def _setup_section(ev: dict) -> dict:
    signal = ev["signal"]
    retest_state = _proof_state_of(signal.get("retest_status"))
    hold_state = _proof_state_of(signal.get("hold_status"))
    structure_event = str(signal.get("structure_event") or "none").lower()

    if structure_event in ("", "none"):
        stage = _UNAVAILABLE
    elif structure_event == "failed_breakdown_reclaim":
        stage = "FAILED"
    elif retest_state == "CONFIRMED" and hold_state == "CONFIRMED":
        stage = "CONFIRMED"
    elif retest_state == "BROKEN" or hold_state == "BROKEN":
        stage = "FAILED"
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


def _doctrine_sequence_section(ev: dict) -> list:
    """Structure -> Liquidity -> Displacement -> Acceptance/Reclaim -> Retest
    -> Hold -> Invalidation -> Target.

    Liquidity/Displacement/Acceptance have no dedicated schema field; each is
    rendered as DERIVED_DISPLAY from the fields that do exist (structure_event,
    location_state, zone_type), explicitly labelled, never invented.
    """
    signal = ev["signal"]
    trade_location = ev["trade_location"]
    one_hour = ev["one_hour_entry"]

    structure_event = str(signal.get("structure_event") or "none")
    structure_state = (
        "BROKEN" if structure_event == "failed_breakdown_reclaim"
        else "MISSING" if structure_event.lower() == "none"
        else "CONFIRMED"
    )

    displacement_state = (
        "CONFIRMED" if structure_event in ("BOS", "MSS", "accepted_break")
        else "MISSING"
    )

    location_state = str(trade_location.get("location_state") or "")
    acceptance_state = (
        "CONFIRMED" if ("acceptance" in location_state.lower() or structure_event == "reclaim")
        else "FORMING" if location_state and location_state != "unknown"
        else "MISSING"
    )

    retest_state = _authoritative_proof_state(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state = _authoritative_proof_state(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )

    inval_level = signal.get("invalidation_level")
    invalidation_state = "CONFIRMED" if inval_level is not None else "MISSING"

    targets = _safe_list(signal.get("targets"))
    target_state = "CONFIRMED" if targets else "MISSING"

    rows = [
        ("Structure", structure_state, _fmt(signal.get("structure_event")), None),
        ("Liquidity", "UNAVAILABLE",
         "not modeled as a discrete field in the current schema", None),
        ("Displacement", displacement_state,
         f"derived from structure_event={_fmt(signal.get('structure_event'))}", None),
        ("Acceptance/Reclaim", acceptance_state, _fmt(trade_location.get("location_state")), None),
        ("Retest", retest_state, _fmt(signal.get("retest_status")), None),
        ("Hold", hold_state, _fmt(signal.get("hold_status")), None),
        ("Invalidation", invalidation_state,
         _fmt(signal.get("invalidation_condition")), _fmt_price(inval_level)),
        ("Target", target_state,
         f"{len(targets)} target(s)" if targets else _DASH,
         _fmt_price(targets[0].get("level")) if targets and isinstance(targets[0], dict) else None),
    ]
    return [
        {"step": step, "state": state, "icon": _icon(state), "evidence": evidence, "level": level}
        for step, state, evidence, level in rows
    ]


def _execution_proof_section(ev: dict) -> dict:
    signal = ev["signal"]
    trade_location = ev["trade_location"]
    one_hour = ev["one_hour_entry"]

    structure_event = str(signal.get("structure_event") or "none")
    break_state = (
        "BROKEN" if structure_event == "failed_breakdown_reclaim"
        else "MISSING" if structure_event.lower() == "none"
        else "CONFIRMED"
    )
    location_state = str(trade_location.get("location_state") or "")
    acceptance_state = (
        "CONFIRMED" if "acceptance" in location_state.lower()
        else "FORMING" if location_state and location_state != "unknown"
        else "MISSING"
    )
    retest_state = _authoritative_proof_state(
        one_hour, "retest_truth", _RETEST_TRUTH_STATE, signal.get("retest_status")
    )
    hold_state = _authoritative_proof_state(
        one_hour, "hold_truth", _HOLD_TRUTH_STATE, signal.get("hold_status")
    )

    states = [break_state, acceptance_state, retest_state, hold_state]
    if any(s == "BROKEN" for s in states):
        sequence = "FAILED"
    elif all(s == "CONFIRMED" for s in states):
        sequence = "COMPLETE"
    elif all(s == "MISSING" for s in states):
        sequence = _UNAVAILABLE
    else:
        sequence = "INCOMPLETE"

    final_tier = str(ev["tiering_result"].get("final_tier") or "WAIT").upper()

    return {
        "break": {"state": break_state, "icon": _icon(break_state)},
        "acceptance": {"state": acceptance_state, "icon": _icon(acceptance_state)},
        "retest": {"state": retest_state, "icon": _icon(retest_state)},
        "hold": {"state": hold_state, "icon": _icon(hold_state)},
        "sequence": sequence,
        "capital_readiness": _CAPITAL_READINESS.get(final_tier, "NONE"),
    }


def _weekly_section(ev: dict) -> dict:
    htf = ev["higher_timeframe_context"]
    if not htf or str(htf.get("data_status") or "").upper() != "OK":
        return {"available": False}
    supports = htf.get("supports_long_setup") is True
    weakens = htf.get("weakens_long_setup") is True
    if weakens:
        posture = "hostile"
    elif supports:
        posture = "supportive"
    else:
        posture = "mixed"
    return {
        "available": True,
        "monthly_bias": _fmt(htf.get("monthly_bias_state")),
        "weekly_campaign": _fmt(htf.get("weekly_campaign_state")),
        "location": _fmt(htf.get("campaign_location_label")),
        "location_quality": _fmt(htf.get("campaign_location_quality")),
        "posture": posture,
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
        "permission": _SWING_PERMISSION_MAP.get(swing_state, _UNAVAILABLE),
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
        "targets": [
            {"label": t.get("label"), "level": _fmt_price(t.get("level")), "reason": _sanitize(t.get("reason"))}
            for t in targets if isinstance(t, dict)
        ],
        "dist_to_trigger_pct": _fmt_pct(_pct_distance(scan_price, trigger)),
        "dist_to_invalidation_pct": _fmt_pct(_pct_distance(scan_price, inval_level)),
        "dist_to_t1_pct": _fmt_pct(_pct_distance(t1, scan_price)),
    }


def _candle_truth_section(ev: dict) -> dict:
    candle = ev["candle_evidence"]
    if not candle or str(candle.get("status") or "unknown") == "unknown":
        return {"available": False}
    return {
        "available": True,
        "body_pct": _fmt_pct(candle.get("body_pct")),
        "upper_wick_pct": _fmt_pct(candle.get("upper_wick_pct")),
        "lower_wick_pct": _fmt_pct(candle.get("lower_wick_pct")),
        "close_position_pct": _fmt_pct(candle.get("close_position_pct")),
        "candle_family": _fmt(candle.get("candle_family")),
        "close_quality": _fmt(candle.get("close_quality")),
        "wick_read": _fmt(candle.get("wick_read")),
        "level_reaction": _fmt(candle.get("level_reaction")),
        "next_candle_verdict": _fmt(candle.get("next_candle_verdict")),
        "candle_veto": _fmt(candle.get("candle_veto")),
        "display_text": _sanitize(candle.get("display_text")),
        "live_state": "information only — no confirmation authority until close",
    }


def _risk_runway_section(ev: dict) -> dict:
    signal = ev["signal"]
    one_hour = ev["one_hour_entry"]
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
    return {
        "trigger": _fmt_price(trigger),
        "invalidation": _fmt_price(signal.get("invalidation_level")),
        "risk_distance": _fmt_price(signal.get("risk_distance")),
        "risk_distance_pct": _fmt_pct(signal.get("risk_distance_pct")),
        "t1": _fmt_price(t1.get("level")),
        "t2": _fmt_price(t2.get("level")),
        "reward_t1_pct": _fmt_pct(_reward_pct(t1.get("level"), trigger)) if t1 else _DASH,
        "reward_t2_pct": _fmt_pct(_reward_pct(t2.get("level"), trigger)) if t2 else _DASH,
        "rr_t1": _fmt_ratio(signal.get("risk_reward")),
        "overhead": _fmt(signal.get("overhead_status")),
        "path_clarity": _fmt(path_quality.get("path_label")) if path_quality else _DASH,
        "failure_condition": _sanitize(signal.get("invalidation_condition")),
    }


def _tier_judgment_section(ev: dict, result: dict) -> dict:
    tiering_result = ev["tiering_result"]
    signal = ev["signal"]
    sga = ev["snipe_gate_audit"]
    ladder = ev["snipe_ladder"]
    seal = ev["snipe_confirmed_seal"]

    final_tier = str(result.get("final_tier") or tiering_result.get("final_tier") or "WAIT").upper()
    capital_action = tiering_result.get("capital_action")

    missing_proofs = _nonempty(sga.get("missing_proofs"))
    blocked_gates = _nonempty(sga.get("blocked_gate_names")) or _nonempty(sga.get("blocked_gates"))
    applied_vetoes = _nonempty(tiering_result.get("applied_vetoes"))

    # MISSING vs BROKEN law: retest/hold "failed" is broken; anything else
    # incomplete (missing/partial/forming) is missing, never invented as failed.
    broken: list = []
    missing: list = []
    if _proof_state_of(signal.get("retest_status")) == "BROKEN":
        broken.append("retest_status=failed")
    elif _proof_state_of(signal.get("retest_status")) != "CONFIRMED":
        missing.append(f"retest_status={_fmt(signal.get('retest_status'))}")
    if _proof_state_of(signal.get("hold_status")) == "BROKEN":
        broken.append("hold_status=failed")
    elif _proof_state_of(signal.get("hold_status")) != "CONFIRMED":
        missing.append(f"hold_status={_fmt(signal.get('hold_status'))}")
    for m in missing_proofs:
        missing.append(_fmt_item(m))
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
        "tier_judgment": _tier_judgment_section(ev, result),
        "delivery": _delivery_section(result, ev),
    }


def _render_doctrine_sequence(rows: list) -> list:
    lines = ["DOCTRINE SEQUENCE", "─" * 30]
    for row in rows:
        level = f"  @ {row['level']}" if row.get("level") else ""
        lines.append(f"{row['icon']} {row['step']:<20} {row['state']:<12} {row['evidence']}{level}")
    return lines


def _render_weekly(w: dict) -> list:
    if not w.get("available"):
        lines = ["WEEKLY — CAMPAIGN CONTEXT", f"  {_UNAVAILABLE}"]
        return lines
    return [
        "WEEKLY — CAMPAIGN CONTEXT",
        f"  Monthly bias:     {w['monthly_bias']}",
        f"  Weekly campaign:  {w['weekly_campaign']}",
        f"  Location:         {w['location']} ({w['location_quality']})",
        f"  Posture:          {w['posture']}",
        f"  Blocks SNIPE:     {'yes' if w['blocks_snipe'] else 'no'}",
    ]


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
        f"Scan time:                 {vc['scan_time']}",
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
        "EXECUTION PROOF",
        "─" * 32,
        f"  {exe['break']['icon']} Break:      {exe['break']['state']}",
        f"  {exe['acceptance']['icon']} Acceptance: {exe['acceptance']['state']}",
        f"  {exe['retest']['icon']} Retest:     {exe['retest']['state']}",
        f"  {exe['hold']['icon']} Hold:       {exe['hold']['state']}",
        "",
        f"  Sequence:          {exe['sequence']}",
        f"  Capital readiness: {exe['capital_readiness']}",
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
        f"  Invalidation:        {tl['invalidation']}",
        "  Targets:",
    ]
    if tl["targets"]:
        for t in tl["targets"]:
            lines.append(f"    {t['label']}: {t['level']}  ({t['reason']})")
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
        lines += [
            "  LAST CLOSED 1H",
            f"    Body %:            {candle['body_pct']}",
            f"    Upper wick %:      {candle['upper_wick_pct']}",
            f"    Lower wick %:      {candle['lower_wick_pct']}",
            f"    Close position %:  {candle['close_position_pct']}",
            f"    Candle family:     {candle['candle_family']}",
            f"    Close quality:     {candle['close_quality']}",
            f"    Wick read:         {candle['wick_read']}",
            f"    Level reaction:    {candle['level_reaction']}",
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
        f"  Trigger / entry:  {risk['trigger']}",
        f"  Invalidation:     {risk['invalidation']}",
        f"  Risk distance:    {risk['risk_distance']} ({risk['risk_distance_pct']})",
        f"  Target 1:         {risk['t1']}",
        f"  Target 2:         {risk['t2']}",
        f"  Reward to T1:     {risk['reward_t1_pct']}",
        f"  Reward to T2:     {risk['reward_t2_pct']}",
        f"  R:R T1:           {risk['rr_t1']}",
        f"  Overhead:         {risk['overhead']}",
        f"  Path clarity:     {risk['path_clarity']}",
        f"  Failure condition: {risk['failure_condition']}",
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
    dependency."""
    if len(text) <= max_len:
        return [text]
    chunks, cur, cur_len = [], [], 0
    for line in text.split("\n"):
        is_boundary = line.startswith("─" * 4) or line.startswith("━" * 4)
        if is_boundary and cur and cur_len + len(line) + 1 > max_len * 0.6:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
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

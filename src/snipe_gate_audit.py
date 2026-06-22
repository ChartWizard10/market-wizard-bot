"""Phase 14H — SNIPE_IT Gate Audit / Promotion Path Integrity.

A read-only diagnostic flight-recorder that explains WHY a candidate did or did
not qualify for SNIPE_IT. It records the per-gate proof matrix, an audit label,
a promotion state, and (critically) flags the anti-paralysis case where every
SNIPE gate appears complete yet final_tier is not SNIPE_IT.

Doctrine (permanent):
  - Diagnostic ONLY. It explains the decision tiering already made.
  - NEVER promotes, downgrades, routes, authorizes capital, or loosens a gate.
  - NEVER mutates tiering_result or any sub-object. Pure, re-entrant, never raises.
  - Reads existing objects only (final_signal, one_hour_entry,
    timeframe_alignment, trade_location, candle_evidence, enriched). Invents no
    proof and no levels.

No new indicators. No RSI/MACD/Bollinger/Stochastic. No SMA10 dependency.
"""

# ---------------------------------------------------------------------------
# Canonical enums
# ---------------------------------------------------------------------------

STATUS_VALUES = {"ENABLED", "DISABLED", "DEGRADED", "ERROR"}
AUDIT_LABELS = {
    "SNIPE_CONFIRMED", "STARTER_ONLY_VALID", "NEAR_ENTRY_PENDING",
    "WATCH_ONLY_BLOCKED", "DISQUALIFIED", "INSUFFICIENT_CONTEXT",
}
PROMOTION_STATES = {
    "ALREADY_SNIPE", "PROMOTION_READY", "PROMOTION_PENDING",
    "PROMOTION_BLOCKED", "NOT_ELIGIBLE", "UNKNOWN",
}
GRADES = {"A", "A-", "B+", "B", "C", "D", "F", "UNKNOWN"}
GATE_STATUSES = {"PASS", "BLOCK", "UNKNOWN"}

GATE_NAMES = [
    "HTF_CONTEXT_SUPPORTIVE", "DAILY_PERMISSION_GRANTED", "FOUR_H_LOCATION_VALID",
    "ONE_H_TRIGGER_CONFIRMED", "BREAK_CONFIRMED", "ACCEPTANCE_CONFIRMED",
    "RETEST_CONFIRMED", "HOLD_CONFIRMED", "INVALIDATION_CLEAR", "OVERHEAD_CLEAR",
    "PATH_CLEAN", "ASYMMETRY_VALID", "LIVE_EDGE_SAFE", "CANDLE_TRUTH_SUPPORTIVE",
    "NO_REACCEPTANCE_FAILURE",
]

# Scored critical gates (sum = 100). Audit-only scoring; never the scanner score.
_CRITICAL_POINTS = {
    "DAILY_PERMISSION_GRANTED": 10,
    "FOUR_H_LOCATION_VALID": 10,
    "ONE_H_TRIGGER_CONFIRMED": 15,
    "RETEST_CONFIRMED": 10,
    "HOLD_CONFIRMED": 15,
    "INVALIDATION_CLEAR": 10,
    "OVERHEAD_CLEAR": 10,
    "PATH_CLEAN": 5,
    "ASYMMETRY_VALID": 10,
    "CANDLE_TRUTH_SUPPORTIVE": 5,
}

# The 8 gates that must all PASS for SNIPE_CONFIRMED (OVERHEAD or PATH satisfies one).
_SNIPE_CRITICAL = (
    "DAILY_PERMISSION_GRANTED", "FOUR_H_LOCATION_VALID", "ONE_H_TRIGGER_CONFIRMED",
    "RETEST_CONFIRMED", "HOLD_CONFIRMED", "INVALIDATION_CLEAR", "ASYMMETRY_VALID",
)

_CAP_ANY_CRITICAL_BLOCK = 69
_CAP_ONE_H_BLOCK        = 49
_CAP_HOLD_BLOCK         = 59
_CAP_INVAL_BLOCK        = 59
_CAP_ASYM_BLOCK         = 59
_CAP_OVERHEAD_BLOCK     = 79
_CAP_CANDLE_BLOCK       = 79
_CAP_INSUFFICIENT       = 74

_CAPITAL_BLOCKS = {"wait_no_capital", "no_capital", "no_trade", "none", ""}
_CAPITAL_ALLOWS = {"full_quality_allowed", "starter_only"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_snipe_gate_audit(ticker, tiering_result, enriched_data=None, config=None) -> dict:
    """Build the SNIPE_IT gate-audit object. NEVER raises. Mutates nothing."""
    try:
        return _build(ticker, tiering_result or {}, enriched_data or {}, config or {})
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return error_snipe_gate_audit_object(str(exc))


def default_snipe_gate_audit_object() -> dict:
    return {
        "enabled": True,
        "status": "ENABLED",
        "audit_label": "INSUFFICIENT_CONTEXT",
        "promotion_state": "UNKNOWN",
        "snipe_score": 0,
        "raw_snipe_score": 0,
        "effective_snipe_score": 0,
        "score_blocked_by": [],
        "display_score_label": None,
        "snipe_grade": "UNKNOWN",
        "current_final_tier": None,
        "current_capital_action": None,
        "eligible_for_snipe_review": False,
        "passed_gates": [],
        "blocked_gates": [],
        "missing_proofs": [],
        "blocking_reasons": [],
        "promotion_triggers": [],
        "invalidation": {"level": None, "type": None, "clear": False, "source": None},
        "risk": {"rr": None, "risk_state": None, "risk_window_pct": None, "asymmetry_valid": False},
        "evidence_sources": {
            "tiering": False, "one_hour_entry": False, "timeframe_alignment": False,
            "trade_location": False, "candle_evidence": False,
        },
        "diagnostic_sentence": None,
    }


def degraded_snipe_gate_audit_object(reason: str) -> dict:
    obj = default_snipe_gate_audit_object()
    obj["status"] = "DEGRADED"
    obj["blocking_reasons"].append(str(reason))
    obj["diagnostic_sentence"] = _sentence("INSUFFICIENT_CONTEXT")
    return obj


def error_snipe_gate_audit_object(error: str) -> dict:
    obj = default_snipe_gate_audit_object()
    obj["status"] = "ERROR"
    obj["audit_label"] = "INSUFFICIENT_CONTEXT"
    obj["promotion_state"] = "UNKNOWN"
    obj["snipe_grade"] = "UNKNOWN"
    obj["snipe_score"] = 0
    obj["blocking_reasons"].append(f"snipe_gate_audit_error: {error}")
    obj["diagnostic_sentence"] = _sentence("INSUFFICIENT_CONTEXT")
    return obj


def safe_get(obj, *keys, default=None):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _gate(name, status, reason, source) -> dict:
    return {"gate": name, "status": status, "reason": reason, "source": source}


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(ticker, tiering_result, enriched, config) -> dict:
    cfg = config.get("snipe_gate_audit", {}) if isinstance(config, dict) else {}
    if cfg.get("enabled", True) is False:
        obj = default_snipe_gate_audit_object()
        obj["enabled"] = False
        obj["status"] = "DISABLED"
        obj["diagnostic_sentence"] = None
        return obj

    obj = default_snipe_gate_audit_object()

    signal = tiering_result.get("final_signal") or {}
    if not isinstance(signal, dict):
        signal = {}
    oh = tiering_result.get("one_hour_entry") or {}
    tf = tiering_result.get("timeframe_alignment") or {}
    tl = tiering_result.get("trade_location") or {}
    ce = tiering_result.get("candle_evidence") or {}

    final_tier = str(tiering_result.get("final_tier", "") or "").upper().strip()
    capital_action = str(tiering_result.get("capital_action", "") or "").lower().strip()
    safe_for_alert = bool(tiering_result.get("safe_for_alert", False))

    obj["current_final_tier"] = tiering_result.get("final_tier")
    obj["current_capital_action"] = tiering_result.get("capital_action")
    obj["evidence_sources"] = {
        "tiering": bool(signal),
        "one_hour_entry": bool(oh) and str(oh.get("status", "")).upper() != "DISABLED",
        "timeframe_alignment": bool(tf) and str(tf.get("status", "")).upper() != "DISABLED",
        "trade_location": bool(tl),
        "candle_evidence": bool(ce),
    }
    source_count = sum(1 for v in obj["evidence_sources"].values() if v)

    # ---- Evaluate every gate ---------------------------------------------
    gates = _evaluate_gates(
        signal, oh, tf, tl, ce, final_tier, capital_action, safe_for_alert, config
    )
    status_by_gate = {g["gate"]: g["status"] for g in gates}

    for g in gates:
        if g["status"] == "PASS":
            obj["passed_gates"].append(g)
        elif g["status"] == "BLOCK":
            obj["blocked_gates"].append(g)
            obj["blocking_reasons"].append(f"{g['gate']}: {g['reason']}")
        else:  # UNKNOWN
            obj["missing_proofs"].append(f"{g['gate']}: {g['reason']}")

    # ---- Eligibility ------------------------------------------------------
    structure = str(signal.get("structure_event", "none") or "none").lower().strip()
    eligible = final_tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY") and structure not in ("none", "")
    obj["eligible_for_snipe_review"] = eligible

    # ---- Sub-objects ------------------------------------------------------
    obj["invalidation"] = _invalidation_block(signal, oh, status_by_gate)
    obj["risk"] = _risk_block(signal, status_by_gate)

    # ---- Promotion triggers ----------------------------------------------
    obj["promotion_triggers"] = _promotion_triggers(signal, oh, status_by_gate)

    # ---- Derived flags ----------------------------------------------------
    capital_blocks = capital_action in _CAPITAL_BLOCKS
    critical_blocks = [
        name for name in _CRITICAL_POINTS
        if status_by_gate.get(name) == "BLOCK"
    ]
    has_critical_block = bool(critical_blocks)
    invalidating_block = any(
        status_by_gate.get(n) == "BLOCK"
        for n in ("ONE_H_TRIGGER_CONFIRMED", "NO_REACCEPTANCE_FAILURE", "ASYMMETRY_VALID")
    )
    all_critical_pass = all(
        status_by_gate.get(n) == "PASS" for n in _SNIPE_CRITICAL
    ) and (
        status_by_gate.get("OVERHEAD_CLEAR") == "PASS"
        or status_by_gate.get("PATH_CLEAN") == "PASS"
    )
    promotion_path = bool(obj["promotion_triggers"]) and not invalidating_block
    insufficient = (not signal) and source_count < 2

    # ---- Status -----------------------------------------------------------
    obj["status"] = "DEGRADED" if (
        not signal or not obj["evidence_sources"]["one_hour_entry"]
        or not obj["evidence_sources"]["timeframe_alignment"]
    ) else "ENABLED"

    # ---- Audit label ------------------------------------------------------
    obj["audit_label"] = _classify_audit_label(
        insufficient, final_tier, capital_action, capital_blocks,
        invalidating_block, has_critical_block, promotion_path,
    )

    # ---- Promotion state --------------------------------------------------
    some_critical_pass = any(
        status_by_gate.get(n) == "PASS" for n in _CRITICAL_POINTS
    )
    obj["promotion_state"] = _promotion_state(
        final_tier, all_critical_pass, has_critical_block, eligible,
        obj["promotion_triggers"], some_critical_pass,
    )

    # ---- Consistency seal (Phase 14K) --------------------------------------
    # PROMOTION_READY is a claim that the audit sees no remaining reason a
    # setup could not be reviewed/promoted. _promotion_state above only
    # checks the _SNIPE_CRITICAL subset, so a gate outside that subset (e.g.
    # LIVE_EDGE_SAFE blocked by a candle veto) could be BLOCKed while the
    # claim still stood. Gate evaluation already records every gate's true
    # status in blocked_gates/missing_proofs — seal against that full truth
    # before the claim is allowed to stand. Never invents a new enum value;
    # never auto-promotes; never loosens SNIPE_IT.
    obj["promotion_state"] = _seal_promotion_state(obj)

    # Anti-paralysis integrity concern: every SNIPE gate is complete but the
    # scanner did not promote. Surface it loudly (never auto-promote). Only
    # fires once promotion_state has survived the consistency seal above.
    if obj["promotion_state"] == "PROMOTION_READY":
        obj["blocking_reasons"].append(
            "SNIPE gates appear complete but final_tier is not SNIPE_IT."
        )

    # ---- Score → caps → grade --------------------------------------------
    raw = _score_gates(status_by_gate)
    capped = _apply_caps(raw, status_by_gate, critical_blocks, insufficient)
    effective, score_blocked_by, display_label = _seal_score(capped, status_by_gate)
    obj["raw_snipe_score"] = capped
    obj["effective_snipe_score"] = effective
    obj["score_blocked_by"] = score_blocked_by
    obj["display_score_label"] = display_label
    obj["snipe_score"] = effective
    obj["snipe_grade"] = _grade(effective)

    obj["diagnostic_sentence"] = _sentence(obj["audit_label"])
    return obj


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def _evaluate_gates(signal, oh, tf, tl, ce, final_tier, capital_action, safe, config) -> list:
    g = []

    tf_label = str(safe_get(tf, "alignment_label", default="") or "").upper()
    daily_state = str(safe_get(tf, "swing_timeframe", "state", default="") or "").upper()
    op_state = str(safe_get(tf, "operational_timeframe", "state", default="") or "").upper()
    loc_state = str(safe_get(tl, "location_state", default="") or "").lower()
    oh_loc = str(safe_get(oh, "location_realism", "label", default="") or "").upper()

    oh_state = str(safe_get(oh, "trigger_state", default="") or "").upper()
    oh_alert = str(safe_get(oh, "alert_truth_label", default="") or "").upper()
    oh_retest = str(safe_get(oh, "pullback_retest_hold", "retest_truth", default="") or "").upper()
    oh_hold = str(safe_get(oh, "pullback_retest_hold", "hold_truth", default="") or "").upper()
    oh_inval_clear = bool(safe_get(oh, "invalidation", "clear", default=False))
    oh_closed_confirms = bool(safe_get(oh, "candle_truth", "closed_candle_confirms", default=False))
    oh_event = str(safe_get(oh, "candle_truth", "event_type", default="") or "").upper()
    oh_path_label = str(safe_get(oh, "path_quality", "path_label", default="") or "").upper()
    oh_path_clear = bool(safe_get(oh, "path_quality", "overhead_clear_enough", default=False))

    retest = str(signal.get("retest_status", "") or "").lower()
    hold = str(signal.get("hold_status", "") or "").lower()
    structure = str(signal.get("structure_event", "none") or "none").lower()
    overhead = str(signal.get("overhead_status", "") or "").lower()
    inval_level = signal.get("invalidation_level")
    inval_cond = str(signal.get("invalidation_condition", "") or "").strip()
    rr = signal.get("risk_reward")
    risk_state = str(signal.get("risk_realism_state", "") or "").lower()

    ce_family = str(safe_get(ce, "candle_family", default="") or "").upper()
    ce_veto = str(safe_get(ce, "candle_veto", default="") or "").upper()
    ce_reaction = str(safe_get(ce, "level_reaction", default="") or "").upper()
    ce_status = str(safe_get(ce, "status", default="") or "").lower()

    min_rr = float(safe_get(config, "tiers", "snipe_it", "min_rr", default=3.0) or 3.0)

    # 1. HTF_CONTEXT_SUPPORTIVE
    if not tf_label:
        g.append(_gate("HTF_CONTEXT_SUPPORTIVE", "UNKNOWN", "no timeframe_alignment context", "timeframe_alignment.alignment_label"))
    elif tf_label in ("FULL_STACK_ALIGNED", "HTF_ALIGNED_TRIGGER_PENDING", "HTF_VALID_4H_REPAIR", "MIXED_ALIGNMENT"):
        g.append(_gate("HTF_CONTEXT_SUPPORTIVE", "PASS", f"alignment {tf_label}", "timeframe_alignment.alignment_label"))
    elif tf_label in ("CONFLICTED", "LOWER_TIMEFRAME_ONLY"):
        g.append(_gate("HTF_CONTEXT_SUPPORTIVE", "BLOCK", f"alignment {tf_label}", "timeframe_alignment.alignment_label"))
    else:
        g.append(_gate("HTF_CONTEXT_SUPPORTIVE", "UNKNOWN", f"alignment {tf_label}", "timeframe_alignment.alignment_label"))

    # 2. DAILY_PERMISSION_GRANTED
    if daily_state == "PERMISSION_GRANTED" or (final_tier in ("SNIPE_IT", "STARTER") and safe):
        g.append(_gate("DAILY_PERMISSION_GRANTED", "PASS", "daily swing permission granted", "timeframe_alignment.swing_timeframe.state/final_tier"))
    elif daily_state == "PERMISSION_DENIED":
        g.append(_gate("DAILY_PERMISSION_GRANTED", "BLOCK", "daily swing permission denied", "timeframe_alignment.swing_timeframe.state"))
    else:
        g.append(_gate("DAILY_PERMISSION_GRANTED", "UNKNOWN", f"daily permission {daily_state or 'unknown'} (forming/missing)", "timeframe_alignment.swing_timeframe.state"))

    # 3. FOUR_H_LOCATION_VALID
    if op_state == "LOCATION_VALID" or loc_state == "mid_zone_acceptance":
        g.append(_gate("FOUR_H_LOCATION_VALID", "PASS", "operational location valid", "timeframe_alignment.operational_timeframe.state/trade_location"))
    elif op_state == "LOCATION_HOSTILE" or loc_state == "below_zone_failure" or oh_loc in ("MIDRANGE_NO_EDGE", "HOSTILE_LOCATION", "MISSED_ENTRY"):
        g.append(_gate("FOUR_H_LOCATION_VALID", "BLOCK", "operational location hostile/midrange/missed", "timeframe_alignment.operational_timeframe.state/trade_location"))
    else:
        g.append(_gate("FOUR_H_LOCATION_VALID", "UNKNOWN", f"location {op_state or loc_state or 'unknown'} (repairing/extended/missing)", "timeframe_alignment.operational_timeframe.state"))

    # 4. ONE_H_TRIGGER_CONFIRMED
    if not oh and not oh_state:
        g.append(_gate("ONE_H_TRIGGER_CONFIRMED", "UNKNOWN", "no one_hour_entry object", "one_hour_entry.trigger_state"))
    elif oh_state in ("TRIGGER_LIVE", "HOLD_CONFIRMED") or oh_alert in ("CONFIRMED_TRIGGER", "LIVE_TRIGGER"):
        g.append(_gate("ONE_H_TRIGGER_CONFIRMED", "PASS", f"1H {oh_state or oh_alert}", "one_hour_entry.trigger_state"))
    elif oh_state in ("FAILED_RETEST", "INVALID_1H_TRIGGER") or oh_alert == "FAILED_TRIGGER":
        g.append(_gate("ONE_H_TRIGGER_CONFIRMED", "BLOCK", f"1H {oh_state or oh_alert}", "one_hour_entry.trigger_state"))
    else:
        g.append(_gate("ONE_H_TRIGGER_CONFIRMED", "UNKNOWN", f"1H {oh_state or 'pending'} (forming/weak/pending)", "one_hour_entry.trigger_state"))

    # 5. BREAK_CONFIRMED
    if ce_family == "FAILED_BREAK":
        g.append(_gate("BREAK_CONFIRMED", "BLOCK", "candle evidence shows failed break", "candle_evidence.candle_family"))
    elif structure in ("bos", "mss", "accepted_break", "reclaim", "failed_breakdown_reclaim"):
        g.append(_gate("BREAK_CONFIRMED", "PASS", f"structure_event={structure}", "final_signal.structure_event"))
    else:
        g.append(_gate("BREAK_CONFIRMED", "UNKNOWN", f"structure_event={structure or 'none'} (no explicit break)", "final_signal.structure_event"))

    # 6. ACCEPTANCE_CONFIRMED
    one_h_pass = g[3]["status"] == "PASS"
    if (retest == "confirmed" and hold == "confirmed") or one_h_pass:
        g.append(_gate("ACCEPTANCE_CONFIRMED", "PASS", "retest+hold confirmed or 1H trigger confirmed", "final_signal.retest_status/hold_status"))
    elif ce_family == "FAILED_BREAK" or ce_reaction in ("FAILED_ZONE", "LOST_LEVEL", "REJECTED"):
        g.append(_gate("ACCEPTANCE_CONFIRMED", "BLOCK", "acceptance denied / rejection at level", "candle_evidence.level_reaction"))
    else:
        g.append(_gate("ACCEPTANCE_CONFIRMED", "UNKNOWN", "acceptance still forming", "final_signal.retest_status/hold_status"))

    # 7. RETEST_CONFIRMED
    if retest == "confirmed" or oh_retest in ("RETEST_CORE_VALID", "RETEST_REAL"):
        g.append(_gate("RETEST_CONFIRMED", "PASS", "retest confirmed", "final_signal.retest_status/one_hour_entry"))
    elif retest == "failed" or oh_retest == "RETEST_MISSED" or oh_state == "FAILED_RETEST":
        g.append(_gate("RETEST_CONFIRMED", "BLOCK", "retest failed/missed", "final_signal.retest_status/one_hour_entry"))
    else:
        g.append(_gate("RETEST_CONFIRMED", "UNKNOWN", f"retest {retest or oh_retest or 'pending'} (partial/in-progress)", "final_signal.retest_status/one_hour_entry"))

    # 8. HOLD_CONFIRMED
    if hold == "confirmed" or oh_hold == "HOLD_CONFIRMED":
        g.append(_gate("HOLD_CONFIRMED", "PASS", "hold confirmed", "final_signal.hold_status/one_hour_entry"))
    elif hold == "failed" or oh_hold == "HOLD_FAILED":
        g.append(_gate("HOLD_CONFIRMED", "BLOCK", "hold failed", "final_signal.hold_status/one_hour_entry"))
    else:
        g.append(_gate("HOLD_CONFIRMED", "UNKNOWN", f"hold {hold or oh_hold or 'pending'} (weak/partial/forming)", "final_signal.hold_status/one_hour_entry"))

    # 9. INVALIDATION_CLEAR
    if (inval_level is not None and inval_cond) or oh_inval_clear:
        g.append(_gate("INVALIDATION_CLEAR", "PASS", "invalidation level + body-close rule present", "final_signal.invalidation_level/condition"))
    else:
        g.append(_gate("INVALIDATION_CLEAR", "UNKNOWN", "invalidation level/condition missing or ambiguous", "final_signal.invalidation_level/condition"))

    # 10. OVERHEAD_CLEAR
    if overhead == "clear" or (overhead == "moderate" and final_tier in ("SNIPE_IT", "STARTER")):
        g.append(_gate("OVERHEAD_CLEAR", "PASS", f"overhead {overhead or 'clear'}", "final_signal.overhead_status"))
    elif overhead == "blocked" or oh_path_label == "HOSTILE":
        g.append(_gate("OVERHEAD_CLEAR", "BLOCK", "overhead blocked / ceiling lock", "final_signal.overhead_status/one_hour_entry.path_quality"))
    else:
        g.append(_gate("OVERHEAD_CLEAR", "UNKNOWN", f"overhead {overhead or 'moderate'} (ambiguous)", "final_signal.overhead_status"))

    # 11. PATH_CLEAN
    if oh_path_clear or oh_path_label in ("CLEAN", "ACCEPTABLE") or overhead == "clear":
        g.append(_gate("PATH_CLEAN", "PASS", "path to target clean enough", "one_hour_entry.path_quality/final_signal.overhead_status"))
    elif oh_path_label == "HOSTILE" or overhead == "blocked":
        g.append(_gate("PATH_CLEAN", "BLOCK", "path blocked by overhead", "one_hour_entry.path_quality/final_signal.overhead_status"))
    else:
        g.append(_gate("PATH_CLEAN", "UNKNOWN", "path cleanliness unclear", "one_hour_entry.path_quality"))

    # 12. ASYMMETRY_VALID
    rr_f = _f(rr)
    if rr_f is None:
        g.append(_gate("ASYMMETRY_VALID", "UNKNOWN", "risk_reward missing", "final_signal.risk_reward"))
    elif rr_f >= min_rr and risk_state not in ("fragile", "invalid"):
        g.append(_gate("ASYMMETRY_VALID", "PASS", f"R:R {rr_f:.2f} >= {min_rr} and risk {risk_state or 'ok'}", "final_signal.risk_reward/risk_realism_state"))
    else:
        g.append(_gate("ASYMMETRY_VALID", "BLOCK", f"R:R {rr_f:.2f} or risk {risk_state} below SNIPE floor", "final_signal.risk_reward/risk_realism_state"))

    # 13. LIVE_EDGE_SAFE
    if ce_veto in ("HOSTILE_WICK", "FAILED_RETEST"):
        g.append(_gate("LIVE_EDGE_SAFE", "BLOCK", f"candle veto {ce_veto}", "candle_evidence.candle_veto"))
    elif ce_veto in ("OPEN_ONLY", "NO_CLOSE_CONFIRMATION", "NO_NEXT_CANDLE_VERDICT", "DOJI_AT_TRIGGER"):
        g.append(_gate("LIVE_EDGE_SAFE", "UNKNOWN", f"live-edge forming ({ce_veto})", "candle_evidence.candle_veto"))
    elif oh_closed_confirms or (ce_status == "ok" and ce_veto in ("NONE", "UNKNOWN", "")):
        g.append(_gate("LIVE_EDGE_SAFE", "PASS", "closed candle confirmation present", "one_hour_entry.candle_truth/candle_evidence"))
    else:
        g.append(_gate("LIVE_EDGE_SAFE", "UNKNOWN", "live-edge state unverified", "candle_evidence.candle_veto"))

    # 14. CANDLE_TRUTH_SUPPORTIVE
    if ce_family in ("DISPLACEMENT", "RETEST_HOLD", "CONTINUATION") or (oh_event == "DISPLACEMENT") or (oh_event in ("REJECTION", "TRAP_RECLAIM") and oh_closed_confirms):
        g.append(_gate("CANDLE_TRUTH_SUPPORTIVE", "PASS", f"candle {ce_family or oh_event} supportive", "candle_evidence.candle_family/one_hour_entry.candle_truth"))
    elif ce_family == "FAILED_BREAK" or oh_event == "FAILURE":
        g.append(_gate("CANDLE_TRUTH_SUPPORTIVE", "BLOCK", f"candle {ce_family or oh_event} failed/rejection", "candle_evidence.candle_family/one_hour_entry.candle_truth"))
    else:
        g.append(_gate("CANDLE_TRUTH_SUPPORTIVE", "UNKNOWN", f"candle {ce_family or oh_event or 'unknown'} indecision/forming", "candle_evidence.candle_family"))

    # 15. NO_REACCEPTANCE_FAILURE
    reacceptance_fail = (
        oh_state == "INVALID_1H_TRIGGER"
        or (oh_event == "FAILURE")
        or loc_state == "below_zone_failure"
        or ce_reaction in ("LOST_LEVEL", "FAILED_ZONE")
    )
    if reacceptance_fail:
        g.append(_gate("NO_REACCEPTANCE_FAILURE", "BLOCK", "price reaccepted below trigger/zone", "one_hour_entry/trade_location/candle_evidence"))
    elif oh or tl or ce:
        g.append(_gate("NO_REACCEPTANCE_FAILURE", "PASS", "no reacceptance failure detected", "one_hour_entry/trade_location/candle_evidence"))
    else:
        g.append(_gate("NO_REACCEPTANCE_FAILURE", "UNKNOWN", "no source to verify reacceptance", "one_hour_entry/trade_location/candle_evidence"))

    return g


# ---------------------------------------------------------------------------
# Sub-objects
# ---------------------------------------------------------------------------

def _invalidation_block(signal, oh, status_by_gate) -> dict:
    level = signal.get("invalidation_level")
    if level is None:
        level = safe_get(oh, "invalidation", "level")
    cond = signal.get("invalidation_condition") or safe_get(oh, "invalidation", "condition")
    return {
        "level": level,
        "type": str(cond) if cond else None,
        "clear": status_by_gate.get("INVALIDATION_CLEAR") == "PASS",
        "source": "final_signal.invalidation_level/condition",
    }


def _risk_block(signal, status_by_gate) -> dict:
    return {
        "rr": _f(signal.get("risk_reward")),
        "risk_state": signal.get("risk_realism_state"),
        "risk_window_pct": _f(signal.get("risk_distance_pct")),
        "asymmetry_valid": status_by_gate.get("ASYMMETRY_VALID") == "PASS",
    }


def _promotion_triggers(signal, oh, status_by_gate) -> list:
    triggers = []
    trigger_level = _f(signal.get("trigger_level"))
    inval_level = _f(signal.get("invalidation_level"))
    upgrade = str(signal.get("upgrade_trigger", "") or "").strip()

    if status_by_gate.get("ONE_H_TRIGGER_CONFIRMED") != "PASS" or status_by_gate.get("HOLD_CONFIRMED") != "PASS":
        if trigger_level is not None:
            triggers.append(f"1H closed hold above {trigger_level:.2f}")
        else:
            triggers.append("1H closed-hold confirmation")
    if status_by_gate.get("OVERHEAD_CLEAR") == "BLOCK":
        triggers.append("clear overhead resistance before full-size")
    if upgrade and upgrade.lower() not in ("none", "—", "-", "n/a"):
        triggers.append(f"acceptance per upgrade trigger: {upgrade}")
    if inval_level is not None:
        triggers.append(f"avoid body close below invalidation {inval_level:.2f}")
    return triggers


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_audit_label(
    insufficient, final_tier, capital_action, capital_blocks,
    invalidating_block, has_critical_block, promotion_path,
) -> str:
    if insufficient:
        return "INSUFFICIENT_CONTEXT"
    if final_tier == "SNIPE_IT":
        return "SNIPE_CONFIRMED"
    if capital_blocks and invalidating_block and not promotion_path:
        return "DISQUALIFIED"
    if capital_blocks and has_critical_block:
        return "WATCH_ONLY_BLOCKED"
    if final_tier == "STARTER" and capital_action == "starter_only":
        return "STARTER_ONLY_VALID"
    if final_tier == "NEAR_ENTRY" and capital_action in ("wait_no_capital", "no_capital", "none", ""):
        return "NEAR_ENTRY_PENDING"
    if capital_blocks:
        return "WATCH_ONLY_BLOCKED"
    return "INSUFFICIENT_CONTEXT"


def _promotion_state(
    final_tier, all_critical_pass, has_critical_block, eligible,
    promotion_triggers, some_critical_pass,
) -> str:
    if final_tier == "SNIPE_IT":
        return "ALREADY_SNIPE"
    if all_critical_pass:
        return "PROMOTION_READY"
    if has_critical_block:
        return "PROMOTION_BLOCKED"
    if eligible and some_critical_pass and promotion_triggers:
        return "PROMOTION_PENDING"
    if not eligible:
        return "NOT_ELIGIBLE"
    return "UNKNOWN"


def _seal_promotion_state(obj: dict) -> str:
    """Phase 14K consistency seal: PROMOTION_READY may never coexist with an
    active blocker. blocked_gates/missing_proofs already reflect the FULL
    15-gate matrix (not just the _SNIPE_CRITICAL subset), so this check is
    strictly more complete than the all_critical_pass computation above.

    Downgrades to PROMOTION_PENDING (an existing enum value — never invents a
    new one here) rather than erasing the READY signal entirely, since the
    setup may still be on a legitimate promotion path.
    """
    state = obj.get("promotion_state")
    if state != "PROMOTION_READY":
        return state
    if obj.get("blocked_gates") or obj.get("missing_proofs"):
        obj["blocking_reasons"].append(
            "Promotion state normalized: active blocker/missing proof present; "
            "downgraded from PROMOTION_READY to PROMOTION_PENDING."
        )
        return "PROMOTION_PENDING"
    return state


# ---------------------------------------------------------------------------
# Score → caps → grade
# ---------------------------------------------------------------------------

def _score_gates(status_by_gate) -> int:
    score = 0
    for name, pts in _CRITICAL_POINTS.items():
        st = status_by_gate.get(name, "UNKNOWN")
        if st == "PASS":
            score += pts
        elif st == "UNKNOWN":
            score += pts // 2
        # BLOCK adds 0
    return max(0, min(100, score))


def _apply_caps(raw, status_by_gate, critical_blocks, insufficient) -> int:
    caps = []
    if critical_blocks:
        caps.append(_CAP_ANY_CRITICAL_BLOCK)
    if status_by_gate.get("ONE_H_TRIGGER_CONFIRMED") == "BLOCK":
        caps.append(_CAP_ONE_H_BLOCK)
    if status_by_gate.get("HOLD_CONFIRMED") == "BLOCK":
        caps.append(_CAP_HOLD_BLOCK)
    if status_by_gate.get("INVALIDATION_CLEAR") == "BLOCK":
        caps.append(_CAP_INVAL_BLOCK)
    if status_by_gate.get("ASYMMETRY_VALID") == "BLOCK":
        caps.append(_CAP_ASYM_BLOCK)
    if status_by_gate.get("OVERHEAD_CLEAR") == "BLOCK":
        caps.append(_CAP_OVERHEAD_BLOCK)
    if status_by_gate.get("CANDLE_TRUTH_SUPPORTIVE") == "BLOCK":
        caps.append(_CAP_CANDLE_BLOCK)
    if insufficient:
        caps.append(_CAP_INSUFFICIENT)
    score = raw
    for c in caps:
        score = min(score, c)
    return max(0, min(100, score))


_SOFT_PROOF_BLOCK_CAP = 79   # mirrors the severity of the existing overhead/candle caps

# Gates that contribute to _CRITICAL_POINTS/_apply_caps already suppress the
# score on BLOCK. LIVE_EDGE_SAFE does not (by design — it is a live-edge/
# candle-truth proof, not a structural critical gate), so a HOSTILE_WICK veto
# could leave the score reading a clean, unblocked 100. Seal that gap here
# without touching the existing critical-gate scoring above.
_UNCAPPED_BLOCK_GATES = ("LIVE_EDGE_SAFE",)


def _seal_score(score, status_by_gate) -> tuple:
    """Phase 14K score-consistency seal.

    Returns (effective_score, score_blocked_by, display_score_label). Never
    raises the score — only ever caps it further, and only labels it when it
    actually changed something, so a genuinely clean 100 still reads as 100.
    """
    blocked_by = [g for g in _UNCAPPED_BLOCK_GATES if status_by_gate.get(g) == "BLOCK"]
    effective = score
    if blocked_by:
        effective = min(effective, _SOFT_PROOF_BLOCK_CAP)
    label = "raw/pre-block" if effective < score else None
    return effective, blocked_by, label


def _grade(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if s >= 90:
        return "A"
    if s >= 82:
        return "A-"
    if s >= 75:
        return "B+"
    if s >= 68:
        return "B"
    if s >= 55:
        return "C"
    if s >= 40:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Diagnostic sentence
# ---------------------------------------------------------------------------

def _sentence(label) -> str:
    return {
        "SNIPE_CONFIRMED": "SNIPE audit: all critical gates confirm; setup is already SNIPE_IT.",
        "STARTER_ONLY_VALID": (
            "SNIPE audit: starter valid, but SNIPE promotion waits for 1H closed-hold "
            "proof and cleaner full-size confirmation."
        ),
        "NEAR_ENTRY_PENDING": (
            "SNIPE audit: near-entry pending; promotion waits for closed hold confirmation "
            "and trigger acceptance."
        ),
        "WATCH_ONLY_BLOCKED": (
            "SNIPE audit: watch-only blocked; capital remains disabled until blocker resolves."
        ),
        "DISQUALIFIED": "SNIPE audit: disqualified; critical gate failure prevents promotion.",
        "INSUFFICIENT_CONTEXT": (
            "SNIPE audit: insufficient context; scanner cannot verify SNIPE gates without guessing."
        ),
    }.get(label, "SNIPE audit: insufficient context; scanner cannot verify SNIPE gates without guessing.")


# ---------------------------------------------------------------------------
# Optional compact Discord line (config-gated; one line only)
# ---------------------------------------------------------------------------

def render_snipe_audit_line(audit, config=None) -> str | None:
    """Return one compact diagnostic line, or None when disabled/missing.

    Gated on config snipe_gate_audit.render_compact_line (default False) — by
    default NO line is rendered (no alert bloat).
    """
    cfg = (config or {}).get("snipe_gate_audit", {}) if isinstance(config, dict) else {}
    if not cfg.get("render_compact_line", False):
        return None
    if not isinstance(audit, dict):
        return None
    if audit.get("enabled") is False or str(audit.get("status", "DISABLED")) == "DISABLED":
        return None
    label = str(audit.get("audit_label", "INSUFFICIENT_CONTEXT"))
    sentence = str(audit.get("diagnostic_sentence") or "").strip()
    # The diagnostic sentence already carries the "SNIPE audit:" prefix — strip it
    # so the compact line does not repeat it.
    if sentence.lower().startswith("snipe audit:"):
        sentence = sentence.split(":", 1)[1].strip()
    grade = str(audit.get("snipe_grade", "UNKNOWN"))
    score = audit.get("snipe_score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    return f"  SNIPE audit: {label} ({grade} {score}/100) — {sentence}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(val):
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f

"""Phase 14S — Unified SNIPE ladder judgment engine.

One internal opportunity ladder replaces the scared binary SNIPE logic:

    PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS

Public Discord tiers stay simple (NEAR_ENTRY / STARTER_ENTRY / SNIPER_ENTRY);
the internal judgment becomes graded. The ladder has AUTHORITY over the final
tier recommendation (applied upstream of the seal via apply_ladder_arbitration)
— it is not display-only.

Doctrine (permanent):
  - Core formula: Structure -> Liquidity -> Displacement -> Retest -> Hold ->
    Invalidation -> Target. Execution: Break -> Acceptance -> Retest -> Hold.
  - Missing proof is not failed proof. Repairing location is not broken
    location. HOLD_WEAK is not failure unless price accepts failure.
    RETEST_IN_PROGRESS is not failure when the base is alive. WATCH_ONLY is
    not automatically no-opportunity. A wick is not automatically bearish.
  - TRUE_HARD_FAILURE overrides every ladder tier. Missing invalidation and
    invalid R:R block STARTER and SNIPER. No fake sniper. No fear scanner.
  - The seal stays downgrade-only; promotion happens HERE, upstream, and only
    NEAR_ENTRY->STARTER or STARTER->SNIPE_IT (never from WAIT, never inside
    the seal).
  - Pure stdlib; never raises; never mutates its input in classify; the
    arbitration applies the recommendation using the existing tier machinery
    (tiering.CHANNEL_MAP/CAPITAL_MAP + sanitizers) exactly like the seal does.
  - No ticker whitelists. Every ticker is judged by the same formula.

Existing final_tier compatibility mapping (this repo has no literal "PASS"
tier; WAIT is the existing suppression tier):
    PASS          -> WAIT      (no_trade, suppressed)
    WATCH_C       -> NEAR_ENTRY (wait_no_capital)
    STARTER_B/A   -> STARTER    (starter_only)
    SNIPER_A/A+   -> SNIPE_IT   (full_quality_allowed)
"""

from src import snipe_blocker_taxonomy as tax
from src.display_formatting import format_usd_price

# ---------------------------------------------------------------------------
# Ladder vocabulary
# ---------------------------------------------------------------------------

PASS = "PASS"
WATCH_C = "WATCH_C"
STARTER_B = "STARTER_B"
STARTER_A = "STARTER_A"
SNIPER_A = "SNIPER_A"
SNIPER_A_PLUS = "SNIPER_A_PLUS"

LADDER_TIERS = (PASS, WATCH_C, STARTER_B, STARTER_A, SNIPER_A, SNIPER_A_PLUS)

_PUBLIC_MAP = {
    PASS: "SUPPRESSED",
    WATCH_C: "NEAR_ENTRY",
    STARTER_B: "STARTER_ENTRY",
    STARTER_A: "STARTER_ENTRY",
    SNIPER_A: "SNIPER_ENTRY",
    SNIPER_A_PLUS: "SNIPER_ENTRY",
}
_FINAL_TIER_MAP = {
    PASS: "WAIT",
    WATCH_C: "NEAR_ENTRY",
    STARTER_B: "STARTER",
    STARTER_A: "STARTER",
    SNIPER_A: "SNIPE_IT",
    SNIPER_A_PLUS: "SNIPE_IT",
}
_CAPITAL_MAP = {
    PASS: "no_trade",
    WATCH_C: "wait_no_capital",
    STARTER_B: "starter_only",
    STARTER_A: "starter_only",
    SNIPER_A: "full_quality_allowed",
    SNIPER_A_PLUS: "full_quality_allowed",
}
_LANE_MAP = {
    PASS: "NONE",
    WATCH_C: "WATCH",
    STARTER_B: "STARTER_THESIS",
    STARTER_A: "STARTER_ACTIONABLE",
    SNIPER_A: "SNIPER_CLEAN",
    SNIPER_A_PLUS: "SNIPER_A_PLUS",
}
_BASKET_SENTENCE = {
    WATCH_C: "Watch only; no capital; base not defended or proof too early.",
    STARTER_B: "Thesis starter; reduced-size only; proof alive but soft.",
    STARTER_A: "Actionable starter; reduced-size opportunity capture; full sniper proof incomplete.",
    SNIPER_A: "Clean sniper; full sequence complete; one or more soft caps prevent A+.",
    SNIPER_A_PLUS: "A+ sniper; complete sequence plus clean path/location/context.",
    PASS: "Failed or invalid setup; no scanner capital attention.",
}

# Severity classes
TRUE_HARD_FAILURE = "TRUE_HARD_FAILURE"
STARTER_BLOCKER = "STARTER_BLOCKER"
SNIPER_ONLY_BLOCKER = "SNIPER_ONLY_BLOCKER"
SOFT_CAP = "SOFT_CAP"
INFO_NOTE = "INFO_NOTE"

_STARTER_MIN_RR = 3.0
_SNIPE_MIN_RR = 3.0

_VALID_STRUCTURES = {
    "BOS", "MSS", "CHOCH", "RECLAIM", "ACCEPTED_BREAK",
    "FAILED_BREAKDOWN_RECLAIM", "CONTINUATION", "FRESH_EXPANSION",
}
_REAL_RETEST_TRUTHS = {"RETEST_CORE_VALID", "RETEST_REAL"}
_CONFIRMED_TRIGGERS = {"TRIGGER_LIVE", "HOLD_CONFIRMED", "TRIGGER_CONFIRMED"}
_FORMING_TRIGGERS = {"RETEST_IN_PROGRESS", "HOLD_FORMING", "PULLBACK_FORMING",
                     "APPROACHING_LOCATION", "TRIGGER_FORMING"}
_FAILED_TRIGGERS = {"FAILED_RETEST", "INVALID_1H_TRIGGER", "STALE_TRIGGER"}


# ---------------------------------------------------------------------------
# Safe read helpers
# ---------------------------------------------------------------------------

def _d(obj, *keys):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(k)
    return cur if isinstance(cur, dict) else {}


def _s(value) -> str:
    return str(value or "").upper().strip()


def _low(value) -> str:
    return str(value or "").lower().strip()


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ---------------------------------------------------------------------------
# Evidence card (normalized view over a live tiering_result OR persisted row)
# ---------------------------------------------------------------------------

def _signal_or_row(obj, signal, key, default=None):
    """Phase 14S.1 — persisted alert_history rows flatten final_signal fields
    onto the row's top level (state_store.record_alert never persists a nested
    final_signal dict). A live tiering_result always has the nested signal.
    Prefer the live signal's value; fall back to the row's top-level field so
    a recompute on a persisted row reads the same evidence a live
    tiering_result would have provided. Audit-render parity only — does not
    change ladder thresholds, promotion rules, or any live classification.
    """
    if isinstance(signal, dict) and signal.get(key) is not None:
        return signal.get(key)
    return obj.get(key, default)


def _card(obj) -> dict:
    if not isinstance(obj, dict):
        obj = {}
    signal = obj.get("final_signal") if isinstance(obj.get("final_signal"), dict) else {}
    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else {}
    tf = obj.get("timeframe_alignment") if isinstance(obj.get("timeframe_alignment"), dict) else {}
    htf = obj.get("higher_timeframe_context") if isinstance(obj.get("higher_timeframe_context"), dict) else {}
    tl = obj.get("trade_location") if isinstance(obj.get("trade_location"), dict) else {}

    prh = _d(oh, "pullback_retest_hold")
    path = _d(oh, "path_quality")
    candle = _d(oh, "candle_truth")
    oh_inval = _d(oh, "invalidation")

    retest_status = _low(signal.get("retest_status") if signal else obj.get("retest_status"))
    hold_status = _low(signal.get("hold_status") if signal else obj.get("hold_status"))

    rr = _num(_signal_or_row(obj, signal, "risk_reward"))
    inval_level = _num(_signal_or_row(obj, signal, "invalidation_level"))
    price = _num(_signal_or_row(obj, signal, "scan_price"))
    if price is None:
        price = _num(_signal_or_row(obj, signal, "current_price"))
    inval_clear = bool(
        (inval_level is not None and str(_signal_or_row(obj, signal, "invalidation_condition") or "").strip())
        or oh_inval.get("clear") is True
    )
    overhead = _low(_signal_or_row(obj, signal, "overhead_status"))
    path_label = _s(path.get("path_label"))
    path_ok = (
        path_label in ("CLEAN", "ACCEPTABLE")
        or path.get("overhead_clear_enough") is True
        or overhead == "clear"
        or (overhead == "moderate" and rr is not None and rr >= _STARTER_MIN_RR)
    )
    path_blocked = overhead == "blocked" or path_label == "HOSTILE"

    cc = tax.normalized_candle_context(obj)

    return {
        "signal": signal, "oh": oh, "tf": tf, "htf": htf, "tl": tl,
        "structure": _s(_signal_or_row(obj, signal, "structure_event")),
        "retest_status": retest_status, "hold_status": hold_status,
        "retest_truth": _s(prh.get("retest_truth")),
        "hold_truth": _s(prh.get("hold_truth")),
        "trigger": _s(oh.get("trigger_state")),
        "alert_truth": _s(oh.get("alert_truth_label")),
        "oh_present": bool(oh) and _s(oh.get("status")) not in ("", "DISABLED"),
        "freshness": _s(oh.get("data_freshness")),
        "candle_event": _s(candle.get("event_type")),
        "closed_confirms": candle.get("closed_candle_confirms"),
        "cc": cc,
        "rr": rr, "inval_level": inval_level, "price": price,
        "inval_clear": inval_clear,
        "overhead": overhead, "path_label": path_label,
        "path_ok": path_ok, "path_blocked": path_blocked,
        "oh_loc": _s(_d(oh, "location_realism").get("label")),
        "daily": _s(_d(tf, "swing_timeframe").get("state")),
        "four_h": _s(_d(tf, "operational_timeframe").get("state")),
        "align": _s(tf.get("alignment_label")),
        "weekly": _s(htf.get("weekly_campaign_state")),
        "tl_state": _low(tl.get("location_state")),
        "htf_blocks": htf.get("blocks_snipe_contextually") is True,
        "htf_weakens": htf.get("weakens_long_setup") is True,
        "ctx_grade": _s(htf.get("context_grade")),
        "monthly": _s(htf.get("monthly_bias")),
        "price_below_inval": (price is not None and inval_level is not None and price < inval_level),
    }


# ---------------------------------------------------------------------------
# Hard failure / blocker collection
# ---------------------------------------------------------------------------

def _hard_failures(c) -> list:
    """TRUE_HARD_FAILURE: real failed proof or invalid risk — blocks STARTER and
    SNIPER. Missing proof is NOT here (missing proof is not failed proof)."""
    hard = []
    if c["price_below_inval"]:
        hard.append("price accepted below invalidation")
    if not c["inval_clear"]:
        hard.append("invalidation missing or unclear")
    if c["rr"] is not None and c["rr"] < _STARTER_MIN_RR:
        hard.append(f"R:R {c['rr']:.2f} below starter threshold {_STARTER_MIN_RR}")
    if c["path_blocked"]:
        hard.append("path blocked by overhead")
    if c["daily"] == "PERMISSION_DENIED":
        hard.append("daily permission denied (bearish, not forming)")
    if c["four_h"] == "LOCATION_HOSTILE" or c["tl_state"] == "below_zone_failure":
        hard.append("4H location hostile / price below zone")
    if c["trigger"] in _FAILED_TRIGGERS:
        hard.append(f"1H trigger failed ({c['trigger']})")
    if c["hold_truth"] == "HOLD_FAILED":
        hard.append("hold failed")
    if c["retest_status"] == "failed" or c["hold_status"] == "failed":
        hard.append("signal-level retest/hold failed")
    if c["freshness"] == "STALE":
        hard.append("1H data stale")
    cc = c["cc"]
    if cc.get("candle_tier_effect") == tax.CAPITAL_BLOCKER and cc.get("candle_context") == "HOSTILE_REJECTION":
        # Only a HOSTILE rejection with real failure evidence counts as hard here;
        # the taxonomy already requires explicit failure or unproven entry-zone
        # acceptance. Unproven-without-failure is handled by base_alive below.
        if any(t in _low(cc.get("candle_context_reason")) for t in
               ("failed entry-zone", "proved failed", "below")):
            hard.append("hostile rejection: entry-zone acceptance failed")
    return hard


def _base_alive(c, hard) -> bool:
    """base_alive: the defended idea still exists and is proven enough for
    reduced-size consideration. Requires positive evidence — never inferred."""
    if hard:
        return False
    if c["structure"] not in _VALID_STRUCTURES:
        return False
    if c["retest_truth"] not in _REAL_RETEST_TRUTHS:
        return False
    if not c["inval_clear"]:
        return False
    if not c["path_ok"]:
        return False
    if c["rr"] is None or c["rr"] < _STARTER_MIN_RR:
        return False
    if c["price"] is not None and c["inval_level"] is not None and c["price"] < c["inval_level"]:
        return False
    if c["freshness"] == "STALE":
        return False
    return True


def _daily_sponsorship(c) -> str:
    """GRANTED | SPONSORED_FORMING | UNKNOWN | DENIED"""
    if c["daily"] == "PERMISSION_GRANTED":
        return "GRANTED"
    if c["daily"] == "PERMISSION_DENIED":
        return "DENIED"
    if c["daily"] in ("PERMISSION_FORMING", "FORMING") or (
        not c["daily"] and c["weekly"] in ("HTF_CONTINUATION", "BULLISH", "HTF_BULLISH")
    ):
        # Forming with weekly sponsorship, or unknown daily under a bullish
        # weekly campaign, counts as sponsored-forming (STARTER_B ceiling).
        if c["weekly"] in ("HTF_CONTINUATION", "BULLISH", "HTF_BULLISH"):
            return "SPONSORED_FORMING"
        return "UNKNOWN"
    return "UNKNOWN" if not c["daily"] else "UNKNOWN"


def _four_h_ok(c) -> str:
    """VALID | REPAIRING_IN_ZONE | REPAIRING | UNKNOWN | BROKEN"""
    if c["four_h"] == "LOCATION_VALID" or c["tl_state"] == "mid_zone_acceptance":
        return "VALID"
    if c["four_h"] == "LOCATION_HOSTILE" or c["tl_state"] == "below_zone_failure":
        return "BROKEN"
    if c["four_h"] in ("LOCATION_REPAIRING", "LOCATION_EXTENDED"):
        # Repairing inside a real defended zone (retest truth + price above
        # invalidation) is a live entry neighborhood, not a broken location.
        if c["retest_truth"] in _REAL_RETEST_TRUTHS and not c["price_below_inval"]:
            return "REPAIRING_IN_ZONE"
        return "REPAIRING"
    return "UNKNOWN"


def functionally_valid_repair(c_or_obj) -> bool:
    """4H LOCATION_REPAIRING that is functionally valid for a full sequence:
    full 1H proof + real retest truth + clear invalidation + open path. Used by
    the ladder (SNIPER on repair) and mirrored by the taxonomy so the seal
    cannot re-bury what the ladder legitimately graded."""
    c = c_or_obj if isinstance(c_or_obj, dict) and "cc" in c_or_obj else _card(c_or_obj)
    return (
        _four_h_ok(c) in ("VALID", "REPAIRING_IN_ZONE")
        and c["trigger"] in _CONFIRMED_TRIGGERS
        and c["retest_truth"] in _REAL_RETEST_TRUTHS
        and c["hold_truth"] == "HOLD_CONFIRMED"
        and c["inval_clear"] and c["path_ok"]
    )


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

def classify_snipe_ladder(card_or_row) -> dict:
    """Classify one candidate onto the unified ladder. Pure; never raises;
    never mutates input. Works on a live tiering_result or a persisted row."""
    try:
        return _classify(card_or_row)
    except Exception as exc:  # pragma: no cover - defensive; never break a scan
        out = _result(WATCH_C, base_alive=False, proof_state="FORMING_NO_CAPITAL")
        out["basket_reason"] = f"ladder classification error: {exc}"
        out["audit_tags"] = ["LADDER_ERROR"]
        return out


def _result(tier, base_alive, proof_state) -> dict:
    return {
        "internal_ladder_tier": tier,
        "public_signal_tier": _PUBLIC_MAP[tier],
        "existing_final_tier_recommendation": _FINAL_TIER_MAP[tier],
        "capital_action_recommendation": _CAPITAL_MAP[tier],
        "opportunity_lane": _LANE_MAP[tier],
        "starter_grade": tier if tier in (STARTER_B, STARTER_A) else "NONE",
        "sniper_grade": tier if tier in (SNIPER_A, SNIPER_A_PLUS) else "NONE",
        "base_alive": bool(base_alive),
        "proof_state": proof_state,
        "proof_failure": proof_state == "FAILED",
        "structure_state": "FORMING",
        "location_state": "NOT_CLOSE",
        "trigger_state": "NONE",
        "candle_state": "NO_REJECTION",
        "risk_state": "INVALID",
        "hard_failures": [],
        "starter_blockers": [],
        "sniper_only_blockers": [],
        "soft_caps": [],
        "info_notes": [],
        "basket_reason": _BASKET_SENTENCE[tier],
        "why_this_ladder_tier": "",
        "why_not_higher": "",
        "why_not_lower": "",
        "next_promotion_proof": [],
        "failure_condition": [],
        "audit_tags": [],
    }


def _classify(obj) -> dict:
    c = _card(obj)
    hard = _hard_failures(c)
    alive = _base_alive(c, hard)
    sponsorship = _daily_sponsorship(c)
    four_h = _four_h_ok(c)
    cc = c["cc"]
    candle_ctx = cc.get("candle_context")

    # ---- derived organ states ------------------------------------------------
    if c["structure"] in ("", "NONE"):
        structure_state = "FAILED"
    elif c["structure"] in _VALID_STRUCTURES:
        structure_state = "STRONG" if c["structure"] in ("BOS", "MSS") else "VALID"
    else:
        structure_state = "FORMING"

    location_state = {
        "VALID": "VALID", "REPAIRING_IN_ZONE": "REPAIRING", "REPAIRING": "REPAIRING",
        "BROKEN": "INVALID", "UNKNOWN": "NOT_CLOSE",
    }[four_h]

    if c["trigger"] in ("TRIGGER_LIVE",):
        trig_state = "LIVE"
    elif c["trigger"] in _CONFIRMED_TRIGGERS:
        trig_state = "CONFIRMED"
    elif c["trigger"] == "RETEST_IN_PROGRESS":
        trig_state = "RETEST_IN_PROGRESS"
    elif c["trigger"] in _FORMING_TRIGGERS:
        trig_state = "FORMING"
    else:
        trig_state = "NONE"

    candle_state = {
        "HOSTILE_REJECTION": "HOSTILE", "UNRESOLVED_REJECTION": "UNRESOLVED",
        "DEFENSIVE_REJECTION": "DEFENSIVE", "NO_REJECTION": "NO_REJECTION",
        "EXPANSION_REJECTION": "NO_REJECTION",  # base-scope truth; tagged below
        "UNKNOWN": "UNRESOLVED",
    }.get(candle_ctx, "UNRESOLVED")
    if any("entry-zone acceptance failed" in h or "hold failed" in h for h in hard):
        candle_state = "FAILED"

    if not c["inval_clear"] or c["rr"] is None or (c["rr"] is not None and c["rr"] < _STARTER_MIN_RR):
        risk_state = "INVALID"
    elif c["rr"] >= 4.0 and c["overhead"] == "clear":
        risk_state = "PRISTINE"
    elif c["overhead"] in ("clear", "") and c["path_label"] == "CLEAN":
        risk_state = "CLEAN"
    else:
        risk_state = "VALID"

    audit_tags = []
    if candle_ctx == "EXPANSION_REJECTION":
        audit_tags.append("EXPANSION_REJECTION_ADD_LEVEL_ONLY")

    # ---- blocker collection ---------------------------------------------------
    starter_blockers = []
    sniper_only = []
    soft_caps = []
    info_notes = []

    if not alive and not hard:
        if c["retest_truth"] not in _REAL_RETEST_TRUTHS:
            starter_blockers.append("no real retest truth yet (price approaching/falling into zone)")
        if not c["oh_present"]:
            starter_blockers.append("no 1H evidence organ (trigger proof unverifiable)")
        if c["rr"] is None:
            starter_blockers.append("R:R missing (asymmetry unproven)")
        if not c["inval_clear"]:
            starter_blockers.append("invalidation not yet clean")
        if not c["path_ok"]:
            starter_blockers.append("path/overhead not acceptable yet")
        if sponsorship == "DENIED":
            starter_blockers.append("daily permission denied")

    if alive:
        if c["trigger"] not in _CONFIRMED_TRIGGERS:
            sniper_only.append(f"1H trigger {c['trigger'] or 'pending'} (full-size trigger proof incomplete)")
        if c["hold_truth"] != "HOLD_CONFIRMED":
            sniper_only.append(f"hold_truth {c['hold_truth'] or 'unproven'} (full-size hold proof incomplete)")
        if four_h in ("REPAIRING_IN_ZONE", "REPAIRING") and not functionally_valid_repair(c):
            sniper_only.append("4H location repairing (not yet functionally valid for full size)")
        if candle_state == "UNRESOLVED":
            sniper_only.append("candle proof unresolved (no accepted failure)")
        if sponsorship in ("SPONSORED_FORMING", "UNKNOWN"):
            sniper_only.append("daily permission not fully granted")
        if c["htf_blocks"]:
            sniper_only.append("HTF context blocks full size (blocks_snipe_contextually=true)")
        if c["overhead"] == "moderate":
            soft_caps.append("overhead moderate (R:R still valid)")
        if c["htf_weakens"] and not c["htf_blocks"]:
            soft_caps.append("HTF extended/weakens (not contextually blocking)")
        if c["ctx_grade"] in ("B", "C") and not c["htf_blocks"]:
            soft_caps.append(f"HTF context grade {c['ctx_grade']} (not blocking)")
        if candle_state == "DEFENSIVE":
            soft_caps.append("defensive rejection (zone defended; supports the long)")
        if c["oh_loc"] == "ACCEPTABLE_BUT_NOT_IDEAL":
            soft_caps.append("location acceptable but not ideal")
    if c["monthly"] in ("", "UNKNOWN"):
        info_notes.append("monthly bias unknown (display only)")

    # ---- ladder decision -------------------------------------------------------
    if structure_state == "FAILED":
        tier = PASS
        proof = "FAILED"
        why = "no valid structure family — nothing to grade"
    elif hard:
        consequence = any(t in h for h in hard for t in
                          ("accepted below", "failed", "hostile", "denied", "hostile rejection"))
        tier = PASS if consequence else WATCH_C
        proof = "FAILED"
        why = "true hard failure: " + "; ".join(hard)
    elif not alive:
        tier = WATCH_C
        # Softer thesis basket: real retest evidence + clean risk + sponsorship,
        # but base not fully alive (e.g. daily only sponsored-forming).
        if (
            c["retest_truth"] in _REAL_RETEST_TRUTHS
            and c["inval_clear"] and c["path_ok"]
            and c["rr"] is not None and c["rr"] >= _STARTER_MIN_RR
            and sponsorship in ("GRANTED", "SPONSORED_FORMING")
        ):
            tier = STARTER_B
        elif (
            not c["oh_present"]  # signal-level retest may stand in ONLY when no
                                 # 1H organ exists to contradict it (1H sovereignty)
            and c["retest_status"] in ("confirmed", "partial")
            and c["inval_clear"] and c["path_ok"]
            and c["rr"] is not None and c["rr"] >= _STARTER_MIN_RR
            and sponsorship in ("GRANTED", "SPONSORED_FORMING")
            and c["structure"] in _VALID_STRUCTURES
            and not c["price_below_inval"]
        ):
            tier = STARTER_B
        proof = "ALIVE_INCOMPLETE" if tier == STARTER_B else "FORMING_NO_CAPITAL"
        why = ("retest evidence + clean risk under sponsorship, but base proof still soft"
               if tier == STARTER_B else
               "base not defended yet — proof too early for capital")
    else:
        # base is alive — grade the opportunity
        sequence_complete = (
            c["trigger"] in _CONFIRMED_TRIGGERS
            and c["hold_truth"] == "HOLD_CONFIRMED"
            and candle_state in ("NO_REJECTION", "DEFENSIVE")
            and sponsorship == "GRANTED"
            and (four_h == "VALID" or functionally_valid_repair(c))
            and not c["htf_blocks"]
        )
        if sequence_complete:
            pristine = (
                four_h == "VALID"
                and c["path_label"] == "CLEAN"
                and c["overhead"] in ("clear", "")
                and not soft_caps
                and c["align"] in ("FULL_STACK_ALIGNED",)
                and risk_state in ("CLEAN", "PRISTINE")
            )
            tier = SNIPER_A_PLUS if pristine else SNIPER_A
            proof = "PRISTINE" if pristine else "COMPLETE"
            why = ("complete sequence plus clean path/location/context"
                   if pristine else
                   "full sequence complete; soft caps prevent A+")
        else:
            # Actionable vs thesis starter
            hold_evidence = (
                c["hold_status"] == "confirmed" or c["hold_truth"] == "HOLD_CONFIRMED"
            )
            actionable = (
                sponsorship == "GRANTED"
                and hold_evidence
                and candle_state != "HOSTILE"
            )
            tier = STARTER_A if actionable else STARTER_B
            proof = "ALIVE_INCOMPLETE"
            why = ("base alive with defended hold evidence under granted daily permission; "
                   "full sniper proof incomplete"
                   if tier == STARTER_A else
                   "base alive but hold/sponsorship proof softer — thesis starter only")

    # ---- explanations ----------------------------------------------------------
    ladder_idx = LADDER_TIERS.index(tier)
    next_proofs = []
    if tier in (WATCH_C, STARTER_B, STARTER_A):
        if c["trigger"] not in _CONFIRMED_TRIGGERS:
            trig_level = _num(_signal_or_row(obj, c["signal"], "trigger_level"))
            next_proofs.append(
                f"1H closed hold above {format_usd_price(trig_level)}" if trig_level is not None
                else "1H closed-hold confirmation")
        if c["hold_truth"] != "HOLD_CONFIRMED":
            next_proofs.append("closed 1H hold_truth confirmation")
        if four_h not in ("VALID",):
            next_proofs.append("4H location repair completes (LOCATION_VALID)")
        if sponsorship != "GRANTED":
            next_proofs.append("daily permission granted")
        if candle_state == "UNRESOLVED":
            next_proofs.append("supportive/defensive closed candle verdict")
        if tier == WATCH_C:
            next_proofs.insert(0, "defended retest with real retest truth")
    elif tier == SNIPER_A:
        next_proofs.append("clear remaining soft caps for A+ "
                           f"({'; '.join(soft_caps) if soft_caps else 'location/path polish'})")

    failure_conditions = []
    if c["inval_level"] is not None:
        failure_conditions.append(f"body close below invalidation {format_usd_price(c['inval_level'])}")
    failure_conditions.append("accepted failure of the defended zone")

    why_not_higher = {
        PASS: "hard failure/invalid setup — no capital tier available",
        WATCH_C: "base not alive: " + ("; ".join(starter_blockers) if starter_blockers else "proof too early"),
        STARTER_B: "hold/sponsorship proof too soft for the actionable starter basket",
        STARTER_A: "full sniper proof incomplete: " + ("; ".join(sniper_only) if sniper_only else "1H trigger/hold not confirmed"),
        SNIPER_A: "soft caps remain: " + ("; ".join(soft_caps) if soft_caps else "location/path/context not pristine"),
        SNIPER_A_PLUS: "already best-in-class",
    }[tier]
    why_not_lower = {
        PASS: "n/a",
        WATCH_C: "structure/zone attention is still warranted" if structure_state != "FAILED" else "n/a",
        STARTER_B: "real retest evidence + clean invalidation/path/R:R under sponsorship — not a dead watchlist",
        STARTER_A: "base alive: defended retest truth, clean invalidation, valid path/R:R, no accepted failure",
        SNIPER_A: "full sequence complete: trigger, hold, candle, daily, location all proven",
        SNIPER_A_PLUS: "complete sequence plus clean path/location/context; no material blockers",
    }[tier]

    out = _result(tier, alive, proof)
    out.update({
        "structure_state": structure_state,
        "location_state": location_state,
        "trigger_state": trig_state,
        "candle_state": candle_state,
        "risk_state": risk_state,
        "hard_failures": hard,
        "starter_blockers": starter_blockers,
        "sniper_only_blockers": sniper_only,
        "soft_caps": soft_caps,
        "info_notes": info_notes,
        "why_this_ladder_tier": why,
        "why_not_higher": why_not_higher,
        "why_not_lower": why_not_lower,
        "next_promotion_proof": next_proofs,
        "failure_condition": failure_conditions,
        "audit_tags": audit_tags,
    })
    return out


# ---------------------------------------------------------------------------
# Fear-downgrade diagnostic
# ---------------------------------------------------------------------------

_FEAR_ONLY_MARKERS = ("HOLD_WEAK", "RETEST_IN_PROGRESS", "LOCATION_REPAIRING", "WATCH_ONLY")


def is_fear_downgrade_candidate(obj, ladder=None) -> bool:
    """A row that landed NEAR_ENTRY/no-capital although its base is alive and
    the only depressors are fear markers (HOLD_WEAK / RETEST_IN_PROGRESS /
    LOCATION_REPAIRING / WATCH_ONLY) with invalidation, path, and R:R intact."""
    if not isinstance(obj, dict):
        return False
    tier = _s(obj.get("final_tier") or obj.get("tier"))
    if tier not in ("NEAR_ENTRY", "WATCHLIST"):
        return False
    ladder = ladder if isinstance(ladder, dict) else classify_snipe_ladder(obj)
    if not ladder.get("base_alive"):
        return False
    if ladder.get("hard_failures"):
        return False
    c = _card(obj)
    markers = {c["hold_truth"], c["trigger"], c["four_h"], c["alert_truth"]}
    return any(m in _FEAR_ONLY_MARKERS for m in markers)


def ladder_distribution(rows) -> dict:
    """Internal diagnostic counts over history rows (read-only)."""
    counts = {t: 0 for t in LADDER_TIERS}
    counts.update({"HARD_FAILURE_BLOCKED": 0, "STARTER_BLOCKED": 0,
                   "SOFT_ONLY_BLOCKED": 0, "FEAR_DOWNGRADE_CANDIDATE": 0})
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ladder = classify_snipe_ladder(row)
        counts[ladder["internal_ladder_tier"]] += 1
        if ladder["hard_failures"]:
            counts["HARD_FAILURE_BLOCKED"] += 1
        elif ladder["starter_blockers"] and ladder["internal_ladder_tier"] == WATCH_C:
            counts["STARTER_BLOCKED"] += 1
        elif not ladder["sniper_only_blockers"] and ladder["soft_caps"] and \
                ladder["internal_ladder_tier"] not in (SNIPER_A, SNIPER_A_PLUS):
            counts["SOFT_ONLY_BLOCKED"] += 1
        if is_fear_downgrade_candidate(row, ladder):
            counts["FEAR_DOWNGRADE_CANDIDATE"] += 1
    return counts


# ---------------------------------------------------------------------------
# Arbitration (the authority step — runs upstream of the seal)
# ---------------------------------------------------------------------------

# Promotions the ladder may apply. NEVER from WAIT (hard-veto territory), never
# any other jump; downgrades follow the ladder freely. The seal downstream
# remains downgrade-only and can still veto a promoted SNIPE with hard proof.
_ALLOWED_PROMOTIONS = {
    ("NEAR_ENTRY", "STARTER"),
    ("STARTER", "SNIPE_IT"),
}

_TIER_ORDER = {"WAIT": 0, "PASS": 0, "NEAR_ENTRY": 1, "WATCHLIST": 1, "STARTER": 2, "SNIPE_IT": 3}

# Phase 14S.7 — diagnostic reasons for the direct NEAR_ENTRY -> SNIPE_IT path.
DIRECT_SNIPE_ALLOWED_REASON = "DIRECT_NEAR_ENTRY_TO_SNIPE_ALLOWED_BY_COMPLETE_SNIPER_PROOF"
DIRECT_SNIPE_BLOCKED_REASON = "DIRECT_SNIPE_BLOCKED_BY_INCOMPLETE_CAPITAL_PROOF"

# Phase 14S.7B — doctrine floor mirrored from config
# tiers.snipe_it.min_risk_distance_pct. A stop tighter than this is fake
# asymmetry: it INFLATES R:R rather than earning it, so it must never
# authorize SNIPE capital on the direct promotion path.
_DEFAULT_MIN_RISK_DISTANCE_PCT = 0.35

# Phase 14S.7B hardening — the capital floor fails CLOSED. When the floor
# evaluator cannot complete, this named violation stands in for a proven
# breach, so SNIPE capital is withdrawn exactly as any other floor breach
# withdraws it. Unknown safety state is not permission.
FLOOR_EVALUATION_ERROR_REASON = "SNIPE_CAPITAL_FLOOR_EVALUATION_ERROR"


def _min_risk_distance_pct(config) -> float:
    try:
        tier_cfg = ((config or {}).get("tiers") or {}).get("snipe_it") or {}
        return float(tier_cfg.get("min_risk_distance_pct", _DEFAULT_MIN_RISK_DISTANCE_PCT))
    except (TypeError, ValueError, AttributeError):
        return _DEFAULT_MIN_RISK_DISTANCE_PCT


def allow_direct_near_entry_to_snipe_when_sniper_complete(obj, ladder, config=None):
    """Phase 14S.7 — may a NEAR_ENTRY baseline jump straight to SNIPE_IT?

    The Phase 14S one-rung cap made a complete, pristine sniper wait an extra
    scan purely because the Claude/tiering baseline label arrived as
    NEAR_ENTRY. When the full sniper proof is already complete, hard failures
    are absent, and the downgrade-only seal still runs afterwards, the scanner
    should tell that truth now rather than a scan later.

    This gate is deliberately STRICTER than SNIPER_A alone. A SNIPER_A grade
    can be reached on a still-open bar via the Phase 14Q defensive-rejection
    rule; doctrine forbids an open candle from creating SNIPE authority, so the
    two-rung jump additionally demands EXPLICIT closed-candle confirmation.
    A defensive-but-unclosed candidate keeps the existing behavior (one rung to
    STARTER, and it may earn SNIPE on a later scan) — the extra rung costs a
    higher bar, never a lower one.

    Returns (allowed: bool, reason: str). Never raises.
    """
    try:
        grade = str((ladder or {}).get("internal_ladder_tier") or "").upper()
        if grade not in (SNIPER_A, SNIPER_A_PLUS):
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: ladder grade {grade or 'UNKNOWN'} is not a sniper grade"
        if (ladder or {}).get("hard_failures"):
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: hard failure present"
        if (ladder or {}).get("starter_blockers"):
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: starter blocker present"

        c = _card(obj)

        # Closed proof is mandatory for the direct jump — never an open bar alone.
        if c["closed_confirms"] is not True:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: no closed-candle confirmation"
        if c["cc"].get("candle_context") in (tax.CC_HOSTILE, tax.CC_UNRESOLVED, tax.CC_UNKNOWN):
            return False, (f"{DIRECT_SNIPE_BLOCKED_REASON}: candle context "
                           f"{c['cc'].get('candle_context')}")
        # Closed retest + closed hold defense.
        if c["retest_truth"] not in _REAL_RETEST_TRUTHS:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: retest truth {c['retest_truth'] or 'NONE'} not real"
        if c["hold_truth"] != "HOLD_CONFIRMED":
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: hold truth {c['hold_truth'] or 'NONE'} not confirmed"
        if c["trigger"] not in _CONFIRMED_TRIGGERS:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: 1H trigger {c['trigger'] or 'NONE'} not confirmed"
        if c["alert_truth"] in tax._NON_CONFIRMED_ALERT_TRUTHS:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: alert truth {c['alert_truth']}"

        # Risk contract must be real and numeric.
        if c["inval_level"] is None or not c["inval_clear"]:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: invalidation missing or unclear"
        if c["price"] is not None and c["price"] < c["inval_level"]:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: price accepted below invalidation"
        if c["rr"] is None or c["rr"] < _SNIPE_MIN_RR:
            return False, (f"{DIRECT_SNIPE_BLOCKED_REASON}: R:R "
                           f"{c['rr'] if c['rr'] is not None else 'missing'} below SNIPE threshold {_SNIPE_MIN_RR}")
        signal = obj.get("final_signal") if isinstance(obj, dict) else {}
        signal = signal if isinstance(signal, dict) else {}
        if not signal.get("targets"):
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: no target path"

        # Fake tight stop: a sub-floor risk distance inflates R:R instead of
        # earning it. Prefer the already-computed signal field; fall back to
        # deriving it from price/invalidation.
        min_rd = _min_risk_distance_pct(config)
        risk_dist_pct = _num(signal.get("risk_distance_pct"))
        if risk_dist_pct is None and c["price"] and c["inval_level"] is not None:
            try:
                risk_dist_pct = abs(c["price"] - c["inval_level"]) / c["price"] * 100.0
            except (TypeError, ZeroDivisionError):
                risk_dist_pct = None
        if risk_dist_pct is not None and risk_dist_pct < min_rd:
            return False, (f"{DIRECT_SNIPE_BLOCKED_REASON}: fake tight stop — risk distance "
                           f"{risk_dist_pct:.3f}% below floor {min_rd}%")

        # Path / location / data quality.
        if c["path_blocked"] or not c["path_ok"]:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: path or overhead blocked"
        if c["freshness"] == "STALE":
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: stale 1H data"
        if c["htf_blocks"]:
            return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: HTF context blocks full size"

        return True, f"{DIRECT_SNIPE_ALLOWED_REASON}: {grade} complete closed sniper proof"
    except Exception:  # pragma: no cover - defensive; never break a scan
        return False, f"{DIRECT_SNIPE_BLOCKED_REASON}: evaluation error"


def snipe_capital_floor_violation(obj, config=None):
    """Phase 14S.7B — capital-grade floor every SNIPE_IT outcome must clear.

    Returns a reason string when a SNIPE_IT result must NOT stand, else None.

    This is deliberately path-independent. The risk-distance floor is doctrine
    (`tiers.snipe_it.min_risk_distance_pct`, default 0.35): a stop tighter than
    the floor INFLATES R:R rather than earning it, so it is fake asymmetry.
    tiering.py already blocks both SNIPE_IT and STARTER on that condition, so
    the ladder must not be able to hand back SNIPE capital through ANY route —
    the SNIPE_IT baseline pass-through, the STARTER->SNIPE_IT single rung, or
    the NEAR_ENTRY->SNIPE_IT direct jump.

    Risk distance is checked on every basis that is computable: an explicit
    risk_distance_pct field, trigger-vs-invalidation (tiering.py's own
    convention), and price-vs-invalidation. If ANY computable basis is below
    the floor the setup is blocked — a genuine setup has a real stop on both.
    Never raises.

    FAIL-CLOSED: an unexpected error inside this evaluator returns
    FLOOR_EVALUATION_ERROR_REASON — a real violation — not None. A capital
    floor that cannot prove itself satisfied must not authorize SNIPE capital.
    Unknown safety state is not permission.
    """
    try:
        if not isinstance(obj, dict):
            return None
        signal = obj.get("final_signal")
        signal = signal if isinstance(signal, dict) else {}

        inval = _num(signal.get("invalidation_level"))
        if inval is None:
            return "no numeric invalidation"
        if not signal.get("targets"):
            return "no target path"
        rr = _num(signal.get("risk_reward"))
        if rr is None or rr < _SNIPE_MIN_RR:
            return f"R:R {rr if rr is not None else 'missing'} below SNIPE threshold {_SNIPE_MIN_RR}"

        floor = _min_risk_distance_pct(config)
        price = _num(signal.get("scan_price")) or _num(signal.get("current_price"))
        trigger = _num(signal.get("trigger_level"))

        bases = []
        explicit = _num(signal.get("risk_distance_pct"))
        if explicit is not None:
            bases.append(("risk_distance_pct", explicit))
        # tiering.py convention: (trigger - invalidation) / |trigger| * 100
        if trigger is not None and trigger != 0:
            dist = (trigger - inval) / abs(trigger) * 100.0
            if dist > 0:
                bases.append(("trigger-vs-invalidation", dist))
        if price is not None and price != 0:
            dist = (price - inval) / abs(price) * 100.0
            if dist > 0:
                bases.append(("price-vs-invalidation", dist))

        for name, dist in bases:
            if dist < floor:
                return (f"fake tight stop — risk distance {dist:.3f}% ({name}) "
                        f"below floor {floor}%")
        return None
    except Exception as exc:
        # FAIL CLOSED. Every other defensive handler in this module protects the
        # scan from crashing; this one additionally protects capital. If the
        # floor evaluator itself errors we cannot assert the risk contract, so
        # the only safe answer is a violation.
        return f"{FLOOR_EVALUATION_ERROR_REASON}: {type(exc).__name__}"


# ---------------------------------------------------------------------------
# Phase 14S.7C — transactional SNIPE capital safety
# ---------------------------------------------------------------------------
#
# The 14S.7C fault audit proved four injected exception surfaces that could
# leave SNIPE_IT / full_quality_allowed standing when the universal capital
# floor had NOT been successfully enforced: a fault during the withdrawal
# itself, a fault writing the diagnostic marker before the withdrawal, a fault
# anywhere inside the enforcer, and a fault in the outer wrapper after a SNIPE
# promotion. The downstream seal cannot rescue any of them (a risk-geometry
# breach is not a gate blocker, so the seal sees no contradiction).
#
# The law: PROVEN FLOOR -> capital may stand. UNPROVEN FLOOR -> full SNIPE
# capital may not stand. Software failure is not market failure, so the ladder
# BASKET is preserved as evidence of what the chart graded; only the public
# capital authorization is withdrawn.

FLOOR_CLEARED_KEY = "snipe_capital_floor_cleared"
UNPROVEN_FLOOR_REASON = "SNIPE_CAPITAL_FLOOR_NOT_PROVEN"
EMERGENCY_LANDING_KEY = "snipe_capital_emergency_landing"


def _canonical_no_capital_landing() -> dict:
    """Resolve the canonical NEAR_ENTRY public state ONCE, from the existing
    tiering maps, BEFORE entering the vulnerable transaction path.

    This is not a second tier system: it is a single fixed state, read from the
    same CHANNEL_MAP / CAPITAL_MAP `_apply_tier` uses, captured early so the
    emergency barrier never has to call anything that could itself fail.
    """
    channel, capital = "none", "wait_no_capital"
    try:
        from src import tiering
        channel = tiering.CHANNEL_MAP.get("NEAR_ENTRY", "none")
        capital = tiering.CAPITAL_MAP.get("NEAR_ENTRY", "wait_no_capital")
    except Exception:  # pragma: no cover - defensive; map import must never bind capital
        pass
    return {
        "final_tier": "NEAR_ENTRY",
        "capital_action": capital,
        "final_discord_channel": channel,
        # governed NEAR_ENTRY value — identical to _apply_tier's rule
        "safe_for_alert": "NEAR_ENTRY" != "WAIT",
    }


def _snipe_capital_standing(tiering_result) -> bool:
    """True when public SNIPE capital authorization is still in force. Checked
    on EITHER field so a half-written hybrid state is caught too."""
    if not isinstance(tiering_result, dict):
        return False
    return (_s(tiering_result.get("final_tier")) == "SNIPE_IT"
            or str(tiering_result.get("capital_action") or "") == "full_quality_allowed")


def _floor_cleared(ladder):
    """The definitive floor verdict. True = the floor ran and found no
    violation. False = it ran and found one, or could not be proven. None =
    it never completed. Only True is permission."""
    if not isinstance(ladder, dict):
        return None
    try:
        return ladder.get(FLOOR_CLEARED_KEY)
    except Exception:  # pragma: no cover - hostile mapping
        return None


def _mark_floor_cleared(ladder, cleared) -> None:
    """Record the verdict. Guarded: a diagnostic write must never be able to
    block or divert capital safety."""
    if not isinstance(ladder, dict):
        return
    try:
        ladder[FLOOR_CLEARED_KEY] = cleared
    except Exception:  # pragma: no cover - hostile mapping
        return


def _record_floor_diagnostics(tiering_result, ladder, reason) -> None:
    """Diagnostic decoration ONLY. Runs after the capital decision, never
    before it, and every write is individually guarded."""
    if not reason:
        return
    if isinstance(ladder, dict):
        try:
            ladder["snipe_capital_floor_violation"] = reason
        except Exception:  # pragma: no cover - hostile mapping
            pass
    if isinstance(tiering_result, dict):
        try:
            notes = tiering_result.get("downgrades")
            if isinstance(notes, list):
                notes.append(f"SNIPE capital floor: {reason}")
        except Exception:  # pragma: no cover - hostile mapping
            pass


def _emergency_no_capital_landing(tiering_result, landing, reason) -> None:
    """Crash barrier — the last resort when the normal withdrawal machinery
    faulted while public SNIPE capital was standing and the floor had not
    definitively cleared.

    Deliberately primitive: every write is a direct dict assignment, each
    individually guarded, and it never calls _apply_tier (the audit proved
    _apply_tier can itself fail or partially mutate state). It synchronizes
    BOTH the top-level fields and final_signal so no hybrid state survives.
    It does NOT touch internal_ladder_tier — the market judgment stands; only
    the capital authorization is withdrawn.
    """
    if not isinstance(tiering_result, dict):
        return
    for key in ("final_tier", "capital_action", "final_discord_channel", "safe_for_alert"):
        try:
            tiering_result[key] = landing[key]
        except Exception:  # pragma: no cover - hostile mapping
            pass
    signal = None
    try:
        signal = tiering_result.get("final_signal")
    except Exception:  # pragma: no cover - hostile mapping
        signal = None
    if isinstance(signal, dict):
        for key, value in (("tier", landing["final_tier"]),
                           ("capital_action", landing["capital_action"]),
                           ("discord_channel", landing["final_discord_channel"])):
            try:
                signal[key] = value
            except Exception:  # pragma: no cover - hostile mapping
                pass
    ladder = None
    try:
        ladder = tiering_result.get("snipe_ladder")
    except Exception:  # pragma: no cover - hostile mapping
        ladder = None
    _mark_floor_cleared(ladder, False)
    if isinstance(ladder, dict):
        try:
            ladder[EMERGENCY_LANDING_KEY] = reason
        except Exception:  # pragma: no cover - hostile mapping
            pass
    try:
        notes = tiering_result.get("downgrades")
        if isinstance(notes, list):
            notes.append(f"SNIPE capital withdrawn (fail-closed): {reason}")
    except Exception:  # pragma: no cover - hostile mapping
        pass


def _enforce_no_unproven_snipe_capital(tiering_result, landing) -> None:
    """The production invariant: SNIPE capital may only stand on a floor that
    definitively cleared. Unknown is not permission."""
    if not _snipe_capital_standing(tiering_result):
        return
    ladder = tiering_result.get("snipe_ladder") if isinstance(tiering_result, dict) else None
    if _floor_cleared(ladder) is True:
        return
    _emergency_no_capital_landing(tiering_result, landing, UNPROVEN_FLOOR_REASON)


def _enforce_snipe_capital_floor(tiering_result, ladder, config=None, landing=None) -> None:
    """If the arbitrated result is SNIPE_IT but fails the capital floor, take
    the capital away. Because tiering.py blocks STARTER on the same fake-
    asymmetry condition, granting starter capital here would contradict
    doctrine — the truthful landing is NEAR_ENTRY (no capital). Runs BEFORE the
    downgrade-only seal, which still runs afterwards and can downgrade further.

    Phase 14S.7C ordering: capital safety FIRST, diagnostics second. The
    withdrawal happens before any marker write, and a fault anywhere here lands
    on the canonical no-capital state instead of returning with SNIPE intact.
    """
    landing = landing if isinstance(landing, dict) else _canonical_no_capital_landing()
    reason = None
    try:
        if _s(tiering_result.get("final_tier")) != "SNIPE_IT":
            return
        reason = snipe_capital_floor_violation(tiering_result, config)
        if not reason:
            _mark_floor_cleared(ladder, True)
            return
        _mark_floor_cleared(ladder, False)
        # SAFETY FIRST: withdraw the capital before decorating anything.
        _apply_tier(tiering_result, "NEAR_ENTRY", ladder, promoted=False)
    except Exception as exc:
        _mark_floor_cleared(ladder, False)
        if _snipe_capital_standing(tiering_result):
            _emergency_no_capital_landing(
                tiering_result, landing,
                f"{UNPROVEN_FLOOR_REASON}: enforcement fault {type(exc).__name__}")
    finally:
        # Diagnostics are never load-bearing and can never block a withdrawal.
        _record_floor_diagnostics(tiering_result, ladder, reason)


def apply_ladder_arbitration(tiering_result, config=None):
    """Run the ladder judgment and let it govern the final tier. Returns the
    same tiering_result. Never raises. Promotion only NEAR_ENTRY->STARTER or
    STARTER->SNIPE_IT (plus the 14S.7B direct NEAR_ENTRY->SNIPE_IT jump behind
    a stricter gate); WAIT is never promoted; the seal still runs after.

    Every SNIPE_IT outcome — however it was reached, including an untouched
    SNIPE_IT baseline — must clear the capital floor before this returns.

    Phase 14S.7C: the canonical no-capital landing is resolved BEFORE the
    vulnerable path, and the invariant guard runs unconditionally on the way
    out. After this returns, SNIPE_IT + full_quality_allowed implies the floor
    verdict is definitively True.
    """
    landing = _canonical_no_capital_landing()
    try:
        _arbitrate_tier(tiering_result, config)
        if isinstance(tiering_result, dict):
            _enforce_snipe_capital_floor(
                tiering_result, tiering_result.get("snipe_ladder"), config, landing
            )
    except Exception:  # pragma: no cover - defensive; never break a scan
        pass
    try:
        _enforce_no_unproven_snipe_capital(tiering_result, landing)
    except Exception:  # pragma: no cover - the barrier itself must never raise
        pass
    return tiering_result


def _arbitrate_tier(tiering_result, config=None):
    try:
        if not isinstance(tiering_result, dict):
            return tiering_result
        ladder = classify_snipe_ladder(tiering_result)
        tiering_result["snipe_ladder"] = ladder

        current = _s(tiering_result.get("final_tier"))
        recommended = ladder["existing_final_tier_recommendation"]
        if recommended == current or not current:
            return tiering_result

        cur_rank = _TIER_ORDER.get(current)
        rec_rank = _TIER_ORDER.get(recommended)
        if cur_rank is None or rec_rank is None:
            return tiering_result

        if rec_rank > cur_rank:
            # Promotion path — strictly whitelisted, never from WAIT, one rung.
            if (current, recommended) not in _ALLOWED_PROMOTIONS:
                # Phase 14S.7: a NEAR_ENTRY baseline whose ladder evidence is a
                # COMPLETE, closed-proof SNIPER_A/A_PLUS may jump both rungs
                # rather than wait a scan. The gate below is stricter than the
                # SNIPER grade alone (it demands explicit closed-candle proof),
                # WAIT is still never promoted, and the downgrade-only seal
                # still runs afterwards and can veto a false promotion.
                if current == "NEAR_ENTRY" and recommended == "SNIPE_IT":
                    allowed, reason = allow_direct_near_entry_to_snipe_when_sniper_complete(
                        tiering_result, ladder, config
                    )
                    ladder["direct_snipe_decision"] = reason
                    if allowed:
                        # Phase 14S.7C — PROVE BEFORE COMMIT. The direct gate
                        # checks explicit risk_distance_pct and
                        # price-vs-invalidation; the universal floor adds
                        # trigger-vs-invalidation (tiering.py's own convention),
                        # so the two are NOT equivalent. Clear the universal
                        # floor before writing SNIPE_IT, never after.
                        floor_reason = snipe_capital_floor_violation(tiering_result, config)
                        if floor_reason:
                            _mark_floor_cleared(ladder, False)
                            _record_floor_diagnostics(tiering_result, ladder, floor_reason)
                            return tiering_result
                        _apply_tier(tiering_result, "SNIPE_IT", ladder, promoted=True)
                        return tiering_result
                # Two-rung recommendation (e.g. NEAR_ENTRY -> SNIPE_IT) promotes
                # a single rung only; the next scan can earn the rest. The
                # ladder may not hand out starter capital on a card that fails
                # the capital floor either — tiering.py blocks STARTER on the
                # same fake-asymmetry condition, so promoting into it here
                # would contradict doctrine. (This never DEMOTES a tier that
                # tiering itself assigned; it only declines to promote.)
                if (current, "STARTER") in _ALLOWED_PROMOTIONS and rec_rank > _TIER_ORDER["STARTER"]:
                    floor_reason = snipe_capital_floor_violation(tiering_result, config)
                    if floor_reason:
                        ladder["snipe_capital_floor_violation"] = floor_reason
                        return tiering_result
                    _apply_tier(tiering_result, "STARTER", ladder, promoted=True)
                return tiering_result
            floor_reason = snipe_capital_floor_violation(tiering_result, config)
            if floor_reason and _TIER_ORDER.get(recommended, 0) >= _TIER_ORDER["STARTER"]:
                ladder["snipe_capital_floor_violation"] = floor_reason
                return tiering_result
            _apply_tier(tiering_result, recommended, ladder, promoted=True)
            return tiering_result

        # Downgrade path — the ladder found less proof than the tier claims.
        _apply_tier(tiering_result, recommended, ladder, promoted=False)
        return tiering_result
    except Exception:  # pragma: no cover - defensive; never break a scan
        return tiering_result


def _apply_tier(tiering_result, corrected, ladder, promoted) -> None:
    from src import tiering  # local import avoids cycle/load cost

    channel = tiering.CHANNEL_MAP.get(corrected, "none")
    capital = tiering.CAPITAL_MAP.get(corrected, "no_trade")
    original = tiering_result.get("final_tier")

    signal = tiering_result.get("final_signal")
    if isinstance(signal, dict):
        scan_price = signal.get("scan_price")
        signal["tier"] = corrected
        signal["discord_channel"] = channel
        signal["capital_action"] = capital
        try:
            signal["sanitized_reason"] = tiering._sanitize_reason_for_tier(signal.get("reason"), corrected)
            signal["sanitized_next_action"] = tiering._sanitize_reason_for_tier(signal.get("next_action"), corrected)
        except Exception:
            pass
        if corrected == "NEAR_ENTRY":
            try:
                signal["near_entry_blocker_note"] = tiering._build_near_entry_blocker_note(signal, scan_price)
            except Exception:
                pass
        tiering_result["final_signal"] = signal

    tiering_result["final_tier"] = corrected
    tiering_result["final_discord_channel"] = channel
    tiering_result["capital_action"] = capital
    tiering_result["safe_for_alert"] = corrected != "WAIT"

    notes = tiering_result.get("downgrades")
    if not isinstance(notes, list):
        notes = []
    direction = "promoted" if promoted else "downgraded"
    notes.append(
        f"{original}→{corrected}: ladder arbitration ({direction}) — "
        f"{ladder['internal_ladder_tier']}: {ladder['why_this_ladder_tier']}"
    )
    tiering_result["downgrades"] = notes

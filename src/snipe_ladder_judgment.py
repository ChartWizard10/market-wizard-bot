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

    rr = _num(signal.get("risk_reward"))
    inval_level = _num(signal.get("invalidation_level"))
    price = _num(signal.get("scan_price"))
    if price is None:
        price = _num(signal.get("current_price"))
    inval_clear = bool(
        (inval_level is not None and str(signal.get("invalidation_condition") or "").strip())
        or oh_inval.get("clear") is True
    )
    overhead = _low(signal.get("overhead_status"))
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
        "structure": _s(signal.get("structure_event")),
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
            trig_level = _num(c["signal"].get("trigger_level"))
            next_proofs.append(
                f"1H closed hold above {trig_level:.2f}" if trig_level is not None
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
        failure_conditions.append(f"body close below invalidation {c['inval_level']:.2f}")
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


def apply_ladder_arbitration(tiering_result, config=None):
    """Run the ladder judgment and let it govern the final tier. Returns the
    same tiering_result. Never raises. Promotion only NEAR_ENTRY->STARTER or
    STARTER->SNIPE_IT; WAIT is never promoted; the seal still runs after."""
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
                # Two-rung recommendation (e.g. NEAR_ENTRY -> SNIPE_IT) promotes
                # a single rung only; the next scan can earn the rest.
                if (current, "STARTER") in _ALLOWED_PROMOTIONS and rec_rank > _TIER_ORDER["STARTER"]:
                    _apply_tier(tiering_result, "STARTER", ladder, promoted=True)
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

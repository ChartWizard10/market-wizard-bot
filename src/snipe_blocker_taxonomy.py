"""Phase 14Q — SNIPE blocker taxonomy + promotion reconciliation (pure helper).

A deterministic, read-only classifier that sorts every *active* SNIPE blocker a
setup carries into exactly one of four classes, and from that derives the
truthful tier floor a sealed-down SNIPE candidate may keep.

Doctrine (permanent):
  - This module NEVER mutates its input, NEVER does IO/network, NEVER raises,
    and NEVER promotes. It only classifies and recommends a floor; the seal
    applies it using the existing tier machinery.
  - It reads only REAL fields that already exist on the evidence objects
    (snipe_gate_audit, one_hour_entry, timeframe_alignment,
    higher_timeframe_context, final_signal). It invents no proof and no levels.
  - The floor is conditional, never blanket:
      * hard failure                          -> WAIT
      * any CAPITAL_BLOCKER / base not earned  -> NEAR_ENTRY (no fresh capital)
      * base earned + only SNIPE_ONLY blocker  -> STARTER (reduced size)
      * only SOFT_CAP / INFO_NOTE              -> do not seal (SNIPE_IT stands)
  - The STARTER floor is allowed ONLY when the base-entry sequence is positively
    confirmed by the one_hour_entry truth (trigger live/hold confirmed, retest
    real/core-valid, hold confirmed). Signal-level retest/hold flags alone are
    NOT sufficient — they cannot loosen capital without genuine 1H proof.
  - Leader/continuation context may soften NON-FATAL context into a SOFT_CAP. It
    can never override a hard failure, a CAPITAL_BLOCKER, or an unconfirmed base
    sequence. Every ticker is judged with the same formula; leaders get correct
    sponsorship context, not special treatment. No ticker is ever whitelisted.

The four classes:
  CAPITAL_BLOCKER   — blocks all new capital; final tier may not exceed NEAR_ENTRY.
  SNIPE_ONLY_BLOCKER— blocks SNIPE_IT (full size) but a confirmed base may keep STARTER.
  SOFT_CAP          — may reduce score/grade/wording/posture; cannot alone block SNIPE_IT.
  INFO_NOTE         — display-only context; no tier effect.

No new indicators. No new provider. No new cadence. Pure stdlib.
"""

# ---------------------------------------------------------------------------
# Class vocabulary
# ---------------------------------------------------------------------------

CAPITAL_BLOCKER = "CAPITAL_BLOCKER"
SNIPE_ONLY_BLOCKER = "SNIPE_ONLY_BLOCKER"
SOFT_CAP = "SOFT_CAP"
INFO_NOTE = "INFO_NOTE"

BLOCKER_CLASSES = (CAPITAL_BLOCKER, SNIPE_ONLY_BLOCKER, SOFT_CAP, INFO_NOTE)

# Critical base-entry gates: any of these BLOCKED or MISSING means the executable
# base sequence has not been earned, so no STARTER floor is possible.
_CRITICAL_BASE_GATES = {
    "DAILY_PERMISSION_GRANTED", "FOUR_H_LOCATION_VALID", "ONE_H_TRIGGER_CONFIRMED",
    "RETEST_CONFIRMED", "HOLD_CONFIRMED", "INVALIDATION_CLEAR", "ASYMMETRY_VALID",
}

# one_hour_entry positive-confirmation vocabulary (base earned).
_CONFIRMED_TRIGGER_STATES = {"TRIGGER_LIVE", "HOLD_CONFIRMED"}
_REAL_RETEST_TRUTHS = {"RETEST_CORE_VALID", "RETEST_REAL"}
_CONFIRMED_HOLD_TRUTHS = {"HOLD_CONFIRMED"}
_NON_CONFIRMED_ALERT_TRUTHS = {"WATCH_ONLY", "FORMING_TRIGGER", "FAILED_TRIGGER", "NO_ALERT"}

# Hard live-edge / candle vetoes — an active rejection of the entry zone, not a
# merely-pending full-size proof. These bind capital (NEAR_ENTRY / WAIT).
_HARD_CANDLE_EVENTS = {"FAILURE", "FAILED_BREAK"}
_HARD_LIVE_EDGE_VETOES = {"HOSTILE_WICK", "FAILED_RETEST"}
_HARD_VETO_TEXT = ("hostile wick", "failed retest", "failed break", "candle veto")

# Soft live-edge states — full-size confirmation pending, zone not rejected.
_SOFT_LIVE_EDGE_VETOES = {
    "OPEN_ONLY", "NO_CLOSE_CONFIRMATION", "NO_NEXT_CANDLE_VERDICT", "DOJI_AT_TRIGGER",
}

# 1H trigger / hold states that prove the base sequence is NOT yet earned.
_SOFT_FORMING_TRIGGERS = {"RETEST_IN_PROGRESS", "HOLD_FORMING", "PULLBACK_FORMING", "APPROACHING_LOCATION"}
_HARD_TRIGGER_STATES = {"FAILED_RETEST", "INVALID_1H_TRIGGER", "STALE_TRIGGER", "NO_1H_EVIDENCE"}
_WEAK_HOLDS = {"HOLD_WEAK", "HOLD_FORMING", "HOLD_FAILED", "NONE"}

# Candle-context vocabulary (Phase 14Q refinement: a rejection is not auto-bearish).
_REJECTION_EVENTS = {"REJECTION", "INDECISION"}
_HOSTILE_LEVEL_REACTIONS = {"FAILED_ZONE", "LOST_LEVEL", "REJECTED"}

# Candle context labels.
CANDLE_SUPPORTIVE = "SUPPORTIVE"
CANDLE_DEFENSIVE = "DEFENSIVE_REJECTION"
CANDLE_HOSTILE = "HOSTILE_REJECTION"
CANDLE_UNRESOLVED = "CANDLE_CONTEXT_UNRESOLVED"
CANDLE_UNCONFIRMED_BASE = "CANDLE_UNCONFIRMED_BASE"


# ---------------------------------------------------------------------------
# Small read helpers (never raise, never mutate)
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


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _gate_names(items) -> list:
    out = []
    for it in items or []:
        if isinstance(it, str) and it:
            out.append(it.split(":", 1)[0].strip())
        elif isinstance(it, dict):
            for k in ("gate", "name", "id", "key"):
                v = it.get(k)
                if isinstance(v, str) and v:
                    out.append(v.strip())
                    break
    return out


def _proof_gate_names(missing_proofs) -> list:
    """missing_proofs entries look like 'GATE_NAME: reason text' — pull the gate."""
    out = []
    for it in missing_proofs or []:
        if isinstance(it, str) and it:
            out.append(it.split(":", 1)[0].strip())
    return out


def _blocker(code, klass, current, required, tier_effect, proof_required) -> dict:
    return {
        "code": code,
        "blocker_class": klass,
        "current_value": current,
        "required_value": required,
        "tier_effect": tier_effect,
        "proof_required": proof_required,
    }


# ---------------------------------------------------------------------------
# Base-sequence confirmation (the STARTER-floor gate)
# ---------------------------------------------------------------------------

def base_sequence_confirmed(obj) -> bool:
    """True only when the executable base-entry sequence is positively proven by
    the one_hour_entry truth AND no critical base gate is blocked/missing.

    Signal-level retest/hold flags alone are intentionally NOT sufficient: a
    STARTER floor authorizes reduced-size capital and must rest on genuine 1H
    proof, not Claude-layer text.
    """
    if not isinstance(obj, dict):
        return False

    sga = obj.get("snipe_gate_audit") if isinstance(obj.get("snipe_gate_audit"), dict) else {}
    blocked = set(_gate_names(sga.get("blocked_gate_names")) or _gate_names(sga.get("blocked_gates")))
    missing = set(_proof_gate_names(sga.get("missing_proofs")))
    if (blocked | missing) & _CRITICAL_BASE_GATES:
        return False

    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else None
    if not oh:
        # No 1H evidence object -> cannot positively confirm the base sequence.
        return False

    trig = _s(oh.get("trigger_state"))
    alert = _s(oh.get("alert_truth_label"))
    prh = _d(oh, "pullback_retest_hold")
    hold_truth = _s(prh.get("hold_truth"))
    retest_truth = _s(prh.get("retest_truth"))

    if trig not in _CONFIRMED_TRIGGER_STATES:
        return False
    if hold_truth not in _CONFIRMED_HOLD_TRUTHS:
        return False
    if retest_truth not in _REAL_RETEST_TRUTHS:
        return False
    if alert in _NON_CONFIRMED_ALERT_TRUTHS:
        return False
    return True


# ---------------------------------------------------------------------------
# Leader / continuation context (computed from existing evidence only)
# ---------------------------------------------------------------------------

LEADER_CONTINUATION_CONTEXT = "LEADER_CONTINUATION_CONTEXT"
NON_LEADER = "NON_LEADER"
LEADER_UNKNOWN = "UNKNOWN"

LEADER_SOFT_CAP_RELIEF = "SOFT_CAP_RELIEF"
LEADER_NO_EFFECT = "NO_EFFECT"
LEADER_HARD_FAILURE_OVERRIDES = "HARD_FAILURE_OVERRIDES"


def compute_leader_continuation_context(obj) -> dict:
    """Recognize genuine market leadership / healthy-pullback continuation from
    fields the scanner already produced (existing bars/fields only; no new
    provider, cadence, or dependency). Used ONLY to soften non-fatal context —
    never to override a hard failure. Same formula for every ticker; no ticker
    is ever whitelisted.

    Returns leader_context / leader_evidence / leader_effect. leader_effect is a
    preliminary value here (NO_EFFECT / SOFT_CAP_RELIEF); the classifier upgrades
    it to HARD_FAILURE_OVERRIDES when a CAPITAL_BLOCKER is present.
    """
    htf = obj.get("higher_timeframe_context") if isinstance(obj.get("higher_timeframe_context"), dict) else {}
    tf = obj.get("timeframe_alignment") if isinstance(obj.get("timeframe_alignment"), dict) else {}
    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else {}
    signal = obj.get("final_signal") if isinstance(obj.get("final_signal"), dict) else {}

    campaign = _s(htf.get("weekly_campaign_state"))
    align_label = _s(tf.get("alignment_label"))
    daily_state = _s(_d(tf, "swing_timeframe").get("state"))
    structure = _s(signal.get("structure_event"))
    path_label = _s(_d(oh, "path_quality").get("path_label"))
    inval_clear = bool(_d(oh, "invalidation").get("clear")) or signal.get("invalidation_level") is not None

    evidence = []
    if campaign in ("HTF_CONTINUATION", "BULLISH", "HTF_BULLISH"):
        evidence.append(f"weekly_campaign={campaign}")
    if align_label in ("FULL_STACK_ALIGNED", "HTF_ALIGNED_TRIGGER_PENDING"):
        evidence.append(f"alignment={align_label}")
    if daily_state == "PERMISSION_GRANTED":
        evidence.append("daily=PERMISSION_GRANTED")
    if structure in ("BOS", "MSS", "ACCEPTED_BREAK", "RECLAIM", "FRESH_EXPANSION", "CONTINUATION"):
        evidence.append(f"structure={structure}")
    if path_label in ("CLEAN", "ACCEPTABLE"):
        evidence.append(f"path={path_label}")
    if inval_clear:
        evidence.append("invalidation_defined")

    if not (campaign or align_label or daily_state):
        context = LEADER_UNKNOWN
    elif len(evidence) >= 3:
        context = LEADER_CONTINUATION_CONTEXT
    else:
        context = NON_LEADER

    return {
        "leader_context": context,
        "leader_evidence": evidence,
        "leader_effect": LEADER_SOFT_CAP_RELIEF if context == LEADER_CONTINUATION_CONTEXT else LEADER_NO_EFFECT,
    }


# ---------------------------------------------------------------------------
# Candle context — a rejection candle is NOT automatically bearish.
#
# ONE normalized object per candle. Every candle blocker is derived from this
# single object, so the same candle can never appear in two blocker classes and
# there is never scattered/contradictory candle interpretation.
# ---------------------------------------------------------------------------

# candle_context values
CC_NO_REJECTION = "NO_REJECTION"
CC_DEFENSIVE = "DEFENSIVE_REJECTION"
CC_HOSTILE = "HOSTILE_REJECTION"
CC_EXPANSION = "EXPANSION_REJECTION"
CC_UNRESOLVED = "UNRESOLVED_REJECTION"
CC_UNKNOWN = "UNKNOWN"

# candle_context_scope values
SCOPE_ENTRY_ZONE = "BASE_ENTRY_ZONE"
SCOPE_EXPANSION = "EXPANSION_ADD_LEVEL"
SCOPE_UNKNOWN = "UNKNOWN"

# candle_blocker_code values
CODE_DEFENSIVE = "CANDLE_DEFENSIVE_REJECTION"
CODE_UNRESOLVED = "CANDLE_CONTEXT_UNRESOLVED"
CODE_HOSTILE = "CANDLE_HOSTILE_REJECTION"
CODE_EXPANSION = "CANDLE_EXPANSION_REJECTION"
CODE_NO_REJECTION = "CANDLE_NO_REJECTION"
CODE_UNKNOWN = "CANDLE_CONTEXT_UNKNOWN"

# candle_tier_effect: reuses the four class names + NONE
TIER_EFFECT_NONE = "NONE"


# ---------------------------------------------------------------------------
# Candle context — a rejection candle is NOT automatically bearish.
# ---------------------------------------------------------------------------

def _defensive_proof_complete(obj) -> bool:
    """All proof needed to call a rejection DEFENSIVE (rejected lower value while
    the defended zone holds). Requires positive confirmation of path, daily
    permission, 4H location, and price above invalidation — read from real
    fields. If any cannot be proven, the rejection is NOT defensive (-> STARTER
    safe minimum), never assumed.
    """
    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else {}
    signal = obj.get("final_signal") if isinstance(obj.get("final_signal"), dict) else {}
    tf = obj.get("timeframe_alignment") if isinstance(obj.get("timeframe_alignment"), dict) else {}
    ce = obj.get("candle_evidence") if isinstance(obj.get("candle_evidence"), dict) else {}

    path = _d(oh, "path_quality")
    path_clean = (
        _s(path.get("path_label")) in ("CLEAN", "ACCEPTABLE")
        or path.get("overhead_clear_enough") is True
        or _s(signal.get("overhead_status")) == "CLEAR"
    )
    daily_granted = _s(_d(tf, "swing_timeframe").get("state")) == "PERMISSION_GRANTED"
    four_h_valid = _s(_d(tf, "operational_timeframe").get("state")) == "LOCATION_VALID"

    price = _num(signal.get("scan_price"))
    if price is None:
        price = _num(signal.get("current_price"))
    inval = _num(signal.get("invalidation_level"))
    price_above_inval = price is not None and inval is not None and price > inval

    no_zone_failure = _s(ce.get("level_reaction")) not in _HOSTILE_LEVEL_REACTIONS

    return bool(path_clean and daily_granted and four_h_valid and price_above_inval and no_zone_failure)


def _cc(context, scope, reason, effect, code, current="—", required="—", proof="n/a") -> dict:
    return {
        "candle_context": context,
        "candle_context_scope": scope,
        "candle_context_reason": reason,
        "candle_tier_effect": effect,
        "candle_blocker_code": code,
        "current_value": current,
        "required_value": required,
        "proof_required": proof,
    }


def normalized_candle_context(obj, base_ok=None) -> dict:
    """THE single normalized candle-context object. Every candle blocker is
    derived from this; a candle is classified exactly once.

    A rejection candle is not automatically bearish:
      DEFENSIVE_REJECTION  (zone held, rejected lower value)  -> SOFT_CAP
      HOSTILE_REJECTION    (entry-zone acceptance failed)     -> CAPITAL_BLOCKER
      EXPANSION_REJECTION  (add/expansion level failed only)  -> SOFT_CAP
      UNRESOLVED_REJECTION (base earned, defensive unprovable) -> SNIPE_ONLY_BLOCKER
      NO_REJECTION                                            -> NONE
      UNKNOWN              (candle fields missing)            -> INFO_NOTE / SNIPE_ONLY
    """
    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else {}
    signal = obj.get("final_signal") if isinstance(obj.get("final_signal"), dict) else {}
    ce = obj.get("candle_evidence") if isinstance(obj.get("candle_evidence"), dict) else {}
    candle = _d(oh, "candle_truth")
    event = _s(candle.get("event_type"))
    closed = candle.get("closed_candle_confirms")

    if base_ok is None:
        base_ok = base_sequence_confirmed(obj)

    # No candle evidence at all -> UNKNOWN (not a claim of rejection).
    has_candle_data = bool(oh) and ("candle_truth" in oh) and (event not in ("", "NONE") or closed is not None)
    is_rejection = event in _REJECTION_EVENTS or event in _HARD_CANDLE_EVENTS or closed is False

    if not has_candle_data and not is_rejection:
        # Missing required candle fields.
        if base_ok:
            return _cc(CC_UNKNOWN, SCOPE_UNKNOWN,
                       "candle fields missing; full-size candle proof unverified",
                       SNIPE_ONLY_BLOCKER, CODE_UNKNOWN,
                       "candle context unknown (no candle evidence)",
                       "closed candle confirmation for full size",
                       "closed 1H candle confirmation")
        return _cc(CC_UNKNOWN, SCOPE_UNKNOWN, "candle fields missing",
                   TIER_EFFECT_NONE, CODE_UNKNOWN, "candle context unknown")

    if not is_rejection:
        return _cc(CC_NO_REJECTION, SCOPE_UNKNOWN, f"candle {event or 'supportive'} — no rejection",
                   TIER_EFFECT_NONE, CODE_NO_REJECTION, event or "supportive")

    prh = _d(oh, "pullback_retest_hold")
    hold = _s(prh.get("hold_truth"))
    retest = _s(prh.get("retest_truth"))
    trig = _s(oh.get("trigger_state"))
    alert = _s(oh.get("alert_truth_label"))
    price = _num(signal.get("scan_price"))
    if price is None:
        price = _num(signal.get("current_price"))
    inval = _num(signal.get("invalidation_level"))
    price_below = price is not None and inval is not None and price < inval

    # Is the base entry-zone hold itself confirmed? (Determines whether a failure
    # belongs to the entry zone or to an add/expansion level above it.)
    entry_zone_held = (
        hold in _CONFIRMED_HOLD_TRUTHS and retest in _REAL_RETEST_TRUTHS
        and trig in _CONFIRMED_TRIGGER_STATES and alert not in _NON_CONFIRMED_ALERT_TRUTHS
    )

    explicit_failure = (
        event in _HARD_CANDLE_EVENTS
        or _s(ce.get("level_reaction")) in _HOSTILE_LEVEL_REACTIONS
        or _s(ce.get("candle_family")) == "FAILED_BREAK"
        or _s(ce.get("candle_veto")) in _HARD_LIVE_EDGE_VETOES
        or hold == "HOLD_FAILED"
        or price_below
    )

    if explicit_failure:
        if entry_zone_held:
            # Entry-zone hold confirmed -> the failure is at the add/expansion level.
            return _cc(CC_EXPANSION, SCOPE_EXPANSION,
                       "expansion/add trigger failed; base entry-zone retest/hold confirmed",
                       SOFT_CAP, CODE_EXPANSION,
                       "expansion/add trigger failed (not the base entry zone)",
                       "—", "clean acceptance above the add/expansion level")
        return _cc(CC_HOSTILE, SCOPE_ENTRY_ZONE,
                   "rejection proved failed entry-zone acceptance / hold not held",
                   CAPITAL_BLOCKER, CODE_HOSTILE,
                   f"candle {event} failed the entry zone",
                   "closed acceptance/defense of the entry zone",
                   "closed 1H acceptance above the defended zone")

    # Plain rejection (no explicit failure signal).
    if base_ok:
        if _defensive_proof_complete(obj):
            return _cc(CC_DEFENSIVE, SCOPE_ENTRY_ZONE,
                       "rejected lower value while the defended zone holds; supports the long",
                       SOFT_CAP, CODE_DEFENSIVE,
                       f"defensive {event}: defended zone held",
                       "—", "n/a (defensive rejection supports the long)")
        return _cc(CC_UNRESOLVED, SCOPE_UNKNOWN,
                   "defensive-vs-hostile rejection not provable from current fields",
                   SNIPE_ONLY_BLOCKER, CODE_UNRESOLVED,
                   f"candle {event}, defensive-vs-hostile unproven",
                   "closed full-size candle / defensive proof set",
                   "closed 1H candle confirmation or full defensive proof")

    # Base sequence not earned -> the entry-zone acceptance is unproven.
    return _cc(CC_HOSTILE, SCOPE_ENTRY_ZONE,
               "1H hold not confirmed; entry-zone acceptance unproven",
               CAPITAL_BLOCKER, CODE_HOSTILE,
               f"candle {event}, 1H hold not yet confirmed",
               "closed 1H hold + supportive candle at the zone",
               "closed 1H hold + supportive candle")


def _dedup_by_code(items) -> list:
    seen, out = set(), []
    for b in items:
        code = b.get("code") if isinstance(b, dict) else None
        if code in seen:
            continue
        seen.add(code)
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def classify_blockers(obj) -> dict:
    """Classify every active SNIPE blocker into the four-class taxonomy and
    derive the truthful tier floor. Pure; never raises; never mutates obj.
    """
    try:
        return _classify(obj)
    except Exception:  # pragma: no cover - defensive; classification never breaks a scan
        return {
            "core_sequence_complete": False,
            "capital_blockers": [],
            "snipe_only_blockers": [],
            "soft_caps": [],
            "info_notes": [],
            "leader_context": {"is_leader_continuation": False, "signals": [], "note": "classification error"},
            "recommended_floor": "NEAR_ENTRY",
            "hidden_blocker_violation": False,
        }


def _classify(obj) -> dict:
    if not isinstance(obj, dict):
        obj = {}

    sga = obj.get("snipe_gate_audit") if isinstance(obj.get("snipe_gate_audit"), dict) else {}
    oh = obj.get("one_hour_entry") if isinstance(obj.get("one_hour_entry"), dict) else {}
    htf = obj.get("higher_timeframe_context") if isinstance(obj.get("higher_timeframe_context"), dict) else {}

    blocked_names = _gate_names(sga.get("blocked_gate_names")) or _gate_names(sga.get("blocked_gates"))
    missing_names = _proof_gate_names(sga.get("missing_proofs"))
    score_blocked = _gate_names(sga.get("score_blocked_by"))
    blocking_reasons = [r for r in (sga.get("blocking_reasons") or []) if isinstance(r, str)]

    capital: list = []
    snipe_only: list = []
    soft: list = []
    info: list = []

    base_ok = base_sequence_confirmed(obj)

    # ---- Critical base gates blocked/missing => CAPITAL_BLOCKER --------------
    for gate in _CRITICAL_BASE_GATES:
        if gate in blocked_names:
            capital.append(_blocker(
                gate, CAPITAL_BLOCKER, "BLOCK", "PASS",
                "blocks all new capital; tier <= NEAR_ENTRY",
                f"{gate} must PASS",
            ))
        elif gate in missing_names:
            capital.append(_blocker(
                gate, CAPITAL_BLOCKER, "MISSING/forming", "PASS",
                "blocks all new capital; tier <= NEAR_ENTRY",
                f"{gate} proof must confirm",
            ))

    # ---- Path / overhead blocked => CAPITAL_BLOCKER -------------------------
    for gate in ("PATH_CLEAN", "OVERHEAD_CLEAR"):
        if gate in blocked_names:
            capital.append(_blocker(
                gate, CAPITAL_BLOCKER, "BLOCK", "PASS or explicitly not-blocking",
                "blocks all new capital; tier <= NEAR_ENTRY",
                "clear the path/overhead before capital",
            ))

    # ---- one_hour_entry truth ----------------------------------------------
    trig = _s(oh.get("trigger_state"))
    prh = _d(oh, "pullback_retest_hold")
    hold_truth = _s(prh.get("hold_truth"))
    alert_truth = _s(oh.get("alert_truth_label"))
    loc_label = _s(_d(oh, "location_realism").get("label"))

    # 1H trigger / hold not confirmed -> base sequence not earned -> binds capital.
    if oh and (
        trig in _SOFT_FORMING_TRIGGERS or trig in _HARD_TRIGGER_STATES
        or hold_truth in _WEAK_HOLDS or alert_truth in _NON_CONFIRMED_ALERT_TRUTHS
    ):
        capital.append(_blocker(
            "ONE_H_TRIGGER_CONFIRMED", CAPITAL_BLOCKER,
            f"1H {trig or alert_truth or hold_truth or 'unconfirmed'} not confirmed",
            "1H trigger live/confirmed + closed hold confirmed",
            "blocks all new capital; tier <= NEAR_ENTRY",
            "closed 1H hold + confirmed trigger",
        ))

    # ---- Signal-level retest/hold (parity with the seal detector) -----------
    # A present-but-unconfirmed retest/hold status is a base-sequence gap and
    # binds capital. Absent values make no claim (persisted-row recompute path).
    signal = obj.get("final_signal") if isinstance(obj.get("final_signal"), dict) else {}
    for key, gate in (("retest_status", "RETEST_CONFIRMED"), ("hold_status", "HOLD_CONFIRMED")):
        v = signal.get(key)
        if v is not None and str(v).strip().lower() not in (
            "confirmed", "hold_confirmed", "retest_confirmed", "true", "yes", "pass"
        ):
            capital.append(_blocker(
                gate, CAPITAL_BLOCKER, f"{key}={v}", "confirmed",
                "blocks all new capital; tier <= NEAR_ENTRY",
                f"{key.replace('_', ' ')} must confirm",
            ))

    # ---- Candle CONTEXT (single normalized object; derive exactly one blocker) -
    # A rejection candle is not automatically bearish. Every candle blocker comes
    # from this one object, so a candle is classified exactly once.
    cc = normalized_candle_context(obj, base_ok)
    effect, code = cc["candle_tier_effect"], cc["candle_blocker_code"]
    if effect == CAPITAL_BLOCKER:
        capital.append(_blocker(code, CAPITAL_BLOCKER, cc["current_value"], cc["required_value"],
                                "blocks all new capital; tier <= NEAR_ENTRY", cc["proof_required"]))
    elif effect == SNIPE_ONLY_BLOCKER:
        snipe_only.append(_blocker(code, SNIPE_ONLY_BLOCKER, cc["current_value"], cc["required_value"],
                                   "blocks SNIPE_IT full size; confirmed base keeps STARTER", cc["proof_required"]))
    elif effect == SOFT_CAP:
        soft.append(_blocker(code, SOFT_CAP, cc["current_value"], cc["required_value"],
                             "grades wording/score only; cannot block SNIPE_IT", cc["proof_required"]))
    elif effect == INFO_NOTE:
        info.append(_blocker(code, INFO_NOTE, cc["current_value"], cc["required_value"],
                             "no tier effect", cc["proof_required"]))

    # ---- Hard live-edge veto (HOSTILE_WICK / FAILED_RETEST) => CAPITAL ------
    if "LIVE_EDGE_SAFE" in blocked_names or any(
        t in r.lower() for r in blocking_reasons for t in _HARD_VETO_TEXT
    ):
        capital.append(_blocker(
            "LIVE_EDGE_SAFE", CAPITAL_BLOCKER, "BLOCK (hostile/failed live edge)",
            "live edge safe / zone defended",
            "blocks all new capital; tier <= NEAR_ENTRY",
            "resolve the live-edge veto (closed defense, no hostile wick)",
        ))

    # ---- HTF contextual block (Rule G/H) -----------------------------------
    if htf.get("blocks_snipe_contextually") is True:
        snipe_only.append(_blocker(
            "HTF_CONTEXT_BLOCK", SNIPE_ONLY_BLOCKER,
            f"weekly/HTF supply blocks full size ({_s(htf.get('campaign_location_label')) or 'HTF'})",
            "HTF context not contextually blocking",
            "blocks SNIPE_IT full size; confirmed base may keep STARTER",
            "HTF supply cleared or no longer contextually blocking",
        ))

    # ---- SNIPE-only: live-edge full-size proof forming (base earned) --------
    if base_ok:
        soft_live_edge = _s(_d(obj, "candle_evidence").get("candle_veto")) in _SOFT_LIVE_EDGE_VETOES
        if soft_live_edge or "LIVE_EDGE_SAFE" in missing_names:
            snipe_only.append(_blocker(
                "LIVE_EDGE_SAFE", SNIPE_ONLY_BLOCKER,
                "live-edge full-size proof forming",
                "live-edge confirmed for full size",
                "blocks SNIPE_IT full size; confirmed base keeps STARTER",
                "closed live-edge confirmation",
            ))

    # ---- SNIPE-only: score realism below SNIPE threshold --------------------
    if score_blocked:
        snipe_only.append(_blocker(
            "SNIPE_SCORE_REALISM", SNIPE_ONLY_BLOCKER,
            "score capped below SNIPE threshold (" + ", ".join(score_blocked) + ")",
            "score clears SNIPE threshold",
            "blocks SNIPE_IT full size; confirmed base keeps STARTER",
            "clear the score-capping proof",
        ))

    # ---- SOFT_CAP: non-fatal context ---------------------------------------
    campaign_loc = _s(htf.get("campaign_location_label"))
    if htf.get("blocks_snipe_contextually") is False and (
        campaign_loc == "EXTENDED_ABOVE_VALUE" or htf.get("weakens_long_setup") is True
    ):
        soft.append(_blocker(
            "HTF_EXTENDED", SOFT_CAP,
            f"HTF {campaign_loc or 'extended'} (weakens but does not block)",
            "—", "grades wording/score only; cannot block SNIPE_IT",
            "n/a (disclosure)",
        ))
    ctx_grade = _s(htf.get("context_grade"))
    if ctx_grade in ("C", "B") and htf.get("blocks_snipe_contextually") is not True:
        soft.append(_blocker(
            "HTF_CONTEXT_GRADE", SOFT_CAP, f"context grade {ctx_grade}", "—",
            "grades wording/score only; cannot block SNIPE_IT", "n/a (disclosure)",
        ))
    if loc_label in ("ACCEPTABLE_BUT_NOT_IDEAL", "MIDRANGE"):
        soft.append(_blocker(
            "LOCATION_REALISM", SOFT_CAP, f"location {loc_label}", "—",
            "grades wording/posture only; cannot block SNIPE_IT", "n/a (disclosure)",
        ))

    # ---- INFO_NOTE: display-only context -----------------------------------
    monthly = _s(htf.get("monthly_bias"))
    if monthly in ("UNKNOWN", "") and htf.get("monthly_used_as_gate") is not True:
        info.append(_blocker(
            "MONTHLY_BIAS_UNKNOWN", INFO_NOTE, "monthly bias unknown", "—",
            "no tier effect", "n/a (display only)",
        ))
    if _s(htf.get("data_status")) == "INFERRED" or htf.get("weekly_inferred") is True:
        info.append(_blocker(
            "WEEKLY_INFERRED", INFO_NOTE, "weekly context inferred", "—",
            "no tier effect", "n/a (display only)",
        ))

    # ---- Dedup within + across classes (a code lives in exactly one class) ---
    capital = _dedup_by_code(capital)
    snipe_only = _dedup_by_code(snipe_only)
    soft = _dedup_by_code(soft)
    info = _dedup_by_code(info)
    capital, snipe_only, soft, info = _resolve_cross_class(capital, snipe_only, soft, info)

    core_complete = base_ok and not capital
    floor = _recommended_floor(obj, capital, snipe_only, core_complete)

    # ---- Leader effect: relief only when no hard failure exists --------------
    leader = compute_leader_continuation_context(obj)
    if leader["leader_context"] == LEADER_CONTINUATION_CONTEXT:
        leader["leader_effect"] = LEADER_HARD_FAILURE_OVERRIDES if capital else LEADER_SOFT_CAP_RELIEF
    else:
        leader["leader_effect"] = LEADER_NO_EFFECT

    # Hidden-blocker violation (Rule D/E): the result claims a blocked promotion
    # but NO structured blocker of any blocking class was identified.
    promo = _s(sga.get("promotion_state"))
    audit_label = _s(sga.get("audit_label"))
    claims_block = promo == "PROMOTION_BLOCKED" or audit_label == "SNIPE_CONFIRMATION_BLOCKED"
    hidden = bool(claims_block and not (capital or snipe_only))

    return {
        "core_sequence_complete": core_complete,
        "base_sequence_confirmed": base_ok,
        "capital_blockers": capital,
        "snipe_only_blockers": snipe_only,
        "soft_caps": soft,
        "info_notes": info,
        "candle_context": cc,
        "leader_context": leader["leader_context"],
        "leader_evidence": leader["leader_evidence"],
        "leader_effect": leader["leader_effect"],
        "recommended_floor": floor,
        "hidden_blocker_violation": hidden,
    }


def _resolve_cross_class(capital, snipe_only, soft, info) -> tuple:
    """Guarantee a blocker code appears in at most one class (capital > snipe-only
    > soft > info). Prevents the same candle/context code from being reported as
    both a SNIPE_ONLY_BLOCKER and a SOFT_CAP.
    """
    seen = set()
    out = []
    for lst in (capital, snipe_only, soft, info):
        kept = []
        for b in lst:
            code = b.get("code") if isinstance(b, dict) else None
            if code in seen:
                continue
            seen.add(code)
            kept.append(b)
        out.append(kept)
    return tuple(out)


def _recommended_floor(obj, capital, snipe_only, core_complete) -> str:
    """Map the classification to a tier floor. Hard-failure detection is delegated
    to the seal (which owns the WAIT vs NEAR_ENTRY severity call); this returns the
    *highest tier the blockers permit*, never above STARTER (the seal never promotes).
    """
    if capital:
        return "NEAR_ENTRY"
    if core_complete and snipe_only:
        return "STARTER"
    if snipe_only:
        return "NEAR_ENTRY"
    # No capital/SNIPE-only blocker -> only soft caps/info notes -> SNIPE stands.
    return "SNIPE_IT"


# ---------------------------------------------------------------------------
# Convenience: flat list of named blockers (for diagnostics / disclosure)
# ---------------------------------------------------------------------------

def named_blockers(classification) -> list:
    """Flat, human-readable 'CODE (CLASS): proof_required' list across the two
    blocking classes — used to name the exact unresolved proof in diagnostics
    so the seal never emits vague 'unresolved proof remains' language.
    """
    out = []
    for b in (classification.get("capital_blockers") or []) + (classification.get("snipe_only_blockers") or []):
        if isinstance(b, dict):
            out.append(f"{b.get('code')} ({b.get('blocker_class')}): {b.get('proof_required')}")
    return out

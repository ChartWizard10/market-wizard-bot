"""Phase 14F — Multi-Timeframe Alignment Evidence Object.

A dedicated, auditable ledger that records Weekly / Daily / 4H / 1H alignment
state in one place. It is evidence / display / audit ONLY.

Doctrine (fixed):
  - Weekly  = campaign context.
  - Daily   = swing permission.
  - 4H      = operational location / repair state / entry neighborhood.
  - 1H      = trigger proof (sourced from tiering_result["one_hour_entry"]).

Ownership rules (permanent):
  - PURE and re-entrant. Reads inputs, returns a fresh dict, mutates nothing.
  - NEVER raises in production. Any exception returns a safe ERROR object.
  - NEVER promotes, routes, authorizes capital, creates entries, or overrides
    higher-timeframe sovereignty or tiering.
  - Does NOT re-run 1H candle logic; the 1H state is mapped from one_hour_entry.
  - Weekly is honestly marked inferred — no standalone weekly bars are acquired.

No new indicators. No RSI/MACD/Bollinger/Stochastic. No SMA10 dependency.
"""

# ---------------------------------------------------------------------------
# Canonical enums (mandatory — emitting an unlisted value is a test failure)
# ---------------------------------------------------------------------------

STATUS_VALUES = {"ENABLED", "DISABLED", "DEGRADED", "ERROR"}
ALIGNMENT_GRADES = {"A", "A-", "B+", "B", "C", "D", "F", "UNKNOWN"}
ALIGNMENT_LABELS = {
    "FULL_STACK_ALIGNED", "HTF_ALIGNED_TRIGGER_PENDING", "HTF_VALID_4H_REPAIR",
    "MIXED_ALIGNMENT", "LOWER_TIMEFRAME_ONLY", "CONFLICTED",
    "INSUFFICIENT_CONTEXT",
}
WEEKLY_STATES = {"BULLISH", "NEUTRAL", "BEARISH", "CONFLICTED", "UNKNOWN"}
DAILY_STATES = {
    "PERMISSION_GRANTED", "PERMISSION_FORMING", "PERMISSION_REPAIRING",
    "PERMISSION_DENIED", "UNKNOWN",
}
OPERATIONAL_STATES = {
    "LOCATION_VALID", "LOCATION_REPAIRING", "LOCATION_EXTENDED",
    "LOCATION_HOSTILE", "UNKNOWN",
}
TRIGGER_STATES = {
    "TRIGGER_CONFIRMED", "TRIGGER_FORMING", "TRIGGER_WEAK", "TRIGGER_FAILED",
    "TRIGGER_STALE", "UNKNOWN",
}

# ---------------------------------------------------------------------------
# Scoring weights (per spec) and grade bands
# ---------------------------------------------------------------------------

_WEEKLY_POINTS = {
    "BULLISH": 20, "NEUTRAL": 12, "UNKNOWN": 6, "BEARISH": 0, "CONFLICTED": 0,
}
_DAILY_POINTS = {
    "PERMISSION_GRANTED": 30, "PERMISSION_FORMING": 22,
    "PERMISSION_REPAIRING": 14, "UNKNOWN": 6, "PERMISSION_DENIED": 0,
}
_OPERATIONAL_POINTS = {
    "LOCATION_VALID": 25, "LOCATION_REPAIRING": 18, "LOCATION_EXTENDED": 10,
    "UNKNOWN": 6, "LOCATION_HOSTILE": 0,
}
_TRIGGER_POINTS = {
    "TRIGGER_CONFIRMED": 25, "TRIGGER_FORMING": 17, "TRIGGER_WEAK": 9,
    "TRIGGER_STALE": 4, "UNKNOWN": 4, "TRIGGER_FAILED": 0,
}

# Hard cap ceilings (lowest applicable wins).
_CAP_DAILY_DENIED        = 49
_CAP_4H_HOSTILE          = 59
_CAP_1H_FAILED           = 49
_CAP_1H_STALE            = 69
_CAP_LOWER_TF_ONLY       = 64
_CAP_INSUFFICIENT        = 74
_CAP_LEGACY_VS_1H        = 74
_CAP_NO_INVALIDATION     = 74
_CAP_CEILING_BLOCKER     = 79

_CAPITAL_ENTRY_ACTIONS = {"full_quality_allowed", "starter_only"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_timeframe_alignment_context(
    ticker, tiering_result, enriched_data=None, config=None
) -> dict:
    """Build the multi-timeframe alignment evidence object. NEVER raises.

    Pure / re-entrant: reads inputs, returns a fresh dict, mutates nothing.
    On any exception returns a safe ERROR object.
    """
    try:
        return _build(ticker, tiering_result or {}, enriched_data or {}, config or {})
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return error_timeframe_alignment_object(str(exc))


def default_timeframe_alignment_object() -> dict:
    """Canonical empty schema with safe UNKNOWN defaults."""
    return {
        "enabled": True,
        "status": "ENABLED",
        "alignment_grade": "UNKNOWN",
        "alignment_score": 0,
        "alignment_label": "INSUFFICIENT_CONTEXT",
        "campaign_timeframe": _blank_layer("1W", "CAMPAIGN_CONTEXT"),
        "swing_timeframe": _blank_layer("1D", "SWING_PERMISSION"),
        "operational_timeframe": _blank_layer("4H", "OPERATIONAL_LOCATION"),
        "trigger_timeframe": _blank_layer("1H", "TRIGGER_PROOF"),
        "conflicts": [],
        "missing_context": [],
        "hard_caps_applied": [],
        "downgrade_reasons": [],
        "scanner_sentence": None,
    }


def degraded_timeframe_alignment_object(reason: str) -> dict:
    obj = default_timeframe_alignment_object()
    obj["status"] = "DEGRADED"
    obj["downgrade_reasons"].append(str(reason))
    obj["missing_context"].append(str(reason))
    obj["scanner_sentence"] = build_scanner_sentence("INSUFFICIENT_CONTEXT")
    return obj


def error_timeframe_alignment_object(error: str) -> dict:
    obj = default_timeframe_alignment_object()
    obj["status"] = "ERROR"
    obj["alignment_label"] = "INSUFFICIENT_CONTEXT"
    obj["alignment_grade"] = "UNKNOWN"
    obj["alignment_score"] = 0
    obj["downgrade_reasons"].append(f"timeframe_alignment_error: {error}")
    obj["scanner_sentence"] = build_scanner_sentence("INSUFFICIENT_CONTEXT")
    return obj


def _blank_layer(timeframe: str, role: str) -> dict:
    return {
        "timeframe": timeframe,
        "role": role,
        "state": "UNKNOWN",
        "evidence": [],
        "warnings": [],
        "blocks_trigger": False,
    }


def safe_get(obj, *keys, default=None):
    """Defensively walk nested dict keys; never raises."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(ticker, tiering_result, enriched, config) -> dict:
    tfa_cfg = config.get("timeframe_alignment", {}) if isinstance(config, dict) else {}
    if tfa_cfg.get("enabled", True) is False:
        obj = default_timeframe_alignment_object()
        obj["enabled"] = False
        obj["status"] = "DISABLED"
        obj["scanner_sentence"] = None
        return obj

    obj = default_timeframe_alignment_object()

    signal = tiering_result.get("final_signal") or {}
    if not isinstance(signal, dict):
        signal = {}
    trade_location = tiering_result.get("trade_location") or {}
    one_hour = tiering_result.get("one_hour_entry") or {}

    # ---- Per-layer derivation (read-only) ---------------------------------
    weekly = derive_campaign_timeframe(signal, tiering_result, enriched)
    daily = derive_swing_timeframe(tiering_result, signal)
    operational = derive_operational_timeframe(trade_location, one_hour)
    trigger = derive_trigger_timeframe_from_one_hour_entry(one_hour)

    obj["campaign_timeframe"] = weekly
    obj["swing_timeframe"] = daily
    obj["operational_timeframe"] = operational
    obj["trigger_timeframe"] = trigger

    layers = {
        "1W": weekly, "1D": daily, "4H": operational, "1H": trigger,
    }

    # ---- Missing context (honest, actionable) -----------------------------
    missing = []
    if not trade_location or operational["state"] == "UNKNOWN":
        missing.append("4H operational location unavailable (no trade_location context)")
    if not one_hour or trigger["state"] == "UNKNOWN":
        missing.append("1H trigger proof unavailable (no usable one_hour_entry object)")
    obj["missing_context"] = missing

    # ---- Conflicts --------------------------------------------------------
    final_tier = str(tiering_result.get("final_tier", "")).upper()
    capital_action = str(tiering_result.get("capital_action", "")).lower()
    conflicts = _detect_conflicts(
        layers, final_tier, capital_action, signal, one_hour
    )
    obj["conflicts"] = conflicts

    # ---- Status (DEGRADED when a source layer is missing/inferred) --------
    status = "ENABLED"
    if missing:
        status = "DEGRADED"
    obj["status"] = status

    # ---- Classification cascade -------------------------------------------
    classifiable = sum(1 for L in layers.values() if L["state"] != "UNKNOWN")
    label = classify_alignment_label(layers, conflicts, classifiable)
    obj["alignment_label"] = label

    # ---- Scoring → caps → grade (order is mandatory) ----------------------
    raw_score = score_alignment(layers)
    invalidation_clear = _has_clear_invalidation(signal, one_hour)
    caps, cap_reasons = _collect_alignment_caps(
        layers, label, conflicts, invalidation_clear
    )
    capped = apply_alignment_caps(raw_score, caps)
    obj["alignment_score"] = capped
    obj["alignment_grade"] = grade_from_score(capped)
    obj["hard_caps_applied"] = list(caps.keys())
    obj["downgrade_reasons"].extend(cap_reasons)

    obj["scanner_sentence"] = build_scanner_sentence(label)
    return obj


# ---------------------------------------------------------------------------
# Layer derivations
# ---------------------------------------------------------------------------

def derive_campaign_timeframe(signal, tiering_result, enriched) -> dict:
    """Weekly campaign context — ALWAYS inferred (no standalone weekly bars)."""
    sub = _blank_layer("1W", "CAMPAIGN_CONTEXT")
    # Honesty law: weekly is inferred from existing HTF/tiering fields.
    sub["evidence"].append(
        "weekly context inferred from existing HTF/tiering fields; "
        "no standalone weekly bars attached"
    )
    sub["warnings"].append(
        "weekly context inferred; standalone weekly bars not attached"
    )

    trend = str(signal.get("trend_state", "") or "").lower().strip()
    structure = str(signal.get("structure_event", "") or "").lower().strip()
    overhead = str(signal.get("overhead_status", "") or "").lower().strip()

    hostile_overhead = overhead == "blocked"
    bullish_trend = trend in ("fresh_expansion", "mature_continuation", "basing")
    bullish_structure = structure in (
        "bos", "mss", "continuation", "accepted_break", "reclaim",
        "failed_breakdown_reclaim",
    )

    if trend in ("", "none") and structure in ("", "none"):
        state = "UNKNOWN"
    elif hostile_overhead and not bullish_trend:
        state = "CONFLICTED"
    elif trend == "failure":
        state = "BEARISH"
    elif bullish_trend and bullish_structure and not hostile_overhead:
        # Clear broad bullish continuation — still inferred, not bar-verified.
        state = "BULLISH"
    else:
        # Supportive-but-not-explicit, or inferred without strong signal.
        state = "NEUTRAL"

    sub["state"] = state
    sub["blocks_trigger"] = state in ("BEARISH", "CONFLICTED")
    if trend:
        sub["evidence"].append(f"broad trend proxy: trend_state={trend}")
    if structure:
        sub["evidence"].append(f"broad structure proxy: structure_event={structure}")
    if overhead:
        sub["evidence"].append(f"overhead_status={overhead}")
    if hostile_overhead:
        sub["warnings"].append("broad overhead reads blocked")
    return sub


def derive_swing_timeframe(tiering_result, signal) -> dict:
    """Daily swing permission — sourced from validated tiering fields."""
    sub = _blank_layer("1D", "SWING_PERMISSION")
    final_tier = str(tiering_result.get("final_tier", "") or "").upper().strip()
    safe = bool(tiering_result.get("safe_for_alert", False))
    capital_action = str(tiering_result.get("capital_action", "") or "").lower().strip()
    rejection = str(tiering_result.get("rejection_reason", "") or "").lower().strip()

    if final_tier in ("SNIPE_IT", "STARTER"):
        state = "PERMISSION_GRANTED" if safe else "PERMISSION_REPAIRING"
    elif final_tier == "NEAR_ENTRY":
        state = "PERMISSION_FORMING"
    elif final_tier == "INVALID":
        state = "PERMISSION_DENIED"
    elif final_tier == "WAIT":
        # WAIT alone is "no permission established", not necessarily an active
        # denial. Only an explicit invalid-setup rejection denies permission.
        if rejection and any(
            k in rejection for k in ("invalid", "hostile", "fail", "reject", "violat")
        ):
            state = "PERMISSION_DENIED"
        else:
            state = "UNKNOWN"
    elif capital_action == "wait_no_capital":
        state = "PERMISSION_FORMING"
    else:
        state = "UNKNOWN"

    sub["state"] = state
    sub["blocks_trigger"] = state == "PERMISSION_DENIED"
    if final_tier:
        sub["evidence"].append(f"final_tier={final_tier}")
    sub["evidence"].append(f"safe_for_alert={safe}")
    if capital_action:
        sub["evidence"].append(f"capital_action={capital_action}")
    if state == "PERMISSION_REPAIRING":
        sub["warnings"].append("setup tier present but not yet safe_for_alert")
    if state == "PERMISSION_DENIED" and rejection:
        sub["warnings"].append(f"swing permission denied: {rejection}")
    return sub


def derive_operational_timeframe(trade_location, one_hour) -> dict:
    """4H operational location.

    Sourced from tiering_result["trade_location"].location_state (the scanner's
    operational location object). FIELD_MAP: the spec assumed a
    trade_location.label with REALISTIC_ENTRY_LOCATION-style values, which does
    not exist — the real field is location_state. one_hour_entry.location_realism
    is used only as a fallback when trade_location is unavailable.
    """
    sub = _blank_layer("4H", "OPERATIONAL_LOCATION")
    loc_state = str(safe_get(trade_location, "location_state", default="") or "").lower().strip()

    state_map = {
        "mid_zone_acceptance": "LOCATION_VALID",
        "lower_zone_defense": "LOCATION_REPAIRING",
        "above_zone_extension": "LOCATION_EXTENDED",
        "upper_zone_expansion": "LOCATION_EXTENDED",
        "below_zone_failure": "LOCATION_HOSTILE",
    }
    state = state_map.get(loc_state)

    if state is not None:
        sub["evidence"].append(f"trade_location.location_state={loc_state}")
    else:
        # Fallback: the 1H location-realism label (closest available structured
        # entry-location quality signal) when trade_location is unknown.
        label = str(safe_get(one_hour, "location_realism", "label", default="") or "").upper().strip()
        fallback_map = {
            "REALISTIC_ENTRY_LOCATION": "LOCATION_VALID",
            "ACCEPTABLE_BUT_NOT_IDEAL": "LOCATION_REPAIRING",
            "EXTENDED_ENTRY_LOCATION": "LOCATION_EXTENDED",
            "MISSED_ENTRY": "LOCATION_EXTENDED",
            "MIDRANGE_NO_EDGE": "LOCATION_HOSTILE",
            "HOSTILE_LOCATION": "LOCATION_HOSTILE",
        }
        state = fallback_map.get(label, "UNKNOWN")
        if state != "UNKNOWN":
            sub["evidence"].append(
                f"trade_location unavailable; inferred from 1H location_realism={label}"
            )
            sub["warnings"].append("4H location inferred from 1H location_realism fallback")
        else:
            sub["warnings"].append("no usable 4H operational location context")

    sub["state"] = state
    sub["blocks_trigger"] = state == "LOCATION_HOSTILE"
    return sub


def derive_trigger_timeframe_from_one_hour_entry(one_hour) -> dict:
    """1H trigger proof — mapped from the existing one_hour_entry object only.

    Does NOT re-run any 1H candle logic. When one_hour_entry is missing,
    disabled, malformed, or carries no usable trigger fields → UNKNOWN.
    """
    sub = _blank_layer("1H", "TRIGGER_PROOF")
    if not isinstance(one_hour, dict) or not one_hour:
        sub["warnings"].append("one_hour_entry object missing")
        return sub
    status = str(one_hour.get("status", "DISABLED")).upper()
    if status == "DISABLED":
        sub["warnings"].append("one_hour_entry disabled")
        return sub

    trigger_state = str(one_hour.get("trigger_state", "") or "").upper().strip()
    alert_label = str(one_hour.get("alert_truth_label", "") or "").upper().strip()
    score_label = str(one_hour.get("score_label", "") or "").upper().strip()
    freshness = str(one_hour.get("data_freshness", "") or "").upper().strip()
    hold_truth = str(safe_get(one_hour, "pullback_retest_hold", "hold_truth", default="") or "").upper().strip()
    closed_confirms = bool(safe_get(one_hour, "candle_truth", "closed_candle_confirms", default=False))

    state = "UNKNOWN"

    # Failure / stale outrank everything (failure-first).
    if trigger_state in ("FAILED_RETEST", "INVALID_1H_TRIGGER") or alert_label == "FAILED_TRIGGER":
        state = "TRIGGER_FAILED"
    elif trigger_state == "STALE_TRIGGER" or freshness == "STALE":
        state = "TRIGGER_STALE"
    elif (
        trigger_state in ("TRIGGER_LIVE", "HOLD_CONFIRMED")
        or alert_label in ("CONFIRMED_TRIGGER", "LIVE_TRIGGER")
        or (score_label in ("1H_TRIGGER_A_PLUS", "1H_TRIGGER_VALID") and closed_confirms)
    ):
        state = "TRIGGER_CONFIRMED"
    elif trigger_state in ("HOLD_FORMING", "RETEST_IN_PROGRESS", "PULLBACK_FORMING") or alert_label == "FORMING_TRIGGER":
        state = "TRIGGER_FORMING"
    elif hold_truth == "HOLD_WEAK" or score_label == "1H_TRIGGER_WEAK" or alert_label == "WATCH_ONLY":
        state = "TRIGGER_WEAK"

    sub["state"] = state
    sub["blocks_trigger"] = state == "TRIGGER_FAILED"
    if trigger_state:
        sub["evidence"].append(f"one_hour_entry.trigger_state={trigger_state}")
    if alert_label:
        sub["evidence"].append(f"one_hour_entry.alert_truth_label={alert_label}")
    if score_label:
        sub["evidence"].append(f"one_hour_entry.score_label={score_label}")
    if freshness == "STALE":
        sub["warnings"].append("1H data stale")
    return sub


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------

def _detect_conflicts(layers, final_tier, capital_action, signal, one_hour) -> list:
    conflicts = []

    # 1. Any blocks_trigger == true.
    for tf, layer in layers.items():
        if layer.get("blocks_trigger"):
            conflicts.append({
                "layer": tf,
                "reason": f"{tf} {layer['state']} blocks trigger readiness",
            })

    # 2. Legacy-vs-1H contradiction (executable tier vs failed/stale 1H proof).
    one_h_state = layers["1H"]["state"]
    if final_tier in ("SNIPE_IT", "STARTER") and one_h_state in ("TRIGGER_FAILED", "TRIGGER_STALE"):
        conflicts.append({
            "layer": "1H",
            "reason": f"legacy tier {final_tier} contradicts 1H {one_h_state}",
        })

    # 3. Ceiling / overhead contradiction: overhead lock active while the
    #    capital action implies entry.
    overhead_status = str(signal.get("overhead_status", "") or "").lower().strip()
    oh_path = str(safe_get(one_hour, "path_quality", "path_label", default="") or "").upper().strip()
    ceiling_active = overhead_status == "blocked" or oh_path == "HOSTILE"
    if ceiling_active and capital_action in _CAPITAL_ENTRY_ACTIONS:
        conflicts.append({
            "layer": "4H",
            "reason": "overhead ceiling lock active while capital action implies entry",
        })

    return conflicts


def _is_contradiction_conflict(conflicts) -> bool:
    """True when any conflict is a hard contradiction (blocks classification)."""
    return bool(conflicts)


# ---------------------------------------------------------------------------
# Classification cascade (strict order — first match wins)
# ---------------------------------------------------------------------------

def classify_alignment_label(layers, conflicts, classifiable_count) -> str:
    weekly = layers["1W"]["state"]
    daily = layers["1D"]["state"]
    operational = layers["4H"]["state"]
    trigger = layers["1H"]["state"]

    # 1. Insufficient context — fewer than two classifiable layers.
    if classifiable_count < 2:
        return "INSUFFICIENT_CONTEXT"

    # 2. Conflicted — any blocking conflict.
    if _is_contradiction_conflict(conflicts):
        return "CONFLICTED"

    # 3. Full stack aligned.
    if (
        weekly in ("BULLISH", "NEUTRAL")
        and daily == "PERMISSION_GRANTED"
        and operational == "LOCATION_VALID"
        and trigger == "TRIGGER_CONFIRMED"
    ):
        return "FULL_STACK_ALIGNED"

    # 4. Lower-timeframe only — 1H evidence but Weekly AND Daily both unknown.
    if (
        trigger != "UNKNOWN"
        and weekly == "UNKNOWN"
        and daily == "UNKNOWN"
    ):
        return "LOWER_TIMEFRAME_ONLY"

    daily_not_denied = daily != "PERMISSION_DENIED"
    weekly_ok = weekly not in ("BEARISH", "CONFLICTED")
    op_not_hostile = operational != "LOCATION_HOSTILE"

    # 5. HTF aligned, trigger pending.
    if (
        daily_not_denied and weekly_ok and op_not_hostile
        and trigger in ("TRIGGER_FORMING", "TRIGGER_WEAK", "UNKNOWN")
    ):
        return "HTF_ALIGNED_TRIGGER_PENDING"

    # 6. HTF valid, 4H repairing.
    if (
        daily_not_denied and weekly_ok
        and operational in ("LOCATION_REPAIRING", "LOCATION_EXTENDED")
        and trigger != "TRIGGER_CONFIRMED"
    ):
        return "HTF_VALID_4H_REPAIR"

    # 7. Mixed alignment.
    supportive = _count_supportive(layers)
    soft = _count_soft(layers)
    if supportive >= 1 and soft >= 1:
        return "MIXED_ALIGNMENT"

    # 8. Else insufficient.
    return "INSUFFICIENT_CONTEXT"


_SUPPORTIVE_STATES = {
    "BULLISH", "PERMISSION_GRANTED", "PERMISSION_FORMING", "LOCATION_VALID",
    "TRIGGER_CONFIRMED", "TRIGGER_FORMING",
}
_SOFT_STATES = {
    "NEUTRAL", "UNKNOWN", "PERMISSION_REPAIRING", "LOCATION_REPAIRING",
    "LOCATION_EXTENDED", "TRIGGER_WEAK", "TRIGGER_STALE",
}


def _count_supportive(layers) -> int:
    return sum(1 for L in layers.values() if L["state"] in _SUPPORTIVE_STATES)


def _count_soft(layers) -> int:
    return sum(1 for L in layers.values() if L["state"] in _SOFT_STATES)


# ---------------------------------------------------------------------------
# Scoring → caps → grade
# ---------------------------------------------------------------------------

def score_alignment(layers) -> int:
    score = (
        _WEEKLY_POINTS.get(layers["1W"]["state"], 0)
        + _DAILY_POINTS.get(layers["1D"]["state"], 0)
        + _OPERATIONAL_POINTS.get(layers["4H"]["state"], 0)
        + _TRIGGER_POINTS.get(layers["1H"]["state"], 0)
    )
    return max(0, min(100, score))


def _collect_alignment_caps(layers, label, conflicts, invalidation_clear):
    """Return ({cap_name: ceiling}, [reasons]). Lowest cap wins."""
    caps = {}
    reasons = []

    def add(name, value, reason):
        caps[name] = value
        reasons.append(f"{name}: {reason} (cap {value})")

    if layers["1D"]["state"] == "PERMISSION_DENIED":
        add("DAILY_PERMISSION_DENIED", _CAP_DAILY_DENIED, "daily swing permission denied")
    if layers["4H"]["state"] == "LOCATION_HOSTILE":
        add("FOUR_HOUR_HOSTILE_LOCATION", _CAP_4H_HOSTILE, "4H operational location hostile")
    if layers["1H"]["state"] == "TRIGGER_FAILED":
        add("ONE_HOUR_TRIGGER_FAILED", _CAP_1H_FAILED, "1H trigger failed")
    if layers["1H"]["state"] == "TRIGGER_STALE":
        add("ONE_HOUR_TRIGGER_STALE", _CAP_1H_STALE, "1H trigger stale")
    if label == "LOWER_TIMEFRAME_ONLY":
        add("LOWER_TIMEFRAME_ONLY", _CAP_LOWER_TF_ONLY, "lower-timeframe-only evidence")
    if label == "INSUFFICIENT_CONTEXT":
        add("INSUFFICIENT_CONTEXT", _CAP_INSUFFICIENT, "insufficient context to classify")

    # Legacy-vs-1H contradiction cap.
    if any("legacy tier" in str(c.get("reason", "")) for c in conflicts):
        add("LEGACY_VS_1H_CONTRADICTION", _CAP_LEGACY_VS_1H, "legacy tier vs 1H proof contradiction")

    if not invalidation_clear:
        add("NO_CLEAR_INVALIDATION", _CAP_NO_INVALIDATION, "no clear invalidation in tiering/final_signal")

    if any("ceiling lock" in str(c.get("reason", "")) for c in conflicts):
        add("CEILING_BLOCKER_ACTIVE", _CAP_CEILING_BLOCKER, "overhead ceiling blocker active")

    return caps, reasons


def apply_alignment_caps(raw_score, caps) -> int:
    """Apply caps (lowest wins). Caps limit the score only — never the grade."""
    score = raw_score
    for ceiling in (caps or {}).values():
        score = min(score, ceiling)
    return max(0, min(100, score))


def grade_from_score(score) -> str:
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


def _has_clear_invalidation(signal, one_hour) -> bool:
    if signal.get("invalidation_level") is not None:
        return True
    if safe_get(one_hour, "invalidation", "clear", default=False):
        return True
    return False


# ---------------------------------------------------------------------------
# Scanner sentence
# ---------------------------------------------------------------------------

def build_scanner_sentence(label) -> str:
    return {
        "FULL_STACK_ALIGNED": (
            "Timeframe alignment: full stack aligned — Weekly/Daily/4H context "
            "supports the setup and 1H trigger proof is confirmed."
        ),
        "HTF_ALIGNED_TRIGGER_PENDING": (
            "Timeframe alignment: HTF context supports the setup; 1H trigger "
            "proof is still pending."
        ),
        "HTF_VALID_4H_REPAIR": (
            "Timeframe alignment: Daily/Weekly context remains valid, but 4H "
            "location is repairing or not fully ideal."
        ),
        "MIXED_ALIGNMENT": (
            "Timeframe alignment: mixed — some layers support the setup while "
            "others remain neutral, repairing, or unknown."
        ),
        "LOWER_TIMEFRAME_ONLY": (
            "Timeframe alignment: lower-timeframe evidence exists, but higher-"
            "timeframe context is insufficient; no higher-timeframe upgrade."
        ),
        "CONFLICTED": (
            "Timeframe alignment: conflicted — one or more timeframe layers "
            "contradict the setup."
        ),
        "INSUFFICIENT_CONTEXT": (
            "Timeframe alignment: insufficient context — scanner cannot classify "
            "full-stack alignment without guessing."
        ),
    }.get(label, (
        "Timeframe alignment: insufficient context — scanner cannot classify "
        "full-stack alignment without guessing."
    ))


# ---------------------------------------------------------------------------
# Discord rendering (display-only)
# ---------------------------------------------------------------------------

def render_timeframe_alignment_lines(tfa) -> list:
    """Compact, desk-readable multi-timeframe block. Display-only.

    Returns [] when the object is missing/disabled so alerts are never flooded.
    Never emits trigger-ready wording for non-FULL_STACK labels — sentences are
    label-derived. Enum values are rendered verbatim (never rewritten).
    """
    if not isinstance(tfa, dict):
        return []
    if tfa.get("enabled") is False or str(tfa.get("status", "DISABLED")) == "DISABLED":
        return []

    label = str(tfa.get("alignment_label", "INSUFFICIENT_CONTEXT"))
    sentence = str(tfa.get("scanner_sentence") or "").strip()
    grade = str(tfa.get("alignment_grade", "UNKNOWN"))
    score = tfa.get("alignment_score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    caps = tfa.get("hard_caps_applied") or []
    caps_text = ", ".join(str(c) for c in caps) if caps else "none"

    weekly = str(safe_get(tfa, "campaign_timeframe", "state", default="UNKNOWN"))
    daily = str(safe_get(tfa, "swing_timeframe", "state", default="UNKNOWN"))
    operational = str(safe_get(tfa, "operational_timeframe", "state", default="UNKNOWN"))
    trigger = str(safe_get(tfa, "trigger_timeframe", "state", default="UNKNOWN"))

    lines = [
        f"  TF alignment: {label} — {sentence}",
        f"  TF score:     {grade} {score}/100; caps: {caps_text}",
        f"  TF stack:     1W={weekly}, 1D={daily}, 4H={operational}, 1H={trigger}",
    ]

    conflicts = tfa.get("conflicts") or []
    if conflicts:
        first = conflicts[0]
        reason = str(first.get("reason", "")).strip() if isinstance(first, dict) else str(first)
        if reason:
            lines.append(f"  TF caution:   {reason}")

    # Inferred-weekly honesty note.
    weekly_warnings = safe_get(tfa, "campaign_timeframe", "warnings", default=[]) or []
    if any("inferred" in str(w).lower() for w in weekly_warnings):
        lines.append(
            "  TF note:      inferred weekly context; standalone weekly bars not attached."
        )

    return lines

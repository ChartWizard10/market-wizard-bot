"""1H Entry Trigger Evidence Engine — Phase 14E.1.

The dedicated trigger-proof organ. Weekly/Daily/4H remain sovereign — they own
the thesis. The 1H proves (or rejects) entry readiness only. It never invents
bias and never promotes a setup.

Doctrine (enforced):
  - The 1H proves the trigger; it does not create the thesis.
  - Closed 1H candle = evidence. Live 1H candle = developing information.
  - No invalidation = no trigger-ready alert.
  - No retest = no LIVE_TRIGGER.
  - Mid-range location = no trigger-ready alert.
  - Stale 1H data = no trigger-ready alert.
  - Location realism outranks candle excitement.
  - Higher-timeframe sovereignty is absolute.

Ownership rules (enforced permanently):
  - PURELY evidence/display-layer. NEVER raises in production.
  - NEVER mutates tiering_result, enriched, raw score, final_tier,
    capital_action, final_discord_channel, safe_for_alert, suppression, dedup,
    or state transitions.
  - It MAY record an alert_truth_label and hard_caps_applied, and MAY recommend
    a conservative score-realism cap that only score_calibration may read.
  - tiering.py remains the sole final authority on tier and gates.

No new indicators. No RSI/MACD/Bollinger/Stochastic. No SMA10 dependency added.
The engine reads only separately-acquired 1H OHLCV bars plus existing
higher-timeframe structure already present on the tiering_result / enriched dict.
"""

from datetime import datetime

from src import candle_evidence

_EPS = 1e-9

# ---------------------------------------------------------------------------
# Canonical enums (mandatory — never rename)
# ---------------------------------------------------------------------------

STATUS_VALUES = {"ENABLED", "DISABLED", "DEGRADED", "ERROR"}
FRESHNESS_VALUES = {"FRESH", "RECENT", "DEGRADED", "STALE"}
TRIGGER_STATES = {
    "NO_1H_EVIDENCE", "APPROACHING_LOCATION", "PULLBACK_FORMING",
    "RETEST_IN_PROGRESS", "HOLD_FORMING", "HOLD_CONFIRMED", "TRIGGER_LIVE",
    "FAILED_RETEST", "INVALID_1H_TRIGGER", "STALE_TRIGGER",
}
LOCATION_LABELS = {
    "REALISTIC_ENTRY_LOCATION", "ACCEPTABLE_BUT_NOT_IDEAL",
    "EXTENDED_ENTRY_LOCATION", "MIDRANGE_NO_EDGE", "HOSTILE_LOCATION",
    "MISSED_ENTRY",
}
CANDLE_EVENT_TYPES = {
    "DISPLACEMENT", "REJECTION", "ABSORPTION", "INDECISION", "TRAP_RECLAIM",
    "FAILURE", "NONE",
}
VOLUME_SUPPORT = {"STRONG", "ACCEPTABLE", "WEAK", "UNKNOWN"}
PULLBACK_TRUTH = {
    "PULLBACK_REAL", "PULLBACK_TOO_DEEP", "PULLBACK_TOO_SHALLOW",
    "PULLBACK_MIDRANGE_NO_EDGE", "NONE",
}
RETEST_TRUTH = {
    "RETEST_REAL", "RETEST_EDGE_ONLY", "RETEST_CORE_VALID", "RETEST_MISSED",
    "NONE",
}
HOLD_TRUTH = {
    "HOLD_CONFIRMED", "HOLD_FORMING", "HOLD_WEAK", "HOLD_FAILED", "NONE",
}
RETEST_ZONE_TYPES = {
    "BREAKOUT_LEVEL", "RECLAIM_LEVEL", "DEMAND_CORE", "FVG", "SMA_VALUE",
    "PRIOR_RESISTANCE_FLIP", "UNKNOWN",
}
PATH_LABELS = {"CLEAN", "ACCEPTABLE", "CAPPED", "HOSTILE", "UNKNOWN"}
SCORE_LABELS = {
    "1H_TRIGGER_A_PLUS", "1H_TRIGGER_VALID", "1H_TRIGGER_FORMING",
    "1H_TRIGGER_WEAK", "NO_VALID_1H_TRIGGER",
}
ALERT_TRUTH_LABELS = {
    "NO_ALERT", "WATCH_ONLY", "FORMING_TRIGGER", "CONFIRMED_TRIGGER",
    "LIVE_TRIGGER", "FAILED_TRIGGER",
}

# ---------------------------------------------------------------------------
# Tunables (one place for every threshold)
# ---------------------------------------------------------------------------

# Freshness thresholds in minutes from the latest 1H bar to "now".
_FRESH_MAX_MIN  = 150     # latest bar within ~2 hourly bars
_RECENT_MAX_MIN = 300     # within ~5 hourly bars
_DEGRADED_MAX_MIN = 1440  # within a trading day → context only

# Invalidation is "close" (high-quality) when within this percent of price.
_INVAL_CLOSE_PCT = 4.0
# Overhead "ceiling lock" distance — resistance directly overhead.
_OVERHEAD_LOCK_PCT = 1.0
_OVERHEAD_ACCEPTABLE_PCT = 3.0
# Extension above the zone (in ATR) past which entry is no longer at value.
_EXTENDED_ATR_MULT = 1.0
_MISSED_ATR_MULT = 2.0
_EXTENDED_PCT_FALLBACK = 3.0
_MISSED_PCT_FALLBACK = 6.0

# Hard caps (lowest applicable wins).
_CAP_LIVE_ONLY        = 79
_CAP_MIDRANGE         = 69
_CAP_EXTENDED         = 74
_CAP_NO_INVALIDATION  = 69
_CAP_FAILED_RETEST    = 49
_CAP_STALE            = 59
_CAP_NO_HTF           = 69
_CAP_NO_RETEST        = 74
_CAP_OVERHEAD_LOCK    = 79


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_one_hour_entry_context(
    ticker,
    tiering_result=None,
    enriched_data=None,
    one_hour_bars=None,
    htf_context=None,
    config=None,
) -> dict:
    """Build the 1H entry-trigger evidence context. NEVER raises.

    Args:
        ticker:         symbol (echo only).
        tiering_result: validated tiering result — read only (final_tier,
                        final_signal, trade_location). Never mutated.
        enriched_data:  indicators.enrich() output — read only (atr, zones).
        one_hour_bars:  separately-acquired 1H bars. Either a chronological list
                        (oldest→newest) of OHLC dicts, or an envelope dict
                        {"bars": [...], "freshness": ..., "now": ...}. The newest
                        bar may carry is_open=True to mark the live (forming) bar.
        htf_context:    optional higher-timeframe override dict (zone/levels).
        config:         doctrine config (read only).

    On any error returns a safe DEGRADED/ERROR object with a downgrade reason.
    """
    try:
        return _build(
            ticker, tiering_result or {}, enriched_data or {},
            one_hour_bars, htf_context or {}, config or {},
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all
        ctx = _disabled_context(status="ERROR", freshness="STALE")
        ctx["downgrade_reasons"].append(f"one_hour_entry_error: {exc}")
        ctx["scanner_sentence"] = "No 1H trigger evidence."
        return ctx


def render_one_hour_lines(one_hour) -> list:
    """Compact desk-readable 1H block for the alert body. Display-only.

    Returns [] when the object is missing/disabled so alerts are never flooded.
    """
    if not isinstance(one_hour, dict):
        return []
    status = str(one_hour.get("status", "DISABLED"))
    if status in ("DISABLED",):
        return []
    state = str(one_hour.get("trigger_state", "NO_1H_EVIDENCE"))
    sentence = str(one_hour.get("scanner_sentence") or "").strip()
    score = one_hour.get("score", 0)
    score_label = str(one_hour.get("score_label", "NO_VALID_1H_TRIGGER"))
    caps = one_hour.get("hard_caps_applied") or []
    truth = one_hour.get("pullback_retest_hold") or {}
    candle = one_hour.get("candle_truth") or {}
    location = one_hour.get("location_realism") or {}
    freshness = str(one_hour.get("data_freshness", "STALE"))

    caps_text = ", ".join(str(c) for c in caps) if caps else "none"
    lines = [
        f"  1H trigger: {state} — {sentence}",
        f"  1H score:   {score_label} {_safe_int(score)}/100; caps: {caps_text}",
        (
            "  1H truth:   "
            f"retest={truth.get('retest_truth', 'NONE')}, "
            f"hold={truth.get('hold_truth', 'NONE')}, "
            f"candle={candle.get('event_type', 'NONE')}, "
            f"location={location.get('label', 'MIDRANGE_NO_EDGE')}"
        ),
    ]
    if freshness in ("STALE", "DEGRADED"):
        lines.append(
            "  1H caution: stale/degraded bar context; "
            "trigger-ready wording blocked."
        )
    return lines


# ---------------------------------------------------------------------------
# Safe / disabled object
# ---------------------------------------------------------------------------

def _blank_context() -> dict:
    return {
        "enabled": True,
        "timeframe": "1H",
        "status": "ENABLED",
        "data_freshness": "FRESH",
        "bar_context": {
            "last_closed_bar_time": None,
            "current_live_bar_time": None,
            "closed_bar_available": False,
            "live_bar_available": False,
            "using_live_bar_for_confirmation": False,
        },
        "trigger_state": "NO_1H_EVIDENCE",
        "location_realism": {
            "label": "MIDRANGE_NO_EDGE",
            "reason": None,
            "distance_to_trigger_pct": None,
            "distance_to_invalidation_pct": None,
            "distance_to_overhead_pct": None,
        },
        "candle_truth": {
            "event_type": "NONE",
            "closed_candle_confirms": False,
            "live_candle_constructive": False,
            "body_acceptance": False,
            "wick_rejection": False,
            "follow_through_present": False,
            "volume_support": "UNKNOWN",
        },
        "pullback_retest_hold": {
            "pullback_truth": "NONE",
            "retest_truth": "NONE",
            "hold_truth": "NONE",
            "retest_zone_type": "UNKNOWN",
        },
        "invalidation": {
            "clear": False,
            "level": None,
            "condition": None,
            "invalidation_distance_pct": None,
        },
        "path_quality": {
            "overhead_clear_enough": False,
            "nearest_resistance": None,
            "rr_estimate": None,
            "path_label": "UNKNOWN",
        },
        "score": 0,
        "score_label": "NO_VALID_1H_TRIGGER",
        "hard_caps_applied": [],
        "downgrade_reasons": [],
        "alert_truth_label": "NO_ALERT",
        "scanner_sentence": None,
    }


def _disabled_context(status: str = "DISABLED", freshness: str = "STALE") -> dict:
    ctx = _blank_context()
    ctx["status"] = status
    ctx["enabled"] = status != "DISABLED"
    ctx["data_freshness"] = freshness
    ctx["scanner_sentence"] = "No 1H trigger evidence."
    return ctx


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(ticker, tiering_result, enriched, one_hour_bars, htf_context, config) -> dict:
    one_hour_cfg = config.get("one_hour", {}) if isinstance(config, dict) else {}
    if one_hour_cfg.get("enabled", True) is False:
        return _disabled_context(status="DISABLED")

    ctx = _blank_context()

    bars, freshness, now_ref, meta_status = _resolve_bars_envelope(
        one_hour_bars, one_hour_cfg
    )

    # Higher-timeframe reference structure (sovereign — read only).
    ref = _resolve_reference_levels(tiering_result, enriched, htf_context)
    final_tier = str(tiering_result.get("final_tier", "WAIT")).upper()
    htf_permission = final_tier in ("SNIPE_IT", "STARTER")
    htf_forming = final_tier == "NEAR_ENTRY"

    if not bars:
        ctx["status"] = "DEGRADED"
        ctx["data_freshness"] = "STALE"
        ctx["downgrade_reasons"].append("no separately-acquired 1H bars available")
        ctx["scanner_sentence"] = _sentence("NO_1H_EVIDENCE")
        ctx["alert_truth_label"] = "NO_ALERT"
        ctx["hard_caps_applied"].append("STALE_1H_DATA")
        return ctx

    # Split closed vs live bars.
    closed_bars, live_bar = _split_closed_live(bars)
    last_closed = closed_bars[-1] if closed_bars else None

    if freshness is None:
        freshness = _compute_freshness(bars, now_ref)
    if freshness not in FRESHNESS_VALUES:
        freshness = "FRESH"
    ctx["data_freshness"] = freshness

    ctx["bar_context"] = {
        "last_closed_bar_time": _bar_time(last_closed),
        "current_live_bar_time": _bar_time(live_bar),
        "closed_bar_available": last_closed is not None,
        "live_bar_available": live_bar is not None,
        "using_live_bar_for_confirmation": False,   # law: never true
    }

    if last_closed is None:
        ctx["status"] = "DEGRADED"
        ctx["downgrade_reasons"].append("no closed 1H candle available")
        ctx["scanner_sentence"] = _sentence("NO_1H_EVIDENCE")
        ctx["alert_truth_label"] = "NO_ALERT"
        return ctx

    # Reference price: the last *closed* bar close is the confirmation anchor.
    price = last_closed["close"]

    # ---- Invalidation -----------------------------------------------------
    inval = _build_invalidation(ref, price)
    ctx["invalidation"] = inval

    # ---- Distances --------------------------------------------------------
    dist_trigger = _pct(price, ref.get("trigger_level"))
    dist_inval = inval["invalidation_distance_pct"]
    dist_overhead = _pct(ref.get("overhead_level"), price)

    # ---- Candle truth (reuse the candle-evidence organ on 1H bars) --------
    candle_truth, closed_read = _build_candle_truth(
        closed_bars, live_bar, enriched, tiering_result, ref, final_tier
    )
    ctx["candle_truth"] = candle_truth

    # ---- Pullback / retest / hold -----------------------------------------
    prh = _build_pullback_retest_hold(
        closed_bars, live_bar, ref, price, inval, candle_truth, closed_read
    )
    ctx["pullback_retest_hold"] = prh

    # ---- Location realism -------------------------------------------------
    location = _build_location_realism(
        ref, price, enriched, inval, dist_trigger, dist_inval, dist_overhead, prh
    )
    ctx["location_realism"] = location

    # ---- Path quality -----------------------------------------------------
    path = _build_path_quality(ref, price, dist_overhead, inval)
    ctx["path_quality"] = path

    # ---- Trigger state machine --------------------------------------------
    trigger_state = _select_trigger_state(
        ref, price, inval, location, prh, candle_truth, htf_permission,
        htf_forming, freshness,
    )
    ctx["trigger_state"] = trigger_state

    # ---- Score + caps -----------------------------------------------------
    raw_score, breakdown = _score_categories(
        htf_permission, htf_forming, location, candle_truth, prh, inval, path,
    )
    caps, cap_reasons = _collect_caps(
        freshness, location, inval, prh, htf_permission, path, candle_truth,
        trigger_state,
    )
    score = raw_score
    for cap_value in caps.values():
        score = min(score, cap_value)
    score = max(0, min(100, score))
    ctx["score"] = score
    ctx["score_label"] = _score_label(score)
    ctx["hard_caps_applied"] = list(caps.keys())
    ctx["downgrade_reasons"].extend(cap_reasons)

    # Re-evaluate TRIGGER_LIVE against the final score (LIVE needs >= 80).
    if trigger_state == "TRIGGER_LIVE" and score < 80:
        trigger_state = "HOLD_CONFIRMED"
        ctx["trigger_state"] = trigger_state
        ctx["downgrade_reasons"].append(
            "1H trigger sequence complete but score realism below live threshold"
        )

    # ---- Alert governance -------------------------------------------------
    ctx["alert_truth_label"] = _alert_truth_label(
        freshness, trigger_state, inval, location, score, ctx["hard_caps_applied"],
    )
    ctx["scanner_sentence"] = _sentence(trigger_state)
    return ctx


# ---------------------------------------------------------------------------
# Bar envelope resolution
# ---------------------------------------------------------------------------

def _resolve_bars_envelope(one_hour_bars, one_hour_cfg):
    """Return (normalized_bars, freshness_or_None, now_ref, status)."""
    freshness = None
    now_ref = None
    raw_bars = one_hour_bars

    if isinstance(one_hour_bars, dict):
        raw_bars = one_hour_bars.get("bars")
        f = one_hour_bars.get("freshness")
        if isinstance(f, str) and f.upper() in FRESHNESS_VALUES:
            freshness = f.upper()
        now_ref = _parse_time(one_hour_bars.get("now"))

    bars = _normalize_bars(raw_bars)
    return bars, freshness, now_ref, "ok"


def _normalize_bars(raw) -> list:
    if not isinstance(raw, (list, tuple)) or not raw:
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        o = _f(item.get("open"))
        h = _f(item.get("high"))
        l = _f(item.get("low"))
        c = _f(item.get("close"))
        if None in (o, h, l, c):
            continue
        hi = max(h, o, c)
        lo = min(l, o, c)
        bar = {"open": o, "high": hi, "low": lo, "close": c}
        for k in ("volume", "avg_volume", "average_volume", "atr"):
            v = _f(item.get(k))
            if v is not None:
                bar[k] = v
        if item.get("is_open"):
            bar["is_open"] = True
        t = item.get("time", item.get("timestamp"))
        if t is not None:
            bar["time"] = t
        out.append(bar)
    return out


def _split_closed_live(bars):
    """The live (forming) bar, if any, is the newest bar flagged is_open."""
    if bars and bars[-1].get("is_open"):
        return bars[:-1], bars[-1]
    return bars, None


def _compute_freshness(bars, now_ref) -> str:
    newest = bars[-1] if bars else None
    t = _parse_time((newest or {}).get("time")) if newest else None
    if t is None:
        # No timestamp metadata — synthetic/replay bars are treated as current.
        return "FRESH"
    now = now_ref or datetime.utcnow()
    try:
        gap_min = abs((now - t).total_seconds()) / 60.0
    except Exception:
        return "FRESH"
    if gap_min <= _FRESH_MAX_MIN:
        return "FRESH"
    if gap_min <= _RECENT_MAX_MIN:
        return "RECENT"
    if gap_min <= _DEGRADED_MAX_MIN:
        return "DEGRADED"
    return "STALE"


# ---------------------------------------------------------------------------
# Reference structure (higher-timeframe sovereign levels — read only)
# ---------------------------------------------------------------------------

def _resolve_reference_levels(tiering_result, enriched, htf_context) -> dict:
    final_signal = tiering_result.get("final_signal") or {}
    location = tiering_result.get("trade_location") or {}

    zone_low = _f(htf_context.get("zone_low"))
    zone_mid = _f(htf_context.get("zone_mid"))
    zone_high = _f(htf_context.get("zone_high"))
    zone_type = str(htf_context.get("zone_type") or "").upper()

    if zone_low is None or zone_high is None:
        zl = _f(location.get("zone_low"))
        zm = _f(location.get("zone_mid"))
        zh = _f(location.get("zone_high"))
        zt = str(location.get("zone_type") or "").upper()
        if zl is not None and zh is not None and zh > zl:
            zone_low, zone_high = zl, zh
            zone_mid = zm if zm is not None else (zl + zh) / 2.0
            zone_type = zt

    if zone_low is None or zone_high is None:
        zl, zh, zt = _zone_from_enriched(enriched, final_signal)
        if zl is not None and zh is not None and zh > zl:
            zone_low, zone_high = zl, zh
            zone_mid = (zl + zh) / 2.0
            zone_type = zt

    trigger_level = _f(final_signal.get("trigger_level"))
    if trigger_level is None:
        trigger_level = _f(enriched.get("structure_level"))
    if trigger_level is None and zone_high is not None:
        trigger_level = zone_high

    invalidation_level = _f(final_signal.get("invalidation_level"))
    if invalidation_level is None:
        invalidation_level = _f(enriched.get("invalidation_level"))

    overhead_level = _f(final_signal.get("overhead_level"))
    if overhead_level is None:
        overhead_level = _f(enriched.get("overhead_level"))
    if overhead_level is None:
        overhead_level = _f(enriched.get("nearest_pool_above"))

    targets = final_signal.get("targets") or enriched.get("targets") or []

    atr = _f(enriched.get("atr"))

    return {
        "zone_low": zone_low,
        "zone_mid": zone_mid if zone_mid is not None else (
            (zone_low + zone_high) / 2.0
            if (zone_low is not None and zone_high is not None) else None
        ),
        "zone_high": zone_high,
        "zone_type": zone_type,
        "trigger_level": trigger_level,
        "invalidation_level": invalidation_level,
        "invalidation_condition": (
            final_signal.get("invalidation_condition")
            or enriched.get("invalidation_condition")
        ),
        "overhead_level": overhead_level,
        "targets": targets,
        "atr": atr,
        "structure_event": str(
            final_signal.get("structure_event")
            or enriched.get("structure_event") or ""
        ).lower(),
    }


def _zone_from_enriched(enriched, final_signal):
    fvg = enriched.get("fvg") if isinstance(enriched.get("fvg"), dict) else None
    ob = enriched.get("ob") if isinstance(enriched.get("ob"), dict) else None
    sig_zone = str(final_signal.get("zone_type") or "").upper()
    if "FVG" in sig_zone and fvg:
        lo, hi = _f(fvg.get("fvg_bot")), _f(fvg.get("fvg_top"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "FVG"
    if "OB" in sig_zone and ob:
        lo, hi = _f(ob.get("ob_lo")), _f(ob.get("ob_hi"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "OB"
    if fvg:
        lo, hi = _f(fvg.get("fvg_bot")), _f(fvg.get("fvg_top"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "FVG"
    if ob:
        lo, hi = _f(ob.get("ob_lo")), _f(ob.get("ob_hi"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "OB"
    return None, None, ""


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

def _build_invalidation(ref, price) -> dict:
    level = ref.get("invalidation_level")
    out = {
        "clear": False,
        "level": level,
        "condition": ref.get("invalidation_condition"),
        "invalidation_distance_pct": None,
    }
    if level is None or price is None or price <= 0:
        return out
    # A long-thesis invalidation must sit below current price to be coherent.
    out["invalidation_distance_pct"] = round((price - level) / price * 100, 2)
    out["clear"] = level < price
    return out


# ---------------------------------------------------------------------------
# Candle truth (reuse the candle_evidence engine on 1H bars)
# ---------------------------------------------------------------------------

_CONSTRUCTIVE_FAMILIES = {"DISPLACEMENT", "RETEST_HOLD", "CONTINUATION"}


def _build_candle_truth(closed_bars, live_bar, enriched, tiering_result, ref, final_tier):
    truth = {
        "event_type": "NONE",
        "closed_candle_confirms": False,
        "live_candle_constructive": False,
        "body_acceptance": False,
        "wick_rejection": False,
        "follow_through_present": False,
        "volume_support": "UNKNOWN",
    }
    if not closed_bars:
        return truth, {}

    # Read the most-recent closed candle's standalone character (no prior bar, so
    # inside/outside geometry never masks a genuine displacement/rejection at the
    # zone). The break/retest/hold *sequence* is proven separately below.
    closed_read = candle_evidence.build_candle_evidence_context(
        enriched=enriched,
        tiering_result=tiering_result,
        bars=[closed_bars[-1]],
        event_index=0,
        timeframe="1H",
    )

    # Sequence read: prior closed candle defended by the latest closed candle.
    seq_verdict = "PENDING"
    if len(closed_bars) >= 2:
        seq_read = candle_evidence.build_candle_evidence_context(
            enriched=enriched,
            tiering_result=tiering_result,
            bars=closed_bars,
            event_index=len(closed_bars) - 2,
            timeframe="1H",
        )
        seq_verdict = str(seq_read.get("next_candle_verdict", "PENDING"))

    family = str(closed_read.get("candle_family", "UNKNOWN"))
    close_quality = str(closed_read.get("close_quality", "UNKNOWN"))
    wick_read = str(closed_read.get("wick_read", "UNKNOWN"))
    veto = str(closed_read.get("candle_veto", "NONE")).upper()
    level_reaction = str(closed_read.get("level_reaction", "UNKNOWN"))
    body_pct = _f(closed_read.get("body_pct")) or 0.0
    close_pos = _f(closed_read.get("close_position_pct")) or 0.0

    truth["event_type"] = _map_event_type(
        family, level_reaction, closed_bars, ref, seq_verdict
    )
    truth["body_acceptance"] = body_pct >= 0.5 and close_pos >= 0.6
    truth["wick_rejection"] = wick_read == "LOWER_WICK_DEMAND_DEFENSE"
    truth["follow_through_present"] = seq_verdict in ("HOLD", "CONTINUATION")
    truth["volume_support"] = _map_volume_support(
        str(closed_read.get("volume_read", "UNKNOWN"))
    )

    strong_close = close_quality == "STRONG_BULLISH_CLOSE"
    truth["closed_candle_confirms"] = bool(
        family in _CONSTRUCTIVE_FAMILIES
        and strong_close
        and veto in ("NONE", "UNKNOWN")
        and truth["event_type"] != "FAILURE"
    )

    # Live candle: developing information only — can never set closed confirms.
    if live_bar is not None:
        live_read = candle_evidence.build_candle_evidence_context(
            enriched=enriched,
            tiering_result=tiering_result,
            bars=closed_bars + [live_bar],
            event_index=len(closed_bars),
            timeframe="1H",
        )
        lf = str(live_read.get("candle_family", "UNKNOWN"))
        lveto = str(live_read.get("candle_veto", "NONE")).upper()
        truth["live_candle_constructive"] = bool(
            lf in _CONSTRUCTIVE_FAMILIES and lveto != "HOSTILE_WICK"
        )

    return truth, closed_read


def _map_event_type(family, level_reaction, closed_bars, ref, seq_verdict) -> str:
    zone_low = ref.get("zone_low")
    engaged = _had_zone_engagement(closed_bars, ref)
    last = closed_bars[-1] if closed_bars else None

    # A genuine failed breakdown then reclaim outranks everything.
    if _detect_trap_reclaim(closed_bars, ref):
        return "TRAP_RECLAIM"

    # FAILURE means the level was actually lost — a closed acceptance back below
    # the zone after it had been engaged. A bearish candle that stays inside the
    # zone is a normal retest, not a failure.
    lost_level = (
        last is not None and zone_low is not None
        and last["close"] < zone_low - _EPS and engaged
    )
    if lost_level:
        return "FAILURE"

    # A denied push back into the zone (closed at/above zone_low) is a rejection.
    if family == "FAILED_BREAK":
        return "REJECTION"

    return {
        "DISPLACEMENT": "DISPLACEMENT",
        "REJECTION": "REJECTION",
        "RETEST_HOLD": "REJECTION",
        "ABSORPTION": "ABSORPTION",
        "DOJI_INDECISION": "INDECISION",
        "INSIDE_COMPRESSION": "INDECISION",
        "OUTSIDE_VOLATILITY": "INDECISION",
        "CONTINUATION": "DISPLACEMENT" if seq_verdict == "CONTINUATION" else "NONE",
        "UNRESOLVED": "NONE",
        "UNKNOWN": "NONE",
    }.get(family, "NONE")


def _had_zone_engagement(closed_bars, ref) -> bool:
    """True if any earlier closed bar broke above the trigger or accepted into/
    above the zone — i.e. the structure was actually engaged before the latest
    candle. Used to distinguish a failure from a first-time approach."""
    zone_low = ref.get("zone_low")
    zone_high = ref.get("zone_high")
    trigger = ref.get("trigger_level") or zone_high
    if zone_low is None:
        return False
    for bar in closed_bars[:-1]:
        if bar["close"] >= zone_low - _EPS:
            return True
        if trigger is not None and bar["high"] > trigger + _EPS:
            return True
    return False


def _detect_trap_reclaim(closed_bars, ref) -> bool:
    """A genuine failed breakdown: price was accepted above the zone, broke
    below it (trapping sellers), then reclaimed with a bullish close.

    The accept→break→reclaim ordering prevents a first-time approach from below
    being mistaken for a trap.
    """
    zone_low = ref.get("zone_low")
    if zone_low is None or len(closed_bars) < 3:
        return False
    window = closed_bars[-6:]
    accepted_above = False
    broke_below = False
    for bar in window[:-1]:
        if not accepted_above:
            if bar["close"] >= zone_low - _EPS:
                accepted_above = True
            continue
        if bar["close"] < zone_low - _EPS:
            broke_below = True
    last = window[-1]
    reclaimed = last["close"] > zone_low + _EPS and last["close"] > last["open"]
    return bool(accepted_above and broke_below and reclaimed)


def _map_volume_support(volume_read) -> str:
    return {
        "VOLUME_EXPANSION_CONFIRMED": "STRONG",
        "HEALTHY_RETEST_DRYUP": "ACCEPTABLE",
        "NORMAL": "ACCEPTABLE",
        "HIGH_VOLUME_NO_PROGRESS": "WEAK",
        "WEAK_PARTICIPATION": "WEAK",
        "UNKNOWN": "UNKNOWN",
    }.get(str(volume_read), "UNKNOWN")


# ---------------------------------------------------------------------------
# Pullback / retest / hold truth
# ---------------------------------------------------------------------------

def _build_pullback_retest_hold(
    closed_bars, live_bar, ref, price, inval, candle_truth, closed_read
) -> dict:
    out = {
        "pullback_truth": "NONE",
        "retest_truth": "NONE",
        "hold_truth": "NONE",
        "retest_zone_type": _map_retest_zone_type(ref),
    }
    zone_low = ref.get("zone_low")
    zone_mid = ref.get("zone_mid")
    zone_high = ref.get("zone_high")
    inval_level = inval.get("level")
    if zone_mid is None and zone_low is not None and zone_high is not None:
        zone_mid = (zone_low + zone_high) / 2.0

    if zone_low is None or zone_high is None:
        # No defensible structure: any move here is mid-range.
        out["pullback_truth"] = "PULLBACK_MIDRANGE_NO_EDGE"
        return out

    trigger = ref.get("trigger_level") or zone_high
    window = closed_bars[-10:]

    # A retest requires a real break above the trigger FIRST, then a return into
    # the zone — never a first-time approach from below. This is what prevents a
    # jump from APPROACHING_LOCATION straight to TRIGGER_LIVE.
    break_idx = None
    for i, b in enumerate(window):
        if b["high"] > trigger + _EPS and b["close"] > zone_low - _EPS:
            break_idx = i
            break

    edge_band = zone_high - 0.25 * (zone_high - zone_low)

    retest_low = None         # deepest low of the pullback after the break
    retest_idx = None
    if break_idx is not None:
        post = window[break_idx + 1:]
        returned = [b for b in post if b["low"] <= zone_high + _EPS]
        if returned:
            retest_low = min(b["low"] for b in returned)
            for j in range(break_idx + 1, len(window)):
                if window[j]["low"] <= zone_high + _EPS:
                    retest_idx = j

    # ---- Retest truth -----------------------------------------------------
    if break_idx is None:
        out["retest_truth"] = "NONE"
    elif retest_low is None:
        # Broke and ran without returning to value.
        if price > zone_high * (1 + _MISSED_PCT_FALLBACK / 100.0):
            out["retest_truth"] = "RETEST_MISSED"
        else:
            out["retest_truth"] = "NONE"
    elif retest_low <= zone_mid + _EPS:
        out["retest_truth"] = "RETEST_CORE_VALID"
    elif retest_low <= edge_band + _EPS:
        out["retest_truth"] = "RETEST_REAL"
    else:
        out["retest_truth"] = "RETEST_EDGE_ONLY"

    # ---- Pullback truth ---------------------------------------------------
    out["pullback_truth"] = _pullback_truth(
        break_idx, retest_low, zone_low, zone_high, inval_level, price
    )

    # ---- Hold truth -------------------------------------------------------
    out["hold_truth"] = _hold_truth(
        window, retest_idx, live_bar, ref, zone_mid, inval, out["retest_truth"],
        candle_truth, break_idx is not None,
    )
    return out


def _pullback_truth(break_idx, retest_low, zone_low, zone_high, inval_level, price):
    if break_idx is None:
        # Still approaching — no break/trigger yet.
        if price > zone_high * (1 + _EXTENDED_PCT_FALLBACK / 100.0):
            return "PULLBACK_TOO_SHALLOW"
        return "NONE"
    if retest_low is None:
        # Broke but never returned to value — chase territory.
        return "PULLBACK_TOO_SHALLOW"
    if inval_level is not None and retest_low < inval_level - _EPS:
        return "PULLBACK_TOO_DEEP"
    if retest_low < zone_low - _EPS and price < zone_low - _EPS:
        return "PULLBACK_TOO_DEEP"
    return "PULLBACK_REAL"


def _hold_truth(
    window, retest_idx, live_bar, ref, zone_mid, inval, retest_truth,
    candle_truth, break_occurred,
):
    zone_low = ref.get("zone_low")
    inval_level = inval.get("level")
    last_closed = window[-1] if window else None

    # Hard fail: accepted below invalidation always fails. Losing the zone only
    # counts as a hold failure once a trigger (break) actually occurred — a
    # first-time approach from below has nothing yet to hold.
    if last_closed is not None:
        if inval_level is not None and last_closed["close"] < inval_level - _EPS:
            return "HOLD_FAILED"
        if break_occurred and zone_low is not None and last_closed["close"] < zone_low - _EPS:
            return "HOLD_FAILED"

    if retest_truth in ("NONE", "RETEST_MISSED"):
        if live_bar is not None and candle_truth.get("live_candle_constructive"):
            return "HOLD_FORMING"
        return "NONE"

    # Is there a CLOSED defending candle after the pullback low?
    closed_defense = False
    if retest_idx is not None and retest_idx < len(window):
        for k in range(retest_idx, len(window)):
            b = window[k]
            if (
                b["close"] > b["open"]
                and (zone_mid is None or b["close"] >= zone_mid - _EPS)
            ):
                closed_defense = True
                break

    confirmed = closed_defense and (
        candle_truth.get("closed_candle_confirms")
        or candle_truth.get("follow_through_present")
        or candle_truth.get("body_acceptance")
    )

    if (
        confirmed
        and retest_truth in ("RETEST_REAL", "RETEST_CORE_VALID")
        and last_closed is not None
        and (zone_low is None or last_closed["close"] >= zone_low - _EPS)
    ):
        return "HOLD_CONFIRMED"

    if live_bar is not None and candle_truth.get("live_candle_constructive"):
        return "HOLD_FORMING"

    if retest_truth == "RETEST_EDGE_ONLY":
        return "HOLD_WEAK"

    return "HOLD_WEAK"


def _map_retest_zone_type(ref) -> str:
    zt = str(ref.get("zone_type") or "").upper()
    structure = str(ref.get("structure_event") or "").lower()
    if zt == "FVG":
        return "FVG"
    if zt == "OB":
        return "DEMAND_CORE"
    if structure in ("bos", "mss"):
        return "BREAKOUT_LEVEL"
    if structure in ("reclaim", "failed_breakdown_reclaim"):
        return "RECLAIM_LEVEL"
    if structure == "choch":
        return "PRIOR_RESISTANCE_FLIP"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Location realism
# ---------------------------------------------------------------------------

def _build_location_realism(
    ref, price, enriched, inval, dist_trigger, dist_inval, dist_overhead, prh
) -> dict:
    out = {
        "label": "MIDRANGE_NO_EDGE",
        "reason": None,
        "distance_to_trigger_pct": dist_trigger,
        "distance_to_invalidation_pct": dist_inval,
        "distance_to_overhead_pct": dist_overhead,
    }
    zone_low = ref.get("zone_low")
    zone_mid = ref.get("zone_mid")
    zone_high = ref.get("zone_high")
    atr = ref.get("atr")

    if zone_low is None or zone_high is None:
        out["label"] = "MIDRANGE_NO_EDGE"
        out["reason"] = "no defensible 1H structure at price"
        return out

    # Overhead ceiling lock outranks everything below it.
    if dist_overhead is not None and 0 <= dist_overhead < _OVERHEAD_LOCK_PCT:
        out["label"] = "HOSTILE_LOCATION"
        out["reason"] = "resistance directly overhead — ceiling lock"
        return out

    extended_threshold = (
        atr * _EXTENDED_ATR_MULT if (atr is not None and atr > 0)
        else zone_high * _EXTENDED_PCT_FALLBACK / 100.0
    )
    missed_threshold = (
        atr * _MISSED_ATR_MULT if (atr is not None and atr > 0)
        else zone_high * _MISSED_PCT_FALLBACK / 100.0
    )

    inval_level = inval.get("level")
    if inval_level is not None and price < inval_level - _EPS:
        out["label"] = "HOSTILE_LOCATION"
        out["reason"] = "price below invalidation — against structure"
        return out

    if price > zone_high + missed_threshold:
        out["label"] = "MISSED_ENTRY"
        out["reason"] = "clean entry already passed — far above value"
        return out

    if price > zone_high + extended_threshold:
        out["label"] = "EXTENDED_ENTRY_LOCATION"
        out["reason"] = "trigger real but extended from value"
        return out

    # At / inside / just under the zone — a defensible location.
    inval_close = (
        inval.get("clear")
        and dist_inval is not None
        and dist_inval <= _INVAL_CLOSE_PCT
    )
    path_ok = dist_overhead is None or dist_overhead >= _OVERHEAD_ACCEPTABLE_PCT
    realistic = (
        zone_low - _EPS <= price <= zone_high + extended_threshold
        and inval_close and path_ok
        and prh.get("retest_truth") in ("RETEST_REAL", "RETEST_CORE_VALID")
    )
    if realistic:
        out["label"] = "REALISTIC_ENTRY_LOCATION"
        out["reason"] = "defended structure, close invalidation, acceptable path"
        return out

    out["label"] = "ACCEPTABLE_BUT_NOT_IDEAL"
    out["reason"] = "valid location with one soft factor"
    return out


# ---------------------------------------------------------------------------
# Path quality
# ---------------------------------------------------------------------------

def _build_path_quality(ref, price, dist_overhead, inval) -> dict:
    out = {
        "overhead_clear_enough": False,
        "nearest_resistance": ref.get("overhead_level"),
        "rr_estimate": None,
        "path_label": "UNKNOWN",
    }
    # R:R estimate from first target and invalidation.
    target = _first_target_level(ref.get("targets"))
    inval_level = inval.get("level")
    if target is not None and inval_level is not None and price is not None:
        risk = price - inval_level
        reward = target - price
        if risk > 0 and reward > 0:
            out["rr_estimate"] = round(reward / risk, 2)

    if dist_overhead is None:
        out["path_label"] = "ACCEPTABLE"
        out["overhead_clear_enough"] = True
        return out
    if dist_overhead < _OVERHEAD_LOCK_PCT:
        out["path_label"] = "HOSTILE"
        out["overhead_clear_enough"] = False
    elif dist_overhead < _OVERHEAD_ACCEPTABLE_PCT:
        out["path_label"] = "CAPPED"
        out["overhead_clear_enough"] = False
    elif dist_overhead < 2 * _OVERHEAD_ACCEPTABLE_PCT:
        out["path_label"] = "ACCEPTABLE"
        out["overhead_clear_enough"] = True
    else:
        out["path_label"] = "CLEAN"
        out["overhead_clear_enough"] = True
    return out


def _first_target_level(targets):
    if isinstance(targets, list) and targets:
        first = targets[0]
        if isinstance(first, dict):
            return _f(first.get("level"))
        return _f(first)
    return None


# ---------------------------------------------------------------------------
# Trigger state machine
# ---------------------------------------------------------------------------

def _select_trigger_state(
    ref, price, inval, location, prh, candle_truth, htf_permission,
    htf_forming, freshness,
) -> str:
    zone_low = ref.get("zone_low")
    zone_high = ref.get("zone_high")
    loc = location.get("label")
    retest = prh.get("retest_truth")
    hold = prh.get("hold_truth")
    event = candle_truth.get("event_type")

    # 1. No usable structure at all.
    if zone_low is None or zone_high is None:
        return "NO_1H_EVIDENCE"

    # 2. Thesis directly contradicted: closed below invalidation. Only an
    #    accepted loss of invalidation invalidates the 1H trigger outright.
    inval_level = inval.get("level")
    if inval_level is not None and price < inval_level - _EPS:
        return "INVALID_1H_TRIGGER"

    # 3. Failed retest: lost the zone (above invalidation) or failed to hold.
    if hold == "HOLD_FAILED":
        return "FAILED_RETEST"
    if event == "FAILURE" and retest not in ("NONE", "RETEST_MISSED"):
        return "FAILED_RETEST"

    # 4. Missed / extended — trigger already happened, entry no longer clean.
    if loc == "MISSED_ENTRY" or retest == "RETEST_MISSED":
        return "STALE_TRIGGER"

    # 5. Confirmed closed-candle hold → live or confirmed.
    if hold == "HOLD_CONFIRMED":
        if (
            htf_permission
            and inval.get("clear")
            and retest in ("RETEST_REAL", "RETEST_CORE_VALID")
            and loc in ("REALISTIC_ENTRY_LOCATION", "ACCEPTABLE_BUT_NOT_IDEAL")
            and location.get("distance_to_overhead_pct") is not None
            and location["distance_to_overhead_pct"] >= _OVERHEAD_LOCK_PCT
        ):
            return "TRIGGER_LIVE"
        return "HOLD_CONFIRMED"

    # 6. Live defense forming.
    if hold == "HOLD_FORMING":
        return "HOLD_FORMING"

    # 7. Retest interaction without a hold yet.
    if retest in ("RETEST_REAL", "RETEST_CORE_VALID", "RETEST_EDGE_ONLY"):
        return "RETEST_IN_PROGRESS"

    # 8. Pullback forming toward the zone.
    if prh.get("pullback_truth") in ("PULLBACK_REAL", "PULLBACK_TOO_SHALLOW"):
        return "PULLBACK_FORMING"

    # 9. Approaching a valid location (HTF permission, near zone, no proof yet).
    if (htf_permission or htf_forming) and loc in (
        "ACCEPTABLE_BUT_NOT_IDEAL", "REALISTIC_ENTRY_LOCATION",
        "EXTENDED_ENTRY_LOCATION",
    ):
        return "APPROACHING_LOCATION"

    return "NO_1H_EVIDENCE"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_categories(htf_permission, htf_forming, location, candle_truth, prh, inval, path):
    # HTF alignment support (0-15)
    if htf_permission:
        htf = 15
    elif htf_forming:
        htf = 9
    else:
        htf = 0

    # Location realism (0-20)
    loc_pts = {
        "REALISTIC_ENTRY_LOCATION": 20,
        "ACCEPTABLE_BUT_NOT_IDEAL": 15,
        "EXTENDED_ENTRY_LOCATION": 9,
        "MIDRANGE_NO_EDGE": 4,
        "HOSTILE_LOCATION": 2,
        "MISSED_ENTRY": 2,
    }.get(location.get("label"), 4)

    # Candle truth (0-20)
    event = candle_truth.get("event_type")
    confirms = candle_truth.get("closed_candle_confirms")
    if event == "FAILURE":
        candle_pts = 0
    elif event == "DISPLACEMENT" and confirms:
        candle_pts = 20
    elif event in ("REJECTION", "TRAP_RECLAIM") and confirms:
        candle_pts = 17
    elif candle_truth.get("live_candle_constructive"):
        candle_pts = 12
    elif event == "ABSORPTION":
        candle_pts = 8
    elif event == "INDECISION":
        candle_pts = 6
    else:
        candle_pts = 7

    # Retest quality (0-15)
    retest_pts = {
        "RETEST_CORE_VALID": 15,
        "RETEST_REAL": 12,
        "RETEST_EDGE_ONLY": 7,
        "RETEST_MISSED": 2,
        "NONE": 4,
    }.get(prh.get("retest_truth"), 4)

    # Hold quality (0-15)
    hold_pts = {
        "HOLD_CONFIRMED": 15,
        "HOLD_FORMING": 9,
        "HOLD_WEAK": 5,
        "HOLD_FAILED": 0,
        "NONE": 3,
    }.get(prh.get("hold_truth"), 3)

    # Invalidation clarity (0-10)
    if not inval.get("clear"):
        inval_pts = 0
    elif (
        inval.get("invalidation_distance_pct") is not None
        and inval["invalidation_distance_pct"] <= _INVAL_CLOSE_PCT
    ):
        inval_pts = 10
    else:
        inval_pts = 6

    # Path / R:R cleanliness (0-5)
    path_pts = {
        "CLEAN": 5,
        "ACCEPTABLE": 4,
        "CAPPED": 2,
        "HOSTILE": 0,
        "UNKNOWN": 2,
    }.get(path.get("path_label"), 2)

    breakdown = {
        "htf_alignment": htf,
        "location_realism": loc_pts,
        "candle_truth": candle_pts,
        "retest_quality": retest_pts,
        "hold_quality": hold_pts,
        "invalidation_clarity": inval_pts,
        "path_quality": path_pts,
    }
    return sum(breakdown.values()), breakdown


def _collect_caps(
    freshness, location, inval, prh, htf_permission, path, candle_truth,
    trigger_state,
):
    """Return (caps: {name: cap_value}, reasons: list[str]). Lowest cap wins."""
    caps = {}
    reasons = []

    def add(name, value, reason):
        caps[name] = value
        reasons.append(f"{name}: {reason} (cap {value})")

    if freshness == "STALE":
        add("STALE_1H_DATA", _CAP_STALE, "1H data stale — cannot prove trigger")

    if prh.get("hold_truth") == "HOLD_FAILED" or trigger_state == "FAILED_RETEST":
        add("FAILED_RETEST", _CAP_FAILED_RETEST, "1H retest failed")

    if not inval.get("clear"):
        add("NO_CLEAR_INVALIDATION", _CAP_NO_INVALIDATION, "no clear 1H invalidation")

    loc = location.get("label")
    if loc == "MIDRANGE_NO_EDGE":
        add("MIDRANGE_LOCATION", _CAP_MIDRANGE, "mid-range — no structural edge")
    elif loc == "EXTENDED_ENTRY_LOCATION":
        add("EXTENDED_LOCATION", _CAP_EXTENDED, "extended from value")

    if not htf_permission:
        add("NO_HTF_PERMISSION", _CAP_NO_HTF, "higher-timeframe setup not yet valid")

    if prh.get("retest_truth") in ("NONE", "RETEST_MISSED"):
        add("NO_RETEST", _CAP_NO_RETEST, "no real retest of structure")

    if path.get("path_label") == "HOSTILE":
        add("OVERHEAD_CEILING_LOCK", _CAP_OVERHEAD_LOCK, "direct overhead ceiling lock")

    # Live-candle-only confirmation: no closed proof yet.
    if (
        candle_truth.get("live_candle_constructive")
        and not candle_truth.get("closed_candle_confirms")
        and prh.get("hold_truth") != "HOLD_CONFIRMED"
    ):
        add("LIVE_CANDLE_ONLY", _CAP_LIVE_ONLY, "live candle only — no closed proof")

    return caps, reasons


def _score_label(score) -> str:
    if score >= 90:
        return "1H_TRIGGER_A_PLUS"
    if score >= 80:
        return "1H_TRIGGER_VALID"
    if score >= 70:
        return "1H_TRIGGER_FORMING"
    if score >= 60:
        return "1H_TRIGGER_WEAK"
    return "NO_VALID_1H_TRIGGER"


# ---------------------------------------------------------------------------
# Alert governance
# ---------------------------------------------------------------------------

def _alert_truth_label(freshness, trigger_state, inval, location, score, caps) -> str:
    if freshness == "STALE":
        return "NO_ALERT"
    if trigger_state in ("INVALID_1H_TRIGGER", "FAILED_RETEST"):
        return "FAILED_TRIGGER"
    if not inval.get("clear"):
        return "NO_ALERT"
    if location.get("label") in ("MIDRANGE_NO_EDGE", "HOSTILE_LOCATION", "MISSED_ENTRY"):
        return "NO_ALERT"
    if trigger_state == "HOLD_FORMING":
        return "FORMING_TRIGGER"
    if trigger_state == "HOLD_CONFIRMED":
        return "CONFIRMED_TRIGGER"
    if trigger_state == "TRIGGER_LIVE" and score >= 80:
        return "LIVE_TRIGGER"
    return "WATCH_ONLY"


# ---------------------------------------------------------------------------
# Scanner sentence (state-derived; never entry-ready unless state earns it)
# ---------------------------------------------------------------------------

def _sentence(trigger_state) -> str:
    return {
        "NO_1H_EVIDENCE": "No 1H trigger evidence.",
        "APPROACHING_LOCATION": "Approaching 1H trigger zone. No entry proof yet.",
        "PULLBACK_FORMING": "Pullback forming into valid trigger area. Await retest/hold evidence.",
        "RETEST_IN_PROGRESS": "1H retest in progress. Hold not confirmed until closed candle defense.",
        "HOLD_FORMING": "1H hold forming. Live candle constructive but unconfirmed.",
        "HOLD_CONFIRMED": "1H hold confirmed on closed candle. Trigger evidence improving.",
        "TRIGGER_LIVE": "1H trigger live: break/retest/hold sequence confirmed, invalidation clear.",
        "FAILED_RETEST": "1H retest failed. Entry thesis downgraded.",
        "INVALID_1H_TRIGGER": "1H trigger invalid. No entry.",
        "STALE_TRIGGER": "1H trigger already occurred but entry is no longer clean.",
    }.get(trigger_state, "No 1H trigger evidence.")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _pct(numer, denom) -> float | None:
    a = _f(numer)
    b = _f(denom)
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / b * 100, 2)


def _bar_time(bar):
    if not isinstance(bar, dict):
        return None
    t = bar.get("time")
    if t is None:
        return None
    if isinstance(t, datetime):
        return t.isoformat()
    return str(t)


def _parse_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _f(val) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:                       # NaN guard
        return None
    return f

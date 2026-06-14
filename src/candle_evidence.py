"""Candle Evidence Quality Engine — Phase 14C.3.

A candle is not a pattern. A candle is a completed auction receipt:

  Bodies = accepted value.
  Wicks  = rejected value.
  Close  = control snapshot.
  Next candle = verdict.

This module reads the just-closed event candle (and, when supplied, its prior
and next candles) and returns a deterministic, defensive evidence context that
describes what was attempted, accepted, rejected, and whether the next candle
confirmed, denied, or left the claim unresolved.

Ownership rules (enforced permanently):
  - PURELY informational / evidence-layer. It NEVER raises in production.
  - NEVER mutates tiering_result, enriched, or the raw score.
  - NEVER affects final_tier, capital_action, final_discord_channel,
    safe_for_alert, suppression, dedup, or state transitions.
  - It may RECOMMEND a bounded score_delta ([-4, +3]); only score_calibration
    may apply that to calibrated_score. tiering.py remains the sole final
    authority on tier and gates.

No new indicators. No SMA10. No RSI/MACD/Bollinger/Stochastic. The engine reads
only existing OHLCV, existing ATR, existing FVG/OB context, existing SMA fields
if already present, and existing trade_location context.

Production reality: at the live scan edge the most recent closed candle has no
next candle yet, so next_candle_verdict is honestly PENDING. The HOLD / FAIL /
CONTINUATION verdict logic activates when a caller (tests, backtests, replay)
supplies a completed event+next pair via `bars`.
"""

_EPS = 1e-9

# Baseline evidence thresholds (classifications, not hard gates).
_BODY_DOMINANT       = 0.60   # body_pct >= → dominant body
_BODY_DOJI           = 0.20   # body_pct <= → doji / indecision candidate
_BODY_ABSORPTION     = 0.35   # small-ish body ceiling for absorption
_CLOSE_BULL          = 0.75   # close_position_pct >= → bullish close quality
_CLOSE_BEAR          = 0.25   # close_position_pct <= → bearish close quality
_WICK_MAJOR          = 0.45   # wick_pct >= → major wick
_RANGE_ATR_EXPANSION = 1.20   # range_atr_ratio >= → expansion / displacement
_VOL_EXPANSION       = 1.20   # volume_ratio >= → participation expansion
_VOL_DRYUP           = 0.80   # volume_ratio <= on retest → possible healthy dry-up

# Candle contribution bounds (the engine never recommends beyond these).
_DELTA_CEIL  =  3
_DELTA_FLOOR = -4

_FAMILIES = {
    "DISPLACEMENT", "RETEST_HOLD", "REJECTION", "ABSORPTION", "DOJI_INDECISION",
    "FAILED_BREAK", "INSIDE_COMPRESSION", "OUTSIDE_VOLATILITY", "CONTINUATION",
    "UNRESOLVED", "UNKNOWN",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_candle_evidence_context(
    enriched: dict | None = None,
    tiering_result: dict | None = None,
    bars: list | None = None,
    event_index: int | None = None,
    timeframe: str | None = None,
) -> dict:
    """Return the candle-evidence context dict. NEVER raises.

    Args:
        enriched:       indicators.enrich() output for this ticker. Used to build
                        a single event candle from current_open/high/low/close
                        and to read atr / volume_ratio / fvg / ob when `bars` is
                        not supplied.
        tiering_result: validated tiering result, used only to read the final
                        signal's tier, zone, trigger, and the attached
                        trade_location context.
        bars:           optional chronological OHLCV list (oldest -> newest).
                        Each item is a dict with open/high/low/close and optional
                        volume / avg_volume / is_open. Enables inside/outside and
                        next-candle verdict logic.
        event_index:    optional index into `bars` of the event candle. Defaults
                        to the last bar (live edge → next verdict PENDING).
        timeframe:      optional timeframe label for display/echo only.
    """
    try:
        return _build(enriched or {}, tiering_result or {}, bars, event_index, timeframe)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        ctx = _unknown_context()
        ctx["warnings"] = [f"candle_evidence_error: {exc}"]
        return ctx


def humanize_candle_veto(veto) -> str:
    """Compact, desk-readable caution text for a candle_veto code."""
    return {
        "NONE": "",
        "OPEN_ONLY": "candle still open; close not confirmed.",
        "NO_CLOSE_CONFIRMATION": "close confirmation missing.",
        "NO_NEXT_CANDLE_VERDICT": "next-candle verdict pending.",
        "DOJI_AT_TRIGGER": "doji at trigger; confirmation incomplete.",
        "HOSTILE_WICK": "hostile wick against the setup direction.",
        "FAILED_RETEST": "failed retest; no fresh aggression.",
        "HIGH_VOLUME_NO_PROGRESS": "high-volume effort produced limited progress.",
        "EXTENDED_FROM_VALUE": "extended from value; chase risk.",
        "MID_RANGE_NO_LEVEL": "mid-range; no level interaction.",
        "UNKNOWN": "",
    }.get(str(veto or "NONE"), "")


# ---------------------------------------------------------------------------
# Default / unknown context
# ---------------------------------------------------------------------------

def _unknown_context() -> dict:
    return {
        "status": "unknown",
        "timeframe": None,
        "candle_status": "UNKNOWN",
        "event_index": None,
        "body_pct": None,
        "upper_wick_pct": None,
        "lower_wick_pct": None,
        "close_position_pct": None,
        "range_atr_ratio": None,
        "volume_ratio": None,
        "candle_family": "UNKNOWN",
        "close_quality": "UNKNOWN",
        "wick_read": "UNKNOWN",
        "volume_read": "UNKNOWN",
        "level_reaction": "UNKNOWN",
        "next_candle_verdict": "UNKNOWN",
        "candle_veto": "UNKNOWN",
        "score_delta": 0,
        "score_reason": "",
        "display_text": "",
        "proof_level": None,
        "failure_level": None,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(
    enriched: dict,
    tiering_result: dict,
    bars: list | None,
    event_index: int | None,
    timeframe: str | None,
) -> dict:
    ctx = _unknown_context()
    ctx["timeframe"] = timeframe

    final_signal = tiering_result.get("final_signal") or {}
    final_tier   = str(tiering_result.get("final_tier", "WAIT")).upper()
    location     = tiering_result.get("trade_location") or {}

    norm_bars = _normalize_bars(bars)
    from_bars = bool(norm_bars)

    if from_bars:
        idx = event_index if event_index is not None else len(norm_bars) - 1
        idx = max(0, min(idx, len(norm_bars) - 1))
        event = norm_bars[idx]
        prior = norm_bars[idx - 1] if idx - 1 >= 0 else None
        nxt   = norm_bars[idx + 1] if idx + 1 < len(norm_bars) else None
        ctx["event_index"] = idx
    else:
        event = _event_from_enriched(enriched)
        prior = None
        nxt   = None
        ctx["event_index"] = None

    if event is None:
        ctx["status"] = "insufficient_data"
        ctx["candle_status"] = "UNKNOWN"
        ctx["candle_veto"] = "NO_CLOSE_CONFIRMATION"
        ctx["next_candle_verdict"] = "NOT_AVAILABLE"
        ctx["display_text"] = ""
        ctx["warnings"].append("no usable OHLC for event candle")
        return ctx

    o, h, l, c = event["open"], event["high"], event["low"], event["close"]
    is_open = bool(event.get("is_open"))

    rng = h - l
    if rng <= _EPS:
        # Zero-range bar: defined but uninformative. Never raise.
        ctx["status"] = "insufficient_data"
        ctx["candle_status"] = "OPEN_OR_UNKNOWN" if is_open else "CLOSED"
        ctx["body_pct"] = 0.0
        ctx["upper_wick_pct"] = 0.0
        ctx["lower_wick_pct"] = 0.0
        ctx["close_position_pct"] = 0.5
        ctx["candle_family"] = "DOJI_INDECISION"
        ctx["close_quality"] = "UNRESOLVED"
        ctx["wick_read"] = "NO_MAJOR_WICK"
        ctx["candle_veto"] = "NO_CLOSE_CONFIRMATION"
        ctx["next_candle_verdict"] = "NOT_AVAILABLE" if not from_bars else "PENDING"
        ctx["display_text"] = "flat candle — no range; verdict pending."
        ctx["warnings"].append("zero-range candle")
        return ctx

    ctx["status"] = "ok"
    ctx["candle_status"] = "OPEN_OR_UNKNOWN" if is_open else "CLOSED"

    # ---- Metrics ----------------------------------------------------------
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_pct = _clip01(body / max(rng, _EPS))
    upper_wick_pct = _clip01(upper_wick / max(rng, _EPS))
    lower_wick_pct = _clip01(lower_wick / max(rng, _EPS))
    close_position_pct = _clip01((c - l) / max(rng, _EPS))

    ctx["body_pct"] = round(body_pct, 4)
    ctx["upper_wick_pct"] = round(upper_wick_pct, 4)
    ctx["lower_wick_pct"] = round(lower_wick_pct, 4)
    ctx["close_position_pct"] = round(close_position_pct, 4)

    atr = _safe_float(event.get("atr"))
    if atr is None:
        atr = _safe_float(enriched.get("atr"))
    if atr is not None and atr > 0:
        ctx["range_atr_ratio"] = round(rng / atr, 3)

    vol_ratio = _resolve_volume_ratio(event, enriched)
    ctx["volume_ratio"] = round(vol_ratio, 3) if vol_ratio is not None else None

    bull = c > o
    bear = c < o

    # ---- Close quality ----------------------------------------------------
    ctx["close_quality"] = _close_quality(body_pct, close_position_pct, bull, bear)

    # ---- Wick read --------------------------------------------------------
    ctx["wick_read"] = _wick_read(upper_wick_pct, lower_wick_pct, bull, bear)

    # ---- Volume read ------------------------------------------------------
    ctx["volume_read"] = _volume_read(vol_ratio, body_pct, ctx["range_atr_ratio"])

    # ---- Level context ----------------------------------------------------
    zone_low, zone_high, zone_label = _resolve_zone(location, enriched, final_signal)
    at_level = _interacts_with_zone(l, h, zone_low, zone_high)
    ctx["level_reaction"] = _level_reaction(
        c, o, zone_low, zone_high, at_level, bull, bear, close_position_pct
    )

    # ---- Hostile wick (opposite the setup direction on a long-biased setup)-
    hostile_wick = _hostile_wick(final_tier, upper_wick_pct, lower_wick_pct)

    # ---- Family classification -------------------------------------------
    family = _classify_family(
        body_pct=body_pct,
        upper_wick_pct=upper_wick_pct,
        lower_wick_pct=lower_wick_pct,
        close_position_pct=close_position_pct,
        range_atr_ratio=ctx["range_atr_ratio"],
        vol_ratio=vol_ratio,
        bull=bull,
        bear=bear,
        at_level=at_level,
        zone_low=zone_low,
        zone_high=zone_high,
        close=c,
        event=event,
        prior=prior,
        hostile_wick=hostile_wick,
    )
    ctx["candle_family"] = family

    # ---- Proof / failure levels ------------------------------------------
    proof_level, failure_level = _proof_failure_levels(
        family, bull, bear, h, l, zone_low, zone_high
    )
    ctx["proof_level"] = proof_level
    ctx["failure_level"] = failure_level

    # ---- Next-candle verdict ---------------------------------------------
    verdict = _next_candle_verdict(
        nxt, from_bars, bull, bear, proof_level, failure_level, h, l
    )
    ctx["next_candle_verdict"] = verdict

    # ---- Veto -------------------------------------------------------------
    ctx["candle_veto"] = _candle_veto(
        family=family,
        verdict=verdict,
        is_open=is_open,
        hostile_wick=hostile_wick,
        at_level=at_level,
        volume_read=ctx["volume_read"],
        final_tier=final_tier,
        body_pct=body_pct,
    )

    # ---- Score delta ------------------------------------------------------
    delta, reason = _score_delta(
        family=family,
        verdict=verdict,
        veto=ctx["candle_veto"],
        close_quality=ctx["close_quality"],
        volume_read=ctx["volume_read"],
        hostile_wick=hostile_wick,
        final_tier=final_tier,
    )
    ctx["score_delta"] = max(_DELTA_FLOOR, min(_DELTA_CEIL, int(delta)))
    ctx["score_reason"] = reason

    # ---- Display ----------------------------------------------------------
    ctx["display_text"] = _display_text(family, zone_label, verdict, ctx["level_reaction"])

    return ctx


# ---------------------------------------------------------------------------
# Bar normalization & event extraction
# ---------------------------------------------------------------------------

def _normalize_bars(bars) -> list:
    if not isinstance(bars, (list, tuple)) or not bars:
        return []
    out: list[dict] = []
    for raw in bars:
        bar = _normalize_one_bar(raw)
        if bar is not None:
            out.append(bar)
    return out


def _normalize_one_bar(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    o = _safe_float(raw.get("open"))
    h = _safe_float(raw.get("high"))
    l = _safe_float(raw.get("low"))
    c = _safe_float(raw.get("close"))
    if None in (o, h, l, c):
        return None
    # Defensive: ensure high/low actually bound open/close.
    hi = max(h, o, c)
    lo = min(l, o, c)
    bar = {"open": o, "high": hi, "low": lo, "close": c}
    for k in ("volume", "avg_volume", "average_volume", "atr"):
        v = _safe_float(raw.get(k))
        if v is not None:
            bar[k] = v
    if raw.get("is_open"):
        bar["is_open"] = True
    return bar


def _event_from_enriched(enriched: dict) -> dict | None:
    o = _safe_float(enriched.get("current_open"))
    h = _safe_float(enriched.get("current_high"))
    l = _safe_float(enriched.get("current_low"))
    c = _safe_float(enriched.get("current_price"))
    if c is None:
        c = _safe_float(enriched.get("close"))
    if None in (o, h, l, c):
        return None
    hi = max(h, o, c)
    lo = min(l, o, c)
    return {"open": o, "high": hi, "low": lo, "close": c}


def _resolve_volume_ratio(event: dict, enriched: dict) -> float | None:
    vol = _safe_float(event.get("volume"))
    avg = _safe_float(event.get("avg_volume"))
    if avg is None:
        avg = _safe_float(event.get("average_volume"))
    if vol is not None and avg is not None and avg > 0:
        return vol / avg
    # Fall back to the already-computed enriched volume_ratio.
    return _safe_float(enriched.get("volume_ratio"))


# ---------------------------------------------------------------------------
# Component reads
# ---------------------------------------------------------------------------

def _close_quality(body_pct, close_position_pct, bull, bear) -> str:
    if close_position_pct >= _CLOSE_BULL and bull:
        return "STRONG_BULLISH_CLOSE"
    if close_position_pct <= _CLOSE_BEAR and bear:
        return "STRONG_BEARISH_CLOSE"
    if body_pct <= _BODY_DOJI:
        return "WEAK_CLOSE"
    if _CLOSE_BEAR < close_position_pct < _CLOSE_BULL:
        return "MID_RANGE_CLOSE"
    return "MID_RANGE_CLOSE"


def _wick_read(upper_wick_pct, lower_wick_pct, bull, bear) -> str:
    upper_major = upper_wick_pct >= _WICK_MAJOR
    lower_major = lower_wick_pct >= _WICK_MAJOR
    if upper_major and lower_major:
        return "DOUBLE_WICK_UNRESOLVED"
    if lower_major:
        return "LOWER_WICK_DEMAND_DEFENSE"
    if upper_major:
        return "UPPER_WICK_SUPPLY_REJECTION"
    return "NO_MAJOR_WICK"


def _volume_read(vol_ratio, body_pct, range_atr_ratio) -> str:
    if vol_ratio is None:
        return "UNKNOWN"
    if vol_ratio >= _VOL_EXPANSION:
        # High effort: did it produce result?
        limited = body_pct <= _BODY_ABSORPTION or (
            range_atr_ratio is not None and range_atr_ratio < _RANGE_ATR_EXPANSION
        )
        if limited and body_pct <= _BODY_ABSORPTION:
            return "HIGH_VOLUME_NO_PROGRESS"
        return "VOLUME_EXPANSION_CONFIRMED"
    if vol_ratio <= _VOL_DRYUP:
        return "HEALTHY_RETEST_DRYUP"
    return "NORMAL"


def _resolve_zone(location: dict, enriched: dict, final_signal: dict):
    """Return (zone_low, zone_high, zone_label) from location, then fvg/ob."""
    zl = _safe_float(location.get("zone_low"))
    zh = _safe_float(location.get("zone_high"))
    ztype = str(location.get("zone_type") or "").upper()
    if zl is not None and zh is not None and zh > zl:
        label = ztype if ztype in ("FVG", "OB") else "zone"
        return zl, zh, label

    sig_zone = str(final_signal.get("zone_type") or "").upper()
    fvg = enriched.get("fvg") if isinstance(enriched.get("fvg"), dict) else None
    ob = enriched.get("ob") if isinstance(enriched.get("ob"), dict) else None

    if "FVG" in sig_zone and fvg:
        lo, hi = _safe_float(fvg.get("fvg_bot")), _safe_float(fvg.get("fvg_top"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "FVG"
    if "OB" in sig_zone and ob:
        lo, hi = _safe_float(ob.get("ob_lo")), _safe_float(ob.get("ob_hi"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "OB"
    if fvg:
        lo, hi = _safe_float(fvg.get("fvg_bot")), _safe_float(fvg.get("fvg_top"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "FVG"
    if ob:
        lo, hi = _safe_float(ob.get("ob_lo")), _safe_float(ob.get("ob_hi"))
        if lo is not None and hi is not None and hi > lo:
            return lo, hi, "OB"
    return None, None, "zone"


def _interacts_with_zone(low, high, zone_low, zone_high) -> bool:
    if zone_low is None or zone_high is None:
        return False
    return low <= zone_high + _EPS and high >= zone_low - _EPS


def _level_reaction(close, open_, zone_low, zone_high, at_level, bull, bear, close_pos) -> str:
    if zone_low is None or zone_high is None:
        return "MID_RANGE_NO_LEVEL"
    if not at_level:
        if close > zone_high:
            return "ACCEPTED_ABOVE_LEVEL"
        if close < zone_low:
            return "LOST_LEVEL"
        return "MID_RANGE_NO_LEVEL"
    # Interacting with the zone.
    if close >= zone_low and bull and close_pos >= 0.55:
        return "DEFENDED_ZONE"
    if close < zone_low:
        return "FAILED_ZONE"
    if close > zone_high:
        return "RECLAIMED_LEVEL"
    if bear and close_pos <= 0.45:
        return "REJECTED_FROM_LEVEL"
    return "UNRESOLVED"


def _hostile_wick(final_tier, upper_wick_pct, lower_wick_pct) -> bool:
    # Long-biased executable tiers: a dominant UPPER wick is hostile (supply
    # rejection against the long). The scanner is long-only.
    if final_tier in ("SNIPE_IT", "STARTER"):
        return upper_wick_pct >= _WICK_MAJOR and upper_wick_pct > lower_wick_pct
    return False


# ---------------------------------------------------------------------------
# Family classification
# ---------------------------------------------------------------------------

def _classify_family(
    body_pct, upper_wick_pct, lower_wick_pct, close_position_pct,
    range_atr_ratio, vol_ratio, bull, bear, at_level, zone_low, zone_high,
    close, event, prior, hostile_wick,
) -> str:
    # 1. Multi-bar structural reads (only when prior bar supplied).
    if prior is not None:
        ph, pl = prior["high"], prior["low"]
        eh, el = event["high"], event["low"]
        if eh <= ph + _EPS and el >= pl - _EPS:
            return "INSIDE_COMPRESSION"
        if eh >= ph - _EPS and el <= pl + _EPS and (eh > ph or el < pl):
            return "OUTSIDE_VOLATILITY"

    big_range = range_atr_ratio is not None and range_atr_ratio >= _RANGE_ATR_EXPANSION
    small_body = body_pct <= _BODY_DOJI
    absorption_body = body_pct <= _BODY_ABSORPTION
    high_vol = vol_ratio is not None and vol_ratio >= _VOL_EXPANSION
    mid_close = _CLOSE_BEAR < close_position_pct < _CLOSE_BULL
    double_wick = upper_wick_pct >= _WICK_MAJOR and lower_wick_pct >= _WICK_MAJOR

    # 2. Absorption: high effort, small body, limited progress.
    if high_vol and absorption_body and not big_range:
        return "ABSORPTION"

    # 3. Doji / indecision: tiny body with mid close or competing wicks.
    if small_body and (mid_close or double_wick):
        return "DOJI_INDECISION"

    # 4. Failed break: closed back through a contested level after probing past.
    if at_level and zone_low is not None and zone_high is not None:
        probed_below = event["low"] < zone_low - _EPS
        probed_above = event["high"] > zone_high + _EPS
        closed_back_in = zone_low - _EPS <= close <= zone_high + _EPS
        if probed_below and close < zone_low - _EPS and bear:
            return "FAILED_BREAK"
        if probed_above and closed_back_in and close_position_pct <= 0.45:
            return "FAILED_BREAK"

    # 5. Displacement: dominant body, directional control close, expansion.
    if (
        body_pct >= _BODY_DOMINANT
        and ((bull and close_position_pct >= _CLOSE_BULL)
             or (bear and close_position_pct <= _CLOSE_BEAR))
        and (range_atr_ratio is None or big_range)
        and not hostile_wick
    ):
        return "DISPLACEMENT"

    # 6. At-level wick reactions: rejection vs retest-hold.
    if at_level:
        if bull and lower_wick_pct >= _WICK_MAJOR and close_position_pct >= 0.60:
            if body_pct >= 0.50 and close_position_pct >= 0.70 and (
                zone_low is None or close >= zone_low
            ):
                return "RETEST_HOLD"
            return "REJECTION"
        if bear and upper_wick_pct >= _WICK_MAJOR and close_position_pct <= 0.40:
            return "REJECTION"
        # Body-driven defended hold without a dominant wick.
        if bull and body_pct >= 0.50 and close_position_pct >= 0.60 and (
            zone_low is None or close >= zone_low
        ):
            return "RETEST_HOLD"

    # 7. Benign directional continuation.
    if body_pct >= 0.40 and (
        (bull and close_position_pct >= 0.60) or (bear and close_position_pct <= 0.40)
    ):
        return "CONTINUATION"

    # 8. Nothing resolved cleanly.
    if small_body:
        return "DOJI_INDECISION"
    return "UNRESOLVED"


def _proof_failure_levels(family, bull, bear, high, low, zone_low, zone_high):
    """Proof = level whose reclaim/acceptance confirms; failure = level whose
    loss invalidates the candle's claim."""
    proof = high if bull else (low if bear else None)
    if zone_high is not None and bull:
        proof = max(proof, zone_high) if proof is not None else zone_high
    failure = low if bull else (high if bear else None)
    if zone_low is not None and bull:
        failure = min(failure, zone_low) if failure is not None else zone_low
    proof = round(proof, 4) if proof is not None else None
    failure = round(failure, 4) if failure is not None else None
    return proof, failure


# ---------------------------------------------------------------------------
# Next-candle verdict
# ---------------------------------------------------------------------------

def _next_candle_verdict(nxt, from_bars, bull, bear, proof_level, failure_level, high, low) -> str:
    if nxt is None:
        # No next candle: honest pending at the live edge, else not available.
        return "PENDING" if from_bars else "NOT_AVAILABLE"

    nc = nxt["close"]
    no, nh, nl = nxt["open"], nxt["high"], nxt["low"]
    n_body = abs(nc - no)
    n_range = max(nh - nl, _EPS)
    n_body_pct = n_body / n_range

    # Indecision: next candle is tiny / non-committal.
    if n_body_pct <= _BODY_DOJI:
        return "INDECISION"

    if bull:
        if failure_level is not None and nc < failure_level - _EPS:
            return "FAIL"
        if proof_level is not None and nc > proof_level + _EPS:
            return "CONTINUATION"
        if nc >= (failure_level if failure_level is not None else low):
            return "HOLD"
        return "FAIL"
    if bear:
        if failure_level is not None and nc > failure_level + _EPS:
            return "FAIL"
        if proof_level is not None and nc < proof_level - _EPS:
            return "CONTINUATION"
        if nc <= (failure_level if failure_level is not None else high):
            return "HOLD"
        return "FAIL"
    return "INDECISION"


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------

def _candle_veto(
    family, verdict, is_open, hostile_wick, at_level, volume_read, final_tier, body_pct,
) -> str:
    if is_open:
        return "OPEN_ONLY"
    if verdict == "FAIL":
        return "FAILED_RETEST"
    if family == "FAILED_BREAK":
        return "FAILED_RETEST"
    if family == "DOJI_INDECISION" and at_level:
        return "DOJI_AT_TRIGGER"
    if hostile_wick and final_tier in ("SNIPE_IT", "STARTER"):
        return "HOSTILE_WICK"
    if volume_read == "HIGH_VOLUME_NO_PROGRESS":
        return "HIGH_VOLUME_NO_PROGRESS"
    if (
        final_tier == "SNIPE_IT"
        and family in ("DOJI_INDECISION", "ABSORPTION", "UNRESOLVED")
        and verdict not in ("HOLD", "CONTINUATION")
    ):
        return "NO_NEXT_CANDLE_VERDICT"
    if family == "OUTSIDE_VOLATILITY" and verdict not in ("HOLD", "CONTINUATION"):
        return "NO_NEXT_CANDLE_VERDICT"
    if family == "MID_RANGE_NO_LEVEL":
        return "MID_RANGE_NO_LEVEL"
    return "NONE"


# ---------------------------------------------------------------------------
# Score delta
# ---------------------------------------------------------------------------

def _score_delta(
    family, verdict, veto, close_quality, volume_read, hostile_wick, final_tier,
) -> tuple[int, str]:
    strong_close = close_quality in ("STRONG_BULLISH_CLOSE", "STRONG_BEARISH_CLOSE")
    confirmed = verdict in ("HOLD", "CONTINUATION")

    # ---- Negative-first: contradictions outweigh quality. -----------------
    if verdict == "FAIL":
        return -3, "candle failed next-candle verdict"
    if family == "FAILED_BREAK":
        return -3, "candle failed retest"
    if hostile_wick and final_tier in ("SNIPE_IT", "STARTER"):
        return -3, "hostile wick against setup direction"
    if family == "DOJI_INDECISION" and veto == "DOJI_AT_TRIGGER":
        if final_tier == "SNIPE_IT":
            return -4, "doji at trigger contradicts capital language"
        return -2, "doji at trigger"
    if veto == "NO_NEXT_CANDLE_VERDICT" and final_tier == "SNIPE_IT":
        return -4, "no next-candle verdict on unresolved candle"
    if volume_read == "HIGH_VOLUME_NO_PROGRESS":
        return -2, "high-volume effort produced limited progress"
    if family in ("DOJI_INDECISION", "ABSORPTION", "UNRESOLVED"):
        return -2, "absorption / indecision unresolved"
    if family == "OUTSIDE_VOLATILITY":
        return -1, "outside volatility unresolved"
    if close_quality == "MID_RANGE_CLOSE":
        return -1, "mid-range close"
    if volume_read == "WEAK_PARTICIPATION":
        return -1, "weak participation"

    # ---- Positive: confirmed structure earns score realism. ---------------
    if family == "RETEST_HOLD" and confirmed and strong_close:
        return +3, "candle retest-hold confirmed"
    if family == "RETEST_HOLD" and confirmed:
        return +2, "candle retest-hold confirmed"
    if family == "DISPLACEMENT" and strong_close and not hostile_wick:
        if confirmed:
            return +3, "displacement accepted and held"
        return +2, "clean displacement with control close"
    if family == "RETEST_HOLD":
        return +1, "early hold, verdict pending"
    if family == "CONTINUATION":
        return +1, "mild continuation"
    if family == "INSIDE_COMPRESSION":
        return 0, "inside compression — expansion pending"

    return 0, "normal candle, no contradiction"


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _display_text(family, zone_label, verdict, level_reaction) -> str:
    held = " hold confirmed" if verdict in ("HOLD", "CONTINUATION") else ""
    zl = zone_label if zone_label in ("FVG", "OB") else "level"
    base = {
        "DISPLACEMENT":
            "displacement — strong body and control close; retest still determines execution.",
        "RETEST_HOLD":
            "retest hold — zone defended with close control.",
        "REJECTION":
            f"rejection — denied value at active {zl};{held or ' follow-through determines quality.'}".rstrip(),
        "ABSORPTION":
            "absorption candidate — high effort, limited result; wait for escape from range.",
        "DOJI_INDECISION":
            "indecision — doji/small body at decision area; next candle verdict required.",
        "FAILED_BREAK":
            "failed break — attempted acceptance denied; trap risk active.",
        "INSIDE_COMPRESSION":
            "compression — inside range; expansion close required.",
        "OUTSIDE_VOLATILITY":
            "outside volatility — control unresolved unless close/next candle resolves.",
        "CONTINUATION":
            "continuation — directional close; momentum intact pending retest.",
        "UNRESOLVED":
            "unresolved — candle evidence incomplete; verdict pending.",
        "UNKNOWN": "",
    }.get(family, "")
    if family == "REJECTION" and held:
        base = f"rejection — denied value at active {zl};{held}."
    return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip01(x: float) -> float:
    if x != x:               # NaN guard
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _safe_float(val) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:               # NaN guard
        return None
    return f

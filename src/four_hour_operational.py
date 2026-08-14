"""Real 4H Operational Evidence Engine — Phase R4H-1.

The 4H timeframe owns operational location, repair state, the entry
neighborhood, structural sequence, retest/hold quality, local invalidation and
the local target path. Until this phase the scanner labeled a Daily-derived
proxy "4H". This module reads an ACTUAL session-aligned four-hour chart and
answers those questions from real candles.

    Structure -> Liquidity -> Displacement -> Retest -> Hold -> Invalidation -> Target

Candle law:

    A live 4H candle is information.
    A closed COMPLETE 4H candle is evidence.
    A missing constituent candle is missing evidence.
    A wick is not a hold.
    A touch is not a retest confirmation.
    A live breach is a threat; a closed accepted breach is failure.

AUTHORITY: none. `authority_mode` is a permanent SHADOW_EVIDENCE_ONLY. The
Phase-14F operational proxy remains production-authoritative for alignment,
gates, ladder and capital. This organ only records what a real 4H chart says
and where it disagrees with the proxy. R4H-2 is the authority-handoff phase.

Ownership rules (enforced permanently):
  - PURE and deterministic. No network. No environment reads. No clock reads
    beyond the caller-supplied envelope timestamps.
  - NEVER mutates tiering_result, enriched, the proxy object, or the bars.
  - NEVER affects raw_score, score, final_tier, capital_action, safe_for_alert,
    routing, ladder, gate, seal, dedup, cooldown or suppression.
  - NEVER raises into production — degrades to a safe object instead.

The 4H may read confirmed Daily context. It may say it supports, repairs or
conflicts with the Daily campaign. It may never grant Daily permission.
"""

import logging
from datetime import datetime

from src import candle_evidence as _ce

log = logging.getLogger(__name__)

ENGINE_VERSION = "R4H-1"
AUTHORITY_MODE = "SHADOW_EVIDENCE_ONLY"

_EPS = 1e-9

# ---------------------------------------------------------------------------
# NUMERIC THRESHOLD GOVERNOR (Phase R4H-1, section 27)
#
# REUSED — existing scanner thresholds, semantically valid here, imported
# rather than re-invented so 4H candle reads match the rest of the scanner:
#   _ce._BODY_DOMINANT       0.60  body share => dominant body
#   _ce._BODY_DOJI           0.20  body share => indecision
#   _ce._CLOSE_BULL          0.75  close position => bullish control close
#   _ce._WICK_MAJOR          0.45  wick share => major wick
#   _ce._RANGE_ATR_EXPANSION 1.20  range/ATR => expansion / displacement
#   _ce._VOL_EXPANSION       1.20  volume ratio => participation expansion
#   _ce._VOL_DRYUP           0.80  volume ratio => dry-up
#
# REUSED from indicators/config semantics:
#   _RETEST_PROXIMITY_ATR    0.5   mirrors indicators.assess_retest's 0.5-ATR
#                                  "partial retest" proximity band.
#   ATR period 14                  mirrors indicators.compute_atr's default.
#   overhead_block_distance_pct    read from config (default 3) exactly as
#                                  indicators.assess_overhead uses it, incl.
#                                  its *2.5 "moderate" multiplier.
#
# NEW SHADOW-EVIDENCE CONSTANTS — research thresholds for this organ only.
# They are NOT doctrine, they are NOT written to config, and they govern no
# capital decision. Each answers one distinct structural question.
# ---------------------------------------------------------------------------

_PIVOT_N = 2                    # swing pivot half-width in 4H bars (~1 session
                                # either side; Daily uses 3 over far more bars)
_MIN_CONFIRMED_BARS = 12        # ~6 sessions — below this the 4H chart cannot
                                # support a structural verdict at all
_EDGE_BAND = 0.25               # range position within 25% of an extreme = edge
_MID_BAND_HALF = 0.10           # +/-10% around the range midpoint = MID_RANGE
_EXTENDED_ATR = 2.0             # ATRs above the nearest defendable structure
                                # beyond which location is EXTENDED
_COMPRESSION_RATIO = 0.75       # recent avg range / prior avg range below which
                                # the auction is contracting
_OVERLAP_HIGH = 0.60            # mean bar-to-bar overlap above which structure
                                # is overlapping rather than directional
_PATH_COMPRESSED_MULT = 1.5     # multiple of the config block distance marking
                                # the COMPRESSED band between BLOCKED and MODERATE
_RETEST_PROXIMITY_ATR = 0.5     # reused from indicators.assess_retest

_SMA_PERIODS = (10, 20, 50)
_ATR_PERIOD = 14

_STRUCTURAL_STATES = ("EXPANSION", "CONTINUATION", "COMPRESSION", "REPAIR",
                      "TRANSITION", "FAILURE", "UNKNOWN")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_four_hour_operational_context(
    ticker,
    tiering_result=None,
    enriched_data=None,
    four_hour_bars=None,
    config=None,
) -> dict:
    """Build the real 4H operational evidence object. NEVER raises."""
    try:
        return _build(ticker, tiering_result or {}, enriched_data or {},
                      four_hour_bars, config or {})
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log.warning("FOUR_HOUR_OPERATIONAL_ERROR: %s: %s", ticker, exc)
        return error_four_hour_object(str(exc))


def default_four_hour_object(status: str = "INSUFFICIENT") -> dict:
    """Safe degraded object. Every field present, nothing claimed."""
    return {
        "enabled": True,
        "engine_version": ENGINE_VERSION,
        "status": status,
        "authority_mode": AUTHORITY_MODE,
        "timeframe": "4H",
        "bar_context": {
            "source_interval": None,
            "aggregation": None,
            "source_request_reused": True,
            "last_closed_4h_time": None,
            "current_live_4h_time": None,
            "closed_bar_available": False,
            "live_bar_available": False,
            "last_closed_source_complete": False,
            "latest_bucket_status": "NONE",
            "using_live_bar_for_confirmation": False,
            "history_bars": 0,
            "confirmed_history_bars": 0,
            "sessions_covered": 0,
            "freshness_status": "UNKNOWN",
        },
        "structural_state": "UNKNOWN",
        "state_confidence": "INSUFFICIENT",
        "operational_location": "UNKNOWN",
        "operational_readiness": "INSUFFICIENT",
        "structure": {
            "swing_highs": [], "swing_lows": [],
            "last_swing_high": None, "last_swing_low": None,
            "range_high": None, "range_low": None, "range_position": None,
            "ladder": "UNKNOWN",
            "break_state": "UNKNOWN", "break_level": None,
            "reclaim_state": "UNKNOWN", "reclaim_level": None,
        },
        "liquidity": {
            "buyside_target": None, "sellside_target": None,
            "prior_swing_high": None, "prior_swing_low": None,
            "swept_level": None, "sweep_state": "UNKNOWN",
            "liquidity_threat": None,
        },
        "displacement": {"state": "UNKNOWN", "origin": None,
                         "body_pct": None, "range_atr_ratio": None},
        "retest_truth": {"state": "UNKNOWN", "anchor": None, "anchor_level": None,
                         "distance_atr": None},
        "hold_truth": {"state": "UNKNOWN", "basis": None},
        "candle_truth": {"status": "UNKNOWN", "body_pct": None,
                         "close_position_pct": None, "wick_read": "UNKNOWN",
                         "close_quality": "UNKNOWN"},
        "location": {"state": "UNKNOWN", "reason": None, "reference_level": None,
                     "distance_atr": None, "price": None},
        "zone_context": {"fvg": None, "fvg_state": "UNKNOWN", "demand_core": None},
        "value_context": {"sma10": None, "sma20": None, "sma50": None,
                          "stack": "UNAVAILABLE", "price_vs_value": "UNKNOWN",
                          "unavailable": list(_SMA_PERIODS)},
        "volume_participation": {"volume_ratio": None, "volume_behavior": "UNKNOWN",
                                 "volume_comparison_basis": "SAME_SESSION_SLOT",
                                 "slot": None, "baseline_samples": 0},
        "invalidation_quality": {"status": "UNCLEAR", "level": None, "basis": None,
                                 "risk_distance_pct": None},
        "target_path": {"path_class": "UNKNOWN", "next_objective": None,
                        "objective_basis": None, "distance_pct": None},
        "failure_truth": {"state": "UNKNOWN", "level": None, "basis": None},
        "daily_relationship": "UNKNOWN",
        "sequence": {
            "structure": "UNKNOWN", "liquidity": "UNKNOWN",
            "displacement": "UNKNOWN", "retest": "UNKNOWN", "hold": "UNKNOWN",
            "invalidation": "UNKNOWN", "target": "UNKNOWN",
        },
        "hard_failures": [],
        "soft_warnings": [],
        "missing_proofs": [],
        "scanner_sentence": "",
        "proxy_comparison": None,
    }


def error_four_hour_object(message: str) -> dict:
    obj = default_four_hour_object("ERROR")
    obj["soft_warnings"] = [f"four_hour_operational_error: {message}"]
    obj["scanner_sentence"] = "4H operational evidence unavailable."
    return obj


# ---------------------------------------------------------------------------
# Real-vs-proxy comparison (pure; mutates neither input)
# ---------------------------------------------------------------------------

# Rank of real operational location as an execution neighborhood, best first.
_REAL_RANK = {"DEFENDABLE": 4, "REPAIRING": 3, "MID_RANGE": 2,
              "EXTENDED": 1, "HOSTILE": 0}
# Rank of the Phase-14F proxy state on the same scale.
_PROXY_RANK = {"LOCATION_VALID": 4, "LOCATION_REPAIRING": 3,
               "LOCATION_EXTENDED": 1, "LOCATION_HOSTILE": 0}


def compare_real_vs_proxy(proxy_state, real_obj) -> dict:
    """Compare the Phase-14F proxy operational state with real 4H evidence.

    Pure. Never edits either object. Disagreement is the point — real evidence
    is never bent to match the proxy.
    """
    real = real_obj if isinstance(real_obj, dict) else {}
    proxy = str(proxy_state or "").upper().strip() or "UNKNOWN"
    real_loc = str(real.get("operational_location") or "UNKNOWN").upper()
    real_state = str(real.get("structural_state") or "UNKNOWN").upper()
    real_ready = str(real.get("operational_readiness") or "INSUFFICIENT").upper()

    reasons = []
    p_rank = _PROXY_RANK.get(proxy)
    r_rank = _REAL_RANK.get(real_loc)

    if p_rank is None or r_rank is None:
        agreement = "UNKNOWN"
        if p_rank is None:
            reasons.append(f"proxy state not comparable: {proxy}")
        if r_rank is None:
            reasons.append(f"real 4H location not established: {real_loc}")
    elif p_rank == r_rank:
        agreement = "AGREE"
        reasons.append(f"proxy {proxy} matches real {real_loc}")
    elif r_rank > p_rank:
        agreement = "REAL_STRONGER"
        reasons.append(f"real 4H {real_loc} is a better neighborhood than proxy {proxy}")
    else:
        agreement = "REAL_WEAKER"
        reasons.append(f"real 4H {real_loc} is a worse neighborhood than proxy {proxy}")

    # MID_RANGE has no proxy counterpart at all — the proxy cannot express it.
    if real_loc == "MID_RANGE" and p_rank is not None:
        agreement = "REAL_WEAKER" if p_rank > _REAL_RANK["MID_RANGE"] else agreement
        reasons.append("proxy vocabulary has no MID_RANGE state")

    if real_state == "FAILURE" and proxy in ("LOCATION_VALID", "LOCATION_REPAIRING"):
        reasons.append("real 4H shows accepted structural failure")

    return {
        "proxy_state": proxy,
        "real_structural_state": real_state,
        "real_location_state": real_loc,
        "real_readiness": real_ready,
        "agreement": agreement,
        "reasons": reasons,
    }


def render_four_hour_log_line(ticker, real_obj, comparison=None) -> str:
    """One concise diagnostic line. Never logs arrays or constituent bars."""
    real = real_obj if isinstance(real_obj, dict) else {}
    bc = real.get("bar_context") or {}
    cmp_ = comparison if isinstance(comparison, dict) else {}
    return (
        f"FOUR_HOUR_REAL: {ticker} state={real.get('structural_state')} "
        f"location={real.get('operational_location')} "
        f"readiness={real.get('operational_readiness')} "
        f"closed={bc.get('last_closed_4h_time')} "
        f"live={str(bool(bc.get('live_bar_available'))).lower()} "
        f"proxy={cmp_.get('proxy_state', 'UNKNOWN')} "
        f"agreement={cmp_.get('agreement', 'UNKNOWN')}"
    )


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(ticker, tiering_result, enriched, four_hour_bars, config) -> dict:
    obj = default_four_hour_object()

    envelope, bars = _resolve_bars(four_hour_bars)
    obj["bar_context"]["source_interval"] = envelope.get("source_interval")
    obj["bar_context"]["aggregation"] = envelope.get("aggregation")
    obj["bar_context"]["source_request_reused"] = bool(
        envelope.get("source_request_reused", True))

    history = envelope.get("history") or {}
    obj["bar_context"]["history_bars"] = int(history.get("total_bars") or len(bars))
    obj["bar_context"]["sessions_covered"] = int(history.get("sessions_covered") or 0)

    env_status = str(envelope.get("status") or "").upper()
    if env_status in ("ERROR", "EMPTY") and not bars:
        obj["status"] = "INSUFFICIENT" if env_status == "EMPTY" else "ERROR"
        obj["missing_proofs"] = ["no 4H bars available"]
        obj["scanner_sentence"] = "4H operational evidence unavailable."
        return obj

    confirmed = [b for b in bars if b.get("confirmation_eligible")]
    live = bars[-1] if bars and bars[-1].get("is_open") else None

    bc = obj["bar_context"]
    bc["confirmed_history_bars"] = len(confirmed)
    bc["closed_bar_available"] = bool(confirmed)
    bc["live_bar_available"] = live is not None
    bc["current_live_4h_time"] = live.get("time") if live else None
    if confirmed:
        bc["last_closed_4h_time"] = confirmed[-1].get("time")
        bc["last_closed_source_complete"] = bool(confirmed[-1].get("source_complete"))
    bc["latest_bucket_status"] = str(
        envelope.get("latest_bucket_status") or "NONE").upper()
    bc["freshness_status"] = _freshness(bars, envelope)

    price = _current_price(enriched, live, confirmed)
    obj["location"]["price"] = price

    if len(confirmed) < _MIN_CONFIRMED_BARS:
        obj["status"] = "INSUFFICIENT"
        obj["missing_proofs"] = [
            f"insufficient confirmed 4H history: {len(confirmed)} < {_MIN_CONFIRMED_BARS}"
        ]
        obj["scanner_sentence"] = (
            f"4H evidence insufficient — only {len(confirmed)} confirmed operational "
            f"candles available."
        )
        obj["proxy_comparison"] = compare_real_vs_proxy(_proxy_state(tiering_result), obj)
        return obj

    obj["status"] = "DEGRADED" if env_status == "DEGRADED" else "ENABLED"

    # ---- Layer 1: price ladder -------------------------------------------
    atr = _atr(confirmed, _ATR_PERIOD)
    pivots = (_pivots(confirmed, "high", max), _pivots(confirmed, "low", min))
    structure = _build_structure(confirmed, price, pivots)
    obj["structure"] = structure

    # ---- Layer 2: events --------------------------------------------------
    liquidity = _build_liquidity(confirmed, structure, price, low_pivots=pivots[1])
    obj["liquidity"] = liquidity

    displacement = _build_displacement(confirmed, live, atr, structure)
    obj["displacement"] = displacement

    zone = _build_zone_context(confirmed, price)
    obj["zone_context"] = zone

    value = _build_value_context(confirmed, price)
    obj["value_context"] = value

    failure = _build_failure_truth(confirmed, live, structure, price)
    obj["failure_truth"] = failure

    # ---- Layer 3: location ------------------------------------------------
    location = _build_location(confirmed, structure, zone, value, failure, atr, price)
    obj["operational_location"] = location["state"]
    obj["location"] = {**location, "price": price}

    retest = _build_retest_truth(confirmed, live, structure, zone, atr, price, pivots)
    obj["retest_truth"] = retest

    hold = _build_hold_truth(confirmed, live, retest, failure)
    obj["hold_truth"] = hold

    obj["candle_truth"] = _build_candle_truth(confirmed, live, atr)

    volume = _build_volume_participation(bars, confirmed, live)
    obj["volume_participation"] = volume

    invalidation = _build_invalidation_quality(structure, zone, liquidity, price)
    obj["invalidation_quality"] = invalidation

    target = _build_target_path(structure, liquidity, enriched, price, config)
    obj["target_path"] = target

    # ---- Layer 4: narrative ----------------------------------------------
    state, confidence, evidence = _synthesize_state(
        confirmed, structure, displacement, failure, retest, hold, value, atr)
    obj["structural_state"] = state
    obj["state_confidence"] = confidence

    obj["daily_relationship"] = _daily_relationship(enriched, state, location["state"])
    obj["operational_readiness"] = _readiness(state, location["state"], failure,
                                              retest, hold, confidence)

    obj["sequence"] = {
        "structure": structure["break_state"],
        "liquidity": liquidity["sweep_state"],
        "displacement": displacement["state"],
        "retest": retest["state"],
        "hold": hold["state"],
        "invalidation": invalidation["status"],
        "target": target["path_class"],
    }

    obj["hard_failures"], obj["soft_warnings"], obj["missing_proofs"] = _proof_ledger(
        obj, evidence, live, confirmed)
    obj["scanner_sentence"] = _sentence(ticker, obj)
    obj["proxy_comparison"] = compare_real_vs_proxy(_proxy_state(tiering_result), obj)
    return obj


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------

def _resolve_bars(four_hour_bars):
    """Accept the market_data four_hour envelope or a bare bar list."""
    if isinstance(four_hour_bars, dict):
        raw = four_hour_bars.get("bars")
        return four_hour_bars, _normalize_bars(raw)
    return {}, _normalize_bars(four_hour_bars)


def _normalize_bars(raw) -> list:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        o, h, l, c = (_f(item.get("open")), _f(item.get("high")),
                      _f(item.get("low")), _f(item.get("close")))
        if None in (o, h, l, c):
            continue
        bar = dict(item)
        bar["open"], bar["high"], bar["low"], bar["close"] = o, max(h, o, c), min(l, o, c), c
        out.append(bar)
    return out


def _current_price(enriched, live, confirmed):
    """Scan-moment price. The Daily engine's live current_price is preferred —
    it is the same auction instant — then the live 4H close, then the last
    confirmed 4H close."""
    price = _f((enriched or {}).get("current_price"))
    if price is not None:
        return price
    if live is not None:
        return _f(live.get("close"))
    if confirmed:
        return _f(confirmed[-1].get("close"))
    return None


def _proxy_state(tiering_result):
    tfa = (tiering_result or {}).get("timeframe_alignment")
    if not isinstance(tfa, dict):
        return None
    layers = tfa.get("layers")
    if isinstance(layers, dict):
        op = layers.get("operational") or layers.get("4H")
        if isinstance(op, dict):
            return op.get("state")
    op = tfa.get("operational_timeframe")
    if isinstance(op, dict):
        return op.get("state")
    return None


_DEGRADED_LATEST = ("INCOMPLETE", "AMBIGUOUS", "MISSING")


def _freshness(bars, envelope):
    """Trust in the CURRENT evidence — a different fact from the last valid
    confirmation. An older good candle does not make the latest missing
    candle healthy."""
    if not bars:
        return "STALE"
    latest = str(envelope.get("latest_bucket_status") or "").upper()
    if latest in _DEGRADED_LATEST:
        return "DEGRADED"
    if bars[-1].get("is_open"):
        return "LIVE"
    return "CLOSED" if str(envelope.get("status", "")).upper() == "OK" else "DEGRADED"


# ---------------------------------------------------------------------------
# Layer 1 — price ladder
# ---------------------------------------------------------------------------

def _pivots(bars, key, pick):
    """Structural pivots: an extreme that dominates _PIVOT_N bars either side.

    A plateau (several bars sharing the same extreme) is ONE pivot, not
    several — otherwise the ladder read compares a level against itself and
    reports neither higher nor lower.
    """
    vals = [b[key] for b in bars]
    out = []
    for i in range(_PIVOT_N, len(vals) - _PIVOT_N):
        window = vals[i - _PIVOT_N: i + _PIVOT_N + 1]
        if vals[i] == pick(window):
            level = round(vals[i], 4)
            if out and out[-1][1] == level:
                out[-1] = (i, level)          # same plateau — keep the last bar
            else:
                out.append((i, level))
    return out


def _build_structure(confirmed, price, pivots=None) -> dict:
    highs, lows = pivots if pivots is not None else (
        _pivots(confirmed, "high", max), _pivots(confirmed, "low", min))

    range_high = round(max(b["high"] for b in confirmed), 4)
    range_low = round(min(b["low"] for b in confirmed), 4)
    span = range_high - range_low
    position = None
    if price is not None and span > _EPS:
        position = round((price - range_low) / span, 4)

    ladder = _ladder_behavior(highs, lows)

    # Break / reclaim from CONFIRMED closes only. Walk the pivots newest-first
    # and take the most recent structural level the auction actually had to
    # resolve — the newest pivot may have no bars after it at all, which
    # proves nothing either way.
    break_state, break_level = "NONE", None
    for ref_idx, ref_level in reversed(highs):
        after = confirmed[ref_idx + 1:]
        if not after:
            continue
        if max(b["close"] for b in after) > ref_level + _EPS:
            break_state, break_level = "BOS_CONFIRMED", ref_level
            break
        if max(b["high"] for b in after) > ref_level + _EPS:
            break_state, break_level = "WICK_ONLY", ref_level
            break

    reclaim_state, reclaim_level = "NONE", None
    for lo_idx, lo_level in reversed(lows):
        after = confirmed[lo_idx + 1:]
        if not after:
            continue
        if (any(b["close"] < lo_level - _EPS for b in after)
                and confirmed[-1]["close"] > lo_level + _EPS):
            reclaim_state, reclaim_level = "RECLAIM_CONFIRMED", lo_level
            break

    return {
        "swing_highs": [p for _, p in highs][-6:],
        "swing_lows": [p for _, p in lows][-6:],
        "last_swing_high": highs[-1][1] if highs else None,
        "last_swing_low": lows[-1][1] if lows else None,
        "range_high": range_high,
        "range_low": range_low,
        "range_position": position,
        "ladder": ladder,
        "break_state": break_state,
        "break_level": break_level,
        "reclaim_state": reclaim_state,
        "reclaim_level": reclaim_level,
    }


def _ladder_behavior(highs, lows) -> str:
    hh = len(highs) >= 2 and highs[-1][1] > highs[-2][1]
    lh = len(highs) >= 2 and highs[-1][1] < highs[-2][1]
    hl = len(lows) >= 2 and lows[-1][1] > lows[-2][1]
    ll = len(lows) >= 2 and lows[-1][1] < lows[-2][1]
    if hh and hl:
        return "HH_HL"
    if lh and ll:
        return "LH_LL"
    if hh or hl:
        return "MIXED_CONSTRUCTIVE"
    if lh or ll:
        return "MIXED_DAMAGED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Layer 2 — events
# ---------------------------------------------------------------------------

def _build_liquidity(confirmed, structure, price, low_pivots=()) -> dict:
    highs, lows = structure["swing_highs"], structure["swing_lows"]
    above = sorted([p for p in highs if price is not None and p > price])
    below = sorted([p for p in lows if price is not None and p < price], reverse=True)

    # A sweep is a TAKE plus a FAILED sustained acceptance — touching a level
    # is not a sweep, and a level can only be swept AFTER it exists. Scanning
    # bars that predate the pivot would call ordinary prior trade a sweep.
    sweep_state, swept = "NONE", None
    for pivot_idx, level in reversed(list(low_pivots)):
        for i in range(pivot_idx + 1, len(confirmed)):
            b = confirmed[i]
            if b["low"] < level - _EPS and b["close"] > level + _EPS:
                after = confirmed[i + 1:]
                if after and all(x["close"] > level - _EPS for x in after[:2]):
                    sweep_state, swept = "SWEEP_CONFIRMED", round(level, 4)
                    break
        if swept is not None:
            break

    return {
        "buyside_target": above[0] if above else structure["range_high"],
        "sellside_target": below[0] if below else structure["range_low"],
        "prior_swing_high": structure["last_swing_high"],
        "prior_swing_low": structure["last_swing_low"],
        "swept_level": swept,
        "sweep_state": sweep_state,
        "liquidity_threat": below[0] if below else structure["range_low"],
    }


def _build_displacement(confirmed, live, atr, structure) -> dict:
    """Displacement needs body conviction, range expansion and structural
    consequence — never candle colour alone."""
    def read(bar):
        rng = bar["high"] - bar["low"]
        if rng <= _EPS:
            return 0.0, 0.0, None
        body = abs(bar["close"] - bar["open"]) / rng
        close_pos = (bar["close"] - bar["low"]) / rng
        # No ATR-14 -> range expansion is UNPROVABLE, never assumed satisfied.
        ratio = (rng / atr) if atr else None
        return body, close_pos, ratio

    level = structure.get("break_level") or structure.get("last_swing_high")
    state, origin, body_pct, ratio = "NONE", None, None, None

    for i in range(len(confirmed) - 1, max(-1, len(confirmed) - 6), -1):
        bar = confirmed[i]
        body, close_pos, r = read(bar)
        consequence = (
            level is not None and bar["close"] > level + _EPS
        ) or structure["break_state"] == "BOS_CONFIRMED"
        if (body >= _ce._BODY_DOMINANT and close_pos >= _ce._CLOSE_BULL
                and r is not None and r >= _ce._RANGE_ATR_EXPANSION and consequence):
            state = "DISPLACEMENT_CONFIRMED"
            origin = round(bar["low"], 4)
            body_pct, ratio = round(body, 4), round(r, 3)
            break

    if state == "NONE" and live is not None:
        body, close_pos, r = read(live)
        if body >= _ce._BODY_DOMINANT and r is not None and r >= _ce._RANGE_ATR_EXPANSION:
            state = "DISPLACEMENT_BUILDING"
            body_pct, ratio = round(body, 4), round(r, 3)

    if state == "NONE" and structure["break_state"] == "WICK_ONLY":
        state = "FAILED"

    return {"state": state, "origin": origin,
            "body_pct": body_pct, "range_atr_ratio": ratio}


def _build_zone_context(confirmed, price) -> dict:
    """Confirmed 4H FVG only. A live/incomplete candle can never create one,
    and a live excursion through one never destroys it — only a closed
    accepted loss does."""
    fvg = None
    # c1=i, c2=i+1, c3=i+2 — the newest CONFIRMED bar may complete a gap.
    for i in range(len(confirmed) - 2):
        c1_high, c3_low = confirmed[i]["high"], confirmed[i + 2]["low"]
        if c3_low > c1_high + _EPS:
            bot, top = round(c1_high, 4), round(c3_low, 4)
            after = confirmed[i + 3:]
            # Closed acceptance below the base invalidates it.
            if after and min(b["close"] for b in after) < bot - _EPS:
                continue
            fvg = {"bot": bot, "top": top, "mid": round((bot + top) / 2, 4),
                   "origin_index": i}

    state = "NONE"
    if fvg is not None:
        state = "CONFIRMED"
        if price is not None and fvg["bot"] <= price <= fvg["top"]:
            state = "CONFIRMED_PRICE_INSIDE"

    demand = None
    if confirmed:
        lows = sorted(b["low"] for b in confirmed[-8:])
        demand = round(lows[0], 4) if lows else None

    return {"fvg": fvg, "fvg_state": state, "demand_core": demand}


def _build_value_context(confirmed, price) -> dict:
    """4H SMAs from CONFIRMED 4H closes only. Missing history stays missing —
    no shortened period, no other timeframe's SMA wearing a 4H label."""
    closes = [b["close"] for b in confirmed]
    out, unavailable = {}, []
    for period in _SMA_PERIODS:
        if len(closes) >= period:
            out[f"sma{period}"] = round(sum(closes[-period:]) / period, 4)
        else:
            out[f"sma{period}"] = None
            unavailable.append(period)

    available = [out[f"sma{p}"] for p in _SMA_PERIODS if out[f"sma{p}"] is not None]
    if len(available) >= 2 and all(
            available[i] > available[i + 1] for i in range(len(available) - 1)):
        stack = "BULLISH_STACK"
    elif len(available) >= 2 and all(
            available[i] < available[i + 1] for i in range(len(available) - 1)):
        stack = "BEARISH_STACK"
    elif available:
        stack = "MIXED"
    else:
        stack = "UNAVAILABLE"

    price_vs = "UNKNOWN"
    ref = out.get("sma20") or out.get("sma10")
    if price is not None and ref:
        price_vs = "ABOVE_VALUE" if price > ref else "BELOW_VALUE"

    return {**out, "stack": stack, "price_vs_value": price_vs,
            "unavailable": unavailable}


def _build_failure_truth(confirmed, live, structure, price) -> dict:
    """FAILURE_THREAT (live) and ACCEPTED_FAILURE (closed) are different
    things. A live breach never becomes structural failure by itself."""
    core = structure.get("last_swing_low")
    if core is None:
        return {"state": "UNKNOWN", "level": None, "basis": None}

    tail = confirmed[-3:]
    if any(b["close"] < core - _EPS for b in tail):
        return {"state": "ACCEPTED_FAILURE", "level": core,
                "basis": "closed 4H acceptance below defended swing low"}

    if live is not None and _f(live.get("low")) is not None and live["low"] < core - _EPS:
        return {"state": "FAILURE_THREAT", "level": core,
                "basis": "live 4H bar trading below defended swing low"}
    if price is not None and price < core - _EPS:
        return {"state": "FAILURE_THREAT", "level": core,
                "basis": "current price below defended swing low, no closed acceptance"}
    return {"state": "NONE", "level": core, "basis": None}


# ---------------------------------------------------------------------------
# Layer 3 — location, retest, hold
# ---------------------------------------------------------------------------

def _build_location(confirmed, structure, zone, value, failure, atr, price) -> dict:
    if price is None:
        return {"state": "UNKNOWN", "reason": "no scan-moment price",
                "reference_level": None, "distance_atr": None}

    if failure["state"] == "ACCEPTED_FAILURE":
        return {"state": "HOSTILE",
                "reason": "closed 4H acceptance below defended structure",
                "reference_level": failure["level"], "distance_atr": None}

    # Defendable anchors, best first: confirmed FVG, displacement origin,
    # reclaimed shelf, last confirmed swing low.
    anchors = []
    if zone["fvg"]:
        anchors.append(("confirmed 4H FVG", zone["fvg"]["bot"], zone["fvg"]["top"]))
    if structure["reclaim_state"] == "RECLAIM_CONFIRMED":
        anchors.append(("reclaimed 4H shelf", structure["reclaim_level"],
                        structure["reclaim_level"]))
    if structure["last_swing_low"] is not None:
        anchors.append(("confirmed 4H swing low", structure["last_swing_low"],
                        structure["last_swing_low"]))

    for label, lo, hi in anchors:
        if lo - _EPS <= price <= hi + _EPS:
            state = "REPAIRING" if failure["state"] == "FAILURE_THREAT" else "DEFENDABLE"
            return {"state": state, "reason": f"price inside {label}",
                    "reference_level": lo, "distance_atr": 0.0}

    # Nearest anchor by RAW distance — always measurable. The ATR multiple is
    # attached only when ATR-14 genuinely exists; it is never fabricated, and
    # a missing ATR never manufactures EXTENDED or proximity.
    nearest = None
    for label, lo, hi in anchors:
        dist = min(abs(price - lo), abs(price - hi))
        if nearest is None or dist < nearest[3]:
            d_atr = round(dist / atr, 2) if atr else None
            nearest = (label, d_atr, lo, dist)

    if failure["state"] == "FAILURE_THREAT":
        return {"state": "REPAIRING",
                "reason": "live breach of defended structure without closed acceptance",
                "reference_level": failure["level"],
                "distance_atr": nearest[1] if nearest else None}

    if nearest and nearest[1] is not None and nearest[1] <= _RETEST_PROXIMITY_ATR:
        return {"state": "DEFENDABLE", "reason": f"price at {nearest[0]}",
                "reference_level": nearest[2], "distance_atr": nearest[1]}

    position = structure.get("range_position")
    if position is not None and abs(position - 0.5) <= _MID_BAND_HALF:
        return {"state": "MID_RANGE",
                "reason": "price in the centre of the confirmed 4H dealing range "
                          "with no structural reason to act",
                "reference_level": None, "distance_atr": nearest[1] if nearest else None}

    if nearest and nearest[1] is not None and nearest[1] >= _EXTENDED_ATR:
        return {"state": "EXTENDED",
                "reason": f"{nearest[1]} ATR above the nearest defendable 4H structure",
                "reference_level": nearest[2], "distance_atr": nearest[1]}

    if position is not None and position >= 1 - _EDGE_BAND:
        return {"state": "EXTENDED", "reason": "price at the upper edge of the 4H range",
                "reference_level": structure["range_high"],
                "distance_atr": nearest[1] if nearest else None}

    return {"state": "MID_RANGE", "reason": "no defendable 4H structure at price",
            "reference_level": None, "distance_atr": nearest[1] if nearest else None}


def _level_index(pivots, level):
    for idx, lvl in pivots:
        if level is not None and abs(lvl - level) <= _EPS:
            return idx
    return None


def _retest_anchor(structure, zone, pivots):
    """(label, low, high, established_index).

    `established_index` is the bar at which the anchor came into existence. A
    retest can only happen AFTER that — the candles that CREATE a zone are its
    origin, not a revisit of it.
    """
    highs, lows = pivots
    if zone["fvg"]:
        return ("CONFIRMED_FVG", zone["fvg"]["bot"], zone["fvg"]["top"],
                zone["fvg"]["origin_index"] + 3)
    if structure["reclaim_state"] == "RECLAIM_CONFIRMED":
        idx = _level_index(lows, structure["reclaim_level"])
        return ("RECLAIMED_SHELF", structure["reclaim_level"],
                structure["reclaim_level"], (idx + 1) if idx is not None else 0)
    if structure["break_state"] == "BOS_CONFIRMED":
        idx = _level_index(highs, structure["break_level"])
        return ("BROKEN_SHELF", structure["break_level"], structure["break_level"],
                (idx + 1) if idx is not None else 0)
    if structure["last_swing_low"] is not None:
        idx = _level_index(lows, structure["last_swing_low"])
        return ("CONFIRMED_SWING_LOW", structure["last_swing_low"],
                structure["last_swing_low"], (idx + 1) if idx is not None else 0)
    return None, None, None, 0


def _build_retest_truth(confirmed, live, structure, zone, atr, price, pivots) -> dict:
    """A retest must revisit REAL structure. A pullback into empty space is
    not a retest, and CONFIRMED requires completed evidence."""
    anchor, lo, hi, since = _retest_anchor(structure, zone, pivots)
    if anchor is None or price is None:
        return {"state": "UNKNOWN", "anchor": None, "anchor_level": None,
                "distance_atr": None}

    dist = 0.0 if lo - _EPS <= price <= hi + _EPS else min(abs(price - lo), abs(price - hi))
    d_atr = round(dist / atr, 2) if atr else None

    # Only bars AFTER the anchor was established can retest it.
    since_bars = confirmed[max(0, since):]
    closed_in = [b for b in since_bars[-4:]
                 if b["low"] <= hi + _EPS and b["high"] >= lo - _EPS]
    closed_defended = [
        b for b in closed_in
        if b["close"] >= lo - _EPS and b["close"] > b["open"]
    ]
    closed_lost = any(b["close"] < lo - _EPS for b in since_bars[-3:])

    if closed_lost:
        state = "FAILED"
    elif closed_defended:
        rng = closed_defended[-1]["high"] - closed_defended[-1]["low"]
        body = abs(closed_defended[-1]["close"] - closed_defended[-1]["open"]) / rng if rng > _EPS else 0.0
        state = "CONFIRMED" if body >= _ce._BODY_DOMINANT else "CORE_VALID"
    elif closed_in:
        state = "CORE_VALID"
    elif lo - _EPS <= price <= hi + _EPS or (live is not None and
                                             live.get("low") is not None and
                                             live["low"] <= hi + _EPS and
                                             live["high"] >= lo - _EPS):
        state = "IN_PROGRESS"
    elif d_atr is not None and d_atr <= _RETEST_PROXIMITY_ATR:
        state = "APPROACHING"
    else:
        state = "NOT_REACHED"

    return {"state": state, "anchor": anchor,
            "anchor_level": round(lo, 4) if lo is not None else None,
            "distance_atr": d_atr}


def _build_hold_truth(confirmed, live, retest, failure) -> dict:
    """A wick is not a hold. One green candle is not a hold. Live defense is
    FORMING."""
    if failure["state"] == "ACCEPTED_FAILURE":
        return {"state": "FAILED", "basis": "closed acceptance through core"}
    if retest["state"] in ("NOT_REACHED", "UNKNOWN"):
        return {"state": "NONE", "basis": "no valid retest to hold"}
    if retest["state"] == "FAILED":
        return {"state": "FAILED", "basis": "closed loss of the retest anchor"}

    level = retest.get("anchor_level")
    if retest["state"] in ("CORE_VALID", "CONFIRMED") and level is not None:
        for bar in reversed(confirmed[-3:]):
            rng = bar["high"] - bar["low"]
            if rng <= _EPS:
                continue
            body = abs(bar["close"] - bar["open"]) / rng
            close_pos = (bar["close"] - bar["low"]) / rng
            if (bar["close"] > level + _EPS and body >= _ce._BODY_DOMINANT
                    and close_pos >= _ce._CLOSE_BULL):
                return {"state": "CONFIRMED",
                        "basis": "closed 4H body defense with close control at the anchor"}
        return {"state": "FORMING", "basis": "anchor engaged, no closed body defense yet"}

    if retest["state"] in ("IN_PROGRESS", "APPROACHING"):
        return {"state": "FORMING", "basis": "live engagement with the anchor"}
    return {"state": "NONE", "basis": None}


def _build_candle_truth(confirmed, live, atr) -> dict:
    bar = live if live is not None else (confirmed[-1] if confirmed else None)
    if bar is None:
        return {"status": "UNKNOWN", "body_pct": None, "close_position_pct": None,
                "wick_read": "UNKNOWN", "close_quality": "UNKNOWN"}
    rng = bar["high"] - bar["low"]
    if rng <= _EPS:
        return {"status": "OPEN" if live is not None else "CLOSED", "body_pct": 0.0,
                "close_position_pct": 0.5, "wick_read": "NO_MAJOR_WICK",
                "close_quality": "UNRESOLVED"}
    body = abs(bar["close"] - bar["open"]) / rng
    close_pos = (bar["close"] - bar["low"]) / rng
    upper = (bar["high"] - max(bar["open"], bar["close"])) / rng
    lower = (min(bar["open"], bar["close"]) - bar["low"]) / rng

    if upper >= _ce._WICK_MAJOR and lower >= _ce._WICK_MAJOR:
        wick = "DOUBLE_WICK_UNRESOLVED"
    elif lower >= _ce._WICK_MAJOR:
        wick = "LOWER_WICK_DEMAND_DEFENSE"
    elif upper >= _ce._WICK_MAJOR:
        wick = "UPPER_WICK_SUPPLY_REJECTION"
    else:
        wick = "NO_MAJOR_WICK"

    if body <= _ce._BODY_DOJI:
        quality = "WEAK_CLOSE"
    elif close_pos >= _ce._CLOSE_BULL and bar["close"] > bar["open"]:
        quality = "STRONG_BULLISH_CLOSE"
    elif close_pos <= _ce._CLOSE_BEAR and bar["close"] < bar["open"]:
        quality = "STRONG_BEARISH_CLOSE"
    else:
        quality = "MID_RANGE_CLOSE"

    return {"status": "OPEN" if live is not None else "CLOSED",
            "body_pct": round(body, 4), "close_position_pct": round(close_pos, 4),
            "wick_read": wick, "close_quality": quality}


# ---------------------------------------------------------------------------
# Volume, invalidation, path
# ---------------------------------------------------------------------------

def _build_volume_participation(bars, confirmed, live) -> dict:
    """Slot-aware. A 150-minute AFTERNOON_CLOSE bucket is never compared
    against 240-minute MORNING_4H buckets — that would call every afternoon a
    dry-up by construction."""
    subject = confirmed[-1] if confirmed else None
    provisional = False
    if live is not None and live.get("volume") is not None:
        provisional = True

    if subject is None or subject.get("volume") is None:
        return {"volume_ratio": None, "volume_behavior": "UNKNOWN",
                "volume_comparison_basis": "SAME_SESSION_SLOT",
                "slot": subject.get("bucket_slot") if subject else None,
                "baseline_samples": 0, "live_bucket_provisional": provisional}

    slot = subject.get("bucket_slot")
    baseline = [b["volume"] for b in confirmed[:-1]
                if b.get("bucket_slot") == slot and b.get("volume") is not None]
    if len(baseline) < 3:
        return {"volume_ratio": None, "volume_behavior": "UNKNOWN",
                "volume_comparison_basis": "SAME_SESSION_SLOT", "slot": slot,
                "baseline_samples": len(baseline), "live_bucket_provisional": provisional}

    avg = sum(baseline) / len(baseline)
    if avg <= 0:
        return {"volume_ratio": None, "volume_behavior": "UNKNOWN",
                "volume_comparison_basis": "SAME_SESSION_SLOT", "slot": slot,
                "baseline_samples": len(baseline), "live_bucket_provisional": provisional}

    ratio = round(subject["volume"] / avg, 3)
    if ratio >= _ce._VOL_EXPANSION:
        behavior = "EXPANSION"
    elif ratio <= _ce._VOL_DRYUP:
        behavior = "DRYUP"
    else:
        behavior = "NEUTRAL"
    return {"volume_ratio": ratio, "volume_behavior": behavior,
            "volume_comparison_basis": "SAME_SESSION_SLOT", "slot": slot,
            "baseline_samples": len(baseline), "live_bucket_provisional": provisional}


def _build_invalidation_quality(structure, zone, liquidity, price) -> dict:
    """Shadow assessment only — production invalidation is never overwritten,
    and no level is invented to flatter R:R."""
    candidates = []
    if liquidity.get("swept_level") is not None:
        candidates.append((liquidity["swept_level"], "4H sweep low"))
    if zone.get("fvg"):
        candidates.append((zone["fvg"]["bot"], "confirmed 4H FVG base"))
    if structure.get("reclaim_state") == "RECLAIM_CONFIRMED":
        candidates.append((structure["reclaim_level"], "reclaimed 4H shelf"))
    if structure.get("last_swing_low") is not None:
        candidates.append((structure["last_swing_low"], "defended 4H swing low"))

    below = [(lvl, basis) for lvl, basis in candidates
             if price is not None and lvl < price - _EPS]
    if not below:
        return {"status": "UNCLEAR", "level": None,
                "basis": "no confirmed 4H structure below price", "risk_distance_pct": None}

    level, basis = max(below, key=lambda x: x[0])
    risk_pct = round((price - level) / price * 100, 3) if price else None
    status = "CLEAR" if len(below) >= 2 else "PARTIAL"
    return {"status": status, "level": round(level, 4), "basis": basis,
            "risk_distance_pct": risk_pct}


def _build_target_path(structure, liquidity, enriched, price, config) -> dict:
    """Shadow path assessment. Production targets and estimated_rr untouched.

    A next objective must be AHEAD of price. Candidates are the confirmed 4H
    swing highs above price, the confirmed 4H range high above price, and any
    numeric confirmed Daily target above price; the NEAREST wins, so a nearer
    4H objective beats a distant Daily one and a Daily target is used only
    when no 4H objective sits above price.

    "No overhead objective" is a different fact from "old objective behind
    price" — the former is an honest OPEN path with no target, the latter is
    false target labeling and is never emitted.
    """
    block_pct = float(
        (config or {}).get("prefilter", {}).get("thresholds", {})
        .get("overhead_block_distance_pct", 3)
    )

    if price is None or price <= 0:
        return {"path_class": "UNKNOWN", "next_objective": None,
                "objective_basis": None, "distance_pct": None}

    candidates = []
    for level in (structure.get("swing_highs") or []):
        lvl = _f(level)
        if lvl is not None and lvl > price + _EPS:
            candidates.append((lvl, "next confirmed 4H swing high"))
    range_high = _f(structure.get("range_high"))
    if range_high is not None and range_high > price + _EPS:
        candidates.append((range_high, "confirmed 4H range high"))
    for target in ((enriched or {}).get("targets") or []):
        if not isinstance(target, dict):
            continue
        lvl = _f(target.get("level"))
        if lvl is not None and lvl > price + _EPS:
            candidates.append((lvl, "confirmed Daily objective"))

    if not candidates:
        # Nothing confirmed stands above price. That is a legitimately open
        # structural path — with no target, not a stale one behind price.
        return {"path_class": "OPEN", "next_objective": None,
                "objective_basis": "NO_CONFIRMED_OVERHEAD_OBJECTIVE",
                "distance_pct": None}

    objective, basis = min(candidates, key=lambda c: c[0])
    dist_pct = round((objective - price) / price * 100, 3)
    if dist_pct <= block_pct:
        path = "BLOCKED"
    elif dist_pct <= block_pct * _PATH_COMPRESSED_MULT:
        path = "COMPRESSED"
    elif dist_pct <= block_pct * 2.5:
        path = "MODERATE"
    else:
        path = "OPEN"
    return {"path_class": path, "next_objective": round(objective, 4),
            "objective_basis": basis, "distance_pct": dist_pct}


# ---------------------------------------------------------------------------
# Layer 4 — narrative synthesis
# ---------------------------------------------------------------------------

def _mean_range(bars):
    return sum(b["high"] - b["low"] for b in bars) / len(bars) if bars else 0.0


def _mean_overlap(bars):
    if len(bars) < 2:
        return 0.0
    vals = []
    for prev, cur in zip(bars, bars[1:]):
        rng = max(cur["high"], prev["high"]) - min(cur["low"], prev["low"])
        if rng <= _EPS:
            continue
        overlap = min(cur["high"], prev["high"]) - max(cur["low"], prev["low"])
        vals.append(max(0.0, overlap) / rng)
    return sum(vals) / len(vals) if vals else 0.0


def _synthesize_state(confirmed, structure, displacement, failure, retest, hold,
                      value, atr):
    """Precedence: confirmed FAILURE > REPAIR > EXPANSION > COMPRESSION >
    CONTINUATION > TRANSITION > UNKNOWN — but the evidence that produced the
    state is always exposed so the verdict stays auditable."""
    evidence = []
    recent, prior = confirmed[-6:], confirmed[-12:-6]
    recent_range, prior_range = _mean_range(recent), _mean_range(prior)
    overlap = _mean_overlap(recent)
    contracting = bool(prior_range > _EPS and
                       recent_range / prior_range <= _COMPRESSION_RATIO)

    if failure["state"] == "ACCEPTED_FAILURE":
        evidence.append(failure["basis"])
        return "FAILURE", "HIGH", evidence

    if (structure["reclaim_state"] == "RECLAIM_CONFIRMED"
            or (failure["state"] == "FAILURE_THREAT" and hold["state"] in ("FORMING", "CONFIRMED"))):
        evidence.append(f"reclaim_state={structure['reclaim_state']}, hold={hold['state']}")
        confidence = "HIGH" if structure["reclaim_state"] == "RECLAIM_CONFIRMED" else "MEDIUM"
        return "REPAIR", confidence, evidence

    if (displacement["state"] == "DISPLACEMENT_CONFIRMED"
            and structure["break_state"] == "BOS_CONFIRMED"):
        evidence.append("confirmed displacement with confirmed structural break")
        return "EXPANSION", "HIGH", evidence

    if contracting and overlap >= _OVERLAP_HIGH:
        evidence.append(
            f"recent/prior mean range {recent_range / prior_range:.2f} "
            f"<= {_COMPRESSION_RATIO}, mean overlap {overlap:.2f} >= {_OVERLAP_HIGH}")
        return "COMPRESSION", "MEDIUM", evidence

    if structure["ladder"] == "HH_HL" and failure["state"] in ("NONE", "UNKNOWN"):
        evidence.append("HH/HL ladder intact with no accepted local failure")
        confidence = "HIGH" if value["stack"] == "BULLISH_STACK" else "MEDIUM"
        return "CONTINUATION", confidence, evidence

    evidence.append(
        f"ladder={structure['ladder']}, break={structure['break_state']}, "
        f"failure={failure['state']} — no completed structural proof")
    return "TRANSITION", "LOW", evidence


def _daily_relationship(enriched, state, location) -> str:
    daily_confirmed = (enriched or {}).get("structure_confirmed")
    if daily_confirmed is None:
        return "UNKNOWN"
    if state == "FAILURE" or location == "HOSTILE":
        return "4H_CONFLICTS_WITH_CAMPAIGN"
    if state == "REPAIR":
        return "4H_REPAIRS_CAMPAIGN"
    return "4H_SUPPORTS_CAMPAIGN"


def _readiness(state, location, failure, retest, hold, confidence) -> str:
    if state == "FAILURE" or location == "HOSTILE":
        return "HOSTILE"
    if location == "EXTENDED":
        return "EXTENDED"
    if state == "REPAIR" or location == "REPAIRING":
        return "REPAIRING"
    if confidence == "INSUFFICIENT":
        return "INSUFFICIENT"
    if location == "DEFENDABLE" and hold["state"] in ("CONFIRMED", "FORMING") \
            and retest["state"] in ("CORE_VALID", "CONFIRMED", "IN_PROGRESS"):
        return "READY_FOR_1H_PROOF"
    return "FORMING"


def _proof_ledger(obj, evidence, live, confirmed):
    hard, soft, missing = [], [], []
    if obj["failure_truth"]["state"] == "ACCEPTED_FAILURE":
        hard.append("accepted 4H failure through defended structure")
    if obj["operational_location"] == "HOSTILE":
        hard.append("hostile 4H operational location")

    if live is not None:
        soft.append("current 4H bucket is still forming — live evidence is provisional")
    if not obj["bar_context"]["last_closed_source_complete"]:
        soft.append("last closed 4H bucket had incomplete source coverage")
    latest = obj["bar_context"].get("latest_bucket_status")
    if latest in _DEGRADED_LATEST:
        soft.append(f"latest expected 4H bucket is {latest} — current evidence "
                    f"is degraded even though older confirmations stand")
        missing.append(f"latest expected 4H bucket {latest}")
    soft.extend(evidence)

    if obj["displacement"]["state"] in ("NONE", "BUILDING", "DISPLACEMENT_BUILDING"):
        missing.append("no confirmed 4H displacement")
    if obj["retest_truth"]["state"] not in ("CONFIRMED", "CORE_VALID"):
        missing.append("no confirmed 4H retest")
    if obj["hold_truth"]["state"] != "CONFIRMED":
        missing.append("no confirmed 4H hold")
    if obj["invalidation_quality"]["status"] == "UNCLEAR":
        missing.append("no clear 4H structural invalidation")
    for period in obj["value_context"]["unavailable"]:
        missing.append(f"4H SMA{period} unavailable — insufficient confirmed history")
    return hard, soft, missing


def _sentence(ticker, obj) -> str:
    bc = obj["bar_context"]
    live = "forming 4H bucket open" if bc["live_bar_available"] else "no forming 4H bucket"
    return (
        f"{ticker} 4H {obj['structural_state'].lower()} — location "
        f"{obj['operational_location'].lower()}, retest {obj['retest_truth']['state'].lower()}, "
        f"hold {obj['hold_truth']['state'].lower()}; {live}; readiness "
        f"{obj['operational_readiness'].lower()} "
        f"({bc['confirmed_history_bars']} confirmed 4H bars)."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _atr(bars, period):
    """ATR over `period` true ranges, matching indicators.compute_atr exactly.

    The canonical implementation builds a true-range series the same length as
    the bar series — the first bar's TR is its own high-low, because there is
    no prior close — and then takes rolling(period, min_periods=period). So
    ATR-14 needs 14 BARS, and fewer than that returns None.

    Insufficient history does not authorize changing the feature definition:
    a shortened ATR is never returned wearing the ATR-14 label.
    """
    if not bars or period <= 0:
        return None
    trs = [bars[0]["high"] - bars[0]["low"]]
    for prev, cur in zip(bars, bars[1:]):
        trs.append(max(cur["high"] - cur["low"],
                       abs(cur["high"] - prev["close"]),
                       abs(cur["low"] - prev["close"])))
    if len(trs) < period:
        return None
    return round(sum(trs[-period:]) / period, 4)


def _f(val):
    """Finite float or None. NaN and +/-inf are malformed, not values."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f

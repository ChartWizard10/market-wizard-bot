"""Phase 14I — Monthly / Weekly Structural Memory Engine.

A dedicated higher-timeframe structural-context organ. It resamples existing
daily OHLCV into completed weekly and monthly bars and answers: where price came
from over months, whether it is interacting with sovereign HTF value, whether a
bounce / continuation / repair / supply-rejection is in play, whether dynamic
(SMA) support is defended, and whether the lower-timeframe setup is part of a
real campaign-level sequence.

Doctrine (permanent):
  - Monthly defines bias. Weekly defines campaign. Daily grants swing
    permission. 4H defines operational location. 1H proves the trigger.
  - Evidence-first: NEVER promotes SNIPE_IT, never loosens gates, never mutates
    final_tier / capital_action / routing / suppression / dedup. It records
    supporting/weakening/blocking context for later audit only.
  - Pure, re-entrant, never raises. Degrades honestly on insufficient/malformed
    data. A current (incomplete) weekly/monthly candle is developing context
    only — never a confirmed HTF close.

No new indicators (no RSI/MACD/Bollinger/Stochastic, no SMA10 *daily* dependency).
SMAs here are computed on completed weekly/monthly closes for HTF value only.
"""

from datetime import date, datetime

# ---------------------------------------------------------------------------
# Enums (canonical — emitting an unlisted value is a test failure)
# ---------------------------------------------------------------------------

ENGINE_VERSION = "14I"

DATA_STATUSES = {
    "OK", "DEGRADED_INSUFFICIENT_HISTORY", "DEGRADED_MISSING_VOLUME",
    "UNAVAILABLE", "ERROR",
}
BIAS_STATES = {"BULLISH", "BEARISH", "REPAIR", "TRANSITION", "RANGE", "UNKNOWN"}
TREND_STATES = {
    "ACCUMULATING", "FRESH_EXPANSION", "MATURE_CONTINUATION", "REPAIR",
    "TRANSITION", "FAILURE", "UNKNOWN",
}
STACK_STATES = {
    "CLEAN_EXPANSION", "COMPRESSED", "WARPED", "TRANSITIONAL", "INVERTED", "UNKNOWN",
}
PRICE_VS = {"ABOVE", "BELOW", "TESTING", "UNKNOWN"}
DYNAMIC_SUPPORT = {"DEFENDED", "LOST", "RECLAIMING", "OVEREXTENDED", "NEUTRAL", "UNKNOWN"}
CAMPAIGN_STATES = {
    "HTF_BOUNCE", "HTF_CONTINUATION", "HTF_RECLAIM", "HTF_REPAIR",
    "HTF_SUPPLY_REJECTION", "HTF_MID_RANGE", "HTF_FAILURE", "UNKNOWN",
}
CAMPAIGN_LOCATIONS = {
    "AT_MONTHLY_DEMAND", "AT_WEEKLY_DEMAND", "AT_HTF_SUPPORT", "AT_HTF_FLIP_ZONE",
    "ABOVE_HTF_RECLAIM", "INTO_HTF_SUPPLY", "MID_RANGE", "EXTENDED_ABOVE_VALUE",
    "BELOW_HTF_FAILURE", "UNKNOWN",
}
LOCATION_QUALITY = {"SOVEREIGN", "FUNCTIONAL", "INFORMATIONAL", "HOSTILE", "NEUTRAL", "UNKNOWN"}
PATH_STATES = {"OPEN", "PARTIALLY_CONGESTED", "BLOCKED_BY_SUPPLY", "UNKNOWN"}
CAME_FROM = {
    "MAJOR_SUPPORT", "MAJOR_SUPPLY", "MONTHLY_DEMAND", "WEEKLY_DEMAND",
    "MID_RANGE", "BREAKDOWN", "UNKNOWN",
}
ATTEMPTS = {"BOUNCE", "RECLAIM", "BREAK_OF_STRUCTURE", "RETEST", "HOLD", "FAILURE", "UNKNOWN"}
CURRENT_READS = {"SUPPORTED_CONTINUATION", "REPAIRING", "FORMING", "HOSTILE", "FAILED", "UNKNOWN"}
GRADES = {"A", "B", "C", "D", "F", "UNKNOWN"}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_NEAR_PCT = 3.0          # within this % of a level => "at"/near it
_TESTING_PCT = 1.8       # within this % of an SMA => TESTING
_EXTENDED_PCT = 12.0     # > this % above value => overextended
_SUPPLY_NEAR_PCT = 3.0   # resistance within this % overhead => into supply
_WEEKLY_PIVOT_L = 2
_WEEKLY_PIVOT_R = 2
_MONTHLY_PIVOT_L = 2
_MONTHLY_PIVOT_R = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_higher_timeframe_context(
    ticker, tiering_result=None, enriched_data=None, daily_bars=None, config=None
) -> dict:
    """Build the higher-timeframe structural context. NEVER raises. Mutates nothing."""
    try:
        return _build(
            ticker, tiering_result or {}, enriched_data or {}, daily_bars, config or {}
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return error_htf_object(str(exc))


def default_htf_object() -> dict:
    return {
        "engine_version": ENGINE_VERSION,
        "enabled": True,
        "data_status": "UNAVAILABLE",
        "diagnostic_sentence": None,
        "lookback": {
            "requested_months": 60,
            "daily_bars_used": 0,
            "weekly_bars_used": 0,
            "monthly_bars_used": 0,
            "first_bar_date": None,
            "last_completed_weekly_bar_date": None,
            "last_completed_monthly_bar_date": None,
            "current_weekly_bar_is_developing": False,
            "current_monthly_bar_is_developing": False,
        },
        "monthly": _blank_tf_block(),
        "weekly": _blank_tf_block(),
        "campaign_location": {
            "label": "UNKNOWN", "quality": "UNKNOWN",
            "distance_to_nearest_support_pct": None,
            "distance_to_nearest_resistance_pct": None,
            "path_state": "UNKNOWN",
        },
        "htf_sequence": {
            "came_from": "UNKNOWN", "attempt": "UNKNOWN", "current_read": "UNKNOWN",
            "bos_context": {
                "weekly_bos_detected": False, "monthly_bos_detected": False,
                "bos_level": None, "bos_quality": "UNKNOWN",
            },
        },
        "setup_relationship": {
            "supports_long_setup": False, "weakens_long_setup": False,
            "blocks_snipe_contextually": False, "context_grade": "UNKNOWN",
            "context_score": None, "promotion_support": [], "missing_htf_proof": [],
            "blocking_reasons": [], "invalidation_conditions": [],
        },
    }


def _blank_tf_block() -> dict:
    return {
        "bias_state": "UNKNOWN",   # monthly only; harmless extra on weekly default
        "campaign_state": "UNKNOWN", # weekly only; harmless extra on monthly default
        "trend_state": "UNKNOWN",
        "stack_state": "UNKNOWN",
        "sma_relationship": {
            "price_vs_10": "UNKNOWN", "price_vs_20": "UNKNOWN",
            "price_vs_50": "UNKNOWN", "price_vs_200": "UNKNOWN",
            "dynamic_support_state": "UNKNOWN",
        },
        "nearest_zone": None,
        "key_levels": [],
        "support_resistance_map": [],
        "context_read": None,
    }


def degraded_htf_object(status: str, reason: str) -> dict:
    obj = default_htf_object()
    obj["data_status"] = status if status in DATA_STATUSES else "UNAVAILABLE"
    obj["diagnostic_sentence"] = f"HTF context: unavailable — {reason}."
    obj["setup_relationship"]["blocking_reasons"] = []
    obj["setup_relationship"]["missing_htf_proof"] = [reason]
    return obj


def error_htf_object(error: str) -> dict:
    obj = default_htf_object()
    obj["data_status"] = "ERROR"
    obj["diagnostic_sentence"] = "HTF context: unavailable — engine error."
    obj["setup_relationship"]["missing_htf_proof"] = [f"htf_context_error: {error}"]
    return obj


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def _build(ticker, tiering_result, enriched, daily_bars, config) -> dict:
    cfg = config.get("higher_timeframe_context", {}) if isinstance(config, dict) else {}
    if cfg.get("enabled", True) is False:
        obj = default_htf_object()
        obj["enabled"] = False
        obj["data_status"] = "UNAVAILABLE"
        obj["diagnostic_sentence"] = None
        return obj

    requested_months = int(cfg.get("lookback_months", 60) or 60)
    min_weekly = int(cfg.get("min_weekly_bars", 52) or 52)
    min_monthly = int(cfg.get("min_monthly_bars", 12) or 12)

    # Resolve daily bars (explicit arg first, then enriched fallback).
    raw = daily_bars
    if raw is None:
        raw = enriched.get("daily_bars") if isinstance(enriched, dict) else None

    bars, missing_volume = _normalize_daily_bars(raw)
    if not bars:
        return degraded_htf_object("UNAVAILABLE", "no usable daily bars")
    if len(bars) < 40:
        obj = degraded_htf_object("DEGRADED_INSUFFICIENT_HISTORY", "insufficient daily history")
        obj["lookback"]["daily_bars_used"] = len(bars)
        obj["lookback"]["first_bar_date"] = _iso(bars[0]["date"])
        return obj

    # Resample into completed weekly / monthly bars (current period = developing).
    w_completed, w_dev = _resample(bars, "weekly")
    m_completed, m_dev = _resample(bars, "monthly")

    obj = default_htf_object()
    obj["lookback"] = {
        "requested_months": requested_months,
        "daily_bars_used": len(bars),
        "weekly_bars_used": len(w_completed),
        "monthly_bars_used": len(m_completed),
        "first_bar_date": _iso(bars[0]["date"]),
        "last_completed_weekly_bar_date": _iso(w_completed[-1]["date"]) if w_completed else None,
        "last_completed_monthly_bar_date": _iso(m_completed[-1]["date"]) if m_completed else None,
        "current_weekly_bar_is_developing": w_dev is not None,
        "current_monthly_bar_is_developing": m_dev is not None,
    }

    if len(w_completed) < min_weekly or len(m_completed) < min_monthly:
        obj["data_status"] = "DEGRADED_INSUFFICIENT_HISTORY"
    elif missing_volume:
        obj["data_status"] = "DEGRADED_MISSING_VOLUME"
    else:
        obj["data_status"] = "OK"

    price = bars[-1]["close"]   # current (developing) price anchor

    obj["weekly"] = _build_tf_block(w_completed, price, "weekly", _WEEKLY_PIVOT_L, _WEEKLY_PIVOT_R)
    obj["monthly"] = _build_tf_block(m_completed, price, "monthly", _MONTHLY_PIVOT_L, _MONTHLY_PIVOT_R)

    # Weekly carries campaign_state; monthly carries bias_state.
    obj["monthly"]["bias_state"] = _monthly_bias(m_completed, price, obj["monthly"])
    obj["monthly"].pop("campaign_state", None)
    obj["weekly"]["campaign_state"] = _weekly_campaign(w_completed, m_completed, price, obj["weekly"], obj["monthly"])
    obj["weekly"].pop("bias_state", None)

    # Campaign location + sequence + relationship/scoring.
    obj["campaign_location"] = _campaign_location(price, obj["weekly"], obj["monthly"])
    obj["htf_sequence"] = _htf_sequence(w_completed, m_completed, price, obj["weekly"], obj["monthly"])
    obj["setup_relationship"] = _setup_relationship(
        tiering_result, obj, price
    )

    obj["diagnostic_sentence"] = _diagnostic_sentence(obj)
    return obj


# ---------------------------------------------------------------------------
# Daily-bar normalization + df conversion
# ---------------------------------------------------------------------------

def daily_bars_from_df(df) -> "list | None":
    """Convert a pandas daily OHLCV DataFrame (DatetimeIndex) into a list of bar
    dicts oldest->newest. Returns None when df is missing or not convertible.

    Pandas is only touched here; the engine core works on plain dicts.
    """
    if df is None:
        return None
    try:
        cols = {c.lower(): c for c in df.columns}
        out = []
        for idx, row in df.iterrows():
            try:
                d = idx.date() if hasattr(idx, "date") else _parse_date(idx)
            except Exception:
                d = None
            bar = {
                "date": d,
                "open": _f(row[cols["open"]]) if "open" in cols else None,
                "high": _f(row[cols["high"]]) if "high" in cols else None,
                "low": _f(row[cols["low"]]) if "low" in cols else None,
                "close": _f(row[cols["close"]]) if "close" in cols else None,
                "volume": _f(row[cols["volume"]]) if "volume" in cols else None,
            }
            out.append(bar)
        return out
    except Exception:
        return None


def _normalize_daily_bars(raw):
    """Return (clean_bars sorted ascending, missing_volume_flag)."""
    if not isinstance(raw, (list, tuple)) or not raw:
        return [], False
    out = []
    missing_volume = False
    for item in raw:
        if not isinstance(item, dict):
            continue
        o = _f(item.get("open"))
        h = _f(item.get("high"))
        l = _f(item.get("low"))
        c = _f(item.get("close"))
        if None in (o, h, l, c):
            continue
        d = _coerce_date(item.get("date") or item.get("time") or item.get("timestamp"))
        if d is None:
            continue
        v = _f(item.get("volume"))
        if v is None:
            missing_volume = True
        hi = max(h, o, c)
        lo = min(l, o, c)
        out.append({"date": d, "open": o, "high": hi, "low": lo, "close": c, "volume": v})
    out.sort(key=lambda b: b["date"])
    return out, missing_volume


# ---------------------------------------------------------------------------
# Resampling (calendar week / month; current period is developing)
# ---------------------------------------------------------------------------

def _resample(bars, period):
    """Group daily bars into period bars. Returns (completed, developing_or_None).

    The most recent period group is always treated as developing (not a confirmed
    HTF close), per doctrine. completed = all groups except the latest.
    """
    groups = {}
    order = []
    for b in bars:
        key = _period_key(b["date"], period)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(b)

    agg = []
    for key in order:
        g = groups[key]
        agg.append({
            "date": g[-1]["date"],
            "open": g[0]["open"],
            "high": max(x["high"] for x in g),
            "low": min(x["low"] for x in g),
            "close": g[-1]["close"],
            "volume": _sum_volume(g),
            "n": len(g),
        })
    if not agg:
        return [], None
    developing = agg[-1]
    completed = agg[:-1]
    return completed, developing


def _period_key(d, period):
    if period == "weekly":
        iso = d.isocalendar()
        return (iso[0], iso[1])
    return (d.year, d.month)


def _sum_volume(group):
    vols = [x["volume"] for x in group if x["volume"] is not None]
    if not vols:
        return None
    return sum(vols)


# ---------------------------------------------------------------------------
# SMA + slope
# ---------------------------------------------------------------------------

def _sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / float(period)


def _sma_series(closes, period):
    if len(closes) < period:
        return []
    return [sum(closes[i - period + 1:i + 1]) / float(period) for i in range(period - 1, len(closes))]


def _slope_up(closes, period, back=3):
    """True/False/None — is the period SMA rising over `back` steps?"""
    series = _sma_series(closes, period)
    if len(series) < back + 1:
        return None
    return series[-1] > series[-1 - back]


# ---------------------------------------------------------------------------
# Per-timeframe block (SMAs, pivots, zones, trend/stack)
# ---------------------------------------------------------------------------

def _build_tf_block(completed, price, tf, pivot_l, pivot_r):
    block = _blank_tf_block()
    if not completed:
        return block
    closes = [b["close"] for b in completed]

    sma10 = _sma(closes, 10)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)

    block["sma_relationship"] = {
        "price_vs_10": _price_vs(price, sma10),
        "price_vs_20": _price_vs(price, sma20),
        "price_vs_50": _price_vs(price, sma50),
        "price_vs_200": _price_vs(price, sma200),
        "dynamic_support_state": _dynamic_support(completed, price, sma20, sma50, closes),
    }
    block["stack_state"] = _stack_state(sma10, sma20, sma50, sma200)
    block["trend_state"] = _trend_state(completed, price, sma20, sma50, sma200, closes)

    highs, lows = _swing_pivots(completed, pivot_l, pivot_r)
    block["key_levels"] = _key_levels(highs, lows, price)
    block["support_resistance_map"] = _sr_map(highs, lows, price)
    block["nearest_zone"] = _nearest_zone(block["support_resistance_map"], price)
    block["context_read"] = _tf_context_read(tf, block, price, sma20, sma50)
    return block


def _price_vs(price, sma):
    if sma is None or price is None or sma <= 0:
        return "UNKNOWN"
    diff_pct = (price - sma) / sma * 100.0
    if abs(diff_pct) <= _TESTING_PCT:
        return "TESTING"
    return "ABOVE" if diff_pct > 0 else "BELOW"


def _dynamic_support(completed, price, sma20, sma50, closes):
    ref = sma20 if sma20 is not None else sma50
    if ref is None or price is None or ref <= 0:
        return "UNKNOWN"
    rising = _slope_up(closes, 20 if sma20 is not None else 50)
    diff_pct = (price - ref) / ref * 100.0

    if diff_pct > _EXTENDED_PCT:
        return "OVEREXTENDED"
    if abs(diff_pct) <= _TESTING_PCT:
        # At value: defended if value is rising and recent lows held above it.
        if rising and _recent_low_held(completed, ref):
            return "DEFENDED"
        return "NEUTRAL"
    if diff_pct > 0:
        return "DEFENDED" if rising else "NEUTRAL"
    # price below value
    if _recently_reclaimed(closes, ref):
        return "RECLAIMING"
    return "LOST"


def _recent_low_held(completed, ref, window=4):
    seg = completed[-window:]
    if not seg:
        return False
    # A wick may undercut, but closes should hold at/above value.
    return all(b["close"] >= ref * 0.985 for b in seg)


def _recently_reclaimed(closes, ref, window=4):
    seg = closes[-window:]
    if len(seg) < 2:
        return False
    was_below = any(c < ref for c in seg[:-1])
    now_above = seg[-1] >= ref
    return was_below and now_above


def _stack_state(s10, s20, s50, s200):
    present = [s for s in (s10, s20, s50, s200) if s is not None]
    if len(present) < 2:
        return "UNKNOWN"
    # Use the available shorter->longer ordering.
    seq = [s for s in (s10, s20, s50, s200) if s is not None]
    bull = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
    bear = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
    spread = (max(seq) - min(seq)) / max(seq) * 100.0 if max(seq) > 0 else 0.0
    if bull and spread >= 2.0:
        return "CLEAN_EXPANSION"
    if bear and spread >= 2.0:
        return "INVERTED"
    if spread < 1.5:
        return "COMPRESSED"
    if bull or bear:
        return "TRANSITIONAL"
    return "WARPED"


def _trend_state(completed, price, sma20, sma50, sma200, closes):
    if sma20 is None:
        return "UNKNOWN"
    above20 = price >= sma20
    above50 = sma50 is None or price >= sma50
    rising20 = _slope_up(closes, 20)
    rising50 = _slope_up(closes, 50) if sma50 is not None else None
    ext_pct = (price - sma20) / sma20 * 100.0 if sma20 > 0 else 0.0

    if not above20 and (sma50 is not None and price < sma50):
        if _recently_reclaimed(closes, sma20):
            return "REPAIR"
        if rising50 is False:
            return "FAILURE"
        return "REPAIR"
    if above20 and above50 and rising20:
        if ext_pct > _EXTENDED_PCT:
            return "MATURE_CONTINUATION"
        if _broke_recent_high(completed):
            return "FRESH_EXPANSION"
        return "MATURE_CONTINUATION"
    if abs(ext_pct) <= _TESTING_PCT and not rising20:
        return "ACCUMULATING"
    return "TRANSITION"


def _broke_recent_high(completed, window=10):
    if len(completed) < window + 1:
        return False
    recent = completed[-1]["close"]
    prior_high = max(b["high"] for b in completed[-window - 1:-1])
    return recent > prior_high


# ---------------------------------------------------------------------------
# Swing pivots / levels / zones
# ---------------------------------------------------------------------------

def _swing_pivots(completed, left, right):
    highs, lows = [], []
    n = len(completed)
    for i in range(left, n - right):
        win = completed[i - left:i + right + 1]
        hv = completed[i]["high"]
        lv = completed[i]["low"]
        if hv >= max(b["high"] for b in win):
            highs.append({"date": completed[i]["date"], "level": hv})
        if lv <= min(b["low"] for b in win):
            lows.append({"date": completed[i]["date"], "level": lv})
    return highs, lows


def _key_levels(highs, lows, price):
    out = []
    for h in highs[-6:]:
        out.append({"level": _round(h["level"]), "kind": "RESISTANCE", "date": _iso(h["date"])})
    for l in lows[-6:]:
        out.append({"level": _round(l["level"]), "kind": "SUPPORT", "date": _iso(l["date"])})
    return out


def _sr_map(highs, lows, price):
    """Compact support/resistance map relative to current price."""
    out = []
    for l in lows:
        lvl = l["level"]
        out.append({
            "level": _round(lvl), "type": "SUPPORT",
            "side": "below" if lvl <= price else "above",
            "distance_pct": _pct_dist(price, lvl),
        })
    for h in highs:
        lvl = h["level"]
        out.append({
            "level": _round(lvl), "type": "RESISTANCE",
            "side": "above" if lvl >= price else "below",
            "distance_pct": _pct_dist(price, lvl),
        })
    out.sort(key=lambda z: (z["distance_pct"] if z["distance_pct"] is not None else 9e9))
    return out[:8]


def _nearest_zone(sr_map, price):
    below = [z for z in sr_map if z["side"] == "below"]
    above = [z for z in sr_map if z["side"] == "above"]
    nearest = None
    if below:
        nearest = min(below, key=lambda z: z["distance_pct"] if z["distance_pct"] is not None else 9e9)
    if above:
        cand = min(above, key=lambda z: z["distance_pct"] if z["distance_pct"] is not None else 9e9)
        if nearest is None or (cand["distance_pct"] or 9e9) < (nearest["distance_pct"] or 9e9):
            nearest = cand
    if nearest is None:
        return None
    return {
        "level": nearest["level"], "type": nearest["type"], "side": nearest["side"],
        "distance_pct": nearest["distance_pct"],
        "zone_grade": "FUNCTIONAL", "freshness": "TESTED",
    }


def _nearest(sr_map, side, kind=None):
    cand = [z for z in sr_map if z["side"] == side and (kind is None or z["type"] == kind)]
    if not cand:
        return None
    return min(cand, key=lambda z: z["distance_pct"] if z["distance_pct"] is not None else 9e9)


def _tf_context_read(tf, block, price, sma20, sma50):
    trend = block["trend_state"]
    dyn = block["sma_relationship"]["dynamic_support_state"]
    return f"{tf} trend {trend.lower()}, dynamic support {dyn.lower()}"


# ---------------------------------------------------------------------------
# Monthly bias / weekly campaign
# ---------------------------------------------------------------------------

def _monthly_bias(completed, price, block):
    if not completed:
        return "UNKNOWN"
    closes = [b["close"] for b in completed]
    sma50 = _sma(closes, 50)
    sma20 = _sma(closes, 20)
    ref = sma50 if sma50 is not None else sma20
    rising = _slope_up(closes, 50 if sma50 is not None else 20)
    trend = block["trend_state"]
    if ref is None:
        return "UNKNOWN"
    if price >= ref and rising:
        return "BULLISH"
    if price < ref and rising is False:
        return "BEARISH"
    if trend == "REPAIR":
        return "REPAIR"
    if block["stack_state"] == "COMPRESSED":
        return "RANGE"
    return "TRANSITION"


def _weekly_campaign(w_completed, m_completed, price, w_block, m_block):
    if not w_completed:
        return "UNKNOWN"
    sr = w_block["support_resistance_map"]
    sup = _nearest(sr, "below", "SUPPORT")
    res = _nearest(sr, "above", "RESISTANCE")
    dyn = w_block["sma_relationship"]["dynamic_support_state"]
    trend = w_block["trend_state"]

    pos = _range_position(w_completed, price)         # 0 (low) .. 1 (high)
    near_support = _opt(sup, "distance_pct") is not None and sup["distance_pct"] <= _NEAR_PCT
    into_supply = _opt(res, "distance_pct") is not None and res["distance_pct"] <= _SUPPLY_NEAR_PCT
    reacted_up = len(w_completed) >= 1 and w_completed[-1]["close"] > w_completed[-1]["open"]

    # Bounce: a genuine reaction up off a recent major swing low (lower range)
    # outranks the raw "value lost" read — price came into demand and reacted.
    if pos <= 0.4 and reacted_up and _recent_swing_low(w_completed, within=6):
        return "HTF_BOUNCE"
    # Value loss / reclaim (dynamic-support truth).
    if dyn == "LOST":
        return "HTF_FAILURE"
    if dyn == "RECLAIMING":
        return "HTF_RECLAIM"
    # Genuine supply rejection: in the UPPER range, pressed into overhead supply,
    # and not a clean fresh breakout.
    if into_supply and pos >= 0.7 and trend != "FRESH_EXPANSION":
        return "HTF_SUPPLY_REJECTION"
    if trend in ("FRESH_EXPANSION", "MATURE_CONTINUATION") and dyn in ("DEFENDED", "NEUTRAL", "OVEREXTENDED"):
        return "HTF_CONTINUATION"
    if trend == "REPAIR":
        return "HTF_REPAIR"
    # Otherwise: middle of the range, no decisive HTF interaction.
    return "HTF_MID_RANGE"


def _recent_swing_low(completed, within=6):
    if len(completed) < 3:
        return False
    lows = [b["low"] for b in completed]
    min_idx = lows.index(min(lows))
    return min_idx >= len(completed) - within


def _range_position(completed, price, window=52):
    seg = completed[-window:] if len(completed) >= window else completed
    if not seg:
        return 0.5
    hi = max(b["high"] for b in seg)
    lo = min(b["low"] for b in seg)
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (price - lo) / (hi - lo)))


# ---------------------------------------------------------------------------
# Campaign location / sequence / relationship
# ---------------------------------------------------------------------------

def _campaign_location(price, w_block, m_block):
    sr_w = w_block["support_resistance_map"]
    sr_m = m_block["support_resistance_map"]
    sup_w = _nearest(sr_w, "below", "SUPPORT")
    res_w = _nearest(sr_w, "above", "RESISTANCE")
    sup_m = _nearest(sr_m, "below", "SUPPORT")
    res_m = _nearest(sr_m, "above", "RESISTANCE")

    dist_sup = _min_opt(_opt(sup_w, "distance_pct"), _opt(sup_m, "distance_pct"))
    dist_res = _min_opt(_opt(res_w, "distance_pct"), _opt(res_m, "distance_pct"))

    campaign = w_block.get("campaign_state")
    dyn = w_block["sma_relationship"]["dynamic_support_state"]

    near_m_sup = _opt(sup_m, "distance_pct") is not None and sup_m["distance_pct"] <= _NEAR_PCT
    near_w_sup = _opt(sup_w, "distance_pct") is not None and sup_w["distance_pct"] <= _NEAR_PCT

    # Location stays consistent with the weekly campaign classification.
    if campaign == "HTF_SUPPLY_REJECTION":
        label, quality = "INTO_HTF_SUPPLY", "HOSTILE"
    elif campaign == "HTF_FAILURE":
        label, quality = "BELOW_HTF_FAILURE", "HOSTILE"
    elif campaign == "HTF_BOUNCE":
        if near_m_sup:
            label, quality = "AT_MONTHLY_DEMAND", "SOVEREIGN"
        else:
            label, quality = "AT_WEEKLY_DEMAND", "FUNCTIONAL"
    elif campaign in ("HTF_RECLAIM", "HTF_REPAIR"):
        label, quality = "ABOVE_HTF_RECLAIM", "FUNCTIONAL"
    elif campaign == "HTF_MID_RANGE":
        label, quality = "MID_RANGE", "NEUTRAL"
    elif campaign == "HTF_CONTINUATION":
        if dyn == "OVEREXTENDED":
            label, quality = "EXTENDED_ABOVE_VALUE", "INFORMATIONAL"
        elif near_m_sup:
            label, quality = "AT_MONTHLY_DEMAND", "SOVEREIGN"
        else:
            label, quality = "AT_HTF_SUPPORT", "FUNCTIONAL"
    elif near_m_sup:
        label, quality = "AT_MONTHLY_DEMAND", "SOVEREIGN"
    elif near_w_sup:
        label, quality = "AT_WEEKLY_DEMAND", "FUNCTIONAL"
    elif dyn == "OVEREXTENDED":
        label, quality = "EXTENDED_ABOVE_VALUE", "INFORMATIONAL"
    elif dyn == "DEFENDED":
        label, quality = "AT_HTF_SUPPORT", "FUNCTIONAL"
    else:
        label, quality = "MID_RANGE", "NEUTRAL"

    path = "UNKNOWN"
    if dist_res is None:
        path = "OPEN"
    elif dist_res <= _SUPPLY_NEAR_PCT:
        path = "BLOCKED_BY_SUPPLY"
    elif dist_res <= 2 * _SUPPLY_NEAR_PCT:
        path = "PARTIALLY_CONGESTED"
    else:
        path = "OPEN"

    return {
        "label": label, "quality": quality,
        "distance_to_nearest_support_pct": dist_sup,
        "distance_to_nearest_resistance_pct": dist_res,
        "path_state": path,
    }


def _htf_sequence(w_completed, m_completed, price, w_block, m_block):
    dyn = w_block["sma_relationship"]["dynamic_support_state"]
    campaign = w_block.get("campaign_state")
    loc_sup = _nearest(w_block["support_resistance_map"], "below", "SUPPORT")

    came_from = "UNKNOWN"
    if campaign == "HTF_BOUNCE":
        came_from = "WEEKLY_DEMAND"
    elif campaign in ("HTF_FAILURE",):
        came_from = "BREAKDOWN"
    elif campaign == "HTF_SUPPLY_REJECTION":
        came_from = "MAJOR_SUPPLY"
    elif campaign in ("HTF_CONTINUATION", "HTF_RECLAIM"):
        came_from = "WEEKLY_DEMAND"
    elif campaign == "HTF_MID_RANGE":
        came_from = "MID_RANGE"

    attempt = {
        "HTF_BOUNCE": "BOUNCE", "HTF_RECLAIM": "RECLAIM",
        "HTF_CONTINUATION": "HOLD", "HTF_REPAIR": "RETEST",
        "HTF_SUPPLY_REJECTION": "FAILURE", "HTF_FAILURE": "FAILURE",
        "HTF_MID_RANGE": "UNKNOWN",
    }.get(campaign, "UNKNOWN")

    current_read = {
        "HTF_CONTINUATION": "SUPPORTED_CONTINUATION", "HTF_BOUNCE": "FORMING",
        "HTF_RECLAIM": "REPAIRING", "HTF_REPAIR": "REPAIRING",
        "HTF_SUPPLY_REJECTION": "HOSTILE", "HTF_FAILURE": "FAILED",
        "HTF_MID_RANGE": "FORMING",
    }.get(campaign, "UNKNOWN")

    weekly_bos = _broke_recent_high(w_completed) if w_completed else False
    monthly_bos = _broke_recent_high(m_completed) if m_completed else False
    bos_level = _round(w_completed[-1]["high"]) if (weekly_bos and w_completed) else None
    if weekly_bos and dyn in ("DEFENDED", "RECLAIMING"):
        bos_quality = "STRONG"
    elif weekly_bos:
        bos_quality = "MODERATE"
    elif monthly_bos:
        bos_quality = "MODERATE"
    else:
        bos_quality = "NONE"

    return {
        "came_from": came_from, "attempt": attempt, "current_read": current_read,
        "bos_context": {
            "weekly_bos_detected": bool(weekly_bos),
            "monthly_bos_detected": bool(monthly_bos),
            "bos_level": bos_level, "bos_quality": bos_quality,
        },
    }


def _setup_relationship(tiering_result, obj, price):
    rel = {
        "supports_long_setup": False, "weakens_long_setup": False,
        "blocks_snipe_contextually": False, "context_grade": "UNKNOWN",
        "context_score": None, "promotion_support": [], "missing_htf_proof": [],
        "blocking_reasons": [], "invalidation_conditions": [],
    }
    if obj["data_status"] in ("UNAVAILABLE", "ERROR"):
        return rel

    loc = obj["campaign_location"]
    weekly = obj["weekly"]
    monthly = obj["monthly"]
    campaign = weekly.get("campaign_state")
    bias = monthly.get("bias_state")
    dyn = weekly["sma_relationship"]["dynamic_support_state"]

    score, support, missing, blocking, invalidations = _score_context(obj, price)
    rel["context_score"] = score
    rel["context_grade"] = _grade(score)
    rel["promotion_support"] = support
    rel["missing_htf_proof"] = missing
    rel["blocking_reasons"] = blocking
    rel["invalidation_conditions"] = invalidations

    hostile = loc["quality"] == "HOSTILE" or campaign in ("HTF_SUPPLY_REJECTION", "HTF_FAILURE")
    supportive = (
        campaign in ("HTF_BOUNCE", "HTF_CONTINUATION", "HTF_RECLAIM")
        and loc["quality"] in ("SOVEREIGN", "FUNCTIONAL")
        and not hostile
    )

    rel["supports_long_setup"] = bool(supportive)
    rel["weakens_long_setup"] = bool(
        not supportive and (loc["label"] in ("MID_RANGE", "EXTENDED_ABOVE_VALUE") or campaign == "HTF_REPAIR")
    )
    rel["blocks_snipe_contextually"] = bool(hostile)

    # Future-ready promotion hint (evidence only — never promotes).
    if rel["context_grade"] in ("A", "B") and supportive:
        if "HTF campaign context supports SNIPE review." not in rel["promotion_support"]:
            rel["promotion_support"].append("HTF campaign context supports SNIPE review.")
    return rel


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_context(obj, price):
    loc = obj["campaign_location"]
    weekly = obj["weekly"]
    monthly = obj["monthly"]
    campaign = weekly.get("campaign_state")
    bias = monthly.get("bias_state")
    dyn = weekly["sma_relationship"]["dynamic_support_state"]
    path = loc["path_state"]
    bos = obj["htf_sequence"]["bos_context"]

    score = 50
    support, missing, blocking, invalidations = [], [], [], []

    if loc["quality"] == "SOVEREIGN":
        score += 20
        support.append("price at sovereign monthly/weekly demand")
    elif loc["quality"] == "FUNCTIONAL":
        score += 10

    if dyn == "DEFENDED":
        score += 15
        support.append("weekly/monthly dynamic support defended")
    elif dyn == "RECLAIMING":
        score += 5
        missing.append("dynamic value reclaim needs retest/hold confirmation")
    elif dyn == "LOST":
        score -= 15
        blocking.append("weekly/monthly value lost; reclaim failed")
        invalidations.append("loss of reclaimed value confirms HTF failure")
    elif dyn == "OVEREXTENDED":
        score -= 10
        missing.append("price extended above HTF value; await pullback to value")

    if bos["weekly_bos_detected"] or campaign == "HTF_RECLAIM":
        score += 15
        support.append("weekly BOS / reclaim from HTF value")

    if bias in ("BULLISH",):
        score += 10
        support.append("monthly bias constructive")
    elif bias in ("BEARISH", "FAILURE"):
        score -= 10
        blocking.append("monthly bias hostile/failing")

    if weekly["trend_state"] in ("FRESH_EXPANSION", "MATURE_CONTINUATION"):
        score += 10
    elif weekly["trend_state"] in ("TRANSITION", "FAILURE"):
        score -= 10

    if path == "OPEN":
        score += 10
        support.append("path open to next HTF resistance")
    elif path == "BLOCKED_BY_SUPPLY":
        score -= 10
        blocking.append("path blocked by nearby HTF supply")

    if loc["label"] == "INTO_HTF_SUPPLY":
        score -= 20
        blocking.append("setup pushing into major HTF supply")
        missing.append("acceptance through HTF resistance required for SNIPE review")
    elif loc["label"] == "MID_RANGE":
        score -= 15
        missing.append("no HTF decision zone; lower-timeframe proof controls")
    elif loc["label"] == "BELOW_HTF_FAILURE":
        score -= 15
        blocking.append("price below failed HTF value")

    nz = weekly.get("nearest_zone")
    if isinstance(nz, dict) and nz.get("freshness") == "FRESH":
        score += 5

    if obj["data_status"] != "OK":
        score -= 5
        missing.append("HTF history incomplete; context is approximate")

    score = max(0, min(100, score))
    return score, support, missing, blocking, invalidations


# ---------------------------------------------------------------------------
# Diagnostic sentence + render
# ---------------------------------------------------------------------------

def _diagnostic_sentence(obj):
    status = obj["data_status"]
    if status in ("UNAVAILABLE", "ERROR"):
        return "HTF context: unavailable — insufficient higher-timeframe data."
    campaign = obj["weekly"].get("campaign_state", "UNKNOWN")
    bias = obj["monthly"].get("bias_state", "UNKNOWN")
    loc = obj["campaign_location"]
    rel = obj["setup_relationship"]
    if rel["blocks_snipe_contextually"]:
        return ("HTF context: Caution — setup is pushing into weekly/monthly supply; "
                "SNIPE review requires acceptance through HTF resistance.")
    if campaign == "HTF_REPAIR":
        return ("HTF context: Weekly repair — price reclaimed value but still needs "
                "defended hold and follow-through.")
    if rel["supports_long_setup"]:
        return (f"HTF context: Weekly campaign support — {campaign.replace('HTF_', '').lower()} "
                f"from {loc['label'].replace('_', ' ').lower()}; monthly bias "
                f"{bias.lower()}.")
    return ("HTF context: Neutral — price is mid-range on weekly/monthly; "
            "lower-timeframe proof controls.")


def render_htf_line(htf, config=None):
    """One compact alert line — only when render_compact_line is true. Else None."""
    cfg = (config or {}).get("higher_timeframe_context", {}) if isinstance(config, dict) else {}
    if not cfg.get("render_compact_line", False):
        return None
    if not isinstance(htf, dict) or htf.get("enabled") is False:
        return None
    if str(htf.get("data_status")) in ("UNAVAILABLE", "ERROR"):
        return None
    sentence = str(htf.get("diagnostic_sentence") or "").strip()
    if not sentence:
        return None
    return f"  {sentence}"


# ---------------------------------------------------------------------------
# Compact, JSON-safe history snapshot
# ---------------------------------------------------------------------------

def compact_history_snapshot(htf):
    """Return a compact, strictly JSON-safe snapshot, or None when missing."""
    if htf is None:
        return None
    if not isinstance(htf, dict):
        return {
            "data_status": None, "monthly_bias_state": None,
            "weekly_campaign_state": None, "campaign_location_label": None,
            "campaign_location_quality": None, "context_grade": None,
            "context_score": None, "supports_long_setup": None,
            "weakens_long_setup": None, "blocks_snipe_contextually": None,
            "promotion_support": [], "missing_htf_proof": [],
            "blocking_reasons": ["higher_timeframe_context snapshot degraded: malformed source"],
            "diagnostic_sentence": None,
        }
    try:
        rel = htf.get("setup_relationship") or {}
        loc = htf.get("campaign_location") or {}
        return {
            "data_status": _safe_scalar(htf.get("data_status")),
            "monthly_bias_state": _safe_scalar((htf.get("monthly") or {}).get("bias_state")),
            "weekly_campaign_state": _safe_scalar((htf.get("weekly") or {}).get("campaign_state")),
            "campaign_location_label": _safe_scalar(loc.get("label")),
            "campaign_location_quality": _safe_scalar(loc.get("quality")),
            "context_grade": _safe_scalar(rel.get("context_grade")),
            "context_score": _safe_number(rel.get("context_score")),
            "supports_long_setup": _safe_bool(rel.get("supports_long_setup")),
            "weakens_long_setup": _safe_bool(rel.get("weakens_long_setup")),
            "blocks_snipe_contextually": _safe_bool(rel.get("blocks_snipe_contextually")),
            "promotion_support": _safe_str_list(rel.get("promotion_support")),
            "missing_htf_proof": _safe_str_list(rel.get("missing_htf_proof")),
            "blocking_reasons": _safe_str_list(rel.get("blocking_reasons")),
            "diagnostic_sentence": _safe_scalar(htf.get("diagnostic_sentence")),
        }
    except Exception:  # pragma: no cover
        return {
            "data_status": None, "monthly_bias_state": None,
            "weekly_campaign_state": None, "campaign_location_label": None,
            "campaign_location_quality": None, "context_grade": None,
            "context_score": None, "supports_long_setup": None,
            "weakens_long_setup": None, "blocks_snipe_contextually": None,
            "promotion_support": [], "missing_htf_proof": [],
            "blocking_reasons": ["higher_timeframe_context snapshot degraded: extraction error"],
            "diagnostic_sentence": None,
        }


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
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _round(v, nd=4):
    f = _f(v)
    return round(f, nd) if f is not None else None


def _pct_dist(price, level):
    p = _f(price)
    lv = _f(level)
    if p is None or lv is None or p <= 0:
        return None
    return round(abs(p - lv) / p * 100.0, 2)


def _opt(d, key):
    return d.get(key) if isinstance(d, dict) else None


def _min_opt(a, b):
    vals = [x for x in (a, b) if x is not None]
    return min(vals) if vals else None


def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _parse_date(value)


def _parse_date(value):
    if value is None:
        return None
    try:
        s = str(value)[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _iso(d):
    if isinstance(d, (date, datetime)):
        return d.isoformat()[:10]
    return None


def _grade(score):
    s = _f(score)
    if s is None:
        return "UNKNOWN"
    if s >= 85:
        return "A"
    if s >= 70:
        return "B"
    if s >= 55:
        return "C"
    if s >= 40:
        return "D"
    return "F"


# JSON-safety primitives (mirror state_store hardening contract).

def _safe_scalar(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value) if (value == value and value not in (float("inf"), float("-inf"))) else None
    return None


def _safe_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if (value == value and value not in (float("inf"), float("-inf"))) else None
    return None


def _safe_bool(value):
    if value is True:
        return True
    if value is False:
        return False
    return None


def _safe_str_list(value):
    out = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out

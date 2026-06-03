"""Structure-first feature extraction.

No rsi, macd, bollinger_bands, or stochastic. Ever.
Only: structure, value/SMA alignment, liquidity, sweep, BOS/MSS/CHoCH/reclaim,
FVG, OB/demand/flip zone, retest, overhead, targets, invalidation, R:R, volume behavior.
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SMA / Value alignment
# ---------------------------------------------------------------------------

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def compute_smas(df: pd.DataFrame) -> dict:
    c = df["close"]
    s20 = _sma(c, 20)
    s50 = _sma(c, 50)
    s200 = _sma(c, 200)
    return {
        "sma20": round(float(s20.iloc[-1]), 4) if not np.isnan(s20.iloc[-1]) else None,
        "sma50": round(float(s50.iloc[-1]), 4) if not np.isnan(s50.iloc[-1]) else None,
        "sma200": round(float(s200.iloc[-1]), 4) if not np.isnan(s200.iloc[-1]) else None,
        "_s20": s20,
        "_s50": s50,
        "_s200": s200,
    }


def sma_value_alignment(cur: float, smas: dict) -> str:
    """supportive | mixed | hostile | unavailable."""
    s20, s50, s200 = smas.get("sma20"), smas.get("sma50"), smas.get("sma200")
    if s20 is None or s50 is None:
        return "unavailable"
    if s200 is None:
        # Only 20/50 available
        if cur > s20 > s50:
            return "supportive"
        if cur < s20 and cur < s50:
            return "hostile"
        return "mixed"
    if cur > s20 > s50 > s200:
        return "supportive"
    if cur < s20 and cur < s50 and cur < s200:
        return "hostile"
    return "mixed"


def price_extension_from_sma20_pct(cur: float, sma20: float | None) -> float | None:
    if sma20 is None or sma20 == 0:
        return None
    return round(abs(cur - sma20) / sma20 * 100, 2)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean().iloc[-1]
    return round(float(atr), 4) if not np.isnan(atr) else None


# ---------------------------------------------------------------------------
# Swing highs / lows
# ---------------------------------------------------------------------------

def _find_swing_highs(high: pd.Series, lookback: int, pivot_n: int = 3) -> list:
    """Return list of (index_pos, price) for swing highs within lookback bars."""
    highs = high.iloc[-lookback:]
    pivots = []
    arr = highs.values
    for i in range(pivot_n, len(arr) - pivot_n):
        if arr[i] == max(arr[i - pivot_n: i + pivot_n + 1]):
            pivots.append((len(high) - lookback + i, float(arr[i])))
    return pivots


def _find_swing_lows(low: pd.Series, lookback: int, pivot_n: int = 3) -> list:
    """Return list of (index_pos, price) for swing lows within lookback bars."""
    lows = low.iloc[-lookback:]
    pivots = []
    arr = lows.values
    for i in range(pivot_n, len(arr) - pivot_n):
        if arr[i] == min(arr[i - pivot_n: i + pivot_n + 1]):
            pivots.append((len(low) - lookback + i, float(arr[i])))
    return pivots


def compute_swings(df: pd.DataFrame, lookback: int) -> dict:
    sh = _find_swing_highs(df["high"], lookback)
    sl = _find_swing_lows(df["low"], lookback)
    return {
        "swing_highs": sh,
        "swing_lows": sl,
        "last_swing_high": round(sh[-1][1], 4) if sh else None,
        "last_swing_low": round(sl[-1][1], 4) if sl else None,
    }


# ---------------------------------------------------------------------------
# Liquidity pools
# ---------------------------------------------------------------------------

def compute_liquidity_pools(df: pd.DataFrame, swings: dict) -> dict:
    h, l = df["high"], df["low"]
    cur = float(df["close"].iloc[-1])

    # Equal highs/lows: swing levels within 0.2% of each other
    def cluster(levels: list, tol: float = 0.002) -> list:
        pools = []
        for _, price in levels:
            for p in pools:
                if abs(price - p) / max(p, 1e-6) <= tol:
                    break
            else:
                pools.append(price)
        return sorted(pools)

    sh_prices = [p for _, p in swings["swing_highs"]]
    sl_prices = [p for _, p in swings["swing_lows"]]

    equal_highs = cluster([(0, p) for p in sh_prices])
    equal_lows = cluster([(0, p) for p in sl_prices])

    recent_range_high = round(float(h.iloc[-20:].max()), 4)
    recent_range_low = round(float(l.iloc[-20:].min()), 4)

    pools_above = sorted([p for p in equal_highs if p > cur])
    pools_below = sorted([p for p in equal_lows if p < cur], reverse=True)

    return {
        "equal_highs": [round(p, 4) for p in equal_highs],
        "equal_lows": [round(p, 4) for p in equal_lows],
        "recent_range_high": recent_range_high,
        "recent_range_low": recent_range_low,
        "nearest_pool_above": round(pools_above[0], 4) if pools_above else None,
        "nearest_pool_below": round(pools_below[0], 4) if pools_below else None,
    }


# ---------------------------------------------------------------------------
# Sweep detection
# ---------------------------------------------------------------------------

def detect_sweep(df: pd.DataFrame, config: dict) -> dict:
    """Detect liquidity sweep: recent low breaks below prior swing low.

    Critically: the recent window is excluded from the prior low comparison
    so we don't compare recent low against itself.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    recent_window = thresholds.get("recent_trigger_window_bars", 10)
    swing_lookback = thresholds.get("swing_lookback_bars", 60)
    atr = compute_atr(df) or 0

    l = df["low"]
    if len(l) < swing_lookback + recent_window:
        return {"sweep_detected": False, "sweep_low": None, "prior_low": None}

    # Prior low: from lookback window, excluding the recent window
    prior_window = l.iloc[-(swing_lookback + recent_window): -recent_window]
    recent_window_data = l.iloc[-recent_window:]

    prior_low = float(prior_window.min())
    recent_low = float(recent_window_data.min())

    # Sweep requires recent low to break below prior low by at least a meaningful margin
    threshold = max(prior_low * 0.001, atr * 0.1) if atr else prior_low * 0.001
    swept = recent_low < (prior_low - threshold)

    return {
        "sweep_detected": bool(swept),
        "sweep_low": round(recent_low, 4) if swept else None,
        "prior_low": round(prior_low, 4),
    }


# ---------------------------------------------------------------------------
# BOS / MSS / CHoCH / Reclaim
# ---------------------------------------------------------------------------

def detect_structure_event(df: pd.DataFrame, sweep: dict, config: dict) -> dict:
    """Detect the most recent bullish structure event.

    Requires body/close confirmation — wick-only breaks do not qualify.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    recent_window = thresholds.get("recent_trigger_window_bars", 10)
    swing_lookback = thresholds.get("swing_lookback_bars", 60)

    c = df["close"]
    h = df["high"]
    o = df["open"]

    if len(c) < swing_lookback:
        return {"structure_event": "none", "structure_level": None, "structure_confirmed": False}

    # Prior high: highest close in lookback, excluding recent window
    prior_window_close = c.iloc[-(swing_lookback + recent_window): -recent_window]
    prior_window_high = h.iloc[-(swing_lookback + recent_window): -recent_window]
    if prior_window_close.empty:
        return {"structure_event": "none", "structure_level": None, "structure_confirmed": False}

    prior_high_close = float(prior_window_close.max())
    prior_high_wick = float(prior_window_high.max())

    # Recent closes and bodies
    recent_closes = c.iloc[-recent_window:]
    recent_opens = o.iloc[-recent_window:]
    recent_highs = h.iloc[-recent_window:]

    # Body acceptance: at least one recent candle closed above prior high close
    body_above = recent_closes > prior_high_close
    latest_close = float(c.iloc[-1])
    latest_open = float(o.iloc[-1])

    event = "none"
    structure_level = None

    if body_above.any():
        # BOS: clean break with no sweep needed
        # MSS: sweep happened before the break (shift in structure with liquidity grab)
        if sweep.get("sweep_detected"):
            event = "MSS"
        else:
            event = "BOS"
        # Use the prior high close as the broken level
        structure_level = round(prior_high_close, 4)

    # Reclaim: price closed back above a level it previously lost
    # Detect as: most recent close above prior high close, after having been below it
    if event == "none":
        was_below = (c.iloc[-recent_window - 5: -recent_window] < prior_high_close).any()
        if was_below and latest_close > prior_high_close:
            event = "reclaim"
            structure_level = round(prior_high_close, 4)

    # CHoCH: change of character — wick broke above but body accepted below (bearish signal)
    # For bullish scanner: CHoCH is a prior bearish CHoCH that now reversed
    # Simplified: prior high broken by wick only (not body) is noted but not treated as confirmed
    wick_only_break = (recent_highs > prior_high_close).any() and not body_above.any()

    return {
        "structure_event": event,
        "structure_level": structure_level,
        "structure_confirmed": event != "none",
        "prior_structural_high": round(prior_high_close, 4),
        "wick_only_break": bool(wick_only_break),
    }


# ---------------------------------------------------------------------------
# FVG detection
# ---------------------------------------------------------------------------

def detect_fvg(df: pd.DataFrame, config: dict) -> dict | None:
    """Detect most recent unfilled bullish FVG within lookback.

    Bullish FVG: candle1 high < candle3 low (gap between them).
    Returns None if no unfilled FVG found.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    lookback = thresholds.get("fvg_lookback_bars", 30)

    h = df["high"]
    l = df["low"]
    c = df["close"]

    n = len(df)
    if n < lookback + 2:
        return None

    cur_close = float(c.iloc[-1])
    best = None

    for i in range(n - lookback, n - 2):
        c1_high = float(h.iloc[i])
        c3_low = float(l.iloc[i + 2])

        if c3_low > c1_high:
            fvg_bot = round(c1_high, 4)
            fvg_top = round(c3_low, 4)
            fvg_mid = round((fvg_bot + fvg_top) / 2, 4)

            # Filled check: price has not returned into the FVG zone
            subsequent_lows = l.iloc[i + 3:]
            if not subsequent_lows.empty and float(subsequent_lows.min()) <= fvg_bot:
                continue  # FVG has been filled — exclude

            best = {
                "fvg_top": fvg_top,
                "fvg_mid": fvg_mid,
                "fvg_bot": fvg_bot,
                "fvg_start_idx": i,
                "fvg_end_idx": i + 2,
                "fvg_filled": False,
                "price_in_fvg": fvg_bot <= cur_close <= fvg_top,
            }
            # Take the most recent valid FVG
    return best


# ---------------------------------------------------------------------------
# OB / Demand / Flip zone
# ---------------------------------------------------------------------------

def detect_ob(df: pd.DataFrame, config: dict) -> dict | None:
    """Detect most recent valid, unmitigated bullish OB/demand zone.

    OB: last bearish candle before a displacement move up.
    Mitigated OB (price traded back through the body) is excluded.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    lookback = thresholds.get("ob_lookback_bars", 30)

    o = df["open"]
    c = df["close"]
    h = df["high"]
    l = df["low"]

    n = len(df)
    if n < lookback + 3:
        return None

    cur_close = float(c.iloc[-1])
    best = None

    for i in range(n - lookback, n - 3):
        is_bearish = float(c.iloc[i]) < float(o.iloc[i])
        if not is_bearish:
            continue

        # Displacement candle: next candle closes above the OB candle open with body
        disp_close = float(c.iloc[i + 1])
        disp_open = float(o.iloc[i + 1])
        ob_open = float(o.iloc[i])
        ob_close = float(c.iloc[i])

        body_displacement = disp_close > ob_open and disp_close > disp_open

        if not body_displacement:
            continue

        ob_hi = round(ob_open, 4)
        ob_lo = round(ob_close, 4)
        ob_core = round((ob_hi + ob_lo) / 2, 4)

        # Mitigation check: has price closed back below ob_lo after the OB formed?
        subsequent_closes = c.iloc[i + 2:]
        if not subsequent_closes.empty and float(subsequent_closes.min()) < ob_lo:
            continue  # OB mitigated — exclude

        best = {
            "ob_hi": ob_hi,
            "ob_lo": ob_lo,
            "ob_core": ob_core,
            "ob_idx": i,
            "mitigated": False,
            "price_at_ob": ob_lo <= cur_close <= ob_hi,
        }

    return best


# ---------------------------------------------------------------------------
# Retest proximity / status
# ---------------------------------------------------------------------------

def assess_retest(cur: float, fvg: dict | None, ob: dict | None, atr: float | None) -> dict:
    """Assess whether price is retesting a key zone.

    Returns retest_status: confirmed | partial | missing | failed.
    """
    if atr is None or atr == 0:
        return {"retest_status": "missing", "retest_zone": None, "retest_distance_atr": None}

    zones = []
    if fvg:
        zones.append(("FVG", fvg["fvg_bot"], fvg["fvg_top"]))
    if ob:
        zones.append(("OB", ob["ob_lo"], ob["ob_hi"]))

    if not zones:
        return {"retest_status": "missing", "retest_zone": None, "retest_distance_atr": None}

    for label, z_lo, z_hi in zones:
        z_mid = (z_lo + z_hi) / 2

        if z_lo <= cur <= z_hi:
            # Price is inside the zone — confirmed retest
            return {
                "retest_status": "confirmed",
                "retest_zone": label,
                "retest_distance_atr": 0.0,
            }

        dist_to_zone = min(abs(cur - z_lo), abs(cur - z_hi))
        dist_atr = round(dist_to_zone / atr, 2)

        if dist_atr <= 0.5:
            return {
                "retest_status": "partial",
                "retest_zone": label,
                "retest_distance_atr": dist_atr,
            }

        if cur < z_lo:
            # Price has fallen below the zone — failed retest
            return {
                "retest_status": "failed",
                "retest_zone": label,
                "retest_distance_atr": dist_atr,
            }

    return {
        "retest_status": "missing",
        "retest_zone": None,
        "retest_distance_atr": None,
    }


# ---------------------------------------------------------------------------
# Overhead path
# ---------------------------------------------------------------------------

def assess_overhead(cur: float, pools: dict, atr: float | None, config: dict) -> dict:
    """Assess overhead resistance: clear | moderate | blocked | unknown."""
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    block_pct = thresholds.get("overhead_block_distance_pct", 3) / 100

    nearest_above = pools.get("nearest_pool_above")

    if nearest_above is None:
        return {"overhead_status": "unknown", "overhead_level": None, "overhead_distance_pct": None}

    dist_pct = (nearest_above - cur) / cur
    overhead_status = (
        "blocked" if dist_pct <= block_pct
        else "moderate" if dist_pct <= block_pct * 2.5
        else "clear"
    )

    return {
        "overhead_status": overhead_status,
        "overhead_level": round(nearest_above, 4),
        "overhead_distance_pct": round(dist_pct * 100, 2),
    }


# ---------------------------------------------------------------------------
# Targets / Invalidation / R:R
# ---------------------------------------------------------------------------

def estimate_targets(cur: float, pools: dict, structure: dict) -> list:
    """Return list of target dicts with label, level, reason."""
    targets = []
    above = pools.get("nearest_pool_above")
    highs = pools.get("equal_highs", [])

    if above:
        targets.append({"label": "T1", "level": round(above, 4), "reason": "nearest liquidity pool above"})

    if len(highs) >= 2:
        t2_candidates = [p for p in highs if p > (above or cur)]
        if t2_candidates:
            targets.append({"label": "T2", "level": round(t2_candidates[0], 4), "reason": "next major pool above"})

    return targets


def estimate_invalidation(fvg: dict | None, ob: dict | None, swings: dict) -> dict:
    """Return invalidation level and condition description."""
    levels = []

    if ob:
        levels.append((ob["ob_lo"], "below OB low"))
    if fvg:
        levels.append((fvg["fvg_bot"], "below FVG base"))
    if swings.get("last_swing_low") is not None:
        levels.append((swings["last_swing_low"], "below swing low"))

    if not levels:
        return {"invalidation_level": None, "invalidation_condition": "no clear invalidation identified"}

    # Use the highest (most conservative / closest) invalidation floor
    level, condition = max(levels, key=lambda x: x[0])
    return {
        "invalidation_level": round(level, 4),
        "invalidation_condition": condition,
    }


def estimate_rr(cur: float, targets: list, invalidation: dict) -> float | None:
    """Estimate R:R from current price, first target, and invalidation level."""
    inv_level = invalidation.get("invalidation_level")
    if not targets or inv_level is None:
        return None

    t1 = targets[0]["level"]
    risk = cur - inv_level
    reward = t1 - cur

    if risk <= 0 or reward <= 0:
        return None

    return round(reward / risk, 2)


# ---------------------------------------------------------------------------
# Volume behavior
# ---------------------------------------------------------------------------

def assess_volume(df: pd.DataFrame, config: dict) -> dict:
    """Assess recent volume vs 20-bar average."""
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    exp_ratio = thresholds.get("volume_expansion_ratio", 1.2)
    dryup_ratio = thresholds.get("volume_dryup_ratio", 0.8)

    v = df["volume"]
    if len(v) < 21:
        return {"volume_ratio": None, "volume_behavior": "unknown"}

    avg20 = float(v.iloc[-21:-1].mean())
    recent = float(v.iloc[-1])
    ratio = round(recent / avg20, 3) if avg20 > 0 else None

    if ratio is None:
        behavior = "unknown"
    elif ratio >= exp_ratio:
        behavior = "expansion"
    elif ratio <= dryup_ratio:
        behavior = "dryup"
    else:
        behavior = "neutral"

    return {"volume_ratio": ratio, "volume_behavior": behavior}


# ---------------------------------------------------------------------------
# VCP (Volatility Contraction Pattern) — Phase 1B evidence-capture engine
# ---------------------------------------------------------------------------
# Detects accumulation-style VCPs by measuring four objective components:
#   1. Prior advance (no advance → no VCP)
#   2. Contraction count (2–4 is canonical)
#   3. Range contraction (each pullback shallower than the prior)
#   4. Volume dry-up (recent volume contracted vs prior expansion phase)
# Plus MA alignment, pivot identification, and failure detection.
#
# OBSERVATIONAL ONLY. The returned fields are passed through enrich() → prefilter
# key_features → tiering final_signal → state_store alert_history for future
# backtesting. They are never read by any tier gate, scoring function, calibration
# step, routing decision, capital authorization, or alert formatter.
#
# Thresholds are conservative to avoid false-positive VCP labels on random chop —
# accuracy outweighs frequency in evidence capture.

_VCP_MIN_BARS                  = 60     # need enough history to see prior advance + consolidation
_VCP_ADVANCE_LOOKBACK_BARS     = 60     # look this far back of pivot for the advance low
_VCP_MIN_PULLBACK_PCT          = 2.0    # filter trivial pullbacks (noise)
_VCP_MIN_PRIOR_ADVANCE_PCT     = 25.0   # CONFIRMED requires meaningful prior run
_VCP_MIN_PRIOR_ADVANCE_FORMING = 10.0   # below this prior advance is too thin for FORMING
_VCP_VOLUME_DRYUP_RATIO        = 0.85   # recent vol < 85% of advance vol = dry-up
_VCP_FAILURE_BREAK_RATIO       = 0.98   # recent low < 98% of last contraction low = failure
_VCP_FAILURE_WINDOW_BARS       = 5      # recent low measured over this many bars
_VCP_VOLUME_RECENT_WINDOW_BARS = 10     # volume dry-up measured over this window
_VCP_IDEAL_CONTRACTION_MIN     = 2      # CONFIRMED requires ≥2 contractions
_VCP_IDEAL_CONTRACTION_MAX     = 4      # CONFIRMED requires ≤4 contractions

_EMPTY_VCP = {
    "vcp_status":               "UNKNOWN",
    "vcp_prior_advance_pct":    None,
    "vcp_contractions_count":   0,
    "vcp_range_contraction":    False,
    "vcp_contraction_sequence": [],
    "vcp_volume_dryup":         False,
    "vcp_volume_ratio":         None,
    "vcp_ma_alignment":         "UNKNOWN",
    "vcp_pivot_level":          None,
    "vcp_failure_flag":         False,
}


def _vcp_ma_alignment(cur_close: float, smas: dict) -> str:
    """Uppercase MA alignment label for VCP evidence record."""
    s20, s50, s200 = smas.get("sma20"), smas.get("sma50"), smas.get("sma200")
    if s20 is None or s50 is None:
        return "UNKNOWN"
    if s200 is None:
        if cur_close > s20 > s50:
            return "SUPPORTIVE"
        if cur_close < s20 and cur_close < s50:
            return "HOSTILE"
        return "MIXED"
    if cur_close > s20 > s50 > s200:
        return "SUPPORTIVE"
    if cur_close < s20 and cur_close < s50 and cur_close < s200:
        return "HOSTILE"
    return "MIXED"


def detect_vcp(df: pd.DataFrame, swings: dict, smas: dict, config: dict) -> dict:
    """Phase 1B: detect Volatility Contraction Pattern characteristics.

    Returns 10 vcp_* evidence fields. Pure observation — never read by any
    tier gate, scoring, calibration, routing, capital, or alert decision.
    Never raises. Returns _EMPTY_VCP on any unexpected condition.
    """
    try:
        return _detect_vcp_impl(df, swings, smas, config)
    except Exception as exc:                                # noqa: BLE001
        log.warning("detect_vcp_error: %s", exc)
        return dict(_EMPTY_VCP)


def _detect_vcp_impl(df: pd.DataFrame, swings: dict, smas: dict, _config: dict) -> dict:
    if df is None or len(df) < _VCP_MIN_BARS:
        return dict(_EMPTY_VCP)

    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]

    swing_highs = swings.get("swing_highs") or []
    swing_lows  = swings.get("swing_lows")  or []

    # Need at least two swing points on each side to identify a consolidation
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return dict(_EMPTY_VCP)

    # Pivot: highest of the recent swing highs. This is the top of the consolidation
    # — the level above which a true VCP would break out.
    pivot_idx, pivot_level = max(swing_highs, key=lambda p: p[1])

    # Prior advance: lowest swing low within the lookback window BEFORE the pivot.
    # Fallback to close minimum when no swing lows exist in the advance window
    # (e.g. clean monotonic uptrend produces no swing lows during the advance phase).
    advance_window_start = max(0, pivot_idx - _VCP_ADVANCE_LOOKBACK_BARS)
    pre_pivot_lows = [(i, p) for i, p in swing_lows if advance_window_start <= i < pivot_idx]
    if not pre_pivot_lows:
        window_closes = c.iloc[advance_window_start:pivot_idx]
        if len(window_closes) == 0:
            return dict(_EMPTY_VCP)
        rel_idx = int(np.argmin(window_closes.values))
        advance_low_idx = advance_window_start + rel_idx
        advance_low = float(window_closes.iloc[rel_idx])
    else:
        advance_low_idx, advance_low = min(pre_pivot_lows, key=lambda p: p[1])
    if advance_low <= 0:
        return dict(_EMPTY_VCP)

    prior_advance_pct = round((pivot_level - advance_low) / advance_low * 100, 2)

    # Walk the swing sequence from advance_low forward, alternating H/L. For each
    # rally-then-pullback pair after the advance phase, compute pullback depth.
    sequence = sorted(
        [(i, p, "H") for i, p in swing_highs if i >= advance_low_idx]
        + [(i, p, "L") for i, p in swing_lows if i >= advance_low_idx],
        key=lambda x: x[0],
    )
    pullback_depths: list[float] = []
    last_high: float | None = None
    for _idx, price, kind in sequence:
        if kind == "H":
            last_high = price
        elif kind == "L" and last_high is not None and last_high > price:
            depth = round((last_high - price) / last_high * 100, 2)
            if depth >= _VCP_MIN_PULLBACK_PCT:
                pullback_depths.append(depth)
            last_high = None

    contractions_count = len(pullback_depths)
    range_contraction = (
        contractions_count >= 2
        and all(
            pullback_depths[i] < pullback_depths[i - 1]
            for i in range(1, contractions_count)
        )
    )

    # Volume dry-up: recent-window mean vs prior advance-phase mean.
    volume_ratio: float | None = None
    volume_dryup = False
    if pivot_idx > advance_low_idx and len(v) >= _VCP_VOLUME_RECENT_WINDOW_BARS:
        try:
            advance_v = float(v.iloc[advance_low_idx:pivot_idx + 1].mean())
            recent_v  = float(v.iloc[-_VCP_VOLUME_RECENT_WINDOW_BARS:].mean())
            if advance_v > 0 and not np.isnan(advance_v) and not np.isnan(recent_v):
                volume_ratio = round(recent_v / advance_v, 3)
                volume_dryup = volume_ratio < _VCP_VOLUME_DRYUP_RATIO
        except (TypeError, ValueError, IndexError):
            pass

    # MA alignment from existing SMAs
    cur_close = float(c.iloc[-1])
    ma_alignment = _vcp_ma_alignment(cur_close, smas)

    # Failure detection: recent low broke below the most-recent post-pivot swing low
    failure_flag = False
    post_pivot_lows = [p for i, p in swing_lows if i > pivot_idx]
    if post_pivot_lows and len(l) >= _VCP_FAILURE_WINDOW_BARS:
        try:
            recent_low = float(l.iloc[-_VCP_FAILURE_WINDOW_BARS:].min())
            last_contraction_low = min(post_pivot_lows)
            if (
                last_contraction_low > 0
                and recent_low < last_contraction_low * _VCP_FAILURE_BREAK_RATIO
            ):
                failure_flag = True
        except (TypeError, ValueError, IndexError):
            pass

    # Status classification — conservative; false negatives preferred over false positives.
    has_advance        = prior_advance_pct >= _VCP_MIN_PRIOR_ADVANCE_PCT
    has_pattern_count  = _VCP_IDEAL_CONTRACTION_MIN <= contractions_count <= _VCP_IDEAL_CONTRACTION_MAX
    has_thin_advance   = prior_advance_pct < _VCP_MIN_PRIOR_ADVANCE_FORMING

    if failure_flag and contractions_count >= 1:
        status = "INVALID"
    elif (
        has_advance
        and has_pattern_count
        and range_contraction
        and volume_dryup
    ):
        status = "CONFIRMED"
    elif contractions_count >= 1 and not has_thin_advance and (
        range_contraction or volume_dryup
    ):
        status = "FORMING"
    elif has_thin_advance or contractions_count == 0:
        status = "ABSENT"
    else:
        status = "FORMING"

    return {
        "vcp_status":               status,
        "vcp_prior_advance_pct":    prior_advance_pct,
        "vcp_contractions_count":   contractions_count,
        "vcp_range_contraction":    bool(range_contraction),
        "vcp_contraction_sequence": pullback_depths,
        "vcp_volume_dryup":         bool(volume_dryup),
        "vcp_volume_ratio":         volume_ratio,
        "vcp_ma_alignment":         ma_alignment,
        "vcp_pivot_level":          round(pivot_level, 4),
        "vcp_failure_flag":         bool(failure_flag),
    }


# ---------------------------------------------------------------------------
# Phase 1C-P1: Break & Retest Doctrine Organs — evidence-capture engine
# ---------------------------------------------------------------------------
# Six structural evidence fields plus one deferred organ. Pure observation.
# None of these fields are read by any tier gate, scoring function, calibration
# step, routing decision, capital authorization, dedup logic, campaign identity,
# or alert formatter. They flow enrich() -> prefilter key_features -> tiering
# final_signal -> state_store alert_history for future backtesting only.
#
# CORE LAW: Setup Quality is not Entry Quality. These fields describe the entry
# context and the doctrine-sequence position; they never gate opportunity.
#
# VCP GOVERNING LAW: VCP is one entry family inside the larger Break & Retest
# doctrine. vcp_base never overrides structure, sponsorship, or risk.

_BRT_ZONE_FRESH_MAX_AGE_BARS  = 10    # zone younger than this with <=1 touch = fresh
_BRT_OVERLAP_WINDOW_BARS      = 10    # window for counting retest overlap bars
_BRT_OVERLAP_MIN_BARS         = 3     # >= this many overlapping bars = drift/overlap
_BRT_CONSUMPTION_HIGH_TOUCHES = 3     # >= this many zone touches = high consumption
_BRT_CONSUMPTION_MOD_TOUCHES  = 2     # this many touches = moderate consumption
_BRT_EXPANSION_PCT            = 5.0   # close this far above zone top = expanded away
_BRT_AUTHORITY_TOL_PCT        = 1.0   # swings within this % of level count toward authority
_BRT_AUTHORITY_STRONG_SWINGS  = 3     # >= this many nearby swings = strong authority
_BRT_DEFERRED_1H              = "deferred_requires_1h"


def _brt_active_zone(fvg: dict | None, ob: dict | None, retest_zone):
    """Return (zone_lo, zone_hi, formation_idx) for the controlling zone.

    Prefers the zone named by retest_zone; otherwise prefers OB, then FVG.
    Returns (None, None, None) when no zone exists.
    """
    if retest_zone == "FVG" and fvg:
        return fvg.get("fvg_bot"), fvg.get("fvg_top"), fvg.get("fvg_start_idx")
    if retest_zone == "OB" and ob:
        return ob.get("ob_lo"), ob.get("ob_hi"), ob.get("ob_idx")
    if ob:
        return ob.get("ob_lo"), ob.get("ob_hi"), ob.get("ob_idx")
    if fvg:
        return fvg.get("fvg_bot"), fvg.get("fvg_top"), fvg.get("fvg_start_idx")
    return None, None, None


def classify_entry_family(
    structure_event: str,
    sweep_detected: bool,
    fvg: dict | None,
    ob: dict | None,
    vcp_status: str,
    sma_value_alignment: str,
    retest_status: str,
) -> str:
    """Classify the Break & Retest entry family. Evidence only.

    Priority (first match wins):
      mss_reclaim             — sweep + MSS structure shift (liquidity-grab reversal)
      failed_break_conversion — reclaim of a previously lost level
      zone_core               — FVG and OB confluence
      fvg_entry               — FVG zone only
      ob_entry                — OB zone only
      vcp_base                — VCP pattern present, no specific FVG/OB zone
      dynamic_value           — supportive SMA value retest only (no zone)
      unclassified            — none of the above

    VCP is one family inside the doctrine; it never displaces a structural zone.
    """
    try:
        se = str(structure_event or "none")
        if bool(sweep_detected) and se.upper() == "MSS":
            return "mss_reclaim"
        if se.lower() == "reclaim":
            return "failed_break_conversion"
        has_fvg = bool(fvg)
        has_ob = bool(ob)
        if has_fvg and has_ob:
            return "zone_core"
        if has_fvg:
            return "fvg_entry"
        if has_ob:
            return "ob_entry"
        if str(vcp_status or "UNKNOWN") in ("CONFIRMED", "FORMING"):
            return "vcp_base"
        if (
            str(sma_value_alignment or "unavailable") == "supportive"
            and str(retest_status or "missing") in ("confirmed", "partial")
        ):
            return "dynamic_value"
        return "unclassified"
    except Exception as exc:                                # noqa: BLE001
        log.warning("entry_family_error: %s", exc)
        return "unclassified"


def assess_retest_quality(
    df: pd.DataFrame,
    retest_status: str,
    retest_zone,
    fvg: dict | None,
    ob: dict | None,
) -> str:
    """Quality of the retest interaction. Evidence only.

    Labels (first match wins):
      not_retesting — no zone, or retest_status missing/failed
      clean_bounce  — current bar wicked into the zone and closed back above it,
                      with little prior lingering (sharp defense)
      body_in_zone  — current close is inside the zone band
      overlap       — price overlapped the zone for several recent bars (drift)
      unclear       — fallback when none of the above is determinable

    DAILY-BAR LIMITATION: true intraday core-defense texture requires 1H data.
    These labels are the conservative daily-bar approximation.
    """
    try:
        if str(retest_status or "missing") in ("missing", "failed"):
            return "not_retesting"
        z_lo, z_hi, _idx = _brt_active_zone(fvg, ob, retest_zone)
        if z_lo is None or z_hi is None:
            return "not_retesting"
        z_lo, z_hi = float(z_lo), float(z_hi)

        cur_close = float(df["close"].iloc[-1])
        cur_low = float(df["low"].iloc[-1])

        window = df.iloc[-_BRT_OVERLAP_WINDOW_BARS:]
        overlap_bars = int(
            ((window["low"] <= z_hi) & (window["high"] >= z_lo)).sum()
        )

        if cur_low <= z_hi and cur_close > z_hi and overlap_bars <= 2:
            return "clean_bounce"
        if z_lo <= cur_close <= z_hi:
            return "body_in_zone"
        if overlap_bars >= _BRT_OVERLAP_MIN_BARS:
            return "overlap"
        return "unclear"
    except Exception as exc:                                # noqa: BLE001
        log.warning("retest_quality_error: %s", exc)
        return "unclear"


def _brt_zone_touches(df: pd.DataFrame, z_lo: float, z_hi: float, z_idx) -> int:
    """Count bars after formation whose range entered the zone band."""
    n = len(df)
    start = min(max(int(z_idx) + 1, 0), n)
    if start >= n:
        return 0
    seg = df.iloc[start:]
    return int(((seg["low"] <= z_hi) & (seg["high"] >= z_lo)).sum())


def assess_consumption_risk(
    df: pd.DataFrame,
    fvg: dict | None,
    ob: dict | None,
    retest_zone,
) -> str:
    """Measure potential zone depletion from repeated tests. Evidence only.

    Labels:
      unknown  — no zone present
      low      — 0-1 zone touches since formation
      moderate — 2 touches, or 3+ touches after price expanded away from the zone
      high     — 3+ touches with no expansion (liquidity being consumed)

    DAILY-BAR LIMITATION: true order-depletion analysis needs intraday volume at
    level. This is a conservative touch-count proxy.
    """
    try:
        z_lo, z_hi, z_idx = _brt_active_zone(fvg, ob, retest_zone)
        if z_lo is None or z_hi is None or z_idx is None:
            return "unknown"
        z_lo, z_hi = float(z_lo), float(z_hi)

        touches = _brt_zone_touches(df, z_lo, z_hi, z_idx)

        cur_close = float(df["close"].iloc[-1])
        expanded = z_hi > 0 and cur_close > z_hi * (1 + _BRT_EXPANSION_PCT / 100)

        if touches >= _BRT_CONSUMPTION_HIGH_TOUCHES:
            return "moderate" if expanded else "high"
        if touches >= _BRT_CONSUMPTION_MOD_TOUCHES:
            return "moderate"
        return "low"
    except Exception as exc:                                # noqa: BLE001
        log.warning("consumption_risk_error: %s", exc)
        return "unknown"


def assess_level_authority(
    structure_level,
    fvg: dict | None,
    ob: dict | None,
    swings: dict,
    retest_zone,
) -> str:
    """Measure structural importance of the level. Evidence only.

    Authority reflects how many swing points cluster around the reference level
    (the broken structural level, or the zone core when no structure level set).

    Labels:
      strong   — 3+ nearby swing points (well-established level)
      moderate — 2 nearby swing points
      weak     — reference level exists with <2 nearby swings
      unknown  — no reference level at all

    Authority is independent of freshness — a historically important level can
    already be consumed.
    """
    try:
        ref = None
        if structure_level is not None:
            ref = float(structure_level)
        else:
            z_lo, z_hi, _ = _brt_active_zone(fvg, ob, retest_zone)
            if z_lo is not None and z_hi is not None:
                ref = (float(z_lo) + float(z_hi)) / 2.0
        if ref is None or ref <= 0:
            return "unknown"

        tol = ref * (_BRT_AUTHORITY_TOL_PCT / 100)
        prices = [p for _, p in (swings.get("swing_highs") or [])]
        prices += [p for _, p in (swings.get("swing_lows") or [])]
        nearby = sum(1 for p in prices if abs(float(p) - ref) <= tol)

        if nearby >= _BRT_AUTHORITY_STRONG_SWINGS:
            return "strong"
        if nearby == 2:
            return "moderate"
        return "weak"
    except Exception as exc:                                # noqa: BLE001
        log.warning("level_authority_error: %s", exc)
        return "unknown"


def assess_zone_freshness(
    df: pd.DataFrame,
    fvg: dict | None,
    ob: dict | None,
    retest_zone,
) -> str:
    """Measure lifecycle status of the zone. Evidence only.

    Labels:
      fresh    — young zone (<= 10 bars old) with at most one touch
      tested   — zone has had moderate interaction but is still intact
      consumed — zone touched 3+ times (heavily worked)
      unknown  — no zone present

    Freshness and authority are separate concepts: strong does not mean fresh.
    """
    try:
        z_lo, z_hi, z_idx = _brt_active_zone(fvg, ob, retest_zone)
        if z_lo is None or z_hi is None or z_idx is None:
            return "unknown"
        z_lo, z_hi = float(z_lo), float(z_hi)

        age = (len(df) - 1) - int(z_idx)
        touches = _brt_zone_touches(df, z_lo, z_hi, z_idx)

        if touches >= _BRT_CONSUMPTION_HIGH_TOUCHES:
            return "consumed"
        if age <= _BRT_ZONE_FRESH_MAX_AGE_BARS and touches <= 1:
            return "fresh"
        return "tested"
    except Exception as exc:                                # noqa: BLE001
        log.warning("zone_freshness_error: %s", exc)
        return "unknown"


def classify_break_retest_state(
    structure_event: str,
    retest_status: str,
    hold_status: str | None = None,
    acceptance: str | None = None,
) -> str:
    """Position within the Break & Retest doctrine sequence. Evidence only.

    Sequence: Context -> Level -> Break/Reclaim -> Acceptance -> Retest -> Hold
              -> Trigger -> Expansion.

    Scanner-determinable states (from sovereign structure_event + retest_status):
      awaiting_break  — no structural break yet
      break_confirmed — break/reclaim present, retest not yet underway
      retesting       — price interacting with the zone (partial/confirmed retest)
      failed          — retest failed or acceptance invalidated

    Hold/trigger states require hold_status (Claude) and acceptance (tiering) and
    are reachable only when those are supplied. In Phase 1C-P1 enrich() supplies
    scanner data only, so the function emits the scanner-view sequence position:
      hold_confirmed  — retest confirmed and hold confirmed (future-wired)
      trigger_pending — hold confirmed, entry not yet accepted (future-wired)
      active_entry    — hold confirmed, entry accepted (future-wired)
      unknown         — insufficient data
    """
    try:
        se = str(structure_event or "none").lower()
        rs = str(retest_status or "missing").lower()
        hs = str(hold_status or "").lower()
        ac = str(acceptance or "").lower()

        if rs == "failed" or ac == "invalidated":
            return "failed"

        # Hold/trigger/active states require explicit hold + acceptance inputs.
        if hs == "confirmed" and rs == "confirmed":
            if ac == "accepted":
                return "active_entry"
            if ac in ("unproven", "damaging", "unknown", ""):
                return "trigger_pending" if ac else "hold_confirmed"
            return "hold_confirmed"

        if rs in ("confirmed", "partial"):
            return "retesting"

        broke = se in (
            "bos", "mss", "reclaim", "accepted_break", "failed_breakdown_reclaim"
        )
        if broke:
            return "break_confirmed"
        if se == "none":
            return "awaiting_break"
        return "unknown"
    except Exception as exc:                                # noqa: BLE001
        log.warning("break_retest_state_error: %s", exc)
        return "unknown"


# ---------------------------------------------------------------------------
# Phase 1D: Market Structure State — evidence-capture engine
# ---------------------------------------------------------------------------
# Single field: market_structure_state.  Pure observation of the current
# auction context.  Never read by any gate, scoring function, calibration
# step, routing decision, capital authorisation, dedup logic, campaign
# identity, or alert formatter.  Flows enrich() → prefilter key_features →
# tiering final_signal → state_store alert_history for future backtesting.


def classify_market_structure_state(
    structure_event: str | None,
    sweep_detected: bool,
    retest_status: str | None,
    sma_value_alignment: str | None,
    overhead_status: str | None,
) -> str:
    """Classify current auction state.

    Returns one of:
      EXPANSION | ORDERLY_CONTINUATION | COMPRESSION |
      REPAIR | TRANSITION | FAILURE | UNKNOWN

    Pure observation. Never referenced by any gate, score, routing,
    capital, or alert-formatting path.
    """
    try:
        se  = str(structure_event or "").upper()
        rs  = str(retest_status or "").lower()
        sva = str(sma_value_alignment or "").lower()
        oh  = str(overhead_status or "").lower()
        sw  = bool(sweep_detected)

        # 1 — FAILURE: failed retest or hostile alignment with no bullish structure
        if rs == "failed":
            return "FAILURE"
        if sva == "hostile" and se in ("CHOCH", "NONE", ""):
            return "FAILURE"

        # 2 — TRANSITION: directional structure present but conflicting context.
        # Evaluated before EXPANSION so overhead and mixed alignment are caught first.
        if se in ("MSS", "BOS", "RECLAIM", "CONTINUATION"):
            if sva in ("mixed", "hostile", "unavailable"):
                return "TRANSITION"
            if oh in ("blocked", "moderate"):
                return "TRANSITION"

        # 3 — EXPANSION: displacement with supportive alignment and no conflicts
        if se == "MSS" and sva == "supportive":
            return "EXPANSION"
        if se == "BOS" and sw and sva == "supportive":
            return "EXPANSION"

        # 4 — REPAIR: sweep without MSS confirmation, or active reclaim in progress
        if sw and se not in ("MSS",):
            return "REPAIR"
        if se == "RECLAIM":
            return "REPAIR"

        # 5 — ORDERLY_CONTINUATION: clean BOS/continuation, no sweep, supportive
        if se in ("BOS", "CONTINUATION") and sva == "supportive" and not sw and rs != "failed":
            return "ORDERLY_CONTINUATION"

        # 6 — COMPRESSION: no clear structure or unresolvable alignment
        if se in ("NONE", "") or sva in ("mixed", "unavailable"):
            return "COMPRESSION"

        return "UNKNOWN"

    except Exception:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# Main enrichment entry point
# ---------------------------------------------------------------------------

def enrich(ticker: str, df: pd.DataFrame, config: dict) -> dict:
    """Compute all structure-first features for a validated ticker DataFrame.

    Returns a flat feature dict for use by prefilter and claude_client.
    No rsi, macd, bollinger_bands, or stochastic computed or included.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    swing_lookback = thresholds.get("swing_lookback_bars", 60)

    cur = round(float(df["close"].iloc[-1]), 4)

    smas = compute_smas(df)
    alignment = sma_value_alignment(cur, smas)
    extension = price_extension_from_sma20_pct(cur, smas.get("sma20"))
    atr = compute_atr(df)
    swings = compute_swings(df, swing_lookback)
    pools = compute_liquidity_pools(df, swings)
    sweep = detect_sweep(df, config)
    structure = detect_structure_event(df, sweep, config)
    fvg = detect_fvg(df, config)
    ob = detect_ob(df, config)
    retest = assess_retest(cur, fvg, ob, atr)
    overhead = assess_overhead(cur, pools, atr, config)
    targets = estimate_targets(cur, pools, structure)
    invalidation = estimate_invalidation(fvg, ob, swings)
    rr = estimate_rr(cur, targets, invalidation)
    volume = assess_volume(df, config)
    vcp = detect_vcp(df, swings, smas, config)

    # Phase 1C-P1 — Break & Retest doctrine organs (observational only).
    # Computed from scanner-authoritative daily-bar fields. break_retest_state is
    # the scanner-view sequence position (hold/acceptance states are future-wired).
    entry_family = classify_entry_family(
        structure["structure_event"], sweep["sweep_detected"],
        fvg, ob, vcp["vcp_status"], alignment, retest["retest_status"],
    )
    retest_quality = assess_retest_quality(
        df, retest["retest_status"], retest["retest_zone"], fvg, ob
    )
    consumption_risk = assess_consumption_risk(df, fvg, ob, retest["retest_zone"])
    level_authority = assess_level_authority(
        structure["structure_level"], fvg, ob, swings, retest["retest_zone"]
    )
    zone_freshness = assess_zone_freshness(df, fvg, ob, retest["retest_zone"])
    break_retest_state = classify_break_retest_state(
        structure["structure_event"], retest["retest_status"]
    )

    # Phase 1D — Market Structure State (observational only).
    market_structure_state = classify_market_structure_state(
        structure["structure_event"], sweep["sweep_detected"],
        retest["retest_status"], alignment, overhead["overhead_status"],
    )

    prev_close: float | None = None
    if len(df) >= 2:
        prev_close = round(float(df["close"].iloc[-2]), 4)

    return {
        "ticker": ticker,
        "current_price": cur,
        "current_open": round(float(df["open"].iloc[-1]), 4),
        "current_high": round(float(df["high"].iloc[-1]), 4),
        "current_low": round(float(df["low"].iloc[-1]), 4),
        "previous_close": prev_close,
        # SMA / value
        "sma20": smas["sma20"],
        "sma50": smas["sma50"],
        "sma200": smas["sma200"],
        "sma_value_alignment": alignment,
        "price_extension_from_sma20_pct": extension,
        # Structure
        "structure_event": structure["structure_event"],
        "structure_level": structure["structure_level"],
        "structure_confirmed": structure["structure_confirmed"],
        "prior_structural_high": structure["prior_structural_high"],
        "wick_only_break": structure["wick_only_break"],
        # Swing / liquidity
        "swing_highs": swings["swing_highs"],
        "swing_lows": swings["swing_lows"],
        "last_swing_high": swings["last_swing_high"],
        "last_swing_low": swings["last_swing_low"],
        "equal_highs": pools["equal_highs"],
        "equal_lows": pools["equal_lows"],
        "recent_range_high": pools["recent_range_high"],
        "recent_range_low": pools["recent_range_low"],
        "nearest_pool_above": pools["nearest_pool_above"],
        "nearest_pool_below": pools["nearest_pool_below"],
        # Sweep
        "sweep_detected": sweep["sweep_detected"],
        "sweep_low": sweep["sweep_low"],
        "prior_low": sweep["prior_low"],
        # FVG
        "fvg": fvg,
        # OB / demand
        "ob": ob,
        # Retest
        "retest_status": retest["retest_status"],
        "retest_zone": retest["retest_zone"],
        "retest_distance_atr": retest["retest_distance_atr"],
        # Overhead
        "overhead_status": overhead["overhead_status"],
        "overhead_level": overhead["overhead_level"],
        "overhead_distance_pct": overhead["overhead_distance_pct"],
        # Targets / invalidation / R:R
        "targets": targets,
        "invalidation_level": invalidation["invalidation_level"],
        "invalidation_condition": invalidation["invalidation_condition"],
        "estimated_rr": rr,
        # Volume
        "volume_ratio": volume["volume_ratio"],
        "volume_behavior": volume["volume_behavior"],
        # ATR
        "atr": atr,
        # Phase 1B — VCP evidence (observational; never read by gates/scoring/routing)
        "vcp_status":               vcp["vcp_status"],
        "vcp_prior_advance_pct":    vcp["vcp_prior_advance_pct"],
        "vcp_contractions_count":   vcp["vcp_contractions_count"],
        "vcp_range_contraction":    vcp["vcp_range_contraction"],
        "vcp_contraction_sequence": vcp["vcp_contraction_sequence"],
        "vcp_volume_dryup":         vcp["vcp_volume_dryup"],
        "vcp_volume_ratio":         vcp["vcp_volume_ratio"],
        "vcp_ma_alignment":         vcp["vcp_ma_alignment"],
        "vcp_pivot_level":          vcp["vcp_pivot_level"],
        "vcp_failure_flag":         vcp["vcp_failure_flag"],
        # Phase 1C-P1 — Break & Retest doctrine organs (observational; never read
        # by gates/scoring/routing/capital/alert formatting). one_hour_momentum_repair
        # is a deferred organ — no daily-bar proxy is permitted.
        "entry_family":             entry_family,
        "retest_quality":           retest_quality,
        "consumption_risk":         consumption_risk,
        "level_authority":          level_authority,
        "zone_freshness":           zone_freshness,
        "break_retest_state":       break_retest_state,
        "one_hour_momentum_repair": _BRT_DEFERRED_1H,
        # Phase 1D — Market Structure State (observational; never read by
        # gates/scoring/routing/capital/alert formatting).
        "market_structure_state":   market_structure_state,
    }

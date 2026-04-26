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

    return {
        "ticker": ticker,
        "current_price": cur,
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
    }

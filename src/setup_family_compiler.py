"""Deterministic setup-family evidence compiler.

Phase SFC-1 turns the four locked Chart Wizard bullish setup families into one
normalized, auditable evidence contract.  It is deliberately *not* a tiering
engine: family detection establishes state/location/proof that downstream
prefilter, Claude, 1H/4H evidence, ladder and seal may consume.  A family label
never grants capital by itself.

Locked families:
    BREAK_RETEST_CONTINUATION
    VCP_BREAK_RETEST
    SMA_CRADLE_CONTINUATION
    GAP_FILL_REVERSAL

Evidence law:
    state -> location -> event -> reaction -> acceptance -> retest -> hold

Only completed Daily bars may be passed as ``confirmed_df``.  Current price is
allowed separately as location information; it never rewrites closed-candle
proof.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd


VERSION = "SFC-1"

BREAK_RETEST_CONTINUATION = "BREAK_RETEST_CONTINUATION"
VCP_BREAK_RETEST = "VCP_BREAK_RETEST"
SMA_CRADLE_CONTINUATION = "SMA_CRADLE_CONTINUATION"
GAP_FILL_REVERSAL = "GAP_FILL_REVERSAL"
NONE = "NONE"

FAMILY_IDS = (
    BREAK_RETEST_CONTINUATION,
    VCP_BREAK_RETEST,
    SMA_CRADLE_CONTINUATION,
    GAP_FILL_REVERSAL,
)


@dataclass
class _Thresholds:
    vcp_lookback: int = 60
    vcp_min_prior_advance_pct: float = 8.0
    vcp_max_pivot_distance_pct: float = 8.0
    vcp_volume_dry_ratio: float = 0.85
    cradle_max_distance_atr: float = 1.25
    cradle_max_distance_pct: float = 3.0
    gap_lookback: int = 50
    gap_min_size_pct: float = 1.0
    gap_min_fill_pct: float = 25.0
    gap_reclaim_fill_pct: float = 50.0


def _thresholds(config: dict | None) -> _Thresholds:
    cfg = (config or {}).get("setup_families", {})
    if not isinstance(cfg, dict):
        cfg = {}
    return _Thresholds(
        vcp_lookback=int(cfg.get("vcp_lookback_bars", 60)),
        vcp_min_prior_advance_pct=float(cfg.get("vcp_min_prior_advance_pct", 8.0)),
        vcp_max_pivot_distance_pct=float(cfg.get("vcp_max_pivot_distance_pct", 8.0)),
        vcp_volume_dry_ratio=float(cfg.get("vcp_volume_dry_ratio", 0.85)),
        cradle_max_distance_atr=float(cfg.get("cradle_max_distance_atr", 1.25)),
        cradle_max_distance_pct=float(cfg.get("cradle_max_distance_pct", 3.0)),
        gap_lookback=int(cfg.get("gap_lookback_bars", 50)),
        gap_min_size_pct=float(cfg.get("gap_min_size_pct", 1.0)),
        gap_min_fill_pct=float(cfg.get("gap_min_fill_pct", 25.0)),
        gap_reclaim_fill_pct=float(cfg.get("gap_reclaim_fill_pct", 50.0)),
    )


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b) * 100.0


def _atr(df: pd.DataFrame, period: int = 14) -> float | None:
    if len(df) < period:
        return None
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    value = tr.rolling(period, min_periods=period).mean().iloc[-1]
    return None if pd.isna(value) else float(value)


def _sma(series: pd.Series, period: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(period, min_periods=period).mean()


def _slope_pct(series: pd.Series, bars: int = 5) -> float | None:
    clean = series.dropna()
    if len(clean) <= bars:
        return None
    old = _f(clean.iloc[-bars - 1])
    new = _f(clean.iloc[-1])
    return _pct(new, old)


def _first_target(base: dict) -> float | None:
    targets = base.get("targets") or []
    if not isinstance(targets, list):
        return None
    for item in targets:
        if isinstance(item, dict):
            level = _f(item.get("level"))
        else:
            level = _f(item)
        if level is not None:
            return level
    return None


def _rr(entry: float | None, invalidation: float | None, target: float | None) -> float | None:
    if entry is None or invalidation is None or target is None:
        return None
    risk = entry - invalidation
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _candidate(
    family_id: str,
    *,
    detected: bool = False,
    state: str = "INACTIVE",
    family_score: int = 0,
    watch_ready: bool = False,
    admission_ready: bool = False,
    entry_structure_valid: bool = False,
    location_valid: bool = False,
    retest_state: str = "NONE",
    invalidation_level: float | None = None,
    target_1: float | None = None,
    rr_to_t1: float | None = None,
    path_status: str = "UNKNOWN",
    blockers: list[str] | None = None,
    soft_caps: list[str] | None = None,
    metrics: dict | None = None,
) -> dict:
    return {
        "family_id": family_id,
        "detected": bool(detected),
        "state": state,
        "family_score": max(0, min(100, int(family_score))),
        "watch_ready": bool(watch_ready),
        "admission_ready": bool(admission_ready),
        "entry_structure_valid": bool(entry_structure_valid),
        "location_valid": bool(location_valid),
        "retest_state": retest_state,
        "invalidation_level": _round(invalidation_level),
        "target_1": _round(target_1),
        "rr_to_t1": _round(rr_to_t1, 2),
        "path_status": path_status,
        "blockers": list(dict.fromkeys(blockers or [])),
        "soft_caps": list(dict.fromkeys(soft_caps or [])),
        "metrics": metrics or {},
    }


def _empty(family_id: str, blocker: str = "INSUFFICIENT_CONFIRMED_DAILY_HISTORY") -> dict:
    return _candidate(family_id, blockers=[blocker])


def _break_retest(base: dict, current_price: float | None) -> dict:
    event = str(base.get("structure_event") or "none")
    retest = str(base.get("retest_status") or "missing")
    valid_events = {"BOS", "MSS", "reclaim", "accepted_break", "failed_breakdown_reclaim"}
    detected = event in valid_events

    if not detected:
        return _candidate(
            BREAK_RETEST_CONTINUATION,
            blockers=["NO_ACCEPTED_BREAK_OR_RECLAIM"],
            metrics={"structure_event": event, "retest_status": retest},
        )

    if retest == "confirmed":
        state = "RETEST_HELD"
        retest_state = "HELD"
        score = 92
    elif retest == "partial":
        state = "RETESTING"
        retest_state = "PENDING"
        score = 76
    elif retest == "failed":
        state = "FAILED"
        retest_state = "FAILED"
        score = 20
    else:
        state = "BREAK_ACCEPTED"
        retest_state = "PENDING"
        score = 66

    invalidation = _f(base.get("invalidation_level"))
    target = _first_target(base)
    rr = _rr(current_price, invalidation, target)
    path = str(base.get("overhead_status") or "unknown").upper()
    path_status = "CLEAN" if path == "CLEAR" and target is not None else (
        "BLOCKED" if path == "BLOCKED" else "PARTIAL_OR_UNKNOWN"
    )
    blockers: list[str] = []
    if retest == "failed":
        blockers.append("RETEST_FAILED")
    if path == "BLOCKED":
        blockers.append("OVERHEAD_BLOCKED")

    return _candidate(
        BREAK_RETEST_CONTINUATION,
        detected=True,
        state=state,
        family_score=score,
        watch_ready=retest != "failed",
        admission_ready=retest != "failed" and path != "BLOCKED",
        entry_structure_valid=retest == "confirmed",
        location_valid=True,
        retest_state=retest_state,
        invalidation_level=invalidation,
        target_1=target,
        rr_to_t1=rr,
        path_status=path_status,
        blockers=blockers,
        metrics={"structure_event": event, "retest_status": retest},
    )


def _local_contraction_depths(df: pd.DataFrame, lookback: int) -> list[float]:
    """Return peak-to-subsequent-trough percentage depths from confirmed bars.

    This is intentionally conservative and deterministic.  It is not the sole
    VCP test; range compression and volume contraction are evaluated separately.
    """
    work = df.iloc[-max(20, lookback):]
    highs = pd.to_numeric(work["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(work["low"], errors="coerce").to_numpy(dtype=float)
    if len(work) < 12:
        return []

    piv_hi: list[int] = []
    piv_lo: list[int] = []
    for i in range(2, len(work) - 2):
        if np.isfinite(highs[i]) and highs[i] >= np.nanmax(highs[i - 2:i + 3]):
            piv_hi.append(i)
        if np.isfinite(lows[i]) and lows[i] <= np.nanmin(lows[i - 2:i + 3]):
            piv_lo.append(i)

    depths: list[float] = []
    for hi_i in piv_hi:
        next_lows = [lo_i for lo_i in piv_lo if lo_i > hi_i]
        next_highs = [other for other in piv_hi if other > hi_i]
        if not next_lows:
            continue
        lo_i = next_lows[0]
        if next_highs and lo_i > next_highs[0]:
            continue
        peak = highs[hi_i]
        trough = lows[lo_i]
        if peak > 0 and np.isfinite(trough) and trough < peak:
            depths.append((peak - trough) / peak * 100.0)
    return depths[-4:]


def _vcp(df: pd.DataFrame, current_price: float | None, base: dict, t: _Thresholds) -> dict:
    if len(df) < 55 or current_price is None:
        return _empty(VCP_BREAK_RETEST)

    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    s20 = _f(sma20.iloc[-1])
    s50 = _f(sma50.iloc[-1])
    slope20 = _slope_pct(sma20, 5)
    slope50 = _slope_pct(sma50, 5)

    trend_sponsored = bool(
        s20 is not None and s50 is not None and current_price >= s20 >= s50
        and (slope20 is None or slope20 > 0)
        and (slope50 is None or slope50 >= -0.15)
    )

    lb = min(len(df), max(30, t.vcp_lookback))
    prior_floor = _f(low.iloc[-lb:-max(10, lb // 4)].min())
    recent_peak = _f(high.iloc[-max(15, lb // 3):].max())
    prior_advance_pct = _pct(recent_peak, prior_floor)
    prior_advance_ok = prior_advance_pct is not None and prior_advance_pct >= t.vcp_min_prior_advance_pct

    def width(n: int) -> float | None:
        if len(df) < n:
            return None
        hi = _f(high.iloc[-n:].max())
        lo = _f(low.iloc[-n:].min())
        mid = _f(close.iloc[-1])
        if hi is None or lo is None or mid is None or mid == 0:
            return None
        return (hi - lo) / abs(mid) * 100.0

    width20 = width(20)
    width10 = width(10)
    width5 = width(5)
    range_contracting = bool(
        width20 is not None and width10 is not None and width5 is not None
        and width10 <= width20 * 0.92
        and width5 <= width10 * 0.88
    )

    depths = _local_contraction_depths(df, t.vcp_lookback)
    shrinking_pairs = 0
    for a, b in zip(depths, depths[1:]):
        if b <= a * 0.92:
            shrinking_pairs += 1
    pullbacks_contracting = len(depths) >= 2 and shrinking_pairs >= len(depths) - 1

    recent_vol = _f(volume.iloc[-5:].mean())
    prior_vol = _f(volume.iloc[-25:-5].mean()) if len(volume) >= 25 else None
    volume_ratio = recent_vol / prior_vol if recent_vol is not None and prior_vol not in (None, 0) else None
    volume_contracting = volume_ratio is not None and volume_ratio <= t.vcp_volume_dry_ratio

    # Pivot is established before the newest three completed candles so a live
    # breakout/hold can be measured against pre-existing resistance.
    pivot_window = high.iloc[-30:-3]
    pivot = _f(pivot_window.max()) if not pivot_window.empty else None
    pivot_distance_pct = _pct(pivot, current_price)
    near_pivot = bool(
        pivot_distance_pct is not None
        and -3.0 <= pivot_distance_pct <= t.vcp_max_pivot_distance_pct
    )

    breakout_accepted = bool(pivot is not None and _f(close.iloc[-1]) is not None and float(close.iloc[-1]) > pivot)
    retest_held = False
    if breakout_accepted and len(df) >= 3:
        last3 = df.iloc[-3:]
        had_prior_acceptance = bool((pd.to_numeric(last3["close"], errors="coerce") > pivot).iloc[:-1].any())
        latest_low = _f(last3["low"].iloc[-1])
        latest_close = _f(last3["close"].iloc[-1])
        retest_held = bool(
            had_prior_acceptance
            and latest_low is not None and latest_close is not None
            and latest_low <= pivot * 1.01
            and latest_close >= pivot
        )

    detected = trend_sponsored and prior_advance_ok and (range_contracting or pullbacks_contracting)
    admission = detected and near_pivot

    if not detected:
        state = "INACTIVE"
    elif retest_held:
        state = "BREAKOUT_RETEST_HELD"
    elif breakout_accepted:
        state = "BREAKOUT_ACCEPTED"
    else:
        state = "FINAL_CONTRACTION"

    final_low = _f(low.iloc[-10:].min())
    if pivot is not None and current_price < pivot:
        target = pivot
    elif pivot is not None and final_low is not None:
        target = pivot + max(0.0, pivot - final_low)
    else:
        target = _first_target(base)
    rr = _rr(current_price, final_low, target)

    score = 0
    score += 28 if trend_sponsored else 0
    score += 20 if prior_advance_ok else 0
    score += 22 if range_contracting else (14 if pullbacks_contracting else 0)
    score += 12 if volume_contracting else 4
    score += 10 if near_pivot else 0
    score += 8 if breakout_accepted else 0

    blockers: list[str] = []
    if not trend_sponsored:
        blockers.append("NO_TREND_SPONSORSHIP")
    if not prior_advance_ok:
        blockers.append("NO_MEANINGFUL_PRIOR_ADVANCE")
    if not (range_contracting or pullbacks_contracting):
        blockers.append("CONTRACTION_NOT_PROVEN")
    if detected and not near_pivot:
        blockers.append("PIVOT_LOCATION_NOT_READY")

    return _candidate(
        VCP_BREAK_RETEST,
        detected=detected,
        state=state,
        family_score=score,
        watch_ready=detected,
        admission_ready=admission,
        entry_structure_valid=retest_held,
        location_valid=near_pivot,
        retest_state="HELD" if retest_held else ("PENDING" if breakout_accepted else "NOT_STARTED"),
        invalidation_level=final_low,
        target_1=target,
        rr_to_t1=rr,
        path_status="CLEAN_TO_PIVOT" if admission and current_price < (pivot or current_price) else "REQUIRES_BREAKOUT_PATH_PROOF",
        blockers=blockers,
        soft_caps=[] if volume_contracting else (["VOLUME_CONTRACTION_NOT_PROVEN"] if detected else []),
        metrics={
            "prior_advance_pct": _round(prior_advance_pct, 2),
            "contraction_depths_pct": [_round(x, 2) for x in depths],
            "range_width_20_pct": _round(width20, 2),
            "range_width_10_pct": _round(width10, 2),
            "range_width_5_pct": _round(width5, 2),
            "range_contracting": range_contracting,
            "pullbacks_contracting": pullbacks_contracting,
            "volume_ratio_5_vs_prior20": _round(volume_ratio, 3),
            "volume_contracting": volume_contracting,
            "pivot": _round(pivot),
            "pivot_distance_pct": _round(pivot_distance_pct, 2),
            "breakout_accepted": breakout_accepted,
            "retest_held": retest_held,
            "sma20_slope_5_pct": _round(slope20, 3),
            "sma50_slope_5_pct": _round(slope50, 3),
        },
    )


def _lower_wick_defense(row: pd.Series, ma_value: float | None) -> bool:
    if ma_value is None:
        return False
    o = _f(row.get("open"))
    h = _f(row.get("high"))
    l = _f(row.get("low"))
    c = _f(row.get("close"))
    if None in (o, h, l, c):
        return False
    assert o is not None and h is not None and l is not None and c is not None
    body = max(abs(c - o), (h - l) * 0.08, 1e-9)
    lower_wick = min(o, c) - l
    touched = l <= ma_value * 1.01
    reclaimed = c >= ma_value
    return bool(touched and reclaimed and lower_wick / body >= 0.8)


def _cradle(df: pd.DataFrame, current_price: float | None, base: dict, t: _Thresholds) -> dict:
    if len(df) < 55 or current_price is None:
        return _empty(SMA_CRADLE_CONTINUATION)

    close = pd.to_numeric(df["close"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    s20 = _f(sma20.iloc[-1])
    s50 = _f(sma50.iloc[-1])
    slope20 = _slope_pct(sma20, 5)
    slope50 = _slope_pct(sma50, 5)
    atr = _atr(df)

    sponsorship = bool(
        s20 is not None and s50 is not None and s20 >= s50
        and slope20 is not None and slope20 > 0
        and (slope50 is None or slope50 >= -0.10)
    )

    prior_low = _f(low.iloc[-35:-15].min()) if len(df) >= 35 else None
    prior_high = _f(high.iloc[-15:].max())
    prior_advance = _pct(prior_high, prior_low)
    impulse_ok = bool(
        prior_advance is not None and prior_advance >= 6.0
        or str(base.get("structure_event") or "none") in {"BOS", "MSS", "reclaim", "accepted_break"}
    )

    distance20 = abs(current_price - s20) if s20 is not None else None
    distance20_atr = distance20 / atr if distance20 is not None and atr not in (None, 0) else None
    distance20_pct = abs(_pct(current_price, s20) or 999.0) if s20 is not None else None
    pocket_low = min(s20, s50) if s20 is not None and s50 is not None else None
    pocket_high = max(s20, s50) if s20 is not None and s50 is not None else None

    recent_low = _f(low.iloc[-3:].min())
    touched_value = bool(
        s20 is not None and recent_low is not None
        and recent_low <= s20 * 1.015
        and (pocket_low is None or recent_low >= pocket_low * 0.965)
    )
    close_enough = bool(
        (distance20_atr is not None and distance20_atr <= t.cradle_max_distance_atr)
        or (distance20_pct is not None and distance20_pct <= t.cradle_max_distance_pct)
    )
    location_valid = sponsorship and (touched_value or close_enough)

    defensive_bar = False
    defense_index: int | None = None
    for offset in range(min(3, len(df))):
        idx = len(df) - 1 - offset
        ma = _f(sma20.iloc[idx])
        if _lower_wick_defense(df.iloc[idx], ma):
            defensive_bar = True
            defense_index = idx
            break

    latest_close = _f(close.iloc[-1])
    reclaim = bool(touched_value and s20 is not None and latest_close is not None and latest_close >= s20)
    last_two = close.iloc[-2:].dropna()
    hold = bool(reclaim and s20 is not None and len(last_two) == 2 and (last_two >= s20).all())
    accepted_below_pocket = bool(
        pocket_low is not None and len(last_two) == 2 and (last_two < pocket_low).all()
    )

    detected = sponsorship and impulse_ok and location_valid
    admission = detected and not accepted_below_pocket
    entry_structure_valid = admission and reclaim and hold

    if accepted_below_pocket:
        state = "FAILED_VALUE_ACCEPTANCE"
    elif entry_structure_valid:
        state = "CRADLE_RETEST_HELD"
    elif reclaim:
        state = "VALUE_RECLAIMED"
    elif detected:
        state = "TESTING_CRADLE"
    else:
        state = "INACTIVE"

    invalidation = _f(low.iloc[-5:].min())
    target = _first_target(base)
    if target is None:
        prior_target = _f(high.iloc[-25:-3].max()) if len(df) >= 25 else None
        target = prior_target if prior_target is not None and prior_target > current_price else None
    rr = _rr(current_price, invalidation, target)

    score = 0
    score += 28 if sponsorship else 0
    score += 16 if impulse_ok else 0
    score += 20 if location_valid else 0
    score += 14 if defensive_bar else (8 if touched_value else 0)
    score += 12 if reclaim else 0
    score += 10 if hold else 0

    blockers: list[str] = []
    if not sponsorship:
        blockers.append("MA_SPONSORSHIP_NOT_RISING")
    if not impulse_ok:
        blockers.append("PRIOR_IMPULSE_NOT_PROVEN")
    if sponsorship and not location_valid:
        blockers.append("NOT_AT_CRADLE_VALUE")
    if accepted_below_pocket:
        blockers.append("ACCEPTED_BELOW_VALUE_POCKET")

    return _candidate(
        SMA_CRADLE_CONTINUATION,
        detected=detected,
        state=state,
        family_score=score,
        watch_ready=detected and not accepted_below_pocket,
        admission_ready=admission,
        entry_structure_valid=entry_structure_valid,
        location_valid=location_valid,
        retest_state="HELD" if hold else ("RECLAIMED" if reclaim else ("TESTING" if detected else "NONE")),
        invalidation_level=invalidation,
        target_1=target,
        rr_to_t1=rr,
        path_status="CLEAN" if target is not None and target > current_price else "TARGET_PROOF_REQUIRED",
        blockers=blockers,
        soft_caps=[] if defensive_bar else (["DEFENSIVE_CANDLE_NOT_PROVEN"] if detected else []),
        metrics={
            "sma20": _round(s20),
            "sma50": _round(s50),
            "sma20_slope_5_pct": _round(slope20, 3),
            "sma50_slope_5_pct": _round(slope50, 3),
            "distance_to_sma20_atr": _round(distance20_atr, 2),
            "distance_to_sma20_pct": _round(distance20_pct, 2),
            "prior_advance_pct": _round(prior_advance, 2),
            "touched_value": touched_value,
            "defensive_lower_wick": defensive_bar,
            "defense_bar_index": defense_index,
            "reclaim": reclaim,
            "hold": hold,
            "accepted_below_pocket": accepted_below_pocket,
        },
    )


def _find_recent_gap_up(df: pd.DataFrame, lookback: int, min_size_pct: float) -> dict | None:
    if len(df) < 8:
        return None
    start = max(1, len(df) - lookback)
    close = pd.to_numeric(df["close"], errors="coerce")
    open_ = pd.to_numeric(df["open"], errors="coerce")
    candidates: list[dict] = []
    for i in range(start, len(df) - 2):
        prev_close = _f(close.iloc[i - 1])
        gap_open = _f(open_.iloc[i])
        size_pct = _pct(gap_open, prev_close)
        if prev_close is None or gap_open is None or size_pct is None:
            continue
        if size_pct >= min_size_pct:
            candidates.append({
                "index": i,
                "gap_low": prev_close,
                "gap_high": gap_open,
                "gap_size_pct": size_pct,
            })
    return candidates[-1] if candidates else None


def _gap_fill(df: pd.DataFrame, current_price: float | None, base: dict, t: _Thresholds) -> dict:
    if len(df) < 20 or current_price is None:
        return _empty(GAP_FILL_REVERSAL)

    gap = _find_recent_gap_up(df, t.gap_lookback, t.gap_min_size_pct)
    if not gap:
        return _candidate(GAP_FILL_REVERSAL, blockers=["NO_RECENT_BULLISH_GAP"])

    gap_low = float(gap["gap_low"])
    gap_high = float(gap["gap_high"])
    gap_size = gap_high - gap_low
    if gap_size <= 0:
        return _candidate(GAP_FILL_REVERSAL, blockers=["INVALID_GAP_GEOMETRY"])

    recent = df.iloc[-5:]
    recent_low = _f(pd.to_numeric(recent["low"], errors="coerce").min())
    latest_close = _f(recent["close"].iloc[-1])
    fill_pct = None
    if recent_low is not None:
        fill_pct = max(0.0, min(150.0, (gap_high - recent_low) / gap_size * 100.0))

    full_fill = bool(fill_pct is not None and fill_pct >= 100.0)
    partial_fill = bool(fill_pct is not None and fill_pct >= t.gap_min_fill_pct)
    midpoint = (gap_low + gap_high) / 2.0
    reclaim_boundary = gap_low if full_fill else midpoint

    touched_boundary = bool(recent_low is not None and recent_low <= reclaim_boundary * 1.005)
    body_reclaim = bool(touched_boundary and latest_close is not None and latest_close > reclaim_boundary)
    closes2 = pd.to_numeric(recent["close"], errors="coerce").iloc[-2:]
    multi_hold = bool(body_reclaim and len(closes2) == 2 and (closes2 > reclaim_boundary).all())
    accepted_below = bool(len(closes2) == 2 and (closes2 < gap_low).all())

    detected = partial_fill
    admission = detected and not accepted_below
    entry_structure_valid = bool(
        admission and fill_pct is not None and fill_pct >= t.gap_reclaim_fill_pct and body_reclaim
    )

    if accepted_below:
        state = "FAILED_ACCEPTANCE_BELOW_GAP"
    elif multi_hold and entry_structure_valid:
        state = "GAP_RECLAIM_HELD"
    elif entry_structure_valid:
        state = "GAP_RECLAIMED"
    elif detected:
        state = "GAP_FILLING"
    else:
        state = "INACTIVE"

    invalidation = recent_low
    target = gap_high if current_price < gap_high else _first_target(base)
    if target is None:
        prior_hi = _f(pd.to_numeric(df["high"], errors="coerce").iloc[-25:-5].max()) if len(df) >= 25 else None
        target = prior_hi if prior_hi is not None and prior_hi > current_price else None
    rr = _rr(current_price, invalidation, target)

    score = 0
    score += 26 if detected else 0
    score += 16 if full_fill else (10 if partial_fill else 0)
    score += 22 if body_reclaim else 0
    score += 12 if multi_hold else 0
    score += 14 if target is not None and target > current_price else 0
    score += 10 if not accepted_below else 0

    blockers: list[str] = []
    if not partial_fill:
        blockers.append("GAP_FILL_NOT_AT_DECISION_ZONE")
    if accepted_below:
        blockers.append("ACCEPTED_BELOW_GAP_BOUNDARY")

    return _candidate(
        GAP_FILL_REVERSAL,
        detected=detected,
        state=state,
        family_score=score,
        watch_ready=detected and not accepted_below,
        admission_ready=admission,
        entry_structure_valid=entry_structure_valid,
        location_valid=detected,
        retest_state="HELD" if multi_hold else ("RECLAIMED" if body_reclaim else ("FILLING" if detected else "NONE")),
        invalidation_level=invalidation,
        target_1=target,
        rr_to_t1=rr,
        path_status="CLEAN" if target is not None and target > current_price else "TARGET_PROOF_REQUIRED",
        blockers=blockers,
        metrics={
            "gap_index": int(gap["index"]),
            "gap_low": _round(gap_low),
            "gap_high": _round(gap_high),
            "gap_size_pct": _round(float(gap["gap_size_pct"]), 2),
            "gap_fill_pct": _round(fill_pct, 2),
            "full_fill": full_fill,
            "reclaim_boundary": _round(reclaim_boundary),
            "body_reclaim": body_reclaim,
            "multi_close_hold": multi_hold,
            "accepted_below_gap": accepted_below,
        },
    )


def compile_setup_families(
    confirmed_df: pd.DataFrame | None,
    current_price: float | None,
    base_features: dict | None,
    config: dict | None = None,
) -> dict:
    """Compile all locked setup families into one normalized evidence object.

    ``confirmed_df`` must contain only completed Daily bars.  ``current_price``
    is scan-moment location information. ``base_features`` is the existing
    structure-first indicator output (structure, zones, targets, invalidation,
    overhead, retest).  No family result mutates those canonical fields here.
    """
    base = base_features if isinstance(base_features, dict) else {}
    cp = _f(current_price)
    t = _thresholds(config)

    if confirmed_df is None or not isinstance(confirmed_df, pd.DataFrame):
        families = {family: _empty(family) for family in FAMILY_IDS}
    else:
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(confirmed_df.columns)) or len(confirmed_df) == 0:
            families = {family: _empty(family) for family in FAMILY_IDS}
        else:
            families = {
                BREAK_RETEST_CONTINUATION: _break_retest(base, cp),
                VCP_BREAK_RETEST: _vcp(confirmed_df, cp, base, t),
                SMA_CRADLE_CONTINUATION: _cradle(confirmed_df, cp, base, t),
                GAP_FILL_REVERSAL: _gap_fill(confirmed_df, cp, base, t),
            }

    ranked = sorted(
        families.values(),
        key=lambda item: (
            bool(item.get("admission_ready")),
            bool(item.get("watch_ready")),
            int(item.get("family_score") or 0),
            -FAMILY_IDS.index(item["family_id"]),
        ),
        reverse=True,
    )
    primary = ranked[0]["family_id"] if ranked and ranked[0].get("detected") else NONE
    primary_obj = families.get(primary) if primary != NONE else None

    return {
        "version": VERSION,
        "primary_family": primary,
        "detected_families": [
            family for family in FAMILY_IDS if families[family].get("detected")
        ],
        "watch_ready": any(bool(obj.get("watch_ready")) for obj in families.values()),
        "admission_ready": any(bool(obj.get("admission_ready")) for obj in families.values()),
        "entry_structure_valid": bool(primary_obj and primary_obj.get("entry_structure_valid")),
        "primary_state": primary_obj.get("state") if primary_obj else "NONE",
        "primary_family_score": int(primary_obj.get("family_score") or 0) if primary_obj else 0,
        "primary_invalidation_level": primary_obj.get("invalidation_level") if primary_obj else None,
        "primary_target_1": primary_obj.get("target_1") if primary_obj else None,
        "primary_rr_to_t1": primary_obj.get("rr_to_t1") if primary_obj else None,
        "families": families,
    }

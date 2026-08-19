"""VELOCITY-1A — five-session feasibility and three-barrier research contract.

The scanner constitution defines approximately +8% within five trading
sessions as an aspirational validation objective, not a promised forecast.
This module turns that objective into deterministic research evidence without
creating a new trade gate.

Two separate questions are kept separate:

1. Ex-ante feasibility: does the current snapshot appear to have enough known
   structural room and observed range capacity for the research objective?
2. Ex-post label: after a signal, which barrier was reached first — the +8%
   target, structural invalidation, or the five-session time barrier?

The ex-ante range-capacity calculation is deliberately named a proxy.  It is
not a probability and it cannot authorize or reject capital until later
chronological validation proves an authority rule.

Pure module: no network, files, model calls, scanner imports, routing, state or
side effects.
"""

from __future__ import annotations

import math
from typing import Any

VERSION = "VELOCITY-1A"
DEFAULT_TARGET_RETURN_PCT = 8.0
DEFAULT_HORIZON_SESSIONS = 5

FEASIBILITY_SUPPORTED = "SUPPORTED"
FEASIBILITY_BLOCKED_PATH = "BLOCKED_PATH"
FEASIBILITY_RANGE_STRETCHED = "RANGE_STRETCHED"
FEASIBILITY_PARTIAL = "PARTIAL_SUPPORT"
FEASIBILITY_UNKNOWN = "UNKNOWN"
FEASIBILITY_INVALID = "INVALID_DATA"

TARGET_FIRST = "TARGET_FIRST"
INVALIDATION_FIRST = "INVALIDATION_FIRST"
AMBIGUOUS_SAME_SESSION = "AMBIGUOUS_SAME_SESSION"
TIME_BARRIER = "TIME_BARRIER"
INCOMPLETE_HORIZON = "INCOMPLETE_HORIZON"
INVALID_DATA = "INVALID_DATA"

_CAPITAL_TIERS = {"SNIPE_IT", "STARTER"}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _first_target(features: dict) -> float | None:
    targets = features.get("targets") if isinstance(features, dict) else None
    if not isinstance(targets, list):
        return None
    for item in targets:
        if isinstance(item, dict):
            value = _num(item.get("level"))
            if value is None:
                value = _num(item.get("price"))
        else:
            value = _num(item)
        if value is not None:
            return value
    return None


def _reference_price(features: dict) -> tuple[float | None, str | None]:
    for key in ("entry_price", "scan_price", "current_price", "latest_close", "trigger_level"):
        value = _num(features.get(key)) if isinstance(features, dict) else None
        if value is not None and value > 0:
            return value, key
    return None, None


def build_feasibility_snapshot(
    features: dict | None,
    target_return_pct: float = DEFAULT_TARGET_RETURN_PCT,
    horizon_sessions: int = DEFAULT_HORIZON_SESSIONS,
) -> dict:
    """Build ex-ante, research-only velocity evidence from one chart snapshot.

    Known structural room is measured to the nearest supplied overhead/target
    level above price. Observed range capacity uses ``ATR / price * sessions``
    as a transparent proxy only. Missing evidence remains unknown.
    """
    f = features if isinstance(features, dict) else {}
    price, price_source = _reference_price(f)
    target_pct = _num(target_return_pct)
    try:
        sessions = int(horizon_sessions)
    except (TypeError, ValueError):
        sessions = 0

    base = {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "forecast_authority": False,
        "target_return_pct": target_pct,
        "horizon_sessions": sessions,
        "reference_price": _round(price),
        "reference_price_source": price_source,
    }

    if price is None or price <= 0 or target_pct is None or target_pct <= 0 or sessions <= 0:
        return {
            **base,
            "status": FEASIBILITY_INVALID,
            "target_price": None,
            "required_compound_daily_pct": None,
            "known_path_ceiling": None,
            "known_path_room_pct": None,
            "path_supports_target": None,
            "atr": None,
            "atr_pct": None,
            "required_move_atr": None,
            "session_atr_capacity_pct": None,
            "range_capacity_supports_target": None,
            "reason_codes": ["INVALID_REFERENCE_OR_OBJECTIVE"],
        }

    target_price = price * (1.0 + target_pct / 100.0)
    compound_daily = ((1.0 + target_pct / 100.0) ** (1.0 / sessions) - 1.0) * 100.0

    overhead = _num(f.get("overhead_level"))
    first_target = _first_target(f)
    ceilings = [v for v in (overhead, first_target) if v is not None and v > price]
    path_ceiling = min(ceilings) if ceilings else None
    path_room_pct = (
        (path_ceiling - price) / price * 100.0
        if path_ceiling is not None
        else None
    )
    path_supports = (
        path_room_pct >= target_pct if path_room_pct is not None else None
    )

    atr = _num(f.get("atr"))
    atr_pct = atr / price * 100.0 if atr is not None and atr > 0 else None
    required_move_atr = target_pct / atr_pct if atr_pct not in (None, 0) else None
    session_capacity = atr_pct * sessions if atr_pct is not None else None
    range_supports = (
        session_capacity >= target_pct if session_capacity is not None else None
    )

    reasons: list[str] = []
    if path_supports is False:
        status = FEASIBILITY_BLOCKED_PATH
        reasons.append("KNOWN_DECISION_CEILING_INSIDE_TARGET_OBJECTIVE")
    elif range_supports is False:
        status = FEASIBILITY_RANGE_STRETCHED
        reasons.append("OBSERVED_ATR_CAPACITY_PROXY_BELOW_OBJECTIVE")
    elif path_supports is True and range_supports is True:
        status = FEASIBILITY_SUPPORTED
        reasons.append("KNOWN_PATH_AND_RANGE_PROXY_SUPPORT_OBJECTIVE")
    elif path_supports is True or range_supports is True:
        status = FEASIBILITY_PARTIAL
        reasons.append("OBJECTIVE_PARTIALLY_SUPPORTED_MISSING_SECOND_PROOF")
    else:
        status = FEASIBILITY_UNKNOWN
        reasons.append("OBJECTIVE_CAPACITY_UNPROVEN")

    if path_ceiling is None:
        reasons.append("KNOWN_PATH_CEILING_UNAVAILABLE")
    if atr_pct is None:
        reasons.append("ATR_CAPACITY_UNAVAILABLE")

    return {
        **base,
        "status": status,
        "target_price": _round(target_price),
        "required_compound_daily_pct": _round(compound_daily, 3),
        "known_path_ceiling": _round(path_ceiling),
        "known_path_room_pct": _round(path_room_pct, 3),
        "path_supports_target": path_supports,
        "atr": _round(atr),
        "atr_pct": _round(atr_pct, 3),
        "required_move_atr": _round(required_move_atr, 3),
        "session_atr_capacity_pct": _round(session_capacity, 3),
        "range_capacity_supports_target": range_supports,
        "reason_codes": reasons,
    }


def _invalid_label(reason: str, *, target_pct: float | None, sessions: int) -> dict:
    return {
        "version": VERSION,
        "label": INVALID_DATA,
        "target_return_pct": target_pct,
        "horizon_sessions": sessions,
        "entry_price": None,
        "target_price": None,
        "invalidation_level": None,
        "terminal_session": None,
        "sessions_observed": 0,
        "max_favorable_excursion_pct": None,
        "max_adverse_excursion_pct": None,
        "time_barrier_close_return_pct": None,
        "reason": reason,
    }


def label_three_barrier_outcome(
    entry_price: float,
    invalidation_level: float,
    future_bars: list[dict],
    target_return_pct: float = DEFAULT_TARGET_RETURN_PCT,
    horizon_sessions: int = DEFAULT_HORIZON_SESSIONS,
) -> dict:
    """Label target / invalidation / time ordering from future Daily OHLC.

    ``future_bars`` must begin with the first completed trading session after
    the observation being labeled. A same-session touch of both price barriers
    is ambiguous because Daily OHLC cannot prove intraday ordering.

    A terminal price barrier hit is valid even if fewer than five future bars
    are supplied. If no price barrier is hit, the time-barrier label is emitted
    only when the full horizon is present; otherwise the result is incomplete.
    """
    entry = _num(entry_price)
    invalidation = _num(invalidation_level)
    target_pct = _num(target_return_pct)
    try:
        sessions = int(horizon_sessions)
    except (TypeError, ValueError):
        sessions = 0

    if (
        entry is None or entry <= 0
        or invalidation is None or invalidation >= entry
        or target_pct is None or target_pct <= 0
        or sessions <= 0
        or not isinstance(future_bars, list)
        or not future_bars
    ):
        return _invalid_label(
            "Missing/invalid entry, invalidation, objective, horizon, or future bars.",
            target_pct=target_pct,
            sessions=sessions,
        )

    bars = future_bars[:sessions]
    clean: list[dict] = []
    for i, bar in enumerate(bars):
        if not isinstance(bar, dict):
            return _invalid_label(
                f"Future bar {i} is not an object.", target_pct=target_pct, sessions=sessions
            )
        row = {key: _num(bar.get(key)) for key in ("open", "high", "low", "close")}
        if any(row[key] is None for key in row):
            return _invalid_label(
                f"Future bar {i} has non-numeric OHLC.", target_pct=target_pct, sessions=sessions
            )
        assert all(row[key] is not None for key in row)
        if row["high"] < row["low"]:
            return _invalid_label(
                f"Future bar {i} has high below low.", target_pct=target_pct, sessions=sessions
            )
        clean.append(row)

    target = entry * (1.0 + target_pct / 100.0)
    max_high = entry
    min_low = entry

    for i, bar in enumerate(clean, start=1):
        high = float(bar["high"])
        low = float(bar["low"])
        max_high = max(max_high, high)
        min_low = min(min_low, low)
        hit_target = high >= target
        hit_invalidation = low <= invalidation

        if hit_target and hit_invalidation:
            label = AMBIGUOUS_SAME_SESSION
            reason = f"Target and invalidation both touched in session {i}; ordering unknown."
        elif hit_target:
            label = TARGET_FIRST
            reason = f"+{target_pct:g}% target touched first in session {i}."
        elif hit_invalidation:
            label = INVALIDATION_FIRST
            reason = f"Structural invalidation touched first in session {i}."
        else:
            continue

        return {
            "version": VERSION,
            "label": label,
            "target_return_pct": target_pct,
            "horizon_sessions": sessions,
            "entry_price": _round(entry),
            "target_price": _round(target),
            "invalidation_level": _round(invalidation),
            "terminal_session": i,
            "sessions_observed": i,
            "max_favorable_excursion_pct": _round((max_high - entry) / entry * 100.0, 4),
            "max_adverse_excursion_pct": _round((min_low - entry) / entry * 100.0, 4),
            "time_barrier_close_return_pct": None,
            "reason": reason,
        }

    max_high = max(float(b["high"]) for b in clean)
    min_low = min(float(b["low"]) for b in clean)
    mfe = (max_high - entry) / entry * 100.0
    mae = (min_low - entry) / entry * 100.0

    if len(clean) < sessions:
        return {
            "version": VERSION,
            "label": INCOMPLETE_HORIZON,
            "target_return_pct": target_pct,
            "horizon_sessions": sessions,
            "entry_price": _round(entry),
            "target_price": _round(target),
            "invalidation_level": _round(invalidation),
            "terminal_session": None,
            "sessions_observed": len(clean),
            "max_favorable_excursion_pct": _round(mfe, 4),
            "max_adverse_excursion_pct": _round(mae, 4),
            "time_barrier_close_return_pct": None,
            "reason": "Full five-session research horizon is not yet available.",
        }

    final_close = float(clean[-1]["close"])
    close_ret = (final_close - entry) / entry * 100.0
    return {
        "version": VERSION,
        "label": TIME_BARRIER,
        "target_return_pct": target_pct,
        "horizon_sessions": sessions,
        "entry_price": _round(entry),
        "target_price": _round(target),
        "invalidation_level": _round(invalidation),
        "terminal_session": sessions,
        "sessions_observed": sessions,
        "max_favorable_excursion_pct": _round(mfe, 4),
        "max_adverse_excursion_pct": _round(mae, 4),
        "time_barrier_close_return_pct": _round(close_ret, 4),
        "reason": f"Neither price barrier was touched within {sessions} completed sessions.",
    }


def label_alert_three_barrier(
    alert: dict,
    future_bars: list[dict],
    target_return_pct: float = DEFAULT_TARGET_RETURN_PCT,
    horizon_sessions: int = DEFAULT_HORIZON_SESSIONS,
) -> dict:
    """Label one historical scanner observation without pretending every tier was capital.

    Entry reference is resolved deterministically from entry_price, scan_price,
    current_price, then trigger_level.  The chosen basis is always returned.
    ``capital_authorized_at_observation`` is metadata only and prevents a watch
    observation from being confused with an executed trade in later analysis.
    """
    a = alert if isinstance(alert, dict) else {}
    entry, basis = _reference_price(a)
    invalidation = _num(a.get("invalidation_level"))
    result = label_three_barrier_outcome(
        entry,
        invalidation,
        future_bars,
        target_return_pct=target_return_pct,
        horizon_sessions=horizon_sessions,
    )
    tier = str(a.get("final_tier") or a.get("tier") or "UNKNOWN")
    return {
        **result,
        "ticker": a.get("ticker"),
        "alert_tier": tier,
        "setup_family": a.get("setup_family") or a.get("setup_family_primary") or "UNKNOWN",
        "entry_price_source": basis,
        "capital_authorized_at_observation": tier in _CAPITAL_TIERS,
    }


def summarize_three_barrier_labels(results: list[dict]) -> dict:
    """Aggregate deterministic labels by verdict tier and setup family."""
    labels = (
        TARGET_FIRST,
        INVALIDATION_FIRST,
        AMBIGUOUS_SAME_SESSION,
        TIME_BARRIER,
        INCOMPLETE_HORIZON,
        INVALID_DATA,
    )
    counts = {label: 0 for label in labels}
    by_tier: dict[str, dict[str, int]] = {}
    by_family: dict[str, dict[str, int]] = {}

    def add(group: dict, key: str, label: str) -> None:
        if key not in group:
            group[key] = {name: 0 for name in labels}
            group[key]["total"] = 0
        group[key]["total"] += 1
        if label in group[key]:
            group[key][label] += 1

    for row in results if isinstance(results, list) else []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or INVALID_DATA)
        if label not in counts:
            label = INVALID_DATA
        counts[label] += 1
        add(by_tier, str(row.get("alert_tier") or "UNKNOWN"), label)
        add(by_family, str(row.get("setup_family") or "UNKNOWN"), label)

    completed = counts[TARGET_FIRST] + counts[INVALIDATION_FIRST] + counts[TIME_BARRIER]
    target_rate = round(counts[TARGET_FIRST] / completed * 100.0, 2) if completed else None

    return {
        "version": VERSION,
        "total": sum(counts.values()),
        "counts": counts,
        "completed_unambiguous": completed,
        "target_first_rate_completed_pct": target_rate,
        "by_tier": by_tier,
        "by_setup_family": by_family,
        "research_only": True,
    }

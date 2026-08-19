"""VELOCITY-1 — five-session / +8% validation research engine.

Pure, offline, read-only functions for the Chart Wizard research objective:

    Can an entry reach +8% before its structural invalidation within
    five subsequent trading sessions?

This module deliberately does NOT authorize, promote, downgrade, route, or
suppress a live scanner signal. It creates the forward labels needed to test
that objective chronologically before any velocity rule becomes production
capital authority.

Three barriers
--------------
1. upside target: entry_price * (1 + target_return_pct / 100)
2. structural stop: the signal's explicit invalidation_level
3. time barrier: session_limit subsequent Daily bars (default 5)

Daily OHLC cannot prove intraday ordering when target and stop are both touched
in the same session, so that case is labeled ambiguous rather than guessed.

A missing portion of the requested forward horizon is never mislabeled as a
timeout. If neither price barrier has resolved and fewer than ``session_limit``
future sessions are supplied, the result is ``INCOMPLETE_HORIZON``.

No network calls. No file writes. No live scanner imports. Standard library only.
"""

from __future__ import annotations

from typing import Any

VERSION = "VELOCITY-1"
DEFAULT_TARGET_RETURN_PCT = 8.0
DEFAULT_SESSION_LIMIT = 5

TARGET_BEFORE_STOP = "TARGET_8_BEFORE_STOP"
STOP_BEFORE_TARGET = "STOP_BEFORE_TARGET_8"
TIMEOUT = "TIMEOUT_5_SESSIONS"
AMBIGUOUS_SAME_SESSION = "AMBIGUOUS_SAME_SESSION"
INCOMPLETE_HORIZON = "INCOMPLETE_HORIZON"
INVALID_DATA = "INVALID_DATA"

ENTRY_SOURCE_EXPLICIT = "EXPLICIT_ENTRY_PRICE"
ENTRY_SOURCE_SCAN = "SCAN_PRICE"
ENTRY_SOURCE_TRIGGER = "TRIGGER_LEVEL"
ENTRY_SOURCE_CURRENT = "CURRENT_PRICE"


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _resolve_entry_price(record: dict) -> tuple[float | None, str | None]:
    """Resolve the research entry anchor without inventing a fill.

    Preference order:
    1. explicit ``entry_price`` when a replay/execution record provides it;
    2. ``scan_price`` for an alert-time research label;
    3. ``trigger_level`` as a historical fallback;
    4. ``current_price`` for raw enriched-state research snapshots.

    The source is always returned so downstream studies can stratify by anchor
    rather than silently mixing fill assumptions.
    """
    for key, source in (
        ("entry_price", ENTRY_SOURCE_EXPLICIT),
        ("scan_price", ENTRY_SOURCE_SCAN),
        ("trigger_level", ENTRY_SOURCE_TRIGGER),
        ("current_price", ENTRY_SOURCE_CURRENT),
    ):
        value = _to_float(record.get(key))
        if value is not None:
            return value, source
    return None, None


def _normalize_targets(targets: Any) -> list[float]:
    """Normalize existing mapped structural targets for research diagnostics."""
    if targets is None:
        return []
    if isinstance(targets, (int, float)) and not isinstance(targets, bool):
        value = _to_float(targets)
        return [value] if value is not None else []
    if not isinstance(targets, list):
        return []

    out: list[float] = []
    for item in targets:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            value = _to_float(item)
            if value is not None:
                out.append(value)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("level", "price", "target"):
            if key in item:
                value = _to_float(item.get(key))
                if value is not None:
                    out.append(value)
                break
    return out


def build_velocity_research_snapshot(
    record: dict,
    *,
    target_return_pct: float = DEFAULT_TARGET_RETURN_PCT,
    session_limit: int = DEFAULT_SESSION_LIMIT,
) -> dict:
    """Build non-authoritative ex-ante velocity geometry for one signal/state.

    No arbitrary ATR feasibility threshold is imposed in VELOCITY-1. The raw
    geometry is recorded so chronological replay can discover which values are
    actually useful instead of hard-coding an unvalidated cutoff.
    """
    record = record if isinstance(record, dict) else {}
    target_pct = _to_float(target_return_pct)
    if target_pct is None or target_pct <= 0:
        target_pct = DEFAULT_TARGET_RETURN_PCT
    try:
        sessions = int(session_limit)
    except (TypeError, ValueError):
        sessions = DEFAULT_SESSION_LIMIT
    if sessions <= 0:
        sessions = DEFAULT_SESSION_LIMIT

    entry, entry_source = _resolve_entry_price(record)
    stop = _to_float(record.get("invalidation_level"))
    atr = _to_float(record.get("atr"))
    mapped_targets = _normalize_targets(record.get("targets"))

    target_price = None
    structural_risk_pct = None
    rr_to_velocity_target = None
    atr_pct = None
    required_move_atr = None

    if entry is not None and entry > 0:
        target_price = entry * (1.0 + target_pct / 100.0)
        if stop is not None:
            structural_risk_pct = (entry - stop) / entry * 100.0
            if structural_risk_pct > 0:
                rr_to_velocity_target = target_pct / structural_risk_pct
        if atr is not None and atr > 0:
            atr_pct = atr / entry * 100.0
            required_move_atr = (target_price - entry) / atr

    mapped_above = sorted(x for x in mapped_targets if entry is not None and x > entry)
    nearest_mapped = mapped_above[0] if mapped_above else None
    farthest_mapped = mapped_above[-1] if mapped_above else None
    max_mapped_upside_pct = None
    mapped_target_reaches_velocity_target = None
    if entry is not None and entry > 0 and mapped_targets:
        if farthest_mapped is not None:
            max_mapped_upside_pct = (farthest_mapped - entry) / entry * 100.0
            mapped_target_reaches_velocity_target = bool(
                target_price is not None and farthest_mapped >= target_price
            )
        else:
            max_mapped_upside_pct = max(
                ((x - entry) / entry * 100.0 for x in mapped_targets),
                default=None,
            )
            mapped_target_reaches_velocity_target = False

    valid_geometry = bool(
        entry is not None
        and entry > 0
        and stop is not None
        and stop < entry
        and target_price is not None
        and target_price > entry
    )

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "target_return_pct": round(target_pct, 4),
        "session_limit": sessions,
        "entry_price": round(entry, 6) if entry is not None else None,
        "entry_price_source": entry_source,
        "velocity_target_price": round(target_price, 6) if target_price is not None else None,
        "structural_stop": round(stop, 6) if stop is not None else None,
        "structural_risk_pct": (
            round(structural_risk_pct, 6) if structural_risk_pct is not None else None
        ),
        "rr_to_velocity_target": (
            round(rr_to_velocity_target, 6)
            if rr_to_velocity_target is not None
            else None
        ),
        "atr": round(atr, 6) if atr is not None else None,
        "atr_pct": round(atr_pct, 6) if atr_pct is not None else None,
        "required_move_atr": (
            round(required_move_atr, 6) if required_move_atr is not None else None
        ),
        "mapped_targets": [round(x, 6) for x in mapped_targets],
        "nearest_mapped_target_above_entry": (
            round(nearest_mapped, 6) if nearest_mapped is not None else None
        ),
        "farthest_mapped_target_above_entry": (
            round(farthest_mapped, 6) if farthest_mapped is not None else None
        ),
        "max_mapped_upside_pct": (
            round(max_mapped_upside_pct, 6)
            if max_mapped_upside_pct is not None
            else None
        ),
        "mapped_target_reaches_velocity_target": mapped_target_reaches_velocity_target,
        "overhead_status": record.get("overhead_status"),
        "valid_geometry_for_label": valid_geometry,
    }


def _invalid_result(snapshot: dict, reason: str) -> dict:
    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "outcome_label": INVALID_DATA,
        "decisive": False,
        "target_hit": False,
        "stop_hit": False,
        "timeout": False,
        "ambiguous": False,
        "complete_horizon": False,
        "terminal_session": None,
        "target_hit_session": None,
        "stop_hit_session": None,
        "sessions_observed": 0,
        "max_favorable_excursion_pct": None,
        "max_adverse_excursion_pct": None,
        "reason": reason,
        "velocity_snapshot": snapshot,
    }


def evaluate_five_session_barriers(
    record: dict,
    future_daily_bars: list[dict],
    *,
    target_return_pct: float = DEFAULT_TARGET_RETURN_PCT,
    session_limit: int = DEFAULT_SESSION_LIMIT,
) -> dict:
    """Evaluate +8% target vs structural stop vs five-session deadline.

    ``future_daily_bars`` must be chronological and begin with the first Daily
    session after the signal/entry timestamp. Each supplied row represents one
    trading session; no calendar-day arithmetic is used.
    """
    snapshot = build_velocity_research_snapshot(
        record,
        target_return_pct=target_return_pct,
        session_limit=session_limit,
    )
    sessions = int(snapshot["session_limit"])
    entry = _to_float(snapshot.get("entry_price"))
    target = _to_float(snapshot.get("velocity_target_price"))
    stop = _to_float(snapshot.get("structural_stop"))

    if not snapshot["valid_geometry_for_label"]:
        return _invalid_result(
            snapshot,
            "Entry/target/structural-stop geometry is missing or invalid.",
        )
    if not isinstance(future_daily_bars, list) or not future_daily_bars:
        return _invalid_result(snapshot, "future_daily_bars is empty or not a list.")

    bars = future_daily_bars[:sessions]
    for index, bar in enumerate(bars, start=1):
        if not isinstance(bar, dict):
            return _invalid_result(snapshot, f"Future session {index} is not an OHLC dict.")
        for field in ("open", "high", "low", "close"):
            if _to_float(bar.get(field)) is None:
                return _invalid_result(
                    snapshot,
                    f"Non-numeric OHLC in future session {index}: {field}={bar.get(field)!r}.",
                )

    max_high = entry
    min_low = entry
    target_hit_session = None
    stop_hit_session = None

    for session_index, bar in enumerate(bars, start=1):
        high = float(bar["high"])
        low = float(bar["low"])
        max_high = max(max_high, high)
        min_low = min(min_low, low)

        hit_target = high >= target
        hit_stop = low <= stop

        if hit_target and hit_stop:
            return {
                "version": VERSION,
                "research_only": True,
                "capital_authority": False,
                "outcome_label": AMBIGUOUS_SAME_SESSION,
                "decisive": False,
                "target_hit": False,
                "stop_hit": False,
                "timeout": False,
                "ambiguous": True,
                "complete_horizon": len(bars) >= sessions,
                "terminal_session": session_index,
                "target_hit_session": session_index,
                "stop_hit_session": session_index,
                "sessions_observed": len(bars),
                "max_favorable_excursion_pct": round((max_high - entry) / entry * 100.0, 6),
                "max_adverse_excursion_pct": round((min_low - entry) / entry * 100.0, 6),
                "reason": (
                    f"Velocity target ({target:.6f}) and structural stop ({stop:.6f}) "
                    f"both touched in future session {session_index}; Daily OHLC cannot "
                    "resolve intraday ordering."
                ),
                "velocity_snapshot": snapshot,
            }

        if hit_target:
            target_hit_session = session_index
            return {
                "version": VERSION,
                "research_only": True,
                "capital_authority": False,
                "outcome_label": TARGET_BEFORE_STOP,
                "decisive": True,
                "target_hit": True,
                "stop_hit": False,
                "timeout": False,
                "ambiguous": False,
                "complete_horizon": len(bars) >= sessions,
                "terminal_session": session_index,
                "target_hit_session": target_hit_session,
                "stop_hit_session": None,
                "sessions_observed": len(bars),
                "max_favorable_excursion_pct": round((max_high - entry) / entry * 100.0, 6),
                "max_adverse_excursion_pct": round((min_low - entry) / entry * 100.0, 6),
                "reason": f"+{snapshot['target_return_pct']}% target hit before structural stop in session {session_index}.",
                "velocity_snapshot": snapshot,
            }

        if hit_stop:
            stop_hit_session = session_index
            return {
                "version": VERSION,
                "research_only": True,
                "capital_authority": False,
                "outcome_label": STOP_BEFORE_TARGET,
                "decisive": True,
                "target_hit": False,
                "stop_hit": True,
                "timeout": False,
                "ambiguous": False,
                "complete_horizon": len(bars) >= sessions,
                "terminal_session": session_index,
                "target_hit_session": None,
                "stop_hit_session": stop_hit_session,
                "sessions_observed": len(bars),
                "max_favorable_excursion_pct": round((max_high - entry) / entry * 100.0, 6),
                "max_adverse_excursion_pct": round((min_low - entry) / entry * 100.0, 6),
                "reason": f"Structural stop hit before +{snapshot['target_return_pct']}% target in session {session_index}.",
                "velocity_snapshot": snapshot,
            }

    mfe_pct = round((max_high - entry) / entry * 100.0, 6)
    mae_pct = round((min_low - entry) / entry * 100.0, 6)

    if len(bars) < sessions:
        return {
            "version": VERSION,
            "research_only": True,
            "capital_authority": False,
            "outcome_label": INCOMPLETE_HORIZON,
            "decisive": False,
            "target_hit": False,
            "stop_hit": False,
            "timeout": False,
            "ambiguous": False,
            "complete_horizon": False,
            "terminal_session": None,
            "target_hit_session": None,
            "stop_hit_session": None,
            "sessions_observed": len(bars),
            "max_favorable_excursion_pct": mfe_pct,
            "max_adverse_excursion_pct": mae_pct,
            "reason": (
                f"Only {len(bars)} of {sessions} required future trading sessions are available; "
                "deadline outcome is not yet knowable."
            ),
            "velocity_snapshot": snapshot,
        }

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "outcome_label": TIMEOUT,
        "decisive": True,
        "target_hit": False,
        "stop_hit": False,
        "timeout": True,
        "ambiguous": False,
        "complete_horizon": True,
        "terminal_session": sessions,
        "target_hit_session": None,
        "stop_hit_session": None,
        "sessions_observed": len(bars),
        "max_favorable_excursion_pct": mfe_pct,
        "max_adverse_excursion_pct": mae_pct,
        "reason": (
            f"Neither +{snapshot['target_return_pct']}% target nor structural stop was hit "
            f"within {sessions} future trading sessions."
        ),
        "velocity_snapshot": snapshot,
    }


def to_forward_outcome_block(result: dict) -> dict:
    """Convert a VELOCITY-1 result into a compact replay/telemetry outcome block.

    This shape is designed to satisfy later R4H/CAP-40 counterfactual studies
    without teaching the live scan path to look into the future.
    """
    if not isinstance(result, dict):
        return {"observed": False, "source": VERSION}

    label = result.get("outcome_label")
    observed = label not in {INVALID_DATA, INCOMPLETE_HORIZON, None}
    snapshot = result.get("velocity_snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}

    return {
        "observed": bool(observed),
        "source": VERSION,
        "outcome_label": label,
        "target_return_pct": snapshot.get("target_return_pct"),
        "session_limit": snapshot.get("session_limit"),
        "target_hit": bool(result.get("target_hit")),
        "stop_hit": bool(result.get("stop_hit")),
        "timeout": bool(result.get("timeout")),
        "ambiguous": bool(result.get("ambiguous")),
        "terminal_session": result.get("terminal_session"),
        "mfe_pct": result.get("max_favorable_excursion_pct"),
        "mae_pct": result.get("max_adverse_excursion_pct"),
    }

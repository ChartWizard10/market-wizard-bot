"""VELOCITY-1D — offline chronological observation-to-outcome linker.

VELOCITY-1C persists a compact scan-time observation beside analyzed decision
traces.  This module joins those immutable observations to completed future
Daily bars and delegates target / invalidation / time ordering to the pure
VELOCITY-1A three-barrier labeler.

The linker is deliberately OFFLINE and PURE:

* no network access;
* no market-data fetches;
* no model calls;
* no scanner/tiering/routing/state mutation;
* no file I/O;
* no trade authority.

The first eligible future session is strictly AFTER the observation's calendar
date.  This prevents the still-developing observation-day Daily candle from
leaking future information into the label.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import math
from typing import Any

from src import velocity_research

VERSION = "VELOCITY-1D"

LINK_OK = "OK"
LINK_INVALID_OBSERVATION = "INVALID_OBSERVATION"
LINK_INVALID_OBSERVATION_TIME = "INVALID_OBSERVATION_TIME"
LINK_NO_TICKER_BARS = "NO_TICKER_BARS"
LINK_BAR_DATE_CONFLICT = "BAR_DATE_CONFLICT"
LINK_DUPLICATE_OBSERVATION_CONFLICT = "DUPLICATE_OBSERVATION_CONFLICT"


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_date(value: Any) -> date | None:
    """Parse an observation/bar date without guessing missing chronology."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).date()
    except (TypeError, ValueError):
        return None


def _bar_date(bar: dict) -> date | None:
    for key in ("date", "timestamp", "time", "session_date"):
        if key in bar:
            parsed = _parse_date(bar.get(key))
            if parsed is not None:
                return parsed
    return None


def _ohlc(bar: dict) -> dict:
    return {key: _num(bar.get(key)) for key in ("open", "high", "low", "close")}


def _same_ohlc(left: dict, right: dict) -> bool:
    return all(left.get(key) == right.get(key) for key in ("open", "high", "low", "close"))


def extract_velocity_observations(ledger: dict | None) -> list[dict]:
    """Project analyzed VELOCITY-1C trace blocks into immutable link inputs."""
    data = _dict(ledger)
    traces = data.get("decision_traces")
    if not isinstance(traces, list):
        return []

    out: list[dict] = []
    for trace in traces:
        if not isinstance(trace, dict) or trace.get("trace_kind") != "analyzed":
            continue
        block = trace.get("velocity_observation")
        if not isinstance(block, dict):
            continue
        out.append({
            "version": VERSION,
            "research_only": True,
            "capital_authority": False,
            "tier_authority": False,
            "scan_id": _text(trace.get("scan_id")),
            "ticker": _text(trace.get("ticker")),
            "observed_at": _text(block.get("observed_at")),
            "persistence_ready": block.get("ready") is True,
            "entry_price": _num(block.get("reference_price")),
            "entry_price_source": _text(block.get("reference_source")),
            "invalidation_level": _num(block.get("invalidation_level")),
            "target_return_pct": _num(block.get("target_return_pct")),
            "horizon_sessions": _num(block.get("horizon_sessions")),
            "feasibility_status": _text(block.get("feasibility_status")),
            "known_path_room_pct": _num(block.get("known_path_room_pct")),
            "atr_pct": _num(block.get("atr_pct")),
            "required_move_atr": _num(block.get("required_move_atr")),
            "final_tier": _text(block.get("final_tier")),
            "capital_authorized_at_observation": (
                block.get("capital_authorized_at_observation") is True
            ),
            "setup_family": _text(block.get("primary_family")),
            "four_hour_state": _text(block.get("four_hour_state")),
            "four_hour_proxy_state": _text(block.get("four_hour_proxy_state")),
            "four_hour_proxy_agreement": _text(block.get("four_hour_proxy_agreement")),
        })
    return out


def select_future_daily_sessions(
    observed_at: Any,
    raw_bars: list | None,
    horizon_sessions: int,
) -> dict:
    """Select chronological completed Daily sessions strictly after observation day.

    Duplicate rows for the same session are tolerated only when OHLC is
    identical.  Conflicting duplicate Daily rows are not guessed through.
    Malformed-date rows are counted and ignored because their chronological
    position cannot be proven.
    """
    observed_date = _parse_date(observed_at)
    if observed_date is None:
        return {
            "status": LINK_INVALID_OBSERVATION_TIME,
            "bars": [],
            "session_dates": [],
            "available_future_sessions": 0,
            "malformed_date_rows": 0,
            "duplicate_identical_rows": 0,
        }

    try:
        horizon = int(horizon_sessions)
    except (TypeError, ValueError, OverflowError):
        horizon = 0
    if horizon <= 0:
        return {
            "status": LINK_INVALID_OBSERVATION,
            "bars": [],
            "session_dates": [],
            "available_future_sessions": 0,
            "malformed_date_rows": 0,
            "duplicate_identical_rows": 0,
        }

    if not isinstance(raw_bars, list):
        return {
            "status": LINK_NO_TICKER_BARS,
            "bars": [],
            "session_dates": [],
            "available_future_sessions": 0,
            "malformed_date_rows": 0,
            "duplicate_identical_rows": 0,
        }

    by_date: dict[date, dict] = {}
    malformed = 0
    duplicate_identical = 0
    for raw in raw_bars:
        if not isinstance(raw, dict):
            malformed += 1
            continue
        session_date = _bar_date(raw)
        if session_date is None:
            malformed += 1
            continue
        if session_date <= observed_date:
            continue
        row = _ohlc(raw)
        prior = by_date.get(session_date)
        if prior is not None:
            if not _same_ohlc(prior, row):
                return {
                    "status": LINK_BAR_DATE_CONFLICT,
                    "bars": [],
                    "session_dates": [],
                    "available_future_sessions": len(by_date),
                    "malformed_date_rows": malformed,
                    "duplicate_identical_rows": duplicate_identical,
                    "conflict_date": session_date.isoformat(),
                }
            duplicate_identical += 1
            continue
        by_date[session_date] = row

    ordered_dates = sorted(by_date)
    selected_dates = ordered_dates[:horizon]
    return {
        "status": LINK_OK if ordered_dates else LINK_NO_TICKER_BARS,
        "bars": [by_date[d] for d in selected_dates],
        "session_dates": [d.isoformat() for d in selected_dates],
        "available_future_sessions": len(ordered_dates),
        "malformed_date_rows": malformed,
        "duplicate_identical_rows": duplicate_identical,
    }


def _invalid_outcome(reason: str, observation: dict) -> dict:
    try:
        sessions = int(observation.get("horizon_sessions") or 0)
    except (TypeError, ValueError, OverflowError):
        sessions = 0
    return {
        "version": velocity_research.VERSION,
        "label": velocity_research.INVALID_DATA,
        "target_return_pct": _num(observation.get("target_return_pct")),
        "horizon_sessions": sessions,
        "entry_price": _num(observation.get("entry_price")),
        "target_price": None,
        "invalidation_level": _num(observation.get("invalidation_level")),
        "terminal_session": None,
        "sessions_observed": 0,
        "max_favorable_excursion_pct": None,
        "max_adverse_excursion_pct": None,
        "time_barrier_close_return_pct": None,
        "reason": reason,
    }


def link_observation_to_future(
    observation: dict | None,
    raw_bars: list | None,
) -> dict:
    """Join one immutable observation to future Daily bars and label outcome."""
    obs = deepcopy(observation) if isinstance(observation, dict) else {}
    ticker = _text(obs.get("ticker"))
    scan_id = _text(obs.get("scan_id"))
    observed_at = _text(obs.get("observed_at"))
    entry = _num(obs.get("entry_price"))
    invalidation = _num(obs.get("invalidation_level"))
    target_pct = _num(obs.get("target_return_pct"))
    try:
        horizon = int(obs.get("horizon_sessions") or 0)
    except (TypeError, ValueError, OverflowError):
        horizon = 0

    identity_ok = bool(ticker and scan_id and observed_at)
    geometry_ok = bool(
        obs.get("persistence_ready") is True
        and entry is not None and entry > 0
        and invalidation is not None and invalidation < entry
        and target_pct is not None and target_pct > 0
        and horizon > 0
    )

    selection = select_future_daily_sessions(observed_at, raw_bars, horizon)
    if not identity_ok or not geometry_ok:
        link_status = LINK_INVALID_OBSERVATION
        outcome = _invalid_outcome("Observation identity or structural geometry is incomplete.", obs)
    elif selection["status"] == LINK_BAR_DATE_CONFLICT:
        link_status = LINK_BAR_DATE_CONFLICT
        outcome = _invalid_outcome("Conflicting duplicate Daily rows prevent chronological labeling.", obs)
    elif selection["status"] == LINK_INVALID_OBSERVATION_TIME:
        link_status = LINK_INVALID_OBSERVATION_TIME
        outcome = _invalid_outcome("Observation timestamp cannot be resolved to a calendar date.", obs)
    else:
        link_status = selection["status"]
        outcome = velocity_research.label_three_barrier_outcome(
            entry,
            invalidation,
            selection["bars"],
            target_return_pct=target_pct,
            horizon_sessions=horizon,
        )

    return {
        "dataset_version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "scan_id": scan_id,
        "ticker": ticker,
        "observed_at": observed_at,
        "observation_key": f"{scan_id}:{ticker}" if scan_id and ticker else None,
        "final_tier": _text(obs.get("final_tier")),
        "alert_tier": _text(obs.get("final_tier")) or "UNKNOWN",
        "capital_authorized_at_observation": (
            obs.get("capital_authorized_at_observation") is True
        ),
        "setup_family": _text(obs.get("setup_family")) or "UNKNOWN",
        "feasibility_status": _text(obs.get("feasibility_status")),
        "known_path_room_pct": _num(obs.get("known_path_room_pct")),
        "atr_pct": _num(obs.get("atr_pct")),
        "required_move_atr": _num(obs.get("required_move_atr")),
        "four_hour_state": _text(obs.get("four_hour_state")),
        "four_hour_proxy_state": _text(obs.get("four_hour_proxy_state")),
        "four_hour_proxy_agreement": _text(obs.get("four_hour_proxy_agreement")),
        "entry_price_source": _text(obs.get("entry_price_source")),
        "link_status": link_status,
        "future_session_dates": list(selection.get("session_dates") or []),
        "available_future_sessions": selection.get("available_future_sessions", 0),
        "malformed_date_rows": selection.get("malformed_date_rows", 0),
        "duplicate_identical_rows": selection.get("duplicate_identical_rows", 0),
        **outcome,
    }


def _observation_signature(observation: dict) -> tuple:
    keys = (
        "observed_at",
        "entry_price",
        "invalidation_level",
        "target_return_pct",
        "horizon_sessions",
        "final_tier",
        "setup_family",
        "four_hour_state",
        "four_hour_proxy_state",
    )
    return tuple(observation.get(key) for key in keys)


def link_velocity_dataset(
    ledger: dict | None,
    bars_by_ticker: dict | None,
) -> dict:
    """Build a deterministic chronological VELOCITY dataset from local inputs."""
    observations = extract_velocity_observations(ledger)
    bars_map = bars_by_ticker if isinstance(bars_by_ticker, dict) else {}

    grouped: dict[tuple, list[dict]] = {}
    orphan_counter = 0
    for obs in observations:
        scan_id = obs.get("scan_id")
        ticker = obs.get("ticker")
        if scan_id and ticker:
            key = (scan_id, ticker)
        else:
            orphan_counter += 1
            key = (f"__orphan_{orphan_counter}", ticker)
        grouped.setdefault(key, []).append(obs)

    records: list[dict] = []
    duplicate_identical = 0
    duplicate_conflicts = 0
    for _, rows in grouped.items():
        first = rows[0]
        if len(rows) > 1:
            signatures = {_observation_signature(row) for row in rows}
            if len(signatures) > 1:
                duplicate_conflicts += 1
                bad = link_observation_to_future(first, [])
                bad["link_status"] = LINK_DUPLICATE_OBSERVATION_CONFLICT
                bad["label"] = velocity_research.INVALID_DATA
                bad["reason"] = "Conflicting duplicate scan/ticker observations prevent unique linkage."
                records.append(bad)
                continue
            duplicate_identical += len(rows) - 1

        ticker = first.get("ticker")
        raw_bars = bars_map.get(ticker, []) if ticker else []
        records.append(link_observation_to_future(first, raw_bars))

    records.sort(key=lambda r: (
        str(r.get("observed_at") or ""),
        str(r.get("ticker") or ""),
        str(r.get("scan_id") or ""),
    ))

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "observation_count_raw": len(observations),
        "observation_count_unique": len(records),
        "duplicate_identical_observations_deduped": duplicate_identical,
        "duplicate_observation_conflicts": duplicate_conflicts,
        "records": records,
        "summary": summarize_linked_dataset(records),
    }


def summarize_linked_dataset(records: list[dict] | None) -> dict:
    """Summarize labels and attribution without converting outcomes to authority."""
    rows = [r for r in (records or []) if isinstance(r, dict)]
    label_counts: dict[str, int] = {}
    link_status_counts: dict[str, int] = {}
    by_tier: dict[str, dict[str, int]] = {}
    by_family: dict[str, dict[str, int]] = {}
    by_feasibility: dict[str, dict[str, int]] = {}
    by_four_hour_state: dict[str, dict[str, int]] = {}
    by_proxy_agreement: dict[str, dict[str, int]] = {}
    capital_authorized = 0
    watch_observations = 0

    def _add(group: dict, key: str, label: str) -> None:
        bucket = group.setdefault(key, {})
        bucket[label] = bucket.get(label, 0) + 1

    for row in rows:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        status = str(row.get("link_status") or "UNKNOWN")
        label_counts[label] = label_counts.get(label, 0) + 1
        link_status_counts[status] = link_status_counts.get(status, 0) + 1
        _add(by_tier, str(row.get("final_tier") or "UNKNOWN"), label)
        _add(by_family, str(row.get("setup_family") or "UNKNOWN"), label)
        _add(by_feasibility, str(row.get("feasibility_status") or "UNKNOWN"), label)
        _add(by_four_hour_state, str(row.get("four_hour_state") or "UNKNOWN"), label)
        _add(by_proxy_agreement, str(row.get("four_hour_proxy_agreement") or "UNKNOWN"), label)
        if row.get("capital_authorized_at_observation") is True:
            capital_authorized += 1
        else:
            watch_observations += 1

    decisive = (
        label_counts.get(velocity_research.TARGET_FIRST, 0)
        + label_counts.get(velocity_research.INVALIDATION_FIRST, 0)
    )
    target_first = label_counts.get(velocity_research.TARGET_FIRST, 0)
    target_first_rate = round(target_first / decisive * 100.0, 4) if decisive else None

    return {
        "total_records": len(rows),
        "capital_authorized_observations": capital_authorized,
        "watch_or_no_capital_observations": watch_observations,
        "label_counts": label_counts,
        "link_status_counts": link_status_counts,
        "decisive_price_barrier_outcomes": decisive,
        "target_first_rate_decisive_pct": target_first_rate,
        "by_tier": by_tier,
        "by_setup_family": by_family,
        "by_feasibility_status": by_feasibility,
        "by_four_hour_state": by_four_hour_state,
        "by_four_hour_proxy_agreement": by_proxy_agreement,
    }

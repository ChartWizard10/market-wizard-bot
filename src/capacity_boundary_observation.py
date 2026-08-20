"""CAP-40A — pre-model candidate-cap boundary observation contract.

Production currently admits at most 30 deep-analysis candidates per scan. A
possible move to 40 must be measured rather than assumed. This module creates a
compact, research-only observation from facts that already exist BEFORE the
model call so ranks 21-30 and 31-40 can later be compared on the same basis.

The two canonical bands are:

* BASELINE_EDGE: the last 10 candidates inside the current cap;
* SHADOW_INCREMENT: the next 10 eligible candidates that a cap of 40 would add.

No model call is added. No rank is promoted. No tier, capital, routing,
suppression, candidate-cap or forecast authority is introduced.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src import velocity_research

VERSION = "CAP-40A"

BAND_BASELINE_EDGE = "BASELINE_EDGE"
BAND_SHADOW_INCREMENT = "SHADOW_INCREMENT"
BAND_OUTSIDE = "OUTSIDE_STUDY_BAND"

DEFAULT_CURRENT_CAP = 30
DEFAULT_INCREMENT = 10
DEFAULT_BASELINE_WIDTH = 10

_COMPACT_TEXT = 160
_COMPACT_LIST = 8


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _compact_text(value: Any) -> str | None:
    text = _text(value)
    return text[:_COMPACT_TEXT] if text else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def study_band(
    rank: Any,
    current_cap: int = DEFAULT_CURRENT_CAP,
    increment: int = DEFAULT_INCREMENT,
    baseline_width: int = DEFAULT_BASELINE_WIDTH,
) -> str:
    """Return the cap-boundary study band for a 1-based prefilter rank."""
    try:
        r = int(rank)
        cap = int(current_cap)
        inc = int(increment)
        width = int(baseline_width)
    except (TypeError, ValueError, OverflowError):
        return BAND_OUTSIDE
    if r <= 0 or cap <= 0 or inc <= 0 or width <= 0:
        return BAND_OUTSIDE
    baseline_start = max(1, cap - width + 1)
    if baseline_start <= r <= cap:
        return BAND_BASELINE_EDGE
    if cap < r <= cap + inc:
        return BAND_SHADOW_INCREMENT
    return BAND_OUTSIDE


def _reference_price(enriched: dict) -> tuple[float | None, str | None]:
    for key in ("current_price", "latest_close", "close"):
        value = _num(enriched.get(key))
        if value is not None and value > 0:
            return value, key
    return None, None


def _invalidation(
    result: dict,
    enriched: dict,
    price: float | None,
) -> tuple[float | None, str | None]:
    """Resolve a pre-model structural invalidation without inventing geometry."""
    if price is None or price <= 0:
        return None, None

    key_features = _dict(result.get("key_features"))
    family_level = _num(key_features.get("setup_family_invalidation"))
    if family_level is not None and 0 < family_level < price:
        return family_level, "setup_family_invalidation"

    family = _dict(enriched.get("setup_family_evidence"))
    family_level = _num(family.get("primary_invalidation_level"))
    if family_level is not None and 0 < family_level < price:
        return family_level, "setup_family_evidence.primary_invalidation_level"

    generic_level = _num(enriched.get("invalidation_level"))
    if generic_level is not None and 0 < generic_level < price:
        return generic_level, "invalidation_level"

    return None, None


def build_boundary_observation(
    scan_timestamp: str | None,
    rank: Any,
    result: dict | None,
    enriched: dict | None,
    *,
    scan_id: str | None = None,
    current_cap: int = DEFAULT_CURRENT_CAP,
    increment: int = DEFAULT_INCREMENT,
    baseline_width: int = DEFAULT_BASELINE_WIDTH,
    target_return_pct: float = velocity_research.DEFAULT_TARGET_RETURN_PCT,
    horizon_sessions: int = velocity_research.DEFAULT_HORIZON_SESSIONS,
) -> dict | None:
    """Build one comparable pre-model capacity-boundary research observation.

    Returns ``None`` outside the declared boundary bands so telemetry does not
    grow for candidates irrelevant to the 30-vs-40 decision. Stable scan/ticker
    identity is persisted when available because later chronological linking
    must never join rows by rank alone.
    """
    r = deepcopy(result) if isinstance(result, dict) else {}
    e = deepcopy(enriched) if isinstance(enriched, dict) else {}

    band = study_band(rank, current_cap, increment, baseline_width)
    if band == BAND_OUTSIDE:
        return None

    try:
        rank_i = int(rank)
        cap_i = int(current_cap)
        increment_i = int(increment)
    except (TypeError, ValueError, OverflowError):
        return None

    observation_id = _text(scan_id)
    ticker = _text(r.get("ticker")) or _text(e.get("ticker"))
    observed_at = _text(scan_timestamp)
    price, price_source = _reference_price(e)
    invalidation, invalidation_source = _invalidation(r, e, price)
    feasibility = velocity_research.build_feasibility_snapshot(
        e,
        target_return_pct=target_return_pct,
        horizon_sessions=horizon_sessions,
    )

    key_features = _dict(r.get("key_features"))
    ready = bool(
        observation_id
        and ticker
        and observed_at
        and price is not None
        and price > 0
        and invalidation is not None
        and 0 < invalidation < price
    )
    missing: list[str] = []
    if not observation_id:
        missing.append("scan_id")
    if not ticker:
        missing.append("ticker")
    if not observed_at:
        missing.append("observed_at")
    if price is None or price <= 0:
        missing.append("reference_price")
    if invalidation is None:
        missing.append("invalidation_level")

    return {
        "version": VERSION,
        "research_only": True,
        "observational_only": True,
        "model_authority": False,
        "candidate_cap_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "forecast_authority": False,
        "scan_id": observation_id,
        "ticker": ticker,
        "observed_at": observed_at,
        "rank": rank_i,
        "current_cap": cap_i,
        "proposed_cap": cap_i + increment_i,
        "band": band,
        "ready": ready,
        "missing": missing,
        "reference_price": price,
        "reference_source": price_source,
        "invalidation_level": invalidation,
        "invalidation_source": invalidation_source,
        "target_return_pct": _num(target_return_pct),
        "horizon_sessions": _num(horizon_sessions),
        "feasibility_status": _text(feasibility.get("status")),
        "known_path_room_pct": _num(feasibility.get("known_path_room_pct")),
        "atr_pct": _num(feasibility.get("atr_pct")),
        "required_move_atr": _num(feasibility.get("required_move_atr")),
        "prefilter_score": _num(r.get("prefilter_score")),
        "admission_rank_score": _num(r.get("admission_rank_score")),
        "admission_source": _text(r.get("admission_source")),
        "primary_family": _text(key_features.get("setup_family_primary")),
        "family_state": _text(key_features.get("setup_family_state")),
        "family_score": _num(key_features.get("setup_family_score")),
        "family_watch_ready": key_features.get("setup_family_watch_ready") is True,
        "family_admission_ready": key_features.get("setup_family_admission_ready") is True,
        "family_entry_structure_valid": (
            key_features.get("setup_family_entry_structure_valid") is True
        ),
        "family_rr_to_t1": _num(key_features.get("setup_family_rr_to_t1")),
        "retest_status": _text(key_features.get("retest_status")),
        "overhead_status": _text(key_features.get("overhead_status")),
        "estimated_rr": _num(key_features.get("estimated_rr")),
    }


def compact_for_telemetry(observation: dict | None) -> dict | None:
    """Return the bounded, whitelisted CAP-40 observation stored in 14V traces.

    The projection is additive and carries no post-model tier or capital field.
    It is deliberately small enough to attach to existing traces rather than
    creating extra trace rows that would reduce telemetry retention.
    """
    if not isinstance(observation, dict):
        return None

    missing = observation.get("missing")
    if isinstance(missing, (list, tuple)):
        compact_missing = [
            text
            for item in list(missing)[:_COMPACT_LIST]
            if (text := _compact_text(item))
        ]
    else:
        compact_missing = []

    return {
        "version": _compact_text(observation.get("version")) or VERSION,
        "research_only": True,
        "observational_only": True,
        "model_authority": False,
        "candidate_cap_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "forecast_authority": False,
        "scan_id": _compact_text(observation.get("scan_id")),
        "ticker": _compact_text(observation.get("ticker")),
        "observed_at": _compact_text(observation.get("observed_at")),
        "rank": _num(observation.get("rank")),
        "current_cap": _num(observation.get("current_cap")),
        "proposed_cap": _num(observation.get("proposed_cap")),
        "band": _compact_text(observation.get("band")),
        "ready": observation.get("ready") is True,
        "missing": compact_missing,
        "reference_price": _num(observation.get("reference_price")),
        "reference_source": _compact_text(observation.get("reference_source")),
        "invalidation_level": _num(observation.get("invalidation_level")),
        "invalidation_source": _compact_text(observation.get("invalidation_source")),
        "target_return_pct": _num(observation.get("target_return_pct")),
        "horizon_sessions": _num(observation.get("horizon_sessions")),
        "feasibility_status": _compact_text(observation.get("feasibility_status")),
        "known_path_room_pct": _num(observation.get("known_path_room_pct")),
        "atr_pct": _num(observation.get("atr_pct")),
        "required_move_atr": _num(observation.get("required_move_atr")),
        "prefilter_score": _num(observation.get("prefilter_score")),
        "admission_rank_score": _num(observation.get("admission_rank_score")),
        "admission_source": _compact_text(observation.get("admission_source")),
        "primary_family": _compact_text(observation.get("primary_family")),
        "family_state": _compact_text(observation.get("family_state")),
        "family_score": _num(observation.get("family_score")),
        "family_watch_ready": observation.get("family_watch_ready") is True,
        "family_admission_ready": observation.get("family_admission_ready") is True,
        "family_entry_structure_valid": (
            observation.get("family_entry_structure_valid") is True
        ),
        "family_rr_to_t1": _num(observation.get("family_rr_to_t1")),
        "retest_status": _compact_text(observation.get("retest_status")),
        "overhead_status": _compact_text(observation.get("overhead_status")),
        "estimated_rr": _num(observation.get("estimated_rr")),
    }

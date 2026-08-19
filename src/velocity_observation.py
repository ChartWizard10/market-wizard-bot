"""VELOCITY-1B — scan-time research observation envelope.

VELOCITY-1A defined two pure research contracts:

* ex-ante five-session / +8% feasibility evidence; and
* ex-post target / invalidation / time-barrier labels.

VELOCITY-1B defines the immutable observation envelope that a later wiring
phase may persist beside an analyzed decision trace.  The envelope joins the
minimum facts required for chronological validation without creating a new
trade gate or mutating the production judgment object.

This module is intentionally PURE.  It performs no file writes, network calls,
model calls, state updates, routing, tiering, or capital decisions.  It never
promotes or downgrades a verdict.  Unknown evidence stays unknown.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src import velocity_research

VERSION = "VELOCITY-1B"

_CAPITAL_TIERS = {"SNIPE_IT", "STARTER"}


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
    return value if isinstance(value, str) and value else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _primary_family(features: dict) -> tuple[str | None, dict]:
    evidence = _dict(features.get("setup_family_evidence"))
    primary = _text(evidence.get("primary_family"))
    resolution = _dict(evidence.get("family_resolution"))
    return primary, resolution


def _four_hour_projection(judgment: dict) -> dict | None:
    four = _dict(judgment.get("four_hour_operational"))
    if not four:
        return None
    bar = _dict(four.get("bar_context"))
    comparison = _dict(four.get("proxy_comparison"))
    missing = four.get("missing_proofs")
    missing = list(missing[:6]) if isinstance(missing, list) else []
    return {
        "status": _text(four.get("status")),
        "authority_mode": _text(four.get("authority_mode")),
        "structural_state": _text(four.get("structural_state")),
        "location_state": _text(four.get("operational_location")),
        "readiness": _text(four.get("operational_readiness")),
        "last_closed_time": _text(bar.get("last_closed_4h_time")),
        "freshness_status": _text(bar.get("freshness_status")),
        "history_gap_detected": bar.get("history_gap_detected") is True,
        "confirmed_history_bars": _num(bar.get("confirmed_history_bars")),
        "proxy_state": _text(comparison.get("proxy_state")),
        "proxy_agreement": _text(comparison.get("agreement")),
        "missing_proofs": missing,
    }


def _family_projection(features: dict) -> dict:
    primary, resolution = _primary_family(features)
    secondary = resolution.get("secondary_families")
    failed = resolution.get("failed_families")
    return {
        "primary_family": primary,
        "relationship": _text(resolution.get("relationship")),
        "conflict_scope": _text(resolution.get("conflict_scope")),
        "secondary_families": list(secondary[:6]) if isinstance(secondary, list) else [],
        "failed_families": list(failed[:6]) if isinstance(failed, list) else [],
    }


def build_observation_envelope(
    scan_id: str | None,
    scan_timestamp: str | None,
    ticker: str | None,
    features: dict | None,
    judgment: dict | None,
    *,
    target_return_pct: float = velocity_research.DEFAULT_TARGET_RETURN_PCT,
    horizon_sessions: int = velocity_research.DEFAULT_HORIZON_SESSIONS,
) -> dict:
    """Build a research-only observation record from already-known facts.

    Parameters are snapshots supplied by the caller.  They are deep-copied or
    projected and are never mutated.  The returned envelope is suitable for a
    later telemetry wiring phase because it contains the scan identity,
    reference price, structural invalidation, observed verdict, setup-family
    attribution, real-4H shadow context, and VELOCITY-1A feasibility evidence.

    ``persistence_ready`` means only that the minimum geometry required for a
    later three-barrier label is present.  It is not a trade-quality verdict.
    """
    f = deepcopy(features) if isinstance(features, dict) else {}
    j = deepcopy(judgment) if isinstance(judgment, dict) else {}

    feasibility = velocity_research.build_feasibility_snapshot(
        f,
        target_return_pct=target_return_pct,
        horizon_sessions=horizon_sessions,
    )

    signal = _dict(j.get("final_signal"))
    invalidation = _num(signal.get("invalidation_level"))
    if invalidation is None:
        invalidation = _num(j.get("invalidation_level"))

    final_tier = _text(j.get("final_tier"))
    capital_action = _text(j.get("capital_action"))
    reference_price = _num(feasibility.get("reference_price"))
    reference_source = _text(feasibility.get("reference_price_source"))

    missing: list[str] = []
    if not _text(scan_id):
        missing.append("scan_id")
    if not _text(scan_timestamp):
        missing.append("scan_timestamp")
    if not _text(ticker):
        missing.append("ticker")
    if reference_price is None or reference_price <= 0:
        missing.append("reference_price")
    if invalidation is None:
        missing.append("invalidation_level")

    capital_authorized = final_tier in _CAPITAL_TIERS

    return {
        "version": VERSION,
        "research_only": True,
        "observational_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "routing_authority": False,
        "forecast_authority": False,
        "scan_id": _text(scan_id),
        "scan_timestamp": _text(scan_timestamp),
        "ticker": _text(ticker),
        "observation": {
            "final_tier": final_tier,
            "capital_action": capital_action,
            "score": _num(j.get("score")),
            "capital_authorized_at_observation": capital_authorized,
        },
        "geometry": {
            "reference_price": reference_price,
            "reference_price_source": reference_source,
            "invalidation_level": invalidation,
            "invalidation_condition": _text(signal.get("invalidation_condition")),
            "risk_reward": _num(signal.get("risk_reward")),
            "overhead_status": _text(signal.get("overhead_status"))
                or _text(f.get("overhead_status")),
        },
        "setup_family": _family_projection(f),
        "four_hour_shadow": _four_hour_projection(j),
        "feasibility": feasibility,
        "persistence_ready": not missing,
        "missing_required_fields": missing,
    }


def observation_to_label_input(envelope: dict | None) -> dict:
    """Project the immutable fields needed by the later outcome-linking phase.

    This function does not fetch future bars and does not produce a barrier
    outcome.  It merely makes the future linker contract explicit.
    """
    env = _dict(envelope)
    geometry = _dict(env.get("geometry"))
    feasibility = _dict(env.get("feasibility"))
    observation = _dict(env.get("observation"))
    family = _dict(env.get("setup_family"))
    four = _dict(env.get("four_hour_shadow"))

    return {
        "scan_id": _text(env.get("scan_id")),
        "scan_timestamp": _text(env.get("scan_timestamp")),
        "ticker": _text(env.get("ticker")),
        "entry_price": _num(geometry.get("reference_price")),
        "entry_price_source": _text(geometry.get("reference_price_source")),
        "invalidation_level": _num(geometry.get("invalidation_level")),
        "target_return_pct": _num(feasibility.get("target_return_pct")),
        "horizon_sessions": _num(feasibility.get("horizon_sessions")),
        "final_tier": _text(observation.get("final_tier")),
        "capital_authorized_at_observation": (
            observation.get("capital_authorized_at_observation") is True
        ),
        "setup_family": _text(family.get("primary_family")),
        "four_hour_state": _text(four.get("structural_state")),
        "four_hour_proxy_state": _text(four.get("proxy_state")),
        "four_hour_proxy_agreement": _text(four.get("proxy_agreement")),
        "persistence_ready": env.get("persistence_ready") is True,
    }

"""R4H-3A — pure real-vs-proxy 4H authority counterfactual contract.

R4H-2 held real 4H in SHADOW_EVIDENCE_ONLY because implementation truth and
proxy agreement are not forward outcome proof.  VELOCITY-1D now supplies an
offline target / invalidation / time outcome dataset.  R4H-3A defines the
minimum policy vocabulary needed to join the two without pretending that a
4H location state is a complete trade decision.

The production scanner currently gives the legacy operational proxy a specific
location role inside the ladder: hostile location is a hard failure; valid,
repairing, extended, and unknown states are distinct non-hostile conditions
whose final capital result still depends on Daily permission, 1H proof, hold,
invalidation, path, R:R, and candle truth.

The real 4H engine expresses its own location/readiness/state.  This module maps
both sources into the same LOCATION-EFFECT vocabulary and compares only the
4H layer.  It does not simulate a final tier and it does not grant real 4H any
live authority.

PURE / research-only:
  - no network or file I/O;
  - no scanner, model, tier, routing, state, or capital mutation;
  - no numeric trading threshold is introduced;
  - no proxy agreement is treated as ground truth;
  - no automatic authority handoff.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VERSION = "R4H-3A"

EFFECT_SUPPORTIVE = "SUPPORTIVE"
EFFECT_REPAIRING = "REPAIRING"
EFFECT_NO_EDGE = "NO_EDGE"
EFFECT_EXTENDED = "EXTENDED"
EFFECT_HARD_BLOCK = "HARD_BLOCK"
EFFECT_UNAVAILABLE = "UNAVAILABLE"

EFFECTS = {
    EFFECT_SUPPORTIVE,
    EFFECT_REPAIRING,
    EFFECT_NO_EDGE,
    EFFECT_EXTENDED,
    EFFECT_HARD_BLOCK,
    EFFECT_UNAVAILABLE,
}

COMPARE_SAME = "SAME_LOCATION_EFFECT"
COMPARE_REAL_ADDS_BLOCK = "REAL_ADDS_HARD_BLOCK"
COMPARE_REAL_REMOVES_BLOCK = "REAL_REMOVES_PROXY_HARD_BLOCK"
COMPARE_NON_FATAL_DIFFERENCE = "NON_FATAL_LOCATION_DIFFERENCE"
COMPARE_UNAVAILABLE = "COMPARISON_UNAVAILABLE"


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _upper(value: Any) -> str:
    return str(value or "").upper().strip()


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def proxy_location_effect(proxy_state: Any) -> dict:
    """Map the existing Phase-14F proxy location state without changing it.

    The mapping follows the production ladder's existing semantics:
    LOCATION_HOSTILE is the 4H hard-failure state.  Other states remain
    non-hostile location conditions and are not promoted into capital by this
    function.
    """
    state = _upper(proxy_state)
    mapping = {
        "LOCATION_VALID": EFFECT_SUPPORTIVE,
        "LOCATION_REPAIRING": EFFECT_REPAIRING,
        "LOCATION_EXTENDED": EFFECT_EXTENDED,
        "LOCATION_HOSTILE": EFFECT_HARD_BLOCK,
        "UNKNOWN": EFFECT_UNAVAILABLE,
        "": EFFECT_UNAVAILABLE,
    }
    effect = mapping.get(state, EFFECT_UNAVAILABLE)
    return {
        "source": "PRODUCTION_PROXY",
        "raw_state": state or "UNKNOWN",
        "location_effect": effect,
        "hard_block": effect == EFFECT_HARD_BLOCK,
        "capital_authority": False,
        "tier_authority": False,
    }


def real_location_effect(real_four_hour: dict | None) -> dict:
    """Map real-4H shadow facts into the same location-effect vocabulary.

    Only explicit R4H-1 states are used.  A closed structural FAILURE or a
    HOSTILE operational location is the real engine's hard-failure condition.
    MID_RANGE means the engine found no structural reason to act at price, but
    is kept separate from a hard structural failure.  EXTENDED is likewise a
    distinct no-chase condition, not silently converted to failure.
    """
    real = _dict(real_four_hour)
    status = _upper(real.get("status"))
    freshness = _upper(real.get("freshness_status"))
    state = _upper(real.get("structural_state"))
    location = _upper(real.get("location_state") or real.get("operational_location"))
    readiness = _upper(real.get("readiness") or real.get("operational_readiness"))

    unavailable = (
        not real
        or status in ("ERROR", "INSUFFICIENT", "STALE")
        or freshness == "STALE"
    )
    if unavailable:
        effect = EFFECT_UNAVAILABLE
    elif state == "FAILURE" or location == "HOSTILE" or readiness == "HOSTILE":
        effect = EFFECT_HARD_BLOCK
    elif location == "DEFENDABLE" or readiness == "READY_FOR_1H_PROOF":
        effect = EFFECT_SUPPORTIVE
    elif location == "REPAIRING" or readiness == "REPAIRING" or state == "REPAIR":
        effect = EFFECT_REPAIRING
    elif location == "MID_RANGE":
        effect = EFFECT_NO_EDGE
    elif location == "EXTENDED" or readiness == "EXTENDED":
        effect = EFFECT_EXTENDED
    else:
        effect = EFFECT_UNAVAILABLE

    return {
        "source": "REAL_4H_SHADOW",
        "raw_status": status or "UNKNOWN",
        "raw_structural_state": state or "UNKNOWN",
        "raw_location_state": location or "UNKNOWN",
        "raw_readiness": readiness or "UNKNOWN",
        "freshness_status": freshness or "UNKNOWN",
        "location_effect": effect,
        "hard_block": effect == EFFECT_HARD_BLOCK,
        "capital_authority": False,
        "tier_authority": False,
    }


def compare_location_policies(proxy_state: Any, real_four_hour: dict | None) -> dict:
    """Compare only the 4H location effect; never infer a final trade tier."""
    proxy = proxy_location_effect(proxy_state)
    real = real_location_effect(real_four_hour)
    p_effect = proxy["location_effect"]
    r_effect = real["location_effect"]

    if EFFECT_UNAVAILABLE in (p_effect, r_effect):
        comparison = COMPARE_UNAVAILABLE
    elif p_effect == r_effect:
        comparison = COMPARE_SAME
    elif real["hard_block"] and not proxy["hard_block"]:
        comparison = COMPARE_REAL_ADDS_BLOCK
    elif proxy["hard_block"] and not real["hard_block"]:
        comparison = COMPARE_REAL_REMOVES_BLOCK
    else:
        comparison = COMPARE_NON_FATAL_DIFFERENCE

    return {
        "version": VERSION,
        "research_only": True,
        "automatic_promotion": False,
        "capital_authority": False,
        "tier_authority": False,
        "proxy": proxy,
        "real": real,
        "comparison": comparison,
        "can_measure_hard_block_counterfactual": comparison != COMPARE_UNAVAILABLE,
        "can_reconstruct_full_tier_counterfactual": False,
        "full_tier_counterfactual_missing_inputs": [
            "complete 1H trigger/retest/hold evidence",
            "complete candle truth and trade-location evidence",
            "complete Daily/HTF permission evidence",
            "complete path/invalidation/R:R evidence at the policy decision point",
        ],
    }


def counterfactual_from_trace(trace: dict | None) -> dict:
    """Build one 4H-layer comparison from an existing analyzed decision trace."""
    row = _dict(trace)
    real = _dict(row.get("four_hour_real"))
    proxy_state = real.get("proxy_state")
    result = compare_location_policies(proxy_state, real)
    result.update({
        "scan_id": _text(row.get("scan_id")),
        "ticker": _text(row.get("ticker")),
    })
    return result


def _trace_index(ledger: dict | None) -> dict[tuple[str, str], dict]:
    data = _dict(ledger)
    traces = data.get("decision_traces")
    if not isinstance(traces, list):
        return {}
    out: dict[tuple[str, str], dict] = {}
    conflicts: set[tuple[str, str]] = set()
    for row in traces:
        if not isinstance(row, dict) or row.get("trace_kind") != "analyzed":
            continue
        scan_id = _text(row.get("scan_id"))
        ticker = _text(row.get("ticker"))
        if not scan_id or not ticker:
            continue
        key = (scan_id, ticker)
        if key in out and out[key] != row:
            conflicts.add(key)
        else:
            out[key] = row
    for key in conflicts:
        out.pop(key, None)
    return out


def attach_counterfactuals(
    ledger: dict | None,
    velocity_dataset: dict | None,
) -> dict:
    """Attach R4H-3A location comparisons to a VELOCITY-1D dataset copy.

    Records are joined by the already-stable (scan_id, ticker) observation key.
    Missing or conflicting trace evidence yields COMPARISON_UNAVAILABLE.  The
    input ledger and dataset are never mutated.
    """
    dataset = deepcopy(velocity_dataset) if isinstance(velocity_dataset, dict) else {}
    records = dataset.get("records")
    records = records if isinstance(records, list) else []
    index = _trace_index(ledger)

    joined: list[dict] = []
    matched = 0
    for raw in records:
        row = deepcopy(raw) if isinstance(raw, dict) else {}
        scan_id = _text(row.get("scan_id"))
        ticker = _text(row.get("ticker"))
        trace = index.get((scan_id, ticker)) if scan_id and ticker else None
        if trace is not None:
            matched += 1
            cf = counterfactual_from_trace(trace)
        else:
            cf = compare_location_policies(None, None)
            cf.update({"scan_id": scan_id, "ticker": ticker})
        row["four_hour_counterfactual"] = cf
        joined.append(row)

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "records": joined,
        "join_summary": {
            "velocity_records": len(records),
            "matched_analyzed_traces": matched,
            "unmatched_or_conflicted": len(records) - matched,
        },
        "comparison_summary": summarize_counterfactuals(joined),
    }


def summarize_counterfactuals(records: list[dict] | None) -> dict:
    """Count outcome evidence by 4H-layer comparison without making a claim.

    Precision/recall acceptance is deliberately NOT inferred here.  R4H-2
    requires a separately reviewed statistical plan and enough chronological
    observations before those validation flags may be set.
    """
    rows = [r for r in (records or []) if isinstance(r, dict)]
    comparison_counts: dict[str, int] = {}
    outcome_by_comparison: dict[str, dict[str, int]] = {}
    proxy_effect_counts: dict[str, int] = {}
    real_effect_counts: dict[str, int] = {}

    for row in rows:
        cf = _dict(row.get("four_hour_counterfactual"))
        comparison = str(cf.get("comparison") or COMPARE_UNAVAILABLE)
        proxy = _dict(cf.get("proxy"))
        real = _dict(cf.get("real"))
        p_effect = str(proxy.get("location_effect") or EFFECT_UNAVAILABLE)
        r_effect = str(real.get("location_effect") or EFFECT_UNAVAILABLE)
        label = str(row.get("label") or "INVALID_DATA")

        comparison_counts[comparison] = comparison_counts.get(comparison, 0) + 1
        proxy_effect_counts[p_effect] = proxy_effect_counts.get(p_effect, 0) + 1
        real_effect_counts[r_effect] = real_effect_counts.get(r_effect, 0) + 1
        bucket = outcome_by_comparison.setdefault(comparison, {})
        bucket[label] = bucket.get(label, 0) + 1

    return {
        "total_records": len(rows),
        "comparison_counts": comparison_counts,
        "proxy_location_effect_counts": proxy_effect_counts,
        "real_location_effect_counts": real_effect_counts,
        "outcome_by_comparison": outcome_by_comparison,
        "real_adds_hard_block_outcomes": outcome_by_comparison.get(
            COMPARE_REAL_ADDS_BLOCK, {}
        ),
        "real_removes_proxy_hard_block_outcomes": outcome_by_comparison.get(
            COMPARE_REAL_REMOVES_BLOCK, {}
        ),
        "full_tier_counterfactual_supported": False,
        "authority_decision": "NOT_EVALUATED",
    }

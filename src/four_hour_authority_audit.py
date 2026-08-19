"""Phase R4H-2 — evidence-gated real-4H authority decision.

R4H-1 proved that the scanner can build truthful session-aligned real 4H
operational evidence. That is necessary, but it is not sufficient to hand the
4H capital/gating authority. R4H-2 separates three different questions:

1. Is real 4H market-bar evidence technically available and healthy?
2. Is real-vs-proxy disagreement observable in scan-time telemetry?
3. Has forward, chronological outcome evidence proved that using real 4H as an
   authority improves decisions without damaging legitimate opportunity recall?

Only question 3 can justify an authority handoff. Agreement with the legacy
proxy is not a validation target: the proxy may be wrong. Synthetic unit tests
prove implementation semantics, not predictive edge. Therefore the current
production default remains SHADOW_EVIDENCE_ONLY until an explicit validation
artifact supplies outcome-linked, counterfactual, chronological evidence.

VELOCITY-1 compatibility
------------------------
A later replay may attach a compact ``forward_outcome`` block produced by the
VELOCITY-1 three-barrier engine either directly on a trace or inside
``forward_validation``. Such a block counts as forward outcome linkage only when
``observed`` is not explicitly False. Incomplete horizons therefore cannot
silently satisfy the R4H evidence requirement.

This module is PURE. It never mutates tiering, config, telemetry, or capital
state, and it never promotes 4H authority on its own.
"""

from __future__ import annotations

from typing import Any

VERSION = "R4H-2"

DECISION_HOLD_SHADOW = "HOLD_SHADOW"
DECISION_ELIGIBLE_FOR_CONTROLLED_PROMOTION = "ELIGIBLE_FOR_CONTROLLED_PROMOTION"

_REQUIRED_VALIDATION_FLAGS = (
    "chronological_out_of_sample",
    "outcome_linked",
    "counterfactual_proxy_vs_real",
    "sample_size_accepted_under_predeclared_plan",
    "market_condition_coverage_accepted",
    "real_4h_improves_or_preserves_precision",
    "real_4h_does_not_materially_damage_recall",
    "capital_integrity_regressions_green",
)


def _traces(ledger: dict | None) -> list[dict]:
    if not isinstance(ledger, dict):
        return []
    rows = ledger.get("decision_traces")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _bool(value: Any) -> bool:
    return value is True


def _observed_forward_outcome(row: dict, forward_validation: dict) -> dict | None:
    """Return a usable forward-outcome block, never an incomplete placeholder."""
    candidates = []
    direct = row.get("forward_outcome")
    if isinstance(direct, dict) and direct:
        candidates.append(direct)
    nested = forward_validation.get("forward_outcome")
    if isinstance(nested, dict) and nested:
        candidates.append(nested)

    for block in candidates:
        if block.get("observed") is False:
            continue
        if block.get("outcome_label") in (None, ""):
            continue
        return block
    return None


def summarize_shadow_evidence(ledger: dict | None) -> dict:
    """Summarize only facts already persisted by scan/replay telemetry.

    Scan-time 14V traces carry real-4H/proxy state. Forward labels and
    counterfactual policy results may be attached later by offline replay.
    Unknown/missing/incomplete fields are counted as absent, never synthesized.
    """
    rows = _traces(ledger)
    analyzed = [r for r in rows if r.get("trace_kind") == "analyzed"]
    real_rows = []
    comparable = []
    healthy = []
    stale_or_degraded = []
    gap_rows = []
    outcome_linked = []
    counterfactual = []

    for row in analyzed:
        real = row.get("four_hour_real")
        if isinstance(real, dict) and real:
            real_rows.append(row)
            if real.get("proxy_agreement") not in (None, "UNKNOWN"):
                comparable.append(row)
            status = str(real.get("status") or "").upper()
            freshness = str(real.get("freshness_status") or "").upper()
            if status == "ENABLED" and freshness not in ("STALE", "UNKNOWN", ""):
                healthy.append(row)
            if status in ("STALE", "DEGRADED", "ERROR", "INSUFFICIENT") or freshness == "STALE":
                stale_or_degraded.append(row)
            if _bool(real.get("history_gap_detected")):
                gap_rows.append(row)

        fwd = row.get("forward_validation")
        fwd = fwd if isinstance(fwd, dict) else {}
        outcome = _observed_forward_outcome(row, fwd)

        # Backward-compatible validation artifacts may not yet wrap the outcome
        # in a dedicated block. A non-empty forward_validation dict counts as
        # linked only when it is not explicitly marked observed=False.
        legacy_linked = bool(fwd) and fwd.get("observed") is not False
        if outcome is not None or legacy_linked:
            outcome_linked.append(row)

        if isinstance(fwd.get("proxy_vs_real_counterfactual"), dict):
            counterfactual.append(row)

    return {
        "decision_traces": len(rows),
        "analyzed_traces": len(analyzed),
        "real_4h_traces": len(real_rows),
        "proxy_comparable_traces": len(comparable),
        "healthy_real_4h_traces": len(healthy),
        "stale_or_degraded_real_4h_traces": len(stale_or_degraded),
        "history_gap_traces": len(gap_rows),
        "forward_outcome_linked_traces": len(outcome_linked),
        "counterfactual_proxy_vs_real_traces": len(counterfactual),
        "has_real_4h_observability": bool(real_rows),
        "has_proxy_comparison_observability": bool(comparable),
        "has_forward_outcome_linkage": bool(outcome_linked),
        "has_counterfactual_authority_evidence": bool(counterfactual),
    }


def audit_authority_readiness(
    ledger: dict | None = None,
    validation_summary: dict | None = None,
) -> dict:
    """Return the R4H-2 authority decision without changing runtime authority.

    ``validation_summary`` must come from a separately reviewed chronological
    validation artifact; this function does not infer predictive superiority
    from proxy agreement, synthetic tests, or incomplete forward horizons.
    """
    shadow = summarize_shadow_evidence(ledger)
    validation = validation_summary if isinstance(validation_summary, dict) else {}

    blockers: list[str] = []
    if not shadow["has_real_4h_observability"]:
        blockers.append("NO_PERSISTED_REAL_4H_SHADOW_SAMPLE")
    if not shadow["has_proxy_comparison_observability"]:
        blockers.append("NO_REAL_VS_PROXY_COMPARISON_SAMPLE")
    if not shadow["has_forward_outcome_linkage"]:
        blockers.append("NO_FORWARD_OUTCOME_LINKAGE")
    if not shadow["has_counterfactual_authority_evidence"]:
        blockers.append("NO_COUNTERFACTUAL_PROXY_VS_REAL_OUTCOMES")

    missing_validation = [
        flag for flag in _REQUIRED_VALIDATION_FLAGS if validation.get(flag) is not True
    ]
    blockers.extend(f"VALIDATION_MISSING:{flag}" for flag in missing_validation)

    eligible = not blockers
    decision = (
        DECISION_ELIGIBLE_FOR_CONTROLLED_PROMOTION
        if eligible
        else DECISION_HOLD_SHADOW
    )

    return {
        "version": VERSION,
        "decision": decision,
        "current_authority_mode": "SHADOW_EVIDENCE_ONLY",
        "automatic_promotion": False,
        "shadow_evidence": shadow,
        "validation_flags": {
            flag: bool(validation.get(flag) is True)
            for flag in _REQUIRED_VALIDATION_FLAGS
        },
        "blockers": blockers,
        "next_required_evidence": (
            []
            if eligible
            else [
                "link scan-time real-4H/proxy states to forward three-barrier outcomes",
                "run chronological out-of-sample proxy-vs-real counterfactual evaluation",
                "predeclare sample/market-condition/precision/recall acceptance criteria",
                "re-run full capital-integrity regressions before any authority handoff",
            ]
        ),
    }

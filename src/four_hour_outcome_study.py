"""R4H-3B — predeclared chronological real-vs-proxy 4H outcome study.

R4H-3A normalizes the production 4H proxy and the real 4H shadow engine into a
common location-effect vocabulary and joins those comparisons to VELOCITY-1D
forward outcomes. R4H-3B makes that evidence statistically executable without
creating live authority.

Core laws:

* the acceptance plan must be explicit and frozen before outcome review;
* TARGET_FIRST, INVALIDATION_FIRST and TIME_BARRIER are evaluable terminal
  outcomes for the five-session/+8% research objective;
* AMBIGUOUS_SAME_SESSION is ambiguous, INCOMPLETE_HORIZON is censored, and
  INVALID_DATA is invalid — none may be silently scored as a win or loss;
* REAL_ADDS_HARD_BLOCK and REAL_REMOVES_PROXY_HARD_BLOCK are studied as local
  4H-layer counterfactuals only, not reconstructed final STARTER/SNIPE trades;
* non-fatal real 4H states are reported separately;
* sample/completeness/effect thresholds are caller-predeclared — this module
  invents no favorable trading threshold after seeing outcomes;
* full 4H authority replacement remains unsupported because compact telemetry
  cannot reconstruct the whole decision-time ladder;
* no network, model call, file I/O, random sampling, tiering, routing or capital
  mutation occurs here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src import four_hour_counterfactual as cf
from src import velocity_research

VERSION = "R4H-3B"

PLAN_VALID = "VALID"
PLAN_INVALID = "INVALID"

STUDY_PLAN_INVALID = "PLAN_INVALID"
STUDY_SAMPLE_INSUFFICIENT = "SAMPLE_INSUFFICIENT"
STUDY_DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
STUDY_NARROW_SUPPORTIVE = "NARROW_HARD_BLOCK_EVIDENCE_SUPPORTIVE"
STUDY_NARROW_NOT_SUPPORTIVE = "NARROW_HARD_BLOCK_EVIDENCE_NOT_SUPPORTIVE"

EVALUABLE_LABELS = {
    velocity_research.TARGET_FIRST,
    velocity_research.INVALIDATION_FIRST,
    velocity_research.TIME_BARRIER,
}
AMBIGUOUS_LABELS = {velocity_research.AMBIGUOUS_SAME_SESSION}
CENSORED_LABELS = {velocity_research.INCOMPLETE_HORIZON}
INVALID_LABELS = {velocity_research.INVALID_DATA}

_SAMPLE_KEYS = (
    "min_evaluable_records",
    "min_real_adds_hard_block_evaluable",
    "min_real_removes_proxy_hard_block_evaluable",
    "max_ambiguous_or_censored_pct",
    "max_comparison_unavailable_pct",
)

_EFFECT_KEYS = (
    "max_real_adds_block_target_opportunity_cost_pct",
    "min_real_adds_block_objective_failure_protection_pct",
    "min_real_removes_block_target_recovery_pct",
    "max_real_removes_block_objective_failure_exposure_pct",
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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


def _pct(num: int | float, den: int | float) -> float | None:
    if not den:
        return None
    return round(float(num) / float(den) * 100.0, 4)


def validate_study_plan(plan: dict | None) -> dict:
    """Validate the predeclared R4H-3B sample/effect plan.

    Required sample fields are deliberately not defaulted. The project must
    choose them before examining outcomes. Effect thresholds are optional; if
    omitted, the study can become sample-ready but remains descriptive only.
    """
    p = deepcopy(plan) if isinstance(plan, dict) else {}
    name = _text(p.get("name"))
    version = _text(p.get("version"))
    errors: list[str] = []

    if not name:
        errors.append("MISSING_PLAN_NAME")
    if not version:
        errors.append("MISSING_PLAN_VERSION")
    if p.get("frozen_before_outcome_review") is not True:
        errors.append("PLAN_NOT_FROZEN_BEFORE_OUTCOME_REVIEW")
    if p.get("chronological_out_of_sample") is not True:
        errors.append("CHRONOLOGICAL_OUT_OF_SAMPLE_NOT_DECLARED")

    normalized: dict[str, float] = {}
    for key in _SAMPLE_KEYS:
        value = _num(p.get(key))
        if value is None:
            errors.append(f"MISSING_OR_INVALID:{key}")
        elif value < 0:
            errors.append(f"NEGATIVE_THRESHOLD:{key}")
        else:
            normalized[key] = value

    effects: dict[str, float] = {}
    for key in _EFFECT_KEYS:
        if key not in p:
            continue
        value = _num(p.get(key))
        if value is None or value < 0 or value > 100:
            errors.append(f"INVALID_EFFECT_THRESHOLD:{key}")
        else:
            effects[key] = value

    coverage_minimums: dict[str, float] = {}
    raw_coverage = p.get("market_condition_minimums")
    if raw_coverage is not None:
        if not isinstance(raw_coverage, dict):
            errors.append("INVALID_MARKET_CONDITION_MINIMUMS")
        else:
            for key, value in raw_coverage.items():
                label = _text(key)
                count = _num(value)
                if not label or count is None or count < 0:
                    errors.append("INVALID_MARKET_CONDITION_MINIMUM")
                    continue
                coverage_minimums[label] = count

    return {
        "contract_version": VERSION,
        "status": PLAN_VALID if not errors else PLAN_INVALID,
        "valid": not errors,
        "name": name,
        "version": version,
        "frozen_before_outcome_review": p.get("frozen_before_outcome_review") is True,
        "chronological_out_of_sample": p.get("chronological_out_of_sample") is True,
        "sample_thresholds": normalized,
        "effect_thresholds": effects,
        "market_condition_minimums": coverage_minimums,
        "errors": errors,
    }


def _counterfactual(row: dict) -> dict:
    value = row.get("four_hour_counterfactual")
    return value if isinstance(value, dict) else {}


def _label_class(label: str) -> str:
    if label in EVALUABLE_LABELS:
        return "EVALUABLE"
    if label in AMBIGUOUS_LABELS:
        return "AMBIGUOUS"
    if label in CENSORED_LABELS:
        return "CENSORED"
    if label in INVALID_LABELS:
        return "INVALID"
    return "UNRECOGNIZED"


def _terminal_outcome_counts(rows: list[dict]) -> dict:
    counts = {
        velocity_research.TARGET_FIRST: 0,
        velocity_research.INVALIDATION_FIRST: 0,
        velocity_research.TIME_BARRIER: 0,
        velocity_research.AMBIGUOUS_SAME_SESSION: 0,
        velocity_research.INCOMPLETE_HORIZON: 0,
        velocity_research.INVALID_DATA: 0,
        "UNRECOGNIZED": 0,
    }
    for row in rows:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        if label in counts:
            counts[label] += 1
        else:
            counts["UNRECOGNIZED"] += 1
    return counts


def _comparison_rows(rows: list[dict], comparison: str) -> list[dict]:
    return [
        row for row in rows
        if str(_counterfactual(row).get("comparison") or cf.COMPARE_UNAVAILABLE) == comparison
    ]


def _evaluable(rows: list[dict]) -> list[dict]:
    return [row for row in rows if str(row.get("label")) in EVALUABLE_LABELS]


def _intervention_metrics(rows: list[dict], comparison: str) -> dict:
    subset = _comparison_rows(rows, comparison)
    evaluable = _evaluable(subset)
    counts = _terminal_outcome_counts(subset)
    targets = counts[velocity_research.TARGET_FIRST]
    objective_failures = (
        counts[velocity_research.INVALIDATION_FIRST]
        + counts[velocity_research.TIME_BARRIER]
    )
    evaluable_n = len(evaluable)

    if comparison == cf.COMPARE_REAL_ADDS_BLOCK:
        interpretation = "Real 4H would add a local hard block where proxy did not."
        positive_label = "OBJECTIVE_FAILURE_PROTECTION"
        positive_count = objective_failures
        negative_label = "TARGET_OPPORTUNITY_COST"
        negative_count = targets
    elif comparison == cf.COMPARE_REAL_REMOVES_BLOCK:
        interpretation = "Real 4H would remove a proxy hard block."
        positive_label = "TARGET_RECOVERY"
        positive_count = targets
        negative_label = "OBJECTIVE_FAILURE_EXPOSURE"
        negative_count = objective_failures
    else:
        interpretation = "Non-intervention comparison."
        positive_label = "N/A"
        positive_count = 0
        negative_label = "N/A"
        negative_count = 0

    return {
        "comparison": comparison,
        "interpretation": interpretation,
        "total_rows": len(subset),
        "evaluable_rows": evaluable_n,
        "outcome_counts": counts,
        "target_first": targets,
        "objective_failures": objective_failures,
        "positive_evidence_label": positive_label,
        "positive_evidence_count": positive_count,
        "positive_evidence_pct": _pct(positive_count, evaluable_n),
        "negative_evidence_label": negative_label,
        "negative_evidence_count": negative_count,
        "negative_evidence_pct": _pct(negative_count, evaluable_n),
    }


def _nonfatal_real_effects(rows: list[dict]) -> dict:
    effects = (
        cf.EFFECT_SUPPORTIVE,
        cf.EFFECT_REPAIRING,
        cf.EFFECT_NO_EDGE,
        cf.EFFECT_EXTENDED,
        cf.EFFECT_UNAVAILABLE,
    )
    out: dict[str, dict] = {}
    for effect in effects:
        subset = [
            row for row in rows
            if str((_counterfactual(row).get("real") or {}).get("location_effect") or cf.EFFECT_UNAVAILABLE)
            == effect
        ]
        counts = _terminal_outcome_counts(subset)
        evaluable_n = sum(counts[label] for label in EVALUABLE_LABELS)
        target = counts[velocity_research.TARGET_FIRST]
        out[effect] = {
            "total_rows": len(subset),
            "evaluable_rows": evaluable_n,
            "outcome_counts": counts,
            "target_first_rate_pct": _pct(target, evaluable_n),
        }
    return out


def summarize_outcomes(counterfactual_dataset: dict | None) -> dict:
    """Summarize linked outcomes without applying acceptance thresholds."""
    data = counterfactual_dataset if isinstance(counterfactual_dataset, dict) else {}
    records = [r for r in (data.get("records") or []) if isinstance(r, dict)]
    counts = _terminal_outcome_counts(records)
    evaluable_n = sum(counts[label] for label in EVALUABLE_LABELS)
    ambiguous_or_censored = (
        counts[velocity_research.AMBIGUOUS_SAME_SESSION]
        + counts[velocity_research.INCOMPLETE_HORIZON]
    )

    comparisons: dict[str, int] = {}
    unavailable = 0
    for row in records:
        comparison = str(
            _counterfactual(row).get("comparison") or cf.COMPARE_UNAVAILABLE
        )
        comparisons[comparison] = comparisons.get(comparison, 0) + 1
        if comparison == cf.COMPARE_UNAVAILABLE:
            unavailable += 1

    by_family: dict[str, dict[str, int]] = {}
    by_tier: dict[str, dict[str, int]] = {}
    for row in records:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        family = str(row.get("setup_family") or "UNKNOWN")
        tier = str(row.get("final_tier") or "UNKNOWN")
        by_family.setdefault(family, {})[label] = by_family.setdefault(family, {}).get(label, 0) + 1
        by_tier.setdefault(tier, {})[label] = by_tier.setdefault(tier, {}).get(label, 0) + 1

    return {
        "total_records": len(records),
        "outcome_counts": counts,
        "evaluable_records": evaluable_n,
        "ambiguous_or_censored_records": ambiguous_or_censored,
        "ambiguous_or_censored_pct": _pct(ambiguous_or_censored, len(records)),
        "comparison_counts": comparisons,
        "comparison_unavailable_records": unavailable,
        "comparison_unavailable_pct": _pct(unavailable, len(records)),
        "real_adds_hard_block": _intervention_metrics(records, cf.COMPARE_REAL_ADDS_BLOCK),
        "real_removes_proxy_hard_block": _intervention_metrics(records, cf.COMPARE_REAL_REMOVES_BLOCK),
        "nonfatal_real_effects": _nonfatal_real_effects(records),
        "by_setup_family": by_family,
        "by_final_tier": by_tier,
    }


def evaluate_market_condition_coverage(
    plan: dict | None,
    coverage_counts: dict | None,
) -> dict:
    """Evaluate caller-supplied market-condition counts against frozen minima.

    R4H-3B does not invent regimes from fields that were never persisted. If a
    study plan requires regime coverage, the counts must come from a separately
    auditable chronological dataset/report.
    """
    p = validate_study_plan(plan)
    minima = p.get("market_condition_minimums") or {}
    counts = coverage_counts if isinstance(coverage_counts, dict) else {}
    if not minima:
        return {
            "required": False,
            "accepted": False,
            "checks": {},
            "reason": "NO_MARKET_CONDITION_COVERAGE_PLAN_DECLARED",
        }

    checks: dict[str, dict] = {}
    for condition, minimum in minima.items():
        actual = _num(counts.get(condition))
        passed = actual is not None and actual >= float(minimum)
        checks[condition] = {
            "actual": actual,
            "minimum": minimum,
            "passed": passed,
        }
    accepted = bool(checks) and all(c["passed"] for c in checks.values())
    return {
        "required": True,
        "accepted": accepted,
        "checks": checks,
        "reason": "COVERAGE_ACCEPTED" if accepted else "COVERAGE_INCOMPLETE",
    }


def evaluate_sample_readiness(summary: dict | None, plan: dict | None) -> dict:
    s = summary if isinstance(summary, dict) else {}
    p = validate_study_plan(plan)
    if not p["valid"]:
        return {
            "accepted": False,
            "checks": {},
            "reason": STUDY_PLAN_INVALID,
            "plan_errors": list(p["errors"]),
        }

    thresholds = p["sample_thresholds"]
    adds = s.get("real_adds_hard_block") or {}
    removes = s.get("real_removes_proxy_hard_block") or {}
    checks = {
        "min_evaluable_records": {
            "actual": s.get("evaluable_records"),
            "threshold": thresholds["min_evaluable_records"],
            "passed": (s.get("evaluable_records") or 0) >= thresholds["min_evaluable_records"],
        },
        "min_real_adds_hard_block_evaluable": {
            "actual": adds.get("evaluable_rows"),
            "threshold": thresholds["min_real_adds_hard_block_evaluable"],
            "passed": (adds.get("evaluable_rows") or 0) >= thresholds["min_real_adds_hard_block_evaluable"],
        },
        "min_real_removes_proxy_hard_block_evaluable": {
            "actual": removes.get("evaluable_rows"),
            "threshold": thresholds["min_real_removes_proxy_hard_block_evaluable"],
            "passed": (removes.get("evaluable_rows") or 0) >= thresholds["min_real_removes_proxy_hard_block_evaluable"],
        },
        "max_ambiguous_or_censored_pct": {
            "actual": s.get("ambiguous_or_censored_pct"),
            "threshold": thresholds["max_ambiguous_or_censored_pct"],
            "passed": (
                s.get("ambiguous_or_censored_pct") is not None
                and s["ambiguous_or_censored_pct"] <= thresholds["max_ambiguous_or_censored_pct"]
            ),
        },
        "max_comparison_unavailable_pct": {
            "actual": s.get("comparison_unavailable_pct"),
            "threshold": thresholds["max_comparison_unavailable_pct"],
            "passed": (
                s.get("comparison_unavailable_pct") is not None
                and s["comparison_unavailable_pct"] <= thresholds["max_comparison_unavailable_pct"]
            ),
        },
    }
    accepted = all(c["passed"] for c in checks.values())
    return {
        "accepted": accepted,
        "checks": checks,
        "reason": "SAMPLE_ACCEPTED" if accepted else STUDY_SAMPLE_INSUFFICIENT,
        "plan_errors": [],
    }


def evaluate_effect_thresholds(summary: dict | None, plan: dict | None) -> dict:
    s = summary if isinstance(summary, dict) else {}
    p = validate_study_plan(plan)
    thresholds = p.get("effect_thresholds") or {}
    if not p["valid"]:
        return {
            "declared": False,
            "accepted": False,
            "checks": {},
            "reason": STUDY_PLAN_INVALID,
        }
    if not thresholds:
        return {
            "declared": False,
            "accepted": False,
            "checks": {},
            "reason": STUDY_DESCRIPTIVE_ONLY,
        }

    adds = s.get("real_adds_hard_block") or {}
    removes = s.get("real_removes_proxy_hard_block") or {}
    checks: dict[str, dict] = {}

    def maximum(key: str, actual: float | None) -> None:
        if key not in thresholds:
            return
        threshold = thresholds[key]
        checks[key] = {
            "actual": actual,
            "threshold": threshold,
            "passed": actual is not None and actual <= threshold,
        }

    def minimum(key: str, actual: float | None) -> None:
        if key not in thresholds:
            return
        threshold = thresholds[key]
        checks[key] = {
            "actual": actual,
            "threshold": threshold,
            "passed": actual is not None and actual >= threshold,
        }

    maximum(
        "max_real_adds_block_target_opportunity_cost_pct",
        adds.get("negative_evidence_pct"),
    )
    minimum(
        "min_real_adds_block_objective_failure_protection_pct",
        adds.get("positive_evidence_pct"),
    )
    minimum(
        "min_real_removes_block_target_recovery_pct",
        removes.get("positive_evidence_pct"),
    )
    maximum(
        "max_real_removes_block_objective_failure_exposure_pct",
        removes.get("negative_evidence_pct"),
    )

    accepted = bool(checks) and all(c["passed"] for c in checks.values())
    return {
        "declared": True,
        "accepted": accepted,
        "checks": checks,
        "reason": (
            "EFFECT_THRESHOLDS_ACCEPTED"
            if accepted
            else "EFFECT_THRESHOLDS_NOT_ACCEPTED"
        ),
    }


def build_study_report(
    counterfactual_dataset: dict | None,
    plan: dict | None,
    coverage_counts: dict | None = None,
) -> dict:
    """Build the auditable R4H-3B research report.

    Passing this report is never a live authority handoff. At most it can mark
    a narrow hard-block evidence package ready for a separately reviewed phase.
    Full real-4H replacement remains unsupported here.
    """
    p = validate_study_plan(plan)
    summary = summarize_outcomes(counterfactual_dataset)
    sample = evaluate_sample_readiness(summary, plan)
    effects = evaluate_effect_thresholds(summary, plan)
    coverage = evaluate_market_condition_coverage(plan, coverage_counts)

    if not p["valid"]:
        decision = STUDY_PLAN_INVALID
    elif not sample["accepted"]:
        decision = STUDY_SAMPLE_INSUFFICIENT
    elif not effects["declared"]:
        decision = STUDY_DESCRIPTIVE_ONLY
    elif effects["accepted"] and (not coverage["required"] or coverage["accepted"]):
        decision = STUDY_NARROW_SUPPORTIVE
    else:
        decision = STUDY_NARROW_NOT_SUPPORTIVE

    # This projection intentionally does NOT satisfy the full R4H-2 promotion
    # contract. The location-layer study cannot prove full-stack precision or
    # recall, and this pure module cannot assert CI state from outside itself.
    r4h2_projection = {
        "chronological_out_of_sample": p.get("chronological_out_of_sample") is True,
        "outcome_linked": summary.get("evaluable_records", 0) > 0,
        "counterfactual_proxy_vs_real": (
            summary.get("comparison_unavailable_records", 0)
            < summary.get("total_records", 0)
        ),
        "sample_size_accepted_under_predeclared_plan": sample["accepted"],
        "market_condition_coverage_accepted": coverage["accepted"],
        "real_4h_improves_or_preserves_precision": False,
        "real_4h_does_not_materially_damage_recall": False,
        "capital_integrity_regressions_green": False,
    }

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "routing_authority": False,
        "automatic_promotion": False,
        "scope": "4H_LOCATION_LAYER_ONLY",
        "plan": p,
        "summary": summary,
        "sample_readiness": sample,
        "effect_evaluation": effects,
        "market_condition_coverage": coverage,
        "study_decision": decision,
        "narrow_hard_block_handoff_review_ready": decision == STUDY_NARROW_SUPPORTIVE,
        "full_tier_counterfactual_supported": False,
        "full_4h_replacement_supported": False,
        "r4h2_validation_projection": r4h2_projection,
        "next_required_evidence": [
            "persist/replay enough decision-time evidence to reconstruct the full ladder before any full 4H replacement claim",
            "obtain independently auditable market-condition coverage when required by the predeclared plan",
            "run full capital-integrity CI in the later handoff branch",
            "perform a separately reviewed authority handoff even if a narrow veto study passes",
        ],
    }

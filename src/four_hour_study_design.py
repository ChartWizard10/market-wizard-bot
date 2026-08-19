"""R4H-3C — forward 4H study design, independence and uncertainty gate.

R4H-3B can score a predeclared real-vs-proxy location-layer outcome study.
R4H-3C closes three research-integrity gaps before any forward evidence is
reviewed:

1. repeated 15-minute observations of one ticker/session are not treated as
   independent sample units;
2. the evaluation window is explicit and forward-dated;
3. point estimates are accompanied by predeclared Wilson confidence bounds.

The canonical sampling unit is the FIRST observation for a ticker on a session
inside the declared evaluation window. Selection is made before inspecting the
outcome label, so a later better-looking result cannot replace an earlier row.

Chart-native condition coverage is derived from the persisted real-4H
structural state: TRENDING, COMPRESSION, REPAIR, TRANSITION, FAILURE, UNKNOWN.
No outside market factor is introduced.

Research only. No network, file I/O, model calls, live tiering, routing,
capital, suppression or authority mutation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from statistics import NormalDist
from typing import Any

from src import four_hour_counterfactual as cf
from src import four_hour_outcome_study as base_study

VERSION = "R4H-3C"
SAMPLING_FIRST_TICKER_SESSION = "FIRST_OBSERVATION_PER_TICKER_SESSION"

CONDITION_TRENDING = "TRENDING"
CONDITION_COMPRESSION = "COMPRESSION"
CONDITION_REPAIR = "REPAIR"
CONDITION_TRANSITION = "TRANSITION"
CONDITION_FAILURE = "FAILURE"
CONDITION_UNKNOWN = "UNKNOWN"

CONDITIONS = {
    CONDITION_TRENDING,
    CONDITION_COMPRESSION,
    CONDITION_REPAIR,
    CONDITION_TRANSITION,
    CONDITION_FAILURE,
    CONDITION_UNKNOWN,
}

_CI_KEYS = (
    "min_real_adds_block_protection_lcb_pct",
    "max_real_adds_block_target_cost_ucb_pct",
    "min_real_removes_block_recovery_lcb_pct",
    "max_real_removes_block_failure_ucb_pct",
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


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_observed_at(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_forward_plan(plan: dict | None) -> dict:
    """Validate R4H-3B rules plus forward-window/independence/CI rules."""
    p = deepcopy(plan) if isinstance(plan, dict) else {}
    base = base_study.validate_study_plan(p)
    errors = list(base.get("errors") or [])

    sampling_unit = _text(p.get("sampling_unit"))
    if sampling_unit != SAMPLING_FIRST_TICKER_SESSION:
        errors.append("INVALID_OR_MISSING_SAMPLING_UNIT")

    start = _parse_date(p.get("evaluation_start_date"))
    end = _parse_date(p.get("evaluation_end_date"))
    if start is None:
        errors.append("INVALID_OR_MISSING_EVALUATION_START_DATE")
    if end is None:
        errors.append("INVALID_OR_MISSING_EVALUATION_END_DATE")
    if start is not None and end is not None and end < start:
        errors.append("EVALUATION_END_PRECEDES_START")

    confidence = _num(p.get("confidence_level"))
    if confidence is None or confidence <= 0.5 or confidence >= 1.0:
        errors.append("INVALID_OR_MISSING_CONFIDENCE_LEVEL")

    ci_thresholds: dict[str, float] = {}
    for key in _CI_KEYS:
        value = _num(p.get(key))
        if value is None or value < 0 or value > 100:
            errors.append(f"INVALID_OR_MISSING:{key}")
        else:
            ci_thresholds[key] = value

    minima = base.get("market_condition_minimums") or {}
    unknown_conditions = sorted(set(minima) - CONDITIONS)
    if unknown_conditions:
        errors.append(
            "UNSUPPORTED_MARKET_CONDITION_KEYS:" + ",".join(unknown_conditions)
        )
    if not minima:
        errors.append("MARKET_CONDITION_MINIMUMS_REQUIRED")

    return {
        "version": VERSION,
        "valid": not errors,
        "errors": errors,
        "base_plan": base,
        "sampling_unit": sampling_unit,
        "evaluation_start_date": start.isoformat() if start else None,
        "evaluation_end_date": end.isoformat() if end else None,
        "confidence_level": confidence,
        "confidence_thresholds": ci_thresholds,
        "market_condition_minimums": dict(minima),
    }


def select_independent_records(
    counterfactual_dataset: dict | None,
    plan: dict | None,
) -> dict:
    """Select one earliest row per ticker/session without reading outcomes."""
    data = deepcopy(counterfactual_dataset) if isinstance(counterfactual_dataset, dict) else {}
    raw_records = [r for r in (data.get("records") or []) if isinstance(r, dict)]
    design = validate_forward_plan(plan)
    start = _parse_date(design.get("evaluation_start_date"))
    end = _parse_date(design.get("evaluation_end_date"))

    excluded = {
        "MISSING_SAMPLING_IDENTITY": 0,
        "OUTSIDE_EVALUATION_WINDOW": 0,
    }
    eligible: list[tuple[datetime, str, str, dict]] = []

    for row in raw_records:
        ticker = _text(row.get("ticker"))
        observed = _parse_observed_at(row.get("observed_at"))
        if not ticker or observed is None:
            excluded["MISSING_SAMPLING_IDENTITY"] += 1
            continue
        session_date = observed.date()
        if start is None or end is None or session_date < start or session_date > end:
            excluded["OUTSIDE_EVALUATION_WINDOW"] += 1
            continue
        eligible.append(
            (
                observed,
                ticker.upper(),
                str(row.get("scan_id") or ""),
                row,
            )
        )

    # Chronology and identity decide the sample. Outcome labels are untouched
    # and are not part of the selection key or sort order.
    eligible.sort(key=lambda item: (item[0], item[1], item[2]))
    selected_by_key: dict[tuple[str, date], dict] = {}
    repeated_removed = 0
    for observed, ticker, _, row in eligible:
        key = (ticker, observed.date())
        if key in selected_by_key:
            repeated_removed += 1
            continue
        selected_by_key[key] = row

    selected = list(selected_by_key.values())
    selected.sort(
        key=lambda row: (
            str(row.get("observed_at") or ""),
            str(row.get("ticker") or ""),
            str(row.get("scan_id") or ""),
        )
    )

    return {
        "version": VERSION,
        "research_only": True,
        "sampling_unit": design.get("sampling_unit"),
        "raw_records": len(raw_records),
        "window_eligible_records": len(eligible),
        "independent_records": len(selected),
        "repeated_ticker_session_rows_removed": repeated_removed,
        "excluded": excluded,
        "records": selected,
        "dataset": {
            "version": data.get("version"),
            "records": selected,
        },
    }


def structural_condition(record: dict | None) -> str:
    row = record if isinstance(record, dict) else {}
    block = row.get("four_hour_counterfactual")
    block = block if isinstance(block, dict) else {}
    real = block.get("real")
    real = real if isinstance(real, dict) else {}
    state = str(real.get("raw_structural_state") or "UNKNOWN").upper()

    if state in ("EXPANSION", "CONTINUATION"):
        return CONDITION_TRENDING
    if state == "COMPRESSION":
        return CONDITION_COMPRESSION
    if state == "REPAIR":
        return CONDITION_REPAIR
    if state == "TRANSITION":
        return CONDITION_TRANSITION
    if state == "FAILURE":
        return CONDITION_FAILURE
    return CONDITION_UNKNOWN


def condition_counts(records: list[dict] | None) -> dict[str, int]:
    counts = {condition: 0 for condition in CONDITIONS}
    for row in records or []:
        if isinstance(row, dict):
            condition = structural_condition(row)
            counts[condition] = counts.get(condition, 0) + 1
    return counts


def wilson_interval(
    successes: int,
    total: int,
    confidence_level: float = 0.95,
) -> dict:
    """Two-sided Wilson score interval for a binomial proportion."""
    try:
        success_n = int(successes)
        total_n = int(total)
        confidence = float(confidence_level)
    except (TypeError, ValueError, OverflowError):
        return {"lower_pct": None, "upper_pct": None, "point_pct": None}

    if total_n <= 0 or success_n < 0 or success_n > total_n:
        return {"lower_pct": None, "upper_pct": None, "point_pct": None}
    if confidence <= 0.5 or confidence >= 1.0:
        return {"lower_pct": None, "upper_pct": None, "point_pct": None}

    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = success_n / total_n
    z2 = z * z
    denominator = 1.0 + z2 / total_n
    center = (p + z2 / (2.0 * total_n)) / denominator
    spread = (
        z
        * ((p * (1.0 - p) / total_n + z2 / (4.0 * total_n * total_n)) ** 0.5)
        / denominator
    )
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return {
        "successes": success_n,
        "total": total_n,
        "confidence_level": confidence,
        "point_pct": round(p * 100.0, 4),
        "lower_pct": round(lower * 100.0, 4),
        "upper_pct": round(upper * 100.0, 4),
    }


def evaluate_confidence_gate(summary: dict | None, plan: dict | None) -> dict:
    """Apply predeclared Wilson-bound requirements to intervention evidence."""
    s = summary if isinstance(summary, dict) else {}
    design = validate_forward_plan(plan)
    confidence = design.get("confidence_level")
    thresholds = design.get("confidence_thresholds") or {}

    if not design["valid"]:
        return {
            "accepted": False,
            "checks": {},
            "intervals": {},
            "reason": "INVALID_FORWARD_PLAN",
        }

    adds = s.get("real_adds_hard_block") or {}
    removes = s.get("real_removes_proxy_hard_block") or {}

    intervals = {
        "real_adds_block_protection": wilson_interval(
            adds.get("positive_evidence_count") or 0,
            adds.get("evaluable_rows") or 0,
            confidence,
        ),
        "real_adds_block_target_cost": wilson_interval(
            adds.get("negative_evidence_count") or 0,
            adds.get("evaluable_rows") or 0,
            confidence,
        ),
        "real_removes_block_recovery": wilson_interval(
            removes.get("positive_evidence_count") or 0,
            removes.get("evaluable_rows") or 0,
            confidence,
        ),
        "real_removes_block_failure": wilson_interval(
            removes.get("negative_evidence_count") or 0,
            removes.get("evaluable_rows") or 0,
            confidence,
        ),
    }

    checks = {
        "min_real_adds_block_protection_lcb_pct": {
            "actual": intervals["real_adds_block_protection"]["lower_pct"],
            "threshold": thresholds["min_real_adds_block_protection_lcb_pct"],
        },
        "max_real_adds_block_target_cost_ucb_pct": {
            "actual": intervals["real_adds_block_target_cost"]["upper_pct"],
            "threshold": thresholds["max_real_adds_block_target_cost_ucb_pct"],
        },
        "min_real_removes_block_recovery_lcb_pct": {
            "actual": intervals["real_removes_block_recovery"]["lower_pct"],
            "threshold": thresholds["min_real_removes_block_recovery_lcb_pct"],
        },
        "max_real_removes_block_failure_ucb_pct": {
            "actual": intervals["real_removes_block_failure"]["upper_pct"],
            "threshold": thresholds["max_real_removes_block_failure_ucb_pct"],
        },
    }

    for key, check in checks.items():
        actual = check["actual"]
        threshold = check["threshold"]
        if key.startswith("min_"):
            check["passed"] = actual is not None and actual >= threshold
        else:
            check["passed"] = actual is not None and actual <= threshold

    accepted = all(check["passed"] for check in checks.values())
    return {
        "accepted": accepted,
        "checks": checks,
        "intervals": intervals,
        "reason": (
            "CONFIDENCE_BOUNDS_ACCEPTED"
            if accepted
            else "CONFIDENCE_BOUNDS_NOT_ACCEPTED"
        ),
    }


def build_forward_report(
    counterfactual_dataset: dict | None,
    plan: dict | None,
) -> dict:
    """Build the forward-designed R4H report with independent sample units."""
    design = validate_forward_plan(plan)
    selection = select_independent_records(counterfactual_dataset, plan)
    counts = condition_counts(selection["records"])
    base_report = base_study.build_study_report(
        selection["dataset"],
        plan,
        coverage_counts=counts,
    )
    confidence = evaluate_confidence_gate(base_report.get("summary"), plan)

    review_ready = bool(
        design["valid"]
        and base_report.get("narrow_hard_block_handoff_review_ready") is True
        and confidence.get("accepted") is True
    )

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "routing_authority": False,
        "automatic_promotion": False,
        "design": design,
        "sampling": {k: v for k, v in selection.items() if k not in ("records", "dataset")},
        "condition_counts": counts,
        "base_study": base_report,
        "confidence_gate": confidence,
        "forward_handoff_review_ready": review_ready,
        "full_4h_replacement_supported": False,
        "next_required_evidence": (
            [
                "complete the declared forward evaluation window",
                "allow five future completed sessions for terminal outcome maturation",
                "re-run the independent-sample study after the window closes",
            ]
            if not review_ready
            else [
                "open a separate reviewed narrow-authority handoff branch",
                "re-run full capital-integrity CI before any runtime authority change",
            ]
        ),
    }

"""CAP-40C — predeclared independent candidate-cap boundary study.

CAP-40B links pre-model boundary observations to future completed Daily
sessions. CAP-40C defines the study design that must be declared before those
outcomes are reviewed for a capacity decision.

The study uses one earliest observation per ticker/session across both boundary
bands. Selection depends only on timestamp, ticker, scan identity and the
predeclared date window; outcome labels never participate in sample selection.

A passing report can only make a paid 30-vs-40 deep-analysis experiment
eligible for separate review. It cannot change the production candidate cap,
tiering, capital, routing, suppression or model-call count.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from statistics import NormalDist
from typing import Any
from zoneinfo import ZoneInfo

from src import capacity_boundary_observation as boundary
from src import velocity_research

VERSION = "CAP-40C"
SAMPLING_UNIT = "FIRST_OBSERVATION_PER_TICKER_SESSION"
DEFAULT_SESSION_TIMEZONE = "America/New_York"

PLAN_VALID = "VALID"
PLAN_INVALID = "INVALID"

DECISION_PLAN_INVALID = "PLAN_INVALID"
DECISION_WINDOW_NOT_MATURE = "WINDOW_NOT_MATURE"
DECISION_SAMPLE_INSUFFICIENT = "SAMPLE_INSUFFICIENT"
DECISION_EVIDENCE_NOT_SUPPORTIVE = "BOUNDARY_EVIDENCE_NOT_SUPPORTIVE"
DECISION_PAID_EXPERIMENT_REVIEW_READY = "PAID_EXPERIMENT_REVIEW_READY"

EVALUABLE_LABELS = {
    velocity_research.TARGET_FIRST,
    velocity_research.INVALIDATION_FIRST,
    velocity_research.TIME_BARRIER,
}
AMBIGUOUS_LABELS = {velocity_research.AMBIGUOUS_SAME_SESSION}
CENSORED_LABELS = {velocity_research.INCOMPLETE_HORIZON}
INVALID_LABELS = {velocity_research.INVALID_DATA}

_SAMPLE_KEYS = (
    "min_evaluable_total",
    "min_baseline_evaluable",
    "min_shadow_evaluable",
    "max_ambiguous_or_censored_pct",
    "max_invalid_pct",
    "max_shadow_unknown_family_pct",
)

_EFFECT_KEYS = (
    "min_shadow_target_first_count",
    "min_shadow_target_rate_pct",
    "min_shadow_target_lcb_pct",
    "min_shadow_minus_baseline_target_diff_lcb_pct",
    "min_shadow_feasibility_supported_or_partial_pct",
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


def _parse_timestamp(
    value: Any,
    session_timezone: str = DEFAULT_SESSION_TIMEZONE,
) -> tuple[datetime | None, date | None]:
    """Return absolute UTC time plus the intended U.S. session calendar date.

    Current autoscan timestamps are naive UTC strings. Offset-aware timestamps
    are also accepted. Both forms are converted to the declared session zone
    before the ticker/session identity is formed.
    """
    text = _text(value)
    if not text:
        return None, None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        session_zone = ZoneInfo(session_timezone)
    except (ValueError, KeyError):
        return None, None

    if parsed.tzinfo is None:
        absolute = parsed.replace(tzinfo=timezone.utc)
    else:
        absolute = parsed.astimezone(timezone.utc)
    session_date = absolute.astimezone(session_zone).date()
    return absolute, session_date


def _pct(num: int | float, den: int | float) -> float | None:
    if not den:
        return None
    return round(float(num) / float(den) * 100.0, 4)


def validate_study_plan(plan: dict | None) -> dict:
    """Validate the complete CAP-40C study contract with no numeric defaults."""
    p = deepcopy(plan) if isinstance(plan, dict) else {}
    errors: list[str] = []

    name = _text(p.get("name"))
    version = _text(p.get("version"))
    sampling = _text(p.get("sampling_unit"))
    session_timezone = _text(p.get("session_timezone"))
    start = _parse_date(p.get("evaluation_start_date"))
    end = _parse_date(p.get("evaluation_end_date"))
    review_date = _parse_date(p.get("final_review_not_before_date"))
    confidence = _num(p.get("confidence_level"))

    if not name:
        errors.append("MISSING_PLAN_NAME")
    if not version:
        errors.append("MISSING_PLAN_VERSION")
    if p.get("declared_before_observation_review") is not True:
        errors.append("PLAN_NOT_DECLARED_BEFORE_OBSERVATION_REVIEW")
    if p.get("no_favorable_early_stop") is not True:
        errors.append("NO_FAVORABLE_EARLY_STOP_NOT_DECLARED")
    if sampling != SAMPLING_UNIT:
        errors.append("INVALID_OR_MISSING_SAMPLING_UNIT")
    if not session_timezone:
        errors.append("MISSING_SESSION_TIMEZONE")
    else:
        try:
            ZoneInfo(session_timezone)
        except KeyError:
            errors.append("INVALID_SESSION_TIMEZONE")

    if start is None:
        errors.append("INVALID_OR_MISSING_EVALUATION_START_DATE")
    if end is None:
        errors.append("INVALID_OR_MISSING_EVALUATION_END_DATE")
    if start is not None and end is not None and end < start:
        errors.append("EVALUATION_END_PRECEDES_START")
    if review_date is None:
        errors.append("INVALID_OR_MISSING_FINAL_REVIEW_DATE")
    if end is not None and review_date is not None and review_date <= end:
        errors.append("FINAL_REVIEW_DATE_MUST_FOLLOW_EVALUATION_END")
    if confidence is None or confidence <= 0.5 or confidence >= 1.0:
        errors.append("INVALID_OR_MISSING_CONFIDENCE_LEVEL")

    sample_thresholds: dict[str, float] = {}
    for key in _SAMPLE_KEYS:
        value = _num(p.get(key))
        if value is None:
            errors.append(f"MISSING_OR_INVALID:{key}")
        elif value < 0 or (key.startswith("max_") and value > 100):
            errors.append(f"INVALID_THRESHOLD:{key}")
        else:
            sample_thresholds[key] = value

    effect_thresholds: dict[str, float] = {}
    for key in _EFFECT_KEYS:
        value = _num(p.get(key))
        if value is None:
            errors.append(f"MISSING_OR_INVALID:{key}")
            continue
        if key == "min_shadow_minus_baseline_target_diff_lcb_pct":
            if value < -100 or value > 100:
                errors.append(f"INVALID_THRESHOLD:{key}")
                continue
        elif value < 0 or value > 100:
            errors.append(f"INVALID_THRESHOLD:{key}")
            continue
        effect_thresholds[key] = value

    return {
        "contract_version": VERSION,
        "status": PLAN_VALID if not errors else PLAN_INVALID,
        "valid": not errors,
        "errors": errors,
        "name": name,
        "version": version,
        "declared_before_observation_review": (
            p.get("declared_before_observation_review") is True
        ),
        "no_favorable_early_stop": p.get("no_favorable_early_stop") is True,
        "sampling_unit": sampling,
        "session_timezone": session_timezone,
        "evaluation_start_date": start.isoformat() if start else None,
        "evaluation_end_date": end.isoformat() if end else None,
        "final_review_not_before_date": review_date.isoformat() if review_date else None,
        "confidence_level": confidence,
        "sample_thresholds": sample_thresholds,
        "effect_thresholds": effect_thresholds,
    }


def select_independent_records(
    cap40b_dataset: dict | None,
    plan: dict | None,
) -> dict:
    """Select the earliest observation per ticker/session without reading label."""
    data = deepcopy(cap40b_dataset) if isinstance(cap40b_dataset, dict) else {}
    records = [row for row in (data.get("records") or []) if isinstance(row, dict)]
    design = validate_study_plan(plan)
    start = _parse_date(design.get("evaluation_start_date"))
    end = _parse_date(design.get("evaluation_end_date"))
    session_timezone = design.get("session_timezone") or DEFAULT_SESSION_TIMEZONE

    excluded = {
        "MISSING_SAMPLING_IDENTITY": 0,
        "OUTSIDE_EVALUATION_WINDOW": 0,
    }
    eligible: list[tuple[datetime, str, str, date, dict]] = []

    for row in records:
        ticker = _text(row.get("ticker"))
        absolute, session_date = _parse_timestamp(
            row.get("observed_at"),
            session_timezone,
        )
        if not ticker or absolute is None or session_date is None:
            excluded["MISSING_SAMPLING_IDENTITY"] += 1
            continue
        if start is None or end is None or session_date < start or session_date > end:
            excluded["OUTSIDE_EVALUATION_WINDOW"] += 1
            continue
        eligible.append((
            absolute,
            ticker.upper(),
            str(row.get("scan_id") or ""),
            session_date,
            row,
        ))

    eligible.sort(key=lambda item: (item[0], item[1], item[2]))
    selected: dict[tuple[str, date], dict] = {}
    repeated_removed = 0
    band_crossovers_removed = 0

    for _, ticker, _, session_date, row in eligible:
        key = (ticker, session_date)
        if key in selected:
            repeated_removed += 1
            if selected[key].get("band") != row.get("band"):
                band_crossovers_removed += 1
            continue
        selected[key] = row

    rows = list(selected.values())
    rows.sort(key=lambda row: (
        _parse_timestamp(row.get("observed_at"), session_timezone)[0]
        or datetime.max.replace(tzinfo=timezone.utc),
        str(row.get("ticker") or ""),
        str(row.get("scan_id") or ""),
    ))

    return {
        "version": VERSION,
        "research_only": True,
        "sampling_unit": design.get("sampling_unit"),
        "raw_records": len(records),
        "window_eligible_records": len(eligible),
        "independent_records": len(rows),
        "repeated_ticker_session_rows_removed": repeated_removed,
        "band_crossovers_removed": band_crossovers_removed,
        "excluded": excluded,
        "records": rows,
    }


def wilson_interval(
    successes: int,
    total: int,
    confidence_level: float,
) -> dict:
    """Two-sided Wilson score interval for one binomial proportion."""
    try:
        success_n = int(successes)
        total_n = int(total)
        confidence = float(confidence_level)
    except (TypeError, ValueError, OverflowError):
        return {"point_pct": None, "lower_pct": None, "upper_pct": None}

    if total_n <= 0 or success_n < 0 or success_n > total_n:
        return {"point_pct": None, "lower_pct": None, "upper_pct": None}
    if confidence <= 0.5 or confidence >= 1.0:
        return {"point_pct": None, "lower_pct": None, "upper_pct": None}

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


def _band_summary(rows: list[dict], band: str, confidence: float) -> dict:
    subset = [row for row in rows if row.get("band") == band]
    labels: dict[str, int] = {}
    for row in subset:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        labels[label] = labels.get(label, 0) + 1

    evaluable = sum(labels.get(label, 0) for label in EVALUABLE_LABELS)
    targets = labels.get(velocity_research.TARGET_FIRST, 0)
    objective_failures = (
        labels.get(velocity_research.INVALIDATION_FIRST, 0)
        + labels.get(velocity_research.TIME_BARRIER, 0)
    )
    supported_or_partial = sum(
        1 for row in subset
        if row.get("label") in EVALUABLE_LABELS
        and row.get("feasibility_status") in (
            velocity_research.FEASIBILITY_SUPPORTED,
            velocity_research.FEASIBILITY_PARTIAL,
        )
    )
    unknown_family = sum(
        1 for row in subset
        if row.get("label") in EVALUABLE_LABELS
        and str(row.get("setup_family") or "UNKNOWN") == "UNKNOWN"
    )

    return {
        "band": band,
        "records": len(subset),
        "evaluable": evaluable,
        "label_counts": labels,
        "target_first": targets,
        "objective_failures": objective_failures,
        "target_rate_pct": _pct(targets, evaluable),
        "objective_failure_rate_pct": _pct(objective_failures, evaluable),
        "target_rate_interval": wilson_interval(targets, evaluable, confidence),
        "feasibility_supported_or_partial": supported_or_partial,
        "feasibility_supported_or_partial_pct": _pct(
            supported_or_partial, evaluable
        ),
        "unknown_family": unknown_family,
        "unknown_family_pct": _pct(unknown_family, evaluable),
    }


def summarize_independent_records(
    records: list[dict] | None,
    confidence_level: float,
) -> dict:
    """Summarize independent baseline-edge and shadow-increment observations."""
    rows = [row for row in (records or []) if isinstance(row, dict)]
    baseline = _band_summary(rows, boundary.BAND_BASELINE_EDGE, confidence_level)
    shadow = _band_summary(rows, boundary.BAND_SHADOW_INCREMENT, confidence_level)

    all_labels: dict[str, int] = {}
    for row in rows:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        all_labels[label] = all_labels.get(label, 0) + 1

    evaluable_total = sum(all_labels.get(label, 0) for label in EVALUABLE_LABELS)
    ambiguous_or_censored = (
        all_labels.get(velocity_research.AMBIGUOUS_SAME_SESSION, 0)
        + all_labels.get(velocity_research.INCOMPLETE_HORIZON, 0)
    )
    invalid = all_labels.get(velocity_research.INVALID_DATA, 0)

    b_int = baseline["target_rate_interval"]
    s_int = shadow["target_rate_interval"]
    point_diff = None
    lower_diff = None
    upper_diff = None
    if (
        shadow["target_rate_pct"] is not None
        and baseline["target_rate_pct"] is not None
    ):
        point_diff = round(
            shadow["target_rate_pct"] - baseline["target_rate_pct"], 4
        )
    if s_int.get("lower_pct") is not None and b_int.get("upper_pct") is not None:
        lower_diff = round(s_int["lower_pct"] - b_int["upper_pct"], 4)
    if s_int.get("upper_pct") is not None and b_int.get("lower_pct") is not None:
        upper_diff = round(s_int["upper_pct"] - b_int["lower_pct"], 4)

    family_counts: dict[str, dict[str, int]] = {}
    feasibility_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        band = str(row.get("band") or "UNKNOWN")
        family = str(row.get("setup_family") or "UNKNOWN")
        feasibility = str(row.get("feasibility_status") or "UNKNOWN")
        family_counts.setdefault(band, {})[family] = (
            family_counts.setdefault(band, {}).get(family, 0) + 1
        )
        feasibility_counts.setdefault(band, {})[feasibility] = (
            feasibility_counts.setdefault(band, {}).get(feasibility, 0) + 1
        )

    return {
        "records": len(rows),
        "evaluable_total": evaluable_total,
        "label_counts": all_labels,
        "ambiguous_or_censored": ambiguous_or_censored,
        "ambiguous_or_censored_pct": _pct(ambiguous_or_censored, len(rows)),
        "invalid": invalid,
        "invalid_pct": _pct(invalid, len(rows)),
        "baseline_edge": baseline,
        "shadow_increment": shadow,
        "shadow_minus_baseline_target_rate": {
            "point_pct": point_diff,
            "lower_pct": lower_diff,
            "upper_pct": upper_diff,
            "method": "CONSERVATIVE_WILSON_BOUND_DIFFERENCE",
        },
        "setup_family_counts_by_band": family_counts,
        "feasibility_counts_by_band": feasibility_counts,
    }


def evaluate_review_maturity(plan: dict | None, as_of_date: Any) -> dict:
    design = validate_study_plan(plan)
    as_of = _parse_date(as_of_date)
    review_date = _parse_date(design.get("final_review_not_before_date"))
    accepted = bool(
        design["valid"]
        and as_of is not None
        and review_date is not None
        and as_of >= review_date
    )
    return {
        "accepted": accepted,
        "as_of_date": as_of.isoformat() if as_of else None,
        "final_review_not_before_date": (
            review_date.isoformat() if review_date else None
        ),
        "reason": "WINDOW_MATURE" if accepted else DECISION_WINDOW_NOT_MATURE,
    }


def evaluate_sample_readiness(summary: dict | None, plan: dict | None) -> dict:
    s = summary if isinstance(summary, dict) else {}
    design = validate_study_plan(plan)
    if not design["valid"]:
        return {
            "accepted": False,
            "checks": {},
            "reason": DECISION_PLAN_INVALID,
        }

    thresholds = design["sample_thresholds"]
    baseline = s.get("baseline_edge") or {}
    shadow = s.get("shadow_increment") or {}
    checks = {
        "min_evaluable_total": {
            "actual": s.get("evaluable_total"),
            "threshold": thresholds["min_evaluable_total"],
            "passed": (s.get("evaluable_total") or 0) >= thresholds["min_evaluable_total"],
        },
        "min_baseline_evaluable": {
            "actual": baseline.get("evaluable"),
            "threshold": thresholds["min_baseline_evaluable"],
            "passed": (baseline.get("evaluable") or 0) >= thresholds["min_baseline_evaluable"],
        },
        "min_shadow_evaluable": {
            "actual": shadow.get("evaluable"),
            "threshold": thresholds["min_shadow_evaluable"],
            "passed": (shadow.get("evaluable") or 0) >= thresholds["min_shadow_evaluable"],
        },
        "max_ambiguous_or_censored_pct": {
            "actual": s.get("ambiguous_or_censored_pct"),
            "threshold": thresholds["max_ambiguous_or_censored_pct"],
            "passed": (
                s.get("ambiguous_or_censored_pct") is not None
                and s["ambiguous_or_censored_pct"]
                <= thresholds["max_ambiguous_or_censored_pct"]
            ),
        },
        "max_invalid_pct": {
            "actual": s.get("invalid_pct"),
            "threshold": thresholds["max_invalid_pct"],
            "passed": (
                s.get("invalid_pct") is not None
                and s["invalid_pct"] <= thresholds["max_invalid_pct"]
            ),
        },
        "max_shadow_unknown_family_pct": {
            "actual": shadow.get("unknown_family_pct"),
            "threshold": thresholds["max_shadow_unknown_family_pct"],
            "passed": (
                shadow.get("unknown_family_pct") is not None
                and shadow["unknown_family_pct"]
                <= thresholds["max_shadow_unknown_family_pct"]
            ),
        },
    }
    accepted = all(check["passed"] for check in checks.values())
    return {
        "accepted": accepted,
        "checks": checks,
        "reason": "SAMPLE_ACCEPTED" if accepted else DECISION_SAMPLE_INSUFFICIENT,
    }


def evaluate_effect_evidence(summary: dict | None, plan: dict | None) -> dict:
    s = summary if isinstance(summary, dict) else {}
    design = validate_study_plan(plan)
    if not design["valid"]:
        return {
            "accepted": False,
            "checks": {},
            "reason": DECISION_PLAN_INVALID,
        }

    thresholds = design["effect_thresholds"]
    shadow = s.get("shadow_increment") or {}
    shadow_interval = shadow.get("target_rate_interval") or {}
    difference = s.get("shadow_minus_baseline_target_rate") or {}

    checks = {
        "min_shadow_target_first_count": {
            "actual": shadow.get("target_first"),
            "threshold": thresholds["min_shadow_target_first_count"],
            "passed": (
                (shadow.get("target_first") or 0)
                >= thresholds["min_shadow_target_first_count"]
            ),
        },
        "min_shadow_target_rate_pct": {
            "actual": shadow.get("target_rate_pct"),
            "threshold": thresholds["min_shadow_target_rate_pct"],
            "passed": (
                shadow.get("target_rate_pct") is not None
                and shadow["target_rate_pct"] >= thresholds["min_shadow_target_rate_pct"]
            ),
        },
        "min_shadow_target_lcb_pct": {
            "actual": shadow_interval.get("lower_pct"),
            "threshold": thresholds["min_shadow_target_lcb_pct"],
            "passed": (
                shadow_interval.get("lower_pct") is not None
                and shadow_interval["lower_pct"]
                >= thresholds["min_shadow_target_lcb_pct"]
            ),
        },
        "min_shadow_minus_baseline_target_diff_lcb_pct": {
            "actual": difference.get("lower_pct"),
            "threshold": thresholds[
                "min_shadow_minus_baseline_target_diff_lcb_pct"
            ],
            "passed": (
                difference.get("lower_pct") is not None
                and difference["lower_pct"]
                >= thresholds["min_shadow_minus_baseline_target_diff_lcb_pct"]
            ),
        },
        "min_shadow_feasibility_supported_or_partial_pct": {
            "actual": shadow.get("feasibility_supported_or_partial_pct"),
            "threshold": thresholds[
                "min_shadow_feasibility_supported_or_partial_pct"
            ],
            "passed": (
                shadow.get("feasibility_supported_or_partial_pct") is not None
                and shadow["feasibility_supported_or_partial_pct"]
                >= thresholds["min_shadow_feasibility_supported_or_partial_pct"]
            ),
        },
    }
    accepted = all(check["passed"] for check in checks.values())
    return {
        "accepted": accepted,
        "checks": checks,
        "reason": (
            "BOUNDARY_EFFECT_ACCEPTED"
            if accepted
            else DECISION_EVIDENCE_NOT_SUPPORTIVE
        ),
    }


def build_study_report(
    cap40b_dataset: dict | None,
    plan: dict | None,
    as_of_date: Any,
) -> dict:
    """Build the CAP-40C report without granting any production authority."""
    design = validate_study_plan(plan)
    selection = select_independent_records(cap40b_dataset, plan)
    confidence = design.get("confidence_level") or 0.95
    summary = summarize_independent_records(selection["records"], confidence)
    maturity = evaluate_review_maturity(plan, as_of_date)
    sample = evaluate_sample_readiness(summary, plan)
    effect = evaluate_effect_evidence(summary, plan)

    if not design["valid"]:
        decision = DECISION_PLAN_INVALID
    elif not maturity["accepted"]:
        decision = DECISION_WINDOW_NOT_MATURE
    elif not sample["accepted"]:
        decision = DECISION_SAMPLE_INSUFFICIENT
    elif not effect["accepted"]:
        decision = DECISION_EVIDENCE_NOT_SUPPORTIVE
    else:
        decision = DECISION_PAID_EXPERIMENT_REVIEW_READY

    return {
        "version": VERSION,
        "research_only": True,
        "candidate_cap_authority": False,
        "model_call_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "automatic_cap_change": False,
        "production_cap": 30,
        "proposed_experiment_cap": 40,
        "design": design,
        "selection": {k: v for k, v in selection.items() if k != "records"},
        "summary": summary,
        "review_maturity": maturity,
        "sample_readiness": sample,
        "effect_evidence": effect,
        "study_decision": decision,
        "paid_experiment_review_ready": (
            decision == DECISION_PAID_EXPERIMENT_REVIEW_READY
        ),
        "counterfactual_model_tier_supported": False,
        "permanent_cap_increase_supported": False,
        "next_required_evidence": (
            [
                "open a separate reviewed paid 30-vs-40 experiment branch",
                "measure downstream Claude quality for the added candidates",
                "measure scan duration, provider limits, API usage and alert quality",
                "keep permanent production cap promotion as a separate decision",
            ]
            if decision == DECISION_PAID_EXPERIMENT_REVIEW_READY
            else [
                "complete the declared observation window and outcome maturation",
                "meet the predeclared independent-sample thresholds",
                "meet the predeclared shadow opportunity and uncertainty thresholds",
            ]
        ),
    }

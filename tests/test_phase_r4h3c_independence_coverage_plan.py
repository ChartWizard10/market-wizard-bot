"""R4H-3C — forward study design, independence and uncertainty tests."""

from copy import deepcopy
from pathlib import Path
import json

from src import four_hour_counterfactual as cf
from src import four_hour_study_design as design
from src import velocity_research


PLAN_PATH = Path("research/plans/r4h3_forward_oos_v1.json")


def _plan(**overrides):
    base = {
        "name": "test-plan",
        "version": "1",
        "predeclared_before_outcome_review": True,
        "chronological_out_of_sample": True,
        "sampling_unit": design.SAMPLING_FIRST_TICKER_SESSION,
        "evaluation_start_date": "2026-08-20",
        "evaluation_end_date": "2026-09-30",
        "confidence_level": 0.95,
        "min_evaluable_records": 4,
        "min_real_adds_hard_block_evaluable": 2,
        "min_real_removes_proxy_hard_block_evaluable": 1,
        "max_ambiguous_or_censored_pct": 20,
        "max_comparison_unavailable_pct": 20,
        "max_real_adds_block_target_opportunity_cost_pct": 30,
        "min_real_adds_block_objective_failure_protection_pct": 70,
        "min_real_removes_block_target_recovery_pct": 60,
        "max_real_removes_block_objective_failure_exposure_pct": 40,
        "min_real_adds_block_protection_lcb_pct": 50,
        "max_real_adds_block_target_cost_ucb_pct": 50,
        "min_real_removes_block_recovery_lcb_pct": 40,
        "max_real_removes_block_failure_ucb_pct": 60,
        "market_condition_minimums": {
            "TRENDING": 1,
            "COMPRESSION": 0,
            "REPAIR": 1,
            "TRANSITION": 0,
            "FAILURE": 1,
        },
    }
    base.update(overrides)
    return base


def _block(comparison, real_state, real_effect=None):
    if real_effect is None:
        real_effect = {
            "FAILURE": cf.EFFECT_HARD_BLOCK,
            "REPAIR": cf.EFFECT_REPAIRING,
            "COMPRESSION": cf.EFFECT_SUPPORTIVE,
            "TRANSITION": cf.EFFECT_NO_EDGE,
            "EXPANSION": cf.EFFECT_SUPPORTIVE,
            "CONTINUATION": cf.EFFECT_SUPPORTIVE,
        }.get(real_state, cf.EFFECT_UNAVAILABLE)
    return {
        "version": cf.VERSION,
        "comparison": comparison,
        "proxy": {"location_effect": cf.EFFECT_SUPPORTIVE},
        "real": {
            "location_effect": real_effect,
            "raw_structural_state": real_state,
        },
    }


def _row(
    scan_id,
    ticker,
    observed_at,
    label,
    comparison=cf.COMPARE_SAME,
    real_state="CONTINUATION",
    real_effect=None,
):
    return {
        "scan_id": scan_id,
        "ticker": ticker,
        "observed_at": observed_at,
        "label": label,
        "setup_family": "BREAK_RETEST_CONTINUATION",
        "final_tier": "STARTER",
        "four_hour_counterfactual": _block(comparison, real_state, real_effect),
    }


def _dataset(rows):
    return {"version": cf.VERSION, "records": list(rows)}


def test_forward_plan_requires_window_sampling_confidence_and_condition_coverage():
    invalid = design.validate_forward_plan({
        "name": "x",
        "version": "1",
        "predeclared_before_outcome_review": True,
        "chronological_out_of_sample": True,
        "min_evaluable_records": 1,
        "min_real_adds_hard_block_evaluable": 1,
        "min_real_removes_proxy_hard_block_evaluable": 1,
        "max_ambiguous_or_censored_pct": 20,
        "max_comparison_unavailable_pct": 20,
    })
    assert invalid["valid"] is False
    assert "INVALID_OR_MISSING_SAMPLING_UNIT" in invalid["errors"]
    assert "INVALID_OR_MISSING_EVALUATION_START_DATE" in invalid["errors"]
    assert "INVALID_OR_MISSING_CONFIDENCE_LEVEL" in invalid["errors"]
    assert "MARKET_CONDITION_MINIMUMS_REQUIRED" in invalid["errors"]

    valid = design.validate_forward_plan(_plan())
    assert valid["valid"] is True
    assert valid["sampling_unit"] == design.SAMPLING_FIRST_TICKER_SESSION


def test_committed_forward_plan_is_valid_and_starts_after_plan_commit_day():
    with PLAN_PATH.open("r", encoding="utf-8") as handle:
        plan = json.load(handle)
    validated = design.validate_forward_plan(plan)

    assert validated["valid"] is True
    assert validated["evaluation_start_date"] == "2026-08-20"
    assert validated["evaluation_end_date"] == "2026-09-30"
    assert plan["predeclared_before_outcome_review"] is True
    assert plan["min_evaluable_records"] == 150


def test_sampling_selects_first_ticker_session_without_looking_at_outcome():
    rows = [
        _row(
            "early",
            "AAPL",
            "2026-08-20T09:45:00-04:00",
            velocity_research.INVALIDATION_FIRST,
        ),
        _row(
            "later",
            "AAPL",
            "2026-08-20T14:15:00-04:00",
            velocity_research.TARGET_FIRST,
        ),
        _row(
            "next-day",
            "AAPL",
            "2026-08-21T09:45:00-04:00",
            velocity_research.TARGET_FIRST,
        ),
    ]
    selected = design.select_independent_records(_dataset(rows), _plan())

    assert selected["raw_records"] == 3
    assert selected["independent_records"] == 2
    assert selected["repeated_ticker_session_rows_removed"] == 1
    assert [row["scan_id"] for row in selected["records"]] == ["early", "next-day"]


def test_sampling_excludes_outside_window_and_missing_identity():
    rows = [
        _row("before", "AAPL", "2026-08-19T15:00:00-04:00", velocity_research.TARGET_FIRST),
        _row("inside", "MSFT", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST),
        _row("after", "NVDA", "2026-10-01T10:00:00-04:00", velocity_research.TARGET_FIRST),
        {"scan_id": "missing", "ticker": "AMD", "label": velocity_research.TARGET_FIRST},
    ]
    selected = design.select_independent_records(_dataset(rows), _plan())

    assert selected["independent_records"] == 1
    assert selected["records"][0]["ticker"] == "MSFT"
    assert selected["excluded"]["OUTSIDE_EVALUATION_WINDOW"] == 2
    assert selected["excluded"]["MISSING_SAMPLING_IDENTITY"] == 1


def test_naive_timestamp_is_rejected_instead_of_timezone_guessed():
    row = _row(
        "naive",
        "AAPL",
        "2026-08-20T10:00:00",
        velocity_research.TARGET_FIRST,
    )
    selected = design.select_independent_records(_dataset([row]), _plan())
    assert selected["independent_records"] == 0
    assert selected["excluded"]["MISSING_SAMPLING_IDENTITY"] == 1


def test_structural_condition_mapping_is_chart_native_and_deterministic():
    assert design.structural_condition(_row("a", "A", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="EXPANSION")) == design.CONDITION_TRENDING
    assert design.structural_condition(_row("b", "B", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="CONTINUATION")) == design.CONDITION_TRENDING
    assert design.structural_condition(_row("c", "C", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="COMPRESSION")) == design.CONDITION_COMPRESSION
    assert design.structural_condition(_row("d", "D", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="REPAIR")) == design.CONDITION_REPAIR
    assert design.structural_condition(_row("e", "E", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="TRANSITION")) == design.CONDITION_TRANSITION
    assert design.structural_condition(_row("f", "F", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="FAILURE")) == design.CONDITION_FAILURE


def test_condition_counts_are_computed_from_selected_real_4h_state():
    rows = [
        _row("a", "AAPL", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="CONTINUATION"),
        _row("b", "MSFT", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST, real_state="REPAIR"),
        _row("c", "NVDA", "2026-08-20T10:00:00-04:00", velocity_research.INVALIDATION_FIRST, real_state="FAILURE"),
    ]
    counts = design.condition_counts(rows)
    assert counts[design.CONDITION_TRENDING] == 1
    assert counts[design.CONDITION_REPAIR] == 1
    assert counts[design.CONDITION_FAILURE] == 1


def test_wilson_interval_is_bounded_and_contains_point_estimate():
    interval = design.wilson_interval(30, 40, 0.95)
    assert interval["point_pct"] == 75.0
    assert 0 <= interval["lower_pct"] < 75.0
    assert 75.0 < interval["upper_pct"] <= 100

    invalid = design.wilson_interval(2, 0, 0.95)
    assert invalid["lower_pct"] is None
    assert invalid["upper_pct"] is None


def test_confidence_gate_uses_predeclared_lower_and_upper_bounds():
    summary = {
        "real_adds_hard_block": {
            "positive_evidence_count": 38,
            "negative_evidence_count": 2,
            "evaluable_rows": 40,
        },
        "real_removes_proxy_hard_block": {
            "positive_evidence_count": 28,
            "negative_evidence_count": 2,
            "evaluable_rows": 30,
        },
    }
    gate = design.evaluate_confidence_gate(summary, _plan())
    assert gate["accepted"] is True
    assert all(check["passed"] for check in gate["checks"].values())

    stricter = design.evaluate_confidence_gate(
        summary,
        _plan(min_real_adds_block_protection_lcb_pct=99),
    )
    assert stricter["accepted"] is False


def test_forward_report_uses_independent_rows_and_requires_confidence_gate():
    rows = [
        _row("a1", "A", "2026-08-20T09:45:00-04:00", velocity_research.INVALIDATION_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, "FAILURE", cf.EFFECT_HARD_BLOCK),
        _row("a1-late", "A", "2026-08-20T14:45:00-04:00", velocity_research.TARGET_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, "FAILURE", cf.EFFECT_HARD_BLOCK),
        _row("a2", "B", "2026-08-20T10:00:00-04:00", velocity_research.TIME_BARRIER, cf.COMPARE_REAL_ADDS_BLOCK, "FAILURE", cf.EFFECT_HARD_BLOCK),
        _row("r1", "C", "2026-08-20T10:15:00-04:00", velocity_research.TARGET_FIRST, cf.COMPARE_REAL_REMOVES_BLOCK, "CONTINUATION", cf.EFFECT_SUPPORTIVE),
        _row("s1", "D", "2026-08-20T10:30:00-04:00", velocity_research.TARGET_FIRST, cf.COMPARE_SAME, "REPAIR", cf.EFFECT_REPAIRING),
    ]
    plan = _plan(
        min_real_adds_hard_block_evaluable=2,
        min_real_removes_proxy_hard_block_evaluable=1,
        min_real_adds_block_protection_lcb_pct=0,
        max_real_adds_block_target_cost_ucb_pct=100,
        min_real_removes_block_recovery_lcb_pct=0,
        max_real_removes_block_failure_ucb_pct=100,
    )
    report = design.build_forward_report(_dataset(rows), plan)

    assert report["sampling"]["raw_records"] == 5
    assert report["sampling"]["independent_records"] == 4
    assert report["sampling"]["repeated_ticker_session_rows_removed"] == 1
    assert report["confidence_gate"]["accepted"] is True
    assert report["capital_authority"] is False
    assert report["tier_authority"] is False
    assert report["automatic_promotion"] is False


def test_forward_handoff_readiness_fails_when_condition_coverage_is_missing():
    rows = [
        _row("a1", "A", "2026-08-20T09:45:00-04:00", velocity_research.INVALIDATION_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, "FAILURE", cf.EFFECT_HARD_BLOCK),
        _row("a2", "B", "2026-08-20T10:00:00-04:00", velocity_research.TIME_BARRIER, cf.COMPARE_REAL_ADDS_BLOCK, "FAILURE", cf.EFFECT_HARD_BLOCK),
        _row("r1", "C", "2026-08-20T10:15:00-04:00", velocity_research.TARGET_FIRST, cf.COMPARE_REAL_REMOVES_BLOCK, "CONTINUATION", cf.EFFECT_SUPPORTIVE),
        _row("s1", "D", "2026-08-20T10:30:00-04:00", velocity_research.TARGET_FIRST, cf.COMPARE_SAME, "CONTINUATION", cf.EFFECT_SUPPORTIVE),
    ]
    plan = _plan(
        market_condition_minimums={"TRENDING": 10, "FAILURE": 10},
        min_real_adds_block_protection_lcb_pct=0,
        max_real_adds_block_target_cost_ucb_pct=100,
        min_real_removes_block_recovery_lcb_pct=0,
        max_real_removes_block_failure_ucb_pct=100,
    )
    report = design.build_forward_report(_dataset(rows), plan)
    assert report["base_study"]["market_condition_coverage"]["accepted"] is False
    assert report["forward_handoff_review_ready"] is False


def test_forward_design_does_not_mutate_inputs():
    dataset = _dataset([
        _row("x", "AAPL", "2026-08-20T10:00:00-04:00", velocity_research.TARGET_FIRST)
    ])
    plan = _plan()
    dataset_before = deepcopy(dataset)
    plan_before = deepcopy(plan)

    design.build_forward_report(dataset, plan)

    assert dataset == dataset_before
    assert plan == plan_before

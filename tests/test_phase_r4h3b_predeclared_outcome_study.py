"""R4H-3B — predeclared chronological outcome-study regressions."""

from copy import deepcopy

from src import four_hour_counterfactual as cf
from src import four_hour_outcome_study as study
from src import velocity_research


def _plan(**overrides):
    base = {
        "name": "r4h-location-study",
        "version": "1",
        "frozen_before_outcome_review": True,
        "chronological_out_of_sample": True,
        "min_evaluable_records": 4,
        "min_real_adds_hard_block_evaluable": 2,
        "min_real_removes_proxy_hard_block_evaluable": 1,
        "max_ambiguous_or_censored_pct": 20,
        "max_comparison_unavailable_pct": 20,
    }
    base.update(overrides)
    return base


def _cf(comparison, real_effect=cf.EFFECT_SUPPORTIVE):
    return {
        "version": cf.VERSION,
        "comparison": comparison,
        "proxy": {"location_effect": cf.EFFECT_SUPPORTIVE},
        "real": {"location_effect": real_effect},
    }


def _row(label, comparison=cf.COMPARE_SAME, real_effect=cf.EFFECT_SUPPORTIVE, **extra):
    row = {
        "scan_id": extra.pop("scan_id", "s1"),
        "ticker": extra.pop("ticker", "AAPL"),
        "label": label,
        "setup_family": extra.pop("setup_family", "BREAK_RETEST_CONTINUATION"),
        "final_tier": extra.pop("final_tier", "STARTER"),
        "four_hour_counterfactual": _cf(comparison, real_effect),
    }
    row.update(extra)
    return row


def _dataset(rows):
    return {"version": cf.VERSION, "records": list(rows)}


def _supportive_rows():
    return [
        _row(velocity_research.INVALIDATION_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, cf.EFFECT_HARD_BLOCK, scan_id="a1"),
        _row(velocity_research.TIME_BARRIER, cf.COMPARE_REAL_ADDS_BLOCK, cf.EFFECT_HARD_BLOCK, scan_id="a2"),
        _row(velocity_research.TARGET_FIRST, cf.COMPARE_REAL_REMOVES_BLOCK, cf.EFFECT_SUPPORTIVE, scan_id="r1"),
        _row(velocity_research.TARGET_FIRST, cf.COMPARE_SAME, cf.EFFECT_SUPPORTIVE, scan_id="s1"),
        _row(velocity_research.AMBIGUOUS_SAME_SESSION, cf.COMPARE_SAME, cf.EFFECT_REPAIRING, scan_id="x1"),
    ]


def test_plan_requires_explicit_frozen_chronological_sample_rules():
    invalid = study.validate_study_plan({"name": "x", "version": "1"})
    assert invalid["valid"] is False
    assert "PLAN_NOT_FROZEN_BEFORE_OUTCOME_REVIEW" in invalid["errors"]
    assert "CHRONOLOGICAL_OUT_OF_SAMPLE_NOT_DECLARED" in invalid["errors"]
    assert any("min_evaluable_records" in err for err in invalid["errors"])

    valid = study.validate_study_plan(_plan())
    assert valid["valid"] is True
    assert valid["sample_thresholds"]["min_evaluable_records"] == 4


def test_terminal_outcome_law_keeps_timeout_evaluable_and_censors_partial_history():
    summary = study.summarize_outcomes(_dataset([
        _row(velocity_research.TARGET_FIRST),
        _row(velocity_research.INVALIDATION_FIRST),
        _row(velocity_research.TIME_BARRIER),
        _row(velocity_research.AMBIGUOUS_SAME_SESSION),
        _row(velocity_research.INCOMPLETE_HORIZON),
        _row(velocity_research.INVALID_DATA),
    ]))

    assert summary["evaluable_records"] == 3
    assert summary["ambiguous_or_censored_records"] == 2
    assert summary["outcome_counts"][velocity_research.INVALID_DATA] == 1


def test_real_adds_hard_block_reports_protection_and_opportunity_cost():
    rows = [
        _row(velocity_research.INVALIDATION_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, cf.EFFECT_HARD_BLOCK),
        _row(velocity_research.TIME_BARRIER, cf.COMPARE_REAL_ADDS_BLOCK, cf.EFFECT_HARD_BLOCK),
        _row(velocity_research.TARGET_FIRST, cf.COMPARE_REAL_ADDS_BLOCK, cf.EFFECT_HARD_BLOCK),
    ]
    metrics = study.summarize_outcomes(_dataset(rows))["real_adds_hard_block"]

    assert metrics["evaluable_rows"] == 3
    assert metrics["positive_evidence_label"] == "OBJECTIVE_FAILURE_PROTECTION"
    assert metrics["positive_evidence_count"] == 2
    assert metrics["positive_evidence_pct"] == round(2 / 3 * 100, 4)
    assert metrics["negative_evidence_label"] == "TARGET_OPPORTUNITY_COST"
    assert metrics["negative_evidence_count"] == 1


def test_real_removes_proxy_block_reports_recovery_and_failure_exposure():
    rows = [
        _row(velocity_research.TARGET_FIRST, cf.COMPARE_REAL_REMOVES_BLOCK),
        _row(velocity_research.INVALIDATION_FIRST, cf.COMPARE_REAL_REMOVES_BLOCK),
        _row(velocity_research.TIME_BARRIER, cf.COMPARE_REAL_REMOVES_BLOCK),
    ]
    metrics = study.summarize_outcomes(_dataset(rows))["real_removes_proxy_hard_block"]

    assert metrics["positive_evidence_label"] == "TARGET_RECOVERY"
    assert metrics["positive_evidence_count"] == 1
    assert metrics["negative_evidence_label"] == "OBJECTIVE_FAILURE_EXPOSURE"
    assert metrics["negative_evidence_count"] == 2


def test_nonfatal_real_states_are_reported_separately():
    rows = [
        _row(velocity_research.TARGET_FIRST, real_effect=cf.EFFECT_SUPPORTIVE),
        _row(velocity_research.TIME_BARRIER, real_effect=cf.EFFECT_REPAIRING),
        _row(velocity_research.INVALIDATION_FIRST, real_effect=cf.EFFECT_NO_EDGE),
        _row(velocity_research.TARGET_FIRST, real_effect=cf.EFFECT_EXTENDED),
    ]
    effects = study.summarize_outcomes(_dataset(rows))["nonfatal_real_effects"]

    assert effects[cf.EFFECT_SUPPORTIVE]["target_first_rate_pct"] == 100.0
    assert effects[cf.EFFECT_REPAIRING]["target_first_rate_pct"] == 0.0
    assert effects[cf.EFFECT_NO_EDGE]["evaluable_rows"] == 1
    assert effects[cf.EFFECT_EXTENDED]["outcome_counts"][velocity_research.TARGET_FIRST] == 1


def test_sample_readiness_uses_only_predeclared_thresholds():
    summary = study.summarize_outcomes(_dataset(_supportive_rows()))
    ready = study.evaluate_sample_readiness(summary, _plan())
    assert ready["accepted"] is True
    assert all(check["passed"] for check in ready["checks"].values())

    too_strict = study.evaluate_sample_readiness(
        summary,
        _plan(min_evaluable_records=100),
    )
    assert too_strict["accepted"] is False
    assert too_strict["reason"] == study.STUDY_SAMPLE_INSUFFICIENT


def test_effect_thresholds_are_optional_and_never_invented():
    summary = study.summarize_outcomes(_dataset(_supportive_rows()))
    descriptive = study.evaluate_effect_thresholds(summary, _plan())
    assert descriptive["declared"] is False
    assert descriptive["reason"] == study.STUDY_DESCRIPTIVE_ONLY

    declared = _plan(
        max_real_adds_block_target_opportunity_cost_pct=0,
        min_real_adds_block_objective_failure_protection_pct=100,
        min_real_removes_block_target_recovery_pct=100,
        max_real_removes_block_objective_failure_exposure_pct=0,
    )
    evaluated = study.evaluate_effect_thresholds(summary, declared)
    assert evaluated["declared"] is True
    assert evaluated["accepted"] is True


def test_market_condition_coverage_requires_separately_auditable_counts():
    plan = _plan(market_condition_minimums={"TREND": 20, "CHOP": 10})
    missing = study.evaluate_market_condition_coverage(plan, None)
    assert missing["required"] is True
    assert missing["accepted"] is False

    covered = study.evaluate_market_condition_coverage(
        plan,
        {"TREND": 25, "CHOP": 11},
    )
    assert covered["accepted"] is True


def test_report_is_descriptive_when_sample_is_ready_but_effect_plan_absent():
    report = study.build_study_report(_dataset(_supportive_rows()), _plan())
    assert report["sample_readiness"]["accepted"] is True
    assert report["effect_evaluation"]["declared"] is False
    assert report["study_decision"] == study.STUDY_DESCRIPTIVE_ONLY
    assert report["narrow_hard_block_handoff_review_ready"] is False


def test_report_can_mark_narrow_evidence_supportive_but_never_grants_authority():
    plan = _plan(
        max_real_adds_block_target_opportunity_cost_pct=0,
        min_real_adds_block_objective_failure_protection_pct=100,
        min_real_removes_block_target_recovery_pct=100,
        max_real_removes_block_objective_failure_exposure_pct=0,
    )
    report = study.build_study_report(_dataset(_supportive_rows()), plan)

    assert report["study_decision"] == study.STUDY_NARROW_SUPPORTIVE
    assert report["narrow_hard_block_handoff_review_ready"] is True
    assert report["capital_authority"] is False
    assert report["tier_authority"] is False
    assert report["automatic_promotion"] is False
    assert report["full_tier_counterfactual_supported"] is False
    assert report["full_4h_replacement_supported"] is False


def test_required_market_coverage_can_block_narrow_supportive_result():
    plan = _plan(
        max_real_adds_block_target_opportunity_cost_pct=0,
        min_real_adds_block_objective_failure_protection_pct=100,
        market_condition_minimums={"TREND": 10, "CHOP": 10},
    )
    report = study.build_study_report(
        _dataset(_supportive_rows()),
        plan,
        coverage_counts={"TREND": 15, "CHOP": 2},
    )
    assert report["market_condition_coverage"]["accepted"] is False
    assert report["study_decision"] == study.STUDY_NARROW_NOT_SUPPORTIVE


def test_full_r4h2_promotion_flags_remain_unsatisfied_by_location_only_study():
    plan = _plan(
        max_real_adds_block_target_opportunity_cost_pct=0,
        min_real_adds_block_objective_failure_protection_pct=100,
    )
    report = study.build_study_report(_dataset(_supportive_rows()), plan)
    flags = report["r4h2_validation_projection"]

    assert flags["chronological_out_of_sample"] is True
    assert flags["outcome_linked"] is True
    assert flags["counterfactual_proxy_vs_real"] is True
    assert flags["sample_size_accepted_under_predeclared_plan"] is True
    assert flags["real_4h_improves_or_preserves_precision"] is False
    assert flags["real_4h_does_not_materially_damage_recall"] is False
    assert flags["capital_integrity_regressions_green"] is False


def test_study_engine_does_not_mutate_dataset_plan_or_coverage_payloads():
    dataset = _dataset(_supportive_rows())
    plan = _plan()
    coverage = {"TREND": 5}
    before_dataset = deepcopy(dataset)
    before_plan = deepcopy(plan)
    before_coverage = deepcopy(coverage)

    study.build_study_report(dataset, plan, coverage)

    assert dataset == before_dataset
    assert plan == before_plan
    assert coverage == before_coverage

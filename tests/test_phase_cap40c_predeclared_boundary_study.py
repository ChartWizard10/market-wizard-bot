"""CAP-40C — independent boundary-study and uncertainty regressions."""

import ast
import json
from copy import deepcopy
from pathlib import Path

from src import capacity_boundary_observation as boundary
from src import capacity_boundary_study as study
from src import velocity_research


def _plan(**overrides):
    base = {
        "name": "cap40-test",
        "version": "1",
        "declared_before_observation_review": True,
        "no_favorable_early_stop": True,
        "sampling_unit": study.SAMPLING_UNIT,
        "session_timezone": "America/New_York",
        "evaluation_start_date": "2026-08-20",
        "evaluation_end_date": "2026-08-31",
        "final_review_not_before_date": "2026-09-08",
        "confidence_level": 0.95,
        "min_evaluable_total": 4,
        "min_baseline_evaluable": 2,
        "min_shadow_evaluable": 2,
        "max_ambiguous_or_censored_pct": 25,
        "max_invalid_pct": 25,
        "max_shadow_unknown_family_pct": 50,
        "min_shadow_target_first_count": 1,
        "min_shadow_target_rate_pct": 25,
        "min_shadow_target_lcb_pct": 0,
        "min_shadow_minus_baseline_target_diff_lcb_pct": -100,
        "min_shadow_feasibility_supported_or_partial_pct": 50,
    }
    base.update(overrides)
    return base


def _row(
    ticker,
    scan_id,
    observed_at,
    band,
    label=velocity_research.TARGET_FIRST,
    family="BREAK_RETEST_CONTINUATION",
    feasibility=velocity_research.FEASIBILITY_SUPPORTED,
):
    return {
        "scan_id": scan_id,
        "ticker": ticker,
        "observed_at": observed_at,
        "band": band,
        "label": label,
        "setup_family": family,
        "feasibility_status": feasibility,
        "rank": 25 if band == boundary.BAND_BASELINE_EDGE else 31,
        "entry_price": 100.0,
        "invalidation_level": 95.0,
        "target_return_pct": 8.0,
        "horizon_sessions": 5,
    }


def _supportive_dataset():
    return {
        "version": "CAP-40B",
        "records": [
            _row("B1", "b1", "2026-08-20T13:35:00", boundary.BAND_BASELINE_EDGE),
            _row(
                "B2",
                "b2",
                "2026-08-20T13:36:00",
                boundary.BAND_BASELINE_EDGE,
                velocity_research.INVALIDATION_FIRST,
            ),
            _row("S1", "s1", "2026-08-20T13:35:00", boundary.BAND_SHADOW_INCREMENT),
            _row("S2", "s2", "2026-08-20T13:36:00", boundary.BAND_SHADOW_INCREMENT),
        ],
    }


def test_plan_requires_complete_predeclared_contract():
    invalid = study.validate_study_plan({"name": "x", "version": "1"})
    assert invalid["valid"] is False
    assert "PLAN_NOT_DECLARED_BEFORE_OBSERVATION_REVIEW" in invalid["errors"]
    assert "NO_FAVORABLE_EARLY_STOP_NOT_DECLARED" in invalid["errors"]
    assert "INVALID_OR_MISSING_SAMPLING_UNIT" in invalid["errors"]

    valid = study.validate_study_plan(_plan())
    assert valid["valid"] is True
    assert valid["sampling_unit"] == study.SAMPLING_UNIT
    assert valid["confidence_level"] == 0.95


def test_final_review_date_must_follow_observation_window():
    invalid = study.validate_study_plan(
        _plan(final_review_not_before_date="2026-08-31")
    )
    assert invalid["valid"] is False
    assert "FINAL_REVIEW_DATE_MUST_FOLLOW_EVALUATION_END" in invalid["errors"]


def test_naive_utc_timestamp_maps_to_new_york_session_date():
    # 00:30 UTC on Aug 21 is still the Aug 20 U.S. session date.
    data = {
        "records": [
            _row(
                "TEST",
                "s1",
                "2026-08-21T00:30:00",
                boundary.BAND_SHADOW_INCREMENT,
            )
        ]
    }
    selected = study.select_independent_records(
        data,
        _plan(evaluation_end_date="2026-08-20"),
    )
    assert selected["independent_records"] == 1
    assert selected["excluded"]["OUTSIDE_EVALUATION_WINDOW"] == 0


def test_offset_aware_timestamp_uses_same_absolute_session_logic():
    data = {
        "records": [
            _row(
                "TEST",
                "s1",
                "2026-08-20T20:30:00-04:00",
                boundary.BAND_SHADOW_INCREMENT,
            )
        ]
    }
    selected = study.select_independent_records(
        data,
        _plan(evaluation_end_date="2026-08-20"),
    )
    assert selected["independent_records"] == 1


def test_first_ticker_session_observation_wins_even_if_band_changes_later():
    data = {
        "records": [
            _row(
                "TEST",
                "early",
                "2026-08-20T13:35:00",
                boundary.BAND_BASELINE_EDGE,
                velocity_research.INVALIDATION_FIRST,
            ),
            _row(
                "TEST",
                "late",
                "2026-08-20T14:35:00",
                boundary.BAND_SHADOW_INCREMENT,
                velocity_research.TARGET_FIRST,
            ),
        ]
    }
    selected = study.select_independent_records(data, _plan())

    assert selected["independent_records"] == 1
    assert selected["repeated_ticker_session_rows_removed"] == 1
    assert selected["band_crossovers_removed"] == 1
    assert selected["records"][0]["scan_id"] == "early"
    assert selected["records"][0]["band"] == boundary.BAND_BASELINE_EDGE


def test_selection_is_label_invariant():
    data = {
        "records": [
            _row(
                "TEST",
                "early",
                "2026-08-20T13:35:00",
                boundary.BAND_SHADOW_INCREMENT,
                velocity_research.INVALIDATION_FIRST,
            ),
            _row(
                "TEST",
                "late",
                "2026-08-20T14:35:00",
                boundary.BAND_SHADOW_INCREMENT,
                velocity_research.TARGET_FIRST,
            ),
        ]
    }
    first = study.select_independent_records(data, _plan())
    mutated = deepcopy(data)
    mutated["records"][0]["label"] = velocity_research.TARGET_FIRST
    mutated["records"][1]["label"] = velocity_research.INVALIDATION_FIRST
    second = study.select_independent_records(mutated, _plan())

    assert [row["scan_id"] for row in first["records"]] == ["early"]
    assert [row["scan_id"] for row in second["records"]] == ["early"]


def test_wilson_interval_is_bounded_and_reflects_sample_size():
    small = study.wilson_interval(7, 10, 0.95)
    large = study.wilson_interval(70, 100, 0.95)

    assert 0 <= small["lower_pct"] <= small["point_pct"] <= small["upper_pct"] <= 100
    assert 0 <= large["lower_pct"] <= large["point_pct"] <= large["upper_pct"] <= 100
    assert (large["upper_pct"] - large["lower_pct"]) < (
        small["upper_pct"] - small["lower_pct"]
    )


def test_summary_keeps_boundary_bands_separate_and_computes_difference_bounds():
    rows = _supportive_dataset()["records"]
    summary = study.summarize_independent_records(rows, 0.95)

    assert summary["baseline_edge"]["evaluable"] == 2
    assert summary["baseline_edge"]["target_first"] == 1
    assert summary["shadow_increment"]["evaluable"] == 2
    assert summary["shadow_increment"]["target_first"] == 2
    diff = summary["shadow_minus_baseline_target_rate"]
    assert diff["point_pct"] == 50.0
    assert diff["lower_pct"] is not None
    assert diff["upper_pct"] is not None


def test_ambiguous_censored_and_invalid_rows_are_not_evaluable():
    rows = [
        _row("A", "a", "2026-08-20T13:35:00", boundary.BAND_BASELINE_EDGE),
        _row(
            "B",
            "b",
            "2026-08-20T13:36:00",
            boundary.BAND_BASELINE_EDGE,
            velocity_research.AMBIGUOUS_SAME_SESSION,
        ),
        _row(
            "C",
            "c",
            "2026-08-20T13:37:00",
            boundary.BAND_SHADOW_INCREMENT,
            velocity_research.INCOMPLETE_HORIZON,
        ),
        _row(
            "D",
            "d",
            "2026-08-20T13:38:00",
            boundary.BAND_SHADOW_INCREMENT,
            velocity_research.INVALID_DATA,
        ),
    ]
    summary = study.summarize_independent_records(rows, 0.95)

    assert summary["evaluable_total"] == 1
    assert summary["ambiguous_or_censored"] == 2
    assert summary["invalid"] == 1


def test_review_maturity_blocks_early_favorable_readout():
    plan = _plan()
    before = study.evaluate_review_maturity(plan, "2026-09-07")
    mature = study.evaluate_review_maturity(plan, "2026-09-08")

    assert before["accepted"] is False
    assert before["reason"] == study.DECISION_WINDOW_NOT_MATURE
    assert mature["accepted"] is True


def test_sample_readiness_uses_only_declared_thresholds():
    selection = study.select_independent_records(_supportive_dataset(), _plan())
    summary = study.summarize_independent_records(selection["records"], 0.95)

    ready = study.evaluate_sample_readiness(summary, _plan())
    assert ready["accepted"] is True

    strict = study.evaluate_sample_readiness(
        summary,
        _plan(min_shadow_evaluable=100),
    )
    assert strict["accepted"] is False
    assert strict["reason"] == study.DECISION_SAMPLE_INSUFFICIENT


def test_effect_gate_can_support_paid_experiment_review_but_not_cap_change():
    data = _supportive_dataset()
    report = study.build_study_report(data, _plan(), "2026-09-08")

    assert report["study_decision"] == study.DECISION_PAID_EXPERIMENT_REVIEW_READY
    assert report["paid_experiment_review_ready"] is True
    assert report["candidate_cap_authority"] is False
    assert report["model_call_authority"] is False
    assert report["automatic_cap_change"] is False
    assert report["permanent_cap_increase_supported"] is False
    assert report["production_cap"] == 30
    assert report["proposed_experiment_cap"] == 40


def test_effect_gate_rejects_weak_shadow_target_evidence():
    data = _supportive_dataset()
    data["records"][2]["label"] = velocity_research.INVALIDATION_FIRST
    data["records"][3]["label"] = velocity_research.TIME_BARRIER
    report = study.build_study_report(
        data,
        _plan(min_shadow_target_rate_pct=50),
        "2026-09-08",
    )

    assert report["sample_readiness"]["accepted"] is True
    assert report["effect_evidence"]["accepted"] is False
    assert report["study_decision"] == study.DECISION_EVIDENCE_NOT_SUPPORTIVE


def test_actual_committed_plan_is_valid_and_forward_dated():
    plan = json.loads(
        Path("research/plans/cap40_boundary_oos_v1.json").read_text(encoding="utf-8")
    )
    validated = study.validate_study_plan(plan)

    assert validated["valid"] is True
    assert validated["evaluation_start_date"] == "2026-08-20"
    assert validated["evaluation_end_date"] == "2026-09-30"
    assert validated["final_review_not_before_date"] == "2026-10-08"
    assert validated["sampling_unit"] == study.SAMPLING_UNIT
    assert validated["sample_thresholds"]["min_shadow_evaluable"] == 90
    assert validated["effect_thresholds"]["min_shadow_target_rate_pct"] == 35


def test_study_engine_does_not_mutate_dataset_or_plan():
    data = _supportive_dataset()
    plan = _plan()
    before_data = deepcopy(data)
    before_plan = deepcopy(plan)

    study.build_study_report(data, plan, "2026-09-08")

    assert data == before_data
    assert plan == before_plan


def test_study_source_has_no_network_model_or_live_mutation_imports():
    path = Path("src/capacity_boundary_study.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    calls = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    for prefix in (
        "openai",
        "anthropic",
        "requests",
        "aiohttp",
        "discord",
        "src.scheduler",
        "src.state_store",
        "src.discord_alerts",
        "src.claude_client",
    ):
        assert not any(module.startswith(prefix) for module in imports)

    for forbidden in (
        "async_claude_scan",
        "claude_call",
        "send_alert",
        "record_alert",
        "check_alert",
        "batch_download",
        "fetch_ticker",
        "apply_ladder_arbitration",
    ):
        assert forbidden not in calls

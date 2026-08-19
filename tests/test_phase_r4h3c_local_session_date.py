"""R4H-3C — original-offset session-date sampling regression."""

from src import four_hour_counterfactual as cf
from src import four_hour_study_design as design
from src import velocity_research


def _plan():
    return {
        "name": "session-date-test",
        "version": "1",
        "predeclared_before_outcome_review": True,
        "chronological_out_of_sample": True,
        "sampling_unit": design.SAMPLING_FIRST_TICKER_SESSION,
        "evaluation_start_date": "2026-08-20",
        "evaluation_end_date": "2026-08-20",
        "confidence_level": 0.95,
        "min_evaluable_records": 1,
        "min_real_adds_hard_block_evaluable": 0,
        "min_real_removes_proxy_hard_block_evaluable": 0,
        "max_ambiguous_or_censored_pct": 100,
        "max_comparison_unavailable_pct": 100,
        "max_real_adds_block_target_opportunity_cost_pct": 100,
        "min_real_adds_block_objective_failure_protection_pct": 0,
        "min_real_removes_block_target_recovery_pct": 0,
        "max_real_removes_block_objective_failure_exposure_pct": 100,
        "min_real_adds_block_protection_lcb_pct": 0,
        "max_real_adds_block_target_cost_ucb_pct": 100,
        "min_real_removes_block_recovery_lcb_pct": 0,
        "max_real_removes_block_failure_ucb_pct": 100,
        "market_condition_minimums": {"TRENDING": 0},
    }


def _row(scan_id, observed_at):
    return {
        "scan_id": scan_id,
        "ticker": "AAPL",
        "observed_at": observed_at,
        "label": velocity_research.TARGET_FIRST,
        "four_hour_counterfactual": {
            "comparison": cf.COMPARE_SAME,
            "real": {
                "location_effect": cf.EFFECT_SUPPORTIVE,
                "raw_structural_state": "CONTINUATION",
            },
            "proxy": {"location_effect": cf.EFFECT_SUPPORTIVE},
        },
    }


def test_original_offset_date_is_sampling_session_even_when_utc_rolls_next_day():
    dataset = {
        "version": cf.VERSION,
        "records": [
            _row("early", "2026-08-20T19:15:00-04:00"),
            _row("late", "2026-08-20T21:30:00-04:00"),
        ],
    }

    selected = design.select_independent_records(dataset, _plan())

    assert selected["window_eligible_records"] == 2
    assert selected["independent_records"] == 1
    assert selected["repeated_ticker_session_rows_removed"] == 1
    assert selected["records"][0]["scan_id"] == "early"

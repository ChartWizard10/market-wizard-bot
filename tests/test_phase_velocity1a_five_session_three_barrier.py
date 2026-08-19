"""VELOCITY-1A five-session/+8% research contract tests."""

import ast
from pathlib import Path

import pytest

from src.velocity_research import (
    AMBIGUOUS_SAME_SESSION,
    DEFAULT_HORIZON_SESSIONS,
    DEFAULT_TARGET_RETURN_PCT,
    FEASIBILITY_BLOCKED_PATH,
    FEASIBILITY_PARTIAL,
    FEASIBILITY_RANGE_STRETCHED,
    FEASIBILITY_SUPPORTED,
    INCOMPLETE_HORIZON,
    INVALIDATION_FIRST,
    TARGET_FIRST,
    TIME_BARRIER,
    build_feasibility_snapshot,
    label_alert_three_barrier,
    label_three_barrier_outcome,
    summarize_three_barrier_labels,
)


def _bar(high, low, close=100.0, open_=100.0):
    return {"open": open_, "high": high, "low": low, "close": close}


def test_constitution_defaults_are_exact_research_objective():
    assert DEFAULT_TARGET_RETURN_PCT == 8.0
    assert DEFAULT_HORIZON_SESSIONS == 5


def test_feasibility_supported_requires_known_path_and_range_proxy():
    out = build_feasibility_snapshot({
        "current_price": 100.0,
        "atr": 2.0,
        "overhead_level": 112.0,
        "targets": [{"label": "T1", "level": 112.0}],
    })
    assert out["status"] == FEASIBILITY_SUPPORTED
    assert out["target_price"] == 108.0
    assert out["known_path_room_pct"] == 12.0
    assert out["session_atr_capacity_pct"] == 10.0
    assert out["path_supports_target"] is True
    assert out["range_capacity_supports_target"] is True
    assert out["research_only"] is True
    assert out["capital_authority"] is False
    assert out["tier_authority"] is False
    assert out["forecast_authority"] is False


def test_feasibility_blocked_when_nearest_known_ceiling_is_inside_8_percent():
    out = build_feasibility_snapshot({
        "current_price": 100.0,
        "atr": 3.0,
        "overhead_level": 106.0,
        "targets": [{"level": 110.0}],
    })
    assert out["status"] == FEASIBILITY_BLOCKED_PATH
    assert out["known_path_ceiling"] == 106.0
    assert out["known_path_room_pct"] == 6.0
    assert out["path_supports_target"] is False


def test_feasibility_range_stretched_when_path_open_but_five_atr_proxy_below_target():
    out = build_feasibility_snapshot({
        "current_price": 100.0,
        "atr": 1.0,
        "overhead_level": 115.0,
    })
    assert out["status"] == FEASIBILITY_RANGE_STRETCHED
    assert out["session_atr_capacity_pct"] == 5.0
    assert out["required_move_atr"] == 8.0


def test_feasibility_missing_one_side_is_partial_not_false_certainty():
    out = build_feasibility_snapshot({
        "current_price": 100.0,
        "atr": 2.0,
        "overhead_level": None,
        "targets": [],
    })
    assert out["status"] == FEASIBILITY_PARTIAL
    assert out["path_supports_target"] is None
    assert out["range_capacity_supports_target"] is True


def test_target_first_within_five_sessions():
    bars = [
        _bar(102, 98, 101),
        _bar(105, 99, 104),
        _bar(108.1, 101, 107),
        _bar(109, 104, 108),
        _bar(110, 105, 109),
    ]
    out = label_three_barrier_outcome(100, 95, bars)
    assert out["label"] == TARGET_FIRST
    assert out["target_price"] == pytest.approx(108.0)
    assert out["terminal_session"] == 3
    assert out["sessions_observed"] == 3


def test_invalidation_first_within_horizon():
    bars = [
        _bar(103, 99, 101),
        _bar(104, 94.9, 96),
        _bar(109, 96, 108),
    ]
    out = label_three_barrier_outcome(100, 95, bars)
    assert out["label"] == INVALIDATION_FIRST
    assert out["terminal_session"] == 2


def test_same_session_target_and_stop_is_ambiguous_not_guessed():
    bars = [_bar(109, 94, 101)]
    out = label_three_barrier_outcome(100, 95, bars)
    assert out["label"] == AMBIGUOUS_SAME_SESSION
    assert out["terminal_session"] == 1


def test_full_five_sessions_without_price_barrier_is_time_barrier():
    bars = [
        _bar(102, 98, 101),
        _bar(103, 97, 102),
        _bar(104, 96, 103),
        _bar(105, 96, 104),
        _bar(106, 96, 105),
    ]
    out = label_three_barrier_outcome(100, 95, bars)
    assert out["label"] == TIME_BARRIER
    assert out["terminal_session"] == 5
    assert out["time_barrier_close_return_pct"] == pytest.approx(5.0)


def test_partial_future_history_is_not_mislabeled_as_timeout():
    bars = [_bar(102, 98, 101), _bar(103, 97, 102), _bar(104, 96, 103)]
    out = label_three_barrier_outcome(100, 95, bars)
    assert out["label"] == INCOMPLETE_HORIZON
    assert out["sessions_observed"] == 3
    assert out["terminal_session"] is None


def test_terminal_hit_can_be_valid_before_full_future_history_exists():
    out = label_three_barrier_outcome(100, 95, [_bar(108.2, 99, 107)])
    assert out["label"] == TARGET_FIRST
    assert out["sessions_observed"] == 1


def test_alert_wrapper_records_entry_basis_and_capital_truth_without_filtering_watch_observation():
    alert = {
        "ticker": "TEST",
        "final_tier": "NEAR_ENTRY",
        "scan_price": 100.0,
        "trigger_level": 101.0,
        "invalidation_level": 95.0,
        "setup_family_primary": "VCP_BREAK_RETEST",
    }
    bars = [_bar(108.5, 99, 107)]
    out = label_alert_three_barrier(alert, bars)
    assert out["label"] == TARGET_FIRST
    assert out["entry_price_source"] == "scan_price"
    assert out["capital_authorized_at_observation"] is False
    assert out["setup_family"] == "VCP_BREAK_RETEST"


def test_alert_wrapper_marks_starter_and_snipe_as_capital_observations():
    for tier in ("STARTER", "SNIPE_IT"):
        out = label_alert_three_barrier({
            "ticker": "TEST",
            "final_tier": tier,
            "scan_price": 100.0,
            "invalidation_level": 95.0,
        }, [_bar(108.1, 99, 107)])
        assert out["capital_authorized_at_observation"] is True


def test_summary_attributes_results_by_tier_and_family():
    rows = [
        {
            "label": TARGET_FIRST,
            "alert_tier": "SNIPE_IT",
            "setup_family": "BREAK_RETEST_CONTINUATION",
        },
        {
            "label": INVALIDATION_FIRST,
            "alert_tier": "STARTER",
            "setup_family": "SMA_CRADLE_CONTINUATION",
        },
        {
            "label": TIME_BARRIER,
            "alert_tier": "STARTER",
            "setup_family": "SMA_CRADLE_CONTINUATION",
        },
    ]
    out = summarize_three_barrier_labels(rows)
    assert out["total"] == 3
    assert out["completed_unambiguous"] == 3
    assert out["target_first_rate_completed_pct"] == pytest.approx(33.33)
    assert out["by_tier"]["STARTER"]["total"] == 2
    assert out["by_setup_family"]["SMA_CRADLE_CONTINUATION"]["total"] == 2
    assert out["research_only"] is True


def test_velocity_module_is_pure_and_has_no_live_scanner_imports():
    path = Path("src/velocity_research.py")
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = {"src", "discord", "yfinance", "requests", "aiohttp", "anthropic", "openai"}
    assert all(name.split(".")[0] not in forbidden for name in imports)

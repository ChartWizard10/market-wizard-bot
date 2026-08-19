"""VELOCITY-1 five-session / +8% three-barrier regression tests."""

import ast
from pathlib import Path

import pytest

from src.velocity_validation import (
    AMBIGUOUS_SAME_SESSION,
    DEFAULT_SESSION_LIMIT,
    DEFAULT_TARGET_RETURN_PCT,
    ENTRY_SOURCE_EXPLICIT,
    ENTRY_SOURCE_SCAN,
    ENTRY_SOURCE_TRIGGER,
    INCOMPLETE_HORIZON,
    INVALID_DATA,
    STOP_BEFORE_TARGET,
    TARGET_BEFORE_STOP,
    TIMEOUT,
    build_velocity_research_snapshot,
    evaluate_five_session_barriers,
    to_forward_outcome_block,
)


def _record(**overrides):
    out = {
        "ticker": "TEST",
        "final_tier": "STARTER",
        "scan_price": 100.0,
        "trigger_level": 101.0,
        "invalidation_level": 96.0,
        "atr": 2.0,
        "targets": [
            {"label": "T1", "level": 106.0, "reason": "near liquidity"},
            {"label": "T2", "level": 112.0, "reason": "next pool"},
        ],
        "overhead_status": "clear",
    }
    out.update(overrides)
    return out


def _bar(high, low, *, open_=100.0, close=100.0):
    return {"open": open_, "high": high, "low": low, "close": close}


def test_default_objective_is_exactly_plus_8_percent_with_five_session_deadline():
    snapshot = build_velocity_research_snapshot(_record())
    assert snapshot["target_return_pct"] == DEFAULT_TARGET_RETURN_PCT == 8.0
    assert snapshot["session_limit"] == DEFAULT_SESSION_LIMIT == 5
    assert snapshot["entry_price"] == 100.0
    assert snapshot["velocity_target_price"] == 108.0
    assert snapshot["research_only"] is True
    assert snapshot["capital_authority"] is False


def test_snapshot_records_raw_velocity_geometry_without_unvalidated_feasibility_gate():
    snapshot = build_velocity_research_snapshot(_record())
    assert snapshot["entry_price_source"] == ENTRY_SOURCE_SCAN
    assert snapshot["structural_risk_pct"] == 4.0
    assert snapshot["rr_to_velocity_target"] == 2.0
    assert snapshot["atr_pct"] == 2.0
    assert snapshot["required_move_atr"] == 4.0
    assert snapshot["max_mapped_upside_pct"] == 12.0
    assert snapshot["mapped_target_reaches_velocity_target"] is True
    assert "feasible" not in {str(k).lower() for k in snapshot}


def test_explicit_entry_price_outranks_scan_price_and_source_is_auditable():
    snapshot = build_velocity_research_snapshot(
        _record(entry_price=102.0, scan_price=100.0, trigger_level=101.0)
    )
    assert snapshot["entry_price"] == 102.0
    assert snapshot["entry_price_source"] == ENTRY_SOURCE_EXPLICIT
    assert snapshot["velocity_target_price"] == pytest.approx(110.16)


def test_scan_price_outranks_trigger_for_alert_time_research_label():
    snapshot = build_velocity_research_snapshot(
        _record(scan_price=99.0, trigger_level=101.0)
    )
    assert snapshot["entry_price"] == 99.0
    assert snapshot["entry_price_source"] == ENTRY_SOURCE_SCAN


def test_trigger_is_fallback_when_scan_price_is_missing():
    record = _record(scan_price=None, trigger_level=101.0)
    snapshot = build_velocity_research_snapshot(record)
    assert snapshot["entry_price"] == 101.0
    assert snapshot["entry_price_source"] == ENTRY_SOURCE_TRIGGER


def test_target_hits_before_structural_stop_within_five_sessions():
    bars = [
        _bar(102.0, 99.0),
        _bar(104.0, 98.0),
        _bar(108.5, 97.0),
        _bar(109.0, 98.0),
        _bar(110.0, 99.0),
    ]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == TARGET_BEFORE_STOP
    assert result["target_hit"] is True
    assert result["stop_hit"] is False
    assert result["terminal_session"] == 3
    assert result["target_hit_session"] == 3
    assert result["decisive"] is True


def test_structural_stop_hits_before_plus_8_target():
    bars = [
        _bar(102.0, 99.0),
        _bar(103.0, 95.5),
        _bar(109.0, 97.0),
        _bar(110.0, 98.0),
        _bar(111.0, 99.0),
    ]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == STOP_BEFORE_TARGET
    assert result["stop_hit"] is True
    assert result["target_hit"] is False
    assert result["terminal_session"] == 2
    assert result["stop_hit_session"] == 2


def test_same_daily_session_touch_of_target_and_stop_is_ambiguous_not_guessed():
    bars = [
        _bar(102.0, 99.0),
        _bar(109.0, 95.0),
        _bar(110.0, 98.0),
        _bar(111.0, 99.0),
        _bar(112.0, 100.0),
    ]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == AMBIGUOUS_SAME_SESSION
    assert result["ambiguous"] is True
    assert result["decisive"] is False
    assert result["target_hit"] is False
    assert result["stop_hit"] is False
    assert result["target_hit_session"] == 2
    assert result["stop_hit_session"] == 2


def test_deadline_barrier_is_timeout_only_after_five_complete_future_sessions():
    bars = [_bar(105.0, 97.0)] * 5
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == TIMEOUT
    assert result["timeout"] is True
    assert result["complete_horizon"] is True
    assert result["terminal_session"] == 5
    assert result["sessions_observed"] == 5


def test_less_than_five_sessions_without_terminal_hit_is_incomplete_not_false_timeout():
    bars = [_bar(105.0, 97.0)] * 4
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == INCOMPLETE_HORIZON
    assert result["timeout"] is False
    assert result["complete_horizon"] is False
    assert result["sessions_observed"] == 4


def test_terminal_price_barrier_can_resolve_before_full_forward_horizon_exists():
    bars = [_bar(109.0, 99.0)]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == TARGET_BEFORE_STOP
    assert result["target_hit"] is True
    assert result["terminal_session"] == 1
    assert result["complete_horizon"] is False


def test_sixth_session_target_does_not_rescue_five_session_timeout():
    bars = [_bar(105.0, 97.0)] * 5 + [_bar(109.0, 99.0)]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == TIMEOUT
    assert result["sessions_observed"] == 5


def test_structural_stop_must_be_below_entry_for_long_side_label():
    result = evaluate_five_session_barriers(
        _record(invalidation_level=101.0),
        [_bar(109.0, 99.0)] * 5,
    )
    assert result["outcome_label"] == INVALID_DATA
    assert result["decisive"] is False
    assert result["velocity_snapshot"]["valid_geometry_for_label"] is False


def test_missing_stop_is_invalid_instead_of_being_reconstructed_from_atr():
    record = _record()
    record.pop("invalidation_level")
    snapshot = build_velocity_research_snapshot(record)
    assert snapshot["structural_stop"] is None
    assert snapshot["valid_geometry_for_label"] is False
    result = evaluate_five_session_barriers(record, [_bar(109.0, 99.0)] * 5)
    assert result["outcome_label"] == INVALID_DATA


def test_missing_mapped_targets_does_not_invent_path_but_plus_8_barrier_still_has_defined_research_price():
    snapshot = build_velocity_research_snapshot(_record(targets=[]))
    assert snapshot["velocity_target_price"] == 108.0
    assert snapshot["mapped_targets"] == []
    assert snapshot["mapped_target_reaches_velocity_target"] is None
    assert snapshot["max_mapped_upside_pct"] is None
    assert snapshot["valid_geometry_for_label"] is True


def test_mapped_target_below_plus_8_is_recorded_as_path_evidence_not_live_rejection():
    snapshot = build_velocity_research_snapshot(
        _record(targets=[{"label": "T1", "level": 106.0}])
    )
    assert snapshot["mapped_target_reaches_velocity_target"] is False
    assert snapshot["max_mapped_upside_pct"] == 6.0
    assert snapshot["research_only"] is True
    assert snapshot["capital_authority"] is False


def test_mfe_mae_are_measured_from_research_entry_anchor():
    bars = [
        _bar(104.0, 98.0),
        _bar(107.0, 97.0),
        _bar(106.0, 99.0),
        _bar(105.0, 98.5),
        _bar(104.0, 99.0),
    ]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == TIMEOUT
    assert result["max_favorable_excursion_pct"] == 7.0
    assert result["max_adverse_excursion_pct"] == -3.0


def test_non_numeric_future_ohlc_is_invalid_not_silently_skipped():
    bars = [_bar(102.0, 99.0)] * 4 + [
        {"open": 100.0, "high": "bad", "low": 99.0, "close": 100.0}
    ]
    result = evaluate_five_session_barriers(_record(), bars)
    assert result["outcome_label"] == INVALID_DATA
    assert "non-numeric" in result["reason"].lower()


def test_forward_outcome_block_marks_decisive_target_stop_timeout_as_observed():
    target = evaluate_five_session_barriers(
        _record(),
        [_bar(109.0, 99.0)] + [_bar(105.0, 97.0)] * 4,
    )
    timeout = evaluate_five_session_barriers(_record(), [_bar(105.0, 97.0)] * 5)

    a = to_forward_outcome_block(target)
    b = to_forward_outcome_block(timeout)
    assert a["observed"] is True
    assert a["target_hit"] is True
    assert a["session_limit"] == 5
    assert b["observed"] is True
    assert b["timeout"] is True


def test_forward_outcome_block_keeps_incomplete_horizon_unobserved_for_r4h_cap40_studies():
    result = evaluate_five_session_barriers(_record(), [_bar(105.0, 97.0)] * 4)
    block = to_forward_outcome_block(result)
    assert block["observed"] is False
    assert block["outcome_label"] == INCOMPLETE_HORIZON


def test_ambiguous_same_session_is_observed_but_flagged_ambiguous_for_exclusion_or_sensitivity_analysis():
    result = evaluate_five_session_barriers(
        _record(),
        [_bar(109.0, 95.0)] + [_bar(105.0, 97.0)] * 4,
    )
    block = to_forward_outcome_block(result)
    assert block["observed"] is True
    assert block["ambiguous"] is True
    assert block["outcome_label"] == AMBIGUOUS_SAME_SESSION


def test_custom_target_and_deadline_are_explicitly_auditable_not_hidden():
    snapshot = build_velocity_research_snapshot(
        _record(), target_return_pct=10.0, session_limit=7
    )
    assert snapshot["target_return_pct"] == 10.0
    assert snapshot["session_limit"] == 7
    assert snapshot["velocity_target_price"] == 110.0


def test_velocity_engine_has_no_live_scanner_network_or_model_imports():
    tree = ast.parse(Path("src/velocity_validation.py").read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    forbidden_roots = {
        "src",
        "discord",
        "yfinance",
        "requests",
        "aiohttp",
        "openai",
        "anthropic",
    }
    assert all(name.split(".")[0] not in forbidden_roots for name in imports)

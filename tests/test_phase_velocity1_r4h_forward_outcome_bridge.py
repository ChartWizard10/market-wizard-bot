"""VELOCITY-1 forward-outcome compatibility with R4H-2 evidence audit."""

from src.four_hour_authority_audit import summarize_shadow_evidence
from src.velocity_validation import evaluate_five_session_barriers, to_forward_outcome_block


def _real4h():
    return {
        "status": "ENABLED",
        "freshness_status": "FRESH",
        "proxy_agreement": "AGREE",
        "history_gap_detected": False,
    }


def _record():
    return {
        "scan_price": 100.0,
        "trigger_level": 100.0,
        "invalidation_level": 96.0,
        "targets": [{"label": "T1", "level": 112.0}],
        "atr": 2.0,
    }


def _bar(high=105.0, low=97.0):
    return {"open": 100.0, "high": high, "low": low, "close": 101.0}


def test_observed_velocity_outcome_counts_as_forward_outcome_linkage():
    result = evaluate_five_session_barriers(
        _record(),
        [_bar(high=109.0, low=99.0)] + [_bar()] * 4,
    )
    ledger = {
        "decision_traces": [
            {
                "trace_kind": "analyzed",
                "four_hour_real": _real4h(),
                "forward_outcome": to_forward_outcome_block(result),
            }
        ]
    }
    summary = summarize_shadow_evidence(ledger)
    assert summary["forward_outcome_linked_traces"] == 1
    assert summary["has_forward_outcome_linkage"] is True
    assert summary["has_counterfactual_authority_evidence"] is False


def test_incomplete_velocity_horizon_does_not_satisfy_r4h_forward_outcome_requirement():
    result = evaluate_five_session_barriers(_record(), [_bar()] * 4)
    block = to_forward_outcome_block(result)
    assert block["observed"] is False

    ledger = {
        "decision_traces": [
            {
                "trace_kind": "analyzed",
                "four_hour_real": _real4h(),
                "forward_outcome": block,
            }
        ]
    }
    summary = summarize_shadow_evidence(ledger)
    assert summary["forward_outcome_linked_traces"] == 0
    assert summary["has_forward_outcome_linkage"] is False


def test_nested_observed_velocity_outcome_is_supported_for_future_validation_artifact_shape():
    result = evaluate_five_session_barriers(_record(), [_bar()] * 5)
    ledger = {
        "decision_traces": [
            {
                "trace_kind": "analyzed",
                "four_hour_real": _real4h(),
                "forward_validation": {
                    "forward_outcome": to_forward_outcome_block(result),
                    "proxy_vs_real_counterfactual": {"observed": True},
                },
            }
        ]
    }
    summary = summarize_shadow_evidence(ledger)
    assert summary["forward_outcome_linked_traces"] == 1
    assert summary["counterfactual_proxy_vs_real_traces"] == 1


def test_explicit_observed_false_legacy_forward_validation_block_is_not_counted():
    ledger = {
        "decision_traces": [
            {
                "trace_kind": "analyzed",
                "four_hour_real": _real4h(),
                "forward_validation": {
                    "observed": False,
                    "outcome_label": "INCOMPLETE_HORIZON",
                },
            }
        ]
    }
    summary = summarize_shadow_evidence(ledger)
    assert summary["forward_outcome_linked_traces"] == 0
    assert summary["has_forward_outcome_linkage"] is False

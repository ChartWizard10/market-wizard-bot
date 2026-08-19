"""R4H-2 — evidence-based real-4H authority decision tests."""

from copy import deepcopy

from src import four_hour_authority_audit as audit
from src import four_hour_operational
from src import scan_telemetry


def _trace(*, status="ENABLED", freshness="FRESH", agreement="AGREE",
           gap=False, forward=None):
    row = {
        "trace_kind": "analyzed",
        "ticker": "TEST",
        "four_hour_real": {
            "status": status,
            "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "CONTINUATION",
            "location_state": "DEFENDABLE",
            "readiness": "READY",
            "freshness_status": freshness,
            "history_gap_detected": gap,
            "proxy_state": "LOCATION_VALID",
            "proxy_agreement": agreement,
        },
    }
    if forward is not None:
        row["forward_validation"] = forward
    return row


def _all_green_validation():
    return {flag: True for flag in audit._REQUIRED_VALIDATION_FLAGS}


def test_r4h1_runtime_authority_remains_shadow():
    assert four_hour_operational.AUTHORITY_MODE == "SHADOW_EVIDENCE_ONLY"
    obj = four_hour_operational.default_four_hour_object()
    assert obj["authority_mode"] == "SHADOW_EVIDENCE_ONLY"


def test_current_scan_telemetry_has_real_4h_shadow_projection_but_no_forward_outcome_contract():
    tiering_result = {
        "four_hour_operational": {
            "status": "ENABLED",
            "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "CONTINUATION",
            "operational_location": "DEFENDABLE",
            "operational_readiness": "READY",
            "bar_context": {
                "last_closed_4h_time": "2026-08-19T17:30:00+00:00",
                "live_bar_available": True,
                "last_closed_source_complete": True,
                "confirmed_history_bars": 40,
                "structural_segment_bars": 40,
                "history_gap_detected": False,
                "freshness_status": "FRESH",
            },
            "proxy_comparison": {
                "proxy_state": "LOCATION_VALID",
                "agreement": "AGREE",
            },
            "missing_proofs": [],
        }
    }
    trace = scan_telemetry.build_decision_trace(
        "scan1", "TEST", {}, 1, tiering_result,
        claude_analyzed=True,
    )
    assert trace["four_hour_real"]["proxy_agreement"] == "AGREE"
    assert "forward_validation" not in trace


def test_shadow_summary_reports_observability_without_inventing_outcomes():
    ledger = {"decision_traces": [_trace(), _trace(agreement="REAL_WEAKER", gap=True)]}
    before = deepcopy(ledger)
    out = audit.summarize_shadow_evidence(ledger)

    assert ledger == before
    assert out["real_4h_traces"] == 2
    assert out["proxy_comparable_traces"] == 2
    assert out["history_gap_traces"] == 1
    assert out["has_real_4h_observability"] is True
    assert out["has_forward_outcome_linkage"] is False
    assert out["has_counterfactual_authority_evidence"] is False


def test_proxy_agreement_alone_can_never_promote_authority():
    ledger = {"decision_traces": [_trace() for _ in range(500)]}
    out = audit.audit_authority_readiness(ledger, _all_green_validation())

    assert out["decision"] == audit.DECISION_HOLD_SHADOW
    assert "NO_FORWARD_OUTCOME_LINKAGE" in out["blockers"]
    assert "NO_COUNTERFACTUAL_PROXY_VS_REAL_OUTCOMES" in out["blockers"]
    assert out["automatic_promotion"] is False


def test_synthetic_correctness_without_chronological_validation_holds_shadow():
    forward = {
        "target_hit_before_stop": True,
        "proxy_vs_real_counterfactual": {
            "proxy_policy": "ALLOW",
            "real_policy": "ALLOW",
        },
    }
    ledger = {"decision_traces": [_trace(forward=forward)]}
    validation = _all_green_validation()
    validation["chronological_out_of_sample"] = False

    out = audit.audit_authority_readiness(ledger, validation)
    assert out["decision"] == audit.DECISION_HOLD_SHADOW
    assert "VALIDATION_MISSING:chronological_out_of_sample" in out["blockers"]


def test_complete_explicit_validation_can_only_make_authority_eligible_for_controlled_promotion():
    forward = {
        "five_session_result": "TARGET_FIRST",
        "proxy_vs_real_counterfactual": {
            "proxy_policy": "BLOCK",
            "real_policy": "ALLOW",
            "outcome": "TARGET_FIRST",
        },
    }
    ledger = {"decision_traces": [_trace(forward=forward)]}

    out = audit.audit_authority_readiness(ledger, _all_green_validation())
    assert out["decision"] == audit.DECISION_ELIGIBLE_FOR_CONTROLLED_PROMOTION
    assert out["automatic_promotion"] is False
    assert out["blockers"] == []


def test_missing_or_hostile_input_fails_closed_without_exception():
    for ledger in (None, {}, {"decision_traces": "bad"}, {"decision_traces": [None, 3]}):
        out = audit.audit_authority_readiness(ledger)
        assert out["decision"] == audit.DECISION_HOLD_SHADOW
        assert out["current_authority_mode"] == "SHADOW_EVIDENCE_ONLY"
        assert out["automatic_promotion"] is False

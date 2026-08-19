"""R4H-3A — real-vs-proxy 4H location-policy counterfactual tests."""

from copy import deepcopy

from src import four_hour_counterfactual as cf


def _real(**overrides):
    base = {
        "status": "ENABLED",
        "authority_mode": "SHADOW_EVIDENCE_ONLY",
        "structural_state": "CONTINUATION",
        "location_state": "DEFENDABLE",
        "readiness": "READY_FOR_1H_PROOF",
        "freshness_status": "CLOSED",
        "proxy_state": "LOCATION_VALID",
        "proxy_agreement": "AGREE",
    }
    base.update(overrides)
    return base


def _trace(scan_id="scan_1", ticker="AAPL", real=None):
    return {
        "scan_id": scan_id,
        "ticker": ticker,
        "trace_kind": "analyzed",
        "four_hour_real": _real() if real is None else real,
    }


def _record(scan_id="scan_1", ticker="AAPL", label="TARGET_FIRST"):
    return {
        "scan_id": scan_id,
        "ticker": ticker,
        "label": label,
        "final_tier": "STARTER",
        "capital_authorized_at_observation": True,
    }


def test_proxy_location_mapping_matches_existing_production_vocabulary():
    assert cf.proxy_location_effect("LOCATION_VALID")["location_effect"] == cf.EFFECT_SUPPORTIVE
    assert cf.proxy_location_effect("LOCATION_REPAIRING")["location_effect"] == cf.EFFECT_REPAIRING
    assert cf.proxy_location_effect("LOCATION_EXTENDED")["location_effect"] == cf.EFFECT_EXTENDED
    hostile = cf.proxy_location_effect("LOCATION_HOSTILE")
    assert hostile["location_effect"] == cf.EFFECT_HARD_BLOCK
    assert hostile["hard_block"] is True
    assert cf.proxy_location_effect("UNKNOWN")["location_effect"] == cf.EFFECT_UNAVAILABLE


def test_proxy_mapping_has_no_tier_or_capital_authority():
    out = cf.proxy_location_effect("LOCATION_VALID")
    assert out["capital_authority"] is False
    assert out["tier_authority"] is False


def test_real_defendable_ready_is_supportive():
    out = cf.real_location_effect(_real())
    assert out["location_effect"] == cf.EFFECT_SUPPORTIVE
    assert out["hard_block"] is False


def test_real_repair_is_preserved_as_repair_not_failure():
    out = cf.real_location_effect(_real(
        structural_state="REPAIR",
        location_state="REPAIRING",
        readiness="REPAIRING",
    ))
    assert out["location_effect"] == cf.EFFECT_REPAIRING
    assert out["hard_block"] is False


def test_real_midrange_is_no_edge_not_hard_failure():
    out = cf.real_location_effect(_real(
        location_state="MID_RANGE",
        readiness="FORMING",
    ))
    assert out["location_effect"] == cf.EFFECT_NO_EDGE
    assert out["hard_block"] is False


def test_real_extended_is_distinct_no_chase_condition_not_failure():
    out = cf.real_location_effect(_real(
        location_state="EXTENDED",
        readiness="EXTENDED",
    ))
    assert out["location_effect"] == cf.EFFECT_EXTENDED
    assert out["hard_block"] is False


def test_real_closed_failure_is_hard_block():
    out = cf.real_location_effect(_real(
        structural_state="FAILURE",
        location_state="HOSTILE",
        readiness="HOSTILE",
    ))
    assert out["location_effect"] == cf.EFFECT_HARD_BLOCK
    assert out["hard_block"] is True


def test_stale_or_insufficient_real_evidence_is_unavailable_not_failure():
    stale = cf.real_location_effect(_real(status="STALE", freshness_status="STALE"))
    insufficient = cf.real_location_effect(_real(status="INSUFFICIENT"))
    assert stale["location_effect"] == cf.EFFECT_UNAVAILABLE
    assert stale["hard_block"] is False
    assert insufficient["location_effect"] == cf.EFFECT_UNAVAILABLE


def test_same_effect_classification():
    out = cf.compare_location_policies("LOCATION_VALID", _real())
    assert out["comparison"] == cf.COMPARE_SAME
    assert out["can_measure_hard_block_counterfactual"] is True
    assert out["can_reconstruct_full_tier_counterfactual"] is False


def test_real_adds_hard_block_when_proxy_did_not_block():
    out = cf.compare_location_policies(
        "LOCATION_VALID",
        _real(structural_state="FAILURE", location_state="HOSTILE", readiness="HOSTILE"),
    )
    assert out["comparison"] == cf.COMPARE_REAL_ADDS_BLOCK
    assert out["proxy"]["hard_block"] is False
    assert out["real"]["hard_block"] is True


def test_real_removes_proxy_hard_block_without_claiming_a_trade():
    out = cf.compare_location_policies(
        "LOCATION_HOSTILE",
        _real(location_state="DEFENDABLE", readiness="READY_FOR_1H_PROOF"),
    )
    assert out["comparison"] == cf.COMPARE_REAL_REMOVES_BLOCK
    assert out["proxy"]["hard_block"] is True
    assert out["real"]["hard_block"] is False
    assert out["capital_authority"] is False
    assert out["automatic_promotion"] is False


def test_nonfatal_difference_stays_nonfatal():
    out = cf.compare_location_policies(
        "LOCATION_VALID",
        _real(location_state="MID_RANGE", readiness="FORMING"),
    )
    assert out["comparison"] == cf.COMPARE_NON_FATAL_DIFFERENCE
    assert out["real"]["location_effect"] == cf.EFFECT_NO_EDGE


def test_unavailable_input_cannot_create_counterfactual_claim():
    out = cf.compare_location_policies(None, None)
    assert out["comparison"] == cf.COMPARE_UNAVAILABLE
    assert out["can_measure_hard_block_counterfactual"] is False
    assert out["can_reconstruct_full_tier_counterfactual"] is False


def test_trace_projection_uses_persisted_real_and_proxy_facts_only():
    trace = _trace()
    before = deepcopy(trace)
    out = cf.counterfactual_from_trace(trace)
    assert out["scan_id"] == "scan_1"
    assert out["ticker"] == "AAPL"
    assert out["comparison"] == cf.COMPARE_SAME
    assert trace == before


def test_attach_counterfactuals_joins_by_scan_id_and_ticker_without_mutation():
    ledger = {"decision_traces": [_trace()]}
    dataset = {"records": [_record()]}
    ledger_before = deepcopy(ledger)
    dataset_before = deepcopy(dataset)

    out = cf.attach_counterfactuals(ledger, dataset)

    assert out["join_summary"]["matched_analyzed_traces"] == 1
    assert out["records"][0]["four_hour_counterfactual"]["comparison"] == cf.COMPARE_SAME
    assert ledger == ledger_before
    assert dataset == dataset_before


def test_unmatched_velocity_record_stays_comparison_unavailable():
    out = cf.attach_counterfactuals(
        {"decision_traces": []},
        {"records": [_record()]},
    )
    assert out["join_summary"]["unmatched_or_conflicted"] == 1
    assert out["records"][0]["four_hour_counterfactual"]["comparison"] == cf.COMPARE_UNAVAILABLE


def test_conflicting_duplicate_trace_key_is_not_guessed_through():
    left = _trace(real=_real(location_state="DEFENDABLE"))
    right = _trace(real=_real(location_state="HOSTILE", structural_state="FAILURE"))
    out = cf.attach_counterfactuals(
        {"decision_traces": [left, right]},
        {"records": [_record()]},
    )
    assert out["join_summary"]["matched_analyzed_traces"] == 0
    assert out["records"][0]["four_hour_counterfactual"]["comparison"] == cf.COMPARE_UNAVAILABLE


def test_summary_exposes_outcomes_for_real_added_and_removed_blocks():
    add = _record(scan_id="s1", ticker="AAPL", label="INVALIDATION_FIRST")
    add["four_hour_counterfactual"] = cf.compare_location_policies(
        "LOCATION_VALID",
        _real(structural_state="FAILURE", location_state="HOSTILE", readiness="HOSTILE"),
    )
    remove = _record(scan_id="s2", ticker="MSFT", label="TARGET_FIRST")
    remove["four_hour_counterfactual"] = cf.compare_location_policies(
        "LOCATION_HOSTILE",
        _real(location_state="DEFENDABLE", readiness="READY_FOR_1H_PROOF"),
    )

    summary = cf.summarize_counterfactuals([add, remove])

    assert summary["real_adds_hard_block_outcomes"]["INVALIDATION_FIRST"] == 1
    assert summary["real_removes_proxy_hard_block_outcomes"]["TARGET_FIRST"] == 1
    assert summary["full_tier_counterfactual_supported"] is False
    assert summary["authority_decision"] == "NOT_EVALUATED"


def test_summary_never_turns_outcome_counts_into_authority_decision():
    row = _record(label="TARGET_FIRST")
    row["four_hour_counterfactual"] = cf.compare_location_policies(
        "LOCATION_HOSTILE",
        _real(location_state="DEFENDABLE", readiness="READY_FOR_1H_PROOF"),
    )
    summary = cf.summarize_counterfactuals([row] * 20)
    assert summary["authority_decision"] == "NOT_EVALUATED"
    assert summary["full_tier_counterfactual_supported"] is False

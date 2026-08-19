"""Phase SFC-2A — setup-family admission arbitration tests.

These tests prove that setup-family evidence can repair generic prefilter blind
spots for model admission without becoming capital authority.
"""

from copy import deepcopy

from src.family_admission import build_family_admission_decision


BASE_CONFIG = {
    "prefilter": {
        "family_admission": {
            "enabled": True,
            "min_family_score": 65,
            "max_family_rank_score": 95,
        }
    },
    "tiers": {"snipe_it": {"min_rr": 3.0}},
}


def _evidence(
    family="VCP_BREAK_RETEST",
    *,
    score=82,
    watch_ready=True,
    admission_ready=True,
    entry_structure_valid=False,
    invalidation=97.0,
    target=112.0,
    rr=3.5,
):
    primary = {
        "family_id": family,
        "detected": True,
        "state": "FINAL_CONTRACTION",
        "family_score": score,
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_structure_valid,
        "invalidation_level": invalidation,
        "target_1": target,
        "rr_to_t1": rr,
        "path_status": "CLEAN",
        "blockers": [],
        "soft_caps": [],
    }
    return {
        "version": "SFC-1",
        "primary_family": family,
        "primary_state": primary["state"],
        "primary_family_score": score,
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_structure_valid,
        "primary_invalidation_level": invalidation,
        "primary_target_1": target,
        "primary_rr_to_t1": rr,
        "families": {family: primary},
    }


def _enriched(**kwargs):
    out = {
        "ticker": "TEST",
        "data_status": "OK",
        "setup_family_evidence": _evidence(),
    }
    out.update(kwargs)
    return out


def test_family_can_rescue_generic_structure_and_midrange_blind_spots():
    decision = build_family_admission_decision(
        _enriched(),
        42,
        ["no_clear_structure", "mid_range_no_edge"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is True
    assert decision["rescued_vetoes"] == ["no_clear_structure", "mid_range_no_edge"]
    assert decision["remaining_vetoes"] == []
    assert decision["admission_rank_score"] == 82


def test_family_geometry_can_satisfy_generic_missing_invalidation_and_target_for_admission():
    decision = build_family_admission_decision(
        _enriched(),
        50,
        ["no_clear_invalidation_estimate", "no_target_path"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is True
    assert set(decision["rescued_vetoes"]) == {
        "no_clear_invalidation_estimate",
        "no_target_path",
    }


def test_missing_family_invalidation_is_not_invented():
    enriched = _enriched(setup_family_evidence=_evidence(invalidation=None))
    decision = build_family_admission_decision(
        enriched,
        50,
        ["no_clear_invalidation_estimate"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["remaining_vetoes"] == ["no_clear_invalidation_estimate"]


def test_missing_family_target_is_not_invented():
    enriched = _enriched(setup_family_evidence=_evidence(target=None))
    decision = build_family_admission_decision(
        enriched,
        50,
        ["no_target_path"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["remaining_vetoes"] == ["no_target_path"]


def test_family_rr_must_pass_same_minimum_before_rr_veto_is_rescued():
    enriched = _enriched(setup_family_evidence=_evidence(rr=2.4))
    decision = build_family_admission_decision(
        enriched,
        50,
        ["rr_below_threshold_estimate"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["remaining_vetoes"] == ["rr_below_threshold_estimate"]


def test_family_rr_can_rescue_generic_rr_estimate_when_family_geometry_passes():
    enriched = _enriched(setup_family_evidence=_evidence(rr=3.2))
    decision = build_family_admission_decision(
        enriched,
        50,
        ["rr_below_threshold_estimate"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is True
    assert decision["rescued_vetoes"] == ["rr_below_threshold_estimate"]


def test_overhead_blocked_is_never_rescued():
    decision = build_family_admission_decision(
        _enriched(),
        80,
        ["overhead_blocked"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["rescued_vetoes"] == []
    assert decision["remaining_vetoes"] == ["overhead_blocked"]


def test_hostile_value_is_never_rescued():
    decision = build_family_admission_decision(
        _enriched(),
        80,
        ["hostile_value_alignment"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["remaining_vetoes"] == ["hostile_value_alignment"]


def test_failed_retest_is_never_rescued():
    decision = build_family_admission_decision(
        _enriched(),
        80,
        ["retest_failed"],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["remaining_vetoes"] == ["retest_failed"]


def test_watch_ready_without_admission_ready_does_not_get_model_admission_override():
    enriched = _enriched(
        setup_family_evidence=_evidence(
            watch_ready=True,
            admission_ready=False,
            score=88,
        )
    )
    decision = build_family_admission_decision(
        enriched,
        40,
        ["no_clear_structure"],
        BASE_CONFIG,
    )
    assert decision["watch_ready"] is True
    assert decision["admission_ready"] is False
    assert decision["admitted_by_family"] is False
    assert decision["admission_rank_score"] == 40
    assert decision["reason"] == "FAMILY_WATCH_READY_NOT_ADMISSION_READY"


def test_family_score_below_floor_cannot_open_family_lane():
    enriched = _enriched(setup_family_evidence=_evidence(score=64))
    decision = build_family_admission_decision(
        enriched,
        55,
        [],
        BASE_CONFIG,
    )
    assert decision["admitted_by_family"] is False
    assert decision["reason"] == "FAMILY_SCORE_BELOW_ADMISSION_FLOOR"


def test_entry_structure_valid_gets_small_rank_bonus_but_never_over_cap():
    enriched = _enriched(
        setup_family_evidence=_evidence(score=94, entry_structure_valid=True)
    )
    decision = build_family_admission_decision(enriched, 70, [], BASE_CONFIG)
    assert decision["admitted_by_family"] is True
    assert decision["admission_rank_score"] == 95


def test_no_family_evidence_preserves_legacy_score_and_vetoes():
    decision = build_family_admission_decision(
        {"ticker": "TEST", "data_status": "OK"},
        61,
        ["no_clear_structure"],
        BASE_CONFIG,
    )
    assert decision["active"] is False
    assert decision["admitted_by_family"] is False
    assert decision["admission_rank_score"] == 61
    assert decision["remaining_vetoes"] == ["no_clear_structure"]


def test_disabled_family_lane_is_inert():
    cfg = deepcopy(BASE_CONFIG)
    cfg["prefilter"]["family_admission"]["enabled"] = False
    decision = build_family_admission_decision(_enriched(), 58, [], cfg)
    assert decision["active"] is False
    assert decision["admitted_by_family"] is False
    assert decision["admission_rank_score"] == 58


def test_admission_object_is_not_a_tier_or_capital_authority():
    decision = build_family_admission_decision(_enriched(), 80, [], BASE_CONFIG)
    forbidden = {
        "final_tier",
        "tier",
        "capital_action",
        "discord_channel",
        "safe_for_alert",
    }
    assert forbidden.isdisjoint(decision)

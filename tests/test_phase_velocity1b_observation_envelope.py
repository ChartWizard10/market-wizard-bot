"""Phase VELOCITY-1B — research observation envelope regressions."""

from copy import deepcopy

from src.velocity_observation import (
    VERSION,
    build_observation_envelope,
    observation_to_label_input,
)


def _features(**overrides):
    base = {
        "current_price": 100.0,
        "atr": 2.0,
        "overhead_level": 112.0,
        "targets": [{"label": "T1", "level": 115.0}],
        "overhead_status": "clear",
        "setup_family_evidence": {
            "primary_family": "BREAK_RETEST_CONTINUATION",
            "family_resolution": {
                "relationship": "CONFLUENT",
                "conflict_scope": "NONE",
                "secondary_families": ["SMA_CRADLE_CONTINUATION"],
                "failed_families": [],
            },
        },
    }
    base.update(overrides)
    return base


def _judgment(**overrides):
    base = {
        "final_tier": "STARTER",
        "capital_action": "starter_reduced_size",
        "score": 78,
        "final_signal": {
            "invalidation_level": 96.0,
            "invalidation_condition": "close below defended demand",
            "risk_reward": 3.25,
            "overhead_status": "clear",
        },
        "four_hour_operational": {
            "status": "ENABLED",
            "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "ORDERLY_CONTINUATION",
            "operational_location": "VALUE_RETEST",
            "operational_readiness": "ARMED",
            "missing_proofs": ["FOLLOW_THROUGH"],
            "bar_context": {
                "last_closed_4h_time": "2026-08-19T16:00:00-04:00",
                "freshness_status": "FRESH",
                "history_gap_detected": False,
                "confirmed_history_bars": 30,
            },
            "proxy_comparison": {
                "proxy_state": "BULLISH_REPAIR",
                "agreement": "AGREE",
            },
        },
    }
    base.update(overrides)
    return base


def test_observation_envelope_contains_minimum_future_label_geometry():
    env = build_observation_envelope(
        "scan_1",
        "2026-08-19T14:00:00-04:00",
        "AAPL",
        _features(),
        _judgment(),
    )

    assert env["version"] == VERSION
    assert env["persistence_ready"] is True
    assert env["geometry"]["reference_price"] == 100.0
    assert env["geometry"]["reference_price_source"] == "current_price"
    assert env["geometry"]["invalidation_level"] == 96.0
    assert env["feasibility"]["target_return_pct"] == 8.0
    assert env["feasibility"]["horizon_sessions"] == 5


def test_envelope_is_research_only_and_has_zero_trade_authority():
    env = build_observation_envelope(
        "scan_2", "2026-08-19T14:15:00-04:00", "MSFT", _features(), _judgment()
    )

    assert env["research_only"] is True
    assert env["observational_only"] is True
    assert env["capital_authority"] is False
    assert env["tier_authority"] is False
    assert env["routing_authority"] is False
    assert env["forecast_authority"] is False
    assert env["feasibility"]["capital_authority"] is False
    assert env["feasibility"]["tier_authority"] is False


def test_builder_never_mutates_features_or_judgment():
    features = _features()
    judgment = _judgment()
    features_before = deepcopy(features)
    judgment_before = deepcopy(judgment)

    _ = build_observation_envelope(
        "scan_3", "2026-08-19T14:30:00-04:00", "NVDA", features, judgment
    )

    assert features == features_before
    assert judgment == judgment_before


def test_starter_and_snipe_are_marked_capital_authorized_at_observation():
    starter = build_observation_envelope(
        "s1", "2026-08-19T10:00:00-04:00", "A", _features(), _judgment(final_tier="STARTER")
    )
    snipe = build_observation_envelope(
        "s2", "2026-08-19T10:15:00-04:00", "B", _features(), _judgment(final_tier="SNIPE_IT")
    )

    assert starter["observation"]["capital_authorized_at_observation"] is True
    assert snipe["observation"]["capital_authorized_at_observation"] is True


def test_near_entry_is_studied_without_being_counted_as_capital():
    env = build_observation_envelope(
        "s3",
        "2026-08-19T10:30:00-04:00",
        "C",
        _features(),
        _judgment(final_tier="NEAR_ENTRY", capital_action="wait_no_capital"),
    )

    assert env["persistence_ready"] is True
    assert env["observation"]["final_tier"] == "NEAR_ENTRY"
    assert env["observation"]["capital_authorized_at_observation"] is False


def test_wait_is_not_silently_treated_as_executed_trade():
    env = build_observation_envelope(
        "s4",
        "2026-08-19T10:45:00-04:00",
        "D",
        _features(),
        _judgment(final_tier="WAIT", capital_action="wait_no_capital"),
    )
    assert env["observation"]["capital_authorized_at_observation"] is False


def test_primary_family_and_cross_family_context_are_attributed_without_score_stacking():
    env = build_observation_envelope(
        "s5", "2026-08-19T11:00:00-04:00", "E", _features(), _judgment()
    )

    family = env["setup_family"]
    assert family["primary_family"] == "BREAK_RETEST_CONTINUATION"
    assert family["relationship"] == "CONFLUENT"
    assert family["conflict_scope"] == "NONE"
    assert family["secondary_families"] == ["SMA_CRADLE_CONTINUATION"]
    assert "score" not in family


def test_real_four_hour_shadow_and_proxy_context_are_preserved_for_future_counterfactuals():
    env = build_observation_envelope(
        "s6", "2026-08-19T11:15:00-04:00", "F", _features(), _judgment()
    )

    four = env["four_hour_shadow"]
    assert four["authority_mode"] == "SHADOW_EVIDENCE_ONLY"
    assert four["structural_state"] == "ORDERLY_CONTINUATION"
    assert four["proxy_state"] == "BULLISH_REPAIR"
    assert four["proxy_agreement"] == "AGREE"
    assert four["history_gap_detected"] is False


def test_missing_four_hour_evidence_stays_none_not_fabricated():
    j = _judgment()
    j.pop("four_hour_operational")
    env = build_observation_envelope(
        "s7", "2026-08-19T11:30:00-04:00", "G", _features(), j
    )
    assert env["four_hour_shadow"] is None


def test_missing_reference_price_blocks_persistence_readiness_but_not_builder():
    f = _features(current_price=None, targets=[])
    f.pop("overhead_level", None)
    env = build_observation_envelope(
        "s8", "2026-08-19T11:45:00-04:00", "H", f, _judgment()
    )

    assert env["persistence_ready"] is False
    assert "reference_price" in env["missing_required_fields"]
    assert env["feasibility"]["status"] == "INVALID_DATA"


def test_missing_invalidation_blocks_persistence_readiness():
    j = _judgment(final_signal={"risk_reward": 3.0, "overhead_status": "clear"})
    env = build_observation_envelope(
        "s9", "2026-08-19T12:00:00-04:00", "I", _features(), j
    )

    assert env["persistence_ready"] is False
    assert "invalidation_level" in env["missing_required_fields"]


def test_invalid_scan_identity_is_explicitly_incomplete():
    env = build_observation_envelope(None, None, None, _features(), _judgment())
    assert env["persistence_ready"] is False
    assert env["missing_required_fields"][:3] == ["scan_id", "scan_timestamp", "ticker"]


def test_label_input_projection_contains_no_future_outcome_fabrication():
    env = build_observation_envelope(
        "s10", "2026-08-19T12:15:00-04:00", "J", _features(), _judgment()
    )
    projected = observation_to_label_input(env)

    assert projected["entry_price"] == 100.0
    assert projected["invalidation_level"] == 96.0
    assert projected["target_return_pct"] == 8.0
    assert projected["horizon_sessions"] == 5
    assert projected["final_tier"] == "STARTER"
    assert projected["setup_family"] == "BREAK_RETEST_CONTINUATION"
    assert "label" not in projected
    assert "outcome" not in projected
    assert "future_bars" not in projected


def test_label_projection_keeps_four_hour_real_and_proxy_states_separate():
    env = build_observation_envelope(
        "s11", "2026-08-19T12:30:00-04:00", "K", _features(), _judgment()
    )
    projected = observation_to_label_input(env)

    assert projected["four_hour_state"] == "ORDERLY_CONTINUATION"
    assert projected["four_hour_proxy_state"] == "BULLISH_REPAIR"
    assert projected["four_hour_proxy_agreement"] == "AGREE"


def test_final_signal_geometry_outranks_loose_top_level_geometry():
    j = _judgment(invalidation_level=90.0)
    j["final_signal"]["invalidation_level"] = 96.0
    env = build_observation_envelope(
        "s12", "2026-08-19T12:45:00-04:00", "L", _features(), j
    )
    assert env["geometry"]["invalidation_level"] == 96.0


def test_top_level_invalidation_is_accepted_only_as_compatibility_fallback():
    j = _judgment(final_signal={"risk_reward": 2.5})
    j["invalidation_level"] = 95.0
    env = build_observation_envelope(
        "s13", "2026-08-19T13:00:00-04:00", "M", _features(), j
    )
    assert env["geometry"]["invalidation_level"] == 95.0
    assert env["persistence_ready"] is True


def test_custom_objective_is_carried_into_snapshot_and_link_input():
    env = build_observation_envelope(
        "s14",
        "2026-08-19T13:15:00-04:00",
        "N",
        _features(),
        _judgment(),
        target_return_pct=6.0,
        horizon_sessions=4,
    )
    projected = observation_to_label_input(env)

    assert env["feasibility"]["target_return_pct"] == 6.0
    assert env["feasibility"]["horizon_sessions"] == 4
    assert projected["target_return_pct"] == 6.0
    assert projected["horizon_sessions"] == 4

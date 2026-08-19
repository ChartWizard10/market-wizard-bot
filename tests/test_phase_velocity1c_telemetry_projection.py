"""VELOCITY-1C — bounded research telemetry projection regressions."""

import json

from src.velocity_observation import (
    build_observation_envelope,
    compact_for_telemetry,
)


def _envelope():
    features = {
        "current_price": 100.0,
        "atr": 2.0,
        "overhead_level": 112.0,
        "targets": [{"label": "T1", "level": 115.0}],
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
    judgment = {
        "final_tier": "STARTER",
        "capital_action": "starter_reduced_size",
        "score": 77,
        "final_signal": {
            "invalidation_level": 96.0,
            "invalidation_condition": "close below defended demand",
            "risk_reward": 3.2,
            "overhead_status": "clear",
        },
        "four_hour_operational": {
            "status": "ENABLED",
            "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "ORDERLY_CONTINUATION",
            "operational_location": "VALUE_RETEST",
            "operational_readiness": "ARMED",
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
    return build_observation_envelope(
        "scan_1",
        "2026-08-19T14:00:00-04:00",
        "AAPL",
        features,
        judgment,
    )


def test_compact_projection_has_future_linkage_geometry_and_attribution():
    compact = compact_for_telemetry(_envelope())

    assert compact["observed_at"] == "2026-08-19T14:00:00-04:00"
    assert compact["ready"] is True
    assert compact["reference_price"] == 100.0
    assert compact["invalidation_level"] == 96.0
    assert compact["target_return_pct"] == 8.0
    assert compact["horizon_sessions"] == 5.0
    assert compact["final_tier"] == "STARTER"
    assert compact["capital_authorized_at_observation"] is True
    assert compact["primary_family"] == "BREAK_RETEST_CONTINUATION"
    assert compact["four_hour_state"] == "ORDERLY_CONTINUATION"
    assert compact["four_hour_proxy_state"] == "BULLISH_REPAIR"
    assert compact["four_hour_proxy_agreement"] == "AGREE"


def test_compact_projection_carries_no_trade_authority_and_no_outcome():
    compact = compact_for_telemetry(_envelope())

    assert compact["research_only"] is True
    assert compact["capital_authority"] is False
    assert compact["tier_authority"] is False
    forbidden = {"label", "outcome", "future_bars", "terminal_session", "target_first"}
    assert forbidden.isdisjoint(compact)


def test_compact_projection_is_bounded_for_9000_trace_ring_buffer():
    compact = compact_for_telemetry(_envelope())
    encoded = json.dumps(compact, separators=(",", ":"), allow_nan=False)

    # Keep the additive per-trace payload small enough that 9000 retained
    # observations add comfortably under 10 MB before the existing trace body.
    assert len(encoded.encode("utf-8")) < 1000


def test_missing_geometry_remains_explicit_not_fabricated():
    env = build_observation_envelope(
        "scan_2",
        "2026-08-19T14:15:00-04:00",
        "MSFT",
        {"current_price": None, "targets": []},
        {"final_tier": "NEAR_ENTRY", "final_signal": {}},
    )
    compact = compact_for_telemetry(env)

    assert compact["ready"] is False
    assert compact["reference_price"] is None
    assert compact["invalidation_level"] is None
    assert compact["capital_authorized_at_observation"] is False
    assert set(compact["missing"]) >= {"reference_price", "invalidation_level"}

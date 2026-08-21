"""VELOCITY-1C scan-trace observation bridge contract tests."""

import ast
from pathlib import Path

from src.velocity_trace_envelope import (
    TRACE_ANALYZED,
    TRACE_CLAUDE_FAILED,
    TRACE_RANKED_NOT_ANALYZED,
    build_trace_observation,
    should_capture_trace_observation,
)


def _family_admission(**overrides):
    out = {
        "active": True,
        "primary_family": "VCP_BREAK_RETEST",
        "compiler_primary_family": "VCP_BREAK_RETEST",
        "primary_state": "FINAL_CONTRACTION",
        "family_score": 84,
        "watch_ready": True,
        "admission_ready": True,
        "entry_structure_valid": False,
        "family_invalidation_level": 96.0,
        "family_target_1": 112.0,
        "family_rr_to_t1": 4.0,
        "family_path_status": "CLEAN_TO_PIVOT",
        "family_blockers": [],
        "family_soft_caps": ["BREAKOUT_RETEST_PENDING"],
        "family_relationship": "SINGLE",
        "family_conflict_scope": "NONE",
        "secondary_families": [],
        "failed_families": [],
        "shared_failure_codes": [],
        "confluence_count": 1,
        "resolver_reason_codes": ["SINGLE_VIABLE_FAMILY"],
    }
    out.update(overrides)
    return out


def _prefilter(rank=1, **overrides):
    out = {
        "ticker": "TEST",
        "prefilter_score": 72,
        "admission_rank_score": 84,
        "admission_source": "family",
        "eligible_for_model": True,
        "eligible_for_claude": True,
        "veto_flags": [],
        "rescued_veto_flags": ["no_clear_structure"],
        "rank": rank,
        "family_admission": _family_admission(),
        "key_features": {
            "current_price": 100.0,
            "atr": 2.0,
            "estimated_rr": None,
            "overhead_status": "clear",
            "sma_value_alignment": "supportive",
            "structure_event": "none",
            "retest_status": "missing",
            "volume_behavior": "dryup",
            "setup_family_primary": "VCP_BREAK_RETEST",
            "setup_family_state": "FINAL_CONTRACTION",
            "setup_family_score": 84,
            "setup_family_watch_ready": True,
            "setup_family_admission_ready": True,
            "setup_family_entry_structure_valid": False,
            "setup_family_invalidation": 96.0,
            "setup_family_target_1": 112.0,
            "setup_family_rr_to_t1": 4.0,
        },
    }
    out.update(overrides)
    return out


def _judgment(tier="STARTER"):
    return {
        "final_tier": tier,
        "capital_action": "starter_only" if tier == "STARTER" else "wait_no_capital",
        "safe_for_alert": tier in {"STARTER", "SNIPE_IT", "NEAR_ENTRY"},
        "final_signal": {
            "ticker": "TEST",
            "timestamp_et": "2026-08-19T10:30:00-04:00",
            "tier": tier,
            "scan_price": 100.0,
            "trigger_level": 100.0,
            "invalidation_level": 96.0,
            "targets": [{"label": "T1", "level": 112.0}],
            "risk_reward": 3.0,
            "overhead_status": "clear",
            "capital_action": "starter_only" if tier == "STARTER" else "wait_no_capital",
        },
        "four_hour_real": {
            "status": "ENABLED",
            "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "REPAIR",
            "operational_readiness": "WATCH",
            "freshness_status": "FRESH",
            "retest_state": "RETEST_IN_PROGRESS",
            "hold_state": "HOLD_FORMING",
            "failure_state": "NONE",
            "proxy_comparison": {
                "agreement": "AGREE",
                "real_state": "REPAIR",
                "proxy_state": "REPAIR",
            },
        },
    }


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _walk_keys(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_keys(item)


def test_capture_population_is_analyzed_model_failed_and_near_cut_only():
    assert should_capture_trace_observation(TRACE_ANALYZED) is True
    assert should_capture_trace_observation(TRACE_CLAUDE_FAILED) is True
    assert should_capture_trace_observation(TRACE_RANKED_NOT_ANALYZED, near_cut=True) is True
    assert should_capture_trace_observation(TRACE_RANKED_NOT_ANALYZED, near_cut=False) is False
    assert should_capture_trace_observation("prefilter_rejected") is False
    assert should_capture_trace_observation("prefilter_admitted_not_selected") is False


def test_analyzed_observation_preserves_actual_tier_and_capital_truth():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_ANALYZED,
        ticker="TEST",
        prefilter_row=_prefilter(rank=1),
        judgment=_judgment("STARTER"),
    )
    assert observation is not None
    assert observation["identity"]["observed_at"] == "2026-08-19T14:30:00Z"
    assert observation["stage"] == "STARTER"
    assert observation["final_state"]["observed_tier"] == "STARTER"
    assert observation["final_state"]["capital_authorized"] is True
    assert observation["selection_context"] == {
        "trace_kind": "analyzed",
        "deep_analysis_selected": True,
        "analysis_performed": True,
        "final_tier_observed": True,
        "capital_authorized": True,
    }
    assert observation["capital_authority"] is False
    assert observation["research_only"] is True


def test_near_cut_rank31_is_not_falsely_labeled_wait():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_RANKED_NOT_ANALYZED,
        ticker="RANK31",
        prefilter_row=_prefilter(rank=31, ticker="RANK31"),
        judgment=None,
        near_cut=True,
    )
    assert observation is not None
    assert observation["stage"] == "RANKED_NOT_ANALYZED"
    assert observation["final_state"]["observed_tier"] is None
    assert observation["final_state"]["capital_action"] is None
    assert observation["final_state"]["capital_authorized"] is False
    assert observation["selection_context"]["deep_analysis_selected"] is False
    assert observation["selection_context"]["analysis_performed"] is False
    assert observation["selection_context"]["final_tier_observed"] is False
    assert observation["velocity_feasibility"]["stage"] == "RANKED_NOT_ANALYZED"


def test_model_failure_is_selected_but_has_no_observed_tier():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_CLAUDE_FAILED,
        ticker="FAIL",
        prefilter_row=_prefilter(rank=4, ticker="FAIL"),
        judgment=None,
    )
    assert observation is not None
    assert observation["stage"] == "CLAUDE_FAILED"
    assert observation["final_state"]["observed_tier"] is None
    assert observation["selection_context"]["deep_analysis_selected"] is True
    assert observation["selection_context"]["analysis_performed"] is False


def test_family_projection_is_scan_time_existing_evidence_not_redetection():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_RANKED_NOT_ANALYZED,
        ticker="RANK31",
        prefilter_row=_prefilter(rank=31),
        near_cut=True,
    )
    family = observation["setup_family"]
    assert family["primary_family"] == "VCP_BREAK_RETEST"
    assert family["primary_state"] == "FINAL_CONTRACTION"
    assert family["primary_score"] == 84
    assert family["admission_ready"] is True
    assert family["family_resolution"]["relationship"] == "SINGLE"
    assert family["capital_authority"] is False


def test_family_confluence_and_local_failed_sibling_context_survive_projection():
    pf = _prefilter(rank=31)
    pf["family_admission"] = _family_admission(
        primary_family="SMA_CRADLE_CONTINUATION",
        compiler_primary_family="GAP_FILL_REVERSAL",
        primary_state="VALUE_RECLAIMED",
        family_score=83,
        family_relationship="CONTRADICTORY",
        family_conflict_scope="LOCAL",
        secondary_families=["GAP_FILL_REVERSAL"],
        failed_families=["GAP_FILL_REVERSAL"],
        confluence_count=1,
        resolver_reason_codes=["VALID_PRIMARY_PRESERVED_DESPITE_LOCAL_SIBLING_FAILURE"],
    )
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_RANKED_NOT_ANALYZED,
        ticker="TEST",
        prefilter_row=pf,
        near_cut=True,
    )
    assert observation["setup_family"]["primary_family"] == "SMA_CRADLE_CONTINUATION"
    resolution = observation["setup_family"]["family_resolution"]
    assert resolution["relationship"] == "CONTRADICTORY"
    assert resolution["conflict_scope"] == "LOCAL"
    assert resolution["failed_families"] == ["GAP_FILL_REVERSAL"]


def test_analyzed_projection_maps_current_real4h_key_into_shadow_context():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_ANALYZED,
        ticker="TEST",
        prefilter_row=_prefilter(),
        judgment=_judgment("STARTER"),
    )
    four_hour = observation["four_hour_shadow"]
    assert four_hour["status"] == "ENABLED"
    assert four_hour["authority_mode"] == "SHADOW_EVIDENCE_ONLY"
    assert four_hour["proxy_comparison"]["agreement"] == "AGREE"
    assert observation["authority"]["real_4h_authority"] == "SHADOW_ONLY"


def test_bridge_never_accepts_or_emits_future_outcome_fields():
    pf = _prefilter()
    pf["future_daily_bars"] = [{"high": 110.0, "low": 95.0}]
    judgment = _judgment("STARTER")
    judgment["forward_outcome"] = {"outcome_label": "TARGET_HIT"}

    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_ANALYZED,
        ticker="TEST",
        prefilter_row=pf,
        judgment=judgment,
    )
    assert observation is not None
    keys = set(_walk_keys(observation))
    assert "future_daily_bars" not in keys
    assert "forward_outcome" not in keys
    assert "outcome_label" not in keys
    assert "target_hit_session" not in keys
    assert "stop_hit_session" not in keys


def test_non_scan_id_without_valid_timestamp_fails_closed_for_unanalyzed_trace():
    observation = build_trace_observation(
        scan_id="manual_without_date",
        trace_kind=TRACE_RANKED_NOT_ANALYZED,
        ticker="TEST",
        prefilter_row=_prefilter(rank=31),
        near_cut=True,
    )
    assert observation is None


def test_model_timestamp_can_supply_fallback_for_analyzed_manual_trace():
    observation = build_trace_observation(
        scan_id="manual_without_date",
        trace_kind=TRACE_ANALYZED,
        ticker="TEST",
        prefilter_row=_prefilter(),
        judgment=_judgment("STARTER"),
    )
    assert observation is not None
    assert observation["identity"]["observed_at"] == "2026-08-19T10:30:00-04:00"


def test_bridge_has_no_network_market_data_model_or_telemetry_write_imports():
    tree = ast.parse(Path("src/velocity_trace_envelope.py").read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    forbidden = {
        "openai",
        "anthropic",
        "yfinance",
        "requests",
        "aiohttp",
        "discord",
        "src.scheduler",
        "src.market_data",
        "src.scan_telemetry",
        "src.state_store",
    }
    assert not (set(imports) & forbidden)


def test_observation_output_contains_no_routing_or_capital_authority_keys_from_bridge():
    observation = build_trace_observation(
        scan_id="scan_20260819_143000_abcdef",
        trace_kind=TRACE_RANKED_NOT_ANALYZED,
        ticker="TEST",
        prefilter_row=_prefilter(rank=31),
        near_cut=True,
    )
    assert observation["capital_authority"] is False
    assert "final_discord_channel" not in observation
    assert "discord_channel" not in observation
    assert "safe_for_alert" not in observation

"""Phase SFC-2 — family evidence wiring and broad-universe admission."""

from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pandas as pd

from src import indicators, prefilter
from src.claude_client import build_prompt
from src.setup_family_compiler import VCP_BREAK_RETEST


def _cfg():
    return {
        "prefilter": {
            "prefilter_min_score": 55,
            "scoring_weights": {
                "trend_value_alignment": 15,
                "structure_event": 20,
                "fvg_ob_demand_zone_quality": 15,
                "retest_proximity_status": 20,
                "target_path_rr_estimate": 15,
                "volume_participation": 10,
                "data_quality_recency": 5,
            },
            "thresholds": {"max_price_extension_from_sma20_pct": 8},
        },
        "tiers": {"snipe_it": {"min_rr": 3.0}},
    }


def _family_evidence(*, admission=True, entry=False, state="FINAL_CONTRACTION", score=82,
                     invalidation=94.0, target=108.0, rr=2.8, retest="NOT_STARTED"):
    primary = {
        "family_id": VCP_BREAK_RETEST,
        "detected": True,
        "state": state,
        "family_score": score,
        "watch_ready": True,
        "admission_ready": admission,
        "entry_structure_valid": entry,
        "location_valid": True,
        "retest_state": retest,
        "invalidation_level": invalidation,
        "target_1": target,
        "rr_to_t1": rr,
        "path_status": "CLEAN_TO_PIVOT",
        "blockers": [],
        "soft_caps": [],
        "metrics": {"volume_contracting": True, "pivot": 108.0},
    }
    return {
        "version": "SFC-1",
        "primary_family": VCP_BREAK_RETEST,
        "detected_families": [VCP_BREAK_RETEST],
        "watch_ready": True,
        "admission_ready": admission,
        "entry_structure_valid": entry,
        "primary_state": state,
        "primary_family_score": score,
        "primary_invalidation_level": invalidation,
        "primary_target_1": target,
        "primary_rr_to_t1": rr,
        "families": {VCP_BREAK_RETEST: primary},
    }


def _family_only_enriched(**overrides):
    out = {
        "ticker": "TEST",
        "data_status": "OK",
        "current_price": 100.0,
        "current_open": 99.5,
        "current_high": 101.0,
        "current_low": 99.0,
        "previous_close": 99.2,
        "sma_value_alignment": "supportive",
        "price_extension_from_sma20_pct": 2.0,
        "structure_event": "none",
        "wick_only_break": False,
        "fvg": None,
        "ob": None,
        "retest_status": "missing",
        "overhead_status": "clear",
        "targets": [],
        "invalidation_level": None,
        "estimated_rr": None,
        "volume_behavior": "dryup",
        "setup_family_evidence": _family_evidence(),
    }
    out.update(overrides)
    return out


def test_family_ready_vcp_is_not_rejected_for_missing_classic_structure_zone():
    enriched = _family_only_enriched()
    result = prefilter.score_ticker(enriched, _cfg())

    assert prefilter.VETO_NO_CLEAR_STRUCTURE not in result["veto_flags"]
    assert prefilter.VETO_MID_RANGE_NO_EDGE not in result["veto_flags"]
    assert prefilter.VETO_NO_INVALIDATION not in result["veto_flags"]
    assert prefilter.VETO_NO_TARGET_PATH not in result["veto_flags"]
    assert result["prefilter_score"] >= 55
    assert result["eligible_for_claude"] is True


def test_family_evidence_maps_into_existing_score_budget_without_new_weight_bucket():
    enriched = _family_only_enriched()
    total, breakdown = prefilter.algo_score(enriched, _cfg())

    assert set(breakdown) == {
        "trend_value_alignment",
        "structure_event",
        "fvg_ob_demand_zone_quality",
        "retest_proximity_status",
        "target_path_rr_estimate",
        "volume_participation",
        "data_quality_recency",
    }
    assert sum(breakdown.values()) == total
    assert breakdown["structure_event"] > 0
    assert breakdown["fvg_ob_demand_zone_quality"] > 0
    assert breakdown["retest_proximity_status"] > 0
    assert breakdown["target_path_rr_estimate"] > 0


def test_family_ready_candidate_does_not_override_true_overhead_or_alignment_blockers():
    overhead = prefilter.apply_hard_vetoes(
        _family_only_enriched(overhead_status="blocked"), _cfg()
    )
    hostile = prefilter.apply_hard_vetoes(
        _family_only_enriched(sma_value_alignment="hostile"), _cfg()
    )

    assert prefilter.VETO_OVERHEAD_BLOCKED in overhead
    assert prefilter.VETO_HOSTILE_ALIGNMENT in hostile


def test_unrelated_generic_retest_failure_does_not_kill_valid_family_lifecycle():
    enriched = _family_only_enriched(retest_status="failed")
    vetoes = prefilter.apply_hard_vetoes(enriched, _cfg())
    assert prefilter.VETO_RETEST_FAILED not in vetoes


def test_family_failed_retest_still_blocks_admission():
    evidence = _family_evidence(admission=False, state="FAILED", retest="FAILED")
    enriched = _family_only_enriched(
        retest_status="failed",
        setup_family_evidence=evidence,
    )
    vetoes = prefilter.apply_hard_vetoes(enriched, _cfg())
    assert prefilter.VETO_RETEST_FAILED in vetoes


def test_key_features_persist_compact_family_proof_for_downstream_tiering():
    result = prefilter.score_ticker(_family_only_enriched(), _cfg())
    family = result["key_features"]["setup_family_evidence"]

    assert family["primary_family"] == VCP_BREAK_RETEST
    assert family["admission_ready"] is True
    assert family["watch_ready"] is True
    assert family["entry_structure_valid"] is False
    assert family["primary_state"] == "FINAL_CONTRACTION"
    assert family["primary_invalidation_level"] == 94.0
    assert family["primary_target_1"] == 108.0


def test_prompt_exposes_deterministic_family_evidence_without_changing_json_schema():
    prompt = build_prompt(_family_only_enriched())
    assert "PRIMARY_FAMILY_ID: VCP_BREAK_RETEST" in prompt
    assert "FAMILY_STATE: FINAL_CONTRACTION" in prompt
    assert "FAMILY_ADMISSION_READY: True" in prompt
    assert "FAMILY_ENTRY_STRUCTURE_VALID: False" in prompt
    assert "FAMILY_INVALIDATION_LEVEL: 94.0" in prompt
    assert "FAMILY_TARGET_1: 108.0" in prompt


def test_no_family_evidence_preserves_legacy_classic_scoring_contract():
    enriched = _family_only_enriched(
        structure_event="MSS",
        fvg={"price_in_fvg": True},
        ob={"price_at_ob": True},
        retest_status="confirmed",
        targets=[{"level": 112.0}],
        invalidation_level=96.0,
        estimated_rr=3.2,
        volume_behavior="expansion",
        setup_family_evidence=None,
    )
    score, breakdown = prefilter.algo_score(enriched, _cfg())
    vetoes = prefilter.apply_hard_vetoes(enriched, _cfg())

    assert score == 100
    assert all(value >= 0 for value in breakdown.values())
    assert vetoes == []


def _bars(n=130):
    close = np.linspace(80.0, 120.0, n)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 1.0,
            "low": np.minimum(open_, close) - 1.0,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="B"),
    )


def test_indicators_pass_only_completed_daily_bars_into_family_compiler():
    df = _bars()
    captured = {}
    fake = {
        "version": "SFC-1",
        "primary_family": "NONE",
        "detected_families": [],
        "watch_ready": False,
        "admission_ready": False,
        "entry_structure_valid": False,
        "primary_state": "NONE",
        "primary_family_score": 0,
        "primary_invalidation_level": None,
        "primary_target_1": None,
        "primary_rr_to_t1": None,
        "families": {},
    }

    # Explicitly force the newest row to be developing through the existing
    # partition boundary, then prove the compiler sees the completed view only.
    confirmed = df.iloc[:-1].copy()
    partition = {
        "context": {"status": "LIVE"},
        "confirmed_df": confirmed,
        "live_row": df.iloc[-1],
    }

    def _compile(frame, current_price, base_features, config=None):
        captured["rows"] = len(frame)
        captured["last_close"] = float(frame.close.iloc[-1])
        captured["current_price"] = current_price
        captured["base_before_family"] = deepcopy(base_features)
        return fake

    with (
        patch("src.indicators.partition_daily_bars", return_value=partition),
        patch("src.indicators.setup_family_compiler.compile_setup_families", side_effect=_compile),
    ):
        out = indicators.enrich("TEST", df, _cfg())

    assert captured["rows"] == len(df) - 1
    assert captured["last_close"] == float(df.close.iloc[-2])
    assert captured["current_price"] == float(df.close.iloc[-1])
    assert "setup_family_evidence" not in captured["base_before_family"]
    assert out["setup_family_evidence"] == fake

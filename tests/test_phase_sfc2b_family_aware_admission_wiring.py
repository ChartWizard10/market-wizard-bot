"""Phase SFC-2B — family-aware enrichment, admission, ranking and prompt tests."""

from copy import deepcopy

import numpy as np
import pandas as pd
import yaml

from src import indicators, tiering
from src.claude_client import build_prompt
from src.prefilter import prefilter, score_ticker


def _config():
    with open("config/doctrine_config.yaml") as f:
        return yaml.safe_load(f)


def _family_evidence(
    family="VCP_BREAK_RETEST",
    *,
    score=84,
    admission_ready=True,
    watch_ready=True,
    entry_structure_valid=False,
    invalidation=96.0,
    target=112.0,
    rr=3.5,
    state="FINAL_CONTRACTION",
):
    primary = {
        "family_id": family,
        "detected": True,
        "state": state,
        "family_score": score,
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_structure_valid,
        "location_valid": True,
        "retest_state": "PENDING",
        "invalidation_level": invalidation,
        "target_1": target,
        "rr_to_t1": rr,
        "path_status": "CLEAN",
        "blockers": [],
        "soft_caps": ["BREAKOUT_RETEST_PENDING"] if not entry_structure_valid else [],
        "metrics": {
            "range_contracting": True,
            "volume_contracting": True,
            "pivot": 104.5,
        },
    }
    return {
        "version": "SFC-1",
        "primary_family": family,
        "detected_families": [family],
        "watch_ready": watch_ready,
        "admission_ready": admission_ready,
        "entry_structure_valid": entry_structure_valid,
        "primary_state": state,
        "primary_family_score": score,
        "primary_invalidation_level": invalidation,
        "primary_target_1": target,
        "primary_rr_to_t1": rr,
        "families": {family: primary},
    }


def _base_enriched(ticker="TEST", **overrides):
    out = {
        "ticker": ticker,
        "data_status": "OK",
        "current_price": 100.0,
        "current_open": 99.5,
        "current_high": 101.0,
        "current_low": 99.0,
        "previous_close": 99.0,
        "sma20": 98.0,
        "sma50": 95.0,
        "sma200": 88.0,
        "sma_value_alignment": "supportive",
        "price_extension_from_sma20_pct": 2.0,
        "structure_event": "MSS",
        "structure_confirmed": True,
        "structure_level": 97.0,
        "prior_structural_high": 97.0,
        "wick_only_break": False,
        "fvg": {
            "fvg_top": 99.5,
            "fvg_mid": 98.75,
            "fvg_bot": 98.0,
            "fvg_filled": False,
            "price_in_fvg": True,
        },
        "ob": None,
        "retest_status": "confirmed",
        "retest_zone": "FVG",
        "retest_distance_atr": 0.0,
        "overhead_status": "clear",
        "overhead_level": 112.0,
        "overhead_distance_pct": 12.0,
        "targets": [{"label": "T1", "level": 112.0, "reason": "nearest pool"}],
        "invalidation_level": 96.0,
        "invalidation_condition": "below structure",
        "estimated_rr": 3.0,
        "volume_ratio": 1.2,
        "volume_behavior": "expansion",
        "atr": 2.0,
    }
    out.update(overrides)
    return out


def _family_blind_spot_enriched(ticker="VCPX", **overrides):
    out = _base_enriched(
        ticker=ticker,
        structure_event="none",
        fvg=None,
        ob=None,
        retest_status="missing",
        invalidation_level=None,
        targets=[],
        estimated_rr=None,
        setup_family_evidence=_family_evidence(),
    )
    out.update(overrides)
    return out


def test_family_admitted_candidate_repairs_generic_blind_spot_without_erasing_audit_truth():
    cfg = _config()
    result = score_ticker(_family_blind_spot_enriched(), cfg)

    assert "no_clear_structure" in result["original_veto_flags"]
    assert "mid_range_no_edge" in result["original_veto_flags"]
    assert "no_clear_invalidation_estimate" in result["original_veto_flags"]
    assert "no_target_path" in result["original_veto_flags"]
    assert result["veto_flags"] == []
    assert result["effective_admission_vetoes"] == []
    assert set(result["rescued_veto_flags"]) >= {
        "no_clear_structure",
        "mid_range_no_edge",
        "no_clear_invalidation_estimate",
        "no_target_path",
    }
    assert result["eligible_for_model"] is True
    assert result["eligible_for_claude"] is True
    assert result["admission_source"] == "family"
    assert result["family_admission"]["admitted_by_family"] is True
    assert result["key_features"]["original_prefilter_vetoes"] == result["original_veto_flags"]


def test_family_never_rescue_overhead_blocker_still_rejects_candidate():
    cfg = _config()
    enriched = _base_enriched(
        overhead_status="blocked",
        setup_family_evidence=_family_evidence(),
    )
    result = score_ticker(enriched, cfg)

    assert "overhead_blocked" in result["original_veto_flags"]
    assert "overhead_blocked" in result["veto_flags"]
    assert "overhead_blocked" in result["effective_admission_vetoes"]
    assert result["eligible_for_model"] is False
    assert result["admission_source"] == "none"


def test_no_family_evidence_preserves_legacy_prefilter_eligibility_score_and_veto_semantics():
    cfg = _config()
    enriched = _base_enriched()
    baseline = score_ticker(enriched, cfg)

    assert baseline["legacy_prefilter_eligible"] is True
    assert baseline["eligible_for_model"] is True
    assert baseline["eligible_for_claude"] is True
    assert baseline["admission_source"] == "legacy"
    assert baseline["admission_rank_score"] == baseline["prefilter_score"]
    assert baseline["family_admission"]["active"] is False
    assert baseline["veto_flags"] == baseline["original_veto_flags"]


def test_rescued_prefilter_blind_spot_does_not_poison_downstream_tiering():
    cfg = _config()
    pf = score_ticker(_family_blind_spot_enriched(), cfg)
    assert pf["original_veto_flags"]
    assert pf["veto_flags"] == []

    # Family admission itself grants no capital. A fresh downstream signal must
    # independently prove the existing STARTER execution contract.
    raw_signal = {
        "ticker": "VCPX",
        "timestamp_et": "2026-08-19T10:30:00-04:00",
        "tier": "STARTER",
        "score": 80,
        "setup_family": "compression_to_expansion",
        "structure_event": "accepted_break",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "support_cluster",
        "trigger_level": 100.0,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below defended family structure",
        "invalidation_level": 96.0,
        "targets": [{"label": "T1", "level": 112.0, "reason": "family target path"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "developing",
        "missing_conditions": [],
        "upgrade_trigger": "break and hold above next pivot",
        "next_action": "starter only",
        "discord_channel": "#starter-signals",
        "capital_action": "starter_only",
        "reason": "Family candidate independently proved starter execution gates.",
    }
    validated = tiering.validate(raw_signal, pf, cfg)
    assert validated["final_tier"] == "STARTER"
    assert validated["capital_action"] == "starter_only"


def test_family_rank_repairs_selection_priority_without_overwriting_prefilter_score():
    cfg = _config()
    legacy = _base_enriched(
        ticker="LEGACY",
        sma_value_alignment="mixed",
        structure_event="reclaim",
        retest_status="partial",
        volume_behavior="neutral",
    )
    family = _family_blind_spot_enriched(
        ticker="FAMILY",
        volume_behavior="neutral",
        setup_family_evidence=_family_evidence(score=90),
    )

    result = prefilter([legacy, family], cfg)
    rows = {r["ticker"]: r for r in result["all_results"]}

    assert rows["FAMILY"]["prefilter_score"] < rows["LEGACY"]["prefilter_score"]
    assert rows["LEGACY"]["admission_rank_score"] < 90
    assert rows["FAMILY"]["admission_rank_score"] == 90
    assert result["ranked_results"][0]["ticker"] == "FAMILY"
    assert rows["FAMILY"]["prefilter_score"] != rows["FAMILY"]["admission_rank_score"]


def test_provider_neutral_candidate_alias_matches_historical_compatibility_alias():
    cfg = _config()
    result = prefilter([_base_enriched(ticker="AAA")], cfg)
    assert result["model_candidates"] is result["claude_candidates"]
    assert result["board_summary"]["total_model_candidates"] == result["board_summary"]["total_claude_candidates"]


def test_deep_analysis_candidate_cap_stays_30():
    cfg = _config()
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30
    board = [_base_enriched(ticker=f"S{i:03d}") for i in range(45)]
    result = prefilter(board, cfg)
    assert len(result["model_candidates"]) == 30
    assert len(result["claude_candidates"]) == 30


def test_gpt_prompt_contains_normalized_setup_family_lifecycle_evidence():
    enriched = _base_enriched(
        ticker="VCPX",
        setup_family_evidence=_family_evidence(score=88, rr=4.1),
    )
    prompt = build_prompt(enriched)

    assert "SETUP_FAMILY_PRIMARY: VCP_BREAK_RETEST" in prompt
    assert "SETUP_FAMILY_STATE: FINAL_CONTRACTION" in prompt
    assert "SETUP_FAMILY_SCORE: 88" in prompt
    assert "SETUP_FAMILY_ADMISSION_READY: True" in prompt
    assert "SETUP_FAMILY_RR_TO_T1: 4.1" in prompt
    assert "SETUP_FAMILY_METRICS:" in prompt
    assert '"range_contracting":true' in prompt


def test_gpt_prompt_omits_family_context_when_no_family_is_detected():
    enriched = _base_enriched(
        setup_family_evidence={
            "version": "SFC-1",
            "primary_family": "NONE",
            "detected_families": [],
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "primary_state": "NONE",
            "primary_family_score": 0,
            "families": {},
        }
    )
    prompt = build_prompt(enriched)
    assert "SETUP_FAMILY_PRIMARY:" not in prompt


def _daily_frame(n=150):
    idx = pd.date_range("2026-01-02", periods=n, freq="B", tz="UTC")
    close = np.linspace(80.0, 120.0, n)
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def test_indicators_family_compiler_receives_completed_daily_frame_and_closed_retest(monkeypatch):
    cfg = _config()
    raw = _daily_frame(150)
    confirmed = raw.iloc[:-1].copy()
    live_row = raw.iloc[-1]

    monkeypatch.setattr(
        indicators,
        "partition_daily_bars",
        lambda df, now_utc=None: {
            "context": {"status": "DEVELOPING"},
            "confirmed_df": confirmed,
            "live_row": live_row,
        },
    )
    monkeypatch.setattr(
        indicators,
        "assess_retest",
        lambda cur, fvg, ob, atr: {
            "retest_status": "missing",
            "retest_zone": None,
            "retest_distance_atr": None,
        },
    )
    monkeypatch.setattr(
        indicators,
        "live_retest_context",
        lambda cur, fvg, ob, atr: {
            "live_zone": "FVG",
            "live_zone_low": 100.0,
            "live_zone_high": 101.0,
            "live_interaction": "INSIDE_ZONE",
            "live_distance_atr": 0.0,
            "confirms_retest": False,
            "confirms_failure": False,
        },
    )

    captured = {}

    def fake_compile(frame, current_price, base_features, config):
        captured["frame"] = frame
        captured["current_price"] = current_price
        captured["base_features"] = deepcopy(base_features)
        return {
            "version": "SFC-1",
            "primary_family": "NONE",
            "detected_families": [],
            "watch_ready": False,
            "admission_ready": False,
            "entry_structure_valid": False,
            "primary_state": "NONE",
            "primary_family_score": 0,
            "families": {},
        }

    monkeypatch.setattr(indicators.setup_family_compiler, "compile_setup_families", fake_compile)
    result = indicators.enrich("TEST", raw, cfg)

    assert captured["frame"].equals(confirmed)
    assert len(captured["frame"]) == len(raw) - 1
    assert captured["base_features"]["retest_status"] == "missing"
    assert result["retest_status"] == "partial"
    assert result["daily_retest_proof"] == "PROVISIONAL_LIVE"
    assert result["setup_family_evidence"]["primary_family"] == "NONE"

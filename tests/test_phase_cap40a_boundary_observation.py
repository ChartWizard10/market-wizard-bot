"""CAP-40A — candidate-cap boundary observation regressions.

CAP-40A observes the decision boundary. It never changes the 30-candidate
production cap and never pays for analysis of ranks 31-40.
"""

import ast
from copy import deepcopy
from pathlib import Path

from src import capacity_boundary_observation as cap40
from src import velocity_research


def _result(**overrides):
    base = {
        "ticker": "TEST",
        "prefilter_score": 74,
        "admission_rank_score": 86,
        "admission_source": "family",
        "key_features": {
            "setup_family_primary": "BREAK_RETEST_CONTINUATION",
            "setup_family_state": "RETEST_HOLD",
            "setup_family_score": 91,
            "setup_family_watch_ready": True,
            "setup_family_admission_ready": True,
            "setup_family_entry_structure_valid": True,
            "setup_family_invalidation": 95.0,
            "setup_family_rr_to_t1": 3.6,
            "retest_status": "confirmed",
            "overhead_status": "clear",
            "estimated_rr": 3.6,
        },
    }
    base.update(overrides)
    return base


def _enriched(**overrides):
    base = {
        "ticker": "TEST",
        "current_price": 100.0,
        "invalidation_level": 92.0,
        "overhead_level": 112.0,
        "targets": [112.0],
        "atr": 3.0,
        "setup_family_evidence": {
            "primary_invalidation_level": 94.0,
        },
    }
    base.update(overrides)
    return base


def _obs(rank=31, result=None, enriched=None, **kwargs):
    return cap40.build_boundary_observation(
        "2026-08-20T09:35:00-04:00",
        rank,
        _result() if result is None else result,
        _enriched() if enriched is None else enriched,
        scan_id="scan_20260820_133500_deadbe",
        **kwargs,
    )


def test_default_band_boundaries_are_exactly_21_to_30_and_31_to_40():
    assert cap40.study_band(20) == cap40.BAND_OUTSIDE
    assert cap40.study_band(21) == cap40.BAND_BASELINE_EDGE
    assert cap40.study_band(30) == cap40.BAND_BASELINE_EDGE
    assert cap40.study_band(31) == cap40.BAND_SHADOW_INCREMENT
    assert cap40.study_band(40) == cap40.BAND_SHADOW_INCREMENT
    assert cap40.study_band(41) == cap40.BAND_OUTSIDE


def test_custom_cap_increment_and_baseline_width_are_not_hardcoded():
    assert cap40.study_band(31, current_cap=40, increment=5, baseline_width=10) == cap40.BAND_BASELINE_EDGE
    assert cap40.study_band(40, current_cap=40, increment=5, baseline_width=10) == cap40.BAND_BASELINE_EDGE
    assert cap40.study_band(41, current_cap=40, increment=5, baseline_width=10) == cap40.BAND_SHADOW_INCREMENT
    assert cap40.study_band(45, current_cap=40, increment=5, baseline_width=10) == cap40.BAND_SHADOW_INCREMENT
    assert cap40.study_band(46, current_cap=40, increment=5, baseline_width=10) == cap40.BAND_OUTSIDE


def test_invalid_rank_or_geometry_stays_outside_study():
    for rank in (None, "bad", 0, -1):
        assert cap40.study_band(rank) == cap40.BAND_OUTSIDE
    assert cap40.study_band(30, current_cap=0) == cap40.BAND_OUTSIDE
    assert cap40.study_band(30, increment=0) == cap40.BAND_OUTSIDE
    assert cap40.study_band(30, baseline_width=0) == cap40.BAND_OUTSIDE


def test_outside_band_produces_no_observation():
    assert _obs(rank=20) is None
    assert _obs(rank=41) is None


def test_stable_scan_and_ticker_identity_are_persisted_for_future_linking():
    obs = _obs(rank=31)
    assert obs["scan_id"] == "scan_20260820_133500_deadbe"
    assert obs["ticker"] == "TEST"
    assert obs["observed_at"] == "2026-08-20T09:35:00-04:00"
    assert obs["rank"] == 31
    assert obs["band"] == cap40.BAND_SHADOW_INCREMENT
    assert obs["ready"] is True
    assert obs["missing"] == []


def test_ticker_falls_back_to_enriched_identity_but_is_never_invented():
    result = _result()
    result.pop("ticker")
    obs = _obs(result=result)
    assert obs["ticker"] == "TEST"
    assert obs["ready"] is True

    enriched = _enriched()
    enriched.pop("ticker")
    obs = _obs(result={**result}, enriched=enriched)
    assert obs["ticker"] is None
    assert obs["ready"] is False
    assert "ticker" in obs["missing"]


def test_missing_scan_identity_prevents_research_ready_state():
    obs = cap40.build_boundary_observation(
        "2026-08-20T09:35:00-04:00",
        31,
        _result(),
        _enriched(),
    )
    assert obs["scan_id"] is None
    assert obs["ready"] is False
    assert "scan_id" in obs["missing"]


def test_family_key_feature_invalidation_has_priority():
    obs = _obs()
    assert obs["invalidation_level"] == 95.0
    assert obs["invalidation_source"] == "setup_family_invalidation"


def test_enriched_family_invalidation_is_second_choice():
    result = _result()
    result["key_features"] = dict(result["key_features"])
    result["key_features"]["setup_family_invalidation"] = 101.0
    obs = _obs(result=result)
    assert obs["invalidation_level"] == 94.0
    assert obs["invalidation_source"] == "setup_family_evidence.primary_invalidation_level"


def test_generic_invalidation_is_final_fallback_without_fabrication():
    result = _result()
    result["key_features"] = dict(result["key_features"])
    result["key_features"].pop("setup_family_invalidation")
    enriched = _enriched(setup_family_evidence={})
    obs = _obs(result=result, enriched=enriched)
    assert obs["invalidation_level"] == 92.0
    assert obs["invalidation_source"] == "invalidation_level"

    enriched["invalidation_level"] = 101.0
    obs = _obs(result=result, enriched=enriched)
    assert obs["invalidation_level"] is None
    assert obs["invalidation_source"] is None
    assert obs["ready"] is False
    assert "invalidation_level" in obs["missing"]


def test_missing_reference_price_remains_missing():
    enriched = _enriched()
    for key in ("current_price", "latest_close", "close"):
        enriched.pop(key, None)
    obs = _obs(enriched=enriched)
    assert obs["reference_price"] is None
    assert obs["ready"] is False
    assert "reference_price" in obs["missing"]


def test_velocity_feasibility_is_copied_as_research_evidence_only():
    obs = _obs()
    assert obs["feasibility_status"] == velocity_research.FEASIBILITY_SUPPORTED
    assert obs["known_path_room_pct"] == 12.0
    assert obs["atr_pct"] == 3.0
    assert obs["required_move_atr"] == round(8.0 / 3.0, 3)
    assert obs["target_return_pct"] == 8.0
    assert obs["horizon_sessions"] == 5.0


def test_family_and_admission_fields_are_preserved_without_tier_claim():
    obs = _obs(rank=25)
    assert obs["band"] == cap40.BAND_BASELINE_EDGE
    assert obs["prefilter_score"] == 74.0
    assert obs["admission_rank_score"] == 86.0
    assert obs["admission_source"] == "family"
    assert obs["primary_family"] == "BREAK_RETEST_CONTINUATION"
    assert obs["family_state"] == "RETEST_HOLD"
    assert obs["family_score"] == 91.0
    assert obs["family_watch_ready"] is True
    assert obs["family_admission_ready"] is True
    assert obs["family_entry_structure_valid"] is True
    assert obs["family_rr_to_t1"] == 3.6
    assert obs["retest_status"] == "confirmed"
    assert obs["overhead_status"] == "clear"
    assert obs["estimated_rr"] == 3.6


def test_all_authority_flags_remain_false():
    obs = _obs()
    assert obs["research_only"] is True
    assert obs["observational_only"] is True
    for key in (
        "model_authority",
        "candidate_cap_authority",
        "tier_authority",
        "capital_authority",
        "routing_authority",
        "forecast_authority",
    ):
        assert obs[key] is False


def test_observation_does_not_mutate_prefilter_or_enriched_inputs():
    result = _result()
    enriched = _enriched()
    before_result = deepcopy(result)
    before_enriched = deepcopy(enriched)
    _obs(result=result, enriched=enriched)
    assert result == before_result
    assert enriched == before_enriched


def test_source_imports_only_pure_research_dependency_and_makes_no_external_calls():
    path = Path("src/capacity_boundary_observation.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    imported_modules = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called_names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called_names.add(fn.attr)

    assert not any(
        module.startswith(prefix)
        for module in imported_modules
        for prefix in (
            "openai",
            "anthropic",
            "requests",
            "aiohttp",
            "discord",
            "src.scheduler",
            "src.state_store",
            "src.discord_alerts",
            "src.claude_client",
        )
    )
    for forbidden in (
        "async_claude_scan",
        "claude_call",
        "send_alert",
        "record_alert",
        "check_alert",
        "batch_download",
        "fetch_one_hour_bars",
        "apply_ladder_arbitration",
        "validate",
    ):
        assert forbidden not in called_names

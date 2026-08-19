"""CFR-2 production wiring tests.

The green CFR-1 contract is now inserted between raw SFC-1 compilation and the
existing SFC-2B admission/model path.  These tests prove runtime reconciliation
without granting any new tier or routing authority.
"""

from copy import deepcopy

import yaml

from src import indicators
from src import setup_family_runtime as runtime
from src.claude_client import build_prompt
from src.family_admission import build_family_admission_decision
from src.family_resolver import (
    BREAK_RETEST_CONTINUATION,
    GAP_FILL_REVERSAL,
    NONE,
    REL_CONFLUENT,
    SMA_CRADLE_CONTINUATION,
    VCP_BREAK_RETEST,
)


def _config():
    with open("config/doctrine_config.yaml") as f:
        return yaml.safe_load(f)


def _family(
    family_id,
    *,
    state="LIVE",
    score=80,
    detected=True,
    watch=True,
    admission=True,
    entry=False,
    retest="PENDING",
    invalidation=95.0,
    target=112.0,
    rr=3.4,
    path="CLEAN",
    blockers=None,
    soft_caps=None,
    metrics=None,
):
    return {
        "family_id": family_id,
        "detected": detected,
        "state": state,
        "family_score": score,
        "watch_ready": watch,
        "admission_ready": admission,
        "entry_structure_valid": entry,
        "location_valid": True,
        "retest_state": retest,
        "invalidation_level": invalidation,
        "target_1": target,
        "rr_to_t1": rr,
        "path_status": path,
        "blockers": blockers or [],
        "soft_caps": soft_caps or [],
        "metrics": metrics or {},
    }


def _raw_overlap_evidence():
    families = {
        BREAK_RETEST_CONTINUATION: _family(
            BREAK_RETEST_CONTINUATION, detected=False, watch=False, admission=False
        ),
        VCP_BREAK_RETEST: _family(
            VCP_BREAK_RETEST,
            state="FINAL_CONTRACTION",
            score=97,
            entry=False,
            metrics={"pivot": 104.5, "range_contracting": True},
        ),
        SMA_CRADLE_CONTINUATION: _family(
            SMA_CRADLE_CONTINUATION,
            state="CRADLE_RETEST_HELD",
            score=84,
            entry=True,
            retest="HELD",
            invalidation=94.0,
            target=115.0,
            rr=3.8,
            metrics={"defensive_lower_wick": True, "hold": True},
        ),
        GAP_FILL_REVERSAL: _family(
            GAP_FILL_REVERSAL, detected=False, watch=False, admission=False
        ),
    }
    # This intentionally mirrors the pre-CFR raw SFC summary: highest score wins
    # even though the VCP execution lifecycle is unfinished.
    return {
        "version": "SFC-1",
        "primary_family": VCP_BREAK_RETEST,
        "detected_families": [VCP_BREAK_RETEST, SMA_CRADLE_CONTINUATION],
        "watch_ready": True,
        "admission_ready": True,
        "entry_structure_valid": False,
        "primary_state": "FINAL_CONTRACTION",
        "primary_family_score": 97,
        "primary_invalidation_level": 95.0,
        "primary_target_1": 112.0,
        "primary_rr_to_t1": 3.4,
        "families": families,
    }


def test_indicators_uses_cfr2_runtime_facade_not_raw_compiler():
    assert indicators.setup_family_compiler is runtime
    assert runtime.RUNTIME_VERSION == "CFR-2"
    assert runtime.RAW_VERSION == "SFC-1"


def test_runtime_resolves_primary_by_execution_proof_and_preserves_raw(monkeypatch):
    raw = _raw_overlap_evidence()
    before = deepcopy(raw)
    monkeypatch.setattr(runtime._raw_compiler, "compile_setup_families", lambda *a, **k: raw)

    out = runtime.compile_setup_families(None, 101.0, {}, {})

    assert raw == before
    assert out["primary_family"] == SMA_CRADLE_CONTINUATION
    assert out["primary_state"] == "CRADLE_RETEST_HELD"
    assert out["entry_structure_valid"] is True
    assert out["primary_family_score"] == 84
    assert out["family_resolution"]["relationship"] == REL_CONFLUENT
    assert out["family_resolution"]["score_stacking_allowed"] is False
    assert out["family_resolution"]["capital_authority"] is False
    assert out["runtime_version"] == "CFR-2"


def test_runtime_projects_compact_cross_family_context_into_primary_metrics(monkeypatch):
    raw = _raw_overlap_evidence()
    original_primary_metrics = deepcopy(
        raw["families"][SMA_CRADLE_CONTINUATION]["metrics"]
    )
    monkeypatch.setattr(runtime._raw_compiler, "compile_setup_families", lambda *a, **k: raw)

    out = runtime.compile_setup_families(None, 101.0, {}, {})
    metrics = out["families"][SMA_CRADLE_CONTINUATION]["metrics"]
    cfr = metrics["cross_family_resolution"]

    assert raw["families"][SMA_CRADLE_CONTINUATION]["metrics"] == original_primary_metrics
    assert cfr["relationship"] == REL_CONFLUENT
    assert cfr["resolved_primary_family"] == SMA_CRADLE_CONTINUATION
    assert VCP_BREAK_RETEST in cfr["secondary_families"]
    assert cfr["confluence_count"] == 2
    assert cfr["score_stacking_allowed"] is False
    assert cfr["capital_authority"] is False


def test_gpt_prompt_receives_resolved_primary_and_cross_family_context(monkeypatch):
    monkeypatch.setattr(
        runtime._raw_compiler,
        "compile_setup_families",
        lambda *a, **k: _raw_overlap_evidence(),
    )
    evidence = runtime.compile_setup_families(None, 101.0, {}, {})
    prompt = build_prompt({
        "ticker": "TEST",
        "latest_close": 101.0,
        "structure_event": "accepted_break",
        "retest_status": "confirmed",
        "overhead_status": "clear",
        "volume_behavior": "neutral",
        "setup_family_evidence": evidence,
    })

    assert f"SETUP_FAMILY_PRIMARY: {SMA_CRADLE_CONTINUATION}" in prompt
    assert "SETUP_FAMILY_STATE: CRADLE_RETEST_HELD" in prompt
    assert '"cross_family_resolution":{' in prompt
    assert '"relationship":"CONFLUENT"' in prompt
    assert f'"resolved_primary_family":"{SMA_CRADLE_CONTINUATION}"' in prompt
    assert '"score_stacking_allowed":false' in prompt
    assert '"capital_authority":false' in prompt


def test_sfc2b_admission_reads_the_resolved_primary_not_stale_raw_primary(monkeypatch):
    monkeypatch.setattr(
        runtime._raw_compiler,
        "compile_setup_families",
        lambda *a, **k: _raw_overlap_evidence(),
    )
    evidence = runtime.compile_setup_families(None, 101.0, {}, {})
    decision = build_family_admission_decision(
        {"setup_family_evidence": evidence},
        prefilter_score=40,
        veto_flags=[
            "no_clear_structure",
            "mid_range_no_edge",
            "no_clear_invalidation_estimate",
            "no_target_path",
        ],
        config=_config(),
    )

    assert decision["primary_family"] == SMA_CRADLE_CONTINUATION
    assert decision["primary_state"] == "CRADLE_RETEST_HELD"
    assert decision["family_score"] == 84
    assert decision["entry_structure_valid"] is True
    assert decision["admitted_by_family"] is True
    assert decision["remaining_vetoes"] == []


def test_no_detected_family_does_not_invent_model_context(monkeypatch):
    raw = {
        "version": "SFC-1",
        "primary_family": NONE,
        "detected_families": [],
        "watch_ready": False,
        "admission_ready": False,
        "entry_structure_valid": False,
        "primary_state": "NONE",
        "primary_family_score": 0,
        "primary_invalidation_level": None,
        "primary_target_1": None,
        "primary_rr_to_t1": None,
        "families": {
            family_id: _family(
                family_id, detected=False, watch=False, admission=False, score=0
            )
            for family_id in (
                BREAK_RETEST_CONTINUATION,
                VCP_BREAK_RETEST,
                SMA_CRADLE_CONTINUATION,
                GAP_FILL_REVERSAL,
            )
        },
    }
    monkeypatch.setattr(runtime._raw_compiler, "compile_setup_families", lambda *a, **k: raw)

    out = runtime.compile_setup_families(None, 101.0, {}, {})
    prompt = build_prompt({
        "ticker": "TEST",
        "latest_close": 101.0,
        "structure_event": "none",
        "retest_status": "missing",
        "overhead_status": "unknown",
        "volume_behavior": "neutral",
        "setup_family_evidence": out,
    })

    assert out["primary_family"] == NONE
    assert out["family_resolution"]["resolved_primary_family"] == NONE
    assert out["family_resolution"]["capital_authority"] is False
    assert "SETUP_FAMILY_PRIMARY:" not in prompt

"""CFR-2 resolved-family production wiring regression tests."""

from copy import deepcopy

import yaml

from src.claude_client import build_prompt
from src.family_admission import build_family_admission_decision
from src.family_resolver import reconcile_compiled_evidence


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
    invalidation=96.0,
    target=112.0,
    rr=3.5,
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


def _evidence(families, compiler_primary, compiler_state, compiler_score):
    primary_obj = families[compiler_primary]
    return {
        "version": "SFC-1",
        "primary_family": compiler_primary,
        "detected_families": [
            k for k, v in families.items() if isinstance(v, dict) and v.get("detected")
        ],
        "watch_ready": bool(primary_obj.get("watch_ready")),
        "admission_ready": bool(primary_obj.get("admission_ready")),
        "entry_structure_valid": bool(primary_obj.get("entry_structure_valid")),
        "primary_state": compiler_state,
        "primary_family_score": compiler_score,
        "primary_invalidation_level": primary_obj.get("invalidation_level"),
        "primary_target_1": primary_obj.get("target_1"),
        "primary_rr_to_t1": primary_obj.get("rr_to_t1"),
        "families": families,
    }


def _enriched(evidence):
    return {
        "ticker": "TEST",
        "data_status": "OK",
        "current_price": 100.0,
        "latest_close": 100.0,
        "sma20": 98.0,
        "sma50": 95.0,
        "sma200": 88.0,
        "sma_value_alignment": "supportive",
        "price_extension_from_sma20_pct": 2.0,
        "structure_event": "none",
        "wick_only_break": False,
        "fvg": None,
        "ob": None,
        "retest_status": "missing",
        "overhead_status": "clear",
        "volume_behavior": "dryup",
        "invalidation_level": None,
        "targets": [],
        "estimated_rr": None,
        "atr": 2.0,
        "setup_family_evidence": evidence,
    }


def test_admission_uses_cfr_resolved_primary_not_raw_highest_family_score():
    cfg = _config()
    families = {
        "VCP_BREAK_RETEST": _family(
            "VCP_BREAK_RETEST",
            state="FINAL_CONTRACTION",
            score=98,
            admission=True,
            entry=False,
            metrics={"range_contracting": True},
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            score=84,
            admission=True,
            entry=True,
            retest="HELD",
            invalidation=94.0,
            target=115.0,
            rr=3.8,
            metrics={"defensive_lower_wick": True},
        ),
    }
    evidence = _evidence(families, "VCP_BREAK_RETEST", "FINAL_CONTRACTION", 98)
    enriched = _enriched(evidence)

    decision = build_family_admission_decision(
        enriched,
        45,
        [
            "no_clear_structure",
            "mid_range_no_edge",
            "no_clear_invalidation_estimate",
            "no_target_path",
        ],
        cfg,
    )

    assert decision["primary_family"] == "SMA_CRADLE_CONTINUATION"
    assert decision["compiler_primary_family"] == "VCP_BREAK_RETEST"
    assert decision["family_relationship"] == "CONFLUENT"
    assert decision["entry_structure_valid"] is True
    assert decision["family_score"] == 84
    assert decision["admission_rank_score"] == 87
    assert decision["admission_rank_score"] < 98
    assert decision["admitted_by_family"] is True

    # Deliberate CFR-2 normalization side effect: the later GPT prompt sees the
    # exact same resolved primary that admission used.
    normalized = enriched["setup_family_evidence"]
    assert normalized["primary_family"] == "SMA_CRADLE_CONTINUATION"
    assert normalized["compiler_primary_family"] == "VCP_BREAK_RETEST"
    assert normalized["families"] == families


def test_confluence_never_stacks_scores_into_admission_rank():
    cfg = _config()
    families = {
        "BREAK_RETEST_CONTINUATION": _family(
            "BREAK_RETEST_CONTINUATION",
            state="RETEST_HELD",
            score=92,
            entry=True,
            retest="HELD",
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            score=91,
            entry=True,
            retest="HELD",
        ),
    }
    evidence = _evidence(families, "BREAK_RETEST_CONTINUATION", "RETEST_HELD", 92)
    decision = build_family_admission_decision(_enriched(evidence), 60, [], cfg)

    assert decision["family_relationship"] == "CONFLUENT"
    assert decision["confluence_count"] == 2
    assert decision["admission_rank_score"] == 95  # 92 + existing entry-proof bonus, capped
    assert decision["admission_rank_score"] != 92 + 91


def test_local_failed_sibling_does_not_poison_valid_primary_admission():
    cfg = _config()
    families = {
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="VALUE_RECLAIMED",
            score=84,
            admission=True,
            entry=False,
        ),
        "GAP_FILL_REVERSAL": _family(
            "GAP_FILL_REVERSAL",
            state="FAILED_ACCEPTANCE_BELOW_GAP",
            score=58,
            watch=False,
            admission=False,
            blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
        ),
    }
    evidence = _evidence(families, "GAP_FILL_REVERSAL", "FAILED_ACCEPTANCE_BELOW_GAP", 58)
    enriched = _enriched(evidence)

    decision = build_family_admission_decision(
        enriched,
        50,
        ["no_clear_structure", "mid_range_no_edge"],
        cfg,
    )

    assert decision["primary_family"] == "SMA_CRADLE_CONTINUATION"
    assert decision["family_relationship"] == "CONTRADICTORY"
    assert decision["family_conflict_scope"] == "LOCAL"
    assert "GAP_FILL_REVERSAL" in decision["failed_families"]
    assert decision["admitted_by_family"] is True
    assert decision["remaining_vetoes"] == []


def test_shared_common_veto_remains_active_and_unrescued():
    cfg = _config()
    families = {
        "VCP_BREAK_RETEST": _family(
            "VCP_BREAK_RETEST",
            state="FINAL_CONTRACTION",
            score=86,
            admission=True,
        ),
        "BREAK_RETEST_CONTINUATION": _family(
            "BREAK_RETEST_CONTINUATION",
            state="FAILED",
            score=20,
            watch=False,
            admission=False,
            retest="FAILED",
            blockers=["RETEST_FAILED"],
        ),
    }
    evidence = _evidence(families, "VCP_BREAK_RETEST", "FINAL_CONTRACTION", 86)
    enriched = _enriched(evidence)

    decision = build_family_admission_decision(
        enriched,
        70,
        ["retest_failed"],
        cfg,
    )

    assert decision["family_relationship"] == "CONTRADICTORY"
    assert decision["family_conflict_scope"] == "SHARED"
    assert "RETEST_FAILED" in decision["shared_failure_codes"]
    assert decision["admitted_by_family"] is False
    assert decision["rescued_vetoes"] == []
    assert decision["remaining_vetoes"] == ["retest_failed"]


def test_prompt_defensively_resolves_and_exposes_cfr_relationship_context():
    families = {
        "VCP_BREAK_RETEST": _family(
            "VCP_BREAK_RETEST",
            state="FINAL_CONTRACTION",
            score=97,
            admission=True,
            entry=False,
            metrics={"range_contracting": True, "volume_contracting": True},
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            score=84,
            admission=True,
            entry=True,
            retest="HELD",
            metrics={"defensive_lower_wick": True},
        ),
    }
    evidence = _evidence(families, "VCP_BREAK_RETEST", "FINAL_CONTRACTION", 97)
    enriched = _enriched(evidence)

    # Direct prompt construction bypasses prefilter on purpose. The prompt
    # helper must still resolve the family relationship defensively.
    prompt = build_prompt(enriched)

    assert "SETUP_FAMILY_PRIMARY: SMA_CRADLE_CONTINUATION" in prompt
    assert "SETUP_FAMILY_COMPILER_PRIMARY: VCP_BREAK_RETEST" in prompt
    assert "SETUP_FAMILY_RELATIONSHIP: CONFLUENT" in prompt
    assert "SETUP_FAMILY_CONFLICT_SCOPE: NONE" in prompt
    assert "SETUP_FAMILY_SECONDARY: VCP_BREAK_RETEST" in prompt
    assert "SETUP_FAMILY_CONFLUENCE_COUNT: 2" in prompt
    assert "SETUP_FAMILY_SCORE_STACKING_ALLOWED: False" in prompt
    assert "SETUP_FAMILY_CAPITAL_AUTHORITY: False" in prompt
    assert '"defensive_lower_wick":true' in prompt
    assert '"range_contracting":true' not in prompt  # non-primary metrics are not mislabeled as primary


def test_prompt_exposes_local_failed_sibling_without_calling_primary_failed():
    families = {
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="VALUE_RECLAIMED",
            score=82,
            admission=True,
        ),
        "GAP_FILL_REVERSAL": _family(
            "GAP_FILL_REVERSAL",
            state="FAILED_ACCEPTANCE_BELOW_GAP",
            score=55,
            watch=False,
            admission=False,
            blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
        ),
    }
    evidence = _evidence(families, "GAP_FILL_REVERSAL", "FAILED_ACCEPTANCE_BELOW_GAP", 55)
    prompt = build_prompt(_enriched(evidence))

    assert "SETUP_FAMILY_PRIMARY: SMA_CRADLE_CONTINUATION" in prompt
    assert "SETUP_FAMILY_RELATIONSHIP: CONTRADICTORY" in prompt
    assert "SETUP_FAMILY_CONFLICT_SCOPE: LOCAL" in prompt
    assert "SETUP_FAMILY_FAILED_SIBLINGS: GAP_FILL_REVERSAL" in prompt


def test_reconciliation_is_idempotent_and_preserves_original_compiler_provenance():
    families = {
        "VCP_BREAK_RETEST": _family(
            "VCP_BREAK_RETEST",
            state="FINAL_CONTRACTION",
            score=98,
            admission=True,
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            score=84,
            admission=True,
            entry=True,
            retest="HELD",
        ),
    }
    source = _evidence(families, "VCP_BREAK_RETEST", "FINAL_CONTRACTION", 98)
    before = deepcopy(source)
    once = reconcile_compiled_evidence(source)
    twice = reconcile_compiled_evidence(once)

    assert source == before
    assert once["compiler_primary_family"] == "VCP_BREAK_RETEST"
    assert twice["compiler_primary_family"] == "VCP_BREAK_RETEST"
    assert once["primary_family"] == twice["primary_family"] == "SMA_CRADLE_CONTINUATION"
    assert once["families"] == twice["families"] == families


def test_cfr2_does_not_change_candidate_capacity_contract():
    cfg = _config()
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30

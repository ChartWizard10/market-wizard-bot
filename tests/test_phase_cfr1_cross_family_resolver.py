"""CFR-1 cross-family contradiction/confluence resolver tests."""

from copy import deepcopy

from src.family_resolver import (
    BREAK_RETEST_CONTINUATION,
    CONFLICT_LOCAL,
    CONFLICT_NONE,
    CONFLICT_SHARED,
    GAP_FILL_REVERSAL,
    NONE,
    REL_ALL_FAILED,
    REL_AMBIGUOUS,
    REL_COMPATIBLE,
    REL_CONFLUENT,
    REL_CONTRADICTORY,
    REL_NONE,
    REL_SINGLE,
    SMA_CRADLE_CONTINUATION,
    VCP_BREAK_RETEST,
    reconcile_compiled_evidence,
    resolve_families,
)


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
        "metrics": {},
    }


def _all(**overrides):
    families = {
        BREAK_RETEST_CONTINUATION: _family(BREAK_RETEST_CONTINUATION, detected=False),
        VCP_BREAK_RETEST: _family(VCP_BREAK_RETEST, detected=False),
        SMA_CRADLE_CONTINUATION: _family(SMA_CRADLE_CONTINUATION, detected=False),
        GAP_FILL_REVERSAL: _family(GAP_FILL_REVERSAL, detected=False),
    }
    families.update(overrides)
    return families


def test_no_detected_family_resolves_to_none():
    result = resolve_families(_all())
    assert result["relationship"] == REL_NONE
    assert result["resolved_primary_family"] == NONE
    assert result["admission_ready"] is False
    assert result["capital_authority"] is False
    assert result["score_stacking_allowed"] is False


def test_single_viable_family_remains_single_primary():
    families = _all(
        **{
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                state="FINAL_CONTRACTION",
                score=86,
                admission=True,
            )
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_SINGLE
    assert result["conflict_scope"] == CONFLICT_NONE
    assert result["resolved_primary_family"] == VCP_BREAK_RETEST
    assert result["admission_ready"] is True


def test_entry_structure_proof_outranks_higher_unfinished_family_score():
    families = _all(
        **{
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                state="FINAL_CONTRACTION",
                score=97,
                admission=True,
                entry=False,
            ),
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                state="CRADLE_RETEST_HELD",
                score=84,
                admission=True,
                entry=True,
                retest="HELD",
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_CONFLUENT
    assert result["resolved_primary_family"] == SMA_CRADLE_CONTINUATION
    assert result["entry_structure_valid"] is True
    assert result["confluence_count"] == 2


def test_confluence_never_sums_or_inflates_family_scores():
    families = _all(
        **{
            BREAK_RETEST_CONTINUATION: _family(
                BREAK_RETEST_CONTINUATION,
                state="RETEST_HELD",
                score=92,
                entry=True,
                retest="HELD",
            ),
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                state="CRADLE_RETEST_HELD",
                score=90,
                entry=True,
                retest="HELD",
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_CONFLUENT
    assert result["score_stacking_allowed"] is False
    assert max(x["family_score"] for x in result["family_snapshots"]) == 92
    assert sum(x["family_score"] for x in result["family_snapshots"]) > 100
    assert result["capital_authority"] is False


def test_one_ready_family_plus_watch_family_is_compatible_not_contradictory():
    families = _all(
        **{
            BREAK_RETEST_CONTINUATION: _family(
                BREAK_RETEST_CONTINUATION,
                score=88,
                admission=True,
                watch=True,
            ),
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                state="FINAL_CONTRACTION",
                score=76,
                admission=False,
                watch=True,
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_COMPATIBLE
    assert result["resolved_primary_family"] == BREAK_RETEST_CONTINUATION


def test_multiple_developing_families_without_ready_primary_are_ambiguous():
    families = _all(
        **{
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                score=74,
                admission=False,
                watch=True,
            ),
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                score=72,
                admission=False,
                watch=True,
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_AMBIGUOUS
    assert result["admission_ready"] is False


def test_family_local_gap_failure_does_not_cancel_valid_cradle_primary():
    families = _all(
        **{
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                state="CRADLE_RETEST_HELD",
                score=86,
                admission=True,
                entry=True,
                retest="HELD",
            ),
            GAP_FILL_REVERSAL: _family(
                GAP_FILL_REVERSAL,
                state="FAILED_ACCEPTANCE_BELOW_GAP",
                score=58,
                admission=False,
                watch=False,
                entry=False,
                blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_CONTRADICTORY
    assert result["conflict_scope"] == CONFLICT_LOCAL
    assert result["resolved_primary_family"] == SMA_CRADLE_CONTINUATION
    assert result["admission_ready"] is True
    assert GAP_FILL_REVERSAL in result["failed_families"]
    assert "VALID_PRIMARY_PRESERVED_DESPITE_LOCAL_SIBLING_FAILURE" in result["reason_codes"]


def test_shared_retest_failure_is_labeled_shared_for_common_gate_ownership():
    families = _all(
        **{
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                state="FINAL_CONTRACTION",
                score=84,
                admission=True,
            ),
            BREAK_RETEST_CONTINUATION: _family(
                BREAK_RETEST_CONTINUATION,
                state="FAILED",
                score=20,
                admission=False,
                watch=False,
                retest="FAILED",
                blockers=["RETEST_FAILED"],
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_CONTRADICTORY
    assert result["conflict_scope"] == CONFLICT_SHARED
    assert result["resolved_primary_family"] == VCP_BREAK_RETEST
    assert "RETEST_FAILED" in result["shared_failure_codes"]
    assert "COMMON_GATE_FAILURE_REMAINS_SOVEREIGN" in result["reason_codes"]
    # CFR diagnoses the conflict but never overrides common tiering authority.
    assert result["capital_authority"] is False


def test_all_detected_families_failed_is_not_admission_ready():
    families = _all(
        **{
            BREAK_RETEST_CONTINUATION: _family(
                BREAK_RETEST_CONTINUATION,
                state="FAILED",
                score=20,
                admission=False,
                watch=False,
                retest="FAILED",
                blockers=["RETEST_FAILED"],
            ),
            GAP_FILL_REVERSAL: _family(
                GAP_FILL_REVERSAL,
                state="FAILED_ACCEPTANCE_BELOW_GAP",
                score=55,
                admission=False,
                watch=False,
                blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
            ),
        }
    )
    result = resolve_families(families)
    assert result["relationship"] == REL_ALL_FAILED
    assert result["admission_ready"] is False
    assert result["entry_structure_valid"] is False


def test_reconcile_changes_top_level_primary_only_not_family_objects():
    families = _all(
        **{
            VCP_BREAK_RETEST: _family(
                VCP_BREAK_RETEST,
                score=98,
                admission=True,
                entry=False,
            ),
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                state="CRADLE_RETEST_HELD",
                score=84,
                admission=True,
                entry=True,
                retest="HELD",
                invalidation=94.0,
                target=115.0,
                rr=3.8,
            ),
        }
    )
    evidence = {
        "version": "SFC-1",
        "primary_family": VCP_BREAK_RETEST,
        "detected_families": [VCP_BREAK_RETEST, SMA_CRADLE_CONTINUATION],
        "watch_ready": True,
        "admission_ready": True,
        "entry_structure_valid": False,
        "primary_state": "FINAL_CONTRACTION",
        "primary_family_score": 98,
        "primary_invalidation_level": 95.0,
        "primary_target_1": 112.0,
        "primary_rr_to_t1": 3.4,
        "families": families,
    }
    before = deepcopy(evidence)
    reconciled = reconcile_compiled_evidence(evidence)

    assert evidence == before
    assert reconciled["families"] == before["families"]
    assert reconciled["primary_family"] == SMA_CRADLE_CONTINUATION
    assert reconciled["primary_state"] == "CRADLE_RETEST_HELD"
    assert reconciled["primary_family_score"] == 84
    assert reconciled["primary_invalidation_level"] == 94.0
    assert reconciled["primary_target_1"] == 115.0
    assert reconciled["primary_rr_to_t1"] == 3.8
    assert reconciled["entry_structure_valid"] is True
    assert reconciled["family_resolution"]["relationship"] == REL_CONFLUENT


def test_reconcile_local_failed_sibling_preserves_valid_ready_summary():
    families = _all(
        **{
            SMA_CRADLE_CONTINUATION: _family(
                SMA_CRADLE_CONTINUATION,
                state="VALUE_RECLAIMED",
                score=82,
                admission=True,
                entry=False,
            ),
            GAP_FILL_REVERSAL: _family(
                GAP_FILL_REVERSAL,
                state="FAILED_ACCEPTANCE_BELOW_GAP",
                score=60,
                admission=False,
                watch=False,
                blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
            ),
        }
    )
    evidence = {"version": "SFC-1", "families": families}
    out = reconcile_compiled_evidence(evidence)
    assert out["primary_family"] == SMA_CRADLE_CONTINUATION
    assert out["admission_ready"] is True
    assert out["watch_ready"] is True
    assert out["family_resolution"]["conflict_scope"] == CONFLICT_LOCAL


def test_reconcile_all_failed_cannot_keep_stale_admission_ready_summary():
    failed_gap = _family(
        GAP_FILL_REVERSAL,
        state="FAILED_ACCEPTANCE_BELOW_GAP",
        score=60,
        admission=False,
        watch=False,
        blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
    )
    evidence = {
        "version": "SFC-1",
        "primary_family": GAP_FILL_REVERSAL,
        "watch_ready": True,
        "admission_ready": True,
        "entry_structure_valid": True,
        "families": _all(**{GAP_FILL_REVERSAL: failed_gap}),
    }
    out = reconcile_compiled_evidence(evidence)
    assert out["admission_ready"] is False
    assert out["entry_structure_valid"] is False
    assert out["watch_ready"] is False
    assert out["family_resolution"]["relationship"] == REL_ALL_FAILED

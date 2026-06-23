"""Phase 14M.1 — sealed audit normalization patch tests.

Live evidence that triggered this phase: RL scan_20260623_172852_c3cfb5 —
the Phase 14M seal correctly sealed final_tier/capital_action/channel down to
NEAR_ENTRY/wait_no_capital/#near-entry-watch, but the audit ledger still
reported Audit label INCONSISTENT_SNIPE_CONFIRMED and Promotion state
ALREADY_SNIPE — an audit-ledger truth failure, not a trading failure.

This phase makes the audit ledger (snipe_gate_audit.audit_label/
promotion_state, the persisted snipe_confirmed_seal marker, and
audit_access.interpret()/!auditready) tell the same corrected-tier truth that
Phase 14M already enforced in final_tier/capital_action/routing. It never
loosens SNIPE_IT, never invents a promotion path, and never grants capital.
"""

import json

from src import audit_access
from src import snipe_confirmed_seal as seal
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Fixtures (mirrors tests/test_phase_14m_snipe_confirmed_consistency_seal.py)
# ---------------------------------------------------------------------------

def _audit(**over):
    a = {
        "audit_label": "SNIPE_CONFIRMED",
        "promotion_state": "ALREADY_SNIPE",
        "snipe_score": 89,
        "raw_snipe_score": 89,
        "effective_snipe_score": 89,
        "score_blocked_by": [],
        "display_score_label": None,
        "snipe_grade": "A-",
        "eligible_for_snipe_review": True,
        "blocked_gate_names": [],
        "blocked_gates": [],
        "missing_proofs": [],
        "promotion_triggers": [],
        "blocking_reasons": [],
        "diagnostic_sentence": "SNIPE audit: all critical gates confirm; setup is already SNIPE_IT.",
    }
    a.update(over)
    return a


def _signal(**over):
    s = {
        "ticker": "RL", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals",
        "reason": "SNIPE_IT conditions met.", "next_action": "Enter full size now.",
        "retest_status": "confirmed", "hold_status": "confirmed",
        "scan_price": 100.0, "targets": [105, 110], "missing_conditions": [],
    }
    s.update(over)
    return s


def _tr(audit=None, signal=None, final_tier="SNIPE_IT", capital="full_quality_allowed",
        channel="#snipe-signals"):
    sig = dict(signal if signal is not None else _signal())
    sig["tier"] = final_tier
    sig["capital_action"] = capital
    sig["discord_channel"] = channel
    return {
        "final_tier": final_tier, "capital_action": capital,
        "final_discord_channel": channel, "safe_for_alert": True, "score": 88,
        "final_signal": sig,
        "snipe_gate_audit": audit if audit is not None else _audit(),
        "higher_timeframe_context": {"blocks_snipe_contextually": False},
    }


def _rl_tr():
    """The live RL evidence: SNIPE_IT structure with an active 1H trigger and
    candle blocker — corrected by the seal to NEAR_ENTRY (forming, not hard
    failure)."""
    audit = _audit(
        missing_proofs=[
            "ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS",
            "CANDLE_TRUTH_SUPPORTIVE: candle REJECTION indecision/forming",
        ],
    )
    return _tr(audit=audit)


def _live_edge_blocked_tr():
    """A second SNIPE-shaped structure (a different blocker than _rl_tr) used
    only to confirm the seal/ledger normalization generalizes beyond the RL
    fixture — not for asserting a specific WAIT/NEAR_ENTRY tier (that routing
    rule belongs to Phase 14M, not 14M.1)."""
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK",
                                   "reason": "candle veto HOSTILE_WICK"}])
    return _tr(audit=audit)


def _row(tier="SNIPE_IT", audit=None, seal_marker=None, retest="confirmed", hold="confirmed",
         capital_action="full_quality_allowed", channel="snipe"):
    row = {
        "ticker": "RL", "tier": tier, "scan_id": "scan_20260623_172852_c3cfb5",
        "alerted_at": "2026-06-23T17:32:16.213726", "retest_status": retest,
        "hold_status": hold, "capital_action": capital_action,
        "score": 88, "final_discord_channel": channel,
        "snipe_gate_audit": audit if audit is not None else _audit(),
        "higher_timeframe_context": {},
    }
    if seal_marker is not None:
        row["snipe_confirmed_seal"] = seal_marker
    return row


# ===========================================================================
# 1 — post-14M sealed NEAR_ENTRY row (the live RL evidence)
# ===========================================================================

def test_sealed_near_entry_corrects_trading_fields():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert tr["final_discord_channel"] == "#near-entry-watch"
    assert tr["safe_for_alert"] is True
    assert tr["final_signal"]["tier"] == "NEAR_ENTRY"
    assert tr["final_signal"]["capital_action"] == "wait_no_capital"
    assert tr["final_signal"]["discord_channel"] == "#near-entry-watch"


def test_sealed_near_entry_audit_ledger_no_longer_already_snipe():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    sga = tr["snipe_gate_audit"]
    assert sga["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert sga["promotion_state"] != "ALREADY_SNIPE"
    assert sga["promotion_state"] in ("PROMOTION_BLOCKED", "PROMOTION_PENDING")


def test_sealed_near_entry_diagnostic_names_corrected_tier():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    diag = tr["snipe_confirmed_seal"]["diagnostic"]
    assert "SNIPE confirmation blocked" in diag
    assert "NEAR_ENTRY" in diag
    assert diag == tr["snipe_gate_audit"]["diagnostic_sentence"]


def test_sealed_near_entry_marker_shape():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    marker = tr["snipe_confirmed_seal"]
    assert marker["applied"] is True
    assert marker["original_tier"] == "SNIPE_IT"
    assert marker["sealed_tier"] == "NEAR_ENTRY"
    assert marker["reason"] == "active SNIPE confirmation blocker remained"
    assert isinstance(marker["active_blockers"], list) and marker["active_blockers"]
    assert marker["sealed_by_phase"] == "14M"
    json.dumps(marker, allow_nan=False)


def test_sealed_near_entry_interpret_is_not_inconsistent_snipe_confirmed():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    row = _row(tier=tr["final_tier"], audit=tr["snipe_gate_audit"],
               seal_marker=tr["snipe_confirmed_seal"],
               capital_action=tr["capital_action"], channel=tr["final_discord_channel"])
    verdict = audit_access.interpret(row)
    assert verdict["label"] == "CORRECT_NEAR_ENTRY"
    assert verdict["label"] not in ("INCONSISTENT_SNIPE_CONFIRMED", "POSSIBLE_UNDER_PROMOTION", "SNIPE_CONFIRMED")


def test_sealed_near_entry_excluded_from_auditready():
    tr = _rl_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    row = _row(tier=tr["final_tier"], audit=tr["snipe_gate_audit"],
               seal_marker=tr["snipe_confirmed_seal"],
               capital_action=tr["capital_action"], channel=tr["final_discord_channel"])
    ok, why = audit_access.is_auditready_candidate(row)
    assert ok is False
    assert any("snipe_confirmed_seal" in r for r in why)


def test_sealed_near_entry_persisted_via_record_alert():
    tr = _rl_tr()
    tr["final_signal"]["ticker"] = "RL"
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = record_alert("RL", tr, {"tickers": {}, "meta": {}},
                          {"state": {"max_memory_entries": 500}}, "scan_rl")
    row = state["tickers"]["RL"]["alert_history"][-1]
    assert row["tier"] == "NEAR_ENTRY"
    assert row["capital_action"] == "wait_no_capital"
    assert row["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert row["snipe_gate_audit"]["promotion_state"] != "ALREADY_SNIPE"
    assert row["snipe_confirmed_seal"]["applied"] is True
    assert row["snipe_confirmed_seal"]["sealed_tier"] == "NEAR_ENTRY"
    assert audit_access.interpret(row)["label"] == "CORRECT_NEAR_ENTRY"
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is False
    json.dumps(row, allow_nan=False)


# ===========================================================================
# 2 — post-14M sealed STARTER row
# ===========================================================================

def test_sealed_starter_row_interprets_correct_starter_and_excluded():
    """A sealed-down row whose corrected tier is STARTER (not NEAR_ENTRY) must
    resolve the same way: corrected tier truth, never ALREADY_SNIPE, never
    flagged by !auditready. Built directly off the seal marker contract rather
    than re-deriving Phase 14M's WAIT-vs-NEAR_ENTRY routing rules."""
    seal_marker = {
        "applied": True, "original_tier": "SNIPE_IT", "sealed_tier": "STARTER",
        "reason": "active SNIPE confirmation blocker remained",
        "active_blockers": ["1H trigger_state RETEST_IN_PROGRESS"],
        "sealed_by_phase": "14M",
    }
    audit = _audit(audit_label="SNIPE_CONFIRMATION_BLOCKED", promotion_state="PROMOTION_BLOCKED",
                   missing_proofs=["ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS"],
                   diagnostic_sentence="SNIPE confirmation blocked; final tier sealed to STARTER "
                                       "because unresolved proof remains.")
    row = _row(tier="STARTER", audit=audit, seal_marker=seal_marker,
               capital_action="starter_only", channel="#starter-signals")
    verdict = audit_access.interpret(row)
    assert verdict["label"] == "CORRECT_STARTER"
    ok, why = audit_access.is_auditready_candidate(row)
    assert ok is False
    assert any("snipe_confirmed_seal" in r for r in why)


# ===========================================================================
# 3 — legacy historical SNIPE_IT row with blockers (no seal marker)
# ===========================================================================

def test_legacy_unsealed_snipe_it_row_still_inconsistent():
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK"}])
    row = _row(tier="SNIPE_IT", audit=audit)   # no snipe_confirmed_seal marker
    assert "snipe_confirmed_seal" not in row
    assert audit_access.interpret(row)["label"] == "INCONSISTENT_SNIPE_CONFIRMED"


def test_legacy_seal_engine_still_flags_unsealed_tier():
    """The seal engine itself (not just interpret()) still produces the legacy
    label/diagnostic shape when it has just sealed a row down — i.e. a tr
    object freshly sealed THIS run is never confused with a legacy row that
    was never sealed at all."""
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK",
                                   "reason": "candle veto HOSTILE_WICK"}])
    tr = _tr(audit=audit)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert tr["snipe_confirmed_seal"]["applied"] is True


# ===========================================================================
# 4 — true under-promotion row still flagged
# ===========================================================================

def test_true_under_promotion_row_still_flagged_by_auditready():
    audit = _audit(audit_label="STARTER_ONLY_VALID", promotion_state="PROMOTION_READY")
    row = _row(tier="STARTER", audit=audit, capital_action="starter_only", channel="#starter-signals")
    assert "snipe_confirmed_seal" not in row
    assert audit_access.interpret(row)["label"] == "POSSIBLE_UNDER_PROMOTION"
    ok, why = audit_access.is_auditready_candidate(row)
    assert ok is True


# ===========================================================================
# 5 — clean SNIPE row still SNIPE_CONFIRMED
# ===========================================================================

def test_clean_snipe_row_still_snipe_confirmed():
    row = _row(tier="SNIPE_IT", audit=_audit())
    assert "snipe_confirmed_seal" not in row
    assert audit_access.interpret(row)["label"] == "SNIPE_CONFIRMED"


# ===========================================================================
# 6 — evidence preservation
# ===========================================================================

def test_evidence_preserved_through_seal_and_persistence():
    tr = _rl_tr()
    tr["final_signal"]["ticker"] = "RL"
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = record_alert("RL", tr, {"tickers": {}, "meta": {}},
                          {"state": {"max_memory_entries": 500}}, "scan_rl")
    row = state["tickers"]["RL"]["alert_history"][-1]
    sga = row["snipe_gate_audit"]
    assert sga["raw_snipe_score"] == 89
    assert sga["missing_proofs"] == [
        "ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS",
        "CANDLE_TRUTH_SUPPORTIVE: candle REJECTION indecision/forming",
    ]
    assert sga["blocked_gate_names"] == []
    assert sga["blocked_gates"] == []
    assert sga["score_blocked_by"] == []
    assert sga["promotion_triggers"] == []


# ===========================================================================
# No new promotion path / no SNIPE loosening
# ===========================================================================

def test_seal_never_promotes_and_never_grants_full_capital():
    for tr in (_rl_tr(), _live_edge_blocked_tr()):
        seal.seal_snipe_confirmed_consistency(tr, {})
        assert tr["final_tier"] != "SNIPE_IT"
        assert tr["capital_action"] not in seal._FULL_SNIPE_CAPITAL
        assert "snipe" not in str(tr["final_discord_channel"]).lower()

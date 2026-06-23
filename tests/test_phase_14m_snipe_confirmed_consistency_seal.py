"""Phase 14M — SNIPE_CONFIRMED consistency seal tests.

The scanner may not emit SNIPE_IT / FULL QUALITY / full_quality_allowed / #snipe
routing while its own evidence still contains an active SNIPE blocker. The seal
only ever downgrades a false SNIPE (using existing tier rules), preserves every
piece of raw evidence, and never hides the contradiction.

Live evidence that triggered this phase: FORM scan_20260623_153028_8d6c74 —
SNIPE_IT + full_quality_allowed while LIVE_EDGE_SAFE was blocked, 1H trigger was
RETEST_IN_PROGRESS, candle truth was unresolved/hostile wick, and 4H location
was repairing.
"""

import json

from src import audit_access
from src import discord_alerts
from src import snipe_confirmed_seal as seal
from src import snipe_gate_audit as sga
from src import state_store
from src.state_store import make_dedup_key, record_alert


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _audit(**over):
    """A clean SNIPE_CONFIRMED audit snapshot (no blockers) by default."""
    a = {
        "audit_label": "SNIPE_CONFIRMED",
        "promotion_state": "ALREADY_SNIPE",
        "snipe_score": 92,
        "raw_snipe_score": 92,
        "effective_snipe_score": 92,
        "score_blocked_by": [],
        "display_score_label": None,
        "snipe_grade": "A",
        "eligible_for_snipe_review": True,
        "blocked_gate_names": [],
        "blocked_gates": [],
        "missing_proofs": [],
        "promotion_triggers": ["avoid body close below invalidation 138.0"],
        "blocking_reasons": [],
        "diagnostic_sentence": "SNIPE audit: all critical gates confirm; setup is already SNIPE_IT.",
    }
    a.update(over)
    return a


def _signal(**over):
    s = {
        "ticker": "FORM", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals",
        "reason": "SNIPE_IT conditions met. FULL QUALITY — capital authorized after live-chart verification.",
        "next_action": "Enter full size now; capital authorized.",
        "retest_status": "confirmed", "hold_status": "confirmed",
        "structure_event": "bos", "trigger_level": 141.84, "invalidation_level": 138.0,
        "invalidation_condition": "1H close below 138", "risk_reward": 3.2,
        "overhead_status": "clear", "scan_price": 142.0, "targets": [145, 150],
        "missing_conditions": [],
    }
    s.update(over)
    return s


def _tr(audit=None, signal=None, final_tier="SNIPE_IT", capital="full_quality_allowed",
        channel="#snipe-signals", oh=None, htf=None):
    sig = signal if signal is not None else _signal()
    # Keep the nested final_signal internally consistent with the requested
    # tier/capital/channel — exactly as tiering.run produces it.
    sig = dict(sig)
    sig.setdefault("tier", final_tier)
    sig["tier"] = final_tier
    sig["capital_action"] = capital
    sig["discord_channel"] = channel
    tr = {
        "final_tier": final_tier, "capital_action": capital,
        "final_discord_channel": channel, "safe_for_alert": True, "score": 88,
        "final_signal": sig,
        "snipe_gate_audit": audit if audit is not None else _audit(),
        "higher_timeframe_context": htf if htf is not None else {"blocks_snipe_contextually": False},
    }
    if oh is not None:
        tr["one_hour_entry"] = oh
    return tr


def _row(tier="SNIPE_IT", audit=None, htf=None, retest="confirmed", hold="confirmed"):
    """A persisted alert_history-style row (no one_hour_entry persisted)."""
    return {
        "ticker": "FORM", "tier": tier, "scan_id": "scan_20260623_153028_8d6c74",
        "alerted_at": "2026-06-23T15:30:28", "retest_status": retest,
        "hold_status": hold, "capital_action": "full_quality_allowed",
        "score": 88, "final_discord_channel": "snipe",
        "snipe_gate_audit": audit if audit is not None else _audit(),
        "higher_timeframe_context": htf if htf is not None else {},
    }


# ===========================================================================
# 1 — clean SNIPE_IT stays SNIPE_CONFIRMED (the seal must not over-fire)
# ===========================================================================

def test_clean_snipe_stays_confirmed():
    tr = _tr()
    blocked, reasons = seal.has_active_snipe_confirmation_blocker(tr)
    assert blocked is False
    assert reasons == []
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    assert tr["snipe_confirmed_seal"]["applied"] is False


def test_clean_snipe_interprets_as_snipe_confirmed():
    assert audit_access.interpret(_row())["label"] == "SNIPE_CONFIRMED"


# ===========================================================================
# 2 — blocked_gate_names LIVE_EDGE_SAFE → INCONSISTENT
# ===========================================================================

def test_blocked_gate_downgrades_and_interprets_inconsistent():
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK",
                                   "reason": "candle veto HOSTILE_WICK"}])
    tr = _tr(audit=audit)
    blocked, reasons = seal.has_active_snipe_confirmation_blocker(tr)
    assert blocked is True
    assert any("LIVE_EDGE_SAFE" in r for r in reasons)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["snipe_confirmed_seal"]["seal_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    # interpret() on the equivalent persisted row (still tier SNIPE_IT):
    assert audit_access.interpret(_row(audit=audit))["label"] == "INCONSISTENT_SNIPE_CONFIRMED"


# ===========================================================================
# 3 — missing_proofs ONE_H_TRIGGER_CONFIRMED → INCONSISTENT
# ===========================================================================

def test_missing_proofs_downgrades():
    audit = _audit(missing_proofs=["ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS"])
    tr = _tr(audit=audit)
    assert seal.has_active_snipe_confirmation_blocker(tr)[0] is True
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] != "SNIPE_IT"
    assert audit_access.interpret(_row(audit=audit))["label"] == "INCONSISTENT_SNIPE_CONFIRMED"


# ===========================================================================
# 4 — score_blocked_by LIVE_EDGE_SAFE → INCONSISTENT
# ===========================================================================

def test_score_blocked_by_downgrades():
    audit = _audit(score_blocked_by=["LIVE_EDGE_SAFE"], raw_snipe_score=84,
                   effective_snipe_score=79, snipe_score=79)
    tr = _tr(audit=audit)
    assert seal.has_active_snipe_confirmation_blocker(tr)[0] is True
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] != "SNIPE_IT"
    assert audit_access.interpret(_row(audit=audit))["label"] == "INCONSISTENT_SNIPE_CONFIRMED"


# ===========================================================================
# 5 — candle unresolved → INCONSISTENT
# ===========================================================================

def test_candle_unresolved_downgrades():
    oh = {"trigger_state": "TRIGGER_LIVE",
          "candle_truth": {"event_type": "INDECISION", "closed_candle_confirms": False}}
    tr = _tr(oh=oh)
    blocked, reasons = seal.has_active_snipe_confirmation_blocker(tr)
    assert blocked is True
    assert any("candle" in r.lower() for r in reasons)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] != "SNIPE_IT"


# ===========================================================================
# 6 — HOSTILE_WICK blocking reason → INCONSISTENT
# ===========================================================================

def test_hostile_wick_text_downgrades():
    audit = _audit(blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"])
    tr = _tr(audit=audit)
    blocked, reasons = seal.has_active_snipe_confirmation_blocker(tr)
    assert blocked is True
    assert any("hostile wick" in r.lower() or "candle veto" in r.lower() for r in reasons)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] != "SNIPE_IT"


# ===========================================================================
# 7 — trigger_state RETEST_IN_PROGRESS cannot keep full_quality_allowed
# ===========================================================================

def test_retest_in_progress_drops_full_quality():
    oh = {"trigger_state": "RETEST_IN_PROGRESS",
          "pullback_retest_hold": {"hold_truth": "HOLD_CONFIRMED"},
          "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True}}
    tr = _tr(oh=oh)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["capital_action"] != "full_quality_allowed"
    assert tr["final_signal"]["capital_action"] != "full_quality_allowed"


# ===========================================================================
# 8 — hold_truth HOLD_WEAK cannot keep full_quality_allowed
# ===========================================================================

def test_hold_weak_drops_full_quality():
    oh = {"trigger_state": "TRIGGER_LIVE",
          "pullback_retest_hold": {"hold_truth": "HOLD_WEAK"},
          "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True}}
    tr = _tr(oh=oh)
    blocked, reasons = seal.has_active_snipe_confirmation_blocker(tr)
    assert blocked is True
    assert any("HOLD_WEAK" in r for r in reasons)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["capital_action"] != "full_quality_allowed"


# ===========================================================================
# 9 — alert_truth_label FORMING_TRIGGER cannot route to a snipe channel
# ===========================================================================

def test_forming_trigger_reroutes_off_snipe():
    oh = {"trigger_state": "TRIGGER_LIVE", "alert_truth_label": "FORMING_TRIGGER",
          "pullback_retest_hold": {"hold_truth": "HOLD_CONFIRMED"},
          "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True}}
    tr = _tr(oh=oh)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert "snipe" not in str(tr["final_discord_channel"]).lower()
    assert "snipe" not in str(tr["final_signal"]["discord_channel"]).lower()


# ===========================================================================
# 10 — FORM regression fixture (the full live contradiction)
# ===========================================================================

def _form_tr():
    audit = _audit(
        audit_label="SNIPE_CONFIRMED", promotion_state="ALREADY_SNIPE",
        snipe_score=79, raw_snipe_score=84, effective_snipe_score=79,
        score_blocked_by=["LIVE_EDGE_SAFE"],
        blocked_gate_names=["LIVE_EDGE_SAFE"],
        blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK", "reason": "candle veto HOSTILE_WICK"}],
        missing_proofs=[
            "FOUR_H_LOCATION_VALID: location LOCATION_REPAIRING",
            "ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS",
            "CANDLE_TRUTH_SUPPORTIVE: candle UNRESOLVED",
        ],
        blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"],
    )
    return _tr(audit=audit, htf={"data_status": "OK", "weekly_campaign_state": "HTF_CONTINUATION",
                                 "campaign_location_label": "EXTENDED_ABOVE_VALUE",
                                 "context_grade": "C", "context_score": 60,
                                 "weakens_long_setup": True, "blocks_snipe_contextually": False})


def test_form_regression_full():
    tr = _form_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    # Not a clean SNIPE_CONFIRMED any more.
    assert tr["final_tier"] != "SNIPE_IT"
    # No full size.
    assert tr["capital_action"] != "full_quality_allowed"
    assert tr["final_signal"]["capital_action"] != "full_quality_allowed"
    # No snipe routing.
    assert "snipe" not in str(tr["final_discord_channel"]).lower()
    # Diagnostic explains the contradiction.
    assert "SNIPE confirmation blocked" in tr["snipe_confirmed_seal"]["diagnostic"]
    assert tr["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert tr["snipe_gate_audit"]["promotion_state"] != "ALREADY_SNIPE"
    assert tr["snipe_confirmed_seal"]["sealed_tier"] == tr["final_tier"]
    assert tr["snipe_confirmed_seal"]["sealed_by_phase"] == "14M"
    # Raw evidence preserved.
    assert tr["snipe_gate_audit"]["raw_snipe_score"] == 84
    assert tr["snipe_gate_audit"]["blocked_gate_names"] == ["LIVE_EDGE_SAFE"]
    assert tr["snipe_gate_audit"]["missing_proofs"]  # still present
    assert tr["snipe_gate_audit"]["score_blocked_by"] == ["LIVE_EDGE_SAFE"]


def test_form_persisted_row_interprets_inconsistent():
    audit = _form_tr()["snipe_gate_audit"]
    assert audit_access.interpret(_row(audit=audit))["label"] == "INCONSISTENT_SNIPE_CONFIRMED"


# ===========================================================================
# 11 / 12 — rendered alert wording regression
# ===========================================================================

def test_rendered_alert_drops_full_quality_wording():
    tr = _form_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    body = discord_alerts.format_alert(tr)
    low = body.lower()
    assert "full quality" not in low
    assert "capital authorized" not in low
    assert "snipe_it conditions met" not in low


def test_rendered_alert_includes_proof_wait_wording():
    tr = _form_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    body = discord_alerts.format_alert(tr).lower()
    assert ("no capital" in body or "no fresh" in body or "watch" in body
            or "blocker" in body or "missing proof" in body)


# ===========================================================================
# 13 — repeated alert / dedup uses the corrected tier (no SNIPE resend)
# ===========================================================================

def test_dedup_key_and_record_use_corrected_tier():
    tr = _form_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    # Make the signal record_alert-friendly.
    tr["final_signal"].update({"ticker": "FORM", "missing_conditions": []})
    key = make_dedup_key("FORM", tr["final_tier"], tr["final_signal"].get("trigger_level"),
                         tr["final_signal"].get("invalidation_level"))
    assert "SNIPE_IT" not in key
    state = {"tickers": {}, "meta": {}}
    state = record_alert("FORM", tr, state, {"state": {"max_memory_entries": 500}}, "scan_form")
    row = state["tickers"]["FORM"]["alert_history"][-1]
    assert row["tier"] != "SNIPE_IT"
    assert row["capital_action"] != "full_quality_allowed"
    # Raw audit evidence still persisted.
    assert row["snipe_gate_audit"]["blocked_gate_names"] == ["LIVE_EDGE_SAFE"]
    assert row["snipe_gate_audit"]["raw_snipe_score"] == 84


# ===========================================================================
# 14 / 15 — non-SNIPE outputs are never touched (no promotion, no side effects)
# ===========================================================================

def test_starter_with_blockers_untouched():
    audit = _audit(audit_label="STARTER_ONLY_VALID", promotion_state="PROMOTION_PENDING",
                   blocked_gate_names=["LIVE_EDGE_SAFE"], blocked_gates=["LIVE_EDGE_SAFE"])
    tr = _tr(audit=audit, final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    assert "snipe_confirmed_seal" not in tr  # seal did not engage


def test_near_entry_with_incomplete_proof_untouched():
    audit = _audit(audit_label="NEAR_ENTRY_PENDING", promotion_state="PROMOTION_PENDING",
                   missing_proofs=["ONE_H_TRIGGER_CONFIRMED: forming"])
    tr = _tr(audit=audit, final_tier="NEAR_ENTRY", capital="wait_no_capital",
             channel="#near-entry-watch")
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert "snipe_confirmed_seal" not in tr


# ===========================================================================
# 16 / 17 / 18 — prior-phase audit interpretation still intact
# ===========================================================================

def test_14j_clean_starter_still_correct_starter():
    row = {
        "ticker": "AAA", "tier": "STARTER", "retest_status": "confirmed",
        "hold_status": "confirmed",
        "snipe_gate_audit": _audit(audit_label="STARTER_ONLY_VALID",
                                   promotion_state="PROMOTION_PENDING"),
        "higher_timeframe_context": {},
    }
    assert audit_access.interpret(row)["label"] == "CORRECT_STARTER"


def test_14k_promotion_ready_with_blocker_still_inconsistent_audit_state():
    audit = _audit(promotion_state="PROMOTION_READY", blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=["LIVE_EDGE_SAFE"],
                   blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"])
    row = {"ticker": "AAA", "tier": "STARTER", "snipe_gate_audit": audit,
           "higher_timeframe_context": {}}
    assert audit_access.interpret(row)["label"] == "INCONSISTENT_AUDIT_STATE"


def test_14l_clean_under_promotion_still_possible():
    audit = _audit(audit_label="STARTER_ONLY_VALID", promotion_state="PROMOTION_READY")
    row = {"ticker": "AAA", "tier": "STARTER", "capital_action": "starter_only",
           "retest_status": "confirmed", "hold_status": "confirmed",
           "snipe_gate_audit": audit, "higher_timeframe_context": {}}
    ok, why = audit_access.is_auditready_candidate(row)
    assert ok is True
    assert audit_access.interpret(row)["label"] == "POSSIBLE_UNDER_PROMOTION"


# ===========================================================================
# Hard-failure path → WAIT (suppressed); forming path → NEAR_ENTRY (visible)
# ===========================================================================

def test_hard_failure_downgrades_to_wait():
    audit = _audit(audit_label="DISQUALIFIED", promotion_state="PROMOTION_BLOCKED",
                   blocked_gate_names=["ONE_H_TRIGGER_CONFIRMED"],
                   blocked_gates=[{"gate": "ONE_H_TRIGGER_CONFIRMED", "status": "BLOCK",
                                   "reason": "1H FAILED_RETEST"}],
                   blocking_reasons=["ONE_H_TRIGGER_CONFIRMED: failed retest"])
    tr = _tr(audit=audit)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "WAIT"
    assert tr["safe_for_alert"] is False
    assert tr["capital_action"] == "no_trade"


def test_forming_failure_downgrades_to_near_entry_visible():
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK",
                                   "reason": "candle veto HOSTILE_WICK"}])
    tr = _tr(audit=audit)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["safe_for_alert"] is True   # still visible, not hidden


# ===========================================================================
# Robustness: idempotent, never raises, preserves score, ignores junk
# ===========================================================================

def test_seal_is_idempotent():
    tr = _form_tr()
    seal.seal_snipe_confirmed_consistency(tr, {})
    first = tr["final_tier"]
    seal.seal_snipe_confirmed_consistency(tr, {})  # second pass: nothing to seal
    assert tr["final_tier"] == first
    assert tr["snipe_gate_audit"]["raw_snipe_score"] == 84


def test_seal_never_raises_on_junk():
    for junk in (None, {}, {"final_tier": "SNIPE_IT"}, {"final_tier": 5},
                 {"final_signal": "oops"}, {"snipe_gate_audit": "bad"}):
        seal.seal_snipe_confirmed_consistency(junk, {})  # must not raise


def test_detector_clean_on_empty_and_nonsnipe():
    assert seal.has_active_snipe_confirmation_blocker({}) == (False, [])
    assert seal.is_snipe_confirmation_output({"final_tier": "WAIT"}) is False


def test_promotion_trigger_is_not_a_blocker():
    # A promotion_trigger (guidance) must never count as a blocker.
    audit = _audit(promotion_triggers=["avoid body close below invalidation 138.0",
                                       "clear overhead before full-size"])
    tr = _tr(audit=audit)
    assert seal.has_active_snipe_confirmation_blocker(tr)[0] is False


# ===========================================================================
# End-to-end: seal → record_alert → !audit interpretation
# ===========================================================================

def test_end_to_end_seal_record_audit():
    tr = _form_tr()
    tr["final_signal"].update({"ticker": "FORM", "missing_conditions": []})
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = {"tickers": {}, "meta": {}}
    state = record_alert("FORM", tr, state, {"state": {"max_memory_entries": 500}}, "scan_form")
    row = state["tickers"]["FORM"]["alert_history"][-1]
    # The recorded row is no longer a clean SNIPE; audit_access exposes the truth.
    assert row["tier"] != "SNIPE_IT"
    assert row["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert row["snipe_gate_audit"]["promotion_state"] != "ALREADY_SNIPE"
    assert row["snipe_confirmed_seal"]["applied"] is True
    assert row["snipe_confirmed_seal"]["sealed_tier"] == row["tier"]
    # The compact snapshot must remain strictly JSON-safe.
    json.dumps(row, allow_nan=False)

"""Phase 14S.5 — SNIPE grade truth reconciliation.

SNIPE_IT is EXECUTION AUTHORIZATION, not a synonym for A+.

  SNIPER_A       — complete executable sequence, capital-ready, may carry
                   legitimate NON-BLOCKING soft caps.
  SNIPER_A_PLUS  — the pristine/best-in-class version of the same sequence.

Two defects are repaired here, both audit-truth only:

  1. The gate audit is built at Step 6.59, BEFORE the Phase 14S ladder may
     promote STARTER -> SNIPE_IT (6.592) and before the downgrade-only seal
     (6.595). A legitimate SNIPER_A could finish final_tier=SNIPE_IT while the
     stored audit still described the older STARTER state.
  2. The SNIPE_CONFIRMED diagnostic implied every SNIPE is pristine.

The seal remains sovereign on real false-SNIPE contradictions, the ladder
remains the upstream promotion authority, and NO scanner decision field is
touched by the reconciliation.
"""

import copy
import json

from src import audit_access
from src import discord_alerts
from src import snipe_confirmed_seal as seal
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as lad

# Existing audit-label enum — reconciliation may only ever choose from these.
_AUDIT_LABELS = {
    "SNIPE_CONFIRMED", "STARTER_ONLY_VALID", "NEAR_ENTRY_PENDING",
    "WATCH_ONLY_BLOCKED", "DISQUALIFIED", "INSUFFICIENT_CONTEXT",
    "INCONSISTENT_SNIPE_CONFIRMED", "SNIPE_CONFIRMATION_BLOCKED",
}


# ---------------------------------------------------------------------------
# Fixtures — arbitrary ticker; every ticker judged by the same formula
# ---------------------------------------------------------------------------

def _signal(**over):
    s = {
        "ticker": "LDR", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals", "reason": "SNIPE_IT conditions met.",
        "next_action": "Enter full size.", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 101.0, "targets": [110.0, 118.25],
        "missing_conditions": [], "risk_realism_state": "healthy",
        "upgrade_trigger": "none",
    }
    s.update(over)
    return s


def _oh(**over):
    o = {
        "status": "ENABLED", "trigger_state": "TRIGGER_LIVE",
        "alert_truth_label": "CONFIRMED_TRIGGER", "score": 92,
        "score_label": "STRONG_1H_TRIGGER", "data_freshness": "FRESH",
        "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID",
                                 "hold_truth": "HOLD_CONFIRMED"},
        "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "invalidation": {"clear": True},
    }
    o.update(over)
    return o


_TF_FULL = {
    "alignment_label": "FULL_STACK_ALIGNED", "status": "ENABLED",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_VALID"},
}
# Pristine HTF: nothing that produces a soft cap.
_HTF_PRISTINE = {
    "weekly_campaign_state": "HTF_CONTINUATION", "blocks_snipe_contextually": False,
    "monthly_bias": "BULLISH", "data_status": "OK",
}
# Legitimate NON-BLOCKING soft cap: extended above value, explicitly not blocking.
_HTF_SOFT_CAP = {
    "weekly_campaign_state": "HTF_CONTINUATION",
    "campaign_location_label": "EXTENDED_ABOVE_VALUE",
    "context_grade": "C", "weakens_long_setup": True,
    "blocks_snipe_contextually": False, "monthly_bias": "BULLISH", "data_status": "OK",
}


def _tr(sig=None, one=None, tf=_TF_FULL, htf=None, final_tier="SNIPE_IT",
        capital="full_quality_allowed", channel="#snipe-signals"):
    s = dict(sig if sig is not None else _signal())
    s["tier"] = final_tier
    s["capital_action"] = capital
    s["discord_channel"] = channel
    tr = {
        "final_tier": final_tier, "capital_action": capital,
        "final_discord_channel": channel, "safe_for_alert": True, "score": 92,
        "final_signal": s,
        "one_hour_entry": one if one is not None else _oh(),
        "timeframe_alignment": copy.deepcopy(tf),
        "higher_timeframe_context": copy.deepcopy(htf if htf is not None else _HTF_PRISTINE),
    }
    return tr


def _pipeline(tr):
    """Run the REAL production order: gate audit -> ladder arbitration -> seal
    -> Phase 14S.5 final audit reconciliation."""
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    lad.apply_ladder_arbitration(tr, {})
    seal.seal_snipe_confirmed_consistency(tr, {})
    sga_mod.reconcile_final_snipe_audit_state(tr)
    return tr


def _sniper_a_tr():
    """Complete sequence carrying a legitimate non-blocking soft cap."""
    return _tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                     "closed_candle_confirms": False},
                       location_realism={"label": "ACCEPTABLE_BUT_NOT_IDEAL"}),
               htf=_HTF_SOFT_CAP)


def _sniper_a_plus_tr():
    """Complete sequence with pristine supporting context."""
    return _tr()


# ===========================================================================
# 1 — SNIPER_A remains a legitimate SNIPE_IT
# ===========================================================================

def test_sniper_a_remains_legitimate_snipe_it():
    tr = _pipeline(_sniper_a_tr())
    ladder = tr["snipe_ladder"]
    assert ladder["internal_ladder_tier"] == "SNIPER_A"
    assert ladder["sniper_grade"] == "SNIPER_A"
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    assert tr["safe_for_alert"] is True
    assert tr["final_tier"] not in ("STARTER", "NEAR_ENTRY", "WAIT")
    # A legitimate soft cap must be disclosed, not treated as a capital blocker.
    assert ladder["soft_caps"]
    assert not ladder["hard_failures"]


# ===========================================================================
# 2 — SNIPER_A_PLUS remains the pristine SNIPE
# ===========================================================================

def test_sniper_a_plus_remains_pristine_snipe():
    tr = _pipeline(_sniper_a_plus_tr())
    ladder = tr["snipe_ladder"]
    assert ladder["internal_ladder_tier"] == "SNIPER_A_PLUS"
    assert ladder["sniper_grade"] == "SNIPER_A_PLUS"
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"


# ===========================================================================
# 3 — post-ladder audit parity (the core defect)
# ===========================================================================

def test_post_ladder_audit_parity_starter_promoted_to_snipe():
    """Pre-ladder tier is STARTER; Phase 14S classification is SNIPER_A.
    After ladder -> seal -> reconciliation the audit must describe SNIPE_IT."""
    tr = _sniper_a_tr()
    tr.update({"final_tier": "STARTER", "capital_action": "starter_only",
               "final_discord_channel": "#starter-signals"})
    tr["final_signal"]["tier"] = "STARTER"

    # Pre-ladder audit legitimately reflects the STARTER state.
    pre_audit = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    assert pre_audit["current_final_tier"] == "STARTER"

    tr = _pipeline(tr)
    audit = tr["snipe_gate_audit"]

    assert tr["final_tier"] == "SNIPE_IT"
    assert audit["current_final_tier"] == "SNIPE_IT"
    assert audit["current_capital_action"] == "full_quality_allowed"
    assert audit["audit_label"] == "SNIPE_CONFIRMED"
    assert audit["promotion_state"] == "ALREADY_SNIPE"
    assert "SNIPER_A" in audit["diagnostic_sentence"]
    assert "SNIPER_A_PLUS" not in audit["diagnostic_sentence"]
    # SNIPER_A must never be described as incomplete or as still needing A+.
    low = audit["diagnostic_sentence"].lower()
    assert "incomplete" not in low
    assert "a+" not in low


# ===========================================================================
# 4 — A+ diagnostic explicitly names SNIPER_A_PLUS
# ===========================================================================

def test_a_plus_diagnostic_names_sniper_a_plus():
    tr = _pipeline(_sniper_a_plus_tr())
    audit = tr["snipe_gate_audit"]
    assert audit["audit_label"] == "SNIPE_CONFIRMED"
    assert audit["promotion_state"] == "ALREADY_SNIPE"
    assert "SNIPER_A_PLUS" in audit["diagnostic_sentence"]
    assert "pristine" in audit["diagnostic_sentence"].lower()


# ===========================================================================
# 5 — seal downgrade sovereignty (reconciliation must NOT overwrite)
# ===========================================================================

def test_seal_downgrade_sovereignty_preserved():
    """A false SNIPE the SEAL catches: the seal owns the contradiction verdict
    and reconciliation must not overwrite it."""
    # Hostile live-edge veto — the classic Phase 14M seal trigger.
    tr = _tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                   "closed_candle_confirms": False}))
    tr["candle_evidence"] = {"status": "ok", "candle_family": "RETEST_HOLD",
                             "next_candle_verdict": "UNKNOWN",
                             "candle_veto": "HOSTILE_WICK", "level_reaction": "HELD"}
    tr = _pipeline(tr)
    audit = tr["snipe_gate_audit"]
    seal_marker = tr.get("snipe_confirmed_seal") or {}

    assert seal_marker.get("applied") is True, "fixture must exercise the seal path"
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"
    # Seal verdict preserved — never rewritten to SNIPE_CONFIRMED/ALREADY_SNIPE.
    assert audit["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert audit["promotion_state"] != "ALREADY_SNIPE"
    marker = audit["final_audit_reconciliation"]
    assert marker["applied"] is False
    assert marker["seal_authoritative"] is True
    # current_* mirrors still resynchronized to the truthful final state.
    assert audit["current_final_tier"] == tr["final_tier"]
    assert audit["current_capital_action"] == tr["capital_action"]


def test_ladder_downgrade_does_not_leave_stale_snipe_confirmed():
    """Mirror-image contradiction: the LADDER (not the seal) downgrades a hard
    failure, leaving the 6.59 audit still claiming SNIPE_CONFIRMED/ALREADY_SNIPE.
    Both are defined as final_tier == SNIPE_IT, so on a non-SNIPE final tier they
    are provably stale and must never ship."""
    tr = _tr(sig=_signal(scan_price=95.0))  # accepted below invalidation 96.5

    pre = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    assert pre["audit_label"] == "SNIPE_CONFIRMED"  # legitimately built pre-ladder

    tr = _pipeline(tr)
    audit = tr["snipe_gate_audit"]
    assert (tr.get("snipe_confirmed_seal") or {}).get("applied") is not True, \
        "this case must be a LADDER downgrade, not a seal downgrade"
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] in ("no_trade", "wait_no_capital")
    # The stale SNIPE claim is corrected to an existing, truthful enum value.
    assert audit["audit_label"] != "SNIPE_CONFIRMED"
    assert audit["audit_label"] in _AUDIT_LABELS
    assert audit["promotion_state"] != "ALREADY_SNIPE"
    assert audit["current_final_tier"] == tr["final_tier"]


def test_sealed_row_keeps_seal_diagnostic_and_blockers():
    audit_in = {
        "enabled": True, "status": "ENABLED",
        "audit_label": "SNIPE_CONFIRMATION_BLOCKED",
        "promotion_state": "PROMOTION_BLOCKED",
        "diagnostic_sentence": "SNIPE confirmation blocked; blocked by: LIVE_EDGE_SAFE.",
        "blocked_gates": [{"gate": "LIVE_EDGE_SAFE"}],
        "blocking_reasons": ["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"],
        "missing_proofs": [], "current_final_tier": "SNIPE_IT",
        "current_capital_action": "full_quality_allowed",
    }
    tr = {
        "final_tier": "NEAR_ENTRY", "capital_action": "wait_no_capital",
        "snipe_gate_audit": audit_in,
        "snipe_confirmed_seal": {"applied": True, "sealed_tier": "NEAR_ENTRY"},
        "snipe_ladder": {"sniper_grade": "NONE"},
    }
    before_diag = audit_in["diagnostic_sentence"]
    before_blockers = copy.deepcopy(audit_in["blocked_gates"])
    sga_mod.reconcile_final_snipe_audit_state(tr)
    a = tr["snipe_gate_audit"]
    assert a["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert a["promotion_state"] == "PROMOTION_BLOCKED"
    assert a["diagnostic_sentence"] == before_diag
    assert a["blocked_gates"] == before_blockers
    assert a["blocking_reasons"] == ["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"]


# ===========================================================================
# 6 — evidence immutability across reconciliation
# ===========================================================================

_EVIDENCE_KEYS = (
    "passed_gates", "blocked_gates", "missing_proofs", "blocking_reasons",
    "promotion_triggers", "survival_conditions", "raw_snipe_score",
    "effective_snipe_score", "score_blocked_by", "snipe_score", "snipe_grade",
)


def test_evidence_immutable_across_reconciliation():
    tr = _sniper_a_tr()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    lad.apply_ladder_arbitration(tr, {})
    seal.seal_snipe_confirmed_consistency(tr, {})

    before = {k: copy.deepcopy(tr["snipe_gate_audit"].get(k)) for k in _EVIDENCE_KEYS}
    sga_mod.reconcile_final_snipe_audit_state(tr)
    after = {k: tr["snipe_gate_audit"].get(k) for k in _EVIDENCE_KEYS}

    for k in _EVIDENCE_KEYS:
        assert before[k] == after[k], f"evidence field mutated by reconciliation: {k}"


# ===========================================================================
# 7 — decision-field invariants across reconciliation
# ===========================================================================

_DECISION_KEYS = (
    "final_tier", "capital_action", "final_discord_channel", "safe_for_alert",
    "score", "snipe_ladder",
)


def test_decision_fields_unchanged_by_reconciliation():
    tr = _sniper_a_tr()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    lad.apply_ladder_arbitration(tr, {})
    seal.seal_snipe_confirmed_consistency(tr, {})

    before = {k: copy.deepcopy(tr.get(k)) for k in _DECISION_KEYS}
    sga_mod.reconcile_final_snipe_audit_state(tr)

    for k in _DECISION_KEYS:
        assert tr.get(k) == before[k], f"decision field mutated by reconciliation: {k}"


def test_reconciliation_never_raises_on_junk():
    for junk in (None, {}, [], {"snipe_gate_audit": "bad"},
                 {"snipe_gate_audit": {"enabled": False}},
                 {"final_tier": 5, "snipe_gate_audit": {}}):
        sga_mod.reconcile_final_snipe_audit_state(junk)


# ===========================================================================
# 8 / 9 — Discord lane display
# ===========================================================================

def test_discord_sniper_a_display():
    tr = _pipeline(_sniper_a_tr())
    body = discord_alerts.format_alert(tr)
    assert "SNIPE_IT" in body
    assert "Lane: SNIPER_ENTRY | SNIPER_A" in body
    # Must NOT claim the pristine grade it does not hold.
    assert "SNIPER_A_PLUS" not in body
    low = body.lower()
    assert "a+ sniper" not in low
    assert "pristine sniper" not in low


def test_discord_sniper_a_plus_display():
    tr = _pipeline(_sniper_a_plus_tr())
    body = discord_alerts.format_alert(tr)
    assert "Lane: SNIPER_ENTRY | SNIPER_A_PLUS" in body


# ===========================================================================
# 10 — human capital wording describes full-size authorization, not A+
# ===========================================================================

def test_human_capital_wording_is_full_size_authorization():
    tr = _pipeline(_sniper_a_tr())
    body = discord_alerts.format_alert(tr)
    assert "FULL-SIZE AUTHORIZED" in body
    # The old wording conflated capital authorization with A+ quality.
    assert "FULL QUALITY" not in body
    # The structured enum is a protected compatibility field — unchanged.
    assert tr["capital_action"] == "full_quality_allowed"
    assert discord_alerts.CAPITAL_CONTRACT["SNIPE_IT"]["capital_state"] == "capital_authorized"


def test_capital_action_enum_unchanged():
    assert discord_alerts._CAPITAL_LABEL["full_quality_allowed"] == "FULL-SIZE AUTHORIZED"
    assert "full_quality_allowed" in discord_alerts._CAPITAL_LABEL
    assert "capital authorized" in discord_alerts.CAPITAL_CONTRACT["SNIPE_IT"]["sizing"]


def test_full_size_authorized_never_leaks_into_lower_tiers():
    """The new SNIPE sizing phrase must be stripped from STARTER / NEAR_ENTRY."""
    for tier, capital, channel in (("STARTER", "starter_only", "#starter-signals"),
                                   ("NEAR_ENTRY", "wait_no_capital", "#near-entry-watch")):
        sig = _signal(tier=tier, capital_action=capital, discord_channel=channel,
                      reason="FULL-SIZE AUTHORIZED — capital authorized after live-chart verification.",
                      next_action="Enter full size now.")
        tr = _tr(sig=sig, final_tier=tier, capital=capital, channel=channel)
        body = discord_alerts.format_alert(tr)
        assert "FULL-SIZE AUTHORIZED" not in body, f"{tier} leaked the SNIPE sizing phrase"


# ===========================================================================
# 11 — audit channel naming separates gate score from sniper grade
# ===========================================================================

def test_audit_naming_separates_gate_audit_grade_from_sniper_grade():
    tr = _pipeline(_sniper_a_tr())
    row = dict(tr)
    row["tier"] = tr["final_tier"]
    text = audit_access.format_row(row)
    assert "Gate-audit score:" in text
    assert "Gate-audit grade:" in text
    assert "Sniper grade:" in text
    # The ambiguous old labels are gone from the human render.
    assert "SNIPE grade:" not in text
    assert "SNIPE score:" not in text
    # Underlying schema keys are unchanged.
    assert "snipe_grade" in tr["snipe_gate_audit"]
    assert "snipe_score" in tr["snipe_gate_audit"]


def test_audit_json_schema_keys_unchanged():
    tr = _pipeline(_sniper_a_tr())
    audit = tr["snipe_gate_audit"]
    for key in ("snipe_score", "snipe_grade", "audit_label", "promotion_state",
                "current_final_tier", "current_capital_action"):
        assert key in audit
    json.dumps(audit, allow_nan=False, default=str)


# ===========================================================================
# 12 — acceptance matrix / existing fear regressions still hold
# ===========================================================================

def test_alive_base_incomplete_full_size_proof_stays_starter():
    tr = _tr(one=_oh(trigger_state="RETEST_IN_PROGRESS", alert_truth_label="WATCH_ONLY",
                     pullback_retest_hold={"retest_truth": "RETEST_CORE_VALID",
                                           "hold_truth": "HOLD_WEAK"},
                     candle_truth={"event_type": "NONE", "closed_candle_confirms": False}),
             final_tier="NEAR_ENTRY", capital="wait_no_capital",
             channel="#near-entry-watch")
    tr = _pipeline(tr)
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    assert tr["snipe_gate_audit"]["current_final_tier"] == "STARTER"


def test_missing_invalidation_blocks_capital():
    tr = _tr(sig=_signal(invalidation_level=None, invalidation_condition=""),
             one=_oh(invalidation={"clear": False}))
    tr = _pipeline(tr)
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"


def test_defensive_rejection_does_not_bury_valid_snipe():
    tr = _pipeline(_sniper_a_tr())
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["snipe_ladder"]["candle_state"] in ("DEFENSIVE", "NO_REJECTION")


def test_no_a_minus_sniper_rung_introduced():
    """A- is explicitly out of scope for this reconciliation patch."""
    assert not hasattr(lad, "SNIPER_A_MINUS")
    assert "SNIPER_A_MINUS" not in lad.LADDER_TIERS
    tr = _pipeline(_sniper_a_tr())
    assert tr["snipe_ladder"]["sniper_grade"] in ("NONE", "SNIPER_A", "SNIPER_A_PLUS")

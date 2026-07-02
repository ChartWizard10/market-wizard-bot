"""Phase 14Q — conditional seal floor, leader-continuation context, and the
normalized candle-context reconciliation.

Final law under test:
  * A rejection candle is not automatically a blocker.
  * A defensive rejection can preserve SNIPE_IT.
  * A hostile rejection blocks capital (NEAR_ENTRY / wait_no_capital).
  * An unresolved rejection with a confirmed base sequence floors to STARTER.
  * An expansion/add rejection means add proof failed, not base retest failed.
  * Weak-1H / WATCH_ONLY remains NEAR_ENTRY under Phase 14M.1.
  * Leader context softens non-fatal context only; it never overrides failure.
  * The seal is downgrade-only and never promotes NEAR_ENTRY upward.
  * No hidden blockers; no vague "unresolved proof remains" language.

No ticker is whitelisted — every fixture is an arbitrary ticker judged by the
same Structure -> Liquidity -> Displacement -> Retest -> Hold -> Invalidation ->
Target formula.
"""

import json

from src import audit_access
from src import discord_alerts
from src import snipe_blocker_taxonomy as tax
from src import snipe_confirmed_seal as seal
from src import snipe_gate_audit as sga_mod
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Fixtures (arbitrary ticker "LDR" — leaders get context, never special-casing)
# ---------------------------------------------------------------------------

def _audit(**over):
    a = {
        "audit_label": "SNIPE_CONFIRMED", "promotion_state": "ALREADY_SNIPE",
        "snipe_score": 100, "raw_snipe_score": 100, "effective_snipe_score": 100,
        "score_blocked_by": [], "display_score_label": None, "snipe_grade": "A",
        "eligible_for_snipe_review": True, "blocked_gate_names": [], "blocked_gates": [],
        "missing_proofs": [], "promotion_triggers": [], "blocking_reasons": [],
        "diagnostic_sentence": "SNIPE audit: all critical gates confirm; setup is already SNIPE_IT.",
    }
    a.update(over)
    return a


def _oh(trigger="HOLD_CONFIRMED", retest="RETEST_CORE_VALID", hold="HOLD_CONFIRMED",
        alert="CONFIRMED_TRIGGER", candle="REJECTION", closed=False,
        loc="ACCEPTABLE_BUT_NOT_IDEAL", path="CLEAN"):
    return {
        "status": "ENABLED", "trigger_state": trigger, "alert_truth_label": alert,
        "score": 92, "score_label": "STRONG_1H_TRIGGER",
        "pullback_retest_hold": {"retest_truth": retest, "hold_truth": hold},
        "candle_truth": {"event_type": candle, "closed_candle_confirms": closed},
        "location_realism": {"label": loc},
        "path_quality": {"path_label": path, "overhead_clear_enough": True},
        "invalidation": {"clear": True},
    }


_TF_OK = {
    "alignment_label": "FULL_STACK_ALIGNED",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_VALID"},
}

# Leader/continuation sponsorship: HTF extended above value but NOT contextually
# blocking (the WDC-shaped healthy-pullback context).
_HTF_LEADER = {
    "weekly_campaign_state": "HTF_CONTINUATION",
    "campaign_location_label": "EXTENDED_ABOVE_VALUE",
    "context_grade": "C", "context_score": 60,
    "weakens_long_setup": True, "blocks_snipe_contextually": False,
    "monthly_bias": "UNKNOWN", "data_status": "OK",
}


def _signal(**over):
    s = {
        "ticker": "LDR", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals", "reason": "SNIPE_IT conditions met.",
        "next_action": "Enter full size now.", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 605.90, "invalidation_level": 572.29,
        "invalidation_condition": "1H close below 572.29", "risk_reward": 3.2,
        "overhead_status": "clear", "scan_price": 606.0, "targets": [640, 700],
        "missing_conditions": [],
    }
    s.update(over)
    return s


def _tr(audit=None, oh=None, tf=None, htf=None, signal=None, final_tier="SNIPE_IT",
        capital="full_quality_allowed", channel="#snipe-signals"):
    sig = dict(signal if signal is not None else _signal())
    sig["tier"] = final_tier
    sig["capital_action"] = capital
    sig["discord_channel"] = channel
    tr = {
        "final_tier": final_tier, "capital_action": capital, "final_discord_channel": channel,
        "safe_for_alert": True, "score": 92, "final_signal": sig,
        "snipe_gate_audit": audit if audit is not None else _audit(),
        "higher_timeframe_context": dict(htf if htf is not None else _HTF_LEADER),
    }
    if oh is not None:
        tr["one_hour_entry"] = oh
    if tf is not None:
        tr["timeframe_alignment"] = tf
    return tr


def _all_codes(c) -> list:
    out = []
    for key in ("capital_blockers", "snipe_only_blockers", "soft_caps", "info_notes"):
        out.extend(b.get("code") for b in c.get(key, []) if isinstance(b, dict))
    return out


# ===========================================================================
# A — defensive rejection + complete sequence preserves SNIPE_IT
# ===========================================================================

def test_defensive_rejection_complete_sequence_preserves_snipe():
    tr = _tr(oh=_oh(), tf=_TF_OK)  # REJECTION, closed=False, but full defensive proof
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    assert tr["final_discord_channel"] == "#snipe-signals"
    assert tr["snipe_confirmed_seal"]["applied"] is False
    recon = tr["snipe_promotion_reconciliation"]
    cc = recon["candle_context"]
    assert cc["candle_context"] == "DEFENSIVE_REJECTION"
    assert cc["candle_context_scope"] == "BASE_ENTRY_ZONE"
    assert cc["candle_tier_effect"] in ("SOFT_CAP", "INFO_NOTE")
    assert not recon["capital_blockers"]
    assert not recon["snipe_only_blockers"]
    # Audit ledger not rewritten (seal declined to act).
    assert tr["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMED"


# ===========================================================================
# B — unresolved rejection + confirmed base floors to STARTER
# ===========================================================================

def test_unresolved_rejection_complete_base_sequence_floors_to_starter():
    # Base confirmed via 1H truth, but no TF proof -> defensive not provable.
    tr = _tr(oh=_oh())
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    assert tr["final_discord_channel"] == "#starter-signals"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["candle_context"]["candle_context"] == "UNRESOLVED_REJECTION"
    assert recon["base_sequence_confirmed"] is True
    named = recon["named_blockers"]
    assert any("CANDLE_CONTEXT_UNRESOLVED" in n for n in named)
    # Diagnostic names the exact proof — never the vague legacy phrase.
    diag = tr["snipe_confirmed_seal"]["diagnostic"]
    assert "SNIPE confirmation blocked" in diag
    assert "unresolved proof remains" not in diag
    assert "CANDLE_CONTEXT_UNRESOLVED" in diag


# ===========================================================================
# C — hostile rejection / weak 1H preserves Phase 14M.1 NEAR_ENTRY
# ===========================================================================

def test_hostile_rejection_weak_1h_preserves_14m1_near_entry():
    tr = _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY"))
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert tr["final_discord_channel"] == "#near-entry-watch"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["candle_context"]["candle_context"] == "HOSTILE_REJECTION"
    assert recon["capital_blockers"], "exact CAPITAL blocker must be printed"
    assert "unresolved proof remains" not in tr["snipe_confirmed_seal"]["diagnostic"]


def test_rl_missing_proof_shape_stays_near_entry():
    # The exact 14M.1 _rl_tr audit shape (missing ONE_H_TRIGGER_CONFIRMED).
    audit = _audit(missing_proofs=[
        "ONE_H_TRIGGER_CONFIRMED: 1H RETEST_IN_PROGRESS",
        "CANDLE_TRUTH_SUPPORTIVE: candle REJECTION indecision/forming",
    ])
    tr = _tr(audit=audit)  # no one_hour_entry object at all
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"


# ===========================================================================
# D / J — expansion rejection never claims the base entry retest failed
# ===========================================================================

def test_expansion_rejection_does_not_claim_entry_retest_failed():
    # Base entry-zone retest/hold confirmed; FAILED_BREAK belongs to the add level.
    tr = _tr(oh=_oh(closed=True), tf=_TF_OK)
    tr["candle_evidence"] = {"candle_family": "FAILED_BREAK"}
    c = tax.classify_blockers(tr)
    cc = c["candle_context"]
    assert cc["candle_context"] == "EXPANSION_REJECTION"
    assert cc["candle_context_scope"] == "EXPANSION_ADD_LEVEL"
    reason = cc["candle_context_reason"].lower()
    assert "expansion/add trigger failed" in reason
    assert "entry-zone retest failed" not in reason
    assert cc["candle_tier_effect"] in ("SOFT_CAP", "SNIPE_ONLY_BLOCKER")
    assert cc["candle_tier_effect"] != "CAPITAL_BLOCKER"


def test_expansion_rejection_alone_never_forces_near_entry():
    tr = _tr(oh=_oh(closed=True), tf=_TF_OK)
    tr["candle_evidence"] = {"candle_family": "FAILED_BREAK"}
    seal.seal_snipe_confirmed_consistency(tr, {})
    # Expansion failure is an add blocker, not a base blocker.
    assert tr["final_tier"] != "NEAR_ENTRY"


def test_hostile_scope_when_base_not_held():
    # Same FAILED_BREAK but the base hold itself is weak -> entry-zone failure.
    tr = _tr(oh=_oh(hold="HOLD_WEAK", alert="WATCH_ONLY"))
    tr["candle_evidence"] = {"candle_family": "FAILED_BREAK"}
    c = tax.classify_blockers(tr)
    cc = c["candle_context"]
    assert cc["candle_context"] == "HOSTILE_REJECTION"
    assert cc["candle_context_scope"] == "BASE_ENTRY_ZONE"
    assert cc["candle_tier_effect"] == "CAPITAL_BLOCKER"


# ===========================================================================
# E — one candle classification; no duplicate codes across classes
# ===========================================================================

def test_no_duplicate_candle_blockers():
    for tr in (
        _tr(oh=_oh(), tf=_TF_OK),                                             # defensive
        _tr(oh=_oh()),                                                        # unresolved
        _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY")),  # hostile
        _tr(oh=_oh(closed=True), tf=_TF_OK),                                  # no rejection... expansion via ce below
    ):
        c = tax.classify_blockers(tr)
        codes = _all_codes(c)
        assert len(codes) == len(set(codes)), f"duplicate blocker codes: {codes}"
        candle_codes = [x for x in codes if isinstance(x, str) and x.startswith("CANDLE_")]
        assert len(candle_codes) <= 1, f"one candle -> one classification, got {candle_codes}"


# ===========================================================================
# F — arbitrary-ticker leader complete sequence: soft caps only -> SNIPE_IT
# ===========================================================================

def test_leader_complete_sequence_soft_caps_only_stays_snipe():
    tr = _tr(oh=_oh(candle="DISPLACEMENT", closed=True), tf=_TF_OK)
    c = tax.classify_blockers(tr)
    assert c["leader_context"] == "LEADER_CONTINUATION_CONTEXT"
    assert c["leader_effect"] == "SOFT_CAP_RELIEF"
    assert c["recommended_floor"] == "SNIPE_IT"
    soft_codes = {b["code"] for b in c["soft_caps"]}
    assert "HTF_EXTENDED" in soft_codes        # extended-above-value: soft only
    assert "LOCATION_REALISM" in soft_codes    # acceptable-but-not-ideal: soft only
    assert any(b["code"] == "MONTHLY_BIAS_UNKNOWN" for b in c["info_notes"])
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["snipe_gate_audit"]["promotion_state"] != "PROMOTION_BLOCKED"
    assert tr["snipe_gate_audit"]["audit_label"] != "SNIPE_CONFIRMATION_BLOCKED"


# ===========================================================================
# G — leader context cannot override weak 1H / hard failure
# ===========================================================================

def test_leader_weak_1h_stays_blocked():
    tr = _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY"),
             tf=_TF_OK)
    c = tax.classify_blockers(tr)
    assert c["leader_context"] == "LEADER_CONTINUATION_CONTEXT"
    assert c["leader_effect"] == "HARD_FAILURE_OVERRIDES"
    assert c["capital_blockers"]
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"


# ===========================================================================
# H — GS newest STARTER wording (weak/forming 1H)
# ===========================================================================

def test_gs_newest_starter_wording_no_conditions_met():
    tr = _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY"),
             final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    body = discord_alerts.format_alert(tr)
    low = body.lower()
    assert "starter conditions met" not in low
    assert "entry valid now" not in low
    assert "no fresh aggression" in low
    assert "thesis valid" in low


# ===========================================================================
# I — GS older STARTER: confirmed base, candle-limited
# ===========================================================================

def test_gs_older_starter_candle_limited():
    tr = _tr(oh=_oh(trigger="TRIGGER_LIVE", candle="NONE", closed=False),
             tf=_TF_OK if False else None,
             final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    c = tax.classify_blockers(tr)
    assert c["base_sequence_confirmed"] is True
    assert c["recommended_floor"] == "STARTER"  # not NEAR_ENTRY — base is earned
    assert c["candle_context"]["candle_context"] in ("UNRESOLVED_REJECTION", "UNKNOWN")
    named = tax.named_blockers(c)
    assert named and any("CANDLE" in n for n in named)


# ===========================================================================
# K — MRCY weak hold cannot sound clean and is not SNIPE
# ===========================================================================

def test_mrcy_weak_hold_not_snipe_and_not_clean_wording():
    tr = _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY"),
             final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    c = tax.classify_blockers(tr)
    assert c["recommended_floor"] != "SNIPE_IT"
    assert c["capital_blockers"]
    body = discord_alerts.format_alert(tr).lower()
    assert "high-quality starter" not in body
    assert "clean starter" not in body


# ===========================================================================
# L — survival condition is not a promotion trigger
# ===========================================================================

def test_survival_condition_not_a_promotion_trigger():
    tr = _tr(signal=_signal(retest_status="partial", hold_status="partial"),
             final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    audit = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    promo = " ".join(audit["promotion_triggers"]).lower()
    surv = " ".join(audit["survival_conditions"]).lower()
    assert "avoid body close" not in promo
    assert "avoid body close" in surv


# ===========================================================================
# Seal discipline: downgrade-only; NEAR_ENTRY never promoted; no blank blocks
# ===========================================================================

def test_seal_never_promotes_near_entry_upward():
    audit = _audit(audit_label="NEAR_ENTRY_PENDING", promotion_state="PROMOTION_PENDING")
    tr = _tr(audit=audit, oh=_oh(), tf=_TF_OK, final_tier="NEAR_ENTRY",
             capital="wait_no_capital", channel="#near-entry-watch")
    seal.seal_snipe_confirmed_consistency(tr, {})
    # Not SNIPE-shaped: the seal never engages, never promotes.
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert "snipe_confirmed_seal" not in tr


def test_sealed_row_never_promotion_blocked_with_blank_blockers():
    tr = _tr(oh=_oh())  # unresolved -> STARTER
    seal.seal_snipe_confirmed_consistency(tr, {})
    sgao = tr["snipe_gate_audit"]
    if sgao["promotion_state"] == "PROMOTION_BLOCKED":
        recon = tr["snipe_promotion_reconciliation"]
        assert recon["capital_blockers"] or recon["snipe_only_blockers"]
        assert recon["named_blockers"]
        assert recon["hidden_blocker_violation"] is False


def test_taxonomy_flags_hidden_blocker_violation_when_truly_blank():
    row = {
        "tier": "NEAR_ENTRY",
        "snipe_gate_audit": _audit(audit_label="SNIPE_CONFIRMATION_BLOCKED",
                                   promotion_state="PROMOTION_BLOCKED"),
    }
    c = tax.classify_blockers(row)
    assert c["hidden_blocker_violation"] is True


def test_diagnostic_is_never_vague():
    audit = _audit(blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=[{"gate": "LIVE_EDGE_SAFE", "status": "BLOCK",
                                   "reason": "candle veto HOSTILE_WICK"}])
    tr = _tr(audit=audit)
    seal.seal_snipe_confirmed_consistency(tr, {})
    diag = tr["snipe_confirmed_seal"]["diagnostic"]
    assert "unresolved proof remains" not in diag
    assert "blocked by:" in diag and "LIVE_EDGE_SAFE" in diag


# ===========================================================================
# Formatter: confirmed-base STARTER names the exact SNIPE-only blocker
# ===========================================================================

def test_confirmed_base_starter_headline_names_blocker():
    tr = _tr(oh=_oh())  # unresolved -> sealed to STARTER
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "STARTER"
    body = discord_alerts.format_alert(tr)
    assert "Confirmed-base STARTER" in body
    assert "CANDLE_CONTEXT_UNRESOLVED" in body
    assert "STARTER conditions met." not in body


def test_legacy_starter_headline_untouched():
    # A plain STARTER (no seal marker, no 1H weakness) keeps the standard headline.
    tr = _tr(oh=_oh(candle="DISPLACEMENT", closed=True),
             final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    body = discord_alerts.format_alert(tr)
    assert "STARTER conditions met." in body


# ===========================================================================
# Audit output: reconciliation section renders + persisted-row recompute
# ===========================================================================

def test_audit_reconciliation_section_renders_live_and_persisted():
    tr = _tr(oh=_oh())
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = record_alert("LDR", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_ldr")
    row = state["tickers"]["LDR"]["alert_history"][-1]
    text = audit_access.format_row(row)
    assert "__SNIPE PROMOTION RECONCILIATION__" in text
    for label in ("Core sequence complete:", "Base entry sequence confirmed:",
                  "Candle context:", "Candle context reason:", "Candle context scope:",
                  "Candle tier effect:", "Capital blockers:", "SNIPE-only blockers:",
                  "Soft caps:", "Info notes:", "Leader context:", "Leader effect:",
                  "Hidden blocker violation:"):
        assert label in text, f"missing reconciliation label: {label}"
    assert "Survival conditions:" in text
    cj = audit_access.compact_json(row)
    json.dumps(cj, allow_nan=False)
    json.dumps(row, allow_nan=False)


def test_persisted_row_recompute_shows_candle_context():
    # Persisted rows carry the 14O one_hour_entry snapshot; the reconciliation
    # is recomputed deterministically for historical rows.
    tr = _tr(oh=_oh())
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = record_alert("LDR", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_ldr2")
    row = state["tickers"]["LDR"]["alert_history"][-1]
    text = audit_access.format_row(row)
    assert "UNRESOLVED_REJECTION" in text


# ===========================================================================
# Robustness
# ===========================================================================

def test_taxonomy_never_raises_on_junk():
    for junk in (None, {}, [], {"snipe_gate_audit": "bad"}, {"one_hour_entry": 5},
                 {"final_signal": "oops"}, {"higher_timeframe_context": 3}):
        c = tax.classify_blockers(junk)
        assert c["recommended_floor"] in ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT")
        json.dumps(c, allow_nan=False)


def test_seal_idempotent_across_floors():
    for tr in (_tr(oh=_oh(), tf=_TF_OK), _tr(oh=_oh()),
               _tr(oh=_oh(trigger="RETEST_IN_PROGRESS", hold="HOLD_WEAK", alert="WATCH_ONLY"))):
        seal.seal_snipe_confirmed_consistency(tr, {})
        first = tr["final_tier"]
        seal.seal_snipe_confirmed_consistency(tr, {})
        assert tr["final_tier"] == first


def test_normalized_candle_context_is_json_safe_and_stable():
    tr = _tr(oh=_oh(), tf=_TF_OK)
    a = tax.normalized_candle_context(tr)
    b = tax.normalized_candle_context(tr)
    assert a == b  # deterministic
    json.dumps(a, allow_nan=False)
    assert set(a.keys()) >= {"candle_context", "candle_context_reason",
                             "candle_context_scope", "candle_tier_effect",
                             "candle_blocker_code"}

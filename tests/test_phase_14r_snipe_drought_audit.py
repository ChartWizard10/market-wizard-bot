"""Phase 14R — SNIPE_IT drought root-cause audit + final tier calibration.

Root cause proven by pipeline simulation (real build_snipe_gate_audit ->
real seal): candle_evidence marks the live bar OPEN_ONLY on essentially every
intra-bar scan, which made LIVE_EDGE_SAFE structurally unsatisfiable at live
cadence — every confirmed-base candidate was floored to STARTER even when the
1H engine had already proven a CLOSED candle confirms. Phase 14R makes closed
candle truth sovereign over open-bar cosmetics: the soft live-edge veto blocks
full size only when closed proof is genuinely absent (candle context
UNRESOLVED/UNKNOWN). Hard vetoes and weak-1H discipline are unchanged.

FINAL LAW under test: SNIPE_IT must be rare because truth is rare — not
because the code made it impossible.
"""

import json

from src import snipe_blocker_taxonomy as tax
from src import snipe_confirmed_seal as seal
from src import snipe_drought_audit as sda
from src import snipe_gate_audit as sga_mod


# ---------------------------------------------------------------------------
# Fixtures — arbitrary ticker, judged by the same formula as every ticker
# ---------------------------------------------------------------------------

def _signal(**over):
    s = {
        "ticker": "LDR", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals", "reason": "SNIPE_IT conditions met.",
        "next_action": "Enter full size.", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 101.0, "targets": [108, 115],
        "missing_conditions": [], "risk_realism_state": "healthy",
        "upgrade_trigger": "none",
    }
    s.update(over)
    return s


def _oh(**over):
    o = {
        "status": "ENABLED", "trigger_state": "TRIGGER_LIVE",
        "alert_truth_label": "CONFIRMED_TRIGGER", "score": 88,
        "score_label": "STRONG_1H_TRIGGER", "data_freshness": "FRESH",
        "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID", "hold_truth": "HOLD_CONFIRMED"},
        "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "invalidation": {"clear": True},
    }
    o.update(over)
    return o


_TF_OK = {
    "alignment_label": "FULL_STACK_ALIGNED", "status": "ENABLED",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_VALID"},
}
_HTF_LEADER = {
    "weekly_campaign_state": "HTF_CONTINUATION",
    "campaign_location_label": "EXTENDED_ABOVE_VALUE",
    "context_grade": "C", "context_score": 60,
    "weakens_long_setup": True, "blocks_snipe_contextually": False,
    "monthly_bias": "UNKNOWN", "data_status": "OK",
}
# The live-cadence reality: the current bar is open -> candle_veto OPEN_ONLY.
_CE_OPEN_BAR = {"status": "ok", "candle_family": "RETEST_HOLD",
                "next_candle_verdict": "UNKNOWN", "candle_veto": "OPEN_ONLY",
                "level_reaction": "HELD"}
_TL_OK = {"location_state": "mid_zone_acceptance", "scan_price": 101.0, "zone_mid": 99.5}


def _tr(sig=None, one="default", tf=_TF_OK, htf=_HTF_LEADER, ce=_CE_OPEN_BAR, tl=_TL_OK,
        final_tier="SNIPE_IT", capital="full_quality_allowed", channel="#snipe-signals"):
    s = dict(sig if sig is not None else _signal())
    s["tier"] = final_tier
    s["capital_action"] = capital
    s["discord_channel"] = channel
    tr = {
        "final_tier": final_tier, "capital_action": capital,
        "final_discord_channel": channel, "safe_for_alert": True, "score": 92,
        "final_signal": s,
    }
    if one == "default":
        tr["one_hour_entry"] = _oh()
    elif one is not None:
        tr["one_hour_entry"] = one
    if tf is not None:
        tr["timeframe_alignment"] = tf
    if htf is not None:
        tr["higher_timeframe_context"] = htf
    if ce is not None:
        tr["candle_evidence"] = ce
    if tl is not None:
        tr["trade_location"] = tl
    return tr


def _sealed(tr):
    """Run the REAL production audit + seal pipeline on a tiering result."""
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit(
        tr["final_signal"].get("ticker", "LDR"), tr, {}, {})
    seal.seal_snipe_confirmed_consistency(tr, {})
    return tr


# ===========================================================================
# 1 — defensive rejection + full sequence preserves SNIPE_IT
# ===========================================================================

def test_defensive_rejection_full_sequence_becomes_or_preserves_snipe():
    tr = _sealed(_tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False})))
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["candle_context"]["candle_context"] == "DEFENSIVE_REJECTION"
    assert not recon["capital_blockers"]


# ===========================================================================
# 2 — soft caps alone do not block SNIPE_IT
# ===========================================================================

def test_soft_caps_alone_do_not_block_snipe():
    # HTF extended + grade C + monthly unknown + open live bar; path clean;
    # blocks_snipe_contextually=false. Full confirmed sequence.
    tr = _sealed(_tr())
    assert tr["final_tier"] == "SNIPE_IT"
    recon = tr["snipe_promotion_reconciliation"]
    assert not recon["capital_blockers"] and not recon["snipe_only_blockers"]
    soft_codes = {b["code"] for b in recon["soft_caps"]}
    assert "HTF_EXTENDED" in soft_codes
    # The open live bar is disclosed as a soft cap, never a blocker here.
    assert "LIVE_EDGE_SAFE" in soft_codes


# ===========================================================================
# 3 — SNIPE-only blocker floors to STARTER, never NEAR_ENTRY
# ===========================================================================

def test_snipe_only_blocker_does_not_become_capital_blocker():
    # Base confirmed but defensive-vs-hostile unprovable (no TF/TL evidence)
    # -> genuine full-size proof gap -> STARTER, not NEAR_ENTRY.
    tr = _sealed(_tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False}),
                     tf=None))
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["snipe_only_blockers"] and not recon["capital_blockers"]


# ===========================================================================
# 4 — hostile rejection blocks capital
# ===========================================================================

def test_hostile_rejection_blocks_capital():
    # TRUE hostile: no real retest truth -> base not alive -> entry-zone
    # acceptance genuinely unproven -> capital blocked (14M.1 discipline).
    tr = _sealed(_tr(one=_oh(trigger_state="RETEST_IN_PROGRESS",
                             alert_truth_label="WATCH_ONLY",
                             pullback_retest_hold={"retest_truth": "NONE",
                                                   "hold_truth": "HOLD_WEAK"},
                             candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False})))
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["capital_blockers"]


def test_weak_1h_with_alive_base_floors_starter_14s():
    # Phase 14S recalibration: the same weak 1H WITH an alive base (real retest
    # truth, invalidation clear, zone defended) is a full-size gap -> STARTER.
    tr = _sealed(_tr(one=_oh(trigger_state="RETEST_IN_PROGRESS",
                             alert_truth_label="WATCH_ONLY",
                             pullback_retest_hold={"retest_truth": "RETEST_REAL",
                                                   "hold_truth": "HOLD_WEAK"},
                             candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False})))
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["snipe_only_blockers"], "full-size gap must be named"


# ===========================================================================
# 5 — expansion rejection never claims the base retest failed
# ===========================================================================

def test_expansion_rejection_does_not_claim_base_retest_failed():
    tr = _tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                   "closed_candle_confirms": True}))
    tr["candle_evidence"] = {"status": "ok", "candle_family": "FAILED_BREAK",
                             "next_candle_verdict": "UNKNOWN", "candle_veto": "NONE",
                             "level_reaction": "HELD"}
    c = tax.classify_blockers(tr)
    cc = c["candle_context"]
    assert cc["candle_context"] == "EXPANSION_REJECTION"
    assert cc["candle_context_scope"] == "EXPANSION_ADD_LEVEL"
    assert "expansion/add trigger failed" in cc["candle_context_reason"].lower()
    assert "entry-zone retest failed" not in cc["candle_context_reason"].lower()
    assert cc["candle_tier_effect"] != "CAPITAL_BLOCKER"


# ===========================================================================
# 6 — no blank blocked promotion
# ===========================================================================

def test_no_blank_blocked_promotion():
    tr = _sealed(_tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False}),
                     tf=None))
    assert tr["final_tier"] != "SNIPE_IT"
    sgao = tr["snipe_gate_audit"]
    recon = tr["snipe_promotion_reconciliation"]
    if str(sgao.get("promotion_state")).upper() == "PROMOTION_BLOCKED":
        assert recon["capital_blockers"] or recon["snipe_only_blockers"]
        assert recon["named_blockers"]
    assert "unresolved proof remains" not in str(tr["snipe_confirmed_seal"]["diagnostic"])


# ===========================================================================
# 7 — WDC-style leader continuation fixture must be SNIPE_IT (no false drought)
# ===========================================================================

def test_no_snipe_drought_false_negative_fixture():
    # Weekly continuation, Daily granted, 4H valid, 1H trigger live, retest
    # core-valid, hold confirmed, invalidation clear, path clean, defensive
    # rejection, R:R valid — at live cadence (bar still open).
    tr = _sealed(_tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False})))
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    assert "snipe" in tr["final_discord_channel"]
    recon = tr["snipe_promotion_reconciliation"]
    assert recon["leader_context"] == "LEADER_CONTINUATION_CONTEXT"
    assert recon["leader_effect"] == "SOFT_CAP_RELIEF"


# ===========================================================================
# 8 — NEAR_ENTRY is never promoted by the seal
# ===========================================================================

def test_near_entry_not_promoted_by_seal():
    tr = _tr(final_tier="NEAR_ENTRY", capital="wait_no_capital",
             channel="#near-entry-watch")
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert "snipe_confirmed_seal" not in tr  # seal never engaged


# ===========================================================================
# 9 — no fake SNIPE: broken invalidation / path / accepted-below-zone blocks
# ===========================================================================

def test_no_fake_snipe_missing_invalidation():
    tr = _sealed(_tr(sig=_signal(invalidation_level=None, invalidation_condition=""),
                     one=_oh(invalidation={"clear": False})))
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"


def test_no_fake_snipe_accepted_below_zone():
    tr = _sealed(_tr(sig=_signal(scan_price=95.0),  # below invalidation 96.5
                     one=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False})))
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"


def test_no_fake_snipe_hostile_live_edge():
    tr = _sealed(_tr(ce={"status": "ok", "candle_family": "RETEST_HOLD",
                         "next_candle_verdict": "UNKNOWN",
                         "candle_veto": "HOSTILE_WICK", "level_reaction": "HELD"}))
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"


# ===========================================================================
# 10 — drought audit outputs
# ===========================================================================

def _history_rows():
    """Synthetic persisted-style history: one buried leader (pre-14R shape),
    one genuine weak-1H NEAR_ENTRY, one STARTER with unresolved candle."""
    buried = _sealed(_tr(one=_oh(candle_truth={"event_type": "REJECTION",
                                               "closed_candle_confirms": False}),
                         tf=None))
    weak = _sealed(_tr(one=_oh(trigger_state="RETEST_IN_PROGRESS",
                               alert_truth_label="WATCH_ONLY",
                               pullback_retest_hold={"retest_truth": "RETEST_REAL",
                                                     "hold_truth": "HOLD_WEAK"},
                               candle_truth={"event_type": "REJECTION",
                                             "closed_candle_confirms": False})))
    rows = []
    for i, tr in enumerate((buried, weak)):
        rows.append({
            "ticker": f"T{i}", "scan_id": f"scan_{i}", "alerted_at": f"2026-07-0{i+1}T10:00",
            "tier": tr["final_tier"], "capital_action": tr["capital_action"],
            "score": 88, "final_discord_channel": tr["final_discord_channel"],
            "retest_status": "confirmed", "hold_status": "confirmed",
            "snipe_gate_audit": tr["snipe_gate_audit"],
            "snipe_confirmed_seal": tr.get("snipe_confirmed_seal"),
            "one_hour_entry": tr.get("one_hour_entry"),
            "timeframe_alignment": tr.get("timeframe_alignment"),
            "higher_timeframe_context": tr.get("higher_timeframe_context"),
        })
    return rows


def test_drought_audit_outputs_blocker_frequency():
    report = sda.run_snipe_drought_audit(rows=_history_rows())
    assert report["total_rows"] == 2
    assert report["tier_counts"]  # tier distribution present
    freq = report["blocker_frequency"]
    assert isinstance(freq, dict) and any(v > 0 for v in freq.values())
    assert report["almost_snipe"], "almost-SNIPE table must list the closest candidates"
    top = report["almost_snipe"][0]
    for key in ("ticker", "scan_id", "tier", "snipe_score", "promotion_state",
                "candle_context", "leader_context", "reason_not_snipe", "blocker_class"):
        assert key in top
    assert report["primary_root_causes"], "root cause classification required"
    assert report["recommended_actions"]
    text = sda.render_snipe_drought_audit(report)
    for label in ("__SNIPE_IT DROUGHT AUDIT__", "__TIER DISTRIBUTION__",
                  "__BLOCKER FREQUENCY__", "__ALMOST-SNIPE", "__ROOT CAUSE__",
                  "__RECOMMENDED ACTIONS__"):
        assert label in text
    json.dumps(report, allow_nan=False)


def test_drought_audit_flags_impossible_gate():
    # Every eligible row missing the same gate -> impossible-gate diagnostic (F).
    rows = []
    for i in range(5):
        rows.append({
            "ticker": f"X{i}", "scan_id": f"s{i}", "alerted_at": f"2026-07-01T0{i}:00",
            "tier": "STARTER", "score": 85,
            "snipe_gate_audit": {
                "eligible_for_snipe_review": True, "promotion_state": "PROMOTION_PENDING",
                "raw_snipe_score": 90, "snipe_score": 90, "snipe_grade": "A",
                "blocked_gate_names": [], "blocked_gates": [],
                "missing_proofs": ["LIVE_EDGE_SAFE: live-edge forming (OPEN_ONLY)"],
                "score_blocked_by": [], "blocking_reasons": [], "promotion_triggers": [],
            },
        })
    report = sda.run_snipe_drought_audit(rows=rows)
    assert any(ig["gate"] == "LIVE_EDGE_SAFE" for ig in report["impossible_gates"])
    assert any(rc["code"] == "F" for rc in report["primary_root_causes"])
    assert any("LIVE_EDGE_SAFE" in a for a in report["recommended_actions"])


def test_drought_audit_never_raises_on_junk():
    for junk in (None, [], [{}], [{"tier": 5}], [{"snipe_gate_audit": "bad"}]):
        report = sda.run_snipe_drought_audit(rows=junk)
        assert "tier_counts" in report
    report = sda.run_snipe_drought_audit(state={"tickers": "bad"})
    assert report["total_rows"] == 0


def test_drought_audit_is_read_only():
    rows = _history_rows()
    import copy
    before = copy.deepcopy(rows)
    sda.run_snipe_drought_audit(rows=rows)
    assert rows == before, "drought audit must never mutate history rows"

"""Phase 14U — SNIPE / STARTER shyness funnel audit.

Proves WHERE in the 13-stage scan pipeline a valid SNIPE_IT / STARTER
opportunity is capped, blocked, suppressed, or never admitted — and, equally
important, proves the audit is HONEST about the stages it cannot observe.

LAW under test: a diagnostic that reports a confident zero for a stage it
cannot see is worse than no diagnostic at all. Every unobservable stage must
report null and be named as a blind spot; every recompute that leans on a
field `state_store.record_alert` does not persist must be marked
not-determinable rather than converted into a fake verdict.

This phase changes no tiering, capital, routing, threshold, gate, ladder,
seal, dedup, or cooldown behaviour. It is read-only instrumentation.
"""

import ast
import copy
import json
from pathlib import Path

from src import audit_access
from src import snipe_blocker_taxonomy as tax
from src import snipe_confirmed_seal as seal_mod
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as ladder_mod
from src import snipe_shyness_funnel_audit as ssfa
from src import state_store


CFG = {
    "tiers": {
        "snipe_it": {"min_score": 85, "min_rr": 3.0, "min_risk_distance_pct": 0.35},
        "starter": {"min_score": 75, "min_rr": 3.0},
        "near_entry": {"min_score": 60},
    },
    "prefilter": {"max_claude_candidates_per_scan": 30, "prefilter_min_score": 55},
    "state": {"max_memory_entries": 500, "cooldown_minutes": 60},
    "discord": {"snipe_channel_id": 1497532086335311883,
                "starter_channel_id": 1497532177359962112},
    "audit_access": {"enabled": True, "allowed_user_ids": ["4242"],
                     "allowed_channel_ids": ["777"]},
}


# ---------------------------------------------------------------------------
# Fixtures — arbitrary tickers, judged by the same funnel as every ticker
# ---------------------------------------------------------------------------

def _oh(**over):
    o = {
        "status": "ENABLED", "enabled": True, "trigger_state": "TRIGGER_LIVE",
        "alert_truth_label": "CONFIRMED_TRIGGER", "score": 88,
        "score_label": "STRONG_1H_TRIGGER", "data_freshness": "FRESH",
        "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID",
                                 "hold_truth": "HOLD_CONFIRMED"},
        "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "invalidation": {"clear": True, "level": 96.5,
                         "condition": "1H close below 96.5"},
    }
    o.update(over)
    return o


_TF_OK = {
    "enabled": True, "status": "ENABLED", "alignment_label": "FULL_STACK_ALIGNED",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_VALID"},
    "conflicts": [], "hard_caps_applied": [],
}
_HTF_OK = {
    "data_status": "OK", "weekly_campaign_state": "HTF_CONTINUATION",
    "campaign_location_label": "INSIDE_VALUE", "context_grade": "B",
    "context_score": 75, "weakens_long_setup": False,
    "blocks_snipe_contextually": False,
}
_SGA_CLEAN = {
    "audit_label": "SNIPE_AUDIT", "promotion_state": "PROMOTION_READY",
    "snipe_score": 90, "snipe_grade": "A", "eligible_for_snipe_review": True,
    "blocked_gate_names": [], "missing_proofs": [], "blocking_reasons": [],
}
_SGA_BLOCKED = {
    **_SGA_CLEAN, "promotion_state": "PROMOTION_BLOCKED",
    "eligible_for_snipe_review": False,
    "blocked_gate_names": ["FOUR_H_LOCATION_VALID"],
    "missing_proofs": ["ONE_H_TRIGGER_CONFIRMED"],
}


def _row(ticker="AAA", tier="STARTER", capital="starter_only", score=88,
         oh=None, tf=None, htf=None, sga=None, seal=None, **extra):
    """A persisted alert_history row, shaped exactly as record_alert writes it."""
    r = {
        "ticker": ticker, "scan_id": "scan_20260810_120000_aaaaaa",
        "alerted_at": "2026-08-10T12:00:00", "tier": tier,
        "capital_action": capital, "score": score,
        "trigger_level": 100.0, "invalidation_level": 96.5, "risk_reward": 3.4,
        "scan_price": 101.0, "targets": [108, 115], "risk_distance_pct": 3.5,
        "structure_event": "bos", "retest_status": "confirmed",
        "hold_status": "confirmed", "overhead_status": "clear",
        "final_discord_channel": "#starter", "reason": "Starter entry.",
        "one_hour_entry": _oh() if oh is None else oh,
        "timeframe_alignment": copy.deepcopy(_TF_OK) if tf is None else tf,
        "higher_timeframe_context": copy.deepcopy(_HTF_OK) if htf is None else htf,
    }
    if sga is not None:
        r["snipe_gate_audit"] = sga
    if seal is not None:
        r["snipe_confirmed_seal"] = seal
    r.update(extra)
    return r


def _classes(row, config=CFG):
    return ssfa.classify_row(row, config)["classes"]


# ===========================================================================
# A — vocabulary and funnel contract
# ===========================================================================

def test_shyness_classes_is_the_documented_closed_set():
    expected = {
        "PREFILTER_REJECTED", "NOT_IN_TOP_30", "CLAUDE_NOT_ANALYZED",
        "BASE_TIER_CAPPED", "ONE_H_PROOF_MISSING", "ONE_H_PROOF_TOO_STRICT",
        "FOUR_H_LOCATION_REPAIR_CAP", "TIMEFRAME_ALIGNMENT_CAP",
        "SNIPE_GATE_BLOCKED", "LADDER_CAPPED", "SEAL_DOWNGRADED",
        "DEDUP_SUPPRESSED", "COOLDOWN_SUPPRESSED", "ROUTING_SUPPRESSED",
        "ALERT_WORDING_UNDERSTATED", "CORRECTLY_BLOCKED_HARD_FAILURE",
        "CORRECTLY_WAITING_FOR_PROOF", "POSSIBLE_STARTER_UNDERCALL",
        "POSSIBLE_SNIPE_UNDERCALL", "UNCLASSIFIED",
    }
    assert set(ssfa.SHYNESS_CLASSES) == expected


def test_funnel_has_thirteen_stages_in_pipeline_order():
    assert len(ssfa.STAGES) == 13
    assert [s["n"] for s in ssfa.STAGES] == list(range(1, 14))
    assert len(set(ssfa.STAGE_IDS)) == 13


def test_every_class_maps_to_a_real_stage():
    assert set(ssfa.CLASS_STAGE) == set(ssfa.SHYNESS_CLASSES)
    for cls, stage in ssfa.CLASS_STAGE.items():
        assert stage in ssfa.STAGE_IDS, cls


def test_unobservable_classes_are_a_subset_and_cover_the_blind_stages():
    assert ssfa.UNOBSERVABLE_CLASSES <= ssfa.SHYNESS_CLASSES
    # An unobservable class must never sit on a stage the audit claims to see
    # fully. NOT_PERSISTED (nothing survives) and PARTIAL (only the survivors
    # survive — e.g. routing, where suppressed rows are never recorded) both
    # qualify; OBSERVABLE does not.
    weak = {s["id"] for s in ssfa.STAGES
            if s["observability"] in (ssfa.NOT_PERSISTED, ssfa.PARTIAL)}
    for cls in ssfa.UNOBSERVABLE_CLASSES:
        assert ssfa.CLASS_STAGE[cls] in weak, cls
    assert ssfa.CLASS_STAGE[ssfa.ROUTING_SUPPRESSED] == "ROUTING_AND_ALERT_WORDING"


def test_classify_row_never_emits_an_unobservable_class():
    rows = [
        _row(), _row(sga=_SGA_CLEAN), _row(sga=_SGA_BLOCKED),
        _row(tier="NEAR_ENTRY", capital="wait_no_capital", score=62),
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92),
        _row(oh={}), _row(oh=_oh(trigger_state="FAILED_RETEST")),
        _row(tf={}), _row(htf={}), {},
    ]
    for r in rows:
        for cls in _classes(r):
            assert cls not in ssfa.UNOBSERVABLE_CLASSES, (cls, r.get("tier"))


def test_unobservable_stages_report_null_never_zero():
    report = ssfa.run_shyness_funnel_audit(rows=[_row(sga=_SGA_CLEAN)], config=CFG)
    for stage in report["stages"]:
        if stage["observability"] == ssfa.NOT_PERSISTED:
            assert stage["shy_rows_attributed"] is None, stage["stage"]
        else:
            assert isinstance(stage["shy_rows_attributed"], int), stage["stage"]


# ===========================================================================
# B — read-only guarantees
# ===========================================================================

def test_classify_row_never_mutates_the_row():
    row = _row(sga=_SGA_CLEAN, seal={"applied": True, "reason": "seal"})
    before = copy.deepcopy(row)
    ssfa.classify_row(row, CFG)
    assert row == before


def test_run_audit_never_mutates_the_state_dict():
    state = {"tickers": {"AAA": {"alert_history": [_row(sga=_SGA_CLEAN)]}},
             "meta": {"total_alerts": 1}}
    before = copy.deepcopy(state)
    ssfa.run_shyness_funnel_audit(state=state, config=CFG)
    assert state == before


def test_module_never_writes_state_or_imports_network():
    """AST-level purity check — prose in the docstring must not be able to
    pass or fail this test, only real imports and real calls."""
    tree = ast.parse(Path("src/snipe_shyness_funnel_audit.py").read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            imported.update(a.name for a in node.names)
    for forbidden in ("discord", "requests", "urllib", "httpx", "aiohttp",
                      "subprocess", "socket", "shutil", "state_store"):
        assert forbidden not in imported, forbidden

    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            called.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            called.add(fn.attr)
            if isinstance(fn.value, ast.Name):
                called.add(f"{fn.value.id}.{fn.attr}")
    for forbidden in ("open", "exec", "eval", "save", "record_alert",
                      "write_text", "write", "send_alert", "check_alert",
                      "validate", "apply_ladder_arbitration",
                      "seal_snipe_confirmed_consistency"):
        assert forbidden not in called, forbidden


def test_never_raises_on_garbage_input():
    for junk in (None, [], "not-a-row", 7, {"tier": object()},
                 {"one_hour_entry": "nope", "snipe_gate_audit": 5}):
        out = ssfa.classify_row(junk, CFG)
        assert out["primary_class"] in ssfa.SHYNESS_CLASSES or out["primary_class"] is None
    for junk in (None, "x", 3, [{"bad": 1}]):
        rep = ssfa.run_shyness_funnel_audit(rows=junk if isinstance(junk, list) else None,
                                            state=junk if not isinstance(junk, list) else None,
                                            config=CFG)
        assert isinstance(rep, dict)
        assert ssfa.render_shyness_funnel_audit(rep)


# ===========================================================================
# C — classification correctness
# ===========================================================================

def test_below_ceiling_on_a_recompute_is_a_possible_undercall_not_a_proven_cap():
    """Phase 14U.1: a below-ceiling row whose scan-time ladder was never
    persisted is evidence for review, not a proven stage-10 cap."""
    out = ssfa.classify_row(_row(sga=_SGA_CLEAN), CFG)
    assert out["ceiling_tier"] == "SNIPE_IT"
    assert out["tier"] == "STARTER"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_RECONSTRUCTED
    assert ssfa.LADDER_CAPPED not in out["classes"]
    assert out["primary_class"] == ssfa.POSSIBLE_SNIPE_UNDERCALL
    assert out["stage"] == "LADDER_ARBITRATION"
    assert out["is_shy"] is True


def test_seal_downgraded_takes_precedence_when_the_seal_applied():
    out = ssfa.classify_row(
        _row(sga=_SGA_CLEAN, seal={"applied": True, "reason": "downgrade"}), CFG)
    assert out["primary_class"] == ssfa.SEAL_DOWNGRADED
    assert out["stage"] == "DOWNGRADE_ONLY_SEAL"


def test_one_h_proof_missing_when_one_h_gates_block():
    assert ssfa.ONE_H_PROOF_MISSING in _classes(_row(sga=_SGA_BLOCKED))


def test_one_h_proof_too_strict_when_only_closed_bar_proof_is_outstanding():
    row = _row(sga=_SGA_CLEAN,
               oh=_oh(candle_truth={"event_type": "REJECTION",
                                    "closed_candle_confirms": False}))
    out = ssfa.classify_row(row, CFG)
    assert ssfa.ONE_H_PROOF_TOO_STRICT in out["classes"]
    assert out["stage"] == "ONE_H_ENTRY_PROOF"
    # Doctrine must be restated, not waived.
    assert "open candle cannot create SNIPE authority" in out["why"]


def test_hostile_rejection_is_never_called_over_strict():
    assert tax.CODE_HOSTILE not in ssfa._CLOSED_BAR_GATES
    row = _row(sga=_SGA_CLEAN,
               oh=_oh(candle_truth={"event_type": "REJECTION",
                                    "closed_candle_confirms": False,
                                    "wick_rejection": True,
                                    "body_acceptance": False}),
               candle_evidence={"candle_veto": "HOSTILE_WICK", "status": "ok"})
    assert ssfa.ONE_H_PROOF_TOO_STRICT not in _classes(row)


def test_four_h_location_repair_cap():
    tf = {**copy.deepcopy(_TF_OK), "alignment_label": "PARTIAL",
          "operational_timeframe": {"state": "REPAIRING_IN_ZONE"}}
    assert ssfa.FOUR_H_LOCATION_REPAIR_CAP in _classes(_row(tf=tf, sga=_SGA_CLEAN))


def test_timeframe_alignment_cap_on_conflicts():
    tf = {**copy.deepcopy(_TF_OK),
          "conflicts": [{"layer": "daily", "reason": "below value"}]}
    assert ssfa.TIMEFRAME_ALIGNMENT_CAP in _classes(_row(tf=tf, sga=_SGA_CLEAN))


def test_snipe_gate_blocked_when_promotion_state_is_blocked():
    assert ssfa.SNIPE_GATE_BLOCKED in _classes(_row(sga=_SGA_BLOCKED))


def test_base_tier_capped_when_the_numeric_score_is_the_binding_constraint():
    out = ssfa.classify_row(
        _row(tier="NEAR_ENTRY", capital="wait_no_capital", score=70,
             sga=_SGA_CLEAN), CFG)
    assert ssfa.BASE_TIER_CAPPED in out["classes"]
    assert "min_score" in out["why"]


def test_undercall_classes_track_the_taxonomy_floor():
    snipe = ssfa.classify_row(_row(sga=_SGA_CLEAN), CFG)
    assert snipe["floor_tier"] == "SNIPE_IT"
    assert ssfa.POSSIBLE_SNIPE_UNDERCALL in snipe["classes"]

    tf = {**copy.deepcopy(_TF_OK), "alignment_label": "PARTIAL",
          "operational_timeframe": {"state": "REPAIRING_IN_ZONE"}}
    starter = ssfa.classify_row(
        _row(tier="NEAR_ENTRY", capital="wait_no_capital", score=80,
             tf=tf, sga=_SGA_CLEAN), CFG)
    assert (ssfa.POSSIBLE_STARTER_UNDERCALL in starter["classes"]
            or ssfa.POSSIBLE_SNIPE_UNDERCALL in starter["classes"])


# ===========================================================================
# D — benign verdicts are never inflated into shyness
# ===========================================================================

def test_hard_failure_is_correctly_blocked_and_not_shy():
    row = _row(tier="WAIT", capital="no_trade", score=40,
               oh=_oh(trigger_state="FAILED_RETEST",
                      alert_truth_label="FAILED_TRIGGER",
                      pullback_retest_hold={"retest_truth": "RETEST_FAILED",
                                            "hold_truth": "HOLD_FAILED"}))
    out = ssfa.classify_row(row, CFG)
    assert out["primary_class"] == ssfa.CORRECTLY_BLOCKED_HARD_FAILURE
    assert out["is_shy"] is False


def test_clean_snipe_at_its_ceiling_produces_no_finding_at_all():
    out = ssfa.classify_row(
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92,
             sga=_SGA_CLEAN), CFG)
    assert out["classes"] == []
    assert out["primary_class"] is None
    assert out["stage"] is None
    assert out["is_shy"] is False
    assert out["ceiling_vs_served"] == "AT_CEILING"


def test_correctly_waiting_for_proof_when_nothing_caps_the_row():
    htf = {**copy.deepcopy(_HTF_OK), "context_grade": "C", "context_score": 55,
           "weakens_long_setup": True}
    out = ssfa.classify_row(
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92,
             htf=htf, sga=_SGA_CLEAN), CFG)
    assert out["is_shy"] is False


def test_alert_wording_understated_only_fires_when_capital_was_granted():
    understated = _row(tier="STARTER", capital="starter_only", score=88,
                       sga=_SGA_CLEAN,
                       sanitized_reason="Watch only; no capital until proof.")
    assert ssfa.ALERT_WORDING_UNDERSTATED in _classes(understated)

    honest = _row(tier="NEAR_ENTRY", capital="wait_no_capital", score=65,
                  sga=_SGA_CLEAN,
                  sanitized_reason="Watch only; no capital until proof.")
    assert ssfa.ALERT_WORDING_UNDERSTATED not in _classes(honest)


# ===========================================================================
# E — observability honesty (the core of Phase 14U)
# ===========================================================================

def test_missing_invalidation_condition_is_not_determinable_not_a_hard_failure():
    # record_alert never persists final_signal.invalidation_condition, and this
    # row carries no one_hour_entry.invalidation.clear either.
    row = _row(oh={}, sga=_SGA_CLEAN)
    out = ssfa.classify_row(row, CFG)
    assert out["recompute_confidence"] == ssfa.LOW_CONFIDENCE
    assert out["primary_class"] == ssfa.UNCLASSIFIED
    assert out["is_shy"] is False
    assert ssfa.CORRECTLY_BLOCKED_HARD_FAILURE not in out["classes"]
    assert any("invalidation_condition" in g for g in out["recompute_gaps"])


def test_served_tier_above_recomputed_ceiling_is_reported_not_called_over_promotion():
    htf = {**copy.deepcopy(_HTF_OK), "campaign_location_label": "EXTENDED_ABOVE_VALUE",
           "context_grade": "C", "context_score": 55, "weakens_long_setup": True}
    out = ssfa.classify_row(
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92,
             htf=htf, oh=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False}),
             sga=_SGA_CLEAN), CFG)
    assert out["ceiling_vs_served"] == "ABOVE_RECOMPUTED_CEILING"
    assert out["is_shy"] is False
    assert "does not persist" in out["why"]


def test_report_names_every_blind_spot():
    report = ssfa.run_shyness_funnel_audit(rows=[_row(sga=_SGA_CLEAN)], config=CFG)
    named = {b["cls"] for b in report["blind_spots"]}
    assert named == set(ssfa.UNOBSERVABLE_CLASSES)
    for b in report["blind_spots"]:
        assert b["reason"].strip()


def test_report_names_the_persistence_gaps_that_degrade_the_recompute():
    report = ssfa.run_shyness_funnel_audit(rows=[_row(sga=_SGA_CLEAN)], config=CFG)
    fields = {g["field"] for g in report["persistence_gaps"]}
    assert "final_signal.invalidation_condition" in fields
    assert "snipe_ladder" in fields


def test_observability_note_states_sent_alerts_only():
    note = ssfa.run_shyness_funnel_audit(rows=[], config=CFG)["observability_note"]
    assert "SENT ALERTS ONLY" in note
    assert "never as zero" in note


def test_pre_top_30_shyness_is_declared_undeterminable_in_code_and_report():
    src = Path("src/snipe_shyness_funnel_audit.py").read_text(encoding="utf-8")
    assert "cannot be determined from the current persisted alert_history" in src
    report = ssfa.run_shyness_funnel_audit(rows=[_row(sga=_SGA_CLEAN)], config=CFG)
    reasons = {b["cls"]: b["reason"] for b in report["blind_spots"]}
    assert "never written to alert_history" in reasons[ssfa.NOT_IN_TOP_30]


# ===========================================================================
# F — !auditshy command surface (existing commands untouched)
# ===========================================================================

def test_auditshy_denies_unauthorized_callers():
    out = audit_access.run_auditshy(CFG, "", user_id="9999", channel_id="0")
    assert out["ok"] is False
    assert out["error"] == "unauthorized"


def test_auditshy_rejects_an_unknown_token_with_usage():
    out = audit_access.run_auditshy(CFG, "bogus", user_id="4242")
    assert out["error"] == "usage"
    assert "!auditshy" in out["messages"][0]


def test_auditshy_accepts_the_same_grammar_as_auditready(monkeypatch):
    seen = {}

    def _fake(config, limit=100, json_mode=False):
        seen["limit"], seen["json"] = limit, json_mode
        return {"ok": True, "error": None, "match_count": 0, "json": None,
                "messages": ["ok"]}

    monkeypatch.setattr(audit_access, "build_auditshy_report", _fake)
    audit_access.run_auditshy(CFG, "50 json", user_id="4242")
    assert seen == {"limit": 50, "json": True}
    audit_access.run_auditshy(CFG, "5", user_id="4242")        # clamped up
    assert seen["limit"] == 10
    audit_access.run_auditshy(CFG, "9999", user_id="4242")     # clamped down
    assert seen["limit"] == 300


def test_auditshy_json_mode_is_a_sanitized_whitelist(tmp_path, monkeypatch):
    state = {"tickers": {"AAA": {"alert_history": [_row(sga=_SGA_CLEAN)]}},
             "meta": {"total_alerts": 1}}
    path = tmp_path / "alert_history.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    cfg = {**CFG, "state": {**CFG["state"], "state_file": str(path)}}

    out = audit_access.run_auditshy(cfg, "json", user_id="4242")
    assert out["ok"] is True
    blob = json.dumps(out["json"])
    for secret in ("1497532086335311883", "1497532177359962112", "ANTHROPIC",
                   "DISCORD", "allowed_user_ids", str(path)):
        assert secret not in blob, secret
    assert set(out["json"]["examples"][0]) <= set(ssfa._EXAMPLE_JSON_KEYS)


def test_existing_audit_commands_are_unchanged():
    assert audit_access.run_audit(CFG, "", user_id="4242")["error"] == "usage"
    assert "!audit <scan_id|TICKER>" in audit_access.run_audit(
        CFG, "", user_id="4242")["messages"][0]
    assert audit_access.run_auditready(CFG, "bogus", user_id="4242")["error"] == "usage"
    assert audit_access.run_audit(CFG, "AAA", user_id="0", channel_id="0")["error"] == \
        "unauthorized"


def test_main_registers_auditshy_and_documents_it_in_help():
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert 'bot.command(name="auditshy")' in main_src
    assert "audit_access.run_auditshy" in main_src
    assert "`!auditshy [rows] [json]`" in main_src
    # existing commands survive
    assert 'bot.command(name="audit")' in main_src
    assert 'bot.command(name="auditready")' in main_src


# ===========================================================================
# G — end-to-end through the real production organs
# ===========================================================================

def _live_tiering_result(tier="SNIPE_IT", capital="full_quality_allowed"):
    signal = {
        "ticker": "EEE", "tier": tier, "capital_action": capital,
        "discord_channel": "#snipe-signals", "reason": "SNIPE_IT conditions met.",
        "next_action": "Enter full size.", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 101.0, "targets": [108, 115],
        "missing_conditions": [], "risk_realism_state": "healthy",
        "upgrade_trigger": "none",
    }
    return {
        "final_tier": tier, "capital_action": capital,
        "final_discord_channel": "#snipe-signals", "safe_for_alert": True,
        "score": 92, "final_signal": signal, "one_hour_entry": _oh(),
        "timeframe_alignment": copy.deepcopy(_TF_OK),
        "higher_timeframe_context": copy.deepcopy(_HTF_OK),
        "candle_evidence": {"status": "ok", "candle_family": "RETEST_HOLD",
                            "next_candle_verdict": "UNKNOWN",
                            "candle_veto": "OPEN_ONLY", "level_reaction": "HELD"},
        "trade_location": {"location_state": "mid_zone_acceptance",
                           "scan_price": 101.0, "zone_mid": 99.5},
    }


def test_end_to_end_real_pipeline_row_classifies_without_contradiction():
    tr = _live_tiering_result()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("EEE", tr, {}, CFG)
    ladder_mod.apply_ladder_arbitration(tr, CFG)
    seal_mod.seal_snipe_confirmed_consistency(tr, CFG)

    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, CFG, "scan_20260810_130000_bbbbbb")
    row = state["tickers"]["EEE"]["alert_history"][-1]

    out = ssfa.classify_row(row, CFG)
    assert out["ticker"] == "EEE"
    # Phase 14V persists the scan-time snipe_ladder, so a row recorded by the
    # CURRENT record_alert carries real provenance. The 14U.1 reconstruction
    # caveat is therefore self-retiring: it applies to legacy rows only.
    assert out["ladder_source"] == "stored_scan_time"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_STORED
    assert out["ceiling_vs_served"] in (
        "AT_CEILING", "BELOW_CEILING", "ABOVE_RECOMPUTED_CEILING")
    # A row the live pipeline promoted is never reported as a hard failure.
    assert ssfa.CORRECTLY_BLOCKED_HARD_FAILURE not in out["classes"]
    for cls in out["classes"]:
        assert cls in ssfa.SHYNESS_CLASSES


def test_render_emits_every_report_section():
    rows = [_row(sga=_SGA_CLEAN),
            _row(ticker="BBB", tier="SNIPE_IT", capital="full_quality_allowed",
                 score=92, sga=_SGA_CLEAN),
            _row(ticker="CCC", oh={}, sga=_SGA_CLEAN)]
    text = ssfa.render_shyness_funnel_audit(
        ssfa.run_shyness_funnel_audit(rows=rows, config=CFG))
    for header in ("__TIER DISTRIBUTION__", "__FUNNEL (13 stages",
                   "__SHYNESS CLASS COUNTS__", "__TOP SHYNESS STAGES__",
                   "__EXAMPLES", "__BLIND SPOTS", "__PERSISTENCE GAPS",
                   "__OBSERVABILITY__", "__RECOMMENDED NEXT PROBES"):
        assert header in text, header
    assert "Read-only diagnostic." in text
    for stage in ssfa.STAGE_IDS:
        assert stage in text


# ===========================================================================
# Phase 14U.1 — recompute attribution truth
# ===========================================================================
#
# LAW: recomputation is evidence RECONSTRUCTION, not scan-time causality.
#
#   stored_scan_time ladder            -> may support causal ladder attribution
#   recomputed_from_persisted_row      -> evidence reconstruction only
#
# A reconstruction may say POSSIBLE_SNIPE_UNDERCALL / POSSIBLE_STARTER_UNDERCALL.
# It may NOT say the historical scanner definitely LADDER_CAPPED the row.
#
# No merge timestamp, deploy date, or scanner version inferred from alerted_at
# is used anywhere — provenance comes only from whether the row itself carries
# the ladder object.


def _stored_ladder(recommendation="SNIPE_IT", rung="SNIPER_A_PLUS"):
    """A scan-time snipe_ladder object as a future telemetry phase would persist."""
    return {
        "internal_ladder_tier": rung,
        "public_signal_tier": "SNIPER_ENTRY",
        "existing_final_tier_recommendation": recommendation,
        "capital_action_recommendation": "full_quality_allowed",
        "opportunity_lane": rung,
        "starter_grade": "NONE",
        "sniper_grade": rung,
        "base_alive": True,
        "proof_state": "PRISTINE",
        "hard_failures": [],
        "starter_blockers": [],
        "sniper_only_blockers": [],
        "soft_caps": [],
        "info_notes": [],
        "why_this_ladder_tier": "complete sequence",
    }


def test_u1_historical_starter_recomputing_sniper_is_not_a_proven_ladder_cap():
    """1 + 9 — a pre-14S.7B-style row must not be rewritten as if the new
    mechanism existed at its scan time."""
    out = ssfa.classify_row(_row(sga=_SGA_CLEAN), CFG)
    assert out["ladder_source"] == "recomputed_from_persisted_row"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_RECONSTRUCTED
    assert ssfa.LADDER_CAPPED not in out["classes"]
    assert "cannot be causally attributed" in out["why"]


def test_u1_historical_starter_retains_the_possible_snipe_undercall_signal():
    """2 — the useful review signal is preserved, not thrown away."""
    out = ssfa.classify_row(_row(sga=_SGA_CLEAN), CFG)
    assert ssfa.POSSIBLE_SNIPE_UNDERCALL in out["classes"]
    assert out["is_shy"] is True


def test_u1_historical_near_entry_recomputing_starter_is_not_a_proven_cap():
    """3 + 4 — same rule one rung down: no proven cap, undercall retained."""
    tf = {**copy.deepcopy(_TF_OK), "alignment_label": "PARTIAL",
          "operational_timeframe": {"state": "REPAIRING_IN_ZONE"}}
    out = ssfa.classify_row(
        _row(tier="NEAR_ENTRY", capital="wait_no_capital", score=80,
             tf=tf, sga=_SGA_CLEAN), CFG)
    assert out["tier"] == "NEAR_ENTRY"
    assert ssfa._rank(out["ceiling_tier"]) > ssfa._rank("NEAR_ENTRY")
    assert ssfa.LADDER_CAPPED not in out["classes"]
    assert (ssfa.POSSIBLE_STARTER_UNDERCALL in out["classes"]
            or ssfa.POSSIBLE_SNIPE_UNDERCALL in out["classes"])


def test_u1_stored_scan_time_ladder_may_emit_a_definitive_ladder_cap():
    """5 — we are fixing epistemology, not disabling the class. With real
    scan-time ladder evidence the causal attribution is legitimate."""
    row = _row(sga=_SGA_CLEAN, snipe_ladder=_stored_ladder())
    out = ssfa.classify_row(row, CFG)
    assert out["ladder_source"] == "stored_scan_time"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_STORED
    assert out["primary_class"] == ssfa.LADDER_CAPPED
    assert out["stage"] == "LADDER_ARBITRATION"
    assert "cannot be causally attributed" not in out["why"]


def test_u1_stored_ladder_seal_downgrade_still_wins_over_ladder_cap():
    """SEAL_DOWNGRADED stays definitive either way — the seal marker IS
    persisted, so that attribution always rests on scan-time evidence."""
    for ladder in (None, _stored_ladder()):
        kwargs = {"sga": _SGA_CLEAN, "seal": {"applied": True, "reason": "downgrade"}}
        if ladder is not None:
            kwargs["snipe_ladder"] = ladder
        out = ssfa.classify_row(_row(**kwargs), CFG)
        assert out["primary_class"] == ssfa.SEAL_DOWNGRADED
        assert out["stage"] == "DOWNGRADE_ONLY_SEAL"


def test_u1_clean_snipe_row_is_still_a_no_finding():
    """6 — no regression on a row sitting at its ceiling."""
    out = ssfa.classify_row(
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92,
             sga=_SGA_CLEAN), CFG)
    assert out["classes"] == []
    assert out["primary_class"] is None
    assert out["is_shy"] is False


def test_u1_above_recomputed_ceiling_still_a_recompute_limitation():
    """7 — unchanged: not over-promotion, not shyness."""
    htf = {**copy.deepcopy(_HTF_OK), "campaign_location_label": "EXTENDED_ABOVE_VALUE",
           "context_grade": "C", "context_score": 55, "weakens_long_setup": True}
    out = ssfa.classify_row(
        _row(tier="SNIPE_IT", capital="full_quality_allowed", score=92,
             htf=htf, oh=_oh(candle_truth={"event_type": "REJECTION",
                                           "closed_candle_confirms": False}),
             sga=_SGA_CLEAN), CFG)
    assert out["ceiling_vs_served"] == "ABOVE_RECOMPUTED_CEILING"
    assert out["is_shy"] is False
    assert "does not persist" in out["why"]


def test_u1_missing_floor_cleared_is_never_read_as_a_floor_failure():
    """8 — the Phase 14S.7C field did not exist on historical scans. Its
    absence must never be interpreted as a capital-floor failure. Structural
    proof: this module never inspects the field at all."""
    src = Path("src/snipe_shyness_funnel_audit.py").read_text(encoding="utf-8")
    assert "snipe_capital_floor_cleared" not in src
    out = ssfa.classify_row(_row(sga=_SGA_CLEAN), CFG)
    assert ssfa.CORRECTLY_BLOCKED_HARD_FAILURE not in out["classes"]
    # "taxonomy floor" is the TIER floor and is legitimate; what must never
    # appear is any claim about the CAPITAL floor on a historical row.
    blob = (" ".join(out["classes"]) + " " + out["why"]).lower()
    for capital_floor_claim in ("capital floor", "floor_cleared", "floor failed",
                                "floor violation", "fake tight stop"):
        assert capital_floor_claim not in blob, capital_floor_claim


def test_u1_true_hard_failure_is_still_blocked_not_called_an_undercall():
    """10 — attribution provenance must not loosen adverse evidence."""
    row = _row(tier="WAIT", capital="no_trade", score=40,
               oh=_oh(trigger_state="FAILED_RETEST",
                      alert_truth_label="FAILED_TRIGGER",
                      pullback_retest_hold={"retest_truth": "RETEST_FAILED",
                                            "hold_truth": "HOLD_FAILED"}))
    out = ssfa.classify_row(row, CFG)
    assert out["primary_class"] == ssfa.CORRECTLY_BLOCKED_HARD_FAILURE
    assert out["is_shy"] is False
    assert not any("UNDERCALL" in c for c in out["classes"])


def test_u1_hostile_rejection_remains_adverse():
    """11 — unchanged."""
    assert tax.CODE_HOSTILE not in ssfa._CLOSED_BAR_GATES
    row = _row(sga=_SGA_CLEAN,
               oh=_oh(candle_truth={"event_type": "REJECTION",
                                    "closed_candle_confirms": False,
                                    "wick_rejection": True,
                                    "body_acceptance": False}),
               candle_evidence={"candle_veto": "HOSTILE_WICK", "status": "ok"})
    assert ssfa.ONE_H_PROOF_TOO_STRICT not in _classes(row)


def test_u1_definitive_ladder_capped_count_is_not_inflated_by_recomputes():
    """The aggregate law: class_counts['LADDER_CAPPED'] holds only causally
    supported rows."""
    recomputed = [_row(ticker=f"R{i}", sga=_SGA_CLEAN) for i in range(4)]
    stored = [_row(ticker="S1", sga=_SGA_CLEAN, snipe_ladder=_stored_ladder())]
    report = ssfa.run_shyness_funnel_audit(rows=recomputed + stored, config=CFG)
    assert report["class_counts"].get(ssfa.LADDER_CAPPED) == 1
    assert report["class_counts"].get(ssfa.POSSIBLE_SNIPE_UNDERCALL) == 5


def test_u1_blind_stages_and_stage_10_partial_are_unchanged():
    """12 + 13 — no fake zeroes, and stage 10 is NOT upgraded to OBSERVABLE."""
    report = ssfa.run_shyness_funnel_audit(rows=[_row(sga=_SGA_CLEAN)], config=CFG)
    by_id = {s["stage"]: s for s in report["stages"]}
    assert by_id["LADDER_ARBITRATION"]["observability"] == ssfa.PARTIAL
    for stage in report["stages"]:
        if stage["observability"] == ssfa.NOT_PERSISTED:
            assert stage["shy_rows_attributed"] is None, stage["stage"]
    assert {b["cls"] for b in report["blind_spots"]} == set(ssfa.UNOBSERVABLE_CLASSES)


def test_u1_attribution_is_never_inferred_from_a_calendar():
    """No merge-time constant, no deploy date, no version guessed from
    alerted_at. Provenance comes only from the row's own ladder object."""
    src = Path("src/snipe_shyness_funnel_audit.py").read_text(encoding="utf-8")
    for forbidden in ("datetime", "merge_", "deployed_at", "release_", "version_boundary"):
        assert forbidden not in src, forbidden
    early = ssfa.classify_row(_row(sga=_SGA_CLEAN, alerted_at="2020-01-01T00:00:00"), CFG)
    late = ssfa.classify_row(_row(sga=_SGA_CLEAN, alerted_at="2099-01-01T00:00:00"), CFG)
    assert early["ladder_attribution"] == late["ladder_attribution"]
    assert early["classes"] == late["classes"]


def test_u1_json_exposes_attribution_and_stays_sanitized(tmp_path):
    """15 — the new field is whitelisted; no secrets leak."""
    state = {"tickers": {"AAA": {"alert_history": [_row(sga=_SGA_CLEAN)]}},
             "meta": {"total_alerts": 1}}
    path = tmp_path / "alert_history.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    cfg = {**CFG, "state": {**CFG["state"], "state_file": str(path)}}
    out = audit_access.run_auditshy(cfg, "json", user_id="4242")
    example = out["json"]["examples"][0]
    assert example["ladder_attribution"] == ssfa.ATTRIBUTION_RECONSTRUCTED
    assert set(example) <= set(ssfa._EXAMPLE_JSON_KEYS)
    blob = json.dumps(out["json"])
    for secret in ("1497532086335311883", "1497532177359962112", "allowed_user_ids",
                   str(path)):
        assert secret not in blob, secret

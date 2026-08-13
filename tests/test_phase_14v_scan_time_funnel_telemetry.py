"""Phase 14V — scan-time funnel telemetry & decision ledger.

14V OBSERVES. It does not judge, promote, downgrade, reroute, change candidate
admission, or add a single API call.

LAWS under test:
  - Architecture outranks assumption. This scanner has ONE same-signal
    suppression path (`duplicate_suppressed`, the cooldown branch).
    `dedup_key` is identity state and is never a suppression gate, so
    DEDUP_SUPPRESSED is never fabricated from a key match.
  - Telemetry has an isolated failure domain: its own file, written
    atomically. Telemetry corruption != alert-history corruption, and a
    telemetry fault never touches tier, capital, routing, suppression, or
    delivery.
  - No fake zeroes, no retroactive upgrading of historical rows.
  - telemetry_scope = run_scan_pipeline only; manual run_analyze is not a
    market scan funnel and gets no fabricated summary.
"""

import copy
import json
import tempfile
from pathlib import Path

from src import audit_access
from src import scan_telemetry as tlm
from src import snipe_confirmed_seal as seal_mod
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as lad
from src import snipe_shyness_funnel_audit as ssfa
from src import state_store


def _cfg(tmp_path, **over):
    cfg = {
        "tiers": {"snipe_it": {"min_score": 85, "min_rr": 3.0,
                               "min_risk_distance_pct": 0.35},
                  "starter": {"min_score": 75, "min_rr": 3.0}},
        "prefilter": {"max_claude_candidates_per_scan": 30, "prefilter_min_score": 55},
        "state": {"max_memory_entries": 500, "cooldown_minutes": 60,
                  "state_file": str(tmp_path / "alert_history.json")},
        "telemetry": {"max_scan_summaries": 300, "max_decision_traces": 9000},
        "discord": {"snipe_channel_id": 1497532086335311883},
    }
    cfg.update(over)
    return cfg


def _pf_row(ticker, score, eligible=True, reason=None, vetoes=None, status="OK"):
    return {"ticker": ticker, "data_status": status, "prefilter_score": score,
            "veto_flags": vetoes or [], "eligible_for_claude": eligible,
            "rejection_reason": reason, "key_features": {}}


def _pf_result(n_eligible=70, n_rejected=40, cap=30):
    ranked = [_pf_row(f"T{i:03d}", 100 - i) for i in range(n_eligible)]
    rejected = ([_pf_row(f"V{i:03d}", 20, eligible=False,
                         reason="hard_veto: VETO_NO_CLEAR_STRUCTURE",
                         vetoes=["VETO_NO_CLEAR_STRUCTURE"]) for i in range(n_rejected // 2)]
                + [_pf_row(f"S{i:03d}", 40, eligible=False,
                           reason="score_below_floor: 40 < 55") for i in range(n_rejected // 2)])
    return {"all_results": ranked + rejected, "ranked_results": ranked,
            "claude_candidates": ranked[:cap],
            "board_summary": {"total_tickers_input": n_eligible + n_rejected,
                              "total_rejected_by_data_quality": 0,
                              "total_rejected_by_veto": n_rejected,
                              "total_above_prefilter_min_score": n_eligible,
                              "total_claude_candidates": cap}}


def _summary(tmp_path, **over):
    cfg = _cfg(tmp_path)
    kw = dict(scan_id="scan_20260811_120000_aaaaaa", scan_timestamp="2026-08-11T12:00:00",
              tickers_input=814, data_failures=14, pf_result=_pf_result(), config=cfg,
              final_tier_counts={"SNIPE_IT": 2, "STARTER": 5, "NEAR_ENTRY": 9, "WAIT": 14},
              ladder_counts={"SNIPER_A": 2, "STARTER_A": 5, "WATCH_C": 9, "PASS": 14},
              base_tier_counts={"NEAR_ENTRY": 16, "STARTER": 4, "WAIT": 10},
              check_alert_reason_counts={"new_signal": 6, "duplicate_suppressed": 3,
                                         "wait_no_alert": 14},
              delivery={"send_alert_called": 16, "sent": 6, "skipped": 9, "failed": 1},
              analysis={"admitted": 30, "claude_success": 30, "claude_failed": 0,
                        "claude_rate_limited": 0, "tiering_failed": 0, "judged": 30})
    kw.update(over)
    return tlm.build_scan_summary(**kw)


# ---- live tiering result through the REAL organs ---------------------------

def _live_result(tier="NEAR_ENTRY"):
    sig = {"ticker": "EEE", "tier": tier, "capital_action": "wait_no_capital",
           "discord_channel": "#near-entry", "reason": "Setup.", "next_action": "Act.",
           "retest_status": "confirmed", "hold_status": "confirmed",
           "structure_event": "bos", "trigger_level": 100.0, "invalidation_level": 96.5,
           "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
           "overhead_status": "clear", "scan_price": 101.0, "targets": [110.0, 118.0],
           "missing_conditions": [], "risk_realism_state": "healthy"}
    oh = {"status": "ENABLED", "trigger_state": "TRIGGER_LIVE",
          "alert_truth_label": "CONFIRMED_TRIGGER", "score": 90, "data_freshness": "FRESH",
          "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID",
                                   "hold_truth": "HOLD_CONFIRMED"},
          "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True},
          "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
          "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
          "invalidation": {"clear": True}}
    return {"final_tier": tier, "capital_action": "wait_no_capital",
            "final_discord_channel": "#near-entry", "safe_for_alert": True, "score": 90,
            "final_signal": sig, "one_hour_entry": oh,
            "timeframe_alignment": {"alignment_label": "FULL_STACK_ALIGNED",
                                    "status": "ENABLED",
                                    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
                                    "operational_timeframe": {"state": "LOCATION_VALID"}},
            "higher_timeframe_context": {"weekly_campaign_state": "HTF_CONTINUATION",
                                         "blocks_snipe_contextually": False,
                                         "monthly_bias": "BULLISH", "data_status": "OK"},
            "candle_evidence": {"status": "ok", "candle_family": "RETEST_HOLD",
                                "candle_veto": "OPEN_ONLY", "next_candle_verdict": "UNKNOWN",
                                "level_reaction": "HELD"}}


def _backed_summary(scan_id="s1", **over):
    """A scan summary carrying real Layer-1 stage evidence.

    Phase 14V.1B: a bare {"scan_id": ...} marker proves nothing about any
    stage — evidence must belong to the stage it upgrades.
    """
    return {
        "schema_version": tlm.SCHEMA_VERSION, "scan_id": scan_id,
        "universe": {"input_count": 814, "data_stage_success": 800,
                     "data_stage_failure": 14},
        "prefilter": {"eligible_count": 70, "rejected_count": 40,
                      "primary_rejection_reason_counts": {"hard_veto": 40},
                      "veto_flag_counts": {}, "candidate_cap": 30,
                      "admitted_count": 30, "cutoff_rank": 30, "cutoff_score": 71},
        "analysis": {"admitted": 30, "claude_success": 30, "judged": 24},
        "suppression": {"check_alert_reason_counts": {"new_signal": 24},
                        "cooldown_suppressed": 0,
                        "dedup_key_suppression_supported": False},
        **over,
    }


def _row_for_scan(scan_id, ticker="AAA"):
    """A persisted alert_history row belonging to a specific scan."""
    live = _live_result()
    return {"ticker": ticker, "scan_id": scan_id, "alerted_at": "2026-08-11T12:00:00",
            "tier": "STARTER", "capital_action": "starter_only", "score": 88,
            "trigger_level": 100.0, "invalidation_level": 96.5, "risk_reward": 3.4,
            "scan_price": 101.0, "targets": [108, 115], "risk_distance_pct": 3.5,
            "invalidation_condition": "1H close below 96.5",
            "structure_event": "bos", "retest_status": "confirmed",
            "hold_status": "confirmed", "overhead_status": "clear",
            "one_hour_entry": live["one_hour_entry"],
            "timeframe_alignment": live["timeframe_alignment"],
            "higher_timeframe_context": live["higher_timeframe_context"]}


def _piped(tr, cfg):
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("EEE", tr, {}, cfg)
    lad.apply_ladder_arbitration(tr, cfg)
    seal_mod.seal_snipe_confirmed_consistency(tr, cfg)
    return tr


# ===========================================================================
# 1-5 — Layer 1 scan summary
# ===========================================================================

def test_1_scan_summary_records_universe_input_count(tmp_path):
    s = _summary(tmp_path)
    assert s["universe"]["input_count"] == 814
    assert s["universe"]["data_stage_failure"] == 14
    assert s["universe"]["data_stage_success"] == 800


def test_2_prefilter_rejection_histogram_persists(tmp_path):
    s = _summary(tmp_path)
    hist = s["prefilter"]["primary_rejection_reason_counts"]
    assert hist["hard_veto"] == 20
    assert hist["score_below_floor"] == 20
    assert s["prefilter"]["veto_flag_counts"]["VETO_NO_CLEAR_STRUCTURE"] == 20
    assert s["prefilter"]["rejected_count"] == 40
    # the primary histogram reconciles against rejected_count; the multi-label
    # veto histogram is deliberately kept separate
    assert sum(hist.values()) == s["prefilter"]["rejected_count"]


def test_3_top30_admitted_count_and_cutoff_persist(tmp_path):
    s = _summary(tmp_path)
    assert s["prefilter"]["candidate_cap"] == 30
    assert s["prefilter"]["admitted_count"] == 30
    assert s["prefilter"]["cutoff_rank"] == 30
    assert s["prefilter"]["cutoff_score"] == 71          # ranked[29] == 100-29


def test_3b_cutoff_is_null_when_the_cap_did_not_bind(tmp_path):
    """No fake cutoff when the cap excluded nothing — including ranked == cap."""
    s = _summary(tmp_path, pf_result=_pf_result(n_eligible=12, cap=12))
    assert s["prefilter"]["admitted_count"] == 12
    assert s["prefilter"]["cutoff_rank"] is None
    assert s["prefilter"]["cutoff_score"] is None
    # M3: ranked == cap excluded nothing, so there is no cutoff either
    exact = _summary(tmp_path, pf_result=_pf_result(n_eligible=30, n_rejected=0, cap=30))
    assert exact["prefilter"]["cutoff_rank"] is None
    assert exact["prefilter"]["cutoff_score"] is None


def test_4_near_cut_sample_is_ranks_31_to_60_and_bounded():
    pairs = tlm.near_cut_slice(_pf_result()["ranked_results"])
    assert len(pairs) == 30
    assert [r for _, r in pairs] == list(range(31, 61))
    assert pairs[0][0]["ticker"] == "T030"
    traces = [tlm.build_near_cut_trace("scan_x", r, rank) for r, rank in pairs]
    assert all(t["trace_kind"] == "near_cut" for t in traces)
    assert all(t["pipeline"]["admitted_to_deep_analysis"] is False for t in traces)


def test_5_near_cut_telemetry_triggers_no_analysis_of_any_kind():
    """Copied from ranked_results only — no Claude, no market data, no strategy.

    AST-based, not substring-based: `eligible_for_claude` is a prefilter FIELD
    the ledger reads, and a naive text match would confuse reading a field with
    making a call.
    """
    import ast
    tree = ast.parse(Path("src/scan_telemetry.py").read_text(encoding="utf-8"))
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                called.add(f.attr)
            elif isinstance(f, ast.Name):
                called.add(f.id)
    for forbidden in ("async_claude_scan", "claude_call", "batch_download", "enrich",
                      "prefilter", "validate", "apply_ladder_arbitration",
                      "build_snipe_gate_audit", "seal_snipe_confirmed_consistency",
                      "send_alert", "check_alert", "record_alert", "save", "get", "post"):
        if forbidden == "get":
            continue                      # dict .get is not an HTTP call
        assert forbidden not in called, forbidden

    # Behavioural proof: near-cut traces are pure copies of ranked_results.
    ranked = _pf_result()["ranked_results"]
    before = copy.deepcopy(ranked)
    pairs = tlm.near_cut_slice(ranked)
    traces = [tlm.build_near_cut_trace("s", r, rank) for r, rank in pairs]
    assert ranked == before                              # nothing re-evaluated
    assert all(t["pipeline"]["claude_analyzed"] is False for t in traces)


# ===========================================================================
# 6-13 — Layer 2 decision traces + the three closed persistence gaps
# ===========================================================================

def test_6_analyzed_candidate_base_tier_persists(tmp_path):
    tr = _piped(_live_result(), _cfg(tmp_path))
    t = tlm.build_decision_trace("s1", "EEE", _pf_row("EEE", 90), 7, tr,
                                 base_final_tier="NEAR_ENTRY")
    assert t["judgment"]["base_final_tier"] == "NEAR_ENTRY"
    assert t["judgment"]["final_tier"] == tr["final_tier"]
    assert t["pipeline"]["prefilter_rank"] == 7


def test_7_scan_time_snipe_ladder_persists_with_stored_provenance(tmp_path):
    tr = _piped(_live_result(), _cfg(tmp_path))
    t = tlm.build_decision_trace("s1", "EEE", {}, 1, tr)
    assert t["ladder_source"] == "stored_scan_time"
    assert t["snipe_ladder"]["internal_ladder_tier"] in lad.LADDER_TIERS


def test_8_and_9_sniper_and_starter_grades_persist_distinctly(tmp_path):
    cfg = _cfg(tmp_path)
    plus = tlm.compact_ladder(_piped(_live_result(), cfg)["snipe_ladder"])
    assert plus["internal_ladder_tier"] == lad.SNIPER_A_PLUS

    soft = _live_result()
    soft["one_hour_entry"]["location_realism"]["label"] = "ACCEPTABLE_BUT_NOT_IDEAL"
    a = tlm.compact_ladder(_piped(soft, cfg)["snipe_ladder"])
    assert a["internal_ladder_tier"] == lad.SNIPER_A
    assert a["internal_ladder_tier"] != plus["internal_ladder_tier"]

    forming = _live_result()
    forming["one_hour_entry"]["trigger_state"] = "RETEST_IN_PROGRESS"
    forming["one_hour_entry"]["alert_truth_label"] = "FORMING_TRIGGER"
    sa = tlm.compact_ladder(_piped(forming, cfg)["snipe_ladder"])
    softer = _live_result()
    softer["final_signal"]["hold_status"] = "partial"
    softer["one_hour_entry"]["trigger_state"] = "RETEST_IN_PROGRESS"
    softer["one_hour_entry"]["alert_truth_label"] = "FORMING_TRIGGER"
    softer["one_hour_entry"]["pullback_retest_hold"]["hold_truth"] = "HOLD_FORMING"
    sb = tlm.compact_ladder(_piped(softer, cfg)["snipe_ladder"])
    assert sa["internal_ladder_tier"] == lad.STARTER_A
    assert sb["internal_ladder_tier"] == lad.STARTER_B


def test_10_and_11_floor_cleared_and_direct_decision_persist(tmp_path):
    tr = _piped(_live_result(), _cfg(tmp_path))
    compact = tlm.compact_ladder(tr["snipe_ladder"])
    assert compact["snipe_capital_floor_cleared"] is True
    assert "DIRECT_NEAR_ENTRY_TO_SNIPE_ALLOWED" in compact["direct_snipe_decision"]


def test_12_and_13_invalidation_condition_and_candle_evidence_persist(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, cfg, "scan_x")
    row = state["tickers"]["EEE"]["alert_history"][-1]
    assert row["invalidation_condition"] == "1H close below 96.5"
    assert row["candle_evidence"]["candle_veto"] == "OPEN_ONLY"
    assert row["snipe_ladder"]["internal_ladder_tier"] == lad.SNIPER_A_PLUS


def test_14_to_17_existing_snapshots_do_not_regress(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, cfg, "scan_x")
    row = state["tickers"]["EEE"]["alert_history"][-1]
    assert isinstance(row["one_hour_entry"], dict)
    assert isinstance(row["timeframe_alignment"], dict)
    assert isinstance(row["snipe_gate_audit"], dict)
    assert "snipe_confirmed_seal" in row


# ===========================================================================
# 18-23 — every disappearing delivery path is captured
# ===========================================================================

def test_18_wait_row_can_persist_even_though_no_alert_is_sent(tmp_path):
    tr = _live_result("WAIT")
    tr["final_tier"] = "WAIT"
    tr["safe_for_alert"] = False
    t = tlm.build_decision_trace(
        "s1", "EEE", {}, 4, tr,
        dedup_decision={"should_alert": False, "reason": "wait_no_alert",
                        "dedup_key": "EEE|WAIT|100.00|96.50"},
        send_result={"sent": False, "skipped_reason": "wait_no_alert"})
    assert t["judgment"]["final_tier"] == "WAIT"
    assert t["suppression"]["check_alert_reason"] == "wait_no_alert"
    assert t["suppression"]["cooldown_suppressed"] is False
    assert t["delivery"]["sent"] is False


def test_19_and_20_cooldown_suppressed_row_persists_as_telemetry(tmp_path):
    t = tlm.build_decision_trace(
        "s1", "EEE", {}, 2, _live_result(),
        dedup_decision={"should_alert": False, "reason": "duplicate_suppressed",
                        "dedup_key": "EEE|STARTER|100.00|96.50"},
        send_result={"sent": False, "skipped_reason": "duplicate_suppressed"})
    assert t["suppression"]["check_alert_reason"] == "duplicate_suppressed"
    assert t["suppression"]["cooldown_suppressed"] is True
    assert t["suppression"]["should_alert"] is False


def test_21_routing_none_row_persists_as_telemetry():
    t = tlm.build_decision_trace(
        "s1", "EEE", {}, 3, _live_result(),
        dedup_decision={"should_alert": True, "reason": "new_signal"},
        send_result={"sent": False, "skipped_reason": "channel_not_configured",
                     "error_type": "routing_failure"})
    assert t["delivery"]["skipped_reason"] == "channel_not_configured"
    assert t["delivery"]["error_type"] == "routing_failure"
    assert t["suppression"]["cooldown_suppressed"] is False


def test_22_and_23_send_failure_and_sent_alert_persist():
    fail = tlm.build_decision_trace("s1", "E", {}, 1, _live_result(),
                                    send_result={"sent": False, "error_type": "discord_error"})
    sent = tlm.build_decision_trace("s1", "E", {}, 1, _live_result(),
                                    send_result={"sent": True})
    assert fail["delivery"]["sent"] is False and fail["delivery"]["error_type"] == "discord_error"
    assert sent["delivery"]["sent"] is True


# ===========================================================================
# 24-26 + atomic storage 1-9 — isolated failure domain
# ===========================================================================

def test_atomic_write_uses_same_directory_temp_then_replace(tmp_path):
    cfg = _cfg(tmp_path)
    assert tlm.write_scan_telemetry(cfg, _summary(tmp_path), []) is True
    target = tlm.telemetry_path(cfg)
    assert target.exists()
    assert target.parent == tmp_path
    assert not list(tmp_path.glob("*.tmp.*")), "orphan temp file left behind"


def test_serialization_failure_leaves_prior_telemetry_intact(tmp_path):
    cfg = _cfg(tmp_path)
    tlm.write_scan_telemetry(cfg, _summary(tmp_path), [])
    before = tlm.telemetry_path(cfg).read_text(encoding="utf-8")

    class _Unserializable:
        def __repr__(self):
            raise RuntimeError("cannot repr")

    ok = tlm.write_scan_telemetry(cfg, {"scan_id": float("nan")}, [])
    assert ok is False
    assert tlm.telemetry_path(cfg).read_text(encoding="utf-8") == before


def test_write_failure_leaves_prior_telemetry_intact(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    tlm.write_scan_telemetry(cfg, _summary(tmp_path), [])
    before = tlm.telemetry_path(cfg).read_text(encoding="utf-8")

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(tlm.os, "replace", _boom)
    assert tlm.write_scan_telemetry(cfg, _summary(tmp_path), []) is False
    assert tlm.telemetry_path(cfg).read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.tmp.*")), "orphan temp file left behind"


def test_24_to_26_telemetry_failure_cannot_touch_judgment_or_history(tmp_path, monkeypatch):
    """A telemetry fault changes no strategy field, and cannot corrupt or even
    read-modify alert_history.json."""
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, cfg, "scan_x")
    state_store.save(state, cfg)
    history_before = Path(cfg["state"]["state_file"]).read_text(encoding="utf-8")
    strategy_before = {k: copy.deepcopy(tr[k]) for k in
                       ("final_tier", "capital_action", "final_discord_channel",
                        "safe_for_alert", "score")}

    monkeypatch.setattr(tlm.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert tlm.write_scan_telemetry(cfg, _summary(tmp_path), []) is False

    assert Path(cfg["state"]["state_file"]).read_text(encoding="utf-8") == history_before
    for k, v in strategy_before.items():
        assert tr[k] == v


def test_corrupt_telemetry_file_is_survivable_and_isolated(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg["state"]["state_file"]).parent.mkdir(parents=True, exist_ok=True)
    tlm.telemetry_path(cfg).write_text("{not json at all", encoding="utf-8")
    assert tlm.load_ledger(cfg) == {"schema_version": tlm.SCHEMA_VERSION,
                                    "scan_summaries": [], "decision_traces": []}
    assert tlm.write_scan_telemetry(cfg, _summary(tmp_path), []) is True


# ===========================================================================
# Retention
# ===========================================================================

def test_36_retention_bounds_are_enforced_oldest_first(tmp_path):
    cfg = _cfg(tmp_path, telemetry={"max_scan_summaries": 5, "max_decision_traces": 7})
    for i in range(9):
        tlm.write_scan_telemetry(cfg, {"scan_id": f"s{i}"},
                                 [{"scan_id": f"s{i}", "ticker": f"T{i}"}, ])
    ledger = tlm.load_ledger(cfg)
    assert len(ledger["scan_summaries"]) == 5
    assert len(ledger["decision_traces"]) == 7
    assert [s["scan_id"] for s in ledger["scan_summaries"]] == [f"s{i}" for i in range(4, 9)]
    assert ledger["schema_version"] == tlm.SCHEMA_VERSION


def test_retention_defaults_match_the_approved_policy(tmp_path):
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["telemetry"]["max_scan_summaries"] == 300
    assert cfg["telemetry"]["max_decision_traces"] == 9000
    assert tlm._DEFAULT_MAX_SCAN_SUMMARIES == 300
    assert tlm._DEFAULT_MAX_DECISION_TRACES == 9000


def test_malformed_historical_items_are_dropped_not_fatal(tmp_path):
    cfg = _cfg(tmp_path)
    tlm.telemetry_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    tlm.telemetry_path(cfg).write_text(json.dumps(
        {"schema_version": "14V.1", "scan_summaries": [{"scan_id": "ok"}, "junk", 42],
         "decision_traces": ["bad", {"ticker": "T"}]}), encoding="utf-8")
    ledger = tlm.load_ledger(cfg)
    assert ledger["scan_summaries"] == [{"scan_id": "ok"}]
    assert ledger["decision_traces"] == [{"ticker": "T"}]


def test_missing_telemetry_file_starts_cleanly(tmp_path):
    assert tlm.load_ledger(_cfg(tmp_path))["scan_summaries"] == []


# ===========================================================================
# 34-35 + 38-39 — determinism, secrets, purity, invariants
# ===========================================================================

def test_34_serialization_is_deterministic_and_json_safe(tmp_path):
    s = _summary(tmp_path)
    assert json.dumps(s, sort_keys=True, allow_nan=False) == \
        json.dumps(copy.deepcopy(s), sort_keys=True, allow_nan=False)


def test_35_no_secrets_or_config_dumps_in_telemetry(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    blob = json.dumps({"s": _summary(tmp_path),
                       "t": tlm.build_decision_trace("s", "E", {}, 1, tr)})
    for secret in ("1497532086335311883", "ANTHROPIC", "DISCORD_TOKEN",
                   "allowed_user_ids", "state_file", str(tmp_path)):
        assert secret not in blob, secret


def test_38_telemetry_never_mutates_its_inputs(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    before_tr = copy.deepcopy(tr)
    pf = _pf_result()
    before_pf = copy.deepcopy(pf)
    tlm.build_decision_trace("s", "E", pf["ranked_results"][0], 1, tr,
                             {"reason": "new_signal"}, {"sent": True})
    tlm.build_scan_summary("s", "t", 10, 1, pf, cfg)
    assert tr == before_tr
    assert pf == before_pf


def test_39_candidate_cap_remains_exactly_30():
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_40_telemetry_module_adds_no_api_surface():
    src = Path("src/scan_telemetry.py").read_text(encoding="utf-8")
    import ast
    tree = ast.parse(src)
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert imported <= {"json", "logging", "os", "pathlib"}, imported


# ===========================================================================
# 41-43 — suppression truth: no fabricated dedup mechanism
# ===========================================================================

def test_41_duplicate_suppressed_maps_only_to_cooldown_suppression():
    for reason, expected in (("duplicate_suppressed", True), ("new_signal", False),
                             ("tier_improved", False), ("trigger_changed", False),
                             ("invalidation_changed", False), ("cooldown_expired", False),
                             ("manual_override", False), ("wait_no_alert", False),
                             ("unsafe_for_alert", False)):
        t = tlm.build_decision_trace("s", "E", {}, 1, _live_result(),
                                     dedup_decision={"reason": reason, "should_alert": False})
        assert t["suppression"]["cooldown_suppressed"] is expected, reason
        assert t["suppression"]["check_alert_reason"] == reason   # stored verbatim


def test_42_equal_dedup_key_alone_never_creates_a_suppression_event():
    """A dedup_key match is identity state, not a decision. Two rows sharing a
    key but allowed to alert must record no suppression."""
    key = "EEE|STARTER|100.00|96.50"
    for reason in ("new_signal", "tier_improved"):
        t = tlm.build_decision_trace(
            "s", "E", {}, 1, _live_result(),
            dedup_decision={"reason": reason, "should_alert": True, "dedup_key": key})
        assert t["suppression"]["dedup_key"] == key
        assert t["suppression"]["cooldown_suppressed"] is False
        assert t["suppression"]["should_alert"] is True


def test_43_dedup_class_survives_in_vocabulary_but_is_never_emitted(tmp_path):
    """DEDUP_SUPPRESSED stays in the closed 20-member vocabulary for
    compatibility, but the current scanner has no mechanism that produces it —
    and the telemetry says so as a capability fact, not a zero and not a blind
    unknown."""
    assert ssfa.DEDUP_SUPPRESSED in ssfa.SHYNESS_CLASSES
    s = _summary(tmp_path)
    assert s["suppression"]["dedup_key_suppression_supported"] is False
    assert s["suppression"]["cooldown_suppressed"] == 3
    t = tlm.build_decision_trace("s", "E", {}, 1, _live_result(),
                                 dedup_decision={"reason": "duplicate_suppressed"})
    assert t["suppression"]["dedup_key_suppression_supported"] is False


def test_43b_check_alert_vocabulary_is_stored_verbatim_not_renamed(tmp_path):
    s = _summary(tmp_path)
    assert s["suppression"]["check_alert_reason_counts"] == {
        "new_signal": 6, "duplicate_suppressed": 3, "wait_no_alert": 14}


# ===========================================================================
# 44-47 — 14U integration: new observability, no historical rewriting
# ===========================================================================

def test_44_and_45_stage_12_observability_is_telemetry_backed_only():
    legacy = ssfa.run_shyness_funnel_audit(rows=[], config={})
    by_id = {s["stage"]: s for s in legacy["stages"]}
    assert by_id["DEDUP_AND_COOLDOWN"]["observability"] == ssfa.NOT_PERSISTED
    assert by_id["DEDUP_AND_COOLDOWN"]["shy_rows_attributed"] is None
    assert legacy["telemetry_scans"] == 0

    # H3: a telemetry summary alone no longer upgrades anything — a row from
    # that scan must actually be present in the window.
    row = _row_for_scan("s1")
    backed = ssfa.run_shyness_funnel_audit(
        rows=[row], config={},
        telemetry={"scan_summaries": [_backed_summary("s1")], "decision_traces": []})
    b = {s["stage"]: s for s in backed["stages"]}
    assert backed["telemetry_scans"] == 1
    assert backed["telemetry_backed_rows"] == 1 and backed["legacy_rows"] == 0
    for stage in ssfa.TELEMETRY_BACKED_STAGES:
        assert b[stage]["observability"] == ssfa.OBSERVABLE, stage
        assert b[stage]["telemetry_backed"] is True
    # stages 14V does not record are untouched
    assert b["LADDER_ARBITRATION"]["observability"] == ssfa.PARTIAL
    assert b["LADDER_ARBITRATION"]["telemetry_backed"] is False


def test_46_legacy_row_without_stored_ladder_stays_reconstructed():
    legacy_row = {"ticker": "OLD", "scan_id": "scan_old", "alerted_at": "2026-07-01T12:00:00",
                  "tier": "STARTER", "capital_action": "starter_only", "score": 88,
                  "trigger_level": 100.0, "invalidation_level": 96.5, "risk_reward": 3.4,
                  "scan_price": 101.0, "targets": [108, 115], "risk_distance_pct": 3.5,
                  "structure_event": "bos", "retest_status": "confirmed",
                  "hold_status": "confirmed", "overhead_status": "clear",
                  "one_hour_entry": _live_result()["one_hour_entry"],
                  "timeframe_alignment": _live_result()["timeframe_alignment"],
                  "higher_timeframe_context": _live_result()["higher_timeframe_context"]}
    out = ssfa.classify_row(legacy_row, {})
    assert out["ladder_source"] == "recomputed_from_persisted_row"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_RECONSTRUCTED
    assert ssfa.LADDER_CAPPED not in out["classes"]


def test_47_new_stored_ladder_row_becomes_stored_scan_time(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, cfg, "scan_new")
    row = state["tickers"]["EEE"]["alert_history"][-1]
    out = ssfa.classify_row(row, cfg)
    assert out["ladder_source"] == "stored_scan_time"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_STORED
    assert out["recompute_confidence"] == ssfa.HIGH_CONFIDENCE


# ===========================================================================
# 49 — manual run_analyze creates no fake scan funnel
# ===========================================================================

def test_49_run_analyze_writes_no_scan_funnel_telemetry():
    """telemetry_scope = run_scan_pipeline. Manual single-ticker analysis never
    passed through universe admission, prefilter, or the candidate cap, so a
    scan-funnel summary for it would be fabricated."""
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    analyze = src[src.index("async def run_analyze"):]
    for token in ("scan_telemetry.", "_tlm_"):
        assert token not in analyze, f"run_analyze must stay untelemetered: {token}"
    scan = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    assert "scan_telemetry.write_scan_telemetry" in scan


def test_49b_telemetry_scope_is_declared_in_the_summary(tmp_path):
    assert _summary(tmp_path)["telemetry_scope"] == "run_scan_pipeline"


# ===========================================================================
# 50 — storage footprint projection
# ===========================================================================

def test_50_projected_steady_state_footprint_is_within_bound(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    summary_b = len(json.dumps(_summary(tmp_path)))
    admitted_b = len(json.dumps(tlm.build_decision_trace(
        "scan_20260811_120000_aaaaaa", "EEE", _pf_row("EEE", 90), 7, tr,
        {"should_alert": True, "reason": "new_signal", "dedup_key": "EEE|SNIPE_IT|100.00|96.50"},
        {"sent": True}, base_final_tier="NEAR_ENTRY")))
    near_b = len(json.dumps(tlm.build_near_cut_trace(
        "scan_20260811_120000_aaaaaa", _pf_row("T030", 70), 31)))
    trace_b = (admitted_b + near_b) / 2          # traces are ~50/50 admitted vs near-cut
    projected_mb = (300 * summary_b + 16000 * trace_b) / (1024 * 1024)
    assert projected_mb <= 25.0, f"projected {projected_mb:.1f} MB exceeds the 25 MB bound"


# ===========================================================================
# LOAD-BEARING — telemetry-enabled vs telemetry-disabled strategy equality
# ===========================================================================

_STRATEGY_FIELDS = ("final_tier", "capital_action", "final_discord_channel",
                    "safe_for_alert", "score")


def _strategy_fingerprint(tr):
    """Everything a trader's money depends on, plus the ladder basket."""
    fp = {k: tr.get(k) for k in _STRATEGY_FIELDS}
    sig = tr.get("final_signal") or {}
    fp["signal_tier"] = sig.get("tier")
    fp["signal_capital"] = sig.get("capital_action")
    fp["signal_channel"] = sig.get("discord_channel")
    ladder = tr.get("snipe_ladder") or {}
    fp["ladder_tier"] = ladder.get("internal_ladder_tier")
    fp["floor_cleared"] = ladder.get("snipe_capital_floor_cleared")
    return fp


def test_no_strategy_mutation_telemetry_on_versus_off(tmp_path):
    """Identical deterministic fixtures, telemetry OFF vs ON. Every strategy
    output must be identical. If any differs, the phase FAILS."""
    cfg = _cfg(tmp_path)

    baselines = {}
    for name, mutate in (
        ("pristine", lambda t: t),
        ("soft_cap", lambda t: t["one_hour_entry"]["location_realism"]
                                .__setitem__("label", "ACCEPTABLE_BUT_NOT_IDEAL") or t),
        ("forming", lambda t: (t["one_hour_entry"].__setitem__("trigger_state",
                                                               "RETEST_IN_PROGRESS"),
                               t["one_hour_entry"].__setitem__("alert_truth_label",
                                                               "FORMING_TRIGGER"))[0] or t),
        ("failed", lambda t: (t["one_hour_entry"].__setitem__("trigger_state",
                                                              "FAILED_RETEST"),
                              t["one_hour_entry"]["pullback_retest_hold"]
                               .__setitem__("retest_truth", "RETEST_FAILED"))[0] or t),
    ):
        # OFF: no telemetry call at all
        off = _piped(mutate(_live_result()), cfg)
        baselines[name] = _strategy_fingerprint(off)

        # ON: identical fixture, with every telemetry projection exercised
        on = _piped(mutate(_live_result()), cfg)
        tlm.build_decision_trace("s", "EEE", _pf_row("EEE", 90), 3, on,
                                 {"should_alert": True, "reason": "new_signal"},
                                 {"sent": True}, base_final_tier="NEAR_ENTRY")
        tlm.compact_ladder(on.get("snipe_ladder"))
        tlm.compact_candle_evidence(on.get("candle_evidence"))
        tlm.write_scan_telemetry(cfg, _summary(tmp_path), [])

        assert _strategy_fingerprint(on) == baselines[name], name


def test_telemetry_write_failure_leaves_judgment_and_delivery_untouched(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    before = _strategy_fingerprint(tr)
    monkeypatch.setattr(tlm.os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert tlm.write_scan_telemetry(cfg, _summary(tmp_path), []) is False
    assert _strategy_fingerprint(tr) == before


def test_end_to_end_scan_path_is_reconstructible_from_telemetry(tmp_path):
    """universe -> prefilter -> top30 -> analysis -> base tier -> 1H -> HTF ->
    gate -> ladder SNIPER_A_PLUS -> final SNIPE_IT -> dedup -> delivery, all
    recoverable from the ledger, with the scan itself untouched."""
    cfg = _cfg(tmp_path)
    pf = _pf_result()
    tr = _piped(_live_result(), cfg)
    fingerprint = _strategy_fingerprint(tr)

    traces = [tlm.build_near_cut_trace("scan_e2e", r, rank)
              for r, rank in tlm.near_cut_slice(pf["ranked_results"])]
    traces.append(tlm.build_decision_trace(
        "scan_e2e", "EEE", pf["ranked_results"][0], 1, tr,
        {"should_alert": True, "reason": "new_signal",
         "dedup_key": "EEE|SNIPE_IT|100.00|96.50"},
        {"sent": True}, base_final_tier="NEAR_ENTRY"))
    summary = tlm.build_scan_summary(
        "scan_e2e", "2026-08-11T12:00:00", 814, 14, pf, cfg,
        final_tier_counts={"SNIPE_IT": 1}, ladder_counts={"SNIPER_A_PLUS": 1},
        base_tier_counts={"NEAR_ENTRY": 1},
        check_alert_reason_counts={"new_signal": 1},
        delivery={"send_alert_called": 1, "sent": 1, "skipped": 0, "failed": 0},
        analysis={"admitted": 30, "claude_success": 30, "judged": 1})
    assert tlm.write_scan_telemetry(cfg, summary, traces) is True

    led = tlm.load_ledger(cfg)
    s = led["scan_summaries"][-1]
    assert s["universe"]["input_count"] == 814                      # stage 1
    assert s["universe"]["data_stage_success"] == 800               # stage 2
    assert s["prefilter"]["primary_rejection_reason_counts"]["hard_veto"] == 20   # stage 3
    assert s["prefilter"]["cutoff_rank"] == 30                      # stage 4
    assert s["analysis"]["claude_success"] == 30                    # stage 5
    assert s["base_tiers"] == {"NEAR_ENTRY": 1}                     # stage 6
    assert s["ladder_baskets"] == {"SNIPER_A_PLUS": 1}              # stage 10
    assert s["suppression"]["check_alert_reason_counts"] == {"new_signal": 1}  # stage 12
    assert s["delivery"]["sent"] == 1                               # stage 13

    row = [t for t in led["decision_traces"] if t["ticker"] == "EEE"][0]
    assert row["ladder_source"] == "stored_scan_time"
    assert row["snipe_ladder"]["internal_ladder_tier"] == lad.SNIPER_A_PLUS
    assert row["judgment"]["base_final_tier"] == "NEAR_ENTRY"
    assert row["judgment"]["final_tier"] == "SNIPE_IT"
    assert row["risk"]["invalidation_condition"] == "1H close below 96.5"
    assert row["candle_evidence"]["candle_veto"] == "OPEN_ONLY"
    assert len([t for t in led["decision_traces"] if t["trace_kind"] == "near_cut"]) == 30

    # The scan it observed was never touched.
    assert _strategy_fingerprint(tr) == fingerprint


# ===========================================================================
# PHASE 14V.1 — TELEMETRY TRUTH RECONCILIATION
# ===========================================================================
#
# Every test below closes a defect the adversarial review PROVED. The law:
#   BASE tier is BASE tier. FINAL tier is FINAL tier.
#   CHECK_ALERT basis is the state check_alert actually saw.
#   A skipped message is not a failed message; a failed message must not vanish.
#   An analysis failure is not a market WAIT.
#   A legacy row is not telemetry-backed because some unrelated scan has telemetry.


def _served(tr, cfg):
    """The tier actually served, after ladder + capital floor + seal."""
    return _piped(tr, cfg)["final_tier"]


# ---- B1: base tier vs FINAL SERVED tier -----------------------------------

def test_v1_b1_base_near_entry_promoted_to_snipe_is_counted_as_final_snipe(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _live_result("NEAR_ENTRY")
    base = tr["final_tier"]                      # scheduler :353
    served = _served(tr, cfg)                    # scheduler :592, post-seal
    assert base == "NEAR_ENTRY" and served == "SNIPE_IT"
    s = _summary(tmp_path, base_tier_counts={base: 1}, final_tier_counts={served: 1})
    assert s["base_tiers"] == {"NEAR_ENTRY": 1}
    assert s["final_tiers"] == {"SNIPE_IT": 1}
    assert s["final_tiers"] != s["base_tiers"]


def test_v1_b1_seal_downgrade_is_reflected_in_final_tiers(tmp_path):
    cfg = _cfg(tmp_path)
    tr = _live_result("SNIPE_IT")
    tr["capital_action"] = "full_quality_allowed"
    tr["final_signal"]["tier"] = "SNIPE_IT"
    base = tr["final_tier"]
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("EEE", tr, {}, cfg)
    lad.apply_ladder_arbitration(tr, cfg)
    tr["snipe_gate_audit"].update({"promotion_state": "PROMOTION_BLOCKED",
                                   "eligible_for_snipe_review": False,
                                   "blocked_gate_names": ["HOLD_CONFIRMED"],
                                   "blocking_reasons": ["hold failed on closed 1H bar"]})
    seal_mod.seal_snipe_confirmed_consistency(tr, cfg)
    served = tr["final_tier"]
    assert base == "SNIPE_IT" and served != "SNIPE_IT"
    s = _summary(tmp_path, base_tier_counts={base: 1}, final_tier_counts={served: 1})
    assert s["base_tiers"] == {"SNIPE_IT": 1}
    assert s["final_tiers"] == {served: 1}


def test_v1_analysis_failures_are_never_counted_as_final_wait(tmp_path):
    """3, 4, 5 — Claude failure / rate limit / tiering exception are Stage-5
    outcomes, not market judgments."""
    s = _summary(tmp_path, final_tier_counts={"SNIPE_IT": 1},
                 analysis={"admitted": 4, "claude_success": 2, "claude_failed": 1,
                           "claude_rate_limited": 1, "tiering_failed": 1, "judged": 1})
    assert s["final_tiers"] == {"SNIPE_IT": 1}
    assert "WAIT" not in s["final_tiers"]
    assert s["analysis"]["claude_rate_limited"] == 1
    assert s["analysis"]["tiering_failed"] == 1


def test_v1_analysis_outcome_conservation(tmp_path):
    """6 — admitted == success + failed + rate_limited; success == judged + tiering_failed."""
    a = {"admitted": 30, "claude_success": 27, "claude_failed": 2,
         "claude_rate_limited": 1, "tiering_failed": 3, "judged": 24}
    s = _summary(tmp_path, analysis=a)["analysis"]
    assert s["admitted"] == s["claude_success"] + s["claude_failed"] + s["claude_rate_limited"]
    assert s["claude_success"] == s["judged"] + s["tiering_failed"]


def test_v1_analysis_failure_traces_invent_no_judgment():
    """26 — a Stage-5 failure trace must not fabricate a tier or basket."""
    for kind in (tlm.TRACE_ANALYSIS_FAILED, tlm.TRACE_RATE_LIMITED, tlm.TRACE_TIERING_FAILED):
        t = tlm.build_analysis_failure_trace("s", "EEE", _pf_row("EEE", 90), 5, kind,
                                             failure_code="claude_rate_limited")
        assert t["trace_kind"] == kind
        assert t["pipeline"]["admitted_to_deep_analysis"] is True
        for forbidden in ("judgment", "snipe_ladder", "suppression", "delivery"):
            assert forbidden not in t, forbidden


# ---- B2 / B3 / H4: delivery state machine ---------------------------------

_SEND_SHAPES = {
    "sent":        {"ok": True,  "sent": True,  "channel_id": 1, "skipped_reason": None,
                    "error_type": None},
    "cooldown":    {"ok": True,  "sent": False, "channel_id": None,
                    "skipped_reason": "duplicate_suppressed", "error_type": None},
    "wait":        {"ok": True,  "sent": False, "channel_id": None,
                    "skipped_reason": "wait_no_alert", "error_type": None},
    "routing":     {"ok": True,  "sent": False, "channel_id": None,
                    "skipped_reason": "channel_not_configured",
                    "error_type": "routing_failure"},
    "send_error":  {"ok": False, "sent": False, "channel_id": 1, "skipped_reason": None,
                    "error_type": "discord_send_error"},
}


def test_v1_b3_delivery_state_machine_separates_skipped_from_failed():
    """9, 10, 11, 12, 13 — an intentional non-send is SKIPPED, never FAILED."""
    assert tlm.delivery_state(_SEND_SHAPES["sent"]) == tlm.DELIVERY_SENT
    for skip in ("cooldown", "wait", "routing"):
        assert tlm.delivery_state(_SEND_SHAPES[skip]) == tlm.DELIVERY_SKIPPED, skip
    assert tlm.delivery_state(_SEND_SHAPES["send_error"]) == tlm.DELIVERY_FAILED


def test_v1_b2_discord_exception_produces_a_failed_trace():
    """7, 8 — a raised send_alert must still be recorded, as FAILED."""
    synth = tlm.exception_send_result(RuntimeError("boom"))
    assert tlm.delivery_state(synth) == tlm.DELIVERY_FAILED
    assert synth["error_type"] == tlm.DISCORD_EXCEPTION_ERROR
    assert synth["telemetry_synthesized"] is True
    assert "boom" not in json.dumps(synth)          # exception text not persisted
    t = tlm.build_decision_trace("s", "EEE", {}, 1, _live_result(), None, synth)
    assert t["delivery"]["state"] == tlm.DELIVERY_FAILED
    assert t["delivery"]["sent"] is False


def test_v1_h4_send_alert_called_is_distinct_from_network_attempted():
    """14 — calling send_alert is not the same as touching the network."""
    for name, sr in _SEND_SHAPES.items():
        t = tlm.build_decision_trace("s", "EEE", {}, 1, _live_result(), None, sr)
        assert t["delivery"]["send_alert_called"] is True, name
        assert t["delivery"]["network_attempted"] is (sr["channel_id"] is not None), name
    # unprovable -> None, never a fabricated False
    assert tlm.network_attempted({"ok": True, "sent": False}) is None


def test_v1_scheduler_records_delivery_by_state_not_by_sent_flag():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    assert 'scan_telemetry.exception_send_result(exc)' in src
    assert 'scan_telemetry.delivery_state(send_result)' in src
    assert '_tlm_delivery["skipped"] += 1' in src
    assert '_tlm_delivery["attempted"]' not in src        # old ambiguous counter gone


# ---- M1: check_alert decision basis ---------------------------------------

def test_v1_m1_check_alert_evaluated_tier_is_the_pre_ladder_tier(tmp_path):
    """15, 16 — the ledger must never imply the FINAL tier was the basis."""
    cfg = _cfg(tmp_path)
    tr = _live_result("NEAR_ENTRY")
    ca_tier, ca_cap = tr["final_tier"], tr["capital_action"]      # scheduler :392
    dd = {"should_alert": False, "reason": "duplicate_suppressed",
          "dedup_key": "EEE|NEAR_ENTRY|100.00|96.50"}
    _piped(tr, cfg)                                              # ladder promotes
    t = tlm.build_decision_trace("s", "EEE", {}, 1, tr, dd,
                                 _SEND_SHAPES["cooldown"],
                                 base_final_tier=ca_tier,
                                 check_alert_evaluated_tier=ca_tier,
                                 check_alert_evaluated_capital_action=ca_cap)
    assert t["suppression"]["check_alert_evaluated_tier"] == "NEAR_ENTRY"
    assert t["suppression"]["check_alert_evaluated_capital_action"] == "wait_no_capital"
    assert t["judgment"]["final_tier"] == "SNIPE_IT"      # differs, and is not rewritten
    assert t["suppression"]["check_alert_reason"] == "duplicate_suppressed"
    assert t["suppression"]["cooldown_suppressed"] is True


def test_v1_check_alert_timing_was_not_changed():
    """The ordering is MEASURED, not fixed. check_alert must still run before
    the ladder, and must not be re-run afterwards."""
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    scan = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    assert scan.count("state_store.check_alert(") == 1
    assert scan.index("state_store.check_alert(") < scan.index("apply_ladder_arbitration")


# ---- H1: state_store must never depend on telemetry -----------------------

def test_v1_h1_record_alert_survives_a_telemetry_projection_fault(tmp_path):
    """17, 18, 19, 37 — cooldown continuity must survive absurd telemetry input."""
    assert tlm._num(10 ** 400) is None                    # no OverflowError
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    tr["snipe_ladder"]["starter_grade"] = 10 ** 400       # poison the projection
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert("EEE", tr, state, cfg, "scan_x")
    tkr = state["tickers"]["EEE"]
    assert tkr["last_alerted_at"] is not None             # alert recorded
    assert tkr["alert_history"]                           # history appended
    assert tkr["last_alerted_tier"] == tr["final_tier"]   # cooldown armed
    decision = state_store.check_alert(tr, state, cfg)
    assert decision["reason"] == "duplicate_suppressed"   # cooldown works


# ---- B4 + Layer-2 consumption ---------------------------------------------

def _write_ledger(cfg, summary, traces):
    assert tlm.write_scan_telemetry(cfg, summary, traces) is True


def test_v1_b4_auditshy_actually_loads_the_telemetry_ledger(tmp_path):
    """20 — the ledger must reach the production command."""
    cfg = _cfg(tmp_path, audit_access={"enabled": True, "allowed_user_ids": ["4242"]})
    Path(cfg["state"]["state_file"]).write_text(json.dumps(
        {"tickers": {"AAA": {"alert_history": [_row_for_scan("scan_backed")]}},
         "meta": {}}), encoding="utf-8")
    _write_ledger(cfg, {"scan_id": "scan_backed"},
                  [tlm.build_decision_trace("scan_backed", "AAA", {}, 1,
                                            _piped(_live_result(), cfg), None,
                                            _SEND_SHAPES["sent"])])
    out = audit_access.run_auditshy(cfg, "json", user_id="4242")
    assert out["ok"] is True
    assert out["json"]["telemetry_scans"] == 1
    src = Path("src/audit_access.py").read_text(encoding="utf-8")
    assert "load_ledger_readonly" in src


def test_v1_auditshy_ledger_access_is_strictly_read_only(tmp_path):
    """35 — the audit loader must never write, rename, or quarantine."""
    cfg = _cfg(tmp_path)
    p = tlm.telemetry_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{corrupt", encoding="utf-8")
    before = sorted(x.name for x in p.parent.iterdir())
    assert tlm.load_ledger_readonly(cfg)["scan_summaries"] == []
    assert sorted(x.name for x in p.parent.iterdir()) == before
    assert p.read_text(encoding="utf-8") == "{corrupt"     # untouched


def test_v1_layer2_traces_are_consumed_without_double_counting(tmp_path):
    """21, 22, 23, 24, 25 — telemetry-only rows surface; sent alerts do not duplicate."""
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    history_row = _row_for_scan("scan_backed", ticker="AAA")
    traces = {
        "AAA": tlm.build_decision_trace("scan_backed", "AAA", {}, 1, tr, None,
                                        _SEND_SHAPES["sent"]),
        "WWW": tlm.build_decision_trace("scan_backed", "WWW", {}, 2, tr,
                                        {"reason": "wait_no_alert", "should_alert": False},
                                        _SEND_SHAPES["wait"]),
        "CCC": tlm.build_decision_trace("scan_backed", "CCC", {}, 3, tr,
                                        {"reason": "duplicate_suppressed",
                                         "should_alert": False},
                                        _SEND_SHAPES["cooldown"]),
        "RRR": tlm.build_decision_trace("scan_backed", "RRR", {}, 4, tr,
                                        {"reason": "new_signal", "should_alert": True},
                                        _SEND_SHAPES["routing"]),
    }
    rep = ssfa.run_shyness_funnel_audit(
        rows=[history_row], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "scan_backed"}],
                   "decision_traces": list(traces.values())})
    tickers = [r["ticker"] for r in rep["examples"]] + \
              [r.get("ticker") for r in (rep.get("examples") or [])]
    assert rep["total_rows"] == 4          # 1 history + 3 telemetry-only, AAA not doubled
    assert sum(1 for _ in [t for t in traces if t == "AAA"]) == 1
    assert rep["telemetry_backed_rows"] == 4
    assert rep["legacy_rows"] == 0


def test_v1_cooldown_and_routing_suppression_become_emittable(tmp_path):
    """Newly observable classes — and DEDUP_SUPPRESSED still is not (53)."""
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    cool = tlm.build_decision_trace("s1", "CCC", {}, 1, tr,
                                    {"reason": "duplicate_suppressed", "should_alert": False},
                                    _SEND_SHAPES["cooldown"])
    rout = tlm.build_decision_trace("s1", "RRR", {}, 2, tr,
                                    {"reason": "new_signal", "should_alert": True},
                                    _SEND_SHAPES["routing"])
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}], "decision_traces": [cool, rout]})
    assert rep["class_counts"].get(ssfa.COOLDOWN_SUPPRESSED) == 1
    assert rep["class_counts"].get(ssfa.ROUTING_SUPPRESSED) == 1
    assert ssfa.DEDUP_SUPPRESSED not in rep["class_counts"]


def test_v1_analysis_failure_traces_are_not_market_judgments(tmp_path):
    """26 — Stage-5 failures are counted as outcomes, not undercalls."""
    cfg = _cfg(tmp_path)
    fails = [tlm.build_analysis_failure_trace("s1", "F1", {}, 40, tlm.TRACE_RATE_LIMITED),
             tlm.build_analysis_failure_trace("s1", "F2", {}, 41, tlm.TRACE_ANALYSIS_FAILED)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}], "decision_traces": fails})
    assert rep["telemetry_analysis_outcomes"] == {tlm.TRACE_RATE_LIMITED: 1,
                                                  tlm.TRACE_ANALYSIS_FAILED: 1}
    for cls in rep["class_counts"]:
        assert "UNDERCALL" not in cls


# ---- H3: per-scan observability -------------------------------------------

def test_v1_h3_unrelated_telemetry_scan_does_not_upgrade_legacy_rows():
    """27 — 300 legacy rows + 1 unrelated telemetry scan must stay legacy."""
    legacy = [_row_for_scan(f"scan-legacy-{i}", ticker=f"L{i}") for i in range(300)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=legacy, config={}, limit=300,
        telemetry={"scan_summaries": [{"scan_id": "unrelated"}], "decision_traces": []})
    by_id = {s["stage"]: s for s in rep["stages"]}
    assert rep["telemetry_backed_rows"] == 0
    assert rep["legacy_rows"] == 300
    for stage in ssfa.TELEMETRY_BACKED_STAGES:
        assert by_id[stage]["observability"] == ssfa.NOT_PERSISTED, stage
        assert by_id[stage]["shy_rows_attributed"] is None


def test_v1_h3_mixed_window_is_partial_not_observable():
    """28 — matching scan_id upgrades only that evidence; a mix reports PARTIAL."""
    rows = [_row_for_scan("scan-backed", ticker="B1"),
            _row_for_scan("scan-legacy", ticker="L1")]
    rep = ssfa.run_shyness_funnel_audit(
        rows=rows, config={},
        telemetry={"scan_summaries": [_backed_summary("scan-backed")],
                   "decision_traces": []})
    by_id = {s["stage"]: s for s in rep["stages"]}
    assert rep["telemetry_backed_rows"] == 1 and rep["legacy_rows"] == 1
    assert by_id["DEDUP_AND_COOLDOWN"]["observability"] == ssfa.PARTIAL
    assert by_id["DEDUP_AND_COOLDOWN"]["telemetry_backed_rows"] == 1
    assert by_id["DEDUP_AND_COOLDOWN"]["legacy_rows"] == 1


# ---- M5: stale honesty text ------------------------------------------------

def test_v1_m5_stale_ladder_never_persisted_text_is_conditional():
    """31 — the note must not globally claim the ladder is never persisted."""
    backed = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1")], config={},
        telemetry={"scan_summaries": [_backed_summary("s1")], "decision_traces": []})
    note = backed["observability_note"]
    assert "is not persisted and is recomputed here" not in note
    assert "TELEMETRY IN SCOPE" in note or "telemetry-backed" in note
    gaps = " ".join(g["effect"] for g in backed["persistence_gaps"])
    assert "always a recompute" not in gaps
    assert "LEGACY ROWS ONLY" in gaps
    probes = " ".join(backed["recommended_next_probes"])
    assert "Persist the Phase 14S snipe_ladder object" not in probes
    # legacy-only report keeps the original honest text
    legacy = ssfa.run_shyness_funnel_audit(rows=[], config={})
    assert "SENT ALERTS ONLY" in legacy["observability_note"]


# ---- M6 / M7 / M8: path collision, schema, corruption ---------------------

def test_v1_m6_telemetry_path_collision_fails_closed(tmp_path):
    """32, 33 — telemetry unavailable is safer than telemetry destroying state."""
    hist = tmp_path / "alert_history.json"
    cfg = {"state": {"state_file": str(hist)},
           "telemetry": {"telemetry_file": str(hist)}}
    payload = json.dumps({"tickers": {"AAPL": {"last_alerted_at": "2026-01-01T00:00:00",
                                               "alert_history": []}}, "meta": {}})
    hist.write_text(payload, encoding="utf-8")
    assert tlm.telemetry_path_collides(cfg) is True
    assert tlm.write_scan_telemetry(cfg, {"scan_id": "s"}, []) is False
    assert hist.read_text(encoding="utf-8") == payload          # byte-identical
    assert tlm.load_ledger_readonly(cfg)["scan_summaries"] == []


def test_v1_m7_schema_mismatch_is_quarantined_not_relabelled(tmp_path):
    """34 — an old schema must not be silently stamped as the new one."""
    cfg = _cfg(tmp_path)
    p = tlm.telemetry_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": "14V.1",
                             "scan_summaries": [{"old": 1}],
                             "decision_traces": []}), encoding="utf-8")
    tlm.write_scan_telemetry(cfg, {"scan_id": "new"}, [])
    after = json.loads(p.read_text(encoding="utf-8"))
    assert after["schema_version"] == tlm.SCHEMA_VERSION == "14V.2"
    assert {"old": 1} not in after["scan_summaries"]            # not relabelled
    assert list(p.parent.glob("*.corrupt.*"))                   # preserved instead


def test_v1_m8_corrupt_telemetry_is_preserved_before_starting_fresh(tmp_path):
    """36 — a transient read failure must not silently destroy the ledger."""
    cfg = _cfg(tmp_path)
    tlm.write_scan_telemetry(cfg, {"scan_id": "good"}, [{"ticker": "T1"}, {"ticker": "T2"}])
    p = tlm.telemetry_path(cfg)
    p.write_text("{truncated", encoding="utf-8")
    tlm.write_scan_telemetry(cfg, {"scan_id": "new"}, [])
    backups = list(p.parent.glob("*.corrupt.*"))
    assert backups, "corrupt telemetry was destroyed without a backup"
    assert backups[0].read_text(encoding="utf-8") == "{truncated"
    hist = Path(cfg["state"]["state_file"])
    assert not hist.exists() or "scan_summaries" not in hist.read_text(encoding="utf-8")


def test_v1_temp_reaping_is_scoped_to_telemetry_only(tmp_path):
    """48 — stale temps are reaped; unrelated files are never touched."""
    cfg = _cfg(tmp_path)
    p = tlm.telemetry_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    stale = p.with_name(p.name + ".tmp.999999")
    stale.write_text("stale", encoding="utf-8")
    bystander = p.parent / "alert_history.json"
    bystander.write_text("{}", encoding="utf-8")
    tlm.write_scan_telemetry(cfg, {"scan_id": "s"}, [])
    assert not stale.exists()
    assert bystander.read_text(encoding="utf-8") == "{}"


# ---- M10: bounded free text ------------------------------------------------

def test_v1_m10_free_text_is_bounded_and_source_is_unmutated(tmp_path):
    """38, 39 — telemetry caps strings; the scanner object is untouched."""
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    huge = "X" * 8000
    tr["final_signal"]["invalidation_condition"] = huge
    before = copy.deepcopy(tr)
    t = tlm.build_decision_trace("s", "EEE", {}, 1, tr)
    assert len(t["risk"]["invalidation_condition"]) == tlm._MAX_TEXT
    assert tr == before                                   # source unmutated
    assert tr["final_signal"]["invalidation_condition"] == huge


def test_v1_scalar_never_stringifies_containers():
    assert tlm._scalar({"a": 1}) is None
    assert tlm._scalar([1, 2]) is None
    assert tlm._scalar("ok") == "ok"
    assert tlm._scalar(True) is True


# ---- M3 / M4: cutoff + near-cut --------------------------------------------

def test_v1_m3_cutoff_only_when_the_cap_actually_bound(tmp_path):
    """40, 41."""
    exact = _summary(tmp_path, pf_result=_pf_result(n_eligible=30, n_rejected=0, cap=30))
    assert exact["prefilter"]["cutoff_rank"] is None
    over = _summary(tmp_path, pf_result=_pf_result(n_eligible=31, n_rejected=0, cap=30))
    assert over["prefilter"]["cutoff_rank"] == 30
    assert over["prefilter"]["cutoff_score"] == 71


def test_v1_m4_near_cut_window_derives_from_the_configured_cap(tmp_path):
    """42, 43 — and the cap itself is unchanged."""
    ranked = _pf_result(n_eligible=90)["ranked_results"]
    default = tlm.near_cut_slice(ranked, _cfg(tmp_path))
    assert [r for _, r in default] == list(range(31, 61))
    raised = tlm.near_cut_slice(ranked, {"prefilter": {"max_claude_candidates_per_scan": 40}})
    assert [r for _, r in raised] == list(range(41, 71))
    import yaml
    assert yaml.safe_load(open("config/doctrine_config.yaml"))[
        "prefilter"]["max_claude_candidates_per_scan"] == 30


# ---- M9 / M11 / footprint / parity ----------------------------------------

def test_v1_m9_data_stage_names_reflect_fetch_plus_enrich(tmp_path):
    """46."""
    s = _summary(tmp_path)
    assert "data_stage_success" in s["universe"] and "data_stage_failure" in s["universe"]
    assert "market_data_success" not in s["universe"]


def test_v1_m11_final_write_is_off_the_event_loop():
    """51."""
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(" in src
    assert "asyncio.to_thread(\n            scan_telemetry.write_scan_telemetry" in src


def test_v1_h2_footprint_all_three_mixes_under_bound(tmp_path):
    """50 — measured with the EXACT production serializer, not a compact proxy."""
    cfg = _cfg(tmp_path)
    tr = _piped(_live_result(), cfg)
    S = _summary(tmp_path)
    A = tlm.build_decision_trace("scan_20260811_120000_aaaaaa", "EEE",
                                 _pf_row("EEE", 90), 7, tr,
                                 {"should_alert": True, "reason": "new_signal",
                                  "dedup_key": "EEE|SNIPE_IT|100.00|96.50"},
                                 _SEND_SHAPES["sent"], base_final_tier="NEAR_ENTRY",
                                 check_alert_evaluated_tier="NEAR_ENTRY")
    N = tlm.build_near_cut_trace("scan_20260811_120000_aaaaaa", _pf_row("T030", 70), 31)
    n_sum, n_tr = 300, 9000
    for frac in (0.0, 0.5, 1.0):
        na = int(n_tr * frac)
        ledger = {"schema_version": tlm.SCHEMA_VERSION,
                  "scan_summaries": [S] * n_sum,
                  "decision_traces": [A] * na + [N] * (n_tr - na)}
        p = tmp_path / f"probe_{int(frac * 100)}.json"
        p.write_text(json.dumps(ledger, allow_nan=False, separators=(",", ":")),
                     encoding="utf-8")
        mb = p.stat().st_size / (1024 * 1024)
        assert mb < 25.0, f"mix {frac}: {mb:.2f} MB exceeds the 25 MB bound"


def test_v1_observed_zero_cooldown_suppression_is_allowed(tmp_path):
    """54 — UNOBSERVABLE != 0, but an OBSERVED count may legitimately be 0."""
    s = _summary(tmp_path, check_alert_reason_counts={"new_signal": 5})
    assert s["suppression"]["cooldown_suppressed"] == 0
    assert s["suppression"]["check_alert_reason_counts"] == {"new_signal": 5}


def test_v1_strategy_parity_telemetry_on_versus_off(tmp_path):
    """49 — every strategy field identical with telemetry exercised."""
    cfg = _cfg(tmp_path)
    for mutate in (lambda t: t,
                   lambda t: (t["one_hour_entry"].__setitem__("trigger_state",
                                                              "RETEST_IN_PROGRESS"), t)[1]):
        off = _piped(mutate(_live_result()), cfg)
        on = _piped(mutate(_live_result()), cfg)
        tlm.build_decision_trace("s", "EEE", _pf_row("EEE", 90), 3, on,
                                 {"should_alert": True, "reason": "new_signal"},
                                 _SEND_SHAPES["sent"], base_final_tier="NEAR_ENTRY",
                                 check_alert_evaluated_tier="NEAR_ENTRY")
        tlm.write_scan_telemetry(cfg, _summary(tmp_path), [])
        assert _strategy_fingerprint(on) == _strategy_fingerprint(off)


# ===========================================================================
# PHASE 14V.1A — STAGE OBSERVABILITY vs SHYNESS ATTRIBUTION
# ===========================================================================
#
# Two different questions, deliberately not conflated:
#   observability       -> can we see WHAT the stage did?
#   shyness_attribution -> can we prove a SPECIFIC candidate was a missed
#                          SNIPE/STARTER at that stage?
#
# An observed outcome is not automatically proven shyness. A stage marked
# OBSERVABLE must never simultaneously claim its evidence is "not persisted".


def _cool_trace(cfg, ticker, rank):
    return tlm.build_decision_trace(
        "s1", ticker, {}, rank, _piped(_live_result(), cfg),
        {"reason": "duplicate_suppressed", "should_alert": False},
        _SEND_SHAPES["cooldown"])


def _sent_trace(cfg, ticker, rank):
    return tlm.build_decision_trace(
        "s1", ticker, {}, rank, _piped(_live_result(), cfg),
        {"reason": "new_signal", "should_alert": True}, _SEND_SHAPES["sent"])


def _stage(report, stage_id):
    return {s["stage"]: s for s in report["stages"]}[stage_id]


def test_v1a_1_legacy_stage_12_is_unobservable_and_unattributable():
    rep = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.NOT_PERSISTED
    assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert st["shy_rows_attributed"] is None
    assert "not persisted" in st["attribution_reason"]


def test_v1a_2_telemetry_backed_stage_12_reports_a_real_count(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}],
                   "decision_traces": [_cool_trace(cfg, "C1", 1), _cool_trace(cfg, "C2", 2)]})
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.OBSERVABLE
    assert st["shyness_attribution"] == ssfa.ATTR_OBSERVABLE
    assert st["shy_rows_attributed"] == 2


def test_v1a_3_observed_zero_cooldown_is_a_real_zero_not_null(tmp_path):
    """UNOBSERVED != 0, but an OBSERVED count may legitimately be 0."""
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}],
                   "decision_traces": [_sent_trace(cfg, "OK1", 1)]})
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.OBSERVABLE
    assert st["shy_rows_attributed"] == 0
    assert st["shy_rows_attributed"] is not None


def test_v1a_4_mixed_window_is_partial_and_keeps_the_legacy_caveat(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1", ticker="B1"), _row_for_scan("legacy", ticker="L1")],
        config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}],
                   "decision_traces": [_cool_trace(cfg, "C1", 1)]})
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.PARTIAL
    assert st["shyness_attribution"] == ssfa.ATTR_PARTIAL
    assert isinstance(st["shy_rows_attributed"], int)
    assert st["legacy_rows"] == 1 and st["telemetry_backed_rows"] >= 1
    assert "legacy rows are not covered" in st["attribution_reason"]


def test_v1a_5_unrelated_telemetry_scan_upgrades_nothing():
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan(f"legacy-{i}", ticker=f"L{i}") for i in range(5)],
        config={},
        telemetry={"scan_summaries": [{"scan_id": "unrelated"}], "decision_traces": []})
    for sid in ssfa.TELEMETRY_BACKED_STAGES:
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.NOT_PERSISTED, sid
        assert st["shy_rows_attributed"] is None, sid


def test_v1a_6_stage_4_near_cut_is_visible_but_not_attributable(tmp_path):
    """A near-cut trace proves a ticker ranked outside admission. It does NOT
    prove the ticker was a valid SNIPE/STARTER — no judgment ever ran."""
    cfg = _cfg(tmp_path)
    near = [tlm.build_near_cut_trace("s1", _pf_row(f"N{i}", 70 - i), 31 + i) for i in range(3)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}],
                   "decision_traces": near + [_sent_trace(cfg, "OK1", 1)]})
    st = _stage(rep, "CANDIDATE_CAP_TOP_N")
    assert st["observability"] == ssfa.OBSERVABLE          # outcome visible
    assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert st["shy_rows_attributed"] is None               # no fabricated shyness
    assert "not determinable" in st["attribution_reason"]
    for cls in rep["class_counts"]:
        assert "UNDERCALL" not in cls                       # never invented


def test_v1a_7_stage_5_analysis_failures_are_visible_but_not_undercalls(tmp_path):
    cfg = _cfg(tmp_path)
    fails = [tlm.build_analysis_failure_trace("s1", "F1", {}, 5, tlm.TRACE_RATE_LIMITED),
             tlm.build_analysis_failure_trace("s1", "F2", {}, 6, tlm.TRACE_ANALYSIS_FAILED),
             tlm.build_analysis_failure_trace("s1", "F3", {}, 7, tlm.TRACE_TIERING_FAILED)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}], "decision_traces": fails})
    st = _stage(rep, "CLAUDE_ANALYSIS")
    assert st["observability"] == ssfa.OBSERVABLE
    assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert st["shy_rows_attributed"] is None
    assert rep["telemetry_analysis_outcomes"] == {
        tlm.TRACE_RATE_LIMITED: 1, tlm.TRACE_ANALYSIS_FAILED: 1, tlm.TRACE_TIERING_FAILED: 1}
    assert "WAIT" not in rep["tier_counts"]                 # never a fake WAIT
    for cls in rep["class_counts"]:
        assert "UNDERCALL" not in cls


def test_v1a_8_and_9_renderer_never_claims_not_persisted_for_a_visible_stage(tmp_path):
    cfg = _cfg(tmp_path)
    for rows, tel in (
        ([], {"scan_summaries": [{"scan_id": "s1"}],
              "decision_traces": [_cool_trace(cfg, "C1", 1)]}),                    # OBSERVABLE
        ([_row_for_scan("s1"), _row_for_scan("legacy")],
         {"scan_summaries": [{"scan_id": "s1"}],
          "decision_traces": [_cool_trace(cfg, "C1", 1)]}),                        # PARTIAL
    ):
        rep = ssfa.run_shyness_funnel_audit(rows=rows, config=cfg, telemetry=tel)
        text = ssfa.render_shyness_funnel_audit(rep)
        for line in text.splitlines():
            if "[visible]" in line or "[partial]" in line:
                assert "n/a (not persisted)" not in line, line


def test_v1a_10_and_11_zero_is_preserved_and_unobservable_stays_null(tmp_path):
    cfg = _cfg(tmp_path)
    backed = ssfa.run_shyness_funnel_audit(
        rows=[], config=cfg,
        telemetry={"scan_summaries": [{"scan_id": "s1"}],
                   "decision_traces": [_sent_trace(cfg, "OK1", 1)]})
    assert _stage(backed, "DEDUP_AND_COOLDOWN")["shy_rows_attributed"] == 0
    legacy = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    assert _stage(legacy, "DEDUP_AND_COOLDOWN")["shy_rows_attributed"] is None


def test_v1a_12_historical_14u_behaviour_is_unchanged():
    """Stages classified from alert_history keep their original semantics."""
    rep = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    for sid in ("TIERING_BASE_VALIDATION", "ONE_H_ENTRY_PROOF", "SNIPE_GATE_AUDIT",
                "DOWNGRADE_ONLY_SEAL"):
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.OBSERVABLE
        assert st["shyness_attribution"] == ssfa.ATTR_OBSERVABLE
        assert isinstance(st["shy_rows_attributed"], int)
    for sid in ("LADDER_ARBITRATION", "ROUTING_AND_ALERT_WORDING"):
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.PARTIAL
        assert st["shyness_attribution"] == ssfa.ATTR_PARTIAL
        assert isinstance(st["shy_rows_attributed"], int)


def test_v1a_no_stage_is_ever_observable_while_claiming_not_persisted(tmp_path):
    """The invariant, asserted structurally across every window shape."""
    cfg = _cfg(tmp_path)
    windows = [
        ([], None),
        ([_row_for_scan("legacy")], None),
        ([], {"scan_summaries": [{"scan_id": "s1"}],
              "decision_traces": [_cool_trace(cfg, "C1", 1)]}),
        ([_row_for_scan("s1"), _row_for_scan("legacy")],
         {"scan_summaries": [{"scan_id": "s1"}], "decision_traces": []}),
    ]
    for rows, tel in windows:
        rep = ssfa.run_shyness_funnel_audit(rows=rows, config=cfg, telemetry=tel)
        for st in rep["stages"]:
            if st["observability"] == ssfa.NOT_PERSISTED:
                assert st["shy_rows_attributed"] is None
                assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
            if st["shy_rows_attributed"] is not None:
                assert st["observability"] != ssfa.NOT_PERSISTED
                assert st["shyness_attribution"] != ssfa.ATTR_NOT_DETERMINABLE


# ===========================================================================
# PHASE 14V.1B — EVIDENCE IS ORGAN-SPECIFIC
# ===========================================================================
#
# Stage-5 evidence is not Stage-12 evidence. Near-cut evidence is not
# check_alert evidence. A scan summary is real evidence and must not vanish
# because no candidate trace exists. Aggregate observability is not
# candidate-level causation.


def _fail_traces(scan="s1"):
    return [tlm.build_analysis_failure_trace(scan, "F1", {}, 5, tlm.TRACE_ANALYSIS_FAILED),
            tlm.build_analysis_failure_trace(scan, "F2", {}, 6, tlm.TRACE_RATE_LIMITED),
            tlm.build_analysis_failure_trace(scan, "F3", {}, 7, tlm.TRACE_TIERING_FAILED)]


def _near_traces(scan="s1", n=3):
    return [tlm.build_near_cut_trace(scan, _pf_row(f"N{i}", 70 - i), 31 + i) for i in range(n)]


def _report(cfg, summaries, traces, rows=None, limit=100):
    return ssfa.run_shyness_funnel_audit(
        rows=rows if rows is not None else [], config=cfg, limit=limit,
        telemetry={"scan_summaries": summaries, "decision_traces": traces})


def test_v1b_1_stage5_only_evidence_cannot_observe_stage12(tmp_path):
    """CASE A — three candidates died at Claude and never reached check_alert."""
    rep = _report(_cfg(tmp_path), [{"scan_id": "s1"}], _fail_traces())
    claude = _stage(rep, "CLAUDE_ANALYSIS")
    dedup = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert claude["observability"] == ssfa.OBSERVABLE
    assert claude["events_observed"] == 3
    assert dedup["observability"] == ssfa.NOT_PERSISTED
    assert dedup["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert dedup["shy_rows_attributed"] is None       # NOT a fake observed zero


def test_v1b_2_near_cut_only_evidence_cannot_observe_stage12_or_stage5(tmp_path):
    """CASE B — ranked outside admission proves nothing downstream."""
    rep = _report(_cfg(tmp_path), [{"scan_id": "s1"}], _near_traces())
    assert _stage(rep, "CANDIDATE_CAP_TOP_N")["observability"] == ssfa.OBSERVABLE
    assert _stage(rep, "CANDIDATE_CAP_TOP_N")["events_observed"] == 3
    for sid in ("CLAUDE_ANALYSIS", "DEDUP_AND_COOLDOWN"):
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.NOT_PERSISTED, sid
        assert st["shy_rows_attributed"] is None, sid


def test_v1b_3_analyzed_sent_trace_gives_stage12_a_real_zero(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [{"scan_id": "s1"}], [_sent_trace(cfg, "OK1", 1)])
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.OBSERVABLE
    assert st["shyness_attribution"] == ssfa.ATTR_OBSERVABLE
    assert st["shy_rows_attributed"] == 0             # reached check_alert, not suppressed
    assert st["events_observed"] == 1


def test_v1b_4_analyzed_cooldown_trace_increments_stage12(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [{"scan_id": "s1"}],
                  [_cool_trace(cfg, "C1", 1), _cool_trace(cfg, "C2", 2)])
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.OBSERVABLE
    assert st["shy_rows_attributed"] == 2
    assert st["events_observed"] == 2


def test_v1b_5_to_9_summary_only_makes_each_stage_outcome_observable(tmp_path):
    """CASE C — Layer-1 is real evidence. It must not vanish for lack of traces."""
    rep = _report(_cfg(tmp_path), [_backed_summary("s1")], [])
    for sid, events in (("UNIVERSE_ADMISSION", 814),
                        ("MARKET_DATA_ENRICHMENT", 814),
                        ("PREFILTER_SCORE_VETO", 40),
                        ("CANDIDATE_CAP_TOP_N", 30),
                        ("CLAUDE_ANALYSIS", 30)):
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.OBSERVABLE, sid
        assert st["events_observed"] == events, sid
        # outcome observed, but no candidate was ever market-judged here
        assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE, sid
        assert st["shy_rows_attributed"] is None, sid


def test_v1b_10_summary_only_stage12_is_aggregate_observable_not_attributable(tmp_path):
    """A summary proving how check_alert resolved is real aggregate evidence —
    but aggregate observability is not candidate-level causation."""
    rep = _report(_cfg(tmp_path), [_backed_summary("s1")], [])
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.OBSERVABLE          # aggregate outcome seen
    assert st["events_observed"] == 24                     # 24 check_alert decisions
    assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert st["shy_rows_attributed"] is None               # no row-level traces


def test_v1b_11_unrelated_retained_scan_does_not_upgrade_this_window(tmp_path):
    """Window matching: an older retained scan is out of scope."""
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("current")], config=cfg, limit=1,
        telemetry={"scan_summaries": [_backed_summary("old"), {"scan_id": "current"}],
                   "decision_traces": _fail_traces("old")})
    assert rep["telemetry_window"]["scans_in_window"] == 1
    assert rep["telemetry_window"]["traces_in_window"] == 0
    assert _stage(rep, "CLAUDE_ANALYSIS")["observability"] == ssfa.NOT_PERSISTED


def test_v1b_12_13_14_cross_stage_contamination_is_impossible(tmp_path):
    """A trace may only ever upgrade its OWN stage."""
    cfg = _cfg(tmp_path)
    # 12: Stage-5 trace cannot upgrade Stage 12
    r5 = _report(cfg, [{"scan_id": "s1"}], _fail_traces())
    assert _stage(r5, "DEDUP_AND_COOLDOWN")["observability"] == ssfa.NOT_PERSISTED
    # 13: Stage-4 trace cannot upgrade Stage 5 or Stage 12
    r4 = _report(cfg, [{"scan_id": "s1"}], _near_traces())
    assert _stage(r4, "CLAUDE_ANALYSIS")["observability"] == ssfa.NOT_PERSISTED
    assert _stage(r4, "DEDUP_AND_COOLDOWN")["observability"] == ssfa.NOT_PERSISTED
    # 14: Stage-12 trace cannot manufacture Stage-4 candidate judgment
    r12 = _report(cfg, [{"scan_id": "s1"}], [_cool_trace(cfg, "C1", 1)])
    assert _stage(r12, "CANDIDATE_CAP_TOP_N")["observability"] == ssfa.NOT_PERSISTED
    assert _stage(r12, "UNIVERSE_ADMISSION")["observability"] == ssfa.NOT_PERSISTED


def test_v1b_15_16_observed_zero_versus_unreached(tmp_path):
    """5 candidates reached check_alert, 0 suppressed -> 0.
    3 candidates died at Claude and never reached it -> null, not 0."""
    cfg = _cfg(tmp_path)
    reached = _report(cfg, [{"scan_id": "s1"}],
                      [_sent_trace(cfg, f"OK{i}", i) for i in range(1, 6)])
    st = _stage(reached, "DEDUP_AND_COOLDOWN")
    assert st["events_observed"] == 5 and st["shy_rows_attributed"] == 0

    unreached = _report(cfg, [{"scan_id": "s1"}], _fail_traces())
    st2 = _stage(unreached, "DEDUP_AND_COOLDOWN")
    assert st2["events_observed"] is None and st2["shy_rows_attributed"] is None


def test_v1b_17_mixed_window_remains_honest(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1", ticker="B1"), _row_for_scan("legacy", ticker="L1")],
        config=cfg,
        telemetry={"scan_summaries": [_backed_summary("s1")],
                   "decision_traces": [_cool_trace(cfg, "C1", 1)]})
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["observability"] == ssfa.PARTIAL
    assert st["shyness_attribution"] == ssfa.ATTR_PARTIAL
    assert isinstance(st["shy_rows_attributed"], int)
    assert rep["legacy_rows"] >= 1 and rep["telemetry_backed_rows"] >= 1
    assert "legacy rows are not covered" in st["attribution_reason"]


def test_v1b_telemetry_window_is_reported_explicitly(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [_backed_summary(f"s{i}") for i in range(5)], [], limit=2)
    w = rep["telemetry_window"]
    assert w["scans_available"] == 5
    assert w["scans_in_window"] == 2      # bounded, deterministic, most recent
    assert w["limit"] == 2


def test_v1b_stage_evidence_map_is_exposed_and_organ_scoped(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [{"scan_id": "s1"}], _fail_traces())
    ev = rep["stage_evidence"]
    assert set(ev) == set(ssfa.TELEMETRY_BACKED_STAGES)
    assert ev["CLAUDE_ANALYSIS"]["evidence_available"] is True
    assert ev["DEDUP_AND_COOLDOWN"]["evidence_available"] is False
    assert ev["DEDUP_AND_COOLDOWN"]["row_attribution"] is False


# ===========================================================================
# PHASE 14V.1C — AUDIT WINDOW / EVIDENCE ACCOUNTING TRUTH
# ===========================================================================
#
# Field present is not stage reached. Layer 1 and Layer 2 are two views of one
# event, not two events. Recent telemetry does not rewrite unrelated history.
# Every number names its population.
#
# These tests use REAL production objects, not stripped {"scan_id": ...} stubs.


def _real_summary(scan_id="s1", tmp_path=None, **over):
    """A summary built through the actual production builder."""
    cfg = _cfg(tmp_path)
    kw = dict(scan_id=scan_id, scan_timestamp="2026-08-11T12:00:00",
              tickers_input=110, data_failures=40, pf_result=_pf_result(), config=cfg,
              final_tier_counts={"SNIPE_IT": 4, "STARTER": 8, "NEAR_ENTRY": 9, "WAIT": 3},
              ladder_counts={"SNIPER_A": 4}, base_tier_counts={"NEAR_ENTRY": 24},
              check_alert_reason_counts={"new_signal": 24},
              delivery={"send_alert_called": 24, "sent": 13, "skipped": 10, "failed": 1},
              analysis={"admitted": 30, "claude_success": 27, "claude_failed": 2,
                        "claude_rate_limited": 1, "tiering_failed": 3, "judged": 24})
    kw.update(over)
    return tlm.build_scan_summary(**kw)


def _unreached_summary(scan_id="s1", tmp_path=None):
    """Production-shaped: every admitted candidate died before check_alert."""
    return _real_summary(
        scan_id, tmp_path,
        final_tier_counts={}, ladder_counts={}, base_tier_counts={},
        check_alert_reason_counts={},          # schema still emits the block
        delivery={"send_alert_called": 0, "sent": 0, "skipped": 0, "failed": 0},
        analysis={"admitted": 30, "claude_success": 0, "claude_failed": 29,
                  "claude_rate_limited": 1, "tiering_failed": 0, "judged": 0})


def test_v1c_1_empty_check_alert_block_is_not_stage_execution(tmp_path):
    """A field the schema always emits is not proof the stage ran."""
    summ = _unreached_summary("s1", tmp_path)
    assert summ["suppression"]["check_alert_reason_counts"] == {}     # production shape
    rep = _report(_cfg(tmp_path), [summ], _fail_traces())
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["stage_reached"] is False
    assert st["shyness_attribution"] == ssfa.ATTR_NOT_DETERMINABLE
    assert st["shy_rows_attributed"] is None                          # NOT a zero
    assert "not a zero" in st["attribution_reason"]


def test_v1c_2_stage5_only_production_scan_leaves_stage12_unreached(tmp_path):
    rep = _report(_cfg(tmp_path), [_unreached_summary("s1", tmp_path)], _fail_traces())
    assert _stage(rep, "CLAUDE_ANALYSIS")["stage_reached"] is True
    assert _stage(rep, "CLAUDE_ANALYSIS")["events_observed"] == 30
    st = _stage(rep, "DEDUP_AND_COOLDOWN")
    assert st["stage_reached"] is False and st["shy_rows_attributed"] is None


def test_v1c_3_five_real_check_alert_decisions_zero_cooldown_is_a_real_zero(tmp_path):
    cfg = _cfg(tmp_path)
    summ = _real_summary("s1", tmp_path, check_alert_reason_counts={"new_signal": 5})
    traces = [_sent_trace(cfg, f"OK{i}", i) for i in range(1, 6)]
    st = _stage(_report(cfg, [summ], traces), "DEDUP_AND_COOLDOWN")
    assert st["stage_reached"] is True
    assert st["events_observed"] == 5
    assert st["shy_rows_attributed"] == 0                             # real observed zero


def test_v1c_4_layer1_and_layer2_are_not_summed_stage5(tmp_path):
    """30 admitted + 30 traces == 30 events, not 60."""
    summ = _real_summary("s1", tmp_path)
    traces = [tlm.build_analysis_failure_trace("s1", f"A{i}", {}, i,
                                               tlm.TRACE_ANALYSIS_FAILED) for i in range(30)]
    st = _stage(_report(_cfg(tmp_path), [summ], traces), "CLAUDE_ANALYSIS")
    assert st["events_observed"] == 30
    assert st["aggregate_source"] == "scan_summary"
    assert st["trace_rows_observed"] == 30


def test_v1c_5_layer1_and_layer2_are_not_summed_stage12(tmp_path):
    """24 check_alert decisions + 24 analyzed traces == 24 events, not 48."""
    cfg = _cfg(tmp_path)
    summ = _real_summary("s1", tmp_path)
    traces = [_sent_trace(cfg, f"T{i}", i) for i in range(24)]
    st = _stage(_report(cfg, [summ], traces), "DEDUP_AND_COOLDOWN")
    assert st["events_observed"] == 24
    assert st["aggregate_source"] == "scan_summary"
    assert st["trace_rows_observed"] == 24


def test_v1c_6_trace_coverage_is_reported_separately(tmp_path):
    """Layer-2 acts as a fallback count only when no Layer-1 aggregate exists."""
    cfg = _cfg(tmp_path)
    st = _stage(_report(cfg, [{"scan_id": "s1"}], _fail_traces()), "CLAUDE_ANALYSIS")
    assert st["aggregate_source"] == "decision_traces"
    assert st["events_observed"] == 3 and st["trace_rows_observed"] == 3


def test_v1c_7_stage4_admitted_and_near_cut_are_distinct_populations(tmp_path):
    summ = _real_summary("s1", tmp_path)
    st = _stage(_report(_cfg(tmp_path), [summ], _near_traces(n=30)), "CANDIDATE_CAP_TOP_N")
    assert st["events_observed"] == 30                    # admitted candidates
    assert st["near_cut_candidates_observed"] == 30        # the other side of the line
    assert st["events_observed"] != 60                     # never merged


def test_v1c_8_summary_only_stages_1_2_3_remain_observable(tmp_path):
    rep = _report(_cfg(tmp_path), [_real_summary("s1", tmp_path)], [])
    for sid, ev in (("UNIVERSE_ADMISSION", 110), ("MARKET_DATA_ENRICHMENT", 110),
                    ("PREFILTER_SCORE_VETO", 40)):
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.OBSERVABLE, sid
        assert st["events_observed"] == ev, sid
        assert st["stage_reached"] is True, sid


def test_v1c_9_recent_unrelated_telemetry_does_not_redefine_legacy_rows(tmp_path):
    """The inverse of the 14V.1B test: RECENT real telemetry + unrelated legacy rows."""
    legacy = [_row_for_scan(f"legacy-{i}", ticker=f"L{i}") for i in range(5)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=legacy, config=_cfg(tmp_path),
        telemetry={"scan_summaries": [_real_summary("recent", tmp_path)],
                   "decision_traces": []})
    assert rep["scope"] == "MIXED"
    assert rep["legacy_alert_window"]["rows_in_report"] == 5
    assert rep["legacy_alert_window"]["rows_outside_telemetry_window"] == 5
    assert rep["telemetry_backed_rows"] == 0
    # stage counts describe the TELEMETRY population and say so
    assert "TELEMETRY SCAN population" in rep["observability_note"]
    assert "outside the telemetry scan window" in rep["observability_note"]
    # no legacy row gained row-level attribution
    assert _stage(rep, "DEDUP_AND_COOLDOWN")["shy_rows_attributed"] is None


def test_v1c_10_old_unrelated_telemetry_also_excluded(tmp_path):
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("current")], config=_cfg(tmp_path), limit=1,
        telemetry={"scan_summaries": [_real_summary("old", tmp_path), {"scan_id": "current"}],
                   "decision_traces": _fail_traces("old")})
    assert rep["telemetry_window"]["scans_in_window"] == 1
    assert rep["telemetry_window"]["traces_in_window"] == 0


def test_v1c_11_matching_scan_and_rows_work_together(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1", ticker="B1")], config=cfg,
        telemetry={"scan_summaries": [_real_summary("s1", tmp_path)],
                   "decision_traces": [_cool_trace(cfg, "C1", 1)]})
    assert rep["telemetry_backed_rows"] >= 1
    assert rep["legacy_alert_window"]["rows_outside_telemetry_window"] == 0
    assert _stage(rep, "DEDUP_AND_COOLDOWN")["shy_rows_attributed"] == 1


def test_v1c_12_telemetry_only_scan_with_no_sent_alert_still_appears(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [_real_summary("s1", tmp_path)], [_cool_trace(cfg, "C1", 1)])
    assert rep["scope"] == "TELEMETRY_ONLY"
    assert rep["total_rows"] == 1
    assert rep["class_counts"].get(ssfa.COOLDOWN_SUPPRESSED) == 1


def test_v1c_13_legacy_only_mode_is_unchanged():
    rep = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    assert rep["scope"] == "LEGACY_ONLY"
    assert "SENT ALERTS ONLY" in rep["observability_note"]
    for sid in ssfa.TELEMETRY_BACKED_STAGES:
        st = _stage(rep, sid)
        assert st["observability"] == ssfa.NOT_PERSISTED
        assert st["shy_rows_attributed"] is None


def test_v1c_14_mixed_scope_states_population_coverage(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1", ticker="B1"), _row_for_scan("legacy", ticker="L1")],
        config=cfg,
        telemetry={"scan_summaries": [_real_summary("s1", tmp_path)],
                   "decision_traces": [_cool_trace(cfg, "C1", 1)]})
    assert rep["scope"] == "MIXED"
    lw = rep["legacy_alert_window"]
    assert lw["rows_in_report"] >= 1 and lw["rows_outside_telemetry_window"] == 1


def test_v1c_15_16_17_operator_text_reflects_live_telemetry(tmp_path):
    rep = _report(_cfg(tmp_path), [_real_summary("s1", tmp_path)], [])
    note = rep["observability_note"]
    assert "no scan-level ledger" not in note
    assert "TELEMETRY IN SCOPE" in note
    probes = " ".join(rep["recommended_next_probes"])
    assert "Persist a per-scan funnel ledger" not in probes
    observed_classes = {b["cls"] for b in rep["blind_spots"] if b.get("legacy_only")}
    assert ssfa.COOLDOWN_SUPPRESSED in observed_classes
    assert ssfa.CLAUDE_NOT_ANALYZED in observed_classes
    for b in rep["blind_spots"]:
        if b.get("legacy_only"):
            assert "LEGACY ROWS ONLY" in b["reason"]


def test_v1c_18_text_shows_the_audit_window(tmp_path):
    rep = _report(_cfg(tmp_path), [_real_summary("s1", tmp_path)], [])
    text = ssfa.render_shyness_funnel_audit(rep)
    assert "__AUDIT WINDOW__" in text
    assert "Telemetry scan window:" in text
    assert "Legacy alert rows:" in text
    assert "Scope: TELEMETRY_ONLY" in text


def test_v1c_18b_unreached_stage_is_never_rendered_as_observed_zero(tmp_path):
    rep = _report(_cfg(tmp_path), [_unreached_summary("s1", tmp_path)], _fail_traces())
    text = ssfa.render_shyness_funnel_audit(rep)
    line = [l for l in text.splitlines() if "DEDUP_AND_COOLDOWN" in l and "." in l][0]
    assert "no candidate reached this stage" in line
    assert "0 shy row(s)" not in line
    assert "n/a (not persisted)" not in line


def test_v1c_19_20_21_json_exposes_window_and_evidence_without_secrets(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [_real_summary("s1", tmp_path)], [_cool_trace(cfg, "C1", 1)])
    j = ssfa.shyness_json(rep)
    assert j["scope"] == "TELEMETRY_ONLY"
    assert j["telemetry_window"]["scans_in_window"] == 1
    assert j["legacy_alert_window"]["rows_in_report"] == 0
    ev = j["stage_evidence"]["DEDUP_AND_COOLDOWN"]
    assert set(ev) <= {"evidence_available", "stage_reached", "events_observed",
                       "aggregate_source", "trace_rows_observed",
                       "near_cut_candidates_observed", "row_attribution"}
    blob = json.dumps(j)
    for secret in ("1497532086335311883", "ANTHROPIC", "DISCORD_TOKEN",
                   "allowed_user_ids", "state_file", str(tmp_path)):
        assert secret not in blob, secret


def test_v1c_24_25_check_alert_timing_and_cap_unchanged():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    scan = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    assert scan.count("state_store.check_alert(") == 1
    assert scan.index("state_store.check_alert(") < scan.index("apply_ladder_arbitration")
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


# ===========================================================================
# PHASE 14V.2 — PRODUCTION AUDIT TRUTH
# ===========================================================================
#
# Found from the first live !auditshy session:
#   A. telemetry-only benign rows were counted as shy (200 rows -> 198 "shy",
#      of which 99 were CORRECTLY_WAITING_FOR_PROOF)
#   B. Stage 10 still said "snipe_ladder is NOT persisted" while the very row
#      it described carried ladder_source = stored_scan_time
#
# LAW: telemetry provenance may change certainty; it may not change the
# definition of shyness. Correctly waiting is not missed opportunity.
# Stored evidence is stored; reconstructed evidence is reconstructed.


_WAIT_SEND = {"ok": True, "sent": False, "channel_id": None,
              "skipped_reason": "wait_no_alert", "error_type": None}
_COOL_SEND = {"ok": True, "sent": False, "channel_id": None,
              "skipped_reason": "duplicate_suppressed", "error_type": None}
_ROUTE_SEND = {"ok": True, "sent": False, "channel_id": None,
               "skipped_reason": "channel_not_configured", "error_type": "routing_failure"}


def _benign_trace(cfg, ticker, rank, scan="s1"):
    """A telemetry-only row that is CORRECTLY_WAITING_FOR_PROOF."""
    return tlm.build_decision_trace(
        scan, ticker, {}, rank, _piped(_live_result(), cfg),
        {"reason": "wait_no_alert", "should_alert": False}, _WAIT_SEND)


def _route_trace(cfg, ticker, rank, scan="s1"):
    return tlm.build_decision_trace(
        scan, ticker, {}, rank, _piped(_live_result(), cfg),
        {"reason": "new_signal", "should_alert": True}, _ROUTE_SEND)


# ---- DEFECT A: one canonical shyness predicate -----------------------------

def test_v2_canonical_is_shy_predicate():
    """10 — the single rule, applied everywhere."""
    assert ssfa.is_shy_class(ssfa.CORRECTLY_WAITING_FOR_PROOF) is False
    assert ssfa.is_shy_class(ssfa.CORRECTLY_BLOCKED_HARD_FAILURE) is False
    assert ssfa.is_shy_class(ssfa.UNCLASSIFIED) is False
    assert ssfa.is_shy_class(None) is False
    for cls in (ssfa.ONE_H_PROOF_MISSING, ssfa.TIMEFRAME_ALIGNMENT_CAP,
                ssfa.COOLDOWN_SUPPRESSED, ssfa.LADDER_CAPPED,
                ssfa.POSSIBLE_SNIPE_UNDERCALL):
        assert ssfa.is_shy_class(cls) is True, cls


def test_v2_1_legacy_benign_row_is_not_shy():
    row = _row_for_scan("legacy")
    row["one_hour_entry"]["trigger_state"] = "RETEST_IN_PROGRESS"
    out = ssfa.classify_row(row, {})
    if out["primary_class"] == ssfa.CORRECTLY_WAITING_FOR_PROOF:
        assert out["is_shy"] is False


def test_v2_2_and_3_telemetry_benign_rows_are_not_shy(tmp_path):
    """2, 3 — provenance must not change the verdict."""
    cfg = _cfg(tmp_path)
    only = ssfa._telemetry_only_row(_benign_trace(cfg, "W1", 1))
    assert only["primary_class"] == ssfa.CORRECTLY_WAITING_FOR_PROOF
    assert only["is_shy"] is False
    assert only["telemetry_only"] is True

    rep = _report(cfg, [{"scan_id": "s1"}], [_benign_trace(cfg, "W1", 1)])
    assert rep["shy_rows"] == 0


def test_v2_4_5_6_benign_row_is_visible_but_never_counted_as_shy(tmp_path):
    """4, 5, 6 — evidence retained; shyness and stage counts untouched."""
    cfg = _cfg(tmp_path)
    traces = [_benign_trace(cfg, f"W{i}", i) for i in range(99)]
    traces.append(_cool_trace(cfg, "C1", 900))
    rep = _report(cfg, [{"scan_id": "s1"}], traces, limit=200)
    assert rep["total_rows"] == 100
    assert rep["shy_rows"] == 1                                   # was 100
    assert rep["class_counts"][ssfa.CORRECTLY_WAITING_FOR_PROOF] == 99   # still visible
    assert rep["class_counts"][ssfa.COOLDOWN_SUPPRESSED] == 1
    assert rep["stage_counts"] == {"DEDUP_AND_COOLDOWN": 1}       # benign does not pollute
    assert ssfa.CORRECTLY_WAITING_FOR_PROOF not in [
        e["primary_class"] for e in rep["examples"]]              # not shown as a miss


def test_v2_7_8_9_real_shy_telemetry_rows_remain_shy(tmp_path):
    """7, 8, 9 — the fix must not suppress genuine findings."""
    cfg = _cfg(tmp_path)
    cool = ssfa._telemetry_only_row(_cool_trace(cfg, "C1", 1))
    assert cool["primary_class"] == ssfa.COOLDOWN_SUPPRESSED and cool["is_shy"] is True
    route = ssfa._telemetry_only_row(_route_trace(cfg, "R1", 2))
    assert route["primary_class"] == ssfa.ROUTING_SUPPRESSED and route["is_shy"] is True

    # a classified (non-telemetry) row carrying real caps stays shy
    row = _row_for_scan("legacy")
    row["timeframe_alignment"] = {**row["timeframe_alignment"],
                                  "conflicts": [{"layer": "daily", "reason": "below value"}]}
    row["snipe_gate_audit"] = {"promotion_state": "PROMOTION_BLOCKED",
                               "eligible_for_snipe_review": False,
                               "blocked_gate_names": ["FOUR_H_LOCATION_VALID"],
                               "missing_proofs": ["ONE_H_TRIGGER_CONFIRMED"],
                               "blocking_reasons": []}
    out = ssfa.classify_row(row, _cfg(Path(tempfile.mkdtemp())))
    assert ssfa.ONE_H_PROOF_MISSING in out["classes"]
    assert ssfa.TIMEFRAME_ALIGNMENT_CAP in out["classes"]
    assert out["is_shy"] is True


def test_v2_11_headline_obeys_one_predicate_across_provenance(tmp_path):
    """11 — mixed report: legacy + telemetry rows judged by the same rule."""
    cfg = _cfg(tmp_path)
    rows = [_row_for_scan("s1", ticker="B1")]
    traces = [_benign_trace(cfg, "W1", 1), _cool_trace(cfg, "C1", 2)]
    rep = ssfa.run_shyness_funnel_audit(
        rows=rows, config=cfg,
        telemetry={"scan_summaries": [_backed_summary("s1")], "decision_traces": traces})
    for a in rep["examples"]:
        assert ssfa.is_shy_class(a["primary_class"]) is True
    # Deterministic fixture: 1 legacy row (genuinely POSSIBLE_SNIPE_UNDERCALL),
    # 1 telemetry cooldown row (genuinely shy), 1 telemetry benign row.
    # Exactly the two genuine findings count; the benign row is excluded while
    # remaining visible in class_counts.
    assert rep["total_rows"] == 3
    assert rep["shy_rows"] == 2
    assert rep["stage_counts"] == {"LADDER_ARBITRATION": 1, "DEDUP_AND_COOLDOWN": 1}
    assert rep["class_counts"][ssfa.CORRECTLY_WAITING_FOR_PROOF] == 1
    assert ssfa.CORRECTLY_WAITING_FOR_PROOF not in [
        e["primary_class"] for e in rep["examples"]]


# ---- DEFECT B: Stage-10 provenance wording --------------------------------

def _ladder_note(rep):
    return _stage(rep, "LADDER_ARBITRATION")["note"]


def test_v2_13_legacy_only_stage10_says_reconstructed():
    rep = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    note = _ladder_note(rep)
    assert rep["scope"] == "LEGACY_ONLY"
    assert "do not carry scan-time ladder evidence" in note
    assert "reconstructed read-only" in note
    assert "RECONSTRUCTED_NOT_PROVEN" in note
    assert "STORED_SCAN_TIME" not in note


def test_v2_12_telemetry_only_stage10_says_stored(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [{"scan_id": "s1"}], [_cool_trace(cfg, "C1", 1)])
    note = _ladder_note(rep)
    assert rep["scope"] == "TELEMETRY_ONLY"
    assert "available prospectively" in note
    assert "STORED_SCAN_TIME" in note
    # must not claim every telemetry-only row is causally classified
    assert "do not by themselves imply a LADDER_CAPPED finding" in note


def test_v2_14_mixed_stage10_describes_both_populations(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("s1", ticker="B1"), _row_for_scan("legacy", ticker="L1")],
        config=cfg,
        telemetry={"scan_summaries": [_backed_summary("s1")],
                   "decision_traces": [_cool_trace(cfg, "C1", 1)]})
    note = _ladder_note(rep)
    assert rep["scope"] == "MIXED"
    assert "STORED_SCAN_TIME" in note and "RECONSTRUCTED_NOT_PROVEN" in note
    assert "never merged" in note


def test_v2_15_16_17_provenance_is_unchanged_per_row(tmp_path):
    """15, 16, 17 — no legacy row is retroactively upgraded."""
    cfg = _cfg(tmp_path)
    legacy = ssfa.classify_row(_row_for_scan("legacy"), cfg)
    assert legacy["ladder_source"] == "recomputed_from_persisted_row"
    assert legacy["ladder_attribution"] == ssfa.ATTRIBUTION_RECONSTRUCTED
    assert ssfa.LADDER_CAPPED not in legacy["classes"]

    backed = ssfa._telemetry_only_row(_cool_trace(cfg, "C1", 1))
    assert backed["ladder_source"] == "stored_scan_time"
    assert backed["ladder_attribution"] == ssfa.ATTRIBUTION_STORED


def test_v2_18_json_and_text_totals_agree(tmp_path):
    cfg = _cfg(tmp_path)
    traces = [_benign_trace(cfg, f"W{i}", i) for i in range(5)] + [_cool_trace(cfg, "C1", 9)]
    rep = _report(cfg, [{"scan_id": "s1"}], traces, limit=50)
    j = ssfa.shyness_json(rep)
    text = ssfa.render_shyness_funnel_audit(rep)
    assert j["shy_rows"] == rep["shy_rows"] == 1
    assert j["total_rows"] == rep["total_rows"] == 6
    assert f"Rows analyzed: {rep['total_rows']}" in text
    assert f"Shy rows: {rep['shy_rows']}" in text


def test_v2_19_dual_scope_window_semantics_unchanged(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_row_for_scan("legacy")], config=cfg,
        telemetry={"scan_summaries": [_backed_summary("recent")], "decision_traces": []})
    assert rep["scope"] == "MIXED"
    assert rep["legacy_alert_window"]["rows_outside_telemetry_window"] == 1
    assert rep["telemetry_window"]["scans_in_window"] == 1


def test_v2_20_audit_only_no_strategy_organ_touched():
    """20 — this phase may not modify any strategy organ."""
    import subprocess
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=".").stdout.strip()
    if not branch.startswith("phase-14v"):
        import pytest as _pytest
        _pytest.skip("phase-scoped guard — only meaningful on the Phase 14V branch")
    changed = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True, text=True, cwd=".").stdout.split()
    forbidden = ("src/scheduler.py", "src/scan_telemetry.py", "src/tiering.py",
                 "src/snipe_ladder_judgment.py", "src/snipe_blocker_taxonomy.py",
                 "src/snipe_confirmed_seal.py", "src/snipe_gate_audit.py",
                 "src/one_hour_entry.py", "src/timeframe_alignment.py",
                 "src/higher_timeframe_context.py", "src/prefilter.py",
                 "src/discord_alerts.py", "src/market_data.py",
                 "config/doctrine_config.yaml")
    for f in forbidden:
        assert f not in changed, f


# ===========================================================================
# PHASE 14V.2A — STAGE-10 PROVENANCE: AVAILABLE / CONSUMED / CAUSAL
# ===========================================================================
#
# Three states, never conflated:
#   AVAILABLE  the row carries a stored scan-time ladder
#   CONSUMED   the audit actually classified Stage 10 from that ladder
#   CAUSAL     a definitive LADDER_CAPPED was asserted for that row
#
# A persisted alert_history row satisfies all three. A telemetry-only decision
# trace satisfies only AVAILABLE: _telemetry_only_row derives its classes from
# suppression/routing/delivery and never runs the ceiling classifier.


def _sent_history_row_with_stored_ladder(cfg, ticker="SENT1", scan="s1",
                                         served="STARTER"):
    """A real post-14V alert_history row carrying the stored scan-time ladder,
    served BELOW the ladder-supported ceiling."""
    tr = _piped(_live_result(), cfg)
    state = {"tickers": {}, "meta": {}}
    state_store.record_alert(ticker, tr, state, cfg, scan)
    row = state["tickers"][ticker]["alert_history"][-1]
    row.update({"ticker": ticker, "scan_id": scan, "tier": served,
                "capital_action": "starter_only"})
    return row


def test_v2a_1_stored_history_row_uses_stored_scan_time(tmp_path):
    cfg = _cfg(tmp_path)
    row = _sent_history_row_with_stored_ladder(cfg)
    assert isinstance(row.get("snipe_ladder"), dict)          # persisted by record_alert
    out = ssfa.classify_row(row, cfg)
    assert out["ladder_source"] == "stored_scan_time"
    assert out["ladder_attribution"] == ssfa.ATTRIBUTION_STORED


def test_v2a_2_stored_history_row_can_produce_definitive_ladder_capped(tmp_path):
    """CONSUMED + CAUSAL: evidence_ceiling reads the stored ladder and the
    classifier asserts the cap."""
    cfg = _cfg(tmp_path)
    row = _sent_history_row_with_stored_ladder(cfg)
    assert row["snipe_ladder"]["existing_final_tier_recommendation"] == "SNIPE_IT"
    out = ssfa.classify_row(row, cfg)
    assert out["ceiling_tier"] == "SNIPE_IT" and out["tier"] == "STARTER"
    assert ssfa.LADDER_CAPPED in out["classes"]
    assert out["is_shy"] is True


def test_v2a_3_telemetry_only_row_exposes_ladder_but_is_not_ladder_capped(tmp_path):
    """AVAILABLE only. The ladder is displayed provenance, not a causal claim."""
    cfg = _cfg(tmp_path)
    trace = _benign_trace(cfg, "W1", 1)
    assert isinstance(trace.get("snipe_ladder"), dict)         # evidence present
    assert trace["ladder_source"] == "stored_scan_time"
    row = ssfa._telemetry_only_row(trace)
    assert row["ladder_source"] == "stored_scan_time"
    assert row["ladder_attribution"] == ssfa.ATTRIBUTION_STORED
    assert ssfa.LADDER_CAPPED not in row["classes"]            # never auto-asserted
    assert row["primary_class"] == ssfa.CORRECTLY_WAITING_FOR_PROOF
    assert row["is_shy"] is False

    # structural: the telemetry-only path does not run the Stage-10 classifier
    import inspect
    src = inspect.getsource(ssfa._telemetry_only_row)
    assert "evidence_ceiling" not in src
    assert "classify_row" not in src
    assert "LADDER_CAPPED" not in src


def test_v2a_4_telemetry_only_wording_does_not_overclaim(tmp_path):
    cfg = _cfg(tmp_path)
    rep = _report(cfg, [{"scan_id": "s1"}], [_benign_trace(cfg, "W1", 1)])
    note = _ladder_note(rep)
    assert rep["scope"] == "TELEMETRY_ONLY"
    assert "available prospectively" in note
    assert "STORED_SCAN_TIME" in note
    # must NOT claim every telemetry-only row is causally classified
    assert "do not by themselves imply a LADDER_CAPPED finding" in note
    assert "a ladder cap is causally attributable" not in note


def test_v2a_5_legacy_only_wording_unchanged_in_meaning():
    rep = ssfa.run_shyness_funnel_audit(rows=[_row_for_scan("legacy")], config={})
    note = _ladder_note(rep)
    assert rep["scope"] == "LEGACY_ONLY"
    assert "RECONSTRUCTED_NOT_PROVEN" in note
    assert "reconstructed read-only" in note
    assert "STORED_SCAN_TIME" not in note


def test_v2a_6_mixed_wording_names_availability_versus_causation(tmp_path):
    cfg = _cfg(tmp_path)
    rep = ssfa.run_shyness_funnel_audit(
        rows=[_sent_history_row_with_stored_ladder(cfg), _row_for_scan("legacy-old")],
        config=cfg,
        telemetry={"scan_summaries": [_backed_summary("s1")],
                   "decision_traces": [_benign_trace(cfg, "W1", 1)]})
    note = _ladder_note(rep)
    assert rep["scope"] == "MIXED"
    assert "STORED_SCAN_TIME" in note and "RECONSTRUCTED_NOT_PROVEN" in note
    assert "actually consumes stored ladder evidence" in note
    assert "availability alone is never a ladder cap" in note


def test_v2a_7_three_provenance_states_are_never_conflated(tmp_path):
    """CASE C: stored+consumed, stored+unconsumed, reconstructed."""
    cfg = _cfg(tmp_path)
    sent = ssfa.classify_row(_sent_history_row_with_stored_ladder(cfg), cfg)
    unsent = ssfa._telemetry_only_row(_benign_trace(cfg, "W1", 1))
    legacy = ssfa.classify_row(_row_for_scan("legacy-old"), cfg)

    assert (sent["ladder_attribution"], ssfa.LADDER_CAPPED in sent["classes"]) == \
        (ssfa.ATTRIBUTION_STORED, True)                 # available + consumed + causal
    assert (unsent["ladder_attribution"], ssfa.LADDER_CAPPED in unsent["classes"]) == \
        (ssfa.ATTRIBUTION_STORED, False)                # available only
    assert (legacy["ladder_attribution"], ssfa.LADDER_CAPPED in legacy["classes"]) == \
        (ssfa.ATTRIBUTION_RECONSTRUCTED, False)         # reconstructed, never causal


def test_v2a_8_defect_a_fixture_does_not_regress(tmp_path):
    """The 99 benign + 1 real-shy fixture still reports 1, not 100."""
    cfg = _cfg(tmp_path)
    traces = [_benign_trace(cfg, f"W{i}", i) for i in range(99)]
    traces.append(_cool_trace(cfg, "C1", 900))
    rep = _report(cfg, [{"scan_id": "s1"}], traces, limit=200)
    assert rep["total_rows"] == 100
    assert rep["shy_rows"] == 1
    assert rep["class_counts"][ssfa.CORRECTLY_WAITING_FOR_PROOF] == 99
    assert rep["stage_counts"] == {"DEDUP_AND_COOLDOWN": 1}
    assert ssfa.is_shy_class(ssfa.CORRECTLY_WAITING_FOR_PROOF) is False

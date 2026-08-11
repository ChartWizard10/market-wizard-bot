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
from pathlib import Path

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
        "telemetry": {"max_scan_summaries": 300, "max_decision_traces": 16000},
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
              tier_counts={"SNIPE_IT": 2, "STARTER": 5, "NEAR_ENTRY": 9, "WAIT": 14},
              ladder_counts={"SNIPER_A": 2, "STARTER_A": 5, "WATCH_C": 9, "PASS": 14},
              base_tier_counts={"NEAR_ENTRY": 16, "STARTER": 4, "WAIT": 10},
              check_alert_reason_counts={"new_signal": 6, "duplicate_suppressed": 3,
                                         "wait_no_alert": 14},
              delivery={"attempted": 16, "sent": 6, "failed": 10},
              claude_analyzed=30, claude_failed=0)
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
    assert s["universe"]["market_data_failure"] == 14
    assert s["universe"]["market_data_success"] == 800


def test_2_prefilter_rejection_histogram_persists(tmp_path):
    s = _summary(tmp_path)
    hist = s["prefilter"]["rejection_reason_counts"]
    assert hist["hard_veto"] == 20
    assert hist["score_below_floor"] == 20
    assert hist["veto:VETO_NO_CLEAR_STRUCTURE"] == 20
    assert s["prefilter"]["rejected_count"] == 40


def test_3_top30_admitted_count_and_cutoff_persist(tmp_path):
    s = _summary(tmp_path)
    assert s["prefilter"]["candidate_cap"] == 30
    assert s["prefilter"]["admitted_count"] == 30
    assert s["prefilter"]["cutoff_rank"] == 30
    assert s["prefilter"]["cutoff_score"] == 71          # ranked[29] == 100-29


def test_3b_cutoff_is_null_when_the_cap_did_not_bind(tmp_path):
    """No fake cutoff when fewer than `cap` candidates existed."""
    s = _summary(tmp_path, pf_result=_pf_result(n_eligible=12, cap=12))
    assert s["prefilter"]["admitted_count"] == 12
    assert s["prefilter"]["cutoff_rank"] is None
    assert s["prefilter"]["cutoff_score"] is None


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
    assert cfg["telemetry"]["max_decision_traces"] == 16000
    assert tlm._DEFAULT_MAX_SCAN_SUMMARIES == 300
    assert tlm._DEFAULT_MAX_DECISION_TRACES == 16000


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

    backed = ssfa.run_shyness_funnel_audit(
        rows=[], config={}, telemetry={"scan_summaries": [{"scan_id": "s1"}],
                                       "decision_traces": []})
    b = {s["stage"]: s for s in backed["stages"]}
    assert backed["telemetry_scans"] == 1
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
        tier_counts={"SNIPE_IT": 1}, ladder_counts={"SNIPER_A_PLUS": 1},
        base_tier_counts={"NEAR_ENTRY": 1},
        check_alert_reason_counts={"new_signal": 1},
        delivery={"attempted": 1, "sent": 1, "failed": 0},
        claude_analyzed=30, claude_failed=0)
    assert tlm.write_scan_telemetry(cfg, summary, traces) is True

    led = tlm.load_ledger(cfg)
    s = led["scan_summaries"][-1]
    assert s["universe"]["input_count"] == 814                      # stage 1
    assert s["universe"]["market_data_success"] == 800              # stage 2
    assert s["prefilter"]["rejection_reason_counts"]["hard_veto"] == 20   # stage 3
    assert s["prefilter"]["cutoff_rank"] == 30                      # stage 4
    assert s["analysis"]["claude_analyzed_count"] == 30             # stage 5
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

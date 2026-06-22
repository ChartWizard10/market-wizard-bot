"""Phase 14K — SNIPE Gate Audit Consistency Seal tests.

Live evidence that triggered this phase: HAE scan_20260622_164918_4fc48e
persisted promotion_state == PROMOTION_READY while blocked_gate_names ==
["LIVE_EDGE_SAFE"] and blocking_reasons named a HOSTILE_WICK candle veto —
an internally contradictory audit state. This is a truth-seal patch, not a
SNIPE_IT loosening: it never auto-promotes, never loosens tiering, and never
mutates final_tier/capital_action/score/routing/suppression/dedup.

Covers:
  - Builder-level seal (src/snipe_gate_audit.py): PROMOTION_READY can no
    longer coexist with a blocked gate or a missing proof in newly generated
    audit objects.
  - Score-consistency seal: a blocked LIVE_EDGE_SAFE gate can no longer leave
    a clean, unexplained perfect score.
  - Defense-in-depth (src/audit_access.py): a pre-14K historical row that
    already contains the contradiction is detected and labeled
    INCONSISTENT_AUDIT_STATE rather than POSSIBLE_UNDER_PROMOTION — and is
    never rewritten.
  - True under-promotion remains detectable when no blockers exist at all.
"""

import copy

from src import audit_access
from src import snipe_gate_audit as sga
from src import state_store as ss
from src import timeframe_alignment as tfa
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Builders (mirrors tests/test_phase_14h_snipe_gate_audit.py fixtures)
# ---------------------------------------------------------------------------

def _oh(state="RETEST_IN_PROGRESS", hold="HOLD_WEAK", sl="1H_TRIGGER_WEAK",
        al="WATCH_ONLY", closed=False, status="ENABLED", path="ACCEPTABLE",
        retest="RETEST_REAL"):
    return {
        "enabled": True, "status": status, "data_freshness": "FRESH",
        "trigger_state": state, "score": 70, "score_label": sl,
        "alert_truth_label": al,
        "pullback_retest_hold": {"retest_truth": retest, "hold_truth": hold},
        "candle_truth": {"event_type": "DISPLACEMENT" if closed else "REJECTION",
                         "closed_candle_confirms": closed},
        "location_realism": {"label": "ACCEPTABLE_BUT_NOT_IDEAL"},
        "invalidation": {"clear": True, "level": 99.5},
        "path_quality": {"path_label": path, "overhead_clear_enough": path in ("CLEAN", "ACCEPTABLE")},
    }


def _sig(retest="confirmed", hold="confirmed", overhead="clear", rr=4.0,
         risk="healthy", struct="bos", inval=True):
    return {
        "ticker": "X", "structure_event": struct, "retest_status": retest,
        "hold_status": hold, "overhead_status": overhead, "risk_reward": rr,
        "risk_realism_state": risk,
        "invalidation_level": 99.5 if inval else None,
        "invalidation_condition": "1H close below" if inval else "",
        "trigger_level": 102.0, "upgrade_trigger": "body close above 102",
        "risk_distance_pct": 1.2,
    }


def _ce(family="DISPLACEMENT", veto="NONE", reaction="ACCEPTED", status="ok"):
    return {"status": status, "candle_family": family, "candle_veto": veto,
            "level_reaction": reaction}


def _tiering(tier="STARTER", cap="starter_only", safe=True, oh=None, sig=None,
             loc="mid_zone_acceptance", ce=None, with_tf=True):
    tr = {
        "final_tier": tier, "score": 85, "safe_for_alert": safe,
        "capital_action": cap, "final_discord_channel": tier.lower(),
        "final_signal": sig if sig is not None else _sig(),
        "trade_location": {"location_state": loc},
        "candle_evidence": ce if ce is not None else _ce(),
        "one_hour_entry": oh if oh is not None else _oh(),
    }
    if with_tf:
        tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context("X", tr)
    return tr


def _build(**kw):
    return sga.build_snipe_gate_audit("X", _tiering(**kw))


_ALL_CLEAN_KW = dict(
    tier="STARTER", cap="starter_only", safe=True,
    oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
           "CONFIRMED_TRIGGER", closed=True, retest="RETEST_CORE_VALID"),
    sig=_sig("confirmed", "confirmed"),
)


# ===========================================================================
# GROUP 1 — PROMOTION_READY cannot coexist with an active blocker (builder)
# ===========================================================================

class TestBuilderSeal:
    def test_all_clean_is_still_promotion_ready(self):
        # Baseline: the legitimate "every gate genuinely clean" case must
        # still reach PROMOTION_READY — this is the true under-promotion
        # signal the doctrine explicitly wants preserved.
        a = _build(**_ALL_CLEAN_KW)
        assert a["promotion_state"] == "PROMOTION_READY"
        assert a["blocked_gates"] == []
        assert a["missing_proofs"] == []

    def test_live_edge_safe_blocked_prevents_promotion_ready(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        a = _build(**kw)
        assert a["promotion_state"] != "PROMOTION_READY"
        assert a["promotion_state"] == "PROMOTION_PENDING"
        assert any(g["gate"] == "LIVE_EDGE_SAFE" for g in a["blocked_gates"])

    def test_promotion_ready_with_blocked_gates_is_impossible(self):
        # Sweep several distinct real-world blockers; none may leave
        # promotion_state == PROMOTION_READY while blocked_gates is non-empty.
        scenarios = [
            dict(ce=_ce(veto="HOSTILE_WICK")),
            dict(ce=_ce(veto="FAILED_RETEST")),
            dict(sig=_sig("confirmed", "confirmed", overhead="blocked")),
        ]
        for extra in scenarios:
            kw = dict(_ALL_CLEAN_KW)
            kw.update(extra)
            a = _build(**kw)
            if a["blocked_gates"]:
                assert a["promotion_state"] != "PROMOTION_READY"

    def test_promotion_ready_with_missing_proofs_is_impossible(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["oh"] = None  # drop the 1H object -> several proofs become UNKNOWN
        tr = _tiering(**kw)
        a = sga.build_snipe_gate_audit("X", tr)
        if a["missing_proofs"]:
            assert a["promotion_state"] != "PROMOTION_READY"

    def test_promotion_ready_with_active_blocking_reasons_is_impossible(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        a = _build(**kw)
        non_integrity_reasons = [
            r for r in a["blocking_reasons"]
            if "appear complete but final_tier is not SNIPE_IT" not in r
        ]
        if non_integrity_reasons:
            assert a["promotion_state"] != "PROMOTION_READY"

    def test_seal_explains_the_downgrade(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        a = _build(**kw)
        assert any("downgraded from PROMOTION_READY to PROMOTION_PENDING" in r
                   for r in a["blocking_reasons"])
        # The original blocker evidence is preserved, never erased.
        assert any("LIVE_EDGE_SAFE" in r for r in a["blocking_reasons"])

    def test_no_mutation_of_source_tiering_result(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        src = _tiering(**kw)
        before = copy.deepcopy(src)
        sga.build_snipe_gate_audit("X", src)
        assert src == before


# ===========================================================================
# GROUP 2 — score consistency (raw vs effective)
# ===========================================================================

class TestScoreSeal:
    def test_clean_scenario_score_unlabeled(self):
        a = _build(**_ALL_CLEAN_KW)
        assert a["raw_snipe_score"] == a["effective_snipe_score"] == a["snipe_score"]
        assert a["score_blocked_by"] == []
        assert a["display_score_label"] is None

    def test_live_edge_block_caps_effective_score_and_labels_it(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        a = _build(**kw)
        assert a["raw_snipe_score"] == 100
        assert a["effective_snipe_score"] <= 79
        assert a["snipe_score"] == a["effective_snipe_score"]
        assert a["score_blocked_by"] == ["LIVE_EDGE_SAFE"]
        assert a["display_score_label"] == "raw/pre-block"
        # Never a clean, unexplained perfect 100 while blocked.
        assert not (a["snipe_score"] == 100 and a["score_blocked_by"])

    def test_existing_caps_unaffected(self):
        # Pre-existing cap behavior (overhead/one_h/etc.) must be untouched.
        a = _build(oh=_oh("FAILED_RETEST", "HOLD_WEAK", "NO_VALID_1H_TRIGGER", "FAILED_TRIGGER"))
        assert a["snipe_score"] <= 49
        assert a["score_blocked_by"] == []  # not a LIVE_EDGE_SAFE block


# ===========================================================================
# GROUP 3 — defense-in-depth: !audit interpretation of historical rows
# ===========================================================================

def _snipe_snap(promotion_state="PROMOTION_PENDING", blocked=None, missing=None,
                 label="STARTER_ONLY_VALID", blocking_reasons=None,
                 raw_snipe_score=None, score_blocked_by=None):
    return {
        "audit_label": label,
        "promotion_state": promotion_state,
        "snipe_score": 79 if score_blocked_by else 92,
        "raw_snipe_score": raw_snipe_score,
        "effective_snipe_score": 79 if score_blocked_by else 92,
        "score_blocked_by": score_blocked_by or [],
        "display_score_label": "raw/pre-block" if score_blocked_by else None,
        "snipe_grade": "B" if score_blocked_by else "A",
        "eligible_for_snipe_review": True,
        "blocked_gate_names": blocked if blocked is not None else [],
        "blocked_gates": blocked if blocked is not None else [],
        "missing_proofs": missing if missing is not None else [],
        "promotion_triggers": [],
        "blocking_reasons": blocking_reasons if blocking_reasons is not None else [],
        "diagnostic_sentence": "SNIPE audit: starter valid.",
    }


def _row(tier="STARTER", retest="confirmed", hold="confirmed", sga_snap=None, htf=None):
    return {
        "ticker": "HAE", "tier": tier, "scan_id": "scan_x",
        "alerted_at": "2026-06-22T16:49:18", "retest_status": retest,
        "hold_status": hold, "capital_action": "starter_only",
        "score": 80, "final_discord_channel": "starter",
        "snipe_gate_audit": sga_snap if sga_snap is not None else _snipe_snap(),
        "higher_timeframe_context": htf if htf is not None else {},
    }


class TestAuditAccessDefenseInDepth:
    def test_historical_contradictory_row_is_inconsistent_not_under_promotion(self):
        # The exact HAE-style contradiction: PROMOTION_READY persisted
        # alongside a LIVE_EDGE_SAFE block + HOSTILE_WICK blocking reason —
        # a row a pre-14K builder could have produced. Must never be
        # rewritten; must never read as under-promotion evidence.
        row = _row(sga_snap=_snipe_snap(
            promotion_state="PROMOTION_READY",
            blocked=["LIVE_EDGE_SAFE"],
            missing=[],
            blocking_reasons=[
                "LIVE_EDGE_SAFE: candle veto HOSTILE_WICK",
                "SNIPE gates appear complete but final_tier is not SNIPE_IT.",
            ],
        ))
        before = copy.deepcopy(row)
        verdict = audit_access.interpret(row)
        assert verdict["label"] == "INCONSISTENT_AUDIT_STATE"
        assert verdict["label"] != "POSSIBLE_UNDER_PROMOTION"
        assert any("active blockers remain" in n for n in verdict["notes"])
        # No rewrite of the historical row.
        assert row == before

    def test_true_under_promotion_still_detected_when_clean(self):
        row = _row(sga_snap=_snipe_snap(
            promotion_state="PROMOTION_READY", blocked=[], missing=[],
        ))
        assert audit_access.interpret(row)["label"] == "POSSIBLE_UNDER_PROMOTION"

    def test_snipe_it_tier_is_snipe_confirmed(self):
        row = _row(tier="SNIPE_IT", sga_snap=_snipe_snap(
            promotion_state="ALREADY_SNIPE", label="SNIPE_CONFIRMED",
        ))
        assert audit_access.interpret(row)["label"] == "SNIPE_CONFIRMED"

    def test_starter_with_live_edge_block_never_under_promotion(self):
        row = _row(tier="STARTER", sga_snap=_snipe_snap(
            promotion_state="PROMOTION_PENDING", blocked=["LIVE_EDGE_SAFE"],
            blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"],
        ))
        label = audit_access.interpret(row)["label"]
        assert label in ("CORRECT_STARTER", "INCONSISTENT_AUDIT_STATE")
        assert label != "POSSIBLE_UNDER_PROMOTION"

    def test_htf_contextual_block_also_disqualifies_under_promotion(self):
        row = _row(sga_snap=_snipe_snap(
            promotion_state="PROMOTION_READY", blocked=[], missing=[],
        ), htf={"blocks_snipe_contextually": True})
        verdict = audit_access.interpret(row)
        assert verdict["label"] != "POSSIBLE_UNDER_PROMOTION"
        assert verdict["label"] == "INCONSISTENT_AUDIT_STATE"

    def test_score_suffix_renders_for_blocked_score(self):
        row = _row(sga_snap=_snipe_snap(
            promotion_state="PROMOTION_PENDING", blocked=["LIVE_EDGE_SAFE"],
            blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"],
            raw_snipe_score=100, score_blocked_by=["LIVE_EDGE_SAFE"],
        ))
        text = audit_access.format_row(row)
        assert "pre-block" in text
        assert "LIVE_EDGE_SAFE" in text

    def test_score_suffix_silent_for_legacy_rows_without_new_fields(self):
        # Pre-14K persisted rows lack raw_snipe_score/score_blocked_by.
        snap = _snipe_snap()
        del snap["raw_snipe_score"]
        del snap["score_blocked_by"]
        row = _row(sga_snap=snap)
        text = audit_access.format_row(row)
        assert "pre-block" not in text

    def test_conclusions_set_includes_new_labels(self):
        assert "INCONSISTENT_AUDIT_STATE" in audit_access.CONCLUSIONS
        assert "SNIPE_CONFIRMED" in audit_access.CONCLUSIONS


# ===========================================================================
# GROUP 4 — end-to-end: builder -> persisted snapshot -> !audit interpretation
# ===========================================================================

class TestEndToEnd:
    def test_live_edge_blocked_starter_persists_and_interprets_as_correct_starter(self):
        kw = dict(_ALL_CLEAN_KW)
        kw["ce"] = _ce(veto="HOSTILE_WICK")
        tr = _tiering(**kw)
        tr["snipe_gate_audit"] = sga.build_snipe_gate_audit("HAE", tr)
        signal = dict(tr["final_signal"])
        signal.update({"ticker": "HAE", "reason": "BOS", "missing_conditions": [],
                       "scan_price": 101.2})
        tr["final_signal"] = signal
        state = {"tickers": {}, "meta": {}}
        state = record_alert("HAE", tr, state, {"state": {"max_memory_entries": 500}}, "scan1")
        row = state["tickers"]["HAE"]["alert_history"][-1]

        assert row["snipe_gate_audit"]["promotion_state"] == "PROMOTION_PENDING"
        assert row["snipe_gate_audit"]["blocked_gate_names"] == ["LIVE_EDGE_SAFE"]
        assert row["snipe_gate_audit"]["raw_snipe_score"] == 100
        assert row["snipe_gate_audit"]["effective_snipe_score"] <= 79
        assert row["snipe_gate_audit"]["score_blocked_by"] == ["LIVE_EDGE_SAFE"]

        verdict = audit_access.interpret(row)
        assert verdict["label"] == "CORRECT_STARTER"
        assert verdict["label"] != "POSSIBLE_UNDER_PROMOTION"

    def test_genuinely_clean_starter_still_flags_possible_under_promotion(self):
        tr = _tiering(**_ALL_CLEAN_KW)
        tr["snipe_gate_audit"] = sga.build_snipe_gate_audit("HAE", tr)
        signal = dict(tr["final_signal"])
        signal.update({"ticker": "HAE", "reason": "BOS", "missing_conditions": [],
                       "scan_price": 101.2})
        tr["final_signal"] = signal
        state = {"tickers": {}, "meta": {}}
        state = record_alert("HAE", tr, state, {"state": {"max_memory_entries": 500}}, "scan1")
        row = state["tickers"]["HAE"]["alert_history"][-1]

        assert row["snipe_gate_audit"]["promotion_state"] == "PROMOTION_READY"
        verdict = audit_access.interpret(row)
        assert verdict["label"] == "POSSIBLE_UNDER_PROMOTION"

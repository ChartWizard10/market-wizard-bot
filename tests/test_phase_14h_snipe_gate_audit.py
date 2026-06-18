"""Phase 14H — SNIPE_IT Gate Audit / Promotion Path Integrity tests.

Covers schema, no-mutation, the audit labels (SNIPE_CONFIRMED / STARTER_ONLY_VALID
/ NEAR_ENTRY_PENDING / WATCH_ONLY_BLOCKED / DISQUALIFIED), the PROMOTION_READY
anti-paralysis integrity concern, gate source priority, scoring/caps, and the
config-gated compact Discord line.

Doctrine under test: diagnostic only — never promotes, downgrades, routes, or
mutates scanner state; explains the decision tiering already made.
"""

import copy

from src import discord_alerts as da
from src import snipe_gate_audit as sga
from src import timeframe_alignment as tfa


# ---------------------------------------------------------------------------
# Builders
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


# ===========================================================================
# GROUP 1 — SCHEMA
# ===========================================================================

class TestSchema:
    _TOP = {
        "enabled", "status", "audit_label", "promotion_state", "snipe_score",
        "snipe_grade", "current_final_tier", "current_capital_action",
        "eligible_for_snipe_review", "passed_gates", "blocked_gates",
        "missing_proofs", "blocking_reasons", "promotion_triggers",
        "invalidation", "risk", "evidence_sources", "diagnostic_sentence",
    }

    def test_top_level_fields(self):
        a = _build()
        assert self._TOP.issubset(a.keys())

    def test_gate_entry_fields(self):
        a = _build()
        for g in a["passed_gates"] + a["blocked_gates"]:
            assert set(g.keys()) == {"gate", "status", "reason", "source"}
            assert g["status"] in sga.GATE_STATUSES
            assert g["gate"] in sga.GATE_NAMES

    def test_enums_valid(self):
        a = _build()
        assert a["status"] in sga.STATUS_VALUES
        assert a["audit_label"] in sga.AUDIT_LABELS
        assert a["promotion_state"] in sga.PROMOTION_STATES
        assert a["snipe_grade"] in sga.GRADES

    def test_missing_inputs_never_raise(self):
        for bad in (None, {}, {"final_signal": 5}, 123, "x", []):
            a = sga.build_snipe_gate_audit("X", bad)
            assert a["audit_label"] in sga.AUDIT_LABELS
            assert a["status"] in sga.STATUS_VALUES

    def test_error_object_shape(self):
        a = sga.error_snipe_gate_audit_object("boom")
        assert a["status"] == "ERROR"
        assert a["audit_label"] == "INSUFFICIENT_CONTEXT"
        assert a["snipe_grade"] == "UNKNOWN"
        assert a["snipe_score"] == 0

    def test_disabled_via_config(self):
        a = sga.build_snipe_gate_audit("X", _tiering(),
                                       config={"snipe_gate_audit": {"enabled": False}})
        assert a["status"] == "DISABLED"
        assert a["enabled"] is False


# ===========================================================================
# GROUP 2 — NO MUTATION
# ===========================================================================

class TestNoMutation:
    def test_no_field_mutation(self):
        src = _tiering(tier="STARTER", oh=_oh(), sig=_sig())
        before = copy.deepcopy(src)
        sga.build_snipe_gate_audit("X", src)
        assert src == before
        for k in ("final_tier", "capital_action", "final_discord_channel",
                  "safe_for_alert", "score", "one_hour_entry",
                  "timeframe_alignment", "trade_location", "candle_evidence"):
            assert src.get(k) == before.get(k)

    def test_determinism(self):
        src = _tiering()
        assert sga.build_snipe_gate_audit("X", src) == sga.build_snipe_gate_audit("X", src)


# ===========================================================================
# GROUP 3 — SNIPE CONFIRMED
# ===========================================================================

class TestSnipeConfirmed:
    def test_snipe_confirmed(self):
        a = _build(tier="SNIPE_IT", cap="full_quality_allowed", safe=True,
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "CONFIRMED_TRIGGER", closed=True, retest="RETEST_CORE_VALID"),
                   sig=_sig("confirmed", "confirmed"))
        assert a["audit_label"] == "SNIPE_CONFIRMED"
        assert a["promotion_state"] == "ALREADY_SNIPE"
        assert a["snipe_grade"] == "A"


# ===========================================================================
# GROUP 4 — STARTER ONLY VALID
# ===========================================================================

class TestStarterOnlyValid:
    def test_starter_only_valid(self):
        a = _build(tier="STARTER", cap="starter_only", safe=True,
                   oh=_oh("RETEST_IN_PROGRESS", "HOLD_WEAK", "1H_TRIGGER_WEAK", "WATCH_ONLY"),
                   sig=_sig("confirmed", "confirmed"))
        assert a["audit_label"] == "STARTER_ONLY_VALID"
        assert a["promotion_state"] == "PROMOTION_PENDING"
        # 1H closed-hold proof appears as a missing proof / promotion trigger.
        joined = " ".join(a["missing_proofs"]) + " ".join(a["promotion_triggers"])
        assert "ONE_H_TRIGGER_CONFIRMED" in " ".join(a["missing_proofs"])
        assert any("closed hold" in t.lower() for t in a["promotion_triggers"])


# ===========================================================================
# GROUP 5 — NEAR_ENTRY PENDING
# ===========================================================================

class TestNearEntryPending:
    def test_near_entry_pending(self):
        a = _build(tier="NEAR_ENTRY", cap="wait_no_capital", safe=False,
                   oh=_oh("HOLD_FORMING", "HOLD_WEAK", "1H_TRIGGER_FORMING", "FORMING_TRIGGER"),
                   sig=_sig("partial", "partial"))
        assert a["audit_label"] == "NEAR_ENTRY_PENDING"
        assert a["promotion_state"] == "PROMOTION_PENDING"
        assert a["promotion_triggers"]
        assert any("hold" in t.lower() for t in a["promotion_triggers"])


# ===========================================================================
# GROUP 6 — WATCH_ONLY_BLOCKED / DISQUALIFIED
# ===========================================================================

class TestWatchOnlyBlocked:
    def test_overhead_blocker_watch_only(self):
        a = _build(tier="NEAR_ENTRY", cap="wait_no_capital", safe=False,
                   oh=_oh("RETEST_IN_PROGRESS", "HOLD_WEAK", "1H_TRIGGER_WEAK", "WATCH_ONLY"),
                   sig=_sig("partial", "partial", overhead="blocked"))
        assert a["audit_label"] in ("WATCH_ONLY_BLOCKED", "DISQUALIFIED")
        assert a["promotion_state"] == "PROMOTION_BLOCKED"
        assert a["snipe_score"] <= 79

    def test_failed_one_hour_disqualified(self):
        a = _build(tier="NEAR_ENTRY", cap="wait_no_capital", safe=False,
                   oh=_oh("FAILED_RETEST", "HOLD_FAILED", "NO_VALID_1H_TRIGGER", "FAILED_TRIGGER"),
                   sig=_sig("failed", "failed"))
        assert a["audit_label"] == "DISQUALIFIED"
        assert a["promotion_state"] == "PROMOTION_BLOCKED"
        assert a["snipe_score"] <= 49


# ===========================================================================
# GROUP 7 — PROMOTION READY integrity concern (anti-paralysis)
# ===========================================================================

class TestPromotionReadyIntegrity:
    def test_starter_all_gates_pass_flags_integrity(self):
        a = _build(tier="STARTER", cap="starter_only", safe=True,
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "CONFIRMED_TRIGGER", closed=True, retest="RETEST_CORE_VALID"),
                   sig=_sig("confirmed", "confirmed"))
        assert a["promotion_state"] == "PROMOTION_READY"
        assert any("appear complete but final_tier is not SNIPE_IT" in r
                   for r in a["blocking_reasons"])

    def test_near_with_strong_1h_stays_pending_not_ready(self):
        # A NEAR_ENTRY cannot reach PROMOTION_READY: its daily permission is
        # PERMISSION_FORMING (not granted), so DAILY_PERMISSION_GRANTED is
        # legitimately UNKNOWN. The audit must not falsely declare it ready.
        a = _build(tier="NEAR_ENTRY", cap="wait_no_capital", safe=True,
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "CONFIRMED_TRIGGER", closed=True, retest="RETEST_CORE_VALID"),
                   sig=_sig("confirmed", "confirmed"))
        assert a["promotion_state"] == "PROMOTION_PENDING"
        assert a["promotion_state"] != "PROMOTION_READY"


# ===========================================================================
# GROUP 8 — GATE SOURCE PRIORITY
# ===========================================================================

class TestGateSourcePriority:
    def test_one_h_gate_uses_one_hour_entry(self):
        a = _build(oh=_oh("TRIGGER_LIVE", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "LIVE_TRIGGER", closed=True, retest="RETEST_CORE_VALID"))
        one_h = [g for g in a["passed_gates"] if g["gate"] == "ONE_H_TRIGGER_CONFIRMED"]
        assert one_h and "one_hour_entry" in one_h[0]["source"]

    def test_missing_one_hour_makes_gate_unknown(self):
        tr = _tiering()
        tr["one_hour_entry"] = None
        a = sga.build_snipe_gate_audit("X", tr)
        states = {g["gate"]: g["status"] for g in a["passed_gates"] + a["blocked_gates"]}
        # ONE_H gate not PASS/BLOCK when no 1H object → it is UNKNOWN (missing_proofs).
        assert "ONE_H_TRIGGER_CONFIRMED" not in states
        assert any("ONE_H_TRIGGER_CONFIRMED" in m for m in a["missing_proofs"])

    def test_htf_gate_uses_timeframe_alignment(self):
        a = _build()
        htf = [g for g in a["passed_gates"] + a["blocked_gates"]
               if g["gate"] == "HTF_CONTEXT_SUPPORTIVE"]
        assert htf and "timeframe_alignment" in htf[0]["source"]


# ===========================================================================
# GROUP 9 — SCORE / CAP
# ===========================================================================

class TestScoreCap:
    def test_all_critical_pass_scores_a(self):
        a = _build(tier="SNIPE_IT", cap="full_quality_allowed", safe=True,
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "CONFIRMED_TRIGGER", closed=True, retest="RETEST_CORE_VALID"),
                   sig=_sig("confirmed", "confirmed"))
        assert a["snipe_score"] >= 90
        assert a["snipe_grade"] == "A"

    def test_one_h_failed_caps_49(self):
        a = _build(oh=_oh("FAILED_RETEST", "HOLD_WEAK", "NO_VALID_1H_TRIGGER", "FAILED_TRIGGER"))
        assert a["snipe_score"] <= 49

    def test_overhead_blocker_caps_79(self):
        a = _build(sig=_sig("confirmed", "confirmed", overhead="blocked"),
                   oh=_oh("HOLD_CONFIRMED", "HOLD_CONFIRMED", "1H_TRIGGER_VALID",
                          "CONFIRMED_TRIGGER", closed=True, path="HOSTILE",
                          retest="RETEST_CORE_VALID"))
        assert a["snipe_score"] <= 79

    def test_insufficient_context_caps_74(self):
        a = sga.build_snipe_gate_audit("X", {"final_signal": {}})
        assert a["audit_label"] == "INSUFFICIENT_CONTEXT"
        assert a["snipe_score"] <= 74

    def test_grade_bands(self):
        assert sga._grade(95) == "A"
        assert sga._grade(70) == "B"
        assert sga._grade(45) == "D"
        assert sga._grade(None) == "UNKNOWN"

    def test_does_not_alter_scanner_score(self):
        src = _tiering()
        scanner_score = src["score"]
        sga.build_snipe_gate_audit("X", src)
        assert src["score"] == scanner_score


# ===========================================================================
# GROUP 10 — DISCORD COMPACT DISPLAY
# ===========================================================================

def _discord_tiering(render_line=False):
    sig = {
        "ticker": "HAE", "setup_family": "continuation", "structure_event": "bos",
        "trend_state": "fresh_expansion", "zone_type": "fvg", "trigger_level": 102.0,
        "invalidation_level": 99.5, "invalidation_condition": "1H close below",
        "risk_reward": 4.0, "overhead_status": "clear", "risk_realism_state": "healthy",
        "retest_status": "confirmed", "hold_status": "confirmed",
        "targets": [{"label": "T1", "level": 108.0}], "next_action": "monitor",
        "reason": "BOS", "capital_action": "starter_only", "scan_price": 101.2,
        "upgrade_trigger": "body close above 102",
    }
    tr = {
        "final_tier": "STARTER", "score": 80, "safe_for_alert": True,
        "capital_action": "starter_only", "final_discord_channel": "starter",
        "final_signal": sig,
        "trade_location": {"zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
                           "location_state": "mid_zone_acceptance"},
        "candle_evidence": {"status": "ok", "candle_family": "DISPLACEMENT", "candle_veto": "NONE"},
        "one_hour_entry": _oh(),
    }
    tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context("HAE", tr)
    cfg = {"snipe_gate_audit": {"render_compact_line": render_line}}
    tr["snipe_gate_audit"] = sga.build_snipe_gate_audit("HAE", tr, config=cfg)
    return tr, cfg


class TestDiscordCompactDisplay:
    def test_no_line_by_default(self):
        tr, _ = _discord_tiering(render_line=False)
        body = da.format_alert(tr)                       # no config → off
        assert "SNIPE audit:" not in body

    def test_no_line_when_config_disabled(self):
        tr, cfg = _discord_tiering(render_line=False)
        body = da.format_alert(tr, None, "", cfg)
        assert "SNIPE audit:" not in body

    def test_exactly_one_line_when_enabled(self):
        tr, cfg = _discord_tiering(render_line=True)
        body = da.format_alert(tr, None, "", cfg)
        snipe_lines = [l for l in body.splitlines() if "SNIPE audit:" in l]
        assert len(snipe_lines) == 1
        # no gate table — the line carries no per-gate breakdown
        assert "passed_gates" not in body
        assert "SNIPE_GATE_AUDIT_LINE" not in body

    def test_helper_returns_none_when_disabled(self):
        a = _build()
        assert sga.render_snipe_audit_line(a, {"snipe_gate_audit": {"render_compact_line": False}}) is None
        assert sga.render_snipe_audit_line(a, None) is None

    def test_helper_returns_single_line_when_enabled(self):
        a = _build()
        line = sga.render_snipe_audit_line(a, {"snipe_gate_audit": {"render_compact_line": True}})
        assert line is not None
        assert "\n" not in line
        assert line.count("SNIPE audit:") == 1

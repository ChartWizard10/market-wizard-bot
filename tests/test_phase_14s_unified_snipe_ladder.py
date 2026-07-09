"""Phase 14S — unified SNIPE ladder judgment engine.

One internal ladder (PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A ->
SNIPER_A_PLUS) replaces the scared binary SNIPE logic. Public Discord tiers
stay simple (NEAR_ENTRY / STARTER_ENTRY / SNIPER_ENTRY). The ladder has
authority over the final tier (arbitration upstream of the downgrade-only
seal) — it is not display-only.

FINAL LAW under test: soft proof does not bury; failed proof blocks; missing
full-size proof caps; repairing location is not broken location; HOLD_WEAK is
not failure unless price accepts failure; no fake sniper; no fear scanner.
"""

import copy
import json

from src import audit_access
from src import discord_alerts
from src import snipe_blocker_taxonomy as tax
from src import snipe_confirmed_seal as seal
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as lad
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Fixtures — arbitrary tickers; every ticker judged by the same formula
# ---------------------------------------------------------------------------

def _signal(**over):
    s = {
        "ticker": "WTS", "tier": "NEAR_ENTRY", "capital_action": "wait_no_capital",
        "discord_channel": "#near-entry-watch", "reason": "Setup forming.",
        "next_action": "Watch.", "retest_status": "confirmed", "hold_status": "confirmed",
        "structure_event": "bos", "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 4.2,
        "overhead_status": "clear", "scan_price": 101.0, "targets": [110, 118],
        "missing_conditions": ["1H closed hold"], "upgrade_trigger": "1H closed hold above 100",
        "risk_realism_state": "healthy",
    }
    s.update(over)
    return s


def _oh(**over):
    o = {
        "status": "ENABLED", "trigger_state": "RETEST_IN_PROGRESS",
        "alert_truth_label": "WATCH_ONLY", "score": 74, "score_label": "1H_TRIGGER_FORMING",
        "data_freshness": "FRESH",
        "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID", "hold_truth": "HOLD_WEAK"},
        "candle_truth": {"event_type": "NONE", "closed_candle_confirms": False},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "invalidation": {"clear": True},
    }
    o.update(over)
    return o


_TF_GRANTED_REPAIR = {
    "alignment_label": "HTF_ALIGNED_TRIGGER_PENDING",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_REPAIRING"},
}
_TF_FULL = {
    "alignment_label": "FULL_STACK_ALIGNED",
    "swing_timeframe": {"state": "PERMISSION_GRANTED"},
    "operational_timeframe": {"state": "LOCATION_VALID"},
}
_TF_FORMING = {
    "alignment_label": "HTF_ALIGNED_TRIGGER_PENDING",
    "swing_timeframe": {"state": "FORMING"},
    "operational_timeframe": {"state": "LOCATION_REPAIRING"},
}
_HTF = {"weekly_campaign_state": "HTF_CONTINUATION", "blocks_snipe_contextually": False,
        "monthly_bias": "UNKNOWN", "data_status": "OK"}


def _tr(sig=None, one="default", tf=_TF_GRANTED_REPAIR, htf=_HTF, ce=None,
        final_tier="NEAR_ENTRY", capital="wait_no_capital", channel="#near-entry-watch"):
    s = dict(sig if sig is not None else _signal())
    s["tier"] = final_tier
    s["capital_action"] = capital
    s["discord_channel"] = channel
    tr = {
        "final_tier": final_tier, "capital_action": capital,
        "final_discord_channel": channel, "safe_for_alert": True, "score": 84,
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
    return tr


def _wts():
    """The canonical WTS-style repair: BOS + FVG + daily granted + 4H repairing +
    1H retest-in-progress + retest_truth core-valid + hold bool confirmed +
    hold_truth weak + candle NONE + invalidation clear + path clean + R:R>3."""
    return _tr()


def _wdc(candle=None):
    """WDC-style full sequence (leader continuation)."""
    one = _oh(trigger_state="TRIGGER_LIVE", alert_truth_label="CONFIRMED_TRIGGER",
              pullback_retest_hold={"retest_truth": "RETEST_CORE_VALID",
                                    "hold_truth": "HOLD_CONFIRMED"},
              candle_truth=candle or {"event_type": "REJECTION", "closed_candle_confirms": False})
    return _tr(sig=_signal(tier="SNIPE_IT"), one=one, tf=_TF_FULL,
               final_tier="SNIPE_IT", capital="full_quality_allowed", channel="#snipe-signals")


def _arb(tr):
    lad.apply_ladder_arbitration(tr, {})
    return tr


# ===========================================================================
# 1 — WTS-style repair becomes STARTER_A (the missing basket)
# ===========================================================================

def test_wts_style_repair_becomes_starter_a():
    tr = _wts()
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "STARTER_A"
    assert ladder["public_signal_tier"] == "STARTER_ENTRY"
    assert ladder["proof_state"] == "ALIVE_INCOMPLETE"
    assert ladder["existing_final_tier_recommendation"] == "STARTER"
    assert ladder["capital_action_recommendation"] == "starter_only"
    assert ladder["base_alive"] is True
    assert ladder["internal_ladder_tier"] not in ("WATCH_C", "SNIPER_A")
    assert ladder["next_promotion_proof"]


# ===========================================================================
# 2 — softer thesis becomes STARTER_B
# ===========================================================================

def test_starter_b_for_softer_thesis():
    tr = _tr(tf=_TF_FORMING)  # daily only sponsored-forming under bullish weekly
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "STARTER_B"
    assert ladder["public_signal_tier"] == "STARTER_ENTRY"
    assert ladder["starter_grade"] == "STARTER_B"


# ===========================================================================
# 3 — price only falling into zone stays WATCH_C
# ===========================================================================

def test_watch_c_when_price_only_falling_into_zone():
    one = _oh(trigger_state="APPROACHING_LOCATION", alert_truth_label="NO_ALERT",
              pullback_retest_hold={"retest_truth": "NONE", "hold_truth": "NONE"})
    tr = _tr(sig=_signal(retest_status="missing", hold_status="missing"), one=one)
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "WATCH_C"
    assert ladder["public_signal_tier"] == "NEAR_ENTRY"
    assert ladder["capital_action_recommendation"] == "wait_no_capital"
    assert ladder["proof_state"] == "FORMING_NO_CAPITAL"


# ===========================================================================
# 4 — HOLD_WEAK alone is not hostile
# ===========================================================================

def test_hold_weak_alone_is_not_hostile():
    tr = _tr(one=_oh(candle_truth={"event_type": "REJECTION", "closed_candle_confirms": False}))
    cc = tax.normalized_candle_context(tr)
    assert cc["candle_context"] != "HOSTILE_REJECTION"
    ladder = lad.classify_snipe_ladder(tr)
    assert not ladder["hard_failures"]
    assert ladder["candle_state"] != "HOSTILE"


# ===========================================================================
# 5 — RETEST_IN_PROGRESS allows STARTER when base alive
# ===========================================================================

def test_retest_in_progress_allows_starter_when_base_alive():
    ladder = lad.classify_snipe_ladder(_wts())
    assert ladder["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert ladder["internal_ladder_tier"] not in ("WATCH_C", "SNIPER_A", "SNIPER_A_PLUS")


# ===========================================================================
# 6 — LOCATION_REPAIRING inside valid zone allows STARTER
# ===========================================================================

def test_location_repairing_inside_valid_zone_allows_starter():
    ladder = lad.classify_snipe_ladder(_wts())  # 4H LOCATION_REPAIRING fixture
    assert ladder["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert any("4H" in b or "location" in b.lower() or "trigger" in b.lower()
               for b in ladder["sniper_only_blockers"])


# ===========================================================================
# 7 — WATCH_ONLY split: base alive is not buried
# ===========================================================================

def test_watch_only_split_base_alive():
    tr = _wts()  # alert_truth_label WATCH_ONLY in the fixture
    assert tr["one_hour_entry"]["alert_truth_label"] == "WATCH_ONLY"
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["base_alive"] is True
    assert ladder["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert ladder["internal_ladder_tier"] not in ("WATCH_C", "SNIPER_A")


def test_watch_only_without_base_stays_watch_c():
    one = _oh(pullback_retest_hold={"retest_truth": "NONE", "hold_truth": "HOLD_WEAK"})
    tr = _tr(one=one)
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "WATCH_C"


# ===========================================================================
# 8 — hostile failure blocks all capital
# ===========================================================================

def test_hostile_failure_blocks_all_capital():
    tr = _tr(sig=_signal(scan_price=95.0))  # accepted below invalidation 96.5
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] in ("PASS", "WATCH_C")
    assert ladder["proof_state"] == "FAILED"
    assert ladder["capital_action_recommendation"] in ("wait_no_capital", "no_trade")
    assert ladder["starter_grade"] == "NONE" and ladder["sniper_grade"] == "NONE"


# ===========================================================================
# 9 — weak 1H does not become sniper
# ===========================================================================

def test_weak_1h_does_not_become_sniper():
    ladder = lad.classify_snipe_ladder(_wts())
    assert ladder["internal_ladder_tier"] not in ("SNIPER_A", "SNIPER_A_PLUS")
    assert ladder["sniper_grade"] == "NONE"


# ===========================================================================
# 10 — complete sequence becomes SNIPER_A
# ===========================================================================

def test_complete_sequence_becomes_sniper_a():
    tr = _wdc()  # defensive rejection + one soft-cap-ish context
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "SNIPER_A"
    assert ladder["public_signal_tier"] == "SNIPER_ENTRY"
    assert ladder["existing_final_tier_recommendation"] == "SNIPE_IT"
    assert ladder["proof_state"] == "COMPLETE"


# ===========================================================================
# 11 — pristine sequence becomes SNIPER_A_PLUS
# ===========================================================================

def test_pristine_sequence_becomes_sniper_a_plus():
    tr = _wdc(candle={"event_type": "DISPLACEMENT", "closed_candle_confirms": True})
    tr["higher_timeframe_context"] = {"weekly_campaign_state": "HTF_CONTINUATION",
                                      "blocks_snipe_contextually": False,
                                      "monthly_bias": "BULLISH"}
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "SNIPER_A_PLUS"
    assert ladder["proof_state"] == "PRISTINE"
    assert ladder["sniper_grade"] == "SNIPER_A_PLUS"


# ===========================================================================
# 12 — 14R open-bar veto not reintroduced
# ===========================================================================

def test_open_bar_veto_not_reintroduced():
    tr = _wdc(candle={"event_type": "DISPLACEMENT", "closed_candle_confirms": True})
    tr["higher_timeframe_context"] = {"weekly_campaign_state": "HTF_CONTINUATION",
                                      "blocks_snipe_contextually": False,
                                      "monthly_bias": "BULLISH"}
    tr["candle_evidence"] = {"status": "ok", "candle_family": "RETEST_HOLD",
                             "next_candle_verdict": "UNKNOWN", "candle_veto": "OPEN_ONLY",
                             "level_reaction": "HELD"}
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] in ("SNIPER_A", "SNIPER_A_PLUS")
    # And the seal (taxonomy path) does not re-bury it:
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WDC", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"


# ===========================================================================
# 13 — true hard failure overrides the ladder (leader cannot rescue)
# ===========================================================================

def test_true_hard_failure_overrides_ladder():
    tr = _wdc()
    tr["final_signal"]["scan_price"] = 95.0  # accepted below invalidation
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] in ("PASS", "WATCH_C")
    assert ladder["starter_grade"] == "NONE" and ladder["sniper_grade"] == "NONE"
    _arb(tr)
    assert tr["final_tier"] not in ("STARTER", "SNIPE_IT")


# ===========================================================================
# 14 — no blank PROMOTION_BLOCKED
# ===========================================================================

def test_no_blank_promotion_blocked():
    tr = _wts()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WTS", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    sgao = tr["snipe_gate_audit"]
    if str(sgao.get("promotion_state")).upper() == "PROMOTION_BLOCKED":
        c = tax.classify_blockers(tr)
        assert c["capital_blockers"] or c["snipe_only_blockers"]
    ladder = tr["snipe_ladder"]
    assert ladder["why_this_ladder_tier"] and ladder["why_not_higher"]


# ===========================================================================
# 15 — no NEAR_ENTRY promotion inside the seal
# ===========================================================================

def test_no_near_entry_promotion_inside_seal():
    tr = _tr()  # NEAR_ENTRY row
    seal.seal_snipe_confirmed_consistency(tr, {})  # seal alone, no arbitration
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert "snipe_confirmed_seal" not in tr  # seal never engaged, never promoted


def test_arbitration_never_promotes_wait():
    tr = _wts()
    tr.update({"final_tier": "WAIT", "capital_action": "no_trade",
               "final_discord_channel": "none", "safe_for_alert": False})
    tr["final_signal"]["tier"] = "WAIT"
    _arb(tr)
    assert tr["final_tier"] == "WAIT"


# ===========================================================================
# 16 — ladder persists to audit
# ===========================================================================

def test_ladder_persists_to_audit():
    tr = _wts()
    tr["final_signal"]["ticker"] = "WTS"
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WTS", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    for key in ("internal_ladder_tier", "public_signal_tier", "proof_state",
                "base_alive", "why_this_ladder_tier", "why_not_higher", "why_not_lower"):
        assert key in tr["snipe_ladder"]
    state = record_alert("WTS", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_wts")
    row = state["tickers"]["WTS"]["alert_history"][-1]
    text = audit_access.format_row(row)
    assert "__SNIPE LADDER__" in text
    for label in ("Internal ladder tier:", "Public signal tier:", "Proof state:",
                  "Base alive:", "Why this ladder tier:", "Why not higher:", "Why not lower:"):
        assert label in text, f"missing ladder label: {label}"
    json.dumps(audit_access.compact_json(row), allow_nan=False)


# ===========================================================================
# 17 — ladder distribution diagnostics (internal; auditready output unchanged)
# ===========================================================================

def test_auditready_counts_ladder():
    rows = [_wts(), _tr(tf=_TF_FORMING), _wdc(),
            _tr(sig=_signal(scan_price=95.0))]
    counts = lad.ladder_distribution(rows)
    for key in ("PASS", "WATCH_C", "STARTER_B", "STARTER_A", "SNIPER_A",
                "SNIPER_A_PLUS", "HARD_FAILURE_BLOCKED", "STARTER_BLOCKED",
                "SOFT_ONLY_BLOCKED", "FEAR_DOWNGRADE_CANDIDATE"):
        assert key in counts
    assert counts["STARTER_A"] >= 1
    assert counts["STARTER_B"] >= 1
    assert counts["SNIPER_A"] >= 1
    assert counts["HARD_FAILURE_BLOCKED"] >= 1


# ===========================================================================
# 18 — no fake sniper on missing invalidation
# ===========================================================================

def test_no_fake_sniper_missing_invalidation():
    tr = _wdc()
    tr["final_signal"]["invalidation_level"] = None
    tr["final_signal"]["invalidation_condition"] = ""
    tr["one_hour_entry"]["invalidation"] = {"clear": False}
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] in ("PASS", "WATCH_C")
    _arb(tr)
    assert tr["final_tier"] not in ("STARTER", "SNIPE_IT")


# ===========================================================================
# 19 — moderate overhead does not bury the starter
# ===========================================================================

def test_moderate_overhead_does_not_bury_starter():
    tr = _tr(sig=_signal(overhead_status="moderate"))
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert ladder["internal_ladder_tier"] not in ("SNIPER_A", "SNIPER_A_PLUS")


# ===========================================================================
# 20 — expansion rejection preserves the base
# ===========================================================================

def test_expansion_rejection_preserves_base():
    tr = _wdc(candle={"event_type": "REJECTION", "closed_candle_confirms": True})
    tr["candle_evidence"] = {"status": "ok", "candle_family": "FAILED_BREAK",
                             "next_candle_verdict": "UNKNOWN", "candle_veto": "NONE",
                             "level_reaction": "HELD"}
    cc = tax.normalized_candle_context(tr)
    assert cc["candle_context"] == "EXPANSION_REJECTION"
    assert "entry-zone retest failed" not in cc["candle_context_reason"].lower()
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] not in ("PASS", "WATCH_C")
    assert "EXPANSION_REJECTION_ADD_LEVEL_ONLY" in ladder["audit_tags"]


# ===========================================================================
# 21 — defensive rejection preserves sniper
# ===========================================================================

def test_defensive_rejection_preserves_sniper():
    tr = _wdc()  # REJECTION closed=False with full TF proof -> defensive
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["candle_state"] == "DEFENSIVE"
    assert ladder["internal_ladder_tier"] in ("SNIPER_A", "SNIPER_A_PLUS")
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WDC", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"


# ===========================================================================
# 22 — unresolved rejection with base alive floors STARTER
# ===========================================================================

def test_unresolved_rejection_with_base_alive_floors_starter():
    tr = _tr(one=_oh(candle_truth={"event_type": "REJECTION", "closed_candle_confirms": False}))
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["base_alive"] is True
    assert ladder["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert ladder["internal_ladder_tier"] != "WATCH_C"


# ===========================================================================
# 23 — STARTER_A routes to the starter channel, never the sniper channel
# ===========================================================================

def test_starter_a_routing_stays_starter_channel():
    tr = _wts()
    _arb(tr)
    assert tr["final_tier"] == "STARTER"
    assert tr["final_discord_channel"] == "#starter-signals"
    assert "snipe" not in tr["final_discord_channel"]
    assert tr["final_signal"]["discord_channel"] == "#starter-signals"


# ===========================================================================
# 24 / 25 — why-not explanations
# ===========================================================================

def test_sniper_a_has_why_not_a_plus():
    ladder = lad.classify_snipe_ladder(_wdc())
    assert ladder["internal_ladder_tier"] == "SNIPER_A"
    assert ladder["why_not_higher"].strip()
    assert "soft cap" in ladder["why_not_higher"].lower() or "pristine" in ladder["why_not_higher"].lower()


def test_sniper_a_plus_has_why_not_lower():
    tr = _wdc(candle={"event_type": "DISPLACEMENT", "closed_candle_confirms": True})
    tr["higher_timeframe_context"] = {"weekly_campaign_state": "HTF_CONTINUATION",
                                      "blocks_snipe_contextually": False,
                                      "monthly_bias": "BULLISH"}
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "SNIPER_A_PLUS"
    low = ladder["why_not_lower"].lower()
    assert "complete" in low and ("clean" in low or "no material" in low)


# ===========================================================================
# 26 — the ladder influences the final tier (not display-only)
# ===========================================================================

def test_ladder_influences_final_tier_not_display_only():
    tr = _wts()  # tiering said NEAR_ENTRY; base alive; 1H incomplete
    assert tr["final_tier"] == "NEAR_ENTRY"
    _arb(tr)
    assert tr["final_tier"] == "STARTER", "ladder must govern the final tier"
    assert tr["capital_action"] == "starter_only"
    assert tr["snipe_ladder"]["internal_ladder_tier"] == "STARTER_A"
    assert any("ladder arbitration" in n for n in tr.get("downgrades", []))


# ===========================================================================
# 27 — functionally valid repair can be sniper when the sequence completes
# ===========================================================================

def test_functionally_valid_repair_can_be_sniper_when_full_sequence_complete():
    one = _oh(trigger_state="TRIGGER_LIVE", alert_truth_label="CONFIRMED_TRIGGER",
              pullback_retest_hold={"retest_truth": "RETEST_CORE_VALID",
                                    "hold_truth": "HOLD_CONFIRMED"},
              candle_truth={"event_type": "REJECTION", "closed_candle_confirms": False})
    tr = _tr(sig=_signal(tier="SNIPE_IT"), one=one, tf=_TF_GRANTED_REPAIR,
             final_tier="SNIPE_IT", capital="full_quality_allowed", channel="#snipe-signals")
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "SNIPER_A"
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("LDR", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    assert tr["final_tier"] == "SNIPE_IT"


# ===========================================================================
# 28 — fear-downgrade candidate is countable
# ===========================================================================

def test_fear_downgrade_candidate_countable():
    tr = _wts()  # NEAR_ENTRY solely from HOLD_WEAK/RETEST_IN_PROGRESS/WATCH_ONLY
    assert lad.is_fear_downgrade_candidate(tr) is True
    counts = lad.ladder_distribution([tr])
    assert counts["FEAR_DOWNGRADE_CANDIDATE"] == 1
    # After arbitration promotes it, it is no longer a fear candidate.
    _arb(tr)
    assert lad.is_fear_downgrade_candidate(tr) is False


# ===========================================================================
# 29 — no structure family = PASS
# ===========================================================================

def test_pass_for_no_structure_family():
    tr = _tr(sig=_signal(structure_event="none"))
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "PASS"
    assert ladder["public_signal_tier"] == "SUPPRESSED"
    assert ladder["capital_action_recommendation"] == "no_trade"


# ===========================================================================
# 30 — WATCH_C never allows capital
# ===========================================================================

def test_watch_c_does_not_allow_capital():
    one = _oh(trigger_state="APPROACHING_LOCATION", alert_truth_label="NO_ALERT",
              pullback_retest_hold={"retest_truth": "NONE", "hold_truth": "NONE"})
    tr = _tr(one=one)
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["internal_ladder_tier"] == "WATCH_C"
    assert ladder["capital_action_recommendation"] == "wait_no_capital"
    _arb(tr)
    assert tr["capital_action"] == "wait_no_capital"


# ===========================================================================
# Alert lane display
# ===========================================================================

def test_starter_lane_visible_in_alert():
    tr = _wts()
    _arb(tr)
    body = discord_alerts.format_alert(tr)
    assert "Lane: STARTER_ENTRY | STARTER_A" in body
    low = body.lower()
    assert "full quality" not in low  # a starter lane never implies full size
    assert "capital authorized" not in low


def test_sniper_lane_visible_in_alert():
    tr = _wdc(candle={"event_type": "DISPLACEMENT", "closed_candle_confirms": True})
    tr["higher_timeframe_context"] = {"weekly_campaign_state": "HTF_CONTINUATION",
                                      "blocks_snipe_contextually": False,
                                      "monthly_bias": "BULLISH"}
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WDC", tr, {}, {})
    _arb(tr)
    body = discord_alerts.format_alert(tr)
    assert "Lane: SNIPER_ENTRY | SNIPER_A_PLUS" in body


def test_near_entry_alert_has_no_lane_line():
    one = _oh(trigger_state="APPROACHING_LOCATION", alert_truth_label="NO_ALERT",
              pullback_retest_hold={"retest_truth": "NONE", "hold_truth": "NONE"})
    tr = _tr(one=one)
    _arb(tr)
    body = discord_alerts.format_alert(tr)
    assert "Lane:" not in body


# ===========================================================================
# Robustness
# ===========================================================================

def test_ladder_never_raises_on_junk():
    for junk in (None, {}, [], {"final_signal": "bad"}, {"one_hour_entry": 5},
                 {"final_tier": None}, {"timeframe_alignment": "x"}):
        ladder = lad.classify_snipe_ladder(junk)
        assert ladder["internal_ladder_tier"] in lad.LADDER_TIERS
        json.dumps(ladder, allow_nan=False)
    lad.apply_ladder_arbitration(None, {})
    lad.apply_ladder_arbitration({"final_tier": 5}, {})


def test_arbitration_idempotent():
    tr = _wts()
    _arb(tr)
    first = (tr["final_tier"], tr["capital_action"])
    _arb(tr)
    assert (tr["final_tier"], tr["capital_action"]) == first


def test_full_pipeline_end_to_end_json_safe():
    tr = _wts()
    tr["final_signal"]["ticker"] = "WTS"
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("WTS", tr, {}, {})
    _arb(tr)
    seal.seal_snipe_confirmed_consistency(tr, {})
    state = record_alert("WTS", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_e2e")
    row = state["tickers"]["WTS"]["alert_history"][-1]
    json.dumps(row, allow_nan=False)
    assert row["tier"] == "STARTER"
    assert row["capital_action"] == "starter_only"


# ===========================================================================
# Phase 14S.1 — audit recompute parity
#
# Root cause: state_store.record_alert never persists a nested final_signal
# (it flattens final_signal fields onto the row's top level instead). Before
# the 14S.1 fix, snipe_ladder_judgment._card() read structure_event, R:R,
# invalidation_level/condition, scan_price, overhead_status, and trigger_level
# ONLY from `obj["final_signal"]`, so on any persisted row `signal == {}` and
# `structure` was always "" — collapsing every persisted row's recomputed
# ladder to PASS, regardless of what actually happened at scan time.
# ===========================================================================

def _flatten_to_persisted_shape(tr: dict) -> dict:
    """Mirror state_store.record_alert's shape: flatten final_signal fields
    onto the row's top level and remove the nested final_signal entirely —
    exactly what a real alert_history row looks like on disk.
    """
    signal = tr.get("final_signal") or {}
    row = {k: v for k, v in tr.items() if k != "final_signal"}
    row["tier"] = tr.get("final_tier")
    row["retest_status"] = signal.get("retest_status")
    row["hold_status"] = signal.get("hold_status")
    row["risk_reward"] = signal.get("risk_reward")
    row["invalidation_level"] = signal.get("invalidation_level")
    row["structure_event"] = signal.get("structure_event")
    row["overhead_status"] = signal.get("overhead_status")
    row["scan_price"] = signal.get("scan_price")
    row["targets"] = signal.get("targets") or []
    assert "final_signal" not in row
    return row


def test_ladder_recompute_matches_live_after_persistence_watch_c():
    tr = _wts()  # BOS + FVG-style repair; live ladder grades WATCH_C-family
    live = lad.classify_snipe_ladder(tr)
    assert live["internal_ladder_tier"] not in ("PASS",), "fixture must not be a genuine PASS"

    row = _flatten_to_persisted_shape(tr)
    recomputed = lad.classify_snipe_ladder(row)

    assert recomputed["internal_ladder_tier"] == live["internal_ladder_tier"]
    assert recomputed["internal_ladder_tier"] != "PASS"
    assert recomputed["existing_final_tier_recommendation"] == live["existing_final_tier_recommendation"]


def test_ladder_recompute_matches_live_after_persistence_sniper_a_plus():
    tr = _wdc(candle={"event_type": "DISPLACEMENT", "closed_candle_confirms": True})
    tr["higher_timeframe_context"] = {"weekly_campaign_state": "HTF_CONTINUATION",
                                      "blocks_snipe_contextually": False,
                                      "monthly_bias": "BULLISH"}
    live = lad.classify_snipe_ladder(tr)
    assert live["internal_ladder_tier"] in ("SNIPER_A", "SNIPER_A_PLUS")

    row = _flatten_to_persisted_shape(tr)
    recomputed = lad.classify_snipe_ladder(row)

    assert recomputed["internal_ladder_tier"] == live["internal_ladder_tier"]
    assert recomputed["internal_ladder_tier"] != "PASS"
    assert recomputed["existing_final_tier_recommendation"] == "SNIPE_IT"


def test_audit_ladder_source_label_recomputed():
    tr = _wts()
    row = _flatten_to_persisted_shape(tr)
    assert "snipe_ladder" not in row
    text = audit_access.format_row(row)
    assert "__SNIPE LADDER__" in text
    assert "Ladder source: recomputed_from_persisted_row" in text


def test_audit_ladder_source_label_stored():
    tr = _wts()
    live_ladder = lad.classify_snipe_ladder(tr)
    row = _flatten_to_persisted_shape(tr)
    row["snipe_ladder"] = live_ladder  # simulate a future scan-time-persisted row
    text = audit_access.format_row(row)
    assert "Ladder source: stored_scan_time" in text
    assert f"Internal ladder tier: {live_ladder['internal_ladder_tier']}" in text


def test_recompute_does_not_change_live_arbitration_contract():
    """Phase 14S.1 is a display/recompute-only patch — apply_ladder_arbitration's
    promotion rules, hard-failure blocking, and downgrade-only seal contract
    are unchanged."""
    # NEAR_ENTRY + live STARTER_A recommendation promotes only to STARTER.
    wts = _wts()
    assert wts["final_tier"] == "NEAR_ENTRY"
    _arb(wts)
    assert wts["final_tier"] == "STARTER"
    assert wts["capital_action"] == "starter_only"

    # STARTER + live SNIPER_A/A+ recommendation promotes only to SNIPE_IT.
    one = _oh(trigger_state="TRIGGER_LIVE", alert_truth_label="CONFIRMED_TRIGGER",
              pullback_retest_hold={"retest_truth": "RETEST_CORE_VALID",
                                    "hold_truth": "HOLD_CONFIRMED"},
              candle_truth={"event_type": "REJECTION", "closed_candle_confirms": False})
    starter_row = _tr(sig=_signal(tier="STARTER"), one=one, tf=_TF_FULL,
                      final_tier="STARTER", capital="starter_only", channel="#starter-signals")
    _arb(starter_row)
    assert starter_row["final_tier"] == "SNIPE_IT"
    assert starter_row["capital_action"] == "full_quality_allowed"

    # WAIT is never promoted.
    wait_row = _wts()
    wait_row.update({"final_tier": "WAIT", "capital_action": "no_trade",
                     "final_discord_channel": "none", "safe_for_alert": False})
    wait_row["final_signal"]["tier"] = "WAIT"
    _arb(wait_row)
    assert wait_row["final_tier"] == "WAIT"

    # Hard failure still blocks all capital.
    hard_fail = _tr(sig=_signal(scan_price=95.0))  # accepted below invalidation
    ladder = lad.classify_snipe_ladder(hard_fail)
    assert ladder["internal_ladder_tier"] in ("PASS", "WATCH_C")
    _arb(hard_fail)
    assert hard_fail["capital_action"] in ("wait_no_capital", "no_trade")
    assert hard_fail["final_tier"] not in ("STARTER", "SNIPE_IT")

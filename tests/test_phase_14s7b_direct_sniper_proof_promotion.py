"""Phase 14S.7B — direct sniper proof promotion.

Phase 14S capped ladder promotion at ONE rung, so a NEAR_ENTRY baseline whose
deterministic evidence was already a COMPLETE sniper sequence landed at STARTER
and had to wait another scan to reach SNIPE_IT.

14S.7B allows the direct NEAR_ENTRY -> SNIPE_IT jump, but ONLY behind a gate
that is strictly harder than the SNIPER grade alone. A SNIPER_A can be reached
on a still-open bar via the Phase 14Q defensive-rejection rule, and doctrine
forbids an open candle from creating SNIPE authority — so the two-rung jump
additionally demands EXPLICIT closed-candle confirmation, a real closed retest
and hold, a numeric invalidation, a target path, a valid R:R, an open path,
fresh data, and no HTF contextual block.

WAIT is still never promoted. The downgrade-only seal still runs afterwards and
can still veto a false promotion.
"""

import copy

from src import discord_alerts
from src import snipe_confirmed_seal as seal
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as lad


_CAP = {"SNIPE_IT": "full_quality_allowed", "STARTER": "starter_only",
        "NEAR_ENTRY": "wait_no_capital", "WAIT": "no_trade"}
_CH = {"SNIPE_IT": "#snipe-signals", "STARTER": "#starter-signals",
       "NEAR_ENTRY": "#near-entry-watch", "WAIT": "none"}


def _card(entry="NEAR_ENTRY", mutate=None):
    """A COMPLETE closed-proof sniper evidence card at the given baseline tier."""
    sig = {
        "ticker": "T", "tier": entry, "capital_action": _CAP[entry],
        "discord_channel": _CH[entry], "reason": "Setup.", "next_action": "Act.",
        "retest_status": "confirmed", "hold_status": "confirmed",
        "structure_event": "bos", "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 101.0, "targets": [110.0, 118.0],
        "missing_conditions": [], "risk_realism_state": "healthy",
    }
    oh = {
        "status": "ENABLED", "trigger_state": "TRIGGER_LIVE",
        "alert_truth_label": "CONFIRMED_TRIGGER", "score": 90, "data_freshness": "FRESH",
        "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID",
                                 "hold_truth": "HOLD_CONFIRMED"},
        "candle_truth": {"event_type": "DISPLACEMENT", "closed_candle_confirms": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "invalidation": {"clear": True},
    }
    tf = {"alignment_label": "FULL_STACK_ALIGNED", "status": "ENABLED",
          "swing_timeframe": {"state": "PERMISSION_GRANTED"},
          "operational_timeframe": {"state": "LOCATION_VALID"}}
    htf = {"weekly_campaign_state": "HTF_CONTINUATION", "blocks_snipe_contextually": False,
           "monthly_bias": "BULLISH", "data_status": "OK"}
    tr = {"final_tier": entry, "capital_action": _CAP[entry],
          "final_discord_channel": _CH[entry], "safe_for_alert": entry != "WAIT",
          "score": 90, "final_signal": sig, "one_hour_entry": oh,
          "timeframe_alignment": tf, "higher_timeframe_context": htf}
    if mutate:
        mutate(tr)
    return tr


def _full(tr):
    """Real production order: gate audit -> ladder -> seal -> 14S.5 reconciliation."""
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("T", tr, {}, {})
    lad.apply_ladder_arbitration(tr, {})
    seal.seal_snipe_confirmed_consistency(tr, {})
    sga_mod.reconcile_final_snipe_audit_state(tr)
    return tr


def _soft_cap(tr):
    """One non-blocking soft cap -> grades SNIPER_A instead of SNIPER_A_PLUS."""
    tr["one_hour_entry"]["location_realism"]["label"] = "ACCEPTABLE_BUT_NOT_IDEAL"


# ===========================================================================
# 1 / 2 — the fix: complete sniper proof promotes directly from NEAR_ENTRY
# ===========================================================================

def test_near_entry_plus_sniper_a_complete_becomes_snipe():
    tr = _full(_card("NEAR_ENTRY", _soft_cap))
    assert tr["snipe_ladder"]["internal_ladder_tier"] == "SNIPER_A"
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"
    assert tr["final_discord_channel"] == "#snipe-signals"
    assert tr["safe_for_alert"] is True
    assert lad.DIRECT_SNIPE_ALLOWED_REASON in tr["snipe_ladder"]["direct_snipe_decision"]


def test_near_entry_plus_sniper_a_plus_becomes_snipe():
    tr = _full(_card("NEAR_ENTRY"))
    assert tr["snipe_ladder"]["internal_ladder_tier"] == "SNIPER_A_PLUS"
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"


# ===========================================================================
# 3 — a STARTER-grade ladder never reaches SNIPE from NEAR_ENTRY
# ===========================================================================

def test_near_entry_plus_starter_grade_never_snipes():
    def weak(tr):
        tr["one_hour_entry"]["pullback_retest_hold"]["hold_truth"] = "HOLD_WEAK"
    tr = _full(_card("NEAR_ENTRY", weak))
    assert tr["snipe_ladder"]["internal_ladder_tier"] in ("STARTER_A", "STARTER_B")
    assert tr["final_tier"] in ("STARTER", "NEAR_ENTRY")
    assert tr["final_tier"] != "SNIPE_IT"


# ===========================================================================
# 4-10 — every incomplete-capital-proof case must stay out of SNIPE
# ===========================================================================

def _mut(**kw):
    return kw


_NEGATIVES = {
    "partial_retest_and_hold_with_1h_pending": lambda tr: (
        tr["one_hour_entry"].update({"trigger_state": "RETEST_IN_PROGRESS",
                                     "alert_truth_label": "WATCH_ONLY"}),
        tr["one_hour_entry"]["pullback_retest_hold"].update(
            {"retest_truth": "RETEST_EDGE_ONLY", "hold_truth": "HOLD_WEAK"}),
        tr["final_signal"].update({"retest_status": "partial", "hold_status": "partial"}),
    ),
    "partial_retest_only": lambda tr: tr["one_hour_entry"]["pullback_retest_hold"].update(
        {"retest_truth": "RETEST_EDGE_ONLY"}),
    "partial_hold_only": lambda tr: tr["one_hour_entry"]["pullback_retest_hold"].update(
        {"hold_truth": "HOLD_WEAK"}),
    "retest_in_progress_only": lambda tr: tr["one_hour_entry"].update(
        {"trigger_state": "RETEST_IN_PROGRESS", "alert_truth_label": "WATCH_ONLY"}),
    "no_valid_1h_trigger": lambda tr: tr["one_hour_entry"].update(
        {"trigger_state": "NO_1H_EVIDENCE", "alert_truth_label": "NO_ALERT"}),
    "missing_invalidation": lambda tr: (
        tr["final_signal"].update({"invalidation_level": None, "invalidation_condition": ""}),
        tr["one_hour_entry"]["invalidation"].update({"clear": False}),
    ),
    "invalid_rr": lambda tr: tr["final_signal"].update({"risk_reward": 1.8}),
    "no_target_path": lambda tr: tr["final_signal"].update({"targets": []}),
    "immediate_overhead_block": lambda tr: (
        tr["final_signal"].update({"overhead_status": "blocked"}),
        tr["one_hour_entry"]["path_quality"].update(
            {"path_label": "HOSTILE", "overhead_clear_enough": False}),
    ),
    "open_candle_only_no_closed_proof": lambda tr: tr["one_hour_entry"]["candle_truth"].update(
        {"closed_candle_confirms": False, "event_type": "NONE"}),
    "stale_data": lambda tr: tr["one_hour_entry"].update({"data_freshness": "STALE"}),
    "accepted_below_invalidation": lambda tr: tr["final_signal"].update({"scan_price": 95.0}),
    "htf_blocks_contextually": lambda tr: tr["higher_timeframe_context"].update(
        {"blocks_snipe_contextually": True}),
    # Phase 14S.7B: a sub-floor stop INFLATES R:R rather than earning it.
    "fake_tight_stop": lambda tr: (
        tr["final_signal"].update({"scan_price": 101.0, "invalidation_level": 100.90,
                                   "invalidation_condition": "1H close below 100.90",
                                   "risk_reward": 9.0, "targets": [110.0]}),
        tr["one_hour_entry"].update({"invalidation": {"clear": True, "level": 100.90}}),
    ),
}


def test_incomplete_capital_proof_never_reaches_snipe():
    failures = []
    for name, mut in _NEGATIVES.items():
        tr = _full(_card("NEAR_ENTRY", mut))
        if tr["final_tier"] == "SNIPE_IT":
            failures.append(name)
        assert tr["capital_action"] != "full_quality_allowed" or tr["final_tier"] != "SNIPE_IT"
    assert not failures, f"incomplete proof leaked into SNIPE: {failures}"


def test_open_candle_only_is_explicitly_blocked_with_reason():
    """Doctrine: an open candle may never create SNIPE authority. This case
    grades SNIPER_A via the 14Q defensive rule, so the gate must catch it."""
    def open_only(tr):
        tr["one_hour_entry"]["candle_truth"].update(
            {"closed_candle_confirms": False, "event_type": "NONE"})
    tr = _full(_card("NEAR_ENTRY", open_only))
    assert tr["final_tier"] != "SNIPE_IT"
    decision = tr["snipe_ladder"]["direct_snipe_decision"]
    assert lad.DIRECT_SNIPE_BLOCKED_REASON in decision
    assert "closed-candle" in decision


# ===========================================================================
# 11-13 — other baselines unchanged
# ===========================================================================

def test_wait_baseline_never_promotes_even_with_sniper_evidence():
    tr = _full(_card("WAIT"))
    assert tr["snipe_ladder"]["internal_ladder_tier"] in ("SNIPER_A", "SNIPER_A_PLUS")
    assert tr["final_tier"] == "WAIT"
    assert tr["capital_action"] == "no_trade"
    assert tr["safe_for_alert"] is False


def test_starter_baseline_still_reaches_snipe():
    tr = _full(_card("STARTER"))
    assert tr["final_tier"] == "SNIPE_IT"
    assert tr["capital_action"] == "full_quality_allowed"


def test_snipe_baseline_stays_snipe():
    tr = _full(_card("SNIPE_IT"))
    assert tr["final_tier"] == "SNIPE_IT"


# ===========================================================================
# 14 / 15 — seal sovereignty and 14S.5 audit truth after the override
# ===========================================================================

def test_seal_still_downgrades_false_direct_promotion():
    """The seal runs AFTER the override and remains sovereign."""
    def hostile(tr):
        tr["candle_evidence"] = {"status": "ok", "candle_family": "RETEST_HOLD",
                                 "next_candle_verdict": "UNKNOWN",
                                 "candle_veto": "HOSTILE_WICK", "level_reaction": "HELD"}
    tr = _full(_card("NEAR_ENTRY", hostile))
    assert (tr.get("snipe_confirmed_seal") or {}).get("applied") is True
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"
    audit = tr["snipe_gate_audit"]
    assert audit["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"
    assert audit["final_audit_reconciliation"]["seal_authoritative"] is True


def test_audit_reconciliation_reports_final_truth_after_override():
    tr = _full(_card("NEAR_ENTRY", _soft_cap))
    audit = tr["snipe_gate_audit"]
    assert tr["final_tier"] == "SNIPE_IT"
    assert audit["current_final_tier"] == "SNIPE_IT"
    assert audit["current_capital_action"] == "full_quality_allowed"
    assert audit["audit_label"] == "SNIPE_CONFIRMED"
    assert audit["promotion_state"] == "ALREADY_SNIPE"
    assert "SNIPER_A" in audit["diagnostic_sentence"]


# ===========================================================================
# 16 — Discord output for a directly-promoted SNIPE
# ===========================================================================

def test_discord_shows_full_size_and_lane_for_direct_promotion():
    tr = _full(_card("NEAR_ENTRY", _soft_cap))
    body = discord_alerts.format_alert(tr)
    assert "SNIPE_IT" in body
    assert "FULL-SIZE AUTHORIZED" in body
    assert "Lane: SNIPER_ENTRY | SNIPER_A" in body
    assert "SNIPER_A_PLUS" not in body


def test_discord_shows_a_plus_lane_for_direct_pristine_promotion():
    tr = _full(_card("NEAR_ENTRY"))
    body = discord_alerts.format_alert(tr)
    assert "Lane: SNIPER_ENTRY | SNIPER_A_PLUS" in body


# ===========================================================================
# 17 — the CB-like fixture must remain non-capital
# ===========================================================================

def test_cb_like_partial_retest_remains_near_entry_no_capital():
    """BOS + OB + strong R:R + HTF support, but partial retest/hold, 1H
    RETEST_IN_PROGRESS and no closed hold confirmation."""
    def cb(tr):
        tr["final_signal"].update({"risk_reward": 6.66, "retest_status": "partial",
                                   "hold_status": "partial", "zone_type": "OB"})
        tr["one_hour_entry"].update({"trigger_state": "RETEST_IN_PROGRESS",
                                     "alert_truth_label": "WATCH_ONLY",
                                     "score_label": "NO_VALID_1H_TRIGGER"})
        tr["one_hour_entry"]["pullback_retest_hold"].update(
            {"retest_truth": "RETEST_EDGE_ONLY", "hold_truth": "HOLD_WEAK"})
        tr["one_hour_entry"]["candle_truth"].update(
            {"event_type": "NONE", "closed_candle_confirms": False})
    tr = _full(_card("NEAR_ENTRY", cb))
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert tr["snipe_ladder"]["internal_ladder_tier"] == "WATCH_C"


# ===========================================================================
# Gate unit behavior / robustness
# ===========================================================================

def test_gate_requires_sniper_grade():
    tr = _card("NEAR_ENTRY")
    ok, reason = lad.allow_direct_near_entry_to_snipe_when_sniper_complete(
        tr, {"internal_ladder_tier": "STARTER_A"})
    assert ok is False
    assert lad.DIRECT_SNIPE_BLOCKED_REASON in reason


def test_gate_never_raises_on_junk():
    for junk in (None, {}, [], {"final_signal": "bad"}, {"one_hour_entry": 5}):
        ok, reason = lad.allow_direct_near_entry_to_snipe_when_sniper_complete(
            junk, {"internal_ladder_tier": "SNIPER_A"})
        assert ok is False
        assert isinstance(reason, str)


def test_arbitration_idempotent_after_direct_promotion():
    tr = _full(_card("NEAR_ENTRY", _soft_cap))
    first = (tr["final_tier"], tr["capital_action"])
    lad.apply_ladder_arbitration(tr, {})
    assert (tr["final_tier"], tr["capital_action"]) == first


def test_decision_reason_recorded_on_both_paths():
    allowed = _full(_card("NEAR_ENTRY", _soft_cap))
    assert lad.DIRECT_SNIPE_ALLOWED_REASON in allowed["snipe_ladder"]["direct_snipe_decision"]

    def weak(tr):
        tr["one_hour_entry"]["pullback_retest_hold"]["hold_truth"] = "HOLD_WEAK"
    blocked = _full(_card("NEAR_ENTRY", weak))
    # A STARTER-grade ladder never enters the direct gate at all.
    assert blocked["final_tier"] != "SNIPE_IT"


# ===========================================================================
# 11 — fake tight stop (Phase 14S.7B): sub-floor risk distance must not SNIPE
# ===========================================================================

def _fake_tight_stop(tr):
    """price 101.00 / invalidation 100.90 -> 0.099% risk distance, well below
    the config floor tiers.snipe_it.min_risk_distance_pct (0.35). The R:R of
    9.0 is inflated BY the fake stop, not earned."""
    tr["final_signal"].update({"scan_price": 101.0, "invalidation_level": 100.90,
                               "invalidation_condition": "1H close below 100.90",
                               "risk_reward": 9.0, "targets": [110.0]})
    tr["one_hour_entry"]["invalidation"] = {"clear": True, "level": 100.90}


def test_fake_tight_stop_never_reaches_snipe():
    tr = _full(_card("NEAR_ENTRY", _fake_tight_stop))
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] != "full_quality_allowed"
    decision = tr["snipe_ladder"]["direct_snipe_decision"]
    assert lad.DIRECT_SNIPE_BLOCKED_REASON in decision
    assert "fake tight stop" in decision


def test_fake_tight_stop_blocked_with_real_config_threshold():
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    floor = cfg["tiers"]["snipe_it"]["min_risk_distance_pct"]
    assert floor == 0.35, "doctrine floor moved — reconfirm this guard"
    tr = _card("NEAR_ENTRY", _fake_tight_stop)
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("T", tr, {}, cfg)
    lad.apply_ladder_arbitration(tr, cfg)
    seal.seal_snipe_confirmed_consistency(tr, cfg)
    assert tr["final_tier"] != "SNIPE_IT"


def test_fake_tight_stop_blocked_even_without_config():
    """config=None must fall back to the doctrine default, never to 'no floor'."""
    tr = _card("NEAR_ENTRY", _fake_tight_stop)
    ok, reason = lad.allow_direct_near_entry_to_snipe_when_sniper_complete(
        tr, lad.classify_snipe_ladder(tr), None)
    assert ok is False
    assert "fake tight stop" in reason
    assert lad._DEFAULT_MIN_RISK_DISTANCE_PCT == 0.35


def test_healthy_risk_distance_still_promotes():
    """The guard must not block a genuine, well-spaced stop."""
    tr = _full(_card("NEAR_ENTRY"))
    assert tr["final_tier"] == "SNIPE_IT"
    assert lad.DIRECT_SNIPE_ALLOWED_REASON in tr["snipe_ladder"]["direct_snipe_decision"]


# ===========================================================================
# 21 — no A- rung / no new public tier was introduced
# ===========================================================================

def test_no_a_minus_rung_or_new_public_tier_exists():
    assert not hasattr(lad, "SNIPER_A_MINUS")
    for banned in ("SNIPER_A_MINUS", "SNIPER_B", "SNIPE_LITE",
                   "MICRO_SNIPE", "AGGRESSIVE_SNIPE", "EARLY_SNIPE"):
        assert banned not in lad.LADDER_TIERS
    assert lad.LADDER_TIERS == ("PASS", "WATCH_C", "STARTER_B", "STARTER_A",
                                "SNIPER_A", "SNIPER_A_PLUS")
    # Public tier mapping unchanged: only the four existing public tiers.
    assert set(lad._TIER_ORDER) == {"WAIT", "PASS", "NEAR_ENTRY", "WATCHLIST",
                                    "STARTER", "SNIPE_IT"}
    # The one-rung whitelist itself is untouched — WAIT can never promote.
    assert lad._ALLOWED_PROMOTIONS == {("NEAR_ENTRY", "STARTER"), ("STARTER", "SNIPE_IT")}


# ===========================================================================
# Phase 14S.7B revision — the capital floor is UNIVERSAL across every
# SNIPE_IT path, not only the direct NEAR_ENTRY jump.
# ===========================================================================

def _fake_tight_stop_geometry(tr):
    """trigger 101.00 / invalidation 100.90 -> 0.099% on BOTH the
    trigger-vs-invalidation and price-vs-invalidation bases (floor 0.35%).
    The R:R of 9.0 is inflated BY the fake stop, not earned."""
    tr["final_signal"].update({"scan_price": 101.0, "trigger_level": 101.0,
                               "invalidation_level": 100.90,
                               "invalidation_condition": "1H close below 100.90",
                               "risk_reward": 9.0, "targets": [110.0]})
    tr["one_hour_entry"]["invalidation"] = {"clear": True, "level": 100.90}


def _run(entry, mutate=None, config=None):
    tr = _card(entry, mutate)
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("T", tr, {}, config or {})
    lad.apply_ladder_arbitration(tr, config)
    seal.seal_snipe_confirmed_consistency(tr, config)
    sga_mod.reconcile_final_snipe_audit_state(tr)
    return tr


def test_fake_tight_stop_blocks_snipe_from_every_baseline():
    """1-4: no baseline may output SNIPE_IT with a sub-floor stop."""
    leaked = []
    for entry in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        tr = _run(entry, _fake_tight_stop_geometry)
        if tr["final_tier"] == "SNIPE_IT" or tr["capital_action"] == "full_quality_allowed":
            leaked.append(entry)
    assert not leaked, f"fake tight stop reached SNIPE from baselines: {leaked}"


def test_fake_tight_stop_snipe_baseline_downgrades_to_no_capital():
    """3: an untouched SNIPE_IT baseline is caught by the central floor guard."""
    tr = _run("SNIPE_IT", _fake_tight_stop_geometry)
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"
    assert "fake tight stop" in tr["snipe_ladder"]["snipe_capital_floor_violation"]


def test_fake_tight_stop_near_entry_baseline_gets_no_capital():
    """4: the direct jump is refused AND the STARTER fallback is refused."""
    tr = _run("NEAR_ENTRY", _fake_tight_stop_geometry)
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["capital_action"] in ("wait_no_capital", "no_trade")


def test_healthy_risk_distance_still_snipes_from_every_baseline():
    """5-6: the guard must not block genuine, well-spaced stops."""
    for entry in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        tr = _run(entry)
        assert tr["final_tier"] == "SNIPE_IT", f"healthy card blocked from {entry}"
        assert tr["capital_action"] == "full_quality_allowed"


def test_floor_uses_config_and_falls_back_to_doctrine_default():
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["tiers"]["snipe_it"]["min_risk_distance_pct"] == 0.35
    assert lad._min_risk_distance_pct(cfg) == 0.35
    # Absent/garbage config must fall back to the doctrine floor, never to none.
    assert lad._min_risk_distance_pct(None) == 0.35
    assert lad._min_risk_distance_pct({}) == 0.35
    assert lad._min_risk_distance_pct({"tiers": {"snipe_it": {}}}) == 0.35
    # With real config the fake stop is still blocked.
    tr = _run("STARTER", _fake_tight_stop_geometry, config=cfg)
    assert tr["final_tier"] != "SNIPE_IT"


def test_floor_violation_detects_each_risk_distance_basis():
    """Explicit field, trigger-vs-invalidation, and price-vs-invalidation."""
    # explicit field below floor
    tr = _card("STARTER")
    tr["final_signal"]["risk_distance_pct"] = 0.10
    assert "fake tight stop" in (lad.snipe_capital_floor_violation(tr) or "")
    # trigger-vs-invalidation below floor
    tr2 = _card("STARTER", _fake_tight_stop_geometry)
    assert "fake tight stop" in (lad.snipe_capital_floor_violation(tr2) or "")
    # healthy card -> no violation
    assert lad.snipe_capital_floor_violation(_card("STARTER")) is None


def test_floor_guard_also_requires_invalidation_target_and_rr():
    no_inval = _card("STARTER", lambda tr: tr["final_signal"].update(
        {"invalidation_level": None}))
    assert lad.snipe_capital_floor_violation(no_inval) == "no numeric invalidation"
    no_tgt = _card("STARTER", lambda tr: tr["final_signal"].update({"targets": []}))
    assert lad.snipe_capital_floor_violation(no_tgt) == "no target path"
    bad_rr = _card("STARTER", lambda tr: tr["final_signal"].update({"risk_reward": 1.8}))
    assert "below SNIPE threshold" in (lad.snipe_capital_floor_violation(bad_rr) or "")


def test_floor_guard_never_raises_on_junk():
    for junk in (None, {}, [], {"final_signal": "bad"}, {"final_signal": {}}):
        lad.snipe_capital_floor_violation(junk)


def test_tiering_itself_also_blocks_the_fake_tight_stop():
    """Layered defense: tiering.py rejects this geometry for BOTH SNIPE_IT and
    STARTER, so it cannot legitimately reach the ladder as a capital tier."""
    import yaml
    from src import tiering
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    sig = {"trigger_level": 101.0, "invalidation_level": 100.90, "risk_reward": 9.0,
           "retest_status": "confirmed", "hold_status": "confirmed",
           "invalidation_condition": "1H close below 100.90", "targets": [110.0],
           "overhead_status": "clear", "structure_event": "bos",
           "sma_value_alignment": "supportive", "scan_price": 101.0}
    snipe = tiering._snipe_gate_failures(sig, [], 95, cfg)
    starter = tiering._starter_gate_failures(sig, [], 95, cfg)
    assert any("fragile" in str(f) for f in snipe)
    assert any("fragile" in str(f) for f in starter)


def test_seal_still_downgrade_only_after_floor_guard():
    """8: the floor guard runs inside arbitration; the seal still runs after
    and remains sovereign on real contradictions."""
    def hostile(tr):
        tr["candle_evidence"] = {"status": "ok", "candle_family": "RETEST_HOLD",
                                 "next_candle_verdict": "UNKNOWN",
                                 "candle_veto": "HOSTILE_WICK", "level_reaction": "HELD"}
    tr = _run("STARTER", hostile)
    assert (tr.get("snipe_confirmed_seal") or {}).get("applied") is True
    assert tr["final_tier"] != "SNIPE_IT"
    assert tr["snipe_gate_audit"]["audit_label"] == "SNIPE_CONFIRMATION_BLOCKED"


# ===========================================================================
# Regression lock — tiering.py never EMITS a capital tier for a fake tight stop
#
# The ladder deliberately declines to PROMOTE a violating card but never
# demotes a tier tiering itself assigned. That separation is only safe if
# tiering cannot hand such a card down as a capital tier in the first place.
# These tests lock that upstream guarantee at the public entry point
# (tiering.validate), not merely at an internal gate helper.
# ===========================================================================

def _fake_tight_stop_claude_signal(claimed_tier="STARTER"):
    """Claude-shaped signal: STARTER/SNIPE-looking structure, numeric
    invalidation, and a high APPARENT R:R (9.0) inflated by a 0.099% stop —
    far below tiers.snipe_it.min_risk_distance_pct (0.35)."""
    return {
        "ticker": "FAKE", "timestamp_et": "2026-01-15T10:30:00-05:00",
        "tier": claimed_tier, "score": 90, "setup_family": "continuation",
        "structure_event": "BOS", "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive", "zone_type": "FVG",
        "trigger_level": 101.0, "retest_status": "confirmed", "hold_status": "confirmed",
        "invalidation_condition": "1H close below 100.90", "invalidation_level": 100.90,
        "targets": [{"label": "T1", "level": 110.0, "reason": "prior high"}],
        "risk_reward": 9.0, "overhead_status": "clear", "forced_participation": "none",
        "missing_conditions": [], "upgrade_trigger": "none",
        "next_action": "Enter.", "discord_channel": "#starter-signals",
        "capital_action": "starter_only",
        "reason": "Clean BOS with FVG retest confirmed.",
    }


def _fake_asymmetry_reason_present(result) -> bool:
    """True when the emitted result names the fake-asymmetry / minimum
    risk-distance blocker (or the equivalent existing reason)."""
    blob = " ".join([
        str(result.get("rejection_reason") or ""),
        " ".join(str(d) for d in (result.get("downgrades") or [])),
        " ".join(str(n) for n in (result.get("validation_notes") or [])),
    ]).lower()
    return ("fake-asymmetry" in blob
            or "risk_window=fragile" in blob
            or "min_risk_distance" in blob
            or "risk_distance_pct" in blob)


def test_tiering_never_emits_starter_capital_for_fake_tight_stop():
    """A fake tight stop must not come out of tiering as STARTER/starter_only."""
    import yaml
    from src import tiering
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    pf = {"veto_flags": [], "prefilter_score": 90,
          "key_features": {"current_price": 101.0}}

    result = tiering.validate(_fake_tight_stop_claude_signal("STARTER"), pf, cfg)

    # The precise thing the ladder's non-demotion behavior depends on:
    assert not (result["final_tier"] == "STARTER"
                and result["capital_action"] == "starter_only"), \
        "tiering emitted STARTER capital for a sub-floor stop — ladder non-demotion is unsafe"
    # No capital tier at all, and not alertable as a capital signal.
    assert result["final_tier"] not in ("STARTER", "SNIPE_IT")
    assert result["capital_action"] not in ("starter_only", "full_quality_allowed")
    # The truthful blocker must be named.
    assert _fake_asymmetry_reason_present(result), (
        "fake-asymmetry / min-risk-distance reason missing from emitted result")


def test_tiering_never_emits_snipe_capital_for_fake_tight_stop():
    """Same card claimed as SNIPE_IT must also be refused capital."""
    import yaml
    from src import tiering
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    pf = {"veto_flags": [], "prefilter_score": 95,
          "key_features": {"current_price": 101.0}}

    result = tiering.validate(_fake_tight_stop_claude_signal("SNIPE_IT"), pf, cfg)

    assert result["final_tier"] != "SNIPE_IT"
    assert result["capital_action"] not in ("starter_only", "full_quality_allowed")
    assert _fake_asymmetry_reason_present(result)


def test_tiering_still_emits_capital_for_a_genuine_risk_distance():
    """Control: the same shape with a real stop must NOT be blocked by the
    risk-distance rule — proving these tests detect the floor, not just any
    rejection."""
    import yaml
    from src import tiering
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    sig = _fake_tight_stop_claude_signal("STARTER")
    # Genuine stop: 101.00 -> 96.50 == 4.46% risk distance.
    sig["invalidation_level"] = 96.50
    sig["invalidation_condition"] = "1H close below 96.50"
    sig["risk_reward"] = 3.4
    pf = {"veto_flags": [], "prefilter_score": 90,
          "key_features": {"current_price": 101.0}}

    result = tiering.validate(sig, pf, cfg)
    assert not _fake_asymmetry_reason_present(result), (
        "risk-distance blocker fired on a genuine 4.46% stop")
    assert result["capital_action"] in ("starter_only", "full_quality_allowed")

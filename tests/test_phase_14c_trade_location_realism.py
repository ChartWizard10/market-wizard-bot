"""Phase 14C.1 — Trade Location Realism tests.

Covers: zone classification, location-aware score calibration, elite cap,
directional wording, no-mutation invariants, and malformed-data safety.
All location logic is audit/display only — tier, capital, routing, and
suppression are never touched.
"""

import copy

from src import score_calibration as sc
from src.trade_location import (
    build_trade_location_context,
    describe_level_direction,
)
from src.discord_alerts import format_alert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# HPE-like FVG from the live audit
_HPE_FVG = {"fvg_bot": 44.575, "fvg_mid": 49.0225, "fvg_top": 53.47}


def _enriched(scan_price=45.51, fvg=_HPE_FVG, ob=None, atr=1.0, **extra) -> dict:
    e = {
        "ticker": "HPE",
        "current_price": scan_price,
        "fvg": dict(fvg) if fvg else None,
        "ob": dict(ob) if ob else None,
        "atr": atr,
        "overhead_level": 56.0,
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
        "invalidation_level": 44.0,
    }
    e.update(extra)
    return e


def _make_tr(
    final_tier: str = "SNIPE_IT",
    score: int = 88,
    risk_realism_state: str = "healthy",
    overhead_status: str = "clear",
    retest_status: str = "confirmed",
    hold_status: str = "confirmed",
    structure_event: str = "MSS",
    missing_conditions=None,
    trajectory_label: str = "REPEATED_NO_CHANGE",
    trade_location=None,
    scan_price: float = 45.51,
) -> dict:
    tr = {
        "final_tier": final_tier,
        "score": score,
        "safe_for_alert": final_tier != "WAIT",
        "final_discord_channel": {
            "SNIPE_IT":   "#snipe-signals",
            "STARTER":    "#starter-signals",
            "NEAR_ENTRY": "#near-entry-watch",
            "WAIT":       "none",
        }.get(final_tier, "none"),
        "capital_action": {
            "SNIPE_IT":   "full_quality_allowed",
            "STARTER":    "starter_only",
            "NEAR_ENTRY": "wait_no_capital",
            "WAIT":       "no_trade",
        }.get(final_tier, "no_trade"),
        "trajectory": {"label": trajectory_label, "text": ""},
        "final_signal": {
            "ticker": "HPE",
            "score": score,
            "scan_price": scan_price,
            "zone_type": "FVG",
            "risk_realism_state": risk_realism_state,
            "overhead_status": overhead_status,
            "retest_status": retest_status,
            "hold_status": hold_status,
            "structure_event": structure_event,
            "missing_conditions": missing_conditions if missing_conditions is not None else [],
            "invalidation_level": 44.0,
        },
    }
    if trade_location is not None:
        tr["trade_location"] = trade_location
    return tr


def _loc(tr_kwargs=None, enriched_kwargs=None) -> dict:
    tr = _make_tr(**(tr_kwargs or {}))
    return build_trade_location_context(_enriched(**(enriched_kwargs or {})), tr)


# ---------------------------------------------------------------------------
# 1. FVG lower-zone defense classification (HPE live audit numbers)
# ---------------------------------------------------------------------------

def test_fvg_lower_zone_defense_classification():
    ctx = build_trade_location_context(
        _enriched(scan_price=45.51),
        _make_tr(scan_price=45.51),
    )
    assert ctx["zone_type"] == "FVG"
    assert ctx["zone_low"] == 44.575
    assert ctx["zone_mid"] == 49.0225
    assert ctx["zone_high"] == 53.47
    assert ctx["location_state"] == "lower_zone_defense"
    assert ctx["confirmation_level"] == 49.0225
    assert ctx["location_pressure"] == "low_zone_pressure"
    assert "lower-zone defense" in ctx["display_text"]
    assert "49.02" in ctx["display_text"]


def test_classification_boundaries():
    # below zone low → failure
    assert _loc({"scan_price": 44.0}, {"scan_price": 44.0})["location_state"] == "below_zone_failure"
    # at zone low → defense
    assert _loc({"scan_price": 44.575}, {"scan_price": 44.575})["location_state"] == "lower_zone_defense"
    # at zone mid → acceptance
    assert _loc({"scan_price": 49.0225}, {"scan_price": 49.0225})["location_state"] == "mid_zone_acceptance"
    # at zone high → acceptance
    assert _loc({"scan_price": 53.47}, {"scan_price": 53.47})["location_state"] == "mid_zone_acceptance"
    # just above zone high (within 0.75*ATR=0.75) → expansion
    assert _loc({"scan_price": 53.9}, {"scan_price": 53.9})["location_state"] == "upper_zone_expansion"
    # well above zone high → extension
    assert _loc({"scan_price": 55.0}, {"scan_price": 55.0})["location_state"] == "above_zone_extension"


def test_mid_zone_confirmation_is_zone_high():
    ctx = _loc({"scan_price": 50.0}, {"scan_price": 50.0})
    assert ctx["location_state"] == "mid_zone_acceptance"
    assert ctx["confirmation_level"] == 53.47


def test_ob_zone_extraction():
    ob = {"ob_lo": 100.0, "ob_core": 102.5, "ob_hi": 105.0}
    tr = _make_tr(scan_price=101.0)
    tr["final_signal"]["zone_type"] = "OB"
    ctx = build_trade_location_context(
        _enriched(scan_price=101.0, fvg=None, ob=ob), tr
    )
    assert ctx["zone_type"] == "OB"
    assert ctx["zone_low"] == 100.0
    assert ctx["zone_mid"] == 102.5
    assert ctx["zone_high"] == 105.0
    assert ctx["location_state"] == "lower_zone_defense"


def test_signal_zone_type_preferred_when_both_zones_exist():
    ob = {"ob_lo": 100.0, "ob_core": 102.5, "ob_hi": 105.0}
    tr = _make_tr(scan_price=45.51)          # zone_type=FVG in signal
    ctx = build_trade_location_context(
        _enriched(scan_price=45.51, ob=ob), tr
    )
    assert ctx["zone_type"] == "FVG"


# ---------------------------------------------------------------------------
# 2. SNIPE_IT lower-zone defense cannot calibrate to 90+
# ---------------------------------------------------------------------------

def test_snipe_lower_zone_defense_cannot_reach_90():
    loc = _loc()
    assert loc["location_state"] == "lower_zone_defense"
    tr = _make_tr(score=88, trade_location=loc)
    cal = sc.calibrate_score(tr)
    assert cal["calibrated_score"] <= 89
    assert cal["raw_score"] == 88
    assert tr["score"] == 88                       # raw score untouched


def test_snipe_lower_zone_repeated_gets_extra_penalty():
    loc = _loc()
    repeated = sc.calibrate_score(_make_tr(score=88, trade_location=loc,
                                           trajectory_label="REPEATED_NO_CHANGE"))
    new_sig  = sc.calibrate_score(_make_tr(score=88, trade_location=loc,
                                           trajectory_label="NEW_SIGNAL"))
    assert repeated["calibrated_score"] < new_sig["calibrated_score"]


def test_snipe_below_zone_failure_heavy_penalty():
    loc = _loc({"scan_price": 44.0}, {"scan_price": 44.0})
    assert loc["location_state"] == "below_zone_failure"
    cal = sc.calibrate_score(_make_tr(score=88, trade_location=loc))
    assert cal["calibrated_score"] <= 88 - 8 + 4   # floor math: never near elite
    assert cal["calibrated_score"] < 89


def test_snipe_above_zone_extension_penalized():
    loc = _loc({"scan_price": 56.0}, {"scan_price": 56.0})
    assert loc["location_state"] == "above_zone_extension"
    with_loc = sc.calibrate_score(_make_tr(score=88, trade_location=loc))
    without  = sc.calibrate_score(_make_tr(score=88))
    assert with_loc["calibrated_score"] < without["calibrated_score"]


# ---------------------------------------------------------------------------
# 3. SNIPE_IT mid-zone acceptance can remain elite
# ---------------------------------------------------------------------------

def test_snipe_mid_zone_acceptance_can_reach_90():
    loc = _loc({"scan_price": 50.0}, {"scan_price": 50.0})
    assert loc["location_state"] == "mid_zone_acceptance"
    # raw 88, clear overhead (+1), MSS (+1), healthy risk, repeated (0) → 90
    cal = sc.calibrate_score(_make_tr(score=88, trade_location=loc,
                                      scan_price=50.0))
    assert cal["calibrated_score"] == 90
    assert cal["score_band"] == "elite"


def test_snipe_upper_zone_expansion_bonus_requires_clean_path():
    loc = _loc({"scan_price": 53.9}, {"scan_price": 53.9})
    assert loc["location_state"] == "upper_zone_expansion"
    clean   = sc.calibrate_score(_make_tr(score=84, trade_location=loc,
                                          overhead_status="clear"))
    fragile = sc.calibrate_score(_make_tr(score=84, trade_location=loc,
                                          overhead_status="clear",
                                          risk_realism_state="fragile"))
    # bonus only on the clean variant
    assert any("location=upper_zone_expansion" in r for r in clean["reasons"])
    assert not any("location=upper_zone_expansion" in r for r in fragile["reasons"])


# ---------------------------------------------------------------------------
# 4. STARTER behavior preserved (QLYS/HALO-like)
# ---------------------------------------------------------------------------

def test_starter_moderate_overhead_normal_location_preserved():
    loc = _loc({"scan_price": 50.0}, {"scan_price": 50.0})   # mid-zone, 0 delta
    tr = _make_tr(final_tier="STARTER", score=78, overhead_status="moderate",
                  trade_location=loc, scan_price=50.0)
    baseline = sc.calibrate_score(_make_tr(final_tier="STARTER", score=78,
                                           overhead_status="moderate",
                                           scan_price=50.0))
    cal = sc.calibrate_score(tr)
    assert cal["calibrated_score"] == baseline["calibrated_score"]
    assert tr["final_tier"] == "STARTER"
    assert tr["capital_action"] == "starter_only"
    assert tr["final_discord_channel"] == "#starter-signals"


def test_starter_lower_zone_defense_minus_one():
    loc = _loc()
    with_loc = sc.calibrate_score(_make_tr(final_tier="STARTER", score=78,
                                           trade_location=loc))
    without  = sc.calibrate_score(_make_tr(final_tier="STARTER", score=78))
    assert with_loc["calibrated_score"] == without["calibrated_score"] - 1


# ---------------------------------------------------------------------------
# 5. NEAR_ENTRY behavior preserved (LPRO/STX-like)
# ---------------------------------------------------------------------------

def test_near_entry_missing_retest_remains_no_capital():
    loc = _loc()
    tr = _make_tr(final_tier="NEAR_ENTRY", score=62,
                  retest_status="missing", hold_status="missing",
                  trade_location=loc)
    baseline = sc.calibrate_score(_make_tr(final_tier="NEAR_ENTRY", score=62,
                                           retest_status="missing",
                                           hold_status="missing"))
    cal = sc.calibrate_score(tr)
    # location applies NO additional NEAR_ENTRY penalty (no double-counting)
    assert cal["calibrated_score"] == baseline["calibrated_score"]
    assert tr["final_tier"] == "NEAR_ENTRY"
    assert tr["capital_action"] == "wait_no_capital"


def test_near_entry_location_never_upgrades():
    loc = _loc({"scan_price": 50.0}, {"scan_price": 50.0})   # favorable location
    tr = _make_tr(final_tier="NEAR_ENTRY", score=62, trade_location=loc,
                  scan_price=50.0)
    cal = sc.calibrate_score(tr)
    assert not any("location=" in r for r in cal["reasons"])
    assert tr["final_tier"] == "NEAR_ENTRY"


# ---------------------------------------------------------------------------
# 6. Directional wording helper
# ---------------------------------------------------------------------------

def test_describe_level_above_price_no_dip_language():
    text = describe_level_direction(45.51, 49.0225, "FVG mid")
    assert "dip toward" not in text.lower()
    assert "reclaim" in text.lower() or "acceptance above" in text.lower()
    assert "49.02" in text


def test_describe_level_below_price_allows_pullback():
    text = describe_level_direction(50.0, 49.0225, "FVG mid")
    assert "pullback" in text.lower() or "dip" in text.lower()
    assert "49.02" in text


def test_describe_level_equal_and_invalid():
    eq = describe_level_direction(49.0, 49.0, "FVG mid")
    assert "continued acceptance" in eq.lower()
    assert describe_level_direction(None, 49.0, "x") == ""
    assert describe_level_direction(49.0, None, "x") == ""
    assert describe_level_direction("garbage", 49.0, "x") == ""


def test_format_alert_rewrites_dip_toward_when_level_above_price():
    loc = _loc()
    assert loc["confirmation_level"] > loc["scan_price"]
    tr = _make_tr(score=88, trade_location=loc)
    tr["final_signal"].update({
        "setup_family": "continuation",
        "trend_state": "fresh_expansion",
        "zone_type": "FVG",
        "trigger_level": 45.0,
        "invalidation_condition": "Daily close below FVG base",
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
        "risk_reward": 3.5,
        "next_action": "Enter on any intrabar dip toward FVG midpoint (49.02)",
        "reason": "Clean MSS with FVG retest confirmed.",
        "capital_action": "full_quality_allowed",
        "upgrade_trigger": "none",
        "forced_participation": "none",
    })
    text = format_alert(tr)
    assert "dip toward" not in text.lower()
    assert "push toward" in text.lower()


def test_format_alert_renders_location_line():
    loc = _loc()
    tr = _make_tr(score=88, trade_location=loc)
    tr["final_signal"].update({
        "setup_family": "continuation",
        "trend_state": "fresh_expansion",
        "trigger_level": 45.0,
        "invalidation_condition": "Daily close below FVG base",
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
        "risk_reward": 3.5,
        "next_action": "Watch for acceptance above FVG mid.",
        "reason": "Clean MSS with FVG retest confirmed.",
        "capital_action": "full_quality_allowed",
        "upgrade_trigger": "none",
        "forced_participation": "none",
    })
    text = format_alert(tr)
    assert "Location: lower-zone defense" in text
    assert "49.02" in text
    # quality read acknowledges zone defense for SNIPE_IT
    assert "Zone defense active" in text


def test_format_alert_no_location_line_when_unknown():
    tr = _make_tr(score=88)                       # no trade_location at all
    tr["final_signal"].update({
        "setup_family": "continuation",
        "trend_state": "fresh_expansion",
        "trigger_level": 45.0,
        "invalidation_condition": "Daily close below FVG base",
        "targets": [{"label": "T1", "level": 55.0, "reason": "pool"}],
        "risk_reward": 3.5,
        "next_action": "Watch.",
        "reason": "Clean MSS.",
        "capital_action": "full_quality_allowed",
        "upgrade_trigger": "none",
        "forced_participation": "none",
    })
    text = format_alert(tr)
    assert "Location:" not in text


# ---------------------------------------------------------------------------
# 7. No-mutation invariants
# ---------------------------------------------------------------------------

def test_calibration_with_location_mutates_nothing():
    loc = _loc()
    tr = _make_tr(score=88, trade_location=loc)
    before = copy.deepcopy(tr)
    sc.calibrate_score(tr)
    assert tr["score"] == before["score"]
    assert tr["final_tier"] == before["final_tier"]
    assert tr["capital_action"] == before["capital_action"]
    assert tr["final_discord_channel"] == before["final_discord_channel"]
    assert tr["safe_for_alert"] == before["safe_for_alert"]
    assert tr["final_signal"] == before["final_signal"]
    assert tr["trade_location"] == before["trade_location"]


def test_build_context_mutates_nothing():
    enriched = _enriched()
    tr = _make_tr()
    e_before = copy.deepcopy(enriched)
    t_before = copy.deepcopy(tr)
    build_trade_location_context(enriched, tr)
    assert enriched == e_before
    assert tr == t_before


# ---------------------------------------------------------------------------
# 8. Malformed / missing data safety
# ---------------------------------------------------------------------------

def test_empty_enriched_returns_unknown():
    ctx = build_trade_location_context({}, None)
    assert ctx["location_state"] == "unknown"
    assert ctx["zone_type"] == "none"
    assert ctx["display_text"] == ""
    assert ctx["flags"] == []


def test_none_and_garbage_inputs_never_raise():
    assert build_trade_location_context(None, None)["location_state"] == "unknown"
    assert build_trade_location_context(
        {"fvg": "garbage", "ob": 12, "current_price": "abc", "atr": None}, {}
    )["location_state"] == "unknown"
    # inverted zone (high <= low) → unknown, no crash
    bad = build_trade_location_context(
        {"fvg": {"fvg_bot": 50.0, "fvg_mid": 49.0, "fvg_top": 48.0},
         "current_price": 49.0},
        _make_tr(scan_price=49.0),
    )
    assert bad["location_state"] == "unknown"


def test_missing_zone_data_calibration_safe():
    ctx = build_trade_location_context({"current_price": 45.0}, _make_tr())
    assert ctx["location_state"] == "unknown"
    tr = _make_tr(score=88, trade_location=ctx)
    baseline = sc.calibrate_score(_make_tr(score=88))
    cal = sc.calibrate_score(tr)
    assert cal["calibrated_score"] == baseline["calibrated_score"]


def test_trade_location_none_calibration_safe():
    tr = _make_tr(score=88)
    tr["trade_location"] = None
    cal = sc.calibrate_score(tr)
    assert cal["raw_score"] == 88
    assert isinstance(cal["calibrated_score"], int)


def test_absent_location_does_not_block_existing_elite_path():
    # Pre-14C.1 behavior preserved: no trade_location key → elite still reachable
    cal = sc.calibrate_score(_make_tr(score=88))
    assert cal["calibrated_score"] == 90
    assert cal["score_band"] == "elite"


# ---------------------------------------------------------------------------
# HPE end-to-end expectation: honest wording, no 90 below FVG mid
# ---------------------------------------------------------------------------

def test_hpe_like_display_is_honest():
    loc = _loc()
    tr = _make_tr(score=88, trade_location=loc)
    cal = sc.calibrate_score(tr)
    assert cal["calibrated_score"] < 90
    assert "lower-zone defense" in cal["primary_reason"]

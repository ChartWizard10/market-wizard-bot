"""Phase 14S.2 — operator-facing dollar price display formatting.

A price must look like a price: every human-facing equity price gets a
leading '$'. Scores, R:R ratios, percentages, timeframe labels, SMA periods,
DTE, volume, counts, timestamps, and IDs are NEVER touched.

This is a display-truth phase only: no strategy, tiering, scoring, capital,
or routing change. Numeric schema values remain numeric internally; only the
rendered text gains '$'.
"""

import copy
import json

from src import audit_access
from src import discord_alerts
from src import snipe_gate_audit as sga_mod
from src import snipe_ladder_judgment as lad
from src.display_formatting import (
    format_price_level_text,
    format_usd_price,
    format_usd_price_list,
    format_usd_range,
)
from src.state_store import record_alert


# ===========================================================================
# 1-8 — core format_usd_price contract
# ===========================================================================

def test_whole_dollar_formats_without_cents():
    assert format_usd_price(100) == "$100"


def test_decimal_price_formats_with_two_cents():
    assert format_usd_price(100.5) == "$100.50"


def test_thousands_separator_applied():
    assert format_usd_price(1250.5) == "$1,250.50"


def test_sub_dollar_price_formats_correctly():
    assert format_usd_price(0.85) == "$0.85"


def test_numeric_string_formats_as_price():
    assert format_usd_price("100.50") == "$100.50"


def test_missing_price_formats_as_dash():
    assert format_usd_price(None) == "—"
    assert format_usd_price("") == "—"
    assert format_usd_price("not a number") == "—"


def test_nonfinite_price_formats_as_dash():
    assert format_usd_price(float("nan")) == "—"
    assert format_usd_price(float("inf")) == "—"
    assert format_usd_price(float("-inf")) == "—"


def test_helper_is_idempotent():
    assert format_usd_price("$100") == "$100"
    assert format_usd_price(format_usd_price(100)) == "$100"
    assert "$$" not in format_usd_price("$100")


# ===========================================================================
# Extra format_usd_price coverage (long float tails, negatives, whole int)
# ===========================================================================

def test_no_floating_point_tail_exposed():
    assert format_usd_price(100.4999999997) == "$100.50"


def test_negative_price_style():
    assert format_usd_price(-5) == "-$5"
    assert format_usd_price(-5.25) == "-$5.25"


def test_whole_dollar_thousands_no_cents():
    assert format_usd_price(1250) == "$1,250"


def test_usd_price_list_and_range_helpers():
    assert format_usd_price_list([110, 118.25]) == "$110, $118.25"
    assert format_usd_range(98.50, 101.25) == "$98.50–$101.25"


# ===========================================================================
# 9 — underlying numeric schema unchanged
# ===========================================================================

def test_underlying_numeric_schema_unchanged():
    signal = {
        "ticker": "AAPL", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 182.50, "invalidation_level": 178.20,
        "invalidation_condition": "1H close below 178.20", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 182.50,
        "targets": [195.00, 210.5], "missing_conditions": [],
    }
    original = copy.deepcopy(signal)
    tr = {"final_tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
          "final_discord_channel": "#snipe-signals", "safe_for_alert": True,
          "score": 90, "final_signal": signal}

    discord_alerts.format_alert(tr)

    assert signal == original
    assert isinstance(signal["scan_price"], float)
    assert isinstance(signal["invalidation_level"], float)
    assert isinstance(signal["trigger_level"], float)
    assert all(isinstance(t, (int, float)) for t in signal["targets"])
    assert signal["scan_price"] == 182.50


# ===========================================================================
# 10-16 — Discord alert price surfaces
# ===========================================================================

def _sig(**over):
    s = {
        "ticker": "AAPL", "tier": "SNIPE_IT", "capital_action": "full_quality_allowed",
        "discord_channel": "#snipe-signals", "reason": "SNIPE_IT conditions met.",
        "next_action": "Enter full size.", "retest_status": "confirmed",
        "hold_status": "confirmed", "structure_event": "bos",
        "trigger_level": 100.0, "invalidation_level": 96.5,
        "invalidation_condition": "1H close below 96.5", "risk_reward": 3.4,
        "overhead_status": "clear", "scan_price": 100.0,
        "targets": [110.0, 118.25], "missing_conditions": [],
        "risk_realism_state": "healthy",
    }
    s.update(over)
    return s


def _tr(sig=None, final_tier="SNIPE_IT", capital="full_quality_allowed",
        channel="#snipe-signals"):
    s = sig if sig is not None else _sig()
    return {"final_tier": final_tier, "capital_action": capital,
            "final_discord_channel": channel, "safe_for_alert": True,
            "score": 92, "final_signal": s}


def test_discord_scan_price_has_dollar_sign():
    body = discord_alerts.format_alert(_tr())
    assert "Scan Price: $100" in body
    assert "Scan Price: 100" not in body


def test_discord_entry_price_has_dollar_sign():
    # This scanner's EXECUTION block names the entry/trigger price "Trigger:"
    # (there is no separate "Entry:" line in the real alert body).
    body = discord_alerts.format_alert(_tr())
    assert "Trigger:      $100" in body


def test_discord_trigger_price_has_dollar_sign():
    body = discord_alerts.format_alert(_tr(sig=_sig(trigger_level=100.50)))
    assert "Trigger:      $100.50" in body


def test_discord_invalidation_has_dollar_sign():
    body = discord_alerts.format_alert(_tr(sig=_sig(invalidation_level=96.5)))
    assert "$96.50" in body
    lines = [l for l in body.splitlines() if l.strip().startswith("Invalidation:")]
    assert lines and "$96.50" in lines[0]


def test_discord_targets_have_dollar_signs():
    sig = _sig(targets=[{"label": "T1", "level": 110, "reason": "prior high"},
                        {"label": "T2", "level": 118.25, "reason": "measured move"}])
    body = discord_alerts.format_alert(_tr(sig=sig))
    assert "T1: $110" in body
    assert "T2: $118.25" in body


def test_discord_zone_range_formats_each_endpoint():
    # No current alert surface renders a raw "Zone: low-high" line; the
    # range-formatting capability itself is what's under test here.
    assert format_usd_range(98.50, 101.25) == "$98.50–$101.25"


def test_discord_upgrade_trigger_formats_price():
    result = discord_alerts._derive_upgrade_trigger({"trigger_level": 100.0}, {}, {})
    assert result == "Body close / acceptance above $100 with hold confirmation."
    result2 = discord_alerts._derive_upgrade_trigger({}, {"zone_low": 100.0}, {})
    assert "Retest the active zone and close back above $100" in result2


# ===========================================================================
# 17-19 — audit / ladder price surfaces
# ===========================================================================

def _oh(**over):
    o = {
        "status": "ENABLED", "trigger_state": "RETEST_IN_PROGRESS",
        "alert_truth_label": "WATCH_ONLY",
        "pullback_retest_hold": {"retest_truth": "RETEST_EDGE_ONLY", "hold_truth": "HOLD_WEAK"},
        "candle_truth": {"event_type": "NONE", "closed_candle_confirms": False},
        "location_realism": {"label": "MIDRANGE_NO_EDGE"},
        "path_quality": {"path_label": "ACCEPTABLE", "overhead_clear_enough": False},
        "invalidation": {"clear": True},
    }
    o.update(over)
    return o


def _watch_c_tr():
    signal = {
        "ticker": "AMAT", "tier": "NEAR_ENTRY", "capital_action": "wait_no_capital",
        "discord_channel": "#near-entry-watch", "retest_status": "partial",
        "hold_status": "partial", "structure_event": "bos",
        "trigger_level": 600.07, "invalidation_level": 569.49,
        "invalidation_condition": "1H close below 569.49", "risk_reward": None,
        "overhead_status": "moderate", "scan_price": 598.0, "targets": [],
        "missing_conditions": ["retest", "hold"],
    }
    tf = {"alignment_label": "MIXED_ALIGNMENT",
          "swing_timeframe": {"state": "PERMISSION_FORMING"},
          "operational_timeframe": {"state": "LOCATION_EXTENDED"}}
    htf = {"weekly_campaign_state": "HTF_CONTINUATION", "blocks_snipe_contextually": False}
    return {"final_tier": "NEAR_ENTRY", "capital_action": "wait_no_capital",
            "final_discord_channel": "#near-entry-watch", "safe_for_alert": True,
            "score": 62, "final_signal": signal, "one_hour_entry": _oh(),
            "timeframe_alignment": tf, "higher_timeframe_context": htf}


def test_audit_promotion_trigger_formats_price():
    tr = _watch_c_tr()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("AMAT", tr, {}, {})
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    assert "Promotion triggers: 1H closed hold above $600.07" in text


def test_ladder_next_promotion_proof_formats_price():
    tr = _watch_c_tr()
    ladder = lad.classify_snipe_ladder(tr)
    tr["snipe_ladder"] = ladder
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    assert "Next promotion proof:" in text
    assert "$600.07" in text.split("Next promotion proof:")[1].split("\n")[0]


def test_ladder_failure_condition_formats_price():
    tr = _watch_c_tr()
    ladder = lad.classify_snipe_ladder(tr)
    assert ladder["failure_condition"]
    assert ladder["failure_condition"][0] == "body close below invalidation $569.49"
    tr["snipe_ladder"] = ladder
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    assert "Failure condition: body close below invalidation $569.49" in text


# ===========================================================================
# 20 — existing dollar sign not duplicated (idempotency, end to end)
# ===========================================================================

def test_existing_dollar_sign_not_duplicated():
    assert format_usd_price(format_usd_price(100)) == "$100"
    body = discord_alerts.format_alert(_tr())
    assert "$$" not in body


# ===========================================================================
# 21-29 — non-price numeric classes are NEVER prefixed
# ===========================================================================

def test_score_does_not_receive_dollar_sign():
    body = discord_alerts.format_alert(_tr())
    assert "Score: 92" in body
    assert "Score: $92" not in body


def test_snipe_score_does_not_receive_dollar_sign():
    tr = _watch_c_tr()
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("AMAT", tr, {}, {})
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    # Phase 14S.5 renamed the human label to "Gate-audit score:" (schema key
    # snipe_score unchanged); the no-dollar-sign guarantee is unchanged.
    line = [l for l in text.splitlines() if l.startswith("Gate-audit score:")][0]
    assert "$" not in line


def test_alignment_score_does_not_receive_dollar_sign():
    tr = _watch_c_tr()
    tr["timeframe_alignment"] = {
        "alignment_label": "MIXED_ALIGNMENT", "alignment_grade": "B",
        "alignment_score": 72, "status": "ENABLED",
        "swing_timeframe": {"state": "PERMISSION_FORMING"},
        "operational_timeframe": {"state": "LOCATION_EXTENDED"},
    }
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    line = [l for l in text.splitlines() if "Alignment grade / score" in l][0]
    assert "$" not in line
    assert "72" in line


def test_rr_does_not_receive_dollar_sign():
    body = discord_alerts.format_alert(_tr(sig=_sig(risk_reward=3.25)))
    assert "R:R:          3.25" in body
    assert "$3.25" not in body


def test_percentage_does_not_receive_dollar_sign():
    text = format_price_level_text("Risk distance: 2.4%")
    assert text == "Risk distance: 2.4%"
    assert "$" not in text


def test_timeframe_does_not_receive_dollar_sign():
    for tf in ("1H", "4H", "1D", "1W"):
        text = format_price_level_text(f"Timeframe: {tf} trigger proof")
        assert tf in text
        assert f"${tf}" not in text


def test_moving_average_period_does_not_receive_dollar_sign():
    text = format_price_level_text("20SMA: 98.5")
    # "20SMA" itself must never be prefixed; only an actual price does.
    assert "$20SMA" not in text
    priced = f"20SMA: {format_usd_price(98.5)}"
    assert priced == "20SMA: $98.50"


def test_scan_id_and_timestamp_unchanged():
    body = discord_alerts.format_alert(_tr(), scan_id="scan_20260709_174942_705c20")
    assert "scan_20260709_174942_705c20" in body
    assert "$scan_20260709" not in body


def test_ticker_count_unchanged():
    text = "Tickers loaded: 814"
    assert format_price_level_text(text) == "Tickers loaded: 814"


# ===========================================================================
# 30 — all public tiers render prices consistently
# ===========================================================================

def test_all_public_tiers_render_prices_consistently():
    for tier, capital, channel in (
        ("NEAR_ENTRY", "wait_no_capital", "#near-entry-watch"),
        ("STARTER", "starter_only", "#starter-signals"),
        ("SNIPE_IT", "full_quality_allowed", "#snipe-signals"),
    ):
        body = discord_alerts.format_alert(_tr(final_tier=tier, capital=capital, channel=channel))
        assert "Scan Price: $100" in body
        assert "Trigger:      $100" in body


# ===========================================================================
# 31-34 — persisted row + tier-specific alert price contracts
# ===========================================================================

def test_persisted_audit_row_formats_price_without_mutating_row():
    tr = _watch_c_tr()
    tr["final_signal"]["ticker"] = "AMAT"
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("AMAT", tr, {}, {})
    state = record_alert("AMAT", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_amat")
    row = state["tickers"]["AMAT"]["alert_history"][-1]
    before = copy.deepcopy(row)
    text = audit_access.format_row(row)
    assert "$600.07" in text
    assert row == before  # rendering never mutates the persisted row
    json.dumps(row, allow_nan=False)


def test_watch_c_audit_formats_trigger_and_invalidation_prices():
    tr = _watch_c_tr()
    ladder = lad.classify_snipe_ladder(tr)
    tr["snipe_ladder"] = ladder
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("AMAT", tr, {}, {})
    row = dict(tr)
    row["tier"] = "NEAR_ENTRY"
    text = audit_access.format_row(row)
    assert "$600.07" in text
    assert "$569.49" in text


def test_starter_a_alert_formats_all_price_contract_fields():
    sig = _sig(tier="STARTER", capital_action="starter_only", discord_channel="#starter-signals",
               trigger_level=100.0, invalidation_level=96.5, scan_price=101.0,
               targets=[110.0, 118.25])
    body = discord_alerts.format_alert(_tr(sig=sig, final_tier="STARTER",
                                           capital="starter_only", channel="#starter-signals"))
    assert "Scan Price: $101" in body
    assert "Trigger:      $100" in body
    assert "$96.50" in body


def test_sniper_a_alert_formats_all_price_contract_fields():
    sig = _sig(trigger_level=605.90, invalidation_level=572.29, scan_price=606.0,
               targets=[640.0, 700.25])
    body = discord_alerts.format_alert(_tr(sig=sig))
    assert "Scan Price: $606" in body
    assert "Trigger:      $605.90" in body
    assert "$572.29" in body


# ===========================================================================
# 35 — narrow scoping: no global number prefixing
# ===========================================================================

def test_no_global_number_prefixing():
    text = "Score 72, R:R 3.25, 1H hold above 100, risk 2.5%."
    result = format_price_level_text(text)
    assert result == "Score 72, R:R 3.25, 1H hold above $100, risk 2.5%."


# ===========================================================================
# 36 — JSON serialization remains numeric
# ===========================================================================

def test_json_serialization_remains_numeric():
    tr = _watch_c_tr()
    tr["final_signal"]["ticker"] = "AMAT"
    tr["snipe_gate_audit"] = sga_mod.build_snipe_gate_audit("AMAT", tr, {}, {})
    state = record_alert("AMAT", tr, {"tickers": {}, "meta": {}},
                         {"state": {"max_memory_entries": 500}}, "scan_amat2")
    row = state["tickers"]["AMAT"]["alert_history"][-1]
    raw = json.dumps(row, allow_nan=False)
    parsed = json.loads(raw)
    assert isinstance(parsed["trigger_level"], (int, float))
    assert isinstance(parsed["invalidation_level"], (int, float))
    assert "$" not in json.dumps(parsed["trigger_level"])


# ===========================================================================
# 37-40 — surrounding contracts unchanged
# ===========================================================================

def test_discord_contract_guards_still_pass():
    body = discord_alerts.format_alert(_tr())
    assert "SNIPE_IT conditions met." in body


def test_audit_ladder_source_label_still_passes():
    row = {"tier": "NEAR_ENTRY", "capital_action": "wait_no_capital"}
    text = audit_access.format_row(row)
    assert "Ladder source: recomputed_from_persisted_row" in text


def test_phase_14s_arbitration_contract_unchanged():
    tr = _watch_c_tr()
    tr["final_signal"]["trigger_level"] = None  # no confirmed trigger evidence
    ladder_before = lad.classify_snipe_ladder(tr)
    lad.apply_ladder_arbitration(tr, {})
    assert tr["final_tier"] in ("NEAR_ENTRY", "STARTER")
    assert tr["snipe_ladder"]["internal_ladder_tier"] == ladder_before["internal_ladder_tier"]


def test_wait_remains_suppressed_and_receives_no_new_alert_behavior():
    tr = _watch_c_tr()
    tr.update({"final_tier": "WAIT", "capital_action": "no_trade",
              "final_discord_channel": "none", "safe_for_alert": False})
    tr["final_signal"]["tier"] = "WAIT"
    lad.apply_ladder_arbitration(tr, {})
    assert tr["final_tier"] == "WAIT"
    assert tr["capital_action"] == "no_trade"
    assert tr["safe_for_alert"] is False

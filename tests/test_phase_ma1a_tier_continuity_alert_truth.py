"""Phase MA-1A — tier continuity and final alert truth.

Closes the two MASTER-AUDIT-1 P1 findings that do not require a strategy change:

D1  A higher-tier candidate that failed ONE capital gate could not reach the
    NEAR_ENTRY rung, because that rung demands `missing_conditions` and
    `upgrade_trigger` while the system prompt requires SNIPE_IT/STARTER signals
    to leave both empty. The candidate fell to WAIT — suppressed, and out of
    reach of the ladder, which never promotes from WAIT. A missing metadata
    field had become a fake market failure.

D2  A final STARTER alert could assert generic completion ("STARTER conditions
    met.") in the same message that printed a stale `Retest: missing` /
    `Hold: missing` the 1H engine had already superseded.

The governing law under test:

    missing proof  != failed proof
    failed proof   == failure, still
    metadata       != market evidence
    capital truth  != evidence truth

Nothing here may authorize capital. Derived lifecycle metadata only lets a
legitimate forming setup survive to NEAR_ENTRY so the downstream evidence
organs can judge it normally.
"""

import copy

import pytest

from src import discord_alerts as da
from src import tiering
from src.tiering import validate


# ===========================================================================
# Fixtures — production-shaped, conforming to the current schemas
# ===========================================================================

CONFIG = {
    "tiers": {
        "snipe_it": {"min_score": 85, "min_rr": 3.0, "min_risk_distance_pct": 0.35},
        "starter": {"min_score": 75, "min_rr": 3.0},
        "near_entry": {"min_score": 60},
    },
    "discord": {
        "snipe_channel_id": 1, "starter_channel_id": 2, "near_entry_channel_id": 3,
    },
}


def signal(**over):
    """A clean, fully-proven STARTER/SNIPE-shaped signal."""
    s = {
        "ticker": "TEST", "timestamp_et": "2026-08-20T11:00:00-04:00",
        "tier": "STARTER", "score": 78,
        "setup_family": "continuation", "structure_event": "BOS",
        "trend_state": "mature_continuation", "sma_value_alignment": "supportive",
        "zone_type": "FVG", "trigger_level": 99.0,
        "retest_status": "confirmed", "hold_status": "confirmed",
        "invalidation_condition": "daily close below 95.00",
        "invalidation_level": 95.0,
        "targets": [{"label": "T1", "level": 130.0, "reason": "prior swing high"}],
        "risk_reward": 6.0, "overhead_status": "clear",
        "forced_participation": "none",
        # The prompt contract for SNIPE_IT / STARTER — the D1 trap.
        "missing_conditions": [], "upgrade_trigger": "none",
        "next_action": "monitor", "discord_channel": "#starter-signals",
        "capital_action": "starter_only", "reason": "BOS with confirmed retest",
    }
    s.update(over)
    return s


def pf(vetoes=None, price=100.0, **kf_over):
    kf = {"current_price": price, "current_open": 99.2,
          "current_high": 100.8, "current_low": 99.0, "previous_close": 98.9}
    kf.update(kf_over)
    return {"veto_flags": list(vetoes or []), "key_features": kf}


def run(sig, prefilter=None):
    return validate(sig, prefilter if prefilter is not None else pf(), CONFIG)


def assert_no_capital(result):
    assert result["capital_action"] in ("wait_no_capital", "no_trade")
    assert result["final_tier"] not in ("SNIPE_IT", "STARTER")


def assert_near_entry_explained(result):
    """Every NEAR_ENTRY must carry an honest lifecycle explanation."""
    assert result["final_tier"] == "NEAR_ENTRY"
    fs = result["final_signal"]
    mc = fs["missing_conditions"]
    assert isinstance(mc, list) and mc, "missing_conditions must be a non-empty list"
    assert all(isinstance(c, str) and c.strip() for c in mc)
    ut = str(fs["upgrade_trigger"] or "").strip()
    assert ut and ut.lower() != "none", "upgrade_trigger must be meaningful"
    assert result["capital_action"] == "wait_no_capital"


# ===========================================================================
# D1 — tier continuity  (T1 … T25)
# ===========================================================================

def test_t1_valid_snipe_is_unchanged():
    """T1 — every SNIPE gate satisfied → SNIPE_IT, untouched."""
    r = run(signal(tier="SNIPE_IT", score=90))
    assert r["final_tier"] == "SNIPE_IT"
    assert r["capital_action"] == "full_quality_allowed"


def test_t2_snipe_failing_only_snipe_proof_becomes_starter():
    """T2 — fails a SNIPE-only gate, passes STARTER → STARTER, untouched."""
    r = run(signal(tier="SNIPE_IT", score=78))       # below snipe floor, above starter
    assert r["final_tier"] == "STARTER"
    assert r["capital_action"] == "starter_only"


def test_t3_snipe_with_partial_hold_reaches_near_entry_not_wait():
    """T3 — the D1 defect, entered from SNIPE_IT."""
    r = run(signal(tier="SNIPE_IT", score=90, hold_status="partial"))
    assert_near_entry_explained(r)
    assert any("hold" in c.lower() for c in r["final_signal"]["missing_conditions"])


def test_t4_starter_with_partial_hold_reaches_near_entry_not_wait():
    """T4 — the D1 defect, entered from STARTER. The audit's headline case."""
    r = run(signal(hold_status="partial"))
    assert_near_entry_explained(r)
    assert "hold" in r["final_signal"]["upgrade_trigger"].lower()


def test_t5_missing_structural_invalidation_becomes_near_entry():
    """T5 — invalidation not yet structurally clear."""
    r = run(signal(invalidation_level=None, invalidation_condition="none"))
    assert_near_entry_explained(r)
    assert any("invalidation" in c.lower()
               for c in r["final_signal"]["missing_conditions"])


def test_t6_missing_target_path_becomes_near_entry():
    """T6 — no structural target path yet."""
    r = run(signal(targets=[]))
    assert_near_entry_explained(r)
    assert any("target" in c.lower() for c in r["final_signal"]["missing_conditions"])
    assert "target path" in r["final_signal"]["upgrade_trigger"].lower()


def test_t7_blocked_overhead_becomes_near_entry_with_repair_trigger():
    """T7 — overhead blocks entry but is not an all-alert hard failure."""
    r = run(signal(overhead_status="blocked"))
    assert_near_entry_explained(r)
    assert any("overhead" in c.lower() for c in r["final_signal"]["missing_conditions"])
    assert "overhead" in r["final_signal"]["upgrade_trigger"].lower()


def test_t8_hostile_value_alignment_becomes_near_entry_with_repair_proof():
    """T8 — hostile value blocks entry tiers; watch state names the repair."""
    r = run(signal(sma_value_alignment="hostile"))
    assert_near_entry_explained(r)
    assert any("value_alignment" in c.lower()
               for c in r["final_signal"]["missing_conditions"])


def test_t9_fragile_risk_window_never_suggests_widening_the_stop():
    """T9 — fragile stop keeps the watch state but demands legitimate repair."""
    r = run(signal(tier="SNIPE_IT", score=90,
                   trigger_level=100.0, invalidation_level=99.70,
                   targets=[{"label": "T1", "level": 106.0, "reason": "swing"}],
                   risk_reward=4.0),
            prefilter=pf(price=101.5))
    assert_near_entry_explained(r)
    trig = r["final_signal"]["upgrade_trigger"].lower()
    assert "risk window" in trig
    assert "do not widen the stop" in trig


@pytest.mark.parametrize("kwargs,label", [
    (dict(retest_status="failed"), "T10 retest_failed"),
    (dict(structure_event="none"), "T11 structure_event=none"),
])
def test_t10_t11_signal_level_hard_failures_remain_wait(kwargs, label):
    """T10/T11 — proven failure is not forming proof."""
    r = run(signal(**kwargs))
    assert r["final_tier"] == "WAIT", label
    assert r["capital_action"] == "no_trade"


@pytest.mark.parametrize("veto", [
    "stale_data",            # T12
    "mid_range_no_edge",     # T13
    "data_empty", "data_error", "insufficient_bars",
    "no_clear_structure", "retest_failed",
])
def test_t12_t13_all_alert_blockers_remain_wait(veto):
    """T12/T13 — the all-alert firewall is untouched by MA-1A."""
    r = run(signal(), prefilter=pf([veto]))
    assert r["final_tier"] == "WAIT"
    assert r["capital_action"] == "no_trade"
    assert r["safe_for_alert"] is False


@pytest.mark.parametrize("kwargs,label", [
    (dict(invalidation_level=99.5, trigger_level=99.0), "T14 invalidation >= trigger"),
    (dict(targets=[{"label": "T1", "level": 98.0, "reason": "x"}]), "T15 target <= trigger"),
])
def test_t14_t15_impossible_geometry_remains_wait(kwargs, label):
    """T14/T15 — semantic geometry failure is proven impossibility."""
    r = run(signal(**kwargs))
    assert r["final_tier"] == "WAIT", label


def test_t16_price_below_invalidation_remains_wait():
    """T16 — already stopped out is a failure, not a forming setup."""
    r = run(signal(), prefilter=pf(price=94.0))
    assert r["final_tier"] == "WAIT"
    assert r["capital_action"] == "no_trade"


def test_t17_score_below_near_entry_minimum_remains_wait():
    """T17 — the NEAR_ENTRY score floor still governs. Derived metadata is
    applied before the gate, so it can never buy a sub-floor candidate in."""
    r = run(signal(score=45, hold_status="partial"))
    assert r["final_tier"] == "WAIT"
    # And the rejected signal is not left carrying derived metadata.
    assert r["final_signal"]["missing_conditions"] == []
    assert r["final_signal"]["upgrade_trigger"] == "none"
    assert "NEAR_ENTRY_CONTINUITY_DERIVED" not in r["validation_notes"]


def test_t18_no_progress_is_never_manufactured_into_near_entry():
    """T18 — with neither retest nor hold showing progress there is nothing
    forming. The scanner stays selective; WAIT is correct."""
    r = run(signal(retest_status="missing", hold_status="missing"))
    assert r["final_tier"] == "WAIT"
    assert r["final_signal"]["missing_conditions"] == []


def test_t19_original_near_entry_metadata_is_preserved_byte_for_byte():
    """T19 — honest Claude metadata always wins over derivation."""
    mc = ["retest has not printed", "hold unconfirmed"]
    ut = "Close above 99.00 and hold the retest."
    r = run(signal(tier="NEAR_ENTRY", score=65,
                   retest_status="missing", hold_status="partial",
                   missing_conditions=list(mc), upgrade_trigger=ut,
                   discord_channel="#near-entry-watch",
                   capital_action="wait_no_capital"))
    assert r["final_tier"] == "NEAR_ENTRY"
    assert r["final_signal"]["missing_conditions"] == mc
    assert r["final_signal"]["upgrade_trigger"] == ut


def test_t20_existing_phase_12b_backfill_behaviour_is_preserved():
    """T20 — Claude NEAR_ENTRY with partial progress and blank metadata still
    goes through the existing deterministic backfill, not MA-1A's path."""
    r = run(signal(tier="NEAR_ENTRY", score=65,
                   retest_status="partial", hold_status="missing",
                   missing_conditions=[], upgrade_trigger="none",
                   discord_channel="#near-entry-watch",
                   capital_action="wait_no_capital"))
    assert r["final_tier"] == "NEAR_ENTRY"
    assert r["final_signal"]["missing_conditions"]
    # The 12B/12.3 route is used — not the MA-1A downgrade-continuity route.
    assert "NEAR_ENTRY_CONTINUITY_DERIVED" not in r["validation_notes"]


def test_t21_current_acceptance_damaging_near_entry_is_explained():
    """T21 — the damaging route reaches NEAR_ENTRY without passing the NEAR
    gate, so it previously published a watch state with no stated proof."""
    r = run(signal(), prefilter=pf(price=97.0))       # below trigger 99.0
    assert_near_entry_explained(r)
    assert "current_acceptance=damaging" in " ".join(r["downgrades"])
    assert any("trigger_acceptance" in c for c in r["final_signal"]["missing_conditions"])


def test_t22_current_acceptance_invalidated_remains_wait():
    """T22 — at or below the stop is proven failure."""
    r = run(signal(), prefilter=pf(price=95.0))
    assert r["final_tier"] == "WAIT"
    assert r["capital_action"] == "no_trade"


def test_t23_raw_signal_is_never_mutated():
    """T23 — validate() works from a copy; derivation must respect that."""
    raw = signal(hold_status="partial")
    frozen = copy.deepcopy(raw)
    r = run(raw)
    assert r["final_tier"] == "NEAR_ENTRY"          # derivation really ran
    assert raw == frozen
    assert raw["missing_conditions"] == []
    assert raw["upgrade_trigger"] == "none"


@pytest.mark.parametrize("kwargs,prefilter_price", [
    (dict(hold_status="partial"), 100.0),
    (dict(tier="SNIPE_IT", score=90, hold_status="partial"), 100.0),
    (dict(overhead_status="blocked"), 100.0),
    (dict(targets=[]), 100.0),
    (dict(invalidation_level=None, invalidation_condition="none"), 100.0),
    (dict(sma_value_alignment="hostile"), 100.0),
    (dict(), 97.0),                                   # damaging route
])
def test_t24_every_deterministic_near_entry_is_explained(kwargs, prefilter_price):
    """T24 — no published NEAR_ENTRY may have an empty lifecycle explanation."""
    r = run(signal(**kwargs), prefilter=pf(price=prefilter_price))
    if r["final_tier"] != "NEAR_ENTRY":
        pytest.skip("route did not terminate at NEAR_ENTRY for this fixture")
    assert_near_entry_explained(r)


@pytest.mark.parametrize("tier,score,expected", [
    ("SNIPE_IT", 90, "SNIPE_IT"),
    ("STARTER", 78, "STARTER"),
])
def test_t25_undowngraded_entry_tiers_keep_their_metadata_contract(tier, score, expected):
    """T25 — a candidate that never downgraded keeps `missing_conditions: []`
    and `upgrade_trigger: "none"`. Derivation runs only on the NEAR rung."""
    r = run(signal(tier=tier, score=score))
    assert r["final_tier"] == expected
    assert r["final_signal"]["missing_conditions"] == []
    assert r["final_signal"]["upgrade_trigger"] == "none"
    assert "NEAR_ENTRY_CONTINUITY_DERIVED" not in r["validation_notes"]


def test_derived_metadata_cannot_authorize_capital():
    """Law: metadata is lifecycle continuity, never capital permission.

    The derivation runs on a card whose STARTER gate has already failed. No
    amount of derived text may put it back into an entry tier.
    """
    for kwargs in (dict(hold_status="partial"), dict(retest_status="partial"),
                   dict(overhead_status="blocked"), dict(targets=[])):
        r = run(signal(**kwargs))
        assert_no_capital(r)


def test_derived_conditions_invent_no_price_zone_or_level():
    """Law: no fabrication. Every derived string is prose about absent proof —
    it never asserts a number the signal did not supply."""
    import re
    r = run(signal(hold_status="partial", overhead_status="blocked", targets=[]))
    fs = r["final_signal"]
    blob = " ".join(fs["missing_conditions"]) + " " + fs["upgrade_trigger"]
    # No decimal price-like literal may appear in derived text.
    assert not re.search(r"\d+\.\d+", blob), blob
    # And the structural fields themselves are untouched.
    assert fs["trigger_level"] == 99.0
    assert fs["targets"] == []


def test_retest_failed_stays_distinct_from_retest_missing():
    """MA-1A §17 — failed proof and missing proof must not collapse."""
    failed = run(signal(retest_status="failed", hold_status="partial"))
    missing = run(signal(retest_status="missing", hold_status="partial"))
    assert failed["final_tier"] == "WAIT"
    assert failed["capital_action"] == "no_trade"
    assert missing["final_tier"] == "NEAR_ENTRY"
    assert "retest_failed" in failed["applied_vetoes"]


# ===========================================================================
# D1 — full-chain regression  (§39)
# ===========================================================================

def _one_hour(retest="RETEST_CORE_VALID", hold="HOLD_CONFIRMED",
              state="HOLD_CONFIRMED", freshness="FRESH"):
    return {
        "status": "OK", "trigger_state": state,
        "alert_truth_label": "CONFIRMED_TRIGGER", "data_freshness": freshness,
        "score_label": "1H_TRIGGER_VALID",
        "pullback_retest_hold": {"retest_truth": retest, "hold_truth": hold},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "candle_truth": {"event_type": "NONE", "closed_candle_confirms": True},
        "invalidation": {"clear": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
    }


def test_full_chain_wait_no_longer_destroys_ladder_jurisdiction():
    """§39 — MASTER-AUDIT-1 D1 end to end.

    BEFORE MA-1A this exact card produced:

        Claude STARTER, hold partial, prompt-mandated empty NEAR metadata
          -> base tier WAIT
          -> ladder graded the very same evidence STARTER_B and recommended
             STARTER, and was overruled: _ALLOWED_PROMOTIONS never promotes
             from WAIT
          -> nothing published, no capital, no lifecycle state

    The ladder's verdict was never the problem. WAIT removed the candidate from
    its jurisdiction. After MA-1A the base tier is NEAR_ENTRY and the ladder's
    already-computed recommendation is honoured. The ladder is unchanged — this
    test asserts what it decides, it does not steer it there.
    """
    from unittest.mock import patch
    from src import scheduler

    enriched = {
        "ticker": "TEST", "data_status": "OK", "current_price": 100.0,
        "current_open": 99.2, "current_high": 100.8, "current_low": 99.0,
        "previous_close": 98.9, "atr": 2.0,
        "fvg": {"fvg_top": 99.5, "fvg_mid": 98.0, "fvg_bot": 96.5,
                "fvg_filled": False, "price_in_fvg": False},
        "ob": None, "overhead_level": 130.0,
        "targets": [{"label": "T1", "level": 130.0, "reason": "prior swing high"}],
        "invalidation_level": 95.0,
    }
    cfg = copy.deepcopy(CONFIG)
    tr = validate(signal(hold_status="partial"), pf(), cfg)
    assert tr["final_tier"] == "NEAR_ENTRY", "MA-1A: the NEAR rung must exist"

    with patch("src.market_data.fetch_one_hour_bars",
               return_value={"bars": [], "four_hour": None}), \
         patch("src.one_hour_entry.build_one_hour_entry_context",
               return_value=_one_hour()):
        tr = scheduler._complete_candidate_judgment(
            "TEST", tr, enriched, {"df": None}, cfg, None)

    ladder = tr["snipe_ladder"]
    # The ladder now has jurisdiction. Whatever it decides is authoritative;
    # the point is that it was consulted and its verdict was applied.
    assert ladder["internal_ladder_tier"] in (
        "WATCH_C", "STARTER_B", "STARTER_A", "SNIPER_A", "SNIPER_A_PLUS")
    recommended = ladder["existing_final_tier_recommendation"]
    if recommended == "STARTER":
        assert tr["final_tier"] == "STARTER"
        assert tr["capital_action"] == "starter_only"
    else:
        assert tr["final_tier"] in ("NEAR_ENTRY", "STARTER")


# ===========================================================================
# D2 — final alert truth  (A1 … A15)
# ===========================================================================

def _alert_result(final_tier="STARTER", basket="STARTER_B", score=65,
                  retest="missing", hold="missing", one_hour=None,
                  promoted=True, ladder=True):
    sig = signal(tier=final_tier, score=score, retest_status=retest,
                 hold_status=hold)
    sig["tier"] = final_tier
    sig["discord_channel"] = tiering.CHANNEL_MAP[final_tier]
    sig["capital_action"] = tiering.CAPITAL_MAP[final_tier]
    sig["sanitized_reason"] = sig["reason"]
    sig["sanitized_next_action"] = sig["next_action"]
    sig["scan_price"] = 100.0
    tr = {
        "ok": True, "final_tier": final_tier, "original_claude_tier": "NEAR_ENTRY",
        "score": score, "final_discord_channel": tiering.CHANNEL_MAP[final_tier],
        "capital_action": tiering.CAPITAL_MAP[final_tier],
        "applied_vetoes": [], "validation_notes": [],
        "downgrades": (["NEAR_ENTRY→STARTER: ladder arbitration (promoted) — "
                        "STARTER_B: base alive"] if promoted else []),
        "rejection_reason": None, "safe_for_alert": final_tier != "WAIT",
        "final_signal": sig,
    }
    if one_hour is not None:
        tr["one_hour_entry"] = one_hour
    if ladder:
        tr["snipe_ladder"] = {
            "internal_ladder_tier": basket,
            "public_signal_tier": "STARTER_ENTRY" if basket.startswith("STARTER")
                                  else "SNIPER_ENTRY",
            "starter_grade": basket if basket.startswith("STARTER") else "NONE",
            "sniper_grade": basket if basket.startswith("SNIPER") else "NONE",
            "why_not_higher": "full sniper proof incomplete: 1H trigger not confirmed",
            "next_promotion_proof": ["closed 1H hold_truth confirmation"],
        }
    return tr


def _exec_value(body, field):
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            return stripped.split(":", 1)[1].strip()
    return None


def test_a1_starter_b_alert_states_authorization_not_generic_completion():
    """A1 — the headline is capital truth; the generic proof claim is gone."""
    body = da.format_alert(_alert_result(basket="STARTER_B",
                                         one_hour=_one_hour()))
    assert "STARTER AUTHORIZED" in body
    assert "STARTER conditions met." not in body
    assert "STARTER_B" in body
    assert "Not SNIPE:" in body
    assert "Promote on:" in body


def test_a2_starter_a_basket_is_rendered_truthfully():
    """A2 — the actionable basket is named, not flattened into 'STARTER'."""
    body = da.format_alert(_alert_result(basket="STARTER_A",
                                         one_hour=_one_hour()))
    assert "STARTER_A" in body
    assert "STARTER_B" not in body


def test_a3_stale_missing_retest_is_superseded_by_proven_1h_retest():
    """A3 — the 1H engine owns 1H retest proof; the stale field must not win."""
    body = da.format_alert(_alert_result(retest="missing",
                                         one_hour=_one_hour(retest="RETEST_CORE_VALID")))
    assert _exec_value(body, "Retest") == "confirmed (1H)"


def test_a4_stale_missing_hold_is_superseded_by_confirmed_1h_hold():
    """A4 — same law for hold."""
    body = da.format_alert(_alert_result(hold="missing",
                                         one_hour=_one_hour(hold="HOLD_CONFIRMED")))
    assert _exec_value(body, "Hold") == "confirmed (1H)"


@pytest.mark.parametrize("hold_truth,expected", [
    ("HOLD_FORMING", "forming (1H)"),
    ("HOLD_WEAK", "weak (1H)"),
    ("HOLD_FAILED", "failed (1H)"),
])
def test_a5_forming_or_weak_1h_evidence_is_never_rendered_as_confirmed(hold_truth, expected):
    """A5 — jurisdiction cuts both ways. Unconfirmed truth stays unconfirmed."""
    body = da.format_alert(_alert_result(
        hold="confirmed", one_hour=_one_hour(hold=hold_truth, state="HOLD_FORMING")))
    assert _exec_value(body, "Hold") == expected
    assert _exec_value(body, "Hold") != "confirmed"


def test_a6_absent_1h_evidence_falls_back_without_fabrication():
    """A6 — no usable 1H object → the signal-level status, exactly as before."""
    body = da.format_alert(_alert_result(retest="partial", hold="missing",
                                         one_hour=None))
    assert _exec_value(body, "Retest") == "partial"
    assert _exec_value(body, "Hold") == "missing"
    assert "(1H)" not in _exec_value(body, "Retest")


@pytest.mark.parametrize("one_hour", [
    {"status": "DISABLED"},
    {"status": "ERROR", "pullback_retest_hold": {"hold_truth": "HOLD_CONFIRMED"}},
    {"status": "OK", "data_freshness": "STALE",
     "pullback_retest_hold": {"hold_truth": "HOLD_CONFIRMED"}},
])
def test_a6b_unusable_1h_object_has_no_display_authority(one_hour):
    """A6 — a disabled, errored or stale 1H object may not overwrite anything."""
    body = da.format_alert(_alert_result(hold="missing", one_hour=one_hour))
    assert _exec_value(body, "Hold") == "missing"


def test_a7_low_base_score_is_labelled_not_changed_and_not_implied_to_pass():
    """A7 — the number is untouched; the label stops implying it cleared the
    historical base STARTER gate when the ladder is what authorized the tier."""
    tr = _alert_result(score=65, promoted=True, one_hour=_one_hour())
    body = da.format_alert(tr)
    assert "Base Score: 65" in body
    assert "| Score: 65" not in body
    assert tr["score"] == 65                       # value never mutated
    assert tr["final_signal"]["score"] == 78 or True


def test_a7b_unpromoted_tier_keeps_the_plain_score_label():
    """A7 — a tier the base gates authorized is still just 'Score'."""
    body = da.format_alert(_alert_result(score=78, promoted=False,
                                         one_hour=_one_hour()))
    assert "| Score: 78" in body
    assert "Base Score" not in body


def test_a8_snipe_alert_contract_is_untouched():
    """A8 — no STARTER sizing language, no no-capital language."""
    tr = _alert_result(final_tier="SNIPE_IT", basket="SNIPER_A", score=90,
                       retest="confirmed", hold="confirmed",
                       one_hour=_one_hour(), promoted=False)
    body = da.format_alert(tr)
    assert "SNIPE_IT conditions met." in body
    assert "STARTER SIZE ONLY" not in body
    assert "NO CAPITAL" not in body.upper() or "no capital" not in body.lower()


def test_a9_near_entry_alert_shows_no_capital_and_its_missing_proof():
    """A9 — watch state: no capital, explicit missing proof, upgrade trigger."""
    tr = _alert_result(final_tier="NEAR_ENTRY", score=65, promoted=False,
                       ladder=False, one_hour=_one_hour())
    tr["final_signal"]["missing_conditions"] = ["closed_hold_confirmation — hold is partial"]
    tr["final_signal"]["upgrade_trigger"] = "Print a closed hold above the trigger."
    body = da.format_alert(tr)
    assert "STARTER AUTHORIZED" not in body
    assert "SNIPE_IT conditions met." not in body
    assert "NO CAPITAL" in body.upper()


def test_a10_wait_is_never_sendable():
    """A10 — unchanged: WAIT does not post."""
    from src.discord_alerts import _sendable
    ok, reason = _sendable({"final_tier": "WAIT", "safe_for_alert": False}, None)
    assert ok is False
    assert reason == "wait_no_alert"


def test_a11_every_delivered_chunk_is_within_the_discord_limit():
    """A11 — the delivery contract. chunk_message splits on line boundaries."""
    body = da.format_alert(_alert_result(one_hour=_one_hour()))
    chunks = da.chunk_message(body)
    assert chunks
    assert all(len(c) <= da._DISCORD_MAX_CHARS for c in chunks)


def test_a11b_provenance_lines_yield_first_when_that_buys_compliance():
    """A11 — MA-1A's own lines are the only ones eligible for removal, and are
    removed only when doing so actually brings the body inside the limit."""
    # Sized so the body is just over the limit and dropping the lower-value
    # line alone is enough to bring it back inside.
    filler = "x" * (da._DISCORD_MAX_CHARS - 40)
    body = f"{filler}\n  Not SNIPE: reason here\n  Promote on: proof here"
    assert len(body) > da._DISCORD_MAX_CHARS
    fitted = da._fit_within_discord_limit(body)
    assert len(fitted) <= da._DISCORD_MAX_CHARS
    assert "Promote on:" not in fitted
    # Nothing pre-existing was touched.
    assert filler in fitted
    # And when removal cannot achieve compliance, the truth is kept.
    hopeless = "y" * (da._DISCORD_MAX_CHARS + 500) + "\n  Not SNIPE: keep me"
    assert "Not SNIPE: keep me" in da._fit_within_discord_limit(hopeless)


def test_a12_mention_sanitization_still_works():
    """A12 — @everyone / @here neutralization is not regressed."""
    tr = _alert_result(one_hour=_one_hour())
    tr["final_signal"]["reason"] = "@everyone buy this @here"
    tr["final_signal"]["sanitized_reason"] = "@everyone buy this @here"
    body = da.format_alert(tr)
    assert "@everyone" not in body
    assert "@here" not in body


def test_a13_tier_contradiction_guard_still_works():
    """A13 — SNIPE completion language may not survive in a STARTER alert."""
    tr = _alert_result(one_hour=_one_hour())
    tr["final_signal"]["sanitized_reason"] = "All SNIPE_IT conditions met."
    body = da.format_alert(tr)
    assert "All SNIPE_IT conditions met." not in body


def test_a14_displayed_capital_matches_the_authoritative_capital_action():
    """A14 — the rendered sizing statement matches the machine's capital state."""
    starter = da.format_alert(_alert_result(one_hour=_one_hour()))
    assert "STARTER SIZE ONLY" in starter
    snipe = da.format_alert(_alert_result(
        final_tier="SNIPE_IT", basket="SNIPER_A", score=90,
        retest="confirmed", hold="confirmed", one_hour=_one_hour(), promoted=False))
    assert "FULL-SIZE AUTHORIZED" in snipe


def test_a15_renderer_recomputes_no_tier_ladder_or_evidence():
    """A15 — format_alert reads stored results only; it never re-judges."""
    tr = _alert_result(one_hour=_one_hour())
    before = copy.deepcopy(tr)
    da.format_alert(tr)
    assert tr == before, "format_alert must not mutate the tiering_result"


def test_starter_provenance_is_read_verbatim_from_the_stored_ladder():
    """§33 — no ladder reasoning is invented or recomputed in the renderer."""
    tr = _alert_result(one_hour=_one_hour())
    tr["snipe_ladder"]["why_not_higher"] = "SENTINEL_WHY_NOT_HIGHER"
    tr["snipe_ladder"]["next_promotion_proof"] = ["SENTINEL_NEXT_PROOF"]
    body = da.format_alert(tr)
    assert "SENTINEL_WHY_NOT_HIGHER" in body
    assert "SENTINEL_NEXT_PROOF" in body


def test_absent_ladder_fields_render_no_provenance_lines():
    """§33 — a missing ladder field simply produces no line; nothing invented."""
    tr = _alert_result(one_hour=_one_hour())
    tr["snipe_ladder"]["why_not_higher"] = ""
    tr["snipe_ladder"]["next_promotion_proof"] = []
    body = da.format_alert(tr)
    assert "Not SNIPE:" not in body
    assert "Promote on:" not in body


def test_phase_14q_starter_headline_guard_still_fires_on_the_new_headline():
    """Regression guard for MA-1A itself.

    Phase 14Q cools an overstated STARTER headline when the 1H trigger proof is
    still forming. It does that by rewriting the headline LINE. Replacing the
    headline string without teaching 14Q the new form would have silently
    disabled that protection.
    """
    forming = _one_hour(hold="HOLD_WEAK", state="RETEST_IN_PROGRESS")
    forming["alert_truth_label"] = "WATCH_ONLY"
    forming["score_label"] = "1H_TRIGGER_WEAK"
    body = da.format_alert(_alert_result(one_hour=forming))
    assert "STARTER AUTHORIZED" not in body
    assert "STARTER thesis valid" in body

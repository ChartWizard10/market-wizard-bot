"""Phase 14X.2 — analyze truth closure + structural-evidence discovery.

Two live defects, both traced to real current source before any fix:

1. _tier_judgment_section classified retest/hold independently via
   _proof_state_of(signal.get(...)) — the stale signal-level fields —
   never checking whether usable one_hour_entry evidence had already
   superseded them via the SAME _authoritative_proof_detail precedence
   every other section (VERDICT, SWING DOCTRINE SEQUENCE, LOCAL EXECUTION
   PROOF) already used. One operator case file could therefore say
   "Retest: CONFIRMED" in three places and "retest_status=partial" as a
   CURRENT missing proof in a fourth — two truths in one document.

2. tiering_result["higher_timeframe_context"] on a completed live
   run_analyze() result is the FULL NESTED object exactly as
   build_higher_timeframe_context() returns it (monthly/weekly/
   campaign_location/setup_relationship sub-dicts) — never the flattened
   shape (monthly_bias_state/weekly_campaign_state/campaign_location_label/
   context_grade as top-level keys) that only exists on an
   already-compacted persisted snapshot (higher_timeframe_context.
   compact_history_snapshot's own output). _weekly_section was reading the
   nested object as if it were flat, so every field except data_status/
   diagnostic_sentence (both happen to be top-level in either shape) was
   silently always absent — Weekly always rendered UNAVAILABLE/INCOMPLETE
   regardless of the real HTF engine's actual read.

Both are display/evidence-lineage fixes. Zero strategy files touched.
"""

import copy
import json
from pathlib import Path

from src import higher_timeframe_context as htf_engine
from src import manual_operator_audit as moa
from tests.test_phase_14x1_live_operator_truth_reconciliation import _wmt_shaped_result
from tests.test_phase_14x_full_manual_operator_audit import (
    _completed_result,
    _near_entry_result,
    _snipe_it_result,
    _starter_result,
    _wait_result,
)


# ---------------------------------------------------------------------------
# Real nested HTF fixture builder — uses the actual production shape
# (higher_timeframe_context.default_htf_object()), never a hand-invented one.
# ---------------------------------------------------------------------------

def _real_nested_htf(**overrides) -> dict:
    obj = htf_engine.default_htf_object()
    obj["data_status"] = "OK"
    obj["monthly"]["bias_state"] = "BULLISH"
    obj["weekly"]["campaign_state"] = "EXPANSION"
    obj["campaign_location"]["label"] = "MID_RANGE"
    obj["campaign_location"]["quality"] = "FUNCTIONAL"
    obj["setup_relationship"]["context_grade"] = "B"
    obj["setup_relationship"]["context_score"] = 72
    obj["setup_relationship"]["supports_long_setup"] = True
    obj["setup_relationship"]["weakens_long_setup"] = False
    obj["setup_relationship"]["blocks_snipe_contextually"] = False
    obj["diagnostic_sentence"] = "Weekly campaign supportive."
    for k, v in overrides.items():
        obj[k] = v
    return obj


# ===========================================================================
# TEST 1-2 — authoritative retest/hold removes stale missing proof
# ===========================================================================

def test_authoritative_retest_removes_stale_missing_proof():
    result = _completed_result("WAIT", retest_status="partial")
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_CONFIRMED",
    }
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert not any("retest_status=partial" in m for m in tj["missing_proof"])
    # And every section agrees it is CONFIRMED.
    assert audit["verdict_capital"]["entry_quality"].startswith("retest=CONFIRMED")
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Retest"]["state"] == "CONFIRMED"
    assert audit["execution_proof"]["retest"]["state"] == "CONFIRMED"


def test_authoritative_hold_removes_stale_missing_proof():
    result = _completed_result("WAIT", hold_status="missing")
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_CONFIRMED",
    }
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert not any("hold_status=missing" in m for m in tj["missing_proof"])
    assert audit["verdict_capital"]["entry_quality"].__contains__("hold=CONFIRMED")


# ===========================================================================
# TEST 3 — broken 1H outranks stale confirmed signal
# ===========================================================================

def test_broken_1h_outranks_stale_confirmed_signal():
    result = _completed_result("WAIT", hold_status="confirmed")
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_FAILED",
    }
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("1H hold=HOLD_FAILED" in b for b in tj["broken_proof"])
    assert not any(b for b in tj["broken_proof"] if "hold_status=confirmed" in b.lower())
    assert audit["execution_proof"]["hold"]["state"] == "BROKEN"


# ===========================================================================
# TEST 4 — unusable 1H falls back safely
# ===========================================================================

def test_unusable_1h_falls_back_to_signal_authoritatively():
    for disabled_state in ({"status": "DISABLED"}, {"status": "ERROR"}, {"status": "ENABLED", "data_freshness": "STALE"}):
        result = _completed_result("WAIT", retest_status="failed", hold_status="missing")
        result["tiering_result"]["one_hour_entry"] = disabled_state
        audit = moa.build_operator_audit(result)
        tj = audit["tier_judgment"]
        assert any("retest_status=failed" in b for b in tj["broken_proof"]), disabled_state
        assert any("hold_status=missing" in m for m in tj["missing_proof"]), disabled_state


# ===========================================================================
# TEST 5 — all sections share proof authority
# ===========================================================================

def test_all_sections_agree_on_retest_hold_state():
    for fixture in (_wait_result, _near_entry_result, _starter_result, _snipe_it_result, _wmt_shaped_result):
        result = fixture()
        audit = moa.build_operator_audit(result)
        doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
        exe = audit["execution_proof"]
        entry_quality = audit["verdict_capital"]["entry_quality"]

        assert doctrine["Retest"]["state"] == exe["retest"]["state"], fixture.__name__
        assert doctrine["Hold"]["state"] == exe["hold"]["state"], fixture.__name__
        assert f"retest={doctrine['Retest']['state']}" in entry_quality, fixture.__name__
        assert f"hold={doctrine['Hold']['state']}" in entry_quality, fixture.__name__

        # Tier Judgment must never separately claim a gap for a CONFIRMED leg.
        tj = audit["tier_judgment"]
        stale = tj["missing_proof"] + tj["broken_proof"]
        if doctrine["Retest"]["state"] == "CONFIRMED":
            assert not any("retest" in s.lower() for s in stale if s != moa._DASH), fixture.__name__
        if doctrine["Hold"]["state"] == "CONFIRMED":
            assert not any("hold" in s.lower() for s in stale if s != moa._DASH), fixture.__name__


# ===========================================================================
# TEST 6 — cross-section conflict detector (insurance check)
# ===========================================================================

def test_cross_section_conflict_detector_catches_injected_inconsistency():
    result = _wmt_shaped_result()  # authoritative retest/hold both CONFIRMED
    ev = moa._extract(result)
    fake_tier_judgment = {
        "missing_proof": ["retest_status=partial"],  # deliberately inconsistent
        "broken_proof": [moa._DASH],
    }
    ai = moa._audit_integrity_section(ev, result, fake_tier_judgment)
    assert ai["status"] == "CONFLICT"
    assert any("retest" in c.lower() for c in ai["conflicts"])


def test_cross_section_conflict_detector_silent_when_consistent():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    assert audit["audit_integrity"]["status"] == "CONSISTENT"


# ===========================================================================
# TEST 7 — missing is not broken
# ===========================================================================

def test_missing_1h_evidence_is_missing_not_broken():
    result = _completed_result("WAIT", retest_status="missing")
    result["tiering_result"]["one_hour_entry"] = {"status": "DISABLED"}
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("retest_status=missing" in m for m in tj["missing_proof"])
    assert not any("retest" in b.lower() for b in tj["broken_proof"] if b != moa._DASH)


# ===========================================================================
# TEST 8 — HTF nested object (the real production shape)
# ===========================================================================

def test_htf_nested_object_renders_actual_nested_values():
    result = _snipe_it_result()
    result["tiering_result"]["higher_timeframe_context"] = _real_nested_htf()
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["available"] is True
    assert weekly["monthly_bias"] == "BULLISH"
    assert weekly["weekly_campaign"] == "EXPANSION"
    assert weekly["location"] == "MID_RANGE"
    assert weekly["location_quality"] == "FUNCTIONAL"
    assert weekly["posture"] == "supportive"
    assert weekly["campaign_evidence"] == "COMPLETE"
    assert weekly["positive_sponsorship"] == "PROVEN"


# ===========================================================================
# TEST 9 — HTF flat compatibility (persisted/legacy snapshot shape)
# ===========================================================================

def test_htf_flat_compatibility_still_renders():
    result = _snipe_it_result()
    result["tiering_result"]["higher_timeframe_context"] = {
        "data_status": "OK",
        "monthly_bias_state": "BULLISH",
        "weekly_campaign_state": "EXPANSION",
        "campaign_location_label": "MID_RANGE",
        "campaign_location_quality": "GOOD",
        "context_grade": "A",
        "supports_long_setup": True,
        "weakens_long_setup": False,
        "blocks_snipe_contextually": False,
        "diagnostic_sentence": "Flat legacy snapshot.",
    }
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["available"] is True
    assert weekly["monthly_bias"] == "BULLISH"
    assert weekly["campaign_evidence"] == "COMPLETE"


# ===========================================================================
# TEST 10 — nested wins over a stale conflicting flat value
# ===========================================================================

def test_nested_htf_wins_over_stale_flat_value_when_both_present():
    """If a dict somehow carries both the real nested sub-objects AND a
    stray top-level flat key that disagrees with them, the nested object —
    the authoritative live source — must win. A flat key only legitimately
    exists at all on an already-compacted snapshot."""
    result = _snipe_it_result()
    htf = _real_nested_htf()  # monthly.bias_state = BULLISH
    htf["monthly_bias_state"] = "BEARISH"  # stale/foreign flat key, disagrees
    result["tiering_result"]["higher_timeframe_context"] = htf
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["monthly_bias"] == "BULLISH"  # nested wins, not the stale "BEARISH"


# ===========================================================================
# TEST 11 — UNKNOWN HTF remains UNKNOWN (no positive sponsorship)
# ===========================================================================

def test_unknown_nested_htf_never_proves_positive_sponsorship():
    result = _snipe_it_result()
    result["tiering_result"]["higher_timeframe_context"] = _real_nested_htf(
        **{}
    )
    htf = result["tiering_result"]["higher_timeframe_context"]
    htf["monthly"]["bias_state"] = "UNKNOWN"
    htf["weekly"]["campaign_state"] = "UNKNOWN"
    htf["campaign_location"]["label"] = "UNKNOWN"
    htf["setup_relationship"]["context_grade"] = "UNKNOWN"
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["campaign_evidence"] == "INCOMPLETE"
    assert weekly["positive_sponsorship"] == "NOT PROVEN"


# ===========================================================================
# TEST 12 — real WMT-shaped fixture, fully re-verified
# ===========================================================================

def test_wmt_shaped_fixture_stale_proof_removed_real_blockers_remain():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]

    assert not any("retest" in m.lower() for m in tj["missing_proof"])
    assert not any("hold" in m.lower() for m in tj["missing_proof"])
    assert tj["broken_proof"] == [moa._DASH]
    # Real remaining blockers (Daily/4H gate names) stay visible.
    assert any("DAILY_PERMISSION_GRANTED" in m for m in tj["missing_proof"])
    assert any("FOUR_H_LOCATION_VALID" in m for m in tj["missing_proof"])

    assert audit["verdict_capital"]["final_tier"] == "WAIT"
    assert audit["audit_integrity"]["status"] == "CONSISTENT"
    assert audit["audit_integrity"]["source_capital"] == "NONE"

    text = moa.render_operator_audit(result)
    assert "retest_status=partial" not in text
    assert "hold_status=missing" not in text
    assert "1H Retest:  CONFIRMED — RETEST_REAL" in text
    assert "1H Hold:    CONFIRMED — HOLD_CONFIRMED" in text
    assert "Status:                    CONSISTENT" in text


# ===========================================================================
# TEST 13 — no tier mutation
# ===========================================================================

def test_no_tier_mutation():
    result = _wmt_shaped_result()
    before = copy.deepcopy(result)
    moa.build_operator_audit(result)
    moa.render_operator_audit(result)
    moa.render_operator_audit_json(result)
    moa.render_operator_audit_compact(result)
    assert result == before


# ===========================================================================
# TEST 14 — no market/strategy calls
# ===========================================================================

def test_renderer_invokes_no_market_or_strategy_calls():
    src = Path("src/manual_operator_audit.py").read_text(encoding="utf-8")
    forbidden = [
        "import yfinance", "from src import market_data", "from src import indicators",
        "from src import prefilter", "from src.claude_client", "from src import claude_client",
        "from src import tiering", "from src import scheduler", "_complete_candidate_judgment",
        "from src import state_store", "from src import discord_alerts",
        "claude_call", "client.messages.create", "state_store.save", "state_store.record_alert",
        "discord_alerts.send_alert", "async def",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden dependency: {token!r}"
    # The one intentional exception (Phase 14X.2): a local, read-only import
    # of higher_timeframe_context's pure compact_history_snapshot serializer
    # — never a judgment call. Confirm it stays narrowly scoped to that.
    assert "compact_history_snapshot" in src
    # The renderer may only ever CALL the pure serializer, never the actual
    # judgment-producing builder (a bare docstring mention of the builder's
    # name, explaining what it returns, is fine — an actual call is not).
    assert "_htf_engine.build_higher_timeframe_context(" not in src
    assert ".build_higher_timeframe_context(" not in src


# ===========================================================================
# TEST 15-17 — full / compact / json modes
# ===========================================================================

def test_full_mode_works():
    text = moa.render_operator_audit(_wmt_shaped_result())
    assert "MANUAL TICKER AUDIT" in text


def test_compact_mode_works():
    compact = moa.render_operator_audit_compact(_wmt_shaped_result())
    assert "WMT" in compact


def test_json_mode_valid():
    payload = json.loads(moa.render_operator_audit_json(_wmt_shaped_result()))
    assert payload["tier_judgment"]["final_tier"] == "WAIT"
    assert not any("retest_status=partial" in m for m in payload["tier_judgment"]["missing_proof"])


# ===========================================================================
# TEST 18 — Discord chunking lossless
# ===========================================================================

def test_discord_chunking_lossless_with_fixed_wmt_output():
    text = moa.render_operator_audit(_wmt_shaped_result())
    long_text = (text + "\n") * 3
    chunks = moa.chunk_operator_audit(long_text, max_len=500)
    assert len(chunks) > 1
    assert "".join(chunks) == long_text


# ===========================================================================
# TEST 19 — Phase 14W parity untouched
# ===========================================================================

def test_phase_14w_parity_module_importable():
    import tests.test_phase_14w_manual_analyze_parity  # noqa: F401


# ===========================================================================
# TEST 20 — normal alert firewall (discord_alerts untouched)
# ===========================================================================

def test_discord_alerts_not_touched_by_this_phase():
    import subprocess
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    ).stdout
    assert "src/discord_alerts.py" not in diff
    assert "src/higher_timeframe_context.py" not in diff

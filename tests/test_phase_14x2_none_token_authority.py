"""Phase 14X.2 — live NONE-token authority micro-patch.

A real live production `!analyze WMT` acceptance run exposed one final
proof-authority edge case: `src/one_hour_entry.py`'s own canonical
`RETEST_TRUTH`/`HOLD_TRUTH` enums include the literal member `"NONE"` — a
USABLE 1H organ explicitly reporting that retest/hold proof has not been
earned (evidence of absence, not absence of evidence). manual_operator_
audit's `_RETEST_TRUTH_STATE`/`_HOLD_TRUTH_STATE` display-mapping dicts
omitted that key, so `_authoritative_proof_detail`'s `if truth in table`
check failed for `"NONE"` and silently fell through to the stale
signal-level `retest_status`/`hold_status` fields — even though the 1H
organ was fully usable and had already spoken. One operator case file
showed "Entry quality: retest=FORMING (partial)" while the dedicated 1H
section showed "Retest: NONE" — two truths again.

Locked law: NONE is a valid 1H truth token, distinct from the 1H organ
being unusable (DISABLED/ERROR/STALE/missing object) — only THAT class of
unusability may fall back to the signal-level fields.
"""

import copy
import json
from pathlib import Path

from src import manual_operator_audit as moa
from src import one_hour_entry
from tests.test_phase_14x_full_manual_operator_audit import (
    _completed_result,
    _snipe_it_result,
)


def _usable_one_hour(trigger_state="PULLBACK_FORMING", retest_truth="NONE",
                      hold_truth="NONE", freshness="FRESH", score=44,
                      score_label="NO_VALID_1H_TRIGGER"):
    return {
        "status": "ENABLED", "data_freshness": freshness,
        "trigger_state": trigger_state, "score": score, "score_label": score_label,
        "pullback_retest_hold": {"retest_truth": retest_truth, "hold_truth": hold_truth},
        "location_realism": {"label": "MIDRANGE_NO_EDGE"},
        "candle_truth": {"event_type": "NONE", "closed_candle_confirms": False},
        "invalidation": {"clear": True},
        "path_quality": {"path_label": "UNKNOWN"},
        "hard_caps_applied": [], "downgrade_reasons": [],
        "alert_truth_label": "NO_ALERT",
        "scanner_sentence": "1H has not earned trigger proof yet.",
    }


def _wmt_none_none_result() -> dict:
    """The real live-observed WMT shape: 1H usable/FRESH, PULLBACK_FORMING,
    retest_truth=NONE, hold_truth=NONE, signal-level fields stale
    (partial/missing)."""
    result = _completed_result(
        "WAIT",
        retest_status="partial", hold_status="missing",
        discord_channel="none", capital_action="no_trade",
    )
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour()
    return result


# ===========================================================================
# TEST 1-2 — canonical NONE wins over stale signal fallback
# ===========================================================================

def test_retest_none_from_usable_1h_outranks_stale_signal_partial():
    result = _completed_result("WAIT", retest_status="partial")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(retest_truth="NONE", hold_truth="HOLD_CONFIRMED")
    state, raw, src = moa._authoritative_proof_detail(
        result["tiering_result"]["one_hour_entry"], "retest_truth", moa._RETEST_TRUTH_STATE,
        result["tiering_result"]["final_signal"]["retest_status"],
    )
    assert state == "MISSING"
    assert raw == "NONE"
    assert src == "1H"


def test_hold_none_from_usable_1h_outranks_stale_signal_confirmed():
    result = _completed_result("WAIT", hold_status="confirmed")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(retest_truth="RETEST_MISSED", hold_truth="NONE")
    state, raw, src = moa._authoritative_proof_detail(
        result["tiering_result"]["one_hour_entry"], "hold_truth", moa._HOLD_TRUTH_STATE,
        result["tiering_result"]["final_signal"]["hold_status"],
    )
    assert state == "MISSING"
    assert raw == "NONE"
    assert src == "1H"


# ===========================================================================
# TEST 3-4 — all sections agree on NONE/NONE; never falls back to SIGNAL
# ===========================================================================

def test_all_sections_agree_on_none_none_and_never_use_signal():
    result = _wmt_none_none_result()
    audit = moa.build_operator_audit(result)

    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    exe = audit["execution_proof"]
    entry_quality = audit["verdict_capital"]["entry_quality"]
    tj = audit["tier_judgment"]

    assert doctrine["Retest"]["state"] == "MISSING"
    assert doctrine["Hold"]["state"] == "MISSING"
    assert exe["retest"]["state"] == "MISSING"
    assert exe["hold"]["state"] == "MISSING"
    assert exe["retest"]["raw"] == "NONE"
    assert exe["hold"]["raw"] == "NONE"

    assert "retest=MISSING" in entry_quality
    assert "hold=MISSING" in entry_quality
    # The stale signal-level tokens must not appear as the resolved state.
    assert "retest=FORMING" not in entry_quality
    assert "(partial)" not in entry_quality
    assert "(missing)" not in entry_quality or "1H" in entry_quality

    # Tier Judgment must reflect the 1H-sourced NONE, never the raw signal
    # value, as the CURRENT proof gap.
    assert any("1H retest=MISSING (NONE)" in m for m in tj["missing_proof"])
    assert any("1H hold=MISSING (NONE)" in m for m in tj["missing_proof"])
    assert not any("retest_status=partial" in m for m in tj["missing_proof"])
    assert not any("hold_status=missing" in m for m in tj["missing_proof"])

    assert audit["audit_integrity"]["status"] == "CONSISTENT"


# ===========================================================================
# TEST 5-7 — unusable 1H still falls back safely
# ===========================================================================

def test_disabled_1h_signal_fallback_still_works():
    result = _completed_result("WAIT", retest_status="partial", hold_status="missing")
    result["tiering_result"]["one_hour_entry"] = {"status": "DISABLED"}
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("retest_status=partial" in m for m in tj["missing_proof"])
    assert any("hold_status=missing" in m for m in tj["missing_proof"])
    assert audit["audit_integrity"]["status"] == "CONSISTENT"


def test_error_1h_signal_fallback_still_works():
    result = _completed_result("WAIT", retest_status="partial", hold_status="missing")
    result["tiering_result"]["one_hour_entry"] = {"status": "ERROR"}
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("retest_status=partial" in m for m in tj["missing_proof"])
    assert audit["audit_integrity"]["status"] == "CONSISTENT"


def test_stale_1h_signal_fallback_still_works():
    result = _completed_result("WAIT", retest_status="partial", hold_status="missing")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(freshness="STALE")
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("retest_status=partial" in m for m in tj["missing_proof"])
    assert audit["audit_integrity"]["status"] == "CONSISTENT"


# ===========================================================================
# TEST 8-10 — existing display contract for real non-NONE tokens preserved
# ===========================================================================

def test_retest_missed_remains_missing():
    result = _completed_result("WAIT")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(retest_truth="RETEST_MISSED", hold_truth="HOLD_CONFIRMED")
    state, raw, src = moa._authoritative_proof_detail(
        result["tiering_result"]["one_hour_entry"], "retest_truth", moa._RETEST_TRUTH_STATE, "partial"
    )
    assert state == "MISSING" and src == "1H"


def test_hold_failed_remains_broken():
    result = _completed_result("WAIT")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(retest_truth="RETEST_REAL", hold_truth="HOLD_FAILED")
    state, raw, src = moa._authoritative_proof_detail(
        result["tiering_result"]["one_hour_entry"], "hold_truth", moa._HOLD_TRUTH_STATE, "confirmed"
    )
    assert state == "BROKEN" and src == "1H"


def test_retest_edge_only_remains_forming():
    result = _completed_result("WAIT")
    result["tiering_result"]["one_hour_entry"] = _usable_one_hour(retest_truth="RETEST_EDGE_ONLY", hold_truth="HOLD_FORMING")
    state, raw, src = moa._authoritative_proof_detail(
        result["tiering_result"]["one_hour_entry"], "retest_truth", moa._RETEST_TRUTH_STATE, "missing"
    )
    assert state == "FORMING" and src == "1H"


# ===========================================================================
# TEST 11 — full WMT live-shaped golden
# ===========================================================================

def test_wmt_live_shaped_none_none_golden():
    result = _wmt_none_none_result()
    audit = moa.build_operator_audit(result)

    assert audit["verdict_capital"]["entry_quality"].startswith("retest=MISSING (NONE) / hold=MISSING (NONE)")
    exe = audit["execution_proof"]
    assert exe["retest"]["state"] == "MISSING" and exe["retest"]["raw"] == "NONE"
    assert exe["hold"]["state"] == "MISSING" and exe["hold"]["raw"] == "NONE"

    tj = audit["tier_judgment"]
    assert not any("retest_status=partial" in m for m in tj["missing_proof"])
    assert not any("hold_status=missing" in m for m in tj["missing_proof"])

    assert audit["audit_integrity"]["status"] == "CONSISTENT"
    assert audit["verdict_capital"]["final_tier"] == "WAIT"
    assert audit["audit_integrity"]["source_capital"] == "NONE"

    text = moa.render_operator_audit(result)
    assert "retest_status=partial" not in text
    assert "hold_status=missing" not in text
    assert "Status:                    CONSISTENT" in text


# ===========================================================================
# TEST 12 — injected fallback leak is caught by Audit Integrity
# ===========================================================================

def test_injected_authority_fallback_leak_is_caught():
    """Directly construct the leak the fix closes (usable canonical NONE
    but a SIGNAL-sourced resolved state) and confirm the new guard in
    _audit_integrity_section flags it — proving the guard itself works
    independent of the direct fix, as insurance against future regressions."""
    result = _wmt_none_none_result()
    ev = moa._extract(result)

    # Monkeypatch the resolution: force _local_execution_states to report a
    # SIGNAL-sourced retest despite the raw 1H token being a real "NONE".
    orig = moa._local_execution_states
    try:
        def _leaky(ev_arg):
            states = dict(orig(ev_arg))
            states["retest_src"] = "SIGNAL"
            return states
        moa._local_execution_states = _leaky
        tier_judgment = moa._tier_judgment_section(ev, result)
        ai = moa._audit_integrity_section(ev, result, tier_judgment)
        assert ai["status"] == "CONFLICT"
        assert any("discarded in favor of the stale signal-level field" in c for c in ai["conflicts"])
    finally:
        moa._local_execution_states = orig


# ===========================================================================
# Canonical-enum coverage lock — guards this fix against future 1H drift
# ===========================================================================

def test_retest_and_hold_truth_state_cover_every_current_canonical_token():
    """Locks the fix against future drift: if one_hour_entry.py ever adds a
    new RETEST_TRUTH/HOLD_TRUTH member, this test fails immediately rather
    than silently falling back to SIGNAL again."""
    assert set(moa._RETEST_TRUTH_STATE.keys()) == one_hour_entry.RETEST_TRUTH
    assert set(moa._HOLD_TRUTH_STATE.keys()) == one_hour_entry.HOLD_TRUTH


# ===========================================================================
# Purity / no-mutation / no-market-call (belt-and-suspenders for this patch)
# ===========================================================================

def test_no_mutation_across_all_fixtures():
    for fixture in (_wmt_none_none_result, _snipe_it_result):
        original = fixture()
        snapshot = copy.deepcopy(original)
        moa.build_operator_audit(original)
        moa.render_operator_audit(original)
        moa.render_operator_audit_json(original)
        moa.render_operator_audit_compact(original)
        assert original == snapshot


def test_renderer_still_pure_no_new_dependency():
    src = Path("src/manual_operator_audit.py").read_text(encoding="utf-8")
    forbidden = [
        "import yfinance", "from src import market_data", "from src import indicators",
        "from src import prefilter", "from src.claude_client", "from src import claude_client",
        "from src import tiering", "from src import scheduler", "_complete_candidate_judgment",
        "from src import state_store", "from src import discord_alerts",
        "from src import one_hour_entry", "claude_call", "client.messages.create",
        "state_store.save", "state_store.record_alert", "discord_alerts.send_alert", "async def",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden dependency: {token!r}"


def test_json_mode_reflects_the_fix():
    result = _wmt_none_none_result()
    payload = json.loads(moa.render_operator_audit_json(result))
    assert not any("retest_status=partial" in m for m in payload["tier_judgment"]["missing_proof"])
    assert payload["audit_integrity"]["status"] == "CONSISTENT"

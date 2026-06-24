"""Phase 14O — 1H + timeframe alignment evidence persistence ledger tests.

Black-box recorder: record_alert persists compact, JSON-safe evidence
snapshots of tiering_result["one_hour_entry"] and tiering_result
["timeframe_alignment"] into alert_history, so a post-hoc audit can inspect
what the deterministic 1H-entry and multi-timeframe-alignment organs actually
saw at scan time. This is evidence/display persistence only: it never
re-derives the evidence, never mutates the source objects, and never affects
final_tier, capital_action, score, safe_for_alert, retest_status, hold_status,
routing, dedup, or alert wording.
"""

import copy
import json

from src import audit_access
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Builders — real one_hour_entry.py / timeframe_alignment.py field shapes
# ---------------------------------------------------------------------------

def _one_hour_entry(**over):
    oh = {
        "enabled": True,
        "timeframe": "1H",
        "status": "ENABLED",
        "data_freshness": "FRESH",
        "bar_context": {
            "last_closed_bar_time": "2026-06-23T15:00:00",
            "current_live_bar_time": "2026-06-23T16:00:00",
            "closed_bar_available": True,
            "live_bar_available": True,
            "using_live_bar_for_confirmation": False,
        },
        "trigger_state": "HOLD_CONFIRMED",
        "location_realism": {
            "label": "AT_VALID_TRIGGER",
            "reason": "price holding above reclaimed level",
            "distance_to_trigger_pct": 0.4,
            "distance_to_invalidation_pct": 2.1,
            "distance_to_overhead_pct": 5.6,
        },
        "candle_truth": {
            "event_type": "DISPLACEMENT",
            "closed_candle_confirms": True,
            "live_candle_constructive": True,
            "body_acceptance": True,
            "wick_rejection": False,
            "follow_through_present": True,
            "volume_support": "CONFIRMED",
        },
        "pullback_retest_hold": {
            "pullback_truth": "PULLBACK_CONFIRMED",
            "retest_truth": "RETEST_CONFIRMED",
            "hold_truth": "HOLD_CONFIRMED",
            "retest_zone_type": "DEMAND",
        },
        "invalidation": {
            "clear": True,
            "level": 138.0,
            "condition": "1H close below 138",
            "invalidation_distance_pct": 2.1,
        },
        "path_quality": {
            "overhead_clear_enough": True,
            "nearest_resistance": 150.0,
            "rr_estimate": 3.2,
            "path_label": "CLEAR",
        },
        "score": 86,
        "score_label": "STRONG_1H_TRIGGER",
        "hard_caps_applied": [],
        "downgrade_reasons": [],
        "alert_truth_label": "TRIGGER_LIVE_READY",
        "scanner_sentence": "1H trigger confirmed with clean hold above reclaim.",
    }
    oh.update(over)
    return oh


def _timeframe_alignment(**over):
    def _layer(tf, role, state):
        return {
            "timeframe": tf, "role": role, "state": state,
            "evidence": [f"{role.lower()} evidence line"],
            "warnings": [],
            "blocks_trigger": False,
        }
    tfa = {
        "enabled": True,
        "status": "ENABLED",
        "alignment_grade": "A-",
        "alignment_score": 88,
        "alignment_label": "FULL_STACK_ALIGNED",
        "campaign_timeframe": _layer("1W", "CAMPAIGN_CONTEXT", "BULLISH"),
        "swing_timeframe": _layer("1D", "SWING_PERMISSION", "PERMISSION_GRANTED"),
        "operational_timeframe": _layer("4H", "OPERATIONAL_LOCATION", "LOCATION_VALID"),
        "trigger_timeframe": _layer("1H", "TRIGGER_PROOF", "TRIGGER_CONFIRMED"),
        "conflicts": [],
        "missing_context": [],
        "hard_caps_applied": [],
        "downgrade_reasons": [],
        "scanner_sentence": "All timeframes aligned; trigger confirmed.",
    }
    tfa.update(over)
    return tfa


def _tiering(oh="default", tfa="default", final_tier="STARTER", **sig):
    signal = {
        "ticker": "FORM", "trigger_level": 141.84, "invalidation_level": 138.0,
        "reason": "demand reclaim", "retest_status": "confirmed", "hold_status": "confirmed",
        "capital_action": "starter_only",
    }
    signal.update(sig)
    tr = {
        "final_tier": final_tier, "final_discord_channel": "starter",
        "safe_for_alert": True, "score": 80, "final_signal": signal,
    }
    if oh == "default":
        tr["one_hour_entry"] = _one_hour_entry()
    elif oh is not _OMIT:
        tr["one_hour_entry"] = oh
    if tfa == "default":
        tr["timeframe_alignment"] = _timeframe_alignment()
    elif tfa is not _OMIT:
        tr["timeframe_alignment"] = tfa
    return tr


_OMIT = object()


def _cfg():
    return {"state": {"max_memory_entries": 500}}


def _record(tr):
    state = {"tickers": {}, "meta": {}}
    state = record_alert("FORM", tr, state, _cfg(), "scan1")
    return state["tickers"]["FORM"]["alert_history"][-1]


# ===========================================================================
# 1 — one_hour_entry snapshot persisted with real fields
# ===========================================================================

def test_one_hour_entry_snapshot_persisted():
    row = _record(_tiering())
    oh = row["one_hour_entry"]
    assert oh is not None
    assert oh["status"] == "ENABLED"
    assert oh["data_freshness"] == "FRESH"
    assert oh["trigger_state"] == "HOLD_CONFIRMED"
    assert oh["score"] == 86
    assert oh["score_label"] == "STRONG_1H_TRIGGER"
    assert oh["alert_truth_label"] == "TRIGGER_LIVE_READY"
    assert oh["scanner_sentence"].startswith("1H trigger confirmed")


def test_one_hour_entry_nested_sub_objects_persisted():
    row = _record(_tiering())
    oh = row["one_hour_entry"]
    assert oh["location_realism"]["label"] == "AT_VALID_TRIGGER"
    assert oh["candle_truth"]["event_type"] == "DISPLACEMENT"
    assert oh["candle_truth"]["closed_candle_confirms"] is True
    assert oh["pullback_retest_hold"]["hold_truth"] == "HOLD_CONFIRMED"
    assert oh["pullback_retest_hold"]["retest_truth"] == "RETEST_CONFIRMED"
    assert oh["invalidation"]["clear"] is True
    assert oh["invalidation"]["level"] == 138.0
    assert oh["path_quality"]["path_label"] == "CLEAR"
    assert oh["bar_context"]["closed_bar_available"] is True


# ===========================================================================
# 2 — timeframe_alignment snapshot persisted with real fields
# ===========================================================================

def test_timeframe_alignment_snapshot_persisted():
    row = _record(_tiering())
    tfa = row["timeframe_alignment"]
    assert tfa is not None
    assert tfa["alignment_grade"] == "A-"
    assert tfa["alignment_score"] == 88
    assert tfa["alignment_label"] == "FULL_STACK_ALIGNED"
    assert tfa["campaign_timeframe"]["state"] == "BULLISH"
    assert tfa["swing_timeframe"]["state"] == "PERMISSION_GRANTED"
    assert tfa["operational_timeframe"]["state"] == "LOCATION_VALID"
    assert tfa["trigger_timeframe"]["state"] == "TRIGGER_CONFIRMED"
    assert tfa["scanner_sentence"] == "All timeframes aligned; trigger confirmed."


def test_timeframe_alignment_layer_fields_complete():
    row = _record(_tiering())
    layer = row["timeframe_alignment"]["trigger_timeframe"]
    assert layer["timeframe"] == "1H"
    assert layer["role"] == "TRIGGER_PROOF"
    assert layer["evidence"] == ["trigger_proof evidence line"]
    assert layer["warnings"] == []
    assert layer["blocks_trigger"] is False


# ===========================================================================
# 3 — missing source objects persist safely as None
# ===========================================================================

def test_missing_one_hour_entry_is_none():
    row = _record(_tiering(oh=_OMIT))
    assert row["one_hour_entry"] is None
    # existing fields untouched
    assert row["retest_status"] == "confirmed"
    assert row["hold_status"] == "confirmed"


def test_missing_timeframe_alignment_is_none():
    row = _record(_tiering(tfa=_OMIT))
    assert row["timeframe_alignment"] is None


def test_one_hour_entry_explicit_none_persists_none():
    row = _record(_tiering(oh=None))
    assert row["one_hour_entry"] is None


# ===========================================================================
# 4 — malformed source objects degrade safely (never raise)
# ===========================================================================

def test_malformed_one_hour_entry_degrades_safely():
    row = _record(_tiering(oh="not a dict"))
    oh = row["one_hour_entry"]
    assert oh["status"] is None
    assert oh["score"] is None
    assert any("degraded" in r for r in oh["downgrade_reasons"])


def test_malformed_timeframe_alignment_degrades_safely():
    row = _record(_tiering(tfa=12345))
    tfa = row["timeframe_alignment"]
    assert tfa["alignment_grade"] is None
    assert tfa["alignment_score"] is None
    assert any("degraded" in r for r in tfa["downgrade_reasons"])


def test_malformed_nested_sub_objects_degrade_safely():
    oh = _one_hour_entry(location_realism="bad", candle_truth=None, pullback_retest_hold=123)
    row = _record(_tiering(oh=oh))
    snap = row["one_hour_entry"]
    assert snap["location_realism"] is None
    assert snap["candle_truth"] is None
    assert snap["pullback_retest_hold"] is None
    # sibling scalar fields still extracted
    assert snap["trigger_state"] == "HOLD_CONFIRMED"


def test_malformed_timeframe_layer_degrades_safely():
    tfa = _timeframe_alignment(campaign_timeframe="bad", conflicts="bad", missing_context=None)
    row = _record(_tiering(tfa=tfa))
    snap = row["timeframe_alignment"]
    assert snap["campaign_timeframe"] is None
    assert snap["conflicts"] == []
    assert snap["missing_context"] == []
    assert snap["alignment_grade"] == "A-"


# ===========================================================================
# 5 — strict JSON safety (NaN/Infinity/bool-as-int/nested objects)
# ===========================================================================

def _unsafe_one_hour_entry():
    return {
        "enabled": "yes",
        "status": {"bad": "object"},
        "data_freshness": object(),
        "trigger_state": ["bad"],
        "score": float("nan"),
        "score_label": True,
        "hard_caps_applied": "not a list",
        "downgrade_reasons": [object(), "valid reason"],
        "alert_truth_label": None,
        "scanner_sentence": object(),
        "location_realism": {"distance_to_trigger_pct": float("inf")},
        "invalidation": {"level": float("nan"), "clear": "yes"},
        "path_quality": {"rr_estimate": float("-inf")},
    }


def _unsafe_timeframe_alignment():
    return {
        "alignment_score": float("nan"),
        "alignment_grade": object(),
        "campaign_timeframe": {"state": True, "evidence": "not a list", "blocks_trigger": "yes"},
        "conflicts": [{"layer": object(), "reason": "ok reason"}, "bad item"],
        "missing_context": [object(), "valid"],
    }


def test_unsafe_one_hour_entry_never_raises_and_strict_json_safe():
    row = _record(_tiering(oh=_unsafe_one_hour_entry()))
    json.dumps(row, allow_nan=False)   # must not raise
    snap = row["one_hour_entry"]
    assert snap["score"] is None
    assert snap["score_label"] is None
    assert snap["hard_caps_applied"] == []
    assert snap["downgrade_reasons"] == ["valid reason"]
    assert snap["location_realism"]["distance_to_trigger_pct"] is None
    assert snap["invalidation"]["level"] is None
    assert snap["invalidation"]["clear"] is None
    assert snap["path_quality"]["rr_estimate"] is None


def test_unsafe_timeframe_alignment_never_raises_and_strict_json_safe():
    row = _record(_tiering(tfa=_unsafe_timeframe_alignment()))
    json.dumps(row, allow_nan=False)   # must not raise
    snap = row["timeframe_alignment"]
    assert snap["alignment_score"] is None
    assert snap["alignment_grade"] is None
    assert snap["campaign_timeframe"]["state"] is None
    assert snap["campaign_timeframe"]["evidence"] == []
    assert snap["campaign_timeframe"]["blocks_trigger"] is None
    assert snap["conflicts"] == [{"layer": None, "reason": "ok reason"}]
    assert snap["missing_context"] == ["valid"]


# ===========================================================================
# 6 — never mutates the source tiering_result
# ===========================================================================

def test_no_mutation_of_tiering_result():
    tr = _tiering()
    before = copy.deepcopy(tr)
    state = {"tickers": {}, "meta": {}}
    record_alert("FORM", tr, state, _cfg(), "scan1")
    assert tr == before


def test_no_mutation_of_unsafe_source():
    tr = _tiering(oh=_unsafe_one_hour_entry(), tfa=_unsafe_timeframe_alignment())
    src_oh = tr["one_hour_entry"]
    src_tfa = tr["timeframe_alignment"]
    _record(tr)
    assert src_oh["score"] != src_oh["score"]   # still NaN (NaN != NaN)
    assert src_tfa["alignment_score"] != src_tfa["alignment_score"]


# ===========================================================================
# 7 — legacy proxies preserved unchanged, never replaced
# ===========================================================================

def test_legacy_retest_hold_proxies_preserved_alongside_new_evidence():
    row = _record(_tiering())
    assert row["retest_status"] == "confirmed"
    assert row["hold_status"] == "confirmed"
    # New evidence is a sibling, not a replacement.
    assert row["one_hour_entry"]["pullback_retest_hold"]["hold_truth"] == "HOLD_CONFIRMED"


def test_no_trading_fields_touched():
    row = _record(_tiering())
    assert row["tier"] == "STARTER"
    assert row["score"] == 80
    assert row["capital_action"] == "starter_only"


# ===========================================================================
# 8 — no full-object bloat: only the documented snapshot keys persist
# ===========================================================================

def test_one_hour_entry_snapshot_key_set_is_closed():
    row = _record(_tiering())
    expected = {
        "enabled", "status", "data_freshness", "bar_context", "trigger_state",
        "location_realism", "candle_truth", "pullback_retest_hold",
        "invalidation", "path_quality", "score", "score_label",
        "hard_caps_applied", "downgrade_reasons", "alert_truth_label",
        "scanner_sentence",
    }
    assert set(row["one_hour_entry"].keys()) == expected


def test_timeframe_alignment_snapshot_key_set_is_closed():
    row = _record(_tiering())
    expected = {
        "enabled", "status", "alignment_grade", "alignment_score",
        "alignment_label", "campaign_timeframe", "swing_timeframe",
        "operational_timeframe", "trigger_timeframe", "conflicts",
        "missing_context", "hard_caps_applied", "downgrade_reasons",
        "scanner_sentence",
    }
    assert set(row["timeframe_alignment"].keys()) == expected


# ===========================================================================
# 9 — record_alert trimming unaffected; every retained row carries snapshots
# ===========================================================================

def test_trimming_unchanged_with_new_snapshots():
    state = {"tickers": {}, "meta": {}}
    cfg = {"state": {"max_memory_entries": 3}}
    for _ in range(5):
        state = record_alert("FORM", _tiering(), state, cfg, "s")
    hist = state["tickers"]["FORM"]["alert_history"]
    assert len(hist) == 3
    assert all(r.get("one_hour_entry") is not None for r in hist)
    assert all(r.get("timeframe_alignment") is not None for r in hist)


# ===========================================================================
# 10 — audit_access.format_row renders the new evidence when present
# ===========================================================================

def test_format_row_renders_one_hour_entry_block():
    row = _record(_tiering())
    text = audit_access.format_row(row)
    assert "__1H ENTRY__" in text
    assert "Status: ENABLED" in text
    assert "Trigger state: HOLD_CONFIRMED" in text
    assert "Score: 86 (STRONG_1H_TRIGGER)" in text
    assert "Retest: confirmed" in text
    assert "Hold: confirmed" in text
    assert "Hold truth: HOLD_CONFIRMED" in text
    assert "Retest truth: RETEST_CONFIRMED" in text
    assert "Location: AT_VALID_TRIGGER" in text
    assert "Candle: DISPLACEMENT" in text


def test_format_row_renders_timeframe_alignment_block():
    row = _record(_tiering())
    text = audit_access.format_row(row)
    assert "__TIMEFRAME ALIGNMENT__" in text
    assert "Alignment grade / score: A- / 88" in text
    assert "Alignment label: FULL_STACK_ALIGNED" in text
    assert "Campaign (1W) state: BULLISH" in text
    assert "Swing (1D) permission: PERMISSION_GRANTED" in text
    assert "Operational (4H) location: LOCATION_VALID" in text
    assert "Trigger (1H) proof: TRIGGER_CONFIRMED" in text


# ===========================================================================
# 11 — legacy rows (no Phase 14O snapshot) keep the honest fallback wording
# ===========================================================================

def _legacy_row():
    return {
        "ticker": "HAE", "tier": "STARTER", "scan_id": "scan_legacy",
        "alerted_at": "2026-01-01T00:00:00", "retest_status": "confirmed",
        "hold_status": "confirmed", "capital_action": "starter_only",
        "score": 80, "final_discord_channel": "starter",
        "snipe_gate_audit": None, "higher_timeframe_context": None,
        # no one_hour_entry / timeframe_alignment keys at all
    }


def test_legacy_row_one_hour_entry_fallback_wording():
    text = audit_access.format_row(_legacy_row())
    assert "n/a (not persisted on this historical row)" in text
    # legacy proxy lines still render
    assert "Retest: confirmed" in text
    assert "Hold: confirmed" in text


def test_legacy_row_timeframe_alignment_fallback_wording():
    text = audit_access.format_row(_legacy_row())
    assert "Phase 14F timeframe_alignment object is not persisted on this historical row." in text


def test_legacy_row_explicit_none_keys_also_fall_back():
    row = _legacy_row()
    row["one_hour_entry"] = None
    row["timeframe_alignment"] = None
    text = audit_access.format_row(row)
    assert "n/a (not persisted on this historical row)" in text
    assert "Phase 14F timeframe_alignment object is not persisted on this historical row." in text


# ===========================================================================
# 12 — compact_json passthrough
# ===========================================================================

def test_compact_json_includes_one_hour_entry_and_timeframe_alignment():
    row = _record(_tiering())
    payload = audit_access.compact_json(row)
    assert payload["one_hour_entry"]["trigger_state"] == "HOLD_CONFIRMED"
    assert payload["timeframe_alignment"]["alignment_label"] == "FULL_STACK_ALIGNED"


def test_compact_json_legacy_row_has_none_for_new_fields():
    payload = audit_access.compact_json(_legacy_row())
    assert payload["one_hour_entry"] is None
    assert payload["timeframe_alignment"] is None
    # legacy proxies still present
    assert payload["retest_status"] == "confirmed"
    assert payload["hold_status"] == "confirmed"


# ===========================================================================
# 13 — no secret/object leakage through the new fields, strictly JSON-safe
# ===========================================================================

def test_no_secret_leak_through_unsafe_one_hour_entry():
    unsafe = _unsafe_one_hour_entry()
    unsafe["scanner_sentence"] = object()
    row = _record(_tiering(oh=unsafe))
    text = audit_access.format_row(row)
    assert "object at 0x" not in text
    payload = audit_access.compact_json(row)
    json.dumps(payload, allow_nan=False)   # must not raise


# ===========================================================================
# 14 — end-to-end: !audit text output surfaces the new evidence
# ===========================================================================

def test_run_audit_text_mode_includes_new_evidence_labels(tmp_path):
    state = {"tickers": {"FORM": {"alert_history": [_record(_tiering())]}}, "meta": {"total_alerts": 1}}
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    cfg = {
        "state": {"state_file": str(p)},
        "audit_access": {"enabled": True, "allowed_user_ids": [111]},
    }
    res = audit_access.run_audit(cfg, "FORM", user_id=111, channel_id=999)
    assert res["ok"] is True
    text = "\n".join(res["messages"])
    assert "__1H ENTRY__" in text
    assert "__TIMEFRAME ALIGNMENT__" in text
    assert "HOLD_CONFIRMED" in text
    assert "FULL_STACK_ALIGNED" in text


def test_run_audit_json_mode_includes_new_evidence_keys(tmp_path):
    state = {"tickers": {"FORM": {"alert_history": [_record(_tiering())]}}, "meta": {"total_alerts": 1}}
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    cfg = {
        "state": {"state_file": str(p)},
        "audit_access": {"enabled": True, "allowed_user_ids": [111]},
    }
    res = audit_access.run_audit(cfg, "FORM json", user_id=111, channel_id=999)
    assert res["ok"] is True
    payload = res["json"][0]
    assert payload["one_hour_entry"]["score"] == 86
    assert payload["timeframe_alignment"]["alignment_score"] == 88


# ===========================================================================
# 15 — !auditready machinery tolerates the new fields without changes
# ===========================================================================

def test_auditready_unaffected_by_new_evidence_fields():
    row = _record(_tiering(
        oh=_one_hour_entry(), tfa=_timeframe_alignment(),
    ))
    row["snipe_gate_audit"] = {
        "audit_label": "STARTER_ONLY_VALID", "promotion_state": "PROMOTION_READY",
        "eligible_for_snipe_review": True, "blocked_gate_names": [], "blocked_gates": [],
        "missing_proofs": [], "score_blocked_by": [], "blocking_reasons": [],
        "diagnostic_sentence": "ready",
    }
    ok, why = audit_access.is_auditready_candidate(row)
    assert ok is True
    assert any("PROMOTION_READY" in w for w in why)

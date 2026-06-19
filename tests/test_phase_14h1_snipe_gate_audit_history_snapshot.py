"""Phase 14H.1 — SNIPE gate-audit history snapshot tests.

Verifies record_alert persists a compact, JSON-safe grading snapshot of
tiering_result["snipe_gate_audit"] into alert_history — defensively (never
raises on missing/malformed audit), without persisting the full 14H object, and
without changing any existing alert_history field or trimming behavior.
"""

import copy
import json

from src import state_store as ss
from src.state_store import record_alert


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _audit(**over):
    a = {
        "enabled": True, "status": "ENABLED",
        "audit_label": "STARTER_ONLY_VALID",
        "promotion_state": "PROMOTION_PENDING",
        "snipe_score": 92, "snipe_grade": "A",
        "current_final_tier": "STARTER", "current_capital_action": "starter_only",
        "eligible_for_snipe_review": True,
        # Bloat fields that must NOT be persisted:
        "passed_gates": [{"gate": "RETEST_CONFIRMED", "status": "PASS"}],
        "evidence_sources": {"tiering": True, "one_hour_entry": True},
        "invalidation": {"level": 99.5, "clear": True},
        "risk": {"rr": 4.0, "asymmetry_valid": True},
        "blocked_gates": [{
            "gate": "ONE_H_TRIGGER_CONFIRMED", "status": "UNKNOWN",
            "reason": "1H hold forming", "source": "one_hour_entry",
        }],
        "missing_proofs": ["ONE_H_TRIGGER_CONFIRMED: 1H closed hold missing"],
        "promotion_triggers": ["1H closed hold above 102.00"],
        "blocking_reasons": [],
        "diagnostic_sentence": "SNIPE audit: starter valid, but SNIPE promotion waits for 1H proof.",
    }
    a.update(over)
    return a


def _tiering(audit="default", final_tier="STARTER", **sig):
    signal = {
        "ticker": "HAE", "trigger_level": 102.0, "invalidation_level": 99.5,
        "reason": "BOS", "retest_status": "confirmed", "hold_status": "confirmed",
        "overhead_status": "clear", "structure_event": "bos",
        "missing_conditions": [], "upgrade_trigger": "body close above 102",
        "capital_action": "starter_only", "risk_reward": 4.0, "scan_price": 101.2,
    }
    signal.update(sig)
    tr = {
        "final_tier": final_tier, "final_discord_channel": "starter",
        "safe_for_alert": True, "score": 80, "original_claude_tier": final_tier,
        "applied_vetoes": [], "final_signal": signal,
    }
    if audit == "default":
        tr["snipe_gate_audit"] = _audit()
    elif audit is not _OMIT:
        tr["snipe_gate_audit"] = audit
    return tr


_OMIT = object()


def _cfg():
    return {"state": {"max_memory_entries": 500}}


def _record(tr):
    state = {"tickers": {}, "meta": {}}
    state = record_alert("HAE", tr, state, _cfg(), "scan1")
    return state["tickers"]["HAE"]["alert_history"][-1]


# ===========================================================================
# 1 — Snapshot persisted when audit exists
# ===========================================================================

def test_snapshot_persisted_when_audit_exists():
    row = _record(_tiering())
    snap = row["snipe_gate_audit"]
    assert snap is not None
    assert set(snap.keys()) == set(ss._SNIPE_SNAPSHOT_KEYS)
    assert snap["audit_label"] == "STARTER_ONLY_VALID"
    assert snap["promotion_state"] == "PROMOTION_PENDING"
    assert snap["snipe_score"] == 92
    assert snap["snipe_grade"] == "A"
    assert snap["eligible_for_snipe_review"] is True
    assert snap["diagnostic_sentence"].startswith("SNIPE audit:")


# ===========================================================================
# 2 — blocked_gate_names generated
# ===========================================================================

def test_blocked_gate_names_generated():
    row = _record(_tiering())
    assert row["snipe_gate_audit"]["blocked_gate_names"] == ["ONE_H_TRIGGER_CONFIRMED"]


# ===========================================================================
# 3 — blocked_gates supports list[str]
# ===========================================================================

def test_blocked_gates_list_of_strings():
    row = _record(_tiering(audit=_audit(blocked_gates=["OVERHEAD_CLEAR", "PATH_CLEAN"])))
    snap = row["snipe_gate_audit"]
    assert snap["blocked_gate_names"] == ["OVERHEAD_CLEAR", "PATH_CLEAN"]
    assert snap["blocked_gates"] == [
        {"gate": "OVERHEAD_CLEAR", "status": None, "reason": None, "source": None},
        {"gate": "PATH_CLEAN", "status": None, "reason": None, "source": None},
    ]


# ===========================================================================
# 4 — dict fallback keys for gate names (gate > name > id > key)
# ===========================================================================

def test_blocked_gate_name_fallback_keys():
    row = _record(_tiering(audit=_audit(blocked_gates=[
        {"name": "HOLD_CONFIRMED"}, {"id": "INVALIDATION_CLEAR"},
        {"key": "ASYMMETRY_VALID"}, {"gate": "OVERHEAD_CLEAR", "name": "ignored"},
    ])))
    assert row["snipe_gate_audit"]["blocked_gate_names"] == [
        "HOLD_CONFIRMED", "INVALIDATION_CLEAR", "ASYMMETRY_VALID", "OVERHEAD_CLEAR",
    ]


# ===========================================================================
# 5 — compact dict missing_proofs (only concise fields)
# ===========================================================================

def test_missing_proofs_compact_dicts():
    row = _record(_tiering(audit=_audit(missing_proofs=[
        "plain string proof",
        {"gate": "HOLD_CONFIRMED", "name": "hold", "reason": "weak",
         "required_evidence": "closed hold", "source": "one_hour_entry",
         "nested_junk": {"deep": [1, 2, 3]}, "extra": "drop me"},
    ])))
    mp = row["snipe_gate_audit"]["missing_proofs"]
    assert mp[0] == "plain string proof"
    assert set(mp[1].keys()) == {"gate", "name", "reason", "required_evidence", "source"}
    assert "nested_junk" not in mp[1] and "extra" not in mp[1]


# ===========================================================================
# 6 — compact dict promotion_triggers (only concise fields)
# ===========================================================================

def test_promotion_triggers_compact_dicts():
    row = _record(_tiering(audit=_audit(promotion_triggers=[
        "1H closed hold above 102.00",
        {"gate": "OVERHEAD_CLEAR", "trigger": "clear overhead", "level": 110.0,
         "condition": "body close", "reason": "ceiling", "junk": [9]},
    ])))
    pt = row["snipe_gate_audit"]["promotion_triggers"]
    assert pt[0] == "1H closed hold above 102.00"
    assert set(pt[1].keys()) == {"gate", "trigger", "level", "condition", "reason"}
    assert "junk" not in pt[1]


# ===========================================================================
# 7 — dict blocking_reasons (reason > message > label > name > gate)
# ===========================================================================

def test_blocking_reasons_dict_extraction():
    row = _record(_tiering(audit=_audit(blocking_reasons=[
        {"reason": "r-wins"}, {"message": "m-wins"}, {"label": "l-wins"},
        {"name": "n-wins"}, {"gate": "g-wins"}, "plain reason",
    ])))
    assert row["snipe_gate_audit"]["blocking_reasons"] == [
        "r-wins", "m-wins", "l-wins", "n-wins", "g-wins", "plain reason",
    ]


# ===========================================================================
# 8 — missing audit is safe (key present, value None)
# ===========================================================================

def test_missing_audit_is_safe():
    row = _record(_tiering(audit=_OMIT))
    assert "snipe_gate_audit" in row
    assert row["snipe_gate_audit"] is None
    # Existing fields still persist.
    assert row["ticker"] == "HAE"
    assert row["tier"] == "STARTER"
    assert row["retest_status"] == "confirmed"


# ===========================================================================
# 9 — malformed audit is safe (degraded snapshot, no raise)
# ===========================================================================

def test_malformed_audit_is_safe():
    row = _record(_tiering(audit="bad"))
    snap = row["snipe_gate_audit"]
    assert snap["audit_label"] is None
    assert "snipe_gate_audit snapshot degraded: malformed source" in snap["blocking_reasons"]


# ===========================================================================
# 10 — malformed nested fields are safe
# ===========================================================================

def test_malformed_nested_fields_safe():
    row = _record(_tiering(audit=_audit(
        blocked_gates="bad", missing_proofs="bad",
        promotion_triggers=None, blocking_reasons=123,
    )))
    snap = row["snipe_gate_audit"]
    assert snap["blocked_gate_names"] == []
    assert snap["blocked_gates"] == []
    assert snap["missing_proofs"] == []
    assert snap["promotion_triggers"] == []
    assert snap["blocking_reasons"] == []
    # Scalar fields still extracted; existing row fields intact.
    assert snap["audit_label"] == "STARTER_ONLY_VALID"
    assert row["ticker"] == "HAE"


# ===========================================================================
# 11 — no full-object bloat
# ===========================================================================

def test_no_full_object_bloat():
    row = _record(_tiering())
    snap = row["snipe_gate_audit"]
    for forbidden in ("passed_gates", "evidence_sources", "invalidation", "risk",
                      "raw_gate_matrix", "gate_details", "debug", "full_audit",
                      "one_hour_entry", "timeframe_alignment", "trade_location",
                      "candle_evidence", "enabled", "status"):
        assert forbidden not in snap


# ===========================================================================
# 12 — existing alert_history fields preserved
# ===========================================================================

def test_existing_fields_preserved():
    row = _record(_tiering())
    for field in ("ticker", "tier", "alerted_at", "trigger_level", "invalidation_level",
                  "score", "reason", "dedup_key", "scan_id", "risk_reward",
                  "retest_status", "hold_status", "overhead_status", "structure_event",
                  "missing_conditions", "upgrade_trigger", "capital_action",
                  "final_discord_channel"):
        assert field in row


# ===========================================================================
# 13 — no mutation of tiering_result
# ===========================================================================

def test_no_mutation():
    tr = _tiering()
    before = copy.deepcopy(tr)
    state = {"tickers": {}, "meta": {}}
    record_alert("HAE", tr, state, _cfg(), "scan1")
    assert tr == before
    for k in ("final_tier", "capital_action", "final_discord_channel",
              "safe_for_alert", "score", "snipe_gate_audit", "final_signal"):
        assert tr.get(k) == before.get(k)


# ===========================================================================
# 14 — PROMOTION_READY persisted with integrity reason
# ===========================================================================

def test_promotion_ready_persisted():
    integrity = "SNIPE gates appear complete but final_tier is not SNIPE_IT."
    row = _record(_tiering(audit=_audit(
        promotion_state="PROMOTION_READY", blocking_reasons=[integrity],
    )))
    snap = row["snipe_gate_audit"]
    assert snap["promotion_state"] == "PROMOTION_READY"
    assert integrity in snap["blocking_reasons"]


# ===========================================================================
# 15 — SNIPE_IT blocked-gate detector
# ===========================================================================

def test_snipe_it_no_blocked_gates():
    row = _record(_tiering(final_tier="SNIPE_IT", audit=_audit(
        audit_label="SNIPE_CONFIRMED", promotion_state="ALREADY_SNIPE",
        blocked_gates=[],
    )))
    assert row["snipe_gate_audit"]["blocked_gate_names"] == []


# ===========================================================================
# 16 — business grading scenarios preserve enough to grade
# ===========================================================================

def test_business_grading_scenarios():
    # STARTER + PROMOTION_PENDING
    s1 = _record(_tiering())["snipe_gate_audit"]
    assert s1["audit_label"] == "STARTER_ONLY_VALID" and s1["promotion_state"] == "PROMOTION_PENDING"
    assert any("1H" in m or "hold" in m.lower() for m in s1["missing_proofs"])
    # NEAR_ENTRY + blocked gates
    s2 = _record(_tiering(final_tier="NEAR_ENTRY", audit=_audit(
        audit_label="WATCH_ONLY_BLOCKED", promotion_state="PROMOTION_BLOCKED",
        blocked_gates=[{"gate": "OVERHEAD_CLEAR", "status": "BLOCK", "reason": "blocked", "source": "final_signal"}],
    )))["snipe_gate_audit"]
    assert s2["blocked_gate_names"] == ["OVERHEAD_CLEAR"]
    # non-SNIPE + PROMOTION_READY
    s3 = _record(_tiering(audit=_audit(promotion_state="PROMOTION_READY")))["snipe_gate_audit"]
    assert s3["promotion_state"] == "PROMOTION_READY"
    # SNIPE_IT + blocked critical gate
    s4 = _record(_tiering(final_tier="SNIPE_IT", audit=_audit(
        audit_label="SNIPE_CONFIRMED", blocked_gates=[{"gate": "ASYMMETRY_VALID", "status": "BLOCK"}],
    )))["snipe_gate_audit"]
    assert s4["blocked_gate_names"] == ["ASYMMETRY_VALID"]


# ===========================================================================
# 17 — max_memory_entries trimming unchanged
# ===========================================================================

def test_trimming_unchanged():
    state = {"tickers": {}, "meta": {}}
    cfg = {"state": {"max_memory_entries": 3}}
    for _ in range(5):
        state = record_alert("HAE", _tiering(), state, cfg, "s")
    hist = state["tickers"]["HAE"]["alert_history"]
    assert len(hist) == 3
    # every retained row carries the snapshot
    assert all(r.get("snipe_gate_audit") is not None for r in hist)


# ===========================================================================
# 18 — backward compatibility / JSON-safe
# ===========================================================================

def test_snapshot_is_json_safe():
    row = _record(_tiering())
    # Round-trips through JSON with no custom encoder.
    dumped = json.dumps(row)
    assert "snipe_gate_audit" in dumped
    restored = json.loads(dumped)
    assert restored["snipe_gate_audit"]["audit_label"] == "STARTER_ONLY_VALID"


def test_old_record_without_snapshot_readable():
    # A pre-14H.1 row (no snipe_gate_audit key) is still a valid dict.
    old_row = {"ticker": "HAE", "tier": "STARTER", "score": 80}
    assert old_row.get("snipe_gate_audit") is None  # readable, no KeyError


# ===========================================================================
# 14H.1 HARDENING — strict JSON safety (json.dumps(row, allow_nan=False))
# ===========================================================================

def _unsafe_audit():
    """An audit object packed with JSON-unsafe garbage in every field."""
    return {
        "audit_label": {"bad": "object"},
        "promotion_state": object(),
        "snipe_score": "ninety-two",
        "snipe_grade": ["A"],
        "eligible_for_snipe_review": "yes",
        "blocked_gates": [{
            "gate": {"bad": "nested"},
            "status": set(["BLOCK"]),
            "reason": object(),
            "source": ["x"],
        }],
        "missing_proofs": [{
            "gate": {"bad": 1},
            "reason": object(),
            "required_evidence": set(["hold"]),
        }],
        "promotion_triggers": [{
            "gate": object(),
            "level": float("nan"),
            "condition": {"bad": 1},
        }],
        "blocking_reasons": [
            {"reason": object()},
            {"message": "valid message"},
        ],
        "diagnostic_sentence": object(),
    }


def test_strict_json_dumps_succeeds_on_unsafe_audit():
    tr = _tiering(audit=_unsafe_audit())
    row = _record(tr)            # must not raise
    # Strict serialization rejects NaN/Infinity — proves no unsafe number leaked.
    json.dumps(row, allow_nan=False)


def test_unsafe_scalars_become_none_or_skipped():
    snap = _record(_tiering(audit=_unsafe_audit()))["snipe_gate_audit"]
    assert snap["audit_label"] is None
    assert snap["promotion_state"] is None
    assert snap["snipe_score"] is None
    assert snap["snipe_grade"] is None
    assert snap["eligible_for_snipe_review"] is None
    assert snap["diagnostic_sentence"] is None
    # Unsafe gate-name extraction yields nothing.
    assert snap["blocked_gate_names"] == []
    # Valid neighbouring blocking reason preserved.
    assert snap["blocking_reasons"] == ["valid message"]


def test_no_nested_objects_in_compact_dicts():
    snap = _record(_tiering(audit=_unsafe_audit()))["snipe_gate_audit"]
    def _all_safe(entries):
        for e in entries:
            assert isinstance(e, (str, dict))
            if isinstance(e, dict):
                for v in e.values():
                    assert v is None or isinstance(v, (str, int, float))
                    assert not isinstance(v, bool)
    _all_safe(snap["blocked_gates"])
    _all_safe(snap["missing_proofs"])
    _all_safe(snap["promotion_triggers"])


def test_unsafe_audit_does_not_mutate_source():
    tr = _tiering(audit=_unsafe_audit())
    src_audit = tr["snipe_gate_audit"]
    snapshot_of_source = {
        "snipe_score": src_audit["snipe_score"],
        "eligible_for_snipe_review": src_audit["eligible_for_snipe_review"],
        "blocked_gates_len": len(src_audit["blocked_gates"]),
    }
    _record(tr)
    assert src_audit["snipe_score"] == "ninety-two"
    assert src_audit["eligible_for_snipe_review"] == "yes"
    assert snapshot_of_source["blocked_gates_len"] == len(src_audit["blocked_gates"])


# ---- targeted helper unit tests ------------------------------------------

def test_json_safe_number():
    assert ss._json_safe_number(92) == 92
    assert ss._json_safe_number(92.5) == 92.5
    assert ss._json_safe_number(True) is None
    assert ss._json_safe_number(False) is None
    assert ss._json_safe_number("92") is None
    assert ss._json_safe_number(float("nan")) is None
    assert ss._json_safe_number(float("inf")) is None
    assert ss._json_safe_number(float("-inf")) is None
    assert ss._json_safe_number({"x": 1}) is None
    assert ss._json_safe_number(None) is None


def test_json_safe_scalar():
    assert ss._json_safe_scalar("A") == "A"
    assert ss._json_safe_scalar(92) == "92"
    assert ss._json_safe_scalar(92.5) == "92.5"
    assert ss._json_safe_scalar(True) is None
    assert ss._json_safe_scalar({"bad": "object"}) is None
    assert ss._json_safe_scalar(["A"]) is None
    assert ss._json_safe_scalar(set(["x"])) is None
    assert ss._json_safe_scalar((1, 2)) is None
    assert ss._json_safe_scalar(object()) is None
    assert ss._json_safe_scalar(lambda: 1) is None
    assert ss._json_safe_scalar(float("nan")) is None
    assert ss._json_safe_scalar(float("inf")) is None
    assert ss._json_safe_scalar(None) is None


def test_json_safe_bool_or_none():
    assert ss._json_safe_bool_or_none(True) is True
    assert ss._json_safe_bool_or_none(False) is False
    assert ss._json_safe_bool_or_none("yes") is None
    assert ss._json_safe_bool_or_none(1) is None
    assert ss._json_safe_bool_or_none(0) is None
    assert ss._json_safe_bool_or_none({}) is None
    assert ss._json_safe_bool_or_none(object()) is None


def test_snipe_score_rejects_nan_inf_and_bool():
    for bad in (float("nan"), float("inf"), float("-inf"), True, "92", {"x": 1}):
        snap = _record(_tiering(audit=_audit(snipe_score=bad)))["snipe_gate_audit"]
        assert snap["snipe_score"] is None
    snap_ok = _record(_tiering(audit=_audit(snipe_score=92)))["snipe_gate_audit"]
    assert snap_ok["snipe_score"] == 92


def test_promotion_trigger_level_rejects_unsafe_keeps_numeric():
    # finite numeric level preserved
    snap = _record(_tiering(audit=_audit(promotion_triggers=[
        {"gate": "OH", "level": 110.5}])))["snipe_gate_audit"]
    assert snap["promotion_triggers"][0]["level"] == 110.5
    # NaN / nested level rejected
    snap2 = _record(_tiering(audit=_audit(promotion_triggers=[
        {"gate": "OH", "level": float("nan")},
        {"gate": "OH2", "level": {"bad": 1}}])))["snipe_gate_audit"]
    assert snap2["promotion_triggers"][0]["level"] is None
    assert snap2["promotion_triggers"][1]["level"] is None

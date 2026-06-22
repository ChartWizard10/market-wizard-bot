"""Phase 14L — AuditReady under-promotion radar tests.

!auditready scans recent alert_history rows for TRUE possible under-promotion:
a setup the SNIPE gate audit calls PROMOTION_READY with no blockers, no missing
proofs, no HTF contextual block, that the scanner did not promote to SNIPE_IT.
It reuses the Phase 14J read-only loader, the Phase 14J permission gate, and the
Phase 14K interpret() conclusion. It must be a radar, not noise: if it returns a
blocked setup, it failed.
"""

import json
from pathlib import Path

from src import audit_access


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ready_snap(**over):
    """A clean PROMOTION_READY snapshot (no blockers) — the true-candidate shape
    the Phase 14K seal produces for a genuinely ready, un-promoted setup."""
    snap = {
        "audit_label": "STARTER_ONLY_VALID",
        "promotion_state": "PROMOTION_READY",
        "snipe_score": 100,
        "raw_snipe_score": 100,
        "effective_snipe_score": 100,
        "score_blocked_by": [],
        "display_score_label": None,
        "snipe_grade": "A",
        "eligible_for_snipe_review": True,
        "blocked_gate_names": [],
        "blocked_gates": [],
        "missing_proofs": [],
        "promotion_triggers": ["avoid body close below invalidation 71.66"],
        "blocking_reasons": ["SNIPE gates appear complete but final_tier is not SNIPE_IT."],
        "diagnostic_sentence": (
            "SNIPE audit: starter valid, but SNIPE promotion waits for 1H "
            "closed-hold proof and cleaner full-size confirmation."
        ),
    }
    snap.update(over)
    return snap


def _htf_snap(blocks=False):
    return {
        "data_status": "OK",
        "monthly_bias_state": "BULLISH",
        "weekly_campaign_state": "HTF_CONTINUATION",
        "campaign_location_label": "AT_HTF_SUPPORT",
        "campaign_location_quality": "FUNCTIONAL",
        "context_grade": "B",
        "context_score": 74,
        "supports_long_setup": not blocks,
        "weakens_long_setup": False,
        "blocks_snipe_contextually": blocks,
        "promotion_support": [],
        "missing_htf_proof": [],
        "blocking_reasons": ["into HTF supply"] if blocks else [],
        "diagnostic_sentence": "HTF context: weekly continuation.",
    }


def _row(ticker, scan_id, tier="STARTER", alerted_at="2026-06-22T16:49:18",
         retest="confirmed", hold="confirmed", capital="starter_only",
         score=80, sga=None, htf=None, **extra):
    row = {
        "ticker": ticker,
        "tier": tier,
        "alerted_at": alerted_at,
        "scan_id": scan_id,
        "score": score,
        "capital_action": capital,
        "retest_status": retest,
        "hold_status": hold,
        "final_discord_channel": tier.lower(),
        "snipe_gate_audit": sga if sga is not None else _ready_snap(),
        "higher_timeframe_context": htf if htf is not None else _htf_snap(),
    }
    row.update(extra)
    return row


def _state(*rows):
    tickers = {}
    for r in rows:
        tickers.setdefault(r["ticker"], {"alert_history": []})["alert_history"].append(r)
    return {"tickers": tickers, "meta": {"total_alerts": len(rows)}}


def _cfg(tmp_path, state, **audit_over):
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    audit = {"enabled": True, "allowed_user_ids": [111],
             "allowed_channel_ids": [555], "max_rows": 3}
    audit.update(audit_over)
    return {"state": {"state_file": str(p)}, "audit_access": audit}


_AUTH = {"user_id": 111, "channel_id": 999}


# ---------------------------------------------------------------------------
# 1 — finds a true under-promotion row
# ---------------------------------------------------------------------------

def test_finds_true_under_promotion(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["ok"] is True
    assert res["match_count"] == 1
    text = "\n".join(res["messages"])
    assert "POSSIBLE UNDER-PROMOTION CANDIDATES" in text
    assert "HAE" in text
    assert "scan_20260622_164918_4fc48e" in text
    assert "!audit scan_20260622_164918_4fc48e" in text


def test_candidate_helper_true_for_clean_ready_row():
    ok, why = audit_access.is_auditready_candidate(_row("HAE", "scan_x"))
    assert ok is True
    assert any("PROMOTION_READY" in w for w in why)


# ---------------------------------------------------------------------------
# 2 — STARTER with PROMOTION_PENDING is not a candidate
# ---------------------------------------------------------------------------

def test_excludes_promotion_pending(tmp_path):
    row = _row("HAE", "scan_p",
               sga=_ready_snap(promotion_state="PROMOTION_PENDING",
                               blocked_gate_names=["ONE_H_TRIGGER_CONFIRMED"],
                               missing_proofs=["closed 1H hold above trigger"]))
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is False
    cfg = _cfg(tmp_path, _state(row))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["match_count"] == 0


# ---------------------------------------------------------------------------
# 3 — NEAR_ENTRY with missing 1H proof is not a candidate
# ---------------------------------------------------------------------------

def test_excludes_near_entry_missing_proof():
    row = _row("QLYS", "scan_n", tier="NEAR_ENTRY", retest="pending", hold="pending",
               capital="wait_no_capital",
               sga=_ready_snap(promotion_state="PROMOTION_PENDING",
                               eligible_for_snipe_review=False,
                               missing_proofs=["1H hold forming"]))
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is False


# ---------------------------------------------------------------------------
# 4 — historical INCONSISTENT_AUDIT_STATE row excluded
# ---------------------------------------------------------------------------

def test_excludes_inconsistent_audit_state(tmp_path):
    row = _row("HAE", "scan_inc",
               sga=_ready_snap(
                   promotion_state="PROMOTION_READY",
                   blocked_gate_names=["LIVE_EDGE_SAFE"],
                   blocked_gates=["LIVE_EDGE_SAFE"],
                   blocking_reasons=["LIVE_EDGE_SAFE: candle veto HOSTILE_WICK"],
               ))
    # The 14K interpreter labels this INCONSISTENT_AUDIT_STATE.
    assert audit_access.interpret(row)["label"] == "INCONSISTENT_AUDIT_STATE"
    ok, fails = audit_access.is_auditready_candidate(row)
    assert ok is False
    cfg = _cfg(tmp_path, _state(row))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["match_count"] == 0


# ---------------------------------------------------------------------------
# 5 — missing_proofs disqualifies
# ---------------------------------------------------------------------------

def test_excludes_missing_proofs():
    row = _row("HAE", "scan_mp",
               sga=_ready_snap(missing_proofs=["closed 1H hold above 75.00"]))
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is False


# ---------------------------------------------------------------------------
# 6 — blocked_gates disqualifies
# ---------------------------------------------------------------------------

def test_excludes_blocked_gates():
    row = _row("HAE", "scan_bg",
               sga=_ready_snap(blocked_gate_names=["OVERHEAD_CLEAR"],
                               blocked_gates=["OVERHEAD_CLEAR"]))
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is False


# ---------------------------------------------------------------------------
# 7 — HTF contextual block disqualifies
# ---------------------------------------------------------------------------

def test_excludes_htf_contextual_block():
    row = _row("HAE", "scan_htf", htf=_htf_snap(blocks=True))
    ok, fails = audit_access.is_auditready_candidate(row)
    assert ok is False
    assert any("HTF contextual block" in f for f in fails)


# ---------------------------------------------------------------------------
# 8 — SNIPE_IT rows are not candidates but ARE counted in summary
# ---------------------------------------------------------------------------

def test_snipe_it_not_candidate_but_counted(tmp_path):
    snipe_row = _row("WIN", "scan_snipe", tier="SNIPE_IT", capital="full_quality_allowed",
                     sga=_ready_snap(audit_label="SNIPE_CONFIRMED",
                                     promotion_state="ALREADY_SNIPE"))
    ok, _ = audit_access.is_auditready_candidate(snipe_row)
    assert ok is False
    cfg = _cfg(tmp_path, _state(snipe_row))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["match_count"] == 0
    text = "\n".join(res["messages"])
    assert "AUDITREADY — CLEAR" in text
    assert "SNIPE_CONFIRMED: 1" in text


# ---------------------------------------------------------------------------
# 9 — CLEAR message when no candidates
# ---------------------------------------------------------------------------

def test_clear_when_no_candidates(tmp_path):
    blocked = _row("HAE", "scan_b",
                   sga=_ready_snap(promotion_state="PROMOTION_BLOCKED",
                                   eligible_for_snipe_review=False,
                                   blocked_gate_names=["ONE_H_TRIGGER_CONFIRMED"],
                                   missing_proofs=["1H hold"]))
    cfg = _cfg(tmp_path, _state(blocked))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["ok"] is True
    assert res["match_count"] == 0
    text = "\n".join(res["messages"])
    assert "AUDITREADY — CLEAR" in text
    assert "POSSIBLE_UNDER_PROMOTION: 0" in text
    assert "No true under-promotion candidates found" in text


# ---------------------------------------------------------------------------
# 10 / 11 — permission gate
# ---------------------------------------------------------------------------

def test_permission_channel_allows(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_x")))
    res = audit_access.run_auditready(cfg, "", user_id=222, channel_id=555)
    assert res["ok"] is True


def test_permission_user_allows(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_x")))
    res = audit_access.run_auditready(cfg, "", user_id=111, channel_id=222)
    assert res["ok"] is True


def test_unauthorized_denied(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_x")))
    res = audit_access.run_auditready(cfg, "", user_id=222, channel_id=222)
    assert res["ok"] is False
    assert res["error"] == "unauthorized"
    assert "HAE" not in res["messages"][0]


def test_feature_off_denied(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_x")), enabled=False)
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["ok"] is False and res["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# 12 — missing state file -> friendly error
# ---------------------------------------------------------------------------

def test_missing_state_file_friendly_error(tmp_path):
    cfg = {"state": {"state_file": str(tmp_path / "nope.json")},
           "audit_access": {"enabled": True, "allowed_user_ids": [111]}}
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["ok"] is False
    assert res["error"] == "state_file_not_found"
    assert "AUDITREADY unavailable" in res["messages"][0]
    assert "state file not found" in res["messages"][0]


# ---------------------------------------------------------------------------
# 13 — malformed state file -> friendly error, no mutation
# ---------------------------------------------------------------------------

def test_malformed_state_file_friendly_error_no_mutation(tmp_path):
    p = tmp_path / "alert_history.json"
    p.write_text("{ not valid json ", encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    cfg = {"state": {"state_file": str(p)},
           "audit_access": {"enabled": True, "allowed_user_ids": [111]}}
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["ok"] is False and res["error"] == "state_file_malformed"
    assert "could not be parsed" in res["messages"][0]
    assert "No state was modified" in res["messages"][0]
    assert p.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.corrupt*"))


# ---------------------------------------------------------------------------
# 14 / 15 — numeric limit works and clamps
# ---------------------------------------------------------------------------

def test_numeric_limit_works(tmp_path):
    rows = [_row("T%d" % i, "scan_%05d" % i, alerted_at="2026-06-22T1%d:00:00" % (i % 9))
            for i in range(20)]
    cfg = _cfg(tmp_path, _state(*rows))
    res = audit_access.run_auditready(cfg, "12", **_AUTH)
    assert res["ok"] is True
    # rows scanned should reflect the limit (12), not all 20.
    assert "Rows scanned: 12" in "\n".join(res["messages"])


def test_numeric_limit_clamps_to_max(tmp_path):
    state = _state(_row("HAE", "scan_x"))
    cfg = _cfg(tmp_path, state)
    res = audit_access.run_auditready(cfg, "99999", **_AUTH)
    assert res["ok"] is True   # clamps to 300; no crash. (only 1 row present)
    # Below-range also clamps up to the 10 floor (no crash).
    res2 = audit_access.run_auditready(cfg, "1", **_AUTH)
    assert res2["ok"] is True


# ---------------------------------------------------------------------------
# 16 — invalid argument -> usage
# ---------------------------------------------------------------------------

def test_invalid_argument_usage(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_x")))
    res = audit_access.run_auditready(cfg, "garbage", **_AUTH)
    assert res["ok"] is False and res["error"] == "usage"
    assert "Usage:" in res["messages"][0]


# ---------------------------------------------------------------------------
# 17 — json mode returns sanitized candidate JSON only
# ---------------------------------------------------------------------------

def test_json_mode_sanitized_candidates(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    res = audit_access.run_auditready(cfg, "json", **_AUTH)
    assert res["ok"] is True
    assert isinstance(res["json"], list)
    body = "\n".join(res["messages"])
    assert body.strip().startswith("```json")
    inner = body.split("```json", 1)[1].rsplit("```", 1)[0]
    parsed = json.loads(inner)
    assert parsed["meta"]["candidates_found"] == 1
    assert parsed["candidates"][0]["ticker"] == "HAE"
    assert parsed["candidates"][0]["conclusion"] == "POSSIBLE_UNDER_PROMOTION"


# ---------------------------------------------------------------------------
# 18 — json mode does not leak secrets
# ---------------------------------------------------------------------------

def test_json_mode_no_secret_leak(tmp_path):
    row = _row("HAE", "scan_20260622_164918_4fc48e")
    row["secret_token"] = "DISCORD_TOKEN_abc123"
    row["api_key"] = "sk-ant-XYZ"
    row["password"] = "hunter2"
    cfg = _cfg(tmp_path, _state(row))

    res = audit_access.run_auditready(cfg, "json", **_AUTH)
    body = "\n".join(res["messages"])
    for secret in ("DISCORD_TOKEN_abc123", "sk-ant-XYZ", "hunter2",
                   "secret_token", "api_key", "password"):
        assert secret not in body
    payload = res["json"][0]
    for secret in ("secret_token", "api_key", "password"):
        assert secret not in payload

    # Text mode also clean.
    res_txt = audit_access.run_auditready(cfg, "", **_AUTH)
    txt = "\n".join(res_txt["messages"])
    for secret in ("DISCORD_TOKEN_abc123", "sk-ant-XYZ", "hunter2"):
        assert secret not in txt


# ---------------------------------------------------------------------------
# 19 — output chunking stays below Discord limit
# ---------------------------------------------------------------------------

def test_output_chunking_below_limit(tmp_path):
    rows = [_row("TK%02d" % i, "scan_cand_%05d" % i,
                 alerted_at="2026-06-22T%02d:00:00" % (i % 24))
            for i in range(40)]
    cfg = _cfg(tmp_path, _state(*rows), auditready_max_candidates=10)
    res = audit_access.run_auditready(cfg, "300", **_AUTH)
    assert res["ok"] is True
    assert all(len(m) <= audit_access._DISCORD_MAX_CHARS for m in res["messages"])


# ---------------------------------------------------------------------------
# 20 — sorting ranks higher effective score first, then newer
# ---------------------------------------------------------------------------

def test_sorting_by_effective_score_then_recency(tmp_path):
    low = _row("LOW", "scan_low", alerted_at="2026-06-22T18:00:00",
               sga=_ready_snap(effective_snipe_score=88, snipe_grade="A-"))
    high = _row("HIGH", "scan_high", alerted_at="2026-06-22T12:00:00",
                sga=_ready_snap(effective_snipe_score=100, snipe_grade="A"))
    mid_new = _row("MIDNEW", "scan_midnew", alerted_at="2026-06-22T20:00:00",
                   sga=_ready_snap(effective_snipe_score=100, snipe_grade="A"))
    cfg = _cfg(tmp_path, _state(low, high, mid_new))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    text = "\n".join(res["messages"])
    # Both 100-score rows precede the 88 row; the newer 100 precedes the older 100.
    i_midnew = text.index("MIDNEW")
    i_high = text.index("HIGH")
    i_low = text.index("LOW")
    assert i_midnew < i_high < i_low


# ---------------------------------------------------------------------------
# 21 — score_blocked_by disqualifies
# ---------------------------------------------------------------------------

def test_excludes_score_blocked_by():
    row = _row("HAE", "scan_sb",
               sga=_ready_snap(score_blocked_by=["LIVE_EDGE_SAFE"],
                               effective_snipe_score=79,
                               display_score_label="raw/pre-block"))
    ok, fails = audit_access.is_auditready_candidate(row)
    assert ok is False
    assert any("score blocked by" in f for f in fails)


# ---------------------------------------------------------------------------
# 22 — text blocker "candle veto HOSTILE_WICK" disqualifies (no structured flag)
# ---------------------------------------------------------------------------

def test_excludes_text_only_candle_veto():
    # Structured fields are all empty — only the blocking_reasons TEXT carries
    # the veto. interpret() alone would miss this; active_blockers must catch it.
    row = _row("HAE", "scan_tv",
               sga=_ready_snap(blocking_reasons=[
                   "SNIPE gates appear complete but final_tier is not SNIPE_IT.",
                   "candle veto HOSTILE_WICK",
               ]))
    assert audit_access.interpret(row)["label"] == "POSSIBLE_UNDER_PROMOTION"
    ok, fails = audit_access.is_auditready_candidate(row)
    assert ok is False
    assert any("candle veto" in f.lower() for f in fails)


# ---------------------------------------------------------------------------
# 23 — benign "avoid body close below invalidation" alone does NOT block
# ---------------------------------------------------------------------------

def test_benign_invalidation_trigger_not_a_blocker():
    row = _row("HAE", "scan_ok",
               sga=_ready_snap(promotion_triggers=["avoid body close below invalidation 71.66"]))
    # promotion_triggers are never scanned for blocker terms.
    assert audit_access.active_blockers(row) == []
    ok, _ = audit_access.is_auditready_candidate(row)
    assert ok is True


def test_integrity_note_alone_not_a_blocker():
    # The 14K integrity note is the only blocking_reason on a clean candidate.
    row = _row("HAE", "scan_ok2")
    assert audit_access.active_blockers(row) == []


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------

def test_read_only_never_mutates_state(tmp_path):
    state = _state(_row("HAE", "scan_x"), _row("QLYS", "scan_y", tier="NEAR_ENTRY"))
    cfg = _cfg(tmp_path, state)
    p = Path(cfg["state"]["state_file"])
    before_bytes = p.read_bytes()
    before_mtime = p.stat().st_mtime
    in_memory_before = json.dumps(state, sort_keys=True)

    audit_access.run_auditready(cfg, "", **_AUTH)
    audit_access.run_auditready(cfg, "json", **_AUTH)
    audit_access.collect_recent_rows(state, 100)

    assert p.read_bytes() == before_bytes
    assert p.stat().st_mtime == before_mtime
    assert json.dumps(state, sort_keys=True) == in_memory_before


def test_collect_recent_rows_fills_parent_ticker_without_mutation():
    # Row missing its own 'ticker' must inherit the parent key, without the
    # source row being mutated.
    bare = {"scan_id": "scan_bare", "tier": "STARTER",
            "alerted_at": "2026-06-22T10:00:00", "snipe_gate_audit": _ready_snap()}
    state = {"tickers": {"ZZZ": {"alert_history": [bare]}}, "meta": {}}
    rows = audit_access.collect_recent_rows(state, 10)
    assert rows[0]["ticker"] == "ZZZ"
    assert "ticker" not in bare         # source untouched


# ---------------------------------------------------------------------------
# Priority labeling
# ---------------------------------------------------------------------------

def test_near_entry_marked_high_priority(tmp_path):
    near = _row("QLYS", "scan_near", tier="NEAR_ENTRY", capital="wait_no_capital",
                sga=_ready_snap(audit_label="NEAR_ENTRY_PENDING"))
    cfg = _cfg(tmp_path, _state(near))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    assert res["match_count"] == 1
    text = "\n".join(res["messages"])
    assert "HIGH PRIORITY" in text


def test_starter_marked_priority(tmp_path):
    cfg = _cfg(tmp_path, _state(_row("HAE", "scan_st")))
    res = audit_access.run_auditready(cfg, "", **_AUTH)
    text = "\n".join(res["messages"])
    assert "PRIORITY" in text


# ---------------------------------------------------------------------------
# Conclusions / labels are within the closed sets
# ---------------------------------------------------------------------------

def test_max_candidates_capped(tmp_path):
    rows = [_row("TK%02d" % i, "scan_%05d" % i,
                 alerted_at="2026-06-22T%02d:00:00" % (i % 24)) for i in range(25)]
    cfg = _cfg(tmp_path, _state(*rows), auditready_max_candidates=10)
    res = audit_access.run_auditready(cfg, "300", **_AUTH)
    assert res["match_count"] == 10

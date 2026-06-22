"""Phase 14J — read-only operator audit-access command tests.

Covers scan_id/ticker lookup, latest-N, friendly errors (missing/malformed/no
match), snipe_gate_audit + higher_timeframe_context field surfacing, the
promotion-path conclusions (POSSIBLE_UNDER_PROMOTION / CORRECT_STARTER /
CORRECT_NEAR_ENTRY), strict read-only behavior (no state mutation, no corrupt
reset), the permission gate, secret non-exposure, and output-length control.
"""

import json
import os
from pathlib import Path

from src import audit_access


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _snipe_snap(promotion_state="BLOCKED", blocked=None, missing=None, label="SNIPE_BLOCKED"):
    return {
        "audit_label": label,
        "promotion_state": promotion_state,
        "snipe_score": 72,
        "snipe_grade": "B",
        "eligible_for_snipe_review": promotion_state == "PROMOTION_READY",
        "blocked_gate_names": blocked if blocked is not None else ["ONE_H_TRIGGER_CONFIRMED"],
        "blocked_gates": blocked if blocked is not None else ["ONE_H_TRIGGER_CONFIRMED"],
        "missing_proofs": missing if missing is not None else ["closed 1H hold above trigger"],
        "promotion_triggers": ["acceptance above 75.00"],
        "blocking_reasons": ["1H closed-hold not yet proven"],
        "diagnostic_sentence": "SNIPE blocked: 1H trigger not confirmed.",
    }


def _htf_snap(blocks=False, campaign="HTF_CONTINUATION", quality="FUNCTIONAL"):
    return {
        "data_status": "OK",
        "monthly_bias_state": "BULLISH",
        "weekly_campaign_state": campaign,
        "campaign_location_label": "AT_HTF_SUPPORT",
        "campaign_location_quality": quality,
        "context_grade": "B",
        "context_score": 74,
        "supports_long_setup": not blocks,
        "weakens_long_setup": False,
        "blocks_snipe_contextually": blocks,
        "promotion_support": ["weekly continuation from value"],
        "missing_htf_proof": [],
        "blocking_reasons": ["into HTF supply"] if blocks else [],
        "diagnostic_sentence": "HTF context: weekly continuation.",
    }


def _row(ticker, scan_id, tier="STARTER", alerted_at="2026-06-22T16:49:18",
         retest="confirmed", hold="confirmed", sga=None, htf=None, **extra):
    row = {
        "ticker": ticker,
        "tier": tier,
        "alerted_at": alerted_at,
        "trigger_level": 75.0,
        "invalidation_level": 73.5,
        "score": 80,
        "reason": "demand reclaim",
        "dedup_key": f"{ticker}|{tier}|75.00|73.50",
        "scan_id": scan_id,
        "capital_action": "starter_only",
        "retest_status": retest,
        "hold_status": hold,
        "final_discord_channel": "starter",
        "snipe_gate_audit": sga if sga is not None else _snipe_snap(),
        "higher_timeframe_context": htf if htf is not None else _htf_snap(),
    }
    row.update(extra)
    return row


def _state(*rows):
    tickers = {}
    for r in rows:
        tickers.setdefault(r["ticker"], {"alert_history": []})["alert_history"].append(r)
    return {"tickers": tickers, "meta": {"total_alerts": len(rows)}}


def _write_state(tmp_path, state) -> dict:
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {
        "state": {"state_file": str(p)},
        "audit_access": {"enabled": True, "allowed_user_ids": [111], "max_rows": 3},
    }


_AUTH = {"user_id": 111, "channel_id": 999}


# ---------------------------------------------------------------------------
# 1 — exact scan_id lookup
# ---------------------------------------------------------------------------

def test_exact_scan_id_lookup(tmp_path):
    state = _state(
        _row("HAE", "scan_20260622_164918_4fc48e", tier="STARTER"),
        _row("QLYS", "scan_20260622_163054_da043b", tier="NEAR_ENTRY"),
    )
    cfg = _write_state(tmp_path, state)
    res = audit_access.run_audit(cfg, "scan_20260622_164918_4fc48e", **_AUTH)
    assert res["ok"] is True
    assert res["match_count"] == 1
    assert "HAE" in res["messages"][0]
    assert "scan_20260622_164918_4fc48e" in res["messages"][0]


# ---------------------------------------------------------------------------
# 2 — ticker lookup returns latest row
# ---------------------------------------------------------------------------

def test_ticker_lookup_returns_latest(tmp_path):
    state = _state(
        _row("HAE", "scan_20260622_120000_aaa", alerted_at="2026-06-22T12:00:00"),
        _row("HAE", "scan_20260622_164918_4fc48e", alerted_at="2026-06-22T16:49:18"),
    )
    cfg = _write_state(tmp_path, state)
    res = audit_access.run_audit(cfg, "HAE", **_AUTH)
    assert res["ok"] is True
    # Latest (16:49) must lead.
    assert res["messages"][0].index("scan_20260622_164918_4fc48e") < (
        res["messages"][0].index("scan_20260622_120000_aaa")
        if "scan_20260622_120000_aaa" in res["messages"][0] else 10**9
    )
    rows = audit_access.find_by_ticker(state, "HAE", max_rows=1)
    assert rows[0]["scan_id"] == "scan_20260622_164918_4fc48e"


# ---------------------------------------------------------------------------
# 3 — ticker lookup can return latest 3 rows
# ---------------------------------------------------------------------------

def test_ticker_lookup_latest_three(tmp_path):
    rows = [
        _row("RS", f"scan_20260622_1{i:05d}_x", alerted_at=f"2026-06-22T1{i}:00:00")
        for i in range(5)
    ]
    state = _state(*rows)
    found = audit_access.find_by_ticker(state, "RS", max_rows=3)
    assert len(found) == 3
    # Newest first.
    assert found[0]["alerted_at"] > found[1]["alerted_at"] > found[2]["alerted_at"]


# ---------------------------------------------------------------------------
# 4 — missing state file -> friendly error
# ---------------------------------------------------------------------------

def test_missing_state_file_friendly_error(tmp_path):
    cfg = {
        "state": {"state_file": str(tmp_path / "does_not_exist.json")},
        "audit_access": {"enabled": True, "allowed_user_ids": [111]},
    }
    res = audit_access.run_audit(cfg, "HAE", **_AUTH)
    assert res["ok"] is False
    assert res["error"] == "state_file_not_found"
    assert "No alert_history state file" in res["messages"][0]


# ---------------------------------------------------------------------------
# 5 — malformed state file -> friendly error (and NOT reset)
# ---------------------------------------------------------------------------

def test_malformed_state_file_friendly_error_and_not_reset(tmp_path):
    p = tmp_path / "alert_history.json"
    p.write_text("{ this is not valid json ", encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    cfg = {
        "state": {"state_file": str(p)},
        "audit_access": {"enabled": True, "allowed_user_ids": [111]},
    }
    res = audit_access.run_audit(cfg, "HAE", **_AUTH)
    assert res["ok"] is False
    assert res["error"] == "state_file_malformed"
    # Read-only: corrupt file is left exactly as-is (unlike state_store.load).
    assert p.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.corrupt*"))


# ---------------------------------------------------------------------------
# 6 — no match -> friendly error
# ---------------------------------------------------------------------------

def test_no_match_friendly_error(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    res_scan = audit_access.run_audit(cfg, "scan_20260622_000000_zzz", **_AUTH)
    assert res_scan["ok"] is False and res_scan["error"] == "not_found"
    res_tkr = audit_access.run_audit(cfg, "ZZZZ", **_AUTH)
    assert res_tkr["ok"] is False and res_tkr["error"] == "not_found"


# ---------------------------------------------------------------------------
# 7 — output includes snipe_gate_audit compact fields
# ---------------------------------------------------------------------------

def test_output_includes_snipe_gate_audit_fields(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    text = "\n".join(audit_access.run_audit(cfg, "HAE", **_AUTH)["messages"])
    for label in ("SNIPE GATE AUDIT", "Audit label", "Promotion state", "SNIPE score",
                  "SNIPE grade", "Eligible for SNIPE review", "Blocked gates",
                  "Missing proofs", "Promotion triggers", "Blocking reasons", "Diagnostic"):
        assert label in text


# ---------------------------------------------------------------------------
# 8 — output includes higher_timeframe_context compact fields
# ---------------------------------------------------------------------------

def test_output_includes_htf_fields(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    text = "\n".join(audit_access.run_audit(cfg, "HAE", **_AUTH)["messages"])
    for label in ("HIGHER TIMEFRAME CONTEXT", "Data status", "Monthly bias",
                  "Weekly campaign", "Campaign location", "Location quality",
                  "Context grade / score", "Supports long", "Weakens long",
                  "Blocks SNIPE contextually", "Promotion support", "Missing HTF proof"):
        assert label in text


# ---------------------------------------------------------------------------
# 9 — PROMOTION_READY + non-SNIPE -> POSSIBLE_UNDER_PROMOTION
# ---------------------------------------------------------------------------

def test_promotion_ready_non_snipe_under_promotion(tmp_path):
    row = _row(
        "HAE", "scan_20260622_164918_4fc48e", tier="STARTER",
        sga=_snipe_snap(promotion_state="PROMOTION_READY", blocked=[], missing=[], label="PROMOTION_READY"),
    )
    assert audit_access.interpret(row)["label"] == "POSSIBLE_UNDER_PROMOTION"
    cfg = _write_state(tmp_path, _state(row))
    text = "\n".join(audit_access.run_audit(cfg, "HAE", **_AUTH)["messages"])
    assert "POSSIBLE_UNDER_PROMOTION" in text


# ---------------------------------------------------------------------------
# 10 — STARTER with blockers -> CORRECT_STARTER
# ---------------------------------------------------------------------------

def test_starter_with_blockers_correct_starter():
    row = _row(
        "HAE", "scan_x", tier="STARTER",
        sga=_snipe_snap(promotion_state="BLOCKED",
                        blocked=["ONE_H_TRIGGER_CONFIRMED"],
                        missing=["closed 1H hold above 75.00"]),
    )
    assert audit_access.interpret(row)["label"] == "CORRECT_STARTER"


# ---------------------------------------------------------------------------
# 11 — NEAR_ENTRY with incomplete 1H -> CORRECT_NEAR_ENTRY
# ---------------------------------------------------------------------------

def test_near_entry_incomplete_1h_correct_near_entry():
    row = _row(
        "QLYS", "scan_y", tier="NEAR_ENTRY", retest="pending", hold="pending",
        sga=_snipe_snap(promotion_state="BLOCKED", blocked=[], missing=[]),
    )
    assert audit_access.interpret(row)["label"] == "CORRECT_NEAR_ENTRY"


# ---------------------------------------------------------------------------
# 12 — read-only: never mutates state
# ---------------------------------------------------------------------------

def test_read_only_never_mutates_state(tmp_path):
    state = _state(_row("HAE", "scan_20260622_164918_4fc48e"))
    cfg = _write_state(tmp_path, state)
    p = Path(cfg["state"]["state_file"])
    before_bytes = p.read_bytes()
    before_mtime = p.stat().st_mtime
    in_memory_before = json.dumps(state, sort_keys=True)

    audit_access.run_audit(cfg, "HAE", **_AUTH)
    audit_access.run_audit(cfg, "scan_20260622_164918_4fc48e json", **_AUTH)

    assert p.read_bytes() == before_bytes
    assert p.stat().st_mtime == before_mtime
    # In-memory state passed to pure helpers is not mutated either.
    audit_access.find_by_ticker(state, "HAE")
    audit_access.find_by_scan_id(state, "scan_20260622_164918_4fc48e")
    audit_access.interpret(state["tickers"]["HAE"]["alert_history"][0])
    assert json.dumps(state, sort_keys=True) == in_memory_before


# ---------------------------------------------------------------------------
# 13 — permission gate
# ---------------------------------------------------------------------------

def test_permission_gate_blocks_unauthorized(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    # Wrong user, wrong channel.
    res = audit_access.run_audit(cfg, "HAE", user_id=222, channel_id=222)
    assert res["ok"] is False and res["error"] == "unauthorized"
    assert "HAE" not in res["messages"][0]   # no data leaked


def test_permission_disabled_by_default_when_no_ids(tmp_path):
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(_state(_row("HAE", "scan_x"))), encoding="utf-8")
    cfg = {"state": {"state_file": str(p)},
           "audit_access": {"enabled": True, "allowed_user_ids": [], "allowed_channel_ids": []}}
    res = audit_access.run_audit(cfg, "HAE", user_id=111, channel_id=999)
    assert res["ok"] is False and res["error"] == "unauthorized"


def test_permission_feature_off(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_x")))
    cfg["audit_access"]["enabled"] = False
    res = audit_access.run_audit(cfg, "HAE", **_AUTH)
    assert res["ok"] is False and res["error"] == "unauthorized"


def test_permission_channel_allows(tmp_path):
    p = tmp_path / "alert_history.json"
    p.write_text(json.dumps(_state(_row("HAE", "scan_x"))), encoding="utf-8")
    cfg = {"state": {"state_file": str(p)},
           "audit_access": {"enabled": True, "allowed_user_ids": [], "allowed_channel_ids": [555]}}
    res = audit_access.run_audit(cfg, "HAE", user_id=222, channel_id=555)
    assert res["ok"] is True


# ---------------------------------------------------------------------------
# 14 — no secrets/tokens exposed
# ---------------------------------------------------------------------------

def test_no_secrets_exposed(tmp_path):
    row = _row("HAE", "scan_20260622_164918_4fc48e")
    # Inject hostile fields that must never surface in audit output.
    row["secret_token"] = "DISCORD_TOKEN_abc123"
    row["api_key"] = "sk-ant-XYZ"
    cfg = _write_state(tmp_path, _state(row))

    text = "\n".join(audit_access.run_audit(cfg, "HAE", **_AUTH)["messages"])
    assert "DISCORD_TOKEN_abc123" not in text
    assert "sk-ant-XYZ" not in text
    assert "secret_token" not in text and "api_key" not in text

    jres = audit_access.run_audit(cfg, "HAE json", **_AUTH)
    jtext = "\n".join(jres["messages"])
    assert "DISCORD_TOKEN_abc123" not in jtext and "sk-ant-XYZ" not in jtext
    # Whitelisted JSON only.
    payload = jres["json"][0]
    assert "secret_token" not in payload and "api_key" not in payload


# ---------------------------------------------------------------------------
# 15 — output length controlled
# ---------------------------------------------------------------------------

def test_output_length_controlled(tmp_path):
    huge = ["blocking reason number %d %s" % (i, "x" * 80) for i in range(200)]
    sga = _snipe_snap()
    sga["blocking_reasons"] = huge
    sga["missing_proofs"] = huge
    row = _row("HAE", "scan_20260622_164918_4fc48e", sga=sga)
    cfg = _write_state(tmp_path, _state(row))
    res = audit_access.run_audit(cfg, "HAE", **_AUTH)
    assert res["ok"] is True
    assert all(len(m) <= audit_access._DISCORD_MAX_CHARS for m in res["messages"])
    assert len(res["messages"]) >= 1


# ---------------------------------------------------------------------------
# Extra — query parsing + json mode + too-many
# ---------------------------------------------------------------------------

def test_parse_query_classification():
    assert audit_access.parse_query("scan_20260622_164918_4fc48e")[0] == "scan_id"
    assert audit_access.parse_query("HAE") == ("ticker", "HAE")
    assert audit_access.parse_query("hae") == ("ticker", "HAE")
    assert audit_access.parse_query("")[0] == "invalid"
    assert audit_access.parse_query("!!!")[0] == "invalid"


def test_json_mode_returns_sanitized_json(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_20260622_164918_4fc48e")))
    res = audit_access.run_audit(cfg, "scan_20260622_164918_4fc48e json", **_AUTH)
    assert res["ok"] is True and isinstance(res["json"], list)
    # Valid JSON inside the code fence.
    body = "\n".join(res["messages"])
    assert body.strip().startswith("```json")
    inner = body.split("```json", 1)[1].rsplit("```", 1)[0]
    parsed = json.loads(inner)
    assert parsed[0]["ticker"] == "HAE"
    assert parsed[0]["conclusion"] in audit_access.CONCLUSIONS


def test_htf_contextual_block_noted():
    row = _row("HAE", "scan_x", tier="STARTER",
               htf=_htf_snap(blocks=True),
               sga=_snipe_snap(blocked=["HTF_CONTEXT_SUPPORTIVE"], missing=["acceptance through HTF supply"]))
    verdict = audit_access.interpret(row)
    assert any("HTF contextual block" in n for n in verdict["notes"])


def test_usage_when_no_args(tmp_path):
    cfg = _write_state(tmp_path, _state(_row("HAE", "scan_x")))
    res = audit_access.run_audit(cfg, "", **_AUTH)
    assert res["ok"] is False and res["error"] == "usage"

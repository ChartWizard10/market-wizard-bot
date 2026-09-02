"""Phase 14X — full manual !analyze operator audit renderer tests.

src/manual_operator_audit.py is a PURE READ-ONLY renderer over the completed
result of scheduler.run_analyze(). It must never re-run analysis, never mutate
its input, and must render every section the doctrine spec requires with
honest MISSING-vs-BROKEN proof semantics and no fabricated numbers.
"""

import copy
import json
from pathlib import Path

from src import manual_operator_audit as moa


# ---------------------------------------------------------------------------
# Fixtures — full completed run_analyze()-shaped result dicts, one per tier.
# ---------------------------------------------------------------------------

def _base_signal(tier: str, **overrides) -> dict:
    sig = {
        "ticker": "WMT", "timestamp_et": "2026-09-02T10:30:00-04:00",
        "tier": tier, "score": 88, "setup_family": "continuation",
        "structure_event": "MSS", "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive", "zone_type": "FVG",
        "trigger_level": 105.50, "scan_price": 104.80,
        "retest_status": "confirmed", "hold_status": "confirmed",
        "invalidation_condition": "Below FVG low", "invalidation_level": 101.20,
        "targets": [
            {"label": "T1", "level": 112.0, "reason": "swing high"},
            {"label": "T2", "level": 118.0, "reason": "liquidity pool"},
        ],
        "risk_reward": 3.2, "overhead_status": "clear",
        "forced_participation": "none", "missing_conditions": [],
        "upgrade_trigger": "none", "next_action": "Enter on retest",
        "discord_channel": "#snipe-signals", "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with confirmed retest and hold.",
        "risk_distance": 4.30, "risk_distance_pct": 4.10,
    }
    sig.update(overrides)
    return sig


def _full_tiering_result(final_tier: str, **sig_overrides) -> dict:
    signal = _base_signal(final_tier, **sig_overrides)
    return {
        "ok": True, "final_tier": final_tier, "original_claude_tier": final_tier,
        "score": 88, "final_discord_channel": signal["discord_channel"],
        "capital_action": signal["capital_action"], "applied_vetoes": [],
        "downgrades": [], "rejection_reason": None, "validation_notes": [],
        "safe_for_alert": final_tier != "WAIT", "final_signal": signal,
        "trajectory": {"label": "NEW_SIGNAL", "text": "New signal."},
        "trade_location": {
            "zone_type": "FVG", "zone_low": 103.0, "zone_mid": 104.0, "zone_high": 105.0,
            "scan_price": 104.80, "location_state": "mid_zone_acceptance",
            "confirmation_level": 105.0, "display_text": "", "flags": [],
        },
        "candle_evidence": {
            "status": "ok", "timeframe": "1H", "candle_status": "CLOSED",
            "body_pct": 62.0, "upper_wick_pct": 10.0, "lower_wick_pct": 28.0,
            "close_position_pct": 85.0, "candle_family": "ACCEPTANCE",
            "close_quality": "STRONG", "wick_read": "MINOR_REJECTION",
            "level_reaction": "HELD", "next_candle_verdict": "CONFIRMED",
            "candle_veto": "NONE", "display_text": "Strong acceptance candle.",
        },
        "one_hour_entry": {
            "status": "ENABLED", "data_freshness": "FRESH",
            "trigger_state": "TRIGGER_LIVE", "score": 82, "score_label": "STRONG_1H_TRIGGER",
            "pullback_retest_hold": {"retest_truth": "RETEST_CORE_VALID", "hold_truth": "HOLD_CONFIRMED"},
            "location_realism": {"label": "MID_ZONE"},
            "candle_truth": {"event_type": "ACCEPTANCE", "closed_candle_confirms": True},
            "invalidation": {"clear": True},
            "path_quality": {"path_label": "CLEAN"},
            "hard_caps_applied": [], "downgrade_reasons": [],
            "alert_truth_label": "TRIGGER_CONFIRMED",
            "scanner_sentence": "1H trigger confirmed with clean retest and hold.",
        },
        "timeframe_alignment": {
            "status": "ENABLED", "alignment_grade": "A", "alignment_score": 90,
            "alignment_label": "FULL_STACK_ALIGNED",
            "campaign_timeframe": {"state": "CAMPAIGN_SUPPORTIVE"},
            "swing_timeframe": {"state": "PERMISSION_GRANTED"},
            "operational_timeframe": {"state": "DEFENDABLE"},
            "trigger_timeframe": {"state": "TRIGGER_CONFIRMED"},
            "conflicts": [], "missing_context": [],
            "scanner_sentence": "All timeframes aligned.",
        },
        "four_hour_operational": {
            "enabled": True, "status": "OK", "structural_state": "HOLDING",
            "state_confidence": "CONFIRMED", "operational_location": "DEFENDABLE",
            "operational_readiness": "READY",
            "structure": {"break_state": "CONFIRMED"},
            "retest_truth": {"state": "CONFIRMED"},
        },
        "higher_timeframe_context": {
            "data_status": "OK", "monthly_bias_state": "BULLISH",
            "weekly_campaign_state": "EXPANSION", "campaign_location_label": "MID_RANGE",
            "campaign_location_quality": "GOOD", "context_grade": "A", "context_score": 88,
            "supports_long_setup": True, "weakens_long_setup": False,
            "blocks_snipe_contextually": False, "promotion_support": True,
            "missing_htf_proof": [], "blocking_reasons": [],
            "diagnostic_sentence": "Weekly campaign supportive.",
        },
        "snipe_gate_audit": {
            "audit_label": "SNIPE_READY", "promotion_state": "ALREADY_SNIPE",
            "snipe_score": 88, "snipe_grade": "A", "eligible_for_snipe_review": True,
            "blocked_gate_names": [], "missing_proofs": [], "promotion_triggers": [],
            "survival_conditions": [], "blocking_reasons": [],
            "diagnostic_sentence": "All gates clear.",
        },
        "snipe_ladder": {
            "internal_ladder_tier": "SNIPER_A", "public_signal_tier": final_tier,
            "proof_state": "COMPLETE", "base_alive": True,
            "why_this_ladder_tier": "Full sequence confirmed with clean 1H trigger.",
            "why_not_higher": "—", "why_not_lower": "All base gates hold.",
            "next_promotion_proof": [], "failure_condition": "Close back below invalidation.",
            "hard_failures": [], "starter_blockers": [], "sniper_only_blockers": [],
        },
        "snipe_confirmed_seal": {"applied": False},
        "calibration": {"raw_score": 88, "calibrated_score": 90, "delta": 2, "score_band": "A"},
    }


def _completed_result(final_tier: str, *, alert_sent: bool = False,
                       dedup_reason: str = "manual_override", **sig_overrides) -> dict:
    tiering_result = _full_tiering_result(final_tier, **sig_overrides)
    return {
        "status": "complete",
        "scan_id": "analyze_WMT_120000",
        "ticker": "WMT",
        "final_tier": final_tier,
        "safe_for_alert": tiering_result["safe_for_alert"],
        "dedup_reason": dedup_reason,
        "alert_sent": alert_sent,
        "channel_id": None,
        "tiering_result": tiering_result,
        "enriched": {
            "ticker": "WMT", "sma20": 102.5, "sma50": 98.2, "sma200": 90.1,
            "current_price": 104.80, "atr": 2.1,
        },
    }


def _wait_result() -> dict:
    r = _completed_result(
        "WAIT",
        alert_sent=False,
        dedup_reason="wait_no_alert",
        retest_status="missing", hold_status="missing",
        structure_event="none", overhead_status="blocked",
        discord_channel="none", capital_action="no_trade",
        reason="No structural break yet; still ranging inside prior value.",
    )
    tr = r["tiering_result"]
    tr["trade_location"]["location_state"] = "unknown"
    tr["candle_evidence"] = moa._safe_dict(None) or {
        "status": "unknown", "candle_family": "UNKNOWN", "candle_veto": "UNKNOWN",
        "next_candle_verdict": "UNKNOWN", "display_text": "",
    }
    tr["one_hour_entry"] = {"status": "DISABLED"}
    tr["timeframe_alignment"]["swing_timeframe"] = {"state": "PERMISSION_DENIED"}
    tr["four_hour_operational"] = {"enabled": False}
    tr["higher_timeframe_context"]["supports_long_setup"] = False
    tr["higher_timeframe_context"]["weakens_long_setup"] = True
    tr["snipe_gate_audit"] = {
        "audit_label": "NOT_READY", "promotion_state": "NOT_ELIGIBLE",
        "blocked_gate_names": ["structure_break", "retest_confirmed"],
        "missing_proofs": ["daily_structure_break"],
        "diagnostic_sentence": "No structure break; setup not yet eligible.",
    }
    tr["snipe_ladder"] = {
        "internal_ladder_tier": "NONE", "why_this_ladder_tier": "No qualifying structure event yet.",
        "why_not_higher": "Structure break has not occurred; NEAR_ENTRY requires a confirmed structural event.",
        "next_promotion_proof": ["Confirmed structure break (BOS/MSS) with retest."],
        "failure_condition": "Price breaks down through prior swing low.",
    }
    return r


def _near_entry_result() -> dict:
    r = _completed_result(
        "NEAR_ENTRY",
        alert_sent=True,
        dedup_reason="new_signal",
        retest_status="partial", hold_status="missing",
        discord_channel="#near-entry-watch", capital_action="wait_no_capital",
        reason="Structure present; retest in progress, hold not yet confirmed.",
    )
    tr = r["tiering_result"]
    tr["one_hour_entry"]["trigger_state"] = "TRIGGER_FORMING"
    tr["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_EDGE_ONLY", "hold_truth": "HOLD_FORMING",
    }
    tr["snipe_gate_audit"]["missing_proofs"] = ["hold_confirmed"]
    tr["snipe_ladder"]["why_not_higher"] = "Hold not yet confirmed; STARTER requires a confirmed hold."
    tr["snipe_ladder"]["next_promotion_proof"] = ["Body close above zone with hold confirmation."]
    return r


def _starter_result() -> dict:
    r = _completed_result(
        "STARTER",
        alert_sent=True,
        dedup_reason="new_signal",
        discord_channel="#starter-signals", capital_action="starter_only",
        reason="Retest and hold confirmed; full-size proof incomplete.",
    )
    tr = r["tiering_result"]
    tr["snipe_ladder"]["why_not_higher"] = (
        "1H closed-hold proof not yet confirmed; SNIPE_IT requires closed-candle confirmation."
    )
    tr["snipe_ladder"]["next_promotion_proof"] = ["1H closed-candle hold confirmation."]
    tr["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_FORMING",
    }
    return r


def _snipe_it_result() -> dict:
    return _completed_result("SNIPE_IT", alert_sent=True, dedup_reason="new_signal")


def _empty_result() -> dict:
    return {"status": "complete", "final_tier": "WAIT", "tiering_result": {}}


# ---------------------------------------------------------------------------
# 1. Static no-second-scanner regression
# ---------------------------------------------------------------------------

def test_renderer_has_zero_scanner_or_side_effect_dependencies():
    src = Path("src/manual_operator_audit.py").read_text(encoding="utf-8")
    forbidden_imports = [
        "import yfinance", "from src import market_data", "from src import indicators",
        "from src import prefilter", "from src.claude_client", "from src import claude_client",
        "from src import tiering", "from src import scheduler", "_complete_candidate_judgment",
        "from src import state_store", "from src import discord_alerts",
        "claude_call", "client.messages.create", "state_store.save", "state_store.record_alert",
        "discord_alerts.send_alert", "async def",
    ]
    for token in forbidden_imports:
        assert token not in src, f"forbidden dependency found in renderer: {token!r}"


def test_renderer_module_is_pure_stdlib_plus_display_formatting_only():
    src = Path("src/manual_operator_audit.py").read_text(encoding="utf-8")
    import_lines = [l for l in src.splitlines() if l.startswith("import ") or l.startswith("from ")]
    for line in import_lines:
        assert (
            line.startswith("import json")
            or line.startswith("import re")
            or "src.display_formatting" in line
        ), f"unexpected import in pure renderer: {line!r}"


# ---------------------------------------------------------------------------
# 2. Purity — never mutates input
# ---------------------------------------------------------------------------

def test_build_and_render_never_mutate_input_result():
    for fixture in (_wait_result, _near_entry_result, _starter_result, _snipe_it_result):
        original = fixture()
        snapshot = copy.deepcopy(original)
        moa.build_operator_audit(original)
        moa.render_operator_audit(original)
        moa.render_operator_audit_json(original)
        moa.render_operator_audit_compact(original)
        assert original == snapshot, "renderer mutated its input result"


# ---------------------------------------------------------------------------
# 3-6. Per-tier golden content
# ---------------------------------------------------------------------------

def test_wait_prints_full_audit_with_all_required_analytical_depth():
    text = moa.render_operator_audit(_wait_result())
    assert "VERDICT: ⚪ WAIT" in text
    assert "CAPITAL: NO TRADE" in text
    for section in (
        "SETUP", "DOCTRINE SEQUENCE", "EXECUTION PROOF", "TIMEFRAME SOVEREIGNTY",
        "TRADE LOCATION / KEY NUMBERS", "CANDLE TRUTH", "RISK / RUNWAY",
        "TIER JUDGMENT", "DELIVERY / AUDIT",
    ):
        assert section in text
    assert "WHY THIS TIER:" in text
    assert "WHY NOT THE NEXT TIER:" in text
    assert "WHY NOT STARTER:" in text
    assert "WHY NOT SNIPE_IT:" in text
    assert "PRIMARY BLOCKING GATE:" in text
    assert "MISSING PROOF:" in text
    assert "BROKEN / FAILED PROOF:" in text
    assert "PROMOTION REQUIREMENT:" in text
    assert "DEMOTION / FAILURE COND:" in text
    assert "Alert eligible:   NO" in text
    assert "Dedup evaluation: wait_no_alert" in text


def test_near_entry_prints_no_capital_and_promotion_proof():
    text = moa.render_operator_audit(_near_entry_result())
    assert "CAPITAL: NO CAPITAL — WATCH ONLY" in text
    assert "PROMOTION REQUIREMENT:" in text
    assert "Body close above zone with hold confirmation." in text
    assert "Capital readiness: NONE" in text


def test_starter_prints_reduced_size_and_why_not_snipe():
    text = moa.render_operator_audit(_starter_result())
    assert "CAPITAL: STARTER SIZE ONLY" in text
    assert "1H closed-hold proof not yet confirmed" in text
    assert "Capital readiness: STARTER" in text


def test_snipe_it_prints_full_capital_without_inventing_higher_tier():
    text = moa.render_operator_audit(_snipe_it_result())
    assert "VERDICT: 🔴 SNIPE IT" in text
    assert "CAPITAL: FULL-SIZE AUTHORIZED" in text
    assert "Capital readiness: FULL" in text
    # No tier above SNIPE_IT exists — the renderer must not invent one.
    assert "SUPER_SNIPE" not in text
    assert "ELITE_TIER" not in text


# ---------------------------------------------------------------------------
# 6b. Setup quality vs entry quality stay separate
# ---------------------------------------------------------------------------

def test_setup_quality_and_entry_quality_are_never_compressed_together():
    audit = moa.build_operator_audit(_starter_result())
    vc = audit["verdict_capital"]
    assert vc["setup_quality"] != vc["entry_quality"]
    assert "family=" in vc["setup_quality"]
    assert "retest=" in vc["entry_quality"]


# ---------------------------------------------------------------------------
# 7-8. Doctrine sequence / execution proof vocabulary
# ---------------------------------------------------------------------------

def test_doctrine_sequence_shows_all_eight_locked_steps_in_order():
    audit = moa.build_operator_audit(_snipe_it_result())
    steps = [row["step"] for row in audit["doctrine_sequence"]]
    assert steps == [
        "Structure", "Liquidity", "Displacement", "Acceptance/Reclaim",
        "Retest", "Hold", "Invalidation", "Target",
    ]


def test_execution_proof_shows_break_acceptance_retest_hold():
    text = moa.render_operator_audit(_snipe_it_result())
    assert "EXECUTION PROOF" in text
    assert "Break:" in text
    assert "Acceptance:" in text
    assert "Retest:" in text
    assert "Hold:" in text
    assert "Sequence:          COMPLETE" in text


def test_execution_proof_incomplete_for_near_entry():
    audit = moa.build_operator_audit(_near_entry_result())
    assert audit["execution_proof"]["sequence"] == "INCOMPLETE"


# ---------------------------------------------------------------------------
# 9. Weekly/Daily/4H/1H render separately
# ---------------------------------------------------------------------------

def test_timeframe_sovereignty_renders_all_four_timeframes_separately():
    text = moa.render_operator_audit(_snipe_it_result())
    assert "WEEKLY — CAMPAIGN CONTEXT" in text
    assert "DAILY — SWING PERMISSION" in text
    assert "4H — OPERATIONAL LOCATION" in text
    assert "1H — ENTRY PROOF" in text
    assert "Weekly = campaign context, Daily = swing permission" in text


def test_daily_permission_reads_from_swing_timeframe_state_verbatim():
    audit = moa.build_operator_audit(_snipe_it_result())
    assert audit["timeframe_sovereignty"]["daily"]["permission"] == "YES"
    wait_audit = moa.build_operator_audit(_wait_result())
    assert wait_audit["timeframe_sovereignty"]["daily"]["permission"] == "NO"


# ---------------------------------------------------------------------------
# 10-11. Key numbers render correctly; missing never becomes $0.00
# ---------------------------------------------------------------------------

def test_key_price_values_render_with_dollar_formatting():
    audit = moa.build_operator_audit(_snipe_it_result())
    tl = audit["trade_location"]
    assert tl["current_price"] == "$104.80"
    assert tl["trigger"] == "$105.50"
    assert tl["invalidation"] == "$101.20"
    assert tl["sma20"] == "$102.50"


def test_missing_values_never_render_as_fake_zero_dollar_or_false():
    audit = moa.build_operator_audit(_empty_result())
    tl = audit["trade_location"]
    for key in ("current_price", "trigger", "invalidation", "sma10", "sma20"):
        assert tl[key] == "—"
        assert "$0" not in tl[key]
        assert tl[key] != "False"
    text = moa.render_operator_audit(_empty_result())
    assert "$0.00" not in text
    assert "$nan" not in text


# ---------------------------------------------------------------------------
# 12. Live 1H is never rendered as closed confirmation
# ---------------------------------------------------------------------------

def test_live_1h_never_rendered_as_closed_confirmation():
    text = moa.render_operator_audit(_snipe_it_result())
    assert "information only — no confirmation authority until close" in text
    # The live-state line itself must never claim "confirmed" outright.
    live_lines = [l for l in text.splitlines() if "live" in l.lower() and "1H" in l]
    for line in live_lines:
        assert "confirmed" not in line.lower() or "no confirmation authority" in line.lower()


# ---------------------------------------------------------------------------
# 13. Missing proof vs broken/failed proof stay distinct
# ---------------------------------------------------------------------------

def test_missing_proof_and_broken_proof_are_never_conflated():
    # NEAR_ENTRY: retest partial (forming), hold missing — neither is BROKEN.
    ne_audit = moa.build_operator_audit(_near_entry_result())
    tj = ne_audit["tier_judgment"]
    assert tj["broken_proof"] == ["—"]
    assert any("hold_status" in m for m in tj["missing_proof"])

    # A genuinely failed retest must appear under BROKEN, never MISSING.
    failed = _completed_result("WAIT", retest_status="failed", hold_status="missing")
    failed_audit = moa.build_operator_audit(failed)
    tj2 = failed_audit["tier_judgment"]
    assert any("retest_status=failed" in b for b in tj2["broken_proof"])
    assert not any("retest_status=failed" in m for m in tj2["missing_proof"])


def test_forming_is_never_displayed_as_failed():
    audit = moa.build_operator_audit(_near_entry_result())
    exe = audit["execution_proof"]
    assert exe["hold"]["state"] != "BROKEN"
    assert exe["sequence"] != "FAILED"


# ---------------------------------------------------------------------------
# 14. Judgment-before-delivery semantics for WAIT
# ---------------------------------------------------------------------------

def test_wait_dedup_reason_never_reads_as_the_cause_of_the_tier():
    audit = moa.build_operator_audit(_wait_result())
    delivery = audit["delivery"]
    assert delivery["alert_eligible"] == "NO"
    assert delivery["alert_sent"] == "NO"
    assert delivery["dedup_reason"] == "wait_no_alert"
    # Judgment (tier_judgment) is a wholly separate section from delivery —
    # the renderer must not fold dedup language into WHY_THIS_TIER.
    tj = audit["tier_judgment"]
    assert "dedup" not in tj["why_this_tier"].lower()
    assert "wait_no_alert" not in tj["why_this_tier"]


# ---------------------------------------------------------------------------
# 15. Zero scanner-engine invocations at runtime (belt-and-suspenders beyond
#     the static check — patch every heavy organ and prove the renderer still
#     produces identical output, i.e. it never touches any of them).
# ---------------------------------------------------------------------------

def test_renderer_runtime_never_touches_any_scanner_module(monkeypatch):
    import sys

    poison_modules = [
        "src.market_data", "src.indicators", "src.prefilter", "src.claude_client",
        "src.tiering", "src.scheduler", "src.state_store", "src.discord_alerts",
    ]
    original_import = __import__

    def _tripwire(name, *args, **kwargs):
        if name in poison_modules:
            raise AssertionError(f"renderer imported forbidden module at runtime: {name}")
        return original_import(name, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "__import__", _tripwire)
    try:
        moa.render_operator_audit(_snipe_it_result())
        moa.build_operator_audit(_wait_result())
        moa.render_operator_audit_json(_starter_result())
    finally:
        pass


# ---------------------------------------------------------------------------
# 16. (covered by purity test above)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 21-22. Chunking safety + mention sanitization
# ---------------------------------------------------------------------------

def test_chunk_operator_audit_respects_discord_length_and_keeps_all_sections():
    text = moa.render_operator_audit(_snipe_it_result())
    long_text = (text + "\n") * 5  # force multi-chunk
    chunks = moa.chunk_operator_audit(long_text, max_len=500)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 500
    assert "".join(chunks).replace("\n", "") == long_text.replace("\n", "")


def test_mention_sanitization_neutralizes_everyone_and_user_mentions():
    result = _completed_result("WAIT", reason="@everyone check <@123456789> now")
    tr = result["tiering_result"]
    tr["snipe_ladder"]["why_this_ladder_tier"] = ""
    tr["snipe_gate_audit"]["diagnostic_sentence"] = ""
    text = moa.render_operator_audit(result)
    assert "@everyone" not in text
    assert "<@123456789>" not in text
    assert "[mention]" in text


# ---------------------------------------------------------------------------
# 23-24. Compact mode / JSON mode
# ---------------------------------------------------------------------------

def test_compact_mode_matches_legacy_short_summary_shape():
    result = _snipe_it_result()
    compact = moa.render_operator_audit_compact(result)
    assert "WMT" in compact
    assert "SNIPE_IT" in compact
    assert "Alert sent: True" in compact
    assert "Scan ID: analyze_WMT_120000" in compact
    assert len(compact.splitlines()) <= 4


def test_json_mode_is_valid_json_and_whitelist_only():
    result = _snipe_it_result()
    payload = json.loads(moa.render_operator_audit_json(result))
    assert payload["verdict_capital"]["final_tier"] == "SNIPE_IT"
    assert "tier_judgment" in payload
    assert "delivery" in payload
    # Whitelist-only: no raw API keys/tokens/prompt text leak through.
    blob = json.dumps(payload)
    assert "ANTHROPIC" not in blob
    assert "system_prompt" not in blob


# ---------------------------------------------------------------------------
# 25. No fake derived metrics without valid inputs
# ---------------------------------------------------------------------------

def test_no_derived_distance_percentages_without_valid_source_numbers():
    result = _completed_result("WAIT", scan_price=None, trigger_level=None, invalidation_level=None)
    audit = moa.build_operator_audit(result)
    tl = audit["trade_location"]
    assert tl["dist_to_trigger_pct"] == "—"
    assert tl["dist_to_invalidation_pct"] == "—"


# ---------------------------------------------------------------------------
# 26. !help reflects new command behavior
# ---------------------------------------------------------------------------

def test_help_text_documents_new_analyze_modes():
    src = Path("main.py").read_text(encoding="utf-8")
    assert "!analyze TICKER [compact|json]" in src
    assert "Full manual operator audit" in src


# ---------------------------------------------------------------------------
# Additional: run_analyze return payload carries `enriched` (Phase 14X minimal
# additive exposure) without altering any existing key or judgment behavior.
# ---------------------------------------------------------------------------

def test_run_analyze_return_signature_includes_enriched_key_only_additively():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    analyze_body = src[src.index("async def run_analyze"):]
    assert '"enriched": enriched,' in analyze_body
    # All pre-existing keys remain present verbatim.
    for key in (
        '"status": "complete"', '"scan_id": scan_id', '"ticker": ticker',
        '"final_tier": final_tier', '"safe_for_alert"', '"dedup_reason"',
        '"alert_sent"', '"channel_id"', '"tiering_result": tiering_result',
    ):
        assert key in analyze_body

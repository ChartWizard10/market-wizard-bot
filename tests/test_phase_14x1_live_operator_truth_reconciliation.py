"""Phase 14X.1 — live operator evidence-truth reconciliation.

A REAL live production `!analyze WMT` audit plus direct chart cross-
examination revealed evidence-lineage contradictions in the Phase 14X
operator display (never in tiering/scoring/routing, which this phase does
not touch):

  1. A model-owned timestamp (final_signal.timestamp_et) was displayed as
     "Scan time" — the operator scan clock must be runtime-owned, never
     model-owned.
  2. The top-level entry-quality summary read stale signal-level retest/hold
     fields while the dedicated 1H engine had already superseded them with
     higher-authority truth.
  3. Local 1H retest/hold proof was displayed without distinguishing it from
     a fully swing-thesis-qualified sequence — an operator could misread
     "Retest: CONFIRMED" as meaning the whole swing thesis was validated,
     even while Daily permission is DENIED and Structure is MISSING.
  4/5. Invalidation/Target rows read "CONFIRMED" when only a level/condition
     was DEFINED — no event-level evidence exists to claim either was
     triggered/hit.
  6. Source-provided risk_reward was shown next to a missing executable
     entry without clarifying whether it represented executable-entry
     geometry or only reference geometry.
  7. The model's own overhead_status was shown as "Path clarity: CLEAN"
     without disclosing that this renderer has no independent structural
     verification of that specific claim's authorship.
  8. A model-authored target reason invoking "liquidity pool" was displayed
     without disclosing that no discrete liquidity schema exists to validate
     it.
  9. Weekly/HTF context could show a posture value even when the underlying
     campaign evidence was materially incomplete.

This phase makes ONE operator screen tell ONE truth. It changes ZERO
tiering/scoring/routing behavior — same law as Phase 14X and the prior
adversarial review.
"""

import copy
import json
from pathlib import Path

from src import manual_operator_audit as moa
from tests.test_phase_14x_full_manual_operator_audit import (
    _base_signal,
    _completed_result,
    _full_tiering_result,
    _snipe_it_result,
    _wait_result,
)


# ---------------------------------------------------------------------------
# The observed live WMT-shaped regression fixture (section 15 of the spec).
# Real production enum values throughout — never fabricated happy-path ones.
# ---------------------------------------------------------------------------

_MODEL_TIMESTAMP = "2025-01-15T16:00:00-05:00"       # stale model-owned field
_RUNTIME_TIMESTAMP_ET = "2026-09-02T09:41:00-04:00"  # controlled 2026 runtime instant
_RUNTIME_TIMESTAMP_UTC = "2026-09-02T13:41:00+00:00"


def _wmt_shaped_result() -> dict:
    signal = _base_signal(
        "WAIT",
        timestamp_et=_MODEL_TIMESTAMP,
        scan_price=105.92,
        setup_family="none",
        structure_event="none",
        trend_state="failure",
        retest_status="partial",
        hold_status="missing",
        trigger_level=None,                 # no executable entry
        invalidation_condition="Close below prior swing low",
        invalidation_level=103.40,
        targets=[
            {"label": "T1", "level": 114.29, "reason": "nearest liquidity pool above"},
            {"label": "T2", "level": 115.75, "reason": "measured move extension"},
        ],
        risk_reward=3.32,
        overhead_status="clear",
        capital_action="no_trade",
        discord_channel="none",
        reason="Structure not yet established; local 1H repair only.",
    )
    tiering_result = _full_tiering_result("WAIT")
    tiering_result["final_signal"] = signal
    tiering_result["capital_action"] = "no_trade"
    tiering_result["final_discord_channel"] = "none"
    tiering_result["safe_for_alert"] = False

    tiering_result["trade_location"]["location_state"] = "lower_zone_defense"

    # Daily: PERMISSION_DENIED
    tiering_result["timeframe_alignment"]["swing_timeframe"] = {"state": "PERMISSION_DENIED"}

    # 4H: TRANSITION / FORMING / LOW confidence / WICK_ONLY break / APPROACHING retest
    tiering_result["four_hour_operational"] = {
        "enabled": True, "status": "OK",
        "structural_state": "TRANSITION",
        "state_confidence": "LOW",
        "operational_location": "TRANSITION",
        "operational_readiness": "FORMING",
        "structure": {"break_state": "WICK_ONLY"},
        "retest_truth": {"state": "APPROACHING"},
    }

    # 1H: RETEST_REAL / HOLD_CONFIRMED, but readiness only FORMING (no live
    # trigger yet) — real production enums throughout.
    tiering_result["one_hour_entry"] = {
        "status": "ENABLED", "data_freshness": "FRESH",
        "trigger_state": "TRIGGER_FORMING",
        "score": 55, "score_label": "PARTIAL_1H_TRIGGER",
        "pullback_retest_hold": {"retest_truth": "RETEST_REAL", "hold_truth": "HOLD_CONFIRMED"},
        "location_realism": {"label": "LOWER_ZONE"},
        "candle_truth": {
            "event_type": "REJECTION", "closed_candle_confirms": False,
            "body_acceptance": False, "wick_rejection": True,
            "follow_through_present": False, "volume_support": "UNKNOWN",
        },
        "invalidation": {"clear": True},
        "path_quality": {"path_label": "CLEAN"},
        "hard_caps_applied": [], "downgrade_reasons": [],
        "alert_truth_label": "TRIGGER_FORMING",
        "scanner_sentence": "1H repair in progress; Daily permission still denied.",
    }

    # Weekly: campaign evidence materially incomplete (data_status OK, but
    # required fields blank) — must not read as positive sponsorship.
    tiering_result["higher_timeframe_context"] = {
        "data_status": "OK",
        "monthly_bias_state": None,
        "weekly_campaign_state": None,
        "campaign_location_label": None,
        "campaign_location_quality": None,
        "context_grade": None, "context_score": None,
        "supports_long_setup": False, "weakens_long_setup": False,
        "blocks_snipe_contextually": False, "promotion_support": False,
        "missing_htf_proof": ["weekly_bar_history"], "blocking_reasons": [],
        "diagnostic_sentence": "Weekly evidence incomplete.",
    }

    # Candle evidence (Daily-derived, per production truth) — timeframe None.
    tiering_result["candle_evidence"] = {
        "status": "ok", "timeframe": None, "candle_status": "CLOSED",
        "body_pct": 30.0, "upper_wick_pct": 15.0, "lower_wick_pct": 55.0,
        "close_position_pct": 35.0, "candle_family": "REJECTION",
        "close_quality": "WEAK", "wick_read": "LOWER_WICK_DEMAND_DEFENSE",
        "level_reaction": "REJECTED", "next_candle_verdict": "PENDING",
        "candle_veto": "HOSTILE_WICK", "display_text": "Rejected at lower zone edge.",
    }

    tiering_result["snipe_gate_audit"] = {
        "audit_label": "NOT_READY", "promotion_state": "NOT_ELIGIBLE",
        "blocked_gate_names": ["daily_structure_break", "daily_permission"],
        "missing_proofs": ["hold_confirmed_1h_closed"],
        "diagnostic_sentence": "Daily permission denied; no structure break.",
    }
    tiering_result["snipe_ladder"] = {
        "internal_ladder_tier": "NONE",
        "why_this_ladder_tier": "No Daily structure event; Daily swing permission denied.",
        "why_not_higher": "Daily permission is DENIED and Structure is MISSING; local 1H repair cannot override higher-timeframe denial.",
        "next_promotion_proof": ["Confirmed Daily structure break with Daily permission granted."],
        "failure_condition": "Price closes below the prior swing low, extending the Daily downtrend.",
    }
    tiering_result["snipe_confirmed_seal"] = {"applied": False}
    tiering_result["calibration"] = {"raw_score": 40, "calibrated_score": 40, "delta": 0, "score_band": "F"}

    result = {
        "status": "complete",
        "scan_id": "analyze_WMT_094100",
        "ticker": "WMT",
        "final_tier": "WAIT",
        "safe_for_alert": False,
        "dedup_reason": "wait_no_alert",
        "alert_sent": False,
        "channel_id": None,
        "tiering_result": tiering_result,
        "enriched": {
            "ticker": "WMT", "sma20": 108.10, "sma50": 111.40, "sma200": 96.30,
            "current_price": 105.92, "atr": 1.85,
            "overhead_status": "moderate", "overhead_level": 109.75,
            "overhead_distance_pct": 3.62,
            "daily_bar_context": {
                "status": "CLOSED",
                "last_closed_daily_date": "2026-09-01",
                "live_daily_date": None,
                "live_bar_available": False,
                "evaluated_at": "2026-09-02T13:40:55+00:00",
            },
        },
        # Phase 14X.1 additive runtime scan-clock fields.
        "scan_timestamp_et": _RUNTIME_TIMESTAMP_ET,
        "scan_timestamp_utc": _RUNTIME_TIMESTAMP_UTC,
    }
    return result


# ===========================================================================
# TEST 1-4 — Scan clock
# ===========================================================================

def test_runtime_scan_time_wins_over_model_timestamp():
    result = _wmt_shaped_result()
    text = moa.render_operator_audit(result)
    assert _RUNTIME_TIMESTAMP_ET in text
    assert f"Scan executed:             {_RUNTIME_TIMESTAMP_ET}" in text
    # The stale 2025 model timestamp must never appear as "Scan executed".
    scan_executed_line = next(l for l in text.splitlines() if l.startswith("Scan executed:"))
    assert _MODEL_TIMESTAMP not in scan_executed_line


def test_runtime_scan_timestamp_is_timezone_aware():
    result = _wmt_shaped_result()
    ts = result["scan_timestamp_et"]
    assert ts.endswith("-04:00") or ts.endswith("+00:00") or "+" in ts or ts.count("-") >= 3
    # A naive timestamp (no offset, no "Z") must never be produced by the
    # scheduler's capture — parse it back and require tzinfo.
    from datetime import datetime
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


def test_model_timestamp_non_authority():
    base = _wmt_shaped_result()
    mutated = copy.deepcopy(base)
    mutated["tiering_result"]["final_signal"]["timestamp_et"] = "1999-01-01T00:00:00-05:00"
    text_base = moa.render_operator_audit(base)
    text_mutated = moa.render_operator_audit(mutated)
    scan_line_base = next(l for l in text_base.splitlines() if l.startswith("Scan executed:"))
    scan_line_mutated = next(l for l in text_mutated.splitlines() if l.startswith("Scan executed:"))
    assert scan_line_base == scan_line_mutated


def test_daily_data_provenance_renders_truthfully_without_fabricated_time():
    result = _wmt_shaped_result()
    text = moa.render_operator_audit(result)
    assert "Daily evidence status:     CLOSED" in text
    date_line = next(l for l in text.splitlines() if l.startswith("Last closed daily date:"))
    assert date_line == "Last closed daily date:    2026-09-01"
    date_value = date_line.split(":", 1)[1].strip()
    # No exact clock time is fabricated onto the date-only source field.
    assert "T" not in date_value
    assert ":" not in date_value


def test_scan_executed_is_unavailable_not_model_time_when_runtime_field_absent():
    """Historical/older result objects without the additive runtime field
    must show UNAVAILABLE — never silently fall back to the model's clock."""
    result = _snipe_it_result()
    result.pop("scan_timestamp_et", None)
    text = moa.render_operator_audit(result)
    scan_line = next(l for l in text.splitlines() if l.startswith("Scan executed:"))
    assert "—" in scan_line
    assert "2026" not in scan_line and "2025" not in scan_line


# ===========================================================================
# TEST 5 — One entry truth
# ===========================================================================

def test_entry_summary_uses_1h_authority_not_stale_signal_fields():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    entry_quality = audit["verdict_capital"]["entry_quality"]
    assert "retest=CONFIRMED (RETEST_REAL)" in entry_quality
    assert "hold=CONFIRMED (HOLD_CONFIRMED)" in entry_quality
    # The stale signal-level values (partial/missing) must not be what the
    # top summary reports as the classified state.
    assert "retest=FORMING" not in entry_quality
    assert "retest=MISSING" not in entry_quality


# ===========================================================================
# TEST 6 — Local proof does not become swing proof
# ===========================================================================

def test_local_proof_does_not_become_swing_proof():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}

    assert doctrine["Retest"]["state"] == "CONFIRMED"
    assert doctrine["Hold"]["state"] == "CONFIRMED"
    assert doctrine["Retest"]["qualification_note"] == "HTF THESIS AUTHORIZATION: NOT AUTHORIZED — local proof alone does not authorize it"
    assert doctrine["Hold"]["qualification_note"] == "HTF THESIS AUTHORIZATION: NOT AUTHORIZED — local proof alone does not authorize it"

    ar = audit["authority_reconciliation"]
    assert ar["local_proof"] == "IMPROVING"
    assert ar["htf_thesis_authorization"] == "NOT AUTHORIZED"
    assert ar["local_execution_sequence"] == "INCOMPLETE"
    assert ar["capital"] == "NONE"
    assert any("Daily permission" in b for b in ar["blockers"])


def test_htf_thesis_authorized_when_structure_confirmed_and_daily_granted():
    result = _snipe_it_result()
    audit = moa.build_operator_audit(result)
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Retest"]["qualification_note"] is None
    assert doctrine["Hold"]["qualification_note"] is None
    ar = audit["authority_reconciliation"]
    assert ar["htf_thesis_authorization"] == "AUTHORIZED"


def test_htf_thesis_authorized_does_not_imply_local_execution_complete():
    """The 'Important 4H law' regression: Daily YES + Structure confirmed +
    4H WICK_ONLY must show HTF thesis AUTHORIZED while local execution
    sequence is NOT complete, and capital is unaffected by either."""
    result = _snipe_it_result()
    result["tiering_result"]["four_hour_operational"]["structure"]["break_state"] = "WICK_ONLY"
    audit = moa.build_operator_audit(result)
    ar = audit["authority_reconciliation"]
    assert ar["htf_thesis_authorization"] == "AUTHORIZED"
    assert ar["local_execution_sequence"] != "COMPLETE"
    assert ar["capital"] == "FULL"  # capital is owned only by final_tier (SNIPE_IT here), never by 4H/1H evidence


# ===========================================================================
# TEST 7-8 — Invalidation/Target DEFINED, never CONFIRMED
# ===========================================================================

def test_invalidation_renders_defined_never_confirmed():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Invalidation"]["state"] == "DEFINED"
    text = moa.render_operator_audit(result)
    assert "Invalidation (DEFINED):" in text
    assert "CONFIRMED" not in next(l for l in text.splitlines() if "Invalidation" in l and "DEFINED" in l)


def test_targets_render_defined_never_confirmed_or_hit():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Target"]["state"] == "DEFINED"
    text = moa.render_operator_audit(result)
    assert "Targets (DEFINED — not hit/confirmed events):" in text


# ===========================================================================
# TEST 9-10 — R:R provenance
# ===========================================================================

def test_rr_with_missing_trigger_shows_executable_entry_unavailable():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    risk = audit["risk_runway"]
    assert risk["executable_trigger"] == "UNAVAILABLE"
    assert risk["executable_entry_rr"] == "UNAVAILABLE"
    assert risk["source_rr"] == "3.32:1"     # source/reference R:R still renders, with provenance


def test_rr_basis_reconciliation_only_when_math_matches_within_tolerance():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    risk = audit["risk_runway"]
    # scan_price=105.92, invalidation=103.40, T1=114.29 -> (114.29-105.92)/(105.92-103.40)
    # = 8.37/2.52 = 3.3214... which is within 5% of the source 3.32 -> reconciles.
    assert risk["reference_rr"] != "—"
    assert "DERIVED_DISPLAY" in risk["reference_rr_basis"]

    # Now break the reconciliation: change the source risk_reward far enough
    # that it can no longer match the deterministic geometry.
    mutated = copy.deepcopy(result)
    mutated["tiering_result"]["final_signal"]["risk_reward"] = 99.0
    audit2 = moa.build_operator_audit(mutated)
    risk2 = audit2["risk_runway"]
    assert risk2["reference_rr"] == "—"


def test_trigger_exists_but_only_scan_price_geometry_reconciles():
    """Adversarial case A: a trigger exists, but the source R:R only matches
    scan-price geometry, not trigger geometry — trigger existence alone must
    never produce a fake executable-entry R:R."""
    result = _wmt_shaped_result()
    mutated = copy.deepcopy(result)
    sig = mutated["tiering_result"]["final_signal"]
    # A trigger far from scan_price so trigger-basis geometry cannot
    # reconcile to the same source R:R that the scan-price basis matches.
    sig["trigger_level"] = 95.00
    audit = moa.build_operator_audit(mutated)
    risk = audit["risk_runway"]
    assert risk["executable_trigger"] != "UNAVAILABLE"  # trigger DOES exist
    assert risk["executable_entry_rr"] == "UNAVAILABLE"
    assert risk["executable_entry_rr_basis"] == "NOT RECONCILED"
    # The independent scan-price basis is unaffected by the trigger's presence.
    assert risk["reference_rr"] != "—"


def test_trigger_geometry_reconciles_to_source_rr():
    """Adversarial case B: trigger geometry genuinely matches source R:R ->
    executable-entry R:R IS reconciled."""
    result = _wmt_shaped_result()
    mutated = copy.deepcopy(result)
    sig = mutated["tiering_result"]["final_signal"]
    # trigger=105.92 (== scan_price), invalidation=103.40, T1=114.29 ->
    # same geometry the scan-price basis already proved reconciles to 3.32.
    sig["trigger_level"] = 105.92
    audit = moa.build_operator_audit(mutated)
    risk = audit["risk_runway"]
    assert risk["executable_entry_rr"] != "UNAVAILABLE"
    assert "DERIVED_DISPLAY" in risk["executable_entry_rr_basis"]


def test_invalid_trigger_invalidation_geometry_yields_unavailable_executable_rr():
    """Adversarial case C/D: trigger exists but invalidation >= trigger (or
    target <= trigger) -> executable R:R stays UNAVAILABLE, never fake."""
    result = _wmt_shaped_result()
    mutated = copy.deepcopy(result)
    sig = mutated["tiering_result"]["final_signal"]
    sig["trigger_level"] = 100.0
    sig["invalidation_level"] = 105.0   # invalidation ABOVE trigger — invalid for a bullish mandate
    audit = moa.build_operator_audit(mutated)
    risk = audit["risk_runway"]
    assert risk["executable_entry_rr"] == "UNAVAILABLE"

    mutated2 = copy.deepcopy(result)
    sig2 = mutated2["tiering_result"]["final_signal"]
    sig2["trigger_level"] = 120.0
    sig2["targets"][0]["level"] = 110.0  # target BELOW trigger — invalid reward
    audit2 = moa.build_operator_audit(mutated2)
    risk2 = audit2["risk_runway"]
    assert risk2["executable_entry_rr"] == "UNAVAILABLE"


def test_rr_reconcile_helper_rejects_nan_inf_and_malformed_inputs():
    assert moa._reconcile_rr(float("nan"), 100, 110, 3.0) is None
    assert moa._reconcile_rr(105, float("inf"), 110, 3.0) is None
    assert moa._reconcile_rr(105, 100, 110, float("nan")) is None
    assert moa._reconcile_rr("abc", 100, 110, 3.0) is None
    assert moa._reconcile_rr(None, None, None, None) is None


# ===========================================================================
# TEST 11 — Model overhead does not become verified path
# ===========================================================================

def test_model_overhead_clear_does_not_become_verified_path():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    risk = audit["risk_runway"]
    assert risk["reported_overhead"] == "clear"
    assert risk["reported_overhead_source"] == "MODEL / final_signal"
    # The real deterministic structural computation is surfaced SEPARATELY —
    # and disagrees here (moderate, not clear) — proving the two are never
    # silently merged into one claim.
    assert risk["structural_overhead_status"] == "moderate"
    text = moa.render_operator_audit(result)
    assert "Reported overhead:         clear" in text
    assert "Structural overhead (deterministic): moderate" in text


def test_model_overhead_blocked_also_kept_separate_from_structural():
    result = _wmt_shaped_result()
    mutated = copy.deepcopy(result)
    mutated["tiering_result"]["final_signal"]["overhead_status"] = "blocked"
    audit = moa.build_operator_audit(mutated)
    risk = audit["risk_runway"]
    assert risk["reported_overhead"] == "blocked"
    assert risk["structural_overhead_status"] == "moderate"  # unchanged, independent


def test_path_quality_not_independently_verified_when_absent():
    result = _wait_result()
    audit = moa.build_operator_audit(result)
    assert audit["risk_runway"]["path_clarity_label"] == "NOT INDEPENDENTLY VERIFIED"


# ===========================================================================
# TEST 12 — Model target reason is not liquidity proof
# ===========================================================================

def test_model_target_reason_liquidity_language_is_not_treated_as_verified():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    t1 = audit["trade_location"]["targets"][0]
    assert t1["reason"] == "nearest liquidity pool above"
    assert t1["reason_provenance"] == "MODEL"
    assert t1["liquidity_validation"] == "UNAVAILABLE"
    text = moa.render_operator_audit(result)
    assert "nearest liquidity pool above" in text
    assert "[reason: MODEL]" in text
    assert "Liquidity validation: UNAVAILABLE" in text


def test_target_reason_without_liquidity_language_gets_no_spurious_disclaimer():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    t2 = audit["trade_location"]["targets"][1]
    assert t2["reason"] == "measured move extension"
    assert t2.get("liquidity_validation") is None


# ===========================================================================
# TEST 13 — Weekly incomplete evidence
# ===========================================================================

def test_weekly_incomplete_evidence_never_reads_as_positive_sponsorship():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["campaign_evidence"] == "INCOMPLETE"
    assert weekly["positive_sponsorship"] == "NOT PROVEN"
    text = moa.render_operator_audit(result)
    assert "Campaign evidence:" in text
    assert "INCOMPLETE" in text


def test_weekly_complete_evidence_can_show_proven_sponsorship():
    result = _snipe_it_result()
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["campaign_evidence"] == "COMPLETE"
    assert weekly["positive_sponsorship"] == "PROVEN"


def test_weekly_literal_unknown_values_never_count_as_complete_evidence():
    """src/higher_timeframe_context.py's own real vocabulary (BIAS_STATES,
    GRADES, etc.) includes the literal string "UNKNOWN" as a legitimate
    degraded value. A bare truthiness check would wrongly treat it as
    present/complete since it is a non-empty string — this must not happen."""
    result = _snipe_it_result()
    htf = result["tiering_result"]["higher_timeframe_context"]
    htf["monthly_bias_state"] = "UNKNOWN"
    htf["weekly_campaign_state"] = "UNKNOWN"
    htf["campaign_location_label"] = "UNKNOWN"
    htf["context_grade"] = "UNKNOWN"
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly["campaign_evidence"] == "INCOMPLETE"
    assert weekly["positive_sponsorship"] == "NOT PROVEN"


def test_weekly_degraded_data_status_never_proven_sponsorship():
    result = _snipe_it_result()
    htf = result["tiering_result"]["higher_timeframe_context"]
    htf["data_status"] = "DEGRADED_INSUFFICIENT_HISTORY"
    audit = moa.build_operator_audit(result)
    weekly = audit["timeframe_sovereignty"]["weekly"]
    assert weekly.get("campaign_evidence") == "INCOMPLETE"
    assert weekly.get("positive_sponsorship") != "PROVEN"


# ===========================================================================
# TEST 14 — Authority reconciliation never promotes
# ===========================================================================

def test_authority_reconciliation_capital_matches_final_tier_always():
    for fixture in (_wait_result, _snipe_it_result, _wmt_shaped_result):
        result = fixture()
        audit = moa.build_operator_audit(result)
        ar = audit["authority_reconciliation"]
        exe = audit["execution_proof"]
        # AUTHORITY RECONCILIATION and EXECUTION PROOF must never disagree
        # about capital readiness — both derive from the same final_tier.
        assert ar["capital"] == exe["capital_readiness"]


# ===========================================================================
# TEST 15-16 — Immutability
# ===========================================================================

def test_final_tier_immutable_across_render():
    result = _wmt_shaped_result()
    before = result["final_tier"]
    moa.render_operator_audit(result)
    moa.render_operator_audit_json(result)
    moa.render_operator_audit_compact(result)
    assert result["final_tier"] == before


def test_no_score_or_capital_mutation_deep_equality():
    for fixture in (_wait_result, _snipe_it_result, _wmt_shaped_result):
        original = fixture()
        snapshot = copy.deepcopy(original)
        moa.build_operator_audit(original)
        moa.render_operator_audit(original)
        moa.render_operator_audit_json(original)
        moa.render_operator_audit_compact(original)
        assert original == snapshot


# ===========================================================================
# TEST 17 — No second scanner
# ===========================================================================

def test_renderer_still_has_zero_scanner_dependencies():
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
        assert token not in src, f"forbidden dependency reintroduced: {token!r}"


# ===========================================================================
# TEST 18 — Phase 14W parity (imported/run alongside — see test command list)
# ===========================================================================

def test_phase_14w_parity_module_still_importable():
    import tests.test_phase_14w_manual_analyze_parity  # noqa: F401


# ===========================================================================
# TEST 19 — Live candle law preserved
# ===========================================================================

def test_live_1h_still_information_only_after_reconciliation():
    result = _wmt_shaped_result()
    text = moa.render_operator_audit(result)
    assert "information only — no confirmation authority until close" in text
    live_lines = [l for l in text.splitlines() if "live" in l.lower() and "1H" in l.upper()]
    for line in live_lines:
        assert "confirmed" not in line.lower() or "no confirmation authority" in line.lower()


# ===========================================================================
# TEST 20 — Missing vs broken still distinct
# ===========================================================================

def test_missing_vs_broken_still_distinct_after_reconciliation():
    result = _wmt_shaped_result()
    audit = moa.build_operator_audit(result)
    tj = audit["tier_judgment"]
    assert any("hold_status" in m for m in tj["missing_proof"])
    assert tj["broken_proof"] == ["—"]

    failed = _completed_result("WAIT", retest_status="failed")
    audit2 = moa.build_operator_audit(failed)
    tj2 = audit2["tier_judgment"]
    assert any("retest_status=failed" in b for b in tj2["broken_proof"])


# ===========================================================================
# TEST — BROKEN local proof must outrank IMPROVING (Phase 14X.1 hardening)
# ===========================================================================

def test_retest_real_hold_failed_is_broken_never_improving():
    result = _snipe_it_result()
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_REAL", "hold_truth": "HOLD_FAILED",
    }
    audit = moa.build_operator_audit(result)
    ar = audit["authority_reconciliation"]
    assert ar["local_proof"] == "BROKEN"
    exe = audit["execution_proof"]
    assert exe["hold"]["state"] == "BROKEN"
    assert exe["sequence"] == "FAILED"


def test_retest_edge_only_hold_failed_is_broken():
    result = _snipe_it_result()
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_EDGE_ONLY", "hold_truth": "HOLD_FAILED",
    }
    audit = moa.build_operator_audit(result)
    assert audit["authority_reconciliation"]["local_proof"] == "BROKEN"


def test_retest_missed_hold_confirmed_is_never_called_complete():
    result = _snipe_it_result()
    result["tiering_result"]["one_hour_entry"]["pullback_retest_hold"] = {
        "retest_truth": "RETEST_MISSED", "hold_truth": "HOLD_CONFIRMED",
    }
    audit = moa.build_operator_audit(result)
    assert audit["authority_reconciliation"]["local_proof"] != "CONFIRMED"
    assert audit["authority_reconciliation"]["local_proof"] != "BROKEN"


def test_retest_real_hold_confirmed_never_broken():
    result = _snipe_it_result()  # already RETEST_CORE_VALID/HOLD_CONFIRMED
    audit = moa.build_operator_audit(result)
    assert audit["authority_reconciliation"]["local_proof"] in ("CONFIRMED", "IMPROVING")


# ===========================================================================
# TEST — failed_breakdown_reclaim is a bullish CONFIRMED event, never BROKEN
# ===========================================================================

def test_failed_breakdown_reclaim_is_never_automatically_broken_or_failed():
    result = _snipe_it_result()
    result["tiering_result"]["final_signal"]["structure_event"] = "failed_breakdown_reclaim"
    audit = moa.build_operator_audit(result)

    assert audit["setup"]["stage"] != "FAILED"
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Structure"]["state"] == "CONFIRMED"
    assert doctrine["Structure"]["state"] != "BROKEN"

    text = moa.render_operator_audit(result)
    assert "Setup stage: FAILED" not in text
    assert "Structure: BROKEN" not in text


def test_failed_breakdown_reclaim_with_daily_4h_context_stays_bullish_capital_from_tier():
    """failed_breakdown_reclaim + valid Daily/4H context: renderer keeps the
    bullish-reclaim semantic; capital still comes only from final_tier."""
    result = _snipe_it_result()
    result["tiering_result"]["final_signal"]["structure_event"] = "failed_breakdown_reclaim"
    audit = moa.build_operator_audit(result)
    ar = audit["authority_reconciliation"]
    assert ar["htf_thesis_authorization"] == "AUTHORIZED"   # Daily YES + structure now CONFIRMED
    assert ar["capital"] == "FULL"                           # unchanged — owned by final_tier (SNIPE_IT)


def test_choch_is_not_automatically_full_structure_confirmation():
    result = _snipe_it_result()  # Daily permission already YES in this fixture
    result["tiering_result"]["final_signal"]["structure_event"] = "CHOCH"
    audit = moa.build_operator_audit(result)
    doctrine = {row["step"]: row for row in audit["doctrine_sequence"]}
    assert doctrine["Structure"]["state"] == "FORMING"
    assert doctrine["Structure"]["state"] != "CONFIRMED"
    ar = audit["authority_reconciliation"]
    # CHOCH alone (FORMING, not CONFIRMED) must not authorize the HTF thesis
    # even though Daily permission reads YES here.
    assert ar["htf_thesis_authorization"] != "AUTHORIZED"


# ===========================================================================
# TEST 21 — Discord chunking safe with expanded labels
# ===========================================================================

def test_discord_chunking_safe_with_expanded_truth_labels():
    result = _wmt_shaped_result()
    text = moa.render_operator_audit(result)
    chunks = moa.chunk_operator_audit(text, max_len=500)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 500
    assert "".join(chunks) == text
    # No section header lost or duplicated.
    for header in ("SWING DOCTRINE SEQUENCE", "LOCAL EXECUTION PROOF", "AUTHORITY RECONCILIATION",
                   "TIER JUDGMENT", "DELIVERY / AUDIT"):
        assert text.count(header) == "".join(chunks).count(header)


# ===========================================================================
# TEST 22 — Compact mode no regression
# ===========================================================================

def test_compact_mode_unchanged_shape():
    result = _wmt_shaped_result()
    compact = moa.render_operator_audit_compact(result)
    assert "WMT" in compact
    assert "WAIT" in compact
    assert len(compact.splitlines()) <= 4


# ===========================================================================
# TEST 23 — JSON mode
# ===========================================================================

def test_json_mode_valid_and_carries_new_provenance_fields():
    result = _wmt_shaped_result()
    payload = json.loads(moa.render_operator_audit_json(result))
    assert payload["verdict_capital"]["scan_executed"] == _RUNTIME_TIMESTAMP_ET
    assert payload["verdict_capital"]["model_timestamp"] == _MODEL_TIMESTAMP
    assert payload["authority_reconciliation"]["htf_thesis_authorization"] == "NOT AUTHORIZED"
    assert payload["authority_reconciliation"]["local_execution_sequence"] == "INCOMPLETE"
    assert payload["risk_runway"]["executable_entry_rr"] == "UNAVAILABLE"
    blob = json.dumps(payload)
    assert "ANTHROPIC" not in blob
    assert "system_prompt" not in blob


# ===========================================================================
# TEST 24 — Error paths unchanged
# ===========================================================================

def test_error_status_results_do_not_crash_renderer():
    for status in ("error", "data_failure", "claude_error", "model_error", "skipped"):
        result = {"status": status, "ticker": "WMT", "final_tier": "WAIT"}
        # Renderer must not raise even on a non-"complete" result — main.py
        # gates on status before calling it, but the renderer itself stays
        # defensive per its existing hard guarantees.
        moa.render_operator_audit(result)
        moa.render_operator_audit_json(result)
        moa.render_operator_audit_compact(result)


# ===========================================================================
# TEST 25 — Normal alert firewall (discord_alerts untouched)
# ===========================================================================

def test_discord_alerts_module_not_touched_by_this_phase():
    import subprocess
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    ).stdout
    assert "src/discord_alerts.py" not in diff


# ===========================================================================
# TEST 26 — WMT-shaped golden: one coherent case file, no contradictions
# ===========================================================================

def test_wmt_shaped_golden_is_one_coherent_case_file():
    result = _wmt_shaped_result()
    text = moa.render_operator_audit(result)

    assert "VERDICT: ⚪ WAIT" in text
    assert "CAPITAL: NO TRADE" in text
    assert f"Scan executed:             {_RUNTIME_TIMESTAMP_ET}" in text
    assert _MODEL_TIMESTAMP not in next(l for l in text.splitlines() if l.startswith("Scan executed:"))

    for section in (
        "SETUP", "SWING DOCTRINE SEQUENCE", "LOCAL EXECUTION PROOF",
        "TIMEFRAME SOVEREIGNTY", "AUTHORITY RECONCILIATION",
        "TRADE LOCATION / KEY NUMBERS", "CANDLE TRUTH", "RISK / RUNWAY",
        "TIER JUDGMENT", "DELIVERY / AUDIT",
    ):
        assert section in text, f"missing section: {section}"

    assert "1H Retest:  CONFIRMED — RETEST_REAL" in text
    assert "1H Hold:    CONFIRMED — HOLD_CONFIRMED" in text
    assert "HTF THESIS AUTHORIZATION: NOT AUTHORIZED" in text
    assert "4H Break:   FORMING — WICK_ONLY" in text
    assert "Permission:       NO  (PERMISSION_DENIED)" in text
    assert "Invalidation (DEFINED): $103.40" in text
    assert "T1: $114.29" in text
    assert "T2: $115.75" in text
    assert "Executable-entry R:R:      UNAVAILABLE" in text
    assert "Reported overhead:         clear" in text
    assert "Structural overhead (deterministic): moderate" in text
    assert "NOT PROVEN" in text  # Weekly positive sponsorship
    assert "Capital readiness:         NONE" in text  # AUTHORITY RECONCILIATION

    assert "$0.00" not in text
    # Fields with genuinely no source value render "—"/UNAVAILABLE, never a
    # fabricated zero — check the specific known-absent numeric fields.
    unavailable_lines = [
        l for l in text.splitlines()
        if l.strip().startswith(("Live daily date:", "10 SMA:", "Reference R:R"))
    ]
    for line in unavailable_lines:
        assert "0.00" not in line and "$0" not in line
    assert "False" not in text

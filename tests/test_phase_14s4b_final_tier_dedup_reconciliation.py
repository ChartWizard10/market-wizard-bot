"""Phase 14S.4B — final-tier dedup reconciliation regression tests.

Dedup/cooldown is execution governance, so it must evaluate the final state
that can actually be served after the SNIPE ladder and downgrade-only seal.
A stale preliminary tier may never bury an earned SNIPE or grant permission to
a result that was subsequently sealed down.
"""

from copy import deepcopy
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.scheduler import run_scan_pipeline
from tests.test_scheduler import (
    _cfg_market_hours,
    _claude_ok,
    _enriched,
    _market_results,
    _mock_bot,
    _pf_result,
    _run,
    _snipe_tiering_result,
)


TICKER = "AAPL"


def _starter_tiering_result():
    result = deepcopy(_snipe_tiering_result(TICKER))
    result["final_tier"] = "STARTER"
    result["capital_action"] = "starter_only"
    result["final_discord_channel"] = "#starter-signals"
    signal = result["final_signal"]
    signal["tier"] = "STARTER"
    signal["capital_action"] = "starter_only"
    signal["discord_channel"] = "#starter-signals"
    return result


def _state_with_recent_alert(last_tier):
    return {
        "tickers": {
            TICKER: {
                "last_alerted_at": datetime.utcnow().isoformat(),
                "last_alerted_tier": last_tier,
                "last_trigger_level": 182.50,
                "last_invalidation_level": 178.20,
            }
        },
        "meta": {},
    }


def _promote_starter_to_sniper(result, _config):
    result["final_tier"] = "SNIPE_IT"
    result["capital_action"] = "full_quality_allowed"
    result["final_discord_channel"] = "#snipe-signals"
    result["safe_for_alert"] = True
    signal = result["final_signal"]
    signal["tier"] = "SNIPE_IT"
    signal["capital_action"] = "full_quality_allowed"
    signal["discord_channel"] = "#snipe-signals"
    result["snipe_ladder"] = {
        "internal_ladder_tier": "SNIPER_A",
        "proof_state": "COMPLETE",
    }
    return result


def _downgrade_sniper_to_starter(result, _config):
    result["final_tier"] = "STARTER"
    result["capital_action"] = "starter_only"
    result["final_discord_channel"] = "#starter-signals"
    result["safe_for_alert"] = True
    signal = result["final_signal"]
    signal["tier"] = "STARTER"
    signal["capital_action"] = "starter_only"
    signal["discord_channel"] = "#starter-signals"
    result["snipe_confirmed_seal"] = {
        "applied": True,
        "original_tier": "SNIPE_IT",
        "corrected_tier": "STARTER",
        "blockers": ["test blocker"],
    }
    return result


def _identity(result, _config):
    return result


async def _send_using_final_dedup(tiering_result, dedup_decision, _bot, _config, _scan_id):
    sent = bool(dedup_decision.get("should_alert"))
    return {
        "ok": True,
        "sent": sent,
        "channel_id": 1001 if sent else None,
        "final_tier": tiering_result.get("final_tier"),
        "message_count": 1 if sent else 0,
        "error_type": None,
        "error_message": None,
        "skipped_reason": None if sent else dedup_decision.get("reason"),
    }


def _common_patches(tiering_result, ladder_side_effect, seal_side_effect):
    tickers = [TICKER]
    return (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[_claude_ok(TICKER)])),
        patch("src.scheduler.tiering.validate", return_value=tiering_result),
        patch("src.scheduler.trade_location.build_trade_location_context", return_value={}),
        patch("src.scheduler.candle_evidence.build_candle_evidence_context", return_value={}),
        patch("src.scheduler.market_data_mod.fetch_one_hour_bars", return_value=None),
        patch("src.scheduler.one_hour_entry.build_one_hour_entry_context", return_value={}),
        patch("src.scheduler.timeframe_alignment.build_timeframe_alignment_context", return_value={}),
        patch("src.scheduler.four_hour_operational.build_four_hour_operational_context", return_value={}),
        patch("src.scheduler.higher_timeframe_context.daily_bars_from_df", return_value=[]),
        patch("src.scheduler.higher_timeframe_context.build_higher_timeframe_context", return_value={}),
        patch("src.scheduler.snipe_gate_audit.build_snipe_gate_audit", return_value={}),
        patch("src.scheduler.snipe_gate_audit.reconcile_final_snipe_audit_state"),
        patch("src.scheduler.snipe_ladder_judgment.apply_ladder_arbitration", side_effect=ladder_side_effect),
        patch("src.scheduler.snipe_confirmed_seal.seal_snipe_confirmed_consistency", side_effect=seal_side_effect),
        patch("src.scheduler.score_calibration.calibrate_score", return_value=None),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(side_effect=_send_using_final_dedup)),
        patch("src.scheduler.state_store.record_alert"),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.scan_telemetry.write_scan_telemetry", return_value=True),
    )


def test_starter_to_sniper_promotion_beats_recent_starter_cooldown():
    """An earned final SNIPE must be seen as a tier improvement immediately."""
    cfg = _cfg_market_hours()
    state = _state_with_recent_alert("STARTER")
    preliminary = _starter_tiering_result()

    patches = _common_patches(preliminary, _promote_starter_to_sniper, _identity)
    for p in patches:
        p.start()
    try:
        summary = _run(run_scan_pipeline(
            [TICKER], _mock_bot(), cfg, state, "PROMPT", MagicMock()
        ))
    finally:
        for p in reversed(patches):
            p.stop()

    assert summary["alerts_sent"] == 1
    assert summary["alerts_suppressed"] == 0
    assert summary["final_tier_counts"]["SNIPE_IT"] == 1
    assert summary["final_tier_counts"]["STARTER"] == 0


def test_sealed_down_sniper_does_not_inherit_stale_tier_improvement_permission():
    """A final STARTER must be deduped as STARTER, not as the preliminary SNIPE."""
    cfg = _cfg_market_hours()
    state = _state_with_recent_alert("STARTER")
    preliminary = deepcopy(_snipe_tiering_result(TICKER))

    patches = _common_patches(preliminary, _identity, _downgrade_sniper_to_starter)
    for p in patches:
        p.start()
    try:
        summary = _run(run_scan_pipeline(
            [TICKER], _mock_bot(), cfg, state, "PROMPT", MagicMock()
        ))
    finally:
        for p in reversed(patches):
            p.stop()

    assert summary["alerts_sent"] == 0
    assert summary["alerts_suppressed"] == 1
    assert summary["final_tier_counts"]["STARTER"] == 1
    assert summary["final_tier_counts"]["SNIPE_IT"] == 0


def test_check_alert_receives_post_ladder_post_seal_state():
    """Direct contract proof: state_store.check_alert sees the executable tier."""
    cfg = _cfg_market_hours()
    state = _state_with_recent_alert("STARTER")
    preliminary = _starter_tiering_result()
    observed = {}

    def _capture_final(result, _state, _config, manual_override=False):
        observed["tier"] = result.get("final_tier")
        observed["capital"] = result.get("capital_action")
        observed["manual_override"] = manual_override
        return {"should_alert": True, "reason": "tier_improved", "dedup_key": "key"}

    patches = _common_patches(preliminary, _promote_starter_to_sniper, _identity)
    patches = patches + (patch("src.scheduler.state_store.check_alert", side_effect=_capture_final),)
    for p in patches:
        p.start()
    try:
        _run(run_scan_pipeline([TICKER], _mock_bot(), cfg, state, "PROMPT", MagicMock()))
    finally:
        for p in reversed(patches):
            p.stop()

    assert observed == {
        "tier": "SNIPE_IT",
        "capital": "full_quality_allowed",
        "manual_override": False,
    }

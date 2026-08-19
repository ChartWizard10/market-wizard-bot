"""Phase 14W — manual !analyze judgment-pipeline parity.

The operator command may bypass universe admission/cooldown, but it may never
bypass chart judgment. Once Claude returns a signal, !analyze and the universe
scanner must use the same post-tiering evidence/arbitration stack:

    trajectory -> trade location -> candle truth -> 1H -> MTF -> real 4H
    -> HTF -> SNIPE gate audit -> ladder -> seal -> audit reconcile -> calibration

Manual analysis remains outside the scan-funnel telemetry ledger.
"""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

from src.scheduler import run_analyze
from tests.test_scheduler import (
    _cfg_market_hours,
    _claude_ok,
    _enriched,
    _market_results,
    _mock_bot,
    _run,
    _snipe_tiering_result,
)


TICKER = "AAPL"


def _fetch_result():
    return _market_results([TICKER])[TICKER]


def _pf_rejected_but_preserved():
    return {
        "ticker": TICKER,
        "data_status": "OK",
        "prefilter_score": 20,
        "score_breakdown": {},
        "veto_flags": ["price_too_extended"],
        "eligible_for_claude": False,
        "rejection_reason": "hard_veto: price_too_extended",
        "ranking_reason": "",
        "key_features": {},
    }


def _starter_base():
    out = deepcopy(_snipe_tiering_result(TICKER))
    out["final_tier"] = "STARTER"
    out["capital_action"] = "starter_only"
    out["final_discord_channel"] = "#starter-signals"
    out["safe_for_alert"] = True
    out["final_signal"]["tier"] = "STARTER"
    out["final_signal"]["capital_action"] = "starter_only"
    out["final_signal"]["discord_channel"] = "#starter-signals"
    return out


def _promote_to_snipe(result, _config):
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


def _identity(result, _config):
    return result


def test_manual_analyze_runs_the_complete_post_tiering_judgment_stack():
    cfg = _cfg_market_hours()
    base = _starter_base()
    one_hour_envelope = {
        "bars": [],
        "four_hour": {"status": "OK", "bars": [{"time": "x"}]},
    }
    state = {"tickers": {TICKER: {"last_alerted_tier": "STARTER"}}, "meta": {}}
    dedup_seen = {}

    def _dedup(result, loaded_state, _config, manual_override=False):
        dedup_seen["tier"] = result.get("final_tier")
        dedup_seen["capital"] = result.get("capital_action")
        dedup_seen["state"] = loaded_state
        dedup_seen["manual"] = manual_override
        return {"should_alert": True, "reason": "manual_override", "dedup_key": "key"}

    with (
        patch("src.scheduler.market_data_mod.fetch_ticker", return_value=_fetch_result()),
        patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)),
        patch("src.scheduler.prefilter_mod.score_ticker", return_value=_pf_rejected_but_preserved()),
        patch("src.scheduler.claude_call", new=AsyncMock(return_value=_claude_ok(TICKER))),
        patch("src.scheduler.tiering.validate", return_value=base),
        patch("src.scheduler.state_store.load", return_value=state),
        patch("src.scheduler.trajectory_mod.compute", return_value={"label": "UPGRADING"}) as trajectory,
        patch("src.scheduler.trade_location.build_trade_location_context", return_value={"location_state": "mid_zone_acceptance"}) as location,
        patch("src.scheduler.candle_evidence.build_candle_evidence_context", return_value={"status": "ok"}) as candle,
        patch("src.scheduler.market_data_mod.fetch_one_hour_bars", return_value=one_hour_envelope) as fetch_1h,
        patch("src.scheduler.one_hour_entry.build_one_hour_entry_context", return_value={"status": "ENABLED", "trigger_state": "TRIGGER_LIVE"}) as one_h,
        patch("src.scheduler.timeframe_alignment.build_timeframe_alignment_context", return_value={"status": "ENABLED", "alignment_label": "FULL_STACK_ALIGNED"}) as mtf,
        patch("src.scheduler.four_hour_operational.build_four_hour_operational_context", return_value={"status": "ENABLED", "operational_location": "DEFENDABLE"}) as four_h,
        patch("src.scheduler.higher_timeframe_context.daily_bars_from_df", return_value=[{"date": "x"}]) as daily_convert,
        patch("src.scheduler.higher_timeframe_context.build_higher_timeframe_context", return_value={"data_status": "OK"}) as htf,
        patch("src.scheduler.snipe_gate_audit.build_snipe_gate_audit", return_value={"audit_label": "STARTER_ONLY_VALID"}) as gate,
        patch("src.scheduler.snipe_ladder_judgment.apply_ladder_arbitration", side_effect=_promote_to_snipe) as ladder,
        patch("src.scheduler.snipe_confirmed_seal.seal_snipe_confirmed_consistency", side_effect=_identity) as seal,
        patch("src.scheduler.snipe_gate_audit.reconcile_final_snipe_audit_state") as reconcile,
        patch("src.scheduler.score_calibration.calibrate_score", return_value={"calibrated_score": 90}) as calibration,
        patch("src.scheduler.state_store.check_alert", side_effect=_dedup),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value={"sent": False, "channel_id": None})),
        patch("src.scheduler.state_store.record_alert") as record,
        patch("src.scheduler.state_store.save") as save,
        patch("src.scheduler.scan_telemetry.write_scan_telemetry") as telemetry_write,
    ):
        result = _run(run_analyze(
            TICKER, _mock_bot(), cfg, "PROMPT", MagicMock()
        ))

    assert result["status"] == "complete"
    assert result["final_tier"] == "SNIPE_IT"
    judged = result["tiering_result"]
    assert judged["trajectory"] == {"label": "UPGRADING"}
    assert judged["trade_location"]["location_state"] == "mid_zone_acceptance"
    assert judged["candle_evidence"]["status"] == "ok"
    assert judged["one_hour_entry"]["trigger_state"] == "TRIGGER_LIVE"
    assert judged["timeframe_alignment"]["alignment_label"] == "FULL_STACK_ALIGNED"
    assert judged["four_hour_operational"]["operational_location"] == "DEFENDABLE"
    assert judged["higher_timeframe_context"]["data_status"] == "OK"
    assert judged["snipe_gate_audit"]["audit_label"] == "STARTER_ONLY_VALID"
    assert judged["snipe_ladder"]["internal_ladder_tier"] == "SNIPER_A"
    assert judged["calibration"]["calibrated_score"] == 90

    assert dedup_seen == {
        "tier": "SNIPE_IT",
        "capital": "full_quality_allowed",
        "state": state,
        "manual": True,
    }
    trajectory.assert_called_once_with(base, state["tickers"][TICKER])
    location.assert_called_once()
    candle.assert_called_once()
    fetch_1h.assert_called_once_with(TICKER, cfg)
    one_h.assert_called_once()
    mtf.assert_called_once()
    assert four_h.call_args.kwargs["four_hour_bars"] is one_hour_envelope["four_hour"]
    daily_convert.assert_called_once()
    htf.assert_called_once()
    gate.assert_called_once()
    ladder.assert_called_once()
    seal.assert_called_once()
    reconcile.assert_called_once()
    calibration.assert_called_once()
    record.assert_not_called()
    save.assert_not_called()
    telemetry_write.assert_not_called()


def test_manual_analyze_bypasses_prefilter_admission_but_preserves_veto_evidence():
    """Manual inspection forces Claude review; deterministic tiering still sees vetoes."""
    cfg = _cfg_market_hours()
    pf = _pf_rejected_but_preserved()
    seen = {}

    def _tier(signal, pf_result, _config):
        seen["pf"] = pf_result
        return _snipe_tiering_result(TICKER)

    with (
        patch("src.scheduler.market_data_mod.fetch_ticker", return_value=_fetch_result()),
        patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)),
        patch("src.scheduler.prefilter_mod.score_ticker", return_value=pf),
        patch("src.scheduler.claude_call", new=AsyncMock(return_value=_claude_ok(TICKER))) as claude,
        patch("src.scheduler.tiering.validate", side_effect=_tier),
        patch("src.scheduler._complete_candidate_judgment", side_effect=lambda t, r, e, m, c, p=None: r),
        patch("src.scheduler.state_store.load", return_value={"tickers": {}, "meta": {}}),
        patch("src.scheduler.state_store.check_alert", return_value={"should_alert": False, "reason": "unsafe_for_alert", "dedup_key": "k"}),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value={"sent": False, "channel_id": None})),
    ):
        result = _run(run_analyze(TICKER, _mock_bot(), cfg, "PROMPT", MagicMock()))

    assert result["status"] == "complete"
    assert pf["eligible_for_claude"] is False
    claude.assert_awaited_once()
    assert seen["pf"] is pf


def test_manual_analyze_and_scan_share_one_named_judgment_organ():
    """Static architecture guard against future drift between command and autoscan."""
    from pathlib import Path

    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    pipeline = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    analyze = src[src.index("async def run_analyze") :]

    assert pipeline.count("_complete_candidate_judgment(") == 1
    assert analyze.count("_complete_candidate_judgment(") == 1
    assert "state_store.check_alert(" in pipeline
    assert "state_store.check_alert(" in analyze

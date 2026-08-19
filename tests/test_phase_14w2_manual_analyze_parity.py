"""Phase 14W2 — manual !analyze judgment-pipeline parity.

Manual inspection may bypass universe admission and cooldown. It may not bypass
chart judgment. Autoscan and !analyze must share the same post-tiering organ.
"""

from contextlib import ExitStack
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
    result = deepcopy(_snipe_tiering_result(TICKER))
    result["final_tier"] = "STARTER"
    result["capital_action"] = "starter_only"
    result["final_discord_channel"] = "#starter-signals"
    result["safe_for_alert"] = True
    result["final_signal"]["tier"] = "STARTER"
    result["final_signal"]["capital_action"] = "starter_only"
    result["final_signal"]["discord_channel"] = "#starter-signals"
    return result


def _promote_to_snipe(result, _config):
    result["final_tier"] = "SNIPE_IT"
    result["capital_action"] = "full_quality_allowed"
    result["final_discord_channel"] = "#snipe-signals"
    result["safe_for_alert"] = True
    result["final_signal"]["tier"] = "SNIPE_IT"
    result["final_signal"]["capital_action"] = "full_quality_allowed"
    result["final_signal"]["discord_channel"] = "#snipe-signals"
    result["snipe_ladder"] = {
        "internal_ladder_tier": "SNIPER_A",
        "proof_state": "COMPLETE",
    }
    return result


def _identity(result, _config):
    return result


def test_manual_analyze_runs_complete_shared_judgment_before_dedup():
    cfg = _cfg_market_hours()
    base = _starter_base()
    one_hour_envelope = {
        "bars": [],
        "four_hour": {"status": "OK", "bars": [{"time": "x"}]},
    }
    state = {"tickers": {TICKER: {"last_alerted_tier": "STARTER"}}, "meta": {}}
    observed = {}

    def _dedup(result, loaded_state, _config, manual_override=False):
        observed.update(
            tier=result.get("final_tier"),
            capital=result.get("capital_action"),
            state=loaded_state,
            manual=manual_override,
        )
        return {"should_alert": True, "reason": "manual_override", "dedup_key": "key"}

    with ExitStack() as stack:
        stack.enter_context(patch("src.scheduler.market_data_mod.fetch_ticker", return_value=_fetch_result()))
        stack.enter_context(patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)))
        stack.enter_context(patch("src.scheduler.prefilter_mod.score_ticker", return_value=_pf_rejected_but_preserved()))
        stack.enter_context(patch("src.scheduler.claude_call", new=AsyncMock(return_value=_claude_ok(TICKER))))
        stack.enter_context(patch("src.scheduler.tiering.validate", return_value=base))
        stack.enter_context(patch("src.scheduler.state_store.load", return_value=state))
        trajectory = stack.enter_context(patch("src.scheduler.trajectory_mod.compute", return_value={"label": "UPGRADING"}))
        stack.enter_context(patch("src.scheduler.trade_location.build_trade_location_context", return_value={"location_state": "mid_zone_acceptance"}))
        stack.enter_context(patch("src.scheduler.candle_evidence.build_candle_evidence_context", return_value={"status": "ok"}))
        fetch_1h = stack.enter_context(patch("src.scheduler.market_data_mod.fetch_one_hour_bars", return_value=one_hour_envelope))
        stack.enter_context(patch("src.scheduler.one_hour_entry.build_one_hour_entry_context", return_value={"status": "ENABLED", "trigger_state": "TRIGGER_LIVE"}))
        stack.enter_context(patch("src.scheduler.timeframe_alignment.build_timeframe_alignment_context", return_value={"status": "ENABLED", "alignment_label": "FULL_STACK_ALIGNED"}))
        four_h = stack.enter_context(patch("src.scheduler.four_hour_operational.build_four_hour_operational_context", return_value={"status": "ENABLED", "operational_location": "DEFENDABLE"}))
        stack.enter_context(patch("src.scheduler.four_hour_operational.render_four_hour_log_line", return_value="4H"))
        stack.enter_context(patch("src.scheduler.higher_timeframe_context.daily_bars_from_df", return_value=[{"date": "x"}]))
        stack.enter_context(patch("src.scheduler.higher_timeframe_context.build_higher_timeframe_context", return_value={"data_status": "OK"}))
        stack.enter_context(patch("src.scheduler.snipe_gate_audit.build_snipe_gate_audit", return_value={"audit_label": "STARTER_ONLY_VALID"}))
        ladder = stack.enter_context(patch("src.scheduler.snipe_ladder_judgment.apply_ladder_arbitration", side_effect=_promote_to_snipe))
        seal = stack.enter_context(patch("src.scheduler.snipe_confirmed_seal.seal_snipe_confirmed_consistency", side_effect=_identity))
        reconcile = stack.enter_context(patch("src.scheduler.snipe_gate_audit.reconcile_final_snipe_audit_state"))
        calibration = stack.enter_context(patch("src.scheduler.score_calibration.calibrate_score", return_value={"calibrated_score": 90}))
        stack.enter_context(patch("src.scheduler.state_store.check_alert", side_effect=_dedup))
        stack.enter_context(patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value={"sent": False, "channel_id": None})))
        telemetry_write = stack.enter_context(patch("src.scheduler.scan_telemetry.write_scan_telemetry"))

        result = _run(run_analyze(TICKER, _mock_bot(), cfg, "PROMPT", MagicMock()))

    assert result["status"] == "complete"
    assert result["final_tier"] == "SNIPE_IT"
    assert result["tiering_result"]["snipe_ladder"]["internal_ladder_tier"] == "SNIPER_A"
    assert observed == {
        "tier": "SNIPE_IT",
        "capital": "full_quality_allowed",
        "state": state,
        "manual": True,
    }
    trajectory.assert_called_once_with(base, state["tickers"][TICKER])
    fetch_1h.assert_called_once_with(TICKER, cfg)
    assert four_h.call_args.kwargs["four_hour_bars"] is one_hour_envelope["four_hour"]
    ladder.assert_called_once()
    seal.assert_called_once()
    reconcile.assert_called_once()
    calibration.assert_called_once()
    telemetry_write.assert_not_called()


def test_manual_analyze_bypasses_admission_but_preserves_veto_evidence():
    cfg = _cfg_market_hours()
    pf = _pf_rejected_but_preserved()
    seen = {}

    def _tier(signal, pf_result, _config):
        seen["pf"] = pf_result
        return _snipe_tiering_result(TICKER)

    with ExitStack() as stack:
        stack.enter_context(patch("src.scheduler.market_data_mod.fetch_ticker", return_value=_fetch_result()))
        stack.enter_context(patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)))
        stack.enter_context(patch("src.scheduler.prefilter_mod.score_ticker", return_value=pf))
        claude = stack.enter_context(patch("src.scheduler.claude_call", new=AsyncMock(return_value=_claude_ok(TICKER))))
        stack.enter_context(patch("src.scheduler.tiering.validate", side_effect=_tier))
        stack.enter_context(patch("src.scheduler._complete_candidate_judgment", side_effect=lambda t, r, e, m, c, p=None: r))
        stack.enter_context(patch("src.scheduler.state_store.load", return_value={"tickers": {}, "meta": {}}))
        stack.enter_context(patch("src.scheduler.state_store.check_alert", return_value={"should_alert": False, "reason": "unsafe_for_alert", "dedup_key": "k"}))
        stack.enter_context(patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value={"sent": False, "channel_id": None})))
        result = _run(run_analyze(TICKER, _mock_bot(), cfg, "PROMPT", MagicMock()))

    assert result["status"] == "complete"
    assert pf["eligible_for_claude"] is False
    claude.assert_awaited_once()
    assert seen["pf"] is pf


def test_autoscan_and_manual_share_one_named_post_tiering_organ():
    from pathlib import Path

    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    pipeline = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    analyze = src[src.index("async def run_analyze") :]
    assert pipeline.count("_complete_candidate_judgment(") == 1
    assert analyze.count("_complete_candidate_judgment(") == 1
    assert pipeline.index("_complete_candidate_judgment(") < pipeline.index("state_store.check_alert(")
    assert analyze.index("_complete_candidate_judgment(") < analyze.index("state_store.check_alert(")

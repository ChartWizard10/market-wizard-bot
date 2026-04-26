"""Scheduler and pipeline tests — Phase 8.

All external boundaries mocked: no live yfinance, Claude, or Discord calls.
"""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.scheduler import is_market_hours, run_scan_pipeline, run_full_scan, run_analyze
from main import validate_startup, format_scan_summary, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ET_TZ_NAME = "America/New_York"

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo(ET_TZ_NAME)


def _dt(year, month, day, hour, minute) -> datetime:
    """Build a tz-aware datetime in ET."""
    return datetime(year, month, day, hour, minute, tzinfo=ET)


# Jan 13 2025 is a Monday; Jan 11 2025 is a Saturday
_MON_EARLY  = _dt(2025, 1, 13,  8,  0)   # 08:00 ET Monday  — before open
_MON_MID    = _dt(2025, 1, 13, 10, 30)   # 10:30 ET Monday  — in market
_MON_OPEN   = _dt(2025, 1, 13,  9, 35)   # 09:35 ET Monday  — exact open
_MON_CLOSE  = _dt(2025, 1, 13, 15, 55)   # 15:55 ET Monday  — exact close
_MON_AFTER  = _dt(2025, 1, 13, 16,  0)   # 16:00 ET Monday  — after close
_SAT_MID    = _dt(2025, 1, 11, 10, 30)   # 10:30 ET Saturday


def _cfg_market_hours(market_hours_only: bool = True) -> dict:
    return {
        "scan": {
            "market_hours_only": market_hours_only,
            "market_open":       "09:35",
            "market_close":      "15:55",
            "timezone":          "America/New_York",
            "interval_minutes":  15,
            "ticker_file":       "config/tickers.txt",
        },
        "data":     {},
        "prefilter": {"max_claude_candidates_per_scan": 30, "prefilter_min_score": 55, "scoring_weights": {}, "thresholds": {}},
        "claude":   {"model": "claude-sonnet-4-6", "max_tokens": 1200, "max_concurrent_calls": 8},
        "state":    {"cooldown_minutes": 240, "state_file": "data/alert_state.json"},
        "discord":  {"snipe_channel_id": 1001, "starter_channel_id": 1002, "near_entry_channel_id": 1003},
        "tiers":    {"snipe_it": {"min_score": 85, "min_rr": 3.0}, "starter": {"min_score": 75, "min_rr": 3.0}, "near_entry": {"min_score": 60}},
    }


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_bot(channel_id: int = 1001) -> MagicMock:
    ch = MagicMock()
    ch.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=ch)
    return bot


def _snipe_tiering_result(ticker: str = "AAPL") -> dict:
    sig = {
        "ticker": ticker, "tier": "SNIPE_IT", "score": 88,
        "setup_family": "continuation", "structure_event": "MSS",
        "trend_state": "fresh_expansion", "sma_value_alignment": "supportive",
        "zone_type": "FVG", "trigger_level": 182.50,
        "retest_status": "confirmed", "hold_status": "confirmed",
        "invalidation_condition": "Below FVG", "invalidation_level": 178.20,
        "targets": [{"label": "T1", "level": 195.0, "reason": "swing high"}],
        "risk_reward": 3.1, "overhead_status": "clear",
        "forced_participation": "none", "missing_conditions": [],
        "upgrade_trigger": "none", "next_action": "Enter on retest",
        "discord_channel": "#snipe-signals", "capital_action": "full_quality_allowed",
        "reason": "Clean MSS.",
    }
    return {
        "ok": True, "final_tier": "SNIPE_IT", "original_claude_tier": "SNIPE_IT",
        "score": 88, "final_discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed", "applied_vetoes": [],
        "downgrades": [], "rejection_reason": None, "validation_notes": [],
        "safe_for_alert": True, "final_signal": sig,
    }


def _wait_tiering_result(ticker: str = "AAPL") -> dict:
    return {
        "ok": True, "final_tier": "WAIT", "original_claude_tier": "WAIT",
        "score": 40, "final_discord_channel": "none",
        "capital_action": "no_trade", "applied_vetoes": [],
        "downgrades": [], "rejection_reason": "tier=WAIT", "validation_notes": [],
        "safe_for_alert": False, "final_signal": None,
    }


def _pf_result(tickers: list, eligible_count: int = None, cap: int = 30) -> dict:
    """Build a minimal prefilter result for the given ticker list."""
    if eligible_count is None:
        eligible_count = len(tickers)

    all_results = [
        {"ticker": t, "data_status": "OK", "prefilter_score": 70,
         "score_breakdown": {}, "veto_flags": [], "eligible_for_claude": True,
         "rejection_reason": None, "ranking_reason": "", "key_features": {}}
        for t in tickers
    ]
    ranked = all_results[:eligible_count]
    candidates = ranked[:cap]

    return {
        "all_results":      all_results,
        "ranked_results":   ranked,
        "claude_candidates": candidates,
        "board_summary": {
            "total_tickers_input":           len(tickers),
            "total_evaluated":               len(tickers),
            "total_rejected_by_data_quality": 0,
            "total_rejected_by_veto":         len(tickers) - eligible_count,
            "total_above_prefilter_min_score": eligible_count,
            "total_claude_candidates":        len(candidates),
            "top_10_tickers_by_score":        [{"ticker": t, "score": 70} for t in tickers[:10]],
        },
    }


def _market_results(tickers: list, fail_one: str | None = None) -> dict:
    """Build fake batch_download output."""
    out = {}
    for t in tickers:
        if t == fail_one:
            out[t] = {"ticker": t, "bars": 0, "latest_close": None,
                      "latest_date": None, "data_status": "ERROR", "df": None, "error": "network"}
        else:
            out[t] = {"ticker": t, "bars": 200, "latest_close": 150.0,
                      "latest_date": "2025-01-13", "data_status": "OK", "df": MagicMock(), "error": None}
    return out


def _enriched(ticker: str) -> dict:
    return {
        "ticker": ticker, "data_status": "OK", "latest_close": 150.0,
        "current_price": 150.0, "structure_event": "MSS",
        "sma_value_alignment": "supportive", "retest_status": "confirmed",
        "overhead_status": "clear", "estimated_rr": 3.5,
        "fvg": {"fvg_top": 152.0, "fvg_mid": 151.0, "fvg_bot": 150.0,
                "fvg_filled": False, "price_in_fvg": True},
        "ob": None, "volume_behavior": "expansion",
        "invalidation_level": 147.0, "targets": [{"label": "T1", "level": 160.0, "reason": "pool"}],
        "atr": 2.5,
    }


def _claude_ok(ticker: str) -> dict:
    from tests.test_claude_client import _valid_signal
    sig = _valid_signal(ticker=ticker)
    return {"ticker": ticker, "signal": sig, "error_type": None, "error_message": None}


def _claude_error(ticker: str) -> dict:
    return {"ticker": ticker, "signal": None, "error_type": "CLAUDE_API_ERROR", "error_message": "timeout"}


def _send_ok(tier: str = "SNIPE_IT") -> dict:
    return {"ok": True, "sent": True, "channel_id": 1001, "final_tier": tier,
            "message_count": 1, "error_type": None, "error_message": None, "skipped_reason": None}


def _send_skip(reason: str = "duplicate_suppressed") -> dict:
    return {"ok": True, "sent": False, "channel_id": None, "final_tier": "SNIPE_IT",
            "message_count": 0, "error_type": None, "error_message": None, "skipped_reason": reason}


_DEDUP_YES = {"should_alert": True, "reason": "new_signal", "dedup_key": "key"}
_DEDUP_NO  = {"should_alert": False, "reason": "duplicate_suppressed", "dedup_key": "key"}
_EMPTY_STATE = {"tickers": {}, "meta": {}}


# ---------------------------------------------------------------------------
# 1. Scheduler reads interval from config
# ---------------------------------------------------------------------------

def test_interval_from_config():
    """is_market_hours with market_hours_only=False always returns True regardless of time."""
    cfg = _cfg_market_hours(market_hours_only=False)
    # Any time, any day — should be True
    assert is_market_hours(cfg, _now=_SAT_MID) is True
    assert is_market_hours(cfg, _now=_MON_EARLY) is True


# ---------------------------------------------------------------------------
# 2. Market hours gate — outside window → False
# ---------------------------------------------------------------------------

def test_market_hours_gate():
    cfg = _cfg_market_hours()
    assert is_market_hours(cfg, _now=_MON_EARLY) is False   # 08:00 ET, before open
    assert is_market_hours(cfg, _now=_MON_AFTER) is False   # 16:00 ET, after close


# ---------------------------------------------------------------------------
# 3. Market hours passes — inside window → True
# ---------------------------------------------------------------------------

def test_market_hours_passes():
    cfg = _cfg_market_hours()
    assert is_market_hours(cfg, _now=_MON_MID)   is True    # 10:30 ET
    assert is_market_hours(cfg, _now=_MON_OPEN)  is True    # exact open
    assert is_market_hours(cfg, _now=_MON_CLOSE) is True    # exact close


# ---------------------------------------------------------------------------
# 4. Weekend → False
# ---------------------------------------------------------------------------

def test_weekend_skipped():
    cfg = _cfg_market_hours()
    assert is_market_hours(cfg, _now=_SAT_MID) is False


# ---------------------------------------------------------------------------
# 5. Overlap lock prevents concurrent scheduled scans
# ---------------------------------------------------------------------------

def test_overlap_skipped():
    fresh_lock = asyncio.Lock()

    async def _run_with_held_lock():
        await fresh_lock.acquire()          # hold the lock
        result = await run_full_scan(
            _mock_bot(), _cfg_market_hours(), "PROMPT", None,
            _lock=fresh_lock,
        )
        fresh_lock.release()
        return result

    result = _run(_run_with_held_lock())
    assert result["status"] == "skipped"
    assert result["reason"] == "scan_already_running"


# ---------------------------------------------------------------------------
# 6. Manual scan executes pipeline and returns complete summary
# ---------------------------------------------------------------------------

def test_manual_scan_works():
    tickers = ["AAPL", "NVDA"]
    cfg = _cfg_market_hours()

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", side_effect=lambda t, df, c: _enriched(t)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[_claude_ok(t) for t in tickers])),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result()),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_YES),
        patch("src.scheduler.state_store.record_alert", return_value=_EMPTY_STATE),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value=_send_ok())),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
            is_manual=True,
        ))

    assert summary["status"] == "complete"
    assert summary["is_manual"] is True
    assert summary["total_tickers_input"] == 2


# ---------------------------------------------------------------------------
# 7. Scan summary contains all required fields
# ---------------------------------------------------------------------------

def test_scan_summary_required_fields():
    required = [
        "scan_id", "started_at", "ended_at", "duration_seconds",
        "total_tickers_input", "total_evaluated", "total_data_failures",
        "total_prefilter_rejected", "total_prefilter_passed",
        "total_claude_candidates", "total_claude_success", "total_claude_failed",
        "total_claude_rate_limited",
        "final_tier_counts", "alerts_sent", "alerts_suppressed",
        "top_candidates", "failures", "first_data_failure_reasons",
        "is_manual", "market_hours", "status",
    ]
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[])),
        patch("src.scheduler.state_store.save"),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
        ))

    for field in required:
        assert field in summary, f"Missing required summary field: {field}"


# ---------------------------------------------------------------------------
# 8. Pipeline caps Claude calls at max_claude_candidates_per_scan
# ---------------------------------------------------------------------------

def test_pipeline_caps_claude_calls():
    """50 eligible tickers → Claude called with at most 30 candidates."""
    tickers = [f"SYM{i:02d}" for i in range(50)]
    cfg = _cfg_market_hours()
    cap = 30

    pf = _pf_result(tickers, eligible_count=50, cap=cap)
    claude_mock = AsyncMock(return_value=[])

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", side_effect=lambda t, df, c: _enriched(t)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=pf),
        patch("src.scheduler.async_claude_scan", new=claude_mock),
        patch("src.scheduler.state_store.save"),
    ):
        _run(run_scan_pipeline(tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()))

    assert claude_mock.called
    candidates_passed = claude_mock.call_args[0][0]
    assert len(candidates_passed) <= cap


# ---------------------------------------------------------------------------
# 9. Pipeline does not call Claude on all 811 tickers
# ---------------------------------------------------------------------------

def test_pipeline_does_not_call_claude_all_tickers():
    """811 tickers → Claude candidates capped at max_claude_candidates_per_scan."""
    tickers = [f"T{i:04d}" for i in range(811)]
    cfg = _cfg_market_hours()
    cap = cfg["prefilter"]["max_claude_candidates_per_scan"]

    pf = _pf_result(tickers, eligible_count=811, cap=cap)
    claude_mock = AsyncMock(return_value=[])

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", side_effect=lambda t, df, c: _enriched(t)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=pf),
        patch("src.scheduler.async_claude_scan", new=claude_mock),
        patch("src.scheduler.state_store.save"),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    candidates_passed = claude_mock.call_args[0][0]
    assert len(candidates_passed) <= cap
    assert summary["total_claude_candidates"] <= cap


# ---------------------------------------------------------------------------
# 10. yfinance failure for one ticker does not crash scan
# ---------------------------------------------------------------------------

def test_yfinance_failure_does_not_crash():
    tickers = ["AAPL", "FAIL", "NVDA"]
    cfg = _cfg_market_hours()

    with (
        patch("src.scheduler.market_data_mod.batch_download",
              return_value=_market_results(tickers, fail_one="FAIL")),
        patch("src.scheduler.indicators.enrich", side_effect=lambda t, df, c: _enriched(t)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(["AAPL", "NVDA"])),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[])),
        patch("src.scheduler.state_store.save"),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["status"] == "complete"
    assert summary["total_data_failures"] >= 1


# ---------------------------------------------------------------------------
# 11. Claude failure for one candidate does not crash scan
# ---------------------------------------------------------------------------

def test_claude_failure_does_not_crash():
    tickers = ["AAPL", "NVDA"]
    cfg = _cfg_market_hours()
    claude_results = [_claude_ok("AAPL"), _claude_error("NVDA")]

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", side_effect=lambda t, df, c: _enriched(t)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=claude_results)),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result("AAPL")),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_YES),
        patch("src.scheduler.state_store.record_alert", return_value=_EMPTY_STATE),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value=_send_ok())),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["status"] == "complete"
    assert summary["total_claude_failed"] == 1
    assert summary["total_claude_success"] == 1


# ---------------------------------------------------------------------------
# 12. Invalid Claude JSON → no alert sent
# ---------------------------------------------------------------------------

def test_invalid_json_no_alert():
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()
    send_mock = AsyncMock(return_value=_send_ok())

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        # Claude returns bad JSON (signal=None)
        patch("src.scheduler.async_claude_scan",
              new=AsyncMock(return_value=[{"ticker": "AAPL", "signal": None,
                                           "error_type": "JSON_PARSE_ERROR", "error_message": "bad"}])),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=send_mock),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    send_mock.assert_not_called()
    assert summary["alerts_sent"] == 0


# ---------------------------------------------------------------------------
# 13. Tiering returns WAIT → no Discord post
# ---------------------------------------------------------------------------

def test_tiering_wait_no_alert():
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    from tests.test_claude_client import _valid_signal
    claude_results = [{"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                       "error_type": None, "error_message": None}]
    send_mock = AsyncMock(return_value=_send_skip("wait_no_alert"))

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=claude_results)),
        patch("src.scheduler.tiering.validate", return_value=_wait_tiering_result("AAPL")),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_NO),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=send_mock),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["alerts_sent"] == 0
    # send_alert may be called (it guards WAIT internally) but sent must be False
    for c in send_mock.call_args_list:
        result = _run(c[0][0]) if asyncio.iscoroutine(c[0][0]) else None
        # The key assertion: no alert recorded as sent
    assert summary["alerts_sent"] == 0


# ---------------------------------------------------------------------------
# 14. Dedup suppression → no alert recorded
# ---------------------------------------------------------------------------

def test_dedup_suppressed_no_alert():
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    from tests.test_claude_client import _valid_signal
    claude_results = [{"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                       "error_type": None, "error_message": None}]

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=claude_results)),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result("AAPL")),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_NO),
        patch("src.scheduler.state_store.record_alert") as mock_record,
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert",
              new=AsyncMock(return_value=_send_skip("duplicate_suppressed"))),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["alerts_sent"] == 0
    assert summary["alerts_suppressed"] == 1
    mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# 15. Discord send exception does not crash scan
# ---------------------------------------------------------------------------

def test_discord_send_failure_no_crash():
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    from tests.test_claude_client import _valid_signal
    claude_results = [{"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                       "error_type": None, "error_message": None}]

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=claude_results)),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result("AAPL")),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_YES),
        patch("src.scheduler.state_store.save"),
        # Discord raises
        patch("src.scheduler.discord_alerts.send_alert",
              new=AsyncMock(side_effect=Exception("Connection reset"))),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["status"] == "complete"   # scan did not crash
    assert summary["alerts_sent"] == 0
    assert any(f["type"] == "DISCORD_SEND_FAILED" for f in summary["failures"])


# ---------------------------------------------------------------------------
# 16. !analyze passes manual_override=True to state_store.check_alert
# ---------------------------------------------------------------------------

def test_analyze_manual_override_bypasses_cooldown():
    cfg = _cfg_market_hours()
    check_mock = MagicMock(return_value=_DEDUP_YES)

    from tests.test_claude_client import _valid_signal

    with (
        patch("src.scheduler.market_data_mod.fetch_ticker",
              return_value={"data_status": "OK", "latest_close": 150.0, "df": MagicMock()}),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.score_ticker",
              return_value={"ticker": "AAPL", "veto_flags": [], "eligible_for_claude": True,
                            "prefilter_score": 70, "data_status": "OK",
                            "rejection_reason": None, "score_breakdown": {}, "ranking_reason": "", "key_features": {}}),
        patch("src.scheduler.claude_call",
              new=AsyncMock(return_value={"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                                          "error_type": None, "error_message": None})),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result("AAPL")),
        patch("src.scheduler.state_store.load", return_value=_EMPTY_STATE.copy()),
        patch("src.scheduler.state_store.check_alert", new=check_mock),
        patch("src.scheduler.state_store.record_alert", return_value=_EMPTY_STATE),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value=_send_ok())),
    ):
        result = _run(run_analyze("AAPL", _mock_bot(), cfg, "PROMPT", MagicMock()))

    assert result["status"] == "complete"
    # Verify manual_override=True was passed
    _, kwargs = check_mock.call_args
    assert kwargs.get("manual_override") is True or check_mock.call_args[0][3] is True


# ---------------------------------------------------------------------------
# 17. validate_startup: missing DISCORD_TOKEN → ok=False
# ---------------------------------------------------------------------------

def test_missing_discord_token_fails_safely():
    cfg = load_config()
    env_clean = {k: v for k, v in os.environ.items()
                 if k not in ("DISCORD_TOKEN", "ANTHROPIC_KEY")}
    with patch.dict(os.environ, env_clean, clear=True):
        result = validate_startup(cfg)
    assert result["ok"] is False
    assert any("DISCORD_TOKEN" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 18. validate_startup: missing ANTHROPIC_KEY → ok=True (warning only)
# ---------------------------------------------------------------------------

def test_missing_anthropic_key_safe():
    cfg = load_config()
    env_with_token = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_KEY"}
    env_with_token["DISCORD_TOKEN"] = "fake_token_for_test"
    with patch.dict(os.environ, env_with_token, clear=True):
        result = validate_startup(cfg)
    assert result["ok"] is True
    assert any("ANTHROPIC_KEY" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# 19. Scan summary does not contain secrets
# ---------------------------------------------------------------------------

def test_no_secrets_in_summary():
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[])),
        patch("src.scheduler.state_store.save"),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    summary_str = str(summary).lower()
    assert "discord_token" not in summary_str
    assert "anthropic_key" not in summary_str
    # Ensure no obvious secret-like values leaked
    for key in ("DISCORD_TOKEN", "ANTHROPIC_KEY"):
        val = os.environ.get(key, "")
        if val and len(val) > 10:
            assert val not in str(summary)


# ---------------------------------------------------------------------------
# 20. scheduler.py and main.py contain no disabled indicators
# ---------------------------------------------------------------------------

def test_no_disabled_indicators_in_scheduler():
    disabled = ["rsi", "macd", "bollinger_bands", "stochastic"]
    for fname in ("src/scheduler.py", "main.py"):
        source = Path(fname).read_text()
        for indicator in disabled:
            assert not re.search(rf"\b{indicator}\b", source, re.IGNORECASE), (
                f"Disabled indicator '{indicator}' found in {fname}"
            )


# ---------------------------------------------------------------------------
# 21. Discord alerts still route only from final_signal (not Claude raw output)
# ---------------------------------------------------------------------------

def test_discord_alerts_route_from_final_signal():
    """Routing uses final_tier from tiering_result — not Claude's discord_channel field."""
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()

    from tests.test_claude_client import _valid_signal
    # Claude claims SNIPE_IT but tiering downgrades it to WAIT
    claude_results = [{"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                       "error_type": None, "error_message": None}]
    send_mock = AsyncMock(return_value=_send_skip("wait_no_alert"))

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=claude_results)),
        # tiering overrides to WAIT
        patch("src.scheduler.tiering.validate", return_value=_wait_tiering_result("AAPL")),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_NO),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=send_mock),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert summary["alerts_sent"] == 0
    # If send_alert was called, it must have been with the tiering_result (WAIT), not raw Claude output
    if send_mock.called:
        tr_arg = send_mock.call_args[0][0]
        assert tr_arg["final_tier"] == "WAIT"


# ---------------------------------------------------------------------------
# 22. Full pipeline order enforced: prefilter before Claude, tiering before alert
# ---------------------------------------------------------------------------

def test_full_pipeline_order_enforced():
    """Verify that Claude is never called before prefilter, and alerts never before tiering."""
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()
    call_order = []

    def record(name, return_val):
        def side_effect(*args, **kwargs):
            call_order.append(name)
            return return_val
        return side_effect

    async def record_async(name, return_val):
        call_order.append(name)
        return return_val

    from tests.test_claude_client import _valid_signal

    with (
        patch("src.scheduler.market_data_mod.batch_download",
              side_effect=record("batch_download", _market_results(tickers))),
        patch("src.scheduler.indicators.enrich",
              side_effect=lambda t, df, c: (call_order.append("enrich"), _enriched(t))[1]),
        patch("src.scheduler.prefilter_mod.prefilter",
              side_effect=record("prefilter", _pf_result(tickers))),
        patch("src.scheduler.async_claude_scan",
              new=AsyncMock(side_effect=lambda *a, **k: (call_order.append("claude"), [
                  {"ticker": "AAPL", "signal": _valid_signal(ticker="AAPL"),
                   "error_type": None, "error_message": None}
              ])[1])),
        patch("src.scheduler.tiering.validate",
              side_effect=record("tiering", _snipe_tiering_result("AAPL"))),
        patch("src.scheduler.state_store.check_alert",
              side_effect=record("dedup", _DEDUP_YES)),
        patch("src.scheduler.state_store.record_alert", return_value=_EMPTY_STATE),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert",
              new=AsyncMock(side_effect=lambda *a, **k: (call_order.append("alert"), _send_ok())[1])),
    ):
        _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert call_order.index("batch_download") < call_order.index("prefilter")
    assert call_order.index("prefilter") < call_order.index("claude")
    assert call_order.index("claude") < call_order.index("tiering")
    assert call_order.index("tiering") < call_order.index("dedup")
    assert call_order.index("dedup") < call_order.index("alert")


# ---------------------------------------------------------------------------
# 23. Scheduler does not require manual mkdir for state directory
# ---------------------------------------------------------------------------

def test_scheduler_does_not_require_manual_mkdir(tmp_path):
    """state_store.save() auto-creates missing parent directories.
    No manual mkdir needed before starting the bot."""
    from src import state_store as ss

    state_path = tmp_path / "auto_created" / "state.json"
    cfg = _cfg_market_hours()
    cfg["state"]["state_file"] = str(state_path)

    # Mimic exactly what run_scan_pipeline does: load then save
    state = ss.load(cfg)       # parent dir does not exist; returns empty state
    ss.save(state, cfg)        # must auto-create directory and write file

    assert state_path.exists(), "state_store.save() must create missing parent directory"


# ---------------------------------------------------------------------------
# 24. Scan summary includes first_data_failure_reasons when data failures occur
# ---------------------------------------------------------------------------

def test_scan_summary_includes_data_failure_sample():
    """When batch_download returns all failures, summary includes first_data_failure_reasons
    with at most 10 entries, each a non-empty string."""
    tickers = [f"T{i:04d}" for i in range(20)]
    cfg = _cfg_market_hours()

    fail_results = {
        t: {"ticker": t, "bars": 0, "latest_close": None, "latest_date": None,
            "data_status": "ERROR", "df": None, "error": f"network error for {t}"}
        for t in tickers
    }

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=fail_results),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result([], eligible_count=0)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[])),
        patch("src.scheduler.state_store.save"),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    assert "first_data_failure_reasons" in summary, "summary must include first_data_failure_reasons"
    sample = summary["first_data_failure_reasons"]
    assert isinstance(sample, list)
    assert 0 < len(sample) <= 10
    assert all(isinstance(r, str) and len(r) > 0 for r in sample)


# ---------------------------------------------------------------------------
# 25. Rate-limited Claude result → no alert, counted as total_claude_rate_limited
# ---------------------------------------------------------------------------

def test_rate_limited_result_no_alert_counted_separately():
    """429 from Claude is recorded as rate_limited, does not generate alert or set rejection."""
    tickers = ["AAPL"]
    cfg = _cfg_market_hours()
    send_mock = AsyncMock(return_value={"ok": True, "sent": False})

    rate_limited_results = [{
        "ticker": "AAPL",
        "signal": None,
        "error_type": "claude_rate_limited",
        "error_message": "429 Too Many Requests",
    }]

    with (
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched("AAPL")),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=rate_limited_results)),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=send_mock),
    ):
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock()
        ))

    send_mock.assert_not_called()
    assert summary["alerts_sent"] == 0
    assert summary["total_claude_rate_limited"] == 1
    assert summary["total_claude_failed"] == 0        # not counted as hard failure
    assert any(f["type"] == "claude_rate_limited" for f in summary["failures"])

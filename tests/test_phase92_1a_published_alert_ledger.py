"""Phase 92-1A — immutable published-alert ledger acceptance tests.

Measurement must never become strategy. These tests prove that only successful
Discord deliveries become permanent events, that scan-time evidence is copied
without mutation, that scheduled/manual cohorts remain separable, and that a
ledger fault cannot break state continuity or scanner judgment.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src import signal_outcome_ledger as ledger
from src.scheduler import run_analyze, run_scan_pipeline
from tests.test_scheduler import (
    _DEDUP_NO,
    _DEDUP_YES,
    _EMPTY_STATE,
    _cfg_market_hours,
    _claude_ok,
    _enriched,
    _market_results,
    _mock_bot,
    _pf_result,
    _run,
    _send_ok,
    _send_skip,
    _snipe_tiering_result,
)


TICKER = "AAPL"


def _ledger_cfg(tmp_path: Path, *, enabled: bool = True) -> dict:
    return {
        "scan": {
            "timezone": "America/New_York",
            "ticker_file": str(tmp_path / "tickers.txt"),
        },
        "state": {"state_file": str(tmp_path / "alert_history.json")},
        "research_archive": {"directory": str(tmp_path / "research_archive")},
        "signal_outcomes": {
            "enabled": enabled,
            "directory": str(tmp_path / "signal_outcomes"),
        },
        "claude": {"model": "claude-opus-5"},
    }


def _rich_tiering_result() -> dict:
    result = _snipe_tiering_result(TICKER)
    result["raw_score"] = 91
    result["final_signal"].update({
        "scan_price": 150.0,
        "risk_distance": 2.0,
        "risk_distance_pct": 1.3333,
        "risk_realism_state": "clean",
        "entry_archetype": "break_retest",
        "current_acceptance": "accepted",
        "sanitized_reason": "Closed proof supports the setup.",
        "sanitized_next_action": "Honor structural invalidation.",
    })
    result["one_hour_entry"] = {
        "status": "ENABLED",
        "data_freshness": "FRESH",
        "trigger_state": "TRIGGER_LIVE",
        "score": 91,
        "score_label": "1H_TRIGGER_A_PLUS",
        "alert_truth_label": "LIVE_TRIGGER",
        "bar_context": {
            "last_closed_bar_time": "2026-08-24T19:00:00+00:00",
            "current_live_bar_time": "2026-08-24T20:00:00+00:00",
            "using_live_bar_for_confirmation": False,
        },
        "candle_truth": {
            "event_type": "BULLISH_ACCEPTANCE",
            "closed_candle_confirms": True,
        },
        "pullback_retest_hold": {
            "pullback_truth": "PULLBACK_REAL",
            "retest_truth": "RETEST_CORE_VALID",
            "hold_truth": "HOLD_CONFIRMED",
            "retest_zone_type": "FVG",
        },
        "hard_caps_applied": [],
        "downgrade_reasons": [],
    }
    result["timeframe_alignment"] = {
        "status": "ENABLED",
        "alignment_grade": "A",
        "alignment_score": 90,
        "alignment_label": "FULL_STACK_ALIGNED",
        "campaign_timeframe": {
            "timeframe": "1W", "role": "campaign_context", "state": "BULLISH",
            "blocks_trigger": False, "evidence": ["weekly trend"], "warnings": [],
        },
        "swing_timeframe": {
            "timeframe": "1D", "role": "swing_permission", "state": "PERMISSION_GRANTED",
            "blocks_trigger": False, "evidence": ["daily support"], "warnings": [],
        },
        "operational_timeframe": {
            "timeframe": "4H", "role": "operational_location", "state": "LOCATION_VALID",
            "blocks_trigger": False, "evidence": ["proxy valid"], "warnings": [],
        },
        "trigger_timeframe": {
            "timeframe": "1H", "role": "trigger_proof", "state": "TRIGGER_LIVE",
            "blocks_trigger": False, "evidence": ["closed hold"], "warnings": [],
        },
        "conflicts": [],
        "missing_context": [],
        "hard_caps_applied": [],
        "downgrade_reasons": [],
    }
    result["four_hour_operational"] = {
        "status": "ENABLED",
        "engine_version": "R4H-1",
        "authority_mode": "SHADOW_EVIDENCE_ONLY",
        "structural_state": "CONTINUATION",
        "state_confidence": "HIGH",
        "operational_location": "DEFENDABLE",
        "operational_readiness": "READY",
        "bar_context": {
            "last_closed_4h_time": "2026-08-24T17:30:00+00:00",
            "current_live_4h_time": "2026-08-24T21:30:00+00:00",
            "live_bar_available": True,
            "last_closed_source_complete": True,
            "using_live_bar_for_confirmation": False,
            "freshness_status": "FRESH",
        },
        "retest_truth": {"state": "CONFIRMED", "anchor": "FVG", "anchor_level": 149.0},
        "hold_truth": {"state": "CONFIRMED", "basis": "closed body defense"},
        "invalidation_quality": {"status": "CLEAR", "level": 148.0, "risk_distance_pct": 1.3333},
        "target_path": {"path_class": "CLEAN", "next_objective": 160.0, "distance_pct": 6.66},
        "daily_relationship": "SUPPORTS",
        "hard_failures": [],
        "soft_warnings": [],
        "missing_proofs": [],
        "proxy_comparison": {"proxy_state": "LOCATION_VALID", "agreement": "AGREE"},
    }
    result["snipe_ladder"] = {
        "internal_ladder_tier": "SNIPER_A",
        "public_signal_tier": "SNIPER_ENTRY",
        "existing_final_tier_recommendation": "SNIPE_IT",
        "capital_action_recommendation": "full_quality_allowed",
        "opportunity_lane": "SNIPER_CLEAN",
        "proof_state": "COMPLETE",
        "base_alive": True,
        "hard_failures": [],
        "starter_blockers": [],
        "sniper_only_blockers": [],
        "soft_caps": ["location acceptable but not ideal"],
        "why_this_ladder_tier": "full sequence complete; soft caps prevent A+",
        "why_not_higher": "soft caps remain",
        "why_not_lower": "full sequence complete",
        "next_promotion_proof": ["clear remaining soft caps for A+"],
        "failure_condition": ["body close below invalidation"],
    }
    result["snipe_gate_audit"] = {
        "audit_label": "SNIPE_CONFIRMED",
        "promotion_state": "PROMOTED",
        "snipe_score": 91,
        "snipe_grade": "A",
        "eligible_for_snipe_review": True,
        "blocked_gate_names": [],
        "missing_proofs": [],
        "promotion_triggers": [],
        "blocking_reasons": [],
    }
    result["candle_evidence"] = {
        "candle_context": "NO_REJECTION",
        "bar_status": "CLOSED",
    }
    return result


def _build_event(cfg: dict, **overrides) -> dict:
    args = {
        "ticker": TICKER,
        "tiering_result": _rich_tiering_result(),
        "dedup_decision": {"should_alert": True, "reason": "new_signal", "dedup_key": "AAPL|SNIPE_IT|182.50|178.20"},
        "send_result": {"sent": True, "channel_id": 1001, "message_count": 2},
        "config": cfg,
        "scan_id": "scan_20260824_201247_abc123",
        "scan_started_at": "2026-08-24T20:12:47",
        "system_prompt": "MARKET WIZARD PROMPT",
        "origin": ledger.ORIGIN_SCHEDULED_SCAN,
        "tickers": ["AAPL", "NVDA"],
        "sent_at": "2026-08-24T20:12:50+00:00",
    }
    args.update(overrides)
    return ledger.build_published_event(**args)


def test_event_copies_real_scan_truth_without_mutating_source(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    source = _rich_tiering_result()
    before = deepcopy(source)

    event = _build_event(cfg, tiering_result=source)

    assert source == before
    assert event["schema_version"] == "published_alert_event_v1"
    assert event["measurement_version"] == "PHASE92-1A"
    assert event["origin"] == "scheduled_scan"
    assert event["judgment"]["final_tier"] == "SNIPE_IT"
    assert event["judgment"]["ladder_basket"] == "SNIPER_A"
    assert event["geometry"]["scan_price"] == 150.0
    assert event["proof"]["daily_permission"] == "PERMISSION_GRANTED"
    assert event["proof"]["one_hour"]["retest_truth"] == "RETEST_CORE_VALID"
    assert event["proof"]["one_hour"]["hold_truth"] == "HOLD_CONFIRMED"
    assert event["proof"]["four_hour"]["operational_location"] == "DEFENDABLE"
    assert event["proof"]["four_hour"]["operational_readiness"] == "READY"
    assert event["proof"]["four_hour"]["bar_context"]["last_closed_4h_time"] == "2026-08-24T17:30:00+00:00"
    assert event["narrative"]["why_this_tier"] == "full sequence complete; soft caps prevent A+"
    assert event["narrative"]["next_promotion_proof"] == ["clear remaining soft caps for A+"]
    assert event["measurement_authority"] == {
        "strategy_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "outcome_authority": False,
    }
    assert len(event["event_sha256"]) == 64


def test_build_requires_successful_discord_delivery(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    with pytest.raises(ValueError, match="send_result.sent"):
        _build_event(cfg, send_result={"sent": False})


def test_append_disabled_and_unsent_never_create_files(tmp_path):
    disabled = _ledger_cfg(tmp_path, enabled=False)
    res_disabled = ledger.append_published_event(
        ticker=TICKER,
        tiering_result=_rich_tiering_result(),
        dedup_decision=_DEDUP_YES,
        send_result={"sent": True},
        config=disabled,
        scan_id="scan_x",
        scan_started_at="2026-08-24T20:00:00",
        system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert res_disabled["status"] == "disabled"
    assert not ledger.ledger_dir(disabled).exists()

    cfg = _ledger_cfg(tmp_path, enabled=True)
    res_unsent = ledger.append_published_event(
        ticker=TICKER,
        tiering_result=_rich_tiering_result(),
        dedup_decision=_DEDUP_NO,
        send_result={"sent": False},
        config=cfg,
        scan_id="scan_y",
        scan_started_at="2026-08-24T20:00:00",
        system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert res_unsent["status"] == "not_published"
    assert not ledger.ledger_dir(cfg).exists()


def test_append_is_idempotent_for_same_published_event(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    kwargs = dict(
        ticker=TICKER,
        tiering_result=_rich_tiering_result(),
        dedup_decision={"reason": "new_signal", "dedup_key": "key"},
        send_result={"sent": True, "channel_id": 1001},
        config=cfg,
        scan_id="scan_20260824_201247_abc123",
        scan_started_at="2026-08-24T20:12:47",
        system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
        tickers=[TICKER],
        sent_at="2026-08-24T20:12:50+00:00",
    )
    first = ledger.append_published_event(**kwargs)
    second = ledger.append_published_event(**kwargs)

    assert first["status"] == "appended"
    assert second["status"] == "duplicate_ignored"
    assert first["alert_id"] == second["alert_id"]
    path = Path(first["path"])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["alert_id"] == first["alert_id"]


def test_alert_id_is_globally_distinct_when_manual_scan_id_repeats_on_another_day(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    first = _build_event(
        cfg,
        scan_id="analyze_AAPL_161200",
        scan_started_at="2026-08-24T20:12:00",
        origin=ledger.ORIGIN_MANUAL_ANALYZE,
    )
    second = _build_event(
        cfg,
        scan_id="analyze_AAPL_161200",
        scan_started_at="2026-08-25T20:12:00",
        origin=ledger.ORIGIN_MANUAL_ANALYZE,
    )
    assert first["alert_id"] != second["alert_id"]


def test_naive_scheduler_timestamp_is_utc_then_converted_to_market_session(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    # 01:30 UTC on Aug 25 is still Aug 24 in New York.
    assert ledger.session_date("2026-08-25T01:30:00", cfg) == "2026-08-24"


def test_provenance_hashes_are_stable_and_sensitive(tmp_path, monkeypatch):
    cfg = _ledger_cfg(tmp_path)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    one = _build_event(cfg, system_prompt="PROMPT A", tickers=["AAPL", "NVDA"])
    two = _build_event(cfg, system_prompt="PROMPT A", tickers=["AAPL", "NVDA"])
    three = _build_event(cfg, system_prompt="PROMPT B", tickers=["AAPL", "NVDA"])
    four = _build_event(cfg, system_prompt="PROMPT A", tickers=["AAPL", "MSFT"])

    assert one["provenance"]["build_commit_sha"] == "abc123"
    assert one["provenance"]["config_sha256"] == two["provenance"]["config_sha256"]
    assert one["provenance"]["prompt_sha256"] == two["provenance"]["prompt_sha256"]
    assert one["provenance"]["universe_sha256"] == two["provenance"]["universe_sha256"]
    assert one["provenance"]["prompt_sha256"] != three["provenance"]["prompt_sha256"]
    assert one["provenance"]["universe_sha256"] != four["provenance"]["universe_sha256"]


def test_nonfinite_and_unserializable_evidence_degrades_without_breaking_json(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    source = _rich_tiering_result()
    source["final_signal"]["risk_reward"] = float("nan")
    source["candle_evidence"]["opaque"] = object()
    event = _build_event(cfg, tiering_result=source)
    assert event["geometry"]["risk_reward"] is None
    assert event["proof"]["candle_evidence"]["opaque"] is None
    json.dumps(event, allow_nan=False)


def test_malformed_existing_jsonl_does_not_destroy_next_valid_event(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    events = Path(cfg["signal_outcomes"]["directory"]) / "events"
    events.mkdir(parents=True)
    path = events / "2026-08-24.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    result = ledger.append_published_event(
        ticker=TICKER,
        tiering_result=_rich_tiering_result(),
        dedup_decision={"reason": "new_signal", "dedup_key": "unique"},
        send_result={"sent": True, "channel_id": 1001},
        config=cfg,
        scan_id="scan_20260824_210000_def456",
        scan_started_at="2026-08-24T21:00:00",
        system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
        tickers=[TICKER],
    )
    assert result["status"] == "appended"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "{not-json}"
    assert json.loads(lines[-1])["alert_id"] == result["alert_id"]


def test_path_collision_refuses_operational_or_research_storage(tmp_path):
    cfg = _ledger_cfg(tmp_path)
    cfg["signal_outcomes"]["directory"] = cfg["research_archive"]["directory"]
    assert ledger.path_collision(cfg) is True
    result = ledger.append_published_event(
        ticker=TICKER,
        tiering_result=_rich_tiering_result(),
        dedup_decision=_DEDUP_YES,
        send_result={"sent": True},
        config=cfg,
        scan_id="scan_z",
        scan_started_at="2026-08-24T20:00:00",
        system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert result["ok"] is False
    assert result["status"] == "path_collision"


def _pipeline_context(*, send_result, ledger_result, is_manual=False):
    tickers = [TICKER]
    cfg = _cfg_market_hours()
    ledger_mock = MagicMock(return_value=ledger_result)
    record_mock = MagicMock(return_value=_EMPTY_STATE)
    patches = [
        patch("src.scheduler.market_data_mod.batch_download", return_value=_market_results(tickers)),
        patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)),
        patch("src.scheduler.prefilter_mod.prefilter", return_value=_pf_result(tickers)),
        patch("src.scheduler.async_claude_scan", new=AsyncMock(return_value=[_claude_ok(TICKER)])),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result(TICKER)),
        patch("src.scheduler._complete_candidate_judgment", side_effect=lambda t, r, e, m, c, p=None: r),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_YES),
        patch("src.scheduler.state_store.record_alert", new=record_mock),
        patch("src.scheduler.state_store.save"),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value=send_result)),
        patch("src.scheduler.signal_outcome_ledger.append_published_event", new=ledger_mock),
        patch("src.scheduler.scan_telemetry.write_scan_telemetry"),
    ]
    return tickers, cfg, ledger_mock, record_mock, patches


def test_scheduled_sent_alert_is_written_to_commercial_ledger_then_state():
    tickers, cfg, ledger_mock, record_mock, patches = _pipeline_context(
        send_result=_send_ok(), ledger_result={"ok": True, "status": "appended", "alert_id": "mw_x"}
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11]:
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
            scan_id="scan_20260824_200000_test",
            is_manual=False,
        ))

    assert summary["status"] == "complete"
    assert summary["alerts_sent"] == 1
    ledger_mock.assert_called_once()
    kwargs = ledger_mock.call_args.kwargs
    assert kwargs["origin"] == ledger.ORIGIN_SCHEDULED_SCAN
    assert kwargs["scan_id"] == "scan_20260824_200000_test"
    assert kwargs["tickers"] == tickers
    assert kwargs["system_prompt"] == "PROMPT"
    record_mock.assert_called_once()


def test_manual_full_scan_is_separate_origin():
    tickers, cfg, ledger_mock, _, patches = _pipeline_context(
        send_result=_send_ok(), ledger_result={"ok": True, "status": "appended", "alert_id": "mw_x"}, is_manual=True
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11]:
        _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
            scan_id="scan_manual_test",
            is_manual=True,
        ))
    assert ledger_mock.call_args.kwargs["origin"] == ledger.ORIGIN_MANUAL_SCAN


def test_unsent_or_suppressed_alert_never_calls_commercial_ledger():
    tickers, cfg, ledger_mock, record_mock, patches = _pipeline_context(
        send_result=_send_skip("duplicate_suppressed"),
        ledger_result={"ok": True, "status": "not_published"},
    )
    # Override dedup to truthfully match the skipped send.
    patches[6] = patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_NO)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11]:
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
            scan_id="scan_unsent_test",
        ))
    assert summary["alerts_sent"] == 0
    ledger_mock.assert_not_called()
    record_mock.assert_not_called()


def test_ledger_write_failure_cannot_block_state_continuity_or_change_tier():
    tickers, cfg, ledger_mock, record_mock, patches = _pipeline_context(
        send_result=_send_ok(),
        ledger_result={"ok": False, "status": "write_error", "error": "disk full"},
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11]:
        summary = _run(run_scan_pipeline(
            tickers, _mock_bot(), cfg, _EMPTY_STATE.copy(), "PROMPT", MagicMock(),
            scan_id="scan_ledger_failure_test",
        ))
    assert summary["status"] == "complete"
    assert summary["final_tier_counts"]["SNIPE_IT"] == 1
    ledger_mock.assert_called_once()
    record_mock.assert_called_once()


def test_manual_analyze_sent_alert_is_tagged_manual_analyze_origin():
    cfg = _cfg_market_hours()
    ledger_mock = MagicMock(return_value={"ok": True, "status": "appended", "alert_id": "mw_manual"})

    with (
        patch("src.scheduler.market_data_mod.fetch_ticker", return_value=_market_results([TICKER])[TICKER]),
        patch("src.scheduler.indicators.enrich", return_value=_enriched(TICKER)),
        patch("src.scheduler.prefilter_mod.score_ticker", return_value=_pf_result([TICKER])["all_results"][0]),
        patch("src.scheduler.claude_call", new=AsyncMock(return_value=_claude_ok(TICKER))),
        patch("src.scheduler.tiering.validate", return_value=_snipe_tiering_result(TICKER)),
        patch("src.scheduler._complete_candidate_judgment", side_effect=lambda t, r, e, m, c, p=None: r),
        patch("src.scheduler.state_store.load", return_value=_EMPTY_STATE.copy()),
        patch("src.scheduler.state_store.check_alert", return_value=_DEDUP_YES),
        patch("src.scheduler.discord_alerts.send_alert", new=AsyncMock(return_value=_send_ok())),
        patch("src.scheduler.signal_outcome_ledger.append_published_event", new=ledger_mock),
        patch("src.scheduler.state_store.record_alert"),
        patch("src.scheduler.state_store.save"),
    ):
        result = _run(run_analyze(TICKER, _mock_bot(), cfg, "PROMPT", MagicMock()))

    assert result["status"] == "complete"
    assert result["alert_sent"] is True
    ledger_mock.assert_called_once()
    kwargs = ledger_mock.call_args.kwargs
    assert kwargs["origin"] == ledger.ORIGIN_MANUAL_ANALYZE
    assert kwargs["ticker"] == TICKER
    assert kwargs["system_prompt"] == "PROMPT"
    assert kwargs["scan_started_at"]


def test_production_config_activates_dedicated_commercial_ledger():
    with open("config/doctrine_config.yaml", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    assert cfg["signal_outcomes"]["enabled"] is True
    assert cfg["signal_outcomes"]["directory"] == ".state/signal_outcomes"
    assert cfg["signal_outcomes"]["directory"] != cfg["research_archive"]["directory"]
    assert cfg["signal_outcomes"]["directory"] != cfg["state"]["state_file"]

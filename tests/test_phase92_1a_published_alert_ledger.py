"""Phase 92-1A — immutable published-alert ledger acceptance tests."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src import signal_outcome_ledger as ledger


def _cfg(tmp_path, enabled=True):
    return {
        "scan": {"timezone": "America/New_York"},
        "state": {"state_file": str(tmp_path / "alert_history.json")},
        "research_archive": {"directory": str(tmp_path / "research_archive")},
        "signal_outcomes": {"enabled": enabled, "directory": str(tmp_path / "signal_outcomes")},
        "claude": {"model": "claude-opus-5"},
    }


def _tiering():
    return {
        "final_tier": "SNIPE_IT",
        "score": 91,
        "raw_score": 93,
        "capital_action": "full_quality_allowed",
        "final_discord_channel": "snipe",
        "safe_for_alert": True,
        "original_claude_tier": "SNIPE_IT",
        "final_signal": {
            "scan_price": 150.0,
            "trigger_level": 151.0,
            "invalidation_level": 148.0,
            "invalidation_condition": "acceptance below structure",
            "targets": [{"label": "T1", "level": 160.0, "reason": "prior high"}],
            "risk_reward": 3.0,
            "risk_distance": 3.0,
            "risk_distance_pct": 2.0,
            "risk_realism_state": "clean",
            "overhead_status": "clear",
            "setup_family": "BREAK_RETEST_CONTINUATION",
            "entry_archetype": "break_retest",
            "structure_event": "bos",
            "trend_state": "continuation",
            "zone_type": "FVG",
            "sma_value_alignment": "aligned",
            "current_acceptance": "accepted",
            "reason": "Complete sequence.",
            "sanitized_reason": "Complete sequence.",
            "sanitized_next_action": "Honor invalidation.",
            "missing_conditions": [],
            "upgrade_trigger": None,
        },
        "one_hour_entry": {
            "status": "ENABLED", "data_freshness": "FRESH",
            "trigger_state": "TRIGGER_LIVE", "score": 91,
            "score_label": "1H_TRIGGER_A_PLUS", "alert_truth_label": "LIVE_TRIGGER",
            "pullback_retest_hold": {
                "pullback_truth": "PULLBACK_REAL", "retest_truth": "RETEST_REAL",
                "hold_truth": "HOLD_CONFIRMED",
            },
            "candle_truth": {"event_type": "BULLISH_ACCEPTANCE", "closed_candle_confirms": True},
            "bar_context": {"last_closed_bar_time": "2026-09-11T15:00:00-04:00", "using_live_bar_for_confirmation": False},
            "hard_caps_applied": [], "downgrade_reasons": [],
        },
        "timeframe_alignment": {
            "status": "ENABLED", "alignment_grade": "A", "alignment_score": 90,
            "alignment_label": "FULL_STACK_ALIGNED",
            "campaign_timeframe": {"timeframe": "1W", "role": "campaign_context", "state": "BULLISH"},
            "swing_timeframe": {"timeframe": "1D", "role": "swing_permission", "state": "PERMISSION_GRANTED"},
            "operational_timeframe": {"timeframe": "4H", "role": "operational_location", "state": "LOCATION_VALID"},
            "trigger_timeframe": {"timeframe": "1H", "role": "trigger_proof", "state": "TRIGGER_LIVE"},
        },
        "four_hour_operational": {
            "status": "OK", "engine_version": "R4H-1", "authority_mode": "SHADOW_EVIDENCE_ONLY",
            "structural_state": "CONTINUATION", "state_confidence": "HIGH",
            "operational_location": "DEFENDABLE", "operational_readiness": "READY",
            "bar_context": {"last_closed_4h_time": "2026-09-11T16:00:00-04:00", "freshness_status": "FRESH", "using_live_bar_for_confirmation": False},
            "retest_truth": {"state": "CONFIRMED"}, "hold_truth": {"state": "CONFIRMED"},
            "invalidation_quality": {"status": "CLEAR"}, "target_path": {"path_class": "CLEAN"},
            "daily_relationship": "SUPPORTS", "hard_failures": [], "soft_warnings": [], "missing_proofs": [],
        },
        "snipe_ladder": {
            "internal_ladder_tier": "SNIPER_A", "public_signal_tier": "SNIPE_IT",
            "why_this_ladder_tier": "complete sequence", "why_not_higher": "soft cap",
            "next_promotion_proof": ["clear soft cap"], "hard_failures": [],
        },
        "snipe_gate_audit": {
            "audit_label": "SNIPE_CONFIRMED", "promotion_state": "PROMOTED",
            "blocked_gate_names": [], "missing_proofs": [],
        },
        "candle_evidence": {"bar_status": "CLOSED"},
    }


def _event(cfg, **changes):
    args = {
        "ticker": "AAPL", "tiering_result": _tiering(),
        "dedup_decision": {"should_alert": True, "reason": "new_signal", "dedup_key": "AAPL|SNIPE"},
        "send_result": {"sent": True, "channel_id": 1001, "message_count": 2},
        "config": cfg, "scan_id": "scan_20260911_150000_abc123",
        "scan_started_at": "2026-09-11T19:00:00+00:00",
        "system_prompt": "MARKET WIZARD PROMPT", "origin": ledger.ORIGIN_SCHEDULED_SCAN,
        "tickers": ["AAPL", "NVDA"], "sent_at": "2026-09-11T19:00:05+00:00",
    }
    args.update(changes)
    return ledger.build_published_event(**args)


def test_event_is_immutable_projection_and_authority_zero(tmp_path):
    cfg = _cfg(tmp_path)
    source = _tiering()
    before = deepcopy(source)
    event = _event(cfg, tiering_result=source)
    assert source == before
    assert event["schema_version"] == "published_alert_event_v1"
    assert event["judgment"]["final_tier"] == "SNIPE_IT"
    assert event["proof"]["daily_permission"] == "PERMISSION_GRANTED"
    assert event["proof"]["one_hour"]["retest_truth"] == "RETEST_REAL"
    assert event["proof"]["four_hour"]["authority_mode"] == "SHADOW_EVIDENCE_ONLY"
    assert not any(event["measurement_authority"].values())


def test_only_successful_discord_delivery_can_build_event(tmp_path):
    with pytest.raises(ValueError, match="send_result.sent"):
        _event(_cfg(tmp_path), send_result={"sent": False})


def test_invalid_chronology_is_not_fabricated(tmp_path):
    with pytest.raises(ValueError, match="scan_started_at"):
        _event(_cfg(tmp_path), scan_started_at="not-a-time")


def test_session_date_uses_market_timezone(tmp_path):
    # 01:30 UTC Sep 12 is still Sep 11 ET.
    assert ledger.session_date("2026-09-12T01:30:00+00:00", _cfg(tmp_path)) == "2026-09-11"


def test_append_is_idempotent_and_append_only(tmp_path):
    cfg = _cfg(tmp_path)
    kwargs = dict(
        ticker="AAPL", tiering_result=_tiering(),
        dedup_decision={"reason": "new_signal", "dedup_key": "key"},
        send_result={"sent": True, "channel_id": 1001}, config=cfg,
        scan_id="scan_x", scan_started_at="2026-09-11T19:00:00+00:00",
        system_prompt="P", origin=ledger.ORIGIN_SCHEDULED_SCAN,
        tickers=["AAPL"], sent_at="2026-09-11T19:00:05+00:00",
    )
    first = ledger.append_published_event(**kwargs)
    second = ledger.append_published_event(**kwargs)
    assert first["status"] == "appended"
    assert second["status"] == "duplicate_ignored"
    rows = Path(first["path"]).read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1


def test_disabled_and_unsent_do_not_write(tmp_path):
    cfg = _cfg(tmp_path, enabled=False)
    res = ledger.append_published_event(
        ticker="AAPL", tiering_result=_tiering(), dedup_decision={},
        send_result={"sent": True}, config=cfg, scan_id="x",
        scan_started_at="2026-09-11T19:00:00+00:00", system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert res["status"] == "disabled"
    assert not ledger.ledger_dir(cfg).exists()
    cfg = _cfg(tmp_path, enabled=True)
    res = ledger.append_published_event(
        ticker="AAPL", tiering_result=_tiering(), dedup_decision={},
        send_result={"sent": False}, config=cfg, scan_id="x",
        scan_started_at="2026-09-11T19:00:00+00:00", system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert res["status"] == "not_published"
    assert not ledger.ledger_dir(cfg).exists()


def test_manual_and_scheduled_origins_are_separate(tmp_path):
    cfg = _cfg(tmp_path)
    scheduled = _event(cfg, origin=ledger.ORIGIN_SCHEDULED_SCAN)
    manual = _event(cfg, origin=ledger.ORIGIN_MANUAL_ANALYZE)
    assert scheduled["origin"] != manual["origin"]
    assert scheduled["alert_id"] != manual["alert_id"]


def test_repeated_manual_scan_id_on_different_days_is_distinct(tmp_path):
    cfg = _cfg(tmp_path)
    a = _event(cfg, scan_id="analyze_AAPL_150000", scan_started_at="2026-09-11T19:00:00+00:00", origin=ledger.ORIGIN_MANUAL_ANALYZE)
    b = _event(cfg, scan_id="analyze_AAPL_150000", scan_started_at="2026-09-12T19:00:00+00:00", origin=ledger.ORIGIN_MANUAL_ANALYZE)
    assert a["alert_id"] != b["alert_id"]


def test_fingerprints_do_not_store_secrets(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg["secret"] = "SUPER_SECRET_VALUE"
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    event = _event(cfg)
    dumped = json.dumps(event)
    assert "SUPER_SECRET_VALUE" not in dumped
    assert event["provenance"]["build_commit_sha"] == "abc123"
    assert len(event["provenance"]["config_sha256"]) == 64
    assert len(event["provenance"]["strategy_cohort_sha256"]) == 64


def test_nonfinite_values_degrade_to_null(tmp_path):
    tr = _tiering()
    tr["final_signal"]["risk_reward"] = float("nan")
    event = _event(_cfg(tmp_path), tiering_result=tr)
    assert event["geometry"]["risk_reward"] is None
    json.dumps(event, allow_nan=False)


def test_path_collision_fails_closed(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["signal_outcomes"]["directory"] = cfg["research_archive"]["directory"]
    assert ledger.path_collision(cfg) is True
    result = ledger.append_published_event(
        ticker="AAPL", tiering_result=_tiering(), dedup_decision={},
        send_result={"sent": True}, config=cfg, scan_id="x",
        scan_started_at="2026-09-11T19:00:00+00:00", system_prompt="P",
        origin=ledger.ORIGIN_SCHEDULED_SCAN,
    )
    assert result["ok"] is False
    assert result["status"] == "path_collision"


def test_reader_skips_malformed_rows_and_reports_duplicates(tmp_path):
    cfg = _cfg(tmp_path)
    event = _event(cfg)
    path = ledger.events_dir(cfg) / "2026-09-11.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(event) + "\nBAD\n" + json.dumps(event) + "\n", encoding="utf-8")
    view = ledger.load_events_readonly(cfg)
    assert view["stats"]["events"] == 2
    assert view["stats"]["malformed_lines"] == 1
    assert view["stats"]["duplicate_alert_ids"] == [event["alert_id"]]


def test_commercial_ledger_has_no_retention_pruning(tmp_path):
    src = Path("src/signal_outcome_ledger.py").read_text(encoding="utf-8")
    assert "retention_days" not in src
    assert "unlink(" not in src
    assert "_prune" not in src


def test_scheduler_wires_only_after_successful_send_and_is_isolated():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    assert "from src import signal_outcome_ledger" in src
    assert "_record_published_event_isolated" in src
    sent = src.index('if send_result.get("sent"):')
    record = src.index("await _record_published_event_isolated", sent)
    assert record > sent
    helper = src[src.index("async def _record_published_event_isolated"):src.index("# Phase 14W")]
    assert "asyncio.to_thread" in helper
    assert "except Exception" in helper


def test_manual_analyze_origin_is_explicit_when_it_publishes():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    analyze = src[src.index("async def run_analyze("):]
    assert "ORIGIN_MANUAL_ANALYZE" in analyze
    assert "await _record_published_event_isolated" in analyze


def test_config_activates_separate_commercial_jurisdiction():
    import yaml
    cfg = yaml.safe_load(Path("config/doctrine_config.yaml").read_text(encoding="utf-8"))
    assert cfg["signal_outcomes"]["enabled"] is True
    assert cfg["signal_outcomes"]["directory"] == ".state/signal_outcomes"
    assert cfg["signal_outcomes"]["directory"] != cfg["research_archive"]["directory"]
    assert cfg["signal_outcomes"]["directory"] != cfg["state"]["state_file"]

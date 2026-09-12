"""Phase 92-1B/1C/1D/1E pure measurement acceptance tests."""

from copy import deepcopy

from src import backtest
from src import signal_outcome_measurement as m


def _event(alert_id="a1", tier="SNIPE_IT", origin="scheduled_scan", sent="2026-09-11T15:00:00-04:00"):
    return {
        "alert_id": alert_id,
        "ticker": "AAPL",
        "origin": origin,
        "session_date": "2026-09-11",
        "scan_started_at": sent,
        "sent_at": sent,
        "provenance": {"strategy_cohort_sha256": "cohort-A", "build_commit_sha": "abc"},
        "judgment": {"final_tier": tier},
        "geometry": {
            "scan_price": 100.0,
            "trigger_level": 101.0,
            "invalidation_level": 95.0,
            "targets": [{"label": "T1", "level": 110.0}],
            "risk_realism_state": "clean",
        },
        "proof": {
            "one_hour": {"retest_truth": "RETEST_REAL", "hold_truth": "HOLD_CONFIRMED"},
            "ladder": {"hard_failures": [], "starter_blockers": [], "sniper_only_blockers": [], "soft_caps": []},
            "snipe_gate_audit": {"blocked_gate_names": [], "missing_proofs": [], "blocking_reasons": []},
        },
    }


def _hbar(ts, o=100, h=103, l=99, c=102):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c}


def _dbar(date, o=100, h=103, l=99, c=102):
    return {"date": date, "open": o, "high": h, "low": l, "close": c}


def test_independence_views_do_not_count_realerts_as_new_capital_decisions():
    e1 = _event("a1", "STARTER", sent="2026-09-11T10:00:00-04:00")
    e2 = _event("a2", "STARTER", sent="2026-09-11T11:00:00-04:00")
    e3 = _event("a3", "SNIPE_IT", sent="2026-09-11T12:00:00-04:00")
    out = m.build_independence_views([e3, e1, e2])
    assert out["counts"]["raw"] == 3
    assert out["counts"]["tier_transitions"] == 2
    assert out["counts"]["capital_decisions"] == 1
    assert out["capital_decision_events"][0]["alert_id"] == "a1"


def test_manual_origin_is_never_mixed_into_scheduled_commercial_view():
    out = m.build_independence_views([
        _event("s", origin="scheduled_scan"),
        _event("m", origin="manual_analyze"),
    ])
    assert [x["alert_id"] for x in out["scheduled_commercial_events"]] == ["s"]
    assert [x["alert_id"] for x in out["manual_operator_events"]] == ["m"]


def test_alert_day_daily_bar_is_never_future_confirmation():
    event = _event()
    bars = [_dbar("2026-09-11", h=120), _dbar("2026-09-12", h=103)]
    out = m.evaluate_horizon(event, bars, "D1")
    assert out["bars_used"] == 1
    assert out["outcome_label"] != backtest.WIN_T1_BEFORE_INVALIDATION


def test_hourly_bar_must_be_strictly_after_publication():
    event = _event(sent="2026-09-11T15:00:00-04:00")
    bars = [
        _hbar("2026-09-11T15:00:00-04:00", h=111),
        _hbar("2026-09-11T16:00:00-04:00", h=103),
    ]
    out = m.evaluate_horizon(event, bars, "H1")
    assert out["outcome_label"] != backtest.WIN_T1_BEFORE_INVALIDATION


def test_horizon_is_pending_until_required_completed_bars_exist():
    out = m.evaluate_horizon(_event(), [_hbar("2026-09-11T16:00:00-04:00")], "H4")
    assert out["outcome_status"] == "PENDING"
    assert out["outcome_label"] is None


def test_same_bar_target_and_invalidation_is_ambiguous_not_win():
    out = m.evaluate_horizon(
        _event(),
        [_hbar("2026-09-11T16:00:00-04:00", h=111, l=94)],
        "H1",
    )
    assert out["outcome_status"] == "AMBIGUOUS"
    assert out["outcome_label"] == backtest.AMBIGUOUS_SAME_BAR
    assert out["t1_before_invalidation"] is False


def test_mfe_mae_and_r_are_preserved_on_matured_outcome():
    out = m.evaluate_horizon(
        _event(),
        [_hbar("2026-09-11T16:00:00-04:00", h=108, l=98, c=105)],
        "H1",
    )
    assert out["outcome_status"] == "MATURED"
    assert out["max_favorable_excursion"] == 8.0
    assert out["max_adverse_excursion"] == -2.0
    assert out["mfe_r"] == 1.6
    assert out["mae_r"] == -0.4
    assert out["bar_set_sha256"]


def test_all_four_predeclared_horizons_returned():
    hourly = [_hbar(f"2026-09-11T{h:02d}:00:00-04:00") for h in (16, 17, 18, 19)]
    daily = [_dbar(f"2026-09-{d:02d}") for d in (12, 13, 14, 15, 16)]
    rows = m.evaluate_all_horizons(_event(), hourly_bars=hourly, daily_bars=daily)
    assert [x["horizon"] for x in rows] == ["H1", "H4", "D1", "D5"]
    assert all(x["outcome_status"] == "MATURED" for x in rows)


def test_invalid_geometry_stays_invalid_data():
    event = _event()
    event["geometry"]["invalidation_level"] = 111.0
    out = m.evaluate_horizon(event, [_hbar("2026-09-11T16:00:00-04:00")], "H1")
    assert out["outcome_status"] == "INVALID_DATA"


def test_trajectory_records_promotion_and_blocker_resolution_without_mutation():
    a = _event("a", "NEAR_ENTRY", sent="2026-09-11T10:00:00-04:00")
    b = _event("b", "STARTER", sent="2026-09-11T11:00:00-04:00")
    a["proof"]["snipe_gate_audit"]["missing_proofs"] = ["HOLD_CONFIRMED"]
    before = deepcopy([a, b])
    links = m.build_trajectory([a, b])
    assert [a, b] == before
    assert len(links) == 1
    assert links[0]["promotion"] is True
    assert links[0]["from_tier"] == "NEAR_ENTRY"
    assert links[0]["to_tier"] == "STARTER"
    assert "HOLD_CONFIRMED" in links[0]["blockers_resolved"]


def test_new_strategy_cohort_starts_new_lifecycle():
    a = _event("a", "STARTER")
    b = _event("b", "STARTER", sent="2026-09-11T16:00:00-04:00")
    b["provenance"]["strategy_cohort_sha256"] = "cohort-B"
    views = m.build_independence_views([a, b])
    assert views["counts"]["capital_decisions"] == 2


def test_near_entry_never_gets_conventional_win_rate():
    event = _event("n", "NEAR_ENTRY")
    out = m.evaluate_horizon(event, [_hbar("2026-09-11T16:00:00-04:00", h=111)], "H1")
    report = m.summarize_performance([event], [out])
    near = report["horizons"]["H1"]["by_tier"]["NEAR_ENTRY"]
    assert near["target_first_rate"] is None
    assert near["wins"] is None
    assert report["reporting_law"]["near_entry_has_win_rate"] is False


def test_pending_and_ambiguous_are_outside_capital_win_rate_denominator():
    event = _event("s", "SNIPE_IT")
    pending = {"alert_id": "s", "horizon": "H1", "outcome_status": "PENDING", "outcome_label": None}
    ambiguous = {"alert_id": "s", "horizon": "H1", "outcome_status": "AMBIGUOUS", "outcome_label": backtest.AMBIGUOUS_SAME_BAR}
    report = m.summarize_performance([event], [pending, ambiguous])
    snipe = report["horizons"]["H1"]["by_tier"]["SNIPE_IT"]
    assert snipe["decisive_denominator"] == 0
    assert snipe["target_first_rate"] is None
    assert report["horizons"]["H1"]["pending"] == 1
    assert report["horizons"]["H1"]["ambiguous"] == 1


def test_scheduled_and_manual_outcome_reports_are_filterable():
    scheduled = _event("s", "SNIPE_IT", "scheduled_scan")
    manual = _event("m", "SNIPE_IT", "manual_analyze")
    os = m.evaluate_horizon(scheduled, [_hbar("2026-09-11T16:00:00-04:00", h=111)], "H1")
    om = m.evaluate_horizon(manual, [_hbar("2026-09-11T16:00:00-04:00", h=111)], "H1")
    report = m.summarize_performance([scheduled, manual], [os, om])
    assert report["event_count"] == 1
    assert report["horizons"]["H1"]["observations"] == 1


def test_module_is_pure_no_io_network_model_or_strategy_calls():
    from pathlib import Path
    src = Path("src/signal_outcome_measurement.py").read_text(encoding="utf-8")
    for forbidden in (
        "yfinance", "requests.", "httpx.", "open(", "write_text(", "append_published_event",
        "send_alert(", "claude_call(", "tiering.validate(", "state_store", "fetch_ticker(",
        "fetch_one_hour_bars(",
    ):
        assert forbidden not in src

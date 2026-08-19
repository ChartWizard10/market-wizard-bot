"""VELOCITY-1D — offline chronological outcome-linker regressions."""

from copy import deepcopy

from src import velocity_dataset
from src import velocity_research


def _block(**overrides):
    base = {
        "version": "VELOCITY-1C",
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "observed_at": "2026-08-19T14:00:00-04:00",
        "ready": True,
        "missing": [],
        "reference_price": 100.0,
        "reference_source": "current_price",
        "invalidation_level": 95.0,
        "target_return_pct": 8.0,
        "horizon_sessions": 5.0,
        "feasibility_status": "SUPPORTED",
        "known_path_room_pct": 12.0,
        "atr_pct": 2.1,
        "required_move_atr": 3.81,
        "final_tier": "STARTER",
        "capital_authorized_at_observation": True,
        "primary_family": "BREAK_RETEST_CONTINUATION",
        "four_hour_state": "ORDERLY_CONTINUATION",
        "four_hour_proxy_state": "BULLISH_REPAIR",
        "four_hour_proxy_agreement": "AGREE",
    }
    base.update(overrides)
    return base


def _trace(scan_id="scan_1", ticker="AAPL", **block_overrides):
    return {
        "schema_version": "14V.2",
        "scan_id": scan_id,
        "ticker": ticker,
        "trace_kind": "analyzed",
        "velocity_observation": _block(**block_overrides),
    }


def _ledger(*traces):
    return {"schema_version": "14V.2", "decision_traces": list(traces)}


def _bar(day, high=102.0, low=98.0, close=101.0, open_=100.0):
    return {"date": day, "open": open_, "high": high, "low": low, "close": close}


def _quiet_five():
    return [
        _bar("2026-08-20", 102, 98, 101),
        _bar("2026-08-21", 103, 99, 102),
        _bar("2026-08-24", 104, 99, 103),
        _bar("2026-08-25", 105, 100, 104),
        _bar("2026-08-26", 106, 100, 105),
    ]


def test_extracts_only_analyzed_traces_with_velocity_block():
    observations = velocity_dataset.extract_velocity_observations({
        "decision_traces": [
            _trace(),
            {"scan_id": "near", "ticker": "MSFT", "trace_kind": "near_cut"},
            {"scan_id": "old", "ticker": "AMD", "trace_kind": "analyzed"},
        ]
    })

    assert len(observations) == 1
    obs = observations[0]
    assert obs["scan_id"] == "scan_1"
    assert obs["ticker"] == "AAPL"
    assert obs["entry_price"] == 100.0
    assert obs["setup_family"] == "BREAK_RETEST_CONTINUATION"
    assert obs["four_hour_state"] == "ORDERLY_CONTINUATION"


def test_same_observation_day_bar_is_strictly_excluded_from_future_sessions():
    selection = velocity_dataset.select_future_daily_sessions(
        "2026-08-19T09:45:00-04:00",
        [
            _bar("2026-08-19", high=120, low=90, close=110),
            _bar("2026-08-20", high=103, low=98, close=101),
        ],
        5,
    )

    assert selection["status"] == velocity_dataset.LINK_OK
    assert selection["session_dates"] == ["2026-08-20"]
    assert selection["bars"][0]["high"] == 103.0


def test_target_first_label_uses_future_daily_sessions_only():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    bars = [
        _bar("2026-08-19", high=112, low=90, close=101),  # must be ignored
        _bar("2026-08-20", high=104, low=98, close=102),
        _bar("2026-08-21", high=109, low=99, close=108),
    ]
    linked = velocity_dataset.link_observation_to_future(obs, bars)

    assert linked["label"] == velocity_research.TARGET_FIRST
    assert linked["terminal_session"] == 2
    assert linked["future_session_dates"] == ["2026-08-20", "2026-08-21"]


def test_invalidation_first_is_preserved():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    linked = velocity_dataset.link_observation_to_future(
        obs,
        [_bar("2026-08-20", high=103, low=94, close=96)],
    )
    assert linked["label"] == velocity_research.INVALIDATION_FIRST
    assert linked["terminal_session"] == 1


def test_same_session_target_and_stop_remain_ambiguous():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    linked = velocity_dataset.link_observation_to_future(
        obs,
        [_bar("2026-08-20", high=109, low=94, close=101)],
    )
    assert linked["label"] == velocity_research.AMBIGUOUS_SAME_SESSION


def test_full_five_sessions_without_price_barrier_emits_time_barrier():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    linked = velocity_dataset.link_observation_to_future(obs, _quiet_five())

    assert linked["label"] == velocity_research.TIME_BARRIER
    assert linked["terminal_session"] == 5
    assert linked["sessions_observed"] == 5


def test_partial_future_history_is_incomplete_not_timeout():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    linked = velocity_dataset.link_observation_to_future(obs, _quiet_five()[:3])

    assert linked["label"] == velocity_research.INCOMPLETE_HORIZON
    assert linked["sessions_observed"] == 3
    assert linked["label"] != velocity_research.TIME_BARRIER


def test_unready_observation_never_gets_a_valid_market_outcome():
    obs = velocity_dataset.extract_velocity_observations(
        _ledger(_trace(ready=False, invalidation_level=None))
    )[0]
    linked = velocity_dataset.link_observation_to_future(obs, _quiet_five())

    assert linked["link_status"] == velocity_dataset.LINK_INVALID_OBSERVATION
    assert linked["label"] == velocity_research.INVALID_DATA


def test_conflicting_duplicate_daily_rows_are_not_guessed_through():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    bars = [
        _bar("2026-08-20", high=103, low=98, close=101),
        _bar("2026-08-20", high=109, low=97, close=108),
    ]
    linked = velocity_dataset.link_observation_to_future(obs, bars)

    assert linked["link_status"] == velocity_dataset.LINK_BAR_DATE_CONFLICT
    assert linked["label"] == velocity_research.INVALID_DATA


def test_identical_duplicate_daily_rows_count_once():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    row = _bar("2026-08-20", high=103, low=98, close=101)
    selection = velocity_dataset.select_future_daily_sessions(
        obs["observed_at"], [row, deepcopy(row), _bar("2026-08-21")], 5
    )

    assert selection["status"] == velocity_dataset.LINK_OK
    assert selection["session_dates"] == ["2026-08-20", "2026-08-21"]
    assert selection["duplicate_identical_rows"] == 1


def test_dataset_deduplicates_identical_scan_ticker_observations():
    trace = _trace()
    dataset = velocity_dataset.link_velocity_dataset(
        _ledger(trace, deepcopy(trace)),
        {"AAPL": _quiet_five()},
    )

    assert dataset["observation_count_raw"] == 2
    assert dataset["observation_count_unique"] == 1
    assert dataset["duplicate_identical_observations_deduped"] == 1
    assert dataset["duplicate_observation_conflicts"] == 0


def test_conflicting_duplicate_scan_ticker_observations_are_invalidated():
    left = _trace()
    right = _trace(reference_price=101.0)
    dataset = velocity_dataset.link_velocity_dataset(
        _ledger(left, right),
        {"AAPL": _quiet_five()},
    )

    assert dataset["observation_count_unique"] == 1
    assert dataset["duplicate_observation_conflicts"] == 1
    record = dataset["records"][0]
    assert record["link_status"] == velocity_dataset.LINK_DUPLICATE_OBSERVATION_CONFLICT
    assert record["label"] == velocity_research.INVALID_DATA


def test_dataset_summary_keeps_capital_and_watch_observations_separate():
    starter = _trace(scan_id="s1", ticker="AAPL", final_tier="STARTER", capital_authorized_at_observation=True)
    watch = _trace(
        scan_id="s2",
        ticker="MSFT",
        final_tier="NEAR_ENTRY",
        capital_authorized_at_observation=False,
        primary_family="SMA_CRADLE_CONTINUATION",
    )
    dataset = velocity_dataset.link_velocity_dataset(
        _ledger(starter, watch),
        {"AAPL": _quiet_five(), "MSFT": _quiet_five()},
    )
    summary = dataset["summary"]

    assert summary["total_records"] == 2
    assert summary["capital_authorized_observations"] == 1
    assert summary["watch_or_no_capital_observations"] == 1
    assert "STARTER" in summary["by_tier"]
    assert "NEAR_ENTRY" in summary["by_tier"]
    assert "BREAK_RETEST_CONTINUATION" in summary["by_setup_family"]
    assert "SMA_CRADLE_CONTINUATION" in summary["by_setup_family"]


def test_dataset_preserves_real_four_hour_and_proxy_attribution_for_later_study():
    dataset = velocity_dataset.link_velocity_dataset(
        _ledger(_trace()),
        {"AAPL": _quiet_five()},
    )
    record = dataset["records"][0]
    summary = dataset["summary"]

    assert record["four_hour_state"] == "ORDERLY_CONTINUATION"
    assert record["four_hour_proxy_state"] == "BULLISH_REPAIR"
    assert record["four_hour_proxy_agreement"] == "AGREE"
    assert "ORDERLY_CONTINUATION" in summary["by_four_hour_state"]
    assert "AGREE" in summary["by_four_hour_proxy_agreement"]


def test_linker_does_not_mutate_ledger_or_bar_payload():
    ledger = _ledger(_trace())
    bars = {"AAPL": _quiet_five()}
    ledger_before = deepcopy(ledger)
    bars_before = deepcopy(bars)

    _ = velocity_dataset.link_velocity_dataset(ledger, bars)

    assert ledger == ledger_before
    assert bars == bars_before


def test_no_ticker_bar_payload_is_explicit_invalid_data_not_timeout():
    obs = velocity_dataset.extract_velocity_observations(_ledger(_trace()))[0]
    linked = velocity_dataset.link_observation_to_future(obs, None)

    assert linked["link_status"] == velocity_dataset.LINK_NO_TICKER_BARS
    assert linked["label"] == velocity_research.INVALID_DATA
    assert linked["label"] != velocity_research.TIME_BARRIER

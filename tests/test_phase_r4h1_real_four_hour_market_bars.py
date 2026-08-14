"""Phase R4H-1 — real 4H MARKET-BAR truth (aggregation layer only).

Judgment lives in test_phase_r4h1_four_hour_operational_evidence.py. This file
proves only what the bars themselves are:

    ONE provider request, two organs.
    The afternoon operational candle is 150 minutes and says so.
    A completed window with a missing constituent is INCOMPLETE, never closed.
    Duplicate / future / unparseable constituents withhold confirmation.
    Only the currently developing bucket may be LIVE.

Every test injects `now_utc`, so the session clock never depends on when the
suite runs.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import market_data

ET = ZoneInfo("America/New_York")

RTH_STARTS = ((9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30), (15, 30))
MORNING_STARTS = RTH_STARTS[:4]
AFTERNOON_STARTS = RTH_STARTS[4:]

SESSION = (2025, 6, 11)          # Wednesday, EDT
PRIOR = (2025, 6, 10)            # Tuesday, EDT


def et(y, m, d, hour, minute) -> datetime:
    return datetime(y, m, d, hour, minute, tzinfo=ET)


def utc(y, m, d, hour, minute) -> datetime:
    return et(y, m, d, hour, minute).astimezone(timezone.utc)


def frame(rows) -> pd.DataFrame:
    """rows = [(datetime_ET, open, high, low, close, volume), ...]"""
    return pd.DataFrame(
        {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        },
        index=pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows]),
    )


def session_rows(day=SESSION, starts=RTH_STARTS, base=100.0):
    """One RTH session of distinct hourly bars."""
    rows = []
    for i, (h, m) in enumerate(starts):
        px = base + i
        rows.append((et(*day, h, m), px, px + 1.0, px - 1.0, px + 0.5, 1000.0 + 100 * i))
    return rows


def buckets(env):
    return {b["bucket_slot"]: b for b in env["bars"]}


# ===========================================================================
# 1-11 — normal session construction
# ===========================================================================

def test_01_seven_rth_source_bars_make_exactly_two_operational_buckets():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 16, 5))
    assert env["status"] == "OK"
    assert len(env["bars"]) == 2
    assert [b["bucket_slot"] for b in env["bars"]] == ["MORNING_4H", "AFTERNOON_CLOSE"]
    assert env["aggregation"] == "RTH_SESSION_ALIGNED"
    assert env["source_request_reused"] is True


def test_02_morning_source_membership_is_0930_1030_1130_1230():
    rows = session_rows()
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 16, 5))
    morning = buckets(env)["MORNING_4H"]
    assert morning["source_bar_count"] == 4
    assert morning["expected_source_bar_count"] == 4
    assert morning["source_complete"] is True
    # The bucket spans 09:30 -> 13:30 ET exactly.
    assert morning["time"] == utc(*SESSION, 9, 30).isoformat()
    assert morning["end_time"] == utc(*SESSION, 13, 30).isoformat()


def test_03_morning_ohlcv_aggregate_is_exact():
    rows = session_rows()
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 16, 5))
    m = buckets(env)["MORNING_4H"]
    src = rows[:4]
    assert m["open"] == src[0][1]
    assert m["high"] == max(r[2] for r in src)
    assert m["low"] == min(r[3] for r in src)
    assert m["close"] == src[-1][4]
    assert m["volume"] == sum(r[5] for r in src)


def test_04_morning_duration_is_240_minutes():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 16, 5))
    assert buckets(env)["MORNING_4H"]["duration_minutes"] == 240


def test_05_morning_before_1330_is_live():
    rows = session_rows(starts=MORNING_STARTS[:3])
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 12, 0))
    m = buckets(env)["MORNING_4H"]
    assert m["is_open"] is True
    assert m["status"] == "LIVE"
    assert m["confirmation_eligible"] is False


def test_06_morning_after_1330_with_complete_closed_source_is_confirmation_eligible():
    rows = session_rows(starts=MORNING_STARTS)
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 13, 35))
    m = buckets(env)["MORNING_4H"]
    assert m["is_open"] is False
    assert m["source_complete"] is True
    assert m["confirmation_eligible"] is True
    assert m["status"] == "CONFIRMED"


def test_07_afternoon_source_membership_is_1330_1430_1530():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 16, 5))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["source_bar_count"] == 3
    assert a["expected_source_bar_count"] == 3
    assert a["time"] == utc(*SESSION, 13, 30).isoformat()
    assert a["end_time"] == utc(*SESSION, 16, 0).isoformat()


def test_08_afternoon_ohlcv_aggregate_is_exact():
    rows = session_rows()
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 16, 5))
    a = buckets(env)["AFTERNOON_CLOSE"]
    src = rows[4:]
    assert a["open"] == src[0][1]
    assert a["high"] == max(r[2] for r in src)
    assert a["low"] == min(r[3] for r in src)
    assert a["close"] == src[-1][4]
    assert a["volume"] == sum(r[5] for r in src)


def test_09_afternoon_duration_is_150_minutes_and_never_claims_240():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 16, 5))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["duration_minutes"] == 150
    assert a["duration_minutes"] != 240


def test_10_afternoon_at_1555_is_live():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 15, 55))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["is_open"] is True
    assert a["status"] == "LIVE"
    assert a["confirmation_eligible"] is False
    # ...while the morning bucket is already confirmed.
    assert buckets(env)["MORNING_4H"]["confirmation_eligible"] is True


def test_11_afternoon_after_close_with_complete_source_is_confirmation_eligible():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 16, 5))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["is_open"] is False
    assert a["confirmation_eligible"] is True
    assert a["status"] == "CONFIRMED"


# ===========================================================================
# 12-15 — completeness and ambiguity
# ===========================================================================

def test_12_missing_1130_makes_the_morning_bucket_incomplete():
    starts = [(9, 30), (10, 30), (12, 30)]
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows(starts=starts)), now_utc=utc(*SESSION, 14, 0))
    m = buckets(env)["MORNING_4H"]
    assert m["source_bar_count"] == 3
    assert m["source_complete"] is False
    assert m["status"] == "INCOMPLETE"
    assert m["confirmation_eligible"] is False


def test_13_missing_1430_makes_the_afternoon_bucket_incomplete():
    starts = [(13, 30), (15, 30)]
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows(starts=starts)), now_utc=utc(*SESSION, 16, 30))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["source_complete"] is False
    assert a["confirmation_eligible"] is False
    assert a["status"] == "INCOMPLETE"


def test_14_completed_window_with_a_hole_can_never_confirm():
    """Closed clock time alone is not enough — and no synthetic bar is made."""
    starts = [(9, 30), (10, 30), (12, 30)]
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows(starts=starts)), now_utc=utc(*SESSION, 20, 0))
    m = buckets(env)["MORNING_4H"]
    assert m["is_open"] is False           # the window really did complete
    assert m["confirmation_eligible"] is False
    assert m["source_bar_count"] == 3      # no 11:30 was invented
    assert env["history"]["closed_complete_bars"] == 0


def test_15_duplicate_constituent_withholds_the_bucket():
    rows = session_rows(starts=MORNING_STARTS)
    rows.append((et(*SESSION, 10, 30), 999.0, 999.0, 999.0, 999.0, 5.0))
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 14, 0))
    m = buckets(env)["MORNING_4H"]
    assert m["status"] == "AMBIGUOUS"
    assert m["confirmation_eligible"] is False
    assert m["source_complete"] is False


def test_15b_future_dated_constituent_withholds_the_bucket():
    rows = session_rows(starts=MORNING_STARTS)
    rows.append((et(2025, 12, 31, 11, 30), 500.0, 501.0, 499.0, 500.5, 10.0))
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 14, 0))
    future = [b for b in env["bars"] if b["session_date"] == "2025-12-31"]
    assert future and future[0]["status"] == "AMBIGUOUS"
    assert future[0]["confirmation_eligible"] is False
    # The genuine session is untouched by the anomaly.
    real = [b for b in env["bars"] if b["session_date"] == "2025-06-11"]
    assert real and real[0]["confirmation_eligible"] is True
    assert real[0]["high"] < 500.0


def test_15c_unparseable_constituent_is_counted_and_never_confirmed():
    rows = session_rows(starts=MORNING_STARTS)
    df = frame(rows)
    df.index = pd.Index(list(df.index[:-1]) + ["not-a-time"], dtype=object)
    env = market_data.aggregate_four_hour_bars(df, now_utc=utc(*SESSION, 14, 0))
    assert env["history"]["source_rows_unparseable"] == 1
    assert env["status"] == "DEGRADED"
    m = buckets(env)["MORNING_4H"]
    assert m["source_bar_count"] == 3
    assert m["confirmation_eligible"] is False


def test_16_unsorted_source_rows_are_ordered_before_aggregation():
    rows = session_rows(starts=MORNING_STARTS)
    scrambled = [rows[2], rows[0], rows[3], rows[1]]
    env_a = market_data.aggregate_four_hour_bars(
        frame(scrambled), now_utc=utc(*SESSION, 14, 0))
    env_b = market_data.aggregate_four_hour_bars(
        frame(rows), now_utc=utc(*SESSION, 14, 0))
    assert buckets(env_a)["MORNING_4H"] == buckets(env_b)["MORNING_4H"]
    # open/close came from the chronological ends, not the physical ends.
    assert buckets(env_a)["MORNING_4H"]["open"] == rows[0][1]
    assert buckets(env_a)["MORNING_4H"]["close"] == rows[3][4]


def test_17_different_session_dates_never_merge():
    rows = session_rows(day=PRIOR) + session_rows(day=SESSION)
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 16, 5))
    assert len(env["bars"]) == 4
    assert env["history"]["sessions_covered"] == 2
    dates = sorted({b["session_date"] for b in env["bars"]})
    assert dates == ["2025-06-10", "2025-06-11"]
    for b in env["bars"]:
        assert b["source_bar_count"] <= b["expected_source_bar_count"]


# ===========================================================================
# 18-21 — RTH filtering and live law
# ===========================================================================

@pytest.mark.parametrize("hour,minute,label", [
    (4, 30, "premarket"), (7, 30, "premarket"), (8, 30, "premarket"),
    (16, 30, "afterhours"), (18, 30, "afterhours"),
    (2, 30, "overnight"), (23, 30, "overnight"),
])
def test_18_19_20_non_rth_rows_are_excluded(hour, minute, label):
    rows = session_rows(starts=RTH_STARTS)
    rows.append((et(*SESSION, hour, minute), 500.0, 600.0, 400.0, 550.0, 99_999.0))
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 20, 0))
    assert env["history"]["source_rows_off_session"] == 1, label
    assert len(env["bars"]) == 2          # still just the two RTH buckets
    # The excluded row's extreme prices never reach any operational candle.
    for b in env["bars"]:
        assert b["high"] != 600.0 and b["high"] < 600.0
        assert b["low"] != 400.0
        assert b["volume"] != 99_999.0
    assert sum(b["source_bar_count"] for b in env["bars"]) == len(RTH_STARTS)


def test_21_only_the_current_bucket_may_be_live():
    rows = session_rows(day=PRIOR) + session_rows(day=SESSION)
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 15, 55))
    live = [b for b in env["bars"] if b["is_open"]]
    assert len(live) == 1
    assert live[0] is env["bars"][-1]
    assert live[0]["bucket_slot"] == "AFTERNOON_CLOSE"
    assert live[0]["session_date"] == "2025-06-11"


# ===========================================================================
# 22-24 — DST and early close
# ===========================================================================

def test_22_summer_dst_edt_bucket_boundaries():
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows(day=(2025, 7, 9))), now_utc=utc(2025, 7, 9, 16, 5))
    m = buckets(env)["MORNING_4H"]
    # 09:30 EDT == 13:30 UTC, 13:30 EDT == 17:30 UTC
    assert m["time"].startswith("2025-07-09T13:30:00")
    assert m["end_time"].startswith("2025-07-09T17:30:00")


def test_23_winter_dst_est_bucket_boundaries():
    day = (2025, 1, 15)
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows(day=day)), now_utc=utc(*day, 16, 5))
    m = buckets(env)["MORNING_4H"]
    # 09:30 EST == 14:30 UTC, 13:30 EST == 18:30 UTC
    assert m["time"].startswith("2025-01-15T14:30:00")
    assert m["end_time"].startswith("2025-01-15T18:30:00")
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["end_time"].startswith("2025-01-15T21:00:00")   # 16:00 EST


def test_24_early_close_never_manufactures_a_confirmed_afternoon_candle():
    """2025-07-03 is a real 13:00 ET early close. No calendar dependency is
    added; the afternoon simply never receives 14:30/15:30, so it stays
    INCOMPLETE. Confirmation is delayed, never invented."""
    day = (2025, 7, 3)
    rows = session_rows(day=day, starts=MORNING_STARTS + ((13, 30),))
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*day, 20, 0))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["source_bar_count"] == 1
    assert a["source_complete"] is False
    assert a["confirmation_eligible"] is False
    assert buckets(env)["MORNING_4H"]["confirmation_eligible"] is True


# ===========================================================================
# 25-30 — source integrity, 1H parity, network parity
# ===========================================================================

def test_25_source_ohlcv_is_never_mutated():
    rows = session_rows()
    df = frame(rows)
    before = df.copy(deep=True)
    market_data.aggregate_four_hour_bars(df, now_utc=utc(*SESSION, 16, 5))
    pd.testing.assert_frame_equal(df, before)


def _download_frame(sessions=3):
    rows = []
    for d in range(sessions):
        day = (2025, 6, 9 + d)
        rows += session_rows(day=day, base=100.0 + d)
    return frame(rows)


CFG = {"one_hour": {"interval": "60m", "lookback_period": "1mo", "max_bars": 80}}


def test_26_one_hour_output_is_unchanged_by_r4h1():
    df = _download_frame()
    with patch("yfinance.download", return_value=df):
        env = market_data.fetch_one_hour_bars("T", CFG)
    # Every legacy key and value survives, and the 1H list is the source tail.
    for key in ("bars", "freshness", "now", "status", "error"):
        assert key in env
    assert env["status"] == "OK"
    assert len(env["bars"]) == len(df)          # under max_bars -> all rows
    assert env["bars"][0]["open"] == float(df["open"].iloc[0])
    assert env["bars"][-1]["close"] == float(df["close"].iloc[-1])
    assert all("bucket_slot" not in b for b in env["bars"])


def test_27_four_hour_uses_the_full_response_not_the_truncated_1h_tail():
    """The 1H window is deliberately tiny; 4H history must not shrink with it."""
    df = _download_frame(sessions=3)          # 21 source rows -> 6 buckets
    small = {"one_hour": {"interval": "60m", "lookback_period": "1mo", "max_bars": 7}}
    with patch("yfinance.download", return_value=df):
        env = market_data.fetch_one_hour_bars("T", small)
    assert len(env["bars"]) == 7               # 1H truncated to one session
    fh = env["four_hour"]
    assert fh["history"]["total_bars"] == 6    # 4H kept all three sessions
    assert fh["history"]["sessions_covered"] == 3
    assert fh["history"]["source_rows_seen"] == len(df)
    # Aggregating from the truncated tail would have produced only 2 buckets.
    tail_only = market_data.aggregate_four_hour_bars(df.tail(7), now_utc=None)
    assert tail_only["history"]["total_bars"] == 2
    assert fh["history"]["total_bars"] > tail_only["history"]["total_bars"]


def test_28_exactly_one_yfinance_download_serves_both_organs():
    df = _download_frame()
    with patch("yfinance.download", return_value=df) as dl:
        env = market_data.fetch_one_hour_bars("T", CFG)
    assert dl.call_count == 1
    assert env["bars"]
    assert env["four_hour"]["bars"]
    assert env["four_hour"]["source_request_reused"] is True


def test_29_empty_source_degrades_safely():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        env = market_data.fetch_one_hour_bars("T", CFG)
    assert env["status"] == "EMPTY"
    assert env["four_hour"]["status"] == "EMPTY"
    assert env["four_hour"]["bars"] == []
    assert env["four_hour"]["history"]["total_bars"] == 0


def test_30_provider_error_degrades_safely():
    with patch("yfinance.download", side_effect=RuntimeError("boom")):
        env = market_data.fetch_one_hour_bars("T", CFG)
    assert env["status"] == "ERROR"
    assert env["four_hour"]["status"] == "ERROR"
    assert env["four_hour"]["bars"] == []
    assert "boom" in (env["four_hour"]["error"] or "")


# ===========================================================================
# Source-semantics guard (section 15) and misc adversarial input
# ===========================================================================

def test_mbt1_source_timestamps_are_interval_starts():
    """The bucket schedule assumes a 60m timestamp is the interval START.
    Verified against the MBT-1 contract itself, not assumed."""
    start = utc(*SESSION, 9, 30)
    # Still open 30 minutes in, closed 61 minutes in -> the stamp is the START.
    assert market_data._resolve_newest_bar_open(start, 60, start + timedelta(minutes=30)) is True
    assert market_data._resolve_newest_bar_open(start, 60, start + timedelta(minutes=61)) is False
    # And the 15:30 bar closes with the session at 16:00, not 16:30.
    last = utc(*SESSION, 15, 30)
    assert market_data._interval_end_utc(last, 60) == utc(*SESSION, 16, 0)


def test_none_and_empty_frames_never_claim_bars():
    for arg in (None, pd.DataFrame()):
        env = market_data.aggregate_four_hour_bars(arg, now_utc=utc(*SESSION, 16, 5))
        assert env["bars"] == []
        assert env["status"] == "EMPTY"
        assert env["history"]["total_bars"] == 0


def test_naive_index_cannot_be_bucketed_and_is_reported():
    rows = session_rows()
    df = frame(rows)
    df.index = df.index.tz_localize(None)
    env = market_data.aggregate_four_hour_bars(df, now_utc=utc(*SESSION, 16, 5))
    assert env["history"]["source_rows_unparseable"] == len(rows)
    assert env["bars"] == []
    assert env["status"] == "DEGRADED"


def test_partial_live_source_bar_keeps_its_bucket_open():
    """The 15:30 source bar is still forming at 15:45, so the afternoon bucket
    is live even though every expected constituent is present."""
    env = market_data.aggregate_four_hour_bars(
        frame(session_rows()), now_utc=utc(*SESSION, 15, 45))
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["source_complete"] is True
    assert a["is_open"] is True
    assert a["confirmation_eligible"] is False


# ===========================================================================
# PHASE R4H-1A — latest-bucket health (Defect A, market-bar layer)
#
# An older good candle does not make the latest missing candle healthy.
# "Historical evidence exists" and "the latest expected evidence is healthy"
# are two different facts, and the envelope must report both.
# ===========================================================================

MISSING_1430 = [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (15, 30)]


def _env(starts, hour, minute):
    return market_data.aggregate_four_hour_bars(
        frame(session_rows(starts=starts)), now_utc=utc(*SESSION, hour, minute))


def test_a1_missing_1430_after_close_makes_the_latest_bucket_incomplete():
    env = _env(MISSING_1430, 16, 5)
    b = buckets(env)
    assert b["MORNING_4H"]["status"] == "CONFIRMED"
    assert b["MORNING_4H"]["confirmation_eligible"] is True
    assert b["AFTERNOON_CLOSE"]["status"] == "INCOMPLETE"
    assert b["AFTERNOON_CLOSE"]["confirmation_eligible"] is False
    assert env["latest_bucket_status"] == "INCOMPLETE"
    assert env["latest_bucket_confirmation_eligible"] is False
    assert env["latest_bucket_time"] == utc(*SESSION, 13, 30).isoformat()


def test_a2_missing_1430_degrades_the_envelope_despite_a_confirmed_morning():
    env = _env(MISSING_1430, 16, 5)
    assert env["status"] == "DEGRADED"
    # The historical confirmation is still counted — it is simply not health.
    assert env["history"]["closed_complete_bars"] == 1
    assert env["history"]["total_bars"] == 2


def test_a7_a_complete_session_stays_healthy():
    env = _env(list(RTH_STARTS), 16, 5)
    assert env["status"] == "OK"
    assert env["latest_bucket_status"] == "CONFIRMED"
    assert env["latest_bucket_confirmation_eligible"] is True


def test_a8_a_live_current_bucket_is_not_degraded_for_still_forming():
    env = _env(list(RTH_STARTS), 15, 55)
    assert env["latest_bucket_status"] == "LIVE"
    assert env["latest_bucket_confirmation_eligible"] is False
    assert env["status"] == "OK"          # provisional, not degraded
    assert buckets(env)["MORNING_4H"]["confirmation_eligible"] is True


def test_a8b_a_bucket_that_has_not_begun_is_not_falsely_degraded():
    """At 12:00 the afternoon window has not started, so its absence is
    legitimate — the morning bucket is the latest EXPECTED evidence."""
    env = _env([(9, 30), (10, 30), (11, 30)], 12, 0)
    assert env["latest_bucket_status"] == "LIVE"
    assert env["latest_bucket_time"] == utc(*SESSION, 9, 30).isoformat()


def test_a8c_a_completed_window_that_produced_no_bar_is_missing():
    """The afternoon window completed and delivered nothing at all — that is
    missing evidence, not a healthy chart."""
    env = _env(list(MORNING_STARTS), 16, 5)
    assert env["latest_bucket_status"] == "MISSING"
    assert env["latest_bucket_time"] == utc(*SESSION, 13, 30).isoformat()
    assert env["latest_bucket_confirmation_eligible"] is False
    assert env["status"] == "DEGRADED"
    assert buckets(env)["MORNING_4H"]["confirmation_eligible"] is True


def test_a9_early_close_degradation_remains_conservative():
    day = (2025, 7, 3)
    rows = session_rows(day=day, starts=list(MORNING_STARTS) + [(13, 30)])
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*day, 20, 0))
    assert env["latest_bucket_status"] == "INCOMPLETE"
    assert env["status"] == "DEGRADED"
    a = buckets(env)["AFTERNOON_CLOSE"]
    assert a["confirmation_eligible"] is False
    assert buckets(env)["MORNING_4H"]["confirmation_eligible"] is True


def test_a_ambiguous_latest_bucket_also_degrades():
    rows = session_rows(starts=list(RTH_STARTS))
    rows.append((et(*SESSION, 14, 30), 999.0, 999.0, 999.0, 999.0, 5.0))
    env = market_data.aggregate_four_hour_bars(frame(rows), now_utc=utc(*SESSION, 16, 5))
    assert env["latest_bucket_status"] == "AMBIGUOUS"
    assert env["status"] == "DEGRADED"


def test_a_empty_and_error_envelopes_carry_the_new_provenance():
    for env in (market_data.aggregate_four_hour_bars(None, now_utc=utc(*SESSION, 16, 5)),
                market_data._empty_four_hour("now", "ERROR", "boom")):
        assert env["latest_bucket_status"] == "NONE"
        assert env["latest_bucket_time"] is None
        assert env["latest_bucket_confirmation_eligible"] is False

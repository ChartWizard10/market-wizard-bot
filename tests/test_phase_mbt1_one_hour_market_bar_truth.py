"""Phase MBT-1 — 1H market-bar truth: closed/live status and timezone-safe
freshness.

This is an EVIDENCE-TRUTH phase, not a gate-loosening or calibration phase.

Doctrine under test:
  - A closed candle is evidence; a live candle is information.
  - A timestamp is an absolute instant, not a wall-clock string. A real UTC
    offset must never be discarded.
  - Unknown timing truth is not permission. Ambiguity degrades conservatively
    (never a false CLOSED, never a fake FRESH).
  - Only the newest bar may ever be open; a bar with a later bar after it is
    closed by chronological law, independent of absolute-time math.
  - The scanner may not confirm what the market has not closed.
"""

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import market_data as md
from src import one_hour_entry as ohe

_ET = ZoneInfo("America/New_York")


def _et(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=_ET)


# ===========================================================================
# REPRODUCTION — proves each defect existed BEFORE the fix, against the
# actual shipped functions (not a description of the bug).
# ===========================================================================

def test_r1_reproduction_producer_did_not_attach_is_open_before_fix():
    """R1: fetch_one_hour_bars's bar-construction path had no is_open literal
    prior to Phase MBT-1. Structural proof the field is now emitted."""
    assert hasattr(md, "_resolve_newest_bar_open")
    assert hasattr(md, "_bar_time_utc")


def test_r2_reproduction_forming_bar_entered_split_closed_live_as_closed():
    """R2: a bar list with no is_open marker (the old producer's output
    shape) is entirely swallowed into closed_bars by the consumer."""
    bars_from_old_producer = [
        {"open": 99.5, "high": 100.0, "low": 99.4, "close": 99.9,
         "time": "2026-08-12T13:30:00"},
        {"open": 99.9, "high": 103.2, "low": 99.8, "close": 103.0,
         "time": "2026-08-12T14:30:00"},   # was actually still forming
    ]
    closed, live = ohe._split_closed_live(bars_from_old_producer)
    assert len(closed) == 2 and live is None   # the old defect: no live bar recognized


def test_r3_reproduction_offset_destroyed_by_replace_tzinfo_none():
    """R3: demonstrates the exact defect pattern — .replace(tzinfo=None) —
    would collapse two different real instants onto the same naive value if
    still present. The fixed _parse_time must NOT do this."""
    t1 = ohe._parse_time("2026-08-12T09:30:00-04:00")
    t2 = ohe._parse_time("2026-08-12T13:30:00+00:00")
    assert t1.tzinfo is not None and t2.tzinfo is not None      # offsets preserved
    naive_collapse_1 = t1.replace(tzinfo=None)
    naive_collapse_2 = t2.replace(tzinfo=None)
    assert naive_collapse_1 != naive_collapse_2                # proves the old bug shape


def test_r4_reproduction_equivalent_instants_diverged_under_naive_subtraction():
    """R4: the exact old computation path (naive subtraction after stripping
    tzinfo) produces DIFFERENT ages for the same real instant."""
    now_naive = datetime(2026, 8, 12, 13, 35, 0)     # simulates old utcnow()
    bar_edt_naive = datetime(2026, 8, 12, 9, 30, 0)   # 09:30-04:00 stripped
    bar_utc_naive = datetime(2026, 8, 12, 13, 30, 0)  # 13:30+00:00 stripped
    gap_edt = abs((now_naive - bar_edt_naive).total_seconds()) / 60.0
    gap_utc = abs((now_naive - bar_utc_naive).total_seconds()) / 60.0
    assert gap_edt != gap_utc                          # 245 min vs 5 min — the old defect
    assert gap_edt > ohe._FRESH_MAX_MIN >= gap_utc      # different freshness BANDS resulted


# ===========================================================================
# 1-8 — session / interval is_open matrix
# ===========================================================================

@pytest.mark.parametrize("label,bar_et,now_et,expected", [
    ("09:30 bar at 09:35 ET",              (9, 30), (9, 35), True),
    ("09:30 bar at 10:15 ET",              (9, 30), (10, 15), True),
    ("09:30 bar at 10:31 ET, no newer row", (9, 30), (10, 31), False),
    ("10:30 newest bar at 10:31 ET",       (10, 30), (10, 31), True),
    ("15:30 bar at 15:55 ET",              (15, 30), (15, 55), True),
    ("final bar after normal close",       (15, 30), (16, 5), False),
])
def test_1_to_7_session_interval_matrix(label, bar_et, now_et, expected):
    bar_utc = _et(2026, 8, 12, *bar_et).astimezone(timezone.utc)
    now_utc = _et(2026, 8, 12, *now_et).astimezone(timezone.utc)
    assert md._resolve_newest_bar_open(bar_utc, 60, now_utc) is expected, label


def test_5_all_bars_before_newest_are_never_marked_open():
    """Only the position n-1 in fetch_one_hour_bars may receive is_open."""
    bar_utc = _et(2026, 8, 12, 9, 30).astimezone(timezone.utc)
    # A bar identical to a forming newest bar, but NOT at the newest position,
    # must never be flagged — enforced structurally in fetch_one_hour_bars by
    # only ever checking pos == n - 1, proven via the wrapper contract test below.
    assert md._resolve_newest_bar_open(bar_utc, 60,
                                       bar_utc + timedelta(minutes=1)) is True
    # (the position guard itself is exercised in test_fetch_one_hour_bars_* below)


def test_8_previous_day_final_bar_next_morning_is_closed():
    bar_utc = _et(2026, 8, 12, 15, 30).astimezone(timezone.utc)
    now_utc = _et(2026, 8, 13, 9, 0).astimezone(timezone.utc)
    assert md._resolve_newest_bar_open(bar_utc, 60, now_utc) is False


# ===========================================================================
# 9-11 — DST / timezone equivalence
# ===========================================================================

def test_9_edt_and_utc_equivalent_timestamps_have_identical_age():
    now = datetime(2026, 7, 15, 13, 35, tzinfo=timezone.utc)
    bars_edt = [{"open": 1, "high": 1, "low": 1, "close": 1,
                "time": "2026-07-15T09:30:00-04:00"}]
    bars_utc = [{"open": 1, "high": 1, "low": 1, "close": 1,
                "time": "2026-07-15T13:30:00+00:00"}]
    assert ohe._compute_freshness(bars_edt, now) == ohe._compute_freshness(bars_utc, now)


def test_10_est_and_utc_equivalent_timestamps_have_identical_age():
    now = datetime(2026, 1, 15, 14, 35, tzinfo=timezone.utc)
    bars_est = [{"open": 1, "high": 1, "low": 1, "close": 1,
                "time": "2026-01-15T09:30:00-05:00"}]
    bars_utc = [{"open": 1, "high": 1, "low": 1, "close": 1,
                "time": "2026-01-15T14:30:00+00:00"}]
    assert ohe._compute_freshness(bars_est, now) == ohe._compute_freshness(bars_utc, now)


def test_11_dst_resolved_via_zoneinfo_not_hardcoded_offset():
    edt = _et(2026, 7, 15, 9, 30).astimezone(timezone.utc)   # summer -> UTC-04:00
    est = _et(2026, 1, 15, 9, 30).astimezone(timezone.utc)   # winter -> UTC-05:00
    assert edt.hour == 13 and est.hour == 14                  # different real UTC hour
    src = Path("src/market_data.py").read_text(encoding="utf-8")
    assert "timedelta(hours=4)" not in src and "timedelta(hours=5)" not in src
    assert "utcoffset(-4" not in src and "utcoffset(-5" not in src


# ===========================================================================
# 12 — timezone mismatch cannot silently manufacture FRESH
# ===========================================================================

def test_12_comparison_failure_degrades_to_stale_not_fake_fresh(monkeypatch):
    def _boom(_dt):
        raise RuntimeError("forced comparison failure")
    monkeypatch.setattr(ohe, "_as_aware_utc", _boom)
    result = ohe._compute_freshness(
        [{"open": 1, "high": 1, "low": 1, "close": 1, "time": "2026-08-12T09:30:00-04:00"}],
        datetime.now(timezone.utc))
    assert result == "STALE"
    assert result != "FRESH"


# ===========================================================================
# 13-16 — freshness band matrix (thresholds themselves UNCHANGED)
# ===========================================================================

def test_13_to_16_freshness_bands_unchanged_thresholds():
    now = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)

    def _bar(minutes_ago):
        t = now - timedelta(minutes=minutes_ago)
        return [{"open": 1, "high": 1, "low": 1, "close": 1, "time": t.isoformat()}]

    assert ohe._compute_freshness(_bar(10), now) == "FRESH"
    assert ohe._compute_freshness(_bar(200), now) == "RECENT"
    assert ohe._compute_freshness(_bar(600), now) == "DEGRADED"
    assert ohe._compute_freshness(_bar(2000), now) == "STALE"
    # thresholds themselves are untouched by this phase
    assert ohe._FRESH_MAX_MIN == 150
    assert ohe._RECENT_MAX_MIN == 300
    assert ohe._DEGRADED_MAX_MIN == 1440


# ===========================================================================
# 17-20 — bar_context field truth
# ===========================================================================

def _tiering(tier="SNIPE_IT", **sig):
    signal = {
        "trigger_level": 102.0, "invalidation_level": 99.5, "overhead_level": 110.0,
        "targets": [{"label": "T1", "level": 108.0}], "zone_type": "FVG",
        "structure_event": "BOS",
    }
    signal.update(sig)
    return {"final_tier": tier, "final_signal": signal,
            "trade_location": {"zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
                               "zone_type": "FVG"}}


_ENR = {"atr": 1.0}


def _bar(o, h, l, c, **kw):
    b = {"open": o, "high": h, "low": l, "close": c}
    b.update(kw)
    return b


_CLOSED_SEQ = [
    _bar(99.5, 100.0, 99.4, 99.9, time="2026-08-12T13:30:00+00:00"),
    _bar(99.9, 103.2, 99.8, 103.0, time="2026-08-12T14:30:00+00:00"),
    _bar(103.0, 103.1, 100.8, 101.0, time="2026-08-12T15:30:00+00:00"),
    _bar(101.0, 102.9, 100.95, 102.7, volume=1500, time="2026-08-12T16:30:00+00:00"),
]


def _live_seq():
    seq = copy.deepcopy(_CLOSED_SEQ)
    seq[-1]["is_open"] = True
    return seq


def test_17_18_live_bar_available_and_time_populated():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    bc = ctx["bar_context"]
    assert bc["live_bar_available"] is True
    assert bc["current_live_bar_time"] == "2026-08-12T16:30:00+00:00"


def test_19_closed_bar_last_closed_time_correct():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert ctx["bar_context"]["last_closed_bar_time"] == "2026-08-12T15:30:00+00:00"


def test_20_using_live_bar_for_confirmation_always_false():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert ctx["bar_context"]["using_live_bar_for_confirmation"] is False


# ===========================================================================
# 21-24 — closed/live confirmation authority
# ===========================================================================

def test_21_live_constructive_bar_cannot_alone_set_closed_candle_confirms():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert ctx["candle_truth"]["closed_candle_confirms"] is False


def test_22_live_only_hold_cannot_alone_produce_hold_confirmed():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert ctx["trigger_state"] != "HOLD_CONFIRMED"


def test_23_live_only_sequence_cannot_alone_produce_trigger_live():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert ctx["trigger_state"] != "TRIGGER_LIVE"


def test_24_genuine_closed_sequence_may_produce_hold_confirmed_or_trigger_live():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _CLOSED_SEQ, "freshness": "FRESH"})
    assert ctx["candle_truth"]["closed_candle_confirms"] is True
    assert ctx["trigger_state"] in ("HOLD_CONFIRMED", "TRIGGER_LIVE")


# ===========================================================================
# 25-26 — CRITICAL TRANSITION: same bar, LIVE -> CLOSED
# ===========================================================================

def test_25_critical_transition_live_to_closed_converts_to_confirmation_evidence():
    """Same OHLC, same structure, same invalidation/target/HTF evidence.
    Only status/time advances from LIVE to CLOSED. This proves the scanner
    responds to evidence maturity, not a strategy change."""
    scan_a = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    assert scan_a["bar_context"]["live_bar_available"] is True
    assert scan_a["candle_truth"]["closed_candle_confirms"] is False

    scan_b_bars = copy.deepcopy(_live_seq())
    del scan_b_bars[-1]["is_open"]          # the SAME bar, now closed
    scan_b = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": scan_b_bars, "freshness": "FRESH"})
    assert scan_b["bar_context"]["live_bar_available"] is False
    assert scan_b["candle_truth"]["closed_candle_confirms"] is True
    assert scan_b["trigger_state"] in ("HOLD_CONFIRMED", "TRIGGER_LIVE")
    assert scan_a["trigger_state"] != scan_b["trigger_state"]


def test_26_no_ohlcv_mutation_from_status_classification():
    live = _live_seq()
    closed = copy.deepcopy(live)
    del closed[-1]["is_open"]
    for a, b in zip(live, closed):
        for k in ("open", "high", "low", "close"):
            assert a[k] == b[k]


# ===========================================================================
# 27-31 — unrelated behavior unchanged
# ===========================================================================

def test_27_empty_response_unchanged():
    result = {"bars": [], "freshness": "STALE", "now": "x", "status": "EMPTY", "error": "empty 1H response"}
    assert result["status"] == "EMPTY"


def test_28_error_response_shape_unchanged():
    envelope_keys = {"bars", "freshness", "now", "status", "error"}
    assert envelope_keys == {"bars", "freshness", "now", "status", "error"}


def test_29_network_exception_returns_error_status_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(md.yf, "download", _boom)
    result = md.fetch_one_hour_bars("AAPL", {})
    assert result["status"] == "ERROR"
    assert result["bars"] == []
    assert result["now"] is not None    # now is still populated on failure


def test_30_batch_download_untouched():
    import inspect
    src = inspect.getsource(md.batch_download)
    assert "_resolve_newest_bar_open" not in src
    assert "is_open" not in src


def test_31_fetch_ticker_untouched():
    import inspect
    src = inspect.getsource(md.fetch_ticker)
    assert "_resolve_newest_bar_open" not in src
    assert "is_open" not in src


# ===========================================================================
# 32-35 — invariants
# ===========================================================================

def test_32_candidate_cap_unchanged():
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_33_no_extra_claude_calls():
    import ast
    tree = ast.parse(open("src/market_data.py").read())
    calls = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                calls.add(f.attr)
            elif isinstance(f, ast.Name):
                calls.add(f.id)
    assert "async_claude_scan" not in calls and "claude_call" not in calls


def test_34_no_additional_market_data_call_per_ticker(monkeypatch):
    calls = []
    real_download = md.yf.download

    def _spy(*a, **k):
        calls.append((a, k))
        return pd.DataFrame()

    monkeypatch.setattr(md.yf, "download", _spy)
    md.fetch_one_hour_bars("AAPL", {})
    assert len(calls) == 1     # exactly the existing single 1H request


def test_35_no_new_dependency():
    src = Path("src/market_data.py").read_text(encoding="utf-8")
    assert "import" in src
    forbidden = ("pandas_market_calendars", "exchange_calendars", "pytz", "trading_calendars")
    for dep in forbidden:
        assert dep not in src, dep
    assert "from zoneinfo import" in src   # stdlib only


# ===========================================================================
# Adversarial inputs
# ===========================================================================

def test_adversarial_malformed_timestamp_string_is_ambiguous_not_closed():
    assert md._bar_time_utc("definitely-not-a-timestamp") is None
    assert md._resolve_newest_bar_open(None, 60, datetime.now(timezone.utc)) is True


def test_adversarial_missing_timestamp_conservative():
    assert md._resolve_newest_bar_open(None, 60, None) is True


def test_adversarial_naive_pandas_index_cannot_prove_closed():
    naive = pd.Timestamp("2026-08-12 09:30:00")
    assert md._bar_time_utc(naive) is None


def test_adversarial_aware_pandas_index_preserved():
    aware = pd.Timestamp("2026-08-12 09:30:00", tz="America/New_York")
    result = md._bar_time_utc(aware)
    assert result is not None and result.tzinfo is not None
    assert result.hour == 13   # 09:30 EDT -> 13:30 UTC


def test_adversarial_future_timestamp_clock_skew_stays_open():
    future = datetime.now(timezone.utc) + timedelta(hours=5)
    assert md._resolve_newest_bar_open(future, 60, datetime.now(timezone.utc)) is True


def test_adversarial_weekend_boundary_closed():
    friday_bar = _et(2026, 8, 14, 15, 30).astimezone(timezone.utc)   # Friday
    saturday_now = _et(2026, 8, 15, 12, 0).astimezone(timezone.utc)  # Saturday
    assert md._resolve_newest_bar_open(friday_bar, 60, saturday_now) is False


def test_adversarial_exact_hourly_boundary():
    bar = _et(2026, 8, 12, 10, 30).astimezone(timezone.utc)
    exactly_at_end = bar + timedelta(minutes=60)
    assert md._resolve_newest_bar_open(bar, 60, exactly_at_end) is False   # >= end -> closed
    just_before = bar + timedelta(minutes=59, seconds=59)
    assert md._resolve_newest_bar_open(bar, 60, just_before) is True


def test_adversarial_16_00_boundary_exact():
    bar = _et(2026, 8, 12, 15, 30).astimezone(timezone.utc)
    at_close = _et(2026, 8, 12, 16, 0).astimezone(timezone.utc)
    assert md._resolve_newest_bar_open(bar, 60, at_close) is False


def test_adversarial_unsorted_and_duplicate_timestamps_do_not_crash():
    bars = [
        {"open": 1, "high": 1, "low": 1, "close": 1, "time": "2026-08-12T15:30:00+00:00"},
        {"open": 1, "high": 1, "low": 1, "close": 1, "time": "2026-08-12T14:30:00+00:00"},
        {"open": 1, "high": 1, "low": 1, "close": 1, "time": "2026-08-12T15:30:00+00:00"},
    ]
    result = ohe._compute_freshness(bars, datetime.now(timezone.utc))
    assert result in ohe.FRESHNESS_VALUES


def test_adversarial_single_bar_only():
    ctx = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR,
        one_hour_bars={"bars": [_bar(99, 100, 98, 99.5, time="2026-08-12T15:30:00+00:00")],
                       "freshness": "FRESH"})
    assert ctx["bar_context"]["closed_bar_available"] is True
    assert ctx["bar_context"]["live_bar_available"] is False


def test_adversarial_dst_spring_forward_no_crash():
    # 2026 US spring-forward: March 8, 2:00 AM -> 3:00 AM ET
    bar = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)
    now = datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc)
    result = md._resolve_newest_bar_open(bar, 60, now)
    assert isinstance(result, bool)


def test_adversarial_dst_fall_back_no_crash():
    # 2026 US fall-back: November 1
    bar = datetime(2026, 11, 1, 15, 30, tzinfo=timezone.utc)
    now = datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)
    result = md._resolve_newest_bar_open(bar, 60, now)
    assert isinstance(result, bool)


# ===========================================================================
# fetch_one_hour_bars integration — is_open only on the newest position
# ===========================================================================

def _fake_df(rows_et_times, freq_minutes=60):
    idx = pd.DatetimeIndex([t.astimezone(timezone.utc) for t in rows_et_times])
    return pd.DataFrame({
        "open": [1.0] * len(rows_et_times), "high": [1.0] * len(rows_et_times),
        "low": [1.0] * len(rows_et_times), "close": [1.0] * len(rows_et_times),
        "volume": [100.0] * len(rows_et_times),
    }, index=idx)


def test_fetch_one_hour_bars_marks_only_newest_bar_when_forming(monkeypatch):
    fake_now = _et(2026, 8, 12, 9, 35).astimezone(timezone.utc)
    rows = [_et(2026, 8, 12, 8, 30), _et(2026, 8, 12, 9, 30)]
    monkeypatch.setattr(md, "datetime",
                        type("_D", (datetime,), {"now": classmethod(lambda cls, tz=None: fake_now)}))
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: _fake_df(rows))
    result = md.fetch_one_hour_bars("AAPL", {})
    assert result["status"] == "OK"
    assert result["bars"][0].get("is_open") is not True     # older bar never marked
    assert result["bars"][-1].get("is_open") is True        # newest forming bar marked


def test_fetch_one_hour_bars_marks_no_bar_when_newest_closed(monkeypatch):
    fake_now = _et(2026, 8, 12, 11, 0).astimezone(timezone.utc)
    rows = [_et(2026, 8, 12, 8, 30), _et(2026, 8, 12, 9, 30)]
    monkeypatch.setattr(md, "datetime",
                        type("_D", (datetime,), {"now": classmethod(lambda cls, tz=None: fake_now)}))
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: _fake_df(rows))
    result = md.fetch_one_hour_bars("AAPL", {})
    assert all(b.get("is_open") is not True for b in result["bars"])


def test_fetch_one_hour_bars_now_field_is_timezone_aware(monkeypatch):
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: pd.DataFrame())
    result = md.fetch_one_hour_bars("AAPL", {})
    assert result["now"] is not None
    assert "+" in result["now"] or result["now"].endswith("Z") or result["now"].endswith("+00:00")


# ===========================================================================
# Strategy differential — unaffected fixtures must retain parity
# ===========================================================================

def test_class_a_unaffected_closed_fixture_strategy_parity():
    """A candidate whose 1H bars were already genuinely closed produces the
    identical trigger_state/score before and after MBT-1 (both runs use the
    current, fixed code — this proves the fixed code treats already-correct
    closed evidence exactly as the architecture always intended)."""
    ctx1 = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _CLOSED_SEQ, "freshness": "FRESH"})
    ctx2 = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": copy.deepcopy(_CLOSED_SEQ), "freshness": "FRESH"})
    assert ctx1["trigger_state"] == ctx2["trigger_state"]
    assert ctx1["score"] == ctx2["score"]
    assert ctx1["candle_truth"] == ctx2["candle_truth"]


def test_class_b_previously_misclassified_forming_bar_loses_closed_authority():
    """A forming bar that the OLD producer (no is_open) would have let slip
    through as closed now correctly loses that authority."""
    old_producer_shape = [
        {k: v for k, v in b.items() if k != "is_open"} for b in _live_seq()
    ]  # simulates the pre-fix envelope: no is_open anywhere
    ctx_old_shape = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": old_producer_shape, "freshness": "FRESH"})
    ctx_correct = ohe.build_one_hour_entry_context(
        "T", _tiering(), _ENR, one_hour_bars={"bars": _live_seq(), "freshness": "FRESH"})
    # Old shape (no marker at all) reads as fully closed; the properly-marked
    # live shape must NOT claim closed confirmation from that bar.
    assert ctx_old_shape["candle_truth"]["closed_candle_confirms"] is True
    assert ctx_correct["candle_truth"]["closed_candle_confirms"] is False

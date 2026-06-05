"""Phase 14C.5 — Observation Ledger tests (outcome_tracker).

Covers outcome math (TP1/2/3, invalidation, MFE/MAE), safe defaults, config
gating, decision-path isolation, and the read-only ledger query.
"""

import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src import outcome_tracker
from src.outcome_tracker import (
    compute_outcome,
    query_ledger,
    update_outcomes,
    _normalize_targets,
)

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bars(rows, start="2026-01-02"):
    """Build a daily OHLCV DataFrame. rows = list of (open, high, low, close)."""
    idx = pd.date_range(start=start, periods=len(rows), freq="D")
    data = {
        "open":   [r[0] for r in rows],
        "high":   [r[1] for r in rows],
        "low":    [r[2] for r in rows],
        "close":  [r[3] for r in rows],
        "volume": [1_000_000] * len(rows),
    }
    return pd.DataFrame(data, index=idx)


def _record(**overrides):
    rec = {
        "ticker":             "AAPL",
        "alert_id":           "s1|AAPL|2026-01-01T00:00:00",
        "alerted_at":         "2026-01-01T00:00:00",
        "tier":               "SNIPE_IT",
        "safe_for_alert":     True,
        "trigger_level":      100.0,
        "invalidation_level": 95.0,
        "targets":            [{"label": "T1", "level": 110.0},
                               {"label": "T2", "level": 120.0},
                               {"label": "T3", "level": 130.0}],
        "outcome_updated_at": None,
        "weekly_trend_state": "advancing",
        "four_hour_market_state": "EXPANSION",
    }
    rec.update(overrides)
    return rec


# ---------------------------------------------------------------------------
# compute_outcome — TP hit logic
# ---------------------------------------------------------------------------

def test_compute_outcome_tp1_hit():
    rec = _record()
    df = _bars([(100, 112, 99, 111)])   # close 111 >= TP1 110
    out = compute_outcome(rec, df)
    assert out["tp1_hit"] is True
    assert out["tp2_hit"] is False
    assert out["tp3_hit"] is False
    assert out["invalidated"] is False


def test_compute_outcome_tp2_hit_only_after_tp1():
    rec = _record()
    df = _bars([(100, 112, 99, 111), (111, 122, 110, 121)])  # TP1 then TP2
    out = compute_outcome(rec, df)
    assert out["tp1_hit"] is True
    assert out["tp2_hit"] is True
    assert out["tp3_hit"] is False


def test_compute_outcome_tp3_hit_full_sequence():
    rec = _record()
    df = _bars([(100, 112, 99, 111), (111, 122, 110, 121), (121, 132, 120, 131)])
    out = compute_outcome(rec, df)
    assert out["tp1_hit"] is True
    assert out["tp2_hit"] is True
    assert out["tp3_hit"] is True


def test_compute_outcome_tp2_blocked_without_tp1():
    """A bar closing above TP2 without TP1 ever hit cannot flip tp2 first.

    (Constructed so TP1 is never closed above — only possible if price gaps;
    here close stays below TP1 so neither flips.)
    """
    rec = _record()
    df = _bars([(100, 109, 99, 108)])   # high 109 < TP1 110; nothing hit
    out = compute_outcome(rec, df)
    assert out["tp1_hit"] is False
    assert out["tp2_hit"] is False


# ---------------------------------------------------------------------------
# compute_outcome — invalidation
# ---------------------------------------------------------------------------

def test_compute_outcome_invalidated():
    rec = _record()
    df = _bars([(100, 101, 90, 94)])   # close 94 <= invalidation 95
    out = compute_outcome(rec, df)
    assert out["invalidated"] is True
    assert out["tp1_hit"] is False


def test_compute_outcome_invalidation_before_targets_stops_walk():
    rec = _record()
    # Bar 1 invalidates; bar 2 would have hit TP1 but walk has stopped.
    df = _bars([(100, 101, 90, 94), (94, 115, 93, 112)])
    out = compute_outcome(rec, df)
    assert out["invalidated"] is True
    assert out["tp1_hit"] is False
    # MFE/MAE only reflect the walked (first) bar
    assert out["mfe_pct"] == pytest.approx((101 - 100) / 100 * 100)
    assert out["mae_pct"] == pytest.approx((90 - 100) / 100 * 100)


# ---------------------------------------------------------------------------
# compute_outcome — MFE / MAE math
# ---------------------------------------------------------------------------

def test_compute_outcome_mfe_mae_math():
    rec = _record(targets=[], invalidation_level=None)
    df = _bars([(100, 108, 96, 104), (104, 115, 101, 112)])
    out = compute_outcome(rec, df)
    assert out["mfe_pct"] == pytest.approx((115 - 100) / 100 * 100)  # +15%
    assert out["mae_pct"] == pytest.approx((96 - 100) / 100 * 100)   # -4%


def test_compute_outcome_no_targets_keeps_hits_none_but_computes_excursion():
    rec = _record(targets=None, invalidation_level=None)
    df = _bars([(100, 108, 96, 104)])
    out = compute_outcome(rec, df)
    assert out["tp1_hit"] is None
    assert out["tp2_hit"] is None
    assert out["tp3_hit"] is None
    assert out["invalidated"] is None
    assert out["mfe_pct"] is not None
    assert out["mae_pct"] is not None
    assert out["outcome_updated_at"] is not None


# ---------------------------------------------------------------------------
# compute_outcome — safe defaults
# ---------------------------------------------------------------------------

def test_compute_outcome_empty_df_returns_all_none():
    rec = _record()
    out = compute_outcome(rec, _bars([]))
    assert all(out[f] is None for f in (
        "tp1_hit", "tp2_hit", "tp3_hit", "invalidated",
        "mfe_pct", "mae_pct", "outcome_updated_at"))


def test_compute_outcome_none_df_returns_all_none():
    rec = _record()
    out = compute_outcome(rec, None)
    assert out["outcome_updated_at"] is None
    assert out["mfe_pct"] is None


def test_compute_outcome_missing_trigger_returns_all_none():
    rec = _record(trigger_level=None)
    df = _bars([(100, 112, 99, 111)])
    out = compute_outcome(rec, df)
    assert all(out[f] is None for f in out)


def test_compute_outcome_only_bars_after_alert():
    rec = _record(alerted_at="2026-01-03T00:00:00")
    # Bars on 01-02 (before) and 01-03/01-04. 01-02 would invalidate; excluded.
    df = _bars([(100, 101, 90, 94), (100, 112, 99, 111), (111, 113, 109, 112)],
               start="2026-01-02")
    out = compute_outcome(rec, df)
    # Pre-alert invalidation bar excluded → not invalidated; TP1 hit after.
    assert out["invalidated"] is False
    assert out["tp1_hit"] is True


# ---------------------------------------------------------------------------
# update_outcomes — config gating + skip rules
# ---------------------------------------------------------------------------

def _write_state(tmp_path, records):
    state = {"tickers": {"AAPL": {"alert_history": records}}, "meta": {}}
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return str(path)


def test_update_outcomes_disabled_means_no_fetch(tmp_path, monkeypatch):
    called = {"n": 0}

    def _fake_fetch(ticker, config):
        called["n"] += 1
        return {"df": _bars([(100, 112, 99, 111)])}

    monkeypatch.setattr(outcome_tracker.market_data, "fetch_ticker", _fake_fetch)
    path = _write_state(tmp_path, [_record()])
    cfg = {"observation": {"enable_outcome_tracking": False}}
    update_outcomes(path, cfg)
    assert called["n"] == 0


def test_update_outcomes_enabled_writes_outcome(tmp_path, monkeypatch):
    alert_dt = datetime.now(timezone.utc) - timedelta(days=10)
    bar_start = (alert_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setattr(
        outcome_tracker.market_data, "fetch_ticker",
        lambda t, c: {"df": _bars([(100, 112, 99, 111)], start=bar_start)},
    )
    rec = _record(alerted_at=alert_dt.isoformat())
    path = _write_state(tmp_path, [rec])
    cfg = {"observation": {"enable_outcome_tracking": True, "outcome_lookback_days": 3650},
           "data": {}}
    update_outcomes(path, cfg)
    state = json.loads(pathlib.Path(path).read_text())
    saved = state["tickers"]["AAPL"]["alert_history"][0]
    assert saved["tp1_hit"] is True
    assert saved["outcome_updated_at"] is not None


def test_update_outcomes_skips_wait_and_unsafe(tmp_path, monkeypatch):
    called = {"n": 0}

    def _fake_fetch(ticker, config):
        called["n"] += 1
        return {"df": _bars([(100, 112, 99, 111)])}

    monkeypatch.setattr(outcome_tracker.market_data, "fetch_ticker", _fake_fetch)
    recs = [
        _record(alert_id="a|WAIT", tier="WAIT",
                alerted_at=datetime.now(timezone.utc).isoformat()),
        _record(alert_id="a|unsafe", safe_for_alert=False,
                alerted_at=datetime.now(timezone.utc).isoformat()),
    ]
    path = _write_state(tmp_path, recs)
    cfg = {"observation": {"enable_outcome_tracking": True}}
    update_outcomes(path, cfg)
    assert called["n"] == 0


def test_update_outcomes_skips_already_finalized(tmp_path, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        outcome_tracker.market_data, "fetch_ticker",
        lambda t, c: called.__setitem__("n", called["n"] + 1) or {"df": None},
    )
    rec = _record(outcome_updated_at="2026-06-01T00:00:00+00:00",
                  alerted_at=datetime.now(timezone.utc).isoformat())
    path = _write_state(tmp_path, [rec])
    cfg = {"observation": {"enable_outcome_tracking": True}}
    update_outcomes(path, cfg)
    assert called["n"] == 0


def test_update_outcomes_one_bad_ticker_does_not_abort(tmp_path, monkeypatch):
    alert_dt = datetime.now(timezone.utc) - timedelta(days=10)
    bar_start = (alert_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    def _fetch(ticker, config):
        if ticker == "BAD":
            raise RuntimeError("boom")
        return {"df": _bars([(100, 112, 99, 111)], start=bar_start)}

    monkeypatch.setattr(outcome_tracker.market_data, "fetch_ticker", _fetch)
    now_iso = alert_dt.isoformat()
    state = {"tickers": {
        "BAD":  {"alert_history": [_record(ticker="BAD", alert_id="b|BAD", alerted_at=now_iso)]},
        "AAPL": {"alert_history": [_record(ticker="AAPL", alert_id="g|AAPL", alerted_at=now_iso)]},
    }, "meta": {}}
    path = tmp_path / "s.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    cfg = {"observation": {"enable_outcome_tracking": True, "outcome_lookback_days": 3650}}
    update_outcomes(str(path), cfg)
    saved = json.loads(path.read_text())
    # Good ticker still processed despite bad ticker raising.
    assert saved["tickers"]["AAPL"]["alert_history"][0]["tp1_hit"] is True
    assert saved["tickers"]["BAD"]["alert_history"][0].get("tp1_hit") is None


# ---------------------------------------------------------------------------
# query_ledger — grouping + read-only
# ---------------------------------------------------------------------------

def test_query_ledger_groups_by_evidence():
    state = {"tickers": {"AAPL": {"alert_history": [
        _record(weekly_trend_state="advancing", four_hour_market_state="EXPANSION",
                outcome_updated_at="t", tp1_hit=True, mfe_pct=5.0, mae_pct=-1.0),
        _record(weekly_trend_state="advancing", four_hour_market_state="EXPANSION",
                outcome_updated_at="t", tp1_hit=False, mfe_pct=1.0, mae_pct=-3.0),
        _record(weekly_trend_state="declining", four_hour_market_state="FAILURE",
                outcome_updated_at="t", tp1_hit=False, mfe_pct=0.5, mae_pct=-5.0),
    ]}}, "meta": {}}
    path = pathlib.Path("/tmp/_ledger_test.json")
    path.write_text(json.dumps(state), encoding="utf-8")

    rows = query_ledger(str(path))
    by_key = {(r["weekly_trend_state"], r["four_hour_market_state"]): r for r in rows}

    adv = by_key[("advancing", "EXPANSION")]
    assert adv["n"] == 2
    assert adv["tp1_hit_rate"] == 0.5
    assert adv["avg_mfe_pct"] == 3.0

    dec = by_key[("declining", "FAILURE")]
    assert dec["n"] == 1
    assert dec["tp1_hit_rate"] == 0.0


def test_query_ledger_excludes_unfinalized():
    state = {"tickers": {"AAPL": {"alert_history": [
        _record(outcome_updated_at=None),  # not finalized → excluded
    ]}}, "meta": {}}
    path = pathlib.Path("/tmp/_ledger_test2.json")
    path.write_text(json.dumps(state), encoding="utf-8")
    assert query_ledger(str(path)) == []


def test_query_ledger_is_read_only(tmp_path):
    state = {"tickers": {"AAPL": {"alert_history": [
        _record(outcome_updated_at="t", tp1_hit=True, mfe_pct=2.0, mae_pct=-1.0),
    ]}}, "meta": {}}
    path = tmp_path / "ro.json"
    raw = json.dumps(state)
    path.write_text(raw, encoding="utf-8")
    query_ledger(str(path))
    assert path.read_text() == raw   # file byte-for-byte unchanged


def test_query_ledger_custom_group_by():
    state = {"tickers": {"AAPL": {"alert_history": [
        _record(four_hour_market_state="EXPANSION", outcome_updated_at="t", tp1_hit=True),
    ]}}, "meta": {}}
    path = pathlib.Path("/tmp/_ledger_test3.json")
    path.write_text(json.dumps(state), encoding="utf-8")
    rows = query_ledger(str(path), group_by_fields=["four_hour_market_state"])
    assert rows[0]["four_hour_market_state"] == "EXPANSION"
    assert rows[0]["n"] == 1


def test_query_ledger_missing_file_returns_empty():
    assert query_ledger("/nonexistent/path/state.json") == []


# ---------------------------------------------------------------------------
# Decision-path isolation (structural)
# ---------------------------------------------------------------------------

def test_outcome_tracker_imports_no_decision_path_symbols():
    """outcome_tracker must not import tiering, prefilter, discord_alerts, indicators."""
    source = (SRC / "outcome_tracker.py").read_text()
    tree = ast.parse(source)
    forbidden = {"tiering", "prefilter", "discord_alerts", "indicators",
                 "claude_client", "campaign_store", "score_calibration"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module.split(".")[-1]
            imported.add(mod)
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[-1])
    leaked = forbidden & imported
    assert not leaked, f"outcome_tracker leaked decision-path imports: {leaked}"


def test_normalize_targets_supports_dict_and_number_forms():
    assert _normalize_targets([{"level": 110.0}, {"price": 120.0}]) == [110.0, 120.0]
    assert _normalize_targets([110, 120, 130]) == [110.0, 120.0, 130.0]
    assert _normalize_targets(110) == [110.0]
    assert _normalize_targets(None) == []
    assert _normalize_targets("garbage") == []

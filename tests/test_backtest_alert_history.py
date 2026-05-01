"""Tests for Phase 13.1 — Alert History Backtest Runner (scripts/backtest_alert_history.py)."""

from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

# Make the scripts/ directory importable for tests.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import backtest_alert_history as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _bar(date, high, low, open_=None, close=None) -> dict:
    return {
        "date":  date,
        "open":  open_  if open_  is not None else low,
        "high":  high,
        "low":   low,
        "close": close if close is not None else high,
    }


def _raw_alert(**kwargs) -> dict:
    base = {
        "ticker":             "AAPL",
        "scan_id":            "scan-001",
        "scan_time":          "2026-01-01T15:30:00",
        "final_tier":         "SNIPE_IT",
        "scan_price":         100.0,
        "trigger_level":      100.0,
        "invalidation_level": 95.0,
        "targets":            [110.0],
        "risk_reward":        3.0,
        "risk_realism_state": "healthy",
        "retest_status":      "confirmed",
        "hold_status":        "confirmed",
    }
    base.update(kwargs)
    return base


# ===========================================================================
# 1. normalize_alert_record — common fields
# ===========================================================================
def test_normalize_alert_record_maps_common_fields():
    raw = _raw_alert(
        ticker="MSFT",
        scan_id="scan-42",
        scan_time="2026-02-01T15:30:00",
        final_tier="STARTER",
        scan_price=305.0,
        trigger_level=300.0,
        invalidation_level=290.0,
        targets=[330.0, 340.0],
        risk_reward=3.5,
        risk_realism_state="healthy",
        retest_status="confirmed",
        hold_status="partial",
        current_acceptance="accepted",
        overhead_status="moderate",
        missing_conditions=["foo"],
        upgrade_trigger="break above 305",
    )
    out = runner.normalize_alert_record(raw)

    assert out["ticker"]              == "MSFT"
    assert out["scan_id"]             == "scan-42"
    assert out["scan_time"]           == "2026-02-01T15:30:00"
    assert out["final_tier"]          == "STARTER"
    assert out["tier"]                == "STARTER"
    assert out["scan_price"]          == 305.0
    assert out["trigger_level"]       == 300.0
    assert out["invalidation_level"]  == 290.0
    assert out["targets"]             == [330.0, 340.0]
    assert out["risk_reward"]         == 3.5
    assert out["risk_realism_state"]  == "healthy"
    assert out["retest_status"]       == "confirmed"
    assert out["hold_status"]         == "partial"
    assert out["current_acceptance"]  == "accepted"
    assert out["overhead_status"]     == "moderate"
    assert out["missing_conditions"]  == ["foo"]
    assert out["upgrade_trigger"]     == "break above 305"


# ===========================================================================
# 2. tier fallback (final_tier missing → tier; alerted_at as scan_time)
# ===========================================================================
def test_normalize_alert_record_uses_tier_fallback():
    raw = {
        "ticker":             "C",
        "tier":               "NEAR_ENTRY",
        "alerted_at":         "2026-03-01T15:30:00",
        "current_price":      128.35,
        "trigger":            128.44,
        "invalidation":       125.00,
        "target_1":           140.0,
    }
    out = runner.normalize_alert_record(raw)

    assert out["final_tier"]         == "NEAR_ENTRY"
    assert out["tier"]               == "NEAR_ENTRY"
    assert out["scan_time"]          == "2026-03-01T15:30:00"
    assert out["scan_price"]         == 128.35
    assert out["trigger_level"]      == 128.44
    assert out["invalidation_level"] == 125.00
    assert out["targets"]            == [140.0]


# ===========================================================================
# 3. targets variants
# ===========================================================================
def test_normalize_alert_record_targets_variants():
    # variant A — list
    a = runner.normalize_alert_record({"ticker": "A", "targets": [110, 120]})
    assert a["targets"] == [110, 120]

    # variant B — single scalar via "target"
    b = runner.normalize_alert_record({"ticker": "B", "target": 200})
    assert b["targets"] == [200]

    # variant C — dict via "target"
    c = runner.normalize_alert_record({"ticker": "C", "target": {"label": "T1", "level": 195}})
    assert c["targets"] == [{"label": "T1", "level": 195}]

    # variant D — single via "target_1"
    d = runner.normalize_alert_record({"ticker": "D", "target_1": 150})
    assert d["targets"] == [150]

    # variant E — none of the above
    e = runner.normalize_alert_record({"ticker": "E"})
    assert e["targets"] == []


# ===========================================================================
# 4. normalize_ohlc_bars — common fields
# ===========================================================================
def test_normalize_ohlc_bars_maps_common_fields():
    raw = [
        {"timestamp": "2026-01-02", "open": 100, "high": 102, "low": 99,  "close": 101},
        {"date":      "2026-01-01", "open":  98, "high": 101, "low": 97,  "close": 100},
        {"time":      "2026-01-03", "open": 101, "high": 103, "low": 100, "close": 102},
    ]
    out = runner.normalize_ohlc_bars(raw)
    # Every record normalized to {date, open, high, low, close}.
    assert all(set(b.keys()) >= {"date", "open", "high", "low", "close"} for b in out)
    # Sorted ascending by date.
    dates = [b["date"] for b in out]
    assert dates == sorted(dates)
    # Values preserved.
    assert out[0]["open"]  == 98
    assert out[0]["close"] == 100


# ===========================================================================
# 5. pair_alerts_with_bars — filters future bars by timestamp
# ===========================================================================
def test_pair_alerts_with_bars_filters_future_bars_by_timestamp():
    alert = runner.normalize_alert_record(_raw_alert(
        ticker="AAPL",
        scan_time="2026-01-02",
    ))
    bars = runner.normalize_ohlc_bars([
        {"date": "2026-01-01", "open": 100, "high": 101, "low": 99,  "close": 100},
        {"date": "2026-01-02", "open": 100, "high": 102, "low": 99,  "close": 101},
        {"date": "2026-01-03", "open": 101, "high": 103, "low": 100, "close": 102},
        {"date": "2026-01-04", "open": 102, "high": 111, "low": 101, "close": 110},
    ])
    pairs = runner.pair_alerts_with_bars([alert], {"AAPL": bars})

    assert len(pairs) == 1
    future = pairs[0]["future_bars"]
    # Only bars strictly after scan_time (2026-01-02).
    assert [b["date"] for b in future] == ["2026-01-03", "2026-01-04"]


# ===========================================================================
# 6. pair_alerts_with_bars — uses all bars when scan_time missing
# ===========================================================================
def test_pair_alerts_with_bars_uses_all_bars_when_time_missing():
    alert = runner.normalize_alert_record({
        "ticker":             "AAPL",
        "tier":               "SNIPE_IT",
        "trigger_level":      100.0,
        "invalidation_level": 95.0,
        "targets":            [110.0],
    })
    assert alert["scan_time"] is None

    bars = runner.normalize_ohlc_bars([
        {"date": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
        {"date": "2026-01-02", "open": 100, "high": 102, "low": 99, "close": 101},
    ])
    pairs = runner.pair_alerts_with_bars([alert], {"AAPL": bars})

    assert len(pairs) == 1
    assert len(pairs[0]["future_bars"]) == 2


# ===========================================================================
# 7. run_alert_history_backtest — produces a WIN summary
# ===========================================================================
def test_run_alert_history_backtest_produces_win_summary():
    alerts = [_raw_alert(ticker="AAPL", scan_time="2026-01-01")]
    bars = {
        "AAPL": [
            {"date": "2026-01-02", "open": 100, "high": 102, "low": 99,  "close": 101},
            {"date": "2026-01-03", "open": 101, "high": 111, "low": 101, "close": 110},
        ]
    }
    out = runner.run_alert_history_backtest(alerts, bars)

    assert len(out["results"]) == 1
    assert out["results"][0]["outcome_label"] == "WIN_T1_BEFORE_INVALIDATION"

    summary = out["summary"]
    assert summary["total_alerts"]   == 1
    assert summary["valid_results"]  == 1
    assert summary["wins"]           == 1
    assert summary["losses"]         == 0
    assert summary["win_rate_valid"] == 100.0


# ===========================================================================
# 8. run_alert_history_backtest — groups by tier
# ===========================================================================
def test_run_alert_history_backtest_groups_by_tier():
    alerts = [
        _raw_alert(ticker="AAA", scan_time="2026-01-01", final_tier="SNIPE_IT"),
        _raw_alert(ticker="BBB", scan_time="2026-01-01", final_tier="STARTER"),
    ]
    bars = {
        "AAA": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}],
        "BBB": [{"date": "2026-01-02", "open": 100, "high": 90,  "low": 90, "close": 90}],
    }
    out = runner.run_alert_history_backtest(alerts, bars)
    by_tier = out["summary"]["by_tier"]

    assert "SNIPE_IT" in by_tier
    assert "STARTER"  in by_tier
    assert by_tier["SNIPE_IT"]["wins"]   == 1
    assert by_tier["STARTER"]["losses"]  == 1


# ===========================================================================
# 9. run_alert_history_backtest — groups by risk_realism_state
# ===========================================================================
def test_run_alert_history_backtest_groups_by_risk_realism():
    alerts = [
        _raw_alert(ticker="AAA", scan_time="2026-01-01", risk_realism_state="healthy"),
        _raw_alert(ticker="BBB", scan_time="2026-01-01", risk_realism_state="dangerous"),
    ]
    bars = {
        "AAA": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}],
        "BBB": [{"date": "2026-01-02", "open": 100, "high": 102, "low": 90, "close": 91}],
    }
    out = runner.run_alert_history_backtest(alerts, bars)
    rrs = out["summary"]["by_risk_realism_state"]

    assert "healthy"   in rrs
    assert "dangerous" in rrs
    assert rrs["healthy"]["wins"]   == 1
    assert rrs["dangerous"]["losses"] == 1


# ===========================================================================
# 10. run_alert_history_backtest — groups by retest/hold combo
# ===========================================================================
def test_run_alert_history_backtest_groups_by_retest_hold_combo():
    alerts = [
        _raw_alert(ticker="AAA", scan_time="2026-01-01",
                   retest_status="confirmed", hold_status="confirmed"),
        _raw_alert(ticker="BBB", scan_time="2026-01-01",
                   retest_status="partial",   hold_status="partial"),
    ]
    bars = {
        "AAA": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}],
        "BBB": [{"date": "2026-01-02", "open": 100, "high": 102, "low": 90, "close": 91}],
    }
    out = runner.run_alert_history_backtest(alerts, bars)
    combos = out["summary"]["by_retest_hold_combo"]

    assert "confirmed/confirmed" in combos
    assert "partial/partial"     in combos
    assert combos["confirmed/confirmed"]["wins"]   == 1
    assert combos["partial/partial"]["losses"]     == 1


# ===========================================================================
# 11. format_backtest_summary contains core metrics
# ===========================================================================
def test_format_backtest_summary_contains_core_metrics():
    summary = {
        "total_alerts":      3,
        "valid_results":     3,
        "invalid_results":   0,
        "wins":              2,
        "losses":            1,
        "open":              0,
        "no_trigger":        0,
        "ambiguous":         0,
        "win_rate_valid":    66.67,
        "loss_rate_valid":   33.33,
        "avg_mfe_pct":       4.5,
        "avg_mae_pct":      -2.0,
        "by_tier": {
            "SNIPE_IT": {"count": 2, "wins": 2, "losses": 0,
                         "win_rate": 100.0, "avg_mfe_pct": 5.0, "avg_mae_pct": -1.0},
            "STARTER":  {"count": 1, "wins": 0, "losses": 1,
                         "win_rate":   0.0, "avg_mfe_pct": 1.0, "avg_mae_pct": -3.0},
        },
        "by_risk_realism_state": {
            "healthy": {"count": 3, "wins": 2, "losses": 1,
                        "win_rate": 66.67, "avg_mfe_pct": 4.5, "avg_mae_pct": -2.0},
        },
        "by_retest_hold_combo": {
            "confirmed/confirmed": {"count": 3, "wins": 2, "losses": 1,
                                    "win_rate": 66.67, "avg_mfe_pct": 4.5, "avg_mae_pct": -2.0},
        },
    }
    text = runner.format_backtest_summary(summary)

    assert "total_alerts:" in text
    assert "valid_results:" in text
    assert "invalid_results:" in text
    assert "wins:" in text
    assert "losses:" in text
    assert "open:" in text
    assert "no_trigger:" in text
    assert "ambiguous:" in text
    assert "win_rate_valid:" in text
    assert "avg_mfe_pct:" in text
    assert "avg_mae_pct:" in text
    assert "by_tier:" in text
    assert "by_risk_realism_state:" in text
    assert "by_retest_hold_combo:" in text
    assert "SNIPE_IT" in text
    assert "STARTER" in text
    assert "healthy" in text
    assert "confirmed/confirmed" in text


# ===========================================================================
# 12. CLI main — prints summary
# ===========================================================================
def test_cli_main_prints_summary(tmp_path, capsys):
    alerts_path = tmp_path / "alerts.json"
    bars_path   = tmp_path / "bars.json"

    alerts_path.write_text(json.dumps([_raw_alert(ticker="AAPL", scan_time="2026-01-01")]))
    bars_path.write_text(json.dumps({
        "AAPL": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}]
    }))

    rc = runner.main(["--alerts", str(alerts_path), "--bars", str(bars_path), "--horizon", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Backtest Summary" in out
    assert "total_alerts:" in out
    assert "wins:" in out


# ===========================================================================
# 13. CLI main — nonzero exit for missing file
# ===========================================================================
def test_cli_main_returns_nonzero_for_missing_file(tmp_path, capsys):
    bars_path = tmp_path / "bars.json"
    bars_path.write_text(json.dumps({"AAPL": []}))

    missing = tmp_path / "nonexistent_alerts.json"
    rc = runner.main(["--alerts", str(missing), "--bars", str(bars_path)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "alerts file not found" in err


# ===========================================================================
# 14. Script does NOT import live scanner / discord
# ===========================================================================
def test_script_does_not_import_live_scanner_or_discord():
    path = _SCRIPTS_DIR / "backtest_alert_history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden_modules = {
        "discord",
        "yfinance",
        "anthropic",
        "src.scheduler",
        "src.discord_alerts",
        "src.tiering",
        "src.main",
        "src.state_store",
        "src.claude_client",
        "src.market_data",
        "src.indicators",
        "src.prefilter",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.add(node.module)

    bad = forbidden_modules.intersection(seen)
    assert not bad, f"Script imports forbidden modules: {bad}"

    # Confirm src.backtest IS imported (only allowed src import).
    assert "src.backtest" in seen


# ===========================================================================
# 15. No file writes anywhere in script
# ===========================================================================
def test_no_file_writes_in_script():
    path = _SCRIPTS_DIR / "backtest_alert_history.py"
    source = path.read_text(encoding="utf-8")

    forbidden_substrings = [
        ".write_text(",
        ".write_bytes(",
        "open(",   # any open(...) call could write
        "json.dump(",
        "shutil.copy",
        "shutil.move",
        "os.remove",
        "os.rename",
    ]
    found = [s for s in forbidden_substrings if s in source]
    assert not found, f"Script contains write-capable call sites: {found}"


# ===========================================================================
# 16. No network imports
# ===========================================================================
def test_no_network_imports():
    path = _SCRIPTS_DIR / "backtest_alert_history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden_modules = {
        "urllib",
        "urllib.request",
        "urllib.parse",
        "http",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "yfinance",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.add(node.module)

    bad = forbidden_modules.intersection(seen)
    assert not bad, f"Script imports network modules: {bad}"


# ===========================================================================
# 17. NEAR_ENTRY alert history can be backtested (Phase 12.3 surface)
# ===========================================================================
def test_near_entry_alert_history_can_be_backtested():
    # NEAR_ENTRY: scan_price below trigger; trigger above scan_price; T1 above trigger.
    alerts = [_raw_alert(
        ticker="C",
        scan_time="2026-01-01",
        final_tier="NEAR_ENTRY",
        scan_price=128.35,
        trigger_level=128.44,
        invalidation_level=125.00,
        targets=[140.0],
        retest_status="confirmed",
        hold_status="confirmed",
        risk_realism_state="healthy",
    )]
    bars = {
        "C": [
            {"date": "2026-01-02", "open": 129, "high": 130,    "low": 128.5, "close": 129.5},
            {"date": "2026-01-03", "open": 130, "high": 141.00, "low": 129,   "close": 140.5},
        ]
    }
    out = runner.run_alert_history_backtest(alerts, bars)

    assert len(out["results"]) == 1
    r = out["results"][0]
    assert r["outcome_label"] == "WIN_T1_BEFORE_INVALIDATION"
    assert r["alert_tier"] == "NEAR_ENTRY"
    # Trigger was above scan_price (128.44 > 128.35). Track that trigger was hit.
    assert r["hit_trigger_first"] is True


# ===========================================================================
# 18. AMBIGUOUS_SAME_BAR surfaces in runner
# ===========================================================================
def test_ambiguous_same_bar_surfaces_in_runner():
    # One bar that touches BOTH the T1 high and the invalidation low.
    alerts = [_raw_alert(
        ticker="X",
        scan_time="2026-01-01",
        trigger_level=100.0,
        invalidation_level=95.0,
        targets=[110.0],
    )]
    bars = {
        "X": [
            {"date": "2026-01-02", "open": 100, "high": 111, "low": 94, "close": 100},
        ]
    }
    out = runner.run_alert_history_backtest(alerts, bars)

    assert len(out["results"]) == 1
    assert out["results"][0]["outcome_label"] == "AMBIGUOUS_SAME_BAR"
    assert out["summary"]["ambiguous"] == 1

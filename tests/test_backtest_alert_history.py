"""Tests for Phase 13.1 / 13.2 — Alert History Backtest Runner (scripts/backtest_alert_history.py)."""

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


# ===========================================================================
# Phase 13.2 tests — data quality reporting
# ===========================================================================

def _complete_alert(**kwargs) -> dict:
    """Normalized alert with all fields populated — COMPLETE quality label."""
    base = {
        "ticker":             "AAPL",
        "final_tier":         "SNIPE_IT",
        "tier":               "SNIPE_IT",
        "scan_price":         100.0,
        "trigger_level":      100.0,
        "invalidation_level": 95.0,
        "targets":            [110.0],
    }
    base.update(kwargs)
    return base


# ===========================================================================
# 19. get_alert_data_quality — COMPLETE
# ===========================================================================
def test_get_alert_data_quality_complete():
    alert = _complete_alert()
    dq = runner.get_alert_data_quality(alert)

    assert dq["has_target"]          is True
    assert dq["has_invalidation"]    is True
    assert dq["has_reference_price"] is True
    assert dq["has_trigger"]         is True
    assert dq["has_tier"]            is True
    assert dq["missing_fields"]      == []
    assert dq["data_quality_label"]  == "COMPLETE"


# ===========================================================================
# 20. get_alert_data_quality — BACKTESTABLE (trigger missing)
# ===========================================================================
def test_get_alert_data_quality_backtestable_without_trigger():
    # Has target, invalidation, scan_price (reference_price), tier but no trigger.
    alert = {
        "ticker":             "MSFT",
        "final_tier":         "STARTER",
        "tier":               "STARTER",
        "scan_price":         200.0,
        "trigger_level":      None,
        "invalidation_level": 190.0,
        "targets":            [220.0],
    }
    dq = runner.get_alert_data_quality(alert)

    assert dq["has_target"]          is True
    assert dq["has_invalidation"]    is True
    assert dq["has_reference_price"] is True   # scan_price covers it
    assert dq["has_trigger"]         is False
    assert "trigger_level"           in dq["missing_fields"]
    assert dq["data_quality_label"]  == "BACKTESTABLE"


# ===========================================================================
# 21. get_alert_data_quality — PARTIAL (no target)
# ===========================================================================
def test_get_alert_data_quality_partial_missing_target():
    alert = {
        "ticker":             "C",
        "tier":               "NEAR_ENTRY",
        "scan_price":         128.35,
        "trigger_level":      128.44,
        "invalidation_level": 126.84,
        "targets":            [],       # empty — no target
    }
    dq = runner.get_alert_data_quality(alert)

    assert dq["has_target"]         is False
    assert dq["has_invalidation"]   is True
    assert dq["data_quality_label"] == "PARTIAL"
    assert "targets" in dq["missing_fields"]


# ===========================================================================
# 22. get_alert_data_quality — INSUFFICIENT
# ===========================================================================
def test_get_alert_data_quality_insufficient_missing_invalidation_and_reference():
    # Missing invalidation, scan_price, trigger_level — and no targets either.
    alert = {
        "ticker":    "GHOST",
        "tier":      "WAIT",
        "reason":    "nothing here",
        "score":     12,
    }
    dq = runner.get_alert_data_quality(alert)

    assert dq["has_target"]          is False
    assert dq["has_invalidation"]    is False
    assert dq["has_reference_price"] is False
    assert dq["data_quality_label"]  == "INSUFFICIENT"


# ===========================================================================
# 23. summarize_data_quality — missing_target count
# ===========================================================================
def test_summarize_data_quality_counts_missing_targets():
    alerts = [
        _complete_alert(ticker="A"),                       # has target
        _complete_alert(ticker="B", targets=[]),            # missing target
        _complete_alert(ticker="C", targets=None),          # missing target (None coerced to [])
    ]
    # normalize so targets=None becomes [] in the dict
    normalized = [runner.normalize_alert_record(a) for a in alerts]
    dq = runner.summarize_data_quality(normalized)

    assert dq["total_alerts"]   == 3
    assert dq["missing_target"] == 2   # B and C have no targets


# ===========================================================================
# 24. summarize_data_quality — by_tier grouping
# ===========================================================================
def test_summarize_data_quality_groups_by_tier():
    alerts = [
        runner.normalize_alert_record(_complete_alert(ticker="A", final_tier="SNIPE_IT", tier="SNIPE_IT")),
        runner.normalize_alert_record(_complete_alert(ticker="B", final_tier="STARTER",  tier="STARTER", targets=[])),
        runner.normalize_alert_record(_complete_alert(ticker="C", final_tier="NEAR_ENTRY", tier="NEAR_ENTRY")),
    ]
    dq = runner.summarize_data_quality(alerts)

    assert "SNIPE_IT"   in dq["by_tier"]
    assert "STARTER"    in dq["by_tier"]
    assert "NEAR_ENTRY" in dq["by_tier"]
    assert dq["by_tier"]["SNIPE_IT"]["complete"]        == 1
    assert dq["by_tier"]["STARTER"]["missing_target"]   == 1
    assert dq["by_tier"]["NEAR_ENTRY"]["complete"]      == 1


# ===========================================================================
# 25. summarize_data_quality — missing_fields_ranked
# ===========================================================================
def test_summarize_data_quality_ranks_missing_fields():
    alerts = [
        runner.normalize_alert_record(_complete_alert(ticker="A", targets=[])),
        runner.normalize_alert_record(_complete_alert(ticker="B", targets=[])),
        runner.normalize_alert_record(_complete_alert(ticker="C", targets=[], trigger_level=None)),
    ]
    dq = runner.summarize_data_quality(alerts)

    ranked = dq["missing_fields_ranked"]
    assert len(ranked) > 0
    fields = [e["field"] for e in ranked]
    assert "targets" in fields
    # targets missing for all 3 — should rank first
    targets_entry = next(e for e in ranked if e["field"] == "targets")
    assert targets_entry["count"] == 3


# ===========================================================================
# 26. run_alert_history_backtest returns data_quality key
# ===========================================================================
def test_run_alert_history_backtest_returns_data_quality():
    alerts = [_raw_alert(ticker="AAPL", scan_time="2026-01-01")]
    bars   = {"AAPL": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}]}
    out    = runner.run_alert_history_backtest(alerts, bars)

    assert "results"      in out
    assert "summary"      in out
    assert "data_quality" in out
    dq = out["data_quality"]
    assert "total_alerts"          in dq
    assert "complete"              in dq
    assert "missing_target"        in dq
    assert "missing_fields_ranked" in dq
    assert "by_tier"               in dq


# ===========================================================================
# 27. missing target → INVALID_DATA in results + counted in data_quality
# ===========================================================================
def test_run_alert_history_backtest_missing_target_counts_invalid_data():
    alerts = [_raw_alert(ticker="AAPL", scan_time="2026-01-01", targets=[])]
    bars   = {"AAPL": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}]}
    out    = runner.run_alert_history_backtest(alerts, bars)

    assert out["results"][0]["outcome_label"] == "INVALID_DATA"
    assert out["summary"]["invalid_results"]  == 1
    assert out["data_quality"]["missing_target"] == 1


# ===========================================================================
# 28. format_backtest_summary — DATA QUALITY section present
# ===========================================================================
def test_format_backtest_summary_includes_data_quality_section():
    summary = {
        "total_alerts": 2, "valid_results": 2, "invalid_results": 0,
        "wins": 1, "losses": 1, "open": 0, "no_trigger": 0, "ambiguous": 0,
        "win_rate_valid": 50.0, "loss_rate_valid": 50.0,
        "avg_mfe_pct": 3.0, "avg_mae_pct": -1.0,
        "by_tier": {}, "by_risk_realism_state": {}, "by_retest_hold_combo": {},
    }
    data_quality = {
        "total_alerts": 2, "complete": 1, "backtestable": 0, "partial": 1, "insufficient": 0,
        "missing_target": 1, "missing_invalidation": 0, "missing_reference_price": 0,
        "missing_trigger": 0, "missing_tier": 0,
        "by_tier": {"SNIPE_IT": {"count": 2, "complete": 1, "backtestable": 0,
                                  "partial": 1, "insufficient": 0,
                                  "missing_target": 1, "missing_invalidation": 0,
                                  "missing_reference_price": 0}},
        "missing_fields_ranked": [{"field": "targets", "count": 1}],
    }
    text = runner.format_backtest_summary(summary, data_quality)

    assert "DATA QUALITY"         in text
    assert "Total alerts:"        in text
    assert "Complete:"            in text
    assert "Backtestable:"        in text
    assert "Missing targets:"     in text
    assert "BY TIER DATA QUALITY" in text
    assert "MISSING FIELDS"       in text


# ===========================================================================
# 29. MISSING TARGET STRATEGY — "Do not fabricate targets" when targets missing
# ===========================================================================
def test_format_backtest_summary_includes_missing_target_strategy_when_targets_missing():
    summary = {
        "total_alerts": 1, "valid_results": 0, "invalid_results": 1,
        "wins": 0, "losses": 0, "open": 0, "no_trigger": 0, "ambiguous": 0,
        "win_rate_valid": None, "loss_rate_valid": None,
        "avg_mfe_pct": None, "avg_mae_pct": None,
        "by_tier": {}, "by_risk_realism_state": {}, "by_retest_hold_combo": {},
    }
    data_quality = {
        "total_alerts": 1, "complete": 0, "backtestable": 0, "partial": 1, "insufficient": 0,
        "missing_target": 1, "missing_invalidation": 0, "missing_reference_price": 0,
        "missing_trigger": 0, "missing_tier": 0,
        "by_tier": {}, "missing_fields_ranked": [{"field": "targets", "count": 1}],
    }
    text = runner.format_backtest_summary(summary, data_quality)

    assert "MISSING TARGET STRATEGY"  in text
    assert "Do not fabricate targets" in text
    assert "target_1 / targets"       in text


# ===========================================================================
# 30. MISSING TARGET STRATEGY — "Targets available" when no missing targets
# ===========================================================================
def test_format_backtest_summary_targets_available_message_when_no_missing_targets():
    summary = {
        "total_alerts": 1, "valid_results": 1, "invalid_results": 0,
        "wins": 1, "losses": 0, "open": 0, "no_trigger": 0, "ambiguous": 0,
        "win_rate_valid": 100.0, "loss_rate_valid": 0.0,
        "avg_mfe_pct": 5.0, "avg_mae_pct": -1.0,
        "by_tier": {}, "by_risk_realism_state": {}, "by_retest_hold_combo": {},
    }
    data_quality = {
        "total_alerts": 1, "complete": 1, "backtestable": 0, "partial": 0, "insufficient": 0,
        "missing_target": 0, "missing_invalidation": 0, "missing_reference_price": 0,
        "missing_trigger": 0, "missing_tier": 0,
        "by_tier": {}, "missing_fields_ranked": [],
    }
    text = runner.format_backtest_summary(summary, data_quality)

    assert "Targets available for all records." in text
    assert "Do not fabricate targets"           not in text


# ===========================================================================
# 31. CLI main prints DATA QUALITY section
# ===========================================================================
def test_cli_main_prints_data_quality_section(tmp_path, capsys):
    alerts_path = tmp_path / "alerts.json"
    bars_path   = tmp_path / "bars.json"

    alerts_path.write_text(json.dumps([_raw_alert(ticker="AAPL", scan_time="2026-01-01")]))
    bars_path.write_text(json.dumps({
        "AAPL": [{"date": "2026-01-02", "open": 100, "high": 111, "low": 99, "close": 110}]
    }))

    rc = runner.main(["--alerts", str(alerts_path), "--bars", str(bars_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DATA QUALITY"             in out
    assert "MISSING TARGET STRATEGY"  in out


# ===========================================================================
# 32. Existing Phase 13.1 tests still pass — format_backtest_summary(summary) alone
# ===========================================================================
def test_existing_phase13_1_summary_still_works_without_data_quality():
    summary = {
        "total_alerts": 3, "valid_results": 3, "invalid_results": 0,
        "wins": 2, "losses": 1, "open": 0, "no_trigger": 0, "ambiguous": 0,
        "win_rate_valid": 66.67, "loss_rate_valid": 33.33,
        "avg_mfe_pct": 4.5, "avg_mae_pct": -2.0,
        "by_tier": {}, "by_risk_realism_state": {}, "by_retest_hold_combo": {},
    }
    text = runner.format_backtest_summary(summary)   # no data_quality argument

    assert "Backtest Summary"  in text
    assert "total_alerts:"     in text
    assert "wins:"             in text
    assert "DATA QUALITY"      not in text           # absent when not passed


# ===========================================================================
# 33. No target fabrication
# ===========================================================================
def test_no_target_fabrication():
    # Alert with no target field at all.
    alert_raw = {
        "ticker":             "C",
        "tier":               "NEAR_ENTRY",
        "scan_price":         128.35,
        "trigger_level":      128.44,
        "invalidation_level": 126.84,
    }
    normalized = runner.normalize_alert_record(alert_raw)
    assert normalized["targets"] == []   # empty — not fabricated

    dq = runner.get_alert_data_quality(normalized)
    assert dq["has_target"]         is False
    assert "targets" in dq["missing_fields"]

    bars = {"C": [{"date": "2026-01-02", "open": 128.4, "high": 135.0, "low": 128.0, "close": 134.0}]}
    out  = runner.run_alert_history_backtest([alert_raw], bars)

    result = out["results"][0]
    assert result["outcome_label"]         == "INVALID_DATA"   # no target → cannot classify WIN
    assert out["data_quality"]["missing_target"] == 1


# ===========================================================================
# 34. Regression: script still does not import live scanner / discord (Phase 13.2)
# ===========================================================================
def test_script_still_does_not_import_live_scanner_or_discord():
    path = _SCRIPTS_DIR / "backtest_alert_history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden_modules = {
        "discord", "yfinance", "anthropic",
        "src.scheduler", "src.discord_alerts", "src.tiering", "src.main",
        "src.state_store", "src.claude_client", "src.market_data",
        "src.indicators", "src.prefilter",
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
    assert "src.backtest" in seen


# ===========================================================================
# 35. Regression: no network imports (Phase 13.2)
# ===========================================================================
def test_script_still_has_no_network_imports():
    path = _SCRIPTS_DIR / "backtest_alert_history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden = {"urllib", "urllib.request", "urllib.parse", "http", "http.client",
                 "requests", "httpx", "aiohttp", "socket", "yfinance"}
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.add(node.module)

    bad = forbidden.intersection(seen)
    assert not bad, f"Script imports network modules: {bad}"


# ===========================================================================
# 36. Regression: no file writes (Phase 13.2)
# ===========================================================================
def test_script_still_has_no_file_writes():
    path   = _SCRIPTS_DIR / "backtest_alert_history.py"
    source = path.read_text(encoding="utf-8")

    forbidden_substrings = [
        ".write_text(", ".write_bytes(", "open(", "json.dump(",
        "shutil.copy", "shutil.move", "os.remove", "os.rename",
    ]
    found = [s for s in forbidden_substrings if s in source]
    assert not found, f"Script contains write-capable call sites: {found}"


# ===========================================================================
# 37. Realistic state-store record (C NEAR_ENTRY without target)
# ===========================================================================
def test_data_quality_for_realistic_alert_state_record_without_target():
    raw = {
        "ticker":             "C",
        "tier":               "NEAR_ENTRY",
        "alerted_at":         "2026-04-15T15:30:00",
        "trigger_level":      128.44,
        "invalidation_level": 126.84,
        "score":              87,
        "reason":             "near-entry setup with blocker below trigger",
        "dedup_key":          "C|NEAR_ENTRY|128.44|126.84",
        "scan_id":            "scan-20260415-153000",
    }
    normalized = runner.normalize_alert_record(raw)
    dq = runner.get_alert_data_quality(normalized)

    assert dq["has_target"]         is False         # no target stored
    assert "targets"                in dq["missing_fields"]
    # trigger_level exists → reference_price falls back to trigger
    assert dq["has_reference_price"] is True
    assert dq["has_trigger"]         is True
    # No targets → not COMPLETE or BACKTESTABLE; has invalidation and reference → PARTIAL
    assert dq["data_quality_label"]  == "PARTIAL"

    # Confirm no target was fabricated during normalization
    assert normalized["targets"] == []


# ===========================================================================
# 38. No-analysis-paralysis: no alert-suppression / scanner-gating words
# ===========================================================================
def test_data_quality_preserves_no_analysis_paralysis():
    path   = _SCRIPTS_DIR / "backtest_alert_history.py"
    source = path.read_text(encoding="utf-8")

    forbidden_words = [
        "block_alert",
        "suppress_alert",
        "change_tier",
        "tune_score",
    ]
    found = [w for w in forbidden_words if w in source]
    assert not found, f"Script contains gating/suppression logic: {found}"

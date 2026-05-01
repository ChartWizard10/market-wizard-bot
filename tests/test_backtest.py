"""Tests for Phase 13 — Backtest Foundation (src/backtest.py)."""

import ast
import pathlib

import pytest

from src.backtest import (
    evaluate_alert_outcome,
    summarize_backtest_results,
    WIN_T1_BEFORE_INVALIDATION,
    LOSS_INVALIDATION_BEFORE_T1,
    OPEN_NO_TERMINAL_HIT,
    NO_TRIGGER,
    AMBIGUOUS_SAME_BAR,
    INVALID_DATA,
    _normalize_targets,
    _get_first_target,
    _get_reference_price,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_UNSET = object()  # sentinel so _alert(targets=None) ≠ _alert()


def _alert(
    scan_price=100.0,
    trigger_level=100.0,
    invalidation_level=95.0,
    targets=_UNSET,
    tier="SNIPE_IT",
    risk_realism_state="healthy",
    retest_status="confirmed",
    hold_status="confirmed",
    **kwargs,
) -> dict:
    base_targets = [110.0] if targets is _UNSET else targets
    a = {
        "ticker":             "AAPL",
        "final_tier":         tier,
        "scan_price":         scan_price,
        "trigger_level":      trigger_level,
        "invalidation_level": invalidation_level,
        "targets":            base_targets,
        "risk_realism_state": risk_realism_state,
        "retest_status":      retest_status,
        "hold_status":        hold_status,
    }
    a.update(kwargs)
    return a


def _bar(high, low, open_=None, close=None) -> dict:
    return {
        "open":  open_  if open_  is not None else low,
        "high":  high,
        "low":   low,
        "close": close if close is not None else high,
    }


def _flat_bars(n: int, *, price: float = 100.0) -> list[dict]:
    """n bars that stay in a tight range — never hit default T1=110 or inv=95."""
    return [_bar(high=price + 1, low=price - 1) for _ in range(n)]


# ---------------------------------------------------------------------------
# 1. WIN
# ---------------------------------------------------------------------------
def test_evaluate_alert_win_t1_before_invalidation():
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110])
    bars = [
        _bar(high=102, low=99),   # no hit
        _bar(high=111, low=101),  # T1 hit
    ]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == WIN_T1_BEFORE_INVALIDATION
    assert result["hit_t1_before_invalidation"] is True
    assert result["hit_invalidation_before_t1"] is False
    assert result["bars_to_t1"] == 1
    assert result["first_hit"] == "t1"


# ---------------------------------------------------------------------------
# 2. LOSS
# ---------------------------------------------------------------------------
def test_evaluate_alert_loss_invalidation_before_t1():
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110])
    bars = [
        _bar(high=102, low=99),  # no hit
        _bar(high=101, low=94),  # invalidation hit
    ]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == LOSS_INVALIDATION_BEFORE_T1
    assert result["hit_t1_before_invalidation"] is False
    assert result["hit_invalidation_before_t1"] is True
    assert result["bars_to_invalidation"] == 1
    assert result["first_hit"] == "invalidation"


# ---------------------------------------------------------------------------
# 3. OPEN_NO_TERMINAL_HIT
# ---------------------------------------------------------------------------
def test_evaluate_alert_open_no_terminal_hit():
    # trigger_level=None → no NO_TRIGGER path; bars stay in tight range
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110],
                   trigger_level=None)
    bars = _flat_bars(5)  # high=101, low=99 each
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == OPEN_NO_TERMINAL_HIT
    assert result["hit_t1_before_invalidation"] is False
    assert result["hit_invalidation_before_t1"] is False
    assert result["terminal_bar_index"] is None


# ---------------------------------------------------------------------------
# 4. AMBIGUOUS_SAME_BAR
# ---------------------------------------------------------------------------
def test_evaluate_alert_ambiguous_same_bar():
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110],
                   trigger_level=None)
    bars = [_bar(high=111, low=94)]  # same bar touches both T1 and invalidation
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == AMBIGUOUS_SAME_BAR
    assert result["hit_t1_before_invalidation"] is False
    assert result["hit_invalidation_before_t1"] is False
    assert result["first_hit"] == "ambiguous_same_bar"
    assert result["terminal_bar_index"] == 0


# ---------------------------------------------------------------------------
# 5. NO_TRIGGER
# ---------------------------------------------------------------------------
def test_evaluate_alert_no_trigger():
    # trigger=105, T1=110, invalidation=95; bars peak at 104 — never confirm
    alert = _alert(scan_price=100, trigger_level=105, invalidation_level=95,
                   targets=[110])
    bars = [_bar(high=104, low=98) for _ in range(5)]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == NO_TRIGGER
    assert result["hit_trigger_first"] is False
    assert result["hit_t1_before_invalidation"] is False


# ---------------------------------------------------------------------------
# 6. INVALID_DATA — no valid targets
# ---------------------------------------------------------------------------
def test_evaluate_alert_invalid_data_missing_target():
    alert = _alert(scan_price=100, invalidation_level=95, targets=None)
    bars = _flat_bars(5)
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == INVALID_DATA
    assert "target" in result["reason"].lower()


# ---------------------------------------------------------------------------
# 7. INVALID_DATA — no invalidation
# ---------------------------------------------------------------------------
def test_evaluate_alert_invalid_data_missing_invalidation():
    alert = _alert(scan_price=100, targets=[110])
    alert.pop("invalidation_level", None)
    bars = _flat_bars(5)
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == INVALID_DATA
    assert "invalidation" in result["reason"].lower()


# ---------------------------------------------------------------------------
# 8. Target normalization — list of numbers
# ---------------------------------------------------------------------------
def test_evaluate_alert_normalizes_targets_from_numbers():
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110, 120])
    bars = [_bar(high=111, low=100)]
    result = evaluate_alert_outcome(alert, bars)
    # T1 is the first element (110), not the second (120)
    assert result["outcome_label"] == WIN_T1_BEFORE_INVALIDATION


# ---------------------------------------------------------------------------
# 9. Target normalization — list of dicts (production alert format)
# ---------------------------------------------------------------------------
def test_evaluate_alert_normalizes_targets_from_dicts():
    alert = _alert(
        scan_price=100,
        invalidation_level=95,
        targets=[
            {"label": "T1", "level": 110.0, "reason": "Prior swing"},
            {"label": "T2", "level": 120.0, "reason": "Extension"},
        ],
    )
    bars = [_bar(high=111, low=100)]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == WIN_T1_BEFORE_INVALIDATION


# ---------------------------------------------------------------------------
# 10. MFE / MAE computation
# ---------------------------------------------------------------------------
def test_evaluate_alert_computes_mfe_mae_pct():
    alert = _alert(scan_price=100, invalidation_level=90, targets=[120],
                   trigger_level=None)
    bars = [
        _bar(high=105, low=98),  # up 5,  down 2
        _bar(high=108, low=97),  # up 8,  down 3  ← extremes
        _bar(high=103, low=99),
    ]
    result = evaluate_alert_outcome(alert, bars)
    # outcome is OPEN (T1=120 not hit, invalidation=90 not hit)
    assert result["outcome_label"] == OPEN_NO_TERMINAL_HIT
    assert result["max_favorable_excursion"]     == pytest.approx(8.0)
    assert result["max_favorable_excursion_pct"] == pytest.approx(8.0)
    assert result["max_adverse_excursion"]       == pytest.approx(-3.0)
    assert result["max_adverse_excursion_pct"]   == pytest.approx(-3.0)


# ---------------------------------------------------------------------------
# 11. summarize — total counts and win rate
# ---------------------------------------------------------------------------
def test_summarize_backtest_results_counts_wins_losses():
    results = [
        evaluate_alert_outcome(
            _alert(targets=[110]),
            [_bar(high=111, low=100)]),            # WIN
        evaluate_alert_outcome(
            _alert(targets=[110]),
            [_bar(high=100, low=94)]),             # LOSS
        evaluate_alert_outcome(
            _alert(targets=[110], trigger_level=None),
            _flat_bars(5)),                         # OPEN
    ]
    s = summarize_backtest_results(results)
    assert s["total_alerts"]    == 3
    assert s["wins"]            == 1
    assert s["losses"]          == 1
    assert s["open"]            == 1
    assert s["invalid_results"] == 0
    assert s["win_rate_valid"]  == 50.0


# ---------------------------------------------------------------------------
# 12. summarize — by_tier grouping
# ---------------------------------------------------------------------------
def test_summarize_groups_by_tier():
    results = [
        evaluate_alert_outcome(
            _alert(tier="SNIPE_IT",   targets=[110]), [_bar(high=111, low=100)]),  # WIN
        evaluate_alert_outcome(
            _alert(tier="SNIPE_IT",   targets=[110]), [_bar(high=100, low=94)]),   # LOSS
        evaluate_alert_outcome(
            _alert(tier="STARTER",    targets=[110]), [_bar(high=111, low=100)]),  # WIN
        evaluate_alert_outcome(
            _alert(tier="NEAR_ENTRY", targets=[110], trigger_level=None),
            _flat_bars(5)),                                                          # OPEN
    ]
    by_tier = summarize_backtest_results(results)["by_tier"]
    assert by_tier["SNIPE_IT"]["count"]  == 2
    assert by_tier["SNIPE_IT"]["wins"]   == 1
    assert by_tier["SNIPE_IT"]["losses"] == 1
    assert by_tier["STARTER"]["count"]   == 1
    assert by_tier["STARTER"]["wins"]    == 1
    assert by_tier["NEAR_ENTRY"]["count"] == 1


# ---------------------------------------------------------------------------
# 13. summarize — by_risk_realism_state grouping
# ---------------------------------------------------------------------------
def test_summarize_groups_by_risk_realism_state():
    results = [
        evaluate_alert_outcome(
            _alert(risk_realism_state="healthy", targets=[110]),
            [_bar(high=111, low=100)]),   # WIN
        evaluate_alert_outcome(
            _alert(risk_realism_state="tight", targets=[110]),
            [_bar(high=100, low=94)]),    # LOSS
        evaluate_alert_outcome(
            _alert(risk_realism_state="fragile", targets=[110], trigger_level=None),
            _flat_bars(5)),               # OPEN
    ]
    by_rrs = summarize_backtest_results(results)["by_risk_realism_state"]
    assert by_rrs["healthy"]["count"]  == 1
    assert by_rrs["healthy"]["wins"]   == 1
    assert by_rrs["tight"]["count"]    == 1
    assert by_rrs["tight"]["losses"]   == 1
    assert by_rrs["fragile"]["count"]  == 1


# ---------------------------------------------------------------------------
# 14. summarize — by_retest_hold_combo grouping
# ---------------------------------------------------------------------------
def test_summarize_groups_by_retest_hold_combo():
    results = [
        evaluate_alert_outcome(
            _alert(retest_status="confirmed", hold_status="confirmed", targets=[110]),
            [_bar(high=111, low=100)]),   # WIN → confirmed/confirmed
        evaluate_alert_outcome(
            _alert(retest_status="partial", hold_status="partial", targets=[110]),
            [_bar(high=100, low=94)]),    # LOSS → partial/partial
        evaluate_alert_outcome(
            _alert(retest_status="missing", hold_status="missing", targets=[110],
                   trigger_level=None),
            _flat_bars(5)),               # OPEN → missing/missing
    ]
    by_combo = summarize_backtest_results(results)["by_retest_hold_combo"]
    assert "confirmed/confirmed" in by_combo
    assert "partial/partial"     in by_combo
    assert "missing/missing"     in by_combo
    assert by_combo["confirmed/confirmed"]["wins"]   == 1
    assert by_combo["partial/partial"]["losses"]     == 1
    assert by_combo["missing/missing"]["count"]      == 1


# ---------------------------------------------------------------------------
# 15. Import guard — src/backtest.py uses standard library only
# ---------------------------------------------------------------------------
def test_backtest_does_not_import_live_scanner_or_discord():
    p    = pathlib.Path("src/backtest.py")
    tree = ast.parse(p.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    forbidden = {"src", "discord", "yfinance", "requests", "aiohttp", "anthropic"}
    for imp in imports:
        root = imp.split(".")[0]
        assert root not in forbidden, (
            f"Forbidden import found in backtest.py: {imp!r}"
        )


# ---------------------------------------------------------------------------
# 16. NEAR_ENTRY below trigger — reclaims, then hits T1 (no overrejection)
# ---------------------------------------------------------------------------
def test_near_entry_below_trigger_can_be_evaluated_without_overrejecting():
    alert = _alert(
        tier="NEAR_ENTRY",
        scan_price=128.35,
        trigger_level=128.44,
        invalidation_level=125.0,
        targets=[140.0],
        retest_status="confirmed",
        hold_status="confirmed",
        risk_realism_state="healthy",
    )
    bars = [
        _bar(high=128.20, low=127.00),  # below trigger, no terminal hit
        _bar(high=129.00, low=128.10),  # trigger reclaimed
        _bar(high=141.00, low=129.00),  # T1 hit
    ]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == WIN_T1_BEFORE_INVALIDATION
    assert result["hit_trigger_first"] is True
    assert result["alert_tier"] == "NEAR_ENTRY"


# ---------------------------------------------------------------------------
# 17. Loss before trigger reclaim still counts as LOSS
# ---------------------------------------------------------------------------
def test_loss_before_trigger_counts_as_loss():
    alert = _alert(
        scan_price=128.35,
        trigger_level=128.44,
        invalidation_level=125.0,
        targets=[140.0],
    )
    bars = [
        _bar(high=128.00, low=124.50),  # low <= 125 → invalidation hit before trigger
    ]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == LOSS_INVALIDATION_BEFORE_T1
    assert result["hit_trigger_first"] is False
    assert result["hit_invalidation_before_t1"] is True


# ---------------------------------------------------------------------------
# 18. Horizon limits evaluation — T1 hit after horizon is not counted
# ---------------------------------------------------------------------------
def test_horizon_limits_evaluation():
    alert = _alert(scan_price=100, trigger_level=None, invalidation_level=95,
                   targets=[110])
    # First 10 bars: tight range (no hit). Bars 10–14: T1 hit.
    bars = [_bar(high=102, low=99)] * 10 + [_bar(high=111, low=100)] * 5
    result = evaluate_alert_outcome(alert, bars, horizon_bars=10)
    assert result["outcome_label"] == OPEN_NO_TERMINAL_HIT


# ---------------------------------------------------------------------------
# 19. Reference price falls back to trigger when scan_price is missing
# ---------------------------------------------------------------------------
def test_reference_price_falls_back_to_trigger_when_scan_price_missing():
    alert = _alert(
        scan_price=None,
        trigger_level=100.0,
        invalidation_level=95.0,
        targets=[110.0],
    )
    del alert["scan_price"]  # ensure the key is absent
    bars = [_bar(high=111, low=100)]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] != INVALID_DATA
    assert result["max_favorable_excursion"] is not None


# ---------------------------------------------------------------------------
# 20. Non-numeric OHLC returns INVALID_DATA
# ---------------------------------------------------------------------------
def test_invalid_non_numeric_ohlc_returns_invalid_data():
    alert = _alert(scan_price=100, invalidation_level=95, targets=[110])
    bars  = [{"open": "bad", "high": "data", "low": "here", "close": "none"}]
    result = evaluate_alert_outcome(alert, bars)
    assert result["outcome_label"] == INVALID_DATA
    assert "non-numeric" in result["reason"].lower()

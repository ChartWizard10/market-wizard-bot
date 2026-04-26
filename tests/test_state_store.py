"""State store and deduplication tests — Phase 6."""

import json
import pathlib
from datetime import datetime, timedelta

import pytest

from src.state_store import (
    check_alert,
    load,
    make_dedup_key,
    record_alert,
    save,
    _is_material_change,
    _tier_rank,
    _within_cooldown,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path=None, cooldown=240, trigger_pct=0.25, inval_pct=0.25):
    path = str(tmp_path / "alert_state.json") if tmp_path else "data/alert_state.json"
    return {
        "state": {
            "state_file": path,
            "cooldown_minutes": cooldown,
            "max_memory_entries": 500,
            "trigger_material_change_pct": trigger_pct,
            "invalidation_material_change_pct": inval_pct,
        }
    }


def _tiering(
    ticker="AAPL",
    final_tier="SNIPE_IT",
    channel="#snipe-signals",
    safe=True,
    score=90,
    trigger=182.50,
    invalidation=178.20,
    **extra,
):
    return {
        "final_tier": final_tier,
        "final_discord_channel": channel,
        "safe_for_alert": safe,
        "score": score,
        "final_signal": {
            "ticker": ticker,
            "tier": final_tier,
            "trigger_level": trigger,
            "invalidation_level": invalidation,
            "score": score,
            "reason": "Test signal",
            "discord_channel": channel,
            **extra,
        },
    }


def _state_with(ticker="AAPL", **overrides):
    """Build a state dict with a prior alert for ticker."""
    ticker_state = {
        "last_alerted_tier":        "SNIPE_IT",
        "last_alerted_at":          _recent(5),
        "last_trigger_level":       182.50,
        "last_invalidation_level":  178.20,
        "last_score":               90,
        "last_reason":              "prior signal",
        "last_discord_channel":     "#snipe-signals",
        "last_dedup_key":           f"{ticker}|SNIPE_IT|182.50|178.20",
        "scan_id":                  "s1",
        "alert_history":            [],
    }
    ticker_state.update(overrides)
    return {"tickers": {ticker: ticker_state}, "meta": {"total_alerts": 1}}


def _empty():
    return {"tickers": {}, "meta": {}}


def _recent(minutes_ago=5):
    return (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()


def _old(minutes_ago=300):
    return (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()


# ---------------------------------------------------------------------------
# 1. Initializes empty state when file missing
# ---------------------------------------------------------------------------

def test_initializes_empty_state_when_file_missing(tmp_path):
    cfg = _cfg(tmp_path)
    state = load(cfg)
    assert state["tickers"] == {}
    assert "meta" in state
    assert state["meta"]["total_alerts"] == 0


# ---------------------------------------------------------------------------
# 2. Creates data directory safely
# ---------------------------------------------------------------------------

def test_creates_data_directory_safely(tmp_path):
    nested = tmp_path / "deep" / "nested"
    cfg = {"state": {"state_file": str(nested / "alert_state.json"), "cooldown_minutes": 240}}
    state = {"tickers": {}, "meta": {"total_alerts": 0, "created_at": "", "last_updated": ""}}
    save(state, cfg)
    assert (nested / "alert_state.json").exists()


# ---------------------------------------------------------------------------
# 3. Loads existing valid state
# ---------------------------------------------------------------------------

def test_loads_existing_valid_state(tmp_path):
    cfg = _cfg(tmp_path)
    original = {
        "tickers": {"AAPL": {"last_alerted_tier": "SNIPE_IT", "alert_history": []}},
        "meta": {"total_alerts": 3, "created_at": "", "last_updated": ""},
    }
    path = pathlib.Path(cfg["state"]["state_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(original))
    state = load(cfg)
    assert state["tickers"]["AAPL"]["last_alerted_tier"] == "SNIPE_IT"
    assert state["meta"]["total_alerts"] == 3


# ---------------------------------------------------------------------------
# 4. Corrupt state file is backed up and reset safely
# ---------------------------------------------------------------------------

def test_corrupt_state_file_backed_up_and_reset(tmp_path):
    cfg = _cfg(tmp_path)
    path = pathlib.Path(cfg["state"]["state_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{{not valid json{{{{")
    state = load(cfg)
    assert state["tickers"] == {}           # reset to empty
    assert not path.exists()               # original removed (backed up)
    backups = list(tmp_path.glob("alert_state.json.corrupt.*"))
    assert len(backups) == 1               # backup created


# ---------------------------------------------------------------------------
# 5. Saves state after alert
# ---------------------------------------------------------------------------

def test_saves_state_after_alert(tmp_path):
    cfg = _cfg(tmp_path)
    state = {"tickers": {"NVDA": {"last_alerted_tier": "STARTER"}}, "meta": {}}
    save(state, cfg)
    path = pathlib.Path(cfg["state"]["state_file"])
    loaded = json.loads(path.read_text())
    assert loaded["tickers"]["NVDA"]["last_alerted_tier"] == "STARTER"


# ---------------------------------------------------------------------------
# 5a. load() returns empty state when parent directory does not exist
# ---------------------------------------------------------------------------

def test_load_when_parent_dir_missing(tmp_path):
    """load() must not crash and must return empty state when parent dir does not exist."""
    missing_parent = tmp_path / "nonexistent" / "deep"
    cfg = {"state": {"state_file": str(missing_parent / "state.json"), "cooldown_minutes": 240}}
    state = load(cfg)
    assert state["tickers"] == {}
    assert "meta" in state


# ---------------------------------------------------------------------------
# 5b. save() creates missing parent directory then persists; load() reads back
# ---------------------------------------------------------------------------

def test_persists_state_after_creating_missing_dir(tmp_path):
    """Full round-trip: save() creates dir, writes data; load() reads it correctly."""
    missing_dir = tmp_path / "auto_created" / "nested"
    cfg = {"state": {"state_file": str(missing_dir / "state.json"), "cooldown_minutes": 240}}

    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), cfg)
    save(state, cfg)
    assert (missing_dir / "state.json").exists()

    loaded = load(cfg)
    assert loaded["tickers"]["AAPL"]["last_alerted_tier"] == "SNIPE_IT"


# ---------------------------------------------------------------------------
# 6. WAIT never alerts
# ---------------------------------------------------------------------------

def test_wait_never_alerts():
    tr = _tiering(final_tier="WAIT", channel="none", safe=False)
    result = check_alert(tr, _empty(), _cfg())
    assert result["should_alert"] is False
    assert result["reason"] == "wait_no_alert"


def test_wait_never_alerts_even_with_manual_override():
    tr = _tiering(final_tier="WAIT", channel="none", safe=False)
    result = check_alert(tr, _empty(), _cfg(), manual_override=True)
    assert result["should_alert"] is False
    assert result["reason"] == "wait_no_alert"


# ---------------------------------------------------------------------------
# 7. safe_for_alert false never alerts
# ---------------------------------------------------------------------------

def test_unsafe_for_alert_suppressed():
    tr = _tiering(final_tier="SNIPE_IT", safe=False)
    result = check_alert(tr, _empty(), _cfg())
    assert result["should_alert"] is False
    assert result["reason"] == "unsafe_for_alert"


# ---------------------------------------------------------------------------
# 8. final_discord_channel none never alerts
# ---------------------------------------------------------------------------

def test_channel_none_never_alerts():
    tr = _tiering(final_tier="NEAR_ENTRY", channel="none", safe=True)
    result = check_alert(tr, _empty(), _cfg())
    assert result["should_alert"] is False
    assert result["reason"] == "unsafe_for_alert"


# ---------------------------------------------------------------------------
# 9. New safe signal alerts
# ---------------------------------------------------------------------------

def test_new_signal_alerts():
    tr = _tiering()
    result = check_alert(tr, _empty(), _cfg())
    assert result["should_alert"] is True
    assert result["reason"] == "new_signal"


def test_new_ticker_no_prior_history_alerts():
    tr = _tiering(ticker="MSFT")
    state = _state_with("AAPL")     # AAPL has history, MSFT does not
    result = check_alert(tr, state, _cfg())
    assert result["should_alert"] is True
    assert result["reason"] == "new_signal"


# ---------------------------------------------------------------------------
# 10. Exact duplicate inside cooldown suppresses
# ---------------------------------------------------------------------------

def test_exact_duplicate_inside_cooldown_suppresses():
    tr = _tiering(trigger=182.50, invalidation=178.20)
    state = _state_with(last_alerted_at=_recent(5))   # 5 min ago, cooldown=240
    result = check_alert(tr, state, _cfg(cooldown=240))
    assert result["should_alert"] is False
    assert result["reason"] == "duplicate_suppressed"


# ---------------------------------------------------------------------------
# 11. Exact duplicate after cooldown can re-alert
# ---------------------------------------------------------------------------

def test_exact_duplicate_after_cooldown_re_alerts():
    tr = _tiering(trigger=182.50, invalidation=178.20)
    state = _state_with(last_alerted_at=_old(300))    # 300 min ago, cooldown=60
    result = check_alert(tr, state, _cfg(cooldown=60))
    assert result["should_alert"] is True
    assert result["reason"] == "cooldown_expired"


# ---------------------------------------------------------------------------
# 12. NEAR_ENTRY → STARTER re-alerts as tier improvement
# ---------------------------------------------------------------------------

def test_near_entry_to_starter_re_alerts():
    tr = _tiering(
        final_tier="STARTER",
        channel="#starter-signals",
        trigger=182.50,
        invalidation=178.20,
    )
    state = _state_with(last_alerted_tier="NEAR_ENTRY", last_alerted_at=_recent(5))
    result = check_alert(tr, state, _cfg(cooldown=240))
    assert result["should_alert"] is True
    assert result["reason"] == "tier_improved"


# ---------------------------------------------------------------------------
# 13. STARTER → SNIPE_IT re-alerts as tier improvement
# ---------------------------------------------------------------------------

def test_starter_to_snipe_it_re_alerts():
    tr = _tiering(
        final_tier="SNIPE_IT",
        channel="#snipe-signals",
        trigger=182.50,
        invalidation=178.20,
    )
    state = _state_with(last_alerted_tier="STARTER", last_alerted_at=_recent(5))
    result = check_alert(tr, state, _cfg(cooldown=240))
    assert result["should_alert"] is True
    assert result["reason"] == "tier_improved"


# ---------------------------------------------------------------------------
# 14. SNIPE_IT → STARTER does NOT re-alert as tier improvement
# ---------------------------------------------------------------------------

def test_snipe_to_starter_not_tier_improvement():
    tr = _tiering(
        final_tier="STARTER",
        channel="#starter-signals",
        trigger=182.50,
        invalidation=178.20,
    )
    # Last alert was SNIPE_IT (higher) — degradation, should NOT trigger tier_improved
    state = _state_with(last_alerted_tier="SNIPE_IT", last_alerted_at=_recent(5))
    result = check_alert(tr, state, _cfg(cooldown=240))
    assert result["reason"] != "tier_improved"
    # Inside cooldown with no material change → suppressed
    assert result["should_alert"] is False
    assert result["reason"] == "duplicate_suppressed"


# ---------------------------------------------------------------------------
# 15. Trigger material change re-alerts
# ---------------------------------------------------------------------------

def test_trigger_material_change_re_alerts():
    # 0.25% threshold on a $182.50 base → $0.46 minimum change
    # Old trigger=182.50, new trigger=185.00 → 1.37% change → material
    tr = _tiering(trigger=185.00, invalidation=178.20)
    state = _state_with(
        last_trigger_level=182.50,
        last_invalidation_level=178.20,
        last_alerted_at=_recent(5),
    )
    result = check_alert(tr, state, _cfg(cooldown=240, trigger_pct=0.25))
    assert result["should_alert"] is True
    assert result["reason"] == "trigger_changed"


# ---------------------------------------------------------------------------
# 16. Invalidation material change re-alerts
# ---------------------------------------------------------------------------

def test_invalidation_material_change_re_alerts():
    tr = _tiering(trigger=182.50, invalidation=175.00)   # was 178.20 → 1.8% change
    state = _state_with(
        last_trigger_level=182.50,
        last_invalidation_level=178.20,
        last_alerted_at=_recent(5),
    )
    result = check_alert(tr, state, _cfg(cooldown=240, inval_pct=0.25))
    assert result["should_alert"] is True
    assert result["reason"] == "invalidation_changed"


# ---------------------------------------------------------------------------
# 17. Non-material trigger change suppresses
# ---------------------------------------------------------------------------

def test_non_material_trigger_change_suppresses():
    # Change of 0.01 on $182.50 → 0.005% → well below 0.25% threshold
    tr = _tiering(trigger=182.51, invalidation=178.20)
    state = _state_with(
        last_alerted_tier="SNIPE_IT",
        last_trigger_level=182.50,
        last_invalidation_level=178.20,
        last_alerted_at=_recent(5),
    )
    result = check_alert(tr, state, _cfg(cooldown=240, trigger_pct=0.25))
    assert result["should_alert"] is False
    assert result["reason"] == "duplicate_suppressed"


# ---------------------------------------------------------------------------
# 18. Non-material invalidation change suppresses
# ---------------------------------------------------------------------------

def test_non_material_invalidation_change_suppresses():
    tr = _tiering(trigger=182.50, invalidation=178.21)   # 0.006% change
    state = _state_with(
        last_alerted_tier="SNIPE_IT",
        last_trigger_level=182.50,
        last_invalidation_level=178.20,
        last_alerted_at=_recent(5),
    )
    result = check_alert(tr, state, _cfg(cooldown=240, inval_pct=0.25))
    assert result["should_alert"] is False
    assert result["reason"] == "duplicate_suppressed"


# ---------------------------------------------------------------------------
# 19. manual_override alerts safe non-WAIT signal
# ---------------------------------------------------------------------------

def test_manual_override_alerts_safe_signal():
    tr = _tiering()
    state = _state_with(last_alerted_at=_recent(5))      # inside cooldown
    result = check_alert(tr, state, _cfg(cooldown=240), manual_override=True)
    assert result["should_alert"] is True
    assert result["reason"] == "manual_override"


# ---------------------------------------------------------------------------
# 20. manual_override cannot alert WAIT
# ---------------------------------------------------------------------------

def test_manual_override_cannot_alert_wait():
    tr = _tiering(final_tier="WAIT", channel="none", safe=False)
    result = check_alert(tr, _empty(), _cfg(), manual_override=True)
    assert result["should_alert"] is False
    assert result["reason"] == "wait_no_alert"


# ---------------------------------------------------------------------------
# 21. manual_override cannot alert unsafe signal
# ---------------------------------------------------------------------------

def test_manual_override_cannot_alert_unsafe():
    tr = _tiering(final_tier="SNIPE_IT", safe=False)
    result = check_alert(tr, _empty(), _cfg(), manual_override=True)
    assert result["should_alert"] is False
    assert result["reason"] == "unsafe_for_alert"


# ---------------------------------------------------------------------------
# 22. Dedup key normalizes levels consistently
# ---------------------------------------------------------------------------

def test_dedup_key_normalizes_nulls():
    key = make_dedup_key("AAPL", "SNIPE_IT", None, None)
    assert key == "AAPL|SNIPE_IT|null|null"


def test_dedup_key_normalizes_floats_to_two_decimals():
    key1 = make_dedup_key("AAPL", "SNIPE_IT", 182.5, 178.2)
    key2 = make_dedup_key("AAPL", "SNIPE_IT", 182.50, 178.20)
    assert key1 == key2
    assert "182.50" in key1
    assert "178.20" in key1


def test_dedup_key_different_tiers_differ():
    k1 = make_dedup_key("AAPL", "SNIPE_IT", 182.50, 178.20)
    k2 = make_dedup_key("AAPL", "STARTER", 182.50, 178.20)
    assert k1 != k2


def test_dedup_key_different_triggers_differ():
    k1 = make_dedup_key("AAPL", "SNIPE_IT", 182.50, 178.20)
    k2 = make_dedup_key("AAPL", "SNIPE_IT", 185.00, 178.20)
    assert k1 != k2


# ---------------------------------------------------------------------------
# 23. alert_history appends entries
# ---------------------------------------------------------------------------

def test_alert_history_appends():
    tr = _tiering()
    state = _empty()
    state = record_alert("AAPL", tr, state, _cfg())
    assert len(state["tickers"]["AAPL"]["alert_history"]) == 1
    state = record_alert("AAPL", tr, state, _cfg())
    assert len(state["tickers"]["AAPL"]["alert_history"]) == 2


def test_alert_history_trimmed_to_max_entries():
    cfg = {"state": {"state_file": "x", "max_memory_entries": 3, "cooldown_minutes": 240}}
    tr = _tiering()
    state = _empty()
    for _ in range(5):
        state = record_alert("AAPL", tr, state, cfg)
    assert len(state["tickers"]["AAPL"]["alert_history"]) == 3


# ---------------------------------------------------------------------------
# 24. State schema stores required fields
# ---------------------------------------------------------------------------

def test_state_schema_required_fields():
    tr = _tiering()
    state = _empty()
    state = record_alert("AAPL", tr, state, _cfg())
    ts = state["tickers"]["AAPL"]
    for field in (
        "last_alerted_tier", "last_alerted_at", "last_trigger_level",
        "last_invalidation_level", "last_score", "last_reason",
        "last_discord_channel", "scan_id", "alert_history",
    ):
        assert field in ts, f"Missing field: {field}"


def test_state_schema_history_entry_fields():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    entry = state["tickers"]["AAPL"]["alert_history"][0]
    for field in ("ticker", "tier", "alerted_at", "trigger_level",
                  "invalidation_level", "score", "reason", "dedup_key"):
        assert field in entry, f"Missing history field: {field}"


# ---------------------------------------------------------------------------
# 25. state_store does not import Discord, scheduler, Claude, or yfinance
# ---------------------------------------------------------------------------

def test_no_forbidden_imports_in_state_store():
    import re
    source = pathlib.Path("src/state_store.py").read_text()
    forbidden = ["discord", "scheduler", "anthropic", "yfinance", "claude_client"]
    for name in forbidden:
        # Check for actual import statements only — not docstring mentions
        assert not re.search(
            rf"^(?:import|from)\s+{re.escape(name)}", source, re.MULTILINE
        ), f"Forbidden import '{name}' found in state_store.py"


# ---------------------------------------------------------------------------
# 26. Disabled indicators absent from state_store logic
# ---------------------------------------------------------------------------

def test_no_disabled_indicators_in_state_store():
    import re
    source = pathlib.Path("src/state_store.py").read_text()
    for indicator in ("rsi", "macd", "bollinger_bands", "stochastic"):
        # Word-boundary check avoids false positives like "rsi" inside "persist"
        assert not re.search(rf"\b{re.escape(indicator)}\b", source, re.IGNORECASE), (
            f"Disabled indicator '{indicator}' found in src/state_store.py"
        )


# ---------------------------------------------------------------------------
# Extra: save failure does not crash
# ---------------------------------------------------------------------------

def test_state_write_failure_no_crash(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    state = {"tickers": {}, "meta": {}}

    def bad_write(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("pathlib.Path.write_text", bad_write)
    save(state, cfg)          # must not raise


# ---------------------------------------------------------------------------
# Extra: previous_state returned in decision
# ---------------------------------------------------------------------------

def test_decision_includes_previous_state():
    tr = _tiering()
    state = _state_with()
    result = check_alert(tr, state, _cfg(cooldown=240))
    assert "previous_state" in result
    assert result["previous_state"] is not None


# ---------------------------------------------------------------------------
# Extra: record_alert updates meta total_alerts
# ---------------------------------------------------------------------------

def test_record_alert_increments_total_alerts():
    tr = _tiering()
    state = _empty()
    state["meta"]["total_alerts"] = 5
    state = record_alert("AAPL", tr, state, _cfg())
    assert state["meta"]["total_alerts"] == 6


# ---------------------------------------------------------------------------
# Extra: _is_material_change covers edge cases
# ---------------------------------------------------------------------------

def test_material_change_both_null():
    assert _is_material_change(None, None, 0.0025) is False


def test_material_change_one_null():
    assert _is_material_change(None, 182.50, 0.0025) is True
    assert _is_material_change(182.50, None, 0.0025) is True


def test_material_change_small():
    assert _is_material_change(100.0, 100.1, 0.0025) is False   # 0.1% < 0.25%


def test_material_change_large():
    assert _is_material_change(100.0, 101.0, 0.0025) is True    # 1.0% > 0.25%


# ---------------------------------------------------------------------------
# Extra: _within_cooldown handles edge cases
# ---------------------------------------------------------------------------

def test_within_cooldown_no_prior():
    assert _within_cooldown(None, 60) is False


def test_within_cooldown_recent():
    recent = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    assert _within_cooldown(recent, 60) is True


def test_within_cooldown_expired():
    old = (datetime.utcnow() - timedelta(minutes=120)).isoformat()
    assert _within_cooldown(old, 60) is False

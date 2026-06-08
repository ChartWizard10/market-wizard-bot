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
    record_outcome,
    save,
    _is_material_change,
    _OUTCOME_FIELDS,
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


# ---------------------------------------------------------------------------
# Phase 13.3B — record_alert field storage contract (23 tests)
# ---------------------------------------------------------------------------

def test_record_alert_stores_targets():
    targets = [{"label": "T1", "level": 192.0, "reason": "FVG top"}]
    tr = _tiering(targets=targets)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["targets"] == targets


def test_record_alert_missing_targets_stored_as_empty_list():
    tr_none = _tiering(targets=None)
    state_none = record_alert("AAPL", tr_none, _empty(), _cfg())
    assert state_none["tickers"]["AAPL"]["alert_history"][0]["targets"] == []

    tr_absent = _tiering()
    state_absent = record_alert("AAPL", tr_absent, _empty(), _cfg())
    assert state_absent["tickers"]["AAPL"]["alert_history"][0]["targets"] == []


def test_record_alert_stores_scan_price():
    tr = _tiering(scan_price=183.50)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["scan_price"] == 183.50


def test_record_alert_scan_price_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["scan_price"] is None


def test_record_alert_stores_risk_reward():
    tr = _tiering(risk_reward=3.8)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["risk_reward"] == 3.8


def test_record_alert_stores_risk_realism_state():
    tr = _tiering(risk_realism_state="realistic")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["risk_realism_state"] == "realistic"


def test_record_alert_stores_risk_distance_fields():
    tr = _tiering(risk_distance=4.30, risk_distance_pct=2.35)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["risk_distance"] == 4.30
    assert rec["risk_distance_pct"] == 2.35


def test_record_alert_stores_price_to_invalidation_fields():
    tr = _tiering(
        current_price_to_invalidation=3.80,
        current_price_to_invalidation_pct=2.10,
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["current_price_to_invalidation"] == 3.80
    assert rec["current_price_to_invalidation_pct"] == 2.10


def test_record_alert_stores_retest_and_hold_status():
    tr = _tiering(retest_status="confirmed", hold_status="confirmed")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["retest_status"] == "confirmed"
    assert rec["hold_status"] == "confirmed"


def test_record_alert_stores_current_acceptance():
    tr = _tiering(current_acceptance="strong")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["current_acceptance"] == "strong"


def test_record_alert_stores_overhead_status():
    tr = _tiering(overhead_status="clear")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["overhead_status"] == "clear"


def test_record_alert_stores_volume_behavior_and_ratio():
    # Phase 1A — evidence capture: alert_history persists volume fields so future
    # sponsorship-quality backtesting can tag records without re-deriving them.
    tr = _tiering(volume_behavior="expansion", volume_ratio=1.45)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["volume_behavior"] == "expansion"
    assert rec["volume_ratio"] == 1.45


def test_record_alert_volume_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["volume_behavior"] is None
    assert rec["volume_ratio"] is None


# ---------------------------------------------------------------------------
# Phase 1B — VCP evidence persistence (observational only)
# ---------------------------------------------------------------------------
# These tests verify the alert_history record stores all ten vcp_* fields so
# future sponsorship/VCP backtesting can tag historical alerts. The fields
# are read-only metadata — recording them does not affect dedup, cooldown,
# tier, scoring, routing, or capital.


def test_record_alert_stores_vcp_fields():
    tr = _tiering(
        vcp_status="CONFIRMED",
        vcp_prior_advance_pct=78.5,
        vcp_contractions_count=3,
        vcp_range_contraction=True,
        vcp_contraction_sequence=[12.0, 7.5, 4.2],
        vcp_volume_dryup=True,
        vcp_volume_ratio=0.72,
        vcp_ma_alignment="SUPPORTIVE",
        vcp_pivot_level=182.50,
        vcp_failure_flag=False,
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]

    assert rec["vcp_status"] == "CONFIRMED"
    assert rec["vcp_prior_advance_pct"] == 78.5
    assert rec["vcp_contractions_count"] == 3
    assert rec["vcp_range_contraction"] is True
    assert rec["vcp_contraction_sequence"] == [12.0, 7.5, 4.2]
    assert rec["vcp_volume_dryup"] is True
    assert rec["vcp_volume_ratio"] == 0.72
    assert rec["vcp_ma_alignment"] == "SUPPORTIVE"
    assert rec["vcp_pivot_level"] == 182.50
    assert rec["vcp_failure_flag"] is False


def test_record_alert_vcp_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]

    for field in (
        "vcp_status",
        "vcp_prior_advance_pct",
        "vcp_contractions_count",
        "vcp_range_contraction",
        "vcp_contraction_sequence",
        "vcp_volume_dryup",
        "vcp_volume_ratio",
        "vcp_ma_alignment",
        "vcp_pivot_level",
        "vcp_failure_flag",
    ):
        assert field in rec, f"VCP field missing from history record: {field!r}"
        assert rec[field] is None


def test_record_alert_vcp_failure_flag_does_not_affect_dedup_key():
    # Recording an alert with vcp_failure_flag=True must produce the same
    # dedup_key as one without it. dedup is structural; VCP is evidence.
    tr_no_vcp = _tiering(trigger=182.50, invalidation=178.20)
    tr_with_vcp = _tiering(
        trigger=182.50, invalidation=178.20,
        vcp_status="INVALID", vcp_failure_flag=True,
    )
    s1 = record_alert("AAPL", tr_no_vcp,   _empty(), _cfg())
    s2 = record_alert("AAPL", tr_with_vcp, _empty(), _cfg())

    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"]


# ---------------------------------------------------------------------------
# Phase 1C-P1 — Break & Retest doctrine evidence persistence (observational only)
# ---------------------------------------------------------------------------
# These tests verify the alert_history record stores the six doctrine organs plus
# the deferred 1H field so future entry-quality backtesting can tag historical
# alerts. The fields are read-only metadata — recording them does not affect
# dedup, cooldown, tier, scoring, routing, or capital.

_BRT_HISTORY_FIELDS = (
    "entry_family",
    "retest_quality",
    "consumption_risk",
    "level_authority",
    "zone_freshness",
    "break_retest_state",
    "one_hour_momentum_repair",
)


def test_record_alert_stores_brt_fields():
    tr = _tiering(
        entry_family="zone_core",
        retest_quality="clean_bounce",
        consumption_risk="low",
        level_authority="strong",
        zone_freshness="fresh",
        break_retest_state="retesting",
        one_hour_momentum_repair="deferred_requires_1h",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]

    assert rec["entry_family"] == "zone_core"
    assert rec["retest_quality"] == "clean_bounce"
    assert rec["consumption_risk"] == "low"
    assert rec["level_authority"] == "strong"
    assert rec["zone_freshness"] == "fresh"
    assert rec["break_retest_state"] == "retesting"
    assert rec["one_hour_momentum_repair"] == "deferred_requires_1h"


def test_record_alert_brt_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    for field in _BRT_HISTORY_FIELDS:
        assert field in rec, f"BRT field missing from history record: {field!r}"
        assert rec[field] is None


def test_record_alert_brt_fields_do_not_affect_dedup_key():
    # Recording adverse BRT evidence must produce the same dedup_key as a record
    # without it. dedup is structural; BRT organs are evidence.
    tr_plain = _tiering(trigger=182.50, invalidation=178.20)
    tr_brt = _tiering(
        trigger=182.50, invalidation=178.20,
        entry_family="failed_break_conversion",
        consumption_risk="high",
        break_retest_state="failed",
    )
    s1 = record_alert("AAPL", tr_plain, _empty(), _cfg())
    s2 = record_alert("AAPL", tr_brt,   _empty(), _cfg())
    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"]


def test_record_alert_stores_setup_context_fields():
    tr = _tiering(
        setup_family="continuation",
        structure_event="BOS",
        trend_state="fresh_expansion",
        zone_type="FVG",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["setup_family"] == "continuation"
    assert rec["structure_event"] == "BOS"
    assert rec["trend_state"] == "fresh_expansion"
    assert rec["zone_type"] == "FVG"


def test_record_alert_stores_sma_value_alignment():
    tr = _tiering(sma_value_alignment="supportive")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["sma_value_alignment"] == "supportive"


def test_record_alert_stores_near_entry_fields():
    tr = _tiering(
        missing_conditions=["retest_needed"],
        upgrade_trigger="Close above 182 on volume",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["missing_conditions"] == ["retest_needed"]
    assert rec["upgrade_trigger"] == "Close above 182 on volume"


def test_record_alert_stores_capital_action():
    tr = _tiering(capital_action="full_quality_allowed")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["capital_action"] == "full_quality_allowed"


def test_record_alert_stores_sanitized_fields():
    tr = _tiering(
        sanitized_reason="Reclaim above 182 FVG with volume expansion",
        sanitized_next_action="Wait for confirmed retest before entry",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["sanitized_reason"] == "Reclaim above 182 FVG with volume expansion"
    assert rec["sanitized_next_action"] == "Wait for confirmed retest before entry"


def test_record_alert_stores_original_claude_tier():
    tr = _tiering()
    tr["original_claude_tier"] = "SNIPE_IT"
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["original_claude_tier"] == "SNIPE_IT"


def test_record_alert_stores_applied_vetoes():
    tr = _tiering()
    tr["applied_vetoes"] = ["rr_too_low", "retest_missing"]
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["applied_vetoes"] == ["rr_too_low", "retest_missing"]


def test_record_alert_old_9field_record_still_readable():
    """Old 9-field history record coexists correctly with new 32-field records."""
    old_record = {
        "ticker": "AAPL", "tier": "NEAR_ENTRY",
        "alerted_at": "2024-01-01T09:00:00",
        "trigger_level": 180.0, "invalidation_level": 175.0,
        "score": 65, "reason": "old alert",
        "dedup_key": "AAPL|NEAR_ENTRY|180.0|175.0", "scan_id": "s0",
    }
    state = _empty()
    state["tickers"]["AAPL"] = {
        "last_alerted_tier": "NEAR_ENTRY",
        "last_alerted_at": "2024-01-01T09:00:00",
        "last_trigger_level": 180.0,
        "last_invalidation_level": 175.0,
        "last_score": 65,
        "last_reason": "old alert",
        "last_discord_channel": "#near-entry-watch",
        "last_dedup_key": "AAPL|NEAR_ENTRY|180.0|175.0",
        "scan_id": "s0",
        "alert_history": [old_record],
    }
    tr = _tiering(targets=[{"label": "T1", "level": 192.0, "reason": "FVG"}])
    state = record_alert("AAPL", tr, state, _cfg())
    history = state["tickers"]["AAPL"]["alert_history"]
    assert len(history) == 2
    assert history[0]["tier"] == "NEAR_ENTRY"
    assert history[0]["score"] == 65
    assert "targets" not in history[0]
    assert history[1]["tier"] == "SNIPE_IT"
    assert history[1]["targets"] == [{"label": "T1", "level": 192.0, "reason": "FVG"}]


def test_record_alert_stores_final_discord_channel():
    tr = _tiering(channel="#snipe-signals")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["final_discord_channel"] == "#snipe-signals"


def test_record_alert_backtest_round_trip(tmp_path):
    """Record → normalize → evaluate_alert_outcome is not INVALID_DATA when targets present."""
    import sys as _sys
    scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent / "scripts")
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)
    import backtest_alert_history as _bah
    from src.backtest import evaluate_alert_outcome, INVALID_DATA, WIN_T1_BEFORE_INVALIDATION

    targets = [{"label": "T1", "level": 200.0, "reason": "FVG top"}]
    tr = _tiering(
        trigger=182.50, invalidation=178.20,
        scan_price=183.50, targets=targets,
    )
    state = record_alert("AAPL", tr, _empty(), _cfg(tmp_path))
    raw_rec = state["tickers"]["AAPL"]["alert_history"][0]

    normalized = _bah.normalize_alert_record(raw_rec)
    future_bars = [{"open": 184.0, "high": 205.0, "low": 183.0, "close": 200.0}]
    result = evaluate_alert_outcome(normalized, future_bars)

    assert result["outcome_label"] != INVALID_DATA
    assert result["outcome_label"] == WIN_T1_BEFORE_INVALIDATION


def test_record_alert_baseline_fields_unchanged():
    """All 9 Phase 6 baseline fields are still present and correct after 13.3B expansion."""
    tr = _tiering(ticker="AAPL", final_tier="SNIPE_IT", score=90,
                  trigger=182.50, invalidation=178.20)
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="scan-001")
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["ticker"] == "AAPL"
    assert rec["tier"] == "SNIPE_IT"
    assert "alerted_at" in rec
    assert rec["trigger_level"] == 182.50
    assert rec["invalidation_level"] == 178.20
    assert rec["score"] == 90
    assert rec["reason"] == "Test signal"
    assert "dedup_key" in rec
    assert rec["scan_id"] == "scan-001"


def test_record_alert_no_live_behavior_keywords():
    """state_store.py must not import or invoke live network, API, or Discord behavior."""
    source_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "state_store.py"
    lines = source_path.read_text().splitlines()
    non_comment = [ln for ln in lines if not ln.strip().startswith("#")]
    joined = "\n".join(non_comment)
    # Check executable usage patterns (imports and call sites), not bare words that
    # may appear in docstrings stating what the module deliberately avoids.
    forbidden = [
        "import yfinance",
        "yfinance.",
        "import anthropic",
        "anthropic.",
        "discord.send",
        "requests.get",
        "urllib.request",
    ]
    for keyword in forbidden:
        assert keyword not in joined, (
            f"Forbidden live-behavior keyword {keyword!r} found in state_store.py"
        )


# ---------------------------------------------------------------------------
# Phase 14C.5 — Observation Ledger: alert_id + outcome slots + record_outcome
# ---------------------------------------------------------------------------

def test_record_alert_initializes_outcome_fields_to_none():
    """All 7 observational outcome fields start as None on a fresh record."""
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    for field in _OUTCOME_FIELDS:
        assert field in rec, f"{field} missing from record"
        assert rec[field] is None, f"{field} should initialize to None"


def test_record_alert_assigns_stable_alert_id():
    """Each record carries an immutable alert_id built from scan_id|ticker|ts."""
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="scan-001")
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["alert_id"].startswith("scan-001|AAPL|")
    assert rec["alert_id"].endswith(rec["alerted_at"])


def test_alert_id_does_not_affect_dedup_key():
    """Adding alert_id leaves the dedup key identical to the legacy form."""
    tr = _tiering(trigger=182.50, invalidation=178.20)
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="scan-xyz")
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["dedup_key"] == make_dedup_key("AAPL", "SNIPE_IT", 182.50, 178.20)
    # alert_id is not a component of the dedup key
    assert rec["alert_id"] not in rec["dedup_key"]


def test_record_alert_stores_safe_for_alert_flag():
    """The observation ledger captures the tiering safe_for_alert verdict."""
    tr = _tiering(safe=True)
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["safe_for_alert"] is True


def test_record_outcome_writes_only_outcome_fields():
    """record_outcome overwrites the 7 outcome fields and nothing else."""
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="s1")
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    alert_id = rec["alert_id"]

    outcome = {
        "tp1_hit": True, "tp2_hit": False, "tp3_hit": None,
        "invalidated": False, "mfe_pct": 4.2, "mae_pct": -1.1,
        "outcome_updated_at": "2026-06-05T12:00:00+00:00",
    }
    record_outcome("AAPL", alert_id, outcome, state)
    rec2 = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec2["tp1_hit"] is True
    assert rec2["tp2_hit"] is False
    assert rec2["mfe_pct"] == 4.2
    assert rec2["mae_pct"] == -1.1
    assert rec2["outcome_updated_at"] == "2026-06-05T12:00:00+00:00"


def test_record_outcome_preserves_all_decision_fields():
    """record_outcome must never alter any decision-path field."""
    tr = _tiering(
        ticker="AAPL", final_tier="SNIPE_IT", channel="#snipe-signals",
        safe=True, score=90, trigger=182.50, invalidation=178.20,
        capital_action="DEPLOY_FULL",
        weekly_trend_state="advancing",
        four_hour_market_state="EXPANSION",
    )
    tr["campaign_id"] = "AAPL|continuation|ob|178|178.2"
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="s1")
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    alert_id = rec["alert_id"]

    before = {
        "tier": rec["tier"],
        "trigger_level": rec["trigger_level"],
        "invalidation_level": rec["invalidation_level"],
        "score": rec["score"],
        "dedup_key": rec["dedup_key"],
        "capital_action": rec["capital_action"],
        "final_discord_channel": rec["final_discord_channel"],
        "safe_for_alert": rec["safe_for_alert"],
        "weekly_trend_state": rec["weekly_trend_state"],
        "four_hour_market_state": rec["four_hour_market_state"],
    }
    # Attempt to also smuggle decision-path keys through outcome_dict — ignored.
    record_outcome("AAPL", alert_id, {
        "tp1_hit": True, "outcome_updated_at": "2026-06-05T12:00:00+00:00",
        "tier": "WAIT", "final_discord_channel": "none", "score": 0,
        "capital_action": "BLOCK", "safe_for_alert": False,
    }, state)

    rec2 = state["tickers"]["AAPL"]["alert_history"][0]
    for key, val in before.items():
        assert rec2[key] == val, f"decision field {key} was mutated"
    assert rec2["tp1_hit"] is True  # the legitimate outcome write applied


def test_record_outcome_noop_for_unknown_alert_id():
    """Unknown alert_id leaves all records untouched."""
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg(), scan_id="s1")
    record_outcome("AAPL", "does-not-exist", {"tp1_hit": True}, state)
    assert state["tickers"]["AAPL"]["alert_history"][0]["tp1_hit"] is None


def test_record_outcome_noop_for_unknown_ticker():
    """Unknown ticker is a safe no-op."""
    state = _empty()
    result = record_outcome("ZZZZ", "x", {"tp1_hit": True}, state)
    assert result is state
    assert state["tickers"] == {}


# ---------------------------------------------------------------------------
# Campaign identity integration — C1
# ---------------------------------------------------------------------------

class TestCampaignIdentityDedup:
    """State store correctly uses campaign_id when present."""

    def _state_with_campaign(self, ticker="STRL", campaign_id="STRL|continuation|ob|728.0000|728.2900"):
        return {
            "tickers": {
                ticker: {
                    "last_alerted_tier":       "SNIPE_IT",
                    "last_alerted_at":         _recent(5),
                    "last_trigger_level":      733.57,
                    "last_invalidation_level": 728.29,
                    "last_campaign_id":        campaign_id,
                    "last_score":              88,
                    "last_reason":             "prior alert",
                    "last_discord_channel":    "#snipe-signals",
                    "last_dedup_key":          f"STRL|SNIPE_IT|{campaign_id}",
                    "scan_id":                 "s1",
                    "alert_history":           [],
                }
            },
            "meta": {"total_alerts": 1},
        }

    def _tiering_with_campaign(self, ticker="STRL", trigger=732.81, campaign_id="STRL|continuation|ob|728.0000|728.2900"):
        return {
            "final_tier": "SNIPE_IT",
            "final_discord_channel": "#snipe-signals",
            "safe_for_alert": True,
            "score": 88,
            "campaign_id": campaign_id,
            "final_signal": {
                "ticker": ticker,
                "tier": "SNIPE_IT",
                "trigger_level": trigger,
                "invalidation_level": 728.29,
                "campaign_id": campaign_id,
                "score": 88,
                "reason": "test",
                "discord_channel": "#snipe-signals",
            },
        }

    def test_dedup_key_uses_campaign_id_when_present(self):
        from src.state_store import make_dedup_key
        key = make_dedup_key("STRL", "SNIPE_IT", 732.81, 728.29, "STRL|continuation|ob|728.0000|728.2900")
        assert "STRL|SNIPE_IT|STRL|continuation|ob|728.0000|728.2900" == key

    def test_dedup_key_fallback_without_campaign_id(self):
        from src.state_store import make_dedup_key
        key = make_dedup_key("STRL", "SNIPE_IT", 732.81, 728.29, None)
        assert key == "STRL|SNIPE_IT|732.81|728.29"

    def test_trigger_drift_suppressed_same_campaign(self):
        """Same campaign_id, trigger drifts by > threshold — must NOT re-alert."""
        state = self._state_with_campaign()
        # New trigger 734.81 — old was 733.57, delta = 1.24 / 733.57 = 0.169% > 0.25% would fire under legacy
        # but with campaign_id present and same → duplicate_suppressed
        tiering = self._tiering_with_campaign(trigger=734.81)
        cfg = _cfg(cooldown=240, trigger_pct=0.25, inval_pct=0.25)
        result = check_alert(tiering, state, cfg)
        assert result["should_alert"] is False
        assert result["reason"] == "duplicate_suppressed"

    def test_new_campaign_id_re_alerts(self):
        """Different campaign_id → new_campaign reason → should alert."""
        state = self._state_with_campaign(campaign_id="STRL|continuation|ob|728.0000|728.2900")
        new_cid = "STRL|continuation|ob|715.0000|714.5000"
        tiering = self._tiering_with_campaign(campaign_id=new_cid)
        cfg = _cfg(cooldown=240)
        result = check_alert(tiering, state, cfg)
        assert result["should_alert"] is True
        assert result["reason"] == "new_campaign"


# ===========================================================================
# Phase 1D — Market Structure State persistence tests
# ===========================================================================

def test_record_alert_stores_market_structure_state():
    tr = _tiering(market_structure_state="EXPANSION")
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["market_structure_state"] == "EXPANSION", (
        f"market_structure_state not stored: got {rec.get('market_structure_state')!r}"
    )


def test_record_alert_market_structure_state_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert "market_structure_state" in rec, "market_structure_state key missing from history record"
    assert rec["market_structure_state"] is None


def test_record_alert_market_structure_state_does_not_affect_dedup_key():
    tr_plain  = _tiering(trigger=182.50, invalidation=178.20)
    tr_mktst  = _tiering(
        trigger=182.50, invalidation=178.20,
        market_structure_state="FAILURE",
    )
    s1 = record_alert("AAPL", tr_plain, _empty(), _cfg())
    s2 = record_alert("AAPL", tr_mktst, _empty(), _cfg())
    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"], (
        "market_structure_state must not influence the dedup_key"
    )


# ===========================================================================
# Phase 14A — Weekly Sovereignty Evidence persistence tests
# ===========================================================================

_WEEKLY_HISTORY_FIELDS = (
    "weekly_sma_alignment",
    "weekly_trend_state",
    "weekly_alignment_context",
)


def test_record_alert_stores_weekly_fields():
    tr = _tiering(
        weekly_sma_alignment="supportive",
        weekly_trend_state="advancing",
        weekly_alignment_context="full_alignment",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["weekly_sma_alignment"] == "supportive"
    assert rec["weekly_trend_state"] == "advancing"
    assert rec["weekly_alignment_context"] == "full_alignment"


def test_record_alert_weekly_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    for field in _WEEKLY_HISTORY_FIELDS:
        assert field in rec, f"weekly field missing from history record: {field!r}"
        assert rec[field] is None


def test_record_alert_weekly_fields_do_not_affect_dedup_key():
    tr_plain = _tiering(trigger=182.50, invalidation=178.20)
    tr_weekly = _tiering(
        trigger=182.50, invalidation=178.20,
        weekly_sma_alignment="hostile",
        weekly_trend_state="declining",
        weekly_alignment_context="countertrend_context",
    )
    s1 = record_alert("AAPL", tr_plain, _empty(), _cfg())
    s2 = record_alert("AAPL", tr_weekly, _empty(), _cfg())
    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"], (
        "weekly evidence must not influence the dedup_key"
    )


# ===========================================================================
# Phase 14C — Real 4H Operational State Evidence persistence tests
# ===========================================================================

_4H_HISTORY_FIELDS = (
    "four_hour_market_state",
    "four_hour_sma_alignment",
    "four_hour_reclaim_status",
    "four_hour_structure_note",
    "four_hour_data_status",
)


def test_record_alert_stores_4h_fields():
    tr = _tiering(
        four_hour_market_state="TRANSITION",
        four_hour_sma_alignment="mixed",
        four_hour_reclaim_status="below_value",
        four_hour_structure_note="lower_high_pressure",
        four_hour_data_status="current",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["four_hour_market_state"] == "TRANSITION"
    assert rec["four_hour_sma_alignment"] == "mixed"
    assert rec["four_hour_reclaim_status"] == "below_value"
    assert rec["four_hour_structure_note"] == "lower_high_pressure"
    assert rec["four_hour_data_status"] == "current"


def test_record_alert_4h_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    for field in _4H_HISTORY_FIELDS:
        assert field in rec, f"4H field missing from history record: {field!r}"
        assert rec[field] is None


def test_record_alert_4h_fields_do_not_affect_dedup_key():
    tr_plain = _tiering(trigger=182.50, invalidation=178.20)
    tr_4h = _tiering(
        trigger=182.50, invalidation=178.20,
        four_hour_market_state="FAILURE",
        four_hour_sma_alignment="hostile",
        four_hour_reclaim_status="failed_reclaim",
        four_hour_structure_note="breakdown_pressure",
        four_hour_data_status="current",
    )
    s1 = record_alert("AAPL", tr_plain, _empty(), _cfg())
    s2 = record_alert("AAPL", tr_4h, _empty(), _cfg())
    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"], (
        "4H evidence must not influence the dedup_key"
    )


# ---------------------------------------------------------------------------
# Phase 14E — Real 1H Entry Trigger Evidence (observational) in alert_history
# ---------------------------------------------------------------------------

_1H_HISTORY_FIELDS = (
    "one_hour_trigger_family",
    "one_hour_state",
    "one_hour_retest_quality",
    "one_hour_acceptance_state",
    "one_hour_consequence_state",
    "one_hour_no_chase_status",
    "one_hour_data_status",
)


def test_record_alert_stores_1h_fields():
    tr = _tiering(
        one_hour_trigger_family="break_retest_hold",
        one_hour_state="expansion",
        one_hour_retest_quality="clean",
        one_hour_acceptance_state="accepted",
        one_hour_consequence_state="confirmed",
        one_hour_no_chase_status="ideal",
        one_hour_data_status="available",
    )
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    assert rec["one_hour_trigger_family"] == "break_retest_hold"
    assert rec["one_hour_state"] == "expansion"
    assert rec["one_hour_retest_quality"] == "clean"
    assert rec["one_hour_acceptance_state"] == "accepted"
    assert rec["one_hour_consequence_state"] == "confirmed"
    assert rec["one_hour_no_chase_status"] == "ideal"
    assert rec["one_hour_data_status"] == "available"


def test_record_alert_1h_fields_none_when_absent():
    tr = _tiering()
    state = record_alert("AAPL", tr, _empty(), _cfg())
    rec = state["tickers"]["AAPL"]["alert_history"][0]
    for field in _1H_HISTORY_FIELDS:
        assert field in rec, f"1H field missing from history record: {field!r}"
        assert rec[field] is None


def test_record_alert_1h_fields_do_not_affect_dedup_key():
    tr_plain = _tiering(trigger=182.50, invalidation=178.20)
    tr_1h = _tiering(
        trigger=182.50, invalidation=178.20,
        one_hour_trigger_family="none",
        one_hour_state="failure",
        one_hour_retest_quality="failed",
        one_hour_acceptance_state="rejected",
        one_hour_consequence_state="rejected",
        one_hour_no_chase_status="overextended",
        one_hour_data_status="available",
    )
    s1 = record_alert("AAPL", tr_plain, _empty(), _cfg())
    s2 = record_alert("AAPL", tr_1h, _empty(), _cfg())
    rec1 = s1["tickers"]["AAPL"]["alert_history"][0]
    rec2 = s2["tickers"]["AAPL"]["alert_history"][0]
    assert rec1["dedup_key"] == rec2["dedup_key"], (
        "1H evidence must not influence the dedup_key"
    )

"""Phase 14Y — Structural Atlas display/evidence contract."""

import copy
import inspect

from src import structural_atlas as sa


def _result():
    return {
        "ticker": "WMT",
        "final_tier": "WAIT",
        "enriched": {
            "latest_close": 105.92,
            "sma20": 109.50,
            "sma50": 111.31,
            "sma200": 118.06,
            "sma_alignment": "hostile",
            "swing_highs": [[10, 110.56], [20, 115.75]],
            "swing_lows": [[15, 102.87]],
            "last_swing_high": 115.75,
            "last_swing_low": 102.87,
            "equal_highs": [110.56],
            "equal_lows": [102.87],
            "recent_range_high": 115.75,
            "recent_range_low": 102.87,
            "nearest_pool_above": 110.56,
            "nearest_pool_below": 102.87,
            "sweep_detected": False,
            "structure_event": "none",
            "structure_level": None,
            "prior_structural_high": 110.56,
            "fvg": {"fvg_bot": 103.40, "fvg_mid": 104.03, "fvg_top": 104.66, "fvg_filled": False},
            "ob": {"ob_lo": 102.90, "ob_hi": 103.80, "ob_core": 103.35, "mitigated": False},
            "overhead_status": "moderate",
            "overhead_level": 109.50,
            "overhead_distance_pct": 3.38,
            "volume_ratio": 0.91,
            "volume_behavior": "neutral",
            "live_daily_volume": 123456,
            "atr": 2.1,
            "previous_close": 105.10,
            "daily_bar_context": {"status": "LIVE", "last_closed_daily_date": "2026-09-11", "live_daily_date": "2026-09-12"},
            "targets": [{"label": "T1", "level": 110.56, "reason": "prior structural high"}],
            "invalidation_level": 103.40,
            "invalidation_condition": "acceptance below FVG bottom",
            "estimated_rr": 1.85,
        },
        "tiering_result": {
            "final_tier": "WAIT",
            "final_signal": {
                "current_price": 105.92,
                "trigger_level": None,
                "invalidation_level": 103.40,
                "invalidation_condition": "acceptance below FVG bottom",
                "targets": [{"label": "T1", "level": 114.29, "reason": "nearest liquidity pool above"}],
                "risk_reward": 3.32,
                "overhead_status": "clear",
            },
            "higher_timeframe_context": {
                "data_status": "OK",
                "monthly": {
                    "bias_state": "TRANSITION",
                    "trend_state": "TRANSITION",
                    "stack_state": "WARPED",
                    "sma_relationship": {"price_vs_20": "BELOW"},
                    "key_levels": [{"level": 130.00, "kind": "RESISTANCE", "date": "2026-04-01"}],
                    "support_resistance_map": [],
                    "nearest_zone": {"level": 102.00, "type": "SUPPORT", "side": "below", "distance_pct": 3.7, "zone_grade": "FUNCTIONAL", "freshness": "TESTED"},
                },
                "weekly": {
                    "campaign_state": "HTF_FAILURE",
                    "trend_state": "FAILURE",
                    "stack_state": "INVERTED",
                    "sma_relationship": {"price_vs_20": "BELOW"},
                    "key_levels": [{"level": 115.55, "kind": "RESISTANCE", "date": "2026-08-01"}],
                    "support_resistance_map": [],
                    "nearest_zone": {"level": 104.08, "type": "SUPPORT", "side": "below", "distance_pct": 1.74, "zone_grade": "FUNCTIONAL", "freshness": "TESTED"},
                },
                "campaign_location": {"label": "BELOW_HTF_FAILURE", "quality": "HOSTILE"},
                "htf_sequence": {"came_from": "EXPANSION", "attempt": "REPAIR", "current_read": "FAILURE", "bos_context": "NONE"},
                "setup_relationship": {"context_grade": "HOSTILE", "context_score": 0, "supports_long_setup": False, "weakens_long_setup": True, "blocks_snipe_contextually": True},
                "lookback": {"current_weekly_bar_is_developing": True, "current_monthly_bar_is_developing": True, "last_completed_weekly_bar_date": "2026-09-04", "last_completed_monthly_bar_date": "2026-08-31"},
            },
            "four_hour_operational": {
                "status": "OK",
                "authority_mode": "SHADOW_EVIDENCE_ONLY",
                "structural_state": "TRANSITION",
                "operational_location": "DEFENDABLE",
                "operational_readiness": "FORMING",
                "state_confidence": "LOW",
                "bar_context": {"last_closed_4h_time": "2026-09-11T16:00:00-04:00"},
                "structure": {"swing_highs": [{"level": 106.60}], "swing_lows": [{"level": 102.87}], "range_high": 106.60, "range_low": 102.87, "break_state": "WICK_ONLY", "break_level": 106.60, "reclaim_state": "NONE", "reclaim_level": None},
                "liquidity": {"buyside_target": 106.60, "sellside_target": 102.87, "prior_swing_high": 106.60, "prior_swing_low": 102.87, "swept_level": None, "sweep_state": "NONE"},
                "zone_context": {"fvg": {"bottom": 103.40, "top": 104.66, "midpoint": 104.03}, "fvg_state": "DEFENDED", "demand_core": {"low": 103.10, "high": 103.80, "midpoint": 103.45}},
                "value_context": {"sma10": 105.40, "sma20": 104.90, "sma50": 104.10, "stack": "BULLISH", "price_vs_value": "ABOVE"},
                "volume_participation": {"volume_ratio": 1.1, "volume_behavior": "NEUTRAL"},
                "target_path": {"path_class": "MODERATE", "next_objective": 109.50},
            },
            "one_hour_entry": {
                "status": "ENABLED",
                "data_freshness": "FRESH",
                "trigger_state": "PULLBACK_FORMING",
                "bar_context": {"last_closed_bar_time": "2026-09-11T15:00:00-04:00"},
                "pullback_retest_hold": {"retest_truth": "NONE", "hold_truth": "NONE"},
                "candle_truth": {"event_type": "NONE"},
                "location_realism": {"label": "ACCEPTABLE_BUT_NOT_IDEAL", "nearest_resistance": 106.60},
                "path_quality": {"path_label": "CAPPED", "nearest_resistance": 106.60},
                "invalidation": {"clear": True, "level": 103.40, "condition": "acceptance below FVG"},
                "score": 44,
                "score_label": "NO_VALID_1H_TRIGGER",
                "alert_truth_label": "FORMING_TRIGGER",
                "scanner_sentence": "No valid 1H trigger yet.",
            },
        },
    }


def test_structural_evidence_exposes_existing_blocks_without_fetch():
    result = _result()
    evidence = sa.build_structural_evidence(result)
    assert evidence["higher_timeframe"]["weekly"]["campaign_state"] == "HTF_FAILURE"
    assert evidence["daily"]["last_swing_high"] == 115.75
    assert evidence["four_hour"]["authority_mode"] == "SHADOW_EVIDENCE_ONLY"
    assert evidence["one_hour"]["trigger_state"] == "PULLBACK_FORMING"


def test_level_ledger_separates_horizontal_structure_from_dynamic_value():
    ledger = sa.build_level_ledger(_result())
    sma = next(x for x in ledger if x["structure_type"] == "SMA_20" and x["timeframe"] == "DAILY")
    assert sma["role"] == "VALUE"
    assert sma["authority_mode"] == "DYNAMIC_VALUE"
    swing = next(x for x in ledger if x["structure_type"] == "SWING_HIGH" and x["timeframe"] == "DAILY")
    assert swing["role"] == "RESISTANCE"


def test_real_four_hour_remains_shadow_in_atlas():
    ledger = sa.build_level_ledger(_result())
    four = [x for x in ledger if x["timeframe"] == "4H"]
    assert four
    assert all("SHADOW_EVIDENCE_ONLY" in x["authority_mode"] for x in four)


def test_degraded_missing_volume_does_not_erase_htf_ohlc_structure():
    result = _result()
    result["tiering_result"]["higher_timeframe_context"]["data_status"] = "DEGRADED_MISSING_VOLUME"
    atlas = sa.build_structural_atlas(result)
    assert atlas["evidence"]["higher_timeframe"]["data_status"] == "DEGRADED_MISSING_VOLUME"
    assert any(x["timeframe"] == "WEEKLY" for x in atlas["level_ledger"])
    assert any(x["timeframe"] == "MONTHLY" for x in atlas["level_ledger"])


def test_known_missing_period_levels_are_not_fabricated():
    evidence = sa.build_structural_evidence(_result())
    missing = set(evidence["known_absent_evidence"])
    assert "PREVIOUS_DAY_HIGH" in missing
    assert "PREVIOUS_WEEK_CLOSE" in missing
    assert "PREVIOUS_MONTH_LOW" in missing
    assert not any("previous_day_high" in str(x).lower() for x in sa.build_level_ledger(_result()))


def test_candidate_and_model_selected_geometry_remain_distinct():
    evidence = sa.build_structural_evidence(_result())
    assert evidence["daily"]["candidate_targets"][0]["level"] == 110.56
    assert evidence["selected_trade_geometry"]["targets"][0]["level"] == 114.29
    assert evidence["daily"]["candidate_estimated_rr"] == 1.85
    assert evidence["selected_trade_geometry"]["risk_reward"] == 3.32


def test_atlas_is_pure_and_does_not_mutate_result():
    result = _result()
    before = copy.deepcopy(result)
    sa.build_structural_evidence(result)
    sa.build_level_ledger(result)
    sa.build_structural_atlas(result)
    sa.render_structural_atlas(result)
    sa.render_structural_atlas_json(result)
    assert result == before


def test_module_has_no_strategy_or_io_calls():
    src = inspect.getsource(sa)
    forbidden = (
        "requests.", "httpx.", "yfinance", "batch_download(", "fetch_one_hour_bars(",
        "claude_call(", "async_claude_scan(", "tiering.validate(", "send_alert(",
        "state_store", "datetime.now(", "os.environ",
    )
    for token in forbidden:
        assert token not in src


def test_render_contains_operator_battlefield_sections():
    text = sa.render_structural_atlas(_result())
    for heading in (
        "STRUCTURAL ATLAS — EVIDENCE MAP",
        "CAMPAIGN STRUCTURE",
        "KEY LEVEL LADDER — ABOVE PRICE",
        "KEY LEVEL LADDER — BELOW PRICE",
        "NEAREST STRUCTURAL REFERENCES",
        "DAILY SWING / LIQUIDITY",
        "ZONES",
        "DYNAMIC VALUE — NOT HORIZONTAL STRUCTURE",
        "4H OPERATIONAL EVIDENCE",
        "1H TRIGGER PROOF",
        "CANDIDATE VS SELECTED GEOMETRY",
        "KNOWN ABSENT / NOT YET MODELED",
    ):
        assert heading in text


def test_nearest_support_resistance_and_liquidity_are_deterministic_by_distance():
    atlas = sa.build_structural_atlas(_result())
    assert atlas["horizontal_structure"]["nearest_resistance"] is not None
    assert atlas["horizontal_structure"]["nearest_support"] is not None
    assert atlas["liquidity_map"]["nearest_buy_side"] is not None
    assert atlas["liquidity_map"]["nearest_sell_side"] is not None


def test_json_is_machine_readable():
    import json
    payload = json.loads(sa.render_structural_atlas_json(_result()))
    assert payload["schema_version"] == "14Y-1"
    assert isinstance(payload["level_ledger"], list)

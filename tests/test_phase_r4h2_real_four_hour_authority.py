"""Phase R4H-2 — real 4H operational authority handoff regression suite.

These tests enforce the production hierarchy:

    Weekly campaign -> Daily permission -> REAL 4H operation -> 1H trigger.

The old Phase-14F proxy remains visible for diagnosis/rollback but cannot
outvote trusted real 4H evidence. Untrusted real 4H evidence is missing proof,
not market failure, and must fail closed to no new capital.
"""

from copy import deepcopy
from unittest.mock import MagicMock, patch

from src import four_hour_authority as r4h2
from src import snipe_ladder_judgment as ladder
from src import timeframe_alignment
from src.scheduler import _complete_candidate_judgment
from tests.test_scheduler import _cfg_market_hours, _enriched, _snipe_tiering_result


def _proxy(state="LOCATION_VALID"):
    return {
        "timeframe": "4H",
        "role": "OPERATIONAL_LOCATION",
        "state": state,
        "evidence": [f"legacy proxy={state}"],
        "warnings": [],
        "blocks_trigger": state == "LOCATION_HOSTILE",
    }


def _real(
    *,
    status="ENABLED",
    freshness="CLOSED",
    latest="CONFIRMED",
    gap=False,
    complete=True,
    closed=True,
    segment=20,
    location="DEFENDABLE",
    structural="CONTINUATION",
    retest="CONFIRMED",
    hold="CONFIRMED",
    failure="NONE",
):
    return {
        "status": status,
        "operational_location": location,
        "structural_state": structural,
        "operational_readiness": "READY_FOR_1H_PROOF",
        "bar_context": {
            "closed_bar_available": closed,
            "last_closed_source_complete": complete,
            "history_gap_detected": gap,
            "freshness_status": freshness,
            "latest_bucket_status": latest,
            "structural_segment_bars": segment,
            "using_live_bar_for_confirmation": False,
        },
        "retest_truth": {"state": retest},
        "hold_truth": {"state": hold},
        "failure_truth": {"state": failure},
        "hard_failures": [],
        "soft_warnings": [],
        "missing_proofs": [],
    }


def _cfg(authority=True):
    return {"timeframe_alignment": {"enabled": True, "real_4h_authority_enabled": authority}}


def test_01_closed_complete_fresh_defendable_4h_becomes_valid_authority():
    auth = r4h2.build_operational_authority(_real(), _proxy(), _cfg())
    assert auth["authority_status"] == r4h2.TRUSTED
    assert auth["authority_usable"] is True
    assert auth["capital_floor_cleared"] is True
    assert auth["state"] == "LOCATION_VALID"
    assert auth["proxy_state"] == "LOCATION_VALID"


def test_02_live_bucket_cannot_create_full_4h_confirmation():
    """Fresh LIVE context may exist, but forming retest/hold cannot map VALID."""
    auth = r4h2.build_operational_authority(
        _real(freshness="LIVE", retest="IN_PROGRESS", hold="FORMING"),
        _proxy(),
        _cfg(),
    )
    assert auth["authority_status"] == r4h2.TRUSTED
    assert auth["state"] == "LOCATION_REPAIRING"
    assert any("still forming" in e for e in auth["evidence"])


def test_03_stale_real_4h_is_untrusted_and_blocks_capital_not_market_failure():
    auth = r4h2.build_operational_authority(
        _real(status="STALE", freshness="STALE"), _proxy(), _cfg()
    )
    assert auth["authority_status"] == r4h2.UNTRUSTED
    assert auth["state"] == "UNKNOWN"
    assert auth["blocks_capital"] is True
    assert auth["blocks_trigger"] is False
    assert auth["capital_floor_cleared"] is False
    assert any("STALE" in r for r in auth["trust_failures"])


def test_04_history_gap_withholds_real_4h_capital_authority():
    auth = r4h2.build_operational_authority(_real(gap=True), _proxy(), _cfg())
    assert auth["authority_usable"] is False
    assert auth["blocks_capital"] is True
    assert any("evidence gap" in r for r in auth["trust_failures"])


def test_05_incomplete_latest_bucket_withholds_authority():
    auth = r4h2.build_operational_authority(
        _real(status="DEGRADED", latest="INCOMPLETE"), _proxy(), _cfg()
    )
    assert auth["authority_usable"] is False
    assert any("INCOMPLETE" in r for r in auth["trust_failures"])


def test_06_mid_range_is_trusted_chart_evidence_but_execution_hostile():
    auth = r4h2.build_operational_authority(
        _real(location="MID_RANGE", retest="NONE", hold="NONE"),
        _proxy("LOCATION_VALID"),
        _cfg(),
    )
    assert auth["authority_usable"] is True
    assert auth["state"] == "LOCATION_HOSTILE"
    assert auth["blocks_trigger"] is True
    assert any("mid-range" in e for e in auth["evidence"])


def test_07_emergency_rollback_restores_proxy_without_erasing_real_diagnostic():
    auth = r4h2.build_operational_authority(
        _real(status="STALE", freshness="STALE", location="HOSTILE"),
        _proxy("LOCATION_REPAIRING"),
        _cfg(authority=False),
    )
    assert auth["authority_mode"] == r4h2.PROXY_MODE
    assert auth["authority_status"] == r4h2.DISABLED
    assert auth["state"] == "LOCATION_REPAIRING"
    assert auth["blocks_capital"] is False
    assert auth["real_state"] == "HOSTILE"


def _capital_result(tier):
    result = deepcopy(_snipe_tiering_result("AAPL"))
    result["final_tier"] = tier
    if tier == "STARTER":
        result["capital_action"] = "starter_only"
        result["final_discord_channel"] = "#starter-signals"
    else:
        result["capital_action"] = "full_quality_allowed"
        result["final_discord_channel"] = "#snipe-signals"
    result["safe_for_alert"] = True
    result["final_signal"]["tier"] = tier
    result["final_signal"]["capital_action"] = result["capital_action"]
    result["final_signal"]["discord_channel"] = result["final_discord_channel"]
    return result


def test_08_untrusted_real_4h_withdraws_snipe_capital_to_near_entry():
    result = _capital_result("SNIPE_IT")
    result["four_hour_authority"] = r4h2.build_operational_authority(
        _real(status="STALE", freshness="STALE"), _proxy(), _cfg()
    )
    out = r4h2.enforce_operational_capital_floor(result, _cfg())
    assert out["final_tier"] == "NEAR_ENTRY"
    assert out["capital_action"] == "wait_no_capital"
    assert out["four_hour_authority"]["capital_floor_enforced"] is True


def test_09_untrusted_real_4h_withdraws_starter_capital_too():
    result = _capital_result("STARTER")
    result["four_hour_authority"] = r4h2.build_operational_authority(
        _real(gap=True), _proxy(), _cfg()
    )
    out = r4h2.enforce_operational_capital_floor(result, _cfg())
    assert out["final_tier"] == "NEAR_ENTRY"
    assert out["capital_action"] == "wait_no_capital"


def test_10_trusted_real_4h_does_not_change_existing_capital_tier():
    result = _capital_result("STARTER")
    result["four_hour_authority"] = r4h2.build_operational_authority(
        _real(), _proxy(), _cfg()
    )
    out = r4h2.enforce_operational_capital_floor(result, _cfg())
    assert out["final_tier"] == "STARTER"
    assert out["capital_action"] == "starter_only"
    assert out["four_hour_authority"]["capital_floor_enforced"] is False


def _alignment_input(authority, proxy_state="LOCATION_VALID"):
    result = _snipe_tiering_result("AAPL")
    result["trade_location"] = {
        "location_state": "mid_zone_acceptance" if proxy_state == "LOCATION_VALID"
        else "lower_zone_defense"
    }
    result["one_hour_entry"] = {
        "status": "ENABLED",
        "trigger_state": "TRIGGER_LIVE",
        "alert_truth_label": "LIVE_TRIGGER",
        "score_label": "1H_TRIGGER_VALID",
        "data_freshness": "FRESH",
        "candle_truth": {"closed_candle_confirms": True},
        "pullback_retest_hold": {"hold_truth": "HOLD_CONFIRMED"},
        "invalidation": {"clear": True},
        "path_quality": {"path_label": "CLEAN"},
    }
    result["four_hour_authority"] = authority
    return result


def test_11_timeframe_alignment_real_4h_outvotes_legacy_proxy():
    auth = r4h2.build_operational_authority(
        _real(location="HOSTILE", structural="FAILURE", failure="ACCEPTED_FAILURE"),
        _proxy("LOCATION_VALID"),
        _cfg(),
    )
    result = _alignment_input(auth)
    tf = timeframe_alignment.build_timeframe_alignment_context(
        "AAPL", result, enriched_data={}, config=_cfg()
    )
    assert tf["operational_timeframe"]["state"] == "LOCATION_HOSTILE"
    assert tf["operational_proxy_timeframe"]["state"] == "LOCATION_VALID"
    assert tf["operational_authority"]["authority_mode"] == r4h2.AUTHORITY_MODE
    assert tf["alignment_label"] == "CONFLICTED"


def test_12_timeframe_alignment_untrusted_4h_is_unknown_and_capital_blocked():
    auth = r4h2.build_operational_authority(
        _real(status="STALE", freshness="STALE"), _proxy("LOCATION_VALID"), _cfg()
    )
    tf = timeframe_alignment.build_timeframe_alignment_context(
        "AAPL", _alignment_input(auth), enriched_data={}, config=_cfg()
    )
    op = tf["operational_timeframe"]
    assert op["state"] == "UNKNOWN"
    assert op["blocks_capital"] is True
    assert "REAL_4H_AUTHORITY_UNTRUSTED" in tf["hard_caps_applied"]
    assert tf["status"] == "DEGRADED"


def test_13_real_extended_4h_cannot_be_upgraded_to_functionally_valid_repair():
    card = {
        "four_h": "LOCATION_EXTENDED",
        "tl_state": "above_zone_extension",
        "retest_truth": "RETEST_REAL",
        "price_below_inval": False,
        "real4h_active": True,
    }
    assert ladder._four_h_ok(card) == "REPAIRING"


def test_14_shared_scheduler_uses_same_60m_request_for_1h_and_real_4h():
    cfg = _cfg_market_hours()
    cfg.setdefault("timeframe_alignment", {})["real_4h_authority_enabled"] = True
    result = _snipe_tiering_result("AAPL")
    enriched = _enriched("AAPL")
    four_env = {"status": "OK", "bars": []}
    one_env = {"bars": [], "four_hour": four_env}
    call_order = []

    def _authority(real, proxy, config):
        call_order.append("authority")
        return {
            "authority_mode": r4h2.AUTHORITY_MODE,
            "authority_status": r4h2.TRUSTED,
            "authority_usable": True,
            "capital_floor_cleared": True,
            "state": "LOCATION_VALID",
            "blocks_trigger": False,
            "blocks_capital": False,
            "evidence": [], "warnings": [], "trust_failures": [],
            "proxy_state": proxy.get("state"), "proxy_layer": proxy,
        }

    with (
        patch("src.scheduler.trajectory_mod.compute", return_value={}),
        patch("src.scheduler.trade_location.build_trade_location_context", return_value={"location_state": "mid_zone_acceptance"}),
        patch("src.scheduler.candle_evidence.build_candle_evidence_context", return_value={}),
        patch("src.scheduler.market_data_mod.fetch_one_hour_bars", return_value=one_env) as fetch,
        patch("src.scheduler.one_hour_entry.build_one_hour_entry_context", return_value={"status": "ENABLED"}),
        patch("src.scheduler.four_hour_operational.build_four_hour_operational_context", return_value=_real()) as real4h,
        patch("src.scheduler.four_hour_operational.compare_real_vs_proxy", return_value={"agreement": "AGREE"}),
        patch("src.scheduler.four_hour_authority.build_operational_authority", side_effect=_authority),
        patch("src.scheduler.timeframe_alignment.build_timeframe_alignment_context", return_value={"operational_timeframe": {"state": "LOCATION_VALID"}}) as tf,
        patch("src.scheduler.higher_timeframe_context.daily_bars_from_df", return_value=[]),
        patch("src.scheduler.higher_timeframe_context.build_higher_timeframe_context", return_value={}),
        patch("src.scheduler.snipe_gate_audit.build_snipe_gate_audit", return_value={}),
        patch("src.scheduler.snipe_ladder_judgment.apply_ladder_arbitration", side_effect=lambda r, c: r),
        patch("src.scheduler.four_hour_authority.enforce_operational_capital_floor", side_effect=lambda r, c: r) as floor,
        patch("src.scheduler.snipe_confirmed_seal.seal_snipe_confirmed_consistency", side_effect=lambda r, c: r),
        patch("src.scheduler.snipe_gate_audit.reconcile_final_snipe_audit_state"),
        patch("src.scheduler.score_calibration.calibrate_score", return_value={}),
    ):
        out = _complete_candidate_judgment(
            "AAPL", result, enriched, {"df": MagicMock()}, cfg, None
        )

    fetch.assert_called_once_with("AAPL", cfg)
    assert real4h.call_args.kwargs["four_hour_bars"] is four_env
    assert out["four_hour_authority"]["authority_usable"] is True
    assert call_order == ["authority"]
    tf.assert_called_once()
    floor.assert_called_once()


def test_15_authority_floor_executes_before_downgrade_only_seal():
    from pathlib import Path

    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    helper = src[src.index("def _complete_candidate_judgment("):src.index("async def run_scan_pipeline")]
    assert helper.index("apply_ladder_arbitration") < helper.index("enforce_operational_capital_floor")
    assert helper.index("enforce_operational_capital_floor") < helper.index("seal_snipe_confirmed_consistency")
    assert helper.index("build_four_hour_operational_context") < helper.index("build_timeframe_alignment_context")

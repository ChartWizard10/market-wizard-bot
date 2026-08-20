"""CAP-40B — telemetry attachment and offline outcome-linkage regressions."""

import ast
import json
from copy import deepcopy
from pathlib import Path

from src import capacity_boundary_dataset as dataset
from src import capacity_boundary_observation as boundary
from src import scheduler
from src import velocity_dataset
from src import velocity_research


def _observation(rank=31, ticker="TEST", scan_id="scan_1", **overrides):
    band = (
        boundary.BAND_BASELINE_EDGE
        if rank <= 30
        else boundary.BAND_SHADOW_INCREMENT
    )
    base = {
        "version": boundary.VERSION,
        "research_only": True,
        "observational_only": True,
        "model_authority": False,
        "candidate_cap_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "forecast_authority": False,
        "scan_id": scan_id,
        "ticker": ticker,
        "observed_at": "2026-08-20T09:35:00-04:00",
        "rank": rank,
        "current_cap": 30,
        "proposed_cap": 40,
        "band": band,
        "ready": True,
        "missing": [],
        "reference_price": 100.0,
        "reference_source": "current_price",
        "invalidation_level": 95.0,
        "invalidation_source": "setup_family_invalidation",
        "target_return_pct": 8.0,
        "horizon_sessions": 5.0,
        "feasibility_status": velocity_research.FEASIBILITY_SUPPORTED,
        "known_path_room_pct": 12.0,
        "atr_pct": 3.0,
        "required_move_atr": 2.667,
        "prefilter_score": 74.0,
        "admission_rank_score": 86.0,
        "admission_source": "family",
        "primary_family": "BREAK_RETEST_CONTINUATION",
        "family_state": "RETEST_HOLD",
        "family_score": 91.0,
        "family_watch_ready": True,
        "family_admission_ready": True,
        "family_entry_structure_valid": True,
        "family_rr_to_t1": 3.6,
        "retest_status": "confirmed",
        "overhead_status": "clear",
        "estimated_rr": 3.6,
    }
    base.update(overrides)
    return base


def _trace(rank=31, trace_kind="near_cut", ticker="TEST", scan_id="scan_1", **obs):
    block = boundary.compact_for_telemetry(
        _observation(rank=rank, ticker=ticker, scan_id=scan_id, **obs)
    )
    return {
        "schema_version": "14V.2",
        "scan_id": scan_id,
        "ticker": ticker,
        "trace_kind": trace_kind,
        "capacity_boundary_observation": block,
    }


def _bars_target_first():
    return [
        {"date": "2026-08-20", "open": 100, "high": 120, "low": 90, "close": 110},
        {"date": "2026-08-21", "open": 100, "high": 104, "low": 98, "close": 103},
        {"date": "2026-08-24", "open": 103, "high": 109, "low": 100, "close": 108.5},
        {"date": "2026-08-25", "open": 108, "high": 110, "low": 105, "close": 109},
        {"date": "2026-08-26", "open": 109, "high": 111, "low": 107, "close": 110},
        {"date": "2026-08-27", "open": 110, "high": 112, "low": 108, "close": 111},
    ]


def test_compact_projection_is_bounded_whitelisted_and_has_no_post_model_tier():
    obs = _observation()
    obs["missing"] = ["x" * 1000] * 20
    compact = boundary.compact_for_telemetry(obs)
    blob = json.dumps(compact, allow_nan=False, separators=(",", ":"))

    assert len(blob.encode("utf-8")) < 3000
    assert len(compact["missing"]) <= 8
    assert all(len(item) <= 160 for item in compact["missing"])
    assert "final_tier" not in compact
    assert "capital_action" not in compact
    assert compact["candidate_cap_authority"] is False
    assert compact["tier_authority"] is False


def test_scheduler_attachment_is_additive_and_does_not_mutate_trace_or_block():
    trace = {"trace_kind": "near_cut", "ticker": "TEST"}
    block = boundary.compact_for_telemetry(_observation())
    before_trace = deepcopy(trace)
    before_block = deepcopy(block)

    attached = scheduler._attach_capacity_boundary(trace, block)

    assert attached is not trace
    assert attached["capacity_boundary_observation"] == block
    assert trace == before_trace
    assert block == before_block


def test_extracts_boundary_blocks_from_near_cut_analyzed_and_failure_traces():
    ledger = {
        "decision_traces": [
            _trace(rank=31, trace_kind="near_cut", ticker="SHADOW", scan_id="s1"),
            _trace(rank=25, trace_kind="analyzed", ticker="BASE", scan_id="s2"),
            _trace(rank=24, trace_kind="analysis_failed", ticker="FAIL", scan_id="s3"),
        ]
    }
    rows = dataset.extract_boundary_observations(ledger)
    by_ticker = {row["ticker"]: row for row in rows}

    assert set(by_ticker) == {"SHADOW", "BASE", "FAIL"}
    assert by_ticker["SHADOW"]["band"] == boundary.BAND_SHADOW_INCREMENT
    assert by_ticker["BASE"]["band"] == boundary.BAND_BASELINE_EDGE
    assert by_ticker["BASE"]["model_analyzed_at_observation"] is True
    assert by_ticker["SHADOW"]["model_analyzed_at_observation"] is False
    assert by_ticker["FAIL"]["source_trace_kind"] == "analysis_failed"
    assert by_ticker["BASE"]["final_tier"] is None
    assert by_ticker["BASE"]["capital_authorized_at_observation"] is False


def test_future_link_strictly_excludes_observation_day_and_labels_target_first():
    ledger = {"decision_traces": [_trace(rank=31)]}
    built = dataset.link_capacity_boundary_dataset(
        ledger,
        {"TEST": _bars_target_first()},
    )
    record = built["records"][0]

    assert record["future_session_dates"][0] == "2026-08-21"
    assert "2026-08-20" not in record["future_session_dates"]
    assert record["label"] == velocity_research.TARGET_FIRST
    assert record["band"] == boundary.BAND_SHADOW_INCREMENT
    assert record["counterfactual_model_tier_supported"] is False


def test_valid_shadow_invalidation_first_is_preserved_as_outcome_not_trade_claim():
    ledger = {"decision_traces": [_trace(rank=32)]}
    bars = [
        {"date": "2026-08-21", "open": 100, "high": 103, "low": 94, "close": 96},
        {"date": "2026-08-24", "open": 96, "high": 99, "low": 92, "close": 94},
    ]
    built = dataset.link_capacity_boundary_dataset(ledger, {"TEST": bars})
    record = built["records"][0]

    assert record["label"] == velocity_research.INVALIDATION_FIRST
    assert record["candidate_cap_authority"] is False
    assert record["capital_authority"] is False
    assert record["tier_authority"] is False


def test_missing_geometry_stays_invalid_and_is_not_repaired_by_linker():
    ledger = {
        "decision_traces": [
            _trace(
                rank=31,
                ready=False,
                invalidation_level=None,
                missing=["invalidation_level"],
            )
        ]
    }
    built = dataset.link_capacity_boundary_dataset(ledger, {"TEST": _bars_target_first()})
    record = built["records"][0]

    assert record["link_status"] == velocity_dataset.LINK_INVALID_OBSERVATION
    assert record["label"] == velocity_research.INVALID_DATA


def test_identical_duplicate_scan_ticker_observations_dedupe_once():
    trace = _trace(rank=31)
    ledger = {"decision_traces": [deepcopy(trace), deepcopy(trace)]}
    built = dataset.link_capacity_boundary_dataset(ledger, {"TEST": _bars_target_first()})

    assert built["observation_count_raw"] == 2
    assert built["observation_count_unique"] == 1
    assert built["duplicate_identical_observations_deduped"] == 1
    assert built["duplicate_observation_conflicts"] == 0


def test_conflicting_duplicate_scan_ticker_observations_fail_closed():
    first = _trace(rank=31)
    second = _trace(rank=31)
    second["capacity_boundary_observation"] = dict(second["capacity_boundary_observation"])
    second["capacity_boundary_observation"]["reference_price"] = 101.0
    ledger = {"decision_traces": [first, second]}

    built = dataset.link_capacity_boundary_dataset(ledger, {"TEST": _bars_target_first()})
    record = built["records"][0]

    assert built["duplicate_observation_conflicts"] == 1
    assert record["link_status"] == dataset.LINK_DUPLICATE_BOUNDARY_CONFLICT
    assert record["label"] == velocity_research.INVALID_DATA


def test_band_summary_keeps_baseline_and_shadow_outcomes_separate():
    ledger = {
        "decision_traces": [
            _trace(rank=25, ticker="BASE", scan_id="b1", trace_kind="analyzed"),
            _trace(rank=31, ticker="SHADOW", scan_id="s1", trace_kind="near_cut"),
        ]
    }
    bars = {
        "BASE": _bars_target_first(),
        "SHADOW": _bars_target_first(),
    }
    built = dataset.link_capacity_boundary_dataset(ledger, bars)
    summary = built["summary"]

    assert summary["bands"][boundary.BAND_BASELINE_EDGE]["records"] == 1
    assert summary["bands"][boundary.BAND_SHADOW_INCREMENT]["records"] == 1
    assert summary["bands"][boundary.BAND_BASELINE_EDGE]["target_first"] == 1
    assert summary["bands"][boundary.BAND_SHADOW_INCREMENT]["target_first"] == 1
    assert summary["shadow_target_first_candidates"] == 1


def test_dataset_builder_does_not_mutate_ledger_or_bar_inputs():
    ledger = {"decision_traces": [_trace(rank=31)]}
    bars = {"TEST": _bars_target_first()}
    before_ledger = deepcopy(ledger)
    before_bars = deepcopy(bars)

    dataset.link_capacity_boundary_dataset(ledger, bars)

    assert ledger == before_ledger
    assert bars == before_bars


def test_offline_dataset_module_has_no_network_model_or_live_mutation_imports():
    path = Path("src/capacity_boundary_dataset.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    calls = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    for prefix in (
        "openai",
        "anthropic",
        "requests",
        "aiohttp",
        "discord",
        "src.scheduler",
        "src.state_store",
        "src.discord_alerts",
        "src.model_client",
        "src.claude_client",
    ):
        assert not any(module.startswith(prefix) for module in imports)

    for forbidden in (
        "async_claude_scan",
        "claude_call",
        "send_alert",
        "record_alert",
        "check_alert",
        "batch_download",
        "fetch_ticker",
        "apply_ladder_arbitration",
    ):
        assert forbidden not in calls


def test_scheduler_wiring_keeps_cap_and_model_candidate_source_unchanged():
    text = Path("src/scheduler.py").read_text(encoding="utf-8")

    assert "candidate_tickers = [r[\"ticker\"] for r in pf_result[\"claude_candidates\"]]" in text
    assert "claude_enriched = [enriched_map[t] for t in candidate_tickers if t in enriched_map]" in text
    assert "capacity_boundary_observation.build_boundary_observation" in text
    assert "capacity_boundary=_tlm_capacity_boundary.get(ticker)" in text
    assert "_attach_capacity_boundary" in text

    # CAP-40B may observe ranks outside the paid cap but cannot alter the call input.
    call_pos = text.index("claude_results = await async_claude_scan(")
    call_slice = text[call_pos:call_pos + 240]
    assert "claude_enriched" in call_slice
    assert "_tlm_capacity_boundary" not in call_slice

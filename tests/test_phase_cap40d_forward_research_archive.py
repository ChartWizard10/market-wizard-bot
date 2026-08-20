"""CAP-40D — forward research archive retention/integrity regressions."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

from src import capacity_boundary_dataset
from src import capacity_boundary_observation
from src import forward_research_archive as archive
from src import four_hour_counterfactual
from src import scheduler
from src import velocity_dataset


BASE_TS = "2026-08-20T14:00:00+00:00"


def _config(tmp_path: Path, **archive_overrides) -> dict:
    block = {
        "enabled": True,
        "directory": str(tmp_path / "research_archive"),
        "retention_days": 120,
        "max_daily_file_bytes": 10 * 1024 * 1024,
    }
    block.update(archive_overrides)
    return {
        "scan": {"timezone": "America/New_York"},
        "state": {"state_file": str(tmp_path / "alert_history.json")},
        "telemetry": {
            "telemetry_file": str(tmp_path / "scan_telemetry.json"),
            "max_scan_summaries": 300,
            "max_decision_traces": 9000,
        },
        "research_archive": block,
    }


def _velocity_block(**overrides) -> dict:
    block = {
        "version": "VELOCITY-1C",
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "observed_at": BASE_TS,
        "ready": True,
        "missing": [],
        "reference_price": 100.0,
        "reference_source": "current_price",
        "invalidation_level": 95.0,
        "target_return_pct": 8.0,
        "horizon_sessions": 5,
        "feasibility_status": "SUPPORTED",
        "known_path_room_pct": 12.0,
        "atr_pct": 3.0,
        "required_move_atr": 2.667,
        "final_tier": "STARTER",
        "capital_authorized_at_observation": True,
        "primary_family": "BREAK_RETEST_CONTINUATION",
        "four_hour_state": "CONTINUATION",
        "four_hour_proxy_state": "LOCATION_VALID",
        "four_hour_proxy_agreement": "AGREE",
    }
    block.update(overrides)
    return block


def _four_hour_block(**overrides) -> dict:
    block = {
        "status": "OK",
        "authority_mode": "SHADOW_EVIDENCE_ONLY",
        "structural_state": "CONTINUATION",
        "location_state": "DEFENDABLE",
        "readiness": "READY_FOR_1H_PROOF",
        "last_closed_time": "2026-08-20T13:30:00-04:00",
        "live_bar_available": True,
        "last_closed_source_complete": True,
        "confirmed_history_bars": 20,
        "structural_segment_bars": 8,
        "history_gap_detected": False,
        "freshness_status": "FRESH",
        "proxy_state": "LOCATION_VALID",
        "proxy_agreement": "AGREE",
        "missing_proofs": [],
    }
    block.update(overrides)
    return block


def _capacity_block(rank: int = 25, **overrides) -> dict:
    band = (
        capacity_boundary_observation.BAND_BASELINE_EDGE
        if rank <= 30
        else capacity_boundary_observation.BAND_SHADOW_INCREMENT
    )
    block = {
        "version": "CAP-40A",
        "research_only": True,
        "observational_only": True,
        "model_authority": False,
        "candidate_cap_authority": False,
        "tier_authority": False,
        "capital_authority": False,
        "routing_authority": False,
        "forecast_authority": False,
        "scan_id": "scan_1",
        "ticker": "TEST",
        "observed_at": BASE_TS,
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
        "horizon_sessions": 5,
        "feasibility_status": "SUPPORTED",
        "known_path_room_pct": 12.0,
        "atr_pct": 3.0,
        "required_move_atr": 2.667,
        "prefilter_score": 78.0,
        "admission_rank_score": 88.0,
        "admission_source": "family",
        "primary_family": "BREAK_RETEST_CONTINUATION",
        "family_state": "RETEST_HOLD",
        "family_score": 91.0,
        "family_watch_ready": True,
        "family_admission_ready": True,
        "family_entry_structure_valid": True,
        "family_rr_to_t1": 3.5,
        "retest_status": "confirmed",
        "overhead_status": "clear",
        "estimated_rr": 3.5,
    }
    block.update(overrides)
    return block


def _analyzed_trace(rank: int = 25, ticker: str = "TEST") -> dict:
    return {
        "schema_version": "14V.2",
        "scan_id": "scan_1",
        "ticker": ticker,
        "trace_kind": "analyzed",
        "pipeline": {
            "market_data_ok": True,
            "prefilter_eligible": True,
            "prefilter_rank": rank,
            "prefilter_score": 80,
            "admitted_to_deep_analysis": True,
            "claude_analyzed": True,
            "secret_extra": "drop me",
        },
        "velocity_observation": _velocity_block(),
        "four_hour_real": _four_hour_block(),
        "capacity_boundary_observation": _capacity_block(rank),
        "judgment": {"final_tier": "SNIPE_IT", "capital_action": "full_size"},
        "suppression": {"dedup_key": "secret-key"},
        "delivery": {"channel_id": "123"},
        "model_prose": "do not archive this",
    }


def _near_cut_trace(rank: int) -> dict:
    trace = {
        "schema_version": "14V.2",
        "scan_id": "scan_1",
        "ticker": f"N{rank}",
        "trace_kind": "near_cut",
        "pipeline": {
            "market_data_ok": True,
            "prefilter_eligible": True,
            "prefilter_rank": rank,
            "prefilter_score": 70,
            "admitted_to_deep_analysis": False,
            "claude_analyzed": False,
        },
    }
    if 31 <= rank <= 40:
        trace["capacity_boundary_observation"] = _capacity_block(
            rank,
            ticker=f"N{rank}",
        )
    return trace


def test_projection_omits_trace_with_no_forward_study_block():
    assert archive.project_trace(_near_cut_trace(41)) is None


def test_projection_keeps_analyzed_velocity_four_hour_and_boundary_blocks():
    projected = archive.project_trace(_analyzed_trace())
    assert projected["trace_kind"] == "analyzed"
    assert projected["velocity_observation"]["reference_price"] == 100.0
    assert projected["four_hour_real"]["structural_state"] == "CONTINUATION"
    assert projected["capacity_boundary_observation"]["rank"] == 25


def test_projection_keeps_shadow_boundary_near_cut_without_inventing_model_result():
    projected = archive.project_trace(_near_cut_trace(31))
    assert projected["trace_kind"] == "near_cut"
    assert projected["capacity_boundary_observation"]["band"] == "SHADOW_INCREMENT"
    assert "velocity_observation" not in projected
    assert "four_hour_real" not in projected
    assert "judgment" not in projected


def test_projection_is_strict_whitelist_and_drops_sensitive_or_free_form_fields():
    projected = archive.project_trace(_analyzed_trace())
    blob = json.dumps(projected, allow_nan=False)
    assert "judgment" not in projected
    assert "suppression" not in projected
    assert "delivery" not in projected
    assert "model_prose" not in projected
    assert "secret_extra" not in projected["pipeline"]
    assert "secret-key" not in blob
    assert "do not archive this" not in blob


def test_projection_sanitizes_nonfinite_numbers_for_json_safety():
    trace = _analyzed_trace()
    trace["velocity_observation"]["atr_pct"] = float("nan")
    trace["capacity_boundary_observation"]["estimated_rr"] = float("inf")
    projected = archive.project_trace(trace)
    assert projected["velocity_observation"]["atr_pct"] is None
    assert projected["capacity_boundary_observation"]["estimated_rr"] is None
    json.dumps(projected, allow_nan=False)


def test_session_date_treats_current_naive_scheduler_timestamp_as_utc():
    assert archive.session_date("2026-08-20T00:30:00") == "2026-08-19"


def test_session_date_preserves_aware_absolute_time_then_converts_to_et():
    assert archive.session_date("2026-08-20T13:35:00+00:00") == "2026-08-20"
    assert archive.session_date("2026-08-20T09:35:00-04:00") == "2026-08-20"


def test_invalid_timestamp_builds_no_scan_batch():
    assert archive.build_scan_batch("scan_1", "not-a-time", [_analyzed_trace()]) is None


def test_build_scan_batch_omits_irrelevant_rank_41_to_60_near_cut_traces():
    batch = archive.build_scan_batch(
        "scan_1",
        BASE_TS,
        [_analyzed_trace(), _near_cut_trace(31), _near_cut_trace(41), _near_cut_trace(60)],
    )
    assert batch["trace_count"] == 2
    assert {row["ticker"] for row in batch["traces"]} == {"TEST", "N31"}


def test_disabled_archive_performs_no_write(tmp_path):
    config = _config(tmp_path, enabled=False)
    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    assert result == {"ok": True, "written": False, "reason": "disabled"}
    assert not archive.archive_dir(config).exists()


def test_enabled_archive_creates_one_daily_partition_and_one_line_per_scan(tmp_path):
    config = _config(tmp_path)
    first = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    second = archive.append_scan_batch(config, "scan_2", BASE_TS, [_analyzed_trace()])

    assert first["ok"] is True and first["written"] is True
    assert second["ok"] is True and second["written"] is True
    path = Path(first["path"])
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert path.name == "2026-08-20.jsonl"
    assert len(lines) == 2
    assert json.loads(lines[0])["scan_id"] == "scan_1"
    assert json.loads(lines[1])["scan_id"] == "scan_2"


def test_daily_file_limit_refuses_without_modifying_prior_bytes(tmp_path):
    config = _config(tmp_path, max_daily_file_bytes=1)
    directory = archive.archive_dir(config)
    directory.mkdir(parents=True)
    path = directory / "2026-08-20.jsonl"
    path.write_bytes(b"existing\n")
    before = path.read_bytes()

    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])

    assert result["ok"] is False
    assert result["reason"] == "daily_file_limit"
    assert path.read_bytes() == before


def test_archive_directory_equal_to_alert_state_file_is_refused(tmp_path):
    state_file = tmp_path / "alert_history.json"
    config = _config(tmp_path, directory=str(state_file))
    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    assert archive.path_collision(config) is True
    assert result["reason"] == "path_collision"
    assert not state_file.exists()


def test_archive_directory_equal_to_scan_telemetry_file_is_refused(tmp_path):
    telemetry_file = tmp_path / "scan_telemetry.json"
    config = _config(tmp_path, directory=str(telemetry_file))
    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    assert archive.path_collision(config) is True
    assert result["reason"] == "path_collision"
    assert not telemetry_file.exists()


def test_write_fault_returns_failure_and_never_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "mkdir", boom)
    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    assert result["ok"] is False
    assert result["written"] is False
    assert result["reason"] == "write_error"


def test_readonly_loader_skips_malformed_lines_and_does_not_repair_file(tmp_path):
    directory = tmp_path / "archive"
    directory.mkdir()
    good = archive.build_scan_batch("scan_1", BASE_TS, [_analyzed_trace()])
    path = directory / "2026-08-20.jsonl"
    path.write_text(
        json.dumps(good, separators=(",", ":")) + "\n{not-json\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    ledger = archive.load_directory_readonly(directory)

    assert len(ledger["decision_traces"]) == 1
    assert ledger["archive_stats"]["malformed_lines_skipped"] == 1
    assert path.read_bytes() == before


def test_readonly_loader_date_filter_is_deterministic(tmp_path):
    directory = tmp_path / "archive"
    directory.mkdir()
    for day in ("2026-08-20", "2026-08-21", "2026-08-24"):
        batch = archive.build_scan_batch(
            f"scan_{day}",
            f"{day}T14:00:00+00:00",
            [_analyzed_trace(ticker=day)],
        )
        (directory / f"{day}.jsonl").write_text(json.dumps(batch) + "\n", encoding="utf-8")

    ledger = archive.load_directory_readonly(
        directory, start_date="2026-08-21", end_date="2026-08-21"
    )
    assert [row["ticker"] for row in ledger["decision_traces"]] == ["2026-08-21"]
    assert ledger["archive_stats"]["files_read"] == 1


def test_prune_only_removes_expired_date_partitions_and_keeps_unrelated_files(tmp_path):
    config = _config(tmp_path, retention_days=10)
    directory = archive.archive_dir(config)
    directory.mkdir(parents=True)
    (directory / "2026-08-01.jsonl").write_text("old\n", encoding="utf-8")
    (directory / "notes.jsonl").write_text("keep\n", encoding="utf-8")
    (directory / "README.txt").write_text("keep\n", encoding="utf-8")

    result = archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])

    assert result["ok"] is True
    assert not (directory / "2026-08-01.jsonl").exists()
    assert (directory / "notes.jsonl").exists()
    assert (directory / "README.txt").exists()


def test_default_retention_keeps_august_20_partition_through_october_8_review_floor(tmp_path):
    config = _config(tmp_path)
    directory = archive.archive_dir(config)
    directory.mkdir(parents=True)
    old = directory / "2026-08-20.jsonl"
    old.write_text("historical\n", encoding="utf-8")
    oct8 = "2026-10-08T14:00:00+00:00"

    archive.append_scan_batch(config, "scan_oct8", oct8, [_analyzed_trace()])

    assert old.exists()


def test_velocity_consumer_reads_reconstructed_archive_ledger(tmp_path):
    config = _config(tmp_path)
    archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    ledger = archive.load_archive_ledger_readonly(config)
    rows = velocity_dataset.extract_velocity_observations(ledger)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "TEST"
    assert rows[0]["entry_price"] == 100.0


def test_capacity_consumer_reads_baseline_and_shadow_archive_rows(tmp_path):
    config = _config(tmp_path)
    archive.append_scan_batch(
        config,
        "scan_1",
        BASE_TS,
        [_analyzed_trace(rank=25), _near_cut_trace(31)],
    )
    ledger = archive.load_archive_ledger_readonly(config)
    rows = capacity_boundary_dataset.extract_boundary_observations(ledger)
    assert {row["band"] for row in rows} == {"BASELINE_EDGE", "SHADOW_INCREMENT"}


def test_r4h_counterfactual_consumer_reads_archived_analyzed_trace(tmp_path):
    config = _config(tmp_path)
    archive.append_scan_batch(config, "scan_1", BASE_TS, [_analyzed_trace()])
    ledger = archive.load_archive_ledger_readonly(config)
    trace = ledger["decision_traces"][0]
    result = four_hour_counterfactual.counterfactual_from_trace(trace)
    assert result["comparison"] == four_hour_counterfactual.COMPARE_SAME
    assert result["capital_authority"] is False
    assert result["tier_authority"] is False


def test_archive_module_has_no_network_model_discord_or_market_data_calls():
    tree = ast.parse(Path("src/forward_research_archive.py").read_text(encoding="utf-8"))
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

    forbidden_import_prefixes = (
        "openai",
        "anthropic",
        "requests",
        "aiohttp",
        "discord",
        "yfinance",
        "src.market_data",
        "src.state_store",
        "src.discord_alerts",
        "src.claude_client",
    )
    for prefix in forbidden_import_prefixes:
        assert not any(module.startswith(prefix) for module in imports)

    for forbidden_call in (
        "batch_download",
        "fetch_ticker",
        "fetch_one_hour_bars",
        "async_claude_scan",
        "claude_call",
        "send_alert",
        "record_alert",
        "check_alert",
        "apply_ladder_arbitration",
    ):
        assert forbidden_call not in calls


def test_production_config_enables_archive_without_changing_capacity_or_cadence():
    config = yaml.safe_load(Path("config/doctrine_config.yaml").read_text(encoding="utf-8"))
    assert config["scan"]["interval_minutes"] == 15
    assert config["prefilter"]["max_claude_candidates_per_scan"] == 30
    assert config["telemetry"]["max_scan_summaries"] == 300
    assert config["telemetry"]["max_decision_traces"] == 9000
    assert config["research_archive"] == {
        "enabled": True,
        "directory": ".state/research_archive",
        "retention_days": 120,
        "max_daily_file_bytes": 10485760,
    }


def test_production_tier_thresholds_remain_unchanged():
    config = yaml.safe_load(Path("config/doctrine_config.yaml").read_text(encoding="utf-8"))
    assert config["tiers"]["snipe_it"]["min_score"] == 85
    assert config["tiers"]["snipe_it"]["min_rr"] == 3.0
    assert config["tiers"]["starter"]["min_score"] == 75
    assert config["tiers"]["starter"]["min_rr"] == 3.0
    assert config["tiers"]["near_entry"]["min_score"] == 60


def test_production_universe_remains_814_symbols():
    symbols = [
        line.strip().upper()
        for line in Path("config/tickers.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(dict.fromkeys(symbols)) == 814


def test_scheduler_archive_call_is_scan_only_and_separate_from_14v_write():
    text = Path("src/scheduler.py").read_text(encoding="utf-8")
    scan_part, manual_part = text.split("async def run_analyze(", 1)
    assert "from src import forward_research_archive" in text
    assert "forward_research_archive.append_scan_batch" in scan_part
    assert "forward_research_archive.append_scan_batch" not in manual_part

    telemetry_pos = scan_part.index("scan_telemetry.write_scan_telemetry")
    archive_pos = scan_part.index("forward_research_archive.append_scan_batch")
    assert telemetry_pos < archive_pos
    between = scan_part[telemetry_pos:archive_pos]
    assert 'log.warning("TELEMETRY_WRITE_ERROR: %s", exc)' in between


@pytest.mark.asyncio
async def test_scheduler_attempts_archive_even_when_phase14v_write_raises(monkeypatch, tmp_path):
    config = _config(tmp_path, enabled=True)
    config.update({
        "prefilter": {"max_claude_candidates_per_scan": 30},
        "tiers": {"snipe_it": {"min_rr": 3.0}},
    })
    calls = {"telemetry": 0, "archive": 0}

    class DummyDf:
        pass

    monkeypatch.setattr(
        scheduler.market_data_mod,
        "batch_download",
        lambda tickers, cfg: {
            "AAA": {"data_status": "OK", "df": DummyDf(), "latest_close": 100.0}
        },
    )
    monkeypatch.setattr(
        scheduler.indicators,
        "enrich",
        lambda ticker, df, cfg: {
            "ticker": ticker,
            "current_price": 100.0,
            "invalidation_level": 95.0,
            "data_status": "OK",
        },
    )
    monkeypatch.setattr(
        scheduler.prefilter_mod,
        "prefilter",
        lambda rows, cfg: {
            "all_results": [{"ticker": "AAA", "data_status": "OK", "eligible_for_claude": False}],
            "ranked_results": [],
            "claude_candidates": [],
            "board_summary": {
                "total_rejected_by_data_quality": 0,
                "total_rejected_by_veto": 1,
                "total_above_prefilter_min_score": 0,
                "total_claude_candidates": 0,
            },
        },
    )
    monkeypatch.setattr(scheduler.state_store, "save", lambda state, cfg: None)

    def broken_telemetry(*args, **kwargs):
        calls["telemetry"] += 1
        raise OSError("14V unavailable")

    def archive_attempt(*args, **kwargs):
        calls["archive"] += 1
        return {"ok": True, "written": False, "reason": "no_research_traces"}

    monkeypatch.setattr(scheduler.scan_telemetry, "write_scan_telemetry", broken_telemetry)
    monkeypatch.setattr(scheduler.forward_research_archive, "append_scan_batch", archive_attempt)

    result = await scheduler.run_scan_pipeline(
        ["AAA"],
        bot=None,
        config=config,
        state={},
        system_prompt="",
        client=None,
        scan_id="scan_test",
    )

    assert result["status"] == "complete"
    assert calls == {"telemetry": 1, "archive": 1}


def test_research_builders_accept_archive_directory_as_alternative_source():
    velocity_text = Path("scripts/build_velocity_dataset.py").read_text(encoding="utf-8")
    cap_text = Path("scripts/build_cap40b_dataset.py").read_text(encoding="utf-8")
    for text in (velocity_text, cap_text):
        assert "add_mutually_exclusive_group(required=True)" in text
        assert '"--telemetry"' in text
        assert '"--archive-dir"' in text
        assert "forward_research_archive.load_directory_readonly" in text

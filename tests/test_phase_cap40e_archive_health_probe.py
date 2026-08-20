"""CAP-40E — read-only archive health/persistence-anchor regressions."""

from __future__ import annotations

import ast
from datetime import datetime
import json
from pathlib import Path

import discord
from discord.ext import commands
import pytest
import yaml

import main
from src import forward_research_archive as archive
from src import research_archive_health as health


TS = "2026-08-20T14:00:00+00:00"


def _config(tmp_path: Path, *, enabled=True) -> dict:
    return {
        "scan": {
            "timezone": "America/New_York",
            "interval_minutes": 15,
            "market_hours_only": True,
            "market_open": "09:35",
            "market_close": "15:55",
        },
        "state": {"state_file": str(tmp_path / "alert_history.json")},
        "telemetry": {
            "telemetry_file": str(tmp_path / "scan_telemetry.json"),
            "max_scan_summaries": 300,
            "max_decision_traces": 9000,
        },
        "research_archive": {
            "enabled": enabled,
            "directory": str(tmp_path / "research_archive"),
            "retention_days": 120,
            "max_daily_file_bytes": 10485760,
        },
        "audit_access": {
            "enabled": True,
            "allowed_user_ids": [],
            "allowed_channel_ids": [12345],
            "max_rows": 3,
        },
        "prefilter": {"max_claude_candidates_per_scan": 30},
    }


def _trace(ticker="AAA") -> dict:
    return {
        "schema_version": "14V.2",
        "scan_id": "scan_20260820_140000_abc123",
        "ticker": ticker,
        "trace_kind": "analyzed",
        "pipeline": {
            "market_data_ok": True,
            "prefilter_eligible": True,
            "prefilter_rank": 5,
            "prefilter_score": 88,
            "admitted_to_deep_analysis": True,
            "claude_analyzed": True,
        },
        "velocity_observation": {
            "version": "VELOCITY-1C",
            "research_only": True,
            "capital_authority": False,
            "tier_authority": False,
            "observed_at": TS,
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
        },
    }


def _write_scan(config: dict, scan_id: str, ts: str = TS) -> dict:
    trace = _trace()
    trace["scan_id"] = scan_id
    result = archive.append_scan_batch(config, scan_id, ts, [trace])
    assert result["ok"] is True
    assert result["written"] is True
    return result


def test_disabled_status_is_explicit_and_does_not_create_directory(tmp_path):
    config = _config(tmp_path, enabled=False)
    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_DISABLED
    assert result["durability_proven"] is False
    assert not archive.archive_dir(config).exists()


def test_enabled_missing_directory_is_not_falsely_ready(tmp_path):
    config = _config(tmp_path)
    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_MISSING_DIRECTORY
    assert result["partition_count"] == 0


def test_empty_archive_directory_is_not_falsely_ready(tmp_path):
    config = _config(tmp_path)
    archive.archive_dir(config).mkdir(parents=True)
    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_EMPTY


def test_ready_snapshot_reports_partition_range_bytes_and_scan_anchors(tmp_path):
    config = _config(tmp_path)
    first = _write_scan(config, "scan_20260820_140000_first")
    _write_scan(config, "scan_20260820_141500_second", "2026-08-20T14:15:00+00:00")

    result = health.snapshot(config, now=datetime.fromisoformat("2026-08-20T15:00:00+00:00"))

    assert result["status"] == health.STATUS_READY
    assert result["partition_count"] == 1
    assert result["oldest_partition"] == "2026-08-20"
    assert result["newest_partition"] == "2026-08-20"
    assert result["current_partition_present"] is True
    assert result["oldest_scan_id"] == "scan_20260820_140000_first"
    assert result["latest_scan_id"] == "scan_20260820_141500_second"
    assert result["latest_scan_timestamp"] == "2026-08-20T14:15:00+00:00"
    assert result["latest_trace_count"] == 1
    assert result["latest_partition_bytes"] >= first["bytes_appended"]
    assert result["total_partition_bytes"] == result["latest_partition_bytes"]
    assert result["durability_proven"] is False


def test_snapshot_current_session_date_is_et_not_utc_date(tmp_path):
    config = _config(tmp_path)
    result = health.snapshot(
        config,
        now=datetime.fromisoformat("2026-08-20T00:30:00+00:00"),
    )
    assert result["current_session_date"] == "2026-08-19"


def test_multiple_partitions_report_oldest_and_newest_anchor(tmp_path):
    config = _config(tmp_path)
    _write_scan(config, "scan_aug20", "2026-08-20T14:00:00+00:00")
    _write_scan(config, "scan_aug21", "2026-08-21T14:00:00+00:00")

    result = health.snapshot(config, now=datetime.fromisoformat("2026-08-21T15:00:00+00:00"))

    assert result["status"] == health.STATUS_READY
    assert result["partition_count"] == 2
    assert result["oldest_partition"] == "2026-08-20"
    assert result["newest_partition"] == "2026-08-21"
    assert result["oldest_scan_id"] == "scan_aug20"
    assert result["latest_scan_id"] == "scan_aug21"


def test_non_date_jsonl_is_ignored_from_partition_health(tmp_path):
    config = _config(tmp_path)
    _write_scan(config, "scan_good")
    directory = archive.archive_dir(config)
    (directory / "notes.jsonl").write_text("not a study partition\n", encoding="utf-8")

    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_READY
    assert result["partition_count"] == 1


def test_malformed_trailing_line_is_degraded_but_preserves_last_valid_anchor(tmp_path):
    config = _config(tmp_path)
    written = _write_scan(config, "scan_before_partial")
    path = Path(written["path"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{partial")

    result = health.snapshot(config, now=datetime.fromisoformat(TS))

    assert result["status"] == health.STATUS_DEGRADED
    assert result["latest_scan_id"] == "scan_before_partial"
    assert result["latest_partition_malformed_tail_lines"] == 1


def test_partition_with_no_valid_batch_is_degraded(tmp_path):
    config = _config(tmp_path)
    directory = archive.archive_dir(config)
    directory.mkdir(parents=True)
    (directory / "2026-08-20.jsonl").write_text("bad\n{broken\n", encoding="utf-8")

    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_DEGRADED
    assert result["latest_scan_id"] is None


def test_snapshot_is_strictly_read_only(tmp_path):
    config = _config(tmp_path)
    written = _write_scan(config, "scan_readonly")
    path = Path(written["path"])
    before = path.read_bytes()

    health.snapshot(config, now=datetime.fromisoformat(TS))

    assert path.read_bytes() == before


def test_path_collision_is_surfaceable_without_writing(tmp_path):
    config = _config(tmp_path)
    config["research_archive"]["directory"] = config["state"]["state_file"]
    result = health.snapshot(config, now=datetime.fromisoformat(TS))
    assert result["status"] == health.STATUS_PATH_COLLISION
    assert not Path(config["state"]["state_file"]).exists()


def test_render_is_compact_and_explicit_that_durability_is_not_proven(tmp_path):
    config = _config(tmp_path)
    _write_scan(config, "scan_anchor")
    text = health.render(health.snapshot(config, now=datetime.fromisoformat(TS)))
    assert "CAP-40D Research Archive Status" in text
    assert "scan_anchor" in text
    assert "Durability proven by this snapshot: **NO**" in text
    assert len(text) < 1900


def test_health_module_has_no_network_model_discord_or_write_calls():
    tree = ast.parse(Path("src/research_archive_health.py").read_text(encoding="utf-8"))
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
        "yfinance",
        "src.market_data",
        "src.state_store",
        "src.discord_alerts",
        "src.claude_client",
    ):
        assert not any(module.startswith(prefix) for module in imports)

    for forbidden in (
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "replace",
        "append_scan_batch",
        "batch_download",
        "fetch_ticker",
        "claude_call",
        "send_alert",
        "record_alert",
        "check_alert",
    ):
        assert forbidden not in calls


def _bot_and_command(config: dict):
    bot = commands.Bot(
        command_prefix="!",
        intents=discord.Intents.none(),
        help_command=None,
    )
    main.register_commands(bot, config, model_client=None, system_prompt=None)
    return bot, bot.get_command("archivestatus")


def test_archive_status_command_is_registered_and_help_mentions_it(tmp_path):
    config = _config(tmp_path)
    bot, command = _bot_and_command(config)
    assert command is not None
    assert command.name == "archivestatus"
    assert bot.get_command("help") is not None


class _FakeCtx:
    def __init__(self, user_id=1, channel_id=1):
        self.author = type("Author", (), {"id": user_id})()
        self.channel = type("Channel", (), {"id": channel_id})()
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_archive_status_command_denies_non_operator(tmp_path):
    config = _config(tmp_path)
    _, command = _bot_and_command(config)
    ctx = _FakeCtx(user_id=999, channel_id=999)

    await command.callback(ctx)

    assert ctx.messages == ["Archive status access denied."]


@pytest.mark.asyncio
async def test_archive_status_command_returns_anchor_to_authorized_operator(tmp_path):
    config = _config(tmp_path)
    _write_scan(config, "scan_runtime_anchor")
    _, command = _bot_and_command(config)
    ctx = _FakeCtx(user_id=999, channel_id=12345)

    await command.callback(ctx)

    text = "\n".join(ctx.messages)
    assert "CAP-40D Research Archive Status" in text
    assert "scan_runtime_anchor" in text
    assert "Durability proven by this snapshot: **NO**" in text


def test_production_contract_stays_814_30_and_15():
    config = yaml.safe_load(Path("config/doctrine_config.yaml").read_text(encoding="utf-8"))
    symbols = [
        line.strip().upper()
        for line in Path("config/tickers.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(dict.fromkeys(symbols)) == 814
    assert config["prefilter"]["max_claude_candidates_per_scan"] == 30
    assert config["scan"]["interval_minutes"] == 15
    assert config["telemetry"]["max_decision_traces"] == 9000
    assert config["research_archive"]["enabled"] is True

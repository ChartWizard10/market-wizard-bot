"""Phase AI-2R — Claude Opus 5 production provider restoration.

    This is a Claude bot. Anthropic owns the model boundary.

    Railway -> Anthropic credential -> anthropic.AsyncAnthropic -> scheduler
    -> src.claude_client -> client.messages.create(model="claude-opus-5", ...)

There is no OpenAI runtime, no compatibility adapter, and no cross-provider
fallback. If Anthropic is unavailable the scanner fails closed.

Provider restoration is NOT strategy restoration: every scanner and research
change merged after the provider migration is preserved.
"""

import ast
import asyncio
import inspect
import logging
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

import main as production_main
from src import claude_client
from src.claude_client import (
    DEFAULT_CLAUDE_MODEL,
    async_claude_scan,
    claude_call,
    resolve_claude_model,
)

OPUS = "claude-opus-5"
SONNET = "claude-sonnet-4-6"

REPO = pathlib.Path(__file__).resolve().parents[1]

CRED_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "OPENAI_API_KEY",
             "OPENAI_MODEL", "ANTHROPIC_MODEL", "DISCORD_TOKEN")

VALID_JSON = (
    '{"ticker":"T","timestamp_et":"2026-01-01T10:00:00","tier":"WAIT","score":10,'
    '"setup_family":"none","structure_event":"none","trend_state":"basing",'
    '"sma_value_alignment":"mixed","zone_type":"none","trigger_level":1,'
    '"retest_status":"missing","hold_status":"missing","invalidation_condition":"x",'
    '"invalidation_level":1,"targets":[],"risk_reward":null,"overhead_status":"unknown",'
    '"forced_participation":false,"missing_conditions":[],"upgrade_trigger":"x",'
    '"next_action":"x","discord_channel":"none","capital_action":"no_trade","reason":"x"}'
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in CRED_VARS:
        monkeypatch.delenv(var, raising=False)


def config():
    return yaml.safe_load(open(REPO / "config" / "doctrine_config.yaml"))


def mock_anthropic_client():
    """Stands in for anthropic.AsyncAnthropic. No live request, no credits."""
    client = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=VALID_JSON)]
    client.messages.create = AsyncMock(return_value=response)
    return client


# ===========================================================================
# Provider identity
# ===========================================================================

def test_build_bot_creates_a_native_anthropic_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    sentinel = mock_anthropic_client()
    made = {}

    def _factory(api_key=None, **_kw):
        made["api_key"] = api_key
        return sentinel

    with patch("anthropic.AsyncAnthropic", _factory):
        _bot, client, _prompt = production_main.build_bot(config())

    assert client is sentinel
    assert made["api_key"] == "fake-anthropic-key"
    assert hasattr(client.messages, "create")     # the Messages contract


def test_build_bot_never_imports_or_instantiates_openai(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    with patch("anthropic.AsyncAnthropic", lambda **_kw: mock_anthropic_client()):
        production_main.build_bot(config())

    src = inspect.getsource(production_main.build_bot)
    # `model_client` is the provider-neutral local variable name and is fine;
    # the OpenAI SDK, its adapter and its module must all be absent.
    for banned in ("AsyncOpenAI", "openai", "OpenAISchedulerCompatClient",
                   "src.model_client"):
        assert banned not in src
    assert "AsyncAnthropic" in src


def test_no_openai_adapter_modules_exist():
    assert not (REPO / "src" / "model_client.py").exists()
    assert not (REPO / "src" / "openai_scheduler_compat.py").exists()


def test_no_production_import_path_reaches_openai():
    """AST proof over every production module reachable from main.py."""
    offenders = []
    for path in [REPO / "main.py"] + sorted((REPO / "src").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "openai":
                        offenders.append(f"{path.name}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root == "openai" or node.module in (
                        "src.model_client", "src.openai_scheduler_compat"):
                    offenders.append(f"{path.name}:{node.lineno} from {node.module}")
            elif isinstance(node, ast.Attribute) and node.attr == "create":
                owner = getattr(node.value, "attr", None)
                if owner == "responses":
                    offenders.append(f"{path.name}:{node.lineno} responses.create")
    assert offenders == [], offenders


def test_requirements_has_anthropic_and_no_openai():
    reqs = (REPO / "requirements.txt").read_text()
    packages = [ln.strip() for ln in reqs.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    assert "anthropic" in packages
    assert not any(p.split("=")[0].split(">")[0].strip() == "openai" for p in packages)


def test_anthropic_sdk_imports():
    import anthropic
    assert hasattr(anthropic, "AsyncAnthropic")


# ===========================================================================
# Credential precedence — C1..C6
# ===========================================================================

def test_c1_anthropic_api_key_is_selected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "primary")
    key, source = production_main.resolve_anthropic_api_key()
    assert key == "primary"
    assert source == "ANTHROPIC_API_KEY"


def test_c2_legacy_anthropic_key_is_supported(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_KEY", "legacy")
    key, source = production_main.resolve_anthropic_api_key()
    assert key == "legacy"
    assert source == "ANTHROPIC_KEY"


def test_c3_anthropic_api_key_wins_when_both_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "primary")
    monkeypatch.setenv("ANTHROPIC_KEY", "legacy")
    key, source = production_main.resolve_anthropic_api_key()
    assert key == "primary"
    assert source == "ANTHROPIC_API_KEY"


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_c4_blank_credentials_are_missing(monkeypatch, blank):
    monkeypatch.setenv("ANTHROPIC_API_KEY", blank)
    monkeypatch.setenv("ANTHROPIC_KEY", blank)
    key, source = production_main.resolve_anthropic_api_key()
    assert key is None
    assert source == "MISSING"


def test_c5_an_openai_key_is_not_an_anthropic_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6")
    key, source = production_main.resolve_anthropic_api_key()
    assert key is None
    assert source == "MISSING"


def test_c6_the_credential_value_is_never_logged(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SUPER-SECRET-VALUE")
    with caplog.at_level(logging.INFO):
        with patch("anthropic.AsyncAnthropic", lambda **_kw: mock_anthropic_client()):
            production_main.build_bot(config())
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SUPER-SECRET" not in blob
    assert "sk-ant" not in blob
    # ...while the SOURCE is reported.
    assert "credential_source=ANTHROPIC_API_KEY" in blob


# ===========================================================================
# OpenAI environment has zero authority
# ===========================================================================

def test_openai_env_alone_creates_no_model_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6")
    monkeypatch.setenv("DISCORD_TOKEN", "x")

    with patch("anthropic.AsyncAnthropic", side_effect=AssertionError(
            "Anthropic must not be constructed without a credential")):
        _bot, client, _prompt = production_main.build_bot(config())
    assert client is None

    report = production_main.validate_startup(config())
    assert report["ok"] is True                     # graceful, not fatal
    warning = " ".join(report["warnings"])
    assert "Anthropic API key is not set" in warning
    assert "OPENAI" not in warning.upper()


def test_openai_env_is_ignored_when_anthropic_is_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    sentinel = mock_anthropic_client()
    with patch("anthropic.AsyncAnthropic", lambda **_kw: sentinel):
        _bot, client, _prompt = production_main.build_bot(config())
    assert client is sentinel
    model, _source = resolve_claude_model(config())
    assert model == OPUS
    assert "gpt" not in model


# ===========================================================================
# Startup matrix — S1..S6
# ===========================================================================

def test_s1_discord_plus_anthropic_is_healthy(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    report = production_main.validate_startup(config())
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["warnings"] == []


def test_s2_discord_without_anthropic_warns_only(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    report = production_main.validate_startup(config())
    assert report["ok"] is True
    assert len(report["warnings"]) == 1
    assert "Anthropic" in report["warnings"][0]


def test_s3_anthropic_without_discord_is_a_hard_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    report = production_main.validate_startup(config())
    assert report["ok"] is False
    assert any("DISCORD_TOKEN" in e for e in report["errors"])


def test_s4_legacy_anthropic_key_satisfies_the_model_credential(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("ANTHROPIC_KEY", "legacy")
    report = production_main.validate_startup(config())
    assert report["ok"] is True
    assert report["warnings"] == []


def test_s5_runtime_ready_line_reports_provider_and_model(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with caplog.at_level(logging.INFO):
        with patch("anthropic.AsyncAnthropic", lambda **_kw: mock_anthropic_client()):
            production_main.build_bot(config())
    lines = [r.getMessage() for r in caplog.records
             if "CLAUDE_RUNTIME_READY" in r.getMessage()]
    assert len(lines) == 1
    assert "provider=anthropic" in lines[0]
    assert "credential_source=ANTHROPIC_API_KEY" in lines[0]
    assert OPUS in lines[0]


# ===========================================================================
# Opus 5 routing — through the real production call path
# ===========================================================================

def test_default_model_constant_is_opus_5():
    assert DEFAULT_CLAUDE_MODEL == OPUS


def test_config_model_is_opus_5():
    cfg = config()
    assert cfg["claude"]["model"] == OPUS
    assert "model" not in cfg                # the OpenAI provider block is gone


@pytest.mark.parametrize("scenario,cfg_model,env,expected_source", [
    ("environment override", SONNET, OPUS, "ENVIRONMENT"),
    ("config value",         OPUS,   None, "CONFIG"),
    ("repository default",   None,   None, "DEFAULT"),
])
def test_opus5_reaches_messages_create(monkeypatch, scenario, cfg_model, env,
                                       expected_source):
    cfg = config()
    if cfg_model is None:
        cfg["claude"].pop("model", None)
    else:
        cfg["claude"]["model"] = cfg_model
    if env:
        monkeypatch.setenv("ANTHROPIC_MODEL", env)

    model, source = resolve_claude_model(cfg)
    assert model == OPUS, scenario
    assert source == expected_source, scenario

    client = mock_anthropic_client()
    asyncio.run(claude_call({"ticker": "T", "current_price": 10.0},
                            "SYSTEM PROMPT", client, asyncio.Semaphore(1), cfg))
    assert client.messages.create.await_args.kwargs["model"] == OPUS, scenario


def test_in_provider_rollback_changes_model_not_provider(monkeypatch):
    """Emergency rollback stays WITHIN Anthropic."""
    monkeypatch.setenv("ANTHROPIC_MODEL", SONNET)
    client = mock_anthropic_client()
    asyncio.run(claude_call({"ticker": "T", "current_price": 10.0},
                            "SYSTEM PROMPT", client, asyncio.Semaphore(1), config()))
    assert client.messages.create.await_args.kwargs["model"] == SONNET
    # Still the Anthropic Messages contract — no adapter, no other provider.
    assert set(client.messages.create.await_args.kwargs) == {
        "model", "max_tokens", "system", "messages"}


# ===========================================================================
# End-to-end mocked proof and output parity
# ===========================================================================

def test_end_to_end_mocked_claude_path_produces_the_same_signal_contract():
    client = mock_anthropic_client()
    result = asyncio.run(claude_call({"ticker": "T", "current_price": 10.0},
                                     "SYSTEM PROMPT", client,
                                     asyncio.Semaphore(1), config()))
    assert sorted(result) == ["error_message", "error_type", "signal", "ticker"]
    assert result["error_type"] is None
    signal = result["signal"]
    assert signal["tier"] == "WAIT"
    assert signal["capital_action"] == "no_trade"
    assert signal["discord_channel"] == "none"
    assert type(client).__module__ != "src.openai_scheduler_compat"


def test_batch_scan_makes_exactly_one_model_call_per_candidate(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", OPUS)
    cfg = config()
    cfg["claude"]["claude_min_seconds_between_calls"] = 0
    client = mock_anthropic_client()
    candidates = [{"ticker": t, "current_price": 10.0} for t in ("AAA", "BBB", "CCC")]
    results = asyncio.run(async_claude_scan(candidates, "SYSTEM PROMPT", client, cfg))

    assert client.messages.create.await_count == 3          # one per candidate
    assert len(results) == 3
    assert [c.kwargs["model"] for c in client.messages.create.await_args_list] == [OPUS] * 3
    # The Anthropic Messages contract was used — never an OpenAI Responses call.
    assert client.mock_calls
    assert not any("responses" in str(c) for c in client.mock_calls)


def test_model_selection_log_names_opus_5(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_MODEL", OPUS)
    cfg = config()
    cfg["claude"]["claude_min_seconds_between_calls"] = 0
    with caplog.at_level(logging.INFO, logger="src.claude_client"):
        asyncio.run(async_claude_scan([{"ticker": "AAA", "current_price": 10.0}],
                                      "SYSTEM PROMPT", mock_anthropic_client(), cfg))
    lines = [r.getMessage() for r in caplog.records
             if "CLAUDE_MODEL_SELECTED" in r.getMessage()]
    assert len(lines) == 1
    assert f"model={OPUS}" in lines[0]
    assert "source=ENVIRONMENT" in lines[0]


# ===========================================================================
# Operator-facing text
# ===========================================================================

def test_manual_command_error_text_names_claude_not_gpt():
    src = inspect.getsource(production_main.register_commands)
    assert "ERROR: Claude model not configured" in src
    assert "Anthropic API key missing" in src
    for banned in ("GPT-5.6", "OPENAI_API_KEY", "OpenAI"):
        assert banned not in src


def test_status_command_uses_the_claude_resolver():
    src = inspect.getsource(production_main.register_commands)
    assert "from src.claude_client import resolve_claude_model" in src
    assert "resolve_claude_model(config)" in src
    assert "resolve_model(config)" not in src.replace("resolve_claude_model(config)", "")


def test_scan_summary_text_names_claude():
    summary = {"scan_id": "s1", "total_claude_candidates": 7,
               "final_tier_counts": {}, "top_candidates": []}
    text = production_main.format_scan_summary(summary)
    assert "Claude candidates: 7" in text
    assert "GPT" not in text


# ===========================================================================
# Preservation — provider restoration is not strategy restoration
# ===========================================================================

def test_scanner_strategy_configuration_is_preserved():
    cfg = config()
    assert cfg["scan"]["interval_minutes"] == 15
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30
    assert cfg["prefilter"]["prefilter_min_score"] == 55
    assert cfg["tiers"]["snipe_it"]["min_rr"] == 3.0
    # AI-2R pacing remains intact; the Opus 5 output ceiling was later raised
    # after a live adaptive-thinking truncation incident.
    assert cfg["claude"]["max_tokens"] == 8192
    assert cfg["claude"]["claude_concurrency"] == 1
    assert cfg["claude"]["claude_min_seconds_between_calls"] == 4
    assert cfg["claude"]["claude_max_input_tokens_per_minute_budget"] == 25000


def test_every_later_scanner_and_research_organ_survives():
    """The later work must still be importable and wired."""
    for module in ("market_data", "indicators", "prefilter", "tiering",
                   "one_hour_entry", "four_hour_operational", "timeframe_alignment",
                   "higher_timeframe_context", "scan_telemetry", "state_store",
                   "setup_family_compiler", "family_admission", "family_resolver",
                   "capacity_boundary_study", "forward_research_archive",
                   "research_archive_health", "four_hour_outcome_study",
                   "four_hour_study_design", "four_hour_counterfactual"):
        __import__(f"src.{module}")

    from src import scheduler
    scheduler_src = inspect.getsource(scheduler)
    assert "from src.claude_client import async_claude_scan, claude_call" in scheduler_src
    # MBT/R4H truth engines still present.
    from src.market_data import partition_daily_bars, aggregate_four_hour_bars
    from src.four_hour_operational import AUTHORITY_MODE
    assert AUTHORITY_MODE == "SHADOW_EVIDENCE_ONLY"


def test_the_system_prompt_loads():
    """Enduring invariant: the analyst boundary can read its instructions.

    (Phase-scoped proof that AI-2R did not EDIT the prompt is PR-review
    evidence — `git diff origin/main...HEAD -- prompts/market_wizard_system.md`
    — and deliberately does not live here. A permanent test must not veto a
    future phase that legitimately changes the prompt.)
    """
    prompt = claude_client.load_system_prompt("prompts/market_wizard_system.md")
    assert isinstance(prompt, str)
    assert prompt.strip()


# ===========================================================================
# Repository cleanliness gates
# ===========================================================================

ACTIVE_RUNTIME_PATHS = ["main.py", "src", "config", ".env.example",
                        "requirements.txt"]


def test_no_active_openai_runtime_or_config_reference():
    import subprocess
    pattern = (r"OPENAI_API_KEY|OPENAI_MODEL|AsyncOpenAI|OpenAISchedulerCompatClient"
               r"|openai_scheduler_compat|from openai|import openai"
               r"|provider: \"openai\"|name: \"gpt-5\.6\"")
    hits = subprocess.run(
        ["grep", "-rnE", pattern] + ACTIVE_RUNTIME_PATHS,
        capture_output=True, text=True, cwd=REPO).stdout
    hits = [h for h in hits.splitlines() if "__pycache__" not in h]
    assert hits == [], hits


def test_production_docs_name_anthropic_claude_opus_5():
    for doc in ("README.md", "docs/ARCHITECTURE.md", "docs/PRODUCTION_STATE.md",
                "docs/RUNBOOK.md"):
        text = (REPO / doc).read_text()
        assert OPUS in text, doc
        assert "Anthropic" in text, doc


def test_obsolete_ai1_provider_documents_are_gone():
    for doc in ("docs/AI1_ACCEPTANCE.md", "docs/AI1_GPT56_RUNTIME.md",
                "docs/CHANGELOG_AI1_NOTE.md"):
        assert not (REPO / doc).exists(), doc

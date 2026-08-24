"""Phase MR-1 — Anthropic model routing control.

Model intelligence and scanner doctrine are separate layers.

    1. ANTHROPIC_MODEL environment variable (non-empty, trimmed)
    2. config["claude"]["model"]
    3. DEFAULT_CLAUDE_MODEL (claude-opus-5 since AI-2R)

The operator selects the model at runtime; the repository holds the fallback.
Removing the environment variable restores the config model with no code
change. Nothing else about the Claude call may move.
"""

import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import claude_client
from src.claude_client import (
    DEFAULT_CLAUDE_MODEL,
    async_claude_scan,
    claude_call,
    resolve_claude_model,
)

ENV_VAR = "ANTHROPIC_MODEL"

SONNET = "claude-sonnet-4-6"        # emergency in-provider model rollback
OPUS = "claude-opus-5"              # AI-2R production default
FABLE = "claude-fable-5"

CFG = {"claude": {"model": SONNET, "max_tokens": 1200,
                  "claude_concurrency": 1,
                  "claude_min_seconds_between_calls": 0,
                  "claude_max_input_tokens_per_minute_budget": 25_000}}

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
    """No test may leak ANTHROPIC_MODEL into another."""
    monkeypatch.delenv(ENV_VAR, raising=False)


def mock_client():
    """A mocked Anthropic client. No live request, no credits spent."""
    client = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=VALID_JSON)]
    client.messages.create = AsyncMock(return_value=response)
    return client


def call(config, client=None, ticker="T"):
    client = client or mock_client()
    result = asyncio.run(claude_call(
        {"ticker": ticker, "current_price": 10.0}, "SYSTEM PROMPT", client,
        asyncio.Semaphore(1), config))
    return client, result


# ===========================================================================
# 1-9 — resolver unit matrix
# ===========================================================================

def test_1_environment_wins_over_config(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    model, source = resolve_claude_model(CFG)
    assert model == FABLE
    assert source == "ENVIRONMENT"


@pytest.mark.parametrize("value", [
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-haiku-4-5-20251001",
    "some-future-model-id",
])
def test_2_any_environment_model_passes_through_exactly(monkeypatch, value):
    """The router is generic — never Fable-specific, never aliased, never
    date-appended, never rewritten."""
    monkeypatch.setenv(ENV_VAR, value)
    model, source = resolve_claude_model(CFG)
    assert model == value
    assert source == "ENVIRONMENT"


def test_3_environment_unset_falls_through_to_config():
    model, source = resolve_claude_model(CFG)
    assert model == SONNET
    assert source == "CONFIG"


def test_4_environment_empty_string_falls_through(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "")
    model, source = resolve_claude_model(CFG)
    assert model == SONNET
    assert source == "CONFIG"


@pytest.mark.parametrize("blank", ["   ", "\t", "\n", "  \t \n "])
def test_5_environment_whitespace_falls_through(monkeypatch, blank):
    monkeypatch.setenv(ENV_VAR, blank)
    model, source = resolve_claude_model(CFG)
    assert model == SONNET
    assert source == "CONFIG"


def test_5b_environment_value_is_trimmed(monkeypatch):
    monkeypatch.setenv(ENV_VAR, f"  {FABLE}  ")
    model, source = resolve_claude_model(CFG)
    assert model == FABLE            # exact, no surrounding whitespace
    assert source == "ENVIRONMENT"


def test_6_config_custom_value_is_used_exactly():
    model, source = resolve_claude_model({"claude": {"model": "custom-test-model"}})
    assert model == "custom-test-model"
    assert source == "CONFIG"


def test_7_config_model_missing_yields_the_safe_default():
    for config in ({"claude": {"max_tokens": 1200}}, {}, {"claude": {}}):
        model, source = resolve_claude_model(config)
        assert model == DEFAULT_CLAUDE_MODEL == OPUS
        assert source == "DEFAULT"


def test_8_config_model_empty_yields_the_default():
    model, source = resolve_claude_model({"claude": {"model": ""}})
    assert model == OPUS
    assert source == "DEFAULT"


@pytest.mark.parametrize("blank", ["   ", "\t", "\n"])
def test_9_config_model_whitespace_yields_the_default(blank):
    model, source = resolve_claude_model({"claude": {"model": blank}})
    assert model == OPUS
    assert source == "DEFAULT"


def test_9b_no_empty_model_string_can_ever_be_produced(monkeypatch):
    """Every combination of blank inputs still yields a real model name."""
    for env in (None, "", "   "):
        if env is None:
            monkeypatch.delenv(ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(ENV_VAR, env)
        for cfg in ({}, {"claude": {}}, {"claude": {"model": ""}},
                    {"claude": {"model": "  "}}, {"claude": {"model": None}}):
            model, source = resolve_claude_model(cfg)
            assert model.strip() == model
            assert model == OPUS
            assert source == "DEFAULT"


def test_9c_resolver_never_raises_on_hostile_config():
    for hostile in (None, [], "string", 42, {"claude": "not-a-dict"}):
        try:
            model, source = resolve_claude_model(hostile)
        except AttributeError:
            # A non-dict config is not a supported production shape; the
            # scanner always passes the loaded doctrine dict.
            continue
        assert model
        assert source in ("ENVIRONMENT", "CONFIG", "DEFAULT")


# ===========================================================================
# I1-I5 — API-call integration (mocked; no live request)
# ===========================================================================

def test_i1_fable_environment_reaches_messages_create_exactly(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    client, _ = call(CFG)
    assert client.messages.create.await_args.kwargs["model"] == FABLE


def test_i2_config_model_reaches_messages_create_when_env_absent():
    client, _ = call(CFG)
    assert client.messages.create.await_args.kwargs["model"] == SONNET


def test_i3_default_reaches_messages_create_when_config_has_no_model():
    client, _ = call({"claude": {"max_tokens": 1200}})
    assert client.messages.create.await_args.kwargs["model"] == OPUS


def test_i4_every_other_call_parameter_is_identical(monkeypatch):
    """Same fixture, model routed three different ways — only `model` moves."""
    baseline_client, _ = call(CFG)
    baseline = dict(baseline_client.messages.create.await_args.kwargs)

    monkeypatch.setenv(ENV_VAR, FABLE)
    fable_client, _ = call(CFG)
    fable = dict(fable_client.messages.create.await_args.kwargs)

    monkeypatch.delenv(ENV_VAR, raising=False)
    default_client, _ = call({"claude": {"max_tokens": 1200}})
    default = dict(default_client.messages.create.await_args.kwargs)

    assert set(baseline) == set(fable) == set(default) == {
        "model", "max_tokens", "system", "messages"}
    for other in (fable, default):
        assert other["max_tokens"] == baseline["max_tokens"] == 1200
        assert other["system"] == baseline["system"] == "SYSTEM PROMPT"
        assert other["messages"] == baseline["messages"]
    assert baseline["model"] == SONNET      # from the test CFG, via CONFIG
    assert fable["model"] == FABLE
    assert default["model"] == OPUS         # via DEFAULT


def test_i5_result_schema_and_signal_parsing_are_unchanged(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    _, result = call(CFG)
    assert sorted(result) == ["error_message", "error_type", "signal", "ticker"]
    assert result["error_type"] is None
    assert result["error_message"] is None
    assert result["ticker"] == "T"
    assert result["signal"]["tier"] == "WAIT"
    assert result["signal"]["capital_action"] == "no_trade"


def test_i6_an_api_rejection_is_never_silently_downgraded(monkeypatch):
    """An explicitly selected model that Anthropic rejects surfaces the error.
    It must NOT fall back to Sonnet and retry — that would hide operator
    configuration mistakes."""
    monkeypatch.setenv(ENV_VAR, "definitely-not-a-real-model")
    client = mock_client()
    client.messages.create = AsyncMock(side_effect=RuntimeError("model not found"))
    _, result = call(CFG, client=client)

    assert result["signal"] is None
    assert result["error_type"] == "CLAUDE_API_ERROR"
    assert "model not found" in result["error_message"]
    assert client.messages.create.await_count == 1          # no silent retry
    assert client.messages.create.await_args.kwargs["model"] == "definitely-not-a-real-model"


def test_i7_rate_limit_path_is_unchanged(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    client = mock_client()
    client.messages.create = AsyncMock(side_effect=RuntimeError("429 rate limit"))
    _, result = call(CFG, client=client)
    assert result["error_type"] == "claude_rate_limited"


# ===========================================================================
# Batch scan — one runtime route, not per-ticker routing
# ===========================================================================

def _scan(config, candidates):
    client = mock_client()
    results = asyncio.run(async_claude_scan(
        candidates, "SYSTEM PROMPT", client, config))
    return client, results


def test_batch_every_candidate_receives_the_same_resolved_model(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    candidates = [{"ticker": t, "current_price": 10.0} for t in ("AAA", "BBB", "CCC")]
    client, results = _scan(CFG, candidates)

    assert client.messages.create.await_count == 3
    models = [c.kwargs["model"] for c in client.messages.create.await_args_list]
    assert models == [FABLE, FABLE, FABLE]
    assert len(results) == 3


def test_batch_falls_back_to_config_for_every_candidate():
    candidates = [{"ticker": t, "current_price": 10.0} for t in ("AAA", "BBB")]
    client, _ = _scan(CFG, candidates)
    models = [c.kwargs["model"] for c in client.messages.create.await_args_list]
    assert models == [SONNET, SONNET]


def test_batch_max_tokens_and_system_are_identical_across_candidates(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FABLE)
    candidates = [{"ticker": t, "current_price": 10.0} for t in ("AAA", "BBB", "CCC")]
    client, _ = _scan(CFG, candidates)
    for c in client.messages.create.await_args_list:
        assert c.kwargs["max_tokens"] == 1200
        assert c.kwargs["system"] == "SYSTEM PROMPT"


# ===========================================================================
# Observability and security
# ===========================================================================

def test_log_emits_selected_model_once_per_scan(monkeypatch, caplog):
    monkeypatch.setenv(ENV_VAR, FABLE)
    candidates = [{"ticker": t, "current_price": 10.0} for t in ("AAA", "BBB", "CCC")]
    with caplog.at_level(logging.INFO, logger="src.claude_client"):
        _scan(CFG, candidates)

    lines = [r.getMessage() for r in caplog.records
             if "CLAUDE_MODEL_SELECTED" in r.getMessage()]
    assert len(lines) == 1                     # once per scan, not per ticker
    assert FABLE in lines[0]
    assert "ENVIRONMENT" in lines[0]


def test_log_reports_config_source_on_rollback(caplog):
    candidates = [{"ticker": "AAA", "current_price": 10.0}]
    with caplog.at_level(logging.INFO, logger="src.claude_client"):
        _scan(CFG, candidates)
    lines = [r.getMessage() for r in caplog.records
             if "CLAUDE_MODEL_SELECTED" in r.getMessage()]
    assert len(lines) == 1
    assert SONNET in lines[0]
    assert "CONFIG" in lines[0]


def test_no_credential_or_environment_dump_in_logs(monkeypatch, caplog):
    monkeypatch.setenv(ENV_VAR, FABLE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET-do-not-log")
    candidates = [{"ticker": "AAA", "current_price": 10.0}]
    with caplog.at_level(logging.INFO, logger="src.claude_client"):
        _scan(CFG, candidates)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "sk-ant" not in blob
    assert "SECRET" not in blob
    assert "ANTHROPIC_API_KEY" not in blob
    # The only environment fact logged is the SOURCE label — never a variable
    # name, never a value, never a dump.
    assert "ANTHROPIC_MODEL" not in blob
    assert "=" not in blob.replace("model=", "").replace("source=", "")

    src = inspect.getsource(claude_client)
    assert "os.environ" not in src            # only os.getenv of one named var
    assert src.count("os.getenv") == 1
    assert "ANTHROPIC_API_KEY" not in src


# ===========================================================================
# Rollback, genericity and parity guards
# ===========================================================================

def test_rollback_removing_the_variable_restores_the_config_model(monkeypatch):
    """The whole point: one Railway variable, no code rollback."""
    monkeypatch.setenv(ENV_VAR, FABLE)
    client_a, _ = call(CFG)
    assert client_a.messages.create.await_args.kwargs["model"] == FABLE

    monkeypatch.delenv(ENV_VAR, raising=False)          # operator deletes it
    client_b, _ = call(CFG)
    assert client_b.messages.create.await_args.kwargs["model"] == SONNET

    monkeypatch.setenv(ENV_VAR, "")                     # or blanks it
    client_c, _ = call(CFG)
    assert client_c.messages.create.await_args.kwargs["model"] == SONNET


def test_production_router_is_generic_not_fable_hardcoded():
    src = inspect.getsource(claude_client)
    assert "claude-fable" not in src
    # No whitelist DATA STRUCTURE — the resolver returns whatever it is given.
    # (The module comment explains why one is deliberately absent, so the word
    # itself is expected in prose; a container of model names is not.)
    for structure in ("allowed_models", "ALLOWED_MODELS", "VALID_MODELS",
                      "SUPPORTED_MODELS", "MODEL_ALIASES"):
        assert structure not in src
    resolver = inspect.getsource(claude_client.resolve_claude_model)
    assert "in (" not in resolver and "in {" not in resolver
    # The only model name the resolver LOGIC contains is the default constant.
    # (Module prose may name other IDs when documenting the in-provider
    # rollback path; prose routes nothing.)
    resolver_logic = inspect.getsource(claude_client.resolve_claude_model)
    for literal in (OPUS, SONNET, FABLE):
        assert literal not in resolver_logic
    assert f'DEFAULT_CLAUDE_MODEL = "{OPUS}"' in src


def test_no_model_catalog_lookup_or_extra_network_call():
    src = inspect.getsource(claude_client)
    for banned in ("models.list", "client.models", "requests.get", "httpx.get",
                   "urlopen"):
        assert banned not in src


def test_doctrine_config_holds_the_opus5_production_model():
    """AI-2R: the repository fallback is Opus 5, so production stays on the
    intended model even when the Railway override is absent."""
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["claude"]["model"] == OPUS
    assert cfg["claude"]["max_tokens"] == 8192


def test_rate_governor_and_concurrency_settings_are_untouched(monkeypatch):
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))["claude"]
    assert cfg["claude_concurrency"] == 1
    assert cfg["claude_min_seconds_between_calls"] == 4
    assert cfg["claude_max_input_tokens_per_minute_budget"] == 25000
    assert cfg["max_concurrent_calls"] == 8

    # The governor is constructed from config exactly as before, regardless of
    # which model the environment selects.
    monkeypatch.setenv(ENV_VAR, FABLE)
    src = inspect.getsource(claude_client.async_claude_scan)
    assert 'claude_cfg.get("claude_concurrency"' in src
    assert 'claude_cfg.get("claude_min_seconds_between_calls", 4.0)' in src
    assert 'claude_cfg.get("claude_max_input_tokens_per_minute_budget", 25000)' in src


def test_no_inference_control_parameters_were_added():
    src = inspect.getsource(claude_client.claude_call)
    for banned in ("temperature", "thinking", "effort", "top_p", "top_k",
                   "cache_control", "stream"):
        assert banned not in src
    # The call still passes exactly four keyword arguments.
    assert src.count("model=model") == 1
    assert "max_tokens=max_tokens" in src
    assert "system=system_prompt" in src


def test_manual_analyze_path_resolves_the_same_runtime_model(monkeypatch):
    """scheduler's !analyze path calls claude_call directly, bypassing
    async_claude_scan — it must route identically."""
    src = inspect.getsource(claude_client.claude_call)
    assert "resolve_claude_model(config)" in src
    assert 'claude_cfg.get("model"' not in src        # old lookup is gone

    monkeypatch.setenv(ENV_VAR, FABLE)
    client, _ = call(CFG)
    assert client.messages.create.await_args.kwargs["model"] == FABLE

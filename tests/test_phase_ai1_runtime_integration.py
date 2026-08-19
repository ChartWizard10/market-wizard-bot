"""AI-1 production integration guards.

These tests distinguish runtime provider truth from historical compatibility
naming retained elsewhere during the migration.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml

from main import build_bot, validate_startup
from src.openai_scheduler_compat import OpenAISchedulerCompatClient


def test_main_production_runtime_does_not_instantiate_anthropic():
    src = Path("main.py").read_text()
    assert "AsyncOpenAI" in src
    assert "AsyncAnthropic" not in src
    assert "OPENAI_API_KEY" in src


def test_env_example_is_openai_gpt56():
    env = Path(".env.example").read_text()
    assert "OPENAI_API_KEY=" in env
    assert "OPENAI_MODEL=gpt-5.6" in env
    assert "ANTHROPIC_KEY=" not in env


def test_config_keeps_cap_30_separate_from_model_migration():
    cfg = yaml.safe_load(Path("config/doctrine_config.yaml").read_text())
    assert cfg["model"]["provider"] == "openai"
    assert cfg["model"]["name"] == "gpt-5.6"
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_openai_adapter_uses_responses_structured_output_and_store_false():
    cfg = yaml.safe_load(Path("config/doctrine_config.yaml").read_text())
    raw = MagicMock()
    response = MagicMock()
    response.output_text = '{"ok":true}'
    raw.responses.create = AsyncMock(return_value=response)
    client = OpenAISchedulerCompatClient(raw, cfg)

    import asyncio
    out = asyncio.run(client.messages.create(
        model="legacy-ignored",
        max_tokens=1200,
        system="SYSTEM",
        messages=[{"role": "user", "content": "INPUT"}],
    ))
    kwargs = raw.responses.create.await_args.kwargs
    assert kwargs["model"] == "gpt-5.6"
    assert kwargs["store"] is False
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert out.content[0].text == '{"ok":true}'


def test_startup_uses_openai_key_not_anthropic_key(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_KEY", "legacy-should-not-count")
    result = validate_startup({})
    assert result["ok"] is True
    assert any("OPENAI_API_KEY" in w for w in result["warnings"])


def test_build_bot_wraps_async_openai(monkeypatch):
    cfg = yaml.safe_load(Path("config/doctrine_config.yaml").read_text())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    raw_client = MagicMock()
    with patch("openai.AsyncOpenAI", return_value=raw_client):
        bot, model_client, prompt = build_bot(cfg)
    assert model_client is not None
    assert isinstance(model_client, OpenAISchedulerCompatClient)
    assert prompt
    assert bot is not None

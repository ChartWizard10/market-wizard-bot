"""AI-1 production-provider truth guard."""

from pathlib import Path


def test_production_entry_has_no_anthropic_instantiation():
    src = Path("main.py").read_text()
    assert "AsyncAnthropic" not in src
    assert "import anthropic" not in src
    assert "AsyncOpenAI" in src


def test_historical_anthropic_dependency_is_labeled_nonproduction():
    req = Path("requirements.txt").read_text()
    assert "openai" in req
    assert "Historical contract tests" in req

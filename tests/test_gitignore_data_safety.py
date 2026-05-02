"""Phase 13.5A — .gitignore data-safety contract tests.

Asserts that local runtime and backtest data files are protected from
accidental git commits by entries in .gitignore.
"""

import pathlib
import subprocess

GITIGNORE_PATH = pathlib.Path(__file__).resolve().parent.parent / ".gitignore"


def _gitignore_text() -> str:
    return GITIGNORE_PATH.read_text(encoding="utf-8")


def _check_ignored(path: str) -> bool:
    """Return True if git check-ignore reports the path is ignored."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=str(GITIGNORE_PATH.parent),
        capture_output=True,
    )
    return result.returncode == 0


def test_gitignore_protects_state_directory():
    text = _gitignore_text()
    assert ".state/" in text, ".gitignore must contain .state/ to protect runtime alert history"
    assert _check_ignored(".state/alert_history.json"), (
        "git check-ignore must confirm .state/alert_history.json is ignored"
    )


def test_gitignore_protects_alert_state_json():
    text = _gitignore_text()
    assert "data/alert_state.json" in text, (
        ".gitignore must explicitly protect data/alert_state.json"
    )
    assert _check_ignored("data/alert_state.json"), (
        "git check-ignore must confirm data/alert_state.json is ignored"
    )


def test_gitignore_protects_backtest_bars_json():
    text = _gitignore_text()
    assert "data/backtest_bars.json" in text or "data/*_bars.json" in text or "data/backtest_*.json" in text, (
        ".gitignore must protect data/backtest_bars.json (explicit or via pattern)"
    )
    assert _check_ignored("data/backtest_bars.json"), (
        "git check-ignore must confirm data/backtest_bars.json is ignored"
    )


def test_gitignore_protects_backtest_json_patterns():
    text = _gitignore_text()
    assert "data/backtest_*.json" in text or "data/*_bars.json" in text, (
        ".gitignore must contain a glob pattern covering data/backtest_*.json or data/*_bars.json"
    )
    assert _check_ignored("data/backtest_2026_bars.json"), (
        "git check-ignore must confirm pattern-matched file data/backtest_2026_bars.json is ignored"
    )
    assert _check_ignored("data/nvda_bars.json"), (
        "git check-ignore must confirm pattern-matched file data/nvda_bars.json is ignored"
    )

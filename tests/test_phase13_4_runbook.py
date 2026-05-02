"""Phase 13.4 — Runbook existence and content contract tests."""

import pathlib

RUNBOOK_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "docs" / "backtesting" / "phase13_4_first_real_backtest_runbook.md"
)


def _text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Existence
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_exists():
    assert RUNBOOK_PATH.exists(), f"Runbook not found at {RUNBOOK_PATH}"
    assert RUNBOOK_PATH.stat().st_size > 0, "Runbook file is empty"


# ---------------------------------------------------------------------------
# 2. Required sections
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_has_required_sections():
    text = _text()
    required_sections = [
        "## Purpose",
        "## Current System State",
        "## Non-Negotiable Outcome Law",
        "## Source Files",
        "## Alert History Shape",
        "## Required OHLC Bars Input",
        "## Minimum Fields For Backtestable Alert",
        "## Exact Commands",
        "## Expected Output Sections",
        "## How To Interpret INVALID_DATA",
        "## How To Interpret NO_TRIGGER",
        "## How To Interpret AMBIGUOUS_SAME_BAR",
        "## First Real Backtest Procedure",
        "## No-Analysis-Paralysis Guard",
        "## What We Are Looking For",
        "## Decision Rules After First Run",
        "## Future Improvements",
        "## Explicit Non-Changes",
        "## Final Operator Checklist",
    ]
    missing = [s for s in required_sections if s not in text]
    assert not missing, f"Runbook missing sections: {missing}"


# ---------------------------------------------------------------------------
# 3. Both paths documented
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_references_live_and_fallback_paths():
    text = _text()
    assert ".state/alert_history.json" in text, (
        "Runbook must document the live deployed path: .state/alert_history.json"
    )
    assert "data/alert_state.json" in text, (
        "Runbook must document the code fallback path: data/alert_state.json"
    )


# ---------------------------------------------------------------------------
# 4. Required real files referenced
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_references_real_files():
    text = _text()
    required_files = [
        "scripts/backtest_alert_history.py",
        "src/backtest.py",
        "config/doctrine_config.yaml",
    ]
    missing = [f for f in required_files if f not in text]
    assert not missing, f"Runbook missing file references: {missing}"


# ---------------------------------------------------------------------------
# 5. Exact runner command present
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_runner_command():
    text = _text()
    required_command = (
        "python scripts/backtest_alert_history.py "
        "--alerts .state/alert_history.json "
        "--bars data/backtest_bars.json "
        "--horizon 10"
    )
    assert required_command in text, (
        f"Runbook must contain exact command:\n  {required_command}"
    )


# ---------------------------------------------------------------------------
# 6. Outcome law: T1 before invalidation
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_outcome_law():
    text = _text()
    assert "T1 before invalidation" in text or "T1 hit before invalidation" in text, (
        "Runbook must state the outcome law: T1 before invalidation"
    )
    assert "WIN_T1_BEFORE_INVALIDATION" in text, (
        "Runbook must reference the WIN_T1_BEFORE_INVALIDATION outcome label"
    )


# ---------------------------------------------------------------------------
# 7. No target fabrication rule
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_no_target_fabrication_rule():
    text = _text()
    assert "Do not fabricate targets" in text or "do not fabricate targets" in text.lower(), (
        "Runbook must state: Do not fabricate targets"
    )
    assert "Missing targets remain missing" in text, (
        "Runbook must state: Missing targets remain missing"
    )


# ---------------------------------------------------------------------------
# 8. No-analysis-paralysis guard
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_no_analysis_paralysis_guard():
    text = _text()
    assert "No-Analysis-Paralysis" in text or "No-analysis-paralysis" in text.lower(), (
        "Runbook must contain a No-Analysis-Paralysis Guard section"
    )
    assert "No single alert or small sample should cause a new hard gate" in text, (
        "Runbook must state: No single alert or small sample should cause a new hard gate"
    )


# ---------------------------------------------------------------------------
# 9. Both bars input formats documented
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_two_bars_formats():
    text = _text()
    assert "Format A" in text or "Shape A" in text, (
        "Runbook must document bars Format A (dict keyed by ticker)"
    )
    assert "Format B" in text or "Shape B" in text, (
        "Runbook must document bars Format B (flat list with ticker field)"
    )


# ---------------------------------------------------------------------------
# 10. INVALID_DATA interpretation
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_invalid_data_interpretation():
    text = _text()
    assert "INVALID_DATA is" in text or "`INVALID_DATA` is" in text or "INVALID_DATA` is" in text, (
        "Runbook must explain INVALID_DATA"
    )
    assert "not automatically a bad alert" in text, (
        "Runbook must clarify: INVALID_DATA is not automatically a bad alert"
    )


# ---------------------------------------------------------------------------
# 11. Explicit non-changes section
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_contains_explicit_non_changes():
    text = _text()
    required_non_changes = [
        "src/tiering.py",
        "src/discord_alerts.py",
        "src/scheduler.py",
        "main.py",
    ]
    missing = [f for f in required_non_changes if f not in text]
    assert not missing, (
        f"Runbook Explicit Non-Changes section missing references to: {missing}"
    )
    assert "This runbook does not change live scanner behavior" in text or \
           "does not change live scanner behavior" in text, (
        "Runbook must state it does not change live scanner behavior"
    )


# ---------------------------------------------------------------------------
# 12. !status path as source of truth
# ---------------------------------------------------------------------------

def test_phase13_4_runbook_says_status_path_is_source_of_truth():
    text = _text()
    assert "!status" in text, (
        "Runbook must reference the !status command"
    )
    assert "source of truth" in text, (
        "Runbook must declare the !status path as source of truth"
    )
    assert (
        "Use the path reported by !status as the source of truth" in text
        or "use the path reported by !status as the source of truth" in text.lower()
    ), (
        "Runbook must contain: 'Use the path reported by !status as the source of truth'"
    )

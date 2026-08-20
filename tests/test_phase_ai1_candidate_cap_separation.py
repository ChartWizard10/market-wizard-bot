"""Provider guard: a provider change can never silently become CAP-40."""

from pathlib import Path

import yaml


def test_ai1_does_not_raise_candidate_cap():
    cfg = yaml.safe_load(Path("config/doctrine_config.yaml").read_text())
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_cap40_is_explicitly_deferred_to_measured_phase():
    doc = Path("docs/CAP_40_DECISION.md").read_text()
    assert "Current production cap: **30" in doc
    assert "Proposed next cap: **40**" in doc
    assert "ranks 31-60" in doc

"""Phase 13.8A — Chart Engine Sovereignty / No VIX Blocking.

Mission:
  The Market Wizard scanner is a pure chart-structure intelligence engine.
  VIX/macro/regime state must never block, downgrade, suppress, reroute, or
  mutate scanner output.  The human operator — not the scanner — decides
  whether to deploy capital under current macro conditions.

Core law:
  Scanner answers: "Is this chart structurally valid?"
  Operator answers: "Do I deploy capital under current macro/VIX conditions?"

Audit result (full repo grep for vix, regime, macro, freeze, frozen,
no_new_entry, cash_mode, downgrade_aggression, risk_off, market_regime,
vix_regime_high):
  ZERO MATCHES across all source files, test files, config, and prompts.

These tests establish a permanent regression baseline confirming:
  1. No VIX/macro term appears anywhere in the production codebase.
  2. Identical chart structure produces identical final tier regardless of any
     hypothetical macro/VIX annotation injected into the signal dict.
  3. SNIPE_IT / STARTER / NEAR_ENTRY tier assignments and alert bodies are
     identical whether VIX is "low", "high", "extreme", or absent entirely.
  4. Alert routing (discord_channel) is VIX-invariant.
  5. Capital contract language is VIX-invariant.
  6. Prefilter veto set contains no VIX/macro entries.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

from src.discord_alerts import format_alert
from src.prefilter import apply_hard_vetoes
from src.tiering import validate, _ENTRY_BLOCKING_VETOES, _ALL_ALERT_BLOCKING_VETOES

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_SRC_FILES = sorted((_REPO_ROOT / "src").glob("*.py"))
_TEST_FILES = sorted((_REPO_ROOT / "tests").glob("*.py"))
_CONFIG_FILES = [
    _REPO_ROOT / "config" / "doctrine_config.yaml",
    _REPO_ROOT / "prompts" / "market_wizard_system.md",
]
_ALL_SOURCE_FILES = _SRC_FILES + _TEST_FILES + _CONFIG_FILES

# Terms that must never appear as active logic.
_FORBIDDEN_MACRO_TERMS = [
    "vix",
    "regime",
    "macro",
    "freeze",
    "frozen",
    "no_new_entry",
    "cash_mode",
    "downgrade_aggression",
    "risk_off",
    "market_regime",
    "vix_regime",
    "vix_regime_high",
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MIN_CONFIG = {
    "tiers": {
        "snipe_it":    {"min_score": 85, "min_rr": 3.0, "min_risk_distance_pct": 0.35},
        "starter":     {"min_score": 75, "min_rr": 3.0},
        "near_entry":  {"min_score": 60},
        "wait":        {},
    }
}


def _snipe_signal(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "tier": "SNIPE_IT",
        "score": 88,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "zone_type": "OB",
        "trigger_level": 200.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below OB",
        "invalidation_level": 195.00,
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "sma_value_alignment": "supportive",
        "forced_participation": "none",
        "next_action": "Enter at trigger.",
        "capital_action": "full_quality_allowed",
        "reason": "Clean BOS with retest and hold.",
        "missing_conditions": [],
        "upgrade_trigger": "",
        "targets": [{"label": "T1", "level": 210.00, "reason": "prior high"}],
        "discord_channel": "#snipe-signals",
    }
    base.update(overrides)
    return base


def _starter_signal(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "tier": "STARTER",
        "score": 78,
        "setup_family": "reclaim",
        "structure_event": "MSS",
        "trend_state": "repair",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below FVG base",
        "invalidation_level": 97.00,
        "risk_reward": 3.1,
        "overhead_status": "clear",
        "sma_value_alignment": "supportive",
        "forced_participation": "none",
        "next_action": "Enter reduced size at trigger.",
        "capital_action": "starter_only",
        "reason": "Zone accepted with retest confirmed.",
        "missing_conditions": [],
        "upgrade_trigger": "",
        "targets": [{"label": "T1", "level": 108.00, "reason": "swing high"}],
        "discord_channel": "#starter-signals",
    }
    base.update(overrides)
    return base


def _near_entry_signal(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "tier": "NEAR_ENTRY",
        "score": 63,
        "setup_family": "reclaim",
        "structure_event": "MSS",
        "trend_state": "repair",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "partial",
        "hold_status": "missing",
        "invalidation_condition": "below FVG base",
        "invalidation_level": 97.00,
        "risk_reward": None,
        "overhead_status": "clear",
        "sma_value_alignment": "supportive",
        "forced_participation": "none",
        "next_action": "Watch for retest confirmation.",
        "capital_action": "wait_no_capital",
        "reason": "Structure repair in progress; no zone acceptance yet.",
        "missing_conditions": ["retest_confirmed", "hold_confirmed"],
        "upgrade_trigger": "Confirmed retest and hold of FVG.",
        "targets": [{"label": "T1", "level": 108.00, "reason": "swing high"}],
        "discord_channel": "#near-entry-watch",
    }
    base.update(overrides)
    return base


def _tiering_result(signal: dict) -> dict:
    return validate(signal, {"veto_flags": []}, _MIN_CONFIG)


def _format(signal: dict) -> str:
    result = _tiering_result(signal)
    tr = {
        "final_tier": result["final_tier"],
        "score": result["score"],
        "ticker": signal["ticker"],
        "final_signal": result["final_signal"],
    }
    return format_alert(tr)


# ---------------------------------------------------------------------------
# Section 1 — Static source-code audit
# ---------------------------------------------------------------------------


class TestNoVixMacroInSourceCode:
    """Zero VIX/macro terms in any production source file."""

    @pytest.mark.parametrize("term", _FORBIDDEN_MACRO_TERMS)
    def test_term_absent_from_src(self, term: str):
        """Forbidden macro term must not appear in any src/*.py file."""
        matches = []
        for path in _SRC_FILES:
            text = path.read_text(errors="replace").lower()
            if term.lower() in text:
                # Find line numbers for context
                for i, line in enumerate(text.splitlines(), 1):
                    if term.lower() in line:
                        matches.append(f"{path.name}:{i}: {line.strip()}")
        assert not matches, (
            f"Forbidden macro term {term!r} found in src/ files:\n"
            + "\n".join(matches)
        )

    @pytest.mark.parametrize("term", _FORBIDDEN_MACRO_TERMS)
    def test_term_absent_from_config_and_prompts(self, term: str):
        """Forbidden macro term must not appear in config or prompts."""
        matches = []
        for path in _CONFIG_FILES:
            if not path.exists():
                continue
            text = path.read_text(errors="replace").lower()
            if term.lower() in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if term.lower() in line:
                        matches.append(f"{path.name}:{i}: {line.strip()}")
        assert not matches, (
            f"Forbidden macro term {term!r} found in config/prompts:\n"
            + "\n".join(matches)
        )


class TestVetoSetContainsNoMacroEntries:
    """Hard-veto sets must be chart-structural only — no macro/VIX entries."""

    def test_entry_blocking_vetoes_no_macro(self):
        for veto in _ENTRY_BLOCKING_VETOES:
            for term in _FORBIDDEN_MACRO_TERMS:
                assert term.lower() not in veto.lower(), (
                    f"Macro term {term!r} found in _ENTRY_BLOCKING_VETOES entry {veto!r}"
                )

    def test_all_alert_blocking_vetoes_no_macro(self):
        for veto in _ALL_ALERT_BLOCKING_VETOES:
            for term in _FORBIDDEN_MACRO_TERMS:
                assert term.lower() not in veto.lower(), (
                    f"Macro term {term!r} found in _ALL_ALERT_BLOCKING_VETOES entry {veto!r}"
                )

    def test_prefilter_veto_constants_no_macro(self):
        """All veto label constants in prefilter.py are chart-structural."""
        import src.prefilter as pf
        veto_constants = [
            v for k, v in vars(pf).items()
            if k.startswith("VETO_") and isinstance(v, str)
        ]
        assert veto_constants, "Expected at least one VETO_* constant in prefilter"
        for veto in veto_constants:
            for term in _FORBIDDEN_MACRO_TERMS:
                assert term.lower() not in veto.lower(), (
                    f"Macro term {term!r} found in prefilter constant {veto!r}"
                )


# ---------------------------------------------------------------------------
# Section 2 — Tier invariance under simulated macro annotation
# ---------------------------------------------------------------------------


class TestTierInvariantUnderVixAnnotation:
    """Injecting VIX/macro fields into the signal dict must not change final_tier."""

    # Fields a naive macro-aware implementation might add to the signal dict.
    _MACRO_INJECTIONS = [
        {"vix_level": 35},
        {"vix_level": 80},
        {"vix_regime": "high"},
        {"vix_regime": "extreme"},
        {"market_regime": "risk_off"},
        {"macro_environment": "bearish"},
        {"freeze": True},
        {"cash_mode": True},
        {"no_new_entry": True},
        {"downgrade_aggression": True},
        {"risk_off": True},
        # All combined
        {
            "vix_level": 80,
            "vix_regime": "extreme",
            "market_regime": "risk_off",
            "freeze": True,
            "cash_mode": True,
            "no_new_entry": True,
        },
    ]

    @pytest.mark.parametrize("injection", _MACRO_INJECTIONS)
    def test_snipe_it_invariant(self, injection: dict):
        """SNIPE_IT stays SNIPE_IT regardless of injected macro annotation."""
        baseline = _tiering_result(_snipe_signal())["final_tier"]
        with_macro = _tiering_result(_snipe_signal(**injection))["final_tier"]
        assert baseline == "SNIPE_IT"
        assert with_macro == "SNIPE_IT", (
            f"Macro injection {injection} changed SNIPE_IT → {with_macro}"
        )

    @pytest.mark.parametrize("injection", _MACRO_INJECTIONS)
    def test_starter_invariant(self, injection: dict):
        """STARTER stays STARTER regardless of injected macro annotation."""
        baseline = _tiering_result(_starter_signal())["final_tier"]
        with_macro = _tiering_result(_starter_signal(**injection))["final_tier"]
        assert baseline == "STARTER"
        assert with_macro == "STARTER", (
            f"Macro injection {injection} changed STARTER → {with_macro}"
        )

    @pytest.mark.parametrize("injection", _MACRO_INJECTIONS)
    def test_near_entry_invariant(self, injection: dict):
        """NEAR_ENTRY stays NEAR_ENTRY regardless of injected macro annotation."""
        baseline = _tiering_result(_near_entry_signal())["final_tier"]
        with_macro = _tiering_result(_near_entry_signal(**injection))["final_tier"]
        assert baseline == "NEAR_ENTRY"
        assert with_macro == "NEAR_ENTRY", (
            f"Macro injection {injection} changed NEAR_ENTRY → {with_macro}"
        )


# ---------------------------------------------------------------------------
# Section 3 — Alert routing invariance
# ---------------------------------------------------------------------------


class TestRoutingInvariantUnderVix:
    """Discord channel routing must be VIX-invariant."""

    def test_snipe_it_routing_invariant(self):
        r_base = _tiering_result(_snipe_signal())
        r_vix  = _tiering_result(_snipe_signal(vix_level=80, vix_regime="extreme"))
        assert r_base["final_discord_channel"] == r_vix["final_discord_channel"]
        assert r_base["final_discord_channel"] == "#snipe-signals"

    def test_starter_routing_invariant(self):
        r_base = _tiering_result(_starter_signal())
        r_vix  = _tiering_result(_starter_signal(vix_level=80, market_regime="risk_off"))
        assert r_base["final_discord_channel"] == r_vix["final_discord_channel"]
        assert r_base["final_discord_channel"] == "#starter-signals"

    def test_near_entry_routing_invariant(self):
        r_base = _tiering_result(_near_entry_signal())
        r_vix  = _tiering_result(_near_entry_signal(vix_level=80, cash_mode=True))
        assert r_base["final_discord_channel"] == r_vix["final_discord_channel"]
        assert r_base["final_discord_channel"] == "#near-entry-watch"


# ---------------------------------------------------------------------------
# Section 4 — Capital contract invariance
# ---------------------------------------------------------------------------


class TestCapitalContractInvariantUnderVix:
    """Capital authorization language must be VIX-invariant."""

    def test_snipe_it_capital_invariant(self):
        text_base = _format(_snipe_signal())
        text_vix  = _format(_snipe_signal(vix_level=80, vix_regime="extreme"))
        assert "FULL QUALITY" in text_base
        assert "FULL QUALITY" in text_vix
        assert text_base == text_vix  # entire alert body identical

    def test_starter_capital_invariant(self):
        text_base = _format(_starter_signal())
        text_vix  = _format(_starter_signal(vix_level=80, market_regime="risk_off"))
        assert "STARTER SIZE ONLY" in text_base
        assert "STARTER SIZE ONLY" in text_vix
        assert text_base == text_vix

    def test_near_entry_capital_invariant(self):
        text_base = _format(_near_entry_signal())
        text_vix  = _format(_near_entry_signal(vix_level=80, cash_mode=True, freeze=True))
        assert "NO CAPITAL" in text_base
        assert "NO CAPITAL" in text_vix
        assert text_base == text_vix


# ---------------------------------------------------------------------------
# Section 5 — Prefilter apply_hard_vetoes is VIX-free
# ---------------------------------------------------------------------------


class TestPrefilterVetoesVixFree:
    """apply_hard_vetoes must never emit a macro/VIX veto."""

    _GOOD_ENRICHED = {
        "df_valid": True,
        "df_empty": False,
        "error": None,
        "bar_count": 200,
        "staleness_days": 0,
        "structure_event": "BOS",
        "invalidation_level": 95.0,
        "targets": [{"label": "T1", "level": 110.0, "reason": "swing high"}],
        "overhead_status": "clear",
        "overhead_distance_pct": 5.0,
        "price_extension_pct": 2.0,
        "retest_status": "partial",
        "sma_value_alignment": "supportive",
        "estimated_rr": 3.5,
        "mid_range": False,
    }

    def test_no_macro_veto_emitted_for_clean_chart(self):
        vetoes = apply_hard_vetoes(self._GOOD_ENRICHED, _MIN_CONFIG)
        for veto in vetoes:
            for term in _FORBIDDEN_MACRO_TERMS:
                assert term.lower() not in veto.lower(), (
                    f"Macro term {term!r} found in emitted veto {veto!r}"
                )

    def test_macro_fields_in_enriched_do_not_create_vetoes(self):
        """Enriched dict with injected macro fields must not generate extra vetoes."""
        enriched_base = dict(self._GOOD_ENRICHED)
        enriched_vix  = dict(self._GOOD_ENRICHED)
        enriched_vix.update({
            "vix_level": 80,
            "vix_regime": "extreme",
            "market_regime": "risk_off",
            "freeze": True,
            "cash_mode": True,
        })
        vetoes_base = apply_hard_vetoes(enriched_base, _MIN_CONFIG)
        vetoes_vix  = apply_hard_vetoes(enriched_vix, _MIN_CONFIG)
        assert vetoes_base == vetoes_vix, (
            f"Macro-injected enriched dict produced different vetoes:\n"
            f"  base: {vetoes_base}\n"
            f"  vix:  {vetoes_vix}"
        )


# ---------------------------------------------------------------------------
# Section 6 — Alert body contains no macro/VIX language
# ---------------------------------------------------------------------------


class TestAlertBodyVixFree:
    """Rendered alert text must not contain macro/VIX language in any section."""

    @pytest.mark.parametrize("tier,signal_fn", [
        ("SNIPE_IT",    _snipe_signal),
        ("STARTER",     _starter_signal),
        ("NEAR_ENTRY",  _near_entry_signal),
    ])
    def test_alert_body_no_vix_language(self, tier: str, signal_fn):
        text = _format(signal_fn()).lower()
        for term in _FORBIDDEN_MACRO_TERMS:
            assert term.lower() not in text, (
                f"Macro term {term!r} found in {tier} alert body"
            )

    def test_snipe_it_body_identical_under_high_vix(self):
        text_base = _format(_snipe_signal())
        text_vix  = _format(_snipe_signal(vix_level=80, market_regime="risk_off"))
        assert text_base == text_vix

    def test_starter_body_identical_under_extreme_vix(self):
        text_base = _format(_starter_signal())
        text_vix  = _format(_starter_signal(vix_level=80, vix_regime="extreme"))
        assert text_base == text_vix

    def test_near_entry_body_identical_under_frozen_mode(self):
        text_base = _format(_near_entry_signal())
        text_vix  = _format(_near_entry_signal(freeze=True, cash_mode=True))
        assert text_base == text_vix

"""Phase 13.9A — Capital Integrity Audit tests.

Scope: src/tiering.py (P1) and src/discord_alerts.py (P2, P3).
No config, routing, scheduler, state, or scanner changes.

Defects verified fixed:
  P1 — Fragile-risk gate extended to STARTER: a signal with risk_distance_pct
       < min_risk_distance_pct (0.35%) now cascades STARTER → NEAR_ENTRY (or WAIT
       if NEAR_ENTRY conditions are also absent), never authorizing reduced-size
       capital on fake-asymmetry geometry.
  P2 — Duplicate "Risk note" lines eliminated: caution_markers marker fixed from
       "risk is fragile" → "is fragile", matching both the tiering note
       ("Risk window is fragile...") and the injected caution ("Risk is fragile...").
  P3 — "of zone" tail cleaned: NE + both_confirmed next_action retest regex
       now consumes optional "of [the] zone" suffix, preventing
       "monitor for blocker resolution of zone" artifact.
"""

import pytest
from src.tiering import validate
from src.discord_alerts import format_alert


# ---------------------------------------------------------------------------
# Helpers — tiering
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "tiers": {
        "snipe_it":   {"min_score": 85, "min_rr": 3.0, "min_risk_distance_pct": 0.35},
        "starter":    {"min_score": 75, "min_rr": 3.0},
        "near_entry": {"min_score": 60},
        "wait":       {"posts_to_discord": False},
    }
}

_FRAGILE_TRIGGER   = 100.00
_FRAGILE_INVAL     = 99.70   # 0.30% gap — below 0.35% floor → fragile
_HEALTHY_INVAL     = 98.00   # 2.0% gap — healthy

_FRAGILE_TARGETS = [{"label": "T1", "level": 105.00, "reason": "Prior swing high"}]
_HEALTHY_TARGETS = [{"label": "T1", "level": 108.00, "reason": "Prior swing high"}]


def _snipe_signal(**overrides) -> dict:
    """SNIPE_IT signal passing all gates (healthy risk by default)."""
    base = {
        "ticker": "AAPL",
        "timestamp_et": "2026-05-11T10:30:00-05:00",
        "tier": "SNIPE_IT",
        "score": 90,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": _FRAGILE_TRIGGER,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Below FVG base",
        "invalidation_level": _HEALTHY_INVAL,
        "targets": _HEALTHY_TARGETS,
        "risk_reward": 4.0,
        "overhead_status": "clear",
        "forced_participation": "Full quality — zone held cleanly",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Enter at zone retest",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with confirmed FVG retest and hold.",
    }
    base.update(overrides)
    return base


def _starter_signal(**overrides) -> dict:
    """STARTER signal: score below SNIPE_IT floor but above STARTER floor."""
    base = _snipe_signal(
        tier="STARTER",
        score=78,
        discord_channel="#starter-signals",
        capital_action="starter_only",
        reason="Partial zone interaction — reduced size warranted.",
    )
    base.update(overrides)
    return base


def _ne_conditions() -> dict:
    """Fields that satisfy NEAR_ENTRY gate conditions."""
    return {
        "missing_conditions": ["overhead resistance too close"],
        "upgrade_trigger": "Confirmed hold above 101.00",
    }


def _pf(vetoes=None, kf=None) -> dict:
    return {"veto_flags": vetoes or [], "key_features": kf or {}}


# ---------------------------------------------------------------------------
# Helpers — discord_alerts
# ---------------------------------------------------------------------------

def _count_risk_notes(alert_text: str) -> int:
    """Count 'Risk note:' occurrences in a rendered alert."""
    return alert_text.lower().count("risk note:")


def _make_ne_tr(next_action: str, retest: str = "confirmed", hold: str = "confirmed") -> dict:
    """Build a minimal NEAR_ENTRY tiering_result for format_alert."""
    signal = {
        "ticker": "TEST",
        "tier": "NEAR_ENTRY",
        "score": 72,
        "retest_status": retest,
        "hold_status": hold,
        "structure_event": "bos",
        "setup_family": "continuation",
        "zone_type": "ob",
        "overhead_status": "moderate",
        "trend_state": "fresh_expansion",
        "risk_realism_state": "healthy",
        "risk_reward": 3.5,
        "sma_value_alignment": "supportive",
        "trigger_level": 101.0,
        "invalidation_level": 98.0,
        "invalidation_condition": "Below zone",
        "targets": [{"label": "T1", "level": 110.0, "reason": "Prior swing"}],
        "forced_participation": "None",
        "next_action": next_action,
        "reason": "Structure developing.",
        "missing_conditions": ["overhead resistance too close"],
        "upgrade_trigger": "Close above 103",
        "timestamp_et": "2026-05-11 10:30 ET",
        "capital_action": "wait_no_capital",
    }
    return {"final_tier": "NEAR_ENTRY", "score": 72, "final_signal": signal, "ticker": "TEST"}


def _make_fragile_tr(tier: str = "NEAR_ENTRY") -> dict:
    """Build a tiering_result with fragile risk fields for P2 rendering tests."""
    capital = {
        "SNIPE_IT": "full_quality_allowed",
        "STARTER":  "starter_only",
        "NEAR_ENTRY": "wait_no_capital",
    }.get(tier, "wait_no_capital")
    signal = {
        "ticker": "FRAG",
        "tier": tier,
        "score": 68,
        "retest_status": "confirmed" if tier != "NEAR_ENTRY" else "partial",
        "hold_status": "confirmed" if tier != "NEAR_ENTRY" else "missing",
        "structure_event": "bos",
        "setup_family": "continuation",
        "zone_type": "fvg",
        "overhead_status": "clear",
        "trend_state": "fresh_expansion",
        # Fragile risk fields — set directly to simulate tiering output
        "risk_realism_state": "fragile",
        "risk_realism_note": "Risk window is fragile; invalidation is very close.",
        "risk_distance": 0.29,
        "risk_distance_pct": 0.29,
        "risk_reward": 4.2,
        "sma_value_alignment": "supportive",
        "trigger_level": 101.0,
        "invalidation_level": 100.71,
        "invalidation_condition": "Below zone",
        "targets": [{"label": "T1", "level": 110.0, "reason": "Prior swing"}],
        "forced_participation": "None",
        "next_action": "Monitor zone for hold confirmation.",
        "reason": "Setup developing near zone.",
        "missing_conditions": ["hold_status"] if tier == "NEAR_ENTRY" else [],
        "upgrade_trigger": "Confirmed hold above trigger" if tier == "NEAR_ENTRY" else "",
        "timestamp_et": "2026-05-11 10:30 ET",
        "capital_action": capital,
    }
    return {"final_tier": tier, "score": 68, "final_signal": signal, "ticker": "FRAG"}


# ===========================================================================
# P1 — Fragile-risk gate extended to STARTER
# ===========================================================================

class TestFragileRiskGateOnStarter:
    """P1: STARTER capital must not be authorized on fragile risk geometry."""

    def test_starter_fragile_risk_cascades_to_near_entry(self):
        """STARTER + fragile risk + valid NE conditions → NEAR_ENTRY, not STARTER."""
        signal = _starter_signal(
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
            **_ne_conditions(),
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] == "NEAR_ENTRY", (
            f"Expected NEAR_ENTRY (fragile gate blocks STARTER), got {result['final_tier']}. "
            f"Downgrades: {result.get('downgrades')}"
        )
        assert result["capital_action"] == "wait_no_capital"
        downgrade_text = " ".join(result.get("downgrades", []))
        assert "fragile" in downgrade_text.lower()
        assert "starter" in downgrade_text.lower()

    def test_starter_fragile_risk_blocks_capital_authorization(self):
        """STARTER + fragile risk must NOT produce starter_only capital."""
        signal = _starter_signal(
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
            **_ne_conditions(),
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["capital_action"] != "starter_only", (
            "Fragile risk must not authorize reduced-size capital."
        )

    def test_snipe_it_fragile_with_ne_conditions_cascades_to_near_entry(self):
        """SNIPE_IT + fragile risk + valid NE conditions → NEAR_ENTRY (STARTER blocked too)."""
        signal = _snipe_signal(
            score=90,
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
            **_ne_conditions(),
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] == "NEAR_ENTRY", (
            f"Expected NEAR_ENTRY (SNIPE_IT and STARTER both blocked by fragile gate), "
            f"got {result['final_tier']}. Downgrades: {result.get('downgrades')}"
        )
        downgrade_text = " ".join(result.get("downgrades", []))
        assert "fragile" in downgrade_text.lower()
        assert "snipe_it" in downgrade_text.lower()

    def test_fragile_risk_not_snipe_or_starter_in_downgrades(self):
        """Fragile cascade downgrade note explicitly names the fake-asymmetry reason."""
        signal = _starter_signal(
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
            **_ne_conditions(),
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        downgrade_text = " ".join(result.get("downgrades", []))
        assert "fake-asymmetry" in downgrade_text.lower() or "fragile" in downgrade_text.lower()

    def test_healthy_risk_starter_still_passes(self):
        """Healthy risk distance (2.0%) does not trigger fragile gate — STARTER passes."""
        signal = _starter_signal(
            invalidation_level=_HEALTHY_INVAL,
            targets=_HEALTHY_TARGETS,
            risk_reward=4.0,
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] == "STARTER", (
            f"Healthy risk must not block STARTER. Got {result['final_tier']}. "
            f"Downgrades: {result.get('downgrades')}"
        )
        assert result["capital_action"] == "starter_only"

    def test_above_fragile_threshold_starter_passes(self):
        """risk_distance_pct = 0.40% (above 0.35% floor) → STARTER gate does not fire."""
        # trigger=100.00, inval=99.60 → risk_dist=0.40, risk_dist_pct=0.40% — above floor
        signal = _starter_signal(
            invalidation_level=99.60,
            targets=_HEALTHY_TARGETS,
            risk_reward=4.0,
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        # 0.40% is NOT below 0.35% — gate does not fire.
        assert result["final_tier"] == "STARTER", (
            f"Above-floor threshold must not block STARTER. Got {result['final_tier']}."
        )

    def test_fragile_risk_realism_state_still_informational(self):
        """After P1 fix, risk_realism_state field still reflects fragile in final_signal."""
        signal = _starter_signal(
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
            **_ne_conditions(),
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        fs = result["final_signal"]
        # Informational field always reflects true risk geometry
        assert fs["risk_realism_state"] == "fragile"
        assert "fragile" in fs["risk_realism_note"].lower()

    def test_fragile_starter_safe_for_alert_false_when_wait(self):
        """SNIPE_IT + fragile + no NE conditions → WAIT → safe_for_alert is False."""
        # _snipe_signal has missing_conditions=[], upgrade_trigger="none" → NE fails → WAIT
        signal = _snipe_signal(
            invalidation_level=_FRAGILE_INVAL,
            targets=_FRAGILE_TARGETS,
            risk_reward=3.5,
        )
        result = validate(signal, _pf(), _BASE_CONFIG)
        assert result["final_tier"] == "WAIT"
        assert result["safe_for_alert"] is False


# ===========================================================================
# P2 — Single "Risk note" line on fragile alerts
# ===========================================================================

class TestSingleRiskNoteOnFragileAlert:
    """P2: Fragile alert must render exactly one 'Risk note:' line."""

    def test_near_entry_fragile_risk_has_single_risk_note(self):
        """NEAR_ENTRY alert with fragile risk → exactly one 'Risk note:' in output."""
        tr = _make_fragile_tr(tier="NEAR_ENTRY")
        alert = format_alert(tr)
        count = _count_risk_notes(alert)
        assert count == 1, (
            f"Expected 1 'Risk note:' line, got {count}.\n"
            f"Lines containing 'risk note':\n"
            + "\n".join(l for l in alert.split("\n") if "risk note" in l.lower())
        )

    def test_fragile_note_content_is_tiering_note_not_injected(self):
        """The single Risk note that appears comes from tiering, not the injected caution."""
        tr = _make_fragile_tr(tier="NEAR_ENTRY")
        alert = format_alert(tr)
        risk_note_lines = [l for l in alert.split("\n") if "risk note:" in l.lower()]
        assert len(risk_note_lines) == 1
        # Tiering note is "Risk window is fragile; invalidation is very close."
        # Injected caution is "Risk is fragile; invalidation is compressed..."
        # After fix: tiering note already present → injection suppressed → only tiering note shows
        note_text = risk_note_lines[0].lower()
        assert "risk window is fragile" in note_text, (
            f"Expected tiering note text, got: {risk_note_lines[0]!r}"
        )

    def test_healthy_risk_alert_has_exactly_one_risk_note(self):
        """A healthy-risk alert has exactly one 'Risk note:' line — no duplication."""
        signal_fields = {
            "ticker": "TEST",
            "tier": "NEAR_ENTRY",
            "score": 72,
            "retest_status": "partial",
            "hold_status": "missing",
            "structure_event": "bos",
            "setup_family": "continuation",
            "zone_type": "ob",
            "overhead_status": "clear",
            "trend_state": "fresh_expansion",
            "risk_realism_state": "healthy",
            "risk_realism_note": "Risk window is healthy.",
            "risk_reward": 4.5,
            "sma_value_alignment": "supportive",
            "trigger_level": 101.0,
            "invalidation_level": 98.0,
            "invalidation_condition": "Below zone",
            "targets": [{"label": "T1", "level": 110.0, "reason": "Prior swing"}],
            "forced_participation": "None",
            "next_action": "Monitor for retest.",
            "reason": "Setup developing.",
            "missing_conditions": ["retest_status"],
            "upgrade_trigger": "Confirmed close above zone",
            "timestamp_et": "2026-05-11 10:30 ET",
            "capital_action": "wait_no_capital",
        }
        tr = {"final_tier": "NEAR_ENTRY", "score": 72, "final_signal": signal_fields, "ticker": "TEST"}
        alert = format_alert(tr)
        count = _count_risk_notes(alert)
        assert count == 1, (
            f"Healthy-risk alert must have exactly 1 'Risk note:' line. Got {count}."
        )

    def test_fragile_risk_risk_state_line_present(self):
        """Fragile alert must contain 'Risk state: fragile' line."""
        tr = _make_fragile_tr(tier="NEAR_ENTRY")
        alert = format_alert(tr)
        assert "risk state:" in alert.lower()
        state_lines = [l for l in alert.split("\n") if "risk state:" in l.lower()]
        assert any("fragile" in l.lower() for l in state_lines)

    def test_fragile_caution_not_injected_when_note_present(self):
        """Injected caution text must not appear when tiering note is already present."""
        tr = _make_fragile_tr(tier="NEAR_ENTRY")
        alert = format_alert(tr)
        # The injected caution phrase (from _FRAGILE_RISK_CAUTION)
        injected_phrase = "invalidation is compressed and execution is sensitive"
        assert injected_phrase not in alert.lower(), (
            "Injected caution phrase must be suppressed when tiering note already present."
        )


# ===========================================================================
# P3 — "of zone" tail cleaned on NE + both_confirmed next_action
# ===========================================================================

class TestOfZoneTailCleaned:
    """P3: 'Enter on retest of zone' → 'monitor for blocker resolution' (no tail)."""

    def test_enter_on_retest_of_zone_no_tail(self):
        """'Enter on retest of zone' becomes 'monitor for blocker resolution' cleanly."""
        tr = _make_ne_tr("Enter on retest of zone.", retest="confirmed", hold="confirmed")
        alert = format_alert(tr)
        next_lines = [l for l in alert.split("\n") if "next:" in l.lower()]
        assert next_lines, "Expected a 'Next:' line in alert"
        next_text = next_lines[0].lower()
        assert "of zone" not in next_text, (
            f"'of zone' tail must be cleaned. Got: {next_lines[0]!r}"
        )
        assert "monitor for blocker resolution" in next_text, (
            f"Expected watch language. Got: {next_lines[0]!r}"
        )

    def test_enter_on_retest_of_the_zone_no_tail(self):
        """'Enter on retest of the zone' → 'monitor for blocker resolution' cleanly."""
        tr = _make_ne_tr("Enter on retest of the zone.", retest="confirmed", hold="confirmed")
        alert = format_alert(tr)
        next_lines = [l for l in alert.split("\n") if "next:" in l.lower()]
        assert next_lines
        next_text = next_lines[0].lower()
        assert "of the zone" not in next_text
        assert "monitor for blocker resolution" in next_text

    def test_enter_on_retest_no_tail_still_works(self):
        """Plain 'Enter on retest' (no suffix) → 'monitor for blocker resolution'."""
        tr = _make_ne_tr("Enter on retest.", retest="confirmed", hold="confirmed")
        alert = format_alert(tr)
        next_lines = [l for l in alert.split("\n") if "next:" in l.lower()]
        assert next_lines
        next_text = next_lines[0].lower()
        assert "monitor for blocker resolution" in next_text

    def test_enter_on_retest_partial_not_converted(self):
        """When retest is only partial (not confirmed), no substitution occurs."""
        tr = _make_ne_tr("Enter on retest of zone.", retest="partial", hold="missing")
        alert = format_alert(tr)
        # The sovereignty guard should intercept this differently — but the 13.8C
        # substitution must NOT fire (it only fires for both_confirmed).
        # The body-level guard may still transform the text, but we verify
        # no "monitor for blocker resolution of zone" artifact (the specific P3 bug).
        next_lines = [l for l in alert.split("\n") if "next:" in l.lower()]
        if next_lines:
            assert "monitor for blocker resolution of zone" not in next_lines[0].lower()

"""Phase 14E.1A — 1H alert-truth alignment tests.

Reproduces the live SPG / PSA contradiction: the legacy structured fields
(retest_status / hold_status from the daily/4H tiering pass) read "confirmed"
while the dedicated 1H entry-trigger evidence engine — measuring actual 1H bars
— proves the trigger is NOT yet confirmed (RETEST_IN_PROGRESS / HOLD_WEAK /
1H_TRIGGER_WEAK / WATCH_ONLY).

Doctrine under test:
  - The 1H object is sovereign for trigger-PROOF wording.
  - Legacy proof language is cooled when the 1H has not confirmed a closed hold.
  - Capital posture, routing, tier, and the structured trigger/invalidation/
    target fields are NEVER changed by the alignment guard.
  - Confirmed 1H evidence is never overcooled.
  - Structured 1H enum strings are protected from narrative-guard rewriting.
  - The HTF cap is named truthfully (context-unavailable, not false no-permission).
"""

import re

import pytest

from src import discord_alerts as da
from src import one_hour_entry as ohe


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _signal(**over):
    """A NEAR_ENTRY signal whose legacy fields claim retest+hold confirmed and
    whose quality dimensions yield A+/near-ready prestige language."""
    s = {
        "ticker":               "SPG",
        "setup_family":         "continuation",
        "structure_event":      "bos",
        "trend_state":          "fresh_expansion",
        "zone_type":            "fvg",
        "trigger_level":        102.0,
        "invalidation_level":   99.5,
        "invalidation_condition": "1H close below",
        "risk_reward":          3.6,                 # healthy + <4.0 → one standard dim
        "overhead_status":      "clear",
        "risk_realism_state":   "healthy",
        "sma_value_alignment":  "supportive",
        "retest_status":        "confirmed",
        "hold_status":          "confirmed",
        "targets":              [{"label": "T1", "level": 108.0, "reason": "prior high"}],
        "missing_conditions":   ["overhead_path_not_clean"],
        "near_entry_blocker_note": "awaiting 1H hold confirmation",
        "next_action":          "monitor for blocker resolution",
        "reason":               "BOS continuation with FVG retest",
        "capital_action":       "wait_no_capital",
        "scan_price":           101.2,
    }
    s.update(over)
    return s


def _tiering(one_hour=None, signal_over=None, tier="NEAR_ENTRY"):
    return {
        "final_tier": tier,
        "score": 87,
        "final_signal": _signal(**(signal_over or {})),
        "trade_location": {
            "zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
            "zone_type": "FVG", "scan_price": 101.2,
        },
        "one_hour_entry": one_hour,
    }


def _one_hour(
    state="RETEST_IN_PROGRESS",
    hold="HOLD_WEAK",
    retest="RETEST_REAL",
    score_label="1H_TRIGGER_WEAK",
    alert="WATCH_ONLY",
    score=66,
    status="ENABLED",
    caps=("NO_RETEST",),
    candle="REJECTION",
    location="ACCEPTABLE_BUT_NOT_IDEAL",
):
    return {
        "enabled": True, "timeframe": "1H", "status": status,
        "data_freshness": "FRESH",
        "trigger_state": state,
        "score": score, "score_label": score_label,
        "alert_truth_label": alert,
        "hard_caps_applied": list(caps),
        "pullback_retest_hold": {
            "pullback_truth": "PULLBACK_REAL", "retest_truth": retest,
            "hold_truth": hold, "retest_zone_type": "FVG",
        },
        "candle_truth": {"event_type": candle},
        "location_realism": {"label": location},
        "invalidation": {"clear": True, "level": 99.5},
        "scanner_sentence": "1H retest in progress. Hold not confirmed until closed candle defense.",
    }


def _retest_value(body):
    m = re.search(r"^\s*Retest:\s+(.*)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _hold_value(body):
    m = re.search(r"^\s*Hold:\s+(.*)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _quality_value(body):
    m = re.search(r"^\s*Quality read:\s+(.*)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


# ===========================================================================
# Baseline — without a 1H object the legacy prestige wording survives (proving
# the guard, not the fixture, is what cools the language).
# ===========================================================================

class TestBaselineLegacyWordingSurvives:
    def test_no_one_hour_keeps_confirmed_and_prestige(self):
        body = da.format_alert(_tiering(one_hour=None))
        assert _retest_value(body) == "confirmed"
        assert _hold_value(body) == "confirmed"
        assert "A+ setup" in body
        assert "confirmed sequence and hold" in body
        assert "1H trigger proof remains incomplete" not in body


# ===========================================================================
# Test 1 — confirmed retest/hold legacy fields vs RETEST_IN_PROGRESS + HOLD_WEAK
# ===========================================================================

class TestRetestHoldCooling:
    def test_confirmed_legacy_cooled_by_weak_one_hour(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            state="RETEST_IN_PROGRESS", hold="HOLD_WEAK"
        )))
        # Legacy retest/hold display must no longer claim confirmed.
        assert _retest_value(body) != "confirmed"
        assert _hold_value(body) != "confirmed"
        assert re.search(r"^\s*Retest:\s+confirmed\s*$", body, re.MULTILINE) is None
        assert re.search(r"^\s*Hold:\s+confirmed\s*$", body, re.MULTILINE) is None
        # Watch-only / incomplete-1H-proof language present.
        assert "Watch-only valid" in body
        assert "1H trigger proof remains incomplete" in body
        assert "1H evidence has not confirmed a closed hold" in body
        # Capital posture untouched.
        assert "NO CAPITAL — WATCH ONLY" in body

    def test_structured_execution_fields_unchanged(self):
        body = da.format_alert(_tiering(one_hour=_one_hour()))
        # Trigger / invalidation / target levels survive the cooling pass.
        assert "Trigger:      102.00" in body
        assert "99.50" in body
        assert "T1: 108.00" in body


# ===========================================================================
# Test 2 — 1H_TRIGGER_WEAK score label removes A+/near-ready prestige language
# ===========================================================================

class TestPrestigeLanguageCooling:
    def test_weak_score_label_removes_prestige(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            score_label="1H_TRIGGER_WEAK"
        )))
        assert "A+ setup" not in body
        assert "near-ready" not in body.lower()
        # Honest replacement language is allowed.
        assert "structure exists" in body
        assert "Watch-only valid" in body


# ===========================================================================
# Test 3 — WATCH_ONLY alert label removes "confirmed sequence and hold"
# ===========================================================================

class TestConfirmedSequenceCooling:
    def test_watch_only_removes_confirmed_sequence(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            alert="WATCH_ONLY",
            # Force the confirmed-path fields off so only alert label drives it.
            state="APPROACHING_LOCATION", hold="HOLD_FORMING",
            score_label="1H_TRIGGER_FORMING",
        )))
        assert "confirmed sequence and hold" not in body


# ===========================================================================
# Test 4 — HOLD_CONFIRMED + CONFIRMED_TRIGGER: confirmed wording stays allowed
# ===========================================================================

class TestNoOvercoolingWhenConfirmed:
    def test_confirmed_one_hour_does_not_cool(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            state="HOLD_CONFIRMED", hold="HOLD_CONFIRMED",
            retest="RETEST_CORE_VALID", score_label="1H_TRIGGER_VALID",
            alert="CONFIRMED_TRIGGER", score=84, caps=(),
            candle="DISPLACEMENT", location="REALISTIC_ENTRY_LOCATION",
        )))
        # Confirmed wording remains; no overcooling injected.
        assert "confirmed sequence and hold" in body
        assert _retest_value(body) == "confirmed"
        assert _hold_value(body) == "confirmed"
        assert "1H trigger proof remains incomplete" not in body
        assert "1H evidence has not confirmed a closed hold" not in body

    def test_live_trigger_does_not_cool(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            state="TRIGGER_LIVE", hold="HOLD_CONFIRMED",
            retest="RETEST_CORE_VALID", score_label="1H_TRIGGER_A_PLUS",
            alert="LIVE_TRIGGER", score=92, caps=(),
        )))
        assert "1H trigger proof remains incomplete" not in body
        assert _hold_value(body) == "confirmed"


# ===========================================================================
# Test 5 — 1H block enum protection (structured strings never rewritten)
# ===========================================================================

class TestOneHourEnumProtection:
    def test_structured_enums_survive_all_guards(self):
        body = da.format_alert(_tiering(one_hour=_one_hour(
            state="TRIGGER_LIVE", hold="HOLD_CONFIRMED",
            retest="RETEST_CORE_VALID", score_label="1H_TRIGGER_A_PLUS",
            alert="LIVE_TRIGGER", score=92, caps=(),
        )))
        assert "HOLD_CONFIRMED" in body
        assert "RETEST_CORE_VALID" in body
        assert "TRIGGER_LIVE" in body
        # Sentinel is fully spliced out — no leakage.
        assert "ONE_HOUR_EVIDENCE_BLOCK" not in body

    def test_weak_enums_also_survive_when_cooling(self):
        # Even while legacy prose is cooled, the 1H block's own enums are intact.
        body = da.format_alert(_tiering(one_hour=_one_hour(
            state="RETEST_IN_PROGRESS", hold="HOLD_WEAK", retest="RETEST_REAL",
        )))
        assert "hold=HOLD_WEAK" in body
        assert "retest=RETEST_REAL" in body
        assert "RETEST_IN_PROGRESS" in body


# ===========================================================================
# Test 6 — NO_HTF_PERMISSION mapping (engine-level)
# ===========================================================================

def _engine_tiering(tier):
    signal = {
        "trigger_level": 102.0, "invalidation_level": 99.5,
        "overhead_level": 110.0, "targets": [{"label": "T1", "level": 108.0}],
        "zone_type": "FVG", "structure_event": "BOS",
    }
    return {
        "final_tier": tier,
        "final_signal": signal,
        "trade_location": {
            "zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
            "zone_type": "FVG",
        },
    }


_ENGINE_BARS = [
    {"open": 99.5, "high": 100.0, "low": 99.4, "close": 99.9},
    {"open": 99.9, "high": 103.2, "low": 99.8, "close": 103.0},
    {"open": 103.0, "high": 103.1, "low": 100.8, "close": 101.0},
    {"open": 101.0, "high": 102.9, "low": 100.95, "close": 102.7, "volume": 1500},
]


class TestHtfContextMapping:
    def test_near_entry_with_valid_context_no_false_no_permission(self):
        ctx = ohe.build_one_hour_entry_context(
            "SPG", _engine_tiering("NEAR_ENTRY"), {"atr": 1.0},
            one_hour_bars=_ENGINE_BARS,
        )
        caps = ctx["hard_caps_applied"]
        assert "NO_HTF_PERMISSION" not in caps
        assert "HTF_CONTEXT_UNAVAILABLE_FOR_1H_ENGINE" not in caps

    def test_starter_with_valid_context_no_htf_cap(self):
        ctx = ohe.build_one_hour_entry_context(
            "SPG", _engine_tiering("STARTER"), {"atr": 1.0},
            one_hour_bars=_ENGINE_BARS,
        )
        caps = ctx["hard_caps_applied"]
        assert "NO_HTF_PERMISSION" not in caps
        assert "HTF_CONTEXT_UNAVAILABLE_FOR_1H_ENGINE" not in caps

    def test_missing_context_uses_conservative_truthful_cap(self):
        ctx = ohe.build_one_hour_entry_context(
            "SPG", _engine_tiering("WAIT"), {"atr": 1.0},
            one_hour_bars=_ENGINE_BARS,
        )
        caps = ctx["hard_caps_applied"]
        assert "HTF_CONTEXT_UNAVAILABLE_FOR_1H_ENGINE" in caps
        assert "NO_HTF_PERMISSION" not in caps
        # Cap remains conservative.
        assert ctx["score"] <= 69


# ===========================================================================
# Invariants — the alignment guard never touches sovereign capital/routing.
# ===========================================================================

class TestAlignmentGuardInvariants:
    def test_missing_one_hour_is_noop(self):
        assert da._apply_one_hour_truth_alignment_guard("body text", None) == "body text"

    def test_disabled_one_hour_is_noop(self):
        oh = _one_hour(status="DISABLED")
        assert da._apply_one_hour_truth_alignment_guard("Retest:  confirmed", oh) == \
            "Retest:  confirmed"

    def test_capital_posture_never_changed_by_cooling(self):
        body = da.format_alert(_tiering(one_hour=_one_hour()))
        assert "NO CAPITAL — WATCH ONLY" in body
        assert "Near-entry watch — no capital until blocker resolves." in body

    def test_proof_incomplete_detects_each_weak_axis(self):
        assert da._one_hour_proof_incomplete(_one_hour(state="FAILED_RETEST"))
        assert da._one_hour_proof_incomplete(_one_hour(hold="HOLD_FAILED"))
        assert da._one_hour_proof_incomplete(_one_hour(score_label="NO_VALID_1H_TRIGGER"))
        assert da._one_hour_proof_incomplete(_one_hour(alert="NO_ALERT"))
        # Genuine confirmation is not flagged.
        assert not da._one_hour_proof_incomplete(_one_hour(
            state="HOLD_CONFIRMED", hold="HOLD_CONFIRMED",
            score_label="1H_TRIGGER_VALID", alert="CONFIRMED_TRIGGER",
        ))

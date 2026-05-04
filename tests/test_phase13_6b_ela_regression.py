"""Phase 13.6B — ELA-style final rendered alert sanitizer regression tests.

Live post-deploy bug (ELA, #near-entry):
  - Final tier: NEAR_ENTRY
  - Retest: confirmed, Hold: partial
  - Blocker note correctly said "hold is not fully confirmed"
  - But ACTION/Why text still said:
      * "degrading this from SNIPE_IT to STARTER"
      * "Watchlist only until retest and hold confirm."

Root causes fixed in Phase 13.6B:
  1. "degrading this from SNIPE_IT to STARTER" was not in _TIER_BANNED_PHRASES
     or _GUARD_RULES for NEAR_ENTRY.
  2. "Watchlist only until retest and hold confirm." was an old replacement text
     that Claude learned to output literally; it was not a banned INPUT phrase.
  3. _build_near_entry_blocker_note() fallback said "watchlist only until..."
     — rewritten to "watch for trigger acceptance and full zone confirmation."
  4. "manage position X" replacement appended trailing fragments (" to OB low...")
     — a cleanup pattern now strips the dangling continuation.
"""

import pytest
from src.discord_alerts import format_alert
from src.tiering import _sanitize_reason_for_tier, _build_near_entry_blocker_note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tr(tier: str, **signal_overrides) -> dict:
    """Build a minimal tiering_result for format_alert()."""
    capital_map = {
        "SNIPE_IT":   "full_quality_allowed",
        "STARTER":    "starter_only",
        "NEAR_ENTRY": "wait_no_capital",
        "WAIT":       "no_trade",
    }
    channel_map = {
        "SNIPE_IT":   "#snipe-signals",
        "STARTER":    "#starter-signals",
        "NEAR_ENTRY": "#near-entry-watch",
        "WAIT":       "none",
    }
    signal = {
        "ticker": "ELA",
        "tier": tier,
        "score": 72,
        "setup_family": "continuation",
        "structure_event": "BOS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "OB",
        "trigger_level": 55.00,
        "retest_status": "confirmed",
        "hold_status": "partial",
        "invalidation_condition": "Below OB low",
        "invalidation_level": 52.00,
        "targets": [{"label": "T1", "level": 65.00, "reason": "Prior swing high"}],
        "risk_reward": 3.3,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": ["hold_partial"],
        "upgrade_trigger": "Confirmed body close above zone.",
        "next_action": "Watch for acceptance.",
        "discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "reason": "Clean BOS with OB retest confirmed.",
        "sanitized_reason": None,
        "sanitized_next_action": None,
        "scan_price": 55.00,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 5.0,
        "risk_distance": 3.00,
        "risk_distance_pct": 5.45,
        "current_price_to_invalidation": 3.00,
        "current_price_to_invalidation_pct": 5.45,
        "risk_realism_state": "healthy",
        "risk_realism_note": None,
        "near_entry_blocker_note": None,
    }
    signal.update(signal_overrides)
    return {
        "ok": True,
        "final_tier": tier,
        "score": signal["score"],
        "safe_for_alert": True,
        "final_discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "final_signal": signal,
    }


# ---------------------------------------------------------------------------
# Test 1 — ELA live bug: NEAR_ENTRY reason contains tier-degradation language
# ---------------------------------------------------------------------------

def test_ela_degrading_from_snipe_to_starter_stripped():
    """ELA: NEAR_ENTRY reason said 'degrading this from SNIPE_IT to STARTER'.

    The guard must strip it. The rendered alert must:
      - say NO CAPITAL / WATCH ONLY
      - NOT say 'degrading this from SNIPE_IT to STARTER'
      - NOT say 'from SNIPE_IT to STARTER' (substring)
      - NOT say FULL QUALITY
      - include hold blocker
    """
    tr = _tr(
        "NEAR_ENTRY",
        reason=(
            "BOS confirmed with OB retest. Hold partial — degrading this from "
            "SNIPE_IT to STARTER while hold remains unconfirmed."
        ),
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: hold is not fully confirmed; wait for body-close acceptance"
            " inside/above the zone."
        ),
    )
    text = format_alert(tr)

    # Must carry NEAR_ENTRY badge
    assert "🟢 NEAR ENTRY" in text

    # Must say no-capital language
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    # Must name the hold blocker
    assert "hold" in text.lower()

    # Must NOT say tier-degradation language
    assert "degrading this from snipe_it to starter" not in text.lower()
    assert "from snipe_it to starter" not in text.lower()
    assert "from SNIPE_IT to STARTER" not in text

    # Must NOT say FULL QUALITY
    assert "FULL QUALITY" not in text

    # Must NOT say All SNIPE_IT conditions met
    assert "all snipe_it conditions met" not in text.lower()


# ---------------------------------------------------------------------------
# Test 2 — ELA live bug: next_action contains the old replacement phrase
# ---------------------------------------------------------------------------

def test_ela_watchlist_only_until_retest_and_hold_stripped():
    """ELA: Claude's next_action literally said 'Watchlist only until retest and hold confirm.'

    This was the old tiering.py replacement text; Claude learned to output it.
    The guard must strip it. When retest is confirmed and only hold is partial,
    the alert must NOT say 'retest and hold confirm' (implies both unconfirmed).
    """
    tr = _tr(
        "NEAR_ENTRY",
        reason="BOS confirmed with OB retest.",
        sanitized_reason=None,
        next_action="Watchlist only until retest and hold confirm.",
        sanitized_next_action=None,
        near_entry_blocker_note=(
            "Blocker: hold is not fully confirmed; wait for body-close acceptance"
            " inside/above the zone."
        ),
    )
    text = format_alert(tr)

    # Must say no-capital language
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    # Must NOT say the old watchlist phrase
    assert "watchlist only until retest and hold confirm" not in text.lower()

    # Must NOT imply both retest and hold are unconfirmed (retest IS confirmed)
    assert "watchlist only until" not in text.lower()


# ---------------------------------------------------------------------------
# Test 3 — ELA combined: both phrases in reason + next_action simultaneously
# ---------------------------------------------------------------------------

def test_ela_combined_both_contradictions_stripped():
    """ELA combined case: both contradictions present simultaneously.

    This matches the exact live bug observed: reason AND next_action both
    contained wrong-tier language.
    """
    tr = _tr(
        "NEAR_ENTRY",
        reason=(
            "BOS confirmed with OB retest. Hold partial — degrading this from "
            "SNIPE_IT to STARTER while hold remains unconfirmed. "
            "Watchlist only until retest and hold confirm."
        ),
        sanitized_reason=None,
        next_action="Watchlist only until retest and hold confirm.",
        sanitized_next_action=None,
        near_entry_blocker_note=(
            "Blocker: hold is not fully confirmed; wait for body-close acceptance"
            " inside/above the zone."
        ),
    )
    text = format_alert(tr)

    # All four required properties
    assert "🟢 NEAR ENTRY" in text
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()
    assert "hold" in text.lower()

    # All five forbidden phrases
    assert "degrading this from snipe_it to starter" not in text.lower()
    assert "from snipe_it to starter" not in text.lower()
    assert "watchlist only until retest and hold confirm" not in text.lower()
    assert "watchlist only until" not in text.lower()
    assert "FULL QUALITY" not in text
    assert "all snipe_it conditions met" not in text.lower()


# ---------------------------------------------------------------------------
# Test 4 — "snipe_it to starter" short-form variants
# ---------------------------------------------------------------------------

def test_near_entry_snipe_to_starter_short_form_stripped():
    """Various shorter degradation-language variants must all be stripped."""
    phrases = [
        "downgraded from snipe_it to starter",
        "snipe_it downgrade to starter",
        "from snipe_it to starter",
        "downgraded to starter",
        "downgrade to starter",
        "snipe_it to starter",
    ]
    for phrase in phrases:
        clean = _sanitize_reason_for_tier(
            f"Zone quality high — {phrase} given hold partial.", "NEAR_ENTRY"
        )
        assert phrase.lower() not in clean.lower(), (
            f"Expected phrase {phrase!r} to be stripped but found in: {clean!r}"
        )
        # Replaced text should carry watch-only language
        assert "watch-only" in clean.lower() or "no capital" in clean.lower(), (
            f"Expected watch-only/no capital after stripping {phrase!r}, got: {clean!r}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Sanitizer: "watchlist only until" catch-all
# ---------------------------------------------------------------------------

def test_near_entry_watchlist_only_until_catch_all():
    """Any 'Watchlist only until X' variant in reason/next_action is sanitized."""
    variants = [
        "Watchlist only until retest and hold confirm.",
        "Watchlist only until the zone confirms.",
        "Watchlist only until trigger is reclaimed.",
        "Watchlist only until acceptance above OB.",
    ]
    for variant in variants:
        clean = _sanitize_reason_for_tier(variant, "NEAR_ENTRY")
        assert "watchlist only until" not in clean.lower(), (
            f"Expected 'watchlist only until' stripped from {variant!r}, got: {clean!r}"
        )


# ---------------------------------------------------------------------------
# Test 6 — manage position trailing fragment cleanup
# ---------------------------------------------------------------------------

def test_near_entry_manage_position_trailing_fragment_stripped():
    """'Manage position to OB low.' → 'No position management until capital is authorized.'

    The remainder (' to OB low.') must NOT appear in the sanitized output.
    """
    dirty = "Manage position to OB low at 52.00."
    clean = _sanitize_reason_for_tier(dirty, "NEAR_ENTRY")
    assert "manage position" not in clean.lower()
    assert "no position management until capital is authorized." in clean.lower()
    # Trailing fragment must be stripped
    assert "to ob low" not in clean.lower()
    assert "52.00" not in clean


def test_near_entry_manage_position_trailing_preposition_only_stripped():
    """'Manage position towards swing high.' — trailing 'towards...' stripped."""
    dirty = "Manage position towards swing high resistance."
    clean = _sanitize_reason_for_tier(dirty, "NEAR_ENTRY")
    assert "manage position" not in clean.lower()
    assert "no position management until capital is authorized." in clean.lower()
    assert "towards swing high" not in clean.lower()


# ---------------------------------------------------------------------------
# Test 7 — Blocker note fallback no longer says "watchlist only until"
# ---------------------------------------------------------------------------

def test_build_near_entry_blocker_note_fallback_no_watchlist_language():
    """_build_near_entry_blocker_note() fallback must NOT say 'watchlist only until'.

    The fallback fires when retest, hold, R:R, and overhead are all acceptable
    but the signal is still in NEAR_ENTRY (edge case).
    """
    signal = {
        "trigger_level": 55.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "risk_reward": 3.5,
        "overhead_status": "clear",
    }
    note = _build_near_entry_blocker_note(signal, current_price=56.00)
    assert "watchlist only" not in note.lower()
    assert "watchlist only until" not in note.lower()
    # Must still be a valid blocker note (non-empty, starts with "Blocker:")
    assert note.startswith("Blocker:")


# ---------------------------------------------------------------------------
# Test 8 — Full format_alert() does not display blocker fallback with "watchlist"
# ---------------------------------------------------------------------------

def test_format_alert_blocker_fallback_no_watchlist_language():
    """format_alert() with all confirmed conditions still renders a clean blocker."""
    tr = _tr(
        "NEAR_ENTRY",
        retest_status="confirmed",
        hold_status="confirmed",
        risk_reward=3.5,
        overhead_status="clear",
        near_entry_blocker_note=(
            "Blocker: watch for trigger acceptance and full zone confirmation."
        ),
        reason="All conditions confirmed — borderline NEAR_ENTRY.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "watchlist only" not in text.lower()
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()


# ---------------------------------------------------------------------------
# Test 9 — NEAR_ENTRY with sanitized_reason pre-populated (pipeline path)
# ---------------------------------------------------------------------------

def test_ela_pre_sanitized_reason_via_pipeline():
    """Simulate the real pipeline path: tiering.py populated sanitized_reason.

    When sanitized_reason is already set (stripped of tier-degradation language),
    format_alert() should use it and the guard should see clean text.
    """
    # Simulate tiering.py having already sanitized the reason
    sanitized = _sanitize_reason_for_tier(
        "BOS confirmed — degrading this from SNIPE_IT to STARTER; hold partial.",
        "NEAR_ENTRY",
    )
    tr = _tr(
        "NEAR_ENTRY",
        reason="BOS confirmed — degrading this from SNIPE_IT to STARTER; hold partial.",
        sanitized_reason=sanitized,
        near_entry_blocker_note=(
            "Blocker: hold is not fully confirmed; wait for body-close acceptance"
            " inside/above the zone."
        ),
    )
    text = format_alert(tr)

    assert "from snipe_it to starter" not in text.lower()
    assert "from SNIPE_IT to STARTER" not in text
    assert "degrading" not in text.lower()
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()


# ---------------------------------------------------------------------------
# Test 10 — Regression: Phase 13.6A tests still pass (guard backward compat)
# ---------------------------------------------------------------------------

def test_13_6a_regression_guard_still_covers_prior_contradictions():
    """Verify Phase 13.6A guard rules are not broken by Phase 13.6B additions."""
    # GEV: "All SNIPE_IT conditions are met" in NEAR_ENTRY
    tr_gev = _tr(
        "NEAR_ENTRY",
        reason="All SNIPE_IT conditions are met — overhead moderate.",
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: overhead path is not clean enough for capital."
        ),
        overhead_status="moderate",
        missing_conditions=["overhead_path_not_clean"],
    )
    text_gev = format_alert(tr_gev)
    assert "all snipe_it conditions are met" not in text_gev.lower()
    assert "NO CAPITAL" in text_gev or "WATCH ONLY" in text_gev or "no capital" in text_gev.lower()

    # HWKN: "making this a STARTER" in NEAR_ENTRY
    tr_hwkn = _tr(
        "NEAR_ENTRY",
        reason="Retest partial — making this a STARTER entry with starter size only.",
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed."
        ),
        retest_status="partial",
        hold_status="partial",
        missing_conditions=["retest_partial"],
    )
    text_hwkn = format_alert(tr_hwkn)
    assert "making this a starter" not in text_hwkn.lower()
    assert "STARTER SIZE ONLY" not in text_hwkn
    assert "NO CAPITAL" in text_hwkn or "WATCH ONLY" in text_hwkn or "no capital" in text_hwkn.lower()

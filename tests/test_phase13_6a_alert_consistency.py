"""Phase 13.6A — Alert text consistency regression tests.

Locks the four live observed contradictions (GEV, HWKN, AVGO) and the two
correct-tier baselines (STARTER, SNIPE_IT) so they can never regress.

Scenario labels match the live observations documented in Phase 13.6A:
  GEV  — NEAR_ENTRY with SNIPE-like raw conditions; text said "All SNIPE_IT conditions are met"
  HWKN — NEAR_ENTRY with text saying "making this a STARTER"
  AVGO — NEAR_ENTRY with confirmed retest + hold but text said "wait until retest and hold confirm"
  WST  — model correct NEAR_ENTRY (hold partial, NO CAPITAL, watch only)
"""

from src.discord_alerts import format_alert


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
        "ticker": "TEST",
        "tier": tier,
        "score": 80,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Below FVG base",
        "invalidation_level": 95.00,
        "targets": [{"label": "T1", "level": 115.00, "reason": "Prior swing high"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Watch for acceptance.",
        "discord_channel": channel_map[tier],
        "capital_action": capital_map[tier],
        "reason": "Clean structure.",
        "sanitized_reason": None,
        "sanitized_next_action": None,
        "scan_price": 100.00,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 5.0,
        "risk_distance": 5.00,
        "risk_distance_pct": 5.0,
        "current_price_to_invalidation": 5.00,
        "current_price_to_invalidation_pct": 5.0,
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
# Test 1 — GEV scenario: NEAR_ENTRY with confirmed retest + confirmed hold
#           but overhead blocks capital. Must NOT say "All SNIPE_IT conditions
#           are met" or "wait until retest and hold confirm".
# ---------------------------------------------------------------------------

def test_near_entry_confirmed_retest_hold_overhead_blocker():
    """AVGO / GEV scenario: retest and hold are both confirmed; blocker is overhead.

    The alert must:
      - say NO CAPITAL / WATCH ONLY
      - name the overhead/acceptance blocker
      - NOT say "All SNIPE_IT conditions met" in any form
      - NOT say "wait until retest and hold confirm" (they are already confirmed)
    """
    tr = _tr(
        "NEAR_ENTRY",
        retest_status="confirmed",
        hold_status="confirmed",
        overhead_status="moderate",
        # Claude's raw reason contained the GEV contradiction phrase
        reason="All SNIPE_IT conditions are met — overhead moderate.",
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: overhead path is not clean enough for capital;"
            " wait for reclaim through resistance."
        ),
        missing_conditions=["overhead_path_not_clean"],
        upgrade_trigger="Reclaim through resistance with expansion candle.",
    )
    text = format_alert(tr)

    # Must say no-capital language
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    # Must name the overhead blocker (from near_entry_blocker_note)
    assert "overhead" in text.lower() or "resistance" in text.lower()

    # Must NOT say "All SNIPE_IT conditions met" in any variant
    assert "All SNIPE_IT conditions met" not in text
    assert "all snipe_it conditions met" not in text.lower()
    assert "All SNIPE_IT conditions are met" not in text
    assert "all snipe_it conditions are met" not in text.lower()

    # Must NOT say "wait until retest and hold confirm" (they are confirmed)
    assert "wait until retest and hold confirm" not in text.lower()
    assert "Watchlist only until retest and hold confirm" not in text


# ---------------------------------------------------------------------------
# Test 2 — GEV scenario: NEAR_ENTRY with SNIPE-like raw reason but tier blocked.
#           Must stay in NEAR_ENTRY language throughout.
# ---------------------------------------------------------------------------

def test_near_entry_snipe_like_reason_stays_near_entry():
    """NEAR_ENTRY alert where Claude's reason contained SNIPE_IT affirmations.

    The sanitizer and guard must strip them. The rendered text must:
      - contain NEAR_ENTRY badge
      - say NO CAPITAL or WATCH ONLY
      - NOT say "All SNIPE_IT conditions met" (any form)
      - NOT say "FULL QUALITY"
    """
    tr = _tr(
        "NEAR_ENTRY",
        retest_status="confirmed",
        hold_status="confirmed",
        overhead_status="moderate",
        reason=(
            "Snipe_it conditions met — full quality allowed. "
            "All SNIPE_IT conditions satisfied. "
            "This is a full-quality candidate."
        ),
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: overhead path is not clean enough for capital;"
            " wait for reclaim through resistance."
        ),
        missing_conditions=["overhead_path_not_clean"],
        upgrade_trigger="Clean break above resistance.",
    )
    text = format_alert(tr)

    # NEAR_ENTRY badge must be present
    assert "🟢 NEAR ENTRY" in text

    # Must say no-capital language
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    # Must NOT say SNIPE_IT execution affirmations
    assert "All SNIPE_IT conditions met" not in text
    assert "all snipe_it conditions met" not in text.lower()
    assert "all snipe_it conditions satisfied" not in text.lower()

    # Must NOT say FULL QUALITY (SNIPE_IT capital label)
    assert "FULL QUALITY" not in text


# ---------------------------------------------------------------------------
# Test 3 — HWKN scenario: NEAR_ENTRY with "making this a STARTER" in reason.
#           Must NOT leak STARTER execution language.
# ---------------------------------------------------------------------------

def test_near_entry_hwkn_making_this_a_starter_stripped():
    """HWKN scenario: Claude wrote "making this a STARTER" inside a NEAR_ENTRY reason.

    The alert must:
      - say NO CAPITAL / WATCH ONLY
      - NOT say "making this a STARTER"
      - NOT say "STARTER SIZE ONLY"
    """
    tr = _tr(
        "NEAR_ENTRY",
        retest_status="partial",
        hold_status="partial",
        overhead_status="clear",
        reason=(
            "Retest partial — making this a STARTER entry with starter size only "
            "until full confirmation."
        ),
        sanitized_reason=None,
        near_entry_blocker_note=(
            "Blocker: retest is not fully confirmed; wait for full zone interaction and hold."
        ),
        missing_conditions=["retest_partial", "hold_partial"],
        upgrade_trigger="Confirmed close inside zone with body acceptance.",
    )
    text = format_alert(tr)

    # Must say no-capital language
    assert "NO CAPITAL" in text or "WATCH ONLY" in text or "no capital" in text.lower()

    # Must NOT say STARTER execution language leaked from reason
    assert "making this a STARTER" not in text
    assert "making this a starter" not in text.lower()

    # Must NOT say STARTER SIZE ONLY (STARTER capital label)
    assert "STARTER SIZE ONLY" not in text


# ---------------------------------------------------------------------------
# Test 4 — STARTER: must say STARTER SIZE ONLY, never NO CAPITAL or FULL QUALITY.
# ---------------------------------------------------------------------------

def test_starter_capital_language_correct():
    """STARTER alert must carry STARTER SIZE ONLY capital label.

    Must NOT say NO CAPITAL, WATCH ONLY, or FULL QUALITY.
    """
    tr = _tr(
        "STARTER",
        reason=(
            "BOS confirmed with OB retest and hold. Overhead moderate — "
            "full-size confirmation not granted. Starter size only."
        ),
        sanitized_reason=None,
    )
    text = format_alert(tr)

    # Must say STARTER capital language
    assert "STARTER SIZE ONLY" in text

    # Must say STARTER action label (Phase 13.7B contract headline)
    assert "STARTER conditions met." in text

    # Must NOT say NEAR_ENTRY capital language
    assert "NO CAPITAL — WATCH ONLY" not in text

    # Must NOT say SNIPE_IT capital language
    assert "FULL QUALITY" not in text

    # Must NOT say SNIPE_IT action label
    assert "All SNIPE_IT conditions met." not in text


# ---------------------------------------------------------------------------
# Test 5 — SNIPE_IT: must say FULL QUALITY or "All SNIPE_IT conditions met",
#           must NOT say NO CAPITAL, must NOT include blocker section.
# ---------------------------------------------------------------------------

def test_snipe_it_capital_and_action_language_correct():
    """SNIPE_IT alert must carry FULL QUALITY and the SNIPE_IT action label.

    Must NOT say NO CAPITAL, WATCH ONLY, or include a blocker section.
    """
    tr = _tr(
        "SNIPE_IT",
        retest_status="confirmed",
        hold_status="confirmed",
        overhead_status="clear",
        reason="Clean MSS with FVG retest and hold confirmed. Path clear.",
        sanitized_reason=None,
    )
    text = format_alert(tr)

    # Must say SNIPE_IT action label (Phase 13.7B contract headline)
    assert "SNIPE_IT conditions met." in text

    # Must say FULL QUALITY capital label
    assert "FULL QUALITY" in text

    # Must NOT say NO CAPITAL or WATCH ONLY
    assert "NO CAPITAL" not in text
    assert "WATCH ONLY" not in text

    # Must NOT include a blocker section (blocker is NEAR_ENTRY-only)
    assert "⚠️  NO CAPITAL YET" not in text
    assert "Blocker:" not in text

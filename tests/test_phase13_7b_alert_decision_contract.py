"""Phase 13.7B: Alert Decision Contract / Capital Authorization Clarity.

Every test in this file validates one of the following contract guarantees:
- SNIPE_IT alerts never contain NO CAPITAL / WATCH ONLY / NEAR_ENTRY language
- STARTER alerts never contain FULL QUALITY / SNIPE_IT action language
- NEAR_ENTRY alerts never contain entry / capital / position-management language
- Overhead "moderate" always specifies whether it is blocking or not
- The contract guard runs last and cleans any phrase that survived upstream

No scanner/scoring/threshold/ticker/state/Railway changes are tested here.
"""

import pytest
from src.discord_alerts import format_alert, CAPITAL_CONTRACT, _render_overhead_label

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tr(tier="SNIPE_IT", score=88, safe=True, **signal_overrides) -> dict:
    """Minimal tiering_result fixture."""
    signal = {
        "ticker": "TST",
        "tier": tier,
        "score": score,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 100.00,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Daily close below FVG base",
        "invalidation_level": 97.00,
        "targets": [{"label": "T1", "level": 110.00, "reason": "Prior swing high"}],
        "risk_reward": 3.5,
        "overhead_status": "clear",
        "forced_participation": "none",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Monitor zone hold.",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with FVG retest and hold.",
        "sanitized_reason": None,
        "scan_price": 100.00,
        "drift_status": "snapshot_only",
        "drift_pct": 0.0,
        "freshness_note": "Signal based on scan-time price; verify live chart before entry.",
        "price_distance_to_trigger_pct": 0.0,
        "price_distance_to_invalidation_pct": 3.0,
        "risk_distance": 3.00,
        "risk_distance_pct": 3.0,
        "current_price_to_invalidation": 3.00,
        "current_price_to_invalidation_pct": 3.0,
        "risk_realism_state": "healthy",
        "risk_realism_note": "Risk window is healthy.",
    }
    signal.update(signal_overrides)
    channel_map = {
        "SNIPE_IT":   "#snipe-signals",
        "STARTER":    "#starter-signals",
        "NEAR_ENTRY": "#near-entry-watch",
    }
    return {
        "ok": True,
        "final_tier": tier,
        "score": score,
        "safe_for_alert": safe,
        "final_discord_channel": channel_map.get(tier, "none"),
        "capital_action": signal["capital_action"],
        "final_signal": signal,
    }


def _ne_tr(**overrides):
    """NEAR_ENTRY fixture with mandatory NEAR_ENTRY fields pre-set."""
    base = {
        "tier": "NEAR_ENTRY",
        "score": 65,
        "safe": True,
        "capital_action": "wait_no_capital",
        "missing_conditions": ["retest_not_confirmed"],
        "upgrade_trigger": "Confirmed retest with hold.",
        "reason": "Zone valid — awaiting retest.",
        "sanitized_reason": "Zone valid — awaiting retest.",
    }
    base.update(overrides)
    tr = _tr(**base)
    tr["final_tier"] = "NEAR_ENTRY"
    tr["capital_action"] = "wait_no_capital"
    tr["final_discord_channel"] = "#near-entry-watch"
    return tr


# ===========================================================================
# 1. SNIPE_IT contract: blocks no-capital / watch-only language
# ===========================================================================

def test_snipe_it_contract_blocks_no_capital_language():
    """SNIPE_IT alert must not contain NO CAPITAL, watch-only, or blocker language."""
    dirty = (
        "NO CAPITAL until retest confirms. Watch-only for now. "
        "Near-entry watch. No capital until blocker resolves."
    )
    tr = _tr(
        tier="SNIPE_IT",
        reason=dirty,
        sanitized_reason=None,
    )
    text = format_alert(tr)

    # Forbidden phrases must be gone
    assert "no capital" not in text.lower()
    assert "watch-only" not in text.lower()
    assert "watch only" not in text.lower()
    assert "near-entry watch" not in text.lower()
    assert "blocker resolves" not in text.lower()

    # Contract headline and sizing must appear
    assert "SNIPE_IT conditions met." in text
    assert "FULL QUALITY" in text
    assert "capital authorized after live-chart verification" in text.lower()


def test_snipe_it_contract_blocks_starter_size_only_language():
    """SNIPE_IT alert must not show STARTER SIZE ONLY language."""
    tr = _tr(
        tier="SNIPE_IT",
        reason="Starter size only — not full quality.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "starter size only" not in text.lower()
    # Still has the SNIPE_IT contract sizing
    assert "FULL QUALITY" in text


def test_snipe_it_contract_blocks_no_capital_yet():
    """SNIPE_IT alert must not contain 'NO CAPITAL YET' from any reason text."""
    tr = _tr(
        tier="SNIPE_IT",
        reason="NO CAPITAL YET — wait for confirmation.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "no capital yet" not in text.lower()
    assert "no capital" not in text.lower()


# ===========================================================================
# 2. STARTER contract: blocks FULL QUALITY / SNIPE_IT action language
# ===========================================================================

def test_starter_contract_blocks_full_quality_language():
    """STARTER alert must not contain FULL QUALITY, SNIPE_IT action language."""
    dirty = (
        "FULL QUALITY entry — all SNIPE_IT conditions met. "
        "All SNIPE_IT conditions satisfied. No capital — watch only."
    )
    tr = _tr(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason=dirty,
        sanitized_reason=None,
    )
    tr["final_tier"] = "STARTER"
    tr["final_discord_channel"] = "#starter-signals"
    text = format_alert(tr)

    # Forbidden phrases must be gone
    assert "full quality" not in text.lower()
    assert "all snipe_it conditions" not in text.lower()
    assert "no capital — watch only" not in text.lower()

    # Contract headline and sizing must appear
    assert "STARTER conditions met." in text
    assert "STARTER SIZE ONLY" in text
    assert "reduced-size capital only" in text.lower()


def test_starter_contract_blocks_snipe_it_conditions_met_variants():
    """STARTER alert must replace all SNIPE_IT conditions-met variants."""
    for phrase in [
        "All SNIPE_IT conditions satisfied.",
        "All SNIPE_IT conditions are met.",
        "All SNIPE_IT conditions met.",
        "SNIPE_IT conditions met.",
        "SNIPE_IT conditions satisfied.",
    ]:
        tr = _tr(
            tier="STARTER",
            score=78,
            capital_action="starter_only",
            reason=phrase,
            sanitized_reason=None,
        )
        tr["final_tier"] = "STARTER"
        text = format_alert(tr)
        assert "snipe_it conditions" not in text.lower(), (
            f"Found 'snipe_it conditions' in STARTER text after guard for input: {phrase!r}"
        )
        assert "STARTER conditions met." in text


def test_starter_contract_blocks_capital_authorized():
    """'capital authorized' in STARTER reason must be replaced."""
    tr = _tr(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="Setup is capital authorized — enter now.",
        sanitized_reason=None,
    )
    tr["final_tier"] = "STARTER"
    text = format_alert(tr)
    # "capital authorized" from reason must be sanitized
    assert "capital authorized" not in text.lower()
    # Replacement must be tier-safe
    assert "reduced-size capital allocated" in text.lower()


def test_starter_contract_preserves_valid_denial_language():
    """'full-size confirmation not granted' is valid STARTER language — must not be replaced."""
    tr = _tr(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        reason="Starter-quality candidate; full-size confirmation not granted.",
        sanitized_reason="Starter-quality candidate; full-size confirmation not granted.",
    )
    tr["final_tier"] = "STARTER"
    text = format_alert(tr)
    # Denial language must survive (it's not forbidden; "full quality" is the forbidden phrase)
    assert "full-size confirmation not granted" in text.lower()
    assert "STARTER SIZE ONLY" in text


# ===========================================================================
# 3. NEAR_ENTRY contract: blocks entry/capital/position-management language
# ===========================================================================

def test_near_entry_contract_blocks_entry_language():
    """NEAR_ENTRY alert must not contain entry, capital auth, SNIPE/STARTER action language."""
    dirty = (
        "Enter long at trigger. Capital authorized — FULL QUALITY allowed. "
        "All SNIPE_IT conditions met. Trail stop below 97.00. "
        "Scale into position on strength."
    )
    tr = _ne_tr(reason=dirty, sanitized_reason=None)
    text = format_alert(tr)

    # All forbidden phrases must be gone
    assert "enter long" not in text.lower()
    assert "capital authorized" not in text.lower()
    assert "full quality" not in text.lower()
    assert "all snipe_it conditions" not in text.lower()
    assert "trail stop" not in text.lower()
    assert "scale" not in text.lower()

    # Required contract text must be present
    assert "Near-entry watch — no capital until blocker resolves." in text
    assert "NO CAPITAL — WATCH ONLY" in text


def test_near_entry_contract_no_position_management_language():
    """NEAR_ENTRY: 'no position management until capital is authorized' is forbidden."""
    tr = _ne_tr(
        reason="Zone holds. No position management until capital is authorized.",
        sanitized_reason="Zone holds. No position management until capital is authorized.",
        next_action="Watch zone — no position management until capital is authorized.",
        sanitized_next_action=(
            "Watch zone — no position management until capital is authorized."
        ),
    )
    text = format_alert(tr)

    assert "position management" not in text.lower()
    assert "capital is authorized" not in text.lower()
    # Replaced with watch-safe language
    assert "watch-only" in text.lower() or "blocker resolution" in text.lower()


def test_near_entry_contract_blocks_add_to_position():
    """NEAR_ENTRY: 'add to position' is forbidden capital-action language."""
    tr = _ne_tr(
        reason="Hold and add to position on retest.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "add to position" not in text.lower()


def test_near_entry_contract_blocks_starter_sizing():
    """NEAR_ENTRY: 'starter sizing' / 'starter size only' must not appear."""
    for phrase in ["starter sizing", "starter size only"]:
        tr = _ne_tr(
            reason=f"Use {phrase} pending trigger.",
            sanitized_reason=None,
        )
        text = format_alert(tr)
        assert phrase not in text.lower(), (
            f"Forbidden phrase {phrase!r} survived in NEAR_ENTRY text"
        )
        assert "NO CAPITAL — WATCH ONLY" in text


def test_near_entry_all_starter_conditions_met_blocked():
    """NEAR_ENTRY: 'All STARTER conditions met' must be replaced."""
    for phrase in ["All STARTER conditions met.", "all starter conditions met"]:
        tr = _ne_tr(reason=phrase, sanitized_reason=None)
        text = format_alert(tr)
        assert "all starter conditions" not in text.lower(), (
            f"Phrase {phrase!r} survived in NEAR_ENTRY text"
        )


# ===========================================================================
# 4. Overhead label clarity
# ===========================================================================

def test_snipe_it_moderate_overhead_renders_not_blocking():
    """SNIPE_IT with moderate overhead → 'moderate — not blocking'."""
    tr = _tr(tier="SNIPE_IT", overhead_status="moderate")
    text = format_alert(tr)
    assert "moderate — not blocking" in text.lower()
    assert "moderate — blocker active" not in text.lower()
    # Bare "Overhead: moderate" must not appear (spec: always qualify)
    lines = [l for l in text.splitlines() if "overhead" in l.lower()]
    for line in lines:
        # Each overhead line must contain a qualifier
        assert "not blocking" in line.lower() or "blocker active" in line.lower() or \
               "clear" in line.lower() or "blocked" in line.lower(), \
               f"Overhead line missing qualifier: {line!r}"


def test_starter_moderate_overhead_renders_not_blocking():
    """STARTER with moderate overhead → 'moderate — not blocking'."""
    tr = _tr(
        tier="STARTER",
        score=78,
        capital_action="starter_only",
        overhead_status="moderate",
    )
    tr["final_tier"] = "STARTER"
    text = format_alert(tr)
    assert "moderate — not blocking" in text.lower()


def test_near_entry_overhead_blocker_renders_blocker_active():
    """NEAR_ENTRY with overhead-related blocker → 'moderate — blocker active'."""
    tr = _ne_tr(
        overhead_status="moderate",
        near_entry_blocker_note=(
            "Blocker: overhead resistance cluster within 2% — path is not clear."
        ),
    )
    text = format_alert(tr)
    assert "moderate — blocker active" in text.lower()


def test_near_entry_moderate_overhead_no_blocker_renders_not_blocking():
    """NEAR_ENTRY with moderate overhead and non-overhead blocker → 'not blocking'."""
    tr = _ne_tr(
        overhead_status="moderate",
        near_entry_blocker_note="Blocker: retest not yet confirmed.",
    )
    text = format_alert(tr)
    assert "moderate — not blocking" in text.lower()


def test_clear_overhead_renders_clear():
    """Any tier with clear overhead → 'clear'."""
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        overrides = {}
        if tier == "STARTER":
            overrides = {"score": 78, "capital_action": "starter_only"}
        elif tier == "NEAR_ENTRY":
            overrides = {
                "score": 65,
                "capital_action": "wait_no_capital",
                "missing_conditions": ["retest"],
                "upgrade_trigger": "Confirmed retest.",
            }
        tr = _tr(tier=tier, overhead_status="clear", **overrides)
        tr["final_tier"] = tier
        text = format_alert(tr)
        lines = [l for l in text.splitlines() if "overhead" in l.lower()]
        assert any("clear" in l.lower() for l in lines), (
            f"Expected 'clear' in overhead line for tier={tier}, got: {lines}"
        )


def test_blocked_overhead_renders_blocked():
    """overhead_status='blocked' renders as 'blocked'."""
    tr = _tr(tier="SNIPE_IT", overhead_status="blocked")
    text = format_alert(tr)
    assert "overhead" in text.lower()
    lines = [l for l in text.splitlines() if "overhead" in l.lower()]
    assert any("blocked" in l.lower() for l in lines)


# ===========================================================================
# 5. _render_overhead_label unit tests
# ===========================================================================

def test_render_overhead_label_snipe_it_moderate():
    assert _render_overhead_label("moderate", "SNIPE_IT") == "moderate — not blocking"


def test_render_overhead_label_starter_moderate():
    assert _render_overhead_label("moderate", "STARTER") == "moderate — not blocking"


def test_render_overhead_label_near_entry_overhead_keyword_in_blocker():
    label = _render_overhead_label(
        "moderate", "NEAR_ENTRY", "Blocker: overhead supply zone within 2%."
    )
    assert label == "moderate — blocker active"


def test_render_overhead_label_near_entry_no_overhead_keyword():
    label = _render_overhead_label(
        "moderate", "NEAR_ENTRY", "Blocker: retest not confirmed."
    )
    assert label == "moderate — not blocking"


def test_render_overhead_label_clear():
    assert _render_overhead_label("clear", "SNIPE_IT") == "clear"
    assert _render_overhead_label("clear", "NEAR_ENTRY") == "clear"


def test_render_overhead_label_blocked():
    assert _render_overhead_label("blocked", "STARTER") == "blocked"


def test_render_overhead_label_resistance_keyword_in_blocker():
    label = _render_overhead_label(
        "moderate", "NEAR_ENTRY", "Blocker: resistance cluster directly above trigger."
    )
    assert label == "moderate — blocker active"


def test_render_overhead_label_supply_keyword_in_blocker():
    label = _render_overhead_label(
        "moderate", "NEAR_ENTRY", "Blocker: supply zone at 105.00 not yet absorbed."
    )
    assert label == "moderate — blocker active"


# ===========================================================================
# 6. Contract guard runs last (catches anything that survives upstream)
# ===========================================================================

def test_contract_guard_runs_last():
    """Even if earlier sanitization passes, the contract guard catches final output."""
    # Build a NEAR_ENTRY alert where the raw reason carries forbidden SNIPE_IT language
    # that has NOT been pre-sanitized (sanitized_reason=None forces raw reason through).
    tr = _ne_tr(
        reason="All SNIPE_IT conditions are met. FULL QUALITY capital authorized.",
        sanitized_reason=None,
    )
    text = format_alert(tr)

    # The contract guard must have cleaned these
    assert "all snipe_it conditions" not in text.lower()
    assert "full quality" not in text.lower()
    assert "capital authorized" not in text.lower()

    # Required NEAR_ENTRY contract text intact
    assert "Near-entry watch — no capital until blocker resolves." in text
    assert "NO CAPITAL — WATCH ONLY" in text


def test_contract_guard_snipe_it_cleans_near_entry_language_from_reason():
    """SNIPE_IT contract guard catches NEAR_ENTRY language leaked into reason."""
    tr = _tr(
        tier="SNIPE_IT",
        reason="Near-entry watch — no capital yet. Blocker resolves before entry.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "near-entry watch" not in text.lower()
    assert "no capital yet" not in text.lower()
    assert "blocker resolves" not in text.lower()
    # SNIPE_IT contract intact
    assert "SNIPE_IT conditions met." in text
    assert "FULL QUALITY" in text


# ===========================================================================
# 7. CAPITAL_CONTRACT structure sanity
# ===========================================================================

def test_capital_contract_has_all_required_keys():
    """CAPITAL_CONTRACT must have all three actionable tiers with required keys."""
    required_keys = {"headline", "sizing", "capital_state", "forbidden"}
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        assert tier in CAPITAL_CONTRACT, f"CAPITAL_CONTRACT missing tier {tier!r}"
        entry = CAPITAL_CONTRACT[tier]
        missing = required_keys - set(entry.keys())
        assert not missing, f"CAPITAL_CONTRACT[{tier!r}] missing keys: {missing}"


def test_capital_contract_forbidden_lists_non_empty():
    """Each tier's forbidden list must have entries."""
    for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
        assert CAPITAL_CONTRACT[tier]["forbidden"], (
            f"CAPITAL_CONTRACT[{tier!r}]['forbidden'] is empty"
        )


def test_capital_contract_headlines_per_tier():
    """Contract headlines match Phase 13.7B spec."""
    assert CAPITAL_CONTRACT["SNIPE_IT"]["headline"] == "SNIPE_IT conditions met."
    assert CAPITAL_CONTRACT["STARTER"]["headline"] == "STARTER conditions met."
    assert CAPITAL_CONTRACT["NEAR_ENTRY"]["headline"] == (
        "Near-entry watch — no capital until blocker resolves."
    )


def test_capital_contract_sizing_contains_key_phrases():
    assert "FULL QUALITY" in CAPITAL_CONTRACT["SNIPE_IT"]["sizing"]
    assert "capital authorized" in CAPITAL_CONTRACT["SNIPE_IT"]["sizing"]
    assert "STARTER SIZE ONLY" in CAPITAL_CONTRACT["STARTER"]["sizing"]
    assert "reduced-size" in CAPITAL_CONTRACT["STARTER"]["sizing"]
    assert "NO CAPITAL" in CAPITAL_CONTRACT["NEAR_ENTRY"]["sizing"]
    assert "WATCH ONLY" in CAPITAL_CONTRACT["NEAR_ENTRY"]["sizing"]


def test_near_entry_no_replacement_contains_capital_authorized():
    """Hygiene: no NEAR_ENTRY replacement string may contain 'capital authorized'.

    The 'capital authorized' → 'no capital' rule must not be re-triggered by
    any earlier replacement producing 'capital authorized' as a substring.
    """
    for match, replacement in CAPITAL_CONTRACT["NEAR_ENTRY"]["forbidden"]:
        assert "capital authorized" not in replacement.lower(), (
            f"NEAR_ENTRY replacement {replacement!r} contains 'capital authorized'; "
            f"this would cause re-trigger of the 'capital authorized' rule."
        )


# ===========================================================================
# 8. Regression: Phase 13.6A/13.6B/13.7A protections still hold
# ===========================================================================

def test_existing_phase136_language_tests_still_pass():
    """Phase 13.6A/13.6B NEAR_ENTRY consistency protections are preserved."""
    # 13.6A: GEV-style — 'all snipe_it conditions are met' in NEAR_ENTRY
    tr = _ne_tr(
        reason="All SNIPE_IT conditions are met.",
        sanitized_reason=None,
    )
    text = format_alert(tr)
    assert "all snipe_it conditions" not in text.lower()
    assert "no capital" in text.lower()

    # 13.6B: ELA-style — degradation language
    tr2 = _ne_tr(
        reason="Degrading this from SNIPE_IT to STARTER.",
        sanitized_reason=None,
    )
    text2 = format_alert(tr2)
    assert "degrading this from snipe_it to starter" not in text2.lower()
    assert "snipe_it to starter" not in text2.lower()

    # 13.6B: watchlist-only language
    tr3 = _ne_tr(
        reason="Watchlist only until retest and hold confirm.",
        sanitized_reason=None,
    )
    text3 = format_alert(tr3)
    assert "watchlist only until" not in text3.lower()


def test_existing_phase137a_fragile_rr_tests_still_pass():
    """Phase 13.7A fragile risk governor still operates correctly."""
    from src.tiering import validate

    _BASE_CONFIG = {
        "tiers": {
            "snipe_it":   {"min_score": 85, "min_rr": 3.0},
            "starter":    {"min_score": 75, "min_rr": 3.0},
            "near_entry": {"min_score": 60},
        }
    }

    # CSX-style: fragile stop must block SNIPE_IT → cascade to STARTER
    signal = {
        "ticker": "CSX",
        "timestamp_et": "2025-01-15T10:30:00-05:00",
        "tier": "SNIPE_IT",
        "score": 90,
        "setup_family": "continuation",
        "structure_event": "MSS",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "FVG",
        "trigger_level": 44.70,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "Close below FVG base",
        "invalidation_level": 44.68,
        "targets": [{"label": "T1", "level": 46.00, "reason": "Prior supply"}],
        "risk_reward": 73.80,
        "overhead_status": "clear",
        "forced_participation": "Full quality — zone held cleanly",
        "missing_conditions": [],
        "upgrade_trigger": "none",
        "next_action": "Monitor hold.",
        "discord_channel": "#snipe-signals",
        "capital_action": "full_quality_allowed",
        "reason": "Clean MSS with FVG retest and hold.",
    }
    result = validate(signal, {"veto_flags": []}, _BASE_CONFIG)
    assert result["final_tier"] == "STARTER"
    downgrade_text = " ".join(result.get("downgrades", []))
    assert "fragile" in downgrade_text.lower()

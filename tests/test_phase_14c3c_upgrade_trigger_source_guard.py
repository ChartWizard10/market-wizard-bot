"""Phase 14C.3C — Upgrade Trigger Level Source Guard tests.

Verifies that target / liquidity / T1 / T2 levels are never used as the
Upgrade trigger execution proof level in Discord alerts.

Five test groups:
  1. CRNT exact regression — trigger=3.02 wins over T1=3.29.
  2. Target guard — when only targets exist, use safe fallback text.
  3. Source priority — level-selection hierarchy is respected.
  4. Existing live-case preservation — TWLO/LSTR/SAIC patterns intact.
  5. Invariants — no score/tier/capital/routing mutation; no raise on bad data.
"""

import copy
import math

from src.discord_alerts import (
    format_alert,
    _is_target_like_label,
    _valid_execution_proof_level,
    _collect_target_levels,
    _select_upgrade_trigger_level,
    _derive_upgrade_trigger,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _loc(
    location_state="mid_zone_acceptance",
    zone_type="FVG",
    zone_low=2.98,
    zone_high=3.02,
    zone_mid=3.00,
    scan_price=2.91,
    confirmation_level=None,
    display_text="",
) -> dict:
    return {
        "zone_type":          zone_type,
        "zone_low":           zone_low,
        "zone_high":          zone_high,
        "zone_mid":           zone_mid,
        "scan_price":         scan_price,
        "location_state":     location_state,
        "confirmation_level": confirmation_level,
        "display_text":       display_text or f"location: {location_state}",
        "flags":              [],
    }


def _tr_near_entry(
    ticker="CRNT",
    trigger_level=3.02,
    invalidation_level=2.98,
    targets=None,
    upgrade_trigger="—",
    retest_status="partial",
    hold_status="partial",
    trade_location=None,
    near_entry_blocker_note="Retest incomplete.",
    missing_conditions=None,
    **sig_extra,
) -> dict:
    if targets is None:
        targets = [{"label": "T1", "level": 3.29, "reason": "next liquidity pool"}]
    sig = {
        "ticker":               ticker,
        "score":                72,
        "scan_price":           2.91,
        "zone_type":            "FVG",
        "setup_family":         "continuation",
        "structure_event":      "MSS",
        "trend_state":          "expansion",
        "risk_realism_state":   "healthy",
        "overhead_status":      "moderate",
        "retest_status":        retest_status,
        "hold_status":          hold_status,
        "risk_reward":          2.5,
        "sma_value_alignment":  "supportive",
        "missing_conditions":   missing_conditions or [],
        "invalidation_level":   invalidation_level,
        "invalidation_condition": "daily body close below zone",
        "trigger_level":        trigger_level,
        "reason":               "FVG holding; retest needed.",
        "next_action":          "Wait for full retest of FVG.",
        "upgrade_trigger":      upgrade_trigger,
        "near_entry_blocker_note": near_entry_blocker_note,
        "targets":              targets,
    }
    sig.update(sig_extra)
    tr = {
        "final_tier":           "NEAR_ENTRY",
        "score":                72,
        "safe_for_alert":       True,
        "final_discord_channel": "#near",
        "capital_action":       "wait_no_capital",
        "trajectory":           {"label": "NEW_SIGNAL", "text": ""},
        "final_signal":         sig,
    }
    if trade_location is not None:
        tr["trade_location"] = trade_location
    return tr


# ---------------------------------------------------------------------------
# Unit tests for new helpers
# ---------------------------------------------------------------------------

class TestIsTargetLikeLabel:
    def test_t1_is_target(self):
        assert _is_target_like_label("T1")
        assert _is_target_like_label("t1")

    def test_t2_is_target(self):
        assert _is_target_like_label("T2")
        assert _is_target_like_label("t2")

    def test_ltp_is_target(self):
        assert _is_target_like_label("LTP")

    def test_liquidity_pool_is_target(self):
        assert _is_target_like_label("liquidity_pool")

    def test_measured_move_is_target(self):
        assert _is_target_like_label("measured_move")

    def test_take_profit_is_target(self):
        assert _is_target_like_label("take_profit")

    def test_trigger_not_target(self):
        assert not _is_target_like_label("trigger")

    def test_zone_high_not_target(self):
        assert not _is_target_like_label("zone_high")

    def test_confirmation_level_not_target(self):
        assert not _is_target_like_label("confirmation_level")

    def test_empty_not_target(self):
        assert not _is_target_like_label("")
        assert not _is_target_like_label(None)


class TestValidExecutionProofLevel:
    def test_valid_positive_float(self):
        assert _valid_execution_proof_level(3.02) == pytest_approx(3.02)

    def test_valid_string_float(self):
        assert _valid_execution_proof_level("204.53") == pytest_approx(204.53)

    def test_none_returns_none(self):
        assert _valid_execution_proof_level(None) is None

    def test_zero_returns_none(self):
        assert _valid_execution_proof_level(0) is None

    def test_negative_returns_none(self):
        assert _valid_execution_proof_level(-1.5) is None

    def test_inf_returns_none(self):
        assert _valid_execution_proof_level(math.inf) is None

    def test_nan_returns_none(self):
        assert _valid_execution_proof_level(math.nan) is None

    def test_blank_string_returns_none(self):
        assert _valid_execution_proof_level("") is None

    def test_non_numeric_returns_none(self):
        assert _valid_execution_proof_level("above 3.02") is None


# pytest_approx alias (avoids importing pytest at module level)
def pytest_approx(v):
    import pytest
    return pytest.approx(v)


class TestCollectTargetLevels:
    def test_t1_level_collected(self):
        sig = {"targets": [{"label": "T1", "level": 3.29, "reason": "pool"}]}
        banned = _collect_target_levels(sig)
        assert 3.29 in banned

    def test_t2_level_collected(self):
        sig = {"targets": [
            {"label": "T1", "level": 3.29},
            {"label": "T2", "level": 3.55},
        ]}
        banned = _collect_target_levels(sig)
        assert 3.29 in banned
        assert 3.55 in banned

    def test_direct_t1_field_collected(self):
        sig = {"t1": 55.0}
        banned = _collect_target_levels(sig)
        assert 55.0 in banned

    def test_all_targets_collected_regardless_of_label(self):
        sig = {"targets": [{"label": "Custom Level", "level": 99.0}]}
        banned = _collect_target_levels(sig)
        assert 99.0 in banned

    def test_empty_signal_returns_empty(self):
        assert len(_collect_target_levels({})) == 0

    def test_no_targets_key_returns_empty(self):
        assert len(_collect_target_levels({"score": 88})) == 0

    def test_invalid_level_skipped(self):
        sig = {"targets": [{"label": "T1", "level": None}]}
        banned = _collect_target_levels(sig)
        assert len(banned) == 0


class TestSelectUpgradeTriggerLevel:
    def test_confirmation_level_wins_when_not_target(self):
        sig = {"targets": [{"label": "T1", "level": 3.29}]}
        tl  = {"confirmation_level": 3.02, "zone_high": 3.02, "zone_low": 2.98}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert level == pytest_approx(3.02)
        assert source == "confirmation_level"

    def test_confirmation_level_rejected_when_matches_target(self):
        """CRNT defect: confirmation_level=3.29 (T1) must be rejected."""
        sig = {"targets": [{"label": "T1", "level": 3.29}], "trigger_level": 3.02}
        tl  = {"confirmation_level": 3.29, "zone_high": 3.02, "zone_low": 2.98}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert level == pytest_approx(3.02)
        assert source in ("trigger_level",)

    def test_trigger_level_beats_zone_high(self):
        sig = {"trigger_level": 3.02}
        tl  = {"zone_high": 3.00, "zone_low": 2.98}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "trigger_level"

    def test_zone_high_beats_zone_low(self):
        sig = {}
        tl  = {"zone_high": 3.02, "zone_low": 2.98}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "zone_high"

    def test_zone_low_used_as_last_resort(self):
        sig = {}
        tl  = {"zone_low": 2.98}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "zone_low"
        assert level == pytest_approx(2.98)

    def test_no_level_returns_none(self):
        level, source, _ = _select_upgrade_trigger_level({}, {})
        assert level is None

    def test_target_is_never_selected(self):
        """When only target levels exist, return None."""
        sig = {
            "targets": [{"label": "T1", "level": 3.29}],
        }
        tl  = {"confirmation_level": 3.29}
        level, _, _ = _select_upgrade_trigger_level(sig, tl)
        assert level is None


# ===========================================================================
# Group 1 — CRNT exact regression
# ===========================================================================

class TestCRNTRegressionExact:
    def _crnt_tr(self):
        """Reproduce the live CRNT defect scenario exactly."""
        tl = _loc(
            location_state="below_zone_low",
            zone_type="FVG",
            zone_low=2.98,
            zone_high=3.02,
            zone_mid=3.00,
            scan_price=2.91,
            # confirmation_level contaminated with T1 (the live defect)
            confirmation_level=3.29,
        )
        return _tr_near_entry(
            ticker="CRNT",
            trigger_level=3.02,
            invalidation_level=2.98,
            targets=[{"label": "T1", "level": 3.29, "reason": "next liquidity pool"}],
            upgrade_trigger="—",   # blank → falls through to synthesis
            trade_location=tl,
        )

    def test_upgrade_trigger_uses_3_02_not_3_29(self):
        """Core regression: synthesized trigger must be 3.02, never 3.29."""
        body = format_alert(self._crnt_tr())
        assert "Upgrade trigger:    Body close / acceptance above 3.02" in body

    def test_upgrade_trigger_does_not_use_t1(self):
        """T1 (3.29) must not appear in the Upgrade trigger line."""
        body = format_alert(self._crnt_tr())
        upgrade_lines = [
            ln for ln in body.splitlines()
            if ln.strip().startswith("Upgrade trigger:")
        ]
        assert upgrade_lines, "Expected an Upgrade trigger: line"
        for line in upgrade_lines:
            assert "3.29" not in line, (
                f"T1 value 3.29 appeared in upgrade trigger line: {line!r}"
            )

    def test_t1_remains_in_targets_section(self):
        """T1=3.29 must still appear in the TARGETS section, not the trigger."""
        body = format_alert(self._crnt_tr())
        assert "3.29" in body, "T1 should still appear somewhere in the alert"
        targets_idx = body.find("TARGETS")
        t1_idx      = body.find("3.29")
        assert targets_idx != -1, "TARGETS section missing"
        assert t1_idx > targets_idx, "3.29 must appear after the TARGETS header"

    def test_no_missing_conditions_dash(self):
        """NEAR_ENTRY blocker intelligence is synthesized — never '—'."""
        body = format_alert(self._crnt_tr())
        assert "Missing conditions: —" not in body

    def test_no_upgrade_trigger_none(self):
        """Upgrade trigger must never render as 'none'."""
        body = format_alert(self._crnt_tr())
        assert "Upgrade trigger:    none" not in body.lower()


# ===========================================================================
# Group 2 — Target guard
# ===========================================================================

class TestTargetGuard:
    def test_only_targets_available_no_trigger_uses_fallback(self):
        """If no execution-proof level exists at all, render safe fallback."""
        tl = _loc(
            location_state="mid_zone_acceptance",
            zone_low=None, zone_high=None, zone_mid=None,
            confirmation_level=None,
        )
        # Override loc to strip zone values
        tl["zone_low"]          = None
        tl["zone_high"]         = None
        tl["zone_mid"]          = None
        tl["confirmation_level"] = None

        tr = _tr_near_entry(
            trigger_level=None,
            targets=[{"label": "T1", "level": 3.29}],
            upgrade_trigger="—",
            trade_location=tl,
        )
        # Also remove trigger_level from signal
        tr["final_signal"]["trigger_level"] = None
        body = format_alert(tr)
        upgrade_lines = [
            ln for ln in body.splitlines()
            if ln.strip().startswith("Upgrade trigger:")
        ]
        assert upgrade_lines
        ul = upgrade_lines[0]
        # Should be safe fallback text — not 3.29 and not '—' and not 'none'
        assert "3.29" not in ul
        assert "Upgrade trigger:    —" not in body
        assert "Upgrade trigger:    none" not in body.lower()

    def test_t1_in_confirmation_level_blocked(self):
        """confirmation_level matching T1 is rejected; trigger_level used instead."""
        sig = {
            "targets": [{"label": "T1", "level": 55.0}],
            "trigger_level": 48.5,
        }
        tl = {"confirmation_level": 55.0}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert level == pytest_approx(48.5)
        assert source == "trigger_level"

    def test_target_value_never_in_trigger_line(self):
        """Any target value must not appear in the Upgrade trigger: rendered line."""
        tl = _loc(confirmation_level=3.29, zone_high=3.02, zone_low=2.98)
        tr = _tr_near_entry(
            trigger_level=3.02,
            targets=[{"label": "T1", "level": 3.29}],
            upgrade_trigger="—",
            trade_location=tl,
        )
        body = format_alert(tr)
        for line in body.splitlines():
            if line.strip().startswith("Upgrade trigger:"):
                assert "3.29" not in line


# ===========================================================================
# Group 3 — Source priority
# ===========================================================================

class TestSourcePriority:
    def test_confirmation_level_beats_trigger_level(self):
        """Non-contaminated confirmation_level takes priority over trigger_level."""
        sig = {
            "targets": [{"label": "T1", "level": 55.0}],
            "trigger_level": 49.0,
        }
        tl = {"confirmation_level": 51.0}  # not in targets
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "confirmation_level"
        assert level == pytest_approx(51.0)

    def test_trigger_level_beats_zone_high_when_conf_contaminated(self):
        """trigger_level used when confirmation_level is contaminated."""
        sig = {
            "targets": [{"label": "T1", "level": 55.0}],
            "trigger_level": 49.0,
        }
        tl = {"confirmation_level": 55.0, "zone_high": 48.0}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "trigger_level"
        assert level == pytest_approx(49.0)

    def test_zone_high_beats_zone_low(self):
        sig = {}
        tl  = {"zone_high": 3.02, "zone_low": 2.98}
        _, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "zone_high"

    def test_zone_low_last_resort_returns_retest_phrasing(self):
        """When only zone_low is available, render retest-and-close wording."""
        body = _derive_upgrade_trigger(
            signal={},
            tl_ctx={"zone_low": 2.98},
            candle={},
        )
        assert "close back above" in body.lower()
        assert "2.98" in body

    def test_confirmation_level_not_target_used_over_trigger(self):
        """Uncontaminated confirmation_level (e.g. zone_high set by trade_location)
        wins over trigger_level in the source priority."""
        sig = {"targets": [{"label": "T1", "level": 55.0}], "trigger_level": 49.0}
        tl  = {"confirmation_level": 50.5}
        level, source, _ = _select_upgrade_trigger_level(sig, tl)
        assert source == "confirmation_level"
        assert level == pytest_approx(50.5)


# ===========================================================================
# Group 4 — Existing live-case preservation
# ===========================================================================

class TestExistingLiveCases:
    """Regression guard: named live-case patterns must still render correctly."""

    def _make_tr(self, ticker, trigger, t1, conf_level, zone_high, zone_low,
                 scan_price=None):
        tl = _loc(
            zone_low=zone_low, zone_high=zone_high,
            zone_mid=(zone_low + zone_high) / 2,
            scan_price=scan_price or (zone_low + zone_high) / 2,
            confirmation_level=conf_level,
        )
        return _tr_near_entry(
            ticker=ticker,
            trigger_level=trigger,
            targets=[{"label": "T1", "level": t1, "reason": "pool"}],
            upgrade_trigger="—",
            trade_location=tl,
        )

    def test_twlo_style_uses_trigger_not_target(self):
        """TWLO-style: trigger=204.53, T1=230.00 → trigger wins."""
        tr = self._make_tr("TWLO", trigger=204.53, t1=230.00,
                           conf_level=204.53, zone_high=204.53, zone_low=198.0,
                           scan_price=202.0)
        body = format_alert(tr)
        upgrade_lines = [l for l in body.splitlines()
                         if l.strip().startswith("Upgrade trigger:")]
        assert upgrade_lines
        assert "204.53" in upgrade_lines[0]
        assert "230.00" not in upgrade_lines[0]

    def test_lstr_style_uses_ob_top_not_target(self):
        """LSTR-style: OB top=219.62, T1=240.00 → OB top wins."""
        tr = self._make_tr("LSTR", trigger=219.62, t1=240.00,
                           conf_level=219.62, zone_high=219.62, zone_low=212.0,
                           scan_price=215.0)
        body = format_alert(tr)
        upgrade_lines = [l for l in body.splitlines()
                         if l.strip().startswith("Upgrade trigger:")]
        assert upgrade_lines
        assert "219.62" in upgrade_lines[0]
        assert "240.00" not in upgrade_lines[0]

    def test_saic_style_fvg_uses_zone_proof_not_target(self):
        """SAIC-style: FVG zone 120-124, T1=123.41 should not be trigger."""
        tr = self._make_tr("SAIC", trigger=124.0, t1=123.41,
                           conf_level=124.0, zone_high=124.0, zone_low=120.0,
                           scan_price=122.0)
        body = format_alert(tr)
        upgrade_lines = [l for l in body.splitlines()
                         if l.strip().startswith("Upgrade trigger:")]
        assert upgrade_lines
        assert "123.41" not in upgrade_lines[0]
        assert "124.00" in upgrade_lines[0]

    def test_no_upgrade_trigger_none_in_any_case(self):
        """Upgrade trigger must never render as 'none' for any of these cases."""
        for ticker, trigger, t1, conf, zh, zl, sp in [
            ("TWLO", 204.53, 230.00, 204.53, 204.53, 198.0, 202.0),
            ("LSTR", 219.62, 240.00, 219.62, 219.62, 212.0, 215.0),
            ("SAIC", 124.0,  123.41, 124.0,  124.0,  120.0, 122.0),
        ]:
            tr = self._make_tr(ticker, trigger, t1, conf, zh, zl, sp)
            body = format_alert(tr)
            assert "Upgrade trigger:    none" not in body.lower(), (
                f"{ticker}: Upgrade trigger: none found"
            )

    def test_no_missing_conditions_dash_in_any_case(self):
        """Missing conditions must never be blank '—' when context exists."""
        for ticker, trigger, t1, conf, zh, zl, sp in [
            ("TWLO", 204.53, 230.00, 204.53, 204.53, 198.0, 202.0),
            ("LSTR", 219.62, 240.00, 219.62, 219.62, 212.0, 215.0),
        ]:
            tr = self._make_tr(ticker, trigger, t1, conf, zh, zl, sp)
            body = format_alert(tr)
            assert "Missing conditions: —" not in body, (
                f"{ticker}: 'Missing conditions: —' found"
            )


# ===========================================================================
# Group 5 — Invariants
# ===========================================================================

class TestInvariants:
    def _crnt_tr(self):
        tl = _loc(confirmation_level=3.29, zone_high=3.02, zone_low=2.98,
                  scan_price=2.91)
        return _tr_near_entry(
            trigger_level=3.02,
            targets=[{"label": "T1", "level": 3.29}],
            upgrade_trigger="—",
            trade_location=tl,
        )

    def test_raw_score_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["score"] == before["score"]

    def test_final_tier_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["final_tier"] == before["final_tier"]

    def test_capital_action_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["capital_action"] == before["capital_action"]

    def test_final_discord_channel_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["final_discord_channel"] == before["final_discord_channel"]

    def test_safe_for_alert_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["safe_for_alert"] == before["safe_for_alert"]

    def test_final_signal_unchanged(self):
        tr = self._crnt_tr()
        before = copy.deepcopy(tr)
        format_alert(tr)
        assert tr["final_signal"] == before["final_signal"]

    def test_no_raise_on_missing_trigger_level(self):
        """Absent trigger_level must not raise — graceful fallback."""
        tr = self._crnt_tr()
        tr["final_signal"]["trigger_level"] = None
        try:
            format_alert(tr)
        except Exception as exc:
            assert False, f"format_alert raised on missing trigger_level: {exc}"

    def test_no_raise_on_malformed_confirmation_level(self):
        """Non-numeric confirmation_level must not raise."""
        tr = self._crnt_tr()
        tr["trade_location"]["confirmation_level"] = "above FVG"
        try:
            format_alert(tr)
        except Exception as exc:
            assert False, f"format_alert raised on malformed confirmation_level: {exc}"

    def test_no_raise_on_empty_targets(self):
        """Empty targets list must not raise."""
        tr = self._crnt_tr()
        tr["final_signal"]["targets"] = []
        try:
            format_alert(tr)
        except Exception as exc:
            assert False, f"format_alert raised on empty targets: {exc}"

    def test_no_raise_on_completely_missing_trade_location(self):
        """Absent trade_location must not raise."""
        tr = self._crnt_tr()
        tr.pop("trade_location", None)
        try:
            format_alert(tr)
        except Exception as exc:
            assert False, f"format_alert raised with no trade_location: {exc}"

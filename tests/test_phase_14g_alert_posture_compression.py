"""Phase 14G — Alert Posture Compression tests.

Text-only rendering contract: STARTER alerts read as reduced-size (never
watch-only / no-capital) while add/full-size stays blocked on 1H proof;
NEAR_ENTRY alerts keep NO CAPITAL but never duplicate the blocker into the
missing-conditions line. Structured 1H / TF evidence blocks and enum values are
preserved. No tier/capital/routing/score mutation.
"""

from src import discord_alerts as da
from src import timeframe_alignment as tfa


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _oh(state="RETEST_IN_PROGRESS", hold="HOLD_WEAK", sl="1H_TRIGGER_WEAK",
        al="WATCH_ONLY", status="ENABLED"):
    return {
        "enabled": True, "status": status, "data_freshness": "FRESH",
        "trigger_state": state, "score": 66, "score_label": sl,
        "alert_truth_label": al, "hard_caps_applied": ["NO_RETEST"],
        "pullback_retest_hold": {"retest_truth": "RETEST_REAL", "hold_truth": hold},
        "candle_truth": {"event_type": "REJECTION", "closed_candle_confirms": False},
        "location_realism": {"label": "ACCEPTABLE_BUT_NOT_IDEAL"},
        "invalidation": {"clear": True, "level": 99.5},
        "path_quality": {"path_label": "ACCEPTABLE"},
    }


def _starter_signal(**o):
    s = {
        "ticker": "HAE", "setup_family": "continuation", "structure_event": "bos",
        "trend_state": "fresh_expansion", "zone_type": "fvg", "trigger_level": 102.0,
        "invalidation_level": 99.5, "invalidation_condition": "1H close below",
        "risk_reward": 4.0, "overhead_status": "clear", "risk_realism_state": "healthy",
        "sma_value_alignment": "supportive", "retest_status": "confirmed",
        "hold_status": "confirmed", "targets": [{"label": "T1", "level": 108.0}],
        "next_action": "monitor", "reason": "BOS", "capital_action": "starter_only",
        "scan_price": 101.2,
    }
    s.update(o)
    return s


def _starter_tiering(oh=None, tf_label="HTF_ALIGNED_TRIGGER_PENDING"):
    tr = {
        "final_tier": "STARTER", "score": 80, "safe_for_alert": True,
        "capital_action": "starter_only", "final_discord_channel": "starter",
        "final_signal": _starter_signal(),
        "trade_location": {"zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
                           "location_state": "mid_zone_acceptance",
                           "confirmation_level": 102.5, "scan_price": 101.2},
        "one_hour_entry": oh if oh is not None else _oh(),
    }
    tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context("HAE", tr)
    return tr


def _near_signal(**o):
    s = {
        "ticker": "MTB", "setup_family": "continuation", "structure_event": "bos",
        "trend_state": "fresh_expansion", "zone_type": "fvg", "trigger_level": 102.0,
        "invalidation_level": 99.5, "invalidation_condition": "1H close below",
        "risk_reward": 3.6, "overhead_status": "moderate", "retest_status": "partial",
        "hold_status": "partial", "targets": [{"label": "T1", "level": 108.0}],
        "missing_conditions": [],
        "near_entry_blocker_note": (
            "Blocker: hold is not fully confirmed; "
            "wait for body-close acceptance inside/above the zone"
        ),
        "upgrade_trigger": "Body close acceptance above 102.00 with hold confirmation",
        "next_action": "monitor", "reason": "BOS", "capital_action": "wait_no_capital",
        "scan_price": 101.2,
    }
    s.update(o)
    return s


def _near_tiering(oh=None, signal_over=None):
    sig = _near_signal(**(signal_over or {}))
    tr = {
        "final_tier": "NEAR_ENTRY", "score": 70, "safe_for_alert": False,
        "capital_action": "wait_no_capital", "final_discord_channel": "near_entry",
        "final_signal": sig,
        "trade_location": {"zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
                           "location_state": "mid_zone_acceptance"},
        "one_hour_entry": oh if oh is not None else _oh(),
    }
    tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context("MTB", tr)
    return tr


# ===========================================================================
# Test 1 — STARTER pending-1H compression
# ===========================================================================

class TestStarterCompression:
    def test_starter_pending_reads_as_reduced_size(self):
        body = da.format_alert(_starter_tiering())
        assert "STARTER SIZE ONLY" in body
        assert "Starter valid" in body
        assert "reduced-size" in body

    def test_starter_pending_drops_watch_only(self):
        body = da.format_alert(_starter_tiering())
        assert "Watch-only valid" not in body
        assert "NO CAPITAL — WATCH ONLY" not in body
        assert "no capital" not in body.lower()
        assert "near-entry watch" not in body.lower()
        assert "watch-only" not in body.lower()

    def test_no_add_phrase_allowed(self):
        # "no add" / "no full-size" are legitimate STARTER language, not "no capital".
        body = da.format_alert(_starter_tiering())
        # The compression must not have stripped add-blocking language.
        assert "add" in body.lower()


# ===========================================================================
# Test 2 — STARTER still blocks add / full-size
# ===========================================================================

class TestStarterBlocksAddFullSize:
    def test_add_full_size_proof_pending(self):
        body = da.format_alert(_starter_tiering())
        assert any(p in body for p in (
            "add/full-size waits", "add waits",
            "full-size confirmation remains pending", "no add until",
        ))


# ===========================================================================
# Test 3 — NEAR_ENTRY keeps no capital and never reads as STARTER
# ===========================================================================

class TestNearEntryKeepsNoCapital:
    def test_near_entry_keeps_no_capital(self):
        body = da.format_alert(_near_tiering())
        assert "NO CAPITAL — WATCH ONLY" in body or "NO CAPITAL" in body

    def test_near_entry_never_starter(self):
        body = da.format_alert(_near_tiering())
        assert "STARTER SIZE ONLY" not in body
        assert "Starter valid" not in body


# ===========================================================================
# Test 4 — NEAR_ENTRY duplicate blocker compression
# ===========================================================================

class TestNearEntryDuplicateBlocker:
    def test_no_missing_conditions_blocker_duplicate(self):
        body = da.format_alert(_near_tiering())
        assert "Missing conditions: Blocker:" not in body
        assert "Missing proof:" in body

    def test_upgrade_and_invalidation_preserved(self):
        body = da.format_alert(_near_tiering())
        assert "Upgrade trigger:" in body
        assert "Invalidation:" in body
        assert "Blocker:" in body

    def test_clean_missing_conditions_untouched(self):
        # A non-duplicate humanized missing-conditions list must keep its label.
        body = da.format_alert(_near_tiering(signal_over={
            "missing_conditions": ["missing_retest", "missing_hold"],
            "near_entry_blocker_note": "overhead path not clean",
        }))
        assert "Missing conditions:" in body
        assert "Missing conditions: Blocker:" not in body


# ===========================================================================
# Test 5 — structured blocks preserved
# ===========================================================================

class TestStructuredBlocksPreserved:
    def test_starter_blocks_present(self):
        body = da.format_alert(_starter_tiering())
        for marker in ("1H trigger:", "1H score:", "1H truth:",
                       "TF alignment:", "TF score:", "TF stack:"):
            assert marker in body

    def test_near_blocks_present(self):
        body = da.format_alert(_near_tiering())
        for marker in ("1H trigger:", "1H score:", "1H truth:",
                       "TF alignment:", "TF score:", "TF stack:"):
            assert marker in body


# ===========================================================================
# Test 6 — no enum rewrite
# ===========================================================================

class TestNoEnumRewrite:
    def test_enums_preserved_starter(self):
        body = da.format_alert(_starter_tiering())
        for enum in ("HTF_ALIGNED_TRIGGER_PENDING", "TRIGGER_FORMING",
                     "RETEST_IN_PROGRESS", "HOLD_WEAK"):
            assert enum in body
        assert "TIMEFRAME_ALIGNMENT_BLOCK" not in body
        assert "ONE_HOUR_EVIDENCE_BLOCK" not in body

    def test_enums_preserved_near(self):
        body = da.format_alert(_near_tiering())
        assert "RETEST_IN_PROGRESS" in body
        assert "HOLD_WEAK" in body


# ===========================================================================
# Test 7 — HAE/BIRK regression
# ===========================================================================

class TestHaeBirkRegression:
    def test_hae_birk_starter_posture(self):
        for ticker in ("HAE", "BIRK"):
            tr = _starter_tiering()
            tr["final_signal"]["ticker"] = ticker
            body = da.format_alert(tr)
            assert "STARTER SIZE ONLY" in body          # starter remains starter
            assert "reduced-size" in body                # reduced-size language
            assert "Watch-only valid" not in body        # watch-only removed
            assert "Starter valid" in body
            assert "add/full-size waits" in body         # add/full-size still pending


# ===========================================================================
# Test 8 — MTB regression
# ===========================================================================

class TestMtbRegression:
    def test_mtb_near_entry_posture(self):
        body = da.format_alert(_near_tiering())
        assert "NO CAPITAL" in body                       # no capital remains
        assert "Missing conditions: Blocker:" not in body  # duplicate removed
        assert "Missing proof:" in body                    # clean missing proof
        assert "Upgrade trigger:" in body                  # upgrade preserved


# ===========================================================================
# Invariants — helpers are tier-gated and never mutate input
# ===========================================================================

class TestPostureInvariants:
    def test_starter_helper_noop_for_non_starter(self):
        body = "  Quality read: Watch-only valid — structure exists.\n"
        assert da._apply_starter_posture_compression(body, "NEAR_ENTRY", "wait_no_capital") == body
        assert da._apply_starter_posture_compression(body, "STARTER", "wait_no_capital") == body

    def test_near_helper_noop_for_non_near(self):
        body = "Missing conditions: Blocker: hold not confirmed\n"
        assert da._apply_near_entry_missing_proof_compression(body, "STARTER") == body

    def test_no_tiering_mutation(self):
        import copy
        tr = _starter_tiering()
        before = copy.deepcopy(tr)
        da.format_alert(tr)
        # Sovereign fields unchanged.
        assert tr["final_tier"] == before["final_tier"]
        assert tr["capital_action"] == before["capital_action"]
        assert tr["final_discord_channel"] == before["final_discord_channel"]
        assert tr["safe_for_alert"] == before["safe_for_alert"]
        assert tr["score"] == before["score"]

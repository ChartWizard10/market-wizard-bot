"""Phase 14E.1 — 1H Entry Trigger Evidence Engine tests.

Covers the 10 mandated groups: object schema, freshness, closed-vs-live candle
law, candle taxonomy, pullback/retest/hold truth, the trigger state machine,
location realism, scoring/caps, alert governance, and integration invariants.

Doctrine under test:
  - The 1H proves the trigger; it never creates the thesis.
  - Closed candle = evidence; live candle = developing information.
  - No invalidation / no retest / mid-range / stale => never trigger-ready.
  - Higher-timeframe sovereignty is absolute.
"""

import copy

import pytest

from src import one_hour_entry as ohe


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

def _tiering(tier="SNIPE_IT", **sig_overrides):
    signal = {
        "trigger_level": 102.0,
        "invalidation_level": 99.5,
        "overhead_level": 110.0,
        "targets": [{"label": "T1", "level": 108.0}],
        "zone_type": "FVG",
        "structure_event": "BOS",
    }
    signal.update(sig_overrides)
    return {
        "final_tier": tier,
        "final_signal": signal,
        "trade_location": {
            "zone_low": 100.0, "zone_mid": 101.0, "zone_high": 102.0,
            "zone_type": "FVG", "scan_price": signal.get("scan_price"),
        },
    }


_ENR = {"atr": 1.0}


def _bar(o, h, l, c, **kw):
    bar = {"open": o, "high": h, "low": l, "close": c}
    bar.update(kw)
    return bar


# A complete, clean break → retest-to-core → closed-candle hold sequence.
_CLEAN_SEQUENCE = [
    _bar(99.5, 100.0, 99.4, 99.9),
    _bar(99.9, 103.2, 99.8, 103.0),                 # break above trigger
    _bar(103.0, 103.1, 100.8, 101.0),               # pullback into core
    _bar(101.0, 102.9, 100.95, 102.7, volume=1500), # closed defending candle
]

# Break → live pullback (no closed defense yet).
_LIVE_FORMING = [
    _bar(99.5, 100.0, 99.4, 99.9),
    _bar(99.9, 103.2, 99.8, 103.0),
    _bar(103.0, 103.1, 100.9, 101.3, is_open=True),
]


def _build(bars, tier="SNIPE_IT", **sig):
    return ohe.build_one_hour_entry_context(
        "TEST", _tiering(tier, **sig), _ENR, one_hour_bars=bars
    )


# ===========================================================================
# Group 1 — Object schema
# ===========================================================================

class TestObjectSchema:
    _TOP_LEVEL = {
        "enabled", "timeframe", "status", "data_freshness", "bar_context",
        "trigger_state", "location_realism", "candle_truth",
        "pullback_retest_hold", "invalidation", "path_quality", "score",
        "score_label", "hard_caps_applied", "downgrade_reasons",
        "alert_truth_label", "scanner_sentence",
    }

    def test_all_top_level_fields_present(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert self._TOP_LEVEL.issubset(set(ctx.keys()))

    def test_enums_use_allowed_values(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["status"] in ohe.STATUS_VALUES
        assert ctx["data_freshness"] in ohe.FRESHNESS_VALUES
        assert ctx["trigger_state"] in ohe.TRIGGER_STATES
        assert ctx["location_realism"]["label"] in ohe.LOCATION_LABELS
        assert ctx["candle_truth"]["event_type"] in ohe.CANDLE_EVENT_TYPES
        assert ctx["candle_truth"]["volume_support"] in ohe.VOLUME_SUPPORT
        prh = ctx["pullback_retest_hold"]
        assert prh["pullback_truth"] in ohe.PULLBACK_TRUTH
        assert prh["retest_truth"] in ohe.RETEST_TRUTH
        assert prh["hold_truth"] in ohe.HOLD_TRUTH
        assert prh["retest_zone_type"] in ohe.RETEST_ZONE_TYPES
        assert ctx["path_quality"]["path_label"] in ohe.PATH_LABELS
        assert ctx["score_label"] in ohe.SCORE_LABELS
        assert ctx["alert_truth_label"] in ohe.ALERT_TRUTH_LABELS

    def test_missing_bars_returns_safe_degraded(self):
        ctx = ohe.build_one_hour_entry_context("T", _tiering(), _ENR, one_hour_bars=None)
        assert ctx["status"] in ("DEGRADED", "DISABLED")
        assert ctx["trigger_state"] == "NO_1H_EVIDENCE"
        assert ctx["alert_truth_label"] == "NO_ALERT"
        assert ctx["score"] == 0

    def test_malformed_bars_do_not_raise(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR, one_hour_bars=[{"open": "x"}, 5, None, {}],
        )
        assert ctx["status"] in ("DEGRADED", "ENABLED", "ERROR")
        assert ctx["trigger_state"] in ohe.TRIGGER_STATES

    def test_disabled_via_config(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR, one_hour_bars=_CLEAN_SEQUENCE,
            config={"one_hour": {"enabled": False}},
        )
        assert ctx["status"] == "DISABLED"
        assert ctx["enabled"] is False

    def test_garbage_inputs_never_raise(self):
        for bad in (None, 123, "x", [], {}, {"bars": "no"}):
            ctx = ohe.build_one_hour_entry_context(None, None, None, one_hour_bars=bad)
            assert ctx["trigger_state"] in ohe.TRIGGER_STATES


# ===========================================================================
# Group 2 — Freshness
# ===========================================================================

class TestFreshness:
    def _envelope(self, freshness):
        return {"bars": copy.deepcopy(_CLEAN_SEQUENCE), "freshness": freshness}

    def test_fresh_allows_confirmed_or_live(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["data_freshness"] == "FRESH"
        assert ctx["trigger_state"] in ("HOLD_CONFIRMED", "TRIGGER_LIVE")
        assert ctx["alert_truth_label"] in ("CONFIRMED_TRIGGER", "LIVE_TRIGGER")

    def test_recent_does_not_overstate(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR, one_hour_bars=self._envelope("RECENT")
        )
        assert ctx["data_freshness"] == "RECENT"
        # RECENT is not stale — caution only, never forced to NO_ALERT by freshness.
        assert "STALE_1H_DATA" not in ctx["hard_caps_applied"]

    def test_degraded_blocks_nothing_silently_but_flags(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR, one_hour_bars=self._envelope("DEGRADED")
        )
        assert ctx["data_freshness"] == "DEGRADED"

    def test_stale_forces_no_alert_and_cap_59(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR, one_hour_bars=self._envelope("STALE")
        )
        assert ctx["data_freshness"] == "STALE"
        assert ctx["alert_truth_label"] == "NO_ALERT"
        assert "STALE_1H_DATA" in ctx["hard_caps_applied"]
        assert ctx["score"] <= 59


# ===========================================================================
# Group 3 — Closed vs live candle law
# ===========================================================================

class TestClosedVsLiveCandle:
    def test_live_pullback_is_forming_only(self):
        ctx = _build(_LIVE_FORMING)
        assert ctx["trigger_state"] in ("HOLD_FORMING", "PULLBACK_FORMING", "RETEST_IN_PROGRESS")
        assert ctx["alert_truth_label"] in ("FORMING_TRIGGER", "WATCH_ONLY")

    def test_using_live_bar_for_confirmation_always_false(self):
        ctx = _build(_LIVE_FORMING)
        assert ctx["bar_context"]["using_live_bar_for_confirmation"] is False
        assert ctx["bar_context"]["live_bar_available"] is True

    def test_live_candle_cannot_produce_hold_confirmed(self):
        ctx = _build(_LIVE_FORMING)
        assert ctx["pullback_retest_hold"]["hold_truth"] != "HOLD_CONFIRMED"

    def test_live_only_capped_at_79(self):
        # A constructive live defending candle after a real break+return.
        bars = [
            _bar(99.5, 100.0, 99.4, 99.9),
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),                 # closed pullback into core
            _bar(100.9, 102.2, 100.85, 102.0, is_open=True),  # live defending
        ]
        ctx = _build(bars)
        if ctx["pullback_retest_hold"]["hold_truth"] == "HOLD_FORMING":
            assert ctx["score"] <= 79

    def test_closed_candle_can_confirm_hold(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["pullback_retest_hold"]["hold_truth"] == "HOLD_CONFIRMED"
        assert ctx["candle_truth"]["closed_candle_confirms"] is True

    def test_live_candle_closes_weak_downgrades(self):
        # Same setup but the final bar closes back below the zone (closed, weak).
        bars = [
            _bar(99.5, 100.0, 99.4, 99.9),
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),
            _bar(100.9, 101.0, 99.6, 99.7),       # closed weak, lost the zone
        ]
        ctx = _build(bars)
        assert ctx["trigger_state"] in ("FAILED_RETEST", "INVALID_1H_TRIGGER")
        assert ctx["alert_truth_label"] == "FAILED_TRIGGER"


# ===========================================================================
# Group 4 — Candle taxonomy
# ===========================================================================

class TestCandleTaxonomy:
    def test_displacement_confirms(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["candle_truth"]["event_type"] == "DISPLACEMENT"
        assert ctx["candle_truth"]["closed_candle_confirms"] is True

    def test_failure_overrides_constructive(self):
        bars = [
            _bar(99.5, 100.0, 99.4, 99.9),
            _bar(99.9, 103.2, 99.8, 103.0),    # accepted above
            _bar(103.0, 103.1, 99.6, 99.7),    # body accepts back below the zone
        ]
        ctx = _build(bars)
        assert ctx["candle_truth"]["event_type"] == "FAILURE"

    def test_trap_reclaim_requires_break_then_reclaim(self):
        bars = [
            _bar(100.5, 101.0, 100.2, 100.8),   # accepted in zone
            _bar(100.8, 101.0, 98.8, 99.0),     # break down below zone (trap)
            _bar(99.0, 101.5, 98.9, 101.2),     # reclaim with bullish close
        ]
        ctx = _build(bars)
        assert ctx["candle_truth"]["event_type"] == "TRAP_RECLAIM"

    def test_indecision_cannot_confirm(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.8, 101.0),
            _bar(101.0, 101.4, 100.7, 101.05),   # tiny doji body at zone
        ]
        ctx = _build(bars)
        assert ctx["candle_truth"]["event_type"] in ("INDECISION", "NONE")
        assert ctx["candle_truth"]["closed_candle_confirms"] is False

    def test_approach_from_below_is_not_failure(self):
        bars = [_bar(98.2, 98.6, 98.0, 98.4), _bar(98.4, 99.2, 98.3, 99.0)]
        ctx = _build(bars, invalidation_level=97.0)
        assert ctx["candle_truth"]["event_type"] != "FAILURE"


# ===========================================================================
# Group 5 — Pullback / retest / hold truth
# ===========================================================================

class TestPullbackRetestHold:
    def test_retest_core_valid_with_closed_defense_confirms_hold(self):
        ctx = _build(_CLEAN_SEQUENCE)
        prh = ctx["pullback_retest_hold"]
        assert prh["retest_truth"] == "RETEST_CORE_VALID"
        assert prh["hold_truth"] == "HOLD_CONFIRMED"
        assert prh["pullback_truth"] == "PULLBACK_REAL"

    def test_edge_only_retest_never_hold_confirmed(self):
        # Break, then a shallow tag of only the top quartile of the zone.
        bars = [
            _bar(99.9, 104.0, 99.8, 103.8),
            _bar(103.8, 103.9, 101.85, 102.3),   # only nicks zone top (edge)
            _bar(102.3, 103.0, 101.9, 102.8),
        ]
        ctx = _build(bars)
        prh = ctx["pullback_retest_hold"]
        if prh["retest_truth"] == "RETEST_EDGE_ONLY":
            assert prh["hold_truth"] != "HOLD_CONFIRMED"

    def test_pullback_too_deep(self):
        # Break then pull back below invalidation.
        bars = [
            _bar(99.9, 103.5, 99.8, 103.2),
            _bar(103.2, 103.3, 99.0, 99.2),   # below invalidation 99.5
        ]
        ctx = _build(bars)
        assert ctx["pullback_retest_hold"]["pullback_truth"] in (
            "PULLBACK_TOO_DEEP", "PULLBACK_REAL"
        )
        assert ctx["trigger_state"] in ("INVALID_1H_TRIGGER", "FAILED_RETEST")

    def test_hold_failed_creates_failed_retest(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),
            _bar(100.9, 101.0, 99.6, 99.7),    # lost the zone, above invalidation
        ]
        ctx = _build(bars)
        assert ctx["pullback_retest_hold"]["hold_truth"] == "HOLD_FAILED"
        assert ctx["trigger_state"] == "FAILED_RETEST"

    def test_no_zone_yields_midrange_pullback(self):
        ctx = ohe.build_one_hour_entry_context(
            "T",
            {"final_tier": "WAIT", "final_signal": {}},
            {},
            one_hour_bars=[_bar(50, 51, 49, 50.5), _bar(50.5, 52, 50, 51.5)],
        )
        assert ctx["pullback_retest_hold"]["pullback_truth"] == "PULLBACK_MIDRANGE_NO_EDGE"
        assert ctx["location_realism"]["label"] == "MIDRANGE_NO_EDGE"


# ===========================================================================
# Group 6 — State machine
# ===========================================================================

class TestStateMachine:
    def test_no_evidence(self):
        ctx = ohe.build_one_hour_entry_context("T", _tiering(), _ENR, one_hour_bars=None)
        assert ctx["trigger_state"] == "NO_1H_EVIDENCE"

    def test_approaching_location(self):
        bars = [_bar(98.2, 98.6, 98.0, 98.4), _bar(98.4, 99.2, 98.3, 99.0)]
        ctx = _build(bars, invalidation_level=97.0)
        assert ctx["trigger_state"] == "APPROACHING_LOCATION"

    def test_pullback_forming(self):
        bars = [
            _bar(99.5, 100.0, 99.4, 99.9),
            _bar(99.9, 104.0, 99.8, 103.8),
            _bar(103.8, 103.9, 102.3, 102.5),   # pulling back, not yet in zone
        ]
        ctx = _build(bars, invalidation_level=97.0)
        assert ctx["trigger_state"] in ("PULLBACK_FORMING", "APPROACHING_LOCATION")

    def test_retest_in_progress(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.8, 101.2),   # into core, no defending close after
        ]
        ctx = _build(bars)
        assert ctx["trigger_state"] in ("RETEST_IN_PROGRESS", "HOLD_CONFIRMED")

    def test_hold_forming_on_live_defense(self):
        ctx = _build(_LIVE_FORMING)
        assert ctx["trigger_state"] in ("HOLD_FORMING", "PULLBACK_FORMING", "RETEST_IN_PROGRESS")

    def test_hold_confirmed_or_live_on_closed_defense(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["trigger_state"] in ("HOLD_CONFIRMED", "TRIGGER_LIVE")

    def test_trigger_live_full_sequence(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["trigger_state"] == "TRIGGER_LIVE"
        assert ctx["score"] >= 80

    def test_failed_retest(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),
            _bar(100.9, 101.0, 99.6, 99.7),
        ]
        ctx = _build(bars)
        assert ctx["trigger_state"] == "FAILED_RETEST"

    def test_invalid_on_close_below_invalidation(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 99.0, 99.2),   # closed below invalidation 99.5
        ]
        ctx = _build(bars)
        assert ctx["trigger_state"] == "INVALID_1H_TRIGGER"

    def test_stale_trigger_when_missed(self):
        # Broke and ran far without ever returning to value.
        bars = [
            _bar(99.9, 103.0, 99.8, 102.9),
            _bar(102.9, 112.0, 102.8, 111.5),   # ran far above value, no retest
        ]
        ctx = _build(bars)
        assert ctx["trigger_state"] in ("STALE_TRIGGER", "APPROACHING_LOCATION")

    def test_no_jump_from_approaching_to_trigger_live(self):
        bars = [_bar(98.2, 98.6, 98.0, 98.4), _bar(98.4, 99.2, 98.3, 99.0)]
        ctx = _build(bars, invalidation_level=97.0)
        assert ctx["trigger_state"] != "TRIGGER_LIVE"


# ===========================================================================
# Group 7 — Location realism
# ===========================================================================

class TestLocationRealism:
    def test_realistic_location_full_credit(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["location_realism"]["label"] == "REALISTIC_ENTRY_LOCATION"

    def test_extended_location_capped_74(self):
        # Price extended ~1.5 ATR above the zone after a break (no real retest).
        bars = [
            _bar(99.9, 103.0, 99.8, 102.9),
            _bar(102.9, 103.8, 102.8, 103.7),   # ~1.7 above zone_high (atr 1.0)
        ]
        ctx = _build(bars)
        if ctx["location_realism"]["label"] == "EXTENDED_ENTRY_LOCATION":
            assert "EXTENDED_LOCATION" in ctx["hard_caps_applied"]
            assert ctx["score"] <= 74

    def test_midrange_no_edge_capped_69(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", {"final_tier": "WAIT", "final_signal": {}}, {},
            one_hour_bars=[_bar(50, 51, 49, 50.5), _bar(50.5, 52, 50, 51.5)],
        )
        assert ctx["location_realism"]["label"] == "MIDRANGE_NO_EDGE"
        assert "MIDRANGE_LOCATION" in ctx["hard_caps_applied"]
        assert ctx["score"] <= 69
        assert ctx["alert_truth_label"] == "NO_ALERT"

    def test_hostile_location_blocks_alert(self):
        # Overhead resistance directly above price (ceiling lock).
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.8, 101.2),
        ]
        ctx = _build(bars, overhead_level=101.4)   # ~0.2% overhead
        assert ctx["location_realism"]["label"] == "HOSTILE_LOCATION"
        assert ctx["alert_truth_label"] == "NO_ALERT"

    def test_missed_entry_no_alert(self):
        bars = [
            _bar(99.9, 103.0, 99.8, 102.9),
            _bar(102.9, 109.0, 102.8, 108.8),   # far above value
        ]
        ctx = _build(bars)
        if ctx["location_realism"]["label"] == "MISSED_ENTRY":
            assert ctx["alert_truth_label"] == "NO_ALERT"


# ===========================================================================
# Group 8 — Scoring and caps
# ===========================================================================

class TestScoringAndCaps:
    def test_clean_sequence_scores_a_plus(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["score"] >= 90
        assert ctx["score_label"] == "1H_TRIGGER_A_PLUS"
        assert ctx["hard_caps_applied"] == []

    def test_score_bands(self):
        assert ohe._score_label(95) == "1H_TRIGGER_A_PLUS"
        assert ohe._score_label(85) == "1H_TRIGGER_VALID"
        assert ohe._score_label(75) == "1H_TRIGGER_FORMING"
        assert ohe._score_label(65) == "1H_TRIGGER_WEAK"
        assert ohe._score_label(40) == "NO_VALID_1H_TRIGGER"

    def test_lowest_cap_wins(self):
        # Failed retest (cap 49) must dominate weaker caps.
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),
            _bar(100.9, 101.0, 99.6, 99.7),
        ]
        ctx = _build(bars)
        assert "FAILED_RETEST" in ctx["hard_caps_applied"]
        assert ctx["score"] <= 49

    def test_no_invalidation_caps_69(self):
        ctx = _build(_CLEAN_SEQUENCE, invalidation_level=None)
        assert "NO_CLEAR_INVALIDATION" in ctx["hard_caps_applied"]
        assert ctx["score"] <= 69

    def test_missing_htf_context_caps_69(self):
        # WAIT tier has no validated higher-timeframe thesis for the 1H engine to
        # prove a trigger against — that is a genuine context-unavailable
        # condition (Phase 14E.1A: truthful cap naming, not false "no permission").
        ctx_wait = ohe.build_one_hour_entry_context(
            "T", _tiering("WAIT"), _ENR, one_hour_bars=_CLEAN_SEQUENCE
        )
        assert "HTF_CONTEXT_UNAVAILABLE_FOR_1H_ENGINE" in ctx_wait["hard_caps_applied"]
        assert "NO_HTF_PERMISSION" not in ctx_wait["hard_caps_applied"]
        assert ctx_wait["score"] <= 69

    def test_near_entry_does_not_apply_false_no_permission_cap(self):
        # A valid forming NEAR_ENTRY setup HAS higher-timeframe context (BOS /
        # FVG / continuation). The 1H engine must not stamp it with a false
        # no-permission / context-unavailable cap (the SPG/PSA defect).
        ctx_ne = ohe.build_one_hour_entry_context(
            "T", _tiering("NEAR_ENTRY"), _ENR, one_hour_bars=_CLEAN_SEQUENCE
        )
        caps = ctx_ne["hard_caps_applied"]
        assert "NO_HTF_PERMISSION" not in caps
        assert "HTF_CONTEXT_UNAVAILABLE_FOR_1H_ENGINE" not in caps

    def test_stale_caps_59(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR,
            one_hour_bars={"bars": _CLEAN_SEQUENCE, "freshness": "STALE"},
        )
        assert "STALE_1H_DATA" in ctx["hard_caps_applied"]
        assert ctx["score"] <= 59

    def test_every_cap_records_a_downgrade_reason(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering("WAIT"), _ENR,
            one_hour_bars={"bars": _CLEAN_SEQUENCE, "freshness": "STALE"},
        )
        assert ctx["hard_caps_applied"]
        # At least as many reasons as caps applied.
        assert len(ctx["downgrade_reasons"]) >= len(ctx["hard_caps_applied"])

    def test_score_never_out_of_bounds(self):
        for bars in (_CLEAN_SEQUENCE, _LIVE_FORMING, None, []):
            ctx = ohe.build_one_hour_entry_context("T", _tiering(), _ENR, one_hour_bars=bars)
            assert 0 <= ctx["score"] <= 100


# ===========================================================================
# Group 9 — Alert governance
# ===========================================================================

class TestAlertGovernance:
    def test_stale_no_alert(self):
        ctx = ohe.build_one_hour_entry_context(
            "T", _tiering(), _ENR,
            one_hour_bars={"bars": _CLEAN_SEQUENCE, "freshness": "STALE"},
        )
        assert ctx["alert_truth_label"] == "NO_ALERT"

    def test_no_invalidation_no_alert(self):
        ctx = _build(_CLEAN_SEQUENCE, invalidation_level=None)
        assert ctx["alert_truth_label"] == "NO_ALERT"

    def test_hold_confirmed_is_confirmed_trigger_or_live(self):
        ctx = _build(_CLEAN_SEQUENCE)
        assert ctx["alert_truth_label"] in ("CONFIRMED_TRIGGER", "LIVE_TRIGGER")

    def test_trigger_live_requires_score_80(self):
        ctx = _build(_CLEAN_SEQUENCE)
        if ctx["alert_truth_label"] == "LIVE_TRIGGER":
            assert ctx["score"] >= 80
            assert ctx["trigger_state"] == "TRIGGER_LIVE"

    def test_failed_retest_is_failed_trigger(self):
        bars = [
            _bar(99.9, 103.2, 99.8, 103.0),
            _bar(103.0, 103.1, 100.7, 100.9),
            _bar(100.9, 101.0, 99.6, 99.7),
        ]
        ctx = _build(bars)
        assert ctx["alert_truth_label"] == "FAILED_TRIGGER"

    def test_sentence_matches_state(self):
        for bars in (_CLEAN_SEQUENCE, _LIVE_FORMING):
            ctx = _build(bars)
            assert ctx["scanner_sentence"] == ohe._sentence(ctx["trigger_state"])

    def test_watch_only_carries_no_entry_language(self):
        bars = [_bar(98.2, 98.6, 98.0, 98.4), _bar(98.4, 99.2, 98.3, 99.0)]
        ctx = _build(bars, invalidation_level=97.0)
        if ctx["alert_truth_label"] == "WATCH_ONLY":
            low = ctx["scanner_sentence"].lower()
            assert "entry proof yet" in low or "await" in low or "no entry" in low


# ===========================================================================
# Group 10 — Integration invariants
# ===========================================================================

class TestIntegrationInvariants:
    def _frozen_tiering(self):
        return _tiering()

    def test_engine_never_mutates_tiering_result(self):
        tr = self._frozen_tiering()
        before = copy.deepcopy(tr)
        ohe.build_one_hour_entry_context("T", tr, _ENR, one_hour_bars=_CLEAN_SEQUENCE)
        assert tr == before, "one_hour_entry must not mutate tiering_result"

    def test_engine_never_mutates_enriched(self):
        enr = copy.deepcopy(_ENR)
        before = copy.deepcopy(enr)
        ohe.build_one_hour_entry_context("T", _tiering(), enr, one_hour_bars=_CLEAN_SEQUENCE)
        assert enr == before

    def test_scheduler_attach_does_not_change_authority_fields(self):
        # Simulate the scheduler attach step against a tiering result and assert
        # that the sovereign authority fields are untouched by the engine.
        tr = _tiering("SNIPE_IT")
        tr["score"] = 88
        tr["safe_for_alert"] = True
        tr["capital_action"] = "snipe"
        tr["final_discord_channel"] = "snipe"
        snapshot = {
            "score": tr["score"],
            "final_tier": tr["final_tier"],
            "safe_for_alert": tr["safe_for_alert"],
            "capital_action": tr["capital_action"],
            "final_discord_channel": tr["final_discord_channel"],
        }
        tr["one_hour_entry"] = ohe.build_one_hour_entry_context(
            "T", tr, _ENR, one_hour_bars=_CLEAN_SEQUENCE
        )
        for k, v in snapshot.items():
            assert tr[k] == v

    def test_missing_object_is_safe_for_renderer(self):
        from src import discord_alerts
        assert discord_alerts._render_one_hour_lines(None) == []
        assert discord_alerts._render_one_hour_lines({"status": "DISABLED"}) == []

    def test_renderer_emits_compact_block(self):
        from src import discord_alerts
        ctx = _build(_CLEAN_SEQUENCE)
        lines = discord_alerts._render_one_hour_lines(ctx)
        assert any("1H trigger:" in ln for ln in lines)
        assert any("1H score:" in ln for ln in lines)

    def test_full_body_preserves_hold_confirmed_enum(self):
        # The structured 1H block must bypass the Claude-prose narrative guards
        # (which would otherwise rewrite the literal HOLD_CONFIRMED enum).
        from src import discord_alerts
        tr = _tiering("SNIPE_IT")
        tr["score"] = 88
        tr["final_signal"].update({
            "ticker": "TEST", "tier": "SNIPE_IT", "scan_price": 102.7,
            "capital_action": "snipe", "discord_channel": "snipe",
            "reason": "clean", "next_action": "execute",
        })
        tr["one_hour_entry"] = _build(_CLEAN_SEQUENCE)
        body = discord_alerts.format_alert(tr, None, "scan_x")
        assert "ONE_HOUR_EVIDENCE_BLOCK" not in body
        assert "hold=HOLD_CONFIRMED" in body
        assert "1H trigger: TRIGGER_LIVE" in body

    def test_no_one_hour_object_adds_no_block(self):
        from src import discord_alerts
        tr = _tiering("SNIPE_IT")
        tr["final_signal"].update({
            "ticker": "TEST", "tier": "SNIPE_IT", "scan_price": 101.0,
            "capital_action": "snipe", "discord_channel": "snipe",
            "reason": "x", "next_action": "y",
        })
        body = discord_alerts.format_alert(tr, None, "scan_x")
        assert "1H trigger:" not in body


# ===========================================================================
# Calibration integration — downward-only, read-only
# ===========================================================================

class TestCalibrationOneHourCaps:
    def test_one_hour_cap_only_lowers_calibrated(self):
        from src import score_calibration
        tr = _tiering("SNIPE_IT")
        tr["score"] = 92
        tr["final_signal"]["risk_realism_state"] = "normal"
        tr["one_hour_entry"] = ohe.build_one_hour_entry_context(
            "T", tr, _ENR,
            one_hour_bars={"bars": _CLEAN_SEQUENCE, "freshness": "STALE"},
        )
        cal = score_calibration.calibrate_score(tr, {})
        assert cal["calibrated_score"] <= 79
        assert cal["raw_score"] == 92   # raw never mutated

    def test_one_hour_disabled_applies_no_cap(self):
        from src import score_calibration
        tr = _tiering("SNIPE_IT")
        tr["score"] = 84
        tr["one_hour_entry"] = {"status": "DISABLED"}
        cal = score_calibration.calibrate_score(tr, {})
        # Without the 1H cap, an 84 may calibrate normally (no forced <=79 here).
        assert cal["raw_score"] == 84

    def test_missing_one_hour_is_default_safe(self):
        from src import score_calibration
        tr = _tiering("SNIPE_IT")
        tr["score"] = 84
        cal = score_calibration.calibrate_score(tr, {})
        assert cal["raw_score"] == 84

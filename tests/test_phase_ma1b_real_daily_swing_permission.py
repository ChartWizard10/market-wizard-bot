"""Phase MA-1B — Daily swing permission derived from Daily market evidence.

Closes MASTER-AUDIT-1 P1 finding D3.

Before this phase `derive_swing_timeframe` read exactly four fields —
`final_tier`, `safe_for_alert`, `capital_action`, `rejection_reason` — and no
Daily bar at all. The Daily state it produced is consumed downstream by the
capital-authoritative SNIPE ladder as Daily sponsorship, so the pipeline's own
answer was relabelled as Daily evidence and fed back in to justify that answer:

    final_tier -> "Daily permission" -> alignment -> sponsorship -> final_tier

The defect was measurable in both directions. One identical Daily chart produced
four different Daily states depending only on the tier, and one identical tier
produced PERMISSION_GRANTED across a supportive chart, a hostile chart, a
closed-failure chart and an ambiguous frame alike.

The governing law under test:

    evidence flows toward judgment; judgment never flows back as evidence
    the Daily chart authorizes the campaign, the 1H proves the entry
    only completed Daily evidence may GRANT — a live candle says "forming"
    ambiguity withholds permission; it does not invent a bearish verdict
    proven closed failure outranks live repair excitement
    missing proof is not failed proof

Daily permission is campaign sponsorship, never entry permission: GRANTED does
not mean SNIPE_IT, STARTER or safe_for_alert.
"""

import copy
import inspect
from datetime import datetime, timezone

import pytest

from src import snipe_ladder_judgment as lad
from src import timeframe_alignment as tfa


# ===========================================================================
# Fixtures — real MBT-2 / indicators schemas
# ===========================================================================

def daily(value="supportive", structure="BOS", confirmed=True,
          retest="confirmed", proof="CLOSED_CONFIRMED", status="CLOSED",
          confirmed_bars=380, withheld=0, last_close=99.5, **over):
    e = {
        "ticker": "TEST", "data_status": "OK",
        "current_price": 100.0, "last_closed_daily_close": last_close,
        "daily_bar_context": {
            "status": status,
            "status_source": ("regular_session_in_progress_et" if status == "LIVE"
                              else "prior_session_date_et"),
            "last_closed_daily_date": "2026-08-20",
            "live_daily_date": "2026-08-21" if status == "LIVE" else None,
            "live_bar_available": status == "LIVE",
            "using_live_bar_for_confirmation": False,
            "confirmed_bars": confirmed_bars, "ambiguous_rows_withheld": withheld,
            "current_row_trusted": True, "index_reordered": False,
        },
        "sma20": 96.0, "sma50": 92.0, "sma200": 80.0,
        "sma_value_alignment": value,
        "structure_event": structure, "structure_confirmed": confirmed,
        "structure_level": 98.0, "prior_structural_high": 98.0,
        "wick_only_break": False,
        "retest_status": retest, "daily_retest_proof": proof,
        "overhead_status": "clear", "atr": 2.0,
    }
    e.update(over)
    return e


def live_daily(**over):
    """Trusted LIVE frame whose CLOSED evidence cannot classify."""
    base = daily(value="unavailable", structure="none", confirmed=False,
                 retest="missing", proof="", status="LIVE",
                 live_sma_value_alignment="supportive",
                 live_structure_context={"state": "LIVE_RECLAIM_BUILDING",
                                         "level": 98.0, "confirms_structure": False},
                 live_retest_context={"live_interaction": "INSIDE_ZONE",
                                      "confirms_retest": False,
                                      "confirms_failure": False})
    base.update(over)
    return base


def tiering_result(final_tier="NEAR_ENTRY", safe=False,
                   capital_action="wait_no_capital", rejection_reason=""):
    return {
        "final_tier": final_tier, "safe_for_alert": safe,
        "capital_action": capital_action, "rejection_reason": rejection_reason,
        "final_discord_channel": "none", "score": 78,
        "final_signal": {
            "ticker": "TEST", "structure_event": "BOS",
            "trend_state": "mature_continuation", "overhead_status": "clear",
            "retest_status": "confirmed", "hold_status": "confirmed",
            "risk_reward": 6.0, "invalidation_level": 95.0,
            "invalidation_condition": "daily close below 95", "scan_price": 100.0,
            "targets": [{"label": "T1", "level": 130.0, "reason": "swing"}],
            "risk_distance_pct": 4.0, "trigger_level": 99.0,
        },
    }


def one_hour(state="HOLD_CONFIRMED", hold="HOLD_CONFIRMED",
             retest="RETEST_CORE_VALID", freshness="FRESH"):
    return {
        "status": "OK", "trigger_state": state,
        "alert_truth_label": "CONFIRMED_TRIGGER", "data_freshness": freshness,
        "score_label": "1H_TRIGGER_VALID",
        "pullback_retest_hold": {"retest_truth": retest, "hold_truth": hold},
        "path_quality": {"path_label": "CLEAN", "overhead_clear_enough": True},
        "candle_truth": {"event_type": "NONE", "closed_candle_confirms": True},
        "invalidation": {"clear": True},
        "location_realism": {"label": "REALISTIC_ENTRY_LOCATION"},
    }


def full_chain(daily_evidence, base_tier="NEAR_ENTRY", oh=None,
               loc="mid_zone_acceptance"):
    """Alignment -> ladder card -> sponsorship -> arbitration. No ladder edits."""
    caps = {"SNIPE_IT": "full_quality_allowed", "STARTER": "starter_only"}
    tr = tiering_result(base_tier, base_tier in ("SNIPE_IT", "STARTER"),
                        caps.get(base_tier, "wait_no_capital"))
    tr["one_hour_entry"] = oh if oh is not None else one_hour()
    tr["higher_timeframe_context"] = {
        "weekly_campaign_state": "HTF_CONTINUATION",
        "blocks_snipe_contextually": False, "weakens_long_setup": False,
        "context_grade": "A", "monthly_bias": "BULLISH",
    }
    tr["trade_location"] = {"location_state": loc}
    tr["timeframe_alignment"] = tfa.build_timeframe_alignment_context(
        "TEST", tr, enriched_data=daily_evidence, config={})
    card = lad._card(tr)
    ladder = lad.classify_snipe_ladder(tr)
    lad.apply_ladder_arbitration(tr, {})
    return {
        "daily_state": tr["timeframe_alignment"]["swing_timeframe"]["state"],
        "sponsorship": lad._daily_sponsorship(card),
        "basket": ladder["internal_ladder_tier"],
        "recommends": ladder["existing_final_tier_recommendation"],
        "final_tier": tr["final_tier"],
        "capital": tr["capital_action"],
        "label": tr["timeframe_alignment"]["alignment_label"],
        "score": tr["timeframe_alignment"]["alignment_score"],
    }


# ===========================================================================
# SOVEREIGNTY — no downstream judgment may change Daily permission
# ===========================================================================

_TIER_MATRIX = [
    ("SNIPE_IT", True, "full_quality_allowed", ""),
    ("STARTER", True, "starter_only", ""),
    ("STARTER", False, "starter_only", ""),
    ("NEAR_ENTRY", False, "wait_no_capital", ""),
    ("WAIT", False, "no_trade", ""),
    ("WAIT", False, "no_trade", "STARTER->WAIT: sma_value_alignment=hostile"),
    ("WAIT", False, "no_trade", "invalid geometry; reject; violation; fail"),
    ("INVALID", True, "full_quality_allowed", ""),
    ("", False, "", ""),
]


@pytest.mark.parametrize("evidence_kind,expected", [
    ("supportive", "PERMISSION_GRANTED"),
    ("hostile", "PERMISSION_DENIED"),
    ("mixed", "PERMISSION_REPAIRING"),
    ("ambiguous", "UNKNOWN"),
])
def test_daily_state_is_identical_across_every_tier(evidence_kind, expected):
    """§43 — the primary D3 closure test.

    One Daily chart, every legal tier/capital/safety/rejection permutation.
    The Daily state must not move, because none of those are Daily evidence.
    """
    ev = {
        "supportive": daily(),
        "hostile": daily(value="hostile", structure="none", confirmed=False,
                         retest="missing", proof=""),
        "mixed": daily(value="mixed"),
        "ambiguous": daily(status="UNKNOWN"),
    }[evidence_kind]

    states = set()
    for tier, safe, cap, rej in _TIER_MATRIX:
        tr = tiering_result(tier, safe, cap, rej)
        obj = tfa.build_timeframe_alignment_context(
            "TEST", tr, enriched_data=ev, config={})
        states.add(obj["swing_timeframe"]["state"])
    assert states == {expected}, f"tier changed Daily permission: {states}"


def test_daily_evidence_never_cites_tier_or_capital_language():
    """§28 — after the repair, Daily evidence may not mention downstream judgment."""
    for tier, safe, cap, rej in _TIER_MATRIX:
        sub = tfa.derive_swing_timeframe(daily())
        blob = " ".join(sub["evidence"] + sub["warnings"]).lower()
        for banned in ("final_tier", "safe_for_alert", "capital_action",
                       "rejection_reason", "snipe", "starter", "near_entry",
                       "capital", "ladder", "seal", "discord", "score"):
            assert banned not in blob, f"{banned!r} leaked into Daily evidence: {blob}"


def _field_reads(func) -> set:
    """Every dict key the function actually reads: `x.get("k")` and `x["k"]`.

    Parsed from the AST so prose in comments and docstrings — which legitimately
    names the forbidden fields in order to explain that they are NOT read —
    cannot satisfy or break the contract.
    """
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
        elif (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
              and isinstance(node.slice.value, str)):
            keys.add(node.slice.value)
    return keys


def test_daily_resolver_reads_no_downstream_judgment_field():
    """§70 — enduring architectural contract, asserted statically.

    Not a branch diff and not a text search: this asserts which dict keys the
    Daily resolver may ever read. Judgment fields are not Daily evidence.
    """
    reads = set()
    for func in (tfa.derive_swing_timeframe, tfa._daily_trust_failure,
                 tfa._live_daily_is_constructive):
        reads |= _field_reads(func)

    forbidden = {
        "final_tier", "safe_for_alert", "capital_action", "rejection_reason",
        "score", "snipe_ladder", "snipe_confirmed_seal", "snipe_gate_audit",
        "final_discord_channel", "one_hour_entry", "trade_location",
        "four_hour_operational", "timeframe_alignment", "calibration",
        "internal_ladder_tier", "original_claude_tier", "final_signal",
    }
    leaked = reads & forbidden
    assert not leaked, f"Daily resolver reads downstream judgment field(s): {sorted(leaked)}"

    # And it does read the Daily chart it claims to.
    assert {"daily_bar_context", "sma_value_alignment", "structure_event",
            "structure_confirmed", "retest_status", "daily_retest_proof",
            "last_closed_daily_close"} <= reads


def test_daily_permission_is_reproducible_from_its_own_evidence():
    """§95 I — the state is a pure function of the Daily chart."""
    ev = daily()
    first = tfa.derive_swing_timeframe(ev)["state"]
    for tier, safe, cap, rej in _TIER_MATRIX:
        assert tfa.derive_swing_timeframe(ev)["state"] == first
    assert tfa.derive_swing_timeframe(copy.deepcopy(ev))["state"] == first


@pytest.mark.parametrize("trigger_state,hold", [
    ("FAILED_RETEST", "HOLD_FAILED"),
    ("RETEST_IN_PROGRESS", "HOLD_FORMING"),
    ("HOLD_CONFIRMED", "HOLD_CONFIRMED"),
])
def test_one_hour_evidence_cannot_change_daily_permission(trigger_state, hold):
    """§57 — the 1H proves the entry. It does not authorize the campaign."""
    ev = daily()
    tr = tiering_result()
    tr["one_hour_entry"] = one_hour(state=trigger_state, hold=hold)
    obj = tfa.build_timeframe_alignment_context("TEST", tr, enriched_data=ev, config={})
    assert obj["swing_timeframe"]["state"] == "PERMISSION_GRANTED"


@pytest.mark.parametrize("loc", [
    "mid_zone_acceptance", "below_zone_failure", "above_zone_extension",
    "lower_zone_defense", "unknown",
])
def test_four_hour_evidence_cannot_change_daily_permission(loc):
    """§58 — the 4H organizes the campaign; it does not authorize it."""
    ev = daily()
    tr = tiering_result()
    tr["trade_location"] = {"location_state": loc}
    tr["four_hour_operational"] = {"structural_state": "BROKEN",
                                   "authority_mode": "SHADOW_EVIDENCE_ONLY"}
    obj = tfa.build_timeframe_alignment_context("TEST", tr, enriched_data=ev, config={})
    assert obj["swing_timeframe"]["state"] == "PERMISSION_GRANTED"


def test_ladder_result_cannot_change_daily_permission():
    """§95 H — a downstream basket is not Daily evidence."""
    ev = daily()
    for basket in ("PASS", "WATCH_C", "STARTER_B", "SNIPER_A_PLUS"):
        tr = tiering_result()
        tr["snipe_ladder"] = {"internal_ladder_tier": basket}
        tr["snipe_confirmed_seal"] = {"applied": True, "corrected_tier": "NEAR_ENTRY"}
        obj = tfa.build_timeframe_alignment_context("TEST", tr, enriched_data=ev, config={})
        assert obj["swing_timeframe"]["state"] == "PERMISSION_GRANTED"


# ===========================================================================
# DAILY EVIDENCE SENSITIVITY — the chart controls the permission
# ===========================================================================

@pytest.mark.parametrize("kwargs,expected,why", [
    (dict(), "PERMISSION_GRANTED", "supportive closed value + confirmed BOS"),
    (dict(structure="none", confirmed=False), "PERMISSION_GRANTED",
     "§48 supportive established value sponsors an ongoing campaign"),
    (dict(value="mixed"), "PERMISSION_REPAIRING",
     "§49 confirmed bullish structure + mixed value"),
    (dict(value="mixed", structure="none", confirmed=False), "PERMISSION_REPAIRING",
     "mixed closed value alone"),
    (dict(value="hostile", structure="reclaim"), "PERMISSION_REPAIRING",
     "§50 hostile value but confirmed bullish repair"),
    (dict(value="hostile", structure="none", confirmed=False), "PERMISSION_DENIED",
     "hostile closed value with no repair"),
    (dict(retest="failed"), "PERMISSION_DENIED",
     "§47 closed retest proved failed"),
    (dict(value="unavailable", structure="none", confirmed=False), "UNKNOWN",
     "nothing classifiable"),
    (dict(status="UNKNOWN"), "UNKNOWN", "§46 ambiguous provenance"),
    (dict(confirmed_bars=0), "UNKNOWN", "no confirmation-eligible bars"),
    (dict(last_close=None), "UNKNOWN", "no closed Daily close"),
])
def test_daily_evidence_controls_daily_permission(kwargs, expected, why):
    """§44 — changing only the Daily chart changes the Daily state."""
    assert tfa.derive_swing_timeframe(daily(**kwargs))["state"] == expected, why


def test_supportive_trend_without_fresh_bos_is_not_denied():
    """§48 — a healthy campaign does not need a fresh break every session.

    This is the anti-shyness guard: requiring a recent structural event to keep
    an established supportive trend legal would invent a new defect while
    fixing D3.
    """
    sub = tfa.derive_swing_timeframe(daily(structure="none", confirmed=False))
    assert sub["state"] == "PERMISSION_GRANTED"
    assert sub["blocks_trigger"] is False
    assert any("established closed value" in e for e in sub["evidence"])


def test_missing_structure_and_missing_retest_are_not_denial():
    """§25 — missing proof is not bearish proof."""
    sub = tfa.derive_swing_timeframe(
        daily(value="mixed", structure="none", confirmed=False,
              retest="missing", proof=""))
    assert sub["state"] != "PERMISSION_DENIED"


# ===========================================================================
# CANDLE / PROVENANCE TRUTH
# ===========================================================================

def test_live_evidence_alone_can_never_grant_permission():
    """§27 — the explicit invariant. Vary ONLY live fields; GRANTED is
    unreachable from any non-granted closed state."""
    live_variants = [
        dict(live_sma_value_alignment="supportive"),
        dict(live_structure_context={"state": "LIVE_RECLAIM_BUILDING",
                                     "confirms_structure": False}),
        dict(live_structure_context={"state": "LIVE_BREAK_BUILDING",
                                     "confirms_structure": False}),
        dict(live_structure_context={"state": "LIVE_ABOVE_LEVEL",
                                     "confirms_structure": False}),
        dict(live_retest_context={"live_interaction": "INSIDE_ZONE",
                                  "confirms_retest": False}),
        dict(live_sma_value_alignment="supportive",
             live_structure_context={"state": "LIVE_RECLAIM_BUILDING"},
             live_retest_context={"live_interaction": "INSIDE_ZONE"}),
    ]
    non_granted_bases = [
        daily(value="unavailable", structure="none", confirmed=False,
              retest="missing", proof="", status="LIVE"),                 # UNKNOWN
        daily(value="mixed", status="LIVE"),                              # REPAIRING
        daily(value="hostile", structure="none", confirmed=False,
              retest="missing", proof="", status="LIVE"),                 # DENIED
        daily(retest="failed", status="LIVE"),                            # DENIED
    ]
    for base in non_granted_bases:
        baseline = tfa.derive_swing_timeframe(base)["state"]
        assert baseline != "PERMISSION_GRANTED"
        for variant in live_variants:
            ev = copy.deepcopy(base)
            ev.update(variant)
            state = tfa.derive_swing_timeframe(ev)["state"]
            assert state != "PERMISSION_GRANTED", (
                f"live evidence granted permission from {baseline}: {variant}")


def test_live_constructive_attempt_reaches_forming_not_granted():
    """§25 — a developing session may say forming. It may not say confirmed."""
    sub = tfa.derive_swing_timeframe(live_daily())
    assert sub["state"] == "PERMISSION_FORMING"
    assert any("live Daily" in e for e in sub["evidence"])
    assert any("cannot grant" in w for w in sub["warnings"])


def _maturity_frame(n=240):
    """One raw Daily frame whose newest session is the decisive one.

    The penultimate session dips below value; the newest session reclaims
    decisively. So the SAME frame reads `mixed` while the newest row is still
    developing and excluded from confirmation, and `supportive` once that row
    matures into completed evidence.
    """
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range(end=pd.Timestamp("2026-08-21"), periods=n)
    base = np.linspace(50.0, 100.0, n)
    close = base.copy()
    close[-2] = base[-2] * 0.90
    close[-1] = base[-1] * 1.04
    op = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({
        "open": op, "high": np.maximum(op, close) * 1.005,
        "low": np.minimum(op, close) * 0.995, "close": close,
        "volume": np.full(n, 1_000_000.0)}, index=idx)


def test_live_to_closed_maturity_through_the_real_pipeline():
    """§45 / §9 — maturity creates authority, not excitement.

    ONE raw DataFrame. ONE final bar with one set of OHLCV values. The only
    thing that changes between the two calls is the clock: nothing in the
    enriched object is edited by hand, so the transition is the real MBT-2
    partition maturing a developing row into confirmation-eligible evidence.

    In session, the newest row is LIVE and withheld from confirmation, so the
    confirmed anchor is still the dip and the campaign has not earned a grant —
    even though the live row is visibly building a reclaim. After the close the
    very same row becomes completed evidence and the campaign is sponsored.
    """
    import yaml
    from src import indicators

    config = yaml.safe_load(
        open("config/doctrine_config.yaml"))  # real production thresholds
    df = _maturity_frame()
    frozen = df.copy(deep=True)

    in_session = indicators.enrich(
        "T", df, config, now_utc=datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc))
    post_close = indicators.enrich(
        "T", df, config, now_utc=datetime(2026, 8, 21, 20, 5, tzinfo=timezone.utc))

    # The raw market data is identical for both readings.
    pd_testing_equal = df.equals(frozen)
    assert pd_testing_equal, "the raw frame must not be mutated between clocks"
    assert in_session["current_price"] == post_close["current_price"]

    # ---- in session: the newest row is information, not confirmation -------
    live_ctx = in_session["daily_bar_context"]
    assert live_ctx["status"] == "LIVE"
    assert live_ctx["live_bar_available"] is True
    assert live_ctx["using_live_bar_for_confirmation"] is False
    live_state = tfa.derive_swing_timeframe(in_session)["state"]
    assert live_state != "PERMISSION_GRANTED", (
        "a developing row must not create closed Daily permission")

    # ---- after the close: the SAME row is now completed evidence -----------
    closed_ctx = post_close["daily_bar_context"]
    assert closed_ctx["status"] == "CLOSED"
    assert closed_ctx["live_bar_available"] is False
    assert closed_ctx["confirmed_bars"] == live_ctx["confirmed_bars"] + 1
    assert tfa.derive_swing_timeframe(post_close)["state"] == "PERMISSION_GRANTED"

    # ---- and the maturity is what moved, not a hand-edited field -----------
    assert in_session["sma_value_alignment"] != post_close["sma_value_alignment"]
    assert post_close["last_closed_daily_close"] > in_session["last_closed_daily_close"]


def test_live_row_is_never_used_for_confirmation_in_either_reading():
    """The MBT-2 permanent invariant, re-proven across the same transition."""
    import yaml
    from src import indicators

    config = yaml.safe_load(open("config/doctrine_config.yaml"))
    df = _maturity_frame()
    for clock in (datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc),
                  datetime(2026, 8, 21, 20, 5, tzinfo=timezone.utc)):
        e = indicators.enrich("T", df, config, now_utc=clock)
        assert e["daily_bar_context"]["using_live_bar_for_confirmation"] is False


def test_ambiguous_daily_frame_never_grants_and_never_fabricates_denial():
    """§46 / §15 — unknown data is not bearish market evidence."""
    for source in ("duplicate_session_dates", "future_dated_row",
                   "unparseable_index", "no_bars"):
        ev = daily(status="UNKNOWN")
        ev["daily_bar_context"]["status_source"] = source
        sub = tfa.derive_swing_timeframe(ev)
        assert sub["state"] == "UNKNOWN"
        assert sub["blocks_trigger"] is False
        assert any("not trustworthy" in w or "unavailable" in w
                   for w in sub["warnings"])


def _adverse(withheld=0, reordered=False, **kwargs):
    ev = daily(withheld=withheld, **kwargs)
    ev["daily_bar_context"]["index_reordered"] = reordered
    return ev


def test_a1_withheld_ambiguous_rows_cannot_grant_permission():
    """A1 — a row excluded as ambiguous cannot secretly help authorize a campaign.

    MBT-2A withholds the ambiguous rows, but every indicator downstream is then
    computed over a series the partition had to repair. Sovereign permission
    needs trustworthy provenance for that whole series, not just a surviving
    subset that happens to look supportive.
    """
    sub = tfa.derive_swing_timeframe(_adverse(withheld=3))
    assert sub["state"] == "UNKNOWN"
    assert sub["blocks_trigger"] is False
    assert any("ambiguous Daily row" in w for w in sub["warnings"])


def test_a2_reordered_daily_index_cannot_grant_permission():
    """A2 — a series that needed reordering is not sovereign proof."""
    sub = tfa.derive_swing_timeframe(_adverse(reordered=True))
    assert sub["state"] == "UNKNOWN"
    assert sub["blocks_trigger"] is False
    assert any("ordering required repair" in w for w in sub["warnings"])


def test_a3_both_provenance_faults_land_unknown():
    """A3 — withheld rows and a repaired ordering together."""
    sub = tfa.derive_swing_timeframe(_adverse(withheld=2, reordered=True))
    assert sub["state"] == "UNKNOWN"
    assert sub["blocks_trigger"] is False


def test_a4_untrusted_provenance_is_never_classified_bearish_either():
    """A4 — trust failure precedes market classification.

    Ambiguous provenance plus hostile-looking value must not be called DENIED:
    the scanner cannot honestly grade a series it does not trust, in either
    direction. Unknown provenance is not permission, and it is not failure.
    """
    sub = tfa.derive_swing_timeframe(
        _adverse(withheld=2, value="hostile", structure="none",
                 confirmed=False, retest="missing", proof=""))
    assert sub["state"] == "UNKNOWN"
    assert sub["state"] != "PERMISSION_DENIED"
    assert sub["blocks_trigger"] is False


def test_a5_clean_closed_provenance_still_grants():
    """A5 — the fix must not make ordinary clean frames untrusted."""
    sub = tfa.derive_swing_timeframe(_adverse())
    assert sub["state"] == "PERMISSION_GRANTED"


def test_a6_clean_live_session_with_supportive_closed_evidence_still_grants():
    """A6 — a developing candle does not demote an already-earned campaign.

    The live bar is not granting anything here; the completed Daily evidence is.
    Making every LIVE session FORMING would have recreated shyness.
    """
    sub = tfa.derive_swing_timeframe(_adverse(status="LIVE"))
    assert sub["state"] == "PERMISSION_GRANTED"
    assert any("live" in w.lower() for w in sub["warnings"])


def test_a10_ambiguity_check_never_mutates_its_input():
    """A10 — the trust boundary is read-only."""
    for ev in (_adverse(withheld=2), _adverse(reordered=True), _adverse()):
        frozen = copy.deepcopy(ev)
        tfa.derive_swing_timeframe(ev)
        assert ev == frozen


def test_ambiguous_provenance_arises_from_the_real_partition():
    """The adverse fields are not hypothetical dict shapes.

    Proven against market_data.partition_daily_bars itself: a duplicated OLDER
    session and a non-monotonic ordering both leave status CLOSED while an
    ambiguity field is adverse — which is exactly the combination that used to
    grant.
    """
    import numpy as np
    import pandas as pd
    from src import market_data

    now = datetime(2026, 8, 21, 20, 5, tzinfo=timezone.utc)

    def frame(n=200):
        idx = pd.bdate_range(end=pd.Timestamp("2026-08-20"), periods=n)
        base = np.linspace(60.0, 100.0, n)
        return pd.DataFrame({
            "open": base, "high": base * 1.01, "low": base * 0.99,
            "close": base * 1.005, "volume": np.full(n, 1_000_000.0)}, index=idx)

    base_df = frame()
    dup = base_df.copy()
    dup.index = pd.DatetimeIndex(
        [base_df.index[50] if i == 51 else d for i, d in enumerate(base_df.index)])
    ctx = market_data.partition_daily_bars(dup, now_utc=now)["context"]
    assert ctx["status"] == "CLOSED"
    assert ctx["ambiguous_rows_withheld"] > 0

    order = list(range(len(base_df)))
    order[10], order[11] = order[11], order[10]
    ctx2 = market_data.partition_daily_bars(base_df.iloc[order], now_utc=now)["context"]
    assert ctx2["status"] == "CLOSED"
    assert ctx2["index_reordered"] is True


def test_closed_failure_outranks_constructive_live_repair():
    """§26 — live repair excitement cannot erase accepted closed failure."""
    ev = daily(retest="failed", status="LIVE",
               live_sma_value_alignment="supportive",
               live_structure_context={"state": "LIVE_RECLAIM_BUILDING"},
               live_retest_context={"live_interaction": "INSIDE_ZONE"})
    sub = tfa.derive_swing_timeframe(ev)
    assert sub["state"] == "PERMISSION_DENIED"
    assert sub["blocks_trigger"] is True


def test_provisional_live_retest_is_not_closed_confirmation():
    """§51 — a partial lifted by a live touch is not closed Daily proof."""
    ev = daily(value="mixed", structure="none", confirmed=False,
               retest="partial", proof="PROVISIONAL_LIVE", status="LIVE")
    sub = tfa.derive_swing_timeframe(ev)
    assert sub["state"] != "PERMISSION_GRANTED"
    assert any("provisional" in w.lower() for w in sub["warnings"])
    assert not any("closed Daily retest" in e for e in sub["evidence"])


def test_closed_retest_states_stay_materially_distinct():
    """§52 — failed, missing, partial and confirmed are four different facts."""
    states = {
        r: tfa.derive_swing_timeframe(
            daily(value="mixed", structure="none", confirmed=False,
                  retest=r, proof="CLOSED_CONFIRMED"))["state"]
        for r in ("failed", "missing", "partial", "confirmed")
    }
    assert states["failed"] == "PERMISSION_DENIED"
    assert states["missing"] != "PERMISSION_DENIED"
    assert states["partial"] != "PERMISSION_DENIED"
    assert states["confirmed"] != "PERMISSION_DENIED"


# ===========================================================================
# CONTRACT / SAFETY
# ===========================================================================

def test_no_fake_legacy_permission_when_daily_evidence_is_absent():
    """§74 — absent evidence answers UNKNOWN, never a tier-derived fallback."""
    for missing in (None, {}, {"ticker": "TEST"}, {"daily_bar_context": {}}):
        sub = tfa.derive_swing_timeframe(missing)
        assert sub["state"] == "UNKNOWN"
        assert sub["blocks_trigger"] is False
        assert sub["warnings"]


def test_resolver_never_raises_and_never_mutates_its_input():
    """§73 / §75 — pure, deterministic, read-only, safe."""
    for ev in (daily(), live_daily(), daily(status="UNKNOWN"),
               {"daily_bar_context": {"status": "CLOSED", "confirmed_bars": "x"}},
               {"daily_bar_context": None}, {"sma_value_alignment": 5},
               {"daily_bar_context": {"status": "CLOSED", "confirmed_bars": 5},
                "last_closed_daily_close": 10.0, "structure_event": None}):
        frozen = copy.deepcopy(ev)
        sub = tfa.derive_swing_timeframe(ev)
        assert sub["state"] in tfa.DAILY_STATES
        assert ev == frozen


def test_malformed_daily_evidence_keeps_the_safe_error_contract():
    """§75 — a Daily parser problem must not grant permission or crash a scan."""
    tr = tiering_result()
    for bad in (object(), 5, "not-a-dict", [1, 2, 3]):
        obj = tfa.build_timeframe_alignment_context(
            "TEST", tr, enriched_data=bad, config={})
        assert obj["swing_timeframe"]["state"] != "PERMISSION_GRANTED"
        assert obj["status"] in tfa.STATUS_VALUES


def test_state_vocabulary_is_unchanged():
    """§19 — no sixth Daily state, no renamed field."""
    assert tfa.DAILY_STATES == {
        "PERMISSION_GRANTED", "PERMISSION_FORMING", "PERMISSION_REPAIRING",
        "PERMISSION_DENIED", "UNKNOWN",
    }
    sub = tfa.derive_swing_timeframe(daily())
    for key in ("timeframe", "role", "state", "evidence", "warnings", "blocks_trigger"):
        assert key in sub
    assert sub["timeframe"] == "1D"
    assert sub["role"] == "SWING_PERMISSION"
    assert sub["authority_source"] == "DAILY_MARKET_EVIDENCE"


def test_blocks_trigger_only_on_proven_denial():
    """§30 — UNKNOWN is not a fabricated bearish veto."""
    expected = {
        "PERMISSION_GRANTED": False, "PERMISSION_REPAIRING": False,
        "PERMISSION_FORMING": False, "UNKNOWN": False, "PERMISSION_DENIED": True,
    }
    seen = {}
    for kwargs in (dict(), dict(value="mixed"), dict(status="UNKNOWN"),
                   dict(value="hostile", structure="none", confirmed=False),
                   dict(retest="failed")):
        sub = tfa.derive_swing_timeframe(daily(**kwargs))
        seen[sub["state"]] = sub["blocks_trigger"]
    seen["PERMISSION_FORMING"] = tfa.derive_swing_timeframe(live_daily())["blocks_trigger"]
    for state, blocks in seen.items():
        assert blocks is expected[state], state


# ===========================================================================
# SCORING / LABEL DIFFERENTIALS — inputs corrected, arithmetic untouched
# ===========================================================================

def test_daily_points_and_caps_are_unchanged():
    """§31 / §32 — MA-1B changed the Daily INPUT, never the scoring table."""
    assert tfa._DAILY_POINTS == {
        "PERMISSION_GRANTED": 30, "PERMISSION_FORMING": 22,
        "PERMISSION_REPAIRING": 14, "UNKNOWN": 6, "PERMISSION_DENIED": 0,
    }
    assert tfa._CAP_DAILY_DENIED == 49


def test_score_differential_comes_only_from_the_corrected_daily_state():
    """§60 — identical Weekly/4H/1H layers; only the Daily chart differs."""
    scores = {}
    for kind, ev in (("granted", daily()),
                     ("repairing", daily(value="mixed")),
                     ("denied", daily(value="hostile", structure="none",
                                      confirmed=False, retest="missing", proof=""))):
        tr = tiering_result()
        tr["one_hour_entry"] = one_hour()
        tr["trade_location"] = {"location_state": "mid_zone_acceptance"}
        obj = tfa.build_timeframe_alignment_context(
            "TEST", tr, enriched_data=ev, config={})
        scores[kind] = (obj["swing_timeframe"]["state"], obj["alignment_score"])
    assert scores["granted"][1] > scores["repairing"][1] > scores["denied"][1]
    assert scores["denied"][1] <= tfa._CAP_DAILY_DENIED


# ===========================================================================
# FULL-CHAIN REPLAY — the ladder is untouched; it just receives true evidence
# ===========================================================================

def test_d3c_full_proof_near_entry_with_granted_daily_reaches_the_sniper_path():
    """§53 — the direct sniper route was structurally unreachable while Daily
    permission was tier-derived: a NEAR_ENTRY baseline forced PERMISSION_FORMING,
    which capped sponsorship below GRANTED, which capped the ladder below a
    sniper grade, which blocked the direct gate that requires one.

    With Daily permission sourced from the chart, a genuinely supportive Daily
    campaign grants on its own and the existing route works. No ladder rule was
    changed to obtain this.
    """
    r = full_chain(daily(), base_tier="NEAR_ENTRY")
    assert r["daily_state"] == "PERMISSION_GRANTED"
    assert r["sponsorship"] == "GRANTED"
    assert r["basket"] in ("SNIPER_A", "SNIPER_A_PLUS")
    assert r["final_tier"] == "SNIPE_IT"
    assert r["capital"] == "full_quality_allowed"


def test_hostile_daily_no_longer_receives_manufactured_sponsorship():
    """§88 — the permissiveness half of the repair.

    An upstream SNIPE_IT label used to manufacture PERMISSION_GRANTED on a
    hostile Daily chart and score the stack FULL_STACK_ALIGNED at 100.
    """
    r = full_chain(daily(value="hostile", structure="none", confirmed=False,
                         retest="missing", proof=""), base_tier="SNIPE_IT")
    assert r["daily_state"] == "PERMISSION_DENIED"
    assert r["sponsorship"] == "DENIED"
    assert r["final_tier"] != "SNIPE_IT"
    assert r["capital"] != "full_quality_allowed"
    assert r["label"] != "FULL_STACK_ALIGNED"


def test_forming_daily_does_not_authorize_full_snipe_on_1h_beauty_alone():
    """§54 — a beautiful 1H cannot promote a merely-forming Daily campaign."""
    r = full_chain(live_daily(), base_tier="NEAR_ENTRY")
    assert r["daily_state"] == "PERMISSION_FORMING"
    assert r["final_tier"] != "SNIPE_IT"
    assert r["capital"] != "full_quality_allowed"


def test_denied_daily_cannot_be_overthrown_by_the_lower_timeframes():
    """§55 — denied campaign authority survives perfect lower-timeframe proof."""
    r = full_chain(daily(retest="failed"), base_tier="SNIPE_IT")
    assert r["daily_state"] == "PERMISSION_DENIED"
    assert r["final_tier"] != "SNIPE_IT"
    assert r["capital"] != "full_quality_allowed"


def test_unknown_daily_never_masquerades_as_granted():
    """§56 — full SNIPE must not be authorized on fake Daily evidence."""
    r = full_chain(daily(status="UNKNOWN"), base_tier="SNIPE_IT")
    assert r["daily_state"] == "UNKNOWN"
    assert r["final_tier"] != "SNIPE_IT"
    assert r["capital"] != "full_quality_allowed"


@pytest.mark.parametrize("base_tier", ["SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT"])
def test_full_chain_daily_state_is_tier_independent(base_tier):
    """§59 — non-negotiable, asserted through the whole chain."""
    assert full_chain(daily(), base_tier=base_tier)["daily_state"] == "PERMISSION_GRANTED"


def test_daily_permission_is_not_entry_permission():
    """§3 — GRANTED is campaign sponsorship, never capital authorization.

    Same granted Daily chart, but the 1H trigger has failed. The downstream
    proof burden is untouched, so no capital is authorized.
    """
    r = full_chain(daily(), base_tier="NEAR_ENTRY",
                   oh=one_hour(state="FAILED_RETEST", hold="HOLD_FAILED",
                               retest="RETEST_MISSED"))
    assert r["daily_state"] == "PERMISSION_GRANTED"
    assert r["capital"] != "full_quality_allowed"

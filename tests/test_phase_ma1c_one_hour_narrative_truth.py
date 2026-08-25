"""Phase MA-1C — free-form 1H narrative sovereignty regressions.

The dedicated 1H evidence object owns trigger proof.  This suite locks the live
BAESY defect in which the structured block correctly said RETEST_IN_PROGRESS /
HOLD_WEAK while Claude prose still claimed a "confirmed retest and closed-bar
hold".

Display law only: these tests never change tier, capital, score, routing, or the
1H evidence object itself.
"""

from copy import deepcopy

import pytest

from src import discord_alerts as da


def _one_hour(
    *,
    state="RETEST_IN_PROGRESS",
    retest="RETEST_CORE_VALID",
    hold="HOLD_WEAK",
    alert="WATCH_ONLY",
    score_label="1H_TRIGGER_FORMING",
    freshness="FRESH",
):
    return {
        "status": "ENABLED",
        "data_freshness": freshness,
        "trigger_state": state,
        "score_label": score_label,
        "alert_truth_label": alert,
        "pullback_retest_hold": {
            "retest_truth": retest,
            "hold_truth": hold,
        },
    }


def _guard(text, one_hour=None):
    return da._apply_one_hour_truth_alignment_guard(
        text,
        one_hour if one_hour is not None else _one_hour(),
    )


def test_baesy_exact_claim_preserves_valid_retest_but_cools_weak_hold():
    body = (
        "Why: BOS with an unfilled bullish FVG (113.90–117.25), confirmed retest "
        "and closed-bar hold, clear overhead, and price above SMA50/SMA200."
    )
    out = _guard(body)

    assert "confirmed 1H retest; closed 1H hold still pending" in out
    assert "confirmed retest and closed-bar hold" not in out.lower()
    assert "closed-bar hold" not in out.lower()


@pytest.mark.parametrize(
    "claim",
    [
        "closed-bar hold",
        "closed bar hold",
        "closed-candle hold",
        "closed candle hold",
        "closed hold",
    ],
)
def test_closed_hold_variants_are_cooled_when_hold_is_weak(claim):
    out = _guard(f"Why: structure is valid after a {claim} at the trigger.")
    assert claim not in out.lower()
    assert "closed 1H hold still pending" in out


@pytest.mark.parametrize("claim", ["confirmed hold", "hold confirmed"])
def test_generic_confirmed_hold_claim_is_cooled_when_1h_hold_is_weak(claim):
    out = _guard(f"Why: buyers defended and {claim} at value.")
    assert claim not in out.lower()
    assert "1H hold not yet confirmed" in out


def test_valid_retest_claim_survives_when_only_hold_is_incomplete():
    out = _guard("Why: confirmed retest at the FVG; hold remains weak.")
    assert "confirmed retest" in out.lower()
    assert "1H retest not yet confirmed" not in out


@pytest.mark.parametrize("claim", ["confirmed retest", "retest confirmed"])
def test_retest_confirmation_is_cooled_when_1h_retest_is_not_proven(claim):
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    out = _guard(f"Why: {claim} at the FVG, but follow-through is pending.", oh)
    assert claim not in out.lower()
    assert "1H retest not yet confirmed" in out


def test_pair_claim_becomes_fully_incomplete_when_retest_and_hold_are_unproven():
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    out = _guard("Why: confirmed retest and closed candle hold at demand.", oh)
    assert "1H retest/hold proof remains incomplete" in out
    assert "confirmed retest" not in out.lower()
    assert "closed candle hold" not in out.lower()


def test_fully_confirmed_1h_path_is_never_overcooled():
    oh = _one_hour(
        state="HOLD_CONFIRMED",
        retest="RETEST_CORE_VALID",
        hold="HOLD_CONFIRMED",
        alert="CONFIRMED_TRIGGER",
        score_label="1H_TRIGGER_VALID",
    )
    original = "Why: confirmed retest and closed-bar hold at the FVG."
    assert _guard(original, oh) == original


def test_stale_1h_cannot_keep_confirmation_prose():
    oh = _one_hour(
        state="STALE_TRIGGER",
        retest="RETEST_CORE_VALID",
        hold="HOLD_CONFIRMED",
        alert="CONFIRMED_TRIGGER",
        score_label="1H_TRIGGER_VALID",
        freshness="STALE",
    )
    out = _guard("Why: confirmed retest and closed-bar hold at the FVG.", oh)
    assert "confirmed retest and closed-bar hold" not in out.lower()
    assert "1H retest/hold proof remains incomplete" in out


def test_structured_enum_text_is_not_rewritten_by_free_form_rules():
    body = "1H truth: retest=RETEST_CORE_VALID, hold=HOLD_WEAK, candle=NONE"
    out = _guard(body)
    assert "retest=RETEST_CORE_VALID" in out
    assert "hold=HOLD_WEAK" in out


def test_guard_does_not_mutate_one_hour_evidence_object():
    oh = _one_hour()
    before = deepcopy(oh)
    _guard("Why: confirmed retest and closed-bar hold.", oh)
    assert oh == before


# ===========================================================================
# Phase MA-1C.1 — conditional/future wording must never be inverted.
# ===========================================================================

def test_future_retest_requirement_outside_reason_is_preserved():
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    body = (
        "Next: Wait until confirmed retest before entry.\n"
        "Upgrade trigger: confirmed retest required before any capital.\n"
        "Why: confirmed retest and closed-bar hold at the FVG."
    )
    out = _guard(body, oh)

    assert "Next: Wait until confirmed retest before entry." in out
    assert "Upgrade trigger: confirmed retest required before any capital." in out
    assert "Why: 1H retest/hold proof remains incomplete" in out


def test_future_hold_requirement_outside_reason_is_preserved():
    body = (
        "Next: Wait for confirmed hold before adding size.\n"
        "Why: confirmed hold at value."
    )
    out = _guard(body)

    assert "Next: Wait for confirmed hold before adding size." in out
    assert "Why: 1H hold not yet confirmed at value." in out


def test_bare_future_retest_instruction_is_noop():
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    body = "Wait until confirmed retest before entry."
    assert _guard(body, oh) == body


def test_bare_future_hold_instruction_is_noop():
    body = "Wait for confirmed hold before adding size."
    assert _guard(body) == body


# ===========================================================================
# Phase MA-1C.1 review correction — affirmative non-Why prose stays governed.
# ===========================================================================

def test_affirmative_target_and_forced_participation_claims_are_cooled():
    body = (
        "TARGETS\n"
        "  T1: $120 — confirmed retest and closed-bar hold opens the path.\n"
        "FORCED PARTICIPATION: buyers have confirmed hold above value.\n"
        "Why: confirmed retest and closed-bar hold at the FVG."
    )
    out = _guard(body)

    assert "T1: $120 — confirmed 1H retest; closed 1H hold still pending opens the path." in out
    assert "FORCED PARTICIPATION: buyers have 1H hold not yet confirmed above value." in out
    assert "Why: confirmed 1H retest; closed 1H hold still pending at the FVG." in out


def test_all_known_conditional_fields_preserve_future_confirmation_language():
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    lines = [
        "Next: Wait until confirmed retest before entry.",
        "Blocker: confirmed hold required before capital.",
        "Missing conditions: confirmed retest; confirmed hold.",
        "Missing proof: confirmed hold.",
        "Upgrade trigger: confirmed retest and closed-bar hold required.",
        "  Promote on: confirmed retest and closed-bar hold.",
        "  Not SNIPE: full size requires confirmed hold.",
    ]
    out = _guard("\n".join(lines), oh)
    for line in lines:
        assert line in out


def test_affirmative_sequence_claim_outside_why_is_cooled():
    body = "FORCED PARTICIPATION: confirmed sequence and hold forced buyers to defend."
    out = _guard(body)
    assert "confirmed sequence and hold" not in out.lower()
    assert "structure present; 1H hold not yet confirmed" in out


def test_explicit_future_requirement_language_is_preserved_even_without_field_label():
    oh = _one_hour(retest="NONE", hold="HOLD_WEAK")
    samples = [
        "Wait until confirmed retest before entry.",
        "Full capital requires confirmed hold.",
        "Confirmed retest is required before adding size.",
        "Confirmed hold needed before promotion.",
    ]
    for body in samples:
        assert _guard(body, oh) == body

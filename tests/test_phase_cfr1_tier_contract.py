"""CFR-1 tier-contract tests.

Cross-family resolution is evidence context only. Deterministic tiering keeps
exclusive authority over capital and common active vetoes remain sovereign.
"""

from copy import deepcopy

import yaml

from src import tiering
from src.family_resolver import (
    CONFLICT_LOCAL,
    CONFLICT_SHARED,
    REL_CONFLUENT,
    REL_CONTRADICTORY,
    resolve_families,
)


def _config():
    with open("config/doctrine_config.yaml") as f:
        return yaml.safe_load(f)


def _signal(tier="STARTER"):
    return {
        "ticker": "TEST",
        "timestamp_et": "2026-08-19T10:30:00-04:00",
        "tier": tier,
        "score": 80 if tier == "STARTER" else 90,
        "setup_family": "continuation",
        "structure_event": "accepted_break",
        "trend_state": "fresh_expansion",
        "sma_value_alignment": "supportive",
        "zone_type": "support_cluster",
        "trigger_level": 100.0,
        "retest_status": "confirmed",
        "hold_status": "confirmed",
        "invalidation_condition": "below defended structure",
        "invalidation_level": 96.0,
        "targets": [{"label": "T1", "level": 112.0, "reason": "next liquidity"}],
        "risk_reward": 3.0,
        "overhead_status": "clear",
        "forced_participation": "developing",
        "missing_conditions": [],
        "upgrade_trigger": "hold above next expansion shelf",
        "next_action": "starter only" if tier == "STARTER" else "execute if live price confirms",
        "discord_channel": "#starter-signals" if tier == "STARTER" else "#snipe-signals",
        "capital_action": "starter_only" if tier == "STARTER" else "full_quality_allowed",
        "reason": "Execution sequence independently satisfies the requested tier contract.",
    }


def _pf(vetoes=None, resolution=None):
    return {
        "ticker": "TEST",
        "prefilter_score": 82,
        "veto_flags": list(vetoes or []),
        "key_features": {
            "current_price": 101.0,
            "current_open": 99.0,
            "current_high": 102.0,
            "current_low": 98.5,
            "previous_close": 99.5,
            "current_bar_direction": "green",
            "current_close_location_pct": 0.714,
            "family_resolution": resolution or {},
        },
    }


def _family(family_id, **overrides):
    obj = {
        "family_id": family_id,
        "detected": True,
        "state": "LIVE",
        "family_score": 85,
        "watch_ready": True,
        "admission_ready": True,
        "entry_structure_valid": False,
        "location_valid": True,
        "retest_state": "PENDING",
        "invalidation_level": 96.0,
        "target_1": 112.0,
        "rr_to_t1": 3.0,
        "path_status": "CLEAN",
        "blockers": [],
        "soft_caps": [],
        "metrics": {},
    }
    obj.update(overrides)
    return obj


def test_confluence_metadata_cannot_upgrade_starter_to_snipe():
    cfg = _config()
    resolution = resolve_families({
        "BREAK_RETEST_CONTINUATION": _family(
            "BREAK_RETEST_CONTINUATION",
            state="RETEST_HELD",
            family_score=92,
            entry_structure_valid=True,
            retest_state="HELD",
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            family_score=91,
            entry_structure_valid=True,
            retest_state="HELD",
        ),
    })
    assert resolution["relationship"] == REL_CONFLUENT
    assert resolution["capital_authority"] is False

    result = tiering.validate(_signal("STARTER"), _pf(resolution=resolution), cfg)
    assert result["final_tier"] == "STARTER"
    assert result["capital_action"] == "starter_only"


def test_local_sibling_failure_metadata_does_not_downgrade_valid_execution_by_itself():
    cfg = _config()
    resolution = resolve_families({
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="VALUE_RECLAIMED",
            family_score=84,
        ),
        "GAP_FILL_REVERSAL": _family(
            "GAP_FILL_REVERSAL",
            state="FAILED_ACCEPTANCE_BELOW_GAP",
            family_score=55,
            watch_ready=False,
            admission_ready=False,
            blockers=["ACCEPTED_BELOW_GAP_BOUNDARY"],
        ),
    })
    assert resolution["relationship"] == REL_CONTRADICTORY
    assert resolution["conflict_scope"] == CONFLICT_LOCAL

    result = tiering.validate(_signal("STARTER"), _pf(resolution=resolution), cfg)
    assert result["final_tier"] == "STARTER"


def test_shared_failure_metadata_alone_still_has_no_tiering_authority():
    cfg = _config()
    resolution = resolve_families({
        "VCP_BREAK_RETEST": _family("VCP_BREAK_RETEST", family_score=86),
        "BREAK_RETEST_CONTINUATION": _family(
            "BREAK_RETEST_CONTINUATION",
            state="FAILED",
            family_score=20,
            watch_ready=False,
            admission_ready=False,
            retest_state="FAILED",
            blockers=["RETEST_FAILED"],
        ),
    })
    assert resolution["relationship"] == REL_CONTRADICTORY
    assert resolution["conflict_scope"] == CONFLICT_SHARED
    assert resolution["capital_authority"] is False

    # Resolver diagnoses. Existing active veto ledger decides.
    result = tiering.validate(_signal("STARTER"), _pf(resolution=resolution), cfg)
    assert result["final_tier"] == "STARTER"


def test_existing_active_common_veto_remains_sovereign_even_with_good_family_context():
    cfg = _config()
    resolution = resolve_families({
        "VCP_BREAK_RETEST": _family(
            "VCP_BREAK_RETEST",
            state="BREAKOUT_RETEST_HELD",
            family_score=96,
            entry_structure_valid=True,
            retest_state="HELD",
        )
    })

    result = tiering.validate(
        _signal("STARTER"),
        _pf(vetoes=["no_clear_structure"], resolution=resolution),
        cfg,
    )
    assert result["final_tier"] == "WAIT"
    assert result["capital_action"] == "no_trade"


def test_resolver_metadata_is_observational_to_tiering_output_when_active_inputs_are_same():
    cfg = _config()
    base_pf = _pf()
    resolution = resolve_families({
        "BREAK_RETEST_CONTINUATION": _family(
            "BREAK_RETEST_CONTINUATION",
            state="RETEST_HELD",
            family_score=92,
            entry_structure_valid=True,
            retest_state="HELD",
        ),
        "SMA_CRADLE_CONTINUATION": _family(
            "SMA_CRADLE_CONTINUATION",
            state="CRADLE_RETEST_HELD",
            family_score=90,
            entry_structure_valid=True,
            retest_state="HELD",
        ),
    })
    with_resolution = deepcopy(base_pf)
    with_resolution["key_features"]["family_resolution"] = resolution

    a = tiering.validate(_signal("STARTER"), base_pf, cfg)
    b = tiering.validate(_signal("STARTER"), with_resolution, cfg)

    assert a["final_tier"] == b["final_tier"] == "STARTER"
    assert a["capital_action"] == b["capital_action"] == "starter_only"
    assert a["final_discord_channel"] == b["final_discord_channel"]

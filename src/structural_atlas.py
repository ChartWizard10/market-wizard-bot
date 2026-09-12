"""Read-only Structural Atlas for manual ``!analyze``.

This module exposes and normalizes evidence that the production scanner has
already computed.  It has ZERO strategy, tier, capital, routing, data-fetch,
model, state, or alert authority.

Doctrine boundary:
- Monthly/Weekly = campaign structure.
- Daily = swing permission / swing structure.
- 4H = operational evidence (respecting its reported authority_mode).
- 1H = trigger proof only.
- Horizontal structure and dynamic SMA value remain separate.
- Missing evidence remains missing; no level is invented.

The module accepts only the completed ``scheduler.run_analyze`` result and is
pure: no network, no clock, no environment, no mutation.
"""

from __future__ import annotations

import json
import math
from typing import Any


_DASH = "—"


def _d(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _price(value: Any) -> str:
    value = _num(value)
    return _DASH if value is None else f"${value:,.2f}"


def _pct(value: Any) -> str:
    value = _num(value)
    return _DASH if value is None else f"{value:.2f}%"


def _distance_pct(current: float | None, level: float | None) -> float | None:
    if current is None or level is None or current == 0:
        return None
    return round(abs(level - current) / abs(current) * 100.0, 4)


def _side(current: float | None, level: float | None) -> str:
    if current is None or level is None:
        return "UNKNOWN"
    if math.isclose(current, level, rel_tol=0.0, abs_tol=1e-9):
        return "AT_PRICE"
    return "ABOVE_PRICE" if level > current else "BELOW_PRICE"


def _extract(result: dict) -> dict:
    result = _d(result)
    tiering = _d(result.get("tiering_result"))
    return {
        "result": result,
        "tiering": tiering,
        "signal": _d(tiering.get("final_signal")),
        "enriched": _d(result.get("enriched")),
        "htf": _d(tiering.get("higher_timeframe_context")),
        "four_hour": _d(tiering.get("four_hour_operational")),
        "one_hour": _d(tiering.get("one_hour_entry")),
        "timeframe_alignment": _d(tiering.get("timeframe_alignment")),
    }


def build_structural_evidence(result: dict) -> dict:
    """Expose already-computed structural evidence without re-judging it."""
    ev = _extract(result)
    enriched = ev["enriched"]
    htf = ev["htf"]
    four = ev["four_hour"]
    one = ev["one_hour"]
    signal = ev["signal"]

    monthly = _d(htf.get("monthly"))
    weekly = _d(htf.get("weekly"))
    campaign = _d(htf.get("campaign_location"))
    htf_sequence = _d(htf.get("htf_sequence"))
    htf_setup = _d(htf.get("setup_relationship"))
    lookback = _d(htf.get("lookback"))

    four_structure = _d(four.get("structure"))
    four_liquidity = _d(four.get("liquidity"))
    four_zones = _d(four.get("zone_context"))
    four_value = _d(four.get("value_context"))
    four_volume = _d(four.get("volume_participation"))
    four_bar = _d(four.get("bar_context"))

    one_prh = _d(one.get("pullback_retest_hold"))
    one_candle = _d(one.get("candle_truth"))
    one_location = _d(one.get("location_realism"))
    one_path = _d(one.get("path_quality"))
    one_invalidation = _d(one.get("invalidation"))
    one_bar = _d(one.get("bar_context"))

    return {
        "schema_version": "14Y-1",
        "ticker": result.get("ticker"),
        "current_price": enriched.get("latest_close", signal.get("current_price")),
        "higher_timeframe": {
            "data_status": htf.get("data_status"),
            "monthly": {
                "bias_state": monthly.get("bias_state"),
                "trend_state": monthly.get("trend_state"),
                "stack_state": monthly.get("stack_state"),
                "sma_relationship": _d(monthly.get("sma_relationship")),
                "nearest_zone": monthly.get("nearest_zone"),
                "key_levels": _l(monthly.get("key_levels")),
                "support_resistance_map": _l(monthly.get("support_resistance_map")),
                "context_read": monthly.get("context_read"),
            },
            "weekly": {
                "campaign_state": weekly.get("campaign_state"),
                "trend_state": weekly.get("trend_state"),
                "stack_state": weekly.get("stack_state"),
                "sma_relationship": _d(weekly.get("sma_relationship")),
                "nearest_zone": weekly.get("nearest_zone"),
                "key_levels": _l(weekly.get("key_levels")),
                "support_resistance_map": _l(weekly.get("support_resistance_map")),
                "context_read": weekly.get("context_read"),
            },
            "campaign_location": campaign,
            "htf_sequence": htf_sequence,
            "setup_relationship": htf_setup,
            "bar_truth": {
                "current_weekly_bar_is_developing": lookback.get("current_weekly_bar_is_developing"),
                "current_monthly_bar_is_developing": lookback.get("current_monthly_bar_is_developing"),
                "last_completed_weekly_bar_date": lookback.get("last_completed_weekly_bar_date"),
                "last_completed_monthly_bar_date": lookback.get("last_completed_monthly_bar_date"),
            },
        },
        "daily": {
            "sma20": enriched.get("sma20"),
            "sma50": enriched.get("sma50"),
            "sma200": enriched.get("sma200"),
            "sma_alignment": enriched.get("sma_alignment"),
            "swing_highs": _l(enriched.get("swing_highs")),
            "swing_lows": _l(enriched.get("swing_lows")),
            "last_swing_high": enriched.get("last_swing_high"),
            "last_swing_low": enriched.get("last_swing_low"),
            "equal_highs": _l(enriched.get("equal_highs")),
            "equal_lows": _l(enriched.get("equal_lows")),
            "recent_range_high": enriched.get("recent_range_high"),
            "recent_range_low": enriched.get("recent_range_low"),
            "nearest_pool_above": enriched.get("nearest_pool_above"),
            "nearest_pool_below": enriched.get("nearest_pool_below"),
            "sweep_detected": enriched.get("sweep_detected"),
            "sweep_low": enriched.get("sweep_low"),
            "prior_low": enriched.get("prior_low"),
            "structure_event": enriched.get("structure_event"),
            "structure_level": enriched.get("structure_level"),
            "structure_confirmed": enriched.get("structure_confirmed"),
            "prior_structural_high": enriched.get("prior_structural_high"),
            "fvg": _d(enriched.get("fvg")),
            "order_block_demand": _d(enriched.get("ob")),
            "overhead_status": enriched.get("overhead_status"),
            "overhead_level": enriched.get("overhead_level"),
            "overhead_distance_pct": enriched.get("overhead_distance_pct"),
            "volume_ratio": enriched.get("volume_ratio"),
            "volume_behavior": enriched.get("volume_behavior"),
            "live_daily_volume": enriched.get("live_daily_volume"),
            "atr": enriched.get("atr"),
            "previous_close": enriched.get("previous_close"),
            "bar_context": _d(enriched.get("daily_bar_context")),
            "candidate_targets": _l(enriched.get("targets")),
            "candidate_invalidation_level": enriched.get("invalidation_level"),
            "candidate_invalidation_condition": enriched.get("invalidation_condition"),
            "candidate_estimated_rr": enriched.get("estimated_rr"),
        },
        "four_hour": {
            "status": four.get("status"),
            "authority_mode": four.get("authority_mode"),
            "structural_state": four.get("structural_state"),
            "operational_location": four.get("operational_location"),
            "operational_readiness": four.get("operational_readiness"),
            "state_confidence": four.get("state_confidence"),
            "bar_context": four_bar,
            "structure": four_structure,
            "liquidity": four_liquidity,
            "displacement": _d(four.get("displacement")),
            "retest_truth": _d(four.get("retest_truth")),
            "hold_truth": _d(four.get("hold_truth")),
            "zone_context": four_zones,
            "value_context": four_value,
            "volume_participation": four_volume,
            "invalidation_quality": _d(four.get("invalidation_quality")),
            "target_path": _d(four.get("target_path")),
            "failure_truth": _d(four.get("failure_truth")),
            "daily_relationship": four.get("daily_relationship"),
            "hard_failures": _l(four.get("hard_failures")),
            "soft_warnings": _l(four.get("soft_warnings")),
            "missing_proofs": _l(four.get("missing_proofs")),
        },
        "one_hour": {
            "status": one.get("status"),
            "freshness": one.get("data_freshness"),
            "trigger_state": one.get("trigger_state"),
            "bar_context": one_bar,
            "retest_hold": one_prh,
            "candle_truth": one_candle,
            "location_realism": one_location,
            "invalidation": one_invalidation,
            "path_quality": one_path,
            "score": one.get("score"),
            "score_label": one.get("score_label"),
            "alert_truth_label": one.get("alert_truth_label"),
            "diagnostic": one.get("scanner_sentence"),
        },
        "selected_trade_geometry": {
            "trigger_level": signal.get("trigger_level"),
            "invalidation_level": signal.get("invalidation_level"),
            "invalidation_condition": signal.get("invalidation_condition"),
            "targets": _l(signal.get("targets")),
            "risk_reward": signal.get("risk_reward"),
            "overhead_status": signal.get("overhead_status"),
            "provenance": "MODEL_SELECTED",
        },
        "known_absent_evidence": [
            "PREVIOUS_DAY_HIGH",
            "PREVIOUS_DAY_LOW",
            "PREVIOUS_WEEK_HIGH",
            "PREVIOUS_WEEK_LOW",
            "PREVIOUS_WEEK_CLOSE",
            "PREVIOUS_MONTH_HIGH",
            "PREVIOUS_MONTH_LOW",
            "PREVIOUS_MONTH_CLOSE",
            "DAILY_SMA10",
            "NATIVE_1H_SWING_RANGE_MAP",
            "MULTI_LEVEL_DETERMINISTIC_OVERHEAD_LADDER",
            "TARGET_HIT_EVENT_TRUTH",
            "INVALIDATION_TRIGGER_EVENT_TRUTH",
        ],
    }


def _swing_price(item: Any) -> float | None:
    if isinstance(item, dict):
        return _num(item.get("level", item.get("price")))
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return _num(item[1])
    return _num(item)


def _add_level(
    out: list,
    *,
    current: float | None,
    timeframe: str,
    role: str,
    structure_type: str,
    level: Any = None,
    zone_low: Any = None,
    zone_high: Any = None,
    midpoint: Any = None,
    state: str = "CONFIRMED",
    provenance: str = "DETERMINISTIC",
    confirmation_basis: str = "CLOSED",
    authority_mode: str = "EVIDENCE",
    source_path: str,
    note: Any = None,
) -> None:
    p = _num(level)
    lo = _num(zone_low)
    hi = _num(zone_high)
    mid = _num(midpoint)
    reference = p if p is not None else mid
    if reference is None and lo is not None and hi is not None:
        reference = (lo + hi) / 2.0
    if p is None and lo is None and hi is None:
        return
    out.append({
        "timeframe": timeframe,
        "role": role,
        "structure_type": structure_type,
        "price": p,
        "zone_low": lo,
        "zone_high": hi,
        "midpoint": mid,
        "side": _side(current, reference),
        "state": state,
        "distance_pct": _distance_pct(current, reference),
        "provenance": provenance,
        "confirmation_basis": confirmation_basis,
        "authority_mode": authority_mode,
        "source_path": source_path,
        "note": note,
    })


def build_level_ledger(result: dict) -> list:
    """Normalize existing levels into one provenance-rich display ledger."""
    evidence = build_structural_evidence(result)
    current = _num(evidence.get("current_price"))
    out: list[dict] = []

    # Monthly / Weekly horizontal structure from the existing HTF engine.
    for tf_key, tf_name in (("monthly", "MONTHLY"), ("weekly", "WEEKLY")):
        block = _d(evidence["higher_timeframe"].get(tf_key))
        for item in _l(block.get("key_levels")):
            item = _d(item)
            kind = str(item.get("kind") or "LEVEL").upper()
            role = "RESISTANCE" if kind == "RESISTANCE" else "SUPPORT" if kind == "SUPPORT" else "STRUCTURE"
            _add_level(
                out, current=current, timeframe=tf_name, role=role,
                structure_type="SWING_LEVEL", level=item.get("level"),
                authority_mode="CAMPAIGN_CONTEXT", source_path=f"higher_timeframe_context.{tf_key}.key_levels",
                note=item.get("date"),
            )
        zone = _d(block.get("nearest_zone"))
        if zone:
            _add_level(
                out, current=current, timeframe=tf_name,
                role=str(zone.get("type") or "STRUCTURE").upper(),
                structure_type="NEAREST_HTF_ZONE", level=zone.get("level"),
                state=str(zone.get("freshness") or "UNKNOWN").upper(),
                authority_mode="CAMPAIGN_CONTEXT", source_path=f"higher_timeframe_context.{tf_key}.nearest_zone",
                note=zone.get("zone_grade"),
            )

    dly = evidence["daily"]
    for item in _l(dly.get("swing_highs"))[-6:]:
        _add_level(out, current=current, timeframe="DAILY", role="RESISTANCE",
                   structure_type="SWING_HIGH", level=_swing_price(item),
                   authority_mode="SWING_STRUCTURE", source_path="enriched.swing_highs")
    for item in _l(dly.get("swing_lows"))[-6:]:
        _add_level(out, current=current, timeframe="DAILY", role="SUPPORT",
                   structure_type="SWING_LOW", level=_swing_price(item),
                   authority_mode="SWING_STRUCTURE", source_path="enriched.swing_lows")
    for value in _l(dly.get("equal_highs")):
        _add_level(out, current=current, timeframe="DAILY", role="LIQUIDITY",
                   structure_type="EQUAL_HIGH", level=value,
                   authority_mode="SWING_STRUCTURE", source_path="enriched.equal_highs")
    for value in _l(dly.get("equal_lows")):
        _add_level(out, current=current, timeframe="DAILY", role="LIQUIDITY",
                   structure_type="EQUAL_LOW", level=value,
                   authority_mode="SWING_STRUCTURE", source_path="enriched.equal_lows")
    for key, typ, role in (
        ("recent_range_high", "RANGE_HIGH", "RESISTANCE"),
        ("recent_range_low", "RANGE_LOW", "SUPPORT"),
        ("structure_level", "BREAK_LEVEL", "STRUCTURE"),
        ("prior_structural_high", "PRIOR_STRUCTURAL_HIGH", "RESISTANCE"),
        ("nearest_pool_above", "BUY_SIDE_POOL", "LIQUIDITY"),
        ("nearest_pool_below", "SELL_SIDE_POOL", "LIQUIDITY"),
        ("overhead_level", "OVERHEAD", "RESISTANCE"),
    ):
        _add_level(out, current=current, timeframe="DAILY", role=role,
                   structure_type=typ, level=dly.get(key), authority_mode="SWING_STRUCTURE",
                   source_path=f"enriched.{key}")

    fvg = _d(dly.get("fvg"))
    _add_level(out, current=current, timeframe="DAILY", role="ZONE", structure_type="FVG",
               zone_low=fvg.get("fvg_bot"), zone_high=fvg.get("fvg_top"), midpoint=fvg.get("fvg_mid"),
               state="FILLED" if fvg.get("fvg_filled") else "UNFILLED",
               authority_mode="SWING_STRUCTURE", source_path="enriched.fvg")
    ob = _d(dly.get("order_block_demand"))
    _add_level(out, current=current, timeframe="DAILY", role="ZONE", structure_type="DEMAND_OB",
               zone_low=ob.get("ob_lo"), zone_high=ob.get("ob_hi"), midpoint=ob.get("ob_core"),
               state="MITIGATED" if ob.get("mitigated") else "ACTIVE",
               authority_mode="SWING_STRUCTURE", source_path="enriched.ob")

    # Dynamic value is deliberately not mislabeled as horizontal support/resistance.
    for key, period in (("sma20", 20), ("sma50", 50), ("sma200", 200)):
        _add_level(out, current=current, timeframe="DAILY", role="VALUE",
                   structure_type=f"SMA_{period}", level=dly.get(key),
                   authority_mode="DYNAMIC_VALUE", source_path=f"enriched.{key}")

    for target in _l(dly.get("candidate_targets")):
        target = _d(target)
        _add_level(out, current=current, timeframe="DAILY", role="TARGET",
                   structure_type="DETERMINISTIC_CANDIDATE_TARGET", level=target.get("level"),
                   authority_mode="DISPLAY_CANDIDATE", source_path="enriched.targets",
                   note=target.get("reason"))
    _add_level(out, current=current, timeframe="DAILY", role="INVALIDATION",
               structure_type="DETERMINISTIC_CANDIDATE_INVALIDATION",
               level=dly.get("candidate_invalidation_level"), authority_mode="DISPLAY_CANDIDATE",
               source_path="enriched.invalidation_level", note=dly.get("candidate_invalidation_condition"))

    fh = evidence["four_hour"]
    fh_auth = str(fh.get("authority_mode") or "SHADOW_EVIDENCE_ONLY")
    fs = _d(fh.get("structure"))
    for item in _l(fs.get("swing_highs"))[-6:]:
        _add_level(out, current=current, timeframe="4H", role="RESISTANCE", structure_type="SWING_HIGH",
                   level=_swing_price(item), authority_mode=fh_auth,
                   source_path="four_hour_operational.structure.swing_highs")
    for item in _l(fs.get("swing_lows"))[-6:]:
        _add_level(out, current=current, timeframe="4H", role="SUPPORT", structure_type="SWING_LOW",
                   level=_swing_price(item), authority_mode=fh_auth,
                   source_path="four_hour_operational.structure.swing_lows")
    for key, typ, role in (
        ("range_high", "RANGE_HIGH", "RESISTANCE"),
        ("range_low", "RANGE_LOW", "SUPPORT"),
        ("break_level", "BREAK_LEVEL", "TRIGGER"),
        ("reclaim_level", "RECLAIM_LEVEL", "TRIGGER"),
    ):
        _add_level(out, current=current, timeframe="4H", role=role, structure_type=typ,
                   level=fs.get(key), authority_mode=fh_auth,
                   source_path=f"four_hour_operational.structure.{key}")
    fl = _d(fh.get("liquidity"))
    for key, typ in (("buyside_target", "BUY_SIDE_POOL"), ("sellside_target", "SELL_SIDE_POOL"),
                     ("prior_swing_high", "PRIOR_SWING_HIGH"), ("prior_swing_low", "PRIOR_SWING_LOW"),
                     ("swept_level", "SWEPT_LEVEL")):
        _add_level(out, current=current, timeframe="4H", role="LIQUIDITY", structure_type=typ,
                   level=fl.get(key), authority_mode=fh_auth,
                   source_path=f"four_hour_operational.liquidity.{key}", note=fl.get("sweep_state"))
    fz = _d(fh.get("zone_context"))
    fzf = _d(fz.get("fvg"))
    _add_level(out, current=current, timeframe="4H", role="ZONE", structure_type="FVG",
               zone_low=fzf.get("bottom", fzf.get("fvg_bot")), zone_high=fzf.get("top", fzf.get("fvg_top")),
               midpoint=fzf.get("midpoint", fzf.get("fvg_mid")), state=str(fz.get("fvg_state") or "UNKNOWN"),
               authority_mode=fh_auth, source_path="four_hour_operational.zone_context.fvg")
    demand = fz.get("demand_core")
    if isinstance(demand, dict):
        _add_level(out, current=current, timeframe="4H", role="ZONE", structure_type="DEMAND_CORE",
                   zone_low=demand.get("low"), zone_high=demand.get("high"), midpoint=demand.get("midpoint"),
                   authority_mode=fh_auth, source_path="four_hour_operational.zone_context.demand_core")
    else:
        _add_level(out, current=current, timeframe="4H", role="ZONE", structure_type="DEMAND_CORE",
                   level=demand, authority_mode=fh_auth, source_path="four_hour_operational.zone_context.demand_core")
    fv = _d(fh.get("value_context"))
    for key, period in (("sma10", 10), ("sma20", 20), ("sma50", 50)):
        _add_level(out, current=current, timeframe="4H", role="VALUE", structure_type=f"SMA_{period}",
                   level=fv.get(key), authority_mode=f"{fh_auth}:DYNAMIC_VALUE",
                   source_path=f"four_hour_operational.value_context.{key}")

    oh = evidence["one_hour"]
    ol = _d(oh.get("location_realism"))
    op = _d(oh.get("path_quality"))
    oi = _d(oh.get("invalidation"))
    _add_level(out, current=current, timeframe="1H", role="RESISTANCE", structure_type="NEAREST_RESISTANCE",
               level=ol.get("nearest_resistance", op.get("nearest_resistance")), authority_mode="TRIGGER_PROOF",
               source_path="one_hour_entry.location_realism/path_quality.nearest_resistance")
    _add_level(out, current=current, timeframe="1H", role="INVALIDATION", structure_type="TRIGGER_INVALIDATION",
               level=oi.get("level"), authority_mode="TRIGGER_PROOF",
               source_path="one_hour_entry.invalidation.level", note=oi.get("condition"))

    selected = evidence["selected_trade_geometry"]
    _add_level(out, current=current, timeframe="MODEL", role="TRIGGER", structure_type="SELECTED_TRIGGER",
               level=selected.get("trigger_level"), provenance="MODEL", confirmation_basis="MODEL_SELECTED",
               authority_mode="SELECTED_GEOMETRY", source_path="final_signal.trigger_level")
    _add_level(out, current=current, timeframe="MODEL", role="INVALIDATION", structure_type="SELECTED_INVALIDATION",
               level=selected.get("invalidation_level"), provenance="MODEL", confirmation_basis="MODEL_SELECTED",
               authority_mode="SELECTED_GEOMETRY", source_path="final_signal.invalidation_level",
               note=selected.get("invalidation_condition"))
    for target in _l(selected.get("targets")):
        target = _d(target)
        _add_level(out, current=current, timeframe="MODEL", role="TARGET", structure_type="SELECTED_TARGET",
                   level=target.get("level"), provenance="MODEL", confirmation_basis="MODEL_SELECTED",
                   authority_mode="SELECTED_GEOMETRY", source_path="final_signal.targets",
                   note=target.get("reason"))

    out.sort(key=lambda row: (row["distance_pct"] is None, row["distance_pct"] or 0.0,
                              row["timeframe"], row["role"], row["structure_type"]))
    return out


def build_structural_atlas(result: dict) -> dict:
    evidence = build_structural_evidence(result)
    ledger = build_level_ledger(result)
    current = _num(evidence.get("current_price"))

    horizontal = [x for x in ledger if x["role"] not in ("VALUE",)]
    value = [x for x in ledger if x["role"] == "VALUE"]
    above = [x for x in horizontal if x["side"] == "ABOVE_PRICE"]
    below = [x for x in horizontal if x["side"] == "BELOW_PRICE"]
    resistance = [x for x in above if x["role"] in ("RESISTANCE", "ZONE", "LIQUIDITY")]
    support = [x for x in below if x["role"] in ("SUPPORT", "ZONE", "LIQUIDITY")]
    buy_liq = [x for x in ledger if x["role"] == "LIQUIDITY" and x["side"] == "ABOVE_PRICE"]
    sell_liq = [x for x in ledger if x["role"] == "LIQUIDITY" and x["side"] == "BELOW_PRICE"]

    return {
        "schema_version": "14Y-1",
        "ticker": evidence.get("ticker"),
        "current_price": current,
        "evidence": evidence,
        "level_ledger": ledger,
        "horizontal_structure": {
            "nearest_resistance": resistance[0] if resistance else None,
            "nearest_support": support[0] if support else None,
            "above_price": above[:12],
            "below_price": below[:12],
        },
        "liquidity_map": {
            "nearest_buy_side": buy_liq[0] if buy_liq else None,
            "nearest_sell_side": sell_liq[0] if sell_liq else None,
            "buy_side": buy_liq[:8],
            "sell_side": sell_liq[:8],
        },
        "dynamic_value": value[:12],
        "known_absent_evidence": evidence["known_absent_evidence"],
    }


def _level_line(row: dict) -> str:
    if not row:
        return _DASH
    if row.get("price") is not None:
        p = _price(row.get("price"))
    else:
        lo, hi = _price(row.get("zone_low")), _price(row.get("zone_high"))
        p = f"{lo}–{hi}"
    dist = _pct(row.get("distance_pct"))
    return (
        f"{p} | {row.get('timeframe')} {row.get('structure_type')} | "
        f"{row.get('role')} | {dist} | {row.get('authority_mode')}"
    )


def render_structural_atlas(result: dict) -> str:
    """Render a desk-readable map; no strategy inference or promotion logic."""
    atlas = build_structural_atlas(result)
    ev = atlas["evidence"]
    htf = ev["higher_timeframe"]
    monthly = htf["monthly"]
    weekly = htf["weekly"]
    daily = ev["daily"]
    four = ev["four_hour"]
    one = ev["one_hour"]
    horizontal = atlas["horizontal_structure"]
    liq = atlas["liquidity_map"]

    lines = [
        "",
        "━" * 32,
        "STRUCTURAL ATLAS — EVIDENCE MAP",
        "━" * 32,
        f"Current price: {_price(atlas['current_price'])}",
        f"HTF data quality: {htf.get('data_status') or _DASH}",
        "",
        "CAMPAIGN STRUCTURE",
        f"  Monthly: bias={monthly.get('bias_state') or _DASH} trend={monthly.get('trend_state') or _DASH} stack={monthly.get('stack_state') or _DASH}",
        f"  Weekly:  campaign={weekly.get('campaign_state') or _DASH} trend={weekly.get('trend_state') or _DASH} stack={weekly.get('stack_state') or _DASH}",
        f"  Campaign location: {_d(htf.get('campaign_location')).get('label') or _DASH} / {_d(htf.get('campaign_location')).get('quality') or _DASH}",
        "",
        "KEY LEVEL LADDER — ABOVE PRICE",
    ]
    above = horizontal.get("above_price") or []
    lines.extend(f"  R{i}: {_level_line(row)}" for i, row in enumerate(above[:8], 1))
    if not above:
        lines.append(f"  {_DASH}")
    lines += ["", "KEY LEVEL LADDER — BELOW PRICE"]
    below = horizontal.get("below_price") or []
    lines.extend(f"  S{i}: {_level_line(row)}" for i, row in enumerate(below[:8], 1))
    if not below:
        lines.append(f"  {_DASH}")

    lines += [
        "",
        "NEAREST STRUCTURAL REFERENCES",
        f"  Resistance:      {_level_line(horizontal.get('nearest_resistance'))}",
        f"  Support:         {_level_line(horizontal.get('nearest_support'))}",
        f"  Buy-side liq:    {_level_line(liq.get('nearest_buy_side'))}",
        f"  Sell-side liq:   {_level_line(liq.get('nearest_sell_side'))}",
        "",
        "DAILY SWING / LIQUIDITY",
        f"  Last swing high: {_price(daily.get('last_swing_high'))}",
        f"  Last swing low:  {_price(daily.get('last_swing_low'))}",
        f"  Range:           {_price(daily.get('recent_range_low'))}–{_price(daily.get('recent_range_high'))}",
        f"  Pool above:      {_price(daily.get('nearest_pool_above'))}",
        f"  Pool below:      {_price(daily.get('nearest_pool_below'))}",
        f"  Sweep:           {daily.get('sweep_detected')} @ {_price(daily.get('sweep_low'))}",
        f"  Structure:       {daily.get('structure_event') or _DASH} @ {_price(daily.get('structure_level'))}",
        "",
        "ZONES",
    ]
    fvg = _d(daily.get("fvg"))
    ob = _d(daily.get("order_block_demand"))
    lines += [
        f"  Daily FVG:       {_price(fvg.get('fvg_bot'))}–{_price(fvg.get('fvg_top'))} mid={_price(fvg.get('fvg_mid'))} filled={fvg.get('fvg_filled')}",
        f"  Daily demand/OB: {_price(ob.get('ob_lo'))}–{_price(ob.get('ob_hi'))} core={_price(ob.get('ob_core'))} mitigated={ob.get('mitigated')}",
        f"  4H FVG state:    {_d(four.get('zone_context')).get('fvg_state') or _DASH}",
        f"  4H demand core:  {_d(four.get('zone_context')).get('demand_core') or _DASH}",
        "",
        "DYNAMIC VALUE — NOT HORIZONTAL STRUCTURE",
        f"  Daily SMA20/50/200: {_price(daily.get('sma20'))} / {_price(daily.get('sma50'))} / {_price(daily.get('sma200'))}",
        f"  4H SMA10/20/50:     {_price(_d(four.get('value_context')).get('sma10'))} / {_price(_d(four.get('value_context')).get('sma20'))} / {_price(_d(four.get('value_context')).get('sma50'))}",
        f"  4H value stack:      {_d(four.get('value_context')).get('stack') or _DASH}",
        "",
        "4H OPERATIONAL EVIDENCE",
        f"  Authority mode:    {four.get('authority_mode') or _DASH}",
        f"  State/location:    {four.get('structural_state') or _DASH} / {four.get('operational_location') or _DASH}",
        f"  Break/reclaim:     {_d(four.get('structure')).get('break_state') or _DASH} @ {_price(_d(four.get('structure')).get('break_level'))} / {_d(four.get('structure')).get('reclaim_state') or _DASH} @ {_price(_d(four.get('structure')).get('reclaim_level'))}",
        f"  4H range:          {_price(_d(four.get('structure')).get('range_low'))}–{_price(_d(four.get('structure')).get('range_high'))}",
        f"  Target path:       {_d(four.get('target_path')).get('path_class') or _DASH} → {_price(_d(four.get('target_path')).get('next_objective'))}",
        "",
        "1H TRIGGER PROOF",
        f"  Trigger state:     {one.get('trigger_state') or _DASH}",
        f"  Retest / hold:     {_d(one.get('retest_hold')).get('retest_truth') or _DASH} / {_d(one.get('retest_hold')).get('hold_truth') or _DASH}",
        f"  Candle:            {_d(one.get('candle_truth')).get('event_type') or _DASH}",
        f"  Path:              {_d(one.get('path_quality')).get('path_label') or _DASH}",
        "",
        "CANDIDATE VS SELECTED GEOMETRY",
        f"  Deterministic invalidation candidate: {_price(daily.get('candidate_invalidation_level'))}",
        f"  Deterministic estimated R:R:          {daily.get('candidate_estimated_rr') if daily.get('candidate_estimated_rr') is not None else _DASH}",
        f"  Model-selected trigger:               {_price(ev['selected_trade_geometry'].get('trigger_level'))}",
        f"  Model-selected invalidation:          {_price(ev['selected_trade_geometry'].get('invalidation_level'))}",
        "",
        "KNOWN ABSENT / NOT YET MODELED",
        "  " + ", ".join(atlas["known_absent_evidence"]),
        "",
        "Authority law: this Atlas is evidence/display only. It cannot change tier, score, capital, routing, or alert eligibility.",
    ]
    return "\n".join(lines)


def render_structural_atlas_json(result: dict) -> str:
    return json.dumps(build_structural_atlas(result), indent=2, default=str)

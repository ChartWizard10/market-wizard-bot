"""Trade location realism — deterministic zone-position context from existing data.

Phase 14C.1: classifies where scan price sits inside the alert's FVG/OB zone so
the desk can distinguish lower-zone defense from mid-zone acceptance from
above-zone extension. Uses only existing enriched fields (fvg, ob, atr,
current_price) — no new indicators, no new data fetch.

Ownership rules (enforced permanently):
  - PURELY informational / audit-layer.
  - NEVER mutates tiering_result or enriched.
  - NEVER affects tier, capital_action, final_discord_channel, safe_for_alert,
    suppression, dedup, or state transitions.
  - score_calibration may read the context to adjust calibrated_score only;
    tiering_result["score"] is never touched.
  - tiering.py remains the sole final authority on tier and gates.
"""

# Conservative extension threshold: price counts as "extended above zone" only
# when meaningfully past zone_high — 0.75 ATR when ATR is available, else 2.5%.
_EXTENSION_ATR_MULT = 0.75
_EXTENSION_PCT_FALLBACK = 2.5


def build_trade_location_context(
    enriched: dict | None,
    tiering_result: dict | None = None,
) -> dict:
    """Return the trade-location context dict. Never raises.

    Args:
        enriched:       indicators.enrich() output for this ticker (may be a
                        partial/error record — handled safely).
        tiering_result: validated tiering result, used only to prefer the zone
                        the final signal actually referenced and its scan price.
    """
    try:
        return _build(enriched or {}, tiering_result)
    except Exception:
        return _unknown_context()


def _unknown_context() -> dict:
    return {
        "zone_type": "unknown",
        "zone_low": None,
        "zone_mid": None,
        "zone_high": None,
        "scan_price": None,
        "position_in_zone_pct": None,
        "location_state": "unknown",
        "confirmation_level": None,
        "invalidation_distance_pct": None,
        "location_pressure": "unknown",
        "display_text": "",
        "flags": [],
    }


def _build(enriched: dict, tiering_result: dict | None) -> dict:
    final_signal = (tiering_result or {}).get("final_signal") or {}

    scan_price = _safe_float(final_signal.get("scan_price"))
    if scan_price is None:
        scan_price = _safe_float(enriched.get("current_price"))

    zone_type, zone_low, zone_mid, zone_high = _select_zone(enriched, final_signal)

    ctx = _unknown_context()
    ctx["zone_type"] = zone_type
    ctx["zone_low"] = zone_low
    ctx["zone_mid"] = zone_mid
    ctx["zone_high"] = zone_high
    ctx["scan_price"] = scan_price

    inval = _safe_float(final_signal.get("invalidation_level"))
    if inval is None:
        inval = _safe_float(enriched.get("invalidation_level"))
    if scan_price is not None and inval is not None and scan_price != 0:
        ctx["invalidation_distance_pct"] = round(
            (scan_price - inval) / scan_price * 100, 2
        )

    if (
        scan_price is None
        or zone_low is None or zone_mid is None or zone_high is None
        or zone_high <= zone_low
    ):
        return ctx

    ctx["position_in_zone_pct"] = round(
        (scan_price - zone_low) / (zone_high - zone_low) * 100, 1
    )

    atr = _safe_float(enriched.get("atr"))
    state = _classify(scan_price, zone_low, zone_mid, zone_high, atr)
    ctx["location_state"] = state
    ctx["confirmation_level"] = _confirmation_level(
        state, zone_mid, zone_high, enriched, final_signal
    )
    ctx["location_pressure"] = _pressure(state)
    ctx["display_text"] = _display_text(state, zone_low, zone_mid, zone_high)

    flags: list[str] = []
    if ctx["location_pressure"] not in ("normal", "unknown"):
        flags.append(ctx["location_pressure"])
    if ctx["confirmation_level"] is not None and ctx["confirmation_level"] > scan_price:
        flags.append("confirmation_above_price")
    ctx["flags"] = flags
    return ctx


def _select_zone(
    enriched: dict, final_signal: dict
) -> tuple[str, float | None, float | None, float | None]:
    """Pick the zone the alert is about. Prefer the final signal's zone_type."""
    fvg = enriched.get("fvg") if isinstance(enriched.get("fvg"), dict) else None
    ob = enriched.get("ob") if isinstance(enriched.get("ob"), dict) else None

    fvg_vals = None
    if fvg:
        lo, mid, hi = (
            _safe_float(fvg.get("fvg_bot")),
            _safe_float(fvg.get("fvg_mid")),
            _safe_float(fvg.get("fvg_top")),
        )
        if lo is not None and mid is not None and hi is not None:
            fvg_vals = (lo, mid, hi)

    ob_vals = None
    if ob:
        lo, mid, hi = (
            _safe_float(ob.get("ob_lo")),
            _safe_float(ob.get("ob_core")),
            _safe_float(ob.get("ob_hi")),
        )
        if lo is not None and mid is not None and hi is not None:
            ob_vals = (lo, mid, hi)

    sig_zone = str(final_signal.get("zone_type") or "").upper()
    if "FVG" in sig_zone and fvg_vals:
        return ("FVG", *fvg_vals)
    if "OB" in sig_zone and ob_vals:
        return ("OB", *ob_vals)
    if fvg_vals:
        return ("FVG", *fvg_vals)
    if ob_vals:
        return ("OB", *ob_vals)
    return ("none", None, None, None)


def _classify(
    scan_price: float,
    zone_low: float,
    zone_mid: float,
    zone_high: float,
    atr: float | None,
) -> str:
    if scan_price < zone_low:
        return "below_zone_failure"
    if scan_price < zone_mid:
        return "lower_zone_defense"
    if scan_price <= zone_high:
        return "mid_zone_acceptance"
    if atr is not None and atr > 0:
        extension_threshold = atr * _EXTENSION_ATR_MULT
    else:
        extension_threshold = zone_high * _EXTENSION_PCT_FALLBACK / 100.0
    if scan_price > zone_high + extension_threshold:
        return "above_zone_extension"
    return "upper_zone_expansion"


def _confirmation_level(
    state: str,
    zone_mid: float,
    zone_high: float,
    enriched: dict,
    final_signal: dict,
) -> float | None:
    if state == "lower_zone_defense":
        return zone_mid
    if state == "mid_zone_acceptance":
        return zone_high
    if state == "upper_zone_expansion":
        overhead = _safe_float(enriched.get("overhead_level"))
        if overhead is not None:
            return overhead
        return _first_target(final_signal) or _first_target(enriched)
    return None


def _first_target(source: dict) -> float | None:
    targets = source.get("targets")
    if isinstance(targets, list) and targets:
        first = targets[0]
        if isinstance(first, dict):
            return _safe_float(first.get("level"))
        return _safe_float(first)
    return None


def _pressure(state: str) -> str:
    return {
        "lower_zone_defense":  "low_zone_pressure",
        "mid_zone_acceptance": "normal",
        "upper_zone_expansion": "normal",
        "above_zone_extension": "extended_above_zone",
        "below_zone_failure":  "failure_risk",
    }.get(state, "unknown")


def _display_text(
    state: str, zone_low: float, zone_mid: float, zone_high: float
) -> str:
    if state == "lower_zone_defense":
        return f"lower-zone defense — confirmation above {zone_mid:.2f}."
    if state == "mid_zone_acceptance":
        return f"mid-zone acceptance — next proof above {zone_high:.2f}."
    if state == "upper_zone_expansion":
        return f"upper-zone expansion above {zone_high:.2f}."
    if state == "above_zone_extension":
        return f"extended above zone high {zone_high:.2f} — chase risk."
    if state == "below_zone_failure":
        return f"below zone low {zone_low:.2f} — failure risk."
    return ""


def describe_level_direction(scan_price, level, label: str) -> str:
    """Directionally honest wording for a price level relative to scan price.

    A level above the current price is something to reclaim/accept above —
    never something to "dip toward". A level below is a pullback target.
    Returns "" when inputs are unusable.
    """
    sp = _safe_float(scan_price)
    lv = _safe_float(level)
    if sp is None or lv is None:
        return ""
    if lv > sp:
        return f"watch for reclaim/acceptance above {label} at {lv:.2f}"
    if lv < sp:
        return f"watch for defended pullback toward {label} at {lv:.2f}"
    return f"watch for continued acceptance at {label} near {lv:.2f}"


def _safe_float(val) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:                                   # NaN guard
        return None
    return f

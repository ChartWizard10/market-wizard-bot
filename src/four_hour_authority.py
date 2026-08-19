"""Phase R4H-2 — real 4H operational authority handoff.

R4H-1 proved the actual session-aligned 4H chart in shadow. R4H-2 makes that
chart authoritative for the scanner's OPERATIONAL layer without allowing 4H
to grant Daily permission or 1H to create the thesis.

Authority law:

    Monthly/Weekly = context/campaign
    Daily          = swing permission
    REAL 4H        = operational location / repair / entry neighborhood
    1H             = trigger proof

Trust law:
  - closed + COMPLETE + fresh real 4H evidence may govern the operational layer;
  - a developing 4H candle is information only and cannot create confirmation;
  - stale, insufficient, degraded, malformed, gapped, incomplete or ambiguous
    4H evidence is UNTRUSTED for capital authority;
  - missing proof is not failed proof: untrusted data lands at NEAR_ENTRY/no
    capital, not at a fabricated market-failure verdict;
  - a trusted HOSTILE/MID_RANGE real 4H location may block execution because
    that is chart evidence, not a data-quality failure;
  - the legacy Phase-14F proxy is retained as a comparison/rollback diagnostic,
    but it cannot overrule trusted real 4H evidence while authority is enabled.

This module is pure except ``enforce_operational_capital_floor``, which is an
explicit fail-closed execution barrier. The barrier can only REMOVE capital.
It never promotes, never creates levels, never changes market evidence and never
calls a provider.
"""

from __future__ import annotations

from copy import deepcopy

AUTHORITY_VERSION = "R4H-2"
AUTHORITY_MODE = "REAL_4H_OPERATIONAL_AUTHORITY"
PROXY_MODE = "PHASE_14F_PROXY_ROLLBACK_ONLY"

TRUSTED = "TRUSTED"
UNTRUSTED = "UNTRUSTED"
DISABLED = "DISABLED"

_DEGRADED_LATEST = {"INCOMPLETE", "AMBIGUOUS", "MISSING"}
_TRUSTED_FRESHNESS = {"CLOSED", "LIVE"}
_TRUSTED_STATUS = {"ENABLED"}


def _s(value) -> str:
    return str(value or "").upper().strip()


def _d(obj, key) -> dict:
    value = obj.get(key) if isinstance(obj, dict) else None
    return value if isinstance(value, dict) else {}


def authority_enabled(config) -> bool:
    """Runtime rollback switch. Default is ON once R4H-2 is deployed."""
    try:
        cfg = (config or {}).get("timeframe_alignment") or {}
        return cfg.get("real_4h_authority_enabled", True) is not False
    except Exception:
        # Unknown config state must not silently disable the production authority.
        return True


def _proxy_state(proxy_layer) -> str:
    if isinstance(proxy_layer, dict):
        return _s(proxy_layer.get("state")) or "UNKNOWN"
    return "UNKNOWN"


def _trust_reasons(real_obj) -> tuple[bool, list[str]]:
    """Return whether real 4H evidence is eligible to govern capital context."""
    real = real_obj if isinstance(real_obj, dict) else {}
    bc = _d(real, "bar_context")
    reasons: list[str] = []

    if _s(real.get("status")) not in _TRUSTED_STATUS:
        reasons.append(f"status={_s(real.get('status')) or 'MISSING'}")
    if bc.get("closed_bar_available") is not True:
        reasons.append("no closed 4H evidence")
    if bc.get("last_closed_source_complete") is not True:
        reasons.append("last closed 4H bucket incomplete")
    if bc.get("history_gap_detected") is True:
        reasons.append("4H sequential history contains an evidence gap")

    freshness = _s(bc.get("freshness_status"))
    if freshness not in _TRUSTED_FRESHNESS:
        reasons.append(f"freshness={freshness or 'UNKNOWN'}")

    latest = _s(bc.get("latest_bucket_status"))
    if latest in _DEGRADED_LATEST:
        reasons.append(f"latest expected 4H bucket={latest}")

    # The R4H-1 builder requires a contiguous minimum before status ENABLED,
    # but repeat the invariant here so authority never depends on that internal
    # implementation detail remaining unchanged.
    try:
        segment = int(bc.get("structural_segment_bars") or 0)
    except (TypeError, ValueError):
        segment = 0
    if segment < 12:
        reasons.append(f"contiguous confirmed 4H history={segment} < 12")

    return (not reasons, reasons)


def _map_real_state(real_obj) -> tuple[str, bool, list[str]]:
    """Map trusted R4H evidence into the existing Phase-14F operational enum.

    Returns ``(state, blocks_trigger, evidence)``. Favorable LOCATION_VALID is
    deliberately stricter than merely being geographically DEFENDABLE: the real
    4H retest and hold must themselves be confirmed by closed evidence. A
    defendable but still-forming base maps to LOCATION_REPAIRING, preserving the
    user's STARTER-vs-full-size distinction instead of forcing binary perfection.
    """
    real = real_obj if isinstance(real_obj, dict) else {}
    location = _s(real.get("operational_location"))
    structural = _s(real.get("structural_state"))
    retest = _s(_d(real, "retest_truth").get("state"))
    hold = _s(_d(real, "hold_truth").get("state"))
    failure = _s(_d(real, "failure_truth").get("state"))

    evidence = [
        f"real_4h.location={location or 'UNKNOWN'}",
        f"real_4h.structure={structural or 'UNKNOWN'}",
        f"real_4h.retest={retest or 'UNKNOWN'}",
        f"real_4h.hold={hold or 'UNKNOWN'}",
    ]

    if failure == "ACCEPTED_FAILURE" or structural == "FAILURE" or location == "HOSTILE":
        return "LOCATION_HOSTILE", True, evidence

    # MID_RANGE is not bearish structure, but it is execution-hostile because
    # there is no edge. That keeps the semantic distinction in the evidence text.
    if location == "MID_RANGE":
        evidence.append("real 4H mid-range has no operational edge")
        return "LOCATION_HOSTILE", True, evidence

    if location == "EXTENDED":
        return "LOCATION_EXTENDED", False, evidence

    if location == "REPAIRING":
        return "LOCATION_REPAIRING", False, evidence

    if location == "DEFENDABLE":
        if retest in {"CONFIRMED", "CORE_VALID"} and hold == "CONFIRMED":
            return "LOCATION_VALID", False, evidence
        evidence.append("defendable location, but closed 4H retest/hold proof is still forming")
        return "LOCATION_REPAIRING", False, evidence

    return "UNKNOWN", False, evidence


def build_operational_authority(real_obj, proxy_layer=None, config=None) -> dict:
    """Build the R4H-2 authority object. Pure and never raises."""
    try:
        proxy = deepcopy(proxy_layer) if isinstance(proxy_layer, dict) else {}
        proxy_state = _proxy_state(proxy)

        if not authority_enabled(config):
            return {
                "authority_version": AUTHORITY_VERSION,
                "authority_mode": PROXY_MODE,
                "authority_status": DISABLED,
                "authority_usable": False,
                "capital_floor_cleared": True,
                "state": proxy_state,
                "blocks_trigger": bool(proxy.get("blocks_trigger", False)),
                "blocks_capital": False,
                "evidence": list(proxy.get("evidence") or []),
                "warnings": ["real 4H authority disabled by rollback switch"],
                "trust_failures": [],
                "proxy_state": proxy_state,
                "proxy_layer": proxy,
                "real_state": _s((real_obj or {}).get("operational_location")),
                "real_structural_state": _s((real_obj or {}).get("structural_state")),
            }

        trusted, trust_failures = _trust_reasons(real_obj)
        if not trusted:
            return {
                "authority_version": AUTHORITY_VERSION,
                "authority_mode": AUTHORITY_MODE,
                "authority_status": UNTRUSTED,
                "authority_usable": False,
                "capital_floor_cleared": False,
                "state": "UNKNOWN",
                "blocks_trigger": False,
                "blocks_capital": True,
                "evidence": [],
                "warnings": [
                    "real 4H authority unavailable; proxy retained for diagnosis only"
                ],
                "trust_failures": trust_failures,
                "proxy_state": proxy_state,
                "proxy_layer": proxy,
                "real_state": _s((real_obj or {}).get("operational_location")),
                "real_structural_state": _s((real_obj or {}).get("structural_state")),
            }

        state, blocks_trigger, evidence = _map_real_state(real_obj)
        if state == "UNKNOWN":
            # Technically fresh data with an unclassifiable location is still not
            # proof for capital. Unknown evidence is not permission.
            return {
                "authority_version": AUTHORITY_VERSION,
                "authority_mode": AUTHORITY_MODE,
                "authority_status": UNTRUSTED,
                "authority_usable": False,
                "capital_floor_cleared": False,
                "state": "UNKNOWN",
                "blocks_trigger": False,
                "blocks_capital": True,
                "evidence": evidence,
                "warnings": ["real 4H evidence is fresh but operational location is unclassified"],
                "trust_failures": ["operational_location=UNKNOWN"],
                "proxy_state": proxy_state,
                "proxy_layer": proxy,
                "real_state": _s((real_obj or {}).get("operational_location")),
                "real_structural_state": _s((real_obj or {}).get("structural_state")),
            }

        return {
            "authority_version": AUTHORITY_VERSION,
            "authority_mode": AUTHORITY_MODE,
            "authority_status": TRUSTED,
            "authority_usable": True,
            "capital_floor_cleared": True,
            "state": state,
            "blocks_trigger": blocks_trigger,
            "blocks_capital": False,
            "evidence": evidence,
            "warnings": [],
            "trust_failures": [],
            "proxy_state": proxy_state,
            "proxy_layer": proxy,
            "real_state": _s((real_obj or {}).get("operational_location")),
            "real_structural_state": _s((real_obj or {}).get("structural_state")),
        }
    except Exception as exc:  # pragma: no cover - fail closed
        return {
            "authority_version": AUTHORITY_VERSION,
            "authority_mode": AUTHORITY_MODE,
            "authority_status": UNTRUSTED,
            "authority_usable": False,
            "capital_floor_cleared": False,
            "state": "UNKNOWN",
            "blocks_trigger": False,
            "blocks_capital": True,
            "evidence": [],
            "warnings": [f"real 4H authority evaluation error: {type(exc).__name__}"],
            "trust_failures": ["authority evaluation failed"],
            "proxy_state": _proxy_state(proxy_layer),
            "proxy_layer": deepcopy(proxy_layer) if isinstance(proxy_layer, dict) else {},
            "real_state": "UNKNOWN",
            "real_structural_state": "UNKNOWN",
        }


def operational_layer(authority_obj) -> dict:
    """Convert an authority object to the canonical timeframe-alignment layer."""
    auth = authority_obj if isinstance(authority_obj, dict) else {}
    return {
        "timeframe": "4H",
        "role": "OPERATIONAL_LOCATION",
        "state": _s(auth.get("state")) or "UNKNOWN",
        "evidence": list(auth.get("evidence") or []),
        "warnings": list(auth.get("warnings") or []) + [
            f"4H authority={_s(auth.get('authority_status')) or 'UNKNOWN'}; "
            f"proxy={_s(auth.get('proxy_state')) or 'UNKNOWN'}"
        ],
        "blocks_trigger": bool(auth.get("blocks_trigger", False)),
        "authority_mode": auth.get("authority_mode"),
        "authority_status": auth.get("authority_status"),
        "authority_usable": auth.get("authority_usable") is True,
        "blocks_capital": auth.get("blocks_capital") is True,
        "proxy_state": auth.get("proxy_state"),
    }


def _capital_standing(result) -> bool:
    if not isinstance(result, dict):
        return False
    return _s(result.get("final_tier")) in {"STARTER", "SNIPE_IT"} or str(
        result.get("capital_action") or ""
    ) in {"starter_only", "full_quality_allowed"}


def _land_near_entry(result, reason: str) -> None:
    """Canonical no-capital landing. Direct writes are deliberate fail-closed safety."""
    from src import tiering

    channel = tiering.CHANNEL_MAP.get("NEAR_ENTRY", "none")
    capital = tiering.CAPITAL_MAP.get("NEAR_ENTRY", "wait_no_capital")
    result["final_tier"] = "NEAR_ENTRY"
    result["final_discord_channel"] = channel
    result["capital_action"] = capital
    result["safe_for_alert"] = True

    signal = result.get("final_signal")
    if isinstance(signal, dict):
        signal["tier"] = "NEAR_ENTRY"
        signal["discord_channel"] = channel
        signal["capital_action"] = capital
        try:
            signal["sanitized_reason"] = tiering._sanitize_reason_for_tier(
                signal.get("reason"), "NEAR_ENTRY"
            )
            signal["sanitized_next_action"] = tiering._sanitize_reason_for_tier(
                signal.get("next_action"), "NEAR_ENTRY"
            )
            signal["near_entry_blocker_note"] = tiering._build_near_entry_blocker_note(
                signal, signal.get("scan_price")
            )
        except Exception:
            pass

    notes = result.get("downgrades")
    if not isinstance(notes, list):
        notes = []
    notes.append(f"R4H-2 operational capital floor: {reason}")
    result["downgrades"] = notes


def enforce_operational_capital_floor(tiering_result, config=None):
    """Fail closed when real 4H authority is required but untrusted.

    This is path-independent: if STARTER/SNIPE capital is standing after ladder
    arbitration and the real 4H authority cannot prove itself usable, capital is
    withdrawn to NEAR_ENTRY. It never promotes. When the rollback switch is OFF,
    the legacy proxy remains authoritative and this barrier is intentionally inert.
    """
    try:
        if not isinstance(tiering_result, dict):
            return tiering_result
        if not authority_enabled(config):
            return tiering_result
        auth = tiering_result.get("four_hour_authority")
        auth = auth if isinstance(auth, dict) else {}
        cleared = auth.get("capital_floor_cleared") is True and auth.get("authority_usable") is True
        if _capital_standing(tiering_result) and not cleared:
            failures = list(auth.get("trust_failures") or [])
            reason = "; ".join(str(x) for x in failures[:4]) or "real 4H authority not proven"
            _land_near_entry(tiering_result, reason)
            auth["capital_floor_enforced"] = True
            auth["capital_floor_reason"] = reason
        else:
            auth["capital_floor_enforced"] = False
            auth["capital_floor_reason"] = None
        tiering_result["four_hour_authority"] = auth
    except Exception as exc:  # pragma: no cover - emergency barrier
        # A fault in the capital-safety evaluator must never leave capital standing.
        if isinstance(tiering_result, dict) and _capital_standing(tiering_result):
            try:
                _land_near_entry(
                    tiering_result,
                    f"R4H-2 authority enforcement fault: {type(exc).__name__}",
                )
            except Exception:
                # Last resort: primitive direct no-capital state.
                tiering_result["final_tier"] = "NEAR_ENTRY"
                tiering_result["capital_action"] = "wait_no_capital"
                tiering_result["final_discord_channel"] = "#near-entry-watch"
                tiering_result["safe_for_alert"] = True
        return tiering_result
    return tiering_result

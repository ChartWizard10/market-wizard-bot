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
  - a trusted REPAIRING location may support reduced-size STARTER capital but
    cannot authorize full SNIPE size;
  - a trusted EXTENDED location is not a new-entry neighborhood and therefore
    cannot authorize fresh capital;
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
_CAP_REAL_4H_UNTRUSTED = 59


def _s(value) -> str:
    return str(value or "").upper().strip()


def _d(obj, key) -> dict:
    value = obj.get(key) if isinstance(obj, dict) else None
    return value if isinstance(value, dict) else {}


def authority_enabled(config) -> bool:
    """Runtime rollback switch.

    R4H-2 is explicit opt-in so isolated legacy/unit configs preserve Phase-14F
    proxy behavior. Production doctrine_config explicitly sets the flag True.
    """
    try:
        cfg = (config or {}).get("timeframe_alignment") or {}
        return cfg.get("real_4h_authority_enabled") is True
    except Exception:
        return False


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

    try:
        segment = int(bc.get("structural_segment_bars") or 0)
    except (TypeError, ValueError):
        segment = 0
    if segment < 12:
        reasons.append(f"contiguous confirmed 4H history={segment} < 12")

    return (not reasons, reasons)


def _map_real_state(real_obj) -> tuple[str, bool, list[str]]:
    """Map trusted R4H evidence into the existing operational-location enum.

    Favorable LOCATION_VALID is deliberately stricter than merely being
    geographically DEFENDABLE: real 4H retest and hold must themselves be
    confirmed by closed evidence. A defendable but still-forming base maps to
    LOCATION_REPAIRING, preserving STARTER-vs-full-size distinction.
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


def reconcile_timeframe_alignment(tfa_obj, tiering_result, authority_obj, config=None) -> dict:
    """Replace Phase-14F proxy operation with R4H-2 real operation and re-grade.

    The legacy timeframe-alignment builder is deliberately left intact as the
    rollback calculator. This reconciler runs immediately after real-4H truth is
    attached and recomputes every downstream alignment field using the real 4H
    operational layer. No stale proxy score/label/conflict survives.
    """
    try:
        if not authority_enabled(config):
            return deepcopy(tfa_obj) if isinstance(tfa_obj, dict) else tfa_obj

        from src import timeframe_alignment as tfa

        obj = deepcopy(tfa_obj) if isinstance(tfa_obj, dict) else tfa.default_timeframe_alignment_object()
        if obj.get("enabled") is False or str(obj.get("status") or "").upper() == "DISABLED":
            return obj

        authority = authority_obj if isinstance(authority_obj, dict) else {}
        proxy = deepcopy(obj.get("operational_timeframe") or {})
        operational = operational_layer(authority)

        obj["operational_proxy_timeframe"] = proxy
        obj["operational_timeframe"] = operational
        obj["operational_authority"] = {
            "authority_version": authority.get("authority_version"),
            "authority_mode": authority.get("authority_mode"),
            "authority_status": authority.get("authority_status"),
            "authority_usable": authority.get("authority_usable") is True,
            "blocks_capital": authority.get("blocks_capital") is True,
            "proxy_state": authority.get("proxy_state"),
            "real_state": authority.get("real_state"),
        }

        weekly = obj.get("campaign_timeframe") or tfa._blank_layer("1W", "CAMPAIGN_CONTEXT")
        daily = obj.get("swing_timeframe") or tfa._blank_layer("1D", "SWING_PERMISSION")
        trigger = obj.get("trigger_timeframe") or tfa._blank_layer("1H", "TRIGGER_PROOF")
        layers = {"1W": weekly, "1D": daily, "4H": operational, "1H": trigger}

        result = tiering_result if isinstance(tiering_result, dict) else {}
        signal = result.get("final_signal") or {}
        signal = signal if isinstance(signal, dict) else {}
        one_hour = result.get("one_hour_entry") or {}
        one_hour = one_hour if isinstance(one_hour, dict) else {}
        final_tier = _s(result.get("final_tier"))
        capital_action = str(result.get("capital_action") or "").lower().strip()

        missing = [
            str(x) for x in (obj.get("missing_context") or [])
            if "4h operational" not in str(x).lower()
        ]
        if operational.get("authority_usable") is not True:
            failures = list(authority.get("trust_failures") or [])
            detail = "; ".join(str(x) for x in failures[:3])
            msg = "real 4H operational authority unavailable"
            if detail:
                msg += f": {detail}"
            missing.append(msg)
        elif operational.get("state") == "UNKNOWN":
            missing.append("real 4H operational location unavailable")
        obj["missing_context"] = missing

        conflicts = tfa._detect_conflicts(
            layers, final_tier, capital_action, signal, one_hour
        )
        if operational.get("blocks_capital") and capital_action in {"starter_only", "full_quality_allowed"}:
            conflicts.append({
                "layer": "4H",
                "reason": "real 4H authority untrusted while capital action implies entry",
            })
        obj["conflicts"] = conflicts

        obj["status"] = "DEGRADED" if missing else "ENABLED"
        classifiable = sum(1 for layer in layers.values() if layer.get("state") != "UNKNOWN")
        label = tfa.classify_alignment_label(layers, conflicts, classifiable)
        obj["alignment_label"] = label

        raw_score = tfa.score_alignment(layers)
        invalidation_clear = tfa._has_clear_invalidation(signal, one_hour)
        caps, cap_reasons = tfa._collect_alignment_caps(
            layers, label, conflicts, invalidation_clear
        )
        if operational.get("blocks_capital"):
            caps["REAL_4H_AUTHORITY_UNTRUSTED"] = _CAP_REAL_4H_UNTRUSTED
            cap_reasons.append(
                "REAL_4H_AUTHORITY_UNTRUSTED: real 4H evidence is not trusted "
                f"for capital authority (cap {_CAP_REAL_4H_UNTRUSTED})"
            )

        capped = tfa.apply_alignment_caps(raw_score, caps)
        obj["alignment_score"] = capped
        obj["alignment_grade"] = tfa.grade_from_score(capped)
        obj["hard_caps_applied"] = list(caps.keys())
        obj["downgrade_reasons"] = list(cap_reasons)
        obj["scanner_sentence"] = tfa.build_scanner_sentence(label)
        return obj
    except Exception as exc:  # pragma: no cover - fail closed evidence object
        try:
            from src import timeframe_alignment as tfa
            obj = tfa.degraded_timeframe_alignment_object(
                f"R4H-2 alignment reconciliation error: {type(exc).__name__}"
            )
            obj["hard_caps_applied"] = ["REAL_4H_AUTHORITY_UNTRUSTED"]
            return obj
        except Exception:
            return {
                "enabled": True,
                "status": "ERROR",
                "alignment_label": "INSUFFICIENT_CONTEXT",
                "alignment_score": 0,
                "alignment_grade": "UNKNOWN",
                "operational_timeframe": operational_layer({}),
                "hard_caps_applied": ["REAL_4H_AUTHORITY_UNTRUSTED"],
                "downgrade_reasons": ["R4H-2 alignment reconciliation failed"],
            }


def _capital_standing(result) -> bool:
    if not isinstance(result, dict):
        return False
    return _s(result.get("final_tier")) in {"STARTER", "SNIPE_IT"} or str(
        result.get("capital_action") or ""
    ) in {"starter_only", "full_quality_allowed"}


def _apply_tier_landing(result, target_tier: str, reason: str) -> None:
    """Apply canonical existing tier maps for a downward-only safety landing."""
    from src import tiering

    target = _s(target_tier)
    if target not in {"STARTER", "NEAR_ENTRY"}:
        target = "NEAR_ENTRY"
    channel = tiering.CHANNEL_MAP.get(target, "none")
    capital = tiering.CAPITAL_MAP.get(target, "wait_no_capital")
    result["final_tier"] = target
    result["final_discord_channel"] = channel
    result["capital_action"] = capital
    result["safe_for_alert"] = target != "WAIT"

    signal = result.get("final_signal")
    if isinstance(signal, dict):
        signal["tier"] = target
        signal["discord_channel"] = channel
        signal["capital_action"] = capital
        try:
            signal["sanitized_reason"] = tiering._sanitize_reason_for_tier(
                signal.get("reason"), target
            )
            signal["sanitized_next_action"] = tiering._sanitize_reason_for_tier(
                signal.get("next_action"), target
            )
            if target == "NEAR_ENTRY":
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


def _capital_floor_landing(tiering_result, authority) -> tuple[str | None, str | None]:
    """Return downward landing tier + reason, or (None, None) when capital may stand."""
    if not _capital_standing(tiering_result):
        return None, None

    if authority.get("authority_usable") is not True or authority.get("capital_floor_cleared") is not True:
        failures = list(authority.get("trust_failures") or [])
        reason = "; ".join(str(x) for x in failures[:4]) or "real 4H authority not proven"
        return "NEAR_ENTRY", reason

    state = _s(authority.get("state"))
    final_tier = _s(tiering_result.get("final_tier"))

    if state == "LOCATION_VALID":
        return None, None

    if state == "LOCATION_REPAIRING":
        if final_tier == "SNIPE_IT" or str(tiering_result.get("capital_action") or "") == "full_quality_allowed":
            return "STARTER", "real 4H location is repairing; reduced-size capital only"
        return None, None

    if state == "LOCATION_EXTENDED":
        return "NEAR_ENTRY", "real 4H location is extended; no fresh chase capital"

    if state == "LOCATION_HOSTILE":
        return "NEAR_ENTRY", "real 4H location is hostile/no-edge for new long capital"

    return "NEAR_ENTRY", f"real 4H operational state {state or 'UNKNOWN'} is not capital-authorized"


def enforce_operational_capital_floor(tiering_result, config=None):
    """Path-independent R4H-2 capital safety after ladder arbitration.

    - untrusted/unknown/extended/hostile real 4H -> NEAR_ENTRY / no capital;
    - repairing real 4H -> STARTER maximum;
    - valid real 4H -> this floor does not change the tier.

    The function can only maintain or reduce capital. Rollback mode is inert.
    """
    try:
        if not isinstance(tiering_result, dict):
            return tiering_result
        if not authority_enabled(config):
            return tiering_result

        authority = tiering_result.get("four_hour_authority")
        authority = authority if isinstance(authority, dict) else {}
        target, reason = _capital_floor_landing(tiering_result, authority)
        if target:
            _apply_tier_landing(tiering_result, target, reason or "real 4H capital floor")
            authority["capital_floor_enforced"] = True
            authority["capital_floor_reason"] = reason
            authority["capital_floor_landing"] = target
        else:
            authority["capital_floor_enforced"] = False
            authority["capital_floor_reason"] = None
            authority["capital_floor_landing"] = None
        tiering_result["four_hour_authority"] = authority
        return tiering_result
    except Exception as exc:  # pragma: no cover - emergency fail-closed barrier
        if isinstance(tiering_result, dict) and _capital_standing(tiering_result):
            try:
                _apply_tier_landing(
                    tiering_result,
                    "NEAR_ENTRY",
                    f"R4H-2 authority enforcement fault: {type(exc).__name__}",
                )
            except Exception:
                tiering_result["final_tier"] = "NEAR_ENTRY"
                tiering_result["capital_action"] = "wait_no_capital"
                tiering_result["final_discord_channel"] = "#near-entry-watch"
                tiering_result["safe_for_alert"] = True
        return tiering_result

"""Phase 14M — SNIPE_CONFIRMED consistency seal.

A final, pre-alert truth seal. The scanner must never emit SNIPE_IT / FULL
QUALITY / full_quality_allowed / #snipe routing while its own evidence still
contains an active SNIPE blocker (a blocked gate, a missing proof, a blocked
score, a live-edge candle veto, a weak hold, a retest in progress, an
unresolved candle, or an HTF contextual block).

Phase 14L hunts the inverse (a clean setup that was NOT promoted). Phase 14M
fixes false promotion: a setup promoted to SNIPE_IT while active blockers
remain. It is the execution-side counterpart to the Phase 14K audit seal.

Doctrine (permanent):
  - This seal only ever DOWNGRADES. It never promotes, never loosens SNIPE_IT,
    never weakens STARTER/NEAR_ENTRY/WAIT discipline, never invents a tier.
  - It preserves every piece of raw evidence: raw_snipe_score, blocked_gates,
    missing_proofs, score_blocked_by, and the full snipe_gate_audit organ stay
    intact. It records WHY it acted; it never deletes the contradiction.
  - When it corrects a false SNIPE it reuses the existing tier machinery
    (tiering.CHANNEL_MAP / tiering.CAPITAL_MAP / the existing reason sanitizer
    and NEAR_ENTRY blocker-note builder) so routing, capital, and wording stay
    consistent with the rest of the system.
  - Detection reads STRUCTURED fields first (authoritative), hard text second.
    It never treats a promotion_trigger (guidance like "avoid body close below
    invalidation") as a blocker.
  - Pure stdlib; never raises (the scheduler also guards the call).

No new indicators. No external/environment inputs. Chart/evidence truth only.
"""

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# capital_action values that grant full SNIPE-size capital.
_FULL_SNIPE_CAPITAL = {"full_quality_allowed", "full_snipe", "full", "snipe"}

# Gate names whose BLOCK means the setup actually FAILED (not merely "forming").
# A false SNIPE carrying one of these is downgraded to WAIT, not NEAR_ENTRY.
_HARD_FAILURE_GATES = {
    "ONE_H_TRIGGER_CONFIRMED", "HOLD_CONFIRMED", "RETEST_CONFIRMED",
    "ACCEPTANCE_CONFIRMED", "BREAK_CONFIRMED", "NO_REACCEPTANCE_FAILURE",
    "ASYMMETRY_VALID", "DAILY_PERMISSION_GRANTED", "FOUR_H_LOCATION_VALID",
}

# one_hour_entry.trigger_state values that prove the trigger is not confirmed.
_BLOCKING_TRIGGER_STATES = {
    "RETEST_IN_PROGRESS", "HOLD_FORMING", "PULLBACK_FORMING",
    "APPROACHING_LOCATION", "FAILED_RETEST", "INVALID_1H_TRIGGER",
    "STALE_TRIGGER", "NO_1H_EVIDENCE",
}
_HARD_TRIGGER_STATES = {"FAILED_RETEST", "INVALID_1H_TRIGGER", "STALE_TRIGGER", "NO_1H_EVIDENCE"}

# pullback_retest_hold.hold_truth values that prove the hold is not confirmed.
_BLOCKING_HOLD_TRUTHS = {"HOLD_WEAK", "HOLD_FORMING", "HOLD_FAILED", "NONE"}
_HARD_HOLD_TRUTHS = {"HOLD_FAILED"}

# candle_truth.event_type values that prove candle truth is not supportive.
_BLOCKING_CANDLE_EVENTS = {"INDECISION", "REJECTION", "FAILURE", "NONE"}
_HARD_CANDLE_EVENTS = {"FAILURE"}

# alert_truth_label values that prove the alert is not a confirmed trigger.
_BLOCKING_ALERT_TRUTHS = {"WATCH_ONLY", "FORMING_TRIGGER", "FAILED_TRIGGER", "NO_ALERT"}

# audit_label values that themselves declare the setup is not a clean SNIPE.
_BLOCKING_AUDIT_LABELS = {"DISQUALIFIED", "STARTER_ONLY_VALID", "WATCH_ONLY_BLOCKED", "INSUFFICIENT_CONTEXT"}

# promotion_state values that are not a clean confirmation.
_BLOCKING_PROMOTION_STATES = {"PROMOTION_BLOCKED", "PROMOTION_PENDING", "NOT_ELIGIBLE"}

# Hard blocker text (safe to scan diagnostic/blocking strings — none of these
# appear in the benign "appears complete"/promotion-trigger boilerplate).
_HARD_BLOCKER_TEXT = (
    "hostile wick", "candle veto", "failed retest", "failed break",
    "acceptance denied", "no fresh aggression", "hold weak", "hold failed",
    "trigger forming", "no valid 1h", "proof incomplete", "not confirmed",
    "not clean", "unresolved", "watch-only", "watch only",
    "1h trigger proof remains incomplete", "has not confirmed a closed hold",
    "no fresh add", "hold existing only", "candle confirmation remains pending",
    "candle evidence incomplete", "verdict pending",
)
# Text that, when present, means an actual failure (→ WAIT, not NEAR_ENTRY).
_HARD_FAILURE_TEXT = (
    "failed retest", "failed break", "acceptance denied", "hold failed",
    "no valid 1h", "invalid",
)

_CONFIRMED_TOKENS = {"confirmed", "hold_confirmed", "retest_confirmed", "true", "yes", "pass"}


# ---------------------------------------------------------------------------
# Small helpers (no external deps)
# ---------------------------------------------------------------------------

def _d(obj, key):
    v = obj.get(key) if isinstance(obj, dict) else None
    return v if isinstance(v, dict) else {}


def _nonempty_list(value) -> list:
    return [x for x in value if x not in (None, "", [], {})] if isinstance(value, list) else []


def _names(items) -> list:
    out = []
    for it in items or []:
        if isinstance(it, str) and it:
            out.append(it)
        elif isinstance(it, dict):
            for k in ("gate", "name", "id", "key"):
                v = it.get(k)
                if isinstance(v, str) and v:
                    out.append(v)
                    break
    return out


def _has_text(value, terms) -> bool:
    if not isinstance(value, str):
        return False
    low = value.lower()
    return any(t in low for t in terms)


def _confirmed(value) -> bool:
    return isinstance(value, str) and value.strip().lower() in _CONFIRMED_TOKENS


def _resolve_audit(obj) -> dict:
    """obj may be a tiering_result / persisted row (carrying snipe_gate_audit)
    or the audit snapshot itself. Return the audit dict (never None)."""
    sga = obj.get("snipe_gate_audit") if isinstance(obj, dict) else None
    if isinstance(sga, dict):
        return sga
    if isinstance(obj, dict) and any(
        k in obj for k in ("promotion_state", "blocked_gates", "blocked_gate_names", "missing_proofs")
    ):
        return obj
    return {}


def _snipe_channel(channel: str) -> bool:
    return "snipe" in str(channel or "").lower()


# ---------------------------------------------------------------------------
# Core detector (reusable — works on a live tiering_result OR a persisted row)
# ---------------------------------------------------------------------------

def has_active_snipe_confirmation_blocker(obj) -> tuple:
    """Return (blocked: bool, reasons: list[str]).

    A clean confirmation returns (False, []). Any single active blocker returns
    (True, [...]) with human-readable reasons. Structured fields first, hard
    text second. Never scans promotion_triggers. Errs strict on purpose:
    better too strict than to let a false SNIPE through.
    """
    if not isinstance(obj, dict):
        return False, []

    sga = _resolve_audit(obj)
    htf = _d(obj, "higher_timeframe_context") or _d(sga, "higher_timeframe_context")
    oh = _d(obj, "one_hour_entry")
    signal = _d(obj, "final_signal")

    reasons: list = []

    # ---- Structured audit blockers (authoritative) -----------------------
    blocked = _names(_nonempty_list(sga.get("blocked_gate_names"))) or _names(_nonempty_list(sga.get("blocked_gates")))
    if blocked:
        reasons.append("blocked gates: " + ", ".join(blocked))

    missing = _names(_nonempty_list(sga.get("missing_proofs")))
    if missing:
        reasons.append("missing proofs: " + ", ".join(missing))

    score_blocked = _names(_nonempty_list(sga.get("score_blocked_by")))
    if score_blocked:
        reasons.append("score blocked by: " + ", ".join(score_blocked))

    promo = str(sga.get("promotion_state") or "").upper().strip()
    if promo in _BLOCKING_PROMOTION_STATES:
        reasons.append(f"promotion_state {promo} is not a confirmation")

    audit_label = str(sga.get("audit_label") or "").upper().strip()
    if audit_label in _BLOCKING_AUDIT_LABELS:
        reasons.append(f"audit_label {audit_label} contradicts SNIPE")

    if htf.get("blocks_snipe_contextually") is True:
        reasons.append("HTF contextual block (weekly/monthly supply/structure)")

    # ---- one_hour_entry truth (live path; absent in persisted rows) ------
    trig = str(oh.get("trigger_state") or "").upper().strip()
    if trig in _BLOCKING_TRIGGER_STATES:
        reasons.append(f"1H trigger_state {trig}")

    hold_truth = str(_d(oh, "pullback_retest_hold").get("hold_truth") or "").upper().strip()
    if hold_truth in _BLOCKING_HOLD_TRUTHS:
        reasons.append(f"1H hold_truth {hold_truth}")

    candle = _d(oh, "candle_truth")
    event = str(candle.get("event_type") or "").upper().strip()
    if event in _BLOCKING_CANDLE_EVENTS:
        reasons.append(f"candle event_type {event} not supportive")
    elif candle and candle.get("closed_candle_confirms") is False:
        reasons.append("1H closed candle does not confirm")

    alert_truth = str(oh.get("alert_truth_label") or "").upper().strip()
    if alert_truth in _BLOCKING_ALERT_TRUTHS:
        reasons.append(f"alert_truth_label {alert_truth} not a confirmed trigger")

    # ---- retest / hold status (signal first, then row top-level) ---------
    retest = signal.get("retest_status") if signal else obj.get("retest_status")
    hold = signal.get("hold_status") if signal else obj.get("hold_status")
    if retest is not None and not _confirmed(retest):
        reasons.append(f"retest_status {retest!r} not confirmed")
    if hold is not None and not _confirmed(hold):
        reasons.append(f"hold_status {hold!r} not confirmed")

    # ---- Hard text (never scans promotion_triggers) ----------------------
    for r in _nonempty_list(sga.get("blocking_reasons")):
        s = r if isinstance(r, str) else None
        if s and _has_text(s, _HARD_BLOCKER_TEXT):
            reasons.append(f"blocking reason: {s}")
    if _has_text(sga.get("diagnostic_sentence"), _HARD_BLOCKER_TEXT):
        reasons.append(f"diagnostic blocker: {sga.get('diagnostic_sentence')}")

    # De-duplicate while preserving order.
    seen, unique = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return (bool(unique), unique)


# ---------------------------------------------------------------------------
# Severity → corrected tier
# ---------------------------------------------------------------------------

def _is_hard_failure(obj, reasons) -> bool:
    """A blocker is a hard failure (→ WAIT) when the setup actually failed —
    a failed/invalid trigger, failed hold, candle failure, failed break, or a
    BLOCK on a structural gate. Otherwise the setup is structurally valid but
    proof is still forming (→ NEAR_ENTRY, visible, no capital)."""
    sga = _resolve_audit(obj)
    oh = _d(obj, "one_hour_entry")

    blocked_names = set(_names(sga.get("blocked_gate_names")) or _names(sga.get("blocked_gates")))
    if blocked_names & _HARD_FAILURE_GATES:
        return True
    if str(oh.get("trigger_state") or "").upper().strip() in _HARD_TRIGGER_STATES:
        return True
    if str(_d(oh, "pullback_retest_hold").get("hold_truth") or "").upper().strip() in _HARD_HOLD_TRUTHS:
        return True
    if str(_d(oh, "candle_truth").get("event_type") or "").upper().strip() in _HARD_CANDLE_EVENTS:
        return True
    for r in reasons:
        if _has_text(r, _HARD_FAILURE_TEXT):
            return True
    return False


def _corrected_tier(obj, reasons) -> str:
    return "WAIT" if _is_hard_failure(obj, reasons) else "NEAR_ENTRY"


# ---------------------------------------------------------------------------
# Pipeline seal (mutates the tiering_result in place; only ever downgrades)
# ---------------------------------------------------------------------------

_SEAL_LABEL = "SNIPE_CONFIRMATION_BLOCKED"
_SEAL_PROMOTION_STATE = "PROMOTION_BLOCKED"
_SEAL_REASON = "active SNIPE confirmation blocker remained"
_SEAL_PHASE = "14M"


def _seal_diagnostic(corrected: str) -> str:
    return (
        f"SNIPE confirmation blocked; final tier sealed to {corrected} "
        "because unresolved proof remains."
    )


def is_snipe_confirmation_output(tiering_result) -> bool:
    """True when the result currently claims a SNIPE confirmation by tier,
    capital, or routing — the only case the seal needs to inspect."""
    if not isinstance(tiering_result, dict):
        return False
    final_tier = str(tiering_result.get("final_tier") or "").upper().strip()
    signal = _d(tiering_result, "final_signal")
    capital = str(signal.get("capital_action") or tiering_result.get("capital_action") or "").lower().strip()
    channel = tiering_result.get("final_discord_channel") or signal.get("discord_channel")
    return final_tier == "SNIPE_IT" or capital in _FULL_SNIPE_CAPITAL or _snipe_channel(channel)


def seal_snipe_confirmed_consistency(tiering_result, config=None):
    """Final consistency seal. Returns the same tiering_result.

    If the result claims a SNIPE confirmation AND active blockers remain, the
    trading-decision fields (final_tier, capital_action, final_discord_channel,
    safe_for_alert, and the mirrored final_signal fields) are corrected to a
    truthful tier using the existing tier machinery, and the contradiction is
    recorded. Raw evidence is never deleted. Never raises.
    """
    try:
        if not isinstance(tiering_result, dict):
            return tiering_result
        if not is_snipe_confirmation_output(tiering_result):
            return tiering_result

        original_tier = str(tiering_result.get("final_tier") or "").upper().strip()
        blocked, reasons = has_active_snipe_confirmation_blocker(tiering_result)

        if not blocked:
            tiering_result["snipe_confirmed_seal"] = {
                "applied": False,
                "original_tier": original_tier,
                "corrected_tier": original_tier,
                "blockers": [],
                "seal_label": None,
                "diagnostic": "SNIPE confirmation verified: no active SNIPE blockers remain.",
            }
            return tiering_result

        corrected = _corrected_tier(tiering_result, reasons)
        _apply_downgrade(tiering_result, corrected, reasons, original_tier)
        return tiering_result
    except Exception:  # pragma: no cover - defensive; never break a scan
        return tiering_result


def _apply_downgrade(tiering_result, corrected, reasons, original_tier) -> None:
    from src import tiering  # local import avoids any import cycle / load cost

    channel = tiering.CHANNEL_MAP[corrected]
    capital = tiering.CAPITAL_MAP[corrected]

    signal = tiering_result.get("final_signal")
    if isinstance(signal, dict):
        scan_price = signal.get("scan_price")
        signal["tier"] = corrected
        signal["discord_channel"] = channel
        signal["capital_action"] = capital
        try:
            signal["sanitized_reason"] = tiering._sanitize_reason_for_tier(signal.get("reason"), corrected)
            signal["sanitized_next_action"] = tiering._sanitize_reason_for_tier(signal.get("next_action"), corrected)
        except Exception:
            pass
        if corrected == "NEAR_ENTRY":
            try:
                signal["near_entry_blocker_note"] = tiering._build_near_entry_blocker_note(signal, scan_price)
            except Exception:
                pass
        tiering_result["final_signal"] = signal

    tiering_result["final_tier"] = corrected
    tiering_result["final_discord_channel"] = channel
    tiering_result["capital_action"] = capital
    tiering_result["safe_for_alert"] = corrected != "WAIT"

    downgrades = tiering_result.get("downgrades")
    if not isinstance(downgrades, list):
        downgrades = []
    downgrades.append(
        f"{original_tier}→{corrected}: SNIPE confirmation seal — active blockers: "
        + "; ".join(reasons)
    )
    tiering_result["downgrades"] = downgrades

    diagnostic = _seal_diagnostic(corrected)
    tiering_result["snipe_confirmed_seal"] = {
        "applied": True,
        "original_tier": original_tier,
        # Phase 14M.1 spec-shaped keys:
        "sealed_tier": corrected,
        "reason": _SEAL_REASON,
        "active_blockers": list(reasons),
        "sealed_by_phase": _SEAL_PHASE,
        # Legacy 14M keys (kept for scheduler.py logging + existing callers):
        "corrected_tier": corrected,
        "blockers": list(reasons),
        "seal_label": _SEAL_LABEL,
        "diagnostic": diagnostic,
    }

    # Reflect the contradiction in the persisted audit organ so the recorded
    # snapshot can never read as a clean SNIPE_CONFIRMED or ALREADY_SNIPE. Raw
    # evidence (blocked_gates, missing_proofs, score_blocked_by, raw_snipe_score,
    # snipe_score, snipe_grade) is left untouched.
    sga = tiering_result.get("snipe_gate_audit")
    if isinstance(sga, dict):
        sga["audit_label"] = _SEAL_LABEL
        sga["promotion_state"] = _SEAL_PROMOTION_STATE
        sga["diagnostic_sentence"] = diagnostic
        br = sga.get("blocking_reasons")
        if isinstance(br, list):
            br.insert(0, diagnostic)
        else:
            sga["blocking_reasons"] = [diagnostic]

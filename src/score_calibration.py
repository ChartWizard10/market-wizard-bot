"""Score calibration — read-only audit layer for confidence realism.

Phase 14B: produces a calibrated score, delta, band, and reasons by examining
existing tiering_result fields (risk realism, overhead, trajectory, structure).

Ownership rules (enforced permanently):
  - PURELY informational / audit-layer.
  - NEVER mutates tiering_result["score"].
  - NEVER affects tier, capital_action, final_discord_channel, safe_for_alert.
  - NEVER affects suppression, dedup, or state transitions.
  - tiering.py remains the sole final authority on tier and gates.

Output dict shape:
  {
    "raw_score":        int,
    "calibrated_score": int,
    "delta":            int,         # bounded to [-8, +4]
    "score_band":       str,         # "elite" | "executable" | "tactical" | "developing" | "watch" | "low"
    "reasons":          list[str],   # each adjustment with its delta
    "primary_reason":   str,         # one-line summary (read off the largest contributor)
    "display_text":     str,         # "84 — strong but overhead-compressed."
  }
"""

# ---------------------------------------------------------------------------
# Tunables (all magic numbers in one place)
# ---------------------------------------------------------------------------

_TOTAL_DELTA_FLOOR =  -8
_TOTAL_DELTA_CEIL  =  +4
_ELITE_SCORE_FLOOR =  90
_ELITE_CAP         =  89

# Risk realism state → adjustment
_RISK_ADJ = {
    "healthy":  0,
    "normal":   0,
    "elevated": -1,
    "fragile":  -3,
}

# Overhead status → adjustment by tier family
_OVERHEAD_ADJ_EXEC = {           # SNIPE_IT and STARTER
    "clear":    +1,
    "moderate": -2,
    "blocked":  -3,
    "unknown":  -1,
}
_OVERHEAD_ADJ_WATCH = {          # NEAR_ENTRY
    "clear":     0,
    "moderate": -1,
    "blocked":  -2,
    "unknown":  -1,
}

# Trajectory label → adjustment
_TRAJECTORY_ADJ = {
    "UPGRADING":          +2,
    "IMPROVING":          +1,
    "NEW_SIGNAL":          0,
    "REPEATED_NO_CHANGE":  0,
    "STALE_WATCH":        -1,
    "QUALITY_COMPRESSED": -2,
    "BLOCKER_PERSISTING": -2,
    "DETERIORATING":      -2,
    "DOWNGRADING":        -3,
    "UNKNOWN":             0,
}

_ELITE_STRUCTURES = {"bos", "mss", "choch"}
_NORMAL_STRUCTURES = {"reclaim", "accepted_break", "failed_breakdown_reclaim"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calibrate_score(tiering_result: dict, config: dict | None = None) -> dict:
    """Return audit-layer score calibration dict. Never raises.

    `tiering_result["score"]` is read but NEVER mutated by this function.
    The caller stores the returned dict in `tiering_result["calibration"]`.
    """
    try:
        return _calibrate(tiering_result, config or {})
    except Exception as exc:
        safe_score = _safe_int(tiering_result.get("score") if isinstance(tiering_result, dict) else 0)
        return {
            "raw_score":        safe_score,
            "calibrated_score": safe_score,
            "delta":            0,
            "score_band":       _band(safe_score),
            "reasons":          [f"calibration_error: {exc}"],
            "primary_reason":   "calibration unavailable",
            "display_text":     "",
        }


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _calibrate(tiering_result: dict, _config: dict) -> dict:
    raw_score   = _safe_int(tiering_result.get("score", 0))
    final_tier  = str(tiering_result.get("final_tier", "WAIT"))
    signal      = tiering_result.get("final_signal") or {}
    trajectory  = tiering_result.get("trajectory") or {}

    risk_state    = _norm_str(signal.get("risk_realism_state"))
    overhead      = _norm_str(signal.get("overhead_status"))
    structure     = _norm_str(signal.get("structure_event"))
    retest        = _norm_str(signal.get("retest_status"))
    hold          = _norm_str(signal.get("hold_status"))
    mc            = signal.get("missing_conditions") or []
    traj_label    = str(trajectory.get("label", "UNKNOWN")).strip().upper()

    reasons: list[tuple[str, int]] = []

    # ---- A. Risk realism --------------------------------------------------
    risk_delta = _RISK_ADJ.get(risk_state, 0)
    if risk_delta != 0:
        reasons.append((f"risk={risk_state}", risk_delta))

    # ---- B. Path openness -------------------------------------------------
    if final_tier in ("SNIPE_IT", "STARTER"):
        path_table = _OVERHEAD_ADJ_EXEC
    else:
        path_table = _OVERHEAD_ADJ_WATCH
    path_delta = path_table.get(overhead, 0)
    if path_delta != 0:
        reasons.append((f"overhead={overhead}", path_delta))

    # ---- C. Trajectory ----------------------------------------------------
    traj_delta = _TRAJECTORY_ADJ.get(traj_label, 0)
    if traj_delta != 0:
        reasons.append((f"trajectory={traj_label}", traj_delta))

    # ---- D. Structure / confirmation quality ------------------------------
    quality_delta = _structure_quality_adj(final_tier, structure, retest, hold, mc)
    if quality_delta != 0:
        reasons.append((f"structure_quality", quality_delta))

    # ---- Sum + bound ------------------------------------------------------
    raw_delta     = risk_delta + path_delta + traj_delta + quality_delta
    bounded_delta = max(_TOTAL_DELTA_FLOOR, min(_TOTAL_DELTA_CEIL, raw_delta))
    calibrated    = raw_score + bounded_delta

    # ---- Elite cap (no 90+ unless cleanliness preconditions met) ----------
    elite_cap_applied = False
    if calibrated >= _ELITE_SCORE_FLOOR and not _qualifies_for_elite(
        risk_state, overhead, retest, hold, traj_label, final_tier
    ):
        calibrated = _ELITE_CAP
        elite_cap_applied = True
        reasons.append(("elite_cap_applied", _ELITE_CAP - (raw_score + bounded_delta)))

    final_delta = calibrated - raw_score
    score_band  = _band(calibrated)
    primary     = _primary_reason(reasons, score_band, elite_cap_applied)
    display     = _display_text(calibrated, score_band, primary, final_delta)

    return {
        "raw_score":        raw_score,
        "calibrated_score": calibrated,
        "delta":            final_delta,
        "score_band":       score_band,
        "reasons":          [f"{name} ({d:+d})" for name, d in reasons],
        "primary_reason":   primary,
        "display_text":     display,
    }


# ---------------------------------------------------------------------------
# Structure / confirmation quality
# ---------------------------------------------------------------------------

def _structure_quality_adj(
    final_tier: str,
    structure: str,
    retest: str,
    hold: str,
    missing_conditions,
) -> int:
    """+1 for elite structure on executable tiers; soft penalties for NEAR_ENTRY weaknesses."""
    if final_tier in ("SNIPE_IT", "STARTER"):
        if structure in _ELITE_STRUCTURES:
            return +1
        if structure == "none" or structure == "":
            return -1
        return 0

    if final_tier == "NEAR_ENTRY":
        # Soft penalties — NEAR_ENTRY is permitted to have these conditions
        if retest in ("missing", "failed") and hold in ("missing", "failed"):
            return -2
        if retest in ("missing", "failed", "partial") or hold in ("missing", "failed", "partial"):
            return -1
        # Many missing conditions also drag confidence
        if isinstance(missing_conditions, list) and len(missing_conditions) >= 3:
            return -1
        return 0

    return 0


# ---------------------------------------------------------------------------
# Elite cap precondition
# ---------------------------------------------------------------------------

def _qualifies_for_elite(
    risk_state: str,
    overhead: str,
    retest: str,
    hold: str,
    traj_label: str,
    final_tier: str,
) -> bool:
    if final_tier != "SNIPE_IT":
        return False
    if risk_state not in ("normal", "healthy", ""):
        # "" = unknown; do not allow elite without explicit risk state confirmation
        if risk_state != "":
            return False
        return False
    if overhead != "clear":
        return False
    if retest != "confirmed" or hold != "confirmed":
        return False
    if traj_label in ("DETERIORATING", "DOWNGRADING", "QUALITY_COMPRESSED"):
        return False
    return True


# ---------------------------------------------------------------------------
# Band and display
# ---------------------------------------------------------------------------

def _band(score: int) -> str:
    if score >= 90:
        return "elite"
    if score >= 86:
        return "executable"
    if score >= 81:
        return "tactical"
    if score >= 75:
        return "developing"
    if score >= 68:
        return "watch"
    return "low"


_BAND_PHRASE = {
    "elite":      "elite institutional setup",
    "executable": "high-quality executable",
    "tactical":   "strong tactical setup",
    "developing": "developing setup",
    "watch":      "watch-quality",
    "low":        "low conviction",
}


def _primary_reason(
    reasons: list[tuple[str, int]],
    band: str,
    elite_cap_applied: bool,
) -> str:
    """Pick a one-line summary based on the largest-magnitude reason."""
    if elite_cap_applied:
        return "near-elite but cleanliness preconditions not met"
    if not reasons:
        return f"{_BAND_PHRASE.get(band, band)}, no quality compression"

    # Largest absolute delta wins
    name, delta = max(reasons, key=lambda r: abs(r[1]))
    return _humanize_reason(name, delta, band)


def _humanize_reason(name: str, delta: int, band: str) -> str:
    if name.startswith("risk="):
        state = name.split("=", 1)[1]
        if state == "fragile":
            return "risk window is fragile"
        if state == "elevated":
            return "risk window is tight"
        return f"risk={state}"
    if name.startswith("overhead="):
        state = name.split("=", 1)[1]
        if state == "blocked":
            return "overhead path is blocked"
        if state == "moderate":
            return "overhead is moderate"
        if state == "clear":
            return "clear overhead path"
        if state == "unknown":
            return "overhead path unclear"
        return f"overhead={state}"
    if name.startswith("trajectory="):
        label = name.split("=", 1)[1]
        return {
            "UPGRADING":          "tier improving across scans",
            "IMPROVING":          "quality improving across scans",
            "STALE_WATCH":        "watch unchanged across scans",
            "QUALITY_COMPRESSED": "quality compressed across scans",
            "BLOCKER_PERSISTING": "blocker persisting across scans",
            "DETERIORATING":      "quality deteriorating",
            "DOWNGRADING":        "tier degrading across scans",
        }.get(label, f"trajectory={label}")
    if name == "structure_quality":
        if delta > 0:
            return "structure event is elite"
        return "structure / confirmation is weak"
    return name


def _display_text(score: int, band: str, primary: str, delta: int) -> str:
    base = _BAND_PHRASE.get(band, band)
    if delta == 0:
        return f"{score} calibrated — {base}."
    if delta > 0:
        return f"{score} calibrated (+{delta}) — {base}, {primary}."
    return f"{score} calibrated ({delta}) — {primary}."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip().lower()

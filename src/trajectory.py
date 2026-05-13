"""Signal trajectory tracker — informational progression labels across scan cycles.

Computes a single trajectory label and human-readable text line by comparing the
current tiering_result against the previous per-ticker state from state_store.

Ownership rules (enforced permanently):
  - PURELY informational.  Never modifies tiering_result fields.
  - Never affects tier, capital_action, final_discord_channel, or safe_for_alert.
  - Never affects suppression or routing decisions.
  - tiering.py remains the sole final authority on tier at all times.

Usage:
  from src import trajectory
  result = trajectory.compute(tiering_result, ticker_state)
  # result = {"label": "IMPROVING", "text": "Improving — score 72 → 80, confirmations improved."}
"""

_TIER_RANK: dict[str, int] = {
    "WAIT":       0,
    "NEAR_ENTRY": 1,
    "STARTER":    2,
    "SNIPE_IT":   3,
}

_STATUS_RANK: dict[str, int] = {
    "failed":    0,
    "missing":   1,
    "partial":   2,
    "confirmed": 3,
}

_RISK_RANK: dict[str, int] = {
    "fragile":  0,
    "elevated": 1,
    "normal":   2,
    "healthy":  3,
}

_SCORE_CHANGE_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute(tiering_result: dict, ticker_state: dict | None) -> dict:
    """Return trajectory dict with 'label' and 'text' keys.

    Always returns a dict — never raises.  Errors produce label='UNKNOWN', text=''.

    Args:
        tiering_result: validated signal dict from tiering.validate (current cycle)
        ticker_state:   per-ticker state record from state_store BEFORE this alert
                        is recorded.  None when ticker has no prior alert history.
    """
    try:
        return _compute(tiering_result, ticker_state)
    except Exception:
        return {"label": "UNKNOWN", "text": ""}


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _compute(tiering_result: dict, ticker_state: dict | None) -> dict:
    current_tier  = tiering_result.get("final_tier", "WAIT")
    current_score = tiering_result.get("score", 0) or 0
    current_sig   = tiering_result.get("final_signal") or {}

    # No prior state or empty history → NEW_SIGNAL
    history = (ticker_state or {}).get("alert_history") or []
    if not ticker_state or not history:
        return _make("NEW_SIGNAL", "New signal — first appearance in scanner history.")

    prev       = history[-1]
    prev_tier  = prev.get("tier", "WAIT")
    prev_score = prev.get("score") or 0

    curr_rank = _TIER_RANK.get(current_tier, 0)
    prev_rank = _TIER_RANK.get(prev_tier, 0)

    # ---- Tier change --------------------------------------------------------
    if curr_rank > prev_rank:
        return _make(
            "UPGRADING",
            f"Upgrading: {prev_tier} → {current_tier}  (score {prev_score} → {current_score})",
        )

    if curr_rank < prev_rank:
        return _make(
            "DOWNGRADING",
            f"Downgrading: {prev_tier} → {current_tier}  (score {prev_score} → {current_score})",
        )

    # ---- Same tier ----------------------------------------------------------

    # NEAR_ENTRY specific: blocker persisting / stale watch
    if current_tier == "NEAR_ENTRY":
        prev_ut = _norm_str(prev.get("upgrade_trigger"))
        curr_ut = _norm_str(current_sig.get("upgrade_trigger"))
        prev_oh = _norm_str(prev.get("overhead_status"))
        curr_oh = _norm_str(current_sig.get("overhead_status"))
        prev_mc = _norm_list(prev.get("missing_conditions"))
        curr_mc = _norm_list(current_sig.get("missing_conditions"))

        # Blocker persisting: upgrade trigger unchanged AND overhead still blocked/moderate
        if (
            prev_ut == curr_ut
            and curr_oh in ("blocked", "moderate")
            and prev_oh == curr_oh
        ):
            return _make(
                "BLOCKER_PERSISTING",
                "Blocker persisting — upgrade trigger and blocking conditions unchanged from last scan.",
            )

        # Stale watch: missing conditions set unchanged
        if prev_mc == curr_mc:
            return _make(
                "STALE_WATCH",
                "Stale watch — NEAR_ENTRY conditions unchanged from last alert.",
            )

    # ---- Risk realism degraded to fragile ------------------------------------
    prev_risk = _norm_str(prev.get("risk_realism_state"))
    curr_risk = _norm_str(current_sig.get("risk_realism_state"))

    prev_risk_rank = _RISK_RANK.get(prev_risk, -1)
    curr_risk_rank = _RISK_RANK.get(curr_risk, -1)

    if curr_risk == "fragile" and prev_risk_rank > curr_risk_rank:
        return _make(
            "QUALITY_COMPRESSED",
            "Quality compressed — risk window has become fragile since last alert.",
        )

    # ---- Confirmation quality -----------------------------------------------
    prev_retest = _STATUS_RANK.get(_norm_str(prev.get("retest_status")), -1)
    curr_retest = _STATUS_RANK.get(_norm_str(current_sig.get("retest_status")), -1)
    prev_hold   = _STATUS_RANK.get(_norm_str(prev.get("hold_status")), -1)
    curr_hold   = _STATUS_RANK.get(_norm_str(current_sig.get("hold_status")), -1)

    confirmations_improved = curr_retest > prev_retest or curr_hold > prev_hold
    confirmations_worsened = curr_retest < prev_retest or curr_hold < prev_hold
    risk_improved          = curr_risk_rank > prev_risk_rank and prev_risk_rank >= 0
    risk_worsened          = curr_risk_rank < prev_risk_rank and curr_risk_rank >= 0

    score_delta = current_score - prev_score

    # ---- IMPROVING ----------------------------------------------------------
    if score_delta >= _SCORE_CHANGE_THRESHOLD or confirmations_improved or risk_improved:
        parts = []
        if score_delta >= _SCORE_CHANGE_THRESHOLD:
            parts.append(f"score {prev_score} → {current_score}")
        if confirmations_improved:
            parts.append("confirmations improved")
        if risk_improved:
            parts.append("risk window improved")
        return _make("IMPROVING", f"Improving — {', '.join(parts)}.")

    # ---- DETERIORATING ------------------------------------------------------
    if score_delta <= -_SCORE_CHANGE_THRESHOLD or confirmations_worsened or risk_worsened:
        parts = []
        if score_delta <= -_SCORE_CHANGE_THRESHOLD:
            parts.append(f"score {prev_score} → {current_score}")
        if confirmations_worsened:
            parts.append("confirmations weakened")
        if risk_worsened:
            parts.append("risk window compressed")
        return _make("DETERIORATING", f"Deteriorating — {', '.join(parts)}.")

    # ---- Default ------------------------------------------------------------
    return _make("REPEATED_NO_CHANGE", "Repeated — no material change from last alert.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(label: str, text: str) -> dict:
    return {"label": label, "text": text}


def _norm_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip().lower()


def _norm_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return sorted(_norm_str(x) for x in val if x)
    return [_norm_str(val)] if val else []

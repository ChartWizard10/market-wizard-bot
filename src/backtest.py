"""Phase 13 — Backtest Foundation.

Pure-function, offline, read-only engine that evaluates scanner alerts
against future price bars.

No network calls. No file writes. No live scanner imports. No side effects.

Primary question: did price hit T1 before invalidation?
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Outcome labels
# ---------------------------------------------------------------------------

WIN_T1_BEFORE_INVALIDATION  = "WIN_T1_BEFORE_INVALIDATION"
LOSS_INVALIDATION_BEFORE_T1 = "LOSS_INVALIDATION_BEFORE_T1"
OPEN_NO_TERMINAL_HIT        = "OPEN_NO_TERMINAL_HIT"
NO_TRIGGER                  = "NO_TRIGGER"
AMBIGUOUS_SAME_BAR          = "AMBIGUOUS_SAME_BAR"
INVALID_DATA                = "INVALID_DATA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value) -> float | None:
    """Convert value to float; return None if conversion fails or value is None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_targets(targets) -> list[float]:
    """Return a list of valid float targets from various input forms.

    Supports:
    - list of numbers: [110, 120]
    - list of dicts with 'price', 'level', or 'target' key:
        [{"price": 110}, {"level": 120}, {"label": "T1", "level": 195.0}]
    - single number: 110
    - None / empty / missing: []
    """
    if targets is None:
        return []
    if isinstance(targets, (int, float)):
        f = _to_float(targets)
        return [f] if f is not None else []
    if not isinstance(targets, list):
        return []
    result: list[float] = []
    for t in targets:
        if isinstance(t, (int, float)):
            f = _to_float(t)
            if f is not None:
                result.append(f)
        elif isinstance(t, dict):
            for key in ("price", "level", "target"):
                if key in t:
                    f = _to_float(t[key])
                    if f is not None:
                        result.append(f)
                        break
    return result


def _get_first_target(alert: dict) -> float | None:
    """Return the first valid T1 from alert['targets'], or None."""
    targets = _normalize_targets(alert.get("targets"))
    return targets[0] if targets else None


def _get_reference_price(alert: dict) -> float | None:
    """Return the price reference point for MFE/MAE.

    Prefers scan_price; falls back to trigger_level.
    """
    sp = _to_float(alert.get("scan_price"))
    if sp is not None:
        return sp
    return _to_float(alert.get("trigger_level"))


def _compute_mfe_mae(reference_price: float, bars: list[dict]) -> dict:
    """Compute max favorable and max adverse excursion for a long position.

    MFE = max(bar.high - reference_price) over all bars
    MAE = min(bar.low  - reference_price) over all bars  (zero or negative)
    """
    if not bars or reference_price <= 0:
        return {
            "max_favorable_excursion":     None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion":       None,
            "max_adverse_excursion_pct":   None,
        }

    mfe: float | None = None
    mae: float | None = None

    for bar in bars:
        high = _to_float(bar.get("high"))
        low  = _to_float(bar.get("low"))
        if high is None or low is None:
            continue
        up = high - reference_price
        dn = low  - reference_price
        if mfe is None or up > mfe:
            mfe = up
        if mae is None or dn < mae:
            mae = dn

    if mfe is None or mae is None:
        return {
            "max_favorable_excursion":     None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion":       None,
            "max_adverse_excursion_pct":   None,
        }

    return {
        "max_favorable_excursion":     round(mfe, 4),
        "max_favorable_excursion_pct": round(mfe / reference_price * 100, 4),
        "max_adverse_excursion":       round(mae, 4),
        "max_adverse_excursion_pct":   round(mae / reference_price * 100, 4),
    }


def _classify_first_terminal_hit(
    bars:        list[dict],
    t1:          float,
    invalidation: float,
    trigger:     float | None,
) -> dict:
    """Walk bars and classify the first decisive event.

    For long-side alerts:
    - T1 hit:           bar.high >= t1
    - Invalidation hit: bar.low  <= invalidation
    - Trigger hit:      bar.high >= trigger  (tracked, not terminal)

    Tie (same bar hits both): AMBIGUOUS_SAME_BAR — daily OHLC cannot prove
    intrabar sequence.
    """
    trigger_hit = False

    for i, bar in enumerate(bars):
        high = _to_float(bar.get("high"))
        low  = _to_float(bar.get("low"))
        if high is None or low is None:
            continue

        if trigger is not None and not trigger_hit and high >= trigger:
            trigger_hit = True

        hit_t1  = high >= t1
        hit_inv = low  <= invalidation

        if hit_t1 and hit_inv:
            return {
                "outcome_label":              AMBIGUOUS_SAME_BAR,
                "hit_t1_before_invalidation": False,
                "hit_invalidation_before_t1": False,
                "hit_trigger_first":          trigger_hit,
                "bars_to_t1":                 None,
                "bars_to_invalidation":       None,
                "first_hit":                  "ambiguous_same_bar",
                "terminal_bar_index":         i,
                "terminal_price":             None,
                "reason": (
                    f"T1 ({t1}) and invalidation ({invalidation}) both touched"
                    f" in bar {i}; intrabar sequence is ambiguous on daily OHLC."
                ),
            }

        if hit_t1:
            return {
                "outcome_label":              WIN_T1_BEFORE_INVALIDATION,
                "hit_t1_before_invalidation": True,
                "hit_invalidation_before_t1": False,
                "hit_trigger_first":          trigger_hit,
                "bars_to_t1":                 i,
                "bars_to_invalidation":       None,
                "first_hit":                  "t1",
                "terminal_bar_index":         i,
                "terminal_price":             round(high, 4),
                "reason":                     f"T1 ({t1}) hit at bar {i}.",
            }

        if hit_inv:
            return {
                "outcome_label":              LOSS_INVALIDATION_BEFORE_T1,
                "hit_t1_before_invalidation": False,
                "hit_invalidation_before_t1": True,
                "hit_trigger_first":          trigger_hit,
                "bars_to_t1":                 None,
                "bars_to_invalidation":       i,
                "first_hit":                  "invalidation",
                "terminal_bar_index":         i,
                "terminal_price":             round(low, 4),
                "reason":                     f"Invalidation ({invalidation}) hit at bar {i}.",
            }

    # No terminal hit within horizon
    if trigger is not None and not trigger_hit:
        return {
            "outcome_label":              NO_TRIGGER,
            "hit_t1_before_invalidation": False,
            "hit_invalidation_before_t1": False,
            "hit_trigger_first":          False,
            "bars_to_t1":                 None,
            "bars_to_invalidation":       None,
            "first_hit":                  None,
            "terminal_bar_index":         None,
            "terminal_price":             None,
            "reason": (
                f"Trigger ({trigger}) never reached within {len(bars)} bar(s)."
            ),
        }

    return {
        "outcome_label":              OPEN_NO_TERMINAL_HIT,
        "hit_t1_before_invalidation": False,
        "hit_invalidation_before_t1": False,
        "hit_trigger_first":          trigger_hit,
        "bars_to_t1":                 None,
        "bars_to_invalidation":       None,
        "first_hit":                  None,
        "terminal_bar_index":         None,
        "terminal_price":             None,
        "reason": (
            f"Neither T1 ({t1}) nor invalidation ({invalidation})"
            f" hit within {len(bars)} bar(s)."
        ),
    }


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate_alert_outcome(
    alert:        dict,
    future_bars:  list[dict],
    horizon_bars: int = 10,
) -> dict:
    """Evaluate a scanner alert against future OHLC bars.

    Primary question: did price hit T1 before invalidation?

    Parameters
    ----------
    alert:
        Alert dict (live scanner output or historical record).
    future_bars:
        List of OHLC bar dicts sorted ascending, starting after alert time.
        Each bar: {"open": ..., "high": ..., "low": ..., "close": ...}
    horizon_bars:
        Maximum number of bars to evaluate. Default 10.

    Returns
    -------
    dict with deterministic outcome fields.
    """
    tier               = alert.get("final_tier") or alert.get("tier") or ""
    risk_realism_state = alert.get("risk_realism_state") or ""
    retest_status      = alert.get("retest_status") or ""
    hold_status        = alert.get("hold_status") or ""

    def _invalid(reason: str) -> dict:
        return {
            "outcome_label":              INVALID_DATA,
            "hit_t1_before_invalidation": False,
            "hit_invalidation_before_t1": False,
            "hit_trigger_first":          False,
            "max_favorable_excursion":     None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion":       None,
            "max_adverse_excursion_pct":   None,
            "bars_to_t1":                 None,
            "bars_to_invalidation":       None,
            "first_hit":                  None,
            "terminal_bar_index":         None,
            "terminal_price":             None,
            "alert_tier":                 tier,
            "risk_realism_state":         risk_realism_state,
            "retest_status":              retest_status,
            "hold_status":                hold_status,
            "reason":                     reason,
        }

    # Validate future_bars
    if not future_bars:
        return _invalid("future_bars is empty.")

    # Trim to horizon
    bars = future_bars[:horizon_bars]

    # Validate OHLC — all four fields must be numeric
    for i, bar in enumerate(bars):
        for field in ("open", "high", "low", "close"):
            if _to_float(bar.get(field)) is None:
                return _invalid(
                    f"Non-numeric OHLC in bar {i}:"
                    f" field '{field}' = {bar.get(field)!r}."
                )

    # Resolve T1
    t1 = _get_first_target(alert)
    if t1 is None:
        return _invalid("No valid T1 target found in alert['targets'].")

    # Resolve invalidation
    invalidation = _to_float(alert.get("invalidation_level"))
    if invalidation is None:
        return _invalid("invalidation_level missing or non-numeric.")

    # Resolve reference price (for MFE/MAE)
    reference_price = _get_reference_price(alert)
    if reference_price is None:
        return _invalid(
            "scan_price and trigger_level both missing or non-numeric."
        )

    # Conservative geometry check: only reject structurally impossible geometry.
    # T1 must be above invalidation — if not, winning before losing is impossible.
    # Do NOT check T1 > reference_price strictly: NEAR_ENTRY alerts may have
    # scan_price below trigger, with T1 still above trigger above scan_price.
    if t1 <= invalidation:
        return _invalid(
            f"Invalid geometry: T1 ({t1}) <= invalidation ({invalidation})."
            " Cannot reach target without crossing invalidation first."
        )

    # Resolve trigger (optional — not required for WIN/LOSS classification)
    trigger = _to_float(alert.get("trigger_level"))

    # Compute MFE / MAE over the evaluated bars
    mfe_mae = _compute_mfe_mae(reference_price, bars)

    # Classify outcome
    hit = _classify_first_terminal_hit(bars, t1, invalidation, trigger)

    return {
        "outcome_label":              hit["outcome_label"],
        "hit_t1_before_invalidation": hit["hit_t1_before_invalidation"],
        "hit_invalidation_before_t1": hit["hit_invalidation_before_t1"],
        "hit_trigger_first":          hit["hit_trigger_first"],
        "max_favorable_excursion":     mfe_mae["max_favorable_excursion"],
        "max_favorable_excursion_pct": mfe_mae["max_favorable_excursion_pct"],
        "max_adverse_excursion":       mfe_mae["max_adverse_excursion"],
        "max_adverse_excursion_pct":   mfe_mae["max_adverse_excursion_pct"],
        "bars_to_t1":                 hit["bars_to_t1"],
        "bars_to_invalidation":       hit["bars_to_invalidation"],
        "first_hit":                  hit["first_hit"],
        "terminal_bar_index":         hit["terminal_bar_index"],
        "terminal_price":             hit["terminal_price"],
        "alert_tier":                 tier,
        "risk_realism_state":         risk_realism_state,
        "retest_status":              retest_status,
        "hold_status":                hold_status,
        "reason":                     hit["reason"],
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def summarize_backtest_results(results: list[dict]) -> dict:
    """Aggregate a list of evaluate_alert_outcome results into summary stats.

    win_rate_valid is computed over decisive outcomes (WIN + LOSS) only.
    OPEN, NO_TRIGGER, and AMBIGUOUS outcomes are excluded from the denominator
    because they are undecided, not failures.

    Parameters
    ----------
    results:
        List of dicts returned by evaluate_alert_outcome.

    Returns
    -------
    dict with counts, rates, and groupings.
    """
    total     = len(results)
    wins      = 0
    losses    = 0
    open_     = 0
    no_trigger = 0
    ambiguous = 0
    invalid   = 0

    mfe_values: list[float] = []
    mae_values: list[float] = []

    by_tier:              dict[str, dict] = {}
    by_risk_realism_state: dict[str, dict] = {}
    by_retest_hold_combo: dict[str, dict] = {}

    def _inc(group: dict, key: str, is_win: bool, is_loss: bool,
             mfe: float | None, mae: float | None) -> None:
        if key not in group:
            group[key] = {
                "count": 0, "wins": 0, "losses": 0,
                "_mfe": [], "_mae": [],
            }
        group[key]["count"] += 1
        if is_win:
            group[key]["wins"] += 1
        if is_loss:
            group[key]["losses"] += 1
        if mfe is not None:
            group[key]["_mfe"].append(mfe)
        if mae is not None:
            group[key]["_mae"].append(mae)

    for r in results:
        label      = r.get("outcome_label", INVALID_DATA)
        is_win     = label == WIN_T1_BEFORE_INVALIDATION
        is_loss    = label == LOSS_INVALIDATION_BEFORE_T1
        is_open    = label == OPEN_NO_TERMINAL_HIT
        is_ntrig   = label == NO_TRIGGER
        is_ambig   = label == AMBIGUOUS_SAME_BAR
        is_invalid = label == INVALID_DATA

        if is_win:
            wins += 1
        elif is_loss:
            losses += 1
        elif is_open:
            open_ += 1
        elif is_ntrig:
            no_trigger += 1
        elif is_ambig:
            ambiguous += 1
        else:
            invalid += 1

        mfe = r.get("max_favorable_excursion_pct")
        mae = r.get("max_adverse_excursion_pct")
        if mfe is not None:
            mfe_values.append(mfe)
        if mae is not None:
            mae_values.append(mae)

        if not is_invalid:
            tier_key  = r.get("alert_tier") or "unknown"
            rrs_key   = r.get("risk_realism_state") or "unknown"
            retest    = r.get("retest_status") or "unknown"
            hold      = r.get("hold_status") or "unknown"
            combo_key = f"{retest}/{hold}"

            _inc(by_tier,               tier_key,  is_win, is_loss, mfe, mae)
            _inc(by_risk_realism_state, rrs_key,   is_win, is_loss, mfe, mae)
            _inc(by_retest_hold_combo,  combo_key, is_win, is_loss, mfe, mae)

    valid         = total - invalid
    decisive      = wins + losses
    win_rate_valid  = round(wins   / decisive * 100, 2) if decisive > 0 else None
    loss_rate_valid = round(losses / decisive * 100, 2) if decisive > 0 else None
    avg_mfe_pct   = round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else None
    avg_mae_pct   = round(sum(mae_values) / len(mae_values), 4) if mae_values else None

    def _finalize(group: dict) -> dict:
        out: dict[str, dict] = {}
        for k, v in group.items():
            w  = v["wins"]
            l  = v["losses"]
            d  = w + l
            mfes = v["_mfe"]
            maes = v["_mae"]
            out[k] = {
                "count":       v["count"],
                "wins":        w,
                "losses":      l,
                "win_rate":    round(w / d * 100, 2) if d > 0 else None,
                "avg_mfe_pct": round(sum(mfes) / len(mfes), 4) if mfes else None,
                "avg_mae_pct": round(sum(maes) / len(maes), 4) if maes else None,
            }
        return out

    return {
        "total_alerts":        total,
        "valid_results":       valid,
        "invalid_results":     invalid,
        "wins":                wins,
        "losses":              losses,
        "open":                open_,
        "no_trigger":          no_trigger,
        "ambiguous":           ambiguous,
        "win_rate_valid":      win_rate_valid,
        "loss_rate_valid":     loss_rate_valid,
        "avg_mfe_pct":         avg_mfe_pct,
        "avg_mae_pct":         avg_mae_pct,
        "by_tier":             _finalize(by_tier),
        "by_risk_realism_state": _finalize(by_risk_realism_state),
        "by_retest_hold_combo":  _finalize(by_retest_hold_combo),
    }

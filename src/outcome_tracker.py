"""Phase 14C.5 — Observation Ledger: alert outcome capture (observation only).

Associates evidence already stored on each posted alert (weekly + 4H state,
VCP/BRT organs, etc.) with the *future price outcome* of that alert: whether
TP1/TP2/TP3 were hit, whether it was invalidated, and the max favorable /
adverse excursion observed.

Hard boundary — this module is observation/backtest material ONLY:
  * It NEVER writes to any decision-path object.
  * It is NEVER imported or read by prefilter, tiering, indicators,
    discord_alerts, campaign_store, score_calibration, or the Claude prompt.
  * It writes EXCLUSIVELY through state_store.record_outcome(), which is itself
    restricted to the 7 observational outcome fields.
  * It imports NO symbol from tiering, prefilter, discord_alerts, or indicators.

The only decision-adjacent module it touches is market_data (read-only price
fetch) and state_store (outcome write-back). Default OFF via config.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src import market_data
from src import state_store

log = logging.getLogger(__name__)


# All-None outcome payload. Returned whenever an outcome cannot be computed
# (missing trigger, no price data, no eligible bars). outcome_updated_at stays
# None so the record remains eligible for a later retry once data exists.
_EMPTY_OUTCOME: dict = {
    "tp1_hit":            None,
    "tp2_hit":            None,
    "tp3_hit":            None,
    "invalidated":        None,
    "mfe_pct":            None,
    "mae_pct":            None,
    "outcome_updated_at": None,
}


# ---------------------------------------------------------------------------
# Local helpers (self-contained — no cross-module coupling)
# ---------------------------------------------------------------------------

def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_targets(targets) -> list[float]:
    """Extract ordered float target levels from the stored 'targets' field.

    Supports a list of numbers, a list of dicts ({'level'|'price'|'target': x}),
    or a single number. Order is preserved (T1, T2, T3, ...).
    """
    if targets is None:
        return []
    if isinstance(targets, (int, float)):
        f = _to_float(targets)
        return [f] if f is not None else []
    if not isinstance(targets, list):
        return []
    out: list[float] = []
    for t in targets:
        if isinstance(t, (int, float)):
            f = _to_float(t)
            if f is not None:
                out.append(f)
        elif isinstance(t, dict):
            for key in ("level", "price", "target"):
                if key in t:
                    f = _to_float(t[key])
                    if f is not None:
                        out.append(f)
                    break
    return out


def _bars_after(price_df, alerted_at):
    """Return only the bars strictly after the alert timestamp.

    Daily bars are indexed at midnight, so a same-day alert (intraday) is
    naturally excluded — we observe what happened *after* the alert posted.
    """
    if price_df is None or len(price_df) == 0:
        return None
    if not isinstance(price_df.index, pd.DatetimeIndex):
        return None
    if not alerted_at:
        return price_df

    try:
        ts = pd.Timestamp(alerted_at)
    except Exception:
        return price_df
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)

    df = price_df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)

    return df[df.index > ts]


# ---------------------------------------------------------------------------
# Outcome computation
# ---------------------------------------------------------------------------

def compute_outcome(alert_record: dict, price_df) -> dict:
    """Compute the observational outcome of a single posted alert.

    Rules (per doctrine):
      * entry_ref = trigger_level. If missing → all-None outcome.
      * Only bars strictly after alerted_at are evaluated.
      * tp1_hit flips True once a bar closes >= TP1.
      * tp2_hit flips True only after tp1_hit, once close >= TP2.
      * tp3_hit flips True only after tp2_hit, once close >= TP3.
      * invalidated flips True once a bar closes <= invalidation_level; the
        walk then stops (the trade is closed).
      * mfe_pct = (max_high - entry_ref) / entry_ref * 100  (over walked bars)
      * mae_pct = (min_low  - entry_ref) / entry_ref * 100  (over walked bars)
      * A hit field stays None when its target level is absent.

    Returns a dict with exactly the 7 outcome fields. Never raises for normal
    data problems — degenerate input yields the all-None payload.
    """
    out = dict(_EMPTY_OUTCOME)

    entry_ref = _to_float(alert_record.get("trigger_level"))
    if entry_ref is None or entry_ref <= 0:
        return out

    bars = _bars_after(price_df, alert_record.get("alerted_at"))
    if bars is None or len(bars) == 0:
        return out

    cols = {c.lower(): c for c in bars.columns}
    high_col  = cols.get("high")
    low_col   = cols.get("low")
    close_col = cols.get("close")
    if high_col is None or low_col is None or close_col is None:
        return out

    targets = _normalize_targets(alert_record.get("targets"))
    tp1 = targets[0] if len(targets) >= 1 else None
    tp2 = targets[1] if len(targets) >= 2 else None
    tp3 = targets[2] if len(targets) >= 3 else None
    invalidation = _to_float(alert_record.get("invalidation_level"))

    tp1_hit     = False if tp1 is not None else None
    tp2_hit     = False if tp2 is not None else None
    tp3_hit     = False if tp3 is not None else None
    invalidated = False if invalidation is not None else None

    max_high: float | None = None
    min_low:  float | None = None

    for _, row in bars.iterrows():
        high  = _to_float(row[high_col])
        low   = _to_float(row[low_col])
        close = _to_float(row[close_col])

        if high is not None:
            max_high = high if max_high is None else max(max_high, high)
        if low is not None:
            min_low = low if min_low is None else min(min_low, low)

        # Invalidation closes the trade — record this bar's excursion, then stop.
        if invalidation is not None and close is not None and close <= invalidation:
            invalidated = True
            break

        if tp1 is not None and close is not None and close >= tp1:
            tp1_hit = True
        if tp2 is not None and tp1_hit is True and close is not None and close >= tp2:
            tp2_hit = True
        if tp3 is not None and tp2_hit is True and close is not None and close >= tp3:
            tp3_hit = True

    mfe_pct = ((max_high - entry_ref) / entry_ref * 100.0) if max_high is not None else None
    mae_pct = ((min_low - entry_ref) / entry_ref * 100.0) if min_low is not None else None

    return {
        "tp1_hit":            tp1_hit,
        "tp2_hit":            tp2_hit,
        "tp3_hit":            tp3_hit,
        "invalidated":        invalidated,
        "mfe_pct":            round(mfe_pct, 4) if mfe_pct is not None else None,
        "mae_pct":            round(mae_pct, 4) if mae_pct is not None else None,
        "outcome_updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Batch outcome update (config-gated, default OFF, fire-and-forget caller)
# ---------------------------------------------------------------------------

def update_outcomes(state_store_path: str, config: dict) -> None:
    """Re-examine recent posted alerts and write their observed outcomes.

    Config-gated: returns immediately (zero network calls, zero writes) unless
    ``observation.enable_outcome_tracking`` is True. Each record is processed in
    isolation inside try/except — one bad ticker can never abort the batch.

    Only records that are (a) real posted alerts (safe_for_alert is not False
    and tier != WAIT), (b) not yet finalized (outcome_updated_at is None), and
    (c) within ``observation.outcome_lookback_days`` are evaluated.
    """
    obs_cfg = config.get("observation", {}) or {}
    if not obs_cfg.get("enable_outcome_tracking", False):
        return

    lookback_days = obs_cfg.get("outcome_lookback_days", 30)

    try:
        state = json.loads(Path(state_store_path).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("OUTCOME_LOAD_ERROR: %s: %s", state_store_path, exc)
        return
    if not isinstance(state, dict):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    changed = False

    for ticker, tstate in (state.get("tickers") or {}).items():
        if not isinstance(tstate, dict):
            continue
        for record in tstate.get("alert_history") or []:
            try:
                if record.get("tier") == "WAIT":
                    continue
                if record.get("safe_for_alert") is False:
                    continue
                if record.get("outcome_updated_at") is not None:
                    continue

                if not _within_lookback(record.get("alerted_at"), cutoff):
                    continue

                alert_id = record.get("alert_id")
                if not alert_id:
                    continue

                tkr = record.get("ticker") or ticker
                mres = market_data.fetch_ticker(tkr, config)
                price_df = mres.get("df") if isinstance(mres, dict) else None

                outcome = compute_outcome(record, price_df)
                # Only persist (and mark processed) when an outcome was produced.
                if outcome.get("outcome_updated_at") is None:
                    continue

                state_store.record_outcome(tkr, alert_id, outcome, state)
                changed = True
            except Exception as exc:
                log.warning(
                    "OUTCOME_RECORD_ERROR: %s: %s",
                    record.get("alert_id", "?"), exc,
                )
                continue

    if not changed:
        return

    try:
        Path(state_store_path).write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        log.critical("CRITICAL: outcome state write failed: %s", exc)


def _within_lookback(alerted_at, cutoff: datetime) -> bool:
    """True when alerted_at is missing or newer than cutoff (UTC-aware)."""
    if not alerted_at:
        return True
    try:
        ts = pd.Timestamp(alerted_at).to_pydatetime()
    except Exception:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts >= cutoff


# ---------------------------------------------------------------------------
# Read-only ledger query (research / backtest aggregation)
# ---------------------------------------------------------------------------

def query_ledger(state_store_path: str, group_by_fields=None) -> list[dict]:
    """Aggregate finalized outcomes grouped by evidence label combinations.

    Read-only: loads the state file and returns aggregate statistics. It writes
    NOTHING and mutates no state. Only records with a non-null outcome_updated_at
    are included.

    Returns a list of group dicts, each with the group-by field values plus:
      n, tp1_hit_rate, tp2_hit_rate, tp3_hit_rate, invalidation_rate,
      avg_mfe_pct, avg_mae_pct.
    """
    if group_by_fields is None:
        group_by_fields = ["weekly_trend_state", "four_hour_market_state"]

    try:
        state = json.loads(Path(state_store_path).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("LEDGER_LOAD_ERROR: %s: %s", state_store_path, exc)
        return []
    if not isinstance(state, dict):
        return []

    groups: dict[tuple, list[dict]] = {}
    for _ticker, tstate in (state.get("tickers") or {}).items():
        if not isinstance(tstate, dict):
            continue
        for record in tstate.get("alert_history") or []:
            if record.get("outcome_updated_at") is None:
                continue
            key = tuple(str(record.get(f)) for f in group_by_fields)
            groups.setdefault(key, []).append(record)

    results: list[dict] = []
    for key, recs in groups.items():
        row = {field: key[i] for i, field in enumerate(group_by_fields)}
        row.update({
            "n":                 len(recs),
            "tp1_hit_rate":      _bool_rate(recs, "tp1_hit"),
            "tp2_hit_rate":      _bool_rate(recs, "tp2_hit"),
            "tp3_hit_rate":      _bool_rate(recs, "tp3_hit"),
            "invalidation_rate": _bool_rate(recs, "invalidated"),
            "avg_mfe_pct":       _avg(recs, "mfe_pct"),
            "avg_mae_pct":       _avg(recs, "mae_pct"),
        })
        results.append(row)

    return results


def _bool_rate(records: list[dict], field: str) -> float | None:
    """Fraction of records where field is True, over records where it is not None."""
    vals = [r.get(field) for r in records if r.get(field) is not None]
    if not vals:
        return None
    return round(sum(1 for v in vals if v is True) / len(vals), 4)


def _avg(records: list[dict], field: str) -> float | None:
    vals = [_to_float(r.get(field)) for r in records]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)

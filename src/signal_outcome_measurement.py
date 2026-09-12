"""Phase 92-1B/1C/1D/1E — pure commercial measurement engine.

The live scanner owns judgment.  This module owns only downstream evidence
interpretation over immutable published events plus explicitly future bars.
It performs no market-data fetch, file write, model call, alert, state change,
or strategy mutation.

Contracts implemented:
- raw alert events != independent trading opportunities;
- scheduled customer cohort is separate from manual operator samples;
- future bars must be strictly after the publication event;
- H1/H4/D1/D5 horizons mature only when enough completed future bars exist;
- same-bar target + invalidation is AMBIGUOUS, never guessed;
- pending is not win/loss;
- NEAR_ENTRY is not assigned a conventional win rate;
- lifecycle promotions append evidence without rewriting source events;
- headline rates expose denominator, sample size and Wilson interval.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from src import backtest

VERSION = "PHASE92-1B-E"
OUTCOME_SCHEMA = "published_alert_outcome_v1"
TRAJECTORY_SCHEMA = "published_alert_trajectory_v1"

HORIZONS = {
    "H1": {"kind": "hourly", "bars": 1},
    "H4": {"kind": "hourly", "bars": 4},
    "D1": {"kind": "daily", "bars": 1},
    "D5": {"kind": "daily", "bars": 5},
}
CAPITAL_TIERS = {"STARTER", "SNIPE_IT"}
PUBLIC_TIER_ORDER = {"WAIT": 0, "NEAR_ENTRY": 1, "STARTER": 2, "SNIPE_IT": 3}


def _d(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text + "T00:00:00")
            except ValueError:
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _bar_time(bar: dict) -> datetime | None:
    if not isinstance(bar, dict):
        return None
    return _iso_dt(bar.get("timestamp") or bar.get("time") or bar.get("datetime") or bar.get("date"))


def _bar_fingerprint(bars: list[dict]) -> str:
    payload = json.dumps(bars, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lifecycle_key(event: dict) -> str:
    """Stable opportunity lifecycle key for independence/promotion views.

    Ticker/session/cohort is deliberately conservative: repeated alerts inside
    one session are not automatically independent trades.  A new strategy
    cohort creates a new lifecycle rather than silently pooling versions.
    """
    provenance = _d(event.get("provenance"))
    cohort = provenance.get("strategy_cohort_sha256") or provenance.get("build_commit_sha") or "UNVERSIONED"
    ticker = str(event.get("ticker") or "").upper()
    session = str(event.get("session_date") or "UNKNOWN_SESSION")
    return f"{cohort}|{ticker}|{session}"


def _sent_sort(event: dict):
    dt = _iso_dt(event.get("sent_at") or event.get("scan_started_at"))
    return dt or datetime.min.replace(tzinfo=timezone.utc)


def build_independence_views(events: list[dict]) -> dict:
    """Return raw, transition and independent capital-decision views."""
    rows = [x for x in events if isinstance(x, dict) and x.get("alert_id")]
    rows.sort(key=_sent_sort)
    transitions, capital = [], []
    seen_tiers: dict[str, set[str]] = {}
    capital_seen: set[str] = set()

    for event in rows:
        key = lifecycle_key(event)
        tier = str(_d(event.get("judgment")).get("final_tier") or "WAIT")
        bucket = seen_tiers.setdefault(key, set())
        if tier not in bucket:
            transitions.append(event)
            bucket.add(tier)
        if tier in CAPITAL_TIERS and key not in capital_seen:
            capital.append(event)
            capital_seen.add(key)

    scheduled = [x for x in rows if x.get("origin") == "scheduled_scan"]
    scheduled_capital = [x for x in capital if x.get("origin") == "scheduled_scan"]
    manual = [x for x in rows if x.get("origin") in ("manual_scan", "manual_analyze")]
    return {
        "raw_alert_events": rows,
        "tier_transition_events": transitions,
        "capital_decision_events": capital,
        "scheduled_commercial_events": scheduled,
        "scheduled_capital_decisions": scheduled_capital,
        "manual_operator_events": manual,
        "counts": {
            "raw": len(rows),
            "tier_transitions": len(transitions),
            "capital_decisions": len(capital),
            "scheduled": len(scheduled),
            "scheduled_capital": len(scheduled_capital),
            "manual": len(manual),
        },
    }


def _future_bars(event: dict, bars: list[dict], kind: str) -> list[dict]:
    """Strict chronological filter; alert-day Daily never becomes future proof."""
    sent = _iso_dt(event.get("sent_at") or event.get("scan_started_at"))
    session = str(event.get("session_date") or "")
    out = []
    for raw in bars if isinstance(bars, list) else []:
        if not isinstance(raw, dict):
            continue
        ts = _bar_time(raw)
        if kind == "daily":
            # Daily bars are session-date objects; require date strictly after
            # the alert session, never the unfinished publication-day candle.
            if ts is None or not session:
                continue
            if ts.date().isoformat() <= session:
                continue
        else:
            if ts is None or sent is None or ts <= sent:
                continue
        if not all(_f(raw.get(k)) is not None for k in ("open", "high", "low", "close")):
            out.append(dict(raw))  # preserve invalidity for explicit INVALID_DATA
        else:
            out.append(dict(raw))
    out.sort(key=lambda x: _bar_time(x) or datetime.max.replace(tzinfo=timezone.utc))
    return out


def _flat_alert(event: dict) -> dict:
    judgment = _d(event.get("judgment"))
    geometry = _d(event.get("geometry"))
    proof = _d(event.get("proof"))
    one = _d(proof.get("one_hour"))
    return {
        "final_tier": judgment.get("final_tier"),
        "scan_price": geometry.get("scan_price"),
        "trigger_level": geometry.get("trigger_level"),
        "invalidation_level": geometry.get("invalidation_level"),
        "targets": geometry.get("targets") or [],
        "risk_realism_state": geometry.get("risk_realism_state"),
        "retest_status": one.get("retest_truth"),
        "hold_status": one.get("hold_truth"),
    }


def _return_pct(reference: float | None, close: float | None) -> float | None:
    if reference is None or close is None or reference <= 0:
        return None
    return round((close - reference) / reference * 100.0, 4)


def _risk_r(event: dict, outcome: dict) -> tuple[float | None, float | None]:
    geometry = _d(event.get("geometry"))
    ref = _f(geometry.get("scan_price"))
    inv = _f(geometry.get("invalidation_level"))
    if ref is None or inv is None or ref <= inv:
        return None, None
    risk = ref - inv
    mfe = _f(outcome.get("max_favorable_excursion"))
    mae = _f(outcome.get("max_adverse_excursion"))
    return (
        round(mfe / risk, 4) if mfe is not None else None,
        round(mae / risk, 4) if mae is not None else None,
    )


def evaluate_horizon(event: dict, bars: list[dict], horizon: str) -> dict:
    """Evaluate one immutable event at one predeclared horizon."""
    spec = HORIZONS.get(horizon)
    if spec is None:
        raise ValueError(f"unsupported horizon: {horizon}")
    future = _future_bars(event, bars, spec["kind"])
    needed = int(spec["bars"])
    base = {
        "schema_version": OUTCOME_SCHEMA,
        "measurement_version": VERSION,
        "alert_id": event.get("alert_id"),
        "ticker": event.get("ticker"),
        "origin": event.get("origin"),
        "strategy_cohort_sha256": _d(event.get("provenance")).get("strategy_cohort_sha256"),
        "horizon": horizon,
        "required_completed_bars": needed,
        "available_future_bars": len(future),
        "data_source": "provided_future_bars",
    }
    if len(future) < needed:
        return {**base, "outcome_status": "PENDING", "outcome_label": None,
                "reason": f"Need {needed} completed future {spec['kind']} bar(s); have {len(future)}."}

    used = future[:needed]
    result = backtest.evaluate_alert_outcome(_flat_alert(event), used, horizon_bars=needed)
    label = result.get("outcome_label")
    if label == backtest.AMBIGUOUS_SAME_BAR:
        status = "AMBIGUOUS"
    elif label == backtest.INVALID_DATA:
        status = "INVALID_DATA"
    else:
        status = "MATURED"
    geometry = _d(event.get("geometry"))
    reference = _f(geometry.get("scan_price")) or _f(geometry.get("trigger_level"))
    close = _f(used[-1].get("close"))
    mfe_r, mae_r = _risk_r(event, result)
    return {
        **base,
        "outcome_status": status,
        "outcome_label": label,
        "reference_price": reference,
        "horizon_close": close,
        "return_pct": _return_pct(reference, close),
        "max_favorable_excursion": result.get("max_favorable_excursion"),
        "max_favorable_excursion_pct": result.get("max_favorable_excursion_pct"),
        "max_adverse_excursion": result.get("max_adverse_excursion"),
        "max_adverse_excursion_pct": result.get("max_adverse_excursion_pct"),
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "trigger_reached": result.get("hit_trigger_first"),
        "t1_before_invalidation": result.get("hit_t1_before_invalidation"),
        "invalidation_before_t1": result.get("hit_invalidation_before_t1"),
        "first_terminal_event": result.get("first_hit"),
        "bars_to_target": result.get("bars_to_t1"),
        "bars_to_invalidation": result.get("bars_to_invalidation"),
        "bars_used": len(used),
        "bar_set_sha256": _bar_fingerprint(used),
        "reason": result.get("reason"),
    }


def evaluate_all_horizons(event: dict, *, hourly_bars: list[dict], daily_bars: list[dict]) -> list[dict]:
    return [
        evaluate_horizon(event, hourly_bars if spec["kind"] == "hourly" else daily_bars, horizon)
        for horizon, spec in HORIZONS.items()
    ]


def _blockers(event: dict) -> set[str]:
    proof = _d(event.get("proof"))
    ladder = _d(proof.get("ladder"))
    audit = _d(proof.get("snipe_gate_audit"))
    out = set()
    for key in ("hard_failures", "starter_blockers", "sniper_only_blockers", "soft_caps"):
        for item in _l(ladder.get(key)):
            out.add(str(item))
    for key in ("blocked_gate_names", "missing_proofs", "blocking_reasons"):
        for item in _l(audit.get(key)):
            out.add(str(item))
    return {x for x in out if x}


def build_trajectory(events: list[dict]) -> list[dict]:
    """Link successive lifecycle states without mutating source events."""
    rows = [x for x in events if isinstance(x, dict) and x.get("alert_id")]
    rows.sort(key=_sent_sort)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(lifecycle_key(row), []).append(row)

    links = []
    for key, group in groups.items():
        for earlier, later in zip(group, group[1:]):
            a = str(_d(earlier.get("judgment")).get("final_tier") or "WAIT")
            b = str(_d(later.get("judgment")).get("final_tier") or "WAIT")
            if a == b:
                continue
            before, after = _blockers(earlier), _blockers(later)
            dt_a, dt_b = _sent_sort(earlier), _sent_sort(later)
            elapsed = (dt_b - dt_a).total_seconds() if dt_b >= dt_a else None
            links.append({
                "schema_version": TRAJECTORY_SCHEMA,
                "measurement_version": VERSION,
                "lifecycle_key": key,
                "ticker": earlier.get("ticker"),
                "source_alert_id": earlier.get("alert_id"),
                "later_alert_id": later.get("alert_id"),
                "from_tier": a,
                "to_tier": b,
                "promotion": PUBLIC_TIER_ORDER.get(b, -1) > PUBLIC_TIER_ORDER.get(a, -1),
                "demotion": PUBLIC_TIER_ORDER.get(b, -1) < PUBLIC_TIER_ORDER.get(a, -1),
                "blockers_resolved": sorted(before - after),
                "blockers_added": sorted(after - before),
                "elapsed_seconds": elapsed,
            })
    return links


def _wilson(wins: int, total: int, z: float = 1.959963984540054) -> dict | None:
    if total <= 0:
        return None
    p = wins / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return {"low": round(max(0.0, center - half), 4), "high": round(min(1.0, center + half), 4)}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize_performance(events: list[dict], outcomes: list[dict], *, origin: str = "scheduled_scan") -> dict:
    """Read-only commercial report with explicit denominator semantics."""
    event_map = {x.get("alert_id"): x for x in events if isinstance(x, dict) and x.get("alert_id")}
    selected = [o for o in outcomes if isinstance(o, dict) and event_map.get(o.get("alert_id"), {}).get("origin") == origin]
    horizons: dict[str, dict] = {}
    for horizon in HORIZONS:
        cohort = [o for o in selected if o.get("horizon") == horizon]
        matured = [o for o in cohort if o.get("outcome_status") == "MATURED"]
        pending = [o for o in cohort if o.get("outcome_status") == "PENDING"]
        ambiguous = [o for o in cohort if o.get("outcome_status") == "AMBIGUOUS"]
        invalid = [o for o in cohort if o.get("outcome_status") == "INVALID_DATA"]
        by_tier = {}
        for tier in ("SNIPE_IT", "STARTER", "NEAR_ENTRY"):
            tier_rows = [o for o in matured if _d(event_map.get(o.get("alert_id"))).get("judgment", {}).get("final_tier") == tier]
            wins = [o for o in tier_rows if o.get("outcome_label") == backtest.WIN_T1_BEFORE_INVALIDATION]
            losses = [o for o in tier_rows if o.get("outcome_label") == backtest.LOSS_INVALIDATION_BEFORE_T1]
            decisive = len(wins) + len(losses)
            mfe = [_f(o.get("max_favorable_excursion_pct")) for o in tier_rows]
            mae = [_f(o.get("max_adverse_excursion_pct")) for o in tier_rows]
            record = {
                "matured": len(tier_rows),
                "avg_mfe_pct": _mean([x for x in mfe if x is not None]),
                "avg_mae_pct": _mean([x for x in mae if x is not None]),
            }
            if tier in CAPITAL_TIERS:
                record.update({
                    "decisive_denominator": decisive,
                    "wins": len(wins),
                    "losses": len(losses),
                    "target_first_rate": round(len(wins) / decisive, 4) if decisive else None,
                    "target_first_95ci": _wilson(len(wins), decisive),
                })
            else:
                record.update({
                    "decisive_denominator": None,
                    "wins": None,
                    "losses": None,
                    "target_first_rate": None,
                    "target_first_95ci": None,
                    "note": "NEAR_ENTRY is a no-capital cohort; no conventional win rate is reported.",
                })
            by_tier[tier] = record
        horizons[horizon] = {
            "observations": len(cohort),
            "matured": len(matured),
            "pending": len(pending),
            "ambiguous": len(ambiguous),
            "invalid": len(invalid),
            "by_tier": by_tier,
        }

    transitions = build_trajectory([x for x in events if x.get("origin") == origin])
    near_sources = [x for x in events if x.get("origin") == origin and _d(x.get("judgment")).get("final_tier") == "NEAR_ENTRY"]
    near_ids = {x.get("alert_id") for x in near_sources}
    near_promotions = [x for x in transitions if x.get("source_alert_id") in near_ids and x.get("promotion")]
    starter_to_snipe = [x for x in transitions if x.get("from_tier") == "STARTER" and x.get("to_tier") == "SNIPE_IT"]

    return {
        "measurement_version": VERSION,
        "origin_filter": origin,
        "event_count": sum(1 for x in events if x.get("origin") == origin),
        "horizons": horizons,
        "trajectory": {
            "transition_count": len(transitions),
            "near_entry_source_events": len(near_sources),
            "near_entry_promotions": len(near_promotions),
            "starter_to_snipe_promotions": len(starter_to_snipe),
        },
        "reporting_law": {
            "pending_is_not_failure": True,
            "ambiguous_is_not_win_or_loss": True,
            "manual_samples_mixed_into_headline": False,
            "near_entry_has_win_rate": False,
        },
    }

"""Phase 13.1 — Alert History Backtest Runner.

Offline, read-only CLI runner that connects the Phase 13 pure backtest engine
to real saved scanner alert history.

This module:
- Reads local JSON files only (no network, no yfinance, no live scanner state).
- Normalizes raw alert records into the shape expected by
  src.backtest.evaluate_alert_outcome().
- Pairs each alert with future OHLC bars supplied from a local fixture/file.
- Produces a deterministic summary by tier, risk_realism_state, and
  retest/hold combo.

This module imports nothing from live scanner files except src.backtest.
It does not write files. It does not call Discord, Claude, yfinance, the
scheduler, the state store, or the tiering module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.backtest import (
    evaluate_alert_outcome,
    summarize_backtest_results,
)


# ---------------------------------------------------------------------------
# File I/O — read-only
# ---------------------------------------------------------------------------

def load_json_file(path) -> object:
    """Read JSON from a local file path and return the parsed object.

    The only file-read function in this module. No writes.
    Raises FileNotFoundError if path does not exist.
    Raises json.JSONDecodeError if file content is not valid JSON.
    """
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Field-coalescence helpers
# ---------------------------------------------------------------------------

def _first_present(record: dict, *keys):
    """Return the first key value that is present (not missing) in the record.

    A value of None is considered present; only missing keys are skipped.
    Returns None if no key is present.
    """
    for key in keys:
        if key in record:
            return record[key]
    return None


def _coerce_targets(record: dict) -> list:
    """Coalesce target variants into a list shape consumed by src.backtest.

    Supports:
      - "targets": list (passed through)
      - "target":  single value or list
      - "target_1": single value (wrapped in a list)
    Returns [] if no target field is present.
    """
    if "targets" in record and record["targets"] is not None:
        t = record["targets"]
        return t if isinstance(t, list) else [t]
    if "target" in record and record["target"] is not None:
        t = record["target"]
        return t if isinstance(t, list) else [t]
    if "target_1" in record and record["target_1"] is not None:
        return [record["target_1"]]
    return []


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------

def normalize_alert_record(record: dict) -> dict:
    """Normalize a raw alert-history record into the alert dict consumed by
    src.backtest.evaluate_alert_outcome().

    Tolerates field-name variants commonly seen in saved scanner state:
      ticker
      scan_id
      scan_time / timestamp / alerted_at / created_at
      final_tier / tier
      scan_price / current_price / price
      trigger_level / trigger
      invalidation_level / invalidation
      targets / target / target_1
      risk_reward
      risk_realism_state
      retest_status
      hold_status
      current_acceptance
      overhead_status
      missing_conditions
      upgrade_trigger
    """
    if not isinstance(record, dict):
        return {}

    tier      = _first_present(record, "final_tier", "tier")
    scan_time = _first_present(record, "scan_time", "timestamp", "alerted_at", "created_at")

    return {
        "ticker":              record.get("ticker"),
        "scan_id":             record.get("scan_id"),
        "scan_time":           scan_time,
        "final_tier":          tier,
        "tier":                tier,
        "scan_price":          _first_present(record, "scan_price", "current_price", "price"),
        "trigger_level":       _first_present(record, "trigger_level", "trigger"),
        "invalidation_level":  _first_present(record, "invalidation_level", "invalidation"),
        "targets":             _coerce_targets(record),
        "risk_reward":         record.get("risk_reward"),
        "risk_realism_state":  record.get("risk_realism_state"),
        "retest_status":       record.get("retest_status"),
        "hold_status":         record.get("hold_status"),
        "current_acceptance":  record.get("current_acceptance"),
        "overhead_status":     record.get("overhead_status"),
        "missing_conditions":  record.get("missing_conditions"),
        "upgrade_trigger":     record.get("upgrade_trigger"),
    }


def normalize_ohlc_bars(raw_bars) -> list[dict]:
    """Normalize OHLC bar records into the list-of-dicts shape consumed by
    src.backtest.evaluate_alert_outcome().

    Tolerates field-name variants:
      date / timestamp / time
      open / high / low / close

    Sorts ascending by date/timestamp when comparable. Records that do not
    expose all four OHLC fields (open, high, low, close) are passed through
    unchanged so the backtest engine itself can flag invalid OHLC.
    """
    if not isinstance(raw_bars, list):
        return []

    out: list[dict] = []
    for raw in raw_bars:
        if not isinstance(raw, dict):
            continue
        date_value = _first_present(raw, "date", "timestamp", "time")
        out.append({
            "date":  date_value,
            "open":  raw.get("open"),
            "high":  raw.get("high"),
            "low":   raw.get("low"),
            "close": raw.get("close"),
        })

    if all(b.get("date") is not None for b in out):
        try:
            out.sort(key=lambda b: b["date"])
        except TypeError:
            pass
    return out


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def _both_comparable(a, b) -> bool:
    """True iff a and b are non-None and comparable for ordering."""
    if a is None or b is None:
        return False
    try:
        _ = a < b
        return True
    except TypeError:
        return False


def pair_alerts_with_bars(
    alerts: list[dict],
    bars_by_ticker: dict,
) -> list[dict]:
    """Pair each normalized alert with its future OHLC bars.

    Inputs:
      alerts:         list of normalized alert dicts
      bars_by_ticker: dict[ticker] -> list of normalized OHLC bar dicts

    For each alert:
      - Look up bars by alert['ticker'].
      - If alert['scan_time'] is comparable to bar['date'], select bars whose
        date is strictly greater than scan_time.
      - Otherwise (scan_time missing, dates missing, or types incomparable),
        use all bars for that ticker as supplied.

    Returns a list of {"alert": <dict>, "future_bars": <list>} pairs.
    """
    pairs: list[dict] = []
    for alert in alerts:
        ticker = alert.get("ticker")
        bars   = bars_by_ticker.get(ticker, []) if isinstance(bars_by_ticker, dict) else []

        scan_time = alert.get("scan_time")
        if scan_time is not None and bars and all(b.get("date") is not None for b in bars):
            sample_date = bars[0].get("date")
            if _both_comparable(scan_time, sample_date):
                future = [b for b in bars if b.get("date") > scan_time]
            else:
                future = list(bars)
        else:
            future = list(bars)

        pairs.append({"alert": alert, "future_bars": future})
    return pairs


# ---------------------------------------------------------------------------
# Bars-by-ticker coercion (CLI helper)
# ---------------------------------------------------------------------------

def _coerce_bars_by_ticker(payload) -> dict[str, list[dict]]:
    """Coerce a bars JSON payload into dict[ticker] -> list of bars.

    Supports:
      A. dict of ticker -> list of bars
      B. list of records, each carrying a "ticker" field
    """
    if isinstance(payload, dict):
        out: dict[str, list[dict]] = {}
        for ticker, raw in payload.items():
            out[ticker] = normalize_ohlc_bars(raw)
        return out

    if isinstance(payload, list):
        grouped: dict[str, list[dict]] = {}
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            ticker = raw.get("ticker")
            if ticker is None:
                continue
            grouped.setdefault(ticker, []).append(raw)
        return {ticker: normalize_ohlc_bars(rows) for ticker, rows in grouped.items()}

    return {}


# ---------------------------------------------------------------------------
# Alert-records coercion
# ---------------------------------------------------------------------------

def _coerce_alert_records(payload) -> list[dict]:
    """Extract a flat list of alert records from a JSON payload.

    Supports:
      A. list of alert records
      B. state-store dict: {"tickers": {TICKER: {"alert_history": [...]}}}
      C. dict with "alerts" key: {"alerts": [...]}
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]

    if isinstance(payload, dict):
        if "alerts" in payload and isinstance(payload["alerts"], list):
            return [r for r in payload["alerts"] if isinstance(r, dict)]
        tickers = payload.get("tickers")
        if isinstance(tickers, dict):
            flat: list[dict] = []
            for ticker_state in tickers.values():
                if not isinstance(ticker_state, dict):
                    continue
                history = ticker_state.get("alert_history") or []
                for rec in history:
                    if isinstance(rec, dict):
                        merged = dict(rec)
                        merged.setdefault("ticker", rec.get("ticker"))
                        flat.append(merged)
            return flat
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_alert_history_backtest(
    alert_records: list[dict],
    bars_by_ticker: dict,
    horizon_bars: int = 10,
) -> dict:
    """Normalize alerts, pair them with future bars, run the backtest engine,
    and aggregate results.

    Returns:
      {"results": [...evaluate_alert_outcome dicts...], "summary": {...}}
    """
    normalized_alerts = [normalize_alert_record(r) for r in alert_records]

    if isinstance(bars_by_ticker, dict):
        normalized_bars: dict[str, list[dict]] = {
            ticker: normalize_ohlc_bars(bars)
            for ticker, bars in bars_by_ticker.items()
        }
    else:
        normalized_bars = {}

    pairs = pair_alerts_with_bars(normalized_alerts, normalized_bars)

    results: list[dict] = []
    for pair in pairs:
        result = evaluate_alert_outcome(
            pair["alert"],
            pair["future_bars"],
            horizon_bars=horizon_bars,
        )
        result["ticker"]    = pair["alert"].get("ticker")
        result["scan_id"]   = pair["alert"].get("scan_id")
        result["scan_time"] = pair["alert"].get("scan_time")
        results.append(result)

    summary = summarize_backtest_results(results)
    return {"results": results, "summary": summary}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt_num(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_group(title: str, group: dict) -> list[str]:
    lines = [f"  {title}:"]
    if not group:
        lines.append("    (no decisive groupings)")
        return lines
    for key in sorted(group.keys()):
        v = group[key]
        lines.append(
            f"    - {key}: count={v['count']}, wins={v['wins']}, losses={v['losses']}, "
            f"win_rate={_fmt_pct(v['win_rate'])}, "
            f"avg_mfe_pct={_fmt_num(v['avg_mfe_pct'])}, "
            f"avg_mae_pct={_fmt_num(v['avg_mae_pct'])}"
        )
    return lines


def format_backtest_summary(summary: dict) -> str:
    """Return a deterministic, human-readable text report of a summary dict."""
    if not isinstance(summary, dict):
        return "Backtest Summary\n  (no summary)\n"

    lines: list[str] = ["Backtest Summary"]
    lines.append(f"  total_alerts:    {summary.get('total_alerts', 0)}")
    lines.append(f"  valid_results:   {summary.get('valid_results', 0)}")
    lines.append(f"  invalid_results: {summary.get('invalid_results', 0)}")
    lines.append(f"  wins:            {summary.get('wins', 0)}")
    lines.append(f"  losses:          {summary.get('losses', 0)}")
    lines.append(f"  open:            {summary.get('open', 0)}")
    lines.append(f"  no_trigger:      {summary.get('no_trigger', 0)}")
    lines.append(f"  ambiguous:       {summary.get('ambiguous', 0)}")
    lines.append(f"  win_rate_valid:  {_fmt_pct(summary.get('win_rate_valid'))}")
    lines.append(f"  avg_mfe_pct:     {_fmt_num(summary.get('avg_mfe_pct'))}")
    lines.append(f"  avg_mae_pct:     {_fmt_num(summary.get('avg_mae_pct'))}")
    lines.extend(_format_group("by_tier",               summary.get("by_tier", {})))
    lines.extend(_format_group("by_risk_realism_state", summary.get("by_risk_realism_state", {})))
    lines.extend(_format_group("by_retest_hold_combo",  summary.get("by_retest_hold_combo", {})))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="backtest_alert_history",
        description=(
            "Offline alert-history backtest runner. "
            "Reads a local alerts JSON and a local bars JSON, evaluates each "
            "alert against future OHLC bars, prints a summary. Read-only."
        ),
    )
    parser.add_argument("--alerts",  required=True, help="Path to alerts JSON file.")
    parser.add_argument("--bars",    required=True, help="Path to bars JSON file.")
    parser.add_argument("--horizon", type=int, default=10,
                        help="Max forward bars per alert (default: 10).")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """CLI entrypoint. Returns 0 on success, nonzero on bad input."""
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    try:
        alerts_payload = load_json_file(args.alerts)
    except FileNotFoundError:
        print(f"ERROR: alerts file not found: {args.alerts}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: alerts file is not valid JSON ({exc}).", file=sys.stderr)
        return 3

    try:
        bars_payload = load_json_file(args.bars)
    except FileNotFoundError:
        print(f"ERROR: bars file not found: {args.bars}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: bars file is not valid JSON ({exc}).", file=sys.stderr)
        return 3

    alert_records  = _coerce_alert_records(alerts_payload)
    bars_by_ticker = _coerce_bars_by_ticker(bars_payload)

    output = run_alert_history_backtest(
        alert_records,
        bars_by_ticker,
        horizon_bars=args.horizon,
    )
    print(format_backtest_summary(output["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

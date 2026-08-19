#!/usr/bin/env python3
"""Build a VELOCITY-1D chronological dataset from local JSON inputs.

No network access. Reads a saved scan-telemetry ledger and a local Daily-bar
fixture/history file, writes one deterministic research dataset JSON file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.velocity_dataset import link_velocity_dataset


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bars_by_ticker(payload) -> dict:
    """Accept direct ticker mapping, {bars_by_ticker: ...}, or flat records."""
    if isinstance(payload, dict):
        nested = payload.get("bars_by_ticker")
        if isinstance(nested, dict):
            return nested
        return payload

    if isinstance(payload, list):
        grouped: dict[str, list] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                continue
            bar = {k: v for k, v in row.items() if k != "ticker"}
            grouped.setdefault(ticker, []).append(bar)
        return grouped

    return {}


def build_dataset(telemetry_payload, bars_payload) -> dict:
    return link_velocity_dataset(telemetry_payload, _bars_by_ticker(bars_payload))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build offline five-session/+8% chronological research labels."
    )
    parser.add_argument("--telemetry", required=True, help="Saved scan telemetry JSON ledger")
    parser.add_argument("--bars", required=True, help="Local Daily OHLC JSON by ticker")
    parser.add_argument("--out", required=True, help="Output research dataset JSON")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation (default: 2)")
    args = parser.parse_args(argv)

    telemetry = _load_json(args.telemetry)
    bars = _load_json(args.bars)
    dataset = build_dataset(telemetry, bars)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(dataset, indent=args.indent, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    summary = dataset.get("summary") or {}
    print(
        "VELOCITY-1D dataset written: "
        f"records={summary.get('total_records', 0)} "
        f"capital={summary.get('capital_authorized_observations', 0)} "
        f"watch={summary.get('watch_or_no_capital_observations', 0)} "
        f"out={out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

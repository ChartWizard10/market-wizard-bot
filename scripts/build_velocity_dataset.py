#!/usr/bin/env python3
"""Build a VELOCITY-1D chronological dataset from local research inputs.

No network access. Reads either a saved Phase-14V scan-telemetry ledger or the
CAP-40D forward research archive plus local completed Daily bars, then writes one
deterministic research dataset JSON file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import forward_research_archive
from src.velocity_dataset import link_velocity_dataset


def _load_json(path: str | Path):
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


def _load_ledger(args) -> dict:
    if args.telemetry:
        payload = _load_json(args.telemetry)
        return payload if isinstance(payload, dict) else {}
    return forward_research_archive.load_directory_readonly(
        args.archive_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build offline five-session/+8% chronological research labels."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--telemetry", help="Saved Phase-14V scan telemetry JSON ledger")
    source.add_argument("--archive-dir", help="CAP-40D research archive directory")
    parser.add_argument("--start-date", help="Archive filter YYYY-MM-DD")
    parser.add_argument("--end-date", help="Archive filter YYYY-MM-DD")
    parser.add_argument("--bars", required=True, help="Local Daily OHLC JSON by ticker")
    parser.add_argument("--out", required=True, help="Output research dataset JSON")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation (default: 2)")
    args = parser.parse_args(argv)

    ledger = _load_ledger(args)
    bars = _load_json(args.bars)
    dataset = build_dataset(ledger, bars)

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
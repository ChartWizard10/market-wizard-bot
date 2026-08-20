#!/usr/bin/env python3
"""Build a CAP-40B boundary outcome dataset from local research inputs only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import capacity_boundary_dataset
from src import forward_research_archive


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ledger(args) -> dict:
    if args.telemetry:
        payload = _load(args.telemetry)
        return payload if isinstance(payload, dict) else {}
    return forward_research_archive.load_directory_readonly(
        args.archive_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Link CAP-40 boundary research evidence to future completed Daily bars."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--telemetry", type=Path, help="Saved Phase-14V telemetry ledger")
    source.add_argument("--archive-dir", type=Path, help="CAP-40D research archive directory")
    parser.add_argument("--start-date", help="Archive filter YYYY-MM-DD")
    parser.add_argument("--end-date", help="Archive filter YYYY-MM-DD")
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    ledger = _load_ledger(args)
    bars = _load(args.bars)
    dataset = capacity_boundary_dataset.link_capacity_boundary_dataset(ledger, bars)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(dataset, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
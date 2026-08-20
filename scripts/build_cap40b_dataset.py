#!/usr/bin/env python3
"""Build a CAP-40B boundary outcome dataset from local JSON inputs only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import capacity_boundary_dataset


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Link CAP-40 boundary telemetry to future completed Daily bars."
    )
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    ledger = _load(args.telemetry)
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

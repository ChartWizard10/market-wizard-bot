#!/usr/bin/env python3
"""Build a CAP-40C boundary-study report from local JSON inputs only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import capacity_boundary_study


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the predeclared CAP-40 boundary research report."
    )
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    report = capacity_boundary_study.build_study_report(
        _load(args.dataset),
        _load(args.plan),
        args.as_of,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

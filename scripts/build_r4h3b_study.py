#!/usr/bin/env python3
"""Build an R4H-3B outcome-study report from local JSON artifacts only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.four_hour_outcome_study import build_study_report


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a research-only R4H-3B report from an R4H-3A counterfactual "
            "dataset and a predeclared study plan. No market-data fetch occurs."
        )
    )
    parser.add_argument("--counterfactual", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--coverage", type=Path, default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    dataset = _load(args.counterfactual)
    plan = _load(args.plan)
    coverage = _load(args.coverage) if args.coverage is not None else None

    report = build_study_report(dataset, plan, coverage)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    print(
        f"R4H-3B report: decision={report.get('study_decision')} "
        f"evaluable={report.get('summary', {}).get('evaluable_records')} "
        f"out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

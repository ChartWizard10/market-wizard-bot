#!/usr/bin/env python3
"""Build an R4H-3C independent forward-study report from local JSON only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.four_hour_study_design import build_forward_report


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the research-only R4H-3C independent forward report from "
            "an R4H-3A counterfactual dataset and a predeclared plan."
        )
    )
    parser.add_argument("--counterfactual", required=True, type=Path)
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("research/plans/r4h3_forward_oos_v1.json"),
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    dataset = _load(args.counterfactual)
    plan = _load(args.plan)
    report = build_forward_report(dataset, plan)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    sampling = report.get("sampling") or {}
    print(
        "R4H-3C forward report: "
        f"independent={sampling.get('independent_records')} "
        f"review_ready={report.get('forward_handoff_review_ready')} "
        f"out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Operator-only Phase 92-1F storage verification CLI.

Examples on the deployed Railway service:

    python scripts/verify_signal_outcome_storage.py --write pre-restart-20260912
    python scripts/verify_signal_outcome_storage.py --check pre-restart-20260912

The first command creates an append-only anchor.  After a Railway restart or
redeploy, the second command must find the same anchor.  A single successful
read is not treated as proof of durability; the operator must compare the
pre-restart and post-restart receipts and verify the Railway Volume mount.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

from src import signal_outcome_storage as storage


def _config(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise SystemExit("config must contain a mapping")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Market Wizard commercial-evidence storage.")
    parser.add_argument("--config", default="config/doctrine_config.yaml")
    parser.add_argument("--write", metavar="PROBE_ID", help="append a pre/post-restart durability anchor")
    parser.add_argument("--check", metavar="PROBE_ID", help="verify an exact prior durability anchor")
    parser.add_argument("--note", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    if args.write and args.check:
        parser.error("choose --write or --check, not both")

    config = _config(args.config)
    if args.write:
        result = storage.append_probe(config, args.write, note=args.note)
    elif args.check:
        result = storage.verify_probe(config, args.check)
    else:
        result = storage.storage_health(config)

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    if args.check:
        return 0 if result.get("ok") else 2
    if args.write:
        return 0 if result.get("ok") else 2
    return 0 if result.get("path_collision") is False else 2


if __name__ == "__main__":
    raise SystemExit(main())

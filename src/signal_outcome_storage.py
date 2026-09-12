"""Phase 92-1F — durable commercial-evidence storage verification.

This module is deliberately outside the scanner decision path.  It verifies the
filesystem jurisdiction used by ``signal_outcome_ledger`` and provides an
operator-invoked, append-only durability probe.  A probe can establish a
pre-restart anchor and later prove that the same anchor remains readable after
restart/redeploy when the runtime is backed by a Railway Volume.

No function here changes tiering, capital, routing, dedup, cooldown, cadence,
universe, candidate admission, model calls, or real-4H authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src import signal_outcome_ledger as ledger

VERSION = "PHASE92-1F"
PROBE_SCHEMA = "signal_outcome_durability_probe_v1"
PROBE_FILENAME = "durability_probes.jsonl"


def _text(value: Any, limit: int = 256) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    else:
        value = str(value)
    return value[:limit] if value else None


def health_dir(config: dict | None) -> Path:
    return ledger.ledger_dir(config) / "health"


def probe_path(config: dict | None) -> Path:
    return health_dir(config) / PROBE_FILENAME


def _abs(path: Path) -> Path:
    return path.expanduser().resolve()


def railway_mount_path() -> Path | None:
    raw = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    return _abs(path) if path.is_absolute() else None


def railway_volume_name() -> str | None:
    return _text(os.environ.get("RAILWAY_VOLUME_NAME"))


def mount_alignment(config: dict | None) -> str:
    """Return ALIGNED/MISALIGNED/UNVERIFIED without guessing durability."""
    mount = railway_mount_path()
    if mount is None:
        return "UNVERIFIED"
    root = _abs(ledger.ledger_dir(config))
    try:
        root.relative_to(mount)
    except ValueError:
        return "MISALIGNED"
    return "ALIGNED"


def storage_health(config: dict | None) -> dict:
    """Read-only filesystem health; never creates or repairs storage."""
    root = ledger.ledger_dir(config)
    event_root = ledger.events_dir(config)
    outcome_root = ledger.outcomes_dir(config)
    probe = probe_path(config)
    exists = root.exists()
    directory = root.is_dir() if exists else False
    writable = os.access(root, os.W_OK) if directory else None
    try:
        usage = __import__("shutil").disk_usage(root if directory else root.parent)
        free_bytes = usage.free
        total_bytes = usage.total
    except OSError:
        free_bytes = total_bytes = None
    probe_view = read_probes(config)
    return {
        "schema_version": PROBE_SCHEMA,
        "measurement_version": VERSION,
        "enabled": ledger.enabled(config),
        "path": str(root),
        "path_collision": ledger.path_collision(config),
        "exists": exists,
        "directory": directory,
        "writable": writable,
        "events_directory": event_root.is_dir(),
        "outcomes_directory": outcome_root.is_dir(),
        "probe_file": str(probe),
        "probe_file_exists": probe.is_file(),
        "probe_count": len(probe_view["probes"]),
        "malformed_probe_lines": probe_view["stats"]["malformed_lines"],
        "duplicate_probe_ids": probe_view["stats"]["duplicate_probe_ids"],
        "railway_volume_name": railway_volume_name(),
        "railway_volume_mount_path": str(railway_mount_path()) if railway_mount_path() else None,
        "mount_alignment": mount_alignment(config),
        "free_bytes": free_bytes,
        "total_bytes": total_bytes,
    }


def _probe_id(value: Any) -> str:
    text = _text(value, 128)
    if not text or any(ch.isspace() for ch in text):
        raise ValueError("probe_id must be a non-empty token without whitespace")
    return text


def _probe_fingerprint(row: dict) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _existing_probe_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("probe_id"):
                ids.add(str(row["probe_id"]))
    except OSError:
        return set()
    return ids


def append_probe(config: dict | None, probe_id: str, *, note: str | None = None) -> dict:
    """Append one pre/post-restart anchor without replacing an existing probe."""
    if not ledger.enabled(config):
        return {"ok": True, "status": "disabled", "probe_id": None, "path": None}
    if ledger.path_collision(config):
        return {"ok": False, "status": "path_collision", "probe_id": None, "path": str(ledger.ledger_dir(config))}

    pid = _probe_id(probe_id)
    path = probe_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = _existing_probe_ids(path)
        if pid in existing:
            return {"ok": True, "status": "duplicate_ignored", "probe_id": pid, "path": str(path)}
        row = {
            "schema_version": PROBE_SCHEMA,
            "measurement_version": VERSION,
            "probe_id": pid,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "build_commit_sha": _text(
                os.environ.get("RAILWAY_GIT_COMMIT_SHA")
                or os.environ.get("GITHUB_SHA")
                or os.environ.get("SOURCE_VERSION")
            ),
            "railway_volume_name": railway_volume_name(),
            "railway_volume_mount_path": str(railway_mount_path()) if railway_mount_path() else None,
            "ledger_path": str(_abs(ledger.ledger_dir(config))),
            "note": _text(note, 512),
        }
        row["probe_sha256"] = _probe_fingerprint(row)
        payload = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {"ok": True, "status": "appended", "probe_id": pid, "path": str(path), "probe_sha256": row["probe_sha256"]}
    except Exception as exc:
        return {"ok": False, "status": "write_error", "probe_id": pid, "path": str(path), "error": type(exc).__name__}


def read_probes(config: dict | None) -> dict:
    """Read probes without repairing, rewriting, pruning, or deduplicating them."""
    rows: list[dict] = []
    malformed = 0
    duplicate_ids: set[str] = set()
    seen: set[str] = set()
    path = probe_path(config)
    if not path.exists():
        return {
            "schema_version": PROBE_SCHEMA,
            "probes": [],
            "stats": {"malformed_lines": 0, "duplicate_probe_ids": []},
        }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {
            "schema_version": PROBE_SCHEMA,
            "probes": [],
            "stats": {"malformed_lines": 1, "duplicate_probe_ids": []},
        }
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            malformed += 1
            continue
        if not isinstance(row, dict) or row.get("schema_version") != PROBE_SCHEMA or not row.get("probe_id"):
            malformed += 1
            continue
        pid = str(row["probe_id"])
        if pid in seen:
            duplicate_ids.add(pid)
        seen.add(pid)
        rows.append(row)
    return {
        "schema_version": PROBE_SCHEMA,
        "probes": rows,
        "stats": {
            "malformed_lines": malformed,
            "duplicate_probe_ids": sorted(duplicate_ids),
        },
    }


def verify_probe(config: dict | None, probe_id: str) -> dict:
    """Verify that an exact prior anchor remains readable."""
    pid = _probe_id(probe_id)
    view = read_probes(config)
    matches = [row for row in view["probes"] if row.get("probe_id") == pid]
    health = storage_health(config)
    return {
        "ok": bool(matches) and health["path_collision"] is False,
        "status": "PRESENT" if matches else "MISSING",
        "probe_id": pid,
        "match_count": len(matches),
        "mount_alignment": health["mount_alignment"],
        "malformed_probe_lines": view["stats"]["malformed_lines"],
        "duplicate_probe_ids": view["stats"]["duplicate_probe_ids"],
    }

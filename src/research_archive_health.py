"""CAP-40E — read-only operational health probe for the CAP-40D archive.

This module exists so an authorized operator can verify that forward-study
artifacts are actually appearing in the deployed runtime without shell access.
It is observation only: no writes, no market/model calls, no tier/capital/
routing authority, and no attempt to claim cross-restart durability from a
single snapshot.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src import forward_research_archive as archive

VERSION = "CAP-40E"
_MAX_ERROR_TEXT = 160

STATUS_DISABLED = "DISABLED"
STATUS_PATH_COLLISION = "PATH_COLLISION"
STATUS_MISSING_DIRECTORY = "MISSING_DIRECTORY"
STATUS_EMPTY = "EMPTY"
STATUS_DEGRADED = "DEGRADED"
STATUS_READY = "READY"


def _text(value: Any, cap: int = _MAX_ERROR_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:cap] if value else None


def _partition_paths(directory: Path) -> list[Path]:
    paths: list[Path] = []
    try:
        candidates = directory.glob("*.jsonl") if directory.is_dir() else []
        for path in candidates:
            if archive._date_from_filename(path) is not None:
                paths.append(path)
    except Exception:
        return []
    return sorted(paths, key=lambda p: p.stem)


def _read_edge_batch(path: Path, *, newest: bool) -> tuple[dict | None, int, str | None]:
    """Return first/last valid JSONL batch, malformed-line count, read error."""
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return None, 0, type(exc).__name__

    iterable = reversed(lines) if newest else iter(lines)
    for line in iterable:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            malformed += 1
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("traces"), list):
            malformed += 1
            continue
        return payload, malformed, None
    return None, malformed, None


def _now_session_date(config: dict | None, now: datetime | None) -> str:
    scan = config.get("scan") if isinstance(config, dict) else None
    scan = scan if isinstance(scan, dict) else {}
    tz_name = scan.get("timezone") or archive.DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(archive.DEFAULT_TIMEZONE)
    current = now if isinstance(now, datetime) else datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)
    return current.date().isoformat()


def snapshot(config: dict | None, *, now: datetime | None = None) -> dict:
    """Build a bounded, read-only archive-health snapshot. Never raises."""
    base = {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "routing_authority": False,
        "durability_proven": False,
        "status": STATUS_DEGRADED,
        "enabled": archive.enabled(config),
        "archive_path": str(archive.archive_dir(config)),
        "retention_days": archive.retention_days(config),
        "daily_file_limit_bytes": archive.max_daily_file_bytes(config),
        "current_session_date": _now_session_date(config, now),
        "partition_count": 0,
        "total_partition_bytes": 0,
        "oldest_partition": None,
        "newest_partition": None,
        "current_partition_present": False,
        "oldest_scan_id": None,
        "oldest_scan_timestamp": None,
        "latest_scan_id": None,
        "latest_scan_timestamp": None,
        "latest_trace_count": None,
        "latest_partition_bytes": None,
        "latest_partition_malformed_tail_lines": 0,
        "read_error": None,
        "durability_note": (
            "A single snapshot proves archive presence, not persistence across restart/redeploy. "
            "Compare a pre-restart scan_id/bytes anchor after restart."
        ),
    }

    try:
        if not base["enabled"]:
            base["status"] = STATUS_DISABLED
            return base
        if archive.path_collision(config):
            base["status"] = STATUS_PATH_COLLISION
            return base

        directory = archive.archive_dir(config)
        if not directory.exists() or not directory.is_dir():
            base["status"] = STATUS_MISSING_DIRECTORY
            return base

        paths = _partition_paths(directory)
        if not paths:
            base["status"] = STATUS_EMPTY
            return base

        sizes = []
        for path in paths:
            try:
                sizes.append(path.stat().st_size)
            except Exception:
                sizes.append(0)

        base["partition_count"] = len(paths)
        base["total_partition_bytes"] = sum(sizes)
        base["oldest_partition"] = paths[0].stem
        base["newest_partition"] = paths[-1].stem
        base["current_partition_present"] = any(
            path.stem == base["current_session_date"] for path in paths
        )
        base["latest_partition_bytes"] = sizes[-1]

        oldest, oldest_malformed, oldest_error = _read_edge_batch(paths[0], newest=False)
        latest, latest_malformed, latest_error = _read_edge_batch(paths[-1], newest=True)
        base["latest_partition_malformed_tail_lines"] = latest_malformed

        if isinstance(oldest, dict):
            base["oldest_scan_id"] = _text(oldest.get("scan_id"), 512)
            base["oldest_scan_timestamp"] = _text(oldest.get("scan_timestamp"), 512)
        if isinstance(latest, dict):
            base["latest_scan_id"] = _text(latest.get("scan_id"), 512)
            base["latest_scan_timestamp"] = _text(latest.get("scan_timestamp"), 512)
            try:
                base["latest_trace_count"] = int(latest.get("trace_count"))
            except (TypeError, ValueError, OverflowError):
                base["latest_trace_count"] = None

        error = latest_error or oldest_error
        if error:
            base["read_error"] = _text(error)
            base["status"] = STATUS_DEGRADED
            return base

        if latest is None or oldest is None:
            base["status"] = STATUS_DEGRADED
            return base

        # A malformed trailing partial line is surfaced as degradation even if
        # an earlier valid batch can be recovered. It may indicate a killed
        # writer and should be operationally visible, not silently normalized.
        if latest_malformed > 0 or oldest_malformed > 0:
            base["status"] = STATUS_DEGRADED
            return base

        base["status"] = STATUS_READY
        return base
    except Exception as exc:
        base["read_error"] = _text(type(exc).__name__)
        base["status"] = STATUS_DEGRADED
        return base


def render(snapshot_value: dict | None) -> str:
    s = snapshot_value if isinstance(snapshot_value, dict) else {}
    status = s.get("status") or STATUS_DEGRADED
    latest_id = s.get("latest_scan_id") or "—"
    latest_ts = s.get("latest_scan_timestamp") or "—"
    oldest_id = s.get("oldest_scan_id") or "—"
    newest = s.get("newest_partition") or "—"
    oldest = s.get("oldest_partition") or "—"
    current = s.get("current_session_date") or "—"
    error = s.get("read_error") or "—"
    return (
        "**CAP-40D Research Archive Status**\n"
        f"Status: **{status}** | Enabled: {bool(s.get('enabled'))}\n"
        f"Path: `{s.get('archive_path') or '—'}`\n"
        f"Partitions: {s.get('partition_count', 0)} | Range: {oldest} → {newest}\n"
        f"Bytes: total={s.get('total_partition_bytes', 0)} | latest={s.get('latest_partition_bytes') or 0}\n"
        f"Current ET session: {current} | Current partition present: {bool(s.get('current_partition_present'))}\n"
        f"Oldest anchor scan: `{oldest_id}`\n"
        f"Latest anchor scan: `{latest_id}` | {latest_ts} | traces={s.get('latest_trace_count')}\n"
        f"Malformed latest-tail lines: {s.get('latest_partition_malformed_tail_lines', 0)} | Read error: {error}\n"
        "Durability proven by this snapshot: **NO** — compare the anchor scan/bytes after Railway restart/redeploy."
    )

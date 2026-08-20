"""CAP-40D — durable forward-study archive beside bounded scan telemetry.

Phase-14V intentionally keeps a bounded ring buffer.  CAP-40C and R4H-3C need
multi-week forward cohorts, so their already-built compact research evidence
must survive ring rollover without turning research persistence into trading
authority.

This module is deliberately isolated:

* it copies only whitelisted fields from already-built scan traces;
* it never calls market data or a model;
* it never mutates tiering, capital, routing, suppression, state, or the trace;
* write/read failures never raise into the scanner;
* the read path is strictly read-only and ignores malformed JSONL lines;
* files are date-partitioned and retention-bounded independently of Phase-14V.

A Railway/container filesystem is durable only if the deployment mounts durable
storage.  Repository code cannot prove that operational fact; the runbook owns
that validation requirement.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src import scan_telemetry

log = logging.getLogger(__name__)

VERSION = "CAP-40D"
DEFAULT_DIRNAME = "research_archive"
DEFAULT_RETENTION_DAYS = 120
DEFAULT_MAX_DAILY_FILE_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEZONE = "America/New_York"
_MAX_TEXT = 512
_MAX_LIST = 8

_PIPELINE_KEYS = (
    "market_data_ok",
    "prefilter_eligible",
    "prefilter_rank",
    "prefilter_score",
    "admitted_to_deep_analysis",
    "claude_analyzed",
)

_VELOCITY_KEYS = (
    "version",
    "research_only",
    "capital_authority",
    "tier_authority",
    "observed_at",
    "ready",
    "missing",
    "reference_price",
    "reference_source",
    "invalidation_level",
    "target_return_pct",
    "horizon_sessions",
    "feasibility_status",
    "known_path_room_pct",
    "atr_pct",
    "required_move_atr",
    "final_tier",
    "capital_authorized_at_observation",
    "primary_family",
    "four_hour_state",
    "four_hour_proxy_state",
    "four_hour_proxy_agreement",
)

_FOUR_HOUR_KEYS = (
    "status",
    "authority_mode",
    "structural_state",
    "location_state",
    "readiness",
    "last_closed_time",
    "live_bar_available",
    "last_closed_source_complete",
    "confirmed_history_bars",
    "structural_segment_bars",
    "history_gap_detected",
    "freshness_status",
    "proxy_state",
    "proxy_agreement",
    "missing_proofs",
)

_CAPACITY_KEYS = (
    "version",
    "research_only",
    "observational_only",
    "model_authority",
    "candidate_cap_authority",
    "tier_authority",
    "capital_authority",
    "routing_authority",
    "forecast_authority",
    "scan_id",
    "ticker",
    "observed_at",
    "rank",
    "current_cap",
    "proposed_cap",
    "band",
    "ready",
    "missing",
    "reference_price",
    "reference_source",
    "invalidation_level",
    "invalidation_source",
    "target_return_pct",
    "horizon_sessions",
    "feasibility_status",
    "known_path_room_pct",
    "atr_pct",
    "required_move_atr",
    "prefilter_score",
    "admission_rank_score",
    "admission_source",
    "primary_family",
    "family_state",
    "family_score",
    "family_watch_ready",
    "family_admission_ready",
    "family_entry_structure_valid",
    "family_rr_to_t1",
    "retest_status",
    "overhead_status",
    "estimated_rr",
)


def _cfg(config: dict | None) -> dict:
    if not isinstance(config, dict):
        return {}
    value = config.get("research_archive")
    return value if isinstance(value, dict) else {}


def enabled(config: dict | None) -> bool:
    """Archive is opt-in so minimal/unit-test configs never write implicitly."""
    return _cfg(config).get("enabled") is True


def _positive_int(value: Any, default: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return out if out > 0 else default


def retention_days(config: dict | None) -> int:
    return _positive_int(
        _cfg(config).get("retention_days"), DEFAULT_RETENTION_DAYS
    )


def max_daily_file_bytes(config: dict | None) -> int:
    return _positive_int(
        _cfg(config).get("max_daily_file_bytes"),
        DEFAULT_MAX_DAILY_FILE_BYTES,
    )


def _state_path(config: dict | None) -> Path:
    state = config.get("state") if isinstance(config, dict) else None
    state = state if isinstance(state, dict) else {}
    return Path(state.get("state_file") or ".state/alert_history.json")


def archive_dir(config: dict | None) -> Path:
    configured = _cfg(config).get("directory")
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip())
    return _state_path(config).parent / DEFAULT_DIRNAME


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return True


def path_collision(config: dict | None) -> bool:
    """Refuse configurations that point the archive directory at state files."""
    try:
        directory = archive_dir(config)
        return _same_path(directory, _state_path(config)) or _same_path(
            directory, scan_telemetry.telemetry_path(config)
        )
    except Exception:
        return True


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    if isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    try:
        text = str(value)
    except Exception:
        return None
    return text[:_MAX_TEXT]


def _list(value: Any) -> list:
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value[:_MAX_LIST]:
        projected = _scalar(item)
        if projected is not None:
            out.append(projected)
    return out


def _project_mapping(value: Any, keys: tuple[str, ...], list_keys=()) -> dict | None:
    if not isinstance(value, dict) or not value:
        return None
    out = {}
    for key in keys:
        if key not in value:
            continue
        if key in list_keys:
            out[key] = _list(value.get(key))
        else:
            projected = _scalar(value.get(key))
            if projected is not None or value.get(key) is None:
                out[key] = projected
    return out or None


def project_trace(trace: dict | None) -> dict | None:
    """Whitelist one already-built scan trace for long-horizon research.

    Traces that contain none of the forward-study blocks are deliberately
    omitted.  In normal production this keeps analyzed ranks 1-30 (VELOCITY /
    real 4H) and CAP-40 boundary ranks 21-40, while ranks 41-60 remain solely
    in the ordinary bounded near-cut ledger.
    """
    if not isinstance(trace, dict):
        return None

    velocity = _project_mapping(
        trace.get("velocity_observation"), _VELOCITY_KEYS, ("missing",)
    )
    four_hour = _project_mapping(
        trace.get("four_hour_real"), _FOUR_HOUR_KEYS, ("missing_proofs",)
    )
    capacity = _project_mapping(
        trace.get("capacity_boundary_observation"),
        _CAPACITY_KEYS,
        ("missing",),
    )

    if not any((velocity, four_hour, capacity)):
        return None

    out = {
        "archive_projection_version": VERSION,
        "schema_version": _scalar(trace.get("schema_version")),
        "scan_id": _scalar(trace.get("scan_id")),
        "ticker": _scalar(trace.get("ticker")),
        "trace_kind": _scalar(trace.get("trace_kind")),
    }
    pipeline = _project_mapping(trace.get("pipeline"), _PIPELINE_KEYS)
    if pipeline:
        out["pipeline"] = pipeline
    if velocity:
        out["velocity_observation"] = velocity
    if four_hour:
        out["four_hour_real"] = four_hour
    if capacity:
        out["capacity_boundary_observation"] = capacity
    return out


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        # Scheduler scan timestamps are currently naive UTC.  Preserve that
        # declared historical contract rather than treating them as local time.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def session_date(scan_timestamp: Any, timezone_name: str = DEFAULT_TIMEZONE) -> str | None:
    dt = _parse_timestamp(scan_timestamp)
    if dt is None:
        return None
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    try:
        return dt.astimezone(tz).date().isoformat()
    except Exception:
        return None


def build_scan_batch(
    scan_id: Any,
    scan_timestamp: Any,
    traces: list | tuple | None,
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict | None:
    projected = []
    for trace in traces or []:
        item = project_trace(trace)
        if item is not None:
            projected.append(item)
    if not projected:
        return None

    day = session_date(scan_timestamp, timezone_name)
    if day is None:
        return None

    return {
        "archive_version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "routing_authority": False,
        "candidate_cap_authority": False,
        "scan_id": _scalar(scan_id),
        "scan_timestamp": _scalar(scan_timestamp),
        "session_date": day,
        "trace_count": len(projected),
        "traces": projected,
    }


def _date_from_filename(path: Path) -> date | None:
    if path.suffix != ".jsonl":
        return None
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def _prune(directory: Path, current_session: date, days: int) -> int:
    """Best-effort partition pruning; only CAP-40D YYYY-MM-DD.jsonl files."""
    cutoff = current_session - timedelta(days=days)
    removed = 0
    try:
        for path in directory.glob("*.jsonl"):
            file_date = _date_from_filename(path)
            if file_date is None or file_date >= cutoff:
                continue
            try:
                path.unlink()
                removed += 1
            except Exception as exc:
                log.warning("RESEARCH_ARCHIVE_PRUNE_SKIPPED: %s: %s", path, exc)
    except Exception as exc:
        log.warning("RESEARCH_ARCHIVE_PRUNE_ERROR: %s", exc)
    return removed


def append_scan_batch(
    config: dict | None,
    scan_id: Any,
    scan_timestamp: Any,
    traces: list | tuple | None,
) -> dict:
    """Append one scan's study projection.  Never raises into the scanner."""
    if not enabled(config):
        return {"ok": True, "written": False, "reason": "disabled"}

    try:
        if path_collision(config):
            log.error(
                "RESEARCH_ARCHIVE_PATH_COLLISION: refusing write; state/telemetry untouched"
            )
            return {"ok": False, "written": False, "reason": "path_collision"}

        scan_cfg = config.get("scan") if isinstance(config, dict) else None
        scan_cfg = scan_cfg if isinstance(scan_cfg, dict) else {}
        tz_name = scan_cfg.get("timezone") or DEFAULT_TIMEZONE
        batch = build_scan_batch(scan_id, scan_timestamp, traces, timezone_name=tz_name)
        if batch is None:
            return {"ok": True, "written": False, "reason": "no_research_traces"}

        directory = archive_dir(config)
        if directory.exists() and not directory.is_dir():
            return {"ok": False, "written": False, "reason": "archive_path_not_directory"}
        directory.mkdir(parents=True, exist_ok=True)

        day = date.fromisoformat(batch["session_date"])
        pruned = _prune(directory, day, retention_days(config))
        path = directory / f"{batch['session_date']}.jsonl"

        line = json.dumps(batch, allow_nan=False, separators=(",", ":")) + "\n"
        encoded = line.encode("utf-8")
        ceiling = max_daily_file_bytes(config)
        current_size = path.stat().st_size if path.exists() else 0
        if current_size + len(encoded) > ceiling:
            log.error(
                "RESEARCH_ARCHIVE_DAILY_LIMIT: %s current=%d incoming=%d limit=%d",
                path,
                current_size,
                len(encoded),
                ceiling,
            )
            return {
                "ok": False,
                "written": False,
                "reason": "daily_file_limit",
                "path": str(path),
                "trace_count": batch["trace_count"],
                "pruned_files": pruned,
            }

        # One compact line per scan. O_APPEND semantics plus the scheduler's
        # scan lock prevent offset races in the normal single-process runtime.
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

        return {
            "ok": True,
            "written": True,
            "reason": "written",
            "path": str(path),
            "session_date": batch["session_date"],
            "trace_count": batch["trace_count"],
            "bytes_appended": len(encoded),
            "pruned_files": pruned,
        }
    except Exception as exc:
        log.warning("RESEARCH_ARCHIVE_WRITE_ERROR: %s", exc)
        return {
            "ok": False,
            "written": False,
            "reason": "write_error",
            "error_class": type(exc).__name__,
        }


def _parse_date_filter(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except (ValueError, AttributeError):
            return None
    return None


def load_directory_readonly(
    directory: str | Path,
    *,
    start_date: Any = None,
    end_date: Any = None,
) -> dict:
    """Read archive partitions without writing, repairing, or quarantining."""
    root = Path(directory)
    start = _parse_date_filter(start_date)
    end = _parse_date_filter(end_date)
    traces: list[dict] = []
    files_read = 0
    batch_lines = 0
    malformed_lines = 0
    ignored_files = 0

    try:
        paths = sorted(root.glob("*.jsonl")) if root.is_dir() else []
    except Exception:
        paths = []

    for path in paths:
        file_date = _date_from_filename(path)
        if file_date is None:
            ignored_files += 1
            continue
        if start is not None and file_date < start:
            continue
        if end is not None and file_date > end:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            malformed_lines += 1
            continue

        files_read += 1
        for line in lines:
            if not line.strip():
                continue
            try:
                batch = json.loads(line)
            except Exception:
                malformed_lines += 1
                continue
            if not isinstance(batch, dict) or not isinstance(batch.get("traces"), list):
                malformed_lines += 1
                continue
            batch_lines += 1
            for trace in batch["traces"]:
                projected = project_trace(trace)
                if projected is not None:
                    traces.append(projected)

    return {
        "schema_version": VERSION,
        "archive_scope": "forward_research",
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "decision_traces": traces,
        "archive_stats": {
            "files_read": files_read,
            "batch_lines": batch_lines,
            "malformed_lines_skipped": malformed_lines,
            "ignored_nonpartition_files": ignored_files,
            "decision_traces": len(traces),
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
        },
    }


def load_archive_ledger_readonly(
    config: dict | None,
    *,
    start_date: Any = None,
    end_date: Any = None,
) -> dict:
    """Config-aware read-only ledger adapter for existing research consumers."""
    try:
        if path_collision(config):
            return load_directory_readonly(
                Path("/__research_archive_unavailable__"),
                start_date=start_date,
                end_date=end_date,
            )
        return load_directory_readonly(
            archive_dir(config), start_date=start_date, end_date=end_date
        )
    except Exception:
        return load_directory_readonly(
            Path("/__research_archive_unavailable__"),
            start_date=start_date,
            end_date=end_date,
        )

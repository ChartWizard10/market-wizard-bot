"""Phase 92-1A — immutable published-alert event ledger.

Records what Market Wizard actually published to Discord at the scan moment.
This is measurement infrastructure only: it has no market-data/model calls and
zero strategy, tier, capital, routing, dedup, cooldown, or outcome authority.

Only a successful Discord delivery may become a published event.  Event rows
are append-only scan-time truth.  Future outcome workers write separate rows
and may never rewrite these events.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

VERSION = "PHASE92-1A"
SCHEMA_VERSION = "published_alert_event_v1"
DEFAULT_DIRNAME = "signal_outcomes"
DEFAULT_TIMEZONE = "America/New_York"

ORIGIN_SCHEDULED_SCAN = "scheduled_scan"
ORIGIN_MANUAL_SCAN = "manual_scan"
ORIGIN_MANUAL_ANALYZE = "manual_analyze"
ORIGIN_LEGACY_IMPORT = "legacy_import"
VALID_ORIGINS = {
    ORIGIN_SCHEDULED_SCAN,
    ORIGIN_MANUAL_SCAN,
    ORIGIN_MANUAL_ANALYZE,
    ORIGIN_LEGACY_IMPORT,
}

_BUILD_SHA_ENV_KEYS = (
    "RAILWAY_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "SOURCE_VERSION",
    "COMMIT_SHA",
)
_MAX_TEXT = 2048
_MAX_LIST = 64
_MAX_DEPTH = 5


def _cfg(config: dict | None) -> dict:
    if not isinstance(config, dict):
        return {}
    value = config.get("signal_outcomes")
    return value if isinstance(value, dict) else {}


def enabled(config: dict | None) -> bool:
    return _cfg(config).get("enabled") is True


def _state_path(config: dict | None) -> Path:
    state = config.get("state") if isinstance(config, dict) else None
    state = state if isinstance(state, dict) else {}
    return Path(state.get("state_file") or ".state/alert_history.json")


def ledger_dir(config: dict | None) -> Path:
    configured = _cfg(config).get("directory")
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip())
    return _state_path(config).parent / DEFAULT_DIRNAME


def events_dir(config: dict | None) -> Path:
    return ledger_dir(config) / "events"


def outcomes_dir(config: dict | None) -> Path:
    return ledger_dir(config) / "outcomes"


def _research_archive_dir(config: dict | None) -> Path:
    research = config.get("research_archive") if isinstance(config, dict) else None
    research = research if isinstance(research, dict) else {}
    configured = research.get("directory")
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip())
    return _state_path(config).parent / "research_archive"


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def path_collision(config: dict | None) -> bool:
    """Commercial evidence must own a separate storage jurisdiction."""
    try:
        root = ledger_dir(config)
        state = _state_path(config)
        research = _research_archive_dir(config)
        values = {_norm(root), _norm(events_dir(config)), _norm(outcomes_dir(config))}
        forbidden = {_norm(state), _norm(state.parent / "scan_telemetry.json"), _norm(research)}
        return bool(values & forbidden)
    except Exception:
        return True


def _finite(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _text(value: Any, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, (bool, int)):
        return str(value)[:limit]
    if isinstance(value, float) and math.isfinite(value):
        return str(value)[:limit]
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value[:_MAX_LIST]:
        text = _text(item)
        if text:
            out.append(text)
    return out


def _safe(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in value[:_MAX_LIST]]
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:256]:
            name = _text(key, 256)
            if name is not None:
                out[name] = _safe(item, depth + 1)
        return out
    return None


def _sha(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint(value: Any) -> str | None:
    try:
        payload = json.dumps(
            _safe(value), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except Exception:
        return None
    return _sha(payload)


def resolve_build_commit_sha() -> str | None:
    for key in _BUILD_SHA_ENV_KEYS:
        value = os.environ.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:128]
    return None


def _parse_dt(value: Any) -> datetime | None:
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
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _timezone(config: dict | None) -> ZoneInfo:
    scan = config.get("scan") if isinstance(config, dict) else None
    scan = scan if isinstance(scan, dict) else {}
    try:
        return ZoneInfo(str(scan.get("timezone") or DEFAULT_TIMEZONE))
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def session_date(scan_started_at: Any, config: dict | None) -> str | None:
    dt = _parse_dt(scan_started_at)
    if dt is None:
        return None
    try:
        return dt.astimezone(_timezone(config)).date().isoformat()
    except Exception:
        return None


def universe_fingerprint(tickers: list | tuple | None) -> str | None:
    if not isinstance(tickers, (list, tuple)):
        return None
    symbols = [str(x).strip().upper() for x in tickers if isinstance(x, str) and x.strip()]
    return _fingerprint(symbols) if symbols else None


def _projection(mapping: Any, keys: tuple[str, ...]) -> dict | None:
    if not isinstance(mapping, dict):
        return None
    out = {key: _safe(mapping.get(key)) for key in keys if key in mapping}
    return out or None


def _one_hour(tr: dict) -> dict | None:
    one = tr.get("one_hour_entry")
    if not isinstance(one, dict):
        return None
    prh = one.get("pullback_retest_hold") if isinstance(one.get("pullback_retest_hold"), dict) else {}
    candle = one.get("candle_truth") if isinstance(one.get("candle_truth"), dict) else {}
    bar = one.get("bar_context") if isinstance(one.get("bar_context"), dict) else {}
    return {
        "status": _text(one.get("status")),
        "data_freshness": _text(one.get("data_freshness")),
        "trigger_state": _text(one.get("trigger_state")),
        "score": _finite(one.get("score")),
        "score_label": _text(one.get("score_label")),
        "alert_truth_label": _text(one.get("alert_truth_label")),
        "retest_truth": _text(prh.get("retest_truth")),
        "hold_truth": _text(prh.get("hold_truth")),
        "pullback_truth": _text(prh.get("pullback_truth")),
        "candle_event_type": _text(candle.get("event_type")),
        "closed_candle_confirms": candle.get("closed_candle_confirms") if isinstance(candle.get("closed_candle_confirms"), bool) else None,
        "using_live_bar_for_confirmation": bar.get("using_live_bar_for_confirmation") if isinstance(bar.get("using_live_bar_for_confirmation"), bool) else None,
        "last_closed_bar_time": _text(bar.get("last_closed_bar_time")),
        "current_live_bar_time": _text(bar.get("current_live_bar_time")),
        "hard_caps_applied": _strings(one.get("hard_caps_applied")),
        "downgrade_reasons": _strings(one.get("downgrade_reasons")),
    }


def _timeframes(tr: dict) -> dict | None:
    tf = tr.get("timeframe_alignment")
    if not isinstance(tf, dict):
        return None

    def layer(name: str) -> dict | None:
        return _projection(tf.get(name), ("timeframe", "role", "state", "blocks_trigger", "evidence", "warnings"))

    return {
        "status": _text(tf.get("status")),
        "alignment_grade": _text(tf.get("alignment_grade")),
        "alignment_score": _finite(tf.get("alignment_score")),
        "alignment_label": _text(tf.get("alignment_label")),
        "weekly": layer("campaign_timeframe"),
        "daily": layer("swing_timeframe"),
        "four_hour_proxy": layer("operational_timeframe"),
        "one_hour": layer("trigger_timeframe"),
        "conflicts": _safe(tf.get("conflicts")),
        "missing_context": _strings(tf.get("missing_context")),
        "hard_caps_applied": _strings(tf.get("hard_caps_applied")),
        "downgrade_reasons": _strings(tf.get("downgrade_reasons")),
    }


def _four_hour(tr: dict) -> dict | None:
    four = tr.get("four_hour_operational")
    if not isinstance(four, dict):
        return None
    bar = four.get("bar_context") if isinstance(four.get("bar_context"), dict) else {}
    return {
        "status": _text(four.get("status")),
        "engine_version": _text(four.get("engine_version")),
        "authority_mode": _text(four.get("authority_mode")),
        "structural_state": _text(four.get("structural_state")),
        "state_confidence": _text(four.get("state_confidence")),
        "operational_location": _text(four.get("operational_location")),
        "operational_readiness": _text(four.get("operational_readiness")),
        "bar_context": {
            "last_closed_4h_time": _text(bar.get("last_closed_4h_time")),
            "current_live_4h_time": _text(bar.get("current_live_4h_time")),
            "live_bar_available": bar.get("live_bar_available") if isinstance(bar.get("live_bar_available"), bool) else None,
            "last_closed_source_complete": bar.get("last_closed_source_complete") if isinstance(bar.get("last_closed_source_complete"), bool) else None,
            "using_live_bar_for_confirmation": bar.get("using_live_bar_for_confirmation") if isinstance(bar.get("using_live_bar_for_confirmation"), bool) else None,
            "freshness_status": _text(bar.get("freshness_status")),
        },
        "retest_truth": _safe(four.get("retest_truth")),
        "hold_truth": _safe(four.get("hold_truth")),
        "invalidation_quality": _safe(four.get("invalidation_quality")),
        "target_path": _safe(four.get("target_path")),
        "daily_relationship": _text(four.get("daily_relationship")),
        "hard_failures": _strings(four.get("hard_failures")),
        "soft_warnings": _strings(four.get("soft_warnings")),
        "missing_proofs": _strings(four.get("missing_proofs")),
    }


def _ladder(tr: dict) -> dict | None:
    return _projection(tr.get("snipe_ladder"), (
        "internal_ladder_tier", "public_signal_tier",
        "existing_final_tier_recommendation", "capital_action_recommendation",
        "opportunity_lane", "starter_grade", "sniper_grade", "base_alive",
        "proof_state", "proof_failure", "structure_state", "location_state",
        "trigger_state", "candle_state", "risk_state", "hard_failures",
        "starter_blockers", "sniper_only_blockers", "soft_caps", "info_notes",
        "basket_reason", "why_this_ladder_tier", "why_not_higher", "why_not_lower",
        "next_promotion_proof", "failure_condition", "audit_tags",
        "snipe_capital_floor_violation",
    ))


def _audit(tr: dict) -> dict | None:
    return _projection(tr.get("snipe_gate_audit"), (
        "audit_label", "promotion_state", "snipe_score", "snipe_grade",
        "eligible_for_snipe_review", "blocked_gate_names", "blocked_gates",
        "missing_proofs", "promotion_triggers", "blocking_reasons",
    ))


def _event_id(scan_id: str, ticker: str, tier: str, dedup_key: str | None,
              origin: str, scan_started_at: str) -> str:
    basis = "|".join((VERSION, scan_id, ticker.upper(), tier, dedup_key or "", origin, scan_started_at))
    return "mw_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def build_published_event(*, ticker: str, tiering_result: dict,
                          dedup_decision: dict | None, send_result: dict,
                          config: dict, scan_id: str, scan_started_at: str,
                          system_prompt: str, origin: str,
                          tickers: list | tuple | None = None,
                          sent_at: str | None = None,
                          market_snapshot_at: str | None = None) -> dict:
    if origin not in VALID_ORIGINS:
        raise ValueError(f"unsupported signal origin: {origin}")
    if not isinstance(send_result, dict) or send_result.get("sent") is not True:
        raise ValueError("published event requires send_result.sent == True")
    day = session_date(scan_started_at, config)
    if day is None:
        raise ValueError("scan_started_at is required for immutable event chronology")

    tr = deepcopy(tiering_result) if isinstance(tiering_result, dict) else {}
    signal = tr.get("final_signal") if isinstance(tr.get("final_signal"), dict) else {}
    dedup = dedup_decision if isinstance(dedup_decision, dict) else {}
    tier = _text(tr.get("final_tier")) or "WAIT"
    dedup_key = _text(dedup.get("dedup_key"))
    delivered_at = sent_at or datetime.now(timezone.utc).isoformat()
    one, tf, four, ladder, audit = _one_hour(tr), _timeframes(tr), _four_hour(tr), _ladder(tr), _audit(tr)
    daily_permission = None
    if isinstance(tf, dict) and isinstance(tf.get("daily"), dict):
        daily_permission = _text(tf["daily"].get("state"))

    config_fp = _fingerprint(config)
    prompt_fp = _sha(system_prompt)
    universe_fp = universe_fingerprint(tickers)
    build_sha = resolve_build_commit_sha()
    model = _text(os.environ.get("ANTHROPIC_MODEL") or (config.get("claude") or {}).get("model"))
    cohort_fp = _fingerprint({
        "build_commit_sha": build_sha,
        "model": model,
        "config_sha256": config_fp,
        "prompt_sha256": prompt_fp,
        "universe_sha256": universe_fp,
    })

    event = {
        "schema_version": SCHEMA_VERSION,
        "measurement_version": VERSION,
        "measurement_authority": {
            "strategy_authority": False, "tier_authority": False,
            "capital_authority": False, "routing_authority": False,
            "outcome_authority": False,
        },
        "alert_id": _event_id(scan_id, ticker, tier, dedup_key, origin, scan_started_at),
        "scan_id": _text(scan_id),
        "ticker": _text(ticker.upper()),
        "origin": origin,
        "scan_started_at": _text(scan_started_at),
        "market_snapshot_at": _text(market_snapshot_at or signal.get("market_snapshot_at") or signal.get("scan_timestamp")),
        "sent_at": _text(delivered_at),
        "session_date": day,
        "delivery": {
            "sent": True,
            "channel_id": _text(send_result.get("channel_id")),
            "message_count": _finite(send_result.get("message_count") or send_result.get("chunks") or send_result.get("chunk_count")),
            "dedup_reason": _text(dedup.get("reason")),
            "dedup_key": dedup_key,
        },
        "provenance": {
            "build_commit_sha": build_sha,
            "provider": "anthropic",
            "model": model,
            "config_sha256": config_fp,
            "prompt_sha256": prompt_fp,
            "universe_sha256": universe_fp,
            "strategy_cohort_sha256": cohort_fp,
        },
        "judgment": {
            "final_tier": tier,
            "ladder_basket": _text((ladder or {}).get("internal_ladder_tier")),
            "original_claude_tier": _text(tr.get("original_claude_tier")),
            "score": _finite(tr.get("score")),
            "raw_score": _finite(tr.get("raw_score")),
            "capital_action": _text(tr.get("capital_action") or signal.get("capital_action")),
            "final_discord_channel": _text(tr.get("final_discord_channel")),
            "safe_for_alert": tr.get("safe_for_alert") if isinstance(tr.get("safe_for_alert"), bool) else None,
            "applied_vetoes": _strings(tr.get("applied_vetoes")),
        },
        "geometry": {
            "scan_price": _finite(signal.get("scan_price")),
            "trigger_level": _finite(signal.get("trigger_level")),
            "invalidation_level": _finite(signal.get("invalidation_level")),
            "invalidation_condition": _text(signal.get("invalidation_condition")),
            "targets": _safe(signal.get("targets") or []),
            "risk_reward": _finite(signal.get("risk_reward")),
            "risk_distance": _finite(signal.get("risk_distance")),
            "risk_distance_pct": _finite(signal.get("risk_distance_pct")),
            "risk_realism_state": _text(signal.get("risk_realism_state")),
            "overhead_status": _text(signal.get("overhead_status")),
        },
        "setup": {
            "setup_family": _text(signal.get("setup_family")),
            "entry_archetype": _text(signal.get("entry_archetype")),
            "structure_event": _text(signal.get("structure_event")),
            "trend_state": _text(signal.get("trend_state")),
            "zone_type": _text(signal.get("zone_type")),
            "sma_value_alignment": _text(signal.get("sma_value_alignment")),
            "current_acceptance": _text(signal.get("current_acceptance")),
        },
        "proof": {
            "daily_permission": daily_permission,
            "one_hour": one,
            "four_hour": four,
            "timeframe_alignment": tf,
            "candle_evidence": _safe(tr.get("candle_evidence")),
            "snipe_gate_audit": audit,
            "ladder": ladder,
            "missing_conditions": _safe(signal.get("missing_conditions")),
            "upgrade_trigger": _text(signal.get("upgrade_trigger")),
        },
        "narrative": {
            "reason": _text(signal.get("reason")),
            "sanitized_reason": _text(signal.get("sanitized_reason")),
            "sanitized_next_action": _text(signal.get("sanitized_next_action")),
            "why_this_tier": _text((ladder or {}).get("why_this_ladder_tier")),
            "why_not_higher": _text((ladder or {}).get("why_not_higher")),
            "next_promotion_proof": _safe((ladder or {}).get("next_promotion_proof")),
        },
    }
    event["event_sha256"] = _fingerprint(event)
    return event


def _event_file(config: dict | None, day: str) -> Path:
    return events_dir(config) / f"{day}.jsonl"


def _contains_id(path: Path, alert_id: str) -> bool:
    if not path.exists():
        return False
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if alert_id not in raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("alert_id") == alert_id:
                return True
    except Exception:
        return False
    return False


def append_published_event(**kwargs) -> dict:
    config = kwargs.get("config")
    send_result = kwargs.get("send_result")
    if not enabled(config):
        return {"ok": True, "status": "disabled", "alert_id": None, "path": None}
    if not isinstance(send_result, dict) or send_result.get("sent") is not True:
        return {"ok": True, "status": "not_published", "alert_id": None, "path": None}
    if path_collision(config):
        return {"ok": False, "status": "path_collision", "alert_id": None, "path": str(ledger_dir(config))}
    try:
        event = build_published_event(**kwargs)
        path = _event_file(config, event["session_date"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if _contains_id(path, event["alert_id"]):
            return {"ok": True, "status": "duplicate_ignored", "alert_id": event["alert_id"], "path": str(path)}
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {"ok": True, "status": "appended", "alert_id": event["alert_id"], "path": str(path), "event_sha256": event["event_sha256"]}
    except Exception as exc:
        log.error("SIGNAL_OUTCOME_LEDGER_WRITE_ERROR: %s", exc)
        return {"ok": False, "status": "write_error", "alert_id": None, "path": None, "error": type(exc).__name__}


def load_events_readonly(config: dict | None) -> dict:
    """Read all event partitions without repairing or mutating anything."""
    rows, malformed = [], 0
    duplicate_ids, seen = set(), set()
    root = events_dir(config)
    try:
        paths = sorted(root.glob("*.jsonl")) if root.is_dir() else []
    except Exception:
        paths = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            malformed += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if not isinstance(row, dict) or row.get("schema_version") != SCHEMA_VERSION:
                malformed += 1
                continue
            aid = row.get("alert_id")
            if aid in seen:
                duplicate_ids.add(aid)
            seen.add(aid)
            rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "events": rows,
        "stats": {
            "events": len(rows),
            "malformed_lines": malformed,
            "duplicate_alert_ids": sorted(x for x in duplicate_ids if x),
            "scheduled_events": sum(1 for x in rows if x.get("origin") == ORIGIN_SCHEDULED_SCAN),
            "manual_events": sum(1 for x in rows if x.get("origin") in (ORIGIN_MANUAL_SCAN, ORIGIN_MANUAL_ANALYZE)),
        },
    }


def health(config: dict | None) -> dict:
    ledger = load_events_readonly(config)
    rows = ledger["events"]
    return {
        "enabled": enabled(config),
        "path": str(ledger_dir(config)),
        "path_collision": path_collision(config),
        "event_count": len(rows),
        "last_event_sent_at": rows[-1].get("sent_at") if rows else None,
        "malformed_lines": ledger["stats"]["malformed_lines"],
        "duplicate_alert_ids": len(ledger["stats"]["duplicate_alert_ids"]),
    }

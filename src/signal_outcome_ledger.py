"""Phase 92-1A — immutable published-alert event ledger.

This module records what Market Wizard actually published to Discord at the
exact scan moment.  It is measurement infrastructure only:

* no market-data calls;
* no model calls;
* no tier/capital/routing authority;
* no dedup/cooldown authority;
* no scanner-state mutation;
* no future-outcome calculation.

The record is written only after ``send_alert`` reports successful Discord
delivery.  Scan-time truth is projected from the already-built deterministic
judgment object and stored append-only.  Future Phase-92 outcome workers may
append outcome records elsewhere, but they must never rewrite these events.
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
_MAX_DICT_DEPTH = 5


def _cfg(config: dict | None) -> dict:
    if not isinstance(config, dict):
        return {}
    value = config.get("signal_outcomes")
    return value if isinstance(value, dict) else {}


def enabled(config: dict | None) -> bool:
    """Opt-in by config so existing/minimal test configs never write implicitly."""
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


def _research_archive_dir(config: dict | None) -> Path:
    research = config.get("research_archive") if isinstance(config, dict) else None
    research = research if isinstance(research, dict) else {}
    configured = research.get("directory")
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip())
    return _state_path(config).parent / "research_archive"


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return True


def path_collision(config: dict | None) -> bool:
    """Refuse storage that collides with operational state or research archive."""
    try:
        directory = ledger_dir(config)
        return (
            _same_path(directory, _state_path(config))
            or _same_path(directory, _research_archive_dir(config))
        )
    except Exception:
        return True


def _finite_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _text(value: Any, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    elif isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        text = str(value)
    else:
        return None
    return text[:limit]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value[:_MAX_LIST]:
        text = _text(item)
        if text:
            out.append(text)
    return out


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Bounded JSON-safe copy used for evidence projections and fingerprints."""
    if depth > _MAX_DICT_DEPTH:
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
        return [_json_safe(v, depth + 1) for v in value[:_MAX_LIST]]
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:256]:
            key_text = _text(key, 256)
            if key_text is None:
                continue
            out[key_text] = _json_safe(item, depth + 1)
        return out
    return None


def _sha256_text(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint(value: Any) -> str | None:
    try:
        safe = _json_safe(value)
        payload = json.dumps(
            safe,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except Exception:
        return None
    return _sha256_text(payload)


def resolve_build_commit_sha() -> str | None:
    for key in _BUILD_SHA_ENV_KEYS:
        value = os.environ.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:128]
    return None


def _parse_datetime(value: Any) -> datetime | None:
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

    # Scheduler scan timestamps use datetime.utcnow().isoformat(), so naive
    # values have a declared UTC meaning in the production codebase.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _timezone(config: dict | None) -> ZoneInfo:
    scan = config.get("scan") if isinstance(config, dict) else None
    scan = scan if isinstance(scan, dict) else {}
    name = scan.get("timezone") or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(str(name))
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def session_date(scan_started_at: Any, config: dict | None) -> str:
    dt = _parse_datetime(scan_started_at) or datetime.now(timezone.utc)
    return dt.astimezone(_timezone(config)).date().isoformat()


def _read_universe_from_config(config: dict | None) -> list[str]:
    scan = config.get("scan") if isinstance(config, dict) else None
    scan = scan if isinstance(scan, dict) else {}
    path = Path(scan.get("ticker_file") or "config/tickers.txt")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        symbol = raw.strip().upper()
        if not symbol or symbol.startswith("#"):
            continue
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def universe_fingerprint(tickers: list | tuple | None, config: dict | None) -> str | None:
    symbols: list[str] = []
    source = list(tickers) if isinstance(tickers, (list, tuple)) else _read_universe_from_config(config)
    for raw in source:
        if not isinstance(raw, str):
            continue
        symbol = raw.strip().upper()
        if symbol:
            symbols.append(symbol)
    return _fingerprint(symbols) if symbols else None


def _projection(mapping: Any, keys: tuple[str, ...]) -> dict | None:
    if not isinstance(mapping, dict):
        return None
    out = {}
    for key in keys:
        if key in mapping:
            out[key] = _json_safe(mapping.get(key))
    return out or None


def _one_hour_projection(tiering_result: dict) -> dict | None:
    one = tiering_result.get("one_hour_entry")
    if not isinstance(one, dict):
        return None
    prh = one.get("pullback_retest_hold") if isinstance(one.get("pullback_retest_hold"), dict) else {}
    candle = one.get("candle_truth") if isinstance(one.get("candle_truth"), dict) else {}
    bar = one.get("bar_context") if isinstance(one.get("bar_context"), dict) else {}
    return {
        "status": _text(one.get("status")),
        "data_freshness": _text(one.get("data_freshness")),
        "trigger_state": _text(one.get("trigger_state")),
        "score": _finite_number(one.get("score")),
        "score_label": _text(one.get("score_label")),
        "alert_truth_label": _text(one.get("alert_truth_label")),
        "retest_truth": _text(prh.get("retest_truth")),
        "hold_truth": _text(prh.get("hold_truth")),
        "pullback_truth": _text(prh.get("pullback_truth")),
        "retest_zone_type": _text(prh.get("retest_zone_type")),
        "candle_event_type": _text(candle.get("event_type")),
        "closed_candle_confirms": candle.get("closed_candle_confirms") if isinstance(candle.get("closed_candle_confirms"), bool) else None,
        "using_live_bar_for_confirmation": bar.get("using_live_bar_for_confirmation") if isinstance(bar.get("using_live_bar_for_confirmation"), bool) else None,
        "last_closed_bar_time": _text(bar.get("last_closed_bar_time")),
        "current_live_bar_time": _text(bar.get("current_live_bar_time")),
        "hard_caps_applied": _string_list(one.get("hard_caps_applied")),
        "downgrade_reasons": _string_list(one.get("downgrade_reasons")),
    }


def _timeframe_projection(tiering_result: dict) -> dict | None:
    tf = tiering_result.get("timeframe_alignment")
    if not isinstance(tf, dict):
        return None

    def _layer(name: str) -> dict | None:
        layer = tf.get(name)
        if not isinstance(layer, dict):
            return None
        return _projection(layer, ("timeframe", "role", "state", "blocks_trigger", "evidence", "warnings"))

    return {
        "status": _text(tf.get("status")),
        "alignment_grade": _text(tf.get("alignment_grade")),
        "alignment_score": _finite_number(tf.get("alignment_score")),
        "alignment_label": _text(tf.get("alignment_label")),
        "weekly": _layer("campaign_timeframe"),
        "daily": _layer("swing_timeframe"),
        "four_hour_proxy": _layer("operational_timeframe"),
        "one_hour": _layer("trigger_timeframe"),
        "conflicts": _json_safe(tf.get("conflicts")),
        "missing_context": _string_list(tf.get("missing_context")),
        "hard_caps_applied": _string_list(tf.get("hard_caps_applied")),
        "downgrade_reasons": _string_list(tf.get("downgrade_reasons")),
    }


def _four_hour_projection(tiering_result: dict) -> dict | None:
    four = tiering_result.get("four_hour_operational")
    if not isinstance(four, dict):
        return None
    return _projection(
        four,
        (
            "status",
            "authority_mode",
            "structural_state",
            "location_state",
            "readiness",
            "last_closed_time",
            "live_bar_available",
            "freshness_status",
            "missing_proofs",
            "proxy_comparison",
        ),
    )


def _ladder_projection(tiering_result: dict) -> dict | None:
    ladder = tiering_result.get("snipe_ladder")
    if not isinstance(ladder, dict):
        return None
    return _projection(
        ladder,
        (
            "internal_ladder_tier",
            "proof_state",
            "why_this_tier",
            "why_not_higher",
            "next_promotion_proof",
            "hard_failures",
            "starter_blockers",
            "sniper_only_blockers",
            "snipe_capital_floor_violation",
        ),
    )


def _audit_projection(tiering_result: dict) -> dict | None:
    audit = tiering_result.get("snipe_gate_audit")
    if not isinstance(audit, dict):
        return None
    return _projection(
        audit,
        (
            "audit_label",
            "promotion_state",
            "snipe_score",
            "snipe_grade",
            "eligible_for_snipe_review",
            "blocked_gate_names",
            "missing_proofs",
            "promotion_triggers",
            "blocking_reasons",
        ),
    )


def _event_id(
    scan_id: str,
    ticker: str,
    final_tier: str,
    dedup_key: str | None,
    origin: str,
) -> str:
    basis = "|".join(
        [VERSION, scan_id, ticker.upper(), final_tier, dedup_key or "", origin]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
    return f"mw_{digest}"


def build_published_event(
    *,
    ticker: str,
    tiering_result: dict,
    dedup_decision: dict | None,
    send_result: dict,
    config: dict,
    scan_id: str,
    scan_started_at: str,
    system_prompt: str,
    origin: str,
    tickers: list | tuple | None = None,
    sent_at: str | None = None,
    market_snapshot_at: str | None = None,
) -> dict:
    """Project immutable scan-time truth for one successfully published alert."""
    if origin not in VALID_ORIGINS:
        raise ValueError(f"unsupported signal origin: {origin}")
    if not isinstance(send_result, dict) or send_result.get("sent") is not True:
        raise ValueError("published event requires send_result.sent == True")

    tr = deepcopy(tiering_result) if isinstance(tiering_result, dict) else {}
    final_signal = tr.get("final_signal") if isinstance(tr.get("final_signal"), dict) else {}
    dedup = dedup_decision if isinstance(dedup_decision, dict) else {}
    final_tier = _text(tr.get("final_tier")) or "WAIT"
    dedup_key = _text(dedup.get("dedup_key"))
    now = sent_at or datetime.now(timezone.utc).isoformat()

    one = _one_hour_projection(tr)
    timeframe = _timeframe_projection(tr)
    four = _four_hour_projection(tr)
    ladder = _ladder_projection(tr)
    audit = _audit_projection(tr)

    daily_state = None
    if isinstance(timeframe, dict) and isinstance(timeframe.get("daily"), dict):
        daily_state = _text(timeframe["daily"].get("state"))

    event = {
        "schema_version": SCHEMA_VERSION,
        "measurement_version": VERSION,
        "measurement_authority": {
            "strategy_authority": False,
            "tier_authority": False,
            "capital_authority": False,
            "routing_authority": False,
            "outcome_authority": False,
        },
        "alert_id": _event_id(scan_id, ticker, final_tier, dedup_key, origin),
        "scan_id": _text(scan_id),
        "ticker": _text(ticker.upper()),
        "origin": origin,
        "scan_started_at": _text(scan_started_at),
        "market_snapshot_at": _text(
            market_snapshot_at
            or final_signal.get("market_snapshot_at")
            or final_signal.get("scan_timestamp")
        ),
        "sent_at": _text(now),
        "session_date": session_date(scan_started_at, config),
        "delivery": {
            "sent": True,
            "channel_id": _text(send_result.get("channel_id")),
            "chunks": _finite_number(send_result.get("chunks") or send_result.get("chunk_count")),
            "dedup_reason": _text(dedup.get("reason")),
            "dedup_key": dedup_key,
        },
        "provenance": {
            "build_commit_sha": resolve_build_commit_sha(),
            "provider": "anthropic",
            "model": _text(os.environ.get("ANTHROPIC_MODEL") or (config.get("claude") or {}).get("model")),
            "config_sha256": _fingerprint(config),
            "prompt_sha256": _sha256_text(system_prompt),
            "universe_sha256": universe_fingerprint(tickers, config),
        },
        "judgment": {
            "final_tier": final_tier,
            "ladder_basket": _text((ladder or {}).get("internal_ladder_tier")),
            "original_claude_tier": _text(tr.get("original_claude_tier")),
            "score": _finite_number(tr.get("score")),
            "raw_score": _finite_number(tr.get("raw_score")),
            "capital_action": _text(tr.get("capital_action") or final_signal.get("capital_action")),
            "final_discord_channel": _text(tr.get("final_discord_channel")),
            "safe_for_alert": tr.get("safe_for_alert") if isinstance(tr.get("safe_for_alert"), bool) else None,
            "applied_vetoes": _string_list(tr.get("applied_vetoes")),
        },
        "geometry": {
            "scan_price": _finite_number(final_signal.get("scan_price")),
            "trigger_level": _finite_number(final_signal.get("trigger_level")),
            "invalidation_level": _finite_number(final_signal.get("invalidation_level")),
            "invalidation_condition": _text(final_signal.get("invalidation_condition")),
            "targets": _json_safe(final_signal.get("targets") or []),
            "risk_reward": _finite_number(final_signal.get("risk_reward")),
            "risk_distance": _finite_number(final_signal.get("risk_distance")),
            "risk_distance_pct": _finite_number(final_signal.get("risk_distance_pct")),
            "current_price_to_invalidation": _finite_number(final_signal.get("current_price_to_invalidation")),
            "current_price_to_invalidation_pct": _finite_number(final_signal.get("current_price_to_invalidation_pct")),
            "risk_realism_state": _text(final_signal.get("risk_realism_state")),
            "overhead_status": _text(final_signal.get("overhead_status")),
        },
        "setup": {
            "setup_family": _text(final_signal.get("setup_family")),
            "entry_archetype": _text(final_signal.get("entry_archetype")),
            "structure_event": _text(final_signal.get("structure_event")),
            "trend_state": _text(final_signal.get("trend_state")),
            "zone_type": _text(final_signal.get("zone_type")),
            "sma_value_alignment": _text(final_signal.get("sma_value_alignment")),
            "current_acceptance": _text(final_signal.get("current_acceptance")),
        },
        "proof": {
            "daily_permission": daily_state,
            "one_hour": one,
            "four_hour": four,
            "timeframe_alignment": timeframe,
            "candle_evidence": _json_safe(tr.get("candle_evidence")),
            "snipe_gate_audit": audit,
            "ladder": ladder,
            "missing_conditions": _json_safe(final_signal.get("missing_conditions")),
            "upgrade_trigger": _text(final_signal.get("upgrade_trigger")),
        },
        "narrative": {
            "reason": _text(final_signal.get("reason")),
            "sanitized_reason": _text(final_signal.get("sanitized_reason")),
            "sanitized_next_action": _text(final_signal.get("sanitized_next_action")),
            "why_this_tier": _text((ladder or {}).get("why_this_tier")),
            "why_not_higher": _text((ladder or {}).get("why_not_higher")),
            "next_promotion_proof": _text((ladder or {}).get("next_promotion_proof")),
        },
    }

    # Integrity fingerprint excludes itself by construction.
    event["event_sha256"] = _fingerprint(event)
    return event


def _events_dir(config: dict | None) -> Path:
    return ledger_dir(config) / "events"


def _event_file(config: dict | None, date_text: str) -> Path:
    return _events_dir(config) / f"{date_text}.jsonl"


def _contains_alert_id(path: Path, alert_id: str) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if alert_id not in raw:
                    continue
                try:
                    row = json.loads(raw)
                except Exception:
                    continue
                if isinstance(row, dict) and row.get("alert_id") == alert_id:
                    return True
    except Exception as exc:
        log.warning("SIGNAL_LEDGER_DEDUP_READ_ERROR: %s", exc)
    return False


def append_published_event(
    *,
    ticker: str,
    tiering_result: dict,
    dedup_decision: dict | None,
    send_result: dict,
    config: dict,
    scan_id: str,
    scan_started_at: str,
    system_prompt: str,
    origin: str,
    tickers: list | tuple | None = None,
    sent_at: str | None = None,
    market_snapshot_at: str | None = None,
) -> dict:
    """Append one published alert event exactly once within its date partition.

    Never raises into the scanner.  A failed write returns ``ok=False`` so the
    scheduler can surface operational degradation while preserving trading
    judgment and Discord delivery truth.
    """
    if not enabled(config):
        return {"ok": True, "status": "disabled", "alert_id": None, "path": None}
    if not isinstance(send_result, dict) or send_result.get("sent") is not True:
        return {"ok": True, "status": "not_published", "alert_id": None, "path": None}
    if path_collision(config):
        return {
            "ok": False,
            "status": "path_collision",
            "alert_id": None,
            "path": str(ledger_dir(config)),
        }

    try:
        event = build_published_event(
            ticker=ticker,
            tiering_result=tiering_result,
            dedup_decision=dedup_decision,
            send_result=send_result,
            config=config,
            scan_id=scan_id,
            scan_started_at=scan_started_at,
            system_prompt=system_prompt,
            origin=origin,
            tickers=tickers,
            sent_at=sent_at,
            market_snapshot_at=market_snapshot_at,
        )
        path = _event_file(config, event["session_date"])
        path.parent.mkdir(parents=True, exist_ok=True)
        alert_id = event["alert_id"]
        if _contains_alert_id(path, alert_id):
            return {
                "ok": True,
                "status": "duplicate_ignored",
                "alert_id": alert_id,
                "path": str(path),
            }

        payload = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass

        return {
            "ok": True,
            "status": "appended",
            "alert_id": alert_id,
            "path": str(path),
            "event_sha256": event.get("event_sha256"),
        }
    except Exception as exc:  # pragma: no cover - scanner isolation boundary
        log.error("SIGNAL_OUTCOME_LEDGER_WRITE_ERROR: %s", exc)
        return {
            "ok": False,
            "status": "write_error",
            "alert_id": None,
            "path": None,
            "error": str(exc),
        }

"""Persistent alert history and deduplication state.

Decides whether a validated signal should alert, be suppressed as a duplicate,
or be eligible for re-alert. Does not decide trade quality. Does not change
final_tier. Does not call Discord, Claude, yfinance, or the scheduler.
"""

import json
import logging
import math
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_STATE_PATH = "data/alert_state.json"

_TIER_RANK: dict[str, int] = {
    "WAIT":       0,
    "NEAR_ENTRY": 1,
    "STARTER":    2,
    "SNIPE_IT":   3,
}


# ---------------------------------------------------------------------------
# Path and empty state
# ---------------------------------------------------------------------------

def _state_path(config: dict) -> Path:
    path_str = (config.get("state") or {}).get("state_file", _DEFAULT_STATE_PATH)
    return Path(path_str)


def _empty_state() -> dict:
    return {
        "tickers": {},
        "meta": {
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "total_alerts": 0,
        },
    }


# ---------------------------------------------------------------------------
# Dedup key
# ---------------------------------------------------------------------------

def make_dedup_key(
    ticker: str,
    tier: str,
    trigger_level,
    invalidation_level,
) -> str:
    """Build a normalized dedup key: ticker|tier|trigger|invalidation."""
    def _fmt(v) -> str:
        if v is None:
            return "null"
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return str(v)

    return f"{ticker}|{tier}|{_fmt(trigger_level)}|{_fmt(invalidation_level)}"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _backup_corrupt(path: Path) -> None:
    suffix = f".corrupt.{int(time.time())}"
    backup = path.with_name(path.name + suffix)
    try:
        shutil.move(str(path), str(backup))
        log.warning("Corrupt state file backed up to %s", backup)
    except Exception as exc:
        log.error("Could not back up corrupt state file: %s", exc)


def load(config: dict) -> dict:
    """Load alert history from state file. Returns empty state if missing or corrupt."""
    path = _state_path(config)

    if not path.exists():
        log.info("State file not found at %s — initializing empty state", path)
        return _empty_state()

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "tickers" not in data:
            raise ValueError("invalid state structure: missing 'tickers' key")
        return data
    except Exception as exc:
        log.warning("Corrupt state file at %s: %s — backing up and resetting", path, exc)
        _backup_corrupt(path)
        return _empty_state()


def save(state: dict, config: dict) -> None:
    """Persist state to file. Logs CRITICAL on write failure — does not raise."""
    path = _state_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        log.critical("CRITICAL: state write failed: %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _within_cooldown(last_alerted_at: str | None, cooldown_minutes: int) -> bool:
    if not last_alerted_at:
        return False
    try:
        last = datetime.fromisoformat(last_alerted_at)
        now = datetime.utcnow() if last.tzinfo is None else datetime.now(timezone.utc)
        return (now - last).total_seconds() / 60 < cooldown_minutes
    except Exception:
        return False


def _tier_rank(tier: str | None) -> int:
    return _TIER_RANK.get(tier or "WAIT", 0)


def _is_material_change(old_val, new_val, fraction_threshold: float) -> bool:
    """True if change between old_val and new_val exceeds fraction_threshold."""
    if old_val is None and new_val is None:
        return False
    if old_val is None or new_val is None:
        return True   # one side null, other non-null → treat as material
    try:
        old_f, new_f = float(old_val), float(new_val)
        ref = abs(old_f) if abs(old_f) > 1e-9 else abs(new_f)
        if ref < 1e-9:
            return old_f != new_f
        return abs(new_f - old_f) / ref > fraction_threshold
    except (TypeError, ValueError):
        return str(old_val) != str(new_val)


def _no_alert(reason: str, dedup_key: str, ticker_state) -> dict:
    return {
        "should_alert": False,
        "reason": reason,
        "dedup_key": dedup_key,
        "previous_state": ticker_state,
    }


def _yes_alert(reason: str, dedup_key: str, ticker_state) -> dict:
    return {
        "should_alert": True,
        "reason": reason,
        "dedup_key": dedup_key,
        "previous_state": ticker_state,
    }


# ---------------------------------------------------------------------------
# Main dedup decision
# ---------------------------------------------------------------------------

def check_alert(
    tiering_result: dict,
    state: dict,
    config: dict,
    manual_override: bool = False,
) -> dict:
    """Decide whether to alert, suppress, or re-alert.

    Does NOT modify state. Caller must call record_alert + save when
    should_alert is True.

    Hard blocks — cannot be bypassed by manual_override:
      final_tier == WAIT, safe_for_alert == False, final_discord_channel == none
    """
    final_tier    = tiering_result.get("final_tier", "WAIT")
    final_channel = tiering_result.get("final_discord_channel", "none")
    safe          = tiering_result.get("safe_for_alert", False)
    final_signal  = tiering_result.get("final_signal") or {}

    ticker            = final_signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")
    trigger_level     = final_signal.get("trigger_level")
    invalidation_level = final_signal.get("invalidation_level")

    dedup_key    = make_dedup_key(ticker, final_tier, trigger_level, invalidation_level)
    ticker_state = state.get("tickers", {}).get(ticker)

    # ---- Hard blocks (not bypassable) ----
    if final_tier == "WAIT":
        return _no_alert("wait_no_alert", dedup_key, ticker_state)
    if not safe:
        return _no_alert("unsafe_for_alert", dedup_key, ticker_state)
    if final_channel == "none":
        return _no_alert("unsafe_for_alert", dedup_key, ticker_state)

    # ---- First-time ticker ----
    if not ticker_state or not ticker_state.get("last_alerted_at"):
        return _yes_alert("new_signal", dedup_key, ticker_state)

    # ---- Manual override (bypasses dedup/cooldown) ----
    if manual_override:
        return _yes_alert("manual_override", dedup_key, ticker_state)

    state_cfg         = config.get("state", {})
    cooldown_minutes  = state_cfg.get("cooldown_minutes", 240)
    trigger_pct       = state_cfg.get("trigger_material_change_pct", 0.25) / 100
    inval_pct         = state_cfg.get("invalidation_material_change_pct", 0.25) / 100

    last_tier         = ticker_state.get("last_alerted_tier")
    last_trigger      = ticker_state.get("last_trigger_level")
    last_invalidation = ticker_state.get("last_invalidation_level")
    last_alerted_at   = ticker_state.get("last_alerted_at")
    in_cooldown       = _within_cooldown(last_alerted_at, cooldown_minutes)

    # ---- Re-alert rules (apply before cooldown check) ----

    # Tier improvement
    if _tier_rank(final_tier) > _tier_rank(last_tier):
        return _yes_alert("tier_improved", dedup_key, ticker_state)

    # Material trigger change
    if _is_material_change(last_trigger, trigger_level, trigger_pct):
        return _yes_alert("trigger_changed", dedup_key, ticker_state)

    # Material invalidation change
    if _is_material_change(last_invalidation, invalidation_level, inval_pct):
        return _yes_alert("invalidation_changed", dedup_key, ticker_state)

    # ---- Cooldown ----
    if in_cooldown:
        return _no_alert("duplicate_suppressed", dedup_key, ticker_state)

    # Cooldown expired — re-alert
    return _yes_alert("cooldown_expired", dedup_key, ticker_state)


# ---------------------------------------------------------------------------
# State update
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 14H.1: compact SNIPE gate-audit snapshot for the alert_history ledger.
#
# Persists a small grading payload of tiering_result["snipe_gate_audit"] so the
# scanner's own tier-boundary evidence can be graded after the fact. This is a
# black-box recorder: it never raises, never mutates the source audit, persists
# only the compact grading fields (never the full 14H object), and keeps output
# JSON-safe. Alert persistence is more important than audit persistence — any
# failure here degrades the snapshot, it never breaks record_alert.
# ---------------------------------------------------------------------------

_SNIPE_SNAPSHOT_KEYS = (
    "audit_label", "promotion_state", "snipe_score", "snipe_grade",
    "eligible_for_snipe_review", "blocked_gate_names", "blocked_gates",
    "missing_proofs", "promotion_triggers", "blocking_reasons",
    "diagnostic_sentence",
    # Phase 14K — raw-vs-effective score consistency (never trading-relevant;
    # display/audit only).
    "raw_snipe_score", "effective_snipe_score", "score_blocked_by",
    "display_score_label",
)


def _degraded_snipe_snapshot(note: str) -> dict:
    return {
        "audit_label": None,
        "promotion_state": None,
        "snipe_score": None,
        "snipe_grade": None,
        "eligible_for_snipe_review": None,
        "blocked_gate_names": [],
        "blocked_gates": [],
        "missing_proofs": [],
        "promotion_triggers": [],
        "blocking_reasons": [f"snipe_gate_audit snapshot degraded: {note}"],
        "diagnostic_sentence": None,
        "raw_snipe_score": None,
        "effective_snipe_score": None,
        "score_blocked_by": [],
        "display_score_label": None,
    }


# ---- JSON-safety primitives (strict: json.dumps(row, allow_nan=False) safe) --

def _json_safe_number(value):
    """Finite int/float only — bool rejected. Else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _json_safe_scalar(value):
    """String-safe scalar. None/str pass through; finite numeric (non-bool) ->
    str; bool/dict/list/set/tuple/object/callable/NaN/Infinity -> None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value) if math.isfinite(value) else None
    return None


def _json_safe_bool_or_none(value):
    """Only literal True / False survive; everything else -> None."""
    if value is True:
        return True
    if value is False:
        return False
    return None


def _json_safe_level(value):
    """A numeric level may stay numeric. str / finite int / finite float (non-
    bool) / None survive; bool / NaN / Infinity / nested -> None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _snipe_gate_name(item):
    """Extract a JSON-safe gate name from a dict (gate > name > id > key) or a
    bare string. Returns a non-empty string, or None."""
    if isinstance(item, str):
        return item or None
    if isinstance(item, dict):
        for key in ("gate", "name", "id", "key"):
            safe = _json_safe_scalar(item.get(key))
            if isinstance(safe, str) and safe:
                return safe
    return None


def _snipe_blocked_gate_names(blocked) -> list:
    out = []
    if not isinstance(blocked, list):
        return out
    for item in blocked:
        name = _snipe_gate_name(item)
        if name:
            out.append(name)
    return out


def _snipe_compact_blocked_gates(blocked) -> list:
    out = []
    if not isinstance(blocked, list):
        return out
    for item in blocked:
        if isinstance(item, dict):
            out.append({
                "gate": _snipe_gate_name(item),
                "status": _json_safe_scalar(item.get("status")),
                "reason": _json_safe_scalar(item.get("reason")),
                "source": _json_safe_scalar(item.get("source")),
            })
        elif isinstance(item, str):
            out.append({"gate": item, "status": None, "reason": None, "source": None})
        # skip malformed (non-dict, non-str) entries
    return out


def _snipe_compact_missing_proofs(src) -> list:
    out = []
    if not isinstance(src, list):
        return out
    for item in src:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append({
                "gate": _json_safe_scalar(item.get("gate")),
                "name": _json_safe_scalar(item.get("name")),
                "reason": _json_safe_scalar(item.get("reason")),
                "required_evidence": _json_safe_scalar(item.get("required_evidence")),
                "source": _json_safe_scalar(item.get("source")),
            })
        # skip malformed entries
    return out


def _snipe_compact_promotion_triggers(src) -> list:
    out = []
    if not isinstance(src, list):
        return out
    for item in src:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append({
                "gate": _json_safe_scalar(item.get("gate")),
                "trigger": _json_safe_scalar(item.get("trigger")),
                "level": _json_safe_level(item.get("level")),
                "condition": _json_safe_scalar(item.get("condition")),
                "reason": _json_safe_scalar(item.get("reason")),
            })
        # skip malformed entries
    return out


def _snipe_compact_blocking_reasons(src) -> list:
    out = []
    if not isinstance(src, list):
        return out
    for item in src:
        if isinstance(item, str):
            if item:
                out.append(item)
        elif isinstance(item, dict):
            # Preserve a genuine string only (never stringify an object repr).
            for key in ("reason", "message", "label", "name", "gate"):
                v = item.get(key)
                if isinstance(v, str) and v:
                    out.append(v)
                    break
        # skip malformed entries
    return out


def _json_safe_string_list(value) -> list:
    """A list of plain JSON-safe strings only; anything else dropped."""
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v]


def _compact_snipe_gate_audit_snapshot(audit):
    """Return a compact, strictly JSON-safe grading snapshot of a 14H
    snipe_gate_audit (safe under json.dumps(..., allow_nan=False)).

    None when the audit is missing; a degraded snapshot when it is malformed or
    extraction fails. Never raises and never mutates the source object.
    """
    if audit is None:
        return None
    if not isinstance(audit, dict):
        return _degraded_snipe_snapshot("malformed source")
    try:
        return {
            "audit_label": _json_safe_scalar(audit.get("audit_label")),
            "promotion_state": _json_safe_scalar(audit.get("promotion_state")),
            "snipe_score": _json_safe_number(audit.get("snipe_score")),
            "snipe_grade": _json_safe_scalar(audit.get("snipe_grade")),
            "eligible_for_snipe_review": _json_safe_bool_or_none(
                audit.get("eligible_for_snipe_review")
            ),
            "blocked_gate_names": _snipe_blocked_gate_names(audit.get("blocked_gates")),
            "blocked_gates": _snipe_compact_blocked_gates(audit.get("blocked_gates")),
            "missing_proofs": _snipe_compact_missing_proofs(audit.get("missing_proofs")),
            "promotion_triggers": _snipe_compact_promotion_triggers(audit.get("promotion_triggers")),
            "blocking_reasons": _snipe_compact_blocking_reasons(audit.get("blocking_reasons")),
            "diagnostic_sentence": _json_safe_scalar(audit.get("diagnostic_sentence")),
            "raw_snipe_score": _json_safe_number(audit.get("raw_snipe_score")),
            "effective_snipe_score": _json_safe_number(audit.get("effective_snipe_score")),
            "score_blocked_by": _json_safe_string_list(audit.get("score_blocked_by")),
            "display_score_label": _json_safe_scalar(audit.get("display_score_label")),
        }
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log.warning("SNIPE_AUDIT_SNAPSHOT_ERROR: %s", exc)
        return _degraded_snipe_snapshot("extraction error")


def _compact_snipe_confirmed_seal_snapshot(seal):
    """Phase 14M.1 — compact, strictly JSON-safe snapshot of the Phase 14M
    snipe_confirmed_seal marker (safe under json.dumps(..., allow_nan=False)).

    None when the seal never applied (the common case — no false SNIPE was
    detected) or the source is malformed. Never raises, never mutates the
    source object, never persists the full reasons/blockers verbosity beyond a
    flat string list (no large nested objects).
    """
    if not isinstance(seal, dict) or seal.get("applied") is not True:
        return None
    try:
        sealed_tier = seal.get("sealed_tier") or seal.get("corrected_tier")
        return {
            "applied": True,
            "original_tier": _json_safe_scalar(seal.get("original_tier")),
            "sealed_tier": _json_safe_scalar(sealed_tier),
            "reason": _json_safe_scalar(seal.get("reason")) or "active SNIPE confirmation blocker remained",
            "active_blockers": _json_safe_string_list(seal.get("active_blockers") or seal.get("blockers")),
            "sealed_by_phase": _json_safe_scalar(seal.get("sealed_by_phase")) or "14M",
        }
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log.warning("SNIPE_CONFIRMED_SEAL_SNAPSHOT_ERROR: %s", exc)
        return None


def _higher_timeframe_history_snapshot(tiering_result, config):
    """Compact, JSON-safe Phase 14I snapshot for alert_history. Gated on config
    higher_timeframe_context.persist_history_snapshot (default True). Never raises
    and never breaks record_alert."""
    try:
        cfg = (config or {}).get("higher_timeframe_context", {})
        if isinstance(cfg, dict) and cfg.get("persist_history_snapshot", True) is False:
            return None
        from src import higher_timeframe_context as _htf
        return _htf.compact_history_snapshot(tiering_result.get("higher_timeframe_context"))
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log.warning("HTF_HISTORY_SNAPSHOT_ERROR: %s", exc)
        return None


def record_alert(
    ticker: str,
    tiering_result: dict,
    state: dict,
    config: dict | None = None,
    scan_id: str = "",
) -> dict:
    """Add alert record to state. Trims history to max_memory_entries.

    Returns updated state dict. Does NOT save to disk — caller calls save().
    """
    max_entries  = (config or {}).get("state", {}).get("max_memory_entries", 500)
    final_tier   = tiering_result.get("final_tier", "WAIT")
    final_channel = tiering_result.get("final_discord_channel", "none")
    score        = tiering_result.get("score", 0)
    final_signal = tiering_result.get("final_signal") or {}

    trigger_level     = final_signal.get("trigger_level")
    invalidation_level = final_signal.get("invalidation_level")
    reason            = final_signal.get("reason", "")
    now               = datetime.utcnow().isoformat()
    dedup_key         = make_dedup_key(ticker, final_tier, trigger_level, invalidation_level)

    tickers      = state.setdefault("tickers", {})
    ticker_state = tickers.setdefault(ticker, {
        "last_alerted_tier":        None,
        "last_alerted_at":          None,
        "last_trigger_level":       None,
        "last_invalidation_level":  None,
        "last_score":               None,
        "last_reason":              "",
        "last_discord_channel":     None,
        "last_dedup_key":           None,
        "scan_id":                  "",
        "alert_history":            [],
    })

    history = ticker_state.setdefault("alert_history", [])
    history.append({
        # ---- Phase 6 baseline fields (unchanged) ----
        "ticker":             ticker,
        "tier":               final_tier,
        "alerted_at":         now,
        "trigger_level":      trigger_level,
        "invalidation_level": invalidation_level,
        "score":              score,
        "reason":             reason,
        "dedup_key":          dedup_key,
        "scan_id":            scan_id,

        # ---- Phase 13.3B: REQUIRED_FOR_OUTCOME ----
        "scan_price":         final_signal.get("scan_price"),
        "targets":            final_signal.get("targets") or [],

        # ---- Phase 13.3B: REQUIRED_FOR_DIAGNOSTICS ----
        "risk_reward":                       final_signal.get("risk_reward"),
        "risk_realism_state":                final_signal.get("risk_realism_state"),
        "risk_distance":                     final_signal.get("risk_distance"),
        "risk_distance_pct":                 final_signal.get("risk_distance_pct"),
        "current_price_to_invalidation":     final_signal.get("current_price_to_invalidation"),
        "current_price_to_invalidation_pct": final_signal.get("current_price_to_invalidation_pct"),
        "retest_status":                     final_signal.get("retest_status"),
        "hold_status":                       final_signal.get("hold_status"),
        "current_acceptance":                final_signal.get("current_acceptance"),
        "overhead_status":                   final_signal.get("overhead_status"),
        "setup_family":                      final_signal.get("setup_family"),
        "structure_event":                   final_signal.get("structure_event"),
        "trend_state":                       final_signal.get("trend_state"),
        "zone_type":                         final_signal.get("zone_type"),
        "sma_value_alignment":               final_signal.get("sma_value_alignment"),
        "missing_conditions":                final_signal.get("missing_conditions"),
        "upgrade_trigger":                   final_signal.get("upgrade_trigger"),
        "capital_action":                    final_signal.get("capital_action"),
        "sanitized_reason":                  final_signal.get("sanitized_reason"),
        "sanitized_next_action":             final_signal.get("sanitized_next_action"),
        "original_claude_tier":              tiering_result.get("original_claude_tier"),
        "applied_vetoes":                    tiering_result.get("applied_vetoes") or [],
        "final_discord_channel":             tiering_result.get("final_discord_channel"),

        # ---- Phase 14H.1: compact SNIPE gate-audit grading snapshot ----
        # None when no audit exists; degraded snapshot when malformed. Never the
        # full 14H object (no passed_gates / evidence_sources / invalidation /
        # risk / nested raw matrices).
        "snipe_gate_audit":                  _compact_snipe_gate_audit_snapshot(
            tiering_result.get("snipe_gate_audit")
        ),

        # ---- Phase 14I: compact higher-timeframe structural context snapshot ----
        # None when missing/disabled; degraded snapshot when malformed. Compact
        # grading fields only (never the full 14I object). JSON-safe (allow_nan=False).
        "higher_timeframe_context":          _higher_timeframe_history_snapshot(
            tiering_result, config
        ),

        # ---- Phase 14M.1: compact Phase 14M consistency-seal marker ----
        # None when the seal never applied (the common case). When applied,
        # a small flat record of the downgrade reason/blockers — never the
        # full reasons verbosity, never a trading-decision field re-grant.
        "snipe_confirmed_seal":              _compact_snipe_confirmed_seal_snapshot(
            tiering_result.get("snipe_confirmed_seal")
        ),
    })
    if len(history) > max_entries:
        ticker_state["alert_history"] = history[-max_entries:]

    ticker_state.update({
        "last_alerted_tier":        final_tier,
        "last_alerted_at":          now,
        "last_trigger_level":       trigger_level,
        "last_invalidation_level":  invalidation_level,
        "last_score":               score,
        "last_reason":              reason,
        "last_discord_channel":     final_channel,
        "last_dedup_key":           dedup_key,
        "scan_id":                  scan_id,
    })

    meta = state.setdefault("meta", {})
    meta["last_updated"] = now
    meta["total_alerts"] = meta.get("total_alerts", 0) + 1

    return state

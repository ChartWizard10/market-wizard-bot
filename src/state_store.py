"""Persistent alert history and deduplication state.

Decides whether a validated signal should alert, be suppressed as a duplicate,
or be eligible for re-alert. Does not decide trade quality. Does not change
final_tier. Does not call Discord, Claude, yfinance, or the scheduler.
"""

import json
import logging
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
    campaign_id: str | None = None,
) -> str:
    """Build a normalized dedup key.

    When campaign_id is present: ticker|tier|campaign_id.
    Fallback (no campaign_id): ticker|tier|trigger|invalidation (legacy behavior).
    """
    if campaign_id:
        return f"{ticker}|{tier}|{campaign_id}"

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

    ticker             = final_signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")
    trigger_level      = final_signal.get("trigger_level")
    invalidation_level = final_signal.get("invalidation_level")
    campaign_id        = final_signal.get("campaign_id") or tiering_result.get("campaign_id")

    dedup_key    = make_dedup_key(ticker, final_tier, trigger_level, invalidation_level, campaign_id)
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
    last_campaign_id  = ticker_state.get("last_campaign_id")
    in_cooldown       = _within_cooldown(last_alerted_at, cooldown_minutes)

    # ---- Re-alert rules (apply before cooldown check) ----

    # Tier improvement always re-alerts regardless of campaign state
    if _tier_rank(final_tier) > _tier_rank(last_tier):
        return _yes_alert("tier_improved", dedup_key, ticker_state)

    # Campaign-aware path: campaign_id present on both sides
    if campaign_id and last_campaign_id:
        if campaign_id != last_campaign_id:
            # Structural thesis changed — new campaign identity
            return _yes_alert("new_campaign", dedup_key, ticker_state)
        # Same structural campaign: trigger drift is suppressed entirely.
        # Cooldown governs re-alert within a live campaign.
        if in_cooldown:
            return _no_alert("duplicate_suppressed", dedup_key, ticker_state)
        return _yes_alert("cooldown_expired", dedup_key, ticker_state)

    # Legacy fallback: campaign_id absent on either side — preserve prior behavior
    if _is_material_change(last_trigger, trigger_level, trigger_pct):
        return _yes_alert("trigger_changed", dedup_key, ticker_state)

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
    safe_for_alert = tiering_result.get("safe_for_alert", False)
    final_signal = tiering_result.get("final_signal") or {}

    trigger_level      = final_signal.get("trigger_level")
    invalidation_level = final_signal.get("invalidation_level")
    campaign_id        = final_signal.get("campaign_id") or tiering_result.get("campaign_id")
    reason             = final_signal.get("reason", "")
    now                = datetime.utcnow().isoformat()
    dedup_key          = make_dedup_key(
        ticker, final_tier, trigger_level, invalidation_level, campaign_id
    )

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

    # Phase 14C.5 — immutable unique identifier for the Observation Ledger.
    # Built from scan_id + ticker + timestamp. Never read by dedup, campaign
    # identity, cooldown, routing, tiering, or Discord output — it exists only
    # so the outcome tracker can associate a future price outcome with the
    # exact alert record that produced it.
    alert_id = f"{scan_id}|{ticker}|{now}"

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
        # ---- Phase 14C.5: Observation Ledger identity + filter (observational) ----
        "alert_id":           alert_id,
        "safe_for_alert":     safe_for_alert,

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
        "volume_behavior":                   final_signal.get("volume_behavior"),
        "volume_ratio":                      final_signal.get("volume_ratio"),

        # ---- Phase 1B: VCP evidence (observational only) ----
        # Stored to enable future backtesting of VCP outcome correlation. None
        # of these fields are read by any gate, score, calibration, routing,
        # capital, or alert decision in the current scanner.
        "vcp_status":               final_signal.get("vcp_status"),
        "vcp_prior_advance_pct":    final_signal.get("vcp_prior_advance_pct"),
        "vcp_contractions_count":   final_signal.get("vcp_contractions_count"),
        "vcp_range_contraction":    final_signal.get("vcp_range_contraction"),
        "vcp_contraction_sequence": final_signal.get("vcp_contraction_sequence"),
        "vcp_volume_dryup":         final_signal.get("vcp_volume_dryup"),
        "vcp_volume_ratio":         final_signal.get("vcp_volume_ratio"),
        "vcp_ma_alignment":         final_signal.get("vcp_ma_alignment"),
        "vcp_pivot_level":          final_signal.get("vcp_pivot_level"),
        "vcp_failure_flag":         final_signal.get("vcp_failure_flag"),

        # ---- Phase 1C-P1: Break & Retest doctrine organs (observational only) ----
        # Stored to enable future backtesting of entry-quality vs outcome. None of
        # these fields are read by any gate, score, calibration, routing, capital,
        # dedup, or alert decision in the current scanner.
        "entry_family":             final_signal.get("entry_family"),
        "retest_quality":           final_signal.get("retest_quality"),
        "consumption_risk":         final_signal.get("consumption_risk"),
        "level_authority":          final_signal.get("level_authority"),
        "zone_freshness":           final_signal.get("zone_freshness"),
        "break_retest_state":       final_signal.get("break_retest_state"),
        "one_hour_momentum_repair": final_signal.get("one_hour_momentum_repair"),
        # ---- Phase 1D: Market Structure State (observational only) ----
        "market_structure_state":   final_signal.get("market_structure_state"),
        # ---- Phase 14A: Weekly Sovereignty Evidence (observational only) ----
        "weekly_sma_alignment":      final_signal.get("weekly_sma_alignment"),
        "weekly_trend_state":        final_signal.get("weekly_trend_state"),
        "weekly_alignment_context":  final_signal.get("weekly_alignment_context"),
        # ---- Phase 14C: Real 4H Operational State Evidence (observational) ----
        "four_hour_market_state":    final_signal.get("four_hour_market_state"),
        "four_hour_sma_alignment":   final_signal.get("four_hour_sma_alignment"),
        "four_hour_reclaim_status":  final_signal.get("four_hour_reclaim_status"),
        "four_hour_structure_note":  final_signal.get("four_hour_structure_note"),
        "four_hour_data_status":     final_signal.get("four_hour_data_status"),
        # ---- Phase 14E: Real 1H Entry Trigger Evidence (observational) ----
        # Stored to enable future backtesting of trigger-family vs outcome. None
        # of these fields are read by any gate, score, calibration, routing,
        # capital, dedup, campaign, or alert decision in the current scanner.
        "one_hour_trigger_family":    final_signal.get("one_hour_trigger_family"),
        "one_hour_state":             final_signal.get("one_hour_state"),
        "one_hour_retest_quality":    final_signal.get("one_hour_retest_quality"),
        "one_hour_acceptance_state":  final_signal.get("one_hour_acceptance_state"),
        "one_hour_consequence_state": final_signal.get("one_hour_consequence_state"),
        "one_hour_no_chase_status":   final_signal.get("one_hour_no_chase_status"),
        "one_hour_data_status":       final_signal.get("one_hour_data_status"),
        # ---- Phase 14F: Active Auction Conflict Governor audit record ----
        # Records whether the governor capped the tier and why, so the
        # observation ledger can backtest governor accuracy. The decision was
        # already applied by tiering.py; these fields never feed dedup,
        # campaign identity, or any future read of this store.
        "active_auction_conflict":         final_signal.get("active_auction_conflict"),
        "active_auction_conflict_points":  final_signal.get("active_auction_conflict_points"),
        "active_auction_conflict_reasons": final_signal.get("active_auction_conflict_reasons"),

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

        # ---- Phase 14C.5: Observation Ledger outcome slots (observational) ----
        # Initialized to None at alert time; populated later, out of band, by
        # outcome_tracker. NEVER read by any gate, score, veto, tier, routing,
        # capital, dedup, campaign, or Discord decision. Backtest material only.
        "tp1_hit":            None,
        "tp2_hit":            None,
        "tp3_hit":            None,
        "invalidated":        None,
        "mfe_pct":            None,
        "mae_pct":            None,
        "outcome_updated_at": None,
    })
    if len(history) > max_entries:
        ticker_state["alert_history"] = history[-max_entries:]

    ticker_state.update({
        "last_alerted_tier":        final_tier,
        "last_alerted_at":          now,
        "last_trigger_level":       trigger_level,
        "last_invalidation_level":  invalidation_level,
        "last_campaign_id":         campaign_id,
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


# ---------------------------------------------------------------------------
# Phase 14C.5 — Observation Ledger: outcome write-back (observational only)
# ---------------------------------------------------------------------------

# The ONLY fields record_outcome is permitted to write. Any key in outcome_dict
# that is not in this tuple is ignored. This is the structural guarantee that
# outcome write-back can never touch tier, routing, capital, dedup, campaign,
# evidence, or any other decision-path field on a stored record.
_OUTCOME_FIELDS: tuple[str, ...] = (
    "tp1_hit",
    "tp2_hit",
    "tp3_hit",
    "invalidated",
    "mfe_pct",
    "mae_pct",
    "outcome_updated_at",
)


def record_outcome(
    ticker: str,
    alert_id: str,
    outcome_dict: dict,
    state: dict,
) -> dict:
    """Write observation-only outcome fields onto a stored alert_history record.

    Observation only. Locates the record by its immutable ``alert_id`` and
    overwrites ONLY the 7 fields in ``_OUTCOME_FIELDS``. It can never alter
    final_tier, safe_for_alert, score/prefilter_score, capital_action,
    final_discord_channel, campaign_id, dedup_key (or its inputs), or any
    evidence field — those keys are structurally excluded from the write set.

    Returns the (mutated) state dict. Does NOT save to disk — the caller saves.
    No-op if the ticker or alert_id is not found.
    """
    ticker_state = (state.get("tickers") or {}).get(ticker)
    if not ticker_state:
        return state

    for record in ticker_state.get("alert_history") or []:
        if record.get("alert_id") == alert_id:
            for field in _OUTCOME_FIELDS:
                if field in outcome_dict:
                    record[field] = outcome_dict[field]
            break

    return state

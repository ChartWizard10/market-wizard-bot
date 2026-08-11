"""Phase 14V — scan-time funnel telemetry and decision ledger.

Records what the scanner ALREADY DID, at the exact scan moment, so the Phase
14U funnel audit can finally see the stages that persisted history cannot
reach. It observes; it never judges.

Doctrine (permanent):
  - 14V OBSERVES. It never promotes, downgrades, reroutes, changes candidate
    admission, alters suppression, or adds a single API call. Every value it
    stores is COPIED from an outcome a production organ already computed.
  - Isolated failure domain. Telemetry lives in its own file
    (`.state/scan_telemetry.json`) and is written atomically (tmp in the same
    directory + os.replace). A telemetry fault can never corrupt
    alert_history.json, never mutate final_tier / capital_action / routing /
    suppression, never block a Discord send, and never break a scan.
  - No fake zeroes. A counter the pipeline cannot genuinely observe is None,
    never 0.
  - No fake mechanisms. See SUPPRESSION TRUTH below.
  - Bounded. Ring-buffered to `telemetry.max_scan_summaries` /
    `telemetry.max_decision_traces`.
  - No raw model payloads, no prompts, no secrets, no config dumps.

SCOPE
-----
`telemetry_scope = scheduled/full scan pipeline`. Only
`scheduler.run_scan_pipeline` is instrumented. Manual `run_analyze` is a
single-ticker path that never passes through universe admission, prefilter,
or the candidate cap, so fabricating a scan-funnel summary for it would be
false telemetry. It is deliberately untelemetered.

SUPPRESSION TRUTH (proven against src/state_store.check_alert)
--------------------------------------------------------------
This scanner has exactly ONE same-signal suppression path:

    if in_cooldown:
        return _no_alert("duplicate_suppressed", dedup_key, ticker_state)

`dedup_key` is identity/diagnostic state — grep proves it is never used as a
suppression gate anywhere in src/. Therefore:

  - `duplicate_suppressed` is COOLDOWN suppression, and nothing else.
  - An equal dedup_key alone is NOT a suppression event and must never be
    reported as one.
  - Independent dedup-key suppression is NOT IMPLEMENTED in this scanner.
    That is a statement about the architecture, not a blind spot and not a
    zero. It is carried as `dedup_key_suppression_supported: False`.

Raw `check_alert` reasons are stored VERBATIM. Interpretation belongs to the
audit layer, not the ledger.
"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = "14V.1"

TELEMETRY_FILENAME = "scan_telemetry.json"

# Retention defaults. ~26 scans/session at 15-minute cadence:
#   300 summaries      ~= 11.5 trading sessions
#   16000 traces       ~= 10 trading days at 60 traces/scan (30 admitted + 30 near-cut)
_DEFAULT_MAX_SCAN_SUMMARIES = 300
_DEFAULT_MAX_DECISION_TRACES = 16000

# Near-cut observation window: ranked_results[30:60] -> ranks 31-60.
# Copied from the existing ranking only. No Claude call, no data refetch.
_NEAR_CUT_START = 30
_NEAR_CUT_END = 60

# The one suppression reason this scanner can actually produce.
COOLDOWN_SUPPRESSION_REASON = "duplicate_suppressed"

# Whitelisted scan-time ladder fields (Phase 14S / 14S.7B / 14S.7C).
_LADDER_KEYS = (
    "internal_ladder_tier", "public_signal_tier",
    "existing_final_tier_recommendation", "capital_action_recommendation",
    "opportunity_lane", "starter_grade", "sniper_grade",
    "hard_failures", "starter_blockers", "sniper_only_blockers",
    "soft_caps", "info_notes",
    "why_this_ladder_tier", "why_not_higher", "why_not_lower",
    "next_promotion_proof",
    "snipe_capital_floor_cleared", "direct_snipe_decision",
    "snipe_capital_floor_violation", "snipe_capital_emergency_landing",
)

_CANDLE_KEYS = ("status", "candle_family", "candle_veto", "next_candle_verdict",
                "level_reaction")


# ---------------------------------------------------------------------------
# JSON-safe primitives (mirrors state_store's strictness: allow_nan=False safe)
# ---------------------------------------------------------------------------

def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return int(f) if float(f).is_integer() else f


def _scalar(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    n = _num(value)
    return n if n is not None else str(value)


def _str_list(value, limit=12):
    out = []
    if not isinstance(value, (list, tuple)):
        return out
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
        elif isinstance(item, dict):
            code = item.get("code") or item.get("gate") or item.get("name")
            if isinstance(code, str) and code:
                out.append(code)
        if len(out) >= limit:
            break
    return out


def _d(obj, key):
    v = obj.get(key) if isinstance(obj, dict) else None
    return v if isinstance(v, dict) else {}


# ---------------------------------------------------------------------------
# Storage location + config
# ---------------------------------------------------------------------------

def telemetry_path(config) -> Path:
    """`.state/scan_telemetry.json` beside the existing alert-history file.

    Deliberately a SEPARATE file: a malformed telemetry write must never be
    able to corrupt or truncate alert_history.json.
    """
    cfg = (config or {}).get("telemetry")
    cfg = cfg if isinstance(cfg, dict) else {}
    explicit = cfg.get("telemetry_file")
    if isinstance(explicit, str) and explicit.strip():
        return Path(explicit)
    state_file = ((config or {}).get("state") or {}).get("state_file") or ".state/alert_history.json"
    return Path(state_file).parent / TELEMETRY_FILENAME


def _limits(config) -> tuple:
    cfg = (config or {}).get("telemetry")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _lim(key, default):
        try:
            v = int(cfg.get(key, default))
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    return (_lim("max_scan_summaries", _DEFAULT_MAX_SCAN_SUMMARIES),
            _lim("max_decision_traces", _DEFAULT_MAX_DECISION_TRACES))


def _empty_ledger() -> dict:
    return {"schema_version": SCHEMA_VERSION, "scan_summaries": [], "decision_traces": []}


# ---------------------------------------------------------------------------
# Read / atomic write
# ---------------------------------------------------------------------------

def load_ledger(config) -> dict:
    """Read the telemetry ledger. Never raises. A missing or malformed file
    yields an empty ledger — telemetry corruption is never fatal, and this
    function never touches alert_history.json."""
    path = telemetry_path(config)
    try:
        if not path.exists():
            return _empty_ledger()
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("TELEMETRY_LOAD_DEGRADED: %s", exc)
        return _empty_ledger()
    if not isinstance(data, dict):
        return _empty_ledger()
    ledger = _empty_ledger()
    ledger["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    for key in ("scan_summaries", "decision_traces"):
        items = data.get(key)
        if isinstance(items, list):
            ledger[key] = [x for x in items if isinstance(x, dict)]
    return ledger


def _atomic_write(path: Path, payload: dict) -> bool:
    """Serialize first, then tmp-in-same-directory + os.replace.

    Serializing BEFORE touching the filesystem means a malformed payload can
    never leave a truncated file behind. Stricter than the legacy
    state_store.save() (a bare write_text) — intentionally so.
    """
    tmp = None
    try:
        blob = json.dumps(payload, indent=2, allow_nan=False, default=str)
    except Exception as exc:
        log.warning("TELEMETRY_SERIALIZE_FAILED: %s — prior telemetry left intact", exc)
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return True
    except Exception as exc:
        log.warning("TELEMETRY_WRITE_FAILED: %s — prior telemetry left intact", exc)
        if tmp is not None:
            try:
                if Path(tmp).exists():
                    os.unlink(tmp)          # never leave an orphan temp behind
            except Exception:
                pass
        return False


def write_scan_telemetry(config, summary=None, traces=None) -> bool:
    """Append one scan summary + its decision traces, ring-buffer, persist.

    Returns True on success, False on any failure. NEVER raises: the caller is
    the scan pipeline, and observability failure is not market failure.
    """
    try:
        ledger = load_ledger(config)
        max_summaries, max_traces = _limits(config)
        if isinstance(summary, dict):
            ledger["scan_summaries"].append(summary)
        if isinstance(traces, (list, tuple)):
            ledger["decision_traces"].extend(t for t in traces if isinstance(t, dict))
        # Oldest first out, deterministic order preserved.
        ledger["scan_summaries"] = ledger["scan_summaries"][-max_summaries:]
        ledger["decision_traces"] = ledger["decision_traces"][-max_traces:]
        ledger["schema_version"] = SCHEMA_VERSION
        return _atomic_write(telemetry_path(config), ledger)
    except Exception as exc:  # pragma: no cover - defensive; never break a scan
        log.warning("TELEMETRY_WRITE_ABORTED: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Layer 1 — scan funnel summary
# ---------------------------------------------------------------------------

def _rejection_histogram(all_results) -> dict:
    """Tally canonical prefilter rejection reasons. Hard-veto rejects have no
    rank in ranked_results, so they appear here and only here — no rank is
    invented for them."""
    hist = {}
    for r in all_results or []:
        if not isinstance(r, dict) or r.get("eligible_for_claude"):
            continue
        reason = r.get("rejection_reason")
        if isinstance(reason, str) and reason:
            key = reason.split(":", 1)[0].strip() or "unspecified"
        elif r.get("data_status") not in (None, "OK"):
            key = "data_status"
        else:
            key = "unspecified"
        hist[key] = hist.get(key, 0) + 1
        for flag in _str_list(r.get("veto_flags"), limit=8):
            fk = f"veto:{flag}"
            hist[fk] = hist.get(fk, 0) + 1
    return hist


def build_scan_summary(scan_id, scan_timestamp, tickers_input, data_failures,
                       pf_result, config, tier_counts=None, ladder_counts=None,
                       base_tier_counts=None, check_alert_reason_counts=None,
                       delivery=None, claude_analyzed=None, claude_failed=None) -> dict:
    """Compact Layer-1 record. Every field is copied from an outcome the
    pipeline already produced; nothing is recomputed. Unobservable values are
    None, never 0."""
    pf_result = pf_result if isinstance(pf_result, dict) else {}
    all_results = pf_result.get("all_results") or []
    ranked = pf_result.get("ranked_results") or []
    candidates = pf_result.get("claude_candidates") or []
    board = pf_result.get("board_summary") or {}
    cap = ((config or {}).get("prefilter") or {}).get("max_claude_candidates_per_scan")

    # Cutoff only exists when the cap actually bound the list.
    cutoff_rank = cutoff_score = None
    if isinstance(cap, int) and len(ranked) >= cap >= 1:
        cutoff_rank = cap
        cutoff_score = _num((ranked[cap - 1] or {}).get("prefilter_score"))

    ok = _num(tickers_input)
    fail = _num(data_failures)
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "scan_timestamp": _scalar(scan_timestamp),
        "telemetry_scope": "run_scan_pipeline",
        "universe": {
            "input_count": ok,
            "market_data_failure": fail,
            "market_data_success": (ok - fail) if (ok is not None and fail is not None) else None,
        },
        "prefilter": {
            "eligible_count": len(ranked),
            "rejected_count": _num(board.get("total_rejected_by_data_quality", 0))
                              + _num(board.get("total_rejected_by_veto", 0))
            if board else None,
            "rejection_reason_counts": _rejection_histogram(all_results),
            "candidate_cap": _num(cap),
            "ranked_eligible_count": len(ranked),
            "admitted_count": len(candidates),
            "cutoff_rank": cutoff_rank,
            "cutoff_score": cutoff_score,
        },
        "analysis": {
            "admitted_count": len(candidates),
            "claude_analyzed_count": _num(claude_analyzed),
            "claude_failed_count": _num(claude_failed),
        },
        "base_tiers": dict(base_tier_counts or {}),
        "ladder_baskets": dict(ladder_counts or {}),
        "final_tiers": dict(tier_counts or {}),
        "suppression": {
            # Raw check_alert vocabulary, stored verbatim. Interpretation is
            # the audit layer's job, not the ledger's.
            "check_alert_reason_counts": dict(check_alert_reason_counts or {}),
            "cooldown_suppressed": (check_alert_reason_counts or {}).get(
                COOLDOWN_SUPPRESSION_REASON, 0),
            # Architectural truth, not a blind unknown and not a fake zero:
            # this scanner has no dedup-key-only suppression gate.
            "dedup_key_suppression_supported": False,
        },
        "delivery": dict(delivery or {}),
    }


# ---------------------------------------------------------------------------
# Layer 2 — compact decision traces
# ---------------------------------------------------------------------------

def compact_ladder(ladder) -> dict:
    """Whitelisted projection of the ACTUAL scan-time snipe_ladder, captured
    after arbitration + the 14S.7C capital floor. This is what makes stage 10
    causally attributable for future rows."""
    if not isinstance(ladder, dict):
        return None
    out = {}
    for key in _LADDER_KEYS:
        if key not in ladder:
            continue
        val = ladder.get(key)
        if isinstance(val, list):
            out[key] = _str_list(val)
        elif isinstance(val, dict):
            continue                      # never dump arbitrary nested objects
        else:
            out[key] = _scalar(val)
    return out or None


def compact_candle_evidence(candle) -> dict:
    """Compact scan-time candle truth: enough to tell open/live from closed
    confirmation, and defensive from hostile from unresolved."""
    if not isinstance(candle, dict):
        return None
    out = {k: _scalar(candle.get(k)) for k in _CANDLE_KEYS if k in candle}
    return out or None


def build_near_cut_trace(scan_id, result, rank) -> dict:
    """Ranks 31-60, copied straight from ranked_results. No Claude call, no
    market-data refetch, no strategy evaluation, no promotion."""
    result = result if isinstance(result, dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "ticker": _scalar(result.get("ticker")),
        "trace_kind": "near_cut",
        "pipeline": {
            "market_data_ok": result.get("data_status") == "OK",
            "prefilter_eligible": bool(result.get("eligible_for_claude")),
            "prefilter_rank": _num(rank),
            "prefilter_score": _num(result.get("prefilter_score")),
            "admitted_to_deep_analysis": False,
            "claude_analyzed": False,
        },
        "veto_flags": _str_list(result.get("veto_flags"), limit=6),
    }


def build_decision_trace(scan_id, ticker, pf_res, rank, tiering_result,
                         dedup_decision=None, send_result=None,
                         claude_analyzed=True, base_final_tier=None) -> dict:
    """Compact Layer-2 record for an analyzed candidate — including WAIT rows
    and rows whose delivery path disappears (cooldown-suppressed, routed to
    none, send failure). Everything is copied; nothing is recomputed."""
    pf_res = pf_res if isinstance(pf_res, dict) else {}
    tr = tiering_result if isinstance(tiering_result, dict) else {}
    dd = dedup_decision if isinstance(dedup_decision, dict) else {}
    sr = send_result if isinstance(send_result, dict) else {}
    signal = _d(tr, "final_signal")
    ladder = tr.get("snipe_ladder")
    oh = _d(tr, "one_hour_entry")
    prh = _d(oh, "pullback_retest_hold")
    tfa = _d(tr, "timeframe_alignment")

    reason = _scalar(dd.get("reason")) if dd else None
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "ticker": _scalar(ticker),
        "trace_kind": "analyzed",
        "pipeline": {
            "market_data_ok": pf_res.get("data_status") == "OK" if pf_res else None,
            "prefilter_eligible": bool(pf_res.get("eligible_for_claude")) if pf_res else None,
            "prefilter_rank": _num(rank),
            "prefilter_score": _num(pf_res.get("prefilter_score")) if pf_res else None,
            "admitted_to_deep_analysis": True,
            "claude_analyzed": bool(claude_analyzed),
        },
        "judgment": {
            "base_final_tier": _scalar(base_final_tier),
            "final_tier": _scalar(tr.get("final_tier")),
            "capital_action": _scalar(tr.get("capital_action")),
            "final_discord_channel": _scalar(tr.get("final_discord_channel")),
            "safe_for_alert": tr.get("safe_for_alert"),
            "score": _num(tr.get("score")),
        },
        # The actual scan-time ladder. Provenance is the object itself, never
        # a timestamp or a deploy date.
        "snipe_ladder": compact_ladder(ladder),
        "ladder_source": "stored_scan_time" if isinstance(ladder, dict) else None,
        "proof": {
            "one_hour_status": _scalar(oh.get("status")) or None,
            "one_hour_trigger_state": _scalar(oh.get("trigger_state")),
            "alert_truth_label": _scalar(oh.get("alert_truth_label")),
            "retest_truth": _scalar(prh.get("retest_truth")),
            "hold_truth": _scalar(prh.get("hold_truth")),
            "timeframe_alignment_label": _scalar(tfa.get("alignment_label")),
            "snipe_gate_promotion_state": _scalar(_d(tr, "snipe_gate_audit").get("promotion_state")),
            "seal_applied": _d(tr, "snipe_confirmed_seal").get("applied") is True,
        },
        "risk": {
            "invalidation_level": _num(signal.get("invalidation_level")),
            # Closes the recompute gap that produced false missing-invalidation reads.
            "invalidation_condition": _scalar(signal.get("invalidation_condition")),
            "risk_distance_pct": _num(signal.get("risk_distance_pct")),
            "risk_reward": _num(signal.get("risk_reward")),
            "overhead_status": _scalar(signal.get("overhead_status")),
        },
        "candle_evidence": compact_candle_evidence(tr.get("candle_evidence")),
        "suppression": {
            # Verbatim check_alert vocabulary — never renamed in storage.
            "check_alert_reason": reason,
            "should_alert": dd.get("should_alert") if dd else None,
            "dedup_key": _scalar(dd.get("dedup_key")) if dd else None,
            "cooldown_suppressed": reason == COOLDOWN_SUPPRESSION_REASON,
            # An equal dedup_key is NOT a suppression event in this scanner.
            "dedup_key_suppression_supported": False,
        },
        "delivery": {
            "attempted": bool(sr) or None,
            "sent": sr.get("sent") if sr else None,
            "skipped_reason": _scalar(sr.get("skipped_reason")) if sr else None,
            "error_type": _scalar(sr.get("error_type")) if sr else None,
        },
    }


def near_cut_slice(ranked_results) -> list:
    """ranked_results[30:60] -> (result, rank) pairs for ranks 31-60."""
    ranked = ranked_results if isinstance(ranked_results, list) else []
    window = ranked[_NEAR_CUT_START:_NEAR_CUT_END]
    return [(r, _NEAR_CUT_START + i + 1) for i, r in enumerate(window) if isinstance(r, dict)]

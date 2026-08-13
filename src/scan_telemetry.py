"""Phase 14V — scan-time funnel telemetry and decision ledger.

Records what the scanner ALREADY DID, at the exact scan moment, so the Phase
14U funnel audit can see the stages persisted history cannot reach. It
observes; it never judges.

Doctrine (permanent):
  - 14V OBSERVES. It never promotes, downgrades, reroutes, changes candidate
    admission, alters suppression, or adds an API call. Every value it stores
    is COPIED from an outcome a production organ already computed.
  - Isolated failure domain. Telemetry lives in its own file, written
    atomically, and REFUSES to write if its path would collide with the
    alert-history state file. A telemetry fault can never mutate final_tier /
    capital_action / routing / suppression, never block a Discord send, and
    never break a scan.
  - No field earns a stronger name than its source evidence permits.
  - No fake zeroes for UNOBSERVED stages. An observed stage may legitimately
    report 0.
  - Bounded, in count AND in per-string length.

Phase 14V.1 — telemetry truth reconciliation. The adversarial review proved
the architecture sound but several labels untruthful. Corrected here:
  - base tier vs FINAL SERVED tier are now distinct counters (B1)
  - a real Discord exception now produces a trace (B2)
  - delivery is a SENT / SKIPPED / FAILED state machine (B3, H4)
  - `check_alert_evaluated_tier` records the tier check_alert actually saw (M1)
  - analysis outcomes (success/failed/rate-limited/tiering-failed) are counted
    as analysis outcomes, never as synthetic market WAIT rows
  - cutoff only when the cap actually bound (M3); near-cut window derives from
    the configured cap (M4)
  - path-collision guard (M6), schema-mismatch + corrupt quarantine (M7/M8),
    free-text caps (M10), split rejection histograms, temp reaping
  - compact serialization + 9000-trace retention to hold the file under bound

SCOPE
-----
`telemetry_scope = run_scan_pipeline`. Manual `run_analyze` is a single-ticker
path that never passes through universe admission, prefilter, or the candidate
cap; fabricating a scan-funnel summary for it would be false telemetry.

SUPPRESSION TRUTH (proven against src/state_store.check_alert)
--------------------------------------------------------------
One same-signal suppression path exists:

    if in_cooldown:
        return _no_alert("duplicate_suppressed", dedup_key, ticker_state)

`dedup_key` is identity state and is never a suppression gate. Therefore
`duplicate_suppressed` is COOLDOWN suppression and nothing else, an equal
dedup_key is not a suppression event, and independent dedup-key suppression is
NOT IMPLEMENTED — carried as `dedup_key_suppression_supported: False`.

CHECK_ALERT ORDERING (measured, deliberately NOT fixed here)
------------------------------------------------------------
`check_alert` runs at scheduler Step 6, BEFORE ladder arbitration (6.592) and
the seal (6.595). A row can therefore be evaluated for cooldown as NEAR_ENTRY
and later be served as SNIPE_IT while retaining that decision. 14V records both
`check_alert_evaluated_tier` and the final served tier so the frequency of that
architecture can be measured. It does not change check_alert timing.
"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = "14V.2"

TELEMETRY_FILENAME = "scan_telemetry.json"

# Retention. Measured against the PRODUCTION serializer (compact, no indent):
# see tests test_50_*. 9000 traces keeps every realistic mix — including an
# all-admitted worst case — comfortably under the 25 MB bound.
_DEFAULT_MAX_SCAN_SUMMARIES = 300
_DEFAULT_MAX_DECISION_TRACES = 9000

# Near-cut observation window SIZE. The window START is the configured
# candidate cap, so telemetry stays truthful if the cap ever changes.
# This never changes the cap itself.
_NEAR_CUT_WINDOW = 30
_DEFAULT_CANDIDATE_CAP = 30

# Free-text cap. Telemetry only — the source object is never modified.
_MAX_TEXT = 512
_MAX_LIST = 12

COOLDOWN_SUPPRESSION_REASON = "duplicate_suppressed"

# Delivery state machine (B3/H4).
DELIVERY_SENT = "SENT"
DELIVERY_SKIPPED = "SKIPPED"
DELIVERY_FAILED = "FAILED"
DISCORD_EXCEPTION_ERROR = "DISCORD_SEND_EXCEPTION"

# Trace kinds.
TRACE_ANALYZED = "analyzed"
TRACE_NEAR_CUT = "near_cut"
TRACE_ANALYSIS_FAILED = "analysis_failed"
TRACE_RATE_LIMITED = "rate_limited"
TRACE_TIERING_FAILED = "tiering_failed"

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
# JSON-safe primitives. Telemetry-only: these must never raise, because a
# projection fault must never be able to abort an alert record (H1).
# ---------------------------------------------------------------------------

def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except Exception:        # incl. OverflowError on huge ints (H1)
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    try:
        return int(f) if float(f).is_integer() else f
    except Exception:        # pragma: no cover - defensive
        return None


def _scalar(value, cap=_MAX_TEXT):
    """Bounded scalar projection. Containers are NOT stringified — they become
    None, so an unexpected nested object can never smuggle a payload."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value[:cap]
    if isinstance(value, (dict, list, tuple, set)):
        return None
    n = _num(value)
    if n is not None:
        return n
    try:
        return str(value)[:cap]
    except Exception:        # pragma: no cover - defensive
        return None


def _str_list(value, limit=_MAX_LIST, cap=_MAX_TEXT):
    out = []
    if not isinstance(value, (list, tuple)):
        return out
    for item in value:
        if isinstance(item, str) and item:
            out.append(item[:cap])
        elif isinstance(item, dict):
            code = item.get("code") or item.get("gate") or item.get("name")
            if isinstance(code, str) and code:
                out.append(code[:cap])
        if len(out) >= limit:
            break
    return out


def _d(obj, key):
    v = obj.get(key) if isinstance(obj, dict) else None
    return v if isinstance(v, dict) else {}


def _counts(mapping):
    """Coerce a caller-supplied count map to JSON-safe scalars."""
    out = {}
    if isinstance(mapping, dict):
        for k, v in mapping.items():
            n = _num(v)
            out[str(k)[:_MAX_TEXT]] = n if n is not None else 0
    return out


# ---------------------------------------------------------------------------
# Storage location, collision guard, config
# ---------------------------------------------------------------------------

def _state_path(config) -> Path:
    state_file = ((config or {}).get("state") or {}).get("state_file") \
        or ".state/alert_history.json"
    return Path(state_file)


def telemetry_path(config) -> Path:
    """`<state dir>/scan_telemetry.json`, or an explicit override."""
    cfg = (config or {}).get("telemetry")
    cfg = cfg if isinstance(cfg, dict) else {}
    explicit = cfg.get("telemetry_file")
    if isinstance(explicit, str) and explicit.strip():
        return Path(explicit)
    return _state_path(config).parent / TELEMETRY_FILENAME


def telemetry_path_collides(config) -> bool:
    """True when the telemetry path would resolve onto the alert-history file.

    Phase 14V.1 (M6): telemetry UNAVAILABLE is strictly safer than telemetry
    destroying alert history. On collision we fail closed — no write, no
    fallback path, no touching of state.
    """
    try:
        t = telemetry_path(config)
        s = _state_path(config)
        return os.path.normcase(os.path.abspath(str(t))) == \
            os.path.normcase(os.path.abspath(str(s)))
    except Exception:        # pragma: no cover - defensive
        return True          # unknown -> refuse to write


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


def candidate_cap(config) -> int:
    try:
        cap = ((config or {}).get("prefilter") or {}).get(
            "max_claude_candidates_per_scan", _DEFAULT_CANDIDATE_CAP)
        cap = int(cap)
        return cap if cap > 0 else _DEFAULT_CANDIDATE_CAP
    except (TypeError, ValueError):
        return _DEFAULT_CANDIDATE_CAP


def _empty_ledger() -> dict:
    return {"schema_version": SCHEMA_VERSION, "scan_summaries": [], "decision_traces": []}


# ---------------------------------------------------------------------------
# READ path — never writes, never renames. Safe for the read-only audit.
# ---------------------------------------------------------------------------

def load_ledger_readonly(config) -> dict:
    """Strictly read-only ledger load for the audit layer.

    Never writes, renames, quarantines, or repairs anything — !auditshy's
    read-only guarantee depends on that. A missing/malformed/mismatched file
    yields an empty ledger. Never raises.
    """
    try:
        if telemetry_path_collides(config):
            return _empty_ledger()
        path = telemetry_path(config)
        if not path.exists():
            return _empty_ledger()
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("TELEMETRY_LOAD_DEGRADED: %s", exc)
        return _empty_ledger()
    return _project_ledger(data)


# Back-compat alias: the read-only loader is the default meaning of "load".
load_ledger = load_ledger_readonly


def _project_ledger(data) -> dict:
    if not isinstance(data, dict):
        return _empty_ledger()
    ledger = _empty_ledger()
    ledger["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    for key in ("scan_summaries", "decision_traces"):
        items = data.get(key)
        if isinstance(items, list):
            ledger[key] = [x for x in items if isinstance(x, dict)]
    return ledger


# ---------------------------------------------------------------------------
# WRITE-RECOVERY path — may quarantine a malformed/mismatched TELEMETRY file.
# Never touches alert history.
# ---------------------------------------------------------------------------

def _quarantine(path: Path, why: str) -> None:
    """Preserve an unusable telemetry file instead of silently destroying it
    (M7/M8). Telemetry-only naming; alert history is never involved."""
    try:
        if not path.exists():
            return
        dest = path.with_name(f"{path.name}.corrupt.{os.getpid()}")
        n = 0
        while dest.exists() and n < 50:
            n += 1
            dest = path.with_name(f"{path.name}.corrupt.{os.getpid()}.{n}")
        os.replace(path, dest)
        log.warning("TELEMETRY_QUARANTINED (%s) -> %s", why, dest.name)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("TELEMETRY_QUARANTINE_FAILED: %s", exc)


def _load_ledger_for_write(config) -> dict:
    """Load for the writer. Unlike the audit path this MAY quarantine a
    malformed or schema-mismatched telemetry file before starting fresh."""
    path = telemetry_path(config)
    try:
        if not path.exists():
            return _empty_ledger()
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("TELEMETRY_READ_FAILED: %s", exc)
        _quarantine(path, "unreadable")
        return _empty_ledger()
    try:
        data = json.loads(raw)
    except Exception:
        _quarantine(path, "malformed json")
        return _empty_ledger()
    if not isinstance(data, dict):
        _quarantine(path, "unexpected structure")
        return _empty_ledger()
    version = data.get("schema_version")
    if version and version != SCHEMA_VERSION:
        _quarantine(path, f"schema {version} != {SCHEMA_VERSION}")
        return _empty_ledger()
    return _project_ledger(data)


def _reap_stale_temps(path: Path) -> None:
    """Remove orphan temp files from killed writers. Scoped strictly to this
    telemetry file's own temp pattern; never load-bearing."""
    try:
        mine = f"{path.name}.tmp.{os.getpid()}"
        for stale in path.parent.glob(f"{path.name}.tmp.*"):
            if stale.name == mine:
                continue
            try:
                stale.unlink()
            except Exception:
                pass
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("TELEMETRY_TEMP_REAP_SKIPPED: %s", exc)


def _atomic_write(path: Path, payload: dict) -> bool:
    """Serialize first (so a bad payload never truncates a good file), then
    tmp-in-same-directory + fsync + os.replace. Compact separators: indent=2
    cost ~13-22% and pushed the documented mix over the size bound."""
    tmp = None
    try:
        blob = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except Exception as exc:
        log.warning("TELEMETRY_SERIALIZE_FAILED: %s — prior telemetry left intact", exc)
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _reap_stale_temps(path)
        tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
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
                    os.unlink(tmp)
            except Exception:
                pass
        return False


def write_scan_telemetry(config, summary=None, traces=None) -> bool:
    """Append one scan summary + its traces, ring-buffer, persist atomically.

    Returns True on success, False on any failure or refusal. NEVER raises:
    observability failure is not market failure.
    """
    try:
        if telemetry_path_collides(config):
            log.error(
                "TELEMETRY_PATH_COLLISION: telemetry path resolves to the "
                "alert-history state file — refusing to write. Telemetry is "
                "unavailable this scan; alert history is untouched."
            )
            return False
        ledger = _load_ledger_for_write(config)
        max_summaries, max_traces = _limits(config)
        if isinstance(summary, dict):
            ledger["scan_summaries"].append(summary)
        if isinstance(traces, (list, tuple)):
            ledger["decision_traces"].extend(t for t in traces if isinstance(t, dict))
        ledger["scan_summaries"] = ledger["scan_summaries"][-max_summaries:]
        ledger["decision_traces"] = ledger["decision_traces"][-max_traces:]
        ledger["schema_version"] = SCHEMA_VERSION
        return _atomic_write(telemetry_path(config), ledger)
    except Exception as exc:  # pragma: no cover - defensive; never break a scan
        log.warning("TELEMETRY_WRITE_ABORTED: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Delivery state machine (B2/B3/H4)
# ---------------------------------------------------------------------------

def delivery_state(send_result) -> str:
    """SENT / SKIPPED / FAILED from the real send_alert contract.

    SENT    ok is True  and sent is True
    SKIPPED ok is True  and sent is False   (WAIT, cooldown, routing-none, ...)
    FAILED  ok is False (or a synthesized exception result)

    A skipped message is not a failed message.
    """
    if not isinstance(send_result, dict):
        return None
    if send_result.get("ok") is False:
        return DELIVERY_FAILED
    if send_result.get("sent") is True:
        return DELIVERY_SENT
    return DELIVERY_SKIPPED


def network_attempted(send_result):
    """True only when send_alert actually resolved a channel and tried.

    `_not_sendable` / `_missing_channel` return channel_id None (no network
    contact); `_send_ok` / `_send_error` carry the channel id. Where the
    contract cannot prove it, this is None — never a fabricated False.
    """
    if not isinstance(send_result, dict):
        return None
    if "channel_id" not in send_result:
        return None
    return send_result.get("channel_id") is not None


def exception_send_result(exc) -> dict:
    """TELEMETRY-ONLY synthetic result for a raised send_alert (B2).

    Never fed back into trading logic: it exists so a real delivery failure
    cannot vanish from the ledger.
    """
    return {
        "ok": False,
        "sent": False,
        "channel_id": None,
        "error_type": DISCORD_EXCEPTION_ERROR,
        "error_message": None,          # exception text is not persisted
        "skipped_reason": None,
        "telemetry_synthesized": True,
        "exception_class": _scalar(type(exc).__name__) if exc is not None else None,
    }


# ---------------------------------------------------------------------------
# Layer 1 — scan funnel summary
# ---------------------------------------------------------------------------

def _rejection_histograms(all_results) -> tuple:
    """Two SEPARATE distributions (M-low): a primary single-label reason
    histogram that reconciles against rejected_count, and a multi-label veto
    flag histogram that deliberately does not."""
    primary, vetoes = {}, {}
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
        primary[key] = primary.get(key, 0) + 1
        for flag in _str_list(r.get("veto_flags"), limit=8):
            vetoes[flag] = vetoes.get(flag, 0) + 1
    return primary, vetoes


def build_scan_summary(scan_id, scan_timestamp, tickers_input, data_failures,
                       pf_result, config, final_tier_counts=None,
                       ladder_counts=None, base_tier_counts=None,
                       check_alert_reason_counts=None, delivery=None,
                       analysis=None) -> dict:
    """Compact Layer-1 record. Every field is copied from an outcome the
    pipeline already produced. Unobservable values are None, never 0 — but an
    OBSERVED stage may legitimately report 0."""
    pf_result = pf_result if isinstance(pf_result, dict) else {}
    all_results = pf_result.get("all_results") or []
    ranked = pf_result.get("ranked_results") or []
    candidates = pf_result.get("claude_candidates") or []
    board = pf_result.get("board_summary") or {}
    cap = candidate_cap(config)

    # Cutoff exists ONLY when the cap actually bound — len == cap excluded
    # nothing (M3).
    cutoff_rank = cutoff_score = None
    if len(ranked) > cap >= 1:
        cutoff_rank = cap
        cutoff_score = _num((ranked[cap - 1] or {}).get("prefilter_score"))

    primary_hist, veto_hist = _rejection_histograms(all_results)
    ok = _num(tickers_input)
    fail = _num(data_failures)
    reasons = _counts(check_alert_reason_counts)
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "scan_timestamp": _scalar(scan_timestamp),
        "telemetry_scope": "run_scan_pipeline",
        # Stage 1-2. `data_stage_*` because the failure count includes fetch
        # AND enrichment errors — the name matches MARKET_DATA_ENRICHMENT (M9).
        "universe": {
            "input_count": ok,
            "data_stage_failure": fail,
            "data_stage_success": (ok - fail) if (ok is not None and fail is not None) else None,
        },
        "prefilter": {
            "eligible_count": len(ranked),
            "rejected_count": (_num(board.get("total_rejected_by_data_quality", 0)) or 0)
                              + (_num(board.get("total_rejected_by_veto", 0)) or 0)
            if board else None,
            "primary_rejection_reason_counts": primary_hist,
            "veto_flag_counts": veto_hist,
            "candidate_cap": cap,
            "admitted_count": len(candidates),
            "cutoff_rank": cutoff_rank,
            "cutoff_score": cutoff_score,
        },
        # Stage 5 outcomes. An analysis failure is NOT a market WAIT.
        "analysis": _counts(analysis),
        "base_tiers": _counts(base_tier_counts),
        "ladder_baskets": _counts(ladder_counts),
        # Stage 6.596 — the tier actually served, after ladder + floor + seal.
        "final_tiers": _counts(final_tier_counts),
        "suppression": {
            "check_alert_reason_counts": reasons,
            "cooldown_suppressed": reasons.get(COOLDOWN_SUPPRESSION_REASON, 0),
            "dedup_key_suppression_supported": False,
        },
        "delivery": _counts(delivery),
    }


# ---------------------------------------------------------------------------
# Layer 2 — compact decision traces
# ---------------------------------------------------------------------------

def compact_ladder(ladder) -> dict:
    """Whitelisted projection of the ACTUAL scan-time snipe_ladder, captured
    after arbitration + the 14S.7C capital floor."""
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
            continue
        else:
            out[key] = _scalar(val)
    return out or None


def compact_candle_evidence(candle) -> dict:
    if not isinstance(candle, dict):
        return None
    out = {k: _scalar(candle.get(k)) for k in _CANDLE_KEYS if k in candle}
    return out or None


def near_cut_slice(ranked_results, config=None) -> list:
    """The admission-boundary window, derived from the CONFIGURED cap so the
    telemetry stays truthful if the cap changes. With cap=30 this is
    ranked_results[30:60] -> ranks 31-60. Pure copy: no Claude call, no
    market-data refetch, no strategy evaluation, no promotion, no cap change."""
    ranked = ranked_results if isinstance(ranked_results, list) else []
    start = candidate_cap(config)
    window = ranked[start:start + _NEAR_CUT_WINDOW]
    return [(r, start + i + 1) for i, r in enumerate(window) if isinstance(r, dict)]


def _pipeline_block(pf_res, rank, admitted, analyzed):
    pf_res = pf_res if isinstance(pf_res, dict) else {}
    return {
        "market_data_ok": (pf_res.get("data_status") == "OK") if pf_res else None,
        "prefilter_eligible": bool(pf_res.get("eligible_for_claude")) if pf_res else None,
        "prefilter_rank": _num(rank),
        "prefilter_score": _num(pf_res.get("prefilter_score")) if pf_res else None,
        "admitted_to_deep_analysis": admitted,
        "claude_analyzed": analyzed,
    }


def build_near_cut_trace(scan_id, result, rank) -> dict:
    result = result if isinstance(result, dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "ticker": _scalar(result.get("ticker")),
        "trace_kind": TRACE_NEAR_CUT,
        "pipeline": _pipeline_block(result, rank, False, False),
        "veto_flags": _str_list(result.get("veto_flags"), limit=6),
    }


def build_analysis_failure_trace(scan_id, ticker, pf_res, rank, trace_kind,
                                 failure_code=None) -> dict:
    """A candidate that disappeared BEFORE any market judgment existed.

    Contains only facts that actually happened. It MUST NOT invent a
    final_tier, ladder basket, capital_action, or suppression reason — no
    judgment was made, so none is recorded.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": _scalar(scan_id),
        "ticker": _scalar(ticker),
        "trace_kind": _scalar(trace_kind),
        "pipeline": _pipeline_block(pf_res, rank, True,
                                    trace_kind == TRACE_TIERING_FAILED),
        "analysis_outcome": _scalar(trace_kind),
        "failure_code": _scalar(failure_code),
    }


def compact_four_hour_real(four_hour, proxy_comparison=None) -> dict | None:
    """Compact Phase R4H-1 shadow projection for a decision trace.

    Whitelisted scalars only — never bar arrays, swing lists, or zone history.
    Returns None when the organ produced nothing, so old traces and rows
    without 4H evidence stay valid with no retroactive reconstruction.
    """
    if not isinstance(four_hour, dict) or not four_hour:
        return None
    bc = four_hour.get("bar_context")
    bc = bc if isinstance(bc, dict) else {}
    cmp_ = proxy_comparison if isinstance(proxy_comparison, dict) else (
        four_hour.get("proxy_comparison") if isinstance(four_hour.get("proxy_comparison"), dict) else {}
    )
    missing = four_hour.get("missing_proofs")
    missing = [_scalar(m) for m in missing[:4]] if isinstance(missing, list) else []
    return {
        "status": _scalar(four_hour.get("status")),
        "authority_mode": _scalar(four_hour.get("authority_mode")),
        "structural_state": _scalar(four_hour.get("structural_state")),
        "location_state": _scalar(four_hour.get("operational_location")),
        "readiness": _scalar(four_hour.get("operational_readiness")),
        "last_closed_time": _scalar(bc.get("last_closed_4h_time")),
        "live_bar_available": bc.get("live_bar_available") is True,
        "last_closed_source_complete": bc.get("last_closed_source_complete") is True,
        "confirmed_history_bars": _num(bc.get("confirmed_history_bars")),
        "proxy_state": _scalar(cmp_.get("proxy_state")),
        "proxy_agreement": _scalar(cmp_.get("agreement")),
        "missing_proofs": missing,
    }


def build_decision_trace(scan_id, ticker, pf_res, rank, tiering_result,
                         dedup_decision=None, send_result=None,
                         claude_analyzed=True, base_final_tier=None,
                         check_alert_evaluated_tier=None,
                         check_alert_evaluated_capital_action=None) -> dict:
    """Compact Layer-2 record for a JUDGED candidate — including WAIT rows and
    rows whose delivery path disappears. Everything is copied, nothing
    recomputed."""
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
        "trace_kind": TRACE_ANALYZED,
        "pipeline": _pipeline_block(pf_res, rank, True, bool(claude_analyzed)),
        "judgment": {
            # base = immediately after tiering.validate()
            "base_final_tier": _scalar(base_final_tier),
            # final = after 1H, HTF, gate, ladder, capital floor, seal
            "final_tier": _scalar(tr.get("final_tier")),
            "capital_action": _scalar(tr.get("capital_action")),
            "final_discord_channel": _scalar(tr.get("final_discord_channel")),
            "safe_for_alert": tr.get("safe_for_alert") is True,
            "score": _num(tr.get("score")),
        },
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
            "invalidation_condition": _scalar(signal.get("invalidation_condition")),
            "risk_distance_pct": _num(signal.get("risk_distance_pct")),
            "risk_reward": _num(signal.get("risk_reward")),
            "overhead_status": _scalar(signal.get("overhead_status")),
        },
        "candle_evidence": compact_candle_evidence(tr.get("candle_evidence")),
        "four_hour_real": compact_four_hour_real(tr.get("four_hour_operational")),
        "suppression": {
            "check_alert_reason": reason,
            "should_alert": dd.get("should_alert") if dd else None,
            "dedup_key": _scalar(dd.get("dedup_key")) if dd else None,
            # M1 — the tier check_alert ACTUALLY evaluated. check_alert runs at
            # Step 6, before the ladder; final_tier above may be higher. The
            # ledger must never imply the final tier was the decision basis.
            "check_alert_evaluated_tier": _scalar(check_alert_evaluated_tier),
            "check_alert_evaluated_capital_action": _scalar(
                check_alert_evaluated_capital_action),
            "cooldown_suppressed": reason == COOLDOWN_SUPPRESSION_REASON,
            "dedup_key_suppression_supported": False,
        },
        "delivery": {
            "send_alert_called": bool(sr) or None,
            "network_attempted": network_attempted(sr),
            "state": delivery_state(sr),
            "sent": sr.get("sent") if sr else None,
            "skipped_reason": _scalar(sr.get("skipped_reason")) if sr else None,
            "error_type": _scalar(sr.get("error_type")) if sr else None,
        },
    }

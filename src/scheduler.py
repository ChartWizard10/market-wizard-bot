"""Auto-scan scheduler, pipeline orchestrator, and market hours gate.

Pipeline order (enforced — no shortcuts):
  market_data.batch_download
  → indicators.enrich
  → prefilter.prefilter (score + veto + cap)
  → claude_client.async_claude_scan (capped candidates only)
  → tiering.validate (final tier authority)
  → state_store.check_alert (dedup)
  → discord_alerts.send_alert (route + post)
  → state_store.record_alert + save

Does not bypass tiering gates. Does not bypass JSON validation.
WAIT never posts. Disabled indicators never introduced here.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from src import discord_alerts
from src import indicators
from src import market_data as market_data_mod
from src import prefilter as prefilter_mod
from src import state_store
from src import tiering
from src.claude_client import async_claude_scan, claude_call

log = logging.getLogger(__name__)

_SCAN_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# Market hours gate
# ---------------------------------------------------------------------------

def is_market_hours(config: dict, _now: datetime | None = None) -> bool:
    """Return True if it is currently within configured market hours on a weekday.

    Args:
        config:  doctrine config dict
        _now:    override current time (for testing); must be tz-aware
    """
    scan_cfg = config.get("scan", {})
    if not scan_cfg.get("market_hours_only", True):
        return True

    tz_name = scan_cfg.get("timezone", "America/New_York")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")

    now = _now if _now is not None else datetime.now(tz)

    # Weekdays only: Monday=0 … Friday=4
    if now.weekday() >= 5:
        return False

    open_str  = scan_cfg.get("market_open",  "09:35")
    close_str = scan_cfg.get("market_close", "15:55")

    open_h,  open_m  = map(int, open_str.split(":"))
    close_h, close_m = map(int, close_str.split(":"))

    now_minutes   = now.hour * 60 + now.minute
    open_minutes  = open_h  * 60 + open_m
    close_minutes = close_h * 60 + close_m

    return open_minutes <= now_minutes <= close_minutes


# ---------------------------------------------------------------------------
# Scan ID
# ---------------------------------------------------------------------------

def _make_scan_id() -> str:
    return f"scan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Abort helper
# ---------------------------------------------------------------------------

def _abort_summary(scan_id: str, started_at: str, total_tickers: int, error: str) -> dict:
    return {
        "scan_id":                    scan_id,
        "started_at":                 started_at,
        "ended_at":                   datetime.utcnow().isoformat(),
        "duration_seconds":           0.0,
        "is_manual":                  False,
        "market_hours":               False,
        "status":                     "aborted",
        "error":                      error,
        "total_tickers_input":        total_tickers,
        "total_evaluated":            0,
        "total_data_failures":        total_tickers,
        "total_prefilter_rejected":   0,
        "total_prefilter_passed":     0,
        "total_claude_candidates":    0,
        "total_claude_success":       0,
        "total_claude_failed":        0,
        "final_tier_counts":          {"SNIPE_IT": 0, "STARTER": 0, "NEAR_ENTRY": 0, "WAIT": 0},
        "alerts_sent":                0,
        "alerts_suppressed":          0,
        "top_candidates":                [],
        "failures":                      [{"type": "ABORT", "detail": error}],
        "first_data_failure_reasons":    [],
    }


# ---------------------------------------------------------------------------
# Core pipeline (used by both scheduled and manual scans)
# ---------------------------------------------------------------------------

async def run_scan_pipeline(
    tickers: list,
    bot,
    config: dict,
    state: dict,
    system_prompt: str,
    client,
    scan_id: str = "",
    is_manual: bool = False,
) -> dict:
    """Execute the full scan pipeline for the given ticker list.

    State is updated in-memory and saved to disk after the pipeline completes.
    Does not acquire the scan lock — callers are responsible for that.

    Returns a scan summary dict.
    """
    if not scan_id:
        scan_id = _make_scan_id()

    started_at = datetime.utcnow().isoformat()
    start_ts   = datetime.utcnow()

    total_tickers_input      = len(tickers)
    total_data_failures      = 0
    total_prefilter_rejected = 0
    total_prefilter_passed   = 0
    total_claude_candidates  = 0
    total_claude_success     = 0
    total_claude_failed      = 0
    alerts_sent              = 0
    alerts_suppressed        = 0
    final_tier_counts        = {"SNIPE_IT": 0, "STARTER": 0, "NEAR_ENTRY": 0, "WAIT": 0}
    failures: list           = []
    top_candidates: list     = []
    data_failure_sample: list = []

    log.info("scan_start: scan_id=%s tickers=%d manual=%s", scan_id, total_tickers_input, is_manual)

    # ------------------------------------------------------------------
    # Step 1: Batch download all tickers
    # ------------------------------------------------------------------
    try:
        market_results = market_data_mod.batch_download(tickers, config)
    except Exception as exc:
        log.error("batch_download aborted scan: %s", exc)
        return _abort_summary(scan_id, started_at, total_tickers_input, str(exc))

    # ------------------------------------------------------------------
    # Step 2: Enrich each OK ticker with structure-first features
    # ------------------------------------------------------------------
    enriched_map: dict = {}

    for ticker in tickers:
        mres = market_results.get(ticker)
        if not mres:
            total_data_failures += 1
            failures.append({"ticker": ticker, "type": "FETCH_MISSING"})
            enriched_map[ticker] = {"ticker": ticker, "data_status": "ERROR", "latest_close": None}
            continue

        if mres["data_status"] != "OK":
            total_data_failures += 1
            detail = mres.get("error", "")
            failures.append({
                "ticker": ticker,
                "type":   mres["data_status"],
                "detail": detail,
            })
            if len(data_failure_sample) < 10:
                data_failure_sample.append(f"{ticker}: {mres['data_status']} — {detail}")
            enriched_map[ticker] = {
                "ticker":       ticker,
                "data_status":  mres["data_status"],
                "latest_close": None,
            }
            continue

        try:
            enriched = indicators.enrich(ticker, mres["df"], config)
            enriched["data_status"]  = "OK"
            enriched["latest_close"] = mres["latest_close"]
            enriched_map[ticker] = enriched
        except Exception as exc:
            log.warning("ENRICH_ERROR: %s: %s", ticker, exc)
            total_data_failures += 1
            failures.append({"ticker": ticker, "type": "ENRICH_ERROR", "detail": str(exc)})
            if len(data_failure_sample) < 10:
                data_failure_sample.append(f"{ticker}: ENRICH_ERROR — {exc}")
            enriched_map[ticker] = {"ticker": ticker, "data_status": "ERROR", "latest_close": None}

    if total_data_failures > 0:
        log.warning(
            "DATA_FAILURES: %d/%d tickers failed market data fetch. Sample: %s",
            total_data_failures, total_tickers_input, data_failure_sample,
        )

    # ------------------------------------------------------------------
    # Step 3: Prefilter — score, veto, rank, cap
    # ------------------------------------------------------------------
    all_enriched = list(enriched_map.values())
    try:
        pf_result = prefilter_mod.prefilter(all_enriched, config)
    except Exception as exc:
        log.error("prefilter aborted scan: %s", exc)
        return _abort_summary(scan_id, started_at, total_tickers_input, str(exc))

    bs = pf_result["board_summary"]
    total_prefilter_rejected = (
        bs["total_rejected_by_data_quality"] + bs["total_rejected_by_veto"]
    )
    total_prefilter_passed  = bs["total_above_prefilter_min_score"]
    total_claude_candidates = bs["total_claude_candidates"]

    # ticker → prefilter result dict (for veto flags passed to tiering.validate)
    pf_map: dict = {r["ticker"]: r for r in pf_result["all_results"]}

    # Enriched dicts for capped Claude candidates (preserves ranking order)
    claude_candidate_tickers = [r["ticker"] for r in pf_result["claude_candidates"]]
    claude_enriched = [enriched_map[t] for t in claude_candidate_tickers if t in enriched_map]

    top_candidates = [
        {"ticker": r["ticker"], "score": r["prefilter_score"]}
        for r in pf_result["ranked_results"][:10]
    ]

    log.info(
        "prefilter_complete: %d input → %d ranked → %d claude_candidates",
        total_tickers_input, len(pf_result["ranked_results"]), total_claude_candidates,
    )

    # ------------------------------------------------------------------
    # Step 4: Claude analysis (capped candidates only)
    # ------------------------------------------------------------------
    if claude_enriched and client is not None:
        try:
            claude_results = await async_claude_scan(
                claude_enriched, system_prompt, client, config
            )
        except Exception as exc:
            log.error("async_claude_scan failed: %s", exc)
            claude_results = [
                {
                    "ticker":        e.get("ticker", "UNKNOWN"),
                    "signal":        None,
                    "error_type":    "CLAUDE_API_ERROR",
                    "error_message": str(exc),
                }
                for e in claude_enriched
            ]
    else:
        claude_results = []

    log.info("claude_complete: %d results", len(claude_results))

    # ------------------------------------------------------------------
    # Steps 5–8: Per-result: tiering → dedup → alert → record
    # ------------------------------------------------------------------
    for cr in claude_results:
        ticker = cr.get("ticker", "UNKNOWN")

        if cr.get("signal") is None:
            total_claude_failed += 1
            failures.append({
                "ticker": ticker,
                "type":   cr.get("error_type", "UNKNOWN"),
                "detail": cr.get("error_message", ""),
            })
            final_tier_counts["WAIT"] = final_tier_counts.get("WAIT", 0) + 1
            continue

        total_claude_success += 1
        pf_res = pf_map.get(ticker, {})

        # Step 5: Tiering validation (sole final authority — cannot be bypassed)
        try:
            tiering_result = tiering.validate(cr["signal"], pf_res, config)
        except Exception as exc:
            log.warning("TIERING_ERROR: %s: %s", ticker, exc)
            failures.append({"ticker": ticker, "type": "TIERING_ERROR", "detail": str(exc)})
            final_tier_counts["WAIT"] = final_tier_counts.get("WAIT", 0) + 1
            continue

        final_tier = tiering_result.get("final_tier", "WAIT")
        final_tier_counts[final_tier] = final_tier_counts.get(final_tier, 0) + 1

        # Step 6: Dedup check
        try:
            dedup_decision = state_store.check_alert(
                tiering_result, state, config, manual_override=is_manual
            )
        except Exception as exc:
            log.warning("DEDUP_ERROR: %s: %s", ticker, exc)
            dedup_decision = {"should_alert": False, "reason": "dedup_error"}

        # Step 7: Discord alert
        try:
            send_result = await discord_alerts.send_alert(
                tiering_result, dedup_decision, bot, config, scan_id
            )
        except Exception as exc:
            log.error("DISCORD_SEND_FAILED: %s %s: %s", final_tier, ticker, exc)
            failures.append({"ticker": ticker, "type": "DISCORD_SEND_FAILED", "detail": str(exc)})
            continue

        # Step 8: Record alert to state if sent
        if send_result.get("sent"):
            alerts_sent += 1
            try:
                state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            except Exception as exc:
                log.critical("CRITICAL: state record failed: %s: %s", ticker, exc)
        else:
            if dedup_decision and not dedup_decision.get("should_alert", True):
                alerts_suppressed += 1

    # ------------------------------------------------------------------
    # Save state after full cycle
    # ------------------------------------------------------------------
    try:
        state_store.save(state, config)
    except Exception as exc:
        log.critical("CRITICAL: state write failed: %s", exc)

    ended_at         = datetime.utcnow().isoformat()
    duration_seconds = (datetime.utcnow() - start_ts).total_seconds()

    log.info(
        "scan_end: scan_id=%s duration=%.1fs alerts=%d suppressed=%d",
        scan_id, duration_seconds, alerts_sent, alerts_suppressed,
    )

    return {
        "scan_id":                  scan_id,
        "started_at":               started_at,
        "ended_at":                 ended_at,
        "duration_seconds":         round(duration_seconds, 3),
        "is_manual":                is_manual,
        "market_hours":             is_market_hours(config),
        "status":                   "complete",
        "total_tickers_input":      total_tickers_input,
        "total_evaluated":          total_tickers_input,
        "total_data_failures":      total_data_failures,
        "total_prefilter_rejected": total_prefilter_rejected,
        "total_prefilter_passed":   total_prefilter_passed,
        "total_claude_candidates":  total_claude_candidates,
        "total_claude_success":     total_claude_success,
        "total_claude_failed":      total_claude_failed,
        "final_tier_counts":        final_tier_counts,
        "alerts_sent":              alerts_sent,
        "alerts_suppressed":        alerts_suppressed,
        "top_candidates":                top_candidates,
        "failures":                      failures,
        "first_data_failure_reasons":    data_failure_sample,
    }


# ---------------------------------------------------------------------------
# Full scan with overlap lock (scheduled and manual !scan)
# ---------------------------------------------------------------------------

async def run_full_scan(
    bot,
    config: dict,
    system_prompt: str,
    client,
    scan_id: str = "",
    is_manual: bool = False,
    _lock: asyncio.Lock | None = None,
) -> dict:
    """Load tickers + state, acquire overlap lock, run pipeline.

    Returns scan summary. If the lock is already held, returns a skipped
    summary without running the pipeline.

    Args:
        _lock: override the module-level lock (for testing)
    """
    lock = _lock if _lock is not None else _SCAN_LOCK

    if lock.locked():
        log.warning("SCAN_SKIPPED: previous scan still running (is_manual=%s)", is_manual)
        return {
            "scan_id":   scan_id or "skipped",
            "status":    "skipped",
            "reason":    "scan_already_running",
            "is_manual": is_manual,
        }

    async with lock:
        scan_id = scan_id or _make_scan_id()

        ticker_file   = config.get("scan", {}).get("ticker_file", "config/tickers.txt")
        ticker_result = market_data_mod.load_tickers(ticker_file)
        tickers       = ticker_result.get("tickers", [])

        if not tickers:
            log.error("No tickers loaded from %s", ticker_file)
            return _abort_summary(
                scan_id, datetime.utcnow().isoformat(), 0, "no tickers loaded"
            )

        state = state_store.load(config)

        return await run_scan_pipeline(
            tickers, bot, config, state, system_prompt, client, scan_id, is_manual
        )


# ---------------------------------------------------------------------------
# Single-ticker manual analyze (!analyze TICKER)
# ---------------------------------------------------------------------------

async def run_analyze(
    ticker: str,
    bot,
    config: dict,
    system_prompt: str,
    client,
    _lock: asyncio.Lock | None = None,
) -> dict:
    """Single-ticker analysis with manual_override=True.

    Bypasses prefilter score floor and dedup cooldown.
    Still enforces: tiering hard gates, JSON validation, safe_for_alert, WAIT suppression.
    """
    lock = _lock if _lock is not None else _SCAN_LOCK

    if lock.locked():
        log.warning("ANALYZE_SKIPPED: scan lock held — cannot analyze %s", ticker)
        return {
            "status":     "skipped",
            "reason":     "scan_already_running",
            "ticker":     ticker,
            "final_tier": "WAIT",
        }

    async with lock:
        scan_id = f"analyze_{ticker}_{datetime.utcnow().strftime('%H%M%S')}"

        # Fetch
        try:
            mres = market_data_mod.fetch_ticker(ticker, config)
        except Exception as exc:
            log.warning("FETCH_ERROR in !analyze %s: %s", ticker, exc)
            return {"status": "error", "ticker": ticker, "error": str(exc), "final_tier": "WAIT"}

        if mres["data_status"] != "OK":
            return {
                "status":      "data_failure",
                "ticker":      ticker,
                "data_status": mres["data_status"],
                "final_tier":  "WAIT",
            }

        # Enrich
        try:
            enriched = indicators.enrich(ticker, mres["df"], config)
            enriched["data_status"]  = "OK"
            enriched["latest_close"] = mres["latest_close"]
        except Exception as exc:
            log.warning("ENRICH_ERROR in !analyze %s: %s", ticker, exc)
            return {"status": "error", "ticker": ticker, "error": str(exc), "final_tier": "WAIT"}

        # Prefilter (veto flags only — score floor bypassed for !analyze)
        pf_res = prefilter_mod.score_ticker(enriched, config)

        # Claude — cannot skip
        if client is None:
            return {
                "status":     "error",
                "ticker":     ticker,
                "error":      "ANTHROPIC_KEY not configured",
                "final_tier": "WAIT",
            }

        try:
            semaphore = asyncio.Semaphore(1)
            cr = await claude_call(enriched, system_prompt, client, semaphore, config)
        except Exception as exc:
            log.warning("CLAUDE_ERROR in !analyze %s: %s", ticker, exc)
            return {"status": "error", "ticker": ticker, "error": str(exc), "final_tier": "WAIT"}

        if cr.get("signal") is None:
            return {
                "status":        "claude_error",
                "ticker":        ticker,
                "error_type":    cr.get("error_type"),
                "error_message": cr.get("error_message"),
                "final_tier":    "WAIT",
            }

        # Tiering (cannot be bypassed)
        tiering_result = tiering.validate(cr["signal"], pf_res, config)
        final_tier     = tiering_result.get("final_tier", "WAIT")

        # State + dedup — manual_override=True bypasses cooldown
        state = state_store.load(config)
        dedup_decision = state_store.check_alert(
            tiering_result, state, config, manual_override=True
        )

        # Alert
        send_result = await discord_alerts.send_alert(
            tiering_result, dedup_decision, bot, config, scan_id
        )

        if send_result.get("sent"):
            state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            try:
                state_store.save(state, config)
            except Exception as exc:
                log.critical("CRITICAL: state write failed after !analyze: %s", exc)

        return {
            "status":         "complete",
            "scan_id":        scan_id,
            "ticker":         ticker,
            "final_tier":     final_tier,
            "safe_for_alert": tiering_result.get("safe_for_alert"),
            "dedup_reason":   dedup_decision.get("reason"),
            "alert_sent":     send_result.get("sent", False),
            "channel_id":     send_result.get("channel_id"),
            "tiering_result": tiering_result,
        }

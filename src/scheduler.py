"""Auto-scan scheduler, pipeline orchestrator, and market-hours gate.

Production order:
  market_data -> indicators -> prefilter -> Claude -> deterministic tiering
  -> shared post-tiering chart judgment -> final-tier dedup -> Discord -> state.

Phase 14W law: manual ``!analyze`` may bypass universe admission/cooldown, but
it may never bypass chart judgment. Autoscan and manual analysis therefore use
the same post-tiering evidence/arbitration organ.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from src import candle_evidence
from src import discord_alerts
from src import four_hour_authority
from src import four_hour_operational
from src import higher_timeframe_context
from src import indicators
from src import market_data as market_data_mod
from src import one_hour_entry
from src import prefilter as prefilter_mod
from src import scan_telemetry
from src import score_calibration
from src import snipe_confirmed_seal
from src import snipe_gate_audit
from src import snipe_ladder_judgment
from src import state_store
from src import tiering
from src import timeframe_alignment
from src import trade_location
from src import trajectory as trajectory_mod
from src.claude_client import async_claude_scan, claude_call

log = logging.getLogger(__name__)

_SCAN_LOCK = asyncio.Lock()


def is_market_hours(config: dict, _now: datetime | None = None) -> bool:
    """Return True inside the configured weekday market-hours window."""
    scan_cfg = config.get("scan", {})
    if not scan_cfg.get("market_hours_only", True):
        return True

    try:
        tz = ZoneInfo(scan_cfg.get("timezone", "America/New_York"))
    except Exception:
        tz = ZoneInfo("America/New_York")

    now = _now if _now is not None else datetime.now(tz)
    if now.weekday() >= 5:
        return False

    open_h, open_m = map(int, scan_cfg.get("market_open", "09:35").split(":"))
    close_h, close_m = map(int, scan_cfg.get("market_close", "15:55").split(":"))
    minute = now.hour * 60 + now.minute
    return (open_h * 60 + open_m) <= minute <= (close_h * 60 + close_m)


def _make_scan_id() -> str:
    return f"scan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _abort_summary(scan_id: str, started_at: str, total_tickers: int, error: str) -> dict:
    return {
        "scan_id": scan_id,
        "started_at": started_at,
        "ended_at": datetime.utcnow().isoformat(),
        "duration_seconds": 0.0,
        "is_manual": False,
        "market_hours": False,
        "status": "aborted",
        "error": error,
        "total_tickers_input": total_tickers,
        "total_evaluated": 0,
        "total_data_failures": total_tickers,
        "total_prefilter_rejected": 0,
        "total_prefilter_passed": 0,
        "total_claude_candidates": 0,
        "total_claude_success": 0,
        "total_claude_failed": 0,
        "total_claude_rate_limited": 0,
        "final_tier_counts": {"SNIPE_IT": 0, "STARTER": 0, "NEAR_ENTRY": 0, "WAIT": 0},
        "alerts_sent": 0,
        "alerts_suppressed": 0,
        "top_candidates": [],
        "failures": [{"type": "ABORT", "detail": error}],
        "first_data_failure_reasons": [],
    }


# ---------------------------------------------------------------------------
# Phase 14W — one shared post-tiering candidate judgment organ
# ---------------------------------------------------------------------------

def _complete_candidate_judgment(
    ticker: str,
    tiering_result: dict,
    enriched: dict,
    market_result: dict,
    config: dict,
    previous_state: dict | None = None,
) -> dict:
    """Run every post-tiering chart judgment for one candidate.

    Fixed order:
      trajectory -> trade location -> candle evidence -> 1H trigger -> legacy
      operational proxy snapshot -> REAL 4H evidence -> R4H-2 operational
      authority + reconciled MTF alignment -> HTF context -> SNIPE gate audit
      -> SNIPE ladder -> R4H-2 capital floor -> downgrade-only seal -> final
      audit reconcile -> score calibration.

    This organ deliberately does not dedup, route, send Discord messages,
    persist state, or write scan-funnel telemetry. Execution governance begins
    only after the final executable tier is known.
    """
    tiering_result = tiering_result if isinstance(tiering_result, dict) else {}
    enriched = enriched if isinstance(enriched, dict) else {}
    market_result = market_result if isinstance(market_result, dict) else {}
    final_tier = tiering_result.get("final_tier", "WAIT")

    try:
        tiering_result["trajectory"] = trajectory_mod.compute(
            tiering_result, previous_state
        )
    except Exception as exc:
        log.warning("TRAJECTORY_ERROR: %s: %s", ticker, exc)
        tiering_result["trajectory"] = {"label": "UNKNOWN", "text": ""}

    try:
        tiering_result["trade_location"] = trade_location.build_trade_location_context(
            enriched, tiering_result
        )
    except Exception as exc:
        log.warning("TRADE_LOCATION_ERROR: %s: %s", ticker, exc)
        tiering_result["trade_location"] = None

    try:
        tiering_result["candle_evidence"] = candle_evidence.build_candle_evidence_context(
            enriched, tiering_result
        )
    except Exception as exc:
        log.warning("CANDLE_EVIDENCE_ERROR: %s: %s", ticker, exc)
        tiering_result["candle_evidence"] = candle_evidence._unknown_context()

    try:
        one_hour_envelope = market_data_mod.fetch_one_hour_bars(ticker, config)
    except Exception as exc:
        log.warning("ONE_HOUR_FETCH_ERROR: %s: %s", ticker, exc)
        one_hour_envelope = None

    try:
        tiering_result["one_hour_entry"] = one_hour_entry.build_one_hour_entry_context(
            ticker,
            tiering_result,
            enriched_data=enriched,
            one_hour_bars=one_hour_envelope,
            config=config,
        )
    except Exception as exc:
        log.warning("ONE_HOUR_ENTRY_ERROR: %s: %s", ticker, exc)
        tiering_result["one_hour_entry"] = None

    # Build Phase-14F once to preserve its operational proxy as a diagnostic and
    # emergency rollback baseline. R4H-2 reconciles this object after real 4H is
    # known; no downstream gate sees the stale proxy as authority in production.
    try:
        tiering_result["timeframe_alignment"] = timeframe_alignment.build_timeframe_alignment_context(
            ticker,
            tiering_result,
            enriched_data=enriched,
            config=config,
        )
    except Exception as exc:
        log.warning("TIMEFRAME_ALIGNMENT_ERROR: %s: %s", ticker, exc)
        tiering_result["timeframe_alignment"] = timeframe_alignment.error_timeframe_alignment_object(str(exc))

    # REAL 4H comes from the SAME 60m provider response already fetched for 1H.
    # There is no second network request and no fabricated aggregation.
    try:
        env = one_hour_envelope if isinstance(one_hour_envelope, dict) else {}
        real_four_hour = four_hour_operational.build_four_hour_operational_context(
            ticker,
            tiering_result,
            enriched_data=enriched,
            four_hour_bars=env.get("four_hour"),
            config=config,
        )
    except Exception as exc:
        log.warning("FOUR_HOUR_OPERATIONAL_ERROR: %s: %s", ticker, exc)
        real_four_hour = four_hour_operational.error_four_hour_object(str(exc))

    proxy_operational = (
        (tiering_result.get("timeframe_alignment") or {}).get("operational_timeframe")
        if isinstance(tiering_result.get("timeframe_alignment"), dict)
        else None
    ) or timeframe_alignment.derive_operational_timeframe(
        tiering_result.get("trade_location") or {},
        tiering_result.get("one_hour_entry") or {},
    )

    try:
        real_four_hour["proxy_comparison"] = four_hour_operational.compare_real_vs_proxy(
            proxy_operational.get("state"), real_four_hour
        )
    except Exception as exc:
        log.warning("FOUR_HOUR_PROXY_COMPARE_ERROR: %s: %s", ticker, exc)

    tiering_result["four_hour_operational"] = real_four_hour
    tiering_result["four_hour_authority"] = four_hour_authority.build_operational_authority(
        real_four_hour, proxy_operational, config
    )
    tiering_result["timeframe_alignment"] = four_hour_authority.reconcile_timeframe_alignment(
        tiering_result.get("timeframe_alignment"),
        tiering_result,
        tiering_result.get("four_hour_authority"),
        config,
    )

    log.info(four_hour_operational.render_four_hour_log_line(
        ticker,
        real_four_hour,
        real_four_hour.get("proxy_comparison"),
    ))

    try:
        daily_bars = higher_timeframe_context.daily_bars_from_df(market_result.get("df"))
        tiering_result["higher_timeframe_context"] = higher_timeframe_context.build_higher_timeframe_context(
            ticker,
            tiering_result,
            enriched_data=enriched,
            daily_bars=daily_bars,
            config=config,
        )
    except Exception as exc:
        log.warning("HIGHER_TIMEFRAME_CONTEXT_ERROR: %s: %s", ticker, exc)
        tiering_result["higher_timeframe_context"] = higher_timeframe_context.error_htf_object(str(exc))

    try:
        tiering_result["snipe_gate_audit"] = snipe_gate_audit.build_snipe_gate_audit(
            ticker,
            tiering_result,
            enriched_data=enriched,
            config=config,
        )
    except Exception as exc:
        log.warning("SNIPE_GATE_AUDIT_ERROR: %s: %s", ticker, exc)
        tiering_result["snipe_gate_audit"] = snipe_gate_audit.error_snipe_gate_audit_object(str(exc))

    try:
        tiering_result = snipe_ladder_judgment.apply_ladder_arbitration(
            tiering_result, config
        )
        ladder = tiering_result.get("snipe_ladder") or {}
        if ladder:
            final_tier = tiering_result.get("final_tier", final_tier)
            log.info(
                "SNIPE_LADDER: %s %s (%s) -> final_tier=%s",
                ticker,
                ladder.get("internal_ladder_tier"),
                ladder.get("proof_state"),
                final_tier,
            )
    except Exception as exc:
        log.warning("SNIPE_LADDER_ERROR: %s: %s", ticker, exc)

    # R4H-2 path-independent execution barrier. It can only maintain or remove
    # capital and therefore cannot create a SNIPE/STARTER the ladder did not earn.
    tiering_result = four_hour_authority.enforce_operational_capital_floor(
        tiering_result, config
    )
    authority = tiering_result.get("four_hour_authority") or {}
    if authority.get("capital_floor_enforced"):
        log.warning(
            "R4H2_CAPITAL_FLOOR: %s -> %s reason=%s",
            ticker,
            tiering_result.get("final_tier"),
            authority.get("capital_floor_reason"),
        )

    try:
        tiering_result = snipe_confirmed_seal.seal_snipe_confirmed_consistency(
            tiering_result, config
        )
        seal = tiering_result.get("snipe_confirmed_seal") or {}
        if seal.get("applied"):
            log.warning(
                "SNIPE_CONFIRMED_SEAL: %s %s→%s blockers=%s",
                ticker,
                seal.get("original_tier"),
                seal.get("corrected_tier"),
                "; ".join(seal.get("blockers") or []),
            )
    except Exception as exc:
        log.warning("SNIPE_CONFIRMED_SEAL_ERROR: %s: %s", ticker, exc)

    try:
        snipe_gate_audit.reconcile_final_snipe_audit_state(tiering_result)
    except Exception as exc:
        log.warning("SNIPE_AUDIT_RECONCILE_ERROR: %s: %s", ticker, exc)

    try:
        tiering_result["calibration"] = score_calibration.calibrate_score(
            tiering_result, config
        )
    except Exception as exc:
        log.warning("CALIBRATION_ERROR: %s: %s", ticker, exc)
        tiering_result["calibration"] = None

    return tiering_result


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
    """Execute the full universe scan pipeline."""
    if not scan_id:
        scan_id = _make_scan_id()

    started_at = datetime.utcnow().isoformat()
    start_ts = datetime.utcnow()
    total_tickers_input = len(tickers)
    total_data_failures = 0
    total_prefilter_rejected = 0
    total_prefilter_passed = 0
    total_claude_candidates = 0
    total_claude_success = 0
    total_claude_failed = 0
    total_claude_rate_limited = 0
    alerts_sent = 0
    alerts_suppressed = 0
    final_tier_counts = {"SNIPE_IT": 0, "STARTER": 0, "NEAR_ENTRY": 0, "WAIT": 0}
    failures = []
    top_candidates = []
    data_failure_sample = []

    _tlm_traces = []
    _tlm_base_tiers = {}
    _tlm_final_tiers = {}
    _tlm_baskets = {}
    _tlm_reasons = {}
    _tlm_analysis = {
        "admitted": 0,
        "claude_success": 0,
        "claude_failed": 0,
        "claude_rate_limited": 0,
        "tiering_failed": 0,
        "judged": 0,
    }
    _tlm_delivery = {"send_alert_called": 0, "sent": 0, "skipped": 0, "failed": 0}

    log.info("scan_start: scan_id=%s tickers=%d manual=%s", scan_id, total_tickers_input, is_manual)

    try:
        market_results = market_data_mod.batch_download(tickers, config)
    except Exception as exc:
        log.error("batch_download aborted scan: %s", exc)
        return _abort_summary(scan_id, started_at, total_tickers_input, str(exc))

    enriched_map = {}
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
            failures.append({"ticker": ticker, "type": mres["data_status"], "detail": detail})
            if len(data_failure_sample) < 10:
                data_failure_sample.append(f"{ticker}: {mres['data_status']} — {detail}")
            enriched_map[ticker] = {"ticker": ticker, "data_status": mres["data_status"], "latest_close": None}
            continue

        try:
            enriched = indicators.enrich(ticker, mres["df"], config)
            enriched["data_status"] = "OK"
            enriched["latest_close"] = mres["latest_close"]
            enriched_map[ticker] = enriched
        except Exception as exc:
            log.warning("ENRICH_ERROR: %s: %s", ticker, exc)
            total_data_failures += 1
            failures.append({"ticker": ticker, "type": "ENRICH_ERROR", "detail": str(exc)})
            if len(data_failure_sample) < 10:
                data_failure_sample.append(f"{ticker}: ENRICH_ERROR — {exc}")
            enriched_map[ticker] = {"ticker": ticker, "data_status": "ERROR", "latest_close": None}

    if total_data_failures:
        log.warning(
            "DATA_FAILURES: %d/%d tickers failed market data fetch. Sample: %s",
            total_data_failures,
            total_tickers_input,
            data_failure_sample,
        )

    try:
        pf_result = prefilter_mod.prefilter(list(enriched_map.values()), config)
    except Exception as exc:
        log.error("prefilter aborted scan: %s", exc)
        return _abort_summary(scan_id, started_at, total_tickers_input, str(exc))

    bs = pf_result["board_summary"]
    total_prefilter_rejected = bs["total_rejected_by_data_quality"] + bs["total_rejected_by_veto"]
    total_prefilter_passed = bs["total_above_prefilter_min_score"]
    total_claude_candidates = bs["total_claude_candidates"]
    pf_map = {r["ticker"]: r for r in pf_result["all_results"]}
    candidate_tickers = [r["ticker"] for r in pf_result["claude_candidates"]]
    claude_enriched = [enriched_map[t] for t in candidate_tickers if t in enriched_map]
    top_candidates = [
        {"ticker": r["ticker"], "score": r["prefilter_score"]}
        for r in pf_result["ranked_results"][:10]
    ]

    log.info(
        "prefilter_complete: %d input → %d ranked → %d claude_candidates",
        total_tickers_input,
        len(pf_result["ranked_results"]),
        total_claude_candidates,
    )

    _tlm_rank_map = {}
    try:
        for i, row in enumerate(pf_result.get("ranked_results") or []):
            if isinstance(row, dict) and row.get("ticker"):
                _tlm_rank_map[row["ticker"]] = i + 1
        for row, rank in scan_telemetry.near_cut_slice(pf_result.get("ranked_results"), config):
            _tlm_traces.append(scan_telemetry.build_near_cut_trace(scan_id, row, rank))
    except Exception as exc:
        log.warning("TELEMETRY_NEAR_CUT_ERROR: %s", exc)

    def _tlm_rank_of(symbol):
        return _tlm_rank_map.get(symbol)

    if claude_enriched and client is not None:
        try:
            claude_results = await async_claude_scan(
                claude_enriched, system_prompt, client, config
            )
        except Exception as exc:
            log.error("async_claude_scan failed: %s", exc)
            claude_results = [
                {
                    "ticker": e.get("ticker", "UNKNOWN"),
                    "signal": None,
                    "error_type": "CLAUDE_API_ERROR",
                    "error_message": str(exc),
                }
                for e in claude_enriched
            ]
    else:
        claude_results = []

    log.info("claude_complete: %d results", len(claude_results))

    for cr in claude_results:
        ticker = cr.get("ticker", "UNKNOWN")
        if cr.get("signal") is None:
            error_type = cr.get("error_type", "UNKNOWN")
            if error_type == "claude_rate_limited":
                total_claude_rate_limited += 1
                log.warning(
                    "RATE_LIMITED: %s — excluded from this scan cycle, not a setup rejection",
                    ticker,
                )
            else:
                total_claude_failed += 1
            failures.append({
                "ticker": ticker,
                "type": error_type,
                "detail": cr.get("error_message", ""),
            })
            final_tier_counts["WAIT"] += 1
            try:
                _tlm_analysis["admitted"] += 1
                rate_limited = error_type == "claude_rate_limited"
                _tlm_analysis["claude_rate_limited" if rate_limited else "claude_failed"] += 1
                _tlm_traces.append(scan_telemetry.build_analysis_failure_trace(
                    scan_id,
                    ticker,
                    pf_map.get(ticker, {}),
                    _tlm_rank_of(ticker),
                    scan_telemetry.TRACE_RATE_LIMITED if rate_limited else scan_telemetry.TRACE_ANALYSIS_FAILED,
                    failure_code=error_type,
                ))
            except Exception as exc:
                log.warning("TELEMETRY_ANALYSIS_TRACE_ERROR: %s: %s", ticker, exc)
            continue

        total_claude_success += 1
        pf_res = pf_map.get(ticker, {})
        try:
            _tlm_analysis["admitted"] += 1
            _tlm_analysis["claude_success"] += 1
        except Exception:
            pass

        try:
            tiering_result = tiering.validate(cr["signal"], pf_res, config)
        except Exception as exc:
            log.warning("TIERING_ERROR: %s: %s", ticker, exc)
            failures.append({"ticker": ticker, "type": "TIERING_ERROR", "detail": str(exc)})
            final_tier_counts["WAIT"] += 1
            try:
                _tlm_analysis["tiering_failed"] += 1
                _tlm_traces.append(scan_telemetry.build_analysis_failure_trace(
                    scan_id,
                    ticker,
                    pf_res,
                    _tlm_rank_of(ticker),
                    scan_telemetry.TRACE_TIERING_FAILED,
                    failure_code="TIERING_ERROR",
                ))
            except Exception as terr:
                log.warning("TELEMETRY_TIERING_TRACE_ERROR: %s: %s", ticker, terr)
            continue

        final_tier = tiering_result.get("final_tier", "WAIT")
        _tlm_base_tier = final_tier
        _tlm_base_tiers[final_tier] = _tlm_base_tiers.get(final_tier, 0) + 1

        ticker_states = state.get("tickers", {}) if isinstance(state, dict) else {}
        previous_state = ticker_states.get(ticker) if isinstance(ticker_states, dict) else None

        # Ladder arbitration, R4H-2 capital floor, and the downgrade-only seal
        # all execute inside this shared judgment organ before final-tier dedup.
        tiering_result = _complete_candidate_judgment(
            ticker,
            tiering_result,
            enriched_map.get(ticker, {}),
            market_results.get(ticker) or {},
            config,
            previous_state,
        )
        final_tier = tiering_result.get("final_tier", final_tier)

        try:
            basket = (tiering_result.get("snipe_ladder") or {}).get("internal_ladder_tier")
            if basket:
                _tlm_baskets[basket] = _tlm_baskets.get(basket, 0) + 1
        except Exception:
            pass

        try:
            served = tiering_result.get("final_tier")
            if served:
                _tlm_final_tiers[served] = _tlm_final_tiers.get(served, 0) + 1
                _tlm_analysis["judged"] += 1
        except Exception:
            pass

        final_tier_counts[final_tier] = final_tier_counts.get(final_tier, 0) + 1
        _tlm_ca_tier = tiering_result.get("final_tier")
        _tlm_ca_capital = tiering_result.get("capital_action")

        try:
            dedup_decision = state_store.check_alert(
                tiering_result, state, config, manual_override=is_manual
            )
        except Exception as exc:
            log.warning("DEDUP_ERROR: %s: %s", ticker, exc)
            dedup_decision = {"should_alert": False, "reason": "dedup_error"}

        try:
            reason = (dedup_decision or {}).get("reason")
            if reason:
                _tlm_reasons[reason] = _tlm_reasons.get(reason, 0) + 1
        except Exception:
            pass

        try:
            send_result = await discord_alerts.send_alert(
                tiering_result, dedup_decision, bot, config, scan_id
            )
        except Exception as exc:
            log.error("DISCORD_SEND_FAILED: %s %s: %s", final_tier, ticker, exc)
            failures.append({"ticker": ticker, "type": "DISCORD_SEND_FAILED", "detail": str(exc)})
            try:
                synthetic = scan_telemetry.exception_send_result(exc)
                _tlm_delivery["send_alert_called"] += 1
                _tlm_delivery["failed"] += 1
                _tlm_traces.append(scan_telemetry.build_decision_trace(
                    scan_id,
                    ticker,
                    pf_res,
                    _tlm_rank_of(ticker),
                    tiering_result,
                    dedup_decision,
                    synthetic,
                    claude_analyzed=True,
                    base_final_tier=_tlm_base_tier,
                    check_alert_evaluated_tier=_tlm_ca_tier,
                    check_alert_evaluated_capital_action=_tlm_ca_capital,
                ))
            except Exception as terr:
                log.warning("TELEMETRY_SEND_FAULT_TRACE_ERROR: %s: %s", ticker, terr)
            continue

        if send_result.get("sent"):
            alerts_sent += 1
            try:
                state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            except Exception as exc:
                log.critical("CRITICAL: state record failed: %s: %s", ticker, exc)
        elif dedup_decision and not dedup_decision.get("should_alert", True):
            alerts_suppressed += 1

        try:
            _tlm_delivery["send_alert_called"] += 1
            delivery_state = scan_telemetry.delivery_state(send_result)
            if delivery_state == scan_telemetry.DELIVERY_SENT:
                _tlm_delivery["sent"] += 1
            elif delivery_state == scan_telemetry.DELIVERY_FAILED:
                _tlm_delivery["failed"] += 1
            else:
                _tlm_delivery["skipped"] += 1
            _tlm_traces.append(scan_telemetry.build_decision_trace(
                scan_id,
                ticker,
                pf_res,
                _tlm_rank_of(ticker),
                tiering_result,
                dedup_decision,
                send_result,
                claude_analyzed=True,
                base_final_tier=_tlm_base_tier,
                check_alert_evaluated_tier=_tlm_ca_tier,
                check_alert_evaluated_capital_action=_tlm_ca_capital,
            ))
        except Exception as exc:
            log.warning("TELEMETRY_TRACE_ERROR: %s: %s", ticker, exc)

    try:
        state_store.save(state, config)
    except Exception as exc:
        log.critical("CRITICAL: state write failed: %s", exc)

    try:
        summary = scan_telemetry.build_scan_summary(
            scan_id,
            started_at,
            total_tickers_input,
            total_data_failures,
            pf_result,
            config,
            final_tier_counts=_tlm_final_tiers,
            ladder_counts=_tlm_baskets,
            base_tier_counts=_tlm_base_tiers,
            check_alert_reason_counts=_tlm_reasons,
            delivery=_tlm_delivery,
            analysis=_tlm_analysis,
        )
        await asyncio.to_thread(
            scan_telemetry.write_scan_telemetry,
            config,
            summary,
            _tlm_traces,
        )
    except Exception as exc:
        log.warning("TELEMETRY_WRITE_ERROR: %s", exc)

    ended_at = datetime.utcnow().isoformat()
    duration_seconds = (datetime.utcnow() - start_ts).total_seconds()
    log.info(
        "scan_end: scan_id=%s duration=%.1fs alerts=%d suppressed=%d",
        scan_id,
        duration_seconds,
        alerts_sent,
        alerts_suppressed,
    )

    return {
        "scan_id": scan_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 3),
        "is_manual": is_manual,
        "market_hours": is_market_hours(config),
        "status": "complete",
        "total_tickers_input": total_tickers_input,
        "total_evaluated": total_tickers_input,
        "total_data_failures": total_data_failures,
        "total_prefilter_rejected": total_prefilter_rejected,
        "total_prefilter_passed": total_prefilter_passed,
        "total_claude_candidates": total_claude_candidates,
        "total_claude_success": total_claude_success,
        "total_claude_failed": total_claude_failed,
        "total_claude_rate_limited": total_claude_rate_limited,
        "final_tier_counts": final_tier_counts,
        "alerts_sent": alerts_sent,
        "alerts_suppressed": alerts_suppressed,
        "top_candidates": top_candidates,
        "failures": failures,
        "first_data_failure_reasons": data_failure_sample,
    }


async def run_full_scan(
    bot,
    config: dict,
    system_prompt: str,
    client,
    scan_id: str = "",
    is_manual: bool = False,
    _lock: asyncio.Lock | None = None,
) -> dict:
    """Load tickers/state, enforce overlap lock, and run a full scan."""
    lock = _lock if _lock is not None else _SCAN_LOCK
    if lock.locked():
        log.warning("SCAN_SKIPPED: previous scan still running (is_manual=%s)", is_manual)
        return {
            "scan_id": scan_id or "skipped",
            "status": "skipped",
            "reason": "scan_already_running",
            "is_manual": is_manual,
        }

    async with lock:
        scan_id = scan_id or _make_scan_id()
        ticker_file = config.get("scan", {}).get("ticker_file", "config/tickers.txt")
        ticker_result = market_data_mod.load_tickers(ticker_file)
        tickers = ticker_result.get("tickers", [])
        if not tickers:
            log.error("No tickers loaded from %s", ticker_file)
            return _abort_summary(
                scan_id, datetime.utcnow().isoformat(), 0, "no tickers loaded"
            )
        state = state_store.load(config)
        return await run_scan_pipeline(
            tickers, bot, config, state, system_prompt, client, scan_id, is_manual
        )


async def run_analyze(
    ticker: str,
    bot,
    config: dict,
    system_prompt: str,
    client,
    _lock: asyncio.Lock | None = None,
) -> dict:
    """Single-ticker manual inspection using the production judgment stack.

    Bypasses universe prefilter admission and dedup cooldown only. JSON
    validation, deterministic tiering vetoes, chart evidence, ladder/capital
    arbitration, the downgrade-only seal, WAIT suppression and safety bind.
    """
    lock = _lock if _lock is not None else _SCAN_LOCK
    if lock.locked():
        log.warning("ANALYZE_SKIPPED: scan lock held — cannot analyze %s", ticker)
        return {
            "status": "skipped",
            "reason": "scan_already_running",
            "ticker": ticker,
            "final_tier": "WAIT",
        }

    async with lock:
        scan_id = f"analyze_{ticker}_{datetime.utcnow().strftime('%H%M%S')}"

        try:
            mres = market_data_mod.fetch_ticker(ticker, config)
        except Exception as exc:
            log.warning("FETCH_ERROR in !analyze %s: %s", ticker, exc)
            return {"status": "error", "ticker": ticker, "error": str(exc), "final_tier": "WAIT"}

        if mres["data_status"] != "OK":
            return {
                "status": "data_failure",
                "ticker": ticker,
                "data_status": mres["data_status"],
                "final_tier": "WAIT",
            }

        try:
            enriched = indicators.enrich(ticker, mres["df"], config)
            enriched["data_status"] = "OK"
            enriched["latest_close"] = mres["latest_close"]
        except Exception as exc:
            log.warning("ENRICH_ERROR in !analyze %s: %s", ticker, exc)
            return {"status": "error", "ticker": ticker, "error": str(exc), "final_tier": "WAIT"}

        # Manual analysis bypasses only admission. Veto evidence is preserved
        # and still passed to deterministic tiering.
        pf_res = prefilter_mod.score_ticker(enriched, config)

        if client is None:
            return {
                "status": "error",
                "ticker": ticker,
                "error": "ANTHROPIC_KEY not configured",
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
                "status": "claude_error",
                "ticker": ticker,
                "error_type": cr.get("error_type"),
                "error_message": cr.get("error_message"),
                "final_tier": "WAIT",
            }

        tiering_result = tiering.validate(cr["signal"], pf_res, config)
        state = state_store.load(config)
        ticker_states = state.get("tickers", {}) if isinstance(state, dict) else {}
        previous_state = ticker_states.get(ticker) if isinstance(ticker_states, dict) else None

        tiering_result = _complete_candidate_judgment(
            ticker,
            tiering_result,
            enriched,
            mres,
            config,
            previous_state,
        )
        final_tier = tiering_result.get("final_tier", "WAIT")

        dedup_decision = state_store.check_alert(
            tiering_result, state, config, manual_override=True
        )
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
            "status": "complete",
            "scan_id": scan_id,
            "ticker": ticker,
            "final_tier": final_tier,
            "safe_for_alert": tiering_result.get("safe_for_alert"),
            "dedup_reason": dedup_decision.get("reason"),
            "alert_sent": send_result.get("sent", False),
            "channel_id": send_result.get("channel_id"),
            "tiering_result": tiering_result,
        }

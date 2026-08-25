from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"STOP: {label} anchor not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1. Correct the new ledger schema against actual production organ schemas.
# ---------------------------------------------------------------------------
p = Path("src/signal_outcome_ledger.py")
src = p.read_text(encoding="utf-8")

old = '''def _event_id(
    scan_id: str,
    ticker: str,
    final_tier: str,
    dedup_key: str | None,
    origin: str,
) -> str:
    basis = "|".join(
        [VERSION, scan_id, ticker.upper(), final_tier, dedup_key or "", origin]
    )
'''
new = '''def _event_id(
    scan_id: str,
    ticker: str,
    final_tier: str,
    dedup_key: str | None,
    origin: str,
    scan_started_at: str,
) -> str:
    # scan_started_at is part of identity because manual !analyze scan IDs
    # historically contain only HHMMSS and may repeat on another date.
    basis = "|".join(
        [
            VERSION,
            scan_id,
            ticker.upper(),
            final_tier,
            dedup_key or "",
            origin,
            scan_started_at,
        ]
    )
'''
src = replace_once(src, old, new, "_event_id")
src = replace_once(
    src,
    "_event_id(scan_id, ticker, final_tier, dedup_key, origin)",
    "_event_id(scan_id, ticker, final_tier, dedup_key, origin, scan_started_at)",
    "_event_id call",
)

start = src.index("def _four_hour_projection(")
end = src.index("\ndef _ladder_projection(", start)
four_hour = '''def _four_hour_projection(tiering_result: dict) -> dict | None:
    """Project the actual R4H-1 schema without inventing proxy-shaped keys."""
    four = tiering_result.get("four_hour_operational")
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
        "retest_truth": _json_safe(four.get("retest_truth")),
        "hold_truth": _json_safe(four.get("hold_truth")),
        "invalidation_quality": _json_safe(four.get("invalidation_quality")),
        "target_path": _json_safe(four.get("target_path")),
        "daily_relationship": _text(four.get("daily_relationship")),
        "hard_failures": _string_list(four.get("hard_failures")),
        "soft_warnings": _string_list(four.get("soft_warnings")),
        "missing_proofs": _string_list(four.get("missing_proofs")),
        "proxy_comparison": _json_safe(four.get("proxy_comparison")),
    }

'''
src = src[:start] + four_hour + src[end + 1:]

start = src.index("def _ladder_projection(")
end = src.index("\ndef _audit_projection(", start)
ladder = '''def _ladder_projection(tiering_result: dict) -> dict | None:
    ladder = tiering_result.get("snipe_ladder")
    if not isinstance(ladder, dict):
        return None
    return _projection(
        ladder,
        (
            "internal_ladder_tier",
            "public_signal_tier",
            "existing_final_tier_recommendation",
            "capital_action_recommendation",
            "opportunity_lane",
            "starter_grade",
            "sniper_grade",
            "base_alive",
            "proof_state",
            "proof_failure",
            "structure_state",
            "location_state",
            "trigger_state",
            "candle_state",
            "risk_state",
            "hard_failures",
            "starter_blockers",
            "sniper_only_blockers",
            "soft_caps",
            "info_notes",
            "basket_reason",
            "why_this_ladder_tier",
            "why_not_higher",
            "why_not_lower",
            "next_promotion_proof",
            "failure_condition",
            "audit_tags",
            "snipe_capital_floor_violation",
        ),
    )

'''
src = src[:start] + ladder + src[end + 1:]

src = replace_once(
    src,
    '"chunks": _finite_number(send_result.get("chunks") or send_result.get("chunk_count")),',
    '"message_count": _finite_number(send_result.get("message_count") or send_result.get("chunks") or send_result.get("chunk_count")),',
    "delivery message count",
)
src = replace_once(
    src,
    '"why_this_tier": _text((ladder or {}).get("why_this_tier")),',
    '"why_this_tier": _text((ladder or {}).get("why_this_ladder_tier")),',
    "ladder why_this_ladder_tier",
)
src = replace_once(
    src,
    '"next_promotion_proof": _text((ladder or {}).get("next_promotion_proof")),',
    '"next_promotion_proof": _json_safe((ladder or {}).get("next_promotion_proof")),',
    "ladder next_promotion_proof",
)
p.write_text(src, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Activate a dedicated commercial storage jurisdiction.
# ---------------------------------------------------------------------------
p = Path("config/doctrine_config.yaml")
cfg = p.read_text(encoding="utf-8")
old = '''research_archive:
  enabled: true
  directory: ".state/research_archive"
  retention_days: 120
  max_daily_file_bytes: 10485760

state:
'''
new = '''research_archive:
  enabled: true
  directory: ".state/research_archive"
  retention_days: 120
  max_daily_file_bytes: 10485760

# Phase 92 commercial evidence store. Separate from operational dedup state
# and from the research archive. Records only successfully delivered Discord
# alerts and has zero strategy, tier, capital, routing, or outcome authority.
signal_outcomes:
  enabled: true
  directory: ".state/signal_outcomes"

state:
'''
cfg = replace_once(cfg, old, new, "config research_archive/state")
p.write_text(cfg, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Wire the ledger only after successful Discord delivery.
# ---------------------------------------------------------------------------
p = Path("src/scheduler.py")
sch = p.read_text(encoding="utf-8")
sch = replace_once(
    sch,
    "from src import scan_telemetry\nfrom src import score_calibration\n",
    "from src import scan_telemetry\nfrom src import signal_outcome_ledger\nfrom src import score_calibration\n",
    "scheduler import",
)

old = '''    return _attach_capacity_boundary(trace, capacity_boundary)


# ---------------------------------------------------------------------------
# Phase 14W — one shared post-tiering candidate judgment organ
# ---------------------------------------------------------------------------
'''
new = '''    return _attach_capacity_boundary(trace, capacity_boundary)


async def _record_published_event_isolated(
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
) -> dict:
    """Persist Phase-92 evidence without owning scanner judgment.

    This runs only after Discord reports a successful send. File I/O is moved
    off the event loop. Failure is observable but cannot change the signal,
    tier, capital permission, routing, dedup decision, or state continuity.
    """
    try:
        result = await asyncio.to_thread(
            signal_outcome_ledger.append_published_event,
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
        )
    except Exception as exc:  # pragma: no cover - defensive isolation boundary
        log.critical("SIGNAL_OUTCOME_LEDGER_UNCAUGHT: %s: %s", ticker, exc)
        return {"ok": False, "status": "uncaught_error", "error": str(exc)}

    if not isinstance(result, dict) or result.get("ok") is not True:
        log.critical(
            "SIGNAL_OUTCOME_LEDGER_DEGRADED: ticker=%s scan_id=%s status=%s error=%s",
            ticker,
            scan_id,
            result.get("status") if isinstance(result, dict) else "invalid_result",
            result.get("error") if isinstance(result, dict) else "",
        )
    return result if isinstance(result, dict) else {"ok": False, "status": "invalid_result"}


# ---------------------------------------------------------------------------
# Phase 14W — one shared post-tiering candidate judgment organ
# ---------------------------------------------------------------------------
'''
sch = replace_once(sch, old, new, "scheduler Phase 14W helper insertion")

old = '''        if send_result.get("sent"):
            alerts_sent += 1
            try:
                state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            except Exception as exc:
                log.critical("CRITICAL: state record failed: %s: %s", ticker, exc)
'''
new = '''        if send_result.get("sent"):
            alerts_sent += 1
            await _record_published_event_isolated(
                ticker=ticker,
                tiering_result=tiering_result,
                dedup_decision=dedup_decision,
                send_result=send_result,
                config=config,
                scan_id=scan_id,
                scan_started_at=started_at,
                system_prompt=system_prompt,
                origin=(
                    signal_outcome_ledger.ORIGIN_MANUAL_SCAN
                    if is_manual
                    else signal_outcome_ledger.ORIGIN_SCHEDULED_SCAN
                ),
                tickers=tickers,
            )
            try:
                state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            except Exception as exc:
                log.critical("CRITICAL: state record failed: %s: %s", ticker, exc)
'''
sch = replace_once(sch, old, new, "autoscan successful delivery")

old = '''    async with lock:
        scan_id = f"analyze_{ticker}_{datetime.utcnow().strftime('%H%M%S')}"
'''
new = '''    async with lock:
        started_at = datetime.utcnow().isoformat()
        scan_id = f"analyze_{ticker}_{datetime.utcnow().strftime('%H%M%S')}"
'''
sch = replace_once(sch, old, new, "manual analyze timestamp")

old = '''        if send_result.get("sent"):
            state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            try:
                state_store.save(state, config)
            except Exception as exc:
                log.critical("CRITICAL: state write failed after !analyze: %s", exc)
'''
new = '''        if send_result.get("sent"):
            await _record_published_event_isolated(
                ticker=ticker,
                tiering_result=tiering_result,
                dedup_decision=dedup_decision,
                send_result=send_result,
                config=config,
                scan_id=scan_id,
                scan_started_at=started_at,
                system_prompt=system_prompt,
                origin=signal_outcome_ledger.ORIGIN_MANUAL_ANALYZE,
                tickers=None,
            )
            state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            try:
                state_store.save(state, config)
            except Exception as exc:
                log.critical("CRITICAL: state write failed after !analyze: %s", exc)
'''
sch = replace_once(sch, old, new, "manual analyze successful delivery")
p.write_text(sch, encoding="utf-8")

print("Phase 92-1A surgical patch applied")

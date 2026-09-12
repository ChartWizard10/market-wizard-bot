from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"STOP: {label} anchor not found")
    return text.replace(old, new, 1)


# Config: dedicated commercial evidence jurisdiction, no research retention.
p = Path("config/doctrine_config.yaml")
text = p.read_text(encoding="utf-8")
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
# and from the bounded research archive. Only successfully delivered Discord
# alerts become published events; measurement has zero strategy authority.
signal_outcomes:
  enabled: true
  directory: ".state/signal_outcomes"

state:
'''
text = replace_once(text, old, new, "config signal_outcomes")
p.write_text(text, encoding="utf-8")


# Scheduler: isolated writer only after successful Discord delivery.
p = Path("src/scheduler.py")
text = p.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from src import scan_telemetry\nfrom src import score_calibration\n",
    "from src import scan_telemetry\nfrom src import signal_outcome_ledger\nfrom src import score_calibration\n",
    "scheduler import",
)

anchor = '''    return _attach_capacity_boundary(trace, capacity_boundary)


# ---------------------------------------------------------------------------
# Phase 14W — one shared post-tiering candidate judgment organ
# ---------------------------------------------------------------------------
'''
insert = '''    return _attach_capacity_boundary(trace, capacity_boundary)


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
    """Persist commercial evidence without owning scanner judgment.

    This is called only after Discord reports a successful delivery. File I/O
    runs off the event loop. A measurement fault is logged but cannot alter the
    signal, tier, capital, routing, dedup decision, alert send, or state path.
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
    except Exception as exc:  # defensive isolation boundary
        log.critical("SIGNAL_OUTCOME_LEDGER_UNCAUGHT: %s: %s", ticker, exc)
        return {"ok": False, "status": "uncaught_error", "error": type(exc).__name__}
    if not isinstance(result, dict) or result.get("ok") is not True:
        log.critical(
            "SIGNAL_OUTCOME_LEDGER_DEGRADED: ticker=%s scan_id=%s status=%s",
            ticker,
            scan_id,
            result.get("status") if isinstance(result, dict) else "invalid_result",
        )
    return result if isinstance(result, dict) else {"ok": False, "status": "invalid_result"}


# ---------------------------------------------------------------------------
# Phase 14W — one shared post-tiering candidate judgment organ
# ---------------------------------------------------------------------------
'''
text = replace_once(text, anchor, insert, "ledger helper")

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
text = replace_once(text, old, new, "scan successful delivery hook")

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
                scan_started_at=scan_timestamp_utc,
                system_prompt=system_prompt,
                origin=signal_outcome_ledger.ORIGIN_MANUAL_ANALYZE,
                tickers=[ticker],
            )
            state_store.record_alert(ticker, tiering_result, state, config, scan_id)
            try:
                state_store.save(state, config)
            except Exception as exc:
                log.critical("CRITICAL: state write failed after !analyze: %s", exc)
'''
text = replace_once(text, old, new, "manual analyze successful delivery hook")
p.write_text(text, encoding="utf-8")

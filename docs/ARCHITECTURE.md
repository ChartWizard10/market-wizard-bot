# Production Architecture

This document describes the current production control flow. It is descriptive of code authority, not a substitute for tests.

## Runtime entry

`main.py` is the production application entry point. It:

- loads `config/doctrine_config.yaml`;
- validates required runtime environment;
- builds the Discord bot and Anthropic client;
- loads `prompts/market_wizard_system.md`;
- registers operator commands;
- launches the 15-minute autoscan loop.

## End-to-end scan pipeline

```text
config/tickers.txt
  -> market_data.load_tickers
  -> market_data.batch_download (Daily)
  -> indicators.enrich
  -> prefilter.prefilter
       score + veto + rank + top-30 deep-analysis cap
  -> claude_client.async_claude_scan
  -> tiering.validate
       deterministic base tier / routing / capital contract
  -> scheduler._complete_candidate_judgment
       trajectory
       trade_location
       candle_evidence
       market_data.fetch_one_hour_bars
       one_hour_entry
       timeframe_alignment (current production operational proxy)
       four_hour_operational (real-4H shadow evidence)
       higher_timeframe_context
       snipe_gate_audit
       snipe_ladder_judgment
       snipe_confirmed_seal
       final SNIPE audit reconciliation
       score_calibration
  -> final executable tier
  -> state_store.check_alert
       cooldown / tier-improvement / material-change decision
  -> discord_alerts.send_alert
  -> state_store.record_alert
  -> state_store.save
  -> scan_telemetry.write_scan_telemetry (observational side ledger)
```

## Sovereignty map

### Market-data truth

`src/market_data.py`

Owns ticker loading, Daily fetch/validation, Daily closed-vs-live partitioning, 1H fetch/bar truth, and the session-aligned real-4H aggregation envelope.

### Daily feature compiler

`src/indicators.py`

Owns structure-first Daily features: SMA/value, ATR, swings/liquidity, sweep, BOS/MSS/reclaim, FVG, OB/demand, retest proximity, overhead path, targets, invalidation, R:R, volume behavior, and live-vs-closed Daily evidence separation.

### Universe admission

`src/prefilter.py`

Owns broad-universe algorithmic score, pre-Claude vetoes, ranking, and candidate-cap admission. It is not the final trade grader.

### Model boundary

`src/claude_client.py` + `prompts/market_wizard_system.md`

Own structured prompt payload, model routing, pacing/rate governance, strict JSON validation, and initial model classification. The model cannot bypass deterministic execution law.

### Deterministic base tier

`src/tiering.py`

Owns tier contract, capital mapping, routing correction, semantic price sanity, score/risk gates, and hard-veto interpretation before the shared post-tiering judgment stack.

### Shared post-tiering judgment

`src/scheduler.py::_complete_candidate_judgment`

This is the single post-tiering production organ used by autoscan and manual `!analyze`.

Manual inspection may bypass universe admission and cooldown; it may not bypass chart judgment.

### Entry-trigger evidence

`src/one_hour_entry.py`

1H trigger proof. It cannot create a higher-timeframe thesis.

### Multi-timeframe alignment

`src/timeframe_alignment.py`

Current production alignment object. Its operational 4H state remains the production-authoritative proxy until an explicit R4H-2 promotion is validated.

### Real 4H evidence

`src/four_hour_operational.py`

Real session-aligned 4H structure/location evidence derived from the same 60m response used by 1H. Current mode is shadow/evidence-only. It must not silently become capital authority.

### Higher-timeframe context

`src/higher_timeframe_context.py`

Weekly/monthly structural memory resampled from existing Daily bars. Current config sets `influence_tiering: false`.

### SNIPE audit and ladder

`src/snipe_gate_audit.py`

Explains gate truth and final-state reconciliation.

`src/snipe_ladder_judgment.py`

Grades internal opportunity readiness across the SNIPE ladder and applies only explicitly allowed arbitration.

`src/snipe_confirmed_seal.py`

Downgrade-only consistency seal. It may block false SNIPE authorization. It never promotes.

### Execution governance

`src/state_store.py`

Owns cooldown/dedup/tier-improvement state after final chart judgment.

`src/discord_alerts.py`

Routes exclusively from final tier. WAIT never posts. Environment channel IDs may override config channel IDs.

### Observability

`src/scan_telemetry.py`

Scan-funnel telemetry/decision traces only. Its file is isolated from alert history and it has zero strategy authority.

## Current fixed production constants

From `config/doctrine_config.yaml`:

- scan cadence: 15 minutes;
- market window: 09:35–15:55 America/New_York, weekdays;
- Daily lookback: 18 months;
- Daily minimum bars: 120;
- data batch size: 100;
- deep-analysis candidate cap: 30;
- prefilter minimum score: 55;
- SNIPE_IT minimum score: 85;
- STARTER minimum score: 75;
- NEAR_ENTRY minimum score: 60;
- SNIPE/STARTER R:R floor: 3.0 where computable;
- fragile SNIPE risk-distance floor: 0.35%;
- state cooldown: 60 minutes;
- disabled indicators: RSI, MACD, Bollinger Bands, Stochastic.

A change to these constants is a strategy phase, not a universe-update side effect.

## Known architecture gap entering the next doctrine-compiler phase

The current broad prefilter and base JSON `setup_family` vocabulary remain generic. They do not yet contain deterministic production identifiers for all four locked setup families:

- `BREAK_RETEST_CONTINUATION`
- `VCP_BREAK_RETEST`
- `SMA_CRADLE_CONTINUATION`
- `GAP_FILL_REVERSAL`

This is a production gap because VCP, dynamic-support cradle, and gap-fill lifecycle candidates can exist without the exact FVG/OB + classic structure combination the legacy prefilter expects. The setup-family compiler must be added explicitly, tests-first, before universe expansion is treated as final production completion.
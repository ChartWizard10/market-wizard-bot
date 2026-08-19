# Production Changelog

This is a durable high-level ledger. Git history remains the detailed source.

## 2026-08-19 — Phase P0 Production Governance

- Replaced stale README-as-old-bot-code with current production documentation.
- Added scanner constitution, architecture map, production-state ledger, universe-management contract, runbook and durable changelog.
- Recorded the locked four-family production design and explicitly identified the current setup-family compiler gap before final universe expansion.
- No strategy, scoring, tier, routing, cadence, data-provider, universe or runtime behavior change.

## 2026-08-19 — Phase 14W Manual Analyze Judgment Parity

Main baseline entering P0: `bf476711af8ff486b88a7a91c6a22941bb9d2d1e`.

- Extracted one shared post-tiering candidate judgment organ.
- Autoscan and `!analyze` now consume the same evidence/arbitration stack.
- Manual analysis bypasses universe admission/cooldown only; chart judgment remains authoritative.
- Production CI: 2753 passed, 4 skipped.

## 2026-08-19 — Phase 14S.4B Final-Tier Dedup Reconciliation

Main commit: `93cfa7d7d71f150271357e3f135afa69fa3bdb9a`.

- Moved cooldown/dedup evaluation after all tier-mutating judgment organs.
- Prevented a stale preliminary STARTER suppression from burying an earned final SNIPE.
- Prevented a preliminary SNIPE permission from surviving a later seal downgrade.
- Preserved base-tier vs final-tier provenance in telemetry.

## 2026-08-19 — Phase CI-1 Production Test Gate

Main commit: `472de41a78c7befc0055e121783331ab702937e3`.

- Added GitHub Actions compile/full-pytest gate on pull requests and main pushes.
- Standardized CI to repository Python 3.13.13.
- Added Python 3.13 synchronous asyncio compatibility for legacy unit-test harnesses only.

## 2026-08-17 — Phase MR-1 Anthropic Model Routing Control

- Added runtime `ANTHROPIC_MODEL` override with config/default fallback.
- Kept model selection separate from scanner doctrine and gate logic.

## 2026-08-14 — Phase R4H-1 Real Four-Hour Operational Evidence

- Added real session-aligned 4H evidence aggregated from the same 60m provider response used by the 1H engine.
- Added closed/live/incomplete/ambiguous bucket truth, continuity handling, freshness and real-vs-proxy comparison.
- Kept real 4H in shadow/evidence-only authority mode.

## 2026-08-13 — Phase MBT-2 / MBT-2A Daily Market-Bar Truth

- Split developing Daily information from completed Daily confirmation evidence.
- Withheld ambiguous, duplicate, future and unparseable rows from confirmation authority.
- Preserved current-price location while protecting SMA/ATR/structure/zone/volume confirmation from live-bar contamination.

## Earlier Phase 14 / Phase 13 work

The repository includes prior hardened modules for:

- signal trajectory;
- score calibration;
- trade-location realism;
- candle evidence;
- 1H trigger evidence;
- multi-timeframe alignment;
- higher-timeframe context;
- SNIPE gate audit/history;
- under-promotion/shyness audits;
- unified SNIPE ladder;
- final consistency seal;
- alert/capital wording contracts;
- evidence persistence and scan telemetry.

Use Git history and focused test files for detailed phase-level behavior.
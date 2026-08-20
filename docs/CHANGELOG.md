# Production Changelog

This is a durable high-level ledger. Git history remains the detailed source.

## 2026-08-20 — Phase AI-2R Claude Opus 5 Provider Restoration

Superseded the earlier OpenAI provider migration. Anthropic is restored as the
sole production deep-analysis provider. Git history is unchanged; this entry
records that the migration no longer describes the current tree.

- Production provider: Anthropic. `main.py` constructs `anthropic.AsyncAnthropic`
  and passes it straight through the scheduler to `src/claude_client.py`, which
  calls `client.messages.create(...)` natively. No adapter, no cross-provider
  fallback — if Anthropic is unavailable the scanner fails closed.
- Production model: `claude-opus-5`. Routing remains
  `ANTHROPIC_MODEL` -> `config.claude.model` -> `DEFAULT_CLAUDE_MODEL`, with the
  repository fallback moved to Opus 5 so production stays on the intended model
  even when the Railway override is absent.
- Credentials: `ANTHROPIC_API_KEY`, with `ANTHROPIC_KEY` accepted as a
  compatibility alias for the historical Railway secret. An OpenAI credential
  has zero production effect.
- Removed: the OpenAI client startup, `src/model_client.py`,
  `src/openai_scheduler_compat.py`, the `model:` provider config block, the
  OpenAI direct dependency, the OpenAI `.env.example` contract, and the
  obsolete AI-1 acceptance/runtime documents.
- Emergency model rollback stays within Anthropic (e.g.
  `ANTHROPIC_MODEL=claude-sonnet-4-6`). Provider rollback to OpenAI is not a
  supported path.
- No strategy change. Prompt, parser/schema, market data, Daily/1H/4H truth,
  tiering, ladder, gates, seal, capital, routing, dedup/cooldown, telemetry,
  candidate cap (30), universe and 15-minute cadence are untouched. CAP-40A-E,
  R4H-1/-2/-3, VELOCITY, SFC/CFR and the research archive are all preserved.
- Restoring the provider says nothing about judgment quality; that is measured
  separately against the same evidence and prompt.

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
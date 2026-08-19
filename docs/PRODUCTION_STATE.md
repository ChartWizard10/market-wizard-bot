# Current Production State

Last baseline entering this governance phase: `main` at `bf476711af8ff486b88a7a91c6a22941bb9d2d1e` (Phase 14W — manual analyze judgment parity).

Update this file when a production phase changes architecture, authority, runtime contracts, or the next build priority.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Last Phase 14W gate result: 2753 passed, 4 skipped.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: SHADOW/EVIDENCE ONLY. Do not silently promote it.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- Claude runtime model override is supported through `ANTHROPIC_MODEL`; config fallback remains `claude-sonnet-4-6`.
- Scan-funnel telemetry is isolated from alert history and remains observational only.
- Production ticker loader normalizes uppercase symbols, ignores blanks/comments, deduplicates, validates format, and never fetches market data.

## Current production universe

Source: `config/tickers.txt`

Validated baseline count before the next requested universe expansion: 814 symbols.

The regression suite currently asserts:

- exactly 814 valid symbols;
- zero duplicates;
- zero malformed symbols;
- stable first/last boundaries;
- DRAM present exactly once in alphabetical position;
- IBM present exactly once in alphabetical position.

Any universe expansion must update the expected count/boundaries intentionally in the same reviewed change.

## Current alert contract

External verdicts:

- `SNIPE_IT` -> full-size authorization state;
- `STARTER` -> reduced-size capital only;
- `NEAR_ENTRY` -> watch/no capital;
- `WAIT` -> no trade/no Discord post.

Internal ladder:

`PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS`

`SNIPER_A` and `SNIPER_A_PLUS` are both SNIPE execution states; the ladder grade preserves the quality distinction. SNIPE_IT is not synonymous with a score of 100.

## Production objective

The scanner is a bullish swing-entry engine, not a scalper and not a pattern collector.

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural stop/invalidation. This is an evaluation target, never a guaranteed forecast.

## Locked setup families

Production design requires four explicit families:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

### Current implementation status

`BREAK_RETEST_CONTINUATION`: substantially represented by existing structure/reclaim, zone, retest, 1H, ladder and seal machinery, but not yet normalized under the final family identifier.

`VCP_BREAK_RETEST`: NOT yet represented by a dedicated deterministic family organ. Existing generic compression label is model-side only and broad-universe admission can miss pre-breakout VCPs.

`SMA_CRADLE_CONTINUATION`: doctrine exists in the source stack, but the repository does NOT yet have the dedicated production evidence organ/normalized family object required by the A+ scanner doctrine.

`GAP_FILL_REVERSAL`: doctrine exists in the source stack, but the repository does NOT yet have a dedicated gap-state/fill/reclaim evidence organ.

This is the primary strategy-build gap before the scanner is considered ready for the final requested universe expansion.

## Next production sequence

1. Setup Family Compiler contract/schema.
2. SMA Cradle evidence organ and explicit gate integration.
3. VCP evidence organ and admission/readiness integration.
4. Gap Fill Reversal evidence organ and admission/readiness integration.
5. Normalize Break/Retest family under the same family contract.
6. Cross-family contradiction resolver and tier contract tests.
7. Full CI and shadow/audit review.
8. Universe expansion as a dedicated final change.

## Things that must NOT drift during the family work

- candidate cap remains 30 unless a separate capacity study changes it;
- scan cadence remains 15 minutes;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains shadow until R4H-2 is explicitly proven;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership.

## Operational debt tracked but not blocking family compiler work

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- The old README is being replaced by production documentation in this governance phase.
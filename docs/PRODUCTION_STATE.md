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
- Scan-funnel telemetry is isolated from alert history and remains observational only.
- Production ticker loader normalizes uppercase symbols, ignores blanks/comments, deduplicates, validates format, and never fetches market data.

## Model-provider correction — active P0 finding

Operator intent is OpenAI GPT-5.6.

Current production `main` is NOT yet aligned with that intent:

- `main.py` still instantiates `anthropic.AsyncAnthropic`;
- `requirements.txt` still installs `anthropic`;
- `src/scheduler.py` still imports the legacy `claude_client` API;
- `config/doctrine_config.yaml`, telemetry names, tests, README/runbook history and environment naming still contain Claude/Anthropic terminology.

This is now an explicit production issue to repair. Documentation must not pretend GPT-5.6 is already the deployed model before the runtime migration is merged and Railway is updated.

Target runtime:

- OpenAI API;
- GPT-5.6 model family;
- preferred flagship alias: `gpt-5.6` / GPT-5.6 Sol;
- Structured Outputs / strict JSON-schema contract;
- deterministic tiering remains sovereign over capital/routing.

No provider migration may silently modify scanner doctrine, thresholds, candidate admission, cadence, universe, routing, or capital contracts.

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

`SMA_CRADLE_CONTINUATION`: doctrine exists in the source stack, but the repository does NOT yet have the dedicated production evidence organ/normalized family object required by the scanner doctrine.

`GAP_FILL_REVERSAL`: doctrine exists in the source stack, but the repository does NOT yet have a dedicated gap-state/fill/reclaim evidence organ.

This is the primary strategy-build gap before the scanner is considered ready for the final requested universe expansion.

## Candidate-cap decision

Current production cap: 30 deep-analysis candidates per scan.

Operator preference: consider 40.

Engineering decision: do NOT raise blindly during P0. A move from 30 to 40 is a 33.3% increase in maximum model calls per scan. The repository already observes ranks 31-60 in near-cut telemetry without paying for deep analysis, so the next cap decision can be evidence-based.

Preferred sequence:

1. migrate the runtime to GPT-5.6;
2. complete the setup-family compiler so candidate ranking reflects the actual doctrine;
3. replay/inspect ranks 31-40;
4. verify incremental STARTER/SNIPE capture;
5. verify worst-case scan latency and API cost/rate budget remain comfortably inside the 15-minute cadence;
6. raise to 40 if the incremental recall is real.

40 is technically plausible and is the preferred next ceiling if those tests pass. Candidate-cap expansion must not be used to mask a weak prefilter.

## Next production sequence

1. P0 governance reconciliation and merge.
2. AI-1: OpenAI GPT-5.6 runtime migration with structured-output parity and no doctrine drift.
3. Setup Family Compiler contract/schema.
4. SMA Cradle evidence organ and explicit gate integration.
5. VCP evidence organ and admission/readiness integration.
6. Gap Fill Reversal evidence organ and admission/readiness integration.
7. Normalize Break/Retest family under the same family contract.
8. Cross-family contradiction resolver and tier contract tests.
9. R4H-2 evidence-based real-4H authority decision.
10. Five-session/+8% feasibility research layer.
11. CAP-40 measured 30-vs-40 capacity evaluation.
12. Universe expansion as a dedicated final change.
13. Chronological replay / out-of-sample validation and Railway observation.

## Things that must NOT drift during the next phases

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains shadow until R4H-2 is explicitly proven;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- no provider migration may alter trading doctrine as a side effect.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask the operator for the ticker list.
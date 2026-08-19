# Current Production State

Last merged production baseline entering AI-1: `main` at `6e251a933835e1e24e2dcb2c02ddeea539453521` (Phase SFC-1 — deterministic setup family compiler).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: SHADOW/EVIDENCE ONLY. Do not silently promote it.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- Phase SFC-1 compiles normalized completed-Daily evidence for all four locked setup families without changing tier/capital/admission authority.
- Scan-funnel telemetry is isolated from alert history and remains observational only.
- Production ticker loader normalizes uppercase symbols, ignores blanks/comments, deduplicates, validates format, and never fetches market data.

## AI-1 provider correction

Operator intent and governing production target: **OpenAI GPT-5.6**.

AI-1 is migrating the actual deep-analysis runtime away from Anthropic while preserving the hardened scanner judgment architecture.

Target runtime contract:

- `OPENAI_API_KEY` authenticates the model client;
- `OPENAI_MODEL` may override the configured model;
- canonical model: `gpt-5.6`;
- OpenAI Responses API;
- strict Structured Outputs / JSON Schema at the model boundary;
- response storage disabled (`store=False`);
- GPT-5.6 remains analyst/classifier only; deterministic tiering, ladder, seal, capital and routing remain sovereign.

During AI-1, some internal scheduler/telemetry field names still contain historical `claude_*` terminology for regression compatibility. Those names do **not** mean Anthropic is the production provider. Provider-neutral nomenclature can be migrated separately after the runtime cutover is green.

## Current production universe

Source: `config/tickers.txt`

Validated baseline before the next requested expansion: **814 unique symbols**.

The regression suite asserts:

- exactly 814 valid symbols;
- zero duplicates;
- zero malformed symbols;
- stable first/last boundaries;
- DRAM present exactly once in alphabetical position;
- IBM present exactly once in alphabetical position.

Any universe expansion must update expected count/boundaries intentionally in the same reviewed change.

## Current alert contract

External verdicts:

- `SNIPE_IT` -> execution-authorized/full-size eligibility state;
- `STARTER` -> reduced-size capital only;
- `NEAR_ENTRY` -> watch/no capital;
- `WAIT` -> no trade/no Discord post.

Internal ladder:

`PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS`

`SNIPER_A` and `SNIPER_A_PLUS` are both SNIPE execution states; the ladder grade preserves quality distinction. SNIPE_IT is not synonymous with a score of 100.

## Production objective

The scanner is a bullish swing-entry engine, not a scalper and not a pattern collector.

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural stop/invalidation. This is an evaluation target, never a guaranteed forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

### Current implementation status

Phase SFC-1 now provides a normalized deterministic evidence compiler for all four families from completed Daily evidence.

That compiler is intentionally evidence-only. The next setup-family phase must integrate family evidence into broad-universe admission/readiness without allowing a family label to bypass the common execution laws: accepted structure, defensible location, invalidation, path, retest/hold requirements appropriate to the entry class, and final capital gates.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan** during AI-1.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 if measured evidence proves it adds recall without damaging cadence/cost**.

A move from 30 to 40 is a 33.3% increase in maximum model calls. The scanner already records near-cut ranks 31-60 without paying for deep analysis, so the decision can be measured rather than guessed.

CAP-40 acceptance sequence:

1. finish GPT-5.6 runtime migration;
2. integrate the setup-family compiler into candidate admission/readiness;
3. replay/inspect ranks 31-40 for legitimate missed STARTER/SNIPE opportunities;
4. verify worst-case scan duration remains comfortably inside the 15-minute cadence;
5. verify API rate/cost budget is acceptable;
6. raise to 40 only if incremental opportunity capture is real.

Do not use a larger model-call cap to compensate for weak prefilter logic.

## Next production sequence

1. Complete AI-1 GPT-5.6 runtime migration and full CI.
2. SFC-2: integrate normalized setup-family evidence into admission/readiness without bypassing common gates.
3. Cross-family contradiction resolver and tier contract tests.
4. R4H-2: evidence-based decision on promoting real 4H from shadow to production authority.
5. VELOCITY-1: five-session/+8% feasibility layer and three-barrier validation labels.
6. CAP-40: measured 30-vs-40 capacity study and, if proven, controlled cap increase.
7. Final requested universe expansion in its own reviewed PR.
8. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains shadow until R4H-2 is explicitly proven;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- model-provider migration may not change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names after AI-1 without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.

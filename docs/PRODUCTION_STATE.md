# Current Production State

Last merged production baseline entering SFC-2A: `main` at `99d98080dfa5452df00cf8794ef0741c1d7aa1d2` (Phase AI-1 — OpenAI GPT-5.6 production runtime, built on Phase SFC-1).

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

## AI-1 provider correction — merged

Production deep analysis is **OpenAI GPT-5.6**, not Claude.

Runtime contract:

- `OPENAI_API_KEY` authenticates the model client;
- `OPENAI_MODEL` may override the configured model;
- canonical model: `gpt-5.6`;
- OpenAI Responses API;
- strict Structured Outputs / JSON Schema at the model boundary;
- response storage disabled (`store=False`);
- GPT-5.6 remains analyst/classifier only; deterministic tiering, ladder, seal, capital and routing remain sovereign.

Some internal scheduler/telemetry field names still contain historical `claude_*` terminology for regression compatibility. Those names do **not** mean Anthropic is the production provider. Provider-neutral nomenclature is tracked as operational debt and must be migrated separately without strategy drift.

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

### SFC-1 — compiler status

SFC-1 provides a normalized deterministic evidence compiler for all four families from completed Daily evidence.

The compiler remains evidence-first. A family label is never capital authority.

### SFC-2A — admission arbitration contract

SFC-2A defines, as a pure side-effect-free module, how strong family evidence may repair **generic prefilter/model-admission blind spots** without bypassing common fatal gates.

Key laws:

- bad/empty/insufficient/stale data is never rescued;
- blocked overhead is never rescued;
- excessive extension is never rescued;
- failed retest is never rescued;
- hostile value alignment is never rescued;
- generic no-structure/mid-range blockers may be superseded for model admission when a normalized family is admission-ready;
- missing generic invalidation/target/R:R can be superseded only when the family compiler provides explicit valid equivalents;
- `watch_ready` alone is not enough to open the family lane;
- family rank influence never overwrites the legacy prefilter score and is bounded;
- the family-admission object contains no tier, capital or Discord authority.

SFC-2A itself does not yet change production candidate selection. SFC-2B is the controlled wiring phase after the SFC-2A contract is green.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 if measured evidence proves it adds recall without damaging cadence/cost**.

A move from 30 to 40 is a 33.3% increase in maximum model calls. The scanner already records near-cut ranks 31-60 without paying for deep analysis, so the decision can be measured rather than guessed.

CAP-40 acceptance sequence:

1. keep GPT-5.6 runtime green;
2. complete SFC-2 family admission/readiness integration;
3. replay/inspect ranks 31-40 for legitimate missed STARTER/SNIPE opportunities;
4. verify worst-case scan duration remains comfortably inside the 15-minute cadence;
5. verify API rate/cost budget is acceptable;
6. raise to 40 only if incremental opportunity capture is real.

Do not use a larger model-call cap to compensate for weak candidate ranking.

## Next production sequence

1. SFC-2A: green the pure family-admission arbitration contract.
2. SFC-2B: wire normalized family evidence into prefilter/model admission and GPT-5.6 prompt context while preserving common gates and the 30-candidate cap.
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
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
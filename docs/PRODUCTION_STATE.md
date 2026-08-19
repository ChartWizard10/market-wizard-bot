# Current Production State

Last merged production baseline entering R4H-3B: `main` at `4c26f28ca500471ea0d8a182cf41c40e27272da6` (Phase R4H-3A — 4H location-layer counterfactual policy contract, on top of VELOCITY-1D outcome linkage, VELOCITY-1C telemetry wiring, R4H-2 HOLD SHADOW, CFR-2 family resolution, SFC-2B family-aware GPT-5.6 admission, and the existing deterministic execution stack).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth enforces completed-vs-developing evidence.
- 1H market-bar truth explicitly separates closed and live evidence.
- Real 4H bars are session-aligned and reuse the existing 60m provider response.
- Real 4H authority remains **SHADOW_EVIDENCE_ONLY**.
- Higher-timeframe monthly/weekly context remains evidence-only.
- SNIPE gate audit, unified ladder, downgrade-only seal, final-state reconciliation and calibration remain production-authoritative.
- Autoscan and manual `!analyze` share the same post-tiering judgment organ.
- SFC-1/SFC-2A/SFC-2B and CFR-1/CFR-2 are production-green.
- VELOCITY-1A/1B/1C/1D are production-green research infrastructure.
- R4H-3A is production-green research infrastructure.
- Scan telemetry remains observational and isolated from alert history.
- Production ticker loader normalizes/deduplicates/validates symbols without fetching market data.

## Production model provider

Production deep analysis is **OpenAI GPT-5.6** through the Responses API with Structured Outputs and `store=False`.

`OPENAI_API_KEY` authenticates the client and `OPENAI_MODEL` may override the configured model. GPT-5.6 remains analyst/classifier only; deterministic tiering, ladder, seals, capital and routing remain sovereign.

Historical internal `claude_*` field names remain compatibility debt only and do not indicate the production provider.

## Current production universe

Source: `config/tickers.txt`

Validated baseline: **814 unique symbols**. Regression coverage asserts the expected count, valid formatting, no duplicates, stable boundaries, and specific DRAM/IBM membership.

Any universe expansion must occur in its own reviewed change and update the expected universe contract intentionally.

## Current alert contract

External verdicts:

- `SNIPE_IT` -> execution-authorized/full-size eligibility state;
- `STARTER` -> reduced-size capital only;
- `NEAR_ENTRY` -> watch/no capital;
- `WAIT` -> no trade/no Discord post.

Internal ladder:

`PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS`

A SNIPE does not need a score of 100. STARTER and NEAR_ENTRY remain legitimate distinct readiness states.

## Production objective

The scanner is a bullish swing-entry engine, not a scalper and not a pattern collector.

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural invalidation. This remains an evaluation target, never a promised forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

Family labels may improve model admission/ranking only within the reviewed SFC rules. They never bypass fatal common gates or create capital permission by themselves. Cross-family confluence never stacks scores; execution proof remains primary.

## R4H — real 4H authority program

### R4H-1 — real 4H evidence engine

Real 4H evidence represents closed/live truth, continuity gaps, stale evidence, structural state, liquidity, displacement, retest, hold, invalidation and target path from actual session-aligned candles.

R4H-1 remains shadow evidence. Its research constants are not production doctrine by themselves.

### R4H-2 — authority decision

**Verdict: HOLD SHADOW.**

Before any real-4H authority handoff, a reviewed evidence package must establish:

1. chronological out-of-sample validation;
2. forward outcome linkage;
3. proxy-vs-real counterfactual evaluation;
4. sample size accepted under a predeclared plan;
5. accepted market-condition coverage;
6. precision improved or preserved;
7. legitimate opportunity recall not materially damaged;
8. full capital-integrity regressions green.

R4H-2 never auto-promotes. Even a fully green evidence package can only make a later controlled handoff eligible for review.

### R4H-3A — merged

R4H-3A defines a pure location-layer counterfactual contract and intentionally refuses to pretend it can replay the whole ladder from compact telemetry.

Common location-effect vocabulary:

- `SUPPORTIVE`
- `REPAIRING`
- `NO_EDGE`
- `EXTENDED`
- `HARD_BLOCK`
- `UNAVAILABLE`

Comparison classes:

- `SAME_LOCATION_EFFECT`
- `REAL_ADDS_HARD_BLOCK`
- `REAL_REMOVES_PROXY_HARD_BLOCK`
- `NON_FATAL_LOCATION_DIFFERENCE`
- `COMPARISON_UNAVAILABLE`

R4H-3A joins these comparisons to VELOCITY-1D outcome rows by `(scan_id, ticker)`. It can measure the local 4H hard-failure disagreement but cannot reconstruct a final STARTER/SNIPE tier. Real 4H remains shadow.

R4H-3A merged with permanent Python 3.13 CI at **2911 passed, 4 skipped**.

### R4H-3B — current branch phase

R4H-3B makes the R4H-3A/VELOCITY evidence statistically executable under a **predeclared** research plan without changing live authority.

Outcome law:

- `TARGET_FIRST`, `INVALIDATION_FIRST`, `TIME_BARRIER` are evaluable terminal outcomes for the five-session/+8% objective;
- `AMBIGUOUS_SAME_SESSION` is ambiguous;
- `INCOMPLETE_HORIZON` is censored;
- `INVALID_DATA` is invalid;
- ambiguous/censored/invalid rows never become fabricated wins or losses.

The plan must explicitly declare and freeze sample/completeness thresholds before outcome review. No numeric trading/sample threshold is invented by the engine after seeing results.

R4H-3B reports:

- objective-failure protection versus target opportunity cost when real 4H adds a hard block;
- target recovery versus objective-failure exposure when real 4H removes a proxy hard block;
- separate outcome distributions for real `SUPPORTIVE`, `REPAIRING`, `NO_EDGE`, `EXTENDED`, and `UNAVAILABLE` states;
- sample readiness against the predeclared plan;
- separately auditable market-condition coverage when supplied;
- optional predeclared effect-threshold evaluation.

Study decisions are research-only: `PLAN_INVALID`, `SAMPLE_INSUFFICIENT`, `DESCRIPTIVE_ONLY`, `NARROW_HARD_BLOCK_EVIDENCE_SUPPORTIVE`, or `NARROW_HARD_BLOCK_EVIDENCE_NOT_SUPPORTIVE`.

Even a supportive narrow result does not grant authority. Full-tier counterfactual and full 4H replacement remain explicitly unsupported in this phase.

## VELOCITY-1 — five-session / +8% research stack

### VELOCITY-1A — merged

Pure ex-ante feasibility and ex-post three-barrier research contract. CI at merge: **2853 passed, 4 skipped**.

### VELOCITY-1B — merged

Immutable scan-time observation envelope preserving geometry, observed tier/capital truth, setup-family attribution, real-4H/proxy context and feasibility without future leakage. CI: **2870 passed, 4 skipped**.

### VELOCITY-1C — merged

Bounded additive scan-telemetry projection below 1 KB, failure-isolated from the normal 14V trace, with zero live tier/capital/routing/suppression/forecast authority. CI: **2876 passed, 4 skipped**.

### VELOCITY-1D — merged

Offline chronological linker from scan-time observations to completed future Daily sessions. Observation-day bars are excluded; duplicate/conflicting data is handled explicitly; partial history remains incomplete rather than false timeout. Local-only CLI produces deterministic research datasets. CI: **2892 passed, 4 skipped**.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The preferred next ceiling is 40 only if measured evidence proves incremental opportunity recall without unacceptable cadence/cost impact. A move from 30 to 40 is a 33.3% increase in maximum model calls.

Near-cut telemetry records ranks 31-60, but full VELOCITY observations currently apply to analyzed candidates. CAP-40 therefore still needs its own measured replay/study rather than assuming ranks 31-40 are beneficial.

## Next production sequence

1. R4H-3B: complete and merge the predeclared chronological outcome-study engine/report generator.
2. Collect/run a real R4H-3B dataset under a frozen plan. If evidence is insufficient, remain shadow and keep collecting.
3. If evidence is strong enough, design a separately reviewed **narrow** R4H authority handoff scope before considering broader replacement.
4. CAP-40: measured 30-vs-40 capacity study; raise only if recall/cadence/cost evidence clears review.
5. Final requested universe expansion in its own reviewed PR.
6. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains `SHADOW_EVIDENCE_ONLY` until later reviewed evidence clears a narrowly scoped handoff;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- VELOCITY/R4H research evidence cannot promote, downgrade, route, suppress, size, or forecast a trade;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- cross-family confluence may not stack family scores;
- proxy agreement is not ground truth;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown or universe.

## Operational debt tracked but not blocking the current phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.

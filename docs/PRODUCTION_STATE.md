# Current Production State

Last merged production baseline entering R4H-3A: `main` at `2c521c8f4c24fc191ebf7a0f307b08bc0c751927` (Phase VELOCITY-1D — offline chronological observation-to-outcome linker, on top of VELOCITY-1C telemetry wiring, VELOCITY-1A/1B research contracts, R4H-2 HOLD SHADOW, CFR-2 family resolution, SFC-2B family-aware GPT-5.6 admission, and the existing deterministic execution stack).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: **SHADOW_EVIDENCE_ONLY**. R4H-2 explicitly holds this boundary pending outcome-linked chronological validation.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- SFC-1 compiles normalized completed-Daily evidence for all four locked setup families.
- SFC-2A defines the pure family-admission arbitration contract.
- SFC-2B wires family-aware model admission/ranking into production while preserving common gates and downstream tier authority.
- CFR-1 defines the pure cross-family resolution contract and tier non-interference tests.
- CFR-2 wires the cross-family resolver into the production family-evidence path and GPT-5.6 context without granting capital authority.
- VELOCITY-1A defines the pure ex-ante feasibility snapshot and ex-post five-session/+8% three-barrier label without granting live authority.
- VELOCITY-1B defines the immutable scan-time observation envelope and future-link input without granting live authority.
- VELOCITY-1C persists a bounded VELOCITY observation in analyzed decision traces with telemetry-only failure isolation.
- VELOCITY-1D links those observations offline to future completed Daily sessions and produces deterministic three-barrier research datasets.
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

The regression suite asserts exactly 814 valid symbols, zero duplicates, zero malformed symbols, stable first/last boundaries, DRAM exactly once in alphabetical position, and IBM exactly once in alphabetical position.

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

### SFC-1 / SFC-2A / SFC-2B

The setup-family stack is production-green.

- SFC-1 compiles completed-Daily evidence for all four locked families.
- SFC-2A defines family-aware model-admission arbitration without bypassing fatal common gates.
- SFC-2B wires family-aware admission/ranking into production while preserving legacy `prefilter_score`, original/rescued veto ledgers, common gates, and downstream deterministic tier authority.
- A family label never creates capital permission.
- Developing Daily contact remains provisional and cannot become family confirmation.

Never-rescued blockers include bad/stale data, blocked overhead, excessive extension, failed retest, and hostile value alignment.

### CFR-1 / CFR-2

Cross-family resolution is production-green.

Production evidence flow:

`completed Daily evidence -> raw SFC-1 compiler -> CFR-1 resolver -> SFC-2B admission / GPT-5.6 context -> existing deterministic execution stack`

Core laws:

- execution proof outranks a merely higher family score;
- confluence never stacks scores;
- a local sibling-family failure does not automatically cancel a valid distinct family;
- shared/common failure information remains visible for sovereign gates;
- raw SFC-1 family objects are not mutated;
- resolver metadata has no independent tier, capital, or Discord authority.

CFR-2 merged after the permanent Python 3.13 gate completed with **2831 passed, 4 skipped**.

## R4H — real 4H authority program

### R4H-1 — real 4H evidence engine

Real 4H market bars are session-aligned and reuse the existing 60m response. Closed/live confirmation law, continuity holes, incomplete constituents, stale evidence, structural state, location, retest, hold, invalidation and target path are represented explicitly.

R4H-1 remains shadow evidence. Its research thresholds are not production doctrine by themselves.

### R4H-2 — authority decision

**Verdict: HOLD SHADOW.**

R4H-2 established that implementation correctness and proxy agreement are insufficient for authority handoff. Before promotion review, the evidence package must establish:

1. chronological out-of-sample validation;
2. forward outcome linkage;
3. proxy-vs-real counterfactual evaluation;
4. sample size accepted under a predeclared plan;
5. accepted market-condition coverage;
6. precision improved or preserved;
7. legitimate opportunity recall not materially damaged;
8. full capital-integrity regressions green.

The R4H-2 audit never auto-promotes. Even a fully green evidence package may only become eligible for a separately reviewed controlled handoff.

### R4H-3A — current branch phase

R4H-3A defines the first outcome-study policy contract. It intentionally compares **only the 4H location layer**, because the compact historical trace does not contain enough decision-time inputs to replay the entire SNIPE ladder with the 4H source swapped.

Common location-effect vocabulary:

- `SUPPORTIVE`
- `REPAIRING`
- `NO_EDGE`
- `EXTENDED`
- `HARD_BLOCK`
- `UNAVAILABLE`

Production proxy mapping follows current ladder semantics: `LOCATION_HOSTILE` is the 4H hard-failure state; valid/repairing/extended remain distinct non-hostile conditions whose final capital result still depends on the rest of the stack.

Real-4H mapping uses existing R4H-1 states: defendable/ready is supportive, repair stays repair, mid-range is no-edge, extended stays extended, and closed structural failure/hostile location is a hard block. Stale/insufficient evidence is unavailable, not fabricated failure.

R4H-3A comparison classes:

- `SAME_LOCATION_EFFECT`
- `REAL_ADDS_HARD_BLOCK`
- `REAL_REMOVES_PROXY_HARD_BLOCK`
- `NON_FATAL_LOCATION_DIFFERENCE`
- `COMPARISON_UNAVAILABLE`

The phase can attach these comparisons to VELOCITY-1D outcome records by `(scan_id, ticker)` and count outcomes where real 4H would add or remove a 4H hard block. It does **not** claim that those cases reconstruct a final STARTER/SNIPE verdict.

Authority remains unchanged: `SHADOW_EVIDENCE_ONLY`.

## VELOCITY-1 — five-session / +8% research stack

### VELOCITY-1A — merged

Pure research contract:

- ex-ante feasibility snapshot from known structural path room and ATR-based range-capacity evidence;
- default objective approximately +8% inside five completed future trading sessions;
- outcome taxonomy `TARGET_FIRST`, `INVALIDATION_FIRST`, `AMBIGUOUS_SAME_SESSION`, `TIME_BARRIER`, `INCOMPLETE_HORIZON`, `INVALID_DATA`;
- same-session target/stop touches remain ambiguous on Daily OHLC;
- watch observations stay separate from capital-authorized observations.

CI at merge: **2853 passed, 4 skipped**.

### VELOCITY-1B — merged

Pure immutable observation-envelope contract. It preserves scan identity, original price/invalidation geometry, observed tier/capital truth, setup-family attribution, real-4H/proxy context and VELOCITY feasibility without future outcome leakage.

CI at merge: **2870 passed, 4 skipped**.

### VELOCITY-1C — merged

Bounded scan-telemetry wiring:

- normal 14V trace is built first;
- compact VELOCITY block is additive and regression-bounded below 1 KB;
- projection failure returns the original trace unchanged;
- no schema reset/quarantine is introduced;
- no future bars/outcomes enter scan-time telemetry;
- no tier/capital/routing/suppression/forecast authority.

CI at merge: **2876 passed, 4 skipped**.

### VELOCITY-1D — merged

Offline chronological outcome linker:

- observation-day Daily bar is strictly excluded from future sessions;
- future sessions are date-sorted and deduplicated;
- conflicting duplicate OHLC rows are invalidated rather than guessed through;
- partial future history stays `INCOMPLETE_HORIZON`, never false timeout;
- duplicate scan/ticker observations are deduplicated only when identical;
- output preserves tier/family/feasibility/real-4H/proxy attribution;
- local-only CLI builds deterministic research dataset JSON.

CI at merge: **2892 passed, 4 skipped**.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The preferred next ceiling is **40 only if measured evidence proves it adds recall without damaging cadence/cost**. A move from 30 to 40 is a 33.3% increase in maximum model calls.

Near-cut telemetry records ranks 31-60 without paying for deep analysis, but VELOCITY-1C full observations currently apply to analyzed candidates. Therefore VELOCITY-1D alone does not prove the ranks 31-40 counterfactual. CAP-40 still needs a dedicated measured replay/study plus scan-duration and API-cost/rate evidence.

## Next production sequence

1. R4H-3A: complete and merge pure location-layer counterfactual policy contract.
2. R4H-3B: predeclared chronological outcome-study plan and report generator; no live authority.
3. If evidence justifies it, design a separately reviewed controlled R4H handoff scope; otherwise keep shadow and continue collecting evidence.
4. CAP-40: measured 30-vs-40 capacity study and controlled cap increase only if proven.
5. Final requested universe expansion in its own reviewed PR.
6. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains `SHADOW_EVIDENCE_ONLY` until forward evidence explicitly clears a later authority handoff;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- VELOCITY/R4H research evidence cannot promote, downgrade, route, suppress, size, or forecast a trade unless a later reviewed phase explicitly grants a narrowly defined authority;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- cross-family confluence may not stack family scores;
- a resolver may not become a tier/capital/routing organ;
- proxy agreement is not ground truth and cannot by itself justify 4H authority;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
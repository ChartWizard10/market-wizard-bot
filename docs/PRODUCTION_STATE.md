# Current Production State

Last merged production baseline entering R4H-3C: `main` at `65abdcd762db94fe0323b7d262a850d54641cb32` (Phase R4H-3B — predeclared chronological 4H outcome study, on top of R4H-3A, VELOCITY-1D/1C, R4H-2 HOLD SHADOW, CFR-2 family resolution, SFC-2B family-aware GPT-5.6 admission, and the deterministic execution stack).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime: `.python-version` = 3.13.13.
- Permanent GitHub Actions gate: compile + full `pytest` on PRs/pushes to main.
- Daily completed-vs-developing evidence law remains enforced.
- 1H closed-vs-live evidence remains explicit.
- Real 4H bars are session-aligned and reuse the existing 60m provider response.
- Real 4H authority remains **SHADOW_EVIDENCE_ONLY**.
- Monthly/weekly context remains evidence-only where configured.
- SNIPE gate audit, unified ladder, downgrade-only seal, final-state reconciliation and calibration remain production-authoritative.
- Autoscan and manual `!analyze` share the same post-tiering judgment organ.
- SFC-1/SFC-2A/SFC-2B and CFR-1/CFR-2 are production-green.
- VELOCITY-1A/1B/1C/1D are production-green research infrastructure.
- R4H-3A/3B are production-green research infrastructure.
- Scan telemetry remains observational and isolated from alert history.
- Production ticker loader normalizes/deduplicates/validates symbols without fetching market data.

## Production model provider

Production deep analysis is **OpenAI GPT-5.6** through the Responses API with Structured Outputs and `store=False`.

`OPENAI_API_KEY` authenticates the client and `OPENAI_MODEL` may override the configured model. GPT-5.6 remains analyst/classifier only; deterministic tiering, ladder, seals, capital and routing remain sovereign.

Historical internal `claude_*` names remain compatibility debt only and do not indicate the production provider.

## Current production universe and cadence

Source: `config/tickers.txt`

- universe: **814 unique symbols**
- scan cadence: **15 minutes**
- deep-analysis candidate cap: **30**

Any universe or candidate-cap change must occur in its own reviewed phase with updated regression contracts.

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

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural invalidation. This is an evaluation target, never a promised forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

Family evidence may improve model admission/ranking only within reviewed SFC rules. It never bypasses fatal common gates or creates capital permission by itself. Cross-family confluence never stacks scores; execution proof remains primary.

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

R4H-2 never auto-promotes. A green evidence package can only make a later controlled handoff eligible for review.

### R4H-3A — merged

R4H-3A defines the pure location-layer counterfactual between the production proxy and real 4H shadow evidence.

Common effects:

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

It joins comparisons to VELOCITY-1D rows by `(scan_id, ticker)` but explicitly cannot reconstruct a final STARTER/SNIPE verdict from the compact trace.

Merge CI: **2911 passed, 4 skipped**.

### R4H-3B — merged

R4H-3B scores the location-layer counterfactual under an explicit predeclared chronological study plan.

Outcome law:

- `TARGET_FIRST`, `INVALIDATION_FIRST`, `TIME_BARRIER` are evaluable terminal outcomes;
- `AMBIGUOUS_SAME_SESSION` is ambiguous;
- `INCOMPLETE_HORIZON` is censored;
- `INVALID_DATA` is invalid.

For `REAL_ADDS_HARD_BLOCK`, invalidation/time outcomes are objective-failure protection evidence and target outcomes are target opportunity cost. For `REAL_REMOVES_PROXY_HARD_BLOCK`, target outcomes are recovery evidence and invalidation/time outcomes are objective-failure exposure.

R4H-3B also reports non-fatal real states separately, applies sample/completeness thresholds, and requires separately auditable condition coverage before a narrow handoff review can be marked ready.

Full-tier reconstruction and full 4H replacement remain unsupported.

Merge CI: **2925 passed, 4 skipped**.

### R4H-3C — current branch phase

R4H-3C locks the **forward** research design before the evaluation window begins.

Independent sampling law:

`FIRST_OBSERVATION_PER_TICKER_SESSION`

Repeated 15-minute observations from the same ticker/session are not counted as independent evidence. The earliest valid observation survives, chosen from chronology/identity only and without reading the future outcome label.

Timestamp law:

- `observed_at` must be offset-aware;
- UTC is used for absolute ordering;
- ticker/session identity uses the calendar date encoded in the original timestamp offset, preventing UTC rollover from reassigning a session.

Chart-native condition coverage uses persisted real-4H structural state only:

- `TRENDING` = `EXPANSION` or `CONTINUATION`
- `COMPRESSION`
- `REPAIR`
- `TRANSITION`
- `FAILURE`
- `UNKNOWN`

Uncertainty law:

- point estimates are not enough;
- intervention proportions receive predeclared two-sided Wilson confidence intervals;
- narrow handoff review readiness requires both the point-effect rules and confidence-bound rules to pass.

Committed forward plan: `research/plans/r4h3_forward_oos_v1.json`.

Declared evaluation window:

- start: **2026-08-20**
- end: **2026-09-30**
- confidence level: **95%**
- no early stop because interim estimates look favorable
- final evaluation only after the end-date cohort has enough future completed sessions to mature its five-session VELOCITY label

Predeclared v1 minimums:

- 150 evaluable independent observations overall;
- 40 `REAL_ADDS_HARD_BLOCK` evaluable observations;
- 30 `REAL_REMOVES_PROXY_HARD_BLOCK` evaluable observations;
- <=15% ambiguous/censored;
- <=10% unavailable comparison;
- condition coverage: TRENDING 40, COMPRESSION 15, REPAIR 25, TRANSITION 15, FAILURE 5.

Point-effect requirements:

- real-adds-block protection >=70%;
- real-adds-block target cost <=30%;
- real-removes-block target recovery >=60%;
- real-removes-block objective-failure exposure <=40%.

95% Wilson-bound requirements:

- real-adds protection lower bound >=60%;
- real-adds target-cost upper bound <=40%;
- real-removes recovery lower bound >=50%;
- real-removes failure-exposure upper bound <=50%.

Even a fully passing R4H-3C report is research-only and can only justify opening a separately reviewed narrow-authority handoff branch. It cannot change runtime authority itself.

## VELOCITY-1 — five-session / +8% research stack

- VELOCITY-1A: pure feasibility + three-barrier contract. CI: **2853 passed, 4 skipped**.
- VELOCITY-1B: immutable scan-time observation envelope. CI: **2870 passed, 4 skipped**.
- VELOCITY-1C: bounded additive scan telemetry with zero live authority. CI: **2876 passed, 4 skipped**.
- VELOCITY-1D: offline observation-to-future-Daily chronological linker. CI: **2892 passed, 4 skipped**.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The next candidate ceiling is 40 only if measured evidence proves incremental opportunity recall without unacceptable cadence/cost impact. A move from 30 to 40 is a 33.3% increase in maximum model calls.

Near-cut telemetry records ranks 31-60, but full VELOCITY observations currently apply to analyzed candidates. CAP-40 therefore needs its own measured design/replay rather than assuming ranks 31-40 are beneficial.

## Next production sequence

1. R4H-3C: complete and merge forward independence/coverage/uncertainty design with zero live authority.
2. Allow the declared R4H forward window to accrue from 2026-08-20 through 2026-09-30 and then allow the final cohort's five-session outcome horizon to mature.
3. Run the independent R4H-3C report only after the planned window matures. Do not use favorable interim evidence to stop early.
4. If sample, condition coverage, point effects and Wilson bounds all pass, open a **separate narrow authority-handoff review**; otherwise remain shadow and continue evidence collection under a new reviewed plan if needed.
5. While the R4H forward window accrues, CAP-40 may proceed as a separate measured capacity/replay phase because it does not require premature 4H authority.
6. Final requested universe expansion remains its own reviewed PR after the pre-universe checkpoint.
7. Railway production observation remains part of final operational validation; no direct Railway connector is available in the current chat environment.

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
- setup-family work may not casually change universe membership;
- cross-family confluence may not stack scores;
- proxy agreement is not ground truth;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown or universe.

## Operational debt tracked but not blocking the current phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.

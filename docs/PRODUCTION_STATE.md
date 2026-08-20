# Current Production State

Last merged production baseline entering CAP-40C: `main` at `d6fa8f372b880db835b7d2d8dfa4de05996332f6` (Phase CAP-40B — boundary telemetry and offline future-Daily outcome linkage, on top of CAP-40A, R4H-3C/3B/3A, VELOCITY-1D/1C, R4H-2 HOLD SHADOW, CFR-2 family resolution, SFC-2B family-aware GPT-5.6 admission, and the deterministic execution stack).

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
- R4H-3A/3B/3C are production-green research infrastructure.
- CAP-40A/CAP-40B are production-green research infrastructure.
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

### R4H-2 authority decision

**Verdict: HOLD SHADOW.**

Before any real-4H authority handoff, a reviewed evidence package must establish chronological out-of-sample validation, forward outcome linkage, proxy-vs-real counterfactual evaluation, sample size accepted under a predeclared plan, accepted chart-condition coverage, precision preserved/improved, legitimate recall not materially damaged, and full capital-integrity CI.

R4H-2 never auto-promotes. A green evidence package only makes a later controlled handoff eligible for review.

### R4H-3A — merged

Pure 4H location-layer counterfactual between the production proxy and real-4H shadow evidence. It compares `SUPPORTIVE`, `REPAIRING`, `NO_EDGE`, `EXTENDED`, `HARD_BLOCK`, and `UNAVAILABLE`, joins by `(scan_id, ticker)`, and explicitly cannot reconstruct a final STARTER/SNIPE verdict from compact telemetry.

Merge CI: **2911 passed, 4 skipped**.

### R4H-3B — merged

Predeclared chronological location-layer outcome study. `TARGET_FIRST`, `INVALIDATION_FIRST`, and `TIME_BARRIER` are evaluable; same-session ambiguity, incomplete horizon, and invalid data stay non-evaluable. Full-tier reconstruction and full 4H replacement remain unsupported.

Merge CI: **2925 passed, 4 skipped**.

### R4H-3C — merged / forward study accruing

Independent sampling law: `FIRST_OBSERVATION_PER_TICKER_SESSION`.

Committed plan: `research/plans/r4h3_forward_oos_v1.json`.

Declared window:

- start: **2026-08-20**
- end: **2026-09-30**
- confidence level: **95%**
- no favorable early stop
- final review only after the last cohort's five-session outcome horizon can mature.

Predeclared minimums:

- 150 evaluable independent observations overall;
- 40 `REAL_ADDS_HARD_BLOCK` evaluable observations;
- 30 `REAL_REMOVES_PROXY_HARD_BLOCK` evaluable observations;
- <=15% ambiguous/censored;
- <=10% unavailable comparison;
- chart-condition coverage: TRENDING 40, COMPRESSION 15, REPAIR 25, TRANSITION 15, FAILURE 5.

Point-effect and Wilson-bound requirements remain exactly as committed in the R4H-3C plan. Even a full pass is research-only and requires a separate narrow-authority handoff branch.

Merge CI: **2938 passed, 4 skipped**.

## VELOCITY-1 — five-session / +8% research stack

- VELOCITY-1A: pure feasibility + three-barrier contract. CI: **2853 passed, 4 skipped**.
- VELOCITY-1B: immutable scan-time observation envelope. CI: **2870 passed, 4 skipped**.
- VELOCITY-1C: bounded additive scan telemetry with zero live authority. CI: **2876 passed, 4 skipped**.
- VELOCITY-1D: offline observation-to-future-Daily chronological linker. CI: **2892 passed, 4 skipped**.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**. Moving to 40 would increase the maximum GPT-5.6 call count by 33.3%, so the change must earn its cost with measured opportunity recall and operational evidence.

### CAP-40A — merged

Pure pre-model boundary observation for:

- `BASELINE_EDGE` = ranks 21–30;
- `SHADOW_INCREMENT` = ranks 31–40.

The observation carries stable scan/ticker/time identity, rank/admission evidence, structural invalidation when already available, setup-family evidence and VELOCITY feasibility. Missing geometry remains missing. No extra GPT-5.6 calls and no cap change.

Merge CI: **2954 passed, 4 skipped**.

### CAP-40B — merged

CAP-40B attaches the pre-model boundary block to existing Phase-14V traces without increasing normal-path trace count:

- ranks 31–40 reuse existing `near_cut` traces;
- ranks 21–30 reuse their analyzed/analysis-failure/rate-limit/tiering-failure trace;
- ranks 41–60 remain ordinary near-cut telemetry.

`capacity_boundary_dataset.py` reuses VELOCITY-1D chronology to produce future target/invalidation/time outcomes by boundary band. Shadow candidates never receive a reconstructed model tier; `counterfactual_model_tier_supported = false` remains explicit.

A shadow `TARGET_FIRST` is evidence of an excluded pre-model structural opportunity candidate, not proof of a missed STARTER/SNIPE alert.

Merge CI: **2966 passed, 4 skipped**.

### CAP-40C — current branch phase

CAP-40C locks the boundary-study design before outcomes are reviewed for a capacity decision.

Canonical plan: `research/plans/cap40_boundary_oos_v1.json`.

Declared observation window:

- start: **2026-08-20**
- end: **2026-09-30**
- final review not before: **2026-10-08**
- confidence level: **95%**
- no favorable early stop.

Independent sampling law:

`FIRST_OBSERVATION_PER_TICKER_SESSION`

Current naive autoscan timestamps are treated as UTC and converted to `America/New_York` before the session date is assigned. Offset-aware timestamps follow the same absolute-time path. If a ticker moves between rank bands during a session, only its earliest observation survives; outcome labels never influence selection.

Predeclared sample requirements:

- >=200 evaluable independent observations overall;
- >=90 evaluable baseline-edge observations;
- >=90 evaluable shadow-increment observations;
- <=15% ambiguous/censored;
- <=10% invalid;
- <=20% unknown setup family in the evaluable shadow cohort.

Predeclared shadow-opportunity requirements:

- >=30 shadow `TARGET_FIRST` observations;
- shadow target rate >=35%;
- 95% Wilson lower bound for shadow target rate >=25%;
- conservative lower bound for `(shadow target rate - baseline target rate)` >= -20 percentage points;
- >=60% of evaluable shadow observations classified VELOCITY `SUPPORTED` or `PARTIAL_SUPPORT`.

A passing CAP-40C report yields only `PAID_EXPERIMENT_REVIEW_READY`. It cannot change the production cap. A separately reviewed paid 30-vs-40 experiment must still measure downstream GPT-5.6 decision quality, scan duration, provider behavior, API usage/cost, precision, recall and alert quality.

## Next production sequence

1. CAP-40C: complete and merge the predeclared independent boundary-study engine, committed plan, uncertainty gates and local report generator.
2. Allow CAP-40 telemetry/outcomes to accrue through 2026-09-30 and mature through the committed final-review floor. Do not stop early because interim results look favorable.
3. Run CAP-40C only after the observation window/outcome horizon matures. If it fails, keep the cap at 30. If it passes, open a separate reviewed paid 30-vs-40 experiment design; do not change production directly.
4. In parallel, continue accruing the R4H-3C forward study through its committed window. Any R4H authority change remains a separate reviewed handoff.
5. Final requested universe expansion remains its own reviewed PR after the pre-universe checkpoint.
6. Railway production observation remains part of final operational validation; no direct Railway connector is available in the current chat environment.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a reviewed capacity experiment;
- production deep-analysis cap remains 30 until a later reviewed capacity decision explicitly changes it;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains `SHADOW_EVIDENCE_ONLY` until later reviewed evidence clears a narrowly scoped handoff;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- VELOCITY/R4H/CAP research evidence cannot promote, downgrade, route, suppress, size or forecast a trade;
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

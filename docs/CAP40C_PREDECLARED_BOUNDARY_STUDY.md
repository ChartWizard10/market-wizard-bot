# CAP-40C — Predeclared Candidate-Cap Boundary Study

## Purpose

CAP-40B creates a chronological outcome dataset for the current-cap edge and the next ten candidates outside the 30-candidate deep-analysis limit. CAP-40C locks the study design **before those outcomes are reviewed for a capacity decision**.

This phase answers one question:

> Is there enough independent, uncertainty-aware evidence that ranks 31–40 contain materially valuable pre-model opportunities to justify paying for a controlled 30-vs-40 GPT-5.6 experiment?

It does **not** answer whether the permanent production cap should become 40.

## Authority boundary

A passing CAP-40C report can only produce:

`PAID_EXPERIMENT_REVIEW_READY`

That means a separately reviewed paid capacity experiment may be designed. It does not change:

- the current 30-candidate production cap;
- GPT-5.6 call count;
- deterministic tiering;
- capital permission;
- Discord routing;
- suppression/cooldown;
- universe membership;
- real-4H authority.

`automatic_cap_change = false` and `permanent_cap_increase_supported = false` remain explicit report fields.

## Committed study plan

Canonical plan:

`research/plans/cap40_boundary_oos_v1.json`

Observation window:

- start: **2026-08-20**
- end: **2026-09-30**
- final review not before: **2026-10-08**
- confidence level: **95%**
- favorable interim results may not stop the study early.

The October 8 review floor gives the September 30 cohort time to mature its five completed future-session VELOCITY horizon before the final capacity review.

## Independent sampling law

Sampling unit:

`FIRST_OBSERVATION_PER_TICKER_SESSION`

A ticker can appear on many 15-minute scans and can move between rank bands during the same session. Those repeats are not independent opportunities.

CAP-40C therefore:

1. resolves the U.S. session date in `America/New_York`;
2. sorts observations by absolute timestamp, ticker and scan identity;
3. keeps the earliest observation for each ticker/session;
4. removes every later same-ticker/session observation, even if its band or outcome is more favorable.

Outcome labels are never used to choose which row survives.

### Timestamp compatibility

Current autoscan `started_at` values are naive UTC timestamps. CAP-40C explicitly treats those as UTC, then converts them to `America/New_York` before assigning the session date.

Offset-aware timestamps are also supported and are converted through the same absolute-time path.

This prevents an evening UTC date rollover from creating a false second U.S. session.

## Boundary bands

At the current cap:

- `BASELINE_EDGE` = ranks 21–30
- `SHADOW_INCREMENT` = ranks 31–40

The comparison remains local to the admission boundary.

CAP-40C deliberately excludes any reconstructed GPT-5.6 tier for shadow candidates. The study measures **pre-model opportunity value**, not hypothetical alert output.

## Outcome law

Evaluable terminal labels:

- `TARGET_FIRST`
- `INVALIDATION_FIRST`
- `TIME_BARRIER`

Non-evaluable quality states:

- `AMBIGUOUS_SAME_SESSION`
- `INCOMPLETE_HORIZON`
- `INVALID_DATA`

Ambiguous, censored and invalid rows are reported explicitly and cannot be silently converted into wins or losses.

## Predeclared sample requirements

The v1 plan requires:

- at least **200** evaluable independent observations overall;
- at least **90** evaluable `BASELINE_EDGE` observations;
- at least **90** evaluable `SHADOW_INCREMENT` observations;
- ambiguous + censored fraction <= **15%**;
- invalid fraction <= **10%**;
- unknown setup-family share in the evaluable shadow cohort <= **20%**.

These are study-readiness thresholds, not trading thresholds.

## Predeclared opportunity requirements

The shadow cohort must satisfy all of the following before a paid experiment can become review-eligible:

- at least **30** `TARGET_FIRST` observations;
- shadow `TARGET_FIRST` rate >= **35%**;
- 95% Wilson lower bound for the shadow target rate >= **25%**;
- conservative lower bound for `(shadow target rate - baseline-edge target rate)` >= **-20 percentage points**;
- at least **60%** of evaluable shadow observations must have ex-ante VELOCITY feasibility classified `SUPPORTED` or `PARTIAL_SUPPORT`.

The intent is not to prove that ranks 31–40 are equal to ranks 21–30. The intent is to require evidence that the excluded cohort contains enough structurally credible opportunity to justify spending money on a real deep-analysis experiment.

## Uncertainty law

Point estimates alone are insufficient.

Each band receives a 95% Wilson interval for its `TARGET_FIRST` proportion.

The report also creates a conservative difference interval:

- lower bound = shadow Wilson lower bound − baseline Wilson upper bound;
- upper bound = shadow Wilson upper bound − baseline Wilson lower bound.

This is intentionally conservative. A paid experiment is not justified merely because the point estimate looks attractive.

## Feasibility and setup-family composition

The report preserves composition by:

- setup family;
- VELOCITY feasibility state;
- boundary band.

This makes it possible to detect a misleading result driven by unknown family attribution or structurally weak path evidence rather than genuine near-cut opportunity.

The four production setup families remain:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

## Study decisions

CAP-40C can emit:

- `PLAN_INVALID`
- `WINDOW_NOT_MATURE`
- `SAMPLE_INSUFFICIENT`
- `BOUNDARY_EVIDENCE_NOT_SUPPORTIVE`
- `PAID_EXPERIMENT_REVIEW_READY`

The first four states leave the production cap at 30 and do not authorize extra model calls.

The fifth state also leaves the production cap at 30; it only authorizes review of a new experiment design.

## Local CLI

`scripts/build_cap40c_report.py` accepts:

- `--dataset`: CAP-40B outcome dataset JSON;
- `--plan`: committed CAP-40C plan JSON;
- `--as-of`: study evaluation date;
- `--out`: output report path.

The CLI is local-only and does not alter production state.

## What a later paid experiment must prove

If CAP-40C reaches `PAID_EXPERIMENT_REVIEW_READY`, a later branch must still measure the consequences of actually giving ranks 31–40 GPT-5.6 analysis:

1. how many added candidates become legitimate `NEAR_ENTRY`, `STARTER`, or `SNIPE_IT` states;
2. whether legitimate recall improves;
3. whether precision/alert quality deteriorates;
4. full scan duration versus the 15-minute cadence;
5. provider-limit behavior;
6. API usage and cost;
7. downstream dedup/routing effects;
8. outcome quality of the additional model-authorized candidates.

Only after that controlled experiment could a permanent 30-to-40 production-cap change be considered in another reviewed decision.

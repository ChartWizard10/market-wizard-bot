# CAP-40B — Boundary Telemetry and Outcome Linkage

## Purpose

CAP-40A defined a pure pre-model observation for the current 30-candidate admission boundary. CAP-40B wires that evidence into the existing isolated scan-telemetry path and makes valid observations linkable to future completed Daily sessions.

Production still analyzes **30** candidates per scan. CAP-40B makes **zero additional GPT-5.6 calls**.

## Boundary cohorts

At the current cap:

- `BASELINE_EDGE` = ranks **21–30**
- `SHADOW_INCREMENT` = ranks **31–40**

The first cohort is the weakest ten candidates already paid for under the current cap. The second is the next ten eligible candidates that a cap of 40 would admit.

This comparison is intentionally local to the cutoff. It does not compare elite top-ranked names with weaker shadow names.

## Telemetry wiring

CAP-40B does **not** create twenty additional decision-trace rows per scan.

Instead, it attaches the compact `capacity_boundary_observation` block to traces that already exist:

- ranks 31–40 attach to the existing Phase-14V `near_cut` traces;
- ranks 21–30 attach to their existing analyzed, analysis-failed, rate-limited, or tiering-failed trace.

Ranks 41–60 retain their existing Phase-14V near-cut trace but receive no CAP-40 boundary block.

This preserves the existing 9,000-trace retention budget instead of shortening the history merely to collect a capacity study.

The Phase-14V schema version remains `14V.2`. The new field is optional and additive; existing telemetry remains valid.

## Decision-time evidence

Before the model call, the scheduler builds CAP-40A observations from the already-computed prefilter result and enriched chart evidence. The compact block may include:

- stable scan/ticker/time identity;
- rank and current/proposed candidate cap;
- reference price and existing structural invalidation;
- approximately +8% / five-session VELOCITY feasibility;
- prefilter and family-aware admission score/source;
- setup-family identity/state/score;
- entry-structure, retest, overhead and R:R evidence.

The block contains no post-model final tier or capital action. This keeps the rank-21–30 and rank-31–40 observations comparable at the same decision stage.

## Failure isolation

CAP-40 telemetry is observational only. The projection is wrapped inside the existing telemetry failure domain.

A CAP-40 projection error cannot:

- change candidate admission;
- add a model call;
- block an admitted model call;
- change a deterministic tier;
- change capital action;
- reroute or suppress Discord;
- mutate alert history.

## Offline outcome linker

`src/capacity_boundary_dataset.py` extracts the attached CAP-40 blocks from local telemetry and reuses the existing VELOCITY-1D chronological linker.

For a research-ready observation it carries forward:

- entry/reference price;
- structural invalidation;
- target-return objective;
- five-session horizon;
- feasibility and setup-family attribution;
- rank/band/admission metadata.

`velocity_dataset.link_observation_to_future()` remains the source of chronological truth. The observation-day Daily candle is excluded. Future completed sessions are date-sorted, duplicate-conflict checked, and fed to the existing three-barrier outcome labeler.

Possible labels remain:

- `TARGET_FIRST`
- `INVALIDATION_FIRST`
- `AMBIGUOUS_SAME_SESSION`
- `TIME_BARRIER`
- `INCOMPLETE_HORIZON`
- `INVALID_DATA`

## What the outcome means

A `TARGET_FIRST` result in `SHADOW_INCREMENT` is evidence that the 30-candidate cutoff excluded a pre-model candidate whose existing structural geometry later achieved the research objective before invalidation.

It is **not** evidence that GPT-5.6 would have returned `STARTER` or `SNIPE_IT` for that candidate.

Ranks 31–40 never received the model call, so CAP-40B explicitly returns:

`counterfactual_model_tier_supported = false`

The correct interpretation is **missed structural opportunity candidate**, not reconstructed missed trade.

## Duplicate law

CAP-40 observations join by stable `(scan_id, ticker)` identity.

- byte-semantically equivalent normalized duplicates are deduplicated;
- conflicting duplicates fail closed as `INVALID_DATA` with `DUPLICATE_BOUNDARY_OBSERVATION_CONFLICT`;
- rank alone is never a join key.

## Local CLI

`scripts/build_cap40b_dataset.py` accepts:

- `--telemetry`: local Phase-14V telemetry JSON;
- `--bars`: local ticker → completed Daily bars JSON;
- `--out`: output dataset path.

The CLI performs local file I/O only. It makes no network request and changes no production state.

## Zero-authority contract

CAP-40B grants no:

- candidate-cap authority;
- model authority;
- tier authority;
- capital authority;
- routing authority;
- forecast authority.

The production cap remains **30**.

## Next phase — CAP-40C

CAP-40C should define the predeclared evidence report for the boundary dataset before any paid capacity experiment is considered.

The report should quantify at minimum:

1. research-ready sample counts in both bands;
2. `TARGET_FIRST`, `INVALIDATION_FIRST`, and `TIME_BARRIER` distributions;
3. censored/ambiguous/invalid fractions;
4. setup-family and feasibility composition by band;
5. the incremental shadow target opportunity rate;
6. uncertainty intervals around the difference between the two boundary cohorts.

Only if the boundary evidence shows material excluded opportunity should the project consider paying for a controlled live 30-vs-40 deep-analysis experiment.

A later paid experiment must separately measure GPT-5.6 downstream quality, scan duration, provider limits, API usage/cost, precision, legitimate recall and alert quality before any permanent cap increase.

## Non-drift law

CAP-40B changes no strategy authority:

- 814-symbol universe unchanged;
- 15-minute cadence unchanged;
- 30-candidate deep-analysis cap unchanged;
- GPT-5.6 runtime unchanged;
- family-aware admission unchanged;
- SNIPE / STARTER / NEAR_ENTRY / WAIT ladder unchanged;
- real 4H remains `SHADOW_EVIDENCE_ONLY`;
- capital, routing, cooldown and Discord behavior unchanged.

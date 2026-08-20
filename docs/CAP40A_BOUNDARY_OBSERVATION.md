# CAP-40A — Candidate-Cap Boundary Observation

## Purpose

Production currently admits at most **30** candidates per scan to GPT-5.6 deep analysis. The next proposed ceiling is **40**, but the project does not assume that ten additional model calls improve the scanner.

CAP-40A creates the first controlled measurement surface at the admission boundary. It compares candidates that are already inside the current cap with the next candidates that would become eligible if the cap were raised.

This phase is **research-only**. It does not change the production cap.

## Canonical study bands

With the current cap of 30:

- `BASELINE_EDGE` = ranks **21–30**
- `SHADOW_INCREMENT` = ranks **31–40**

The baseline band is intentionally the ten weakest admitted candidates under the current ranking. The shadow band is the next ten eligible candidates immediately outside the cap. This creates a like-for-like boundary comparison rather than comparing ranks 1–10 against ranks 31–40.

The band logic derives from the declared current cap, increment and baseline width. It is not permanently hardcoded to 30/40.

## What CAP-40A records

`src/capacity_boundary_observation.py` builds a compact pre-model observation from evidence that already exists before GPT-5.6 is called:

- stable `scan_id` and ticker identity;
- observation timestamp;
- prefilter rank and score;
- admission rank score and admission source;
- current reference price;
- structural invalidation when it already exists;
- +8% / five-session VELOCITY feasibility evidence;
- setup-family identity/state/score;
- family watch/admission/entry-structure flags;
- family R:R, retest status, overhead status and estimated R:R.

Missing geometry remains missing. The observation is marked `ready = false` if stable identity, price or structural invalidation is unavailable. CAP-40A never manufactures a stop so that a row can enter a later outcome study.

## Stable identity law

Future chronological linking must never join observations by rank alone. Rankings can change every scan and a ticker can appear repeatedly.

A research-ready CAP-40A row therefore requires:

- `scan_id`
- ticker
- `observed_at`
- reference price
- invalidation level

These fields define the decision-time observation that later research phases may link to future completed Daily sessions.

## Invalidation precedence

CAP-40A uses only structural invalidation evidence already available before the model call, in this order:

1. `key_features.setup_family_invalidation`
2. `setup_family_evidence.primary_invalidation_level`
3. generic enriched `invalidation_level`

A level must be positive and below the reference price for the bullish research contract. Invalid values are rejected rather than repaired or guessed.

## VELOCITY relationship

CAP-40A reuses the existing pure VELOCITY-1A feasibility contract. The approximately +8% within five completed sessions objective remains a **research objective**, not a forecast and not a trade gate.

The boundary observation may therefore carry:

- feasibility status;
- known structural path room;
- ATR percentage;
- required move in ATR units.

This lets later research ask whether the shadow increment contains feasible opportunities that the 30-candidate cutoff excluded.

## What CAP-40A does not prove

Ranks 31–40 have **not** received GPT-5.6 analysis in this phase. Therefore CAP-40A cannot claim that a shadow candidate would have become:

- `NEAR_ENTRY`
- `STARTER`
- `SNIPE_IT`

It also cannot reconstruct the full downstream ladder, because the model output and post-tiering evidence stack do not exist for an unadmitted candidate.

A strong pre-model boundary observation is evidence that a candidate deserved further study, not proof that it was a trade.

## Zero-authority contract

CAP-40A grants no:

- model authority;
- candidate-cap authority;
- tier authority;
- capital authority;
- routing authority;
- forecast authority.

It adds no model call, market-data refetch, Discord action, state mutation, suppression rule or live candidate promotion.

Production remains at **30** candidates per scan.

## Next phase: CAP-40B

After CAP-40A is production-green, CAP-40B should wire these bounded pre-model observations into the existing isolated telemetry/research path and make them chronologically linkable to future completed Daily sessions.

CAP-40B should still make **zero extra GPT-5.6 calls** and should still leave the production cap at 30.

The resulting research dataset can compare the last ten admitted candidates with the next ten excluded candidates on:

- observation completeness;
- setup-family distribution;
- structural/volatility feasibility;
- future +8% target / invalidation / five-session outcomes where valid geometry exists.

That outcome comparison can measure whether the cutoff is excluding structurally valuable candidates, but it still cannot measure the exact downstream tier those candidates would have received from GPT-5.6.

## Later capacity experiment

A live cap increase requires a separately reviewed capacity phase after boundary evidence justifies paying for the extra calls. That phase must measure at least:

1. incremental legitimate opportunity recall;
2. deep-analysis quality for the added candidates;
3. full scan duration against the 15-minute cadence;
4. provider rate-limit behavior;
5. API usage/cost impact;
6. whether precision or alert quality deteriorates.

Only that later reviewed phase may change `max_claude_candidates_per_scan` from 30 to 40.

## Non-drift law

CAP-40A changes no production strategy behavior. In particular:

- 814-symbol universe unchanged;
- 15-minute cadence unchanged;
- 30-candidate cap unchanged;
- GPT-5.6 provider/runtime unchanged;
- setup-family admission unchanged;
- SNIPE/STARTER/NEAR_ENTRY/WAIT ladder unchanged;
- real 4H remains `SHADOW_EVIDENCE_ONLY`;
- capital, routing, cooldown and Discord behavior unchanged.

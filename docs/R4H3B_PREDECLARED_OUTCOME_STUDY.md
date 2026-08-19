# R4H-3B — Predeclared Chronological Outcome Study

## Purpose

R4H-3A created a common 4H location-effect vocabulary for the legacy production proxy and the real R4H-1 shadow engine, then attached those comparisons to VELOCITY-1D forward outcomes.

R4H-3B makes that evidence executable as a **predeclared chronological research study**. It still does not give real 4H any live authority.

The study remains limited to the 4H location layer. Compact historical telemetry still does not contain every decision-time input required to reconstruct the full STARTER/SNIPE ladder with the 4H source swapped.

## Outcome law

For the five-session / approximately +8% research objective:

- `TARGET_FIRST` = evaluable terminal target outcome;
- `INVALIDATION_FIRST` = evaluable terminal structural-failure outcome;
- `TIME_BARRIER` = evaluable terminal outcome where neither price barrier was hit inside the horizon;
- `AMBIGUOUS_SAME_SESSION` = ambiguous and excluded from efficacy rates;
- `INCOMPLETE_HORIZON` = censored and excluded from efficacy rates;
- `INVALID_DATA` = invalid and excluded from efficacy rates.

The study never converts ambiguous, censored, or invalid rows into wins or losses.

## Predeclared plan law

`validate_study_plan()` requires the project to freeze the sample rules **before outcome review**.

Required plan fields:

- `name`
- `version`
- `frozen_before_outcome_review: true`
- `chronological_out_of_sample: true`
- `min_evaluable_records`
- `min_real_adds_hard_block_evaluable`
- `min_real_removes_proxy_hard_block_evaluable`
- `max_ambiguous_or_censored_pct`
- `max_comparison_unavailable_pct`

There are no built-in numeric defaults. The repository must explicitly choose the thresholds in the reviewed study plan rather than allowing the code to invent favorable cutoffs after seeing results.

Optional effect thresholds:

- `max_real_adds_block_target_opportunity_cost_pct`
- `min_real_adds_block_objective_failure_protection_pct`
- `min_real_removes_block_target_recovery_pct`
- `max_real_removes_block_objective_failure_exposure_pct`

If no effect thresholds are declared, a sample-ready study remains `DESCRIPTIVE_ONLY`.

## Hard-block intervention interpretation

### `REAL_ADDS_HARD_BLOCK`

This means the production proxy was not a 4H hard block but real 4H was.

For evaluable rows:

- `INVALIDATION_FIRST` + `TIME_BARRIER` are counted as **objective-failure protection evidence** for the added block;
- `TARGET_FIRST` is counted as **target opportunity cost**.

This is local 4H-layer evidence. It does not prove the full scanner would have entered the candidate absent the real 4H block.

### `REAL_REMOVES_PROXY_HARD_BLOCK`

This means the production proxy was a 4H hard block but real 4H was not.

For evaluable rows:

- `TARGET_FIRST` is counted as **target recovery evidence**;
- `INVALIDATION_FIRST` + `TIME_BARRIER` are counted as **objective-failure exposure**.

Again, this is not a reconstructed final trade.

## Non-fatal state study

The report separately summarizes forward outcomes for real 4H states mapped to:

- `SUPPORTIVE`
- `REPAIRING`
- `NO_EDGE`
- `EXTENDED`
- `UNAVAILABLE`

This prevents a hard-failure study from erasing useful information about repair, mid-range, or extension behavior.

## Sample readiness

`evaluate_sample_readiness()` applies only the plan thresholds that were frozen in advance. It checks:

- total evaluable outcomes;
- evaluable `REAL_ADDS_HARD_BLOCK` observations;
- evaluable `REAL_REMOVES_PROXY_HARD_BLOCK` observations;
- ambiguous/censored fraction;
- unavailable-comparison fraction.

If the sample fails any declared threshold, the study returns `SAMPLE_INSUFFICIENT`.

## Market-condition coverage

R4H-2 requires accepted market-condition coverage before any authority handoff.

The current compact VELOCITY/R4H dataset does not persist a canonical market-regime label. R4H-3B therefore does not invent one.

A study plan may declare `market_condition_minimums`, and `build_study_report()` may receive a separately auditable `coverage_counts` object. Missing or insufficient counts remain unaccepted.

## Study decisions

R4H-3B can emit:

- `PLAN_INVALID`
- `SAMPLE_INSUFFICIENT`
- `DESCRIPTIVE_ONLY`
- `NARROW_HARD_BLOCK_EVIDENCE_SUPPORTIVE`
- `NARROW_HARD_BLOCK_EVIDENCE_NOT_SUPPORTIVE`

`NARROW_HARD_BLOCK_EVIDENCE_SUPPORTIVE` means only that the predeclared local 4H hard-block study cleared the declared sample/effect/coverage rules. It is **not** live authority.

A later reviewed branch would still be required to decide whether a narrow first handoff is justified—for example, allowing a validated real-4H accepted-failure state to operate as a veto while leaving the rest of the proxy stack untouched.

## Why full replacement remains unsupported

R4H-3B explicitly leaves:

- `full_tier_counterfactual_supported = false`
- `full_4h_replacement_supported = false`

The R4H-2 projection also keeps the following full-authority flags false:

- full-stack precision improved/preserved;
- legitimate opportunity recall not materially damaged;
- capital-integrity regressions green.

Those facts cannot be manufactured from a location-only study.

## Local CLI

`scripts/build_r4h3b_study.py` accepts:

- `--counterfactual`: R4H-3A counterfactual dataset JSON;
- `--plan`: predeclared R4H-3B plan JSON;
- `--coverage`: optional separately auditable market-condition counts JSON;
- `--out`: output report path.

The CLI performs local file I/O only. It makes no network request and changes no production state.

## No production drift

R4H-3B changes no live scanner behavior.

Real 4H remains `SHADOW_EVIDENCE_ONLY`. The 814-symbol universe, 15-minute cadence, 30-candidate GPT-5.6 cap, setup-family compiler/resolver, tier thresholds, capital map, Discord routing, cooldown, ladder and downgrade-only seals remain unchanged.

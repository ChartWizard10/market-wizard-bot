# R4H-3C — Forward Independence, Coverage, and Uncertainty Design

## Purpose

R4H-3A established a truthful 4H location-layer counterfactual between the production proxy and the real 4H shadow engine. R4H-3B linked that comparison to VELOCITY-1D terminal outcomes and created a predeclared study contract.

R4H-3C locks the forward study design before the evaluation window begins. It addresses three remaining research-integrity risks:

1. repeated 15-minute observations of the same ticker/session must not be counted as independent evidence;
2. chronological out-of-sample status must be tied to an explicit forward date window;
3. point estimates must be accompanied by uncertainty bounds rather than treated as sufficient evidence by themselves.

Real 4H remains `SHADOW_EVIDENCE_ONLY` throughout this phase.

## Independent sampling law

The canonical unit is:

`FIRST_OBSERVATION_PER_TICKER_SESSION`

For every ticker/session inside the declared evaluation window, the earliest valid observation is selected. Later observations from the same ticker/session are removed from the independent sample.

The selection key is based only on chronology and identity. The future outcome label is never used to choose which row survives. A later `TARGET_FIRST` observation therefore cannot replace an earlier `INVALIDATION_FIRST` observation simply because it looks better after the fact.

The observation timestamp must be offset-aware. Naive timestamps are excluded rather than assigned a guessed timezone.

Session identity uses the calendar date encoded in the observation's original offset. UTC is used only for absolute ordering. This prevents a late offset-aware observation from being accidentally moved to the next session merely because its UTC date rolled over.

## Explicit forward window

The reviewed plan file is:

`research/plans/r4h3_forward_oos_v1.json`

Version 1.0 declares:

- evaluation start: `2026-08-20`
- evaluation end: `2026-09-30`
- no early stop based on favorable interim results
- final evaluation only after the end-date cohort has enough future completed sessions to mature its five-session VELOCITY label

This means no R4H authority conclusion can legitimately be produced from this plan before the forward evidence exists.

## Predeclared sample requirements

The v1 plan requires at least:

- 150 evaluable independent observations overall;
- 40 evaluable `REAL_ADDS_HARD_BLOCK` observations;
- 30 evaluable `REAL_REMOVES_PROXY_HARD_BLOCK` observations;
- no more than 15% ambiguous/censored rows;
- no more than 10% unavailable comparisons.

These thresholds are committed before the forward evaluation window. They are not tuned from future results.

## Point-effect requirements

For the local 4H hard-block disagreement study, the v1 plan declares:

### Real 4H adds a hard block

- objective-failure protection must be at least 70%;
- target opportunity cost must be no more than 30%.

### Real 4H removes a proxy hard block

- target recovery must be at least 60%;
- objective-failure exposure must be no more than 40%.

These remain location-layer research measures. They are not reconstructed final trades.

## Wilson uncertainty gate

R4H-3C adds a two-sided Wilson score interval to each intervention proportion at a predeclared 95% confidence level.

The v1 plan requires:

- real-adds-block protection lower confidence bound >= 60%;
- real-adds-block target-cost upper confidence bound <= 40%;
- real-removes-block recovery lower confidence bound >= 50%;
- real-removes-block failure-exposure upper confidence bound <= 50%.

A favorable point estimate with an uncertainty interval that fails these bounds is not enough for handoff review readiness.

## Chart-native condition coverage

R4H-3C derives condition coverage only from the persisted real-4H structural state. No external market factor is invented.

Canonical categories:

- `TRENDING` — real state `EXPANSION` or `CONTINUATION`
- `COMPRESSION`
- `REPAIR`
- `TRANSITION`
- `FAILURE`
- `UNKNOWN`

The v1 plan requires at least:

- TRENDING: 40
- COMPRESSION: 15
- REPAIR: 25
- TRANSITION: 15
- FAILURE: 5

Coverage is evaluated on the same independently sampled records used by the study.

## Forward review-readiness law

`forward_handoff_review_ready` can become true only if all of the following are true:

1. the R4H-3C forward plan is valid;
2. the independent sample satisfies the R4H-3B sample requirements;
3. the R4H-3B point-effect requirements pass;
4. the declared chart-condition coverage passes;
5. the R4H-3C Wilson confidence-bound gate passes.

Even then, the result is only **ready for a separately reviewed narrow authority-handoff branch**. It does not modify runtime authority automatically.

## What this phase still cannot prove

R4H-3C remains a 4H location-layer study. It does not reconstruct the complete historical STARTER/SNIPE ladder because compact telemetry does not persist every decision-time Daily, 1H, candle, path, invalidation, and R:R input needed for a full counterfactual replay.

Therefore:

- full-tier counterfactual remains unsupported;
- full 4H replacement remains unsupported;
- real 4H remains shadow;
- no live tier, capital, routing, Discord, universe, cadence, candidate-cap, or model-admission behavior changes in this phase.

## Stop rule

Do not evaluate the v1 plan early because interim results look favorable.

After the September 30, 2026 session closes, the final observation cohort still needs the full future-session horizon required by VELOCITY-1D. Only after those labels mature should the independent forward report be treated as the planned evaluation artifact.

If the sample, coverage, effect, or uncertainty requirements fail, the correct verdict is to remain shadow and keep collecting or redesign a future study in a new reviewed plan. The thresholds must not be retroactively loosened to make the completed sample pass.

# R4H-3A — Real-vs-Proxy 4H Counterfactual Policy Contract

## Decision boundary

R4H-2 correctly held the real 4H engine in `SHADOW_EVIDENCE_ONLY`. A truthful real 4H chart and a proxy-agreement statistic do not prove that replacing the existing operational proxy will improve scanner decisions.

VELOCITY-1D now supplies the missing forward-outcome bridge: scan-time observations can be linked offline to future Daily target / invalidation / time-barrier outcomes. R4H-3A defines the policy vocabulary needed to compare the **4H location layer** against those outcomes without pretending that 4H alone determines a final trade tier.

## What production actually does today

The production SNIPE ladder reads the Phase-14F operational proxy through `timeframe_alignment.operational_timeframe.state` and `trade_location`.

Its existing location semantics are not a simple yes/no gate:

- `LOCATION_VALID` is the strongest operational neighborhood;
- `LOCATION_REPAIRING` is alive but not pristine;
- `LOCATION_EXTENDED` is non-hostile but not an ideal location;
- `LOCATION_HOSTILE` is a hard 4H location failure;
- unknown remains unproven.

A final STARTER or SNIPE still requires the rest of the sovereign stack: Daily permission, real retest truth, 1H trigger/hold, candle truth, structural invalidation, clean enough path, R:R, and every downstream seal/capital rule.

Therefore R4H-3A does **not** claim it can reconstruct a final tier merely from a 4H state.

## Common location-effect vocabulary

Both proxy and real 4H are mapped into the same research vocabulary:

- `SUPPORTIVE`
- `REPAIRING`
- `NO_EDGE`
- `EXTENDED`
- `HARD_BLOCK`
- `UNAVAILABLE`

This vocabulary is descriptive. It has no live authority.

### Production proxy mapping

- `LOCATION_VALID` -> `SUPPORTIVE`
- `LOCATION_REPAIRING` -> `REPAIRING`
- `LOCATION_EXTENDED` -> `EXTENDED`
- `LOCATION_HOSTILE` -> `HARD_BLOCK`
- missing/unknown -> `UNAVAILABLE`

### Real 4H mapping

The mapping uses the states already emitted by R4H-1:

- `DEFENDABLE` or `READY_FOR_1H_PROOF` -> `SUPPORTIVE`
- `REPAIRING` / structural `REPAIR` -> `REPAIRING`
- `MID_RANGE` -> `NO_EDGE`
- `EXTENDED` -> `EXTENDED`
- closed structural `FAILURE` / `HOSTILE` -> `HARD_BLOCK`
- stale, insufficient, error, or unclassifiable evidence -> `UNAVAILABLE`

`MID_RANGE` is intentionally not called structural failure. R4H-1 defines it as a location with no structural reason to act. `EXTENDED` is likewise kept distinct rather than converted into a failure.

## Counterfactual comparison classes

R4H-3A classifies only the 4H-layer difference:

- `SAME_LOCATION_EFFECT`
- `REAL_ADDS_HARD_BLOCK`
- `REAL_REMOVES_PROXY_HARD_BLOCK`
- `NON_FATAL_LOCATION_DIFFERENCE`
- `COMPARISON_UNAVAILABLE`

These classes let the future study ask evidence questions such as:

- When production did not have a hostile 4H proxy but real 4H showed accepted failure, what happened next?
- When the production proxy was hostile but real 4H showed a defendable/reparing/non-hostile location, what happened next?
- What are the forward outcomes of real `MID_RANGE` and `EXTENDED` states?

The answers are research evidence. They are not automatic promotion instructions.

## Why full-tier counterfactual is not claimed yet

The compact telemetry used by the VELOCITY dataset does not preserve every input required to rerun the entire ladder with one 4H source swapped for another. A full final-tier counterfactual would need the complete decision-time combination of:

- 1H trigger/retest/hold evidence;
- candle truth and trade-location evidence;
- Daily and higher-timeframe permission evidence;
- path, invalidation, R:R and failure-state evidence;
- the exact downstream ladder/seal context.

R4H-3A therefore exposes `can_reconstruct_full_tier_counterfactual=false` rather than inventing missing evidence.

## Outcome join

`attach_counterfactuals()` joins an existing VELOCITY-1D dataset to the original analyzed telemetry trace by `(scan_id, ticker)` and attaches the R4H-3A comparison.

Conflicting/missing trace evidence becomes `COMPARISON_UNAVAILABLE`; it is not guessed through.

The summary exposes outcome counts for:

- real-added hard blocks;
- real-removed proxy hard blocks;
- each proxy location effect;
- each real location effect;
- every comparison class.

It deliberately leaves `authority_decision=NOT_EVALUATED`.

## What R4H-3A can prove

With enough chronological linked observations, it can measure whether the real 4H **hard-failure layer** appears to protect against losing outcomes or whether it blocks legitimate winners. It can also identify proxy-hostile cases where real 4H was non-hostile and observe what happened next.

That is useful evidence, but it still does not prove that real 4H should replace every production 4H function.

## Next phase

R4H-3B should make the study statistically executable without touching live authority. It should:

1. define the predeclared sample/completeness rules;
2. define which outcome labels are decisive versus censored/ambiguous;
3. report winner-loss protection and opportunity-cost counts for `REAL_ADDS_HARD_BLOCK` and `REAL_REMOVES_PROXY_HARD_BLOCK`;
4. separately study non-fatal real states (`SUPPORTIVE`, `REPAIRING`, `NO_EDGE`, `EXTENDED`);
5. refuse an authority verdict when the sample is incomplete or too small under the predeclared plan;
6. keep full-tier replacement unsupported unless enough decision-time evidence is persisted to reconstruct it honestly.

A later controlled handoff may choose a narrower first authority scope—for example, validated real-4H accepted failure as a veto—rather than forcing an all-or-nothing replacement. Any such handoff still requires its own reviewed production phase and full capital-integrity CI.

## No production drift

R4H-3A changes no live scanner behavior. Real 4H remains `SHADOW_EVIDENCE_ONLY`. The 814-symbol universe, 15-minute cadence, 30-candidate GPT-5.6 cap, setup-family logic, tier thresholds, capital map, Discord routing, cooldown, and seals remain unchanged.
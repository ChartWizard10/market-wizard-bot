# VELOCITY-1B — Observation Envelope Contract

## Purpose

VELOCITY-1A established the deterministic research semantics for the Chart Wizard fast-swing objective:

- ex-ante feasibility evidence for an approximately +8% move inside five trading sessions; and
- ex-post three-barrier outcome labels using target, structural invalidation, and time.

VELOCITY-1B defines the immutable scan-time observation envelope that can later be persisted and linked to future Daily bars. This is the bridge between a live scanner judgment and chronological validation.

This phase is still research-only. It does not change tiering, candidate admission, ranking, capital, Discord routing, cooldown, universe membership, scan cadence, candidate cap, or real-4H authority.

## Why an explicit envelope is necessary

A forward outcome label is only useful if the original observation can be reconstructed without hindsight. The validation record therefore needs the exact scan-time facts that existed before the future bars occurred.

The envelope joins:

- scan identity and timestamp;
- ticker;
- observed final tier and capital action;
- whether the observed tier was capital-authorized at that moment;
- reference price and its source;
- structural invalidation and condition;
- observed R:R and overhead state when present;
- resolved setup-family attribution;
- real-4H shadow state and legacy-proxy comparison context;
- the VELOCITY-1A feasibility snapshot;
- an explicit persistence-readiness flag and missing-field ledger.

No future bar, outcome label, or hindsight-derived feature belongs in this object.

## Authority boundary

Every envelope carries permanent negative-authority flags:

- `research_only=true`
- `observational_only=true`
- `capital_authority=false`
- `tier_authority=false`
- `routing_authority=false`
- `forecast_authority=false`

`persistence_ready=true` means only that enough original geometry exists to support a later label. It is not a quality grade and cannot upgrade or reject a trade.

## Capital-at-observation truth

The validation system must not silently treat every observed chart as an executed trade.

VELOCITY-1B records `capital_authorized_at_observation` from the observed final tier:

- `SNIPE_IT` -> true
- `STARTER` -> true
- `NEAR_ENTRY` -> false
- `WAIT` -> false

This allows later research to study watch-state opportunity capture while keeping realized-capital studies separate.

## Setup-family attribution

The envelope records the resolved primary family plus compact cross-family relationship context. It does not copy family scores or stack confluence.

This supports later attribution by:

- `BREAK_RETEST_CONTINUATION`
- `VCP_BREAK_RETEST`
- `SMA_CRADLE_CONTINUATION`
- `GAP_FILL_REVERSAL`

while preserving the CFR law that a family resolver has no tier or capital authority.

## Real-4H research context

R4H-2 correctly held real 4H in `SHADOW_EVIDENCE_ONLY` because the repository did not yet possess outcome-linked proxy-vs-real evidence.

VELOCITY-1B therefore preserves both sides as separate research facts:

- real-4H structural state/location/readiness/freshness/continuity; and
- legacy proxy state/agreement when available.

Agreement is not ground truth. The future validation phase must compare each policy against actual forward outcomes.

## Future linker contract

`observation_to_label_input()` projects only the immutable fields required by a later chronological linker:

- scan id/time/ticker;
- reference price;
- invalidation;
- target-return objective;
- time horizon;
- observed tier/capital authorization;
- primary setup family;
- real-4H state;
- proxy state/agreement.

It deliberately emits no `label`, `outcome`, or `future_bars` field.

## Next controlled phase

VELOCITY-1C should wire this envelope into scan telemetry as a bounded observational block for analyzed candidates only. The wiring must preserve telemetry's isolated failure domain and must not modify the judgment object passed to dedup, Discord, or state history.

After sufficient observations exist, VELOCITY-1D can connect those records to completed future Daily bars offline and produce the chronological three-barrier dataset required for:

1. five-session/+8% objective validation;
2. R4H real-vs-proxy counterfactual analysis;
3. setup-family/tier attribution;
4. candidate-cap 30-vs-40 recall measurement.

## No drift

This phase leaves unchanged:

- 814-symbol production universe;
- 15-minute scan cadence;
- 30-candidate GPT-5.6 cap;
- all setup-family common gates;
- score and R:R floors;
- structural invalidation law;
- real 4H shadow authority;
- WAIT routing law;
- cooldown/dedup;
- capital authority.

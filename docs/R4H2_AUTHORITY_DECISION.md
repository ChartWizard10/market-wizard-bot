# R4H-2 — Real 4H Authority Decision

## Verdict

**HOLD SHADOW. Do not promote real 4H to production gating/capital authority yet.**

This is an evidence decision, not a statement that the real 4H engine is weak. R4H-1 established that the scanner can construct session-aligned 4H candles and derive a coherent operational structure/location/retest/hold/failure/path read. The missing proof is different: the repository does not yet contain chronological forward evidence showing that replacing the legacy operational proxy with the real 4H authority improves trade decisions without materially reducing legitimate opportunity recall.

## What is already proven

R4H-1 proves implementation and evidence semantics:

- real 4H is built from the existing 60-minute response with no extra market-data fetch;
- completed 4H candles are confirmation evidence while live 4H candles are information only;
- incomplete/ambiguous/missing constituent buckets cannot be stitched across as if history were continuous;
- accepted structural failure, live failure threat, break, displacement, retest and hold are distinguished;
- stale/degraded evidence fails safely;
- real-vs-proxy comparison is recorded without forcing agreement;
- the 4H organ cannot grant Daily permission and cannot receive 1H back-writes;
- R4H-1 is explicitly `SHADOW_EVIDENCE_ONLY`.

The production scan telemetry also persists a compact `four_hour_real` block with status, state, location, readiness, evidence freshness/continuity and proxy agreement.

## What is not yet proven

The current decision-trace contract does **not** attach a forward outcome label or a proxy-vs-real counterfactual outcome to the 4H comparison. Therefore the repository can answer:

- what real 4H said;
- what the legacy proxy said;
- whether they agreed;
- whether the 4H evidence was fresh/complete.

It cannot yet answer, across a chronological out-of-sample sample:

- whether the real-4H decision would have filtered more false positives;
- whether it would have blocked valid STARTER/SNIPE opportunities;
- whether it would have improved target-before-stop performance;
- whether any benefit persists across different regimes;
- whether a disagreement should resolve in favor of real 4H based on realized forward outcomes.

Agreement rate alone is not a validation metric because the legacy proxy is not ground truth. Synthetic unit tests are implementation tests, not predictive validation.

## Additional reason not to promote by assumption

`src/four_hour_operational.py` explicitly classifies several R4H-1 constants as **new shadow-evidence research thresholds**, not doctrine/config authority. Promoting the engine before outcome validation would silently elevate research thresholds into capital logic. That is exactly the kind of authority drift the scanner architecture is designed to prevent.

## R4H-2 evidence contract

`src/four_hour_authority_audit.py` formalizes the promotion prerequisites. A future validation artifact must explicitly establish all of the following before real 4H can even become **eligible for controlled promotion review**:

1. chronological out-of-sample evaluation;
2. forward outcome linkage;
3. proxy-vs-real counterfactual evaluation;
4. sample size accepted under a predeclared plan;
5. accepted regime coverage;
6. real 4H improves or preserves precision;
7. real 4H does not materially damage recall;
8. capital-integrity regressions remain green.

The audit never auto-promotes. Even a fully green validation summary returns only `ELIGIBLE_FOR_CONTROLLED_PROMOTION`, after which a separate reviewed authority-handoff phase would be required.

## Production decision

For now:

- `four_hour_operational.AUTHORITY_MODE` remains `SHADOW_EVIDENCE_ONLY`;
- Phase-14F operational proxy remains the existing production comparison/authority path;
- no tier, score, capital, routing, dedup or Discord change is made in R4H-2;
- no 4H research threshold is promoted into doctrine/config;
- the 30-candidate cap and 814-symbol universe remain unchanged.

## Next dependency

Proceed to **VELOCITY-1**. Its five-session/+8% three-barrier labeling work can provide the forward-outcome layer needed to connect scan-time evidence to realized outcomes. Once those labels exist, add the explicit proxy-vs-real counterfactual evaluation and revisit 4H authority in a later controlled handoff phase.

This ordering is deliberate: do not promote an evidence organ first and invent its validation afterward.
# CFR-1 — Cross-Family Confluence / Contradiction Resolver

## Objective

Define how Chart Wizard interprets simultaneous detections from the four locked bullish setup families without double-counting evidence, confusing lifecycle states, or allowing one family label to become capital authority.

The four families remain:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

CFR-1 is a **pure resolution contract plus tier-authority firewall tests**. It does not yet change production family selection. Production wiring is a separately reviewable follow-up after this contract is green.

## Doctrine

Different family labels can describe the same bullish auction from different angles.

Examples:

- a VCP can complete its final contraction near a rising SMA cradle;
- an SMA cradle can overlap a gap-fill repair zone;
- a gap-fill reclaim can become the liquidity event inside a broader break/retest continuation;
- a generic break/retest can be the execution layer of a VCP breakout.

Therefore, multiple detections are not automatically contradictory and must never be score-stacked.

The governing sequence remains:

`structure/state -> location -> liquidity/event -> reaction/acceptance -> retest -> hold -> invalidation -> target`

Sequence proof outranks pattern-label count.

## Relationship taxonomy

CFR-1 emits one relationship state:

- `NONE` — no family detected;
- `SINGLE` — one viable family;
- `CONFLUENT` — two or more admission-ready viable families describe compatible bullish evidence;
- `COMPATIBLE` — one ready primary plus at least one supporting watch-ready family;
- `AMBIGUOUS` — multiple viable families are detected but readiness is not resolved cleanly;
- `CONTRADICTORY` — a viable family coexists with at least one failed sibling family;
- `ALL_FAILED` — all detected families have failed their own lifecycle.

## Primary-family hierarchy

The resolver does not simply choose the highest family score.

Primary selection prioritizes:

1. `entry_structure_valid`;
2. `admission_ready`;
3. `watch_ready`;
4. path quality;
5. explicit invalidation/target/R:R geometry;
6. family score;
7. deterministic family order only as a final tie-breaker.

This prevents an unfinished 97-point pattern label from displacing a lower-scored setup whose retest/hold lifecycle is actually complete.

## No score stacking

`score_stacking_allowed = false` is a hard CFR-1 contract.

Two 90-point family detections do not create a 180-point setup, a bonus tier, or automatic SNIPE permission. Confluence can improve context and confidence interpretation later, but it cannot bypass the existing execution gates.

## Conflict scope

A sibling-family failure can be `LOCAL` or `SHARED`.

### Local conflict

A local failure belongs to that setup's own geometry/lifecycle and does not automatically invalidate another coherent family.

Examples:

- `ACCEPTED_BELOW_GAP_BOUNDARY` may invalidate the bullish gap-fill model while a separate SMA cradle remains structurally valid;
- `ACCEPTED_BELOW_VALUE_POCKET` may invalidate the cradle model without automatically invalidating a separate VCP unless common structure is also lost.

CFR-1 therefore preserves a valid primary family through a local sibling failure.

### Shared conflict

Shared failures are evidence that must remain visible to the common sovereign gates.

Current shared codes include:

- `RETEST_FAILED`;
- `OVERHEAD_BLOCKED`;
- bad/stale/insufficient data;
- hostile value alignment.

CFR-1 diagnoses shared scope but does not itself own the trade rejection. The existing prefilter/tiering gates remain the authority.

## Capital firewall

The resolver explicitly returns:

- `capital_authority = false`;
- `score_stacking_allowed = false`.

It does not return a final tier, Discord route, safe-for-alert flag, or capital action.

Tier-contract regression tests prove:

1. `CONFLUENT` metadata cannot upgrade a STARTER to SNIPE;
2. a local failed sibling cannot downgrade an otherwise valid execution by metadata alone;
3. even shared-conflict metadata is diagnostic only;
4. an existing active common veto still forces the normal deterministic downgrade/WAIT path;
5. identical active tiering inputs produce identical tier/capital output whether CFR metadata is attached or not.

## Reconciliation helper

`reconcile_compiled_evidence()` deep-copies an SFC-1 evidence object, runs CFR-1, and rewrites only the **top-level summary** to the resolved primary family.

The underlying per-family objects are not mutated.

This allows the next wiring phase to consume a coherent primary family while preserving every raw family reading for audit.

## Next wiring phase

After CFR-1 is green, the follow-up production wiring should:

1. reconcile `setup_family_evidence` before SFC-2 family admission arbitration;
2. ensure GPT-5.6 receives the resolved relationship, conflict scope, primary and secondary family context;
3. preserve all original family objects in the prompt/audit ledger;
4. prevent confluence from increasing `admission_rank_score` through score addition;
5. preserve valid primary admission through local sibling failure;
6. leave shared/common blockers in the existing active veto ledger;
7. keep final tiering/ladder/seal sovereign;
8. keep real 4H shadow-only;
9. keep the deep-analysis cap at 30 pending CAP-40.

## 30 vs 40 boundary

CFR-1 does not alter capacity.

Current maximum GPT-5.6 deep-analysis candidates: **30 per scan**.

The proposed 40-candidate ceiling remains deferred until the family-aware ranking stack, including cross-family resolution, is production-green and the ranks 31-40 shadow population can be evaluated for genuine incremental opportunity recall, scan-duration headroom, and API cost/rate impact.

# CFR-2 — Resolved-Family Production Wiring

## Objective

Put the green CFR-1 cross-family resolver into the live SFC-2 admission/model-context path while preserving the existing deterministic capital firewall.

CFR-2 does **not** add another setup family and does not loosen a trading gate. It makes the four existing family readings cooperate correctly before GPT-5.6 evaluates the candidate.

## Runtime order

The family path is now conceptually:

`SFC-1 raw family evidence -> CFR-1 reconciliation -> SFC-2A family admission -> GPT-5.6 context -> deterministic tiering / judgment / ladder / seal`

The four locked families remain:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

## Why reconciliation must happen before admission

SFC-1 originally selected the top-level primary mostly from readiness and family score. Once multiple dedicated family organs are active, that is not sufficient.

Example: a 98-score VCP may still be waiting for its breakout retest while an 84-score SMA cradle on the same ticker already has a defended retest/hold. CFR-1 correctly gives execution proof priority over unfinished pattern score.

CFR-2 ensures SFC-2 admission uses that resolved primary rather than the raw compiler primary.

## Deliberate normalization bridge

`family_admission.build_family_admission_decision()` now runs CFR reconciliation before reading the family snapshot.

The reconciliation function itself deep-copies input. The admission bridge then deliberately replaces:

`enriched['setup_family_evidence']`

with that reconciled copy.

This narrowly scoped normalization is intentional: the scheduler later passes the same enriched ticker object into the GPT-5.6 prompt path, so admission and model analysis must see the same resolved primary family.

The per-family evidence objects are preserved unchanged in the reconciled copy.

## Compiler provenance

CFR reconciliation now preserves:

- `compiler_primary_family`;
- `compiler_primary_state`;
- `compiler_primary_family_score`.

These fields record what SFC-1 selected before CFR arbitration. Reconciliation is idempotent: a second reconciliation does not overwrite that original provenance with the already-resolved primary.

## Admission laws

All SFC-2A laws remain active.

Never rescued:

- bad/empty/insufficient/stale data;
- blocked overhead;
- excessive extension;
- failed retest;
- hostile value alignment.

Conditionally superseded for **model admission only** when the resolved primary supplies explicit equivalent evidence:

- generic `no_clear_structure`;
- `mid_range_no_edge`;
- missing generic invalidation estimate;
- missing generic target;
- generic R:R estimate below floor only when resolved-family R:R independently passes the same configured floor.

## Confluence law

Confluence never stacks scores.

CFR-2 keeps the existing family ranking rule:

`resolved primary family score + at most the existing +3 entry-structure proof bonus`, capped by the configured family rank ceiling.

A second or third family never contributes additive points.

Two 90-grade family labels cannot manufacture a 180-grade setup, a SNIPE tier, or a capital authorization.

## Local sibling failure

A failed sibling family with a **local** failure does not automatically poison a distinct valid primary.

Example:

- gap-fill model accepts below its own gap boundary and fails;
- SMA cradle remains valid at a separate defended value structure.

CFR labels the relationship `CONTRADICTORY / LOCAL`, keeps the failed gap model visible, and allows the valid cradle to remain the admission primary if its own evidence passes.

## Shared/common failure

CFR may label a sibling failure `SHARED`, but it does not suppress common gate evidence.

The existing active veto/tiering stack remains sovereign. If `retest_failed`, `overhead_blocked`, hostile value, bad data, or another common blocker is active in the prefilter/tiering ledger, family admission cannot rescue it.

## GPT-5.6 context

The prompt helper now defensively reconciles family evidence even when called directly outside the normal prefilter path.

When a primary family exists, GPT-5.6 receives:

- resolved primary family;
- original compiler primary;
- resolved state and family score;
- watch/admission/entry-structure readiness;
- relationship (`SINGLE`, `CONFLUENT`, `COMPATIBLE`, `AMBIGUOUS`, `CONTRADICTORY`, `ALL_FAILED`);
- conflict scope (`NONE`, `LOCAL`, `SHARED`);
- confluence count;
- secondary families;
- failed sibling families;
- shared failure codes;
- resolver reason codes;
- explicit `score_stacking_allowed=False`;
- explicit `capital_authority=False`;
- resolved primary invalidation / target / R:R / path / blockers / soft caps / metrics.

Non-primary metrics are not mislabeled as primary evidence.

## Capital firewall

CFR-2 still cannot return or create:

- `SNIPE_IT`;
- `STARTER`;
- `NEAR_ENTRY`;
- Discord route;
- `safe_for_alert`;
- capital action.

GPT-5.6 remains the analyst/classifier. Deterministic tiering, current-acceptance checks, 1H proof, trade-location judgment, unified ladder, downgrade-only seal, invalidation/path rules, fragile-risk floor, cooldown/dedup, and Discord routing remain sovereign.

## Capacity boundary

CFR-2 keeps the maximum deep-analysis candidate count at **30 per scan**.

The user proposed 40. The engineering decision remains to defer that change until CAP-40 can measure the now-family-aware and cross-family-resolved ranks 31-40.

The later CAP-40 study must prove:

1. incremental legitimate NEAR/STARTER/SNIPE recall in ranks 31-40;
2. acceptable target/stop/time-barrier behavior;
3. full scan duration remains comfortably within the 15-minute cadence;
4. API cost/rate headroom is acceptable;
5. added candidates do not reduce signal precision.

Only then should 30 -> 40 be promoted.

## No-change contract

CFR-2 does not change:

- 814-symbol universe;
- 15-minute cadence;
- 30-candidate cap;
- legacy prefilter weights/floor;
- SNIPE/STARTER/NEAR score floors;
- R:R floors;
- fragile-risk floor;
- real-4H shadow authority;
- cooldown/dedup;
- Discord routing;
- capital authorization.

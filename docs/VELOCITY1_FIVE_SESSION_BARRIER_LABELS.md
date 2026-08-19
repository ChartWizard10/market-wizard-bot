# VELOCITY-1 — +8% / Five-Session Three-Barrier Validation

## Objective

Create the forward-outcome labels required to test Chart Wizard's research objective without turning an unvalidated velocity heuristic into a live trading gate.

The governing research question is:

> From an entry/alert anchor, did price reach **+8%** before the signal's **structural invalidation** within **five subsequent trading sessions**?

This is an evaluation target, not a guaranteed forecast.

## Why labels come before authority

The scanner needs a realistic path/velocity standard, but an arbitrary ATR or momentum cutoff could create exactly the failure we are trying to avoid: missing valid snipes because the system became analytically over-constrained.

VELOCITY-1 therefore records the geometry and the realized future outcome first. It does **not** declare a live ticker feasible/infeasible based on an invented threshold.

After chronological replay produces enough labeled examples, later calibration can determine which ex-ante velocity features actually separate successful +8%/five-session opportunities from stops/timeouts.

## Three barriers

For a long-side entry:

1. **Target barrier** = entry price × 1.08.
2. **Structural-stop barrier** = explicit `invalidation_level` from the signal/setup.
3. **Time barrier** = five subsequent Daily trading sessions.

The first terminal barrier wins.

Outcome labels:

- `TARGET_8_BEFORE_STOP`
- `STOP_BEFORE_TARGET_8`
- `TIMEOUT_5_SESSIONS`
- `AMBIGUOUS_SAME_SESSION`
- `INCOMPLETE_HORIZON`
- `INVALID_DATA`

## Entry-anchor provenance

The evaluator never pretends to know an execution fill it was not given.

Anchor priority:

1. explicit replay/execution `entry_price`;
2. alert-time `scan_price`;
3. `trigger_level` fallback;
4. raw `current_price` fallback for research snapshots.

The selected source is persisted as `entry_price_source` so studies can stratify results rather than silently mix fill assumptions.

## Same-session ambiguity

Daily OHLC cannot tell whether the +8% target or the structural stop occurred first when both fall inside the same session's high/low range.

VELOCITY-1 labels that case `AMBIGUOUS_SAME_SESSION` instead of choosing the favorable or unfavorable ordering.

This preserves chronological integrity.

## Incomplete forward history

A trace with fewer than five subsequent sessions is **not** a five-session timeout unless target/stop already resolved.

If neither price barrier has resolved and the complete five-session horizon is unavailable, the outcome is `INCOMPLETE_HORIZON`.

This prevents the most recent signals from being falsely classified as velocity failures.

## Ex-ante research snapshot

`build_velocity_research_snapshot()` records raw, non-authoritative geometry:

- entry price and source;
- +8% target price;
- structural stop;
- structural risk percentage;
- R:R to the +8% target;
- ATR and ATR percentage when available;
- number of ATRs required to reach +8%;
- mapped structural target levels;
- maximum mapped upside percentage;
- whether the currently mapped target set reaches the +8% barrier;
- overhead status;
- whether the geometry is valid enough to label later.

### No arbitrary volatility cutoff

VELOCITY-1 intentionally does **not** say, for example, "required_move_atr <= X means feasible."

That threshold must be learned/validated from chronological data, not invented.

## Structural target vs +8% research target

The +8% barrier is a research objective. It does not replace structural target mapping.

If mapped structural targets stop at +6%, VELOCITY-1 records that fact as `mapped_target_reaches_velocity_target=False`; it does not automatically reject the live trade.

Later validation can determine how strongly mapped open path should influence the velocity gate and whether different setup families need different treatment.

## Forward-outcome bridge

`to_forward_outcome_block()` emits a compact outcome record suitable for future offline validation artifacts and R4H/CAP-40 counterfactual studies.

Decisive target/stop/timeout outcomes are marked observed. `INCOMPLETE_HORIZON` and invalid data remain unobserved.

R4H-2 audit compatibility is hardened in this phase so an explicitly unobserved/incomplete VELOCITY block cannot satisfy the real-4H forward-evidence requirement.

## Capital firewall

`src/velocity_validation.py` is pure/offline and imports no live scanner, model, market-data, Discord, or network module.

Every result explicitly carries:

- `research_only=True`
- `capital_authority=False`

VELOCITY-1 does not:

- change `SNIPE_IT`, `STARTER`, `NEAR_ENTRY`, or `WAIT`;
- change admission/ranking;
- change Discord routing;
- change stop placement;
- change target mapping;
- change the 30-candidate cap;
- make API calls;
- mutate telemetry/state.

## Relationship to R4H-2

R4H-2 correctly held real 4H in shadow because outcome-linked counterfactual evidence did not yet exist.

VELOCITY-1 creates the common +8% / stop / five-session outcome label that can later be joined to scan-time real-4H vs proxy state.

That future replay is what can answer whether real 4H authority improves precision without materially damaging recall.

## Relationship to CAP-40

The candidate cap remains **30**.

After the family-aware/CFR stack and VELOCITY labels are available, ranks 31-40 can be replayed against the same three barriers. Only then can CAP-40 measure whether ten additional GPT-5.6 calls recover real opportunities rather than merely add cost/noise.

## Next phase

After VELOCITY-1 is green:

1. build a chronological replay/join path from persisted scan traces to future Daily bars;
2. attach observed VELOCITY outcomes to research validation artifacts, never live scans;
3. stratify results by final tier, setup family, family lifecycle, real-4H state, proxy-4H state, and admission rank;
4. predeclare calibration/acceptance criteria before promoting any velocity or 4H authority rule;
5. keep 30 candidates until CAP-40 is measured.

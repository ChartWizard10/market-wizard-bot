# SFC-2B — Family-Aware GPT-5.6 Candidate Admission Wiring

## Objective

Wire the green SFC-2A arbitration contract into the production scan path without allowing setup-family detection to become capital authority.

The result is a two-lane admission system:

1. **Legacy generic lane** — existing structure/FVG/OB/retest/path prefilter.
2. **Deterministic family lane** — SFC-1 evidence for the four locked bullish setup families.

Both lanes feed the same GPT-5.6 analyst boundary and then the same deterministic tiering/ladder/seal stack.

## Family evidence source

`indicators.enrich()` now calls `setup_family_compiler.compile_setup_families()` on completed Daily bars.

MBT-2 separation is preserved:

- completed Daily bars own confirmation;
- current price may inform location;
- a developing Daily candle may promote the runtime display retest from `missing` to provisional `partial`;
- the family compiler receives the **closed retest verdict**, never the provisional live contact.

This prevents an unfinished candle from creating a false family confirmation.

## Admission arbitration

`prefilter.score_ticker()` preserves the legacy 0-100 `prefilter_score` and generic veto calculation, then applies SFC-2A family arbitration.

The following ledgers are deliberately distinct:

- `original_veto_flags` — the full generic pre-arbitration audit ledger;
- `rescued_veto_flags` — generic blind spots explicitly superseded by valid family evidence;
- `veto_flags` — the **active downstream gate ledger** after arbitration;
- `effective_admission_vetoes` — explicit alias of the active ledger.

This distinction is required. If a generic blind spot is legitimately repaired for family admission but remains in the active `veto_flags`, deterministic tiering would force the candidate to WAIT before it could evaluate the fresh GPT-5.6 execution proof. Conversely, deleting the original evidence would destroy auditability.

A family rescue therefore removes only the *active status* of the explicitly superseded generic blocker. It does not erase history and it does not grant a tier.

## Capital firewall

Family admission cannot directly create `SNIPE_IT`, `STARTER`, `NEAR_ENTRY`, a Discord route, or capital action.

After admission, GPT-5.6 must still produce a coherent signal and deterministic tiering must still independently enforce the existing execution laws, including:

- structure event in the model signal;
- retest and hold requirements for capital tiers;
- clear invalidation;
- valid target path;
- R:R floor;
- non-hostile value;
- semantic bullish price geometry;
- fragile-risk protection;
- current acceptance checks;
- post-tiering chart judgment;
- unified ladder;
- downgrade-only seal;
- cooldown/dedup and final routing.

A regression test proves a family-admitted candidate whose generic blind spot was rescued can reach `STARTER` **only after** a separate downstream signal independently satisfies the existing STARTER contract.

## Ranking

The legacy `prefilter_score` is never overwritten.

A valid family can contribute a bounded `admission_rank_score` so a legitimate VCP, SMA cradle, gap-fill reversal, or family-specific break/retest state is not buried simply because the legacy scorer is biased toward already-visible generic FVG/OB structure.

Candidate ranking uses:

1. `admission_rank_score`;
2. legacy `prefilter_score` as tie-breaker;
3. stable input order thereafter.

The family rank ceiling remains 95 under current SFC-2A config. It is an admission priority, not a trade grade or probability.

## GPT-5.6 context

The production prompt now includes normalized family evidence when a primary family exists:

- primary family;
- lifecycle state;
- family score;
- watch/admission readiness;
- entry-structure-valid state;
- family invalidation;
- first target;
- family R:R;
- path status;
- blockers;
- soft caps;
- compact deterministic family metrics.

No family lines are emitted when `primary_family=NONE`.

## Compatibility aliases

Historical scheduler/telemetry names remain temporarily:

- `eligible_for_claude` mirrors `eligible_for_model`;
- `claude_candidates` is the same list object as `model_candidates`;
- `total_claude_candidates` mirrors `total_model_candidates`.

These names are schema compatibility debt only. Production provider truth remains OpenAI GPT-5.6.

## Capacity boundary — 30 vs 40

SFC-2B does **not** raise the candidate cap.

Current maximum deep-analysis candidates per scan: **30**.

The proposed 40 ceiling remains a dedicated CAP-40 decision after family-aware admission is production-green. The 30 -> 40 move adds 33.3% maximum model-call capacity, so it must be justified by measured ranks 31-40 opportunity recall, scan-duration headroom and API budget rather than intuition.

## No-change contract

SFC-2B does not change:

- 814-symbol universe;
- 15-minute cadence;
- prefilter legacy scoring weights;
- prefilter legacy score floor;
- tier score floors;
- R:R floors;
- fragile-risk floor;
- real-4H shadow authority;
- cooldown/dedup;
- Discord routing;
- final capital contracts.

## Acceptance

Do not merge SFC-2B unless the permanent Python 3.13 gate proves:

1. legacy no-family behavior remains compatible;
2. all original generic veto evidence remains auditable;
3. rescued blind spots are removed only from the active downstream veto ledger;
4. never-rescue blockers remain active and reject admission;
5. family ranking does not overwrite the legacy score;
6. candidate cap remains 30;
7. model/legacy candidate aliases match exactly;
8. GPT-5.6 receives normalized family context;
9. developing Daily contact cannot become closed family proof;
10. downstream tiering still independently controls capital.

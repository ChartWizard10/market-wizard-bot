# Current Production State

Last merged production baseline entering R4H-2: `main` at `2c2bc8fdfaf82519e7488f4b78c97643ace5d7f2` (Phase CFR-2 — production cross-family resolver wiring, on top of SFC-2B family-aware GPT-5.6 admission and the existing deterministic execution stack).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: **SHADOW_EVIDENCE_ONLY**. R4H-2 explicitly holds this boundary pending outcome-linked chronological validation.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- SFC-1 compiles normalized completed-Daily evidence for all four locked setup families.
- SFC-2A defines the pure family-admission arbitration contract.
- SFC-2B wires family-aware model admission/ranking into production while preserving common gates and downstream tier authority.
- CFR-1 defines the pure cross-family resolution contract and tier non-interference tests.
- CFR-2 wires the cross-family resolver into the production family-evidence path and GPT-5.6 context without granting capital authority.
- Scan-funnel telemetry is isolated from alert history and remains observational only.
- Production ticker loader normalizes uppercase symbols, ignores blanks/comments, deduplicates, validates format, and never fetches market data.

## AI-1 provider correction — merged

Production deep analysis is **OpenAI GPT-5.6**, not Claude.

Runtime contract:

- `OPENAI_API_KEY` authenticates the model client;
- `OPENAI_MODEL` may override the configured model;
- canonical model: `gpt-5.6`;
- OpenAI Responses API;
- strict Structured Outputs / JSON Schema at the model boundary;
- response storage disabled (`store=False`);
- GPT-5.6 remains analyst/classifier only; deterministic tiering, ladder, seal, capital and routing remain sovereign.

Some internal scheduler/telemetry field names still contain historical `claude_*` terminology for regression compatibility. Those names do **not** mean Anthropic is the production provider. Provider-neutral nomenclature is tracked as operational debt and must be migrated separately without strategy drift.

## Current production universe

Source: `config/tickers.txt`

Validated baseline before the next requested expansion: **814 unique symbols**.

The regression suite asserts exactly 814 valid symbols, zero duplicates, zero malformed symbols, stable first/last boundaries, DRAM exactly once in alphabetical position, and IBM exactly once in alphabetical position.

Any universe expansion must update expected count/boundaries intentionally in the same reviewed change.

## Current alert contract

External verdicts:

- `SNIPE_IT` -> execution-authorized/full-size eligibility state;
- `STARTER` -> reduced-size capital only;
- `NEAR_ENTRY` -> watch/no capital;
- `WAIT` -> no trade/no Discord post.

Internal ladder:

`PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS`

`SNIPER_A` and `SNIPER_A_PLUS` are both SNIPE execution states; the ladder grade preserves quality distinction. SNIPE_IT is not synonymous with a score of 100.

## Production objective

The scanner is a bullish swing-entry engine, not a scalper and not a pattern collector.

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural stop/invalidation. This is an evaluation target, never a guaranteed forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

### SFC-1 — compiler

SFC-1 provides normalized deterministic completed-Daily evidence for all four families. A family label is never capital authority.

### SFC-2A — admission arbitration

SFC-2A defines how strong family evidence may repair generic **model-admission** blind spots without bypassing common fatal gates.

Never rescued:

- bad/empty/insufficient/stale data;
- blocked overhead;
- excessive extension;
- failed retest;
- hostile value alignment.

Conditionally superseded for model admission only when explicit family evidence exists:

- generic no-clear-structure;
- generic mid-range/no-edge;
- missing generic invalidation estimate;
- missing generic target path;
- generic R:R estimate below floor when family-specific R:R independently passes the same floor.

### SFC-2B — family-aware production wiring

SFC-2B wires SFC-1/SFC-2A into the production scan path while preserving the capital firewall.

Implemented contract:

- `indicators.enrich()` compiles setup families from completed Daily bars only;
- developing Daily contact can remain provisional runtime context but cannot become family confirmation;
- legacy `prefilter_score` remains unchanged and auditable;
- strong family evidence may create a bounded `admission_rank_score` for candidate selection;
- `original_veto_flags` preserves the generic pre-arbitration ledger;
- `rescued_veto_flags` records only explicitly superseded generic blind spots;
- `veto_flags` remains the active downstream gate ledger after arbitration;
- never-rescue blockers remain active in `veto_flags`;
- `model_candidates` is the provider-neutral candidate alias while historical compatibility aliases remain;
- GPT-5.6 receives normalized family lifecycle/state/readiness/geometry/path/blocker/metric context;
- downstream deterministic tiering still independently requires structure/retest/hold/invalidation/target/R:R and every existing capital gate before a STARTER or SNIPE can survive.

### CFR-1 — cross-family resolver contract

CFR-1 is merged and production-green as a pure resolver contract.

Resolver taxonomy:

- `NONE`
- `SINGLE`
- `CONFLUENT`
- `COMPATIBLE`
- `AMBIGUOUS`
- `CONTRADICTORY`
- `ALL_FAILED`

Conflict scope is classified as `NONE`, `LOCAL`, or `SHARED`.

Core laws:

- execution proof outranks a merely higher family score;
- confluence never stacks scores;
- a local sibling-family failure does not automatically cancel a valid distinct family;
- shared/common failure information remains visible for existing sovereign gates;
- reconciliation deep-copies the compiled summary and preserves raw per-family objects;
- resolver metadata has no independent tier, capital, or Discord authority.

### CFR-2 — production resolver wiring

CFR-2 is merged and production-green.

Production evidence flow:

`completed Daily evidence -> raw SFC-1 compiler -> CFR-1 resolver -> SFC-2B admission / GPT-5.6 context -> existing deterministic execution stack`

Implemented boundary:

- `src/setup_family_runtime.py` is the package-level production facade;
- raw `src.setup_family_compiler` remains unchanged for deterministic low-level tests;
- `indicators.enrich()` receives reconciled family evidence without changing Daily confirmation law;
- resolved primary selection is execution-proof-first rather than raw-score-first;
- compact cross-family relationship/conflict context reaches GPT-5.6 through the existing resolved-primary metrics payload;
- raw SFC-1 family objects are not mutated;
- no new tier, score-stacking, routing, or capital authority is introduced.

CFR-2 merged after the permanent Python 3.13 gate completed with **2831 passed, 4 skipped**.

## R4H-2 — real 4H authority decision

### Verdict

**HOLD SHADOW. Do not promote real 4H to production authority yet.**

This is an evidence-based hold, not a rejection of the R4H-1 engine.

What is already proven:

- real 4H market bars are session-aligned and reuse the existing 60m response;
- live-vs-closed confirmation law is explicit;
- continuity holes, incomplete constituents, stale evidence and accepted failure are handled safely;
- the operational engine expresses structure, liquidity, displacement, retest, hold, invalidation and target path;
- scan-time telemetry persists compact real-4H state/location/readiness/freshness/continuity plus proxy agreement.

What is not yet proven:

- the current decision-trace contract has no forward outcome label attached to the 4H state;
- it has no proxy-vs-real counterfactual outcome result;
- the repository has no chronological out-of-sample artifact proving that real-4H authority improves precision without materially damaging opportunity recall;
- several R4H-1 constants are explicitly documented in the engine as shadow/research thresholds rather than doctrine/config authority.

Therefore proxy agreement cannot be used as a substitute for ground truth, and synthetic correctness tests cannot be treated as predictive validation.

`src/four_hour_authority_audit.py` formalizes the R4H-2 evidence contract. Before real 4H can even become eligible for controlled promotion review, a separate validation artifact must explicitly establish:

1. chronological out-of-sample validation;
2. forward outcome linkage;
3. proxy-vs-real counterfactual evaluation;
4. sample size accepted under a predeclared plan;
5. accepted regime coverage;
6. precision improved or preserved;
7. legitimate opportunity recall not materially damaged;
8. full capital-integrity regressions green.

The audit never auto-promotes. A fully green evidence package may only return `ELIGIBLE_FOR_CONTROLLED_PROMOTION`; an explicit reviewed handoff would still be required.

The natural dependency is VELOCITY-1: its five-session/+8% three-barrier labels provide the forward-outcome layer needed to perform the later counterfactual 4H authority study.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The preferred next ceiling is **40 only if measured evidence proves it adds recall without damaging cadence/cost**.

A move from 30 to 40 is a 33.3% increase in maximum model calls. The scanner records near-cut ranks 31-60 without paying for deep analysis, so the decision can be measured rather than guessed.

CAP-40 acceptance sequence:

1. keep GPT-5.6 runtime green;
2. use the production family-aware/resolved ranking stack;
3. replay/inspect ranks 31-40 for legitimate missed NEAR/STARTER/SNIPE opportunities;
4. measure target/stop/time-barrier outcomes once labels are available;
5. verify worst-case scan duration remains comfortably inside the 15-minute cadence;
6. verify API rate/cost budget is acceptable;
7. raise to 40 only if incremental opportunity capture is real.

Do not use a larger model-call cap to compensate for weak candidate ranking.

## Next production sequence

1. Merge R4H-2 evidence decision with real 4H remaining shadow.
2. VELOCITY-1: five-session/+8% feasibility layer and three-barrier validation labels.
3. R4H authority revisit: use outcome-linked proxy-vs-real counterfactual validation before any controlled handoff.
4. CAP-40: measured 30-vs-40 capacity study and, if proven, controlled cap increase.
5. Final requested universe expansion in its own reviewed PR.
6. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains `SHADOW_EVIDENCE_ONLY` until forward outcome evidence explicitly clears a later authority handoff;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- cross-family confluence may not stack family scores;
- a resolver may not become a tier/capital/routing organ;
- proxy agreement is not ground truth and cannot by itself justify 4H authority;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
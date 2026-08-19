# Current Production State

Last merged production baseline entering CFR-2: `main` at `26e3a3ddf288e8559485c6bc31cb10c095401226` (Phase CFR-1 — pure cross-family confluence/contradiction resolver contract, on top of production-green SFC-2B family-aware admission wiring and OpenAI GPT-5.6 AI-1 runtime).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: SHADOW/EVIDENCE ONLY. Do not silently promote it.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- Phase SFC-1 compiles normalized completed-Daily evidence for all four locked setup families.
- Phase SFC-2A defines the pure family-admission arbitration contract.
- Phase SFC-2B wires family-aware model admission/ranking into production while preserving common gates and downstream tier authority.
- Phase CFR-1 defines the pure cross-family resolution contract and tier non-interference tests.
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
- GPT-5.6 receives normalized primary-family lifecycle/state/readiness/geometry/path/blocker/metric context;
- downstream deterministic tiering still independently requires structure/retest/hold/invalidation/target/R:R and every existing capital gate before a STARTER or SNIPE can survive.

This solves a critical integration trap: a family candidate may be worth GPT-5.6 analysis even when the generic scorer cannot express its structure, but a rescued generic blocker must not remain active and mechanically force WAIT before downstream execution proof is evaluated. The original generic evidence remains preserved for audit rather than deleted.

### CFR-1 — cross-family resolver contract

CFR-1 is merged and production-green as a **pure contract**. It does not by itself alter the runtime family evidence path.

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

Tier-contract regressions prove confluence cannot upgrade STARTER to SNIPE, local sibling failure metadata cannot independently downgrade a valid execution, resolver metadata alone cannot alter tier output, and active common vetoes remain sovereign.

### CFR-2 — production resolver wiring

CFR-2 is the current branch phase.

Target production evidence flow:

`completed Daily evidence -> raw SFC-1 compiler -> CFR-1 resolver -> SFC-2B admission / GPT-5.6 context -> existing deterministic execution stack`

CFR-2 implementation boundary:

- `src/setup_family_runtime.py` is the package-level production facade;
- raw `src.setup_family_compiler` remains unchanged for deterministic low-level tests;
- package-level `from src import setup_family_compiler` resolves through the CFR-2 facade so `indicators.enrich()` receives reconciled evidence without changing Daily confirmation law;
- resolved primary selection is execution-proof-first rather than raw-score-first;
- cross-family relationship/conflict context is projected into a namespaced `cross_family_resolution` object inside the deep-copied resolved primary metrics, which the existing GPT-5.6 prompt already serializes;
- raw SFC-1 family objects are not mutated;
- no new tier, score-stacking, routing, or capital authority is introduced.

CFR-2 must merge only after the permanent Python 3.13 production gate proves all legacy regressions plus its production-wiring tests.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 only if measured evidence proves it adds recall without damaging cadence/cost**.

A move from 30 to 40 is a 33.3% increase in maximum model calls. The scanner records near-cut ranks 31-60 without paying for deep analysis, so the decision can be measured rather than guessed.

CAP-40 acceptance sequence:

1. keep GPT-5.6 runtime green;
2. complete and merge the family-aware stack through CFR-2;
3. replay/inspect resolved family-aware ranks 31-40 for legitimate missed NEAR/STARTER/SNIPE opportunities;
4. measure target/stop/time-barrier outcomes where labels are available;
5. verify worst-case scan duration remains comfortably inside the 15-minute cadence;
6. verify API rate/cost budget is acceptable;
7. raise to 40 only if incremental opportunity capture is real.

Do not use a larger model-call cap to compensate for weak candidate ranking.

## Next production sequence

1. CFR-2: complete and merge production cross-family resolver wiring.
2. R4H-2: evidence-based decision on promoting real 4H from shadow to production authority.
3. VELOCITY-1: five-session/+8% feasibility layer and three-barrier validation labels.
4. CAP-40: measured 30-vs-40 capacity study and, if proven, controlled cap increase.
5. Final requested universe expansion in its own reviewed PR.
6. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains shadow until R4H-2 is explicitly proven;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no setup-family phase may casually change universe membership;
- cross-family confluence may not stack family scores;
- a resolver may not become a tier/capital/routing organ;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
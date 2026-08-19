# Current Production State

Last merged production baseline entering SFC-2B: `main` at `744cd38f2fda060c1eb9b4f1bb344500ff78bee6` (Phase SFC-2A — setup-family admission arbitration contract, on top of OpenAI GPT-5.6 AI-1 runtime).

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

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 deep-analysis candidates per scan**.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 only if measured evidence proves it adds recall without damaging cadence/cost**.

A move from 30 to 40 is a 33.3% increase in maximum model calls. The scanner records near-cut ranks 31-60 without paying for deep analysis, so the decision can be measured rather than guessed.

CAP-40 acceptance sequence:

1. keep GPT-5.6 runtime green;
2. complete and merge SFC-2 family-aware admission;
3. replay/inspect family-aware ranks 31-40 for legitimate missed NEAR/STARTER/SNIPE opportunities;
4. measure target/stop/time-barrier outcomes where labels are available;
5. verify worst-case scan duration remains comfortably inside the 15-minute cadence;
6. verify API rate/cost budget is acceptable;
7. raise to 40 only if incremental opportunity capture is real.

Do not use a larger model-call cap to compensate for weak candidate ranking.

## Next production sequence

1. Merge SFC-2B only after the permanent production gate is green.
2. Cross-family contradiction resolver and tier contract tests.
3. R4H-2: evidence-based decision on promoting real 4H from shadow to production authority.
4. VELOCITY-1: five-session/+8% feasibility layer and three-barrier validation labels.
5. CAP-40: measured 30-vs-40 capacity study and, if proven, controlled cap increase.
6. Final requested universe expansion in its own reviewed PR.
7. Chronological replay/out-of-sample validation and Railway observation.

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
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
# Current Production State

Last merged production baseline entering CFR-2: `main` at `26e3a3ddf288e8559485c6bc31cb10c095401226` (CFR-1 cross-family resolver contract, on top of SFC-2B family-aware OpenAI GPT-5.6 admission).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: **SHADOW / EVIDENCE ONLY**. Do not silently promote it.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- SFC-1 compiles deterministic completed-Daily evidence for all four locked setup families.
- SFC-2A defines family-admission arbitration.
- SFC-2B wires family-aware GPT-5.6 candidate admission while preserving common gates.
- CFR-1 defines cross-family confluence/contradiction resolution and tier-authority firewalls.
- Scan-funnel telemetry is isolated from alert history and remains observational only.
- Production ticker loader normalizes uppercase symbols, ignores blanks/comments, deduplicates, validates format, and never fetches market data.

## Production model truth

Production deep analysis is **OpenAI GPT-5.6**, not Claude.

Runtime contract:

- `OPENAI_API_KEY` authenticates the model client;
- `OPENAI_MODEL` may override the configured model;
- canonical model: `gpt-5.6`;
- OpenAI Responses API;
- strict Structured Outputs / JSON Schema at the model boundary;
- response storage disabled (`store=False`);
- GPT-5.6 is analyst/classifier only; deterministic tiering, ladder, seal, capital and routing remain sovereign.

Some internal scheduler/telemetry names still contain historical `claude_*` terminology for regression compatibility. Those names are compatibility debt, not provider truth.

## Current production universe

Source: `config/tickers.txt`

Validated baseline before the requested future expansion: **814 unique symbols**.

The regression suite protects exact count, uniqueness, symbol format, stable boundaries, and named universe invariants such as DRAM/IBM membership.

Any universe expansion must be isolated in its own reviewed change.

## Current alert contract

External verdicts:

- `SNIPE_IT` -> execution-authorized/full-size eligibility state;
- `STARTER` -> reduced-size capital only;
- `NEAR_ENTRY` -> watch/no capital;
- `WAIT` -> no trade/no Discord post.

Internal ladder:

`PASS -> WATCH_C -> STARTER_B -> STARTER_A -> SNIPER_A -> SNIPER_A_PLUS`

`SNIPER_A` and `SNIPER_A_PLUS` are both SNIPE execution states; the ladder preserves quality distinction. SNIPE_IT is not synonymous with a score of 100.

## Production objective

Chart Wizard is a bullish swing-entry engine, not a scalper and not a pattern collector.

Research objective: identify entries with a realistic structural/volatility path to approximately +8% within five trading sessions, subject to structural invalidation. This is an evaluation target, never a guaranteed forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

The common execution law remains sequence-first:

`structure/state -> location -> liquidity/event -> reaction/acceptance -> retest -> hold -> invalidation -> target`

A setup-family label never grants capital by itself.

## SFC-2 family-aware admission

Family evidence may repair generic **model-admission** blind spots while the common fatal gates remain sovereign.

Never rescued:

- bad/empty/insufficient/stale data;
- blocked overhead;
- excessive extension;
- failed retest;
- hostile value alignment.

Conditionally superseded for model admission only when explicit family evidence supplies the equivalent geometry:

- generic no-clear-structure;
- generic mid-range/no-edge;
- missing generic invalidation estimate;
- missing generic target path;
- generic R:R estimate below floor only when family-specific R:R independently passes the same floor.

The legacy `prefilter_score` is never overwritten. Family-aware candidate priority uses a separate bounded `admission_rank_score`.

## CFR-1 cross-family resolution

CFR-1 resolves simultaneous family detections using:

1. entry-structure validity;
2. admission readiness;
3. watch readiness;
4. path quality;
5. explicit invalidation/target/R:R geometry;
6. family score;
7. deterministic family order only as final tie-breaker.

Relationship taxonomy:

- `NONE`
- `SINGLE`
- `CONFLUENT`
- `COMPATIBLE`
- `AMBIGUOUS`
- `CONTRADICTORY`
- `ALL_FAILED`

Critical laws:

- confluence never stacks family scores;
- local sibling-family failure does not automatically cancel a distinct valid family;
- shared/common failures remain owned by common gates;
- resolver metadata has no tier/capital authority.

## CFR-2 resolved-family production wiring

CFR-2 connects CFR-1 to the live SFC-2 admission/model-context path.

Implemented contract:

- family admission reconciles the raw SFC evidence before selecting its primary;
- compiler-primary provenance is preserved under `compiler_primary_*` fields;
- reconciliation is idempotent;
- all raw per-family evidence objects remain unchanged in the reconciled copy;
- the reconciled evidence is deliberately attached to the same enriched ticker object so admission and the later GPT-5.6 call consume the same primary family;
- an unfinished higher-score family cannot displace a lower-score family with stronger retest/hold proof;
- confluence contributes **zero additive score bonus**;
- local failed siblings remain visible without poisoning a valid primary;
- shared/common active vetoes remain non-rescuable;
- GPT-5.6 receives resolved primary, compiler primary, relationship, conflict scope, secondary families, failed siblings, shared failure codes, confluence count, resolver reasons and explicit no-score-stacking/no-capital-authority flags;
- deterministic tiering/1H proof/trade-location judgment/ladder/seal remain sovereign over STARTER/SNIPE capital.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 GPT-5.6 deep-analysis candidates per scan**.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 only if measured evidence proves incremental opportunity recall without damaging cadence, API budget, or signal precision**.

A move from 30 to 40 increases maximum model calls by 33.3%. Existing near-cut telemetry already records ranks 31-60, so CAP-40 can evaluate ranks 31-40 rather than guessing.

CAP-40 must measure:

1. legitimate incremental NEAR/STARTER/SNIPE opportunity recall in ranks 31-40;
2. target/stop/five-session outcomes where labels are available;
3. worst-case scan duration versus the 15-minute cadence;
4. API rate/cost headroom;
5. precision impact.

Do not use a larger candidate cap to compensate for weak ranking.

## Next production sequence

1. Merge CFR-2 only after the permanent production gate is green.
2. **R4H-2**: evidence-based decision on promoting real session-aligned 4H from shadow to production authority.
3. **VELOCITY-1**: five-session/+8% feasibility layer and three-barrier validation labels.
4. **CAP-40**: measured 30-vs-40 capacity study; raise only if proven beneficial.
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
- no family/confluence phase may stack pattern scores into capital permission;
- no setup-family phase may casually change universe membership;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
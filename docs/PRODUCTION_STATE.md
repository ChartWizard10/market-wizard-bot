# Current Production State

Last merged production baseline entering VELOCITY-1: `main` at `c85bc622cd7766f17988080d379b406c8cb81370` (R4H-2 evidence decision — HOLD real 4H in shadow, on top of CFR-2/SFC-2B OpenAI GPT-5.6 family-aware admission).

Update this file whenever architecture, authority, runtime contracts, universe, or next-phase priority changes.

## Production-green foundations

- Python runtime contract: `.python-version` = 3.13.13.
- Permanent GitHub Actions production gate: compile + full `pytest` on pull requests/pushes to main.
- R4H-2 merge gate: **2843 passed, 4 skipped**.
- Daily market-bar truth: completed-vs-developing evidence split is enforced.
- 1H market-bar truth: closed/live evidence is explicitly resolved.
- Real 4H aggregation: session-aligned evidence exists and reuses the existing 60m provider response.
- Real 4H authority: **SHADOW / EVIDENCE ONLY** after the explicit R4H-2 decision. Do not silently promote it.
- Higher-timeframe monthly/weekly context exists and is evidence-only under current config.
- SNIPE gate audit, unified ladder, downgrade-only consistency seal, final-state reconciliation, and calibration are installed.
- Final-tier dedup reconciliation is installed: cooldown/tier-improvement sees the final executable tier.
- Autoscan and manual `!analyze` share the same post-tiering candidate-judgment organ.
- SFC-1 compiles deterministic completed-Daily evidence for all four locked setup families.
- SFC-2A defines family-admission arbitration.
- SFC-2B wires family-aware GPT-5.6 candidate admission while preserving common gates.
- CFR-1 defines cross-family confluence/contradiction resolution and tier-authority firewalls.
- CFR-2 wires resolved family context into the production admission/model path.
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

Research objective: identify entries with a realistic structural/volatility path to approximately **+8% within five trading sessions**, subject to structural invalidation. This is an evaluation target, never a guaranteed forecast.

## Locked setup families

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

The common execution law remains sequence-first:

`structure/state -> location -> liquidity/event -> reaction/acceptance -> retest -> hold -> invalidation -> target`

A setup-family label never grants capital by itself.

## SFC-2 family-aware admission

Family evidence may repair generic **model-admission** blind spots while common fatal gates remain sovereign.

Never rescued:

- bad/empty/insufficient/stale data;
- blocked overhead;
- excessive extension;
- failed retest;
- hostile value alignment.

Conditionally superseded for model admission only when explicit family evidence supplies equivalent geometry:

- generic no-clear-structure;
- generic mid-range/no-edge;
- missing generic invalidation estimate;
- missing generic target path;
- generic R:R estimate below floor only when family-specific R:R independently passes the same floor.

The legacy `prefilter_score` is never overwritten. Family-aware candidate priority uses a separate bounded `admission_rank_score`.

## CFR cross-family resolution

Cross-family resolution prioritizes actual execution proof over an unfinished high family score and classifies relationships as:

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

## R4H-2 real-4H authority decision

R4H-1 already provides truthful real session-aligned 4H structure/location/retest/hold evidence and proxy comparison at zero extra market-data fetch cost.

R4H-2 audited whether that evidence was sufficient to promote real 4H from shadow into production authority.

Decision: **HOLD_SHADOW**.

Reason:

- synthetic unit tests prove engineering semantics, not predictive edge;
- proxy agreement is diagnostic, not a validation target because the proxy itself may be wrong;
- no qualifying outcome-linked chronological real-vs-proxy counterfactual sample was present;
- no predeclared out-of-sample precision/recall acceptance artifact existed.

Therefore real 4H remains shadow/evidence-only. Production tiering/ladder/seal behavior was not changed.

R4H-2 requires future authority evidence to include chronological out-of-sample outcome linkage, proxy-vs-real counterfactuals, accepted sample/market-condition coverage, precision preservation/improvement, no material recall damage, and green capital-integrity regressions.

## VELOCITY-1 — +8% / five-session validation contract

VELOCITY-1 creates the forward labels needed to test the scanner's velocity objective before adding any live velocity gate.

Three barriers:

1. **target** = entry/alert anchor × 1.08;
2. **structural stop** = explicit signal invalidation;
3. **deadline** = five subsequent trading sessions.

Terminal labels:

- `TARGET_8_BEFORE_STOP`
- `STOP_BEFORE_TARGET_8`
- `TIMEOUT_5_SESSIONS`
- `AMBIGUOUS_SAME_SESSION`
- `INCOMPLETE_HORIZON`
- `INVALID_DATA`

Key integrity laws:

- Daily same-session target+stop touch is ambiguous; intraday ordering is never guessed.
- Fewer than five available future sessions cannot be called a timeout unless target/stop already resolved.
- Entry-price source is explicit and auditable: execution/replay entry -> scan price -> trigger fallback -> current-price fallback.
- Missing structural invalidation is not reconstructed from ATR or hope.
- The +8% research target does not replace structural target mapping.
- Raw ATR/path/R:R geometry is recorded, but **no arbitrary velocity-feasibility cutoff is introduced in VELOCITY-1**.
- Every VELOCITY result is `research_only=True` and `capital_authority=False`.
- The module is pure/offline: no model, Discord, market-data or network calls and no live scanner mutation.

VELOCITY-1 emits a compact `forward_outcome` block for later R4H/CAP-40 counterfactual studies. R4H evidence auditing is hardened so an explicitly unobserved/incomplete forward horizon cannot satisfy the forward-outcome requirement.

## Candidate-cap decision: 30 vs 40

Current production cap remains **30 GPT-5.6 deep-analysis candidates per scan**.

The operator proposed 40 and delegated the engineering decision. The preferred next ceiling is **40 only if measured evidence proves incremental opportunity recall without damaging cadence, API budget, or signal precision**.

A move from 30 to 40 increases maximum model calls by 33.3%. Existing near-cut telemetry already records ranks 31-60, so CAP-40 can evaluate ranks 31-40 rather than guessing.

CAP-40 must measure:

1. legitimate incremental NEAR/STARTER/SNIPE opportunity recall in ranks 31-40;
2. the same +8%/structural-stop/five-session barrier outcomes;
3. worst-case scan duration versus the 15-minute cadence;
4. API rate/cost headroom;
5. precision impact.

Do not use a larger candidate cap to compensate for weak ranking.

## Next production sequence

1. Merge VELOCITY-1 only after the permanent production gate is green.
2. Build a chronological replay/join path from persisted scan traces to future Daily bars and attach observed VELOCITY outcomes to a separate research validation artifact.
3. Use those labels for R4H real-vs-proxy counterfactual validation and setup/tier calibration; do not leak future outcomes into live scans.
4. Run **CAP-40** using family-aware/CFR-resolved ranks 31-40 and the same barrier labels; raise to 40 only if proven beneficial and operationally safe.
5. Final requested universe expansion in its own reviewed PR.
6. Chronological replay/out-of-sample validation and Railway observation.

## Things that must NOT drift

- scan cadence remains 15 minutes unless explicitly changed in a capacity phase;
- Daily/Weekly/4H/1H jurisdiction remains intact;
- real 4H remains shadow until a future governed authority promotion is explicitly proven;
- score cannot override failed execution gates;
- WAIT never posts;
- telemetry remains observational;
- future outcomes never feed the live scan path;
- no disabled indicator may be reintroduced;
- no family organ may treat a level touch as an entry;
- no family/confluence phase may stack pattern scores into capital permission;
- no setup-family/velocity phase may casually change universe membership;
- model-provider work may not silently change strategy thresholds, capital rules, routing, cooldown, or universe.

## Operational debt tracked but not blocking the next phase

- `datetime.utcnow()` deprecation warnings under Python 3.13 should be migrated deliberately in a dedicated timestamp phase.
- Root historical artifacts (`bot.py`, legacy PDFs) are not the governing runtime path; do not modify/delete them casually without a dedicated cleanup review.
- Historical `claude_*` internal naming should be migrated to provider-neutral names without changing behavior.

## Stop condition before universe expansion

Do not request the new ticker list until the pre-universe production checkpoint is reached. At that checkpoint, stop and explicitly ask for the ticker list.
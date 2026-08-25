# Phase 92-0 — Market Wizard Measurement Constitution

Status: PRE-PRODUCTION CONTRACT  
Authority: measurement/audit only  
Strategy authority: ZERO  
Capital authority: ZERO  
Routing authority: ZERO  
Tier authority: ZERO  

## 1. Objective

Market Wizard must be able to prove what happened after it spoke without rewriting what it knew when it spoke.

Phase 92 creates the permanent evidence architecture required to move the product from a strong production scanner toward a commercially auditable signal service. The system must measure published-alert behavior, lifecycle promotion, risk-path realism, and scanner shyness without contaminating live strategy authority.

This phase does not exist to manufacture a favorable win rate. It exists so scanner performance, missed-opportunity behavior, tier calibration, and operational reliability can be audited honestly.

## 2. Governing doctrine

The measurement system inherits, but never changes, the production doctrine:

`Structure -> Liquidity -> Displacement -> Retest -> Hold -> Invalidation -> Target`

Execution sequence:

`Break -> Acceptance -> Retest -> Hold`

Timeframe jurisdiction remains sovereign:

- Weekly = campaign context.
- Daily = swing permission.
- 4H = operational location, repair state, and entry neighborhood.
- 1H = trigger proof.
- Lower timeframes may refine execution only when explicitly supported; they cannot create swing authority.

Measurement is downstream from judgment. It may observe what tiering, evidence organs, capital policy, and routing decided. It may never change those decisions.

## 3. Core measurement law

**The scan-time record is immutable. Future information may append an outcome, but may never rewrite the original evidence.**

At minimum, every measured published alert must preserve:

1. what the scanner knew;
2. when it knew it;
3. what it said;
4. what capital permission it granted;
5. which proof was present or missing;
6. what happened afterward;
7. which software/config/prompt version produced the decision.

No future candle, target hit, invalidation hit, later tier promotion, operator opinion, or manual chart review may modify the original scan-time truth.

## 4. Definitions

### 4.1 Published alert

A signal is a **published alert** only when the production Discord delivery path reports successful delivery.

A model result, tiering result, dedup candidate, suppressed duplicate, failed Discord send, or internal trace is not a published customer signal.

### 4.2 Signal event

A **signal event** is one immutable published-alert record. Re-alerts and promotions may create additional signal events, but they are not automatically independent trades.

### 4.3 Commercial cohort

The primary commercial cohort is:

`origin = scheduled_scan AND discord_delivery = sent`

Manual `!scan` and `!analyze` observations remain auditable but must be reported separately because operator selection can introduce selection bias.

### 4.4 Capital-authorized event

- `SNIPE_IT` = full-quality capital authorization according to production policy.
- `STARTER` = reduced-size capital authorization.
- `NEAR_ENTRY` = watch/no capital.
- `WAIT` = no trade/no published alert under the normal routing contract.

### 4.5 Outcome

An outcome is a future, chronological market observation attached to an immutable event. Outcome data is evidence; it is never tier authority.

### 4.6 Ambiguous outcome

If the available OHLC granularity cannot establish whether target or invalidation occurred first, the outcome is `AMBIGUOUS`, not a win or loss.

### 4.7 Pending outcome

If the required future horizon has not matured or data is incomplete, the outcome is `PENDING` or `UNKNOWN`, never a loss, win, zero, or assumed result.

## 5. Evidence architecture

Phase 92 uses four separate layers:

```text
LIVE SCANNER
    |
    | successful Discord delivery
    v
1. PUBLISHED ALERT EVENT LEDGER
    |
    | immutable scan-time truth
    v
2. FUTURE OUTCOME LEDGER
    |
    | chronological future bars only
    v
3. TRAJECTORY / PROMOTION LEDGER
    |
    | tier progression and blocker resolution
    v
4. PERFORMANCE / CALIBRATION REPORTS
```

Layers 1–3 are evidence stores. Layer 4 is interpretation and must always be reproducible from the evidence stores.

## 6. Published Alert Event Ledger contract

The permanent commercial event ledger must be distinct from the operational dedup/cooldown state store and distinct from the research archive.

Recommended storage root:

```text
.state/signal_outcomes/
    events/YYYY-MM-DD.jsonl
    outcomes/YYYY-MM-DD.jsonl
    health/
```

The exact file layout may be changed during implementation only if these invariants remain true:

- append-oriented;
- durable-volume compatible;
- date partitioned or equivalently bounded;
- independently recoverable;
- does not control scanner judgment;
- does not share destructive retention with dedup state;
- does not silently rewrite prior records.

### 6.1 Required event identity

Every event must have a stable unique `alert_id` and preserve:

- `schema_version`
- `measurement_version`
- `alert_id`
- `scan_id`
- `ticker`
- `origin`
- `scan_started_at`
- `market_snapshot_at` when available
- `sent_at`
- `session_date`
- `dedup_reason`

### 6.2 Required production provenance

Every event must preserve enough provenance to define a reproducible strategy cohort:

- git/build commit SHA when available;
- production model/provider identity;
- config fingerprint;
- prompt fingerprint;
- universe fingerprint;
- measurement schema version.

A material strategy change must create a distinguishable cohort. Historical records must never be silently grouped across incompatible strategy versions.

### 6.3 Required judgment truth

Persist the actual final scan-time judgment, not a recomputation:

- `final_tier`
- `ladder_basket`
- `original_claude_tier`
- `score`
- `raw_score` when available
- `capital_action`
- `final_discord_channel`
- `safe_for_alert`
- suppression/dedup reason applicable to the event

### 6.4 Required trade geometry

Persist actual scan-time geometry:

- `scan_price`
- `trigger_level`
- `invalidation_level`
- `invalidation_condition`
- `targets`
- `risk_reward`
- `risk_distance`
- `risk_distance_pct`
- `risk_realism_state`
- `overhead_status`

Missing geometry remains missing. The ledger must never invent a target, stop, trigger, or R:R.

### 6.5 Required setup and proof state

Persist enough evidence to audit setup quality separately from entry quality:

- setup family / entry archetype when available;
- structure event;
- trend state;
- zone type;
- Daily permission state;
- 4H operational state and authority mode;
- 1H trigger state;
- retest truth;
- hold truth;
- candle truth;
- closed/live bar context;
- hard blockers;
- soft caps;
- why this tier;
- why not the tier above;
- promotion gate;
- next required proof.

The authoritative organ owns its field. No free-form narrative may overwrite structured evidence.

## 7. Independence and duplicate law

Raw Discord events and independent trading opportunities are not the same statistical unit.

Phase 92 must preserve three views:

### 7.1 Raw alert-event view

Every successfully delivered Discord signal is retained.

### 7.2 Tier-transition view

For a ticker/session lifecycle, the first occurrence of each distinct public tier is a transition event used to measure promotion timing and progression.

### 7.3 Capital-decision view

The first capital-authorized decision for a ticker/session lifecycle is the primary independent commercial trade-decision unit, subject to the final implementation's explicit lifecycle-key contract.

Cooldown re-alerts, unchanged duplicate events, and repeated manual requests must not inflate headline trade counts.

The raw event record is never deleted merely because it is not an independent observation.

## 8. Origin separation law

Headline commercial statistics must not mix scheduled and operator-selected samples.

Minimum origin states:

- `scheduled_scan`
- `manual_scan`
- `manual_analyze`
- `legacy_import`

Primary forward commercial reporting uses scheduled scans unless a report explicitly states otherwise.

Legacy data may be backfilled for diagnostics, but it must remain visibly `LEGACY` and must never silently contaminate the post-Phase-92 forward cohort.

## 9. Future-outcome chronology law

Future outcome evaluation must be strictly chronological and leak-free.

The implementation should reuse the already-proven principles from the pure backtest and VELOCITY outcome-linking infrastructure rather than creating a competing definition of future truth.

Minimum horizons:

### H1

First fully completed 1H candle after the event's publication time, subject to market-session chronology.

### H4

First four fully completed 1H candles after publication, or an explicitly equivalent completed 4H window with deterministic session handling.

### D1

First completed Daily session strictly after the alert session.

### D5

First five completed Daily sessions strictly after the alert session.

The unfinished alert-day Daily candle cannot become future confirmation merely because the outcome process runs later.

## 10. Outcome record contract

Each matured horizon should preserve, where data permits:

- `alert_id`
- horizon identity;
- reference price and source;
- horizon close;
- return percentage;
- MFE and MFE percentage;
- MAE and MAE percentage;
- MFE in R and MAE in R when structural risk is valid;
- trigger reached?;
- T1 reached?;
- T2 reached?;
- invalidation reached?;
- first terminal event;
- time/bars to target;
- time/bars to invalidation;
- number of bars used;
- normalized bar timestamps;
- normalized bar-set fingerprint/hash if implemented;
- data source/provider;
- data-quality state;
- outcome status (`MATURED`, `PENDING`, `AMBIGUOUS`, `INVALID_DATA`, etc.).

If target and invalidation are touched inside the same unresolved bar, the system must not guess the intrabar order.

## 11. Tier-specific measurement semantics

### 11.1 SNIPE_IT

Measure capital-authorized execution quality:

- T1 before invalidation;
- T2 when available;
- MFE/MAE;
- realized opportunity in R;
- path efficiency;
- time to expansion;
- failure before target.

### 11.2 STARTER

Measure reduced-size participation quality plus lifecycle progression:

- all capital-path measures above;
- subsequent promotion to SNIPE_IT;
- time to promotion;
- invalidation before promotion;
- whether early reduced-size entry improved or degraded subsequent path quality.

### 11.3 NEAR_ENTRY

NEAR_ENTRY is not a trade and must not receive a conventional win/loss rate.

Measure:

- promotion to STARTER;
- promotion to SNIPE_IT;
- time to promotion;
- invalidation/failure before promotion;
- strong favorable excursion without promotion;
- blocker resolution;
- blocker persistence;
- missed-move rate under a separately defined research metric.

This cohort is the primary evidence source for determining whether scanner patience is disciplined or whether a gate creates analysis paralysis.

### 11.4 WAIT / PASS

Normal customer performance reporting does not treat WAIT/PASS as trades. Any future study of suppressed opportunities must be explicitly counterfactual/research-only.

## 12. Ladder/basket calibration law

Performance reporting must preserve public tier and internal ladder separately:

- `WATCH_C`
- `STARTER_B`
- `STARTER_A`
- `SNIPER_A`
- `SNIPER_A_PLUS`

The objective is not to force monotonic win rates. It is to test whether stronger baskets exhibit meaningfully better quality through appropriate combinations of target-first behavior, MFE/MAE, path efficiency, drawdown, and progression.

If basket ordering is not supported by forward data, Score Calibration and proof-burden attribution may be audited. The measurement layer itself may not recalibrate them.

## 13. Trajectory and blocker-resolution ledger

The system must be able to reconstruct a ticker lifecycle without rewriting earlier events.

Minimum transitions of interest:

```text
NEAR_ENTRY -> STARTER
NEAR_ENTRY -> SNIPE_IT
NEAR_ENTRY -> FAILED / INVALIDATED
STARTER -> SNIPE_IT
STARTER -> TARGET
STARTER -> FAILED / INVALIDATED
SNIPE_IT -> TARGET
SNIPE_IT -> FAILED / INVALIDATED
```

For every promotion or failure, preserve:

- source `alert_id`;
- later event `alert_id` when applicable;
- blocker at source;
- whether blocker resolved;
- proof that changed;
- elapsed market time/session count;
- target/invalidation status before promotion.

## 14. Counterfactual/shyness research firewall

Missed-opportunity research must never be mixed with published-signal performance.

Counterfactual cohorts may include:

- NEAR_ENTRY candidates;
- selected high-quality WAIT candidates;
- blocked STARTER candidates;
- blocked SNIPE candidates.

They must remain explicitly tagged:

```text
COUNTERFACTUAL_RESEARCH
NOT_A_PUBLISHED_TRADE
NO_CAPITAL_WAS_AUTHORIZED
```

A later favorable move does not retroactively create a historical trade signal.

## 15. Outcome-worker isolation

Outcome settlement must not burden or control the critical scan path.

Preferred architecture:

- scanner continues its normal market-hours cadence;
- an isolated settlement process/job evaluates unresolved published events using already-available or deliberately fetched historical bars;
- only tickers with unresolved outcomes are evaluated;
- outcome failure cannot crash scanning;
- outcome failure cannot suppress or create alerts;
- no outcome record may alter tier, capital, routing, dedup, cooldown, universe, candidate admission, or model calls.

A failed settlement attempt leaves the event pending and emits health telemetry.

## 16. Storage/durability law

The commercial outcome ledger is not the dedup state store and not the research archive.

Requirements:

- dedicated storage jurisdiction;
- durable-volume compatible;
- append-oriented event history;
- restart/redeploy persistence test;
- corruption detection;
- malformed-line isolation;
- duplicate-ID detection;
- bounded per-write behavior;
- no silent event loss;
- no silent event replacement;
- reproducible read-only reconstruction.

Commercial evidence should not inherit the research archive's 120-day deletion policy unless a separately approved export/retention policy preserves the audit record first.

## 17. Reconciliation law

For successfully published alerts, the system must be able to reconcile:

```text
Discord delivery success
    <-> published event ledger
    <-> operational alert-history record
```

A mismatch is a product-health defect, not a trading result.

Minimum health metrics:

- ledger writable;
- last event timestamp;
- last settlement timestamp;
- pending H1/H4/D1/D5 counts;
- Discord-sent event count;
- commercial-ledger event count;
- unreconciled event count;
- malformed record count;
- duplicate alert-ID count;
- durable-volume/restart check state.

## 18. Forward-cohort freeze and versioning

Outcome measurement cannot be used as an excuse for continuous micro-tuning.

Once the forward Phase-92 commercial cohort begins:

- only proven P0/P1 correctness or production-safety defects may change strategy without deliberate cohort handling;
- any material strategy change must create a new strategy cohort/version;
- threshold, risk, ladder, proof-burden, timeframe-authority, setup-admission, or real-4H-authority changes must be identifiable in the producing event;
- display-only wording fixes may remain in the same strategy cohort when they do not alter judgment, but their build commit still remains recorded.

Performance reports must expose version boundaries rather than pool incompatible regimes silently.

## 19. Reporting law

Reports are read-only and reproducible from immutable evidence.

Every headline rate must show:

- cohort definition;
- origin filter;
- strategy/build version or version range;
- sample size;
- matured/evaluable sample size;
- pending count;
- ambiguous/invalid count;
- denominator definition;
- confidence interval where a rate is displayed.

Prohibited reporting behavior:

- one unlabeled global "win rate";
- counting NEAR_ENTRY as a trade;
- counting repeated cooldown alerts as independent trades;
- mixing manual and scheduled samples without disclosure;
- dropping losses because data quality was inconvenient;
- resolving ambiguous same-bar outcomes favorably;
- treating pending observations as failures or successes;
- mixing historical legacy observations into forward Phase-92 results without an explicit legacy flag;
- changing outcome definitions after seeing the data without a new measurement version.

## 20. Phase 92 build sequence

### 92-0 — Measurement Constitution

Documentation only. Lock this contract before runtime implementation.

### 92-1A — Immutable published-alert event ledger

Add the dedicated event schema/storage path and hook it only after successful Discord delivery. No outcome calculation yet.

### 92-1B — Independence/duplicate contract

Add deterministic lifecycle/independence keys and views without deleting raw events.

### 92-1C — Pure H1/H4/D1/D5 outcome engine

Reuse proven chronological/backtest principles. Pure/read-only calculation first.

### 92-1D — Tier-specific outcome semantics

Separate SNIPE, STARTER, NEAR_ENTRY, and non-trade cohort metrics.

### 92-1E — Promotion/trajectory engine

Link later events to earlier lifecycle states without mutation.

### 92-1F — Dedicated durable storage verification

Prove restart/redeploy persistence and corruption isolation.

### 92-1G — Isolated settlement worker

Operationalize future-outcome maturation with zero scan authority.

### 92-1H — Operator performance reporting

Add read-only health/performance reporting with explicit denominators and sample warnings.

### 92-2 — Shyness counterfactual study

Measure blocked/missed opportunities as research, never published trades.

### 92-3 — Commercial evidence gate

Review live forward evidence, reliability, reconciliation, and remaining product/compliance gaps before upgrading the commercial-readiness grade.

## 21. Protected production invariants

Unless a later explicitly approved logic-changing phase says otherwise, Phase 92 measurement work must preserve:

- `raw_score`
- `final_tier`
- `score`
- `capital_action`
- `final_discord_channel`
- `safe_for_alert`
- suppression
- dedup
- cooldown
- scan cadence
- ticker universe
- Railway configuration
- requirements/dependencies unless a dedicated storage dependency is independently justified
- routing
- capital policy
- Discord wording
- Claude prompt
- model/provider routing
- candidate cap
- risk thresholds
- setup admission
- ladder rules
- SNIPE gate rules
- Daily/4H/1H authority
- real 4H shadow/authority state

Measurement code may observe these fields. It may not secretly mutate them.

## 22. Acceptance tests required across implementation phases

The complete Phase-92 program must eventually prove:

1. every successful scheduled Discord alert is captured exactly once as a raw event;
2. failed Discord sends do not become published events;
3. manual analyses are distinguishable from scheduled scans;
4. duplicate/re-alert events remain in raw history but cannot inflate independent trade counts;
5. scan-time records are immutable;
6. future data only appends outcomes;
7. H1/H4/D1/D5 chronology excludes unfinished/future leakage;
8. same-bar target/invalidation ambiguity is not guessed;
9. missing/incomplete future data stays pending/unknown;
10. MFE/MAE is reproducible;
11. target/invalidation ordering is deterministic;
12. NEAR_ENTRY is never reported as a conventional trade win/loss cohort;
13. basket and public-tier attribution remain separate;
14. strategy/build provenance is attached to every new event;
15. outcome-processing failure cannot alter scanning, tiering, capital, routing, or Discord;
16. durable storage survives controlled restart/redeploy validation;
17. sent-alert count and ledger count reconcile;
18. reports expose denominators, pending/ambiguous rows, and sample size;
19. counterfactual research remains visibly separate from customer-signal performance;
20. full production CI and compile gates remain green.

## 23. 92/100 milestone gate

The commercial-readiness grade does not become 92 merely because Phase-92 code exists.

A 92/100 review requires evidence that:

- known P1 scanner-truth defects are closed;
- scheduled published alerts are permanently and reproducibly captured;
- outcome chronology is leak-free;
- result attribution is replayable;
- performance statistics are not duplicate-inflated or selection-biased by manual requests;
- live operational reconciliation is clean;
- storage persistence is proven;
- multiple live market sessions accumulate without silent provider/ledger failures;
- real-4H remains governed by its separately predeclared authority study until that program earns a handoff;
- customer-facing/compliance packaging is reviewed separately before broad public performance claims.

Only then should the project be re-graded.

## 24. Final law

**Build the outcome system to expose the truth, not to prove the scanner right.**

If SNIPE_IT is excellent, the evidence should show it. If STARTER is too timid, the evidence should show it. If NEAR_ENTRY prevents bad trades, the evidence should show it. If a gate creates analysis paralysis, the evidence should show it. If a basket does not discriminate quality, the evidence should show it.

The scanner must tell the truth at the scan moment. The outcome system must tell the truth about what happened afterward. Neither may rewrite the other.

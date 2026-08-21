# VELOCITY-1C — Scan-Trace Observation Bridge Contract

## Objective

Define exactly which scan-time populations must receive immutable VELOCITY research observations before the scanner starts persisting those envelopes into telemetry.

VELOCITY-1C is a **pure bridge contract**. It does not yet modify live telemetry writes.

## Why this bridge is necessary

The later chronological replay and CAP-40 study require more than the current top-30 analyzed names.

Three distinct populations matter:

1. **Analyzed** — selected for GPT-5.6 and completed deterministic judgment.
2. **Model failed** — selected for deep analysis, but the model/API did not produce a valid result.
3. **Near-cut ranked but not analyzed** — eligible candidates immediately outside the 30-candidate model cap, especially ranks 31-60.

The third population is the shadow counterfactual for the user-proposed 40-candidate ceiling.

A rank-31 candidate was **not judged WAIT**. It was never analyzed. That distinction must survive into research data or CAP-40 would be biased before it starts.

## Capture policy

The bridge captures:

- `analyzed`;
- `model_failed`;
- historical compatibility `claude_failed`;
- `ranked_not_analyzed` only when the trace is inside the configured near-cut shadow window.

It does not capture every prefilter rejection or every eligible candidate outside the near-cut window in this phase. That keeps the future telemetry footprint bounded while preserving the exact population needed for 30-vs-40 analysis.

## Analysis-selection provenance

Every bridge observation contains a `selection_context` block:

- `trace_kind`;
- `deep_analysis_selected`;
- `analysis_performed`;
- `final_tier_observed`;
- `capital_authorized`.

### Analyzed

An analyzed trace preserves the actual final observed tier/capital truth.

### Model failure

A model failure records:

- selected for deep analysis = true;
- analysis performed successfully = false;
- final tier observed = false;
- observed tier = null;
- capital authorized = false.

### Rank 31-60 near-cut

A ranked-but-not-analyzed trace records:

- selected for deep analysis = false;
- analysis performed = false;
- final tier observed = false;
- observed tier = null;
- capital authorized = false.

The stage becomes `RANKED_NOT_ANALYZED`, never `WAIT`.

## Timestamp truth

Full-scan IDs already encode their UTC scan start:

`scan_YYYYMMDD_HHMMSS_<nonce>`

VELOCITY-1C converts that embedded UTC timestamp into the envelope's `observed_at` value.

For analyzed/manual observations only, a valid final-signal timestamp may be used as a fallback when the scan ID has no date.

Unanalyzed research observations fail closed if no trustworthy observation timestamp exists.

## Family projection

The bridge does **not redetect** patterns.

It projects only family/CFR fields already present in the scan-time prefilter/admission ledger:

- resolved primary family;
- compiler primary when available;
- lifecycle state;
- family score;
- watch/admission/entry-structure readiness;
- family invalidation;
- family target;
- family R:R;
- path status;
- blockers/soft caps;
- CFR relationship/conflict scope;
- secondary families;
- failed siblings;
- shared failure codes;
- resolver reasons.

This preserves the exact scan-time decision context for later replay.

## Real-4H projection

For analyzed observations, the bridge maps the current production `four_hour_real` evidence into VELOCITY-1B's `four_hour_shadow` projection.

Authority remains explicitly:

`SHADOW_ONLY`

The bridge does not promote real 4H.

## Future-data firewall

VELOCITY-1C never accepts or emits:

- future Daily bars;
- forward outcome labels;
- target-hit/stop-hit sessions;
- MFE/MAE outcome fields;
- any post-observation result.

The bridge recursively fails closed if a forbidden future-outcome key somehow reaches the constructed envelope.

Future bars join only in the offline chronological labeling phase.

## Capital firewall

Every bridge result remains:

- `research_only = true`
- `capital_authority = false`

The module has no imports from:

- scheduler;
- market-data fetchers;
- model clients;
- Discord;
- state store;
- scan telemetry writer;
- network libraries.

It cannot change the live scanner by itself.

## Candidate-cap boundary

The production deep-analysis cap remains **30**.

VELOCITY-1C is specifically designed so the later live telemetry wiring can preserve ranks 31-60 as an immutable near-cut research population. That enables CAP-40 to compare current top-30 selection against ranks 31-40 using the same +8% / structural-stop / five-session outcome contract.

No capacity change is made here.

## Next phase

After this pure bridge contract is green:

1. wire it into isolated scan telemetry for analyzed, model-failed, and near-cut traces only;
2. verify telemetry retention/disk bounds remain safe;
3. persist scan-time envelopes only — never future outcomes;
4. build an offline chronological join from persisted envelopes to subsequent Daily sessions;
5. attach VELOCITY-1A outcomes to a separate research validation artifact;
6. use that artifact for R4H and CAP-40 counterfactual decisions.

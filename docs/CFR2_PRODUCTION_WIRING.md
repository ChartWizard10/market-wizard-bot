# CFR-2 — Cross-Family Production Wiring

## Purpose

CFR-1 established a pure, tested contract for resolving simultaneous detections across the four locked bullish setup families. CFR-2 inserts that green contract into the production evidence path without changing any downstream trading-tier authority.

Production evidence flow becomes:

`completed Daily evidence -> raw SFC-1 compiler -> CFR-1 resolver -> SFC-2B admission / Claude context -> existing deterministic execution stack`

The scanner remains governed by the project sequence:

`Auction Engine -> Trend Engine -> Zone Control -> Opportunity Engine -> Verdict`

## Runtime boundary

`src/setup_family_runtime.py` is the production facade.

It calls the raw `src.setup_family_compiler.compile_setup_families()` first, then calls `family_resolver.reconcile_compiled_evidence()` on the returned object. The raw SFC-1 compiler is not rewritten and its direct unit-test contract remains intact.

Package-level `from src import setup_family_compiler` now points to the runtime facade. `src.indicators` already imports the compiler through that package-level path, so enrichment receives resolved family evidence without changing the large indicators module or its completed-vs-developing Daily truth boundary.

Direct imports from `src.setup_family_compiler` still address the raw SFC-1 compiler.

## Resolution law

The production facade preserves CFR-1 doctrine:

- execution proof outranks a merely higher family score;
- simultaneous family labels do not stack scores;
- confluence is context, not automatic promotion;
- a family-local failure does not automatically cancel a valid sibling setup;
- shared/common failures remain observable for sovereign downstream gates;
- no resolver field assigns a tier, route, or position size.

## Claude context bridge

The existing GPT prompt already serializes the resolved primary family's `metrics` as structured JSON. CFR-2 therefore adds a namespaced `cross_family_resolution` object to a deep-copied primary metrics object.

That compact object exposes:

- relationship;
- conflict scope;
- resolved primary family;
- secondary families;
- failed families;
- shared failure codes;
- confluence count;
- reason codes;
- explicit `score_stacking_allowed=false`;
- explicit `capital_authority=false`.

No raw SFC-1 family object is mutated.

## SFC-2B admission interaction

Because the reconciled evidence replaces the stale top-level primary summary before prefilter admission, SFC-2B evaluates the resolved primary family. This prevents an unfinished high-score family label from displacing another family whose execution lifecycle is actually further advanced.

Admission remains admission only. Existing common fatal gates remain non-rescuable.

## No-drift boundary

CFR-2 does not change:

- the 814-symbol universe;
- the 15-minute cadence;
- the 30-candidate deep-analysis cap;
- prefilter score weights/floor;
- SNIPE / STARTER score floors;
- R:R law;
- fragile-risk floor;
- 1H execution authority;
- real-4H shadow status;
- cooldown/dedup;
- Discord routing;
- capital sizing authority.

## Acceptance tests

CFR-2 must prove under the permanent Python 3.13 production gate that:

1. `indicators` is using the production runtime facade;
2. execution-proof-first resolution replaces stale raw primary selection;
3. raw SFC evidence is not mutated;
4. cross-family context reaches Claude through the existing metrics payload;
5. SFC-2B admission sees the resolved primary;
6. no-family cases remain no-family cases;
7. all legacy regressions remain green.

## Next after CFR-2

After CFR-2 is production-green, proceed to the next planned evidence-authority/validation work without using candidate-cap expansion as a substitute for ranking quality. The 30-vs-40 study remains evidence-gated.
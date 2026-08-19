# Ticker Universe Management Contract

Production universe source: `config/tickers.txt`.

The ticker universe is data/configuration, not strategy. Adding symbols must not silently mutate scanner doctrine.

## Loader contract

`src.market_data.load_tickers(path)` performs format validation only.

It must:

- ignore blank lines;
- ignore `#` comment lines;
- uppercase symbols;
- accept letters, digits, dot and dash within the existing regex contract;
- reject malformed symbols without crashing;
- remove duplicates while preserving first occurrence and file order;
- not call yfinance or any market-data provider;
- keep well-formed symbols even if they may later prove delisted/unfetchable.

Fetch-time viability remains the market-data layer's responsibility.

## Current baseline

Before the next requested expansion the production regression count is 814 valid unique symbols.

`tests/test_ticker_loader.py::test_full_universe_loads_correctly` is the explicit universe snapshot test. It intentionally fails when the universe changes until the change is reviewed and the expected count/boundaries are updated.

## Procedure for the next ticker addition

When the operator supplies the list:

1. Normalize requested symbols to uppercase.
2. Compare against the loaded current universe.
3. Report/handle duplicates against existing membership without adding a second copy.
4. Reject only malformed strings at the loader-contract level; do not silently remove a well-formed symbol because a provider has temporary/no data.
5. Insert new symbols in deterministic alphabetical order unless the operator explicitly changes universe-order policy.
6. Re-run `load_tickers` against the modified file.
7. Update the full-universe regression count and boundary assertions if they changed.
8. Add exact-presence regression assertions for strategically important new symbols when appropriate.
9. Run compile + full production tests.
10. Review diff to confirm no unrelated config, thresholds, candidate cap, cadence, scoring, tiering, model provider, or routing changed.
11. Merge through a dedicated universe PR.
12. Validate Railway/Discord runtime after deploy.

## Universe-change invariants

A universe update may change:

- membership;
- expected universe count;
- alphabetical boundaries;
- symbol-presence tests.

A universe update must NOT implicitly change:

- deep-analysis candidate cap;
- prefilter minimum score;
- scoring weights;
- tier score thresholds;
- R:R floors;
- risk-distance floors;
- scan cadence;
- market hours;
- model provider/model selection;
- Discord channels;
- cooldown;
- setup-family doctrine;
- 4H authority mode.

If the expanded universe later demonstrates capacity pressure, rate-limit pressure, or candidate-cap crowding, that becomes a separately measured architecture phase. The universe change itself is not permission to guess at those settings.

## Capacity interpretation

The prefilter evaluates the full loaded universe algorithmically, then admits only the configured top candidate set to the deep-analysis model. Therefore a larger universe mainly increases Daily market-data/feature work and ranking competition; it does not automatically increase model calls beyond the configured cap.

That architecture is deliberate. It protects API cost/rate budget while requiring telemetry to reveal whether good setups are being cut off near the admission boundary.

Current baseline cap is 30. Ranks 31-60 are already captured through near-cut telemetry. The preferred next ceiling is 40 only after the GPT-5.6 runtime migration, setup-family compiler, near-cut opportunity review, and scan-budget validation prove a net benefit.

## Failure handling

A ticker that fails market-data retrieval in one scan must be recorded as a data failure for that cycle. It must not be rewritten into a setup rejection and must not be silently removed from the universe by runtime code.

Permanent removal of a symbol from `config/tickers.txt` is an explicit operator/configuration decision.
# Institutional Leadership & Alpha Engine — integration contract

Status: DESIGN / RESEARCH ONLY. No production authority or capital gate change until validated and merged.

## Mission and boundaries
Add a cross-sectional institutional leadership research organ to Chart Wizard without weakening its established structure-first execution gates. The ChatGPT Market Desk scheduled reports are separate from this Railway scanner; editing one does not deploy the other.

## Four separate rankings
A. Point-in-time investable US common-equity universe: split/dividend-adjusted trailing 126-session total return (with raw return shown, not mistaken for quality).
B. Residual alpha: factor-adjusted performance conditional on adequate history and an explicitly fitted market/sector/style exposure model; no unsupported alpha estimate.
C. Six-month persistence: monthly return dispersion, positive months, path efficiency, max drawdown, downside vol, 20/50/100/200-day trend slope, 5/10/20-day concentration of six-month log return, sector/industry-relative strength, liquidity and sponsorship corroboration.
D. Current opportunity: chart location, actionable setup family, catalyst, price/volume acceptance, structural invalidation, target path, execution liquidity and risk-adjusted trade expression.

Report Top 10 by C, with A/B/D alongside and top three trade dossiers. Do not rank by the last six days or require every soft indicator to agree.

## Universe and data contracts
- Point-in-time universe membership, ticker and corporate-action mapping; exclude funds, penny stocks, illiquid names, short-history IPOs by explicit screens. Never silently equate the scanner's 814-symbol universe with all US equities.
- At least 126 completed daily sessions per eligible security; adjustment metadata, session/date provenance, missing-bar and provider-entitlement flags. The existing 18-month daily lookback may suffice for price-derived measures, but must be verified against source completeness and corporate-action handling.
- Price and volume: current existing market-data adapter first, then independently licensed OHLCV. Sector/industry membership and benchmarks must have dated provenance. Factor series, estimate revisions, fundamental data, options tape, OI and Greeks are optional corroboration unless their absence makes a proposed execution expression impossible.
- Unusual Whales free options prints can be delayed two trading sessions; its live intraday candles are paywalled in the currently observed connector. Never mark them live. Its official API offers real-time and historical data subject to subscription and redistribution licensing; verify entitlement and licensing before ingestion.
- Options print direction, complex spread legs, rolls and next-day OI must be reconciled before inferring new sponsorship. A large print alone is not evidence of institutional accumulation.

## Calculation contract
- Six-month log return = sum(log(adjusted_close[t]/adjusted_close[t-1])); recent-contribution ratio uses 5/10/20-day sums over the six-month log return and must mark denominator near zero/negative as not interpretable.
- Path efficiency = abs(sum daily log returns) / sum(abs(daily log returns)); preserve direction separately.
- Relative strength = cumulative log-return spread vs SPY and sector/peer benchmarks on aligned sessions; factor residuals require an explicitly estimated model, enough observations and sensitivity checks.
- Persistence: monthly hit ratio, rolling trend slopes, return concentration, volatility and drawdown; do not collapse into a false-precision score until calibrated on chronological out-of-sample outcomes.
- Mark each metric VERIFIED INPUT / DERIVED / ESTIMATED / JUDGMENT; store as-of, provider, universe and version.

## Non-paralysis / execution sovereignty
- Leadership ranks are ADVISORY candidate discovery, not authority to override prefilter, tiering, ladder, seal or SNIPE capital gates.
- Minor soft disagreements affect ranking/confidence, not automatic veto. Only material execution failures remain hard blocks.
- Respect four production setup families, completed candle law, 4H shadow status, 15-minute cadence, candidate cap 30, and existing Discord final-tier routing.
- Do not add network calls to the 15-minute hot path without a budgeted/cacheable asynchronous batch. No new provider subscriptions or secrets committed.

## Proposed incremental build checkpoints
1. Pure offline price-only feature engine + deterministic fixtures/tests (splits, missing sessions, flat/negative returns, event-gap dominance, persistent leaders, sector-relative leader) and point-in-time universe coverage reporting.
2. Cached daily cross-sectional rankings, coverage diagnostics, source receipts and rank-change persistence; benchmark/factor estimates only with validated data.
3. Shadow-only candidate discovery against existing prefilter, with opportunity recall, cost/cadence and chronological outcome linkage; no capital or alert behavior changes.
4. Shadow-to-production promotion only after CI, out-of-sample evidence, operator review, merge and Railway receipt; add top-ten output and top-three dossiers to appropriate operator reporting surfaces.

## Acceptance criteria
- Reproducible Top 10 and four separate rankings from fixed snapshots; correct return math and point-in-time provenance; no false live claims.
- No alteration to existing production tiers, candidate caps, Discord routes, model prompts, scan timing or risk gates until separate authorized promotion.
- Chronological tests prove rank stability, no lookahead and no significant degradation in scan budget.
- Operational receipt includes test results, CI, merge SHA, Railway deployment status and live-vs-shadow parity.

## Institutional sourcing, backtesting and forward-monitoring contract
- Build a provider inventory with primary/secondary sources, licensing, update latency, symbol/contract mapping, field provenance, as-of timestamps, historical depth and failover behavior. Entitlement checks must precede any live-data assertion.
- Version immutable point-in-time research snapshots, corporate actions, factor/sector membership and release-date-aware fundamentals. Record missing data, revisions, exclusions and sample coverage. Independent source cross-checks are required for decision-critical fields.
- Research design: predeclare hypothesis, feature/label availability time, candidate universe, benchmark, regime buckets, costs and acceptance criteria before evaluating outcomes. Purged/embargoed chronological walk-forward where overlapping labels require it; avoid lookahead, survivorship, selection and multiple-testing biases.
- Evaluate expectancy, payoff distribution, hit rate, drawdown, tail losses, turnover, implementation shortfall, liquidity/capacity, factor-adjusted return and stability by regime. Use transaction costs, spread/slippage, and for options bid/ask, IV/theta and exercise/assignment assumptions. Report sample size and uncertainty; never invent win probabilities.
- Keep distinct BACKTEST / SHADOW / PAPER / LIVE evidence and persist research version, candidate rank, as-of signal, later outcome and attribution. Production intraday scans consume the latest validated research artifact; they do not rerun expensive full-history backtests on every scan.
- Monitor data freshness, provider failures, rank drift, factor exposure, forward-vs-backtest divergence and regime changes. Trigger controlled recalibration and regression tests when thresholds are breached. Preserve all existing production risk gates, cadence and cost budgets until separate authorized promotion.

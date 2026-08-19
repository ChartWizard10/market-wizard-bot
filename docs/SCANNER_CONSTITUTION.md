# Chart Wizard Scanner Constitution

Status: production-governing doctrine

This file is the durable operating law for the Chart Wizard bullish swing scanner. Chat context may help explain a decision, but repository doctrine and tests must preserve the decision after the conversation ends.

## 1. Mission

Build a selective bullish swing-entry engine that finds actionable opportunities across a broad U.S. equity/ETF universe without manufacturing certainty.

The scanner may identify a setup as capable of a fast move only when the chart has a realistic structural path and volatility capacity. The aspirational research target is a setup with a plausible path to approximately +8% within five trading sessions. That is a validation target, not a promised outcome and never a reason to weaken a gate.

Precision, abstention, falsifiability, and repeatability outrank alert volume.

## 2. Governing read order

Every chart is read in this order:

1. Auction Engine
2. Trend Engine
3. Zone Control
4. Opportunity Engine
5. Verdict

Universal sequence grammar:

`STATE -> LOCATION -> EVENT -> REACTION -> ACCEPTANCE -> RETEST -> HOLD -> CONSEQUENCE`

Core structural law:

`Structure -> Liquidity -> Displacement -> Retest -> Hold -> Invalidation -> Target`

Execution law:

`Break/Reclaim -> Acceptance -> Retest -> Hold`

A visible level, moving-average touch, wick, gap fill, breakout print, or pattern label is information. It is not capital permission by itself.

## 3. Timeframe jurisdiction

- Weekly: campaign context and higher-timeframe permission.
- Daily: swing thesis permission, trend/value, sovereign structure, major zones and path.
- Real 4H: operational location and repair evidence. Until an explicit R4H-2 promotion is validated, the real-4H organ remains shadow evidence and the existing Phase-14F operational proxy remains production-authoritative.
- 1H: entry-trigger proof. The 1H may confirm or reject execution; it does not invent the swing thesis.
- 15m/5m/1m: precision/monitoring only when explicitly added. They may not legalize a swing thesis.

Higher-timeframe structure outranks lower-timeframe excitement. Closed-candle evidence outranks developing-candle information.

## 4. Production setup families

The production design must recognize these bullish setup families as distinct lifecycles, not force every opportunity through one visual template:

### BREAK_RETEST_CONTINUATION
Break or reclaim of a meaningful decision boundary, body acceptance, retest, hold, and consequence. Includes accepted breakout/reclaim and failed-breakdown reclaim behavior when the downside participant becomes trapped.

### VCP_BREAK_RETEST
A sponsored bullish trend contracts in price range, pullback depth/violence, and preferably volume. A clean pivot/boundary forms. Premium execution requires breakout acceptance and preferably breakout-retest-hold. An elite final contraction may qualify only for reduced starter treatment under explicit family rules; it is never automatically full-size.

### SMA_CRADLE_CONTINUATION
Prior displacement establishes sponsorship. Price repairs into a rising SMA20 or SMA20/50 value pocket, often with a lower wick/pinbar or undercut, reclaims value, then proves break/acceptance/retest/hold. The moving average is value memory, not a signal.

### GAP_FILL_REVERSAL
Price returns into a prior gap/imbalance and the fill resolves through failed downside acceptance, reclaim, and hold. Valid forms include full-fill sweep reclaim, partial-fill respect, fill into rising dynamic support, and exhaustion-flush reclaim. The gap fill itself is not an entry.

Family labels never outrank sequence quality. A beautiful pattern with no acceptance, no retest/hold, no invalidation, or no path is not an official entry.

## 5. Entry/readiness states

The scanner deliberately supports different entry classes.

- `SNIPE_IT`: execution-authorized state. Full-size eligibility requires the complete governing proof stack. SNIPE_IT does not mean every setup scores 100 or is A+; the internal SNIPE ladder carries quality distinctions.
- `STARTER`: controlled reduced-size entry. A legitimate setup may earn starter capital before every full-size condition is complete when structure/location, first proof, invalidation, and path justify smaller-risk participation.
- `NEAR_ENTRY`: forming/watch state. No capital. Must name what is missing and the exact upgrade trigger.
- `WAIT` / `PASS`: no actionable bullish entry. No capital.

Do not incorrectly demote a legitimate starter merely because it is not a full-size SNIPE. Do not promote a watch state because a score is high.

## 6. Gate law

Deterministic doctrine gates precede model preference. The weakest material reading caps the verdict.

Non-negotiable execution truths include:

- no fabricated structure;
- no blind moving-average touch;
- no gap-fill superstition;
- no wick-only confirmation when a close is required;
- no official full-size SNIPE without retest/hold proof;
- no capital without a killable invalidation;
- no official entry with blocked target path;
- no fake R:R from a microscopic stop;
- no stale/ambiguous bar granted confirmation authority;
- no score rescue of a failed hard gate;
- no stale intermediate tier allowed to govern cooldown, routing, or capital.

## 7. Data-truth law

A closed candle is evidence. A developing candle is information.

Daily and 1H market-bar truth must explicitly distinguish closed from live/ambiguous data. Ambiguous data withholds confirmation; it never manufactures it.

The real 4H engine must continue to use session-aligned aggregation from the same 60m provider response already acquired for 1H. It must not add a second intraday request merely to create 4H evidence.

Provider failure, stale data, malformed bars, rate limiting, and telemetry failure must remain distinguishable from a genuine market/setup rejection.

## 8. Model law

Claude is an analyst/classifier inside the system, not the sovereign risk engine.

- JSON contract is mandatory.
- Deterministic tiering and capital gates can downgrade or reject model output.
- Model routing is runtime-configurable; model intelligence and scanner doctrine are separate layers.
- No model change may silently change hard gates, scoring, routing, cooldown, universe, or capital contracts.

## 9. Alert and state law

Production order after judgment:

`final executable tier -> dedup/cooldown -> Discord routing -> state record`

WAIT never posts.

Cooldown/tier-improvement logic must evaluate the final executable tier after all tier-mutating organs have finished.

Manual `!analyze` may bypass universe admission and cooldown for operator inspection, but it must use the same post-tiering chart-judgment organ as autoscan.

Telemetry is observational only. Telemetry corruption or telemetry-write failure must never change strategy, tier, capital, routing, suppression, or alert history.

## 10. Universe law

`config/tickers.txt` is the production universe source.

Universe changes must be:

1. normalized and validated by `market_data.load_tickers`;
2. unique;
3. reviewable in Git diff;
4. accompanied by the universe regression update;
5. tested through the permanent production CI gate;
6. merged through a dedicated branch/PR.

Expanding the universe does not authorize changing candidate cap, doctrine thresholds, scoring weights, cadence, or alert rules unless a separate reviewed phase proves that change is needed.

## 11. Version-control and deployment law

GitHub is the durable source of truth. Railway is the runtime platform. Discord is the alert surface.

Every production change follows:

`branch -> focused change -> focused tests -> full CI -> review -> merge -> Railway validation`

Never patch production strategy casually in chat and leave the repository undocumented.

## 12. Evaluation law

Backtests and live-shadow evaluation must be chronological and must separate setup quality from outcome luck.

For the fast-swing objective, the preferred research label is a three-barrier outcome:

- target barrier: approximately +8%;
- risk barrier: structural invalidation/stop;
- time barrier: five trading sessions.

Performance must be attributable by setup family, verdict tier, regime, and trigger state. An aspirational hit-rate target is not a production claim until proven out of sample.

## 13. Anti-drift law

When doctrine, code, tests, prompt wording, and runtime behavior disagree, do not guess. Find the contradiction, identify the current production authority, and repair the architecture through reviewable version control.

The scanner is allowed to say no setup exists. It is not allowed to invent certainty.
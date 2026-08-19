# VELOCITY-1A — Five-Session / +8% Research Contract

## Purpose

The scanner constitution defines an aspirational research objective: identify bullish entries with a realistic path to approximately **+8% within five trading sessions**, subject to structural invalidation. That objective is a validation target, not a promised forecast and not a reason to weaken chart gates.

VELOCITY-1A converts the objective into two deterministic research contracts while preserving production authority:

1. **Ex-ante feasibility snapshot** — a transparent description of known path room and observed ATR-based range capacity at the observation time.
2. **Ex-post three-barrier label** — after the observation, determine whether the +8% target, structural invalidation, or five-session time barrier resolved first.

This phase is research-only. It does not change `SNIPE_IT`, `STARTER`, `NEAR_ENTRY`, capital sizing, routing, prefilter admission, candidate rank, or Discord behavior.

## Why the existing Phase-13 backtest is not replaced

`src/backtest.py` already answers a different useful question: did the alert's own T1 target hit before invalidation over a configurable bar horizon?

VELOCITY-1A does **not** rewrite that engine. The new constitutional label has a fixed research objective independent of the alert's T1:

- upper barrier: entry/reference price × 1.08 by default;
- lower barrier: structural invalidation from the observation;
- time barrier: five completed future trading sessions by default.

Keeping both contracts allows the project to distinguish **setup target quality** from **fast-swing objective attainment**.

## Ex-ante feasibility evidence

`build_feasibility_snapshot()` records:

- target return objective;
- five-session horizon;
- reference price and its source;
- target price;
- compound daily move required to reach the objective in five sessions;
- nearest known decision ceiling from supplied overhead/target evidence;
- known structural room percentage;
- ATR percentage;
- number of ATRs required for the +8% objective;
- a transparent five-session ATR-capacity proxy;
- path-support and range-capacity booleans when the needed inputs exist.

Possible research states:

- `SUPPORTED`
- `BLOCKED_PATH`
- `RANGE_STRETCHED`
- `PARTIAL_SUPPORT`
- `UNKNOWN`
- `INVALID_DATA`

The ATR calculation is explicitly a **capacity proxy**, not a probability. `SUPPORTED` is not a trade signal. The returned object permanently carries:

- `research_only=true`
- `capital_authority=false`
- `tier_authority=false`
- `forecast_authority=false`

A later chronological study must determine whether any feasibility state deserves production authority.

## Ex-post three-barrier labels

`label_three_barrier_outcome()` walks future Daily OHLC bars in chronological order and emits exactly one of:

- `TARGET_FIRST` — +8% upper barrier touched before invalidation;
- `INVALIDATION_FIRST` — structural invalidation touched before +8%;
- `AMBIGUOUS_SAME_SESSION` — both price barriers touched in one Daily bar and intraday order cannot be proven;
- `TIME_BARRIER` — neither price barrier touched after the full five-session horizon;
- `INCOMPLETE_HORIZON` — no price barrier has resolved but fewer than five future sessions are available;
- `INVALID_DATA` — required geometry or OHLC is unusable.

A terminal price-barrier hit can be labeled before all five future bars exist. A no-hit observation cannot be called a timeout until all five sessions are present.

## Entry/reference truth

`label_alert_three_barrier()` resolves the research reference in this order:

1. `entry_price`
2. `scan_price`
3. `current_price`
4. `latest_close`
5. `trigger_level`

The selected source is persisted as `entry_price_source` so later audits know exactly what price was used.

The wrapper also records `capital_authorized_at_observation` based on the observed tier. A `NEAR_ENTRY` observation may still be studied, but it is never silently counted as an executed trade. Production-capital studies must stratify by this field/tier.

## Same-session law

Daily OHLC cannot prove whether high or low occurred first. If the target and invalidation are both touched in the same future session, the result is `AMBIGUOUS_SAME_SESSION`. VELOCITY-1A does not invent sequence.

## Attribution

`summarize_three_barrier_labels()` groups results by:

- observed final tier;
- setup family;
- barrier label.

This creates the basic attribution contract needed for later chronological out-of-sample validation, R4H proxy-vs-real counterfactual analysis, and the 30-vs-40 candidate-cap study.

## Authority boundary

VELOCITY-1A is deliberately **not wired into live tiering**. First establish the label and feasibility semantics under the permanent test gate. The next controlled phase should persist the ex-ante snapshot in scan-time telemetry without allowing it to mutate a verdict, then connect completed observations to future Daily bars offline.

Only after enough chronological evidence exists should the project test whether a velocity state improves selectivity or recall. No hit-rate claim should be promoted from synthetic tests.

## No drift

This phase does not change:

- 814-symbol universe;
- 15-minute cadence;
- 30-candidate GPT-5.6 cap;
- setup-family admission;
- score floors;
- R:R floors;
- structural invalidation law;
- real-4H shadow authority;
- cooldown/dedup;
- Discord routing;
- capital authority.
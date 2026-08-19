# VELOCITY-1D — Offline Chronological Outcome Linker

## Purpose

VELOCITY-1A defined the five-session / approximately +8% research objective and deterministic three-barrier outcome labels. VELOCITY-1B defined the immutable scan-time observation envelope. VELOCITY-1C wired a bounded version of that envelope into analyzed decision traces.

VELOCITY-1D connects those observations to completed future Daily bars **offline** so the project can build a chronological research dataset without granting any new live trading authority.

## Data flow

`scan-time VELOCITY-1C trace -> local telemetry ledger -> local future Daily bars -> VELOCITY-1D linker -> VELOCITY-1A three-barrier label`

The linker does not fetch market data. Future bars must be supplied as a local historical/fixture payload.

## Chronology law

The observation-day Daily candle is never a future outcome bar.

For an observation made on calendar date `D`, VELOCITY-1D admits only completed Daily sessions whose supplied session date is strictly greater than `D`.

This prevents intraday leakage from the developing Daily candle that existed when the scanner made its observation.

The supplied bars are sorted by session date. The first five unique sessions after the observation are the default research horizon.

## Duplicate and malformed data law

- identical duplicate rows for one Daily session are deduplicated;
- conflicting OHLC rows for the same session invalidate that linkage rather than forcing a choice;
- malformed or unparseable session-date rows are counted and ignored because their chronological position cannot be proven;
- a missing ticker-bar payload is `INVALID_DATA`, never a time-barrier result;
- partial future history remains `INCOMPLETE_HORIZON`, never a timeout;
- same-session target and invalidation touches remain `AMBIGUOUS_SAME_SESSION` because Daily OHLC cannot prove intraday ordering.

## Observation identity law

A linkable observation requires:

- scan id;
- ticker;
- observation timestamp;
- persistence-ready VELOCITY-1C geometry;
- valid entry/reference price;
- structural invalidation below entry;
- positive target-return objective;
- positive session horizon.

Incomplete observations are retained as invalid research rows rather than silently discarded.

## Duplicate observation law

The natural observation key is `(scan_id, ticker)`.

- identical duplicate observations are deduplicated;
- conflicting duplicates under the same key are marked `DUPLICATE_OBSERVATION_CONFLICT` and labeled invalid rather than double-counted or guessed through.

## Research attribution

Every linked record carries the original scan-time attribution required for later study:

- observed final tier;
- whether capital was authorized at observation time;
- primary setup family;
- feasibility state and path/range metrics;
- real-4H shadow state;
- legacy proxy state and agreement.

This allows later analysis by setup family, tier, feasibility state, real-4H state, and proxy relationship without converting those attributes into live authority.

## R4H dependency

VELOCITY-1D supplies the forward-outcome side that R4H-2 was missing. It does **not** by itself prove that real 4H should replace the existing proxy.

A later reviewed study must still define the actual proxy-vs-real decision policy, compare the two policies against linked outcomes chronologically, measure precision and opportunity recall, and satisfy the R4H-2 acceptance contract before any authority handoff.

## CAP-40 dependency

VELOCITY-1D also creates the outcome-linking machinery needed for the later 30-vs-40 candidate-cap study. The cap remains 30 until ranks 31–40 are studied with real incremental opportunity outcomes and cadence/cost constraints.

## Offline CLI

`scripts/build_velocity_dataset.py` accepts:

- `--telemetry`: saved scan-telemetry JSON ledger;
- `--bars`: local Daily OHLC JSON;
- `--out`: output dataset JSON.

Accepted Daily-bar payloads:

1. direct mapping: `{ "AAPL": [ ... ], "MSFT": [ ... ] }`;
2. nested mapping: `{ "bars_by_ticker": { ... } }`;
3. flat records with a `ticker` field on each row.

The CLI performs local file I/O only and makes no network request.

## Authority boundary

VELOCITY-1D is research-only.

It has no authority to:

- promote or downgrade a tier;
- authorize or deny capital;
- alter routing or cooldown;
- change the scanner universe or candidate cap;
- change scan cadence;
- promote real 4H;
- claim that +8% within five sessions is probable or guaranteed.

The next phase after a green merge is **R4H outcome study preparation**, unless an intermediate dataset-quality phase is required by real collected telemetry.
# Backtest Runbook — Alert History Offline Analysis

## Overview

`scripts/backtest_alert_history.py` is an offline, read-only CLI tool.
It reads saved scanner alert history from a local JSON file, pairs each alert
with future OHLC bars you supply, and prints a deterministic win/loss/open summary.

It makes no network calls. It does not modify any file. It does not interact
with the live bot, Discord, Railway, or the scheduler.

---

## Step 0 — Verify the State-Store Path Before Running

**This is the most important step. Do not skip it.**

The path to the live alert history file is not fixed. It is set by
`doctrine_config.yaml` and reported by `!status`. The code has a separate
hardcoded fallback that is only used when config is absent.

**There are two paths in the codebase. They are not the same:**

| Source | Path | When used |
|---|---|---|
| `config/doctrine_config.yaml` → `state.state_file` | `.state/alert_history.json` | **Live deployed bot — source of truth** |
| `src/state_store.py` `_DEFAULT_STATE_PATH` | `data/alert_state.json` | Code fallback only, if config is missing or broken |

> **Use the path reported by `!status` as the source of truth for the deployed bot.**

### How to verify

**Option A — `!status` in Discord (preferred for deployed bot):**

```
!status
```

Look for the line:
```
State store: .state/alert_history.json
```

That value is the active path. Use it as your `--alerts` argument.

**Option B — read the config directly:**

```bash
grep "state_file" config/doctrine_config.yaml
```

Expected output for the current deployment:
```
  state_file: ".state/alert_history.json"
```

---

## Step 1 — Locate the Alert History File

For the **live/deployed bot** (confirmed via `!status` as of Phase 13.3B):

```
.state/alert_history.json
```

For **local dev or CI environments** where no config is loaded, the code fallback is:

```
data/alert_state.json
```

Never assume the path. Always verify first.

---

## Step 2 — Prepare a Bars File

The backtest runner requires a separate bars JSON file containing future OHLC data
for each ticker you want to evaluate.

Format — either of these shapes is accepted:

**Shape A — dict keyed by ticker:**
```json
{
  "AAPL": [
    {"open": 182.0, "high": 195.0, "low": 181.5, "close": 193.0},
    {"open": 193.0, "high": 198.0, "low": 192.0, "close": 197.5}
  ]
}
```

**Shape B — flat list of bars with ticker field:**
```json
[
  {"ticker": "AAPL", "open": 182.0, "high": 195.0, "low": 181.5, "close": 193.0}
]
```

Each bar must have `open`, `high`, `low`, `close` as numeric values.
Bars should be sorted ascending (oldest first) starting from after the alert time.

---

## Step 3 — Run the Backtest

```bash
python scripts/backtest_alert_history.py \
  --alerts .state/alert_history.json \
  --bars   /path/to/your/bars.json \
  --horizon 10
```

Replace `.state/alert_history.json` with the path confirmed in Step 0.
`--horizon` is the max number of forward bars evaluated per alert (default: 10).

The runner accepts the raw state-store format directly — you do not need to
pre-process the file. It automatically extracts all `alert_history` records
from the `tickers` dict.

---

## Step 4 — Interpret the Output

The summary prints:

- **Overall win rate** — alerts where T1 was hit before invalidation
- **By tier** — SNIPE_IT / STARTER / NEAR_ENTRY breakdown
- **By risk_realism_state** — realistic / marginal / aggressive / unavailable
- **By retest × hold combo** — confirmed/confirmed vs other combinations
- **Data quality** — COMPLETE / BACKTESTABLE / PARTIAL / INSUFFICIENT counts

### Outcome labels

| Label | Meaning |
|---|---|
| `WIN_T1_BEFORE_INVALIDATION` | Price hit T1 target before touching invalidation level |
| `LOSS_INVALIDATION_BEFORE_T1` | Price hit invalidation before reaching T1 |
| `OPEN_NO_TERMINAL_HIT` | Neither T1 nor invalidation hit within the horizon window |
| `NO_TRIGGER` | Price never touched the trigger level |
| `AMBIGUOUS_SAME_BAR` | T1 and invalidation both hit on the same bar |
| `INVALID_DATA` | Missing or non-numeric required fields — alert not evaluable |

### Data quality labels

| Label | Meaning |
|---|---|
| `COMPLETE` | All fields present: tier, scan_price/trigger, invalidation, targets |
| `BACKTESTABLE` | Core fields present; some diagnostics may be absent |
| `PARTIAL` | One required field missing; outcome may be unreliable |
| `INSUFFICIENT` | Too many required fields missing; not evaluable |

**Phase 13.3B note:** Alerts recorded after the Phase 13.3B storage contract
upgrade store all fields needed for `COMPLETE` or `BACKTESTABLE` classification.
Older alerts recorded before Phase 13.3B may only have the original 9 fields
and will typically score `PARTIAL` or `INSUFFICIENT`.

---

## Path Reference Summary

```
doctrine_config.yaml  →  state.state_file  →  .state/alert_history.json   ← LIVE SOURCE OF TRUTH
state_store.py        →  _DEFAULT_STATE_PATH  →  data/alert_state.json     ← CODE FALLBACK ONLY
main.py (!status)     →  reads from config, falls back to data/alert_state.json
```

When in doubt: **run `!status` and use whatever path it reports.**

# Phase 13.4 — First Real Backtest Runbook

## Purpose

This runbook guides the operator through running the first real offline backtest
against live scanner alert history. It documents the exact commands, input formats,
output interpretation, and decision rules that govern what to do with results.

The backtest engine asks one primary question:
**Did price hit T1 before touching the invalidation level?**

This runbook does not change live scanner behavior. It does not change tiering,
routing, capital policy, or alert thresholds. It is read-only analysis only.

---

## Current System State

As of Phase 13.3B, `record_alert()` stores 32 fields per alert record (up from 9).
The two fields required for outcome evaluation are:

- `targets` — list of target dicts with `level` key (e.g. `[{"label": "T1", "level": 195.0}]`)
- `scan_price` — reference price at alert time (fallback: `trigger_level`)

Alerts recorded **before** Phase 13.3B have only the original 9 fields and will
produce `INVALID_DATA` or `PARTIAL` quality labels — this is expected, not a bug.

---

## Non-Negotiable Outcome Law

The outcome engine is defined in `src/backtest.py`. Its law is fixed:

> **WIN = T1 hit before invalidation level, within `horizon_bars` forward bars.**

Everything else is classification, not judgment. The outcome labels are:

| Label | Meaning |
|---|---|
| `WIN_T1_BEFORE_INVALIDATION` | Price hit T1 before touching invalidation |
| `LOSS_INVALIDATION_BEFORE_T1` | Price hit invalidation before reaching T1 |
| `OPEN_NO_TERMINAL_HIT` | Neither hit within the horizon window |
| `NO_TRIGGER` | Price never touched the trigger level |
| `AMBIGUOUS_SAME_BAR` | T1 and invalidation both hit on the same bar |
| `INVALID_DATA` | Missing or non-numeric required fields — alert not evaluable |

`INVALID_DATA` is not automatically a bad alert. It means the record lacked
the fields needed to evaluate the outcome. Alerts from before Phase 13.3B will
produce `INVALID_DATA` because `targets` was not stored. This is a data-quality
gap, not a signal-quality judgment.

---

## Source Files

| File | Role |
|---|---|
| `scripts/backtest_alert_history.py` | CLI runner — reads alert history, normalizes records, calls engine |
| `src/backtest.py` | Pure outcome engine — `evaluate_alert_outcome()` |
| `config/doctrine_config.yaml` | Defines `state.state_file` — the active alert history path |

---

## Alert History Shape

The alert history file written by the live bot is a state-store JSON with this structure:

```json
{
  "tickers": {
    "AAPL": {
      "last_alerted_tier": "SNIPE_IT",
      "alert_history": [
        {
          "ticker": "AAPL",
          "tier": "SNIPE_IT",
          "alerted_at": "2025-01-15T14:32:00",
          "trigger_level": 182.50,
          "invalidation_level": 178.20,
          "scan_price": 183.50,
          "targets": [{"label": "T1", "level": 195.0, "reason": "FVG top"}],
          "score": 88,
          "reason": "..."
        }
      ]
    }
  },
  "meta": {}
}
```

The runner accepts this format directly via `--alerts`. No pre-processing needed.

---

## Required OHLC Bars Input

The runner requires a separate bars file (`--bars`) with future OHLC data.
Two formats are accepted:

**Format A — dict keyed by ticker (preferred):**

```json
{
  "AAPL": [
    {"open": 183.0, "high": 196.0, "low": 182.5, "close": 194.0},
    {"open": 194.0, "high": 198.0, "low": 193.0, "close": 197.5}
  ]
}
```

**Format B — flat list with ticker field:**

```json
[
  {"ticker": "AAPL", "open": 183.0, "high": 196.0, "low": 182.5, "close": 194.0}
]
```

Each bar must have `open`, `high`, `low`, `close` as numeric values.
Bars must be sorted ascending (oldest first), starting from after the alert time.

---

## Minimum Fields For Backtestable Alert

An alert record must have all three of these to produce a non-`INVALID_DATA` outcome:

1. `targets` — non-empty list with at least one entry containing a numeric `level`
2. `invalidation_level` — numeric value
3. `scan_price` or `trigger_level` — at least one numeric reference price

Missing targets remain missing. **Do not fabricate targets.** An alert with no
stored target scores `INVALID_DATA` and that is the correct result.

---

## Exact Commands

### Verify the active state-store path first (mandatory)

```
!status
```

Look for: `State store: .state/alert_history.json`

That value is the path to pass as `--alerts`. Do not assume.

Alternatively, read config directly:

```bash
grep "state_file" config/doctrine_config.yaml
```

### Run the backtest

```bash
python scripts/backtest_alert_history.py --alerts .state/alert_history.json --bars data/backtest_bars.json --horizon 10
```

Replace `data/backtest_bars.json` with the actual path to your bars file.
`--horizon 10` evaluates up to 10 forward bars per alert (approximately 10 trading days).

---

## Expected Output Sections

The runner prints a summary with these sections:

```
Overall
  Total evaluated:  N
  WIN:              N  (N%)
  LOSS:             N  (N%)
  OPEN:             N  (N%)
  INVALID:          N  (N%)

By tier
  SNIPE_IT:  N evaluated, N% win
  STARTER:   N evaluated, N% win
  NEAR_ENTRY: N evaluated, N% win

By risk_realism_state
  realistic:   N evaluated, N% win
  marginal:    N evaluated, N% win
  aggressive:  N evaluated, N% win

By retest × hold
  confirmed × confirmed:  N evaluated, N% win
  ...

DATA QUALITY
  COMPLETE:      N
  BACKTESTABLE:  N
  PARTIAL:       N
  INSUFFICIENT:  N
```

---

## How To Interpret INVALID_DATA

`INVALID_DATA` means the outcome engine could not evaluate the alert because one or
more required fields were missing or non-numeric.

**Common causes:**
- Alert recorded before Phase 13.3B — `targets` was not stored
- Alert recorded when `scan_price` and `trigger_level` were both absent
- `T1 <= invalidation` geometry (structurally impossible to win without crossing invalidation first)

**What to do:**
- Check the DATA QUALITY section of the output for counts
- `PARTIAL` and `INSUFFICIENT` are expected for pre-Phase-13.3B records
- `INVALID_DATA` on a post-Phase-13.3B record warrants investigation of that specific alert
- Do not treat a high `INVALID_DATA` count as scanner failure — it is a data-age artifact

---

## How To Interpret NO_TRIGGER

`NO_TRIGGER` means price never touched the trigger level within the horizon window.
The alert fired, but the market never gave an entry.

**This is not a bad alert.** It means the setup did not activate. The scanner
identified a potential, not a guarantee of entry. NO_TRIGGER alerts are neutral —
they neither confirm nor deny signal quality.

---

## How To Interpret AMBIGUOUS_SAME_BAR

`AMBIGUOUS_SAME_BAR` means a single bar's high touched or exceeded T1 while the
same bar's low touched or broke the invalidation level. The engine cannot determine
which happened first within that bar without intrabar data.

**What to do:**
- Treat as inconclusive — do not count as WIN or LOSS
- If frequency is high, consider reducing `--horizon` or using higher-resolution bars
- This is a data-granularity limitation, not a doctrine failure

---

## First Real Backtest Procedure

1. Run `!status` in Discord. Note the `State store:` value.
2. Confirm the state file exists on disk: `ls -lh .state/alert_history.json`
3. Prepare a bars JSON file for the tickers in the alert history.
4. Run the exact command from the **Exact Commands** section above.
5. Read the DATA QUALITY section first. If fewer than 5 records are `COMPLETE` or
   `BACKTESTABLE`, the sample is too small for any conclusion. Stop and collect more data.
6. Read the Overall section. Note WIN/LOSS/OPEN/INVALID counts.
7. Read By tier. Note whether SNIPE_IT win rate differs from STARTER or NEAR_ENTRY.
8. Apply the Decision Rules below.

---

## No-Analysis-Paralysis Guard

A first backtest run may have:
- A small sample (< 20 evaluable alerts)
- High `INVALID_DATA` count from pre-Phase-13.3B records
- Mixed results with no clear pattern

**Do not draw hard conclusions from a small or data-poor sample.**
**Do not add new hard gates to the scanner based on a first run.**

The purpose of the first run is to confirm the pipeline works end-to-end and to
establish a baseline, not to make immediate doctrine changes.

No single alert or small sample should cause a new hard gate, a new veto rule,
or a change to the tiering contract.

---

## What We Are Looking For

From the first real backtest, the acceptable outcomes are:

- Pipeline runs without error
- DATA QUALITY section shows expected INVALID for pre-13.3B records
- At least some COMPLETE or BACKTESTABLE records exist (from post-13.3B alerts)
- SNIPE_IT win rate is not catastrophically below NEAR_ENTRY win rate
- No obvious systematic failure (e.g. 100% INVALID_DATA on post-13.3B records)

We are NOT looking for a specific win percentage threshold on this first run.
The first run is a pipeline validation, not a performance judgment.

---

## Decision Rules After First Run

| Result | Action |
|---|---|
| Pipeline errors on startup | Fix the path, file format, or bars JSON before any analysis |
| 100% INVALID_DATA on post-13.3B records | Investigate individual records — likely a `targets` storage bug |
| High INVALID on pre-13.3B records | Expected — do nothing |
| Sample < 5 evaluable alerts | Collect more alert history before drawing conclusions |
| SNIPE_IT win rate > 50% | Encouraging baseline — continue collecting data |
| SNIPE_IT win rate < 20% | Note for review after ≥ 20 evaluable alerts; do not gate yet |
| AMBIGUOUS count > 20% of evaluable | Consider using daily bars if currently using weekly |

Do not modify doctrine_config.yaml, tiering.py, prefilter.py, or any scanner
source file based solely on a first backtest run.

---

## Future Improvements

- Automated bars fetch from yfinance (separate offline script, not in main scanner)
- Per-ticker breakdown in summary output
- Time-decay analysis (alerts evaluated at 5-bar vs 10-bar vs 20-bar horizon)
- Risk-realism-state filterable summary
- Integration with a visualization layer for MFE/MAE curves

None of these are in scope for Phase 13.4. They are logged here for future planning only.

---

## Explicit Non-Changes

This runbook and Phase 13.4 do not change:

- `src/state_store.py` — no edits to record_alert, check_alert, load, save, or dedup logic
- `src/tiering.py` — no tier gate changes
- `src/discord_alerts.py` — no routing changes
- `src/scheduler.py` — no cadence or market-hours changes
- `src/indicators.py` — no indicator changes
- `src/prefilter.py` — no scoring changes
- `src/claude_client.py` — no prompt changes
- `main.py` — no command changes
- `config/doctrine_config.yaml` — no threshold changes
- `config/tickers.txt` — unchanged
- `prompts/market_wizard_system.md` — unchanged
- `requirements.txt` — no new dependencies
- Railway / deployment configuration — not touched
- Live scanner capital policy — unchanged
- Alert suppression / dedup logic — unchanged
- Disabled indicator list — unchanged

The scanner's job remains the same: surface strong opportunities.
This runbook only makes past alert history measurable.

---

## Final Operator Checklist

Before running:

- [ ] Ran `!status` and noted the exact `State store:` path
- [ ] Confirmed state file exists on disk at that path
- [ ] Prepared a valid bars JSON file for the relevant tickers
- [ ] Confirmed `--alerts` path matches `!status` output

After running:

- [ ] Noted DATA QUALITY counts (COMPLETE / BACKTESTABLE / PARTIAL / INSUFFICIENT)
- [ ] Noted Overall WIN / LOSS / OPEN / INVALID counts
- [ ] Noted By tier breakdown
- [ ] Applied the No-Analysis-Paralysis Guard (small sample → no conclusions)
- [ ] Did NOT modify any live scanner file based on this run
- [ ] Did NOT push new hard gates based on this run

---

## Path Reference

```
doctrine_config.yaml  →  state.state_file      →  .state/alert_history.json   ← LIVE SOURCE OF TRUTH
src/state_store.py    →  _DEFAULT_STATE_PATH   →  data/alert_state.json        ← CODE FALLBACK ONLY
main.py   (!status)   →  reads config          →  falls back to data/alert_state.json
```

**Use the path reported by !status as the source of truth for the deployed bot.**

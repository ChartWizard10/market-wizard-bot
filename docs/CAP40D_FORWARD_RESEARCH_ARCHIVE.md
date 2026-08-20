# Phase CAP-40D — Forward Research Archive / Study Retention Integrity

## Objective

Protect the predeclared CAP-40C and R4H-3C forward studies from the bounded Phase-14V ring buffer.

The production scan ledger intentionally retains only 9,000 decision traces. At the current 15-minute cadence, a normal scan can emit roughly 60 traces (30 analyzed candidates plus 30 near-cut traces). That means the ring buffer can cover only about 150 full scans — roughly six trading sessions at the current market-hours schedule. CAP-40C and R4H-3C both require evidence spanning the 2026-08-20 through 2026-09-30 observation window, so the ring buffer alone cannot preserve the committed study cohort.

CAP-40D adds a separate, research-only, date-partitioned append archive. It does not enlarge Phase-14V, does not change its 9,000-trace safety bound, and does not alter any market judgment.

## Authority law

The archive is observational only.

It may not:

- change the 30-candidate production cap;
- add a GPT-5.6 call;
- promote or downgrade a tier;
- change capital action;
- change Discord routing or suppression;
- change scan cadence or universe membership;
- change setup-family admission;
- change real-4H authority;
- create a forecast.

Archive failure is a TELEMETRY/RESEARCH incident, never a trading failure.

## What is archived

Only the minimum trace projection needed by the existing offline research stack:

- `scan_id`;
- `ticker`;
- `trace_kind`;
- `pipeline` rank/score block when already present;
- `velocity_observation` when already present;
- `four_hour_real` when already present;
- `capacity_boundary_observation` when already present.

No Discord payload, dedup key, free-form model explanation, secrets, bar arrays, or live state snapshot is copied.

This preserves compatibility with the existing pure research consumers:

- `velocity_dataset.extract_velocity_observations()`;
- `four_hour_counterfactual.attach_counterfactuals()`;
- `capacity_boundary_dataset.extract_boundary_observations()`.

## Storage contract

Default directory: `.state/research_archive/`.

Files are partitioned by the America/New_York session date encoded from the scan timestamp:

`YYYY-MM-DD.jsonl`

Each successful scan appends one compact JSON line containing all study-relevant trace projections from that scan. A partial/corrupt line is ignored by the read-only loader and counted as degraded archive input; no repair or quarantine occurs on the read path.

Default retention: 120 days.

Default daily-file safety ceiling: 10 MiB. A write that would exceed the ceiling refuses safely and leaves trading/runtime state untouched.

## Railway durability requirement

Repository code can ensure append retention across the in-process ring-buffer rollover, but it cannot prove Railway filesystem persistence from GitHub alone.

For the committed forward studies to be valid, the production deployment must preserve `.state/research_archive/` across restarts/redeploys (normally by mounting the same persistent storage used for state, or an equivalent durable volume). This is an operational validation requirement and must not be inferred from repository code.

## Offline use

`forward_research_archive.load_archive_ledger_readonly()` reconstructs a ledger-shaped object with `decision_traces`, so the existing dataset/report builders can consume the archive without changing their statistical contracts.

The CLI research builders may use either:

- a saved Phase-14V telemetry JSON ledger, or
- the CAP-40D research archive directory.

The archive is the required source for the full-window forward studies once Phase-14V ring retention is exceeded.

## Study-window freeze

The 814-symbol production universe and the 30-candidate cap must remain unchanged through the committed CAP-40C observation window unless the study is explicitly invalidated and restarted under a new predeclared plan. A mid-window universe/cap change would alter the rank-boundary sampling frame.

## Acceptance

CAP-40D is acceptable only if tests prove:

1. only study-relevant traces are archived;
2. projection is whitelist-only and JSON-safe;
3. writer failure never raises into the scan path;
4. state/telemetry path collisions are refused;
5. one scan adds one JSONL batch line;
6. read-only loading skips malformed lines without writing;
7. date filtering is deterministic;
8. 120-day retention cannot remove the committed 2026-08-20 cohort before the 2026-10-08 CAP-40C review floor;
9. existing VELOCITY/CAP-40/R4H consumers work from the reconstructed archive ledger;
10. Phase-14V limits, production cap, cadence, universe, tiering, capital, routing and 4H authority remain unchanged.

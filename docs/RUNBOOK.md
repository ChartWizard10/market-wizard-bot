# Production Runbook

Runtime platform: Railway.
Alert surface: Discord.
Durable source of truth: GitHub repository.
Production deep-analysis provider: OpenAI GPT-5.6 after AI-1 merge/cutover.

This runbook records repository-verified behavior. Railway project-level settings that are not committed here must be checked in Railway rather than guessed.

## Application entry point

Production Python entry point: `main.py`.

Local equivalent:

```bash
python main.py
```

`main.py` loads `config/doctrine_config.yaml`, validates environment, builds the Discord/OpenAI clients, loads `prompts/market_wizard_system.md`, registers commands, and starts the bot.

## Required/recognized environment

Required for bot authentication:

- `DISCORD_TOKEN`

Required for GPT-5.6-backed `!scan` / `!analyze` and scheduled deep analysis:

- `OPENAI_API_KEY`

Optional runtime model override:

- `OPENAI_MODEL`

Canonical model resolution order:

1. non-empty `OPENAI_MODEL` environment value;
2. `config.model.name`;
3. code fallback `gpt-5.6`.

Discord channel environment overrides recognized by `src/discord_alerts.py`:

- `DISCORD_SNIPE_CHANNEL_ID`
- `DISCORD_STARTER_CHANNEL_ID`
- `DISCORD_NEAR_ENTRY_CHANNEL_ID`

If an override is absent, the corresponding channel ID in `config/doctrine_config.yaml` is used.

Never commit live secrets.

## AI-1 compatibility note

The scheduler and telemetry still expose historical `claude_*` function/field names during the provider cutover. Production `main.py` does not instantiate Anthropic; it constructs `AsyncOpenAI`, and `src/openai_scheduler_compat.py` translates the hardened scheduler call contract to the OpenAI Responses API with strict JSON Schema output.

This compatibility layer is naming/contract debt only. It exists to avoid combining a provider migration with a broad scheduler/telemetry schema migration. Remove/rename it only in a separately reviewed provider-neutral nomenclature phase.

## Startup expectations

`main.validate_startup` treats:

- missing `DISCORD_TOKEN` as a hard startup error;
- missing `OPENAI_API_KEY` as a warning, with model-backed commands expected to fail gracefully.

The system prompt must be readable from `prompts/market_wizard_system.md` for GPT-5.6 analysis.

## Scheduled scanning

Configured schedule:

- interval: 15 minutes;
- market-hours only: true;
- window: 09:35–15:55 America/New_York;
- weekdays only by scheduler gate.

The in-process autoscan loop sleeps for the configured interval and calls `scheduler.run_full_scan` only when `scheduler.is_market_hours(config)` is true.

The scheduler has an overlap lock. A new scan/manual analyze does not start while another scan owns the lock.

## Candidate capacity

Current deep-analysis cap: **30 candidates per scan**.

40 is the preferred next ceiling only if CAP-40 proves a benefit after GPT-5.6 migration and setup-family admission integration. Ranks 31-60 are already captured by near-cut telemetry, so the scanner can measure whether ranks 31-40 contain valid missed opportunities before paying for ten extra model calls.

A cap increase must satisfy:

1. incremental actionable recall is real;
2. worst-case scan duration remains comfortably below 15 minutes;
3. API rate/cost budget is acceptable;
4. no candidate-cap increase is being used to compensate for weak prefilter logic.

The production cap stays at 30 through the committed CAP-40C observation window unless that study is explicitly invalidated and restarted under a new predeclared plan.

## Operator commands

Verified command surface in `main.py`:

- `!scan` — full manual universe scan;
- `!analyze TICKER` — single-ticker manual analysis;
- `!status` — loaded ticker count, selected model, scheduler state and last-scan summary;
- `!autoscan start` / `!autoscan stop`;
- `!audit <scan_id|TICKER> [json]`;
- `!auditready [rows] [json]`;
- `!auditshy [rows] [json]`;
- `!archivestatus` — CAP-40D research-archive health and pre/post-restart persistence anchors;
- `!help`.

Audit commands and `!archivestatus` remain operator-gated by the same `audit_access` configuration.

## State and telemetry

Alert state file under current config:

`.state/alert_history.json`

Scan telemetry file is maintained separately by the telemetry module. It must remain isolated from alert history.

Phase-14V telemetry is intentionally bounded at 300 scan summaries and 9,000 decision traces. That bound protects runtime storage and must not be enlarged casually to solve a research-retention problem.

Never treat telemetry-write failure as permission to modify market judgment.

## CAP-40D forward research archive

CAP-40C and R4H-3C require multi-week forward cohorts. The 9,000-trace Phase-14V ring cannot retain the full committed 2026-08-20 through 2026-09-30 observation window at current scan throughput, so CAP-40D adds a separate research archive.

Configured archive:

`.state/research_archive/`

Contract:

- enabled in `config/doctrine_config.yaml` under `research_archive`;
- one compact JSONL batch per completed universe scan;
- partitioned by America/New_York session date as `YYYY-MM-DD.jsonl`;
- 120-day retention;
- 10 MiB safety ceiling per daily partition;
- whitelist-only research fields (`velocity_observation`, `four_hour_real`, CAP-40 boundary block and minimal identity/rank fields);
- no Discord payloads, dedup keys, model prose, secrets, bar arrays, or alert-state snapshots;
- no market-data or model call;
- no tier, capital, routing, suppression, candidate-cap, cadence, universe, setup-family, or real-4H authority.

The scheduler attempts CAP-40D persistence in a separate failure domain after Phase-14V persistence. A Phase-14V write failure does not prevent the archive attempt. An archive failure cannot change the scan result.

Manual `!analyze` is not part of the committed forward universe cohort and does not write CAP-40D scan batches.

## CAP-40E archive health probe

`!archivestatus` is a read-only, operator-gated health probe over the configured CAP-40D directory. It accepts no arbitrary filesystem path and performs no archive write.

It reports:

- health state (`READY`, `DEGRADED`, `EMPTY`, `MISSING_DIRECTORY`, `PATH_COLLISION`, `DISABLED`);
- partition count/range and byte counts;
- current ET session date and whether a matching partition exists;
- oldest and latest retained scan-id anchors;
- latest scan timestamp/trace count;
- malformed latest-tail line count and read-error class when applicable.

The command always states that **one snapshot does not prove durability**. Durability requires a pre-restart anchor to remain present after Railway restart/redeploy.

### Railway durability validation — mandatory

GitHub code cannot prove whether Railway preserves a filesystem path across restart/redeploy. Before CAP-40C/R4H-3C evidence is treated as safely accruing, verify in Railway that `.state/research_archive/` resides on durable persistent storage (normally the same persistent volume family used for state, or an equivalent durable volume).

Operational validation sequence using CAP-40E:

1. deploy the green CAP-40D + CAP-40E production commits;
2. after a completed universe scan, run `!archivestatus` in an authorized operator channel;
3. record the oldest/latest scan-id anchors and total/latest-partition byte counts;
4. restart/redeploy the Railway service without deleting persistent storage;
5. run `!archivestatus` again and confirm the prior anchor is still present and bytes did not reset;
6. allow another completed universe scan;
7. run `!archivestatus` again and confirm the latest anchor/bytes advance rather than replacing prior history;
8. confirm `.state/alert_history.json`, normal Phase-14V telemetry, alerts and scanner behavior remain intact;
9. if any persistence check fails, classify the forward study as **NOT SAFELY ACCRUING** until storage is corrected. Do not reconstruct lost evidence from later prices.

Repository merge alone and a single `!archivestatus` snapshot are not proof of this operational requirement.

### Offline forward-study inputs

The VELOCITY and CAP-40 dataset builders accept either:

- `--telemetry <saved Phase-14V ledger>` for bounded/recent research; or
- `--archive-dir <CAP-40D directory>` for the full forward window.

Optional `--start-date` / `--end-date` filters limit archive partitions deterministically.

For the committed full-window CAP-40C/R4H-3C studies, use the durable CAP-40D archive once Phase-14V ring retention would otherwise roll off earlier observations.

## Pre-deploy checklist

Before merging a strategy/runtime change:

1. branch is based on current `main`;
2. scope is explicit;
3. focused regression tests exist for the changed contract;
4. `python -m compileall -q src tests main.py` passes;
5. `python -m pytest -q` passes through the permanent GitHub Actions gate;
6. PR diff is reviewed for unrelated strategy drift;
7. config changes are intentional and named;
8. no secret is committed;
9. real-4H authority has not changed unless the PR is explicitly an authority handoff;
10. candidate cap/universe/cadence/routing remain unchanged unless explicitly in scope;
11. for CAP-40D changes, Phase-14V trace limits remain unchanged and archive failure remains isolated from judgment/state;
12. for CAP-40E changes, the probe remains read-only/operator-gated and cannot certify durability from a single snapshot;
13. for any forward-study change, verify the predeclared sampling frame/window was not silently altered.

## AI-1 Railway cutover

After the AI-1 PR is green and merged:

1. add/verify `OPENAI_API_KEY` in Railway;
2. set `OPENAI_MODEL=gpt-5.6` or leave it absent to use the repo default;
3. redeploy/restart;
4. confirm service reaches `Bot ready` / `Starting Market Wizard Bot`;
5. run `!status` and confirm model reports `gpt-5.6`, expected ticker count and 15-minute cadence;
6. run one controlled `!analyze` and confirm a strict signal reaches deterministic tiering;
7. verify model API/rate failure is treated as a MODEL failure, not as a bearish/WAIT market judgment;
8. during market hours, verify one scan reaches data -> prefilter -> GPT-5.6 -> final tier -> dedup -> Discord/state;
9. confirm telemetry failure, if any, is isolated and does not stop alert state;
10. after successful cutover, remove obsolete Railway Anthropic secrets/overrides so they cannot confuse operations.

## Data-retention contract

AI-1 sends Responses API requests with `store=False`. Do not remove that setting casually; changing model-response retention is an explicit data-control change.

CAP-40D retention concerns only locally generated compact research evidence. It does not change OpenAI response retention or store model response bodies.

CAP-40E reads only bounded metadata/anchors from that local archive and adds no new stored research payload.

## Rollback rule

Rollback by returning GitHub/Railway to the last known-green production commit. Do not attempt an emergency strategy rewrite directly in runtime configuration unless that configuration was designed as an explicit runtime control.

If CAP-40D must be rolled back, the production scanner may continue operating on the prior green commit, but the committed multi-week forward studies must be marked unsafe/incomplete for any interval whose research archive was not durably captured. Do not backfill missing scan-time evidence from hindsight.

CAP-40E can be rolled back independently because it is a read-only operator surface; removing the probe does not alter the CAP-40D archive writer or trading logic.

## Incident classification

Keep these distinct:

- DATA: provider empty/error/stale/malformed bars;
- MODEL: OpenAI API/schema/rate-limit failure;
- JUDGMENT: deterministic gate/logic failure;
- DELIVERY: Discord routing/send failure;
- STATE: alert-history read/write failure;
- TELEMETRY: bounded Phase-14V observational-ledger failure;
- RESEARCH_ARCHIVE: CAP-40D append/retention/durability failure;
- ARCHIVE_PROBE: CAP-40E read-only status/anchor failure;
- CONFIG: missing/invalid environment or YAML;
- CAPACITY: scan duration/rate budget/candidate-cut pressure.

A DATA or MODEL failure is not a bearish/WAIT market verdict. A telemetry/research-archive/probe failure is not a trading failure, but a research-archive failure can invalidate forward-study completeness if evidence is lost.
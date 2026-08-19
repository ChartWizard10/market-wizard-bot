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

## Operator commands

Verified command surface in `main.py`:

- `!scan` — full manual universe scan;
- `!analyze TICKER` — single-ticker manual analysis;
- `!status` — loaded ticker count, selected model, scheduler state and last-scan summary;
- `!autoscan start` / `!autoscan stop`;
- `!audit <scan_id|TICKER> [json]`;
- `!auditready [rows] [json]`;
- `!auditshy [rows] [json]`;
- `!help`.

Audit commands remain operator-gated by configuration.

## State and telemetry

Alert state file under current config:

`.state/alert_history.json`

Scan telemetry file is maintained separately by the telemetry module. It must remain isolated from alert history.

Never treat telemetry-write failure as permission to modify market judgment.

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
9. real-4H authority has not changed unless the PR is explicitly R4H-2;
10. candidate cap/universe/cadence/routing remain unchanged unless explicitly in scope.

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

## Rollback rule

Rollback by returning GitHub/Railway to the last known-green production commit. Do not attempt an emergency strategy rewrite directly in runtime configuration unless that configuration was designed as an explicit runtime control.

## Incident classification

Keep these distinct:

- DATA: provider empty/error/stale/malformed bars;
- MODEL: OpenAI API/schema/rate-limit failure;
- JUDGMENT: deterministic gate/logic failure;
- DELIVERY: Discord routing/send failure;
- STATE: alert-history read/write failure;
- TELEMETRY: observational ledger failure;
- CONFIG: missing/invalid environment or YAML;
- CAPACITY: scan duration/rate budget/candidate-cut pressure.

A DATA or MODEL failure is not a bearish/WAIT market verdict. An observability failure is not a trading failure.

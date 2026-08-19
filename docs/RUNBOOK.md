# Production Runbook

Runtime platform: Railway.
Alert surface: Discord.
Durable source of truth: GitHub repository.

This runbook records only behavior verified in the repository. Railway project-level settings that are not committed here must be checked in Railway rather than guessed.

## Application entry point

Production Python entry point: `main.py`.

Local equivalent:

```bash
python main.py
```

`main.py` loads `config/doctrine_config.yaml`, validates environment, builds the Discord/Anthropic clients, loads `prompts/market_wizard_system.md`, registers commands, and starts the bot.

## Required/recognized environment

Required for bot authentication:

- `DISCORD_TOKEN`

Required for Claude-backed `!scan` / `!analyze` and scheduled deep analysis:

- `ANTHROPIC_KEY`

Optional runtime model override:

- `ANTHROPIC_MODEL`

Model resolution order is:

1. non-empty `ANTHROPIC_MODEL` environment value;
2. `config.claude.model`;
3. code fallback.

Discord channel environment overrides recognized by `src/discord_alerts.py`:

- `DISCORD_SNIPE_CHANNEL_ID`
- `DISCORD_STARTER_CHANNEL_ID`
- `DISCORD_NEAR_ENTRY_CHANNEL_ID`

If an override is absent, the corresponding channel ID in `config/doctrine_config.yaml` is used.

Never commit live secrets.

## Startup expectations

`main.validate_startup` treats:

- missing `DISCORD_TOKEN` as a hard startup error;
- missing `ANTHROPIC_KEY` as a warning, with Claude-backed commands expected to fail gracefully.

The system prompt must be readable from `prompts/market_wizard_system.md` for Claude analysis.

## Scheduled scanning

Configured schedule:

- interval: 15 minutes;
- market-hours only: true;
- window: 09:35–15:55 America/New_York;
- weekdays only by scheduler gate.

The in-process autoscan loop sleeps for the configured interval and calls `scheduler.run_full_scan` only when `scheduler.is_market_hours(config)` is true.

The scheduler has an overlap lock. A new scan/manual analyze does not start while another scan owns the lock.

## Operator commands

Verified command surface in `main.py`:

- `!scan` — full manual universe scan;
- `!analyze TICKER` — single-ticker manual analysis;
- `!status` — loaded ticker count, scheduler state and last-scan summary;
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
10. candidate cap/universe/cadence/model/routing remain unchanged unless explicitly in scope.

## Post-merge Railway validation

After Railway deploy/restart:

1. confirm the service reaches the `Bot ready` / `Starting Market Wizard Bot` path;
2. run `!status` and confirm the expected ticker count and scan cadence;
3. confirm configured Discord channels resolve;
4. confirm Claude model-selection log reflects the intended environment/config source;
5. verify no repeated startup loop or scan-overlap error;
6. during market hours, verify one scan reaches data -> prefilter -> Claude -> final tier -> dedup -> Discord/state without unexpected exceptions;
7. confirm telemetry failure, if any, is isolated and does not stop alert state.

## Rollback rule

Rollback by returning GitHub/Railway to the last known-green production commit. Do not attempt an emergency strategy rewrite directly in runtime configuration unless that configuration was designed as an explicit runtime control (for example the model environment override).

## Incident classification

Keep these distinct:

- DATA: provider empty/error/stale/malformed bars;
- MODEL: Anthropic API/JSON/rate-limit failure;
- JUDGMENT: deterministic gate/logic failure;
- DELIVERY: Discord routing/send failure;
- STATE: alert-history read/write failure;
- TELEMETRY: observational ledger failure;
- CONFIG: missing/invalid environment or YAML;
- CAPACITY: scan duration/rate budget/candidate-cut pressure.

A DATA or MODEL failure is not a bearish/WAIT market verdict. An observability failure is not a trading failure.
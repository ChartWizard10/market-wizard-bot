# Production Runbook

Runtime platform: Railway.
Alert surface: Discord.
Durable source of truth: GitHub repository.
Intended deep-analysis model: OpenAI GPT-5.6.

This runbook records repository-verified behavior. Railway project-level settings that are not committed here must be checked in Railway rather than guessed.

## Application entry point

Production Python entry point: `main.py`.

Local equivalent:

```bash
python main.py
```

`main.py` loads `config/doctrine_config.yaml`, validates environment, builds runtime clients, loads `prompts/market_wizard_system.md`, registers commands, and starts the bot.

## Important provider-alignment status

Current `main` entering P0 still uses Anthropic in code. Operator intent is GPT-5.6. Therefore two states must not be confused:

### Current deployed-code contract before AI-1

- `ANTHROPIC_KEY` is required for the legacy deep-analysis client;
- `ANTHROPIC_MODEL` can override the legacy model;
- `requirements.txt` installs `anthropic`;
- `main.py` instantiates `anthropic.AsyncAnthropic`.

### Target contract after AI-1

- `OPENAI_API_KEY` will authenticate the deep-analysis client;
- `OPENAI_MODEL` will select the runtime model with `gpt-5.6` as the production default/flagship target;
- OpenAI Structured Outputs will enforce the signal JSON schema;
- Anthropic-specific runtime dependencies/environment will be removed or explicitly quarantined as historical compatibility only.

Do not change Railway secrets to the target names until the AI-1 PR is merged and its deployment checklist explicitly authorizes the cutover.

## Discord environment

Required for bot authentication:

- `DISCORD_TOKEN`

Discord channel environment overrides recognized by `src/discord_alerts.py`:

- `DISCORD_SNIPE_CHANNEL_ID`
- `DISCORD_STARTER_CHANNEL_ID`
- `DISCORD_NEAR_ENTRY_CHANNEL_ID`

If an override is absent, the corresponding channel ID in `config/doctrine_config.yaml` is used.

Never commit live secrets.

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

## Candidate-cap operations

Current production cap: 30 deep-analysis candidates per scan.

Ranks 31-60 are already recorded by near-cut telemetry without extra deep-analysis calls.

Do not raise the cap merely because 40 sounds safer for recall. CAP-40 requires:

1. GPT-5.6 runtime migration complete;
2. setup-family compiler complete enough that ranking reflects all locked setup families;
3. evidence that ranks 31-40 contain repeatable actionable opportunities missed by 30;
4. worst-case scan duration remains comfortably below the 15-minute cadence;
5. API rate/cost budget is acceptable.

If those conditions pass, 40 is the preferred next ceiling.

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

## Post-merge Railway validation — general

After Railway deploy/restart:

1. confirm the service reaches the `Bot ready` / `Starting Market Wizard Bot` path;
2. run `!status` and confirm the expected ticker count and scan cadence;
3. confirm configured Discord channels resolve;
4. verify no repeated startup loop or scan-overlap error;
5. during market hours, verify one scan reaches data -> prefilter -> model -> final tier -> dedup -> Discord/state without unexpected exceptions;
6. confirm telemetry failure, if any, is isolated and does not stop alert state.

## AI-1 GPT-5.6 cutover checklist

Only after the migration PR is green and merged:

1. add/verify `OPENAI_API_KEY` in Railway;
2. set `OPENAI_MODEL=gpt-5.6` unless the merged config/runbook specifies a tested snapshot instead;
3. redeploy;
4. confirm startup reports the intended OpenAI model source without printing secrets;
5. run one controlled `!analyze` and verify strict signal-schema output reaches deterministic tiering;
6. verify API/rate failure remains classified as MODEL failure, not WAIT;
7. verify autoscan and manual analysis still share the same post-tiering judgment organ;
8. verify alert/state/telemetry contracts are unchanged;
9. remove legacy Anthropic Railway secrets only after successful GPT-5.6 validation and only if the merged migration explicitly removes fallback support.

## Rollback rule

Rollback by returning GitHub/Railway to the last known-green production commit. Do not attempt an emergency strategy rewrite directly in runtime configuration unless that configuration was designed as an explicit runtime control.

## Incident classification

Keep these distinct:

- DATA: provider empty/error/stale/malformed bars;
- MODEL: OpenAI/legacy-provider API, schema, timeout, or rate-limit failure;
- JUDGMENT: deterministic gate/logic failure;
- DELIVERY: Discord routing/send failure;
- STATE: alert-history read/write failure;
- TELEMETRY: observational ledger failure;
- CONFIG: missing/invalid environment or YAML;
- CAPACITY: scan duration/rate budget/candidate-cut pressure.

A DATA or MODEL failure is not a bearish/WAIT market verdict. An observability failure is not a trading failure.
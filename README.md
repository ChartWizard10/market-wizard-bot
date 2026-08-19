# Chart Wizard Market Scanner

Production bullish swing-entry scanner for a broad U.S. equity/ETF universe.

The repository—not chat memory—is the durable source of truth for scanner doctrine, architecture, current production state, tests, and deployment procedure.

## Mission

Chart Wizard is a selective structure-first scanner. It is designed to surface `NEAR_ENTRY`, `STARTER`, and `SNIPE_IT` opportunities without forcing every valid setup through one entry standard and without using score as a substitute for proof.

Governing read order:

`Auction Engine -> Trend Engine -> Zone Control -> Opportunity Engine -> Verdict`

Execution grammar:

`Break/Reclaim -> Acceptance -> Retest -> Hold`

Timeframe jurisdiction:

`Weekly context -> Daily permission -> 4H operational location -> 1H trigger proof`

The research objective is to identify bullish swing entries with a realistic structural/volatility path to approximately +8% within five trading sessions. That is an evaluation target, not a guaranteed forecast.

## Production docs

Read these before changing strategy or universe:

- [Scanner Constitution](docs/SCANNER_CONSTITUTION.md)
- [Production Architecture](docs/ARCHITECTURE.md)
- [Current Production State](docs/PRODUCTION_STATE.md)
- [Ticker Universe Management](docs/UNIVERSE_MANAGEMENT.md)
- [Production Runbook](docs/RUNBOOK.md)
- [Production Changelog](docs/CHANGELOG.md)

## Production entry point

```bash
python main.py
```

`main.py` loads `config/doctrine_config.yaml`, validates runtime environment, builds the Discord/Anthropic clients, loads `prompts/market_wizard_system.md`, registers operator commands, and starts the autoscan loop.

## Current high-level pipeline

```text
config/tickers.txt
  -> Daily market data / bar truth
  -> structure-first indicators
  -> algorithmic prefilter + hard vetoes + ranking
  -> top-30 Claude deep analysis
  -> deterministic base tiering
  -> shared post-tiering chart judgment
       trade location
       candle truth
       1H trigger evidence
       MTF alignment
       real 4H shadow evidence
       HTF context
       SNIPE gate audit
       SNIPE ladder
       downgrade-only seal
       calibration
  -> final executable tier
  -> final-tier dedup/cooldown
  -> Discord
  -> alert state
  -> isolated scan telemetry
```

## External verdicts

- `SNIPE_IT` — execution-authorized state; full-size eligibility after the governing proof stack.
- `STARTER` — legitimate reduced-size participation when first proof is strong but full-size proof is incomplete.
- `NEAR_ENTRY` — forming/watch state; no capital; exact upgrade trigger required.
- `WAIT` — no actionable setup; no Discord alert.

SNIPE_IT does not require a perfect 100 score. Internal ladder quality distinguishes `SNIPER_A` from `SNIPER_A_PLUS`.

## Locked setup-family design

The production design must explicitly support:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

The current production-state ledger records which of these are fully implemented and which remain the next doctrine-compiler work. Do not assume a generic `setup_family` label means the deterministic family engine exists.

## Current fixed configuration

From `config/doctrine_config.yaml`:

- scan cadence: 15 minutes;
- market window: 09:35–15:55 ET, weekdays;
- Daily lookback: 18 months;
- Daily minimum bars: 120;
- prefilter minimum score: 55;
- Claude candidate cap: 30 per scan;
- SNIPE_IT score floor: 85;
- STARTER score floor: 75;
- NEAR_ENTRY score floor: 60;
- SNIPE/STARTER R:R floor: 3.0 where computable;
- SNIPE fragile-risk floor: 0.35%;
- cooldown: 60 minutes;
- prohibited indicators: RSI, MACD, Bollinger Bands, Stochastic.

These are strategy/runtime contracts. A ticker-universe update must not silently alter them.

## Current universe

Production universe source:

`config/tickers.txt`

Validated baseline before the next requested expansion: 814 unique symbols.

Universe changes follow [docs/UNIVERSE_MANAGEMENT.md](docs/UNIVERSE_MANAGEMENT.md) and must pass the permanent production CI gate.

## Runtime environment

Required:

- `DISCORD_TOKEN`
- `ANTHROPIC_KEY` for Claude-backed scans/analysis

Optional model override:

- `ANTHROPIC_MODEL`

Optional Discord channel overrides:

- `DISCORD_SNIPE_CHANNEL_ID`
- `DISCORD_STARTER_CHANNEL_ID`
- `DISCORD_NEAR_ENTRY_CHANNEL_ID`

Never commit live secrets.

## Operator commands

- `!scan`
- `!analyze TICKER`
- `!status`
- `!autoscan start`
- `!autoscan stop`
- `!audit <scan_id|TICKER> [json]`
- `!auditready [rows] [json]`
- `!auditshy [rows] [json]`

Manual `!analyze` bypasses universe admission/cooldown for inspection only; it uses the same post-tiering chart-judgment organ as autoscan.

## Authority warnings

- Real 4H is currently shadow/evidence-only; the Phase-14F operational proxy remains production-authoritative until an explicit R4H-2 promotion is validated.
- Higher-timeframe context is evidence-only under the current configuration.
- Claude is a classifier/analyst, not sovereign capital authority.
- Telemetry is observational only.
- WAIT never posts.
- Score cannot rescue failed hard gates.

## Engineering workflow

Production changes follow:

`branch -> focused tests -> full CI -> review -> merge -> Railway validation`

The permanent GitHub Actions gate runs Python 3.13 compile checks and the complete pytest suite.

## Historical root artifacts

`bot.py`, `prototype_backup.py`, and root PDFs are historical artifacts. They are not the governing modular production architecture described above. Do not use them as current doctrine or edit/delete them casually without a dedicated cleanup review.
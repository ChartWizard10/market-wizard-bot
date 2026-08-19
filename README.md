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

`main.py` loads `config/doctrine_config.yaml`, validates runtime environment, builds the Discord/OpenAI clients, loads `prompts/market_wizard_system.md`, registers operator commands, and starts the autoscan loop.

## Current high-level pipeline

```text
config/tickers.txt
  -> Daily market data / bar truth
  -> structure-first indicators
  -> deterministic setup-family evidence
  -> algorithmic prefilter + hard vetoes + ranking
  -> configured GPT-5.6 deep-analysis candidate set
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

## Model boundary

Production deep analysis uses **OpenAI GPT-5.6**.

- default model: `gpt-5.6`;
- runtime override: `OPENAI_MODEL`;
- API: OpenAI Responses API;
- output: strict JSON Schema / Structured Outputs;
- API response storage: disabled (`store=False`).

GPT-5.6 is the analyst/classifier. Deterministic tiering, ladder, seal, invalidation/path law, capital authorization and Discord routing remain sovereign.

AI-1 deliberately retains some historical `claude_*` internal field/function names so provider migration does not simultaneously become a scheduler/telemetry schema migration. Those names are compatibility debt, not the production provider.

## External verdicts

- `SNIPE_IT` — execution-authorized state; full-size eligibility after the governing proof stack.
- `STARTER` — legitimate reduced-size participation when first proof is strong but full-size proof is incomplete.
- `NEAR_ENTRY` — forming/watch state; no capital; exact upgrade trigger required.
- `WAIT` — no actionable setup; no Discord alert.

SNIPE_IT does not require a perfect 100 score. Internal ladder quality distinguishes `SNIPER_A` from `SNIPER_A_PLUS`.

## Locked setup-family design

The production design explicitly targets:

1. `BREAK_RETEST_CONTINUATION`
2. `VCP_BREAK_RETEST`
3. `SMA_CRADLE_CONTINUATION`
4. `GAP_FILL_REVERSAL`

Phase SFC-1 now compiles deterministic completed-Daily evidence for all four families. The next family phase integrates that evidence into admission/readiness without allowing a family label to bypass common execution gates.

## Current fixed configuration

From `config/doctrine_config.yaml`:

- scan cadence: 15 minutes;
- market window: 09:35–15:55 ET, weekdays;
- Daily lookback: 18 months;
- Daily minimum bars: 120;
- prefilter minimum score: 55;
- deep-analysis candidate cap: **30 per scan** during AI-1;
- SNIPE_IT score floor: 85;
- STARTER score floor: 75;
- NEAR_ENTRY score floor: 60;
- SNIPE/STARTER R:R floor: 3.0 where computable;
- SNIPE fragile-risk floor: 0.35%;
- cooldown: 60 minutes;
- prohibited indicators: RSI, MACD, Bollinger Bands, Stochastic.

These are strategy/runtime contracts. A ticker-universe update must not silently alter them.

## 30 vs 40 candidate capacity

40 is the preferred next ceiling only if measured CAP-40 validation proves it improves recall without harming cadence/cost.

The scanner already observes ranks 31-60 through near-cut telemetry without additional model calls. After GPT-5.6 migration and setup-family admission integration, ranks 31-40 will be replayed/inspected for legitimate missed STARTER/SNIPE opportunities. If incremental recall is real and the scan remains comfortably inside the 15-minute budget, the cap can move to 40 in its own reviewed phase.

Do not use a larger cap to compensate for a weak prefilter.

## Current universe

Production universe source:

`config/tickers.txt`

Validated baseline before the next requested expansion: **814 unique symbols**.

Universe changes follow [docs/UNIVERSE_MANAGEMENT.md](docs/UNIVERSE_MANAGEMENT.md) and must pass the permanent production CI gate.

## Runtime environment

Required:

- `DISCORD_TOKEN`
- `OPENAI_API_KEY` for GPT-5.6-backed scans/analysis

Optional model override:

- `OPENAI_MODEL`

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
- GPT-5.6 is a classifier/analyst, not sovereign capital authority.
- Telemetry is observational only.
- WAIT never posts.
- Score cannot rescue failed hard gates.

## Engineering workflow

Production changes follow:

`branch -> focused tests -> full CI -> review -> merge -> Railway validation`

The permanent GitHub Actions gate runs Python 3.13 compile checks and the complete pytest suite.

## Historical root artifacts

`bot.py`, `prototype_backup.py`, and root PDFs are historical artifacts. They are not the governing modular production architecture described above. Do not use them as current doctrine or edit/delete them casually without a dedicated cleanup review.

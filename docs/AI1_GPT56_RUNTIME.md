# AI-1 — GPT-5.6 Runtime Migration

## Objective

Correct production provider truth without changing trading doctrine.

The scanner is built around OpenAI GPT-5.6. AI-1 moves the actual deep-analysis runtime from the historical Anthropic client to OpenAI while preserving deterministic risk authority and all scanner contracts.

## Runtime path

`main.py`

-> `openai.AsyncOpenAI`

-> `OpenAISchedulerCompatClient`

-> OpenAI Responses API

-> strict `market_wizard_signal` JSON Schema

-> hardened signal parser

-> deterministic `tiering.validate`

-> shared post-tiering judgment

-> final tier / dedup / Discord / state

No Anthropic API call exists in this production path.

## Why a compatibility adapter exists

The mature scheduler, telemetry and test suite contain historical Claude-named symbols and counters. Renaming them in the same change as provider migration would create a large unrelated diff and increase regression risk.

AI-1 therefore preserves those internal names temporarily while changing the actual network provider. A later provider-neutral nomenclature phase can rename them with zero strategy change.

## Data controls

Responses API calls set `store=False`.

## Candidate cap

AI-1 does not change the deep-analysis cap. It remains 30.

The proposed 40-candidate cap is deferred to CAP-40 because it is a capacity/recall decision, not a provider-migration side effect. CAP-40 will use existing near-cut ranks 31-60 after setup-family admission integration to prove whether ranks 31-40 contain actionable missed opportunities and whether latency/cost remain acceptable.

## Explicit non-changes

AI-1 does not change:

- ticker universe;
- prefilter scoring weights;
- tier score floors;
- R:R floors;
- fragile-risk floor;
- scan cadence;
- market hours;
- setup-family doctrine;
- real-4H authority;
- cooldown/dedup rules;
- Discord routing;
- capital contracts.

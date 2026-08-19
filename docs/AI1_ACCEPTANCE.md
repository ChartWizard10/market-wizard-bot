# AI-1 Acceptance Contract

Do not merge unless all conditions hold:

1. Production `main.py` instantiates OpenAI, not Anthropic.
2. Default deep-analysis model is `gpt-5.6`.
3. Runtime override is `OPENAI_MODEL`.
4. Model requests use the OpenAI Responses API.
5. Signal output is constrained by strict JSON Schema Structured Outputs.
6. `store=False` is set on model requests.
7. Existing deterministic tiering / ladder / seal remains downstream and sovereign.
8. Autoscan/manual parity remains intact.
9. Candidate cap remains 30 during AI-1.
10. Universe remains 814 during AI-1.
11. Real 4H remains shadow/evidence-only.
12. Full permanent Python 3.13 production test gate is green.
13. Railway cutover uses `OPENAI_API_KEY`; obsolete Anthropic secrets are removed only after a successful GPT-5.6 deploy validation.

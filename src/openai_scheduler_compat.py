"""OpenAI Responses API adapter for the hardened scheduler model-call contract.

Phase AI-1 deliberately preserves the existing scheduler/telemetry function
surface while moving the actual provider to OpenAI GPT-5.6. This adapter makes
an AsyncOpenAI client look like the small `.messages.create(...)` interface the
legacy model-boundary wrapper expects. It does NOT call Anthropic.

Once provider-neutral scheduler naming is migrated in a separate phase, this
compatibility adapter can be removed without changing trading doctrine.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.model_client import SIGNAL_JSON_SCHEMA, resolve_model


class _MessagesAdapter:
    def __init__(self, openai_client, config: dict):
        self._client = openai_client
        self._config = config

    async def create(self, *, model, max_tokens, system, messages):
        # The legacy `model` argument is intentionally ignored. Canonical model
        # routing is OPENAI_MODEL -> config.model.name -> gpt-5.6.
        selected_model, _source = resolve_model(self._config)
        model_cfg = self._config.get("model", {}) if isinstance(self._config, dict) else {}
        model_cfg = model_cfg if isinstance(model_cfg, dict) else {}
        reasoning_effort = str(model_cfg.get("reasoning_effort", "medium") or "medium").strip()

        user_text = ""
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                user_text = str(last.get("content") or "")

        kwargs = {
            "model": selected_model,
            "instructions": system,
            "input": user_text,
            "max_output_tokens": int(model_cfg.get("max_output_tokens", max_tokens or 1200)),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "market_wizard_signal",
                    "schema": SIGNAL_JSON_SCHEMA,
                    "strict": True,
                }
            },
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}

        response = await self._client.responses.create(**kwargs)
        output_text = str(getattr(response, "output_text", "") or "")
        if not output_text.strip():
            raise RuntimeError("OpenAI response contained no output_text")

        # Shape expected by the hardened legacy parser wrapper.
        return SimpleNamespace(content=[SimpleNamespace(text=output_text)])


class OpenAISchedulerCompatClient:
    """Expose `.messages.create` while executing only through OpenAI Responses."""

    def __init__(self, openai_client, config: dict):
        self.messages = _MessagesAdapter(openai_client, config)

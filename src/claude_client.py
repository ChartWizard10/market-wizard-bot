"""Async Claude API wrapper. Sends structured prompts, validates strict JSON responses. Implemented in Phase 4."""


def build_prompt(enriched: dict) -> str:
    """Build structured context string for Claude. No disabled indicators included."""
    raise NotImplementedError("Implemented in Phase 4")


def parse_and_validate_json(response_text: str) -> tuple:
    """Parse Claude response, validate required keys and enum values.

    Returns (signal_dict, error_message). On failure: (None, error_message).
    """
    raise NotImplementedError("Implemented in Phase 4")


async def claude_call(enriched: dict, system_prompt: str, client, semaphore, config: dict) -> tuple:
    """Send one ticker to Claude. Returns (signal_dict, error_message)."""
    raise NotImplementedError("Implemented in Phase 4")


async def async_claude_scan(candidates: list, system_prompt: str, client, config: dict) -> list:
    """Run Claude analysis on all candidates with concurrency limit. Returns list of raw signal dicts."""
    raise NotImplementedError("Implemented in Phase 4")

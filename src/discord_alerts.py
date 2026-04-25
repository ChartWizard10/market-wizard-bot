"""Build and route Discord alerts from validated signal dicts only. Implemented in Phase 7."""


def format_alert(signal: dict) -> dict:
    """Build Discord embed payload from validated signal fields. No prose inference."""
    raise NotImplementedError("Implemented in Phase 7")


async def route_and_post(signal: dict, bot, config: dict) -> bool:
    """Route signal to correct channel by tier. WAIT never posts.

    Returns True if posted, False if suppressed or routing failed.
    Logs ROUTING_FAILURE if channel ID is null — does not raise.
    """
    raise NotImplementedError("Implemented in Phase 7")

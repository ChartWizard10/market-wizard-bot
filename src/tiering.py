"""Deterministic tier validation. Final authority over all tier decisions. Implemented in Phase 5."""

TIERS = ("SNIPE_IT", "STARTER", "NEAR_ENTRY", "WAIT")

CHANNEL_MAP = {
    "SNIPE_IT": "#snipe-signals",
    "STARTER": "#starter-signals",
    "NEAR_ENTRY": "#near-entry-watch",
    "WAIT": "none",
}

CAPITAL_MAP = {
    "SNIPE_IT": "full_quality_allowed",
    "STARTER": "starter_only",
    "NEAR_ENTRY": "wait_no_capital",
    "WAIT": "no_trade",
}


def validate(raw_signal: dict, enriched: dict, config: dict) -> dict:
    """Apply all hard vetoes and tier gates. Returns validated signal dict.

    Claude's tier is the starting point only. This function may downgrade it.
    This function is the sole final authority — Claude cannot override its output.
    """
    raise NotImplementedError("Implemented in Phase 5")

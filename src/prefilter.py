"""Algorithmic prefilter scorer. Ranks tickers before Claude. Implemented in Phase 3."""


def algo_score(enriched: dict, config: dict) -> int:
    """Score a ticker 0–100 using configured weights. Returns int."""
    raise NotImplementedError("Implemented in Phase 3")


def apply_hard_vetoes(enriched: dict, config: dict) -> tuple:
    """Apply pre-Claude hard vetoes. Returns (passes, veto_reason)."""
    raise NotImplementedError("Implemented in Phase 3")


def prefilter(enriched_list: list, config: dict) -> list:
    """Score, veto, rank, and cap candidates for Claude analysis."""
    raise NotImplementedError("Implemented in Phase 3")

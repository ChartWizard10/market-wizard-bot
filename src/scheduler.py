"""Auto-scan scheduler with market hours gate and overlap lock. Implemented in Phase 8."""
import asyncio


_scan_lock = asyncio.Lock()


def is_market_hours(config: dict) -> bool:
    """Return True if current ET time is within configured market hours on a weekday."""
    raise NotImplementedError("Implemented in Phase 8")


async def run_full_scan(bot, config: dict) -> dict:
    """Execute the full pipeline: fetch → enrich → prefilter → Claude → tiering → dedup → alert.

    Returns scan summary dict. Acquires _scan_lock; skips if already running.
    """
    raise NotImplementedError("Implemented in Phase 8")

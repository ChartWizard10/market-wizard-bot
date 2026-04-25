"""Structure-first feature extraction. No rsi, macd, bollinger_bands, or stochastic. Implemented in Phase 2."""


def enrich(ticker: str, df, config: dict) -> dict:
    """Compute all structure-first features for a ticker DataFrame.

    Returns a dict with: sma20, sma50, sma200, value_alignment, swing_high, swing_low,
    liquidity_pools, sweep, structure_event, fvg, ob_zone, retest_status, overhead_status,
    estimated_invalidation, estimated_targets, estimated_rr, volume_expansion_ratio,
    volume_dryup_ratio, atr.
    """
    raise NotImplementedError("Implemented in Phase 2")

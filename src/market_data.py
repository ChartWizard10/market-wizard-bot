"""Fetch and validate OHLCV data from yfinance. Implemented in Phase 2."""


def batch_download(tickers: list, config: dict) -> dict:
    """Download 18mo daily OHLCV for all tickers in batches. Returns per-ticker DataFrames."""
    raise NotImplementedError("Implemented in Phase 2")


def validate_ticker_data(ticker: str, df, config: dict) -> tuple:
    """Validate bar count and staleness. Returns (is_valid, skip_reason)."""
    raise NotImplementedError("Implemented in Phase 2")

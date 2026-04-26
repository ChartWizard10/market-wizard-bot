"""Market data tests — Phase 2."""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np
import pytest

from src.market_data import validate_ticker_data, fetch_ticker, _normalize, _extract_ticker_df, batch_download

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "data": {
        "min_daily_bars": 120,
        "max_staleness_days": 2,
        "lookback_period": "18mo",
        "interval": "1d",
        "fetch_batch_size": 100,
        "fetch_delay_seconds": 0.0,
    }
}


def _make_df(n_bars: int, last_date_offset_days: int = 0) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame with approximately n_bars rows."""
    # Use a fixed past weekday anchor to avoid weekend/holiday boundary issues
    anchor = date(2025, 1, 2)  # known Thursday
    end = anchor - timedelta(days=last_date_offset_days)
    idx = pd.bdate_range(end=end, periods=n_bars)
    n = len(idx)
    np.random.seed(42)
    closes = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": closes - 0.2,
        "high": closes + 0.5,
        "low": closes - 0.5,
        "close": closes,
        "volume": np.random.randint(1_000_000, 5_000_000, n).astype(float),
    }, index=idx)
    return df


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_ohlcv_columns_normalized():
    df = _make_df(130)
    assert set(["open", "high", "low", "close", "volume"]).issubset(set(df.columns))
    for col in df.columns:
        assert col == col.lower(), f"Column not lowercase: {col}"


def test_normalize_flattens_multiindex():
    idx = pd.bdate_range(end=date(2025, 1, 2), periods=10)
    n = len(idx)
    arrays = [["open", "high", "low", "close", "volume"], ["AAPL"] * 5]
    mi = pd.MultiIndex.from_arrays(arrays)
    df = pd.DataFrame(np.random.rand(n, 5), index=idx, columns=mi)
    norm = _normalize(df)
    assert list(norm.columns) == ["open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
# Validation — bar count
# ---------------------------------------------------------------------------

def test_thin_data_skipped():
    df = _make_df(90)  # below min_daily_bars=120
    valid, reason = validate_ticker_data("THIN", df, BASE_CONFIG)
    assert not valid
    assert reason.startswith("INSUFFICIENT")


def test_valid_bar_count_passes():
    # Use a recent last-weekday anchor so staleness check also passes
    today = date.today()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    idx = pd.bdate_range(end=today, periods=200)
    n = len(idx)
    closes = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame({
        "open": closes - 0.2, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes,
        "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    valid, reason = validate_ticker_data("OK", df, BASE_CONFIG)
    assert valid, f"Expected valid, got: {reason}"
    assert reason is None


# ---------------------------------------------------------------------------
# Validation — empty
# ---------------------------------------------------------------------------

def test_empty_df_returns_invalid():
    df = pd.DataFrame()
    valid, reason = validate_ticker_data("EMPTY", df, BASE_CONFIG)
    assert not valid
    assert reason == "EMPTY"


def test_none_df_returns_invalid():
    valid, reason = validate_ticker_data("NONE", None, BASE_CONFIG)
    assert not valid
    assert reason == "EMPTY"


# ---------------------------------------------------------------------------
# Validation — staleness
# ---------------------------------------------------------------------------

def test_stale_data_flagged():
    # Build a df whose last bar is explicitly far in the past
    idx = pd.bdate_range(end=date(2024, 1, 1), periods=200)
    n = len(idx)
    closes = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame({
        "open": closes - 0.2, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes,
        "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    valid, reason = validate_ticker_data("STALE", df, BASE_CONFIG)
    assert not valid
    assert reason.startswith("STALE")


def test_recent_data_not_stale():
    # Build a df whose last bar is today (Friday anchor)
    anchor = date.today()
    # Walk back to last weekday
    while anchor.weekday() >= 5:
        anchor -= timedelta(days=1)
    idx = pd.bdate_range(end=anchor, periods=200)
    n = len(idx)
    closes = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame({
        "open": closes - 0.2, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes,
        "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    valid, reason = validate_ticker_data("FRESH", df, BASE_CONFIG)
    assert valid


# ---------------------------------------------------------------------------
# fetch_ticker integration (mocked yfinance)
# ---------------------------------------------------------------------------

def test_fetch_ticker_empty_response_returns_empty_status():
    with patch("src.market_data.yf.download", return_value=pd.DataFrame()):
        result = fetch_ticker("FAKE", BASE_CONFIG)
    assert result["data_status"] == "EMPTY"
    assert result["df"] is None


def test_fetch_ticker_thin_response_returns_insufficient():
    df = _make_df(50)
    with patch("src.market_data.yf.download", return_value=df):
        result = fetch_ticker("THIN", BASE_CONFIG)
    assert result["data_status"] == "INSUFFICIENT"
    assert result["df"] is None


def test_fetch_ticker_valid_response_returns_ok():
    today = date.today()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    idx = pd.bdate_range(end=today, periods=200)
    n = len(idx)
    closes = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame({
        "open": closes - 0.2, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes,
        "volume": np.ones(n) * 1_000_000,
    }, index=idx)
    with patch("src.market_data.yf.download", return_value=df):
        result = fetch_ticker("GOOD", BASE_CONFIG)
    assert result["data_status"] == "OK", f"Got: {result['data_status']} / {result['error']}"
    assert result["df"] is not None
    assert result["bars"] == n
    assert result["latest_close"] is not None


def test_fetch_ticker_exception_returns_error():
    with patch("src.market_data.yf.download", side_effect=Exception("network error")):
        result = fetch_ticker("ERR", BASE_CONFIG)
    assert result["data_status"] == "ERROR"
    assert "network error" in result["error"]


# ---------------------------------------------------------------------------
# _extract_ticker_df — MultiIndex shape handling
# ---------------------------------------------------------------------------

def _make_mi_field_ticker(ticker: str, n: int = 10) -> pd.DataFrame:
    """(field, ticker) MultiIndex — default yfinance orientation."""
    idx = pd.bdate_range(end=date(2025, 1, 2), periods=n)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    mi = pd.MultiIndex.from_arrays([fields, [ticker] * 5])
    return pd.DataFrame(np.ones((n, 5)) * 100.0, index=idx, columns=mi)


def _make_mi_ticker_field(ticker: str, n: int = 10) -> pd.DataFrame:
    """(ticker, field) MultiIndex — group_by='ticker' orientation (the buggy shape)."""
    idx = pd.bdate_range(end=date(2025, 1, 2), periods=n)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    mi = pd.MultiIndex.from_arrays([[ticker] * 5, fields])
    return pd.DataFrame(np.ones((n, 5)) * 100.0, index=idx, columns=mi)


def test_extract_ticker_df_flat_no_multiindex():
    """single=True returns flat df with lowercased columns."""
    df = _make_df(10)
    result = _extract_ticker_df(df, "AAPL", single=True)
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert len(result) == 10


def test_extract_ticker_df_field_ticker_multiindex():
    """(field, ticker) MultiIndex — ticker at level 1 → correct extraction."""
    raw = _make_mi_field_ticker("AAPL")
    result = _extract_ticker_df(raw, "AAPL", single=False)
    assert set(result.columns) == {"open", "high", "low", "close", "volume"}


def test_extract_ticker_df_ticker_field_multiindex():
    """(ticker, field) MultiIndex — ticker at level 0 → correct extraction (was the bug)."""
    raw = _make_mi_ticker_field("AAPL")
    result = _extract_ticker_df(raw, "AAPL", single=False)
    assert set(result.columns) == {"open", "high", "low", "close", "volume"}


def test_extract_ticker_df_missing_ticker_raises_key_error():
    """Ticker absent from both MultiIndex levels → KeyError."""
    raw = _make_mi_field_ticker("AAPL")
    with pytest.raises(KeyError):
        _extract_ticker_df(raw, "NVDA", single=False)


def test_batch_download_multi_ticker_field_ticker_orientation():
    """batch_download handles (field, ticker) MultiIndex and returns OK for all tickers."""
    today = date.today()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    n = 200
    idx = pd.bdate_range(end=today, periods=n)
    test_tickers = ["AAPL", "NVDA"]
    fields = ["Close", "High", "Low", "Open", "Volume"]
    mi = pd.MultiIndex.from_product([fields, test_tickers])
    raw = pd.DataFrame(np.ones((n, len(fields) * len(test_tickers))) * 100.0, index=idx, columns=mi)

    with patch("src.market_data.yf.download", return_value=raw):
        results = batch_download(test_tickers, BASE_CONFIG)

    for t in test_tickers:
        assert results[t]["data_status"] == "OK", f"{t}: {results[t].get('error')}"
        assert results[t]["df"] is not None


def test_batch_download_missing_ticker_falls_back_to_fetch_ticker():
    """Ticker absent from batch response triggers individual fetch_ticker fallback."""
    today = date.today()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    n = 200
    idx = pd.bdate_range(end=today, periods=n)

    # Batch raw contains only AAPL — NVDA is absent
    fields = ["Close", "High", "Low", "Open", "Volume"]
    mi = pd.MultiIndex.from_arrays([fields, ["AAPL"] * 5])
    raw_batch = pd.DataFrame(np.ones((n, 5)) * 100.0, index=idx, columns=mi)

    fallback_result = {
        "ticker": "NVDA", "bars": n, "latest_close": 150.0,
        "latest_date": str(today), "data_status": "OK",
        "df": MagicMock(), "error": None,
    }

    with (
        patch("src.market_data.yf.download", return_value=raw_batch),
        patch("src.market_data.fetch_ticker", return_value=fallback_result) as mock_fallback,
    ):
        results = batch_download(["AAPL", "NVDA"], BASE_CONFIG)

    mock_fallback.assert_called_once_with("NVDA", BASE_CONFIG)
    assert results["NVDA"]["data_status"] == "OK"

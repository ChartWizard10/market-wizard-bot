"""Fetch and validate OHLCV data from yfinance."""

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ticker universe loader
# ---------------------------------------------------------------------------

_VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")


def load_tickers(path: str) -> dict:
    """Load and validate the ticker universe from a flat text file.

    Rules:
    - Blank lines ignored.
    - Lines starting with # ignored.
    - Tickers normalized to uppercase.
    - Duplicates removed; first occurrence preserved; file order maintained.
    - Valid characters: A-Z, 0-9, dot, dash. No spaces, slashes, commas, etc.
    - Does NOT fetch market data. Format validation only.
    - Potentially delisted or unfetchable tickers are NOT removed — that is
      the fetch layer's responsibility.

    Returns dict with:
      tickers              validated, deduplicated, order-preserved list
      validation_summary   counts and sample tickers
    """
    file_path = Path(path)
    if not file_path.exists():
        log.error("Ticker file not found: %s", path)
        return {
            "tickers": [],
            "validation_summary": {
                "raw_line_count": 0,
                "valid_ticker_count": 0,
                "duplicate_count": 0,
                "invalid_count": 0,
                "invalid_tickers": [],
                "first_10_tickers": [],
                "last_10_tickers": [],
                "error": f"file not found: {path}",
            },
        }

    raw_lines = file_path.read_text().splitlines()
    raw_line_count = len(raw_lines)

    seen: set = set()
    tickers: list = []
    duplicates: list = []
    invalid: list = []

    for line in raw_lines:
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        normalized = stripped.upper()

        # Reject malformed symbols
        if not _VALID_TICKER_RE.match(normalized):
            log.warning("INVALID_TICKER rejected: %r", stripped)
            invalid.append(stripped)
            continue

        # Deduplicate — preserve first occurrence
        if normalized in seen:
            duplicates.append(normalized)
            continue

        seen.add(normalized)
        tickers.append(normalized)

    return {
        "tickers": tickers,
        "validation_summary": {
            "raw_line_count": raw_line_count,
            "valid_ticker_count": len(tickers),
            "duplicate_count": len(duplicates),
            "invalid_count": len(invalid),
            "invalid_tickers": invalid,
            "first_10_tickers": tickers[:10],
            "last_10_tickers": tickers[-10:],
        },
    }

_REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase all column names; flatten MultiIndex columns from yfinance batch downloads."""
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance batch download returns (field, ticker) MultiIndex — drop ticker level
        df = df.xs(df.columns.get_level_values(1)[0], axis=1, level=1)
    df.columns = [c.lower() for c in df.columns]
    return df


def _last_market_date() -> datetime:
    """Return today if weekday, else last Friday."""
    today = datetime.utcnow().date()
    offset = max(0, today.weekday() - 4)  # Saturday→1, Sunday→2
    return datetime.combine(today - timedelta(days=offset), datetime.min.time())


def validate_ticker_data(ticker: str, df: pd.DataFrame, config: dict) -> tuple:
    """Validate bar count and staleness.

    Returns (is_valid: bool, skip_reason: str | None).
    """
    data_cfg = config.get("data", {})
    min_bars = data_cfg.get("min_daily_bars", 120)
    max_stale = data_cfg.get("max_staleness_days", 2)

    if df is None or df.empty:
        return False, "EMPTY"

    if len(df) < min_bars:
        return False, f"INSUFFICIENT:{len(df)}<{min_bars}"

    last_date = pd.to_datetime(df.index[-1]).date()
    market_today = _last_market_date().date()
    gap = (market_today - last_date).days
    # Convert calendar days to approximate market days (exclude weekends)
    market_days_gap = gap - (gap // 7) * 2
    if market_days_gap > max_stale:
        return False, f"STALE:{last_date}"

    return True, None


def fetch_ticker(ticker: str, config: dict) -> dict:
    """Download 18mo daily OHLCV for a single ticker. Returns structured result dict."""
    data_cfg = config.get("data", {})
    period = data_cfg.get("lookback_period", "18mo")
    interval = data_cfg.get("interval", "1d")

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        log.warning("FETCH_ERROR: %s: %s", ticker, exc)
        return _error_result(ticker, str(exc))

    if df is None or df.empty:
        return {
            "ticker": ticker,
            "bars": 0,
            "latest_close": None,
            "latest_date": None,
            "data_status": "EMPTY",
            "df": None,
            "error": "empty response from yfinance",
        }

    try:
        df = _normalize(df)
    except Exception as exc:
        return _error_result(ticker, f"normalization failed: {exc}")

    is_valid, skip_reason = validate_ticker_data(ticker, df, config)
    if not is_valid:
        status = skip_reason.split(":")[0]
        return {
            "ticker": ticker,
            "bars": len(df),
            "latest_close": float(df["close"].iloc[-1]) if "close" in df.columns else None,
            "latest_date": str(pd.to_datetime(df.index[-1]).date()),
            "data_status": status,
            "df": None,
            "error": skip_reason,
        }

    return {
        "ticker": ticker,
        "bars": len(df),
        "latest_close": round(float(df["close"].iloc[-1]), 4),
        "latest_date": str(pd.to_datetime(df.index[-1]).date()),
        "data_status": "OK",
        "df": df,
        "error": None,
    }


def batch_download(tickers: list, config: dict) -> dict:
    """Download OHLCV for all tickers in batches. Returns {ticker: result_dict}."""
    data_cfg = config.get("data", {})
    batch_size = data_cfg.get("fetch_batch_size", 100)
    delay = data_cfg.get("fetch_delay_seconds", 0.3)
    period = data_cfg.get("lookback_period", "18mo")
    interval = data_cfg.get("interval", "1d")

    results = {}
    batches = [tickers[i : i + batch_size] for i in range(0, len(tickers), batch_size)]

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            time.sleep(delay)
        try:
            raw = yf.download(
                batch,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
        except Exception as exc:
            log.warning("BATCH_FETCH_ERROR batch %d: %s", batch_idx, exc)
            for t in batch:
                results[t] = _error_result(t, str(exc))
            continue

        for ticker in batch:
            try:
                if len(batch) == 1:
                    # Single-ticker download doesn't produce MultiIndex
                    df = raw.copy()
                    df.columns = [c.lower() for c in df.columns]
                else:
                    if ticker not in raw.columns.get_level_values(1):
                        results[ticker] = _error_result(ticker, "not in batch response")
                        continue
                    df = raw.xs(ticker, axis=1, level=1).copy()
                    df.columns = [c.lower() for c in df.columns]

                is_valid, skip_reason = validate_ticker_data(ticker, df, config)
                if df.empty:
                    results[ticker] = {
                        "ticker": ticker, "bars": 0,
                        "latest_close": None, "latest_date": None,
                        "data_status": "EMPTY", "df": None, "error": "empty",
                    }
                elif not is_valid:
                    status = skip_reason.split(":")[0]
                    results[ticker] = {
                        "ticker": ticker, "bars": len(df),
                        "latest_close": round(float(df["close"].iloc[-1]), 4),
                        "latest_date": str(pd.to_datetime(df.index[-1]).date()),
                        "data_status": status, "df": None, "error": skip_reason,
                    }
                else:
                    results[ticker] = {
                        "ticker": ticker, "bars": len(df),
                        "latest_close": round(float(df["close"].iloc[-1]), 4),
                        "latest_date": str(pd.to_datetime(df.index[-1]).date()),
                        "data_status": "OK", "df": df, "error": None,
                    }
            except Exception as exc:
                log.warning("FETCH_ERROR: %s: %s", ticker, exc)
                results[ticker] = _error_result(ticker, str(exc))

    return results


def _error_result(ticker: str, msg: str) -> dict:
    return {
        "ticker": ticker,
        "bars": 0,
        "latest_close": None,
        "latest_date": None,
        "data_status": "ERROR",
        "df": None,
        "error": msg,
    }

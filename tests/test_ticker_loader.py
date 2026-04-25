"""Ticker universe loader tests — Phase 2.5."""

import tempfile
from pathlib import Path

import pytest

from src.market_data import load_tickers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(lines: list[str]) -> str:
    """Write lines to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write("\n".join(lines) + "\n")
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------

def test_one_ticker_per_line_loads():
    path = _write_file(["AAPL", "MSFT", "NVDA"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT", "NVDA"]
    assert result["validation_summary"]["valid_ticker_count"] == 3


def test_blank_lines_ignored():
    path = _write_file(["AAPL", "", "  ", "MSFT"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT"]
    assert result["validation_summary"]["valid_ticker_count"] == 2


def test_comment_lines_ignored():
    path = _write_file(["# this is a comment", "AAPL", "# another comment", "MSFT"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT"]


def test_lowercase_normalized_to_uppercase():
    path = _write_file(["aapl", "msft", "nvda"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT", "NVDA"]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_duplicates_removed_preserving_first_occurrence():
    path = _write_file(["AAPL", "MSFT", "AAPL", "NVDA", "MSFT"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT", "NVDA"]
    assert result["validation_summary"]["duplicate_count"] == 2


def test_file_order_preserved_after_deduplication():
    path = _write_file(["ZS", "AAPL", "MSFT", "ZS", "NVDA"])
    result = load_tickers(path)
    assert result["tickers"] == ["ZS", "AAPL", "MSFT", "NVDA"]


# ---------------------------------------------------------------------------
# Invalid / malformed tickers
# ---------------------------------------------------------------------------

def test_invalid_tickers_reported_not_crashed():
    path = _write_file(["AAPL", "BAD TICKER", "MSFT", "inv@lid!", "NVDA"])
    result = load_tickers(path)
    assert "AAPL" in result["tickers"]
    assert "MSFT" in result["tickers"]
    assert "NVDA" in result["tickers"]
    assert result["validation_summary"]["invalid_count"] == 2
    assert result["validation_summary"]["valid_ticker_count"] == 3


def test_spaces_inside_symbol_rejected():
    path = _write_file(["AA PL", "MSFT"])
    result = load_tickers(path)
    assert "AA PL" not in result["tickers"]
    assert "MSFT" in result["tickers"]
    assert result["validation_summary"]["invalid_count"] == 1


def test_slash_in_symbol_rejected():
    path = _write_file(["BRK/B", "AAPL"])
    result = load_tickers(path)
    assert "BRK/B" not in result["tickers"]
    assert result["validation_summary"]["invalid_count"] == 1


def test_comma_in_symbol_rejected():
    path = _write_file(["AAPL,MSFT", "NVDA"])
    result = load_tickers(path)
    assert "AAPL,MSFT" not in result["tickers"]
    assert result["validation_summary"]["invalid_count"] == 1


def test_empty_symbol_after_strip_ignored():
    path = _write_file(["AAPL", "   ", "MSFT"])
    result = load_tickers(path)
    assert result["tickers"] == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# Valid edge-case characters
# ---------------------------------------------------------------------------

def test_dot_in_symbol_accepted():
    path = _write_file(["BRK.B", "AAPL"])
    result = load_tickers(path)
    assert "BRK.B" in result["tickers"]


def test_dash_in_symbol_accepted():
    path = _write_file(["BF-B", "AAPL"])
    result = load_tickers(path)
    assert "BF-B" in result["tickers"]


def test_numbers_in_symbol_accepted():
    path = _write_file(["V", "A1B", "AAPL"])
    result = load_tickers(path)
    assert "A1B" in result["tickers"]


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------

def test_validation_summary_correct_counts():
    path = _write_file(["AAPL", "MSFT", "AAPL", "BAD TICKER", "NVDA"])
    result = load_tickers(path)
    s = result["validation_summary"]
    assert s["valid_ticker_count"] == 3
    assert s["duplicate_count"] == 1
    assert s["invalid_count"] == 1
    assert s["raw_line_count"] == 5


def test_first_10_tickers_returned():
    symbols = [f"SYM{i:02d}" for i in range(20)]
    path = _write_file(symbols)
    result = load_tickers(path)
    assert result["validation_summary"]["first_10_tickers"] == symbols[:10]


def test_last_10_tickers_returned():
    symbols = [f"SYM{i:02d}" for i in range(20)]
    path = _write_file(symbols)
    result = load_tickers(path)
    assert result["validation_summary"]["last_10_tickers"] == symbols[10:]


def test_missing_file_returns_empty_safely():
    result = load_tickers("/nonexistent/path/tickers.txt")
    assert result["tickers"] == []
    assert result["validation_summary"]["valid_ticker_count"] == 0
    assert "error" in result["validation_summary"]


# ---------------------------------------------------------------------------
# No market data fetched
# ---------------------------------------------------------------------------

def test_loader_does_not_fetch_market_data(monkeypatch):
    """load_tickers must never call yfinance."""
    called = []

    def fake_download(*a, **kw):
        called.append(True)
        return None

    monkeypatch.setattr("src.market_data.yf.download", fake_download)
    path = _write_file(["AAPL", "MSFT"])
    load_tickers(path)
    assert not called, "load_tickers must not call yf.download"


# ---------------------------------------------------------------------------
# Delisted / unfetchable tickers not auto-removed
# ---------------------------------------------------------------------------

def test_well_formed_potentially_delisted_ticker_kept():
    """A well-formed ticker that may be delisted must NOT be removed by the loader."""
    path = _write_file(["SHLD", "SEARS", "AAPL"])
    result = load_tickers(path)
    assert "SHLD" in result["tickers"], "Potentially delisted SHLD must be kept"
    assert "AAPL" in result["tickers"]


# ---------------------------------------------------------------------------
# Full universe file
# ---------------------------------------------------------------------------

def test_full_universe_loads_correctly():
    """Validate the actual config/tickers.txt against expected counts."""
    result = load_tickers("config/tickers.txt")
    s = result["validation_summary"]
    assert s["valid_ticker_count"] == 811, (
        f"Expected 811 tickers, got {s['valid_ticker_count']}"
    )
    assert s["duplicate_count"] == 0, (
        f"Expected 0 duplicates, got {s['duplicate_count']}"
    )
    assert s["invalid_count"] == 0, (
        f"Expected 0 invalid, got {s['invalid_count']} — check: {s['invalid_tickers']}"
    )
    assert s["first_10_tickers"] == [
        "AA", "AAL", "AAON", "AAPL", "ABAT", "ABBV", "ABCL", "ABNB", "ABOS", "ABT"
    ]
    assert s["last_10_tickers"] == [
        "XPO", "XPOF", "XYL", "YORW", "YUM", "ZBH", "ZBRA", "ZION", "ZS", "ZWS"
    ]

"""Fetch and validate OHLCV data from yfinance."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase MBT-1 — 1H closed/live bar truth and timezone-safe freshness.
#
# Doctrine: a closed candle is evidence; a live candle is information. The
# newest 1H bar may be genuinely still forming (is_open=True) or may already
# be closed even though the provider has not yet published the next interval.
# Every earlier bar is closed by chronological law (a later bar exists).
#
# The newest bar's status is proven from its own absolute timestamp, the
# configured interval, and the regular U.S. equity session close — never
# guessed. If the timestamp's real UTC offset cannot be established (a naive
# pandas index, i.e. the provider gave us no timezone information at all),
# the bar is conservatively treated as still open: unknown timing truth is
# not permission to grant closed-confirmation authority. No third-party
# market-calendar dependency is added; early-close/holiday sessions are not
# specially modeled, which only ever biases toward staying open longer than
# the true close — the safe direction, never a false CLOSED.
# ---------------------------------------------------------------------------

_EASTERN = ZoneInfo("America/New_York")
_SESSION_OPEN_ET = (9, 30)
_SESSION_CLOSE_ET = (16, 0)


def _parse_interval_minutes(interval) -> int:
    """Parse a yfinance-style interval string ('60m', '1h', '30m') to minutes.
    Unparseable input defaults to 60 — the doctrine default for 1H evidence."""
    if not isinstance(interval, str):
        return 60
    s = interval.strip().lower()
    try:
        if s.endswith("h"):
            return int(round(float(s[:-1]) * 60))
        if s.endswith("m"):
            return int(s[:-1])
    except (TypeError, ValueError):
        pass
    return 60


def _bar_time_utc(index_value):
    """Absolute UTC instant for a pandas index entry, or None if the source
    carries no timezone information. Never guesses a provider timezone —
    only converts an offset the data itself actually supplies."""
    try:
        ts = pd.Timestamp(index_value)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        return None
    try:
        return ts.tz_convert("UTC").to_pydatetime()
    except Exception:
        return None


def _interval_end_utc(bar_time_utc: datetime, interval_minutes: int) -> datetime:
    """The UTC instant at which `bar_time_utc`'s interval completes.

    Bars that start within the regular U.S. equity session (09:30-16:00 ET)
    can never run past that session's 16:00 ET close, even if the configured
    interval would nominally extend further (e.g. a 15:30 ET 60m bar closes
    with the session at 16:00 ET, not 16:30 ET).
    """
    nominal_end = bar_time_utc + timedelta(minutes=interval_minutes)
    bar_et = bar_time_utc.astimezone(_EASTERN)
    session_open = bar_et.replace(hour=_SESSION_OPEN_ET[0], minute=_SESSION_OPEN_ET[1],
                                  second=0, microsecond=0)
    session_close = bar_et.replace(hour=_SESSION_CLOSE_ET[0], minute=_SESSION_CLOSE_ET[1],
                                   second=0, microsecond=0)
    if session_open <= bar_et < session_close:
        session_close_utc = session_close.astimezone(timezone.utc)
        return min(nominal_end, session_close_utc)
    return nominal_end


def _resolve_newest_bar_open(bar_time_utc, interval_minutes: int, now_utc: datetime) -> bool:
    """True (open/live/provisional) unless the interval's completion can be
    proven from an absolute timestamp. Conservative Ambiguity Law: any
    unprovable case resolves to open, never to closed."""
    if bar_time_utc is None or now_utc is None:
        return True
    try:
        end = _interval_end_utc(bar_time_utc, interval_minutes)
    except Exception:
        return True
    return now_utc < end


# ---------------------------------------------------------------------------
# Phase MBT-2 — Daily developing/closed bar truth.
#
# A daily row is stamped with its SESSION DATE, so its status is proven from
# that calendar date against the current America/New_York session clock — no
# provider timezone is ever guessed, and no intraday offset is needed.
#
#   bar date < today ET                  -> CLOSED  (a later session exists)
#   bar date == today ET, now  < 16:00ET -> LIVE    (regular session running)
#   bar date == today ET, now >= 16:00ET -> CLOSED  (regular session complete)
#   bar date > today ET / unparseable /
#   non-monotonic index                  -> UNKNOWN (never proven closed)
#
# UNKNOWN is treated exactly like LIVE by every consumer: it withholds
# confirmation authority. Unknown timing truth is not permission.
#
# EARLY-CLOSE / HOLIDAY LIMITATION (documented, deliberate): no market-calendar
# dependency is added, so a 13:00 ET early close is still treated as LIVE until
# 16:00 ET. That only ever DELAYS confirmation — a few hours of false OPEN,
# never a false CLOSED. Confirmation is delayed, never invented.
# ---------------------------------------------------------------------------

_DAILY_STATUS_LIVE = "LIVE"
_DAILY_STATUS_CLOSED = "CLOSED"
_DAILY_STATUS_UNKNOWN = "UNKNOWN"


def _index_date(index_value):
    """Session date for a daily index entry, or None if it cannot be parsed."""
    try:
        ts = pd.Timestamp(index_value)
    except (TypeError, ValueError):
        return None
    try:
        if ts is pd.NaT or ts != ts:      # NaT guard
            return None
        return ts.date()
    except (TypeError, ValueError, AttributeError):
        return None


def _session_dates(index) -> list:
    """Session date per row, None where it cannot be parsed."""
    try:
        if isinstance(index, pd.DatetimeIndex):
            return [None if v is pd.NaT or v != v else v for v in index.date]
    except (TypeError, ValueError, AttributeError):
        pass
    return [_index_date(v) for v in index]


def _session_complete(now_utc: datetime) -> bool:
    """True once the current ET regular session's 16:00 close has passed."""
    now_et = now_utc.astimezone(_EASTERN)
    close = now_et.replace(
        hour=_SESSION_CLOSE_ET[0], minute=_SESSION_CLOSE_ET[1], second=0, microsecond=0
    )
    return now_et >= close


# ---------------------------------------------------------------------------
# Phase MBT-2A — ambiguous-row partition safety.
#
# Confirmation eligibility is decided PER ROW from that row's own validated
# session date. Physical row position is not provenance: a scrambled or
# duplicated index must never promote an unfinished candle into completed
# evidence, and dropping `df.iloc[-1]` proves nothing about the rest.
#
#   date < today ET, unique              -> eligible completed history
#   date == today ET, session complete,
#                     unique             -> eligible
#   date == today ET, session running    -> NOT eligible (developing)
#   date > today ET                      -> NOT eligible (future)
#   date unparseable                     -> NOT eligible
#   date duplicated anywhere in the frame-> NOT eligible for EVERY copy
#
# Duplicate session rows are ambiguity, not extra confirmation: no copy is
# arbitrarily crowned canonical, so the whole duplicated group is withheld.
# Bad ordering alone does not destroy recoverable history — rows with valid,
# unique dates are kept and sorted chronologically before any indicator runs.
# OHLCV is never mutated and no bar is ever synthesized.
# ---------------------------------------------------------------------------

def partition_daily_bars(df, now_utc: datetime | None = None) -> dict:
    """Split a daily frame into confirmation-eligible bars and everything else.

    Returns:
      confirmed_df  rows that earned confirmation authority, chronological
      live_row      the trustworthy developing current-session row, or None
      current_row   the row that owns current price (provider's last row), or None
      context       the canonical `daily_bar_context` provenance object

    Never raises. `using_live_bar_for_confirmation` is a permanent False.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    ctx = {
        "status": _DAILY_STATUS_UNKNOWN,
        "last_closed_daily_date": None,
        "live_daily_date": None,
        "live_bar_available": False,
        "using_live_bar_for_confirmation": False,
        "status_source": "no_bars",
        "confirmed_bars": 0,
        "ambiguous_rows_withheld": 0,
        "current_row_trusted": False,
        "index_reordered": False,
        "evaluated_at": now_utc.isoformat(),
    }
    empty = {"confirmed_df": df, "live_row": None, "current_row": None, "context": ctx}

    try:
        n = 0 if df is None else len(df)
    except TypeError:
        n = 0
    if n == 0:
        return empty

    dates = _session_dates(df.index)
    counts: dict = {}
    for d in dates:
        if d is not None:
            counts[d] = counts.get(d, 0) + 1

    today_et = now_utc.astimezone(_EASTERN).date()
    complete = _session_complete(now_utc)

    def eligible(d) -> bool:
        if d is None:                 # unparseable date
            return False
        if counts[d] > 1:             # ambiguous duplicated session
            return False
        if d > today_et:              # future / clock-skewed row
            return False
        if d == today_et:             # current session
            return complete
        return True                   # a later session exists

    positions = [i for i, d in enumerate(dates) if eligible(d)]
    ordered = sorted(positions, key=lambda i: dates[i])
    ctx["index_reordered"] = ordered != positions
    confirmed_df = df.iloc[ordered]

    parseable = [d for d in dates if d is not None]
    newest = max(parseable) if parseable else None

    # ---- status of the newest provable session -----------------------------
    if newest is None:
        status, source = _DAILY_STATUS_UNKNOWN, "unparseable_index"
    elif counts[newest] > 1:
        status, source = _DAILY_STATUS_UNKNOWN, "duplicate_session_dates"
    elif newest > today_et:
        status, source = _DAILY_STATUS_UNKNOWN, "future_dated_row"
    elif any(d is None for d in dates):
        status, source = _DAILY_STATUS_UNKNOWN, "unparseable_index"
    elif newest < today_et:
        status, source = _DAILY_STATUS_CLOSED, "prior_session_date_et"
    elif complete:
        status, source = _DAILY_STATUS_CLOSED, "regular_session_complete_et"
    else:
        status, source = _DAILY_STATUS_LIVE, "regular_session_in_progress_et"

    # ---- the developing row, identified by DATE, never by position ---------
    live_row = None
    if not complete and counts.get(today_et, 0) == 1:
        pos = dates.index(today_et)
        live_row = df.iloc[pos]
        ctx["live_daily_date"] = today_et.isoformat()

    # ---- current price row: the provider's last row, never a synthesized one
    current_row = df.iloc[-1]
    ctx["current_row_trusted"] = bool(
        dates[-1] is not None
        and newest is not None
        and dates[-1] == newest
        and counts[dates[-1]] == 1
        and dates[-1] <= today_et
    )

    withheld = n - len(confirmed_df)
    ctx["status"] = status
    ctx["status_source"] = source
    ctx["live_bar_available"] = live_row is not None
    ctx["confirmed_bars"] = len(confirmed_df)
    ctx["ambiguous_rows_withheld"] = max(0, withheld - (1 if live_row is not None else 0))
    if len(confirmed_df):
        last_confirmed = dates[ordered[-1]]
        ctx["last_closed_daily_date"] = last_confirmed.isoformat() if last_confirmed else None

    return {
        "confirmed_df": confirmed_df,
        "live_row": live_row,
        "current_row": current_row,
        "context": ctx,
    }


def resolve_daily_bar_status(df, now_utc: datetime | None = None) -> dict:
    """Classify the newest daily row as CLOSED, LIVE (developing) or UNKNOWN.

    Thin accessor over `partition_daily_bars` — the partition is the single
    source of truth for Daily confirmation provenance.
    """
    return partition_daily_bars(df, now_utc=now_utc)["context"]


# ---------------------------------------------------------------------------
# Phase R4H-1 — session-aligned 4H operational bars from the SAME 60m response.
#
# ONE provider request, two organs. The 1H engine keeps its existing
# tail(max_bars) trigger window; the 4H engine aggregates from the FULL
# normalized response, because operational structure needs far more history
# than trigger proof does.
#
# The regular session splits into exactly two operational buckets:
#
#   MORNING_4H      09:30-13:30 ET   sources 09:30/10:30/11:30/12:30   240 min
#   AFTERNOON_CLOSE 13:30-16:00 ET   sources 13:30/14:30/15:30         150 min
#
# The afternoon bucket is a 150-minute session-close operational candle and is
# labeled as such — it is never described as 240 minutes.
#
# MBT-1 remains sovereign over the source rows: a 60m timestamp is the
# INTERVAL START (see `_interval_end_utc`), and a source bar is closed only
# once its own interval has completed. MBT-2A remains sovereign over
# ambiguity: duplicate, unparseable or future-dated constituents withhold
# confirmation from their bucket rather than being silently dropped, and
# physical row order is never treated as provenance.
#
# Closed clock time alone is not enough: a bucket earns confirmation only when
# every expected source interval is present AND closed. A completed window
# with a missing constituent is INCOMPLETE, never confirmed evidence. No bar
# is ever synthesized, interpolated, or averaged across a hole.
#
# Pre-market, after-hours and overnight rows are excluded — this is the
# regular-session operational chart, and overnight liquidity is a different
# auction.
#
# EARLY-CLOSE LIMITATION (documented, deliberate): no market-calendar
# dependency is added. On a 13:00 ET early close the afternoon bucket simply
# never receives its 13:30/14:30/15:30 constituents, so it stays INCOMPLETE
# and never confirms. Confirmation is delayed, never invented.
# ---------------------------------------------------------------------------

MORNING_4H = "MORNING_4H"
AFTERNOON_CLOSE = "AFTERNOON_CLOSE"

_SLOT_STARTS = {
    MORNING_4H: ((9, 30), (10, 30), (11, 30), (12, 30)),
    AFTERNOON_CLOSE: ((13, 30), (14, 30), (15, 30)),
}
_SLOT_WINDOW_ET = {
    MORNING_4H: ((9, 30), (13, 30)),
    AFTERNOON_CLOSE: ((13, 30), (16, 0)),
}
_SLOT_DURATION_MIN = {MORNING_4H: 240, AFTERNOON_CLOSE: 150}
_SLOT_ORDER = {MORNING_4H: 0, AFTERNOON_CLOSE: 1}

FOUR_HOUR_AGGREGATION = "RTH_SESSION_ALIGNED"


def _slot_for_start(et_dt) -> str | None:
    """Operational bucket for a source bar's ET interval start, or None when
    the row is outside the regular session / off the hourly RTH grid."""
    hm = (et_dt.hour, et_dt.minute)
    for slot, starts in _SLOT_STARTS.items():
        if hm in starts:
            return slot
    return None


def _slot_bounds_utc(session_date, slot) -> tuple:
    """(start_utc, end_utc) for a bucket on a given ET session date."""
    (sh, sm), (eh, em) = _SLOT_WINDOW_ET[slot]
    start = datetime(session_date.year, session_date.month, session_date.day,
                     sh, sm, tzinfo=_EASTERN)
    end = datetime(session_date.year, session_date.month, session_date.day,
                   eh, em, tzinfo=_EASTERN)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _empty_four_hour(now_iso, status="EMPTY", error=None) -> dict:
    return {
        "bars": [],
        "status": status,
        "source_interval": None,
        "aggregation": FOUR_HOUR_AGGREGATION,
        "source_request_reused": True,
        "now": now_iso,
        "error": error,
        "history": {
            "sessions_covered": 0,
            "total_bars": 0,
            "closed_complete_bars": 0,
            "source_rows_seen": 0,
            "source_rows_off_session": 0,
            "source_rows_unparseable": 0,
        },
    }


def aggregate_four_hour_bars(df, now_utc: datetime | None = None,
                             interval: str = "60m") -> dict:
    """Aggregate a normalized intraday DataFrame into session-aligned 4H bars.

    Consumes the FULL provider response (never the truncated 1H window) and
    never mutates it. Returns the `four_hour` envelope. Never raises.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_iso = now_utc.isoformat()

    env = _empty_four_hour(now_iso)
    env["source_interval"] = interval
    interval_minutes = _parse_interval_minutes(interval)

    try:
        n = 0 if df is None else len(df)
    except TypeError:
        n = 0
    if n == 0:
        return env

    hist = env["history"]
    hist["source_rows_seen"] = n

    # ---- Bucket the source rows by (session date, slot) --------------------
    groups: dict = {}
    for idx, row in df.iterrows():
        bar_utc = _bar_time_utc(idx)
        if bar_utc is None:
            hist["source_rows_unparseable"] += 1
            continue
        et = bar_utc.astimezone(_EASTERN)
        slot = _slot_for_start(et)
        if slot is None:
            hist["source_rows_off_session"] += 1
            continue
        try:
            member = {
                "start": bar_utc,
                "hm": (et.hour, et.minute),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]) if "volume" in df.columns else None,
                "closed": not _resolve_newest_bar_open(bar_utc, interval_minutes, now_utc),
                "future": bar_utc > now_utc,
            }
        except (KeyError, TypeError, ValueError):
            hist["source_rows_unparseable"] += 1
            continue
        groups.setdefault((et.date(), slot), []).append(member)

    if not groups:
        env["status"] = "EMPTY" if not hist["source_rows_unparseable"] else "DEGRADED"
        return env

    # ---- Build one operational candle per bucket ---------------------------
    bars = []
    for (session_date, slot) in sorted(groups, key=lambda k: (k[0], _SLOT_ORDER[k[1]])):
        # MBT-2A: safe rows may be sorted chronologically — position is not
        # provenance — but nothing ambiguous is quietly dropped.
        members = sorted(groups[(session_date, slot)], key=lambda m: m["start"])
        starts = [m["hm"] for m in members]
        expected = _SLOT_STARTS[slot]

        duplicated = len(set(starts)) != len(starts)
        has_future = any(m["future"] for m in members)
        source_complete = set(starts) == set(expected) and not duplicated
        all_closed = all(m["closed"] for m in members)

        start_utc, end_utc = _slot_bounds_utc(session_date, slot)
        window_complete = now_utc >= end_utc
        is_open = (not window_complete) or (not all_closed)
        ambiguous = duplicated or has_future

        confirmation_eligible = bool(
            window_complete and source_complete and all_closed and not ambiguous
        )
        if ambiguous:
            status = "AMBIGUOUS"
        elif is_open:
            status = "LIVE"
        elif not source_complete:
            status = "INCOMPLETE"
        else:
            status = "CONFIRMED"

        volumes = [m["volume"] for m in members if m["volume"] is not None]
        bars.append({
            "time": start_utc.isoformat(),
            "end_time": end_utc.isoformat(),
            "session_date": session_date.isoformat(),
            "bucket_slot": slot,
            "duration_minutes": _SLOT_DURATION_MIN[slot],
            "open": members[0]["open"],
            "high": max(m["high"] for m in members),
            "low": min(m["low"] for m in members),
            "close": members[-1]["close"],
            "volume": sum(volumes) if len(volumes) == len(members) else None,
            "source_bar_count": len(members),
            "expected_source_bar_count": len(expected),
            "source_complete": source_complete,
            "is_open": is_open,
            "confirmation_eligible": confirmation_eligible,
            "status": status,
        })

    confirmed = sum(1 for b in bars if b["confirmation_eligible"])
    hist["total_bars"] = len(bars)
    hist["closed_complete_bars"] = confirmed
    hist["sessions_covered"] = len({b["session_date"] for b in bars})

    env["bars"] = bars
    if hist["source_rows_unparseable"] or confirmed == 0:
        env["status"] = "DEGRADED"
    else:
        env["status"] = "OK"
    return env

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


def _extract_ticker_df(raw: pd.DataFrame, ticker: str, single: bool) -> pd.DataFrame:
    """Extract per-ticker DataFrame from a yfinance download result.

    Handles three shapes:
    - Flat (single=True or no MultiIndex): columns are already field names.
    - (field, ticker) MultiIndex — default orientation: tickers at level 1.
    - (ticker, field) MultiIndex — group_by="ticker" orientation: tickers at level 0.

    Raises KeyError if ticker is absent from a multi-ticker response.
    """
    if single or not isinstance(raw.columns, pd.MultiIndex):
        df = raw.copy()
        df.columns = [c.lower() for c in df.columns]
        return df

    level_0_vals = set(raw.columns.get_level_values(0))
    level_1_vals = set(raw.columns.get_level_values(1))

    if ticker in level_1_vals:
        df = raw.xs(ticker, axis=1, level=1).copy()
    elif ticker in level_0_vals:
        df = raw.xs(ticker, axis=1, level=0).copy()
    else:
        raise KeyError(f"{ticker} not found in batch response at level 0 or level 1")

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

        single = len(batch) == 1
        # Pass a string for single-ticker batches to get a flat DataFrame (no MultiIndex)
        download_arg = batch[0] if single else batch

        try:
            raw = yf.download(
                download_arg,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:
            log.warning("BATCH_FETCH_ERROR batch %d: %s", batch_idx, exc)
            for t in batch:
                results[t] = _error_result(t, str(exc))
            continue

        for ticker in batch:
            try:
                df = _extract_ticker_df(raw, ticker, single)
            except KeyError:
                log.warning("TICKER_NOT_IN_BATCH: %s — falling back to individual fetch", ticker)
                results[ticker] = fetch_ticker(ticker, config)
                continue
            except Exception as exc:
                log.warning("EXTRACT_ERROR: %s: %s", ticker, exc)
                results[ticker] = _error_result(ticker, f"extraction failed: {exc}")
                continue

            try:
                if df.empty:
                    results[ticker] = {
                        "ticker": ticker, "bars": 0,
                        "latest_close": None, "latest_date": None,
                        "data_status": "EMPTY", "df": None, "error": "empty",
                    }
                    continue

                is_valid, skip_reason = validate_ticker_data(ticker, df, config)
                if not is_valid:
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


def fetch_one_hour_bars(ticker: str, config: dict) -> dict:
    """Separately acquire recent 1H OHLCV bars for trigger-proof evidence.

    Returns an envelope dict consumable by one_hour_entry.build_one_hour_entry_context:
      {
        "bars":      list of {open,high,low,close,volume,time,is_open?} (oldest→newest),
        "freshness": "FRESH" | "RECENT" | "DEGRADED" | "STALE",
        "now":       timezone-aware UTC ISO timestamp the freshness was computed against,
        "status":    "OK" | "EMPTY" | "ERROR",
        "error":     None | str,
      }

    Only the newest bar may ever carry is_open=True, and only when its own
    interval has not yet completed as of `now` (Phase MBT-1). Every earlier
    bar is closed by chronological law. OHLCV values are never altered by
    this classification.

    Phase R4H-1 adds a backwards-compatible "four_hour" namespace to the same
    envelope. It is aggregated from the SAME provider response — one request,
    two organs — and from the FULL normalized frame rather than the truncated
    1H window, because operational structure needs more history than trigger
    proof. The 1H "bars" list is byte-for-byte unchanged.

    Never raises. On any failure returns status != "OK" with bars=[] so the 1H
    engine degrades safely. This does NOT touch the daily acquisition path.
    """
    one_hour_cfg = config.get("one_hour", {})
    period = one_hour_cfg.get("lookback_period", "1mo")
    interval = one_hour_cfg.get("interval", "60m")
    max_bars = int(one_hour_cfg.get("max_bars", 80))
    interval_minutes = _parse_interval_minutes(interval)

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        log.warning("ONE_HOUR_FETCH_ERROR: %s: %s", ticker, exc)
        return {"bars": [], "freshness": "STALE", "now": now_iso, "status": "ERROR",
                "error": str(exc),
                "four_hour": _empty_four_hour(now_iso, "ERROR", str(exc))}

    if df is None or df.empty:
        return {"bars": [], "freshness": "STALE", "now": now_iso, "status": "EMPTY",
                "error": "empty 1H response",
                "four_hour": _empty_four_hour(now_iso, "EMPTY", "empty 1H response")}

    try:
        df = _normalize(df)
    except Exception as exc:
        return {"bars": [], "freshness": "STALE", "now": now_iso, "status": "ERROR",
                "error": f"1H normalize failed: {exc}",
                "four_hour": _empty_four_hour(now_iso, "ERROR", f"1H normalize failed: {exc}")}

    # R4H-1: aggregate 4H from the FULL normalized response, BEFORE the 1H
    # trigger window is truncated below. No second provider request.
    try:
        four_hour = aggregate_four_hour_bars(df, now_utc=now_utc, interval=interval)
    except Exception as exc:                      # pragma: no cover - defensive
        log.warning("FOUR_HOUR_AGGREGATION_ERROR: %s: %s", ticker, exc)
        four_hour = _empty_four_hour(now_iso, "ERROR", f"4H aggregation failed: {exc}")

    tail = df.tail(max_bars)
    n = len(tail)
    bars = []
    for pos, (idx, row) in enumerate(tail.iterrows()):
        try:
            bar_dt_utc = _bar_time_utc(idx)
            bar = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]) if "volume" in tail.columns else None,
                "time": bar_dt_utc.isoformat() if bar_dt_utc is not None else str(pd.to_datetime(idx)),
            }
        except (KeyError, ValueError, TypeError):
            continue
        # Chronological law: only the newest bar can possibly still be open.
        if pos == n - 1 and _resolve_newest_bar_open(bar_dt_utc, interval_minutes, now_utc):
            bar["is_open"] = True
        bars.append(bar)

    return {"bars": bars, "freshness": None, "now": now_iso, "status": "OK",
            "error": None, "four_hour": four_hour}


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

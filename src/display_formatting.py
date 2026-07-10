"""Phase 14S.2 — operator-facing dollar price display formatting.

Pure, display-only helpers. A price must look like a price: every
human-facing equity price (scan/current price, entry, trigger, proof level,
invalidation, targets, zone/support/resistance levels) gets a leading `$`.
Scores, R:R ratios, percentages, timeframe labels, SMA periods, DTE, volume,
counts, timestamps, and IDs are NEVER touched by this module — callers choose
where to apply it, field by field.

Doctrine (permanent):
  - Display-only. Never mutates the value it is given, never changes any
    stored/schema field, never affects tier, capital, routing, scoring, or any
    decision logic. The underlying numeric type in tiering_result / persisted
    rows is always left as int/float; only the rendered *text* gains `$`.
  - Deterministic and never raises. Missing/invalid/non-finite input renders
    as the placeholder ("—" by default), never "$None" / "$nan" / "$inf".
  - Idempotent: an already-formatted "$100" string passed back in is
    recognized and returned unchanged — never "$$100".
  - No scientific notation, no exposed floating-point tails (100.4999999997
    renders as $100.50, not the raw float repr).
  - Whole-dollar values omit ".00"; non-whole values keep exactly two
    decimals; thousands get comma separators.

Pure stdlib. No IO, no network, no imports of scanner/tiering modules.
"""

import re

_DASH = "—"

# Matches a value that is ALREADY a formatted USD string (idempotency guard),
# e.g. "$100", "$1,250.50", "-$5". Anchored so it only recognizes a clean,
# already-rendered price — not an arbitrary string that merely contains "$".
_ALREADY_FORMATTED_RE = re.compile(r"^-?\$[\d,]+(?:\.\d{2})?$")


def _to_float(value):
    """Best-effort numeric coercion. Returns None for anything that isn't a
    finite real number (None, "", non-numeric strings, bool, NaN, inf)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if _ALREADY_FORMATTED_RE.match(stripped):
            # Idempotency: strip the existing formatting and re-derive the
            # float so re-formatting is a no-op rather than a double-prefix.
            stripped = stripped.replace("$", "").replace(",", "")
        try:
            value = float(stripped)
        except (TypeError, ValueError):
            return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / +inf / -inf
        return None
    return f


def format_usd_price(value, placeholder: str = _DASH) -> str:
    """Render a stock price as an operator-facing dollar string.

    format_usd_price(100)       -> "$100"
    format_usd_price(100.5)     -> "$100.50"
    format_usd_price(1250.5)    -> "$1,250.50"
    format_usd_price(0.85)      -> "$0.85"
    format_usd_price(-5)        -> "-$5"
    format_usd_price(None)      -> "—"
    format_usd_price("")        -> "—"
    format_usd_price(float("nan")) -> "—"

    Never raises. Never mutates `value`. Does not round the underlying
    number anywhere except in this returned display string.
    """
    try:
        f = _to_float(value)
        if f is None:
            return placeholder

        negative = f < 0
        magnitude = -f if negative else f

        # Round to cents for display only; whole-dollar values drop ".00".
        cents_total = round(magnitude * 100)
        whole, cents = divmod(cents_total, 100)
        whole_str = f"{whole:,}"
        body = whole_str if cents == 0 else f"{whole_str}.{cents:02d}"
        sign = "-" if negative else ""
        return f"{sign}${body}"
    except Exception:  # pragma: no cover - defensive; formatting never raises
        return placeholder


# ---------------------------------------------------------------------------
# Narrow free-text price formatter (semantic boundaries only — never a blind
# global number-prefixer). Used only where a price value is already embedded
# in a pre-built natural-language sentence and cannot be formatted at
# construction time.
# ---------------------------------------------------------------------------

# Only numbers immediately preceded by one of these price-semantic phrases are
# formatted. Deliberately excludes "score", "R:R", "risk", "confidence",
# "phase", "duration", timeframe labels, and SMA period labels.
_PRICE_PHRASE_RE = re.compile(
    r"""(?ix)
    \b(
        scan\ price | current\ price | entry(?:\ price|\ level)? |
        trigger(?:\ level)? | confirmation\ level | proof\ level |
        invalidation(?:\ level)? | stop(?:\ level)? |
        hold\ above | close\ above | close\ below |
        body\ close\ above | body\ close\ below |
        target(?:s)? | support | resistance | zone |
        reclaim(?:\ level)? | breakout\ level | breakdown\ level |
        retest\ level | promotion\ level | overhead\ level
    )
    (\s+)
    (-?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?)
    """,
)


def format_price_level_text(text) -> str:
    """Format only the number(s) immediately following a clear price-semantic
    phrase inside an existing sentence (e.g. "1H closed hold above 600.07" ->
    "1H closed hold above $600.07"). Idempotent and narrowly scoped — never a
    blind global number-prefixer; leaves scores, ratios, percentages,
    timeframe labels, and SMA period numbers untouched. Never raises.
    """
    if not isinstance(text, str) or not text:
        return text if isinstance(text, str) else text

    try:
        def _sub(m):
            phrase, sep, number = m.group(1), m.group(2), m.group(3)
            return f"{phrase}{sep}{format_usd_price(number)}"

        return _PRICE_PHRASE_RE.sub(_sub, text)
    except Exception:  # pragma: no cover - defensive; formatting never raises
        return text


def format_usd_price_list(values, placeholder: str = _DASH, sep: str = ", ") -> str:
    """Format a list of prices as a joined, comma-separated dollar string —
    e.g. [110, 118.25] -> "$110, $118.25". Never mutates the source list."""
    if not isinstance(values, (list, tuple)):
        return placeholder
    return sep.join(format_usd_price(v, placeholder) for v in values)


def format_usd_range(low, high, dash: str = "–", placeholder: str = _DASH) -> str:
    """Format a low-high price range — e.g. (98.5, 101.25) -> "$98.50–$101.25"."""
    return f"{format_usd_price(low, placeholder)}{dash}{format_usd_price(high, placeholder)}"

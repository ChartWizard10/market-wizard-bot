"""Campaign identity engine — C1 foundation.

Anchors scanner identity to structural campaigns rather than trigger-price drift.

Campaign identity = ticker + setup_family + zone_type + zone_floor + invalidation_level.

Trigger level is intentionally excluded. Minor drift in entry price inside the same
structural zone does NOT constitute a new campaign.

This module is additive and fail-closed. If resolution fails, callers fall back to the
existing state_store dedup behavior. It does not affect tier, score, capital_action,
routing, or any authorization decision.
"""

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_CAMPAIGN_PATH = "data/campaign_state.json"

# Tolerance for structural level comparison.
# 0.5% absorbs minor bar-to-bar computation variance in zone levels while
# treating any genuine structural shift (new zone, moved invalidation) as a
# new campaign.
_ZONE_TOLERANCE_PCT   = 0.005
_INVAL_TOLERANCE_PCT  = 0.005


# ---------------------------------------------------------------------------
# Level helpers
# ---------------------------------------------------------------------------

def _round_level(v) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def _levels_match(a: float | None, b: float | None, tol_pct: float) -> bool:
    """True when two price levels are within tol_pct of each other."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    ref = abs(a) if abs(a) > 1e-9 else abs(b)
    if ref < 1e-9:
        return a == b
    return abs(a - b) / ref <= tol_pct


# ---------------------------------------------------------------------------
# Zone floor extraction
# ---------------------------------------------------------------------------

def _extract_zone_floor(enriched: dict, zone_type: str | None) -> float | None:
    """Extract controlling zone lower bound from the indicators enriched dict.

    FVG  → fvg_bot  (bottom of the gap — the level the zone would be mitigated below)
    OB   → ob_lo    (bottom of the order block body)
    demand / flip_zone → ob_lo preferentially, fvg_bot as fallback
    none / support_cluster / unknown → None
    """
    if not zone_type or zone_type.lower() in ("none", "support_cluster", "unknown"):
        return None

    zt = zone_type.lower()

    if zt == "ob":
        ob = enriched.get("ob") or {}
        return _round_level(ob.get("ob_lo"))

    if zt == "fvg":
        fvg = enriched.get("fvg") or {}
        return _round_level(fvg.get("fvg_bot"))

    if zt in ("demand", "flip_zone"):
        ob = enriched.get("ob") or {}
        v = _round_level(ob.get("ob_lo"))
        if v is not None:
            return v
        fvg = enriched.get("fvg") or {}
        return _round_level(fvg.get("fvg_bot"))

    return None


# ---------------------------------------------------------------------------
# Campaign identity
# ---------------------------------------------------------------------------

def compute_campaign_id(
    ticker: str,
    setup_family: str | None,
    zone_type: str | None,
    zone_floor: float | None,
    invalidation_level: float | None,
) -> str:
    """Build a stable campaign ID from structural anchors.

    Trigger level is never included. Trigger drift inside the same zone does
    not change the campaign identity.
    """
    sf = (setup_family or "none").lower()
    zt = (zone_type or "none").lower()
    zf = f"{zone_floor:.4f}" if zone_floor is not None else "null"
    iv = f"{invalidation_level:.4f}" if invalidation_level is not None else "null"
    return f"{ticker}|{sf}|{zt}|{zf}|{iv}"


def is_same_structure(
    ticker: str,
    setup_family: str | None,
    zone_type: str | None,
    zone_floor: float | None,
    invalidation_level: float | None,
    existing: dict,
) -> bool:
    """True when a new signal's structural identity matches an existing campaign record.

    Uses tolerance windows on price levels to absorb minor bar-to-bar variance.
    """
    if ticker != existing.get("ticker"):
        return False

    sf = (setup_family or "none").lower()
    zt = (zone_type or "none").lower()

    if sf != (existing.get("setup_family") or "none").lower():
        return False
    if zt != (existing.get("zone_type") or "none").lower():
        return False

    if not _levels_match(zone_floor, existing.get("zone_floor"), _ZONE_TOLERANCE_PCT):
        return False
    if not _levels_match(
        invalidation_level, existing.get("invalidation_level"), _INVAL_TOLERANCE_PCT
    ):
        return False

    return True


# ---------------------------------------------------------------------------
# Path / persistence helpers
# ---------------------------------------------------------------------------

def _campaign_path(config: dict) -> Path:
    path_str = (config.get("campaign") or {}).get(
        "campaign_file", _DEFAULT_CAMPAIGN_PATH
    )
    return Path(path_str)


def _empty_state() -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "campaigns": {},
        "meta": {
            "created_at":   now,
            "last_updated": now,
        },
    }


def _backup_corrupt(path: Path) -> None:
    suffix = f".corrupt.{int(time.time())}"
    backup = path.with_name(path.name + suffix)
    try:
        shutil.move(str(path), str(backup))
        log.warning("Corrupt campaign state backed up to %s", backup)
    except Exception as exc:
        log.error("Could not back up corrupt campaign state: %s", exc)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load(config: dict) -> dict:
    """Load campaign state from file. Returns empty state if missing or corrupt."""
    path = _campaign_path(config)

    if not path.exists():
        log.debug("Campaign state file not found at %s — initializing empty", path)
        return _empty_state()

    try:
        raw  = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "campaigns" not in data:
            raise ValueError("invalid structure: missing 'campaigns' key")
        return data
    except Exception as exc:
        log.warning(
            "Corrupt campaign state at %s: %s — backing up and resetting", path, exc
        )
        _backup_corrupt(path)
        return _empty_state()


def save(campaign_state: dict, config: dict) -> None:
    """Persist campaign state. Logs CRITICAL on write failure — does not raise."""
    path = _campaign_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        campaign_state.setdefault("meta", {})["last_updated"] = (
            datetime.utcnow().isoformat()
        )
        path.write_text(json.dumps(campaign_state, indent=2), encoding="utf-8")
    except Exception as exc:
        log.critical("CRITICAL: campaign state write failed: %s", exc)


# ---------------------------------------------------------------------------
# Resolution — find or create campaign ID
# ---------------------------------------------------------------------------

def resolve(tiering_result: dict, enriched: dict, campaign_state: dict) -> str:
    """Return the stable campaign_id for this signal.

    Looks for an existing campaign with matching structural identity (within
    tolerance). If found, returns the existing canonical ID so that trigger
    drift inside the same zone reuses the same campaign. If not found, creates
    and returns a new canonical ID.
    """
    final_signal       = tiering_result.get("final_signal") or {}
    ticker             = final_signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")
    setup_family       = final_signal.get("setup_family")
    zone_type          = final_signal.get("zone_type")
    invalidation_level = _round_level(final_signal.get("invalidation_level"))
    zone_floor         = _extract_zone_floor(enriched, zone_type)

    campaigns = campaign_state.get("campaigns", {})

    for existing in campaigns.values():
        if is_same_structure(
            ticker, setup_family, zone_type, zone_floor, invalidation_level, existing
        ):
            return existing["campaign_id"]

    return compute_campaign_id(
        ticker, setup_family, zone_type, zone_floor, invalidation_level
    )


# ---------------------------------------------------------------------------
# State update
# ---------------------------------------------------------------------------

def register_seen(
    campaign_id: str,
    tiering_result: dict,
    enriched: dict,
    campaign_state: dict,
) -> dict:
    """Record that this campaign was seen in the current scan cycle.

    Creates a new record if this campaign_id has not been seen before.
    Returns the updated campaign_state dict. Does NOT save to disk — caller
    calls save().
    """
    final_signal       = tiering_result.get("final_signal") or {}
    ticker             = final_signal.get("ticker") or tiering_result.get("ticker", "UNKNOWN")
    setup_family       = final_signal.get("setup_family")
    zone_type          = final_signal.get("zone_type")
    invalidation_level = _round_level(final_signal.get("invalidation_level"))
    zone_floor         = _extract_zone_floor(enriched, zone_type)
    now                = datetime.utcnow().isoformat()

    campaigns = campaign_state.setdefault("campaigns", {})

    if campaign_id not in campaigns:
        campaigns[campaign_id] = {
            "campaign_id":        campaign_id,
            "ticker":             ticker,
            "setup_family":       (setup_family or "none").lower(),
            "zone_type":          (zone_type or "none").lower(),
            "zone_floor":         zone_floor,
            "invalidation_level": invalidation_level,
            "first_seen_at":      now,
            "last_seen_at":       now,
            "scan_count":         1,
        }
    else:
        record = campaigns[campaign_id]
        record["last_seen_at"] = now
        record["scan_count"]   = record.get("scan_count", 0) + 1

    return campaign_state

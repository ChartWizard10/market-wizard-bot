"""Production prefilter facade with VELOCITY-1B observational evidence.

The raw prefilter remains the sovereign admission/ranking implementation.
This facade calls it first, then attaches a research-only five-session
feasibility snapshot to the already-computed rows.  Because attachment happens
after raw scoring, veto arbitration, ranking and candidate capping, velocity
evidence cannot change admission or rank in this phase.

Direct ``src.prefilter`` imports still address the raw implementation. Package-
level ``from src import prefilter`` resolves to this production facade.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any


log = logging.getLogger(__name__)
_raw_prefilter = importlib.import_module("src.prefilter")
_velocity = importlib.import_module("src.velocity_research")

RUNTIME_VERSION = "VELOCITY-1B"


def _snapshot(enriched: dict | None) -> dict | None:
    """Build observational evidence without ever breaking admission."""
    try:
        source = enriched if isinstance(enriched, dict) else {}
        return _velocity.build_feasibility_snapshot(source)
    except Exception as exc:  # observation failure is never a scan failure
        log.warning("VELOCITY_OBSERVATION_UNAVAILABLE: %s", type(exc).__name__)
        return None


def _attach(row: dict | None, enriched: dict | None) -> dict | None:
    if not isinstance(row, dict):
        return row
    row["velocity_research"] = _snapshot(enriched)
    row["velocity_runtime_version"] = RUNTIME_VERSION
    return row


def score_ticker(enriched: dict, config: dict) -> dict:
    """Raw single-ticker result plus non-authoritative velocity evidence."""
    row = _raw_prefilter.score_ticker(enriched, config)
    _attach(row, enriched)
    return row


def prefilter(enriched_list: list, config: dict) -> dict:
    """Run the raw board prefilter first, then attach observational snapshots.

    All raw list ordering, object identity, scores, vetoes, eligibility and the
    configured candidate cap are preserved.
    """
    result = _raw_prefilter.prefilter(enriched_list, config)
    if not isinstance(result, dict):
        return result

    source_by_ticker = {
        str(item.get("ticker")): item
        for item in enriched_list
        if isinstance(item, dict) and item.get("ticker") is not None
    }

    # Raw prefilter collections normally share row objects. Deduplicate by id so
    # the research computation runs at most once per board row even if an object
    # appears in all_results, ranked_results and candidate aliases.
    seen: set[int] = set()
    for key in ("all_results", "ranked_results", "model_candidates", "claude_candidates"):
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or id(row) in seen:
                continue
            seen.add(id(row))
            source = source_by_ticker.get(str(row.get("ticker")))
            _attach(row, source)

    return result


def __getattr__(name: str) -> Any:
    """Delegate every non-overridden prefilter symbol to the raw module."""
    return getattr(_raw_prefilter, name)

"""CAP-40B — offline candidate-cap boundary observation outcome linker.

CAP-40A defines a comparable pre-model observation for the current-cap edge and
for the next ten eligible candidates outside the cap. CAP-40B projects those
blocks from isolated scan telemetry and links valid structural geometry to
future completed Daily sessions through the existing VELOCITY-1D labeler.

This module is deliberately pure and offline:

* no network access or market-data fetch;
* no model call;
* no scanner, tier, routing, state or capital mutation;
* no file I/O;
* no claim about the tier an unanalysed shadow candidate would have received.

The outcome study answers a narrower question: did the rank boundary exclude
pre-model candidates that already had valid structural geometry and later
reached the +8% / five-session research objective before invalidation?
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src import capacity_boundary_observation as boundary
from src import velocity_dataset
from src import velocity_research

VERSION = "CAP-40B"
LINK_DUPLICATE_BOUNDARY_CONFLICT = "DUPLICATE_BOUNDARY_OBSERVATION_CONFLICT"


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def extract_boundary_observations(ledger: dict | None) -> list[dict]:
    """Extract normalized CAP-40 blocks from any existing decision-trace kind.

    A boundary block is pre-model evidence. Post-model final tiers are
    intentionally not imported into the comparable observation envelope.
    """
    data = _dict(ledger)
    traces = data.get("decision_traces")
    if not isinstance(traces, list):
        return []

    out: list[dict] = []
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        block = trace.get("capacity_boundary_observation")
        if not isinstance(block, dict):
            continue

        band = _text(block.get("band"))
        if band not in (boundary.BAND_BASELINE_EDGE, boundary.BAND_SHADOW_INCREMENT):
            continue

        scan_id = _text(trace.get("scan_id")) or _text(block.get("scan_id"))
        ticker = _text(trace.get("ticker")) or _text(block.get("ticker"))
        trace_kind = _text(trace.get("trace_kind"))
        ready = block.get("ready") is True

        out.append({
            "version": VERSION,
            "research_only": True,
            "capital_authority": False,
            "tier_authority": False,
            "candidate_cap_authority": False,
            "scan_id": scan_id,
            "ticker": ticker,
            "observed_at": _text(block.get("observed_at")),
            "persistence_ready": ready,
            "entry_price": _num(block.get("reference_price")),
            "entry_price_source": _text(block.get("reference_source")),
            "invalidation_level": _num(block.get("invalidation_level")),
            "target_return_pct": _num(block.get("target_return_pct")),
            "horizon_sessions": _num(block.get("horizon_sessions")),
            "feasibility_status": _text(block.get("feasibility_status")),
            "known_path_room_pct": _num(block.get("known_path_room_pct")),
            "atr_pct": _num(block.get("atr_pct")),
            "required_move_atr": _num(block.get("required_move_atr")),
            "setup_family": _text(block.get("primary_family")) or "UNKNOWN",
            # Deliberately neutral: the shadow increment was never model-judged.
            "final_tier": None,
            "capital_authorized_at_observation": False,
            "rank": _num(block.get("rank")),
            "band": band,
            "current_cap": _num(block.get("current_cap")),
            "proposed_cap": _num(block.get("proposed_cap")),
            "prefilter_score": _num(block.get("prefilter_score")),
            "admission_rank_score": _num(block.get("admission_rank_score")),
            "admission_source": _text(block.get("admission_source")),
            "family_state": _text(block.get("family_state")),
            "family_score": _num(block.get("family_score")),
            "family_watch_ready": block.get("family_watch_ready") is True,
            "family_admission_ready": block.get("family_admission_ready") is True,
            "family_entry_structure_valid": (
                block.get("family_entry_structure_valid") is True
            ),
            "family_rr_to_t1": _num(block.get("family_rr_to_t1")),
            "retest_status": _text(block.get("retest_status")),
            "overhead_status": _text(block.get("overhead_status")),
            "estimated_rr": _num(block.get("estimated_rr")),
            "source_trace_kind": trace_kind,
            "model_analyzed_at_observation": trace_kind == "analyzed",
        })
    return out


def link_boundary_observation_to_future(
    observation: dict | None,
    raw_bars: list | None,
) -> dict:
    """Link one CAP-40 observation using the existing VELOCITY-1D chronology."""
    obs = deepcopy(observation) if isinstance(observation, dict) else {}
    linked = velocity_dataset.link_observation_to_future(obs, raw_bars)
    return {
        **linked,
        "dataset_version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "candidate_cap_authority": False,
        "rank": _num(obs.get("rank")),
        "band": _text(obs.get("band")),
        "current_cap": _num(obs.get("current_cap")),
        "proposed_cap": _num(obs.get("proposed_cap")),
        "prefilter_score": _num(obs.get("prefilter_score")),
        "admission_rank_score": _num(obs.get("admission_rank_score")),
        "admission_source": _text(obs.get("admission_source")),
        "family_state": _text(obs.get("family_state")),
        "family_score": _num(obs.get("family_score")),
        "family_watch_ready": obs.get("family_watch_ready") is True,
        "family_admission_ready": obs.get("family_admission_ready") is True,
        "family_entry_structure_valid": (
            obs.get("family_entry_structure_valid") is True
        ),
        "family_rr_to_t1": _num(obs.get("family_rr_to_t1")),
        "retest_status": _text(obs.get("retest_status")),
        "overhead_status": _text(obs.get("overhead_status")),
        "estimated_rr": _num(obs.get("estimated_rr")),
        "source_trace_kind": _text(obs.get("source_trace_kind")),
        "model_analyzed_at_observation": obs.get("model_analyzed_at_observation") is True,
        "counterfactual_model_tier_supported": False,
    }


def _signature(observation: dict) -> tuple:
    keys = (
        "observed_at",
        "entry_price",
        "invalidation_level",
        "target_return_pct",
        "horizon_sessions",
        "rank",
        "band",
        "current_cap",
        "proposed_cap",
        "prefilter_score",
        "admission_rank_score",
        "setup_family",
        "family_state",
        "family_score",
        "retest_status",
        "overhead_status",
        "estimated_rr",
    )
    return tuple(observation.get(key) for key in keys)


def link_capacity_boundary_dataset(
    ledger: dict | None,
    bars_by_ticker: dict | None,
) -> dict:
    """Build a deterministic CAP-40 boundary outcome dataset from local inputs."""
    observations = extract_boundary_observations(ledger)
    bars_map = bars_by_ticker if isinstance(bars_by_ticker, dict) else {}

    grouped: dict[tuple[str, str], list[dict]] = {}
    orphans: list[dict] = []
    for obs in observations:
        scan_id = _text(obs.get("scan_id"))
        ticker = _text(obs.get("ticker"))
        if scan_id and ticker:
            grouped.setdefault((scan_id, ticker), []).append(obs)
        else:
            orphans.append(obs)

    records: list[dict] = []
    duplicate_identical = 0
    duplicate_conflicts = 0

    for rows in grouped.values():
        first = rows[0]
        if len(rows) > 1:
            signatures = {_signature(row) for row in rows}
            if len(signatures) > 1:
                duplicate_conflicts += 1
                bad = link_boundary_observation_to_future(first, [])
                bad["link_status"] = LINK_DUPLICATE_BOUNDARY_CONFLICT
                bad["label"] = velocity_research.INVALID_DATA
                bad["reason"] = (
                    "Conflicting duplicate scan/ticker CAP-40 observations prevent unique linkage."
                )
                records.append(bad)
                continue
            duplicate_identical += len(rows) - 1

        ticker = _text(first.get("ticker"))
        records.append(
            link_boundary_observation_to_future(
                first,
                bars_map.get(ticker, []) if ticker else [],
            )
        )

    for orphan in orphans:
        records.append(link_boundary_observation_to_future(orphan, []))

    records.sort(key=lambda row: (
        str(row.get("observed_at") or ""),
        str(row.get("ticker") or ""),
        str(row.get("scan_id") or ""),
    ))

    return {
        "version": VERSION,
        "research_only": True,
        "capital_authority": False,
        "tier_authority": False,
        "candidate_cap_authority": False,
        "counterfactual_model_tier_supported": False,
        "observation_count_raw": len(observations),
        "observation_count_unique": len(records),
        "duplicate_identical_observations_deduped": duplicate_identical,
        "duplicate_observation_conflicts": duplicate_conflicts,
        "records": records,
        "summary": summarize_boundary_dataset(records),
    }


def _count_labels(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("label") or velocity_research.INVALID_DATA)
        counts[label] = counts.get(label, 0) + 1
    return counts


def summarize_boundary_dataset(records: list[dict] | None) -> dict:
    """Summarize current-cap edge versus shadow increment without a trade claim."""
    rows = [row for row in (records or []) if isinstance(row, dict)]
    bands: dict[str, dict] = {}
    for band in (boundary.BAND_BASELINE_EDGE, boundary.BAND_SHADOW_INCREMENT):
        subset = [row for row in rows if row.get("band") == band]
        labels = _count_labels(subset)
        bands[band] = {
            "records": len(subset),
            "research_ready": sum(
                1 for row in subset
                if row.get("link_status") not in (
                    velocity_dataset.LINK_INVALID_OBSERVATION,
                    velocity_dataset.LINK_INVALID_OBSERVATION_TIME,
                    LINK_DUPLICATE_BOUNDARY_CONFLICT,
                )
            ),
            "label_counts": labels,
            "target_first": labels.get(velocity_research.TARGET_FIRST, 0),
            "invalidation_first": labels.get(velocity_research.INVALIDATION_FIRST, 0),
            "time_barrier": labels.get(velocity_research.TIME_BARRIER, 0),
            "incomplete_horizon": labels.get(velocity_research.INCOMPLETE_HORIZON, 0),
            "invalid_data": labels.get(velocity_research.INVALID_DATA, 0),
        }

    return {
        "total_records": len(rows),
        "label_counts": _count_labels(rows),
        "bands": bands,
        "shadow_target_first_candidates": bands[
            boundary.BAND_SHADOW_INCREMENT
        ]["target_first"],
        "interpretation": (
            "Shadow outcomes measure excluded pre-model structural candidates, not reconstructed alerts."
        ),
    }

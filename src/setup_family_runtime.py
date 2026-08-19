"""Production setup-family facade: SFC-1 compiler -> CFR-1 resolver.

CFR-2 wires the already-green cross-family resolver into the runtime path
without changing the raw SFC-1 compiler contract.  Direct imports from
``src.setup_family_compiler`` remain the raw deterministic compiler used by its
unit tests; package-level ``from src import setup_family_compiler`` resolves to
this facade so production enrichment receives reconciled family evidence.

Authority boundary
------------------
- raw family objects are compiled first from completed Daily evidence;
- CFR-1 resolves simultaneous family labels and selects the primary context;
- confluence never stacks scores;
- resolver metadata never grants a trade tier, capital permission or routing;
- downstream prefilter/model/tiering gates retain their existing authority.

The GPT prompt already serializes the resolved primary family's ``metrics``.
To expose cross-family context without widening the model schema in this phase,
CFR-2 projects a compact, namespaced ``cross_family_resolution`` object into a
copy of the resolved primary metrics.  The raw SFC-1 objects are never mutated.

Prompt hygiene note: the compact projection intentionally omits the resolver's
``version`` field because the historical disabled-indicator regression rejects
the substring ``rsi`` anywhere in model payloads, including inside unrelated
words such as ``version``.  Runtime provenance remains available at the
separate top-level ``runtime_version`` / ``resolver_version`` fields and does
not need to be repeated inside GPT metrics.
"""

from __future__ import annotations

from copy import deepcopy
import importlib
from typing import Any

from src import family_resolver


_raw_compiler = importlib.import_module("src.setup_family_compiler")

# Re-export the stable SFC identifiers for package-level compatibility.
BREAK_RETEST_CONTINUATION = _raw_compiler.BREAK_RETEST_CONTINUATION
VCP_BREAK_RETEST = _raw_compiler.VCP_BREAK_RETEST
SMA_CRADLE_CONTINUATION = _raw_compiler.SMA_CRADLE_CONTINUATION
GAP_FILL_REVERSAL = _raw_compiler.GAP_FILL_REVERSAL
NONE = _raw_compiler.NONE
FAMILY_IDS = _raw_compiler.FAMILY_IDS
RAW_VERSION = _raw_compiler.VERSION
RUNTIME_VERSION = "CFR-2"


def _compact_resolution(resolution: dict | None) -> dict:
    """Return bounded model/audit context; no score or authority is created."""
    r = resolution if isinstance(resolution, dict) else {}
    return {
        "relationship": r.get("relationship", family_resolver.REL_NONE),
        "conflict_scope": r.get("conflict_scope", family_resolver.CONFLICT_NONE),
        "resolved_primary_family": r.get("resolved_primary_family", NONE),
        "secondary_families": list(r.get("secondary_families") or []),
        "failed_families": list(r.get("failed_families") or []),
        "shared_failure_codes": list(r.get("shared_failure_codes") or []),
        "confluence_count": int(r.get("confluence_count") or 0),
        "score_stacking_allowed": False,
        "capital_authority": False,
        "reason_codes": list(r.get("reason_codes") or []),
    }


def compile_setup_families(
    confirmed_df,
    current_price: float | None,
    base_features: dict | None,
    config: dict | None = None,
) -> dict:
    """Compile raw SFC evidence, reconcile it, and return runtime evidence.

    ``confirmed_df`` retains the SFC-1 completed-Daily requirement.  This
    function adds no new market data and performs no tiering.
    """
    raw = _raw_compiler.compile_setup_families(
        confirmed_df,
        current_price,
        base_features,
        config,
    )
    resolved = family_resolver.reconcile_compiled_evidence(raw)
    out = deepcopy(resolved)
    out["runtime_version"] = RUNTIME_VERSION

    primary = str(out.get("primary_family") or NONE)
    families = out.get("families")
    families = families if isinstance(families, dict) else {}
    primary_obj = families.get(primary) if primary != NONE else None

    if isinstance(primary_obj, dict):
        metrics = primary_obj.get("metrics")
        metrics = dict(metrics) if isinstance(metrics, dict) else {}
        metrics["cross_family_resolution"] = _compact_resolution(
            out.get("family_resolution")
        )
        primary_obj["metrics"] = metrics

    return out


def __getattr__(name: str) -> Any:
    """Delegate non-overridden compiler helpers/constants to raw SFC-1."""
    return getattr(_raw_compiler, name)

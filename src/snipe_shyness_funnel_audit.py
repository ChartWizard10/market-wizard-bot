"""Phase 14U — SNIPE / STARTER shyness funnel audit (read-only diagnostic).

Answers a different question than Phase 14R. 14R asked "why is there no
SNIPE_IT?" from the blocker taxonomy alone. 14U asks **where in the 13-stage
scan pipeline** a valid SNIPE_IT / STARTER opportunity is capped, blocked,
suppressed, or never admitted at all — and, just as importantly, which of
those stages the persisted evidence can and cannot actually see.

Doctrine (permanent):
  - READ-ONLY / DIAGNOSTIC ONLY. This module never mutates a row, never writes
    state, never touches tiering, capital, routing, dedup, cooldown, cadence,
    thresholds, or the ladder. It produces evidence for a human calibration
    decision. It never promotes anything and never loosens a gate.
  - Pure stdlib + existing pure helpers. Never raises.
  - No ticker is special-cased. Every row is judged by the same funnel.
  - Honest observability. A stage this module cannot observe is reported as
    unobservable — never silently counted as zero. See OBSERVABILITY below.

OBSERVABILITY — the single most important honesty constraint of this phase
--------------------------------------------------------------------------
`state_store.record_alert()` is called from `scheduler.run_scan_pipeline()`
ONLY when `send_result["sent"]` is True (scheduler Step 8). Therefore the
persisted `alert_history` ledger contains **sent alerts only**. It contains no
record of:

  - tickers rejected by the prefilter (score / veto / data quality)
  - tickers that scored above `prefilter_min_score` but fell outside
    `prefilter.max_claude_candidates_per_scan` (the top-N cap)
  - tickers Claude never analyzed (cap, API error, rate limit)
  - rows whose `final_tier` was WAIT (never routed, never recorded)
  - rows suppressed by dedup or cooldown (`check_alert` returns should_alert
    False -> `send_alert` does not send -> `record_alert` is never called)
  - rows routed to channel `none`

Nor does the state file carry any scan-level ledger: `state_store._empty_state`
is `{"tickers": {}, "meta": {...}}` only.

Consequence, stated plainly: **pre-top-30 shyness and suppression shyness
cannot be determined from the current persisted alert_history.** The six
classes in UNOBSERVABLE_CLASSES are therefore part of the vocabulary (so a
later phase that adds a scan-level ledger can populate them) but are NEVER
assigned by `classify_row()` today. The report names them as blind spots
instead of reporting a false zero.

Usage (production):
    from src import snipe_shyness_funnel_audit as ssfa
    report = ssfa.run_shyness_funnel_audit(config=config, limit=100)
    print(ssfa.render_shyness_funnel_audit(report))

Usage (tests / offline):
    report = ssfa.run_shyness_funnel_audit(rows=my_rows)
"""

from src import snipe_blocker_taxonomy as tax
from src import snipe_ladder_judgment as ladder_mod

# ---------------------------------------------------------------------------
# The 13-stage funnel (mirrors src/scheduler.py run_scan_pipeline order)
# ---------------------------------------------------------------------------

OBSERVABLE = "OBSERVABLE"
NOT_PERSISTED = "NOT_PERSISTED"
PARTIAL = "PARTIAL"

STAGES = (
    {"id": "UNIVERSE_ADMISSION", "n": 1,
     "scheduler_step": "ticker universe load",
     "observability": NOT_PERSISTED,
     "note": "Universe membership is not persisted per scan."},
    {"id": "MARKET_DATA_ENRICHMENT", "n": 2,
     "scheduler_step": "Step 1-2 (batch download + enrich)",
     "observability": NOT_PERSISTED,
     "note": "Data-quality failures are counted in the scan summary only, never persisted."},
    {"id": "PREFILTER_SCORE_VETO", "n": 3,
     "scheduler_step": "Step 3 (prefilter score + veto)",
     "observability": NOT_PERSISTED,
     "note": "Rejected tickers are never written to alert_history."},
    {"id": "CANDIDATE_CAP_TOP_N", "n": 4,
     "scheduler_step": "Step 3 (max_claude_candidates_per_scan cap)",
     "observability": NOT_PERSISTED,
     "note": "Below-cut ranks are never written to alert_history."},
    {"id": "CLAUDE_ANALYSIS", "n": 5,
     "scheduler_step": "Step 4 (async_claude_scan)",
     "observability": NOT_PERSISTED,
     "note": "Claude failures/rate-limits are scan-summary counters only."},
    {"id": "TIERING_BASE_VALIDATION", "n": 6,
     "scheduler_step": "Step 5 (tiering.validate)",
     "observability": OBSERVABLE,
     "note": "Score, tier, capital_action and applied_vetoes are persisted."},
    {"id": "ONE_H_ENTRY_PROOF", "n": 7,
     "scheduler_step": "Step 6.57 (one_hour_entry)",
     "observability": OBSERVABLE,
     "note": "Phase 14O compact one_hour_entry snapshot is persisted."},
    {"id": "TIMEFRAME_ALIGNMENT_AND_HTF", "n": 8,
     "scheduler_step": "Step 6.58 / 6.585 (timeframe_alignment + higher_timeframe_context)",
     "observability": OBSERVABLE,
     "note": "Phase 14O / 14I compact snapshots are persisted."},
    {"id": "SNIPE_GATE_AUDIT", "n": 9,
     "scheduler_step": "Step 6.59 (snipe_gate_audit)",
     "observability": OBSERVABLE,
     "note": "Phase 14H.1 compact gate-audit snapshot is persisted."},
    {"id": "LADDER_ARBITRATION", "n": 10,
     "scheduler_step": "Step 6.592 (apply_ladder_arbitration)",
     "observability": PARTIAL,
     "note": "Ladder provenance depends on the row (see scope note)."},
    {"id": "DOWNGRADE_ONLY_SEAL", "n": 11,
     "scheduler_step": "Step 6.595 / 6.596 (seal + reconciliation)",
     "observability": OBSERVABLE,
     "note": "snipe_confirmed_seal marker is persisted when the seal applied."},
    {"id": "DEDUP_AND_COOLDOWN", "n": 12,
     "scheduler_step": "Step 6 (state_store.check_alert)",
     "observability": NOT_PERSISTED,
     "note": "Suppressed rows are never recorded — only survivors reach alert_history."},
    {"id": "ROUTING_AND_ALERT_WORDING", "n": 13,
     "scheduler_step": "Step 7 (discord_alerts.send_alert)",
     "observability": PARTIAL,
     "note": "final_discord_channel is persisted for sent rows only; channel=none rows are never recorded."},
)

STAGE_IDS = tuple(s["id"] for s in STAGES)

# ---------------------------------------------------------------------------
# Shyness classification vocabulary (closed set)
# ---------------------------------------------------------------------------

PREFILTER_REJECTED = "PREFILTER_REJECTED"
NOT_IN_TOP_30 = "NOT_IN_TOP_30"
CLAUDE_NOT_ANALYZED = "CLAUDE_NOT_ANALYZED"
BASE_TIER_CAPPED = "BASE_TIER_CAPPED"
ONE_H_PROOF_MISSING = "ONE_H_PROOF_MISSING"
ONE_H_PROOF_TOO_STRICT = "ONE_H_PROOF_TOO_STRICT"
FOUR_H_LOCATION_REPAIR_CAP = "FOUR_H_LOCATION_REPAIR_CAP"
TIMEFRAME_ALIGNMENT_CAP = "TIMEFRAME_ALIGNMENT_CAP"
SNIPE_GATE_BLOCKED = "SNIPE_GATE_BLOCKED"
LADDER_CAPPED = "LADDER_CAPPED"
SEAL_DOWNGRADED = "SEAL_DOWNGRADED"
DEDUP_SUPPRESSED = "DEDUP_SUPPRESSED"
COOLDOWN_SUPPRESSED = "COOLDOWN_SUPPRESSED"
ROUTING_SUPPRESSED = "ROUTING_SUPPRESSED"
ALERT_WORDING_UNDERSTATED = "ALERT_WORDING_UNDERSTATED"
CORRECTLY_BLOCKED_HARD_FAILURE = "CORRECTLY_BLOCKED_HARD_FAILURE"
CORRECTLY_WAITING_FOR_PROOF = "CORRECTLY_WAITING_FOR_PROOF"
POSSIBLE_STARTER_UNDERCALL = "POSSIBLE_STARTER_UNDERCALL"
POSSIBLE_SNIPE_UNDERCALL = "POSSIBLE_SNIPE_UNDERCALL"
# Defensive terminal member: a row whose evidence supports no other statement.
# Never used to hide a finding — it is reported and counted like any other class.
UNCLASSIFIED = "UNCLASSIFIED"

SHYNESS_CLASSES = {
    PREFILTER_REJECTED, NOT_IN_TOP_30, CLAUDE_NOT_ANALYZED, BASE_TIER_CAPPED,
    ONE_H_PROOF_MISSING, ONE_H_PROOF_TOO_STRICT, FOUR_H_LOCATION_REPAIR_CAP,
    TIMEFRAME_ALIGNMENT_CAP, SNIPE_GATE_BLOCKED, LADDER_CAPPED, SEAL_DOWNGRADED,
    DEDUP_SUPPRESSED, COOLDOWN_SUPPRESSED, ROUTING_SUPPRESSED,
    ALERT_WORDING_UNDERSTATED, CORRECTLY_BLOCKED_HARD_FAILURE,
    CORRECTLY_WAITING_FOR_PROOF, POSSIBLE_STARTER_UNDERCALL,
    POSSIBLE_SNIPE_UNDERCALL, UNCLASSIFIED,
}

# Classes that CANNOT be derived from the current persisted alert_history,
# because the rows they describe are never written (see OBSERVABILITY above).
# classify_row() must never emit one of these.
UNOBSERVABLE_CLASSES = {
    PREFILTER_REJECTED, NOT_IN_TOP_30, CLAUDE_NOT_ANALYZED,
    DEDUP_SUPPRESSED, COOLDOWN_SUPPRESSED, ROUTING_SUPPRESSED,
}

# Classes that describe a correct, doctrine-compliant outcome (not shyness).
BENIGN_CLASSES = {
    CORRECTLY_BLOCKED_HARD_FAILURE, CORRECTLY_WAITING_FOR_PROOF,
}


def is_shy_class(primary) -> bool:
    """THE canonical shyness predicate — Phase 14V.2.

    Telemetry provenance may change how CERTAIN we are about a row. It may
    never change what "shy" MEANS. A row is shy only when it carries a
    finding that is neither benign nor unclassified:

      - CORRECTLY_WAITING_FOR_PROOF / CORRECTLY_BLOCKED_HARD_FAILURE are
        benign. Correctly waiting is not missed opportunity.
      - UNCLASSIFIED is not proven shyness. Unknown is not failure.

    Every row path — legacy, telemetry-backed and telemetry-only — must use
    this one predicate. A divergent copy previously let telemetry-only benign
    rows inflate the headline shy count.
    """
    return bool(primary) and primary not in BENIGN_CLASSES and primary != UNCLASSIFIED

CLASS_STAGE = {
    PREFILTER_REJECTED: "PREFILTER_SCORE_VETO",
    NOT_IN_TOP_30: "CANDIDATE_CAP_TOP_N",
    CLAUDE_NOT_ANALYZED: "CLAUDE_ANALYSIS",
    BASE_TIER_CAPPED: "TIERING_BASE_VALIDATION",
    ONE_H_PROOF_MISSING: "ONE_H_ENTRY_PROOF",
    ONE_H_PROOF_TOO_STRICT: "ONE_H_ENTRY_PROOF",
    FOUR_H_LOCATION_REPAIR_CAP: "TIMEFRAME_ALIGNMENT_AND_HTF",
    TIMEFRAME_ALIGNMENT_CAP: "TIMEFRAME_ALIGNMENT_AND_HTF",
    SNIPE_GATE_BLOCKED: "SNIPE_GATE_AUDIT",
    LADDER_CAPPED: "LADDER_ARBITRATION",
    SEAL_DOWNGRADED: "DOWNGRADE_ONLY_SEAL",
    DEDUP_SUPPRESSED: "DEDUP_AND_COOLDOWN",
    COOLDOWN_SUPPRESSED: "DEDUP_AND_COOLDOWN",
    ROUTING_SUPPRESSED: "ROUTING_AND_ALERT_WORDING",
    ALERT_WORDING_UNDERSTATED: "ROUTING_AND_ALERT_WORDING",
    CORRECTLY_BLOCKED_HARD_FAILURE: "TIERING_BASE_VALIDATION",
    CORRECTLY_WAITING_FOR_PROOF: "SNIPE_GATE_AUDIT",
    POSSIBLE_STARTER_UNDERCALL: "LADDER_ARBITRATION",
    POSSIBLE_SNIPE_UNDERCALL: "LADDER_ARBITRATION",
    UNCLASSIFIED: "TIERING_BASE_VALIDATION",
}

# ---------------------------------------------------------------------------
# Gate -> stage families (gate codes come from snipe_gate_audit / 14Q taxonomy)
# ---------------------------------------------------------------------------

_ONE_H_GATES = {
    "ONE_H_TRIGGER_CONFIRMED", "RETEST_CONFIRMED", "HOLD_CONFIRMED",
    "CANDLE_TRUTH_SUPPORTIVE", "LIVE_EDGE_SAFE", "ONE_H_DATA_FRESH",
}
# The subset that asks for a CLOSED-BAR confirmation. During market hours the
# working bar is open by definition, so these can be structurally unreachable
# even when the base sequence is already confirmed (the Phase 14R finding).
#
# CANDLE_HOSTILE_REJECTION is deliberately EXCLUDED: hostile rejection is real
# adverse evidence, not a scan-cadence artifact, and must never be reported as
# over-strictness. Doctrine stands — an open candle cannot create SNIPE
# authority; flagging this family only marks it for operator review.
_CLOSED_BAR_GATES = {
    "LIVE_EDGE_SAFE", "CANDLE_TRUTH_SUPPORTIVE",
    tax.CODE_UNRESOLVED, tax.CODE_UNKNOWN,
}
_FOUR_H_GATES = {"FOUR_H_LOCATION_VALID"}
_ALIGNMENT_GATES = {
    "DAILY_PERMISSION_GRANTED", "HTF_EXTENDED", "HTF_CONTEXT_GRADE",
    "TIMEFRAME_ALIGNMENT",
}

_TIER_RANK = {"WAIT": 0, "NEAR_ENTRY": 1, "STARTER": 2, "SNIPE_IT": 3}

_CAPITAL_TIERS = {"STARTER", "SNIPE_IT"}

# Wording that denies capital. Flagged only when the row actually GRANTED
# capital — a NEAR_ENTRY row saying "no capital" is correct, not understated.
_NO_CAPITAL_MARKERS = (
    "no capital", "wait_no_capital", "watch only", "do not enter",
    "no trade", "not actionable", "no scanner capital",
)

_DEFAULT_LIMIT = 100
_MIN_LIMIT = 10
_MAX_LIMIT = 300
_MAX_EXAMPLES = 8


# ---------------------------------------------------------------------------
# Safe read helpers (persisted rows may predate any phase)
# ---------------------------------------------------------------------------

def _d(obj, key):
    v = obj.get(key) if isinstance(obj, dict) else None
    return v if isinstance(v, dict) else {}


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _s(value) -> str:
    return str(value).strip().upper() if isinstance(value, str) else ""


def _codes(items) -> list:
    """Blocker/gate codes from either taxonomy dicts or plain strings."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            code = it.get("code") or it.get("gate") or it.get("name")
            if isinstance(code, str) and code.strip():
                out.append(code.strip())
        elif isinstance(it, str) and it.strip():
            out.append(it.split(":", 1)[0].strip())
    return out


def _tier_of(row) -> str:
    if not isinstance(row, dict):
        return "UNKNOWN"
    return _s(row.get("tier")) or _s(row.get("final_tier")) or "UNKNOWN"


def _rank(tier) -> int:
    return _TIER_RANK.get(_s(tier), -1)


def _tier_cfg(config, tier_key) -> dict:
    return _d(_d(config or {}, "tiers"), tier_key)


def _collect_rows_from_state(state, limit) -> list:
    rows = []
    tickers = state.get("tickers") if isinstance(state, dict) else None
    if isinstance(tickers, dict):
        for tkr, tdata in tickers.items():
            hist = tdata.get("alert_history") if isinstance(tdata, dict) else None
            if not isinstance(hist, list):
                continue
            for r in hist:
                if not isinstance(r, dict):
                    continue
                if r.get("ticker"):
                    rows.append(r)
                else:
                    merged = dict(r)          # copy — never mutate source state
                    merged["ticker"] = tkr
                    rows.append(merged)
    rows.sort(key=lambda r: str(r.get("alerted_at") or ""), reverse=True)
    return rows[: max(0, int(limit))]


# ---------------------------------------------------------------------------
# Evidence ceiling — the highest tier this row's own evidence would support
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE = "HIGH"
LOW_CONFIDENCE = "LOW"

# ---------------------------------------------------------------------------
# Phase 14U.1 — recompute attribution provenance
# ---------------------------------------------------------------------------
#
# There are TWO different confidence questions, and conflating them is a lie:
#
#   1. Can we recompute a plausible CURRENT ladder from the persisted evidence?
#      -> answered by recompute_confidence (HIGH / LOW)
#   2. Can we prove this was the ladder/arbitration decision AT SCAN TIME?
#      -> answered by ladder_attribution
#
# A row can be HIGH confidence on (1) and still unproven on (2), because
# `state_store.record_alert` does not persist `snipe_ladder`. Recomputation is
# evidence RECONSTRUCTION; it is not scan-time causality.
#
# Consequence: LADDER_CAPPED is a causal claim about what the scanner did at
# stage 10. It may only be asserted when scan-time ladder evidence actually
# exists. A reconstruction may still surface POSSIBLE_SNIPE_UNDERCALL /
# POSSIBLE_STARTER_UNDERCALL — useful review evidence, not proven causality.
#
# No calendar inference is used anywhere: no merge timestamp, no deploy date,
# no scanner version guessed from alerted_at. Provenance comes only from
# whether the row itself carries the ladder object.

ATTRIBUTION_STORED = "STORED_SCAN_TIME"
ATTRIBUTION_RECONSTRUCTED = "RECONSTRUCTED_NOT_PROVEN"

_RECONSTRUCTION_CAVEAT = (
    "Current-code recomputation places this row above the served tier, but the "
    "scan-time snipe_ladder was not persisted, so ladder arbitration cannot be "
    "causally attributed for this historical row."
)


def recompute_confidence(row) -> dict:
    """How much the recomputed ladder for this persisted row can be trusted.

    `state_store.record_alert` does NOT persist `snipe_ladder`, `candle_evidence`,
    or `final_signal.invalidation_condition`. The Phase 14S ladder derives
    `inval_clear` from either the invalidation CONDITION text or
    `one_hour_entry.invalidation.clear` — so a row that carries neither
    recomputes as "invalidation missing or unclear" even when the live scan had
    a perfectly clear invalidation. That is a persistence gap, not a scanner
    block, and this audit must never report it as one.

    Returns {"level": HIGH|LOW, "gaps": [str, ...]}.
    """
    if not isinstance(row, dict):
        return {"level": LOW_CONFIDENCE, "gaps": ["row is not a dict"]}
    gaps = []
    oh = _d(row, "one_hour_entry")
    if not oh:
        gaps.append("one_hour_entry not persisted on this row (pre-Phase-14O history)")
    if (_d(oh, "invalidation").get("clear") is not True
            and not str(row.get("invalidation_condition") or "").strip()):
        # Phase 14V persists final_signal.invalidation_condition, so a 14V-backed
        # row proves invalidation clarity directly. Legacy rows carry neither
        # that field nor a 1H invalidation snapshot, and stay unprovable.
        if _num(row.get("invalidation_level")) is not None:
            gaps.append(
                "invalidation_condition is not persisted by state_store.record_alert "
                "and one_hour_entry.invalidation.clear is not True — a recomputed "
                "ladder cannot confirm invalidation clarity for this row"
            )
    return {"level": LOW_CONFIDENCE if gaps else HIGH_CONFIDENCE, "gaps": gaps}


def evidence_ceiling(row, config=None) -> dict:
    """Recompute, read-only, the ladder tier this row's persisted evidence
    supports, plus the taxonomy floor. Never mutates the row.

    Returns {"ladder": <ladder dict>, "ceiling_tier": str, "floor_tier": str}.
    The Phase 14S ladder is NOT persisted by state_store.record_alert, so this
    is always a recompute — labeled as such in the report.
    """
    ladder = row.get("snipe_ladder") if isinstance(row, dict) else None
    if not isinstance(ladder, dict):
        ladder = ladder_mod.classify_snipe_ladder(row)
        source = "recomputed_from_persisted_row"
    else:
        source = "stored_scan_time"
    classification = tax.classify_blockers(row)
    return {
        "ladder": ladder,
        "ladder_source": source,
        "classification": classification,
        "ceiling_tier": _s(ladder.get("existing_final_tier_recommendation")) or "WAIT",
        "floor_tier": _s(classification.get("recommended_floor")) or "NEAR_ENTRY",
    }


# ---------------------------------------------------------------------------
# Per-row classification
# ---------------------------------------------------------------------------

def _wording_understated(row) -> bool:
    """True when a capital-granting row carries no-capital wording."""
    tier = _tier_of(row)
    capital = str(row.get("capital_action") or "").strip().lower()
    grants_capital = tier in _CAPITAL_TIERS and capital in ("starter_only", "full_quality_allowed")
    if not grants_capital:
        return False
    blob = " ".join(str(x or "") for x in (
        row.get("sanitized_reason"), row.get("sanitized_next_action"),
        row.get("reason"), _d(row, "one_hour_entry").get("scanner_sentence"),
        _d(row, "snipe_gate_audit").get("diagnostic_sentence"),
    )).lower()
    return any(m in blob for m in _NO_CAPITAL_MARKERS)


def _one_h_absent(row) -> bool:
    oh = _d(row, "one_hour_entry")
    if not oh:
        return True
    if _s(oh.get("status")) in ("", "DISABLED", "UNAVAILABLE", "NO_DATA"):
        return True
    prh = _d(oh, "pullback_retest_hold")
    return not _s(prh.get("retest_truth")) and not _s(prh.get("hold_truth"))


def _alignment_capped(row, blocking_codes) -> bool:
    if any(c in _ALIGNMENT_GATES for c in blocking_codes):
        return True
    tfa = _d(row, "timeframe_alignment")
    if _d(row, "higher_timeframe_context").get("blocks_snipe_contextually") is True:
        return True
    return bool(tfa.get("conflicts")) or bool(tfa.get("hard_caps_applied"))


def _base_tier_capped(row, ladder, config):
    """The numeric tiering score — not a proof gate — is the binding constraint.

    Returns (bool, note). Only true when the ladder says the proof for the next
    rung exists yet the persisted score sits under that rung's min_score.
    """
    score = _num(row.get("score"))
    if score is None:
        return (False, "")
    tier = _tier_of(row)
    snipe_min = _num(_tier_cfg(config, "snipe_it").get("min_score"))
    starter_min = _num(_tier_cfg(config, "starter").get("min_score"))
    if (tier != "SNIPE_IT" and snipe_min is not None and score < snipe_min
            and _s(ladder.get("sniper_grade")) not in ("", "NONE")):
        return (True, f"score {score:g} < tiers.snipe_it.min_score {snipe_min:g} "
                      f"while ladder sniper_grade={ladder.get('sniper_grade')}")
    if (_rank(tier) < _rank("STARTER") and starter_min is not None and score < starter_min
            and _s(ladder.get("starter_grade")) not in ("", "NONE")):
        return (True, f"score {score:g} < tiers.starter.min_score {starter_min:g} "
                      f"while ladder starter_grade={ladder.get('starter_grade')}")
    return (False, "")


def classify_row(row, config=None) -> dict:
    """Classify one persisted alert_history row onto the shyness funnel.

    Pure; never raises; never mutates the row. Never emits a class from
    UNOBSERVABLE_CLASSES — those describe rows that are never persisted.

    Returns a dict with `primary_class`, `stage`, ordered `classes`, the
    recomputed ladder/taxonomy evidence, and a plain-language `why`.
    """
    try:
        return _classify_row(row, config)
    except Exception as exc:  # pragma: no cover - defensive; never break an audit
        return {
            "ticker": (row or {}).get("ticker") if isinstance(row, dict) else None,
            "scan_id": (row or {}).get("scan_id") if isinstance(row, dict) else None,
            "alerted_at": (row or {}).get("alerted_at") if isinstance(row, dict) else None,
            "capital_action": None, "score": None,
            "tier": "UNKNOWN", "ceiling_tier": "UNKNOWN", "floor_tier": "UNKNOWN",
            "primary_class": UNCLASSIFIED, "stage": CLASS_STAGE[UNCLASSIFIED],
            "classes": [UNCLASSIFIED], "is_shy": False,
            "ceiling_vs_served": "AT_CEILING",
            "recompute_confidence": LOW_CONFIDENCE,
            "recompute_gaps": [f"classification error: {exc}"],
            "ladder_source": "error", "ladder_tier": None,
            "ladder_attribution": ATTRIBUTION_RECONSTRUCTED,
            "sniper_grade": None, "starter_grade": None,
            "seal_applied": False, "promotion_state": None,
            "blocking_codes": [], "soft_cap_codes": [],
            "why": f"classification error: {exc}",
        }


def _classify_row(row, config) -> dict:
    if not isinstance(row, dict):
        row = {}

    ec = evidence_ceiling(row, config)
    ladder = ec["ladder"]
    clazz = ec["classification"]
    tier = _tier_of(row)
    ceiling = ec["ceiling_tier"]
    floor = ec["floor_tier"]

    sga = _d(row, "snipe_gate_audit")
    seal = _d(row, "snipe_confirmed_seal")
    seal_applied = seal.get("applied") is True

    hard = list(ladder.get("hard_failures") or [])
    capital_codes = _codes(clazz.get("capital_blockers"))
    snipe_only_codes = _codes(clazz.get("snipe_only_blockers"))
    soft_codes = _codes(clazz.get("soft_caps"))
    gate_codes = _codes(sga.get("blocked_gate_names")) + _codes(sga.get("missing_proofs"))
    # A code already classed as a soft cap is not a blocker — the 14Q taxonomy
    # guarantees single-class membership, so honour it here too.
    soft_set = set(soft_codes)
    blocking_codes = [c for c in (capital_codes + snipe_only_codes + gate_codes)
                      if c not in soft_set]
    base_ok = clazz.get("base_sequence_confirmed") is True

    conf = recompute_confidence(row)
    attribution = (ATTRIBUTION_STORED if ec["ladder_source"] == "stored_scan_time"
                   else ATTRIBUTION_RECONSTRUCTED)

    classes = []

    def add(name):
        if name not in classes:
            classes.append(name)

    # -- 0. Recompute too weak to judge? Say so; never invent a verdict. ------
    # The ladder recompute leans on fields record_alert does not persist. When
    # they are absent, a "hard failure" or an "under-call" would be an artifact
    # of the ledger, not a statement about the scanner.
    if conf["level"] == LOW_CONFIDENCE:
        add(UNCLASSIFIED)
        why = ("not determinable from persisted history — " + "; ".join(conf["gaps"]))
        return _row_result(row, ec, tier, ceiling, floor, classes,
                           blocking_codes, soft_codes, why, conf)

    # -- 1. True hard failure always wins. Nothing below is shyness. ----------
    if hard:
        add(CORRECTLY_BLOCKED_HARD_FAILURE)
        why = "true hard failure: " + "; ".join(str(h) for h in hard[:3])
        return _row_result(row, ec, tier, ceiling, floor, classes,
                           blocking_codes, soft_codes, why, conf)

    # -- 2. Tier sits BELOW the ceiling this row's own evidence supports ------
    #
    # Phase 14U.1 provenance rule. SEAL_DOWNGRADED stays definitive: the seal
    # marker IS persisted, so the claim rests on scan-time evidence.
    # LADDER_CAPPED is a causal claim about stage 10 and may only be asserted
    # when the scan-time ladder itself was persisted. On a reconstruction the
    # useful signal survives as POSSIBLE_*_UNDERCALL below — evidence for
    # review, never proven historical causality.
    below_ceiling = _rank(ceiling) > _rank(tier) >= 0
    if below_ceiling:
        if seal_applied:
            add(SEAL_DOWNGRADED)
        elif attribution == ATTRIBUTION_STORED:
            add(LADDER_CAPPED)

    # -- 3. Which stage family holds the row under SNIPE_IT? -----------------
    if _rank(tier) < _rank("SNIPE_IT"):
        if _one_h_absent(row):
            add(ONE_H_PROOF_MISSING)
        elif (base_ok and not capital_codes and snipe_only_codes
              and all(c in _CLOSED_BAR_GATES for c in snipe_only_codes)):
            # Base sequence already confirmed, no capital blocker, and the only
            # thing left is a closed-bar demand the live scan cadence may never
            # satisfy. Flagged for operator review — not a licence to promote.
            add(ONE_H_PROOF_TOO_STRICT)
        elif any(c in _ONE_H_GATES for c in blocking_codes):
            add(ONE_H_PROOF_MISSING)

        if any(c in _FOUR_H_GATES for c in blocking_codes) or \
                _s(_d(_d(row, "timeframe_alignment"), "operational_timeframe").get("state")).startswith("REPAIR"):
            add(FOUR_H_LOCATION_REPAIR_CAP)

        if _alignment_capped(row, blocking_codes):
            add(TIMEFRAME_ALIGNMENT_CAP)

        if _s(sga.get("promotion_state")) == "PROMOTION_BLOCKED" or gate_codes:
            add(SNIPE_GATE_BLOCKED)

        capped, note = _base_tier_capped(row, ladder, config)
        if capped:
            add(BASE_TIER_CAPPED)
        else:
            note = ""

        # -- 4. Under-call detection (taxonomy floor above the served tier) --
        if _rank(floor) > _rank(tier):
            add(POSSIBLE_SNIPE_UNDERCALL if floor == "SNIPE_IT"
                else POSSIBLE_STARTER_UNDERCALL)
        elif below_ceiling:
            add(POSSIBLE_SNIPE_UNDERCALL if ceiling == "SNIPE_IT"
                else POSSIBLE_STARTER_UNDERCALL)
    else:
        note = ""

    # -- 5. Wording that understates a capital grant --------------------------
    if _wording_understated(row):
        add(ALERT_WORDING_UNDERSTATED)

    # -- 6. Nothing above fired: the row is where its evidence puts it --------
    if not classes:
        if _rank(tier) < _rank("SNIPE_IT") and (capital_codes or snipe_only_codes or soft_codes):
            add(CORRECTLY_WAITING_FOR_PROOF)
        elif _rank(tier) < _rank("SNIPE_IT"):
            add(CORRECTLY_WAITING_FOR_PROOF)

    why = _why_sentence(tier, ceiling, floor, classes, blocking_codes, soft_codes,
                        note, attribution, below_ceiling)
    return _row_result(row, ec, tier, ceiling, floor, classes,
                       blocking_codes, soft_codes, why, conf)


def _ceiling_vs_served(tier, ceiling) -> str:
    """Where the served tier sits against the RECOMPUTED evidence ceiling."""
    if _rank(ceiling) > _rank(tier):
        return "BELOW_CEILING"
    if _rank(ceiling) < _rank(tier):
        # Not shyness. The live scan saw evidence (candle_evidence, the
        # scan-time ladder, the invalidation condition) that record_alert does
        # not persist, so the recompute is the weaker view — say that, do not
        # imply the row was over-promoted.
        return "ABOVE_RECOMPUTED_CEILING"
    return "AT_CEILING"


def _why_sentence(tier, ceiling, floor, classes, blocking_codes, soft_codes, note,
                  attribution=ATTRIBUTION_RECONSTRUCTED, below_ceiling=False) -> str:
    if not classes:
        rel = _ceiling_vs_served(tier, ceiling)
        if rel == "ABOVE_RECOMPUTED_CEILING":
            return (f"{tier} sits above its recomputed ceiling ({ceiling}); the scan-time "
                    f"ladder saw evidence this ledger does not persist. No shyness detected.")
        return f"{tier} matches its evidence ceiling ({ceiling}); no shyness detected."
    primary = classes[0]
    if primary == UNCLASSIFIED:
        return "not determinable from persisted history."
    named = ", ".join(dict.fromkeys(blocking_codes)) or "none named"
    if primary == CORRECTLY_WAITING_FOR_PROOF:
        return (f"{tier} is correct: proof still outstanding ({named}); "
                f"missing proof is not failed proof.")
    if primary == ONE_H_PROOF_TOO_STRICT:
        return (f"base sequence confirmed and no capital blocker, yet SNIPE is held only by "
                f"closed-bar proof ({named}) that live scan cadence may never produce. "
                f"Doctrine still holds — an open candle cannot create SNIPE authority; "
                f"flagged for operator review, not promoted.")
    parts = [f"evidence ceiling {ceiling} / taxonomy floor {floor} vs served tier {tier}",
             f"blocking: {named}"]
    if soft_codes:
        parts.append("soft caps: " + ", ".join(dict.fromkeys(soft_codes)))
    if note:
        parts.append(note)
    sentence = "; ".join(parts) + "."
    if below_ceiling and attribution == ATTRIBUTION_RECONSTRUCTED:
        sentence += " " + _RECONSTRUCTION_CAVEAT
    return sentence


def _row_result(row, ec, tier, ceiling, floor, classes, blocking_codes,
                soft_codes, why, conf=None) -> dict:
    ladder = ec["ladder"]
    # No fabricated verdict: a row sitting at (or above) its ceiling with no
    # finding gets primary_class None, not a borrowed "waiting for proof".
    primary = classes[0] if classes else None
    conf = conf if isinstance(conf, dict) else {"level": HIGH_CONFIDENCE, "gaps": []}
    return {
        "ticker": row.get("ticker"),
        "scan_id": row.get("scan_id"),
        "alerted_at": row.get("alerted_at"),
        "tier": tier,
        "capital_action": row.get("capital_action"),
        "score": row.get("score"),
        "ceiling_tier": ceiling,
        "floor_tier": floor,
        "ladder_tier": ladder.get("internal_ladder_tier"),
        "ladder_source": ec["ladder_source"],
        # Phase 14U.1 — can the scan-time ladder DECISION be attributed, as
        # opposed to merely reconstructed? Distinct from recompute_confidence.
        "ladder_attribution": (ATTRIBUTION_STORED
                               if ec["ladder_source"] == "stored_scan_time"
                               else ATTRIBUTION_RECONSTRUCTED),
        "sniper_grade": ladder.get("sniper_grade"),
        "starter_grade": ladder.get("starter_grade"),
        "seal_applied": _d(row, "snipe_confirmed_seal").get("applied") is True,
        "promotion_state": _d(row, "snipe_gate_audit").get("promotion_state"),
        "primary_class": primary,
        "stage": CLASS_STAGE.get(primary) if primary else None,
        "classes": list(classes),
        "is_shy": is_shy_class(primary),
        "ceiling_vs_served": _ceiling_vs_served(tier, ceiling),
        "recompute_confidence": conf["level"],
        "recompute_gaps": list(conf["gaps"]),
        "blocking_codes": list(dict.fromkeys(blocking_codes)),
        "soft_cap_codes": list(dict.fromkeys(soft_codes)),
        "why": why,
    }


# ---------------------------------------------------------------------------
# Public API — funnel report
# ---------------------------------------------------------------------------

def run_shyness_funnel_audit(rows=None, state=None, config=None,
                             limit=_DEFAULT_LIMIT, telemetry=None) -> dict:
    """Build the shyness funnel report. READ-ONLY. Never raises.

    `telemetry` is an optional Phase 14V ledger. When present, the stages 14V
    records become OBSERVABLE for telemetry-backed scans; legacy history is
    never retroactively upgraded.
    """
    try:
        return _run(rows, state, config, limit, telemetry)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return {
            "error": f"snipe_shyness_funnel_audit_error: {exc}",
            "source": "error", "total_rows": 0, "tier_counts": {},
            "class_counts": {}, "stage_counts": {}, "stages": [],
            "blind_spots": [], "persistence_gaps": [], "examples": [],
            "top_shyness_stages": [],
            "observability_note": "", "recommended_next_probes": [],
        }


def _run(rows, state, config, limit, telemetry=None) -> dict:
    source = "provided-rows"
    if rows is None:
        if state is None:
            from src import audit_access
            loaded = audit_access.load_state_readonly(config or {})
            if not (isinstance(loaded, dict) and loaded.get("ok")):
                return {
                    "error": (loaded or {}).get("error") or "state_unavailable",
                    "source": "alert_state.json (read-only)", "total_rows": 0,
                    "tier_counts": {}, "class_counts": {}, "stage_counts": {},
                    "stages": _stage_rows({}), "blind_spots": _blind_spots(config),
                    "persistence_gaps": _persistence_gaps(),
                    "examples": [], "top_shyness_stages": [],
                    "observability_note": _observability_note(),
                    "recommended_next_probes": _next_probes(),
                }
            state = loaded.get("state") or {}
            source = "alert_state.json (read-only)"
        else:
            source = "provided-state"
        rows = _collect_rows_from_state(state or {}, limit)
    else:
        rows = [r for r in rows if isinstance(r, dict)][: max(0, int(limit))]

    analyzed = [classify_row(r, config) for r in rows]

    # ---- Phase 14V.1: consume Layer-2 decision traces --------------------
    # Attach scan-time provenance to rows that already exist in alert_history
    # (never double-counted), then surface telemetry-ONLY judged rows the
    # history can never contain: WAIT, cooldown-suppressed, routing-none,
    # delivery-failed. Analysis failures are Stage-5 facts, not judgments,
    # and are counted separately rather than forced into an undercall class.
    # Phase 14V.1B: bound the telemetry window deterministically. Rows are
    # already capped at `limit`; consuming all 300 retained summaries / 9000
    # retained traces would silently mix a 100-row window with weeks of
    # telemetry and call it one homogeneous report.
    window = _telemetry_window(telemetry, limit)
    backed_ids = {str(s["scan_id"]) for s in window["summaries"] if s.get("scan_id")}
    traces = window["traces"]
    seen_keys = set()
    backed_rows = legacy_rows = 0
    for a in analyzed:
        key = (str(a.get("scan_id") or ""), str(a.get("ticker") or ""))
        seen_keys.add(key)
        t = traces.get(key)
        if t is not None or key[0] in backed_ids:
            backed_rows += 1
            a["telemetry_backed"] = True
            if isinstance(t, dict):
                a["telemetry"] = _attach_telemetry_facts(t)
        else:
            legacy_rows += 1
            a["telemetry_backed"] = False

    # Phase 14V.1C — DUAL SCOPE. The telemetry scan population and the legacy
    # alert-row population are bounded independently and are NOT the same
    # population. Every count names the population it covers.
    legacy_outside_window = sum(
        1 for a in analyzed
        if not a.get("telemetry_backed")
        and str(a.get("scan_id") or "") not in backed_ids)

    telemetry_only, analysis_outcomes = _telemetry_only_rows(traces, seen_keys)
    telemetry_only = telemetry_only[: max(0, int(limit))]
    analyzed.extend(telemetry_only)
    backed_rows += len(telemetry_only)
    # Evidence is organ-specific: each stage earns observability only from
    # evidence that belongs to it.
    stage_evidence = build_stage_evidence(window["summaries"], traces)

    tier_counts, class_counts, stage_counts = {}, {}, {}
    low_conf = 0
    above_ceiling = 0
    no_finding = 0
    for a in analyzed:
        tier_counts[a["tier"]] = tier_counts.get(a["tier"], 0) + 1
        for c in a["classes"]:
            class_counts[c] = class_counts.get(c, 0) + 1
        if not a["classes"]:
            no_finding += 1
        if a["is_shy"] and a.get("stage"):
            stage_counts[a["stage"]] = stage_counts.get(a["stage"], 0) + 1
        if a.get("recompute_confidence") == LOW_CONFIDENCE:
            low_conf += 1
        if a.get("ceiling_vs_served") == "ABOVE_RECOMPUTED_CEILING":
            above_ceiling += 1

    # Rank the shy rows by how close they were to a higher tier: biggest
    # evidence-vs-served gap first, then newest.
    shy = [a for a in analyzed if a["is_shy"]]
    shy.sort(key=lambda a: str(a.get("alerted_at") or ""), reverse=True)   # newest first
    shy.sort(key=lambda a: (                                              # stable re-sort
        -max(_rank(a["ceiling_tier"]), _rank(a["floor_tier"])),
        -(max(_rank(a["ceiling_tier"]), _rank(a["floor_tier"])) - _rank(a["tier"])),
    ))
    examples = shy[:_MAX_EXAMPLES]

    top_stages = sorted(stage_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "error": None,
        "source": source,
        "telemetry_backed_rows": backed_rows,
        "legacy_rows": legacy_rows,
        "telemetry_analysis_outcomes": analysis_outcomes,
        "total_rows": len(analyzed),
        "shy_rows": len(shy),
        "no_finding_rows": no_finding,
        "low_confidence_rows": low_conf,
        "above_recomputed_ceiling_rows": above_ceiling,
        "tier_counts": tier_counts,
        "class_counts": class_counts,
        "stage_counts": stage_counts,
        "telemetry_scans": len(backed_ids),
        "telemetry_window": window["meta"],
        "legacy_alert_window": {
            "rows_in_report": legacy_rows,
            "rows_outside_telemetry_window": legacy_outside_window,
            "limit": limit,
        },
        "scope": ("TELEMETRY_ONLY" if backed_ids and not legacy_rows else
                  "MIXED" if backed_ids and legacy_rows else "LEGACY_ONLY"),
        "stage_evidence": stage_evidence,
        "stages": _stage_rows(stage_counts, len(backed_ids), backed_rows, legacy_rows,
                              stage_evidence),
        "top_shyness_stages": [{"stage": s, "count": n} for s, n in top_stages],
        "examples": examples,
        "blind_spots": _blind_spots(config, stage_evidence),
        "persistence_gaps": _persistence_gaps(stage_evidence),
        "observability_note": _observability_note(stage_evidence, backed_rows,
                                                  legacy_rows, legacy_outside_window),
        "recommended_next_probes": _next_probes(stage_evidence),
        "newest": (analyzed[0].get("alerted_at") if analyzed else None),
        "oldest": (analyzed[-1].get("alerted_at") if analyzed else None),
    }


# Stages that Phase 14V scan-time telemetry makes observable. They stay
# NOT_PERSISTED for legacy history: a stage is only observable for scans that
# actually wrote a telemetry summary. Historical rows are never retroactively
# upgraded.
TELEMETRY_BACKED_STAGES = {
    "UNIVERSE_ADMISSION", "MARKET_DATA_ENRICHMENT", "PREFILTER_SCORE_VETO",
    "CANDIDATE_CAP_TOP_N", "CLAUDE_ANALYSIS", "DEDUP_AND_COOLDOWN",
}

# ---------------------------------------------------------------------------
# Phase 14V.1A — stage OUTCOME visibility is not the same question as
# candidate-level shyness ATTRIBUTION.
# ---------------------------------------------------------------------------
#
#   observability        -> can we see WHAT the stage did?
#   shyness_attribution  -> can we prove a SPECIFIC candidate was a missed
#                           SNIPE/STARTER at that stage?
#
# An observed outcome is not automatically proven shyness. Of the six stages
# Phase 14V makes visible, only DEDUP_AND_COOLDOWN carries row-level causal
# truth: its `analyzed` traces hold check_alert_reason, cooldown_suppressed,
# check_alert_evaluated_tier AND the surviving final tier + ladder, so a
# suppressed judged row is genuinely attributable.
#
# The other five are outcome-only:
#   1 UNIVERSE_ADMISSION      summary count; no per-ticker record at all
#   2 MARKET_DATA_ENRICHMENT  summary count; no per-ticker record at all
#   3 PREFILTER_SCORE_VETO    histograms only; rejected tickers get no trace
#   4 CANDIDATE_CAP_TOP_N     near-cut traces prove a ticker ranked outside the
#                             boundary — NOT that it was a valid SNIPE/STARTER,
#                             because no judgment ever ran on it
#   5 CLAUDE_ANALYSIS         analysis_failed / rate_limited / tiering_failed
#                             prove a pipeline outcome, not a market undercall
#
# So those five report shy_rows_attributed = None with an explicit reason, and
# must never render "not persisted" — the evidence IS persisted; the causal
# claim is what is missing.

# ---------------------------------------------------------------------------
# Phase 14V.1B — evidence is ORGAN-SPECIFIC.
# ---------------------------------------------------------------------------
#
# A single global "some telemetry exists" flag let evidence from one stage
# make another stage look observed. Stage-5 analysis failures are not
# check_alert evidence; near-cut traces are not check_alert evidence. Each
# stage now earns observability ONLY from evidence that belongs to it, and
# three different counts are kept distinct:
#
#   outcome            did we observe WHAT the stage did?
#   events_observed    how many candidates/events did we actually see there?
#   row_attribution    can we causally attribute shyness to a specific row?
#
# A scan summary is real evidence: Layer-1 aggregates make a stage's OUTCOME
# observable even with zero candidate traces. They never grant row attribution.

_STAGE_UNIVERSE = "UNIVERSE_ADMISSION"
_STAGE_DATA = "MARKET_DATA_ENRICHMENT"
_STAGE_PREFILTER = "PREFILTER_SCORE_VETO"
_STAGE_CAP = "CANDIDATE_CAP_TOP_N"
_STAGE_CLAUDE = "CLAUDE_ANALYSIS"
_STAGE_DEDUP = "DEDUP_AND_COOLDOWN"

_ANALYSIS_FAILURE_KINDS = {"analysis_failed", "rate_limited", "tiering_failed"}

ATTR_NOT_DETERMINABLE = "NOT_DETERMINABLE"
ATTR_PARTIAL = "PARTIAL"
ATTR_OBSERVABLE = "OBSERVABLE"

# Telemetry-backed stages whose traces carry row-level causal shyness truth.
ROW_ATTRIBUTABLE_TELEMETRY_STAGES = {"DEDUP_AND_COOLDOWN"}

_ATTR_REASON_NOT_PERSISTED = "stage not persisted for this window"
_ATTR_REASON_OUTCOME_ONLY = (
    "stage outcome observed; candidate-level shyness not determinable "
    "(no market judgment exists for the candidates at this stage)"
)
_ATTR_REASON_ROW_LEVEL = "row-level decision traces attribute shyness at this stage"
# Phase 14V.2 — Stage-10 provenance wording. Stored evidence is stored;
# reconstructed evidence is reconstructed. The two must never share a
# description, and legacy history is never retroactively upgraded.
_LADDER_NOTE_LEGACY = (
    "snipe_ladder was NOT persisted for these rows; the ladder is reconstructed "
    "read-only from each row's own evidence (RECONSTRUCTED_NOT_PROVEN)."
)
_LADDER_NOTE_TELEMETRY = (
    "Phase 14V persists the scan-time snipe_ladder, so Stage 10 uses STORED_SCAN_TIME "
    "evidence and a ladder cap is causally attributable."
)
_LADDER_NOTE_MIXED = (
    "Mixed provenance: telemetry-backed rows carry the stored scan-time ladder "
    "(STORED_SCAN_TIME); legacy rows have no persisted ladder and are reconstructed "
    "read-only (RECONSTRUCTED_NOT_PROVEN). The two are never merged."
)

_ATTR_REASON_NOT_REACHED = (
    "no candidate reached this stage in the telemetry window; the stage did "
    "not execute, so there is nothing to attribute (this is not a zero)"
)
_ATTR_REASON_HISTORY = "classified from persisted alert_history rows"


def _telemetry_window(telemetry, limit) -> dict:
    """The telemetry actually in scope for this report.

    Deterministic and explicit: the most recent `limit` scan summaries, plus
    ONLY the traces belonging to those scans. An older retained scan cannot
    make the current window's stages look observed.
    """
    empty = {"summaries": [], "traces": {},
             "meta": {"scans_available": 0, "scans_in_window": 0,
                      "traces_in_window": 0, "limit": limit}}
    if not isinstance(telemetry, dict):
        return empty
    all_summaries = [s for s in (telemetry.get("scan_summaries") or [])
                     if isinstance(s, dict)]
    n = max(0, int(limit))
    summaries = all_summaries[-n:] if n else []
    ids = {str(s["scan_id"]) for s in summaries if s.get("scan_id")}
    traces = {}
    for t in telemetry.get("decision_traces") or []:
        if not isinstance(t, dict):
            continue
        sid, tkr = t.get("scan_id"), t.get("ticker")
        if sid and tkr and str(sid) in ids:
            traces[(str(sid), str(tkr))] = t
    return {"summaries": summaries, "traces": traces,
            "meta": {"scans_available": len(all_summaries),
                     "scans_in_window": len(summaries),
                     "traces_in_window": len(traces), "limit": limit}}


def _empty_stage_evidence() -> dict:
    return {sid: {"evidence_available": False, "stage_reached": None,
                  "events_observed": None, "aggregate_source": "none",
                  "trace_rows_observed": 0, "row_attribution": False}
            for sid in TELEMETRY_BACKED_STAGES}


def build_stage_evidence(summaries, traces) -> dict:
    """Per-stage evidence, earned only from evidence belonging to THAT stage.

    Phase 14V.1C keeps three concepts apart:
      evidence_available  we have something that describes this stage
      stage_reached       candidates/events actually occurred here
      row_attribution     a specific row's shyness is causally attributable

    A field existing in the schema is NOT proof the stage executed:
    `build_scan_summary` always emits the suppression block, so an empty
    `check_alert_reason_counts` means nobody reached check_alert — not that
    zero suppressions were observed over reached decisions.

    Layer 1 and Layer 2 are two VIEWS of one pipeline, never two populations.
    Layer 1 owns the aggregate event count; Layer 2 owns candidate identity,
    trace coverage and row-level attribution. They are never summed.
    """
    ev = _empty_stage_evidence()

    def _agg(stage, n):
        """Layer-1 aggregate — authoritative for events_observed."""
        ev[stage]["evidence_available"] = True
        if n is None:
            return
        try:
            n = int(n)
        except (TypeError, ValueError):
            return
        prev = ev[stage]["events_observed"]
        ev[stage]["events_observed"] = n if prev is None else prev + n
        ev[stage]["aggregate_source"] = "scan_summary"
        ev[stage]["stage_reached"] = bool(ev[stage]["events_observed"])

    def _trace(stage, n=1):
        """Layer-2 coverage — never added to the Layer-1 aggregate."""
        ev[stage]["evidence_available"] = True
        ev[stage]["trace_rows_observed"] += n

    # ---- Layer 1: scan-level aggregates ---------------------------------
    for s in summaries or []:
        if not isinstance(s, dict):
            continue
        u = s.get("universe") if isinstance(s.get("universe"), dict) else {}
        if u.get("input_count") is not None:
            _agg(_STAGE_UNIVERSE, _num(u.get("input_count")))
        if u.get("data_stage_success") is not None or u.get("data_stage_failure") is not None:
            _agg(_STAGE_DATA, (_num(u.get("data_stage_success")) or 0)
                 + (_num(u.get("data_stage_failure")) or 0))
        p = s.get("prefilter") if isinstance(s.get("prefilter"), dict) else {}
        if p.get("rejected_count") is not None or p.get("primary_rejection_reason_counts"):
            _agg(_STAGE_PREFILTER, _num(p.get("rejected_count")) or 0)
        if p.get("admitted_count") is not None or p.get("candidate_cap") is not None:
            # Stage 4 counts ADMITTED candidates. Near-cut candidates are the
            # other side of the boundary and are counted separately below.
            _agg(_STAGE_CAP, _num(p.get("admitted_count")) or 0)
        a = s.get("analysis") if isinstance(s.get("analysis"), dict) else {}
        if a:
            _agg(_STAGE_CLAUDE, _num(a.get("admitted")) or 0)
        sup = s.get("suppression") if isinstance(s.get("suppression"), dict) else {}
        if isinstance(sup.get("check_alert_reason_counts"), dict):
            # Evidence exists either way; reachability comes from the COUNT.
            _agg(_STAGE_DEDUP, sum(_num(v) or 0
                                   for v in sup["check_alert_reason_counts"].values()))

    # ---- Layer 2: each trace backs its OWN stage only --------------------
    near_cut = 0
    for t in (traces or {}).values():
        if not isinstance(t, dict):
            continue
        kind = t.get("trace_kind")
        if kind == "near_cut":
            _trace(_STAGE_CAP)
            near_cut += 1
        elif kind in _ANALYSIS_FAILURE_KINDS:
            _trace(_STAGE_CLAUDE)
        elif kind == "analyzed":
            _trace(_STAGE_CLAUDE)
            sup = t.get("suppression") if isinstance(t.get("suppression"), dict) else {}
            # Only a candidate that actually REACHED check_alert is Stage-12
            # evidence, and only that grants row-level attribution.
            if sup.get("check_alert_reason") is not None:
                _trace(_STAGE_DEDUP)
                ev[_STAGE_DEDUP]["row_attribution"] = True

    # Near-cut candidates are a distinct population from admitted candidates.
    ev[_STAGE_CAP]["near_cut_candidates_observed"] = near_cut or None

    # Layer-2 fallback: only when no Layer-1 aggregate existed for the stage.
    for sid, e in ev.items():
        if e["events_observed"] is None and e["trace_rows_observed"]:
            e["events_observed"] = e["trace_rows_observed"]
            e["aggregate_source"] = "decision_traces"
            e["stage_reached"] = True
        elif e["events_observed"] is not None and e["stage_reached"] is None:
            e["stage_reached"] = bool(e["events_observed"])
    return ev


def _telemetry_scan_ids(telemetry) -> set:
    """scan_ids for which Phase 14V actually recorded a funnel summary."""
    out = set()
    if not isinstance(telemetry, dict):
        return out
    for s in telemetry.get("scan_summaries") or []:
        if isinstance(s, dict) and s.get("scan_id"):
            out.add(str(s["scan_id"]))
    return out


def telemetry_traces_by_scan(telemetry) -> dict:
    """Layer-2 decision traces indexed by (scan_id, ticker).

    Phase 14V.1: the audit must actually CONSUME decision traces, not merely
    count summaries. near_cut / analysis_failed / rate_limited / tiering_failed
    are kept distinct — a near-cut row is not an analyzed trade, and an
    analysis failure is not a market judgment.
    """
    out = {}
    if not isinstance(telemetry, dict):
        return out
    for t in telemetry.get("decision_traces") or []:
        if not isinstance(t, dict):
            continue
        sid, tkr = t.get("scan_id"), t.get("ticker")
        if sid and tkr:
            out[(str(sid), str(tkr))] = t
    return out


def _telemetry_scan_count(telemetry) -> int:
    """Retained for compatibility: number of 14V scan summaries available."""
    return len(_telemetry_scan_ids(telemetry))


_TELEMETRY_FACT_KEYS = ("trace_kind", "snipe_ladder", "ladder_source", "judgment",
                        "suppression", "delivery", "pipeline")


def _attach_telemetry_facts(trace) -> dict:
    """Whitelisted scan-time facts attached to an existing alert_history row.
    The persisted row remains the classification source — this only adds
    provenance, so a sent alert is never counted twice."""
    return {k: trace.get(k) for k in _TELEMETRY_FACT_KEYS if k in trace}


def _telemetry_only_row(trace) -> dict:
    """A judged candidate that alert_history can never contain."""
    j = trace.get("judgment") if isinstance(trace.get("judgment"), dict) else {}
    sup = trace.get("suppression") if isinstance(trace.get("suppression"), dict) else {}
    dlv = trace.get("delivery") if isinstance(trace.get("delivery"), dict) else {}
    tier = _s(j.get("final_tier")) or "UNKNOWN"
    ladder = trace.get("snipe_ladder") if isinstance(trace.get("snipe_ladder"), dict) else {}

    classes = []
    if sup.get("cooldown_suppressed") is True:
        classes.append(COOLDOWN_SUPPRESSED)
    elif _s(dlv.get("state")) == "SKIPPED" and dlv.get("skipped_reason"):
        classes.append(ROUTING_SUPPRESSED if "channel" in str(dlv.get("skipped_reason"))
                       else CORRECTLY_WAITING_FOR_PROOF)
    primary = classes[0] if classes else None
    return {
        "ticker": trace.get("ticker"), "scan_id": trace.get("scan_id"),
        "alerted_at": None, "tier": tier,
        "capital_action": j.get("capital_action"), "score": j.get("score"),
        "ceiling_tier": tier, "floor_tier": tier,
        "ladder_tier": ladder.get("internal_ladder_tier"),
        "ladder_source": trace.get("ladder_source"),
        "ladder_attribution": (ATTRIBUTION_STORED
                               if trace.get("ladder_source") == "stored_scan_time"
                               else ATTRIBUTION_RECONSTRUCTED),
        "sniper_grade": ladder.get("sniper_grade"),
        "starter_grade": ladder.get("starter_grade"),
        "seal_applied": None, "promotion_state": None,
        "primary_class": primary,
        "stage": CLASS_STAGE.get(primary) if primary else None,
        "classes": classes,
        # Phase 14V.2: the SAME predicate as every other row path. A benign
        # telemetry-only row is evidence, not shyness.
        "is_shy": is_shy_class(primary),
        "ceiling_vs_served": "AT_CEILING",
        "recompute_confidence": HIGH_CONFIDENCE, "recompute_gaps": [],
        "blocking_codes": [], "soft_cap_codes": [],
        "telemetry_backed": True, "telemetry_only": True,
        "telemetry": _attach_telemetry_facts(trace),
        "why": ("telemetry-only row: judged at scan time but never written to "
                "alert_history (delivery state "
                f"{dlv.get('state')}, check_alert {sup.get('check_alert_reason')})."),
    }


def _telemetry_only_rows(traces, seen_keys) -> tuple:
    """Judged telemetry rows absent from history, plus Stage-5 outcome counts.
    Analysis failures never become market judgments."""
    rows, outcomes = [], {}
    for key, t in (traces or {}).items():
        kind = t.get("trace_kind")
        if kind != "analyzed":
            if kind:
                outcomes[str(kind)] = outcomes.get(str(kind), 0) + 1
            continue
        if key in seen_keys:
            continue                       # already in alert_history — no double count
        rows.append(_telemetry_only_row(t))
    return rows, outcomes


def _stage_rows(stage_counts, telemetry_scans=0, backed_rows=0, legacy_rows=0,
                stage_evidence=None) -> list:
    """Per-stage observability, gated on ACTUAL row/scan intersection.

    Phase 14V.1 (H3): a stage is upgraded only when at least one row IN THIS
    WINDOW came from a scan that recorded telemetry. An unrelated telemetry
    scan can no longer upgrade 300 legacy rows. A mixed window is reported as
    PARTIAL, never OBSERVABLE, and the row carries the exact split. With no
    telemetry-backed rows the output is byte-identical to legacy behavior:
    null counts, never zero.
    """
    stage_evidence = stage_evidence if isinstance(stage_evidence, dict) else {}
    mixed = bool(backed_rows and legacy_rows)
    rows = []
    for s in STAGES:
        observability = s["observability"]
        note = s["note"]
        # Per-stage evidence — never a global "some telemetry exists" flag.
        ev = stage_evidence.get(s["id"]) or {}
        telemetry_backed = bool(s["id"] in TELEMETRY_BACKED_STAGES
                                and ev.get("evidence_available"))
        if s["id"] == "LADDER_ARBITRATION":
            note = (_LADDER_NOTE_MIXED if (backed_rows and legacy_rows)
                    else _LADDER_NOTE_TELEMETRY if backed_rows
                    else _LADDER_NOTE_LEGACY)
        stage_reached = ev.get("stage_reached")
        if telemetry_backed:
            observability = PARTIAL if mixed else OBSERVABLE
            note = (f"{note} Phase 14V telemetry observes this stage for "
                    f"{backed_rows} telemetry-backed row(s) in this window; "
                    f"{legacy_rows} legacy row(s) remain unobservable.")

        # Attribution is a SEPARATE question from outcome visibility, and it
        # requires row-level evidence for THIS stage — an aggregate summary
        # proves an outcome, never causation for a specific candidate.
        if (telemetry_backed and s["id"] in ROW_ATTRIBUTABLE_TELEMETRY_STAGES
                and ev.get("row_attribution") and stage_reached):
            attribution = ATTR_PARTIAL if mixed else ATTR_OBSERVABLE
            attribution_reason = _ATTR_REASON_ROW_LEVEL + (
                " for the telemetry-backed portion only; legacy rows are not "
                "covered by this count." if mixed else "")
        elif telemetry_backed and stage_reached is False:
            # Evidence exists and says NOBODY reached this stage. That is not
            # an observed outcome over reached decisions, and never a zero.
            attribution = ATTR_NOT_DETERMINABLE
            attribution_reason = _ATTR_REASON_NOT_REACHED
        elif telemetry_backed:
            attribution = ATTR_NOT_DETERMINABLE
            attribution_reason = _ATTR_REASON_OUTCOME_ONLY
        elif s["observability"] == NOT_PERSISTED:
            attribution = ATTR_NOT_DETERMINABLE
            attribution_reason = _ATTR_REASON_NOT_PERSISTED
        else:
            # Stages 6-11 and 13 were always classified from alert_history.
            attribution = (ATTR_PARTIAL if s["observability"] == PARTIAL
                           else ATTR_OBSERVABLE)
            attribution_reason = _ATTR_REASON_HISTORY
        rows.append({
            "n": s["n"], "stage": s["id"], "scheduler_step": s["scheduler_step"],
            "observability": observability, "note": note,
            "telemetry_backed": telemetry_backed,
            "telemetry_backed_rows": backed_rows if s["id"] in TELEMETRY_BACKED_STAGES else None,
            "legacy_rows": legacy_rows if s["id"] in TELEMETRY_BACKED_STAGES else None,
            "shyness_attribution": attribution,
            "attribution_reason": attribution_reason,
            # Three distinct counts, never interchangeable.
            "stage_reached": stage_reached,
            "events_observed": ev.get("events_observed"),
            "aggregate_source": ev.get("aggregate_source"),
            "trace_rows_observed": ev.get("trace_rows_observed"),
            "near_cut_candidates_observed": ev.get("near_cut_candidates_observed"),
            # Numeric ONLY when shyness is genuinely attributable at this
            # stage. An observed zero is a real zero and is preserved as 0;
            # an unattributable stage stays None and says why.
            "shy_rows_attributed": (
                stage_counts.get(s["id"], 0)
                if attribution != ATTR_NOT_DETERMINABLE else None
            ),
        })
    return rows


_BLIND_SPOT_STAGE = {
    PREFILTER_REJECTED: _STAGE_PREFILTER,
    NOT_IN_TOP_30: _STAGE_CAP,
    CLAUDE_NOT_ANALYZED: _STAGE_CLAUDE,
    DEDUP_SUPPRESSED: _STAGE_DEDUP,
    COOLDOWN_SUPPRESSED: _STAGE_DEDUP,
    ROUTING_SUPPRESSED: "ROUTING_AND_ALERT_WORDING",
}


def _blind_spots(config=None, stage_evidence=None) -> list:
    cap = _d(config or {}, "prefilter").get("max_claude_candidates_per_scan")
    cap_txt = f"top {cap}" if cap else "the candidate cap"
    observed = _observed_stages(stage_evidence)
    out = [
        {"cls": PREFILTER_REJECTED,
         "reason": "Prefilter-rejected tickers are never written to alert_history."},
        {"cls": NOT_IN_TOP_30,
         "reason": f"Tickers ranked outside {cap_txt} are never written to alert_history."},
        {"cls": CLAUDE_NOT_ANALYZED,
         "reason": "Claude cap/error/rate-limit outcomes are scan-summary counters only."},
        {"cls": DEDUP_SUPPRESSED,
         "reason": "record_alert runs only when send_alert reports sent=True; deduped rows are never recorded."},
        {"cls": COOLDOWN_SUPPRESSED,
         "reason": "Cooldown suppression takes the same unrecorded path as dedup."},
        {"cls": ROUTING_SUPPRESSED,
         "reason": "final_discord_channel='none' and final_tier='WAIT' rows are never recorded."},
    ]
    if not observed:
        return out
    # Phase 14V.1C: a class whose stage the current telemetry window actually
    # records is no longer globally blind. Say so instead of repeating a
    # legacy claim the ledger has already disproved.
    scoped = []
    for item in out:
        stage = _BLIND_SPOT_STAGE.get(item["cls"])
        if stage in observed:
            scoped.append({
                "cls": item["cls"],
                "reason": ("LEGACY ROWS ONLY — Phase 14V telemetry records this "
                           "stage for the scans in the current window. " + item["reason"]),
                "legacy_only": True,
            })
        else:
            scoped.append({**item, "legacy_only": False})
    return scoped


def _has_telemetry(stage_evidence) -> bool:
    return any((e or {}).get("evidence_available")
               for e in (stage_evidence or {}).values())


def _observed_stages(stage_evidence) -> set:
    return {sid for sid, e in (stage_evidence or {}).items()
            if (e or {}).get("evidence_available")}


def _persistence_gaps(stage_evidence=None) -> list:
    """Fields the recompute needs. Phase 14V closed all three PROSPECTIVELY:
    record_alert now persists snipe_ladder, invalidation_condition, and
    candle_evidence. The gaps below are therefore HISTORICAL — they describe
    legacy rows only, and are stated that way once telemetry-backed rows
    exist. Historical gaps stay historical; prospective gaps are closed."""
    scope = ("LEGACY ROWS ONLY — closed prospectively by Phase 14V: "
             if _has_telemetry(stage_evidence) else "")
    return [
        {"field": "final_signal.invalidation_condition",
         "effect": scope + "The ladder derives inval_clear from the condition text or "
                   "one_hour_entry.invalidation.clear. Rows carrying neither "
                   "recompute as a false 'invalidation missing or unclear' hard "
                   "failure; this audit marks them UNCLASSIFIED instead."},
        {"field": "snipe_ladder",
         "effect": scope + "For a legacy row stage 10 is a recompute, so a "
                   "served tier can legitimately sit ABOVE the recomputed ceiling. "
                   "It also means a below-ceiling row cannot be causally attributed "
                   "to a ladder cap: such rows are reported as POSSIBLE_*_UNDERCALL "
                   "(evidence for review), never as a proven LADDER_CAPPED event."},
        {"field": "candle_evidence",
         "effect": scope + "Open-bar/candle-veto truth seen at scan time is not replayable."},
    ]


def _observability_note(stage_evidence=None, backed_rows=0, legacy_rows=0,
                        legacy_outside=0) -> str:
    observed = _observed_stages(stage_evidence)
    if observed:
        return (
            f"TELEMETRY IN SCOPE. Phase 14V scan-level telemetry is loaded and is "
            f"driving {len(observed)} funnel stage(s) directly "
            f"({', '.join(sorted(observed))}). Counts for those stages describe the "
            f"TELEMETRY SCAN population, not the legacy alert rows. "
            f"{backed_rows} row(s) in this report are telemetry-backed; "
            f"{legacy_rows} are legacy, of which {legacy_outside} fall outside the "
            f"telemetry scan window entirely and keep historical-only semantics: "
            f"alert_history holds SENT ALERTS ONLY, their ladder is a recompute, and "
            f"their unobserved stages report null — never zero. A stage with evidence "
            f"showing no candidate reached it is reported as NOT REACHED, which is "
            f"also not a zero. Historical truth is never retroactively upgraded."
        )
    if backed_rows:
        return (
            f"MIXED WINDOW: {backed_rows} row(s) are Phase 14V telemetry-backed and "
            f"{legacy_rows} are legacy. For telemetry-backed scans the funnel stages "
            "14V records are observed directly and the scan-time snipe_ladder is "
            "stored, so stage 10 is causally attributable. Legacy rows keep their "
            "original limits: alert_history holds SENT ALERTS ONLY, their ladder is "
            "a recompute, and their unobserved stages report null — never zero. "
            "Historical truth is never retroactively upgraded."
        )
    return (
        "Persisted alert_history contains SENT ALERTS ONLY (state_store.record_alert "
        "is called from scheduler Step 8 only when send_alert returns sent=True), and "
        "the state file carries no scan-level ledger. Stages 1-5 and 12 of this funnel "
        "are therefore NOT determinable from current persisted history, and stages 10 "
        "and 13 are only partially determinable (the Phase 14S ladder is not persisted "
        "and is recomputed here; routing is visible only for rows that were sent). "
        "Counts for those stages are reported as null, never as zero."
    )


def _next_probes(stage_evidence=None) -> list:
    if _has_telemetry(stage_evidence):
        return [
            "Phase 14V telemetry is live: the scan funnel, the scan-time ladder, "
            "invalidation_condition and candle_evidence are now persisted for new "
            "scans. Remaining work is historical only — legacy rows can never be "
            "back-filled.",
            "Measure how often check_alert evaluates a pre-ladder tier that later "
            "differs from the served tier (check_alert_evaluated_tier vs final_tier). "
            "That ordering is recorded, not changed, by Phase 14V.",
            "Measure basket progression inside one public tier (STARTER_B->STARTER_A, "
            "SNIPER_A->SNIPER_A_PLUS), which dedup remains blind to.",
        ]
    return [
        "Persist a per-scan funnel ledger (input -> prefilter pass -> capped candidates -> "
        "claude analyzed -> tier counts -> suppressed) so stages 1-5 and 12 become observable.",
        "Persist the Phase 14S snipe_ladder object on each recorded row so stage 10 stops "
        "depending on a recompute.",
        "Persist final_signal.invalidation_condition so a recomputed ladder can confirm "
        "invalidation clarity instead of reporting a false hard failure.",
        "Record a compact row for suppressed/WAIT decisions (tier, reason, dedup reason) so "
        "DEDUP_SUPPRESSED / COOLDOWN_SUPPRESSED / ROUTING_SUPPRESSED stop being blind.",
    ]


# ---------------------------------------------------------------------------
# Sanitized JSON view (whitelist only — never raw state, never secrets)
# ---------------------------------------------------------------------------

_EXAMPLE_JSON_KEYS = (
    "ticker", "scan_id", "alerted_at", "tier", "capital_action", "score",
    "ceiling_tier", "floor_tier", "ladder_tier", "ladder_source",
    "ladder_attribution",
    "sniper_grade", "starter_grade", "seal_applied", "promotion_state",
    "primary_class", "stage", "classes", "is_shy", "ceiling_vs_served",
    "recompute_confidence", "recompute_gaps", "blocking_codes",
    "soft_cap_codes", "why",
)


def shyness_json(report) -> dict:
    """Sanitized, JSON-safe projection of a funnel report.

    Whitelist only: never emits raw state, config, tokens, channel IDs, or any
    field not explicitly listed above.
    """
    if not isinstance(report, dict):
        return {"error": "invalid_report"}
    return {
        "error": report.get("error"),
        "source": report.get("source"),
        "total_rows": report.get("total_rows", 0),
        "shy_rows": report.get("shy_rows", 0),
        "no_finding_rows": report.get("no_finding_rows", 0),
        "telemetry_scans": report.get("telemetry_scans", 0),
        "scope": report.get("scope"),
        "telemetry_window": dict(report.get("telemetry_window") or {}),
        "legacy_alert_window": dict(report.get("legacy_alert_window") or {}),
        "stage_evidence": {
            k: {kk: vv for kk, vv in (v or {}).items()
                if kk in ("evidence_available", "stage_reached", "events_observed",
                          "aggregate_source", "trace_rows_observed",
                          "near_cut_candidates_observed", "row_attribution")}
            for k, v in (report.get("stage_evidence") or {}).items()
        },
        "telemetry_backed_rows": report.get("telemetry_backed_rows", 0),
        "legacy_rows": report.get("legacy_rows", 0),
        "telemetry_analysis_outcomes": dict(report.get("telemetry_analysis_outcomes") or {}),
        "low_confidence_rows": report.get("low_confidence_rows", 0),
        "above_recomputed_ceiling_rows": report.get("above_recomputed_ceiling_rows", 0),
        "newest": report.get("newest"),
        "oldest": report.get("oldest"),
        "tier_counts": dict(report.get("tier_counts") or {}),
        "class_counts": dict(report.get("class_counts") or {}),
        "stage_counts": dict(report.get("stage_counts") or {}),
        "stages": [dict(s) for s in (report.get("stages") or [])],
        "top_shyness_stages": [dict(s) for s in (report.get("top_shyness_stages") or [])],
        "blind_spots": [dict(b) for b in (report.get("blind_spots") or [])],
        "persistence_gaps": [dict(g) for g in (report.get("persistence_gaps") or [])],
        "observability_note": report.get("observability_note"),
        "recommended_next_probes": list(report.get("recommended_next_probes") or []),
        "examples": [
            {k: ex.get(k) for k in _EXAMPLE_JSON_KEYS}
            for ex in (report.get("examples") or []) if isinstance(ex, dict)
        ],
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def _obs_mark(observability) -> str:
    return {OBSERVABLE: "visible", PARTIAL: "partial", NOT_PERSISTED: "BLIND"}.get(
        observability, "?")


def render_shyness_funnel_audit(report) -> str:
    """Operator-facing text. Never raises."""
    try:
        return _render(report)
    except Exception as exc:  # pragma: no cover - defensive
        return f"SHYNESS FUNNEL AUDIT unavailable — render error: {type(exc).__name__}: {exc}"


def _render(report) -> str:
    if not isinstance(report, dict):
        return "SHYNESS FUNNEL AUDIT unavailable — invalid report."
    if report.get("error"):
        return (f"**SNIPE / STARTER SHYNESS FUNNEL AUDIT**\n"
                f"Unavailable — {report['error']}\nNo state was modified.")

    lines = [
        "**SNIPE / STARTER SHYNESS FUNNEL AUDIT (Phase 14U)**",
        f"Source: {report.get('source')}   Rows analyzed: {report.get('total_rows', 0)}"
        f"   Shy rows: {report.get('shy_rows', 0)}",
        f"No finding: {report.get('no_finding_rows', 0)}"
        f"   Not determinable: {report.get('low_confidence_rows', 0)}"
        f"   Served above recomputed ceiling: {report.get('above_recomputed_ceiling_rows', 0)}",
        f"Window: {report.get('oldest') or '—'} -> {report.get('newest') or '—'}",
        "Read-only diagnostic. No tier, capital, routing, threshold, or gate was changed.",
        "",
        "__TIER DISTRIBUTION__",
    ]
    tiers = report.get("tier_counts") or {}
    lines.append("  " + ("  ".join(f"{k}={v}" for k, v in sorted(tiers.items())) or "—"))

    w = report.get("telemetry_window") or {}
    lw = report.get("legacy_alert_window") or {}
    if w or lw:
        lines += ["", "__AUDIT WINDOW__",
                  f"  Scope: {report.get('scope')}",
                  f"  Telemetry scan window: available={w.get('scans_available', 0)} "
                  f"in_scope={w.get('scans_in_window', 0)} "
                  f"traces={w.get('traces_in_window', 0)}",
                  f"  Legacy alert rows: in_report={lw.get('rows_in_report', 0)} "
                  f"outside_telemetry_window={lw.get('rows_outside_telemetry_window', 0)}"]

    lines += ["", "__FUNNEL (13 stages, scan-pipeline order)__"]
    for s in report.get("stages") or []:
        attributed = s.get("shy_rows_attributed")
        if attributed is not None:
            count = f"{attributed} shy row(s)"
        elif s.get("stage_reached") is False:
            # Evidence says nobody reached this stage. Never "observed zero".
            count = "no candidate reached this stage"
        elif s.get("shyness_attribution") == ATTR_NOT_DETERMINABLE and \
                s.get("observability") != NOT_PERSISTED:
            # The evidence IS persisted — what is missing is the causal claim.
            # Never say "not persisted" about a stage we can actually see.
            count = "outcome observed; shyness not attributable"
        else:
            count = "n/a (not persisted)"
        lines.append(f"  {s['n']:>2}. {s['stage']:<28} [{_obs_mark(s['observability'])}]  {count}")
        lines.append(f"      {s['scheduler_step']} — {s['note']}")
        if s.get("attribution_reason") and attributed is None:
            lines.append(f"      attribution: {s['attribution_reason']}")

    lines += ["", "__SHYNESS CLASS COUNTS__"]
    counts = report.get("class_counts") or {}
    if counts:
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {k:<32} {v}")
    else:
        lines.append("  — no rows classified")

    lines += ["", "__TOP SHYNESS STAGES__"]
    tops = report.get("top_shyness_stages") or []
    if tops:
        for t in tops[:5]:
            lines.append(f"  {t['stage']:<32} {t['count']}")
    else:
        lines.append("  — no observable shyness in this window")

    lines += ["", "__EXAMPLES (closest to a higher tier)__"]
    examples = report.get("examples") or []
    if not examples:
        lines.append("  — none")
    for i, ex in enumerate(examples, 1):
        lines.append(
            f"  {i}. {ex.get('ticker')} `{ex.get('scan_id')}` {ex.get('tier')} "
            f"(ceiling {ex.get('ceiling_tier')} / floor {ex.get('floor_tier')})"
        )
        lines.append(f"     class: {ex.get('primary_class')} @ {ex.get('stage')}")
        lines.append(f"     {ex.get('why')}")
        lines.append(f"     Command: !audit {ex.get('scan_id')}")

    lines += ["", "__BLIND SPOTS (cannot be determined from persisted history)__"]
    for b in report.get("blind_spots") or []:
        lines.append(f"  {b['cls']:<24} {b['reason']}")

    lines += ["", "__PERSISTENCE GAPS (degrade the recompute, not the scanner)__"]
    for g in report.get("persistence_gaps") or []:
        lines.append(f"  {g['field']}")
        lines.append(f"      {g['effect']}")

    lines += ["", "__OBSERVABILITY__", "  " + str(report.get("observability_note") or "")]

    lines += ["", "__RECOMMENDED NEXT PROBES (no code change made by this phase)__"]
    for p in report.get("recommended_next_probes") or []:
        lines.append(f"  - {p}")

    return "\n".join(lines)

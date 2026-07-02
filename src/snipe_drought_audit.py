"""Phase 14R — SNIPE_IT drought root-cause audit (read-only diagnostic).

Answers, from persisted alert_history evidence: WHY is the scanner not
producing SNIPE_IT? It classifies every row with the same Phase 14Q blocker
taxonomy the seal uses, then aggregates:

  - tier distribution
  - blocker frequency table (which gate blocks SNIPE_IT, how often)
  - almost-SNIPE table (the closest candidates and the exact reason each missed)
  - root-cause classification (A..H, see ROOT_CAUSES)
  - impossible-gate diagnostics (a gate missing on nearly every eligible row is
    structurally unsatisfiable at live scan cadence, not a real filter)
  - soft-cap-overblock and seal-overblock diagnostics
  - recommended calibration actions

Doctrine (permanent):
  - READ-ONLY. Never mutates rows, never writes state, never touches tiering,
    routing, capital, dedup, cooldown, or cadence. Pure stdlib. Never raises.
  - It diagnoses; it never promotes. A finding here is evidence for a human
    calibration decision, never an automatic tier change.
  - No ticker is special-cased. Every row is judged by the same taxonomy.

Usage (production):
    from src import snipe_drought_audit as sda
    report = sda.run_snipe_drought_audit(limit=100)      # reads alert_state.json
    print(sda.render_snipe_drought_audit(report))

Usage (tests / offline):
    report = sda.run_snipe_drought_audit(rows=my_rows)
"""

from src import snipe_blocker_taxonomy as tax

ROOT_CAUSES = {
    "A": "No true SNIPE candidates in the data.",
    "B": "Valid candidates correctly blocked by real capital blockers.",
    "C": "Valid candidates incorrectly blocked by soft caps alone.",
    "D": "Valid candidates blocked by SNIPE-only blockers.",
    "E": "Contradictory state: evidence says confirmed but a gate says missing.",
    "F": "Threshold impossibility: a gate cannot be satisfied under live scan cadence.",
    "G": "Seal overreach: seal demoted candidates whose taxonomy floor is SNIPE_IT.",
    "H": "Alert/tier mismatch: final_tier does not reflect audit truth.",
}

# A gate missing/blocked on at least this share of eligible rows is flagged as
# structurally impossible rather than a genuine filter.
_IMPOSSIBLE_GATE_SHARE = 0.80

_FREQ_GATES = (
    "ONE_H_TRIGGER_CONFIRMED", "LIVE_EDGE_SAFE", "CANDLE_TRUTH_SUPPORTIVE",
    "FOUR_H_LOCATION_VALID", "DAILY_PERMISSION_GRANTED", "OVERHEAD_CLEAR",
    "HTF_EXTENDED", "HTF_CONTEXT_GRADE", "SNIPE_SCORE_REALISM",
    "LOCATION_REALISM", "ASYMMETRY_VALID", "INVALIDATION_CLEAR",
    "PATH_CLEAN", "RETEST_CONFIRMED", "HOLD_CONFIRMED",
)


# ---------------------------------------------------------------------------
# Row helpers (defensive; persisted rows may predate any phase)
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


def _gate_names(items) -> list:
    out = []
    for it in items or []:
        if isinstance(it, str) and it:
            out.append(it.split(":", 1)[0].strip())
        elif isinstance(it, dict):
            for k in ("gate", "name", "id", "key"):
                v = it.get(k)
                if isinstance(v, str) and v:
                    out.append(v.strip())
                    break
    return out


def _collect_rows_from_state(state, limit) -> list:
    rows = []
    tickers = state.get("tickers") if isinstance(state, dict) else None
    if isinstance(tickers, dict):
        for tdata in tickers.values():
            hist = tdata.get("alert_history") if isinstance(tdata, dict) else None
            if isinstance(hist, list):
                rows.extend(r for r in hist if isinstance(r, dict))
    rows.sort(key=lambda r: str(r.get("alerted_at") or ""), reverse=True)
    return rows[: max(0, int(limit))]


# ---------------------------------------------------------------------------
# Per-row analysis
# ---------------------------------------------------------------------------

def _analyze_row(row) -> dict:
    sga = _d(row, "snipe_gate_audit")
    seal = _d(row, "snipe_confirmed_seal")
    c = tax.classify_blockers(row)
    cc = c.get("candle_context") or {}

    tier = str(row.get("tier") or row.get("final_tier") or "").upper().strip() or "UNKNOWN"
    raw = _num(sga.get("raw_snipe_score"))
    eff = _num(sga.get("snipe_score"))
    blocked_names = _gate_names(sga.get("blocked_gate_names")) or _gate_names(sga.get("blocked_gates"))
    missing_names = _gate_names(sga.get("missing_proofs"))
    score_capped = (raw is not None and eff is not None and eff < raw) or bool(sga.get("score_blocked_by"))

    capital = c.get("capital_blockers") or []
    snipe_only = c.get("snipe_only_blockers") or []
    soft = c.get("soft_caps") or []
    floor = c.get("recommended_floor")
    seal_applied = seal.get("applied") is True

    # Per-row root cause (for rows that are not SNIPE_IT)
    if tier == "SNIPE_IT":
        cause = None
    elif capital:
        cause = "B"
    elif snipe_only:
        cause = "D"
    elif floor == "SNIPE_IT":
        # Nothing in the current taxonomy blocks SNIPE, yet the tier is lower.
        cause = "G" if seal_applied else "H"
    elif soft:
        cause = "C"
    else:
        cause = "H"

    promo = str(sga.get("promotion_state") or "").upper()
    blocked_promo_unnamed = (
        promo == "PROMOTION_BLOCKED" and not capital and not snipe_only
    )

    if capital:
        blocker_class = "CAPITAL_BLOCKER"
    elif snipe_only:
        blocker_class = "SNIPE_ONLY_BLOCKER"
    elif soft:
        blocker_class = "SOFT_CAP"
    elif (c.get("info_notes") or []):
        blocker_class = "INFO_NOTE"
    else:
        blocker_class = "NONE"

    named = tax.named_blockers(c)
    if named:
        miss_reason = "; ".join(named)
    elif tier != "SNIPE_IT":
        miss_reason = ("taxonomy floor is SNIPE_IT — tier does not reflect audit truth"
                       if floor == "SNIPE_IT" else "no named blocker (hidden-blocker violation)")
    else:
        miss_reason = "—"

    return {
        "ticker": row.get("ticker"),
        "scan_id": row.get("scan_id"),
        "alerted_at": row.get("alerted_at"),
        "tier": tier,
        "score": row.get("score"),
        "raw_snipe_score": raw,
        "snipe_score": eff,
        "snipe_grade": sga.get("snipe_grade"),
        "promotion_state": sga.get("promotion_state"),
        "eligible": sga.get("eligible_for_snipe_review") is True,
        "blocked_gates": blocked_names,
        "missing_proofs": missing_names,
        "score_capped": bool(score_capped),
        "candle_context": cc.get("candle_context"),
        "candle_tier_effect": cc.get("candle_tier_effect"),
        "leader_context": c.get("leader_context"),
        "leader_effect": c.get("leader_effect"),
        "one_h_trigger_state": _d(row, "one_hour_entry").get("trigger_state"),
        "retest_truth": _d(_d(row, "one_hour_entry"), "pullback_retest_hold").get("retest_truth"),
        "hold_truth": _d(_d(row, "one_hour_entry"), "pullback_retest_hold").get("hold_truth"),
        "daily_permission": _d(_d(row, "timeframe_alignment"), "swing_timeframe").get("state"),
        "four_h_location": _d(_d(row, "timeframe_alignment"), "operational_timeframe").get("state"),
        "htf_context": _d(row, "higher_timeframe_context").get("campaign_location_label"),
        "recommended_floor": floor,
        "seal_applied": seal_applied,
        "blocker_class": blocker_class,
        "capital_codes": [b.get("code") for b in capital if isinstance(b, dict)],
        "snipe_only_codes": [b.get("code") for b in snipe_only if isinstance(b, dict)],
        "soft_codes": [b.get("code") for b in soft if isinstance(b, dict)],
        "reason_not_snipe": miss_reason,
        "root_cause": cause,
        "blocked_promo_unnamed": blocked_promo_unnamed,
        "hidden_blocker_violation": bool(c.get("hidden_blocker_violation")),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_snipe_drought_audit(rows=None, state=None, config=None, limit=100) -> dict:
    """Build the drought report. Never raises; returns a degraded report on error."""
    try:
        return _run(rows, state, config, limit)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return {"error": f"snipe_drought_audit_error: {exc}", "total_rows": 0,
                "tier_counts": {}, "blocker_frequency": {}, "almost_snipe": [],
                "root_cause_counts": {}, "primary_root_causes": [],
                "impossible_gates": [], "soft_cap_overblocks": 0,
                "seal_overblocks": 0, "recommended_actions": [],
                "source": "error"}


def _run(rows, state, config, limit) -> dict:
    source = "provided-rows"
    if rows is None:
        if state is None:
            from src import audit_access
            loaded = audit_access.load_state_readonly(config or {})
            state = loaded.get("state") if isinstance(loaded, dict) and loaded.get("ok") else {}
            source = "alert_state.json (read-only)"
        else:
            source = "provided-state"
        rows = _collect_rows_from_state(state or {}, limit)
    else:
        rows = [r for r in rows if isinstance(r, dict)][: max(0, int(limit))]

    analyzed = [_analyze_row(r) for r in rows]
    total = len(analyzed)

    tier_counts: dict = {}
    for a in analyzed:
        tier_counts[a["tier"]] = tier_counts.get(a["tier"], 0) + 1

    eligible = [a for a in analyzed if a["eligible"]]
    non_snipe = [a for a in analyzed if a["tier"] != "SNIPE_IT"]

    def _count(pred, pool):
        return sum(1 for a in pool if pred(a))

    metrics = {
        "total_rows": total,
        "tier_counts": tier_counts,
        "eligible_for_snipe_review": len(eligible),
        "raw_snipe_score_ge_80": _count(lambda a: (a["raw_snipe_score"] or 0) >= 80, analyzed),
        "raw_snipe_score_ge_90": _count(lambda a: (a["raw_snipe_score"] or 0) >= 90, analyzed),
        "raw_snipe_score_ge_95": _count(lambda a: (a["raw_snipe_score"] or 0) >= 95, analyzed),
        "score_capped_down": _count(lambda a: a["score_capped"], analyzed),
        "blank_blocked_gates_not_snipe": _count(lambda a: not a["blocked_gates"], non_snipe),
        "blank_missing_proofs_not_snipe": _count(lambda a: not a["missing_proofs"], non_snipe),
        "promotion_blocked_unnamed": _count(lambda a: a["blocked_promo_unnamed"], analyzed),
        "defensive_rejection_not_snipe": _count(
            lambda a: a["candle_context"] == "DEFENSIVE_REJECTION", non_snipe),
        "leader_hard_failure_overrides": _count(
            lambda a: a["leader_effect"] == "HARD_FAILURE_OVERRIDES", analyzed),
        "only_soft_caps": _count(
            lambda a: a["blocker_class"] in ("SOFT_CAP", "INFO_NOTE", "NONE") and a["soft_codes"],
            non_snipe),
        "only_snipe_only_blockers": _count(
            lambda a: a["blocker_class"] == "SNIPE_ONLY_BLOCKER", non_snipe),
        "capital_blockers_present": _count(
            lambda a: a["blocker_class"] == "CAPITAL_BLOCKER", non_snipe),
    }

    # ---- Blocker frequency table -------------------------------------------
    freq = {g: 0 for g in _FREQ_GATES}
    freq["SEAL_BLOCKER"] = 0
    freq["SCORE_CAP"] = 0
    for a in non_snipe:
        seen = set(a["blocked_gates"]) | set(a["missing_proofs"])
        seen |= set(a["capital_codes"]) | set(a["snipe_only_codes"]) | set(a["soft_codes"])
        for g in _FREQ_GATES:
            if g in seen:
                freq[g] += 1
        if a["seal_applied"]:
            freq["SEAL_BLOCKER"] += 1
        if a["score_capped"]:
            freq["SCORE_CAP"] += 1
    # Candle-context codes get their own rows.
    for code in ("CANDLE_CONTEXT_UNRESOLVED", "CANDLE_HOSTILE_REJECTION",
                 "CANDLE_EXPANSION_REJECTION", "CANDLE_CONTEXT_UNKNOWN"):
        freq[code] = sum(
            1 for a in non_snipe
            if code in a["capital_codes"] + a["snipe_only_codes"] + a["soft_codes"]
        )

    # ---- Root-cause classification -----------------------------------------
    cause_counts: dict = {}
    for a in non_snipe:
        if a["root_cause"]:
            cause_counts[a["root_cause"]] = cause_counts.get(a["root_cause"], 0) + 1
    if total and not eligible:
        cause_counts["A"] = cause_counts.get("A", 0) + 1

    # Impossible gates (structural, root cause F): a gate missing/blocked on
    # >= _IMPOSSIBLE_GATE_SHARE of eligible non-SNIPE rows.
    impossible = []
    pool = [a for a in non_snipe if a["eligible"]] or non_snipe
    if pool:
        for g in _FREQ_GATES:
            share = sum(
                1 for a in pool if g in set(a["blocked_gates"]) | set(a["missing_proofs"])
            ) / len(pool)
            if share >= _IMPOSSIBLE_GATE_SHARE:
                impossible.append({"gate": g, "share": round(share, 3)})
    if impossible:
        cause_counts["F"] = cause_counts.get("F", 0) + len(impossible)

    soft_overblocks = [a for a in non_snipe if a["root_cause"] == "C"]
    seal_overblocks = [a for a in non_snipe if a["root_cause"] == "G"]

    # ---- Almost-SNIPE table (closest first: effective score, then raw) ------
    almost = sorted(
        (a for a in non_snipe if a["eligible"] or (a["raw_snipe_score"] or 0) >= 80),
        key=lambda a: ((a["snipe_score"] or 0), (a["raw_snipe_score"] or 0)),
        reverse=True,
    )[:10]

    # ---- Recommended actions -------------------------------------------------
    actions = []
    for ig in impossible:
        actions.append(
            f"Gate {ig['gate']} is missing/blocked on {ig['share']:.0%} of eligible rows — "
            "structurally unsatisfiable at live scan cadence; recalibrate the gate "
            "or stop letting its absence block full size (root cause F)."
        )
    if soft_overblocks:
        actions.append(
            f"{len(soft_overblocks)} row(s) blocked with only soft caps/info notes — "
            "soft caps must grade, not bury (root cause C)."
        )
    if seal_overblocks:
        actions.append(
            f"{len(seal_overblocks)} sealed row(s) whose current taxonomy floor is SNIPE_IT — "
            "seal overreach relative to current doctrine (root cause G); "
            "these were sealed under older rules or a taxonomy gap."
        )
    if metrics["promotion_blocked_unnamed"]:
        actions.append(
            f"{metrics['promotion_blocked_unnamed']} PROMOTION_BLOCKED row(s) without a named "
            "CAPITAL/SNIPE-only blocker — hidden-blocker violation; fix disclosure."
        )
    if metrics["defensive_rejection_not_snipe"]:
        actions.append(
            f"{metrics['defensive_rejection_not_snipe']} row(s) with DEFENSIVE_REJECTION not SNIPE_IT — "
            "verify a real capital/SNIPE-only blocker exists on each; a defensive "
            "rejection alone must not bury the sequence."
        )
    if total and not eligible:
        actions.append("No eligible SNIPE-review candidates in the window (root cause A) — "
                       "the drought starts upstream of the gates; inspect scan inputs.")
    if not actions:
        actions.append("No structural overblock detected in this window — blocks look genuine (root cause B).")

    primary = sorted(cause_counts.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "source": source,
        "total_rows": total,
        "tier_counts": tier_counts,
        "metrics": metrics,
        "blocker_frequency": freq,
        "almost_snipe": almost,
        "root_cause_counts": cause_counts,
        "primary_root_causes": [
            {"code": code, "count": n, "meaning": ROOT_CAUSES.get(code, "?")}
            for code, n in primary
        ],
        "impossible_gates": impossible,
        "soft_cap_overblocks": len(soft_overblocks),
        "seal_overblocks": len(seal_overblocks),
        "recommended_actions": actions,
    }


# ---------------------------------------------------------------------------
# Text rendering (operator-readable; used by tests and any future command)
# ---------------------------------------------------------------------------

def render_snipe_drought_audit(report) -> str:
    if not isinstance(report, dict):
        return "SNIPE_IT DROUGHT AUDIT: no report"
    lines = [
        "__SNIPE_IT DROUGHT AUDIT__",
        f"Source: {report.get('source')}",
        f"Rows analyzed: {report.get('total_rows')}",
        "",
        "__TIER DISTRIBUTION__",
    ]
    for tier, n in sorted((report.get("tier_counts") or {}).items()):
        lines.append(f"  {tier}: {n}")
    m = report.get("metrics") or {}
    lines += [
        "",
        "__ELIGIBILITY / SCORES__",
        f"  Eligible for SNIPE review: {m.get('eligible_for_snipe_review')}",
        f"  raw_snipe_score >= 80: {m.get('raw_snipe_score_ge_80')}",
        f"  raw_snipe_score >= 90: {m.get('raw_snipe_score_ge_90')}",
        f"  raw_snipe_score >= 95: {m.get('raw_snipe_score_ge_95')}",
        f"  Score capped down: {m.get('score_capped_down')}",
        f"  Blank blocked_gates (not SNIPE): {m.get('blank_blocked_gates_not_snipe')}",
        f"  Blank missing_proofs (not SNIPE): {m.get('blank_missing_proofs_not_snipe')}",
        f"  PROMOTION_BLOCKED unnamed: {m.get('promotion_blocked_unnamed')}",
        f"  DEFENSIVE_REJECTION not SNIPE: {m.get('defensive_rejection_not_snipe')}",
        f"  Leader hard-failure overrides: {m.get('leader_hard_failure_overrides')}",
        f"  Only soft caps: {m.get('only_soft_caps')}",
        f"  Only SNIPE-only blockers: {m.get('only_snipe_only_blockers')}",
        f"  Capital blockers present: {m.get('capital_blockers_present')}",
        "",
        "__BLOCKER FREQUENCY__",
    ]
    for gate, n in sorted((report.get("blocker_frequency") or {}).items(),
                          key=lambda kv: kv[1], reverse=True):
        if n:
            lines.append(f"  {gate}: {n}")
    lines += ["", "__ALMOST-SNIPE (top 10)__"]
    for a in report.get("almost_snipe") or []:
        lines.append(
            f"  {a.get('ticker')} {a.get('scan_id')} {a.get('alerted_at')} "
            f"tier={a.get('tier')} score={a.get('score')} snipe={a.get('snipe_score')} "
            f"({a.get('snipe_grade')}) promo={a.get('promotion_state')} "
            f"candle={a.get('candle_context')} leader={a.get('leader_context')} "
            f"class={a.get('blocker_class')}"
        )
        lines.append(f"    reason: {a.get('reason_not_snipe')}")
    lines += ["", "__ROOT CAUSE__"]
    for rc in report.get("primary_root_causes") or []:
        lines.append(f"  {rc['code']} x{rc['count']}: {rc['meaning']}")
    for ig in report.get("impossible_gates") or []:
        lines.append(f"  IMPOSSIBLE GATE: {ig['gate']} missing on {ig['share']:.0%} of eligible rows")
    lines += ["", "__RECOMMENDED ACTIONS__"]
    for act in report.get("recommended_actions") or []:
        lines.append(f"  - {act}")
    return "\n".join(lines)

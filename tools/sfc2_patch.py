from pathlib import Path


def replace_section(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


# ---------------------------------------------------------------------------
# indicators.py — compile SFC-1 from the completed-Daily view and attach it.
# ---------------------------------------------------------------------------
p = Path("src/indicators.py")
text = p.read_text(encoding="utf-8")
old_import = "from src.market_data import partition_daily_bars\n"
new_import = "from src.market_data import partition_daily_bars\nfrom src import setup_family_compiler\n"
assert text.count(old_import) == 1
text = text.replace(old_import, new_import, 1)

start = text.index('    return {\n        "ticker": ticker,', text.index("def enrich("))
end_marker = '        "atr": atr,\n    }'
end = text.index(end_marker, start) + len(end_marker)
body = text[start:end]
assert body.startswith("    return {")
body = body.replace("    return {", "    enriched = {", 1)
body += '''

    # Phase SFC-2: family evidence is compiled from COMPLETED Daily bars only.
    # Current price is passed separately as location information. The compiler
    # is evidence-only here and does not mutate the canonical feature fields.
    enriched["setup_family_evidence"] = setup_family_compiler.compile_setup_families(
        confirmed_df, cur, enriched, config
    )
    return enriched'''
text = text[:start] + body + text[end:]
p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# prefilter.py — family-aware admission using the EXISTING 100-point budget.
# ---------------------------------------------------------------------------
p = Path("src/prefilter.py")
text = p.read_text(encoding="utf-8")
helper_marker = "# ---------------------------------------------------------------------------\n# Per-category scoring helpers\n# ---------------------------------------------------------------------------\n"
helpers = '''def _family_summary(enriched: dict) -> dict:
    value = enriched.get("setup_family_evidence")
    return value if isinstance(value, dict) else {}


def _primary_family_evidence(enriched: dict) -> dict:
    summary = _family_summary(enriched)
    family_id = summary.get("primary_family")
    families = summary.get("families")
    if not family_id or family_id == "NONE" or not isinstance(families, dict):
        return {}
    value = families.get(family_id)
    return value if isinstance(value, dict) else {}


def _compact_family_evidence(enriched: dict) -> dict | None:
    """Persist only the fields downstream execution governance needs."""
    summary = _family_summary(enriched)
    if not summary or summary.get("primary_family") in (None, "NONE"):
        return None
    return {
        "version": summary.get("version"),
        "primary_family": summary.get("primary_family"),
        "primary_state": summary.get("primary_state"),
        "primary_family_score": summary.get("primary_family_score"),
        "watch_ready": bool(summary.get("watch_ready")),
        "admission_ready": bool(summary.get("admission_ready")),
        "entry_structure_valid": bool(summary.get("entry_structure_valid")),
        "primary_invalidation_level": summary.get("primary_invalidation_level"),
        "primary_target_1": summary.get("primary_target_1"),
        "primary_rr_to_t1": summary.get("primary_rr_to_t1"),
        "primary_retest_state": _primary_family_evidence(enriched).get("retest_state"),
    }


'''
assert text.count(helper_marker) == 1
text = text.replace(helper_marker, helpers + helper_marker, 1)

old = '''def _score_structure_event(enriched: dict, weight: int) -> int:
    event = enriched.get("structure_event", "none")
    wick_only = enriched.get("wick_only_break", False)

    if event == "MSS":
        return weight                        # sweep + structure shift = highest
    if event in ("BOS", "failed_breakdown_reclaim", "accepted_break"):
        return round(weight * 0.90)
    if event == "reclaim":
        return round(weight * 0.75)
    if event == "CHOCH":
        return round(weight * 0.40)          # modest only — not a bullish full signal
    if wick_only:
        return round(weight * 0.15)          # flagged noise, not rewarded
    return 0                                 # none
'''
new = '''def _score_structure_event(enriched: dict, weight: int) -> int:
    event = enriched.get("structure_event", "none")
    wick_only = enriched.get("wick_only_break", False)

    if event == "MSS":
        return weight                        # sweep + structure shift = highest
    if event in ("BOS", "failed_breakdown_reclaim", "accepted_break"):
        return round(weight * 0.90)
    if event == "reclaim":
        return round(weight * 0.75)
    if event == "CHOCH":
        return round(weight * 0.40)          # modest only — not a bullish full signal
    if wick_only:
        return round(weight * 0.15)          # flagged noise, not rewarded

    # SFC-2: a deterministic family lifecycle can establish meaningful
    # structure/location before a classic BOS/MSS print. This maps that proof
    # into the EXISTING structure bucket; no new score weight is created.
    family = _family_summary(enriched)
    if family.get("entry_structure_valid"):
        return round(weight * 0.90)
    if family.get("admission_ready"):
        return round(weight * 0.70)
    if family.get("watch_ready"):
        return round(weight * 0.50)
    return 0                                 # none
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = '''def _score_zone_quality(enriched: dict, weight: int) -> int:
    fvg = enriched.get("fvg")
    ob = enriched.get("ob")
    score = 0

    if fvg and ob:
        score = weight                       # both present — strongest confluence
    elif fvg or ob:
        score = round(weight * 0.67)         # one present — decent

    # Bonus: price is actively inside the zone
    in_zone = (fvg and fvg.get("price_in_fvg")) or (ob and ob.get("price_at_ob"))
    if in_zone and score > 0:
        bonus = round(weight * 0.20)
        score = min(weight, score + bonus)

    return score
'''
new = '''def _score_zone_quality(enriched: dict, weight: int) -> int:
    fvg = enriched.get("fvg")
    ob = enriched.get("ob")
    score = 0

    if fvg and ob:
        score = weight                       # both present — strongest confluence
    elif fvg or ob:
        score = round(weight * 0.67)         # one present — decent

    # SFC-2: VCP pivot location, rising-MA cradle value, and active gap-fill
    # location are legitimate decision areas even when no FVG/OB is present.
    if score == 0:
        family = _primary_family_evidence(enriched)
        if family.get("location_valid") and family.get("admission_ready"):
            score = round(weight * 0.67)
        elif family.get("location_valid") and family.get("watch_ready"):
            score = round(weight * 0.45)

    # Bonus: price is actively inside the classic zone
    in_zone = (fvg and fvg.get("price_in_fvg")) or (ob and ob.get("price_at_ob"))
    if in_zone and score > 0:
        bonus = round(weight * 0.20)
        score = min(weight, score + bonus)

    return score
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = '''def _score_retest(enriched: dict, weight: int) -> int:
    status = enriched.get("retest_status", "missing")
    if status == "confirmed":
        return weight
    if status == "partial":
        return round(weight * 0.60)
    if status == "missing":
        return round(weight * 0.20)
    return 0                                 # failed
'''
new = '''def _score_retest(enriched: dict, weight: int) -> int:
    status = enriched.get("retest_status", "missing")
    if status == "confirmed":
        return weight
    if status == "partial":
        return round(weight * 0.60)

    family = _primary_family_evidence(enriched)
    family_retest = str(family.get("retest_state") or "NONE").upper()
    if family.get("admission_ready"):
        if family_retest == "HELD":
            return weight
        if family_retest == "RECLAIMED":
            return round(weight * 0.75)
        if family_retest in {"PENDING", "TESTING", "FILLING", "NOT_STARTED"}:
            return round(weight * 0.45)

    if status == "missing":
        return round(weight * 0.20)
    return 0                                 # failed
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = '''def _score_target_rr(enriched: dict, weight: int) -> int:
    overhead = enriched.get("overhead_status", "unknown")
    rr = enriched.get("estimated_rr")
    targets = enriched.get("targets", [])

    if overhead == "blocked" or not targets:
        return 0

    rr_strong = rr is not None and rr >= 3.0
    rr_weak = rr is not None and rr < 3.0

    if overhead == "clear":
        if rr_strong:
            return weight
        if rr_weak:
            return round(weight * 0.65)
        return round(weight * 0.50)          # no RR computable but path is clear

    if overhead == "moderate":
        if rr_strong:
            return round(weight * 0.67)
        if rr_weak:
            return round(weight * 0.40)
        return round(weight * 0.30)

    # unknown overhead
    if rr_strong:
        return round(weight * 0.53)
    if rr_weak:
        return round(weight * 0.25)
    return round(weight * 0.20)
'''
new = '''def _score_target_rr(enriched: dict, weight: int) -> int:
    overhead = enriched.get("overhead_status", "unknown")
    rr = enriched.get("estimated_rr")
    targets = enriched.get("targets", [])

    if overhead == "blocked":
        return 0

    # SFC-2 family targets are admission evidence only. They let a valid family
    # reach deep analysis when the classic liquidity-target builder has no
    # target yet; downstream entry tiers still require the model/tiering target
    # contract and clean path proof.
    if not targets:
        family = _primary_family_evidence(enriched)
        family_target = family.get("target_1")
        if not (family.get("admission_ready") and family_target is not None):
            return 0
        rr = family.get("rr_to_t1")
        if overhead == "clear":
            if rr is not None and rr >= 3.0:
                return weight
            if rr is not None:
                return round(weight * 0.60)
            return round(weight * 0.50)
        if overhead == "moderate":
            return round(weight * 0.40)
        return round(weight * 0.30)

    rr_strong = rr is not None and rr >= 3.0
    rr_weak = rr is not None and rr < 3.0

    if overhead == "clear":
        if rr_strong:
            return weight
        if rr_weak:
            return round(weight * 0.65)
        return round(weight * 0.50)          # no RR computable but path is clear

    if overhead == "moderate":
        if rr_strong:
            return round(weight * 0.67)
        if rr_weak:
            return round(weight * 0.40)
        return round(weight * 0.30)

    # unknown overhead
    if rr_strong:
        return round(weight * 0.53)
    if rr_weak:
        return round(weight * 0.25)
    return round(weight * 0.20)
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)

start_marker = "def apply_hard_vetoes(enriched: dict, config: dict) -> list[str]:\n"
end_marker = "\n\n# ---------------------------------------------------------------------------\n# Single-ticker prefilter result\n# ---------------------------------------------------------------------------\n"
old_section = text[text.index(start_marker):text.index(end_marker, text.index(start_marker))]
new_section = '''def apply_hard_vetoes(enriched: dict, config: dict) -> list[str]:
    """Return active broad-universe admission vetoes for this ticker.

    Phase SFC-2 allows deterministic family evidence to satisfy *admission*
    structure/location/invalidation/target requirements without granting any
    downstream entry tier. Sovereign path, extension and alignment blockers
    remain intact.
    """
    thresholds = config.get("prefilter", {}).get("thresholds", {})
    max_extension = thresholds.get("max_price_extension_from_sma20_pct", 8)
    min_rr = config.get("tiers", {}).get("snipe_it", {}).get("min_rr", 3.0)

    vetoes: list[str] = []
    status = enriched.get("data_status", "ERROR")

    if status == "EMPTY":
        vetoes.append(VETO_DATA_EMPTY)
        return vetoes
    if status == "ERROR":
        vetoes.append(VETO_DATA_ERROR)
        return vetoes
    if status == "INSUFFICIENT":
        vetoes.append(VETO_INSUFFICIENT_BARS)
        return vetoes
    if status == "STALE":
        vetoes.append(VETO_STALE_DATA)
        return vetoes

    family_summary = _family_summary(enriched)
    family_primary = _primary_family_evidence(enriched)
    family_admission = bool(family_summary.get("admission_ready"))
    family_invalidation = family_summary.get("primary_invalidation_level")
    family_target = family_summary.get("primary_target_1")

    has_structure = enriched.get("structure_event", "none") != "none"
    has_fvg = bool(enriched.get("fvg"))
    has_ob = bool(enriched.get("ob"))
    has_zone = has_fvg or has_ob

    if not has_structure and not has_zone and not family_admission:
        vetoes.append(VETO_NO_CLEAR_STRUCTURE)

    if enriched.get("invalidation_level") is None and not (
        family_admission and family_invalidation is not None
    ):
        vetoes.append(VETO_NO_INVALIDATION)

    if not enriched.get("targets") and not (
        family_admission and family_target is not None
    ):
        vetoes.append(VETO_NO_TARGET_PATH)

    if enriched.get("overhead_status") == "blocked":
        vetoes.append(VETO_OVERHEAD_BLOCKED)

    ext = enriched.get("price_extension_from_sma20_pct")
    if ext is not None and ext > max_extension:
        vetoes.append(VETO_PRICE_TOO_EXTENDED)

    if enriched.get("retest_status") == "failed":
        family_retest = str(family_primary.get("retest_state") or "NONE").upper()
        if not family_admission or family_retest == "FAILED":
            vetoes.append(VETO_RETEST_FAILED)

    if enriched.get("sma_value_alignment") == "hostile":
        vetoes.append(VETO_HOSTILE_ALIGNMENT)

    # Family provisional R:R is not a hard-entry R:R contract. Only the
    # canonical estimate can trigger the existing prefilter R:R veto.
    rr = enriched.get("estimated_rr")
    if rr is not None and rr < min_rr:
        vetoes.append(VETO_RR_BELOW_THRESHOLD)

    if (
        not has_structure
        and not has_zone
        and not family_admission
        and enriched.get("retest_status") in ("missing", "failed")
    ):
        if VETO_MID_RANGE_NO_EDGE not in vetoes:
            vetoes.append(VETO_MID_RANGE_NO_EDGE)

    return vetoes
'''
text = text.replace(old_section, new_section, 1)

old = '        "current_close_location_pct": close_loc,\n    }'
new = '        "current_close_location_pct": close_loc,\n        "setup_family_evidence": _compact_family_evidence(enriched),\n    }'
assert text.count(old) == 1
text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# claude_client.py — expose deterministic family evidence to the analyst.
# JSON response schema stays unchanged in SFC-2.
# ---------------------------------------------------------------------------
p = Path("src/claude_client.py")
text = p.read_text(encoding="utf-8")
marker = '''    # Confirmation provenance for the three feature families a developing
    # Daily bar could otherwise contaminate (Phase MBT-2).
'''
insert = '''    # Phase SFC-2 deterministic setup-family evidence. The broad model-side
    # `setup_family` response field stays backward-compatible; PRIMARY_FAMILY_ID
    # is the scanner's exact family taxonomy and must not be invented by Claude.
    family = enriched.get("setup_family_evidence")
    if isinstance(family, dict) and family.get("primary_family") not in (None, "NONE"):
        lines.append(f"PRIMARY_FAMILY_ID: {family.get('primary_family')}")
        lines.append(f"FAMILY_STATE: {family.get('primary_state')}")
        lines.append(f"FAMILY_SCORE: {family.get('primary_family_score')}")
        lines.append(f"FAMILY_WATCH_READY: {bool(family.get('watch_ready'))}")
        lines.append(f"FAMILY_ADMISSION_READY: {bool(family.get('admission_ready'))}")
        lines.append(f"FAMILY_ENTRY_STRUCTURE_VALID: {bool(family.get('entry_structure_valid'))}")
        if family.get("primary_invalidation_level") is not None:
            lines.append(f"FAMILY_INVALIDATION_LEVEL: {family.get('primary_invalidation_level')}")
        if family.get("primary_target_1") is not None:
            lines.append(f"FAMILY_TARGET_1: {family.get('primary_target_1')}")
        if family.get("primary_rr_to_t1") is not None:
            lines.append(f"FAMILY_RR_TO_T1: {family.get('primary_rr_to_t1')}")

'''
assert text.count(marker) == 1
text = text.replace(marker, insert + marker, 1)
p.write_text(text, encoding="utf-8")

print("SFC-2 family-aware admission patch applied")

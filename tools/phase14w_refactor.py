from pathlib import Path
import textwrap

PATH = Path("src/scheduler.py")
text = PATH.read_text(encoding="utf-8")

pipeline_start = text.index("async def run_scan_pipeline(")
block_start = text.index("        # Step 6.5: Trajectory", pipeline_start)
block_end = text.index("        # Step 6.7: FINAL-tier truth", block_start)
original_block = text[block_start:block_end]
block = original_block

# Remove scan-only ladder telemetry accounting from the reusable judgment organ.
basket_start = block.index("        try:\n            _tlm_basket =")
basket_end_marker = "        except Exception:\n            pass\n\n"
basket_end = block.index(basket_end_marker, basket_start) + len(basket_end_marker)
block = block[:basket_start] + block[basket_end:]

# Remove scan-only final-tier telemetry accounting. It remains in run_scan_pipeline.
served_start = block.index("        # Phase 14V.1 (B1):")
served_end = block.index("        # Step 6.6: Score calibration", served_start)
block = block[:served_start] + block[served_end:]

old_trajectory = '''        try:
            _ticker_states = state.get("tickers", {}) if isinstance(state, dict) else {}
            _previous_state = _ticker_states.get(ticker) if isinstance(_ticker_states, dict) else None
            tiering_result["trajectory"] = trajectory_mod.compute(
                tiering_result, _previous_state
            )
        except Exception as exc:
            log.warning("TRAJECTORY_ERROR: %s: %s", ticker, exc)
            tiering_result["trajectory"] = {"label": "UNKNOWN", "text": ""}
'''
new_trajectory = '''        try:
            tiering_result["trajectory"] = trajectory_mod.compute(
                tiering_result, previous_state
            )
        except Exception as exc:
            log.warning("TRAJECTORY_ERROR: %s: %s", ticker, exc)
            tiering_result["trajectory"] = {"label": "UNKNOWN", "text": ""}
'''
assert block.count(old_trajectory) == 1, "trajectory source changed unexpectedly"
block = block.replace(old_trajectory, new_trajectory)

block = block.replace("enriched_map.get(ticker, {})", "enriched")
block = block.replace("market_results.get(ticker) or {}", "market_result or {}")
assert "enriched_map" not in block
assert "market_results" not in block
assert "_tlm_" not in block
assert "state.get(" not in block

helper_body = textwrap.indent(textwrap.dedent(block).rstrip() + "\n", "    ")
helper = '''# ---------------------------------------------------------------------------
# Phase 14W — shared post-tiering judgment stack
# ---------------------------------------------------------------------------

def _complete_candidate_judgment(
    ticker: str,
    tiering_result: dict,
    enriched: dict,
    market_result: dict,
    config: dict,
    previous_state: dict | None = None,
) -> dict:
    """Complete every post-tiering chart judgment before execution governance.

    This is the single production organ used by BOTH the universe scanner and
    manual ``!analyze``. The command may bypass universe admission/cooldown,
    but it may never bypass chart evidence or SNIPE arbitration.

    Order is fixed: trajectory -> trade location -> candle evidence -> 1H
    trigger -> MTF alignment -> real 4H -> HTF structural context -> SNIPE
    gate audit -> ladder arbitration -> downgrade-only seal -> audit reconcile
    -> score calibration.

    This function does NOT dedup, route, send Discord messages, persist alert
    state, or write scan-funnel telemetry. Execution governance stays with the
    caller after the final executable tier is known.
    """
    tiering_result = tiering_result if isinstance(tiering_result, dict) else {}
    enriched = enriched if isinstance(enriched, dict) else {}
    market_result = market_result if isinstance(market_result, dict) else {}
    final_tier = tiering_result.get("final_tier", "WAIT")

''' + helper_body + '''
    return tiering_result


'''

marker = '''# ---------------------------------------------------------------------------
# Core pipeline (used by both scheduled and manual scans)
# ---------------------------------------------------------------------------

'''
assert text.count(marker) == 1, "core pipeline marker changed unexpectedly"
text = text.replace(marker, helper + marker)

pipeline_replacement = '''        # Step 6.5–6.6: Complete the shared post-tiering judgment stack.
        # Phase 14W makes this exact organ authoritative for both autoscan and
        # manual !analyze so command convenience can never create chart drift.
        _ticker_states = state.get("tickers", {}) if isinstance(state, dict) else {}
        _previous_state = _ticker_states.get(ticker) if isinstance(_ticker_states, dict) else None
        tiering_result = _complete_candidate_judgment(
            ticker,
            tiering_result,
            enriched_map.get(ticker, {}),
            market_results.get(ticker) or {},
            config,
            _previous_state,
        )
        final_tier = tiering_result.get("final_tier", final_tier)

        # Phase 14V: scan-only observations stay OUTSIDE the shared judgment organ.
        try:
            _tlm_basket = (tiering_result.get("snipe_ladder") or {}).get("internal_ladder_tier")
            if _tlm_basket:
                _tlm_baskets[_tlm_basket] = _tlm_baskets.get(_tlm_basket, 0) + 1
        except Exception:
            pass

        try:
            _tlm_served = tiering_result.get("final_tier")
            if _tlm_served:
                _tlm_final_tiers[_tlm_served] = _tlm_final_tiers.get(_tlm_served, 0) + 1
                _tlm_analysis["judged"] += 1
        except Exception:
            pass

'''
assert original_block in text, "pipeline evidence block no longer unique"
text = text.replace(original_block, pipeline_replacement, 1)

analyze_start = text.index("async def run_analyze(")
analyze_block_start = text.index("        # Tiering (cannot be bypassed)", analyze_start)
analyze_block_end = text.index("        # Alert", analyze_block_start)
old_analyze_block = text[analyze_block_start:analyze_block_end]
new_analyze_block = '''        # Tiering hard gates cannot be bypassed.
        tiering_result = tiering.validate(cr["signal"], pf_res, config)

        # Phase 14W: manual inspection bypasses universe admission/cooldown only.
        # Chart judgment is IDENTICAL to autoscan from this point forward.
        state = state_store.load(config)
        _ticker_states = state.get("tickers", {}) if isinstance(state, dict) else {}
        _previous_state = _ticker_states.get(ticker) if isinstance(_ticker_states, dict) else None
        tiering_result = _complete_candidate_judgment(
            ticker,
            tiering_result,
            enriched,
            mres,
            config,
            _previous_state,
        )
        final_tier = tiering_result.get("final_tier", "WAIT")

        # Execution governance sees the final executable tier. Manual override
        # bypasses cooldown only; WAIT/safety/routing hard blocks still bind.
        dedup_decision = state_store.check_alert(
            tiering_result, state, config, manual_override=True
        )

'''
text = text[:analyze_block_start] + new_analyze_block + text[analyze_block_end:]

old_doc = '''    Bypasses prefilter score floor and dedup cooldown.
    Still enforces: tiering hard gates, JSON validation, safe_for_alert, WAIT suppression.
'''
new_doc = '''    Bypasses universe prefilter admission and dedup cooldown only.
    Still enforces JSON validation, deterministic tiering hard gates, the complete
    post-tiering evidence/arbitration stack, safe_for_alert, and WAIT suppression.
'''
assert text.count(old_doc) == 1, "run_analyze docstring changed unexpectedly"
text = text.replace(old_doc, new_doc, 1)

# Permanent anti-drift architecture checks before writing.
pipeline = text[text.index("async def run_scan_pipeline("):text.index("async def run_full_scan")]
analyze = text[text.index("async def run_analyze("):]
assert pipeline.count("_complete_candidate_judgment(") == 1
assert analyze.count("_complete_candidate_judgment(") == 1
assert pipeline.index("_complete_candidate_judgment(") < pipeline.index("state_store.check_alert(")
assert analyze.index("_complete_candidate_judgment(") < analyze.index("state_store.check_alert(")
assert pipeline.count("state_store.check_alert(") == 1
assert analyze.count("state_store.check_alert(") == 1

PATH.write_text(text, encoding="utf-8")
print("Phase 14W scheduler refactor applied")

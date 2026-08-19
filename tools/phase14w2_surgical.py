from pathlib import Path
import textwrap

SCHEDULER = Path("src/scheduler.py")
text = SCHEDULER.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Extract the EXISTING autoscan post-tiering sequence without reformatting any
# unrelated scheduler code. Scan-only telemetry stays with run_scan_pipeline.
# ---------------------------------------------------------------------------
pipeline_start = text.index("async def run_scan_pipeline(")
block_start = text.index("        # Step 6.5: Trajectory", pipeline_start)
block_end = text.index("        # Step 6.7: FINAL-tier truth", block_start)
original_block = text[block_start:block_end]
shared_block = original_block

ladder_tlm_start = shared_block.index("        try:\n            _tlm_basket =")
ladder_tlm_end_marker = "        except Exception:\n            pass\n\n"
ladder_tlm_end = shared_block.index(ladder_tlm_end_marker, ladder_tlm_start) + len(ladder_tlm_end_marker)
ladder_tlm_block = shared_block[ladder_tlm_start:ladder_tlm_end]
shared_block = shared_block[:ladder_tlm_start] + shared_block[ladder_tlm_end:]

served_tlm_start = shared_block.index("        # Phase 14V.1 (B1):")
served_tlm_end = shared_block.index("        # Step 6.6: Score calibration", served_tlm_start)
served_tlm_block = shared_block[served_tlm_start:served_tlm_end]
shared_block = shared_block[:served_tlm_start] + shared_block[served_tlm_end:]

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
assert shared_block.count(old_trajectory) == 1, "trajectory source changed unexpectedly"
shared_block = shared_block.replace(old_trajectory, new_trajectory, 1)

shared_block = shared_block.replace("enriched_map.get(ticker, {})", "enriched")
shared_block = shared_block.replace("market_results.get(ticker) or {}", "market_result or {}")

for forbidden in ("enriched_map", "market_results", "_tlm_", "state.get("):
    assert forbidden not in shared_block, f"shared judgment organ still owns {forbidden}"

helper_body = textwrap.indent(textwrap.dedent(shared_block).rstrip() + "\n", "    ")
helper = '''# ---------------------------------------------------------------------------
# Phase 14W2 — shared post-tiering candidate judgment
# ---------------------------------------------------------------------------

def _complete_candidate_judgment(
    ticker: str,
    tiering_result: dict,
    enriched: dict,
    market_result: dict,
    config: dict,
    previous_state: dict | None = None,
) -> dict:
    """Run the production post-tiering evidence/arbitration stack once.

    Used by both autoscan and manual ``!analyze``. This organ does not own
    admission, dedup/cooldown, Discord routing, state persistence, or scan-time
    funnel telemetry; those remain caller responsibilities.
    """
    tiering_result = tiering_result if isinstance(tiering_result, dict) else {}
    enriched = enriched if isinstance(enriched, dict) else {}
    market_result = market_result if isinstance(market_result, dict) else {}
    final_tier = tiering_result.get("final_tier", "WAIT")

''' + helper_body + '''
    return tiering_result


'''

core_marker = '''# ---------------------------------------------------------------------------
# Core pipeline (used by both scheduled and manual scans)
# ---------------------------------------------------------------------------

'''
assert text.count(core_marker) == 1, "core pipeline marker changed unexpectedly"
text = text.replace(core_marker, helper + core_marker, 1)

pipeline_replacement = '''        # Step 6.5–6.6: shared production chart judgment (Phase 14W2).
        # Autoscan and !analyze must consume the same post-tiering organ.
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

'''
pipeline_replacement += ladder_tlm_block
pipeline_replacement += served_tlm_block
assert text.count(original_block) == 1, "autoscan post-tiering block changed unexpectedly"
text = text.replace(original_block, pipeline_replacement, 1)

# ---------------------------------------------------------------------------
# Route manual !analyze through the same judgment organ. It still bypasses
# universe admission and cooldown only; deterministic veto evidence is retained.
# ---------------------------------------------------------------------------
old_doc = '''    Bypasses prefilter score floor and dedup cooldown.
    Still enforces: tiering hard gates, JSON validation, safe_for_alert, WAIT suppression.
'''
new_doc = '''    Bypasses universe prefilter admission and dedup cooldown only.
    Still enforces: tiering hard gates, JSON validation, the complete post-tiering
    evidence/arbitration stack, safe_for_alert, and WAIT suppression.
'''
assert text.count(old_doc) == 1, "run_analyze docstring changed unexpectedly"
text = text.replace(old_doc, new_doc, 1)

analyze_start = text.index("async def run_analyze(")
analyze_block_start = text.index("        # Tiering (cannot be bypassed)", analyze_start)
analyze_block_end = text.index("        # Alert", analyze_block_start)
old_analyze_block = text[analyze_block_start:analyze_block_end]
new_analyze_block = '''        # Tiering (cannot be bypassed)
        tiering_result = tiering.validate(cr["signal"], pf_res, config)

        # Phase 14W2: manual inspection bypasses admission/cooldown only.
        # Chart judgment is identical to autoscan from this point forward.
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

        # State + dedup — manual_override=True bypasses cooldown only.
        dedup_decision = state_store.check_alert(
            tiering_result, state, config, manual_override=True
        )

'''
text = text[:analyze_block_start] + new_analyze_block + text[analyze_block_end:]

# Production anti-drift checks before writing.
pipeline = text[text.index("async def run_scan_pipeline("):text.index("async def run_full_scan")]
analyze = text[text.index("async def run_analyze("):]
assert pipeline.count("_complete_candidate_judgment(") == 1
assert analyze.count("_complete_candidate_judgment(") == 1
assert pipeline.count("state_store.check_alert(") == 1
assert analyze.count("state_store.check_alert(") == 1
assert pipeline.index("_complete_candidate_judgment(") < pipeline.index("state_store.check_alert(")
assert analyze.index("_complete_candidate_judgment(") < analyze.index("state_store.check_alert(")

SCHEDULER.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Repoint architecture tests at the organ that now owns the relevant ordering.
# Do not satisfy architecture guards with comments or duplicated marker strings.
# ---------------------------------------------------------------------------
htf_path = Path("tests/test_phase_14i_higher_timeframe_context.py")
htf_text = htf_path.read_text(encoding="utf-8")
old_htf = 'src = inspect.getsource(scheduler.run_scan_pipeline)'
new_htf = 'src = inspect.getsource(scheduler._complete_candidate_judgment)'
assert htf_text.count(old_htf) == 1, "HTF architecture guard changed unexpectedly"
htf_path.write_text(htf_text.replace(old_htf, new_htf, 1), encoding="utf-8")

v14_path = Path("tests/test_phase_14v_scan_time_funnel_telemetry.py")
v14_text = v14_path.read_text(encoding="utf-8")

start = v14_text.index("def test_v1_check_alert_runs_once_after_final_tier_mutation():")
end = v14_text.index("\n\n# ---- H1:", start)
new_guard = '''def test_v1_check_alert_runs_once_after_final_tier_mutation():
    """Phase 14S.4B/14W2: judge fully, then dedup final executable truth."""
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    organ = src[src.index("def _complete_candidate_judgment("):src.index("async def run_scan_pipeline")]
    scan = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    assert organ.index("apply_ladder_arbitration") < organ.index("seal_snipe_confirmed_consistency")
    assert scan.count("state_store.check_alert(") == 1
    assert scan.index("_complete_candidate_judgment(") < scan.index("state_store.check_alert(")
    assert scan.index("state_store.check_alert(") < scan.index("discord_alerts.send_alert")
'''
v14_text = v14_text[:start] + new_guard + v14_text[end:]

start = v14_text.index("def test_v1c_24_25_check_alert_final_tier_timing_and_cap_unchanged():")
end = v14_text.index("\n\n# ===========================================================================\n# PHASE 14V.2", start)
new_guard = '''def test_v1c_24_25_check_alert_final_tier_timing_and_cap_unchanged():
    src = Path("src/scheduler.py").read_text(encoding="utf-8")
    organ = src[src.index("def _complete_candidate_judgment("):src.index("async def run_scan_pipeline")]
    scan = src[src.index("async def run_scan_pipeline"):src.index("async def run_full_scan")]
    assert organ.index("apply_ladder_arbitration") < organ.index("seal_snipe_confirmed_consistency")
    assert scan.count("state_store.check_alert(") == 1
    assert scan.index("_complete_candidate_judgment(") < scan.index("state_store.check_alert(")
    assert scan.index("state_store.check_alert(") < scan.index("discord_alerts.send_alert")
    import yaml
    cfg = yaml.safe_load(open("config/doctrine_config.yaml"))
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30
'''
v14_text = v14_text[:start] + new_guard + v14_text[end:]
v14_path.write_text(v14_text, encoding="utf-8")

print("Phase 14W2 surgical parity refactor applied")

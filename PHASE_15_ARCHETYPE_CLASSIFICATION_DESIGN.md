# PHASE 15 — ARCHETYPE CLASSIFICATION LAYER: DESIGN MEMO
## Read-Only Design. No Code Changes. No Implementation Authorization.

**Status:** Design only. Requires explicit approval before any implementation begins.  
**Authorship session:** Phase 15 design, post-Phase-14D audit.  
**Scope:** Display-only observational layer. Zero impact on score, tier, capital, routing, suppression, or dedup.

---

## 1. Purpose and Philosophy

The scanner has achieved structural coherence across Phases 1–14. It is:
- state-aware (trajectory)
- calibration-aware (score realism)
- capital-disciplined (tiering gates)
- dedup-disciplined (cooldown + key-based suppression)

Phase 15 addresses the remaining gap: **operator-facing classification clarity**.

A SNIPE_IT alert for SNDK (elite, spacious, sovereign structure) and a SNIPE_IT alert for AFRM (tight stop, 17.61 R:R, $0.28 invalidation) both post to #snipeit with capital authorized. Both are structurally valid. But they are materially different in execution character. The operator currently has to read the full alert to understand the distinction.

The archetype layer makes the distinction explicit at a glance — without changing what either alert does, routes, or authorizes.

**The archetype is a label, not a gate. It describes. It does not decide.**

---

## 2. Design Constraints (Non-Negotiable)

The following constraints apply permanently to Phase 15 and any implementation derived from it:

| Constraint | Enforcement |
|-----------|-------------|
| Does NOT affect `score` | Archetype reads `score`; never writes it |
| Does NOT affect `calibrated_score` | Archetype reads `calibration`; never writes it |
| Does NOT affect `final_tier` | Archetype reads `final_tier`; never writes it |
| Does NOT affect `capital_action` | Archetype is classification only |
| Does NOT affect `discord_channel` | Routing remains `tiering.py` exclusive |
| Does NOT affect suppression | Archetype label never enters dedup key |
| Does NOT affect alert frequency | No new suppression paths |
| Does NOT add new indicators | Input fields sourced exclusively from existing `tiering_result` |
| Does NOT create hidden gates | Classification rules are transparent and auditable |

---

## 3. Archetype Definitions

Five archetypes. Two for executable tiers (SNIPE_IT / STARTER). Two for watch tier (NEAR_ENTRY). One cross-tier stale label.

---

### ARCHETYPE 1: INSTITUTIONAL_CONTINUATION

**Intended meaning:** The setup exhibits the hallmarks of institutional-grade continuation. Spacious stop geometry, clean structure, supportive context, broad execution margin. The scanner's highest-confidence continuation class.

**Classification criteria (all must be satisfied):**

| Field | Required value |
|-------|----------------|
| `final_tier` | `SNIPE_IT` or `STARTER` |
| `risk_state` | `healthy` or `normal` |
| `overhead_status` | `clear` |
| `sma_value_alignment` | `supportive` |
| `structure_event` | `bos`, `mss`, or `choch` (elite structures) |
| `retest_status` | `confirmed` |
| `hold_status` | `confirmed` |
| `calibration.score_band` | `elite` or `executable` |
| `trajectory.label` | NOT in `{"DETERIORATING", "DOWNGRADING", "QUALITY_COMPRESSED"}` |

**Session examples confirmed by Phase 14D audit:**
- SNDK (Score 88, cal 92, elite band, clear overhead, 5/5 dimensions)
- CGNX (Score 82, clear overhead, healthy risk — note: NEAR_ENTRY, would not qualify for this archetype in that state)

**Discord display line:**
```
  Archetype:     INSTITUTIONAL_CONTINUATION — sovereign continuation structure
```

---

### ARCHETYPE 2: TACTICAL_CONTINUATION

**Intended meaning:** Structurally valid continuation with confirmed sequence and hold, but not sovereign-grade. Moderate overhead, mixed SMA, or non-elite structure reduces execution spaciousness. Valid and authorized but precision-dependent.

**Classification criteria:**
- `final_tier` in `{SNIPE_IT, STARTER}`
- Does NOT qualify as INSTITUTIONAL_CONTINUATION
- Does NOT qualify as FRAGILE_CONTINUATION
- `retest_status` = `confirmed`
- `hold_status` = `confirmed`

(All conditions not met for institutional, and risk_state not in `{tight, elevated, fragile}` and not triggering the fragile R:R rule.)

**Session examples confirmed by Phase 14D audit:**
- IESC (Score 87, moderate overhead, 4/5 dimensions — overhead alone disqualifies institutional)
- CPER AM (Score 88, moderate overhead, 3/5 dimensions)
- AME (Score 82, moderate overhead, mixed SMA, tight risk would bump to FRAGILE)

Note: AME with `risk_state = tight` would be classified FRAGILE_CONTINUATION, not TACTICAL (see §3.3).

**Discord display line:**
```
  Archetype:     TACTICAL_CONTINUATION — valid but precision-dependent
```

---

### ARCHETYPE 3: FRAGILE_CONTINUATION

**Intended meaning:** The setup clears all structural gates but execution survivability is compressed. The stop geometry, risk window, or R:R construction makes the setup sensitive to minor intraday movement. Operator verification is essential before deployment.

**Classification criteria (executable tier only; either trigger is sufficient):**

**Primary trigger — risk state:**
| Field | Required value |
|-------|----------------|
| `final_tier` | `SNIPE_IT` or `STARTER` |
| `risk_state` | `tight`, `elevated`, or `fragile` |

**Secondary trigger — geometric compression (risk state alone insufficient if classified healthy/normal but stop is anomalously narrow):**
| Field | Required value |
|-------|----------------|
| `final_tier` | `SNIPE_IT` or `STARTER` |
| `risk_state` | `healthy` or `normal` |
| `risk_window_pct` | `< 0.75%` (stop below 0.75% of price, regardless of risk state label) |

The secondary trigger catches the edge case where a healthy-risk-labeled setup has a stop so narrow that it is mechanically fragile regardless of classification. (Example: a $0.28 stop on a $64 stock would be ~0.44% — below threshold regardless of risk label.)

**Session examples confirmed by Phase 14D audit:**
- AFRM (risk_state: tight, stop $0.28/0.44%) → FRAGILE_CONTINUATION (primary + secondary trigger)
- AME (risk_state: tight, stop $2.13/0.94%) → FRAGILE_CONTINUATION (primary trigger only; 0.94% above secondary threshold)

**CRITICAL:** FRAGILE_CONTINUATION does NOT suppress the alert. It does NOT change capital authorization. It labels. The operator reads the label and decides. The risk note ("Risk window is tight; verify live chart before entry.") remains the operational warning.

**Discord display line:**
```
  Archetype:     FRAGILE_CONTINUATION — execution survivability compressed
```

---

### ARCHETYPE 4: WATCH_CONTINUATION

**Intended meaning:** Valid continuation structure with genuine upside potential, but trigger authority is unresolved. Price has not accepted above trigger. Confirmation is pending. No capital deployment appropriate until blocker resolves.

**Classification criteria:**
| Field | Required value |
|-------|----------------|
| `final_tier` | `NEAR_ENTRY` |
| `trajectory.label` | NOT in `{"STALE_WATCH", "BLOCKER_PERSISTING", "QUALITY_COMPRESSED", "DETERIORATING", "DOWNGRADING"}` |

Positive trajectory labels that qualify for WATCH_CONTINUATION: `NEW_SIGNAL`, `UPGRADING`, `IMPROVING`, `REPEATED_NO_CHANGE` (on first alert), `UNKNOWN`.

**Session examples confirmed by Phase 14D audit:**
- COHU (NEAR_ENTRY, Score 84, R:R 8.06, trajectory NOT PROVIDED — would default to WATCH_CONTINUATION)
- BE (NEAR_ENTRY at first alert; subsequent alert shifted to STALE_WATCH trajectory → reclassified)
- CPER PM (NEAR_ENTRY after demotion; trajectory DOWNGRADING → would NOT qualify as WATCH_CONTINUATION — see STALE/WATCH boundary note below)

Note on CPER PM: trajectory = DOWNGRADING. This does not fit WATCH_CONTINUATION (which implies positive or neutral trajectory) nor STALE_WATCH (which implies unchanged, not degrading). DOWNGRADING trajectory on NEAR_ENTRY is edge-case — recommend classification as WATCH_CONTINUATION with caveat that the display text acknowledges the degradation, since no fifth archetype is needed and the trajectory line already carries the DOWNGRADING label. The archetype layer does not need to duplicate that information.

**Discord display line:**
```
  Archetype:     WATCH_CONTINUATION — valid structure, trigger authority pending
```

---

### ARCHETYPE 5: STALE_WATCH

**Intended meaning:** Structurally valid candidate that has appeared in multiple consecutive scans without material change. No new confirmation. No reclaim progress. The label communicates staleness explicitly so the operator is not misled into treating a repeated alert as fresh intelligence.

**Classification criteria:**
| Field | Required value |
|-------|----------------|
| `final_tier` | `NEAR_ENTRY` (typically; trajectory label can appear on any tier theoretically) |
| `trajectory.label` | `STALE_WATCH` or `BLOCKER_PERSISTING` or `QUALITY_COMPRESSED` |

**Session examples confirmed by Phase 14D audit:**
- CGNX (two alerts: STALE_WATCH trajectory, cooldown_expired, same key, same calibration)
- BE (second alert after trigger_changed; trajectory STALE_WATCH)

**Discord display line:**
```
  Archetype:     STALE_WATCH — no new structural information since last scan
```

---

## 4. Classification Priority and Decision Logic

When multiple conditions could apply, the following priority order resolves ambiguity:

```
Step 1: Is final_tier in {SNIPE_IT, STARTER}?
    YES →
        Step 1a: Is risk_state in {tight, elevated, fragile}?
                OR risk_window_pct < 0.75%?
            YES → FRAGILE_CONTINUATION
            NO  →
                Step 1b: Are all INSTITUTIONAL criteria satisfied?
                    YES → INSTITUTIONAL_CONTINUATION
                    NO  → TACTICAL_CONTINUATION

Step 2: Is final_tier == NEAR_ENTRY?
    YES →
        Step 2a: Is trajectory.label in {STALE_WATCH, BLOCKER_PERSISTING, QUALITY_COMPRESSED}?
            YES → STALE_WATCH
            NO  → WATCH_CONTINUATION

Step 3: Is final_tier == WAIT?
    → No archetype assigned (WAIT is not posted; archetype is irrelevant)

Step 4: trajectory data unavailable (exception or missing)?
    → Assign WATCH_CONTINUATION for NEAR_ENTRY, TACTICAL_CONTINUATION for executable tiers
    → Append "(unclassified)" to display text
```

---

## 5. Input Field Source Map

Phase 15 reads exclusively from `tiering_result`. No new data sources.

| Archetype input | Source field in `tiering_result` |
|-----------------|----------------------------------|
| Tier | `tiering_result["final_tier"]` |
| Risk state | `tiering_result["final_signal"]["risk_realism_state"]` |
| Risk window % | `tiering_result["final_signal"]["risk_window_pct"]` (if available) or derived |
| Overhead | `tiering_result["final_signal"]["overhead_status"]` |
| SMA alignment | `tiering_result["final_signal"]["sma_value_alignment"]` |
| Structure event | `tiering_result["final_signal"]["structure_event"]` |
| Retest | `tiering_result["final_signal"]["retest_status"]` |
| Hold | `tiering_result["final_signal"]["hold_status"]` |
| Score band | `tiering_result["calibration"]["score_band"]` |
| Trajectory label | `tiering_result["trajectory"]["label"]` |

No new fields added to `tiering_result`. The archetype result is stored as a new key: `tiering_result["archetype"]`.

`tiering_result["archetype"]` shape:
```python
{
    "label":        str,   # "INSTITUTIONAL_CONTINUATION" | "TACTICAL_CONTINUATION" |
                           # "FRAGILE_CONTINUATION" | "WATCH_CONTINUATION" | "STALE_WATCH"
    "display_text": str,   # One-line human phrase for Discord display
    "basis":        list,  # List of field values that drove the classification decision
}
```

---

## 6. Integration Architecture

### 6.1 Execution Point

The archetype classifier runs **after** calibration (Step 6.6 in `scheduler.py`) and **before** Discord formatting. Proposed as Step 6.7:

```python
# Step 6.7: Archetype classification (display-only)
try:
    tiering_result["archetype"] = archetype_mod.classify(tiering_result)
except Exception as exc:
    log.warning("ARCHETYPE_ERROR: %s: %s", ticker, exc)
    tiering_result["archetype"] = None
```

**Module:** `src/archetype.py`  
**Public API:** `classify(tiering_result: dict) -> dict`  
**Never raises** (same pattern as `calibrate_score`).

### 6.2 Discord Rendering

The archetype display line is appended to the ACTION block, after the Score realism line:

```
ACTION
  SNIPE_IT conditions met.
  FULL QUALITY — capital authorized after live-chart verification.
  Quality read: Elite candidate — all five quality dimensions institutional-grade.
  Next: ...
  Why:  ...
  Trajectory:    Upgrading: NEAR_ENTRY → SNIPE_IT (score 91 → 88)
  Score realism: 92 calibrated (+4) — elite institutional setup, tier improving across scans.
  Archetype:     INSTITUTIONAL_CONTINUATION — sovereign continuation structure
```

For FRAGILE_CONTINUATION on a STARTER alert:
```
ACTION
  STARTER conditions met.
  STARTER SIZE ONLY — reduced-size capital only.
  Quality read: A+ candidate — 4 of 5 dimensions premium, confirmed sequence and hold.
  Next: ...
  Why:  ...
  Trajectory:    Repeated — no material change
  Score realism: 83 calibrated (+1) — strong tactical setup, clear overhead path.
  Archetype:     FRAGILE_CONTINUATION — execution survivability compressed
```

**Rendering condition:** Archetype line is rendered only when `tiering_result["archetype"]` is not None. If archetype classification failed (exception), the line is omitted silently (same behavior as calibration display_text when empty).

### 6.3 Ownership

| Responsibility | Owner |
|---------------|-------|
| Archetype classification | `src/archetype.py` |
| Archetype storage | `tiering_result["archetype"]` |
| Archetype rendering | `src/discord_alerts.py` |
| Dedup key (unchanged) | `src/state_store.py` — archetype NOT added to dedup key |
| Routing (unchanged) | `src/tiering.py` — archetype never reads or writes routing |

---

## 7. Test Plan (for implementation phase)

All tests in `tests/test_phase_15_archetype.py`. No live API calls. No Discord calls.

| Test | Assertion |
|------|-----------|
| `test_institutional_all_criteria_met` | All institutional fields pass → INSTITUTIONAL_CONTINUATION |
| `test_institutional_blocked_by_overhead_moderate` | overhead=moderate → falls to TACTICAL |
| `test_institutional_blocked_by_hostile_sma` | sma_alignment=mixed → falls to TACTICAL |
| `test_institutional_blocked_by_non_elite_structure` | structure=reclaim → falls to TACTICAL |
| `test_institutional_blocked_by_negative_trajectory` | trajectory=DETERIORATING → falls to TACTICAL |
| `test_fragile_tight_risk_state` | risk_state=tight on SNIPE_IT → FRAGILE |
| `test_fragile_elevated_risk_state` | risk_state=elevated on STARTER → FRAGILE |
| `test_fragile_geometric_threshold` | risk_state=healthy, risk_window_pct=0.44% → FRAGILE |
| `test_fragile_above_geometric_threshold` | risk_state=healthy, risk_window_pct=0.80% → not FRAGILE (TACTICAL or INSTITUTIONAL) |
| `test_tactical_is_default_executable` | Executable tier, healthy risk, moderate overhead → TACTICAL |
| `test_watch_continuation_new_signal` | NEAR_ENTRY, trajectory=NEW_SIGNAL → WATCH_CONTINUATION |
| `test_watch_continuation_upgrading` | NEAR_ENTRY, trajectory=UPGRADING → WATCH_CONTINUATION |
| `test_stale_watch_trajectory_stale_watch` | NEAR_ENTRY, trajectory=STALE_WATCH → STALE_WATCH |
| `test_stale_watch_blocker_persisting` | NEAR_ENTRY, trajectory=BLOCKER_PERSISTING → STALE_WATCH |
| `test_wait_tier_no_archetype` | final_tier=WAIT → archetype=None |
| `test_exception_returns_safe_dict` | Malformed tiering_result → no raise, returns None or safe dict |
| `test_archetype_does_not_mutate_score` | classify() called → tiering_result["score"] unchanged |
| `test_archetype_does_not_mutate_tier` | classify() called → tiering_result["final_tier"] unchanged |
| `test_archetype_does_not_mutate_calibration` | classify() called → tiering_result["calibration"] unchanged |
| `test_afrm_pattern_classified_fragile` | STARTER, tight risk, 0.44% stop → FRAGILE_CONTINUATION |
| `test_sndk_pattern_classified_institutional` | SNIPE_IT, healthy, clear, supportive, BOS → INSTITUTIONAL_CONTINUATION |
| `test_iesc_pattern_classified_tactical` | SNIPE_IT, healthy, moderate overhead → TACTICAL_CONTINUATION |
| `test_display_line_rendered_in_action_block` | discord_alerts formats archetype line after score realism line |
| `test_display_line_omitted_when_none` | archetype=None → no archetype line in output |
| `test_archetype_not_in_dedup_key` | Archetype field never appears in state_store dedup key construction |

---

## 8. Archetype ↔ Observed Alert Mapping (Phase 14D Evidence)

The following retrospective classification applies the archetype logic to May 18 confirmed alerts. This is design validation, not live output.

| Ticker | Tier | Score | Risk | Overhead | Structure | Trajectory | → Archetype |
|--------|------|-------|------|----------|-----------|------------|-------------|
| SNDK | SNIPE_IT | 88 | healthy | clear | BOS | UPGRADING | INSTITUTIONAL_CONTINUATION |
| IESC | SNIPE_IT | 87 | healthy | moderate | BOS | UPGRADING | TACTICAL_CONTINUATION |
| CPER AM | SNIPE_IT | 88 | healthy | moderate | BOS | UPGRADING | TACTICAL_CONTINUATION |
| AME | STARTER | 82 | tight | moderate | BOS | REPEATED | FRAGILE_CONTINUATION |
| AFRM | STARTER | 82 | tight | clear | BOS | REPEATED | FRAGILE_CONTINUATION |
| CPER PM | NEAR_ENTRY | 84 | healthy | moderate | BOS | DOWNGRADING | WATCH_CONTINUATION¹ |
| COHU | NEAR_ENTRY | 84 | healthy | clear | BOS | NOT PROVIDED | WATCH_CONTINUATION (default) |
| BE | NEAR_ENTRY | 82 | healthy | clear | BOS | STALE_WATCH | STALE_WATCH |
| CGNX ×2 | NEAR_ENTRY | 82 | healthy | clear | BOS | STALE_WATCH | STALE_WATCH |

¹ CPER PM trajectory = DOWNGRADING. Not in STALE_WATCH set. Defaults to WATCH_CONTINUATION. The DOWNGRADING trajectory line already communicates degradation; archetype does not need to duplicate it.

**Retrospective validation:** All nine archetype assignments are consistent with the observable alert characteristics. No misclassification identified. INSTITUTIONAL_CONTINUATION correctly restricted to one alert (SNDK). FRAGILE_CONTINUATION correctly captures both tight-risk STARTERs.

---

## 9. Risk Register

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Hidden tier system** | Archetypes start being used as informal promotion/demotion gates | Archetype must never appear in tiering logic. Tests assert score/tier immutability. |
| **Hidden suppression** | Low-conviction archetype labels cause operators to self-suppress execution | Labels are descriptive only. No suppression built in. Operator discretion is explicit doctrine. |
| **Calibration duplication** | Archetype overlaps with calibration score band, creating redundant signals | Calibration captures score realism numerically. Archetype captures structural character categorically. Different dimensions. No overlap. |
| **Over-classification** | Too many archetypes fragment operator attention | Five archetypes maximum. No sub-types. No conditional labels. |
| **Archetype scope creep** | Archetype starts influencing routing, suppression, or scoring after deployment | Immutability tests run on every build. Any routing use of archetype → immediate revert. |
| **FRAGILE suppression creep** | FRAGILE_CONTINUATION treated as implicit veto | Explicit doctrine: FRAGILE labels, never suppresses. Risk note remains the operational warning. |

---

## 10. What Phase 15 Does NOT Include

The following were considered and explicitly excluded from Phase 15 scope:

| Item | Reason excluded |
|------|----------------|
| R:R magnitude adjustment (P2) | Already held for standalone review. Separate from archetype classification. |
| Prompt hardening (P4) | Separate review. No classification connection. |
| WAIT tier archetype | WAIT is never posted. Archetype is irrelevant. |
| Sub-archetypes (e.g., INSTITUTIONAL_COMPRESSION, FRAGILE_REVERSAL) | Complexity without proportionate clarity gain. Five archetypes cover the classification space cleanly. |
| Archetype-based dedup changes | Violates constraint. Dedup key is immutable to archetype. |
| Archetype-based cooldown changes | Violates constraint. |
| Archetype history in state_store | Not needed. Trajectory already captures state evolution. |
| CMI, ROK classification | No May 18 data. Cannot retrospectively validate. |

---

## 11. Implementation Sequence (Conditional on Approval)

If Phase 15 is approved for implementation:

**Phase 15A — Core classifier:**
- Create `src/archetype.py` with `classify()` function
- Add Step 6.7 to `scheduler.py`
- Add `tests/test_phase_15_archetype.py` with all tests from §7
- Run full suite. All prior tests must remain passing.

**Phase 15B — Discord rendering:**
- Add archetype line to ACTION block in `src/discord_alerts.py`
- Update `tests/test_discord_alerts.py` to verify archetype line present when non-None, absent when None
- Run full suite.

**Phase 15C — Live session observation:**
- Run 3–5 live sessions
- Observe archetype distribution in alerts
- Confirm no alert frequency reduction
- Confirm no suppression side effects
- Confirm archetype labels match operator intuition for each alert
- Produce brief observation memo before any parameter adjustment

**No parameter adjustments (threshold changes, new criteria) before Phase 15C observation.**

---

## 12. Final Design Verdict

Phase 15 is architecturally sound as a display-only classification layer. It adds operator-facing truth without modifying any mechanical behavior.

The five archetypes map cleanly to the observable alert population (validated retroactively against Phase 14D audit data). The classification logic is deterministic, transparent, and auditable from existing fields.

The primary risk is not technical — it is behavioral: allowing archetype labels to drift into suppression or routing logic. The immutability tests and the explicit "FRAGILE labels, never suppresses" doctrine clause are the primary safeguards.

The scanner is executing correctly. Phase 15 improves what the operator reads, not what the scanner decides.

---

*Design memo complete. Awaiting implementation approval. No code changes made.*

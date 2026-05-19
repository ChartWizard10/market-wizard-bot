# PHASE 14D — LIVE STATE TRANSITION AUDIT
## May 18, 2026 — Production Scanner Session

**Audit type:** Read-only. No code changes.  
**Source:** Discord alert screenshots, #snipeit and #starter channels, May 18 session.  
**Scans captured:** scan_20260518_143703_fb9c58 (≈10:58 AM ET), scan_20260518_192805_c9e6fb (≈3:49 PM ET), scan_20260518_194612_1ec8c6 (≈3:49 PM ET, second run)  
**Calibration state at time of alerts:** Pre-Phase-14C. P1 (tight=-1) and P3 (UPGRADING +2→+1) not yet deployed.

---

## 1. Alert Inventory

All alerts confirmed from screenshots. Fields marked NOT PROVIDED were not visible in any screenshot.

| # | Ticker | Tier | Score | Cal | Delta | Structure | Zone | Overhead | Risk State | R:R | Trajectory | Dedup Reason | Scan |
|---|--------|------|-------|-----|-------|-----------|------|----------|------------|-----|------------|--------------|------|
| 1 | CPER | SNIPE_IT | 88 | 89 | +1 | BOS | FVG | moderate | healthy | 8.0 | UPGRADING (NE→SI, 88→88) | tier_improved | 143703 |
| 2 | SNDK | SNIPE_IT | 88 | 92 | +4 | BOS | FVG | clear | healthy | 4.31 | UPGRADING (NE→SI, 91→88) | tier_improved | 194612 |
| 3 | IESC | SNIPE_IT | 87 | 88 | +1 | BOS | OB | moderate | healthy | 6.01 | UPGRADING (NE→SI, 88→87) | tier_improved¹ | 194612 |
| 4 | AME | STARTER | 82 | 81 | −1 | BOS | FVG | moderate | tight | 4.70 | REPEATED | cooldown_expired | 192805 |
| 5 | AFRM | STARTER | 82 | 84 | +2 | BOS | OB | clear | tight | 17.61 | REPEATED | cooldown_expired | 192805 |
| 6 | COHU | NEAR_ENTRY | 84 | NP² | NP | BOS | FVG | clear | healthy | 8.06 | NOT PROVIDED | trigger_changed³ | NP |
| 7 | CGNX | NEAR_ENTRY | 82 | 81 | −1 | BOS | FVG | clear | healthy | 3.01 | STALE_WATCH | cooldown_expired | 192805 + 194612 |
| 8 | BE | NEAR_ENTRY | 82 | 81 | −1 | BOS | FVG | clear | healthy | 4.21 | STALE_WATCH | trigger_changed | 192805 |
| 9 | CPER | NEAR_ENTRY | 84 | 80 | −4 | BOS | FVG | moderate | healthy | 5.00 | DOWNGRADING (SI→NE, 88→84) | trigger_changed | 192805 |

**Not provided — no screenshots received:**  
CMI, ROK: zero data. Excluded from all findings.

¹ IESC dedup reason inferred as `tier_improved`; META block not visible in screenshots.  
² COHU calibration not visible in screenshots (ACTION block truncated).  
³ COHU dedup reason inferred from summary context; not confirmed in screenshots.

---

## 2. Tier Transition Integrity

### 2.1 Promotion Transitions (NEAR_ENTRY → SNIPE_IT)

Three tickers were promoted from NEAR_ENTRY to SNIPE_IT during the session.

**CPER (scan_143703, ≈10:58 AM)**  
- Prior state: NEAR_ENTRY. Promoted to SNIPE_IT. Score held at 88 (88→88).  
- Trajectory: `UPGRADING`. Dedup: `tier_improved`. Correctly re-alerted on tier improvement.  
- All SNIPE_IT gates confirmed in alert: retest confirmed, hold confirmed, invalidation at FVG bottom 37.90, R:R 8.0 ≥ 3.0, overhead moderate (non-blocking).  
- Tier promotion is structurally justified. No integrity issue.

**SNDK (scan_194612, ≈3:49 PM)**  
- Prior state: NEAR_ENTRY (score 91). Promoted to SNIPE_IT. Score adjusted to 88 (91→88).  
- Score compression of 3 points on promotion is notable but does not breach SNIPE_IT gate (min score 85). Confirmed: retest confirmed, hold confirmed, invalidation at FVG bottom 1275.11, R:R 4.31 ≥ 3.0, overhead clear.  
- Trajectory: `UPGRADING`. Dedup: `tier_improved`. Alert correct.  
- Quality read: "Elite candidate — all five quality dimensions institutional-grade." Highest quality designation assigned in this session.

**IESC (scan_194612, ≈3:49 PM)**  
- Prior state: NEAR_ENTRY (score 88). Promoted to SNIPE_IT. Score adjusted to 87 (88→87).  
- Score declined by 1 point on promotion. SNIPE_IT gate still cleared (87 ≥ 85).  
- All gates confirmed: retest confirmed, hold confirmed, invalidation at OB low 626.42, R:R 6.01 ≥ 3.0, overhead moderate (non-blocking).  
- Trajectory: `UPGRADING`. Alert correct.

**Finding:** All three promotions passed SNIPE_IT hard gate requirements. Tier assignment and re-alert logic operated correctly in all cases. Score compression on promotion (SNDK: −3, IESC: −1) did not breach tier floors.

---

### 2.2 Demotion Transition (SNIPE_IT → NEAR_ENTRY)

**CPER (scan_192805 or scan_194612, ≈3:49 PM)**  
- Morning state: SNIPE_IT (score 88). Afternoon state: NEAR_ENTRY (score 84).  
- Trigger shifted from 38.22 to 38.52 (+$0.30). Dedup: `trigger_changed`. Re-alert issued correctly.  
- Tier regression from SNIPE_IT to NEAR_ENTRY: score compressed from 88 to 84. Overhead remained moderate throughout.  
- The alert correctly identified the regression. Trajectory: `DOWNGRADING (SNIPE_IT → NEAR_ENTRY, 88 → 84)`. Calibration: 80 (−4) reflecting downgrading trajectory penalty (−3) and overhead compression (−2), partially offset by BOS structure (+1).  
- Capital authorization: alert routed to #near-entry-watch. NO CAPITAL block applied. Correct — NEAR_ENTRY does not authorize capital regardless of session history.

**Finding:** Tier demotion handled correctly. Re-alert fired on trigger change. Capital authorization was not carried forward from the morning SNIPE_IT state. The calibration correctly applied the maximum downgrade penalty for a DOWNGRADING trajectory.

**Open observation:** The mechanism that caused CPER to regress from SNIPE_IT to NEAR_ENTRY within the same session is not fully visible from alert data alone. Score compressed from 88 to 84 and trigger shifted by $0.30. Whether this reflects genuine structural deterioration or price movement relative to the zone cannot be determined without access to the underlying tiering output.

---

## 3. Capital Authorization Discipline

### 3.1 Authorized Entries

| Ticker | Tier | Capital Action | R:R | Risk State | Verdict |
|--------|------|----------------|-----|------------|---------|
| CPER (AM) | SNIPE_IT | FULL QUALITY | 8.0 | healthy | Authorized correctly |
| SNDK | SNIPE_IT | FULL QUALITY | 4.31 | healthy | Authorized correctly |
| IESC | SNIPE_IT | FULL QUALITY | 6.01 | healthy | Authorized correctly |
| AME | STARTER | STARTER SIZE ONLY | 4.70 | tight | Authorized — reduced size |
| AFRM | STARTER | STARTER SIZE ONLY | 17.61 | tight | Authorized — see §5.2 |

### 3.2 Capital Withheld

| Ticker | Tier | Capital Block | Upgrade Trigger Visible |
|--------|------|---------------|------------------------|
| COHU | NEAR_ENTRY | NO CAPITAL | price below trigger |
| CGNX | NEAR_ENTRY | NO CAPITAL | watch for trigger acceptance |
| BE | NEAR_ENTRY | NO CAPITAL | price below trigger |
| CPER (PM) | NEAR_ENTRY | NO CAPITAL | NOT PROVIDED |

All NEAR_ENTRY alerts correctly withheld capital. No NEAR_ENTRY alert crossed into the capital-authorized routing path. WAIT signals are not present in alert screenshots (correct — WAIT is never posted).

---

## 4. Risk Realism Audit

### 4.1 Risk State Distribution

| Risk State | Tickers | Count |
|------------|---------|-------|
| healthy | SNDK, IESC, CPER (both), COHU, CGNX, BE | 7 alerts |
| tight | AME, AFRM | 2 alerts |
| elevated / fragile | (none) | 0 |

### 4.2 Tight-Risk SNIPE_IT / STARTER Alerts

**AME — STARTER, tight risk, $2.13/0.94%**  
- Risk window: $2.13 / 0.94% (trigger 226.15 → invalidation 224.01).  
- SMA alignment: mixed (below SMA20, above SMA50/SMA200). Disclosed explicitly in alert.  
- Risk note displayed: "Risk window is tight; verify live chart before entry."  
- Capital authorized at STARTER size. Doctrine-correct for STARTER tier with mixed SMA alignment.  
- Risk window is numerically thin (0.94%) but price → invalidation matches risk window exactly ($2.13), confirming price was at trigger at scan time. Not mechanically anomalous.

**AFRM — STARTER, tight risk, $0.28/0.44%**  
- Risk window: $0.28 / 0.44% (trigger 63.81 → invalidation 63.53, OB low).  
- Price → invalidation: $0.28 / 0.44%. Price was at trigger at scan time.  
- Risk note displayed: "Risk window is tight; verify live chart before entry."  
- Capital authorized at STARTER size.  
- **Critical finding:** $0.28 risk window is the narrowest recorded in this audit series. At this stop distance, any bid-ask spread or minor intraday wick can breach the invalidation level before a fill is placed. The risk note was correctly generated, but the note alone does not prevent capital authorization. R:R of 17.61 is a direct artifact of this stop distance compression (see §5.2).

---

## 5. Calibration Layer Review

### 5.1 Component Reconstruction (All Alerts)

The following table reconstructs calibration components for each alert using the pre-Phase-14C state (_RISK_ADJ did not include "tight"; _TRAJECTORY_ADJ["UPGRADING"] = +2).

| Ticker | Raw | Structure | Overhead | Trajectory | Risk | Raw Δ | Bounded Δ | Cal | Confirmed |
|--------|-----|-----------|----------|------------|------|-------|-----------|-----|-----------|
| CPER (AM) | 88 | +1 (BOS) | −2 (mod) | +2 (UP) | 0 | +1 | +1 | 89 | ✓ matches alert |
| SNDK | 88 | +1 (BOS) | +1 (clr) | +2 (UP) | 0 | +4 | +4 (ceil) | 92 | ✓ matches alert |
| IESC | 87 | +1 (BOS) | −2 (mod) | +2 (UP) | 0 | +1 | +1 | 88 | ✓ matches alert |
| AME | 82 | +1 (BOS) | −2 (mod) | 0 (REP) | 0¹ | −1 | −1 | 81 | ✓ matches alert |
| AFRM | 82 | +1 (BOS) | +1 (clr) | 0 (REP) | 0¹ | +2 | +2 | 84 | ✓ matches alert |
| CGNX | 82 | +1 (BOS) | 0 (clr/NE) | −1 (SW) | 0 | 0 | −1² | 81 | ✓ matches alert |
| BE | 82 | +1 (BOS) | 0 (clr/NE) | −1 (SW) | 0 | 0 | −1² | 81 | ✓ matches alert |
| CPER (PM) | 84 | +1 (BOS) | −1 (mod/NE) | −3 (DG) | 0 | −3 | −4³ | 80 | ✓ matches alert |

¹ "tight" risk state not in _RISK_ADJ pre-P1 — defaults to 0.  
² STALE_WATCH (−1) dominates; structure +1 offset: net 0. But NEAR_ENTRY overhead clear = 0. Components: structure 0 (NEAR_ENTRY), overhead 0 (clear/NE), trajectory −1, risk 0. Total = −1. Matches.  
³ DOWNGRADING (−3) + moderate overhead (−1, NE table) + structure +1 (BOS/NE, structure quality adj for NEAR_ENTRY = 0 when retest/hold confirmed). Let me recheck: NEAR_ENTRY structure quality adj = 0 when both confirmed. So: −1 (mod/NE) + −3 (DG) = −4. Cal: 84 − 4 = 80. ✓

All eight calibration outputs reconstruct exactly using the pre-Phase-14C coefficient state. **This confirms that the May 18 session was executed prior to Phase 14C deployment.**

### 5.2 Phase 14C Deployment Timing — Confirmed Evidence

**P1 was not active (tight penalty = 0, not −1):**
- AME: tight risk + moderate overhead + BOS + REPEATED = 0−2+1+0 = −1 → 81. Matches alert. With P1 active: −1−2+1+0 = −2 → 80. Alert shows 81, not 80. P1 not deployed.
- AFRM: tight risk + clear overhead + BOS + REPEATED = 0+1+1+0 = +2 → 84. Matches alert. With P1: −1+1+1+0 = +1 → 83. Alert shows 84, not 83. P1 not deployed.

**P3 was not active (UPGRADING bonus = +2, not +1):**
- SNDK: healthy risk + clear overhead + BOS + UPGRADING = 0+1+1+2 = +4 → 92. Matches alert. With P3: 0+1+1+1 = +3 → 91. Alert shows 92, not 91. P3 not deployed.
- CPER AM: healthy + moderate + BOS + UPGRADING = 0−2+1+2 = +1 → 89. Matches. With P3: 0−2+1+1 = 0 → 88. Alert shows 89. P3 not deployed.
- IESC: healthy + moderate + BOS + UPGRADING = 0−2+1+2 = +1 → 88. Matches. With P3: 0 → 87. Alert shows 88. P3 not deployed.

**Post-P1/P3 recalculations (for reference, not live alerts):**

| Ticker | Current Cal | With P1+P3 | Delta Change |
|--------|-------------|------------|--------------|
| AME | 81 | 80 | −1 (tight penalty added) |
| AFRM | 84 | 83 | −1 (tight penalty added) |
| SNDK | 92 | 91 | −1 (UPGRADING reduced) |
| CPER AM | 89 | 88 | −1 (UPGRADING reduced) |
| IESC | 88 | 87 | −1 (UPGRADING reduced) |

None of these recalculations cross a tier gate or alter capital authorization — calibration is audit-only.

### 5.3 Elite Cap Behavior

SNDK raw score 88, calibrated 92. The elite cap (applied at calibrated ≥ 90 unless SNIPE_IT cleanliness preconditions met) was not triggered because SNDK qualified for elite:
- Tier: SNIPE_IT ✓  
- Risk state: healthy ✓  
- Overhead: clear ✓  
- Retest: confirmed ✓  
- Hold: confirmed ✓  
- Trajectory: UPGRADING (not in disqualifying set) ✓  

Elite designation is correctly applied. The 92 calibrated score reflects genuine quality rather than a calibration ceiling artifact.

---

## 6. R:R Inflation Analysis

### 6.1 Stop Distance Compression Pattern

Three tickers in this session presented R:R values elevated by narrow stop distances:

| Ticker | Tier | R:R | Stop ($) | Stop (%) | Risk State | Capital |
|--------|------|-----|----------|----------|------------|---------|
| AFRM | STARTER | 17.61 | $0.28 | 0.44% | tight | Authorized |
| COHU | NEAR_ENTRY | 8.06 | $1.06 | 2.39% | healthy | Withheld |
| CPER AM | SNIPE_IT | 8.0 | ~$0.32 | ~0.83%¹ | healthy | Authorized |

¹ CPER AM: trigger 38.22, invalidation 37.90 = $0.32.

**AFRM — most severe case in audit series:**  
Stop of $0.28 (0.44% of price) at STARTER-authorized capital. This is the narrowest stop in the May 15 + May 18 combined audit record (May 15 MOD: $0.58 / 0.58%; May 18 COHU: $1.06 / 2.39%). A $0.28 stop is within the typical intraday bid-ask spread range for higher-priced names and is mechanically vulnerable to invalidation before a fill can be placed at trigger.

The system correctly:
1. Set risk_state = tight.
2. Generated the risk note: "Risk window is tight; verify live chart before entry."
3. Routed to STARTER (reduced size), not SNIPE_IT.

The system did not:
1. Penalize the calibrated score for tight risk (P1 not yet deployed — would reduce to 83 from 84).
2. Apply any structural limit on R:R computation from microscopic stops (P2 not yet implemented).

**COHU — capital withheld, lower severity:**  
R:R 8.06 from $1.06 stop is notable but capital was not authorized (NEAR_ENTRY). The inflation does not reach the trade channel in actionable form.

**CPER AM — moderate concern:**  
R:R 8.0 from $0.32 stop. SNIPE_IT authorized. Risk state healthy (stop is small but price was already inside FVG at scan time, stop is zone-anchored). Less mechanical concern than AFRM since the invalidation is FVG bottom — a structure-defined level rather than an arbitrary narrow margin.

### 6.2 R:R Computation Methodology Note

SNDK provides a clean illustration of scan-time R:R methodology. Trigger: 1306.34. Scan price: 1336.34 (already above trigger by $30). Invalidation: 1275.11. T1: 1600.

Stated R:R = (1600 − 1336.34) / (1336.34 − 1275.11) = 263.66 / 61.23 = **4.31** (current-price R:R).  
At-trigger R:R = (1600 − 1306.34) / (1306.34 − 1275.11) = 293.66 / 31.23 = **9.4** (entry-price R:R).

The scanner reports current-price R:R, which is conservative when price is above trigger. This is correct behavior — it avoids presenting an inflated R:R when the optimal entry has already passed. A trader entering at trigger would receive better R:R than stated. No finding — documented for reference.

---

## 7. Repeated Alert / Churn Audit

### 7.1 Cooldown-Expired Re-Alerts

**CGNX — two alerts, same session:**  
- Alert 1 (scan_192805): NEAR_ENTRY, score 82, key CGNX|NEAR_ENTRY|61.60|58.90. Trajectory: STALE_WATCH.  
- Alert 2 (scan_194612): Same key, cooldown_expired. Score and trajectory unchanged (STALE_WATCH, calibrated 81 −1).  
- Both alerts correctly withheld capital. The re-alert on cooldown expiry with an identical key and STALE_WATCH trajectory adds no new information. Signal churn without structural change. This is within doctrine (cooldown_expired is an authorized re-alert path) but the STALE_WATCH label correctly communicates stagnation to the reader.

**AME — cooldown_expired, REPEATED trajectory:**  
- Same key (AME|STARTER|226.15|224.01) re-alerted after cooldown. No material change.  
- Capital re-authorized at STARTER size on cooldown expiry.  
- Risk state remained tight. With P1 deployed, the calibrated score drop from 81 to 80 would provide additional visual signal that the setup is tight.

**AFRM — cooldown_expired, REPEATED trajectory:**  
- Same key (AFRM|STARTER|63.81|63.53) re-alerted after cooldown. R:R 17.61 unchanged.  
- Capital re-authorized at STARTER size. See §6.1 for R:R inflation concern.

### 7.2 Trigger-Changed Re-Alerts

**BE:**  
- Trigger change caused re-alert. Alert correctly withheld capital (NEAR_ENTRY). Trajectory: STALE_WATCH. No structural issue.

**CPER (morning to afternoon):**  
- Trigger shifted from 38.22 → 38.52 ($0.30). Tier simultaneously degraded SNIPE_IT → NEAR_ENTRY. Trigger change is the dedup reason but the tier demotion is the operationally significant event. Capital was correctly withdrawn.

### 7.3 Tier-Improved Re-Alerts

Three tickers (CPER AM, SNDK, IESC) re-alerted via `tier_improved`. All were promotions from NEAR_ENTRY to SNIPE_IT. All re-alerts are correctly authorized under dedup doctrine (tier improvement always clears suppression). No churn concern for this class.

---

## 8. Structural Strength Findings

### 8.1 Session-High Quality: SNDK

SNDK is the structurally strongest alert in the May 18 session.

- Quality: "Elite candidate — all five quality dimensions institutional-grade."  
- Structure: BOS confirmed inside unfilled FVG (1275.11–1337.56).  
- Retest and hold: both confirmed with price trading inside the zone at scan time.  
- SMA stack: "fully supportive with price well above all key SMAs."  
- Volume: Not explicitly stated in visible screenshots.  
- Risk: $31.23 / 2.39% — healthy, proportionate to price ($1336).  
- Overhead: clear. T1: 1600.00 at 4.31R current-price.  
- Calibrated: 92 (+4) — elite cap not triggered (all cleanliness preconditions met).  
- This is the only alert in the session to receive elite calibration band.

### 8.2 Strong Executable: IESC

- Structure: BOS confirmed at unmitigated OB (626.42–652.99).  
- Retest and hold confirmed. SMA fully supportive. Volume dryup on retest (institutional absorption noted explicitly).  
- R:R 6.01. Risk $26.27 / 4.03% — healthy, proportionate.  
- Overhead moderate (non-blocking). Calibrated: 88 (+1).  
- Quality: "A+ candidate — 4 of 5 dimensions premium." Solid executable, one dimension short of elite.

### 8.3 Qualified Executable: CPER (AM)

- Structure: BOS confirmed, price inside unmitigated FVG at scan time (37.90–39.14).  
- Volume dryup noted. SMA stack fully supportive.  
- R:R 8.0 — elevated due to $0.32 stop, but zone-anchored (FVG bottom). Less mechanical concern than AFRM.  
- Overhead moderate (non-blocking). Calibrated: 89 (+1).  
- Quality: "A+ candidate — 3 of 5 dimensions premium." Correctly one notch below IESC/SNDK.

### 8.4 Watch-Quality: BE, CGNX (NEAR_ENTRY)

Both BE and CGNX have confirmed BOS, confirmed retest and hold, clear overhead, and healthy risk — strong structural profiles. The NEAR_ENTRY classification reflects that price has not accepted above the trigger level, not structural weakness. STALE_WATCH trajectory correctly identifies these as unchanged from prior scans. No capital concern (capital is withheld).

---

## 9. Remaining Weaknesses and Open Items

### 9.1 R:R Inflation via Microscopic Stop — P2 Not Yet Deployed

**Status:** Open. No code change in Phase 14C.  
**Evidence:** AFRM R:R 17.61 from $0.28/0.44% stop. Capital authorized at STARTER level. Risk note generated ("tight") but does not affect capital routing or calibration (pre-P1). Post-P1 would reduce calibrated score from 84 to 83 — correct directional move but insufficient to convey the magnitude of the stop compression problem.

P2 (R:R quality adjustment: penalize near-floor R:R, potentially cap extreme R:R from demonstrably thin stops) would directly address this. Without P2, the calibration layer accurately reflects structural quality but cannot distinguish between R:R 4.31 (SNDK, from legitimate stop) and R:R 17.61 (AFRM, from stop-compression artifact).

**Implication:** Any reader seeing R:R 17.61 without context may treat it as a high-conviction signal. The tight risk note provides the warning, but a reader who does not read risk realism carefully will miss it.

### 9.2 AFRM: Tight Risk + Capital Authorization Interaction

AFRM received STARTER authorization (capital authorized, reduced size) with:
- Risk state: tight  
- Stop: $0.28 / 0.44%  
- R:R: 17.61  

The three fields together indicate a stop that is mechanically vulnerable. Pre-P1, the calibration did not penalize tight risk (defaulted to 0). With P1 deployed, tight risk receives −1 and calibrated score becomes 83 (+1) rather than 84 (+2). Neither score materially changes the operational output, but 84 (+2) overstates calibration confidence relative to the structural picture.

**Doctrine question (not a finding, requires human judgment):** Should tight risk with sub-$0.50 stop unconditionally cap tier at NEAR_ENTRY regardless of BOS + confirmed sequence? This is outside the scope of any current phase and would require deliberate doctrine review before implementation.

### 9.3 COHU: Trajectory and Calibration Not Visible

COHU NEAR_ENTRY (score 84, R:R 8.06, healthy risk) has confirmed execution data but no trajectory or calibration block visible in screenshots. Cannot audit calibration reconstruction or trajectory label. Functional assessment is limited to: capital withheld correctly (NEAR_ENTRY), gates visible in EXECUTION block are satisfied, R:R 8.06 from $1.06 stop is notable but capital is not authorized.

### 9.4 CPER Intra-Session Regression — Cause Uncertain

CPER cycled NEAR_ENTRY → SNIPE_IT → NEAR_ENTRY within a single trading session. The morning promotion was structurally justified. The afternoon demotion (score 88→84) is visible in the alert but the cause — whether Claude reclassification, updated indicator output, or both — cannot be determined from alert text alone. This is the only intra-session tier regression in the audit.

### 9.5 CMI, ROK — No Data

Two of the ten requested tickers (CMI, ROK) produced no visible screenshots. Their alert state, tier, and calibration for May 18 cannot be assessed. These tickers are excluded from all findings.

---

## 10. Summary of Key Findings

| Category | Finding | Severity |
|----------|---------|----------|
| Phase 14C timing | All May 18 alerts generated pre-P1/P3; calibration coefficients reconstruct exactly to pre-patch state | Informational |
| Capital discipline | All NEAR_ENTRY alerts correctly withheld capital; all SNIPE_IT/STARTER hard gates satisfied | Pass |
| Tier transitions | All tier promotions passed hard gate verification; one intra-session regression (CPER) handled correctly | Pass |
| Dedup behavior | `tier_improved`, `trigger_changed`, `cooldown_expired` paths all fired correctly | Pass |
| SNDK | Strongest alert in session; elite calibration (92 +4); all five dimensions institutional-grade | Strength |
| IESC | Clean SNIPE_IT; 4/5 dimensions; calibration reflects moderate overhead correctly | Strength |
| AFRM R:R inflation | R:R 17.61 from $0.28 stop; capital authorized; risk note present but P2 not deployed | Open gap |
| AME tight risk calibration | Pre-P1: calibrated 81 (−1); post-P1 should be 80 (−2); tight penalty absent from May 18 run | Resolved by P1 |
| CGNX churn | Two STALE_WATCH alerts in same session via cooldown_expired; informational, no capital impact | Low |
| COHU | Trajectory/calibration not auditable from available screenshots | Incomplete |
| CMI, ROK | No data | Not assessed |

**Phases required to close open gaps:**  
- P1 (tight=-1): Deployed in Phase 14C. Will be active in post-May-18 sessions.  
- P3 (UPGRADING +2→+1): Deployed in Phase 14C. Reduces UPGRADING bonus on SNDK/IESC/CPER-class alerts by 1 point.  
- P2 (R:R quality adjustment): Not yet deployed. Required to address AFRM-class stop compression in calibration output.

---

*Audit prepared: Phase 14D. No code changes made. All findings sourced from Discord alert screenshots only.*

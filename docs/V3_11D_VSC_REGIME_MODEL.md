# V3.11D — VSC Regime Model

Status: **VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE — NO PRODUCTION
INTEGRATION AUTHORIZED.** Research/validation only. No eligibility
change, no MC2/kernel change, no other regimes, no futures, no product
changes. Coverage unchanged 3678/9644.

## 1. Prior review (Q7 shadows)

- **V3.2H-VSC: REJECTED** (duration slope 2.61 vs [0.5,1.5]; pace MAE
  10.38/11.58 s vs ≤10.0 s gate; post-exit/gaps passed anyway).
- **V3.2F-VSC: DEFERRED** (evidence pack: +19.6 s median, 55 episodes
  p50 1 lap; mechanism unestimated).
- D differs materially: conditional dynamics GIVEN causally-known
  intervals (no predictive-duration component); transition-lap
  decontamination (entry always dropped; exit dropped on direct
  withdrawal); ratio-form pace vs H-comparable absolute gates;
  duration re-tested as integration blocker, not fitted.

## 2. Physics & contract

VSC support = global delta-time pace (REQUIRED), gap preservation
(REQUIRED claim), frozen order (REQUIRED), VSC pit-loss (dropped:
INSUFFICIENT — fail closed where pits relevant), tyre/retirement
unchanged (no evidence for change), immediate green return on
withdrawal (REQUIRED), duration (OUT OF SCOPE for dynamics;
blocking for integration). Interval contract: tokens 6/7, lap-end
equality, future activation/withdrawal invisible, pre-first UNKNOWN.

## 3. Episodes & quality

82 VSC intervals → 29 usable (16 calibration ≤2021 / 13 validation
≥2022); excluded: 46 single-lap (no full VSC lap), 10→SC, 1→red,
2 truncated. Strict-interior subset 11. Quality rule v2 is
token-semantic (code 7 marks withdrawal onset), fixed before scoring.

## 4. Empirical findings (Q1–Q11)

1. Usable: 29/82 (quality gate above).
2. Pace: ACTIVE/PRE ratio median **1.272** (p25–75 1.22–1.34);
   race medians 1.21–1.37; absolute offset +24.6 s (decontaminated,
   vs H +19.6 s with partials).
3. Global ratio adequate: validation ratio median 1.315 vs R_cal
   1.272; race spread narrow; driver-specific params refused
   (minimality; H's ~9 s sd is noise floor, not structure).
4. Gaps: steady ACTIVE change median 0.66 s full-sample (validation
   slice 1.06 s on ~20 pairs — small-N unstable, see verdict);
   entry transient 1.06–1.35 s (activation chaos, not gated).
5. Spread: full-sample ratio ≈1.01 (H ≈1.1 confirmed); validation
   episode-macro 1.42 on ~2–3 episodes (unstable).
6. Order: steady 3.5% change rate (frozen modulo channel noise;
   green baseline flicker is 14.4%); entry transient 43.7%
   (incident/activation chaos, not gated).
7. Pit loss: in-lap marginal ≈ −0.1 s (n=73, free-stop direction);
   out-lap unmeasurable (n=7).
8. Pit model: INSUFFICIENT — V3 excluded; fail-closed where VSC
   windows contain pit events.
9. Tyre: NO MODIFICATION (MC2 age is lap-based;
   `expected_lap_time_s` has no pace-coupled term; stints continue
   through VSC in D9).
10. Retirement: PRESERVE_FROZEN (27 vs 9 disappearances is
    incident-driven, not pace-hazard evidence; no MC2 hazard model
    exists to modify).
11. Withdrawal: POST−PRE median +0.1–0.3 s — immediate green return,
    no SC-like restart mechanics.

## 5. Candidates, protocol, validation (Q12–Q13)

V0 refuse (control); V1 global ratio; V2 V1+gap claim; V3 excluded
at protocol time. Protocol sha `fd710c68`, temporal split,
episode-macro + pooled, gates G1–G8 (no coverage gate), duration gate
(slope [0.5,1.5] + MAE ≤1 lap). Validation: R_cal 1.272; MAE **9.54 s**
pooled / 9.22 macro (G1 PASS — decontamination beats H by ~1 s);
G3/G5/G6/G7/G8 pass; G2 (1.06 vs 1.0) and G4 (1.42 vs [0.8,1.25])
fail on underpowered validation subsets while full-sample
descriptives pass the same thresholds. Duration: FAIL (confirms H;
median predictor unidentifiable, same DGP).

## 6. Decision (Q17)

**INSUFFICIENT_EVIDENCE.** Pace/order/withdrawal validate with good
N; gap/spread failures are small-N instability, not refutation
(full-sample passes; hard-refutation bounds untouched); pit-loss
unmodelled with fail-closed rule; duration independently blocks
integration. No production integration authorized; projected
eligibility NOT_APPLICABLE; 41 secondary-free VSC anchors stay
TRACK-blocked (11 in-episode anchors used for replay only).

## 7. Parity, replay, poison (Q14–Q16)

- GREEN parity: research module is stdlib-only, production diff
  empty, GREEN suites green; outputs unchanged where VSC inactive.
- RNG: zero stochastic futures in D (deterministic replay only);
  no streams created/consumed; GREEN RNG untouched.
- Fail-closed: VSC→SC/RED, RED→VSC, ambiguous, missing withdrawal,
  contradiction, pit-under-VSC all refuse (unit matrix pinned).
- Replay (HISTORICAL DYNAMICS VALIDATION, 6 rule-selected anchors):
  K+1 order agreement 0.56–1.0, degrading at K+2 — short-horizon
  freezing holds, drift accumulates; supports dynamics qualitatively.
- Poison: all future regime/timing/tyre/pit injections ignored;
  labels separated; boundaries explicit (</==/>T); no nearest
  transition. PASS.

## 8. Integration contract notes (Q18)

A later stage would need: VSC pace-ratio hook (isolated, GREEN
untouched), gap/order passthrough, green-return transition, pit
fail-closed,PLUS a calibrated duration/withdrawal solution (the
blocker) and a larger gap/spread validation sample. Remark:
`vsc_ending` anchors (12) need no duration (withdrawal observed)
— future micro-scope, not pursued here (post-hoc scoping refused).

## 9. Tests / guards / collection

- Focused `test_v3_11d_vsc_model.py`: 18/18.
- Regression green: A+B+C suites, RaceState/phase suites,
  presence/contract/parity/2N, 2J/2F/2H/2K, phase-6 freeze, MC2 batch,
  V3.8/V3.9/perf/V3.10 guards (pins 5250→5268 + D allowlist).
  Collection 5268. Pre-existing untouched:
  `test_v39_freeze_provenance_unchanged` (stale pin, fails clean).
  No Tier-1 (no runtime change), no frontend.
- P1–P20 all zero (tags; A/B/C bytes; eligibility/RaceState/MC2;
  GREEN-default; future/nearest; SC/yellow/red/wet models absent;
  no SC-compression assumption; no invented pit/tyre effects; GREEN
  and RNG unchanged; blockers preserved; coverage never a gate;
  0 futures; product untouched).

## 10. Deferred / next gate

SC research is NOT automatically justified by this result; given
duration blocks VSC integration and SC is F3 (harder), the honest
recommendation is: **review whether V3.11 should stop without
coverage expansion** vs funding a duration + larger-sample VSC
follow-up. Do not start SC, wet, integration, commit/tag/push
(A+B+C+D reviewable together).

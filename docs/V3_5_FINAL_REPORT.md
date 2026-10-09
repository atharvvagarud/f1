# V3.5 OUTCOME DISTRIBUTION — FINAL REPORT

Frozen scientific record for the V3.5 probabilistic race-outcome program.
Parent: `v3.4-ensemble` (`3cbd28470ffa211bd754d4262eb10d66d149bf00`).
Scientific card: `results/v3/v3_5_final_scientific_card.json`
(identity `8d3a8d2ec6aef5d4bb50306036e100b0db6c83386c19ec8f7ce07ae25714446d`).
Freeze record: `results/v3/v3_5_freeze.json`.

## Final verdict

V3.5G COMPLETE — V3.5 FROZEN (pending commit/tag steps in the G mission).
Logistic remains scientific champion; XGB_E remains a nonlinear research
candidate; no serving promotion.

## Scientific question

Can a nonlinear model improve on a frozen L2-Logistic control for
per-driver marginal cumulative finish-threshold probabilities
(p_win / p_podium / p_top5 / p_top10) under strict temporal discipline,
with 2025 held for a single previously-revealed out-of-time evaluation?

## Frozen parent

- Tag: `v3.4-ensemble`, commit `3cbd28470ffa211bd754d4262eb10d66d149bf00`.
- G entry verified HEAD == parent, nothing staged, working tree = V3.5A–F only.

## Stage ledger

| Stage | Verdict | Identity | 2025 contact | Role |
|---|---|---|---|---|
| A | COMPLETE | `15ca7c17…efab` | NONE | contract + landscape |
| B | COMPLETE | `e9ac34e5…5289` | NONE | dataset + targets + projection spec |
| C | COMPLETE | `9dfee182…603a` | NONE | baselines + harness |
| D | COMPLETE | `8d82448e…78ba` | NONE | screening; XGB diversity, HGB out |
| E | COMPLETE | proto `4adf3da3…e6`, recipe `b1d8ce5e…4c09` | NONE | refinement; frozen X2 recipe |
| F | COMPLETE | manifest `eab0da30…8e1`, record `a94ee34d…21a1b3` | EVALUATION_ONLY | single 2025 evaluation |

Provenance recomputation (G, independent): all identities exact match.
See `results/v3/v3_5g/provenance_audit.json`.

## Scientific identity

- Task: `ordered_cumulative_finish_thresholds`; thresholds 1/3/5/10.
- Features: ALL_84 + CORE_26 = 110 (`e054c6fb…4c89e`).
- Development: 2018–2024. Evaluation: 2025 (previously revealed).
- Control: V3.5 Logistic C=.01. Research candidate: XGB_E (X2).
- Calibration: TOP5_SIGMOID_ONLY. Transform: RAW → CALIBRATION → PAVA.
- Projection: `v3.5b-projection-v1`. Serving: NONE. MC2: SEPARATE.

## Target semantics

Outputs are PER-DRIVER MARGINAL PROBABILITIES. They are NOT a joint
finishing-order distribution, NOT field-normalized, NOT exact P1–P20
probabilities, NOT MC2 frequencies. Threshold-differenced bands
(P1, P2–P3, P4–P5, P6–P10, >P10) are diagnostics only.

## Dataset

149 dev races (2018–2024), 2979 outcomes; 2025: 24 races, 479 outcomes,
26692 states. Population `v3.5b-population-v1`, targets `v3.5b-target-v1`,
status `v3.5b-status-v1`. Identity `e9ac34e5…5289`.

## Feature contract

Frozen 110-arm (ALL_84_PLUS_V3_1_DYNAMICS_CORE), hash `e054c6fb…4c89e`.
A forbids new features; B–F reuse the frozen matrix.

## Temporal protocol

D1/D2/D3 temporal folds; `ProtectedHoldoutError` firewall; 2025 tripwire;
A–E never touch 2025; F evaluates once with no reselection.

## Baselines

Climatology, position persistence, grid, L2-Logistic control (C=0.01).
Control reproduced exactly across folds (RAW+PROJECTED <1e-12).

## Model screening

XGB: KEEP_DIVERSITY_CANDIDATE (pooled improvement, uncertain superiority,
CI spans zero, win-threshold weakness). HGB: REJECT_NO_IMPROVEMENT.
No blending (diversity diagnostics only).

## Controlled refinement

X0 anchor → X2 final (min_child_weight 10→15). Dev pooled
refined−Logistic: −0.00531, CI [−0.01034, −0.00079], 37/68 races, 8/12
threshold cells. Top1 regresses on D1/D3 means. Calibration history:
D1 not evaluable; D2/D3 admit top5-SIGMOID only → final rule
TOP5_SIGMOID_ONLY by X2 majority. No outer-validation reversal.

## Calibration

Top5 sigmoid legitimately frozen before 2025 (pooled D3-inner OOS fit).
On 2025 it regressed: Top5 LL +0.00174, Brier +0.00014, ECE +0.00486.
This is an out-of-time scientific result, NOT a protocol failure.
Official recipe unchanged; RAW Top5 reported as attribution only.

## Coherence

Equal-weight L2 isotonic PAVA projection. Final violations: 0
(p_win ≤ p_podium ≤ p_top5 ≤ p_top10 everywhere). XGB raw violation rate
0.077; pre-PAVA (post-calibration) 0.204; projection score effect
−0.00019 — PAVA is not rescuing catastrophic incoherence.

## Development evidence

(See card `development_evidence`.) Refined XGB beat Logistic pooled
(−0.00531, CI excludes zero, 37/68 races, 8/12 cells) with D1/D3 top1
regression and late-race advantage — the basis for carrying X2 to F,
distinct from the 2025 out-of-time evidence below.

## Previously revealed out-of-time evaluation

Single F evaluation: frozen recipes fit on 2018–2024 once, predict 2025
once, report frozen metrics. Terminology is deliberately conservative
because 2025 results were previously revealed before V3.5.

## Primary result

- Logistic PROJECTED: 0.2050270403404582
- XGB RAW: 0.2014019593892697
- XGB calibrated-pre-PAVA: 0.2018361232732994
- XGB FINAL PROJECTED: 0.2016424811805443
- Final XGB − Logistic: −0.0033845591599139246 (point-estimate improvement)

## Threshold-specific result

- Top1: +0.003803 (REGRESSES)
- Top3: +0.001519 (REGRESSES)
- Top5: −0.008262 (IMPROVES)
- Top10: −0.010599 (IMPROVES)
- Improvement is NOT broad across thresholds (2/4).

## Top1 finding

Top1 development weakness persists: 2025 delta +0.003803, 10 improved /
14 worsened. This alone blocks any GENERALIZES disposition.

## Probability quality

Brier: XGB worse in 2 cells (top1, top3); ECE: XGB worse in 1 cell (top5).
No material wholesale degradation, but no clean sweep either.

## Calibration transfer

CALIBRATION_REGRESSES (frozen Top5 sigmoid does not transfer to 2025).

## Race-level uncertainty

15/24 races improved, 9 worsened. Race bootstrap (B=2000, seed=42):
[−0.010514, +0.004273] — spans zero. V3.5 does NOT prove XGB superiority.

## Stage behavior

EARLY +0.001544 (regresses), MID +0.005587 (regresses),
LATE −0.017597 (improves strongly). Late-race nonlinear advantage transfers.

## Development → 2025 transfer

MIXED_TRANSFER: same primary sign (smaller magnitude), threshold
consistency narrows (dev 8/12 → 2025 2/4), top1 weakness persists,
calibration regresses, late advantage transfers.

## Final model status

- SCIENTIFIC CHAMPION: LOGISTIC_CONTROL
- NONLINEAR RESEARCH CANDIDATE: XGB_E
- SERVING PROMOTION: NONE

## Relationship to V3.1B

V3.1B remains the established winner-prediction lineage; V3.5 does not
replace it. V3.5 Logistic Top1 was machine-precision aligned with V3.1B
OOF in C, but V3.5's task is broader (Top1/Top3/Top5/Top10). The result
supports keeping the strong Logistic winner lineage while recognizing
nonlinear signal for broader outcomes. No runtime routing introduced.

## Relationship to MC2

V3.5 outputs learned per-driver marginal probabilities; MC2 outputs
stochastic mutually-exclusive joint future simulation frequencies. They
remain separate. Do not normalize, average, or fuse. V3.8 owns later
Model × Simulation consensus/fusion.

## Serving status

NONE. No promotion, no blend/stack, no routing changes.

## Scientific conclusion

The frozen nonlinear XGBoost outcome model improved the 2025 point
estimate for the aggregate four-threshold race-macro log-loss task,
driven by Top-5, Top-10, and late-race states. The race-level bootstrap
interval spans zero, Top-1 and Top-3 regress, and the frozen Top-5 sigmoid
calibration does not transfer. Therefore the evidence is mixed rather
than proof of superiority. Logistic remains the scientific champion;
XGBoost remains a nonlinear research candidate and is not promoted
to serving.

## Limitations

Top1/Top3 regress; calibration regresses; CI spans zero (n=24);
EARLY/MID regress; fixed-20 inexact (2024-r03-R, 19 drivers);
24-race evaluation is inherently noisy.

## Reproducibility

Determinism verified bit-exact (F determinism audit); logical prediction
identities `e6651d68…` (Logistic) and `1d21dca1…` (XGB); G independently
recomputed all primaries, thresholds, bootstrap, race counts, and stages
to machine precision from frozen parquet artifacts without refitting.

## Tests

V3.5A–F suites (172 tests) + G final-validation suite
(`tests/test_v3_5g_final_validation.py`) + full Tier-1 (see freeze record).

## Freeze provenance

Card identity `8d3a8d2e…4446d` (canonical sha256, identity key excluded).
Freeze record `results/v3/v3_5_freeze.json` (deterministic pre-commit
identity per v3.4 precedent: no commit SHA in hashed content).
Tag `v3.5-outcome-distribution`. Push status NOT_PUSHED.

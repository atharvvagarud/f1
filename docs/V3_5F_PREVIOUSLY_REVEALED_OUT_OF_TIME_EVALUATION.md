# V3.5F PREVIOUSLY REVEALED OUT-OF-TIME OUTCOME EVALUATION

## Final verdict

V3.5F COMPLETE — MIXED OUT-OF-TIME EVIDENCE — READY FOR V3.5G

## Frozen parent

commit 3cbd28470ffa211bd754d4262eb10d66d149bf00, tag v3.4-ensemble. HEAD
verified equal; tree holds V3.5A–F only; nothing staged/committed/tagged/
pushed.

## Provenance

A `15ca7c17…efab`, B `e9ac34e5…57cc5289`, C `9dfee182…799c7603a`, D
`8d82448e…39dfdf78ba4`, E `4adf3da3…e6`, recipe `b1d8ce5e…4c09`, manifest
`eab0da30…3d8e1`, execution record `a94ee34d…c21a` — all recomputed full
identities match. E verdict verified: FINALIST FROZEN — READY FOR V3.5F.

## Evaluation terminology

PREVIOUSLY REVEALED OUT-OF-TIME OUTCOME EVALUATION. 2025 is not called
pristine/untouched/never-seen. Narrower allowed claim: all V3.5 model,
hyperparameter, calibration, projection, and finalist selection used no
V3.5 2025 outcome evidence.

## Frozen recipe

XGB X2 (lr 0.03, depth 3, mcw 15, n300 + frozen fixed params), four
independent binary models, top5-SIGMOID only, RAW→cal→PAVA order,
v3.5b-projection-v1. Logistic control C=0.01/L2/lbfgs/1000/None/42.
Both verified byte-identical to frozen artifacts before contact.

## 2025 firewall opening

Parts A–C passed first (entry safety, graphify, execution record frozen);
then 2025_CONTACT=EVALUATION_ONLY, first contact = 2025 D9 label read.
No exploratory 2025 analysis preceded the frozen pipeline.

## 2025 dataset

26,692 states, 479 driver-race outcomes, 24 races. Frozen B contract:
status policy, population, unclassified-tail/DNS semantics, threshold
order — all enforced with nesting assertions.

## Training population

2018–2024 only (162,728 states). No 2025 row in preprocessing, Logistic,
XGB, or calibrator fits.

## Logistic control

Final fit on 2018–2024, RAW → PAVA, no calibration (none frozen for
control). PROJECTED primary 0.205027.

## XGBoost finalist

Exact X2 recipe, four binary models on 2018–2024, no 2025 validation.
RAW primary 0.201402.

## Calibration

Top-5 SIGMOID refit on pooled D3-inner OOS history (I1+I2+I3, val
2021/2022/2023; 71,757 states, 19,588 positives; coef/intercept finite,
positive). No 2025 labels. Calibrated-pre-PAVA primary 0.201836.

## Prediction identities

`logistic_predictions_2025.parquet` + `xgb_predictions_2025.parquet`
under data/v3/v3_5f/, with state/race/driver/season, targets, RAW/CAL/
PROJ columns; byte + logical identities recorded.

## Primary result

XGB FINAL PROJECTED 0.201642 vs LOGISTIC PROJECTED 0.205027:
delta −0.003385 (lower better).

## Transformation attribution

RAW 0.201402 → CALIBRATED_PRE_PAVA 0.201836 (calibration effect +0.000434)
→ PROJECTED 0.201642 (projection effect −0.000194). Transformations do
not obscure the model: underlying XGB RAW already beats control.

## Threshold-specific results

top1 +0.003803 (regresses), top3 +0.001519 (regresses), top5 −0.008262,
top10 −0.010599. Advantage concentrates in top5/top10.

## Top1 audit

LOAD-BEARING: Logistic 0.063395 vs XGB 0.067198; 10 improved / 14
worsened; mean +0.003803, median +0.003841. Classification:
WEAKNESS_PERSISTS (≥ attenuation bound 0.003134). Not buried: this alone
blocks GENERALIZES.

## Top3 / Top5 / Top10

Podium slightly regresses; development nonlinear advantage transfers
through top5 and top10, not broadly. No threshold tuning performed.

## Probability quality

Per-threshold Brier/ECE/state-pooled in probability_quality.json.
Secondary metrics support but do not override the primary.

## Calibration transfer

Top5 RAW 0.218802 → calibrated 0.220539 (delta +0.001737, Brier +0.000135,
ECE +0.004863): CALIBRATION_REGRESSES. Recipe stays frozen per the
no-reselection rule.

## Coherence transfer

RAW violations: Logistic 9.71%, XGB 7.70% (below ~13% dev rate);
pre-PAVA (post-calibration) 20.38% with tiny mean adjustment (3.1e-4,
max 0.13). Final projected violation rate 0. Changed rate alone is not
failure; quality is not materially compromised.

## Race-level evidence

24 races: mean −0.003385, median −0.010907, 15 improved / 9 worsened.

## Bootstrap

Race unit, B=2000, seed=42, 95% CI: mean −0.003385, [−0.010514, +0.004273].
Spans zero (n=24).

## Stage analysis

EARLY +0.001544, MID +0.005587, LATE −0.017597 (top10 −0.03573, top5
−0.02932): LATE_ADVANTAGE_TRANSFERS. No tuning.

## Development → 2025 transfer

MIXED_TRANSFER (primary improves, CI spans zero). Magnitude similar
(−0.0034 vs dev pooled −0.0053). Threshold breadth narrows (2/4 vs 8/12
cells). Top1 persists; calibration regresses; coherence comparable;
LATE transfers.

## Final disposition

OUTCOME_XGB_MIXED_OUT_OF_TIME (frozen ordered definitions: primary<0 but
CI spans zero, only 2/4 thresholds, top1 regresses).

## Champion status

LOGISTIC_CONTROL retains SCIENTIFIC CHAMPION; XGB is NONLINEAR RESEARCH
CANDIDATE with documented top5/top10/LATE advantage. No serving promotion.

## No-reselection confirmation

Confirmed: no config, calibration, projection, feature, or family change
after 2025 contact. Poor cells are scientific results.

## Independent recomputation

Minimal numpy-only path reproduces primary, all threshold LLs, top1,
Brier, ECE, calibration effect, coherence, race deltas, bootstrap, and
stage deltas at 1e-9/1e-12. all_match=true. (This pass caught and fixed
one real bug: control primary briefly used RAW instead of PROJECTED.)

## Determinism

Prediction generation re-run without refitting: bit-exact
(max abs diff 0.0), logical identity match.

## Tests

tests/test_v3_5f_evaluation.py (33 checks). E/D/C/B/A + final-fit/
calibration/metrics/aggregation/temporal suites per policy; full Tier-1
deferred to V3.5G.

## Known limitations

Top1/top3 regress; calibration regresses (frozen); n=24 → wide CI;
EARLY/MID slightly positive; single-season evaluation.

## V3.5G recommendation

Final validation/freeze with full Tier-1 (including the V3.4 sentinel);
carry Logistic champion + XGB research candidate; no reselection. Do not
start G in this task.

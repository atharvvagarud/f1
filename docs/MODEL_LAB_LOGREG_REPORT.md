# Model Lab LogReg Reference Report (M3)

**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

The M3 Logistic Regression reference is the first candidate ML model: one fixed, untuned specification evaluated through the exact M2 canonical path. No tuning, no resampling, no post-hoc calibration, no 2025 access. Every value below traces to a stored experiment result (task `winner`, protocol v1, matrix d2ee966c18d2…).

## 1. Fixed specification (chosen before observing validation)

- estimator: LogisticRegression (penalty=l2 (sklearn default, not passed explicitly), C=1.0, solver=lbfgs, max_iter=1000, class_weight=None, random_state=42)
- task: winner; feature set: ALL_84 (frozen full 84-feature surface); seed: 42
- training weighting: state_equal (no resampling, no class rebalancing); tuning: none (fixed reference specification)
- probability semantic: INDEPENDENT_BINARY (per-driver P(win); never normalized across drivers)
- calibration fitted: none (raw probabilities evaluated); sklearn: 1.8.0

## 2. Preprocessing (fitted on TRAIN only)

- numeric: median (train-fitted); StandardScaler (train-fitted)
- boolean: most_frequent (train-fitted), cast to float, unscaled
- categorical: constant 'MISSING' (explicit structural sentinel); one-hot, train-fitted vocabulary, unknown=ignore
- native missing/categorical: False/False; fit scope: training only

| fold | train rows | train races | train prevalence | val rows | val races | features in | transformed dim |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 88123 | 81 | 0.055173 | 23577 | 22 | 84 | 106 |
| D2 | 111700 | 103 | 0.055121 | 24422 | 22 | 84 | 106 |
| D3 | 136122 | 125 | 0.054965 | 26606 | 24 | 84 | 106 |

Convergence warnings: D1=none; D2=none; D3=none

## 3. Headline probability quality (race-macro)

### log_loss (race-macro; lower is better)

| scope | D1 | D2 | D3 | mean | std | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| race_macro | 0.083045 | 0.038915 | 0.093433 | 0.071797 | 0.028947 | 0.038915 | 0.093433 |
| state_pooled | 0.083404 | 0.037786 | 0.097607 | 0.072932 | N/A | N/A | N/A |

### brier (race-macro; lower is better)

| scope | D1 | D2 | D3 | mean | std | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| race_macro | 0.024270 | 0.010258 | 0.027720 | 0.020749 | 0.009248 | 0.010258 | 0.027720 |
| state_pooled | 0.024590 | 0.009853 | 0.028805 | 0.021083 | N/A | N/A | N/A |

## 4. Discrimination (race-macro ROC-AUC / PR-AUC)

### roc_auc (race-macro; higher is better)

| D1 | D2 | D3 | mean | std | min | max |
| --- | --- | --- | --- | --- | --- | --- |
| 0.972581 | 0.995147 | 0.968246 | 0.978658 | 0.014443 | 0.968246 | 0.995147 |

### pr_auc (race-macro; higher is better)

| D1 | D2 | D3 | mean | std | min | max |
| --- | --- | --- | --- | --- | --- | --- |
| 0.723252 | 0.917487 | 0.721023 | 0.787254 | 0.112791 | 0.721023 | 0.917487 |

## 5. Calibration (ECE, 10 equal-width bins; raw probabilities)

| D1 | D2 | D3 | mean |
| --- | --- | --- | --- |
| 0.008397 | 0.009098 | 0.019215 | 0.012237 |

Reliability-bin detail is stored per experiment result; no calibrator was fitted.

## 6. Race-stage performance (race-macro)

### log_loss by stage

- D1: EARLY=0.102115 MID=0.079026 LATE=0.066778
- D2: EARLY=0.054428 MID=0.033674 LATE=0.028958
- D3: EARLY=0.116203 MID=0.090093 LATE=0.074061

### brier by stage

- D1: EARLY=0.030633 MID=0.023133 LATE=0.018843
- D2: EARLY=0.015487 MID=0.008392 LATE=0.007021
- D3: EARLY=0.032957 MID=0.026746 LATE=0.023393

## 7. Synchronized winner top-k (coverage-qualified)

| fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/degen) | min field |
| --- | --- | --- | --- | --- | --- |
| D1 | 0.677274 | 0.929090 | 23537 | 0/32/8 | 2 |
| D2 | 0.921184 | 0.997909 | 24386 | 0/25/11 | 2 |
| D3 | 0.719512 | 0.899014 | 26568 | 0/30/8 | 2 |

Top-3 on fields smaller than 3 is reported for completeness but is NOT genuine three-way discrimination (min observable field = 2).

## 8. M2 baseline comparison (from stored M2 artifacts)

| metric | baseline | fold | logreg | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| brier | CURRENT_LEADER | D1 | 0.024270 | 0.029318 | -0.005049 | BEATS |
| brier | CURRENT_LEADER | D2 | 0.010258 | 0.015613 | -0.005355 | BEATS |
| brier | CURRENT_LEADER | D3 | 0.027720 | 0.027562 | 0.000158 | DOES NOT BEAT |
| brier | CURRENT_LEADER | mean | 0.020749 | 0.024165 | -0.003415 | BEATS |
| expected_calibration_error | CLASS_PRIOR | D1 | 0.008397 | 0.000246 | 0.008150 | DOES NOT BEAT |
| expected_calibration_error | CLASS_PRIOR | D2 | 0.009098 | 0.000866 | 0.008231 | DOES NOT BEAT |
| expected_calibration_error | CLASS_PRIOR | D3 | 0.019215 | 0.000692 | 0.018523 | DOES NOT BEAT |
| expected_calibration_error | CLASS_PRIOR | mean | 0.012237 | 0.000602 | 0.011635 | DOES NOT BEAT |
| log_loss | CLASS_PRIOR | D1 | 0.083045 | 0.214068 | -0.131023 | BEATS |
| log_loss | CLASS_PRIOR | D2 | 0.038915 | 0.211307 | -0.172392 | BEATS |
| log_loss | CLASS_PRIOR | D3 | 0.093433 | 0.211340 | -0.117907 | BEATS |
| log_loss | CLASS_PRIOR | mean | 0.071797 | 0.212238 | -0.140441 | BEATS |
| pr_auc | CURRENT_LEADER | D1 | 0.723252 | 0.613725 | 0.109526 | BEATS |
| pr_auc | CURRENT_LEADER | D2 | 0.917487 | 0.762168 | 0.155319 | BEATS |
| pr_auc | CURRENT_LEADER | D3 | 0.721023 | 0.639359 | 0.081664 | BEATS |
| pr_auc | CURRENT_LEADER | mean | 0.787254 | 0.671751 | 0.115503 | BEATS |
| roc_auc | CURRENT_LEADER | D1 | 0.972581 | 0.860631 | 0.111951 | BEATS |
| roc_auc | CURRENT_LEADER | D2 | 0.995147 | 0.923215 | 0.071932 | BEATS |
| roc_auc | CURRENT_LEADER | D3 | 0.968246 | 0.863590 | 0.104657 | BEATS |
| roc_auc | CURRENT_LEADER | mean | 0.978658 | 0.882478 | 0.096180 | BEATS |
| winner_top1 | CURRENT_LEADER | D1 | 0.677274 | 0.730339 | -0.053065 | DOES NOT BEAT |
| winner_top1 | CURRENT_LEADER | D2 | 0.921184 | 0.861478 | 0.059706 | BEATS |
| winner_top1 | CURRENT_LEADER | D3 | 0.719512 | 0.732987 | -0.013475 | DOES NOT BEAT |
| winner_top1 | CURRENT_LEADER | mean | 0.772657 | 0.774935 | -0.002278 | DOES NOT BEAT |

No combined score is constructed; no significance is claimed.

## 9. Determinism, runtime, latency, memory

- determinism refit (D1): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- per-fold fit/predict wall time:
  - D1: fit=0.91 s predict_total=9.28 s batch_mean=0.0491 s throughput=480465.5 states/s
  - D2: fit=1.14 s predict_total=9.08 s batch_mean=0.0484 s throughput=504530.0 states/s
  - D3: fit=1.46 s predict_total=9.94 s batch_mean=0.0521 s throughput=511015.3 states/s
- full suite wall time: 62.1 s
- peak RSS: 1.93 GB

## 10. Artifacts

- logistic_regression/D1: `b5ca849d8ce17d53823a121b92699346c527aca898a3366c102cd489ad2053b3`
- logistic_regression/D2: `09282e26c2771512758f71380869a8db241dc082d8aebf7e430b7f335b741151`
- logistic_regression/D3: `13131c57dc1cead5c855ff33cfabf52c89fe5a6e0e91a43a1c9dd7852565bc06`

Suite summary: `/Users/tfatharva/f1-in-race-prediction_main/data/v2/model_lab/reports/logreg_reference_v1.json` (machine-readable; this document was rendered from it).
M2 baseline suite: schema v1 (values in §8 loaded from stored M2 artifacts).


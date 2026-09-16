# Model Lab Logistic Regression Boundary Resolution Report (M7)

## LOGISTIC REGRESSION DEVELOPMENT CONFIGURATION FREEZE

## OUTER DEVELOPMENT EVALUATION: 2022 / 2023 / 2024

## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED

## 1. Why M7 exists and the M6 boundary finding

M6 nested chronological tuning selected Logistic Regression with the LOWER grid-boundary value `C=0.03` on all three outer folds (D1/D2/D3), so the regularization optimum could not be distinguished from the search boundary. M7 is a ONE-TIME, narrow boundary resolution: it searches exactly `C in [0.003, 0.01, 0.03, 0.1]` with race-macro log loss only, reuses the exact M6 inner folds and preprocessing, and never reopens candidate selection, never tunes ExtraTrees, never starts calibration and never touches 2025.

## 2. Exact outer development folds

| fold | outer TRAIN | outer VALIDATE |
| --- | --- | --- |
| D1 | 2018–2021 | 2022 |
| D2 | 2018–2022 | 2023 |
| D3 | 2018–2023 | 2024 |

## 3. Exact inner folds (identical to M6)

| outer fold | inner fold | inner TRAIN | inner VALIDATE |
| --- | --- | --- | --- |
| D1 | D1-I1 | 2018–2020 | 2021 |
| D2 | D2-I1 | 2018–2020 | 2021 |
| D2 | D2-I2 | 2018–2021 | 2022 |
| D3 | D3-I1 | 2018–2020 | 2021 |
| D3 | D3-I2 | 2018–2021 | 2022 |
| D3 | D3-I3 | 2018–2022 | 2023 |

## 4. Exact C grid (one-time predeclared extension)

- C in [0.003, 0.01, 0.03, 0.1]
- 0.003 = LOWER_BOUNDARY (new); 0.01 = INTERIOR; 0.03 = INTERIOR / PREVIOUS_BOUNDARY (M6 control); 0.1 = UPPER_CONTROL
- no recursive expansion; no adaptive search; every C is fit on every inner fold

## 5. Exact planned fit budget

- inner estimator fits: 24 (4 C x 6 inner folds); inner preprocessor fits: 6 (one per inner fold, reused across C)
- outer selected refits: 3; determinism refits: 2
- total planned estimator fits: 29
- actual: inner estimator fits = 24, inner preprocessor fits = 6, outer selected refits = 3, determinism refits = 2

## 6. Tuning objective and tie-break (declared before execution)

- objective: race_macro_log_loss (simple mean over inner folds); lower is better
- tie-break tolerance: 1e-06 absolute on mean inner race-macro log loss
- among configurations whose mean is within tolerance of the best mean, prefer the smaller C (stronger L2 regularization / simpler configuration)

## 7. INNER RESULTS

### D1: selected `C=0.003` (boundary class LOWER_BOUNDARY; tie-break applied=False)

| C | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.003 | 0.094831 | 0.000000 | 0.094831 | 0.094831 | 0.000000 |
| C=0.01 | 0.095391 | 0.000000 | 0.095391 | 0.095391 | 0.000000 |
| C=0.03 | 0.097344 | 0.000000 | 0.097344 | 0.097344 | 0.000000 |
| C=0.1 | 0.099237 | 0.000000 | 0.099237 | 0.099237 | 0.000000 |

### D2: selected `C=0.01` (boundary class INTERIOR; tie-break applied=False)

| C | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.003 | 0.090365 | 0.006315 | 0.085900 | 0.094831 | 0.008931 |
| C=0.01 | 0.089503 | 0.008327 | 0.083615 | 0.095391 | 0.011776 |
| C=0.03 | 0.090238 | 0.010049 | 0.083132 | 0.097344 | 0.014211 |
| C=0.1 | 0.091157 | 0.011427 | 0.083077 | 0.099237 | 0.016160 |

### D3: selected `C=0.03` (boundary class INTERIOR_PREVIOUS_BOUNDARY; tie-break applied=False)

| C | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.003 | 0.076103 | 0.025103 | 0.047579 | 0.094831 | 0.047252 |
| C=0.01 | 0.073974 | 0.027533 | 0.042917 | 0.095391 | 0.052474 |
| C=0.03 | 0.073816 | 0.029317 | 0.040973 | 0.097344 | 0.056371 |
| C=0.1 | 0.073912 | 0.030943 | 0.039421 | 0.099237 | 0.059815 |

## 8. Selected C per outer fold and boundary classification

| outer fold | selected C | boundary class | new lower boundary? |
| --- | --- | --- | --- |
| D1 | `0.003` | LOWER_BOUNDARY | YES |
| D2 | `0.01` | INTERIOR | no |
| D3 | `0.03` | INTERIOR_PREVIOUS_BOUNDARY | no |

**Boundary conclusion: RESOLVED**

- REMAINS ACTIVE iff the new lower boundary is selected by at least 2 outer folds
- folds selecting the new lower boundary: ['D1']
- no further lower search was performed

## 9. DEVELOPMENT OUTER RESULTS

**OUTER DEVELOPMENT EVALUATION: 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

| fold | selected C | log loss | Brier | state-pooled log loss | state-pooled Brier | ROC-AUC | PR-AUC | ECE | top-1 | top-3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | `0.003` | 0.085900 | 0.025747 | 0.086171 | 0.025944 | 0.972789 | 0.707744 | 0.016282 | 0.633258 | 0.969240 |
| D2 | `0.01` | 0.042917 | 0.010951 | 0.041686 | 0.010481 | 0.994887 | 0.918308 | 0.012795 | 0.904986 | 0.997745 |
| D3 | `0.03` | 0.085306 | 0.025289 | 0.088744 | 0.026234 | 0.970865 | 0.764025 | 0.015380 | 0.750339 | 0.881926 |
| mean | — | 0.071374 | 0.020662 | 0.072200 | 0.020887 | 0.979514 | 0.796692 | 0.014819 | 0.762861 | 0.949637 |

Stage race-macro diagnostics (EARLY / MID / LATE) and synchronized top-k detail:

- D1: EARLY=0.098603 MID=0.084975 LATE=0.074412
- D2: EARLY=0.059206 MID=0.038768 LATE=0.031008
- D3: EARLY=0.107459 MID=0.082962 LATE=0.065473

| fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/degen) | min field | mean field |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 0.633258 | 0.969240 | 23537 | 0/32/8 | 2 | 19.78 |
| D2 | 0.904986 | 0.997745 | 24386 | 0/25/11 | 2 | 19.77 |
| D3 | 0.750339 | 0.881926 | 26568 | 0/30/8 | 2 | 19.77 |

## 10. Comparison vs M6 tuned LogReg C=0.03 (stored procedure result)

### log_loss (PRIMARY, lower)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.085900 | 0.083132 | 0.002768 | DOES NOT BEAT |
| D2 | 0.042917 | 0.040973 | 0.001944 | DOES NOT BEAT |
| D3 | 0.085306 | 0.085306 | 0.000000 | MATCHES |
| mean | 0.071374 | 0.069804 | 0.001571 | DOES NOT BEAT |

### brier (PRIMARY, lower)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.025747 | 0.024457 | 0.001291 | DOES NOT BEAT |
| D2 | 0.010951 | 0.010594 | 0.000357 | DOES NOT BEAT |
| D3 | 0.025289 | 0.025289 | 0.000000 | MATCHES |
| mean | 0.020662 | 0.020113 | 0.000549 | DOES NOT BEAT |

### roc_auc (SECONDARY, higher)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.972789 | 0.972872 | -0.000084 | MATCHES |
| D2 | 0.994887 | 0.994949 | -0.000062 | MATCHES |
| D3 | 0.970865 | 0.970865 | 0.000000 | MATCHES |
| mean | 0.979514 | 0.979562 | -0.000049 | MATCHES |

### pr_auc (SECONDARY, higher)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.707744 | 0.717549 | -0.009805 | DOES NOT BEAT |
| D2 | 0.918308 | 0.916329 | 0.001979 | BEATS |
| D3 | 0.764025 | 0.764025 | 0.000000 | MATCHES |
| mean | 0.796692 | 0.799301 | -0.002609 | DOES NOT BEAT |

### expected_calibration_error (SECONDARY, lower)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.016282 | 0.010432 | 0.005850 | DOES NOT BEAT |
| D2 | 0.012795 | 0.011628 | 0.001167 | DOES NOT BEAT |
| D3 | 0.015380 | 0.015380 | 0.000000 | MATCHES |
| mean | 0.014819 | 0.012480 | 0.002339 | DOES NOT BEAT |

### winner_top1 (SECONDARY, higher)

| fold | M7 | M6 C=0.03 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.633258 | 0.650593 | -0.017334 | DOES NOT BEAT |
| D2 | 0.904986 | 0.908226 | -0.003240 | DOES NOT BEAT |
| D3 | 0.750339 | 0.750339 | 0.000000 | MATCHES |
| mean | 0.762861 | 0.769719 | -0.006858 | DOES NOT BEAT |

## 11. Comparison vs M3 untuned LogReg C=1.0 (stored reference)

### log_loss (PRIMARY, lower)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.085900 | 0.083045 | 0.002855 | DOES NOT BEAT |
| D2 | 0.042917 | 0.038915 | 0.004002 | DOES NOT BEAT |
| D3 | 0.085306 | 0.093433 | -0.008127 | BEATS |
| mean | 0.071374 | 0.071797 | -0.000423 | BEATS |

### brier (PRIMARY, lower)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.025747 | 0.024270 | 0.001478 | DOES NOT BEAT |
| D2 | 0.010951 | 0.010258 | 0.000693 | DOES NOT BEAT |
| D3 | 0.025289 | 0.027720 | -0.002431 | BEATS |
| mean | 0.020662 | 0.020749 | -0.000087 | MATCHES |

### roc_auc (SECONDARY, higher)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.972789 | 0.972581 | 0.000207 | BEATS |
| D2 | 0.994887 | 0.995147 | -0.000260 | DOES NOT BEAT |
| D3 | 0.970865 | 0.968246 | 0.002619 | BEATS |
| mean | 0.979514 | 0.978658 | 0.000855 | BEATS |

### pr_auc (SECONDARY, higher)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.707744 | 0.723252 | -0.015508 | DOES NOT BEAT |
| D2 | 0.918308 | 0.917487 | 0.000821 | BEATS |
| D3 | 0.764025 | 0.721023 | 0.043002 | BEATS |
| mean | 0.796692 | 0.787254 | 0.009438 | BEATS |

### expected_calibration_error (SECONDARY, lower)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.016282 | 0.008397 | 0.007885 | DOES NOT BEAT |
| D2 | 0.012795 | 0.009098 | 0.003698 | DOES NOT BEAT |
| D3 | 0.015380 | 0.019215 | -0.003835 | BEATS |
| mean | 0.014819 | 0.012237 | 0.002582 | DOES NOT BEAT |

### winner_top1 (SECONDARY, higher)

| fold | M7 | M3 C=1.0 | diff | verdict |
| --- | --- | --- | --- | --- |
| D1 | 0.633258 | 0.677274 | -0.044016 | DOES NOT BEAT |
| D2 | 0.904986 | 0.921184 | -0.016198 | DOES NOT BEAT |
| D3 | 0.750339 | 0.719512 | 0.030827 | BEATS |
| mean | 0.762861 | 0.772657 | -0.009796 | DOES NOT BEAT |

- no combined weighted score is constructed; no significance is claimed

## 12. Inner-vs-outer translation

| fold | selected C | inner mean vs C=0.03 | outer log loss vs M6 C=0.03 | inner improved | outer improved | translated |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | `0.003` | -0.002513 | 0.002768 | True | False | False |
| D2 | `0.01` | -0.000735 | 0.001944 | True | False | False |
| D3 | `0.03` | 0.000000 | 0.000000 | False | False | False |

Negative deltas are improvements. Negative translation is not hidden.

## 13. Global development configuration rule

- consider the C selected independently in D1/D2/D3
- choose the value selected by a strict majority of outer folds
- otherwise choose the C with the lowest mean inner tuning log loss aggregating all eligible inner evaluations across D1/D2/D3
- if effectively tied within 1e-06, choose the smaller C
- outer validation used to choose the global C: False
- 2025 used: False
- decision: global C = **0.01** (aggregate_inner_log_loss_fallback; no strict majority; lowest aggregate inner mean (0.0827198539) at C=0.01)

## 14. FINAL DEVELOPMENT-FROZEN LOGISTIC REGRESSION SPECIFICATION

- model family: `logistic_regression` (LogisticRegression)
- feature set: `ALL_84` (task `winner`)
- solver: `lbfgs`; max_iter: 1000; class_weight: None; random_state: 42
- penalty: l2 (sklearn default, not passed explicitly)
- **C: 0.01**
- probability semantics: `INDEPENDENT_BINARY` (never normalized across drivers)
- preprocessing: existing frozen train-fitted pipeline (median/StandardScaler numeric, most-frequent boolean, one-hot categorical with explicit MISSING sentinel)
- no calibration fitted; no threshold optimization

## 15. Boundary limitation

The M6 lower-boundary issue is resolved within the tested range; no recursive search is performed.

## 16. Determinism, runtime, memory

- representative refit (D1, C=0.003): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- suite wall time: 73.1 s
- determinism refit time: 24.1 s
- peak RSS: 1.85 GB
- total actual estimator fits: 29 (plus 6 inner preprocessor fits)

Inference (selected LogReg only; latency probed on every outer evaluation, never per C):

- D1: batch mean=0.048762 s (483514.8 states/s); single-state mean=0.008825 s
- D2: batch mean=0.054656 s (446829.9 states/s); single-state mean=0.008648 s
- D3: batch mean=0.053048 s (501542.2 states/s); single-state mean=0.008643 s

## 17. Hashes (immutability boundary)

- phase2_parquet_byte_hash: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- phase2_manifest_byte_hash: `b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62`
- f16_ablation_byte_hash: `bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7`
- phase2_matrix_content_hash: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- m0_protocol_semantic_hash: `0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce`
- m0_protocol_json_byte_hash: `6a02b4c2ea36f6e3f0b952bec8cb02d5216bead8ce7a341f8e0145cf18545e01`
- phase2_freeze_manifest_byte_hash: `ced17eb9a5cae03b50f3965338ac0fa00d54ba3e68f141e19abb36759368b4ce`

## 18. Artifacts and limitations

- M7 machine-readable artifact: `/Users/tfatharva/f1-in-race-prediction_main/data/v2/model_lab/reports/logreg_boundary_resolution_v1.json` (this document was rendered from it)
- M6 artifact used for comparison: `data/v2/model_lab/reports/tuning_selection_v1.json` (not rerun)
- M3 reference used for comparison: `data/v2/model_lab/reports/logreg_reference_v1.json` (not rerun)
- three outer development folds are limited evidence; inner folds are nested and not independent
- state rows are not independent; headline metrics use race-macro aggregation
- raw probabilities only; no calibration was fitted in M7
- 2025 was not evaluated and remains the protected final holdout

## 19. Recommendation

The base Logistic Regression configuration is development-frozen within the tested regularization range and is ready to advance.


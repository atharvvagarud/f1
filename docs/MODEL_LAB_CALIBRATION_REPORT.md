# Model Lab Calibration Evaluation & Selection Report (M8)

## CALIBRATION DEVELOPMENT EVALUATION

## BASE MODEL: FROZEN LOGISTIC REGRESSION C=0.01

## OUTER EVALUATION: 2022 / 2023 / 2024

## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED

## 1. Calibration question

Does a post-hoc calibration layer (Platt/sigmoid or isotonic) improve chronologically valid probabilistic quality enough to justify its extra fitted complexity, or should the frozen base model's RAW probabilities be retained? Calibration is NOT assumed beneficial; RAW is a legitimate winner.

## 2. Temporal calibration architecture

Calibration is model fitting, so the calibration season is always the LAST complete season of the outer TRAIN: base-fit < calibration < outer evaluation. Calibrators never see outer labels.

| outer fold | BASE FIT | CALIBRATION | OUTER EVALUATION |
| --- | --- | --- | --- |
| D1 | 2018–2020 | 2021 | 2022 |
| D2 | 2018–2021 | 2022 | 2023 |
| D3 | 2018–2022 | 2023 | 2024 |

## 3. Frozen base-model specification

- family: LogisticRegression
- C = 0.01; solver = lbfgs; max_iter = 1000; class_weight = None; random_state = 42
- feature set: ALL_84; probability semantics: INDEPENDENT_BINARY
- no retuning; M8 reuses the M7-frozen C exactly

## 4. Calibration sample audit

| fold | season | rows | races | positives | negatives | prevalence | unique p | min p | max p | exact 0 | exact 1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 2021 | 23758 | 22 | 1299 | 22459 | 0.054676 | 23758 | 0.000000 | 0.963886 | 0 | 0 |
| D2 | 2022 | 23577 | 22 | 1295 | 22282 | 0.054926 | 23577 | 0.000000 | 0.896638 | 0 | 0 |
| D3 | 2023 | 24422 | 22 | 1325 | 23097 | 0.054254 | 24422 | 0.000000 | 0.998624 | 0 | 0 |

## 5. Methods

### RAW

Untouched frozen base-model probability; no transformation.

### PLATT

Explicit one-dimensional `LogisticRegression` over `logit(clip(p, 1e-06, 1-1e-06))`; no hidden cross-validation; no original feature enters the calibrator.

| fold | coefficient | intercept | finite | coefficient > 0 |
| --- | --- | --- | --- | --- |
| D1 | 0.931278 | -0.347193 | True | True |
| D2 | 1.229850 | 0.479335 | True | True |
| D3 | 1.671836 | 0.442985 | True | True |

### ISOTONIC

`sklearn.isotonic.IsotonicRegression(increasing=True, out_of_bounds='clip', y_min=0, y_max=1)` fit on calibration rows only.

| fold | thresholds | unique outer outputs | frac at 0 | frac at 1 | degenerate |
| --- | --- | --- | --- | --- | --- |
| D1 | 44 | 47 | 53.5140% | 0.0382% | True |
| D2 | 46 | 38 | 73.4543% | 0.0000% | True |
| D3 | 50 | 52 | 79.0686% | 0.0000% | True |

## 6. DEVELOPMENT CALIBRATION RESULTS

### CALIBRATION DEVELOPMENT EVALUATION
### BASE MODEL: FROZEN LOGISTIC REGRESSION C=0.01
### OUTER EVALUATION: 2022 / 2023 / 2024
### 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED

### Race-macro log loss / Brier

| method | fold | log loss | Brier | ROC-AUC | PR-AUC | ECE |
| --- | --- | --- | --- | --- | --- | --- |
| RAW | D1 | 0.094892 | 0.028228 | 0.966025 | 0.665607 | 0.008364 |
| RAW | D2 | 0.053476 | 0.014265 | 0.991492 | 0.882029 | 0.016112 |
| RAW | D3 | 0.082712 | 0.024375 | 0.970927 | 0.771109 | 0.013571 |
| PLATT | D1 | 0.096816 | 0.029147 | 0.966025 | 0.665607 | 0.011835 |
| PLATT | D2 | 0.050712 | 0.014345 | 0.991492 | 0.882029 | 0.013933 |
| PLATT | D3 | 0.091569 | 0.024572 | 0.970927 | 0.771109 | 0.018972 |
| ISOTONIC | D1 | 0.112962 | 0.029781 | 0.964457 | 0.653512 | 0.010184 |
| ISOTONIC | D2 | 0.050744 | 0.014242 | 0.990678 | 0.866603 | 0.013475 |
| ISOTONIC | D3 | 0.144673 | 0.026223 | 0.960415 | 0.759822 | 0.021401 |

### State-pooled diagnostics

| method | fold | log loss | Brier | ROC-AUC | PR-AUC |
| --- | --- | --- | --- | --- | --- |
| RAW | D1 | 0.095000 | 0.028399 | 0.969170 | 0.627182 |
| RAW | D2 | 0.052827 | 0.014020 | 0.992892 | 0.906500 |
| RAW | D3 | 0.085737 | 0.025322 | 0.974678 | 0.709917 |
| PLATT | D1 | 0.096554 | 0.029170 | 0.969170 | 0.627182 |
| PLATT | D2 | 0.050354 | 0.014250 | 0.992892 | 0.906500 |
| PLATT | D3 | 0.096695 | 0.025623 | 0.974678 | 0.709917 |
| ISOTONIC | D1 | 0.111164 | 0.029952 | 0.966707 | 0.575864 |
| ISOTONIC | D2 | 0.050281 | 0.014065 | 0.992135 | 0.880232 |
| ISOTONIC | D3 | 0.152464 | 0.027257 | 0.963302 | 0.674922 |

### Race-stage race-macro log loss

| method | fold | EARLY | MID | LATE |
| --- | --- | --- | --- | --- |
| RAW | D1 | 0.111799 | 0.094186 | 0.078558 |
| RAW | D2 | 0.070341 | 0.048755 | 0.041775 |
| RAW | D3 | 0.102714 | 0.080762 | 0.064584 |
| PLATT | D1 | 0.111910 | 0.096485 | 0.082094 |
| PLATT | D2 | 0.070511 | 0.044450 | 0.037692 |
| PLATT | D3 | 0.123089 | 0.088782 | 0.062809 |
| ISOTONIC | D1 | 0.116890 | 0.102757 | 0.121319 |
| ISOTONIC | D2 | 0.069652 | 0.043158 | 0.040070 |
| ISOTONIC | D3 | 0.224972 | 0.132590 | 0.077133 |

### Synchronized winner top-k

| method | fold | top-1 | top-3 | eval states | coverage |
| --- | --- | --- | --- | --- | --- |
| RAW | D1 | 0.602201 | 0.937418 | 23537 | mean field 19.784297 |
| RAW | D2 | 0.883253 | 0.994300 | 24386 | mean field 19.770811 |
| RAW | D3 | 0.766072 | 0.882151 | 26568 | mean field 19.774691 |
| PLATT | D1 | 0.602201 | 0.937418 | 23537 | mean field 19.784297 |
| PLATT | D2 | 0.883253 | 0.994300 | 24386 | mean field 19.770811 |
| PLATT | D3 | 0.766072 | 0.882151 | 26568 | mean field 19.774691 |
| ISOTONIC | D1 | 0.552534 | 0.937205 | 23537 | mean field 19.784297 |
| ISOTONIC | D2 | 0.854056 | 0.988764 | 24386 | mean field 19.770811 |
| ISOTONIC | D3 | 0.738934 | 0.875414 | 26568 | mean field 19.774691 |

## 7. Cross-fold aggregate

| method | mean log loss | mean Brier | mean ECE | mean top-1 | mean ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| RAW | 0.077027 | 0.022289 | 0.012683 | 0.750508 | 0.976148 |
| PLATT | 0.079699 | 0.022688 | 0.014913 | 0.750508 | 0.976148 |
| ISOTONIC | 0.102793 | 0.023415 | 0.015020 | 0.715175 | 0.971850 |

## 8. Per-fold comparisons (calibrated minus RAW)

| method | fold | Δ log loss | Δ Brier | material regression |
| --- | --- | --- | --- | --- |
| PLATT | D1 | +0.001925 | +0.000919 | True |
| PLATT | D2 | -0.002764 | +0.000079 | False |
| PLATT | D3 | +0.008856 | +0.000197 | True |
| ISOTONIC | D1 | +0.018070 | +0.001553 | True |
| ISOTONIC | D2 | -0.002732 | -0.000024 | False |
| ISOTONIC | D3 | +0.061961 | +0.001848 | True |

## 9. Reliability findings

| method | fold | empty bins | largest gap | under-confident | over-confident |
| --- | --- | --- | --- | --- | --- |
| RAW | D1 | 0 | 0.449391 | 4 | 6 |
| RAW | D2 | 0 | 0.228149 | 5 | 5 |
| RAW | D3 | 0 | 0.251329 | 6 | 4 |
| PLATT | D1 | 0 | 0.918895 | 7 | 3 |
| PLATT | D2 | 0 | 0.334669 | 4 | 6 |
| PLATT | D3 | 0 | 0.278883 | 7 | 3 |
| ISOTONIC | D1 | 1 | 1.000000 | 5 | 4 |
| ISOTONIC | D2 | 2 | 0.235263 | 2 | 6 |
| ISOTONIC | D3 | 0 | 0.427210 | 6 | 4 |

## 10. Ranking invariance

Platt with a positive coefficient is strictly monotone, so ranking metrics must be unchanged; isotonic may introduce ties.

| fold | Platt ROC-AUC Δ | Platt PR-AUC Δ | Platt top-1 Δ | Isotonic ROC-AUC Δ |
| --- | --- | --- | --- | --- |
| D1 | 0.000000 | 0.000000 | 0.000000 | -0.001568 |
| D2 | 0.000000 | 0.000000 | 0.000000 | -0.000814 |
| D3 | 0.000000 | 0.000000 | 0.000000 | -0.010513 |

## 11. Material-regression checks

- relative degradation threshold: 0.01
- PLATT: material regressions on 2/3 folds (majority = True)
- ISOTONIC: material regressions on 2/3 folds (majority = True)

## 12. Bootstrap uncertainty

- NOT_APPLICABLE: selected method is RAW; no calibrated candidate to compare

## 13. Calibration selection rule (predeclared)

- primary objective: mean outer race-macro log loss
- guard B: mean Brier no worse than RAW
- guard C: no material regression (relative log-loss degradation > 1%) on a majority of folds
- guard D: fitted behaviour not pathological
- tie tolerance: 0.0001 absolute mean log loss; prefer RAW over PLATT over ISOTONIC
- ECE never decides selection

## 14. Selected method

**SELECT RAW**

- no calibrated method satisfied the predeclared eligibility guards (A–D) — RAW retained
- tie-break applied: False

## 15. Selected probability pipeline

`ALL_84` → frozen preprocessing (train-fitted) → frozen `LogisticRegression` `C=0.01` → **RAW** calibration → INDEPENDENT_BINARY probability (never normalized across drivers).

## 16. Complexity / latency impact

| fold | preprocess fit | base model fit | Platt fit | Platt transform | isotonic fit | isotonic transform |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 0.406870 | 0.237324 | 0.002628 | 0.000229 | 0.002421 | 0.000388 |
| D2 | 0.578412 | 0.347249 | 0.002730 | 0.000213 | 0.002437 | 0.000378 |
| D3 | 0.719045 | 0.411354 | 0.003160 | 0.000261 | 0.002888 | 0.000307 |

- total suite wall time: 146.69 s
- peak RSS bytes: 1764163584

## 17. Determinism

- representative fold: D1
- same experiment ids: True
- metrics identical: True
- max |Δ RAW|: 0.000e+00
- max |Δ PLATT|: 0.000e+00
- max |Δ ISOTONIC|: 0.000e+00

## 18. Limitations

- RAW retained: calibration did not clear the predeclared guards
- ISOTONIC flagged pathological on at least one fold
- calibration method selection is development-only; 2025 is protected

## 19. Deployment refit policy (documented, not executed)

M8 selects a calibration METHOD only. The selected method would later be fitted on development data (base-fit history plus the calibration season) with no change to the frozen base model. No 2025 calibration procedure is invented or evaluated here; the protected holdout remains untouched until the single locked final run.

## 20. Next-stage implications

- The frozen base probabilities already meet the probability-quality bar on outer development folds; no calibration layer is added to the deployment pipeline.
- M9 should build on the RAW INDEPENDENT_BINARY probabilities of the frozen `C=0.01` LogReg.


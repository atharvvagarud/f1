# Model Lab Nonlinear Candidates Report (M4)

**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

M4 evaluates exactly two stronger nonlinear candidate families (sklearn HistGradientBoostingClassifier, XGBoost XGBClassifier) for the PRIMARY winner task on D1/D2/D3, extending the frozen M3 path. One fixed, untuned specification per family; no resampling, no post-hoc calibration, no threshold tuning, no 2025 access. Every value below traces to a stored experiment result (task `winner`, protocol v1, matrix d2ee966c18d2…).

## 1. Fixed candidate specifications (chosen before validation)

- HGB (HistGradientBoostingClassifier): loss=log_loss, learning_rate=0.1, max_iter=100, max_leaf_nodes=31, max_depth=None, min_samples_leaf=20, l2_regularization=0.0, max_bins=255, early_stopping=False (single justified non-default: sklearn default 'auto' would hold out 10% of training rows for early stopping; M4 forbids validation-driven training), class_weight=None, random_state=42; sklearn 1.8.0
- XGB (XGBClassifier): objective=binary:logistic, n_estimators=200, max_depth=4 (conservative vs library default 6 for the rare ~5.5% winner class), learning_rate=0.1, subsample=1.0/colsample=1.0 (deterministic full-data boosting), min_child_weight=1, reg_lambda=1.0, reg_alpha=0.0, gamma=0, tree_method=hist (CPU only, no GPU), eval_metric=logloss recorded with NO eval set supplied (no early stopping), scale_pos_weight=1 (natural prevalence), random_state=42, n_jobs=4 (controlled local CPU); xgboost 3.2.0
- task: winner; feature set: ALL_84 (frozen full 84-feature surface); seed: 42
- training weighting: state_equal; tuning: none (one fixed specification per family, chosen before observing validation)
- probability semantic: INDEPENDENT_BINARY (per-driver P(win); never normalized across drivers)
- calibration fitted: none (raw probabilities evaluated)

## 2. Preprocessing (fitted on TRAIN only)

- both candidates reuse the exact M3 train-fitted preprocessing (median + StandardScaler numerics, most-frequent booleans, MISSING-sentinel + train-vocabulary one-hot categoricals); same 84 source features; HGB native categorical support inspected and deliberately not used to preserve comparable feature semantics

| model | fold | train rows | train races | train prevalence | val rows | val races | features in | transformed dim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | D1 | 88123 | 81 | 0.055173 | 23577 | 22 | 84 | 106 |
| hist_gradient_boosting | D2 | 111700 | 103 | 0.055121 | 24422 | 22 | 84 | 106 |
| hist_gradient_boosting | D3 | 136122 | 125 | 0.054965 | 26606 | 24 | 84 | 106 |
| xgboost | D1 | 88123 | 81 | 0.055173 | 23577 | 22 | 84 | 106 |
| xgboost | D2 | 111700 | 103 | 0.055121 | 24422 | 22 | 84 | 106 |
| xgboost | D3 | 136122 | 125 | 0.054965 | 26606 | 24 | 84 | 106 |

Fit warnings: hist_gradient_boosting/D1=none; hist_gradient_boosting/D2=none; hist_gradient_boosting/D3=none; xgboost/D1=none; xgboost/D2=none; xgboost/D3=none

## 3. Headline probability quality (race-macro)

### log_loss (race-macro; lower is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | 0.180020 | 0.065885 | 0.169010 | 0.138305 | 0.062959 | 0.065885 | 0.180020 | 0.114135 |
| xgboost | 0.139101 | 0.060909 | 0.127178 | 0.109063 | 0.042126 | 0.060909 | 0.139101 | 0.078192 |

_state_pooled (diagnostic):_ hist_gradient_boosting=0.179041/0.064877/0.173115; xgboost=0.139198/0.058856/0.129022

### brier (race-macro; lower is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | 0.040405 | 0.018657 | 0.035221 | 0.031428 | 0.011360 | 0.018657 | 0.040405 | 0.021749 |
| xgboost | 0.035818 | 0.017977 | 0.029829 | 0.027874 | 0.009080 | 0.017977 | 0.035818 | 0.017841 |

_state_pooled (diagnostic):_ hist_gradient_boosting=0.039983/0.018234/0.036116; xgboost=0.035984/0.017423/0.030528

## 4. Discrimination (race-macro ROC-AUC / PR-AUC)

### roc_auc (race-macro; higher is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | 0.955186 | 0.986718 | 0.954798 | 0.965567 | 0.018318 | 0.954798 | 0.986718 | 0.031920 |
| xgboost | 0.954922 | 0.987945 | 0.958322 | 0.967063 | 0.018164 | 0.954922 | 0.987945 | 0.033023 |

_state_pooled (diagnostic):_ hist_gradient_boosting=0.959045/0.993182/0.963170; xgboost=0.961506/0.993544/0.963989

### pr_auc (race-macro; higher is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | 0.652056 | 0.842919 | 0.645535 | 0.713503 | 0.112124 | 0.645535 | 0.842919 | 0.197384 |
| xgboost | 0.599194 | 0.844031 | 0.674199 | 0.705808 | 0.125441 | 0.599194 | 0.844031 | 0.244837 |

_state_pooled (diagnostic):_ hist_gradient_boosting=0.576500/0.887417/0.641003; xgboost=0.608785/0.888473/0.687100

## 5. Calibration (ECE, 10 equal-width bins; raw probabilities)

| model | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| hist_gradient_boosting | 0.037277 | 0.015860 | 0.032131 | 0.028423 |
| xgboost | 0.029583 | 0.015060 | 0.026147 | 0.023597 |

Reliability-bin detail is stored per experiment result; no calibrator was fitted.

## 6. Race-stage performance (race-macro)

### log_loss by stage

- hist_gradient_boosting/D1: EARLY=0.201409 MID=0.184662 LATE=0.157933
- hist_gradient_boosting/D2: EARLY=0.083811 MID=0.067817 LATE=0.046506
- hist_gradient_boosting/D3: EARLY=0.207543 MID=0.169178 LATE=0.130410
- xgboost/D1: EARLY=0.160974 MID=0.134068 LATE=0.125498
- xgboost/D2: EARLY=0.081428 MID=0.059031 LATE=0.042921
- xgboost/D3: EARLY=0.155449 MID=0.127883 LATE=0.098051

### brier by stage

- hist_gradient_boosting/D1: EARLY=0.042335 MID=0.040022 LATE=0.040171
- hist_gradient_boosting/D2: EARLY=0.022658 MID=0.019582 LATE=0.013867
- hist_gradient_boosting/D3: EARLY=0.038950 MID=0.033928 LATE=0.032722
- xgboost/D1: EARLY=0.039258 MID=0.034313 LATE=0.034886
- xgboost/D2: EARLY=0.023909 MID=0.017473 LATE=0.012761
- xgboost/D3: EARLY=0.034453 MID=0.028371 LATE=0.026577

## 7. Synchronized winner top-k (coverage-qualified)

| model | fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/degen) | min field |
| --- | --- | --- | --- | --- | --- | --- |
| hist_gradient_boosting | D1 | 0.569061 | 0.876110 | 23537 | 0/32/8 | 2 |
| hist_gradient_boosting | D2 | 0.811941 | 0.996883 | 24386 | 0/25/11 | 2 |
| hist_gradient_boosting | D3 | 0.553448 | 0.913204 | 26568 | 0/30/8 | 2 |
| xgboost | D1 | 0.491524 | 0.908485 | 23537 | 0/32/8 | 2 |
| xgboost | D2 | 0.803863 | 0.996514 | 24386 | 0/25/11 | 2 |
| xgboost | D3 | 0.626468 | 0.922124 | 26568 | 0/30/8 | 2 |

Top-3 on fields smaller than 3 is reported for completeness but is NOT genuine three-way discrimination (min observable field = 2).

## 8. Comparison vs M3 Logistic Regression (stored M3 artifacts)

### brier (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.040405 | 0.024270 | 0.016136 | DOES NOT BEAT |
| D1 | xgboost | 0.035818 | 0.024270 | 0.011548 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.018657 | 0.010258 | 0.008398 | DOES NOT BEAT |
| D2 | xgboost | 0.017977 | 0.010258 | 0.007719 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.035221 | 0.027720 | 0.007501 | DOES NOT BEAT |
| D3 | xgboost | 0.029829 | 0.027720 | 0.002108 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.031428 | 0.020749 | 0.010678 | DOES NOT BEAT |
| mean | xgboost | 0.027874 | 0.020749 | 0.007125 | DOES NOT BEAT |

### expected_calibration_error (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.037277 | 0.008397 | 0.028880 | DOES NOT BEAT |
| D1 | xgboost | 0.029583 | 0.008397 | 0.021186 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.015860 | 0.009098 | 0.006762 | DOES NOT BEAT |
| D2 | xgboost | 0.015060 | 0.009098 | 0.005963 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.032131 | 0.019215 | 0.012916 | DOES NOT BEAT |
| D3 | xgboost | 0.026147 | 0.019215 | 0.006931 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.028423 | 0.012237 | 0.016186 | DOES NOT BEAT |
| mean | xgboost | 0.023597 | 0.012237 | 0.011360 | DOES NOT BEAT |

### log_loss (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.180020 | 0.083045 | 0.096975 | DOES NOT BEAT |
| D1 | xgboost | 0.139101 | 0.083045 | 0.056056 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.065885 | 0.038915 | 0.026970 | DOES NOT BEAT |
| D2 | xgboost | 0.060909 | 0.038915 | 0.021994 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.169010 | 0.093433 | 0.075577 | DOES NOT BEAT |
| D3 | xgboost | 0.127178 | 0.093433 | 0.033745 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.138305 | 0.071797 | 0.066508 | DOES NOT BEAT |
| mean | xgboost | 0.109063 | 0.071797 | 0.037265 | DOES NOT BEAT |

### pr_auc (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.652056 | 0.723252 | -0.071195 | DOES NOT BEAT |
| D1 | xgboost | 0.599194 | 0.723252 | -0.124057 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.842919 | 0.917487 | -0.074568 | DOES NOT BEAT |
| D2 | xgboost | 0.844031 | 0.917487 | -0.073456 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.645535 | 0.721023 | -0.075488 | DOES NOT BEAT |
| D3 | xgboost | 0.674199 | 0.721023 | -0.046824 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.713503 | 0.787254 | -0.073751 | DOES NOT BEAT |
| mean | xgboost | 0.705808 | 0.787254 | -0.081446 | DOES NOT BEAT |

### roc_auc (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.955186 | 0.972581 | -0.017396 | DOES NOT BEAT |
| D1 | xgboost | 0.954922 | 0.972581 | -0.017660 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.986718 | 0.995147 | -0.008430 | DOES NOT BEAT |
| D2 | xgboost | 0.987945 | 0.995147 | -0.007202 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.954798 | 0.968246 | -0.013449 | DOES NOT BEAT |
| D3 | xgboost | 0.958322 | 0.968246 | -0.009924 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.965567 | 0.978658 | -0.013091 | DOES NOT BEAT |
| mean | xgboost | 0.967063 | 0.978658 | -0.011595 | DOES NOT BEAT |

### winner_top1 (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | logreg | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.569061 | 0.677274 | -0.108213 | DOES NOT BEAT |
| D1 | xgboost | 0.491524 | 0.677274 | -0.185750 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.811941 | 0.921184 | -0.109243 | DOES NOT BEAT |
| D2 | xgboost | 0.803863 | 0.921184 | -0.117321 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.553448 | 0.719512 | -0.166064 | DOES NOT BEAT |
| D3 | xgboost | 0.626468 | 0.719512 | -0.093044 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.644817 | 0.772657 | -0.127840 | DOES NOT BEAT |
| mean | xgboost | 0.640618 | 0.772657 | -0.132039 | DOES NOT BEAT |

No combined score is constructed; no significance is claimed.

## 9. Comparison vs M2 baseline floor (stored M2 artifacts)

### brier (lower is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.040405 | 0.029318 | 0.011087 | DOES NOT BEAT |
| D1 | xgboost | 0.035818 | 0.029318 | 0.006500 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.018657 | 0.015613 | 0.003043 | DOES NOT BEAT |
| D2 | xgboost | 0.017977 | 0.015613 | 0.002363 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.035221 | 0.027562 | 0.007659 | DOES NOT BEAT |
| D3 | xgboost | 0.029829 | 0.027562 | 0.002266 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.031428 | 0.024165 | 0.007263 | DOES NOT BEAT |
| mean | xgboost | 0.027874 | 0.024165 | 0.003710 | DOES NOT BEAT |

### expected_calibration_error (lower is better; baseline: CLASS_PRIOR)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.037277 | 0.000246 | 0.037031 | DOES NOT BEAT |
| D1 | xgboost | 0.029583 | 0.000246 | 0.029336 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.015860 | 0.000866 | 0.014993 | DOES NOT BEAT |
| D2 | xgboost | 0.015060 | 0.000866 | 0.014194 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.032131 | 0.000692 | 0.031439 | DOES NOT BEAT |
| D3 | xgboost | 0.026147 | 0.000692 | 0.025455 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.028423 | 0.000602 | 0.027821 | DOES NOT BEAT |
| mean | xgboost | 0.023597 | 0.000602 | 0.022995 | DOES NOT BEAT |

### log_loss (lower is better; baseline: CLASS_PRIOR)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.180020 | 0.214068 | -0.034048 | BEATS |
| D1 | xgboost | 0.139101 | 0.214068 | -0.074967 | BEATS |
| D2 | hist_gradient_boosting | 0.065885 | 0.211307 | -0.145422 | BEATS |
| D2 | xgboost | 0.060909 | 0.211307 | -0.150397 | BEATS |
| D3 | hist_gradient_boosting | 0.169010 | 0.211340 | -0.042329 | BEATS |
| D3 | xgboost | 0.127178 | 0.211340 | -0.084162 | BEATS |
| mean | hist_gradient_boosting | 0.138305 | 0.212238 | -0.073933 | BEATS |
| mean | xgboost | 0.109063 | 0.212238 | -0.103175 | BEATS |

### pr_auc (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.652056 | 0.613725 | 0.038331 | BEATS |
| D1 | xgboost | 0.599194 | 0.613725 | -0.014531 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.842919 | 0.762168 | 0.080750 | BEATS |
| D2 | xgboost | 0.844031 | 0.762168 | 0.081862 | BEATS |
| D3 | hist_gradient_boosting | 0.645535 | 0.639359 | 0.006176 | BEATS |
| D3 | xgboost | 0.674199 | 0.639359 | 0.034840 | BEATS |
| mean | hist_gradient_boosting | 0.713503 | 0.671751 | 0.041752 | BEATS |
| mean | xgboost | 0.705808 | 0.671751 | 0.034057 | BEATS |

### roc_auc (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.955186 | 0.860631 | 0.094555 | BEATS |
| D1 | xgboost | 0.954922 | 0.860631 | 0.094291 | BEATS |
| D2 | hist_gradient_boosting | 0.986718 | 0.923215 | 0.063502 | BEATS |
| D2 | xgboost | 0.987945 | 0.923215 | 0.064730 | BEATS |
| D3 | hist_gradient_boosting | 0.954798 | 0.863590 | 0.091208 | BEATS |
| D3 | xgboost | 0.958322 | 0.863590 | 0.094733 | BEATS |
| mean | hist_gradient_boosting | 0.965567 | 0.882478 | 0.083089 | BEATS |
| mean | xgboost | 0.967063 | 0.882478 | 0.084585 | BEATS |

### winner_top1 (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | hist_gradient_boosting | 0.569061 | 0.730339 | -0.161278 | DOES NOT BEAT |
| D1 | xgboost | 0.491524 | 0.730339 | -0.238815 | DOES NOT BEAT |
| D2 | hist_gradient_boosting | 0.811941 | 0.861478 | -0.049537 | DOES NOT BEAT |
| D2 | xgboost | 0.803863 | 0.861478 | -0.057615 | DOES NOT BEAT |
| D3 | hist_gradient_boosting | 0.553448 | 0.732987 | -0.179539 | DOES NOT BEAT |
| D3 | xgboost | 0.626468 | 0.732987 | -0.106519 | DOES NOT BEAT |
| mean | hist_gradient_boosting | 0.644817 | 0.774935 | -0.130118 | DOES NOT BEAT |
| mean | xgboost | 0.640618 | 0.774935 | -0.134317 | DOES NOT BEAT |

## 10. Determinism, runtime, latency, memory

- determinism refit (hist_gradient_boosting/D1): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- determinism refit (xgboost/D1): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- per-fold fit/predict wall time:
  - hist_gradient_boosting/D1: fit=3.05 s predict_total=9.37 s batch_mean=0.1145 s throughput=205982.1 states/s
  - hist_gradient_boosting/D2: fit=3.01 s predict_total=9.44 s batch_mean=0.0926 s throughput=263661.1 states/s
  - hist_gradient_boosting/D3: fit=3.13 s predict_total=10.31 s batch_mean=0.1020 s throughput=260948.5 states/s
  - xgboost/D1: fit=1.35 s predict_total=9.11 s batch_mean=0.0529 s throughput=445582.2 states/s
  - xgboost/D2: fit=1.68 s predict_total=9.70 s batch_mean=0.0671 s throughput=363969.2 states/s
  - xgboost/D3: fit=2.24 s predict_total=10.42 s batch_mean=0.0684 s throughput=389094.6 states/s
- full suite wall time: 150.2 s
- peak RSS: 1.86 GB

## 11. Artifacts

- hist_gradient_boosting/D1: `ef33f3351c15e8689921c0489142a363cd3e9446af9247bdbe18eca7cbdf7195`
- hist_gradient_boosting/D2: `f750e57b083cdfe0bf07855deadc9a74c56dcccc548edc298adcf5df216c1152`
- hist_gradient_boosting/D3: `a8f6e9faa2fd7603e2fd1931ab07091c5469caa8aa7baf4b9bcc334b71ded334`
- xgboost/D1: `d7d62af0dfa0f6d52ffec8f6ff4309f1c71961efb67d4e3c084b1a0af5693bce`
- xgboost/D2: `b551b986cf1ec6b0a36389ddb77e0e62c24e33d5208ee5858ec65756be5111ea`
- xgboost/D3: `1c2d6ab0597bdd5acfe8182804db1845a2175c9f6fa5e38f958f9b1756ee2a46`

Suite summary: `/Users/tfatharva/f1-in-race-prediction_main/data/v2/model_lab/reports/nonlinear_candidates_v1.json` (machine-readable; this document was rendered from it).
M3 LOGREG suite: schema v1 (values in §8 loaded from stored M3 artifacts).
M2 baseline suite: schema v1 (values in §9 loaded from stored M2 artifacts).

## 12. Limitations and M5 outlook

- Three development folds is a coarse robustness signal; fold dispersion is reported, not hidden.
- State rows are not independent observations; headline conclusions use race-macro aggregation.
- No tuning was performed: these are representative fixed specifications, not optimized models. M5/M6 may tune inside training history only.
- Raw probabilities only; calibration decisions belong later.
- 2025 was not evaluated and must remain protected until the final locked holdout.
- M5 recommendation: READY FOR M5 — with constraint: neither fixed-spec candidate (HGB, XGB; raw probabilities) beats the M3 Logistic Regression reference on any headline development metric (log-loss, Brier, ROC-AUC, PR-AUC, ECE, top-1), consistently across D1/D2/D3; both beat the M2 floor on log-loss/PR-AUC/ROC-AUC only. Do not promote either family on M4 evidence. Next stages should prioritize calibration analysis and training-history-only tuning investigation over assuming tree superiority. DO NOT START M5 until this report is approved.


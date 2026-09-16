# Model Lab Bagged Trees Report (M5)

**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

M5 evaluates exactly two bagged/randomized tree candidate families (sklearn ExtraTreesClassifier, RandomForestClassifier) for the PRIMARY winner task on D1/D2/D3, extending the frozen M3/M4 path. One fixed, untuned specification per family; no resampling, no class rebalancing, no post-hoc calibration, no threshold tuning, no 2025 access. Every value below traces to a stored experiment result (task `winner`, protocol v1, matrix d2ee966c18d2…).

## 1. Fixed candidate specifications (chosen before validation)

- ExtraTrees (ExtraTreesClassifier): n_estimators=300, criterion=gini, max_depth=None, min_samples_split=2, min_samples_leaf=1, max_features=sqrt, bootstrap=False, class_weight=None, n_jobs=4 (controlled local CPU), random_state=42; sklearn 1.8.0
- RandomForest (RandomForestClassifier): n_estimators=300, criterion=gini, max_depth=None, min_samples_split=2, min_samples_leaf=1, max_features=sqrt, bootstrap=True, class_weight=None, n_jobs=4 (controlled local CPU), random_state=42; sklearn 1.8.0
- family contrast kept at library defaults: ExtraTrees grows fully randomized trees on the full sample (bootstrap=False); RandomForest baggs samples and searches for the best split (bootstrap=True)
- task: winner; feature set: ALL_84 (frozen full 84-feature surface); seed: 42
- training weighting: state_equal; tuning: none (one fixed specification per family, chosen before observing validation)
- probability semantic: INDEPENDENT_BINARY (per-driver P(win); never normalized across drivers)
- calibration fitted: none (raw probabilities evaluated)

## 2. Preprocessing (fitted on TRAIN only)

- both candidates reuse the exact M3/M4 train-fitted preprocessing (median + StandardScaler numerics, most-frequent booleans, MISSING-sentinel + train-vocabulary one-hot categoricals); same 84 source features; densified ~106-dim representation

| model | fold | train rows | train races | train prevalence | val rows | val races | features in | transformed dim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | D1 | 88123 | 81 | 0.055173 | 23577 | 22 | 84 | 106 |
| extra_trees | D2 | 111700 | 103 | 0.055121 | 24422 | 22 | 84 | 106 |
| extra_trees | D3 | 136122 | 125 | 0.054965 | 26606 | 24 | 84 | 106 |
| random_forest | D1 | 88123 | 81 | 0.055173 | 23577 | 22 | 84 | 106 |
| random_forest | D2 | 111700 | 103 | 0.055121 | 24422 | 22 | 84 | 106 |
| random_forest | D3 | 136122 | 125 | 0.054965 | 26606 | 24 | 84 | 106 |

Fit warnings: extra_trees/D1=none; extra_trees/D2=none; extra_trees/D3=none; random_forest/D1=none; random_forest/D2=none; random_forest/D3=none

## 3. Headline probability quality (race-macro)

### log_loss (race-macro; lower is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | 0.098999 | 0.048484 | 0.096943 | 0.081475 | 0.028590 | 0.048484 | 0.098999 | 0.050514 |
| random_forest | 0.114909 | 0.046325 | 0.103178 | 0.088137 | 0.036683 | 0.046325 | 0.114909 | 0.068584 |

_state_pooled (diagnostic):_ extra_trees=0.098112/0.047429/0.098954; random_forest=0.114033/0.045465/0.105685

### brier (race-macro; lower is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | 0.029940 | 0.011452 | 0.027108 | 0.022833 | 0.009958 | 0.011452 | 0.029940 | 0.018488 |
| random_forest | 0.036330 | 0.010855 | 0.025273 | 0.024153 | 0.012774 | 0.010855 | 0.036330 | 0.025475 |

_state_pooled (diagnostic):_ extra_trees=0.029707/0.011011/0.027725; random_forest=0.036073/0.010455/0.025969

## 4. Discrimination (race-macro ROC-AUC / PR-AUC)

### roc_auc (race-macro; higher is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | 0.970035 | 0.996754 | 0.955835 | 0.974208 | 0.020776 | 0.955835 | 0.996754 | 0.040919 |
| random_forest | 0.952259 | 0.996034 | 0.956278 | 0.968190 | 0.024197 | 0.952259 | 0.996034 | 0.043775 |

_state_pooled (diagnostic):_ extra_trees=0.973062/0.998155/0.964710; random_forest=0.954562/0.997911/0.964391

### pr_auc (race-macro; higher is better)

| model | D1 | D2 | D3 | mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | 0.702003 | 0.947478 | 0.645016 | 0.764832 | 0.160722 | 0.645016 | 0.947478 | 0.302462 |
| random_forest | 0.526672 | 0.940157 | 0.710024 | 0.725618 | 0.207184 | 0.526672 | 0.940157 | 0.413486 |

_state_pooled (diagnostic):_ extra_trees=0.678241/0.969356/0.681863; random_forest=0.508291/0.966490/0.716633

## 5. Calibration (ECE, 10 equal-width bins; raw probabilities)

| model | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| extra_trees | 0.023618 | 0.028414 | 0.011111 | 0.021048 |
| random_forest | 0.024192 | 0.024178 | 0.009495 | 0.019288 |

Reliability-bin detail is stored per experiment result; no calibrator was fitted.

## 6. Race-stage performance (race-macro)

### log_loss by stage

- extra_trees/D1: EARLY=0.107376 MID=0.100339 LATE=0.088780
- extra_trees/D2: EARLY=0.059502 MID=0.047173 LATE=0.038932
- extra_trees/D3: EARLY=0.128141 MID=0.090940 LATE=0.072264
- random_forest/D1: EARLY=0.121105 MID=0.117662 LATE=0.106194
- random_forest/D2: EARLY=0.057862 MID=0.045679 LATE=0.035584
- random_forest/D3: EARLY=0.148039 MID=0.096993 LATE=0.065692

### brier by stage

- extra_trees/D1: EARLY=0.033373 MID=0.030384 LATE=0.025946
- extra_trees/D2: EARLY=0.016005 MID=0.010991 LATE=0.007423
- extra_trees/D3: EARLY=0.033709 MID=0.026747 LATE=0.020808
- random_forest/D1: EARLY=0.039047 MID=0.037409 LATE=0.032610
- random_forest/D2: EARLY=0.015301 MID=0.010807 LATE=0.006513
- random_forest/D3: EARLY=0.031693 MID=0.025408 LATE=0.018654

## 7. Synchronized winner top-k (coverage-qualified)

| model | fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/degen) | min field |
| --- | --- | --- | --- | --- | --- | --- |
| extra_trees | D1 | 0.634745 | 0.967625 | 23537 | 0/32/8 | 2 |
| extra_trees | D2 | 0.911958 | 0.998442 | 24386 | 0/25/11 | 2 |
| extra_trees | D3 | 0.608100 | 0.886668 | 26568 | 0/30/8 | 2 |
| random_forest | D1 | 0.394698 | 0.958958 | 23537 | 0/32/8 | 2 |
| random_forest | D2 | 0.900025 | 0.996842 | 24386 | 0/25/11 | 2 |
| random_forest | D3 | 0.660080 | 0.891524 | 26568 | 0/30/8 | 2 |

Top-3 on fields smaller than 3 is reported for completeness but is NOT genuine three-way discrimination (min observable field = 2).

## 8. Comparison vs M3 Logistic Regression (stored M3 artifacts)

### brier (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.029940 | 0.024270 | 0.005670 | DOES NOT BEAT |
| D1 | random_forest | 0.036330 | 0.024270 | 0.012061 | DOES NOT BEAT |
| D2 | extra_trees | 0.011452 | 0.010258 | 0.001194 | DOES NOT BEAT |
| D2 | random_forest | 0.010855 | 0.010258 | 0.000597 | DOES NOT BEAT |
| D3 | extra_trees | 0.027108 | 0.027720 | -0.000612 | BEATS |
| D3 | random_forest | 0.025273 | 0.027720 | -0.002448 | BEATS |
| mean | extra_trees | 0.022833 | 0.020749 | 0.002084 | DOES NOT BEAT |
| mean | random_forest | 0.024153 | 0.020749 | 0.003404 | DOES NOT BEAT |

### expected_calibration_error (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.023618 | 0.008397 | 0.015221 | DOES NOT BEAT |
| D1 | random_forest | 0.024192 | 0.008397 | 0.015795 | DOES NOT BEAT |
| D2 | extra_trees | 0.028414 | 0.009098 | 0.019316 | DOES NOT BEAT |
| D2 | random_forest | 0.024178 | 0.009098 | 0.015080 | DOES NOT BEAT |
| D3 | extra_trees | 0.011111 | 0.019215 | -0.008104 | BEATS |
| D3 | random_forest | 0.009495 | 0.019215 | -0.009720 | BEATS |
| mean | extra_trees | 0.021048 | 0.012237 | 0.008811 | DOES NOT BEAT |
| mean | random_forest | 0.019288 | 0.012237 | 0.007052 | DOES NOT BEAT |

### log_loss (lower is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.098999 | 0.083045 | 0.015954 | DOES NOT BEAT |
| D1 | random_forest | 0.114909 | 0.083045 | 0.031864 | DOES NOT BEAT |
| D2 | extra_trees | 0.048484 | 0.038915 | 0.009569 | DOES NOT BEAT |
| D2 | random_forest | 0.046325 | 0.038915 | 0.007410 | DOES NOT BEAT |
| D3 | extra_trees | 0.096943 | 0.093433 | 0.003511 | DOES NOT BEAT |
| D3 | random_forest | 0.103178 | 0.093433 | 0.009746 | DOES NOT BEAT |
| mean | extra_trees | 0.081475 | 0.071797 | 0.009678 | DOES NOT BEAT |
| mean | random_forest | 0.088137 | 0.071797 | 0.016340 | DOES NOT BEAT |

### pr_auc (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.702003 | 0.723252 | -0.021249 | DOES NOT BEAT |
| D1 | random_forest | 0.526672 | 0.723252 | -0.196580 | DOES NOT BEAT |
| D2 | extra_trees | 0.947478 | 0.917487 | 0.029990 | BEATS |
| D2 | random_forest | 0.940157 | 0.917487 | 0.022670 | BEATS |
| D3 | extra_trees | 0.645016 | 0.721023 | -0.076008 | DOES NOT BEAT |
| D3 | random_forest | 0.710024 | 0.721023 | -0.010999 | DOES NOT BEAT |
| mean | extra_trees | 0.764832 | 0.787254 | -0.022422 | DOES NOT BEAT |
| mean | random_forest | 0.725618 | 0.787254 | -0.061636 | DOES NOT BEAT |

### roc_auc (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.970035 | 0.972581 | -0.002546 | DOES NOT BEAT |
| D1 | random_forest | 0.952259 | 0.972581 | -0.020323 | DOES NOT BEAT |
| D2 | extra_trees | 0.996754 | 0.995147 | 0.001607 | BEATS |
| D2 | random_forest | 0.996034 | 0.995147 | 0.000887 | BEATS |
| D3 | extra_trees | 0.955835 | 0.968246 | -0.012412 | DOES NOT BEAT |
| D3 | random_forest | 0.956278 | 0.968246 | -0.011969 | DOES NOT BEAT |
| mean | extra_trees | 0.974208 | 0.978658 | -0.004450 | DOES NOT BEAT |
| mean | random_forest | 0.968190 | 0.978658 | -0.010468 | DOES NOT BEAT |

### winner_top1 (higher is better; reference: logistic_regression (M3 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.634745 | 0.677274 | -0.042529 | DOES NOT BEAT |
| D1 | random_forest | 0.394698 | 0.677274 | -0.282576 | DOES NOT BEAT |
| D2 | extra_trees | 0.911958 | 0.921184 | -0.009227 | DOES NOT BEAT |
| D2 | random_forest | 0.900025 | 0.921184 | -0.021160 | DOES NOT BEAT |
| D3 | extra_trees | 0.608100 | 0.719512 | -0.111412 | DOES NOT BEAT |
| D3 | random_forest | 0.660080 | 0.719512 | -0.059432 | DOES NOT BEAT |
| mean | extra_trees | 0.718268 | 0.772657 | -0.054389 | DOES NOT BEAT |
| mean | random_forest | 0.651601 | 0.772657 | -0.121056 | DOES NOT BEAT |

## 9.1 Comparison vs M4 hist_gradient_boosting (stored M4 artifacts)

### brier (lower is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.029940 | 0.040405 | -0.010465 | BEATS |
| D1 | random_forest | 0.036330 | 0.040405 | -0.004075 | BEATS |
| D2 | extra_trees | 0.011452 | 0.018657 | -0.007204 | BEATS |
| D2 | random_forest | 0.010855 | 0.018657 | -0.007801 | BEATS |
| D3 | extra_trees | 0.027108 | 0.035221 | -0.008113 | BEATS |
| D3 | random_forest | 0.025273 | 0.035221 | -0.009948 | BEATS |
| mean | extra_trees | 0.022833 | 0.031428 | -0.008594 | BEATS |
| mean | random_forest | 0.024153 | 0.031428 | -0.007275 | BEATS |

### expected_calibration_error (lower is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.023618 | 0.037277 | -0.013660 | BEATS |
| D1 | random_forest | 0.024192 | 0.037277 | -0.013085 | BEATS |
| D2 | extra_trees | 0.028414 | 0.015860 | 0.012554 | DOES NOT BEAT |
| D2 | random_forest | 0.024178 | 0.015860 | 0.008318 | DOES NOT BEAT |
| D3 | extra_trees | 0.011111 | 0.032131 | -0.021020 | BEATS |
| D3 | random_forest | 0.009495 | 0.032131 | -0.022636 | BEATS |
| mean | extra_trees | 0.021048 | 0.028423 | -0.007375 | BEATS |
| mean | random_forest | 0.019288 | 0.028423 | -0.009134 | BEATS |

### log_loss (lower is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.098999 | 0.180020 | -0.081021 | BEATS |
| D1 | random_forest | 0.114909 | 0.180020 | -0.065111 | BEATS |
| D2 | extra_trees | 0.048484 | 0.065885 | -0.017401 | BEATS |
| D2 | random_forest | 0.046325 | 0.065885 | -0.019560 | BEATS |
| D3 | extra_trees | 0.096943 | 0.169010 | -0.072067 | BEATS |
| D3 | random_forest | 0.103178 | 0.169010 | -0.065832 | BEATS |
| mean | extra_trees | 0.081475 | 0.138305 | -0.056830 | BEATS |
| mean | random_forest | 0.088137 | 0.138305 | -0.050168 | BEATS |

### pr_auc (higher is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.702003 | 0.652056 | 0.049947 | BEATS |
| D1 | random_forest | 0.526672 | 0.652056 | -0.125385 | DOES NOT BEAT |
| D2 | extra_trees | 0.947478 | 0.842919 | 0.104559 | BEATS |
| D2 | random_forest | 0.940157 | 0.842919 | 0.097239 | BEATS |
| D3 | extra_trees | 0.645016 | 0.645535 | -0.000520 | DOES NOT BEAT |
| D3 | random_forest | 0.710024 | 0.645535 | 0.064489 | BEATS |
| mean | extra_trees | 0.764832 | 0.713503 | 0.051329 | BEATS |
| mean | random_forest | 0.725618 | 0.713503 | 0.012114 | BEATS |

### roc_auc (higher is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.970035 | 0.955186 | 0.014849 | BEATS |
| D1 | random_forest | 0.952259 | 0.955186 | -0.002927 | DOES NOT BEAT |
| D2 | extra_trees | 0.996754 | 0.986718 | 0.010036 | BEATS |
| D2 | random_forest | 0.996034 | 0.986718 | 0.009316 | BEATS |
| D3 | extra_trees | 0.955835 | 0.954798 | 0.001037 | BEATS |
| D3 | random_forest | 0.956278 | 0.954798 | 0.001480 | BEATS |
| mean | extra_trees | 0.974208 | 0.965567 | 0.008641 | BEATS |
| mean | random_forest | 0.968190 | 0.965567 | 0.002623 | BEATS |

### winner_top1 (higher is better; reference: hist_gradient_boosting (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.634745 | 0.569061 | 0.065684 | BEATS |
| D1 | random_forest | 0.394698 | 0.569061 | -0.174364 | DOES NOT BEAT |
| D2 | extra_trees | 0.911958 | 0.811941 | 0.100016 | BEATS |
| D2 | random_forest | 0.900025 | 0.811941 | 0.088083 | BEATS |
| D3 | extra_trees | 0.608100 | 0.553448 | 0.054652 | BEATS |
| D3 | random_forest | 0.660080 | 0.553448 | 0.106632 | BEATS |
| mean | extra_trees | 0.718268 | 0.644817 | 0.073451 | BEATS |
| mean | random_forest | 0.651601 | 0.644817 | 0.006784 | BEATS |

## 9.2 Comparison vs M4 xgboost (stored M4 artifacts)

### brier (lower is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.029940 | 0.035818 | -0.005878 | BEATS |
| D1 | random_forest | 0.036330 | 0.035818 | 0.000513 | DOES NOT BEAT |
| D2 | extra_trees | 0.011452 | 0.017977 | -0.006525 | BEATS |
| D2 | random_forest | 0.010855 | 0.017977 | -0.007122 | BEATS |
| D3 | extra_trees | 0.027108 | 0.029829 | -0.002720 | BEATS |
| D3 | random_forest | 0.025273 | 0.029829 | -0.004556 | BEATS |
| mean | extra_trees | 0.022833 | 0.027874 | -0.005041 | BEATS |
| mean | random_forest | 0.024153 | 0.027874 | -0.003722 | BEATS |

### expected_calibration_error (lower is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.023618 | 0.029583 | -0.005965 | BEATS |
| D1 | random_forest | 0.024192 | 0.029583 | -0.005391 | BEATS |
| D2 | extra_trees | 0.028414 | 0.015060 | 0.013354 | DOES NOT BEAT |
| D2 | random_forest | 0.024178 | 0.015060 | 0.009117 | DOES NOT BEAT |
| D3 | extra_trees | 0.011111 | 0.026147 | -0.015035 | BEATS |
| D3 | random_forest | 0.009495 | 0.026147 | -0.016652 | BEATS |
| mean | extra_trees | 0.021048 | 0.023597 | -0.002549 | BEATS |
| mean | random_forest | 0.019288 | 0.023597 | -0.004308 | BEATS |

### log_loss (lower is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.098999 | 0.139101 | -0.040102 | BEATS |
| D1 | random_forest | 0.114909 | 0.139101 | -0.024192 | BEATS |
| D2 | extra_trees | 0.048484 | 0.060909 | -0.012425 | BEATS |
| D2 | random_forest | 0.046325 | 0.060909 | -0.014584 | BEATS |
| D3 | extra_trees | 0.096943 | 0.127178 | -0.030234 | BEATS |
| D3 | random_forest | 0.103178 | 0.127178 | -0.024000 | BEATS |
| mean | extra_trees | 0.081475 | 0.109063 | -0.027587 | BEATS |
| mean | random_forest | 0.088137 | 0.109063 | -0.020925 | BEATS |

### pr_auc (higher is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.702003 | 0.599194 | 0.102809 | BEATS |
| D1 | random_forest | 0.526672 | 0.599194 | -0.072523 | DOES NOT BEAT |
| D2 | extra_trees | 0.947478 | 0.844031 | 0.103447 | BEATS |
| D2 | random_forest | 0.940157 | 0.844031 | 0.096127 | BEATS |
| D3 | extra_trees | 0.645016 | 0.674199 | -0.029184 | DOES NOT BEAT |
| D3 | random_forest | 0.710024 | 0.674199 | 0.035825 | BEATS |
| mean | extra_trees | 0.764832 | 0.705808 | 0.059024 | BEATS |
| mean | random_forest | 0.725618 | 0.705808 | 0.019809 | BEATS |

### roc_auc (higher is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.970035 | 0.954922 | 0.015113 | BEATS |
| D1 | random_forest | 0.952259 | 0.954922 | -0.002663 | DOES NOT BEAT |
| D2 | extra_trees | 0.996754 | 0.987945 | 0.008809 | BEATS |
| D2 | random_forest | 0.996034 | 0.987945 | 0.008089 | BEATS |
| D3 | extra_trees | 0.955835 | 0.958322 | -0.002488 | DOES NOT BEAT |
| D3 | random_forest | 0.956278 | 0.958322 | -0.002045 | DOES NOT BEAT |
| mean | extra_trees | 0.974208 | 0.967063 | 0.007145 | BEATS |
| mean | random_forest | 0.968190 | 0.967063 | 0.001127 | BEATS |

### winner_top1 (higher is better; reference: xgboost (M4 stored artifacts))

| fold | model | model | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.634745 | 0.491524 | 0.143221 | BEATS |
| D1 | random_forest | 0.394698 | 0.491524 | -0.096826 | DOES NOT BEAT |
| D2 | extra_trees | 0.911958 | 0.803863 | 0.108095 | BEATS |
| D2 | random_forest | 0.900025 | 0.803863 | 0.096162 | BEATS |
| D3 | extra_trees | 0.608100 | 0.626468 | -0.018368 | DOES NOT BEAT |
| D3 | random_forest | 0.660080 | 0.626468 | 0.033612 | BEATS |
| mean | extra_trees | 0.718268 | 0.640618 | 0.077649 | BEATS |
| mean | random_forest | 0.651601 | 0.640618 | 0.010982 | BEATS |

## 10. Comparison vs M2 baseline floor (stored M2 artifacts)

### brier (lower is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.029940 | 0.029318 | 0.000622 | DOES NOT BEAT |
| D1 | random_forest | 0.036330 | 0.029318 | 0.007012 | DOES NOT BEAT |
| D2 | extra_trees | 0.011452 | 0.015613 | -0.004161 | BEATS |
| D2 | random_forest | 0.010855 | 0.015613 | -0.004758 | BEATS |
| D3 | extra_trees | 0.027108 | 0.027562 | -0.000454 | BEATS |
| D3 | random_forest | 0.025273 | 0.027562 | -0.002290 | BEATS |
| mean | extra_trees | 0.022833 | 0.024165 | -0.001331 | BEATS |
| mean | random_forest | 0.024153 | 0.024165 | -0.000012 | BEATS |

### expected_calibration_error (lower is better; baseline: CLASS_PRIOR)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.023618 | 0.000246 | 0.023371 | DOES NOT BEAT |
| D1 | random_forest | 0.024192 | 0.000246 | 0.023945 | DOES NOT BEAT |
| D2 | extra_trees | 0.028414 | 0.000866 | 0.027547 | DOES NOT BEAT |
| D2 | random_forest | 0.024178 | 0.000866 | 0.023311 | DOES NOT BEAT |
| D3 | extra_trees | 0.011111 | 0.000692 | 0.010419 | DOES NOT BEAT |
| D3 | random_forest | 0.009495 | 0.000692 | 0.008803 | DOES NOT BEAT |
| mean | extra_trees | 0.021048 | 0.000602 | 0.020446 | DOES NOT BEAT |
| mean | random_forest | 0.019288 | 0.000602 | 0.018687 | DOES NOT BEAT |

### log_loss (lower is better; baseline: CLASS_PRIOR)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.098999 | 0.214068 | -0.115069 | BEATS |
| D1 | random_forest | 0.114909 | 0.214068 | -0.099159 | BEATS |
| D2 | extra_trees | 0.048484 | 0.211307 | -0.162823 | BEATS |
| D2 | random_forest | 0.046325 | 0.211307 | -0.164982 | BEATS |
| D3 | extra_trees | 0.096943 | 0.211340 | -0.114396 | BEATS |
| D3 | random_forest | 0.103178 | 0.211340 | -0.108161 | BEATS |
| mean | extra_trees | 0.081475 | 0.212238 | -0.130763 | BEATS |
| mean | random_forest | 0.088137 | 0.212238 | -0.124101 | BEATS |

### pr_auc (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.702003 | 0.613725 | 0.088278 | BEATS |
| D1 | random_forest | 0.526672 | 0.613725 | -0.087054 | DOES NOT BEAT |
| D2 | extra_trees | 0.947478 | 0.762168 | 0.185309 | BEATS |
| D2 | random_forest | 0.940157 | 0.762168 | 0.177989 | BEATS |
| D3 | extra_trees | 0.645016 | 0.639359 | 0.005656 | BEATS |
| D3 | random_forest | 0.710024 | 0.639359 | 0.070664 | BEATS |
| mean | extra_trees | 0.764832 | 0.671751 | 0.093081 | BEATS |
| mean | random_forest | 0.725618 | 0.671751 | 0.053867 | BEATS |

### roc_auc (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.970035 | 0.860631 | 0.109405 | BEATS |
| D1 | random_forest | 0.952259 | 0.860631 | 0.091628 | BEATS |
| D2 | extra_trees | 0.996754 | 0.923215 | 0.073539 | BEATS |
| D2 | random_forest | 0.996034 | 0.923215 | 0.072819 | BEATS |
| D3 | extra_trees | 0.955835 | 0.863590 | 0.092245 | BEATS |
| D3 | random_forest | 0.956278 | 0.863590 | 0.092688 | BEATS |
| mean | extra_trees | 0.974208 | 0.882478 | 0.091729 | BEATS |
| mean | random_forest | 0.968190 | 0.882478 | 0.085712 | BEATS |

### winner_top1 (higher is better; baseline: CURRENT_LEADER)

| fold | model | model | baseline | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | extra_trees | 0.634745 | 0.730339 | -0.095594 | DOES NOT BEAT |
| D1 | random_forest | 0.394698 | 0.730339 | -0.335642 | DOES NOT BEAT |
| D2 | extra_trees | 0.911958 | 0.861478 | 0.050480 | BEATS |
| D2 | random_forest | 0.900025 | 0.861478 | 0.038547 | BEATS |
| D3 | extra_trees | 0.608100 | 0.732987 | -0.124887 | DOES NOT BEAT |
| D3 | random_forest | 0.660080 | 0.732987 | -0.072907 | DOES NOT BEAT |
| mean | extra_trees | 0.718268 | 0.774935 | -0.056667 | DOES NOT BEAT |
| mean | random_forest | 0.651601 | 0.774935 | -0.123334 | DOES NOT BEAT |

## 11. Bagged-vs-linear / bagged-vs-boosted family finding

- model-fold comparisons per metric: 6
- comparisons that BEAT the M3 Logistic Regression reference (higher is better for ROC-AUC/PR-AUC/top-1; lower is better for log-loss/Brier/ECE):
  - brier: 2/6
  - expected_calibration_error: 2/6
  - log_loss: 0/6
  - pr_auc: 2/6
  - roc_auc: 2/6
  - winner_top1: 0/6
- changes the M4 conclusion (bagged beats the linear reference on BOTH primary probability metrics in EVERY comparison): **False**
- no combined score is constructed; no significance is claimed.

## 12. Determinism, runtime, latency, memory

- determinism refit (extra_trees/D1): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- determinism refit (random_forest/D1): same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00
- per-fold fit/predict wall time:
  - extra_trees/D1: fit=7.11 s predict_total=10.67 s batch_mean=0.1332 s throughput=177061.8 states/s
  - extra_trees/D2: fit=9.45 s predict_total=10.54 s batch_mean=0.1301 s throughput=187650.7 states/s
  - extra_trees/D3: fit=13.57 s predict_total=12.59 s batch_mean=0.1746 s throughput=152370.0 states/s
  - random_forest/D1: fit=22.64 s predict_total=10.91 s batch_mean=0.1250 s throughput=188541.2 states/s
  - random_forest/D2: fit=35.43 s predict_total=12.92 s batch_mean=0.1555 s throughput=157103.0 states/s
  - random_forest/D3: fit=41.96 s predict_total=12.15 s batch_mean=0.1407 s throughput=189096.9 states/s
- full suite wall time: 370.0 s
- peak RSS: 1.77 GB

## 13. Artifacts

- extra_trees/D1: `47689438c0956cf67cd47f649bfd29b83e7b62cfcee6efa61b414c8d5a3cf147`
- extra_trees/D2: `922678dc9012c84782e431061843363eefe96ec918ad1c8b4259b541fe1cb6a5`
- extra_trees/D3: `0591c83b9c40104c9c88829f3eece5c25a3cfb0eb007c9c3f7284a58313a21aa`
- random_forest/D1: `d8b598b51f7928440446f901abc8069710da6c54ddf5374cda8e85655918eff7`
- random_forest/D2: `cbdf33cb90b0144e05873f95a550d166a7e5f4336a1ed4b0ea82041d77a76ae2`
- random_forest/D3: `fc000bf07b3b19ed91d0ae33f278415cbca5bdb645b7466b88bbce315605224b`

Suite summary: `/Users/tfatharva/f1-in-race-prediction_main/data/v2/model_lab/reports/bagged_candidates_v1.json` (machine-readable; this document was rendered from it).
M3 LOGREG suite: schema v1 (values in §8 loaded from stored M3 artifacts).
M4 nonlinear suite: schema v1 (values in §9 loaded from stored M4 artifacts).
M2 baseline suite: schema v1 (values in §10 loaded from stored M2 artifacts).

## 14. Limitations and M6 implications

- Three development folds is a coarse robustness signal; fold dispersion is reported, not hidden.
- State rows are not independent observations; headline conclusions use race-macro aggregation.
- No tuning was performed: these are representative fixed specifications, not optimized models. M6 may tune inside training history only.
- Raw probabilities only; calibration decisions belong to M7.
- 2025 was not evaluated and must remain protected until the final locked holdout (M17).
- No additional gradient-boosting library was available in this environment and none was added; M5 is scoped to ExtraTrees + RandomForest only.
- M6 recommendation: PROCEED TO M6 (training-history-only tuning) — with constraint: neither fixed, untuned bagged-tree family (ExtraTrees, RandomForest) beats the M3 Logistic Regression reference on any of the six primary comparison metrics (log-loss, Brier, ROC-AUC, PR-AUC, ECE, winner top-1) in any D1/D2/D3 fold, so the M4 finding is unchanged. However, both bagged families do beat the fixed M4 HGB/XGB candidates on race-macro log-loss/Brier/ROC-AUC/PR-AUC/ECE in most folds, so the boosted-tree deficit was at least partly a boosting-vs-bagging effect rather than a pure linear-vs-nonlinear effect. M6 should tune linear and bagged candidates inside training history only, keep 2025 protected, and not promote a tree family on raw M5 evidence.


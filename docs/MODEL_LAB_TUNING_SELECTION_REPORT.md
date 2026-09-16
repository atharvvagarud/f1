# Model Lab Tuning Selection Report (M6)

## DEVELOPMENT MODEL SELECTION
## OUTER EVALUATION: 2022 / 2023 / 2024

## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED

M6 is a controlled, nested temporal tuning stage. It tunes ONLY Logistic Regression and ExtraTrees using chronology-preserving inner folds contained entirely inside each outer training history, selects one configuration per outer fold, refits it on the complete outer TRAIN history, and evaluates the outer validation season exactly once through the frozen M2 evaluator. This is NOT final holdout evaluation.

## 1. Methodology and frozen nested temporal design

- objective: race_macro_log_loss (simple mean over inner folds); lower is better
- outer folds: D1, D2, D3 (development only)
- task: `winner`; feature set: `ALL_84` (full 84-feature surface); seed: 42
- outer validation is NEVER used for scoring, selection, preprocessing, early stopping, calibration or threshold choice; rejected configurations never reach the outer evaluator
- parameter vectors are selected independently per outer fold; the outer result estimates the tuning PROCEDURE, not one global vector
- protocol v1; matrix content hash `d2ee966c18d2…`

## 2. Exact inner folds

| outer fold | inner fold | inner TRAIN | inner VALIDATE |
| --- | --- | --- | --- |
| D1 | D1-I1 | 2018–2020 | 2021 |
| D2 | D2-I1 | 2018–2020 | 2021 |
| D2 | D2-I2 | 2018–2021 | 2022 |
| D3 | D3-I1 | 2018–2020 | 2021 |
| D3 | D3-I2 | 2018–2021 | 2022 |
| D3 | D3-I3 | 2018–2022 | 2023 |

## 3. Exact search spaces (frozen before results)

- Logistic Regression: C in [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]; fixed solver=lbfgs, max_iter=1000, class_weight=None, random_state=42; M3 C=1.0 included
- ExtraTrees: max_features in ['sqrt', 0.5], min_samples_leaf in [1, 3, 10], max_depth in [None, 20] (12 configurations); fixed n_estimators=300, criterion=gini, bootstrap=False, class_weight=None, n_jobs=4, random_state=42; M5 reference configuration included
- no adaptive/Bayesian/random search; every configuration is fit on every inner fold

## 4. Tie-break rule (declared before execution)

- tolerance: 1e-06 absolute on mean inner race-macro log loss
- among configurations whose mean is within tolerance of the best mean, prefer the simpler / more regularized configuration
- LogReg: smaller C (stronger L2 regularization) wins a tie
- ExtraTrees: larger min_samples_leaf, then max_depth=20 over None, then max_features=sqrt over 0.5

## 5. Exact fit budget

- planned estimator fits: 116 (inner 108, outer selected 6, determinism 2)
- actual logistic_regression: inner estimator fits = 36, inner preprocessor fits = 6, outer selected refits = 3
- actual extra_trees: inner estimator fits = 72, inner preprocessor fits = 6, outer selected refits = 3

## 6.1 Inner tuning results — logistic_regression

### logistic_regression / D1: selected `C=0.03` (mean inner log loss 0.097344; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.03 | 0.097344 | 0.000000 | 0.097344 | 0.097344 | 0.000000 |
| C=0.1 | 0.099237 | 0.000000 | 0.099237 | 0.099237 | 0.000000 |
| C=0.3 | 0.100437 | 0.000000 | 0.100437 | 0.100437 | 0.000000 |
| C=1 | 0.100931 | 0.000000 | 0.100931 | 0.100931 | 0.000000 |
| C=10 | 0.101093 | 0.000000 | 0.101093 | 0.101093 | 0.000000 |
| C=3 | 0.100884 | 0.000000 | 0.100884 | 0.100884 | 0.000000 |

### logistic_regression / D2: selected `C=0.03` (mean inner log loss 0.090238; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.03 | 0.090238 | 0.010049 | 0.083132 | 0.097344 | 0.014211 |
| C=0.1 | 0.091157 | 0.011427 | 0.083077 | 0.099237 | 0.016160 |
| C=0.3 | 0.091598 | 0.012501 | 0.082758 | 0.100437 | 0.017680 |
| C=1 | 0.091988 | 0.012648 | 0.083045 | 0.100931 | 0.017887 |
| C=10 | 0.092040 | 0.012804 | 0.082987 | 0.101093 | 0.018107 |
| C=3 | 0.092035 | 0.012515 | 0.083185 | 0.100884 | 0.017699 |

### logistic_regression / D3: selected `C=0.03` (mean inner log loss 0.073816; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| C=0.03 | 0.073816 | 0.029317 | 0.040973 | 0.097344 | 0.056371 |
| C=0.1 | 0.073912 | 0.030943 | 0.039421 | 0.099237 | 0.059815 |
| C=0.3 | 0.074076 | 0.031610 | 0.039032 | 0.100437 | 0.061405 |
| C=1 | 0.074297 | 0.031920 | 0.038915 | 0.100931 | 0.062016 |
| C=10 | 0.074264 | 0.032093 | 0.038711 | 0.101093 | 0.062382 |
| C=3 | 0.074210 | 0.032117 | 0.038560 | 0.100884 | 0.062325 |

## 6.2 Inner tuning results — extra_trees

### extra_trees / D1: selected `max_features=sqrt;min_samples_leaf=3;max_depth=None` (mean inner log loss 0.096479; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| max_features=0.5;min_samples_leaf=10;max_depth=20 | 0.105358 | 0.000000 | 0.105358 | 0.105358 | 0.000000 |
| max_features=0.5;min_samples_leaf=10;max_depth=None | 0.105497 | 0.000000 | 0.105497 | 0.105497 | 0.000000 |
| max_features=0.5;min_samples_leaf=1;max_depth=20 | 0.107430 | 0.000000 | 0.107430 | 0.107430 | 0.000000 |
| max_features=0.5;min_samples_leaf=1;max_depth=None | 0.107708 | 0.000000 | 0.107708 | 0.107708 | 0.000000 |
| max_features=0.5;min_samples_leaf=3;max_depth=20 | 0.106175 | 0.000000 | 0.106175 | 0.106175 | 0.000000 |
| max_features=0.5;min_samples_leaf=3;max_depth=None | 0.106496 | 0.000000 | 0.106496 | 0.106496 | 0.000000 |
| max_features=sqrt;min_samples_leaf=10;max_depth=20 | 0.097190 | 0.000000 | 0.097190 | 0.097190 | 0.000000 |
| max_features=sqrt;min_samples_leaf=10;max_depth=None | 0.096941 | 0.000000 | 0.096941 | 0.096941 | 0.000000 |
| max_features=sqrt;min_samples_leaf=1;max_depth=20 | 0.098358 | 0.000000 | 0.098358 | 0.098358 | 0.000000 |
| max_features=sqrt;min_samples_leaf=1;max_depth=None | 0.097114 | 0.000000 | 0.097114 | 0.097114 | 0.000000 |
| max_features=sqrt;min_samples_leaf=3;max_depth=20 | 0.097055 | 0.000000 | 0.097055 | 0.097055 | 0.000000 |
| max_features=sqrt;min_samples_leaf=3;max_depth=None | 0.096479 | 0.000000 | 0.096479 | 0.096479 | 0.000000 |

### extra_trees / D2: selected `max_features=sqrt;min_samples_leaf=10;max_depth=None` (mean inner log loss 0.095168; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| max_features=0.5;min_samples_leaf=10;max_depth=20 | 0.105357 | 0.000002 | 0.105356 | 0.105358 | 0.000002 |
| max_features=0.5;min_samples_leaf=10;max_depth=None | 0.105191 | 0.000432 | 0.104886 | 0.105497 | 0.000611 |
| max_features=0.5;min_samples_leaf=1;max_depth=20 | 0.112441 | 0.007087 | 0.107430 | 0.117451 | 0.010022 |
| max_features=0.5;min_samples_leaf=1;max_depth=None | 0.112184 | 0.006331 | 0.107708 | 0.116660 | 0.008953 |
| max_features=0.5;min_samples_leaf=3;max_depth=20 | 0.109063 | 0.004084 | 0.106175 | 0.111950 | 0.005775 |
| max_features=0.5;min_samples_leaf=3;max_depth=None | 0.109693 | 0.004522 | 0.106496 | 0.112890 | 0.006394 |
| max_features=sqrt;min_samples_leaf=10;max_depth=20 | 0.095249 | 0.002746 | 0.093307 | 0.097190 | 0.003883 |
| max_features=sqrt;min_samples_leaf=10;max_depth=None | 0.095168 | 0.002508 | 0.093395 | 0.096941 | 0.003546 |
| max_features=sqrt;min_samples_leaf=1;max_depth=20 | 0.099817 | 0.002064 | 0.098358 | 0.101277 | 0.002919 |
| max_features=sqrt;min_samples_leaf=1;max_depth=None | 0.098056 | 0.001333 | 0.097114 | 0.098999 | 0.001885 |
| max_features=sqrt;min_samples_leaf=3;max_depth=20 | 0.096818 | 0.000336 | 0.096580 | 0.097055 | 0.000475 |
| max_features=sqrt;min_samples_leaf=3;max_depth=None | 0.096705 | 0.000318 | 0.096479 | 0.096930 | 0.000450 |

### extra_trees / D3: selected `max_features=sqrt;min_samples_leaf=10;max_depth=None` (mean inner log loss 0.078802; tie-break applied=False)

| configuration | inner mean | std | min | max | range |
| --- | --- | --- | --- | --- | --- |
| max_features=0.5;min_samples_leaf=10;max_depth=20 | 0.085562 | 0.034286 | 0.045972 | 0.105358 | 0.059387 |
| max_features=0.5;min_samples_leaf=10;max_depth=None | 0.085436 | 0.034219 | 0.045925 | 0.105497 | 0.059572 |
| max_features=0.5;min_samples_leaf=1;max_depth=20 | 0.092587 | 0.034750 | 0.052880 | 0.117451 | 0.064571 |
| max_features=0.5;min_samples_leaf=1;max_depth=None | 0.092775 | 0.033913 | 0.053958 | 0.116660 | 0.062702 |
| max_features=0.5;min_samples_leaf=3;max_depth=20 | 0.089607 | 0.033821 | 0.050697 | 0.111950 | 0.061253 |
| max_features=0.5;min_samples_leaf=3;max_depth=None | 0.090200 | 0.033914 | 0.051215 | 0.112890 | 0.061676 |
| max_features=sqrt;min_samples_leaf=10;max_depth=20 | 0.079024 | 0.028169 | 0.046575 | 0.097190 | 0.050615 |
| max_features=sqrt;min_samples_leaf=10;max_depth=None | 0.078802 | 0.028401 | 0.046071 | 0.096941 | 0.050869 |
| max_features=sqrt;min_samples_leaf=1;max_depth=20 | 0.083083 | 0.029021 | 0.049614 | 0.101277 | 0.051662 |
| max_features=sqrt;min_samples_leaf=1;max_depth=None | 0.081532 | 0.028636 | 0.048484 | 0.098999 | 0.050514 |
| max_features=sqrt;min_samples_leaf=3;max_depth=20 | 0.080312 | 0.028589 | 0.047301 | 0.097055 | 0.049754 |
| max_features=sqrt;min_samples_leaf=3;max_depth=None | 0.080190 | 0.028605 | 0.047161 | 0.096930 | 0.049769 |

## 7. Parameter stability across outer folds

- logistic_regression: same configuration every fold = True; distinct = ['C=0.03']; boundary selection = {'D1': True, 'D2': True, 'D3': True}; any boundary = True
- extra_trees: same configuration every fold = False; distinct = ['max_features=sqrt;min_samples_leaf=10;max_depth=None', 'max_features=sqrt;min_samples_leaf=3;max_depth=None']; boundary selection = {'D1': False, 'D2': True, 'D3': True}; any boundary = True

## 8. DEVELOPMENT OUTER RESULTS

**OUTER EVALUATION: 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

## 8.1 logistic_regression

| fold | selected config | log loss | Brier | state-pooled log loss | state-pooled Brier | ROC-AUC | PR-AUC | ECE | top-1 | top-3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | `C=0.03` | 0.083132 | 0.024457 | 0.083435 | 0.024722 | 0.972872 | 0.717549 | 0.010432 | 0.650593 | 0.955517 |
| D2 | `C=0.03` | 0.040973 | 0.010594 | 0.039794 | 0.010154 | 0.994949 | 0.916329 | 0.011628 | 0.908226 | 0.997827 |
| D3 | `C=0.03` | 0.085306 | 0.025289 | 0.088744 | 0.026234 | 0.970865 | 0.764025 | 0.015380 | 0.750339 | 0.881926 |
| mean | — | 0.069804 | 0.020113 | 0.070658 | 0.020370 | 0.979562 | 0.799301 | 0.012480 | 0.769719 | 0.945090 |

Stage race-macro log loss (EARLY / MID / LATE) and synchronized top-k detail:

- logistic_regression/D1: EARLY=0.100557 MID=0.080542 LATE=0.067695
- logistic_regression/D2: EARLY=0.057601 MID=0.036122 LATE=0.029452
- logistic_regression/D3: EARLY=0.107459 MID=0.082962 LATE=0.065473

## 8.2 extra_trees

| fold | selected config | log loss | Brier | state-pooled log loss | state-pooled Brier | ROC-AUC | PR-AUC | ECE | top-1 | top-3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | `max_features=sqrt;min_samples_leaf=3;max_depth=None` | 0.096930 | 0.029234 | 0.095864 | 0.028916 | 0.971125 | 0.714672 | 0.026370 | 0.646089 | 0.968730 |
| D2 | `max_features=sqrt;min_samples_leaf=10;max_depth=None` | 0.046071 | 0.011014 | 0.044961 | 0.010548 | 0.997260 | 0.955235 | 0.025100 | 0.900968 | 0.997622 |
| D3 | `max_features=sqrt;min_samples_leaf=10;max_depth=None` | 0.084781 | 0.024262 | 0.086789 | 0.024852 | 0.963281 | 0.728909 | 0.013673 | 0.689363 | 0.877183 |
| mean | — | 0.075927 | 0.021503 | 0.075871 | 0.021439 | 0.977222 | 0.799606 | 0.021714 | 0.745473 | 0.947845 |

Stage race-macro log loss (EARLY / MID / LATE) and synchronized top-k detail:

- extra_trees/D1: EARLY=0.106498 MID=0.097805 LATE=0.085589
- extra_trees/D2: EARLY=0.059421 MID=0.044689 LATE=0.034236
- extra_trees/D3: EARLY=0.107235 MID=0.083683 LATE=0.063452

## 9. Tuned vs untuned (stored M3/M5 references)

### 9.1 tuned LogReg vs M3 fixed LogReg (C=1.0)

| metric | fold | tuned | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| brier | D1 | 0.024457 | 0.024270 | 0.000187 | DOES NOT BEAT |
| brier | D2 | 0.010594 | 0.010258 | 0.000336 | DOES NOT BEAT |
| brier | D3 | 0.025289 | 0.027720 | -0.002431 | BEATS |
| brier | mean | 0.020113 | 0.020749 | -0.000636 | BEATS |
| expected_calibration_error | D1 | 0.010432 | 0.008397 | 0.002035 | DOES NOT BEAT |
| expected_calibration_error | D2 | 0.011628 | 0.009098 | 0.002531 | DOES NOT BEAT |
| expected_calibration_error | D3 | 0.015380 | 0.019215 | -0.003835 | BEATS |
| expected_calibration_error | mean | 0.012480 | 0.012237 | 0.000244 | DOES NOT BEAT |
| log_loss | D1 | 0.083132 | 0.083045 | 0.000088 | MATCHES |
| log_loss | D2 | 0.040973 | 0.038915 | 0.002058 | DOES NOT BEAT |
| log_loss | D3 | 0.085306 | 0.093433 | -0.008127 | BEATS |
| log_loss | mean | 0.069804 | 0.071797 | -0.001994 | BEATS |
| pr_auc | D1 | 0.717549 | 0.723252 | -0.005703 | DOES NOT BEAT |
| pr_auc | D2 | 0.916329 | 0.917487 | -0.001158 | DOES NOT BEAT |
| pr_auc | D3 | 0.764025 | 0.721023 | 0.043002 | BEATS |
| pr_auc | mean | 0.799301 | 0.787254 | 0.012047 | BEATS |
| roc_auc | D1 | 0.972872 | 0.972581 | 0.000291 | BEATS |
| roc_auc | D2 | 0.994949 | 0.995147 | -0.000198 | DOES NOT BEAT |
| roc_auc | D3 | 0.970865 | 0.968246 | 0.002619 | BEATS |
| roc_auc | mean | 0.979562 | 0.978658 | 0.000904 | BEATS |
| winner_top1 | D1 | 0.650593 | 0.677274 | -0.026681 | DOES NOT BEAT |
| winner_top1 | D2 | 0.908226 | 0.921184 | -0.012958 | DOES NOT BEAT |
| winner_top1 | D3 | 0.750339 | 0.719512 | 0.030827 | BEATS |
| winner_top1 | mean | 0.769719 | 0.772657 | -0.002938 | DOES NOT BEAT |

### 9.2 tuned ExtraTrees vs M5 fixed ExtraTrees

| metric | fold | tuned | reference | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| brier | D1 | 0.029234 | 0.029940 | -0.000706 | BEATS |
| brier | D2 | 0.011014 | 0.011452 | -0.000438 | BEATS |
| brier | D3 | 0.024262 | 0.027108 | -0.002846 | BEATS |
| brier | mean | 0.021503 | 0.022833 | -0.001330 | BEATS |
| expected_calibration_error | D1 | 0.026370 | 0.023618 | 0.002752 | DOES NOT BEAT |
| expected_calibration_error | D2 | 0.025100 | 0.028414 | -0.003314 | BEATS |
| expected_calibration_error | D3 | 0.013673 | 0.011111 | 0.002562 | DOES NOT BEAT |
| expected_calibration_error | mean | 0.021714 | 0.021048 | 0.000667 | DOES NOT BEAT |
| log_loss | D1 | 0.096930 | 0.098999 | -0.002069 | BEATS |
| log_loss | D2 | 0.046071 | 0.048484 | -0.002413 | BEATS |
| log_loss | D3 | 0.084781 | 0.096943 | -0.012163 | BEATS |
| log_loss | mean | 0.075927 | 0.081475 | -0.005548 | BEATS |
| pr_auc | D1 | 0.714672 | 0.702003 | 0.012669 | BEATS |
| pr_auc | D2 | 0.955235 | 0.947478 | 0.007758 | BEATS |
| pr_auc | D3 | 0.728909 | 0.645016 | 0.083894 | BEATS |
| pr_auc | mean | 0.799606 | 0.764832 | 0.034774 | BEATS |
| roc_auc | D1 | 0.971125 | 0.970035 | 0.001090 | BEATS |
| roc_auc | D2 | 0.997260 | 0.996754 | 0.000506 | BEATS |
| roc_auc | D3 | 0.963281 | 0.955835 | 0.007447 | BEATS |
| roc_auc | mean | 0.977222 | 0.974208 | 0.003014 | BEATS |
| winner_top1 | D1 | 0.646089 | 0.634745 | 0.011344 | BEATS |
| winner_top1 | D2 | 0.900968 | 0.911958 | -0.010990 | DOES NOT BEAT |
| winner_top1 | D3 | 0.689363 | 0.608100 | 0.081263 | BEATS |
| winner_top1 | mean | 0.745473 | 0.718268 | 0.027206 | BEATS |

## 10. Head-to-head: tuned LogReg vs tuned ExtraTrees (frozen hierarchy)

| metric | fold | LogReg | ExtraTrees | diff | verdict |
| --- | --- | --- | --- | --- | --- |
| brier | D1 | 0.024457 | 0.029234 | -0.004777 | BEATS |
| brier | D2 | 0.010594 | 0.011014 | -0.000420 | BEATS |
| brier | D3 | 0.025289 | 0.024262 | 0.001027 | DOES NOT BEAT |
| brier | mean | 0.020113 | 0.021503 | -0.001390 | BEATS |
| expected_calibration_error | D1 | 0.010432 | 0.026370 | -0.015938 | BEATS |
| expected_calibration_error | D2 | 0.011628 | 0.025100 | -0.013472 | BEATS |
| expected_calibration_error | D3 | 0.015380 | 0.013673 | 0.001707 | DOES NOT BEAT |
| expected_calibration_error | mean | 0.012480 | 0.021714 | -0.009234 | BEATS |
| log_loss | D1 | 0.083132 | 0.096930 | -0.013797 | BEATS |
| log_loss | D2 | 0.040973 | 0.046071 | -0.005099 | BEATS |
| log_loss | D3 | 0.085306 | 0.084781 | 0.000525 | DOES NOT BEAT |
| log_loss | mean | 0.069804 | 0.075927 | -0.006124 | BEATS |
| pr_auc | D1 | 0.717549 | 0.714672 | 0.002877 | BEATS |
| pr_auc | D2 | 0.916329 | 0.955235 | -0.038906 | DOES NOT BEAT |
| pr_auc | D3 | 0.764025 | 0.728909 | 0.035116 | BEATS |
| pr_auc | mean | 0.799301 | 0.799606 | -0.000305 | DOES NOT BEAT |
| roc_auc | D1 | 0.972872 | 0.971125 | 0.001747 | BEATS |
| roc_auc | D2 | 0.994949 | 0.997260 | -0.002311 | DOES NOT BEAT |
| roc_auc | D3 | 0.970865 | 0.963281 | 0.007584 | BEATS |
| roc_auc | mean | 0.979562 | 0.977222 | 0.002340 | BEATS |
| winner_top1 | D1 | 0.650593 | 0.646089 | 0.004504 | BEATS |
| winner_top1 | D2 | 0.908226 | 0.900968 | 0.007258 | BEATS |
| winner_top1 | D3 | 0.750339 | 0.689363 | 0.060976 | BEATS |
| winner_top1 | mean | 0.769719 | 0.745473 | 0.024246 | BEATS |

- no combined weighted score is constructed; no significance is claimed

## 11. Inner-vs-outer translation

| candidate | fold | ref inner mean | selected inner mean | inner delta | outer tuned | outer reference | outer delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| extra_trees | D1 | 0.097114 | 0.096479 | -0.000634 | 0.096930 | 0.098999 | -0.002069 |
| extra_trees | D2 | 0.098056 | 0.095168 | -0.002888 | 0.046071 | 0.048484 | -0.002413 |
| extra_trees | D3 | 0.081532 | 0.078802 | -0.002730 | 0.084781 | 0.096943 | -0.012163 |
| logistic_regression | D1 | 0.100931 | 0.097344 | -0.003587 | 0.083132 | 0.083045 | 0.000088 |
| logistic_regression | D2 | 0.091988 | 0.090238 | -0.001750 | 0.040973 | 0.038915 | 0.002058 |
| logistic_regression | D3 | 0.074297 | 0.073816 | -0.000481 | 0.085306 | 0.093433 | -0.008127 |

## 12. Determinism

- extra_trees: same experiment id = True; metrics identical = True; max abs probability difference = 1.110e-16
- logistic_regression: same experiment id = True; metrics identical = True; max abs probability difference = 0.000e+00

## 13. Runtime, memory, artifacts

- suite wall time: 1210.7 s
- determinism refit time: 60.7 s
- peak RSS: 1.64 GB

- logistic_regression/D1: `8d8892f436bf76cc24c21059dce6b2c20ab017a463dea2332b1c328606f7bc0f`
- logistic_regression/D2: `4a414a9bbb33d89c037b0071a8f173f848c912f7289e9cd975096de7b44d9821`
- logistic_regression/D3: `2b69455d3418ec2fedf352a29df1c5b2b2efd7e70e62bc1c3cee6916f2ea248a`
- extra_trees/D1: `21e558304973c7bd3cc258d341001feefbd8f199860bf7d744b99fe1b26e1a54`
- extra_trees/D2: `1ac5bc13c459804de55643e3ce671055d993fbad5d60446e4f4dc6b5f4d53707`
- extra_trees/D3: `93fa1e0891342013eb985a9843785538b4ea63dcc941945ac72aeea3cb64623a`

- tuning artifact: `data/v2/model_lab/reports/tuning_selection_v1.json` (machine-readable; this document was rendered from it)
- M3 reference used for 9.1; M5 reference used for 9.2; neither was rerun

## 14. Limitations

- three outer development folds are limited evidence; inner folds are nested and not independent
- state rows are not independent; headline metrics use race-macro aggregation
- tuning is a small predeclared grid, not exhaustive optimization
- raw probabilities only; no calibration was fitted in M6
- 2025 was not evaluated and remains the protected final holdout

## 15. Development candidate selection

**PROMOTE LOGREG TO M7**

- reason: LogReg has the lower aggregate race-macro log loss and is not worse on Brier
- log loss verdict: BEATS; Brier verdict: BEATS
- evidence note: three outer development folds are limited evidence; this is a selected development candidate under the frozen protocol, not a final holdout claim


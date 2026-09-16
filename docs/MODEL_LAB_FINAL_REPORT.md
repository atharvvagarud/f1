# Model Lab Final Report

Phase 3 (Model Lab) culmination: M0-M9.

## Stage history

- **M0** - Frozen experimental protocol: temporal folds D1/D2/D3, protected 2025 holdout, probability metrics, leakage rules.
- **M1** - Reusable experiment infrastructure (data, tasks, splits, predictions, metrics, calibration, aggregation, results).
- **M1.1** - Prediction-semantics correctness guard (independent binary probabilities are never treated as race distributions).
- **M2** - Non-ML baselines (CURRENT_LEADER/ORDER, GRID_POLE, RECENT_PACE, CLASS_PRIOR) on the canonical evaluation path.
- **M3** - Logistic Regression reference (LogReg C=1.0, ALL_84, train-fitted preprocessing).
- **M4** - Boosted-tree candidates (HistGradientBoosting, XGBoost).
- **M5** - Bagged-tree candidates (ExtraTrees, RandomForest).
- **M6** - Nested chronological tuning of LogReg and ExtraTrees inside development folds.
- **M7** - Regularization boundary resolution and global deployment configuration freeze: Logistic Regression C=0.01.
- **M8** - Calibration evaluation (RAW / Platt / isotonic); RAW retained because calibrated alternatives did not clear the predeclared guards.
- **M9** - Final development fit on all eligible 2018-2024 rows + one-shot protected 2025 holdout evaluation; Model Lab freeze.

## What was tried and rejected

- M2 factual baselines were sanity references, not candidates.
- M3 LogReg C=1.0 was a reference, not the final configuration.
- M4 boosted trees and M5 bagged trees (ExtraTrees/RandomForest) were rejected in favour of the simpler linear model on probability quality and operational cost.
- M6 nested chronological tuning selected candidates but did not justify a tree model over LogReg.
- M7 resolved the regularization boundary and froze C=0.01.
- M8 rejected Platt and isotonic calibration; RAW was retained because the calibrated alternatives did not clear the predeclared guards.

## Why Logistic Regression, C=0.01, RAW

- LogReg gave competitive development probability quality at the lowest complexity/cost class (M4/M5/M6 comparisons).
- C=0.01 was the M7 global development-only freeze rule outcome (aggregate inner log-loss fallback; no strict per-fold majority).
- RAW won the M8 predeclared calibration-selection rule; no calibration layer was justified.

## Development evidence (frozen references)

- M7 frozen-global outer (D1/D2/D3): race-macro log loss 0.071374, Brier 0.020662, ROC-AUC 0.979514, PR-AUC 0.796692, top-1 0.7629.
- M8 RAW (base C=0.01, calibration season withheld): race-macro log loss 0.077027, Brier 0.022289, ROC-AUC 0.976148, PR-AUC 0.772915, top-1 0.7505.

## Protected 2025 holdout (one-shot)

FINAL_FIT: 2018-2024 (149 races, 162728 eligible states).
HOLDOUT: 2025 (24 races, 26692 eligible states).

- race-macro log loss: 0.068035
- race-macro Brier: 0.020014
- state-pooled log loss: 0.067893
- state-pooled Brier: 0.019859
- ROC-AUC: 0.984526
- PR-AUC: 0.803238
- ECE: 0.011108
- synchronized top-1: 0.7961
- synchronized top-3: 0.9790

## Stage breakdown (race-macro log loss)

- EARLY: 0.077468
- MID: 0.069800
- LATE: 0.056847

## Holdout-development differences (descriptive)

- expected_calibration_error: -0.003711 (holdout minus M7)
- race_macro_brier: -0.000648 (holdout minus M7)
- race_macro_log_loss: -0.003339 (holdout minus M7)
- race_macro_pr_auc: 0.006546 (holdout minus M7)
- race_macro_roc_auc: 0.005012 (holdout minus M7)
- state_pooled_brier: -0.001028 (holdout minus M7)
- state_pooled_log_loss: -0.004308 (holdout minus M7)
- winner_top1: 0.033201 (holdout minus M7)
- winner_top3: 0.029362 (holdout minus M7)

GENERALIZATION / HOLDOUT-DEVELOPMENT DIFFERENCES, descriptive only. Training design differs (single all-data fit predicting one season ahead vs multi-fold development evidence with less training data), so differences are not an overfitting diagnosis and carry no statistical certainty claim.

## Latency and memory (measured)

- final preprocessing fit: 1.1356 s
- final model fit: 0.3587 s
- holdout transform: 0.0557 s
- holdout prediction: 0.0557 s
- canonical evaluation: 10.1959 s
- batch throughput: 478741.84 states/s
- single-state latency (mean): 0.008571 s
- peak RSS: 1907621888 bytes

## Leakage protections

- 2025 was protected throughout M0-M8 and unlocked exactly once in M9 with explicit opt-in;
- preprocessing is fit on FINAL_FIT training rows only;
- the frozen mask defines eligibility; labels/masks never enter the design matrix;
- metrics/preprocessing/feature ordering come from frozen Phase-2/M0 artifacts, never re-derived.

## Probability semantics

The winner model emits independent per-driver binary probabilities (BINARY_PROBABILITY / INDEPENDENT_BINARY). They are NOT normalized to sum to 1 across a race and must not be treated as a categorical race distribution.

## Reproducibility

- specification fingerprint: `3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d`
- model fingerprint: `81e0e4beb24287f9b532230fc0da157f3f261b9b034440651d071fbe8dd2076d`
- matrix content hash: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- protocol semantic hash: `0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce`
- protected experiment id: `8359600e9ae092a99555cb7a84619114721ade7e1083b9fb96b0cfe649aab070`

## Final model specification

LogisticRegression, C=0.01, solver=lbfgs, max_iter=1000, class_weight=None, random_state=42; feature set ALL_84; train-fitted preprocessing; calibration RAW; independent binary probability semantics.

## Limitations

- Independent per-driver winner probabilities; no mutually exclusive race distribution.
- FastF1-era data/label limitations apply.
- Telemetry and reliability/DNF modelling remain deferred.
- Model performance varies by race stage.
- Development hyperparameter uncertainty is documented in M7.
- The protected holdout is a single season (24 races).
- No post-holdout tuning, calibration or model change occurred.

The frozen pipeline was evaluated exactly once on 2025 and no post-holdout tuning, calibration, thresholding, feature selection, model switching or ablation was performed.

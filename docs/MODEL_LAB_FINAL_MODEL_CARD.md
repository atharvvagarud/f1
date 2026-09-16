# Model Lab Final Model Card

## MODEL

Logistic Regression (`LogisticRegression`, C=0.01).

## TASK

In-race winner binary probability: `is_winner` under `eligible_is_winner`.

## DATA

Rich FastF1 canonical driver-state matrix, 2018-2025.
- development / final fit: 2018-2024 (149 races, 162728 eligible states, 8926 positives)
- protected holdout: 2025 (24 races, 26692 eligible states, 1444 positives)

## FEATURES

`ALL_84` temporally safe feature set (84 predictive features; train-fitted median imputation + StandardScaler for numeric, most-frequent + float cast for boolean, constant `MISSING` + train-fitted one-hot for categorical).

## MODEL SPEC

- estimator: `LogisticRegression`
- C: 0.01
- solver: lbfgs
- max_iter: 1000
- class_weight: None
- random_state: 42
- penalty: l2 (sklearn default, not passed explicitly)
- project seed: 42
- fingerprint: `3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d`

## CALIBRATION

RAW selected because the M8 calibration alternatives (Platt, isotonic) did not improve development probability quality under the predeclared selection rule. No calibrator is fitted or applied.

## PROBABILITY SEMANTICS

Independent per-driver binary probability. The model does NOT output a mutually exclusive race distribution and its probabilities are not normalized to sum to 1 across a race. Synchronized top-k uses the frozen race adapter on these independent probabilities.

## EVALUATION

Development protocol: expanding-window chronological folds D1-D3 (M2-M8), headline race-macro aggregation.
One-shot protected 2025 holdout (M9), first and only sanctioned target evaluation.

## 2025 PROTECTED HOLDOUT (HEADLINE)

- race-macro log loss: 0.068035
- race-macro Brier: 0.020014
- state-pooled log loss: 0.067893
- state-pooled Brier: 0.019859
- ROC-AUC: 0.984526
- PR-AUC: 0.803238
- ECE (10 equal-width bins): 0.011108
- synchronized top-1: 0.7961
- synchronized top-3: 0.9790

## LIMITATIONS

- independent winner probabilities, not a categorical race distribution;
- FastF1-era data limitations;
- two known Phase-1 partial sessions retained (not dropped);
- telemetry modelling deferred;
- reliability/DNF modelling deferred;
- performance varies by race stage;
- development hyperparameter uncertainty documented in M7;
- the holdout is one season (24 races); no post-holdout tuning.

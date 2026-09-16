# Model Lab M1.1 Correctness Patch (pre-M2 remediation)

Narrowly scoped fix of four findings from the independent pre-M2 correctness
audit. No M2 work, no training, no 2025 evaluation, no M1 refactor, no
general cleanup. Frozen contracts unchanged: `MODEL_LAB_PROTOCOL_VERSION =
v1`, protocol semantic hash
`0168f1d7…3ef53ce`, matrix content hash `d2ee966c…92799db`,
`FEATURE_SET_VERSION = v8`, `LABEL_SET_VERSION = v1`, `MATRIX_VERSION = v1`.

## F1 — PR-AUC / average precision tie handling (`v2/model_lab/metrics.py`)

Old code accumulated precision at every positive in input order, so tied
scores were order-dependent (`[1,0,1,0,1,0]` @ all-0.5 gave ~0.7556).
New code groups equal scores into one distinct-threshold step and
accumulates `(recall - prev_recall) * precision` from whole-group counts —
standard average-precision semantics (option B; sklearn is deliberately not
imported because the frozen M0 non-modeling guard forbids sklearn sources in
`v2/model_lab`). Frozen one-class contract kept: no positives -> `None`.
Parity: 4000 randomized tie-heavy cases vs
`sklearn.metrics.average_precision_score`, 0 mismatches (>1e-12); committed
tests cover all-tied, grouped ties, no ties, perfect, reversed, imbalance,
one-class.

## F2 — metric applicability contract (`v2/model_lab/metrics.py`)

`require_metric_applicability(kind, metric_name)` is the ONE canonical guard
at the semantic evaluation boundary; `evaluate_metric(prediction,
metric_name, y_true, y_pred)` = guard + dispatch. Raw primitives (`brier`,
`compute_metric`, …) stay mathematical primitives — M2 must not call them
with raw arrays but route through the guard with the `PredictionResult`.

| Kind | Allowed |
| --- | --- |
| `BINARY_PROBABILITY` | `log_loss`, `brier`, `roc_auc`, `pr_auc`, `expected_calibration_error`/`ece`, `calibration_report`, `reliability_bins` |
| `RANKING_SCORE` | `roc_auc`, `pr_auc` only (NOT `log_loss`/`brier`/calibration, even for values in [0, 1]) |
| `CONTINUOUS_PREDICTION` | `mae`, `rmse`, `spearman` |
| `ORDINAL_PREDICTION` | `mae`, `rmse`, `spearman` |
| `MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION` | only `race_level_log_loss`, which is not implemented in M1/M1.1 — requesting it fails loudly instead of inventing a metric |

Unsupported combinations raise `UnsupportedMetricError` (never a silent
number). Tests prove `[0.9, 0.1]` `RANKING_SCORE` cannot reach
Brier/log-loss/ECE while identical `BINARY_PROBABILITY` values evaluate
normally.

## F3 — finite-input contract (`v2/model_lab/metrics.py`)

`mae`/`rmse`/`spearman` share `_finite_pair`, which raises
`InvalidPredictionError` on any NaN/+inf/-inf in `y_true` or `y_pred`
(no silent observation dropping; task masks untouched). Empty/singleton
behaviour unchanged (`nan`/`None`). Finite parity vs sklearn/scipy
committed in tests.

## F4 — synchronized winner top-k eligibility (`v2/model_lab/winner.py`)

A snapshot at time T (unchanged `RaceIndex` rule: latest state with
`state_time_s <= T`; no same-lap fallback, no future state, no retirement
inference, stale/lapped drivers kept) is eligible only when (a) the eventual
winner is observable **with a prediction** at T, and (b) >= 2 drivers are
observable with predictions. The >= 2 floor is the smallest semantically
defensible rule (a ranking needs a field); no arbitrary roster minimum was
introduced — coverage is instead reported relative to the factual roster
(`roster_size`, `min/mean_observable_field_size` per output and per race).
Skips are counted separately: `n_skipped_no_predictions`,
`n_skipped_winner_unobservable`, `n_skipped_degenerate` (top level and per
race). Headline top-k accuracies share the eligible denominator; a strict
k-way claim additionally needs observable_field_size >= k (see
`min_observable_field_size` — a 2-driver field cannot discriminate top-3).

## F5 — CLASS_PRIOR provenance (`v2/model_lab/baselines.py`)

Implementation unchanged (no provenance framework). Train-only contract now
explicit on the generator, the `CLASS_PRIOR` baseline description, and
`run_baseline`: **`train_y` MUST be `ExperimentDataset.y_train` only**.
M2 handoff: the M2 runner owns train/validation materialization and must
pass only the training target.

## Tests

`tests/test_v2_model_lab_m1_1.py` (27 tests, synthetic only, no 2025):
PR-AUC (7 incl. sklearn parity), semantic guard (5), non-finite (4 incl.
sklearn/scipy parity), winner top-k (7: single-driver roster, early
unobservable rival, 2-driver top-3 coverage signal, stale-rival +
future-state protection, timestamp boundary, kind rejection).

## Verification

- M1.1 focused: 27 passed.
- M0 + M1 + M1.1: 102 passed.
- Phase-2 RaceIndex/temporal tests: see final report.
- Full regression + D11 + frontend/typecheck/lint/build: see final report
  (each run once at final verification).

## M2 implications

- Consume `require_metric_applicability` / `evaluate_metric` — do not build
  a second applicability system.
- `CLASS_PRIOR` must receive `ExperimentDataset.y_train` only.
- For winner top-k, consult `min_observable_field_size` before claiming
  k-way discrimination; respect `n_skipped_*` accounting.

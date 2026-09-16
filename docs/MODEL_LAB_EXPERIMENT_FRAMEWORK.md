# Model Lab Experiment Framework (Phase 3 — M1)

> **Status: M1 — infrastructure complete. M0–M9 complete; Model Lab FROZEN
> (final model: ALL_84 → train-fitted preprocessing → LogisticRegression
> C=0.01, RAW — see `docs/MODEL_LAB_FINAL_MODEL_CARD.md`). This document
> describes the reusable execution infrastructure built on
> top of the frozen M0 protocol.** Later stages must route *all* splitting,
> masking, metric computation, aggregation, identity and serialization
> through these modules.
>
> Frozen contract: `docs/MODEL_LAB_PROTOCOL.md`,
> `docs/generated/model_lab_protocol_v1.json`.
> M0 semantic hash: `0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce`.

------------------------------------------------------------------------

## 1. Purpose

M0 froze *how* Phase 3 evaluates models. M1 makes that protocol
executable so that later model experiments are boring and reproducible:
one canonical evaluation path, no per-model splitting/metric/holdout code.

## 2. M0 contract consumed

`MODEL_LAB_PROTOCOL_VERSION=v1`; `FEATURE_SET_VERSION=v8` (84);
`LABEL_SET_VERSION=v1`; `MATRIX_VERSION=v1`; `ABLATION_CONFIG_VERSION=v1`;
matrix 189,420 × 106, content hash
`d2ee966c…`; folds D1 (2018–2021→2022), D2 (2018–2022→2023),
D3 (2018–2023→2024); FINAL_FIT 2018–2024; protected holdout 2025;
primary task `winner`. `verify_phase2_artifacts()` and the M0 tests are
re-run before and after M1; no Phase-2 artifact or M0 definition changed.

## 3. Package architecture

```
v2/model_lab/
    protocol.py      M0 frozen protocol (unchanged)
    audit.py         M0 split/task count audit (unchanged)
    errors.py        contract error hierarchy
    data.py          canonical read-only loader + dtype schema + feature sets
    tasks.py         frozen task resolver
    splits.py        fold/holdout resolver + dataset materialization
    predictions.py   typed prediction results + identity alignment
    metrics.py       probability + ordinal/regression metrics
    calibration.py   reliability bins + ECE (evaluation only)
    stages.py        EARLY/MID/LATE partitioning
    aggregation.py   race-macro / state-pooled / fold / stage aggregation
    baselines.py     M0 non-ML prediction baselines
    winner.py        synchronized winner top-k adapter (RaceIndex)
    timing.py        timers + latency summary
    experiment.py    typed config, experiment identity, result schema
    results.py       deterministic serialization + environment metadata
```

No module constructs, tunes or trains a candidate estimator.

## 4. Matrix loading

`data.load_canonical(paths, verify_content_hash=, verify_bytes=)` returns
one validated, process-cached `CanonicalMatrix` (read-only). It verifies
`MATRIX_VERSION`, `FEATURE_SET_VERSION`, `LABEL_SET_VERSION`, counts and
the content hash, and exposes `predictive_columns`, `label_columns`,
`metadata_columns`, `task_eligibility_columns`, `schema`, `select_seasons`
and `race_ids`. Source artifacts are never mutated.

## 5. Feature resolution

All selection goes through the F16 contract:
`data.resolve_features(name, canonical)` → ordered tuple from
`resolve_feature_set(name, manifest)`. `ALL_84`, cumulative, LOGO,
`CURRENT_ORDER_ONLY` and `MINIMAL_RACE_STATE` are supported; unknown sets
raise `UnknownFeatureSetError`. Dataframe column dropping is not a
selector.

## 6. Task resolution

`tasks.resolve_task(name)` → `ResolvedTask` (label column, eligibility
mask, kind, metric set, tier, probability semantics). Winner → `is_winner`
/ `eligible_is_winner` / binary / `INDEPENDENT_BINARY`; final_position →
ordinal with `eligible_ordinal_final_position`; position_change →
regression with `eligible_gain_loss`. DNF raises `UnknownTaskError`.

## 7. Temporal split engine

`get_split(fold_id)` returns `SplitSpec` for D1/D2/D3/FINAL_FIT/HOLDOUT.
`validate_split` asserts no race overlap, strict training-before-validation
chronology and no 2025 in development/final-fit. `split_frame` returns the
train/validation frames. No sklearn random splitter is used anywhere.

## 8. Protected holdout guard

`get_split("HOLDOUT")` raises `ProtectedHoldoutError`; only
`allow_protected_holdout=True` resolves it, and `validate_split` then
permits 2025. `winner.synchronized_winner_top_k` refuses 2025 unless the
same explicit flag is set. Accidental `fold="2025"` raises
`UnknownFoldError`/`ExperimentConfigError`. M1 resolves 2025 **counts**
only and computes no 2025 target performance.

## 9. Dataset materialization

`splits.materialize(canonical, task, fold_id, feature_set)` applies the
frozen task mask *before* selecting data and returns an
`ExperimentDataset`: `X_train`, `y_train`, `train_metadata`,
`X_validation`, `y_validation`, `validation_metadata`, feature names and
per-side `{states, eligible, positives, coverage}` counts. Identity
metadata (`state_id`, `race_id`, `driver_id`, `lap_number`,
`state_time_s`, `season`, `round_no`, …) is always preserved; identity is
never placed in `X`.

## 10. Prediction semantics

`predictions.PredictionResult` types outputs as `BINARY_PROBABILITY`,
`CONTINUOUS_PREDICTION`, `ORDINAL_PREDICTION`, `RANKING_SCORE` or
`MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION`, with `ProbabilitySemantics`
(`POSITIVE_CLASS_PROBABILITY`, `INDEPENDENT_BINARY`,
`MUTUALLY_EXCLUSIVE_RACE`). Independent per-driver probabilities stay
marked `INDEPENDENT_BINARY`; `require_race_distribution` rejects them where
a race distribution is required. No implicit normalization exists.

## 11. Prediction alignment

`predictions.align(prediction, expected_state_ids)` realigns by canonical
`state_id` and fails loudly on duplicate, missing or extra ids. Nothing is
matched positionally.

## 12. Metrics

`metrics` implements log loss (fixed epsilon `1e-15`, original
probabilities preserved for other metrics), Brier, ROC-AUC, PR-AUC,
MAE, RMSE, Spearman. Probabilities must be finite in `[0, 1]`; ranking
metrics accept any finite score. One-class slices return `None` for
AUC-style metrics. Unknown/wrong-kind metrics raise `UnsupportedMetricError`.

## 13. Calibration evaluation

`calibration.reliability_bins` (counts, mean predicted, observed
frequency, weight) and `expected_calibration_error` use the frozen
10 equal-width `[0, 1]` bins. Evaluation only — no calibrator is fitted.

## 14. Stage evaluation

`stages.stage_partition` assigns EARLY `[0, 1/3)`, MID `[1/3, 2/3)`,
LATE `[2/3, 1]`; exactly 1/3 → MID, exactly 2/3 → LATE, 1.0 → LATE.
Null/out-of-range input raises.

## 15. Race-macro aggregation

`aggregation.scoped_metric(...)` returns both scopes:
`race_macro` (compute the row metric within each race, then average races
equally — the headline) and `state_pooled` (metric over all states —
diagnostic). Races are never weighted by row count.

## 16. Fold aggregation

`aggregation.aggregate_folds({...})` returns per-fold values plus
mean/std(ddof=1)/min/max/range. Cross-fold performance is never reported
as one pooled validation number.

## 17. Winner race-level evaluation

`winner.synchronized_winner_top_k(predictions, canonical, ...)` evaluates
top-1/top-3 at synchronized race states by reusing Phase-2 `RaceIndex`
(latest rival state with `state_time_s <= T`). It refuses `INDEPENDENT_BINARY`
input for race-distribution-only paths and refuses 2025 without explicit
intent. It is not run on the holdout in M1.

## 18. Baseline interface

`baselines.Baseline` declares supported tasks, required factual columns,
train dependence and output semantics; `generate` returns aligned
`PredictionResult`s. Implemented: `CURRENT_LEADER`, `CURRENT_ORDER`,
`GRID_POLE`, `RECENT_PACE` (ranking score, not a probability),
`CLASS_PRIOR` (prevalence from train only). Baselines are generators, not
estimators.

## 19. Experiment configuration

`experiment.ExperimentConfig` (typed) validates protocol/version/hash
drift, task, fold, seed and split policy via M0. `build_config(...)`
constructs validated configs. Unknown values fail loudly.

## 20. Experiment identity

`ExperimentConfig.experiment_id` is the deterministic M0 hash over
protocol version, Phase-2 commit, all Phase-2 versions, matrix content
hash, feature set, task, fold, model family, model parameters,
preprocessing config, calibration config and seed. Timestamps, paths and
environment do not affect identity.

## 21. Result schema

`experiment.ExperimentResult` records status, fit/prediction seconds,
latency summary, metrics, calibration, stage metrics, race metrics,
artifact refs, warnings, environment and error — all optional/nullable,
none fabricated. `RESULT_SCHEMA_VERSION`/`CONFIG_SCHEMA_VERSION` gate
unknown documents.

## 22. Serialization

`results.write_experiment` writes `config.json` + `result.json` under
`data/v2/model_lab/experiments/protocol=v1/<experiment_id>/` using an
atomic tmp → fsync → replace write. `read_experiment` round-trips and
rejects unknown schema versions. The run tree is gitignored
(`/data/v2/`); Phase-2 artifact directories are never written.

## 23. Environment metadata

`results.environment_metadata` captures Python version, platform, system,
machine, processor, git commit and dirty state. It is recorded in results
only, never in identity.

## 24. Timing

`timing.Timer`, `timed_call` (monotonic clock, warm-up + repeats) and
`latency_summary` (count/mean/min/max/p50/p95/p99) from real samples only.
No candidate is benchmarked in M1.

## 25. Preprocessing contract

`experiment.PreprocessingContract` declares numeric/categorical
imputation, scaling/encoding and native support flags; `to_dict` stamps
`fit_scope: training only`. M1 stores the declaration and fits nothing;
the declaration participates in experiment identity.

## 26. Future model adapter contract

`experiment.ModelAdapter` (typing `Protocol`) defines `family`, `fit`,
`predict` and `predict_positive_probability`. It is a contract only — no
candidate estimator exists in M1. It keeps framework code decoupled from
any ML library.

## 27. Error handling

`errors` provides: `ProtocolDriftError`, `MatrixContractError`,
`ProtectedHoldoutError`, `UnknownTaskError`, `UnknownFeatureSetError`,
`UnknownFoldError`, `UnknownBaselineError`, `ExperimentConfigError`,
`InvalidPredictionError`, `PredictionAlignmentError`,
`UnsupportedMetricError`, `ResultSchemaError`, all under `ModelLabError`.
No silent fallbacks (feature set, mask, fold, rows, normalization) exist.

## 28. Reproducibility

`PROJECT_SEED = 42` flows from M0; `validate_seed` is enforced in config.
Deterministic mergesort ordering, deterministic experiment IDs and atomic
JSON make runs reproducible. Cross-library/hardware bitwise identity is not
claimed.

## 29. Test strategy

`tests/test_v2_model_lab_m1.py` (44 tests, ~2 s): loader/hash/order,
feature-set resolution, dtype schema, task masks + DNF rejection, folds +
counts vs M0 audit, holdout guard, materialization, metrics + invalid
inputs + one-class slices, calibration, stage boundaries, race-macro vs
state-pooled, fold aggregation, prediction semantics + alignment,
baselines, experiment identity/config/results, timing, synchronized winner
top-k, and static guards (no random split, no candidate estimator).
Tiny synthetic fixtures are used for behaviour; F16 fixtures remain test
aids only.

## 30. Performance

The 24 MB matrix is loaded and validated once per process
(`data._CACHE`); per-call consumers copy only the selected slices/columns.
`verify_content_hash` is opt-in (tests/entry checks); iteration paths skip
the byte hashing. No distributed or caching subsystem is introduced.

## 31. Limitations

- `CURRENT_ORDER`/`GRID_POLE` use a factual top-10 points cutoff for the
  frozen rich era; the ordinal `CURRENT_ORDER` variant is omitted (294
  null-position states), and `RECENT_PACE` is a ranking score, not a
  probability — these are documented rather than invented.
- No full baseline/dev-fold leaderboard is produced in M1.
- Synchronized winner top-k is implemented and fixture-tested, not run on
  full data or 2025.
- LightGBM/CatBoost/torch remain unavailable until the approved M5
  dependency decision.

## 32. M2 handoff

M2 builds the config-driven runner on this infrastructure: compose
`ExperimentConfig`, use `materialize` + an adapter implementing
`ModelAdapter`, evaluate through `metrics`/`aggregation`/`calibration`,
and serialize via `results.write_experiment`. M2 must not re-implement
splitting/masking/metrics/identity or access 2025.

## 33. M1 definition of done

All DoD items pass (see M1 Final Report): loader, feature/task resolution,
masks, temporal splits, D1/D2/D3 counts matching M0, FINAL_FIT, holdout
guard, materialization + identity metadata, dtype contract, typed
prediction semantics + alignment, metrics/calibration/stages, race-macro +
state-pooled + fold aggregation, winner top-k infrastructure, baselines
(CLASS_PRIOR train-only), typed config + deterministic ID + result schema
+ serialization + environment + timing + preprocessing/adapter contracts,
clear errors, no estimator/prediction/2025 metric, focused tests green.

# Model Lab Protocol (Phase 3 — M0)

> **Status: M0 — protocol frozen. M0–M9 complete; Model Lab FROZEN
> (see `docs/MODEL_LAB_FINAL_REPORT.md`). This document is unchanged since
> M0 and remains the experimental constitution for the Phase-3 Model Lab.**
> This document is the experimental constitution for the Phase-3 Model Lab.
> It freezes tasks, eligibility, chronological folds, the protected final
> holdout, metrics, baselines, preprocessing/calibration boundaries,
> selection rules, experiment recording, reproducibility and Phase-2
> immutability **before any candidate result is observed**.
>
> Machine-readable artifact: `docs/generated/model_lab_protocol_v1.json`
> (`MODEL_LAB_PROTOCOL_VERSION = "v1"`, semantic hash
> `0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce`).
> Split/task count evidence: `docs/generated/model_lab_split_audit_v1.json`.
>
> M0 trains no model, fits no preprocessor/calibrator, computes no candidate
> metric and inspects no 2025 target performance.

------------------------------------------------------------------------

## 1. Executive summary

Phase 3 exists because the original university project compared
Logistic Regression / HistGradientBoosting / XGBoost with **race-grouped
cross-validation at fixed lap checkpoints** — legitimate historical
evidence, but not sufficient for production claims. V2 requires strict
temporal evaluation: a model predicting a historical race must be trained
only on races that happened before it.

M0 freezes that evaluation protocol. It is the plan's "M0 Verify Feature
Engine" **merged with** "M1 Freeze Temporal Evaluation Protocol" per the
M0 mission, so that the next stage (M1 — experiment framework) can be built
against a fixed contract.

The protocol is deliberately lightweight: `v2/model_lab/` contains
`protocol.py` (frozen constants, contracts, validation, deterministic
export) and `audit.py` (split/task **counts** only). No estimator is
constructed or fitted anywhere in M0.

**M0 result: READY FOR M1** (see §47).

------------------------------------------------------------------------

## 2. Why temporal evaluation is required

F1 is temporal and the matrix grain is driver-state (driver-lap). Rows are
strongly dependent within a race and within a driver. Random row-level
splits, shuffled `train_test_split`, and random KFold over states would put
near-duplicate laps of the same race into both train and evaluation and
inflate apparent precision. Therefore:

- evaluation operates on **race chronology**, never on row order;
- for every development fold, all training races occur strictly before all
  validation races;
- 2025 is a protected final holdout.

------------------------------------------------------------------------

## 3. Frozen Phase-2 inputs

| Input | Value |
|---|---|
| `FEATURE_SET_VERSION` | `v8` (84 predictive definitions) |
| `LABEL_SET_VERSION` | `v1` (7 targets) |
| `MATRIX_VERSION` | `v1` (189,420 × 106) |
| `ABLATION_CONFIG_VERSION` | `v1` |
| matrix content hash | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| ablation semantic hash | `c88bcbaafe72ff2a615f24563d631f4e313cbc1d41e23b3818d3f9d86f6b087c` |
| Phase-1 freeze | tag `v2-data-platform-phase1` @ `2fa0a7c` |
| Phase-2 freeze | tag `v2-temporal-feature-engine-phase2` @ `adb558395c07733e5f0f5051a92714d8b037951c` |
| races / seasons | 173 / 2018–2025 |
| partial races | Belgium 2021 (`2021-r12-R`), Japan 2022 (`2022-r18-R`) |
| telemetry | absent (ADR-0001) |

`verify_phase2_artifacts()` re-derives these from the frozen manifest,
recomputes the content hash, and re-hashes the Parquet/manifest/ablation
bytes. Any disagreement raises `ModelLabProtocolError`; M0 never repairs
Phase 2.

------------------------------------------------------------------------

## 4. Modeling task inventory

Phase-2 materializes six tasks via `TASKS` and five eligibility masks.
The Model-Lab inventory adds the frozen `position_change_from_state`
regression and records DNF as deferred.

| Task | Target | Kind | Tier | Eligibility mask |
|---|---|---|---|---|
| **winner** | `is_winner` | binary | **PRIMARY** | `eligible_is_winner` |
| podium | `is_podium` | binary | SECONDARY | `eligible_is_podium` |
| points | `scored_points` | binary | SECONDARY | `eligible_scored_points` |
| final_position | `final_position` | ordinal | SECONDARY | `eligible_ordinal_final_position` |
| position_change | `position_change_from_state` | regression | SECONDARY | `eligible_gain_loss` |
| gain | `gains_position_by_finish` | binary | SECONDARY | `eligible_gain_loss` |
| loss | `loses_position_by_finish` | binary | SECONDARY | `eligible_gain_loss` |
| **dnf** | *(none)* | — | **DEFERRED** | *(none)* |

Not every label is a primary modeling task. DNF stays deferred because
Phase 2 defines no DNF event target; M0 invents none. `position_change`
reuses the frozen `eligible_gain_loss` mask (identical to
`position_change_from_state.notna()`), never an ad-hoc condition.

------------------------------------------------------------------------

## 5. Primary task

**PRIMARY TASK = `winner`.**

Rationale: the product is an in-race winner predictor and downstream
Monte Carlo/strategy consume credible P(win); winner is the only task with
an exactly-one-per-race structure. Secondary tasks are modeled separately;
the protocol does **not** require one estimator to win every task, and
ranking is task-specific. The headline "best model" decision is driven by
the winner task under the §32 selection rule.

------------------------------------------------------------------------

## 6. Observation grain / row dependence

Grain is **driver-state (driver-lap)**. Individual rows are **not**
independent observations: consecutive laps of a driver and concurrent
states of a race are highly correlated. N = 189,420 is a count of states,
not independent samples. Headline conclusions use race-level aggregation,
temporal folds and race-level uncertainty; correlation/importance against
2025 targets is forbidden in M0.

------------------------------------------------------------------------

## 7. Canonical race chronology

Chronology is built from factual metadata only:

```
(season, round_no, race_id)
```

Never filesystem order, row order, or label outcomes. Verified: 173 races,
seasons 2018–2025, sorted strictly by the key.

------------------------------------------------------------------------

## 8. Development era

**DEVELOPMENT ERA = 2018–2024** (149 races, 162,728 states).

------------------------------------------------------------------------

## 9. Development folds

Expanding-window, race-chronological:

| Fold | TRAIN | VALIDATE |
|---|---|---|
| D1 | 2018–2021 | 2022 |
| D2 | 2018–2022 | 2023 |
| D3 | 2018–2023 | 2024 |

### Why the first validation season is 2022

2018–2021 is four full seasons of history, which supports three expanding
folds while retaining 2025 as the protected holdout. No fold is added
merely to increase fold count. Repository/data semantics give no evidence
for a materially better start.

------------------------------------------------------------------------

## 10. Protected final holdout

**PROTECTED FINAL HOLDOUT = 2025** (24 races, 26,692 states).

Its purpose is to answer: *after all development/model-selection decisions
are frozen, how does the selected system generalize to the next unseen
season?* 2025 must not be used for hyperparameter tuning, model-family
selection, feature-family selection, ablation decisions, calibration,
preprocessing fitting, threshold selection, early stopping, architecture
selection, or target-performance debugging.

## 11. Holdout access policy

- development runners exclude 2025 by construction;
- the holdout evaluator is a **separate** path requiring an explicit opt-in;
- every experiment record carries `holdout_accessed` / `holdout_purpose`;
- final evaluation occurs once, after model/config selection is frozen;
- no repeated 2025 tuning loop.

This is an engineering guardrail, not cryptographic secrecy. M0 does not
evaluate 2025 targets.

------------------------------------------------------------------------

## 12. Task eligibility

Eligibility is **only** the Phase-2 frozen task mask (`load_task`), never a
re-derived condition. Measured totals:

| Population | Count |
|---|---|
| binary masks (`winner`/`podium`/`points`) | 189,420 each |
| ordinal (`final_position`) | 178,963 |
| gain / loss / position_change | 189,126 |
| non-null `final_position` | 189,420 |

Non-null `final_position` ≠ ordinal eligibility: W/D back-rank source
orderings are excluded by `classified_flag`. Each fold reports races,
states, eligible rows, positives/negatives, and ordinal/regression
coverage — counts only, no metrics.

------------------------------------------------------------------------

## 13. Race-level weighting / aggregation

Two distinct questions, two distinct answers:

- **Training weighting:** every eligible driver-state is one training unit
  (`state_equal`). No synthetic resampling, no silent class balancing.
- **Evaluation aggregation:** the headline is **race-macro** (each race
  contributes equally, so one unusually long race cannot dominate);
  state-level metrics are reported as diagnostics.

Fold aggregation is a simple mean across folds with dispersion (range/σ).

A **within-season rolling-race** evaluation (train through race R, evaluate
race R+1) is explicitly classified as an optional **SECONDARY EVALUATION**
and is **not adopted** in M0: it must not replace the expanding-window
chronological folds used for model selection, and it may be added later
only with a documented justification. It is not run in M0.

------------------------------------------------------------------------

## 14. Stage-of-race evaluation

Frozen buckets reuse the Phase-2 progress thirds on `race_progress_frac`
(half-open `[lo, hi)`, final bucket inclusive):

| Stage | Range | States |
|---|---|---|
| EARLY | 0 ≤ p < 1/3 | 64,016 |
| MID | 1/3 ≤ p < 2/3 | 63,437 |
| LATE | 2/3 ≤ p ≤ 1 | 61,967 |

No stage feature is created; this is an evaluation partition only. F16
fixture "stage" tags are descriptive testing aids, not these buckets.

------------------------------------------------------------------------

## 15. Primary probabilistic metrics

For binary tasks, probability quality is primary (the platform consumes
probabilities):

- **primary:** log loss, Brier score;
- **secondary:** ROC-AUC, PR-AUC.

Accuracy is never the headline. Winner labels are rare at state level
(5.47%); imbalance is acknowledged, not hidden.

## 16. Race-level winner metrics

Row-level independent binary probabilities are **not** a coherent race
distribution and do not sum to 1. Race-level metrics are defined
separately:

- winner top-1 accuracy at synchronized race states;
- winner top-3 inclusion;
- race-level log loss **only** where a valid mutually-exclusive
  distribution exists.

Post-hoc normalization is forbidden unless explicitly justified and
evaluated. M0 distinguishes binary per-driver evaluation from race-level
multinomial evaluation and does not fake normalization.

## 17. Calibration metrics

Frozen before results: Brier score, reliability-curve data, and expected
calibration error (ECE) with **10 equal-width [0, 1] bins**. Bin policy is
frozen and may not be tuned after seeing models.

## 18. Calibration fitting policy

A calibrator (Platt/sigmoid, isotonic) may fit **only** on
development-training/calibration data. It must never fit on the validation
targets being reported or on 2025. Nested calibration inside a temporal
fold must use an inner train/calibration split. M0 implements no
calibrator.

## 19. Ordinal / final-position metrics

MAE (primary), RMSE (secondary), Spearman rank correlation, and per-race
rank quality. Final position is ordinal, not independent continuous data;
ordinary regression is not assumed correct. W/D back-rank numerics are
never eligible ordinal targets.

## 20. Position-change metrics

Regression: MAE (primary), RMSE (secondary). Gain/loss binary: log loss,
Brier, PR-AUC where informative. Position change is **not** an overtake
count.

------------------------------------------------------------------------

## 21. Baseline inventory (non-ML)

| Baseline | Rule |
|---|---|
| CURRENT_LEADER | predict the current race leader as winner |
| CURRENT_ORDER | current running order is the final order |
| GRID_POLE | pre-race: pole/grid leader wins, order by grid |
| RECENT_PACE | rank by a frozen factual recent-pace column at state time |
| CLASS_PRIOR | constant training-prevalence probability (fold-train only) |

F16's `CURRENT_ORDER_ONLY` / `MINIMAL_RACE_STATE` / `ALL_84` are **feature
sets**, not prediction baselines.

## 22. Legacy model baseline

The frozen university-era models are included only as **LEGACY REFERENCE**,
not as a fair direct benchmark. Old GroupKFold metrics are never mixed with
Phase-3 temporal metrics, and no regression/improvement claim is made until
evaluated under a comparable protocol.

------------------------------------------------------------------------

## 23. Preprocessing boundary

All learned preprocessing fits **TRAIN ONLY**: imputers, scalers, encoders,
feature selectors, dimensionality reduction, learned transforms. Validation
and holdout receive transform-only behaviour. No global pre-split fit.

## 24. Missingness policy

Phase-2 structural missingness is preserved. M0 does not fill values
globally. Native-missing models may consume supported nulls; models needing
complete inputs receive train-fitted imputation inside a leakage-safe
pipeline. Missingness indicators only as an explicit, justified pipeline
component. No target-aware imputation; no global statistics; the canonical
matrix is never mutated.

## 25. Categorical policy

The three string categoricals in the 84-feature surface are `compound`,
`stint_compound`, `track_state`. Default treatment is one-hot or native
categorical support fitted on train only; unknown-category behaviour is
frozen per pipeline; target encoding is forbidden unless train-only and
evaluated as an explicit experiment dimension.

## 26. Model-specific pipelines

Each model family gets an appropriate leakage-safe pipeline (tree models
vs linear models vs CatBoost native categoricals). Comparison nonetheless
uses the **same folds, task eligibility, feature-set contract and metric
definitions**.

## 27. Class-imbalance policy

No synthetic resampling initially. Class/sample weighting is allowed only
as an explicit experiment dimension, never silent. Weighting that changes
effective training prevalence must be followed by calibration evaluation.

## 28. Hyperparameter-tuning policy

Start from sensible defaults, then small documented search spaces inside
development-training folds. No 2025 tuning. Budget is recorded. No AutoML
by default; Optuna/random search only if justified and budgeted. M0 adds
none.

## 29. Seed policy

`PROJECT_SEED = 42` (`SEED_SET = (42,)`). Every stochastic model/tuning run
records its seed. Seeds are not averaged by default; one lucky seed must
not determine the production model. Monte Carlo seeds are a separate later
subsystem.

------------------------------------------------------------------------

## 30. Candidate model tiers

**Production candidate:** Logistic Regression, HistGradientBoosting,
XGBoost, LightGBM, CatBoost, ExtraTrees, RandomForest.
**Experimental:** learning-to-rank, ordinal model, MLP.
**Deferred:** GRU/LSTM, temporal transformer, TabPFN, DNF survival
(no frozen DNF target).

Serious tabular candidates run first; deep models are not promoted for
novelty. Tier/eligibility metadata (supported tasks, preprocessing,
missing/categorical handling, probability output, calibration implications,
compute class, dependency) is frozen in `CANDIDATES`.

### Dependency availability (measured, no install)

| Dependency | Available |
|---|---|
| `sklearn` | yes |
| `xgboost` | yes |
| `scipy` | yes |
| `lightgbm` | no |
| `catboost` | no |
| `statsmodels` | no |
| `torch` | no |
| `optuna` | no |
| `mlflow` | no |
| `tabpfn` | no |

M0 installs nothing. LightGBM/CatBoost availability is an M5 dependency
decision.

## 31. Candidate eligibility

Each candidate records supported task types, preprocessing requirements,
missing-value handling, categorical handling, probability-output support,
calibration implications, expected compute class and dependency
availability (§30). A missing package is recorded, not installed.

------------------------------------------------------------------------

## 32. Model-selection rule

For the primary winner task, evidence is weighed in this order:

1. probabilistic quality (log loss, Brier);
2. calibration;
3. temporal consistency across folds;
4. stage-of-race behaviour;
5. inference latency;
6. complexity / operational cost.

No arbitrary weighted "model score"; a documented decision table is
required, and one model need not win every task.

## 33. Fold aggregation

Report every fold separately **and** an aggregate. Do not hide a weak
season behind one pooled number. Aggregate = simple mean across folds
(aligned with the race-level product objective) with dispersion
(σ/range) reported.

## 34. Uncertainty

Later evaluation may report race-level bootstrap confidence intervals and
fold dispersion. Bootstrap resamples **races**, never individual state
rows. M0 computes none.

------------------------------------------------------------------------

## 35. F16 feature-set experiment contract

Phase 3 consumes F16 via `resolve_feature_set(name, manifest)`. Vocabulary:
`ALL_84`, cumulative sets (`CUMULATIVE_00…` …), LOGO sets
(`ALL_MINUS_<GROUP>`), `CURRENT_ORDER_ONLY`, `MINIMAL_RACE_STATE`. No
experiment may infer features by dropping dataframe columns.

## 36. Ablation policy

Ablations run only after baseline model infrastructure is stable, with the
same folds, metrics, preprocessing family and tuning budget. Cumulative and
LOGO experiments use dependency-aware interaction removal. No ablation and
no intuition-based feature removal in M0.

------------------------------------------------------------------------

## 37. Experiment identity

`experiment_id` is a deterministic hash over:
protocol version, Phase-2 freeze commit, feature/label/matrix/ablation
versions, matrix content hash, feature set, task, fold, model family,
model parameters, preprocessing config, calibration config and seed.
Timestamps are recorded outside the semantic identity. Giant feature
matrices are never stored per experiment.

## 38. Result schema

Configuration and results are separated. Config requires: `experiment_id`,
versions/hashes, feature set, task, fold, model family/parameters,
preprocessing/calibration config, seed, train/validation rows and races,
split policy, `holdout_accessed`. Results require: status, fit duration,
inference latency, metrics, calibration metrics, stage metrics, artifact
references and warnings. M0 populates **no** results.

## 39. Experiment storage

Tracked configuration/code/protocol/summary reports + gitignored JSON and
Parquet result artifacts. MLflow is **not** introduced merely because this
is "MLOps"; it is reconsidered only if measured experiment-management pain
justifies it.

## 40. Artifact naming

Structured IDs: `mlab-{task}-{model_family}-{feature_set}-{fold}-{seed}` and
run dirs `experiments/{protocol_version}/{experiment_id}`. No
`best_model_final_v2_REAL.pkl`.

## 41. Model artifact contract

Every future fitted model carries: model family, task, feature set, exact
ordered feature names, training chronology, preprocessing, calibration,
seed, dependency versions, matrix version/content hash, protocol version,
git commit, creation command and metrics reference. M0 fits no artifact.

## 42. Latency / training benchmark contract

Latency: warm-up, repeated timed calls, batch sizes (single state, full
field, batch historical), p50/p95 (p99 where supported), hardware metadata.
Training cost: fit wall time, peak memory where practical, artifact size,
hardware. No fabricated numbers; no benchmark in M0.

## 43. Probability semantics

Two distinct objects:

- **independent binary per-driver probability** — does not sum to 1 across
  a race;
- **mutually exclusive race winner distribution** — sums to 1, requires a
  model/probability contract.

Each future model/task experiment must state which it outputs. Post-hoc
normalization is forbidden unless explicitly justified and evaluated.
Arbitrary scores are never labeled "win probability".

## 44. Multi-driver race structure

Whether winner modeling ultimately needs a race-aware model or
normalization layer remains an M10 research question. Candidate directions:
independent binary classification, grouped ranking, softmax/multinomial
race-state formulation, learning-to-rank. M0 implements none.

## 45. Partial-race policy

Belgium 2021 (`2021-r12-R`) and Japan 2022 (`2022-r18-R`) are retained with
valid observed states and official outcomes, with an explicit race-level
PARTIAL grouping flag. They are not casually dropped. Exclusion happens
only if a task is semantically invalid for the race, justified at
task/protocol level. Phase-2 data is not changed.

## 46. Reproducibility

Given the same matrix, feature set, config, seed and git commit, an
experiment must reproduce the same (or tolerance-bounded) result. Every run
records versions, hashes, seed and dependency versions. Unavoidable
nondeterminism is documented.

------------------------------------------------------------------------

## 47. Protocol validation / drift / tests

`validate_protocol()` (pure) and `verify_phase2_artifacts()` (read-only)
fail loudly on: Phase-2 version drift; matrix/manifest/ablation hash drift;
protected holdout in development training or validation; train season ≥
validation season; non-nested/duplicate folds; unknown task; missing task
mask; unknown metric; unknown feature set; forbidden random split policy;
protocol-document hash drift.

Focused tests: `tests/test_v2_model_lab_m0.py` (29 tests, ~1 s) covering
frozen versions/hashes, chronology, folds, holdout exclusion, final-fit
boundaries, mask-based eligibility, ordinal safety, metric/baseline/
preprocessing/calibration registries, seed and experiment identity,
holdout-access metadata, deterministic export, drift rejection, feature-set
resolution and a static non-modeling source scan.

## 48. Split / task count audit

Generated from the frozen matrix by `python -m v2.model_lab.audit` (counts
only). Stored at `docs/generated/model_lab_split_audit_v1.json`.

### Per-fold counts

| Fold | Train | Val | Train races | Val races | Train states | Val states |
|---|---|---|---|---:|---:|---:|---:|
| D1 | 2018–2021 | 2022 | 81 | 22 | 88,123 | 23,577 |
| D2 | 2018–2022 | 2023 | 103 | 22 | 111,700 | 24,422 |
| D3 | 2018–2023 | 2024 | 125 | 24 | 136,122 | 26,606 |
| FINAL FIT | 2018–2024 | — | 149 | — | 162,728 | — |
| HOLDOUT | — | 2025 | — | 24 | — | 26,692 |

### Validation-fold task eligibility (counts, no metrics)

| Fold | winner (pos) | podium (pos) | points (pos) | ordinal | gain (pos) | loss (pos) |
|---|---|---|---|---|---|---|
| D1 (2022) | 23,577 (1,295) | 23,577 (3,883) | 23,577 (12,926) | 22,087 | 23,536 (9,752) | 23,536 (6,490) |
| D2 (2023) | 24,422 (1,325) | 24,422 (3,975) | 24,422 (13,246) | 23,361 | 24,382 (9,567) | 24,382 (7,321) |
| D3 (2024) | 26,606 (1,444) | 26,606 (4,332) | 26,606 (14,427) | 25,766 | 26,578 (10,129) | 26,578 (7,406) |

Whole-matrix: binary 189,420 each (winner 10,370 pos / 5.47%), ordinal
178,963, gain/loss/position_change 189,126.

These are dataset/protocol counts, **not** model results.

------------------------------------------------------------------------

## 49. Phase-2 immutability

Entry and exit fingerprints agree:

```
sha256(model_matrix.parquet) = b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3
sha256(manifest.json)        = b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62
sha256(ablation_config.json) = bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7
content_hash (recomputed)    = d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db
```

M0 added only new files under `v2/model_lab/`, `tests/` and `docs/`; no
Phase-2 artifact or semantic version changed.

## 50. Known limitations

- Rich-data era is 2018–2025; folds are few (three development folds), so
  fold dispersion is a coarse robustness signal.
- Row dependence means state-level metrics can look artificially precise;
  headline uses race-macro.
- `position_change`/gain/loss are not overtakes; DNF has no frozen target.
- Structural missingness is preserved, so native-missing models have an
  advantage on nullable columns.
- Random-split prohibition is enforced by contract/test, not by a runtime
  sandbox.
- LightGBM/CatBoost are unavailable until an approved M5 dependency
  decision.

## 51. M1 handoff

M1 (Experiment Framework) should build the config-driven runner, shared
temporal splitting, shared metric implementation, artifact metadata and
registry **against this frozen protocol**, without retuning any Phase-2
semantic. No candidate is trained until M1 infrastructure exists.

## 52. M0 definition of done

Every M0 checklist item passes (see the M0 Final Report). No BLOCKER or
MAJOR remains; no model was trained; no candidate prediction was produced;
no 2025 target performance was inspected; regression is green.

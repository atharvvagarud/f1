# PHASE 8 E3 — GLOBAL MODEL EXPLAINABILITY REPORT

Status: **E3 COMPLETE — READY FOR E4**

Phase 8 progress: E0 (explainability/cache contract audit) complete,
E1 (reference cache path) complete, E1.5 (frozen matrix reuse) approved,
E1.6 (accelerated cache builder) complete, E2 (production replay cache)
complete, **E3 (global explainability only) complete**.

E3 explains the frozen winner `LogisticRegression` **as frozen**. It does
not produce local/driver explanations (E4) and does not touch the replay
cache, serving modules, preprocessing, coefficients or 2025.

## 1. Frozen model identity

| Field | Value |
|---|---|
| Task / target / mask | `winner` / `is_winner` / `eligible_is_winner` |
| Estimator | `LogisticRegression` |
| Params | `C=0.01`, `penalty=l2`, `solver=lbfgs`, `max_iter=1000`, `class_weight=None`, `random_state=42` |
| Feature set | `ALL_84` / `v8` |
| Calibration / semantics | `RAW` / `BINARY_PROBABILITY` / `INDEPENDENT_BINARY` |
| Canonical features | 84 |
| Transformed dimensions | 106 = 70 numeric + 11 boolean + 25 one-hot |
| Intercept | `-5.574170885990861` |
| Coefficient shape | `(1, 106)` |
| Serving artifact SHA-256 | `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4` |
| Specification fingerprint | `3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d` |
| Phase-2 matrix content hash | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| Training seasons | 2018–2024 (149 races, 162,728 eligible states, 8,926 positives) |

All anchors were re-verified by importing the validated serving loader
(`v2.model_lab.serving.load_frozen_winner_model`); a mismatch raises before
any explanation is built.

## 2. Explainability mathematics

For the fitted linear model, in the transformed input space `x'`:

```
z = intercept + sum_j beta_j * x'_j          (model log-odds)
p = 1 / (1 + exp(-z))                         (independent binary logit)
```

E3 reports the additive decomposition in **model log-odds**, never in
win-probability increments. The 70 numeric inputs are standardized with
train-fitted statistics, so each numeric `beta_j` is the change in model
log-odds per one training standard deviation, conditional on the other
model inputs. The 11 boolean inputs are unscaled. Categorical inputs enter
through a fitted one-hot block.

`explanation_space = "LOG_ODDS"`, `probability_semantics =
"INDEPENDENT_BINARY"`.

## 3. 106 -> 84 feature mapping

`ColumnTransformer.get_feature_names_out()` is the ordering authority;
transformed order is never guessed. Every transformed dimension maps to
exactly one canonical feature:

- `num__<feature>` -> the 70 numeric canonical features (1:1);
- `bool__<feature>` -> the 11 boolean canonical features (1:1);
- `cat__<feature>_<category>` -> the 3 categorical canonical features
  (`compound`, `stint_compound`, `track_state`; 9 + 9 + 7 = 25 one-hot
  dimensions).

Assertions enforced by code and tests: 106 mapped, 0 unmapped, 0 duplicate
transformed indices, 0 duplicate names, every canonical feature covered,
and the transformed names exactly equal the fitted transformer's authority.

## 4. Feature-family mapping

Families come from the frozen F16/registry authority
(`v2.experiments.feature_sets.primary_group_name`), not from invented
ML-marketing buckets. All 84 canonical features resolve into:

| Family | Canonical features |
|---|---|
| `STATE` | 23 |
| `PRE_RACE_PRIORS` | 13 |
| `FIELD_CONTEXT` | 12 |
| `PACE` | 12 |
| `ENVIRONMENT_HISTORY` | 9 |
| `GAPS` | 8 |
| `RATES_MOMENTUM` | 4 |
| `INTERACTIONS` | 3 |

(The task sketch named `ENV_HISTORY`; the frozen registry's literal group
name is `ENVIRONMENT_HISTORY` and that authoritative name is used.)

## 5. Coefficient evidence

### 5.1 Numeric (70)

Per feature: canonical name, family, transformed index/name, coefficient,
direction, and the **fitted** training median (imputer statistic), mean and
scale (`StandardScaler`). Statistics are read from the fitted preprocessor
and are never recomputed from current data.

### 5.2 Boolean (11)

Per feature: coefficient, direction, and the fitted training imputation
mode (0/1). A 0 -> 1 input change corresponds to the coefficient in model
log-odds, conditional on other inputs. Boolean magnitudes are explicitly
flagged as not comparable with standardized numeric magnitudes.

### 5.3 Categorical (3)

Per feature: fitted vocabulary, per-category coefficients (transformed
index, value, direction, MISSING-sentinel flag), coefficient range,
`missing_category_present`, and `reference_category=None`. The
`OneHotEncoder` is fitted with `handle_unknown="ignore"` and **no dropped
category**, so all fitted categories are encoded and there is no
traditional reference category. An unseen category fires the all-zero
block.

### 5.4 Grouped view and no fake universal ranking

`canonical_groups` exposes the family partition with each categorical
group's individual category coefficients. Raw coefficient magnitude is not
treated as comparable across feature types/scales. E3 does **not** invent
`sum(abs(category coefficients))` or `sum(category coefficients)` as a
global ranking; empirical importance is kept to the permutation analysis.

## 6. Coefficient interpretation limitations

- Coefficients describe the fitted model's log-odds structure, not causal
  effects; they do not establish why a driver won.
- Numeric coefficients are per one training standard deviation,
  conditional on the other model inputs.
- Unscaled boolean coefficients are not magnitude-comparable with
  standardized numeric coefficients without qualification.
- Categorical coefficients are one-hot increments under a no-drop encoding;
  they are reported per category rather than summed.
- Coefficients must never be converted into win-probability increments.

## 7. Existing Model Lab evidence audit

Inventory of frozen M2–M8 / M9 material:

- 49 development-fold experiment records under
  `data/v2/model_lab/experiments/protocol=v1/*/result.json`, each storing
  aggregate + per-race metrics (no per-state predictions).
- M7 `logreg_boundary_resolution_v1.json`, M8
  `calibration_selection_v1.json`, and the other suite reports store
  fold-level aggregate metrics.
- M9 `data/v2/model_lab/final/winner_logreg_raw_v1/metadata.json` is
  metadata-only: the Model Lab intentionally does **not** serialize fitted
  fold estimators.
- `final_holdout_2025_v1.json` is the consumed 2025 holdout (firewalled).

Conclusion: no frozen per-state out-of-sample predictions exist, so a
temporally out-of-sample permutation analysis would require retraining fold
models, which the E3 contract forbids. E3 therefore uses the explicitly
permitted fallback (pre-2025 frozen matrix rows with the frozen serving
artifact) and labels the evidence class precisely.

## 8. Permutation population

- Seasons 2018–2024 only (2025 rejected before any prediction).
- Frozen `eligible_is_winner` mask and frozen ordered ALL_84 columns.
- 162,728 rows, 149 races, 8,926 positives.
- **Evidence class: `PRE_2025_FINAL_FIT_IN_SAMPLE`** — these are the rows
  the production artifact was final-fit on. This is **not** unbiased
  generalization evidence, and the artifact and report say so explicitly.

## 9. Permutation unit

Chosen unit: **state within race, race identity preserved**. For each
canonical feature independently, values are permuted among the states of
the same race. This:

- never moves a value across a race boundary (no cross-race/cross-era
  temporal mixture; race identity is preserved exactly);
- preserves the exact per-race multiset of the feature;
- permutes the **raw canonical input** and re-runs the fitted
  preprocessor, so one-hot columns are never independently permuted into
  impossible combinations.

Rejected alternatives: global row-wise shuffle (unrealistic mixtures,
red-team check `row-wise temporal shuffle`), and cross-race/race-block
permutation (breaks race identity and mixes eras). Driver-trajectory
permutation preserves race identity but cannot test inputs that are
constant within a race and is ill-defined with unequal trajectory lengths;
the chosen within-race state unit can test race-constant-per-lap inputs by
moving them across laps of the same race.

## 10. Permutation metric

Primary (frozen headline): **race-macro log loss**, using the frozen
`v2.model_lab.aggregation.race_macro` implementation (equal weight per
race, row metric = `log_loss`). Importance is
`permuted_metric - baseline_metric`; positive means the disruption made
performance worse. No accuracy substitution.

Baseline (frozen serving model on the in-sample population):
**0.072498**.

## 11. Permutation protocol

| Field | Value |
|---|---|
| Metric | `race_macro_log_loss` |
| Row metric | `log_loss` |
| Aggregation | equal weight per race, then row metric |
| Unit | `state_within_race (race identity preserved)` |
| Repeats | 5 |
| Base seed | 42 |
| Seed scheme | `numpy.default_rng([base_seed, feature_index, repeat])` |
| Target | `is_winner` (never permuted; never in the feature frame) |
| Holdout 2025 | excluded |

Variability across repeats is reported per feature (`std_delta`,
`per_repeat_delta`). Maximum observed `std_delta` = `0.000463`.

## 12. Permutation results (top / bottom; mean delta over 5 repeats)

| mean delta | std | family | feature |
|---|---|---|---|
| 0.027004 | 0.000463 | GAPS | `gap_to_leader_seconds` |
| 0.023535 | 0.000364 | GAPS | `gap_to_ahead_seconds_valid` |
| 0.013136 | 0.000371 | STATE | `position` |
| 0.012048 | 0.000241 | FIELD_CONTEXT | `cars_ahead_observable` |
| 0.009502 | 0.000122 | PRE_RACE_PRIORS | `prior_driver_mean_finish` |
| 0.007002 | 0.000230 | PRE_RACE_PRIORS | `grid_position` |
| 0.006817 | 0.000151 | PRE_RACE_PRIORS | `recent_constructor_points_per_entry_5` |
| 0.006228 | 0.000057 | PRE_RACE_PRIORS | `prior_driver_points_per_start` |

Family mean deltas: GAPS 0.006780, PRE_RACE_PRIORS 0.002982,
FIELD_CONTEXT 0.001377, STATE 0.000628, RATES_MOMENTUM 0.000410,
INTERACTIONS 0.000222, PACE 0.000148, ENVIRONMENT_HISTORY 0.000026.
35 of 84 features exceed `1e-4`.

These are **permutation importances under the specified evaluation
protocol**, not causal or definitive importance.

## 13. Permutation limitations

- In-sample with respect to the production artifact (documented above).
- Correlated engineered features can make a redundant input look
  unimportant; a low value does not establish an input is useless.
- An input constant within every race offers no within-race variation.
- Within-race permutation allows bounded within-race temporal mixtures.
- The result is conditional on one frozen protocol (unit, metric, repeats,
  seed), not a universal ranking.

## 14. 2025 firewall

- Population construction slices `season <= 2024` before any prediction.
- `assert_pre_2025_seasons` fails closed on 2025/out-of-range seasons and
  is exercised by tests, including an injected-2025 red-team test.
- The consumed 2025 holdout and `final_holdout_2025_v1.json` are never
  read. No 2025 target, row, metric, seed or selection entered E3.

## 15. Label firewall

- Predictive columns are disjoint from label / companion / task-mask
  columns (asserted from the frozen manifest).
- The permutation feature frame carries exactly the 84 ordered ALL_84
  columns; `is_winner` is never a feature and is never permuted.

## 16. Global explanation artifact

Generated (gitignored) at:

```
results/v2_explainability/global_winner_logreg_v1.json
results/v2_explainability/global_winner_logreg_v1.sha256
```

Schema (top level): `format`, `model_identity`, `feature_identity`,
`probability_semantics`, `explanation_space`, `intercept`,
`transformed_feature_count`, `canonical_feature_count`, `mathematics`,
`transformed_features`, `numeric_coefficients`, `boolean_coefficients`,
`categorical_coefficients`, `canonical_groups`, `permutation_importance`,
`language_contract`, `limitations`.

## 17. Artifact identity / SHA

| Field | Value |
|---|---|
| Artifact SHA-256 | `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f` |
| Size | 147,114 bytes |
| Tied to | serving SHA, spec fingerprint, `ALL_84`/`v8`, Phase-2 content hash, preprocessor fingerprint |

If any tied identity changes, `is_artifact_stale` reports the artifact
stale (tested).

## 18. Determinism

- The artifact is serialized with sorted keys and canonical separators.
- Two independent full builds (separate processes) produced byte-identical
  scientific blocks (`transformed_features`, coefficient blocks,
  `canonical_groups`, `permutation_importance`, `intercept`,
  `limitations`, `mathematics`); only the newly added Phase-2 identity
  field differed between the two builds, as expected.
- Repeated builds on a bounded population are byte-identical (tested).
- The permutation RNG is a pure function of
  `[base_seed, feature_index, repeat]`; no wall-clock or hash-order
  randomness participates.

## 19. Language contract

Allowed: "model coefficient", "model log-odds", "positive/negative
association in the fitted model", "permutation increased race-macro log
loss by ...", "under this evaluation protocol ...", "model input".

Forbidden (guarded in generated copy and tested): "caused", "proved",
"driver won because", "added X probability points", "probability points",
"most important factor in reality", "the model knows", "the model thinks".

Probability semantics remain `INDEPENDENT_BINARY`; no explanation
normalizes across a race.

## 20. SHAP decision

SHAP remains **deferred/dropped for v1** (E0). It is not installed or
imported; tests assert `shap` is absent from the module and the process.

## 21. Performance (offline, bounded)

| Measure | Value |
|---|---|
| Coefficient extraction | 0.0046 s |
| Full artifact generation | 135.5–139.8 s |
| Permutation share | ~135 s (84 features x 5 repeats x full-population prediction) |
| Artifact size | 147,114 bytes |
| Peak RSS | ~1.80 GB |

No premature optimization was applied; the run is a small multiple of the
baseline full-population prediction time.

## 22. Tests

`tests/test_v2_phase8_e3.py` — **35 passed**. Coverage: frozen model
identity; frozen serving SHA; fitted preprocessor; 106 dimensions / 84
canonical / 0 unmapped / 0 duplicate; `get_feature_names_out` authority;
family mapping; numeric scaler statistics from the fitted artifact;
boolean imputer statistics; categorical vocabulary; unknown-category
semantics; canonical/categorical grouping; no fake universal coefficient
ranking; pre-2025 population; 2025 firewall fail-closed; injected-2025
row excluded; label firewall; target never permuted; race-identity
preservation; not a global row shuffle; permutation determinism; seed
effectiveness; unit + metric declaration; race-macro metric correctness;
one-hot integrity; artifact deterministic ordering; identity/staleness;
byte-stable render; language-contract guard; stored-artifact shape and
language; stored-artifact hash; SHAP absent; no sklearn permutation
dependency; artifact hash determinism.

## 23. Permutation red team

| Attack | Outcome |
|---|---|
| 2025 rows injected | excluded by `season <= 2024` slice; `assert_pre_2025_seasons` fails closed (tested) |
| Label column included | predictive/label/mask disjointness asserted; target absent from feature frame |
| One-hot columns independently permuted | impossible: raw canonical input is permuted then re-transformed by the fitted preprocessor; OHE block stays a valid one-hot/all-zero (tested) |
| Row-wise temporal shuffle selected | rejected: unit is within-race, per-race multiset preserved (tested) |
| Race identity lost | rejected: values never cross race boundaries (tested) |
| Target shuffled with feature | target array untouched by permutation (tested) |
| Random seed omitted | seed is an explicit protocol field; default is a constant; seed effectiveness tested |
| Metric aggregation changed from race-macro | protocol pins `race_macro_log_loss`; correctness checked against a manual race-macro computation |
| Final-fit training performance mislabeled as OOS | evidence class is `PRE_2025_FINAL_FIT_IN_SAMPLE` and states "NOT temporally out-of-sample" |

## 24. Repository safety

No `git reset/restore/checkout/clean/stash`, no `git add`, no commit, no
tag. Only the E3 module, E3 tests, this report and the gitignored
generated artifact were created. Unrelated working-tree changes were left
untouched.

## 25. E4 entry gate

- [x] frozen model identity verified
- [x] 106 transformed dims mapped
- [x] 84 canonical features mapped
- [x] feature families mapped
- [x] numeric coefficient interpretation correct
- [x] boolean interpretation correct
- [x] categorical semantics correct
- [x] no fake universal coefficient ranking
- [x] permutation protocol frozen
- [x] permutation uses defensible pre-2025 evidence (in-sample limitation explicitly documented; OOS blocked by frozen-artifact inventory)
- [x] race-macro metric correct
- [x] deterministic permutation seeds
- [x] 2025 firewall green
- [x] label firewall green
- [x] global artifact deterministic
- [x] global artifact tied to model identity
- [x] language contract frozen
- [x] SHAP remains deferred
- [x] relevant regressions green (P3.1 / M1 metrics-aggregation / F11 registry / F16 ablation)

Final verdict: **E3 COMPLETE — READY FOR E4**.

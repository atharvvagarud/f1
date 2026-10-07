# V3.3A MODEL LANDSCAPE + EXPERIMENT CONTRACT

## Final verdict

V3.3A COMPLETE — EXPERIMENT CONTRACT FROZEN — READY FOR V3.3B.
Contract-only stage: no models trained, no 2025 touched, no runtime changed.

## Frozen parent

Tag `v3.2-monte-carlo-2` == commit `197979d40af0c9dbf90667781d9c83e41613b047`.
V3.2 immutable; nothing in V3.3A modifies simulation, status, API, or frontend.

## Existing Model Lab capability

REUSE_AS_IS: data loader (`data.CanonicalMatrix` + F15 manifest), task
resolver (`tasks.resolve_task`), fold/holdout resolvers (`splits.get_split`
+ `ProtectedHoldoutError`), dataset materialization (`splits.materialize`,
mask-first, M0 count audits), prediction alignment (`predictions.align` +
`PredictionResult`), probability metrics (`metrics`: logloss/Brier/ROC/PR),
race-macro + state-pooled aggregation (`aggregation`), stage aggregation
(`stage_scoped_metrics`), calibration/ECE (`calibration`,
`calibration_selection`), winner top-k (`winner.synchronized_winner_top_k`),
prediction serialization (`to_frame`/`from_frame` + parquet convention),
temporal leakage checks (`validate_split`, firewall asserts), nested tuning
(`tuning` + `inner_splits`), final-fit + serving (`final_fit`,
`FrozenWinnerPredictor`).
MINOR_EXTENSION_NEEDED: dynamics-join materialization (generalize
`materialize_v3` from `v3_dynamics_experiment.py` to the 110-col arm);
HGB/XGB 110-col configs in the tuning suites.
NOT_NEEDED_FOR_V3_3: feature selection/ablation reruns (V3.1 settled that).
BLOCKER: none.

## Accepted V3.1 baseline

V3.1B: task `winner` (binary per-driver `is_winner`, `INDEPENDENT_BINARY`
RAW, never normalized); arms ALL_84 (84) vs ALL_84 + 26 CORE dynamics
(110); LogisticRegression C=0.01, l2, lbfgs, max_iter=1000,
random_state=42; TRAIN-only median/mode + StandardScaler + one-hot
(preprocessing frozen; transformed dims 106/132). Folds D1 2018–2021/2022,
D2 2018–2022/2023, D3 2018–2023/2024; FINAL_FIT 2018–2024 (162,728
eligible, 149 races, 8,926 positives); 2025 holdout 26,692 rows / 24 races.
Holdout: A 0.0680353741 → B 0.0634166678, Δ −0.004619, CI
[−0.007148, −0.002158], 19/24 races, 4/4 temporal. Artifact
`data/v3/v3_1d/final_model_arm_b.joblib` (SHA
`9a1aac51…8960`, present locally, git-ignored); reproducible by load OR
frozen-spec rerun (proven 0.0 diff). Verdict KEEP.

## Task contract

Unchanged: binary per-driver winner prediction at state T,
P(is_winner | causal state at T), `INDEPENDENT_BINARY`. No field softmax;
listwise/ranking models are a deferred separate family (no naive metric
comparison without a calibration bridge).

## Feature arms

Primary: ALL_84 + accepted V3.1 Race Dynamics (110, contract order).
Diagnostic control: ALL_84 (84). No new feature engineering; no
model-specific feature sets except mathematically required preprocessing
inside pipelines.

## Candidate landscape

1. Logistic Regression (control; V3.1B is a member; RAW ECE ~0.01; ~1s
   fits; linear ceiling).
2. HistGradientBoosting (native sklearn; M4 raw LL weak 0.139 mean —
   calibration path required; native NaN support; ~3s fits).
3. Extra Trees (M5 ET ≥ RF on LL; M6 tuned lineage leaf 3/10; strongest
   diversity hypothesis; ~7–14s fits; probability quality scrutinized).
4. XGBoost 3.2.0 (already a dependency; M4 raw 0.109 mean, materially
   better than HGB; regularized-boosting hypothesis; ~2s fits).
5–8. Evaluated and excluded: LightGBM/CatBoost (new deps, redundant
   boosting), Random Forest (redundant with ET), neural nets (no
   scientific question; cost unjustified), calibrated-linear-as-family
   (a method, not a family — covered by calibration policy),
   ranking/listwise (contract-incompatible; deferred).

## Dependency audit

sklearn 1.8.0 + xgboost 3.2.0 already in `requirements.txt` and the venv.
No lightgbm/catboost/optuna/shap anywhere. NOTHING installed in A; no new
dependency admitted. V3.3B may add one only if A had admitted it — it did not.

## Recommended candidate set

Four families incl. baseline: logistic_regression, hist_gradient_boosting,
extra_trees, xgboost. One linear control, one native boosting, one
randomized-bagging, one regularized boosting with distinct M4 loss
behavior. No benchmark results invented; M4/M5/M6 development evidence
only, all on the 84-col surface — the 110-col comparison is V3.3B/C work.

## Temporal folds

D1/D2/D3 expanding windows (counts: 88,123/23,577; 111,700/24,422;
136,122/26,606 eligible; M0-audited); inner folds D1-I1 … D3-I3 frozen
(M6); FINAL_FIT 2018–2024. Resolvers in `splits.py`; 2025 unreachable
without explicit opt-in.

## 2025 firewall

Sealed during A–D: no training/tuning/selection/calibration/elimination/
feature decisions on 2025, not even exploratory candidate metrics.
Enforced by `ProtectedHoldoutError` + development-only resolvers +
harness asserts + output season scans.

## Primary metric

Race-macro winner log loss (`aggregation.race_macro`), equal-per-race
mean, lower is better. Race is the statistical unit.

## Secondary metrics

Brier, ROC AUC, PR AUC, ECE, top-1, top-3; state-pooled + EARLY/MID/LATE
diagnostic. Never select on ROC AUC/accuracy alone.

## Calibration policy

RAW primary. Sigmoid/isotonic allowed only if fitted inside outer-train
history (never outer-validation, never 2025) and beating RAW on mean
inner LL beyond 1e-4 without worsening Brier. No rescue-calibration
(M-calibration precedent: RAW won).

## Preprocessing policy

Frozen pipeline (median/mode, StandardScaler numerics, unscaled boolean
mode, MISSING one-hot, TRAIN-only). Family adjustments inside pipelines
only. No validation/holdout fitting.

## Hyperparameter policy

Small preregistered grids, ≤12 configs/family, mean-inner-LL objective,
1e-6 tie tolerance with simpler-wins tie-breaks, one config per outer
fold, seeds {42}. No unrestricted search.

## Compute budget

189,420-state matrix; reference fits 1–14s/fold; ≤100 fits/family,
≤1h/family, ≤2h total on the M4 Air 16GB (CPU, n_jobs≤4). No cloud.

## Statistical comparison

Per-race Δ LL vs V3.1B; paired race bootstrap (seed 42, B=2000, 95% CI);
report mean/CI/improved/worsened/ties. States never bootstrap units.

## Temporal consistency

Fold-wise deltas reported; CONSISTENT_IMPROVEMENT / MIXED /
CONSISTENT_REGRESSION. No every-fold veto; instability is evidence.

## Practical significance

No post-hoc thresholds. Judge effect size + CI + consistency +
calibration + stage behavior + complexity + diversity value.

## Diversity / complementarity

Aligned OOF predictions → correlation (prediction/residual/per-race
delta), top-1 and high-confidence disagreement, per-race/stage
attribution, spread differences. Input to V3.4. No ensembling in V3.3.

## OOF prediction contract

state_id-keyed frames: season/race/checkpoint/driver/target/baseline +
candidate probabilities/fold/stage; `INDEPENDENT_BINARY` binaries, never
normalized; parquet under ignored `data/v3/v3_3*/`.

## Candidate dispositions

KEEP_PRIMARY_CANDIDATE / KEEP_DIVERSITY_CANDIDATE / HOLD_FOR_CALIBRATION /
REJECT_NO_IMPROVEMENT / REJECT_TEMPORAL_INSTABILITY /
REJECT_PROBABILITY_QUALITY / REJECT_COMPLEXITY_WITHOUT_VALUE /
REJECT_CONTRACT_INCOMPATIBLE.

## Advancement policy

≤3 non-baseline finalists + frozen V3.1B, on pre-2025 evidence only.

## Final holdout policy

Defined now, NOT executed: finalists train through 2024 per frozen
final-fit policy, evaluate once on 2025, same race-macro metric + paired
comparison. After reveal: no retune, no feature/calibration/config changes.

## Artifact contract

Family, implementation/version, task, feature contract/hash, seasons,
folds, hyperparameters, preprocessing, calibration, seed, code version,
dataset identity, SHA256. No trained candidate artifacts in A.

## Reproducibility

random_state 42, n_jobs≤4 recorded, stable canonical ordering, versions
captured; cross-platform binary caveat documented.

## Explainability compatibility

LogReg native coefficients; HGB/ET importance adapters cheap; XGB
gain/cover (SHAP optional, not a dependency). Cost recorded, never a
rejection reason alone. `raceintel/explainability/` exists.

## Serving compatibility

Research-first, no promotion. joblib via `FrozenWinnerPredictor` pattern;
tree ensembles heavier than LogReg; footprint unchanged (sklearn+xgboost).

## Known limitations

Single 24-race holdout; thin/medium-bin descriptives; boosting raw-LL
history; listwise deferred.

## V3.3B recommendation

Build the screening harness on this frozen contract: 110-col
dynamics-join materialization, 4 admitted families, preregistered small
grids, inner-fold selection, OOF capture; no 2025 contact.
Contract hash `d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7`.

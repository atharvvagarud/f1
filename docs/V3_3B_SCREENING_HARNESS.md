# V3.3B CONTROLLED SCREENING HARNESS

## Final verdict

V3.3B COMPLETE — SCREENING HARNESS VALIDATED — READY FOR V3.3C.
All outputs labelled HARNESS_SMOKE_ONLY; no candidate was ranked,
eliminated, calibrated, or ensembled.

## Frozen parent

- tag: `v3.2-monte-carlo-2`, commit `197979d40af0c9dbf90667781d9c83e41613b047`
- HEAD verified equal; working tree holds V3.3A + V3.3B only, nothing
  staged/committed/tagged/pushed.

## V3.3A contract

- schema `v3.3a-experiment-contract-v1`,
  SHA256 `d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7`
- verified by every B script via `verify_contracts()` (fail-closed).

## B preregistration

- `results/v3/v3_3b/preregistration.json`, schema
  `v3.3b-preregistration-v1`
- identity `da60e8d9824cd284c830b0bb9b580db2f7a713f06e8c2fa61e459795b8b712d8`
- frozen by `scripts/freeze_v3_3b_prereg.py` before any smoke fit; grids
  frozen since.

## Existing infrastructure reused

- `v3_dynamics_experiment`: joined-frame loader, `v3_feature_names`,
  `materialize_v3`, `paired_bootstrap`, holdout firewall.
- `splits` (D1/D2/D3 + M0 audits), `inner_splits` (nested temporal folds),
  `preprocessing` (TRAIN-only), `runner.evaluate_*`, `aggregation`
  (race-macro headline), `stages`, `calibration`, `predictions`,
  `tuning_candidates` (LogReg/ET estimator semantics).
- New code is confined to `raceintel/model_lab/v3_3b_harness.py` plus two
  scripts and one test module.

## 110-column materialization

- `feature_names_110()`: ALL_84 (frozen order) + CORE_26 (frozen order).
- `state_id` one-to-one join; row-position joins forbidden.
- `check_feature_contract()`: 84/26/110 counts, prefix/suffix order, no
  overlap, 3 sidecar non-CORE columns excluded, no duplicates, hash
  `sha256("\n".join(names))` persisted.

## V3.1 parity

- Same eligible rows (88123/23577 on D1 = M0 audit), labels identical to
  canonical frame, state identities 1:1, 84-prefix byte-equal, masks match
  Arm A, CORE values from the verified sidecar.
- Logistic control reproduces V3.1B/C Arm-B D1 bit-exactly (see gate).

## 84-column control

- Arm A materialized through the same frozen path; row/label/fold
  identity matches the primary arm; counts equal M0.

## Candidate registry

Exactly `logistic_regression`, `hist_gradient_boosting`, `extra_trees`,
`xgboost` — each with family ID, implementation + version, pipeline
factory, parameter namespace, seed/thread/missing-value/scaling policy,
RAW probability interface, serialization type. No results in config.

## Candidate grids

- logistic_regression: 4 (C in 0.003/0.01/0.03/0.1; frozen C=0.01 inside)
- hist_gradient_boosting: 8 (lr x leaves x min_leaf; early stopping OFF)
- extra_trees: 8 (max_features x min_samples_leaf x max_depth)
- xgboost: 8 (lr x depth x min_child_weight; hist/CPU/n_jobs=4)
- All <= 12; deterministic IDs; frozen complexity ordering.

## Logistic pipeline

`TC.build_estimator` with C from config; frozen TRAIN-only preprocessing;
frozen C=0.01 control reproduces V3.1B exactly.

## HGB pipeline

`HistGradientBoostingClassifier(loss=log_loss, max_iter=200,
early_stopping=False, random_state=42)`; identical frozen preprocessing
(native NaN unused — documented, keeps arms comparable).

## Extra Trees pipeline

`TC.build_estimator` (n_estimators=300, bootstrap=False, n_jobs=4,
random_state=42); RAW independent binary output.

## XGBoost pipeline

Pinned `xgboost==3.2.0`, `XGBClassifier(objective=binary:logistic,
tree_method=hist, n_jobs=4, random_state=42)`; no dependency change; no
external/2025 early stopping.

## Inner-fold tuning

`tune_family()`: M6 expanding-window inner folds inside outer TRAIN only;
mean inner race-macro LL objective; tie <= 1e-6 -> simpler config;
outer validation never touched. Proven on D1 logistic (selected C=0.003).

## Outer-fold evaluation

Exact D1/D2/D3 via `resolve_development_fold`; selected config refit on
full outer TRAIN, single validation prediction; 2025 unreachable.

## OOF contract

Columns: state_id/season/race_id/driver_id/target/fold/stage/
feature_arm/model_family/model_config_id/probability (+ optional
baseline_probability; canonical baseline table stored once).
Unique identity, stable sort, typed 0<=p<=1, no missing targets;
parquets under ignored `data/v3/v3_3b/`.

## Metrics

Reused frozen `metrics` + `aggregation`: race-macro LL primary; Brier,
ROC/PR AUC, ECE, top-1/top-3; state-pooled + EARLY/MID/LATE diagnostics.
No candidate-specific exceptions.

## Race-level comparison

Per-race candidate-minus-baseline deltas + paired race bootstrap
(B=2000, seed=42, 95% CI); mean/races improved/worsened/ties. Smoke
values recorded only — NOT used for KEEP/REJECT.

## Diversity support

Aligned prediction/residual correlation, mean abs gap, per-race deltas
available from OOF pairs. No ensemble optimization.

## 2025 firewall

`assert_development_fold` + `assert_no_holdout_request` + season scans;
HOLDOUT/2025/FINAL_FIT and indirect tuning attempts all raise
`ProtectedHoldoutError` (tested direct + indirect). 2025 never loaded.

## Provenance

Every envelope: A SHA, B SHA, dataset/feature/task/fold identity, family,
config ID, hyperparameters, library versions (sklearn 1.8.0,
xgboost 3.2.0), seed 42, thread policy, seasons, code commit.

## Determinism

Double-fit max-abs diff = 0.0 for all four families (tolerance 1e-9
LogReg, 1e-6 trees; tree CPU bit-exactness documented, not silenced).

## Smoke experiment

D1 only, one config per family, labelled HARNESS_SMOKE_ONLY:
LL 0.080675 (LogReg) / 0.254626 (HGB) / 0.093539 (ET) / 0.124247 (XGB).
No ranking, no elimination. Harness paths (fit/predict/metrics/OOF/
comparison/provenance) proven end to end.

## Logistic parity gate

PASS: max abs prob diff 0.0, race-macro LL diff 0.0, Brier diff 0.0,
top-1 0.6720482644347198 consistent with V3.1C.

## Compute profile

Smoke fits: 9.3/12.4/13.8/11.1 s per family; wall 93.6 s. Projected full
screening 2137.8 s total (<= 7200) and <= 705 s per family (<= 3600):
budget gate PASS with no grid shrinkage.

## Serialization

joblib round-trip diff 0.0 for all four families. No final artifacts
created; smoke files live in ignored paths.

## Failure behavior

Wrong feature count/identity, missing CORE, duplicate state, misaligned
join, 2025 input, unknown family/config, invalid probabilities,
duplicate OOF identity, missing target, fold mismatch — all raise loudly.

## Tests

`tests/test_v3_3b_harness.py` (20) + A contract (14): 34 passed.
Related: M0/M7/M8 (114 passed after M0 allowlist entry for the B harness
per V3.1C precedent), M6 + A (50 passed), V3.1 dynamics governance (23
passed). FULL_TIER1 = NOT_REQUIRED_RESEARCH_INFRA_ONLY.

## Known limitations

- Smoke covers D1 only; D2/D3 outer paths reuse the same code but ran no
  fits in B (belongs to C).
- Inner tuning proven on D1 logistic; tree-family inner loops are
  machinery-identical but unfitted until C.
- Tree CPU bit-exactness across BLAS/OpenMP builds carries a documented
  1e-6 tolerance (observed 0.0 here).
- Single 24-race 2025 holdout stays sealed; CIs in C remain honest.

## V3.3C recommendation

Proceed to full four-family screening on D1/D2/D3 with the frozen grids;
no contract amendment needed (parity exact, firewall holds, budget at
~30% of allowance).

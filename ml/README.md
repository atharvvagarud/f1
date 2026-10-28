# ml/

Live V1 baseline inference surface. Not obsolete — do not delete,
move, or "modernize" this package merely because newer model systems
exist.

## Purpose

`ml/` retains the V1 lap-checkpoint prediction path: checkpoint/model
registries, the load-bearing inference feature-column order, and
framework-free prediction logic (single-model inference plus the
majority-vote ensemble with XGBoost tie-break) over `data/processed/`
datasets and `results/models/` pipelines.

It is live. It serves the R4 prediction route via
`api/services/prediction_service.py`, is imported by
`tests/conftest.py` and the V1 regression tests (`test_ensemble.py`,
`test_prediction_equivalence.py`, `test_model_loading.py`,
`test_datasets.py`, `test_known_defects.py`), and is baked into the
backend image (`Dockerfile.backend` COPYs `ml/`).

## Relationship to `raceintel/model_lab`

Distinct systems, not duplicate implementations:

- `ml/` — V1 lap-checkpoint baselines (logreg/HGB/XGBoost per lap
  5–25, `results/models/*_multilap`), preserved as the frozen
  regression baseline and legacy serving path.
- `raceintel/model_lab` — V2 winner-model programme over canonical
  D9 states, served via
  `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
  (`FrozenWinnerPredictor`).

Neither replaces the other. The V1 path exists so behavior
regressions against the original product stay detectable.

## Maintenance

Content and order are load-bearing: saved pipelines were fitted
against `FEATURE_COLS` exactly, and known defects (e.g. the
Monaco-2022 NaN passthrough) are intentionally preserved and pinned
by regression tests. Changes here require regression-test sign-off.

## New development

New reusable ML/domain logic belongs in `raceintel/` per the C3
forward rule (see `scripts/README.md`). `ml/` changes only to fix
the V1 serving path itself. There is no migration roadmap: `ml/`
stays as the frozen baseline.

"""M6 bounded deterministic tuning engine.

Two predeclared, small, scientifically defensible grids are searched with the
race-macro log loss objective using only chronology-preserving inner folds:

- Logistic Regression: a 6-value ``C`` grid (the M3 reference ``C=1.0`` is
  included; solver/penalty/class_weight/max_iter/seed stay frozen).
- ExtraTrees: a 12-configuration grid over ``max_features`` x
  ``min_samples_leaf`` x ``max_depth`` (the M5 reference configuration is
  included; n_estimators/criterion/bootstrap/class_weight/n_jobs/seed stay
  frozen).

No adaptive search: every configuration in the grid is fit on every inner
fold. The selection objective is the simple mean of inner-fold race-macro log
loss. Ties within a fixed numerical tolerance are resolved by a tie-break rule
frozen here BEFORE any result is observed (prefer the simpler / more
regularized configuration).

This module only touches inner folds contained in an outer TRAIN history; it
never receives outer validation frames, so the outer validation season cannot
influence the search. The outer refit/evaluation lives in
``tuning_runner``.
"""

from __future__ import annotations

import numpy as np

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import data as DATA
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab.errors import ExperimentConfigError
from raceintel.model_lab.inner_splits import (
    inner_split_frame,
    resolve_inner_splits,
)
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON

#: M6 scope (identical to M3/M4/M5).
M6_TASK = "winner"
M6_FEATURE_SET = "ALL_84"
M6_SEED = 42

#: Predeclared LogReg grid: regularization strength only.
LOGREG_C_GRID = (0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
LOGREG_GRID = tuple({"C": c} for c in LOGREG_C_GRID)

#: Predeclared ExtraTrees grid: 2 x 3 x 2 = 12 configurations.
EXTRA_TREES_MAX_FEATURES = ("sqrt", 0.5)
EXTRA_TREES_MIN_SAMPLES_LEAF = (1, 3, 10)
EXTRA_TREES_MAX_DEPTH = (None, 20)
EXTRA_TREES_GRID = tuple(
    {"max_features": mf, "min_samples_leaf": msl, "max_depth": md}
    for mf in EXTRA_TREES_MAX_FEATURES
    for msl in EXTRA_TREES_MIN_SAMPLES_LEAF
    for md in EXTRA_TREES_MAX_DEPTH
)

#: Absolute numerical tolerance for "effectively equal" mean inner log loss.
TIE_TOLERANCE = 1e-6

#: Frozen tie-break description (declared before executing the search).
TIE_BREAK_RULE = {
    "tolerance_abs": TIE_TOLERANCE,
    "objective": "mean inner-fold race-macro log loss (lower is better)",
    "rule": "among configurations whose mean is within tolerance of the best "
            "mean, prefer the simpler / more regularized configuration",
    "logistic_regression": "smaller C (stronger L2 regularization) wins a tie",
    "extra_trees": "larger min_samples_leaf, then max_depth=20 over None, "
                   "then max_features=sqrt over 0.5",
    "frozen_before_results": True,
}

SUPPORTED_FAMILIES = (TC.LOGREG_FAMILY, TC.EXTRA_TREES_FAMILY)
GRIDS = {
    TC.LOGREG_FAMILY: LOGREG_GRID,
    TC.EXTRA_TREES_FAMILY: EXTRA_TREES_GRID,
}


def grid_for(family: str) -> tuple:
    if family not in GRIDS:
        raise ExperimentConfigError(
            f"M6 tunes {list(SUPPORTED_FAMILIES)} only; got {family!r}")
    return GRIDS[family]


def config_key(family: str, config: dict) -> str:
    """Deterministic human-readable configuration key for artifacts."""
    if family == TC.LOGREG_FAMILY:
        return f"C={config['C']:g}"
    if family == TC.EXTRA_TREES_FAMILY:
        depth = "None" if config["max_depth"] is None else str(
            config["max_depth"])
        return (f"max_features={config['max_features']};"
                f"min_samples_leaf={config['min_samples_leaf']};"
                f"max_depth={depth}")
    raise ExperimentConfigError(f"unknown M6 family {family!r}")


def tiebreak_rank(family: str, config: dict) -> tuple:
    if family == TC.LOGREG_FAMILY:
        return (config["C"],)
    if family == TC.EXTRA_TREES_FAMILY:
        return (
            -int(config["min_samples_leaf"]),
            0 if config["max_depth"] is not None else 1,
            0 if config["max_features"] == "sqrt" else 1,
        )
    raise ExperimentConfigError(f"unknown M6 family {family!r}")


def planned_fit_count(folds=("D1", "D2", "D3")) -> dict:
    """Exact pre-execution estimator-fit budget (estimator fits only)."""
    per_family: dict = {}
    for family in SUPPORTED_FAMILIES:
        folds_detail: dict = {}
        total = 0
        for fold in folds:
            inner = resolve_inner_splits(fold)
            fits = len(inner) * len(grid_for(family))
            folds_detail[fold] = {"inner_folds": len(inner),
                                  "configs": len(grid_for(family)),
                                  "estimator_fits": fits}
            total += fits
        per_family[family] = {"per_fold": folds_detail,
                              "inner_estimator_fits": total}
    inner_total = sum(v["inner_estimator_fits"] for v in per_family.values())
    outer_fits = len(folds) * len(SUPPORTED_FAMILIES)
    determinism_fits = len(SUPPORTED_FAMILIES)
    return {
        "families": per_family,
        "inner_estimator_fits": inner_total,
        "outer_selected_refits": outer_fits,
        "determinism_refits": determinism_fits,
        "total_estimator_fits": inner_total + outer_fits + determinism_fits,
        "search_executes_every_config": True,
        "adaptive_search": False,
    }


def aggregate_scores(family: str, scores: dict) -> dict:
    """Per-config mean/std/min/max/range across inner folds."""
    out: dict = {}
    for config in grid_for(family):
        key = config_key(family, config)
        values = {name: scores[name][key] for name in scores}
        out[key] = {
            "config": dict(config),
            **AGG.aggregate_folds(values),
        }
    return out


def select_configuration(family: str, aggregates: dict) -> dict:
    """Pick the best configuration with the predeclared tie-break."""
    defined = {k: v for k, v in aggregates.items()
               if v.get("mean") is not None and np.isfinite(v["mean"])}
    if not defined:
        raise ExperimentConfigError(
            f"{family}: no configuration produced a finite inner log loss")
    best_mean = min(v["mean"] for v in defined.values())
    within = [k for k, v in defined.items()
              if v["mean"] <= best_mean + TIE_TOLERANCE]
    chosen_key = min(
        within, key=lambda k: tiebreak_rank(family, defined[k]["config"]))
    return {
        "selected_key": chosen_key,
        "selected_config": dict(defined[chosen_key]["config"]),
        "selected_mean": defined[chosen_key]["mean"],
        "best_mean": best_mean,
        "within_tolerance": sorted(within),
        "tie_break_applied": len(within) > 1,
        "selection_reason": (
            f"lowest mean inner race-macro log loss ({best_mean:.10f})"
            if len(within) == 1 else
            "mean within tolerance of best; predeclared simpler/more "
            "regularized tie-break applied"),
    }


def tune_family(canonical: DATA.CanonicalMatrix, family: str,
                outer_fold: str, *, task: str = M6_TASK,
                feature_set: str = M6_FEATURE_SET) -> dict:
    """Search the frozen grid on inner folds only (outer validation absent)."""
    if task != M6_TASK:
        raise ExperimentConfigError(
            f"M6 tunes task {M6_TASK!r} only; got {task!r}")
    if feature_set != M6_FEATURE_SET:
        raise ExperimentConfigError(
            f"M6 tunes feature set {M6_FEATURE_SET!r} only; got "
            f"{feature_set!r}")
    grid = grid_for(family)
    splits = resolve_inner_splits(outer_fold)
    scores: dict = {s.inner_fold_id: {} for s in splits}
    inner_records: list = []
    estimator_fits = 0
    preprocessor_fits = 0

    for split in splits:
        (X_train, y_train, meta_train, X_val, y_val,
         meta_val) = inner_split_frame(
            canonical, split, task, feature_set)
        seasons = set(meta_train["season"].astype(int)) | set(
            meta_val["season"].astype(int))
        if PROTECTED_HOLDOUT_SEASON in seasons:
            raise ExperimentConfigError(
                f"{split.inner_fold_id}: protected holdout reached tuning")

        with TIMING.Timer() as t_pre:
            preprocessor = PRE.fit_preprocessor(X_train, canonical.schema)
        preprocessor_fits += 1
        with TIMING.Timer() as t_tr:
            Z_train = preprocessor.transform(X_train)
            Z_val = preprocessor.transform(X_val)

        yv = np.asarray(y_val.astype(float), dtype=float)
        race_ids = np.asarray(meta_val["race_id"].astype(str))
        y_train_arr = np.asarray(y_train.astype(float), dtype=float)
        fold_configs: dict = {}
        fold_fit_seconds = 0.0
        fold_predict_seconds = 0.0
        fold_eval_seconds = 0.0
        fold_warnings: list = []

        for config in grid:
            key = config_key(family, config)
            with TIMING.Timer() as t_fit:
                model = TC.fit_fresh_model(
                    family, config, X_train, y_train_arr,
                    preprocessor=preprocessor, precomputed_matrix=Z_train)
            estimator_fits += 1
            fold_fit_seconds += t_fit.seconds
            with TIMING.Timer() as t_pred:
                probabilities = model.predict_positive_probability(X_val)
            fold_predict_seconds += t_pred.seconds
            if not np.all(np.isfinite(probabilities)):
                raise ExperimentConfigError(
                    f"{split.inner_fold_id} {key}: non-finite probabilities")
            with TIMING.Timer() as t_eval:
                race_macro = AGG.race_macro(
                    yv, probabilities, race_ids, "log_loss")
            fold_eval_seconds += t_eval.seconds
            value = race_macro["value"]
            scores[split.inner_fold_id][key] = float(value)
            for message in model.fit_warnings:
                fold_warnings.append(f"{key}: {message}")
            fold_configs[key] = {
                "hyperparameters": dict(config),
                "race_macro_log_loss": float(value),
                "n_races": int(race_macro["n_races"]),
                "n_races_defined": int(race_macro["n_races_defined"]),
                "n_states": int(race_macro["n_states"]),
                "warnings": list(model.fit_warnings),
            }

        inner_records.append({
            "inner_fold_id": split.inner_fold_id,
            "train_seasons": list(split.train_seasons),
            "validation_seasons": list(split.validation_seasons),
            "train_rows": int(len(X_train)),
            "train_races": int(meta_train["race_id"].nunique()),
            "validation_rows": int(len(X_val)),
            "validation_races": int(meta_val["race_id"].nunique()),
            "preprocessing_fit_seconds": t_pre.seconds,
            "transform_seconds": t_tr.seconds,
            "estimator_fit_seconds": fold_fit_seconds,
            "predict_seconds": fold_predict_seconds,
            "evaluation_seconds": fold_eval_seconds,
            "warnings": fold_warnings,
            "configs": fold_configs,
        })
        del Z_train, Z_val, preprocessor

    aggregates = aggregate_scores(family, scores)
    selection = select_configuration(family, aggregates)
    selection["family"] = family
    selection["outer_fold"] = outer_fold
    selection["objective"] = "race_macro_log_loss (simple mean over inner folds)"
    selection["estimator_fits"] = estimator_fits
    selection["preprocessor_fits"] = preprocessor_fits
    return {
        "family": family,
        "outer_fold": outer_fold,
        "feature_set": feature_set,
        "task": task,
        "inner_folds": inner_records,
        "config_aggregates": aggregates,
        "selection": selection,
        "estimator_fits": estimator_fits,
        "preprocessor_fits": preprocessor_fits,
    }

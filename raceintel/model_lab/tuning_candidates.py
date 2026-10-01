"""M6 trainable candidates: parameterized LogReg + ExtraTrees.

The M6 search may train exactly two estimator families, built here with the
hyperparameters selected by the deterministic inner search:

- ``LogisticRegression`` (only ``C`` varies; solver/penalty/class_weight/
  iteration budget/seed are fixed to the frozen M3 semantics);
- ``ExtraTreesClassifier`` (only ``max_features`` / ``min_samples_leaf`` /
  ``max_depth`` vary; criterion/bootstrap/class_weight/n_estimators/n_jobs/
  seed are fixed to the frozen M5 semantics).

No other estimator family is constructed. Preprocessing is the frozen M3/M4/M5
train-fitted pipeline (``v2.model_lab.preprocessing``), fitted only on the
supplied training rows. The fitted object emits
``PredictionKind.BINARY_PROBABILITY`` / ``ProbabilitySemantics.INDEPENDENT_BINARY``
and never normalizes across drivers.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression

from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab.errors import ExperimentConfigError, InvalidPredictionError
from raceintel.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

#: Base candidate family ids used by the tuning search.
LOGREG_FAMILY = "logistic_regression"
EXTRA_TREES_FAMILY = "extra_trees"

#: Outer experiment family names (distinct from the M3/M5 reference ids so a
#: selected configuration can never overwrite a stored reference result).
TUNED_FAMILY_NAMES = {
    LOGREG_FAMILY: "logistic_regression_tuned",
    EXTRA_TREES_FAMILY: "extra_trees_tuned",
}

#: Fixed LogReg semantics (only C is searched).
LOGREG_FIXED = {
    "solver": "lbfgs",
    "max_iter": 1000,
    "class_weight": None,
    "random_state": 42,
}
#: Fixed ExtraTrees semantics (only the three capacity params are searched).
EXTRA_TREES_FIXED = {
    "n_estimators": 300,
    "criterion": "gini",
    "min_samples_split": 2,
    "bootstrap": False,
    "class_weight": None,
    "n_jobs": 4,
    "random_state": 42,
}

SKLEARN_VERSION = __import__("sklearn").__version__


def build_estimator(family: str, parameters: dict):
    """Construct one fresh estimator for the given family + parameters."""
    if family == LOGREG_FAMILY:
        return LogisticRegression(
            C=parameters["C"],
            solver=LOGREG_FIXED["solver"],
            max_iter=LOGREG_FIXED["max_iter"],
            class_weight=LOGREG_FIXED["class_weight"],
            random_state=LOGREG_FIXED["random_state"],
        )
    if family == EXTRA_TREES_FAMILY:
        return ExtraTreesClassifier(
            n_estimators=EXTRA_TREES_FIXED["n_estimators"],
            criterion=EXTRA_TREES_FIXED["criterion"],
            max_depth=parameters["max_depth"],
            min_samples_split=EXTRA_TREES_FIXED["min_samples_split"],
            min_samples_leaf=parameters["min_samples_leaf"],
            max_features=parameters["max_features"],
            bootstrap=EXTRA_TREES_FIXED["bootstrap"],
            class_weight=EXTRA_TREES_FIXED["class_weight"],
            n_jobs=EXTRA_TREES_FIXED["n_jobs"],
            random_state=EXTRA_TREES_FIXED["random_state"],
        )
    raise ExperimentConfigError(
        f"M6 trains {LOGREG_FAMILY!r}/{EXTRA_TREES_FAMILY!r} only; "
        f"got {family!r}")


def resolved_model_parameters(family: str, parameters: dict) -> dict:
    """Full resolved parameter mapping recorded in experiment identity."""
    if family == LOGREG_FAMILY:
        return {
            "estimator": "LogisticRegression",
            "penalty": "l2 (sklearn default, not passed explicitly)",
            "C": parameters["C"],
            **{k: LOGREG_FIXED[k] for k in
               ("solver", "max_iter", "class_weight", "random_state")},
        }
    if family == EXTRA_TREES_FAMILY:
        return {
            "estimator": "ExtraTreesClassifier",
            "max_depth": parameters["max_depth"],
            "min_samples_leaf": parameters["min_samples_leaf"],
            "max_features": parameters["max_features"],
            **{k: EXTRA_TREES_FIXED[k] for k in
               ("n_estimators", "criterion", "min_samples_split",
                "bootstrap", "class_weight", "n_jobs", "random_state")},
        }
    raise ExperimentConfigError(f"unknown M6 family {family!r}")


class FittedTunedModel:
    """One fitted M6 model: frozen preprocessing + parameterized estimator."""

    def __init__(self, family: str, parameters: dict,
                 preprocessor: PRE.FittedPreprocessor, estimator,
                 positive_index: int, feature_names: tuple,
                 timing: dict, fit_warnings: list, n_train: int) -> None:
        self.family = family
        self.parameters = dict(parameters)
        self.preprocessor = preprocessor
        self.estimator = estimator
        self._positive_index = int(positive_index)
        self._feature_names = tuple(feature_names)
        self.timing = dict(timing)
        self.fit_warnings = list(fit_warnings)
        self.n_train = int(n_train)

    def transform(self, X) -> np.ndarray:
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        if tuple(frame.columns) != self._feature_names:
            raise ExperimentConfigError(
                "predict frame columns do not match the fitted feature order")
        return self.preprocessor.transform(frame)

    def predict_positive_probability(self, X) -> np.ndarray:
        matrix = self.transform(X)
        if not np.all(np.isfinite(matrix)):
            raise InvalidPredictionError(
                "transformed prediction matrix contains NaN/inf")
        proba = self.estimator.predict_proba(matrix)
        column = np.asarray(proba[:, self._positive_index], dtype=float)
        if not np.all(np.isfinite(column)):
            raise InvalidPredictionError("estimator returned NaN/inf probability")
        if np.any(column < 0.0) or np.any(column > 1.0):
            raise InvalidPredictionError("estimator probability outside [0, 1]")
        return column

    def predict_result(self, X, state_ids) -> PredictionResult:
        return PredictionResult(
            kind=PredictionKind.BINARY_PROBABILITY,
            state_ids=tuple(state_ids),
            values=self.predict_positive_probability(X),
            semantics=ProbabilitySemantics.INDEPENDENT_BINARY,
            positive_class=1,
        )

    def sanity(self) -> dict:
        out = {
            "transformed_dim": int(self.preprocessor.output_dim),
            "classes": [int(c) for c in self.estimator.classes_],
            "fit_warnings": list(self.fit_warnings),
            "n_train": int(self.n_train),
        }
        importance = getattr(self.estimator, "feature_importances_", None)
        if importance is not None:
            values = np.asarray(importance, dtype=float)
            out["feature_importances"] = {
                "n_features": int(values.size),
                "finite": bool(np.all(np.isfinite(values))),
                "nonzero": int(np.count_nonzero(values)),
            }
        coef = getattr(self.estimator, "coef_", None)
        if coef is not None:
            coef = np.asarray(coef, dtype=float).ravel()
            out["coefficient_sanity"] = {
                "n_coefficients": int(coef.size),
                "all_zero": bool(np.all(coef == 0.0)),
                "any_nan": bool(np.any(~np.isfinite(coef))),
                "max_abs_coef": float(np.max(np.abs(coef))) if coef.size else None,
            }
        return out


def fit_fresh_model(family: str, parameters: dict, X_train, y_train, *,
                    preprocessor: PRE.FittedPreprocessor | None = None,
                    precomputed_matrix: np.ndarray | None = None,
                    ) -> FittedTunedModel:
    """Fit preprocessing (unless reused) + estimator on training rows only."""
    from raceintel.model_lab.data import load_canonical
    import time as _time

    frame = X_train if isinstance(X_train, pd.DataFrame) else pd.DataFrame(
        X_train)
    target = np.asarray(y_train).astype(float).ravel()
    if len(frame) != len(target):
        raise ExperimentConfigError("X/y length mismatch in M6 fit")
    if set(np.unique(target)) - {0.0, 1.0}:
        raise ExperimentConfigError("winner target must be binary 0/1")

    timing: dict = {}
    if preprocessor is None:
        start = _time.perf_counter()
        preprocessor = PRE.fit_preprocessor(frame, load_canonical().schema)
        timing["preprocessing_fit_seconds"] = _time.perf_counter() - start
    else:
        timing["preprocessing_fit_seconds"] = 0.0

    if precomputed_matrix is None:
        start = _time.perf_counter()
        matrix = preprocessor.transform(frame)
        timing["transform_train_seconds"] = _time.perf_counter() - start
    else:
        matrix = precomputed_matrix
        timing["transform_train_seconds"] = 0.0

    start = _time.perf_counter()
    estimator = build_estimator(family, parameters)
    fit_warnings: list = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimator.fit(matrix, target)
        for item in caught:
            fit_warnings.append(f"{item.category.__name__}: {item.message}")
    timing["estimator_fit_seconds"] = _time.perf_counter() - start

    classes = list(estimator.classes_)
    if 1 not in classes:
        raise InvalidPredictionError(
            f"estimator classes {classes} do not contain positive class 1")
    return FittedTunedModel(
        family=family, parameters=parameters, preprocessor=preprocessor,
        estimator=estimator, positive_index=int(classes.index(1)),
        feature_names=tuple(frame.columns), timing=timing,
        fit_warnings=fit_warnings, n_train=len(target))

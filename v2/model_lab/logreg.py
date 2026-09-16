"""M3 Logistic Regression reference model (single fixed, untuned spec).

This is the FIRST and ONLY candidate ML model for M3. The specification was
fixed before inspecting M3 validation performance and is justified by:

- M0 protocol candidate semantics (``logistic_regression`` tier entry:
  impute + scale pipeline, one-hot train-fitted categoricals, calibrated
  binary probability output, low compute class, sklearn dependency).
- Dataset characteristics: 84 predictive features on mixed numeric/bool/
  categorical dtypes; a rare positive class (~5.5%) evaluated for
  probability quality under the frozen ``state_equal`` training weighting
  (no resampling, no class_weight rebalancing).
- Deterministic execution: ``lbfgs`` is deterministic for fixed data; an
  explicit seed is recorded even though this solver ignores randomness.
- Convergence practicality: ``max_iter=1000`` (technical increase over the
  sklearn default of 100 for ~10^5 rows x ~10^2 columns) with train-fitted
  scaling inspected first if a convergence warning appears.
- Probability output support: binary ``predict_proba`` with the positive
  class (``is_winner == 1``) resolved explicitly from ``classes_``.

NO TUNING was performed: no grid/random/Bayesian search, no C/penalty/
solver/weight sweeps, no feature selection on validation results, no
threshold optimization, no post-hoc calibration.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from v2.model_lab import preprocessing as PRE
from v2.model_lab.errors import ExperimentConfigError, InvalidPredictionError
from v2.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

#: Canonical M3 model family name (used in experiment identity).
LOGREG_FAMILY = "logistic_regression"

#: Short CLI alias accepted by the M3 runner CLIs.
LOGREG_ALIAS = "LOGREG"

#: Fixed, untuned reference specification (resolved values, no hidden defaults).
#: ``penalty`` is the sklearn default (l2); it is recorded here as the
#: resolved value but NOT passed explicitly because sklearn 1.8 deprecates
#: the ``penalty`` parameter (FutureWarning, removal in 1.10) — passing it
#: would add warning noise without changing the estimator.
LOGREG_SPEC = {
    "estimator": "LogisticRegression",
    "penalty": "l2 (sklearn default, not passed explicitly)",
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "class_weight": None,
    "random_state": 42,
}

#: Task / feature / seed contract for the reference model.
LOGREG_TASK = "winner"
LOGREG_FEATURE_SET = "ALL_84"
LOGREG_SEED = 42

#: sklearn runtime recorded at fit time (stored in artifact metadata).
SKLEARN_VERSION = __import__("sklearn").__version__


def logreg_model_parameters() -> dict:
    """Resolved model parameters for experiment identity (no hidden defaults)."""
    return dict(LOGREG_SPEC)


def build_estimator() -> LogisticRegression:
    """Construct one fresh untuned Logistic Regression estimator."""
    return LogisticRegression(
        C=LOGREG_SPEC["C"],
        solver=LOGREG_SPEC["solver"],
        max_iter=LOGREG_SPEC["max_iter"],
        class_weight=LOGREG_SPEC["class_weight"],
        random_state=LOGREG_SPEC["random_state"],
    )


class LogisticRegressionAdapter:
    """Concrete M1 ModelAdapter for the M3 reference model.

    Lifecycle: ``fit`` (TRAIN only) -> ``predict_positive_probability`` /
    ``predict`` / ``predict_result`` (validation, transform-only). One adapter
    instance is fitted exactly once per fold; no fitted object crosses folds.
    """

    family = LOGREG_FAMILY

    def __init__(self) -> None:
        self._preprocessor: PRE.FittedPreprocessor | None = None
        self._estimator: LogisticRegression | None = None
        self._positive_index: int | None = None
        self._feature_names: tuple | None = None
        self.convergence_warnings: list = []
        self.timing: dict = {}

    @property
    def is_fitted(self) -> bool:
        return self._estimator is not None and self._preprocessor is not None

    def fit(self, X, y):  # noqa: ANN001, ANN201
        """Fit preprocessing + estimator on TRAIN data only."""
        if self.is_fitted:
            raise ExperimentConfigError(
                "adapter is already fitted; use a fresh adapter per fold")
        from v2.model_lab.data import load_canonical

        schema = load_canonical().schema
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        target = np.asarray(y).astype(float).ravel()
        if len(frame) != len(target):
            raise ExperimentConfigError("X/y length mismatch in adapter fit")
        if set(np.unique(target)) - {0.0, 1.0}:
            raise ExperimentConfigError("winner target must be binary 0/1")
        self._feature_names = tuple(frame.columns)
        import time as _time

        start = _time.perf_counter()
        self._preprocessor = PRE.fit_preprocessor(frame, schema)
        preprocessing_seconds = _time.perf_counter() - start
        start = _time.perf_counter()
        matrix = self._preprocessor.transform(frame)
        transform_train_seconds = _time.perf_counter() - start
        start = _time.perf_counter()
        estimator = build_estimator()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            estimator.fit(matrix, target)
            for item in caught:
                message = str(item.message)
                self.convergence_warnings.append(
                    f"{item.category.__name__}: {message}")
        estimator_seconds = _time.perf_counter() - start
        self.timing = {
            "preprocessing_fit_seconds": preprocessing_seconds,
            "transform_train_seconds": transform_train_seconds,
            "estimator_fit_seconds": estimator_seconds,
        }
        classes = list(estimator.classes_)
        if 1 not in classes:
            raise InvalidPredictionError(
                f"estimator classes {classes} do not contain positive class 1")
        self._positive_index = int(classes.index(1))
        self._estimator = estimator
        return self

    def _matrix_for(self, X) -> np.ndarray:
        if not self.is_fitted:
            raise ExperimentConfigError("adapter must be fitted before predict")
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        if self._feature_names is not None and tuple(
                frame.columns) != self._feature_names:
            raise ExperimentConfigError(
                "predict frame columns do not match the fitted feature order")
        matrix = self._preprocessor.transform(frame)
        if not np.all(np.isfinite(matrix)):
            raise InvalidPredictionError(
                "transformed validation matrix contains NaN/inf")
        return matrix

    def predict_positive_probability(self, X) -> np.ndarray:  # noqa: ANN001, ANN201
        """P(driver eventually wins | observable state) for is_winner == 1."""
        matrix = self._matrix_for(X)
        proba = self._estimator.predict_proba(matrix)
        column = proba[:, self._positive_index]
        if not np.all(np.isfinite(column)):
            raise InvalidPredictionError("estimator returned NaN/inf probability")
        if np.any(column < 0.0) or np.any(column > 1.0):
            raise InvalidPredictionError("estimator probability outside [0, 1]")
        return np.asarray(column, dtype=float)

    def predict(self, X):  # noqa: ANN001, ANN201
        return self.predict_positive_probability(X)

    def predict_result(self, X, state_ids) -> PredictionResult:
        """INDEPENDENT_BINARY per-driver probabilities (never normalized)."""
        values = self.predict_positive_probability(X)
        return PredictionResult(
            kind=PredictionKind.BINARY_PROBABILITY,
            state_ids=tuple(state_ids),
            values=np.asarray(values, dtype=float),
            semantics=ProbabilitySemantics.INDEPENDENT_BINARY,
            positive_class=1,
        )

    def coefficient_sanity(self) -> dict:
        """Minimal implementation-failure screen (not explainability)."""
        if not self.is_fitted:
            raise ExperimentConfigError("adapter must be fitted for sanity check")
        coef = np.asarray(self._estimator.coef_).ravel()
        intercept = np.asarray(self._estimator.intercept_).ravel()
        return {
            "n_coefficients": int(coef.size),
            "transformed_dim": int(self._preprocessor.output_dim),
            "all_zero": bool(np.all(coef == 0.0)),
            "any_nan": bool(np.any(~np.isfinite(coef))),
            "intercept_finite": bool(np.all(np.isfinite(intercept))),
            "max_abs_coef": float(np.max(np.abs(coef))) if coef.size else None,
        }

    def metadata(self) -> dict:
        return {
            "family": self.family,
            "model_parameters": logreg_model_parameters(),
            "preprocessing": PRE.preprocessing_contract_dict(),
            "sklearn_version": SKLEARN_VERSION,
            "feature_set": LOGREG_FEATURE_SET,
            "task": LOGREG_TASK,
            "seed": LOGREG_SEED,
            "positive_class": 1,
            "probability_semantics": ProbabilitySemantics.INDEPENDENT_BINARY.value,
        }

"""M4 nonlinear tree candidates: HistGradientBoosting + XGBoost (fixed specs).

Two representative nonlinear candidate families for the PRIMARY winner task,
evaluated through the exact M2/M3 canonical path (adapter -> PredictionResult
-> M2 evaluator -> experiment artifact -> suite summary). M4 EXTENDS the M3
path; it does not redesign it. No tuning of any kind was performed: one
fixed specification per family was chosen BEFORE inspecting D1/D2/D3
validation results.

Fixed-specification rationale (documented before validation):

- HGB: sklearn defaults throughout (the representative out-of-box
  HistGradientBoostingClassifier) with ONE justified non-default:
  ``early_stopping=False``. The sklearn 1.8 default ``early_stopping="auto"``
  reserves 10% of the training rows as an internal validation split for
  early stopping; M4 forbids validation-driven training, so all training
  rows train all ``max_iter=100`` iterations. ``random_state=42`` per the
  frozen project seed policy.
- XGB: a conservative fixed specification — ``max_depth=4`` (below the
  library default of 6) limits overfitting on the rare (~5.5%) winner class,
  ``n_estimators=200`` restores capacity at the fixed ``learning_rate=0.1``;
  no subsampling (``subsample=1.0``, ``colsample_bytree=1.0``: deterministic
  full-data boosting), no ``scale_pos_weight`` manipulation (natural winner
  prevalence under frozen ``state_equal`` weighting), ``tree_method="hist"``
  for controlled local CPU use with no GPU dependency, ``eval_metric``
  recorded but NO eval set supplied (hence no early stopping), ``n_jobs=4``
  for controlled local CPU usage, ``random_state=42``.

Preprocessing: both candidates reuse the exact M3 train-fitted preprocessing
(``v2.model_lab.preprocessing``: median + StandardScaler numerics,
most-frequent booleans, MISSING-sentinel + train-vocabulary one-hot
categoricals, densified output). sklearn 1.8 HGB native categorical support
(``categorical_features="from_dtype"``) was inspected and deliberately NOT
used: a second encoding architecture would create scientifically
incomparable feature semantics for no estimator-required reason, since both
estimators accept the dense numeric matrix and scaling is harmless for
trees. Same 84 source features, same ~106-dim transformed representation,
train-fitted only, leakage-safe.

Both adapters emit ``PredictionKind.BINARY_PROBABILITY`` with
``ProbabilitySemantics.INDEPENDENT_BINARY`` (never normalized across
drivers). NO tuning, NO resampling, NO class rebalancing, NO threshold
tuning, NO calibration fitting.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from xgboost import XGBClassifier

from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab.errors import ExperimentConfigError, InvalidPredictionError
from raceintel.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

#: Canonical M4 model family names (used in experiment identity).
HGB_FAMILY = "hist_gradient_boosting"
XGB_FAMILY = "xgboost"

#: Short CLI aliases accepted by the M4 runner CLIs.
HGB_ALIASES = ("HGB", HGB_FAMILY)
XGB_ALIASES = ("XGB", "XGBOOST", XGB_FAMILY)

#: Task / feature / seed contract (identical to M3).
M4_TASK = "winner"
M4_FEATURE_SET = "ALL_84"
M4_SEED = 42

#: Fixed, untuned HGB specification (resolved values, no hidden defaults).
HGB_SPEC = {
    "estimator": "HistGradientBoostingClassifier",
    "loss": "log_loss",
    "learning_rate": 0.1,
    "max_iter": 100,
    "max_leaf_nodes": 31,
    "max_depth": None,
    "min_samples_leaf": 20,
    "l2_regularization": 0.0,
    "max_bins": 255,
    "early_stopping": False,
    "class_weight": None,
    "random_state": 42,
}

#: Fixed, untuned XGB specification (resolved values, no hidden defaults).
XGB_SPEC = {
    "estimator": "XGBClassifier",
    "objective": "binary:logistic",
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.1,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "colsample_bylevel": 1.0,
    "min_child_weight": 1,
    "reg_lambda": 1.0,
    "reg_alpha": 0.0,
    "gamma": 0,
    "tree_method": "hist",
    "eval_metric": "logloss",
    "scale_pos_weight": 1,
    "random_state": 42,
    "n_jobs": 4,
}

#: sklearn / xgboost runtimes recorded at fit time (stored in artifacts).
SKLEARN_VERSION = __import__("sklearn").__version__
XGBOOST_VERSION = __import__("xgboost").__version__


def hgb_model_parameters() -> dict:
    """Resolved HGB parameters for experiment identity (no hidden defaults)."""
    return dict(HGB_SPEC)


def xgb_model_parameters() -> dict:
    """Resolved XGB parameters for experiment identity (no hidden defaults)."""
    return dict(XGB_SPEC)


def build_hgb_estimator() -> HistGradientBoostingClassifier:
    """Construct one fresh untuned HistGradientBoosting estimator."""
    return HistGradientBoostingClassifier(
        loss=HGB_SPEC["loss"],
        learning_rate=HGB_SPEC["learning_rate"],
        max_iter=HGB_SPEC["max_iter"],
        max_leaf_nodes=HGB_SPEC["max_leaf_nodes"],
        max_depth=HGB_SPEC["max_depth"],
        min_samples_leaf=HGB_SPEC["min_samples_leaf"],
        l2_regularization=HGB_SPEC["l2_regularization"],
        max_bins=HGB_SPEC["max_bins"],
        early_stopping=HGB_SPEC["early_stopping"],
        random_state=HGB_SPEC["random_state"],
    )


def build_xgb_estimator() -> XGBClassifier:
    """Construct one fresh untuned XGBoost estimator."""
    return XGBClassifier(
        objective=XGB_SPEC["objective"],
        n_estimators=XGB_SPEC["n_estimators"],
        max_depth=XGB_SPEC["max_depth"],
        learning_rate=XGB_SPEC["learning_rate"],
        subsample=XGB_SPEC["subsample"],
        colsample_bytree=XGB_SPEC["colsample_bytree"],
        colsample_bylevel=XGB_SPEC["colsample_bylevel"],
        min_child_weight=XGB_SPEC["min_child_weight"],
        reg_lambda=XGB_SPEC["reg_lambda"],
        reg_alpha=XGB_SPEC["reg_alpha"],
        gamma=XGB_SPEC["gamma"],
        tree_method=XGB_SPEC["tree_method"],
        eval_metric=XGB_SPEC["eval_metric"],
        scale_pos_weight=XGB_SPEC["scale_pos_weight"],
        random_state=XGB_SPEC["random_state"],
        n_jobs=XGB_SPEC["n_jobs"],
    )


class _TreeAdapterBase:
    """Shared M1 ModelAdapter lifecycle for the M4 tree candidates.

    ``fit`` (TRAIN only) -> ``predict_positive_probability`` / ``predict`` /
    ``predict_result`` (validation, transform-only). One adapter instance is
    fitted exactly once per fold; no fitted object crosses folds.
    """

    family: str = "undefined"
    spec: dict = {}

    def __init__(self) -> None:
        self._preprocessor: PRE.FittedPreprocessor | None = None
        self._estimator = None
        self._positive_index: int | None = None
        self._feature_names: tuple | None = None
        self.fit_warnings: list = []
        self.timing: dict = {}

    @property
    def is_fitted(self) -> bool:
        return self._estimator is not None and self._preprocessor is not None

    def _build_estimator(self):  # noqa: ANN201
        raise NotImplementedError

    def fit(self, X, y):  # noqa: ANN001, ANN201
        """Fit preprocessing + estimator on TRAIN data only."""
        if self.is_fitted:
            raise ExperimentConfigError(
                "adapter is already fitted; use a fresh adapter per fold")
        from raceintel.model_lab.data import load_canonical

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
        estimator = self._build_estimator()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # TRAIN ONLY: no eval_set / validation labels are supplied.
            estimator.fit(matrix, target)
            for item in caught:
                message = str(item.message)
                self.fit_warnings.append(
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

    def predict_positive_probability(self, X) -> np.ndarray:  # noqa: ANN001
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

    def training_sanity(self) -> dict:
        """Minimal implementation-failure screen (not explainability)."""
        if not self.is_fitted:
            raise ExperimentConfigError("adapter must be fitted for sanity check")
        sanity = {
            "transformed_dim": int(self._preprocessor.output_dim),
            "classes": [int(c) for c in self._estimator.classes_],
            "fit_warnings": list(self.fit_warnings),
        }
        sanity.update(self._estimator_sanity())
        return sanity

    def _estimator_sanity(self) -> dict:  # noqa: ANN201
        raise NotImplementedError

    def metadata(self) -> dict:
        raise NotImplementedError


class HistGradientBoostingAdapter(_TreeAdapterBase):
    """Concrete M1 ModelAdapter for the M4 HGB candidate."""

    family = HGB_FAMILY
    spec = HGB_SPEC

    def _build_estimator(self):  # noqa: ANN201
        return build_hgb_estimator()

    def _estimator_sanity(self) -> dict:
        n_iter = int(getattr(self._estimator, "n_iter_", HGB_SPEC["max_iter"]))
        return {
            "n_iterations": n_iter,
            "max_iter_configured": int(HGB_SPEC["max_iter"]),
            "early_stopping": bool(HGB_SPEC["early_stopping"]),
            "feature_importances": None,
            "feature_importance_note": (
                "HistGradientBoostingClassifier exposes no "
                "feature_importances_; explainability is out of scope for M4"),
        }

    def metadata(self) -> dict:
        return {
            "family": self.family,
            "model_parameters": hgb_model_parameters(),
            "preprocessing": PRE.preprocessing_contract_dict(),
            "sklearn_version": SKLEARN_VERSION,
            "feature_set": M4_FEATURE_SET,
            "task": M4_TASK,
            "seed": M4_SEED,
            "positive_class": 1,
            "probability_semantics": ProbabilitySemantics.INDEPENDENT_BINARY.value,
        }


class XGBoostAdapter(_TreeAdapterBase):
    """Concrete M1 ModelAdapter for the M4 XGBoost candidate."""

    family = XGB_FAMILY
    spec = XGB_SPEC

    def _build_estimator(self):  # noqa: ANN201
        return build_xgb_estimator()

    def _estimator_sanity(self) -> dict:
        rounds = None
        try:
            rounds = int(self._estimator.get_booster().num_boosted_rounds())
        except (AttributeError, ValueError):
            rounds = None
        importances = None
        try:
            values = np.asarray(
                self._estimator.feature_importances_, dtype=float)
            if values.size and np.all(np.isfinite(values)):
                importances = {
                    "n_features": int(values.size),
                    "finite": True,
                    "nonzero": int(np.count_nonzero(values)),
                }
        except (AttributeError, ValueError):
            importances = None
        return {
            "n_estimators_configured": int(XGB_SPEC["n_estimators"]),
            "num_boosted_rounds": rounds,
            "tree_method": str(XGB_SPEC["tree_method"]),
            "eval_set_supplied": False,
            "feature_importances": importances,
            "feature_importance_note": (
                "raw gain importances recorded as a fit screen only; "
                "explainability is out of scope for M4"),
        }

    def metadata(self) -> dict:
        return {
            "family": self.family,
            "model_parameters": xgb_model_parameters(),
            "preprocessing": PRE.preprocessing_contract_dict(),
            "sklearn_version": SKLEARN_VERSION,
            "xgboost_version": XGBOOST_VERSION,
            "feature_set": M4_FEATURE_SET,
            "task": M4_TASK,
            "seed": M4_SEED,
            "positive_class": 1,
            "probability_semantics": ProbabilitySemantics.INDEPENDENT_BINARY.value,
        }


#: Family name -> adapter class (the only trainable M4 estimators).
ADAPTERS = {
    HGB_FAMILY: HistGradientBoostingAdapter,
    XGB_FAMILY: XGBoostAdapter,
}

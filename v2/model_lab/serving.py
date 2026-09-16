"""P3.1 production serving boundary for the frozen winner model.

Phase 4 must not refit the final model at API startup, import tuning /
evaluation runners, or touch protected-holdout machinery. This module is the
only production path to the frozen model:

- :func:`load_frozen_winner_model` loads one validated artifact and returns
  a :class:`FrozenWinnerPredictor`;
- :class:`FrozenWinnerPredictor` exposes batch ``predict_proba`` only.

Deliberately absent here: tuning, calibration selection, development folds,
holdout evaluation, experiment runners, M7/M8/M9 orchestration, model
comparison and protected target access. Artifact creation
(:func:`materialize_serving_artifact`) reuses the frozen M9 final-fit path
on 2018-2024 development rows only and never evaluates 2025; its heavy
imports stay function-local so merely loading this module (the API startup
path) never pulls in the evaluation stack.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from v2.config import V2Paths
from v2.model_lab import preprocessing as PRE
from v2.model_lab.errors import ServingArtifactError

#: Serving artifact envelope version (bump only for a format change).
SERVING_ARTIFACT_VERSION = "v1"

#: Tracked production artifact (committed; fresh clones must contain it).
SERVING_ARTIFACT_REL = (
    "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib"
)

#: Frozen anchors. Must match the M9 specification; creation cross-checks
#: them against the live frozen spec, loading enforces them strictly.
EXPECTED_FEATURE_COUNT = 84
EXPECTED_TRANSFORMED_DIM = 106
EXPECTED_ESTIMATOR_CLASS = "LogisticRegression"
EXPECTED_ESTIMATOR_PARAMS = {
    "C": 0.01,
    "solver": "lbfgs",
    "max_iter": 1000,
    "class_weight": None,
    "random_state": 42,
}
EXPECTED_TASK = "winner"
EXPECTED_FEATURE_SET = "ALL_84"
EXPECTED_TRAINING_SEASONS = tuple(range(2018, 2025))


def default_serving_artifact_path(root=None) -> Path:
    """Resolved path of the tracked production serving artifact."""
    base = Path(root) if root is not None else V2Paths.resolve().root
    return base / SERVING_ARTIFACT_REL


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FrozenWinnerPredictor:
    """Batch predictor for the frozen winner model.

    Emits independent per-driver binary probabilities
    (BINARY_PROBABILITY / INDEPENDENT_BINARY): values are never normalized
    across a race. Only constructible via :func:`load_frozen_winner_model`,
    which validates the artifact first.
    """

    def __init__(self, *, feature_names: tuple, preprocessor,
                 estimator, sklearn_version: str,
                 specification_fingerprint: str) -> None:
        self._feature_names = tuple(feature_names)
        self._preprocessor = preprocessor
        self._estimator = estimator
        self.sklearn_version = str(sklearn_version)
        self.specification_fingerprint = str(specification_fingerprint)

    @property
    def feature_names(self) -> tuple:
        """Ordered ALL_84 feature names (exactly 84)."""
        return self._feature_names

    @property
    def transformed_dim(self) -> int:
        """Frozen transformed width (106)."""
        return int(self._preprocessor.output_dim)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Batch P(is_winner=1) for an observable race field.

        ``frame`` must carry exactly the 84 ordered ALL_84 columns; row
        identity and order are preserved (output row ``i`` corresponds to
        input row ``i``). Single-row frames are accepted but Phase 4
        should predict the field as one batch.
        """
        if not isinstance(frame, pd.DataFrame):
            raise ServingArtifactError(
                "serving predictor requires a pandas DataFrame with the "
                "ordered ALL_84 feature columns")
        if tuple(frame.columns) != self._feature_names:
            raise ServingArtifactError(
                "predict frame columns do not match the frozen ordered "
                f"ALL_84 feature set: got {len(frame.columns)} columns, "
                f"expected {len(self._feature_names)} in frozen order")
        matrix = self._preprocessor.transform(frame)
        if not np.all(np.isfinite(matrix)):
            raise ServingArtifactError(
                "transformed serving matrix contains NaN/inf")
        proba = self._estimator.predict_proba(matrix)
        classes = list(self._estimator.classes_)
        if classes != [0, 1]:
            raise ServingArtifactError(
                f"serving estimator classes {classes} != [0, 1]")
        column = np.asarray(proba[:, 1], dtype=float)
        if not np.all(np.isfinite(column)):
            raise ServingArtifactError(
                "serving estimator returned NaN/inf probability")
        if np.any(column < 0.0) or np.any(column > 1.0):
            raise ServingArtifactError(
                "serving estimator probability outside [0, 1]")
        return column


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ServingArtifactError(message)


def load_frozen_winner_model(path=None) -> FrozenWinnerPredictor:
    """Load and validate the production serving artifact (no refit).

    Every structural and scientific anchor is enforced before the predictor
    is returned: envelope version, ordered feature count/names/hash,
    transformed dimension, estimator class and parameters, coefficient
    shape and preprocessing column agreement. Anything else is rejected
    with :class:`ServingArtifactError`; no fallback estimator is ever
    substituted silently.
    """
    dest = Path(path) if path is not None else default_serving_artifact_path()
    if not dest.exists():
        raise ServingArtifactError(
            f"frozen serving artifact missing at {dest}")
    try:
        payload = joblib.load(dest)
    except Exception as exc:  # noqa: BLE001 - re-raised with context
        raise ServingArtifactError(
            f"frozen serving artifact at {dest} is not loadable: {exc}"
        ) from exc
    _check(isinstance(payload, dict),
           f"serving artifact at {dest} must be a mapping")
    _check(payload.get("format") == "v2-serving-winner-logreg-raw",
           "serving artifact format mismatch")
    _check(payload.get("format_version") == SERVING_ARTIFACT_VERSION,
           "serving artifact version mismatch")
    _check(payload.get("task") == EXPECTED_TASK, "serving task mismatch")
    _check(payload.get("feature_set") == EXPECTED_FEATURE_SET,
           "serving feature-set mismatch")
    _check(payload.get("calibration_method") == "RAW",
           "serving calibration mismatch (must be RAW)")
    _check(payload.get("probability_semantics") == "INDEPENDENT_BINARY",
           "serving probability-semantics mismatch")

    feature_names = payload.get("feature_names_ordered")
    _check(isinstance(feature_names, list)
           and len(feature_names) == EXPECTED_FEATURE_COUNT
           and all(isinstance(name, str) for name in feature_names),
           "serving artifact must record exactly 84 ordered feature names")
    recorded_hash = payload.get("feature_names_hash")
    actual_hash = hashlib.sha256(
        "\n".join(feature_names).encode("utf-8")).hexdigest()
    _check(recorded_hash == actual_hash,
           "serving artifact feature hash does not match ordered names")

    _check(payload.get("transformed_dim") == EXPECTED_TRANSFORMED_DIM,
           "serving transformed dimension != 106")
    _check(payload.get("estimator_class") == EXPECTED_ESTIMATOR_CLASS,
           "serving estimator is not LogisticRegression")
    params = payload.get("estimator_params") or {}
    for key, expected in EXPECTED_ESTIMATOR_PARAMS.items():
        _check(params.get(key) == expected,
               f"serving estimator parameter {key}={params.get(key)!r} "
               f"!= frozen {expected!r}")
    _check(list(payload.get("training_seasons") or [])
           == list(EXPECTED_TRAINING_SEASONS),
           "serving training seasons != 2018-2024")

    preprocessor = payload.get("preprocessor")
    _check(isinstance(preprocessor, PRE.FittedPreprocessor),
           "serving preprocessor state has an unexpected type")
    _check(set(preprocessor.numeric_columns)
           | set(preprocessor.boolean_columns)
           | set(preprocessor.categorical_columns) == set(feature_names),
           "serving preprocessor columns disagree with ordered features")
    _check(int(preprocessor.output_dim) == EXPECTED_TRANSFORMED_DIM,
           "serving preprocessor output dimension != 106")

    estimator = payload.get("estimator")
    _check(isinstance(estimator, LogisticRegression),
           "serving estimator object is not a LogisticRegression")
    _check(float(getattr(estimator, "C", float("nan")))
           == EXPECTED_ESTIMATOR_PARAMS["C"],
           "serving estimator object C does not match the frozen spec")
    _check(getattr(estimator, "solver", None)
           == EXPECTED_ESTIMATOR_PARAMS["solver"],
           "serving estimator object solver does not match the frozen spec")
    _check(int(getattr(estimator, "max_iter", -1))
           == EXPECTED_ESTIMATOR_PARAMS["max_iter"],
           "serving estimator object max_iter does not match the frozen spec")
    _check(getattr(estimator, "class_weight", "sentinel") is None,
           "serving estimator object class_weight does not match the frozen "
           "spec")
    _check(int(getattr(estimator, "random_state", -1))
           == EXPECTED_ESTIMATOR_PARAMS["random_state"],
           "serving estimator object random_state does not match the frozen "
           "spec")
    coef = np.asarray(getattr(estimator, "coef_", None), dtype=float)
    intercept = np.asarray(getattr(estimator, "intercept_", None),
                           dtype=float)
    _check(coef.shape == (1, EXPECTED_TRANSFORMED_DIM),
           "serving coefficient shape mismatch")
    _check(intercept.shape == (1,),
           "serving intercept shape mismatch")
    _check(np.all(np.isfinite(coef)) and np.all(np.isfinite(intercept)),
           "serving coefficients contain NaN/inf")

    return FrozenWinnerPredictor(
        feature_names=tuple(feature_names),
        preprocessor=preprocessor,
        estimator=estimator,
        sklearn_version=str(payload.get("sklearn_version", "unknown")),
        specification_fingerprint=str(
            payload.get("specification_fingerprint", "")),
    )


def materialize_serving_artifact(canonical=None, *, paths=None, root=None,
                                 out=None, verify_hashes: bool = True) -> dict:
    """Deterministically materialize the frozen production artifact.

    This is NOT a new experiment: it fits the already-selected frozen
    pipeline (ALL_84 -> train-fitted preprocessing -> LogReg C=0.01 RAW)
    once on the FINAL_FIT 2018-2024 development rows. It never reads 2025
    targets, never evaluates the holdout and never compares models.
    """
    from v2.model_lab import data as DATA
    from v2.model_lab import final_fit as FF

    import sklearn

    if canonical is None:
        canonical = DATA.load_canonical(
            paths, verify_content_hash=True, verify_bytes=True)

    # Pre-materialization verification: frozen spec, C, RAW, ALL_84,
    # preprocessing contract, FINAL_FIT window, Phase-2 hashes, firewalls.
    # Touches no 2025 target.
    gate = FF.run_preunlock_gate(canonical, paths=paths, root=root,
                                 verify_hashes=verify_hashes)
    _check(gate.get("specification_fingerprint")
           == FF.specification_fingerprint(),
           "pre-materialization specification fingerprint drift")

    dataset, counts = FF.materialize_final_fit(canonical)
    fitted = FF.fit_final_model(canonical, dataset)
    model = fitted["model"]

    # Ground-truth feature order comes from the frozen F16 registry.
    expected_order = tuple(DATA.resolve_features("ALL_84", canonical))
    _check(tuple(model._feature_names) == expected_order,
           "final-fit feature order disagrees with the frozen ALL_84 order")
    _check(len(expected_order) == EXPECTED_FEATURE_COUNT,
           "ALL_84 feature count != 84")
    _check(int(model.preprocessor.output_dim) == EXPECTED_TRANSFORMED_DIM,
           "final-fit transformed dimension != 106")
    resolved = FF._estimator_parameters(model.estimator)
    _check(type(model.estimator).__name__ == EXPECTED_ESTIMATOR_CLASS,
           "final-fit estimator is not LogisticRegression")
    for key, expected in EXPECTED_ESTIMATOR_PARAMS.items():
        _check(resolved.get(key) == expected,
               f"final-fit estimator parameter {key} != frozen {expected!r}")

    feature_names = list(expected_order)
    payload = {
        "format": "v2-serving-winner-logreg-raw",
        "format_version": SERVING_ARTIFACT_VERSION,
        "task": EXPECTED_TASK,
        "target": "is_winner",
        "eligibility_mask": "eligible_is_winner",
        "feature_set": EXPECTED_FEATURE_SET,
        "feature_names_ordered": feature_names,
        "feature_names_hash": hashlib.sha256(
            "\n".join(feature_names).encode("utf-8")).hexdigest(),
        "transformed_dim": int(model.preprocessor.output_dim),
        "estimator_class": type(model.estimator).__name__,
        "estimator_params": {
            "C": float(model.estimator.C),
            "solver": model.estimator.solver,
            "max_iter": int(model.estimator.max_iter),
            "class_weight": model.estimator.class_weight,
            "random_state": model.estimator.random_state,
        },
        "preprocessing": PRE.preprocessing_contract_dict(),
        "calibration_method": "RAW",
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": "INDEPENDENT_BINARY",
        "weighting": "state_equal",
        "resampling": False,
        "training_seasons": list(EXPECTED_TRAINING_SEASONS),
        "training_counts": dict(counts),
        "seed": 42,
        "sklearn_version": sklearn.__version__,
        "specification": FF.frozen_specification(),
        "specification_fingerprint": FF.specification_fingerprint(),
        "preprocessor": model.preprocessor,
        "estimator": model.estimator,
    }

    dest = Path(out) if out is not None else default_serving_artifact_path(
        root if root is not None
        else (paths.root if paths is not None else None))
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, dest)
    record = {
        "path": str(dest),
        "sha256": _sha256_file(dest),
        "format": payload["format"],
        "format_version": payload["format_version"],
        "sklearn_version": payload["sklearn_version"],
        "feature_count": len(feature_names),
        "feature_names_hash": payload["feature_names_hash"],
        "transformed_dim": payload["transformed_dim"],
        "estimator_class": payload["estimator_class"],
        "estimator_params": payload["estimator_params"],
        "training_seasons": payload["training_seasons"],
        "training_counts": payload["training_counts"],
        "specification_fingerprint":
            payload["specification_fingerprint"],
        "phase2_matrix_content_hash":
            canonical.manifest.get("content_hash"),
        "pre_materialization_gate": {
            key: gate[key] for key in (
                "task", "feature_set", "final_fit_seasons",
                "holdout_season", "probability_kind",
                "probability_semantics", "calibration_method",
                "specification_fingerprint",
                "holdout_blocked_without_opt_in",
                "development_runner_rejects_holdout")},
    }
    return record


def describe_serving_artifact(path=None) -> dict:
    """Read recorded serving metadata without constructing a predictor."""
    dest = Path(path) if path is not None else default_serving_artifact_path()
    if not dest.exists():
        raise ServingArtifactError(
            f"frozen serving artifact missing at {dest}")
    payload = joblib.load(dest)
    if not isinstance(payload, dict):
        raise ServingArtifactError("serving artifact must be a mapping")
    record = {key: payload.get(key) for key in (
        "format", "format_version", "task", "target", "eligibility_mask",
        "feature_set", "feature_names_hash", "transformed_dim",
        "estimator_class", "estimator_params", "preprocessing",
        "calibration_method", "probability_kind", "probability_semantics",
        "weighting", "resampling", "training_seasons", "training_counts",
        "seed", "sklearn_version", "specification_fingerprint")}
    record["feature_count"] = len(payload.get("feature_names_ordered") or [])
    record["path"] = str(dest)
    record["sha256"] = _sha256_file(dest)
    record["specification"] = (
        json.loads(json.dumps(payload.get("specification"), sort_keys=True,
                               default=str)))
    return record

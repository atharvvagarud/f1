"""Typed experiment configuration, identity, result schema and interfaces.

M1 defines the contracts later stages execute. No estimator is constructed or
trained, and no result is fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ResultSchemaError,
)
from raceintel.model_lab.protocol import (
    EXPECTED_MATRIX_CONTENT_HASH,
    MODEL_LAB_PROTOCOL_VERSION,
    PHASE2_FREEZE_COMMIT,
    REQUIRED_ABLATION_CONFIG_VERSION,
    REQUIRED_FEATURE_SET_VERSION,
    REQUIRED_LABEL_SET_VERSION,
    REQUIRED_MATRIX_VERSION,
    ModelLabProtocolError,
    experiment_id as _protocol_experiment_id,
    validate_experiment_config as _validate_config,
)

CONFIG_SCHEMA_VERSION = "v1"
RESULT_SCHEMA_VERSION = "v1"

#: Project-level deterministic seed (M0 `PROJECT_SEED`).
PROJECT_SEED = 42


def set_project_seed(seed: int = PROJECT_SEED) -> int:
    """Seed supported RNGs (Python random + NumPy); records nothing magical.

    Bitwise reproducibility across every library/hardware is not claimed;
    this controls what the framework can actually control.
    """
    import random

    import numpy as np
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ExperimentConfigError(f"invalid seed {seed!r}")
    random.seed(seed)
    np.random.seed(seed)
    return seed


class ExperimentStatus(str, Enum):
    OK = "OK"
    FAILED = "FAILED"
    SMOKE_TEST = "SMOKE_TEST"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class ExperimentConfig:
    """Typed, validated experiment configuration (semantic identity source)."""

    task: str
    feature_set: str
    fold: str
    model_family: str
    seed: int
    git_commit: str = ""
    protocol_version: str = MODEL_LAB_PROTOCOL_VERSION
    phase2_freeze_commit: str = PHASE2_FREEZE_COMMIT
    feature_set_version: str = REQUIRED_FEATURE_SET_VERSION
    label_set_version: str = REQUIRED_LABEL_SET_VERSION
    matrix_version: str = REQUIRED_MATRIX_VERSION
    ablation_config_version: str = REQUIRED_ABLATION_CONFIG_VERSION
    matrix_content_hash: str = EXPECTED_MATRIX_CONTENT_HASH
    model_parameters: dict = field(default_factory=dict)
    preprocessing_config: dict = field(default_factory=dict)
    calibration_config: dict = field(default_factory=dict)
    training_rows: int = 0
    training_races: int = 0
    validation_rows: int = 0
    validation_races: int = 0
    split_policy: str = "expanding_window_race_chronology"
    holdout_accessed: bool = False
    holdout_purpose: str = ""
    schema_version: str = CONFIG_SCHEMA_VERSION

    def _identity_payload(self) -> dict:
        return {
            "protocol_version": self.protocol_version,
            "phase2_freeze_commit": self.phase2_freeze_commit,
            "feature_set_version": self.feature_set_version,
            "label_set_version": self.label_set_version,
            "matrix_version": self.matrix_version,
            "ablation_config_version": self.ablation_config_version,
            "matrix_content_hash": self.matrix_content_hash,
            "feature_set": self.feature_set,
            "task": self.task,
            "fold": self.fold,
            "model_family": self.model_family,
            "model_parameters": self.model_parameters,
            "preprocessing_config": self.preprocessing_config,
            "calibration_config": self.calibration_config,
            "seed": self.seed,
        }

    @property
    def experiment_id(self) -> str:
        return _protocol_experiment_id(self._identity_payload())

    def to_dict(self) -> dict:
        payload = dict(self.__dict__)
        payload["experiment_id"] = self.experiment_id
        return payload

    def validate(self) -> None:
        if self.protocol_version != MODEL_LAB_PROTOCOL_VERSION:
            raise ExperimentConfigError(
                f"protocol_version {self.protocol_version!r} != "
                f"{MODEL_LAB_PROTOCOL_VERSION!r}")
        if self.feature_set_version != REQUIRED_FEATURE_SET_VERSION:
            raise ExperimentConfigError("feature_set_version drift")
        if self.label_set_version != REQUIRED_LABEL_SET_VERSION:
            raise ExperimentConfigError("label_set_version drift")
        if self.matrix_version != REQUIRED_MATRIX_VERSION:
            raise ExperimentConfigError("matrix_version drift")
        if self.ablation_config_version != REQUIRED_ABLATION_CONFIG_VERSION:
            raise ExperimentConfigError("ablation_config_version drift")
        if self.matrix_content_hash != EXPECTED_MATRIX_CONTENT_HASH:
            raise ExperimentConfigError("matrix_content_hash drift")
        if self.phase2_freeze_commit != PHASE2_FREEZE_COMMIT:
            raise ExperimentConfigError("phase2_freeze_commit drift")
        try:
            _validate_config(self.to_dict())
        except ModelLabProtocolError as exc:
            raise ExperimentConfigError(str(exc)) from exc

    @classmethod
    def from_dict(cls, payload: dict) -> "ExperimentConfig":
        if payload.get("schema_version", CONFIG_SCHEMA_VERSION) != \
                CONFIG_SCHEMA_VERSION:
            raise ResultSchemaError(
                f"unknown config schema_version "
                f"{payload.get('schema_version')!r}")
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in payload.items() if k in known}
        config = cls(**data)
        config.validate()
        return config


def build_config(task: str, feature_set: str, fold: str, model_family: str,
                 *, seed: int, git_commit: str = "", **overrides
                 ) -> ExperimentConfig:
    config = ExperimentConfig(
        task=task, feature_set=feature_set, fold=fold,
        model_family=model_family, seed=seed, git_commit=git_commit,
        **overrides)
    config.validate()
    return config


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    status: ExperimentStatus
    fit_seconds: float | None = None
    prediction_seconds: float | None = None
    latency: dict | None = None
    metrics: dict = field(default_factory=dict)
    calibration: dict | None = None
    stage_metrics: dict | None = None
    race_metrics: dict | None = None
    artifact_refs: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    environment: dict | None = None
    error: str | None = None
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict:
        payload = dict(self.__dict__)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "ExperimentResult":
        if payload.get("schema_version", RESULT_SCHEMA_VERSION) != \
                RESULT_SCHEMA_VERSION:
            raise ResultSchemaError(
                f"unknown result schema_version "
                f"{payload.get('schema_version')!r}")
        data = dict(payload)
        data["status"] = ExperimentStatus(data["status"])
        data.pop("experiment_id", None)
        result = cls(experiment_id=payload["experiment_id"], **data)
        validate_result(result)
        return result


def validate_result(result: ExperimentResult) -> None:
    if not result.experiment_id:
        raise ResultSchemaError("result missing experiment_id")
    if not isinstance(result.status, ExperimentStatus):
        raise ResultSchemaError("result status must be an ExperimentStatus")
    if result.metrics is None:
        raise ResultSchemaError("result metrics must be a mapping (may be empty)")
    for name, value in (("fit_seconds", result.fit_seconds),
                        ("prediction_seconds", result.prediction_seconds)):
        if value is not None and value < 0:
            raise ResultSchemaError(f"{name} must be >= 0 or absent")


@dataclass(frozen=True)
class PreprocessingContract:
    """Declarative train-fitted preprocessing for a future model adapter.

    M1 stores the declaration only; fitting happens in later stages, always on
    training data alone.
    """

    numeric_imputation: str | None = None
    numeric_scaling: str | None = None
    categorical_imputation: str | None = None
    categorical_encoding: str | None = None
    native_missing: bool = False
    native_categorical: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "numeric_imputation": self.numeric_imputation,
            "numeric_scaling": self.numeric_scaling,
            "categorical_imputation": self.categorical_imputation,
            "categorical_encoding": self.categorical_encoding,
            "native_missing": self.native_missing,
            "native_categorical": self.native_categorical,
            "notes": self.notes,
            "fit_scope": "training only",
        }


@runtime_checkable
class ModelAdapter(Protocol):
    """Smallest useful future estimator interface (not implemented in M1)."""

    family: str

    def fit(self, X, y):  # pragma: no cover - contract only
        ...

    def predict(self, X):  # pragma: no cover - contract only
        ...

    def predict_positive_probability(self, X):  # pragma: no cover
        ...

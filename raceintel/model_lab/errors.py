"""Model-Lab M1 contract errors.

Small, intention-revealing hierarchy. Each error names the frozen contract
that was violated so a future contributor knows what not to bypass.
"""

from __future__ import annotations


class ModelLabError(RuntimeError):
    """Base class for Model-Lab framework contract failures."""


class ProtocolDriftError(ModelLabError):
    """Frozen M0 protocol / Phase-2 version or hash drift."""


class MatrixContractError(ModelLabError):
    """Canonical matrix schema/version/hash contract violated."""


class ProtectedHoldoutError(ModelLabError):
    """An ordinary development path tried to reach the 2025 holdout."""


class ProtectedHoldoutAlreadyConsumed(ProtectedHoldoutError):
    """The sanctioned M9 holdout evaluation was already consumed.

    The canonical protected artifact exists, so any further protected
    evaluation is refused before target materialization. The artifact
    itself is the durable consumed marker.
    """


class UnknownTaskError(ModelLabError):
    """Task is not a frozen Model-Lab task (DNF is intentionally absent)."""


class UnknownFeatureSetError(ModelLabError):
    """Feature set is not a frozen F16 configuration."""


class UnknownFoldError(ModelLabError):
    """Fold id is not a frozen development/FINAL_FIT/holdout split."""


class UnknownBaselineError(ModelLabError):
    """Baseline is not a frozen M0 prediction baseline."""


class ExperimentConfigError(ModelLabError):
    """Experiment configuration missing/contradicts the frozen protocol."""


class InvalidPredictionError(ModelLabError):
    """Prediction values violate the declared output semantics."""


class PredictionAlignmentError(ModelLabError):
    """Predictions cannot be aligned to canonical state identities."""


class UnsupportedMetricError(ModelLabError):
    """Metric is unknown or not valid for the prediction/task kind."""


class ResultSchemaError(ModelLabError):
    """Result/config document violates the frozen schema version."""


class ServingArtifactError(ModelLabError):
    """Production serving artifact missing, corrupt or mismatched."""

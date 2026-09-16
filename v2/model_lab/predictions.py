"""Typed prediction results + identity alignment.

Predictions carry their semantics explicitly. Independent per-driver binary
probabilities are never silently treated as a mutually-exclusive race
distribution, and every prediction is aligned to canonical ``state_id``
identities rather than dataframe position.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from v2.model_lab.errors import (
    InvalidPredictionError,
    PredictionAlignmentError,
)


class PredictionKind(str, Enum):
    BINARY_PROBABILITY = "BINARY_PROBABILITY"
    CONTINUOUS_PREDICTION = "CONTINUOUS_PREDICTION"
    ORDINAL_PREDICTION = "ORDINAL_PREDICTION"
    RANKING_SCORE = "RANKING_SCORE"
    MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION = (
        "MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION")


class ProbabilitySemantics(str, Enum):
    POSITIVE_CLASS_PROBABILITY = "POSITIVE_CLASS_PROBABILITY"
    INDEPENDENT_BINARY = "INDEPENDENT_BINARY"
    MUTUALLY_EXCLUSIVE_RACE = "MUTUALLY_EXCLUSIVE_RACE"


_BINARY_SEMANTICS = (
    ProbabilitySemantics.POSITIVE_CLASS_PROBABILITY,
    ProbabilitySemantics.INDEPENDENT_BINARY,
)


@dataclass(frozen=True)
class PredictionResult:
    kind: PredictionKind
    state_ids: tuple
    values: np.ndarray
    semantics: ProbabilitySemantics | None = None
    positive_class: int | None = None
    race_ids: tuple | None = None

    def __post_init__(self) -> None:
        ids = tuple(self.state_ids)
        values = np.asarray(self.values, dtype=float)
        if values.ndim != 1:
            raise InvalidPredictionError("prediction values must be 1-D")
        if len(ids) != len(values):
            raise InvalidPredictionError(
                f"{len(ids)} state ids vs {len(values)} values")
        if len(set(ids)) != len(ids):
            raise InvalidPredictionError("duplicate state ids in prediction")

        if self.kind is PredictionKind.BINARY_PROBABILITY:
            if self.semantics not in _BINARY_SEMANTICS:
                raise InvalidPredictionError(
                    "binary predictions require POSITIVE_CLASS_PROBABILITY or "
                    "INDEPENDENT_BINARY semantics")
            if self.positive_class is None:
                object.__setattr__(self, "positive_class", 1)
            _validate_probabilities(values)
        elif self.kind is (
                PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION):
            if self.semantics is not (
                    ProbabilitySemantics.MUTUALLY_EXCLUSIVE_RACE):
                raise InvalidPredictionError(
                    "race distribution requires MUTUALLY_EXCLUSIVE_RACE "
                    "semantics")
            if self.race_ids is None:
                raise InvalidPredictionError(
                    "race distribution requires race_ids")
            if len(self.race_ids) != len(ids):
                raise InvalidPredictionError(
                    "race_ids length must match state ids")
            _validate_probabilities(values)
        else:
            if self.semantics is not None:
                raise InvalidPredictionError(
                    f"{self.kind.value} must not declare probability "
                    "semantics")
            if np.any(np.isinf(values)):
                raise InvalidPredictionError(
                    "non-probability predictions must not be infinite "
                    "(NaN denotes a legitimate missing prediction)")

    @property
    def is_probability(self) -> bool:
        return self.kind in (
            PredictionKind.BINARY_PROBABILITY,
            PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION)

    def to_frame(self) -> pd.DataFrame:
        data = {"state_id": list(self.state_ids),
                "prediction": np.asarray(self.values, dtype=float)}
        if self.race_ids is not None:
            data["race_id"] = list(self.race_ids)
        return pd.DataFrame(data)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, *,
                   kind: PredictionKind,
                   value_column: str = "prediction",
                   semantics: ProbabilitySemantics | None = None,
                   positive_class: int | None = 1,
                   id_column: str = "state_id",
                   race_column: str | None = None) -> "PredictionResult":
        if id_column not in frame.columns or value_column not in frame.columns:
            raise InvalidPredictionError(
                f"frame needs {id_column!r} and {value_column!r}")
        race_ids = tuple(frame[race_column]) if race_column else None
        return cls(kind=kind, state_ids=tuple(frame[id_column]),
                   values=np.asarray(frame[value_column], dtype=float),
                   semantics=semantics, positive_class=positive_class,
                   race_ids=race_ids)


def _validate_probabilities(values: np.ndarray) -> None:
    if not np.all(np.isfinite(values)):
        raise InvalidPredictionError("probability contains NaN/inf")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise InvalidPredictionError("probability outside [0, 1]")


def require_race_distribution(prediction: PredictionResult) -> None:
    """Reject independent binary output where a race distribution is required."""
    if prediction.kind is not (
            PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION):
        raise InvalidPredictionError(
            "this evaluation requires a MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION; "
            f"got {prediction.kind.value}"
            + (" (independent per-driver probabilities do not sum to 1)"
               if prediction.semantics is (
                   ProbabilitySemantics.INDEPENDENT_BINARY) else ""))


def align(prediction: PredictionResult,
          expected_state_ids) -> np.ndarray:
    """Reorder prediction values to ``expected_state_ids`` (identity-based).

    Fails on duplicate, missing or extra ids — never positionally guesses.
    """
    expected = list(expected_state_ids)
    if len(set(expected)) != len(expected):
        raise PredictionAlignmentError("expected state ids are not unique")
    index = {sid: i for i, sid in enumerate(expected)}
    out = np.full(len(expected), np.nan, dtype=float)
    seen = set()
    for sid, value in zip(prediction.state_ids, prediction.values):
        if sid not in index:
            raise PredictionAlignmentError(
                f"prediction contains extra state id {sid!r}")
        if sid in seen:
            raise PredictionAlignmentError(
                f"prediction contains duplicate state id {sid!r}")
        seen.add(sid)
        out[index[sid]] = float(value)
    if len(seen) != len(expected):
        missing = [sid for sid in expected if sid not in seen]
        raise PredictionAlignmentError(
            f"prediction missing {len(missing)} state ids; "
            f"first: {missing[:3]}")
    return out

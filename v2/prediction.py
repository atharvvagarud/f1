"""Phase-4 R4 frozen batch prediction engine.

``RaceState -> RaceStateFeatureBridge -> FeatureBatch ->
FrozenWinnerPredictor -> PredictionSnapshot``. ONE batch model call per
snapshot; unobservable roster members map to null + reason, never zero.

Probability semantics: each ``winner_probability`` is ``P(is_winner=1 |
state)`` from an independent binary model (``INDEPENDENT_BINARY``). The
values are never normalized, never summed to 1, never described as a
categorical race distribution.

This module may import ONLY the narrow production serving interface
(``v2.model_lab.serving``) from Model Lab, plus the R1 domain and the R3
bridge. No refit, no hyperparameter search, no post-hoc adjustment, no
quality evaluation, and no protected-season access exists here (pinned
by test).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from v2 import race_state as RS
from v2.model_lab import serving as SERVING

#: Canonical probability semantics for every snapshot (artifact-enforced).
PROBABILITY_SEMANTICS = "INDEPENDENT_BINARY"

#: Single factual unavailable reason. Zero-state entrants and
#: pre-first-observation members are intentionally indistinguishable
#: from one RaceState snapshot (R1/R2), so no finer split is invented.
NO_OBSERVATION_AT_SNAPSHOT = "NO_OBSERVATION_AT_SNAPSHOT"

#: Human-readable warning shipped in every snapshot payload.
PROBABILITY_SEMANTICS_NOTE = (
    "Independent per-driver binary probabilities "
    "P(driver wins | driver's observable state). They do not sum to 1 "
    "and are not a race-winner distribution. Do not renormalize."
)

#: Frozen feature-set version (matches ``FEATURE_SET_VERSION == "v8"``).
FEATURE_SET_VERSION = "v8"


class PredictionEngineError(RS.RaceStateError):
    """Base prediction-engine error (no HTTP, no sklearn leakage)."""


class PredictionFeatureMismatchError(PredictionEngineError):
    """FeatureBatch columns do not exactly match predictor order."""

    def __init__(self, detail: str):
        super().__init__(f"prediction feature-order mismatch: {detail}")
        self.detail = detail


class PredictionAlignmentError(PredictionEngineError):
    """Model output rows cannot be aligned onto the RaceState roster."""

    def __init__(self, detail: str):
        super().__init__(f"prediction identity-alignment failure: {detail}")
        self.detail = detail


class PredictionOutputError(PredictionEngineError):
    """Model output is not a valid [0, 1] finite probability vector."""

    def __init__(self, detail: str):
        super().__init__(f"invalid prediction output: {detail}")
        self.detail = detail


class ProductionModelUnavailableError(PredictionEngineError):
    """Serving artifact missing/invalid (wraps the serving cause)."""


def _req_probability(value: object, driver_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PredictionOutputError(
            f"driver {driver_id!r} probability must be a plain number, "
            f"got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise PredictionOutputError(
            f"driver {driver_id!r} probability is not finite: {value!r}")
    if result < 0.0 or result > 1.0:
        raise PredictionOutputError(
            f"driver {driver_id!r} probability {result!r} outside [0, 1]")
    return result


@dataclass(frozen=True)
class ModelIdentity:
    """Factual production metadata identifying what generated a snapshot."""

    task: str
    target: str
    eligibility_mask: str
    feature_set: str
    feature_set_version: str
    estimator: str
    estimator_params: tuple
    calibration_method: str
    probability_semantics: str
    training_seasons: tuple
    transformed_dim: int
    feature_count: int
    artifact_sha256: str
    specification_fingerprint: str
    sklearn_version: str

    def __post_init__(self) -> None:
        for name in ("task", "target", "eligibility_mask", "feature_set",
                     "feature_set_version", "estimator", "calibration_method",
                     "probability_semantics", "artifact_sha256",
                     "specification_fingerprint", "sklearn_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise PredictionEngineError(
                    f"ModelIdentity.{name} must be a non-empty string, "
                    f"got {value!r}")
        if self.probability_semantics != PROBABILITY_SEMANTICS:
            raise PredictionEngineError(
                "ModelIdentity.probability_semantics must be "
                f"{PROBABILITY_SEMANTICS!r}, got "
                f"{self.probability_semantics!r}")
        object.__setattr__(self, "estimator_params",
                            tuple(self.estimator_params))
        object.__setattr__(self, "training_seasons",
                            tuple(self.training_seasons))
        for name in ("transformed_dim", "feature_count"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise PredictionEngineError(
                    f"ModelIdentity.{name} must be a positive int, "
                    f"got {value!r}")

    @classmethod
    def from_production_predictor(cls, predictor,
                                  artifact_sha256: str | None = None,
                                  artifact_path=None) -> "ModelIdentity":
        """Build identity from a loaded predictor + recorded metadata.

        Scientific anchors come from the frozen serving constants (no
        hardcoded copies); the artifact SHA comes from
        ``describe_serving_artifact`` when available.
        """
        sha = artifact_sha256
        if sha is None:
            try:
                record = SERVING.describe_serving_artifact(artifact_path)
            except Exception:  # noqa: BLE001 - metadata fallback only
                record = {}
            sha = record.get("sha256") or "unavailable"
        params = dict(SERVING.EXPECTED_ESTIMATOR_PARAMS)
        return cls(
            task=SERVING.EXPECTED_TASK,
            target="is_winner",
            eligibility_mask="eligible_is_winner",
            feature_set=SERVING.EXPECTED_FEATURE_SET,
            feature_set_version=FEATURE_SET_VERSION,
            estimator=SERVING.EXPECTED_ESTIMATOR_CLASS,
            estimator_params=tuple(sorted(
                (key, params[key]) for key in params)),
            calibration_method="RAW",
            probability_semantics=PROBABILITY_SEMANTICS,
            training_seasons=tuple(SERVING.EXPECTED_TRAINING_SEASONS),
            transformed_dim=int(predictor.transformed_dim),
            feature_count=int(len(predictor.feature_names)),
            artifact_sha256=str(sha),
            specification_fingerprint=str(
                predictor.specification_fingerprint),
            sklearn_version=str(predictor.sklearn_version),
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "target": self.target,
            "eligibility_mask": self.eligibility_mask,
            "feature_set": self.feature_set,
            "feature_set_version": self.feature_set_version,
            "estimator": self.estimator,
            "estimator_params": [
                [key, value] for key, value in self.estimator_params],
            "calibration_method": self.calibration_method,
            "probability_semantics": self.probability_semantics,
            "training_seasons": list(self.training_seasons),
            "transformed_dim": self.transformed_dim,
            "feature_count": self.feature_count,
            "artifact_sha256": self.artifact_sha256,
            "specification_fingerprint": self.specification_fingerprint,
            "sklearn_version": self.sklearn_version,
        }


@dataclass(frozen=True)
class DriverPrediction:
    """One roster member's prediction (no ALL_84, no labels)."""

    driver_id: str
    observable: bool
    observed_lap_number: int | None = None
    observed_time_s: float | None = None
    observation_age_s: float | None = None
    observed_position: int | None = None
    winner_probability: float | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.driver_id, str) or not self.driver_id.strip():
            raise PredictionEngineError(
                f"driver_id must be a non-empty string, "
                f"got {self.driver_id!r}")
        if not isinstance(self.observable, bool):
            raise PredictionEngineError(
                f"observable must be a bool, got {self.observable!r}")
        if self.observable:
            if self.unavailable_reason is not None:
                raise PredictionEngineError(
                    f"observable driver {self.driver_id!r} must carry no "
                    f"unavailable reason")
            object.__setattr__(self, "winner_probability", _req_probability(
                self.winner_probability, self.driver_id))
        else:
            if self.winner_probability is not None:
                raise PredictionEngineError(
                    f"unobservable driver {self.driver_id!r} must carry "
                    f"probability None, never 0.0 or a value")
            if not isinstance(self.unavailable_reason, str) \
                    or not self.unavailable_reason.strip():
                raise PredictionEngineError(
                    f"unobservable driver {self.driver_id!r} requires an "
                    f"explicit unavailable reason")

    def to_dict(self) -> dict:
        return {
            "driver_id": self.driver_id,
            "observable": self.observable,
            "observed_lap_number": self.observed_lap_number,
            "observed_time_s": self.observed_time_s,
            "observation_age_s": self.observation_age_s,
            "observed_position": self.observed_position,
            "winner_probability": self.winner_probability,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class PredictionSnapshot:
    """Exactly one synchronized RaceState prediction result."""

    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    state_time_s: float
    model: ModelIdentity
    predictions: tuple = field(default_factory=tuple)
    probability_semantics: str = PROBABILITY_SEMANTICS
    probability_semantics_note: str = PROBABILITY_SEMANTICS_NOTE
    feature_set: str = SERVING.EXPECTED_FEATURE_SET

    def __post_init__(self) -> None:
        if not isinstance(self.race_id, str) or not self.race_id.strip():
            raise PredictionEngineError("race_id must be non-empty")
        if not isinstance(self.model, ModelIdentity):
            raise PredictionEngineError(
                "model must be a ModelIdentity descriptor")
        if self.probability_semantics != PROBABILITY_SEMANTICS:
            raise PredictionEngineError(
                "snapshot probability semantics must stay "
                f"{PROBABILITY_SEMANTICS!r}")
        entries = list(self.predictions)
        if not entries:
            raise PredictionEngineError(
                "snapshot requires at least one driver prediction")
        for entry in entries:
            if not isinstance(entry, DriverPrediction):
                raise PredictionEngineError(
                    f"predictions must hold DriverPrediction, got {entry!r}")
        ids = [entry.driver_id for entry in entries]
        if len(set(ids)) != len(ids):
            raise PredictionEngineError(
                f"duplicate driver predictions: "
                f"{sorted({i for i in ids if ids.count(i) > 1})}")
        ordered = sorted(entries, key=lambda entry: entry.driver_id)
        object.__setattr__(self, "predictions", tuple(ordered))

    @property
    def roster_size(self) -> int:
        return len(self.predictions)

    @property
    def observable_count(self) -> int:
        return sum(1 for entry in self.predictions if entry.observable)

    @property
    def unavailable_count(self) -> int:
        return sum(1 for entry in self.predictions if not entry.observable)

    def probability_by_driver(self) -> dict:
        """Observable driver_id -> probability (None entries excluded)."""
        return {entry.driver_id: entry.winner_probability
                for entry in self.predictions if entry.observable}

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "state_time_s": self.state_time_s,
            "roster_size": self.roster_size,
            "observable_count": self.observable_count,
            "unavailable_count": self.unavailable_count,
            "probability_semantics": self.probability_semantics,
            "probability_semantics_note": self.probability_semantics_note,
            "feature_set": self.feature_set,
            "model": self.model.to_dict(),
            "predictions": [entry.to_dict() for entry in self.predictions],
        }


class RacePredictionEngine:
    """Reusable frozen batch prediction engine (one batch call/snapshot)."""

    def __init__(self, feature_bridge, predictor, model_identity=None):
        for name, value in (("feature_bridge", feature_bridge),
                            ("predictor", predictor)):
            if value is None:
                raise PredictionEngineError(f"{name} is required")
        if not callable(getattr(feature_bridge, "features_for_state", None)):
            raise PredictionEngineError(
                "feature_bridge must expose features_for_state()")
        if not callable(getattr(predictor, "predict_proba", None)):
            raise PredictionEngineError(
                "predictor must expose predict_proba()")
        if not isinstance(tuple(getattr(
                predictor, "feature_names", ())), tuple) \
                or not predictor.feature_names:
            raise PredictionEngineError(
                "predictor must expose ordered feature_names")
        identity = model_identity
        if identity is None:
            identity = ModelIdentity.from_production_predictor(predictor)
        if not isinstance(identity, ModelIdentity):
            raise PredictionEngineError(
                "model_identity must be a ModelIdentity descriptor")
        self._bridge = feature_bridge
        self._predictor = predictor
        self._identity = identity

    @property
    def model_identity(self) -> ModelIdentity:
        return self._identity

    def predict(self, race_state: RS.RaceState) -> PredictionSnapshot:
        """One RaceState -> one batch model call -> PredictionSnapshot."""
        if not isinstance(race_state, RS.RaceState):
            raise PredictionEngineError(
                f"race_state must be a RaceState, got {race_state!r}")
        batch = self._bridge.features_for_state(race_state)
        expected = tuple(self._predictor.feature_names)
        if tuple(batch.feature_names) != expected:
            raise PredictionFeatureMismatchError(
                f"FeatureBatch carries {len(batch.feature_names)} names, "
                f"predictor expects {len(expected)} in frozen order")
        try:
            probabilities = self._predictor.predict_proba(batch.features)
        except PredictionEngineError:
            raise
        except Exception as exc:
            raise ProductionModelUnavailableError(
                f"frozen predictor failed: {exc}") from exc
        return self._assemble(race_state, batch, probabilities)

    def _assemble(self, race_state, batch, probabilities) -> PredictionSnapshot:
        try:
            count = len(probabilities)
        except TypeError:
            raise PredictionOutputError(
                "predictor output has no length") from None
        if count != len(batch.identities):
            raise PredictionAlignmentError(
                f"predictor returned {count} probabilities for "
                f"{len(batch.identities)} feature rows")
        by_id = {entry.driver_id: entry for entry in race_state.drivers}
        seen: set[str] = set()
        scored: dict[str, float] = {}
        for identity, raw in zip(batch.identities, list(probabilities)):
            driver_id = identity.driver_id
            if driver_id in seen:
                raise PredictionAlignmentError(
                    f"duplicate feature identity: {driver_id!r}")
            seen.add(driver_id)
            member = by_id.get(driver_id)
            if member is None:
                raise PredictionAlignmentError(
                    f"feature row for unknown roster driver {driver_id!r}")
            if not member.observable:
                raise PredictionAlignmentError(
                    f"unobservable driver {driver_id!r} has a feature row")
            scored[driver_id] = _req_probability(raw, driver_id)
        missing = [driver_id for driver_id in race_state.observable_driver_ids
                   if driver_id not in scored]
        if missing:
            raise PredictionAlignmentError(
                f"observable drivers missing feature rows: {missing}")
        entries = []
        for member in race_state.drivers:
            if member.observable:
                entries.append(DriverPrediction(
                    driver_id=member.driver_id, observable=True,
                    observed_lap_number=member.observed_lap_number,
                    observed_time_s=member.observed_time_s,
                    observation_age_s=member.observation_age_s,
                    observed_position=member.position,
                    winner_probability=scored[member.driver_id],
                    unavailable_reason=None))
            else:
                entries.append(DriverPrediction(
                    driver_id=member.driver_id, observable=False,
                    unavailable_reason=NO_OBSERVATION_AT_SNAPSHOT))
        return PredictionSnapshot(
            race_id=race_state.race_id,
            anchor_driver_id=race_state.anchor_driver_id,
            anchor_lap_number=race_state.anchor_lap_number,
            state_time_s=race_state.state_time_s,
            model=self._identity,
            predictions=tuple(entries))


def load_production_prediction_engine(states, history, *,
                                      artifact_path=None,
                                      registry=None) -> RacePredictionEngine:
    """Convenient production constructor (bridge + frozen artifact).

    Data loading stays outside: callers pass the canonical D9 frame (or
    per-race slice) and a frozen ``PriorHistory`` bundle.
    """
    from v2.race_state_features import RaceStateFeatureBridge

    try:
        predictor = SERVING.load_frozen_winner_model(artifact_path)
    except Exception as exc:
        raise ProductionModelUnavailableError(
            f"production serving artifact unavailable: {exc}") from exc
    bridge = RaceStateFeatureBridge(states, history, registry=registry)
    identity = ModelIdentity.from_production_predictor(
        predictor, artifact_path=artifact_path)
    return RacePredictionEngine(bridge, predictor, identity)

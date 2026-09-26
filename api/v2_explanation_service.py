"""V2 local-explanation application service (Phase-8 E4).

Read-only facade that resolves ONE replay checkpoint + observable driver to
an EXACT local explanation of the frozen winner LogisticRegression score:

    replay service (cached checkpoint + exact RaceState)
      -> exact Phase-2 matrix identity lookup (race_id, driver_id,
         lap_number=observed_lap_number, state_time_s=observed_time_s)
      -> v2.local_explainability.explain_winner_prediction (frozen model)

The E2 prediction cache is required (three-way consistency): a missing /
stale / incomplete cache raises ``PredictionUnavailableError`` and is never
generated here. The cache itself is never rewritten or embedded.

No explanation mathematics lives here and none lives in the route handler;
this module only orchestrates frozen, read-only components. It is a
separate module from the hermetic R4 replay service so the R4 import
firewall stays intact.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    V2ReplayService,
    get_v2_replay_service,
)
from v2 import explainability as E3
from v2.local_explainability import (
    LOCAL_EXPLANATION_CONTRACT_VERSION,
    LocalExplanationIdentity,
    explain_winner_prediction,
    public_explanation,
)
from v2.race_state_reconstruction import RaceNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]


class UnknownDriverError(ValueError):
    """Requested driver is not a member of the checkpoint roster."""

    def __init__(self, race_id: str, frame_index: int, driver_id: str):
        super().__init__(
            f"driver {driver_id!r} is not in race {race_id!r} frame "
            f"{frame_index}")
        self.race_id = race_id
        self.frame_index = frame_index
        self.driver_id = driver_id


class DriverNotObservableError(ValueError):
    """Driver is on the roster but carries no observation at the snapshot."""

    def __init__(self, race_id: str, frame_index: int, driver_id: str,
                 reason: str = "NO_OBSERVATION_AT_SNAPSHOT"):
        super().__init__(
            f"driver {driver_id!r} has no observable state at race "
            f"{race_id!r} frame {frame_index} ({reason})")
        self.race_id = race_id
        self.frame_index = frame_index
        self.driver_id = driver_id
        self.reason = reason


class ExplanationFeatureUnavailableError(RuntimeError):
    """The exact frozen Phase-2 feature row could not be resolved (closed)."""


class V2ExplanationService:
    """Exact local explanation over a replay service + frozen model/matrix."""

    def __init__(self, replay_service: V2ReplayService, predictor, matrix,
                 *, map_entries=None, top_n: int = 5):
        if not isinstance(replay_service, V2ReplayService):
            raise ValueError(
                "replay_service must be a V2ReplayService, got "
                f"{type(replay_service)}")
        if predictor is None or matrix is None:
            raise ValueError("predictor and matrix are required")
        if tuple(predictor.feature_names) != tuple(matrix.feature_names):
            raise ValueError(
                "predictor ALL_84 order disagrees with the frozen matrix order")
        self._replay = replay_service
        self._predictor = predictor
        self._matrix = matrix
        self._map_entries = (
            map_entries if map_entries is not None
            else E3.build_transformed_feature_map(predictor))
        self._top_n = int(top_n)
        self._race_frames: dict = {}

    def get_explanation(self, race_id: str, frame_index: int,
                        driver_id: str) -> dict:
        """Checkpoint + driver -> compact local explanation (or fail closed)."""
        public = public_explanation(
            self.get_domain_explanation(race_id, frame_index, driver_id))
        public["cache_status"] = "HIT"
        return public

    def get_domain_explanation(self, race_id: str, frame_index: int,
                               driver_id: str) -> dict:
        """Checkpoint + driver -> full domain explanation (internal evidence).

        This is the E5-facing view: it retains the complete 84 canonical
        contribution rows so an A -> B change can be decomposed exactly. The
        public wire projection strips them.

        The exact driver observation identity comes from the cached frozen
        snapshot itself (stored verbatim at checkpoint generation), so no
        state is re-derived here and the E2 cache is the three-way anchor.
        """
        # Three-way consistency requires the cached prediction to exist.
        cached_result = self._replay.get_prediction(race_id, frame_index)
        checkpoint = cached_result["checkpoint"]
        snapshot = cached_result["prediction"]

        entry = next((e for e in snapshot["predictions"]
                      if e["driver_id"] == driver_id), None)
        if entry is None:
            raise UnknownDriverError(race_id, frame_index, driver_id)
        if not entry["observable"] or entry["winner_probability"] is None:
            raise DriverNotObservableError(race_id, frame_index, driver_id)
        cached_probability = float(entry["winner_probability"])
        observed_lap_number = entry["observed_lap_number"]
        observed_time_s = entry["observed_time_s"]
        if observed_lap_number is None or observed_time_s is None:
            raise ExplanationFeatureUnavailableError(
                "observable cached entry is missing its feature identity")

        canonical_row = self._resolve_exact_row(
            race_id, driver_id, int(observed_lap_number),
            float(observed_time_s))
        identity = LocalExplanationIdentity(
            race_id=race_id,
            frame_index=int(frame_index),
            driver_id=driver_id,
            observed_lap_number=int(observed_lap_number),
            observed_time_s=float(observed_time_s),
            state_time_s=float(snapshot["state_time_s"]),
            anchor_driver_id=str(snapshot["anchor_driver_id"]),
            anchor_lap_number=int(snapshot["anchor_lap_number"]),
            anchor_state_time_s=float(snapshot["state_time_s"]),
            checkpoint_reasons=tuple(checkpoint["reasons"]),
            leader_lap=checkpoint["leader_lap"],
            observed_position=entry["observed_position"],
            observation_age_s=entry["observation_age_s"])

        return explain_winner_prediction(
            self._predictor, canonical_row, identity,
            cached_probability=cached_probability,
            map_entries=self._map_entries, top_n=self._top_n)

    def _resolve_exact_row(self, race_id: str, driver_id: str,
                           observed_lap_number: int,
                           observed_time_s: float) -> pd.DataFrame:
        """Exact Phase-2 matrix row for one observation (no tolerance)."""
        from scripts.replay_feature_matrix import (
            IDENTITY_COLUMNS,
            MatrixBackendError,
        )

        requests = pd.DataFrame(
            [[race_id, driver_id, int(observed_lap_number),
              float(observed_time_s)]],
            columns=list(IDENTITY_COLUMNS))
        try:
            race_frame = self._race_slice(race_id)
            joined = self._matrix.lookup(requests, race_frame)
        except MatrixBackendError as exc:
            raise ExplanationFeatureUnavailableError(
                f"exact frozen feature row unavailable for "
                f"{driver_id!r}: {exc}") from None
        row = joined.iloc[[0]][list(self._predictor.feature_names)].copy()
        if tuple(row.columns) != tuple(self._predictor.feature_names):
            raise ExplanationFeatureUnavailableError(
                "resolved feature row order drifted from frozen ALL_84")
        return row

    def _race_slice(self, race_id: str) -> pd.DataFrame:
        cached = self._race_frames.get(race_id)
        if cached is None:
            cached = self._matrix.race_slice(race_id)
            self._race_frames[race_id] = cached
        return cached


def build_v2_explanation_service(replay_service=None, predictor=None,
                                 matrix=None, *, root=None,
                                 map_entries=None) -> V2ExplanationService:
    """Construct the service, loading frozen components only when omitted."""
    if replay_service is None:
        replay_service = get_v2_replay_service()
    if predictor is None:
        predictor = E3.load_frozen_explanation_model()
    if matrix is None:
        from scripts.replay_feature_matrix import FrozenReplayFeatureMatrix
        matrix = FrozenReplayFeatureMatrix.load(
            str(root if root is not None else _REPO_ROOT))
    return V2ExplanationService(
        replay_service, predictor, matrix, map_entries=map_entries)


@functools.lru_cache(maxsize=1)
def _cached_explanation_service() -> V2ExplanationService:
    return build_v2_explanation_service()


def get_v2_explanation_service() -> V2ExplanationService:
    """FastAPI dependency: lazy process-local singleton (override in tests)."""
    return _cached_explanation_service()


__all__ = [
    "DriverNotObservableError",
    "ExplanationFeatureUnavailableError",
    "UnknownDriverError",
    "V2ExplanationService",
    "LOCAL_EXPLANATION_CONTRACT_VERSION",
    "RaceNotFoundError",
    "NotPredictionCheckpointError",
    "PredictionUnavailableError",
    "build_v2_explanation_service",
    "get_v2_explanation_service",
]

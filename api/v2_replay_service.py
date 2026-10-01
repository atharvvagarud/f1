"""V2 replay application service (Phase-5 R4).

Read-only replay facade over the frozen Phase-4 pipeline plus the R1/R2
factual domain and the R3 prediction cache:

- knows the served historical races (2018–2024; 2025 is unknown),
- lazily builds/caches one small ``ReplayTimeline`` + ``CheckpointSeries``
  per race (model-free, millisecond-scale),
- reconstructs factual ``RaceState`` on demand via the exact R2 path,
- reads R3 filesystem artifacts (``load_validated_artifact`` /
  ``read_cached_prediction`` only).

STRUCTURAL RULE (R4-I): this module never imports or calls the R3
generation path (``generate_race_artifact`` / ``ensure_race_artifact`` /
``generate_checkpoint``), the prediction engine, the feature bridge, or
the predictor. Read-only R3 helpers are imported by explicit name below
so the boundary is auditable by source scan. The service holds NO engine
reference, so request-time generation is impossible by construction —
a cache miss raises ``PredictionUnavailableError``, never a model call.

No FastAPI types here; routes map domain errors to HTTP status codes.

Memory note: the factory shares the already-loaded canonical corpus and
reconstructor by read-only reference (the frozen Phase-4 module is NOT
modified to expose them); per-race timeline/series caches hold only
small identity lists for races actually requested.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

import pandas as pd

from raceintel.replay import replay as RP
from raceintel.replay.replay_predictions import (
    CheckpointCacheMissError,
    IncompleteCacheError,
    StaleCacheError,
    artifact_path,
    cache_identity_inputs,
    canonical_data_identity,
    load_validated_artifact,
    read_cached_prediction,
    select_checkpoints,
)
from raceintel.replay.replay_reconstruction import ReplayReconstructor
from raceintel.replay.replay_probability_timeline import (
    InconsistentTimelineError,
    ProbabilityTimelineError,
    build_probability_timeline,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE_MANIFEST = _REPO_ROOT / "docs" / "PHASE4_FREEZE_MANIFEST.json"


class ReplayFrameNotFoundError(ValueError):
    """Valid race, but no frame at this index (never an HTTP code)."""

    def __init__(self, race_id: str, frame_index: object):
        super().__init__(
            f"no replay frame {frame_index!r} in race {race_id!r}")
        self.race_id = race_id
        self.frame_index = frame_index


class NotPredictionCheckpointError(ValueError):
    """Frame exists but carries no cached model checkpoint."""

    def __init__(self, race_id: str, frame_index: int,
                 previous_frame: int | None, next_frame: int | None):
        super().__init__(
            f"frame {frame_index} in race {race_id!r} is not a "
            f"prediction checkpoint")
        self.race_id = race_id
        self.frame_index = frame_index
        self.previous_frame = previous_frame
        self.next_frame = next_frame


class PredictionUnavailableError(ValueError):
    """Checkpoint exists but its cached artifact cannot be served.

    ``reason`` is one of ``cache_missing`` / ``cache_stale`` /
    ``cache_incomplete`` / ``cache_corrupt``. The read path NEVER
    generates: callers surface this, offline backfill resolves it.
    """

    def __init__(self, race_id: str, frame_index: int, reason: str):
        super().__init__(
            f"cached prediction unavailable for frame {frame_index} in "
            f"race {race_id!r}: {reason}")
        self.race_id = race_id
        self.frame_index = frame_index
        self.reason = reason


class V2ReplayService:
    """Lazy read-only replay serving (timelines, frames, cached checks)."""

    def __init__(self, states: pd.DataFrame, reconstructor,
                 served_race_ids, *, checkpoints_dir: str,
                 scientific_inputs: dict):
        if not isinstance(states, pd.DataFrame):
            raise ValueError(f"states must be a DataFrame, got {type(states)}")
        self._states = states
        self._reconstructor = reconstructor
        self._served = tuple(served_race_ids)
        self._checkpoints_dir = checkpoints_dir
        self._scientific = dict(scientific_inputs)
        missing = {"feature_set", "feature_set_version",
                   "serving_artifact_sha256",
                   "model_specification_fingerprint", "phase2_content_hash",
                   "probability_semantics"} - set(self._scientific)
        if missing:
            raise ValueError(
                f"scientific_inputs is missing keys: {sorted(missing)}")
        self._timelines: dict[str, RP.ReplayTimeline] = {}
        self._series: dict = {}
        self._resolvers: dict = {}
        self._artifacts: dict[str, dict] = {}
        self._probability_timelines: dict[str, dict] = {}

    @property
    def race_ids(self) -> tuple:
        return self._served

    @property
    def checkpoints_dir(self) -> str:
        return self._checkpoints_dir

    # -- race scope --------------------------------------------------------

    def _require_race(self, race_id: str) -> None:
        if race_id not in self._served:
            raise RaceNotFoundError(race_id)

    # -- lazy factual domain -------------------------------------------------

    def get_timeline(self, race_id: str) -> RP.ReplayTimeline:
        """Per-race timeline, built once on first request (ms-scale)."""
        self._require_race(race_id)
        timeline = self._timelines.get(race_id)
        if timeline is None:
            timeline = RP.build_replay_timeline(self._race_states(race_id))
            self._timelines[race_id] = timeline
        return timeline

    def get_series(self, race_id: str):
        """Per-race checkpoint series, selected once (model-free)."""
        self._require_race(race_id)
        series = self._series.get(race_id)
        if series is None:
            series = select_checkpoints(
                self.get_timeline(race_id), self._race_states(race_id))
            self._series[race_id] = series
        return series

    def _resolver(self, race_id: str) -> ReplayReconstructor:
        resolver = self._resolvers.get(race_id)
        if resolver is None:
            resolver = ReplayReconstructor(
                self.get_timeline(race_id), self._reconstructor)
            self._resolvers[race_id] = resolver
        return resolver

    def _race_states(self, race_id: str) -> pd.DataFrame:
        return self._states[self._states["race_id"] == race_id]

    # -- timeline listing (reconstruction-free) -------------------------------

    def list_frames(self, race_id: str, *, offset: int = 0,
                    limit: int = 100) -> dict:
        timeline = self.get_timeline(race_id)
        total = timeline.frame_count
        window = timeline.frames[offset:offset + limit]
        return {
            "race_id": race_id,
            "replay_contract_version": timeline.replay_contract_version,
            "total_frames": total,
            "offset": offset,
            "limit": limit,
            "returned_count": len(window),
            "frames": [frame.to_dict() for frame in window],
        }

    # -- factual frame ----------------------------------------------------------

    def get_frame(self, race_id: str, frame_index: int) -> dict:
        timeline = self.get_timeline(race_id)
        try:
            frame = timeline.frame_at(frame_index)
        except RP.ReplayTimelineError:
            raise ReplayFrameNotFoundError(
                race_id, frame_index) from None
        state = self._resolver(race_id).state_at(frame.frame_index)
        previous = timeline.previous(frame.frame_index)
        following = timeline.next(frame.frame_index)
        series = self.get_series(race_id)
        by_frame = {c.frame_index: c for c in series.checkpoints}
        checkpoint = by_frame.get(frame.frame_index)
        ordered = [c.frame_index for c in series.checkpoints]
        prev_hit, next_hit = _pointers(ordered, frame.frame_index)
        return {
            "frame": frame.to_dict(),
            "state": state,
            "has_previous": previous is not None,
            "has_next": following is not None,
            "previous_frame_index": (
                previous.frame_index if previous is not None else None),
            "next_frame_index": (
                following.frame_index if following is not None else None),
            "leader_lap": state.race_context.race_leader_laps_at_state,
            "is_prediction_checkpoint": checkpoint is not None,
            "checkpoint_reasons": (
                list(checkpoint.reasons) if checkpoint is not None else []),
            "prediction_cache_available": (
                self._is_available(race_id, frame.frame_index)
                if checkpoint is not None else False),
            "previous_prediction_checkpoint_frame": prev_hit,
            "next_prediction_checkpoint_frame": next_hit,
        }

    # -- cached prediction (read-only) --------------------------------------------

    def get_prediction(self, race_id: str, frame_index: int) -> dict:
        timeline = self.get_timeline(race_id)
        try:
            frame = timeline.frame_at(frame_index)
        except RP.ReplayTimelineError:
            raise ReplayFrameNotFoundError(
                race_id, frame_index) from None
        series = self.get_series(race_id)
        checkpoints = {c.frame_index: c for c in series.checkpoints}
        checkpoint = checkpoints.get(frame.frame_index)
        if checkpoint is None:
            ordered = [c.frame_index for c in series.checkpoints]
            prev_hit, next_hit = _pointers(ordered, frame.frame_index)
            raise NotPredictionCheckpointError(
                race_id, frame.frame_index, prev_hit, next_hit)
        artifact = self._load_artifact(race_id, series)
        try:
            prediction = read_cached_prediction(artifact, frame.frame_index)
        except CheckpointCacheMissError:
            raise PredictionUnavailableError(
                race_id, frame.frame_index,
                "cache_incomplete") from None
        return {
            "frame": frame.to_dict(),
            "checkpoint": checkpoint.to_dict(),
            "prediction": prediction,
            "cache_status": "HIT",
        }

    # -- probability timeline (read-only projection, R6) -----------------------------

    def get_probability_timeline(self, race_id: str) -> dict:
        """Complete cached probability series (never generates, never fills).

        Raises ``RaceNotFoundError`` for unknown races (incl. 2025) and
        ``PredictionUnavailableError`` for missing/stale/incomplete/corrupt
        caches. Per-point model drift surfaces as ``cache_corrupt``.
        """
        self._require_race(race_id)
        cached = self._probability_timelines.get(race_id)
        if cached is not None:
            return cached
        series = self.get_series(race_id)
        artifact = self._load_artifact(race_id, series)
        try:
            timeline = build_probability_timeline(artifact)
        except InconsistentTimelineError as exc:
            raise PredictionUnavailableError(
                race_id, -1, "cache_corrupt") from exc
        except ProbabilityTimelineError as exc:
            raise PredictionUnavailableError(
                race_id, -1, "cache_corrupt") from exc
        self._probability_timelines[race_id] = timeline
        return timeline

    # -- cache internals (positive-only artifact cache) ------------------------------

    def _is_available(self, race_id: str, frame_index: int) -> bool:
        try:
            artifact = self._load_artifact(race_id, self.get_series(race_id))
            read_cached_prediction(artifact, frame_index)
        except (PredictionUnavailableError, CheckpointCacheMissError):
            return False
        return True

    def _load_artifact(self, race_id: str, series) -> dict:
        cached = self._artifacts.get(race_id)
        if cached is not None:
            return cached
        path = artifact_path(self._checkpoints_dir, race_id)
        if not os.path.exists(path):
            raise PredictionUnavailableError(
                race_id, -1, "cache_missing")
        try:
            artifact = load_validated_artifact(
                path, expected_inputs=self._expected_inputs(race_id, series),
                series=series)
        except CheckpointCacheMissError:
            raise PredictionUnavailableError(
                race_id, -1, "cache_missing") from None
        except StaleCacheError:
            raise PredictionUnavailableError(
                race_id, -1, "cache_stale") from None
        except IncompleteCacheError:
            raise PredictionUnavailableError(
                race_id, -1, "cache_incomplete") from None
        except (ValueError, KeyError, TypeError):
            raise PredictionUnavailableError(
                race_id, -1, "cache_corrupt") from None
        self._artifacts[race_id] = artifact
        return artifact

    def _expected_inputs(self, race_id: str, series) -> dict:
        return cache_identity_inputs(
            series=series,
            data_identity=canonical_data_identity(
                self._race_states(race_id), race_id),
            feature_set=self._scientific["feature_set"],
            feature_set_version=self._scientific["feature_set_version"],
            artifact_sha256=self._scientific["serving_artifact_sha256"],
            specification_fingerprint=self._scientific[
                "model_specification_fingerprint"],
            phase2_content_hash=self._scientific["phase2_content_hash"],
            probability_semantics=self._scientific[
                "probability_semantics"])


def _pointers(ordered: list, frame_index: int):
    """Nearest checkpoint frames strictly before/after (never the frame)."""
    previous = next_ = None
    for value in ordered:
        if value < frame_index:
            previous = value
        elif value > frame_index and next_ is None:
            next_ = value
    return previous, next_


def live_scientific_inputs(engine, manifest_path: str | None = None) -> dict:
    """Static cache-key inputs from the live frozen stack (no inference)."""
    identity = engine.model_identity
    manifest = manifest_path or str(_FREEZE_MANIFEST)
    with open(manifest) as handle:
        phase2_hash = json.load(handle)["phase2"]["content_hash"]
    return {
        "feature_set": identity.feature_set,
        "feature_set_version": identity.feature_set_version,
        "serving_artifact_sha256": identity.artifact_sha256,
        "model_specification_fingerprint":
            identity.specification_fingerprint,
        "phase2_content_hash": phase2_hash,
        "probability_semantics": identity.probability_semantics,
    }


def default_checkpoints_dir() -> str:
    from raceintel.replay.replay_predictions import DEFAULT_CHECKPOINTS_DIR
    return os.path.join(str(_REPO_ROOT), DEFAULT_CHECKPOINTS_DIR)


def build_v2_replay_service(v2_service, *, checkpoints_dir=None,
                            scientific_inputs=None) -> V2ReplayService:
    """Share the loaded corpus read-only; build NO model, NO engine.

    ``v2_service`` is only touched for its already-loaded canonical
    ``states`` frame, its reusable reconstructor, its race registry, and
    its engine's static identity (attribute read, never ``predict``).
    The frozen ``api/v2_service.py`` module is unchanged.
    """
    from api.v2_service import V2Service as _V2Service
    if not isinstance(v2_service, _V2Service):
        raise ValueError(
            f"v2_service must be a V2Service, got {type(v2_service)}")
    # Read-only shared references: no second corpus load, no frozen change.
    states = v2_service._states  # noqa: SLF001 - shared read-only corpus
    reconstructor = v2_service._reconstructor  # noqa: SLF001 - shared index
    if scientific_inputs is None:
        scientific_inputs = live_scientific_inputs(v2_service._engine)  # noqa: SLF001 - identity attrs only
    return V2ReplayService(
        states, reconstructor, v2_service.race_ids,
        checkpoints_dir=(checkpoints_dir or default_checkpoints_dir()),
        scientific_inputs=scientific_inputs)


@functools.lru_cache(maxsize=1)
def _cached_replay_service() -> V2ReplayService:
    # Deferred import: merely importing this module must NOT pull the
    # model/prediction stack (import firewall, R4-I).
    from api.v2_service import get_v2_service
    return build_v2_replay_service(get_v2_service())


def get_v2_replay_service() -> V2ReplayService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_replay_service()

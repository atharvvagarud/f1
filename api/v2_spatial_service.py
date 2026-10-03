"""V2 spatial application service (Phase-12 P12-5).

Thin adapter over the frozen replay stack and the P12-4 causal
resolver. HTTP/routes map domain errors to status codes; all science
(causal lookup, availability, transforms, causal windows) stays in
``raceintel.spatial`` — this module only orchestrates:

- served-race eligibility via the existing replay service (unserved
  seasons are unknown there, so unserved-season spatial is rejected
  with zero duplicated season policy),
- the replay clock: ``T = ReplayFrame.anchor_state_time_s`` resolved
  through the existing replay frame first (never a lap-derived or
  frontend-rounded clock),
- the driver universe from the exact replay ``RaceState``,
- one bounded ``SpatialStoreCache(max_races=4)`` per service instance
  (race-level lazy loading, no global corpus preload).

No FastAPI types here; routes map domain errors to HTTP status codes.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.spatial import geometry as _geometry
from raceintel.spatial.errors import (
    SpatialArtifactUnavailableError,
    SpatialGeometryMismatchError,
)
from raceintel.spatial.io import geometry_path
from raceintel.spatial.resolver import (
    SpatialStoreCache,
    resolve_frame,
    resolve_window,
    universe_from_race_state,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Strict upper bound for the causal trail window (seconds). A 30 s
#: window holds at most a few hundred already-known samples per driver,
#: so the response stays small without an extra sample-count knob.
MAX_HISTORY_S = 30.0

#: Resolver contract served over HTTP (machine-readable provenance).
SPATIAL_API_CONTRACT_VERSION = "spatial-api-v1"


class V2SpatialService:
    """Replay-bound spatial serving (geometry, frames, causal windows)."""

    def __init__(self, replay_service, *, spatial_root,
                 max_cached_races: int = 4):
        self._replay = replay_service
        self._root = Path(spatial_root)
        self._cache = SpatialStoreCache(max_races=max_cached_races)

    @property
    def spatial_root(self) -> Path:
        return self._root

    @property
    def spatial_cache(self) -> SpatialStoreCache:
        return self._cache

    # -- geometry ------------------------------------------------------

    def get_geometry(self, race_id: str) -> dict:
        """Renderer-ready circuit geometry (bounded fixed artifact)."""
        self._replay.get_timeline(race_id)
        store = self._cache.get(self._root, race_id)
        if store.geometry_stale:
            raise SpatialGeometryMismatchError(
                store.geometry_problem or "stale spatial geometry")
        if not store.geometry_ok:
            raise SpatialArtifactUnavailableError(
                store.geometry_problem or
                f"race {race_id!r} has no renderable spatial geometry")
        record = json.loads(
            geometry_path(self._root, race_id).read_text(encoding="utf-8"))
        _geometry.validate_geometry(record)
        if record.get("content_sha256") != store.geometry_sha256:
            raise SpatialGeometryMismatchError(
                f"race {race_id!r} geometry identity does not reproduce")
        main = record["main_track"]
        pit = record.get("pit_lane")
        return {
            "race_id": race_id,
            "schema_version": record["schema_version"],
            "algorithm_version": record["algorithm_version"],
            "geometry_sha256": record["content_sha256"],
            "main_track": {
                "points": main["points"],
                "n_points": main["n_points"],
                "closed_loop": main["closed_loop"],
            },
            "pit_lane": (None if pit is None else {
                "points": pit["points"],
                "n_points": pit["n_points"],
                "closed_loop": False,
            }),
            "pit_status": record["pit_status"],
            "render_bounds": dict(
                record["transform"]["render_bounds"]),
        }

    # -- frame ----------------------------------------------------------

    def get_frame(self, race_id: str, frame_index: int) -> dict:
        """Spatial state at the authoritative replay time of one frame."""
        replay_result = self._replay.get_frame(race_id, frame_index)
        query_time = float(
            replay_result["frame"]["anchor_state_time_s"])
        universe = universe_from_race_state(replay_result["state"])
        store = self._cache.get(self._root, race_id)
        frame = resolve_frame(store, query_time, universe)
        return {
            "race_id": race_id,
            "frame_index": int(
                replay_result["frame"]["frame_index"]),
            "query_time_s": frame.query_time_s,
            "source_status": store.observation_status,
            "geometry_sha256": frame.geometry_sha256,
            "observation_content_sha256":
                frame.observation_content_sha256,
            "resolver_contract_version":
                frame.resolver_contract_version,
            "fresh_count": frame.fresh_count,
            "stale_count": frame.stale_count,
            "unavailable_count": frame.unavailable_count,
            "drivers": [{
                "driver_id": state.driver_id,
                "driver_number": state.driver_number,
                "availability": state.availability,
                "observation_time_s": state.observation_time_s,
                "age_s": state.age_s,
                "render_x": state.render_x,
                "render_y": state.render_y,
                "outside_viewport": state.outside_viewport,
            } for state in frame.drivers],
        }

    # -- causal window ----------------------------------------------------

    def get_window(self, race_id: str, frame_index: int,
                   driver_number: int, history_s: float) -> dict:
        """Bounded causal trail ``[T - history, T]`` for one driver."""
        replay_result = self._replay.get_frame(race_id, frame_index)
        query_time = float(
            replay_result["frame"]["anchor_state_time_s"])
        store = self._cache.get(self._root, race_id)
        samples = resolve_window(store, int(driver_number), query_time,
                                 float(history_s))
        return {
            "race_id": race_id,
            "frame_index": int(
                replay_result["frame"]["frame_index"]),
            "driver_number": int(driver_number),
            "query_time_s": query_time,
            "history_s": float(history_s),
            "sample_count": len(samples),
            "samples": [{
                "observation_time_s": sample.observation_time_s,
                "render_x": sample.render_x,
                "render_y": sample.render_y,
            } for sample in samples],
        }


def default_spatial_root() -> str:
    """Repository root holding the generated ``data/spatial`` corpus."""
    return str(_REPO_ROOT)


def build_v2_spatial_service(replay_service, *, spatial_root=None,
                             max_cached_races: int = 4
                             ) -> V2SpatialService:
    """Share the replay service read-only; build no second corpus.

    ``replay_service`` is only touched for its existing frame/timeline
    accessors, so served-race eligibility and the replay clock stay
    canonical. The frozen ``api/v2_replay_service.py`` module is
    unchanged.
    """
    for method in ("get_frame", "get_timeline"):
        if not callable(getattr(replay_service, method, None)):
            raise ValueError(
                "replay_service must expose get_frame/get_timeline, "
                f"got {type(replay_service)}")
    return V2SpatialService(
        replay_service,
        spatial_root=(spatial_root or default_spatial_root()),
        max_cached_races=max_cached_races)


@functools.lru_cache(maxsize=1)
def _cached_spatial_service() -> V2SpatialService:
    # Deferred import: merely importing this module must NOT pull the
    # model/prediction stack (import firewall, R4-I).
    from api.v2_replay_service import get_v2_replay_service
    return build_v2_spatial_service(get_v2_replay_service())


def get_v2_spatial_service() -> V2SpatialService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_spatial_service()

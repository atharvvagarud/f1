"""V2 application service (Phase-4 R5).

Owns the reusable Phase-4 pipeline for HTTP serving: canonical
read-only corpus (loaded once per process), one ``RaceStateReconstructor``,
one ``RaceStateFeatureBridge``, one frozen predictor, one
``RacePredictionEngine``. No FastAPI types here; routes map domain
errors to HTTP status codes.

2025 serving policy: the protected-holdout TARGETS are sealed and R0
never authorized 2025 product inference, so this service serves the
development era only (seasons 2018-2024). Races outside that registry
— including any 2025 race_id — are unknown (404). The service never
loads label/target entities, the model matrix, or protected evaluation
artifacts. The frozen ``PriorHistory`` bundle
may physically contain later-season rows, but the Phase-2 firewall
restricts priors to strictly-past rows, so dev-era snapshots are
unaffected (R3).
"""

from __future__ import annotations

import functools
import glob as _glob

import pandas as pd

from raceintel.race_state import race_state as RS
from raceintel.config import V2Paths
from raceintel.features.build_matrix import load_history
from raceintel.model_lab import serving as SERVING
from raceintel.prediction import RacePredictionEngine, load_production_prediction_engine
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError, RaceStateReconstructor

#: Development-era serving registry (inclusive). No 2025 product
#: inference: the holdout targets are sealed and R0 authorizes dev only.
SERVED_SEASONS = tuple(range(2018, 2025))
MAX_SERVED_SEASON = 2024

#: Identity-only race summary fields (PRE_RACE facts; no outcomes exist
#: on the races entity and none are read anywhere in this module).
RACE_SUMMARY_FIELDS = (
    "race_id", "season", "round_no", "event_name", "circuit_id",
    "country", "location", "scheduled_laps",
)


def _read_entity(paths: V2Paths, entity: str) -> pd.DataFrame:
    frames = []
    for season in SERVED_SEASONS:
        pattern = str(paths.processed_dir / entity / f"season={season}"
                      / "*.parquet")
        for path in sorted(_glob.glob(pattern)):
            frames.append(pd.read_parquet(path))
    if not frames:
        raise RuntimeError(f"no canonical rows for entity {entity!r}")
    return pd.concat(frames, ignore_index=True)


class V2Service:
    """Reusable Phase-4 serving pipeline (process-local, read-only)."""

    def __init__(self, states: pd.DataFrame, results: pd.DataFrame,
                 races: pd.DataFrame, paths: V2Paths | None = None):
        if paths is None:
            paths = V2Paths.resolve()
        self._states = states
        self._history = load_history(paths)
        self._reconstructor = RaceStateReconstructor(
            states, results, race_meta=_race_meta(races))
        self._engine = load_production_prediction_engine(
            states, self._history)
        self._races = _race_summaries(races)

    @property
    def race_ids(self) -> tuple:
        return tuple(summary["race_id"] for summary in self._races)

    @property
    def engine(self) -> RacePredictionEngine:
        return self._engine

    def list_races(self) -> list[dict]:
        """Factual race registry, (season, round_no, race_id) order."""
        return [dict(summary) for summary in self._races]

    def list_anchors(self, race_id: str, *, offset: int = 0,
                     limit: int = 100) -> dict:
        """Exact anchor identities for one race (discovery only).

        Stable canonical order: (state_time_s, lap_number, driver_id).
        Identity columns only — no states, no labels, no probabilities.
        """
        self._require_race(race_id)
        frame = self._states[self._states["race_id"] == race_id]
        ordered = frame.sort_values(
            ["state_time_s", "lap_number", "driver_id"],
            kind="mergesort")[["driver_id", "lap_number", "state_time_s"]]
        total = len(ordered)
        window = ordered.iloc[offset:offset + limit]
        return {
            "race_id": race_id,
            "total": int(total),
            "offset": int(offset),
            "limit": int(limit),
            "anchors": [{
                "driver_id": str(row.driver_id),
                "lap_number": int(row.lap_number),
                "state_time_s": float(row.state_time_s),
            } for row in window.itertuples()],
        }

    def get_state(self, race_id: str, anchor_driver_id: str,
                  anchor_lap_number: int,
                  anchor_state_time_s: float) -> RS.RaceState:
        """Exact-anchor reconstruction (never nearest-matched)."""
        self._require_race(race_id)
        anchor = RS.AnchorObservation(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s)
        return self._reconstructor.reconstruct(anchor)

    def predict_snapshot(self, race_id: str, anchor_driver_id: str,
                         anchor_lap_number: int, anchor_state_time_s: float):
        """Exact-anchor frozen winner snapshot (one batch model call)."""
        state = self.get_state(race_id, anchor_driver_id,
                               anchor_lap_number, anchor_state_time_s)
        return self._engine.predict(state)

    def _require_race(self, race_id: str) -> None:
        if race_id not in set(self.race_ids):
            raise RaceNotFoundError(race_id)


def _race_meta(races: pd.DataFrame) -> dict:
    meta: dict = {}
    for row in races.itertuples():
        scheduled = getattr(row, "total_laps_scheduled", None)
        meta[str(row.race_id)] = {
            "scheduled_laps": (None if pd.isna(scheduled)
                               else int(scheduled))}
    return meta


def _race_summaries(races: pd.DataFrame) -> tuple:
    served = races[races["season"].isin(SERVED_SEASONS)].copy()
    served["scheduled_laps"] = served["total_laps_scheduled"].map(
        lambda value: None if pd.isna(value) else int(value))
    ordered = served.sort_values(["season", "round_no", "race_id"],
                                 kind="mergesort")
    summaries = []
    for row in ordered.itertuples():
        summaries.append({
            "race_id": str(row.race_id),
            "season": int(row.season),
            "round_no": int(row.round_no),
            "event_name": str(row.event_name),
            "circuit_id": (None if pd.isna(row.circuit_id)
                           else str(row.circuit_id)),
            "country": (None if pd.isna(row.country) else str(row.country)),
            "location": (None if pd.isna(row.location)
                         else str(row.location)),
            "scheduled_laps": row.scheduled_laps,
        })
    return tuple(summaries)


def load_v2_service(paths: V2Paths | None = None) -> V2Service:
    """Build the serving pipeline (expensive: corpus + history + artifact)."""
    resolved = paths if paths is not None else V2Paths.resolve()
    states = _read_entity(resolved, "driver_lap_state_d9")
    results = _read_entity(resolved, "results")
    races = _read_entity(resolved, "races")
    return V2Service(states, results, races, paths=resolved)


@functools.lru_cache(maxsize=1)
def _cached_service() -> V2Service:
    return load_v2_service()


def get_v2_service() -> V2Service:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_service()


def predictor_identity() -> dict:
    """Recorded production metadata without running inference."""
    return SERVING.describe_serving_artifact()

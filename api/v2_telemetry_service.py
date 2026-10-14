"""V3.10F driver-telemetry application service.

Read-only race-scoped projection over the frozen D9 corpus
(``driver_lap_state_d9``) plus the ``stints`` entity. Shares the already
loaded canonical states frame by read-only reference; loads only the
small stints entity itself.

STRUCTURAL RULES (auditable by source scan):
- this module never imports the prediction engine, the feature bridge,
  the R3 generation path, strategy, consensus, simulation, or MC2 code.
- it performs NO temporal computation, NO aggregation, NO reference or
  delta calculation, NO validity filtering. Projection is verbatim:
  NaN -> None, non-finite floats -> None. Causal (<=T) slicing lives
  client-side in the typed telemetry selector.
- observation boundary per lap: the D9 row's ``state_time_s``
  (``observed_at_s``). The replay frame grid IS the unique
  ``state_time_s`` grid, so a lap row's own ``state_time_s`` is a frame
  anchor time (V3.10F audit: results/v3/v3_10f/telemetry_source_audit.json).
"""

from __future__ import annotations

import functools
import glob as _glob
import math

import pandas as pd

from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

TELEMETRY_CONTRACT_VERSION = "v3.10f-telemetry/1"

#: Verbatim D9 columns projected (allowlist; label/future/model columns
#: are never read).
LAP_COLUMNS = (
    "driver_id", "lap_number", "state_time_s", "lap_time_s",
    "sector_1_s", "sector_2_s", "sector_3_s", "compound", "tyre_life",
    "stint_number", "stint_lap", "fresh_tyre", "pit_in_s", "pit_out_s",
    "track_status", "deleted", "is_accurate", "fastf1_generated",
)

STINT_COLUMNS = (
    "driver_id", "stint_number", "compound", "fresh_tyre", "start_lap",
    "end_lap", "pit_in_lap", "pit_out_lap", "tyre_age_at_start",
)


def _opt_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _opt_int(value) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _present(value) -> bool | None:
    """IN_LAP presence flag: True when the source timestamp exists."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return True


def _opt_bool(value) -> bool | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return bool(value)


def _opt_str(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value)
    return text if text else None


class V2TelemetryService:
    """Lazy read-only telemetry projection (laps + stints, one race)."""

    def __init__(self, states: pd.DataFrame, stints: pd.DataFrame,
                 served_race_ids):
        if not isinstance(states, pd.DataFrame):
            raise ValueError(
                f"states must be a DataFrame, got {type(states)}")
        if not isinstance(stints, pd.DataFrame):
            raise ValueError(
                f"stints must be a DataFrame, got {type(stints)}")
        missing = [c for c in ("race_id", "driver_id", "lap_number",
                               "state_time_s") if c not in states.columns]
        if missing:
            raise ValueError(
                f"states is missing required columns: {missing}")
        self._states = states
        self._stints = stints
        self._served = tuple(served_race_ids)
        self._cache: dict[str, dict] = {}

    @property
    def race_ids(self) -> tuple:
        return self._served

    def _require_race(self, race_id: str) -> None:
        if race_id not in self._served:
            raise RaceNotFoundError(race_id)

    def get_telemetry(self, race_id: str) -> dict:
        """Full-race lap + stint evidence (causal slicing is client-side)."""
        self._require_race(race_id)
        cached = self._cache.get(race_id)
        if cached is not None:
            return cached
        laps = self._project_laps(race_id)
        observed = {(lap["driver_id"], lap["lap_number"]): lap["observed_at_s"]
                    for lap in laps if lap["observed_at_s"] is not None}
        stints = self._project_stints(race_id, observed)
        payload = {
            "race_id": race_id,
            "telemetry_contract_version": TELEMETRY_CONTRACT_VERSION,
            "lap_count": len(laps),
            "stint_count": len(stints),
            "laps": laps,
            "stints": stints,
        }
        self._cache[race_id] = payload
        return payload

    def _project_laps(self, race_id: str) -> list[dict]:
        frame = self._states[self._states["race_id"] == race_id]
        available = [c for c in LAP_COLUMNS if c in frame.columns]
        ordered = frame.sort_values(["driver_id", "lap_number"],
                                    kind="mergesort")
        laps: list[dict] = []
        for row in ordered.itertuples(index=False):
            record = {c: getattr(row, c, None) for c in available}
            observed_at_s = _opt_float(record.get("state_time_s"))
            if observed_at_s is None:
                continue
            laps.append({
                "driver_id": str(record.get("driver_id")),
                "lap_number": _opt_int(record.get("lap_number")),
                "observed_at_s": observed_at_s,
                "lap_time_s": _opt_float(record.get("lap_time_s")),
                "sector_1_s": _opt_float(record.get("sector_1_s")),
                "sector_2_s": _opt_float(record.get("sector_2_s")),
                "sector_3_s": _opt_float(record.get("sector_3_s")),
                "compound": _opt_str(record.get("compound")),
                "tyre_life": _opt_int(record.get("tyre_life")),
                "stint_number": _opt_int(record.get("stint_number")),
                "stint_lap": _opt_int(record.get("stint_lap")),
                "fresh_tyre": _opt_bool(record.get("fresh_tyre")),
                "pit_entry": _present(record.get("pit_in_s"))
                if "pit_in_s" in available else None,
                "pit_exit": _present(record.get("pit_out_s"))
                if "pit_out_s" in available else None,
                "track_status": _opt_str(record.get("track_status")),
                "deleted": _opt_bool(record.get("deleted")),
                "is_accurate": _opt_bool(record.get("is_accurate")),
                "fastf1_generated": _opt_bool(
                    record.get("fastf1_generated")),
            })
        return [lap for lap in laps if lap["lap_number"] is not None]

    def _project_stints(self, race_id: str, observed: dict) -> list[dict]:
        frame = self._stints[self._stints["race_id"] == race_id]
        available = [c for c in STINT_COLUMNS if c in frame.columns]
        ordered = frame.sort_values(["driver_id", "stint_number"],
                                    kind="mergesort")
        stints: list[dict] = []
        for row in ordered.itertuples(index=False):
            record = {c: getattr(row, c, None) for c in available}
            stint_number = _opt_int(record.get("stint_number"))
            if stint_number is None:
                continue
            driver_id = str(record.get("driver_id"))
            start_lap = _opt_int(record.get("start_lap"))
            end_lap = _opt_int(record.get("end_lap"))
            stints.append({
                "driver_id": driver_id,
                "stint_number": stint_number,
                "compound": _opt_str(record.get("compound")),
                "fresh_tyre": _opt_bool(record.get("fresh_tyre")),
                "start_lap": start_lap,
                "end_lap": end_lap,
                "start_observed_at_s": observed.get((driver_id, start_lap))
                if start_lap is not None else None,
                "end_observed_at_s": observed.get((driver_id, end_lap))
                if end_lap is not None else None,
                "pit_in_lap": _opt_int(record.get("pit_in_lap")),
                "pit_out_lap": _opt_int(record.get("pit_out_lap")),
                "tyre_age_at_start": _opt_int(
                    record.get("tyre_age_at_start")),
            })
        return stints


def _read_stints_entity(processed_dir, seasons) -> pd.DataFrame:
    frames = []
    for season in seasons:
        pattern = str(processed_dir / "stints" / f"season={season}"
                      / "*.parquet")
        for path in sorted(_glob.glob(pattern)):
            frames.append(pd.read_parquet(path))
    if not frames:
        raise RuntimeError("no canonical rows for entity 'stints'")
    return pd.concat(frames, ignore_index=True)


def build_v2_telemetry_service(v2_service, *, stints=None,
                               seasons=None) -> V2TelemetryService:
    """Share the loaded corpus read-only; load only the stints entity.

    ``v2_service`` is only touched for its already-loaded canonical
    ``states`` frame and its race registry. The frozen ``api/v2_service.py``
    module is unchanged.
    """
    from api.v2_service import (  # deferred: importing this module alone
        SERVED_SEASONS, V2Service as _V2Service,  # must not pull the engine
    )
    if not isinstance(v2_service, _V2Service):
        raise ValueError(
            f"v2_service must be a V2Service, got {type(v2_service)}")
    # Read-only shared reference: no second corpus load, no frozen change.
    states = v2_service._states  # noqa: SLF001 - shared read-only corpus
    if stints is None:
        from raceintel.config import V2Paths
        paths = V2Paths.resolve()
        stints = _read_stints_entity(
            paths.processed_dir, seasons or SERVED_SEASONS)
    return V2TelemetryService(states, stints, v2_service.race_ids)


@functools.lru_cache(maxsize=1)
def _cached_telemetry_service() -> V2TelemetryService:
    # Deferred import: merely importing this module must NOT pull the
    # model/prediction stack (import firewall).
    from api.v2_service import get_v2_service
    return build_v2_telemetry_service(get_v2_service())


def get_v2_telemetry_service() -> V2TelemetryService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_telemetry_service()

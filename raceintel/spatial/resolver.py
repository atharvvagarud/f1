"""Phase-12 temporal spatial resolver (P12-4).

Authoritative causal resolver mapping a historical replay time ``T`` to
spatial state: for each driver, the latest canonical spatial observation
with ``observation_time_s <= T`` (never future information), its age,
FRESH/STALE/UNAVAILABLE availability (frozen P12-1 thresholds), exact
canonical raw coordinates, and render coordinates via the exact stored
P12-3 geometry transform.

Causal rule (more important than visual smoothness): no
nearest-neighbor lookup, no future backfill, no future interpolation.
``T`` is the frozen replay clock ``anchor_state_time_s``
(``ReplayFrame.anchor_state_time_s == RaceState.state_time_s``); no
second clock is introduced here.

Presentation-only: nothing resolved here may enter ALL_84, the Phase-2
matrix, the winner model, simulation, strategy, or explainability.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from raceintel.spatial import contracts as SC
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V
from raceintel.spatial.errors import (
    SpatialArtifactUnavailableError,
    SpatialContractError,
    SpatialGeometryMismatchError,
    SpatialIdentityError,
    SpatialProvenanceError,
    SpatialResolutionError,
)
from raceintel.spatial.io import (
    artifact_path,
    geometry_manifest_path,
    geometry_path,
    load_geometry_manifest,
    load_manifest,
    manifest_path,
    read_observations,
)

#: Resolver contract version (machine-record provenance, never generic).
RESOLVER_CONTRACT_VERSION = "spatial-resolver-v1"

#: Query-time tolerance: age is ``T - observation_time`` in float64;
#: exact boundary ownership is decided by ``classify_availability``.
#: A strictly negative age is impossible for a causal lookup and fails
#: closed (it would mean future information leaked in).
AGE_TOL_S = 0.0


# ---------------------------------------------------------------------------
# Query-time domain (Part U)
# ---------------------------------------------------------------------------

def require_query_time(value: object) -> float:
    """Validate a replay query time ``T``.

    Accepts any finite number (negative ``T`` yields no causal
    observations, hence all-UNAVAILABLE rows — canonical observations
    are non-negative on the session clock). Rejects NaN/inf (the frozen
    replay clock rejects them too) and non-numeric types.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialResolutionError(
            f"query_time_s must be a finite number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SpatialResolutionError(
            f"query_time_s must be finite (no NaN/Infinity), "
            f"got {value!r}")
    return result


def require_history_window(value: object) -> float:
    """Validate a causal history-window length in seconds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialResolutionError(
            f"history window must be a finite number >= 0, got {value!r}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SpatialResolutionError(
            f"history window must be finite and >= 0, got {value!r}")
    return result


# ---------------------------------------------------------------------------
# Result contracts (Part D)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriverUniverseEntry:
    """One expected frame member, keyed by canonical spatial identity.

    ``driver_number`` is the canonical join key (may be None for roster
    members that carry no telemetry identity — e.g. permanent
    zero-state entrants — which always resolve UNAVAILABLE).
    ``driver_id`` is the replay display identity, carried through so
    P12-7 can present rows without re-joining; at least one of the two
    must be present.
    """

    driver_number: int | None = None
    driver_id: str | None = None

    def __post_init__(self) -> None:
        if self.driver_number is not None:
            if (isinstance(self.driver_number, bool)
                    or not isinstance(self.driver_number, int)):
                raise SpatialIdentityError(
                    "universe driver_number must be an int or None, "
                    f"got {self.driver_number!r}")
            if not SC.DRIVER_NUMBER_MIN <= self.driver_number \
                    <= SC.DRIVER_NUMBER_MAX:
                raise SpatialIdentityError(
                    f"universe driver_number out of range, "
                    f"got {self.driver_number!r}")
        if self.driver_id is not None:
            if not isinstance(self.driver_id, str) \
                    or not self.driver_id.strip():
                raise SpatialIdentityError(
                    "universe driver_id must be a non-empty string or "
                    f"None, got {self.driver_id!r}")
        if self.driver_number is None and self.driver_id is None:
            raise SpatialIdentityError(
                "universe entry needs driver_number and/or driver_id")


def universe_from_race_state(race_state: object) -> tuple:
    """Build the authoritative driver universe from a live RaceState.

    Structural read only (``.drivers`` entries exposing ``.driver_id``
    / ``.driver_number``): this module never imports the race-state
    package, so the dependency direction stays replay -> spatial at the
    P12-7 integration boundary, never spatial -> replay. Caller order
    is preserved (RaceState normalizes to ``driver_id`` order, which is
    the deterministic frame order).
    """
    drivers = getattr(race_state, "drivers", None)
    if not drivers:
        raise SpatialIdentityError(
            "race_state provides no driver roster")
    universe = []
    for entry in drivers:
        number = getattr(entry, "driver_number", None)
        if isinstance(number, float) and float(number).is_integer():
            number = int(number)
        if isinstance(number, bool):
            number = None
        driver_id = getattr(entry, "driver_id", None)
        universe.append(DriverUniverseEntry(
            driver_number=number, driver_id=driver_id))
    return tuple(universe)


@dataclass(frozen=True)
class SpatialDriverState:
    """One driver's resolved spatial state at query time ``T``.

    UNAVAILABLE rows carry None for every observation-derived field
    (the contract's missing-value representation); no future
    coordinate may ever appear. ``outside_viewport`` flags a true
    transformed coordinate outside the normalized render bounds (pit
    lane, runoff, incident, source noise) — the position is preserved,
    never clamped.
    """

    race_id: str
    driver_number: int | None
    driver_id: str | None
    query_time_s: float
    observation_time_s: float | None
    age_s: float | None
    availability: str
    raw_x: int | None
    raw_y: int | None
    render_x: float | None
    render_y: float | None
    source: str | None
    status: str | None
    outside_viewport: bool = False

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "driver_number": self.driver_number,
            "driver_id": self.driver_id,
            "query_time_s": self.query_time_s,
            "observation_time_s": self.observation_time_s,
            "age_s": self.age_s,
            "availability": self.availability,
            "raw_x": self.raw_x,
            "raw_y": self.raw_y,
            "render_x": self.render_x,
            "render_y": self.render_y,
            "source": self.source,
            "status": self.status,
            "outside_viewport": self.outside_viewport,
        }


@dataclass(frozen=True)
class TrajectorySample:
    """One causal window sample: ``start <= t <= T``, ascending."""

    observation_time_s: float
    raw_x: int
    raw_y: int
    render_x: float | None
    render_y: float | None

    def to_dict(self) -> dict:
        return {
            "observation_time_s": self.observation_time_s,
            "raw_x": self.raw_x,
            "raw_y": self.raw_y,
            "render_x": self.render_x,
            "render_y": self.render_y,
        }


@dataclass(frozen=True)
class SpatialFrame:
    """Deterministic multi-driver spatial state at query time ``T``."""

    race_id: str
    query_time_s: float
    observation_content_sha256: str
    geometry_sha256: str | None
    drivers: tuple
    fresh_count: int
    stale_count: int
    unavailable_count: int
    resolver_contract_version: str = RESOLVER_CONTRACT_VERSION

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "query_time_s": self.query_time_s,
            "observation_content_sha256": self.observation_content_sha256,
            "geometry_sha256": self.geometry_sha256,
            "resolver_contract_version": self.resolver_contract_version,
            "fresh_count": self.fresh_count,
            "stale_count": self.stale_count,
            "unavailable_count": self.unavailable_count,
            "drivers": [entry.to_dict() for entry in self.drivers],
        }


# ---------------------------------------------------------------------------
# Race-level store (Parts AA/AK)
# ---------------------------------------------------------------------------

class _DriverSeries:
    """Sorted per-driver observation arrays for searchsorted lookup."""

    __slots__ = ("times", "x", "y", "source", "status")

    def __init__(self, times: np.ndarray, x: np.ndarray, y: np.ndarray,
                 source: np.ndarray, status: np.ndarray) -> None:
        self.times = times
        self.x = x
        self.y = y
        self.source = source
        self.status = status

    def nbytes(self) -> int:
        return (self.times.nbytes + self.x.nbytes + self.y.nbytes
                + self.source.nbytes + self.status.nbytes)


class RaceSpatialStore:
    """One race's indexed observations plus verified geometry.

    Load one race artifact, partition by driver into sorted numpy
    arrays; every later query is a ``searchsorted`` lookup (no
    per-frame Parquet reads, no global corpus preload). Identity-aware:
    the observation content hash and geometry source linkage are pinned
    at load; a changed artifact identity never serves stale indexes.
    """

    def __init__(self, *, race_id: str, observation_content_sha256: str,
                 observation_status: str, series: dict,
                 transform: dict | None, geometry_sha256: str | None,
                 geometry_ok: bool, geometry_stale: bool,
                 geometry_problem: str | None) -> None:
        self._race_id = race_id
        self._observation_content_sha256 = observation_content_sha256
        self._observation_status = observation_status
        self._series = series
        self._transform = transform
        self._geometry_sha256 = geometry_sha256
        self._geometry_ok = geometry_ok
        self._geometry_stale = geometry_stale
        self._geometry_problem = geometry_problem
        self._cache_identities: tuple | None = None
        self._artifact_stat: tuple | None = None

    def _artifact_fresh(self, root: Path) -> bool:
        """Hit-path guard: artifact files unchanged since load (stat)."""
        if self._artifact_stat is None:
            return False
        try:
            obs = artifact_path(root, self._race_id).stat()
            current = (obs.st_mtime_ns, obs.st_size)
            geom_path = geometry_path(root, self._race_id)
            if geom_path.is_file():
                geom = geom_path.stat()
                current += (geom.st_mtime_ns, geom.st_size)
            return current == self._artifact_stat
        except OSError:
            return False

    @property
    def race_id(self) -> str:
        return self._race_id

    @property
    def observation_content_sha256(self) -> str:
        return self._observation_content_sha256

    @property
    def observation_status(self) -> str:
        """P12-2 manifest status (COMPLETE or PARTIAL; never upgraded)."""
        return self._observation_status

    @property
    def transform(self) -> dict | None:
        """Verified P12-3 render transform, or None without geometry."""
        return self._transform

    @property
    def geometry_sha256(self) -> str | None:
        return self._geometry_sha256

    @property
    def geometry_ok(self) -> bool:
        return self._geometry_ok

    @property
    def geometry_stale(self) -> bool:
        """A COMPLETE geometry row existed but failed source identity."""
        return self._geometry_stale

    @property
    def geometry_problem(self) -> str | None:
        return self._geometry_problem

    @property
    def driver_numbers(self) -> tuple:
        """Sorted driver numbers present in the observation artifact."""
        return tuple(sorted(self._series))

    def series_for(self, driver_number: int) -> _DriverSeries | None:
        return self._series.get(driver_number)

    def index_bytes(self) -> int:
        """Indexed numpy payload (arrays only; excludes frame overhead)."""
        return sum(series.nbytes() for series in self._series.values())

    def row_count(self) -> int:
        return sum(len(series.times) for series in self._series.values())

    @classmethod
    def load(cls, root: str | Path, race_id: str) -> "RaceSpatialStore":
        """Load and verify one race's resolver store (fail-closed)."""
        from raceintel.spatial import geometry as G

        root_path = Path(root)
        manifest = load_manifest(manifest_path(root_path))
        row = manifest.get("races", {}).get(race_id)
        if row is None or row.get("status") not in (
                SM.STATUS_COMPLETE, SM.STATUS_PARTIAL):
            raise SpatialArtifactUnavailableError(
                f"race {race_id!r} has no resolvable spatial observations "
                f"(manifest status "
                f"{row.get('status') if isinstance(row, dict) else None!r})")
        status = row["status"]
        path = artifact_path(root_path, race_id)
        if not path.is_file():
            raise SpatialArtifactUnavailableError(
                f"race {race_id!r} observation artifact is missing")
        frame = read_observations(path)
        V.validate_observations(frame)
        content_hash = V.logical_content_hash(frame)
        expected = (row.get("provenance") or {}).get("content_sha256")
        if expected != content_hash:
            raise SpatialProvenanceError(
                f"race {race_id!r} observation content drifted from the "
                f"manifest identity")
        series: dict[int, _DriverSeries] = {}
        for driver_number, group in frame.groupby("driver_number"):
            ordered = group.sort_values("observation_time_s")
            series[int(driver_number)] = _DriverSeries(
                times=ordered["observation_time_s"].to_numpy(
                    dtype=np.float64),
                x=ordered["x"].to_numpy(dtype=np.int64),
                y=ordered["y"].to_numpy(dtype=np.int64),
                source=ordered["source"].to_numpy(),
                status=ordered["status"].to_numpy(),
            )
        transform: dict | None = None
        geometry_sha: str | None = None
        geometry_ok = False
        geometry_stale = False
        geometry_problem: str | None = None
        geometry_manifest = load_geometry_manifest(
            geometry_manifest_path(root_path))
        geometry_row = geometry_manifest.get("races", {}).get(race_id)
        if geometry_row is None or geometry_row.get("status") != \
                G.GEOMETRY_STATUS_COMPLETE:
            reason = (geometry_row.get("reason")
                      if isinstance(geometry_row, dict)
                      else "no geometry manifest row")
            geometry_problem = (
                f"race {race_id!r} has no renderable geometry: {reason}")
        else:
            geometry_path_obj = geometry_path(root_path, race_id)
            try:
                import json as _json

                record = _json.loads(
                    geometry_path_obj.read_text(encoding="utf-8"))
                G.validate_geometry(record)
                if record["source"].get("observation_content_sha256") \
                        != content_hash:
                    raise SpatialGeometryMismatchError(
                        f"race {race_id!r} geometry derives from another "
                        f"observation version")
                if record.get("content_sha256") != geometry_row.get(
                        "geometry_sha256") or \
                        G.geometry_content_hash(record) != record.get(
                            "content_sha256"):
                    raise SpatialGeometryMismatchError(
                        f"race {race_id!r} geometry identity does not "
                        f"reproduce")
                transform = record["transform"]
                geometry_sha = record["content_sha256"]
                geometry_ok = True
            except SpatialGeometryMismatchError as exc:
                geometry_problem = str(exc)
                geometry_stale = True
            except SpatialContractError as exc:
                geometry_problem = (
                    f"race {race_id!r} geometry artifact invalid: {exc}")
            except (OSError, ValueError) as exc:
                geometry_problem = (
                    f"race {race_id!r} geometry artifact unreadable")
        store = cls(race_id=race_id,
                    observation_content_sha256=content_hash,
                    observation_status=status, series=series,
                    transform=transform, geometry_sha256=geometry_sha,
                    geometry_ok=geometry_ok, geometry_stale=geometry_stale,
                    geometry_problem=geometry_problem)
        obs_stat = path.stat()
        stat = (obs_stat.st_mtime_ns, obs_stat.st_size)
        geometry_file = geometry_path(root_path, race_id)
        if geometry_file.is_file():
            geom_stat = geometry_file.stat()
            stat += (geom_stat.st_mtime_ns, geom_stat.st_size)
        store._artifact_stat = stat
        return store


class SpatialStoreCache:
    """Bounded race-level store cache (never the global corpus).

    Keyed by race; every hit re-checks the manifest content identities
    (observation hash + geometry hash) plus the artifact file stats, and
    reloads on any drift, so a changed artifact identity can never serve
    a stale index.
    """

    def __init__(self, max_races: int = 4) -> None:
        if not isinstance(max_races, int) or max_races < 1:
            raise SpatialContractError(
                f"max_races must be a positive int, got {max_races!r}")
        self._max_races = max_races
        self._entries: "OrderedDict[tuple, RaceSpatialStore]" = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _identities(root: Path, race_id: str) -> tuple:
        from raceintel.spatial import geometry as G

        manifest = load_manifest(manifest_path(root))
        row = manifest.get("races", {}).get(race_id)
        obs_hash = (row.get("provenance") or {}).get("content_sha256") \
            if isinstance(row, dict) else None
        geometry_manifest = load_geometry_manifest(
            geometry_manifest_path(root))
        geometry_row = geometry_manifest.get("races", {}).get(race_id)
        geom_hash = geometry_row.get("geometry_sha256") \
            if isinstance(geometry_row, dict) and geometry_row.get(
                "status") == G.GEOMETRY_STATUS_COMPLETE else None
        geom_status = geometry_row.get("status") \
            if isinstance(geometry_row, dict) else None
        return (obs_hash, geom_hash, geom_status)

    def get(self, root: str | Path, race_id: str) -> RaceSpatialStore:
        root_path = Path(root)
        identities = self._identities(root_path, race_id)
        key = (str(root_path), race_id)
        hit = self._entries.get(key)
        if hit is not None and hit._cache_identities == identities \
                and hit._artifact_fresh(root_path):
            self._entries.move_to_end(key)
            return hit
        if hit is not None:
            del self._entries[key]
        store = RaceSpatialStore.load(root_path, race_id)
        store._cache_identities = identities
        self._entries[key] = store
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_races:
            self._entries.popitem(last=False)
        return store

    def invalidate(self, race_id: str | None = None,
                   root: str | Path | None = None) -> int:
        """Drop cached stores (one race, or everything). Returns evictions."""
        if race_id is None:
            count = len(self._entries)
            self._entries.clear()
            return count
        key = (str(Path(root)) if root is not None else None, race_id)
        if root is None:
            doomed = [key for key in self._entries if key[1] == race_id]
        else:
            doomed = [key] if key in self._entries else []
        for key in doomed:
            del self._entries[key]
        return len(doomed)


# ---------------------------------------------------------------------------
# Core causal lookup (Parts H/V)
# ---------------------------------------------------------------------------

def _causal_index(times: np.ndarray, query_time_s: float) -> int:
    """Position of the latest sample with ``time <= T`` (-1 if none).

    ``side="right"`` owns exact-timestamp equality to the earlier
    sample; linear scans are forbidden (millions of rows per frame
    would not serve interactive replay).
    """
    return int(np.searchsorted(times, query_time_s, side="right")) - 1


def resolve_driver(store: RaceSpatialStore, driver_number: int | None,
                   query_time_s: float, *,
                   driver_id: str | None = None) -> SpatialDriverState:
    """Resolve one driver's spatial state at ``T`` (independently testable).

    Unknown drivers (or roster members with ``driver_number=None``)
    resolve UNAVAILABLE — never an error, never a future coordinate.
    Raw coordinates are the exact canonical observation (no smoothing,
    no snapping, no projection). Render coordinates reuse the store's
    verified P12-3 transform, or None without verified geometry.
    """
    query_time = require_query_time(query_time_s)
    race_id = store.race_id
    if driver_number is None:
        return SpatialDriverState(
            race_id=race_id, driver_number=None, driver_id=driver_id,
            query_time_s=query_time, observation_time_s=None, age_s=None,
            availability=SC.AVAILABILITY_UNAVAILABLE, raw_x=None,
            raw_y=None, render_x=None, render_y=None, source=None,
            status=None)
    if isinstance(driver_number, bool) \
            or not isinstance(driver_number, (int, float)):
        raise SpatialResolutionError(
            f"driver_number must be numeric, got {driver_number!r}")
    if isinstance(driver_number, float):
        if not driver_number.is_integer():
            raise SpatialResolutionError(
                f"driver_number must be integral, got {driver_number!r}")
        driver_number = int(driver_number)
    series = store.series_for(int(driver_number))
    if series is None or len(series.times) == 0:
        return SpatialDriverState(
            race_id=race_id, driver_number=int(driver_number),
            driver_id=driver_id, query_time_s=query_time,
            observation_time_s=None, age_s=None,
            availability=SC.AVAILABILITY_UNAVAILABLE, raw_x=None,
            raw_y=None, render_x=None, render_y=None, source=None,
            status=None)
    position = _causal_index(series.times, query_time)
    if position < 0:
        return SpatialDriverState(
            race_id=race_id, driver_number=int(driver_number),
            driver_id=driver_id, query_time_s=query_time,
            observation_time_s=None, age_s=None,
            availability=SC.AVAILABILITY_UNAVAILABLE, raw_x=None,
            raw_y=None, render_x=None, render_y=None, source=None,
            status=None)
    observation_time = float(series.times[position])
    if observation_time > query_time:
        raise SpatialResolutionError(
            f"race {race_id!r} driver {driver_number!r}: causal lookup "
            f"selected a future observation ({observation_time!r} > "
            f"{query_time!r})")
    age = query_time - observation_time
    if age < 0:
        raise SpatialResolutionError(
            f"race {race_id!r} driver {driver_number!r}: negative age "
            f"implies future information ({age!r})")
    availability = SC.classify_availability(age)
    if availability == SC.AVAILABILITY_UNAVAILABLE:
        return SpatialDriverState(
            race_id=race_id, driver_number=int(driver_number),
            driver_id=driver_id, query_time_s=query_time,
            observation_time_s=observation_time, age_s=age,
            availability=availability, raw_x=None, raw_y=None,
            render_x=None, render_y=None, source=None, status=None)
    raw_x = int(series.x[position])
    raw_y = int(series.y[position])
    render_x: float | None = None
    render_y: float | None = None
    outside = False
    if store.transform is not None:
        from raceintel.spatial import geometry as G

        rendered = G.apply_transform(
            np.array([[float(raw_x), float(raw_y)]]), store.transform)
        render_x, render_y = float(rendered[0, 0]), float(rendered[0, 1])
        outside = bool(render_x < 0 or render_x > 1
                       or render_y < 0 or render_y > 1)
    return SpatialDriverState(
        race_id=race_id, driver_number=int(driver_number),
        driver_id=driver_id, query_time_s=query_time,
        observation_time_s=observation_time, age_s=age,
        availability=availability, raw_x=raw_x, raw_y=raw_y,
        render_x=render_x, render_y=render_y,
        source=(None if series.source[position] is None
                else str(series.source[position])),
        status=(None if series.status[position] is None
                else str(series.status[position])),
        outside_viewport=outside)


# ---------------------------------------------------------------------------
# Frame resolution (Part W)
# ---------------------------------------------------------------------------

def _check_universe(universe: tuple) -> tuple:
    """Validate one-to-one (driver_number <-> driver_id) identity."""
    entries = []
    for item in universe:
        if isinstance(item, DriverUniverseEntry):
            entries.append(item)
        elif isinstance(item, dict):
            entries.append(DriverUniverseEntry(
                driver_number=item.get("driver_number"),
                driver_id=item.get("driver_id")))
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            entries.append(DriverUniverseEntry(driver_number=item[0],
                                               driver_id=item[1]))
        else:
            raise SpatialIdentityError(
                f"universe entries must be DriverUniverseEntry/dict/pair, "
                f"got {item!r}")
    seen_numbers: dict[int, str | None] = {}
    seen_ids: dict[str, int | None] = {}
    for entry in entries:
        if entry.driver_number is not None:
            owner = seen_numbers.setdefault(entry.driver_number,
                                            entry.driver_id)
            if owner != entry.driver_id:
                raise SpatialIdentityError(
                    f"ambiguous identity: driver_number "
                    f"{entry.driver_number!r} maps to both "
                    f"{owner!r} and {entry.driver_id!r}")
        if entry.driver_id is not None:
            owner = seen_ids.setdefault(entry.driver_id,
                                        entry.driver_number)
            if owner != entry.driver_number:
                raise SpatialIdentityError(
                    f"ambiguous identity: driver_id {entry.driver_id!r} "
                    f"maps to both {owner!r} and "
                    f"{entry.driver_number!r}")
    return tuple(entries)


def resolve_frame(store: RaceSpatialStore, query_time_s: float,
                  universe: tuple | None = None, *,
                  require_geometry: bool = True) -> SpatialFrame:
    """Resolve a deterministic multi-driver frame at ``T``.

    ``universe`` is the authoritative replay roster (see
    :func:`universe_from_race_state`); caller order is preserved as the
    frame order. Without a universe (observation-only mode, tests and
    tooling), drivers are the sorted observation driver numbers.
    ``require_geometry=True`` fails closed for render-space frames when
    geometry is absent or stale; ``False`` yields a raw-only frame.
    """
    query_time = require_query_time(query_time_s)
    if require_geometry and not store.geometry_ok:
        if store.geometry_stale:
            raise SpatialGeometryMismatchError(store.geometry_problem
                                               or "stale geometry")
        raise SpatialArtifactUnavailableError(store.geometry_problem
                                              or "no geometry")
    if universe is None:
        entries = tuple(DriverUniverseEntry(driver_number=number)
                        for number in store.driver_numbers)
    else:
        entries = _check_universe(tuple(universe))
    states = tuple(resolve_driver(store, entry.driver_number, query_time,
                                  driver_id=entry.driver_id)
                   for entry in entries)
    fresh = sum(state.availability == SC.AVAILABILITY_FRESH
                for state in states)
    stale = sum(state.availability == SC.AVAILABILITY_STALE
                for state in states)
    return SpatialFrame(
        race_id=store.race_id, query_time_s=query_time,
        observation_content_sha256=store.observation_content_sha256,
        geometry_sha256=store.geometry_sha256, drivers=states,
        fresh_count=fresh, stale_count=stale,
        unavailable_count=len(states) - fresh - stale)


# ---------------------------------------------------------------------------
# Causal window (Parts X/Y)
# ---------------------------------------------------------------------------

def resolve_window(store: RaceSpatialStore, driver_number: int,
                   query_time_s: float, history_s: float) -> tuple:
    """Causal trajectory window ``[T - history, T]`` for one driver.

    Historical samples only: every returned sample satisfies
    ``sample_time <= T`` and ``sample_time >= T - history``. No future
    endpoint, no interpolation — future P12-5/P12-6 trail rendering
    consumes already-known samples only.
    """
    query_time = require_query_time(query_time_s)
    window = require_history_window(history_s)
    if isinstance(driver_number, bool) \
            or not isinstance(driver_number, (int, float)):
        raise SpatialResolutionError(
            f"driver_number must be numeric, got {driver_number!r}")
    series = store.series_for(int(driver_number))
    if series is None or len(series.times) == 0:
        return ()
    start = query_time - window
    stop = _causal_index(series.times, query_time)
    begin = int(np.searchsorted(series.times, start, side="left"))
    samples: list[TrajectorySample] = []
    transform = store.transform
    for position in range(begin, stop + 1):
        sample_time = float(series.times[position])
        if sample_time > query_time or sample_time < start:
            raise SpatialResolutionError(
                f"race {store.race_id!r} driver {driver_number!r}: "
                f"window leaked outside [T-history, T]")
        raw_x = int(series.x[position])
        raw_y = int(series.y[position])
        render_x: float | None = None
        render_y: float | None = None
        if transform is not None:
            from raceintel.spatial import geometry as G

            rendered = G.apply_transform(
                np.array([[float(raw_x), float(raw_y)]]), transform)
            render_x, render_y = (float(rendered[0, 0]),
                                  float(rendered[0, 1]))
        samples.append(TrajectorySample(
            observation_time_s=sample_time, raw_x=raw_x, raw_y=raw_y,
            render_x=render_x, render_y=render_y))
    return tuple(samples)

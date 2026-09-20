"""Phase-5 R1 replay timeline + frame domain (factual, lightweight).

Converts canonical historical observations for ONE race into a
deterministic ``ReplayTimeline``: one ``ReplayFrame`` per exact unique
``state_time_s``, each frame carrying the exact Phase-4 anchor identity
the frozen ``RaceStateReconstructor`` will resolve later (R2).

Deliberately reconstruction-free, model-free, API-free, storage-free.
The builder reads ONLY the four factual identity/time columns
(race/driver identity, driver progress, historical time); label, outcome,
future, and model columns are never read (firewall by allowlist
projection). No epsilon grouping, no rounding, no resampling.

Serving scope note: this builder is intentionally season-agnostic — it
receives one race's observations and derives a timeline. The 2018–2024
serving policy (2025 excluded) is enforced at the service/API boundary
(``api/v2_service.py`` ``SERVED_SEASONS``; R4 replay routes follow suit),
not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from v2.race_state import AnchorObservation

#: Phase-5 replay timeline semantics version. Participates in future
#: prediction/cache invalidation. Never a generic version framework.
REPLAY_CONTRACT_VERSION = "v1"

#: Canonical observation columns the builder reads. Nothing else is
#: touched, so outcome/future/label columns cannot influence the timeline.
REQUIRED_COLUMNS = frozenset({
    "race_id", "driver_id", "lap_number", "state_time_s",
})


class ReplayTimelineError(ValueError):
    """Malformed replay input or timeline (never an HTTP code)."""


def _req_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayTimelineError(
            f"{name} must be a non-empty canonical identity string, "
            f"got {value!r}")
    return value


def _req_frame_index(value: object) -> int:
    if type(value) is not int:
        raise ReplayTimelineError(
            f"frame_index must be a plain Python int, got {value!r}")
    if value < 0:
        raise ReplayTimelineError(
            f"frame_index must be >= 0, got {value!r}")
    return value


def _req_lap(value: object) -> int:
    if type(value) is not int:
        raise ReplayTimelineError(
            f"anchor_lap_number must be a plain Python int, got {value!r}")
    if value < 1:
        raise ReplayTimelineError(
            f"anchor_lap_number must be >= 1, got {value!r}")
    return value


def _req_time(value: object) -> float:
    if type(value) not in (int, float):
        raise ReplayTimelineError(
            f"anchor_state_time_s must be a finite plain Python number, "
            f"got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ReplayTimelineError(
            f"anchor_state_time_s must be finite (no NaN/Infinity), "
            f"got {value!r}")
    return result


@dataclass(frozen=True)
class ReplayFrame:
    """One factual replay frame: exact Phase-4 anchor identity + position.

    Carries NO ``RaceState``, NO features, NO predictions, NO labels —
    only the identity R2 needs to reconstruct the factual state later.
    """

    race_id: str
    frame_index: int
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    replay_contract_version: str = REPLAY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        object.__setattr__(self, "frame_index",
                            _req_frame_index(self.frame_index))
        object.__setattr__(self, "anchor_driver_id",
                            _req_id(self.anchor_driver_id,
                                     "anchor_driver_id"))
        object.__setattr__(self, "anchor_lap_number",
                            _req_lap(self.anchor_lap_number))
        object.__setattr__(self, "anchor_state_time_s",
                            _req_time(self.anchor_state_time_s))
        version = _req_id(self.replay_contract_version,
                          "replay_contract_version")
        if version != REPLAY_CONTRACT_VERSION:
            raise ReplayTimelineError(
                f"unsupported replay_contract_version {version!r} "
                f"(this module supports {REPLAY_CONTRACT_VERSION!r})")
        object.__setattr__(self, "replay_contract_version", version)

    def to_anchor(self) -> AnchorObservation:
        """Exact frozen Phase-4 anchor (no lookup, no rounding, no T edit)."""
        return AnchorObservation(
            race_id=self.race_id,
            anchor_driver_id=self.anchor_driver_id,
            anchor_lap_number=self.anchor_lap_number,
            anchor_state_time_s=self.anchor_state_time_s,
        )

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "frame_index": self.frame_index,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "anchor_state_time_s": self.anchor_state_time_s,
            "replay_contract_version": self.replay_contract_version,
        }


@dataclass(frozen=True)
class ReplayTimeline:
    """Immutable ordered replay frames for one race.

    The constructor validates but NEVER reorders: malformed timelines
    fail loudly. The builder (``build_replay_timeline``) owns sorting.
    """

    race_id: str
    replay_contract_version: str
    frames: tuple

    def __post_init__(self) -> None:
        race_id = _req_id(self.race_id, "race_id")
        object.__setattr__(self, "race_id", race_id)
        version = _req_id(self.replay_contract_version,
                          "replay_contract_version")
        if version != REPLAY_CONTRACT_VERSION:
            raise ReplayTimelineError(
                f"unsupported replay_contract_version {version!r}")
        object.__setattr__(self, "replay_contract_version", version)
        entries = list(self.frames) if self.frames is not None else []
        if not entries:
            raise ReplayTimelineError(
                "ReplayTimeline requires at least one frame")
        for entry in entries:
            if not isinstance(entry, ReplayFrame):
                raise ReplayTimelineError(
                    "ReplayTimeline.frames must contain only ReplayFrame, "
                    f"got {entry!r}")
            if entry.race_id != race_id:
                raise ReplayTimelineError(
                    f"frame race {entry.race_id!r} != timeline race "
                    f"{race_id!r}")
            if entry.replay_contract_version != version:
                raise ReplayTimelineError(
                    "frame contract version "
                    f"{entry.replay_contract_version!r} != timeline "
                    f"version {version!r}")
        indices = [entry.frame_index for entry in entries]
        if indices != list(range(len(entries))):
            raise ReplayTimelineError(
                "frame_index must be dense 0..N-1 in order, "
                f"got {indices!r}")
        times = [entry.anchor_state_time_s for entry in entries]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ReplayTimelineError(
                "anchor_state_time_s must strictly increase along the "
                "timeline")
        object.__setattr__(self, "frames", tuple(entries))

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def first(self) -> ReplayFrame:
        return self.frames[0]

    @property
    def last(self) -> ReplayFrame:
        return self.frames[-1]

    def frame_at(self, index: int) -> ReplayFrame:
        """Exact frame by index; raises on out-of-range (no wrap)."""
        if type(index) is not int:
            raise ReplayTimelineError(
                f"frame index must be a plain Python int, got {index!r}")
        if index < 0 or index >= len(self.frames):
            raise ReplayTimelineError(
                f"frame index {index!r} out of range "
                f"[0, {len(self.frames)})")
        return self.frames[index]

    def previous(self, index: int) -> ReplayFrame | None:
        """Frame before index, or None at the first frame (no wrap)."""
        if self.frame_at(index).frame_index == 0:
            return None
        return self.frames[index - 1]

    def next(self, index: int) -> ReplayFrame | None:
        """Frame after index, or None at the last frame (no wrap)."""
        self.frame_at(index)
        if index + 1 >= len(self.frames):
            return None
        return self.frames[index + 1]

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "replay_contract_version": self.replay_contract_version,
            "frame_count": self.frame_count,
            "frames": [entry.to_dict() for entry in self.frames],
        }


def _coerce_row(race_id: object, driver_id: object, lap: object,
                time_s: object) -> tuple:
    """Boundary coercion: pandas/numpy scalars -> plain Python values."""
    for value in (race_id, driver_id, lap, time_s):
        try:
            if value is None or bool(pd.isna(value)):
                raise ReplayTimelineError(
                    "timeline observations must not contain null "
                    "identity/time values")
        except (TypeError, ValueError) as exc:
            raise ReplayTimelineError(
                f"uncoercible timeline value {value!r}: {exc}") from None
    if not isinstance(race_id, str) or not race_id.strip():
        raise ReplayTimelineError(f"bad race_id {race_id!r}")
    if not isinstance(driver_id, str) or not driver_id.strip():
        raise ReplayTimelineError(f"bad driver_id {driver_id!r}")
    try:
        lap_int = int(lap)
    except (TypeError, ValueError) as exc:
        raise ReplayTimelineError(f"bad lap_number {lap!r}: {exc}") from None
    if isinstance(lap, float) and not lap.is_integer():
        raise ReplayTimelineError(
            f"lap_number must be integral, got {lap!r}")
    try:
        time_f = float(time_s)
    except (TypeError, ValueError) as exc:
        raise ReplayTimelineError(
            f"bad state_time_s {time_s!r}: {exc}") from None
    if not math.isfinite(time_f):
        raise ReplayTimelineError(
            f"state_time_s must be finite, got {time_s!r}")
    return race_id, driver_id, lap_int, time_f


def build_replay_timeline(states: pd.DataFrame) -> ReplayTimeline:
    """Derive the canonical replay timeline for exactly one race.

    1. validate required columns; 2. exactly one race_id; 3. coerce +
       validate identity/time values; 4. group by EXACT ``state_time_s``
       (no epsilon, no rounding); 5. sort unique T ascending; 6. within
       each T-group sort candidates by (lap_number ASC, driver_id ASC);
       7. first candidate wins; 8. dense ``frame_index`` 0..N-1.

    Exact-duplicate canonical identity rows are data-contract corruption
    and are rejected (the served corpus contains zero such rows).
    """
    if not isinstance(states, pd.DataFrame):
        raise ReplayTimelineError(
            f"states must be a canonical DataFrame, got {type(states)}")
    missing = sorted(REQUIRED_COLUMNS - set(states.columns))
    if missing:
        raise ReplayTimelineError(
            f"state frame is missing required columns: {missing}")
    if len(states) == 0:
        raise ReplayTimelineError("cannot build a timeline from no rows")
    # Allowlist projection: label/future/model columns are never read.
    frame = states[[c for c in
                    ("race_id", "driver_id", "lap_number", "state_time_s")]]
    races = set()
    coerced: list[tuple] = []
    for row in frame.itertuples(index=False):
        race_id, driver_id, lap, time_s = _coerce_row(
            row.race_id, row.driver_id, row.lap_number, row.state_time_s)
        races.add(race_id)
        coerced.append((race_id, driver_id, lap, time_s))
    if len(races) != 1:
        raise ReplayTimelineError(
            f"timeline input must cover exactly one race, "
            f"got {sorted(races)!r}")
    race_id = next(iter(races))
    seen: set[tuple] = set()
    by_time: dict[float, list[tuple]] = {}
    for _, driver_id, lap, time_s in coerced:
        key = (driver_id, lap, time_s)
        if key in seen:
            raise ReplayTimelineError(
                f"duplicate canonical identity observation: "
                f"{(race_id, driver_id, lap, time_s)}")
        seen.add(key)
        by_time.setdefault(time_s, []).append((lap, driver_id))
    frames = []
    for index, time_s in enumerate(sorted(by_time)):
        # Representative rule: (lap_number ASC, driver_id ASC). Explicit
        # sort — never input/group/dict order.
        lap, driver = sorted(by_time[time_s])[0]
        frames.append(ReplayFrame(
            race_id=race_id,
            frame_index=index,
            anchor_driver_id=driver,
            anchor_lap_number=lap,
            anchor_state_time_s=time_s,
        ))
    return ReplayTimeline(
        race_id=race_id,
        replay_contract_version=REPLAY_CONTRACT_VERSION,
        frames=tuple(frames),
    )

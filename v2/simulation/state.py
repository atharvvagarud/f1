"""Phase-6 R1 simulation-domain contracts (structural, immutable).

"What distinct starting point does one future trajectory evolve from?" —
typed, frozen dataclasses with NO simulation kernel, NO pace/pit/reliability
model, NO RaceState adapter, NO Monte Carlo engine, and NO empirical
parameters.

R1 boundary: this module freezes *contracts*, not unvalidated scientific
assumptions. Every field that only becomes meaningful once R2–R6 exist
(pace baselines, latent pace offsets, pit plans, retirement laps, gaps) is
deliberately absent; later stages add typed, versioned seams instead of R1
inventing semantics. See ``docs/PHASE6_MONTE_CARLO_PLAN.md`` §5 and the R1
record appended there.

Time-T contract: Phase-6 R1 has NO adapter. Tests construct states
directly from already-resolved values. ``DriverSimState.lap_number`` is the
driver's OWN completed-lap count (lapped drivers are first-class, never
forced onto the leader's lap) and ``race_time_s`` is the driver's own
last-completed-lap clock. ``SimulationState.leader_laps_done`` is the
field's factual maximum at T, not a global clock imposed on everyone.

Scientific independence: this module imports only the stdlib, the frozen
Phase-1 track-state token vocabulary, and the frozen Phase-4
``WeatherState`` value object. It must never import ``v2.prediction``,
``v2.model_lab``, replay prediction artifacts, sklearn, pandas, FastAPI,
or the API layer (pinned by test).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from v2.d9schema import TRACK_STATE_TOKENS
from v2.race_state import WeatherState

from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)

#: Authoritative Phase-6 simulation contract version. Defined HERE once;
#: every other simulation module imports it rather than restating it. It
#: participates in deterministic identities and RNG domain separation.
SIMULATION_CONTRACT_VERSION = "v1"


# ---------------------------------------------------------------------------
# Provenance vocabulary (R0 §23).
# ---------------------------------------------------------------------------

class Provenance(str, Enum):
    """Stable scientific-source taxonomy for simulation inputs.

    Exactly one tag per important input/parameter. It is NOT attached to
    every scalar: R1 uses it where the source materially changes meaning
    (e.g. ``Assumptions`` are always ``USER_ASSUMPTION``), and later
    stages reuse the same controlled vocabulary for estimated parameters
    (``HISTORICALLY_ESTIMATED``) and drawn quantities
    (``STOCHASTIC_DRAW``).
    """

    FACTUAL_AT_T = "FACTUAL_AT_T"
    HISTORICALLY_ESTIMATED = "HISTORICALLY_ESTIMATED"
    STOCHASTIC_DRAW = "STOCHASTIC_DRAW"
    USER_ASSUMPTION = "USER_ASSUMPTION"
    ORACLE_EVALUATION_ONLY = "ORACLE_EVALUATION_ONLY"


def provenance_value(value: object, name: str = "provenance") -> Provenance:
    """Coerce a controlled provenance value; reject anything else.

    Accepts the enum member or its exact string value. Free-form strings
    are rejected so a contract expecting a controlled provenance token
    can never silently accept an invented category.
    """
    if isinstance(value, Provenance):
        return value
    if isinstance(value, str):
        try:
            return Provenance(value)
        except ValueError:
            pass
    raise SimulationContractError(
        f"{name} must be one of "
        f"{[member.value for member in Provenance]}, got {value!r}")


class DriverStatus(str, Enum):
    """Structural participant status (R1-J).

    Retirement is a *simulated* state, never inferred from staleness or
    missing observations. R1 represents ACTIVE and RETIRED only; the
    reliability hazard that transitions between them belongs to R6.
    """

    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


def driver_status_value(value: object, name: str = "status") -> DriverStatus:
    """Coerce a controlled driver-status value; reject anything else."""
    if isinstance(value, DriverStatus):
        return value
    if isinstance(value, str):
        try:
            return DriverStatus(value)
        except ValueError:
            pass
    raise SimulationContractError(
        f"{name} must be one of "
        f"{[member.value for member in DriverStatus]}, got {value!r}")


# ---------------------------------------------------------------------------
# Canonical deterministic serialization / hashing (R1-AC, R1-R).
# ---------------------------------------------------------------------------

def canonical_json(payload: object) -> str:
    """Deterministic JSON: sorted keys, compact separators, no NaN/Inf.

    Same semantic object -> byte-identical string. Primitive values only;
    callers own their ``to_dict`` projections.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def canonical_sha256(payload: object) -> str:
    """SHA-256 over the canonical JSON serialization of ``payload``."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validation helpers (stdlib exact-type guards; numpy/pandas rejected).
# ---------------------------------------------------------------------------

def _req_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SimulationValidationError(
            f"{name} must be a non-empty canonical identity string, "
            f"got {value!r}")
    return value


def _req_int(value: object, name: str, minimum: int | None = None) -> int:
    # Exact-type check (not isinstance): numpy/pandas integer scalars and
    # bools are rejected structurally; callers coerce via int().
    if type(value) is not int:
        raise SimulationContractError(
            f"{name} must be a plain Python int (coerce numpy via int()), "
            f"got {value!r}")
    if minimum is not None and value < minimum:
        raise SimulationValidationError(
            f"{name} must be >= {minimum}, got {value!r}")
    return value


def _req_float(value: object, name: str, minimum: float | None = None) -> float:
    # Exact-type check: numpy floating scalars subclass Python float, so
    # isinstance would leak them; callers coerce via float().
    if type(value) not in (int, float):
        raise SimulationContractError(
            f"{name} must be a finite plain Python number "
            f"(coerce numpy via float()), got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SimulationValidationError(
            f"{name} must be finite (no NaN/Infinity), got {value!r}")
    if minimum is not None and result < minimum:
        raise SimulationValidationError(
            f"{name} must be >= {minimum}, got {value!r}")
    return result


def _req_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise SimulationContractError(
            f"{name} must be a plain Python bool, got {value!r}")
    return value


def _opt_id(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _req_id(value, name)


def _opt_int(value: object, name: str,
             minimum: int | None = None) -> int | None:
    if value is None:
        return None
    return _req_int(value, name, minimum=minimum)


def _opt_float(value: object, name: str,
               minimum: float | None = None) -> float | None:
    if value is None:
        return None
    return _req_float(value, name, minimum=minimum)


def _req_contract_version(value: object) -> str:
    version = _req_id(value, "simulation_contract_version")
    if version != SIMULATION_CONTRACT_VERSION:
        raise SimulationContractError(
            f"unsupported simulation_contract_version {version!r} "
            f"(this module supports {SIMULATION_CONTRACT_VERSION!r})")
    return version


# ---------------------------------------------------------------------------
# Environment contract (R1-K): only fields justified by frozen RaceState.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationEnvironment:
    """Environmental conditions held for a trajectory.

    ``track_state`` is the frozen Phase-1 contemporaneous token (verbatim:
    ``all_clear | yellow | safety_car | red_flag | vsc | vsc_ending`` or
    None when unknown). The frozen ``flag_*`` booleans are deliberately NOT
    duplicated here — they are a deterministic view of the same token, and
    two sources of truth invite drift.

    ``weather`` reuses the frozen Phase-4 ``WeatherState`` (strict backward
    as-of, null-preserving). R1 holds weather fixed; evolving/forecast
    weather is DEFERRED and any future oracle input must be explicitly
    labelled ``ORACLE_EVALUATION_ONLY`` at its own seam, never hidden here.
    """

    track_state: str | None = None
    weather: WeatherState | None = None

    def __post_init__(self) -> None:
        track_state = self.track_state
        if track_state is not None:
            if not isinstance(track_state, str):
                raise SimulationContractError(
                    f"track_state must be a string or None, "
                    f"got {track_state!r}")
            if track_state not in TRACK_STATE_TOKENS:
                raise SimulationValidationError(
                    f"track_state must be one of {TRACK_STATE_TOKENS} or "
                    f"None, got {track_state!r}")
        if self.weather is not None \
                and not isinstance(self.weather, WeatherState):
            raise SimulationContractError(
                f"weather must be a WeatherState or None, "
                f"got {self.weather!r}")

    def to_dict(self) -> dict:
        return {
            "track_state": self.track_state,
            "weather": None if self.weather is None
            else self.weather.to_dict(),
        }


# ---------------------------------------------------------------------------
# Per-driver starting/mutable state (R1-E, R1-F).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriverSimState:
    """One roster member's own trajectory state.

    Required, non-speculative fields only:
    - ``lap_number``: completed laps (OWN progress; 0 allowed at a start
      boundary). Lapped drivers legitimately carry a lower count.
    - ``race_time_s``: OWN last-completed-lap clock (finite, >= 0).
    - ``position``: factual classified order at T, nullable; NOT required
      to be unique (frozen evidence measures multi-holder positions during
      pit cycles; it is a classification, not physical state).
    - ``compound`` / ``tyre_age`` / ``stint_number`` / ``pit_count``:
      tyre and pit bookkeeping. ``tyre_age`` is nullable because the
      frozen RaceState represents an unrecorded tyre age as null; null
      must stay distinct from a factual zero (R2-Z refinement).
    - ``constructor_id``: identity.
    - ``status``: ACTIVE or RETIRED (explicit; never inferred).
    - ``observation_age_s``: staleness metadata (>= 0), kept separate from
      ``status`` so an ACTIVE-but-stale driver is structurally possible.

    Deliberately absent until their owning stage: pace baselines and
    latent pace offsets (R3/R4), pit plans (R6), gaps (derived from
    race_time), retirement laps (R6), and any fuel/damage/penalty state
    with no frozen source.
    """

    driver_id: str
    lap_number: int
    race_time_s: float
    position: int | None = None
    compound: str | None = None
    tyre_age: int | None = None
    stint_number: int | None = None
    pit_count: int = 0
    constructor_id: str | None = None
    status: DriverStatus = DriverStatus.ACTIVE
    observation_age_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "driver_id",
                            _req_id(self.driver_id, "driver_id"))
        object.__setattr__(self, "lap_number",
                            _req_int(self.lap_number, "lap_number",
                                     minimum=0))
        object.__setattr__(self, "race_time_s",
                            _req_float(self.race_time_s, "race_time_s",
                                       minimum=0.0))
        object.__setattr__(self, "position",
                            _opt_int(self.position, "position", minimum=1))
        object.__setattr__(self, "compound",
                            _opt_id(self.compound, "compound"))
        object.__setattr__(self, "tyre_age",
                            _opt_int(self.tyre_age, "tyre_age", minimum=0))
        object.__setattr__(self, "stint_number",
                            _opt_int(self.stint_number, "stint_number",
                                     minimum=1))
        object.__setattr__(self, "pit_count",
                            _req_int(self.pit_count, "pit_count",
                                     minimum=0))
        object.__setattr__(self, "constructor_id",
                            _opt_id(self.constructor_id, "constructor_id"))
        object.__setattr__(self, "status",
                            driver_status_value(self.status))
        object.__setattr__(self, "observation_age_s",
                            _opt_float(self.observation_age_s,
                                       "observation_age_s", minimum=0.0))

    def to_dict(self) -> dict:
        return {
            "driver_id": self.driver_id,
            "lap_number": self.lap_number,
            "race_time_s": self.race_time_s,
            "position": self.position,
            "compound": self.compound,
            "tyre_age": self.tyre_age,
            "stint_number": self.stint_number,
            "pit_count": self.pit_count,
            "constructor_id": self.constructor_id,
            "status": self.status.value,
            "observation_age_s": self.observation_age_s,
        }


# ---------------------------------------------------------------------------
# Snapshot root (R1-E, R1-G, R1-I).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationState:
    """Immutable starting state for R2+ to adapt and R4+ to evolve.

    ``drivers`` holds one entry per participant in canonical ``driver_id``
    order (never input/dict order). ``scheduled_laps`` is the PRE_RACE
    distance; ``leader_laps_done`` is the factual maximum completed laps at
    T and each driver's own ``lap_number`` must not exceed it (lapped
    drivers are lower, never forced equal). ``anchor_frame_index`` is the
    optional Phase-5 replay handle that originated the state.

    Frozen boundary: evolution uses ``dataclasses.replace``/copy-on-write,
    never in-place mutation, so this type stays a value.
    """

    race_id: str
    scheduled_laps: int
    leader_laps_done: int
    simulation_time_s: float
    drivers: tuple
    environment: SimulationEnvironment
    season: int | None = None
    round_no: int | None = None
    circuit_id: str | None = None
    anchor_frame_index: int | None = None
    simulation_contract_version: str = SIMULATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        object.__setattr__(self, "scheduled_laps",
                            _req_int(self.scheduled_laps, "scheduled_laps",
                                     minimum=1))
        object.__setattr__(self, "leader_laps_done",
                            _req_int(self.leader_laps_done,
                                     "leader_laps_done", minimum=0))
        if self.leader_laps_done > self.scheduled_laps:
            raise SimulationValidationError(
                "leader_laps_done must not exceed scheduled_laps, "
                f"got {self.leader_laps_done!r} > "
                f"{self.scheduled_laps!r}")
        object.__setattr__(self, "simulation_time_s",
                            _req_float(self.simulation_time_s,
                                       "simulation_time_s", minimum=0.0))

        entries = list(self.drivers) if self.drivers is not None else []
        if not entries:
            raise SimulationContractError(
                "SimulationState requires a non-empty driver collection")
        for entry in entries:
            if not isinstance(entry, DriverSimState):
                raise SimulationContractError(
                    "SimulationState.drivers must contain only "
                    f"DriverSimState, got {entry!r}")
        ids = [entry.driver_id for entry in entries]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise SimulationContractError(
                f"duplicate driver entries: {duplicates}")
        for entry in entries:
            if entry.lap_number > self.leader_laps_done:
                raise SimulationValidationError(
                    f"driver {entry.driver_id!r} lap_number "
                    f"{entry.lap_number!r} exceeds leader_laps_done "
                    f"{self.leader_laps_done!r}")
        # Canonical, deterministic ordering — never input/dict order.
        entries = sorted(entries, key=lambda entry: entry.driver_id)
        object.__setattr__(self, "drivers", tuple(entries))

        if not isinstance(self.environment, SimulationEnvironment):
            raise SimulationContractError(
                f"environment must be a SimulationEnvironment, "
                f"got {self.environment!r}")
        object.__setattr__(self, "season",
                            _opt_int(self.season, "season", minimum=0))
        object.__setattr__(self, "round_no",
                            _opt_int(self.round_no, "round_no", minimum=1))
        object.__setattr__(self, "circuit_id",
                            _opt_id(self.circuit_id, "circuit_id"))
        object.__setattr__(self, "anchor_frame_index",
                            _opt_int(self.anchor_frame_index,
                                     "anchor_frame_index", minimum=0))
        object.__setattr__(self, "simulation_contract_version",
                            _req_contract_version(
                                self.simulation_contract_version))

    @property
    def roster_driver_ids(self) -> tuple:
        """Every participant, canonical ``driver_id`` order."""
        return tuple(entry.driver_id for entry in self.drivers)

    @property
    def roster_size(self) -> int:
        return len(self.drivers)

    @property
    def driver_by_id(self) -> dict:
        return {entry.driver_id: entry for entry in self.drivers}

    def identity(self) -> str:
        """Deterministic SHA-256 identity of this immutable starting state.

        R1-S decision: the state DOES require its own identity because the
        request identity is a function of the starting state. It hashes the
        canonical immutable representation only — never a timestamp,
        hostname, PID, UUID, or memory address. Semantically unordered
        input (driver input order) is canonicalized before hashing.
        """
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            "simulation_contract_version": self.simulation_contract_version,
            "race_id": self.race_id,
            "season": self.season,
            "round_no": self.round_no,
            "circuit_id": self.circuit_id,
            "anchor_frame_index": self.anchor_frame_index,
            "scheduled_laps": self.scheduled_laps,
            "leader_laps_done": self.leader_laps_done,
            "simulation_time_s": self.simulation_time_s,
            "roster_size": self.roster_size,
            "roster_driver_ids": list(self.roster_driver_ids),
            "drivers": [entry.to_dict() for entry in self.drivers],
            "environment": self.environment.to_dict(),
        }

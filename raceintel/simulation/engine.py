"""Phase-6 R4 deterministic race-evolution kernel.

Given an immutable :class:`~v2.simulation.state.SimulationState` at time ``T``,
a validated :class:`~v2.simulation.params.SimulationParameterSet`, and a
zero-noise execution, advance the race lap by lap to a structurally valid
finishing classification. R4 is the *deterministic baseline* kernel that R5
will stochastically replicate and vectorize.

What R4 is
----------
- a compact mutable internal representation (small dataclasses), never a
  mutation of the immutable ``SimulationState``;
- event-driven lap stepping: the driver whose current lap completes first is
  advanced next, so cumulative race-time ordering and lapped-car semantics are
  preserved (a driver is never forced onto the leader's lap);
- deterministic expected pace from the R3-adopted subset only;
- race completion the moment the leader completes ``scheduled_laps``;
- ordering derived from simulated ``(laps_completed DESC, race_time_s ASC,
  driver_id ASC)`` (``free-air`` deterministic ordering, NOT an overtaking
  simulation);
- a validated :class:`~v2.simulation.results.SimulationRunResult` with an
  explicit unsupported/rejection taxonomy for states R4 cannot honestly evolve.

What R4 is NOT (all owned by later stages)
------------------------------------------
No lap noise, no Monte Carlo aggregation, no pit decision/stop/compound
change, no traffic penalty, no overtaking probability, no reliability hazard,
no retirements, no SC/VSC generation, no red-flag restart, no weather
evolution, no strategy/what-if, no API/frontend, and no canonical-data,
winner-model, feature-engine, or replay-prediction access at run time.

Adopted R3 parameter subset (R4-A)
----------------------------------
Only effects R3 explicitly marked usable and that are deterministic:
``pace_base_s`` (with ``pace_base_fallback_s``), ``constructor_pace_offset_s``,
``race_progress_slope_s_per_lap``, and ``degradation_slope_s_per_lap``. The
R3 residual distribution is NOT used (R4 is deterministic). ``compound_offset_s``
is ``deferred`` and MUST NOT be invented. Pit/stint/transition parameters
belong to R6.

Pace anchor decision (R4-I)
---------------------------
``SimulationState`` deliberately carries no lap-time history (R2 did not
bypass ``RaceState``), so no driver-specific factual pace anchor exists in the
R4 inputs. R4 therefore uses the defensible R3 baseline hierarchy
(circuit|era base + constructor relative offset) without a driver-specific
current-pace term (option C). A past-only pace-context seam is NOT added. This
is a documented R4 limitation: two drivers of the same constructor share a
pace anchor.

Expected pace (R4-K/L/M), with the R0 §8 delta-from-T form::

    mu_i(l) = base(circuit, era) + constructor_offset
            + progress_slope * (l - reference_lap)
            + degradation_slope * (clamp(age) - clamp(anchor_age))

``reference_lap`` is the factual leader progress at ``T`` (the race's current
progress); the driver's own factual tyre age at ``T`` anchors degradation. Both
terms are deltas from the anchor, so the era-average trend already embedded in
the R3 base is not re-applied from lap 0. No residual draw, no compound delta,
no traffic/pit/reliability term.

Dependency direction: imports only the stdlib and the Phase-6 simulation
contracts (``errors``/``state``/``params``/``results``). It imports no pandas,
no ``v2.race_state``, no ``v2.replay*``, no feature engine, no
``v2.model_lab``/``v2.prediction``, and no API code (pinned by AST test).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional

from raceintel.simulation.errors import (
    SimulationContractError,
    SimulationError,
    SimulationValidationError,
)
from raceintel.simulation.params import WET_COMPOUNDS, SimulationParameterSet
from raceintel.simulation.results import (
    DriverFinish,
    FinishOrder,
    SimulationRunResult,
)
from raceintel.simulation.state import (
    DriverStatus,
    SimulationState,
)

__all__ = [
    "ENGINE_VERSION",
    "SUPPORTED_TRACK_STATES",
    "ENGINE_UNSUPPORTED_REASONS",
    "INVALID_RUN_REASONS",
    "CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES",
    "ExecutionPolicy",
    "SimulationUnsupportedError",
    "SelectedParameter",
    "PaceParameterSelection",
    "select_pace_parameters",
    "expected_lap_time_s",
    "contemporaneous_roster_offenders",
    "max_lap_events",
    "DeterministicRaceEngine",
]

#: Kernel logic version (structural identity of the evolution semantics).
ENGINE_VERSION = "r4-engine-v1"

#: Track states the R4 dry deterministic kernel supports as an anchor.
SUPPORTED_TRACK_STATES = ("all_clear",)

#: R3 regulation eras (mirrors ``estimator.ERAS`` without importing pandas).
ERA_BOUNDS = ((2018, 2021, "2018-2021"), (2022, 2024, "2022-2024"))

#: Family whose global observed maximum bounds the simulated tyre-age support.
AGE_SUPPORT_FAMILY = "stint_length_laps"

# Stable, API-mappable reasons why a factual SimulationState cannot be honestly
# evolved by the R4 kernel. Distinct from programming/contract errors.
REASON_RED_FLAG_TRACK_STATE = "red_flag_track_state"
REASON_NEUTRALIZED_TRACK_STATE = "neutralized_track_state"
REASON_UNKNOWN_TRACK_STATE = "unknown_track_state"
REASON_WET_TRACK_CONDITIONS = "wet_track_conditions"
REASON_WET_COMPOUND_STATE = "wet_compound_state"
REASON_MISSING_TYRE_AGE = "missing_tyre_age"
REASON_RETIRED_DRIVER = "retired_driver_unsupported"
REASON_MISSING_CIRCUIT_ID = "missing_circuit_id"
REASON_MISSING_SEASON = "missing_season"
REASON_UNSUPPORTED_SEASON = "unsupported_season"
REASON_PARAMETER_TEMPORAL_LEAK = "parameter_temporal_leak"
REASON_MISSING_PACE_PARAMETER = "missing_pace_parameter"
REASON_LEADER_PROGRESS_NOT_REPRESENTED = "leader_progress_not_represented"
REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER = "non_contemporaneous_roster_member"

ENGINE_UNSUPPORTED_REASONS = (
    REASON_RED_FLAG_TRACK_STATE,
    REASON_NEUTRALIZED_TRACK_STATE,
    REASON_UNKNOWN_TRACK_STATE,
    REASON_WET_TRACK_CONDITIONS,
    REASON_WET_COMPOUND_STATE,
    REASON_MISSING_TYRE_AGE,
    REASON_RETIRED_DRIVER,
    REASON_MISSING_CIRCUIT_ID,
    REASON_MISSING_SEASON,
    REASON_UNSUPPORTED_SEASON,
    REASON_PARAMETER_TEMPORAL_LEAK,
    REASON_MISSING_PACE_PARAMETER,
    REASON_LEADER_PROGRESS_NOT_REPRESENTED,
    REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER,
)

#: R7.1 simulation-start eligibility rule (evidence-derived, not a retirement
#: label). A driver's trajectory is advanced from its OWN factual
#: ``(lap_number, race_time_s)``; a driver whose latest observation is many
#: expected lap times older than the anchor T therefore "finishes" the
#: remaining distance from a stale clock and can beat the field (R7-BUG-2,
#: e.g. 2020-r07-R). A roster member observed within this many expected lap
#: times of T is treated as contemporaneously participating and evolved
#: normally.
#:
#: Derivation (R7.1-B/D): over the 99 raw R7 validation states the 1 836
#: drivers with a later observation (contemporaneous ground truth) have an
#: observation age with p50 0.62, p90 0.95, p95 1.11 and p99 1.77 expected
#: lap times; the 144 drivers with no later observation have a median age of
#: 21.4 and a minimum near the boundary. ``3.0`` is a conservative margin
#: (~1.7x the contemporaneous p99) above the observed contemporaneous
#: distribution and below the non-contemporaneous mass, expressed as a
#: dimensionless multiple of the circuit|era expected lap time. This is an
#: ELIGIBILITY bound: it never asserts retirement and never reads final
#: status, future rows, or any post-T information.
CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES = 3.0

# Reasons why a structurally valid run can still fail numerically mid-evolution.
# These produce ``SimulationRunResult(valid=False)`` so a later aggregation can
# count them explicitly, never a fabricated classification.
REASON_NONFINITE_LAP_TIME = "nonfinite_expected_lap_time"
REASON_NONPOSITIVE_LAP_TIME = "nonpositive_expected_lap_time"
REASON_NONFINITE_RACE_TIME = "nonfinite_race_time"
REASON_ITERATION_LIMIT = "iteration_limit_exceeded"

INVALID_RUN_REASONS = (
    REASON_NONFINITE_LAP_TIME,
    REASON_NONPOSITIVE_LAP_TIME,
    REASON_NONFINITE_RACE_TIME,
    REASON_ITERATION_LIMIT,
)


class ExecutionPolicy(str, Enum):
    """How a caller is allowed to interpret the parameter temporal window.

    ``RETROSPECTIVE_PRODUCT`` — normal product replay; the (possibly frozen
    production) parameter set may include the target season, and the run is a
    *retrospective* simulation, not a leakage-free backtest.

    ``HISTORICAL_BACKTEST`` — scientific evaluation; the parameter set MUST be
    estimated strictly before the evaluated target season so a caller can never
    accidentally treat future-estimated parameters as leakage-free.
    """

    RETROSPECTIVE_PRODUCT = "retrospective_product"
    HISTORICAL_BACKTEST = "historical_backtest"


class SimulationUnsupportedError(SimulationError):
    """The input state/parameters cannot be honestly evolved by R4.

    This is a factual/scientific incompatibility (red flag, wet pace, missing
    factual tyre age, temporal parameter leakage), not a programming error.
    ``reason`` is a stable token from :data:`ENGINE_UNSUPPORTED_REASONS`.
    """

    def __init__(self, reason: str, detail: str):
        if reason not in ENGINE_UNSUPPORTED_REASONS:
            raise SimulationContractError(
                f"unknown engine unsupported reason {reason!r}")
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class _NumericalFailure(Exception):
    """Internal control-flow signal for a mid-evolution numerical failure."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _era_for_season(season: int) -> str:
    for start, end, label in ERA_BOUNDS:
        if start <= season <= end:
            return label
    raise SimulationUnsupportedError(
        REASON_UNSUPPORTED_SEASON,
        f"season {season!r} is outside the R3 estimation eras 2018-2024")


# ---------------------------------------------------------------------------
# Parameter selection (R4-Z): the adopted subset + visible support/fallback.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectedParameter:
    """One selected R3 support entry plus its evidence metadata."""

    family: str
    key: str
    value: float
    support_level: str
    fallback_level: str
    identifiability: str

    def __post_init__(self) -> None:
        if type(self.value) not in (int, float):
            raise SimulationContractError(
                f"selected parameter {self.family} value must be numeric, "
                f"got {self.value!r}")
        result = float(self.value)
        if not math.isfinite(result):
            raise SimulationValidationError(
                f"selected parameter {self.family} value must be finite, "
                f"got {self.value!r}")
        object.__setattr__(self, "value", result)

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "key": self.key,
            "value": self.value,
            "support_level": self.support_level,
            "fallback_level": self.fallback_level,
            "identifiability": self.identifiability,
        }


@dataclass(frozen=True)
class PaceParameterSelection:
    """Deterministic R4 parameter selection for one starting state.

    Exposes exactly which R3 entries the kernel adopted (and their
    support/fallback level) so a weak/global fallback is inspectable and can
    never masquerade as a circuit-specific measurement.
    """

    era: str
    target_season: int
    parameter_through_season: int
    reference_lap: int
    age_support_max_laps: Optional[float]
    base: SelectedParameter
    constructor_offsets: Mapping[str, SelectedParameter]
    progress: SelectedParameter
    degradation: SelectedParameter

    @property
    def leakage_free(self) -> bool:
        """True when the parameters end strictly before the target season."""
        return self.parameter_through_season < self.target_season

    def offset_for(self, constructor_id: Optional[str]) -> SelectedParameter:
        """Per-driver constructor offset (falls back to the global zero)."""
        key = constructor_id if constructor_id is not None else ""
        return self.constructor_offsets.get(
            key, self.constructor_offsets[""])

    def to_dict(self) -> dict:
        return {
            "era": self.era,
            "target_season": self.target_season,
            "parameter_through_season": self.parameter_through_season,
            "reference_lap": self.reference_lap,
            "age_support_max_laps": self.age_support_max_laps,
            "leakage_free": self.leakage_free,
            "base": self.base.to_dict(),
            "constructor_offsets": {
                key: value.to_dict()
                for key, value in sorted(self.constructor_offsets.items())},
            "progress": self.progress.to_dict(),
            "degradation": self.degradation.to_dict(),
        }


def _first_entry(parameters: SimulationParameterSet, candidates):
    for family, key in candidates:
        entry = parameters.family(family).entries.get(key)
        if entry is not None and entry.value is not None:
            return family, key, entry
    return None


def _selected(family: str, key: str, entry) -> SelectedParameter:
    return SelectedParameter(
        family=family, key=key, value=entry.value,
        support_level=entry.support_level,
        fallback_level=entry.fallback_level,
        identifiability=entry.identifiability,
    )


def select_pace_parameters(initial_state: SimulationState,
                           parameters: SimulationParameterSet
                           ) -> PaceParameterSelection:
    """Choose the R4 parameter subset from the documented R3 hierarchy.

    Raises ``SimulationUnsupportedError`` for a missing circuit/season or a
    missing pace parameter, and ``SimulationContractError`` for wrong types.
    """
    if not isinstance(initial_state, SimulationState):
        raise SimulationContractError(
            f"initial_state must be a SimulationState, got {initial_state!r}")
    if not isinstance(parameters, SimulationParameterSet):
        raise SimulationContractError(
            "parameters must be a SimulationParameterSet, got "
            f"{parameters!r}")

    if initial_state.circuit_id is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_CIRCUIT_ID,
            f"race {initial_state.race_id!r} has no circuit_id at T")
    if initial_state.season is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_SEASON,
            f"race {initial_state.race_id!r} has no season at T")

    circuit = initial_state.circuit_id
    season = initial_state.season
    era = _era_for_season(season)

    base_candidates = [
        ("pace_base_s", f"{circuit}|{era}"),
        ("pace_base_fallback_s", circuit),
        ("pace_base_fallback_s", "global"),
    ]
    base = _first_entry(parameters, base_candidates)
    if base is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no pace base for circuit {circuit!r}/{era}")

    global_offset = parameters.family(
        "constructor_pace_offset_s").entries.get("global")
    if global_offset is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            "no constructor pace offset (not even the global zero fallback)")
    constructor_offsets: dict = {"": _selected(
        "constructor_pace_offset_s", "global", global_offset)}
    for entry in initial_state.drivers:
        constructor = entry.constructor_id
        if constructor is None or constructor in constructor_offsets:
            continue
        chosen = _first_entry(parameters, [
            ("constructor_pace_offset_s", f"{constructor}|{season}"),
            ("constructor_pace_offset_s", f"{constructor}|{era}"),
            ("constructor_pace_offset_s", "global"),
        ])
        constructor_offsets[constructor] = _selected(*chosen)

    progress = _first_entry(parameters, [
        ("race_progress_slope_s_per_lap", f"{circuit}|{era}"),
        ("race_progress_slope_s_per_lap", era),
        ("race_progress_slope_s_per_lap", "global"),
    ])
    if progress is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no race-progress slope for {circuit!r}/{era}")

    degradation = _first_entry(parameters, [
        ("degradation_slope_s_per_lap", era),
        ("degradation_slope_s_per_lap", "global"),
    ])
    if degradation is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no degradation slope for era {era!r}")

    age_support_max = None
    stint_global = parameters.family(AGE_SUPPORT_FAMILY).entries.get("global")
    if stint_global is not None:
        age_support_max = stint_global.observed_max

    return PaceParameterSelection(
        era=era,
        target_season=season,
        parameter_through_season=parameters.through_season,
        reference_lap=initial_state.leader_laps_done,
        age_support_max_laps=age_support_max,
        base=_selected(*base),
        constructor_offsets=constructor_offsets,
        progress=_selected(*progress),
        degradation=_selected(*degradation),
    )


def _clamp_age(age: float, support_max: Optional[float]) -> float:
    if age < 0.0:
        return 0.0
    if support_max is not None and age > support_max:
        return support_max
    return age


def expected_lap_time_s(selection: PaceParameterSelection, base_pace_s: float,
                        next_lap: int, next_age: float, anchor_age: float):
    """Deterministic expected lap time and its two deltas.

    ``base_pace_s`` is the driver's anchor pace (circuit|era base plus the
    constructor relative offset). Returns ``(mu, progress_adjustment_s,
    degradation_adjustment_s)``. The degradation delta is clamped to the
    observed age support so the effect is never extrapolated beyond the R3
    evidence.
    """
    progress_delta = next_lap - selection.reference_lap
    progress_adjustment = selection.progress.value * progress_delta
    age = _clamp_age(float(next_age), selection.age_support_max_laps)
    anchor = _clamp_age(float(anchor_age), selection.age_support_max_laps)
    degradation_adjustment = selection.degradation.value * (age - anchor)
    mu = base_pace_s + progress_adjustment + degradation_adjustment
    return mu, progress_adjustment, degradation_adjustment


# ---------------------------------------------------------------------------
# Start-state validation (R4-D/F/G/H/T).
# ---------------------------------------------------------------------------

def _validate_start_state(initial_state: SimulationState,
                          selection: PaceParameterSelection) -> None:
    environment = initial_state.environment
    track_state = environment.track_state
    if track_state == "red_flag":
        raise SimulationUnsupportedError(
            REASON_RED_FLAG_TRACK_STATE,
            "red-flag anchors are unsupported in R4 v1 (no restart model)")
    if track_state is not None and track_state != "all_clear":
        raise SimulationUnsupportedError(
            REASON_NEUTRALIZED_TRACK_STATE,
            f"track_state {track_state!r} is unsupported; R4 v1 evolves "
            f"only {SUPPORTED_TRACK_STATES[0]!r} anchors")
    if track_state is None:
        raise SimulationUnsupportedError(
            REASON_UNKNOWN_TRACK_STATE,
            "a null track_state is not a green condition and cannot be "
            "assumed all_clear")

    weather = environment.weather
    if weather is not None and weather.rainfall is True:
        raise SimulationUnsupportedError(
            REASON_WET_TRACK_CONDITIONS,
            "R3 dry pace parameters exclude rainfall laps; wet pace is "
            "DEFERRED")

    for entry in initial_state.drivers:
        if entry.status is not DriverStatus.ACTIVE:
            raise SimulationUnsupportedError(
                REASON_RETIRED_DRIVER,
                f"driver {entry.driver_id!r} is {entry.status.value}; R4 has "
                "no reliability/retirement dynamics")
        if entry.tyre_age is None:
            raise SimulationUnsupportedError(
                REASON_MISSING_TYRE_AGE,
                f"driver {entry.driver_id!r} has no factual tyre age; R4 does "
                "not fabricate one")
        if entry.compound in WET_COMPOUNDS:
            raise SimulationUnsupportedError(
                REASON_WET_COMPOUND_STATE,
                f"driver {entry.driver_id!r} is on {entry.compound!r}; wet "
                "pace semantics are DEFERRED")

    leader_laps = max(entry.lap_number for entry in initial_state.drivers)
    if leader_laps != initial_state.leader_laps_done:
        raise SimulationUnsupportedError(
            REASON_LEADER_PROGRESS_NOT_REPRESENTED,
            f"factual leader progress {initial_state.leader_laps_done!r} is "
            f"not represented by any driver (max lap {leader_laps!r})")

    _validate_contemporaneous(initial_state, selection)


def contemporaneous_roster_offenders(
        initial_state: SimulationState,
        base_pace_s: float) -> tuple:
    """Roster members whose latest factual observation is too old to evolve.

    Returns ``((driver_id, observation_age_s), ...)`` for every driver whose
    factual ``observation_age_s`` exceeds
    ``CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES`` expected lap times. A null
    observation age is not verifiably stale and is never an offender. This is
    a simulation-start ELIGIBILITY check (R7.1-F): it decides whether the
    factual start state is sufficient to initialize a future trajectory. It
    is never a retirement classification, never reads final status/future
    rows, and does not mutate the state.
    """
    if not math.isfinite(float(base_pace_s)) or float(base_pace_s) <= 0.0:
        # No usable race-relative scale: the kernel's own numerical guards
        # reject the run, so no contemporaneity conclusion is drawn here.
        return ()
    bound = CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES * float(base_pace_s)
    return tuple(
        (entry.driver_id, float(entry.observation_age_s))
        for entry in initial_state.drivers
        if entry.observation_age_s is not None
        and float(entry.observation_age_s) > bound
    )


def _validate_contemporaneous(initial_state: SimulationState,
                              selection: PaceParameterSelection) -> None:
    offenders = contemporaneous_roster_offenders(initial_state,
                                                 selection.base.value)
    if offenders:
        detail = ", ".join(
            f"{driver_id} age={age:.1f}s" for driver_id, age in offenders)
        raise SimulationUnsupportedError(
            REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER,
            "roster members whose latest observation is more than "
            f"{CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES:g} expected lap "
            f"times ({CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES * selection.base.value:.1f}s) "
            f"older than T cannot be evolved honestly: {detail}")


def _validate_temporal(initial_state: SimulationState,
                       parameters: SimulationParameterSet,
                       execution_policy: ExecutionPolicy,
                       selection: PaceParameterSelection) -> None:
    if not isinstance(execution_policy, ExecutionPolicy):
        raise SimulationContractError(
            "execution_policy must be an ExecutionPolicy, got "
            f"{execution_policy!r}")
    if execution_policy is ExecutionPolicy.HISTORICAL_BACKTEST \
            and not selection.leakage_free:
        raise SimulationUnsupportedError(
            REASON_PARAMETER_TEMPORAL_LEAK,
            "historical backtest requires parameters estimated strictly "
            f"before the target season: through_season="
            f"{parameters.through_season!r} >= target_season="
            f"{initial_state.season!r}")


# ---------------------------------------------------------------------------
# Kernel.
# ---------------------------------------------------------------------------

@dataclass
class _KernelDriver:
    driver_id: str
    lap_number: int
    race_time_s: float
    tyre_age: int
    compound: Optional[str]
    pit_count: int
    constructor_id: Optional[str]
    anchor_tyre_age: int
    base_pace_s: float
    next_lap: int = 0
    next_age: int = 0
    next_time_s: float = 0.0
    last_expected_s: float = 0.0
    last_progress_adjustment_s: float = 0.0
    last_degradation_adjustment_s: float = 0.0
    finished: bool = False


def _build_kernel(initial_state: SimulationState,
                  selection: PaceParameterSelection):
    base = selection.base.value
    drivers: List[_KernelDriver] = []
    for entry in initial_state.drivers:
        offset = selection.offset_for(entry.constructor_id).value
        kernel = _KernelDriver(
            driver_id=entry.driver_id,
            lap_number=entry.lap_number,
            race_time_s=entry.race_time_s,
            tyre_age=entry.tyre_age,
            compound=entry.compound,
            pit_count=entry.pit_count,
            constructor_id=entry.constructor_id,
            anchor_tyre_age=entry.tyre_age,
            base_pace_s=base + offset,
        )
        drivers.append(kernel)
    return drivers


def _schedule_next(driver: _KernelDriver,
                   selection: PaceParameterSelection) -> None:
    driver.next_lap = driver.lap_number + 1
    driver.next_age = driver.tyre_age + 1
    mu, progress_adj, degradation_adj = expected_lap_time_s(
        selection, driver.base_pace_s, driver.next_lap, driver.next_age,
        driver.anchor_tyre_age)
    if not math.isfinite(mu):
        raise _NumericalFailure(
            REASON_NONFINITE_LAP_TIME,
            f"driver {driver.driver_id!r} lap {driver.next_lap} expected lap "
            f"time is not finite: {mu!r}")
    if mu <= 0.0:
        raise _NumericalFailure(
            REASON_NONPOSITIVE_LAP_TIME,
            f"driver {driver.driver_id!r} lap {driver.next_lap} expected lap "
            f"time is not positive: {mu!r}")
    driver.next_time_s = driver.race_time_s + mu
    if not math.isfinite(driver.next_time_s) or driver.next_time_s < 0.0:
        raise _NumericalFailure(
            REASON_NONFINITE_RACE_TIME,
            f"driver {driver.driver_id!r} next race time is invalid: "
            f"{driver.next_time_s!r}")
    driver.last_expected_s = mu
    driver.last_progress_adjustment_s = progress_adj
    driver.last_degradation_adjustment_s = degradation_adj


def _trace_event(trace, step: int, driver: _KernelDriver, from_lap: int,
                 to_lap: int) -> None:
    trace.append({
        "kind": "event",
        "step": step,
        "driver_id": driver.driver_id,
        "from_lap": from_lap,
        "to_lap": to_lap,
        "expected_lap_time_s": driver.last_expected_s,
        "progress_adjustment_s": driver.last_progress_adjustment_s,
        "degradation_adjustment_s": driver.last_degradation_adjustment_s,
        "race_time_s": driver.race_time_s,
    })


def _classify(drivers: List[_KernelDriver]) -> FinishOrder:
    ordered = sorted(
        drivers,
        key=lambda d: (-d.lap_number, d.race_time_s, d.driver_id),
    )
    entries = [
        DriverFinish(
            driver_id=driver.driver_id,
            classified=True,
            retired=False,
            laps_completed=driver.lap_number,
            race_time_s=driver.race_time_s,
            finish_position=position,
        )
        for position, driver in enumerate(ordered, start=1)
    ]
    return FinishOrder(roster_size=len(drivers), entries=tuple(entries))


def max_lap_events(roster_size: int, scheduled_laps: int) -> int:
    """Hard bound on lap-completion events, derived from field and distance.

    Each event advances exactly one driver by exactly one lap, and no driver
    can complete more than ``scheduled_laps`` laps, so this bound is structural
    (never an arbitrary large constant).
    """
    return roster_size * scheduled_laps + roster_size


class DeterministicRaceEngine:
    """Zero-noise lap-step evolution of one ``SimulationState`` (R4).

    Stateless and deterministic: the same ``(state, parameters, policy)``
    always yields a byte-identical ``SimulationRunResult``. No RNG is used and
    ``SimulationConfig.master_seed`` has no effect on this kernel.
    """

    def run(self, initial_state: SimulationState,
            parameters: SimulationParameterSet, *,
            execution_policy: ExecutionPolicy = (
                ExecutionPolicy.RETROSPECTIVE_PRODUCT),
            trace: Optional[List[dict]] = None) -> SimulationRunResult:
        """Evolve the race and return a validated deterministic result.

        Raises ``SimulationUnsupportedError`` when the state cannot be honestly
        evolved (red/SC/wet/missing tyre age/retired/temporal leakage) and
        ``SimulationContractError`` for wrong input types. Numerical failures
        mid-evolution return ``SimulationRunResult(valid=False, ...)`` rather
        than a fabricated classification.
        """
        if not isinstance(initial_state, SimulationState):
            raise SimulationContractError(
                "initial_state must be a SimulationState, got "
                f"{initial_state!r}")
        if not isinstance(parameters, SimulationParameterSet):
            raise SimulationContractError(
                "parameters must be a SimulationParameterSet, got "
                f"{parameters!r}")

        selection = select_pace_parameters(initial_state, parameters)
        _validate_start_state(initial_state, selection)
        _validate_temporal(initial_state, parameters, execution_policy,
                           selection)

        drivers = _build_kernel(initial_state, selection)
        simulation_id = self._simulation_id(initial_state, parameters)

        if trace is not None:
            trace.append({
                "kind": "selection",
                "execution_policy": execution_policy.value,
                "leakage_free": selection.leakage_free,
                "selection": selection.to_dict(),
            })

        try:
            classification = self._evolve(initial_state, selection, drivers,
                                          trace)
        except _NumericalFailure as failure:
            return SimulationRunResult(
                race_id=initial_state.race_id,
                simulation_id=simulation_id,
                simulation_index=0,
                valid=False,
                invalid_reason=failure.reason,
            )

        if trace is not None:
            for driver in sorted(drivers, key=lambda d: d.driver_id):
                trace.append({
                    "kind": "final",
                    "driver_id": driver.driver_id,
                    "lap_number": driver.lap_number,
                    "race_time_s": driver.race_time_s,
                    "tyre_age": driver.tyre_age,
                    "compound": driver.compound,
                    "pit_count": driver.pit_count,
                })

        return SimulationRunResult(
            race_id=initial_state.race_id,
            simulation_id=simulation_id,
            simulation_index=0,
            valid=True,
            classification=classification,
        )

    @staticmethod
    def _simulation_id(initial_state: SimulationState,
                       parameters: SimulationParameterSet) -> str:
        state_identity = initial_state.identity()
        return (f"{initial_state.race_id}:{parameters.parameter_version}:"
                f"{state_identity[:16]}:0")

    @staticmethod
    def _evolve(initial_state: SimulationState,
                selection: PaceParameterSelection,
                drivers: List[_KernelDriver],
                trace) -> FinishOrder:
        scheduled = initial_state.scheduled_laps
        # The leader already completed the scheduled distance (last-frame
        # smoke): the race is over and drivers keep their own completed laps.
        if max(driver.lap_number for driver in drivers) >= scheduled:
            return _classify(drivers)

        for driver in drivers:
            _schedule_next(driver, selection)

        max_iterations = max_lap_events(initial_state.roster_size, scheduled)
        for step in range(max_iterations):
            active = [d for d in drivers if not d.finished]
            if not active:
                break
            event_time = min(d.next_time_s for d in active)
            batch = sorted(
                (d for d in active if d.next_time_s == event_time),
                key=lambda d: d.driver_id,
            )
            for driver in batch:
                from_lap = driver.lap_number
                driver.lap_number = driver.next_lap
                driver.tyre_age = driver.next_age
                driver.race_time_s = event_time
                if trace is not None:
                    _trace_event(trace, step, driver, from_lap,
                                 driver.lap_number)
                if driver.lap_number >= scheduled:
                    driver.finished = True
                else:
                    _schedule_next(driver, selection)
            if any(d.finished for d in drivers):
                break
        else:
            raise _NumericalFailure(
                REASON_ITERATION_LIMIT,
                f"race did not complete within {max_iterations} lap events")

        return _classify(drivers)

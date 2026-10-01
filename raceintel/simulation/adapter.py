"""Phase-6 R2 factual adapter: ``RaceState`` -> ``SimulationState``.

One-way, factual-only projection of a frozen Phase-4 ``RaceState`` into the
R1 simulation starting state. The adapter does not evolve the race: it has no
pace model, no degradation model, no pit model, no overtaking/traffic model,
no reliability hazard, no stochastic draw, and no Monte Carlo. It reads
nothing but ``RaceState`` (plus the optional Phase-5 ``anchor_frame_index``
handle supplied by the caller) and therefore cannot see future canonical
rows, the full D9 frame, labels, results, the feature engine, the winner
model, or any replay prediction cache.

Temporal firewall (R2 critical rule)
------------------------------------
``SimulationState`` at T may contain ONLY information legally available at T.
The adapter maps from the already-synchronized ``RaceState``; it never
bypasses it to rebuild state from the complete D9 frame. Every mapped field
is ``FACTUAL_AT_T`` (copied from an observation ``<= T``) or a deterministic
past-only factual derivation (observation age). Nothing is modelled.

Mapping (exact)
---------------
Root:
- ``race_id``                       <- ``RaceState.race_id``
- ``season`` / ``round_no`` /
  ``circuit_id``                    <- ``RaceContext`` (nullable verbatim)
- ``scheduled_laps``                <- ``RaceContext.scheduled_laps``
- ``leader_laps_done``              <- ``RaceContext.race_leader_laps_at_state``
- ``simulation_time_s``             <- ``RaceState.state_time_s`` (exact T)
- ``anchor_frame_index``            <- caller-supplied Phase-5 handle (optional)
- ``environment.track_state``       <- ``RaceControlState.track_state`` verbatim
- ``environment.weather``           <- ``WeatherState`` (null-preserving)

Per observed driver:
- ``lap_number``       <- ``observed_lap_number`` (OWN progress, not leader lap)
- ``race_time_s``      <- ``observed_time_s`` (OWN clock ``<= T``)
- ``position``         <- ``position`` (nullable, not required unique)
- ``compound``         <- ``compound`` (nullable, verbatim)
- ``tyre_age``         <- ``tyre_life`` (nullable, verbatim)
- ``stint_number``     <- ``stint_number`` (nullable)
- ``pit_count``        <- ``pit_stops_completed_so_far``
- ``constructor_id``   <- ``constructor_id``
- ``status``           <- ALWAYS ``ACTIVE`` (no factual-at-T retirement source)
- ``observation_age_s``<- ``observation_age_s``

Active-set / pre-first decision (R2-F, R2-I)
--------------------------------------------
The adapter requires the COMPLETE factual roster to be observable at or
before T. If any roster member has no observation ``<= T`` (a pre-first
driver or a permanent zero-state entrant) the adapter refuses with
``SimulationUnavailableError(reason="unobserved_roster_member")`` rather
than fabricating a start position/time or silently dropping the member. The
frozen ``RaceState`` cannot distinguish those two cases from one snapshot,
so refusal is the only honest, lossless policy; a later stage may add a
history-based non-participant policy with its own evidence.

Stale / retirement policy (R2-G, R2-H)
--------------------------------------
Staleness never implies retirement. Every observed driver is emitted with
``DriverStatus.ACTIVE`` regardless of ``observation_age_s``. No retirement is
derived from observation age, last observed lap, gap invalidity, missing
compound, missing tyre age, or missing position. Simulated retirement belongs
to R6.

Null policy (R2-Y)
------------------
Nulls are preserved, never flattened: ``None`` stays ``None``. The adapter
never maps ``None -> 0``, ``None -> ""``, ``None -> fake position``,
``None -> T``, or ``None -> leader lap``. Facts that the R1 root contract
cannot represent as null (``scheduled_laps``, ``leader_laps_done``,
``pit_count``) cause an explicit ``SimulationUnavailableError`` instead of a
fabricated value.

Dependency direction: this module imports the frozen ``v2.race_state``
contracts and the Phase-6 simulation contracts only. It imports no
``v2.replay*`` (the caller composes the replay seam externally), no feature
engine, no prediction/model layer, no pandas/numpy, no API code.
"""

from __future__ import annotations

from raceintel.race_state.race_state import RaceState
from raceintel.simulation.errors import SimulationContractError, SimulationError
from raceintel.simulation.state import (
    DriverSimState,
    DriverStatus,
    Provenance,
    SimulationEnvironment,
    SimulationState,
)

__all__ = [
    "ADAPTER_PROVENANCE",
    "ADAPTER_SOURCE",
    "ADAPTER_VERSION",
    "ADAPTER_UNAVAILABLE_REASONS",
    "REASON_DRIVER_LAP_EXCEEDS_LEADER",
    "REASON_INVALID_POSITION",
    "REASON_LEADER_EXCEEDS_SCHEDULED",
    "REASON_MISSING_LEADER_PROGRESS",
    "REASON_MISSING_PIT_COUNT",
    "REASON_MISSING_SCHEDULED_LAPS",
    "REASON_UNOBSERVED_ROSTER_MEMBER",
    "SimulationUnavailableError",
    "from_race_state",
]

#: Adapter source/provenance identity (R2-P). Every field the adapter
#: supplies is factual at T; the R1 contracts deliberately do not carry
#: redundant per-scalar provenance tags, so this names the source instead.
ADAPTER_VERSION = "v1"
ADAPTER_SOURCE = "raceintel.race_state.race_state.RaceState@state_time_s"
ADAPTER_PROVENANCE = Provenance.FACTUAL_AT_T

# Stable, API-mappable reasons why a factual RaceState cannot be adapted
# honestly. These are distinct from programming/contract errors.
REASON_UNOBSERVED_ROSTER_MEMBER = "unobserved_roster_member"
REASON_MISSING_SCHEDULED_LAPS = "missing_scheduled_laps"
REASON_MISSING_LEADER_PROGRESS = "missing_leader_progress"
REASON_LEADER_EXCEEDS_SCHEDULED = "leader_progress_exceeds_scheduled_laps"
REASON_DRIVER_LAP_EXCEEDS_LEADER = "driver_lap_exceeds_leader_progress"
REASON_MISSING_PIT_COUNT = "missing_pit_count"
REASON_INVALID_POSITION = "invalid_position"

ADAPTER_UNAVAILABLE_REASONS = (
    REASON_UNOBSERVED_ROSTER_MEMBER,
    REASON_MISSING_SCHEDULED_LAPS,
    REASON_MISSING_LEADER_PROGRESS,
    REASON_LEADER_EXCEEDS_SCHEDULED,
    REASON_DRIVER_LAP_EXCEEDS_LEADER,
    REASON_MISSING_PIT_COUNT,
    REASON_INVALID_POSITION,
)


class SimulationUnavailableError(SimulationError):
    """The factual RaceState cannot be honestly represented as a start state.

    This is a factual-state incompatibility, not a programming error:
    the RaceState is well-formed but lacks information the R1 contract
    cannot represent without fabricating it. ``reason`` is a stable token
    from :data:`ADAPTER_UNAVAILABLE_REASONS` so a future API/service can
    map it to an explicit ``simulation_unsupported`` response.
    """

    def __init__(self, reason: str, detail: str):
        if reason not in ADAPTER_UNAVAILABLE_REASONS:
            raise SimulationContractError(
                f"unknown adapter unavailable reason {reason!r}")
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _driver_state(entry, leader_laps_done: int) -> DriverSimState:
    """Project one observed ``DriverRaceState``; never infer retirement."""
    if entry.pit_stops_completed_so_far is None:
        raise SimulationUnavailableError(
            REASON_MISSING_PIT_COUNT,
            f"driver {entry.driver_id!r} has no factual pit count at T")
    lap_number = entry.observed_lap_number
    if lap_number > leader_laps_done:
        raise SimulationUnavailableError(
            REASON_DRIVER_LAP_EXCEEDS_LEADER,
            f"driver {entry.driver_id!r} observed lap {lap_number!r} exceeds "
            f"factual leader progress {leader_laps_done!r}")
    if entry.position is not None and entry.position < 1:
        raise SimulationUnavailableError(
            REASON_INVALID_POSITION,
            f"driver {entry.driver_id!r} has position {entry.position!r}")
    return DriverSimState(
        driver_id=entry.driver_id,
        lap_number=lap_number,
        race_time_s=entry.observed_time_s,
        position=entry.position,
        compound=entry.compound,
        tyre_age=entry.tyre_life,
        stint_number=entry.stint_number,
        pit_count=entry.pit_stops_completed_so_far,
        constructor_id=entry.constructor_id,
        status=DriverStatus.ACTIVE,
        observation_age_s=entry.observation_age_s,
    )


def from_race_state(race_state: RaceState, *,
                    anchor_frame_index: int | None = None) -> SimulationState:
    """Adapt one frozen factual ``RaceState`` into a ``SimulationState``.

    ``anchor_frame_index`` is the optional Phase-5 replay handle that
    originated the state; the adapter itself never imports replay, the
    caller composes ``ReplayFrame -> ReplayReconstructor -> RaceState ->
    from_race_state`` externally.

    Raises ``SimulationContractError`` for programming misuse (wrong input
    type) and ``SimulationUnavailableError`` when the factual state cannot
    be represented honestly (see module docstring). No modelling occurs.
    """
    if not isinstance(race_state, RaceState):
        raise SimulationContractError(
            f"race_state must be a frozen RaceState, got {race_state!r}")
    context = race_state.race_context
    scheduled_laps = context.scheduled_laps
    if scheduled_laps is None:
        raise SimulationUnavailableError(
            REASON_MISSING_SCHEDULED_LAPS,
            f"race {race_state.race_id!r} has no scheduled distance at T")
    leader_laps_done = context.race_leader_laps_at_state
    if leader_laps_done is None:
        raise SimulationUnavailableError(
            REASON_MISSING_LEADER_PROGRESS,
            f"race {race_state.race_id!r} has no factual leader progress at T")
    if leader_laps_done > scheduled_laps:
        raise SimulationUnavailableError(
            REASON_LEADER_EXCEEDS_SCHEDULED,
            f"leader progress {leader_laps_done!r} exceeds scheduled "
            f"distance {scheduled_laps!r}")
    unobserved = race_state.unobservable_driver_ids
    if unobserved:
        raise SimulationUnavailableError(
            REASON_UNOBSERVED_ROSTER_MEMBER,
            "roster members with no observation at or before T: "
            f"{list(unobserved)}")
    drivers = tuple(
        _driver_state(entry, leader_laps_done)
        for entry in race_state.observable_drivers
    )
    environment = SimulationEnvironment(
        track_state=race_state.race_control.track_state,
        weather=race_state.weather,
    )
    return SimulationState(
        race_id=race_state.race_id,
        season=context.season,
        round_no=context.round_no,
        circuit_id=context.circuit_id,
        anchor_frame_index=anchor_frame_index,
        scheduled_laps=scheduled_laps,
        leader_laps_done=leader_laps_done,
        simulation_time_s=race_state.state_time_s,
        drivers=drivers,
        environment=environment,
    )

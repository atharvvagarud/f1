"""V3.2C causal initial-state presence adapter (mc2-field-v1 binding).

Binds the frozen declarative contract in
:mod:`raceintel.simulation.field_contract` to factual ``RaceState``
evidence WITHOUT touching the stochastic kernel:

    RaceState (+ pre-race grid slots)
        -> presence classification (field_contract.classify_presence, once)
        -> DNS exclusion (the sole frozen exclusion rule)
        -> unchanged R2 adapter (``from_race_state``)
        -> terminal check -> parameter selection -> start-state validation
        -> typed :class:`EligibilityResult`

Temporal rule: every input is legally available at T (observations
``<= T`` plus pre-race grid facts). Final classification, future rows,
post-T outcomes, DNF-shaped names, and winner/top-5 facts are never
read; poisoning them leaves every output byte-identical (tested).

What this module does NOT do (explicit V3.2C rejections):

- no generic retirement inference: ``STALE_UNRESOLVED`` stays refused;
- no ``EXCLUDE_SIGNALED_STALE`` runtime exclusion (candidate only);
- no tyre backfill (rejected/deferred by decision, never silent fill);
- no track/weather/terminal policy change;
- no RNG consumption, no stochastic draw, no parameter estimation.

Dependency direction: this module imports the frozen race-state
contracts, the R2 adapter, the R4 parameter/validation seam, and the
declarative field contract. Nothing imports this module except the
service seam, scripts, and tests. The kernel never imports it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from raceintel.race_state.race_state import RaceState
from raceintel.simulation.adapter import (
    SimulationUnavailableError,
    from_race_state,
)
from raceintel.simulation.engine import (
    ExecutionPolicy,
    SimulationUnsupportedError,
    _validate_start_state,
    _validate_temporal,
    contemporaneous_roster_offenders,
    select_pace_parameters,
)
from raceintel.simulation.field_contract import (
    FIELD_CONTRACT_VERSION,
    classify_presence,
    contract_identity,
)
from raceintel.simulation.driver_status import (
    STATUS_CONTRACT_VERSION,
    DriverStatusResolver,
)
from raceintel.simulation.state import SimulationState

__all__ = [
    "PRESENCE_ADAPTER_VERSION",
    "STATUS_CONTRACT_VERSION",
    "ELIGIBILITY_TAXONOMY",
    "ADAPTER_REASON_TO_TAXONOMY",
    "ENGINE_REASON_TO_TAXONOMY",
    "EligibilityResult",
    "grid_slot_known",
    "classify_roster",
    "dns_exclusions",
    "without_drivers",
    "status_exclusions_for_offenders",
    "prepare_initial_state",
]

#: Initial-state / eligibility contract version. Bumps only when the
#: presence/eligibility semantics change. Distinct from the stochastic
#: engine science version (still ``r3-v1`` / ``r5-monte-carlo-v1``):
#: V3.2C changes what may START, never how trajectories EVOLVE.
PRESENCE_ADAPTER_VERSION = "v3.2c-presence-v1"

#: Stable eligibility taxonomy (V3.2A tokens, reused verbatim).
ELIGIBILITY_TAXONOMY = (
    "SIMULATION_CAPABLE",
    "TERMINAL_STATE",
    "UNSUPPORTED_TRACK_STATE",
    "WET_CONDITIONS",
    "MISSING_TYRE_STATE",
    "STALE_ROSTER_OBSERVATION",
    "MISSING_RACE_METADATA",
    "MISSING_DRIVER_OBSERVATION",
    "MISSING_SIM_PARAMETER",
    "UNSUPPORTED_SEASON",
    "TEMPORAL_POLICY",
    "RETIRED_DRIVER_PRESENT",
    "INVALID_INPUT",
    "RECONSTRUCTION_FAILURE",
    "OTHER",
)

#: R2 adapter refusal -> eligibility taxonomy (same mapping as the V3.2A
#: audit classifier; restated here so runtime code never imports scripts).
ADAPTER_REASON_TO_TAXONOMY = {
    "unobserved_roster_member": "MISSING_DRIVER_OBSERVATION",
    "missing_pit_count": "MISSING_DRIVER_OBSERVATION",
    "missing_scheduled_laps": "MISSING_RACE_METADATA",
    "missing_leader_progress": "MISSING_RACE_METADATA",
    "leader_progress_exceeds_scheduled_laps": "INVALID_INPUT",
    "driver_lap_exceeds_leader_progress": "INVALID_INPUT",
    "invalid_position": "INVALID_INPUT",
}

#: R4 engine refusal -> eligibility taxonomy (same mapping as V3.2A).
ENGINE_REASON_TO_TAXONOMY = {
    "red_flag_track_state": "UNSUPPORTED_TRACK_STATE",
    "neutralized_track_state": "UNSUPPORTED_TRACK_STATE",
    "unknown_track_state": "UNSUPPORTED_TRACK_STATE",
    "wet_track_conditions": "WET_CONDITIONS",
    "wet_compound_state": "WET_CONDITIONS",
    "missing_tyre_age": "MISSING_TYRE_STATE",
    "non_contemporaneous_roster_member": "STALE_ROSTER_OBSERVATION",
    "missing_circuit_id": "MISSING_RACE_METADATA",
    "missing_season": "MISSING_RACE_METADATA",
    "unsupported_season": "UNSUPPORTED_SEASON",
    "missing_pace_parameter": "MISSING_SIM_PARAMETER",
    "parameter_temporal_leak": "TEMPORAL_POLICY",
    "retired_driver_unsupported": "RETIRED_DRIVER_PRESENT",
    "leader_progress_not_represented": "INVALID_INPUT",
}


@dataclass(frozen=True)
class EligibilityResult:
    """Deterministic eligibility verdict for one checkpoint at T.

    ``eligible`` True carries the exact ``SimulationState`` the unchanged
    R3 engine would evolve (same object ``from_race_state`` builds, so
    previously valid states are bit-identical). ``eligible`` False
    carries a stable taxonomy ``reason`` plus a human ``detail``.
    """

    eligible: bool
    reason: str
    detail: str
    presence_by_driver: tuple
    excluded_dns_driver_ids: tuple
    active_driver_ids: tuple
    field_contract_version: str = FIELD_CONTRACT_VERSION
    field_contract_identity: str = ""
    presence_adapter_version: str = PRESENCE_ADAPTER_VERSION
    #: V3.2J retired-status exclusions (empty unless status relief fired).
    excluded_status_driver_ids: tuple = ()
    #: Non-empty only when status relief fired (exclusion-only contract).
    status_contract_version: str = ""
    state: SimulationState | None = None

    def __post_init__(self) -> None:
        if self.reason not in ELIGIBILITY_TAXONOMY:
            raise ValueError(f"unknown eligibility reason {self.reason!r}")
        if self.eligible and self.state is None:
            raise ValueError("eligible results must carry the start state")
        if not self.eligible and self.state is not None:
            raise ValueError("refused results must not carry a start state")


def grid_slot_known(grid_value: object) -> bool:
    """Whether a pre-race grid slot exists for one roster member.

    Only the grid value is consulted: ``None``/``NaN`` means no
    qualifying/grid slot (DNS shape). Final classification, DNF flags,
    positions, and winner facts are never read here and cannot change
    this answer.
    """
    if grid_value is None:
        return False
    if isinstance(grid_value, float):
        # NaN check without numpy (stdlib-only module).
        return grid_value == grid_value
    if isinstance(grid_value, bool):
        return False
    if isinstance(grid_value, (int, str)):
        try:
            return float(grid_value) == float(grid_value)
        except (TypeError, ValueError):
            return False
    return False


def classify_roster(race_state: RaceState, grid_by_driver: dict | None,
                    *, age_bound_s: float | None = None,
                    rc_stopped_by_driver: frozenset = frozenset(),
                    laps_behind_by_driver: dict | None = None) -> dict:
    """Presence level per roster member from <=T evidence (one call site).

    ``grid_by_driver`` maps ``driver_id -> grid_position`` (``None``/NaN
    for no pre-race slot); only grid null-ness is read. Stale members
    are reported as ``STALE_UNRESOLVED`` (or the candidate
    ``EXCLUDE_SIGNALED_STALE`` when the bound+signal+behind guard holds)
    but callers must NOT exclude them: only ``EXCLUDE_DNS_PRE_RACE`` is
    a frozen runtime exclusion.
    """
    grid = grid_by_driver or {}
    behind = laps_behind_by_driver or {}
    leader_lap = race_state.race_context.race_leader_laps_at_state
    observable = {e.driver_id: e for e in race_state.observable_drivers}
    levels: dict[str, str] = {}
    for driver_id in race_state.roster_driver_ids:
        entry = observable.get(driver_id)
        if entry is None:
            # DNS is provable only when the pre-race grid fact is present:
            # without a grid map we must not claim it (strictly refuse).
            dns_provable = (grid_by_driver is not None
                            and driver_id in grid
                            and not grid_slot_known(grid[driver_id]))
            levels[driver_id] = classify_presence(
                observed=False, dns_no_grid_slot=dns_provable)
            if levels[driver_id] == "UNOBSERVED_PRE_FIRST" \
                    and (leader_lap is not None and leader_lap > 1):
                # History-free lap-1/data-gap split: once the field has
                # completed lap 1, a gridded-but-never-observed member is
                # a data gap, not a pre-first boundary. Both refuse.
                levels[driver_id] = "UNOBSERVED_DATA_GAP"
            continue
        age = entry.observation_age_s
        levels[driver_id] = classify_presence(
            observed=True,
            observation_age_s=None if age is None else float(age),
            age_bound_s=None if age_bound_s is None else float(age_bound_s),
            rc_stopped=(driver_id in set(rc_stopped_by_driver)),
            laps_behind_leader=behind.get(driver_id),
        )
    return levels


def dns_exclusions(race_state: RaceState,
                   grid_by_driver: dict | None) -> tuple:
    """Proven-DNS roster members: unobserved AND no pre-race grid slot.

    Deterministic ``driver_id`` order. Empty when no grid map is
    supplied (strictly conservative: refuse, never assume).
    """
    if not grid_by_driver:
        return ()
    excluded = [
        driver_id for driver_id in race_state.unobservable_driver_ids
        if driver_id in grid_by_driver
        and not grid_slot_known(grid_by_driver[driver_id])
    ]
    return tuple(sorted(excluded))


def status_exclusions_for_offenders(
        offender_ids: tuple | list,
        *, resolver: DriverStatusResolver | None,
        race_id: str | None, T: float | None,
        windows: dict | None = None) -> tuple | None:
    """V3.2J exclusion-only retired-status relief (additive, fail closed).

    Returns the excludable driver tuple ONLY when EVERY offender is
    authoritatively retired at T: latest causally observed Retired value
    ``<= T`` is ``True`` AND T falls in no pinned unreliable window for
    that driver. Any unknown, ``False``, windowed, anchor, missing
    resolver/race/T, or empty-offender input returns ``None`` (existing
    eligibility behavior applies). Never proves activity.
    """
    offenders = tuple(sorted(set(offender_ids or ())))
    if not offenders or resolver is None or race_id is None or T is None:
        return None
    try:
        moment = float(T)
    except (TypeError, ValueError):
        return None
    excluded = []
    for driver_id in offenders:
        if resolver.retired_known_at(race_id, driver_id, moment) is not True:
            return None
        for start, end in (windows or {}).get((race_id, driver_id), ()):
            if start <= moment < end:
                return None
        excluded.append(driver_id)
    return tuple(sorted(excluded))


def without_drivers(race_state: RaceState,
                    exclude_driver_ids: tuple | frozenset) -> RaceState:
    """Copy of ``race_state`` with the excluded members removed.

    The anchor driver is always observable (an exact D9 row), hence never
    a DNS exclusion; attempting to remove it is refused loudly.
    """
    excluded = set(exclude_driver_ids or ())
    if race_state.anchor_driver_id in excluded:
        raise ValueError(
            f"cannot exclude anchor driver "
            f"{race_state.anchor_driver_id!r}: the anchor is an exact "
            f"observed row and therefore never DNS")
    if not excluded:
        return race_state
    missing = excluded - set(race_state.roster_driver_ids)
    if missing:
        raise ValueError(f"cannot exclude non-roster drivers {sorted(missing)}")
    return dataclasses.replace(
        race_state,
        drivers=tuple(e for e in race_state.drivers
                      if e.driver_id not in excluded),
    )


def prepare_initial_state(
        race_state: RaceState, *, grid_by_driver: dict | None,
        parameters,
        execution_policy: ExecutionPolicy = (
            ExecutionPolicy.RETROSPECTIVE_PRODUCT),
        age_bound_s: float | None = None,
        status_resolver: DriverStatusResolver | None = None,
        status_race_id: str | None = None,
        status_time_s: float | None = None,
        status_windows: dict | None = None) -> EligibilityResult:
    """DNS-aware eligibility for one factual checkpoint (no RNG, no MC).

    Mirrors the audit classifier order (adapter -> terminal -> parameter
    selection -> start-state validation) with the frozen DNS exclusion
    applied first. Raises nothing: refusals are typed results. For a
    checkpoint with no DNS member the adapted ``SimulationState`` is
    built by the byte-identical ``from_race_state`` call on the
    untouched ``RaceState``, so previously valid states are bit-exact.

    V3.2J additive relief: when ``status_resolver`` is supplied and the
    otherwise-unchanged path refuses with ``STALE_ROSTER_OBSERVATION``,
    every contemporaneous offender that is authoritatively retired at T
    (``v3.2j-driver-status-v1``, unreliable windows honored) may be
    excluded and the reduced field re-validated. Previously eligible
    states return before any status logic runs, so they are
    bit-identical with or without a resolver. Without a resolver the
    behavior is exactly V3.2C.
    """
    presence = classify_roster(race_state, grid_by_driver,
                               age_bound_s=age_bound_s)
    dns = dns_exclusions(race_state, grid_by_driver)
    active_state = without_drivers(race_state, dns) if dns else race_state
    presence_items = tuple(sorted(presence.items()))
    active_ids = tuple(sorted(active_state.roster_driver_ids))

    def _refused(taxon: str, detail: str) -> EligibilityResult:
        return EligibilityResult(
            eligible=False, reason=taxon, detail=detail,
            presence_by_driver=presence_items,
            excluded_dns_driver_ids=tuple(dns),
            active_driver_ids=active_ids,
            field_contract_identity=contract_identity(),
        )

    try:
        sim_state = from_race_state(active_state)
    except SimulationUnavailableError as exc:
        taxon = ADAPTER_REASON_TO_TAXONOMY.get(exc.reason, "OTHER")
        return _refused(taxon, f"adapter:{exc.reason}: {exc.detail}")
    scheduled = sim_state.scheduled_laps
    leader_done = sim_state.leader_laps_done
    if leader_done >= scheduled:
        return _refused(
            "TERMINAL_STATE",
            "terminal_state: leader_laps_done >= scheduled_laps "
            "(no remaining race to simulate)")
    try:
        selection = select_pace_parameters(sim_state, parameters)
    except SimulationUnsupportedError as exc:
        taxon = ENGINE_REASON_TO_TAXONOMY.get(exc.reason, "OTHER")
        return _refused(taxon, f"engine_select:{exc.reason}: {exc.detail}")
    except Exception as exc:  # noqa: BLE001 - typed refusal, never a crash
        return _refused("OTHER", f"engine_select:error: {type(exc).__name__}")
    try:
        _validate_start_state(sim_state, selection)
        _validate_temporal(sim_state, parameters, execution_policy,
                           selection)
    except SimulationUnsupportedError as exc:
        taxon = ENGINE_REASON_TO_TAXONOMY.get(exc.reason, "OTHER")
        if taxon == "STALE_ROSTER_OBSERVATION" and status_resolver is not None:
            relieved = _try_status_relief(
                race_state, active_state, sim_state, selection, parameters,
                execution_policy, presence_items, dns,
                status_resolver=status_resolver,
                status_race_id=(race_state.race_id if status_race_id is None
                                else status_race_id),
                status_time_s=(race_state.state_time_s
                               if status_time_s is None else status_time_s),
                status_windows=status_windows)
            if relieved is not None:
                return relieved
        return _refused(taxon, f"engine_validate:{exc.reason}: {exc.detail}")
    except Exception as exc:  # noqa: BLE001 - typed refusal, never a crash
        return _refused("OTHER",
                        f"engine_validate:error: {type(exc).__name__}")
    return EligibilityResult(
        eligible=True, reason="SIMULATION_CAPABLE", detail="capable",
        presence_by_driver=presence_items,
        excluded_dns_driver_ids=tuple(dns),
        active_driver_ids=active_ids,
        field_contract_identity=contract_identity(),
        state=sim_state,
    )


def _try_status_relief(race_state: RaceState, active_state: RaceState,
                       sim_state, selection, parameters,
                       execution_policy: ExecutionPolicy,
                       presence_items: tuple, dns: tuple, *,
                       status_resolver: DriverStatusResolver,
                       status_race_id: str, status_time_s: float,
                       status_windows: dict | None):
    """Second pass: exclude authoritatively retired stale offenders.

    Returns an eligible result only when EVERY contemporaneous offender
    is retired-True at T outside unreliable windows AND the reduced
    field validates cleanly. Any gap returns ``None`` so the caller
    keeps the original refusal byte-identical.
    """
    try:
        offenders = contemporaneous_roster_offenders(
            sim_state, selection.base.value)
    except Exception:  # noqa: BLE001 - no scale, no conclusion
        return None
    offender_ids = tuple(d for d, _ in offenders)
    excludable = status_exclusions_for_offenders(
        offender_ids, resolver=status_resolver, race_id=status_race_id,
        T=status_time_s, windows=status_windows)
    if excludable is None:
        return None
    try:
        reduced = without_drivers(active_state, excludable)
        relieved_state = from_race_state(reduced)
    except Exception:  # noqa: BLE001 - original refusal stands
        return None
    if relieved_state.leader_laps_done >= relieved_state.scheduled_laps:
        return None
    try:
        relieved_selection = select_pace_parameters(relieved_state,
                                                    parameters)
        _validate_start_state(relieved_state, relieved_selection)
        _validate_temporal(relieved_state, parameters, execution_policy,
                           relieved_selection)
    except Exception:  # noqa: BLE001 - original refusal stands
        return None
    return EligibilityResult(
        eligible=True, reason="SIMULATION_CAPABLE",
        detail="capable:stale_offenders_retired_at_T:"
               f"{','.join(excludable)}",
        presence_by_driver=presence_items,
        excluded_dns_driver_ids=tuple(dns),
        active_driver_ids=tuple(sorted(reduced.roster_driver_ids)),
        field_contract_identity=contract_identity(),
        presence_adapter_version="v3.2j-presence-v2",
        excluded_status_driver_ids=tuple(excludable),
        status_contract_version=STATUS_CONTRACT_VERSION,
        state=relieved_state,
    )

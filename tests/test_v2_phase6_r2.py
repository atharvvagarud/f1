"""Phase-6 R2 factual adapter tests: RaceState -> SimulationState.

No simulation kernel, no pace/pit/traffic/reliability model, no stochastic
draw, no aggregation, no training, no inference, no parameter estimation.
The adapter is a one-way factual projection and every test proves it cannot
see future data.

Fixtures (frozen Phase-5 replay seam):
- ordinary: 2023-r01-R @ alonso-28
- partial:  2021-r12-R (Belgium; ends under red)
- red:      2022-r18-R @ ocon-2
- stale:    2022-r07-R @ norris-30
- shared-T: 2020-r09-R @ 2974.257 (representative giovinazzi/6, not latifi)
- early:    2023-r01-R first frame (pre-first roster member -> unavailable)
- lapped:   2023-r01-R last frame
"""

from __future__ import annotations

import ast
import functools
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from v2 import race_state as RS
from v2 import replay as RP
from v2 import simulation as S
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_reconstruction import ReplayReconstructor
from v2.simulation.adapter import (
    ADAPTER_PROVENANCE,
    ADAPTER_SOURCE,
    ADAPTER_UNAVAILABLE_REASONS,
    REASON_DRIVER_LAP_EXCEEDS_LEADER,
    REASON_INVALID_POSITION,
    REASON_LEADER_EXCEEDS_SCHEDULED,
    REASON_MISSING_LEADER_PROGRESS,
    REASON_MISSING_PIT_COUNT,
    REASON_MISSING_SCHEDULED_LAPS,
    REASON_UNOBSERVED_ROSTER_MEMBER,
    SimulationUnavailableError,
    from_race_state,
)

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_SOURCE_PATH = ROOT / "v2" / "simulation" / "adapter.py"

D9 = (str(ROOT) + "/data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = (str(ROOT) + "/data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = (str(ROOT) + "/data/v2/processed/races/season={season}/"
         "races__{race}.parquet")


# ---------------------------------------------------------------------------
# Fixtures / helpers.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def load_race(season: int, race_id: str):
    states = pd.read_parquet(D9.format(season=season))
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(RESULTS.format(season=season, race=race_id))
    meta = {}
    try:
        races = pd.read_parquet(RACES.format(season=season, race=race_id))
        for row in races.itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(scheduled)
                                   else int(scheduled))}
    except FileNotFoundError:
        pass
    return states, results, meta


@functools.lru_cache(maxsize=None)
def make_service(season: int, race_id: str) -> ReplayReconstructor:
    states, results, meta = load_race(season, race_id)
    timeline = RP.build_replay_timeline(states)
    reconstructor = RaceStateReconstructor(states, results,
                                           race_meta=meta or None)
    return ReplayReconstructor(timeline, reconstructor)


def frame_index_for(service: ReplayReconstructor, driver: str, lap: int) -> int:
    for frame in service.timeline.frames:
        if (frame.anchor_driver_id == driver
                and frame.anchor_lap_number == lap):
            return frame.frame_index
    raise AssertionError(f"anchor {(driver, lap)} not found")


def race_state_for(season: int, race_id: str, driver: str, lap: int):
    service = make_service(season, race_id)
    index = frame_index_for(service, driver, lap)
    return service, index, service.state_at(index)


def adapt(race_state: RS.RaceState, frame_index: int | None = None):
    return from_race_state(race_state, anchor_frame_index=frame_index)


def blob(state: S.SimulationState) -> str:
    return S.canonical_json(state.to_dict())


# ---------------------------------------------------------------------------
# Synthetic RaceState builders (no data, no future).
# ---------------------------------------------------------------------------

def syn_driver(driver_id, lap, t, *, observable=True, **kw):
    if not observable:
        return RS.DriverRaceState.unobserved(driver_id)
    kw.setdefault("pit_stops_completed_so_far", 0)
    return RS.DriverRaceState(
        driver_id=driver_id, observable=True,
        observed_lap_number=lap, observed_time_s=t, **kw)


def syn_state(drivers, *, race_id="SYN-R", anchor="a", anchor_lap=2, T=200.0,
              leader=2, scheduled=50, track_state="all_clear", weather=None,
              season=2023, round_no=1, circuit_id="syn"):
    return RS.RaceState(
        race_id=race_id,
        anchor_driver_id=anchor,
        anchor_lap_number=anchor_lap,
        state_time_s=T,
        drivers=tuple(drivers),
        race_context=RS.RaceContext(
            race_leader_laps_at_state=leader, race_progress_frac=None,
            scheduled_laps=scheduled, season=season, round_no=round_no,
            circuit_id=circuit_id),
        weather=weather or RS.WeatherState(),
        race_control=RS.RaceControlState(track_state=track_state),
    )


def simple_state(**kw):
    """Anchor 'a' lap 2 at T=200 with a same-lap rival 'b'."""
    drivers = kw.pop("drivers", None) or [
        syn_driver("a", 2, 200.0, position=1, compound="SOFT", tyre_life=3,
                   stint_number=1, pit_stops_completed_so_far=0,
                   constructor_id="mclaren"),
        syn_driver("b", 2, 205.0, position=2, compound="MEDIUM", tyre_life=1,
                   stint_number=1, pit_stops_completed_so_far=0,
                   constructor_id="mercedes"),
    ]
    return syn_state(drivers, **kw)


# ---------------------------------------------------------------------------
# Error taxonomy / programming errors (R2-X).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [None, "nope", 42, object(), {}])
def test_rejects_non_race_state(bad):
    with pytest.raises(S.SimulationContractError):
        from_race_state(bad)


def test_unavailable_error_rejects_unknown_reason():
    with pytest.raises(S.SimulationContractError):
        SimulationUnavailableError("not_a_reason", "x")


def test_unavailable_error_carries_stable_reason_and_detail():
    err = SimulationUnavailableError(REASON_MISSING_SCHEDULED_LAPS, "detail")
    assert err.reason == REASON_MISSING_SCHEDULED_LAPS
    assert err.detail == "detail"
    assert str(err).startswith(REASON_MISSING_SCHEDULED_LAPS)
    assert isinstance(err, S.SimulationError)


def test_unavailable_error_message_is_deterministic():
    first = SimulationUnavailableError(REASON_MISSING_LEADER_PROGRESS, "d")
    second = SimulationUnavailableError(REASON_MISSING_LEADER_PROGRESS, "d")
    assert str(first) == str(second)


def test_unavailable_reasons_are_unique_and_stable():
    assert len(ADAPTER_UNAVAILABLE_REASONS) == len(
        set(ADAPTER_UNAVAILABLE_REASONS))
    for token in ADAPTER_UNAVAILABLE_REASONS:
        assert isinstance(token, str) and token
        assert token == token.lower()


def test_unavailable_error_is_not_a_validation_error():
    # Factual-state incompatibility is distinct from a malformed contract.
    assert not issubclass(SimulationUnavailableError,
                          S.SimulationValidationError)


# ---------------------------------------------------------------------------
# Root mapping (ordinary fixture).
# ---------------------------------------------------------------------------

def test_root_identity_mapping():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert adapted.race_id == rs.race_id
    assert adapted.season == rs.race_context.season
    assert adapted.round_no == rs.race_context.round_no
    assert adapted.circuit_id == rs.race_context.circuit_id


def test_simulation_time_is_exact_anchor_T():
    service, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, index)
    assert adapted.simulation_time_s == \
        service.timeline.frame_at(index).anchor_state_time_s
    assert adapted.simulation_time_s == rs.state_time_s


def test_leader_progress_from_race_context():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert adapted.leader_laps_done == \
        rs.race_context.race_leader_laps_at_state


def test_scheduled_laps_from_race_context():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert adapted.scheduled_laps == rs.race_context.scheduled_laps


def test_track_state_carried_verbatim():
    _, _, rs = race_state_for(2022, "2022-r18-R", "ocon", 2)
    adapted = adapt(rs, 0)
    assert adapted.environment.track_state == rs.race_control.track_state
    assert adapted.environment.track_state == "red_flag"


def test_weather_is_frozen_weather_state():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert isinstance(adapted.environment.weather, RS.WeatherState)
    assert adapted.environment.weather.to_dict() == rs.weather.to_dict()


def test_anchor_frame_index_mapped_when_supplied():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    assert adapt(rs, index).anchor_frame_index == index


def test_anchor_frame_index_defaults_none():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    assert adapt(rs).anchor_frame_index is None


def test_roster_matches_factual_roster():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert adapted.roster_size == rs.roster_size
    assert set(adapted.roster_driver_ids) == set(rs.roster_driver_ids)


def test_driver_ordering_is_canonical():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    ids = list(adapt(rs, 0).roster_driver_ids)
    assert ids == sorted(ids)


def test_contract_version_propagated():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    assert adapt(rs, 0).simulation_contract_version == "v1"


# ---------------------------------------------------------------------------
# Per-driver factual mapping.
# ---------------------------------------------------------------------------

def test_driver_fields_match_race_state_exactly():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    for entry in rs.observable_drivers:
        got = by_id[entry.driver_id]
        assert got.lap_number == entry.observed_lap_number
        assert got.race_time_s == entry.observed_time_s
        assert got.position == entry.position
        assert got.compound == entry.compound
        assert got.tyre_age == entry.tyre_life
        assert got.stint_number == entry.stint_number
        assert got.pit_count == entry.pit_stops_completed_so_far
        assert got.constructor_id == entry.constructor_id
        assert got.observation_age_s == entry.observation_age_s
        assert got.status == S.DriverStatus.ACTIVE


def test_race_time_is_own_clock_not_T():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    stale = [d for d in adapted.drivers
             if d.observation_age_s is not None
             and d.observation_age_s > 0]
    assert stale
    for entry in stale:
        assert entry.race_time_s < adapted.simulation_time_s
        assert entry.race_time_s != adapted.simulation_time_s


def test_lap_number_is_own_progress():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    own = {d.driver_id: d.lap_number for d in adapted.drivers}
    assert own["alonso"] == 28
    assert min(own.values()) <= max(own.values())


def test_observation_age_invariant_holds():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    for entry in adapted.drivers:
        if entry.observation_age_s is None:
            continue
        expected = adapted.simulation_time_s - entry.race_time_s
        assert entry.observation_age_s == pytest.approx(expected, abs=1e-6)


def test_position_and_compound_carried():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    source = {d.driver_id: d for d in rs.observable_drivers}
    for driver_id in ("alonso", "max_verstappen"):
        if driver_id in source:
            assert by_id[driver_id].position == source[driver_id].position
            assert by_id[driver_id].compound == source[driver_id].compound


def test_constructor_carried():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    source = {d.driver_id: d for d in rs.observable_drivers}
    for driver_id in by_id:
        assert by_id[driver_id].constructor_id == \
            source[driver_id].constructor_id


# ---------------------------------------------------------------------------
# Leader progress independent of the anchor (lapped anchor).
# ---------------------------------------------------------------------------

def test_leader_progress_independent_of_anchor_lap():
    drivers = [
        syn_driver("a", 8, 200.0, position=3),   # anchor, lapped
        syn_driver("b", 10, 195.0, position=1),  # true leader
        syn_driver("c", 9, 198.0, position=2),
    ]
    state = syn_state(drivers, anchor="a", anchor_lap=8, T=200.0, leader=10)
    adapted = adapt(state, 0)
    assert adapted.leader_laps_done == 10
    assert adapted.leader_laps_done != state.anchor_lap_number
    by_id = {d.driver_id: d for d in adapted.drivers}
    assert by_id["a"].lap_number == 8
    assert by_id["b"].lap_number == 10


def test_lapped_driver_keeps_own_lap_count():
    drivers = [
        syn_driver("a", 9, 200.0, position=1),
        syn_driver("b", 8, 199.0, position=2),   # one lap down
        syn_driver("c", 7, 198.0, position=3),   # two laps down
    ]
    state = syn_state(drivers, anchor="a", anchor_lap=9, T=200.0, leader=9)
    adapted = adapt(state, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    assert by_id["b"].lap_number == 8
    assert by_id["c"].lap_number == 7
    assert by_id["b"].lap_number != adapted.leader_laps_done
    assert by_id["c"].lap_number != adapted.leader_laps_done


# ---------------------------------------------------------------------------
# Stale driver semantics.
# ---------------------------------------------------------------------------

def test_stale_driver_preserved_and_active():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    source = {d.driver_id: d for d in rs.observable_drivers}
    assert by_id["norris"].observation_age_s == \
        source["norris"].observation_age_s
    assert all(d.status == S.DriverStatus.ACTIVE for d in adapted.drivers)


def test_stale_driver_race_time_and_lap_preserved():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    source = {d.driver_id: d for d in rs.observable_drivers}
    for driver_id, entry in source.items():
        assert by_id[driver_id].race_time_s == entry.observed_time_s
        assert by_id[driver_id].lap_number == entry.observed_lap_number


def test_stale_not_marked_retired():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    assert all(d.status is not S.DriverStatus.RETIRED
               for d in adapted.drivers)
    assert all(d.status is S.DriverStatus.ACTIVE for d in adapted.drivers)


def test_retirement_not_derived_from_large_observation_age():
    drivers = [
        syn_driver("a", 2, 200.0),
        syn_driver("b", 1, 50.0, observation_age_s=150.0),
    ]
    adapted = adapt(syn_state(drivers), 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    assert by_id["b"].observation_age_s == 150.0
    assert by_id["b"].status is S.DriverStatus.ACTIVE


def test_retirement_not_derived_from_missing_tyre_and_compound():
    drivers = [
        syn_driver("a", 2, 200.0),
        syn_driver("b", 1, 100.0, compound=None, tyre_life=None,
                   stint_number=None),
    ]
    adapted = adapt(syn_state(drivers), 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    assert by_id["b"].compound is None
    assert by_id["b"].tyre_age is None
    assert by_id["b"].status is S.DriverStatus.ACTIVE


# ---------------------------------------------------------------------------
# Pre-first observation policy.
# ---------------------------------------------------------------------------

def test_early_frame_unavailable_reason():
    service = make_service(2023, "2023-r01-R")
    state = service.first_state()
    with pytest.raises(SimulationUnavailableError) as exc:
        from_race_state(state, anchor_frame_index=0)
    assert exc.value.reason == REASON_UNOBSERVED_ROSTER_MEMBER


def test_early_frame_lists_unobserved_members():
    service = make_service(2023, "2023-r01-R")
    state = service.first_state()
    assert len(state.unobservable_driver_ids) > 0
    with pytest.raises(SimulationUnavailableError) as exc:
        from_race_state(state)
    for driver_id in state.unobservable_driver_ids:
        assert driver_id in exc.value.detail


def test_unobserved_roster_member_synthetic():
    drivers = [syn_driver("a", 2, 200.0), syn_driver("b", 1, 100.0),
               syn_driver("z", 0, 0.0, observable=False)]
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(syn_state(drivers), 0)
    assert exc.value.reason == REASON_UNOBSERVED_ROSTER_MEMBER
    assert "z" in exc.value.detail


def test_pre_first_driver_is_never_fabricated():
    service = make_service(2023, "2023-r01-R")
    state = service.first_state()
    try:
        adapted = from_race_state(state)
    except SimulationUnavailableError:
        adapted = None
    # If it ever succeeded it must not contain an unobserved driver with a
    # fabricated lap/time; the frozen policy refuses instead.
    assert adapted is None


def test_full_roster_observed_adapts():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    assert adapted.roster_size == rs.roster_size
    assert len(rs.observable_drivers) == rs.roster_size
    for entry in adapted.drivers:
        assert entry.lap_number >= 1
        assert entry.race_time_s >= 0.0


# ---------------------------------------------------------------------------
# Partial / red / shared-T / lapped fixtures.
# ---------------------------------------------------------------------------

def test_partial_race_adapts_last_state():
    service = make_service(2021, "2021-r12-R")
    state = service.last_state()
    adapted = adapt(state, service.timeline.frame_count - 1)
    assert adapted.roster_size == state.roster_size
    assert adapted.simulation_time_s == state.state_time_s
    assert adapted.scheduled_laps >= adapted.leader_laps_done


def test_partial_race_null_compound_preserved():
    service = make_service(2021, "2021-r12-R")
    state = service.last_state()
    adapted = adapt(state, service.timeline.frame_count - 1)
    source = {d.driver_id: d for d in state.observable_drivers}
    assert any(d.compound is None for d in adapted.drivers)
    for entry in adapted.drivers:
        assert entry.compound == source[entry.driver_id].compound


def test_red_state_representation_and_track_token():
    _, index, rs = race_state_for(2022, "2022-r18-R", "ocon", 2)
    adapted = adapt(rs, index)
    assert adapted.environment.track_state == "red_flag"
    assert rs.race_control.flag_red is True


def test_red_state_adapted_without_refusal():
    # The adapter represents a red factual state honestly; refusing red is an
    # engine (v1) policy, not an adapter mapping policy.
    _, index, rs = race_state_for(2022, "2022-r18-R", "ocon", 2)
    adapted = adapt(rs, index)
    assert adapted.roster_size == 20
    assert adapted.simulation_time_s == rs.state_time_s


def test_shared_t_regression_exact_time():
    service = make_service(2020, "2020-r09-R")
    index = next(i for i, f in enumerate(service.timeline.frames)
                 if f.anchor_state_time_s == 2974.257)
    state = service.state_at(index)
    adapted = adapt(state, index)
    assert adapted.simulation_time_s == 2974.257
    assert state.anchor_driver_id == "giovinazzi"
    assert state.anchor_lap_number == 6


def test_shared_t_representative_not_latifi_sc():
    service = make_service(2020, "2020-r09-R")
    index = next(i for i, f in enumerate(service.timeline.frames)
                 if f.anchor_state_time_s == 2974.257)
    adapted = adapt(service.state_at(index), index)
    assert adapted.environment.track_state == "yellow"
    assert adapted.simulation_time_s == 2974.257


def test_shared_t_adaptation_is_deterministic():
    service = make_service(2020, "2020-r09-R")
    index = next(i for i, f in enumerate(service.timeline.frames)
                 if f.anchor_state_time_s == 2974.257)
    first = adapt(service.state_at(index), index)
    second = adapt(service.state_at(index), index)
    assert blob(first) == blob(second)
    assert first.identity() == second.identity()


def test_lapped_fixture_preserves_own_laps():
    service = make_service(2023, "2023-r01-R")
    index = service.timeline.frame_count - 1
    adapted = adapt(service.state_at(index), index)
    laps = {d.lap_number for d in adapted.drivers}
    assert len(laps) > 1
    assert max(laps) == adapted.leader_laps_done
    assert any(lap < adapted.leader_laps_done for lap in laps)


def test_lapped_fixture_never_forces_leader_lap():
    service = make_service(2023, "2023-r01-R")
    index = service.timeline.frame_count - 1
    adapted = adapt(service.state_at(index), index)
    lapped = [d for d in adapted.drivers
              if d.lap_number < adapted.leader_laps_done]
    assert lapped
    for entry in lapped:
        assert entry.lap_number < adapted.leader_laps_done


# ---------------------------------------------------------------------------
# Tyre / stint / pit mapping (factual only).
# ---------------------------------------------------------------------------

def test_null_tyre_age_preserved_stale_fixture():
    _, _, rs = race_state_for(2022, "2022-r07-R", "norris", 30)
    adapted = adapt(rs, 0)
    source = {d.driver_id: d for d in rs.observable_drivers}
    nulls = [d.driver_id for d in adapted.drivers if d.tyre_age is None]
    assert nulls
    for driver_id in nulls:
        assert source[driver_id].tyre_life is None


def test_null_compound_preserved_partial():
    service = make_service(2021, "2021-r12-R")
    adapted = adapt(service.last_state(),
                    service.timeline.frame_count - 1)
    assert any(d.compound is None for d in adapted.drivers)


def test_zero_tyre_age_distinct_from_null():
    drivers = [
        syn_driver("a", 2, 200.0, tyre_life=0),
        syn_driver("b", 1, 100.0, tyre_life=None),
    ]
    adapted = adapt(syn_state(drivers), 0)
    by_id = {d.driver_id: d for d in adapted.drivers}
    assert by_id["a"].tyre_age == 0
    assert by_id["b"].tyre_age is None


def test_pit_count_zero_is_factual_zero_not_null():
    drivers = [syn_driver("a", 2, 200.0, pit_stops_completed_so_far=0)]
    adapted = adapt(syn_state(drivers, anchor="a", anchor_lap=2), 0)
    assert adapted.drivers[0].pit_count == 0


def test_stint_null_preserved():
    drivers = [syn_driver("a", 2, 200.0, stint_number=None)]
    adapted = adapt(syn_state(drivers), 0)
    assert adapted.drivers[0].stint_number is None


def test_pit_count_and_stint_mapped_from_fixture():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, 0)
    source = {d.driver_id: d for d in rs.observable_drivers}
    for entry in adapted.drivers:
        assert entry.pit_count == \
            source[entry.driver_id].pit_stops_completed_so_far
        assert entry.stint_number == \
            source[entry.driver_id].stint_number


# ---------------------------------------------------------------------------
# Null / unavailable policy (R2-Y).
# ---------------------------------------------------------------------------

def test_missing_scheduled_laps_unavailable():
    drivers = [syn_driver("a", 2, 200.0)]
    state = syn_state(drivers, scheduled=None)
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(state, 0)
    assert exc.value.reason == REASON_MISSING_SCHEDULED_LAPS


def test_missing_leader_progress_unavailable():
    drivers = [syn_driver("a", 2, 200.0)]
    state = syn_state(drivers, leader=None)
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(state, 0)
    assert exc.value.reason == REASON_MISSING_LEADER_PROGRESS


def test_leader_exceeds_scheduled_unavailable():
    drivers = [syn_driver("a", 2, 200.0)]
    state = syn_state(drivers, leader=60, scheduled=50)
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(state, 0)
    assert exc.value.reason == REASON_LEADER_EXCEEDS_SCHEDULED


def test_missing_pit_count_unavailable():
    drivers = [syn_driver("a", 2, 200.0, pit_stops_completed_so_far=None)]
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(syn_state(drivers), 0)
    assert exc.value.reason == REASON_MISSING_PIT_COUNT


def test_driver_lap_exceeds_leader_unavailable():
    drivers = [
        syn_driver("a", 2, 200.0),
        syn_driver("b", 5, 190.0),
    ]
    state = syn_state(drivers, leader=2)
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(state, 0)
    assert exc.value.reason == REASON_DRIVER_LAP_EXCEEDS_LEADER


def test_invalid_position_unavailable():
    drivers = [syn_driver("a", 2, 200.0, position=0)]
    with pytest.raises(SimulationUnavailableError) as exc:
        adapt(syn_state(drivers), 0)
    assert exc.value.reason == REASON_INVALID_POSITION


def test_no_none_is_flattened_to_zero():
    drivers = [
        syn_driver("a", 2, 200.0, position=None, compound=None,
                   tyre_life=None, stint_number=None),
    ]
    adapted = adapt(syn_state(drivers), 0)
    entry = adapted.drivers[0]
    assert entry.position is None
    assert entry.compound is None
    assert entry.tyre_age is None
    assert entry.stint_number is None


# ---------------------------------------------------------------------------
# Deterministic identity (R2-Q).
# ---------------------------------------------------------------------------

def test_same_race_state_same_identity():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    assert adapt(rs, 0).identity() == adapt(rs, 0).identity()


def test_repeated_adaptation_byte_identical():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    first = adapt(rs, index)
    second = adapt(rs, index)
    assert blob(first) == blob(second)
    assert first.to_dict() == second.to_dict()


def test_identity_changes_with_position():
    drivers_a = [syn_driver("a", 2, 200.0, position=1),
                 syn_driver("b", 1, 100.0, position=2)]
    drivers_b = [syn_driver("a", 2, 200.0, position=2),
                 syn_driver("b", 1, 100.0, position=1)]
    assert adapt(syn_state(drivers_a), 0).identity() != \
        adapt(syn_state(drivers_b), 0).identity()


def test_identity_changes_with_compound():
    drivers_a = [syn_driver("a", 2, 200.0, compound="SOFT")]
    drivers_b = [syn_driver("a", 2, 200.0, compound="HARD")]
    assert adapt(syn_state(drivers_a), 0).identity() != \
        adapt(syn_state(drivers_b), 0).identity()


def test_identity_changes_with_weather():
    drivers = [syn_driver("a", 2, 200.0)]
    dry = syn_state(drivers, weather=RS.WeatherState(air_temp_c=20.0))
    wet = syn_state(drivers, weather=RS.WeatherState(air_temp_c=30.0))
    assert adapt(dry, 0).identity() != adapt(wet, 0).identity()


def test_identity_changes_with_track_state():
    drivers = [syn_driver("a", 2, 200.0)]
    green = syn_state(drivers, track_state="all_clear")
    yellow = syn_state(drivers, track_state="yellow")
    assert adapt(green, 0).identity() != adapt(yellow, 0).identity()


def test_identity_changes_with_anchor_frame_index():
    _, _, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    assert adapt(rs, 0).identity() != adapt(rs, 5).identity()


def test_identity_tracks_simulation_time():
    early = syn_state([syn_driver("a", 2, 200.0)], T=200.0, anchor_lap=2)
    late = syn_state([syn_driver("a", 2, 999.0)], T=999.0, anchor_lap=2)
    assert adapt(early, 0).identity() != adapt(late, 0).identity()


def test_driver_input_order_does_not_change_identity():
    drivers = [syn_driver("a", 2, 200.0), syn_driver("b", 1, 100.0)]
    first = syn_state(drivers)
    second = syn_state(list(reversed(drivers)))
    assert adapt(first, 0).identity() == adapt(second, 0).identity()


def test_identity_has_no_walltime_or_process_state():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    payload = adapt(rs, index).to_dict()
    text = S.canonical_json(payload)
    for token in ("timestamp", "hostname", "pid", "uuid", "time.time"):
        assert token not in text


def test_state_identity_usable_in_request_identity():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, index)
    request = S.simulation_request_identity(
        adapted, S.SimulationConfig(100, 42), S.Assumptions())
    assert isinstance(request, str) and len(request) == 64


# ---------------------------------------------------------------------------
# Replay seam (R2-R).
# ---------------------------------------------------------------------------

def test_replay_seam_composes():
    service = make_service(2023, "2023-r01-R")
    frame = service.timeline.frame_at(100)
    state = service.state_at(frame.frame_index)
    adapted = from_race_state(state, anchor_frame_index=frame.frame_index)
    assert adapted.race_id == frame.race_id
    assert adapted.simulation_time_s == frame.anchor_state_time_s
    assert adapted.anchor_frame_index == frame.frame_index


def test_replay_seam_matches_direct_state():
    service = make_service(2022, "2022-r18-R")
    index = frame_index_for(service, "ocon", 2)
    frame = service.timeline.frame_at(index)
    state = service.state_at(index)
    from_frame = from_race_state(state, anchor_frame_index=frame.frame_index)
    direct = from_race_state(state)
    assert from_frame.drivers == direct.drivers
    assert from_frame.environment == direct.environment
    assert from_frame.simulation_time_s == direct.simulation_time_s
    assert from_frame.anchor_frame_index == frame.frame_index
    assert direct.anchor_frame_index is None


def test_adapter_source_does_not_import_replay():
    tree = ast.parse(ADAPTER_SOURCE_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    for name in imported:
        assert not name.startswith("v2.replay"), name
        assert not name.startswith("v2.replay_reconstruction"), name
        assert not name.startswith("v2.race_state_reconstruction"), name
    assert "v2.race_state" in imported


# ---------------------------------------------------------------------------
# Future-data adversarial suite (R2-U).
# ---------------------------------------------------------------------------

def _poison_future(states: pd.DataFrame, T: float) -> pd.DataFrame:
    """Mutate every strictly-future source row with extreme values."""
    mutated = states.copy()
    future = mutated["state_time_s"] > T
    assert future.any()
    fills = {
        "position": 99,
        "lap_number": 999,
        "compound": "SUPERSOFT",
        "tyre_life": 999,
        "stint_number": 99,
        "pit_stops_completed_so_far": 99,
        "laps_since_last_pit_stop": 99,
        "track_state": "red_flag",
        "flag_red": True,
        "flag_safety_car": True,
        "rc_last_message_category": "RedFlag",
        "wx_air_temp_c": -99.0,
        "wx_rainfall": True,
        "race_leader_laps_at_state": 999,
        "race_progress_frac": 9.99,
    }
    for column, value in fills.items():
        if column in mutated.columns:
            mutated.loc[future, column] = value
    # Labels / final results are not adapter inputs; poison them anyway.
    for column, value in (("position_final", 99), ("classified_position", 99),
                          ("status_text", "Retired"), ("dnf_flag", True),
                          ("is_winner", True), ("points", -1.0),
                          ("laps_completed", 999)):
        mutated[column] = value
    return mutated


def test_future_poison_leaves_adaptation_identical():
    states, results, meta = load_race(2023, "2023-r01-R")
    service = make_service(2023, "2023-r01-R")
    index = frame_index_for(service, "alonso", 28)
    T = service.timeline.frame_at(index).anchor_state_time_s
    baseline = adapt(service.state_at(index), index)
    expected = blob(baseline)
    expected_identity = baseline.identity()

    mutated = _poison_future(states, T)
    rebuilt = ReplayReconstructor(
        RP.build_replay_timeline(mutated),
        RaceStateReconstructor(mutated, results, race_meta=meta or None))
    index2 = frame_index_for(rebuilt, "alonso", 28)
    assert index2 == index
    after = adapt(rebuilt.state_at(index2), index2)
    # No leakage was detected under the implemented adversarial test suite.
    assert blob(after) == expected
    assert after.identity() == expected_identity


@pytest.mark.parametrize("season,race_id,driver,lap", [
    (2022, "2022-r07-R", "norris", 30),
    (2022, "2022-r18-R", "ocon", 2),
    (2020, "2020-r09-R", "giovinazzi", 6),
])
def test_future_poison_matrix(season, race_id, driver, lap):
    states, results, meta = load_race(season, race_id)
    service = make_service(season, race_id)
    index = frame_index_for(service, driver, lap)
    T = service.timeline.frame_at(index).anchor_state_time_s
    expected = blob(adapt(service.state_at(index), index))
    mutated = _poison_future(states, T)
    rebuilt = ReplayReconstructor(
        RP.build_replay_timeline(mutated),
        RaceStateReconstructor(mutated, results, race_meta=meta or None))
    index2 = frame_index_for(rebuilt, driver, lap)
    assert blob(adapt(rebuilt.state_at(index2), index2)) == expected


# ---------------------------------------------------------------------------
# Label / model firewall (R2-V) + 2025 boundary (R2-W).
# ---------------------------------------------------------------------------

def test_adapter_source_has_no_forbidden_tokens():
    text = ADAPTER_SOURCE_PATH.read_text()
    for token in ("v2.prediction", "v2.model_lab", "FrozenWinnerPredictor",
                  "v2.race_state_features", "replay_prediction",
                  "features_for_batch", "predict_proba", "sklearn", "joblib",
                  "fastapi", "import api", "from api",
                  "ORACLE_EVALUATION_ONLY", "HISTORICALLY_ESTIMATED"):
        assert token not in text, token


def test_adapter_source_imports_only_contracts():
    tree = ast.parse(ADAPTER_SOURCE_PATH.read_text())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            assert name.startswith(("v2.race_state", "v2.simulation",
                                    "__future__")), name


def test_adapter_runtime_import_firewall():
    probe = (
        "import sys, v2.simulation.adapter; "
        "forbidden={'v2.prediction','v2.model_lab','v2.race_state_features',"
        "'v2.replay','v2.replay_predictions',"
        "'v2.replay_probability_timeline','v2.replay_reconstruction',"
        "'sklearn','joblib','pandas','fastapi','api'}; "
        "bad=sorted(m for m in sys.modules "
        "if m in forbidden or m.split('.')[0] in forbidden); "
        "print('BAD='+','.join(bad) if bad else 'CLEAN')")
    result = subprocess.run([sys.executable, "-c", probe],
                            capture_output=True, text=True,
                            cwd=str(ROOT), timeout=120)
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


def test_adapter_source_has_no_2025_literals():
    text = ADAPTER_SOURCE_PATH.read_text()
    assert "2025" not in text


def test_2025_scope_enforced_at_serving_boundary():
    from api.v2_service import SERVED_SEASONS
    assert 2025 not in SERVED_SEASONS
    assert tuple(SERVED_SEASONS) == tuple(range(2018, 2025))


# ---------------------------------------------------------------------------
# Provenance (R2-P) and R1 refinement regression (R2-Z).
# ---------------------------------------------------------------------------

def test_adapter_provenance_identity():
    assert ADAPTER_PROVENANCE is S.Provenance.FACTUAL_AT_T
    assert ADAPTER_SOURCE.startswith("v2.race_state")


def test_adaptation_is_factual_not_oracle():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    adapted = adapt(rs, index)
    # Every adapted value traces to the factual RaceState at T.
    assert adapted.simulation_time_s == rs.state_time_s
    by_id = {d.driver_id: d for d in adapted.drivers}
    for entry in rs.observable_drivers:
        assert by_id[entry.driver_id].race_time_s <= rs.state_time_s


def test_r1_nullable_tyre_age_regression():
    entry = S.DriverSimState("a", 2, 200.0, tyre_age=None)
    assert entry.tyre_age is None
    with pytest.raises(S.SimulationValidationError):
        S.DriverSimState("a", 2, 200.0, tyre_age=-1)


# ---------------------------------------------------------------------------
# Ordinary / edge fixtures all green.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season,race_id,driver,lap", [
    (2023, "2023-r01-R", "alonso", 28),
    (2021, "2021-r12-R", "hamilton", 2),
    (2022, "2022-r18-R", "ocon", 2),
    (2022, "2022-r07-R", "norris", 30),
    (2020, "2020-r09-R", "giovinazzi", 6),
])
def test_fixture_adapts_green(season, race_id, driver, lap):
    service, index, rs = race_state_for(season, race_id, driver, lap)
    adapted = adapt(rs, index)
    assert adapted.roster_size == rs.roster_size
    assert adapted.simulation_time_s == rs.state_time_s
    assert adapted.leader_laps_done == \
        rs.race_context.race_leader_laps_at_state
    assert all(d.status is S.DriverStatus.ACTIVE for d in adapted.drivers)
    assert all(d.lap_number <= adapted.leader_laps_done
               for d in adapted.drivers)


def test_all_fixtures_byte_deterministic():
    for season, race_id, driver, lap in [
            (2023, "2023-r01-R", "alonso", 28),
            (2021, "2021-r12-R", "hamilton", 2),
            (2022, "2022-r18-R", "ocon", 2),
            (2022, "2022-r07-R", "norris", 30)]:
        service, index, rs = race_state_for(season, race_id, driver, lap)
        assert blob(adapt(rs, index)) == blob(adapt(rs, index))


# ---------------------------------------------------------------------------
# Performance smoke (R2-AA; informational, generous bound).
# ---------------------------------------------------------------------------

def test_adapter_performance_smoke():
    _, index, rs = race_state_for(2023, "2023-r01-R", "alonso", 28)
    from_race_state(rs, anchor_frame_index=index)  # warm
    samples = []
    for _ in range(200):
        start = time.perf_counter()
        from_race_state(rs, anchor_frame_index=index)
        samples.append(time.perf_counter() - start)
    samples.sort()
    mean = sum(samples) / len(samples)
    p50 = samples[len(samples) // 2]
    p95 = samples[int(0.95 * (len(samples) - 1))]
    print(f"\nR2 adapter perf (n=200): mean/p50/p95 "
          f"{mean*1000:.3f}/{p50*1000:.3f}/{p95*1000:.3f} ms")
    assert p95 < 0.05

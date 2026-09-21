"""Phase-6 R4 tests — deterministic race-evolution kernel.

Covers start-state validation, the explicit red/SC/VSC/yellow/wet rejection
taxonomy, the null tyre-age policy, parameter selection/fallback, the
race-progress and degradation effects (sign, reference, support clamp), the
absence of any invented compound effect, event-driven lap/race-time evolution,
lapped-car semantics, deterministic ordering and ties, tyre-age evolution, the
no-pit policy, race completion/classification, zero-noise determinism, seed
independence, the parameter temporal policy, the canonical-data/model/replay
firewall, the hard iteration bound, the last-frame completion smoke, and a
performance smoke.

The deterministic kernel uses no RNG and no canonical data; the real-data
fixtures go through the frozen Phase-5 replay seam purely to build a factual
``SimulationState``.
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

from v2 import replay as RP
from v2.race_state import WeatherState
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_reconstruction import ReplayReconstructor
from v2.simulation import engine as E
from v2.simulation.adapter import from_race_state
from v2.simulation.config import (
    Assumptions,
    ParameterIdentity,
    SimulationConfig,
    simulation_request_identity,
)
from v2.simulation.engine import (
    ENGINE_UNSUPPORTED_REASONS,
    ExecutionPolicy,
    SimulationUnsupportedError,
    expected_lap_time_s,
    max_lap_events,
    select_pace_parameters,
)
from v2.simulation.errors import SimulationContractError
from v2.simulation.params import (
    ELIGIBILITY_RULE_VERSION,
    ESTIMATOR_VERSION,
    FAMILY_NAMES,
    PARAMETER_CONTRACT_VERSION,
    PARAMETER_SET_ID,
    ParameterFamily,
    SimulationParameterSet,
    SupportEntry,
    load_simulation_parameters,
)
from v2.simulation.results import SimulationRunResult
from v2.simulation.state import (
    DriverSimState,
    DriverStatus,
    SimulationEnvironment,
    SimulationState,
    canonical_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = REPO_ROOT / "v2" / "simulation" / "engine.py"
ARTIFACT_DIR = (REPO_ROOT / "data" / "v2" / "simulation" / "params"
                / "r3-v1__through-2024")

D9 = (str(REPO_ROOT) + "/data/v2/processed/driver_lap_state_d9/season="
      "{season}/driver_lap_state_d9__d9-{season}.parquet")
RESULTS = (str(REPO_ROOT) + "/data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = (str(REPO_ROOT) + "/data/v2/processed/races/season={season}/"
         "races__{race}.parquet")


# ---------------------------------------------------------------------------
# Synthetic parameter artifact (only the families R4 consumes).
# ---------------------------------------------------------------------------

def _scalar(value, *, support="strong", fallback="exact", ident="identified",
            samples=1000):
    return SupportEntry(group_key="g", sample_count=samples,
                        support_level=support, fallback_level=fallback,
                        value=value, identifiability=ident)


def _dist(observed_max, *, samples=1000):
    return SupportEntry(
        group_key="g", sample_count=samples, support_level="strong",
        fallback_level="global", probabilities=(0.5,),
        quantile_values=(observed_max / 2.0,),
        observed_min=1.0, observed_max=observed_max)


def make_params(*, base=90.0, circuit="syn", era="2018-2021", season=2019,
                offset=0.0, offsets=None, progress=-0.05, degradation=0.02,
                age_max=40.0, through=2024,
                seasons=tuple(range(2018, 2025)), constructors=("c1",),
                base_exact=True, base_circuit=True):
    families = {name: ParameterFamily(name, "unit", {}) for name in FAMILY_NAMES}
    base_entries = {}
    if base_exact:
        base_entries[f"{circuit}|{era}"] = _scalar(base, fallback="exact")
    families["pace_base_s"] = ParameterFamily(
        "pace_base_s", "seconds", base_entries)
    fallback = {}
    if base_circuit:
        fallback[circuit] = _scalar(base, fallback="circuit")
    fallback["global"] = _scalar(base, support="weak", fallback="global")
    families["pace_base_fallback_s"] = ParameterFamily(
        "pace_base_fallback_s", "seconds", fallback)
    if offsets is None:
        offsets = {constructor: offset for constructor in constructors}
    offset_entries = {}
    for constructor, value in offsets.items():
        offset_entries[f"{constructor}|{season}"] = _scalar(
            value, fallback="exact")
        offset_entries[f"{constructor}|{era}"] = _scalar(
            value, fallback="era")
    offset_entries["global"] = _scalar(0.0, fallback="global")
    families["constructor_pace_offset_s"] = ParameterFamily(
        "constructor_pace_offset_s", "seconds", offset_entries)
    families["race_progress_slope_s_per_lap"] = ParameterFamily(
        "race_progress_slope_s_per_lap", "seconds_per_lap",
        {era: _scalar(progress, fallback="era"),
         "global": _scalar(progress, fallback="global")})
    families["degradation_slope_s_per_lap"] = ParameterFamily(
        "degradation_slope_s_per_lap", "seconds_per_lap",
        {era: _scalar(degradation, fallback="era"),
         "global": _scalar(degradation, fallback="global")})
    families["stint_length_laps"] = ParameterFamily(
        "stint_length_laps", "laps", {"global": _dist(age_max)})
    return SimulationParameterSet(
        parameter_contract_version=PARAMETER_CONTRACT_VERSION,
        estimator_version=ESTIMATOR_VERSION,
        eligibility_rule_version=ELIGIBILITY_RULE_VERSION,
        parameter_set_id=PARAMETER_SET_ID,
        through_season=through,
        estimation_seasons=seasons,
        source_data={}, regimes={}, policies={}, grouping_hierarchy={},
        support_thresholds={}, families=families, diagnostics={},
        creation_metadata={})


# ---------------------------------------------------------------------------
# Synthetic SimulationState builders.
# ---------------------------------------------------------------------------

def sim_driver(driver_id, *, lap, race_time, age=1, compound="HARD",
               position=1, constructor="c1", pit_count=0, status=None,
               observation_age=None):
    return DriverSimState(
        driver_id=driver_id, lap_number=lap, race_time_s=race_time,
        position=position, compound=compound, tyre_age=age, stint_number=1,
        pit_count=pit_count, constructor_id=constructor,
        status=status if status is not None else DriverStatus.ACTIVE,
        observation_age_s=observation_age)


def sim_state(drivers, *, scheduled=10, leader=None, T=None,
              track="all_clear", weather=None, season=2019, circuit="syn",
              race_id="SYN-R"):
    drivers = tuple(drivers)
    if leader is None:
        leader = max(d.lap_number for d in drivers)
    if T is None:
        T = max(d.race_time_s for d in drivers)
    return SimulationState(
        race_id=race_id, scheduled_laps=scheduled, leader_laps_done=leader,
        simulation_time_s=T, drivers=drivers,
        environment=SimulationEnvironment(track_state=track, weather=weather),
        season=season, round_no=1, circuit_id=circuit)


def one_driver(*, lap=3, race_time=100.0, age=1, compound="HARD",
               position=1, constructor="c1", pit_count=0, status=None,
               observation_age=None, scheduled=10, leader=None, T=None,
               track="all_clear", weather=None, season=2019, circuit="syn",
               race_id="SYN-R"):
    driver = sim_driver(
        "a", lap=lap, race_time=race_time, age=age, compound=compound,
        position=position, constructor=constructor, pit_count=pit_count,
        status=status, observation_age=observation_age)
    return sim_state([driver], scheduled=scheduled, leader=leader, T=T,
                     track=track, weather=weather, season=season,
                     circuit=circuit, race_id=race_id)


def run(state, params, **kwargs):
    return E.DeterministicRaceEngine().run(state, params, **kwargs)


def blob(result: SimulationRunResult) -> str:
    return canonical_json(result.to_dict())


# ===========================================================================
# R4-D start-state validation.
# ===========================================================================

def test_unsupported_reasons_are_unique_lowercase_and_stable():
    assert len(ENGINE_UNSUPPORTED_REASONS) == len(
        set(ENGINE_UNSUPPORTED_REASONS))
    for token in ENGINE_UNSUPPORTED_REASONS:
        assert isinstance(token, str) and token
        assert token == token.lower()


def test_unsupported_error_rejects_unknown_reason():
    with pytest.raises(SimulationContractError):
        SimulationUnsupportedError("not_a_reason", "x")


def test_wrong_input_types_raise_contract_error():
    params = make_params()
    with pytest.raises(SimulationContractError):
        run("nope", params)
    with pytest.raises(SimulationContractError):
        run(one_driver(), {"not": "params"})
    with pytest.raises(SimulationContractError):
        select_pace_parameters(one_driver(), object())


def test_supported_state_is_valid_with_one_winner():
    params = make_params()
    state = sim_state([
        sim_driver("a", lap=3, race_time=100.0, constructor="c1"),
        sim_driver("b", lap=3, race_time=101.0, constructor="c1"),
    ], scheduled=6, leader=3)
    result = run(state, params)
    assert result.valid
    order = result.classification
    assert order.finishing_order[0] == order.entries[0].driver_id
    assert order.classified_count == 2
    positions = sorted(e.finish_position for e in order.entries
                       if e.classified)
    assert positions == [1, 2]
    assert order.entries[0].laps_completed == 6


def test_leader_progress_must_be_represented():
    state = sim_state([sim_driver("a", lap=3, race_time=100.0)],
                      scheduled=6, leader=5)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_LEADER_PROGRESS_NOT_REPRESENTED


# ===========================================================================
# R4-F/G red / SC / VSC / yellow policy.
# ===========================================================================

@pytest.mark.parametrize("bad,reason", [
    ("red_flag", E.REASON_RED_FLAG_TRACK_STATE),
    ("safety_car", E.REASON_NEUTRALIZED_TRACK_STATE),
    ("vsc", E.REASON_NEUTRALIZED_TRACK_STATE),
    ("vsc_ending", E.REASON_NEUTRALIZED_TRACK_STATE),
    ("yellow", E.REASON_NEUTRALIZED_TRACK_STATE),
    (None, E.REASON_UNKNOWN_TRACK_STATE),
])
def test_unsupported_track_states_are_rejected(bad, reason):
    state = one_driver(track=bad)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == reason


def test_red_checked_before_wet():
    # red + rainfall: the red-flag rejection is the stable reason surfaced.
    state = one_driver(track="red_flag",
                       weather=WeatherState(rainfall=True))
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_RED_FLAG_TRACK_STATE


def test_engine_never_silently_converts_sc_to_green():
    state = one_driver(track="safety_car")
    with pytest.raises(SimulationUnsupportedError):
        run(state, make_params())


# ===========================================================================
# R4-H wet policy.
# ===========================================================================

def test_rainfall_active_state_is_rejected():
    state = one_driver(weather=WeatherState(rainfall=True))
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_WET_TRACK_CONDITIONS


@pytest.mark.parametrize("compound", ["WET", "INTERMEDIATE"])
def test_wet_compound_state_is_rejected(compound):
    state = one_driver(compound=compound)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_WET_COMPOUND_STATE


def test_dry_state_with_null_compound_is_supported():
    # Compound has no R4 pace effect, so a missing token is not wet-running.
    state = one_driver(compound=None)
    assert run(state, make_params()).valid


# ===========================================================================
# R4-T null tyre age / R4-D retired policy.
# ===========================================================================

def test_missing_tyre_age_is_rejected_not_zeroed():
    state = one_driver(age=None)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_MISSING_TYRE_AGE


def test_retired_driver_is_rejected():
    state = sim_state([
        sim_driver("a", lap=3, race_time=100.0),
        sim_driver("b", lap=3, race_time=101.0,
                   status=DriverStatus.RETIRED),
    ], scheduled=6, leader=3)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, make_params())
    assert excinfo.value.reason == E.REASON_RETIRED_DRIVER


# ===========================================================================
# R4-Z parameter selection / fallback.
# ===========================================================================

def test_selection_uses_exact_circuit_era_base():
    params = make_params(base=88.0)
    selection = select_pace_parameters(one_driver(), params)
    assert selection.base.key == "syn|2018-2021"
    assert selection.base.value == 88.0
    assert selection.base.fallback_level == "exact"
    assert selection.era == "2018-2021"
    assert selection.progress.key == "2018-2021"
    assert selection.degradation.key == "2018-2021"


def test_selection_falls_back_to_circuit_then_global():
    no_exact = make_params(base=91.0, base_exact=False)
    selection = select_pace_parameters(one_driver(), no_exact)
    assert selection.base.key == "syn"
    assert selection.base.fallback_level == "circuit"

    global_only = make_params(base=92.0, base_exact=False,
                              base_circuit=False)
    selection = select_pace_parameters(one_driver(circuit="unknown"),
                                       global_only)
    assert selection.base.key == "global"
    assert selection.base.support_level == "weak"


def test_selection_uses_per_driver_constructor_offset():
    state = sim_state([
        sim_driver("a", lap=2, race_time=100.0, constructor="c1"),
        sim_driver("b", lap=2, race_time=101.0, constructor="c9"),
    ], scheduled=5, leader=2)
    params = make_params(constructors=("c1",), offset=0.5)
    selection = select_pace_parameters(state, params)
    assert selection.offset_for("c1").value == 0.5
    assert selection.offset_for("c9").value == 0.0  # global zero fallback
    assert selection.offset_for(None).value == 0.0


def test_selection_is_deterministic():
    params = make_params()
    first = select_pace_parameters(one_driver(), params).to_dict()
    second = select_pace_parameters(one_driver(), params).to_dict()
    assert first == second


# ===========================================================================
# R4-K/L expected pace and progress reference.
# ===========================================================================

def test_expected_lap_time_equation_and_clamping():
    state = sim_state([sim_driver("a", lap=10, race_time=100.0, age=11)],
                      scheduled=20, leader=10)
    params = make_params(base=90.0, offset=0.0, progress=0.0, degradation=0.1,
                         age_max=12.0)
    selection = select_pace_parameters(state, params)
    base_pace = selection.base.value + selection.offset_for("c1").value
    mu, progress_adj, degradation_adj = expected_lap_time_s(
        selection, base_pace, next_lap=11, next_age=13, anchor_age=11)
    assert progress_adj == 0.0
    assert degradation_adj == pytest.approx(0.1)  # clamped at support max 12
    assert mu == pytest.approx(90.1)


def test_progress_adjustment_uses_leader_reference_and_sign():
    state = sim_state([
        sim_driver("a", lap=5, race_time=100.0),
        sim_driver("b", lap=3, race_time=100.0),
    ], scheduled=8, leader=5)
    params = make_params(progress=-0.05, degradation=0.0, offset=0.0)
    trace: list = []
    run(state, params, trace=trace)
    events = [r for r in trace if r["kind"] == "event"]
    first = {}
    for record in events:
        first.setdefault(record["driver_id"], record)
    # Reference is the factual leader progress at T (5).
    assert first["a"]["from_lap"] == 5
    assert first["a"]["progress_adjustment_s"] == pytest.approx(-0.05)
    assert first["b"]["from_lap"] == 3
    assert first["b"]["progress_adjustment_s"] == pytest.approx(0.05)
    assert first["b"]["progress_adjustment_s"] > 0.0


def test_progress_trend_negative_slows_later_laps():
    state = one_driver(lap=0, race_time=0.0)
    params = make_params(progress=-0.1, degradation=0.0, offset=0.0)
    trace: list = []
    run(sim_state([sim_driver("a", lap=0, race_time=0.0)], scheduled=4,
                  leader=0), params, trace=trace)
    events = [r for r in trace if r["kind"] == "event"]
    adjustments = [r["progress_adjustment_s"] for r in events]
    assert adjustments == sorted(adjustments, reverse=True)
    assert adjustments[-1] < adjustments[0]


# ===========================================================================
# R4-M degradation effect + support clamp.
# ===========================================================================

def test_degradation_grows_with_tyre_age():
    state = one_driver(lap=0, race_time=0.0, age=0)
    params = make_params(degradation=0.1, progress=0.0, age_max=40.0)
    trace: list = []
    run(state, params, trace=trace)
    adjustments = [r["degradation_adjustment_s"] for r in trace
                   if r["kind"] == "event"]
    assert adjustments == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6,
                                         0.7, 0.8, 0.9, 1.0])


def test_degradation_is_clamped_to_observed_age_support():
    state = one_driver(lap=0, race_time=0.0, age=9)
    params = make_params(degradation=0.1, progress=0.0, age_max=12.0)
    trace: list = []
    run(state, params, trace=trace)
    adjustments = [r["degradation_adjustment_s"] for r in trace
                   if r["kind"] == "event"]
    # age reaches the observed max (12) after three laps and stops growing.
    assert adjustments == pytest.approx([0.1, 0.2, 0.3] + [0.3] * 7)


def test_age_support_proxy_comes_from_stint_length_family():
    state = one_driver(lap=0, race_time=0.0, age=0)
    params = make_params(degradation=0.05, progress=0.0, age_max=40.0)
    selection = select_pace_parameters(state, params)
    assert selection.age_support_max_laps == 40.0


def test_no_negative_or_zero_lap_time_when_degradation_is_positive():
    state = one_driver(lap=0, race_time=0.0, age=0)
    params = make_params(degradation=0.05, progress=0.0)
    assert run(state, params).valid


# ===========================================================================
# R4-N compound has no invented effect.
# ===========================================================================

def test_compound_does_not_change_result_or_selection():
    compounds = ["SOFT", "MEDIUM", "HARD", None]
    params = make_params()
    results = []
    for compound in compounds:
        state = one_driver(compound=compound)
        result = run(state, params)
        results.append(canonical_json(result.classification.to_dict()))
    assert len(set(results)) == 1


def test_engine_ignores_a_poisoned_compound_offset_family():
    # Even an absurd compound offset entry must not change the evolution.
    state = one_driver(compound="SOFT")
    clean = make_params()
    payload = clean.to_dict()
    payload["families"]["compound_offset_s"] = ParameterFamily(
        "compound_offset_s", "seconds",
        {"SOFT": _scalar(1000.0)}).to_dict()
    poisoned = SimulationParameterSet.from_dict(payload)
    clean_result = run(state, clean)
    poisoned_result = run(state, poisoned)
    assert canonical_json(clean_result.classification.to_dict()) == \
        canonical_json(poisoned_result.classification.to_dict())


# ===========================================================================
# R4-O/P/Q evolution semantics: laps, clock, lapped cars.
# ===========================================================================

def test_lap_and_race_time_evolve_monotonically():
    state = one_driver(lap=2, race_time=100.0, age=2)
    params = make_params()
    trace: list = []
    result = run(state, params, trace=trace)
    assert result.valid
    events = [r for r in trace if r["kind"] == "event"]
    assert [r["to_lap"] for r in events] == [3, 4, 5, 6, 7, 8, 9, 10]
    assert all(r["race_time_s"] >= 100.0 for r in events)
    times = [r["race_time_s"] for r in events]
    assert times == sorted(times)


def test_lapped_cars_finish_on_their_own_lap_count():
    # A zero progress trend keeps the three identical cars in lockstep so the
    # lapped-car semantics are isolated from the pace trend.
    state = sim_state([
        sim_driver("a", lap=5, race_time=100.0),
        sim_driver("b", lap=4, race_time=100.0),
        sim_driver("c", lap=3, race_time=100.0),
    ], scheduled=7, leader=5)
    result = run(state, make_params(progress=0.0))
    laps = {e.driver_id: e.laps_completed
            for e in result.classification.entries}
    assert laps == {"a": 7, "b": 6, "c": 5}
    assert result.classification.finishing_order[0] == "a"


def test_race_completion_is_leader_based_and_finite():
    state = sim_state([
        sim_driver("a", lap=4, race_time=100.0),
        sim_driver("b", lap=1, race_time=100.0),
    ], scheduled=8, leader=4)
    result = run(state, make_params())
    winner = result.classification.entries[0]
    assert winner.driver_id == "a"
    assert winner.laps_completed == 8
    assert result.classification.entries[1].laps_completed < 8


def test_event_order_never_grants_a_lapped_driver_a_leader_lap():
    state = sim_state([
        sim_driver("leader", lap=6, race_time=200.0),
        sim_driver("lapped", lap=4, race_time=200.0),
    ], scheduled=9, leader=6)
    result = run(state, make_params())
    laps = {e.driver_id: e.laps_completed for e in result.classification.entries}
    assert laps["leader"] - laps["lapped"] >= 2


# ===========================================================================
# R4-R ordering and deterministic ties.
# ===========================================================================

def test_ordering_is_by_laps_then_time_then_driver_id():
    state = sim_state([
        sim_driver("a", lap=5, race_time=100.0),
        sim_driver("b", lap=4, race_time=100.0),
        sim_driver("c", lap=4, race_time=130.0),
    ], scheduled=8, leader=5)
    trace: list = []
    result = run(state, make_params(), trace=trace)
    final = {r["driver_id"]: r for r in trace if r["kind"] == "final"}
    expected = sorted(
        final.values(),
        key=lambda r: (-r["lap_number"], r["race_time_s"], r["driver_id"]))
    assert [e.driver_id for e in result.classification.entries] == \
        [r["driver_id"] for r in expected]


def test_lapped_field_time_ordering_ascending(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    result = run(state, real_params)
    by_laps: dict = {}
    for entry in result.classification.entries:
        by_laps.setdefault(entry.laps_completed, []).append(entry.race_time_s)
    for times in by_laps.values():
        assert times == sorted(times)


def test_exact_tie_is_broken_by_driver_id():
    state = sim_state([
        sim_driver("b", lap=0, race_time=0.0, age=1),
        sim_driver("a", lap=0, race_time=0.0, age=1),
    ], scheduled=2, leader=0)
    result = run(state, make_params())
    assert result.classification.finishing_order == ("a", "b")
    assert all(e.laps_completed == 2 for e in result.classification.entries)


def test_free_air_ordering_can_reorder_by_sustained_pace():
    # 'b' starts ahead on the clock, but 'a' is on a faster constructor and
    # legally completes the final lap first (no overtake model involved).
    state = sim_state([
        sim_driver("a", lap=0, race_time=10.0, constructor="fast"),
        sim_driver("b", lap=0, race_time=0.0, constructor="slow"),
    ], scheduled=3, leader=0)
    params = make_params(offsets={"fast": -5.0, "slow": 0.0})
    result = run(state, params)
    assert result.classification.finishing_order[0] == "a"


def test_small_field_race_completes():
    state = sim_state([
        sim_driver("a", lap=1, race_time=50.0),
        sim_driver("b", lap=0, race_time=10.0),
    ], scheduled=3, leader=1)
    result = run(state, make_params())
    assert result.classification.classified_count == 2
    assert result.classification.retired_count == 0


# ===========================================================================
# R4-S/T tyre age and no-pit policy.
# ===========================================================================

def test_tyre_age_increments_with_completed_laps():
    state = one_driver(lap=2, race_time=100.0, age=4)
    trace: list = []
    run(state, make_params(), trace=trace)
    final = {r["driver_id"]: r for r in trace if r["kind"] == "final"}
    assert final["a"]["tyre_age"] == 4 + (10 - 2)


def test_no_pitting_preserves_pit_count_and_compound():
    state = one_driver(lap=0, race_time=0.0, pit_count=2, compound="MEDIUM")
    trace: list = []
    run(state, make_params(), trace=trace)
    final = {r["driver_id"]: r for r in trace if r["kind"] == "final"}
    assert final["a"]["pit_count"] == 2
    assert final["a"]["compound"] == "MEDIUM"


# ===========================================================================
# R4-W classification / R4-X result contract.
# ===========================================================================

def test_result_accounts_for_every_driver_exactly_once():
    drivers = [sim_driver(f"d{i}", lap=2, race_time=100.0 + i)
               for i in range(6)]
    state = sim_state(drivers, scheduled=5, leader=2)
    result = run(state, make_params())
    assert result.valid
    order = result.classification
    assert sorted(e.driver_id for e in order.entries) == \
        sorted(d.driver_id for d in drivers)
    assert order.roster_size == 6
    assert order.classified_count == 6
    assert order.retired_count == 0


def test_invalid_run_carries_reason_and_no_classification():
    # A nonpositive anchor pace drives expected lap time nonpositive.
    state = one_driver(lap=0, race_time=0.0, age=0)
    params = make_params(base=-1000.0, progress=0.0, degradation=0.0)
    result = run(state, params)
    assert result.valid is False
    assert result.classification is None
    assert result.invalid_reason == E.REASON_NONPOSITIVE_LAP_TIME


# ===========================================================================
# R4-Y zero-noise determinism and RNG independence.
# ===========================================================================

def test_repeated_runs_are_byte_identical():
    state = sim_state([
        sim_driver("a", lap=3, race_time=100.0, age=2),
        sim_driver("b", lap=2, race_time=90.0, age=5),
    ], scheduled=8, leader=3)
    params = make_params()
    first = blob(run(state, params))
    second = blob(run(state, params))
    third = blob(E.DeterministicRaceEngine().run(state, params))
    assert first == second == third


def test_master_seed_has_no_effect_on_the_kernel():
    state = one_driver(lap=1, race_time=100.0)
    params = make_params()
    config_a = SimulationConfig(simulation_count=1, master_seed=1)
    config_b = SimulationConfig(simulation_count=1, master_seed=2)
    assumptions = Assumptions()
    identity_a = simulation_request_identity(
        state, config_a, assumptions, ParameterIdentity.contract_only())
    identity_b = simulation_request_identity(
        state, config_b, assumptions, ParameterIdentity.contract_only())
    assert identity_a != identity_b  # request identity does depend on seed
    assert blob(run(state, params)) == blob(run(state, params))


def test_engine_source_uses_no_rng():
    text = ENGINE_PATH.read_text(encoding="utf-8")
    for token in ("np.random", "import random", "from random", "numpy",
                  "uuid", "time.time", "perf_counter"):
        assert token not in text, token


def test_simulation_id_is_deterministic_and_seed_free():
    state = one_driver(lap=1, race_time=100.0)
    params = make_params()
    first = run(state, params)
    second = run(state, params)
    assert first.simulation_id == second.simulation_id
    assert first.simulation_index == 0


# ===========================================================================
# R4-AB numerical safety and iteration bound.
# ===========================================================================

def test_max_lap_events_is_structural():
    assert max_lap_events(20, 57) == 20 * 57 + 20
    assert max_lap_events(1, 1) == 2


def test_event_count_stays_within_bound():
    drivers = [sim_driver(f"d{i}", lap=0, race_time=0.0)
               for i in range(5)]
    state = sim_state(drivers, scheduled=6, leader=0)
    trace: list = []
    run(state, make_params(), trace=trace)
    events = [r for r in trace if r["kind"] == "event"]
    assert len(events) <= max_lap_events(5, 6)


def test_nonfinite_lap_time_is_rejected():
    # A finite-but-enormous progress slope overflows the expected lap time.
    params = make_params(base=90.0, progress=1e308, degradation=0.0)
    state = sim_state([sim_driver("a", lap=0, race_time=0.0, age=0)],
                      scheduled=3, leader=0)
    result = run(state, params)
    assert result.valid is False
    assert result.invalid_reason in (
        E.REASON_NONFINITE_LAP_TIME, E.REASON_NONPOSITIVE_LAP_TIME,
        E.REASON_NONFINITE_RACE_TIME)


# ===========================================================================
# R4-AD/AE parameter temporal policy.
# ===========================================================================

def test_retrospective_product_allows_in_window_parameters():
    params = make_params(through=2024)
    state = one_driver()
    selection = select_pace_parameters(state, params)
    assert selection.leakage_free is False
    result = run(state, params,
                 execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert result.valid


def test_historical_backtest_rejects_future_estimated_parameters():
    params = make_params(through=2024)
    state = one_driver()
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, params,
            execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    assert excinfo.value.reason == E.REASON_PARAMETER_TEMPORAL_LEAK


def test_historical_backtest_allows_prior_estimated_parameters():
    params = make_params(through=2018, seasons=(2018,))
    state = one_driver()
    selection = select_pace_parameters(state, params)
    assert selection.leakage_free is True
    assert run(state, params,
               execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST).valid


def test_bad_execution_policy_rejected():
    params = make_params()
    with pytest.raises(SimulationContractError):
        run(one_driver(), params, execution_policy="backtest")


# ===========================================================================
# R4-AC canonical-data / model / replay firewall.
# ===========================================================================

def _imported_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_engine_imports_only_contracts():
    modules = _imported_modules(ENGINE_PATH)
    roots = {m.split(".")[0] for m in modules}
    assert roots <= {"__future__", "math", "dataclasses", "enum", "typing",
                     "v2"}
    v2_modules = {m for m in modules if m.startswith("v2")}
    assert all(m.startswith("v2.simulation") for m in v2_modules)


@pytest.mark.parametrize("forbidden", [
    "pandas", "numpy", "sklearn", "joblib", "fastapi",
    "v2.race_state", "v2.replay", "v2.replay_predictions",
    "v2.replay_probability_timeline", "v2.prediction", "v2.model_lab", "api",
])
def test_engine_has_no_forbidden_imports(forbidden):
    modules = _imported_modules(ENGINE_PATH)
    assert not any(m == forbidden or m.startswith(forbidden + ".")
                   for m in modules)


def test_engine_source_has_no_canonical_data_tokens():
    text = ENGINE_PATH.read_text(encoding="utf-8")
    for token in ("driver_lap_state_d9", "race_driver_labels", "read_parquet",
                  "data/v2", "results__", "winner_logreg", "is_winner",
                  "final_position"):
        assert token not in text, token


def test_runtime_import_firewall():
    code = (
        "import sys\n"
        "import v2.simulation.engine\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "{'pandas', 'sklearn', 'joblib', 'fastapi'}] + "
        "[m for m in sys.modules if m.startswith('v2.replay') or "
        "m.startswith('v2.model_lab') or m.startswith('v2.prediction')]\n"
        "assert not bad, bad\n"
    )
    result = subprocess.run([sys.executable, "-c", code],
                            cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ===========================================================================
# R4-AF representative real-data fixtures (frozen Phase-5 replay seam).
# ===========================================================================

@functools.lru_cache(maxsize=None)
def _load_race(season, race_id):
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
def _service(season, race_id):
    states, results, meta = _load_race(season, race_id)
    return ReplayReconstructor(
        RP.build_replay_timeline(states),
        RaceStateReconstructor(states, results, race_meta=meta or None))


def _frame_index(service, driver, lap):
    for frame in service.timeline.frames:
        if (frame.anchor_driver_id == driver
                and frame.anchor_lap_number == lap):
            return frame.frame_index
    raise AssertionError(f"anchor {(driver, lap)} not found")


@functools.lru_cache(maxsize=None)
def _real_state(season, race_id, driver, lap):
    service = _service(season, race_id)
    index = _frame_index(service, driver, lap)
    return from_race_state(service.state_at(index), anchor_frame_index=index)


@pytest.fixture(scope="session")
def real_params():
    return load_simulation_parameters(ARTIFACT_DIR)


@pytest.mark.parametrize("season,race,driver,lap", [
    (2022, "2022-r01-R", "perez", 30),
    (2022, "2022-r01-R", "russell", 38),
])
def test_real_mid_and_late_race_are_supported(real_params, season, race,
                                              driver, lap):
    state = _real_state(season, race, driver, lap)
    result = run(state, real_params)
    assert result.valid
    order = result.classification
    assert order.roster_size == state.roster_size
    assert order.classified_count == state.roster_size
    assert order.retired_count == 0
    assert order.entries[0].laps_completed == state.scheduled_laps
    assert sum(1 for e in order.entries if e.laps_completed
               == state.scheduled_laps) == 1


def test_real_yellow_anchor_is_rejected(real_params):
    state = _real_state(2020, "2020-r09-R", "giovinazzi", 6)
    assert state.environment.track_state == "yellow"
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, real_params)
    assert excinfo.value.reason == E.REASON_NEUTRALIZED_TRACK_STATE


def test_real_red_flag_anchor_is_rejected(real_params):
    state = _real_state(2021, "2021-r12-R", "russell", 3)
    assert state.environment.track_state == "red_flag"
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        run(state, real_params)
    assert excinfo.value.reason == E.REASON_RED_FLAG_TRACK_STATE


def test_real_selection_exposes_support_metadata(real_params):
    state = _real_state(2023, "2023-r01-R", "alonso", 28)
    selection = select_pace_parameters(state, real_params)
    assert selection.base.key == "bahrain|2022-2024"
    assert selection.base.fallback_level == "exact"
    assert selection.progress.value < 0.0
    assert selection.degradation.value > 0.0
    assert selection.age_support_max_laps is not None
    assert selection.parameter_through_season == 2024
    assert selection.target_season == 2023
    assert selection.leakage_free is False


def test_real_retrospective_run_is_deterministic(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    assert blob(run(state, real_params)) == blob(run(state, real_params))


# ===========================================================================
# R4-AG last-frame smoke (contract/completion only, not accuracy).
# ===========================================================================

def test_last_frame_requires_no_future_evolution(real_params):
    service = _service(2023, "2023-r07-R")
    last = service.timeline.frames[-1].frame_index
    state = from_race_state(service.state_at(last), anchor_frame_index=last)
    assert state.leader_laps_done == state.scheduled_laps
    trace: list = []
    result = run(state, real_params, trace=trace)
    assert result.valid
    assert not [r for r in trace if r["kind"] == "event"]
    order = result.classification
    assert order.roster_size == state.roster_size
    assert order.classified_count == state.roster_size
    assert order.entries[0].laps_completed == state.scheduled_laps
    assert order.finishing_order[0] is not None
    # No future evolution: each driver keeps its own factual completed laps.
    factual_laps = {d.driver_id: d.lap_number for d in state.drivers}
    assert {e.driver_id: e.laps_completed for e in order.entries} == \
        factual_laps


# ===========================================================================
# R4-AH performance smoke.
# ===========================================================================

def test_single_run_performance_smoke(real_params):
    state = _real_state(2022, "2022-r01-R", "russell", 38)
    engine = E.DeterministicRaceEngine()
    start = time.perf_counter()
    for _ in range(10):
        engine.run(state, real_params)
    elapsed = (time.perf_counter() - start) / 10
    assert elapsed < 1.0

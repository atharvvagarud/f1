"""Phase-6 R1 simulation contract + deterministic RNG tests.

Foundational only: no adapter, no engine, no pace/pit/reliability model, no
aggregation, no training, no inference, no parameter estimation. Tests
construct simulation states directly because R1 has no ``RaceState``
adapter.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import raceintel.simulation as S

SimulationContractError = S.SimulationContractError
SimulationValidationError = S.SimulationValidationError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "raceintel" / "simulation"
PACKAGE_FILES = ("__init__.py", "errors.py", "state.py", "config.py",
                 "rng.py", "results.py")


# ---------------------------------------------------------------------------
# Builders.
# ---------------------------------------------------------------------------

def driver(driver_id: str, lap: int = 5, race_time: float = 300.0, **kw):
    return S.DriverSimState(driver_id, lap, race_time, **kw)


def environment(track_state="all_clear", **kw):
    return S.SimulationEnvironment(track_state=track_state, **kw)


def state(drivers=None, *, race_id="2023-r01-R", scheduled_laps=57,
          leader_laps_done=5, simulation_time_s=320.0, env=None,
          season=2023, **kw):
    if drivers is None:
        drivers = (driver("a", 5, 300.0, position=1),
                   driver("b", 5, 301.0, position=2))
    return S.SimulationState(
        race_id=race_id, scheduled_laps=scheduled_laps,
        leader_laps_done=leader_laps_done, simulation_time_s=simulation_time_s,
        drivers=drivers, environment=env or environment(),
        season=season, **kw)


def finish_order(entries, roster_size=None):
    return S.FinishOrder(roster_size or len(entries), tuple(entries))


def summary(driver_id="a", **kw):
    return S.DriverSimulationSummary(driver_id=driver_id, **kw)


def monte_carlo(**kw):
    order = finish_order([
        S.DriverFinish("a", True, False, 57, 3600.0, 1),
        S.DriverFinish("b", True, False, 57, 3601.0, 2),
    ])
    base = dict(
        simulation_request_identity="req" * 4,
        race_id="2023-r01-R",
        requested_simulation_count=100,
        valid_simulation_count=98,
        invalid_simulation_count=2,
        master_seed=42,
        parameter_identity="contract-only",
        assumptions_identity="assumptions",
        driver_summaries=(summary("a"), summary("b")),
        sample_orders=(order,),
    )
    base.update(kw)
    return S.MonteCarloResult(**base)


def parse_module(name):
    return ast.parse((PACKAGE_DIR / name).read_text())


def called_and_imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


# ---------------------------------------------------------------------------
# Contract version (R1-C).
# ---------------------------------------------------------------------------

def test_contract_version_is_v1():
    assert S.SIMULATION_CONTRACT_VERSION == "v1"


def test_one_authoritative_version_definition():
    hits = []
    for path in PACKAGE_FILES:
        text = (PACKAGE_DIR / path).read_text()
        if 'SIMULATION_CONTRACT_VERSION =' in text:
            hits.append(path)
    assert hits == ["state.py"]


def test_modules_reuse_version_authority():
    assert S.SimulationConfig(1, 0).identity()
    assert S.seed_sequence_for_simulation(0, 0) is not None
    assert S.MonteCarloResult.__dataclass_fields__[
        "simulation_contract_version"].default == "v1"
    assert S.SimulationState.__dataclass_fields__[
        "simulation_contract_version"].default == "v1"


def test_state_defaults_to_current_version():
    assert state().simulation_contract_version == "v1"


def test_unsupported_state_version_rejected():
    with pytest.raises(SimulationContractError):
        S.SimulationState(
            race_id="r", scheduled_laps=10, leader_laps_done=1,
            simulation_time_s=1.0, drivers=(driver("a", 1, 1.0),),
            environment=environment(), simulation_contract_version="v9")


def test_unsupported_result_version_rejected():
    with pytest.raises(SimulationContractError):
        monte_carlo(simulation_contract_version="v9")


# ---------------------------------------------------------------------------
# Provenance vocabulary (R1-D).
# ---------------------------------------------------------------------------

def test_provenance_membership_exact():
    assert {member.value for member in S.Provenance} == {
        "FACTUAL_AT_T", "HISTORICALLY_ESTIMATED", "STOCHASTIC_DRAW",
        "USER_ASSUMPTION", "ORACLE_EVALUATION_ONLY"}


def test_provenance_is_str_enum_and_serializes():
    assert S.Provenance.FACTUAL_AT_T == "FACTUAL_AT_T"
    assert json.dumps(S.Provenance.STOCHASTIC_DRAW.value) == \
        '"STOCHASTIC_DRAW"'


def test_provenance_value_accepts_enum_and_string():
    assert S.provenance_value(S.Provenance.USER_ASSUMPTION) is \
        S.Provenance.USER_ASSUMPTION
    assert S.provenance_value("FACTUAL_AT_T") is S.Provenance.FACTUAL_AT_T


def test_provenance_value_rejects_free_form():
    with pytest.raises(SimulationContractError):
        S.provenance_value("MADE_UP")


def test_assumptions_provenance_is_user_assumption():
    assert S.Assumptions().provenance is S.Provenance.USER_ASSUMPTION


def test_assumptions_rejects_non_user_provenance():
    for bad in (S.Provenance.FACTUAL_AT_T,
                S.Provenance.ORACLE_EVALUATION_ONLY):
        with pytest.raises(SimulationContractError):
            S.Assumptions(provenance=bad)


# ---------------------------------------------------------------------------
# State construction, ordering, identity invariants (R1-E..R1-I).
# ---------------------------------------------------------------------------

def test_minimal_state_constructs():
    st = state()
    assert st.roster_size == 2
    assert st.roster_driver_ids == ("a", "b")
    assert st.simulation_time_s == 320.0


def test_state_to_dict_is_json_safe():
    payload = state().to_dict()
    json.dumps(payload, allow_nan=False)
    assert payload["roster_driver_ids"] == ["a", "b"]
    assert payload["environment"]["track_state"] == "all_clear"


def test_state_to_dict_has_no_numpy_scalars():
    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        else:
            assert not isinstance(value, np.generic), value
    walk(state().to_dict())


def test_drivers_canonically_ordered_regardless_of_input():
    st = state(drivers=(driver("z", 5, 305.0), driver("a", 5, 300.0),
                        driver("m", 5, 302.0)), leader_laps_done=5)
    assert st.roster_driver_ids == ("a", "m", "z")


def test_duplicate_driver_ids_rejected():
    with pytest.raises(SimulationContractError):
        state(drivers=(driver("a"), driver("a")))


def test_empty_driver_collection_rejected():
    with pytest.raises(SimulationContractError):
        state(drivers=())


def test_none_driver_collection_rejected():
    with pytest.raises(SimulationContractError):
        S.SimulationState(race_id="r", scheduled_laps=10, leader_laps_done=1,
                          simulation_time_s=1.0, drivers=None,
                          environment=environment())


def test_empty_driver_id_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("")


def test_wrong_driver_entry_type_rejected():
    with pytest.raises(SimulationContractError):
        state(drivers=("a",))


def test_empty_race_id_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(race_id="  ")


def test_environment_wrong_type_rejected():
    with pytest.raises(SimulationContractError):
        state(env="all_clear")


def test_driver_by_id_mapping():
    st = state()
    assert set(st.driver_by_id) == {"a", "b"}


# ---------------------------------------------------------------------------
# Numeric validation (R1-H).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_race_time_rejected(bad):
    with pytest.raises(S.SimulationValidationError):
        driver("a", race_time=bad)


def test_negative_race_time_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", race_time=-1.0)


def test_negative_lap_number_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", lap=-1)


def test_negative_tyre_age_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", tyre_age=-1)


def test_null_tyre_age_preserved():
    # R2-Z refinement: frozen RaceState carries unknown tyre age as null;
    # null must not be flattened to a factual zero.
    entry = driver("a", tyre_age=None)
    assert entry.tyre_age is None
    assert entry.to_dict()["tyre_age"] is None
    assert driver("a", tyre_age=0).tyre_age == 0


def test_negative_pit_count_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", pit_count=-1)


def test_negative_observation_age_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", observation_age_s=-0.5)


def test_zero_position_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", position=0)


def test_zero_stint_number_rejected():
    with pytest.raises(S.SimulationValidationError):
        driver("a", stint_number=0)


def test_invalid_scheduled_laps_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(scheduled_laps=0)


def test_negative_leader_laps_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(leader_laps_done=-1)


def test_leader_laps_beyond_schedule_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(scheduled_laps=10, leader_laps_done=11,
              drivers=(driver("a", 5, 1.0),))


def test_driver_laps_beyond_leader_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(leader_laps_done=4, drivers=(driver("a", 5, 1.0),))


def test_non_finite_simulation_time_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(simulation_time_s=float("nan"))


def test_negative_season_rejected():
    with pytest.raises(S.SimulationValidationError):
        state(season=-1)


def test_numpy_integer_scalar_rejected():
    with pytest.raises(S.SimulationContractError):
        driver("a", lap=np.int64(5))


def test_numpy_float_scalar_rejected():
    with pytest.raises(S.SimulationContractError):
        driver("a", race_time=np.float64(1.0))


def test_bool_is_not_a_valid_int():
    with pytest.raises(S.SimulationContractError):
        driver("a", lap=True)


def test_duplicate_positions_are_structurally_allowed():
    # Position is a classification, ambiguous mid-pit-cycle (frozen F6
    # evidence), never required unique in SimulationState.
    st = state(drivers=(driver("a", 5, 1.0, position=2),
                        driver("b", 5, 2.0, position=2)))
    assert st.roster_size == 2


# ---------------------------------------------------------------------------
# Lapped states (R1-I).
# ---------------------------------------------------------------------------

def test_lapped_drivers_allowed_with_distinct_lap_counts():
    st = state(drivers=(
        driver("leader", 20, 900.0),
        driver("on_lead_lap", 20, 901.5),
        driver("one_down", 19, 905.0),
        driver("two_down", 18, 910.0),
    ), leader_laps_done=20)
    laps = sorted(d.lap_number for d in st.drivers)
    assert laps == [18, 19, 20, 20]
    assert st.roster_size == 4


def test_leader_lap_pinned_to_max_progress():
    st = state(drivers=(driver("a", 20, 900.0), driver("b", 19, 905.0)),
               leader_laps_done=20)
    assert st.leader_laps_done == 20


# ---------------------------------------------------------------------------
# Retirement representation (R1-J).
# ---------------------------------------------------------------------------

def test_retired_status_is_structural():
    d = driver("a", status=S.DriverStatus.RETIRED)
    assert d.status is S.DriverStatus.RETIRED


def test_retired_status_accepts_string_token():
    assert driver("a", status="RETIRED").status is S.DriverStatus.RETIRED


def test_invalid_status_rejected():
    with pytest.raises(SimulationContractError):
        driver("a", status="DNF_INFERRED")


def test_active_stale_driver_is_structurally_possible():
    # ACTIVE with a large observation age: retirement is never inferred
    # from staleness.
    d = driver("a", status=S.DriverStatus.ACTIVE, observation_age_s=120.0)
    assert d.status is S.DriverStatus.ACTIVE
    assert d.observation_age_s == 120.0


def test_retirement_is_not_inferred_from_observation_age():
    active_stale = driver("a", observation_age_s=99.0)
    retired = driver("a", status=S.DriverStatus.RETIRED)
    assert active_stale.status != retired.status


# ---------------------------------------------------------------------------
# Environment contract (R1-K).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", ["all_clear", "yellow", "safety_car",
                                   "red_flag", "vsc", "vsc_ending", None])
def test_environment_accepts_frozen_track_tokens(token):
    assert environment(track_state=token).track_state == token


def test_environment_rejects_unknown_track_token():
    with pytest.raises(S.SimulationValidationError):
        environment(track_state="green_flag")


def test_environment_weather_defaults_none():
    assert environment().weather is None


def test_environment_accepts_frozen_weather_state():
    from raceintel.race_state.race_state import WeatherState
    env = environment(weather=WeatherState(air_temp_c=25.0,
                                           observed_at_s=100.0))
    assert env.weather.air_temp_c == 25.0
    assert env.to_dict()["weather"]["air_temp_c"] == 25.0


def test_environment_rejects_wrong_weather_type():
    with pytest.raises(SimulationContractError):
        environment(weather={"air_temp_c": 25.0})


# ---------------------------------------------------------------------------
# SimulationConfig (R1-L).
# ---------------------------------------------------------------------------

def test_config_constructs():
    cfg = S.SimulationConfig(1000, 12345)
    assert (cfg.simulation_count, cfg.master_seed) == (1000, 12345)
    assert cfg.sample_orders == 0
    assert cfg.reliability_enabled is False


def test_config_zero_count_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationConfig(0, 1)


def test_config_negative_count_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationConfig(-5, 1)


def test_config_non_int_count_rejected():
    with pytest.raises(S.SimulationContractError):
        S.SimulationConfig(10.0, 1)


def test_config_negative_seed_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationConfig(10, -1)


def test_config_seed_above_bound_rejected():
    with pytest.raises(S.SimulationContractError):
        S.SimulationConfig(10, S.MAX_MASTER_SEED + 1)


def test_config_non_int_seed_rejected():
    with pytest.raises(S.SimulationContractError):
        S.SimulationConfig(10, "seed")


def test_config_negative_sample_orders_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationConfig(10, 1, sample_orders=-1)


def test_config_sample_orders_above_count_rejected():
    with pytest.raises(S.SimulationContractError):
        S.SimulationConfig(10, 1, sample_orders=11)


def test_config_reliability_flag_must_be_bool():
    with pytest.raises(S.SimulationContractError):
        S.SimulationConfig(10, 1, reliability_enabled=1)


def test_config_identity_stable():
    assert S.SimulationConfig(10, 1).identity() == \
        S.SimulationConfig(10, 1).identity()


def test_config_identity_changes_with_seed():
    assert S.SimulationConfig(10, 1, 3).identity() != \
        S.SimulationConfig(10, 2, 3).identity()


def test_config_identity_changes_with_count_and_sample_and_switch():
    base = S.SimulationConfig(10, 1, 2)
    assert base.identity() != S.SimulationConfig(11, 1, 2).identity()
    assert base.identity() != S.SimulationConfig(10, 1, 1).identity()
    assert base.identity() != \
        S.SimulationConfig(10, 1, 2, reliability_enabled=True).identity()


# ---------------------------------------------------------------------------
# Assumptions (R1-M) and parameter seam (R1-N).
# ---------------------------------------------------------------------------

def test_assumptions_default_version():
    assert S.Assumptions().assumptions_version == S.ASSUMPTIONS_VERSION


def test_assumptions_empty_version_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.Assumptions(assumptions_version="")


def test_assumptions_identity_stable_and_sensitive():
    assert S.Assumptions("v1").identity() == S.Assumptions("v1").identity()
    assert S.Assumptions("v1").identity() != S.Assumptions("v2").identity()


def test_assumptions_to_dict_carries_provenance():
    payload = S.Assumptions().to_dict()
    assert payload["provenance"] == "USER_ASSUMPTION"
    json.dumps(payload, allow_nan=False)


def test_parameter_identity_contract_only():
    pid = S.ParameterIdentity.contract_only()
    assert pid.supplied is False
    assert pid.to_dict() == {"parameter_set_id": None,
                             "parameter_version": None,
                             "parameter_hash": None}


def test_parameter_identity_fully_supplied():
    pid = S.ParameterIdentity("sim-params", "v1", "abc123")
    assert pid.supplied is True


def test_parameter_identity_mixed_rejected():
    with pytest.raises(SimulationContractError):
        S.ParameterIdentity("sim-params", None, "abc123")


def test_parameter_identity_empty_field_rejected():
    with pytest.raises(S.SimulationValidationError):
        S.ParameterIdentity("sim-params", "v1", "")


def test_parameter_identity_stable_and_distinct():
    a = S.ParameterIdentity("sim-params", "v1", "abc")
    b = S.ParameterIdentity("sim-params", "v1", "abc")
    c = S.ParameterIdentity("sim-params", "v2", "abc")
    assert a.identity() == b.identity()
    assert a.identity() != c.identity()
    assert S.ParameterIdentity.contract_only().identity() != a.identity()


# ---------------------------------------------------------------------------
# RNG determinism + parallel invariance (R1-O..R1-Q, R1-AH).
# ---------------------------------------------------------------------------

def test_rng_algorithm_is_versioned_pcg64():
    assert S.SIMULATION_RNG_ALGORITHM == "PCG64"
    gen = S.rng_for_simulation(1, 0)
    assert isinstance(gen, np.random.Generator)
    assert isinstance(gen.bit_generator, np.random.PCG64)


def test_rng_repeat_100_times_identical_sequence():
    reference = S.rng_for_simulation(7, 137).uniform(size=6)
    for _ in range(100):
        assert np.array_equal(
            reference, S.rng_for_simulation(7, 137).uniform(size=6))


def test_rng_different_simulation_id_distinct():
    a = S.rng_for_simulation(7, 1).uniform(size=8)
    b = S.rng_for_simulation(7, 2).uniform(size=8)
    assert not np.array_equal(a, b)


def test_rng_different_master_seed_distinct():
    a = S.rng_for_simulation(1, 5).uniform(size=8)
    b = S.rng_for_simulation(2, 5).uniform(size=8)
    assert not np.array_equal(a, b)


def test_rng_request_order_independent():
    order_a = [0, 1, 2, 3]
    order_b = [3, 1, 0, 2]
    draws_a = {i: S.rng_for_simulation(99, i).uniform(size=4)
               for i in order_a}
    draws_b = {i: S.rng_for_simulation(99, i).uniform(size=4)
               for i in order_b}
    for i in order_a:
        assert np.array_equal(draws_a[i], draws_b[i])


def test_rng_chunk_order_independent():
    serial = {i: S.rng_for_simulation(42, i).uniform(size=5)
              for i in range(100)}
    chunks = [range(0, 25), range(25, 50), range(50, 75), range(75, 100)]
    for chunk in chunks:
        for i in chunk:
            assert np.array_equal(
                serial[i], S.rng_for_simulation(42, i).uniform(size=5))


def test_rng_draw_types_deterministic():
    def draws():
        gen = S.rng_for_simulation(3, 11)
        return (gen.uniform(size=3), gen.standard_normal(size=3),
                gen.choice(10, size=3))
    first = draws()
    second = draws()
    for a, b in zip(first, second):
        assert np.array_equal(a, b)


def test_rng_negative_seed_rejected():
    with pytest.raises(S.SimulationRNGError):
        S.rng_for_simulation(-1, 0)


def test_rng_negative_simulation_id_rejected():
    with pytest.raises(S.SimulationRNGError):
        S.rng_for_simulation(1, -1)


def test_rng_non_int_rejected():
    with pytest.raises(S.SimulationRNGError):
        S.rng_for_simulation(1.0, 0)


def test_rng_empty_contract_version_rejected():
    with pytest.raises(S.SimulationRNGError):
        S.seed_sequence_for_simulation(1, 0, contract_version="")


def test_rng_seed_sequence_is_deterministic_and_distinct():
    a = S.seed_sequence_for_simulation(5, 9)
    b = S.seed_sequence_for_simulation(5, 9)
    c = S.seed_sequence_for_simulation(5, 10)
    assert a.entropy == b.entropy and a.spawn_key == b.spawn_key
    assert not (a.entropy == c.entropy and a.spawn_key == c.spawn_key)


# ---------------------------------------------------------------------------
# Global RNG firewall (R1-AI).
# ---------------------------------------------------------------------------

def test_rng_helpers_do_not_mutate_np_global_state():
    before = np.random.get_state()
    for i in range(5):
        S.rng_for_simulation(123, i).uniform(size=3)
    after = np.random.get_state()
    assert before[0] == after[0]
    assert np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_rng_helpers_do_not_mutate_random_global_state():
    before = random.getstate()
    for i in range(5):
        S.rng_for_simulation(123, i).standard_normal(size=3)
    assert random.getstate() == before


def test_no_global_seed_calls_in_package_source():
    banned_attrs = {"seed"}
    for path in PACKAGE_FILES:
        tree = parse_module(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) \
                    and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Attribute) \
                    and node.func.value.attr == "random" \
                    and node.func.attr in banned_attrs:
                raise AssertionError(f"global seed call in {path}")
        text = (PACKAGE_DIR / path).read_text()
        assert "np.random.seed" not in text
        assert "random.seed" not in text


def test_package_never_imports_random_module():
    for path in PACKAGE_FILES:
        imported = {alias.name for node in ast.walk(parse_module(path))
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        assert "random" not in imported, path


# ---------------------------------------------------------------------------
# Deterministic identity / serialization (R1-R..R1-T, R1-AC).
# ---------------------------------------------------------------------------

def test_canonical_json_is_byte_stable():
    a = S.canonical_json({"b": 1, "a": [2, 3]})
    b = S.canonical_json({"a": [2, 3], "b": 1})
    assert a == b == '{"a":[2,3],"b":1}'


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        S.canonical_json({"x": float("nan")})


def test_canonical_sha256_matches_hashlib():
    assert S.canonical_sha256({"a": 1}) == hashlib.sha256(
        b'{"a":1}').hexdigest()


def test_state_identity_stable_and_driver_order_insensitive():
    st1 = state(drivers=(driver("a", 5, 300.0), driver("b", 5, 301.0)))
    st2 = state(drivers=(driver("b", 5, 301.0), driver("a", 5, 300.0)))
    assert st1.identity() == st2.identity()


def test_state_identity_changes_with_race():
    assert state(race_id="r1").identity() != state(race_id="r2").identity()


def test_state_identity_changes_with_anchor_frame():
    assert state(anchor_frame_index=1).identity() != \
        state(anchor_frame_index=2).identity()


def test_state_identity_changes_with_driver_state():
    assert state(drivers=(driver("a", 5, 300.0),)).identity() != \
        state(drivers=(driver("a", 6, 300.0),),
              leader_laps_done=6).identity()


def test_state_identity_changes_with_environment():
    assert state(env=environment("all_clear")).identity() != \
        state(env=environment("safety_car")).identity()


def test_request_identity_deterministic():
    st, cfg, asm = state(), S.SimulationConfig(10, 1), S.Assumptions()
    assert S.simulation_request_identity(st, cfg, asm) == \
        S.simulation_request_identity(st, cfg, asm)


def test_request_identity_changes_with_config():
    st, asm = state(), S.Assumptions()
    assert S.simulation_request_identity(st, S.SimulationConfig(10, 1),
                                         asm) != \
        S.simulation_request_identity(st, S.SimulationConfig(10, 2), asm)


def test_request_identity_changes_with_assumptions():
    st, cfg = state(), S.SimulationConfig(10, 1)
    assert S.simulation_request_identity(st, cfg, S.Assumptions("v1")) != \
        S.simulation_request_identity(st, cfg, S.Assumptions("v2"))


def test_request_identity_changes_with_parameter_identity():
    st, cfg, asm = state(), S.SimulationConfig(10, 1), S.Assumptions()
    assert S.simulation_request_identity(st, cfg, asm) != \
        S.simulation_request_identity(
            st, cfg, asm, S.ParameterIdentity("p", "v1", "h"))


def test_request_identity_rejects_bad_inputs():
    st, cfg, asm = state(), S.SimulationConfig(10, 1), S.Assumptions()
    with pytest.raises(SimulationContractError):
        S.simulation_request_identity(st, "config", asm)
    with pytest.raises(SimulationContractError):
        S.simulation_request_identity(st, cfg, "assumptions")
    with pytest.raises(SimulationContractError):
        S.simulation_request_identity(st, cfg, asm, "param")


# ---------------------------------------------------------------------------
# SimulationRunResult / FinishOrder (R1-V, R1-AA, R1-Z).
# ---------------------------------------------------------------------------

def test_driver_finish_classified_requires_position():
    with pytest.raises(S.SimulationValidationError):
        S.DriverFinish("a", True, False, 57, 3600.0)


def test_driver_finish_retired_must_not_have_position():
    with pytest.raises(S.SimulationValidationError):
        S.DriverFinish("a", False, True, 30, 2000.0, finish_position=5)


def test_driver_finish_cannot_be_classified_and_retired():
    with pytest.raises(S.SimulationValidationError):
        S.DriverFinish("a", True, True, 57, 3600.0, finish_position=1)


def test_finish_order_accounts_for_all_drivers():
    order = finish_order([
        S.DriverFinish("a", True, False, 57, 3600.0, 1),
        S.DriverFinish("b", True, False, 57, 3601.0, 2),
        S.DriverFinish("c", False, True, 20, 1500.0),
    ])
    assert order.finishing_order == ("a", "b")
    assert order.retired_count == 1


def test_finish_order_roster_mismatch_rejected():
    with pytest.raises(S.SimulationValidationError):
        finish_order([S.DriverFinish("a", True, False, 57, 3600.0, 1)],
                     roster_size=2)


def test_finish_order_duplicate_driver_rejected():
    with pytest.raises(SimulationContractError):
        finish_order([
            S.DriverFinish("a", True, False, 57, 3600.0, 1),
            S.DriverFinish("a", True, False, 57, 3601.0, 2),
        ])


def test_finish_order_position_gap_rejected():
    with pytest.raises(S.SimulationValidationError):
        finish_order([
            S.DriverFinish("a", True, False, 57, 3600.0, 1),
            S.DriverFinish("b", True, False, 57, 3601.0, 3),
        ])


def test_finish_order_duplicate_position_rejected():
    with pytest.raises(S.SimulationValidationError):
        finish_order([
            S.DriverFinish("a", True, False, 57, 3600.0, 1),
            S.DriverFinish("b", True, False, 57, 3601.0, 1),
        ])


def test_finish_order_allows_lapped_drivers():
    order = finish_order([
        S.DriverFinish("a", True, False, 57, 3600.0, 1),
        S.DriverFinish("b", True, False, 57, 3601.0, 2),
        S.DriverFinish("c", True, False, 56, 3605.0, 3),
    ])
    assert order.entries[-1].laps_completed == 56


def test_finish_order_entries_canonicalized():
    order = finish_order([
        S.DriverFinish("c", False, True, 20, 1500.0),
        S.DriverFinish("a", True, False, 57, 3600.0, 1),
        S.DriverFinish("b", True, False, 57, 3601.0, 2),
    ])
    assert order.finishing_order == ("a", "b")
    assert order.entries[-1].driver_id == "c"


def test_run_result_valid_requires_classification():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationRunResult("r", "r:1:0", 0, True)


def test_run_result_valid_rejects_reason():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationRunResult("r", "r:1:0", 0, True,
                              finish_order([S.DriverFinish(
                                  "a", True, False, 57, 3600.0, 1)]),
                              invalid_reason="oops")


def test_run_result_invalid_requires_reason():
    with pytest.raises(S.SimulationValidationError):
        S.SimulationRunResult("r", "r:1:0", 0, False)


def test_run_result_invalid_serializes():
    result = S.SimulationRunResult("r", "r:1:0", 0, False,
                                   invalid_reason="ALL_RETIRED")
    assert result.to_dict()["invalid_reason"] == "ALL_RETIRED"


def test_run_result_valid_round_trips():
    order = finish_order([
        S.DriverFinish("a", True, False, 57, 3600.0, 1),
        S.DriverFinish("b", True, False, 57, 3601.0, 2),
    ])
    result = S.SimulationRunResult("r", "r:1:0", 0, True, order)
    json.dumps(result.to_dict(), allow_nan=False)


# ---------------------------------------------------------------------------
# DriverSimulationSummary (R1-W).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_summary_probability_bounds(value):
    with pytest.raises(S.SimulationValidationError):
        summary(win_probability=value)


def test_summary_probability_nan_rejected():
    with pytest.raises(S.SimulationValidationError):
        summary(podium_probability=float("nan"))


def test_summary_none_probabilities_allowed():
    assert summary().win_probability is None


def test_summary_expected_finish_bounds():
    with pytest.raises(S.SimulationValidationError):
        summary(expected_finish=0.5)


def test_summary_non_finite_expected_rejected():
    with pytest.raises(S.SimulationValidationError):
        summary(expected_points=float("inf"))


def test_summary_invalid_distribution_key_rejected():
    with pytest.raises(S.SimulationValidationError):
        summary(finish_position_distribution=(
            S.PositionFrequency(0, 0.2),))


def test_summary_duplicate_distribution_key_rejected():
    with pytest.raises(S.SimulationValidationError):
        summary(finish_position_distribution=(
            S.PositionFrequency(1, 0.2),
            S.PositionFrequency(1, 0.3)))


def test_summary_allows_dnf_bucket_and_no_sum_to_one():
    entry = summary(finish_position_distribution=(
        S.PositionFrequency(1, 0.2),
        S.PositionFrequency(None, 0.1)))
    assert entry.finish_position_distribution[1].position is None


def test_summary_distribution_wrong_type_rejected():
    with pytest.raises(SimulationContractError):
        summary(finish_position_distribution=((1, 0.2),))


def test_summary_serializes():
    json.dumps(summary(win_probability=0.5).to_dict(), allow_nan=False)


# ---------------------------------------------------------------------------
# MonteCarloResult (R1-X, R1-Z).
# ---------------------------------------------------------------------------

def test_monte_carlo_constructs_and_orders_summaries():
    result = monte_carlo(driver_summaries=(summary("b"), summary("a")))
    assert [s.driver_id for s in result.driver_summaries] == ["a", "b"]


def test_monte_carlo_counts_must_sum_to_requested():
    with pytest.raises(S.SimulationValidationError):
        monte_carlo(valid_simulation_count=90, invalid_simulation_count=5)


def test_monte_carlo_duplicate_summaries_rejected():
    with pytest.raises(SimulationContractError):
        monte_carlo(driver_summaries=(summary("a"), summary("a")))


def test_monte_carlo_empty_summaries_rejected():
    with pytest.raises(SimulationContractError):
        monte_carlo(driver_summaries=())


def test_monte_carlo_negative_counts_rejected():
    with pytest.raises(S.SimulationValidationError):
        monte_carlo(requested_simulation_count=100,
                    valid_simulation_count=101,
                    invalid_simulation_count=-1)


def test_monte_carlo_zero_requested_rejected():
    with pytest.raises(S.SimulationValidationError):
        monte_carlo(requested_simulation_count=0,
                    valid_simulation_count=0,
                    invalid_simulation_count=0)


def test_monte_carlo_sample_order_roster_mismatch_rejected():
    order = finish_order([
        S.DriverFinish("a", True, False, 57, 3600.0, 1)],
        roster_size=1)
    with pytest.raises(S.SimulationValidationError):
        monte_carlo(sample_orders=(order,))


def test_monte_carlo_duplicate_sample_driver_rejected():
    with pytest.raises(SimulationContractError):
        finish_order([
            S.DriverFinish("a", True, False, 57, 3600.0, 1),
            S.DriverFinish("a", True, False, 57, 3601.0, 2),
        ], roster_size=2)


def test_monte_carlo_probability_semantics_pinned():
    assert monte_carlo().probability_semantics == "MONTE_CARLO_FREQUENCY"
    with pytest.raises(SimulationContractError):
        monte_carlo(probability_semantics="INDEPENDENT_BINARY")


def test_monte_carlo_runtime_excluded_from_identity():
    a = monte_carlo(runtime_s=1.0)
    b = monte_carlo(runtime_s=999.0)
    assert a.identity() == b.identity()


def test_monte_carlo_identity_changes_with_seed():
    assert monte_carlo(master_seed=1).identity() != \
        monte_carlo(master_seed=2).identity()


def test_monte_carlo_serializes_deterministically():
    a = S.canonical_json(monte_carlo().to_dict())
    b = S.canonical_json(monte_carlo().to_dict())
    assert a == b
    json.loads(a)


def test_monte_carlo_runtime_bad_type_rejected():
    with pytest.raises(S.SimulationContractError):
        monte_carlo(runtime_s="fast")


# ---------------------------------------------------------------------------
# Scientific separation (R1-AE) and generic-season boundary (R1-AF).
# ---------------------------------------------------------------------------

FORBIDDEN_MODULES = {
    "raceintel.prediction", "raceintel.model_lab", "raceintel.race_state.race_state_features",
    "raceintel.replay", "raceintel.replay.replay_predictions", "raceintel.replay.replay_probability_timeline",
    "raceintel.replay.replay_reconstruction", "sklearn", "joblib",
}

FORBIDDEN_IMPORT_TOKENS = {
    "prediction", "model_lab", "FrozenWinnerPredictor", "sklearn", "joblib",
    "replay_predictions", "replay_probability_timeline",
}


def test_simulation_package_isolated_from_winner_model():
    code = (
        "import sys; import raceintel.simulation; "
        "forbidden={'raceintel.prediction','raceintel.model_lab','raceintel.race_state.race_state_features',"
        "'raceintel.replay','raceintel.replay.replay_predictions',"
        "'raceintel.replay.replay_probability_timeline','raceintel.replay.replay_reconstruction',"
        "'sklearn','joblib'}; "
        "bad=sorted(forbidden.intersection(sys.modules)); "
        "print('BAD='+','.join(bad) if bad else 'CLEAN')")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT),
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


def test_simulation_source_has_no_forbidden_imports():
    for path in PACKAGE_FILES:
        tree = parse_module(path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for token in FORBIDDEN_IMPORT_TOKENS:
                    assert token not in name, (path, name)


def test_simulation_source_has_no_dataframe_or_api_imports():
    for path in PACKAGE_FILES:
        imported = called_and_imported_names(parse_module(path))
        for banned in ("pandas", "fastapi", "joblib", "sklearn"):
            assert banned not in imported, (path, banned)


def test_domain_contracts_are_season_generic():
    text = (PACKAGE_DIR / "state.py").read_text()
    assert "2018" not in text
    assert "2025" not in text


def test_generic_season_values_construct():
    for season in (1950, 2018, 2024, 2030):
        assert state(season=season).season == season

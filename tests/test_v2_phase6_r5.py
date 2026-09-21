"""Phase-6 R5 focused tests: stochastic Monte Carlo engine + aggregation.

The tests exercise the R5 contracts directly and against the frozen
Phase-1..5 replay seam used only to build factual ``SimulationState`` values.
R5 is compared against the R4 deterministic kernel for zero-noise parity and
against its scalar oracle for exact batch parity.
"""

from __future__ import annotations

import ast
import functools
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from v2 import replay as RP
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_reconstruction import ReplayReconstructor
from v2.simulation import engine as E
from v2.simulation.adapter import from_race_state
from v2.simulation.config import (
    Assumptions,
    SimulationConfig,
    simulation_request_identity,
)
from v2.simulation.engine import (
    DeterministicRaceEngine,
    ExecutionPolicy,
    SimulationUnsupportedError,
)
from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.monte_carlo import (
    DEFAULT_CHUNK_SIZE,
    MONTE_CARLO_VERSION,
    PODIUM_POSITIONS,
    RESIDUAL_FAMILY,
    RESIDUAL_INDEPENDENCE_ASSUMPTION,
    RESIDUAL_INDEPENDENCE_NOTE,
    MonteCarloEngine,
    ResidualSampler,
    max_residual_draws,
    run_trajectory_scalar,
    select_residual_sampler,
)
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
from v2.simulation.results import (
    PROBABILITY_SEMANTICS,
    MonteCarloResult,
)
from v2.simulation.rng import rng_for_simulation
from v2.simulation.state import (
    DriverSimState,
    DriverStatus,
    SimulationEnvironment,
    SimulationState,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "v2" / "simulation" / "monte_carlo.py"
ARTIFACT_DIR = (REPO_ROOT / "data" / "v2" / "simulation" / "params"
                / "r3-v1__through-2024")

D9 = (str(REPO_ROOT) + "/data/v2/processed/driver_lap_state_d9/season="
      "{season}/driver_lap_state_d9__d9-{season}.parquet")
RESULTS = (str(REPO_ROOT) + "/data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = (str(REPO_ROOT) + "/data/v2/processed/races/season={season}/"
         "races__{race}.parquet")

RESIDUAL_PROBS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50,
                  0.75, 0.90, 0.95, 0.975, 0.99, 0.995, 0.999)
RESIDUAL_QUANTILES = (-3.17, -2.32, -1.96, -1.45, -1.12, -0.82, -0.41,
                      0.0, 0.48, 1.15, 1.71, 2.34, 3.33, 4.51, 11.93)


# ===========================================================================
# Synthetic artifacts.
# ===========================================================================

def _scalar(value, *, support="strong", fallback="exact", ident="identified",
            samples=1000):
    return SupportEntry(group_key="g", sample_count=samples,
                        support_level=support, fallback_level=fallback,
                        value=value, identifiability=ident)


def _dist(observed_max, *, probs=(0.5,), quants=(20.0,), observed_min=1.0,
          samples=1000):
    return SupportEntry(
        group_key="g", sample_count=samples, support_level="strong",
        fallback_level="global", probabilities=probs,
        quantile_values=quants, observed_min=observed_min,
        observed_max=observed_max)


def make_params(*, base=90.0, circuit="syn", era="2018-2021", season=2019,
                offsets=None, progress=-0.05, degradation=0.02, age_max=40.0,
                through=2024, seasons=tuple(range(2018, 2025)),
                constructors=("c1",), residual=None, base_circuit=True):
    families = {name: ParameterFamily(name, "unit", {}) for name in FAMILY_NAMES}
    families["pace_base_s"] = ParameterFamily(
        "pace_base_s", "seconds",
        {f"{circuit}|{era}": _scalar(base, fallback="exact")})
    fallback = {}
    if base_circuit:
        fallback[circuit] = _scalar(base, fallback="circuit")
    fallback["global"] = _scalar(base, support="weak", fallback="global")
    families["pace_base_fallback_s"] = ParameterFamily(
        "pace_base_fallback_s", "seconds", fallback)
    if offsets is None:
        offsets = {constructor: 0.0 for constructor in constructors}
    offset_entries = {}
    for constructor, value in offsets.items():
        offset_entries[f"{constructor}|{season}"] = _scalar(value,
                                                            fallback="exact")
        offset_entries[f"{constructor}|{era}"] = _scalar(value, fallback="era")
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
    if residual is None:
        residual = _dist(40.0, probs=RESIDUAL_PROBS,
                         quants=RESIDUAL_QUANTILES, observed_min=-8.0)
    families[RESIDUAL_FAMILY] = ParameterFamily(
        RESIDUAL_FAMILY, "seconds", {era: residual, "global": residual})
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


def sim_driver(driver_id, *, lap, race_time, age=1, compound="HARD",
               position=1, constructor="c1", pit_count=0, status=None):
    return DriverSimState(
        driver_id=driver_id, lap_number=lap, race_time_s=race_time,
        position=position, compound=compound, tyre_age=age, stint_number=1,
        pit_count=pit_count, constructor_id=constructor,
        status=status if status is not None else DriverStatus.ACTIVE)


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


def field(n=4, *, scheduled=8, gaps=None, start_lap=2, constructor="c1"):
    if gaps is None:
        gaps = tuple(0.4 * i for i in range(n))
    drivers = [
        sim_driver(chr(ord("a") + i), lap=start_lap + (i % 2),
                   race_time=300.0 + gaps[i], age=2, constructor=constructor,
                   position=i + 1)
        for i in range(n)]
    return sim_state(drivers, scheduled=scheduled)


def config(n=100, seed=12345, samples=0):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=samples)


def result_dict_without_runtime(result: MonteCarloResult) -> dict:
    payload = result.to_dict()
    payload.pop("runtime_s", None)
    return payload


# ===========================================================================
# R5-D empirical quantile interpolation.
# ===========================================================================

def test_sampler_grid_endpoints_are_observed_support():
    sampler = ResidualSampler(
        era="e", key="e", probabilities=(0.25, 0.75),
        quantile_values=(0.0, 1.0), observed_min=-1.0, observed_max=2.0,
        sample_count=10, support_level="strong", fallback_level="exact")
    assert sampler.sample_unit(0.0) == -1.0
    assert sampler.sample_unit(1.0) == 2.0


def test_sampler_interpolates_exact_quantiles():
    probs = (0.25, 0.75)
    quants = (0.0, 1.0)
    sampler = ResidualSampler(
        era="e", key="e", probabilities=probs, quantile_values=quants,
        observed_min=-1.0, observed_max=2.0, sample_count=10,
        support_level="strong", fallback_level="exact")
    assert sampler.sample_unit(0.25) == 0.0
    assert sampler.sample_unit(0.75) == 1.0


def test_sampler_linear_interpolation_is_pinned():
    sampler = ResidualSampler(
        era="e", key="e", probabilities=(0.25, 0.75),
        quantile_values=(0.0, 1.0), observed_min=-1.0, observed_max=2.0,
        sample_count=10, support_level="strong", fallback_level="exact")
    assert sampler.sample_unit(0.5) == pytest.approx(0.5)
    assert sampler.sample_unit(0.125) == pytest.approx(-0.5)
    assert sampler.sample_unit(0.875) == pytest.approx(1.5)


def test_sampler_is_bounded_by_support():
    sampler = ResidualSampler(
        era="e", key="e", probabilities=RESIDUAL_PROBS,
        quantile_values=RESIDUAL_QUANTILES, observed_min=-8.0,
        observed_max=40.0, sample_count=10, support_level="strong",
        fallback_level="exact")
    u = np.linspace(0.0, 1.0, 1001)
    draws = sampler.sample(u)
    assert np.isfinite(draws).all()
    assert draws.min() >= -8.0
    assert draws.max() <= 40.0


def test_sampler_is_deterministic_and_monotone():
    sampler = ResidualSampler(
        era="e", key="e", probabilities=RESIDUAL_PROBS,
        quantile_values=RESIDUAL_QUANTILES, observed_min=-8.0,
        observed_max=40.0, sample_count=10, support_level="strong",
        fallback_level="exact")
    u = np.linspace(0.0, 1.0, 500)
    first = sampler.sample(u)
    second = sampler.sample(u)
    assert np.array_equal(first, second)
    assert np.all(np.diff(first) >= 0.0)


def test_sampler_rejects_malformed_grids():
    with pytest.raises(SimulationValidationError):
        ResidualSampler(era="e", key="e", probabilities=(0.5, 0.25),
                        quantile_values=(0.0, 1.0), observed_min=-1.0,
                        observed_max=2.0, sample_count=1,
                        support_level="strong", fallback_level="exact")
    with pytest.raises(SimulationValidationError):
        ResidualSampler(era="e", key="e", probabilities=(0.5,),
                        quantile_values=(0.0, 1.0), observed_min=-1.0,
                        observed_max=2.0, sample_count=1,
                        support_level="strong", fallback_level="exact")
    with pytest.raises(SimulationValidationError):
        ResidualSampler(era="e", key="e", probabilities=(0.5,),
                        quantile_values=(-5.0,), observed_min=-1.0,
                        observed_max=2.0, sample_count=1,
                        support_level="strong", fallback_level="exact")


def test_select_residual_sampler_prefers_era_then_global():
    params = make_params()
    sampler = select_residual_sampler(params, "2018-2021")
    assert sampler.key == "2018-2021"
    assert sampler.support == (-8.0, 40.0)


def test_select_residual_sampler_uses_global_fallback():
    params = make_params()
    families = dict(params.families)
    families[RESIDUAL_FAMILY] = ParameterFamily(
        RESIDUAL_FAMILY, "seconds",
        {"global": _dist(40.0, probs=RESIDUAL_PROBS,
                         quants=RESIDUAL_QUANTILES, observed_min=-8.0)})
    stripped = SimulationParameterSet(
        parameter_contract_version=params.parameter_contract_version,
        estimator_version=params.estimator_version,
        eligibility_rule_version=params.eligibility_rule_version,
        parameter_set_id=params.parameter_set_id,
        through_season=params.through_season,
        estimation_seasons=params.estimation_seasons,
        source_data={}, regimes={}, policies={}, grouping_hierarchy={},
        support_thresholds={}, families=families, diagnostics={},
        creation_metadata={})
    assert select_residual_sampler(stripped, "2018-2021").key == "global"


def test_select_residual_sampler_refuses_when_absent():
    params = make_params()
    families = dict(params.families)
    families[RESIDUAL_FAMILY] = ParameterFamily(RESIDUAL_FAMILY, "seconds", {})
    stripped = SimulationParameterSet(
        parameter_contract_version=params.parameter_contract_version,
        estimator_version=params.estimator_version,
        eligibility_rule_version=params.eligibility_rule_version,
        parameter_set_id=params.parameter_set_id,
        through_season=params.through_season,
        estimation_seasons=params.estimation_seasons,
        source_data={}, regimes={}, policies={}, grouping_hierarchy={},
        support_thresholds={}, families=families, diagnostics={},
        creation_metadata={})
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        select_residual_sampler(stripped, "2018-2021")
    assert excinfo.value.reason == E.REASON_MISSING_PACE_PARAMETER


def test_residual_diagnostics_are_reported_not_rescaled():
    params = make_params()
    sampler = select_residual_sampler(params, "2018-2021")
    pool = rng_for_simulation(7, 0).random(200_000)
    draws = sampler.sample(pool)
    # The R3 residual is zero-median, heavy-tailed, NOT zero-mean.
    assert sampler.sample_unit(0.5) == 0.0
    assert abs(float(np.median(draws))) < 0.05
    assert float(np.mean(draws)) > 0.0
    assert float(draws.min()) >= sampler.support[0]
    assert float(draws.max()) <= sampler.support[1]


def test_independence_assumption_is_documented():
    assert RESIDUAL_INDEPENDENCE_ASSUMPTION == "independent_per_lap_v1"
    assert "independent" in RESIDUAL_INDEPENDENCE_NOTE.lower()


# ===========================================================================
# R5-G/H RNG and draw-order contract.
# ===========================================================================

def test_residual_pool_matches_direct_stream_draws():
    from v2.simulation.monte_carlo import _draw_pool
    expected = rng_for_simulation(99, 4).random(64)
    assert np.array_equal(_draw_pool(99, 4, 64, "v1"), expected)


def test_residual_pool_is_index_and_seed_sensitive():
    from v2.simulation.monte_carlo import _draw_pool
    assert not np.array_equal(_draw_pool(1, 0, 16, "v1"),
                              _draw_pool(1, 1, 16, "v1"))
    assert not np.array_equal(_draw_pool(1, 0, 16, "v1"),
                              _draw_pool(2, 0, 16, "v1"))


def test_max_residual_draws_is_the_remaining_lap_bound():
    state = field(4, scheduled=8, start_lap=3)
    expected = sum(8 - d.lap_number for d in state.drivers)
    assert max_residual_draws(state) == expected


# ===========================================================================
# R5-J/K scalar oracle and zero-noise R4 parity.
# ===========================================================================

def test_scalar_trajectory_is_deterministic():
    state = field(4)
    params = make_params()
    first = run_trajectory_scalar(state, params, 5, 3)
    second = run_trajectory_scalar(state, params, 5, 3)
    assert first.to_dict() == second.to_dict()
    assert first.valid


def test_scalar_trajectory_differs_by_index():
    state = field(4)
    params = make_params()
    orders = {
        run_trajectory_scalar(state, params, 5, i).classification.to_dict()[
            "entries"][0]["driver_id"]
        for i in range(20)}
    assert len(orders) > 1


def test_zero_noise_scalar_matches_r4_exactly():
    params = make_params()
    for state in (field(4), field(6, gaps=(0.0, 0.2, 0.5, 0.9, 1.4, 2.0))):
        expected = DeterministicRaceEngine().run(state, params)
        for index in range(5):
            got = run_trajectory_scalar(state, params, 123, index,
                                        zero_noise=True)
            assert got.valid
            assert got.classification.to_dict() == \
                expected.classification.to_dict()


def test_zero_noise_scalar_ignores_seed_and_index():
    state = field(4)
    params = make_params()
    base = run_trajectory_scalar(state, params, 1, 0,
                                 zero_noise=True).classification.to_dict()
    for seed, index in ((1, 5), (999, 2), (1, 0)):
        got = run_trajectory_scalar(state, params, seed, index,
                                    zero_noise=True)
        assert got.classification.to_dict() == base


# ===========================================================================
# R5-O/P chunk and prefix invariance.
# ===========================================================================

def test_chunk_invariance_of_scientific_identity():
    state = field(6, gaps=(0.0, 0.3, 0.7, 1.1, 1.6, 2.2))
    params = make_params()
    cfg = config(n=300, seed=4242, samples=10)
    identities = {
        MonteCarloEngine(chunk_size=size).run(
            state, params, cfg, Assumptions()).identity()
        for size in (1, 7, 64, 1024)}
    assert len(identities) == 1


def test_chunk_size_does_not_enter_request_identity():
    state = field(4)
    params = make_params()
    cfg = config(n=50, seed=1)
    identity = simulation_request_identity(
        state, cfg, Assumptions(), params.parameter_identity())
    a = MonteCarloEngine(chunk_size=1).run(state, params, cfg, Assumptions())
    b = MonteCarloEngine(chunk_size=64).run(state, params, cfg, Assumptions())
    assert a.simulation_request_identity == identity
    assert b.simulation_request_identity == identity
    assert a.identity() == b.identity()


def test_prefix_invariance_of_simulation_ids():
    state = field(4)
    params = make_params()
    big = MonteCarloEngine(chunk_size=13).run(
        state, params, config(n=1000, seed=77, samples=100), Assumptions())
    small = MonteCarloEngine(chunk_size=13).run(
        state, params, config(n=100, seed=77, samples=100), Assumptions())
    assert [o.to_dict() for o in big.sample_orders] == \
        [o.to_dict() for o in small.sample_orders]


# ===========================================================================
# R5-AN scalar/batch exact parity.
# ===========================================================================

@pytest.mark.parametrize("n", [10, 25, 100])
def test_scalar_batch_exact_parity(n):
    state = field(5, gaps=(0.0, 0.4, 0.8, 1.3, 1.9))
    params = make_params()
    cfg = config(n=n, seed=2024, samples=n)
    engine = MonteCarloEngine(chunk_size=7)
    batch = engine.run(state, params, cfg, Assumptions())
    scalar = engine.run_scalar(state, params, cfg, Assumptions())
    assert batch.valid_simulation_count == scalar.valid_simulation_count
    assert result_dict_without_runtime(batch) == \
        result_dict_without_runtime(scalar)
    assert batch.identity() == scalar.identity()


# ===========================================================================
# R5-R valid / invalid accounting.
# ===========================================================================

def _negative_residual():
    return _dist(100.0, probs=(0.1, 0.5, 0.9),
                 quants=(-50.0, -1.0, 1.0), observed_min=-100.0)


def test_invalid_trajectories_are_counted_and_excluded():
    driver = sim_driver("a", lap=1, race_time=90.0, age=1)
    state = sim_state([driver], scheduled=2)
    params = make_params(base=1.0, progress=0.0, degradation=0.0,
                         residual=_negative_residual())
    cfg = config(n=200, seed=5)
    engine = MonteCarloEngine(chunk_size=16)
    batch = engine.run(state, params, cfg, Assumptions())
    scalar = engine.run_scalar(state, params, cfg, Assumptions())
    assert batch.valid_simulation_count + batch.invalid_simulation_count == 200
    assert batch.valid_simulation_count > 0
    assert batch.invalid_simulation_count > 0
    assert batch.valid_simulation_count == scalar.valid_simulation_count
    assert batch.invalid_simulation_count == scalar.invalid_simulation_count


def test_zero_valid_trajectories_raise_deterministically():
    driver = sim_driver("a", lap=1, race_time=90.0, age=1)
    state = sim_state([driver], scheduled=2)
    params = make_params(base=0.0001, progress=0.0, degradation=0.0,
                         residual=_dist(-1.0, probs=(0.5,),
                                        quants=(-10.0,), observed_min=-100.0))
    with pytest.raises(SimulationValidationError):
        MonteCarloEngine().run(state, params, config(n=20, seed=3),
                               Assumptions())


def test_reliability_enabled_is_rejected_not_faked():
    state = field(4)
    params = make_params()
    cfg = SimulationConfig(simulation_count=10, master_seed=1,
                           reliability_enabled=True)
    with pytest.raises(SimulationContractError):
        MonteCarloEngine().run(state, params, cfg, Assumptions())


# ===========================================================================
# R5-S..W aggregation semantics.
# ===========================================================================

def _sample_result(n=200, seed=10, state=None, samples=0):
    state = state if state is not None else field(
        5, gaps=(0.0, 0.4, 0.8, 1.3, 1.9))
    params = make_params()
    cfg = config(n=n, seed=seed, samples=samples)
    return MonteCarloEngine(chunk_size=32).run(
        state, params, cfg, Assumptions())


def test_winner_frequencies_sum_to_one_without_normalization():
    result = _sample_result()
    total = sum(s.win_probability for s in result.driver_summaries)
    assert total == pytest.approx(1.0, abs=1e-12)
    assert result.valid_simulation_count == sum(
        round(s.win_probability * result.valid_simulation_count)
        for s in result.driver_summaries)


def test_winner_counts_match_retained_sample_orders():
    result = _sample_result(n=100, samples=100)
    assert len(result.sample_orders) == 100
    winners = [order.entries[0].driver_id for order in result.sample_orders]
    counts: dict = {}
    for winner in winners:
        counts[winner] = counts.get(winner, 0) + 1
    for summary in result.driver_summaries:
        expected = counts.get(summary.driver_id, 0) / len(winners)
        assert summary.win_probability == pytest.approx(expected)


def test_podium_mass_equals_awarded_places():
    result = _sample_result()
    assert sum(s.podium_probability
               for s in result.driver_summaries) == pytest.approx(
        PODIUM_POSITIONS, abs=1e-12)


def test_podium_mass_for_small_fields():
    for size, expected in ((1, 1.0), (2, 2.0)):
        drivers = [sim_driver(chr(ord("a") + i), lap=2, race_time=300.0 + i,
                              age=2) for i in range(size)]
        state = sim_state(drivers, scheduled=5)
        result = MonteCarloEngine(chunk_size=8).run(
            state, make_params(), config(n=50, seed=2, samples=0),
            Assumptions())
        total = sum(s.podium_probability for s in result.driver_summaries)
        assert total == pytest.approx(expected, abs=1e-12)


def test_position_distributions_are_complete_and_sum_to_one():
    state = field(5, gaps=(0.0, 0.4, 0.8, 1.3, 1.9))
    result = _sample_result(state=state)
    field_size = state.roster_size
    for summary in result.driver_summaries:
        positions = [entry.position
                     for entry in summary.finish_position_distribution]
        assert positions == list(range(1, field_size + 1))
        assert None not in positions
        total = sum(entry.frequency
                    for entry in summary.finish_position_distribution)
        assert total == pytest.approx(1.0, abs=1e-12)
        for entry in summary.finish_position_distribution:
            assert 0.0 <= entry.frequency <= 1.0
            assert math.isfinite(entry.frequency)


def test_expected_finish_matches_distribution_mean():
    result = _sample_result()
    for summary in result.driver_summaries:
        direct = sum(entry.position * entry.frequency
                     for entry in summary.finish_position_distribution)
        assert summary.expected_finish == pytest.approx(direct, abs=1e-9)
        assert 1.0 <= summary.expected_finish <= len(result.driver_summaries)


def test_no_dnf_or_points_are_fabricated():
    result = _sample_result()
    for summary in result.driver_summaries:
        assert summary.dnf_probability is None
        assert summary.points_probability is None
        assert summary.expected_points is None
        assert all(entry.position is not None
                   for entry in summary.finish_position_distribution)
    assert result.probability_semantics == PROBABILITY_SEMANTICS


def test_sample_orders_are_bounded_and_deterministic():
    state = field(4)
    params = make_params()
    cfg = config(n=80, seed=8, samples=5)
    first = MonteCarloEngine().run(state, params, cfg, Assumptions())
    second = MonteCarloEngine().run(state, params, cfg, Assumptions())
    assert len(first.sample_orders) == 5
    for order in first.sample_orders:
        assert order.roster_size == state.roster_size
        assert order.classified_count == state.roster_size
    assert [o.to_dict() for o in first.sample_orders] == \
        [o.to_dict() for o in second.sample_orders]


# ===========================================================================
# R5-AC/AD reproducibility, sensitivity, convergence.
# ===========================================================================

def test_same_seed_is_byte_equivalent():
    state = field(5)
    params = make_params()
    a = MonteCarloEngine().run(state, params, config(n=300, seed=1),
                               Assumptions())
    b = MonteCarloEngine().run(state, params, config(n=300, seed=1),
                               Assumptions())
    assert result_dict_without_runtime(a) == result_dict_without_runtime(b)
    assert a.identity() == b.identity()


def test_different_seed_changes_outcomes():
    state = field(5, gaps=(0.0, 0.4, 0.8, 1.3, 1.9))
    params = make_params()
    a = MonteCarloEngine().run(state, params, config(n=400, seed=1),
                               Assumptions())
    b = MonteCarloEngine().run(state, params, config(n=400, seed=2),
                               Assumptions())
    assert a.identity() != b.identity()


def test_probability_invariants_explicitly():
    state = field(6, gaps=(0.0, 0.3, 0.7, 1.1, 1.6, 2.2))
    result = _sample_result(n=500, seed=3, state=state)
    valid = result.valid_simulation_count
    field_size = state.roster_size
    win_total = sum(s.win_probability for s in result.driver_summaries)
    podium_total = sum(s.podium_probability for s in result.driver_summaries)
    assert valid + result.invalid_simulation_count == \
        result.requested_simulation_count
    assert win_total == pytest.approx(1.0, abs=1e-12)
    assert podium_total == pytest.approx(min(PODIUM_POSITIONS, field_size),
                                         abs=1e-12)
    for summary in result.driver_summaries:
        assert 0.0 <= summary.win_probability <= 1.0
        assert 0.0 <= summary.podium_probability <= 1.0


# ===========================================================================
# R5-AI temporal parameter policy.
# ===========================================================================

def test_historical_backtest_rejects_future_estimated_parameters():
    state = field(4)  # season 2019, params through 2024
    params = make_params(through=2024)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        MonteCarloEngine().run(
            state, params, config(n=10, seed=1), Assumptions(),
            execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    assert excinfo.value.reason == E.REASON_PARAMETER_TEMPORAL_LEAK


def test_historical_backtest_allows_prior_estimated_parameters():
    state = field(4)
    params = make_params(through=2018, seasons=(2018,))
    result = MonteCarloEngine().run(
        state, params, config(n=20, seed=1), Assumptions(),
        execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    assert result.valid_simulation_count == 20


def test_retrospective_product_allows_in_window_parameters():
    state = field(4)
    params = make_params(through=2024)
    result = MonteCarloEngine().run(
        state, params, config(n=20, seed=1), Assumptions(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert result.valid_simulation_count == 20


def test_2025_target_season_is_unsupported():
    state = sim_state([sim_driver("a", lap=2, race_time=300.0, age=2)],
                      scheduled=5, season=2025)
    with pytest.raises(SimulationUnsupportedError):
        MonteCarloEngine().run(state, make_params(), config(n=5, seed=1),
                               Assumptions())


# ===========================================================================
# R5-AJ/AK firewalls.
# ===========================================================================

def _module_imports(path: Path) -> tuple:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_monte_carlo_imports_are_firewalled():
    forbidden_prefixes = (
        "pandas", "sklearn", "joblib", "fastapi", "v2.prediction",
        "v2.model_lab", "v2.replay", "v2.race_state", "v2.d11", "v2.features",
        "v2.labels", "api",
    )
    for module in _module_imports(MODULE_PATH):
        assert not module.startswith(forbidden_prefixes), module
        assert "winner" not in module.lower()


def test_monte_carlo_source_has_no_winner_model_or_canonical_data():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    for token in ("FrozenWinnerPredictor", "read_parquet", "winner_logreg",
                  "race_driver_labels", "is_winner",
                  "load_simulation_parameters", "model_lab", "replay"):
        assert token not in names, token


def test_monte_carlo_uses_no_global_rng():
    source = MODULE_PATH.read_text(encoding="utf-8")
    for token in ("np.random", "random.random", "import random",
                  "from random", "default_rng", "time.time"):
        assert token not in source, token


def test_monte_carlo_imports_cleanly_in_fresh_process():
    code = (
        "import sys;"
        "import v2.simulation.monte_carlo as m;"
        "assert m.MONTE_CARLO_VERSION;"
        "assert 'v2.prediction' not in sys.modules;"
        "assert 'v2.model_lab' not in sys.modules;"
        "assert 'pandas' not in sys.modules;"
        "print('ok')")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_monte_carlo_never_reads_canonical_data():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "read_parquet" not in source
    assert "Parquet" not in source


# ===========================================================================
# R5-AF representative real-data fixtures (frozen Phase-5 replay seam only).
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


def test_real_zero_noise_matches_r4(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    expected = DeterministicRaceEngine().run(state, real_params)
    for index in range(3):
        got = run_trajectory_scalar(state, real_params, 11, index,
                                    zero_noise=True)
        assert got.valid
        assert got.classification.to_dict() == \
            expected.classification.to_dict()


def test_real_scalar_batch_parity(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    cfg = config(n=25, seed=99, samples=25)
    engine = MonteCarloEngine(chunk_size=4)
    batch = engine.run(state, real_params, cfg, Assumptions())
    scalar = engine.run_scalar(state, real_params, cfg, Assumptions())
    assert result_dict_without_runtime(batch) == \
        result_dict_without_runtime(scalar)


def test_real_monte_carlo_is_non_degenerate(real_params):
    state = _real_state(2023, "2023-r01-R", "alonso", 2)
    result = MonteCarloEngine(chunk_size=128).run(
        state, real_params, config(n=1000, seed=20240101), Assumptions())
    assert result.valid_simulation_count == 1000
    winners = [s.driver_id for s in result.driver_summaries
               if s.win_probability > 0.0]
    assert len(winners) >= 2
    multi_position = sum(
        1 for s in result.driver_summaries
        if sum(1 for entry in s.finish_position_distribution
               if entry.frequency > 0.0) > 1)
    assert multi_position >= 2


def test_real_1k_smoke_and_invariants(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    started = time.perf_counter()
    result = MonteCarloEngine(chunk_size=256).run(
        state, real_params, config(n=1000, seed=123, samples=3),
        Assumptions())
    elapsed = time.perf_counter() - started
    assert result.valid_simulation_count == 1000
    assert result.invalid_simulation_count == 0
    assert elapsed < 30.0
    assert sum(s.win_probability for s in result.driver_summaries) == \
        pytest.approx(1.0, abs=1e-12)
    assert len(result.sample_orders) == 3
    assert result.runtime_s is not None

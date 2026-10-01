"""Phase-7 S2: deterministic strategy intervention mechanics.

Covers STAY_OUT / PIT_NOW / PIT_NEXT_LAP action resolution against the TARGET
driver's OWN completed laps, the forced-pit draw contract, compound override
without any pace delta, R6-AB race-end suppression, supersession, immutability,
determinism, non-target isolation, and exact scalar/batch parity.
"""

from __future__ import annotations

import dataclasses
import inspect

import numpy as np
import pytest

from raceintel.simulation import monte_carlo as mc
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.params import ParameterFamily
from raceintel.simulation.state import SIMULATION_CONTRACT_VERSION
from raceintel.strategy import (
    InterventionOutcome,
    StrategyAction,
    StrategyIntervention,
    StrategyInterventionError,
    intervention_result_identity,
    parse_intervention_outcomes,
    run_intervention,
)

from test_v2_phase6_r6 import (  # noqa: E402
    COMPOUND_TRANSITION_FAMILY,
    _dist,
    _rebuild,
    _scalar,
    config,
    make_pit_params,
    noisy_residual,
    pit_field,
    sim_driver,
    sim_state,
    zero_residual,
)

D = StrategyAction

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _target_lap(state, driver_id: str) -> int:
    return state.driver_by_id[driver_id].lap_number


def intervention(state, *, driver_id: str = "a", action=D.PIT_NOW,
                 compound=None, decision_lap=None) -> StrategyIntervention:
    return StrategyIntervention(
        target_driver_id=driver_id,
        action=action,
        requested_compound=compound,
        decision_lap=(_target_lap(state, driver_id)
                      if decision_lap is None else decision_lap),
        decision_state_identity=state.identity(),
    )


def sim_cfg(*, n=1, seed=2024, samples=0) -> SimulationConfig:
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=samples, pit_dynamics_enabled=True)


def stable(result) -> dict:
    payload = result.to_dict()
    payload.pop("runtime_s", None)
    return payload


def scalar_trace(state, params, *, action, compound=None, driver_id="a",
                 seed=2024, index=0, zero_noise=True,
                 decision_lap=None):
    """Run one scalar trajectory directly and return ``(trace, iv_state)``."""
    cfg = sim_cfg(seed=seed)
    iv = intervention(state, driver_id=driver_id, action=action,
                      compound=compound, decision_lap=decision_lap)
    plan = mc._resolve_intervention(iv, state, cfg)
    selection, sampler = mc._prepare(state, params,
                                     ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                                     zero_noise)
    pit_params = mc.select_pit_parameters(state, selection, params)
    max_draws = mc.max_residual_draws(state)
    pool = None if zero_noise else mc._draw_pool(
        seed, index, max_draws, SIMULATION_CONTRACT_VERSION)
    pit = mc._ScalarPitRuntime(pit_params, seed, index, state.roster_size,
                               max_draws, SIMULATION_CONTRACT_VERSION, True)
    iv_state = mc._InterventionState(plan)
    trace: list = []
    mc._evolve_scalar(state, selection, sampler, pool, zero_noise, pit,
                      trace, iv_state)
    return trace, iv_state


def one_driver_params(*, stint=2.0, pit_loss=20.0, residual=None):
    return make_pit_params(
        residual=zero_residual() if residual is None else residual,
        stint_length=(stint,), stint_min=stint, stint_max=stint,
        pit_loss=pit_loss)


# ---------------------------------------------------------------------------
# STAY_OUT.
# ---------------------------------------------------------------------------

def test_stay_out_suppresses_exactly_the_first_decision_event():
    # stint target 2 -> baseline would pit at lap 2. STAY_OUT suppresses that
    # single decision; the next completion (lap 3) resumes ordinary mechanics.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    trace, iv_state = scalar_trace(state, params, action=D.STAY_OUT)

    pit_laps = [event["lap"] for event in trace]
    assert pit_laps == [3, 5, 7, 9, 11]  # one event suppressed, then normal
    assert iv_state.status == mc.INTERVENTION_SUPPRESSED
    assert iv_state.applied_lap == 2
    assert iv_state.baseline_pit_suppressed is True
    assert iv_state.compound_used is None


def test_stay_out_suppresses_a_decision_only_once():
    baseline_state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    baseline_trace, _ = scalar_trace(baseline_state, params,
                                     action=D.PIT_NOW)
    # PIT_NOW with an already-due target is the baseline timing (lap 2).
    stay_trace, _ = scalar_trace(baseline_state, params, action=D.STAY_OUT)
    assert baseline_trace[0]["lap"] == 2
    assert stay_trace[0]["lap"] == 3
    assert len(stay_trace) == len(baseline_trace)


def test_stay_out_never_reports_supersession():
    # STAY_OUT suppresses the target's first decision itself; there is no
    # legitimate earlier baseline pit for that driver in the window, so the
    # S0-proposed supersession state cannot occur for STAY_OUT.
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    engine = mc.MonteCarloEngine()
    engine.run(state, params, sim_cfg(n=200), Assumptions(),
               intervention=intervention(state, action=D.STAY_OUT))
    statuses = {entry["status"] for entry in engine.last_intervention_outcome}
    assert mc.INTERVENTION_SUPERSEDED not in statuses
    assert statuses <= {mc.INTERVENTION_SUPPRESSED,
                        mc.INTERVENTION_RACE_END_CANCELLED}


def test_stay_out_with_no_baseline_decision_is_consumed_as_status_only():
    # stint target 5 -> no baseline pit at lap 2; STAY_OUT fires but suppresses
    # nothing and consumes itself (one event), then normal mechanics continue.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    trace, iv_state = scalar_trace(state, params, action=D.STAY_OUT)
    assert iv_state.status == mc.INTERVENTION_SUPPRESSED
    assert iv_state.baseline_pit_suppressed is False
    assert [event["lap"] for event in trace][0] == 5


def test_stay_out_does_not_consume_pit_domain_draws_at_the_suppressed_event():
    # scheduled 3 with target 2: baseline pits once (lap 2); STAY_OUT
    # suppresses that single decision and the final lap cannot pit (R6-AB), so
    # exactly one compound / loss / target draw is never consumed.
    state = pit_field(1, scheduled=3, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    _, baseline_pit = _trace_with_pit(state, params, action=None)
    _, stay_pit = _trace_with_pit(state, params, action=D.STAY_OUT)
    assert baseline_pit.compound_cursor == stay_pit.compound_cursor + 1
    assert baseline_pit.loss_cursor == stay_pit.loss_cursor + 1
    assert baseline_pit.timing_cursor == stay_pit.timing_cursor + 1


def _trace_with_pit(state, params, *, action):
    cfg = sim_cfg(seed=2024)
    selection, sampler = mc._prepare(state, params,
                                     ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                                     True)
    pit_params = mc.select_pit_parameters(state, selection, params)
    max_draws = mc.max_residual_draws(state)
    pit = mc._ScalarPitRuntime(pit_params, 2024, 0, state.roster_size,
                               max_draws, SIMULATION_CONTRACT_VERSION, True)
    iv_state = None
    if action is not None:
        iv = intervention(state, action=action)
        iv_state = mc._InterventionState(
            mc._resolve_intervention(iv, state, cfg))
    trace: list = []
    mc._evolve_scalar(state, selection, sampler, None, True, pit, trace,
                      iv_state)
    return trace, pit


# ---------------------------------------------------------------------------
# PIT_NOW.
# ---------------------------------------------------------------------------

def test_pit_now_forces_the_pit_at_the_next_completed_lap():
    # target 5 means baseline would not pit until lap 5; PIT_NOW forces lap 2.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NOW)
    # Forced at lap 2, next target 5 -> lap 7, then lap 12 is race end.
    assert [event["lap"] for event in trace] == [2, 7]
    assert iv_state.status == mc.INTERVENTION_APPLIED
    assert iv_state.applied_lap == 2
    assert iv_state.compound_used is not None


def test_pit_now_never_double_pits_at_the_decision_event():
    # Baseline already due at lap 2; PIT_NOW must replace, not add to, it.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    trace, _ = scalar_trace(state, params, action=D.PIT_NOW)
    first_event_laps = [event["lap"] for event in trace if event["lap"] == 2]
    assert first_event_laps == [2]
    assert [event["lap"] for event in trace] == [2, 4, 6, 8, 10]


def test_pit_now_explicit_compound_is_used_and_the_draw_is_consumed(
        monkeypatch):
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    # HARD -> MEDIUM (0.4) / SOFT (0.6): u=0.1 -> MEDIUM, u=0.9 -> SOFT.
    entries = {
        "HARD->MEDIUM": _scalar(0.4),
        "HARD->SOFT": _scalar(0.6),
        "MEDIUM->HARD": _scalar(1.0),
        "SOFT->HARD": _scalar(1.0),
        "GLOBAL->HARD": _scalar(1.0),
    }
    params = _rebuild(
        one_driver_params(stint=5.0),
        **{COMPOUND_TRANSITION_FAMILY: ParameterFamily(
            COMPOUND_TRANSITION_FAMILY, "probability", entries)})
    units = np.array([0.1, 0.9])

    def fake_pool(seed, index, domain, size, contract_version):
        if domain == "compound":
            return np.resize(units, size)
        return np.full(size, 0.5)

    monkeypatch.setattr(mc, "_draw_domain_pool", fake_pool)
    selection, sampler = mc._prepare(state, params,
                                     ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                                     True)
    pit = mc._ScalarPitRuntime(
        mc.select_pit_parameters(state, selection, params), 1, 0,
        state.roster_size, mc.max_residual_draws(state),
        SIMULATION_CONTRACT_VERSION, False)
    # The override wins over the sampled target, but the draw is consumed.
    assert pit._draw_next_compound("HARD", "SOFT") == "SOFT"
    assert pit.compound_cursor == 1
    # The next ordinary draw uses the SECOND uniform (0.9 -> SOFT), not the
    # first (0.1 -> MEDIUM): proves the overridden draw was spent.
    assert pit._draw_next_compound("HARD") == "SOFT"


def test_pit_now_consumes_exactly_one_draw_per_pit_domain():
    # scheduled 3, target 5: exactly one forced pit (lap 2); lap 3 is race end.
    state = pit_field(1, scheduled=3, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    _, pit = _trace_with_pit(state, params, action=D.PIT_NOW)
    assert pit.compound_cursor == 1
    assert pit.loss_cursor == 1
    # One initial stint target draw plus the forced pit's next stint target.
    assert pit.timing_cursor == 2


def test_stay_out_consumes_no_pit_domain_draws():
    state = pit_field(1, scheduled=3, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    _, stay_pit = _trace_with_pit(state, params, action=D.STAY_OUT)
    assert stay_pit.compound_cursor == 0
    assert stay_pit.loss_cursor == 0
    # Only the initial stint target draw remains.
    assert stay_pit.timing_cursor == 1


def test_pit_now_null_compound_uses_the_baseline_sampled_transition():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    # HARD -> SOFT deterministically; null compound must sample it.
    entries = {
        "HARD->SOFT": _scalar(1.0),
        "SOFT->HARD": _scalar(1.0),
        "GLOBAL->HARD": _scalar(1.0),
    }
    params = _rebuild(
        one_driver_params(stint=5.0),
        **{COMPOUND_TRANSITION_FAMILY: ParameterFamily(
            COMPOUND_TRANSITION_FAMILY, "probability", entries)})
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NOW)
    assert trace[0]["compound_after"] == "SOFT"
    assert iv_state.compound_used == "SOFT"


def test_pit_now_reuses_the_phase6_pit_loss_and_tyre_age_semantics():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0, pit_loss=20.0)
    engine = mc.MonteCarloEngine()
    result = engine.run(state, params, sim_cfg(samples=1), Assumptions(),
                        intervention=intervention(state, action=D.PIT_NOW))
    entry = result.sample_orders[0].entries[0]
    # 12 laps at 90 s plus two empirical 20 s stops (lap 2 forced, lap 7).
    assert entry.race_time_s == pytest.approx(12 * 90.0 + 2 * 20.0)
    trace, _ = scalar_trace(state, params, action=D.PIT_NOW)
    assert trace[0]["tyre_age_after_pit"] == 0
    assert trace[0]["out_lap_tyre_age"] == 1


def test_next_stint_target_uses_the_phase6_grid_after_a_forced_pit():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=3.0)
    trace, _ = scalar_trace(state, params, action=D.PIT_NOW)
    # Forced pit at lap 2 -> next stint target 3 -> next stop at lap 5.
    assert [event["lap"] for event in trace][:2] == [2, 5]
    assert trace[0]["target_age"] == 3


def test_pit_now_applies_to_the_target_drivers_own_lap_when_lapped():
    # "a" is a lap down (own lap 1) while "b" leads (lap 3). The decision must
    # be a's own next completed lap (2), never b's lap count.
    drivers = [
        sim_driver("a", lap=1, race_time=90.0, age=1, position=2),
        sim_driver("b", lap=3, race_time=270.0, age=1, position=1),
    ]
    state = sim_state(drivers, scheduled=12)
    params = one_driver_params(stint=5.0)
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NOW,
                                   driver_id="a")
    a_laps = [event["lap"] for event in trace if event["driver_id"] == "a"]
    assert a_laps[0] == 2
    assert iv_state.applied_lap == 2


# ---------------------------------------------------------------------------
# PIT_NEXT_LAP.
# ---------------------------------------------------------------------------

def test_pit_next_lap_keeps_the_first_completion_baseline_normal():
    # target 5: baseline would not pit at lap 2, so the forced pit lands at 3.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NEXT_LAP)
    assert [event["lap"] for event in trace] == [3, 8]
    assert iv_state.status == mc.INTERVENTION_APPLIED
    assert iv_state.applied_lap == 3


def test_pit_next_lap_is_superseded_by_a_baseline_pit_at_first_completion():
    # target 2: baseline pits at lap 2, so the forced lap 3 is cancelled.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NEXT_LAP)
    assert [event["lap"] for event in trace] == [2, 4, 6, 8, 10]
    assert iv_state.status == mc.INTERVENTION_SUPERSEDED
    assert iv_state.reason == mc.REASON_SUPERSEDED_BY_BASELINE_PIT
    assert iv_state.applied_lap is None


def test_pit_next_lap_explicit_compound_applies_at_the_second_completion():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    trace, iv_state = scalar_trace(state, params, action=D.PIT_NEXT_LAP,
                                   compound="HARD")
    assert trace[0]["lap"] == 3
    assert iv_state.compound_used == "HARD"


# ---------------------------------------------------------------------------
# Race-end suppression (R6-AB) and static beyond-race rejection.
# ---------------------------------------------------------------------------

def test_pit_now_at_the_final_lap_is_race_end_suppressed():
    state = pit_field(2, scheduled=2, start_lap=1)
    params = one_driver_params(stint=2.0)
    engine = mc.MonteCarloEngine()
    engine.run(state, params, sim_cfg(), Assumptions(),
               intervention=intervention(state, action=D.PIT_NOW))
    outcome = engine.last_intervention_outcome[0]
    assert outcome["status"] == mc.INTERVENTION_RACE_END_CANCELLED
    assert outcome["reason"] == mc.REASON_RACE_END_SUPPRESSED
    assert outcome["applied_lap"] is None


def test_intervention_never_reached_before_race_end_is_cancelled():
    drivers = [
        sim_driver("a", lap=1, race_time=500.0, age=1, position=2),
        sim_driver("b", lap=9, race_time=100.0, age=1, position=1),
    ]
    state = sim_state(drivers, scheduled=10)
    params = one_driver_params(stint=5.0)
    for action in (D.PIT_NOW, D.STAY_OUT, D.PIT_NEXT_LAP):
        engine = mc.MonteCarloEngine()
        engine.run(state, params, sim_cfg(), Assumptions(),
                   intervention=intervention(state, action=action))
        outcome = engine.last_intervention_outcome[0]
        assert outcome["status"] == mc.INTERVENTION_RACE_END_CANCELLED
        assert outcome["reason"] == mc.REASON_RACE_END_SUPPRESSED


def test_decision_beyond_race_is_rejected_statically():
    state = pit_field(2, scheduled=2, start_lap=1)  # target own lap 1
    params = one_driver_params(stint=2.0)
    # PIT_NEXT_LAP needs lap 1 + 2 = 3 > scheduled 2.
    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(
            state, params, sim_cfg(), Assumptions(),
            intervention=intervention(state, action=D.PIT_NEXT_LAP))
    assert excinfo.value.reason == mc.REASON_STRATEGY_DECISION_BEYOND_RACE


# ---------------------------------------------------------------------------
# Runtime validation.
# ---------------------------------------------------------------------------

def test_anchor_mismatch_is_rejected():
    state = pit_field(2, scheduled=12)
    params = one_driver_params()
    iv = dataclasses.replace(
        intervention(state), decision_state_identity="not-the-state")
    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(state, params, sim_cfg(), Assumptions(),
                                  intervention=iv)
    assert excinfo.value.reason == mc.REASON_STRATEGY_ANCHOR_MISMATCH


def test_target_driver_not_in_roster_is_rejected():
    state = pit_field(2, scheduled=12)
    params = one_driver_params()
    iv = StrategyIntervention(
        target_driver_id="missing", action=D.PIT_NOW,
        requested_compound=None, decision_lap=1,
        decision_state_identity=state.identity())
    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(state, params, sim_cfg(), Assumptions(),
                                  intervention=iv)
    assert excinfo.value.reason == \
        mc.REASON_STRATEGY_TARGET_DRIVER_NOT_IN_ROSTER


def test_decision_lap_mismatch_is_rejected():
    state = pit_field(2, scheduled=12)
    params = one_driver_params()
    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(
            state, params, sim_cfg(), Assumptions(),
            intervention=intervention(state, decision_lap=7))
    assert excinfo.value.reason == mc.REASON_STRATEGY_DECISION_LAP_MISMATCH


def test_intervention_requires_pit_dynamics():
    state = pit_field(2, scheduled=12)
    params = one_driver_params()
    cfg = SimulationConfig(simulation_count=1, master_seed=1,
                           pit_dynamics_enabled=False)
    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(state, params, cfg, Assumptions(),
                                  intervention=intervention(state))
    assert excinfo.value.reason == \
        mc.REASON_STRATEGY_PIT_DYNAMICS_REQUIRED


def test_malformed_intervention_is_never_silently_ignored():
    state = pit_field(2, scheduled=12)
    params = one_driver_params()

    class Fake:
        pass

    with pytest.raises(StrategyInterventionError) as excinfo:
        mc.MonteCarloEngine().run(state, params, sim_cfg(), Assumptions(),
                                  intervention=Fake())
    assert excinfo.value.reason == mc.REASON_STRATEGY_MALFORMED


# ---------------------------------------------------------------------------
# Non-target isolation (white-box mask check).
# ---------------------------------------------------------------------------

def test_intervention_masks_never_touch_a_non_target_driver():
    state = pit_field(3, scheduled=12)
    params = one_driver_params(stint=5.0)
    selection, sampler = mc._prepare(state, params,
                                     ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                                     True)
    evolution = mc._ChunkEvolution(
        state, selection, sampler, mc.max_residual_draws(state), 1, [0], True,
        SIMULATION_CONTRACT_VERSION,
        mc.select_pit_parameters(state, selection, params), False,
        intervention_plan=mc._resolve_intervention(
            intervention(state, driver_id="b", action=D.PIT_NOW),
            state, sim_cfg()))
    # Drive the target's decision event synthetically at lap 2.
    evolution.lap[0, 1] = 2
    advance = np.zeros((1, 3), dtype=bool)
    advance[0, 1] = True
    newly_finished = np.zeros((1, 3), dtype=bool)
    race_over = np.zeros(1, dtype=bool)
    force, suppress, override = evolution._intervention_step(
        advance, newly_finished, race_over)
    target_column = 1
    other = np.ones(3, dtype=bool)
    other[target_column] = False
    assert not force[:, other].any()
    assert not suppress[:, other].any()
    assert all(override[0, column] is None for column in np.where(other)[0])
    assert force[0, target_column]


# ---------------------------------------------------------------------------
# Immutability / no mutation.
# ---------------------------------------------------------------------------

def test_strategy_run_does_not_mutate_state_parameters_or_intervention():
    state = pit_field(3, scheduled=12)
    params = one_driver_params(stint=3.0)
    state_before = state.to_dict()
    param_identity_before = params.parameter_identity().identity()
    families_before = dict(params.families)
    iv = intervention(state, action=D.PIT_NOW, compound="SOFT")
    iv_before = iv.to_dict()
    mc.MonteCarloEngine().run(state, params, sim_cfg(), Assumptions(),
                              intervention=iv)
    assert state.to_dict() == state_before
    assert params.parameter_identity().identity() == param_identity_before
    assert params.families == families_before
    assert iv.to_dict() == iv_before


def test_intervention_contract_stays_immutable():
    state = pit_field(2, scheduled=12)
    iv = intervention(state)
    with pytest.raises(dataclasses.FrozenInstanceError):
        iv.action = D.STAY_OUT


# ---------------------------------------------------------------------------
# Determinism and result identity.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action,compound", [
    (D.STAY_OUT, None), (D.PIT_NOW, None), (D.PIT_NOW, "SOFT"),
    (D.PIT_NEXT_LAP, None), (D.PIT_NEXT_LAP, "HARD")])
def test_each_action_is_deterministic(action, compound):
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=action, compound=compound)
    first = mc.MonteCarloEngine()
    second = mc.MonteCarloEngine()
    r1 = first.run(state, params, sim_cfg(n=40, samples=5), Assumptions(),
                   intervention=iv)
    r2 = second.run(state, params, sim_cfg(n=40, samples=5), Assumptions(),
                    intervention=iv)
    assert stable(r1) == stable(r2)
    assert first.last_intervention_outcome == second.last_intervention_outcome


def test_intervention_result_identity_is_deterministic_and_strategy_owned():
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=D.PIT_NOW, compound="SOFT")
    cfg = sim_cfg(n=20, samples=5)

    def once():
        engine = mc.MonteCarloEngine()
        result, outcomes = run_intervention(engine, state, params, cfg,
                                            Assumptions(), iv)
        return intervention_result_identity(
            state=state, parameters=params, config=cfg, intervention=iv,
            result=result, outcomes=outcomes)

    assert once() == once()


def test_intervention_result_differs_from_baseline_result_identity():
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=D.PIT_NOW)
    cfg = sim_cfg(n=40)
    baseline = mc.MonteCarloEngine().run(state, params, cfg, Assumptions())
    pitted = mc.MonteCarloEngine().run(state, params, cfg, Assumptions(),
                                       intervention=iv)
    assert baseline.identity() != pitted.identity()


# ---------------------------------------------------------------------------
# Scalar / batch parity.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action,compound", [
    (D.STAY_OUT, None), (D.PIT_NOW, None), (D.PIT_NOW, "SOFT"),
    (D.PIT_NEXT_LAP, None), (D.PIT_NEXT_LAP, "HARD")])
def test_scalar_batch_parity_with_interventions(action, compound):
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=action, compound=compound)
    cfg = sim_cfg(n=60, samples=60)
    engine = mc.MonteCarloEngine(chunk_size=7)
    batch = engine.run(state, params, cfg, Assumptions(), intervention=iv)
    batch_outcomes = engine.last_intervention_outcome
    scalar = engine.run_scalar(state, params, cfg, Assumptions(),
                               intervention=iv)
    scalar_outcomes = engine.last_intervention_outcome
    assert stable(batch) == stable(scalar)
    assert batch.identity() == scalar.identity()
    assert batch_outcomes == scalar_outcomes
    assert batch_outcomes is not None


def test_scalar_batch_parity_for_supersession_and_race_end():
    # Supersession.
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=D.PIT_NEXT_LAP)
    cfg = sim_cfg(n=30, samples=30)
    engine = mc.MonteCarloEngine(chunk_size=4)
    engine.run(state, params, cfg, Assumptions(), intervention=iv)
    superseded = engine.last_intervention_outcome
    engine.run_scalar(state, params, cfg, Assumptions(), intervention=iv)
    assert engine.last_intervention_outcome == superseded
    # Race end.
    late = [sim_driver("a", lap=1, race_time=500.0, age=1, position=2),
            sim_driver("b", lap=9, race_time=100.0, age=1, position=1)]
    race_state = sim_state(late, scheduled=10)
    riv = intervention(race_state, action=D.PIT_NOW)
    rcfg = sim_cfg(n=5, samples=5)
    engine.run(race_state, params, rcfg, Assumptions(), intervention=riv)
    batch = engine.last_intervention_outcome
    engine.run_scalar(race_state, params, rcfg, Assumptions(), intervention=riv)
    assert engine.last_intervention_outcome == batch


def test_chunk_and_prefix_invariance_with_interventions():
    state = pit_field(4, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    iv = intervention(state, action=D.PIT_NEXT_LAP, compound="MEDIUM")
    cfg = sim_cfg(n=200, seed=4242, samples=10)
    identities = {
        mc.MonteCarloEngine(chunk_size=size).run(
            state, params, cfg, Assumptions(), intervention=iv).identity()
        for size in (1, 7, 64, 512)}
    assert len(identities) == 1
    big = mc.MonteCarloEngine(chunk_size=13).run(
        state, params, sim_cfg(n=400, seed=77, samples=50), Assumptions(),
        intervention=iv)
    small = mc.MonteCarloEngine(chunk_size=13).run(
        state, params, sim_cfg(n=50, seed=77, samples=50), Assumptions(),
        intervention=iv)
    assert [o.to_dict() for o in big.sample_orders] == \
        [o.to_dict() for o in small.sample_orders]


# ---------------------------------------------------------------------------
# Compound has no pace effect.
# ---------------------------------------------------------------------------

def test_forced_compound_does_not_introduce_a_pace_offset_path():
    # Structural: the expected-lap-time path carries no compound argument and
    # the batch scheduler never reads the compound identity.
    assert "compound" not in inspect.signature(
        mc.expected_lap_time_s).parameters
    assert "compound" not in inspect.getsource(mc._ChunkEvolution._schedule)


def test_forced_compound_changes_only_compound_identity_with_equal_grids():
    # Equal stint grid/transition for SOFT and HARD: the forced compound must
    # not change the simulated classification at all (no pace delta).
    state = pit_field(3, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    cfg = sim_cfg(n=40)
    soft = mc.MonteCarloEngine().run(
        state, params, cfg, Assumptions(),
        intervention=intervention(state, action=D.PIT_NOW, compound="SOFT"))
    hard = mc.MonteCarloEngine().run(
        state, params, cfg, Assumptions(),
        intervention=intervention(state, action=D.PIT_NOW, compound="HARD"))
    assert stable(soft) == stable(hard)


# ---------------------------------------------------------------------------
# Default-off compatibility and outcome plumbing.
# ---------------------------------------------------------------------------

def test_none_intervention_still_reproduces_the_phase6_baseline():
    state = pit_field(4, scheduled=15)
    params = make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                             stint_min=2.0, stint_max=6.0, pit_loss=20.0)
    cfg = sim_cfg(n=200)
    plain = mc.MonteCarloEngine(chunk_size=13)
    without = plain.run(state, params, cfg, Assumptions())
    explicit_engine = mc.MonteCarloEngine(chunk_size=13)
    explicit = explicit_engine.run(state, params, cfg, Assumptions(),
                                   intervention=None)
    assert stable(without) == stable(explicit)
    assert without.identity() == explicit.identity()
    assert plain.last_intervention_outcome is None
    assert explicit_engine.last_intervention_outcome is None


def test_outcome_is_available_and_parseable_for_every_action():
    state = pit_field(2, scheduled=15)
    params = one_driver_params(stint=3.0)
    for action in D:
        engine = mc.MonteCarloEngine()
        engine.run(state, params, sim_cfg(n=4), Assumptions(),
                   intervention=intervention(state, action=action))
        parsed = parse_intervention_outcomes(engine.last_intervention_outcome)
        assert len(parsed) == 4
        assert all(isinstance(entry, InterventionOutcome) for entry in parsed)
        assert all(entry.action == action.value for entry in parsed)

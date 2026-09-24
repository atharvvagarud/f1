"""Phase-7 S3: paired Monte Carlo / common-random-numbers substrate.

Covers the per-index outcome contract (exact aggregate reproduction,
scalar/batch parity, chunk/prefix/order invariance), the stable strategy-owned
paired identity, the valid/invalid pair accounting, raw paired differences and
their sign semantics, STAY_OUT inert realizations, PIT_NEXT_LAP supersession,
PIT_NOW baseline-aligned behavior, explicit-compound CRN cursor alignment,
immutability, determinism, and default-off Phase-6 compatibility.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import numpy as np
import pytest

from v2.simulation import monte_carlo as mc
from v2.simulation.config import Assumptions, SimulationConfig
from v2.simulation.engine import ExecutionPolicy
from v2.simulation.monte_carlo import MonteCarloEngine
from v2.simulation.state import SIMULATION_CONTRACT_VERSION
from v2.strategy import (
    StrategyAction,
    StrategyIntervention,
    paired_differences,
    run_pair,
)
from v2.strategy.paired import (
    PairingDiagnostics,
    PerIndexOutcome,
    _pairing_diagnostics,
)

from test_v2_phase6_r6 import (  # noqa: E402
    COMPOUND_TRANSITION_FAMILY,
    _rebuild,
    _scalar,
    make_pit_params,
    noisy_residual,
    pit_field,
    zero_residual,
)
from v2.simulation.params import ParameterFamily  # noqa: E402

D = StrategyAction
ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def sim_cfg(*, n=1, seed=2024, samples=0) -> SimulationConfig:
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=samples, pit_dynamics_enabled=True)


def intervention(state, *, driver_id="a", action=D.PIT_NOW, compound=None,
                 decision_lap=None) -> StrategyIntervention:
    return StrategyIntervention(
        target_driver_id=driver_id,
        action=action,
        requested_compound=compound,
        decision_lap=(state.driver_by_id[driver_id].lap_number
                      if decision_lap is None else decision_lap),
        decision_state_identity=state.identity(),
    )


def one_driver_params(*, stint=2.0, pit_loss=20.0, residual=None):
    return make_pit_params(
        residual=zero_residual() if residual is None else residual,
        stint_length=(stint,), stint_min=stint, stint_max=stint,
        pit_loss=pit_loss)


def noisy_params(*, stint=(3.0,), minimum=2.0, maximum=6.0, pit_loss=20.0):
    return make_pit_params(residual=noisy_residual(), stint_length=stint,
                           stint_min=minimum, stint_max=maximum,
                           pit_loss=pit_loss)


def _raw(engine):
    return engine.last_index_outcomes


# ---------------------------------------------------------------------------
# Per-index outcome contract / aggregate reproduction.
# ---------------------------------------------------------------------------

def test_per_index_outcomes_reproduce_the_aggregate_exactly():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=300, seed=99)
    engine = MonteCarloEngine(chunk_size=17)
    result = engine.run(state, params, cfg, Assumptions(),
                        collect_index_outcomes=True)
    raw = _raw(engine)
    valid = raw["valid"]
    positions = raw["finish_position"]
    n = int(valid.sum())
    assert n == result.valid_simulation_count
    assert raw["finish_position"].shape == (cfg.simulation_count,
                                            state.roster_size)
    for column, driver_id in enumerate(state.roster_driver_ids):
        summary = result.driver_summary_by_id[driver_id]
        win = int((positions[valid, column] == 1).sum()) / n
        podium = int((positions[valid, column] <= 3).sum()) / n
        expected = float(positions[valid, column].mean())
        assert win == summary.win_probability
        assert podium == summary.podium_probability
        assert expected == pytest.approx(summary.expected_finish, abs=1e-12)
        distribution = {entry.position: entry.frequency
                        for entry in summary.finish_position_distribution}
        for position in range(1, state.roster_size + 1):
            count = int((positions[valid, column] == position).sum())
            assert count / n == distribution[position]


def test_per_index_collection_is_opt_in_and_does_not_change_the_result():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=120, seed=11)
    engine = MonteCarloEngine(chunk_size=13)
    plain = engine.run(state, params, cfg, Assumptions())
    assert engine.last_index_outcomes is None
    collected = engine.run(state, params, cfg, Assumptions(),
                           collect_index_outcomes=True)
    assert plain.identity() == collected.identity()
    assert engine.last_index_outcomes is not None


def test_batch_and_scalar_per_index_outcomes_are_identical():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=60, seed=2024)
    iv = intervention(state, driver_id="b", action=D.PIT_NEXT_LAP,
                      compound="MEDIUM")
    for kwargs in ({}, {"intervention": iv}):
        batch_engine = MonteCarloEngine(chunk_size=7)
        scalar_engine = MonteCarloEngine()
        batch_engine.run(state, params, cfg, Assumptions(),
                         collect_index_outcomes=True, **kwargs)
        scalar_engine.run_scalar(state, params, cfg, Assumptions(),
                                 collect_index_outcomes=True, **kwargs)
        batch = _raw(batch_engine)
        scalar = _raw(scalar_engine)
        assert np.array_equal(batch["valid"], scalar["valid"])
        assert np.array_equal(batch["finish_position"],
                              scalar["finish_position"])
        assert list(batch["invalid_reason"]) == list(scalar["invalid_reason"])


def test_chunk_invariance_of_paired_results():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=200, seed=4242)
    iv = intervention(state, action=D.PIT_NOW, compound="SOFT")
    identities = {
        run_pair(state, params, cfg, Assumptions(), iv,
                 chunk_size=size).identity()
        for size in (1, 7, 64, 512)}
    assert len(identities) == 1


def test_prefix_invariance_of_per_index_outcomes():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    big_engine = MonteCarloEngine(chunk_size=13)
    small_engine = MonteCarloEngine(chunk_size=13)
    big_engine.run(state, params, sim_cfg(n=400, seed=77), Assumptions(),
                   collect_index_outcomes=True)
    small_engine.run(state, params, sim_cfg(n=50, seed=77), Assumptions(),
                     collect_index_outcomes=True)
    big = _raw(big_engine)
    small = _raw(small_engine)
    assert np.array_equal(big["finish_position"][:50],
                          small["finish_position"])
    assert np.array_equal(big["valid"][:50], small["valid"])


def test_run_order_does_not_change_either_arm():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=80, seed=5)
    iv = intervention(state, action=D.PIT_NEXT_LAP)

    def arm(engine, kwargs):
        engine.run(state, params, cfg, Assumptions(),
                   collect_index_outcomes=True, **kwargs)
        return _raw(engine)

    first = MonteCarloEngine(chunk_size=9)
    baseline_first = arm(first, {})
    intervention_first = arm(first, {"intervention": iv})
    second = MonteCarloEngine(chunk_size=9)
    intervention_second = arm(second, {"intervention": iv})
    baseline_second = arm(second, {})
    assert np.array_equal(baseline_first["finish_position"],
                          baseline_second["finish_position"])
    assert np.array_equal(intervention_first["finish_position"],
                          intervention_second["finish_position"])


# ---------------------------------------------------------------------------
# Paired identity.
# ---------------------------------------------------------------------------

def test_paired_identity_is_stable_and_sensitive_to_inputs():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=60, seed=2024)
    iv = intervention(state, action=D.PIT_NOW)

    def once(cfg=cfg, iv=iv, params=params, state=state):
        return run_pair(state, params, cfg, Assumptions(), iv).identity()

    assert once() == once()
    other_seed = once(cfg=sim_cfg(n=60, seed=7))
    other_count = once(cfg=sim_cfg(n=30, seed=2024))
    other_action = once(iv=intervention(state, action=D.STAY_OUT))
    other_compound = once(iv=intervention(state, action=D.PIT_NOW,
                                          compound="SOFT"))
    baseline_iv = once()
    assert len({once(), other_seed, other_count, other_action,
                other_compound}) == 5
    # Different state identity (and its matching intervention anchor) changes
    # the identity.
    other_state = pit_field(3, scheduled=16)
    assert once(state=other_state,
                iv=intervention(other_state, action=D.PIT_NOW)) != baseline_iv


def test_paired_identity_is_deterministic_and_default_off_compatible():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=40, seed=3)
    iv = intervention(state, action=D.STAY_OUT)
    first = run_pair(state, params, cfg, Assumptions(), iv)
    second = run_pair(state, params, cfg, Assumptions(), iv)
    assert first.identity() == second.identity()
    assert [o.to_dict() for o in first.baseline_outcomes] == \
        [o.to_dict() for o in second.baseline_outcomes]
    assert [o.to_dict() for o in first.intervention_outcomes] == \
        [o.to_dict() for o in second.intervention_outcomes]
    # Phase-6 product path stays aggregate-only unless explicitly requested.
    engine = MonteCarloEngine()
    engine.run(state, params, cfg, Assumptions())
    assert engine.last_index_outcomes is None


def test_per_index_ordering_and_same_index_pairing():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=50, seed=17)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.PIT_NOW))
    assert len(pair.baseline_outcomes) == cfg.simulation_count
    assert len(pair.intervention_outcomes) == cfg.simulation_count
    for base, iv in zip(pair.baseline_outcomes, pair.intervention_outcomes):
        assert base.simulation_index == iv.simulation_index
        if not base.valid:
            assert base.finishing_order == ()
            assert base.winner_driver_id is None
            continue
        order = base.finishing_order
        assert len(order) == state.roster_size
        assert len(set(order)) == state.roster_size
        assert set(order) == set(state.roster_driver_ids)
        assert base.winner_driver_id == order[0]
        assert base.target_finish_position == \
            order.index(pair.target_driver_id) + 1
    # Both arms ran under the same seed/index identity.
    assert pair.baseline_result.master_seed == cfg.master_seed
    assert pair.intervention_result.master_seed == cfg.master_seed
    assert pair.baseline_result.requested_simulation_count == \
        cfg.simulation_count


# ---------------------------------------------------------------------------
# Valid / invalid accounting.
# ---------------------------------------------------------------------------

def _outcome(index, *, valid, status=None, reason=None, won=None, podium=None,
             finish=None, target="a"):
    return PerIndexOutcome(
        simulation_index=index, valid=valid,
        winner_driver_id=("a" if valid else None),
        finishing_order=(("a", "b") if valid else ()),
        target_finish_position=finish, target_won=won, target_podium=podium,
        intervention_status=status, intervention_reason=reason)


def test_valid_invalid_pair_accounting_is_exhaustive():
    baseline = (
        _outcome(0, valid=True),
        _outcome(1, valid=True),
        _outcome(2, valid=False),
        _outcome(3, valid=False),
        _outcome(4, valid=True),
    )
    intervention = (
        _outcome(0, valid=True, status=mc.INTERVENTION_APPLIED,
                 reason=mc.REASON_FORCED_PIT),
        _outcome(1, valid=False, status=mc.INTERVENTION_RACE_END_CANCELLED,
                 reason=mc.REASON_RACE_END_SUPPRESSED),
        _outcome(2, valid=True, status=mc.INTERVENTION_SUPPRESSED,
                 reason=None),
        _outcome(3, valid=False, status=mc.INTERVENTION_SUPERSEDED,
                 reason=mc.REASON_SUPERSEDED_BY_BASELINE_PIT),
        _outcome(4, valid=True, status=mc.INTERVENTION_SUPPRESSED,
                 reason=mc.REASON_BASELINE_PIT_SUPPRESSED),
    )
    diag = _pairing_diagnostics(baseline, intervention)
    assert diag.pairs_total == 5
    assert diag.pairs_both_valid == 2
    assert diag.baseline_only_valid == 1
    assert diag.intervention_only_valid == 1
    assert diag.both_invalid == 1
    assert diag.intervention_applied == 1
    assert diag.intervention_suppressed == 2
    assert diag.intervention_inert == 1
    assert diag.intervention_superseded == 1
    assert diag.race_end_cancelled == 1
    assert (diag.pairs_both_valid + diag.baseline_only_valid
            + diag.intervention_only_valid + diag.both_invalid
            == diag.pairs_total)


# ---------------------------------------------------------------------------
# Raw paired differences and sign semantics.
# ---------------------------------------------------------------------------

def test_finish_and_win_difference_sign_for_a_forced_pit():
    # Two identical-pace drivers; 'a' leads by canonical id. Baseline stint 8
    # produces one stop (lap 8), but forcing 'a' to pit at lap 2 resets the age
    # and adds a SECOND stop at lap 10, so 'b' wins: a's finish worsens
    # (1 -> 2) and it loses the win. d_finish = baseline - intervention is
    # therefore negative.
    state = pit_field(2, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=8.0, pit_loss=20.0)
    cfg = sim_cfg(n=5)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, driver_id="a", action=D.PIT_NOW))
    diffs = paired_differences(pair)
    assert diffs.valid_pairs == 5
    assert diffs.mean_d_finish == -1.0
    assert diffs.mean_d_win == -1.0
    assert diffs.mean_d_podium == 0.0
    for base, iv in zip(pair.baseline_outcomes, pair.intervention_outcomes):
        assert base.target_finish_position == 1
        assert iv.target_finish_position == 2
        assert base.target_won is True and iv.target_won is False


def test_paired_difference_sign_convention_is_explicit():
    # Positive d_finish must mean a lower (better) intervention position.
    state = pit_field(2, scheduled=12)
    params = one_driver_params(stint=5.0)
    cfg = sim_cfg(n=1)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.PIT_NOW))
    base = pair.baseline_outcomes[0]
    iv = pair.intervention_outcomes[0]
    crafted = dataclasses.replace(
        pair, diagnostics=PairingDiagnostics(
            pairs_total=1, pairs_both_valid=1, baseline_only_valid=0,
            intervention_only_valid=0, both_invalid=0,
            intervention_applied=1, intervention_suppressed=0,
            intervention_superseded=0, intervention_inert=0,
            race_end_cancelled=0))
    crafted = dataclasses.replace(
        crafted,
        baseline_outcomes=(dataclasses.replace(base, target_finish_position=5,
                                               target_won=False,
                                               target_podium=False),),
        intervention_outcomes=(dataclasses.replace(iv, target_finish_position=2,
                                                   target_won=False,
                                                   target_podium=True),))
    diffs = paired_differences(crafted)
    assert diffs.d_finish == (3,)
    assert diffs.d_podium == (1,)
    assert diffs.mean_d_finish == 3.0


def test_paired_differences_use_only_complete_valid_pairs():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=40, seed=8)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.PIT_NEXT_LAP))
    diffs = paired_differences(pair)
    assert diffs.valid_pairs == pair.diagnostics.pairs_both_valid
    assert len(diffs.d_win) == diffs.valid_pairs
    assert len(diffs.d_finish) == diffs.valid_pairs


# ---------------------------------------------------------------------------
# STAY_OUT / PIT_NEXT_LAP / PIT_NOW semantics under pairing.
# ---------------------------------------------------------------------------

def test_stay_out_inert_realization_is_recorded_and_baseline_equivalent():
    # Target 5: baseline would not pit at the decision lap, so STAY_OUT is
    # behaviorally inert there. It consumes itself and changes nothing.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    cfg = sim_cfg(n=4)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.STAY_OUT))
    assert pair.diagnostics.intervention_inert == 4
    assert pair.diagnostics.intervention_suppressed == 4
    assert pair.baseline_result.identity() == \
        pair.intervention_result.identity()
    assert all(o.intervention_status == mc.INTERVENTION_SUPPRESSED
               and o.intervention_reason is None
               for o in pair.intervention_outcomes)


def test_stay_out_suppressing_a_real_baseline_pit_is_not_inert():
    # Scheduled 11, target 2: baseline makes a stop at lap 10; STAY_OUT shifts
    # the sequence so the final stop would fall at the race-end instant and is
    # suppressed (one fewer stop). With two equal-pace drivers the suppressed
    # driver is faster and wins, so the aggregate changes.
    state = pit_field(2, scheduled=11, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    cfg = sim_cfg(n=4)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, driver_id="b", action=D.STAY_OUT))
    assert pair.diagnostics.intervention_suppressed == 4
    assert pair.diagnostics.intervention_inert == 0
    assert all(o.intervention_reason == mc.REASON_BASELINE_PIT_SUPPRESSED
               for o in pair.intervention_outcomes)
    assert pair.baseline_result.identity() != \
        pair.intervention_result.identity()


def test_pit_next_lap_supersession_is_baseline_equivalent():
    # Baseline pits at the first completion (target 2) -> the forced second-lap
    # pit is SUPERSEDED and the intervention trajectory equals the baseline.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    cfg = sim_cfg(n=6)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.PIT_NEXT_LAP))
    assert pair.diagnostics.intervention_superseded == 6
    assert pair.diagnostics.intervention_applied == 0
    assert pair.baseline_result.identity() == \
        pair.intervention_result.identity()
    assert all(o.intervention_status == mc.INTERVENTION_SUPERSEDED
               and o.intervention_reason
               == mc.REASON_SUPERSEDED_BY_BASELINE_PIT
               for o in pair.intervention_outcomes)


def test_pit_now_baseline_aligned_pit_is_not_a_new_stop():
    # Baseline is already due at the decision lap; PIT_NOW replaces it. With a
    # null compound the draw order is identical, so the trajectory is
    # byte-identical to the baseline (baseline-aligned, not a new stop).
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    cfg = sim_cfg(n=6)
    pair = run_pair(state, params, cfg, Assumptions(),
                    intervention(state, action=D.PIT_NOW))
    assert pair.diagnostics.intervention_applied == 6
    assert pair.baseline_result.identity() == \
        pair.intervention_result.identity()


def test_pre_divergence_invariance_for_pit_next_lap():
    # Target 5: the first post-T completion is baseline-normal (no pit), so the
    # forced pit lands at the target driver's second completion (lap 3).
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    pair = run_pair(state, params, sim_cfg(n=3), Assumptions(),
                    intervention(state, action=D.PIT_NEXT_LAP))
    assert pair.diagnostics.intervention_applied == 3
    assert all(o.intervention_status == mc.INTERVENTION_APPLIED
               for o in pair.intervention_outcomes)


def test_pit_now_diverges_at_the_first_post_T_completion():
    # stint 8: baseline stops once; PIT_NOW forces an early stop that adds a
    # second stop, so the arms diverge.
    state = pit_field(2, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=8.0)
    pair = run_pair(state, params, sim_cfg(n=3), Assumptions(),
                    intervention(state, driver_id="a", action=D.PIT_NOW))
    assert pair.diagnostics.intervention_applied == 3
    assert pair.baseline_result.identity() != \
        pair.intervention_result.identity()


# ---------------------------------------------------------------------------
# Explicit compound CRN cursor alignment.
# ---------------------------------------------------------------------------

def test_explicit_compound_consumes_the_compound_uniform_for_crn_alignment(
        monkeypatch):
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    # HARD -> MEDIUM (0.4) / SOFT (0.6): u=0.1 -> MEDIUM, u=0.9 -> SOFT.
    params = _rebuild(one_driver_params(stint=5.0), **{
        COMPOUND_TRANSITION_FAMILY: ParameterFamily(
            COMPOUND_TRANSITION_FAMILY, "probability", {
                "HARD->MEDIUM": _scalar(0.4),
                "HARD->SOFT": _scalar(0.6),
                "MEDIUM->HARD": _scalar(1.0),
                "SOFT->HARD": _scalar(1.0),
                "GLOBAL->HARD": _scalar(1.0),
            })})
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
    # The override wins but still consumes the (first) compound uniform.
    assert pit._draw_next_compound("HARD", "SOFT") == "SOFT"
    assert pit.compound_cursor == 1
    # The next ordinary pit reads the SECOND uniform (0.9 -> SOFT), not the
    # first (0.1 -> MEDIUM): proves the overridden draw was spent.
    assert pit._draw_next_compound("HARD") == "SOFT"


# ---------------------------------------------------------------------------
# Immutability / no mutation / no future data.
# ---------------------------------------------------------------------------

def test_run_pair_does_not_mutate_state_parameters_or_intervention():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=30)
    iv = intervention(state, action=D.PIT_NOW, compound="SOFT")
    state_before = state.to_dict()
    param_identity_before = params.parameter_identity().identity()
    families_before = dict(params.families)
    iv_before = iv.to_dict()
    run_pair(state, params, cfg, Assumptions(), iv)
    assert state.to_dict() == state_before
    assert params.parameter_identity().identity() == param_identity_before
    assert params.families == families_before
    assert iv.to_dict() == iv_before


def test_paired_module_reads_no_future_or_oracle_material():
    tree = ast.parse((ROOT / "v2" / "strategy" / "paired.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("v2.simulation.validation", "v2.replay", "v2.replay_reconstruction",
              "v2.prediction", "v2.model_lab", "pandas", "sklearn")
    for module in imported:
        assert not module.startswith(banned), f"paired.py imports {module}"
    # run_pair accepts only scientific inputs, never an oracle/result argument.
    import inspect
    parameters = set(inspect.signature(run_pair).parameters)
    assert parameters == {
        "state", "parameters", "config", "assumptions", "intervention",
        "execution_policy", "zero_noise", "chunk_size"}

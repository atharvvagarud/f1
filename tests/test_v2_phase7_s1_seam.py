"""Phase-7 intervention seam: default-off + S2 execution tests.

Verifies the additive seam is default-off and byte-identical to Phase-6 when no
intervention is supplied, that a valid supplied intervention actually executes
on BOTH paths, that an invalid intervention is rejected before any draw, and
that the simulation layer never imports the strategy layer (no cycle).

The S1 "supplied intervention raises NotImplemented" assertions are superseded
by S2 mechanics (which execute the intervention); they are replaced here. The
S1 contract and Phase-6 compatibility suites remain authoritative.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.monte_carlo import (
    MonteCarloEngine,
    StrategyInterventionNotImplemented,
)
from raceintel.strategy import (
    StrategyAction,
    StrategyIntervention,
    StrategyInterventionError,
)

from test_v2_phase6_r6 import make_pit_params, noisy_residual, pit_field

ROOT = Path(__file__).resolve().parents[1]
SIMULATION_DIR = ROOT / "raceintel" / "simulation"


@pytest.fixture(scope="module")
def state():
    return pit_field(3, scheduled=15)


@pytest.fixture(scope="module")
def params():
    return make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                           stint_min=2.0, stint_max=6.0, pit_loss=20.0)


@pytest.fixture(scope="module")
def config():
    return SimulationConfig(simulation_count=60, master_seed=2024,
                            sample_orders=5, pit_dynamics_enabled=True)


def _intervention(state) -> StrategyIntervention:
    return StrategyIntervention(
        target_driver_id="a",
        action=StrategyAction.PIT_NOW,
        requested_compound="SOFT",
        decision_lap=1,
        decision_state_identity=state.identity(),
    )


def _stable(result) -> dict:
    payload = result.to_dict()
    payload.pop("runtime_s", None)
    return payload


def test_intervention_default_is_none_on_both_paths():
    for method in (MonteCarloEngine.run, MonteCarloEngine.run_scalar):
        parameter = inspect.signature(method).parameters["intervention"]
        assert parameter.default is None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_none_intervention_is_byte_identical_to_no_argument(state, params,
                                                            config):
    engine = MonteCarloEngine(chunk_size=7)
    without = engine.run(state, params, config, Assumptions())
    explicit = engine.run(state, params, config, Assumptions(),
                          intervention=None)
    assert explicit.identity() == without.identity()
    assert _stable(explicit) == _stable(without)


def test_none_intervention_matches_on_the_scalar_path(state, params, config):
    engine = MonteCarloEngine(chunk_size=7)
    without = engine.run_scalar(state, params, config, Assumptions())
    explicit = engine.run_scalar(state, params, config, Assumptions(),
                                 intervention=None)
    assert explicit.identity() == without.identity()


def test_none_intervention_does_not_mutate_inputs(state, params, config):
    state_before = state.to_dict()
    config_before = config.to_dict()
    assumptions = Assumptions()
    assumptions_before = assumptions.to_dict()
    MonteCarloEngine().run(state, params, config, assumptions,
                           intervention=None)
    assert state.to_dict() == state_before
    assert config.to_dict() == config_before
    assert assumptions.to_dict() == assumptions_before


# ---------------------------------------------------------------------------
# A supplied intervention is never silently ignored: it executes (S2) or is
# rejected with a structured error before any draw.
# ---------------------------------------------------------------------------

def test_supplied_intervention_executes_on_the_batch_path(state, params,
                                                          config):
    baseline = MonteCarloEngine(chunk_size=7).run(
        state, params, config, Assumptions())
    engine = MonteCarloEngine(chunk_size=7)
    result = engine.run(state, params, config, Assumptions(),
                        intervention=_intervention(state))
    assert engine.last_intervention_outcome is not None
    assert len(engine.last_intervention_outcome) == config.simulation_count
    assert result.identity() != baseline.identity()


def test_supplied_intervention_executes_on_the_scalar_path(state, params,
                                                           config):
    engine = MonteCarloEngine(chunk_size=7)
    result = engine.run_scalar(state, params, config, Assumptions(),
                               intervention=_intervention(state))
    assert engine.last_intervention_outcome is not None
    assert len(engine.last_intervention_outcome) == config.simulation_count
    assert result.identity() is not None


def test_invalid_intervention_is_rejected_before_any_rng_stream_is_created(
        monkeypatch, state, params, config):
    calls = {"pace": 0, "domain": 0}
    module = __import__("raceintel.simulation.monte_carlo", fromlist=["x"])
    real_sim = module.rng_for_simulation
    real_domain = module.rng_for_domain

    def spy_sim(*args, **kwargs):
        calls["pace"] += 1
        return real_sim(*args, **kwargs)

    def spy_domain(*args, **kwargs):
        calls["domain"] += 1
        return real_domain(*args, **kwargs)

    monkeypatch.setattr(module, "rng_for_simulation", spy_sim)
    monkeypatch.setattr(module, "rng_for_domain", spy_domain)
    bad = StrategyIntervention(
        target_driver_id="a", action=StrategyAction.PIT_NOW,
        requested_compound=None, decision_lap=1,
        decision_state_identity="not-the-state")
    with pytest.raises(StrategyInterventionError):
        MonteCarloEngine().run(state, params, config, Assumptions(),
                               intervention=bad)
    assert calls == {"pace": 0, "domain": 0}


def test_the_retained_s1_seam_error_type_is_still_importable():
    # Kept for backward compatibility; S2 no longer raises it.
    assert issubclass(StrategyInterventionNotImplemented, ValueError)


def test_none_intervention_and_no_argument_create_the_same_streams(
        monkeypatch, state, params, config):
    module = __import__("raceintel.simulation.monte_carlo", fromlist=["x"])
    real_sim = module.rng_for_simulation
    real_domain = module.rng_for_domain

    def count_for_call(with_argument: bool) -> dict:
        calls = {"pace": 0, "domain": 0}

        def spy_sim(*args, **kwargs):
            calls["pace"] += 1
            return real_sim(*args, **kwargs)

        def spy_domain(*args, **kwargs):
            calls["domain"] += 1
            return real_domain(*args, **kwargs)

        monkeypatch.setattr(module, "rng_for_simulation", spy_sim)
        monkeypatch.setattr(module, "rng_for_domain", spy_domain)
        engine = MonteCarloEngine(chunk_size=7)
        if with_argument:
            engine.run(state, params, config, Assumptions(),
                       intervention=None)
        else:
            engine.run(state, params, config, Assumptions())
        return calls

    without = count_for_call(False)
    with_none = count_for_call(True)
    assert with_none == without


# ---------------------------------------------------------------------------
# Dependency direction / firewall.
# ---------------------------------------------------------------------------

def test_simulation_layer_imports_no_strategy_module():
    for path in SIMULATION_DIR.glob("*.py"):
        tree = ast.parse(path.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name.startswith("raceintel.strategy") for name in imported), \
            f"{path.name} imports the strategy layer (dependency cycle risk)"

"""Phase-7 S6: final scientific validation + adversarial regression.

This suite pins the S6 invariants that make the Strategy Engine safe to expose
as a product feature. It is deliberately offline and synthetic so it runs
without the generated ``/data/v2/`` corpus; the full representative corpus and
the red-team run live in ``scripts/run_phase7_s6_validation.py`` and
``scripts/run_phase7_s6_red_team.py``.

It adds NO strategy capability. Covered: the frozen protocol identity, the
one-way dependency direction, unsupported-state refusal, anchor and
intervention rejection, candidate-set canonicalisation, determinism,
immutability, objective / uncertainty / denominator semantics, probability and
counterfactual metadata, serialization identity and the authorized-drift
governance.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from raceintel.race_state.race_state import WeatherState
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.monte_carlo import (
    _resolve_intervention,
)
from raceintel.simulation.monte_carlo import StrategyInterventionError
from raceintel.simulation.results import PROBABILITY_SEMANTICS
from raceintel.simulation.state import DriverSimState, DriverStatus
from raceintel.strategy import (
    DEFAULT_BOOTSTRAP_REPLICATES,
    STRATEGY_OBJECTIVES,
    StrategyAction,
    StrategyIntervention,
    compare_strategies,
    compute_uncertainty,
    evaluate_objective,
    generate_candidates,
    objective_value,
)
from raceintel.strategy.candidates import (
    CANDIDATE_INVALIDITY_REASONS,
    CANONICAL_CANDIDATE_SPECS,
    build_candidate,
    candidate_identity,
)
from raceintel.strategy.comparison import CandidateComparison, TargetAggregate
from raceintel.strategy.contracts import (
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
    StrategyContractError,
)
from raceintel.strategy.objectives import OBJECTIVE_METRIC
from raceintel.strategy.paired import PerIndexOutcome

from test_v2_phase6_r6 import (  # noqa: E402
    make_pit_params,
    noisy_residual,
    pit_field,
    sim_driver,
    sim_state,
)

import s6_validation_protocol as P  # noqa: E402

D = StrategyAction
ROOT = Path(__file__).resolve().parents[1]


def sim_cfg(*, n=32, seed=2024, samples=0, pit=True) -> SimulationConfig:
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=samples, pit_dynamics_enabled=pit)


def params():
    return make_pit_params(residual=noisy_residual(), stint_length=(3.0,),
                           stint_min=2.0, stint_max=6.0, pit_loss=20.0)


def intervention(state, *, driver_id="a", action=D.PIT_NOW, compound=None):
    return StrategyIntervention(
        target_driver_id=driver_id, action=action, requested_compound=compound,
        decision_lap=state.driver_by_id[driver_id].lap_number,
        decision_state_identity=state.identity())


def outcome(index, *, valid=True, finish=None):
    if not valid:
        return PerIndexOutcome(
            simulation_index=index, valid=False, winner_driver_id=None,
            finishing_order=(), target_finish_position=None, target_won=None,
            target_podium=None, intervention_status=None,
            intervention_reason=None)
    won = finish == 1
    podium = finish is not None and finish <= 3
    return PerIndexOutcome(
        simulation_index=index, valid=True, winner_driver_id="x",
        finishing_order=("x",), target_finish_position=finish,
        target_won=won, target_podium=podium, intervention_status=None,
        intervention_reason=None)


def candidate(key, compound=None):
    action, _, suffix = key.partition(":")
    if compound is None and suffix and suffix != "SAMPLED":
        compound = suffix
    from raceintel.strategy.candidates import StrategyCandidate
    dummy = StrategyIntervention(
        target_driver_id="d0", action=action, requested_compound=compound,
        decision_lap=0, decision_state_identity="s")
    return StrategyCandidate(action=action, requested_compound=compound,
                             valid=True, reason=None, intervention=dummy)


def candidate_comparison(key, outcomes, compound=None):
    return CandidateComparison(
        candidate=candidate(key, compound), valid=True, reason=None,
        evaluated=True, aggregate=None, execution=None, delta_source=None,
        delta_win_probability=None, delta_podium_probability=None,
        delta_expected_finish=None,
        valid_pairs=sum(1 for value in outcomes if value.valid),
        baseline_only_valid=0, intervention_only_valid=0, both_invalid=0,
        validity_sets_match=True, paired_identity=None,
        intervention_outcomes=tuple(outcomes))


def synthetic_comparison(baseline_outcomes, candidates):
    from raceintel.strategy.comparison import StrategyComparisonResult
    return StrategyComparisonResult(
        state_identity="s", parameter_identity="p", config_identity="c",
        master_seed=1, simulation_count=len(baseline_outcomes),
        target_driver_id="d0", supported=True, unsupported_reason=None,
        baseline=TargetAggregate(
            valid_simulations=len(baseline_outcomes), invalid_simulations=0,
            win_probability=0.0, podium_probability=0.0, expected_finish=0.0,
            finish_position_distribution=()),
        candidates=tuple(candidates),
        baseline_outcomes=tuple(baseline_outcomes))


# ===========================================================================
# Protocol identity and deterministic selection.
# ===========================================================================

def test_protocol_identity_is_frozen():
    assert P.STRATEGY_VALIDATION_PROTOCOL_VERSION == "s6-validation-v1"
    assert P.S6_RED_TEAM_VERSION == "s6-red-team-v1"
    assert P.BROAD_SIMULATION_COUNT == 1000
    assert P.DEEP_SIMULATION_COUNT == 10000
    assert P.EVALUATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert P.STAGES == ("EARLY", "MID", "LATE")
    assert P.BANDS == ("FRONT", "MIDFIELD", "BACK")
    assert 2025 not in P.EVALUATION_SEASONS


@pytest.mark.skipif(not P.r7_artifact_available(),
                    reason="Phase-6 R7 corpus not generated here")
def test_corpus_is_deterministic_and_spans_seasons_and_stages():
    first = P.select_corpus()
    second = P.select_corpus()
    assert first == second
    assert len(first) == len(P.EVALUATION_SEASONS) * len(P.STAGES)
    assert {record["stage"] for record in first} == set(P.STAGES)
    assert {record["season"] for record in first} == set(P.EVALUATION_SEASONS)
    assert {record["race_id"] for record in first} > {r["race_id"]
                                                      for r in first[:3]}
    jobs = P.select_broad_jobs()
    assert len(jobs) == len(first) * len(P.BANDS)
    assert {band for _, band in jobs} == set(P.BANDS)


def test_deep_corpus_is_deterministic_and_three_candidates():
    assert P.select_deep_corpus() == P.select_deep_corpus()
    assert len(P.DEEP_SPECS) == 3


# ===========================================================================
# Dependency / architecture.
# ===========================================================================

def _imports(path):
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_simulation_imports_no_strategy():
    offenders = {}
    for path in (ROOT / "raceintel" / "simulation").glob("*.py"):
        hits = [module for module in _imports(path)
                if module.startswith("raceintel.strategy")]
        if hits:
            offenders[path.name] = hits
    assert offenders == {}


def test_strategy_imports_no_api_frontend_model_lab_or_future():
    banned = ("raceintel.api", "frontend", "raceintel.model_lab", "raceintel.prediction",
              "raceintel.replay", "raceintel.validation", "sklearn")
    offenders = {}
    for path in (ROOT / "raceintel" / "strategy").glob("*.py"):
        hits = [module for module in _imports(path)
                if any(module.startswith(token) for token in banned)]
        if hits:
            offenders[path.name] = hits
    assert offenders == {}


def test_strategy_internal_graph_is_acyclic():
    files = {path.stem: path for path in
             (ROOT / "raceintel" / "strategy").glob("*.py")}
    edges = {name: set() for name in files}
    for name, path in files.items():
        for module in _imports(path):
            if module.startswith("raceintel.strategy."):
                target = module.rsplit(".", 1)[-1]
                if target in files:
                    edges[name].add(target)
    visiting = set()
    visited = set()

    def visit(node):
        if node in visited:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for target in edges.get(node, ()):
            if visit(target):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    assert not any(visit(node) for node in list(edges))


# ===========================================================================
# Contract / anchor / intervention attacks.
# ===========================================================================

def test_wrong_anchor_and_lap_and_driver_rejected():
    state = pit_field(3, scheduled=15)
    config = sim_cfg()
    lap = state.driver_by_id["a"].lap_number
    wrong_identity = StrategyIntervention(
        target_driver_id="a", action=D.PIT_NOW, requested_compound=None,
        decision_lap=lap, decision_state_identity="0" * 64)
    with pytest.raises(StrategyInterventionError) as exc:
        _resolve_intervention(wrong_identity, state, config)
    assert exc.value.reason == "anchor_mismatch"

    wrong_lap = StrategyIntervention(
        target_driver_id="a", action=D.PIT_NOW, requested_compound=None,
        decision_lap=lap + 1, decision_state_identity=state.identity())
    with pytest.raises(StrategyInterventionError) as exc:
        _resolve_intervention(wrong_lap, state, config)
    assert exc.value.reason == "decision_lap_mismatch"

    ghost = StrategyIntervention(
        target_driver_id="ghost", action=D.PIT_NOW, requested_compound=None,
        decision_lap=lap, decision_state_identity=state.identity())
    with pytest.raises(StrategyInterventionError) as exc:
        _resolve_intervention(ghost, state, config)
    assert exc.value.reason == "target_driver_not_in_roster"


def test_decision_beyond_race_rejected():
    state = pit_field(2, scheduled=2)
    config = sim_cfg()
    beyond = StrategyIntervention(
        target_driver_id="a", action=D.PIT_NEXT_LAP, requested_compound=None,
        decision_lap=state.driver_by_id["a"].lap_number,
        decision_state_identity=state.identity())
    with pytest.raises(StrategyInterventionError) as exc:
        _resolve_intervention(beyond, state, config)
    assert exc.value.reason in ("decision_beyond_race",
                                "decision_lap_mismatch")


def test_contract_rejects_unknown_action_compound_and_provenance():
    state = pit_field(3, scheduled=15)
    lap = state.driver_by_id["a"].lap_number
    identity = state.identity()

    def build(**overrides):
        payload = {
            "target_driver_id": "a", "action": D.PIT_NOW,
            "requested_compound": None, "decision_lap": lap,
            "decision_state_identity": identity,
        }
        payload.update(overrides)
        return StrategyIntervention(**payload)

    with pytest.raises(StrategyContractError):
        build(action="TELEPORT")
    with pytest.raises(StrategyContractError):
        build(action="pit_now")
    with pytest.raises(StrategyContractError):
        build(requested_compound="PLASMA")
    with pytest.raises(StrategyContractError):
        build(requested_compound="WET")
    with pytest.raises(StrategyContractError):
        build(requested_compound="")
    with pytest.raises(StrategyContractError):
        build(action=D.STAY_OUT, requested_compound="SOFT")
    with pytest.raises(StrategyContractError):
        build(provenance="FACTUAL_AT_T")
    with pytest.raises(StrategyContractError):
        build(intervention_version="v99")
    with pytest.raises(StrategyContractError):
        build(strategy_contract_version="s99")


def test_build_candidate_returns_structured_reasons():
    state = pit_field(3, scheduled=15)
    config = sim_cfg()
    candidate = build_candidate(state, config, "a", "TELEPORT", None)
    assert candidate.valid is False
    assert candidate.reason == "unsupported_action"
    candidate = build_candidate(state, config, "a", D.PIT_NOW, "PLASMA")
    assert candidate.valid is False
    assert candidate.reason == "unsupported_compound"
    assert candidate.reason in CANDIDATE_INVALIDITY_REASONS


# ===========================================================================
# Unsupported-state refusal.
# ===========================================================================

def test_unsupported_states_are_structured_not_partial():
    drivers = tuple(
        sim_driver(chr(ord("a") + i), lap=5, race_time=450.0 + i,
                   position=i + 1)
        for i in range(6))

    def attempt(state):
        return compare_strategies(state, params(), sim_cfg(n=16, pit=True),
                                  Assumptions(), "a",
                                  candidate_specs=(("STAY_OUT", None),))

    cases = {
        "wet_track_conditions": sim_state(
            drivers, scheduled=20,
            weather=WeatherState(rainfall=True)),
        "neutralized_track_state": sim_state(drivers, scheduled=20,
                                             track="safety_car"),
        "red_flag_track_state": sim_state(drivers, scheduled=20,
                                          track="red_flag"),
        "unknown_track_state": sim_state(drivers, scheduled=20, track=None),
    }
    missing = tuple(
        DriverSimState(driver_id=chr(ord("a") + i), lap_number=5,
                       race_time_s=450.0 + i, position=i + 1,
                       compound="MEDIUM", tyre_age=None, stint_number=1,
                       pit_count=0, constructor_id="c1",
                       status=DriverStatus.ACTIVE)
        for i in range(6))
    cases["missing_tyre_age"] = sim_state(missing, scheduled=20)
    stale = tuple(
        DriverSimState(driver_id=chr(ord("a") + i), lap_number=5,
                       race_time_s=450.0 + i, position=i + 1,
                       compound="MEDIUM", tyre_age=3, stint_number=1,
                       pit_count=0, constructor_id="c1",
                       status=DriverStatus.ACTIVE,
                       observation_age_s=1e6)
        for i in range(6))
    cases["non_contemporaneous_roster_member"] = sim_state(stale, scheduled=20)

    for expected, state in cases.items():
        comparison = attempt(state)
        assert comparison.supported is False
        assert comparison.unsupported_reason == expected
        assert all(not candidate.evaluated
                   for candidate in comparison.candidates)

    ghost = compare_strategies(
        sim_state(drivers, scheduled=20), params(), sim_cfg(n=16, pit=True),
        Assumptions(), "ghost", candidate_specs=(("STAY_OUT", None),))
    assert ghost.supported is False
    assert ghost.unsupported_reason == "target_driver_not_in_roster"


# ===========================================================================
# Candidate / determinism / immutability.
# ===========================================================================

def test_canonical_candidate_set_and_dedup_order():
    state = pit_field(3, scheduled=15)
    full = generate_candidates(state, sim_cfg(), "a")
    assert len(full) == 9
    assert [value.key for value in full] == [
        "STAY_OUT:SAMPLED",
        "PIT_NOW:SAMPLED", "PIT_NOW:SOFT", "PIT_NOW:MEDIUM", "PIT_NOW:HARD",
        "PIT_NEXT_LAP:SAMPLED", "PIT_NEXT_LAP:SOFT", "PIT_NEXT_LAP:MEDIUM",
        "PIT_NEXT_LAP:HARD"]
    reversed_set = generate_candidates(
        state, sim_cfg(), "a", specs=tuple(reversed(CANONICAL_CANDIDATE_SPECS)))
    assert [value.key for value in reversed_set] == [value.key
                                                     for value in full]
    duplicates = generate_candidates(
        state, sim_cfg(), "a",
        specs=(("PIT_NOW", None), ("PIT_NOW", None), ("STAY_OUT", None)))
    assert [value.key for value in duplicates] == ["STAY_OUT:SAMPLED",
                                                   "PIT_NOW:SAMPLED"]
    assert candidate_identity(D.PIT_NOW, "SOFT") == \
        candidate_identity("PIT_NOW", "SOFT")


def test_same_request_is_deterministic_and_immutable():
    state = pit_field(3, scheduled=15)
    parameters = params()
    config = sim_cfg(n=32)
    state_identity = state.identity()
    config_identity = config.identity()
    parameter_identity = parameters.parameter_identity().identity()
    first = compare_strategies(state, parameters, config, Assumptions(), "a")
    first_dict = first.to_dict()
    evaluate_objective(first, "MAXIMIZE_WIN_PROBABILITY",
                       bootstrap_replicates=100)
    second = compare_strategies(state, parameters, config, Assumptions(), "a")
    assert first.identity() == second.identity()
    assert first.to_dict() == first_dict
    assert state.identity() == state_identity
    assert config.identity() == config_identity
    assert parameters.parameter_identity().identity() == parameter_identity


def test_candidate_set_does_not_change_a_candidate_result():
    state = pit_field(3, scheduled=15)
    parameters = params()
    config = sim_cfg(n=32)
    one = compare_strategies(state, parameters, config, Assumptions(), "a",
                             candidate_specs=(("PIT_NOW", None),))
    many = compare_strategies(state, parameters, config, Assumptions(), "a",
                              candidate_specs=(("PIT_NOW", None),
                                               ("STAY_OUT", None)))
    one_dict = one.candidates[0].to_dict()
    many_dict = next(value.to_dict() for value in many.candidates
                     if value.candidate.key == "PIT_NOW:SAMPLED")
    assert one_dict == many_dict


# ===========================================================================
# Objective / uncertainty / denominator semantics (synthetic, exact).
# ===========================================================================

def test_probability_semantics_and_no_phase3_import():
    assert PROBABILITY_SEMANTICS == "MONTE_CARLO_FREQUENCY"
    for path in (ROOT / "raceintel" / "strategy").glob("*.py"):
        source = path.read_text()
        assert "INDEPENDENT_BINARY" not in source


def test_counterfactual_metadata_uses_bounded_language():
    from raceintel.strategy import comparison as comparison_module
    metadata = " ".join([comparison_module.COUNTERFACTUAL_SEMANTICS,
                         *comparison_module._LIMITATIONS]).lower()
    for phrase in ("would have won", "best strategy", "optimal strategy",
                   "guaranteed", "proves", "real advantage"):
        assert phrase not in metadata


def test_exactly_three_objectives_and_no_default():
    assert len(STRATEGY_OBJECTIVES) == 3
    assert set(OBJECTIVE_METRIC) == set(STRATEGY_OBJECTIVES)
    with pytest.raises(Exception):
        objective_value(None)


def test_objective_selection_changes_point_estimate_leader():
    n = 100
    baseline = [outcome(i, finish=3) for i in range(n)]
    a = [outcome(i, finish=1 if i < 40 else 5) for i in range(n)]
    b = [outcome(i, finish=2 if i < 80 else 6) for i in range(n)]
    c = [outcome(i, finish=1 if i < 30 else 3) for i in range(n)]
    comparison = synthetic_comparison(baseline, [
        candidate_comparison("PIT_NOW:SAMPLED", a),
        candidate_comparison("PIT_NOW:SOFT", b),
        candidate_comparison("PIT_NEXT_LAP:SAMPLED", c)])
    leaders = {
        objective: evaluate_objective(comparison, objective,
                                      bootstrap_replicates=100)
        .leader_by_point_estimate
        for objective in STRATEGY_OBJECTIVES}
    assert len(set(leaders.values())) >= 2, leaders


def test_leader_ambiguity_uses_direct_pairwise_comparison():
    n = 100
    baseline = [outcome(i, finish=4) for i in range(n)]
    l_finish = [1 if i < 52 else 4 for i in range(n)]
    m_finish = []
    for i in range(n):
        if i < 52 and i not in range(0, 5):
            m_finish.append(1)
        elif 52 <= i < 56:
            m_finish.append(1)
        else:
            m_finish.append(4)
    n_finish = [4] * n
    comparison = synthetic_comparison(baseline, [
        candidate_comparison("PIT_NOW:SAMPLED",
                             [outcome(i, finish=l_finish[i])
                              for i in range(n)]),
        candidate_comparison("PIT_NOW:SOFT",
                             [outcome(i, finish=m_finish[i])
                              for i in range(n)]),
        candidate_comparison("PIT_NEXT_LAP:SAMPLED",
                             [outcome(i, finish=n_finish[i])
                              for i in range(n)])])
    result = evaluate_objective(comparison, "MAXIMIZE_WIN_PROBABILITY",
                                bootstrap_replicates=500)
    assert result.leader_by_point_estimate is not None
    assert result.indistinguishable_from_leader
    assert "best_strategy" not in result.to_dict()


def test_validity_denominator_is_complete_pairs_only():
    baseline = [outcome(i, finish=4) for i in range(10)]
    candidate = [outcome(i, finish=3) for i in range(7)] + [
        outcome(i, valid=False) for i in range(7, 10)]
    uncertainty = compute_uncertainty(
        baseline, candidate, metric="EXPECTED_FINISH",
        substrate_identity="s", subject_identity="c", include_unpaired=False)
    assert uncertainty.valid_pairs == 7
    assert uncertainty.point_estimate == 1.0
    empty = compute_uncertainty(
        [outcome(i, valid=False) for i in range(10)],
        [outcome(i, valid=False) for i in range(10)],
        metric="EXPECTED_FINISH", substrate_identity="s",
        subject_identity="c", include_unpaired=False)
    assert empty.availability == "NO_VALID_PAIRS"
    assert empty.point_estimate is None


def test_uncertainty_small_n_and_zero_variance_policy():
    baseline = [outcome(i, finish=4) for i in range(50)]
    candidate = [outcome(i, finish=3) for i in range(50)]
    constant = compute_uncertainty(
        baseline, candidate, metric="EXPECTED_FINISH",
        substrate_identity="s", subject_identity="c")
    assert constant.paired_se == 0.0
    assert constant.ci_low == constant.ci_high == 1.0
    import re
    assert not re.search(r"\bcertain\b",
                         json.dumps(constant.to_dict()).lower())

    one_pair = compute_uncertainty(
        baseline[:1], candidate[:1], metric="EXPECTED_FINISH",
        substrate_identity="s", subject_identity="c")
    assert one_pair.valid_pairs == 1
    assert one_pair.paired_se is None
    assert one_pair.availability == "INSUFFICIENT_PAIRS"
    assert one_pair.point_estimate == 1.0


def test_comparison_dict_and_identity_exclude_retained_outcomes():
    state = pit_field(3, scheduled=15)
    comparison = compare_strategies(state, params(), sim_cfg(n=16),
                                    Assumptions(), "a",
                                    candidate_specs=(("STAY_OUT", None),))
    payload = comparison.to_dict()
    assert "baseline_outcomes" not in payload
    assert all("intervention_outcomes" not in candidate
               for candidate in payload["candidates"])
    identity = comparison.identity()
    assert dataclasses.replace(comparison,
                               baseline_outcomes=()).identity() == identity


# ===========================================================================
# Serialization and authorized-drift governance.
# ===========================================================================

def test_serialization_identity_stable_and_sensitive():
    state = pit_field(3, scheduled=15)
    iv = intervention(state)
    payload = iv.to_dict()
    reordered = {key: payload[key] for key in reversed(list(payload))}
    assert StrategyIntervention.from_dict(reordered).identity() == \
        iv.identity()
    assert dataclasses.replace(iv, requested_compound="SOFT").identity() != \
        iv.identity()


def test_authorized_drift_matches_live_simulator():
    # C2 structural migration: v2/simulation/monte_carlo.py moved to
    # raceintel/simulation/monte_carlo.py with import-prefix rewrite only.
    # The drift record is frozen evidence (v2 paths + hashes intact); the
    # live file must exist at the new path with acknowledged-different
    # bytes; its new hash is pinned in the C2 migration record.
    drift = json.loads(
        (ROOT / "docs" / "PHASE7_AUTHORIZED_PHASE6_DRIFT.json").read_text())
    assert drift["authorized_files"] == ["v2/simulation/monte_carlo.py"]
    assert not (ROOT / "v2" / "simulation" / "monte_carlo.py").exists()
    live_path = ROOT / "raceintel" / "simulation" / "monte_carlo.py"
    assert live_path.is_file()
    live = hashlib.sha256(live_path.read_bytes()).hexdigest()
    assert live != drift["current_sha256"]["v2/simulation/monte_carlo.py"]
    assert drift["phase7_stage"] in {"S1", "S2", "S3"}
    assert STRATEGY_CONTRACT_VERSION == "s1"
    assert INTERVENTION_VERSION == "v1"
    assert DEFAULT_BOOTSTRAP_REPLICATES == 2000

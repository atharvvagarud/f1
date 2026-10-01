"""Phase-7 S5: explicit objectives, baseline-relative and direct pairwise policy.

Covers the three objective mappings, the absence of a default objective and of a
weighted score, baseline-relative classification (including all-worse and
all-inconclusive results), direct candidate-vs-candidate pairing (positive =
A better) with explicit A/B validity counts, the refusal of the CI-overlap
heuristic, point-estimate ordering and leader ambiguity, execution-context
retention, order/subset invariance, determinism, and the no-simulation-rerun
and semantics firewalls.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.monte_carlo import MonteCarloEngine
from raceintel.simulation.results import PROBABILITY_SEMANTICS
from raceintel.strategy import (
    OBJECTIVE_DEGRADATION,
    OBJECTIVE_IMPROVEMENT,
    OBJECTIVE_INCONCLUSIVE,
    OBJECTIVE_METRIC,
    OBJECTIVE_SAMPLING_SEMANTICS,
    OBJECTIVE_UNAVAILABLE,
    OBJECTIVE_VERSION,
    STRATEGY_OBJECTIVES,
    StrategyAction,
    StrategyObjective,
    compare_strategies,
    evaluate_objective,
    objective_metric,
    objective_value,
)
from raceintel.strategy.paired import PerIndexOutcome
from raceintel.strategy.uncertainty import MIN_VALID_PAIRS_FOR_CI

from test_v2_phase6_r6 import (  # noqa: E402
    make_pit_params,
    noisy_residual,
    pit_field,
    zero_residual,
)

D = StrategyAction
ROOT = Path(__file__).resolve().parents[1]
SPECS = ((D.STAY_OUT, None), (D.PIT_NOW, None), (D.PIT_NEXT_LAP, None))
KEYS = ("STAY_OUT:SAMPLED", "PIT_NOW:SAMPLED", "PIT_NEXT_LAP:SAMPLED")
N = 40


def noisy_params():
    return make_pit_params(residual=noisy_residual(), stint_length=(1.0,),
                           stint_min=1.0, stint_max=6.0, pit_loss=20.0)


def cfg(*, n=N, seed=7):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=0, pit_dynamics_enabled=True)


def oc(index, finish, *, valid=True, status=None, reason=None):
    valid = valid and finish is not None
    if valid:
        return PerIndexOutcome(
            simulation_index=index, valid=True, winner_driver_id="w",
            finishing_order=("w",), target_finish_position=finish,
            target_won=finish == 1, target_podium=finish <= 3,
            intervention_status=status, intervention_reason=reason)
    return PerIndexOutcome(
        simulation_index=index, valid=False, winner_driver_id=None,
        finishing_order=(), target_finish_position=None, target_won=None,
        target_podium=None, intervention_status=status,
        intervention_reason=reason)


def make_comparison(*, specs=SPECS, n=N, seed=7):
    return compare_strategies(pit_field(3, scheduled=15), noisy_params(),
                              cfg(n=n, seed=seed), Assumptions(), "a",
                              candidate_specs=specs)


def inject(baseline_finishes, by_key, *, comp=None, specs=SPECS, n=N):
    comp = comp if comp is not None else make_comparison(specs=specs, n=n)
    base = tuple(oc(i, finish) for i, finish in enumerate(baseline_finishes))
    cands = []
    for candidate in comp.candidates:
        key = candidate.candidate.key
        if key in by_key:
            outs = tuple(oc(i, finish)
                         for i, finish in enumerate(by_key[key]))
            cands.append(dataclasses.replace(candidate,
                                             intervention_outcomes=outs))
        else:
            cands.append(candidate)
    return dataclasses.replace(comp, baseline_outcomes=base,
                               candidates=tuple(cands))


def constant(finish, n=N):
    return [finish] * n


# ---------------------------------------------------------------------------
# Objective contract.
# ---------------------------------------------------------------------------

def test_exactly_three_objectives_and_exact_metric_mapping():
    assert len(STRATEGY_OBJECTIVES) == 3
    assert set(STRATEGY_OBJECTIVES) == {
        "MAXIMIZE_WIN_PROBABILITY", "MAXIMIZE_PODIUM_PROBABILITY",
        "MINIMIZE_EXPECTED_FINISH"}
    assert OBJECTIVE_METRIC == {
        "MAXIMIZE_WIN_PROBABILITY": "WIN_PROBABILITY",
        "MAXIMIZE_PODIUM_PROBABILITY": "PODIUM_PROBABILITY",
        "MINIMIZE_EXPECTED_FINISH": "EXPECTED_FINISH"}
    for objective in STRATEGY_OBJECTIVES:
        assert objective_metric(objective) == OBJECTIVE_METRIC[objective]
        assert objective_metric(StrategyObjective(objective)) == \
            OBJECTIVE_METRIC[objective]
    assert objective_value("MAXIMIZE_WIN_PROBABILITY") == \
        "MAXIMIZE_WIN_PROBABILITY"


def test_unknown_objective_is_rejected():
    with pytest.raises(ValueError):
        objective_value("BEST_OVERALL")
    with pytest.raises(ValueError):
        objective_metric("best")


def test_evaluate_objective_has_no_default_objective():
    import inspect
    parameter = inspect.signature(evaluate_objective).parameters["objective"]
    assert parameter.default is inspect.Parameter.empty


def test_objective_result_is_single_metric_and_has_no_weighted_score():
    comp = inject(constant(5), {KEYS[1]: constant(4)})
    for objective in STRATEGY_OBJECTIVES:
        result = evaluate_objective(comp, objective)
        assert result.metric == OBJECTIVE_METRIC[objective]
        assert len(result.metric) > 0
        payload = result.to_dict()
        for banned in ("score", "utility", "weight", "combined"):
            assert banned not in payload


def test_objective_sampling_semantics_is_explicit():
    comp = inject(constant(5), {KEYS[1]: constant(4)})
    result = evaluate_objective(comp, "MAXIMIZE_WIN_PROBABILITY")
    assert result.sampling_semantics == OBJECTIVE_SAMPLING_SEMANTICS
    assert OBJECTIVE_VERSION == "v1"


# ---------------------------------------------------------------------------
# Baseline-relative classification.
# ---------------------------------------------------------------------------

def test_baseline_relative_improvement_degradation_inconclusive():
    comp = inject(
        constant(5),
        {KEYS[0]: constant(4),          # +1 finish -> improvement
         KEYS[1]: constant(6),          # -1 finish -> degradation
         KEYS[2]: constant(5)})         # 0 -> inconclusive
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    by_key = {e.candidate_key: e.classification
              for e in result.candidate_evaluations}
    assert by_key == {"STAY_OUT:SAMPLED": OBJECTIVE_IMPROVEMENT,
                      "PIT_NOW:SAMPLED": OBJECTIVE_DEGRADATION,
                      "PIT_NEXT_LAP:SAMPLED": OBJECTIVE_INCONCLUSIVE}
    counts = dict(result.baseline_relative_counts)
    assert counts[OBJECTIVE_IMPROVEMENT] == 1
    assert counts[OBJECTIVE_DEGRADATION] == 1
    assert counts[OBJECTIVE_INCONCLUSIVE] == 1
    assert result.baseline_reference_value == 0.0


def test_all_candidates_worse_than_baseline_is_a_valid_result():
    comp = inject(constant(5), {key: constant(6) for key in KEYS})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert all(e.classification == OBJECTIVE_DEGRADATION
               for e in result.candidate_evaluations)
    assert all(e.point_estimate < 0
               for e in result.candidate_evaluations)
    # A leader is still named by point estimate (the least negative), but no
    # intervention is forced to be preferred.
    assert result.leader_by_point_estimate in KEYS
    assert set(result.indistinguishable_from_leader) == set(KEYS) - {
        result.leader_by_point_estimate}


def test_all_candidates_inconclusive_is_a_valid_result():
    comp = inject(constant(5), {key: constant(5) for key in KEYS})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert all(e.classification == OBJECTIVE_INCONCLUSIVE
               for e in result.candidate_evaluations)
    counts = dict(result.baseline_relative_counts)
    assert counts[OBJECTIVE_INCONCLUSIVE] == 3
    assert counts[OBJECTIVE_IMPROVEMENT] == 0
    assert counts[OBJECTIVE_DEGRADATION] == 0


def test_insufficient_pairs_classify_uncertainty_unavailable():
    short = MIN_VALID_PAIRS_FOR_CI - 1
    comp = inject([5] * short,
                  {KEYS[0]: [4] * short, KEYS[1]: [4] * short,
                   KEYS[2]: [4] * short}, n=short)
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert all(e.classification == OBJECTIVE_UNAVAILABLE
               for e in result.candidate_evaluations)
    assert result.leader_by_point_estimate == "STAY_OUT:SAMPLED"
    assert set(result.indistinguishable_from_leader) == \
        {"PIT_NOW:SAMPLED", "PIT_NEXT_LAP:SAMPLED"}


# ---------------------------------------------------------------------------
# Direct candidate-vs-candidate.
# ---------------------------------------------------------------------------

def _candidate(comp, key):
    return next(c for c in comp.candidates if c.candidate.key == key)


def test_direct_pairwise_a_beats_b_loses_b_and_equals_b():
    from raceintel.strategy import pairwise_uncertainty
    comp = make_comparison()
    improved = inject(constant(5), {KEYS[0]: constant(4), KEYS[1]: constant(5)})
    lost = inject(constant(5), {KEYS[0]: constant(5), KEYS[1]: constant(4)})
    equal = inject(constant(5), {KEYS[0]: constant(5), KEYS[1]: constant(5)})
    a_key, b_key = KEYS[0], KEYS[1]
    win = pairwise_uncertainty(comp, _candidate(improved, a_key),
                               _candidate(improved, b_key),
                               "EXPECTED_FINISH")
    lose = pairwise_uncertainty(comp, _candidate(lost, a_key),
                                _candidate(lost, b_key), "EXPECTED_FINISH")
    tie = pairwise_uncertainty(comp, _candidate(equal, a_key),
                               _candidate(equal, b_key), "EXPECTED_FINISH")
    assert win.point_estimate == pytest.approx(1.0)
    assert lose.point_estimate == pytest.approx(-1.0)
    assert tie.point_estimate == pytest.approx(0.0)


def test_pairwise_classification_and_validity_counts_are_exact():
    comp = inject(constant(5), {KEYS[0]: constant(4), KEYS[1]: constant(5),
                                KEYS[2]: constant(5)})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    pair = next(p for p in result.pairwise_comparisons
                if p.candidate_a_key == KEYS[0]
                and p.candidate_b_key == KEYS[1])
    assert pair.classification == OBJECTIVE_IMPROVEMENT  # A improves over B
    assert (pair.both_valid, pair.a_only_valid, pair.b_only_valid,
            pair.both_invalid) == (N, 0, 0, 0)


def test_pairwise_validity_counts_do_not_require_baseline_validity():
    # Baseline is invalid where A is invalid, and B is invalid elsewhere; the
    # A-vs-B counts depend only on the two candidates, never on the baseline.
    base = [5] * N
    base[0] = None
    base[1] = None
    a_finishes = [4] * N
    a_finishes[0] = None
    a_finishes[1] = None
    b_finishes = [4] * N
    b_finishes[2] = None
    b_finishes[3] = None
    comp = inject(base, {KEYS[0]: a_finishes, KEYS[1]: b_finishes,
                         KEYS[2]: constant(5)})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    pair = next(p for p in result.pairwise_comparisons
                if p.candidate_a_key == KEYS[0]
                and p.candidate_b_key == KEYS[1])
    assert pair.both_valid == N - 4
    assert pair.a_only_valid == 2
    assert pair.b_only_valid == 2
    assert pair.both_invalid == 0


def test_direct_pairing_is_used_not_ci_overlap():
    # A and B share a common varying component with B exactly one position
    # behind A on every pair. Their baseline-relative intervals overlap (both
    # are noisy), yet A-vs-B is an exact constant +1 (A better). A CI-overlap
    # heuristic would call this inconclusive; direct pairing must not.
    common = list(range(1, 10)) * 5  # length 45
    a_finishes = list(common)
    b_finishes = [value + 1 for value in common]
    comp = inject([5] * len(common),
                  {KEYS[0]: a_finishes, KEYS[1]: b_finishes,
                   KEYS[2]: [5] * len(common)})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    evaluations = {e.candidate_key: e for e in result.candidate_evaluations}
    a_unc = evaluations[KEYS[0]].uncertainty
    b_unc = evaluations[KEYS[1]].uncertainty
    # Baseline-relative intervals overlap.
    assert a_unc.ci_low <= b_unc.ci_high and b_unc.ci_low <= a_unc.ci_high
    pair = next(p for p in result.pairwise_comparisons
                if p.candidate_a_key == KEYS[0]
                and p.candidate_b_key == KEYS[1])
    assert pair.classification == OBJECTIVE_IMPROVEMENT
    assert pair.point_estimate == pytest.approx(1.0)


def test_objectives_module_documents_no_ci_overlap_heuristic():
    # The prohibition is explicit in the module and the direct paired method is
    # what is implemented (the behavioural test above pins the actual policy).
    source = (ROOT / "raceintel" / "strategy" / "objectives.py").read_text().lower()
    assert "ci overlap" in source  # documented as deliberately not implemented
    assert "pairwise_uncertainty" in source  # direct paired method is used


# ---------------------------------------------------------------------------
# Ordering / leader.
# ---------------------------------------------------------------------------

def test_point_estimate_ordering_is_descending_and_tie_broken_canonically():
    comp = inject(constant(5), {KEYS[0]: constant(4),   # d = +1
                                KEYS[1]: constant(3),   # d = +2
                                KEYS[2]: constant(3)})  # d = +2
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert result.point_estimate_order == (
        "PIT_NOW:SAMPLED", "PIT_NEXT_LAP:SAMPLED", "STAY_OUT:SAMPLED")
    assert result.leader_by_point_estimate == "PIT_NOW:SAMPLED"
    # The exact-tie sibling is not distinguishable from the leader.
    assert "PIT_NEXT_LAP:SAMPLED" in result.indistinguishable_from_leader


def test_leader_ambiguity_when_pairwise_inconclusive():
    # A is the point-estimate leader (d = +1 constant). B has a lower point
    # estimate (+0.875) but its direct A-vs-B difference is noisy and centred
    # near zero, so the interval cannot distinguish it from the leader.
    b_finishes = [4] * 30 + [1] * 5 + [8] * 5
    comp = inject(constant(5), {KEYS[0]: constant(4),
                                KEYS[1]: b_finishes,
                                KEYS[2]: constant(5)})
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert result.leader_by_point_estimate == "STAY_OUT:SAMPLED"
    pair = next(p for p in result.pairwise_comparisons
                if p.candidate_a_key == "STAY_OUT:SAMPLED"
                and p.candidate_b_key == "PIT_NOW:SAMPLED")
    assert pair.classification == OBJECTIVE_INCONCLUSIVE
    assert "PIT_NOW:SAMPLED" in result.indistinguishable_from_leader


def test_candidate_may_remain_better_than_leader_only_by_estimate():
    comp = inject(constant(5), {KEYS[0]: constant(6),   # d = -1
                                KEYS[1]: constant(5),   # d = 0
                                KEYS[2]: constant(4)})  # d = +1
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert result.leader_by_point_estimate == "PIT_NEXT_LAP:SAMPLED"
    assert result.point_estimate_order[0] == "PIT_NEXT_LAP:SAMPLED"


# ---------------------------------------------------------------------------
# Objective mappings on real aggregate outcomes.
# ---------------------------------------------------------------------------

def test_three_objectives_evaluate_on_a_real_comparison():
    comp = make_comparison()
    for objective in STRATEGY_OBJECTIVES:
        result = evaluate_objective(comp, objective)
        assert result.comparison_supported is True
        assert result.metric == OBJECTIVE_METRIC[objective]
        assert len(result.candidate_evaluations) == 3
        assert len(result.pairwise_comparisons) == 3  # 3 choose 2


# ---------------------------------------------------------------------------
# Execution context retention.
# ---------------------------------------------------------------------------

def test_inert_execution_context_is_retained():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = make_pit_params(residual=zero_residual(), stint_length=(5.0,),
                             stint_min=5.0, stint_max=5.0, pit_loss=20.0)
    comp = compare_strategies(state, params, cfg(n=40), Assumptions(), "a",
                              candidate_specs=[(D.STAY_OUT, None)])
    result = evaluate_objective(comp, "MAXIMIZE_WIN_PROBABILITY")
    evaluation = result.candidate_evaluations[0]
    assert evaluation.execution is not None
    assert evaluation.execution.inert_rate == 1.0


def test_superseded_execution_context_is_retained():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = make_pit_params(residual=zero_residual(), stint_length=(2.0,),
                             stint_min=2.0, stint_max=2.0, pit_loss=20.0)
    comp = compare_strategies(state, params, cfg(n=40), Assumptions(), "a",
                              candidate_specs=[(D.PIT_NEXT_LAP, None)])
    result = evaluate_objective(comp, "MAXIMIZE_WIN_PROBABILITY")
    evaluation = result.candidate_evaluations[0]
    assert evaluation.execution.superseded_rate == 1.0


# ---------------------------------------------------------------------------
# Invariance / determinism / identity.
# ---------------------------------------------------------------------------

def test_objective_is_candidate_order_invariant():
    forward = make_comparison(specs=SPECS)
    reversed_specs = tuple(reversed(SPECS))
    backward = make_comparison(specs=reversed_specs)
    first = evaluate_objective(forward, "MINIMIZE_EXPECTED_FINISH")
    second = evaluate_objective(backward, "MINIMIZE_EXPECTED_FINISH")
    assert first.identity() == second.identity()
    assert first.point_estimate_order == second.point_estimate_order


def test_candidate_uncertainty_is_subset_consistent():
    full = make_comparison(specs=SPECS)
    solo = make_comparison(specs=[(D.PIT_NOW, None)])
    full_result = evaluate_objective(full, "MINIMIZE_EXPECTED_FINISH")
    solo_result = evaluate_objective(solo, "MINIMIZE_EXPECTED_FINISH")
    in_full = next(e for e in full_result.candidate_evaluations
                   if e.candidate_key == "PIT_NOW:SAMPLED")
    in_solo = solo_result.candidate_evaluations[0]
    assert in_full.uncertainty.identity() == in_solo.uncertainty.identity()


def test_pairwise_uncertainty_is_subset_consistent():
    full = make_comparison(specs=SPECS)
    pair = make_comparison(specs=[(D.STAY_OUT, None), (D.PIT_NOW, None)])
    full_result = evaluate_objective(full, "MINIMIZE_EXPECTED_FINISH")
    pair_result = evaluate_objective(pair, "MINIMIZE_EXPECTED_FINISH")
    full_pair = next(p for p in full_result.pairwise_comparisons
                     if p.candidate_a_key == "STAY_OUT:SAMPLED"
                     and p.candidate_b_key == "PIT_NOW:SAMPLED")
    solo_pair = pair_result.pairwise_comparisons[0]
    assert full_pair.uncertainty.identity() == solo_pair.uncertainty.identity()


def test_objective_is_deterministic_and_identity_sensitive():
    comp = make_comparison()
    first = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    second = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert first.identity() == second.identity()
    assert first.to_dict() == second.to_dict()
    assert first.identity() != \
        evaluate_objective(comp, "MAXIMIZE_WIN_PROBABILITY").identity()
    assert first.identity() != \
        evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH",
                           bootstrap_seed_root=999).identity()


def test_unsupported_comparison_yields_empty_objective_result():
    from raceintel.simulation.engine import REASON_MISSING_TYRE_AGE

    from test_v2_phase6_r6 import sim_driver, sim_state
    drivers = [sim_driver("a", lap=1, race_time=90.0, age=None),
               sim_driver("b", lap=1, race_time=95.0, age=1)]
    comp = compare_strategies(sim_state(drivers, scheduled=12),
                              noisy_params(), cfg(n=10), Assumptions(), "a")
    assert comp.unsupported_reason == REASON_MISSING_TYRE_AGE
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert result.comparison_supported is False
    assert result.candidate_evaluations == ()
    assert result.leader_by_point_estimate is None


# ---------------------------------------------------------------------------
# No rerun / compatibility / semantics.
# ---------------------------------------------------------------------------

def test_s5_analysis_never_reruns_simulation(monkeypatch):
    comp = make_comparison()

    def forbidden(*args, **kwargs):
        raise AssertionError("S5 must not rerun a simulation")

    monkeypatch.setattr(MonteCarloEngine, "run", forbidden)
    for objective in STRATEGY_OBJECTIVES:
        result = evaluate_objective(comp, objective)
        assert len(result.candidate_evaluations) == 3


def test_s5_point_estimate_reproduces_s4_delta_exactly():
    comp = make_comparison()
    for objective in STRATEGY_OBJECTIVES:
        metric = OBJECTIVE_METRIC[objective]
        result = evaluate_objective(comp, objective)
        by_key = {c.candidate.key: c for c in comp.candidates}
        for evaluation in result.candidate_evaluations:
            candidate = by_key[evaluation.candidate_key]
            if candidate.valid_pairs == 0:
                continue
            s4_delta = {
                "WIN_PROBABILITY": candidate.delta_win_probability,
                "PODIUM_PROBABILITY": candidate.delta_podium_probability,
                "EXPECTED_FINISH": candidate.delta_expected_finish}[metric]
            assert evaluation.point_estimate == s4_delta


def test_s4_comparison_retains_per_index_outcomes_for_s5():
    comp = make_comparison()
    assert len(comp.baseline_outcomes) == N
    for candidate in comp.candidates:
        assert len(candidate.intervention_outcomes) == N
    # The retention is internal: it never leaks into the S4 public payload.
    assert "baseline_outcomes" not in comp.to_dict()
    for candidate in comp.to_dict()["candidates"]:
        assert "intervention_outcomes" not in candidate


def test_probability_semantics_preserved_on_the_comparison():
    comp = make_comparison()
    result = evaluate_objective(comp, "MINIMIZE_EXPECTED_FINISH")
    assert comp.probability_semantics == PROBABILITY_SEMANTICS == \
        "MONTE_CARLO_FREQUENCY"
    assert "counterfactual" in comp.counterfactual_semantics
    assert result.sampling_semantics == OBJECTIVE_SAMPLING_SEMANTICS


def test_objectives_module_reads_no_future_oracle_or_phase3_material():
    banned = ("raceintel.simulation.validation", "raceintel.replay", "raceintel.prediction",
              "raceintel.model_lab", "pandas", "sklearn")
    tree = ast.parse((ROOT / "raceintel" / "strategy" / "objectives.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        assert not module.startswith(banned), f"objectives.py imports {module}"

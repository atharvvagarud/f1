"""Phase-7 S4: candidate generation + strategy comparison.

Covers the canonical candidate set and identity, static validity (including
near-race-end filtering, bad target, anchor mismatch, unsupported compound,
unsupported state), the same-compound policy, duplicate policy, canonical
ordering, the single-baseline comparison runner, exact baseline-reuse
equivalence with S3 ``run_pair``, complete-valid-pair deltas and their sign
convention, execution-status aggregation (STAY_OUT inertness, PIT_NEXT_LAP
supersession), determinism / order / subset invariance, immutability, temporal
safety, probability / counterfactual semantics and the absence of ranking,
objective, Phase-3 model dependency or production uncertainty.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import REASON_MISSING_TYRE_AGE, ExecutionPolicy
from raceintel.simulation.monte_carlo import MonteCarloEngine
from raceintel.simulation.results import PROBABILITY_SEMANTICS
from raceintel.strategy import (
    COMPARISON_VERSION,
    CRN_POLICY,
    DELTA_POLICY,
    StrategyAction,
    build_candidate,
    candidate_identity,
    compare_strategies,
    generate_candidates,
    run_baseline,
    run_intervention_arm,
    pair_arms,
    paired_differences,
    run_pair,
)
from raceintel.strategy.candidates import (
    CANDIDATE_INVALIDITY_REASONS,
    CANONICAL_CANDIDATE_SPECS,
)
from raceintel.strategy.comparison import CandidateComparison
from raceintel.strategy.paired import _pairing_diagnostics

from test_v2_phase6_r6 import (  # noqa: E402
    make_pit_params,
    noisy_residual,
    pit_field,
    sim_driver,
    sim_state,
    zero_residual,
)

D = StrategyAction
ROOT = Path(__file__).resolve().parents[1]

CANONICAL_KEYS = [
    "STAY_OUT:SAMPLED",
    "PIT_NOW:SAMPLED", "PIT_NOW:SOFT", "PIT_NOW:MEDIUM", "PIT_NOW:HARD",
    "PIT_NEXT_LAP:SAMPLED", "PIT_NEXT_LAP:SOFT", "PIT_NEXT_LAP:MEDIUM",
    "PIT_NEXT_LAP:HARD",
]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def sim_cfg(*, n=40, seed=2024, samples=0, pit=True) -> SimulationConfig:
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            sample_orders=samples, pit_dynamics_enabled=pit)


def noisy_params(*, stint=(3.0,), minimum=2.0, maximum=6.0, pit_loss=20.0):
    return make_pit_params(residual=noisy_residual(), stint_length=stint,
                           stint_min=minimum, stint_max=maximum,
                           pit_loss=pit_loss)


def one_driver_params(*, stint=2.0, pit_loss=20.0):
    return make_pit_params(residual=zero_residual(), stint_length=(stint,),
                           stint_min=stint, stint_max=stint, pit_loss=pit_loss)


def intervention(state, *, driver_id="a", action=D.PIT_NOW, compound=None):
    from raceintel.strategy import StrategyIntervention
    return StrategyIntervention(
        target_driver_id=driver_id, action=action,
        requested_compound=compound,
        decision_lap=state.driver_by_id[driver_id].lap_number,
        decision_state_identity=state.identity())


def keys(candidates):
    return [candidate.key for candidate in candidates]


# ---------------------------------------------------------------------------
# Canonical set / ordering / identity.
# ---------------------------------------------------------------------------

def test_canonical_candidate_set_and_order():
    state = pit_field(3, scheduled=15)
    assert len(CANONICAL_CANDIDATE_SPECS) == 9
    assert keys(generate_candidates(state, sim_cfg(), "a")) == CANONICAL_KEYS


def test_candidate_identity_is_stable_and_sensitive_to_content():
    assert candidate_identity(D.PIT_NOW, None) == \
        candidate_identity("PIT_NOW", None)
    assert candidate_identity(D.PIT_NOW, None) != \
        candidate_identity(D.PIT_NOW, "SOFT")
    assert candidate_identity(D.PIT_NOW, "SOFT") != \
        candidate_identity(D.PIT_NEXT_LAP, "SOFT")


def test_sampled_and_explicit_compound_candidates_are_distinct():
    state = pit_field(2, scheduled=12, compound="HARD")
    sampled = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, None)
    explicit = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, "HARD")
    assert sampled.valid and explicit.valid
    assert sampled.identity() != explicit.identity()
    assert sampled.key == "PIT_NOW:SAMPLED"
    assert explicit.key == "PIT_NOW:HARD"


def test_candidate_order_is_caller_order_invariant():
    state = pit_field(3, scheduled=15)
    specs = CANONICAL_CANDIDATE_SPECS
    forward = generate_candidates(state, sim_cfg(), "a", specs=specs)
    backward = generate_candidates(state, sim_cfg(), "a",
                                   specs=tuple(reversed(specs)))
    assert keys(forward) == keys(backward) == CANONICAL_KEYS


def test_duplicate_candidates_are_deterministically_deduplicated():
    state = pit_field(3, scheduled=15)
    specs = ((D.PIT_NOW, None), (D.PIT_NOW, None), (D.STAY_OUT, None))
    result = generate_candidates(state, sim_cfg(), "a", specs=specs)
    assert keys(result) == ["STAY_OUT:SAMPLED", "PIT_NOW:SAMPLED"]


# ---------------------------------------------------------------------------
# Static validity.
# ---------------------------------------------------------------------------

def test_all_default_candidates_are_statically_valid_on_a_supported_state():
    state = pit_field(3, scheduled=15)
    candidates = generate_candidates(state, sim_cfg(), "a")
    assert all(candidate.valid for candidate in candidates)
    assert all(candidate.intervention is not None for candidate in candidates)
    assert all(candidate.reason is None for candidate in candidates)


def test_near_race_end_filters_only_the_impossible_action():
    state = pit_field(2, scheduled=2, start_lap=1)
    by_key = {candidate.key: candidate
              for candidate in generate_candidates(state, sim_cfg(), "a")}
    assert by_key["STAY_OUT:SAMPLED"].valid
    assert by_key["PIT_NOW:SAMPLED"].valid
    assert by_key["PIT_NEXT_LAP:SAMPLED"].valid is False
    assert by_key["PIT_NEXT_LAP:SAMPLED"].reason == "decision_beyond_race"
    assert by_key["PIT_NEXT_LAP:SAMPLED"].intervention is not None


def test_bad_target_is_invalid_with_structured_reason():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "ghost", D.PIT_NOW, None)
    assert candidate.valid is False
    assert candidate.reason == "target_driver_not_in_roster"


def test_anchor_mismatch_is_rejected():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, None,
                                decision_state_identity="not-the-state")
    assert candidate.valid is False
    assert candidate.reason == "anchor_mismatch"


def test_unsupported_compound_is_rejected_without_constructing_one():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, "WET")
    assert candidate.valid is False
    assert candidate.reason == "unsupported_compound"
    assert candidate.intervention is None


def test_unsupported_action_is_rejected_without_constructing_one():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "a", "PIT_SOMETIME", None)
    assert candidate.valid is False
    assert candidate.reason == "unsupported_action"
    assert candidate.intervention is None


def test_stay_out_compound_is_malformed():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "a", D.STAY_OUT, "SOFT")
    assert candidate.valid is False
    assert candidate.reason == "malformed_intervention"


def test_decision_lap_mismatch_is_rejected():
    state = pit_field(2, scheduled=12)
    candidate = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, None,
                                decision_lap=99)
    assert candidate.valid is False
    assert candidate.reason == "decision_lap_mismatch"


def test_pit_dynamics_unavailable_makes_candidates_invalid():
    state = pit_field(2, scheduled=12)
    candidates = generate_candidates(state, sim_cfg(pit=False), "a")
    assert all(not candidate.valid for candidate in candidates)
    assert all(candidate.reason == "pit_dynamics_required"
               for candidate in candidates)


def test_every_candidate_reason_is_a_canonical_intervention_reason():
    state = pit_field(2, scheduled=2, start_lap=1)
    candidates = (
        build_candidate(state, sim_cfg(), "a", D.PIT_NEXT_LAP, None),
        build_candidate(state, sim_cfg(), "ghost", D.PIT_NOW, None),
        build_candidate(state, sim_cfg(), "a", D.PIT_NOW, "WET"),
        build_candidate(state, sim_cfg(), "a", D.PIT_NOW, None,
                        decision_state_identity="x"),
    )
    for candidate in candidates:
        assert candidate.reason in CANDIDATE_INVALIDITY_REASONS


# ---------------------------------------------------------------------------
# Same-compound policy.
# ---------------------------------------------------------------------------

def test_requesting_the_current_compound_is_scientifically_valid():
    # Phase-6 has no per-compound pace delta and no FIA compound rule; the
    # driver's current dry compound is a supported explicit identity, so it is
    # NOT removed merely because it is strategically unusual.
    for compound in ("SOFT", "MEDIUM", "HARD"):
        state = pit_field(2, scheduled=12, compound=compound)
        candidate = build_candidate(state, sim_cfg(), "a", D.PIT_NOW, compound)
        assert candidate.valid, compound


# ---------------------------------------------------------------------------
# Baseline execution / reuse.
# ---------------------------------------------------------------------------

def _counting_run(monkeypatch):
    calls = {"baseline": 0, "intervention": 0}
    original = MonteCarloEngine.run

    def wrapped(self, state, parameters, config, assumptions, *,
                intervention=None, **kwargs):
        if intervention is None:
            calls["baseline"] += 1
        else:
            calls["intervention"] += 1
        return original(self, state, parameters, config, assumptions,
                        intervention=intervention, **kwargs)

    monkeypatch.setattr(MonteCarloEngine, "run", wrapped)
    return calls


def test_comparison_executes_the_baseline_exactly_once(monkeypatch):
    state = pit_field(3, scheduled=15)
    calls = _counting_run(monkeypatch)
    result = compare_strategies(
        state, noisy_params(), sim_cfg(n=20), Assumptions(), "a",
        candidate_specs=[(D.STAY_OUT, None), (D.PIT_NOW, None),
                         (D.PIT_NEXT_LAP, "HARD")])
    evaluated = sum(1 for candidate in result.candidates if candidate.evaluated)
    assert calls["baseline"] == 1
    assert calls["intervention"] == evaluated == 3


def test_baseline_reuse_is_exactly_equivalent_to_s3_run_pair():
    state = pit_field(4, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=40, seed=77)
    baseline = run_baseline(state, params, cfg, Assumptions(), "a")
    for spec in CANONICAL_CANDIDATE_SPECS:
        candidate = build_candidate(state, cfg, "a", spec[0], spec[1])
        arm = run_intervention_arm(state, params, cfg, Assumptions(),
                                   candidate.intervention)
        shared = pair_arms(baseline, arm)
        reference = run_pair(state, params, cfg, Assumptions(),
                             candidate.intervention)
        assert shared.identity() == reference.identity()
        assert shared.baseline_result.identity() == \
            reference.baseline_result.identity()
        assert shared.intervention_result.identity() == \
            reference.intervention_result.identity()
        assert shared.baseline_outcomes == reference.baseline_outcomes
        assert shared.intervention_outcomes == reference.intervention_outcomes
        assert shared.diagnostics == reference.diagnostics


def test_shared_baseline_is_identical_for_every_candidate():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=30, seed=5)
    baseline = run_baseline(state, params, cfg, Assumptions(), "a")
    digests = set()
    for spec in CANONICAL_CANDIDATE_SPECS:
        candidate = build_candidate(state, cfg, "a", spec[0], spec[1])
        arm = run_intervention_arm(state, params, cfg, Assumptions(),
                                   candidate.intervention)
        paired = pair_arms(baseline, arm)
        assert paired.baseline_outcome_digest == baseline.outcome_digest
        assert paired.baseline_outcomes == baseline.outcomes
        digests.add(paired.baseline_result.identity())
    assert len(digests) == 1


# ---------------------------------------------------------------------------
# Aggregates, deltas, validity denominator.
# ---------------------------------------------------------------------------

def test_candidate_aggregate_and_complete_pair_delta_are_exact():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=50, seed=11)
    candidate = build_candidate(state, cfg, "a", D.PIT_NOW, "MEDIUM")
    baseline = run_baseline(state, params, cfg, Assumptions(), "a")
    arm = run_intervention_arm(state, params, cfg, Assumptions(),
                               candidate.intervention)
    paired = pair_arms(baseline, arm)
    comparison = CandidateComparison.from_pair(candidate, paired)
    summary = arm.result.driver_summary_by_id["a"]

    assert comparison.aggregate.win_probability == summary.win_probability
    assert comparison.aggregate.podium_probability == \
        summary.podium_probability
    assert comparison.aggregate.expected_finish == summary.expected_finish
    assert comparison.aggregate.valid_simulations == \
        arm.result.valid_simulation_count
    assert comparison.aggregate.invalid_simulations == \
        arm.result.invalid_simulation_count

    diffs = paired_differences(paired)
    assert comparison.delta_source == DELTA_POLICY == "complete_valid_pairs"
    assert comparison.delta_win_probability == diffs.mean_d_win
    assert comparison.delta_podium_probability == diffs.mean_d_podium
    assert comparison.delta_expected_finish == diffs.mean_d_finish
    assert comparison.valid_pairs == diffs.valid_pairs == \
        paired.diagnostics.pairs_both_valid


def test_delta_sign_convention_for_a_worsening_forced_pit():
    # Forcing 'a' to pit early adds a second stop: a's finish worsens (1 -> 2)
    # and it loses the win, so win delta is -1 and finish delta is -1.
    state = pit_field(2, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=8.0)
    result = compare_strategies(
        state, params, sim_cfg(n=5, seed=2024), Assumptions(), "a",
        candidate_specs=[(D.PIT_NOW, None)])
    comparison = result.candidates[0]
    assert comparison.delta_win_probability == -1.0
    assert comparison.delta_expected_finish == -1.0
    assert comparison.delta_podium_probability == 0.0


def test_delta_uses_only_complete_valid_pairs():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=30, seed=8)
    candidate = build_candidate(state, cfg, "a", D.PIT_NEXT_LAP, None)
    baseline = run_baseline(state, params, cfg, Assumptions(), "a")
    arm = run_intervention_arm(state, params, cfg, Assumptions(),
                               candidate.intervention)
    paired = pair_arms(baseline, arm)

    base = list(paired.baseline_outcomes)
    ivs = list(paired.intervention_outcomes)
    # Force one baseline-only-valid and one intervention-only-valid pair using
    # indices that were both valid.
    valid_pairs = [index for index, (b, iv) in enumerate(zip(base, ivs))
                   if b.valid and iv.valid]
    assert len(valid_pairs) >= 2
    first, second = valid_pairs[0], valid_pairs[1]
    base[first] = dataclasses.replace(
        base[first], valid=False, target_finish_position=None,
        target_won=None, target_podium=None, winner_driver_id=None,
        finishing_order=())
    ivs[second] = dataclasses.replace(
        ivs[second], valid=False, target_finish_position=None,
        target_won=None, target_podium=None, winner_driver_id=None,
        finishing_order=())
    diagnostics = _pairing_diagnostics(tuple(base), tuple(ivs))
    crafted = dataclasses.replace(paired, baseline_outcomes=tuple(base),
                                  intervention_outcomes=tuple(ivs),
                                  diagnostics=diagnostics)
    comparison = CandidateComparison.from_pair(candidate, crafted)

    assert comparison.validity_sets_match is False
    assert comparison.baseline_only_valid == diagnostics.baseline_only_valid
    assert comparison.intervention_only_valid == \
        diagnostics.intervention_only_valid
    assert comparison.valid_pairs == diagnostics.pairs_both_valid
    # Delta is the mean over COMPLETE valid pairs only, not the aggregate diff.
    diffs = paired_differences(crafted)
    assert comparison.delta_win_probability == diffs.mean_d_win


# ---------------------------------------------------------------------------
# Execution-status aggregation.
# ---------------------------------------------------------------------------

def test_stay_out_inertness_is_visible_and_not_a_noop_intervention():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    result = compare_strategies(
        state, params, sim_cfg(n=4), Assumptions(), "a",
        candidate_specs=[(D.STAY_OUT, None)])
    execution = result.candidates[0].execution
    assert execution.total == 4
    assert execution.suppressed == 4
    assert execution.inert == 4
    assert execution.baseline_pit_suppressed == 0
    assert execution.inert_rate == 1.0


def test_stay_out_suppressing_a_real_baseline_pit_is_reported():
    state = pit_field(2, scheduled=11, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    result = compare_strategies(
        state, params, sim_cfg(n=4), Assumptions(), "b",
        candidate_specs=[(D.STAY_OUT, None)])
    execution = result.candidates[0].execution
    assert execution.suppressed == 4
    assert execution.inert == 0
    assert execution.baseline_pit_suppressed == 4


def test_pit_next_lap_supersession_and_application_are_reported():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    result = compare_strategies(
        state, params, sim_cfg(n=6), Assumptions(), "a",
        candidate_specs=[(D.PIT_NEXT_LAP, None)])
    execution = result.candidates[0].execution
    assert execution.superseded == 6
    assert execution.applied == 0
    assert execution.superseded_rate == 1.0


def test_pit_now_execution_is_applied_and_documented():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    result = compare_strategies(
        state, params, sim_cfg(n=4), Assumptions(), "a",
        candidate_specs=[(D.PIT_NOW, None)])
    execution = result.candidates[0].execution
    assert execution.applied == 4
    assert execution.applied_rate == 1.0
    # PIT_NOW can coincide with a baseline-aligned pit; the contract discloses
    # this and the status counts remain descriptive only.
    assert any("coincide" in note for note in result.limitations)


# ---------------------------------------------------------------------------
# Unsupported state propagation.
# ---------------------------------------------------------------------------

def test_unsupported_factual_state_is_a_comparison_level_refusal():
    drivers = [sim_driver("a", lap=1, race_time=90.0, age=None),
               sim_driver("b", lap=1, race_time=95.0, age=1)]
    state = sim_state(drivers, scheduled=12)
    result = compare_strategies(state, one_driver_params(), sim_cfg(n=4),
                                Assumptions(), "a")
    assert result.supported is False
    assert result.unsupported_reason == REASON_MISSING_TYRE_AGE
    assert result.baseline is None
    assert all(not candidate.evaluated for candidate in result.candidates)


def test_target_outside_roster_is_a_comparison_level_refusal():
    state = pit_field(2, scheduled=12)
    result = compare_strategies(state, one_driver_params(), sim_cfg(n=4),
                                Assumptions(), "ghost")
    assert result.supported is False
    assert result.unsupported_reason == "target_driver_not_in_roster"
    assert all(not candidate.valid for candidate in result.candidates)
    assert all(candidate.reason == "target_driver_not_in_roster"
               for candidate in result.candidates)


# ---------------------------------------------------------------------------
# Identity / determinism / order / subset invariance.
# ---------------------------------------------------------------------------

def test_comparison_identity_is_stable_and_sensitive():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    specs = [(D.STAY_OUT, None), (D.PIT_NOW, "SOFT")]

    def once(cfg=sim_cfg(n=30, seed=2024), specs=specs, params=params,
             state=state):
        return compare_strategies(state, params, cfg, Assumptions(), "a",
                                  candidate_specs=specs).identity()

    base = once()
    assert base == once()
    assert base != once(cfg=sim_cfg(n=30, seed=7))
    assert base != once(cfg=sim_cfg(n=20, seed=2024))
    assert base != once(specs=[(D.STAY_OUT, None), (D.PIT_NOW, "HARD")])


def test_comparison_identity_is_candidate_order_invariant():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=20, seed=3)
    forward = [CANONICAL_CANDIDATE_SPECS[0], CANONICAL_CANDIDATE_SPECS[1],
               CANONICAL_CANDIDATE_SPECS[5]]
    backward = list(reversed(forward))
    first = compare_strategies(state, params, cfg, Assumptions(), "a",
                               candidate_specs=forward)
    second = compare_strategies(state, params, cfg, Assumptions(), "a",
                                candidate_specs=backward)
    assert first.identity() == second.identity()
    assert keys_compare(first) == keys_compare(second)


def keys_compare(result):
    return [candidate.candidate.key for candidate in result.candidates]


def test_subset_consistency():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=20, seed=9)
    specs = [CANONICAL_CANDIDATE_SPECS[0], CANONICAL_CANDIDATE_SPECS[1],
             CANONICAL_CANDIDATE_SPECS[6]]
    full = compare_strategies(state, params, cfg, Assumptions(), "a",
                              candidate_specs=specs)
    solo = compare_strategies(state, params, cfg, Assumptions(), "a",
                              candidate_specs=[CANONICAL_CANDIDATE_SPECS[1]])
    in_full = next(candidate for candidate in full.candidates
                   if candidate.candidate.key == "PIT_NOW:SAMPLED")
    in_solo = solo.candidates[0]
    assert in_full.to_dict() == in_solo.to_dict()


def test_candidate_execution_order_invariance():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=20, seed=13)
    baseline = run_baseline(state, params, cfg, Assumptions(), "a")
    candidates = [build_candidate(state, cfg, "a", action, compound)
                  for action, compound in CANONICAL_CANDIDATE_SPECS[:4]]

    def run(order):
        arms = {}
        for candidate in order:
            arm = run_intervention_arm(state, params, cfg, Assumptions(),
                                       candidate.intervention)
            arms[candidate.identity()] = pair_arms(baseline, arm)
        return arms

    forward = run(candidates)
    backward = run(list(reversed(candidates)))
    assert set(forward) == set(backward)
    for key in forward:
        assert forward[key].identity() == backward[key].identity()
        assert forward[key].intervention_outcomes == \
            backward[key].intervention_outcomes


def test_comparison_is_deterministic():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=20, seed=4)
    first = compare_strategies(state, params, cfg, Assumptions(), "a")
    second = compare_strategies(state, params, cfg, Assumptions(), "a")
    assert first.identity() == second.identity()
    assert first.to_dict() == second.to_dict()


# ---------------------------------------------------------------------------
# Immutability.
# ---------------------------------------------------------------------------

def test_comparison_does_not_mutate_inputs():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    cfg = sim_cfg(n=10, seed=4)
    assumptions = Assumptions()
    state_before = state.to_dict()
    param_identity = params.parameter_identity().identity()
    families_before = dict(params.families)
    config_before = cfg.to_dict()
    assumptions_before = assumptions.to_dict()
    compare_strategies(state, params, cfg, assumptions, "a",
                       candidate_specs=[(D.PIT_NOW, "SOFT")])
    assert state.to_dict() == state_before
    assert params.parameter_identity().identity() == param_identity
    assert params.families == families_before
    assert cfg.to_dict() == config_before
    assert assumptions.to_dict() == assumptions_before


# ---------------------------------------------------------------------------
# Semantics / firewall / no ranking / no production uncertainty.
# ---------------------------------------------------------------------------

def test_probability_semantics_is_monte_carlo_frequency_not_independent_binary():
    state = pit_field(3, scheduled=15)
    result = compare_strategies(
        state, noisy_params(), sim_cfg(n=10), Assumptions(), "a",
        candidate_specs=[(D.PIT_NOW, None)])
    assert result.probability_semantics == PROBABILITY_SEMANTICS == \
        "MONTE_CARLO_FREQUENCY"
    payload = result.to_dict()
    assert "INDEPENDENT_BINARY" not in str(payload)


def test_counterfactual_and_crn_metadata_are_carried():
    state = pit_field(3, scheduled=15)
    result = compare_strategies(
        state, noisy_params(), sim_cfg(n=10), Assumptions(), "a",
        candidate_specs=[(D.PIT_NOW, None)])
    assert result.pairing_policy == CRN_POLICY == \
        "CRN_ADOPTED_WITH_LIMITATIONS"
    assert "counterfactual" in result.counterfactual_semantics
    assert COMPARISON_VERSION == "v1"
    assert len(result.limitations) >= 1


def _all_keys(payload):
    keys = set()
    if isinstance(payload, dict):
        keys.update(payload)
        for value in payload.values():
            keys |= _all_keys(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            keys |= _all_keys(value)
    return keys


def test_result_exposes_no_ranking_objective_or_production_uncertainty():
    state = pit_field(3, scheduled=15)
    result = compare_strategies(
        state, noisy_params(), sim_cfg(n=10), Assumptions(), "a",
        candidate_specs=[(D.STAY_OUT, None), (D.PIT_NOW, None)])
    payload = result.to_dict()
    for banned in ("ranking", "objective", "recommended", "best", "winner"):
        assert banned not in payload
    keys_exposed = _all_keys(payload)
    for banned in ("ci", "confidence_interval", "bootstrap",
                   "paired_se", "paired_bootstrap_ci", "se", "std_error",
                   "standard_error", "significance"):
        assert banned not in keys_exposed
    # Canonical action order is preserved; it is not sorted by outcome.
    assert keys_compare(result) == ["STAY_OUT:SAMPLED", "PIT_NOW:SAMPLED"]


def test_strategy_modules_read_no_future_oracle_or_phase3_material():
    banned_prefixes = ("raceintel.simulation.validation", "raceintel.replay",
                       "raceintel.replay.replay_reconstruction", "raceintel.prediction",
                       "raceintel.model_lab", "pandas", "sklearn")
    for name in ("candidates.py", "comparison.py", "paired.py"):
        tree = ast.parse((ROOT / "raceintel" / "strategy" / name).read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for module in imported:
            assert not module.startswith(banned_prefixes), \
                f"{name} imports {module}"


def test_compare_strategies_accepts_only_scientific_inputs():
    import inspect
    parameters = set(inspect.signature(compare_strategies).parameters)
    assert parameters == {
        "state", "parameters", "config", "assumptions", "target_driver_id",
        "candidate_specs", "execution_policy", "zero_noise", "chunk_size"}


def test_candidate_generation_never_needs_the_future():
    # Generation is a pure function of T: repeating it on an unchanged state
    # yields identical identities, and it cannot express a future input.
    state = pit_field(3, scheduled=15)
    cfg = sim_cfg()
    first = generate_candidates(state, cfg, "a")
    second = generate_candidates(state, cfg, "a")
    assert [candidate.identity() for candidate in first] == \
        [candidate.identity() for candidate in second]


# ---------------------------------------------------------------------------
# Default-off Phase-6 compatibility.
# ---------------------------------------------------------------------------

def test_default_engine_path_stays_aggregate_only():
    state = pit_field(3, scheduled=15)
    engine = MonteCarloEngine()
    engine.run(state, noisy_params(), sim_cfg(n=10), Assumptions())
    assert engine.last_index_outcomes is None
    assert engine.last_intervention_outcome is None


def test_execution_policy_is_inherited():
    state = pit_field(3, scheduled=15)
    params = noisy_params()
    # The comparison forwards the execution policy unchanged; a leakage-free
    # backtest over future-estimated parameters is refused as a structured
    # comparison-level unsupported result, never silently accepted.
    result = compare_strategies(
        state, params, sim_cfg(n=10, seed=1), Assumptions(), "a",
        candidate_specs=[(D.PIT_NOW, None)],
        execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    assert result.supported is False
    assert result.unsupported_reason == "parameter_temporal_leak"

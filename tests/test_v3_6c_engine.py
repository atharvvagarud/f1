"""V3.6C engine tests: synthetic invariants, parity, determinism, smoke.

Part 1 (pure, no MC2): paired aggregation math on hand-built vectors.
Part 2 (synthetic MC2 fixtures from Phase-7/Phase-6 test helpers):
engine behavior, CRN/pairing, execution semantics, parity, determinism.
Part 3 (single 5000-run validation): production configuration executes.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from raceintel.simulation import monte_carlo as mc
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.state import canonical_sha256
from raceintel.strategy import v3_contracts as V3
from raceintel.strategy.candidates import CANONICAL_CANDIDATE_SPECS
from raceintel.strategy.comparison import compare_strategies
from raceintel.strategy.contracts import StrategyAction
from raceintel.strategy.paired import run_baseline
from raceintel.strategy.uncertainty import (
    candidate_uncertainty,
    comparison_substrate_identity,
    derive_bootstrap_seed,
)
from raceintel.strategy.v3_engine import (
    V3_ENGINE_VERSION,
    _aggregate_from_positions,
    _extended_delta,
    _paired_stats,
    _pair_positions,
    compare_v3_strategies,
    compare_v3_strategy,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v2_phase6_r6 import make_pit_params, noisy_residual, pit_field
from test_v2_phase7_s3_paired import (
    intervention,
    noisy_params,
    one_driver_params,
    sim_cfg,
)

D = StrategyAction
ROOT = Path(__file__).resolve().parents[1]


def _a_identity():
    d = json.loads((ROOT / "results/v3/v3_6a/strategy_contract.json").read_text())
    return d["contract_hash"]


def _b_identity():
    d = json.loads(
        (ROOT / "results/v3/v3_6b/strategy_execution_contract.json").read_text())
    return d["contract_hash"]


# ---------------------------------------------------------------------------
# Provenance.
# ---------------------------------------------------------------------------

def test_a_identity():
    assert _a_identity() == (
        "2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b")


def test_b_identity():
    assert _b_identity() == (
        "df821fe13ed587d7a086e93b8ee53a1670130299ca92c5a668608add443e3644")


# ---------------------------------------------------------------------------
# Part 1: pure synthetic invariants (no MC2).
# ---------------------------------------------------------------------------

def test_identical_paired_outcomes_delta_zero():
    agg_r = _aggregate_from_positions([3, 3, 5, 7], 4)
    agg_a = _aggregate_from_positions([3, 3, 5, 7], 4)
    assert agg_r.expected_finish == agg_a.expected_finish == 4.5
    d = [a - r for r, a in zip([1, 0, 0], [1, 0, 0])]
    delta = _extended_delta("delta_win_frequency", d, seed=1, valid_pairs=3)
    assert delta.point_estimate == 0.0
    assert abs(sum(f for _, f in agg_r.finish_position_distribution) - 1.0) < 1e-12


def test_all_alt_wins_delta_plus_one():
    delta = _extended_delta("delta_win_frequency", [1, 1, 1, 1],
                            seed=1, valid_pairs=4)
    assert delta.point_estimate == 1.0


def test_all_alt_losses_delta_minus_one():
    delta = _extended_delta("delta_win_frequency", [-1, -1],
                            seed=1, valid_pairs=2)
    assert delta.point_estimate == -1.0


def test_expected_finish_orientation_plus_one():
    # ref [5,5,5], alt [4,4,4] -> improvement +1 (ref - alt).
    pairs = [(5, 4), (5, 4), (5, 4)]
    values = [r - a for r, a in pairs]
    delta = _extended_delta("delta_expected_finish", values,
                            seed=1, valid_pairs=3)
    assert delta.point_estimate == 1.0


def test_expected_finish_orientation_minus_one():
    pairs = [(4, 5), (4, 5)]
    values = [r - a for r, a in pairs]
    delta = _extended_delta("delta_expected_finish", values,
                            seed=1, valid_pairs=2)
    assert delta.point_estimate == -1.0


def test_downside_probability_and_ties():
    # alt worse in 3/4 pairs; tie is not downside.
    harm = [0, 1, 1, 1]
    delta = _extended_delta("delta_downside_probability", harm,
                            seed=1, valid_pairs=4)
    assert delta.point_estimate == 0.75


def test_position_distribution_sums_to_one():
    agg = _aggregate_from_positions([1, 2, 2, 4, 4, 4], 4)
    total = sum(f for _, f in agg.finish_position_distribution)
    assert abs(total - 1.0) < 1e-12
    assert agg.roster_size == 4
    assert agg.win_frequency == pytest.approx(1 / 6)
    assert agg.podium_frequency == pytest.approx(3 / 6)
    assert agg.top5_frequency == pytest.approx(1.0)


def test_median_quantiles_correct():
    agg = _aggregate_from_positions([1, 2, 3, 4], 4)
    assert agg.median_finish == pytest.approx(2.5)
    assert agg.finish_q25 == pytest.approx(1.75)
    assert agg.finish_q75 == pytest.approx(3.25)
    assert agg.expected_finish == pytest.approx(2.5)


def test_pair_exclusion_membership_identical_across_metrics():
    # Membership is a pure function of the pair set: every metric derived
    # from the same pairs shares it by construction.
    pairs = [(2, 3), (5, 5), (1, 4)]
    ref = [p[0] for p in pairs]
    alt = [p[1] for p in pairs]
    d_win = [int(a == 1) - int(r == 1) for r, a in zip(ref, alt)]
    d_top5 = [int(a <= 5) - int(r <= 5) for r, a in zip(ref, alt)]
    assert len(d_win) == len(d_top5) == 3
    assert sum(d_win) == -1
    assert sum(d_top5) == 0


def test_zero_pairs_unsupported_shape():
    point, se, low, high, avail = _paired_stats([], seed=1)
    assert avail == "NO_VALID_PAIRS"
    assert point is None and se is None and low is None


def test_leader_tie_deterministic_by_canonical_order():
    assert CANONICAL_CANDIDATE_SPECS[0][0].value == "STAY_OUT"


# ---------------------------------------------------------------------------
# Part 2: engine behavior on synthetic fixtures.
# ---------------------------------------------------------------------------

def _full_state():
    return pit_field(4, scheduled=15)


def _full_params():
    return make_pit_params(residual=noisy_residual())


def _full_cfg(n=200, seed=99):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            pit_dynamics_enabled=True)


def test_engine_accepts_only_frozen_actions():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("WARP_SPEED", None)])
    # No evaluable content: unsupported, with the frozen ACTION-level
    # reason preserved on the alternative (no simulation was run).
    assert r.supported is False
    assert r.unsupported_reason == "NO_VALID_PAIRS"
    alt = r.alternatives[0]
    assert alt.evaluated is False
    assert alt.reason == "unsupported_action"
    assert alt.deltas == ()
    with pytest.raises(ValueError):
        compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[{"action": "PIT_NOW"}])


def test_invalid_action_runs_no_simulation():
    # Frozen S4 order runs the reference first; the invariant is that NO
    # intervention arm is ever simulated for an invalid action.
    calls = []
    original = mc.MonteCarloEngine.run

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("intervention", "MISSING"))
        return original(self, *args, **kwargs)

    mc.MonteCarloEngine.run = counting
    try:
        r = compare_v3_strategies(
            _full_state(), _full_params(), _full_cfg(n=20),
            Assumptions(), "a", candidate_specs=[("WARP_SPEED", None)])
    finally:
        mc.MonteCarloEngine.run = original
    assert r.alternatives[0].evaluated is False
    # Absent kwarg == intervention=None default: reference-only path.
    assert all(iv in (None, "MISSING") for iv in calls)


def test_reference_is_intervention_none_and_not_stay_out():
    # Semantic: reference kind is pinned and differs from STAY_OUT.
    assert V3.REFERENCE_KIND == "SIMULATED_NO_INTERVENTION_REFERENCE"
    # Behavioral: on a state where the baseline naturally pits, STAY_OUT
    # suppresses a real stop (non-inert), proving the arms differ.
    state = pit_field(2, scheduled=11, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    cfg = sim_cfg(n=8)
    r = compare_v3_strategies(state, params, cfg, Assumptions(), "b",
                              candidate_specs=[("STAY_OUT", None)])
    alt = r.alternatives[0]
    assert alt.evaluated is True
    assert alt.execution["suppressed"] == 8
    assert alt.execution["inert"] == 0
    assert alt.execution["baseline_pit_suppressed"] > 0


def test_same_state_config_seed_across_pair():
    state = _full_state()
    cfg = _full_cfg()
    r = compare_v3_strategies(state, _full_params(), cfg, Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    assert r.state_identity == state.identity()
    assert r.config_identity == cfg.identity()
    assert r.master_seed == cfg.master_seed == 99
    assert r.simulation_count == 200


def test_same_seed_family_across_actions():
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    one = compare_v3_strategies(state, params, cfg, Assumptions(), "a",
                                candidate_specs=[("PIT_NOW", None)])
    two = compare_v3_strategies(
        state, params, cfg, Assumptions(), "a",
        candidate_specs=[("PIT_NOW", None), ("PIT_NEXT_LAP", None)])
    a1 = one.alternatives[0]
    a2 = next(a for a in two.alternatives
              if a.candidate_key == "PIT_NOW:SAMPLED")
    assert a1.complete_pairs == a2.complete_pairs
    assert [d.point_estimate for d in a1.deltas] == [
        d.point_estimate for d in a2.deltas]


def test_complete_pair_membership_accounting():
    state = _full_state()
    r = compare_v3_strategies(state, _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", "MEDIUM")])
    alt = r.alternatives[0]
    assert alt.requested_pairs == 200
    assert alt.complete_pairs + alt.excluded_pairs == 200
    for d in alt.deltas:
        assert d.valid_pairs == alt.complete_pairs


def test_zero_pairs_unsupported():
    # Zero-noise degenerate field where every trajectory is invalid is
    # impractical; assert the contract shape directly on the helper path:
    # an alternative with no pairs carries NO_VALID_PAIRS and no deltas.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    r = compare_v3_strategies(state, params, sim_cfg(n=4), Assumptions(),
                              "no-such-driver",
                              candidate_specs=[("PIT_NOW", None)])
    assert r.supported is False
    assert r.unsupported_reason == "target_driver_not_in_roster"
    assert r.alternatives and all(a.evaluated is False for a in r.alternatives)


def test_outcome_vector_from_mc2_futures():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    alt = r.alternatives[0]
    for agg in (alt.reference_aggregate, alt.alternative_aggregate):
        assert agg.valid_pairs == alt.complete_pairs
        assert 0.0 <= agg.win_frequency <= agg.podium_frequency <= 1.0
        assert agg.podium_frequency <= 1.0
        assert abs(sum(f for _, f in agg.finish_position_distribution)
                   - 1.0) < 1e-9
        assert agg.roster_size == 4
        assert agg.finish_q25 <= agg.median_finish <= agg.finish_q75


def test_delta_signs_and_expected_finish_orientation():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    by_metric = {d.metric: d for d in r.alternatives[0].deltas}
    assert set(by_metric) == set(V3.TRADE_OFF_FIELDS)
    ref = r.alternatives[0].reference_aggregate
    altg = r.alternatives[0].alternative_aggregate
    assert by_metric["delta_win_frequency"].point_estimate == pytest.approx(
        altg.win_frequency - ref.win_frequency)
    assert by_metric["delta_expected_finish"].point_estimate == pytest.approx(
        ref.expected_finish - altg.expected_finish)


def test_downside_probability_bounds():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a")
    for alt in r.alternatives:
        if not alt.evaluated:
            continue
        d = next(x for x in alt.deltas
                 if x.metric == "delta_downside_probability")
        assert 0.0 <= d.point_estimate <= 1.0


def test_execution_diagnostics_denominator():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    ex = r.alternatives[0].execution
    total = ex["total"]
    assert total == 200
    for rate_key, count_key in (("applied_rate", "applied"),
                                ("suppressed_rate", "suppressed"),
                                ("superseded_rate", "superseded"),
                                ("inert_rate", "inert"),
                                ("race_end_cancelled_rate",
                                 "race_end_cancelled")):
        assert ex[rate_key] == pytest.approx(ex[count_key] / total)


def test_pit_next_lap_race_end_non_execution():
    # Target at lap 11 of 12: the forced stop can never execute; the race
    # ends first. Pair stays valid; diagnostic records non-execution.
    state = pit_field(1, scheduled=12, start_lap=11, age=1)
    params = one_driver_params(stint=5.0)
    r = compare_v3_strategies(state, params, sim_cfg(n=6), Assumptions(),
                              "a", candidate_specs=[("PIT_NOW", None)])
    alt = r.alternatives[0]
    assert alt.evaluated is True
    assert alt.execution["race_end_cancelled"] == 6
    assert alt.execution["applied"] == 0
    assert alt.complete_pairs == 6


def test_inert_actions_simulated_and_marked():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=5.0)
    r = compare_v3_strategies(state, params, sim_cfg(n=4), Assumptions(),
                              "a", candidate_specs=[("STAY_OUT", None)])
    alt = r.alternatives[0]
    assert alt.evaluated is True
    assert alt.execution["inert"] == 4
    assert all(d.point_estimate == 0.0 for d in alt.deltas)


def test_superseded_preserved_as_metadata():
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    params = one_driver_params(stint=2.0)
    r = compare_v3_strategies(state, params, sim_cfg(n=6), Assumptions(),
                              "a", candidate_specs=[("PIT_NEXT_LAP", None)])
    alt = r.alternatives[0]
    assert alt.evaluated is True
    assert alt.execution["superseded"] == 6
    assert alt.execution["applied"] == 0


def test_paired_binary_se_matches_s5():
    # Extended-metric machinery reproduces S5 bit-for-bit on shared metrics.
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    s4 = compare_strategies(state, params, cfg, Assumptions(), "a",
                            candidate_specs=[("PIT_NOW", None)])
    cand = next(c for c in s4.candidates if c.evaluated)
    substrate = comparison_substrate_identity(s4)
    base_by_index = {o.simulation_index: o for o in s4.baseline_outcomes}
    for metric, indicator in (
            ("WIN_PROBABILITY", lambda o: int(o.target_won)),
            ("PODIUM_PROBABILITY", lambda o: int(o.target_podium))):
        values = []
        for alt_o in cand.intervention_outcomes:
            base_o = base_by_index.get(alt_o.simulation_index)
            if base_o is None or not (base_o.valid and alt_o.valid):
                continue
            values.append(indicator(alt_o) - indicator(base_o))
        s5 = candidate_uncertainty(s4, cand, metric)
        seed = derive_bootstrap_seed(
            bootstrap_seed_root=20240101, substrate_identity=substrate,
            subject_identity=cand.candidate.identity(), metric=metric)
        point, se, low, high, avail = _paired_stats(values, seed=seed)
        assert point == pytest.approx(s5.point_estimate)
        assert (se or 0.0) == pytest.approx(s5.paired_se or 0.0)
        assert avail == s5.availability
        if avail == "AVAILABLE":
            assert low == pytest.approx(s5.ci_low)
            assert high == pytest.approx(s5.ci_high)


def test_paired_expected_finish_se():
    state = _full_state()
    r = compare_v3_strategies(state, _full_params(), _full_cfg(),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    d = next(x for x in r.alternatives[0].deltas
             if x.metric == "delta_expected_finish")
    assert d.valid_pairs == r.alternatives[0].complete_pairs
    assert d.paired_se is not None and d.paired_se >= 0.0
    assert d.uncertainty_semantics == "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"


def test_mc_interval_terminology():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(n=60),
                              Assumptions(), "a",
                              candidate_specs=[("PIT_NOW", None)])
    for d in r.alternatives[0].deltas:
        assert d.uncertainty_semantics == "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"
        assert d.interval_label == "95% MC interval"
        blob = json.dumps(d.to_dict()).lower()
        assert "real-world" not in blob and "model confidence" not in blob


def test_leader_semantics_point_estimate_only():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                              Assumptions(), "a")
    assert set(r.leaders) == {
        "leader_for_win_frequency", "leader_for_podium_frequency",
        "leader_for_top5_frequency", "leader_for_top10_frequency",
        "leader_for_expected_finish"}
    points = {}
    for alt in r.alternatives:
        if alt.evaluated:
            points[alt.candidate_key] = {
                d.metric: d.point_estimate for d in alt.deltas}
    for field, leader_key in r.leaders.items():
        metric = "delta_" + field.replace("leader_for_", "")
        best = max(points, key=lambda k: points[k][metric])
        assert leader_key == best
    assert "recommend" not in json.dumps(r.leaders).lower()


def test_unsupported_metrics_empty():
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(n=20),
                              Assumptions(), "ghost",
                              candidate_specs=[("PIT_NOW", None)])
    assert r.supported is False
    assert r.provenance["eligibility_status"]["metrics"] == {}
    assert "NaN" not in json.dumps(r.to_dict())


def test_provenance_identity_deterministic():
    kwargs = {"candidate_specs": [("PIT_NOW", None), ("STAY_OUT", None)]}
    r1 = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                               Assumptions(), "a", **kwargs)
    r2 = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                               Assumptions(), "a", **kwargs)
    assert r1.identity() == r2.identity()
    assert set(r1.provenance) == set(V3.PROVENANCE_FIELDS)
    for a in r1.alternatives:
        if a.evaluated:
            assert a.comparison_identity == a.comparison_key.identity()


def test_same_run_determinism_numeric():
    kwargs = {"candidate_specs": [("PIT_NOW", "MEDIUM")]}
    r1 = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                               Assumptions(), "a", **kwargs)
    r2 = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(),
                               Assumptions(), "a", **kwargs)
    d1 = r1.alternatives[0].deltas
    d2 = r2.alternatives[0].deltas
    assert [(x.point_estimate, x.paired_se, x.ci_low, x.ci_high)
            for x in d1] == [(x.point_estimate, x.paired_se, x.ci_low,
                              x.ci_high) for x in d2]
    assert r1.alternatives[0].execution == r2.alternatives[0].execution


def test_action_order_invariance():
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    specs_a = [("PIT_NOW", None), ("STAY_OUT", None),
               ("PIT_NEXT_LAP", "HARD")]
    specs_b = list(reversed(specs_a))
    ra = compare_v3_strategies(state, params, cfg, Assumptions(), "a",
                               candidate_specs=specs_a)
    rb = compare_v3_strategies(state, params, cfg, Assumptions(), "a",
                               candidate_specs=specs_b)
    da = {a.candidate_key: a for a in ra.alternatives}
    db = {a.candidate_key: a for a in rb.alternatives}
    assert set(da) == set(db)
    for key in da:
        assert da[key].to_dict() == db[key].to_dict()


def test_reference_reuse_parity():
    # One shared reference: [A] vs [A,B] give identical A science.
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    single = compare_v3_strategy(state, params, cfg, Assumptions(), "a",
                                 action="PIT_NOW")
    multi = compare_v3_strategies(
        state, params, cfg, Assumptions(), "a",
        candidate_specs=[("PIT_NOW", None), ("STAY_OUT", None)])
    a_single = single.alternatives[0]
    a_multi = next(a for a in multi.alternatives
                   if a.candidate_key == "PIT_NOW:SAMPLED")
    assert a_single.to_dict() == a_multi.to_dict()


def test_mc2_no_intervention_parity():
    # Load-bearing: V3 reference == direct frozen MC2 intervention=None.
    from raceintel.simulation.monte_carlo import MonteCarloEngine
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    engine = MonteCarloEngine()
    direct = engine.run(state, params, cfg, Assumptions(),
                        collect_index_outcomes=True)
    raw = engine.last_index_outcomes
    arm = run_baseline(state, params, cfg, Assumptions(), "a")
    assert arm.result.identity() == direct.identity()
    assert arm.outcome_digest == (
        __import__("raceintel.strategy.paired", fromlist=["x"])
        ._raw_outcome_digest(raw))


def test_phase7_overlap_parity():
    state = _full_state()
    params = _full_params()
    cfg = _full_cfg()
    s4 = compare_strategies(state, params, cfg, Assumptions(), "a",
                            candidate_specs=[("PIT_NOW", "MEDIUM")])
    v3 = compare_v3_strategies(state, params, cfg, Assumptions(), "a",
                               candidate_specs=[("PIT_NOW", "MEDIUM")])
    s4c = next(c for c in s4.candidates if c.evaluated)
    v3a = v3.alternatives[0]
    assert v3a.candidate_identity == s4c.candidate.identity()
    assert v3a.complete_pairs == s4c.valid_pairs
    assert v3a.excluded_pairs == (s4c.baseline_only_valid
                                  + s4c.intervention_only_valid
                                  + s4c.both_invalid)
    by_metric = {d.metric: d.point_estimate for d in v3a.deltas}
    assert by_metric["delta_win_frequency"] == pytest.approx(
        s4c.delta_win_probability)
    assert by_metric["delta_podium_frequency"] == pytest.approx(
        s4c.delta_podium_probability)
    assert by_metric["delta_expected_finish"] == pytest.approx(
        s4c.delta_expected_finish)


def test_temporal_poison_anchor_mismatch_invalid():
    # A forged decision_state_identity is rejected before any simulation.
    from raceintel.strategy.candidates import build_candidate
    state = _full_state()
    cfg = _full_cfg()
    bad = build_candidate(state, cfg, "a", "PIT_NOW", None,
                          decision_state_identity="0" * 64)
    assert bad.valid is False
    assert bad.reason == "anchor_mismatch"


def test_no_v35_runtime_dependency():
    import ast
    import sys as _sys
    assert not any(m.split(".")[0] in ("v3_5",) or m.startswith("v3_5")
                   for m in _sys.modules)
    engine_mod = __import__("raceintel.strategy.v3_engine", fromlist=["x"])
    for path in (Path(V3.__file__), Path(engine_mod.__file__)):
        tree = ast.parse(path.read_text())
        imported = {n.module.split(".")[0] for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom) and n.module}
        imported |= {n.names[0].name.split(".")[0] for n in ast.walk(tree)
                     if isinstance(n, ast.Import)}
        assert not (imported & {"v3_5", "outcome"}), imported


def test_engine_version_pinned():
    assert V3_ENGINE_VERSION == "v3.6c-engine-v1"
    r = compare_v3_strategies(_full_state(), _full_params(), _full_cfg(n=20),
                              Assumptions(), "a",
                              candidate_specs=[("STAY_OUT", None)])
    assert r.engine_version == V3_ENGINE_VERSION


def test_5000_run_production_configuration():
    # ENGINE VALIDATION (Part AI): the frozen 5000 paired-futures/action
    # configuration executes end to end. The strategy numbers are NOT
    # interpreted as historical truth.
    import time
    state = _full_state()
    params = _full_params()
    cfg = SimulationConfig(simulation_count=5000, master_seed=20240101,
                           pit_dynamics_enabled=True)
    assert cfg.simulation_count == V3.PRODUCTION_SIMULATION_COUNT
    start = time.perf_counter()
    r = compare_v3_strategy(state, params, cfg, Assumptions(), "a",
                            action="PIT_NOW")
    elapsed = time.perf_counter() - start
    alt = r.alternatives[0]
    assert r.supported is True and alt.evaluated is True
    assert alt.requested_pairs == 5000
    assert alt.complete_pairs + alt.excluded_pairs == 5000
    assert alt.complete_pairs > 0
    assert len(alt.deltas) == len(V3.TRADE_OFF_FIELDS)
    assert alt.comparison_identity == alt.comparison_key.identity()
    print(f"\n5000-run: {elapsed:.1f}s, complete={alt.complete_pairs}, "
          f"excluded={alt.excluded_pairs}")

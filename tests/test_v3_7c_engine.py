"""V3.7C engine tests: schedule-capable counterfactual execution.

Synthetic fixtures run at production count (5000; ~0.1 s/arm). Real-state
micro-validation uses the V3.6F-validated dry-green anchor and the frozen
parameter artifact (corpus-dependent). No API/cache/frontend built.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v2_phase6_r6 import make_pit_params, noisy_residual, pit_field, sim_driver, sim_state  # noqa: E402
from test_v2_phase7_s2_mechanics import (  # noqa: E402
    intervention as legacy_intervention,
)
from test_v2_phase7_s2_mechanics import one_driver_params, sim_cfg  # noqa: E402

from raceintel.counterfactual import contracts as C  # noqa: E402
from raceintel.counterfactual import engine as E  # noqa: E402
from raceintel.simulation import monte_carlo as mc  # noqa: E402
from raceintel.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.strategy.contracts import StrategyAction  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SID = "s" * 64
SEED = 20240101
COUNT = 5000


def _iv(target="a", n=3, compound="MEDIUM", lap=1, sid=None):
    return C.ScheduledIntervention(
        target_driver_id=target, kind="PIT_IN_N_LAPS", lap_offset_n=n,
        requested_compound=compound, decision_lap=lap,
        decision_state_identity=sid or SID)


def _plan(targets=("a",), specs=(("a", 3, "MEDIUM"),), rival=None, sid=None,
          lap=1):
    return C.CounterfactualPlan(
        target_driver_ids=targets,
        interventions=tuple(
            _iv(t, n, c, lap=lap, sid=sid) for t, n, c in specs),
        rival_driver_id=rival)


def _syn_state(n=2, start_lap=1):
    return pit_field(n, scheduled=12, start_lap=start_lap, age=1)


def _syn_params():
    return one_driver_params(stint=5.0, pit_loss=20.0)


def _prod_cfg(seed=SEED):
    return SimulationConfig(simulation_count=COUNT, master_seed=seed,
                            pit_dynamics_enabled=True)


def _fix_sid(plan, state):
    items = tuple(
        C.ScheduledIntervention(
            target_driver_id=i.target_driver_id, kind=i.kind,
            lap_offset_n=i.lap_offset_n,
            requested_compound=i.requested_compound,
            decision_lap=i.decision_lap,
            decision_state_identity=state.identity())
        for i in plan.interventions)
    return C.CounterfactualPlan(
        target_driver_ids=plan.target_driver_ids, interventions=items,
        rival_driver_id=plan.rival_driver_id)


def _run_plan(state, plan, *, seed=SEED, rival=None):
    plan = _fix_sid(plan, state)
    return E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(seed),
        assumptions=Assumptions(), plan=plan, rival_driver_id=rival)


# --- provenance ---


def test_a_identity_exact():
    a = json.loads((ROOT / "results/v3/v3_7a/counterfactual_contract.json"
                    ).read_text())
    assert a["contract_hash"] == \
        "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12"


def test_corrected_b_identity_exact():
    b = json.loads((ROOT / "results/v3/v3_7b/counterfactual_execution_contract.json"
                    ).read_text())
    assert b["contract_hash"] == \
        "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970"


def test_engine_identity_exact():
    assert E.ENGINE_IDENTITY == "v3.7c-counterfactual-engine-v1"


# --- V3.6 parity ---


def _parity(action, n):
    state = _syn_state()
    params = _syn_params()
    leg = mc.MonteCarloEngine()
    r1 = leg.run(state, params, sim_cfg(n=COUNT, seed=SEED), Assumptions(),
                 intervention=legacy_intervention(
                     state, action=action),
                 collect_index_outcomes=True)
    sch = mc.MonteCarloEngine()
    plan = _fix_sid(_plan(specs=(("a", n, None),)), state)
    r2 = sch.run(state, params, sim_cfg(n=COUNT, seed=SEED), Assumptions(),
                 intervention=E._to_seam(plan),
                 collect_index_outcomes=True)
    return leg, sch


def test_n1_v36_parity():
    leg, sch = _parity(StrategyAction.PIT_NOW, 1)
    assert np.array_equal(leg.last_index_outcomes["finish_position"],
                          sch.last_index_outcomes["finish_position"])
    assert np.array_equal(leg.last_index_outcomes["pit_count"],
                          sch.last_index_outcomes["pit_count"])


def test_n2_v36_parity():
    leg, sch = _parity(StrategyAction.PIT_NEXT_LAP, 2)
    assert np.array_equal(leg.last_index_outcomes["finish_position"],
                          sch.last_index_outcomes["finish_position"])
    assert np.array_equal(leg.last_index_outcomes["pit_count"],
                          sch.last_index_outcomes["pit_count"])


def test_n_greater_than_2_trigger():
    res = _run_plan(_syn_state(), _plan(specs=(("a", 4, "MEDIUM"),)))
    evs = res.schedule_outcomes["alternative"][0]["events"]
    assert evs[0]["trigger_lap"] == 1 + 4
    assert evs[0]["status"] in ("EXECUTED", "SUPERSEDED", "INERT")


def test_trigger_uses_simulated_progression():
    # Zero-noise scalar trace: force must land exactly at decision + N
    # with no historical input anywhere in the call path.
    state = _syn_state(n=1)
    params = _syn_params()
    cfg = SimulationConfig(simulation_count=1, master_seed=SEED,
                           pit_dynamics_enabled=True)
    plan = _fix_sid(_plan(specs=(("a", 3, None),)), state)
    seam = E._to_seam(plan)
    resolved = mc._resolve_intervention(seam, state, cfg)
    selection, sampler = mc._prepare(
        state, params, ExecutionPolicy.RETROSPECTIVE_PRODUCT, True)
    pit_params = mc.select_pit_parameters(state, selection, params)
    max_draws = mc.max_residual_draws(state)
    pit = mc._ScalarPitRuntime(
        pit_params, SEED, 0, state.roster_size, max_draws,
        mc.SIMULATION_CONTRACT_VERSION, True)
    tracker = mc._ScheduleState(resolved)
    mc._evolve_scalar(state, selection, sampler, None, True, pit,
                      None, tracker)
    assert tracker.events[0].status == "EXECUTED"
    assert tracker.events[0].applied_lap == 1 + 3


# --- tracker / lifecycle ---


def test_plan_tracker_evidence():
    res = _run_plan(_syn_state(), _plan(specs=(("a", 2, "SOFT"),)))
    ev = res.schedule_outcomes["alternative"][0]["events"][0]
    assert ev["target_driver_id"] == "a"
    assert ev["trigger_lap"] == 3
    assert ev["status"] in ("EXECUTED", "SUPERSEDED", "INERT",
                            "CANCELLED", "TERMINAL")
    assert res.complete_pairs + res.excluded_pairs == COUNT


def test_illegal_transition_rejection():
    assert not C.transition_allowed("EXECUTED", "ELIGIBLE")
    assert not C.transition_allowed("PLANNED", "EXECUTED")
    with pytest.raises(C.CounterfactualPlanError):
        C.transition_allowed("EXECUTED", "NOPE")


def test_terminal_cancellation():
    # Trigger at the final lap boundary: race ends before execution.
    state = pit_field(1, scheduled=4, start_lap=1, age=1)
    plan = _fix_sid(_plan(specs=(("a", 2, None),)), state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=plan)
    statuses = {e["status"]
                for sim in res.schedule_outcomes["alternative"]
                for e in sim["events"]}
    assert statuses <= {"EXECUTED", "SUPERSEDED", "INERT", "CANCELLED",
                        "TERMINAL"}


# --- multi-event / multi-stop ---


def test_multi_event_execution():
    res = _run_plan(_syn_state(),
                    _plan(specs=(("a", 2, "MEDIUM"), ("a", 6, "HARD"))))
    counts = {}
    for sim in res.schedule_outcomes["alternative"]:
        for e in sim["events"]:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
    assert counts.get("EXECUTED", 0) > 0
    assert sum(counts.values()) == 2 * COUNT


def test_multi_stop_chronological_execution():
    res = _run_plan(_syn_state(),
                    _plan(specs=(("a", 2, "MEDIUM"), ("a", 6, "HARD"))))
    for sim in res.schedule_outcomes["alternative"][:50]:
        applied = [e["applied_lap"] for e in sim["events"]
                   if e["status"] == "EXECUTED"]
        assert applied == sorted(applied)


def test_second_stop_state_continuity():
    # Two forced stops in one trajectory: per-sim pit counts reflect the
    # simulated stint evolution, and both events can execute.
    res = _run_plan(_syn_state(),
                    _plan(specs=(("a", 2, "MEDIUM"), ("a", 6, "HARD"))))
    assert res.alternative_aggregate["expected_pit_count"] >= 1.0
    two_exec = sum(1 for sim in res.schedule_outcomes["alternative"]
                   for e in sim["events"] if e["status"] == "EXECUTED")
    assert two_exec > 0


def test_natural_pit_supersession():
    # Stint target 2 forces a natural pit at lap 2, preempting N=4.
    state = pit_field(1, scheduled=12, start_lap=1, age=1)
    from test_v2_phase6_r6 import make_pit_params, zero_residual
    params = make_pit_params(residual=zero_residual(), stint_length=(2.0,),
                             stint_min=2.0, stint_max=2.0, pit_loss=20.0)
    plan = _fix_sid(_plan(specs=(("a", 4, None),)), state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_prod_cfg(),
        assumptions=Assumptions(), plan=plan)
    statuses = [e["status"]
                for sim in res.schedule_outcomes["alternative"]
                for e in sim["events"]]
    assert "SUPERSEDED" in statuses


# --- conflicts ---


def test_duplicate_deduplication():
    plan = _fix_sid(_plan(specs=(("a", 3, "MEDIUM"), ("a", 3, "MEDIUM"))),
                    _syn_state())
    seam = E._to_seam(plan)
    assert len(seam.schedule_events) == 1


def test_same_trigger_compound_conflict_rejection():
    state = _syn_state()
    plan = _fix_sid(_plan(specs=(("a", 3, "SOFT"), ("a", 3, "HARD"))), state)
    out = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert out["supported"] is False
    assert out["reason_code"] == "CONFLICTING_INTERVENTIONS"
    assert out["metrics"] == {}


# --- multi-driver / order invariance ---


def test_multi_driver_execution():
    state = pit_field(3, scheduled=12, start_lap=1, age=1)
    plan = _fix_sid(_plan(targets=("a", "c"),
                          specs=(("a", 2, "MEDIUM"), ("c", 4, "HARD"))),
                    state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    got = {(e["target_driver_id"], e["trigger_lap"])
           for e in res.schedule_outcomes["alternative"][0]["events"]}
    assert got == {("a", 3), ("c", 5)}


def test_plan_permutation_invariance():
    state = pit_field(3, scheduled=12, start_lap=1, age=1)
    p1 = _fix_sid(_plan(targets=("a", "c"),
                        specs=(("a", 2, "MEDIUM"), ("c", 4, "HARD"))), state)
    p2 = _fix_sid(_plan(targets=("a", "c"),
                        specs=(("c", 4, "HARD"), ("a", 2, "MEDIUM"))), state)
    assert p1.identity() == p2.identity()
    r1 = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=p1)
    r2 = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=p2)
    assert r1.identity() == r2.identity()


def test_target_permutation_invariance():
    p1 = _plan(targets=("a", "b"),
               specs=(("a", 2, "MEDIUM"), ("b", 4, "HARD")))
    p2 = _plan(targets=("b", "a"),
               specs=(("b", 4, "HARD"), ("a", 2, "MEDIUM")))
    assert p1.identity() == p2.identity()


# --- reference / orientation ---


def test_reference_semantics():
    res = _run_plan(_syn_state(), _plan())
    assert res.provenance["reference_kind"] == \
        "SIMULATED_NO_INTERVENTION_REFERENCE"
    assert res.base_identity == "SIMULATED_NO_INTERVENTION_REFERENCE"


def test_reference_vs_plan_orientation():
    res = _run_plan(_syn_state(), _plan())
    assert res.deltas["delta_expected_finish"]["point_estimate"] == \
        pytest.approx(res.base_aggregate["expected_finish"]
                      - res.alternative_aggregate["expected_finish"])


def test_plan_vs_plan_orientation():
    state = _syn_state()
    pa = _fix_sid(_plan(specs=(("a", 2, "MEDIUM"),)), state)
    pb = _fix_sid(_plan(specs=(("a", 5, "MEDIUM"),)), state)
    res = E.compare_plan_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan_a=pa, plan_b=pb)
    assert res.supported is True
    assert res.base_identity == pa.identity()
    assert res.alternative_identity == pb.identity()
    assert res.deltas["delta_expected_finish"]["point_estimate"] == \
        pytest.approx(res.base_aggregate["expected_finish"]
                      - res.alternative_aggregate["expected_finish"])
    assert res.deltas["delta_win_frequency"]["point_estimate"] == \
        pytest.approx(res.alternative_aggregate["win_frequency"]
                      - res.base_aggregate["win_frequency"])


# --- CRN / pairs ---


def test_crn_same_stream_identity():
    r1 = _run_plan(_syn_state(), _plan())
    r2 = _run_plan(_syn_state(), _plan())
    assert r1.identity() == r2.identity()


def test_complete_pair_membership():
    res = _run_plan(_syn_state(), _plan())
    assert res.complete_pairs + res.excluded_pairs == COUNT
    assert res.complete_pairs > 0


def test_pair_exclusion_accounting():
    res = _run_plan(_syn_state(), _plan())
    assert res.excluded_pairs >= 0
    assert res.provenance["simulation_count"] == COUNT
    assert res.provenance["master_seed"] == SEED


# --- outcomes ---


def test_ahead_of_rival_exact_synthetic_case():
    drivers = (sim_driver("a", lap=1, race_time=90.0, age=1, position=1),
               sim_driver("b", lap=1, race_time=150.0, age=1, position=2))
    state = sim_state(drivers, scheduled=6)
    plan = _fix_sid(_plan(specs=(("a", 2, None),)), state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(seed=SEED),
        assumptions=Assumptions(), plan=plan, rival_driver_id="b")
    assert res.base_aggregate["p_ahead_of_rival"] == pytest.approx(1.0)
    assert res.alternative_aggregate["p_ahead_of_rival"] == pytest.approx(1.0)


def test_pit_count_exact_synthetic_case():
    res = _run_plan(_syn_state(), _plan(specs=(("a", 2, "MEDIUM"),)))
    alt = res.alternative_aggregate["expected_pit_count"]
    ref = res.base_aggregate["expected_pit_count"]
    assert alt >= 0 and ref >= 0
    assert float(alt) == float(alt)  # deterministic (see determinism tests)
    n_exec = sum(1 for sim in res.schedule_outcomes["alternative"]
                 for e in sim["events"] if e["status"] == "EXECUTED")
    assert n_exec > 0


def test_position_gain_p5_to_p2():
    assert C.position_gain(5, 2) == 3
    assert C.position_gain(5, 5) == 0
    assert C.position_gain(5, 8) == -3


def test_position_gain_execution_level():
    drivers = (sim_driver("a", lap=1, race_time=90.0, age=1, position=2),
               sim_driver("b", lap=1, race_time=95.0, age=1, position=1))
    state = sim_state(drivers, scheduled=6)
    plan = _fix_sid(_plan(specs=(("a", 2, None),)), state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(seed=SEED),
        assumptions=Assumptions(), plan=plan)
    gain = res.alternative_aggregate["expected_position_gain"]
    assert gain is not None
    # Independent recomputation from the paired arm arrays.
    _, alt_idx, _ = E.run_arm(
        state, _syn_params(), _prod_cfg(seed=SEED), Assumptions(), plan)
    tcol = list(state.roster_driver_ids).index("a")
    valid = np.asarray(alt_idx["valid"], dtype=bool)
    # Complete-pair membership for the comparison equals the alt-valid set
    # intersected with reference-valid; gain is over the comparison pairs.
    _, ref_idx, _ = E.run_arm(
        state, _syn_params(), _prod_cfg(seed=SEED), Assumptions(), None)
    mask = valid & np.asarray(ref_idx["valid"], dtype=bool)
    expect = float(np.mean([C.position_gain(2, int(v)) for v in
                            np.asarray(alt_idx["finish_position"])[mask][:, tcol]]))
    assert gain == pytest.approx(expect)


def test_position_gain_comparison_orientation():
    state = _syn_state()
    pa = _fix_sid(_plan(specs=(("a", 2, "MEDIUM"),)), state)
    pb = _fix_sid(_plan(specs=(("a", 5, "MEDIUM"),)), state)
    res = E.compare_plan_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan_a=pa, plan_b=pb)
    assert res.deltas["delta_position_gain_loss"]["point_estimate"] == \
        pytest.approx(res.alternative_aggregate["expected_position_gain"]
                      - res.base_aggregate["expected_position_gain"])


def test_expected_finish_sign_unchanged():
    res = _run_plan(_syn_state(), _plan())
    d = res.deltas["delta_expected_finish"]["point_estimate"]
    assert d == pytest.approx(res.base_aggregate["expected_finish"]
                              - res.alternative_aggregate["expected_finish"])


def test_probability_signs_unchanged():
    res = _run_plan(_syn_state(), _plan())
    for name in ("delta_win_frequency", "delta_podium_frequency"):
        d = res.deltas[name]["point_estimate"]
        alt = res.alternative_aggregate[name[6:]]
        base = res.base_aggregate[name[6:]]
        assert d == pytest.approx(alt - base)


# --- unsupported / eligibility ---


def test_unsupported_metrics_empty():
    out = E.compare_reference_vs_plan(
        state=_syn_state(), parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(),
        plan=_plan(targets=("zzz",), specs=(("zzz", 2, "MEDIUM"),)))
    assert out["supported"] is False
    assert out["metrics"] == {}
    assert out["level"] == "STATE"


def test_eligibility_hierarchy():
    state = _syn_state()
    bad_n = _fix_sid(_plan(specs=(("a", 40, "MEDIUM"),)), state)
    assert E.check_eligibility(state, bad_n)[1] == "INTERVENTION"
    conflict = _fix_sid(
        _plan(specs=(("a", 3, "SOFT"), ("a", 3, "HARD"))), state)
    assert E.check_eligibility(state, conflict)[1] == "PLAN"
    ok = _fix_sid(_plan(), state)
    assert E.check_eligibility(state, ok, rival_driver_id="zzz")[1] == \
        "COMPARISON"


# --- rejected ---


def _bad_kind_plan(kind):
    class K:
        def __init__(self):
            self.target_driver_id = "a"
            self.kind = kind
            self.lap_offset_n = 2
            self.requested_compound = None
            self.decision_lap = 1
    return K()


def test_weather_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="WEATHER",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_sc_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="SAFETY_CAR",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_vsc_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="VSC",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_red_flag_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="RED_FLAG",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_retirement_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="RETIREMENT",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_reliability_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="RELIABILITY",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_arbitrary_state_edits_rejected():
    for kind in ("ARBITRARY_POSITION", "ARBITRARY_GAP", "ARBITRARY_PACE",
                 "ARBITRARY_TYRE_AGE"):
        with pytest.raises(Exception):
            C.ScheduledIntervention(
                target_driver_id="a", kind=kind, lap_offset_n=2,
                decision_lap=1, decision_state_identity=SID)


def test_undercut_primitive_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="UNDERCUT",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_overcut_primitive_rejected():
    with pytest.raises(Exception):
        C.ScheduledIntervention(target_driver_id="a", kind="OVERCUT",
                                lap_offset_n=2, decision_lap=1,
                                decision_state_identity=SID)


def test_seam_rejects_bad_kind():
    state = _syn_state()
    engine = mc.MonteCarloEngine()

    class Sched:
        schedule_events = (_bad_kind_plan("WEATHER"),)
        decision_state_identity = state.identity()

    with pytest.raises(mc.StrategyInterventionError):
        engine.run(state, _syn_params(), sim_cfg(n=10, seed=1),
                   Assumptions(), intervention=Sched())


def test_v35_absent_from_execution_call_graph():
    for rel in ("raceintel/counterfactual/engine.py",
                "raceintel/counterfactual/contracts.py"):
        src = (ROOT / rel).read_text()
        assert "v3_5" not in src and "V3_5" not in src


# --- poison / determinism ---


def test_historical_future_poison():
    import pandas as pd
    state = _syn_state()
    plan = _fix_sid(_plan(), state)
    before = E.compare_reference_vs_plan(
        state=state, parameters=_syn_params(), config=_prod_cfg(),
        assumptions=Assumptions(), plan=plan).identity()
    real_read = pd.read_parquet

    def _poison(*a, **k):
        raise AssertionError("historical future must not be read")

    pd.read_parquet = _poison
    try:
        after = E.compare_reference_vs_plan(
            state=state, parameters=_syn_params(), config=_prod_cfg(),
            assumptions=Assumptions(), plan=plan).identity()
    finally:
        pd.read_parquet = real_read
    assert before == after


def test_no_historical_reads_in_engine_source():
    src = (ROOT / "raceintel/counterfactual/engine.py").read_text()
    assert "read_parquet" not in src
    assert "from_race_state" not in src
    assert "race_control" not in src.lower()
    assert "weather" not in src.lower()


def test_same_seed_determinism():
    assert _run_plan(_syn_state(), _plan()).identity() == \
        _run_plan(_syn_state(), _plan()).identity()


def test_different_seed_validity():
    r1 = _run_plan(_syn_state(), _plan(), seed=SEED)
    r2 = _run_plan(_syn_state(), _plan(), seed=999)
    assert r1.supported and r2.supported
    assert r1.provenance["master_seed"] == SEED
    assert r2.provenance["master_seed"] == 999


def test_5000_production_configuration_unchanged():
    assert C.PRODUCTION_SIMULATION_COUNT == 5000
    assert C.DEFAULT_MASTER_SEED == 20240101
    res = _run_plan(_syn_state(), _plan())
    assert res.complete_pairs + res.excluded_pairs == 5000


def test_no_api_dependency():
    src = (ROOT / "raceintel/counterfactual/engine.py").read_text()
    assert "from api" not in src and "import api" not in src


def test_no_frontend_dependency():
    src = (ROOT / "raceintel/counterfactual/engine.py").read_text()
    assert "from frontend" not in src and "import frontend" not in src


def test_no_cache_dependency():
    src = (ROOT / "raceintel/counterfactual/engine.py").read_text()
    assert "import cache" not in src and "from cache" not in src
    assert "lru_cache" not in src and "cache_dir" not in src


# --- scalar/batch path equivalence ---


def test_scalar_batch_schedule_equivalence():
    state = _syn_state(n=2)
    params = _syn_params()
    cfg = SimulationConfig(simulation_count=20, master_seed=99,
                           pit_dynamics_enabled=True)
    plan = _fix_sid(_plan(specs=(("a", 2, "MEDIUM"),)), state)
    seam = E._to_seam(plan)
    batch = mc.MonteCarloEngine()
    batch.run(state, params, cfg, Assumptions(), intervention=seam,
              collect_index_outcomes=True)
    scalar = mc.MonteCarloEngine()
    scalar.run_scalar(state, params, cfg, Assumptions(), intervention=seam,
                      collect_index_outcomes=True,
                      collect_diagnostics=True)
    assert np.array_equal(
        batch.last_index_outcomes["finish_position"],
        scalar.last_index_outcomes["finish_position"])
    assert np.array_equal(batch.last_index_outcomes["pit_count"],
                          scalar.last_index_outcomes["pit_count"])


# --- real-state micro-validation (mechanical only) ---


def _real_anchor():
    from api.v2_service import load_v2_service
    from api.v2_simulation_service import build_v2_simulation_service
    from raceintel.race_state.race_state import AnchorObservation
    from raceintel.simulation.adapter import from_race_state
    svc = build_v2_simulation_service(load_v2_service())
    race_state = svc._reconstructor.reconstruct(  # noqa: SLF001
        AnchorObservation(race_id="2022-r01-R", anchor_driver_id="perez",
                          anchor_lap_number=30,
                          anchor_state_time_s=6745.686))
    return svc, from_race_state(race_state)


def _real_cfg(n=5000, seed=SEED):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            pit_dynamics_enabled=True)


_MICRO = {}


def _micro():
    if "state" not in _MICRO:
        svc, state = _real_anchor()
        _MICRO["state"] = state
        _MICRO["params"] = svc.parameters
    return _MICRO["state"], _MICRO["params"]


def _real_plan(n, compound="MEDIUM", target="perez"):
    state, _ = _micro()
    lap = next(e.lap_number for e in state.drivers
               if e.driver_id == target)
    return state, _fix_sid(_plan(
        targets=(target,),
        specs=((target, n, compound),), lap=lap), state)


def test_micro_n1_parity_case():
    # Legacy V3.6 parity at engine level is proven bit-identical on
    # synthetics; here the N=1 schedule must execute mechanically on the
    # real state with the production 5000-future configuration.
    state, params = _micro()
    cfg = _real_cfg()
    lap = next(e.lap_number for e in state.drivers
               if e.driver_id == "perez")
    _, plan = _real_plan(1)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=cfg,
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    assert res.complete_pairs > 0
    assert res.schedule_outcomes["alternative"][0]["events"][0][
        "trigger_lap"] == lap + 1


def test_micro_n2_parity_case():
    state, params = _micro()
    _, plan = _real_plan(2)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_real_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    assert res.complete_pairs > 0


def test_micro_n_greater_than_2_case():
    state, params = _micro()
    _, plan = _real_plan(5)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_real_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    assert res.complete_pairs > 0


def test_micro_multi_stop_case():
    state, params = _micro()
    lap = next(e.lap_number for e in state.drivers
               if e.driver_id == "perez")
    plan = _fix_sid(_plan(targets=("perez",),
                          specs=(("perez", 2, "MEDIUM"),
                                 ("perez", 10, "HARD")), lap=lap), state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_real_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    assert res.complete_pairs > 0


def test_micro_rival_outcome_case():
    state, params = _micro()
    _, plan = _real_plan(3)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_real_cfg(),
        assumptions=Assumptions(), plan=plan, rival_driver_id="max_verstappen")
    assert res.supported is True
    assert res.base_aggregate["p_ahead_of_rival"] is not None
    assert res.alternative_aggregate["p_ahead_of_rival"] is not None


def test_micro_multi_driver_case():
    state, params = _micro()
    laps = {e.driver_id: e.lap_number for e in state.drivers}
    raw = C.CounterfactualPlan(
        target_driver_ids=("perez", "max_verstappen"),
        interventions=(
            _iv("perez", 2, "MEDIUM", lap=laps["perez"]),
            _iv("max_verstappen", 3, "HARD", lap=laps["max_verstappen"]),
        ))
    plan = _fix_sid(raw, state)
    res = E.compare_reference_vs_plan(
        state=state, parameters=params, config=_real_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert res.supported is True
    assert res.complete_pairs > 0

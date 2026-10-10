"""V3.6D Phase 3: Layer-2 fidelity + stability experiments (preregistered).

- layer2: first 8 eligible (canonical order) x 5000 sims x 9 actions.
- seeds: first 6 eligible x {20240101, 12345, 99991} x 200 sims (Layer-1
  count; protocol underspecification resolved toward the frozen count).
- counts: first 6 eligible x {200, 1000, 5000} x seed 20240101.
- crn: first 6 eligible, PIT_NOW:SAMPLED — paired CRN vs independent-seed
  helper (different master seeds per arm, unpaired SE; evaluation only).
- repro: first 4 eligible x 200 sims, run twice, exact-identity required.

Output: results/v3/v3_6d/layer2.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.v2_service import load_v2_service
from api.v2_strategy_service import load_production_parameters
from raceintel.race_state import race_state as RS
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.presence import prepare_initial_state
from raceintel.strategy.candidates import build_candidate
from raceintel.strategy.paired import run_baseline, run_intervention_arm
from raceintel.strategy.v3_engine import compare_v3_strategies

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "results" / "v3" / "v3_6d" / "sample.json"
OUT = ROOT / "results" / "v3" / "v3_6d" / "layer2.json"
SEEDS = [20240101, 12345, 99991]
COUNTS = [200, 1000, 5000]


def _load_state(svc, params, entry):
    a = entry["anchor"]
    anchor = RS.AnchorObservation(
        race_id=entry["race_id"], anchor_driver_id=a["driver_id"],
        anchor_lap_number=a["lap_number"],
        anchor_state_time_s=a["state_time_s"])
    race_state = svc._reconstructor.reconstruct(anchor)
    grid = svc.grid_slots(entry["race_id"])
    relief = prepare_initial_state(
        race_state, grid_by_driver=grid, parameters=params,
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert relief.eligible and relief.state is not None
    return relief.state


def _run(state, params, target, *, n, seed, specs=None):
    cfg = SimulationConfig(simulation_count=n, master_seed=seed,
                           pit_dynamics_enabled=True)
    started = time.perf_counter()
    result = compare_v3_strategies(
        state, params, cfg, Assumptions(), target, candidate_specs=specs)
    return result, time.perf_counter() - started


def _slim(result):
    return result.to_dict()


def main() -> None:
    t0 = time.perf_counter()
    sample = json.loads(SAMPLE.read_text())
    eligible = sorted(
        [s for s in sample["states"] if s["eligible"]],
        key=lambda s: (s["race_id"], s["anchor"]["state_time_s"]))
    svc = load_v2_service()
    params = load_production_parameters()
    out = {"seeds": SEEDS, "counts": COUNTS}

    l2_states = eligible[:8]
    layer2 = []
    for entry in l2_states:
        state = _load_state(svc, params, entry)
        result, el = _run(state, params, entry["target_driver_id"],
                          n=5000, seed=20240101)
        layer2.append({"race_id": entry["race_id"], "anchor": entry["anchor"],
                       "target": entry["target_driver_id"],
                       "stage": entry["stage"], "runtime_s": round(el, 1),
                       "result": _slim(result)})
        print(f"L2 {entry['race_id']} done {el:.0f}s", flush=True)
    out["layer2"] = layer2

    six = eligible[:6]
    seeds_exp = []
    for entry in six:
        state = _load_state(svc, params, entry)
        runs = []
        for seed in SEEDS:
            result, _ = _run(state, params, entry["target_driver_id"],
                             n=200, seed=seed,
                             specs=[("PIT_NOW", None), ("STAY_OUT", None)])
            runs.append({"seed": seed, "result": _slim(result)})
        seeds_exp.append({"race_id": entry["race_id"], "anchor": entry["anchor"],
                          "target": entry["target_driver_id"], "runs": runs})
        print(f"seeds {entry['race_id']} done", flush=True)
    out["seeds_experiment"] = seeds_exp

    counts_exp = []
    for entry in six:
        state = _load_state(svc, params, entry)
        runs = []
        for n in COUNTS:
            result, _ = _run(state, params, entry["target_driver_id"],
                             n=n, seed=20240101,
                             specs=[("PIT_NOW", None), ("STAY_OUT", None)])
            runs.append({"n": n, "result": _slim(result)})
        counts_exp.append({"race_id": entry["race_id"], "anchor": entry["anchor"],
                           "target": entry["target_driver_id"], "runs": runs})
        print(f"counts {entry['race_id']} done", flush=True)
    out["counts_experiment"] = counts_exp

    crn_exp = []
    for entry in six:
        state = _load_state(svc, params, entry)
        target = entry["target_driver_id"]
        cfg = SimulationConfig(simulation_count=500, master_seed=20240101,
                               pit_dynamics_enabled=True)
        cand = build_candidate(state, cfg, target, "PIT_NOW", None)
        assert cand.valid
        base = run_baseline(state, params, cfg, Assumptions(), target)
        arm_same = run_intervention_arm(
            state, params, cfg, Assumptions(), cand.intervention)
        cfg_alt = SimulationConfig(simulation_count=500, master_seed=777001,
                                   pit_dynamics_enabled=True)
        arm_diff = run_intervention_arm(
            state, params, cfg_alt, Assumptions(), cand.intervention)
        import numpy as np

        def series(arm_outcomes, fn):
            base_by = {o.simulation_index: o for o in base.outcomes}
            return [fn(a) - fn(base_by[a.simulation_index])
                    for a in arm_outcomes
                    if a.valid and base_by[a.simulation_index].valid]

        def unpaired(arm_result, fn_name):
            b = [float(getattr(o, fn_name)) for o in base.outcomes if o.valid]
            c = [float(getattr(o, fn_name)) for o in arm_result if o.valid]
            vb = float(np.var(b, ddof=1)) / len(b)
            vc = float(np.var(c, ddof=1)) / len(c)
            return (vb + vc) ** 0.5

        paired_win = series(arm_same.outcomes, lambda o: int(o.target_won))
        n = len(paired_win)
        paired_se = float(np.std(paired_win, ddof=1) / (n ** 0.5))
        indep_se = unpaired(
            arm_diff.outcomes, "target_won") if n else None
        crn_exp.append({
            "race_id": entry["race_id"], "anchor": entry["anchor"],
            "target": target, "pairs": n, "paired_se_win": paired_se,
            "independent_se_win": indep_se,
            "width_ratio": (1.96 * indep_se * 2) / (1.96 * paired_se * 2)
            if paired_se else None})
        print(f"crn {entry['race_id']} done", flush=True)
    out["crn_experiment"] = crn_exp

    repro = []
    for entry in eligible[:4]:
        state = _load_state(svc, params, entry)
        r1, _ = _run(state, params, entry["target_driver_id"],
                     n=200, seed=20240101)
        r2, _ = _run(state, params, entry["target_driver_id"],
                     n=200, seed=20240101)
        repro.append({"race_id": entry["race_id"], "anchor": entry["anchor"],
                      "identical": r1.identity() == r2.identity(),
                      "identity": r1.identity()})
    out["reproducibility"] = repro
    out["runtime_s"] = round(time.perf_counter() - t0, 1)
    OUT.write_text(json.dumps(out))
    print(f"layer2 done runtime={out['runtime_s']}s -> {OUT}")


if __name__ == "__main__":
    main()

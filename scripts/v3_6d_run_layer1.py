"""V3.6D Phase 2: Layer-1 broad evaluation (200 paired sims, frozen seed).

Runs the frozen V3 engine on every eligible sampled state (1 target each,
all 9 actions). Stores compact comparison payloads only (no per-index
trajectories). Output: results/v3/v3_6d/layer1.json.
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
from raceintel.strategy.v3_engine import compare_v3_strategies

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "results" / "v3" / "v3_6d" / "sample.json"
OUT = ROOT / "results" / "v3" / "v3_6d" / "layer1.json"
SIM_COUNT = 200
SEED = 20240101


def main() -> None:
    t0 = time.perf_counter()
    sample = json.loads(SAMPLE.read_text())
    eligible = [s for s in sample["states"] if s["eligible"]]
    svc = load_v2_service()
    params = load_production_parameters()
    records = []
    for entry in eligible:
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
        cfg = SimulationConfig(simulation_count=SIM_COUNT, master_seed=SEED,
                               pit_dynamics_enabled=True)
        started = time.perf_counter()
        result = compare_v3_strategies(
            relief.state, params, cfg, Assumptions(),
            entry["target_driver_id"])
        records.append({
            "race_id": entry["race_id"], "anchor": a,
            "target_driver_id": entry["target_driver_id"],
            "stage": entry["stage"], "decision_lap": entry["decision_lap"],
            "state_identity": entry["state_identity"],
            "runtime_s": round(time.perf_counter() - started, 2),
            "result": result.to_dict(),
        })
        print(f"{entry['race_id']} {a['driver_id']} lap{a['lap_number']} "
              f"supported={result.supported} "
              f"({time.perf_counter()-t0:.0f}s elapsed)", flush=True)
    payload = {"sim_count": SIM_COUNT, "seed": SEED, "states": records,
               "runtime_s": round(time.perf_counter() - t0, 1)}
    OUT.write_text(json.dumps(payload))
    print(f"layer1: {len(records)} states -> {OUT}")


if __name__ == "__main__":
    main()

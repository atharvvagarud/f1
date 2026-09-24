"""Phase-7 S3 performance / memory benchmark (one representative MID state).

Compares, on the accepted MID R7.1 anchor:

- the baseline Phase-6 aggregate-only ``MonteCarloEngine.run`` (no per-index
  collection), and
- the S3 paired baseline+intervention run (two simulations, per-index
  collection on both arms),

for 1 000 and 10 000 trajectories. Reports wall time, relative overhead and
process / traced memory. Paired execution performs TWO simulations, so a
~2x runtime versus a single aggregate run is expected and is not a regression.

Usage (from the repository root)::

    /opt/homebrew/bin/python3.11 scripts/benchmark_phase7_s3_paired.py
"""

from __future__ import annotations

import json
import resource
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "tests")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from v2.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from v2.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from v2.strategy import StrategyAction, StrategyIntervention, run_pair  # noqa: E402

MID = {"season": 2022, "race_id": "2022-r01-R", "driver": "perez", "lap": 30}
COUNTS = (1000, 10000)
SEED = 20240101


def _maxrss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes.
    return value if sys.platform == "darwin" else value * 1024


def main() -> dict:
    from test_v2_phase6_r71 import _params_through, _real_state
    state = _real_state(MID["season"], MID["race_id"], MID["driver"],
                        MID["lap"])
    params = _params_through(MID["season"] - 1)
    target = MID["driver"]
    intervention = StrategyIntervention(
        target_driver_id=target, action=StrategyAction.PIT_NOW,
        requested_compound=None,
        decision_lap=state.driver_by_id[target].lap_number,
        decision_state_identity=state.identity())

    results = []
    for count in COUNTS:
        config = SimulationConfig(
            simulation_count=count, master_seed=SEED, sample_orders=0,
            pit_dynamics_enabled=True)

        baseline_peak_before = _maxrss_bytes()
        started = time.perf_counter()
        MonteCarloEngine().run(state, params, config, Assumptions())
        baseline_s = time.perf_counter() - started
        baseline_peak = _maxrss_bytes() - baseline_peak_before

        tracemalloc.start()
        started = time.perf_counter()
        pair = run_pair(state, params, config, Assumptions(), intervention)
        paired_s = time.perf_counter() - started
        _, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        results.append({
            "count": count,
            "baseline_aggregate_s": baseline_s,
            "paired_baseline_plus_intervention_s": paired_s,
            "relative_overhead_paired_over_single": paired_s / baseline_s,
            "paired_s_per_simulation": paired_s / count,
            "baseline_process_peak_delta_bytes": baseline_peak,
            "paired_traced_peak_bytes": traced_peak,
            "valid_pairs": pair.diagnostics.pairs_both_valid,
        })
    return {
        "state": MID,
        "seed": SEED,
        "note": "paired runs two simulations; ~2x single-run time is expected",
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))

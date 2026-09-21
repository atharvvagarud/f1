"""R5 Monte Carlo benchmark / convergence diagnostic (Phase 6, R5-AE/AD).

Loads an explicit historical fixture through the frozen Phase-5 replay seam,
adapts it with R2, loads an explicit R3 parameter artifact, and runs the R5
stochastic Monte Carlo engine for the requested simulation counts. It reports
only factual measurements (wall time, simulations/sec, valid/invalid counts,
peak RSS, and a simple binomial win-probability standard error). It performs
no generation, no training, and never reads 2025.

Usage:
    python scripts/benchmark_phase6_monte_carlo.py
    python scripts/benchmark_phase6_monte_carlo.py --counts 1000 10000 50000
    python scripts/benchmark_phase6_monte_carlo.py --json out.json

Output is reproducible except for timing / memory.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from v2 import replay as RP  # noqa: E402
from v2.race_state_reconstruction import RaceStateReconstructor  # noqa: E402
from v2.replay_reconstruction import ReplayReconstructor  # noqa: E402
from v2.simulation.adapter import from_race_state  # noqa: E402
from v2.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from v2.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from v2.simulation.params import load_simulation_parameters  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Explicit factual fixtures (2018-2024 only; no 2025).
FIXTURES = (
    ("early", 2023, "2023-r01-R", "alonso", 2),
    ("mid", 2023, "2023-r01-R", "alonso", 28),
    ("late", 2023, "2023-r01-R", "max_verstappen", 40),
)


def _paths(season: int, race_id: str) -> dict:
    processed = PROJECT_ROOT / "data" / "v2" / "processed"
    return {
        "d9": (processed / "driver_lap_state_d9" / f"season={season}"
               / f"driver_lap_state_d9__d9-{season}.parquet"),
        "results": (processed / "results" / f"season={season}"
                    / f"results__{race_id}.parquet"),
        "races": (processed / "races" / f"season={season}"
                  / f"races__{race_id}.parquet"),
    }


def load_fixture(season: int, race_id: str, driver: str, lap: int):
    paths = _paths(season, race_id)
    states = pd.read_parquet(paths["d9"])
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(paths["results"])
    meta = {}
    if paths["races"].exists():
        races = pd.read_parquet(paths["races"])
        for row in races.itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": None if pd.isna(scheduled)
                else int(scheduled)}
    service = ReplayReconstructor(
        RP.build_replay_timeline(states),
        RaceStateReconstructor(states, results, race_meta=meta or None))
    for frame in service.timeline.frames:
        if (frame.anchor_driver_id == driver
                and frame.anchor_lap_number == lap):
            state = from_race_state(service.state_at(frame.frame_index),
                                    anchor_frame_index=frame.frame_index)
            return state
    raise SystemExit(
        f"fixture anchor {(season, race_id, driver, lap)} not found")


def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    if sys.platform == "darwin":
        return value / (1024.0 * 1024.0)
    return value / 1024.0


def run_case(params, state, count: int, seed: int, chunk_size: int,
             pit_dynamics: bool = False,
             collect_diagnostics: bool = None) -> dict:
    if collect_diagnostics is None:
        collect_diagnostics = pit_dynamics
    config = SimulationConfig(simulation_count=count, master_seed=seed,
                              sample_orders=0,
                              pit_dynamics_enabled=pit_dynamics)
    engine = MonteCarloEngine(chunk_size=chunk_size)
    # Warm once on a tiny run so first-call overhead is not the headline.
    engine.run(state, params, SimulationConfig(simulation_count=10,
                                               master_seed=seed,
                                               pit_dynamics_enabled=pit_dynamics),
               Assumptions())
    started = time.perf_counter()
    result = engine.run(state, params, config, Assumptions(),
                        collect_diagnostics=collect_diagnostics)
    elapsed = time.perf_counter() - started
    leaders = sorted(result.driver_summaries,
                     key=lambda summary: (-summary.win_probability,
                                          summary.driver_id))
    top = []
    valid = result.valid_simulation_count
    for summary in leaders[:5]:
        p = summary.win_probability
        se = math.sqrt(p * (1.0 - p) / valid) if valid else float("nan")
        top.append({"driver_id": summary.driver_id,
                    "win_probability": p,
                    "standard_error": se})
    record = {
        "count": count,
        "seed": seed,
        "chunk_size": chunk_size,
        "wall_time_s": elapsed,
        "simulations_per_second": (count / elapsed) if elapsed > 0 else None,
        "valid_simulations": valid,
        "invalid_simulations": result.invalid_simulation_count,
        "peak_rss_mb": peak_rss_mb(),
        "top_win_probabilities": top,
    }
    if pit_dynamics and engine.last_diagnostics is not None:
        record["pit_diagnostics"] = engine.last_diagnostics.to_dict()
    return record


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", type=int, nargs="+",
                        default=[1000, 10000, 50000],
                        help="simulation counts to benchmark")
    parser.add_argument("--through-season", type=int, default=2024)
    parser.add_argument("--seed", type=int, default=20240101)
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--artifact", default=None,
                        help="parameter artifact directory or manifest.json")
    parser.add_argument("--pit-dynamics", action="store_true",
                        help="enable the R6 pit model (default: R5-equivalent)")
    parser.add_argument("--no-diagnostics", action="store_true",
                        help="R7-AC: production memory mode; do not retain "
                             "the descriptive pit diagnostics lists")
    parser.add_argument("--json", default=None,
                        help="optional path to write measured metrics as JSON")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.through_season > 2024:
        print("error: through-season must be <= 2024 (2025 is firewalled)")
        return 2
    artifact = args.artifact or (
        PROJECT_ROOT / "data" / "v2" / "simulation" / "params"
        / f"r3-v1__through-{args.through_season}")
    params = load_simulation_parameters(artifact)

    mechanics = ["pit_dynamics"] if args.pit_dynamics else []
    report = {
        "monte_carlo_version": "r6",
        "parameter_version": params.parameter_version,
        "parameter_set_id": params.parameter_set_id,
        "through_season": args.through_season,
        "seed": args.seed,
        "chunk_size": args.chunk_size,
        "mechanics_enabled": mechanics,
        "diagnostics_enabled": (args.pit_dynamics
                                and not args.no_diagnostics),
        "fixtures": {},
    }
    print(f"mechanics_enabled={mechanics or ['none (R5-equivalent)']}")
    print(f"parameter_version={params.parameter_version}")

    for name, season, race_id, driver, lap in FIXTURES:
        state = load_fixture(season, race_id, driver, lap)
        print(f"\n=== fixture {name}: {race_id} "
              f"{driver} lap {lap} ===")
        print(f"field_size={state.roster_size} "
              f"leader_laps={state.leader_laps_done} "
              f"scheduled_laps={state.scheduled_laps} "
              f"remaining_leader_laps="
              f"{state.scheduled_laps - state.leader_laps_done}")
        case_records = []
        for count in args.counts:
            record = run_case(
                params, state, count, args.seed, args.chunk_size,
                args.pit_dynamics,
                collect_diagnostics=False if args.no_diagnostics else None)
            case_records.append(record)
            print(f"  N={record['count']:>6} "
                  f"t={record['wall_time_s']:.3f}s "
                  f"rate={record['simulations_per_second']:.0f}/s "
                  f"valid={record['valid_simulations']} "
                  f"invalid={record['invalid_simulations']} "
                  f"peak_rss={record['peak_rss_mb']:.1f}MB")
            if "pit_diagnostics" in record:
                diag = record["pit_diagnostics"]
                print(f"      mean_pits/driver={diag['mean_pits_per_driver']:.3f} "
                      f"zero_pits={diag['fraction_zero_pits']:.3f} "
                      f"ge2_pits={diag['fraction_ge2_pits']:.3f} "
                      f"pit_events={diag['total_pit_events']}")
            for entry in record["top_win_probabilities"][:3]:
                print(f"      {entry['driver_id']:<20} "
                      f"p_win={entry['win_probability']:.4f} "
                      f"se={entry['standard_error']:.4f}")
        report["fixtures"][name] = {
            "race_id": race_id,
            "anchor_driver_id": driver,
            "anchor_lap": lap,
            "field_size": state.roster_size,
            "leader_laps_done": state.leader_laps_done,
            "scheduled_laps": state.scheduled_laps,
            "remaining_leader_laps": (
                state.scheduled_laps - state.leader_laps_done),
            "cases": case_records,
        }

    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

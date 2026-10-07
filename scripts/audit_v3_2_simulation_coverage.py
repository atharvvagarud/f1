#!/usr/bin/env python3
"""V3.2A read-only simulation coverage + architecture audit driver.

Audit only. This script NEVER modifies simulator source, parameters,
frozen artifacts, or replay caches. It performs NO model training and runs
NO expensive Monte Carlo sweep for eligibility: a replay checkpoint is
classified simulation-capable by input validation alone
(RaceState -> R2 adapter -> R4 parameter selection -> R4 start-state
validation), which is exactly the honest prefix of every real simulation
request (see ``api/v2_simulation_service.py``).

Modes:
  coverage     full replay catalogue eligibility audit (default)
  perf         wall-clock benchmarks on representative states
  convergence  winner-frequency stability across run counts

Usage:
  python scripts/audit_v3_2_simulation_coverage.py --mode coverage
  python scripts/audit_v3_2_simulation_coverage.py --mode coverage --limit-races 2
  python scripts/audit_v3_2_simulation_coverage.py --mode perf
  python scripts/audit_v3_2_simulation_coverage.py --mode convergence

Output is JSON on stdout (or --out PATH). No timestamps, usernames,
hostnames, or absolute paths are emitted.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.adapter import (  # noqa: E402
    SimulationUnavailableError,
    from_race_state,
)
from raceintel.simulation.config import (  # noqa: E402
    Assumptions,
    SimulationConfig,
)
from raceintel.simulation.engine import (  # noqa: E402
    ExecutionPolicy,
    SimulationUnsupportedError,
    _validate_start_state,
    select_pace_parameters,
)
from raceintel.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "v2" / "processed"
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"

AUDIT_VERSION = "v3.2a-audit-v1"
SIMULATION_CONTRACT = "v1"
RETROSPECTIVE_THROUGH_SEASON = 2024

# Stable audit-only taxonomy. Every ineligible checkpoint maps to one token.
TAXONOMY = (
    "SIMULATION_CAPABLE",
    "TERMINAL_STATE",
    "UNSUPPORTED_TRACK_STATE",
    "WET_CONDITIONS",
    "MISSING_TYRE_STATE",
    "STALE_ROSTER_OBSERVATION",
    "MISSING_RACE_METADATA",
    "MISSING_DRIVER_OBSERVATION",
    "MISSING_SIM_PARAMETER",
    "UNSUPPORTED_SEASON",
    "TEMPORAL_POLICY",
    "RETIRED_DRIVER_PRESENT",
    "INVALID_INPUT",
    "RECONSTRUCTION_FAILURE",
    "OTHER",
)

_ADAPTER_TO_TAXONOMY = {
    "unobserved_roster_member": "MISSING_DRIVER_OBSERVATION",
    "missing_pit_count": "MISSING_DRIVER_OBSERVATION",
    "missing_scheduled_laps": "MISSING_RACE_METADATA",
    "missing_leader_progress": "MISSING_RACE_METADATA",
    "leader_progress_exceeds_scheduled_laps": "INVALID_INPUT",
    "driver_lap_exceeds_leader_progress": "INVALID_INPUT",
    "invalid_position": "INVALID_INPUT",
}

_ENGINE_TO_TAXONOMY = {
    "red_flag_track_state": "UNSUPPORTED_TRACK_STATE",
    "neutralized_track_state": "UNSUPPORTED_TRACK_STATE",
    "unknown_track_state": "UNSUPPORTED_TRACK_STATE",
    "wet_track_conditions": "WET_CONDITIONS",
    "wet_compound_state": "WET_CONDITIONS",
    "missing_tyre_age": "MISSING_TYRE_STATE",
    "non_contemporaneous_roster_member": "STALE_ROSTER_OBSERVATION",
    "missing_circuit_id": "MISSING_RACE_METADATA",
    "missing_season": "MISSING_RACE_METADATA",
    "unsupported_season": "UNSUPPORTED_SEASON",
    "missing_pace_parameter": "MISSING_SIM_PARAMETER",
    "parameter_temporal_leak": "TEMPORAL_POLICY",
    "retired_driver_unsupported": "RETIRED_DRIVER_PRESENT",
    "leader_progress_not_represented": "INVALID_INPUT",
}


def stage_for(fraction: float) -> str:
    if fraction < 1.0 / 3.0:
        return "EARLY"
    if fraction < 2.0 / 3.0:
        return "MID"
    return "LATE"


def classify_checkpoint(state_at_fn, frame_index: int, parameters):
    """Audit-only eligibility classifier (input validation only, no MC)."""
    try:
        state = state_at_fn(frame_index)
    except Exception as exc:  # noqa: BLE001 - audit must classify, not crash
        return ("RECONSTRUCTION_FAILURE",
                f"reconstruction_error: {type(exc).__name__}: {exc}",
                None, None, None)
    try:
        sim_state = from_race_state(state)
    except SimulationUnavailableError as exc:
        taxon = _ADAPTER_TO_TAXONOMY.get(exc.reason, "OTHER")
        return (taxon, f"adapter:{exc.reason}", None, None, None)
    except Exception as exc:  # noqa: BLE001
        return ("OTHER", f"adapter_error: {type(exc).__name__}: {exc}",
                None, None, None)
    scheduled = sim_state.scheduled_laps
    leader_done = sim_state.leader_laps_done
    fraction = (leader_done / scheduled) if scheduled else 0.0
    stage = stage_for(fraction)
    if leader_done >= scheduled:
        return ("TERMINAL_STATE", "terminal_state: leader_laps_done >= "
                "scheduled_laps (no remaining race to simulate)",
                stage, fraction, sim_state)
    try:
        selection = select_pace_parameters(sim_state, parameters)
    except SimulationUnsupportedError as exc:
        taxon = _ENGINE_TO_TAXONOMY.get(exc.reason, "OTHER")
        return (taxon, f"engine_select:{exc.reason}", stage, fraction,
                sim_state)
    try:
        _validate_start_state(sim_state, selection)
    except SimulationUnsupportedError as exc:
        taxon = _ENGINE_TO_TAXONOMY.get(exc.reason, "OTHER")
        return (taxon, f"engine_validate:{exc.reason}", stage, fraction,
                sim_state)
    return ("SIMULATION_CAPABLE", "capable", stage, fraction, sim_state)


def season_of(race_id: str) -> int:
    return int(race_id.split("-")[0])


_SEASON_FRAME_CACHE: dict = {}


def load_race_inputs(season: int, race_id: str):
    base = str(PROCESSED)
    frame = _SEASON_FRAME_CACHE.get(season)
    if frame is None:
        frame = pd.read_parquet(
            os.path.join(base, "driver_lap_state_d9", f"season={season}",
                         f"driver_lap_state_d9__d9-{season}.parquet"))
        _SEASON_FRAME_CACHE[season] = frame
    states = frame[frame["race_id"] == race_id].copy()
    if len(states) == 0:
        raise ValueError(f"no canonical rows for race {race_id!r}")
    results = pd.read_parquet(
        os.path.join(base, "results", f"season={season}",
                     f"results__{race_id}.parquet"))
    meta: dict = {}
    races_path = os.path.join(base, "races", f"season={season}",
                              f"races__{race_id}.parquet")
    if os.path.exists(races_path):
        for row in pd.read_parquet(races_path).itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(scheduled)
                                   else int(scheduled))}
    return states, results, meta


def run_coverage(limit_races=None, max_checkpoints=None):
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT,
                              RETROSPECTIVE_THROUGH_SEASON))
    paths = sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json")))
    if limit_races is not None:
        paths = paths[:limit_races]
    checkpoints_out = []
    races_out = []
    for path in paths:
        artifact = json.load(open(path, encoding="utf-8"))
        race_id = artifact["race_id"]
        season = season_of(race_id)
        frames = sorted(entry["checkpoint"]["frame_index"]
                        for entry in artifact["checkpoints"])
        if max_checkpoints is not None:
            frames = frames[:max_checkpoints]
        try:
            states, results, meta = load_race_inputs(season, race_id)
            timeline = RP.build_replay_timeline(states)
            service = ReplayReconstructor(
                timeline, RaceStateReconstructor(states, results,
                                                 race_meta=meta or None))
        except Exception as exc:  # noqa: BLE001
            for frame_index in frames:
                checkpoints_out.append({
                    "race_id": race_id, "season": season,
                    "frame_index": frame_index, "stage": None,
                    "fraction": None, "verdict": "RECONSTRUCTION_FAILURE",
                    "reason": f"race_load_error: {type(exc).__name__}",
                })
            races_out.append({"race_id": race_id, "season": season,
                              "checkpoint_count": len(frames),
                              "eligible_count": 0,
                              "dominant_failure": "RECONSTRUCTION_FAILURE"})
            continue
        eligible = 0
        failures: dict = {}
        for frame_index in frames:
            verdict, reason, stage, fraction, _ = classify_checkpoint(
                service.state_at, frame_index, parameters)
            leader_lap = None
            for entry in artifact["checkpoints"]:
                if entry["checkpoint"]["frame_index"] == frame_index:
                    leader_lap = entry["checkpoint"].get("leader_lap")
                    break
            checkpoints_out.append({
                "race_id": race_id, "season": season,
                "frame_index": frame_index, "leader_lap": leader_lap,
                "stage": stage,
                "fraction": (round(fraction, 4) if fraction is not None
                             else None),
                "verdict": verdict, "reason": reason,
            })
            if verdict == "SIMULATION_CAPABLE":
                eligible += 1
            else:
                failures[verdict] = failures.get(verdict, 0) + 1
        dominant = None
        if failures:
            dominant = sorted(failures.items(),
                              key=lambda kv: (-kv[1], kv[0]))[0][0]
        races_out.append({"race_id": race_id, "season": season,
                          "checkpoint_count": len(frames),
                          "eligible_count": eligible,
                          "dominant_failure": dominant})
    total = len(checkpoints_out)
    eligible_total = sum(1 for c in checkpoints_out
                         if c["verdict"] == "SIMULATION_CAPABLE")
    by_verdict: dict = {}
    for c in checkpoints_out:
        by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1
    return {
        "audit_version": AUDIT_VERSION,
        "mode": "coverage",
        "parameter_set": "phase6-r3-empirical",
        "parameter_through_season": RETROSPECTIVE_THROUGH_SEASON,
        "execution_policy": "retrospective_product",
        "total_checkpoints": total,
        "eligible_checkpoints": eligible_total,
        "ineligible_checkpoints": total - eligible_total,
        "coverage_fraction": (round(eligible_total / total, 4)
                              if total else 0.0),
        "by_verdict": dict(sorted(by_verdict.items())),
        "races": races_out,
        "checkpoints": checkpoints_out,
    }


def _representative_states(parameters, specs):
    """Build SimulationStates for (race_id, frame_index) specs."""
    out = []
    by_race: dict = {}
    for race_id, frame_index in specs:
        by_race.setdefault(race_id, []).append(frame_index)
    for race_id, frames in sorted(by_race.items()):
        season = season_of(race_id)
        states, results, meta = load_race_inputs(season, race_id)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        for frame_index in sorted(frames):
            state = service.state_at(frame_index)
            sim_state = from_race_state(state)
            out.append((race_id, frame_index, sim_state))
    return out, parameters


def run_perf():
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT,
                              RETROSPECTIVE_THROUGH_SEASON))
    specs = _default_perf_specs()
    states, _ = _representative_states(parameters, specs)
    assumptions = Assumptions()
    rows = []
    skipped = []
    for race_id, frame_index, sim_state in states:
        try:
            selection = select_pace_parameters(sim_state, parameters)
            _validate_start_state(sim_state, selection)
        except SimulationUnsupportedError as exc:
            skipped.append({"race_id": race_id, "frame_index": frame_index,
                            "reason": f"engine:{exc.reason}"})
            continue
        for count in (100, 1000, 10000):
            config = SimulationConfig(simulation_count=count,
                                      master_seed=20240101)
            engine = MonteCarloEngine()
            start = time.perf_counter()
            result = engine.run(sim_state, parameters, config, assumptions,
                                execution_policy=(
                                    ExecutionPolicy.RETROSPECTIVE_PRODUCT))
            elapsed = time.perf_counter() - start
            payload = json.dumps(result.to_dict(), sort_keys=True).encode()
            rows.append({
                "race_id": race_id, "frame_index": frame_index,
                "n_runs": count, "wall_clock_s": round(elapsed, 3),
                "runs_per_s": round(count / elapsed, 1) if elapsed > 0
                else None,
                "output_bytes": len(payload),
                "valid": result.valid_simulation_count,
                "invalid": result.invalid_simulation_count,
            })
    return {"audit_version": AUDIT_VERSION, "mode": "perf",
            "parameter_through_season": RETROSPECTIVE_THROUGH_SEASON,
            "rows": rows, "skipped": skipped}


def _default_perf_specs():
    """Representative (race, frame) specs: early/mid/late x 3 circuits.

    Frames verified SIMULATION_CAPABLE by the coverage audit (clean races
    with no pre-T retirement, dry green anchors, complete tyre state).
    ``run_perf``/``run_convergence`` re-validate each spec and skip any
    state the frozen engine refuses, recording the refusal explicitly.
    """
    return [
        ("2023-r05-R", 160),
        ("2023-r05-R", 540),
        ("2023-r05-R", 939),
        ("2023-r07-R", 180),
        ("2023-r07-R", 640),
        ("2023-r07-R", 1094),
        ("2024-r15-R", 200),
        ("2024-r15-R", 700),
        ("2024-r15-R", 1187),
    ]


def run_convergence():
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT,
                              RETROSPECTIVE_THROUGH_SEASON))
    specs = _default_perf_specs()[:3]
    states, _ = _representative_states(parameters, specs)
    assumptions = Assumptions()
    rows = []
    skipped = []
    for race_id, frame_index, sim_state in states:
        try:
            selection = select_pace_parameters(sim_state, parameters)
            _validate_start_state(sim_state, selection)
        except SimulationUnsupportedError as exc:
            skipped.append({"race_id": race_id, "frame_index": frame_index,
                            "reason": f"engine:{exc.reason}"})
            continue
        prev = None
        for count in (100, 500, 1000, 5000, 10000):
            config = SimulationConfig(simulation_count=count,
                                      master_seed=20240101)
            engine = MonteCarloEngine()
            result = engine.run(sim_state, parameters, config, assumptions,
                                execution_policy=(
                                    ExecutionPolicy.RETROSPECTIVE_PRODUCT))
            freqs = {s.driver_id: s.win_probability
                     for s in result.driver_summaries}
            top = max(sorted(freqs.items()), key=lambda kv: (kv[1], kv[0]))
            tv = None
            if prev is not None:
                tv = round(sum(abs(freqs[d] - prev[d]) for d in freqs) / 2, 4)
            rows.append({"race_id": race_id, "frame_index": frame_index,
                         "n_runs": count,
                         "top_driver": top[0],
                         "top_win_probability": round(top[1], 4),
                         "total_variation_vs_prev": tv})
            prev = freqs
    return {"audit_version": AUDIT_VERSION, "mode": "convergence",
            "parameter_through_season": RETROSPECTIVE_THROUGH_SEASON,
            "rows": rows, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="coverage",
                        choices=["coverage", "perf", "convergence"])
    parser.add_argument("--limit-races", type=int, default=None)
    parser.add_argument("--max-checkpoints", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.mode == "coverage":
        payload = run_coverage(limit_races=args.limit_races,
                               max_checkpoints=args.max_checkpoints)
    elif args.mode == "perf":
        payload = run_perf()
    else:
        payload = run_convergence()
    text = json.dumps(payload, indent=1, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

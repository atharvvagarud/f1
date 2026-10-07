#!/usr/bin/env python3
"""V3.2C pre-change R3 parity corpus freezer (Part C/D).

Read-only. Selects a deterministic corpus of currently SIMULATION_CAPABLE
checkpoints spanning seasons/circuits/stages, runs the frozen R3 stochastic
path (pits-off baseline arm + a pits-on production-path subset), and persists
canonical result identities for post-change bit-exact regression.

No simulator source, parameter, artifact, or replay cache is modified.
No model training. Output carries no timestamps, usernames, or paths.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_v3_2_simulation_coverage import (  # noqa: E402
    classify_checkpoint,
    load_race_inputs,
    season_of,
)
from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.config import (  # noqa: E402
    Assumptions,
    SimulationConfig,
)
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.monte_carlo import (  # noqa: E402
    MONTE_CARLO_VERSION,
    PIT_DYNAMICS_VERSION,
)
from raceintel.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.state import (  # noqa: E402
    SIMULATION_CONTRACT_VERSION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"

PARITY_SEED = 20240101
PARITY_RUNS = 100
PITSON_SUBSET = 20
PER_SEASON_QUOTA = 10


def _select_corpus(parameters):
    """Deterministic capable-checkpoint selection (1 EARLY/MID/LATE/race)."""
    paths = sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json")))
    by_season: dict[int, list] = {}
    for path in paths:
        race_id = json.load(open(path, encoding="utf-8"))["race_id"]
        by_season.setdefault(season_of(race_id), []).append((race_id, path))
    corpus = []
    for season in sorted(by_season):
        taken = 0
        for race_id, path in sorted(by_season[season]):
            if taken >= PER_SEASON_QUOTA:
                break
            artifact = json.load(open(path, encoding="utf-8"))
            frames = sorted(e["checkpoint"]["frame_index"]
                            for e in artifact["checkpoints"])
            states, results, meta = load_race_inputs(season, race_id)
            timeline = RP.build_replay_timeline(states)
            service = ReplayReconstructor(
                timeline, RaceStateReconstructor(states, results,
                                                 race_meta=meta or None))
            band_first: dict[str, tuple] = {}
            for frame_index in frames:
                verdict, _reason, stage, _frac, _st = classify_checkpoint(
                    service.state_at, frame_index, parameters)
                if verdict == "SIMULATION_CAPABLE" and stage not in band_first:
                    band_first[stage] = (race_id, frame_index, stage)
            for band in ("EARLY", "MID", "LATE"):
                if band in band_first and taken < PER_SEASON_QUOTA:
                    corpus.append(band_first[band])
                    taken += 1
    return corpus


def _run_once(sim_state, parameters, *, pits: bool, seed: int, n_runs: int):
    config = SimulationConfig(simulation_count=n_runs, master_seed=seed,
                              pit_dynamics_enabled=pits)
    result = MonteCarloEngine().run(
        sim_state, parameters, config, Assumptions(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    winners = {s.driver_id: round(float(s.win_probability), 6)
               for s in result.driver_summaries}
    top = max(sorted(winners.items()), key=lambda kv: (kv[1], kv[0]))
    return {
        "pits_enabled": pits,
        "seed": seed,
        "n_runs": n_runs,
        "result_identity": result.identity(),
        "request_identity": result.simulation_request_identity,
        "roster": [s.driver_id for s in result.driver_summaries],
        "valid": result.valid_simulation_count,
        "invalid": result.invalid_simulation_count,
        "top_driver": top[0],
        "top_win_probability": top[1],
        "winner_frequencies": winners,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT, 2024))
    corpus = _select_corpus(parameters)
    if args.limit is not None:
        corpus = corpus[:args.limit]
    entries = []
    by_race: dict = {}
    for race_id, frame_index, _stage in corpus:
        by_race.setdefault(race_id, []).append(frame_index)
    for race_id in sorted(by_race):
        season = season_of(race_id)
        states, results, meta = load_race_inputs(season, race_id)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        for frame_index in sorted(by_race[race_id]):
            verdict, _r, stage, frac, sim_state = classify_checkpoint(
                service.state_at, frame_index, parameters)
            assert verdict == "SIMULATION_CAPABLE", (race_id, frame_index)
            arms = [_run_once(sim_state, parameters, pits=False,
                              seed=PARITY_SEED, n_runs=PARITY_RUNS)]
            entries.append({
                "race_id": race_id,
                "frame_index": frame_index,
                "stage": stage,
                "fraction": round(frac, 4),
                "simulation_contract": SIMULATION_CONTRACT_VERSION,
                "monte_carlo_version": MONTE_CARLO_VERSION,
                "pit_dynamics_version": PIT_DYNAMICS_VERSION,
                "parameter_set_id": parameters.parameter_set_id,
                "parameter_hash": parameters.scientific_hash(),
                "arms": arms,
            })
    for entry in entries[:PITSON_SUBSET]:
        race_id, frame_index = entry["race_id"], entry["frame_index"]
        season = season_of(race_id)
        states, results, meta = load_race_inputs(season, race_id)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        _v, _r, _s, _f, sim_state = classify_checkpoint(
            service.state_at, frame_index, parameters)
        entry["arms"].append(_run_once(
            sim_state, parameters, pits=True, seed=PARITY_SEED,
            n_runs=PARITY_RUNS))
    payload = {
        "schema_version": "v3.2c-parity-v1",
        "simulation_contract": SIMULATION_CONTRACT_VERSION,
        "monte_carlo_version": MONTE_CARLO_VERSION,
        "pit_dynamics_version": PIT_DYNAMICS_VERSION,
        "parameter_set_id": parameters.parameter_set_id,
        "parameter_hash": parameters.scientific_hash(),
        "default_seed": PARITY_SEED,
        "default_n_runs": PARITY_RUNS,
        "entry_count": len(entries),
        "entries": entries,
    }
    text = json.dumps(payload, indent=1, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""V3.2C DNS-aware eligibility audit (Parts Y/Z/AA/AB/AC/AD/AJ).

Read-only. Recomputes eligibility over the full 149-race / 9644-checkpoint
replay catalogue through the V3.2C presence adapter
(``raceintel.simulation.presence.prepare_initial_state``: frozen DNS
exclusion + unchanged R3 validation), reporting overall / season / stage /
race coverage, failure taxonomy, DNS recovery accounting, and scan
runtime. No simulator source, parameter, artifact, or replay cache is
modified. No Monte Carlo runs (eligibility is input validation only).

Output JSON on stdout (or --out). No timestamps, usernames, or paths.
"""

from __future__ import annotations

import argparse
import glob
import json
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
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.presence import (  # noqa: E402
    ELIGIBILITY_TAXONOMY,
    prepare_initial_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "v2" / "processed"
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"


def season_of(race_id: str) -> int:
    return int(race_id.split("-")[0])


def stage_for(fraction: float | None) -> str | None:
    if fraction is None:
        return None
    if fraction < 1.0 / 3.0:
        return "EARLY"
    if fraction < 2.0 / 3.0:
        return "MID"
    return "LATE"


def _grid_map(results: pd.DataFrame) -> dict:
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        if grid is None or (isinstance(grid, float) and grid != grid):
            out[str(row.driver_id)] = None
        else:
            out[str(row.driver_id)] = float(grid)
    return out


def run_coverage(limit_races=None):
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT, 2024))
    t_start = time.perf_counter()
    paths = sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json")))
    if limit_races is not None:
        paths = paths[:limit_races]
    checkpoints_out = []
    races_out = []
    dns_recovered = []
    for path in paths:
        artifact = json.load(open(path, encoding="utf-8"))
        race_id = artifact["race_id"]
        season = season_of(race_id)
        frames = sorted(entry["checkpoint"]["frame_index"]
                        for entry in artifact["checkpoints"])
        leader_by_frame = {entry["checkpoint"]["frame_index"]:
                           entry["checkpoint"].get("leader_lap")
                           for entry in artifact["checkpoints"]}
        base = str(PROCESSED)
        frame = pd.read_parquet(
            f"{base}/driver_lap_state_d9/season={season}/"
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            f"{base}/results/season={season}/results__{race_id}.parquet")
        meta: dict = {}
        races_path = (f"{base}/races/season={season}/races__{race_id}.parquet")
        try:
            for row in pd.read_parquet(races_path).itertuples():
                scheduled = getattr(row, "total_laps_scheduled", None)
                meta[str(row.race_id)] = {
                    "scheduled_laps": (None if pd.isna(scheduled)
                                       else int(scheduled))}
        except FileNotFoundError:
            pass
        grid = _grid_map(results)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        eligible = 0
        failures: dict = {}
        for frame_index in frames:
            try:
                race_state = service.state_at(frame_index)
            except Exception as exc:  # noqa: BLE001 - audit classifies
                verdict, reason = ("RECONSTRUCTION_FAILURE",
                                   f"reconstruction_error: "
                                   f"{type(exc).__name__}")
                checkpoints_out.append({
                    "race_id": race_id, "season": season,
                    "frame_index": frame_index, "stage": None,
                    "fraction": None, "verdict": verdict, "reason": reason,
                    "dns_excluded": [],
                })
                failures[verdict] = failures.get(verdict, 0) + 1
                continue
            result = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=parameters,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
            verdict, reason = result.reason, result.detail
            scheduled_laps = race_state.race_context.scheduled_laps
            leader_done = race_state.race_context.race_leader_laps_at_state
            fraction = (leader_done / scheduled_laps
                        if scheduled_laps and leader_done is not None else None)
            stage = stage_for(fraction)
            checkpoints_out.append({
                "race_id": race_id, "season": season,
                "frame_index": frame_index,
                "leader_lap": leader_by_frame.get(frame_index),
                "stage": stage,
                "fraction": (round(fraction, 4) if fraction is not None
                             else None),
                "verdict": verdict, "reason": reason,
                "dns_excluded": list(result.excluded_dns_driver_ids),
            })
            if verdict == "SIMULATION_CAPABLE":
                eligible += 1
                if result.excluded_dns_driver_ids:
                    dns_recovered.append({
                        "race_id": race_id, "frame_index": frame_index,
                        "dns_excluded": list(
                            result.excluded_dns_driver_ids),
                    })
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
    elapsed = time.perf_counter() - t_start
    total = len(checkpoints_out)
    eligible_total = sum(1 for c in checkpoints_out
                         if c["verdict"] == "SIMULATION_CAPABLE")
    by_verdict: dict = {}
    for c in checkpoints_out:
        by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1
    for token in ELIGIBILITY_TAXONOMY:
        by_verdict.setdefault(token, 0)
    return {
        "audit_version": "v3.2c-coverage-v1",
        "mode": "coverage",
        "presence_adapter": "v3.2c-presence-v1",
        "field_contract": "mc2-field-v1",
        "parameter_set": "phase6-r3-empirical",
        "parameter_through_season": 2024,
        "execution_policy": "retrospective_product",
        "total_checkpoints": total,
        "eligible_checkpoints": eligible_total,
        "ineligible_checkpoints": total - eligible_total,
        "coverage_fraction": (round(eligible_total / total, 4)
                              if total else 0.0),
        "by_verdict": dict(sorted(by_verdict.items())),
        "dns_recovered_states": len(dns_recovered),
        "dns_recovered": dns_recovered,
        "scan_wall_clock_s": round(elapsed, 1),
        "races": races_out,
        "checkpoints": checkpoints_out,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-races", type=int, default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--slim", action="store_true",
                        help="omit per-checkpoint rows (summary only)")
    args = parser.parse_args()
    payload = run_coverage(limit_races=args.limit_races)
    if args.slim:
        payload = {k: v for k, v in payload.items() if k != "checkpoints"}
    text = json.dumps(payload, indent=1, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

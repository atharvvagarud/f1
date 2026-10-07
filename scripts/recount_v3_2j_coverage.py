#!/usr/bin/env python3
"""V3.2J Parts AA-AF: full 9644-checkpoint coverage recount with status.

Mirrors scripts/audit_v3_2c_coverage.py frame-for-frame over the frozen
replay-checkpoint population, but passes the pinned derived status
corpus (local artifacts only) + unreliable windows into
``prepare_initial_state``. Before/after, attribution, season/stage/race
splits, and blocker intersections are recomputed. No Monte Carlo runs.
Verifies the prereg hash. Deterministic.
"""

from __future__ import annotations

import glob
import hashlib
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
from raceintel.simulation.driver_status import (  # noqa: E402
    load_status_corpus,
    load_unreliable_windows,
)
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.presence import (  # noqa: E402
    prepare_initial_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "v2" / "processed"
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"
OUT = PROJECT_ROOT / "results" / "v3" / "v3_2j"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")
    return got


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


def main() -> int:
    check_prereg()
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT, 2024))
    resolver = load_status_corpus(OUT / "status")
    windows = load_unreliable_windows(OUT / "unreliable_windows.json")
    corpus_id = json.load(open(OUT / "status_corpus_identity.json",
                               encoding="utf-8"))
    t_start = time.perf_counter()
    checkpoints_out = []
    for path in sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json"))):
        artifact = json.load(open(path, encoding="utf-8"))
        race_id = artifact["race_id"]
        season = season_of(race_id)
        base = str(PROCESSED)
        frame = pd.read_parquet(
            f"{base}/driver_lap_state_d9/season={season}/"
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            f"{base}/results/season={season}/results__{race_id}.parquet")
        meta: dict = {}
        try:
            for row in pd.read_parquet(
                    f"{base}/races/season={season}/races__{race_id}.parquet"
                    ).itertuples():
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
        for entry in artifact["checkpoints"]:
            fi = entry["checkpoint"]["frame_index"]
            try:
                race_state = service.state_at(fi)
            except Exception as exc:  # noqa: BLE001
                checkpoints_out.append({
                    "race_id": race_id, "season": season,
                    "frame_index": fi, "verdict": "RECONSTRUCTION_FAILURE",
                    "reason": type(exc).__name__, "dns_excluded": [],
                    "status_excluded": [],
                    "stage": None, "leader_lap": None})
                continue
            result = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=parameters,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                status_resolver=resolver, status_windows=windows)
            scheduled_laps = race_state.race_context.scheduled_laps
            leader_done = race_state.race_context.race_leader_laps_at_state
            fraction = (leader_done / scheduled_laps
                        if scheduled_laps and leader_done is not None
                        else None)
            checkpoints_out.append({
                "race_id": race_id, "season": season, "frame_index": fi,
                "leader_lap": entry["checkpoint"].get("leader_lap"),
                "stage": stage_for(fraction),
                "fraction": (round(fraction, 4) if fraction is not None
                             else None),
                "verdict": ("SIMULATION_CAPABLE" if result.eligible
                            else result.reason),
                "reason": result.detail,
                "dns_excluded": list(result.excluded_dns_driver_ids),
                "status_excluded": list(result.excluded_status_driver_ids),
                "status_contract": result.status_contract_version,
            })
    elapsed = time.perf_counter() - t_start
    total = len(checkpoints_out)
    capable = [c for c in checkpoints_out
               if c["verdict"] == "SIMULATION_CAPABLE"]
    relieved = [c for c in capable if c["status_excluded"]]
    json.dump({"schema_version": "v3.2j-coverage-after-v1",
               "corpus_hash": corpus_id["corpus_hash"],
               "scan_wall_clock_s": round(elapsed, 1),
               "total": total, "eligible": len(capable),
               "fraction": round(len(capable) / total, 4),
               "relieved_by_status": len(relieved),
               "checkpoints": checkpoints_out},
              open(OUT / "coverage_after.json", "w"),
              indent=1, sort_keys=False)
    print(f"total={total} eligible={len(capable)} "
          f"({len(capable) / total:.4f}) relieved={len(relieved)} "
          f"wall={elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
